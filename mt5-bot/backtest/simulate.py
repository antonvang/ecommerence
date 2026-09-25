"""Python-genskabelse af TrendPullbackEA.mq5 til backtest uden MetaTrader.

Følger EA'ens regler: signal ved lukket H1-candle, indgang ved næste candles
åbning plus spread, ATR-baseret SL/TP, lotstørrelse efter % risiko (0,01-trin),
breakeven ved +1R, handelstider og dagligt tabsstop.

Konservative antagelser: rammes SL og TP i samme candle, tæller det som SL.
Breakeven aktiveres først fra candlen efter +1R blev nået.

Brug:  python simulate.py [--csv fil.csv] [--spread-pips 1.0] [--risk 1.0]
CSV skal have kolonnerne time,open,high,low,close (H1, EURUSD).
Uden --csv bruges de EURUSD H1-data, der følger med pakken `backtesting`.
"""
import argparse

import numpy as np
import pandas as pd

P = dict(fast=50, slow=200, rsi=14, rsi_buy=40.0, rsi_sell=60.0, atr=14,
         sl_mult=1.5, tp_mult=3.0, max_daily_loss=5.0, overshoot=1.5,
         be_r=1.0, start_hour=7, end_hour=20)
CONTRACT = 100_000  # EURUSD: 1 lot = 100.000 EUR, kontoen i USD


def load(csv):
    if csv:
        df = pd.read_csv(csv, parse_dates=["time"], index_col="time")
        df.columns = [c.lower() for c in df.columns]
    else:
        from backtesting.test import EURUSD
        df = EURUSD.rename(columns=str.lower)
    return df[["open", "high", "low", "close"]].astype(float)


def indicators(df):
    c = df["close"]
    df["ema_fast"] = c.ewm(span=P["fast"], adjust=False).mean()
    df["ema_slow"] = c.ewm(span=P["slow"], adjust=False).mean()
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / P["rsi"], adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / P["rsi"], adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - c.shift()).abs(),
                    (df["low"] - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(P["atr"]).mean()  # MT5's iATR er et simpelt gennemsnit
    return df


def run(df, deposit, risk_pct, spread):
    balance = deposit
    trades, equity_curve = [], []
    pos = None
    day, day_start, blocked = None, deposit, False
    warmup = P["slow"] + 5

    for i in range(warmup, len(df) - 1):
        bar = df.iloc[i]
        t = df.index[i]

        if t.date() != day:
            day, day_start, blocked = t.date(), balance, False

        # --- styr åben position i denne candle (bid-priser; spread betalt ved indgang)
        if pos:
            hit_sl = bar.low <= pos["sl"] if pos["dir"] == 1 else bar.high + spread >= pos["sl"]
            hit_tp = bar.high >= pos["tp"] if pos["dir"] == 1 else bar.low + spread <= pos["tp"]
            exit_price = pos["sl"] if hit_sl else pos["tp"] if hit_tp else None
            if exit_price is not None:
                pnl = (exit_price - pos["entry"]) * pos["dir"] * pos["lots"] * CONTRACT
                balance += pnl
                trades.append(dict(open=pos["time"], close=t, dir=pos["dir"], lots=pos["lots"],
                                   pnl=pnl, result="SL" if hit_sl else "TP",
                                   be=pos["sl"] == pos["entry"]))
                pos = None
            elif not pos["be_done"]:
                fav = (bar.high - pos["entry"]) if pos["dir"] == 1 else (pos["entry"] - (bar.low + spread))
                if fav >= P["be_r"] * pos["risk_dist"]:
                    pos["sl"], pos["be_done"] = pos["entry"], True

        if balance <= day_start * (1 - P["max_daily_loss"] / 100):
            blocked = True
        equity_curve.append((t, balance))
        if pos or blocked:
            continue

        # --- signal ved lukket candle i, indgang ved åbning af candle i+1
        nxt_time = df.index[i + 1]
        wd, hr = nxt_time.weekday(), nxt_time.hour
        if wd >= 5 or (wd == 4 and hr >= 18) or not (P["start_hour"] <= hr < P["end_hour"]):
            continue
        prev = df.iloc[i - 1]
        up = bar.close > bar.ema_slow and bar.ema_fast > bar.ema_slow
        down = bar.close < bar.ema_slow and bar.ema_fast < bar.ema_slow
        buy = up and prev.rsi < P["rsi_buy"] <= bar.rsi
        sell = down and prev.rsi > P["rsi_sell"] >= bar.rsi
        if not (buy or sell):
            continue

        direction = 1 if buy else -1
        open_bid = df.iloc[i + 1].open
        entry = open_bid + spread if buy else open_bid
        sl_dist, tp_dist = bar.atr * P["sl_mult"], bar.atr * P["tp_mult"]
        loss_per_lot = sl_dist * CONTRACT
        risk_money = balance * risk_pct / 100
        lots = np.floor(risk_money / loss_per_lot / 0.01 + 1e-8) * 0.01
        if lots < 0.01:
            if 0.01 * loss_per_lot <= risk_money * P["overshoot"]:
                lots = 0.01
            else:
                continue
        pos = dict(time=nxt_time, dir=direction, entry=entry, lots=round(lots, 2),
                   sl=entry - direction * sl_dist, tp=entry + direction * tp_dist,
                   risk_dist=sl_dist, be_done=False)

    return pd.DataFrame(trades), pd.DataFrame(equity_curve, columns=["time", "balance"]).set_index("time")


def report(trades, curve, deposit, df):
    print(f"Data: EURUSD H1 {df.index[0]:%Y-%m-%d} til {df.index[-1]:%Y-%m-%d} ({len(df)} candles)")
    if trades.empty:
        print("Ingen handler.")
        return
    wins = trades[trades.pnl > 0]
    losses = trades[trades.pnl <= 0]
    gross_win, gross_loss = wins.pnl.sum(), -losses.pnl.sum()
    peak = curve.balance.cummax()
    max_dd = ((peak - curve.balance) / peak).max() * 100
    end = curve.balance.iloc[-1]
    print(f"Startkapital:     {deposit:.2f} USD")
    print(f"Slutkapital:      {end:.2f} USD  ({(end / deposit - 1) * 100:+.1f} %)")
    print(f"Antal handler:    {len(trades)}  (køb {int((trades.dir == 1).sum())}, salg {int((trades.dir == -1).sum())})")
    print(f"Win rate:         {len(wins) / len(trades) * 100:.1f} %")
    print(f"Profit factor:    {gross_win / gross_loss if gross_loss else float('inf'):.2f}")
    print(f"Maks. drawdown:   {max_dd:.1f} %")
    print(f"Gns. gevinst/tab: {wins.pnl.mean() if len(wins) else 0:.2f} / {losses.pnl.mean() if len(losses) else 0:.2f} USD")
    print(f"Udfald:           {trades.result.value_counts().to_dict()}, heraf breakeven-stop: {int((trades.be & (trades.result == 'SL')).sum())}")
    monthly = curve.balance.resample("ME").last().pct_change().dropna() * 100
    print("Afkast pr. måned (%):", ", ".join(f"{m:%Y-%m}: {v:+.1f}" for m, v in monthly.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--deposit", type=float, default=200.0)
    ap.add_argument("--risk", type=float, default=1.0)
    ap.add_argument("--spread-pips", type=float, default=1.0)
    a = ap.parse_args()
    data = indicators(load(a.csv))
    tr, cv = run(data, a.deposit, a.risk, a.spread_pips * 0.0001)
    report(tr, cv, a.deposit, data)
