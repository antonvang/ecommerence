"""Paper execution for catalogue experiments (Mission 6). SIMULATION ONLY.

Runs only for experiments a human moved to PAPER_TRADING (which in turn requires a passed sealed holdout and a
VALIDATED -> PAPER_TRADING approval). Market data comes from Binance's public USD-M REST endpoints (no key, no account):
closed 1h klines, settled funding and a 20-level order book. The frozen variant from the experiment's artifacts decides
the target exposure for the hour that is starting; the paper engine walks the public book for the simulated fill.

Idempotency: order ids are `<exp>|<hour_ts>|<symbol>`, so a repeated pass in the same hour cannot trade twice.
Data problems (stale bars, empty or crossed book, fetch failure) pause the experiment through the risk module.
Funding (research/PROTOCOL_V3.md amendment 9 section 2): from T_F (paper.funding_started, written by the first pass
that books funding) every processed ledger - trading, paused or closing - books the settled funding of its positions.
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
SPOT_REST = "https://data-api.binance.vision"   # amendment 11 point 8: spot public book, a market-data-only host
SPOT_SUFFIX = ".SPOT"
HL_PREFIX = "HL:"                       # amendment 13: a Hyperliquid perp leg (public /info only)
HL_POST = None                          # tests replace the Hyperliquid /info call; live it is scanner.http_post
_HL_HOURLY = {}                         # coin -> (hour, settled funding, opens): read once per clock hour


def hl_info(body):
    """One public Hyperliquid /info request through the scanner's only body sender (tests: HL_POST)."""
    if HL_POST is not None:
        return HL_POST(body)
    from lab import scanner
    return scanner.http_post(scanner.HL_INFO, body)


def hl_hourly(coin, now):
    """Amendment 13: Hyperliquid settled funding {settle_ts: rate per hour} and 1h opens {open_ts: open} of the last
    48 hours (the bar in progress included), read once per clock hour when live."""
    hour = int(now) // HOUR * HOUR
    hit = _HL_HOURLY.get(coin) if HL_POST is None else None
    if hit and hit[0] == hour:
        return hit[1], hit[2]
    start = (hour - 48 * HOUR) * 1000
    fh = hl_info({"type": "fundingHistory", "coin": coin, "startTime": start})
    funding = {int(x["time"]) // 1000 // HOUR * HOUR: float(x["fundingRate"]) for x in fh
               if int(x["time"]) // 1000 <= now}
    cs = hl_info({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": start,
                                                     "endTime": int(now) * 1000}})
    opens = {int(c["t"]) // 1000: float(c["o"]) for c in cs if int(c["t"]) // 1000 <= now}
    if HL_POST is None and opens and max(opens) == hour:
        _HL_HOURLY[coin] = (hour, funding, opens)
    return funding, opens
CAPITAL = 10_000.0                      # simulated USD
MIN_NOTIONAL = 10.0
HOUR = 3600
MAX_BAR_AGE = 2 * HOUR


def _get(path):
    req = urllib.request.Request(path if path.startswith("https://") else REST + path, headers={"User-Agent": "copybot-lab/paper (read-only)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


_HOURLY = {}        # symbol -> (hour, bars, funding, volume, opens): bars and settled funding change once an hour
_CM_HOURLY = {}     # (metrics, symbols) -> (hour, values): CoinMetrics daily values, re-read once an hour


def fetch_book(sym, now, get=_get):
    """20-level public book: USD-M, Binance spot for `<SYM>.SPOT` (amendment 11), Hyperliquid for `HL:<COIN>` (13)."""
    if sym.startswith(HL_PREFIX):
        lv = hl_info({"type": "l2Book", "coin": sym[len(HL_PREFIX):]})["levels"]
        return Book(ts=now, bids=tuple((float(x["px"]), float(x["sz"])) for x in lv[0][:20]),
                    asks=tuple((float(x["px"]), float(x["sz"])) for x in lv[1][:20]))
    if sym.endswith(SPOT_SUFFIX):
        d = get(f"{SPOT_REST}/api/v3/depth?symbol={sym[:-len(SPOT_SUFFIX)]}&limit=20")
    else:
        d = get(f"/fapi/v1/depth?symbol={sym}&limit=20")
    return Book(ts=now, bids=tuple((float(p), float(q)) for p, q in d["bids"]),
                asks=tuple((float(p), float(q)) for p, q in d["asks"]))


def hourly(sym, now, get=_get, cache=None):
    """Closed 1h bars [(open_ts, open, close)], settled funding {ts: rate}, hourly quote volume and the open of every
    bar that has started {open_ts: open} (the in-progress bar's open is final; amendment 9 section 2 prices funding at
    the open of the bar starting at the settlement). With a cache, fetched once per clock hour, as soon as the bar
    that closed at the top of the hour is published (nothing here can change before the next close)."""
    hour = int(now) // HOUR * HOUR
    hit = cache.get(sym) if cache is not None else None
    if hit and hit[0] == hour:
        return hit[1:]
    kl = get(f"/fapi/v1/klines?symbol={sym}&interval=1h&limit=1000")
    bars = [(int(k[0]) // 1000, float(k[1]), float(k[4])) for k in kl if int(k[6]) // 1000 < now]
    volume = {int(k[0]) // 1000: float(k[7]) for k in kl if int(k[6]) // 1000 < now and len(k) > 7}
    opens = {int(k[0]) // 1000: float(k[1]) for k in kl if int(k[0]) // 1000 <= now}
    fr = get(f"/fapi/v1/fundingRate?symbol={sym}&limit=200")
    funding = {int(f["fundingTime"]) // 1000 // HOUR * HOUR: float(f["fundingRate"]) for f in fr
               if int(f["fundingTime"]) // 1000 < now}
    if cache is not None and bars and bars[-1][0] + HOUR == hour:     # the latest closed bar is in
        cache[sym] = (hour, bars, funding, volume, opens)
    return bars, funding, volume, opens


def fetch_market(sym, now, get=_get, cache=None, books=None, opens=None):
    """Closed 1h bars [(open_ts, open, close)], settled funding {ts: rate}, a Book and hourly quote volume (bars and
    funding through `hourly`, the book on every call). opens: if given, receives {sym: bar opens}."""
    bars, funding, volume, op = hourly(sym, now, get, cache)
    if opens is not None:
        opens[sym] = op
    book = books.get(sym) if books is not None else None
    if book is None:                                   # one book per symbol per pass for every ledger
        book = fetch_book(sym, now, get)
        if books is not None:
            books[sym] = book
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


def forward_experiments(db):
    from lab.paper import FORWARD_ACCOUNTS, forward_active
    return [e for e in FORWARD_ACCOUNTS if forward_active(db, e)]


def shadow_experiments(db):
    from lab.paper import shadow_active
    return [x["exp_id"] for x in registry.status(db) if x["state"] == "OBSERVATION" and shadow_active(db, x["exp_id"])]


def paper_experiments(db):
    return [x["exp_id"] for x in registry.status(db) if x["state"] == "PAPER_TRADING" and x["exp_id"].startswith("E_")]


def closing_ledgers(db):
    """Ledgers that still hold positions but may no longer trade: approved paper strategies that were rejected or
    retired, and shadow ledgers whose shadow ended. Amendment 4: their positions are closed, never forgotten."""
    from lab import lane
    from lab.paper import PaperEngine, forward_active, shadow_active
    eng, out = PaperEngine(db), []
    for r in db.q("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started'"):
        led = r[0]
        if led.startswith("SHADOW_"):
            base = led[len("SHADOW_"):]
            done = not shadow_active(db, base)
        elif led.startswith("FWD_"):                    # amendment 7: closed when the forward test is stopped
            base = led[len("FWD_"):]
            done = not forward_active(db, base)
        elif led.startswith(lane.PREFIX):              # amendment 11: closed when the lane account retires
            base = led
            done = not lane.is_active(db, led)
        else:
            base = led
            done = lifecycle.state(db, base) in ("REJECTED", "RETIRED")
        if done and eng.ledger(led)["positions"]:
            out.append((led, base))
    return out


def funding_start(db, now):
    """T_F (amendment 9 section 2): written once, by the first pass that books funding; settlements after it count."""
    from lab.paper import funding_t0
    t = funding_t0(db)
    if t is None:
        t = int(now)
        db.event("paper.funding_started", "agent:paper-1", None,
                 {"t_f": t, "rule": "research/PROTOCOL_V3.md amendment 9 section 2: settled funding of open positions "
                                    "is booked in every simulated paper ledger from T_F", "simulated": True})
    return t


def book_funding(db, eng, led, now, data):
    """Book the ledger's settled funding after T_F. data(symbols) -> {sym: (funding, opens)}; only symbols that can
    owe or receive a settlement are asked for (so an idle ledger causes no fetch)."""
    t_f = funding_start(db, now)
    due = eng.funding_due(led, t_f)
    return eng.book_funding(led, data(due), t_f) if due else []


def _cached_funding(get, now, cache):
    """Funding data for ledgers outside run_one (paused, closing): through the shared hourly cache only, so bars and
    funding are still read at most once per hour per symbol for all ledgers (amendment 7 section 7)."""
    def data(syms):
        out = {}
        for s in syms:
            if s.endswith(SPOT_SUFFIX):                 # a spot leg has no funding (amendment 11 point 4)
                out[s] = ({}, {})
                continue
            if s.startswith(HL_PREFIX):                 # amendment 13: Hyperliquid funding, hourly
                out[s] = hl_hourly(s[len(HL_PREFIX):], now)
                continue
            _, funding, _, opens = hourly(s, now, get, cache)
            out[s] = (funding, opens)
        return out
    return data


def _funding_guarded(db, eng, led, get, now, cache):
    try:
        return len(book_funding(db, eng, led, now, _cached_funding(get, now, cache)))
    except Exception as e:                              # no funding data this pass: the next pass books it
        return f"funding unavailable: {e!r}"[:120]


def close_ledger(db, led, base, get, now, books=None, cache=None):
    """Reduce-only close of a ledger that may no longer trade. One close order per symbol per hour, each walking a
    book read just before it. Funding of the held positions is still booked (amendment 9 section 2), with bars and
    funding only through the shared hourly cache (amendment 7 section 7). Marked once an hour."""
    eng, hour = PaperEngine(db, lambda: now), int(now) // HOUR * HOUR
    funding = _funding_guarded(db, eng, led, get, now, cache)
    orders = []
    for s, q in eng.ledger(led)["positions"].items():
        oid = f"{led}|close|{hour}|{s}"
        if eng._existing(oid):
            continue                                    # sent this hour; an unfilled rest is retried next hour
        try:
            book = fetch_book(s, now, get)
        except Exception as e:
            orders.append({"symbol": s, "status": f"book unavailable: {e!r}"[:80]})
            continue
        if books is not None:
            books[s] = book
        r = eng.submit_taker(led, oid, s, "sell" if q > 0 else "buy", abs(q), book, reduce_only=True,
                             signal_ref="close: strategy ended")
        orders.append({"symbol": s, "status": r["status"]})
    if orders:
        db.event("paper.closing", "agent:paper-1", led, {"orders": orders, "simulated": True})
    try:
        marked = _mark_hourly(db, eng, led, get, now, books)
    except Exception:
        marked = False                                  # no mark price this pass; the next pass tries again
    return {"status": "closing", "orders": orders, "marked": marked, "funding": funding}


def held_experiments(db):
    """Approved paper strategies that a circuit breaker paused: they keep their positions (amendment 4 section 7)."""
    return [x["exp_id"] for x in registry.status(db) if x["state"] == "PAUSED" and x["exp_id"].startswith("E_")
            and db.one("SELECT 1 FROM events WHERE kind='paper.started' AND exp_id=?", x["exp_id"])]


def _mark_hourly(db, eng, ledger, get, now, books=None):
    """Mark a ledger's positions once per clock hour at book mids (one shared book per symbol per pass)."""
    if db.one("SELECT 1 FROM sim_equity WHERE exp_id=? AND ts>=?", ledger, int(now) // HOUR * HOUR):
        return False
    marks = {}
    for s in eng.ledger(ledger)["positions"]:
        book = books.get(s) if books is not None else None
        if book is None:
            book = fetch_book(s, now, get)
            if books is not None:
                books[s] = book
        marks[s] = book.mid()
    eng.mark(ledger, marks)
    return True


def mark_only(db, ledger, get, now, books=None, cache=None):
    """Amendment 4 section 7: under a pause nothing new is opened; the positions are kept and marked once an hour.
    Their settled funding is still booked (amendment 9 section 2), with data only through the shared hourly cache."""
    eng = PaperEngine(db, lambda: now)
    funding = _funding_guarded(db, eng, ledger, get, now, cache)
    try:
        marked = _mark_hourly(db, eng, ledger, get, now, books)
    except Exception as e:
        return {"status": "paused", "marked": False, "reason": f"no mark prices: {e!r}"[:200], "funding": funding}
    return {"status": "paused", "marked": marked, "positions": len(eng.ledger(ledger)["positions"]),
            "funding": funding}


def _guarded(db, ledger, fn):
    """One ledger's failure never stops the others (closing in particular); it is reported, not swallowed."""
    try:
        return fn()
    except Exception as e:
        last = db.one("SELECT payload FROM events WHERE kind='paper.error' AND exp_id=? ORDER BY id DESC LIMIT 1", ledger)
        if last is None or json.loads(last[0]).get("error") != repr(e)[:300]:     # a new or changed error, once
            db.event("paper.error", "agent:paper-1", ledger, {"error": repr(e)[:300]})
        return {"status": "error", "reason": repr(e)[:200]}


def run(db, get=_get, now=None, cm_get=_cm_get, cache=None, cm_cache=None):
    from lab import promotion
    if cache is None and get is _get:                  # live: one shared hourly cache for every ledger
        cache = _HOURLY
    if cm_cache is None and cm_get is _cm_get:
        cm_cache = _CM_HOURLY
    books = {}
    now = now or time.time()
    out = {}
    for led, base in closing_ledgers(db):              # reduce-only: allowed even without a supervisor or FAIL_CLOSED
        out[led] = _guarded(db, led, lambda: close_ledger(db, led, base, get, now, books, cache))
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
        out[eid] = _guarded(db, eid, lambda: run_one(db, eid, get, now, cm_get=cm_get, cache=cache,
                                                     cm_cache=cm_cache, books=books))
    for eid in held_experiments(db):                   # paused: positions kept and marked, nothing new
        if eid not in out:                             # (not one a breaker paused in this very pass)
            out[eid] = _guarded(db, eid, lambda: mark_only(db, eid, get, now, books, cache))
    for eid in shadow_experiments(db):                 # amendment 3: simulated, separate ledger, no effect on tests
        out["SHADOW_" + eid] = _guarded(db, "SHADOW_" + eid,
                                        lambda: run_one(db, eid, get, now, ledger="SHADOW_" + eid, cm_get=cm_get,
                                                        cache=cache, cm_cache=cm_cache, books=books))
    for eid in forward_experiments(db):                # amendment 7: forward paper tests, separate ledgers
        out["FWD_" + eid] = _guarded(db, "FWD_" + eid,
                                     lambda: run_one(db, eid, get, now, ledger="FWD_" + eid, cm_get=cm_get,
                                                     cache=cache, cm_cache=cm_cache, books=books))
    from lab import lane                               # amendment 11: lane accounts start and retire by fixed rules
    managed = _guarded(db, "LANE", lambda: lane.manage(db, now, get))
    for led in lane.active(db):
        out[led] = _guarded(db, led, lambda: lane.run_one(db, led, get, now, cache, books))
    return {"experiments": len(out), "results": out, "simulated": True, "lane": managed}


def run_one(db, eid, get, now, ledger=None, cm_get=_cm_get, cache=None, cm_cache=None, books=None):
    """Trade experiment `eid`'s frozen strategy on the simulated ledger `ledger` (default: the experiment itself)."""
    L = ledger or eid
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    spec = json.loads(registry.latest(db, eid)["spec_json"])
    if spec.get("family"):          # amendment 8 point 16: no live spot feed exists yet (a later amendment); no orders
        if not db.one("SELECT 1 FROM events WHERE kind='paper.unsupported' AND exp_id=?", L):
            db.event("paper.unsupported", "agent:paper-1", L, {"reason": "amendment 8 family instance: simulated "
                                                                          "trading needs a live spot feed (point 16)"})
        return {"status": "unsupported", "reason": "live data for this family instance is not implemented; no orders"}
    tpl = catalogue.TEMPLATES[spec["template"]]
    if set(tpl.get("needs") or []) & {"metrics", "dvol", "stable", "taker", "rates"}:
        if not db.one("SELECT 1 FROM events WHERE kind='paper.unsupported' AND exp_id=?", L):
            db.event("paper.unsupported", "agent:paper-1", L, {"reason": "live inputs for this template are not "
                                                                          "built yet (research/PROTOCOL_V3.md section 7)"})
        return {"status": "unsupported", "reason": "live data for this template is not implemented; no orders"}
    eng.start(L, CAPITAL, cost_model(), actor="agent:paper-1")
    if risk.fail_closed():
        return {"status": "fail_closed"}
    if risk.paused(L):
        return mark_only(db, L, get, now, books, cache)   # amendment 4 section 7: kept and marked, nothing new
    try:
        variant = pipeline.frozen_variant(db, eid)                    # fail closed: no orders on unverified rules
    except pipeline.ArtifactError as e:
        if not db.one("SELECT 1 FROM events WHERE kind='paper.blocked' AND exp_id=? AND payload LIKE ?", L,
                      f"%{str(e)[:60]}%"):
            db.event("paper.blocked", "agent:paper-1", L, {"reason": str(e), "orders": "none"})
        return {"status": "blocked", "reason": str(e)}
    hour = int(now) // HOUR * HOUR
    market, opens = {}, {}
    try:
        for s in catalogue.universe(spec["template"]):
            market[s] = fetch_market(s, now, get, cache, books, opens)
    except Exception as e:
        risk.pause(L, "data_fetch", None, None, f"public market data fetch failed: {e!r}"[:300], eng.cancel_entries)
        return {"status": "paused", "reason": "data fetch failed"}
    bundle = None
    if "cm" in (tpl.get("needs") or []):
        try:
            key, hour_now = (tuple(tpl["cm_metrics"]), tuple(sorted(market))), int(now) // HOUR * HOUR
            hit = cm_cache.get(key) if cm_cache is not None else None
            if hit and hit[0] == hour_now:
                cmv = hit[1]
            else:
                cmv = fetch_cm_live(tpl["cm_metrics"], list(market), now, cm_get)
                if cm_cache is not None:
                    cm_cache[key] = (hour_now, cmv)
            bundle = {"cm": cmv}
        except Exception as e:
            risk.pause(L, "data_fetch", None, None, f"CoinMetrics fetch failed: {e!r}"[:300], eng.cancel_entries)
            return {"status": "paused", "reason": "CoinMetrics fetch failed"}
    for s, (bars, _, book, _) in market.items():
        if not bars or now - (bars[-1][0] + HOUR) > MAX_BAR_AGE or book.crossed():
            risk.pause(L, "data_stale", None, MAX_BAR_AGE, f"{s}: stale bars or invalid book", eng.cancel_entries)
            return {"status": "paused", "reason": f"{s} data stale or invalid"}
        risk.observe_book(L, book)
    fetch_more = _cached_funding(get, now, cache)       # a held symbol outside the universe (none today)
    funded = book_funding(db, eng, L, now, lambda syms: {**fetch_more([s for s in syms if s not in market]),
                                                         **{s: (market[s][1], opens[s]) for s in syms if s in market}})
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
        try:
            book = fetch_book(s, now, get)                # the order walks a book read just now
        except Exception as e:
            orders.append({"symbol": s, "status": f"not sent: book unavailable ({e!r})"[:120], "qty": abs(delta)})
            continue                                    # same order id: the next pass this hour retries it
        if book.crossed() or not book.bids or not book.asks:
            orders.append({"symbol": s, "status": "not sent: invalid book", "qty": abs(delta)})
            continue
        r = eng.submit_taker(L, f"{L}|{hour}|{s}", s, "buy" if delta > 0 else "sell", abs(delta), book,
                             reduce_only=reduce_only, signal_ref=f"{spec['template']}@{hour}")
        orders.append({"symbol": s, "status": r["status"], "qty": abs(delta)})
    if not db.one("SELECT 1 FROM sim_equity WHERE exp_id=? AND ts>=?", L, hour):
        eng.mark(L, marks)
    rec = eng.reconcile(L)
    if not rec["ok"]:
        risk.trip_fail_closed("reconciliation", f"{L}: {rec['problems']}"[:500])
    return {"status": "ok", "orders": orders, "pnl": eng.pnl(L, marks), "reconciled": rec["ok"], "funding": len(funded)}

