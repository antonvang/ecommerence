"""Cross-venue funding spread study (Hyperliquid vs Binance USD-M, both perps), last ~60 days. Per 8-hour bucket
(UTC 00/08/16): HL = sum of its hourly rates in the bucket, BN = its settled rate(s) in the bucket. spread = HL - BN.
Enter when |spread| >= X and the mean of the last 3 buckets has the same sign and >= X/2 (short the venue that
pays more, long the other); hold until |spread| < 0.01 % for 2 buckets in a row or the sign flips; cost per round trip."""
import json, os, statistics, sys
d = sys.argv[1]
B = 8 * 3600
bn = json.load(open(os.path.join(d, "binance_funding.json")))
hl = json.load(open(os.path.join(d, "hl_funding.json")))
pairs = {}
for c, rows in hl.items():
    s = f"{c}USDT"
    if isinstance(rows, dict) or s not in bn or isinstance(bn[s], dict):
        continue
    h, b = {}, {}
    for t, r in rows:
        h[t // B] = h.get(t // B, 0.0) + r
    for t, r in bn[s]:
        b[(t - 1) // B] = b.get((t - 1) // B, 0.0) + r          # a settlement at 08:00 pays for the bucket before
    keys = sorted(set(h) & set(b))
    if len(keys) > 30:
        pairs[c] = [h[k] - b[k] for k in keys]
print("coins on both venues with data:", len(pairs))
allv = [v for s in pairs.values() for v in s]
print(f"|spread| median {statistics.median(abs(v) for v in allv)*100:.4f}%/8h, p90 {sorted(abs(v) for v in allv)[int(.9*len(allv))]*100:.4f}%")
for COST in (0.003, 0.005):
    print(f"\n== round-trip cost {COST*100:.1f} %")
    for X in (0.0002, 0.0003, 0.0005, 0.001, 0.002):
        tr = []
        for c, r in pairs.items():
            i = 3
            while i < len(r):
                sg = 1 if r[i] > 0 else -1
                if abs(r[i]) >= X and sg * statistics.mean(r[i-2:i+1]) >= X / 2:
                    j, low, got = i + 1, 0, 0.0
                    while j < len(r):
                        got += sg * r[j]
                        low = low + 1 if sg * r[j] < 0.0001 else 0
                        j += 1
                        if low >= 2:
                            break
                    tr.append((got - COST, j - i - 1, j >= len(r)))
                    i = j + 1
                else:
                    i += 1
        n = [t[0] for t in tr]
        if n:
            print(f"X={X*100:.3f}%/8h trades={len(n):4d} open={sum(t[2] for t in tr):3d} mean={statistics.mean(n)*100:+.3f}% "
                  f"median={statistics.median(n)*100:+.3f}% win={sum(v > 0 for v in n)/len(n):.0%} hold(med)={statistics.median(t[1] for t in tr):.0f} buckets")
