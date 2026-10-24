"""Forward point-in-time on-chain exchange flows (research/PROTOCOL_V3.md amendment 21q). Data only, never a decision.

Every news-watch pass, at most once per 6 hours, reads the last 3 days of CoinMetrics community daily FlowInExNtv,
FlowOutExNtv and SplyExNtv for btc and eth. The first value seen for (asset, metric, date) is stored with the time it
was fetched (`flow_first`, usable from then); a later different value is logged as `flow_revision`. The free series
are revised retroactively by CoinMetrics, so only values collected from 2026-10-24 on are point-in-time.
"""
from __future__ import annotations

import json
import time
import urllib.parse

DETECTOR = "onchain/1"
SOURCE = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
ASSETS, METRICS = ("btc", "eth"), ("FlowInExNtv", "FlowOutExNtv", "SplyExNtv")
EVERY_S, BACK_DAYS = 6 * 3600, 3
DAY = 86400
_STATE = {"last": 0.0}


def url(now):
    start = time.strftime("%Y-%m-%d", time.gmtime(now - BACK_DAYS * DAY))
    return SOURCE + "?" + urllib.parse.urlencode({"assets": ",".join(ASSETS), "metrics": ",".join(METRICS),
                                                  "frequency": "1d", "start_time": start, "page_size": 100})


def _known(db):
    out = {}
    for r in db.q("SELECT metric, payload FROM observations WHERE detector=? AND metric IN ('flow_first', "
                  "'flow_revision') ORDER BY id", DETECTOR):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        out[(p["asset"], p["metric"], p["date"])] = p["value"] if r["metric"] == "flow_first" else p["new"]
    return out


def run(db, get, now=None):
    """One collection (21q point 3). Returns counts; never raises for a source error."""
    now = now or time.time()
    if now - _STATE["last"] < EVERY_S:
        return {"skipped": "less than 6 h since the last collection"}
    _STATE["last"] = now
    try:
        rows = json.loads(get(url(now))).get("data") or []
    except Exception as e:                                       # noqa: BLE001 - recorded, never fatal
        db.append("observations", ts=int(now), detector=DETECTOR, source=SOURCE, instrument=None,
                  metric="onchain_error", value=None, threshold=None, flagged=0, payload={"error": f"{e!r}"[:300]})
        return {"error": f"{e!r}"[:200]}
    known, first, revised = _known(db), 0, 0
    with db.tx():
        for r in rows:
            date = (r.get("time") or "")[:10]
            for m in METRICS:
                if r.get(m) in (None, ""):
                    continue
                v, key = float(r[m]), (r.get("asset"), m, date)
                if key not in known:
                    db.append("observations", ts=int(now), detector=DETECTOR, source=SOURCE, instrument=f"{key[0]}:{m}",
                              metric="flow_first", value=v, threshold=None, flagged=0,
                              payload={"asset": key[0], "metric": m, "date": date, "value": v, "fetched_ts": int(now),
                                       "usable_from": int(now), "licence": "CC BY-NC 4.0 (Coin Metrics community)"})
                    known[key], first = v, first + 1
                elif abs(known[key] - v) > 1e-9 * max(1.0, abs(v)):
                    db.append("observations", ts=int(now), detector=DETECTOR, source=SOURCE, instrument=f"{key[0]}:{m}",
                              metric="flow_revision", value=v, threshold=None, flagged=0,
                              payload={"asset": key[0], "metric": m, "date": date, "old": known[key], "new": v,
                                       "fetched_ts": int(now)})
                    known[key], revised = v, revised + 1
    return {"first": first, "revisions": revised, "rows": len(rows)}
