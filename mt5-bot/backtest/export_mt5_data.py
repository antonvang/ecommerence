"""Eksporterer H1-candles fra din egen MetaTrader 5 (Windows) til CSV for research.py.

Kræver: pip install MetaTrader5 pandas, og MT5 installeret og logget ind.
Brug:   python export_mt5_data.py --symbol EURUSD --years 7 --out eurusd_h1.csv
"""
import argparse
from datetime import datetime, timedelta

import MetaTrader5 as mt5
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--years", type=int, default=7)
    ap.add_argument("--out", default="eurusd_h1.csv")
    a = ap.parse_args()

    if not mt5.initialize():
        raise SystemExit(f"Kunne ikke forbinde til MT5: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(a.symbol, True):
            raise SystemExit(f"Symbolet {a.symbol} findes ikke. Prøv fx EURUSD+ eller EURUSD.a")
        end = datetime.now()
        start = end - timedelta(days=365 * a.years)
        rates = mt5.copy_rates_range(a.symbol, mt5.TIMEFRAME_H1, start, end)
        if rates is None or len(rates) == 0:
            raise SystemExit(f"Ingen data: {mt5.last_error()}. Åbn en {a.symbol} H1-graf og scroll tilbage, så MT5 henter historik.")
        info = mt5.symbol_info(a.symbol)
    finally:
        mt5.shutdown()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["spread"] = df["spread"] * info.point
    df[["time", "open", "high", "low", "close", "spread"]].to_csv(a.out, index=False)
    print(f"Gemt {len(df)} candles ({df.time.iloc[0]:%Y-%m-%d} til {df.time.iloc[-1]:%Y-%m-%d}) i {a.out}")
    print(f"Median spread: {df.spread.median() / 0.0001:.2f} pips (serverens tidszone, ikke UTC)")


if __name__ == "__main__":
    main()
