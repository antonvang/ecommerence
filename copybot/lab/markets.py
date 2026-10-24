"""Dashboard market scanner (research/LINUX_DRIFT.md 2026-10-24 22:23): the latest abnormal_move scan per market, read
from the detector's own observations. Read-only; nothing is recomputed differently from the detector, nothing trades.
"""
from __future__ import annotations

import json
import time

from lab import moves

DETECTOR = "abnormal_move/1"
FRESH_S, SPARK_HOURS, MOVE_LOOKBACK_S = 75 * 60, 48, 24 * 3600


def _p(raw):
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def view(db, now=None):
    now = now or time.time()
    last_scan = db.one("SELECT MAX(ts) FROM observations WHERE detector=?", DETECTOR)[0]
    since = (last_scan or now) - (SPARK_HOURS + 2) * 3600
    rows = db.q("SELECT ts, instrument, metric, value, flagged, payload FROM observations WHERE detector=? AND ts>=? "
                "ORDER BY ts, id", DETECTOR, since)
    latest, spark, book, problems = {}, {}, {}, {}
    for r in rows:
        sym, metric = r["instrument"], r["metric"]
        if metric == "z_1h":
            p = _p(r["payload"])
            latest[sym] = (r["ts"], p)
            if p.get("open_s") is not None:
                spark.setdefault(sym, {}).setdefault(p["open_s"], p.get("price"))      # earliest scan of the hour
        elif metric in ("book_rt", "spread"):
            book.setdefault(sym, {})[metric] = (r["ts"], r["value"], _p(r["payload"]))
        elif metric in ("error", "history_short"):
            problems.setdefault(sym, []).append((r["ts"], metric, _p(r["payload"]).get("error") or r["value"]))
    moves_ev = {}
    for r in db.q("SELECT id, ts, payload FROM events WHERE kind='opportunity.move' AND ts>=? ORDER BY id",
                  now - MOVE_LOOKBACK_S):
        p = _p(r["payload"])
        moves_ev[p.get("instrument")] = {"id": r["id"], "ts": r["ts"], "flags": p.get("flags"),
                                         "triage": p.get("triage"), "news": (p.get("news") or [])[:3],
                                         "macro": (p.get("macro") or {}).get("releases") or []}
    out = []
    for sym, (cls, label, _) in moves.WATCH.items():
        ts_p = latest.get(sym)
        ts, p = ts_p if ts_p else (None, {})
        b = book.get(sym, {})
        rt = b.get("book_rt")
        recent_problems = [x for x in problems.get(sym, []) if last_scan and x[0] >= last_scan - 60]
        pts = sorted(spark.get(sym, {}).items())[-SPARK_HOURS:]
        status = ("fejl" if recent_problems else "ingen data" if ts is None else
                  "forældet" if now - ts > FRESH_S else "frisk")
        out.append({
            "symbol": sym, "label": label, "class": cls, "venue": "Binance USD-M perpetual", "status": status,
            "scan_ts": ts, "data_age_s": (now - p["close_s"]) if p.get("close_s") else None,
            "price": p.get("price"), "ret_1h": p.get("ret_1h"), "ret_24h": p.get("ret_24h"), "z_1h": p.get("z_1h"),
            "z_24h": p.get("z_24h"), "volume_ratio": p.get("volume_ratio"), "quote_volume_1h": p.get("quote_volume_1h"),
            "premium": ((p["mark"] - p["index"]) / p["index"]) if p.get("index") else None,
            "book_rt": rt[1] if rt else None, "spread": (b.get("spread") or (None, None))[1],
            "book_error": (rt[2].get("error") if rt else None), "off_hours": bool(rt[2].get("off_hours")) if rt else None,
            "flags": p.get("flags") or [], "spark": [[o, px] for o, px in pts if px is not None],
            "problems": [{"ts": t, "kind": k, "detail": d} for t, k, d in recent_problems],
            "investigation": moves_ev.get(sym)})
    return {"markets": out, "last_scan_ts": last_scan, "now": now,
            "cadence": "hver time kl. HH:02 UTC (ikke realtid)",
            "thresholds": {"z_1h": moves.Z1, "z_24h": moves.Z24, "volume_ratio": moves.VOLUME_RATIO},
            "label": "observationer, ikke handelsmuligheder; et flag starter en undersøgelse, aldrig en ordre"}
