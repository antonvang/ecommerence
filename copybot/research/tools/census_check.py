"""Amendments 28/28a: census data quality and readiness, read-only. Counts only - never an outcome y (28a point 7).

Per UTC hour since the first snapshot: present, duplicate, missing; per snapshot the symbols, COIN perps, null share per
column, the lag of Binance's premium time and of the row behind the hour, ticker errors; error rows. Readiness: days
covered, and the number of C1 events and C2/C3 days the locked rules could use so far (definitions as 28a).

  python3 research/tools/census_check.py [--db data/lab/lab.db] [--now EPOCH]
"""
import argparse
import collections
import json
import math
import sqlite3
import statistics
import sys
import time

DET, HOUR, DAY = "census/1", 3600, 86400
LEADS = ("SPYUSDT", "QQQUSDT", "XAUUSDT")


def load(con):
    snaps, errors = {}, []
    dup = collections.Counter()
    for ts, metric, payload in con.execute("SELECT ts, metric, payload FROM observations WHERE detector=? ORDER BY id",
                                           (DET,)):
        if metric == "error":
            errors.append(ts)
            continue
        h = ts - ts % HOUR
        dup[h] += 1
        snaps.setdefault(h, (ts, json.loads(payload)))                 # the first row of an hour counts
    return snaps, {h: n for h, n in dup.items() if n > 1}, errors


def mark(p, sym):
    row = p["rows"].get(sym)
    return None if not row else row[p["columns"].index("markPrice")]


def ret(snaps, sym, h):
    a, b = snaps.get(h - HOUR), snaps.get(h)
    pa, pb = (mark(a[1], sym) if a else None), (mark(b[1], sym) if b else None)
    return math.log(pb / pa) if pa and pb and pa > 0 and pb > 0 else None


def readiness(snaps):
    """28a point 7: counts only. C1 events (|z| >= 2.5 with >= 120 of 168 prior returns), C2 days with |R| >= 2 %, C3
    usable day pairs (both days >= 22 BTC hourly returns)."""
    hours = sorted(snaps)
    c1 = 0
    for h in hours:
        for lead in LEADS:
            r = ret(snaps, lead, h)
            prior = [x for x in (ret(snaps, lead, h - k * HOUR) for k in range(1, 169)) if x is not None]
            if r is None or len(prior) < 120 or statistics.pstdev(prior) == 0:
                continue
            if abs(r / statistics.stdev(prior)) >= 2.5:
                c1 += 1
                break
    days = sorted({h - h % DAY for h in hours})
    c2 = 0
    for d in days:
        a, b = snaps.get(d - DAY), snaps.get(d)
        pa, pb = (mark(a[1], "BTCUSDT") if a else None), (mark(b[1], "BTCUSDT") if b else None)
        if pa and pb and abs(math.log(pb / pa)) >= 0.02:
            c2 += 1
    full = {d for d in days if sum(1 for k in range(24) if ret(snaps, "BTCUSDT", d + k * HOUR) is not None) >= 22}
    c3 = sum(1 for d in full if d + DAY in full)
    return {"c1_events": c1, "c1_clusters_need": 15, "c2_candidate_days": c2, "c2_clusters_need": 15,
            "c3_day_pairs": c3, "c3_need": 28, "note": "antal kun; intet udfald beregnet (28a punkt 7)"}


def check(con, now):
    snaps, dups, errors = load(con)
    if not snaps:
        return {"hours": 0, "note": "ingen census-rækker endnu"}
    first = min(snaps)
    expected = list(range(first, int(now) - int(now) % HOUR + 1, HOUR))
    missing = [h for h in expected if h not in snaps]
    lags, behind, nulls, sizes, coin, terr = [], [], collections.Counter(), [], [], 0
    cells = 0
    for h, (ts, p) in snaps.items():
        behind.append(ts - h)
        if p.get("premium_time_ms"):
            lags.append(ts - p["premium_time_ms"] / 1000)
        sizes.append(len(p["rows"]))
        coin.append(len(p.get("coin_perps") or []))
        terr += bool(p.get("ticker_error"))
        for row in p["rows"].values():
            for c, v in zip(p["columns"], row):
                nulls[c] += v is None
            cells += 1
    days = (max(snaps) - first) / DAY
    return {"first": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(first)), "days": round(days, 2),
            "hours_expected": len(expected), "hours_present": len(snaps), "hours_missing": len(missing),
            "missing_first": [time.strftime("%m-%d %H:%M", time.gmtime(h)) for h in missing[:10]],
            "duplicate_hours": len(dups), "error_rows": len(errors), "ticker_errors": terr,
            "symbols_min_median": [min(sizes), int(statistics.median(sizes))],
            "coin_perps_min_median": [min(coin), int(statistics.median(coin))],
            "row_behind_hour_s_max": max(behind), "premium_time_lag_s_median": round(statistics.median(lags), 1)
            if lags else None, "null_share": {c: round(n / cells, 4) for c, n in nulls.items()},
            "readiness": readiness(snaps)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/lab/lab.db")
    ap.add_argument("--now", type=float)
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    print(json.dumps(check(con, a.now or time.time()), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
