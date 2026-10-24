"""PROTOCOL_V3 amendment 21k point 1: the observed execution-cost report (R1). Descriptive, never a decision.

Reads the registry read-only: the scanner's hourly `book_rt` and `spread` (amendment 21h point 3) and the same scan's
`z_1h` observation per market. Groups by class x session (off_hours) and by market: n, missing books, median,
quartiles, max and a 95 % bootstrap interval of the median over UTC-day clusters (2 000 draws, seed 7). Compares with the
21i model RT_est(V), V = 24 * quote_volume_1h / volume_ratio, and splits by |z_1h| >= 2 or a flag. PRELIMINARY until
7 days and 2 weekends of data.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sqlite3
import statistics
import sys
import time

from lab import m21iscreen, moves

DAY = 86400
DRAWS, SEED, MOVE_Z = 2000, 7, 2.0
FINAL_AFTER_S = 7 * DAY


def rows(q):
    """[{market, class, ts, rt, spread, off, z, flagged, v24}] - one per market per scan."""
    z = {}
    for r in q("SELECT ts, instrument, payload FROM observations WHERE detector='abnormal_move/1' AND metric='z_1h'"):
        p = json.loads(r[2])
        z[(r[0], r[1])] = p
    flags = {(r[0], r[1]) for r in q("SELECT ts, instrument FROM observations WHERE detector='abnormal_move/1' AND "
                                     "flagged=1")}
    out = []
    for ts, sym, val, raw in q("SELECT ts, instrument, value, payload FROM observations WHERE detector='abnormal_move/1' "
                               "AND metric='book_rt' ORDER BY ts"):
        p, zp = json.loads(raw), z.get((ts, sym)) or {}
        vr, q1 = zp.get("volume_ratio"), zp.get("quote_volume_1h")
        out.append({"market": sym, "class": "crypto" if p.get("class") == "crypto" else "tradfi", "ts": ts, "rt": val,
                    "spread": p.get("spread"), "off": bool(p.get("off_hours")), "z": zp.get("z_1h"),
                    "flagged": (ts, sym) in flags, "v24": 24 * q1 / vr if vr and q1 else None})
    return out


def med_ci(rs):
    """Median of rt and a 95 % bootstrap interval resampling UTC days."""
    vals = [r["rt"] for r in rs if r["rt"] is not None]
    if not vals:
        return None, None
    days = collections.defaultdict(list)
    for r in rs:
        if r["rt"] is not None:
            days[r["ts"] // DAY].append(r["rt"])
    keys, rnd, meds = sorted(days), random.Random(SEED), []
    if len(keys) < 2:
        return statistics.median(vals), None
    for _ in range(DRAWS):
        pick = [v for _ in keys for v in days[rnd.choice(keys)]]
        meds.append(statistics.median(pick))
    meds.sort()
    return statistics.median(vals), [meds[int(0.025 * DRAWS)], meds[int(0.975 * DRAWS) - 1]]


def describe(rs):
    vals = sorted(r["rt"] for r in rs if r["rt"] is not None)
    med, ci = med_ci(rs)
    q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else None
    return {"n": len(rs), "missing_book": sum(1 for r in rs if r["rt"] is None), "days": len({r["ts"] // DAY for r in rs}),
            "median": med, "median_ci95_day_bootstrap": ci, "q25": q[0] if q else None, "q75": q[2] if q else None,
            "max": vals[-1] if vals else None}


def report(q, now=None):
    now = now or time.time()
    rs = rows(q)
    groups = collections.defaultdict(list)
    for r in rs:
        groups[f"{r['class']}|{'off_hours' if r['off'] else 'regular'}"].append(r)
    markets = {}
    for sym in moves.WATCH:
        mr = [r for r in rs if r["market"] == sym]
        if not mr:
            continue
        model = [m21iscreen.rt_est(r["v24"]) for r in mr if r["v24"]]
        moved = [r for r in mr if r["flagged"] or (r["z"] is not None and abs(r["z"]) >= MOVE_Z)]
        calm = [r for r in mr if r not in moved]
        markets[sym] = {**describe(mr), "model_rt_median": statistics.median(model) if model else None,
                        "measured_over_model": (describe(mr)["median"] / statistics.median(model))
                        if model and describe(mr)["median"] is not None and statistics.median(model) > 0 else None,
                        "move_hours": describe(moved), "other_hours": describe(calm)}
    span = (max(r["ts"] for r in rs) - min(r["ts"] for r in rs)) if rs else 0
    weekends = len({r["ts"] // (7 * DAY) for r in rs if r["off"] and r["class"] == "tradfi"})
    return {"rule": "research/PROTOCOL_V3.md amendment 21k point 1", "generated": now, "scans": len({r["ts"] for r in rs}),
            "span_hours": span / 3600, "status": "FINAL" if span >= FINAL_AFTER_S and weekends >= 2 else "PRELIMINARY",
            "label": "OBSERVED book cost for 5 000 USD (fees excluded); the model column is the 21i ESTIMATE",
            "groups": {k: describe(v) for k, v in sorted(groups.items())}, "markets": markets}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/lab/lab.db")
    ap.add_argument("--out", help="write <out>.json")
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rep = report(lambda sql, *args: con.execute(sql, args).fetchall())
    text = json.dumps(rep, indent=1, sort_keys=True)
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
