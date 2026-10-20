"""Threshold study on recent settled funding (files from fetch_recent_funding.py).

Entry when the latest settled rate, normalised to 8 hours, is >= X and the mean of the recent window (Binance: 3
settlements, HL: 24 hours) is >= X/2; hold until two settlements in a row are below the 0.01 %/8h floor. A trade still
open at the end is valued at its funding so far (flagged 'open').

Fixed 2026-10-21: the normalised rate (per 8 hours) is used only for the entry and exit rules; the income is the sum of
the rates actually paid. Before, the normalised value was summed, which doubled the income of 4-hour coins and
multiplied Hyperliquid's (hourly) by 8.

Costs: one figure per round trip as a fraction of ONE leg's notional (spot leg = perp leg), covering both legs, entry
and exit: fees, spread and slippage. Funding income is also per unit of one leg. Return on capital is lower (capital
= spot + perp margin + buffer, about 2.2 legs at 1x; lab/capital.py).

Usage: python3 research/tools/recent_study.py <dir> [cost ...]   (default costs 0.003 0.006 0.010 0.015)
"""
import json
import os
import random
import statistics
import sys

FLOOR = 0.0001
THRESHOLDS = (0.0002, 0.0003, 0.0005, 0.00075, 0.001, 0.002)
BOOT_N, BOOT_SEED = 2000, 7


def trades(series, window, x, only=None):
    """Gross funding per trade (fraction of one leg), holding length in settlements, open flag."""
    out = []
    for k, r in series.items():
        if only is not None and k not in only:
            continue
        i = window
        while i < len(r):
            if r[i][0] >= x and statistics.mean(v for v, _ in r[i - window + 1:i + 1]) >= x / 2:
                j, low, got = i + 1, 0, 0.0
                while j < len(r):
                    got += r[j][1]                                   # the rate actually paid
                    low = low + 1 if r[j][0] < FLOOR else 0          # the exit rule on the normalised rate
                    j += 1
                    if low >= 2:
                        break
                out.append((got, j - i - 1, j >= len(r)))
                i = j + 1
            else:
                i += 1
    return out


def lower_bound(values, q=0.05):
    rng = random.Random(BOOT_SEED)
    means = sorted(statistics.mean(rng.choice(values) for _ in values) for _ in range(BOOT_N))
    return means[int(q * BOOT_N)]


def study(series, window, name, costs, only=None):
    print(f"\n== {name}: {len(series)} instruments" + (f", {len(only)} with Binance spot" if only is not None else ""))
    for x in THRESHOLDS:
        tr = trades(series, window, x, only)
        if not tr:
            continue
        gross = [g for g, _, _ in tr]
        line = (f"X={x*100:.3f}%/8h trades={len(tr):4d} open={sum(o for *_, o in tr):3d} "
                f"gross mean={statistics.mean(gross)*100:+.3f}% median hold={statistics.median(h for _, h, _ in tr):.0f}")
        for c in costs:
            net = [g - c for g in gross]
            line += (f" | cost {c*100:.1f}%: mean {statistics.mean(net)*100:+.3f}% "
                     f"(5% lower {lower_bound(net)*100:+.3f}%) win {sum(v > 0 for v in net)/len(net):.0%}")
        print(line)


def binance_series(bn):
    out = {}
    for s, rows in bn.items():
        if isinstance(rows, dict) or len(rows) < 10:
            continue
        rows = sorted(rows)
        norm = []
        for (t0, _), (t1, v) in zip(rows, rows[1:]):
            h = max(1, round((t1 - t0) / 3600))
            norm.append((v * 8 / h, v))                              # (per 8 hours, actually paid)
        out[s] = norm
    return out


def hl_series(hl):
    return {c: [(v * 8, v) for _, v in sorted(rows)] for c, rows in hl.items()
            if not isinstance(rows, dict) and len(rows) > 48}


def main(argv):
    d = argv[1]
    costs = tuple(float(c) for c in argv[2:]) or (0.003, 0.006, 0.010, 0.015)
    spot_path = os.path.join(d, "spot_symbols.json")
    spot = set(json.load(open(spot_path))) if os.path.exists(spot_path) else None
    bser = binance_series(json.load(open(os.path.join(d, "binance_funding.json"))))
    study(bser, 3, "Binance USD-M, all perps (a hedge needs spot: not tradeable as a whole)", costs)
    if spot is not None:
        study(bser, 3, "Binance USD-M, only coins with Binance spot", costs, only={s for s in bser if s in spot})
    hser = hl_series(json.load(open(os.path.join(d, "hl_funding.json"))))
    if spot is not None:
        study(hser, 24, "Hyperliquid (rule on rate x 8), only coins with Binance spot", costs,
              only={c for c in hser if f"{c}USDT" in spot})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
