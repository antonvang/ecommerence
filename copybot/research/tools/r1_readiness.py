"""R1 readiness, read-only and reproducible (research/studies/R1_KLARHED_2026-10-26.md).

Per R1 market: the status of the four locked requirements (amendments 21l point 1 and 21n point 2) exactly as
lab/costreport.py computes them, the time each met requirement was first met (from the data) and, for unmet ones, the
earliest time it can be met if every hourly scan at HH:02 UTC happens (an ESTIMATE). Every count is checked against an
independent SQL count. Costs are kept apart: observed (book round trip and spread at 5 000 USD), assumed (taker fee
rates), modelled (amendment 21i RT_est) and not order costs (basis, funding). Nothing is written to the registry;
no rule, threshold or option C changes.

  python3 research/tools/r1_readiness.py [--db data/lab/lab.db] [--now EPOCH] [--json]
"""
import argparse
import json
import os
import sqlite3
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lab import costreport, m21iscreen, moves  # noqa: E402

DAY, HOUR, WEEK = 86400, 3600, 7 * 86400
SCAN_OFFSET = 122                     # the hourly scan runs at about HH:02 UTC


def utc(t):
    return None if t is None else time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t))


def next_scan(t):
    """The first HH:02 scan after t."""
    h = t - t % HOUR + SCAN_OFFSET
    return h if h > t else h + HOUR


def is_weekend(t):
    return time.gmtime(t).tm_wday >= 5


def requirement_times(mr, moved):
    """When each requirement was first met in the data (None if not yet), in costreport's own terms."""
    ts = sorted(r["ts"] for r in mr)
    out = {"observations >= 100": ts[costreport.MIN_OBS - 1] if len(ts) >= costreport.MIN_OBS else None}
    days, weeks, at_day, at_week = set(), set(), None, None
    for t in ts:
        days.add(t // DAY)
        if at_day is None and len(days) >= costreport.MIN_DAYS:
            at_day = t
        if is_weekend(t):
            weeks.add(t // WEEK)
            if at_week is None and len(weeks) >= costreport.MIN_WEEKENDS:
                at_week = t
    mt = sorted(r["ts"] for r in moved)
    out.update({"days >= 7": at_day, "weekends >= 2": at_week,
                "move hours >= 10": mt[costreport.MIN_MOVE - 1] if len(mt) >= costreport.MIN_MOVE else None})
    return out


def estimates(mr, moved, now):
    """Earliest time an unmet requirement can be met if every hourly scan happens from now on. Move hours cannot be
    forecast: the 'naive' value assumes the same rate as so far and is a HYPOTHESIS, never a date."""
    ts = sorted(r["ts"] for r in mr)
    first, n = ts[0], len(ts)
    t = next_scan(now)
    obs = t + (costreport.MIN_OBS - n - 1) * HOUR
    days = {x // DAY for x in ts}
    d, day_at = max(days), None
    while len(days) < costreport.MIN_DAYS:
        d += 1
        days.add(d)
        day_at = max(d * DAY + SCAN_OFFSET, t)
    weeks = {x // WEEK for x in ts if is_weekend(x)}
    week_at, w = None, t
    while len(weeks) < costreport.MIN_WEEKENDS:
        while not is_weekend(w):
            w += HOUR
        weeks.add(w // WEEK)
        week_at = w
        w += WEEK
    rate = len(moved) / max(1, n)
    naive = None if rate == 0 else now + (costreport.MIN_MOVE - len(moved)) / rate * HOUR
    return {"observations >= 100": obs, "days >= 7": day_at, "weekends >= 2": week_at,
            "move hours >= 10 (naive, hypothesis)": naive, "7 x 24 h after the first observation (21k)": first + WEEK}


def raw_counts(con, sym):
    """Independent SQL counts: one row per (market, open_s) from the earliest book_rt scan of the hour."""
    rows = con.execute(
        "WITH b AS (SELECT ts, json_extract(payload, '$.open_s') AS h, value FROM observations "
        "WHERE detector='abnormal_move/1' AND metric='book_rt' AND instrument=?), "
        "f AS (SELECT h, MIN(ts) AS ts FROM b GROUP BY h) "
        "SELECT f.ts, (SELECT value FROM b WHERE b.ts=f.ts AND b.h=f.h LIMIT 1), "
        "(SELECT json_extract(payload, '$.z_1h') FROM observations WHERE detector='abnormal_move/1' AND metric='z_1h' "
        " AND instrument=? AND ts=f.ts LIMIT 1), "
        "(SELECT COUNT(*) FROM observations WHERE detector='abnormal_move/1' AND flagged=1 AND instrument=? "
        " AND ts=f.ts) FROM f", (sym, sym, sym)).fetchall()
    moved = [r for r in rows if r[3] or (r[2] is not None and abs(r[2]) >= costreport.MOVE_Z)]
    return {"observations": len(rows), "missing_book": sum(1 for r in rows if r[1] is None),
            "utc_days": len({r[0] // DAY for r in rows}),
            "weekends": len({r[0] // WEEK for r in rows if is_weekend(r[0])}), "move_hours": len(moved)}


def costs(con, mr, sym):
    """Observed, assumed, modelled and non-order quantities in basis points, never added across categories except
    total = book round trip + 2 x taker fee (costreport's own definition)."""
    rt = [r["rt"] for r in mr if r["rt"] is not None]
    sp = [r["spread"] for r in mr if r["spread"] is not None and r["rt"] is not None]
    slip = [r["rt"] - r["spread"] for r in mr if r["rt"] is not None and r["spread"] is not None]
    fee = costreport.FEE["crypto" if moves.WATCH[sym][0] == "crypto" else "tradfi"]
    model = [m21iscreen.rt_est(r["v24"]) for r in mr if r["v24"]]
    basis, funding = [], []
    for (p,) in con.execute("SELECT payload FROM observations WHERE detector='abnormal_move/1' AND metric='z_1h' "
                            "AND instrument=?", (sym,)):
        p = json.loads(p)
        if p.get("mark") and p.get("index"):
            basis.append(p["mark"] / p["index"] - 1)
        if p.get("funding_rate") is not None:
            funding.append(p["funding_rate"])
    bp = lambda x: None if x is None else round(x * 1e4, 3)                    # noqa: E731
    med = lambda v: statistics.median(v) if v else None                         # noqa: E731
    days = {}
    for r in mr:
        days.setdefault(time.strftime("%Y-%m-%d", time.gmtime(r["ts"])), []).append(r["rt"])
    by_day = {d: {"hours": len(v), "missing": sum(1 for x in v if x is None),
                  "median_bp": bp(med([x for x in v if x is not None]))} for d, v in sorted(days.items())}
    split = {k: [r["rt"] for r in mr if r["rt"] is not None and is_weekend(r["ts"]) == w]
             for k, w in (("weekend", True), ("weekday", False))}
    return {"observed": {"book_round_trip_bp_median": bp(med(rt)), "spread_bp_median": bp(med(sp)),
                         "by_utc_day": by_day,
                         "weekend_vs_weekday_median_bp": {k: {"hours": len(v), "median_bp": bp(med(v))}
                                                          for k, v in split.items()},
                         "slippage_beyond_spread_bp_median": bp(med(slip)),
                         "slippage_beyond_spread_bp_max": bp(max(slip)) if slip else None,
                         "hours_where_5000_usd_fit_inside_the_spread": sum(1 for s in slip if s <= 1e-12),
                         "hours": len(rt)},
            "assumed": {"taker_fee_bp_per_side": bp(fee),
                        "total_round_trip_bp_median": bp(med(rt) + 2 * fee) if rt else None},
            "modelled": {"rt_est_21i_bp_median": bp(med(model))},
            "not_order_costs": {"basis_mark_vs_index_bp_median": bp(med(basis)),
                                "basis_abs_bp_max": bp(max(abs(b) for b in basis)) if basis else None,
                                "funding_rate_bp_median_per_settlement": bp(med(funding))},
            "unknown": ["cost inside a move (the scan measures at HH:02 after a closed hour)",
                        "market impact beyond the visible book (refill, hidden size, latency)",
                        "depth and per-side VWAP at the hourly scans (not stored; only the capacity curve has them)"]}


def capacity(con, sym):
    """Every capacity-curve snapshot at 5 000 USD for the market: depth, levels, per-side VWAP cost, spread."""
    out = []
    for ts, p in con.execute("SELECT ts, payload FROM observations WHERE detector='capacity/1' AND metric='rt_5000' "
                             "AND instrument=? ORDER BY ts", (sym,)):
        p = json.loads(p)
        mid = p.get("mid")
        out.append({"at": utc(ts), "censored": p.get("censored"), "fits_20_levels": p.get("fits_20_levels"),
                    "levels_read": p.get("levels"), "depth_bid_usd": p.get("depth_bid_usd"),
                    "depth_ask_usd": p.get("depth_ask_usd"),
                    "buy_vwap_minus_mid_bp": round((p["buy_vwap"] / mid - 1) * 1e4, 3) if mid and p.get("buy_vwap") else None,
                    "mid_minus_sell_vwap_bp": round((1 - p["sell_vwap"] / mid) * 1e4, 3) if mid and p.get("sell_vwap") else None,
                    "round_trip_bp": round(p["round_trip"] * 1e4, 3) if p.get("round_trip") is not None else None,
                    "spread_bp": round(p["spread"] * 1e4, 3) if p.get("spread") is not None else None})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/lab/lab.db")
    ap.add_argument("--now", type=float, help="the moment the estimates start from (default: now)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    now = a.now or time.time()
    q = lambda sql, *args: con.execute(sql, args).fetchall()                     # noqa: E731
    rep = costreport.report(q, now)
    rs = costreport.rows(q)
    out, mismatches = {}, []
    for sym in moves.WATCH:
        mr = [r for r in rs if r["market"] == sym]
        if not mr:
            continue
        moved = [r for r in mr if r["flagged"] or (r["z"] is not None and abs(r["z"]) >= costreport.MOVE_Z)]
        table = rep["decision_table"][sym]
        m = rep["markets"][sym]
        mine = {"observations": len(mr), "missing_book": sum(1 for r in mr if r["rt"] is None),
                "utc_days": m["days"], "weekends": m["weekends"], "move_hours": m["move_hours"]["n"]}
        raw = raw_counts(con, sym)
        if mine != raw:
            mismatches.append({"market": sym, "costreport": mine, "raw_sql": raw})
        met = requirement_times(mr, moved)
        est = estimates(mr, moved, now)
        req = {}
        for k, ok in table["requirements"].items():
            req[k] = {"met": ok, "verified_at": utc(met[k]) if ok else None,
                      "estimate_earliest": None if ok else utc(est.get(k) or est.get(k + " (naive, hypothesis)"))}
            if not ok and k == "move hours >= 10":
                req[k]["estimate_earliest"] = None
                req[k]["naive_rate_projection_hypothesis"] = utc(est["move hours >= 10 (naive, hypothesis)"])
        unmet_known = [est[k] for k, v in table["requirements"].items() if not v and k != "move hours >= 10"]
        move_ok = table["requirements"]["move hours >= 10"]
        earliest = None
        if move_ok:
            earliest = max([met[k] for k, v in table["requirements"].items() if v] + unmet_known)
        out[sym] = {"recommendation": table["recommendation"], "counts": mine, "requirements": req,
                    "earliest_code_reading": utc(earliest) if move_ok else "unknown (move hours cannot be forecast)",
                    "earliest_strict_7x24h": utc(max(earliest, est["7 x 24 h after the first observation (21k)"]))
                    if move_ok else "unknown (move hours cannot be forecast)",
                    "first_observation": utc(min(r["ts"] for r in mr)), "last_observation": utc(max(r["ts"] for r in mr)),
                    "costs": costs(con, mr, sym), "capacity_curve_5000": capacity(con, sym)}
    res = {"generated": utc(now), "timezone": "UTC everywhere", "db": os.path.abspath(a.db),
           "costreport_status": rep["status"], "rescans_dropped": rep["rescans_dropped"],
           "independent_check": "OK: costreport counts equal raw SQL counts for every market" if not mismatches
           else {"MISMATCH": mismatches}, "markets": out}
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
