"""PROTOCOL_V3 amendments 17g (with its precision) and 17h: the first trade of every Coinbase USD market and every Upbit
KRW market, read from CoinMetrics' community catalogue (keyless GETs; no exchange host). Observations only (detectors
"coinbase/1", "upbit/1"); nothing here trades, ranks or decides.

Each market is stored once: metric "cb_listing" (value = first trade, payload with usable_from = first trade + 1 h) when
the first trade lies in [2020-03-01, 2024-01-01), else "cb_none" with the reason (no time is kept for a first trade from
2024-01-01). Under 17h point 2 an Upbit first trade on a coverage day (>= 10 first trades that UTC day summed over
the okex, huobi and kraken catalogues) is "cb_none" too. A failed read is "cb_error"; a rerun skips every stored market.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

CATALOG = "https://community-api.coinmetrics.io/v4/catalog-all/markets?exchange={}&type=spot"
DETECTOR, URL = "coinbase/1", CATALOG.format("coinbase")
SOURCES = {"coinbase": {"detector": DETECTOR, "quote": "usd", "name": "Coinbase", "rule": "amendment 17g"},
           "upbit": {"detector": "upbit/1", "quote": "krw", "name": "Upbit", "rule": "amendment 17h",
                     "spikes": ("okex", "huobi", "kraken")}}
SPIKE_MIN = 10                                                        # 17h point 2
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


def spike_days(rows_by_exchange):
    """17h point 2: UTC days with >= SPIKE_MIN first trades summed over the catalogues (each base's earliest market)."""
    count = {}
    for rows in rows_by_exchange:
        first = {}
        for m in rows:
            f = ((m.get("trades") or {}).get("min_time") or "")[:10]
            if f and (m.get("base") not in first or f < first[m.get("base")]):
                first[m.get("base")] = f
        for d in first.values():
            count[d] = count.get(d, 0) + 1
    return {d for d, c in count.items() if c >= SPIKE_MIN}


def classify(m, end=None, source="coinbase", spikes=frozenset()):
    """(metric, value, payload) for one catalogue row with the source's quote."""
    end, src = end or _end(), SOURCES[source]
    coin = (m.get("base") or "").upper()
    first = (m.get("trades") or {}).get("min_time")
    base = {"market": m.get("market"), "coin": coin, "status": m.get("status"), "rule": src["rule"]}
    if not first:
        return "cb_none", None, base | {"reason": "no trades in the catalogue"}
    t = _ts(first)
    if t < FROM:
        return "cb_none", None, base | {"reason": "first trade before 2020-03-01"}
    if t >= end:
        return "cb_none", None, base | {"reason": "first trade from 2024-01-01 (not kept)"}
    day = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
    if day in spikes:
        return "cb_none", None, base | {"reason": f"coverage day {day} (amendment 17h point 2)"}
    return "cb_listing", t, base | {"first_trade_ts": t, "usable_from": int(t) + LAG_S,
                                    "title": f"{src['name']} {coin}-{src['quote'].upper()} first trade"}


def known(db, detector=DETECTOR):
    return {r[0] for r in db.q("SELECT instrument FROM observations WHERE detector=? AND metric IN ('cb_listing', "
                               "'cb_none')", detector)}


def backfill(db, get=None, now=None, source="coinbase"):
    """One pass over the source's catalogue (and, for 17h, the coverage catalogues); returns counts. A failed read is
    recorded and returned, never raised."""
    now, src = now or time.time(), SOURCES[source]
    url, det = CATALOG.format(source), src["detector"]
    if get is None:
        from lab import news
        get = news.http_get
    try:
        rows = json.loads(get(url))["data"]
        spikes = spike_days([json.loads(get(CATALOG.format(x)))["data"] for x in src.get("spikes", ())])
    except Exception as e:                                  # noqa: BLE001 - recorded, a rerun tries again
        db.append("observations", ts=int(now), detector=det, source=url, instrument=None, metric="cb_error",
                  value=None, threshold=None, flagged=0, payload={"error": f"{e!r}"[:300]})
        return {"error": f"{e!r}"[:300]}
    seen, out, end = known(db, det), {"cb_listing": 0, "cb_none": 0, "skipped": 0}, _end()
    with db.tx():
        for m in rows:
            if m.get("quote") != src["quote"] or not m.get("market"):
                continue
            if m["market"] in seen:
                out["skipped"] += 1
                continue
            metric, value, payload = classify(m, end, source, spikes)
            db.append("observations", ts=int(now), detector=det, source=url, instrument=m["market"],
                      metric=metric, value=value, threshold=None, flagged=0, payload=payload)
            seen.add(m["market"])
            out[metric] += 1
    return out | {"decisional": False}
