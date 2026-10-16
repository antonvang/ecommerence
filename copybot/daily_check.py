"""Daglig status: virker botterne, fanger sniperen alle graduations, er paper-priserne ærlige, og er kriterierne opfyldt?

  python daily_check.py

Kriterier før rigtige penge (aftalt 15.10.2026): positiv efter alle omkostninger over 1-2 uger, mindst 30 handler,
ikke båret af 2-3 heldige handler (stadig positiv uden de 3 bedste), og positiv i begge halvdele af perioden.
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from copybot import load_config  # noqa: E402
from report import trade_stats  # noqa: E402

DATA = os.path.join(HERE, "data")


def kv(db, k):
    r = db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r[0]) if r else None


def verdict(pnls, ts):
    """Kriterierne på en liste af afkast (brøk) med tidspunkter."""
    if len(pnls) < 30:
        return f"for tidligt ({len(pnls)} af mindst 30 handler)"
    st = trade_stats(pnls)
    srt = sorted(pnls)
    mid = statistics.median(ts)
    h1 = [p for p, t in zip(pnls, ts) if t < mid]; h2 = [p for p, t in zip(pnls, ts) if t >= mid]
    checks = [("positiv i alt", st["net"] > 0), ("positiv uden 3 bedste", sum(srt[:-3]) > 0),
              ("positiv i 1. halvdel", sum(h1) > 0), ("positiv i 2. halvdel", sum(h2) > 0)]
    ok = all(c for _, c in checks)
    return ("OPFYLDT" if ok else "IKKE opfyldt") + " · " + ", ".join(f"{n}: {'ja' if c else 'nej'}" for n, c in checks)


def main():
    cfg = load_config(os.path.join(HERE, "config.json"))
    now = time.time()
    out = []
    p = sqlite3.connect(os.path.join(DATA, "paper.db"))
    hb = kv(p, "heartbeat")
    out.append(f"Kopi-bot: {'kører' if hb and now - hb < 120 else 'STOPPET'} (sidst aktiv for {int(now - hb) if hb else '?'} sek siden)")
    rows = p.execute("SELECT closed_ts, pnl_usd, cost_usd FROM positions WHERE book='port' AND closed_ts IS NOT NULL").fetchall()
    out.append(f"  kopi-konto: {len(rows)} lukkede handler, resultat ${sum(r[1] for r in rows):+.2f} · kriterier: "
               + verdict([r[1] / r[2] for r in rows], [r[0] for r in rows]))
    err = kv(p, "last_error")
    if err and now - err[0] < 86400:
        out.append(f"  seneste fejl: {err[1]}")

    sp = os.path.join(DATA, "sniper.db")
    if os.path.exists(sp):
        s = sqlite3.connect(sp)
        s.row_factory = sqlite3.Row
        shb = kv(s, "sniper_heartbeat")
        out.append(f"Sniper: {'kører' if shb and now - shb < 120 else 'STOPPET'} (sidst aktiv for {int(now - shb) if shb else '?'} sek siden)")
        sn = s.execute("SELECT * FROM snipes").fetchall()
        lat = [r["seen_ts"] - r["grad_ts"] for r in sn if r["grad_ts"] and r["rule"] == "60s"]
        out.append(f"  {len({r['mint'] for r in sn})} graduations i alt, reaktionstid median {statistics.median(lat) if lat else '-'} sek")
        for rule in ("60s", "5min", "tp50_sl30"):
            rr = [r for r in sn if r["rule"] == rule and r["closed_ts"]]
            pn = [r["pnl_usd"] / r["cost_usd"] for r in rr]
            out.append(f"  {rule:<10} {len(rr):>5} handler · ${sum(r['pnl_usd'] for r in rr):+9.2f} · "
                       f"gns. {statistics.mean(pn) * 100 if pn else 0:+.1f}% · kriterier: " + verdict(pn, [r["closed_ts"] for r in rr]))
        coverage(cfg, s, out, now)
    print("\n".join(out))


def coverage(cfg, s, out, now):
    """Fanger sniperen alle graduations? Kræver Helius (getTransactionsForAddress)."""
    if "helius" not in cfg["rpc_url"]:
        out.append("  dækning: kan ikke måles uden Helius-nøgle")
        return
    from solana_rpc import RPC
    from sniper import MIGRATION, parse_migration
    rpc = RPC(cfg["rpc_url"], 8, log=lambda *a: None)
    t0, t1 = int(now - 6 * 3600), int(now - 120)
    real, token = set(), None
    for _ in range(5):
        opts = {"transactionDetails": "full", "encoding": "jsonParsed", "maxSupportedTransactionVersion": 1, "limit": 1000,
                "filters": {"blockTime": {"gte": t0, "lt": t1}, "status": "succeeded"}}
        if token:
            opts["paginationToken"] = token
        r = rpc.call("getTransactionsForAddress", [MIGRATION, opts]) or {}
        for tx in r.get("data") or []:
            g = parse_migration(tx)
            if g:
                real.add(g["mint"])
        token = r.get("paginationToken")
        if not token:
            break
    ours = {r[0] for r in s.execute("SELECT DISTINCT mint FROM snipes WHERE grad_ts>=? AND grad_ts<?", (t0, t1))}
    pct = len(ours & real) / len(real) * 100 if real else 0
    out.append(f"  dækning seneste 6 timer: {len(ours & real)} af {len(real)} graduations fanget ({pct:.0f} %)"
               + ("" if pct >= 90 else "  <-- FOR LAV, noget er galt"))


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    main()
