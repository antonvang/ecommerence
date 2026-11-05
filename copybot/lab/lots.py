"""Lot sizes and minimum notionals for two-leg paper entries (research/PROTOCOL_V3.md amendment 43a).

Read once from Binance exchangeInfo on 2026-11-05 20:14 UTC (USD-M sha256 8ebcae1de486..., spot 7fc78d65830c...).
SIMULATION ONLY: the paper engine trades these quantities against public books; nothing is sent anywhere.
"""
from __future__ import annotations

import math

STEP = {"XAUUSDT": 0.001, "PAXGUSDT.SPOT": 0.0001, "BZUSDT": 0.01, "CLUSDT": 0.01, "QQQUSDT": 0.01,
        "SPYUSDT": 0.01, "ETHUSDT": 0.001, "BTCUSDT": 0.001, "XAGUSDT": 0.001}
MIN_NOTIONAL = {"ETHUSDT": 20.0, "BTCUSDT": 50.0}
TRADFI_MIN = 5.0


def step(symbols):
    """The coarsest step of the given symbols, or None if any is unknown (point 3: BLOCKED)."""
    s = [STEP.get(x) for x in symbols]
    return None if any(v is None for v in s) else max(s)


def round_down(qty, st):
    """qty rounded down to a multiple of st (with a small tolerance for float noise)."""
    return math.floor(qty / st + 1e-9) * st


def min_ok(sym, qty, px):
    return qty * px >= MIN_NOTIONAL.get(sym, TRADFI_MIN)
