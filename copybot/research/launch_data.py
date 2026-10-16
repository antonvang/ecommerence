"""Launch-datasæt: pump.fun-graduations og de første minutters handler i hver PumpSwap-pool.

Pool-centreret: en handels retning og størrelse aflæses af ændringen i poolens to vaults (SOL og coin), som er
upåvirket af routere/aggregatorer. Den handlende er transaktionens fee payer. Reserverne efter hver handel gemmes,
så en køb- eller salgspris kan beregnes for en given størrelse (x*y=k) i stedet for at bruge minut-candles.

  python -m research.launch_data --days 14 --sample 600 --window 180

Alt gemmes i data/research/launches.db (git-ignoreret; kan genopbygges). Hver række har sin kilde-signatur.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from sniper import MIGRATION, parse_migration  # noqa: E402
from swaps import WSOL, _keys  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS grads (mint TEXT PRIMARY KEY, pool TEXT, sol_vault TEXT, tok_vault TEXT, grad_sig TEXT,
  grad_slot INTEGER, grad_ts INTEGER, sol0 REAL, tok0 REAL, sampled INTEGER DEFAULT 0, events_status TEXT,
  events_window INTEGER, fetched_at INTEGER);
CREATE TABLE IF NOT EXISTS events (sig TEXT, mint TEXT, slot INTEGER, idx INTEGER, ts INTEGER, trader TEXT, side TEXT,
  sol REAL, tokens REAL, res_sol REAL, res_tok REAL, PRIMARY KEY (sig, mint));
CREATE INDEX IF NOT EXISTS ix_ev ON events(mint, slot, idx);
CREATE TABLE IF NOT EXISTS snapshots (mint TEXT, t INTEGER, sig TEXT, slot INTEGER, ts INTEGER, res_sol REAL, res_tok REAL,
  status TEXT, PRIMARY KEY (mint, t));
CREATE TABLE IF NOT EXISTS fetch_log (ts INTEGER, what TEXT, n INTEGER, note TEXT);
"""
MIN_SOL_TRADE = 1e-4  # mindre end det er støv/spam, ikke en handel


def open_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def vault_state(tx, sol_vault, tok_vault, which):
    """(SOL, coin) i poolens to vaults før ('pre') eller efter ('post') transaktionen. None hvis de ikke er med."""
    keys, _ = _keys(tx)
    out = {}
    for b in (tx["meta"].get(which + "TokenBalances") or []):
        i = b["accountIndex"]
        if i < len(keys) and keys[i] in (sol_vault, tok_vault):
            u = b["uiTokenAmount"]
            out[keys[i]] = int(u["amount"]) / 10 ** int(u["decimals"])
    if sol_vault in out and tok_vault in out:
        return out[sol_vault], out[tok_vault]
    return None


def parse_pool_tx(tx, g):
    """Én handel i poolen ud fra vault-ændringer, eller None (ikke en handel, fejlet, eller vaults ikke med)."""
    if not tx or (tx.get("meta") or {}).get("err") is not None:
        return None
    post = vault_state(tx, g["sol_vault"], g["tok_vault"], "post")
    pre = vault_state(tx, g["sol_vault"], g["tok_vault"], "pre")
    if post is None or pre is None:
        return None  # migrationen selv (vaults oprettes) eller en transaktion uden poolens vaults
    ds, dt = post[0] - pre[0], post[1] - pre[1]
    if abs(ds) < MIN_SOL_TRADE:
        return None
    if ds > 0 and dt < 0:
        side = "buy"
    elif ds < 0 and dt > 0:
        side = "sell"
    else:
        return None  # fx likviditet tilføjet/fjernet: begge vaults samme vej
    keys, _ = _keys(tx)
    return {"sig": tx["transaction"]["signatures"][0], "slot": tx["slot"], "idx": tx.get("transactionIndex", 0),
            "ts": tx.get("blockTime"), "trader": keys[0], "side": side, "sol": abs(ds), "tokens": abs(dt),
            "res_sol": post[0], "res_tok": post[1]}


def gtfa(rpc, address, opts):
    """Alle sider fra getTransactionsForAddress (en side kan have færre end limit og stadig have flere)."""
    out, token = [], None
    while True:
        o = dict(opts)
        if token:
            o["paginationToken"] = token
        r = rpc.call("getTransactionsForAddress", [address, o]) or {}
        out += r.get("data") or []
        token = r.get("paginationToken")
        if not token or not r.get("data"):
            return out


def collect_graduations(db, rpc, t0, t1, log=print):
    """Alle rigtige graduations i [t0, t1): mint, pool, vaults, start-reserver. Idempotent (INSERT OR IGNORE)."""
    txs = gtfa(rpc, MIGRATION, {"transactionDetails": "full", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1,
                                "limit": 100, "sortOrder": "asc", "filters": {"blockTime": {"gte": t0, "lt": t1}, "status": "succeeded"}})
    n = 0
    for tx in txs:
        g = parse_migration(tx)
        if not g:
            continue
        st = vault_state(tx, g["sol_vault"], g["tok_vault"], "post")
        cur = db.execute("INSERT OR IGNORE INTO grads(mint,pool,sol_vault,tok_vault,grad_sig,grad_slot,grad_ts,sol0,tok0) "
                         "VALUES(?,?,?,?,?,?,?,?,?)", (g["mint"], g["pool"], g["sol_vault"], g["tok_vault"],
                                                       tx["transaction"]["signatures"][0], tx["slot"], g["grad_ts"],
                                                       st[0] if st else None, st[1] if st else None))
        n += cur.rowcount
    db.execute("INSERT INTO fetch_log VALUES(?,?,?,?)", (int(time.time()), "graduations", n, f"{len(txs)} migrate-tx {t0}-{t1}"))
    db.commit()
    log(f"graduations: {n} nye af {len(txs)} migrate-transaktioner")
    return n


def sample_chronological(db, n):
    """Hver k'te graduation i tidsorden, så stikprøven dækker hele perioden jævnt (markeres sampled=1)."""
    rows = db.execute("SELECT mint FROM grads ORDER BY grad_ts, grad_slot").fetchall()
    if not rows:
        return 0
    step = max(len(rows) / n, 1.0)
    pick = {rows[int(i * step)]["mint"] for i in range(min(n, len(rows)))}
    db.executemany("UPDATE grads SET sampled=1 WHERE mint=?", [(m,) for m in pick])
    db.commit()
    return len(pick)


def fetch_events(db, rpc, g, window):
    """Alle handler i poolen fra graduation til +window sek. Idempotent (PRIMARY KEY på signatur)."""
    txs = gtfa(rpc, g["pool"], {"transactionDetails": "full", "encoding": "json", "maxSupportedTransactionVersion": 1,
                                "limit": 1000, "sortOrder": "asc",
                                "filters": {"blockTime": {"gte": g["grad_ts"] - 2, "lt": g["grad_ts"] + window}, "status": "succeeded"}})
    n = 0
    for tx in txs:
        e = parse_pool_tx(tx, g)
        if e:
            db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (e["sig"], g["mint"], e["slot"], e["idx"], e["ts"], e["trader"], e["side"], e["sol"], e["tokens"],
                        e["res_sol"], e["res_tok"]))
            n += 1
    db.execute("UPDATE grads SET events_status=?, events_window=?, fetched_at=? WHERE mint=?",
               ("ok", window, int(time.time()), g["mint"]))
    db.commit()
    return n, len(txs)


def snapshot(db, rpc, g, t):
    """Poolens reserver lige før tidspunkt t: seneste transaktion før t, der indeholder begge vaults."""
    if db.execute("SELECT 1 FROM snapshots WHERE mint=? AND t=?", (g["mint"], t)).fetchone():
        return
    r = rpc.call("getTransactionsForAddress", [g["pool"], {"transactionDetails": "full", "encoding": "json",
                 "maxSupportedTransactionVersion": 1, "limit": 10, "sortOrder": "desc",
                 "filters": {"blockTime": {"lt": t}, "status": "succeeded"}}]) or {}
    for tx in r.get("data") or []:
        st = vault_state(tx, g["sol_vault"], g["tok_vault"], "post")
        if st:
            db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?)",
                       (g["mint"], t, tx["transaction"]["signatures"][0], tx["slot"], tx.get("blockTime"), st[0], st[1], "ok"))
            db.commit()
            return
    db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?,?,?)", (g["mint"], t, None, None, None, None, None, "mangler"))
    db.commit()


def main():
    from copybot import load_config
    from solana_rpc import RPC
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=14)
    ap.add_argument("--sample", type=int, default=600)
    ap.add_argument("--window", type=int, default=180, help="sekunders handler efter graduation (beslutningsdata)")
    ap.add_argument("--horizons", default="300,900,1800,3600", help="exit-tidspunkter i sek efter graduation")
    ap.add_argument("--db", default=os.path.join(HERE, "data", "research", "launches.db"))
    a = ap.parse_args()
    cfg = load_config(os.path.join(HERE, "config.json"))
    if "helius" not in cfg["rpc_url"]:
        raise SystemExit("Kræver en Helius-nøgle (getTransactionsForAddress) i config.local.json")
    rpc = RPC(cfg["rpc_url"], 8, log=lambda *x: None)
    db = open_db(a.db)
    now = int(time.time())
    t0, t1 = int(now - a.days * 86400), now - 2 * 3600  # de seneste 2 timer har ikke fuld exit-historik endnu
    day = 86400
    for s in range(t0, t1, day):
        collect_graduations(db, rpc, s, min(s + day, t1))
    print("stikprøve:", sample_chronological(db, a.sample))
    hz = [int(x) for x in a.horizons.split(",")]
    todo = db.execute("SELECT * FROM grads WHERE sampled=1 ORDER BY grad_ts").fetchall()
    for k, g in enumerate(todo, 1):
        if g["events_status"] != "ok" or (g["events_window"] or 0) < a.window:
            fetch_events(db, rpc, g, a.window)
        for h in hz:
            snapshot(db, rpc, g, g["grad_ts"] + h)
        if k % 25 == 0:
            print(f"  pools {k}/{len(todo)}", flush=True)
    print("færdig:", db.execute("SELECT COUNT(*) FROM events").fetchone()[0], "handler,",
          db.execute("SELECT COUNT(*) FROM snapshots WHERE status='ok'").fetchone()[0], "snapshots")


if __name__ == "__main__":
    main()
