"""Daytrading-test på aktieindeks (H1). Alle positioner lukkes samme dag (ingen natterisiko/swap).

Kun kendte, offentliggjorte effekter med standardregler (ingen tuning):
  1. intraday_momentum  Gao, Han, Li & Zhou (2018): afkast fra gårsdagens luk til kl. 15 (NY)
                        -> samme retning i sidste handelstime (15-16 NY).
  2. orb                Opening range breakout: range = 9:00-11:00 NY-candles; første H1-luk
                        udenfor range -> indgang, SL i modsatte side, exit ved lukketid.
  3. rsi2_daytrade      Connors RSI(2) < 10 over SMA200 (dagsdata) -> køb ved åbning, sælg ved luk.
  4. long_session       Kontrol: køb ved åbning, sælg ved luk hver dag.

H1-candles i UTC konverteres til New York-tid. 9:00-candlen indeholder åbningen kl. 9:30.
Afkast opgøres i % af kursværdi (1x) efter spread.

Brug: python intraday_research.py <mappe med USATECHIDXUSD_h1.csv / USA500IDXUSD_h1.csv>
"""
import os
import sys

import numpy as np
import pandas as pd

SPREAD = {"USATECHIDXUSD": 1.5, "USA500IDXUSD": 0.6}


def load(path):
    df = pd.read_csv(path, parse_dates=["time"], index_col="time")[["open", "high", "low", "close"]]
    df.index = df.index.tz_localize("UTC").tz_convert("America/New_York")
    df = df[df.index.dayofweek < 5]
    df["date"] = df.index.date
    df["hour"] = df.index.hour
    return df


def sessions(df):
    """Én række pr. handelsdag med de NY-timer vi bruger."""
    rows = []
    for date, g in df.groupby("date"):
        g = g.set_index("hour")
        if not all(h in g.index for h in range(9, 16)):
            continue  # halve dage/helligdage
        rows.append(dict(date=pd.Timestamp(date), g=g))
    return rows


def daily_close(df):
    s = df[df.hour == 15].set_index("date").close  # 15:00-candlens luk = 16:00 NY
    s.index = pd.to_datetime(s.index)
    return s


def intraday_momentum(df, spread):
    closes = daily_close(df)
    out = []
    for s in sessions(df):
        d, g = s["date"], s["g"]
        prev = closes[closes.index < d]
        if prev.empty:
            continue
        r = g.loc[14, "close"] / prev.iloc[-1] - 1  # gårsdagens luk -> kl. 15
        side = 1 if r > 0 else -1
        entry, exit_ = g.loc[15, "open"], g.loc[15, "close"]
        out.append((d, side, ((exit_ - entry) * side - spread) / entry * 100))
    return pd.DataFrame(out, columns=["date", "side", "pct"])


def orb(df, spread):
    out = []
    for s in sessions(df):
        d, g = s["date"], s["g"]
        hi, lo = g.loc[[9, 10], "high"].max(), g.loc[[9, 10], "low"].min()
        for h in range(11, 15):
            c = g.loc[h, "close"]
            side = 1 if c > hi else -1 if c < lo else 0
            if side == 0:
                continue
            entry = g.loc[h + 1, "open"]
            stop = lo if side == 1 else hi
            px = g.loc[15, "close"]
            for k in range(h + 1, 16):
                if (side == 1 and g.loc[k, "low"] <= stop) or (side == -1 and g.loc[k, "high"] >= stop):
                    px = stop
                    break
            out.append((d, side, ((px - entry) * side - spread) / entry * 100))
            break
    return pd.DataFrame(out, columns=["date", "side", "pct"])


def rsi(s, n):
    dd = s.diff()
    up = dd.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-dd.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def rsi2_daytrade(df, spread):
    closes = daily_close(df)
    sig = (closes > closes.rolling(200).mean()) & (rsi(closes, 2) < 10)
    out = []
    for s in sessions(df):
        d, g = s["date"], s["g"]
        prev = sig[sig.index < d]
        if prev.empty or not prev.iloc[-1]:
            continue
        entry, exit_ = g.loc[9, "close"], g.loc[15, "close"]  # ind kort efter åbning, ud ved luk
        out.append((d, 1, ((exit_ - entry) - spread) / entry * 100))
    return pd.DataFrame(out, columns=["date", "side", "pct"])


def long_session(df, spread):
    out = []
    for s in sessions(df):
        g = s["g"]
        entry, exit_ = g.loc[9, "close"], g.loc[15, "close"]
        out.append((s["date"], 1, ((exit_ - entry) - spread) / entry * 100))
    return pd.DataFrame(out, columns=["date", "side", "pct"])


STRATS = {"intraday_momentum": intraday_momentum, "orb": orb, "rsi2_daytrade": rsi2_daytrade,
          "long_session (kontrol)": long_session}


def summarize(t):
    if t.empty:
        return dict(n=0)
    years = max((t.date.iloc[-1] - t.date.iloc[0]).days / 365.25, 0.1)
    eq = (1 + t.pct / 100).cumprod()
    w, lo = t.pct[t.pct > 0].sum(), -t.pct[t.pct <= 0].sum()
    yr = t.groupby(t.date.dt.year).pct.sum()
    return dict(n=len(t), per_week=round(len(t) / years / 52, 1), win=round((t.pct > 0).mean() * 100),
                pf=round(w / lo, 2) if lo else np.inf, avg_pct=round(t.pct.mean(), 3),
                cagr_1x=round((eq.iloc[-1] ** (1 / years) - 1) * 100, 1),
                max_dd_1x=round((1 - eq / eq.cummax()).max() * 100, 1),
                losing_years=int((yr < 0).sum()), years=len(yr),
                per_year={int(k): round(v, 1) for k, v in yr.items()})


def main(folder):
    for f in sorted(os.listdir(folder)):
        if not f.endswith("_h1.csv") or f[:-7] not in SPREAD:
            continue
        sym = f[:-7]
        df = load(os.path.join(folder, f))
        print(f"\n=== {sym}  {df.index[0]:%Y-%m-%d} til {df.index[-1]:%Y-%m-%d}, spread {SPREAD[sym]}")
        for name, fn in STRATS.items():
            print(f"  {name:24} {summarize(fn(df, SPREAD[sym]))}")


if __name__ == "__main__":
    main(sys.argv[1])
