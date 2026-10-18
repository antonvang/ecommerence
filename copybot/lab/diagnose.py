"""Non-decisional research diagnostics (research/PROTOCOL_V3.md amendment 5).

Learns from finished experiments: analyses the daily net series that the validation step already recorded
(validate.json, verified against its SHA-256 before use). Reads no market data and no new split, writes only under
artifacts/_diagnostic/, changes no result, trial, transition or verdict. Pure, deterministic arithmetic; the rules that
turn numbers into lessons are fixed below and never feed a gate.
"""
from __future__ import annotations

import math
import statistics

BEST_DAYS = 5
CONCENTRATED = 0.5        # the best 5 days carry more than half of all positive net
LOW_ACTIVITY = 0.3        # a non-zero net return (a position) on fewer than 30 % of days


def _drawdown(r):
    """(deepest drawdown, longest stretch of days below the previous peak)."""
    peak = cum = 0.0
    deepest, longest, run = 0.0, 0, 0
    for x in r:
        cum += x
        if cum >= peak:
            peak, run = cum, 0
        else:
            run += 1
            longest = max(longest, run)
            deepest = max(deepest, peak - cum)
    return deepest, longest


def series(r, periods_per_year=365):
    """Stability, concentration, drawdown and activity (share of days with a non-zero net) of a daily net series."""
    n = len(r)
    if n == 0:
        return {"n": 0}
    sd = statistics.stdev(r) if n > 1 else 0.0
    mean = statistics.mean(r)
    t, h = n // 3, n // 2
    thirds = [sum(r[:t]), sum(r[t:2 * t]), sum(r[2 * t:])] if t else []
    halves = [sum(r[:h]), sum(r[h:])] if h else []
    pos = sorted((x for x in r if x > 0), reverse=True)
    pos_total = sum(pos)
    deepest, longest = _drawdown(r)
    return {"n": n, "total": sum(r), "mean": mean, "sd": sd,
            "sharpe_ann": (mean / sd * math.sqrt(periods_per_year)) if sd else None,
            "thirds": thirds, "positive_thirds": sum(1 for x in thirds if x > 0),
            "halves": halves, "positive_halves": sum(1 for x in halves if x > 0),
            "best_days_share": (sum(pos[:BEST_DAYS]) / pos_total) if pos_total > 0 else None,
            "max_drawdown": deepest, "longest_drawdown_days": longest,
            "active_days": sum(1 for x in r if x != 0) / n, "worst_day": min(r), "best_day": max(r)}


def lessons(s, gates):
    """Fixed, deterministic reading of the numbers (for learning only; never a gate)."""
    out = []
    failed = sorted(k for k, ok in (gates or {}).items() if not ok)
    if s.get("n", 0) == 0:
        return ["no recorded validation series"], failed
    if s["total"] <= 0:
        out.append("no edge: net total <= 0 on validation")
    elif s["positive_thirds"] < 2:
        out.append("unstable: positive in fewer than 2 of 3 chronological thirds")
    if s.get("best_days_share") is not None and s["best_days_share"] > CONCENTRATED:
        out.append(f"concentrated: the best {BEST_DAYS} days carry {s['best_days_share']:.0%} of positive net")
    if s["active_days"] < LOW_ACTIVITY:
        out.append(f"rarely active: a non-zero net on only {s['active_days']:.0%} of days (small effective sample)")
    if any("buy-and-hold" in k for k in failed):
        out.append("beaten by buy-and-hold over the same period")
    if failed and all("deflated" in k or "luck" in k for k in failed):
        out.append("failed only the luck check (multiple testing)")
    if not out:
        out.append("no single weakness flagged by these rules")
    return out, failed
