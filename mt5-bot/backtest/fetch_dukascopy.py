"""Henter EURUSD H1-candles (bid og ask) fra Dukascopy og gemmer som CSV.

Brug: python fetch_dukascopy.py --from 2020-01 --to 2026-08 --out eurusd_h1.csv
Output-kolonner: time,open,high,low,close (bid) samt spread (gennemsnit af åbning/lukning, i pris).
"""
import argparse
import lzma
import struct
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{side}_candles_hour_1.bi5"
POINT = 1e-5


def fetch(url, tries=8):
    for attempt in range(tries):
        r = subprocess.run(["curl", "-sS", "-w", "\n%{http_code}", url], capture_output=True)
        body, _, code = r.stdout.rpartition(b"\n")
        if code == b"200":
            return body
        if code == b"404":
            return b""
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Kunne ikke hente {url} (sidste status {code!r})")


def parse(raw, month_start):
    if not raw:
        return []
    data = lzma.decompress(raw)
    rows = []
    for off in range(0, len(data) - 23, 24):
        t, o, c, lo, hi, _vol = struct.unpack(">5If", data[off:off + 24])
        rows.append((month_start + timedelta(seconds=t), o * POINT, hi * POINT, lo * POINT, c * POINT))
    return rows


def months(start, end):
    y, m = start
    while (y, m) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--from", dest="start", default="2020-01")
    ap.add_argument("--to", dest="end", default="2026-08")
    ap.add_argument("--out", default="eurusd_h1.csv")
    a = ap.parse_args()
    start = tuple(int(x) for x in a.start.split("-"))
    end = tuple(int(x) for x in a.end.split("-"))

    frames = []
    for y, m in months(start, end):
        month_start = datetime(y, m, 1, tzinfo=timezone.utc)
        sides = {}
        for side in ("BID", "ASK"):
            # Dukascopy nummererer måneder fra 0
            raw = fetch(URL.format(sym=a.symbol, y=y, m=m - 1, side=side))
            sides[side] = pd.DataFrame(parse(raw, month_start),
                                       columns=["time", "open", "high", "low", "close"]).set_index("time")
            time.sleep(1.0)
        bid, ask = sides["BID"], sides["ASK"]
        if bid.empty:
            print(f"{y}-{m:02d}: ingen data")
            continue
        # fjern weekend-candles uden handel (flade candles)
        bid = bid[(bid.high > bid.low)]
        df = bid.copy()
        spread = ((ask.open - bid.open) + (ask.close - bid.close)) / 2
        df["spread"] = spread.reindex(df.index)
        frames.append(df)
        print(f"{y}-{m:02d}: {len(df)} candles, median spread {df.spread.median() / 1e-4:.2f} pips", flush=True)

    out = pd.concat(frames)
    out.index = out.index.tz_localize(None)
    out.index.name = "time"
    out.to_csv(a.out)
    print(f"Gemt {len(out)} candles i {a.out}")


if __name__ == "__main__":
    main()
