"""Amendment 32: pre-data power plan. The sd of an outcome comes from explore0's UNCONDITIONAL returns at the same
horizon (never from the hypothesis' own outcome data); MDE = (z_{1-a/2} + z_{0.80}) * sd / sqrt(n clusters).

Cache only (hypogen.Reader('explore0') refuses every other month); no network, no holdout, no outcome y.
Usage: python3 research/tools/power_plan.py [--cache DIR] > plan.json
"""
import argparse, json, math, os, statistics, sys
from statistics import NormalDist

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lab import hypogen, movescreen                                   # noqa: E402
from lab.engine import data                                           # noqa: E402

HOURS = {"1h": 1, "4h": 4, "24h": 24, "7d": 168}
NS = (15, 20, 28, 60, 90)
Z_B = NormalDist().inv_cdf(0.80)


def mde(sd, n, alpha):
    return (NormalDist().inv_cdf(1 - alpha / 2) + Z_B) * sd / math.sqrt(n)


def sds(reader, syms):
    """sd of non-overlapping log returns per horizon: BTC alone, and the median over alts of (alt - BTC)."""
    btc = movescreen.prices(reader, "BTCUSDT")
    out = {}
    for name, h in HOURS.items():
        step = h * hypogen.HOUR
        grid = sorted(btc)[::h]
        rb = {t: math.log(btc[t + step] / btc[t]) for t in grid if t + step in btc}
        alt = []
        for s in syms:
            if s == "BTCUSDT":
                continue
            px = movescreen.prices(reader, s)
            ex = [math.log(px[t + step] / px[t]) - rb[t] for t in rb if t in px and t + step in px]
            if len(ex) >= 30:
                alt.append(statistics.stdev(ex))
        out[name] = {"btc_sd": statistics.stdev(rb.values()), "btc_n": len(rb),
                     "alt_excess_sd_median": statistics.median(alt), "alt_coins": len(alt)}
    return out


def plan(s, cost=hypogen.COST):
    rows = []
    for name, v in s.items():
        for kind, sd in (("btc", v["btc_sd"]), ("alt_excess", v["alt_excess_sd_median"])):
            for a in (0.005, 0.05):
                rows.append({"horizon": name, "outcome": kind, "sd": sd, "alpha": a,
                             "mde": {n: mde(sd, n, a) for n in NS},
                             "n_for_floor": math.ceil(((NormalDist().inv_cdf(1 - a / 2) + Z_B) * sd / cost) ** 2)})
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache")
    a = ap.parse_args()
    if a.cache:
        data.CACHE = a.cache
    r = hypogen.Reader(hypogen.SCREEN)
    s = sds(r, movescreen.universe(a.cache))
    json.dump({"rule": "research/PROTOCOL_V3.md amendment 32", "window": "explore0 2020-03..2021-12 (unconditional)",
               "cost_floor": hypogen.COST, "files": len(r.files), "sd": s, "plan": plan(s)}, sys.stdout, indent=1)
