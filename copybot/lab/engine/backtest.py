"""Deterministic backtest on hourly bars: gross returns from positions, then costs (cost agent) and portfolio metrics.

Portfolio = equal weight across instruments with data at each hour. Returns are simple per-bar returns, summed per
UTC day (an additive approximation, stated in every report). No compounding, no leverage.
"""
from __future__ import annotations

import math
import random
import statistics

from lab import stats

DAY = 86400


def gross(bars, positions):
    """Per-bar (ts, pos, gross_ret, turnover). Position i earns bar i's close-to-close return."""
    out, prev = [], 0.0
    for i in range(1, len(bars)):
        pos = positions[i]
        r = bars[i][2] / bars[i - 1][2] - 1
        out.append((bars[i][0], pos, pos * r, abs(pos - prev)))
        prev = pos
    return out


def apply_costs(rows, funding, costs, mult=1.0):
    """Net per bar = gross - turnover x (fee + half spread + slippage) x mult - pos x funding (longs pay positive rates).
    Returns rows (ts, pos, gross, fee, spread, slippage, funding, net)."""
    out = []
    for ts, pos, g, tov in rows:
        fee = tov * costs["taker_fee"] * mult
        spr = tov * costs["half_spread"] * mult
        slp = tov * costs["slippage"] * mult
        fnd = pos * funding.get(ts, 0.0)
        out.append((ts, pos, g, fee, spr, slp, fnd, g - fee - spr - slp - fnd))
    return out


def portfolio(per_symbol):
    """Equal-weight average across symbols present at each timestamp. per_symbol: {sym: [cost rows]}.
    Rows: (ts, net position, gross, fee, spread, slippage, funding, net, gross exposure, turnover); the last two are
    averages of |position| and |position change| per symbol, so a market-neutral book shows its real activity."""
    acc, prev = {}, {}
    for sym, rows in per_symbol.items():
        p0 = 0.0
        for r in rows:
            a = acc.setdefault(r[0], [0.0] * 10 + [0])
            for k in range(1, 8):
                a[k] += r[k]
            a[8] += abs(r[1])
            a[9] += abs(r[1] - p0)
            p0 = r[1]
            a[10] += 1
    out = []
    for ts in sorted(acc):
        a = acc[ts]
        n = a[10]
        out.append((ts,) + tuple(a[k] / n for k in range(1, 10)))
    return out


def daily(rows, col=7):
    d = {}
    for r in rows:
        d[r[0] // DAY] = d.get(r[0] // DAY, 0.0) + r[col]
    return [d[k] for k in sorted(d)]


def bootstrap_means(x, block=5, n=2000, seed=7):
    """Sorted means of n moving-block bootstrap resamples (contiguous blocks, fixed seed). One distribution serves
    the one-sided lower bound and the 95 % interval."""
    if len(x) < block:
        return None
    rng = random.Random(seed)
    starts = range(len(x) - block + 1)
    k = math.ceil(len(x) / block)
    L = len(x)
    out = []
    for _ in range(n):
        s = [v for st in rng.choices(starts, k=k) for v in x[st:st + block]][:L]
        out.append(math.fsum(s) / L)
    out.sort()
    return out


def sharpe_ann(rows):
    """Annualised net Sharpe of daily net returns only (cheap; used by placebo simulations)."""
    d = daily(rows, 7)
    if len(d) < 2:
        return None
    m = math.fsum(d) / len(d)
    sd = math.sqrt(math.fsum((v - m) ** 2 for v in d) / (len(d) - 1))
    return m / sd * math.sqrt(365) if sd > 0 else None


def auto_block(x, floor=5):
    """Amendment 15a point 2: max(floor, ceil(b)) days, b the Politis & White (2004; Patton, Politis & White 2009)
    automatic block length for the moving-block bootstrap of x (flat-top window), at most n / 3."""
    n = len(x)
    if n < 3 * floor:
        return floor
    m = math.fsum(x) / n
    d = [v - m for v in x]
    r0 = math.fsum(v * v for v in d) / n
    if r0 <= 0:
        return floor
    lags = min(n - 1, max(2 * floor, math.ceil(3 * math.sqrt(n))))
    R = [r0] + [math.fsum(d[i] * d[i - k] for i in range(k, n)) / n for k in range(1, lags + 1)]
    kn, c = max(5, math.ceil(math.sqrt(math.log10(n)))), 2 * math.sqrt(math.log10(n) / n)
    mhat = next((j for j in range(1, lags - kn + 1) if all(abs(R[j + k] / r0) < c for k in range(1, kn + 1))), None)
    if mhat is None:
        return min(n // 3, max(floor, lags))
    M = min(2 * mhat, lags)
    lam = lambda t: 1.0 if abs(t) <= 0.5 else (2 * (1 - abs(t)) if abs(t) <= 1 else 0.0)   # noqa: E731
    G = 2 * math.fsum(lam(k / M) * k * R[k] for k in range(1, M + 1))
    g0 = R[0] + 2 * math.fsum(lam(k / M) * R[k] for k in range(1, M + 1))
    D = 4 / 3 * g0 ** 2
    b = (2 * G * G / D) ** (1 / 3) * n ** (1 / 3) if D > 0 else floor
    return int(min(n // 3, max(floor, math.ceil(b))))


def ar1_lb(x, q):
    """Amendment 15b: one-sided lower q bound of the mean with the AR(1) long-run variance factor (1 + r) / (1 - r),
    r the first-order autocorrelation plus its small-sample bias (1 + 3r) / n, clamped to [0, 0.99]."""
    n = len(x)
    if n < 3:
        return None
    m = math.fsum(x) / n
    s = statistics.stdev(x)
    rho = effective_n(x)[1]
    r = min(0.99, max(0.0, rho + (1 + 3 * rho) / n))
    return m - statistics.NormalDist().inv_cdf(1 - q) * s * math.sqrt((1 + r) / ((1 - r) * n))


def metrics(rows, seed=7, lb_q=0.10, block=5):
    """Portfolio metrics from cost rows; uncertainty by block bootstrap of daily net returns (5-day blocks, or
    block="auto": auto_block, amendment 15a)."""
    if not rows:
        return {"bars": 0}
    net_d, gross_d = daily(rows, 7), daily(rows, 2)
    sd = statistics.stdev(net_d) if len(net_d) > 1 else 0.0
    mean = statistics.mean(net_d)
    if len(rows[0]) > 9:                                   # portfolio rows: count bars where any symbol traded
        trades = sum(1 for r in rows if r[9] > 1e-12)
    else:
        trades = sum(1 for i in range(1, len(rows)) if abs(rows[i][1] - rows[i - 1][1]) > 1e-12)
    total_net = sum(net_d)
    auto = block == "auto"
    block = auto_block(net_d) if auto else block
    boot = bootstrap_means(net_d, block, 2000, seed)
    lb_boot = boot[int(lb_q * len(boot))] if boot else None
    lb_ar1 = ar1_lb(net_d, lb_q) if auto else None
    lb = min(lb_boot, lb_ar1) if (lb_boot is not None and lb_ar1 is not None) else lb_boot
    active_days = sum(1 for x in net_d if x != 0)
    return {
        "bars": len(rows), "days": len(net_d), "gross_total": sum(gross_d), "net_total": total_net,
        "net_mean_daily": mean, "net_sd_daily": sd, "net_sharpe_ann": (mean / sd * math.sqrt(365)) if sd > 0 else None,
        "gross_sharpe_ann": (statistics.mean(gross_d) / statistics.stdev(gross_d) * math.sqrt(365))
        if len(gross_d) > 1 and statistics.stdev(gross_d) > 0 else None,
        "max_drawdown": stats.max_drawdown(net_d), "worst_day": min(net_d), "best_day": max(net_d),
        "exposure": statistics.mean((r[8] if len(r) > 9 else abs(r[1])) for r in rows), "position_changes": trades,
        "turnover": sum(r[9] for r in rows) if len(rows[0]) > 9 else None,
        "win_rate_days": (sum(1 for x in net_d if x > 0) / active_days) if active_days else None,
        "expectancy_per_change": (total_net / trades) if trades else None,
        "fees": sum(r[3] for r in rows), "spread": sum(r[4] for r in rows), "slippage": sum(r[5] for r in rows),
        "funding": sum(r[6] for r in rows),
        "lb_one_sided": lb, "lb_bootstrap": lb_boot, "lb_ar1": lb_ar1,
        "lb_quantile": lb_q, "ci95": [boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]] if boot else None,
        "bootstrap": {"method": "moving block", "block_days": block, "draws": 2000, "seed": seed},
        "daily_net": net_d}


def psr(sr, n_obs, benchmark=0.0, skew=0.0, kurt=3.0):
    """Probabilistic Sharpe ratio: probability that the true per-period Sharpe exceeds `benchmark`."""
    if sr is None or n_obs < 3:
        return None
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    return statistics.NormalDist().cdf((sr - benchmark) * math.sqrt(n_obs - 1) / den)


def effective_n(x):
    """(n_eff, rho): the sample size n (1 - rho) / (1 + rho) of a series with first-order autocorrelation rho > 0, else
    n (amendment 15 point 4; never larger than n)."""
    n = len(x)
    if n < 3:
        return float(n), None
    m = math.fsum(x) / n
    den = math.fsum((v - m) ** 2 for v in x)
    rho = math.fsum((x[i] - m) * (x[i - 1] - m) for i in range(1, n)) / den if den > 0 else 0.0
    return (n * (1 - rho) / (1 + rho) if rho > 0 else float(n)), rho


def deflated_sharpe(sr, sr_trials, n_obs, skew=0.0, kurt=3.0, n=None):
    """Probability that the (per-period) Sharpe `sr` exceeds the expected maximum of `len(sr_trials)` independent trials
    (Bailey & Lopez de Prado 2014). Returns None when it cannot be computed. `n` replaces the number of trials (e.g. an
    effective number of independent trials, lab.engine.pbo.effective_trials); the default is unchanged."""
    N = len(sr_trials) if n is None else n
    if sr is None or N < 2 or n_obs < 3:
        return None
    var = statistics.pvariance(sr_trials)
    if var <= 0:
        return None
    nd, g = statistics.NormalDist(), 0.5772156649
    sr0 = math.sqrt(var) * ((1 - g) * nd.inv_cdf(1 - 1 / N) + g * nd.inv_cdf(1 - 1 / (N * math.e)))
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    return nd.cdf((sr - sr0) * math.sqrt(n_obs - 1) / den)
