"""Threshold study on recent settled funding (files from fetch_recent_funding.py). Rates are normalised to 8 hours.
Enter when the latest settled rate >= X and the mean of the recent window (Binance: 3 settlements, HL: 24 hours)
>= X/2; hold until two settlements in a row are below the 0.01 %/8h floor; 0.6 % cost per round trip. A trade still
open at the end is valued at its funding so far (flagged 'open')."""
import json, os, statistics, sys
d = sys.argv[1]
spot = set(json.load(open(os.path.join(d, "spot_symbols.json")))) if os.path.exists(os.path.join(d, "spot_symbols.json")) else None
COST, FLOOR = 0.006, 0.0001

def study(series, window, name, only=None):
    print(f"\n== {name}: {len(series)} instruments" + (f", {len(only)} with Binance spot" if only is not None else ""))
    for X in (0.0002, 0.0003, 0.0005, 0.00075, 0.001, 0.002):
        tr = []
        for k, rows in series.items():
            if only is not None and k not in only:
                continue
            r = rows
            i = window
            while i < len(r):
                if r[i] >= X and statistics.mean(r[i - window + 1:i + 1]) >= X / 2:
                    j, low, got = i + 1, 0, 0.0
                    while j < len(r):
                        got += r[j][1] if isinstance(r[j], tuple) else r[j]
                        low = low + 1 if r[j] < FLOOR else 0
                        j += 1
                        if low >= 2:
                            break
                    tr.append((got - COST, j - i - 1, j >= len(r)))
                    i = j + 1
                else:
                    i += 1
        if tr:
            n = [t[0] for t in tr]
            print(f"X={X*100:.3f}%/8h trades={len(tr):4d} open={sum(t[2] for t in tr):3d} mean={statistics.mean(n)*100:+.3f}% "
                  f"median={statistics.median(n)*100:+.3f}% win={sum(v > 0 for v in n)/len(n):.0%} "
                  f"median hold={statistics.median(t[1] for t in tr):.0f} settlements total={sum(n)*100:+.1f}%")

bn = json.load(open(os.path.join(d, "binance_funding.json")))
bser = {}
for s, rows in bn.items():
    if isinstance(rows, dict) or len(rows) < 10:
        continue
    rows = sorted(rows)
    norm = []
    for (t0, _), (t1, v) in zip(rows, rows[1:]):
        h = max(1, round((t1 - t0) / 3600))
        norm.append(v * 8 / h)                       # per settlement -> per 8 hours
    bser[s] = norm
study(bser, 3, "Binance USD-M (spot+perp), seneste op til 1000 afregninger")
if spot is not None:
    study(bser, 3, "Binance USD-M, kun mønter med Binance spot", only={s for s in bser if s in spot})
hl = json.load(open(os.path.join(d, "hl_funding.json")))
hser = {c: [v * 8 for _, v in sorted(rows)] for c, rows in hl.items() if not isinstance(rows, dict) and len(rows) > 48}
study(hser, 24, "Hyperliquid (×8), seneste 60 dage")
if spot is not None:
    study(hser, 24, "Hyperliquid, kun mønter med Binance spot", only={c for c in hser if f"{c}USDT" in spot})
