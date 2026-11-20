"""P2 candidate strategies, written BEFORE any real return data was looked at.

Each strategy is a pure, stateless function of a point-in-time snapshot (see
`marketdata.snapshot.build_snapshot`): it returns the target position
"LONG" (hold SOL) or "FLAT" (hold USDC). Stateless means the same snapshot
always gives the same answer, so a restart or a replay cannot drift.

The parameter grids below ARE the trial budget in P2_PLAN.md. Adding a
strategy or a grid value after the plan is locked voids the lock.
"""
from __future__ import annotations

import math
from decimal import Decimal

LONG, FLAT = "LONG", "FLAT"


def _closes(snapshot):
    """(end_times, closes) of the contiguous run in the snapshot, as floats."""
    candles = snapshot.get("candles") or []
    return [float(c["end"]) for c in candles], [float(Decimal(str(c["close"]))) for c in candles]


def _log_return(closes, i, minutes):
    return math.log(closes[i] / closes[i - minutes])


# H1 -- time-series momentum -------------------------------------------------

def tsmom_bars(params):
    # as_of can be up to one rebalance period after the boundary that is used
    return params["lookback_min"] + params["rebalance_min"] + 1


def tsmom(snapshot, params):
    """LONG if SOL rose over the lookback, measured only at fixed 4-hour UTC
    boundaries (00, 04, ... 20 h); the position is held until the next boundary.

    Mechanism: slow diffusion of information and trend-following flows in
    crypto (time-series momentum, Moskowitz-Ooi-Pedersen 2012; for crypto
    Liu-Tsyvinski 2021). Rebalancing only every 4 h keeps turnover low enough
    that the round-trip cost (two Jupiter fills) does not dominate.
    """
    ends, closes = _closes(snapshot)
    lookback, every = params["lookback_min"], params["rebalance_min"] * 60
    if not ends:
        return FLAT
    boundary = math.floor(float(snapshot["as_of"]) / every) * every
    # the last bar that closed at or before the boundary
    idx = max((i for i, end in enumerate(ends) if end <= boundary), default=None)
    if idx is None or idx < lookback:
        return FLAT                      # not enough contiguous history: stay out
    return LONG if _log_return(closes, idx, lookback) > 0 else FLAT


# H2 -- short-term reversal after a sharp drop ---------------------------------

def reversal_bars(params):
    return params["vol_window_min"] + params["drop_min"] + params["hold_min"] + 1


def reversal(snapshot, params):
    """LONG for `hold_min` minutes after a 30-minute drop larger than k sigma.

    sigma is the 1-minute log-return std over the previous `vol_window_min`
    minutes, scaled by sqrt(drop_min). Mechanism: forced selling (liquidation
    cascades, stop runs) overshoots and liquidity providers are paid to take
    the other side (short-term reversal; Nagel 2012 "Evaporating liquidity").
    Stateless: LONG iff the drop condition was true at any of the last
    `hold_min` bars. The condition can stay true for up to `drop_min` bars
    after the drop ends (the window still contains it), so a position can last
    up to drop_min + hold_min minutes after the last falling bar.
    """
    _, closes = _closes(snapshot)
    k, drop, hold, window = params["k"], params["drop_min"], params["hold_min"], params["vol_window_min"]
    n = len(closes)
    if n < reversal_bars(params):
        return FLAT
    first = n - hold - drop - window - 1          # only the tail of the snapshot matters
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(first + 1, n)]  # returns[j] ends at bar first+j+1
    s1, s2 = [0.0], [0.0]                          # prefix sums for O(1) window mean/variance
    for r in returns:
        s1.append(s1[-1] + r)
        s2.append(s2[-1] + r * r)
    for i in range(n - hold, n):                   # bars that could still be held
        a, b = i - drop - window - first - 1, i - drop - first - 1   # vol window, before the drop
        mean = (s1[b] - s1[a]) / window
        variance = max(0.0, (s2[b] - s2[a] - window * mean * mean) / (window - 1))
        sigma = math.sqrt(variance)
        if sigma > 0 and _log_return(closes, i, drop) < -k * sigma * math.sqrt(drop):
            return LONG
    return FLAT


# Registry: name -> (function, bars_needed(params), parameter grid). ---------

STRATEGIES = {
    "tsmom": (tsmom, tsmom_bars, [
        {"lookback_min": 240, "rebalance_min": 240},
        {"lookback_min": 1440, "rebalance_min": 240},
    ]),
    "reversal": (reversal, reversal_bars, [
        {"k": 2.0, "drop_min": 30, "hold_min": 60, "vol_window_min": 360},
        {"k": 3.0, "drop_min": 30, "hold_min": 60, "vol_window_min": 360},
    ]),
}

TRIAL_BUDGET = sum(len(grid) for _, _, grid in STRATEGIES.values())   # = 4
