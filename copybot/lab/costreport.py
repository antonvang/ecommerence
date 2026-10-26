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
import math
import random
import sqlite3
import statistics
import sys
import time

from lab import m21iscreen, moves

DAY = 86400
DRAWS, SEED, MOVE_Z = 2000, 7, 2.0
MIN_DAYS, MIN_OBS, MIN_MOVE, MIN_WEEKENDS = 7, 100, 10, 2      # 21l point 1 and 21n point 2, fixed before data
FEE = {"crypto": 0.0005, "tradfi": 0.0004}                    # taker per side (2026 standard; TradFi promo, 21g)
NOTES = ["book_rt = (buy VWAP - sell VWAP) / mid for 5 000 USD each way: spread and slippage, no fees",
         "total round trip = book_rt + 2 x taker fee; spread is shown separately and never added to book_rt",
         "funding is not an order cost (it is netted in outcomes where a position is held)",
         "5 000 USD each way = the size of the 21i RT_est model",
         "sampled at HH:02 after a closed hour (when the scanner would trade), not inside a move",
         "missing book = too thin for 5 000 USD: median_upper_missing_as_inf is the upper bound",
         "hours on one UTC day are not independent: the median interval bootstraps days"]


FINAL_AFTER_S = 7 * DAY
FINAL_REQUIRES = "span first-last observation >= 7 x 24 h and >= 2 weekends with TradFi off-hours observations (21k)"


def d_class(rs):
    return rs[0]["class"] if rs else "crypto"


def rows(q, dupes=None):
    """[{market, class, ts, open_s, rt, spread, off, z, flagged, v24}] - one per market hour (amendment 21r): the
    earliest scan of each (market, open_s); later rescans of the same hour (restarts, deploys) are counted in `dupes`."""
    z = {}
    for r in q("SELECT ts, instrument, payload FROM observations WHERE detector='abnormal_move/1' AND metric='z_1h'"):
        p = json.loads(r[2])
        z[(r[0], r[1])] = p
    flags = {(r[0], r[1]) for r in q("SELECT ts, instrument FROM observations WHERE detector='abnormal_move/1' AND "
                                     "flagged=1")}
    out, seen = [], set()
    for ts, sym, val, raw in q("SELECT ts, instrument, value, payload FROM observations WHERE detector='abnormal_move/1' "
                               "AND metric='book_rt' ORDER BY ts, id"):
        p, zp = json.loads(raw), z.get((ts, sym)) or {}
        hour = p.get("open_s") or zp.get("open_s")
        if hour is not None and (sym, hour) in seen:
            if dupes is not None:
                dupes.append((sym, hour, ts))
            continue
        seen.add((sym, hour))
        vr, q1 = zp.get("volume_ratio"), zp.get("quote_volume_1h")
        out.append({"market": sym, "class": "crypto" if p.get("class") == "crypto" else "tradfi", "ts": ts,
                    "open_s": hour, "rt": val, "spread": p.get("spread"), "off": bool(p.get("off_hours")),
                    "z": zp.get("z_1h"), "flagged": (ts, sym) in flags, "v24": 24 * q1 / vr if vr and q1 else None})
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
    censored = sorted(r["rt"] if r["rt"] is not None else math.inf for r in rs)      # 21l: a thin book is expensive
    bp = (lambda x: None if x is None else (math.inf if x == math.inf else round(x * 1e4, 3)))   # noqa: E731
    out = {"n": len(rs), "missing_book": len(rs) - len(vals), "days": len({r["ts"] // DAY for r in rs}),
           "median": med, "median_ci95_day_bootstrap": ci, "q25": q[0] if q else None, "q75": q[2] if q else None,
           "max": vals[-1] if vals else None,
           "median_upper_missing_as_inf": statistics.median(censored) if censored else None}
    out["bp"] = {k: bp(out[k]) for k in ("median", "q25", "q75", "max", "median_upper_missing_as_inf")}
    out["bp"]["median_ci95"] = [bp(x) for x in ci] if ci else None
    return out


def sufficient(d, moved, weekends=MIN_WEEKENDS):
    """21l point 1 and 21n point 2: >= 7 days, >= 100 hourly observations, >= 10 move hours and >= 2 weekends of
    this market, else 'too few data'."""
    return d["days"] >= MIN_DAYS and d["n"] >= MIN_OBS and moved["n"] >= MIN_MOVE and weekends >= MIN_WEEKENDS


def weekends_of(rs):
    return len({r["ts"] // (7 * DAY) for r in rs if time.gmtime(r["ts"]).tm_wday >= 5})


def b_and_c(mr, moved):
    """21n point 2: amendment 21i's requirement (B) and option C (21l point 2) side by side at the market's current
    V, with fee 0.040 % (the explore0 fee both rules use) and a day-bootstrap interval of C's q95."""
    fee = m21iscreen.FEE
    vs = [r["v24"] for r in mr if r["v24"]]
    v = statistics.median(vs) if vs else None
    b = max(m21iscreen.FLOOR, 2 * (2 * fee + m21iscreen.rt_est(v))) if v else None
    vals = sorted(r["rt"] for r in moved if r["rt"] is not None)
    if len(vals) < MIN_MOVE:
        return {"v24": v, "B": b, "C": None, "liquid": v is not None and v >= 1e8}
    q95 = statistics.quantiles(vals, n=20)[-1]
    days = collections.defaultdict(list)
    for r in moved:
        if r["rt"] is not None:
            days[r["ts"] // DAY].append(r["rt"])
    keys, rnd, qs = sorted(days), random.Random(SEED), []
    for _ in range(DRAWS if len(keys) >= 2 else 0):
        pick = sorted(x for _ in keys for x in days[rnd.choice(keys)])
        qs.append(statistics.quantiles(pick, n=20)[-1] if len(pick) >= 2 else pick[0])
    qs.sort()
    return {"v24": v, "liquid": v is not None and v >= 1e8, "B": b, "q95": q95,
            "q95_ci95_day_bootstrap": [qs[int(0.025 * len(qs))], qs[int(0.975 * len(qs)) - 1]] if qs else None,
            "C": max(4 * fee, 2 * (2 * fee + q95)),
            "note": "C is never activated automatically (21n): the user decides per market"}


def report(q, now=None):
    now = now or time.time()
    dropped = []
    rs = rows(q, dropped)
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
        d, dm = describe(mr), describe(moved)
        markets[sym] = {**d, "model_rt_median": statistics.median(model) if model else None,
                        "measured_over_model": (d["median"] / statistics.median(model))
                        if model and d["median"] is not None and statistics.median(model) > 0 else None,
                        "move_hours": dm, "other_hours": describe(calm),
                        "weekends": weekends_of(mr),
                        "conclusion": "enough data" if sufficient(d, dm, weekends_of(mr)) else "too few data",
                        "B_vs_C": b_and_c(mr, moved) if sufficient(d, dm, weekends_of(mr)) else None,
                        "total_round_trip_bp_with_fees": None if d["median"] is None else
                        round((d["median"] + 2 * FEE[d_class(mr)]) * 1e4, 3)}
    span = (max(r["ts"] for r in rs) - min(r["ts"] for r in rs)) if rs else 0
    weekends = len({r["ts"] // (7 * DAY) for r in rs if r["off"] and r["class"] == "tradfi"})
    status = "FINAL" if span >= FINAL_AFTER_S and weekends >= 2 else "PRELIMINARY"
    table = {}
    for sym, m in markets.items():                              # 21o point 2: the per-market decision table
        req = {"days >= 7": m["days"] >= MIN_DAYS, "observations >= 100": m["n"] >= MIN_OBS,
               "move hours >= 10": m["move_hours"]["n"] >= MIN_MOVE, "weekends >= 2": m["weekends"] >= MIN_WEEKENDS}
        fee = FEE["crypto" if moves.WATCH[sym][0] == "crypto" else "tradfi"]
        ci = m["median_ci95_day_bootstrap"]
        table[sym] = {"requirements": req, "observations": m["n"], "day_clusters": m["days"],
                      "total_rt_bp_median": m["total_round_trip_bp_with_fees"],
                      "total_rt_bp_ci95": [round((x + 2 * fee) * 1e4, 3) for x in ci] if ci else None,
                      "missing_or_censored": m["missing_book"],
                      "B": (m["B_vs_C"] or {}).get("B"), "C": (m["B_vs_C"] or {}).get("C"),
                      "C_minus_B": None if not m["B_vs_C"] or None in (m["B_vs_C"].get("B"), m["B_vs_C"].get("C"))
                      else m["B_vs_C"]["C"] - m["B_vs_C"]["B"],
                      "observed_inputs": ["book_rt", "spread", "volume_ratio", "quote_volume_1h"],
                      "assumed_inputs": ["taker fee rate", "RT_est volume relation (2026-10-24 snapshot)",
                                         "transfer of 2026 costs to 2020-21 (explore0)"],
                      "recommendation": "can be put to the user" if all(req.values()) else "NO_DECISION",
                      "report_status": status,                  # 21o precision 2026-10-26: display only
                      "report_final_requires": FINAL_REQUIRES}
    return {"rule": "research/PROTOCOL_V3.md amendments 21k, 21l, 21n and 21r", "generated": now, "scans": len({r["ts"] for r in rs}),
            "rescans_dropped": len(dropped),
            "span_hours": span / 3600, "status": status,
            "label": "OBSERVED book cost for 5 000 USD (fees excluded); the model column is the 21i ESTIMATE",
            "notes": NOTES,
            "groups": {k: describe(v) for k, v in sorted(groups.items())}, "markets": markets,
            "decision_table": table}


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
