"""Tester flere strategityper på EURUSD H1 med ens omkostninger og risikomodel.

Hver handel måles i R (1R = det beløb, der risikeres). Egenkapitalen beregnes
med fast procent-risiko pr. handel. Data deles i en udvælgelsesperiode
(in-sample) og en kontrolperiode (out-of-sample), som ikke må bruges til valg.

Konservativt: signal ved lukket candle, indgang ved næste åbning, rammes SL og
TP i samme candle tæller det som SL, og omkostningen trækkes ved indgang.

Brug: python research.py eurusd_h1.csv [server_utc_offset]
      (offset kun for MT5-eksport, fx 3 for Vantage om sommeren; Dukascopy er UTC = 0)
"""
import sys

import numpy as np
import pandas as pd

PIP = 0.0001
COST_PIPS = 1.2          # spread + kommission/slippage pr. handel (Vantage-niveau)
MAX_SL_PIPS_200 = 30.0   # 0,01 lot på 200 USD: 30 pips = 3 USD = 1,5 % risiko
SPLIT = "2024-01-01"


# ---------------------------------------------------------------- indikatorer
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l)


def atr(df, n):
    tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(),
                    (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ---------------------------------------------------------------- motor
def backtest(df, sig):
    """sig: DataFrame med kolonnerne dir (1/-1/0), sl, tp (afstande i pris),
    og valgfrit exit (bool: luk ved næste åbning), max_bars (int)."""
    o, h, l, c = df.open.values, df.high.values, df.low.values, df.close.values
    d, sl_d, tp_d = sig.dir.values, sig.sl.values, sig.tp.values
    ex = sig["exit"].values if "exit" in sig else np.zeros(len(df), bool)
    max_bars = sig["max_bars"].values if "max_bars" in sig else np.full(len(df), 10**9)
    cost = COST_PIPS * PIP
    trades = []
    pos = None
    for i in range(len(df) - 1):
        if pos is not None:
            direction, entry, stop, target, risk, t0, mb = pos
            if direction == 1:
                hit_sl, hit_tp = l[i] <= stop, h[i] >= target
            else:
                hit_sl, hit_tp = h[i] >= stop, l[i] <= target
            px = None
            if hit_sl:
                px = stop
            elif hit_tp:
                px = target
            elif ex[i] or (i - t0) >= mb:
                px = o[i + 1]
            if px is not None:
                r = ((px - entry) * direction - cost) / risk
                trades.append((df.index[t0], df.index[i], direction, r, risk / PIP))
                pos = None
                continue
        if pos is None and d[i] != 0 and sl_d[i] > 0:
            entry = o[i + 1]
            pos = (d[i], entry, entry - d[i] * sl_d[i], entry + d[i] * tp_d[i], sl_d[i], i + 1,
                   max_bars[i])
    return pd.DataFrame(trades, columns=["open", "close", "dir", "r", "sl_pips"])


def stats(t, risk_pct=1.0):
    if len(t) == 0:
        return dict(trades=0)
    eq = (1 + t.r * risk_pct / 100).cumprod()
    dd = (1 - eq / eq.cummax()).max() * 100
    w, lo = t.r[t.r > 0].sum(), -t.r[t.r <= 0].sum()
    years = max((t.close.iloc[-1] - t.open.iloc[0]).days / 365.25, 0.1)
    return dict(trades=len(t), per_week=round(len(t) / years / 52, 1),
                win=round((t.r > 0).mean() * 100), pf=round(w / lo, 2) if lo else np.inf,
                avg_r=round(t.r.mean(), 3), total_r=round(t.r.sum(), 1),
                cagr=round((eq.iloc[-1] ** (1 / years) - 1) * 100, 1), max_dd=round(dd, 1),
                sl_med=round(t.sl_pips.median(), 1))


# ---------------------------------------------------------------- strategier
def s_trend_pullback(df, sl=1.5, tp=3.0):
    """Den oprindelige EA: EMA50/200-trend + RSI14-pullback over 40/under 60."""
    f, s, r, a = ema(df.close, 50), ema(df.close, 200), rsi(df.close, 14), atr(df, 14)
    up = (df.close > s) & (f > s) & (r.shift() < 40) & (r >= 40)
    dn = (df.close < s) & (f < s) & (r.shift() > 60) & (r <= 60)
    return pd.DataFrame({"dir": up.astype(int) - dn.astype(int), "sl": a * sl, "tp": a * tp})


def s_donchian(df, n=20, sl=2.0, tp=4.0, filt=200):
    """Breakout: luk over højeste high i n candles (med trendfilter)."""
    hi, lo = df.high.rolling(n).max().shift(), df.low.rolling(n).min().shift()
    s, a = ema(df.close, filt), atr(df, 14)
    up = (df.close > hi) & (df.close > s)
    dn = (df.close < lo) & (df.close < s)
    return pd.DataFrame({"dir": up.astype(int) - dn.astype(int), "sl": a * sl, "tp": a * tp})


def s_rsi2_meanrev(df, lo_lvl=10, hi_lvl=90, sl=2.0, tp=1.0, filt=200, max_bars=24):
    """Mean reversion: kortsigtet overreaktion (RSI2) i retning af trend, hurtig exit."""
    r2, s, a = rsi(df.close, 2), ema(df.close, filt), atr(df, 14)
    sma5 = df.close.rolling(5).mean()
    up = (r2 < lo_lvl) & (df.close > s)
    dn = (r2 > hi_lvl) & (df.close < s)
    d = up.astype(int) - dn.astype(int)
    # luk når kursen er tilbage over/under det korte gennemsnit
    exit_ = pd.Series(False, index=df.index)
    exit_ |= (df.close > sma5) & (d.replace(0, np.nan).ffill() == 1)
    exit_ |= (df.close < sma5) & (d.replace(0, np.nan).ffill() == -1)
    return pd.DataFrame({"dir": d, "sl": a * sl, "tp": a * tp * 10, "exit": exit_,
                         "max_bars": max_bars})


def s_london_breakout(df, start=0, end=7, tp_mult=1.0, max_range_pips=40, min_range_pips=10):
    """Asiatisk range (UTC start-end) og indgang ved første H1-luk udenfor i London.
    SL i modsatte side af range, TP = range x tp_mult, lukkes senest kl. 20 UTC."""
    hrs = df.index.hour
    day = df.index.normalize()
    in_asia = (hrs >= start) & (hrs < end)
    rng_hi = df.high.where(in_asia).groupby(day).transform("max")
    rng_lo = df.low.where(in_asia).groupby(day).transform("min")
    rng = rng_hi - rng_lo
    ok = (hrs >= end) & (hrs < 12) & (rng >= min_range_pips * PIP) & (rng <= max_range_pips * PIP)
    up = ok & (df.close > rng_hi)
    dn = ok & (df.close < rng_lo)
    d = up.astype(int) - dn.astype(int)
    # kun første signal pr. dag
    first = d.ne(0) & ~d.ne(0).groupby(day).cumsum().gt(1)
    d = d.where(first, 0)
    sl = pd.Series(np.where(d == 1, df.close - rng_lo, rng_hi - df.close), index=df.index)
    exit_ = pd.Series(hrs >= 19, index=df.index)
    return pd.DataFrame({"dir": d, "sl": sl.clip(lower=5 * PIP), "tp": rng * tp_mult,
                         "exit": exit_})


def s_ema_cross_h4(df, fast=20, slow=50, sl=2.0, tp=4.0):
    """H4-trend: EMA-kryds beregnet på H4, handlet på H1-data."""
    h4 = df.close.resample("4h").last().dropna()
    f, s = ema(h4, fast), ema(h4, slow)
    cross = np.sign(f - s).diff().fillna(0) / 2
    # signalet er først kendt, når H4-candlen er lukket: flyt til sidste H1 i blokken
    cross.index = cross.index + pd.Timedelta(hours=3)
    d = cross.reindex(df.index).fillna(0).astype(int)
    a = atr(df, 14)
    return pd.DataFrame({"dir": d, "sl": a * sl * 2, "tp": a * tp * 2})


STRATEGIES = {
    "trend_pullback (nuværende)": [dict()],
    "donchian_breakout": [dict(n=n, sl=sl, tp=tp) for n in (20, 50) for sl, tp in ((2, 4), (1.5, 3))],
    "rsi2_meanrev": [dict(lo_lvl=l, hi_lvl=100 - l, sl=sl) for l in (5, 10) for sl in (2.0, 3.0)],
    "london_breakout": [dict(tp_mult=t, max_range_pips=m) for t in (1.0, 1.5) for m in (30, 40)],
    "ema_cross_h4": [dict(fast=20, slow=50), dict(fast=10, slow=30)],
}
FUNCS = {"trend_pullback (nuværende)": s_trend_pullback, "donchian_breakout": s_donchian,
         "rsi2_meanrev": s_rsi2_meanrev, "london_breakout": s_london_breakout,
         "ema_cross_h4": s_ema_cross_h4}


def main(path, utc_offset=0):
    df = pd.read_csv(path, parse_dates=["time"], index_col="time")
    # MT5-data er i serverens tid (Vantage typisk UTC+2/+3); strategierne regner i UTC
    df.index = df.index - pd.Timedelta(hours=utc_offset)
    print(f"Data: {df.index[0]:%Y-%m-%d} til {df.index[-1]:%Y-%m-%d}, {len(df)} H1-candles, "
          f"omkostning {COST_PIPS} pips/handel. Udvælgelse < {SPLIT} <= kontrol.\n")
    rows = []
    for name, grid in STRATEGIES.items():
        for params in grid:
            sig = FUNCS[name](df, **params)
            t = backtest(df, sig)
            ins, oos = t[t.open < SPLIT], t[t.open >= SPLIT]
            si, so = stats(ins), stats(oos)
            rows.append(dict(strategy=name, params=params,
                             **{f"is_{k}": v for k, v in si.items()},
                             **{f"oos_{k}": v for k, v in so.items()}))
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_colwidth", 60)
    cols = ["strategy", "params", "is_trades", "is_per_week", "is_win", "is_pf", "is_avg_r",
            "is_max_dd", "is_sl_med", "oos_trades", "oos_pf", "oos_avg_r", "oos_cagr", "oos_max_dd"]
    print(res[cols].sort_values("is_pf", ascending=False).to_string(index=False))
    return res


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0)
