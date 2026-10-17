"""Market data for the engine: Binance USD-M perpetual 1-hour klines and funding rates from the free public archive
(data.binance.vision), cached as the original monthly zip files with SHA-256 recorded by the lab's data gateway.

Data policy (fixed in code, see lab/README.md):
- universe: 8 liquid perpetuals that no earlier experiment in this project examined (BTC/ETH/SOL are excluded because
  tsmom_v1 opened their 2024-2026 holdout, and BTC 2023 was used by Mission 3);
- train 2023-01..2023-08, validation 2023-09..2023-12, holdout 2024 (sealed: only in lifecycle VALIDATION);
- PROTOCOL v3 (research/PROTOCOL_V3.md): train3 2022-01..2023-06, validation3 2023-07..2023-12, same 2024 holdout;
- 2024 holdouts of 30-coin universes exclude BTC/ETH/SOL (already seen by L14_tsmom_v1; PROTOCOL v3 amendment 1);
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
# research/PROTOCOL_V2.md amendment 3: first 30 of the ordered candidate list with every monthly file (HEAD check only)
UNIVERSE_30 = tuple(c + "USDT" for c in ("BTC ETH BNB XRP SOL ADA DOGE TRX DOT LINK AVAX LTC BCH ATOM ETC XLM NEAR FIL "
                                         "UNI AAVE ALGO VET ICP EOS XTZ THETA AXS SAND MANA APE").split())
# PROTOCOL v3 universe: same rule on 2022-01..2024-12 (ICP, APE out; CRV, SNX in)
UNIVERSE_30_V3 = tuple(c + "USDT" for c in ("BTC ETH BNB XRP SOL ADA DOGE TRX DOT LINK AVAX LTC BCH ATOM ETC XLM NEAR "
                                            "FIL UNI AAVE ALGO VET EOS XTZ THETA AXS SAND MANA CRV SNX").split())
HOLDOUT_SEEN = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
# PROTOCOL v3 amendment 2: coins with daily CoinMetrics community SplyCur and CapMVRVCur for 2022-2024 (catalog check)
UNIVERSE_CM16 = tuple(c + "USDT" for c in "XRP ADA DOGE LINK LTC BCH ETC XLM UNI AAVE ALGO MANA CRV SNX BTC ETH".split())
FORWARD_MIN = datetime(2026, 11, 1, tzinfo=timezone.utc).timestamp()   # earliest forward window start (amendment 2)
FORWARD_LAG_S = 7 * 86400                                              # monthly files are published after month end
CLOCK = time.time                                                      # replaceable in tests (forward-window guard)
SPLITS = {"train": ((2023, 1), (2023, 8)), "validation": ((2023, 9), (2023, 12)), "holdout": ((2024, 1), (2024, 12)),
          "train3": ((2022, 1), (2023, 6)), "validation3": ((2023, 7), (2023, 12))}
GATEWAY_SPLIT = {"train": "dev", "validation": "validation", "holdout": "holdout", "train3": "dev",
                 "validation3": "validation"}
DAY = 86400
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


def window(split, now=None):
    (y0, m0), (y1, m1) = SPLITS[split]
    a = datetime(y0, m0, 1, tzinfo=timezone.utc).timestamp()
    b = datetime(y1 + (m1 == 12), 1 if m1 == 12 else m1 + 1, 1, tzinfo=timezone.utc).timestamp()
    if split.startswith("fwd"):
        # forward observation windows (amendment 2): only new data, and only once the window is over
        if a < FORWARD_MIN:
            raise ReservedData("forward windows start on or after 2026-11-01; earlier 2025+ data stays reserved")
        if (now or CLOCK()) < b + FORWARD_LAG_S:
            raise ReservedData("forward window has not ended (plus publication lag); its data may not be read yet")
    elif b > RESERVED_FROM:
        raise ReservedData("windows on or after 2025-01-01 are reserved")
    return int(a), int(b) - 1


def forward_split(start_ts, months=6):
    """Register (idempotently) a forward window of whole calendar months starting at the month of start_ts."""
    d = datetime.fromtimestamp(start_ts, timezone.utc)
    y1, m1 = d.year + (d.month + months - 2) // 12, (d.month + months - 2) % 12 + 1
    name = f"fwd{d.year}{d.month:02d}"
    SPLITS[name] = ((d.year, d.month), (y1, m1))
    GATEWAY_SPLIT[name] = "forward"
    return name


def window_bounds(split):
    """Window start/end without the read guards (for scheduling and display only; reads always go through window())."""
    (y0, m0), (y1, m1) = SPLITS[split]
    a = datetime(y0, m0, 1, tzinfo=timezone.utc).timestamp()
    b = datetime(y1 + (m1 == 12), 1 if m1 == 12 else m1 + 1, 1, tzinfo=timezone.utc).timestamp()
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


def load_volume(paths, split):
    """Hourly quote-asset volume {bar open ts: volume} (kline column 8) clipped to the split window."""
    a, b = window(split)
    out = {}
    for p in sorted(paths["klines"]):
        for r in _rows(p):
            ts = int(r[0]) // 1000
            if ts > 10 ** 11:
                ts //= 1000
            if a <= ts <= b and len(r) > 7:
                out.setdefault(ts, float(r[7]))
    return out


def load_taker(paths, split):
    """Hourly aggressive-buy quote volume {bar open ts: volume} (kline column 11, taker_buy_quote_volume)."""
    a, b = window(split)
    out = {}
    for p in sorted(paths["klines"]):
        for r in _rows(p):
            ts = int(r[0]) // 1000
            if ts > 10 ** 11:
                ts //= 1000
            if a <= ts <= b and len(r) > 10:
                out.setdefault(ts, float(r[10]))
    return out


# ---------- PROTOCOL v3 external series (all cached per window; nothing outside the window is stored) ----------
METRICS_URL = "https://data.binance.vision/data/futures/um/daily/metrics"
METRICS_MIN_ROWS = 200


def _sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _days(split):
    a, b = window(split)
    return list(range(a, b + 1, DAY))


def _parse_metrics(zpath):
    """{day start ts: {oi, top, acct, rows}} from one daily metrics zip (5-minute rows)."""
    rows = []
    for r in _rows(zpath):
        try:
            ts = int(datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
            rows.append((ts, float(r[3] or "nan"), float(r[5] or "nan"), float(r[6] or "nan")))
        except (ValueError, IndexError):
            continue
    out = {}
    for ts, oi, top, acct in sorted(rows):
        d = out.setdefault(ts - ts % DAY, {"oi": None, "top": [], "acct": [], "rows": 0})
        d["rows"] += 1
        if oi == oi:
            d["oi"] = oi                                   # last valid value of the day
        if top == top and top > 0:
            d["top"].append(top)
        if acct == acct and acct > 0:
            d["acct"].append(acct)
    return {k: {"oi": v["oi"], "top": (sum(v["top"]) / len(v["top"])) if v["top"] else None,
                "acct": (sum(v["acct"]) / len(v["acct"])) if v["acct"] else None, "rows": v["rows"]}
            for k, v in out.items()}


def metrics_for(sym, split, get=None, threads=8):
    """Download the window's daily metrics zips and consolidate them into one per-symbol file with a SHA-256
    manifest of the source files. Returns the consolidated path."""
    import json
    from concurrent.futures import ThreadPoolExecutor
    window(split)
    out = os.path.join(CACHE, "metrics_daily", f"{sym}-{split}.json")
    if os.path.exists(out):
        return out

    def one(day):
        name = f"{sym}-metrics-{datetime.fromtimestamp(day, timezone.utc):%Y-%m-%d}.zip"
        return _fetch(f"{METRICS_URL}/{sym}/{name}", os.path.join(CACHE, "metrics", sym, name), get)

    with ThreadPoolExecutor(threads) as ex:
        paths = [x for x in ex.map(one, _days(split)) if x]
    a, b = window(split)
    days, manifest = {}, {}
    for zp in paths:
        manifest[os.path.basename(zp)] = _sha(zp)
        for d, v in _parse_metrics(zp).items():
            if a <= d <= b:
                days[str(d)] = v
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".part", "w", encoding="utf-8") as f:
        json.dump({"symbol": sym, "split": split, "days": days, "manifest": manifest}, f, sort_keys=True)
    os.replace(out + ".part", out)
    return out


def load_metrics(path):
    import json
    with open(path, encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f)["days"].items()}


def _get_json(url, get=None):
    import json
    raw = get(url) if get else urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"}), timeout=120).read()
    return json.loads(raw)


def dvol_for(currency, split, get=None):
    """Deribit DVOL daily closes for the window only (request bounded to the window; paged)."""
    import json
    a, b = window(split)
    out = os.path.join(CACHE, "dvol", f"{currency}-{split}.json")
    if os.path.exists(out):
        return out
    days, end = {}, (b + 1) * 1000
    for _ in range(50):
        url = (f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency={currency}"
               f"&start_timestamp={a * 1000}&end_timestamp={end}&resolution=1D")
        res = _get_json(url, get)["result"]
        for ts, _o, _h, _l, c in res.get("data") or []:
            d = int(ts) // 1000
            d -= d % DAY
            if a <= d <= b:
                days[str(d)] = float(c)
        cont = res.get("continuation")
        if not cont or int(cont) <= a * 1000:
            break
        end = int(cont)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".part", "w", encoding="utf-8") as f:
        json.dump({"currency": currency, "split": split, "days": days, "source": "deribit get_volatility_index_data"},
                  f, sort_keys=True)
    os.replace(out + ".part", out)
    return out


def stable_for(split, get=None):
    """DefiLlama total stablecoin supply (USD-pegged). The API returns the full history; only rows inside the window
    are kept and stored, the rest is discarded before any computation (PROTOCOL v3 section 4)."""
    import json
    a, b = window(split)
    out = os.path.join(CACHE, "stable", f"all-{split}.json")
    if os.path.exists(out):
        return out
    days = {}
    for row in _get_json("https://stablecoins.llama.fi/stablecoincharts/all", get):
        d = int(row.get("date", 0))
        d -= d % DAY
        if a <= d <= b:
            v = (row.get("totalCirculatingUSD") or {}).get("peggedUSD")
            if v is not None:
                days[str(d)] = float(v)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".part", "w", encoding="utf-8") as f:
        json.dump({"split": split, "days": days, "source": "stablecoins.llama.fi/stablecoincharts/all (window only)"},
                  f, sort_keys=True)
    os.replace(out + ".part", out)
    return out


def fred_for(series, split, get=None):
    """FRED daily series via the keyless graph CSV, requested only for the window (cosd/coed)."""
    import json
    a, b = window(split)
    out = os.path.join(CACHE, "fred", f"{series}-{split}.json")
    if os.path.exists(out):
        return out
    d0 = datetime.fromtimestamp(a, timezone.utc).strftime("%Y-%m-%d")
    d1 = datetime.fromtimestamp(b, timezone.utc).strftime("%Y-%m-%d")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={d0}&coed={d1}"
    raw = get(url) if get else urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"}), timeout=120).read()
    days = {}
    for r in csv.reader(io.StringIO(raw.decode("utf-8"))):
        if len(r) < 2 or not r[0][:1].isdigit() or r[1] in ("", "."):
            continue
        ts = int(datetime.strptime(r[0], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        if a <= ts <= b:
            days[str(ts)] = float(r[1])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".part", "w", encoding="utf-8") as f:
        json.dump({"series": series, "split": split, "days": days, "source": url}, f, sort_keys=True)
    os.replace(out + ".part", out)
    return out


def cm_for(metric, split, symbols, get=None):
    """CoinMetrics community daily metric for the symbols, requested only for the window (paged)."""
    import json
    a, b = window(split)
    out = os.path.join(CACHE, "coinmetrics", f"{metric}-{split}.json")
    if os.path.exists(out):
        return out
    assets = ",".join(s.replace("USDT", "").lower() for s in symbols)
    d0 = datetime.fromtimestamp(a, timezone.utc).strftime("%Y-%m-%d")
    d1 = datetime.fromtimestamp(b, timezone.utc).strftime("%Y-%m-%d")
    url = (f"https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets={assets}&metrics={metric}"
           f"&frequency=1d&start_time={d0}&end_time={d1}&page_size=10000")
    per = {}
    for _ in range(200):
        res = _get_json(url, get)
        for row in res.get("data") or []:
            ts = int(datetime.strptime(row["time"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
            if a <= ts <= b and row.get(metric) not in (None, ""):
                per.setdefault(row["asset"].upper() + "USDT", {})[str(ts)] = float(row[metric])
        url = res.get("next_page_url")
        if not url:
            break
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out + ".part", "w", encoding="utf-8") as f:
        json.dump({"metric": metric, "split": split, "days": per, "source": "community-api.coinmetrics.io"}, f,
                  sort_keys=True)
    os.replace(out + ".part", out)
    return out


def load_cm(path):
    import json
    with open(path, encoding="utf-8") as f:
        return {s: {int(k): v for k, v in d.items()} for s, d in json.load(f)["days"].items()}


def load_days(path):
    import json
    with open(path, encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f)["days"].items()}


def coverage(days, split):
    return len([d for d in _days(split) if d in days]) / len(_days(split))


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
