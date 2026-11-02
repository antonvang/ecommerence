"""Amendments 34 (H27-A) and 36 (H27-A2): census equity perps, off-hours move -> same-day cash session.

  python3 research/tools/m34_eq.py count [--db PATH]   valid days and symbols only (amendment 34 point 13 / 36 point 13)
  python3 research/tools/m34_eq.py run   [--db PATH]   the one run; refuses before 28 valid days

Written before any census hour from 2026-11-02 was read. The count mode never computes s, y or r_d.
"""
import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import statistics as st
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
from lab import sessions  # noqa: E402
from lab.edgemonitor import t_cdf  # noqa: E402

FIRST_DAY = dt.date(2026, 11, 2)
LAST_DAY = dt.date(2027, 3, 12)
MIN_DAYS, MIN_SYMBOLS, LATE_S = 28, 50, 600
FLOOR = 0.006
U34 = os.path.join(HERE, "research", "data", "H27A_UNIVERSE_2026-11-01.json")
U36 = os.path.join(HERE, "research", "data", "H27A2_UNIVERSE_2026-11-01.json")
DB = os.path.join(HERE, "data", "lab", "lab.db")


def snapshots(db, t0, t1):
    """[(fetched_ts, rows)] of census snapshots fetched in [t0, t1) and at most LATE_S after the hour."""
    out = []
    for ts, pl in db.execute("SELECT ts, payload FROM observations WHERE detector='census/1' AND metric='snapshot' "
                             "AND ts >= ? AND ts < ? ORDER BY id", (t0 - 3600, t1 + 3600)):
        p = json.loads(pl)
        t = p.get("premium_fetched_at") or ts
        if t0 <= t < t1 and t % 3600 <= LATE_S:
            out.append((t, {s: dict(zip(p["columns"], r)) for s, r in p["rows"].items()}))
    return out


def trading_days(first=FIRST_DAY, last=LAST_DAY):
    d = first
    while d <= last:
        if d.weekday() < 5 and d not in sessions.NYSE_CLOSED:
            yield d
        d += dt.timedelta(days=1)


def session_bounds(d):
    opn = dt.datetime.combine(d, dt.time(9, 30), sessions.ET).timestamp()
    cls = dt.datetime.combine(d, dt.time(13 if d in sessions.NYSE_EARLY else 16), sessions.ET).timestamp()
    return opn, cls


def pex(snaps, d):
    """Amendment 34 point 4: P (last before the open), E (first >= 30 min after), X (last >= 60 min before close)."""
    opn, cls = session_bounds(d)
    pre = [x for x in snaps if opn - 24 * 3600 < x[0] < opn]
    e = [x for x in snaps if x[0] >= opn + 1800]
    xs = [x for x in snaps if opn < x[0] <= cls - 3600]
    if not pre or not e or not xs or e[0][0] >= xs[-1][0]:
        return None
    return pre[-1], e[0], xs[-1]


def day_points(db, upto):
    """[(day, P, E, X)] for valid trading days from FIRST_DAY whose X lies before `upto`."""
    snaps = snapshots(db, int(dt.datetime.combine(FIRST_DAY - dt.timedelta(days=4), dt.time(0),
                                                  dt.timezone.utc).timestamp()), upto)
    out, prev = [], None
    for d in trading_days(FIRST_DAY - dt.timedelta(days=4)):
        p = pex(snaps, d)
        p = p if p and p[2][0] < upto else None
        if p and prev and d >= FIRST_DAY:                 # s needs the previous trading day's X
            out.append((d, prev, p))
        prev = p
    return out


def sy(prev, cur, syms):
    """s and y per symbol (amendment 34 points 5-6): s = ln(mark at P / index at prior X); y = ln(index X / index E)."""
    (_, _, (_, xprev)), ((_, P), (_, E), (_, X)) = prev, cur
    out = {}
    for s in syms:
        m, i0 = (P.get(s) or {}).get("markPrice"), (xprev.get(s) or {}).get("indexPrice")
        e, x = (E.get(s) or {}).get("indexPrice"), (X.get(s) or {}).get("indexPrice")
        if m and i0 and e and x:
            out[s] = (math.log(m / i0), math.log(x / e))
    return out


def ls(pairs):
    """Bottom fifth of the signal minus top fifth, equal weight; None below MIN_SYMBOLS."""
    if len(pairs) < MIN_SYMBOLS:
        return None
    order = sorted(pairs, key=lambda v: v[0])
    k = len(order) // 5
    return st.fmean(y for _, y in order[:k]) - st.fmean(y for _, y in order[-k:])


def neutral(d, beta):
    """Amendment 36 point 5: s* = s - beta F_s, y* = y - beta F_y with the day's cross-sectional medians."""
    d = {s: v for s, v in d.items() if s in beta}
    if not d:
        return {}
    fs, fy = st.median(v[0] for v in d.values()), st.median(v[1] for v in d.values())
    return {s: (v[0] - beta[s] * fs, v[1] - beta[s] * fy) for s, v in d.items()}


def tstat(xs):
    if len(xs) < 3 or st.stdev(xs) == 0:
        return None, None
    t = st.fmean(xs) / (st.stdev(xs) / math.sqrt(len(xs)))
    return t, 2 * (1 - t_cdf(abs(t), len(xs) - 1))     # Student's t, two-sided (amendment 35a point 6)


def judge(rs, placebo):
    """PASS rules shared by amendments 34 and 36 (point 11 / 10)."""
    vals = [r for _, r in rs]
    if len(vals) < MIN_DAYS:
        return {"verdict": "UNTESTABLE", "days": len(vals)}
    t, p = tstat(vals)
    mean = st.fmean(vals)
    half = len(vals) // 2
    h1, h2 = st.fmean(vals[:half]), st.fmean(vals[half:])
    drop = sorted(vals, key=abs)[:-2]
    tp, _ = tstat([r for _, r in placebo])
    ok = (p is not None and p <= 0.005 and abs(mean) - FLOOR > 0 and (h1 > 0) == (h2 > 0) == (mean > 0)
          and (st.fmean(drop) > 0) == (mean > 0) and tp is not None and abs(tp) < 2)
    return {"verdict": "PASS" if ok else "SCREEN_FAIL", "days": len(vals), "mean": mean, "t": t, "p": p,
            "halves": [h1, h2], "without_2_largest": st.fmean(drop), "placebo_t": tp}


def count(db, upto):
    u34 = json.load(open(U34))["symbols"]
    u36 = json.load(open(U36))["universe"]
    out = []
    for d, prev, cur in day_points(db, upto):
        n34, n36 = len(sy(prev, cur, u34)), len(sy(prev, cur, u36))
        out.append({"day": str(d), "symbols_m34": n34, "symbols_m36": n36})
    valid34 = sum(1 for r in out if r["symbols_m34"] >= MIN_SYMBOLS)
    valid36 = sum(1 for r in out if r["symbols_m36"] >= MIN_SYMBOLS)
    return {"rule": "amendments 34/36 point 13: counts only", "valid_days_m34": valid34, "valid_days_m36": valid36,
            "days": out}


def run(db, upto):
    u34 = json.load(open(U34))["symbols"]
    beta = json.load(open(U36))["beta"]
    pts = day_points(db, upto)
    r34, r36, p34, p36, prev_sy = [], [], [], [], None
    for d, prev, cur in pts:
        cur_sy = sy(prev, cur, u34)
        a, b = ls(list(cur_sy.values())), ls(list(neutral(cur_sy, beta).values()))
        if a is not None:
            r34.append((d, a))
        if b is not None:
            r36.append((d, b))
        if prev_sy:                                       # placebo: yesterday's signal against today's outcome
            pa = [(prev_sy[s][0], cur_sy[s][1]) for s in cur_sy if s in prev_sy]
            if (x := ls(pa)) is not None:
                p34.append((d, x))
            n0, n1 = neutral(prev_sy, beta), neutral(cur_sy, beta)
            if (x := ls([(n0[s][0], n1[s][1]) for s in n1 if s in n0])) is not None:
                p36.append((d, x))
        prev_sy = cur_sy
    return {"m34": judge(r34, p34), "m36": judge(r36, p36)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("count", "run"))
    ap.add_argument("--db", default=DB)
    a = ap.parse_args()
    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    upto = int(dt.datetime.now(dt.timezone.utc).timestamp())
    if a.what == "count":
        out = count(db, upto)
    else:
        c = count(db, upto)
        if min(c["valid_days_m34"], c["valid_days_m36"]) < MIN_DAYS:
            out = {"refused": f"fewer than {MIN_DAYS} valid days", **{k: v for k, v in c.items() if k != "days"}}
        else:
            out = run(db, upto)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
