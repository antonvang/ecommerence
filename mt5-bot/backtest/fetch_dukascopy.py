"""Henter EURUSD H1-candles (bid og ask) fra Dukascopy og gemmer som CSV.

Brug: python fetch_dukascopy.py --from 2020-01 --to 2026-08 --out eurusd_h1.csv
      python fetch_dukascopy.py --symbol USA500IDXUSD --daily --from 2013-01 --to 2026-12 --out us500_d1.csv
Output-kolonner: time,open,high,low,close (bid). Med --with-ask også spread (i pris).
Filer caches i --cache, så en afbrudt download fortsætter hvor den slap.
"""
import argparse
import lzma
import os
import struct
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{side}_candles_hour_1.bi5"
URL_DAY = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{side}_candles_day_1.bi5"
POINT = 1e-5
# Dukascopy gemmer priser som heltal; skalaen afhænger af instrumentet
POINTS = {"USDJPY": 1e-3, "XAUUSD": 1e-3, "USA500IDXUSD": 1e-3, "USATECHIDXUSD": 1e-3,
          "USA30IDXUSD": 1e-3, "DEUIDXEUR": 1e-3}


def fetch(url, cache_dir, tries=12):
    """Henter med cache på disk, så en afbrudt download kan genoptages."""
    cache = os.path.join(cache_dir, url.split("/datafeed/")[1].replace("/", "_"))
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return f.read()
    code = b""
    for attempt in range(tries):
        r = subprocess.run(["curl", "-sS", "-w", "\n%{http_code}", url], capture_output=True)
        body, _, code = r.stdout.rpartition(b"\n")
        if code in (b"200", b"404"):
            body = body if code == b"200" else b""
            with open(cache, "wb") as f:
                f.write(body)
            return body
        time.sleep(min(10 * (attempt + 1), 60))  # Dukascopy begrænser antal kald (429)
    raise RuntimeError(f"Kunne ikke hente {url} (sidste status {code!r})")


def parse(raw, month_start, point=POINT):
    if not raw:
        return []
    data = lzma.decompress(raw)
    rows = []
    for off in range(0, len(data) - 23, 24):
        t, o, c, lo, hi, _vol = struct.unpack(">5If", data[off:off + 24])
        rows.append((month_start + timedelta(seconds=t), o * point, hi * point, lo * point, c * point))
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
    ap.add_argument("--cache", default="dukascopy_cache")
    ap.add_argument("--daily", action="store_true", help="dagscandles (én fil pr. år) i stedet for H1")
    ap.add_argument("--with-ask", action="store_true", help="hent også ask for rigtig spread (dobbelt så mange kald)")
    a = ap.parse_args()
    start = tuple(int(x) for x in a.start.split("-"))
    end = tuple(int(x) for x in a.end.split("-"))

    os.makedirs(a.cache, exist_ok=True)
    if a.daily:
        return fetch_daily(a, start[0], end[0])
    sides_to_get = ("BID", "ASK") if a.with_ask else ("BID",)
    frames = []
    for y, m in months(start, end):
        month_start = datetime(y, m, 1, tzinfo=timezone.utc)
        sides = {}
        for side in sides_to_get:
            # Dukascopy nummererer måneder fra 0
            raw = fetch(URL.format(sym=a.symbol, y=y, m=m - 1, side=side), a.cache)
            sides[side] = pd.DataFrame(parse(raw, month_start, POINTS.get(a.symbol, POINT)),
                                       columns=["time", "open", "high", "low", "close"]).set_index("time")
            time.sleep(2.0)
        bid = sides["BID"]
        if bid.empty:
            print(f"{y}-{m:02d}: ingen data")
            continue
        # fjern weekend-candles uden handel (flade candles)
        bid = bid[(bid.high > bid.low)]
        df = bid.copy()
        if a.with_ask:
            ask = sides["ASK"]
            spread = ((ask.open - bid.open) + (ask.close - bid.close)) / 2
            df["spread"] = spread.reindex(df.index)
        frames.append(df)
        print(f"{y}-{m:02d}: {len(df)} candles", flush=True)

    out = pd.concat(frames)
    out.index = out.index.tz_localize(None)
    out.index.name = "time"
    out.to_csv(a.out)
    print(f"Gemt {len(out)} candles i {a.out}")


def fetch_daily(a, y0, y1):
    point = POINTS.get(a.symbol, POINT)
    frames = []
    for y in range(y0, y1 + 1):
        raw = fetch(URL_DAY.format(sym=a.symbol, y=y, side="BID"), a.cache)
        df = pd.DataFrame(parse(raw, datetime(y, 1, 1, tzinfo=timezone.utc), point),
                          columns=["time", "open", "high", "low", "close"]).set_index("time")
        df = df[df.high > df.low]  # weekender/helligdage uden handel
        frames.append(df)
        print(f"{a.symbol} {y}: {len(df)} dage", flush=True)
        time.sleep(2.0)
    out = pd.concat(frames)
    out.index = out.index.tz_localize(None)
    out.index.name = "time"
    out.to_csv(a.out)
    print(f"Gemt {len(out)} dage i {a.out}")


if __name__ == "__main__":
    main()
