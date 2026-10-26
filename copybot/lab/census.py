"""PROTOCOL_V3 amendment 28: a forward hourly census of the whole Binance perp universe.

In the first premium-watch pass of each UTC hour (at most 10 minutes after the hour), one `observations` row (detector
census/1, metric snapshot) holds every perp's raw numbers: the premiumIndex rows premium-watch already fetched that
minute, plus one ticker/24hr call. Symbols with "_" (delivery contracts) are left out. A missing field is null, never 0.
Nothing that decides reads it; it is data for later pre-registered hypotheses only. A failure never stops premium-watch.
"""
from __future__ import annotations

import statistics
import time

DET, RULE = "census/1", "research/PROTOCOL_V3.md amendment 28"
HOUR, LATEST_S = 3600, 600
PREMIUM_COLS = ("markPrice", "indexPrice", "lastFundingRate")
TICKER_COLS = ("lastPrice", "openPrice", "highPrice", "lowPrice", "quoteVolume", "count")
COLS = PREMIUM_COLS + TICKER_COLS
_DONE = {}                                      # hour -> True once stored (the registry is checked after a restart)
_ERR = {}


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return int(statistics.median(xs)) if xs else None


def snapshot(rows, ticker):
    """{columns, rows: {symbol: [numbers in COLS order]}, premium_time_ms, ticker_close_ms} from the raw responses."""
    out, ptimes, ttimes = {}, [], []
    for x in rows:
        s = x.get("symbol") or ""
        if not s or "_" in s:
            continue
        out[s] = [_num(x.get(c)) for c in PREMIUM_COLS] + [None] * len(TICKER_COLS)
        ptimes.append(_num(x.get("time")))
    for t in ticker or []:
        s = t.get("symbol") or ""
        if not s or "_" in s:
            continue
        row = out.setdefault(s, [None] * len(COLS))
        row[len(PREMIUM_COLS):] = [_num(t.get(c)) for c in TICKER_COLS]
        ttimes.append(_num(t.get("closeTime")))
    return {"columns": list(COLS), "rows": out, "premium_time_ms": _median(ptimes), "ticker_close_ms": _median(ttimes)}


def _stored(db, hour):
    return db.one("SELECT 1 FROM observations WHERE detector=? AND metric='snapshot' AND ts>=? AND ts<? LIMIT 1",
                  DET, hour, hour + HOUR)


def observe(db, now, rows, get, perps=(), clock=time.time):
    """Amendment 28 for one premium-watch pass: the hour's snapshot if due; returns a short summary or None.
    28a: `perps` is premium-watch's exchangeInfo set of COIN USDT perps; the snapshot's members are stored."""
    now = int(now)
    hour = now - now % HOUR
    if now - hour > LATEST_S or _DONE.get(hour):
        return None
    if _stored(db, hour):
        _DONE[hour] = True
        return None
    from lab.scanner import BN
    url = f"{BN}/fapi/v1/ticker/24hr"
    ticker, err, t_at = None, None, None
    try:
        ticker = get(url)
        t_at = clock()
    except Exception as e:                                      # noqa: BLE001 - the premiumIndex part is kept
        err = repr(e)[:200]
    snap = snapshot(rows, ticker)
    db.append("observations", ts=now, detector=DET, source=f"{BN}/fapi/v1/premiumIndex + {url}", instrument=None,
              metric="snapshot", value=len(snap["rows"]), threshold=None, flagged=0,
              payload={**snap, "coin_perps": sorted(set(perps) & set(snap["rows"])), "premium_fetched_at": now, "ticker_fetched_at": t_at, "ticker_error": err,
                       "rule": RULE, "label": "rådata til senere præregistrerede hypoteser; ingen afgørelse"})
    _DONE[hour] = True
    return {"symbols": len(snap["rows"]), "ticker_error": err}


def guarded(db, now, rows, get, perps=()):
    """premium-watch's hook: a census failure is recorded at most once an hour and never raised."""
    try:
        return observe(db, now, rows, get, perps)
    except Exception as e:                                      # noqa: BLE001
        try:
            if now - _ERR.get("at", 0) >= HOUR:
                _ERR["at"] = now
                db.append("observations", ts=int(now), detector=DET, source="census", instrument=None,
                          metric="error", value=None, threshold=None, flagged=0, payload={"error": repr(e)[:300]})
        except Exception:                                       # noqa: BLE001 - never stops the pass
            pass
        return {"error": repr(e)[:200]}
