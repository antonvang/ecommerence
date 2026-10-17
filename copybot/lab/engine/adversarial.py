"""Adversarial checks: try to break a result before anyone trusts it.

Gating (must pass): look-ahead truncation and future-poison tests are exact; data quality is OK.
Reported flags (inform the decision, documented in the report): one-bar extra delay, placebo with block-shuffled
positions, and the neighbourhood of the selected grid variant.
"""
from __future__ import annotations

import random

from lab.engine import backtest


def truncation_test(family, bars, funding, params, fit=None, samples=40, seed=11):
    """Position at bar i must not change when everything after bar i is removed."""
    full = family(bars, funding, params, fit)
    rng = random.Random(seed)
    idx = sorted(rng.sample(range(1, len(bars)), min(samples, len(bars) - 1))) if len(bars) > 2 else []
    bad = []
    for i in idx:
        cut = bars[i][0]
        part = family(bars[:i + 1], {k: v for k, v in funding.items() if k <= cut}, params, fit)
        if abs(part[i] - full[i]) > 1e-12:
            bad.append(i)
    return {"checked": len(idx), "mismatches": len(bad), "ok": not bad}


def poison_test(family, bars, funding, params, fit=None, seed=13):
    """Replace all data after a random bar with absurd values; earlier positions must be identical."""
    rng = random.Random(seed)
    if len(bars) < 10:
        return {"ok": True, "checked": 0}
    i = rng.randrange(len(bars) // 4, 3 * len(bars) // 4)
    cut = bars[i][0]
    poisoned = bars[:i + 1] + [(ts, o * 1000, c * 1000) for ts, o, c in bars[i + 1:]]
    pf = {k: (v if k <= cut else 1.0) for k, v in funding.items()}
    a, b = family(bars, funding, params, fit), family(poisoned, pf, params, fit)
    diff = sum(1 for k in range(i + 1) if abs(a[k] - b[k]) > 1e-12)
    return {"cut_index": i, "mismatches": diff, "ok": diff == 0}


def truncation_test_xs(family, bars_by, funding_by, params, samples=20, seed=11):
    """Cross-sectional: cut every symbol at the same timestamp; positions up to the cut must not change."""
    full = family(bars_by, funding_by, params)
    ref = min(bars_by, key=lambda s: len(bars_by[s]))
    rng = random.Random(seed)
    n = len(bars_by[ref])
    cuts = sorted(rng.sample(range(1, n), min(samples, n - 1))) if n > 2 else []
    bad = 0
    for i in cuts:
        cut = bars_by[ref][i][0]
        part = family({s: [x for x in b if x[0] <= cut] for s, b in bars_by.items()},
                      {s: {k: v for k, v in f.items() if k <= cut} for s, f in funding_by.items()}, params)
        for s, b in bars_by.items():
            m = sum(1 for x in b if x[0] <= cut)
            if any(abs(part[s][j] - full[s][j]) > 1e-12 for j in range(m)):
                bad += 1
                break
    return {"checked": len(cuts), "mismatches": bad, "ok": bad == 0}


def poison_test_xs(family, bars_by, funding_by, params, seed=13):
    """Cross-sectional: multiply every symbol's prices after a common cut by 1000; earlier positions must not change."""
    ref = min(bars_by, key=lambda s: len(bars_by[s]))
    if len(bars_by[ref]) < 10:
        return {"ok": True, "checked": 0}
    rng = random.Random(seed)
    i = rng.randrange(len(bars_by[ref]) // 4, 3 * len(bars_by[ref]) // 4)
    cut = bars_by[ref][i][0]
    pb = {s: [(ts, o, c) if ts <= cut else (ts, o * 1000, c * 1000) for ts, o, c in b] for s, b in bars_by.items()}
    pf = {s: {k: (v if k <= cut else 1.0) for k, v in f.items()} for s, f in funding_by.items()}
    a, b2 = family(bars_by, funding_by, params), family(pb, pf, params)
    diff = sum(1 for s, b in bars_by.items() for j, x in enumerate(b) if x[0] <= cut and abs(a[s][j] - b2[s][j]) > 1e-12)
    return {"cut_ts": cut, "mismatches": diff, "ok": diff == 0}


def delayed(per_symbol_bars, per_symbol_pos, funding, costs):
    """Net metrics when every position is executed one bar later than decided."""
    rows = {}
    for s, bars in per_symbol_bars.items():
        pos = [0.0] + per_symbol_pos[s][:-1]
        rows[s] = backtest.apply_costs(backtest.gross(bars, pos), funding.get(s, {}), costs)
    return backtest.metrics(backtest.portfolio(rows))


def placebo(per_symbol_bars, per_symbol_pos, funding, costs, n=60, block=24, seed=17):
    """Distribution of net Sharpe when each symbol's position series is shuffled in 24-bar blocks (same exposure and
    roughly the same turnover, but no timing). Returns the share of placebos at or above the actual Sharpe."""
    rng = random.Random(seed)
    base = backtest.sharpe_ann(backtest.portfolio({s: backtest.apply_costs(backtest.gross(b, per_symbol_pos[s]),
                                                                           funding.get(s, {}), costs)
                                                   for s, b in per_symbol_bars.items()}))
    sims = []
    for _ in range(n):
        rows = {}
        for s, bars in per_symbol_bars.items():
            p = per_symbol_pos[s]
            blocks = [p[k:k + block] for k in range(0, len(p), block)]
            rng.shuffle(blocks)
            q = [x for b in blocks for x in b]
            rows[s] = backtest.apply_costs(backtest.gross(bars, q), funding.get(s, {}), costs)
        sims.append(backtest.sharpe_ann(backtest.portfolio(rows)) or 0.0)
    if base is None:
        return {"actual": None, "p": None, "n": n}
    return {"actual": base, "p": sum(1 for x in sims if x >= base) / n, "n": n,
            "placebo_mean": sum(sims) / n}
