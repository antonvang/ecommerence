"""Adversarial checks: try to break a result before anyone trusts it.

Gating (must pass): look-ahead truncation and future-poison tests are exact; data quality is OK.
Reported flags (inform the decision, documented in the report): one-bar extra delay, placebo with block-shuffled
positions, and the neighbourhood of the selected grid variant.
"""
from __future__ import annotations

import math
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


HOUR, DAY = 3600, 86400
BUNDLE_KEYS = {"volume", "taker", "metrics", "dvol", "stable", "rates", "cm"}


def _is_bundle(x):
    return isinstance(x, dict) and bool(x) and set(x) <= BUNDLE_KEYS


def _scale(v, k):
    if isinstance(v, dict):
        return {kk: (vv * k if isinstance(vv, float) and kk != "rows" else vv) for kk, vv in v.items()}
    return v * k


def cut_bundle(b, cut, poison=False):
    """Data a decision at time `cut` may not see: hourly values from bars opening at or after `cut`, daily values of days
    not fully closed by `cut`. Truncate (drop them) or poison (multiply them by 1000)."""
    def hourly(series):
        if poison:
            return {ts: (q * 1000 if ts >= cut else q) for ts, q in series.items()}
        return {ts: q for ts, q in series.items() if ts < cut}

    def daily(series):
        if poison:
            return {d: (_scale(v, 1000) if d + DAY > cut else v) for d, v in series.items()}
        return {d: v for d, v in series.items() if d + DAY <= cut}

    out = {}
    for k, v in b.items():
        if k in ("volume", "taker"):
            out[k] = {s: hourly(x) for s, x in v.items()}
        elif k in ("metrics", "dvol"):
            out[k] = {s: daily(x) for s, x in v.items()}
        elif k in ("stable", "rates"):
            out[k] = daily(v)
        elif k == "cm":
            out[k] = {m: {s: daily(x) for s, x in per.items()} for m, per in v.items()}
    return out


def _call(family, bars_by, funding_by, params, volume_by):
    return family(bars_by, funding_by, params, None, volume_by) if volume_by is not None else family(bars_by, funding_by, params)


def truncation_test_xs(family, bars_by, funding_by, params, samples=20, seed=11, volume_by=None):
    """Cross-sectional: cut every symbol at the same timestamp; positions up to the cut must not change."""
    full = _call(family, bars_by, funding_by, params, volume_by)
    ref = min(bars_by, key=lambda s: len(bars_by[s]))
    rng = random.Random(seed)
    n = len(bars_by[ref])
    cuts = sorted(rng.sample(range(1, n), min(samples, n - 1))) if n > 2 else []
    bad = 0
    for i in cuts:
        cut = bars_by[ref][i][0]
        part = _call(family, {s: [x for x in b if x[0] <= cut] for s, b in bars_by.items()},
                     {s: {k: v for k, v in f.items() if k <= cut} for s, f in funding_by.items()}, params,
                     cut_bundle(volume_by, cut) if _is_bundle(volume_by) else
                     ({s: {k: q for k, q in v.items() if k <= cut} for s, v in volume_by.items()} if volume_by else None))
        for s, b in bars_by.items():
            m = sum(1 for x in b if x[0] <= cut)
            if any(abs(part[s][j] - full[s][j]) > 1e-12 for j in range(m)):
                bad += 1
                break
    return {"checked": len(cuts), "mismatches": bad, "ok": bad == 0}


def poison_test_xs(family, bars_by, funding_by, params, seed=13, volume_by=None):
    """Cross-sectional: multiply every symbol's prices after a common cut by 1000; earlier positions must not change."""
    ref = min(bars_by, key=lambda s: len(bars_by[s]))
    if len(bars_by[ref]) < 10:
        return {"ok": True, "checked": 0}
    rng = random.Random(seed)
    i = rng.randrange(len(bars_by[ref]) // 4, 3 * len(bars_by[ref]) // 4)
    cut = bars_by[ref][i][0]
    pb = {s: [(ts, o, c) if ts <= cut else (ts, o * 1000, c * 1000) for ts, o, c in b] for s, b in bars_by.items()}
    pf = {s: {k: (v if k <= cut else 1.0) for k, v in f.items()} for s, f in funding_by.items()}
    if _is_bundle(volume_by):
        pv = cut_bundle(volume_by, cut, poison=True)
    else:
        pv = {s: {k: (q if k <= cut else q * 1000) for k, q in v.items()} for s, v in volume_by.items()} if volume_by else None
    a, b2 = _call(family, bars_by, funding_by, params, volume_by), _call(family, pb, pf, params, pv)
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


def placebo_circular(per_symbol_bars, per_symbol_pos, funding, costs, n=60, min_days=7, seed=17, offset=3600):
    """Distribution of net Sharpe when each symbol's MARKET (its bar prices and settled funding) is shifted circularly
    by a random whole number of days in [min_days, length - min_days) while its positions stay exactly as they are:
    the same turnover, exposure and costs, only out of step with the market (amendment 11d). Sharpe is taken over
    decision periods starting at `offset` seconds after 00:00 UTC (01:00, the families' decision time). Returns the
    share of placebos at or above the actual Sharpe."""
    rng = random.Random(seed)

    def shifted(s, bars, k_days):
        ts = [b[0] for b in bars]
        n = len(bars)
        k = (k_days * 24) % n
        nb = [(ts[i],) + tuple(bars[(i + k) % n][1:]) for i in range(n)]
        f = funding.get(s, {})
        ft = sorted(f)
        if not ft:
            return nb, {}
        step = k_days * 86400
        span = ft[-1] - ft[0] + 8 * 3600
        nf = {t: f.get(ft[0] + ((t - ft[0] + step) % span), 0.0) for t in ft}
        return nb, nf

    def sharpe(bars_by, fund_by):
        """Net Sharpe over decision periods (UTC days shifted by `offset`), so a period's switch and the settlements
        its decision used never fall in the same period by construction."""
        rows = backtest.portfolio({s: backtest.apply_costs(backtest.gross(b, per_symbol_pos[s]), fund_by.get(s, {}),
                                                           costs) for s, b in bars_by.items()})
        per = {}
        for r in rows:
            per[(r[0] - offset) // 86400] = per.get((r[0] - offset) // 86400, 0.0) + r[7]
        x = [per[k] for k in sorted(per)]
        if len(x) < 2:
            return None
        m = math.fsum(x) / len(x)
        sd = math.sqrt(math.fsum((v - m) ** 2 for v in x) / (len(x) - 1))
        return m / sd * math.sqrt(365) if sd > 0 else None
    base, sims = sharpe(per_symbol_bars, funding), []
    days = min(len(b) for b in per_symbol_bars.values()) // 24
    for _ in range(n):
        bb, ff = {}, {}
        for s, b in per_symbol_bars.items():
            k = rng.randrange(min_days, days - min_days) if days > 2 * min_days else 0
            bb[s], ff[s] = shifted(s, b, k)
        sims.append(sharpe(bb, ff) or 0.0)
    if base is None:
        return {"actual": None, "p": None, "n": n}
    return {"actual": base, "p": sum(1 for x in sims if x >= base) / n, "n": n, "placebo_mean": sum(sims) / n,
            "method": "market shifted by whole days; positions unchanged"}


def delayed_by(per_symbol_bars, per_symbol_pos, funding, costs, bars=24):
    """Net metrics when every position is executed `bars` bars later than decided."""
    rows = {}
    for s, b in per_symbol_bars.items():
        pos = [0.0] * bars + per_symbol_pos[s][:-bars] if bars else per_symbol_pos[s]
        rows[s] = backtest.apply_costs(backtest.gross(b, pos), funding.get(s, {}), costs)
    return backtest.metrics(backtest.portfolio(rows))
