"""Amendments 35/35a (H27-B): tokenised gold (PAXG, XAUT) against the gold perp, 4 h basis convergence.

  python3 research/tools/m35_gold.py count [--db PATH]   valid snapshots and events only (35 point 14, 35a point 7)
  python3 research/tools/m35_gold.py run   [--db PATH]   the one run; refuses below 28 event days

Written before any b, d or c was computed. The count mode never prints b, d, c or a quantile.
"""
import argparse
import bisect
import datetime as dt
import json
import math
import os
import sqlite3
import statistics as st
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import sessions  # noqa: E402
from lab.edgemonitor import t_cdf  # noqa: E402

HOUR, DAY = 3600, 86400
FIRST = 1793577600                                    # 2026-11-02 00:00 UTC (35 point 6)
LAST = int(dt.datetime(2027, 4, 1, tzinfo=dt.timezone.utc).timestamp())   # deadline 2027-03-31 (35 point 9)
PAIRS = {"A": "PAXGUSDT", "B": "XAUTUSDT"}
GOLD = "XAUUSDT"
LATE_S, MEDIAN_N, MEDIAN_MIN, QUANT_N, LEAD = 600, 24, 20, 100, 4 * HOUR
MIN_DAYS, FLOOR = 28, 0.0046
DB = os.path.join(HERE, "data", "lab", "lab.db")


def _mark(p, sym):
    row = p["rows"].get(sym)
    if not row:
        return None
    v = row[p["columns"].index("markPrice")]
    return v if v and v > 0 else None


def series(snaps, upto):
    """35a point 1: {pair: {h: b_h}} from census_check-style {h: (ts, payload)}, valid hours in [FIRST, upto)."""
    out = {k: {} for k in PAIRS}
    for h, (ts, p) in snaps.items():
        t = p.get("premium_fetched_at") or ts
        if h < FIRST or h >= min(upto, LAST + LEAD) or not 0 <= t - h <= LATE_S or not sessions.opened("commodity", h):
            continue
        g = _mark(p, GOLD)
        for k, sym in PAIRS.items():
            m = _mark(p, sym)
            if g and m:
                out[k][h] = math.log(m) - math.log(g)
    return out


def deviations(b):
    """35a point 2: d_h = b_h - median of the 24 latest valid b before h (at least 20)."""
    hs, d = sorted(b), {}
    for i, h in enumerate(hs):
        prior = hs[max(0, i - MEDIAN_N):i]
        if len(prior) >= MEDIAN_MIN:
            d[h] = b[h] - st.median(b[x] for x in prior)
    return d


def events(b, d):
    """35a points 3-4: hours whose |d| is above the 90 % quantile of |d| over the prior 7 days (>= 100 values) and
    whose h + 4 h is a valid snapshot. Returns all such hours, sorted."""
    hs = sorted(d)
    out = []
    for i, h in enumerate(hs):
        if h >= LAST:
            break
        lo = bisect.bisect_left(hs, h - 7 * DAY)
        window = sorted(abs(d[x]) for x in hs[lo:i])
        if len(window) < QUANT_N:
            continue
        if abs(d[h]) > window[int(0.9 * len(window))] and h + LEAD in b:
            out.append(h)
    return out


def first_per_day(hours):
    out = {}
    for h in hours:
        out.setdefault(h - h % DAY, h)
    return out


def count_snaps(snaps, upto):
    """35 point 14: counts only."""
    b = series(snaps, upto)
    per, days = {}, set()
    for k in PAIRS:
        ev = events(b[k], deviations(b[k]))
        fd = first_per_day(ev)
        days |= set(fd)
        per[k] = {"valid_snapshots": len(b[k]), "events_with_outcome": len(ev), "event_days": len(fd)}
    return {"rule": "amendments 35/35a: counts only, never b, d or c", "pairs": per, "event_days": len(days),
            "days_need": MIN_DAYS}


def sign(x):
    return (x > 0) - (x < 0)


def tstat(xs):
    if len(xs) < 3 or st.stdev(xs) == 0:
        return None, None
    t = st.fmean(xs) / (st.stdev(xs) / math.sqrt(len(xs)))
    return t, 2 * (1 - t_cdf(abs(t), len(xs) - 1))


def judge(days, placebo):
    """35 points 9-12."""
    vals = [v for _, v in sorted(days.items())]
    if len(vals) < MIN_DAYS:
        return {"verdict": "UNTESTABLE", "days": len(vals)}
    t, p = tstat(vals)
    mean = st.fmean(vals)
    half = len(vals) // 2
    h1, h2 = st.fmean(vals[:half]), st.fmean(vals[half:])
    drop = st.fmean(sorted(vals, key=abs)[:-2])
    tp, _ = tstat([v for _, v in sorted(placebo.items())])
    ok = (p is not None and p <= 0.005 and mean - FLOOR > 0 and h1 > 0 and h2 > 0 and drop > 0
          and tp is not None and abs(tp) < 2)
    return {"verdict": "PASS" if ok else "SCREEN_FAIL", "days": len(vals), "mean_c": mean, "t": t, "p": p,
            "halves": [h1, h2], "without_2_largest": drop, "placebo_t": tp, "placebo_days": len(placebo)}


def run_snaps(snaps, upto):
    b = series(snaps, upto)
    days, plac, bench = {}, {}, []
    for k in PAIRS:
        d = deviations(b[k])
        for day, h in first_per_day(events(b[k], d)).items():
            move = b[k][h + LEAD] - b[k][h]
            days.setdefault(day, []).append(-sign(d[h]) * move)
            if h - DAY in d:
                plac.setdefault(day, []).append(-sign(d[h - DAY]) * move)
        bench += [abs(b[k][h + LEAD] - b[k][h]) for h in b[k] if h + LEAD in b[k]]
    out = judge({k: st.fmean(v) for k, v in days.items()}, {k: st.fmean(v) for k, v in plac.items()})
    out["benchmark_mean_abs_4h_move"] = st.fmean(bench) if bench else None
    return out


def main(argv=None):
    import census_check
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("count", "run"))
    ap.add_argument("--db", default=DB)
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    snaps, _, _ = census_check.load(con)
    upto = int(dt.datetime.now(dt.timezone.utc).timestamp())
    c = count_snaps(snaps, upto)
    if a.what == "count" or c["event_days"] < MIN_DAYS:
        out = c if a.what == "count" else {"refused": f"fewer than {MIN_DAYS} event days", **c}
    else:
        out = run_snaps(snaps, upto)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
