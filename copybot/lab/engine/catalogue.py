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
PROTOCOL_V3 = {
    **PROTOCOL_V2,
    "version": 3,
    "spec": "research/PROTOCOL_V3.md",
    "windows": "train 2022-01..2023-06, validation 2023-07..2023-12, holdout 2024 (BTC/ETH/SOL excluded), 2025+ reserved",
    "selection": PROTOCOL_V2["selection"].replace("TRAIN (2023-01..2023-08)", "TRAIN (2022-01..2023-06)"),
    "validation": PROTOCOL_V2["validation"].replace("VALIDATION (2023-09..2023-12)", "VALIDATION (2023-07..2023-12)"),
}
PROTOCOLS = {1: PROTOCOL_V1, 2: PROTOCOL_V2, 3: PROTOCOL_V3}
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


def _apply(bars_by, weights):
    """Positions per symbol from {decision ts: {symbol: weight}}: each bar holds the latest decision at or before it."""
    times = sorted(weights)
    out = {}
    for s, b in bars_by.items():
        pos, cur, j = [], 0.0, 0
        for ts, _, _ in b:
            while j < len(times) and times[j] <= ts:
                cur = weights[times[j]].get(s, 0.0)
                j += 1
            pos.append(cur)
        out[s] = pos
    return out


def _midnights(bars_by):
    return sorted({ts for b in bars_by.values() for ts, _, _ in b if ts % DAY == 0})


def _xs(bars_by, funding_by, p, score, long_low, volume_by=None, extra=None):
    close = {s: {ts: c for ts, _, c in b} for s, b in bars_by.items()}
    ctx = {"dv": _daily_dollar_volume(volume_by)} if volume_by else {}
    ctx["extra"] = extra or {}
    times = sorted({ts for b in bars_by.values() for ts, _, _ in b if _is_monday_midnight(ts)})
    k, weights = p["k"], {}
    for T in times:
        sc = {}
        for s in bars_by:
            v = score(close, s, T, p, ctx)
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


def _score_momentum(close, s, T, p, ctx=None):
    return _ret_over(close[s], T - HOUR, T - HOUR - p["lookback_days"] * DAY)


def _score_max(close, s, T, p, ctx=None):
    r = _daily_returns(close[s], T, p["window_days"])
    return max(r) if r else None


def _score_vol(close, s, T, p, ctx=None):
    c, rs = close[s], []
    for h in range(p["lookback_days"] * 24):
        r = _ret_over(c, T - HOUR - h * HOUR, T - 2 * HOUR - h * HOUR)
        if r is None:
            return None
        rs.append(r)
    return statistics.pstdev(rs)


def _score_beta(close, s, T, p, ctx=None):
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


def _daily_dollar_volume(volume_by):
    """{symbol: {UTC day start ts: summed hourly quote volume}}."""
    out = {}
    for s, v in (volume_by or {}).items():
        d = {}
        for ts, q in v.items():
            k = ts - ts % DAY
            d[k] = d.get(k, 0.0) + q
        out[s] = d
    return out


def _market_daily(close, T, days):
    """Equal-weight market daily returns over `days` days before T, or None when any symbol lacks data."""
    per = [_daily_returns(c, T, days) for c in close.values()]
    if any(r is None for r in per):
        return None, None
    return per, [sum(r[d] for r in per) / len(per) for d in range(days)]


def _score_illiquidity(close, s, T, p, ctx):
    r = _daily_returns(close[s], T, p["lookback_days"])
    dv = ctx["dv"].get(s, {})
    vols = [dv.get(T - (d + 1) * DAY) for d in range(p["lookback_days"])]
    if r is None or any(not v for v in vols):
        return None
    return statistics.fmean(abs(a) / v for a, v in zip(r, vols))


def _score_high_volume(close, s, T, p, ctx):
    dv, f = ctx["dv"].get(s, {}), p["formation_days"]
    recent = [dv.get(T - (d + 1) * DAY) for d in range(f)]
    before = [dv.get(T - (d + 1) * DAY) for d in range(f, f + 49)]
    if any(v is None for v in recent + before) or not sum(before):
        return None
    return statistics.fmean(recent) / statistics.fmean(before)


def _score_downside_beta(close, s, T, p, ctx=None):
    own = _daily_returns(close[s], T, p["lookback_days"])
    _, mkt = _market_daily(close, T, p["lookback_days"])
    if own is None or mkt is None:
        return None
    mu = statistics.fmean(mkt)
    idx = [i for i, m in enumerate(mkt) if m < mu]
    if len(idx) < 5:
        return None
    o, m = [own[i] for i in idx], [mkt[i] for i in idx]
    var = statistics.pvariance(m)
    if var <= 0:
        return None
    mo, mm = statistics.fmean(o), statistics.fmean(m)
    return sum((a - mo) * (b - mm) for a, b in zip(o, m)) / len(o) / var


def _score_coskewness(close, s, T, p, ctx=None):
    own = _daily_returns(close[s], T, p["lookback_days"])
    _, mkt = _market_daily(close, T, p["lookback_days"])
    if own is None or mkt is None:
        return None
    mi, mm = statistics.fmean(own), statistics.fmean(mkt)
    si, sm2 = statistics.pstdev(own), statistics.fmean((b - mm) ** 2 for b in mkt)
    if si <= 0 or sm2 <= 0:
        return None
    return statistics.fmean((a - mi) * (b - mm) ** 2 for a, b in zip(own, mkt)) / (si * sm2)


def _score_near_high(close, s, T, p, ctx=None):
    c, last = close[s], close[s].get(T - HOUR)
    hist = [c.get(T - HOUR - h * HOUR) for h in range(p["lookback_days"] * 24)]
    if last is None or any(v is None for v in hist):
        return None
    return last / max(hist)


def xs_illiquidity(bars_by, funding_by, p, fit=None, volume_by=None):
    """Long the k most illiquid, short the k most liquid coins by Amihud ILLIQ (Amihud 2002)."""
    return _xs(bars_by, funding_by, p, _score_illiquidity, long_low=False, volume_by=volume_by)


def xs_high_volume(bars_by, funding_by, p, fit=None, volume_by=None):
    """Long the k coins with the largest abnormal dollar volume, short the k smallest (Gervais et al. 2001)."""
    return _xs(bars_by, funding_by, p, _score_high_volume, long_low=False, volume_by=volume_by)


def xs_downside_beta(bars_by, funding_by, p, fit=None, volume_by=None):
    """Long the k highest downside-beta coins, short the k lowest (Ang, Chen & Xing 2006)."""
    return _xs(bars_by, funding_by, p, _score_downside_beta, long_low=False)


def xs_coskewness(bars_by, funding_by, p, fit=None, volume_by=None):
    """Long the k most negatively coskewed coins, short the k most positive (Harvey & Siddique 2000)."""
    return _xs(bars_by, funding_by, p, _score_coskewness, long_low=True)


def xs_near_high(bars_by, funding_by, p, fit=None, volume_by=None):
    """Long the k coins nearest their L-day high, short the k furthest (George & Hwang 2004, adapted window)."""
    return _xs(bars_by, funding_by, p, _score_near_high, long_low=False)


def turn_of_month(bars, funding, p, fit=None):
    """Long from 00:00 UTC of the last B days of a month through the first A days of the next (Lakonishok & Smidt 1988)."""
    out = []
    for ts, _, _ in bars:
        d = datetime.fromtimestamp(ts, timezone.utc)
        nxt = datetime(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1, tzinfo=timezone.utc)
        days_left = (nxt - d.replace(hour=0, minute=0, second=0, microsecond=0)).days     # 1 on the last day
        out.append(1.0 if (d.day <= p["days_after"] or days_left <= p["days_before"]) else 0.0)
    return out


def btc_lead_lag(bars_by, funding_by, p, fit=None, volume_by=None):
    """Daily: BTC's previous-day return beyond +-x sets the next day's position in every other coin (Hou 2007, adapted)."""
    btc = {ts: c for ts, _, c in bars_by.get("BTCUSDT", [])}
    out = {}
    for s, b in bars_by.items():
        pos, cur = [], 0.0
        for ts, _, _ in b:
            if ts % DAY == 0:
                r = _ret_over(btc, ts - HOUR, ts - HOUR - DAY)
                cur = 0.0 if (s == "BTCUSDT" or r is None) else (1.0 if r > p["x"] else (-1.0 if r < -p["x"] else 0.0))
            pos.append(cur)
        out[s] = pos
    return out


# ---------- PROTOCOL v3 families (research/PROTOCOL_V3.md). A daily value for day D is usable from D + 1 day. ----------
def _metric(ctx, s, day, key):
    v = ((ctx["extra"].get("metrics") or {}).get(s) or {}).get(day)
    if not v or v.get("rows", 0) < 200 or v.get(key) is None:
        return None
    return v[key]


def _score_oi_growth(close, s, T, p, ctx):
    now, then = _metric(ctx, s, T - DAY, "oi"), _metric(ctx, s, T - (p["lookback_days"] + 1) * DAY, "oi")
    return (now / then - 1) if (now and then) else None


def _score_oi_confirmed(close, s, T, p, ctx):
    r = _ret_over(close[s], T - HOUR, T - HOUR - p["lookback_days"] * DAY)
    g = _score_oi_growth(close, s, T, p, ctx)
    if r is None or g is None:
        return None
    return r if g > 0 else -r


def _score_smart_vs_crowd(close, s, T, p, ctx):
    vals = []
    for k in range(1, p["lookback_days"] + 1):
        top, acct = _metric(ctx, s, T - k * DAY, "top"), _metric(ctx, s, T - k * DAY, "acct")
        if top and acct:
            vals.append(math.log(top) - math.log(acct))
    return statistics.fmean(vals) if len(vals) >= p["lookback_days"] - 1 else None


def _taker_daily(ctx):
    if "taker_daily" not in ctx:
        tk, vol = ctx["extra"].get("taker") or {}, ctx["extra"].get("volume") or {}
        out = {}
        for s, series in tk.items():
            num, den = {}, {}
            for ts, q in series.items():
                d = ts - ts % DAY
                num[d] = num.get(d, 0.0) + q
            for ts, q in (vol.get(s) or {}).items():
                d = ts - ts % DAY
                den[d] = den.get(d, 0.0) + q
            out[s] = {d: num[d] / den[d] for d in num if den.get(d)}
        ctx["taker_daily"] = out
    return ctx["taker_daily"]


def _score_taker(close, s, T, p, ctx):
    d = _taker_daily(ctx).get(s, {})
    f = p["formation_days"]
    recent = [d.get(T - k * DAY) for k in range(1, f + 1)]
    before = [d.get(T - k * DAY) for k in range(f + 1, f + 61)]
    if any(v is None for v in recent + before):
        return None
    return statistics.fmean(recent) - statistics.fmean(before)


def oi_growth(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Long the 5 coins with the fastest open-interest growth, short the 5 slowest (Hong & Yogo 2012)."""
    return _xs(bars_by, funding_by, p, _score_oi_growth, long_low=False, extra=extra)


def oi_confirmed_return(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Price moves confirmed by new open interest continue; moves on falling open interest do not (Bessembinder & Seguin 1993)."""
    return _xs(bars_by, funding_by, p, _score_oi_confirmed, long_low=False, extra=extra)


def smart_vs_crowd(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Follow top traders when they are more bullish than all accounts (Wang 2003)."""
    return _xs(bars_by, funding_by, p, _score_smart_vs_crowd, long_low=False, extra=extra)


def taker_pressure(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Coins with unusually aggressive buying keep rising (Chordia & Subrahmanyam 2004), daily and cross-sectional."""
    return _xs(bars_by, funding_by, p, _score_taker, long_low=False, extra=extra)


def _q(values, frac):
    s = sorted(values)
    return s[math.floor((len(s) - 1) * frac)]


def leverage_cycle(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Hold the whole universe except when leverage builds faster than prices (Geanakoplos 2010)."""
    metrics = (extra or {}).get("metrics") or {}
    close = {s: {ts: c for ts, _, c in b} for s, b in bars_by.items()}
    L, hist, weights, cur = p["lookback_days"], [], {}, 1.0
    for T in _midnights(bars_by):
        now, then, rets = 0.0, 0.0, []
        for s in bars_by:
            a = (metrics.get(s) or {}).get(T - DAY) or {}
            b = (metrics.get(s) or {}).get(T - (L + 1) * DAY) or {}
            if a.get("rows", 0) >= 200 and b.get("rows", 0) >= 200 and a.get("oi") and b.get("oi"):
                now += a["oi"]
                then += b["oi"]
            r = _ret_over(close[s], T - HOUR, T - HOUR - L * DAY)
            if r is not None:
                rets.append(r)
        if then > 0 and rets:
            G = math.log(now / then) - math.log(1 + statistics.fmean(rets))
            if len(hist) >= 60:
                cur = 0.0 if G >= _q(hist[-90:], 2 / 3) else 1.0
            else:
                cur = 1.0
            hist.append(G)
        weights[T] = {s: cur for s in bars_by}
    return _apply(bars_by, weights)


def vrp_timing(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Hold BTC/ETH when implied volatility is high relative to realised volatility (Bollerslev, Tauchen & Zhou 2009)."""
    dvol = (extra or {}).get("dvol") or {}
    close = {s: {ts: c for ts, _, c in b} for s, b in bars_by.items()}
    frac = 0.5 if p["threshold"] == "median" else 2 / 3
    hist, weights = {s: [] for s in bars_by}, {}
    for T in _midnights(bars_by):
        w = {}
        for s in bars_by:
            iv = (dvol.get(s.replace("USDT", "")) or {}).get(T - DAY)
            c, rs = close[s], []
            for h in range(14 * 24):
                a, b = c.get(T - HOUR - h * HOUR), c.get(T - 2 * HOUR - h * HOUR)
                if not a or not b:
                    rs = None
                    break
                rs.append(math.log(a / b))
            if iv is None or rs is None:
                w[s] = 0.0
                continue
            vrp = (iv / 100) ** 2 - (statistics.pstdev(rs) * math.sqrt(24 * 365)) ** 2
            h = hist[s]
            w[s] = 1.0 if (len(h) >= 30 and vrp > _q(h[-30:], frac)) else 0.0
            h.append(vrp)
        weights[T] = w
    return _apply(bars_by, weights)


def stablecoin_flow(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Hold the universe when stablecoin supply grows (Griffin & Shams 2020)."""
    stable = (extra or {}).get("stable") or {}
    hist, weights, cur = [], {}, 0.0
    for T in _midnights(bars_by):
        a, b = stable.get(T - DAY), stable.get(T - 8 * DAY)
        if a and b:
            g = a / b - 1
            if p["rule"] == "positive":
                cur = 1.0 if g > 0 else 0.0
            else:
                cur = 1.0 if (len(hist) >= 30 and g > _q(hist[-30:], 0.5)) else 0.0
            hist.append(g)
        else:
            cur = 0.0
        weights[T] = {s: cur for s in bars_by}
    return _apply(bars_by, weights)


def btc_volume_share(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """BTC vs the rest, by the trend in BTC's share of dollar volume (hypothesis; proxy for dominance)."""
    dv = _daily_dollar_volume((extra or {}).get("volume"))
    L, weights = p["lookback_days"], {}
    others = [s for s in bars_by if s != "BTCUSDT"]

    def share(day):
        tot = sum(d.get(day, 0.0) for d in dv.values())
        b = (dv.get("BTCUSDT") or {}).get(day)
        return (b / tot) if (b and tot) else None

    for T in _midnights(bars_by):
        rec = [share(T - k * DAY) for k in range(1, L + 1)]
        pri = [share(T - k * DAY) for k in range(L + 1, 2 * L + 1)]
        w = {s: 0.0 for s in bars_by}
        if "BTCUSDT" in bars_by and others and not any(v is None for v in rec + pri):
            diff = statistics.fmean(rec) - statistics.fmean(pri)
            sign = 1.0 if diff > 0 else (-1.0 if diff < 0 else 0.0)
            w["BTCUSDT"] = sign
            for s in others:
                w[s] = -sign / len(others)
        weights[T] = w
    return _apply(bars_by, weights)


def xs_momentum(bars_by, funding_by, p, fit=None, volume_by=None):
    """Long the k strongest, short the k weakest over the lookback (Liu, Tsyvinski & Wu 2022)."""
    return _xs(bars_by, funding_by, p, _score_momentum, long_low=False)


def xs_max_lottery(bars_by, funding_by, p, fit=None, volume_by=None):
    """Short the k coins with the highest maximum daily return, long the k lowest (Bali, Cakici & Whitelaw 2011)."""
    return _xs(bars_by, funding_by, p, _score_max, long_low=True)


def xs_low_volatility(bars_by, funding_by, p, fit=None, volume_by=None):
    """Long the k least volatile, short the k most volatile (Ang, Hodrick, Xing & Zhang 2006)."""
    return _xs(bars_by, funding_by, p, _score_vol, long_low=True)


def xs_betting_against_beta(bars_by, funding_by, p, fit=None, volume_by=None):
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
    # ---- amendment 3: 30-perp universe ----
    "xs_illiquidity": {
        "family": xs_illiquidity, "cross_sectional": True, "needs_volume": True, "universe": "30",
        "mechanism_tag": "illiquidity_premium", "long_only": False,
        "grid": [{"lookback_days": 28, "k": 5}, {"lookback_days": 56, "k": 5}],
        "hypothesis": "Illiquid coins (high Amihud ILLIQ) earn a premium over liquid coins, net of costs.",
        "rationale": "Investors demand compensation for holding assets that are costly to trade.",
        "evidence": ["Amihud 2002, Journal of Financial Markets, https://doi.org/10.1016/S1386-4181(01)00024-6 (equities)"]},
    "xs_high_volume": {
        "family": xs_high_volume, "cross_sectional": True, "needs_volume": True, "universe": "30",
        "mechanism_tag": "high_volume_return_premium", "long_only": False,
        "grid": [{"formation_days": 7, "k": 5}, {"formation_days": 14, "k": 5}],
        "hypothesis": "Coins with unusually high recent trading volume outperform coins with unusually low volume.",
        "rationale": "A volume shock raises a coin's visibility, which increases later demand.",
        "evidence": ["Gervais, Kaniel & Mingelgrin 2001, Journal of Finance, https://doi.org/10.1111/0022-1082.00349 (equities)"]},
    "xs_downside_beta": {
        "family": xs_downside_beta, "cross_sectional": True, "universe": "30",
        "mechanism_tag": "downside_risk_premium", "long_only": False,
        "grid": [{"lookback_days": 56, "k": 5}, {"lookback_days": 112, "k": 5}],
        "hypothesis": "Coins that move most with the market on down days earn a premium.",
        "rationale": "Investors dislike assets that crash with the market and require compensation to hold them.",
        "evidence": ["Ang, Chen & Xing 2006, Review of Financial Studies, https://doi.org/10.1093/rfs/hhj035 (equities)"]},
    "xs_coskewness": {
        "family": xs_coskewness, "cross_sectional": True, "universe": "30",
        "mechanism_tag": "coskewness_premium", "long_only": False,
        "grid": [{"lookback_days": 56, "k": 5}, {"lookback_days": 112, "k": 5}],
        "hypothesis": "Coins with negative coskewness with the market outperform coins with positive coskewness.",
        "rationale": "Assets that add negative skew to a portfolio must offer higher expected returns.",
        "evidence": ["Harvey & Siddique 2000, Journal of Finance, https://doi.org/10.1111/0022-1082.00247 (equities)"]},
    "xs_near_high": {
        "family": xs_near_high, "cross_sectional": True, "universe": "30",
        "mechanism_tag": "anchoring_to_high", "long_only": False,
        "grid": [{"lookback_days": 60, "k": 5}, {"lookback_days": 120, "k": 5}],
        "hypothesis": "Coins trading near their recent high outperform coins far below it.",
        "rationale": "Traders anchor on the recent high and under-react to good news near it.",
        "evidence": ["George & Hwang 2004, Journal of Finance, https://doi.org/10.1111/j.1540-6261.2004.00695.x (equities; window adapted)"]},
    "turn_of_month": {
        "family": turn_of_month, "universe": "30", "mechanism_tag": "calendar_turn_of_month", "long_only": True,
        "grid": [{"days_before": 1, "days_after": 3}, {"days_before": 2, "days_after": 4}],
        "hypothesis": "Crypto returns around the turn of the month are high enough that holding only then beats buy-and-hold.",
        "rationale": "Month-end flows (salaries, fund rebalancing, contract rolls) concentrate buying around the month turn.",
        "evidence": ["Lakonishok & Smidt 1988, Review of Financial Studies, https://doi.org/10.1093/rfs/1.4.403 (equities)"]},
    "btc_lead_lag": {
        "family": btc_lead_lag, "cross_sectional": True, "universe": "30", "mechanism_tag": "lead_lag_diffusion",
        "long_only": False, "grid": [{"x": 0.02}, {"x": 0.04}],
        "hypothesis": "Large BTC moves are followed by same-direction moves in other coins the next day.",
        "rationale": "Information is priced first in the leader and diffuses slowly to followers.",
        "evidence": ["Hou 2007, Review of Financial Studies, https://doi.org/10.1093/revfin/hhm003 (equities; adapted to BTC as leader)"]},
    # ---- PROTOCOL v3 (research/PROTOCOL_V3.md) ----
    "oi_growth": {
        "family": oi_growth, "cross_sectional": True, "protocol": 3, "universe": "30v3", "needs": ["metrics"],
        "mechanism_tag": "open_interest_growth", "long_only": False,
        "grid": [{"lookback_days": 7, "k": 5}, {"lookback_days": 28, "k": 5}],
        "hypothesis": "Coins whose futures open interest grows fastest outperform those whose open interest shrinks.",
        "rationale": "Rising open interest means new money committing to a market; in commodity futures it predicts higher returns.",
        "evidence": ["Hong & Yogo 2012, Journal of Financial Economics, https://doi.org/10.1016/j.jfineco.2012.04.005 (commodities)"]},
    "oi_confirmed_return": {
        "family": oi_confirmed_return, "cross_sectional": True, "protocol": 3, "universe": "30v3", "needs": ["metrics"],
        "mechanism_tag": "oi_confirmed_trend", "long_only": False,
        "grid": [{"lookback_days": 7, "k": 5}, {"lookback_days": 14, "k": 5}],
        "hypothesis": "Price moves accompanied by rising open interest continue; moves with falling open interest reverse.",
        "rationale": "Open interest separates new positioning from position closing (short covering), which volume cannot.",
        "evidence": ["Bessembinder & Seguin 1993, Journal of Financial and Quantitative Analysis, https://doi.org/10.2307/2331149"]},
    "smart_vs_crowd": {
        "family": smart_vs_crowd, "cross_sectional": True, "protocol": 3, "universe": "30v3", "needs": ["metrics"],
        "mechanism_tag": "informed_positioning_divergence", "long_only": False,
        "grid": [{"lookback_days": 7, "k": 5}, {"lookback_days": 14, "k": 5}],
        "hypothesis": "When top traders are more bullish than the average account, the coin outperforms, and vice versa.",
        "rationale": "Large speculators are better informed than small traders, so their divergence from the crowd carries information.",
        "evidence": ["Wang 2003, Journal of Futures Markets, https://doi.org/10.1002/fut.10056"]},
    "leverage_cycle": {
        "family": leverage_cycle, "cross_sectional": True, "protocol": 3, "universe": "30v3", "needs": ["metrics"],
        "mechanism_tag": "leverage_cycle_timing", "long_only": True,
        "grid": [{"lookback_days": 7}, {"lookback_days": 14}],
        "hypothesis": "Stepping out of the market when leverage builds faster than prices improves risk-adjusted returns.",
        "rationale": "Leverage cycles end in forced deleveraging; fast leverage build-up raises crash risk.",
        "evidence": ["Geanakoplos 2010, NBER Macroeconomics Annual, https://doi.org/10.1086/648285"]},
    "vrp_timing": {
        "family": vrp_timing, "cross_sectional": True, "protocol": 3, "universe": "btceth", "needs": ["dvol"],
        "mechanism_tag": "variance_risk_premium_timing", "long_only": True,
        "grid": [{"threshold": "median"}, {"threshold": "tercile"}],
        "hypothesis": "BTC and ETH earn more when implied volatility is high relative to realised volatility.",
        "rationale": "A high variance risk premium means investors pay for protection; bearing that risk is compensated.",
        "evidence": ["Bollerslev, Tauchen & Zhou 2009, Review of Financial Studies, https://doi.org/10.1093/rfs/hhp008 (equities)"]},
    "stablecoin_flow": {
        "family": stablecoin_flow, "cross_sectional": True, "protocol": 3, "universe": "30v3", "needs": ["stable"],
        "mechanism_tag": "stablecoin_liquidity_flow", "long_only": True,
        "grid": [{"rule": "positive"}, {"rule": "above_median"}],
        "hypothesis": "Crypto returns are higher in weeks after the total stablecoin supply grows.",
        "rationale": "New stablecoins are dry powder waiting to buy crypto; issuance has preceded price increases.",
        "evidence": ["Griffin & Shams 2020, Journal of Finance, https://doi.org/10.1111/jofi.12903"]},
    "btc_volume_share": {
        "family": btc_volume_share, "cross_sectional": True, "protocol": 3, "universe": "30v3", "needs": ["volume"],
        "mechanism_tag": "btc_dominance_rotation", "long_only": False,
        "grid": [{"lookback_days": 7}, {"lookback_days": 14}],
        "hypothesis": "When BTC's share of trading rises, BTC outperforms the other coins, and vice versa.",
        "rationale": "Hypothesis only (user's choice): capital rotating into BTC signals risk aversion within crypto.",
        "evidence": ["hypothesis only: no direct peer-reviewed source; dollar-volume share is a proxy for market-cap dominance"]},
    "taker_pressure": {
        "family": taker_pressure, "cross_sectional": True, "protocol": 3, "universe": "30v3",
        "needs": ["taker", "volume"], "mechanism_tag": "orderflow_imbalance", "long_only": False,
        "grid": [{"formation_days": 7, "k": 5}, {"formation_days": 14, "k": 5}],
        "hypothesis": "Coins with unusually aggressive buying over a week keep outperforming the next week.",
        "rationale": "Order imbalance reflects informed or persistent demand that prices absorb gradually.",
        "evidence": ["Chordia & Subrahmanyam 2004, Journal of Financial Economics, https://doi.org/10.1016/S0304-405X(03)00175-2 (equities)"]},
}

INSTRUMENT_FAMILY = "binance_usdm_perps_8alt"
INSTRUMENT_FAMILY_30 = "binance_usdm_perps_30"
MIN_SYMBOLS_30 = 24                     # amendment 3: experiment continues only with >= 24 quality-checked symbols


def universe(template):
    from lab.engine import data
    u = TEMPLATES[template].get("universe")
    return {"30": data.UNIVERSE_30, "30v3": data.UNIVERSE_30_V3, "btceth": ("BTCUSDT", "ETHUSDT")}.get(u, data.UNIVERSE)


def instrument_family(template):
    u = TEMPLATES[template].get("universe")
    return {"30": INSTRUMENT_FAMILY_30, "30v3": "binance_usdm_perps_30v3", "btceth": "binance_usdm_btc_eth"}.get(
        u, INSTRUMENT_FAMILY)


def min_symbols(template):
    u = TEMPLATES[template].get("universe")
    return MIN_SYMBOLS_30 if u in ("30", "30v3") else len(universe(template))


def protocol_of(template):
    return TEMPLATES[template].get("protocol", PROTOCOL_VERSION)
HORIZON = {"vol_managed_long": "days", "day_of_week": "days", "hour_of_day": "hours", "funding_contrarian": "hours",
           "daily_reversal": "days", "donchian_trend": "days", "xs_momentum": "weeks", "xs_max_lottery": "weeks",
           "xs_low_volatility": "weeks", "xs_betting_against_beta": "weeks", "xs_illiquidity": "weeks",
           "xs_high_volume": "weeks", "xs_downside_beta": "weeks", "xs_coskewness": "weeks", "xs_near_high": "weeks",
           "turn_of_month": "days", "btc_lead_lag": "days", "oi_growth": "weeks", "oi_confirmed_return": "weeks",
           "smart_vs_crowd": "weeks", "leverage_cycle": "days", "vrp_timing": "days", "stablecoin_flow": "days",
           "btc_volume_share": "days", "taker_pressure": "weeks"}


def exp_id(template, version=None):
    return f"E_{template}_p{version or protocol_of(template)}"
