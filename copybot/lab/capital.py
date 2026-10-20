"""Capital model for a hedged funding-carry book (long spot, short perp per coin). DISPLAY AND PLANNING ONLY: it places
nothing, reads no account and knows no key. It answers "what would this strategy need and do with the amount I
actually have", separately from the simulated 10,000 USD paper accounts.

Every figure is derived from the inputs and the stated assumptions; what the lab does not know (per-coin minimum order
sizes, maintenance margin tiers, borrow limits) is returned as UNKNOWN with its consequence, never invented.
"""
from __future__ import annotations

import math

UNKNOWN = "UNKNOWN"
DEFAULTS = {
    "spot_taker_fee": 0.001,          # Binance spot VIP0 taker (the lab's conservative per-leg fee)
    "perp_taker_fee": 0.0005,         # Binance USD-M VIP0 taker
    "slippage": 0.0002,               # per fill, beyond the touch (the paper engine's extra slippage)
    "half_spread": 0.0002,            # per fill (half of the paper engine's expected spread)
    "buffer": 0.20,                   # extra perp margin kept above the initial margin, fraction of the notional
}
SCENARIO_MOVES = (0.10, 0.30, 0.50)   # adverse price rises against the short perp leg
SETTLEMENTS_PER_DAY = 3               # 8-hour funding


class CapitalError(ValueError):
    pass


def _num(name, v, lo=None, hi=None, integer=False):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise CapitalError(f"{name} must be a number, got {v!r}") from None
    if math.isnan(x) or math.isinf(x):
        raise CapitalError(f"{name} must be finite")
    if integer and x != int(x):
        raise CapitalError(f"{name} must be a whole number")
    if lo is not None and x < lo:
        raise CapitalError(f"{name} must be >= {lo}")
    if hi is not None and x > hi:
        raise CapitalError(f"{name} must be <= {hi}")
    return int(x) if integer else x


def plan(amount, coins, leverage=1.0, funding_8h=None, min_order=None, costs=None):
    """The book for `amount` USD split equally over `coins` coins with perp leverage `leverage` (1 = the perp leg is
    fully margined). funding_8h: an assumed settled funding rate per 8 hours (fraction) for the income figures, or None
    (UNKNOWN). min_order: the exchange's minimum order value in USD, or None (UNKNOWN)."""
    amount = _num("amount", amount, lo=0.01)
    coins = _num("coins", coins, lo=1, hi=200, integer=True)
    leverage = _num("leverage", leverage, lo=1, hi=20)
    c = {**DEFAULTS, **(costs or {})}
    for k, v in c.items():
        c[k] = _num(k, v, lo=0, hi=1.0 if k == "buffer" else 0.1)          # fees/fills <= 10 %, buffer <= 100 %
    # capital per coin = spot notional N + perp margin N / leverage + buffer N
    per_unit = 1 + 1 / leverage + c["buffer"]
    per_coin = amount / coins
    notional = per_coin / per_unit
    margin = notional / leverage
    fill_cost = c["slippage"] + c["half_spread"]
    entry = notional * (c["spot_taker_fee"] + c["perp_taker_fee"] + 2 * fill_cost)     # buy spot + sell perp
    round_trip = 2 * entry
    out = {
        "inputs": {"amount_usd": amount, "coins": coins, "leverage": leverage, "funding_8h": funding_8h,
                   "min_order_usd": min_order, "costs": c},
        "per_coin": {"capital_usd": per_coin, "spot_notional_usd": notional, "perp_notional_usd": notional,
                     "perp_margin_usd": margin, "margin_buffer_usd": notional * c["buffer"]},
        "book": {"spot_notional_usd": notional * coins, "perp_notional_usd": notional * coins,
                 "gross_exposure_usd": 2 * notional * coins, "net_price_exposure_usd": 0.0,
                 "capital_tied_usd": amount, "max_share_per_coin": 1 / coins},
        "costs": {"entry_usd_per_coin": entry, "round_trip_usd_per_coin": round_trip,
                  "round_trip_usd_book": round_trip * coins,
                  "round_trip_pct_of_capital": round_trip * coins / amount},
        "unknown": [],
    }
    if min_order is None:
        out["unknown"].append({"item": "minimum order value per coin", "value": UNKNOWN,
                               "consequence": "small books may be rejected by the exchange; check each coin's "
                                              "MIN_NOTIONAL / NOTIONAL filter before trading"})
        out["min_order_ok"] = UNKNOWN
    else:
        mo = _num("min_order", min_order, lo=0)
        out["min_order_ok"] = notional >= mo
        out["max_coins_at_min_order"] = int(amount // (mo * per_unit)) if mo > 0 else coins
    out["unknown"].append({"item": "maintenance margin tiers and exact liquidation price", "value": UNKNOWN,
                           "consequence": "the liquidation distance below is approximate (initial margin + buffer, "
                                          "no maintenance margin or fees)"})
    if funding_8h is None:
        out["income"] = {"per_day_usd_book": UNKNOWN, "break_even_days": UNKNOWN,
                         "note": "give an assumed funding rate to compute income and break-even"}
    else:
        f = _num("funding_8h", funding_8h, lo=-0.05, hi=0.05)
        per_day = notional * coins * f * SETTLEMENTS_PER_DAY
        out["income"] = {"per_day_usd_book": per_day, "per_30d_usd_book": per_day * 30,
                         "apr_on_capital": per_day * 365 / amount,
                         "break_even_days": (round_trip * coins / per_day) if per_day > 0 else None}
    # a price rise r costs the short perp r x N (unrealised, offset by the spot leg) and needs that much margin
    adverse = []
    for r in SCENARIO_MOVES:
        need = notional * r
        have = margin + notional * c["buffer"]
        adverse.append({"price_rise": r, "perp_loss_usd_per_coin": need, "margin_available_usd_per_coin": have,
                        "covered_without_topup": need < have,
                        "spot_gain_usd_per_coin": need, "net_usd_per_coin": 0.0})
    out["liquidation_rise_approx"] = (margin + notional * c["buffer"]) / notional
    out["scenarios"] = {
        "adverse_price": adverse,
        "costs_x2_round_trip_usd_book": 2 * round_trip * coins,
        "funding_at_floor_per_day_usd_book": notional * coins * 0.0001 * SETTLEMENTS_PER_DAY,
        "funding_negative_0_01pct_per_day_usd_book": -notional * coins * 0.0001 * SETTLEMENTS_PER_DAY,
    }
    return out


def sensitivity(amounts=(200, 500, 1000, 5000, 10000), coin_counts=(1, 3, 5, 10), leverage=1.0, funding_8h=0.0005,
                min_order=None):
    """Round-trip cost share and break-even days over a grid of amounts and coin counts."""
    rows = []
    for a in amounts:
        for k in coin_counts:
            p = plan(a, k, leverage, funding_8h, min_order)
            rows.append({"amount_usd": a, "coins": k, "notional_per_coin_usd": p["per_coin"]["spot_notional_usd"],
                         "round_trip_pct_of_capital": p["costs"]["round_trip_pct_of_capital"],
                         "break_even_days": p["income"].get("break_even_days"),
                         "min_order_ok": p["min_order_ok"]})
    return {"rows": rows, "leverage": leverage, "funding_8h": funding_8h}
