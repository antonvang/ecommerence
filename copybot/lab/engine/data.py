"""Market data for the engine: Binance USD-M perpetual 1-hour klines and funding rates from the free public archive
(data.binance.vision), cached as the original monthly zip files with SHA-256 recorded by the lab's data gateway.

Data policy (fixed in code, see lab/README.md):
- universe: 8 liquid perpetuals that no earlier experiment in this project examined (BTC/ETH/SOL are excluded because
  tsmom_v1 opened their 2024-2026 holdout, and BTC 2023 was used by Mission 3);
- train 2023-01..2023-08, validation 2023-09..2023-12, holdout 2024 (sealed: only in lifecycle VALIDATION);
- 2025-01-01 and later is reserved and always refused.
"""
from __future__ import annotations

import csv
import io
import os
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

from lab.db import HERE

UNIVERSE = ("BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "LTCUSDT", "AVAXUSDT", "DOTUSDT")
SPLITS = {"train": ((2023, 1), (2023, 8)), "validation": ((2023, 9), (2023, 12)), "holdout": ((2024, 1), (2024, 12))}
GATEWAY_SPLIT = {"train": "dev", "validation": "validation", "holdout": "holdout"}
RESERVED_FROM = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()
CACHE = os.path.join(HERE, "data", "lab", "market")
BASE = "https://data.binance.vision/data/futures/um/monthly"
HOUR = 3600


class ReservedData(Exception):
    pass


def months(split):
    (y0, m0), (y1, m1) = SPLITS[split]
    out, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def window(split):
    (y0, m0), (y1, m1) = SPLITS[split]
    a = datetime(y0, m0, 1, tzinfo=timezone.utc).timestamp()
    b = datetime(y1 + (m1 == 12), 1 if m1 == 12 else m1 + 1, 1, tzinfo=timezone.utc).timestamp()
    if b > RESERVED_FROM:
        raise ReservedData("windows on or after 2025-01-01 are reserved")
    return int(a), int(b) - 1


def _fetch(url, path, get=None):
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for i in range(4):
        try:
            data = get(url) if get else urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"}), timeout=120).read()
            with open(path + ".part", "wb") as f:
                f.write(data)
            os.replace(path + ".part", path)
            return path
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    raise IOError(f"download failed: {url}")


def files_for(sym, split, get=None):
    """Download (or reuse) the monthly zips for one symbol and split. Returns {'klines': [...], 'funding': [...]}."""
    window(split)                                         # raises for reserved windows
    out = {"klines": [], "funding": []}
    for y, m in months(split):
        k = f"{sym}-1h-{y}-{m:02d}.zip"
        p = _fetch(f"{BASE}/klines/{sym}/1h/{k}", os.path.join(CACHE, "klines", k), get)
        if p:
            out["klines"].append(p)
        f = f"{sym}-fundingRate-{y}-{m:02d}.zip"
        p = _fetch(f"{BASE}/fundingRate/{sym}/{f}", os.path.join(CACHE, "funding", f), get)
        if p:
            out["funding"].append(p)
    return out


def _rows(zpath):
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            with z.open(name) as f:
                for r in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if r and r[0][:1].isdigit():
                        yield r


def load(paths, split):
    """Parse cached zips into (bars, funding) clipped to the split window. bars: list of (ts, open, close) by hour."""
    a, b = window(split)
    bars, seen, dup = [], set(), 0
    for p in sorted(paths["klines"]):
        for r in _rows(p):
            ts = int(r[0]) // 1000
            if ts > 10 ** 11:
                ts //= 1000
            if not a <= ts <= b:
                continue
            if ts in seen:
                dup += 1
                continue
            seen.add(ts)
            bars.append((ts, float(r[1]), float(r[4])))
    bars.sort()
    funding = {}
    for p in sorted(paths["funding"]):
        for r in _rows(p):
            ts = int(r[0]) // 1000
            if a <= ts <= b:
                funding[ts - ts % HOUR] = float(r[2])
    return bars, funding, dup


def quality(bars, split, duplicates=0):
    """Gaps, duplicates, ordering and price sanity for one symbol."""
    a, b = window(split)
    expected = (b + 1 - a) // HOUR
    ts = [x[0] for x in bars]
    gaps = sum(1 for i in range(1, len(ts)) if ts[i] - ts[i - 1] != HOUR)
    bad = sum(1 for x in bars if x[1] <= 0 or x[2] <= 0)
    monotonic = all(ts[i] > ts[i - 1] for i in range(1, len(ts)))
    cov = len(bars) / expected if expected else 0.0
    return {"bars": len(bars), "expected": expected, "coverage": cov, "gaps": gaps, "duplicates": duplicates,
            "nonpositive_prices": bad, "monotonic": monotonic,
            "ok": cov >= 0.99 and bad == 0 and monotonic and duplicates == 0}
