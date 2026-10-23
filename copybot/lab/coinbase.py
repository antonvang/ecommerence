"""PROTOCOL_V3 amendment 17g (with its precision): the first trade of every Coinbase USD market, read from CoinMetrics'
community catalogue (one keyless GET; no Coinbase host). Observations only (detector "coinbase/1"); nothing here trades,
ranks or decides.

Each market is stored once: metric "cb_listing" (value = first trade, payload with usable_from = first trade + 1 h) when
the first trade lies in [2020-03-01, 2024-01-01), else "cb_none" with the reason (no time is kept for a first trade from
2024-01-01). A failed read is "cb_error"; a rerun skips every stored market.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

DETECTOR = "coinbase/1"
URL = "https://community-api.coinmetrics.io/v4/catalog-all/markets?exchange=coinbase&type=spot"
FROM = int(datetime(2020, 3, 1, tzinfo=timezone.utc).timestamp())     # explore0 starts here (point 1)
LAG_S = 3600                                                          # point 2: t = first trade + 1 hour


def _end():
    from lab import measure
    return int(measure.END)                                           # 2024-01-01: never kept from here


def _ts(s):
    """'2022-10-11T17:16:48.452411000Z' -> epoch seconds (nanoseconds cut to microseconds)."""
    s = (s or "").rstrip("Z")
    if "." in s:
        head, frac = s.split(".", 1)
        s = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def classify(m, end=None):
    """(metric, value, payload) for one catalogue row with quote usd."""
    end = end or _end()
    coin = (m.get("base") or "").upper()
    first = (m.get("trades") or {}).get("min_time")
    base = {"market": m.get("market"), "coin": coin, "status": m.get("status"), "rule": "amendment 17g"}
    if not first:
        return "cb_none", None, base | {"reason": "no trades in the catalogue"}
    t = _ts(first)
    if t < FROM:
        return "cb_none", None, base | {"reason": "first trade before 2020-03-01"}
    if t >= end:
        return "cb_none", None, base | {"reason": "first trade from 2024-01-01 (not kept)"}
    return "cb_listing", t, base | {"first_trade_ts": t, "usable_from": int(t) + LAG_S,
                                    "title": f"Coinbase {coin}-USD first trade"}


def known(db):
    return {r[0] for r in db.q("SELECT instrument FROM observations WHERE detector=? AND metric IN ('cb_listing', "
                               "'cb_none')", DETECTOR)}


def backfill(db, get=None, now=None):
    """One pass over the catalogue; returns counts. A failed read is recorded and returned, never raised."""
    now = now or time.time()
    if get is None:
        from lab import news
        get = news.http_get
    try:
        rows = json.loads(get(URL))["data"]
    except Exception as e:                                  # noqa: BLE001 - recorded, a rerun tries again
        db.append("observations", ts=int(now), detector=DETECTOR, source=URL, instrument=None, metric="cb_error",
                  value=None, threshold=None, flagged=0, payload={"error": f"{e!r}"[:300]})
        return {"error": f"{e!r}"[:300]}
    seen, out, end = known(db), {"cb_listing": 0, "cb_none": 0, "skipped": 0}, _end()
    with db.tx():
        for m in rows:
            if m.get("quote") != "usd" or not m.get("market"):
                continue
            if m["market"] in seen:
                out["skipped"] += 1
                continue
            metric, value, payload = classify(m, end)
            db.append("observations", ts=int(now), detector=DETECTOR, source=URL, instrument=m["market"],
                      metric=metric, value=value, threshold=None, flagged=0, payload=payload)
            seen.add(m["market"])
            out[metric] += 1
    return out | {"decisional": False}
