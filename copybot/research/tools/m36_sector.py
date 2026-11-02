"""Amendment 36b: decision-free sector side report for H27-A2 (m36).

  python3 research/tools/m36_sector.py run [--db PATH]   only together with m36's one run; refuses below 28 valid days

Written before any m36 value of s, y or r_d was computed. Nothing here changes m36's verdict.
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m34_eq as base  # noqa: E402

PC1 = os.path.join(base.HERE, "research", "data", "H27A2_SECTOR_PC1_2026-11-02.json")


def residualise(vals, load):
    """Cross-sectional OLS residuals of vals on (1, load) (36b point 2)."""
    ks = list(vals)
    x = [load[k] for k in ks]
    y = [vals[k] for k in ks]
    mx, my = st.fmean(x), st.fmean(y)
    vx = sum((a - mx) ** 2 for a in x)
    g = sum((a - mx) * (b - my) for a, b in zip(x, y)) / vx if vx else 0.0
    return {k: (b - my) - g * (a - mx) for k, a, b in zip(ks, x, y)}


def pearson(a, b):
    ma, mb = st.fmean(a), st.fmean(b)
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** 0.5 if va and vb else None


def day(n36, load):
    """(r_d**, rho_d) for one day's neutralised {sym: (s*, y*)}; r_d** is None below 50 symbols."""
    d = {s: v for s, v in n36.items() if s in load}
    if len(d) < 3:
        return None, None
    ss = residualise({s: v[0] for s, v in d.items()}, load)
    yy = residualise({s: v[1] for s, v in d.items()}, load)
    rho = pearson([d[s][0] for s in d], [load[s] for s in d])
    return base.ls([(ss[s], yy[s]) for s in d]), rho


def report(days):
    """36b point 3 over [(date, r**, rho)]."""
    rs = [r for _, r, _ in days if r is not None]
    rho = [p for _, _, p in days if p is not None]
    t, p = base.tstat(rs)
    return {"rule": "amendment 36b: decides nothing", "days": len(rs), "mean_r_star2": st.fmean(rs) if rs else None,
            "t": t, "p": p, "rho_mean": st.fmean(rho) if rho else None, "rho_median": st.median(rho) if rho else None,
            "share_abs_rho_gt_0_3": sum(abs(x) > 0.3 for x in rho) / len(rho) if rho else None}


def run(db, upto):
    load = json.load(open(PC1))["loading"]
    beta = json.load(open(base.U36))["beta"]
    u34 = json.load(open(base.U34))["symbols"]
    out = []
    for d, prev, cur in base.day_points(db, upto):
        n36 = base.neutral(base.sy(prev, cur, u34), beta)
        if len(n36) < base.MIN_SYMBOLS:                     # the m36 day itself is invalid (36 point 6)
            continue
        r, rho = day(n36, load)
        out.append((d, r, rho))
    return report(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("run",))
    ap.add_argument("--db", default=base.DB)
    a = ap.parse_args(argv)
    db = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    upto = int(dt.datetime.now(dt.timezone.utc).timestamp())
    c = base.count(db, upto)
    out = ({"refused": f"fewer than {base.MIN_DAYS} valid m36 days", "valid_days_m36": c["valid_days_m36"]}
           if c["valid_days_m36"] < base.MIN_DAYS else run(db, upto))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
