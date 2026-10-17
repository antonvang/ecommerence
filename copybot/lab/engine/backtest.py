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
    """Equal-weight average across symbols present at each timestamp. per_symbol: {sym: [cost rows]}."""
    acc = {}
    for rows in per_symbol.values():
        for r in rows:
            a = acc.setdefault(r[0], [0.0] * 8 + [0])
            for k in range(1, 8):
                a[k] += r[k]
            a[8] += 1
    out = []
    for ts in sorted(acc):
        a = acc[ts]
        n = a[8]
        out.append((ts,) + tuple(a[k] / n for k in range(1, 8)))
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


def metrics(rows, seed=7, lb_q=0.10):
    """Portfolio metrics from cost rows; uncertainty by 5-day block bootstrap of daily net returns."""
    if not rows:
        return {"bars": 0}
    net_d, gross_d = daily(rows, 7), daily(rows, 2)
    sd = statistics.stdev(net_d) if len(net_d) > 1 else 0.0
    mean = statistics.mean(net_d)
    trades = sum(1 for i in range(1, len(rows)) if abs(rows[i][1] - rows[i - 1][1]) > 1e-12)
    total_net = sum(net_d)
    boot = bootstrap_means(net_d, 5, 2000, seed)
    active_days = sum(1 for x in net_d if x != 0)
    return {
        "bars": len(rows), "days": len(net_d), "gross_total": sum(gross_d), "net_total": total_net,
        "net_mean_daily": mean, "net_sd_daily": sd, "net_sharpe_ann": (mean / sd * math.sqrt(365)) if sd > 0 else None,
        "gross_sharpe_ann": (statistics.mean(gross_d) / statistics.stdev(gross_d) * math.sqrt(365))
        if len(gross_d) > 1 and statistics.stdev(gross_d) > 0 else None,
        "max_drawdown": stats.max_drawdown(net_d), "worst_day": min(net_d), "best_day": max(net_d),
        "exposure": statistics.mean(abs(r[1]) for r in rows), "position_changes": trades,
        "win_rate_days": (sum(1 for x in net_d if x > 0) / active_days) if active_days else None,
        "expectancy_per_change": (total_net / trades) if trades else None,
        "fees": sum(r[3] for r in rows), "spread": sum(r[4] for r in rows), "slippage": sum(r[5] for r in rows),
        "funding": sum(r[6] for r in rows),
        "lb_one_sided": boot[int(lb_q * len(boot))] if boot else None,
        "lb_quantile": lb_q, "ci95": [boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]] if boot else None,
        "bootstrap": {"method": "moving block", "block_days": 5, "draws": 2000, "seed": seed},
        "daily_net": net_d}


def deflated_sharpe(sr, sr_trials, n_obs, skew=0.0, kurt=3.0):
    """Probability that the (per-period) Sharpe `sr` exceeds the expected maximum of `len(sr_trials)` independent trials
    (Bailey & Lopez de Prado 2014). Returns None when it cannot be computed."""
    N = len(sr_trials)
    if sr is None or N < 2 or n_obs < 3:
        return None
    var = statistics.pvariance(sr_trials)
    if var <= 0:
        return None
    nd, g = statistics.NormalDist(), 0.5772156649
    sr0 = math.sqrt(var) * ((1 - g) * nd.inv_cdf(1 - 1 / N) + g * nd.inv_cdf(1 - 1 / (N * math.e)))
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    return nd.cdf((sr - sr0) * math.sqrt(n_obs - 1) / den)
