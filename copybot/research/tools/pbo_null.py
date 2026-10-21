"""Null PBO with lane-like persistence (research/studies/PBO_PERSISTENCE_2026-10-21.md): no-skill series = 50 % AR(1) phi 0.97 + 50 % noise."""
import sys, math, random, statistics
sys.path.insert(0, "/home/anton/copybot-dev/copybot")
from lab.engine import pbo
def series(t, rng, phi=0.97, w=0.5):
    x, out, s = 0.0, [], math.sqrt(1 - phi * phi)
    for _ in range(t):
        x = phi * x + s * rng.gauss(0, 1)
        out.append(0.01 * (math.sqrt(w) * x + math.sqrt(1 - w) * rng.gauss(0, 1)))
    return out
def acf(x, k):
    m = statistics.fmean(x); d = [v - m for v in x]
    return sum(a * b for a, b in zip(d, d[k:])) / sum(v * v for v in d)
T, N, S = 671, 40, 16
rng = random.Random(5)
probe = [series(T, rng) for _ in range(20)]
print("null model acf lag1 %.2f lag7 %.2f lag30 %.2f" % tuple(statistics.fmean(acf(x, k) for x in probe) for k in (1, 7, 30)))
vals = []
for seed in range(8):
    rng = random.Random(100 + seed)
    vals.append(pbo.cscv([series(T, rng) for _ in range(N)], s=S)["pbo"])
print("null PBO (no skill, lane-like persistence, S=16, N=40): mean %.3f  min %.3f  max %.3f  per seed %s" % (statistics.fmean(vals), min(vals), max(vals), [round(v, 2) for v in vals]))
