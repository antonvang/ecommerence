"""Strategy catalogue and the pre-registered screening protocol (Mission 6).

Each template is one hypothesis family with an economic rationale, a small FIXED grid, a benchmark and a cost model.
Templates may only run after a logged template approval (`python -m lab approve-template`). Their grids are never
widened after results are seen: a new grid is a new template version and a new experiment.

Position convention: positions[i] is the exposure held during bar i. It is decided at the close of bar i-1, using
bars[0..i-1] and funding rates settled before bar i's open. Exposure is in [-1, 1] (no leverage).
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone

DAY, HOUR = 86400, 3600
PROTOCOL_VERSION = 1

# documented cost model (per unit of turnover, per side); see lab/README.md
COSTS = {"taker_fee": 0.0005,      # Binance USD-M VIP0 taker 0.05 % (published schedule; not re-verified this session)
         "half_spread": 0.0002,    # ESTIMATE for these liquid perps (not measured historically)
         "slippage": 0.0002,       # ESTIMATE allowance
         "funding": "Binance settled funding rates applied to open positions at each settlement (data)"}
COST_HIGH_MULT = 2.0

PROTOCOL = {
    "version": PROTOCOL_VERSION,
    "selection": "best net Sharpe on TRAIN (2023-01..2023-08) among the fixed grid; reject if no variant has net Sharpe > 0",
    "validation": ("frozen variant on VALIDATION (2023-09..2023-12): pass requires net mean daily > 0, one-sided 90 % "
                   "block-bootstrap lower bound > 0 (5-day blocks, 2,000 draws, fixed seed), net Sharpe above the "
                   "buy-and-hold benchmark, net total > 0 at 2x costs, deflated Sharpe probability >= 0.95 given all "
                   "trials recorded so far"),
    "adversarial": "look-ahead truncation and future-poison tests must be exact; data coverage >= 99 % with no duplicates",
    "holdout": ("2024 only after a human-approved VALIDATION transition; pass requires net mean > 0, one-sided 95 % lower "
                "bound > 0 and net Sharpe above buy-and-hold; otherwise REJECTED"),
    "paper": "only VALIDATED experiments, only after a human approval; simulated orders only",
}


def _ret(bars, i):
    return bars[i][2] / bars[i - 1][2] - 1 if i > 0 else 0.0


def _is_midnight(ts):
    return ts % DAY == 0


# ---------- families ----------
def vol_managed(bars, funding, p, fit=None):
    """Long exposure = min(1, target_vol / realised vol), rebalanced at 00:00 UTC (Moreira & Muir 2017)."""
    L, pos, cur = int(p["lookback_days"] * 24), [0.0] * len(bars), 0.0
    for i in range(len(bars)):
        if _is_midnight(bars[i][0]) and i > L:
            r = [_ret(bars, j) for j in range(i - L, i)]
            vol = statistics.pstdev(r) * math.sqrt(24 * 365)
            cur = min(1.0, p["target_vol"] / vol) if vol > 0 else 0.0
        pos[i] = cur
    return pos


def day_of_week(bars, funding, p, fit=None):
    """Calendar exposure by UTC weekday (Caporale & Plastun 2019). Calendar dates are known in advance."""
    out = []
    for ts, _, _ in bars:
        wd = datetime.fromtimestamp(ts, timezone.utc).weekday()   # 5 = Sat, 6 = Sun
        weekend = wd >= 5
        out.append(0.0 if (weekend if p["mode"] == "flat_weekend" else not weekend) else 1.0)
    return out


def fit_hour_of_day(bars, p):
    """Fit on TRAIN only: the k UTC hours with the highest mean return."""
    by = {h: [] for h in range(24)}
    for i in range(1, len(bars)):
        by[datetime.fromtimestamp(bars[i][0], timezone.utc).hour].append(_ret(bars, i))
    means = {h: (statistics.mean(v) if v else 0.0) for h, v in by.items()}
    return {"hours": sorted(sorted(means, key=lambda h: -means[h])[:p["k"]])}


def hour_of_day(bars, funding, p, fit=None):
    hours = set((fit or {}).get("hours", []))
    return [1.0 if datetime.fromtimestamp(ts, timezone.utc).hour in hours else 0.0 for ts, _, _ in bars]


def funding_contrarian(bars, funding, p, fit=None):
    """After each funding settlement: short when the settled rate is in the top tail of the trailing 90 settlements,
    long when in the bottom tail; hold until the next settlement (crowding, Schmeling-Schrimpf-Todorov BIS WP 1087)."""
    settled = sorted(funding.items())
    pos, cur, k, hist = [0.0] * len(bars), 0.0, 0, []
    for i in range(len(bars)):
        ts = bars[i][0]
        new = False
        while k < len(settled) and settled[k][0] < ts:            # settled strictly before this bar opens
            hist.append(settled[k][1])
            k += 1
            new = True
        if new and len(hist) > 30:
            past = sorted(hist[-91:-1])
            hi, lo = past[int(p["q"] * (len(past) - 1))], past[int((1 - p["q"]) * (len(past) - 1))]
            r = hist[-1]
            cur = -1.0 if r > hi else (1.0 if r < lo else 0.0)
        pos[i] = cur
    return pos


def daily_reversal(bars, funding, p, fit=None):
    """At 00:00 UTC: take the opposite side of an extreme previous-day move for the next 24 h (Nagel 2012)."""
    pos, cur, daily = [0.0] * len(bars), 0.0, []
    for i in range(len(bars)):
        if _is_midnight(bars[i][0]) and i >= 25:                  # i - 25 >= 0: never wrap to bars[-1] (look-ahead)
            d = bars[i - 1][2] / bars[i - 25][2] - 1
            if len(daily) >= 30:
                sd = statistics.pstdev(daily[-30:])
                z = d / sd if sd > 0 else 0.0
                cur = 1.0 if z < -p["z"] else (-1.0 if z > p["z"] else 0.0)
            daily.append(d)
        pos[i] = cur
    return pos


def donchian_trend(bars, funding, p, fit=None):
    """Daily breakout trend following (Hurst, Ooi & Pedersen 2017)."""
    pos, cur, closes = [0.0] * len(bars), 0.0, []
    for i in range(len(bars)):
        if _is_midnight(bars[i][0]) and i >= 1:
            closes.append(bars[i - 1][2])
            n = p["days"]
            if len(closes) > n:
                past = closes[-n - 1:-1]
                c = closes[-1]
                cur = 1.0 if c > max(past) else (-1.0 if c < min(past) else cur)
        pos[i] = cur
    return pos


TEMPLATES = {
    "vol_managed_long": {
        "family": vol_managed, "mechanism_tag": "volatility_managed_exposure", "long_only": True,
        "grid": [{"lookback_days": 7, "target_vol": 0.5}, {"lookback_days": 30, "target_vol": 0.5}],
        "hypothesis": "Scaling long exposure inversely to recent realised volatility raises net risk-adjusted returns versus buy-and-hold.",
        "rationale": "Volatility clusters while expected returns do not rise proportionally, so de-risking in turbulent periods improves Sharpe.",
        "evidence": ["Moreira & Muir 2017, Journal of Finance, https://doi.org/10.1111/jofi.12513 (equities)"]},
    "day_of_week": {
        "family": day_of_week, "mechanism_tag": "calendar_day_of_week", "long_only": True,
        "grid": [{"mode": "flat_weekend"}, {"mode": "weekend_only"}],
        "hypothesis": "Crypto returns differ by weekday enough that calendar exposure beats buy-and-hold after costs.",
        "rationale": "Weekend liquidity is thinner (traditional venues and many market makers closed), so price formation differs.",
        "evidence": ["Caporale & Plastun 2019, Finance Research Letters, https://doi.org/10.1016/j.frl.2018.11.012"]},
    "hour_of_day": {
        "family": hour_of_day, "fit": fit_hour_of_day, "mechanism_tag": "intraday_seasonality", "long_only": True,
        "grid": [{"k": 3}, {"k": 6}],
        "hypothesis": "Hours with the highest mean return in TRAIN keep a positive edge out of sample.",
        "rationale": "Funding settlements (00/08/16 UTC) and regional session opens may create recurring flows.",
        "evidence": ["hypothesis only: no peer-reviewed source verified for crypto hour-of-day effects"]},
    "funding_contrarian": {
        "family": funding_contrarian, "mechanism_tag": "funding_crowding_contrarian", "long_only": False,
        "grid": [{"q": 0.9}, {"q": 0.95}],
        "hypothesis": "Extreme funding rates mark crowded positioning that subsequently unwinds against the crowd.",
        "rationale": "Trend-chasing retail pays high funding; scarce arbitrage capital lets crowding build and then reverse.",
        "evidence": ["Schmeling, Schrimpf & Todorov 2023, BIS Working Paper 1087, https://www.bis.org/publ/work1087.htm"]},
    "daily_reversal": {
        "family": daily_reversal, "mechanism_tag": "short_term_reversal_liquidity", "long_only": False,
        "grid": [{"z": 1.5}, {"z": 2.0}],
        "hypothesis": "After an extreme daily move, the next day partially reverses by more than costs.",
        "rationale": "Liquidity providers are compensated for absorbing order-flow imbalances; reversals pay that compensation.",
        "evidence": ["Nagel 2012, Review of Financial Studies, https://doi.org/10.1093/rfs/hhs066 (equities)"]},
    "donchian_trend": {
        "family": donchian_trend, "mechanism_tag": "time_series_momentum", "long_only": False,
        "grid": [{"days": 20}, {"days": 55}],
        "hypothesis": "Daily breakout trend following earns positive net returns.",
        "rationale": "Under-reaction and herding create trends (time-series momentum).",
        "evidence": ["Hurst, Ooi & Pedersen 2017, Journal of Portfolio Management, https://doi.org/10.3905/jpm.2017.44.1.015"]},
}

INSTRUMENT_FAMILY = "binance_usdm_perps_8alt"
HORIZON = {"vol_managed_long": "days", "day_of_week": "days", "hour_of_day": "hours", "funding_contrarian": "hours",
           "daily_reversal": "days", "donchian_trend": "days"}


def exp_id(template):
    return f"E_{template}_p{PROTOCOL_VERSION}"
