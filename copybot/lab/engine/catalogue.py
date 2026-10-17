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
PROTOCOL_VERSION = 2              # research/PROTOCOL_V2.md; v1 experiments (_p1) keep their recorded v1 results

# documented cost model (per unit of turnover, per side); see lab/README.md
COSTS = {"taker_fee": 0.0005,      # Binance USD-M VIP0 taker 0.05 % (published schedule; not re-verified this session)
         "half_spread": 0.0002,    # ESTIMATE for these liquid perps (not measured historically)
         "slippage": 0.0002,       # ESTIMATE allowance
         "funding": "Binance settled funding rates applied to open positions at each settlement (data)"}
COST_HIGH_MULT = 2.0

PLACEBO_P_MAX = 0.10             # v2 pre-validation gate
DSR_MIN = 0.95

PROTOCOL_V1 = {
    "version": 1,
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

PROTOCOL_V2 = {
    **PROTOCOL_V1,
    "version": 2,
    "spec": "research/PROTOCOL_V2.md",
    "selection": ("best net Sharpe on TRAIN (2023-01..2023-08) among the fixed grid; train gate: the selected variant "
                  "must have net Sharpe > 0 AND above the buy-and-hold benchmark's train net Sharpe, else REJECTED "
                  "without reading validation data"),
    "pre_validation": ("on TRAIN before any validation read: exact truncation and poison tests, data quality, and a "
                       "block-shuffled placebo (24-bar blocks, 60 draws, seed 17) with p < 0.10, else REJECTED"),
    "validation": ("frozen variant on VALIDATION (2023-09..2023-12): pass requires net mean daily > 0, one-sided 90 % "
                   "block-bootstrap lower bound > 0 (5-day blocks, 2,000 draws, seed 7), net Sharpe above the "
                   "buy-and-hold benchmark, net total > 0 at 2x costs, deflated Sharpe probability >= 0.95 over the "
                   "batch trial set (all trials up to the batch cutoff plus the batch's own trials; validation waits "
                   "until every batch member finished its cost step)"),
}
PROTOCOLS = {1: PROTOCOL_V1, 2: PROTOCOL_V2}
PROTOCOL = PROTOCOLS[PROTOCOL_VERSION]


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


# ---------- cross-sectional families (PROTOCOL v2) ----------
# Interface: family(bars_by_symbol, funding_by_symbol, params, fit=None) -> {symbol: positions aligned to its bars}.
# Rebalance every Monday 00:00 UTC. A score at rebalance time T uses only closes of bars that closed at or before T
# (bar open ts <= T - 1h). The k lowest / highest scores get +1 / -1 (or the reverse); everything else 0.
def _is_monday_midnight(ts):
    return ts % DAY == 0 and datetime.fromtimestamp(ts, timezone.utc).weekday() == 0


def _ret_over(close, end, start):
    a, b = close.get(start), close.get(end)
    return (b / a - 1) if (a and b) else None


def _daily_returns(close, T, days):
    out = []
    for d in range(days):
        r = _ret_over(close, T - HOUR - d * DAY, T - HOUR - (d + 1) * DAY)
        if r is None:
            return None
        out.append(r)
    return out


def _xs(bars_by, funding_by, p, score, long_low):
    close = {s: {ts: c for ts, _, c in b} for s, b in bars_by.items()}
    times = sorted({ts for b in bars_by.values() for ts, _, _ in b if _is_monday_midnight(ts)})
    k, weights = p["k"], {}
    for T in times:
        sc = {}
        for s in bars_by:
            v = score(close, s, T, p)
            if v is not None:
                sc[s] = v
        w = {s: 0.0 for s in bars_by}
        if len(sc) >= 2 * k:
            order = sorted(sc, key=lambda s: (sc[s], s))
            lo, hi = order[:k], order[-k:]
            for s in lo:
                w[s] = 1.0 if long_low else -1.0
            for s in hi:
                w[s] = -1.0 if long_low else 1.0
        weights[T] = w
    out = {}
    for s, b in bars_by.items():
        pos, cur, j = [], 0.0, 0
        for ts, _, _ in b:
            while j < len(times) and times[j] <= ts:
                cur = weights[times[j]][s]
                j += 1
            pos.append(cur)
        out[s] = pos
    return out


def _score_momentum(close, s, T, p):
    return _ret_over(close[s], T - HOUR, T - HOUR - p["lookback_days"] * DAY)


def _score_max(close, s, T, p):
    r = _daily_returns(close[s], T, p["window_days"])
    return max(r) if r else None


def _score_vol(close, s, T, p):
    c, rs = close[s], []
    for h in range(p["lookback_days"] * 24):
        r = _ret_over(c, T - HOUR - h * HOUR, T - 2 * HOUR - h * HOUR)
        if r is None:
            return None
        rs.append(r)
    return statistics.pstdev(rs)


def _score_beta(close, s, T, p):
    own = _daily_returns(close[s], T, p["lookback_days"])
    others = [_daily_returns(close[x], T, p["lookback_days"]) for x in close]
    if own is None or any(o is None for o in others):
        return None
    mkt = [sum(o[d] for o in others) / len(others) for d in range(len(own))]
    var = statistics.pvariance(mkt)
    if var <= 0:
        return None
    mo, mm = statistics.fmean(own), statistics.fmean(mkt)
    return sum((a - mo) * (b - mm) for a, b in zip(own, mkt)) / len(own) / var


def xs_momentum(bars_by, funding_by, p, fit=None):
    """Long the k strongest, short the k weakest over the lookback (Liu, Tsyvinski & Wu 2022)."""
    return _xs(bars_by, funding_by, p, _score_momentum, long_low=False)


def xs_max_lottery(bars_by, funding_by, p, fit=None):
    """Short the k coins with the highest maximum daily return, long the k lowest (Bali, Cakici & Whitelaw 2011)."""
    return _xs(bars_by, funding_by, p, _score_max, long_low=True)


def xs_low_volatility(bars_by, funding_by, p, fit=None):
    """Long the k least volatile, short the k most volatile (Ang, Hodrick, Xing & Zhang 2006)."""
    return _xs(bars_by, funding_by, p, _score_vol, long_low=True)


def xs_betting_against_beta(bars_by, funding_by, p, fit=None):
    """Long the k lowest-beta, short the k highest-beta coins vs the equal-weight 8-coin market (Frazzini & Pedersen 2014)."""
    return _xs(bars_by, funding_by, p, _score_beta, long_low=True)


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
    "xs_momentum": {
        "family": xs_momentum, "cross_sectional": True, "mechanism_tag": "cross_sectional_momentum", "long_only": False,
        "grid": [{"lookback_days": 7, "k": 2}, {"lookback_days": 28, "k": 2}],
        "hypothesis": "Coins with the highest past returns keep outperforming coins with the lowest, net of costs.",
        "rationale": "Investor attention and slow diffusion of information create relative-strength continuation.",
        "evidence": ["Liu, Tsyvinski & Wu 2022, Journal of Finance, https://doi.org/10.1111/jofi.13119"]},
    "xs_max_lottery": {
        "family": xs_max_lottery, "cross_sectional": True, "mechanism_tag": "lottery_demand_max", "long_only": False,
        "grid": [{"window_days": 7, "k": 2}, {"window_days": 28, "k": 2}],
        "hypothesis": "Coins with extreme recent daily jumps are overpriced lotteries and underperform.",
        "rationale": "Lottery-seeking traders overpay for right-skewed payoffs; the premium is paid back later.",
        "evidence": ["Bali, Cakici & Whitelaw 2011, Journal of Financial Economics, https://doi.org/10.1016/j.jfineco.2010.08.014 (equities)"]},
    "xs_low_volatility": {
        "family": xs_low_volatility, "cross_sectional": True, "mechanism_tag": "low_volatility_anomaly", "long_only": False,
        "grid": [{"lookback_days": 7, "k": 2}, {"lookback_days": 28, "k": 2}],
        "hypothesis": "Low-volatility coins earn higher risk-adjusted returns than high-volatility coins.",
        "rationale": "Leverage-constrained and attention-driven traders bid up volatile assets.",
        "evidence": ["Ang, Hodrick, Xing & Zhang 2006, Journal of Finance, https://doi.org/10.1111/j.1540-6261.2006.00836.x (equities)"]},
    "xs_betting_against_beta": {
        "family": xs_betting_against_beta, "cross_sectional": True, "mechanism_tag": "betting_against_beta",
        "long_only": False, "grid": [{"lookback_days": 28, "k": 2}, {"lookback_days": 56, "k": 2}],
        "hypothesis": "Low-beta coins outperform high-beta coins relative to their market exposure.",
        "rationale": "Funding-constrained investors tilt to high-beta assets instead of using leverage, flattening the security market line.",
        "evidence": ["Frazzini & Pedersen 2014, Journal of Financial Economics, https://doi.org/10.1016/j.jfineco.2013.10.005 (equities)"]},
}

INSTRUMENT_FAMILY = "binance_usdm_perps_8alt"
HORIZON = {"vol_managed_long": "days", "day_of_week": "days", "hour_of_day": "hours", "funding_contrarian": "hours",
           "daily_reversal": "days", "donchian_trend": "days", "xs_momentum": "weeks", "xs_max_lottery": "weeks",
           "xs_low_volatility": "weeks", "xs_betting_against_beta": "weeks"}


def exp_id(template, version=PROTOCOL_VERSION):
    return f"E_{template}_p{version}"
