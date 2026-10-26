"""Every amendment-25 liquidity-gate decision, read-only and never truncated (research/studies/AFVISNINGER_2026-10-26.md).

Run before reporting "not observed": it lists each lane.skipped / lane.started whose reason or trigger carries the gate,
with the full reason, the per-leg round trip, the curve status and the limit, and counts every rule that stopped a new
lane in the same period (plain substring matches on the full reason, no truncation).

  python3 research/tools/gate_decisions.py [--db data/lab/lab.db] [--since EPOCH]
"""
import argparse
import collections
import json
import sqlite3
import sys
import time

GATE_DEPLOY = 1792961580                # amendment 25 in production (2026-10-25 20:52:25 UTC, system.running)
RULES = (("likviditetsgate (25)", "25 likviditetsgate"), ("intet spotpar", "19 intet spotpar"),
         ("too thin for the account", "12g bogen for tynd"), ("do not cover the round-trip", "12g funding dækker ikke"),
         ("funding not persistent", "funding ikke vedvarende"), ("unsynchronised", "12h usynkrone bøger"),
         ("afnotering", "16e afnotering"))


def rule_of(reason):
    for needle, name in RULES:
        if needle in reason:
            return name
    return "andet"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/lab/lab.db")
    ap.add_argument("--since", type=float, default=GATE_DEPLOY)
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rows = con.execute("SELECT id, ts, kind, payload FROM events WHERE kind IN ('lane.skipped', 'lane.started') "
                       "AND ts >= ? ORDER BY ts, id", (a.since,)).fetchall()
    counts, decisions = collections.Counter(), []
    for i, ts, kind, raw in rows:
        p = json.loads(raw)
        reason = str(p.get("reason") or "")
        counts["lane.started" if kind == "lane.started" else rule_of(reason)] += 1
        gate = (p.get("trigger") or {}).get("liquidity")
        if gate or "likviditetsgate" in reason:
            decisions.append({"id": i, "at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts)), "kind": kind,
                              "coin": p.get("coin"), "function": p.get("function"), "reason": reason,
                              "gate": {k: (gate or {}).get(k) for k in ("round_trip", "limit", "reason", "legs")}})
    out = {"since": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(a.since)), "attempts": len(rows),
           "by_rule": dict(counts.most_common()), "gate_decisions": decisions}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
