"""Event and news scanner (PROTOCOL_V3 amendment 16): public, keyless GET sources only; data, never a decision.

Each item is one observation (detector "news/1", metric "news_item") keyed by source and the source's own id, with the
publisher's time, the time it was collected, the title, the URL, the category and the coins named in the title. An
item may be used from the time it was collected; Binance announcements fetched backwards (publisher-timestamped) are
marked backfill and may be used from their publication time + 1 hour. Every source fails on its own (metric
"news_error"); nothing here trades, ranks or interprets.
"""
from __future__ import annotations

import calendar
import email.utils
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DETECTOR = "news/1"
ACTOR = "system:news"
UA = "copybot-research/1.0 (paper research; contact via repository owner)"
MAX_BYTES = 2 * 2 ** 20                          # a feed larger than this is refused, not parsed
BINANCE = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
CATALOGS = {48: "listing", 161: "delisting", 49: "binance_news"}
RSS = {"cointelegraph": "https://cointelegraph.com/rss", "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
       "fed_press": "https://www.federalreserve.gov/feeds/press_all.xml",             # amendment 21b (macro)
       "bls_latest": "https://www.bls.gov/feed/bls_latest.rss",
       "ecb_press": "https://www.ecb.europa.eu/rss/press.html",
       "cnbc_economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html"}
RSS_CATEGORY = {"fed_press": "macro", "bls_latest": "macro", "ecb_press": "macro", "cnbc_economy": "macro"}
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = "(bitcoin OR ethereum OR crypto OR cryptocurrency OR stablecoin) sourcelang:english"
GDELT_EVERY, GDELT_BACKOFF_MAX = 1800, 24 * 3600     # amendment 17 point 9 (was 900 and 6 h)
BACKFILL_LAG_S = 3600                            # point 3: a backfilled item is usable from publication + 1 hour
BACKFILL_PAUSE_S = 2.0
BACKFILL_RETRY_S = (60, 180, 600)                # waits after a refused page before the category stops
_STATE = {"gdelt_next": 0.0, "gdelt_wait": GDELT_EVERY, "gdelt_loaded": False}
_PAREN = re.compile(r"\(([A-Z0-9]{2,12})\)")
_PAIR = re.compile(r"\b([A-Z0-9]{2,12})(?:USDT|USDC|FDUSD)\b")


def http_get(url, timeout=30):
    """Raw bytes of a GET (no retries here: the caller records a failure and tries again next pass)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"response larger than {MAX_BYTES} bytes")
    return raw


_LAUNCH = re.compile(r"Futures Will Launch (.*?) Perpetual")
_LAUNCH_DROP = ("USDⓈ-M", "USDS-M", "USDT-Margined", "USDC-Margined", "Coin-Margined")
_TICKER = re.compile(r"[A-Z0-9]{2,15}")


def coins(title):
    """Tickers named in a title by fixed rules: tokens in parentheses, XXXUSDT/USDC/FDUSD pairs, and (amendment 16b)
    the bare tickers between "Futures Will Launch" and "Perpetual" (sorted, unique)."""
    t = title or ""
    out = set(_PAREN.findall(t)) | set(_PAIR.findall(t))
    m = _LAUNCH.search(t)
    if m:
        part = m.group(1)
        for w in _LAUNCH_DROP:
            part = part.replace(w, " ")
        for tok in re.split(r"[\s&,]+", part):
            if tok != "and" and _TICKER.fullmatch(tok):
                out.add(tok)
    return sorted(out)


def item(source, sid, url, title, published, category, now, backfill=False):
    key = f"{source}:{sid}"
    return {"key": key, "hash": hashlib.sha256(key.encode()).hexdigest()[:16], "source": source, "id": str(sid),
            "url": url, "title": (title or "").strip()[:500], "published_ts": published, "fetched_ts": int(now),
            "category": category, "coins": coins(title), "backfill": bool(backfill),
            "usable_from": int(published + BACKFILL_LAG_S) if backfill and published else int(now)}


def binance(get, now, catalog, page=1, size=20, backfill=False):
    q = urllib.parse.urlencode({"type": 1, "pageNo": page, "pageSize": size, "catalogId": catalog})
    d = json.loads(get(f"{BINANCE}?{q}"))
    out = []
    for c in (d.get("data") or {}).get("catalogs") or []:
        for a in c.get("articles") or []:
            pub = (a.get("releaseDate") or 0) / 1000 or None
            out.append(item("binance", a.get("code") or a.get("id"),
                            f"https://www.binance.com/en/support/announcement/{a.get('code')}", a.get("title"), pub,
                            CATALOGS.get(catalog, str(catalog)), now, backfill))
    return out


def rss(get, now, name):
    root = ET.fromstring(get(RSS[name]))
    out = []
    for it in root.iter("item"):
        link, guid = it.findtext("link") or "", it.findtext("guid") or ""
        pub = it.findtext("pubDate")
        try:
            ts = email.utils.parsedate_to_datetime(pub).timestamp() if pub else None
        except (TypeError, ValueError):
            ts = None
        out.append(item(name, guid or link, link, it.findtext("title"), ts, RSS_CATEGORY.get(name, "media"), now))
    return out


def gdelt(get, now):
    q = urllib.parse.urlencode({"query": GDELT_QUERY, "mode": "artlist", "format": "json", "maxrecords": 75,
                                "timespan": "1h", "sort": "datedesc"})
    d = json.loads(get(f"{GDELT}?{q}") or b"{}")
    out = []
    for a in d.get("articles") or []:
        try:
            ts = calendar.timegm(time.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ"))
        except ValueError:
            ts = None
        out.append(item("gdelt", a.get("url"), a.get("url"), a.get("title"), ts, a.get("domain") or "media", now))
    return out


def _known(db, keys):
    if not keys:
        return set()
    out = set()
    keys = list(keys)
    for i in range(0, len(keys), 500):
        part = keys[i:i + 500]
        out |= {r[0] for r in db.q(f"SELECT instrument FROM observations WHERE detector=? AND metric='news_item' AND "
                                   f"instrument IN ({','.join('?' * len(part))})", DETECTOR, *part)}
    return out


def store(db, items, source_url, now):
    """New items only (dedup by source and id across all time). Returns the number stored."""
    seen, new = _known(db, {x["key"] for x in items}), []
    for x in items:
        if x["key"] not in seen:
            seen.add(x["key"])
            new.append(x)
    with db.tx():
        for x in new:
            db.append("observations", ts=int(now), detector=DETECTOR, source=source_url, instrument=x["key"],
                      metric="news_item", value=x["published_ts"], threshold=None, flagged=0, payload=x)
    return len(new)


def _error(db, source_url, now, e):
    db.append("observations", ts=int(now), detector=DETECTOR, source=source_url, instrument=None, metric="news_error",
              value=None, threshold=None, flagged=0, payload={"error": f"{e!r}"[:300]})


def _gdelt_restore(db):
    """Amendment 17 point 9: the backoff survives a restart. Read from the registry once per process: the last GDELT
    error and the number of errors since the last stored GDELT item."""
    _STATE["gdelt_loaded"] = True
    last_item = db.one("SELECT MAX(ts) FROM observations WHERE detector=? AND metric='news_item' AND source=?",
                       DETECTOR, GDELT)[0] or 0
    r = db.one("SELECT COUNT(*), MAX(ts) FROM observations WHERE detector=? AND metric='news_error' AND source=? AND "
               "ts>?", DETECTOR, GDELT, last_item)
    if r[0]:
        _STATE["gdelt_wait"] = min(GDELT_BACKOFF_MAX, GDELT_EVERY * 2 ** r[0])
        _STATE["gdelt_next"] = max(_STATE["gdelt_next"], r[1] + _STATE["gdelt_wait"])


def _retry_after(e):
    try:
        return max(0, int((getattr(e, "headers", None) or {}).get("Retry-After")))
    except (TypeError, ValueError):
        return 0


def run(db, get=http_get, now=None):
    """One pass (news-watch, every 10 minutes): Binance categories and RSS each pass, GDELT at most every 30 minutes
    with exponential backoff after a refusal (Retry-After respected; restored after a restart, amendment 17 point 9).
    Returns counts per source and the errors."""
    now = now or time.time()
    if not _STATE["gdelt_loaded"]:
        _gdelt_restore(db)
    out, errors = {}, []
    jobs = [(f"{BINANCE}#{c}", lambda c=c: binance(get, now, c)) for c in CATALOGS]
    jobs += [(RSS[n], lambda n=n: rss(get, now, n)) for n in RSS]
    if now >= _STATE["gdelt_next"]:
        jobs.append((GDELT, lambda: gdelt(get, now)))
    for src, fn in jobs:
        try:
            got = fn()
            out[src] = store(db, got, src.split("#")[0], now)
            name = next((n for n, u in RSS.items() if u == src), None)
            if RSS_CATEGORY.get(name) == "macro":               # 21d precision 2: the fetch itself, not only new items
                pubs = [x["published_ts"] for x in got if x.get("published_ts")]
                db.append("observations", ts=int(now), detector=DETECTOR, source=src, instrument=None,
                          metric="news_fetch", value=len(got), threshold=None, flagged=0,
                          payload={"items": len(got), "newest_published_ts": max(pubs) if pubs else None})
            if src == GDELT:
                _STATE["gdelt_wait"], _STATE["gdelt_next"] = GDELT_EVERY, now + GDELT_EVERY
        except Exception as e:                                  # noqa: BLE001 - one source never stops the others
            errors.append(f"{src}: {e!r}"[:200])
            _error(db, src.split("#")[0], now, e)
            if src == GDELT:
                _STATE["gdelt_wait"] = min(GDELT_BACKOFF_MAX, max(_STATE["gdelt_wait"] * 2, _retry_after(e)))
                _STATE["gdelt_next"] = now + _STATE["gdelt_wait"]
    return {"stored": out, "errors": errors, "decisional": False}


def backfill(db, get=http_get, now=None, pages=200, sleep=time.sleep):
    """Point 3: Binance announcements backwards, once, at most one request per BACKFILL_PAUSE_S. Stops a category at
    its first empty page (or after `pages`); a rerun skips what is stored."""
    now = now or time.time()
    total = {}
    for c in CATALOGS:
        n = 0
        for p in range(1, pages + 1):
            got = None
            for wait in BACKFILL_RETRY_S + (None,):              # a refusal (e.g. HTTP 429): wait, then try again
                try:
                    got = binance(get, now, c, page=p, size=50, backfill=True)
                    break
                except Exception as e:                          # noqa: BLE001 - recorded, never fatal
                    _error(db, BINANCE, now, e)
                    if wait is None:
                        break
                    sleep(wait)
            if got is None:
                total[f"{CATALOGS[c]}_stopped_at_page"] = p    # a rerun continues (stored items are skipped)
                break
            if not got:
                break
            k = store(db, got, BINANCE, now)
            n += k
            sleep(BACKFILL_PAUSE_S)
        total[CATALOGS[c]] = n
    return total


def items(db, since=None, source=None, limit=200):
    """Stored items, newest collected first (for the dashboard and for registered hypotheses)."""
    sql, args = "SELECT ts, source, payload FROM observations WHERE detector=? AND metric='news_item'", [DETECTOR]
    if since:
        sql, args = sql + " AND ts>=?", args + [int(since)]
    if source:
        sql, args = sql + " AND source=?", args + [source]
    rows = db.q(sql + " ORDER BY ts DESC, rowid DESC LIMIT ?", *args, int(limit))
    return [json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"] for r in rows]
