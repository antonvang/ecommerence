"""ICT/"Smart Money"-inspireret daytrading på aktieindeks, sat på faste regler (H1-niveau).

Regler er fastlagt før test (ingen tuning):
  london_sweep   London-range = NY-candles 03:00-07:00 (dvs. 03-08 NY).
                 I NY-vinduet 08:00-11:00: candle går over London-high men LUKKER under
                 -> short ved næste åbning. Stop = sweep-candlens high. Mål = London-low.
                 Spejlvendt for long. Højst én handel pr. dag, alt lukkes 15:55 NY.
  pdh_sweep      Samme logik med gårsdagens high/low (sessionen 09-16 NY) i vinduet 09-12.
  london_break   Kontrol (modsat hypotese): LUK over London-high -> long, mål 2R.

Afkast i % af kursværdi (1x) efter spread. Alle positioner lukkes samme dag.

Brug: python ict_research.py <mappe med USATECHIDXUSD_h1.csv / USA500IDXUSD_h1.csv>
"""
import os
import sys

import numpy as np
import pandas as pd

from intraday_research import SPREAD, load, summarize


def _manage(g, start_hour, side, entry, stop, target, spread):
    """Følg handlen time for time til stop, mål eller lukketid (15:00-candlens luk)."""
    px = g.loc[15, "close"] if 15 in g.index else g.iloc[-1].close
    for h in range(start_hour, 16):
        if h not in g.index:
            continue
        lo, hi = g.loc[h, "low"], g.loc[h, "high"]
        if side == -1:
            if hi >= stop:
                px = stop
                break
            if lo <= target:
                px = target
                break
        else:
            if lo <= stop:
                px = stop
                break
            if hi >= target:
                px = target
                break
    return ((px - entry) * side - spread) / entry * 100


def sweep_strategy(df, spread, ref="london", window=(8, 11), reverse=True):
    out = []
    days = list(df.groupby("date"))
    prev_sess = None
    for date, g in days:
        g = g.set_index("hour")
        sess = g.loc[[h for h in range(9, 16) if h in g.index]]
        if not all(h in g.index for h in range(3, 16)):
            prev_sess = sess if len(sess) else prev_sess
            continue
        if ref == "london":
            rh, rl = g.loc[3:7, "high"].max(), g.loc[3:7, "low"].min()
        else:
            if prev_sess is None or prev_sess.empty:
                prev_sess = sess
                continue
            rh, rl = prev_sess.high.max(), prev_sess.low.min()
        prev_sess = sess
        for h in range(window[0], window[1] + 1):
            bar = g.loc[h]
            if reverse:
                if bar.high > rh and bar.close < rh:
                    side, stop, target = -1, bar.high, rl
                elif bar.low < rl and bar.close > rl:
                    side, stop, target = 1, bar.low, rh
                else:
                    continue
            else:
                if bar.close > rh:
                    side, stop = 1, rl
                elif bar.close < rl:
                    side, stop = -1, rh
                else:
                    continue
            entry = g.loc[h + 1, "open"]
            risk = (entry - stop) * side
            if risk <= 0:
                break  # allerede forbi stoppet ved indgang: spring dagen over
            if not reverse:
                target = entry + side * 2 * risk
            if (target - entry) * side <= 0:
                break
            out.append((pd.Timestamp(date), side, _manage(g, h + 1, side, entry, stop, target, spread)))
            break
    return pd.DataFrame(out, columns=["date", "side", "pct"])


STRATS = {
    "london_sweep": dict(ref="london", window=(8, 11), reverse=True),
    "pdh_sweep": dict(ref="prevday", window=(9, 12), reverse=True),
    "london_break (kontrol)": dict(ref="london", window=(8, 11), reverse=False),
}


def main(folder):
    for f in sorted(os.listdir(folder)):
        if not f.endswith("_h1.csv") or f[:-7] not in SPREAD:
            continue
        sym = f[:-7]
        df = load(os.path.join(folder, f))
        print(f"\n=== {sym}  {df.index[0]:%Y-%m-%d} til {df.index[-1]:%Y-%m-%d}, spread {SPREAD[sym]}")
        for name, kw in STRATS.items():
            t = sweep_strategy(df, SPREAD[sym], **kw)
            s = summarize(t)
            if len(t):
                s["long/short"] = f"{int((t.side == 1).sum())}/{int((t.side == -1).sum())}"
            print(f"  {name:24} {s}")


if __name__ == "__main__":
    main(sys.argv[1])
