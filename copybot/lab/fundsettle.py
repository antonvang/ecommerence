"""PROTOCOL_V3 amendment 21y section B: settled funding of the watched markets, collected forward only.

Every scanner pass asks Binance for the settlements of each market in moves.WATCH from 2026-10-24 21:00 UTC on and
stores each (symbol, fundingTime) once as `funding_settled`. Older settlements are never requested. Predicted funding
(21x) and settled funding stay apart; only settled funding counts as income or cost.
"""
from __future__ import annotations

import json
import time
import urllib.parse

from lab import moves

DETECTOR, START_MS = "funding_settled/1", 1_792_875_600_000          # 2026-10-24 21:00:00 UTC
SOURCE = f"{moves.BN}/fapi/v1/fundingRate"


def known(db):
    return {(r["instrument"], int(r["value_ts"])) for r in db.q(
        "SELECT instrument, json_extract(payload, '$.funding_time') AS value_ts FROM observations WHERE detector=? "
        "AND metric='funding_settled'", DETECTOR)}


def run(db, get, now=None):
    """`get(url)` returns parsed JSON. Returns counts; a market's error is recorded and never stops the others."""
    now = now or time.time()
    seen, new, errors = known(db), 0, 0
    for sym in moves.WATCH:
        url = f"{SOURCE}?symbol={urllib.parse.quote(sym)}&startTime={START_MS}&limit=1000"
        try:
            rows = get(url)
        except Exception as e:                                   # noqa: BLE001 - recorded, never fatal
            db.append("observations", ts=int(now), detector=DETECTOR, source=SOURCE, instrument=sym, metric="error",
                      value=None, threshold=None, flagged=0, payload={"error": f"{e!r}"[:300]})
            errors += 1
            continue
        for r in sorted(rows or [], key=lambda x: int(x["fundingTime"])):
            ft = int(r["fundingTime"]) // 1000
            if ft * 1000 < START_MS or (sym, ft) in seen or ft > now:
                continue
            db.append("observations", ts=int(now), detector=DETECTOR, source=SOURCE, instrument=sym,
                      metric="funding_settled", value=float(r["fundingRate"]), threshold=None, flagged=0,
                      payload={"funding_time": ft, "rate": float(r["fundingRate"]),
                               "mark_price": float(r["markPrice"]) if r.get("markPrice") not in (None, "") else None,
                               "fetched_ts": int(now), "rule": "research/PROTOCOL_V3.md amendment 21y B"})
            seen.add((sym, ft))
            new += 1
    return {"new": new, "errors": errors}


def settled(db, sym, t0, t1):
    """Settlements of `sym` with funding_time in [t0, t1): [(funding_time, rate)]."""
    out = []
    for r in db.q("SELECT payload FROM observations WHERE detector=? AND metric='funding_settled' AND instrument=? "
                  "ORDER BY id", DETECTOR, sym):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        if t0 <= p["funding_time"] < t1:
            out.append((p["funding_time"], p["rate"]))
    return out
