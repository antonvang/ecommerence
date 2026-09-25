"""Test af veldokumenterede dagsstrategier med deres offentliggjorte standardparametre.

Ingen parametre er tunet på disse data. Strategierne blev offentliggjort før
testperioden (fx Connors' RSI(2), 2008), så 2012-2026 er reelt nye data for dem.

Omkostninger (CFD hos en broker som Vantage):
  - spread pr. handel (i pris), se COSTS
  - finansiering (swap) for hver nat en position holdes: FIN_RATE p.a. af kursværdien

Signal ved dagens luk, indgang ved næste dags åbning. Stop-loss rammes intradag
(kurshul fyldes til åbningskursen). Exit-signaler udføres ved næste dags åbning.

Brug: python daily_research.py <mappe med *_d1.csv>
"""
import os
import sys

import numpy as np
import pandas as pd

FIN_RATE = 0.07  # ca. rente + brokermarkup p.a. på CFD-positioner
COSTS = {  # typisk spread i pris
    "USA500IDXUSD": 0.6, "USATECHIDXUSD": 1.5, "USA30IDXUSD": 2.5, "DEUIDXEUR": 1.5,
    "XAUUSD": 0.30, "EURUSD": 0.00012, "GBPUSD": 0.00015,
}


def sma(s, n):
    return s.rolling(n).mean()


def rsi(s, n):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l)


def atr(df, n=14):
    tr = pd.concat([df.high - df.low, (df.high - df.close.shift()).abs(),
                    (df.low - df.close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ---------------------------------------------------------------- strategier
# Hver returnerer (entry: Series[bool], exit: Series[bool], side: 1/-1)
def connors_rsi2(df):
    """Connors & Alvarez (2008): over SMA200 og RSI(2) < 10 -> køb; sælg når luk > SMA5."""
    return (df.close > sma(df.close, 200)) & (rsi(df.close, 2) < 10), df.close > sma(df.close, 5), 1


def ibs_meanrev(df):
    """Internal Bar Strength < 0.2 over SMA200 -> køb; sælg når luk > gårsdagens high."""
    ibs = (df.close - df.low) / (df.high - df.low)
    return (df.close > sma(df.close, 200)) & (ibs < 0.2), df.close > df.high.shift(), 1


def double_seven(df):
    """Connors 'Double 7s': over SMA200 og luk = laveste i 7 dage -> køb; sælg ved højeste i 7 dage."""
    return ((df.close > sma(df.close, 200)) & (df.close <= df.close.rolling(7).min()),
            df.close >= df.close.rolling(7).max(), 1)


def trend_sma200(df):
    """Tidsserie-momentum: lang når luk > SMA200, ud når under (Faber 2007)."""
    s = sma(df.close, 200)
    return df.close > s, df.close < s, 1


def buy_and_hold(df):
    e = pd.Series(False, index=df.index)
    e.iloc[200] = True
    return e, pd.Series(False, index=df.index), 1


NO_STOP = {"buy_and_hold", "trend_sma200"}
STRATS = {"connors_rsi2": connors_rsi2, "ibs_meanrev": ibs_meanrev, "double_seven": double_seven,
          "trend_sma200": trend_sma200, "buy_and_hold": buy_and_hold}


def backtest(df, entry, exit_, side, spread, stop_atr=3.0, max_days=None):
    o, h, l, c = df.open.values, df.high.values, df.low.values, df.close.values
    a = atr(df).values
    en, ex = entry.values, exit_.values
    trades, pos = [], None
    for i in range(200, len(df) - 1):
        if pos is not None:
            t0, px_in, stop, risk = pos
            nights = max((df.index[i] - df.index[t0]).days, 0)
            out = None
            if (side == 1 and l[i] <= stop) or (side == -1 and h[i] >= stop):
                out = min(o[i], stop) if side == 1 else max(o[i], stop)
            elif ex[i] or (max_days and i - t0 >= max_days):
                out = o[i + 1]
                nights += (df.index[i + 1] - df.index[i]).days
            if out is not None:
                fin = px_in * FIN_RATE / 365 * nights
                pnl = (out - px_in) * side - spread - fin
                trades.append((df.index[t0], df.index[i], pnl / risk, pnl / px_in * 100, nights))
                pos = None
                continue
        if pos is None and en[i] and not np.isnan(a[i]):
            px_in = o[i + 1]
            risk = (stop_atr or 3.0) * a[i]  # R-enhed; uden stop bruges 3 ATR kun som målestok
            stop = px_in - side * risk if stop_atr else (-np.inf if side == 1 else np.inf)
            pos = (i + 1, px_in, stop, risk)
    if pos is not None:  # luk åben position ved sidste luk, så den tæller med
        t0, px_in, stop, risk = pos
        nights = (df.index[-1] - df.index[t0]).days
        pnl = (c[-1] - px_in) * side - spread - px_in * FIN_RATE / 365 * nights
        trades.append((df.index[t0], df.index[-1], pnl / risk, pnl / px_in * 100, nights))
    return pd.DataFrame(trades, columns=["open", "close", "r", "pct", "nights"])


def summarize(t, years):
    if len(t) == 0:
        return dict(n=0)
    w, lo = t.r[t.r > 0].sum(), -t.r[t.r <= 0].sum()
    eq = (1 + t.r / 100).cumprod()  # 1 % risiko pr. handel
    dd = (1 - eq / eq.cummax()).max() * 100
    yr = t.groupby(t.open.dt.year).r.sum()
    eq1x = (1 + t.pct / 100).cumprod()  # hele kontoen i kursværdi, ingen gearing
    dd1x = (1 - eq1x / eq1x.cummax()).max() * 100
    return dict(n=len(t), per_year=round(len(t) / years, 1), win=round((t.r > 0).mean() * 100),
                pf=round(w / lo, 2) if lo else np.inf, avg_r=round(t.r.mean(), 3),
                cagr_1pct=round((eq.iloc[-1] ** (1 / years) - 1) * 100, 1), max_dd=round(dd, 1),
                losing_years=int((yr < 0).sum()), years_tested=len(yr),
                days_in_mkt=round(t.nights.sum() / (years * 365) * 100),
                cagr_1x=round((eq1x.iloc[-1] ** (1 / years) - 1) * 100, 1), max_dd_1x=round(dd1x, 1))


def main(folder):
    rows = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith("_d1.csv"):
            continue
        sym = f[:-7]
        df = pd.read_csv(os.path.join(folder, f), parse_dates=["time"], index_col="time")
        extra = os.path.join(folder, f"{sym}_h1_recent.csv")
        if os.path.exists(extra):  # indeværende år findes kun som timedata: byg dagscandles
            h = pd.read_csv(extra, parse_dates=["time"], index_col="time")
            d = h.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
            df = pd.concat([df, d[d.index > df.index[-1]]])
        years = (df.index[-1] - df.index[200]).days / 365.25
        for name, fn in STRATS.items():
            entry, exit_, side = fn(df)
            t = backtest(df, entry, exit_, side, COSTS.get(sym, 0),
                         stop_atr=None if name in NO_STOP else 3.0)
            rows.append(dict(symbol=sym, strategy=name, **summarize(t, years),
                             period=f"{df.index[200]:%Y}-{df.index[-1]:%Y}"))
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 220, "display.max_columns", 20)
    print(res.to_string(index=False))
    return res


if __name__ == "__main__":
    main(sys.argv[1])
