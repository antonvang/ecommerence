"""Forward tests against buy-and-hold (research/LINUX_DRIFT.md 2026-10-23). Display and record only.

At most once an hour, for every active forward-test ledger: the equal-weight buy-and-hold return of the coins the
ledger has traded, from its first mark to now. A coin's start price is the 1 h open at the ledger's start (read once and
kept as an observation); the current prices come from one call for all symbols (/fapi/v1/ticker/price). Rows go to
`observations` (detector benchmark/1) so every figure can be recomputed. It decides nothing and changes no ledger.
"""
from __future__ import annotations

import time

DETECTOR = "benchmark/1"
EVERY_S = 3600
PREFIX = "FWD_"
RETRY_S = 600                   # after a failed or empty attempt: no new network call for 10 min
_TRIED = {"t": 0.0}


def _get(path):
    from lab import paper_runner
    return paper_runner._get(path)


def _ledgers(db, now):
    """{ledger: (start ts, sorted traded symbols)} for forward ledgers with a mark in the last day."""
    out = {}
    for led, t0 in db.q("SELECT exp_id, MIN(ts) FROM sim_equity WHERE exp_id LIKE ? GROUP BY exp_id "
                        "HAVING MAX(ts) > ?", PREFIX + "%", int(now) - 86400):
        syms = sorted(r[0] for r in db.q("SELECT DISTINCT instrument FROM sim_fills WHERE exp_id=?", led))
        if syms:
            out[led] = (int(t0), syms)
    return out


def _start_price(db, sym, t0, get, now):
    """The 1 h open at t0's hour, read once and kept."""
    key = f"{sym}@{t0 // 3600 * 3600}"
    r = db.one("SELECT value FROM observations WHERE detector=? AND metric='bh_start_price' AND instrument=?",
               DETECTOR, key)
    if r:
        return r[0]
    from lab.paper_runner import _q
    k = get(f"/fapi/v1/klines?symbol={_q(sym)}&interval=1h&startTime={t0 // 3600 * 3600 * 1000}&limit=1")
    px = float(k[0][1])
    db.append("observations", ts=int(now), detector=DETECTOR, source="https://fapi.binance.com", instrument=key,
              metric="bh_start_price", value=px, threshold=None, flagged=0, payload={"symbol": sym, "hour": t0})
    return px


def update(db, now=None, get=_get):
    """Record each forward ledger's buy-and-hold return, at most once an hour. Returns how many were recorded."""
    now = now or time.time()
    last = db.one("SELECT MAX(ts) FROM observations WHERE detector=? AND metric='fwd_bh_return'", DETECTOR)[0]
    if last and now - last < EVERY_S:
        return 0
    leds = _ledgers(db, now)
    if not leds or now - _TRIED["t"] < RETRY_S:
        return 0
    _TRIED["t"] = now
    prices = {x["symbol"]: float(x["price"]) for x in get("/fapi/v1/ticker/price")}
    n = 0
    for led, (t0, syms) in sorted(leds.items()):
        rets = []
        for s in syms:
            if s not in prices:
                continue
            start = _start_price(db, s, t0, get, now)
            if start > 0:
                rets.append(prices[s] / start - 1)
        if not rets:
            continue
        db.append("observations", ts=int(now), detector=DETECTOR, source="https://fapi.binance.com", instrument=led,
                  metric="fwd_bh_return", value=sum(rets) / len(rets), threshold=None, flagged=0,
                  payload={"symbols": syms, "used": len(rets), "start_ts": t0, "decisional": False})
        n += 1
    return n


def latest(db):
    """{ledger: {"bh_return", "ts", "symbols"}} from the newest recorded row per forward ledger."""
    import json
    out = {}
    for led, v, ts, p in db.q("SELECT instrument, value, ts, payload FROM observations o WHERE detector=? AND "
                              "metric='fwd_bh_return' AND id = (SELECT MAX(id) FROM observations WHERE detector=? AND "
                              "metric='fwd_bh_return' AND instrument=o.instrument)", DETECTOR, DETECTOR):
        p = json.loads(p) if isinstance(p, str) else (p or {})
        out[led] = {"bh_return": v, "ts": ts, "symbols": p.get("used")}
    return out
