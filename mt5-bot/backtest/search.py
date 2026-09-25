"""Bred strategisøgning med streng kontrol mod overtilpasning.

1. Alle opsætninger testes på udvælgelsesperioden (før SPLIT).
2. Kun opsætninger der er robuste der, går videre:
   PF >= 1.2, mindst 100 handler, højst ét tabsår, median-SL <= 30 pips
   (0,01 lot på en 200 USD-konto må højst risikere ca. 1,5 %).
3. Først derefter vises kontrolperioden (fra SPLIT), som aldrig bruges til valg.

Brug: python search.py eurusd_h1.csv [server_utc_offset]
"""
import itertools
import sys

import numpy as np
import pandas as pd

import research as R
from research import PIP, atr, backtest, ema, rsi, stats

SPLIT = "2023-01-01"
MAX_SL = 30.0


def htf(df, rule):
    """Candles i højere tidsramme, flyttet så værdien først kendes ved blokkens sidste H1-candle."""
    g = df.resample(rule, label="left", closed="left")
    out = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(),
                        "close": g.close.last()}).dropna()
    step = pd.Timedelta(rule) - pd.Timedelta(hours=1)
    out.index = out.index + step
    return out


def to_h1(series, df):
    return series.reindex(df.index.union(series.index)).ffill().reindex(df.index)


# ---------------------------------------------------------------- strategier
def ema_cross_tf(df, tf="4h", fast=10, slow=30, sl=1.5, exit_mode="cross", trail=0.0):
    """EMA-kryds på højere tidsramme. Exit: modsat kryds, trailing stop eller fast 2R."""
    x = htf(df, tf)
    f, s = ema(x.close, fast), ema(x.close, slow)
    side = np.sign(f - s)
    cross = (side.diff().fillna(0) / 2).astype(int)
    a = atr(x, 14)
    d = cross.reindex(df.index).fillna(0).astype(int)
    sl_d = to_h1(a, df) * sl
    out = pd.DataFrame({"dir": d, "sl": sl_d, "tp": sl_d * (2 if exit_mode == "fixed" else 100)})
    if exit_mode == "cross":
        out.attrs["reverse_exit"] = True
    if trail:
        out["trail"] = to_h1(a, df) * trail
    return out


def donchian_tf(df, tf="4h", n=20, sl=1.5, trail=2.0, filt=100):
    x = htf(df, tf)
    hi, lo = x.high.rolling(n).max().shift(), x.low.rolling(n).min().shift()
    s, a = ema(x.close, filt), atr(x, 14)
    up = (x.close > hi) & (x.close > s)
    dn = (x.close < lo) & (x.close < s)
    d = (up.astype(int) - dn.astype(int)).reindex(df.index).fillna(0).astype(int)
    sl_d = to_h1(a, df) * sl
    return pd.DataFrame({"dir": d, "sl": sl_d, "tp": sl_d * 100, "trail": to_h1(a, df) * trail})


def asian_fade(df, start=21, end=5, n=20, k=2.0, sl=1.5):
    """Rolig nattehandel: sælg over øvre Bollinger-bånd, køb under nedre, mål = midten."""
    m = df.close.rolling(n).mean()
    sd = df.close.rolling(n).std()
    a = atr(df, 14)
    hr = df.index.hour
    night = (hr >= start) | (hr < end - 1)
    up = night & (df.close < m - k * sd)
    dn = night & (df.close > m + k * sd)
    d = up.astype(int) - dn.astype(int)
    pos_side = d.replace(0, np.nan).ffill()
    back = ((pos_side == 1) & (df.close >= m)) | ((pos_side == -1) & (df.close <= m))
    exit_ = back | pd.Series((hr >= end) & (hr < 12), index=df.index)
    return pd.DataFrame({"dir": d, "sl": a * sl, "tp": a * 100, "exit": exit_, "max_bars": 8})


def prev_day_breakout(df, sl_frac=0.5, tp_r=1.5, hours=(7, 12), max_range=80):
    """Brud af gårsdagens high/low i London-formiddag. SL = andel af gårsdagens range."""
    day = df.index.normalize()
    daily = df.groupby(day).agg(high=("high", "max"), low=("low", "min"))
    pdh = daily.high.shift().reindex(day).values
    pdl = daily.low.shift().reindex(day).values
    rng = pdh - pdl
    hr = df.index.hour
    ok = (hr >= hours[0]) & (hr < hours[1]) & (rng <= max_range * PIP)
    up = ok & (df.close.values > pdh)
    dn = ok & (df.close.values < pdl)
    d = pd.Series(up.astype(int) - dn.astype(int), index=df.index)
    first = d.ne(0) & ~d.ne(0).groupby(day).cumsum().gt(1)
    d = d.where(first, 0)
    sl_d = pd.Series(rng * sl_frac, index=df.index)
    return pd.DataFrame({"dir": d, "sl": sl_d, "tp": sl_d * tp_r,
                         "exit": pd.Series(hr >= 20, index=df.index)})


def macd_trend(df, filt=200, sl=1.5, tp=3.0):
    m = ema(df.close, 12) - ema(df.close, 26)
    sig = ema(m, 9)
    s, a = ema(df.close, filt), atr(df, 14)
    cu = (m > sig) & (m.shift() <= sig.shift()) & (m < 0) & (df.close > s)
    cd = (m < sig) & (m.shift() >= sig.shift()) & (m > 0) & (df.close < s)
    return pd.DataFrame({"dir": cu.astype(int) - cd.astype(int), "sl": a * sl, "tp": a * tp})


def grid(**kw):
    keys = list(kw)
    return [dict(zip(keys, v)) for v in itertools.product(*kw.values())]


CANDIDATES = (
    [("ema_cross", ema_cross_tf, p) for p in grid(tf=["2h", "4h"], fast=[8, 10, 20], slow=[21, 30, 50],
                                                  sl=[1.0, 1.5], exit_mode=["cross", "fixed"])
     if p["fast"] < p["slow"]]
    + [("ema_cross_trail", ema_cross_tf, dict(p, exit_mode="trail"))
       for p in grid(tf=["2h", "4h"], fast=[10, 20], slow=[30, 50], sl=[1.0, 1.5], trail=[2.0, 3.0])]
    + [("donchian_tf", donchian_tf, p) for p in grid(tf=["2h", "4h"], n=[20, 55], sl=[1.0, 1.5],
                                                     trail=[2.0, 3.0])]
    + [("asian_fade", asian_fade, p) for p in grid(n=[20, 40], k=[2.0, 2.5], sl=[1.0, 1.5, 2.0])]
    + [("prev_day_breakout", prev_day_breakout, p) for p in grid(sl_frac=[0.3, 0.5], tp_r=[1.0, 1.5, 2.0])]
    + [("macd_trend", macd_trend, p) for p in grid(sl=[1.0, 1.5], tp=[2.0, 3.0])]
    + [("rsi2_meanrev", R.s_rsi2_meanrev, p) for p in grid(lo_lvl=[5, 10], sl=[1.5, 2.0])]
)


def yearly_r(t):
    return t.groupby(t.open.dt.year).r.sum().round(1).to_dict()


def main(path, utc_offset=0):
    df = pd.read_csv(path, parse_dates=["time"], index_col="time")
    df.index = df.index - pd.Timedelta(hours=utc_offset)
    df = df[["open", "high", "low", "close"]]
    print(f"Data {df.index[0]:%Y-%m-%d} til {df.index[-1]:%Y-%m-%d}. Udvælgelse < {SPLIT} <= kontrol. "
          f"{len(CANDIDATES)} opsætninger.\n")
    rows = []
    for name, fn, p in CANDIDATES:
        t = backtest(df, fn(df, **p))
        ins, oos = t[t.open < SPLIT], t[t.open >= SPLIT]
        si = stats(ins)
        yr = yearly_r(ins) if len(ins) else {}
        rows.append(dict(name=name, params=p, t=t, ins=si, oos=stats(oos), years=yr,
                         losing_years=sum(v < 0 for v in yr.values())))

    ok = [r for r in rows if r["ins"].get("trades", 0) >= 100 and r["ins"]["pf"] >= 1.2
          and r["losing_years"] <= 1 and r["ins"]["sl_med"] <= MAX_SL]
    ok.sort(key=lambda r: r["ins"]["avg_r"], reverse=True)

    print("Bedste 10 i udvælgelsesperioden (uanset krav):")
    for r in sorted(rows, key=lambda r: r["ins"].get("pf", 0), reverse=True)[:10]:
        i = r["ins"]
        print(f"  {r['name']:18} {str(r['params']):75} n={i.get('trades')} PF={i.get('pf')} "
              f"SL={i.get('sl_med')}p år={r['years']}")

    print(f"\n{len(ok)} opsætninger består kravene i udvælgelsesperioden.")
    for r in ok[:8]:
        i, o = r["ins"], r["oos"]
        print(f"\n== {r['name']} {r['params']}")
        print(f"   udvælgelse: {i}")
        print(f"   år (R):     {r['years']}")
        print(f"   KONTROL:    {o}")
        print(f"   kontrol år: {yearly_r(r['t'][r['t'].open >= SPLIT])}")
    return rows, ok


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0)
