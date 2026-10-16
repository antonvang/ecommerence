"""arb_v1: arbitrage mellem de to constant-product SOL/USDC-pools (Raydium AMM v4 og PumpSwap). Kun paper/historisk.

  python -m research.arb fetch     hent 12 vinduer à 300 s (pool-tilstand efter hver transaktion)
  python -m research.arb run       kør det forudregistrerede eksperiment (HYPOTHESES.md, arb_v1) én gang

Pool-tilstand = vault-saldi efter hver transaktion, sorteret efter (slot, transactionIndex). Køb/salg regnes med
x*y=k og hver pools målte gebyr. Resultatet er en ØVRE grænse: andre arbitragører i samme slot er ikke modelleret.
"""
from __future__ import annotations

import bisect
import json
import os
import random
import sqlite3
import statistics
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.launch_data import gtfa, vault_state  # noqa: E402

VERSION = "arb_v1"
POOLS = {
    "A": {"name": "Raydium AMM v4", "pool": "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2",
          "sol_vault": "DQyrAcCrDXQ7NeoqGgDCZwBvWDcYmFCjSb9JtteuvPpz", "usdc_vault": "HLmqeL62xR1QoZ1HKKbXRrdN1p3phKpxRMb2VVopvBBz",
          "fee": 0.0025},
    "B": {"name": "PumpSwap", "pool": "Gf7sXMoP8iRw4iiXmJ1nq4vxcRycbGXy5RL8a8LnTd3v",
          "sol_vault": "EjHirXt2", "usdc_vault": "nML7ms", "fee": 0.00275},  # vault-adresser findes ud fra prefix ved fetch
}
CAPITAL = 1000.0           # USDC pr. handel
TX_SOL = 0.001             # base + priority/tip pr. transaktion (ESTIMERET)
WINDOWS, WINDOW_S, DAYS = 12, 300, 14
SCHEMA = """
CREATE TABLE IF NOT EXISTS states (pool TEXT, win INTEGER, slot INTEGER, idx INTEGER, ts INTEGER, sig TEXT, sol REAL, usdc REAL,
  PRIMARY KEY (pool, sig));
CREATE TABLE IF NOT EXISTS windows (win INTEGER PRIMARY KEY, t0 INTEGER, t1 INTEGER, fetched_at INTEGER, n_a INTEGER, n_b INTEGER);
"""


# ---------- AMM-matematik ----------
def swap_out(x_in, y_out, amount, fee):
    """Output fra en x*y=k-pool med reserver (input-side, output-side), gebyr på input."""
    if amount <= 0 or x_in <= 0 or y_out <= 0:
        return 0.0
    a = amount * (1 - fee)
    return y_out * a / (x_in + a)


def round_trip(u, buy, sell):
    """USDC ud efter at købe SOL for u USDC i `buy` og sælge den i `sell`. Pools: (sol, usdc, fee)."""
    sol = swap_out(buy[1], buy[0], u, buy[2])
    return swap_out(sell[0], sell[1], sol, sell[2])


def best_trade(a, b, cap=CAPITAL):
    """(retning, u, brutto-gevinst) for den bedste atomiske rundtur mellem a og b, eller None. Rundtur er konkav i u."""
    best = None
    for name, buy, sell in (("A->B", a, b), ("B->A", b, a)):
        # marginal gevinst ved u -> 0: (1-fa)(1-fb) * (sol/usdc i buy) * (usdc/sol i sell) > 1
        if (1 - buy[2]) * (1 - sell[2]) * (buy[0] / buy[1]) * (sell[1] / sell[0]) <= 1:
            continue
        lo, hi = 0.0, cap
        for _ in range(100):
            m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            if round_trip(m1, buy, sell) - m1 < round_trip(m2, buy, sell) - m2:
                lo = m1
            else:
                hi = m2
        u = (lo + hi) / 2
        g = round_trip(u, buy, sell) - u
        if g > 0 and (best is None or g > best[2]):
            best = (name, u, g)
    return best


# ---------- tilstand over tid ----------
class Series:
    """Én pools tilstand efter hver transaktion; tilstand ved slut af slot s = sidste række med slot <= s."""

    def __init__(self, rows):
        rows = sorted(set(rows))  # (slot, idx, sol, usdc); dubletter fjernes, uorden sorteres
        self.slots = [r[0] for r in rows]
        self.rows = rows

    def at_end_of(self, slot):
        i = bisect.bisect_right(self.slots, slot) - 1
        return self.rows[i] if i >= 0 else None


def simulate_window(sa, sb, fee_a, fee_b, k, theta, tx_sol=TX_SOL, guard=True, cap=CAPITAL):
    """Gennemløb slot for slot. Returnerer (beslutninger, observerede muligheder, persistens-længder)."""
    slots = sorted(set(sa.slots) | set(sb.slots))
    if not slots:
        return [], 0, []
    decisions, observed, runs, run = [], 0, [], 0
    busy_until = -1
    for s in slots:
        ra, rb = sa.at_end_of(s), sb.at_end_of(s)
        if not ra or not rb:
            continue
        a, b = (ra[2], ra[3], fee_a), (rb[2], rb[3], fee_b)
        mid = (a[1] / a[0] + b[1] / b[0]) / 2
        cost = tx_sol * mid
        bt = best_trade(a, b, cap)
        net = (bt[2] - cost) if bt else -cost
        if bt and net > 0:
            observed += 1
            run += 1
        elif run:
            runs.append(run)
            run = 0
        if s <= busy_until or not bt or net < theta or net <= 0:
            continue
        land = s + k
        ea, eb = sa.at_end_of(land - 1), sb.at_end_of(land - 1)
        A, B = (ea[2], ea[3], fee_a), (eb[2], eb[3], fee_b)
        buy, sell = (A, B) if bt[0] == "A->B" else (B, A)
        gross = round_trip(bt[1], buy, sell) - bt[1]
        if guard and gross <= cost:
            pnl, executed = -cost, False   # transaktionen ruller tilbage: kun gebyret er tabt
        else:
            pnl, executed = gross - cost, True
        decisions.append({"slot": s, "dir": bt[0], "u": bt[1], "pred_net": net, "exec_gross": gross, "pnl": pnl,
                          "executed": executed, "cost": cost, "mid": mid})
        busy_until = land  # én transaktion ad gangen
    if run:
        runs.append(run)
    return decisions, observed, runs


# ---------- data ----------
def open_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.executescript(SCHEMA)
    return db


def resolve_vaults(rpc, p):
    """PumpSwap-vaults: token-konti ejet af poolen (fundet ud fra en nylig transaktion; tjekkes mod prefix)."""
    if len(p["sol_vault"]) > 30:
        return p
    from swaps import _keys
    r = rpc.call("getTransactionsForAddress", [p["pool"], {"transactionDetails": "full", "encoding": "json",
                 "maxSupportedTransactionVersion": 1, "limit": 5, "filters": {"status": "succeeded"}}])
    tx = r["data"][0]
    keys, _ = _keys(tx)
    owned = {b["mint"]: keys[b["accountIndex"]] for b in tx["meta"]["postTokenBalances"] if b.get("owner") == p["pool"]}
    sv, uv = owned["So11111111111111111111111111111111111111112"], owned["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"]
    assert sv.startswith(p["sol_vault"]) and uv.startswith(p["usdc_vault"]), "uventede vaults"
    return dict(p, sol_vault=sv, usdc_vault=uv)


def fetch(db, rpc, now=None, log=print):
    now = int(now or time.time()) - 3600
    t0 = now - DAYS * 86400
    pools = {k: resolve_vaults(rpc, v) for k, v in POOLS.items()}
    for i in range(WINDOWS):
        ws = int(t0 + i * (DAYS * 86400 / WINDOWS))
        if db.execute("SELECT 1 FROM windows WHERE win=?", (i,)).fetchone():
            continue  # allerede hentet (genstart-sikker)
        counts = {}
        for key, p in pools.items():
            n = 0
            # tilstanden lige før vinduet + alle transaktioner i vinduet
            first = rpc.call("getTransactionsForAddress", [p["pool"], {"transactionDetails": "full", "encoding": "json",
                             "maxSupportedTransactionVersion": 1, "limit": 20, "sortOrder": "desc",
                             "filters": {"blockTime": {"lt": ws}, "status": "succeeded"}}]) or {}
            txs = [t for t in (first.get("data") or []) if vault_state(t, p["sol_vault"], p["usdc_vault"], "post")][:1]
            txs += gtfa(rpc, p["pool"], {"transactionDetails": "full", "encoding": "json", "maxSupportedTransactionVersion": 1,
                                         "limit": 1000, "sortOrder": "asc",
                                         "filters": {"blockTime": {"gte": ws, "lt": ws + WINDOW_S}, "status": "succeeded"}})
            for tx in txs:
                st = vault_state(tx, p["sol_vault"], p["usdc_vault"], "post")
                if st:
                    db.execute("INSERT OR IGNORE INTO states VALUES(?,?,?,?,?,?,?,?)",
                               (key, i, tx["slot"], tx.get("transactionIndex", 0), tx.get("blockTime"),
                                tx["transaction"]["signatures"][0], st[0], st[1]))
                    n += 1
            counts[key] = n
        db.execute("INSERT INTO windows VALUES(?,?,?,?,?,?)", (i, ws, ws + WINDOW_S, int(time.time()), counts["A"], counts["B"]))
        db.commit()
        log(f"vindue {i + 1}/{WINDOWS} {time.strftime('%d.%m %H:%M', time.localtime(ws))}: Raydium {counts['A']}, PumpSwap {counts['B']} tilstande")


# ---------- eksperiment ----------
def metrics(decs, seed=7):
    p = [d["pnl"] for d in decs]
    out = {"decisions": len(p), "executed": sum(d["executed"] for d in decs)}
    if not p:
        return out
    eq = peak = dd = 0.0
    for x in p:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    rng = random.Random(seed)
    boots = sorted(statistics.mean(rng.choices(p, k=len(p))) for _ in range(4000))
    out.update({"total": sum(p), "mean": statistics.mean(p), "median": statistics.median(p), "worst": min(p), "best": max(p),
                "max_dd": dd, "ci95": [boots[100], boots[3899]],
                "mean_executed_gross": statistics.mean([d["exec_gross"] for d in decs if d["executed"]]) if out["executed"] else None})
    return out


def run(db_path, out_dir, md_path, log=print):
    db = sqlite3.connect(db_path)
    wins = db.execute("SELECT win, t0, n_a, n_b FROM windows ORDER BY win").fetchall()
    series = {}
    for w, _, _, _ in wins:
        for key in ("A", "B"):
            series[(w, key)] = Series([tuple(r) for r in db.execute(
                "SELECT slot, idx, sol, usdc FROM states WHERE win=? AND pool=?", (w, key))])
    db.close()
    fa, fb = POOLS["A"]["fee"], POOLS["B"]["fee"]
    part = {"train": [w for w in wins if w[0] < 6], "validation": [w for w in wins if 6 <= w[0] < 9], "test": [w for w in wins if w[0] >= 9]}

    def go(ws, k=2, theta=0.0, tx_sol=TX_SOL, guard=True, fee_b=fb):
        decs, obs, runs, slots = [], 0, [], 0
        for w, _, _, _ in ws:
            d, o, r = simulate_window(series[(w, "A")], series[(w, "B")], fa, fee_b, k, theta, tx_sol, guard)
            decs += d
            obs += o
            runs += r
            slots += len(set(series[(w, "A")].slots) | set(series[(w, "B")].slots))
        return decs, obs, runs, slots

    train_by_theta = {th: metrics(go(part["train"], theta=th)[0]) for th in (0.0, 0.10, 1.00)}
    theta = max(train_by_theta, key=lambda th: train_by_theta[th].get("total", -1e9))
    res = {"version": VERSION, "built": int(time.time()), "theta": theta, "train_by_theta": train_by_theta,
           "assumptions": {"capital_usdc": CAPITAL, "tx_sol": TX_SOL, "fees": {"A": fa, "B": fb}, "latency_slots": 2, "guard": True,
                           "measured": ["pool-gebyrer (fra rigtige swaps)", "reserver pr. transaktion"],
                           "estimated": ["tx_cost (base + priority/Jito)", "evt. PumpSwap-protokolgebyr uden for poolen"],
                           "not_modelled": ["andre arbitragører i samme slot før os (øvre grænse)", "fejlede/forsinkede landinger", "Jito-auktion"]},
           "windows": [{"win": w, "start": time.strftime("%Y-%m-%d %H:%M", time.localtime(t0)), "states_A": na, "states_B": nb} for w, t0, na, nb in wins],
           "parts": {}}
    for name, ws in part.items():
        decs, obs, runs, slots = go(ws, theta=theta)
        r = {"slots_with_update": slots, "observed_opportunities": obs,
             "persistence_slots": {"runs": len(runs), "median": statistics.median(runs) if runs else None, "max": max(runs) if runs else None,
                                   "share_1_slot": (sum(1 for x in runs if x == 1) / len(runs)) if runs else None},
             "primary": metrics(decs),
             "no_guard": metrics(go(ws, theta=theta, guard=False)[0]),
             "latency": {k: metrics(go(ws, k=k, theta=theta)[0]).get("total") for k in (1, 2, 5, 10)},
             "high_cost": metrics(go(ws, theta=theta, tx_sol=0.005, fee_b=fb + 0.0005)[0]).get("total"),
             "zero_latency_upper_bound": metrics(go(ws, k=1, theta=theta, tx_sol=0.0)[0]).get("total")}
        res["parts"][name] = r
    t = res["parts"]["test"]["primary"]
    if t.get("decisions", 0) >= 1 and t.get("total", 0) > 0 and t.get("executed", 0) >= 30 and t["ci95"][0] > 0:
        res["verdict"] = "OUT-OF-SAMPLE VALIDATED (øvre grænse; kun grundlag for live paper-observation)"
    elif t.get("total", 0) > 0:
        res["verdict"] = "INCONCLUSIVE"
    else:
        res["verdict"] = "REJECTED"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, VERSION + ".json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    md = report_md(res)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    log(md)
    return res


def usd(x):
    return "–" if x is None else f"{x:+,.2f} USDC"


def report_md(res):
    a = res["assumptions"]
    out = [f"# Resultater: {res['version']}", "",
           f"Bygget {time.strftime('%Y-%m-%d %H:%M', time.localtime(res['built']))} af `research/arb.py` ud fra `research/HYPOTHESES.md` (arb_v1).", "",
           f"- Pools: Raydium AMM v4 (gebyr {a['fees']['A'] * 100:.3f} %, målt) og PumpSwap ({a['fees']['B'] * 100:.3f} %, målt i poolen) for SOL/USDC.",
           f"- Kapital {a['capital_usdc']:.0f} USDC pr. handel, atomisk rundtur, profit-sikring, {a['latency_slots']} slots forsinkelse, "
           f"tx-omkostning {a['tx_sol']} SOL (ESTIMERET). Tærskel valgt på train: {res['theta']} USDC.",
           "- Ikke modelleret (resultatet er en ØVRE grænse): " + "; ".join(a["not_modelled"]) + ".", "",
           "| Vindue | Start | Raydium-tilstande | PumpSwap-tilstande |", "|---|---|---|---|"]
    out += [f"| {w['win'] + 1} | {w['start']} | {w['states_A']} | {w['states_B']} |" for w in res["windows"]]
    out += ["", "| Del | Slots med opdatering | Observerede muligheder (netto > 0) | Persistens median/maks (slots) | Andel kun 1 slot | "
            "Beslutninger | Udført | Netto i alt | Gns. pr. beslutning | 95 % CI | Uden sikring | Forsinkelse 1/2/5/10 slots | Høje omkostninger | 0 forsinkelse, 0 tx-omk. |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res["parts"].items():
        p, ps = r["primary"], r["persistence_slots"]
        ci = p.get("ci95")
        one = "–" if ps["share_1_slot"] is None else "%.0f %%" % (ps["share_1_slot"] * 100)
        out.append(f"| {name} | {r['slots_with_update']} | {r['observed_opportunities']} | {ps['median']}/{ps['max']} | "
                   f"{one} | {p.get('decisions')} | {p.get('executed')} | "
                   f"{usd(p.get('total'))} | {usd(p.get('mean'))} | {('[' + usd(ci[0]) + ', ' + usd(ci[1]) + ']') if ci else '–'} | "
                   f"{usd(r['no_guard'].get('total'))} | {' / '.join(usd(v) for v in r['latency'].values())} | {usd(r['high_cost'])} | {usd(r['zero_latency_upper_bound'])} |")
    out += ["", f"**Dom: {res['verdict']}**", ""]
    return "\n".join(out)


def main():
    from copybot import load_config
    from solana_rpc import RPC
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    dbp = os.path.join(HERE, "data", "research", "arb.db")
    if cmd == "fetch":
        cfg = load_config(os.path.join(HERE, "config.json"))
        if "helius" not in cfg["rpc_url"]:
            raise SystemExit("Kræver Helius (getTransactionsForAddress)")
        fetch(open_db(dbp), RPC(cfg["rpc_url"], 8, log=lambda *x: None))
    else:
        run(dbp, os.path.join(HERE, "data", "research", "results"), os.path.join(HERE, "research", "RESULTS_" + VERSION + ".md"))


if __name__ == "__main__":
    main()
