"""PROTOCOL_V3 amendment 21v: a current capacity curve from deep public books, at most once per 23 h.

For the watched markets and every perp and spot leg with a paper fill in the last 14 days: the round trip of 500 to
50 000 USD walked through 500 levels (fees excluded), the spread, the depth per side and whether the first 20 levels
alone (all the paper engine sees) could fill the size. A size the 500 levels cannot fill is stored empty and marked
censored. Current, never historical; capacity status stays UNTESTABLE_CAPACITY without a documented edge.
"""
from __future__ import annotations

import json
import time
import urllib.parse

from lab import moves

DETECTOR = "capacity/1"
SIZES = (500, 2_000, 5_000, 20_000, 50_000)
EVERY_S, PACE_S, LOOKBACK_S, LEVELS, PAPER_LEVELS = 23 * 3600, 0.25, 14 * 86400, 500, 20
PERP, SPOT = "https://fapi.binance.com", "https://data-api.binance.vision"
SPOT_SUFFIX = ".SPOT"


def universe(db, now):
    """moves.WATCH plus every instrument with a paper fill in the last 14 days (21v point 1)."""
    traded = {r[0] for r in db.q("SELECT DISTINCT instrument FROM sim_fills WHERE ts>=?", now - LOOKBACK_S)}
    return sorted(set(moves.WATCH) | {s for s in traded if s and not s.startswith("HL:")})


def url(inst):
    if inst.endswith(SPOT_SUFFIX):
        return f"{SPOT}/api/v3/depth?symbol={urllib.parse.quote(inst[:-len(SPOT_SUFFIX)])}&limit={LEVELS}"
    return f"{PERP}/fapi/v1/depth?symbol={urllib.parse.quote(inst)}&limit={LEVELS}"


def curve(bids, asks):
    """One row per size from a parsed book (21v point 4); None values are censored, never guessed."""
    mid = (bids[0][0] + asks[0][0]) / 2
    depth_bid, depth_ask = sum(p * q for p, q in bids), sum(p * q for p, q in asks)
    rows = []
    for s in SIZES:
        buy, sell = moves.walk(asks, s), moves.walk(bids, s)
        fits20 = moves.walk(asks[:PAPER_LEVELS], s) is not None and moves.walk(bids[:PAPER_LEVELS], s) is not None
        rt = (buy - sell) / mid if buy is not None and sell is not None else None
        rows.append({"size_usd": s, "round_trip": rt, "censored": rt is None, "fits_20_levels": fits20,
                     "buy_vwap": buy, "sell_vwap": sell, "mid": mid, "spread": (asks[0][0] - bids[0][0]) / mid,
                     "depth_bid_usd": depth_bid, "depth_ask_usd": depth_ask, "levels": [len(bids), len(asks)]})
    return rows


def due(db, now):
    last = db.one("SELECT MAX(ts) FROM observations WHERE detector=?", DETECTOR)[0]
    return last is None or now - last >= EVERY_S


def run(db, get, now=None, sleep=time.sleep):
    """One collection when due (21v point 2). `get(url)` returns raw bytes. Never raises for a source error."""
    now = now or time.time()
    if not due(db, now):
        return {"skipped": "less than 23 h since the last curve"}
    done, errors, skipped = 0, 0, 0
    status = {}
    try:                                                         # 21x point 2: one exchangeInfo per run
        status = {x["symbol"]: x.get("status") for x in json.loads(get(f"{PERP}/fapi/v1/exchangeInfo"))["symbols"]}
    except Exception:                                            # noqa: BLE001 - without it the curve runs as before
        status = {}
    for inst in universe(db, now):
        src = url(inst)
        st = None if inst.endswith(SPOT_SUFFIX) else status.get(inst)
        if st is not None and st != "TRADING":
            db.append("observations", ts=int(now), detector=DETECTOR, source=f"{PERP}/fapi/v1/exchangeInfo",
                      instrument=inst, metric="not_trading", value=None, threshold=None, flagged=0,
                      payload={"status": st, "rule": "research/PROTOCOL_V3.md amendment 21x point 2"})
            skipped += 1
            continue
        try:
            d = json.loads(get(src))
            bids = [(float(p), float(q)) for p, q in d.get("bids") or []]
            asks = [(float(p), float(q)) for p, q in d.get("asks") or []]
            if not bids or not asks:
                raise ValueError("empty book")
            rows = curve(bids, asks)
        except Exception as e:                                   # noqa: BLE001 - recorded, never fatal
            db.append("observations", ts=int(now), detector=DETECTOR, source=src.split("?")[0], instrument=inst,
                      metric="error", value=None, threshold=None, flagged=0, payload={"error": f"{e!r}"[:300]})
            errors += 1
        else:
            with db.tx():
                for r in rows:
                    db.append("observations", ts=int(now), detector=DETECTOR, source=src.split("?")[0],
                              instrument=inst, metric=f"rt_{r['size_usd']}", value=r["round_trip"], threshold=None,
                              flagged=0, payload={**r, "fees": "not included", "label": "nutidig, ikke historisk",
                                                  "rule": "research/PROTOCOL_V3.md amendment 21v"})
            done += 1
        sleep(PACE_S)
    return {"books": done, "errors": errors, "not_trading": skipped}


def latest(db):
    """The newest curve per instrument: {inst: {"ts", "rows": [payload per size]}} (for the dashboard)."""
    last = db.one("SELECT MAX(ts) FROM observations WHERE detector=?", DETECTOR)[0]
    if last is None:
        return {"ts": None, "books": {}, "missing": {}}
    out = {}
    for r in db.q("SELECT instrument, metric, payload FROM observations WHERE detector=? AND ts>=? AND metric LIKE 'rt_%' "
                  "ORDER BY id", DETECTOR, last - 3600):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        out.setdefault(r["instrument"], {})[p["size_usd"]] = p
    meta = {}
    for r in db.q("SELECT instrument, metric, payload FROM observations WHERE detector=? AND ts>=? AND metric IN "
                  "('error', 'not_trading') ORDER BY id", DETECTOR, last - 3600):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        meta[r["instrument"]] = {"kind": r["metric"], "detail": p.get("status") or p.get("error")}
    return {"ts": last, "books": {k: [v[s] for s in sorted(v)] for k, v in sorted(out.items())}, "missing": meta}
