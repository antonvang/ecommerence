"""PROTOCOL_V3 amendment 38 A (D10): a forward hourly census of every Hyperliquid perp.

In the first premium-watch pass of each UTC hour (at most 10 minutes after the hour), one `observations` row (detector
hlcensus/1, metric snapshot) holds every perp's raw numbers from the metaAndAssetCtxs response premium-watch already
fetched that minute (amendment 13; no new call). Every universe name is kept, also k-prefixed and delisted ones. A
missing field is null, never 0. Nothing that decides reads it. A failure never stops premium-watch.
"""
from __future__ import annotations


DET, RULE = "hlcensus/1", "research/PROTOCOL_V3.md amendment 38 A"
HOUR, LATEST_S = 3600, 600
CTX_COLS = ("funding", "premium", "markPx", "oraclePx", "midPx", "openInterest", "dayNtlVlm", "prevDayPx")
COLS = CTX_COLS + ("isDelisted",)
_DONE = {}                                      # hour -> True once stored (the registry is checked after a restart)
_ERR = {}


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def snapshot(res):
    """{columns, rows: {name: [numbers in COLS order]}} from a metaAndAssetCtxs response [meta, ctxs]."""
    meta, ctxs = res
    out = {}
    for a, c in zip(meta.get("universe") or [], ctxs or []):
        name = a.get("name") or ""
        if not name:
            continue
        out[name] = [_num((c or {}).get(k)) for k in CTX_COLS] + [1.0 if a.get("isDelisted") else 0.0]
    return {"columns": list(COLS), "rows": out}


def _stored(db, hour):
    return db.one("SELECT 1 FROM observations WHERE detector=? AND metric='snapshot' AND ts>=? AND ts<? LIMIT 1",
                  DET, hour, hour + HOUR)


def observe(db, now, res):
    """Amendment 38 A for one premium-watch pass: the hour's snapshot if due; returns a short summary or None."""
    now = int(now)
    hour = now - now % HOUR
    if now - hour > LATEST_S or _DONE.get(hour):
        return None
    if _stored(db, hour):
        _DONE[hour] = True
        return None
    from lab.scanner import HL_INFO
    snap = snapshot(res)
    db.append("observations", ts=now, detector=DET, source=f"{HL_INFO} metaAndAssetCtxs", instrument=None,
              metric="snapshot", value=len(snap["rows"]), threshold=None, flagged=0,
              payload={**snap, "fetched_at": now, "rule": RULE,
                       "label": "rådata til senere præregistrerede hypoteser; ingen afgørelse"})
    _DONE[hour] = True
    return {"coins": len(snap["rows"])}


def guarded(db, now, res):
    """premium-watch's hook: a failure is recorded at most once an hour and never raised."""
    try:
        return observe(db, now, res)
    except Exception as e:                                      # noqa: BLE001
        try:
            if now - _ERR.get("at", 0) >= HOUR:
                _ERR["at"] = now
                db.append("observations", ts=int(now), detector=DET, source="hlcensus", instrument=None,
                          metric="error", value=None, threshold=None, flagged=0, payload={"error": repr(e)[:300]})
        except Exception:                                       # noqa: BLE001 - never stops the pass
            pass
        return {"error": repr(e)[:200]}
