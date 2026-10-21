"""Probability of backtest overfitting by combinatorially symmetric cross-validation (CSCV).

Bailey, Borwein, López de Prado and Zhu (2014), "The Probability of Backtest Overfitting", Journal of Computational
Finance. DIAGNOSTIC ONLY: it decides nothing and is not a gate.

Given N configurations' per-period returns over the same T periods: split the periods into S equal, contiguous blocks
(S even); for every way of choosing S/2 blocks as in-sample (IS) with the rest out-of-sample (OOS), pick the
configuration with the best IS Sharpe and record where it ranks OOS. With relative rank w = rank / (N + 1) (rank 1 =
worst, N = best; ties share the average rank) the logit is lambda = ln(w / (1 - w)). PBO is the share of combinations
with lambda <= 0: the IS winner did no better than the OOS median. Also reported: how often the IS winner lost money
OOS, and the slope of OOS on IS Sharpe of the winner (performance degradation).

LIMITATION (research/studies/PBO_PERSISTENCE_2026-10-21.md): with strongly persistent returns (AR(1) phi near 1, as
funding carry) CSCV reports a low PBO without any skill (about 0.2 instead of 0.5); a boundary embargo barely helps. A
low PBO is evidence only against a null PBO calibrated with the same persistence.

Pure Python (the lab has no numpy): per configuration and block the sum, sum of squares and count are computed once,
so a combination costs O(N x S).
"""
from __future__ import annotations

import itertools
import math

PERIODS_PER_YEAR = 365


class PBOError(ValueError):
    pass


def _blocks(t, s):
    """S contiguous blocks covering T periods (the first T mod S blocks get one more period)."""
    base, extra = divmod(t, s)
    out, a = [], 0
    for i in range(s):
        b = a + base + (1 if i < extra else 0)
        out.append((a, b))
        a = b
    return out


def _sharpe(n, s1, s2):
    if n < 2:
        return 0.0
    mean = s1 / n
    var = (s2 - n * mean * mean) / (n - 1)
    if var <= 1e-18:
        return 0.0                                     # a flat configuration ranks as zero, never as infinite
    return mean / math.sqrt(var) * math.sqrt(PERIODS_PER_YEAR)


def _ranks(x):
    """1-based ranks, ascending, ties averaged."""
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def cscv(series, s=16, max_combinations=None):
    """series: N lists of T per-period returns (same T). Returns the PBO summary.
    max_combinations: use only the first that many combinations in lexicographic order (None = all C(S, S/2))."""
    n = len(series)
    if n < 2:
        raise PBOError("need at least 2 configurations")
    t = len(series[0])
    if any(len(x) != t for x in series):
        raise PBOError("all configurations need the same number of periods")
    if s < 2 or s % 2:
        raise PBOError("S must be an even number >= 2")
    if t < 2 * s:
        raise PBOError(f"T = {t} periods is too short for S = {s} blocks (need at least 2 periods per block)")
    blocks = _blocks(t, s)
    agg = []                                            # agg[config][block] = (count, sum, sum of squares)
    for x in series:
        row = []
        for a, b in blocks:
            seg = x[a:b]
            row.append((len(seg), math.fsum(seg), math.fsum(v * v for v in seg)))
        agg.append(row)
    total = [(sum(c for c, _, _ in row), math.fsum(v for _, v, _ in row), math.fsum(q for _, _, q in row))
             for row in agg]
    lambdas, is_best, oos_best, losses, k = [], [], [], 0, 0
    for combo in itertools.combinations(range(s), s // 2):
        if max_combinations is not None and k >= max_combinations:
            break
        k += 1
        is_sr, oos_sr = [], []
        for row, (tc, ts, tq) in zip(agg, total):
            c = math.fsum(row[i][0] for i in combo)
            s1 = math.fsum(row[i][1] for i in combo)
            s2 = math.fsum(row[i][2] for i in combo)
            is_sr.append(_sharpe(c, s1, s2))
            oos_sr.append(_sharpe(tc - c, ts - s1, tq - s2))
        best = max(range(n), key=lambda i: is_sr[i])
        w = _ranks(oos_sr)[best] / (n + 1)
        lambdas.append(math.log(w / (1 - w)))
        is_best.append(is_sr[best])
        oos_best.append(oos_sr[best])
        losses += oos_sr[best] < 0
    m = len(lambdas)
    mx, my = sum(is_best) / m, sum(oos_best) / m
    sxx = sum((x - mx) ** 2 for x in is_best)
    slope = sum((x - mx) * (y - my) for x, y in zip(is_best, oos_best)) / sxx if sxx > 0 else None
    lam = sorted(lambdas)
    return {"pbo": sum(1 for v in lambdas if v <= 0) / m, "combinations": m,
            "combinations_total": math.comb(s, s // 2), "configurations": n, "periods": t, "blocks": s,
            "prob_oos_loss": losses / m, "is_sharpe_of_selected_mean": mx, "oos_sharpe_of_selected_mean": my,
            "degradation_slope": slope, "lambda_median": lam[m // 2],
            "method": "CSCV, Bailey/Borwein/Lopez de Prado/Zhu 2014; Sharpe annualised x sqrt(365); diagnostic only"}


def effective_trials(series):
    """Effective number of independent trials among N correlated return series (diagnostic): the mean pairwise
    correlation rho, computed exactly from standardised series (|sum z|^2 - sum |z|^2 over N (N - 1)), and
    N_eff = rho + (1 - rho) N, the approximation in Bailey & Lopez de Prado (2014, The Deflated Sharpe Ratio).
    Flat series (zero variance) are left out and counted."""
    t = len(series[0]) if series else 0
    z, flat = [], 0
    for x in series:
        if len(x) != t:
            raise PBOError("all configurations need the same number of periods")
        m = math.fsum(x) / t
        d = [v - m for v in x]
        norm = math.sqrt(math.fsum(v * v for v in d))
        if norm <= 1e-15:
            flat += 1
            continue
        z.append([v / norm for v in d])
    n = len(z)
    if n < 2:
        return {"configurations": len(series), "used": n, "flat": flat, "mean_correlation": None, "n_eff": float(n)}
    total = [math.fsum(col) for col in zip(*z)]
    rho = (math.fsum(v * v for v in total) - n) / (n * (n - 1))
    rho = max(-1.0 / (n - 1), min(1.0, rho))
    return {"configurations": len(series), "used": n, "flat": flat, "mean_correlation": rho,
            "n_eff": rho + (1 - rho) * n,
            "method": "N_eff = rho + (1 - rho) N, Bailey and Lopez de Prado 2014; rho = mean pairwise correlation"}
