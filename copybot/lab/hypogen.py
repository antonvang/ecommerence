"""PROTOCOL_V3 amendment 17: the automatic hypothesis pipeline. Observations become research tasks without a hand, and
nothing here trades, changes a paper account, a family, a gate or an alpha budget of the families.

- Candidates (points 1-3): fixed event types (titles of Binance announcements in the registry, detector news/1) times
  fixed outcomes on the coin's USD-M perp. Each event keeps its observation id, coin and time t = usable_from. Every
  candidate is recorded once (research.hypothesis, with its sources) and gets a priority each pass.
- Dedup (point 4): a key with a result is never screened again under this method; every result, negative ones too,
  is a hash-chained research.hypothesis_screen event. COVERED keys (H4/H5) are never screened.
- Screening (point 5): explore0 only (2020-03..2021-12), data.binance.vision through the lane's guarded fetch; one job
  at a time. Exploration, never evidence.
- Drafts (point 6) for SCREEN_PASS under data/lab/hypotheses; a lock (point 7) is a `LÅS-17 <key> <sha256>` line in the
  committed protocol plus the committed draft under research/drafts/auto, and only then the measurement job exists.
- Measurement (point 8): train3 gate, then validation3 at alpha_k = 0.05 * 2^-k; a reader refuses every month outside
  the phase and everything from 2024-01-01 (holdout and reserved data are never read).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import statistics
import time
from datetime import datetime, timezone

from lab import jobs, measure, news, pipeline
from lab.engine import data

RULE = "research/PROTOCOL_V3.md amendment 17"
METHOD = "m17"
M17C, RULE_C = "m17c", "research/PROTOCOL_V3.md amendment 17c"
M17E, RULE_E = "m17e", "research/PROTOCOL_V3.md amendment 17e"
M17G, RULE_G = "m17g", "research/PROTOCOL_V3.md amendment 17g"
G_TYPE = "coinbase_listing"                                # 17g: first trade on Coinbase (detector coinbase/1)
CANDIDATES = {M17C: 117, M17E: 124, M17G: 133}             # how many candidates a draft was selected among
HOUR, DAY = 3600, 86400
_T = lambda y, m: int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())          # noqa: E731
PHASES = {"explore0": ((2020, 3), (2021, 12)), "train3": ((2022, 1), (2023, 6)), "validation3": ((2023, 7), (2023, 12))}
END = int(measure.END)                                       # 2024-01-01: holdout from here, 2025+ reserved
SCREEN = "explore0"


def _w(text, *words):
    """Whole-word match of any phrase (amendment 17 precision: "Margin" is not "Margined", "Earn" is not "Learn")."""
    return any(re.search(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", text) for w in words)


def _has(*words):
    return lambda t: _w(t, *words)


TYPES = (                                                    # point 1: fixed; a new type needs a new amendment
    ("spot_listing", lambda t: t.startswith(("Binance Will List", "Binance Lists"))),
    ("innovation_zone", _has("Innovation Zone")),
    ("futures_listing", lambda t: _w(t, "Futures Will Launch") and _w(t, "Perpetual") and not _w(t, "Coin-Margined")),
    ("launchpool", _has("Launchpool")),
    ("network_swap", _has("Network Upgrade", "Hard Fork", "Mainnet", "Token Swap", "Contract Swap", "Migration",
                          "Redenomination")),
    ("delisting", lambda t: _w(t, "Will Delist", "to Delist") and not _w(t, "Futures")),
    ("futures_delisting", _has("Futures Will Delist", "Futures to Delist")),
    ("airdrop", _has("Airdrop")),
    ("staking", _has("Staking", "Savings", "Earn")),
    ("margin", lambda t: _w(t, "Margin") and not _w(t, "Tiers", "Futures") and _w(t, "Will Add", "Adds", "Enabled",
                                                                                     "Launch")),
    ("margin_tiers", _has("Leverage & Margin Tiers", "Leverage and Margin Tiers")),
    ("funding_interval", lambda t: _w(t, "Funding Rate") and _w(t, "Interval", "Frequency", "Settlement")),
)
OUTCOMES = ("ar_1d", "ar_7d", "fund_7d", "vol_3d", "volume_1d",       # point 2
            "far_1d", "far_7d", "sar_1d", "sar_7d")                  # 17a: from the first available price (perp, spot)
PRE = {"fund_7d", "vol_3d", "volume_1d"}                               # need (t - 7 d, t]
HORIZON = {"ar_1d": DAY, "ar_7d": 7 * DAY, "fund_7d": 7 * DAY, "vol_3d": 3 * DAY, "volume_1d": DAY,
           "far_1d": DAY, "far_7d": 7 * DAY, "sar_1d": DAY, "sar_7d": 7 * DAY}
RETURNS = ("ar_", "far_", "sar_")                             # returns: the 0.46 % cost check applies
FIRST_WITHIN = 72 * HOUR                                      # 17a: the first price must come by t + 72 h
COVERED = {"futures_listing|fund_7d|m17": "H4/H5 (amendments 16a, 16c)"}   # point 4
DEDUP_S = 30 * DAY
COVER = 0.9
MIN_SCREEN, MIN_HALF, P_SCREEN, P_PLACEBO, COST = 15, 5, 0.005, 0.05, 0.0046    # point 5
MIN_TRAIN, MIN_VALID, P_TRAIN, ALPHA = 15, 8, 0.05, 0.05                         # points 7 and 8
PLACEBO_SHIFT = 30 * DAY
HALF = _T(2021, 1)                                            # 2020 | 2021
LIVE_DAYS = 30
TTL = 600                                                     # candidates are rebuilt at most every 10 minutes
JOB = {"priority": 190, "max_attempts": 2, "timeout_s": 3600}
DIR = os.path.join(os.path.dirname(pipeline.ARTIFACTS), "hypotheses")
AUTO = "research/drafts/auto"
LOCK = re.compile(r"^LÅS-17 (\S+) ([0-9a-f]{64})\s*$", re.M)
EV_HYP, EV_SCREEN = "research.hypothesis", "research.hypothesis_screen"
_CACHE = {}


class Refused(data.ReservedData):
    pass


def key(etype, outcome, method=METHOD):
    return f"{etype}|{outcome}|{method}"


def fname(k):
    return k.replace("|", "__")


def bounds(phase):
    (y0, m0), (y1, m1) = PHASES[phase]
    return _T(y0, m0), min(END, _T(y1 + (m1 == 12), 1 if m1 == 12 else m1 + 1))


def types_of(title):
    t = title or ""
    return [name for name, f in TYPES if f(t)]


# ---------- amendment 17c: margin coins read from the title ----------
C_TYPES = ("margin",)
C_STOP = {"USD", "USDT", "BUSD", "USDC", "TUSD", "PAX", "USDP", "FDUSD", "DAI", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB",
          "NGN", "UAH", "BIDR", "IDRT", "ZAR", "BKRW", "VAI", "UST", "BNB", "BTC", "ETH", "NFT", "API", "VIP", "UTC", "AMA",
          "FAQ", "BSC", "APY", "APR", "ETF", "OTC", "P2P", "KYC", "DEX", "DAO", "NEW", "AND", "ALL"}
C_LISTS = (re.compile(r"(?:Adds|Will Add) (.+?) (?:on|to) (?:Binance )?(?:Isolated|Cross)"),
           re.compile(r"Margin Trading for (.+?) (?:Enabled|Pairs)"),
           re.compile(r"^(.+?) (?:Enabled|Now Available) on (?:Binance )?(?:Isolated |Cross )?Margin"))
C_PAIR = re.compile(r"(?<![A-Za-z0-9])([A-Z0-9]{2,12})/(?:USDT|BUSD|USDC|BTC|BNB|ETH|DOGE)(?![A-Za-z0-9])")
C_TICK = re.compile(r"(?=[A-Z0-9]{2,12}$)[A-Z0-9]*[A-Z][A-Z0-9]*")


def coins_c(title):
    """Point 2 of 17c: the tickers a margin title lists (fixed rules), without fiat, stablecoins and the stop words."""
    t, out = title or "", set()
    for rx in C_LISTS:
        for m in rx.finditer(t):
            out |= {w for w in re.split(r"[\s,&()]+|\band\b", m.group(1)) if C_TICK.fullmatch(w)}
    out |= set(C_PAIR.findall(t))
    return out - C_STOP


def _coins(p, etype, method):
    base = p.get("coins") or []
    if method == M17C and etype in C_TYPES:
        return sorted(set(base) | coins_c(p.get("title")))
    return base


# ---------- observations -> events (point 1) ----------
def _items(db):
    out = []
    for r in db.q("SELECT id, payload FROM observations WHERE detector=? AND metric='news_item' AND source LIKE "
                  "'%binance.com%' ORDER BY id", news.DETECTOR):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        out.append((r["id"], p))
    return out


def events(items, a, b, method=METHOD):
    """{type: [{obs, coin, t}]} for items usable in [a, b): one event per (type, coin) per DEDUP_S, the first. Under
    m17c (amendment 17c) a C_TYPES item's coins also include those its title lists."""
    out = {name: [] for name, _ in TYPES}
    last = {}
    for obs, p in sorted(items, key=lambda x: (x[1].get("usable_from") or 0, x[0])):
        t = p.get("usable_from")
        if not t or not a <= t < b:
            continue
        for etype in types_of(p.get("title")):
            for coin in _coins(p, etype, method):
                k = (etype, coin)
                if k in last and t - last[k] < DEDUP_S:
                    continue
                last[k] = t
                out[etype].append({"obs": obs, "coin": coin, "t": int(t)})
    return out


# ---------- amendment 17g: Coinbase listings (detector coinbase/1) ----------
def _items_g(db):
    from lab import coinbase
    out = []
    for r in db.q("SELECT id, payload FROM observations WHERE detector=? AND metric='cb_listing' ORDER BY id",
                  coinbase.DETECTOR):
        out.append((r["id"], json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]))
    return out


def events_g(items, a, b):
    """[{obs, coin, t}] in [a, b): one event per coin, its earliest USD market only (17g point 2)."""
    first = {}
    for obs, p in sorted(items, key=lambda x: (x[1].get("usable_from") or 0, x[0])):
        if p.get("coin") and p.get("usable_from") and p["coin"] not in first:
            first[p["coin"]] = {"obs": obs, "coin": p["coin"], "t": int(p["usable_from"])}
    return sorted((e for e in first.values() if a <= e["t"] < b), key=lambda e: (e["t"], e["obs"]))


def _evs(db, etype, method, a, b, items=None):
    """The events of one key: Coinbase listings under m17g, announcements otherwise."""
    if method == M17G:
        return events_g(_items_g(db), a, b)
    return events(items if items is not None else _items(db), a, b, method)[etype]


def live_counts(items, now):
    c = {name: 0 for name, _ in TYPES}
    for _, p in items:
        if not p.get("backfill") and (p.get("fetched_ts") or 0) >= now - LIVE_DAYS * DAY:
            for etype in types_of(p.get("title")):
                c[etype] += 1
    return c


def _months(a, b):
    y, m = datetime.fromtimestamp(a, timezone.utc).year, datetime.fromtimestamp(a, timezone.utc).month
    out = []
    while _T(y, m) <= b:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def need(ev, phase):
    """(symbol, kind, y, m) files an event needs inside the phase (its coin and BTCUSDT)."""
    a, b = bounds(phase)
    lo = max(a, ev["t"] - 7 * DAY - HOUR)
    hi = min(b - 1, ev["t"] + FIRST_WITHIN + 7 * DAY)
    return {(s, k, y, m) for s in (ev["coin"] + "USDT", "BTCUSDT") for k in ("klines", "funding", "spot")
            for y, m in _months(lo, hi)}


def _path(sym, kind, y, m):
    if kind == "spot":
        return os.path.join(data.CACHE, "spot_klines", f"{sym}-1h-{y}-{m:02d}.zip")
    if kind == "klines":
        return os.path.join(data.CACHE, "klines", f"{sym}-1h-{y}-{m:02d}.zip")
    return os.path.join(data.CACHE, "funding", f"{sym}-fundingRate-{y}-{m:02d}.zip")


def _url(sym, kind, y, m):
    if kind == "spot":
        return f"{data.SPOT_BASE}/klines/{sym}/1h/{sym}-1h-{y}-{m:02d}.zip"
    if kind == "klines":
        return f"{data.BASE}/klines/{sym}/1h/{sym}-1h-{y}-{m:02d}.zip"
    return f"{data.BASE}/fundingRate/{sym}/{sym}-fundingRate-{y}-{m:02d}.zip"


def _absent():
    try:
        from lab import families
        return families.absent()
    except Exception:                                       # noqa: BLE001 - no 404 list yet
        return set()


def missing(evs, phase):
    gone = _absent()
    files = set().union(*(need(e, phase) for e in evs)) if evs else set()
    return sum(1 for f in files if not os.path.exists(_path(*f)) and _url(*f) not in gone)


# ---------- candidates and priority (points 2-4) ----------
def results(db):
    out = {}
    for r in db.q("SELECT id, ts, payload FROM events WHERE kind=? ORDER BY id", EV_SCREEN):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        out[p["key"]] = p | {"event_id": r["id"], "ts": r["ts"]}
    return out


def priority(n, n30, miss, overlap):
    return round(2 * min(1.0, n / 40) + min(1.0, n30 / 5) + (1 if n >= MIN_SCREEN else 0) - min(1.0, miss / 200)
                 - overlap, 4)


def candidates(db, now=None, fresh=False):
    """All candidates (60 under 17, 48 more under 17a) with status and priority (cached TTL seconds per registry)."""
    now = now or time.time()
    c = _CACHE.get(db.path)
    if c and not fresh and now - c[0] < TTL:
        return c[1]
    items = _items(db)
    a, b = bounds(SCREEN)
    evs, live, done = events(items, a, b), live_counts(items, now), results(db)
    out = []
    for etype, _ in TYPES:
        miss = missing(evs[etype], SCREEN)
        for o in OUTCOMES:
            k = key(etype, o)
            overlap = (0.5 if any(x.split("|")[0] == etype and x != k for x in done) else 0) + \
                (0.25 if any(x.split("|")[1] == o and x != k for x in done) else 0)
            res = done.get(k)
            status = "COVERED" if k in COVERED else res["verdict"] if res else "QUEUED_FOR_SCREEN"
            ids = [e["obs"] for e in evs[etype]]
            out.append({"key": k, "type": etype, "outcome": o, "events": len(ids), "live_30d": live[etype],
                        "missing_files": miss, "overlap": overlap, "status": status,
                        "priority": priority(len(ids), live[etype], miss, overlap),
                        "sources": {"detector": news.DETECTOR, "events": len(ids), "first_obs": min(ids, default=None),
                                    "last_obs": max(ids, default=None), "events_sha256": hashlib.sha256(json.dumps(
                                        evs[etype], sort_keys=True).encode()).hexdigest()},
                        **({"covered_by": COVERED[k]} if k in COVERED else {})})
    evc = events(items, a, b, M17C)                         # amendment 17c point 3: only after m17 found no data
    for etype in C_TYPES:
        miss = missing(evc[etype], SCREEN)
        for o in OUTCOMES:
            if (done.get(key(etype, o)) or {}).get("verdict") != "UNTESTABLE":
                continue
            k = key(etype, o, M17C)
            res = done.get(k)
            ids = [e["obs"] for e in evc[etype]]
            out.append({"key": k, "type": etype, "outcome": o, "events": len(ids), "live_30d": live[etype],
                        "missing_files": miss, "overlap": 0.5, "status": res["verdict"] if res else "QUEUED_FOR_SCREEN",
                        "priority": priority(len(ids), live[etype], miss, 0.5), "rule": RULE_C,
                        "sources": {"detector": news.DETECTOR, "events": len(ids), "first_obs": min(ids, default=None),
                                    "last_obs": max(ids, default=None), "events_sha256": hashlib.sha256(json.dumps(
                                        evc[etype], sort_keys=True).encode()).hexdigest()}})
    for etype, _ in TYPES:                                  # amendment 17e point 3: an m17 FAIL without a placebo
        miss = missing(evs[etype], SCREEN)
        for o in OUTCOMES:
            r = done.get(key(etype, o)) or {}
            pn = (r.get("placebo") or {}).get("n")
            if r.get("verdict") != "SCREEN_FAIL" or pn is None or pn >= MIN_SCREEN:
                continue
            k = key(etype, o, M17E)
            res = done.get(k)
            ids = [e["obs"] for e in evs[etype]]
            out.append({"key": k, "type": etype, "outcome": o, "events": len(ids), "live_30d": live[etype],
                        "missing_files": miss, "overlap": 0.5, "status": res["verdict"] if res else "QUEUED_FOR_SCREEN",
                        "priority": priority(len(ids), live[etype], miss, 0.5), "rule": RULE_E,
                        "sources": {"detector": news.DETECTOR, "events": len(ids), "first_obs": min(ids, default=None),
                                    "last_obs": max(ids, default=None), "events_sha256": hashlib.sha256(json.dumps(
                                        evs[etype], sort_keys=True).encode()).hexdigest()}})
    from lab import coinbase                                # amendment 17g point 3: 9 candidates once listings exist
    evg = events_g(_items_g(db), a, b)
    if evg:
        miss = missing(evg, SCREEN)
        ids = [e["obs"] for e in evg]
        for o in OUTCOMES:
            k = key(G_TYPE, o, M17G)
            res = done.get(k)
            overlap = 0.25 if any(x.split("|")[1] == o and x != k for x in done) else 0
            out.append({"key": k, "type": G_TYPE, "outcome": o, "events": len(ids), "live_30d": 0,
                        "missing_files": miss, "overlap": overlap, "status": res["verdict"] if res else
                        "QUEUED_FOR_SCREEN", "priority": priority(len(ids), 0, miss, overlap), "rule": RULE_G,
                        "sources": {"detector": coinbase.DETECTOR, "events": len(ids), "first_obs": min(ids),
                                    "last_obs": max(ids), "events_sha256": hashlib.sha256(json.dumps(
                                        evg, sort_keys=True).encode()).hexdigest()}})
    out.sort(key=lambda x: (-x["priority"], x["key"]))
    _CACHE[db.path] = (now, out)
    return out


# ---------- data (point 5 and 8): a reader for one phase ----------
class Reader:
    """Reads 1 h klines and funding of one phase only; refuses any other month and anything from 2024-01-01. `get` is
    the network read (None = cache only)."""

    def __init__(self, phase, get=None):
        if phase not in PHASES:
            raise Refused(f"unknown phase {phase!r}")
        self.phase, self.get = phase, get
        self.a, self.b = bounds(phase)
        self.files, self._memo = [], {}

    def month(self, sym, kind, y, m):
        if not (self.a <= _T(y, m) < self.b) or _T(y, m) >= END:
            raise Refused(f"{sym} {kind} {y}-{m:02d} is outside {self.phase} (amendment 17)")
        k = (sym, kind, y, m)
        if k in self._memo:
            return self._memo[k]
        path = _path(*k)
        if not os.path.exists(path) and self.get is not None:
            path = data._fetch(_url(*k), path, self.get)
        out = {}
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                self.files.append({"file": os.path.basename(path), "sha256": hashlib.sha256(f.read()).hexdigest()})
            for r in data._rows(path):
                ts = int(r[0]) // 1000
                if ts > 10 ** 11:
                    ts //= 1000
                if not (self.a <= ts < self.b) or ts >= END:
                    continue
                if kind in ("klines", "spot"):
                    out[ts] = (float(r[4]), float(r[7]) if len(r) > 7 else 0.0)
                else:
                    out[ts - ts % HOUR] = float(r[2])
        self._memo[k] = out
        return out

    def series(self, sym, kind, lo, hi):
        out = {}
        for y, m in _months(max(lo, self.a), min(hi, self.b - 1)):
            out.update(self.month(sym, kind, y, m))
        return out


def _hours(lo, hi):
    """Bar open times of the hours inside (lo, hi]: bars opening in [ceil(lo), hi)."""
    h = -(-lo // HOUR) * HOUR
    return list(range(h, hi, HOUR))


def outcome(reader, coin, t, name):
    """(y, None) or (None, reason) for one event (point 2)."""
    sym, hz = coin + "USDT", HORIZON[name]
    lo = t - 7 * DAY if name in PRE else t
    if lo - HOUR < reader.a or t + hz > reader.b:
        return None, "window outside the phase"
    t0 = -(-t // HOUR) * HOUR                                 # first full hour >= t
    if name.startswith(("far_", "sar_")):                     # 17a: from the first available price
        kind = "spot" if name.startswith("sar_") else "klines"
        if t + FIRST_WITHIN + hz + HOUR > reader.b:
            return None, "window outside the phase"
        k = reader.series(sym, kind, t0, t0 + FIRST_WITHIN + hz)
        btc = reader.series("BTCUSDT", kind, t0, t0 + FIRST_WITHIN + hz)
        h = next((h for h in range(t0, t + FIRST_WITHIN + 1, HOUR) if h in k and k[h][0] > 0), None)
        if h is None:
            return None, "no price within 72 h"
        p = [k.get(h), k.get(h + hz), btc.get(h), btc.get(h + hz)]
        if any(x is None or x[0] <= 0 for x in p):
            return None, "missing price"
        return math.log(p[1][0] / p[0][0]) - math.log(p[3][0] / p[2][0]), None
    if name.startswith("ar_"):
        k, btc = reader.series(sym, "klines", t0 - HOUR, t0 + hz), reader.series("BTCUSDT", "klines", t0 - HOUR,
                                                                                    t0 + hz)
        p = [k.get(t0 - HOUR), k.get(t0 + hz - HOUR), btc.get(t0 - HOUR), btc.get(t0 + hz - HOUR)]
        if any(x is None or x[0] <= 0 for x in p):
            return None, "missing price"
        return math.log(p[1][0] / p[0][0]) - math.log(p[3][0] / p[2][0]), None
    if name == "fund_7d":
        f = reader.series(sym, "funding", t - 7 * DAY - 8 * HOUR, t + 7 * DAY)
        pre = sorted((ts, v) for ts, v in f.items() if t - 7 * DAY < ts <= t)
        post = sorted((ts, v) for ts, v in f.items() if t < ts <= t + 7 * DAY)
        if len(pre) < 19 or len(post) < 19:
            return None, "too few funding settlements"
        return _per8h(f, post) - _per8h(f, pre), None
    k = reader.series(sym, "klines", t - 7 * DAY - HOUR, t + hz)
    pre_h, post_h = _hours(t - 7 * DAY, t), _hours(t, t + hz)
    if name == "vol_3d":
        def rets(hs):
            return [math.log(k[h][0] / k[h - HOUR][0]) for h in hs if h in k and h - HOUR in k and k[h - HOUR][0] > 0
                    and k[h][0] > 0]
        a, b = rets(pre_h), rets(post_h)
        if len(a) < COVER * len(pre_h) or len(b) < COVER * len(post_h):
            return None, "too few hours"
        sa, sb = statistics.pstdev(a), statistics.pstdev(b)
        if sa <= 0 or sb <= 0:
            return None, "zero volatility"
        return math.log(sb / sa), None
    a, b = [k[h][1] for h in pre_h if h in k], [k[h][1] for h in post_h if h in k]
    if len(a) < COVER * len(pre_h) or len(b) < COVER * len(post_h):
        return None, "too few hours"
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    if ma <= 0 or mb <= 0:
        return None, "zero volume"
    return math.log(mb / ma), None


def _per8h(f, rows):
    """Mean funding per 8 h: each settlement scaled by 8 h / its interval (the gap to the previous one, 8 h if none)."""
    ts_all = sorted(f)
    out = []
    for ts, v in rows:
        i = ts_all.index(ts)
        gap = ts - ts_all[i - 1] if i else 8 * HOUR
        out.append(v * 8 * HOUR / min(max(gap, HOUR), 8 * HOUR))
    return statistics.fmean(out)


# ---------- statistics ----------
def p_two(ys):
    lo = measure.sign_flip_p(list(ys), 20000, 7)
    hi = measure.sign_flip_p([-y for y in ys], 20000, 7)
    return None if lo is None else min(1.0, 2 * min(lo, hi))


def p_one(ys, direction):
    """One-sided p in `direction` (+1: mean > 0, -1: mean < 0)."""
    return measure.sign_flip_p([-y for y in ys] if direction > 0 else list(ys), 20000, 7)


def measure_events(reader, evs, name):
    rows, excl = [], {}
    for e in evs:
        y, why = outcome(reader, e["coin"], e["t"], name)
        if y is None:
            excl[why] = excl.get(why, 0) + 1
        else:
            rows.append({**e, "y": y})
    return rows, excl


# ---------- screening (point 5) ----------
def screen(db, k, get=None, items=None):
    etype, name, method = k.split("|")[:3]
    rule = {M17C: RULE_C, M17E: RULE_E, M17G: RULE_G}.get(method, RULE)
    if k in COVERED:
        return {"key": k, "verdict": "COVERED", "reason": COVERED[k], "method": METHOD, "rule": RULE}
    a, b = bounds(SCREEN)
    evs = _evs(db, etype, method, a, b, items)
    reader = Reader(SCREEN, get)
    rows, excl = measure_events(reader, evs, name)
    ys = [r["y"] for r in rows]
    res = {"key": k, "type": etype, "outcome": name, "method": method, "rule": rule, "window": "explore0 2020-03..2021-12",
           "label": "EXPLORATORY (never evidence)", "events": len(evs), "n": len(ys), "excluded": excl,
           "events_sha256": hashlib.sha256(json.dumps([[r["obs"], r["coin"], r["t"], round(r["y"], 10)] for r in rows]
                                                      ).encode()).hexdigest(),
           "used": [[r["obs"], r["coin"], r["t"], round(r["y"], 6)] for r in rows][:400]}
    if len(ys) < MIN_SCREEN:
        res.update(verdict="UNTESTABLE", reason=f"{len(ys)} events with data (< {MIN_SCREEN})")
        res["files"] = len(reader.files)
        return res
    mean, p = statistics.fmean(ys), p_two(ys)
    h1 = [r["y"] for r in rows if r["t"] < HALF]
    h2 = [r["y"] for r in rows if r["t"] >= HALF]
    shift = -PLACEBO_SHIFT
    pl_rows, _ = measure_events(reader, [{**e, "t": e["t"] + shift} for e in evs], name)
    if method == M17E and len(pl_rows) < MIN_SCREEN:         # amendment 17e: a new market has no price at t - 30 d
        shift = PLACEBO_SHIFT
        pl_rows, _ = measure_events(reader, [{**e, "t": e["t"] + shift} for e in evs], name)
    pl = [r["y"] for r in pl_rows]
    pp = p_two(pl) if len(pl) >= MIN_SCREEN else None
    sign = 1 if mean > 0 else -1
    checks = {f"p <= {P_SCREEN}": p <= P_SCREEN,
              "same sign in 2020 and 2021": len(h1) >= MIN_HALF and len(h2) >= MIN_HALF and
              statistics.fmean(h1) * sign > 0 and statistics.fmean(h2) * sign > 0,
              f"placebo p > {P_PLACEBO} (n >= {MIN_SCREEN})": pp is not None and pp > P_PLACEBO}
    if name.startswith(RETURNS):
        checks[f"|mean| >= {COST}"] = abs(mean) >= COST
    res.update(mean=mean, median=statistics.median(ys), share_positive=sum(y > 0 for y in ys) / len(ys), p=p,
               direction=sign, halves={"2020": [len(h1), statistics.fmean(h1) if h1 else None],
                                       "2021": [len(h2), statistics.fmean(h2) if h2 else None]},
               placebo={"n": len(pl), "mean": statistics.fmean(pl) if pl else None, "p": pp,
                        "shift_days": shift // DAY}, checks=checks,
               files=len(reader.files))
    ok = all(checks.values())
    res.update(verdict="SCREEN_PASS" if ok else "SCREEN_FAIL",
               reason="all screening checks hold" if ok else "failed: " + "; ".join(c for c, v in checks.items()
                                                                                       if not v))
    return res


def draft(res, root=None):
    """Point 6: the pre-registration draft of a SCREEN_PASS (json + md). Returns the json path."""
    d = root or DIR
    os.makedirs(d, exist_ok=True)
    word = "højere" if res["direction"] > 0 else "lavere"
    fwd = (res.get("placebo") or {}).get("shift_days", -30) > 0         # amendment 17e
    g = res.get("method") == M17G                                       # amendment 17g
    spec = {"key": res["key"], "type": res["type"], "outcome": res["outcome"], "direction": res["direction"],
            "claim": f"`{res['outcome']}` efter " + ("den første handel på Coinbase (USD)" if g else
                                                     f"Binance-meddelelser af typen `{res['type']}`") + f" er {word} end 0",
            "mechanism": ("noteringen ændrer efterspørgsel, opmærksomhed eller afdækning i mønten (ikke undersøgt)" if g
                          else "meddelelsen ændrer efterspørgsel, opmærksomhed eller afdækning i mønten (ikke undersøgt)"),
            "data": ("CoinMetrics' katalog: første handel pr. Coinbase USD-marked (coinbase/1); " if g else
                     "Binance' meddelelser i registret (news/1); ") +
                    "USD-M 1 t-klines og fundingRate fra data.binance.vision",
            "baseline": "0: ingen ændring (afkast er fratrukket BTCUSDT; de andre måles mod (t - 7 d, t])",
            "placebo": f"samme mønter med t {'+' if fwd else '-'} 30 d",
            "costs": "afkast (ar_, far_, sar_): 0,46 % rundtur (F1); andre udfald handles ikke",
            "criterion": f"train3 ensidet p < {P_TRAIN} med n >= {MIN_TRAIN}; validation3 ensidet p < alpha_k med "
                         f"n >= {MIN_VALID}; alpha_k = 0,05 * 2^-k (ændring 17 punkt 7)",
            "risks": f"screeningen valgte blandt {CANDIDATES.get(res.get('method'), 108)} kandidater; overlappende "
                     "begivenheder; tynde perps",
            "plan": "låses ved en dateret ændring (LÅS-17); måles derefter automatisk én gang",
            "screen": {x: res.get(x) for x in ("n", "mean", "median", "p", "halves", "placebo", "events_sha256")},
            "rule": res.get("rule", RULE), "method": res.get("method", METHOD)}
    path = os.path.join(d, fname(res["key"]) + ".json")
    with open(path, "w") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    with open(path[:-5] + ".md", "w") as f:
        f.write(f"# {res['key']} (udkast, ændring 17; ikke bevis)\n\n" + "\n".join(
            f"- **{k}:** {spec[k]}" for k in ("claim", "mechanism", "data", "baseline", "placebo", "costs", "criterion",
                                             "risks", "plan")) + f"\n\nScreening (explore0): n {res['n']}, gennemsnit "
                f"{res['mean']:.6f}, p {res['p']:.5f}.\n\nLåses ved at kopiere json-filen til `{AUTO}/` og skrive "
                f"`LÅS-17 {res['key']} <sha256>` i en dateret ændring.\n")
    return path


# ---------- locks and measurement (points 7-8) ----------
def locks(text=None, read=None):
    """[(key, sha256, k, spec)] from the committed protocol (HEAD), in file order; a lock whose committed draft is
    missing or has another sha256 is left out."""
    from lab.registry import git
    if text is None:
        try:
            text = git("show", "HEAD:copybot/research/PROTOCOL_V3.md")
        except Exception:                                   # noqa: BLE001 - no git: nothing is locked
            return []
    read = read or (lambda p: git("show", f"HEAD:copybot/{p}") + "\n")
    out = []
    for i, (k, sha) in enumerate(LOCK.findall(text), 1):
        try:
            raw = read(f"{AUTO}/{fname(k)}.json")
        except Exception:                                   # noqa: BLE001
            continue
        if hashlib.sha256(raw.encode()).hexdigest() == sha:
            out.append((k, sha, i, json.loads(raw)))
    return out


def measure_locked(db, k, sha, idx, spec, get=None, items=None):
    etype, name, direction = spec["type"], spec["outcome"], spec["direction"]
    alpha = ALPHA * 2 ** -idx
    items = items if items is not None or spec.get("method") == M17G else _items(db)
    res = {"hypothesis": k, "name": f"{etype} {name}", "rule": "17", "artifact_id": f"MEASURE_17_{idx}",
           "draft_sha256": sha, "alpha": alpha, "direction": direction, "phases": {}}
    for phase, n_min, p_max in (("train3", MIN_TRAIN, P_TRAIN), ("validation3", MIN_VALID, alpha)):
        a, b = bounds(phase)
        reader = Reader(phase, get)
        rows, excl = measure_events(reader, _evs(db, etype, spec.get("method", METHOD), a, b, items), name)
        ys = [r["y"] for r in rows]
        p = p_one(ys, direction) if ys else None
        res["phases"][phase] = {"n": len(ys), "mean": statistics.fmean(ys) if ys else None, "p": p, "excluded": excl,
                                "files": reader.files}
        if len(ys) < n_min:
            res.update(verdict="UNTESTABLE", reason=f"{phase}: {len(ys)} events (< {n_min})")
            return res
        if p >= p_max:
            res.update(verdict="REJECTED", reason=f"{phase}: one-sided p {p:.4f} >= {p_max:g}")
            return res
    res.update(verdict="PASS", reason=f"train3 and validation3 hold (alpha {alpha:g}); a measurement, not a trading rule")
    return res


# ---------- jobs ----------
def step_screen(db, job, worker, get=None):
    k = json.loads(job["payload"])["key"] if isinstance(job["payload"], str) else job["payload"]["key"]
    if k in results(db):
        return {"key": k, "skipped": "already screened (point 4)"}
    if get is None:
        from lab import explore
        get = explore.guarded_get()
    res = screen(db, k, get)
    if res["verdict"] == "SCREEN_PASS":
        res["draft"] = os.path.basename(draft(res))
    res["event_id"] = db.event(EV_SCREEN, f"agent:{worker}", None, res)
    _CACHE.pop(db.path, None)
    return {x: res.get(x) for x in ("key", "verdict", "n", "p", "reason", "event_id")}


def measured(db):
    return {(json.loads(r[0]) if isinstance(r[0], str) else r[0]).get("hypothesis")
            for r in db.q("SELECT payload FROM events WHERE kind=?", measure.EVENT)}


def step_measure(db, job, worker, get=None, lock_list=None):
    k = json.loads(job["payload"])["key"] if isinstance(job["payload"], str) else job["payload"]["key"]
    if k in measured(db):
        return {"key": k, "skipped": "already measured"}
    lk = next((x for x in (lock_list if lock_list is not None else locks()) if x[0] == k), None)
    if lk is None:
        raise pipeline.StepError(f"{k} is not locked in the committed protocol (amendment 17 point 7)")
    if get is None:
        from lab import explore
        get = explore.guarded_get()
    res = measure_locked(db, *lk, get=get)
    res["event_id"] = db.event(measure.EVENT, f"agent:{worker}", None, res)
    return {x: res.get(x) for x in ("hypothesis", "verdict", "reason", "event_id")}


def cached_locks(db, now=None):
    now = now or time.time()
    hit = _CACHE.get(("locks", db.path))
    if not hit or now - hit[0] >= TTL:
        hit = (now, locks())
        _CACHE[("locks", db.path)] = hit
    return hit[1]


def enqueue(db, now=None, actor="strategy-1", lock_list=None):
    """Point 3: record new candidates once; at most one screening job at a time (highest priority first); one
    measurement job per lock. Returns the number of new jobs."""
    now = now or time.time()
    jobs.init(db)
    if not db.one("SELECT 1 FROM observations WHERE detector=? AND metric='news_item' AND source LIKE '%binance.com%' "
                  "LIMIT 1", news.DETECTOR):
        return 0                                            # no announcements yet: no candidates (point 1)
    cands = candidates(db, now)
    known = {(json.loads(r[0]) if isinstance(r[0], str) else r[0]).get("key")
             for r in db.q("SELECT payload FROM events WHERE kind=?", EV_HYP)}
    for c in cands:
        if c["key"] not in known:
            db.event(EV_HYP, f"system:{actor}", None, {k: c[k] for k in ("key", "type", "outcome", "sources",
                                                                          "priority", "status")} | {"rule": c.get("rule", RULE)})
    n = 0
    if not db.one("SELECT 1 FROM jobs WHERE kind='hypo_screen' AND status IN ('queued', 'running', 'blocked') LIMIT 1"):
        nxt = next((c for c in cands if c["status"] == "QUEUED_FOR_SCREEN" and not db.one(
            "SELECT 1 FROM jobs WHERE job_id=?", f"hypo_screen|{c['key']}")), None)
        if nxt:
            n += jobs.enqueue(db, f"hypo_screen|{nxt['key']}", "hypo_screen", None, {"key": nxt["key"]},
                              actor=f"system:{actor}", now=now, **JOB)[1]
    lock_list = cached_locks(db, now) if lock_list is None else lock_list
    done = measured(db)
    for k, *_ in lock_list:
        if k not in done:
            n += jobs.enqueue(db, f"hypo_measure|{k}", "hypo_measure", None, {"key": k}, actor=f"system:{actor}",
                              now=now, **JOB)[1]
    return n


def view(db, now=None, top=12):
    """Display only: counts by status, the next candidates and the latest results (negative ones included)."""
    cands = candidates(db, now)
    res = sorted(results(db).values(), key=lambda r: -r["event_id"])
    by = {}
    for c in cands:
        by[c["status"]] = by.get(c["status"], 0) + 1
    drafts = sorted(os.listdir(DIR)) if os.path.isdir(DIR) else []
    return {"total": len(cands), "by_status": by, "next": cands[:top], "drafts": [d for d in drafts if
                                                                                    d.endswith(".md")],
            "results": [{x: r.get(x) for x in ("key", "verdict", "n", "mean", "p", "reason", "ts")} for r in res[:top]],
            "locks": [x[0] for x in cached_locks(db, now)], "rule": RULE}
