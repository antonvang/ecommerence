"""Historical liquidity vs the lab's cost model (amendment 14 data; descriptive, decides nothing).

Reads the hourly bookDepth summaries (data/lab/market/ingest/bookdepth_1h/<COIN>-<YYYY-MM>.csv.gz) for the TRAIN
window only (2023-01..2023-08; validation and holdout stay untouched) and estimates, per coin and order size, the
average price impact of a market order that walks the book on one side.

Model (stated, not measured): cumulative notional is linear between the published levels (0 at the mid, then the
notional at 1, 2, 3, 4, 5 % away). An order of S USD that consumes up to x % has an average fill
offset = (integral of the offset over the consumed notional) / S. The bid-ask spread is NOT in bookDepth: the impact
here excludes it, so it is compared with the model's slippage term only (2 bp per fill), and the model's half-spread
(2 bp) is reported next to it as an assumption.

Usage: python3 research/tools/depth_study.py [ingest_dir]
"""
import csv
import glob
import gzip
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT = os.path.join(HERE, "data", "lab", "market", "ingest", "bookdepth_1h")
TRAIN = tuple(f"2023-{m:02d}" for m in range(1, 9))
SIZES = (1_000, 5_000, 10_000, 50_000, 100_000)
MODEL_SLIPPAGE = 0.0002          # lab cost model, per fill (lab/capital.py DEFAULTS, paper engine extra slippage)
MODEL_HALF_SPREAD = 0.0002


def impact(size, depth):
    """Average fill offset (fraction) for `size` USD against cumulative depth {pct: usd} (pct = 1..5), linear between
    levels; None if the order is larger than the 5 % depth."""
    pts = [(0.0, 0.0)] + sorted((p / 100.0, d) for p, d in depth.items() if d is not None)
    cost, prev_x, prev_d = 0.0, 0.0, 0.0
    for x, d in pts[1:]:
        if d <= prev_d:
            prev_x, prev_d = x, d
            continue
        take = min(size, d) - prev_d
        if take <= 0:
            break
        # within the segment the offset rises linearly from prev_x to x as notional goes from prev_d to d
        x_end = prev_x + (x - prev_x) * take / (d - prev_d)
        cost += take * (prev_x + x_end) / 2
        if size <= d:
            return cost / size
        prev_x, prev_d = x, d
    return None


def quantile(v, q):
    v = sorted(v)
    if not v:
        return None
    i = (len(v) - 1) * q
    lo, hi = math.floor(i), math.ceil(i)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def study(folder=DEFAULT):
    out = {}
    for path in sorted(glob.glob(os.path.join(folder, "*.csv.gz"))):
        coin, month = os.path.basename(path)[:-7].split("-", 1)
        if month not in TRAIN:
            continue
        with gzip.open(path, "rt") as f:
            for row in csv.DictReader(f):
                for side, sign in (("buy", "+"), ("sell", "-")):
                    for kind in ("mean", "min"):
                        depth = {p: (float(row[f"{kind}_usd_{sign}{p}"]) if row[f"{kind}_usd_{sign}{p}"] else None)
                                 for p in range(1, 6)}
                        for s in SIZES:
                            v = impact(s, depth)
                            key = (coin, kind, s)
                            o = out.setdefault(key, {"hours": 0, "too_big": 0, "v": []})
                            o["hours"] += 1
                            if v is None:
                                o["too_big"] += 1
                            else:
                                o["v"].append(v)
    return out


def main(argv):
    folder = argv[1] if len(argv) > 1 else DEFAULT
    res = study(folder)
    if not res:
        print(f"no train-window files in {folder}")
        return 1
    print(f"impact excludes the spread; model slippage {MODEL_SLIPPAGE * 1e4:.0f} bp/fill, "
          f"half-spread {MODEL_HALF_SPREAD * 1e4:.0f} bp/fill (assumed)")
    print(f"{'coin':10} {'depth':5} {'size USD':>9} {'side-h':>6} {'median bp':>9} {'p90 bp':>7} {'p99 bp':>7} "
          f"{'> model':>8} {'>5% book':>8}")
    for (coin, kind, s), o in sorted(res.items()):
        v = o["v"]
        over = sum(1 for x in v if x > MODEL_SLIPPAGE) / len(v) if v else None
        fmt = lambda x: f"{x * 1e4:.2f}" if x is not None else "-"
        print(f"{coin:10} {kind:5} {s:>9,} {o['hours']:>6} {fmt(quantile(v, .5)):>9} {fmt(quantile(v, .9)):>7} "
              f"{fmt(quantile(v, .99)):>7} {('-' if over is None else f'{over:.0%}'):>8} {o['too_big']:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
