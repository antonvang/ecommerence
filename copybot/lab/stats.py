"""One implementation of the statistics used across the research record (ENGINE_PROPOSAL.md §2, stage S2).

Each function reproduces the corresponding research-module function bit for bit (same algorithm, same random-number
call order), so old results can be re-derived here. The old modules are not changed.

| here                   | replaces                                                    |
|------------------------|-------------------------------------------------------------|
| block_lb               | tsmom.block_lb (block 8), carry.block_lb (block 4)          |
| cluster_lb             | pmcal.cluster_lb (weeks), pm_lp.cluster_lb (markets), prelim/m3 day_lb |
| n_req                  | tsmom/pm_lp (z 2.5758), carry (2.512), pmcal (3.0233)       |
| psr                    | tsmom.psr                                                   |
"""
from __future__ import annotations

import math
import random
import statistics

Z_POWER_80 = 0.8416


def z_one_sided(alpha):
    """One-sided normal quantile (e.g. 0.005 -> 2.5758)."""
    return statistics.NormalDist().inv_cdf(1 - alpha)


def block_lb(x, q, block=8, n=10000, seed=5):
    """Lower q-quantile of the mean by circular-free moving-block bootstrap (contiguous blocks of `block`)."""
    if len(x) < block:
        return None
    rng = random.Random(seed)
    starts = list(range(len(x) - block + 1))
    k = math.ceil(len(x) / block)
    means = sorted(statistics.mean([v for s in rng.choices(starts, k=k) for v in x[s:s + block]][:len(x)])
                   for _ in range(n))
    return means[int(q * n)]


def clusters_in_order(rows, key, value, builtin_sum=False):
    """[(sum, count)] per cluster, in order of first appearance (the order the research modules used).

    builtin_sum=False adds values one at a time (pmcal, pm_lp); True uses Python's sum(), which is compensated since
    Python 3.12 and differs in the last bit (prelim/m3 day_lb). Both are kept so old results reproduce exactly.
    """
    acc = {}
    for r in rows:
        acc.setdefault(key(r), []).append(value(r))
    out = []
    for vals in acc.values():
        if builtin_sum:
            s = sum(vals)
        else:
            s = 0.0
            for v in vals:
                s += v
        out.append((s, len(vals)))
    return out


def cluster_lb(clusters, q, n=10000, seed=5, min_clusters=2):
    """Lower q-quantile of the pooled mean, resampling whole clusters [(sum, count)] with replacement."""
    cl = [c for c in clusters if c[1] > 0]
    if len(cl) < min_clusters:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        s = k = 0
        for a, b in rng.choices(cl, k=len(cl)):
            s += a
            k += b
        means.append(s / k)
    means.sort()
    return means[int(q * n)]


def n_req(mean, sd, z_a=2.5758, z_b=Z_POWER_80):
    """Required sample size for a one-sided test; None when the mean is not positive."""
    if mean is None or mean <= 0 or not sd:
        return None
    return math.ceil(((z_a + z_b) * sd / mean) ** 2)


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def psr(r, sr0=0.0):
    """Probabilistic Sharpe ratio (Bailey & López de Prado), per-period Sharpe."""
    if len(r) < 3 or statistics.stdev(r) == 0:
        return None
    m, s = statistics.mean(r), statistics.stdev(r)
    sr = m / s
    n = len(r)
    g3 = sum((x - m) ** 3 for x in r) / n / s ** 3
    g4 = sum((x - m) ** 4 for x in r) / n / s ** 4
    den = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return norm_cdf((sr - sr0) * math.sqrt(n - 1) / den)


def max_drawdown(r):
    """Largest peak-to-trough fall of the cumulative sum of r."""
    eq = peak = dd = 0.0
    for x in r:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dd


def thirds(r):
    t = len(r) // 3
    return [sum(r[:t]), sum(r[t:2 * t]), sum(r[2 * t:])] if t else []


def series_summary(r, periods_per_year=None, lb=None):
    """Common summary of a return series; `lb` is a callable returning the lower bound (or None)."""
    sd = statistics.stdev(r) if len(r) > 1 else None
    mean = statistics.mean(r) if r else None
    return {"n": len(r), "total": sum(r), "mean": mean, "sd": sd,
            "sharpe_ann": (mean / sd * math.sqrt(periods_per_year)) if sd and periods_per_year else None,
            "max_dd": max_drawdown(r), "worst": min(r) if r else None, "thirds": thirds(r),
            "lb": lb(r) if lb else None, "psr_0": psr(r)}
