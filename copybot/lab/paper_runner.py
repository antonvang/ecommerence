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

from lab import lifecycle, pipeline, registry
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


CM_DAYS = 120


def _cm_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "copybot-lab/paper (read-only)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def fetch_cm_live(metrics, symbols, now, get=_cm_get):
    """CoinMetrics community daily values for the last CM_DAYS days up to yesterday: {metric: {symbol: {day: v}}}."""
    from datetime import datetime, timezone
    end = int(now) // 86400 * 86400 - 86400
    d0 = datetime.fromtimestamp(end - CM_DAYS * 86400, timezone.utc).strftime("%Y-%m-%d")
    d1 = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m-%d")
    assets = ",".join(s.replace("USDT", "").lower() for s in symbols)
    out = {m: {} for m in metrics}
    url = (f"https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets={assets}&metrics={','.join(metrics)}"
           f"&frequency=1d&start_time={d0}&end_time={d1}&page_size=10000")
    for _ in range(50):
        res = get(url)
        for row in res.get("data") or []:
            day = int(datetime.strptime(row["time"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
            for m in metrics:
                if row.get(m) not in (None, "") and day <= end:
                    out[m].setdefault(row["asset"].upper() + "USDT", {})[day] = float(row[m])
        url = res.get("next_page_url")
        if not url:
            break
    return out


def shadow_experiments(db):
    from lab.paper import shadow_active
    return [x["exp_id"] for x in registry.status(db) if x["state"] == "OBSERVATION" and shadow_active(db, x["exp_id"])]


def paper_experiments(db):
    return [x["exp_id"] for x in registry.status(db) if x["state"] == "PAPER_TRADING" and x["exp_id"].startswith("E_")]


def closing_ledgers(db):
    """Ledgers that still hold positions but may no longer trade: approved paper strategies that were rejected or
    retired, and shadow ledgers whose shadow ended. Amendment 4: their positions are closed, never forgotten."""
    from lab.paper import PaperEngine, shadow_active
    eng, out = PaperEngine(db), []
    for r in db.q("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started'"):
        led = r[0]
        base = led[len("SHADOW_"):] if led.startswith("SHADOW_") else led
        st = lifecycle.state(db, base)
        done = (not shadow_active(db, base)) if led.startswith("SHADOW_") else st in ("REJECTED", "RETIRED")
        if done and eng.ledger(led)["positions"]:
            out.append((led, base))
    return out


def close_ledger(db, led, base, get, now):
    eng, hour = PaperEngine(db, lambda: now), int(now) // HOUR * HOUR
    orders = []
    for s, q in eng.ledger(led)["positions"].items():
        try:
            _, _, book, _ = fetch_market(s, now, get)
        except Exception as e:
            orders.append({"symbol": s, "status": f"fetch failed: {e!r}"[:80]})
            continue
        r = eng.submit_taker(led, f"{led}|close|{hour}|{s}", s, "sell" if q > 0 else "buy", abs(q), book,
                             reduce_only=True, signal_ref="close: strategy ended")
        orders.append({"symbol": s, "status": r["status"]})
    db.event("paper.closing", "agent:paper-1", led, {"orders": orders, "simulated": True})
    return {"status": "closing", "orders": orders}


def _guarded(db, ledger, fn):
    """One ledger's failure never stops the others (closing in particular); it is reported, not swallowed."""
    try:
        return fn()
    except Exception as e:
        last = db.one("SELECT payload FROM events WHERE kind='paper.error' AND exp_id=? ORDER BY id DESC LIMIT 1", ledger)
        if last is None or json.loads(last[0]).get("error") != repr(e)[:300]:     # a new or changed error, once
            db.event("paper.error", "agent:paper-1", ledger, {"error": repr(e)[:300]})
        return {"status": "error", "reason": repr(e)[:200]}


def run(db, get=_get, now=None, cm_get=_cm_get):
    from lab import promotion
    now = now or time.time()
    out = {}
    for led, base in closing_ledgers(db):              # reduce-only: allowed even without a supervisor or FAIL_CLOSED
        out[led] = _guarded(db, led, lambda: close_ledger(db, led, base, get, now))
    if not promotion.supervisor_ok(db, now):
        return {"experiments": len(out), "results": out, "simulated": True, "blocked": "supervisor state unknown"}
    for eid in paper_experiments(db):
        ok, why = promotion.trading_authorized(db, eid)
        if not ok:
            if not db.one("SELECT 1 FROM events WHERE kind='paper.not_authorized' AND exp_id=? AND payload LIKE ?",
                          eid, f"%{why[:40]}%"):
                db.event("paper.not_authorized", "agent:paper-1", eid, {"reason": why})
            out[eid] = {"status": "not authorized", "reason": why}
            continue
        out[eid] = _guarded(db, eid, lambda: run_one(db, eid, get, now, cm_get=cm_get))
    for eid in shadow_experiments(db):                 # amendment 3: simulated, separate ledger, no effect on tests
        out["SHADOW_" + eid] = _guarded(db, "SHADOW_" + eid,
                                        lambda: run_one(db, eid, get, now, ledger="SHADOW_" + eid, cm_get=cm_get))
    return {"experiments": len(out), "results": out, "simulated": True}


def run_one(db, eid, get, now, ledger=None, cm_get=_cm_get):
    """Trade experiment `eid`'s frozen strategy on the simulated ledger `ledger` (default: the experiment itself)."""
    L = ledger or eid
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    spec = json.loads(registry.latest(db, eid)["spec_json"])
    tpl = catalogue.TEMPLATES[spec["template"]]
    if set(tpl.get("needs") or []) & {"metrics", "dvol", "stable", "taker", "rates"}:
        if not db.one("SELECT 1 FROM events WHERE kind='paper.unsupported' AND exp_id=?", L):
            db.event("paper.unsupported", "agent:paper-1", L, {"reason": "live inputs for this template are not "
                                                                          "built yet (research/PROTOCOL_V3.md section 7)"})
        return {"status": "unsupported", "reason": "live data for this template is not implemented; no orders"}
    eng.start(L, CAPITAL, cost_model(), actor="agent:paper-1")
    if risk.paused(L) or risk.fail_closed():
        return {"status": "paused" if risk.paused(L) else "fail_closed"}
    try:
        variant = pipeline.frozen_variant(db, eid)                    # fail closed: no orders on unverified rules
    except pipeline.ArtifactError as e:
        if not db.one("SELECT 1 FROM events WHERE kind='paper.blocked' AND exp_id=? AND payload LIKE ?", L,
                      f"%{str(e)[:60]}%"):
            db.event("paper.blocked", "agent:paper-1", L, {"reason": str(e), "orders": "none"})
        return {"status": "blocked", "reason": str(e)}
    hour = int(now) // HOUR * HOUR
    market = {}
    try:
        for s in catalogue.universe(spec["template"]):
            market[s] = fetch_market(s, now, get)
    except Exception as e:
        risk.pause(L, "data_fetch", None, None, f"public market data fetch failed: {e!r}"[:300], eng.cancel_entries)
        return {"status": "paused", "reason": "data fetch failed"}
    bundle = None
    if "cm" in (tpl.get("needs") or []):
        try:
            bundle = {"cm": fetch_cm_live(tpl["cm_metrics"], list(market), now, cm_get)}
        except Exception as e:
            risk.pause(L, "data_fetch", None, None, f"CoinMetrics fetch failed: {e!r}"[:300], eng.cancel_entries)
            return {"status": "paused", "reason": "CoinMetrics fetch failed"}
    for s, (bars, _, book, _) in market.items():
        if not bars or now - (bars[-1][0] + HOUR) > MAX_BAR_AGE or book.crossed():
            risk.pause(L, "data_stale", None, MAX_BAR_AGE, f"{s}: stale bars or invalid book", eng.cancel_entries)
            return {"status": "paused", "reason": f"{s} data stale or invalid"}
        risk.observe_book(L, book)
    marks = {s: m[2].mid() for s, m in market.items()}
    equity = eng.pnl(L, marks)["equity"]
    fam = tpl["family"]
    nxt = {s: m[0] + [(m[0][-1][0] + HOUR, m[0][-1][2], m[0][-1][2])] for s, m in market.items()}   # prices unused
    vol = {s: m[3] for s, m in market.items()} if tpl.get("needs_volume") else None
    xs = None
    if tpl.get("cross_sectional"):
        fund = {s: m[1] for s, m in market.items()}
        if tpl.get("needs"):
            xs = fam(nxt, fund, variant["params"], None, extra=bundle)
        else:
            xs = fam(nxt, fund, variant["params"], None, vol) if vol is not None else fam(nxt, fund, variant["params"])
    orders = []
    for s, (bars, funding, book, _) in market.items():
        target_pos = xs[s][-1] if xs else fam(nxt[s], funding, variant["params"], (variant["fit"] or {}).get(s))[-1]
        target_qty = target_pos * (equity / len(market)) / marks[s]
        cur = eng.ledger(L)["positions"].get(s, 0.0)
        delta = target_qty - cur
        if abs(delta) * marks[s] < MIN_NOTIONAL:
            continue
        reduce_only = abs(target_qty) < abs(cur) and (target_qty == 0 or (target_qty > 0) == (cur > 0))
        r = eng.submit_taker(L, f"{L}|{hour}|{s}", s, "buy" if delta > 0 else "sell", abs(delta), book,
                             reduce_only=reduce_only, signal_ref=f"{spec['template']}@{hour}")
        orders.append({"symbol": s, "status": r["status"], "qty": abs(delta)})
    if not db.one("SELECT 1 FROM sim_equity WHERE exp_id=? AND ts>=?", L, hour):
        eng.mark(L, marks)
    rec = eng.reconcile(L)
    if not rec["ok"]:
        risk.trip_fail_closed("reconciliation", f"{L}: {rec['problems']}"[:500])
    return {"status": "ok", "orders": orders, "pnl": eng.pnl(L, marks), "reconciled": rec["ok"]}

