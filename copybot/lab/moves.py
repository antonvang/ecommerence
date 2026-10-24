"""Abnormal moves across markets (research/PROTOCOL_V3.md amendment 21): data and descriptive analysis only.

Every hourly scan reads 1-hour klines and the mark/index price of a fixed list of Binance USD-M perpetuals (crypto and
TradFi contracts on metals, energy, equity ETFs and USDBRL; never spot gold, an index or interbank FX) and records, per
market, the last closed hour's return in units of its own trailing volatility (z_1h), the same for 24 hours (z_24h),
the hour's turnover against its trailing median, and the perp/index premium. A flagged market gets one analysis
record per 6 hours (`opportunity.move`) with the cross-market context, the book cost of a 5 000 USD round trip and
matching news-watch titles; 24 hours later its forward return is stored (`opportunity.outcome`) for a later, locked
test. Nothing here registers a candidate, trades or reads data for a decision.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

DETECTOR = "abnormal_move"
BN = "https://fapi.binance.com"
WATCH = {                         # symbol: (class, label, news keywords) - amendment 21 point 1
    "BTCUSDT": ("crypto", "Bitcoin (Binance perp)", ("bitcoin", "btc", "crypto")),
    "ETHUSDT": ("crypto", "Ether (Binance perp)", ("ether", "ethereum", "eth", "crypto")),
    "XAUUSDT": ("commodity", "Guld (Binance TradFi-perp)", ("gold", "xau", "bullion", "fed", "fomc", "cpi",
                                                            "inflation", "dollar", "treasury", "yields")),
    "XAGUSDT": ("commodity", "Sølv (Binance TradFi-perp)", ("silver", "xag", "metals", "fed", "inflation", "dollar")),
    "XPTUSDT": ("commodity", "Platin (Binance TradFi-perp)", ("platinum", "metals")),
    "COPPERUSDT": ("commodity", "Kobber (Binance TradFi-perp)", ("copper", "metals", "china")),
    "CLUSDT": ("commodity", "WTI-olie (Binance TradFi-perp)", ("oil", "crude", "wti", "opec", "energy")),
    "BZUSDT": ("commodity", "Brent-olie (Binance TradFi-perp)", ("oil", "crude", "brent", "opec", "energy")),
    "NATGASUSDT": ("commodity", "Naturgas (Binance TradFi-perp)", ("natural gas", "lng", "energy")),
    "SPYUSDT": ("equity_etf", "S&P 500-fond SPY (Binance TradFi-perp)", ("s&p", "stocks", "equities", "fed",
                                                                         "cpi", "earnings", "wall street")),
    "QQQUSDT": ("equity_etf", "Nasdaq-100-fond QQQ (Binance TradFi-perp)", ("nasdaq", "tech", "stocks", "fed",
                                                                            "earnings")),
    "USDBRLUSDT": ("fx", "USD/BRL (Binance TradFi-perp)", ("brazil", "real", "brl", "dollar")),
}
Z1, Z24, VOLUME_RATIO = 4.0, 3.0, 5.0          # point 4: fixed before any data
HIST, MIN_RETURNS = 720, 600
MAX_AGE_S = 2 * 3600
DEDUP_S = 6 * 3600
NEWS_WINDOW_S = 3 * 3600
OUTCOME_S = 24 * 3600
SIZE_USD = 5000.0
HOUR = 3600
ACTOR = "system:scanner"
MACRO_BEFORE_S, MACRO_EVERY_S = 3 * 3600, 86400            # amendment 21a
_KLINES = {}                                   # symbol -> the closed klines of the latest scan (for the outcomes)
_MACRO = {"ts": 0.0, "events": [], "error": None}


def _closed(klines, now):
    """[(open_s, close_price, quote_volume, close_s)] of the hours that closed before `now`."""
    return [(int(k[0]) // 1000, float(k[4]), float(k[7]), (int(k[6]) + 1) // 1000) for k in klines
            if (int(k[6]) + 1) // 1000 <= now]


def stats(klines, now):
    """Point 3 for one market, or {'short': n} with fewer than MIN_RETURNS trailing returns."""
    rows = _closed(klines, now)
    if len(rows) < 26:
        return {"short": max(0, len(rows) - 2)}
    px = [r[1] for r in rows]
    rets = [math.log(b / a) for a, b in zip(px[:-1], px[1:]) if a > 0 and b > 0]
    trail = rets[-1 - HIST:-1]
    if len(trail) < MIN_RETURNS:
        return {"short": len(trail)}
    sigma = statistics.pstdev(trail)
    r1, r24 = math.log(px[-1] / px[-2]), math.log(px[-1] / px[-25])
    vols = [r[2] for r in rows[-1 - HIST:-1]]
    med = statistics.median(vols) if vols else 0.0
    return {"open_s": rows[-1][0], "close_s": rows[-1][3], "price": px[-1], "ret_1h": r1, "ret_24h": r24,
            "sigma_1h": sigma, "z_1h": r1 / sigma if sigma > 0 else 0.0,
            "tails_720h": sum(1 for r in trail if sigma > 0 and abs(r) / sigma >= Z1),
            "z_24h": r24 / (sigma * math.sqrt(24)) if sigma > 0 else 0.0,
            "volume_ratio": rows[-1][2] / med if med > 0 else None, "quote_volume_1h": rows[-1][2],
            "age_s": now - rows[-1][3], "returns": len(trail), **_log(rows, trail, med, now)}


def _log(rows, trail, med, now):
    """Amendment 21p: the inputs behind the numbers (no raw data): the trailing window, the volume median, sigma's
    sums and the data quality."""
    win = rows[-1 - HIST:-1]
    first, last = win[0][0], win[-1][0]
    return {"window": {"first_open_s": first, "last_open_s": last, "n_returns": len(trail), "n_bars": len(win)},
            "median_qvol_720": med,
            "sigma_basis": {"n": len(trail), "sum": math.fsum(trail), "sumsq": math.fsum(r * r for r in trail)},
            "quality": {"age_s": now - rows[-1][3], "missing_bars": (last - first) // HOUR + 1 - len(win)}}


_VERSION = {}


def version():
    """Detector and git commit, read once per process (a deploy restarts the process)."""
    if not _VERSION:
        try:
            from lab import registry
            commit = registry.git("rev-parse", "HEAD")
        except Exception:                                       # noqa: BLE001 - no git: recorded as unknown
            commit = None
        _VERSION.update(detector=f"{DETECTOR}/1", commit=commit)
    return dict(_VERSION)


def detect(get, post, now):
    """Scanner detector (amendment 21): observations only, never a proposal."""
    from lab.scanner import obs
    out = []
    for sym, (cls, label, _) in WATCH.items():
        src = f"{BN}/fapi/v1/klines?symbol={sym}&interval=1h"
        try:
            kl = get(f"{src}&limit={HIST + 2}")
            prem = get(f"{BN}/fapi/v1/premiumIndex?symbol={sym}")
        except Exception as e:                                  # noqa: BLE001 - one market never stops the others
            out.append(obs(DETECTOR, src, sym, "error", None, payload={"error": f"{sym}: {e!r}"[:300]}))
            continue
        _KLINES[sym] = _closed(kl, now)
        s = stats(kl, now)
        base = {"class": cls, "label": label, "venue": "Binance USD-M perpetual"}
        if "short" in s:
            out.append(obs(DETECTOR, src, sym, "history_short", s["short"], MIN_RETURNS, False, base))
            continue
        if s["age_s"] > MAX_AGE_S:
            out.append(obs(DETECTOR, src, sym, "error", None,
                           payload={**base, "error": f"{sym}: last closed hour is {s['age_s'] // 60} min old"}))
            continue
        mark, index = float(prem.get("markPrice") or 0), float(prem.get("indexPrice") or 0)
        flags = [{"metric": m, "value": v, "threshold": t, "rule": "research/PROTOCOL_V3.md amendment 21 point 4"}
                 for m, v, t in (("z_1h", s["z_1h"], Z1), ("z_24h", s["z_24h"], Z24),
                                 ("volume_ratio", s["volume_ratio"], VOLUME_RATIO))
                 if v is not None and (abs(v) >= t if m != "volume_ratio" else v >= t)]
        fr = prem.get("lastFundingRate")
        p = {**base, **s, "mark": mark, "index": index, "flags": flags, "version": version(),     # 21p
             "funding_rate": float(fr) if fr not in (None, "") else None,                         # 21x point 1
             "next_funding_ts": int(prem["nextFundingTime"]) // 1000 if prem.get("nextFundingTime") else None,
             "klines_sha256": hashlib.sha256(json.dumps(kl, separators=(",", ":")).encode()).hexdigest()}
        out.append(obs(DETECTOR, src, sym, "z_1h", s["z_1h"], Z1, abs(s["z_1h"]) >= Z1, p))
        out.append(obs(DETECTOR, src, sym, "z_24h", s["z_24h"], Z24, abs(s["z_24h"]) >= Z24, p))
        if s["volume_ratio"] is not None:
            out.append(obs(DETECTOR, src, sym, "volume_ratio", s["volume_ratio"], VOLUME_RATIO,
                           s["volume_ratio"] >= VOLUME_RATIO, p))
        if index > 0:
            out.append(obs(DETECTOR, src, sym, "premium", (mark - index) / index, None, False, p))
        b = book_cost(get, sym)                                 # amendment 21h point 3: every market, every scan
        bp = {**base, "open_s": s["open_s"], "off_hours": off_hours(cls, s["open_s"]), **b}
        out.append(obs(DETECTOR, f"{BN}/fapi/v1/depth", sym, "book_rt", b.get("round_trip"), None, False, bp))
        if b.get("spread") is not None:
            out.append(obs(DETECTOR, f"{BN}/fapi/v1/depth", sym, "spread", b["spread"], None, False, bp))
    return out, []


def walk(levels, usd):
    """Mean price of a taker order of `usd` walked through `levels` [(price, qty)], or None if the book is too thin."""
    left, cost, qty = usd, 0.0, 0.0
    for px, q in levels:
        take = min(left, px * q)
        cost, qty, left = cost + take, qty + take / px, left - take
        if left <= 1e-9:
            return cost / qty
    return None


def book_cost(get, sym):
    """Round trip of SIZE_USD through the current book: (buy vwap - sell vwap) / mid, fees excluded (point 5)."""
    try:
        d = get(f"{BN}/fapi/v1/depth?symbol={urllib.parse.quote(sym)}&limit=100")     # non-ASCII symbols exist
        bids = [(float(p), float(q)) for p, q in d.get("bids") or []]
        asks = [(float(p), float(q)) for p, q in d.get("asks") or []]
    except Exception as e:                                      # noqa: BLE001
        return {"error": f"{e!r}"[:200]}
    if not bids or not asks:
        return {"error": "empty book"}
    mid = (bids[0][0] + asks[0][0]) / 2
    buy, sell = walk(asks, SIZE_USD), walk(bids, SIZE_USD)
    if buy is None or sell is None:
        return {"error": "book too thin for 5 000 USD", "spread": (asks[0][0] - bids[0][0]) / mid}
    fees = TRADFI_FEES if WATCH.get(sym, ("crypto",))[0] != "crypto" else "not included"
    return {"round_trip": (buy - sell) / mid, "spread": (asks[0][0] - bids[0][0]) / mid, "size_usd": SIZE_USD,
            "fees": fees}


def news_near(db, sym, t0):
    """news-watch titles published (the source's own time) within 3 h before or after the move hour that mention the
    market's keywords; a title without a publication time is not used (precision of amendment 21 point 5)."""
    words = WATCH[sym][2]
    out = []
    for r in db.q("SELECT payload FROM observations WHERE detector='news/1' AND metric='news_item' AND "
                  "json_extract(payload, '$.published_ts') BETWEEN ? AND ?", t0 - NEWS_WINDOW_S,
                  t0 + HOUR + NEWS_WINDOW_S):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        title = (p.get("title") or "")
        low = f" {title.lower()} "
        if any(f" {w} " in low or f" {w}," in low or f" {w}'" in low for w in words):
            out.append({"title": title[:200], "source": p.get("source"), "published_ts": p.get("published_ts"),
                        "url": p.get("url")})
    return out[:10]


def calendar(now, fetch=None):
    """Amendment 21a: scheduled FOMC statements and BLS CPI / Employment Situation releases of this year and the
    next, read at most once a day with amendment 14's parsers. Returns (events, error)."""
    from lab import ingest
    if _MACRO["ts"] and now - _MACRO["ts"] < MACRO_EVERY_S:
        return _MACRO["events"], _MACRO["error"]
    fetch = fetch or ingest._text
    events, errors = [], []
    year = int(time.strftime("%Y", time.gmtime(now)))
    for y in (year, year + 1):
        for url, parse in ((ingest.FOMC_CAL, ingest.parse_fomc), (ingest.BLS.format(year=y), ingest.parse_bls)):
            try:
                events += [e for e in parse(fetch(url), y) if e.get("scheduled") and e.get("ts")]
            except Exception as e:                                  # noqa: BLE001 - recorded, never stops a scan
                errors.append(f"{url}: {e!r}"[:200])
    _MACRO.update(ts=now, events=sorted({(e["event"], e["ts"]): e for e in events}.values(), key=lambda e: e["ts"]),
                  error="; ".join(errors) or None)
    return _MACRO["events"], _MACRO["error"]


def macro_near(events, error, hour_open):
    """Scheduled releases from 3 h before the move hour to its end (amendment 21a)."""
    near = [{"event": e["event"], "ts": e["ts"], "date": e["date"]} for e in events
            if hour_open - MACRO_BEFORE_S <= e["ts"] <= hour_open + HOUR]
    return {"releases": near, **({"error": error} if error else {})}


TRADFI_FEES = {"taker": 0.0004, "maker": 0.0, "included_in_round_trip": False,     # amendment 21g point 2
               "source": "Binance announcement a4c3f1957f2b4e69902985154235c3b1: promotion from 2026-03-31 02:00 UTC "
                         "until further notice (regular users)"}
_ET = ZoneInfo("America/New_York")


def off_hours(cls, t):
    """Amendment 21g: the move hour starts in a window where Binance prices the TradFi perp's index from its own order
    book (Orderbook EWMA): commodities Fri 17:00 - Sun 18:00 ET, FX Fri 17:00 - Sun 17:00 ET, equities Sat-Sun UTC."""
    if cls == "equity_etf":
        return time.gmtime(t).tm_wday >= 5
    reopen = {"commodity": 18, "fx": 17}.get(cls)
    if reopen is None:
        return False
    et = datetime.fromtimestamp(t, _ET)
    wd, hr = et.weekday(), et.hour + et.minute / 60
    return (wd == 4 and hr >= 17) or wd == 5 or (wd == 6 and hr < reopen)


TAIL_ROUTINE, ILLIQUID_RT = 3, 0.005                      # amendment 21e: fixed before any record was judged
TESTED = "m21c (ændring 21c): 4σ-timeflag på krypto-perps gav SCREEN_FAIL i explore0 ved 4 og 24 t"


def triage(rec):
    """Amendment 21e: rule-based explanations, verdict, reason and next step of one analysis record."""
    ex, flags, book = [], rec.get("flags") or [], rec.get("book") or {}
    if flags == ["volume_ratio"] and abs(rec.get("z_1h") or 0) < 2:
        ex.append("volume_only")
    if "error" in book or (book.get("round_trip") or 0) > ILLIQUID_RT:
        ex.append("illiquid")
    if (rec.get("tails_720h") or 0) >= TAIL_ROUTINE:
        ex.append("routine_tail")
    if (rec.get("macro") or {}).get("releases"):
        ex.append("macro_release")
    end = rec["move_hour_s"] + HOUR
    if any((n.get("published_ts") or float("inf")) <= end for n in rec.get("news") or []):
        ex.append("news")
    if "macro_release" not in ex and "news" not in ex:
        ex.append("unexplained")
    crypto = rec.get("class") == "crypto"
    if not crypto and off_hours(rec.get("class"), rec["move_hour_s"]):
        ex.append("off_hours")
    if "volume_only" in ex:
        v = ("REJECT_NOT_DIRECTIONAL", "kun volumen, ingen prisbevægelse", "ingen")
    elif "illiquid" in ex:
        why = book.get("error") or f"rundtur {book.get('round_trip', 0):.2%} for 5 000 USD"
        v = ("REJECT_ILLIQUID", f"bogen: {why}", "ingen; en handel ville koste mere end bevægelsen kan forklare")
    elif crypto and "z_1h" in flags:
        v = ("REJECT_TESTED", TESTED, "ingen; et nyt spor kræver en ny dateret ændring")
    elif crypto:
        v = ("NOT_SCREENED", "flaget er ikke screenet (kun z_1h er testet)", "ikke screenet; en screening kræver en "
             "dateret ændring")
    else:
        v = ("FORWARD_ONLY", "historikken ligger i den reserverede periode (fra 2025)" + (
            "; uden for det underliggende markeds åbningstid (perpens egen ordrebog)" if "off_hours" in ex else ""),
             "udfaldet efter 24 t indsamles; "
             "en test kræver en dateret lås")
    return {"tails_720h": rec.get("tails_720h"), "explanations": ex, "verdict": v[0], "reason": v[1], "next": v[2],
            "rule": "research/PROTOCOL_V3.md amendment 21e"}


def record(db, observations, now, get, fetch=None):
    """Point 5 and 6 after the scan's observations are stored: analysis records for flagged markets, then the
    forward outcomes that are due. Returns the number of records written."""
    by = {}
    for o in observations:
        if o["metric"] in ("z_1h", "z_24h", "volume_ratio"):
            by.setdefault(o["instrument"], {})[o["metric"]] = o
    context = {s: {"z_1h": round(m["z_1h"]["value"], 2), "z_24h": round(m["z_24h"]["value"], 2),
                   "ret_1h": m["z_1h"]["payload"]["ret_1h"], "ret_24h": m["z_1h"]["payload"]["ret_24h"]}
               for s, m in by.items() if "z_1h" in m and "z_24h" in m}
    written = 0
    for sym, m in by.items():
        flags = [k for k, o in m.items() if o["flagged"]]
        if not flags or "z_1h" not in m:
            continue
        if db.one("SELECT 1 FROM events WHERE kind='opportunity.move' AND exp_id IS NULL AND "
                  "json_extract(payload, '$.instrument')=? AND json_extract(payload, '$.scan_ts')>?",
                  sym, now - DEDUP_S):
            continue
        p = m["z_1h"]["payload"]
        rec = {
            "instrument": sym, "class": p["class"], "label": p["label"], "venue": p["venue"], "flags": sorted(flags),
            "move_hour_s": p["open_s"], "price": p["price"], "ret_1h": p["ret_1h"], "ret_24h": p["ret_24h"],
            "z_1h": p["z_1h"], "z_24h": p["z_24h"], "volume_ratio": p["volume_ratio"], "sigma_1h": p["sigma_1h"],
            "mark": p["mark"], "index": p["index"], "others": {k: v for k, v in context.items() if k != sym},
            "book": book_cost(get, sym), "news": news_near(db, sym, p["open_s"]),
            "macro": macro_near(*calendar(now, fetch), p["open_s"]),
            "next": "beskrivende: en test kræver sin egen daterede lås; historik fra 2025 er reserveret (ændring 21)",
            "tails_720h": p.get("tails_720h"),
            "rule": "research/PROTOCOL_V3.md amendment 21", "scan_ts": now, "decisional": False}
        rec["triage"] = triage(rec)
        db.event("opportunity.move", ACTOR, None, rec)
        written += 1
    return written + outcomes(db, now)


def outcomes(db, now):
    """Point 6: the log return from the move hour's close to 24 h later, once, from the klines of this scan."""
    done = {r[0] for r in db.q("SELECT json_extract(payload, '$.move_id') FROM events WHERE kind='opportunity.outcome'")}
    n = 0
    for r in db.q("SELECT id, payload FROM events WHERE kind='opportunity.move' AND exp_id IS NULL ORDER BY id"):
        if r["id"] in done:
            continue
        p = json.loads(r["payload"])
        end = p["move_hour_s"] + HOUR + OUTCOME_S                 # close of the move hour + 24 h
        rows = {o + HOUR: c for o, c, _, _ in _KLINES.get(p["instrument"], [])}   # close time -> close price
        if now < end or end not in rows or p["move_hour_s"] + HOUR not in rows:
            continue
        db.event("opportunity.outcome", ACTOR, None, {
            "move_id": r["id"], "instrument": p["instrument"], "from_s": p["move_hour_s"] + HOUR, "to_s": end,
            "ret_24h_after": math.log(rows[end] / rows[p["move_hour_s"] + HOUR]),
            "rule": "research/PROTOCOL_V3.md amendment 21 point 6", "decisional": False})
        n += 1
    return n
