"""Amendment 37 (H27-M): crypto equities against BTC off-hours -> same-day cash session.

  python3 research/tools/m37_cryptoeq.py count [--db PATH]   valid days and names per day only (37 point 13)
  python3 research/tools/m37_cryptoeq.py run   [--db PATH]   the one run on the first 40 valid days; refuses before

Written before any census hour from 2026-11-02 was read. The count mode never prints s*, y*, beta or r_d.
"""
import argparse
import datetime as dt
import json
import math
import os
import random
import sqlite3
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m34_eq as base  # noqa: E402
from lab import sessions  # noqa: E402

NAMES = ("COINUSDT", "MSTRUSDT", "MARAUSDT", "IRENUSDT", "HUTUSDT", "BMNRUSDT", "CRCLUSDT", "HOODUSDT")
BTC = "BTCUSDT"
MIN_DAYS, MIN_N, MIN_HOURS, BETA_DAYS, FLOOR = 40, 6, 20, 15, 0.0075
HOUR = 3600
CENSUS_START = dt.date(2026, 10, 20)                   # before the first census hour; only bounds the beta read


def _get(snap, sym, col):
    v = (snap.get(sym) or {}).get(col)
    return v if v and v > 0 else None


def rth_returns(snaps):
    """37 point 4: [(ET date, {sym: index return, BTC: mark return})] for snapshot pairs 30-90 min apart whose hours
    are both RTH."""
    out = []
    for (t0, a), (t1, b) in zip(snaps, snaps[1:]):
        h0, h1 = t0 - t0 % HOUR, t1 - t1 % HOUR
        if not 1800 <= t1 - t0 <= 5400 or sessions.equity(h0) != "RTH" or sessions.equity(h1 - HOUR) != "RTH":
            continue
        b0, b1 = _get(a, BTC, "markPrice"), _get(b, BTC, "markPrice")
        if not b0 or not b1:
            continue
        r = {BTC: math.log(b1 / b0)}
        for s in NAMES:
            i0, i1 = _get(a, s, "indexPrice"), _get(b, s, "indexPrice")
            if i0 and i1:
                r[s] = math.log(i1 / i0)
        out.append((dt.datetime.fromtimestamp(t0, sessions.ET).date(), r))
    return out


def betas(rets, d):
    """37 point 4: 0.5 * OLS + 0.5 over the 15 NYSE trading days before d; names under 20 hours are left out."""
    prior = [x for x in base.trading_days(CENSUS_START, d - dt.timedelta(days=1))][-BETA_DAYS:]
    window = set(prior)
    rows = [r for day, r in rets if day in window]
    out = {}
    for s in NAMES:
        xy = [(r[BTC], r[s]) for r in rows if s in r]
        if len(xy) < MIN_HOURS:
            continue
        mx, my = st.fmean(x for x, _ in xy), st.fmean(y for _, y in xy)
        vx = sum((x - mx) ** 2 for x, _ in xy)
        if vx == 0:
            continue
        out[s] = 0.5 * sum((x - mx) * (y - my) for x, y in xy) / vx + 0.5
    return out


def raw(prev, cur):
    """Per name (s, y) and BTC's (s, y) before beta: s from P against the prior X, y from E to X (37 points 5-6)."""
    (_, _, (_, xp)), ((_, P), (_, E), (_, X)) = prev, cur
    bs = (_get(P, BTC, "markPrice"), _get(xp, BTC, "markPrice"))
    by = (_get(X, BTC, "markPrice"), _get(E, BTC, "markPrice"))
    if not all(bs + by):
        return {}, None
    btc = (math.log(bs[0] / bs[1]), math.log(by[0] / by[1]))
    out = {}
    for s in NAMES:
        m, i0 = _get(P, s, "markPrice"), _get(xp, s, "indexPrice")
        e, x = _get(E, s, "indexPrice"), _get(X, s, "indexPrice")
        if m and i0 and e and x:
            out[s] = (math.log(m / i0), math.log(x / e))
    return out, btc


def star(rw, btc, beta):
    return {s: (v[0] - beta[s] * btc[0], v[1] - beta[s] * btc[1]) for s, v in rw.items() if s in beta}


def ls_half(pairs):
    """37 point 7: bottom k minus top k of the signal, k = n // 2; None below 6 names."""
    if len(pairs) < MIN_N:
        return None
    order = sorted(pairs, key=lambda v: v[0])
    k = len(order) // 2
    return st.fmean(y for _, y in order[:k]) - st.fmean(y for _, y in order[-k:])


def days(db, upto):
    """[(d, raw today, btc today, raw yesterday or None, btc yesterday, beta_d)] for days with a P/E/X and prior X."""
    t0 = int(dt.datetime.combine(CENSUS_START, dt.time(0), dt.timezone.utc).timestamp())
    rets = rth_returns(base.snapshots(db, t0, upto))
    out, last = [], None
    for d, prev, cur in base.day_points(db, upto):
        rw, btc = raw(prev, cur)
        out.append((d, rw, btc, last[1] if last and last[0] == prev else None,
                    last[2] if last and last[0] == prev else None, betas(rets, d)))
        last = (cur, rw, btc)
    return out


def valid(rows):
    return [r for r in rows if r[2] is not None and len(star(r[1], r[2], r[5])) >= MIN_N]


def count(db, upto):
    rows = days(db, upto)
    per = [{"day": str(r[0]), "names": len(star(r[1], r[2], r[5])) if r[2] else 0} for r in rows]
    return {"rule": "amendment 37 point 13: counts only", "valid_days": len(valid(rows)), "days_need": MIN_DAYS,
            "days": per}


def judge(rs, placebo):
    vals = [v for _, v in rs]
    if len(vals) < MIN_DAYS:
        return {"verdict": "UNTESTABLE", "days": len(vals)}
    t, p = base.tstat(vals)
    mean = st.fmean(vals)
    half = len(vals) // 2
    h1, h2 = st.fmean(vals[:half]), st.fmean(vals[half:])
    drop = st.fmean(sorted(vals, key=abs)[:-2])
    tp, _ = base.tstat([v for _, v in placebo])
    ok = (p is not None and p <= 0.005 and abs(mean) - FLOOR > 0 and (h1 > 0) == (h2 > 0) == (mean > 0)
          and (drop > 0) == (mean > 0) and tp is not None and abs(tp) < 2)
    return {"verdict": "PASS" if ok else "SCREEN_FAIL", "days": len(vals), "mean": mean, "t": t, "p": p,
            "halves": [h1, h2], "without_2_largest": drop, "placebo_t": tp, "placebo_days": len(placebo)}


def run(rows):
    """The first 40 valid days (37 point 8)."""
    use = [r for r in valid(rows) if r[0] <= base.LAST_DAY][:MIN_DAYS]
    rnd = random.Random(37)
    rs, plac, bench = [], [], []
    for d, rw, btc, rw0, btc0, beta in use:
        cur = star(rw, btc, beta)
        rs.append((d, ls_half(list(cur.values()))))
        if rw0 and btc0:
            old = star(rw0, btc0, beta)                                   # yesterday's s* with today's beta
            if (x := ls_half([(old[s][0], cur[s][1]) for s in cur if s in old])) is not None:
                plac.append((d, x))
        ys = [v[1] for v in cur.values()]
        rnd.shuffle(ys)
        k = len(ys) // 2
        bench.append(abs(st.fmean(ys[:k]) - st.fmean(ys[-k:])))
    out = judge(rs, plac)
    out["benchmark_mean_abs_random_split"] = st.fmean(bench) if bench else None
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("count", "run"))
    ap.add_argument("--db", default=base.DB)
    a = ap.parse_args(argv)
    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    upto = int(dt.datetime.now(dt.timezone.utc).timestamp())
    if a.what == "count":
        out = count(db, upto)
    else:
        c = count(db, upto)
        out = ({"refused": f"fewer than {MIN_DAYS} valid days", "valid_days": c["valid_days"]}
               if c["valid_days"] < MIN_DAYS else run(days(db, upto)))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
