"""PBO / CSCV for the exploration lane (diagnostic, decides nothing): if the lane picks the variant with the best
in-sample Sharpe, how often does it rank at or below the median out of sample?

Recomputes each tried variant's daily net return in explore0 (2020-03..2021-12) at the lane's 2x cost stress, with
the lane's own code (lab.explore, the family module, lab.engine.backtest), from the market cache only: every download
is refused. Variants are aligned on the days that all of them cover. Runs CSCV on all variants and per function.

Usage: python3 research/tools/pbo_lane.py <market_cache_dir> <explore_artifacts_dir> [S] [max_variants] [--no-cscv]
"""
import glob
import importlib
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)

from lab import explore, families  # noqa: E402
from lab.engine import backtest, data, pbo  # noqa: E402

DAY = 86400


def no_network(*a, **k):
    raise RuntimeError("pbo_lane: network refused (cache only)")


def variants(art_dir, fid):
    seen = {}
    for p in sorted(glob.glob(os.path.join(art_dir, "*", f"{fid}_*.json"))):
        with open(p) as f:
            for r in json.load(f).get("results") or []:
                seen.setdefault(r["key"], (r["function"], r["params"], r.get("coins")))
    return seen


def daily(fid, fam, fn, params, bars, funding, coins):
    if coins:
        bars, funding = {s: bars[s] for s in coins if s in bars}, {s: funding.get(s, {}) for s in coins if s in bars}
    mod = importlib.import_module(f"lab.families.{fid}")
    pos = getattr(mod, fn)(bars, funding, params, None)
    rows = {s: backtest.apply_costs(backtest.gross(bars[s], pos[s]), funding[s], fam["costs"], explore.STRESS)
            for s in bars}
    out = {}
    for r in backtest.portfolio(rows):
        d = int(r[0]) // DAY
        out[d] = out.get(d, 0.0) + r[7]                       # net of the equal-weight book, summed per UTC day
    return out


def dsr_view(rows):
    """Effective trials and the deflated Sharpe of the best variant (daily Sharpe), with N = configurations and with
    N = N_eff (diagnostic)."""
    import statistics
    eff = pbo.effective_trials(rows)
    srs = []
    for x in rows:
        sd = statistics.pstdev(x)
        srs.append(statistics.fmean(x) / sd if sd > 0 else 0.0)
    best = max(range(len(rows)), key=lambda i: srs[i])
    x = rows[best]
    m, sd = statistics.fmean(x), statistics.pstdev(x)
    skew = sum(((v - m) / sd) ** 3 for v in x) / len(x) if sd > 0 else 0.0
    kurt = sum(((v - m) / sd) ** 4 for v in x) / len(x) if sd > 0 else 3.0
    return {**eff, "best_daily_sharpe": srs[best], "best_annual_sharpe": srs[best] * 365 ** 0.5,
            "dsr_n_configurations": backtest.deflated_sharpe(srs[best], srs, len(x), skew, kurt),
            "dsr_n_eff": backtest.deflated_sharpe(srs[best], srs, len(x), skew, kurt, n=max(2.0, eff["n_eff"]))}


def main(argv):
    pos = [a for a in argv[1:] if not a.startswith("--")]
    market, arts = pos[0], pos[1]
    s = int(pos[2]) if len(pos) > 2 else 16
    cap = int(pos[3]) if len(pos) > 3 else None
    urllib.request.urlopen = no_network
    explore.fetch_allowed = lambda *a, **k: False             # read the cache only
    data.CACHE = market
    fid = "fcarry"
    fam = families.load(fid)
    t0 = time.time()
    bars, funding, excluded, inputs = explore._files(fam, explore.SPLIT)
    vs = variants(arts, fid)
    keys = sorted(vs)[:cap] if cap else sorted(vs)
    series = {}
    for k in keys:
        fn, params, coins = vs[k]
        if coins and any(c not in bars for c in coins):
            continue                                           # a coin the data-quality rule excluded
        series[k] = daily(fid, fam, fn, params, bars, funding, coins)
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    out = {"family": fid, "window": explore.SPLIT, "cost_stress": explore.STRESS, "excluded_coins": excluded,
           "variants_tried": len(vs), "variants_used": len(series), "days_common": len(common),
           "first_day": time.strftime("%Y-%m-%d", time.gmtime(common[0] * DAY)) if common else None,
           "last_day": time.strftime("%Y-%m-%d", time.gmtime(common[-1] * DAY)) if common else None,
           "inputs_digest": inputs["digest"], "blocks": s}
    mat = {k: [v[d] for d in common] for k, v in series.items()}
    by_fn = {}
    for k in mat:
        by_fn.setdefault(vs[k][0], []).append(mat[k])
    if "--no-cscv" not in argv:
        out["all"] = pbo.cscv(list(mat.values()), s=s)
        out["by_function"] = {fn: (pbo.cscv(rows, s=s) if len(rows) >= 2 else None)
                              for fn, rows in sorted(by_fn.items())}
    out["effective_trials"] = {"all": dsr_view(list(mat.values())),
                               **{fn: dsr_view(rows) for fn, rows in sorted(by_fn.items())}}
    out["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
