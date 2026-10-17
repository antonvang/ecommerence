"""Paper execution for catalogue experiments (Mission 6). SIMULATION ONLY.

Runs only for experiments a human moved to PAPER_TRADING (which in turn requires a passed sealed holdout and a
VALIDATED -> PAPER_TRADING approval). Market data comes from Binance's public USD-M REST endpoints (no key, no account):
closed 1h klines, settled funding and a 20-level order book. The frozen variant from the experiment's artifacts decides
the target exposure for the hour that is starting; the paper engine walks the public book for the simulated fill.

Idempotency: order ids are `<exp>|<hour_ts>|<symbol>`, so a repeated pass in the same hour cannot trade twice.
Data problems (stale bars, empty or crossed book, fetch failure) pause the experiment through the risk module.
"""
from __future__ import annotations

import json
import time
import urllib.request

from lab import pipeline, registry
from lab.engine import catalogue, data
from lab.paper import Book, CostModel, PaperEngine
from lab.risk import Risk

REST = "https://fapi.binance.com"
CAPITAL = 10_000.0                      # simulated USD
MIN_NOTIONAL = 10.0
HOUR = 3600
MAX_BAR_AGE = 2 * HOUR


def _get(path):
    req = urllib.request.Request(REST + path, headers={"User-Agent": "copybot-lab/paper (read-only)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_market(sym, now, get=_get):
    """Closed 1h bars [(open_ts, open, close)], settled funding {ts: rate} and a Book."""
    kl = get(f"/fapi/v1/klines?symbol={sym}&interval=1h&limit=1000")
    bars = [(int(k[0]) // 1000, float(k[1]), float(k[4])) for k in kl if int(k[6]) // 1000 < now]
    volume = {int(k[0]) // 1000: float(k[7]) for k in kl if int(k[6]) // 1000 < now and len(k) > 7}
    fr = get(f"/fapi/v1/fundingRate?symbol={sym}&limit=200")
    funding = {int(f["fundingTime"]) // 1000 // HOUR * HOUR: float(f["fundingRate"]) for f in fr
               if int(f["fundingTime"]) // 1000 < now}
    d = get(f"/fapi/v1/depth?symbol={sym}&limit=20")
    book = Book(ts=now, bids=tuple((float(p), float(q)) for p, q in d["bids"]),
                asks=tuple((float(p), float(q)) for p, q in d["asks"]))
    return bars, funding, book, volume


def cost_model():
    c = catalogue.COSTS
    return CostModel(taker_fee=c["taker_fee"], extra_slippage=c["slippage"], expected_spread=2 * c["half_spread"])


def paper_experiments(db):
    return [x["exp_id"] for x in registry.status(db) if x["state"] == "PAPER_TRADING" and x["exp_id"].startswith("E_")]


def run(db, get=_get, now=None):
    now = now or time.time()
    out = {}
    for eid in paper_experiments(db):
        out[eid] = run_one(db, eid, get, now)
    return {"experiments": len(out), "results": out, "simulated": True}


def run_one(db, eid, get, now):
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    spec = json.loads(registry.latest(db, eid)["spec_json"])
    if set(catalogue.TEMPLATES[spec["template"]].get("needs") or []) & {"metrics", "dvol", "stable", "taker"}:
        if not db.one("SELECT 1 FROM events WHERE kind='paper.unsupported' AND exp_id=?", eid):
            db.event("paper.unsupported", "agent:paper-1", eid, {"reason": "live inputs for this template are not "
                                                                            "built yet (research/PROTOCOL_V3.md section 7)"})
        return {"status": "unsupported", "reason": "live data for this template is not implemented; no orders"}
    eng.start(eid, CAPITAL, cost_model(), actor="agent:paper-1")
    if risk.paused(eid) or risk.fail_closed():
        return {"status": "paused" if risk.paused(eid) else "fail_closed"}
    cost = pipeline.load_artifact(eid, "cost")
    variant = pipeline.load_artifact(eid, "backtest")["variants"][cost["selected"]]
    hour = int(now) // HOUR * HOUR
    market = {}
    try:
        for s in catalogue.universe(spec["template"]):
            market[s] = fetch_market(s, now, get)
    except Exception as e:
        risk.pause(eid, "data_fetch", None, None, f"public market data fetch failed: {e!r}"[:300], eng.cancel_entries)
        return {"status": "paused", "reason": "data fetch failed"}
    for s, (bars, _, book, _) in market.items():
        if not bars or now - (bars[-1][0] + HOUR) > MAX_BAR_AGE or book.crossed():
            risk.pause(eid, "data_stale", None, MAX_BAR_AGE, f"{s}: stale bars or invalid book", eng.cancel_entries)
            return {"status": "paused", "reason": f"{s} data stale or invalid"}
        risk.observe_book(eid, book)
    marks = {s: m[2].mid() for s, m in market.items()}
    equity = eng.pnl(eid, marks)["equity"]
    tpl = catalogue.TEMPLATES[spec["template"]]
    fam = tpl["family"]
    nxt = {s: m[0] + [(m[0][-1][0] + HOUR, m[0][-1][2], m[0][-1][2])] for s, m in market.items()}   # prices unused
    vol = {s: m[3] for s, m in market.items()} if tpl.get("needs_volume") else None
    xs = None
    if tpl.get("cross_sectional"):
        fund = {s: m[1] for s, m in market.items()}
        xs = fam(nxt, fund, variant["params"], None, vol) if vol is not None else fam(nxt, fund, variant["params"])
    orders = []
    for s, (bars, funding, book, _) in market.items():
        target_pos = xs[s][-1] if xs else fam(nxt[s], funding, variant["params"], (variant["fit"] or {}).get(s))[-1]
        target_qty = target_pos * (equity / len(market)) / marks[s]
        cur = eng.ledger(eid)["positions"].get(s, 0.0)
        delta = target_qty - cur
        if abs(delta) * marks[s] < MIN_NOTIONAL:
            continue
        reduce_only = abs(target_qty) < abs(cur) and (target_qty == 0 or (target_qty > 0) == (cur > 0))
        r = eng.submit_taker(eid, f"{eid}|{hour}|{s}", s, "buy" if delta > 0 else "sell", abs(delta), book,
                             reduce_only=reduce_only, signal_ref=f"{spec['template']}@{hour}")
        orders.append({"symbol": s, "status": r["status"], "qty": abs(delta)})
    if not db.one("SELECT 1 FROM sim_equity WHERE exp_id=? AND ts>=?", eid, hour):
        eng.mark(eid, marks)
    rec = eng.reconcile(eid)
    if not rec["ok"]:
        risk.trip_fail_closed("reconciliation", f"{eid}: {rec['problems']}"[:500])
    return {"status": "ok", "orders": orders, "pnl": eng.pnl(eid, marks), "reconciled": rec["ok"]}

