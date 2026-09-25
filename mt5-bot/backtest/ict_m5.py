"""ICT/TJR-inspireret daytrading på 5-minutters data eksporteret fra MT5 (export_mt5_data.py --tf M5).

Regler fastlagt før test (ingen tuning). Tider i New York-tid:
  sweep          London-range = 03:00-08:00. Kl. 08:30-11:00: en M5-candle går over London-high
                 men lukker under -> short ved næste åbning. Stop = sweep-candlens high,
                 mål = London-low. Spejlvendt for long. Én handel pr. dag, alt lukkes 15:55.
  sweep_fvg      Som sweep, men indgang først når der efter sweepet (inden for 6 candles) dannes
                 en fair value gap i vendingens retning (short: high[i] < low[i-2]).
                 Stop = højeste high siden sweepet, mål = London-low.
  silver_bullet  Kl. 10:00-11:00: første FVG. Retning = retning af FVG. Stop = candlen før gap,
                 mål 2R. Lukkes senest 15:55.
  break          Kontrol: M5-luk over London-high -> long (mål 2R), under London-low -> short.

Spread: MT5-eksportens spread-kolonne (rigtig Vantage-spread) betales ved indgang.
Afkast i % af kursværdi (1x).

Brug: python ict_m5.py nas100_m5.csv [server_minus_ny_timer=7]
"""
import sys

import numpy as np
import pandas as pd

from intraday_research import summarize


def load(path, offset):
    df = pd.read_csv(path, parse_dates=["time"])
    df["time"] = df["time"] - pd.Timedelta(hours=offset)  # servertid -> New York-tid
    df = df[df.time.dt.dayofweek < 5].set_index("time")
    if "spread" not in df:
        df["spread"] = 0.0
    df["date"] = df.index.date
    df["hm"] = df.index.hour * 100 + df.index.minute
    return df


def run_trade(g, i0, side, entry, stop, target, spread):
    """Følg handlen candle for candle fra position i0 til stop/mål/15:55."""
    px = None
    for j in range(i0, len(g)):
        row = g.iloc[j]
        if row.hm >= 1555:
            px = row.open
            break
        if side == -1:
            if row.high >= stop:
                px = max(row.open, stop)
                break
            if row.low <= target:
                px = target
                break
        else:
            if row.low <= stop:
                px = min(row.open, stop)
                break
            if row.high >= target:
                px = target
                break
    if px is None:
        px = g.iloc[-1].close
    return ((px - entry) * side - spread) / entry * 100


def day_strategy(g, mode):
    lon = g[(g.hm >= 300) & (g.hm < 800)]
    if len(lon) < 50 or g.hm.max() < 1555:
        return None
    rh, rl = lon.high.max(), lon.low.min()
    idx = list(range(len(g)))
    hm, hi, lo, cl = g.hm.values, g.high.values, g.low.values, g.close.values

    if mode in ("sweep", "sweep_fvg", "break"):
        for i in idx[:-1]:
            if not (830 <= hm[i] < 1100):
                continue
            if mode == "break":
                side = 1 if cl[i] > rh else -1 if cl[i] < rl else 0
                if side == 0:
                    continue
                entry = g.iloc[i + 1].open
                stop = rl if side == 1 else rh
                risk = (entry - stop) * side
                if risk <= 0:
                    return None
                return run_trade(g, i + 1, side, entry, stop, entry + side * 2 * risk, g.iloc[i + 1].spread)
            side = -1 if (hi[i] > rh and cl[i] < rh) else 1 if (lo[i] < rl and cl[i] > rl) else 0
            if side == 0:
                continue
            k = i
            if mode == "sweep_fvg":
                k = None
                for j in range(i + 2, min(i + 7, len(g) - 1)):
                    if (side == -1 and hi[j] < lo[j - 2]) or (side == 1 and lo[j] > hi[j - 2]):
                        k = j
                        break
                if k is None:
                    return None
            ext = hi[i:k + 1].max() if side == -1 else lo[i:k + 1].min()
            entry = g.iloc[k + 1].open
            target = rl if side == -1 else rh
            if (entry - ext) * side <= 0 or (target - entry) * side <= 0:
                return None
            return run_trade(g, k + 1, side, entry, ext, target, g.iloc[k + 1].spread)

    if mode == "silver_bullet":
        for j in idx[2:-1]:
            if not (1000 <= hm[j] < 1100):
                continue
            if lo[j] > hi[j - 2]:
                side, stop = 1, lo[j - 1]
            elif hi[j] < lo[j - 2]:
                side, stop = -1, hi[j - 1]
            else:
                continue
            entry = g.iloc[j + 1].open
            risk = (entry - stop) * side
            if risk <= 0:
                continue
            return run_trade(g, j + 1, side, entry, stop, entry + side * 2 * risk, g.iloc[j + 1].spread)
    return None


def main(path, offset=7):
    df = load(path, offset)
    print(f"Data {df.index[0]} til {df.index[-1]} (NY-tid), {len(df)} M5-candles, "
          f"median spread {df.spread.median():.2f}")
    for mode in ("sweep", "sweep_fvg", "silver_bullet", "break"):
        rows = []
        for date, g in df.groupby("date"):
            r = day_strategy(g.reset_index(drop=True), mode)
            if r is not None:
                rows.append((pd.Timestamp(date), 0, r))
        t = pd.DataFrame(rows, columns=["date", "side", "pct"])
        print(f"  {mode:14} {summarize(t)}")


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 7)
