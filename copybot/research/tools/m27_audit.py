"""Mission 27.1 audits (research/studies/MISSION27_1_2026-11-02.md). Read-only on lab.db; no network, no outcome of a
locked key after its lock.

  python3 research/tools/m27_audit.py h27a  [--db PATH]   structure of the 197 equity perps on census hours BEFORE
                                                          amendment 34's first day (2026-11-02 00:00 UTC) only
  python3 research/tools/m27_audit.py costs [--db PATH]   cost regimes from abnormal_move book_rt, k3 books, capacity
  python3 research/tools/m27_audit.py flags [--db PATH]   scanner flags right after a data gap vs the rest
"""
import argparse
import calendar
import datetime as dt
import json
import math
import os
import random
import sqlite3
import statistics as st
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
from lab import sessions  # noqa: E402

LOCK_34 = 1793577600                                  # 2026-11-02 00:00 UTC: amendment 34 uses no hour before this
UNIVERSE = os.path.join(HERE, "research", "data", "H27A_UNIVERSE_2026-11-01.json")
DB = os.path.join(HERE, "data", "lab", "lab.db")


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def census(db, before=None):
    """[(ts, {symbol: {column: value}})] in time order; only snapshots with ts < before when given."""
    out = []
    q = "SELECT ts, payload FROM observations WHERE detector='census/1' AND metric='snapshot'"
    for ts, pl in db.execute(q + (" AND ts < ?" if before else "") + " ORDER BY id", (before,) if before else ()):
        p = json.loads(pl)
        cols = p["columns"]
        out.append((p.get("premium_fetched_at") or ts, {s: dict(zip(cols, r)) for s, r in p["rows"].items()}))
    return out


def corr(a, b):
    if len(a) < 3:
        return None
    ma, mb = st.fmean(a), st.fmean(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb) if va and vb else None


def hourly_returns(snaps, syms, field="markPrice"):
    """{t_end: {sym: log return}} for consecutive snapshots 0.5-1.5 h apart."""
    out = {}
    for (t0, a), (t1, b) in zip(snaps, snaps[1:]):
        if not 1800 <= t1 - t0 <= 5400:
            continue
        r = {}
        for s in syms:
            x, y = (a.get(s) or {}).get(field), (b.get(s) or {}).get(field)
            if x and y and x > 0 and y > 0:
                r[s] = math.log(y / x)
        out[t0] = r
    return out


def dependence(rets, syms, min_obs=10):
    """Average pairwise correlation, mean R^2 on the equal-weight market, market share of the average variance."""
    hours = sorted(rets)
    mkt = {h: st.fmean(rets[h].values()) for h in hours if len(rets[h]) >= 50}
    series = {s: [(h, rets[h][s]) for h in mkt if s in rets[h]] for s in syms}
    series = {s: v for s, v in series.items() if len(v) >= min_obs}
    r2 = [c * c for s, v in series.items() if (c := corr([x for _, x in v], [mkt[h] for h, _ in v])) is not None]
    names = sorted(series)
    rng = random.Random(34)
    pairs = [tuple(rng.sample(names, 2)) for _ in range(min(3000, len(names) * 10))] if len(names) > 1 else []
    pc = []
    for a, b in pairs:
        da, db_ = dict(series[a]), dict(series[b])
        common = sorted(set(da) & set(db_))
        if (c := corr([da[h] for h in common], [db_[h] for h in common])) is not None:
            pc.append(c)
    var_m = st.pvariance(list(mkt.values())) if len(mkt) > 2 else None
    var_i = st.fmean(st.pvariance([x for _, x in v]) for v in series.values()) if series else None
    return {"hours": len(mkt), "symbols": len(series), "mean_pair_corr": round(st.fmean(pc), 3) if pc else None,
            "mean_r2_on_market": round(st.fmean(r2), 3) if r2 else None,
            "market_var_share": round(var_m / var_i, 3) if var_m and var_i else None}


def ls_sd(rets, syms, n_leg=40, draws=200):
    """sd of an equal-weight n_leg-vs-n_leg hourly long-short: random partitions, and the beta-sorted extreme legs."""
    hours = [h for h in sorted(rets) if len(rets[h]) >= 2 * n_leg]
    if len(hours) < 5:
        return None
    mkt = {h: st.fmean(rets[h].values()) for h in hours}
    beta = {}
    for s in syms:
        v = [(rets[h][s], mkt[h]) for h in hours if s in rets[h]]
        if len(v) >= 5 and (vm := st.pvariance([m for _, m in v])):
            mx, mm = st.fmean(x for x, _ in v), st.fmean(m for _, m in v)
            beta[s] = sum((x - mx) * (m - mm) for x, m in v) / len(v) / vm
    rng = random.Random(34)
    rand = []
    for _ in range(draws):
        ls = []
        for h in hours:
            names = sorted(rets[h])
            pick = rng.sample(names, 2 * n_leg)
            ls.append(st.fmean(rets[h][s] for s in pick[:n_leg]) - st.fmean(rets[h][s] for s in pick[n_leg:]))
        rand.append(st.pstdev(ls))
    order = sorted(beta, key=beta.get)
    lo, hi = order[:n_leg], order[-n_leg:]
    bls = [st.fmean(rets[h][s] for s in hi if s in rets[h]) - st.fmean(rets[h][s] for s in lo if s in rets[h])
           for h in hours if sum(s in rets[h] for s in hi) > 10 and sum(s in rets[h] for s in lo) > 10]
    return {"hours": len(hours), "random_hourly_sd": round(st.fmean(rand), 5),
            "beta_sorted_hourly_sd": round(st.pstdev(bls), 5) if len(bls) > 2 else None}


def signals(snaps, syms):
    """Amendment 34 point 5 signal on pre-lock days: P = last snapshot before the open, prior X = last snapshot >= 60 min
    before the previous close. Returns {day: {sym: s}} (signal side only; no outcome)."""
    out, prev_x = {}, None
    days = sorted({dt.datetime.fromtimestamp(t, dt.timezone.utc).astimezone(sessions.ET).date() for t, _ in snaps})
    for d in days:
        if d.weekday() >= 5 or d in sessions.NYSE_CLOSED:
            continue
        opn = dt.datetime.combine(d, dt.time(9, 30), sessions.ET).timestamp()
        cls = dt.datetime.combine(d, dt.time(13 if d in sessions.NYSE_EARLY else 16), sessions.ET).timestamp()
        pre = [r for t, r in snaps if opn - 24 * 3600 < t < opn]
        x = [r for t, r in snaps if opn < t <= cls - 3600]
        if prev_x is not None and pre:
            s = {}
            for sym in syms:
                m, i = (pre[-1].get(sym) or {}).get("markPrice"), (prev_x.get(sym) or {}).get("indexPrice")
                if m and i:
                    s[sym] = math.log(m / i)
            out[str(d)] = s
        prev_x = x[-1] if x else None
    return out


def h27a(db):
    syms = json.load(open(UNIVERSE))["symbols"]
    snaps = census(db, before=LOCK_34)
    rets = hourly_returns(snaps, syms)
    rth = {h: r for h, r in rets.items() if sessions.equity(h) == sessions.RTH}
    off = {h: r for h, r in rets.items() if sessions.equity(h) != sessions.RTH}
    idx = hourly_returns(snaps, syms, "indexPrice")
    idx_rth = {h: r for h, r in idx.items() if sessions.equity(h) == sessions.RTH}
    sig = signals(snaps, syms)
    spy = "SPYUSDT"
    sig_rows = []
    for d, s in sig.items():
        v = list(s.values())
        if len(v) < 50:
            continue
        m = st.fmean(v)
        ms = st.fmean(x * x for x in v)
        sig_rows.append({"day": d, "n": len(v), "mean_s": round(m, 5), "sd_s": round(st.pstdev(v), 5),
                         "common_share": round(m * m / ms, 3) if ms else None,
                         "spy_s": round(s[spy], 5) if spy in s else None})
    lsd = ls_sd(idx_rth, syms)
    est = None
    if lsd:
        est = {k: round(v * math.sqrt(5), 4) if v else None for k, v in lsd.items() if k.endswith("_sd")}
    return {"rule": "Mission 27.1 point 1; census hours before 2026-11-02 00:00 UTC only (never amendment 34 data)",
            "snapshots": len(snaps), "universe": len(syms),
            "off_hours_mark": dependence(off, syms), "rth_mark": dependence(rth, syms),
            "rth_index": dependence(idx_rth, syms),
            "ls_sd_rth_index": lsd, "ls_sd_day_est_sqrt5h": est,
            "signal_days": sig_rows}


def costs(db):
    """Book round trip (no fees) by regime; each comparison is split into two halves of the period."""
    rows = []
    for ts, inst, metric, val, pl in db.execute(
            "SELECT ts, instrument, metric, value, payload FROM observations WHERE detector='abnormal_move/1' "
            "AND metric IN ('book_rt','z_1h') ORDER BY id"):
        rows.append((ts, inst, metric, val, pl))
    z = {}
    rt = []
    for ts, inst, metric, val, pl in rows:
        p = json.loads(pl) if pl else {}
        key = (inst, p.get("open_s"))
        if metric == "z_1h":
            z[key] = val
        elif val is not None:
            rt.append((ts, inst, val, p.get("off_hours"), p.get("class"), p.get("open_s")))
    if not rt:
        return {}
    mid = st.median(t for t, *_ in rt)

    def cmp(name, f):
        out = {}
        for inst in sorted({r[1] for r in rt}):
            res = []
            for half in (0, 1):
                g = [r for r in rt if r[1] == inst and (r[0] >= mid) == bool(half)]
                a = [r[2] for r in g if f(r) is True]
                b = [r[2] for r in g if f(r) is False]
                res.append((st.median(a) * 1e4 if len(a) >= 5 else None, len(a),
                            st.median(b) * 1e4 if len(b) >= 5 else None, len(b)))
            ratio = [round(x[0] / x[2], 2) if x[0] and x[2] else None for x in res]
            out[inst] = {"halves": [[round(x[0], 2) if x[0] else None, x[1], round(x[2], 2) if x[2] else None, x[3]]
                                    for x in res], "ratio": ratio,
                         "same_direction": (None if None in ratio else (ratio[0] > 1) == (ratio[1] > 1))}
        return {"comparison": name, "by_market": out}

    def hour(r):
        return time.gmtime(r[5] or r[0]).tm_hour

    def wkd(r):
        return time.gmtime(r[5] or r[0]).tm_wday >= 5

    def vol(r):
        v = z.get((r[1], r[5]))
        return None if v is None else (abs(v) >= 2 if (abs(v) >= 2 or abs(v) < 1) else None)
    res = {"rule": "Mission 27.1 point 4; abnormal_move book_rt = $5k book round trip without fees; median bp; "
                   "two halves split at the median timestamp; same_direction = the ratio is on the same side of 1 in both",
           "n": len(rt), "from": time.strftime("%m-%d %H:%M", time.gmtime(min(r[0] for r in rt))),
           "to": time.strftime("%m-%d %H:%M", time.gmtime(max(r[0] for r in rt))),
           "off_hours_vs_open": cmp("off_hours / open", lambda r: r[3] if r[3] is not None else None),
           "weekend_vs_weekday": cmp("weekend / weekday", wkd),
           "asia_night_vs_rest": cmp("UTC 00-07 / rest", lambda r: hour(r) < 8),
           "high_vol_vs_calm": cmp("|z_1h|>=2 / |z_1h|<1", vol)}
    k3 = {}
    for inst, pl in db.execute("SELECT instrument, payload FROM observations WHERE detector='k3/1' AND metric='book'"):
        p = json.loads(pl)
        if p.get("rt_5000") is not None and p.get("S"):
            k3.setdefault(time.gmtime(p["S"]).tm_hour, []).append(p["rt_5000"])
    res["k3_rt5000_by_S_hour"] = {h: {"n": len(v), "median_bp": round(st.median(v) * 1e4, 1)} for h, v in sorted(k3.items())}
    cap = {}
    for inst, pl in db.execute("SELECT instrument, payload FROM observations WHERE detector='capacity/1'"):
        p = json.loads(pl)
        if p.get("round_trip") is not None and not p.get("censored"):
            cap.setdefault(inst, []).append(p["round_trip"])
    tiers = sorted((st.median(v) * 1e4 for v in cap.values()))
    if tiers:
        q = lambda f: round(tiers[min(len(tiers) - 1, int(f * len(tiers)))], 1)   # noqa: E731
        res["capacity_50k_rt_bp_quantiles"] = {"instruments": len(tiers), "p10": q(.1), "p25": q(.25), "p50": q(.5),
                                               "p75": q(.75), "p90": q(.9)}
    return res


def flags(db, watch_log):
    """Flag rate in the first scan hour after a scanner gap (watch.log 'scanner virker igen') vs all other scan hours."""
    rec = []
    for line in open(watch_log, encoding="utf-8", errors="replace"):
        if "scanner virker igen" in line:
            try:
                rec.append(calendar.timegm(time.strptime(line[:19], "%Y-%m-%dT%H:%M:%S")))
            except ValueError:
                pass
    after, base = [0, 0], [0, 0]
    for ts, fl in db.execute("SELECT ts, flagged FROM observations WHERE detector='abnormal_move/1' AND metric IN "
                             "('z_1h','z_24h','volume_ratio')"):
        g = after if any(0 <= ts - r <= 2 * 3600 for r in rec) else base
        g[0] += 1
        g[1] += 1 if fl else 0
    return {"rule": "Mission 27.1 H27-K; flags = z_1h/z_24h/volume_ratio rows with flagged=1",
            "recoveries": len(rec), "after_gap": {"rows": after[0], "flagged": after[1],
                                                  "rate": round(after[1] / after[0], 4) if after[0] else None},
            "other": {"rows": base[0], "flagged": base[1], "rate": round(base[1] / base[0], 4) if base[0] else None}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("h27a", "costs", "flags"))
    ap.add_argument("--db", default=DB)
    ap.add_argument("--watch-log", default=os.path.join(os.path.dirname(DB), "watch.log"))
    a = ap.parse_args()
    db = ro(a.db)
    out = {"h27a": lambda: h27a(db), "costs": lambda: costs(db), "flags": lambda: flags(db, a.watch_log)}[a.what]()
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
