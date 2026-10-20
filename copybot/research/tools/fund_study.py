"""Threshold study on cached explore0 funding (2020-03..2021-12), no network: enter when the settled rate >= X and the
mean of the last 3 >= X/2 (12e-like), hold until two settlements in a row < 0.01 %, cost 0.6 % per round trip."""
import csv, io, os, statistics, sys, zipfile
d = sys.argv[1]
series = {}
for f in sorted(os.listdir(d)):
    sym, _, ym = f[:-4].split("-", 2)[0], None, f[:-4].split("-", 2)[2]
    if not ("2020-03" <= ym <= "2021-12"):
        continue
    z = zipfile.ZipFile(os.path.join(d, f))
    rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
    series.setdefault(sym, []).extend((int(r[0]) // 1000, float(r[2])) for r in rows[1:] if r and r[0].isdigit())
COST = 0.006
for X in (0.0003, 0.0005, 0.00075, 0.001, 0.0015, 0.002, 0.003):
    trades = []
    for sym, s in series.items():
        s = sorted(s)
        r = [v for _, v in s]
        i = 3
        while i < len(r):
            if r[i] >= X and statistics.mean(r[i - 2:i + 1]) >= X / 2:
                j, low, got = i + 1, 0, 0.0
                while j < len(r):
                    got += r[j]
                    low = low + 1 if r[j] < 0.0001 else 0
                    j += 1
                    if low >= 2:
                        break
                trades.append((got - COST, j - i - 1))
                i = j + 1
            else:
                i += 1
    if trades:
        nets = [t[0] for t in trades]
        print(f"X={X*100:.3f}%  trades={len(trades):4d}  mean net={statistics.mean(nets)*100:+.3f}%  median={statistics.median(nets)*100:+.3f}%  "
              f"win={sum(n > 0 for n in nets)/len(nets):.0%}  median hold={statistics.median(t[1] for t in trades)} settlements")
