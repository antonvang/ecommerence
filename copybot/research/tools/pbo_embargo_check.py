"""CSCV under the null with autocorrelated returns: PBO with and without a boundary embargo (research/studies/PBO_PERSISTENCE_2026-10-21.md)."""
import sys, math, random, itertools, statistics
sys.path.insert(0, "/home/anton/copybot-dev/copybot")
from lab.engine import pbo

def ar1(t, phi, rng):
    x, out = 0.0, []
    s = math.sqrt(1 - phi * phi)
    for _ in range(t):
        x = phi * x + s * rng.gauss(0, 1)
        out.append(0.01 * x)                      # zero mean: no skill
    return out

def cscv_embargo(series, s, emb):
    """CSCV where IS drops the `emb` periods next to any OOS block (both sides)."""
    t, n = len(series[0]), len(series)
    blocks = pbo._blocks(t, s)
    lambdas = []
    for combo in itertools.combinations(range(s), s // 2):
        cs = set(combo)
        keep = []
        for b, (a, z) in enumerate(blocks):
            if b not in cs:
                continue
            lo, hi = a, z
            if b - 1 >= 0 and b - 1 not in cs: lo = min(z, a + emb)
            if b + 1 < s and b + 1 not in cs: hi = max(lo, z - emb)
            keep.append((lo, hi))
        oos = [(a, z) for b, (a, z) in enumerate(blocks) if b not in cs]
        def sr(x, spans):
            v = [x[i] for a, z in spans for i in range(a, z)]
            m = sum(v) / len(v); sd = statistics.pstdev(v)
            return m / sd if sd > 0 else 0.0
        is_sr = [sr(x, keep) for x in series]
        oos_sr = [sr(x, oos) for x in series]
        best = max(range(n), key=lambda i: is_sr[i])
        w = pbo._ranks(oos_sr)[best] / (n + 1)
        lambdas.append(math.log(w / (1 - w)))
    return sum(1 for v in lambdas if v <= 0) / len(lambdas)

T, N, S, SEEDS, EMB = 671, 40, 8, 12, 14
for phi in (0.0, 0.5, 0.9, 0.98):
    plain, emb = [], []
    for seed in range(SEEDS):
        rng = random.Random(1000 * seed + int(phi * 100))
        rows = [ar1(T, phi, rng) for _ in range(N)]
        plain.append(pbo.cscv(rows, s=S)["pbo"])
        emb.append(cscv_embargo(rows, S, EMB))
    se = lambda v: statistics.pstdev(v) / math.sqrt(len(v))
    print(f"phi={phi}: PBO plain {statistics.mean(plain):.3f} (se {se(plain):.3f})  embargo{EMB} {statistics.mean(emb):.3f} (se {se(emb):.3f})  diff {statistics.mean(emb)-statistics.mean(plain):+.3f}")
