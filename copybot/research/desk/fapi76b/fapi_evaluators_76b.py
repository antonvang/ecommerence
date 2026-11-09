"""Director order 76-B: synthetic evaluators for the five mechanism designs. Pure functions over lists handed in by the
caller: no file, no network, no lab.db, no market data. They exist so the mechanical rules in FAPI_DESIGNS_76B.md are
exact, and so the tests can plant effects and leaks on synthetic series. A future evaluator would start from this code
after a lock. Parameters are fixed design choices written before any data; nothing is tuned.

Point in time: every signal at row t uses only rows 0..t (tests: truncation invariance through validation_engine).
Cluster = UTC day. Statistic: one-sided t on cluster means; t critical value from order69_power.t_quantile.
"""
from __future__ import annotations

import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.desk.order69_power import ALPHA_F, t_quantile  # noqa: E402

DAY, HOUR = 86400, 3600
PASS, FALSIFIED, INCONCLUSIVE, UNTESTABLE = "PASS", "FALSIFIED", "INCONCLUSIVE", "UNTESTABLE"

CB1 = {"range_days": 7, "pct_window": 90, "pct_min": 60, "pct_q": 0.15, "channel": 20, "vol_mult": 2.0, "vol_window": 20,
       "dedup_days": 14, "hold_hours": 72, "entry_delay_h": 1, "horizon_days": 3, "n_bins": 10, "min_controls": 5}
PR1 = {"tau": 0.0010, "h": 8, "dedup_h": 8, "min_bucket": 3, "min_vol_usd": 1e6}
LD1 = {"z_price": 3.0, "z_liq": 2.0}
FL1 = {"z_win": 720, "z_min_obs": 600, "z": -4.0, "oi_drop": -0.02, "dedup_h": 6, "hold_h": 24}
TS1 = {"start_h": 13, "end_h": 20, "rv_days": 30}


def decide(values, mu0=0.0, alpha=ALPHA_F, min_clusters=40):
    """One-sided cluster t-test of H0 mean <= mu0. PASS needs mean > mu0 and t above the critical value. Mean <= mu0 is a
    FALSIFIED hypothesis (given enough clusters), and between the two it is INCONCLUSIVE."""
    n = len(values)
    if n < min_clusters:
        return {"n": n, "verdict": UNTESTABLE, "mean": None, "t": None}
    m = statistics.fmean(values)
    sd = statistics.stdev(values)
    t = (m - mu0) / (sd / math.sqrt(n)) if sd > 0 else 0.0
    crit = t_quantile(1 - alpha, n - 1)
    verdict = FALSIFIED if m <= mu0 else (PASS if t > crit else INCONCLUSIVE)
    return {"n": n, "verdict": verdict, "mean": m, "t": t, "crit": crit}


def daily_means(events):
    """events: iterable of (ts, value). One cluster per UTC day, the mean of the day's values, in day order."""
    days = {}
    for ts, v in events:
        days.setdefault(ts - ts % DAY, []).append(v)
    return [statistics.fmean(days[d]) for d in sorted(days)]


# ---- CB1: compression, then a breakout with participation (daily bars) ----

def _quantile(sorted_vals, q):
    return sorted_vals[math.floor(q * (len(sorted_vals) - 1))]


def cb1_compressed_series(bars, cfg=CB1):
    """True at day t when the mean 7-day range through t-1 is strictly below the 15th percentile of its own trailing
    pct_window values (each dated before t-1). Causal: bar t is not used, so a breakout day cannot make compression."""
    n = len(bars)
    ranges = [math.log(b["high"] / b["low"]) for b in bars]
    cr = [None] * n
    for t in range(cfg["range_days"] - 1, n):
        cr[t] = statistics.fmean(ranges[t - cfg["range_days"] + 1:t + 1])
    out = [False] * n
    for t in range(cfg["range_days"] + 1, n):
        past = [v for v in cr[max(0, t - 1 - cfg["pct_window"]):t - 1] if v is not None]
        if len(past) >= cfg["pct_min"] and cr[t - 1] < _quantile(sorted(past), cfg["pct_q"]):   # strict: flat is not compressed
            out[t] = True
    return out


def cb1_signal_series(bars, cfg=CB1):
    """bars: list of dicts {ts, high, low, close, volume}. For each day t: +1 or -1 if compression held through t-1 and
    day t closes outside the prior 20-day channel on at least 2 x the prior 20-day median volume; else 0. Causal."""
    n = len(bars)
    out, last = [0] * n, -10 ** 9
    compressed = cb1_compressed_series(bars, cfg)
    channel, vw = cfg["channel"], cfg["vol_window"]
    for t in range(max(channel, vw, cfg["range_days"] + 1), n):
        if not compressed[t] or t - last < cfg["dedup_days"]:
            continue
        hi = max(b["high"] for b in bars[t - channel:t])
        lo = min(b["low"] for b in bars[t - channel:t])
        side = 1 if bars[t]["close"] > hi else (-1 if bars[t]["close"] < lo else 0)
        if side == 0:
            continue
        if bars[t]["volume"] < cfg["vol_mult"] * statistics.median(b["volume"] for b in bars[t - vw:t]):
            continue
        out[t], last = side, t
    return out


def _ols(rows):
    """Coefficients of an OLS with intercept (rows: (features, y)), by normal equations and Gaussian elimination."""
    k = len(rows[0][0]) + 1
    a = [[0.0] * (k + 1) for _ in range(k)]
    for x, y in rows:
        v = [1.0] + list(x)
        for i in range(k):
            for j in range(k):
                a[i][j] += v[i] * v[j]
            a[i][k] += v[i] * y
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(a[r][i]))
        a[i], a[p] = a[p], a[i]
        if abs(a[i][i]) < 1e-12:
            return None
        for r in range(i + 1, k):
            f = a[r][i] / a[i][i]
            for c in range(i, k + 1):
                a[r][c] -= f * a[i][c]
    b = [0.0] * k
    for i in range(k - 1, -1, -1):
        b[i] = (a[i][k] - sum(a[i][j] * b[j] for j in range(i + 1, k))) / a[i][i]
    return b


def _har_features(rv, d):
    return math.log(rv[d]), math.log(statistics.fmean(rv[d - 6:d + 1])), math.log(statistics.fmean(rv[d - 29:d + 1]))


def har_log_forecast(rv, t, horizon=3, min_rows=60):
    """ln of the forecast mean daily RV over t+1..t+horizon, log-HAR on 1, 7 and 30 days, fitted by OLS on rows whose
    target was already known at t (no row looks past t). None when there is too little history."""
    if t < 29 or len(rv) <= t:
        return None
    rows = []
    for d in range(29, t - horizon + 1):
        target = statistics.fmean(rv[d + 1:d + horizon + 1])
        if target > 0 and rv[d] > 0:
            rows.append((_har_features(rv, d), math.log(target)))
    if len(rows) < min_rows:
        return None
    coef = _ols(rows)
    if coef is None or rv[t] <= 0:
        return None
    return coef[0] + sum(c * f for c, f in zip(coef[1:], _har_features(rv, t)))


def cb1_vol_outcomes(panel, cfg=CB1, n_bins=None):
    """panel: {symbol: {"bars": daily bars, "rv": daily RV, same length and days for every symbol}}. An event's g is
    ln(RV next 3 days) minus the log-HAR forecast. y = g minus the median g of same-day coins in the same forecast bin
    that are also compressed but had no event in the last dedup_days, so the test isolates the breakout and its volume
    from plain volatility mean reversion after compression. Returns [(day ts, y)]; events without enough controls drop."""
    bins = n_bins or cfg["n_bins"]
    syms = sorted(panel)
    signals = {s: cb1_signal_series(panel[s]["bars"], cfg) for s in syms}
    compressed = {s: cb1_compressed_series(panel[s]["bars"], cfg) for s in syms}
    n = len(panel[syms[0]]["bars"])
    out = []
    for t in range(n - cfg["horizon_days"]):
        evs = [s for s in syms if signals[s][t] != 0]
        if not evs:
            continue
        info = {}
        for s in syms:
            rv = panel[s]["rv"]
            fc = har_log_forecast(rv, t, cfg["horizon_days"])
            real = statistics.fmean(rv[t + 1:t + cfg["horizon_days"] + 1])
            if fc is None or real <= 0:
                continue
            quiet = all(signals[s][k] == 0 for k in range(max(0, t - cfg["dedup_days"]), t + 1))
            info[s] = {"fc": fc, "g": math.log(real) - fc, "quiet": quiet and compressed[s][t]}
        order = sorted(info, key=lambda s: info[s]["fc"])
        for rank, s in enumerate(order):
            info[s]["bin"] = rank * bins // len(order)
        for s in evs:
            if s not in info:
                continue
            controls = [info[c]["g"] for c in info if info[c]["quiet"] and info[c]["bin"] == info[s]["bin"] and c != s]
            if len(controls) >= cfg["min_controls"]:
                out.append((panel[s]["bars"][t]["ts"], info[s]["g"] - statistics.median(controls)))
    return out


def cb1_direction_net(hours, close_ts, side, cost_frac, cfg=CB1):
    """hours: [(close ts, price)] sorted. Entry at the first hourly close at least entry_delay_h after the signal day's
    close; exit hold_hours later. Returns the net log return, or None if a leg is missing (never filled)."""
    prices = dict(hours)
    entry_ts = close_ts + cfg["entry_delay_h"] * HOUR
    exit_ts = entry_ts + cfg["hold_hours"] * HOUR
    if entry_ts not in prices or exit_ts not in prices or side == 0:
        return None
    return side * math.log(prices[exit_ts] / prices[entry_ts]) - cost_frac


# ---- PR1: premium decay over one funding period, liquid against thin perps ----

def pr1_signal_series(rows, cfg=PR1):
    """rows: list of dicts {mark, index}. 1 at hour t if |premium| >= tau at t and t-1 with the same sign; else 0. Causal."""
    p = [math.log(r["mark"] / r["index"]) for r in rows]
    out = [0] * len(rows)
    for t in range(1, len(rows)):
        if abs(p[t]) >= cfg["tau"] and abs(p[t - 1]) >= cfg["tau"] and p[t] * p[t - 1] > 0:
            out[t] = 1
    return out


def pr1_events(rows, cfg=PR1):
    """rows: list of dicts {ts, mark, index, qvol}. Events deduplicated over dedup_h. Returns dicts with decay D at +h:
    the share of the premium gone after h hours (1 = fully gone, negative = it grew)."""
    sig = pr1_signal_series(rows, cfg)
    p = [math.log(r["mark"] / r["index"]) for r in rows]
    h, out, last = cfg["h"], [], -10 ** 9
    for t in range(len(rows) - h):
        if sig[t] and t - last >= cfg["dedup_h"]:
            last = t
            s = 1 if p[t] > 0 else -1
            out.append({"ts": rows[t]["ts"], "D": (abs(p[t]) - s * p[t + h]) / abs(p[t]), "qvol": rows[t]["qvol"]})
    return out


def pr1_daily_contrast(panel, cfg=PR1):
    """panel: {symbol: rows}. Per UTC day: mean D of events in coins in the top volume tercile minus the bottom tercile,
    terciles over coins with an event that day and at least min_vol_usd. Days lacking min_bucket events in either
    bucket are dropped. Returns (contrast values, mean D of liquid days)."""
    days = {}
    for s in sorted(panel):
        for e in pr1_events(panel[s], cfg):
            if e["qvol"] >= cfg["min_vol_usd"]:
                days.setdefault(e["ts"] - e["ts"] % DAY, []).append(e)
    contrast, liquid_d = [], []
    for d in sorted(days):
        evs = sorted(days[d], key=lambda e: e["qvol"])
        third = len(evs) // 3
        low, high = evs[:third], evs[-third:] if third else []
        if third == 0 or len(low) < cfg["min_bucket"] or len(high) < cfg["min_bucket"]:
            continue
        ml, mh = statistics.fmean(e["D"] for e in low), statistics.fmean(e["D"] for e in high)
        contrast.append(mh - ml)
        liquid_d.append(mh)
    return contrast, liquid_d


def pr1_decide(contrast, liquid_d, alpha=ALPHA_F):
    """PASS needs the contrast above zero AND a mean liquid-coin decay of at least 0.5 (the premium mostly gone in 8 h)."""
    res = decide(contrast, 0.0, alpha)
    if res["verdict"] == PASS and (not liquid_d or statistics.fmean(liquid_d) < 0.5):
        res = dict(res, verdict=INCONCLUSIVE, reason="liquid decay below 0.5")
    return res


# ---- LD1: price-led against liquidity-led book disruption (same rows as LQ1) ----

def ld1_classify(z_abs, cfg=LD1):
    if z_abs >= cfg["z_price"]:
        return "price"
    return "liquidity" if z_abs < cfg["z_liq"] else None


def ld1_contrast(events, cfg=LD1):
    """events: dicts {ts, z_abs, rt0, rt1} in bp. Saving S = (rt0 - rt1) / 2. Returns (saving means of the two groups by
    UTC day, price-led and liquidity-led); the design compares liquidity-led minus price-led."""
    groups = {"price": [], "liquidity": []}
    for e in events:
        g = ld1_classify(e["z_abs"], cfg)
        if g:
            groups[g].append((e["ts"], (e["rt0"] - e["rt1"]) / 2))
    return daily_means(groups["price"]), daily_means(groups["liquidity"])


def ld1_signal_series(rows, cfg=LD1):
    """rows: dicts {z_abs}. Numeric label per row: 1 price-led, -1 liquidity-led, 0 neither (no future row is used)."""
    code = {"price": 1, "liquidity": -1, None: 0}
    return [code[ld1_classify(r["z_abs"], cfg)] for r in rows]


# ---- FL1: extreme hourly drop with an open-interest flush ----

def fl1_signal_series(rows, cfg=FL1):
    """rows: dicts {r: 1 h log return, oi_chg: OI change over the hour}. 1 at t on a flush; causal, dedup_h apart."""
    out, last = [0] * len(rows), -10 ** 9
    for t in range(len(rows)):
        past = [r["r"] for r in rows[max(0, t - cfg["z_win"]):t]]
        if len(past) < cfg["z_min_obs"]:
            continue
        sd = statistics.pstdev(past)
        if sd > 0 and rows[t]["r"] / sd <= cfg["z"] and rows[t]["oi_chg"] <= cfg["oi_drop"] and t - last >= cfg["dedup_h"]:
            out[t], last = 1, t
    return out


def fl1_outcomes(rows, cost_frac, cfg=FL1):
    """rows: dicts {ts, r, oi_chg, close}. Long at the close of the hour after the flush, held hold_h hours. A missing leg
    drops the event. Returns [(ts, net)]."""
    sig = fl1_signal_series(rows, cfg)
    h = cfg["hold_h"]
    out = []
    for t in range(len(rows) - h - 1):
        if sig[t]:
            out.append((rows[t]["ts"], math.log(rows[t + 1 + h]["close"] / rows[t + 1]["close"]) - cost_frac))
    return out


# ---- TS1: US session in a high-volatility regime ----

def ts1_signal_series(rows, cfg=TS1):
    """rows: dicts {ts: bar open, r: 1 h log return of that bar}, hourly, no gaps. 1 for the bars of the 13:00-20:00 UTC
    session when the realised variance of the 24 h before the session start is at least the median of the same measure
    over the preceding rv_days days. The session's label is fixed at its start, so it never uses a later row."""
    n = len(rows)
    out = [0] * n
    active_day, on = None, False
    for t in range(n):
        ts = rows[t]["ts"]
        hour = (ts % DAY) // HOUR
        if hour == cfg["start_h"] and ts % HOUR == 0:
            active_day, on = ts - ts % DAY, False
            if t >= 24:
                day_rv = [sum(r["r"] ** 2 for r in rows[j - 24:j]) for j in range(t, t - 24 * (cfg["rv_days"] + 1), -24)
                          if j >= 24]
                if len(day_rv) > cfg["rv_days"]:
                    on = day_rv[0] >= statistics.median(day_rv[1:])
        if on and active_day == ts - ts % DAY and cfg["start_h"] <= hour < cfg["end_h"]:
            out[t] = 1
    return out


def ts1_session_returns(rows, cost_frac, cfg=TS1):
    """Net return per session where the label is on, cost per session. Returns [(day ts, net)]."""
    sig = ts1_signal_series(rows, cfg)
    by_day = {}
    for t, r in enumerate(rows):
        if sig[t]:
            d = r["ts"] - r["ts"] % DAY
            by_day[d] = by_day.get(d, 0.0) + r["r"]
    return [(d, v - cost_frac) for d, v in sorted(by_day.items())]
