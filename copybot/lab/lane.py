"""Lane accounts (research/PROTOCOL_V3.md amendment 11). SIMULATION ONLY: no exchange, no keys, no real money.

The exploration lane's candidates (amendment 10 point 5) trade automatically on separate simulated ledgers
`LANE_<10 hex>` and retire automatically by fixed rules. Never evidence: no results, trials, transitions, approvals,
alpha rows or formal balance; a candidate becomes formal only through an amendment 8 family draft and the user.

- start (system:lane): at most SLOTS active, one per mechanism function, one new account per clock hour; both legs'
  public books must load for at least MIN_COINS coins;
- trade: the family's own function on the latest 1h perp bars and settled funding; +1 = long spot and short perp of the
  same quantity, sized at opening and held until the signal is 0 (no rebalancing); a partly filled leg is brought up
  to the other leg's quantity later;
- retire: family approval gone, MAX_AGE_S, loss >= LOSS_RETIRE of capital, paused for PAUSE_RETIRE_S, the source does
  not pay (funding - fees <= 0 after SOURCE_DAYS), edge missing (z <= Z_RETIRE after MIN_DAYS daily returns), or a
  human `lane-off`. Positions are then closed reduce-only.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import statistics
import time

from lab import explore, families, lifecycle, pipeline
from lab.paper import CostModel, PaperEngine
from lab.risk import Risk

PREFIX = "LANE_"
ACTOR = "system:lane"
LABEL = "BANEKONTO (udforskning, simuleret, aldrig bevis)"
POLICY = "lane.policy"
SPOT = ".SPOT"                                  # instrument suffix of the spot leg (book from the spot API)
MODEL = "spot_perp_ratio"                       # point 2: the only instrument model with a live feed here
CAPITAL = 10_000.0
SLOTS = 3
START_EVERY = 3600
PROBES = 3                                      # candidates probed per pass at most (each probe reads 2 books a coin)
MIN_COINS = explore.MIN_COINS
COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.0004)   # point 4, per leg
UNIT_CAPITAL = 2                                # point 6: capital_per_unit_notional (both legs)
MIN_NOTIONAL = 10.0
HOUR, DAY = 3600, 86400
MIN_DAYS, Z_RETIRE = 7, -3.0
LOSS_RETIRE = 0.03
PAUSE_RETIRE_S = DAY
MAX_AGE_S = 90 * DAY
PROMISING_DAYS, PROMISING_Z = 30, -1.0
SOURCE_DAYS = 14                                # point 5: funding booked - fees paid must be > 0 by then
# amendment 12: scanner accounts (source "scanner"): one coin, the scanner's perp premium decides in and out
SCAN_LABEL = "SCANNERKONTO (scannerfund, simuleret, aldrig bevis)"
SCAN_SLOTS = 5
SCAN_MIN, SCAN_BIG = 0.005, 0.01                # in: >= 1 % in the latest scan, or >= 0.5 % in the two latest
SCAN_STALE_S = 3 * HOUR                         # an older latest scan: nothing new opens, a position is held
SCAN_COOLDOWN_S = DAY
SCAN_LOSS = 0.05
SCAN_SOURCE_S = 3 * DAY
SCAN_FLAT_S = 2 * DAY
SCAN_MAX_AGE_S = 30 * DAY
_CANDIDATES = {}                                # (registry, last research.explore id, families) -> candidates


def is_scanner(info):
    return (info or {}).get("source") == "scanner"


def label(info):
    return SCAN_LABEL if is_scanner(info) else LABEL


def rules_text(info):
    """The automatic stop rules, in Danish, for the dashboard."""
    if is_scanner(info):
        return (f"ind ved præmie ≥ {SCAN_BIG:.0%} eller ≥ {SCAN_MIN:.1%} i to scanninger, ud når den er væk i to; "
                f"stoppes ved tab ≥ {SCAN_LOSS:.0%}, 24 t pause, funding − gebyrer ≤ 0 efter {SCAN_SOURCE_S // DAY} "
                f"dage, {SCAN_FLAT_S // DAY} døgn uden position eller {SCAN_MAX_AGE_S // DAY} dage")
    return (f"stoppes ved funding − gebyrer ≤ 0 efter {SOURCE_DAYS} dage, tab ≥ {LOSS_RETIRE:.0%}, 24 t pause, "
            f"z ≤ {Z_RETIRE:g} eller {MAX_AGE_S // DAY} dage")


def ledger_id(key):
    return PREFIX + hashlib.sha256(key.encode()).hexdigest()[:10]


def _events(db, kind):
    return [(r["id"], r["ts"], r["actor"], r["exp_id"], json.loads(r["payload"] or "{}"))
            for r in db.q("SELECT id, ts, actor, exp_id, payload FROM events WHERE kind=? ORDER BY id", kind)]


# ---------- policy (point 5, last rule) ----------
def policy_on(db):
    """On unless a human switched it off (the latest lane.policy by a human decides)."""
    r = db.one("SELECT actor, payload FROM events WHERE kind=? AND actor LIKE 'human:%' ORDER BY id DESC LIMIT 1",
               POLICY)
    return r is None or bool(json.loads(r["payload"] or "{}").get("on"))


def set_policy(db, on, actor, reason):
    if not actor.startswith("human:"):
        raise lifecycle.LifecycleError("only a human can switch the lane accounts on or off")
    if not reason or len(reason.strip()) < 10:
        raise lifecycle.LifecycleError("a reason of at least 10 characters is required")
    db.event(POLICY, actor, None, {"on": bool(on), "reason": reason.strip()[:300], "simulated": True})
    return on


# ---------- state ----------
def started(db):
    """{ledger: lane.started payload}; ts is the runner's clock at the start (payload t), else the event time."""
    return {e: {**p, "ts": p.get("t", ts)} for _, ts, _, e, p in _events(db, "lane.started")}


def retired(db):
    return {e: {**p, "ts": p.get("t", ts)} for _, ts, _, e, p in _events(db, "lane.retired")}


def active(db):
    gone = retired(db)
    return sorted(e for e in started(db) if e not in gone)


def is_active(db, ledger):
    if not ledger.startswith(PREFIX):
        return False
    r = db.one("SELECT kind FROM events WHERE kind IN ('lane.started','lane.retired') AND exp_id=? "
               "ORDER BY id DESC LIMIT 1", ledger)
    return bool(r and r["kind"] == "lane.started")


def tried_keys(db):
    return {p.get("key") for _, _, _, _, p in _events(db, "lane.started") + _events(db, "lane.skipped")}


# ---------- candidates (point 2) ----------
def _model_ok(fid):
    try:
        return families.load(fid).get("instrument_model", {}).get("type") == MODEL
    except OSError:                                              # no family file: nothing to trade
        return False


def candidates(db, fids):
    """Lane results that meet all three amendment 10 point 5 checks, from artifacts whose SHA-256 a research.explore
    event recorded, for the given families with the spot_perp_ratio model. Best net Sharpe first (ties by key)."""
    fids = {f for f in fids if _model_ok(f)}
    ev = _events(db, "research.explore")
    memo = (db.path, ev[-1][0] if ev else None, tuple(sorted(fids)))     # artifacts change only with a new event
    if memo in _CANDIDATES:
        return list(_CANDIDATES[memo])
    known = {p.get("artifact_sha256") for _, _, _, _, p in ev}
    root, out = os.path.join(pipeline.ARTIFACTS, explore.DIR), {}
    for day in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        d = os.path.join(root, day)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), "rb") as fh:
                raw = fh.read()
            sha = hashlib.sha256(raw).hexdigest()
            if sha not in known:
                continue                                         # not a recorded lane artifact: never traded
            art = json.loads(raw)
            for r in art.get("results") or []:
                if r.get("candidate") and r.get("family") in fids and all((r.get("checks") or {}).values()):
                    out[r["key"]] = {**r, "artifact": os.path.relpath(os.path.join(d, f), pipeline.HERE)
                                     .replace("\\", "/"), "artifact_sha256": sha,
                                     "evaluated_coins": r.get("coins") or art.get("coins") or None}
    res = sorted(out.values(), key=lambda r: (-(r.get("net_sharpe_ann") or 0), r["key"]))
    _CANDIDATES.clear()
    _CANDIDATES[memo] = res
    return list(res)


def expectation(r):
    """Point 6: daily mean and sd at 2x costs on capital (the backtest is per unit of one leg: divide by 2)."""
    sr, days, total = r.get("net_sharpe_ann"), r.get("days"), r.get("net_total")
    if not sr or sr <= 0 or not days or total is None:
        return None
    m = total / days
    return {"mean": m / UNIT_CAPITAL, "sd": m * math.sqrt(365) / sr / UNIT_CAPITAL, "days": days,
            "source": "explore0 result at 2x costs (amendment 11 point 6)"}


# ---------- live statistics (points 5-7) ----------
def daily_returns(db, ledger, now):
    """Returns between consecutive finished UTC days' last hourly marks (after costs, funding included)."""
    today, closes = int(now) // DAY * DAY, {}
    for x in db.q("SELECT ts, equity FROM sim_equity WHERE exp_id=? ORDER BY id", ledger):
        if x["ts"] < today:
            closes[x["ts"] // DAY] = x["equity"]
    days = sorted(closes)
    return [closes[b] / closes[a] - 1 for a, b in zip(days, days[1:]) if closes[a] > 0]


def stats(db, ledger, now=None, info=None):
    now = now or time.time()
    info = info or started(db).get(ledger) or {}
    rets, exp = daily_returns(db, ledger, now), info.get("expectation")
    n = len(rets)
    live = statistics.mean(rets) if n else None
    z = (live - exp["mean"]) / (exp["sd"] / math.sqrt(n)) if (n and exp and exp.get("sd")) else None
    last = db.one("SELECT equity FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", ledger)
    return {"days": n, "mean": live, "z": z, "expectation": exp, "equity": last["equity"] if last else None,
            "age_days": (now - info["ts"]) / DAY if info.get("ts") else None, "decisional": False}


def _paused_for(risk, ledger, now):
    p = risk._last(ledger, ("PAUSE",)) if risk.paused(ledger) else None
    return (now - p["ts"], p["rule"]) if p is not None else (None, None)


def _paid(db, ledger, now):
    try:
        return PaperEngine(db, lambda: now).ledger(ledger)
    except lifecycle.LifecycleError:                             # never ran (no paper.started): nothing paid
        return {"funding": 0.0, "fees": 0.0, "positions": {}}


def _scan_retire_reason(db, ledger, info, now):
    """Amendment 12 point 5."""
    st, risk = stats(db, ledger, now, info), Risk(db, lambda: now)
    if now - info["ts"] >= SCAN_MAX_AGE_S:
        return "expired", f"{SCAN_MAX_AGE_S // DAY} dage efter start", st
    if st["equity"] is not None and st["equity"] <= CAPITAL * (1 - SCAN_LOSS):
        return "loss", f"værdi {st['equity']:.2f} er mindst {SCAN_LOSS:.0%} under startkapitalen", st
    age, rule = _paused_for(risk, ledger, now)
    if age is not None and age >= PAUSE_RETIRE_S:
        return "paused", f"på pause i {age / HOUR:.0f} timer ({rule})", st
    led = _paid(db, ledger, now)
    if now - info["ts"] >= SCAN_SOURCE_S:
        st["funding_minus_fees"] = led["funding"] - led["fees"]
        if st["funding_minus_fees"] <= 0:
            return "source", (f"kilden betaler ikke: funding {led['funding']:.2f} − gebyrer {led['fees']:.2f} ≤ 0 "
                              f"efter {SCAN_SOURCE_S // DAY} dage"), st
    if not led["positions"]:
        last = db.one("SELECT MAX(ts) FROM sim_fills WHERE exp_id=?", ledger)[0]
        since = max(info["ts"], last or 0)
        if now - since >= SCAN_FLAT_S:
            return "flat", f"ingen position i {SCAN_FLAT_S // DAY} døgn: præmien er væk", st
    return None, None, st


def _tested_coins(info):
    """The coins the variant was evaluated on, from its recorded artifact (hash-checked); None if unreadable."""
    if info.get("evaluated_coins"):
        return info["evaluated_coins"]
    try:
        with open(os.path.join(pipeline.HERE, info["artifact"]), "rb") as fh:
            raw = fh.read()
    except (OSError, KeyError, TypeError):
        return None
    if hashlib.sha256(raw).hexdigest() != info.get("artifact_sha256"):
        return None
    art = json.loads(raw)
    r = next((x for x in art.get("results") or [] if x.get("key") == info.get("key")), {})
    return r.get("coins") or art.get("coins")


def _retire_reason(db, ledger, info, now, fids):
    if is_scanner(info):
        return _scan_retire_reason(db, ledger, info, now)
    st, risk = stats(db, ledger, now, info), Risk(db, lambda: now)
    tested = _tested_coins(info)
    extra = sorted(set(info.get("coins") or []) - set(tested or []))
    if tested is not None and extra:                             # started before the basket fix (amendment 11)
        return "basket", f"handler {len(extra)} mønter, varianten ikke blev testet på ({', '.join(extra[:5])} ...)", st
    if info.get("family") not in fids:
        return "family", "familiens godkendelse er ikke længere gyldig", st
    if now - info["ts"] >= MAX_AGE_S:
        return "expired", f"{MAX_AGE_S // DAY} dage efter start", st
    if st["equity"] is not None and st["equity"] <= CAPITAL * (1 - LOSS_RETIRE):
        return "loss", f"værdi {st['equity']:.2f} er mindst {LOSS_RETIRE:.0%} under startkapitalen", st
    if risk.paused(ledger):
        p = risk._last(ledger, ("PAUSE",))
        if p is not None and now - p["ts"] >= PAUSE_RETIRE_S:
            return "paused", f"på pause siden {p['ts']} ({p['rule']})", st
    if now - info["ts"] >= SOURCE_DAYS * DAY:
        try:
            led = PaperEngine(db, lambda: now).ledger(ledger)
        except lifecycle.LifecycleError:                         # never ran (no paper.started): nothing paid
            led = {"funding": 0.0, "fees": 0.0}
        st["funding_minus_fees"] = led["funding"] - led["fees"]
        if st["funding_minus_fees"] <= 0:
            return "source", (f"kilden betaler ikke: funding {led['funding']:.2f} − gebyrer {led['fees']:.2f} ≤ 0 "
                              f"efter {SOURCE_DAYS} dage"), st
    if st["days"] >= MIN_DAYS and st["z"] is not None and st["z"] <= Z_RETIRE:
        return "edge", f"z = {st['z']:.2f} <= {Z_RETIRE} efter {st['days']} dage", st
    return None, None, st


def retire(db, ledger, rule, detail, st=None, now=None):
    db.event("lane.retired", ACTOR, ledger, {"rule": rule, "detail": detail, "stats": st, "simulated": True,
                                             "decisional": False, "label": LABEL, "t": int(now or time.time())})


# ---------- start (point 3) ----------
def _probe(r, fam, get, now):
    """Coins whose perp and spot books both load (one read each), in basket order."""
    from lab import paper_runner
    ok, dropped = [], []
    for s in r.get("evaluated_coins") or r.get("coins") or explore.universe(fam):   # the coins it was tested on
        try:
            for inst in (s, s + SPOT):
                b = paper_runner.fetch_book(inst, now, get)
                if b.crossed():
                    raise ValueError("crossed or empty book")
            ok.append(s)
        except Exception as e:
            dropped.append({"coin": s, "reason": repr(e)[:120]})
    return ok, dropped


def _start(db, r, get, now):
    led, fam = ledger_id(r["key"]), families.load(r["family"])
    coins, dropped = _probe(r, fam, get, now)
    base = {k: r.get(k) for k in ("key", "family", "function", "params", "net_sharpe_ann", "artifact",
                                  "artifact_sha256", "evaluated_coins")} | {"basket": r.get("coins"),
                                                                            "dropped": dropped}
    if len(coins) < MIN_COINS:
        db.event("lane.skipped", ACTOR, led, {**base, "coins": coins, "reason": f"{len(coins)} coins with both live "
                                              f"books, fewer than {MIN_COINS}", "simulated": True})
        return None
    db.event("lane.started", ACTOR, led, {**base, "coins": coins, "expectation": expectation(r), "capital": CAPITAL,
                                          "t": int(now),
                                          "costs": COSTS.__dict__, "label": LABEL, "simulated": True,
                                          "decisional": False, "rule": "research/PROTOCOL_V3.md amendment 11"})
    return led


def manage(db, now=None, get=None, fids=None):
    """Retire what a rule stops, then start at most one account (point 3). Returns what it did."""
    now = now or time.time()
    fids = set(explore.eligible(db) if fids is None else fids)
    info, out = started(db), {"retired": [], "started": None, "skipped": [], "promising": []}
    on = policy_on(db)
    for led in active(db):
        if not on:
            retire(db, led, "human", "brugeren slog banekontiene fra (lane-off)", stats(db, led, now, info[led]), now)
            out["retired"].append(led)
            continue
        rule, detail, st = _retire_reason(db, led, info[led], now, fids)
        if rule:
            retire(db, led, rule, detail, st, now)
            out["retired"].append(led)
        elif (not is_scanner(info[led]) and st["days"] >= PROMISING_DAYS and st["mean"] is not None and st["mean"] > 0 and st["z"] is not None
              and st["z"] > PROMISING_Z and not db.one("SELECT 1 FROM events WHERE kind='lane.promising' AND "
                                                       "exp_id=?", led)):
            db.event("lane.promising", ACTOR, led, {"stats": st, "decisional": False, "label": LABEL,
                                                    "next": "an amendment 8 family draft for the user's approval"})
            out["promising"].append(led)
    if not on or get is None or Risk(db, lambda: now).fail_closed():
        return out
    out["scanner"] = manage_scanner(db, now, get)
    info = started(db)
    act = [a for a in active(db) if not is_scanner(info[a])]
    last = max((i["ts"] for i in info.values() if not is_scanner(i)), default=None)
    if len(act) >= SLOTS or (last is not None and now - last < START_EVERY):
        return out
    busy, done = {(info[a]["family"], info[a]["function"]) for a in act}, tried_keys(db)
    probes = 0
    for r in candidates(db, fids):
        if r["key"] in done or (r["family"], r["function"]) in busy:
            continue
        if probes >= PROBES:
            break
        probes += 1
        led = _start(db, r, get, now)
        if led:
            out["started"] = led
            break
        out["skipped"].append(r["key"])
    return out


# ---------- scanner accounts (amendment 12) ----------
def scans(db, now, n=2):
    """The latest n scan times with a USD-M premium read (the scanner writes symbols_compared every such scan)."""
    return [r[0] for r in db.q("SELECT DISTINCT ts FROM observations WHERE metric='symbols_compared' AND "
                               "instrument='binance_perps' AND ts<=? ORDER BY ts DESC LIMIT ?", int(now), n)]


def premiums(db, ts):
    """{symbol: premium} of the positive premiums the scanner flagged at scan time ts."""
    return {r["instrument"]: r["value"] for r in db.q("SELECT instrument, value FROM observations WHERE "
                                                      "metric='perp_premium' AND flagged=1 AND ts=? AND value>0", ts)}


def _last_two(db, now):
    ts = scans(db, now)
    return ts, [premiums(db, t) for t in ts]


def scan_entry(p_now, p_prev):
    return p_now is not None and p_now >= SCAN_MIN and (p_now >= SCAN_BIG or (p_prev or 0) >= SCAN_MIN)


def scan_signal(db, coin, holding, now):
    """Point 2-3: in on the entry rule; out when neither of the two latest scans flags a positive premium; with no scan
    in SCAN_STALE_S nothing new opens and a position is held."""
    ts, ps = _last_two(db, now)
    if not ts or now - ts[0] > SCAN_STALE_S:
        return 1.0 if holding else 0.0
    vals = [p.get(coin) for p in ps] + [None]
    if holding:
        return 1.0 if any(v is not None and v > 0 for v in vals[:2]) else 0.0
    return 1.0 if scan_entry(vals[0], vals[1]) else 0.0


def scan_candidates(db, now):
    """Coins meeting the entry rule now, largest latest premium first."""
    ts, ps = _last_two(db, now)
    if not ts or now - ts[0] > SCAN_STALE_S:
        return []
    prev = ps[1] if len(ps) > 1 else {}
    return sorted((c for c, v in ps[0].items() if scan_entry(v, prev.get(c))), key=lambda c: (-ps[0][c], c))


def _cooling(db, coin, now):
    """Point 4: a coin gets a new account SCAN_COOLDOWN_S after its last one stopped or was skipped."""
    info = started(db)
    for kind in ("lane.retired", "lane.skipped"):
        for _, ts, _, led, p in _events(db, kind):
            i = p if kind == "lane.skipped" else info.get(led, {})
            if is_scanner(i) and coin in (i.get("coins") or []) and now - p.get("t", ts) < SCAN_COOLDOWN_S:
                return True
    return False


def manage_scanner(db, now, get):
    """Start scanner accounts for every coin that meets the entry rule, up to SCAN_SLOTS (point 4)."""
    from lab import paper_runner
    info = started(db)
    held = {info[a]["coins"][0] for a in active(db) if is_scanner(info[a])}
    out, probes = {"started": [], "skipped": []}, 0
    ts, ps = _last_two(db, now)
    for coin in scan_candidates(db, now):
        if len(held) >= SCAN_SLOTS or probes >= PROBES:
            break
        if coin in held or _cooling(db, coin, now):
            continue
        probes += 1
        key, hour = f"scan|{coin}|{int(now) // HOUR * HOUR}", int(now) // HOUR * HOUR
        led = ledger_id(key)
        trigger = {"scan_ts": ts[:2], "premium": [p.get(coin) for p in ps], "rule": "research/PROTOCOL_V3.md "
                   "amendment 12 point 2"}
        base = {"key": key, "source": "scanner", "family": "fcarry", "function": "scanner_premium", "params": {},
                "coin": coin, "trigger": trigger, "label": SCAN_LABEL, "simulated": True, "decisional": False,
                "t": int(now)}
        try:
            for inst in (coin, coin + SPOT):
                if paper_runner.fetch_book(inst, now, get).crossed():
                    raise ValueError("crossed or empty book")
        except Exception as e:
            db.event("lane.skipped", ACTOR, led, {**base, "coins": [coin], "reason": f"book unavailable: {e!r}"[:160]})
            out["skipped"].append(coin)
            continue
        db.event("lane.started", ACTOR, led, {**base, "coins": [coin], "expectation": None, "capital": CAPITAL,
                                              "costs": COSTS.__dict__, "hour": hour,
                                              "rule": "research/PROTOCOL_V3.md amendment 12"})
        held.add(coin)
        out["started"].append(led)
    return out


# ---------- trading (point 4) ----------
def _signal(info, market):
    """The family function's position for the hour that is starting, per coin (0 or +1)."""
    mod = importlib.import_module(f"lab.families.{info['family']}")
    nxt = {s: b + [(b[-1][0] + HOUR, b[-1][2], b[-1][2])] for s, (b, _) in market.items()}   # prices unused
    fund = {s: {t: -r for t, r in f.items()} for s, (_, f) in market.items()}   # cost convention (fcarry.py)
    pos = getattr(mod, info["function"])(nxt, fund, info["params"], None)
    return {s: (pos.get(s) or [0.0])[-1] for s in market}


def run_one(db, ledger, get, now, cache=None, books=None):
    from lab import paper_runner as pr
    info = started(db)[ledger]
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    eng.start(ledger, CAPITAL, COSTS, actor=ACTOR)
    if risk.fail_closed():
        return {"status": "fail_closed"}
    if risk.paused(ledger):
        return pr.mark_only(db, ledger, get, now, books, cache)
    hour, market, opens = int(now) // HOUR * HOUR, {}, {}
    try:
        for s in info["coins"]:
            bars, funding, _, op = pr.hourly(s, now, get, cache)
            market[s], opens[s] = (bars, funding), op
    except Exception as e:
        risk.pause(ledger, "data_fetch", None, None, f"public market data fetch failed: {e!r}"[:300],
                   eng.cancel_entries)
        return {"status": "paused", "reason": "data fetch failed"}
    for s, (bars, _) in market.items():
        if not bars or now - (bars[-1][0] + HOUR) > pr.MAX_BAR_AGE:
            risk.pause(ledger, "data_stale", None, pr.MAX_BAR_AGE, f"{s}: stale bars", eng.cancel_entries)
            return {"status": "paused", "reason": f"{s} data stale"}
    funded = pr.book_funding(db, eng, ledger, now, lambda syms: {
        x: (market[x][1], opens[x]) if x in market else ({}, {}) for x in syms})     # the spot leg has no funding
    if is_scanner(info):                                 # amendment 12: the scanner's premium decides
        c = info["coins"][0]
        pos0 = eng.ledger(ledger)["positions"]
        want = {c: scan_signal(db, c, pos0.get(c + SPOT, 0.0) > 0 or pos0.get(c, 0.0) < 0, now)}
    else:
        want = _signal(info, market)
    pos = eng.ledger(ledger)["positions"]
    last = db.one("SELECT equity FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", ledger)
    size = (last["equity"] if last else CAPITAL) / (UNIT_CAPITAL * len(info["coins"]))
    orders = []
    for s in info["coins"]:
        sq, pq, px = pos.get(s + SPOT, 0.0), pos.get(s, 0.0), market[s][0][-1][2]
        q = max(sq, -pq, 0.0) if want[s] > 0 else 0.0
        fresh = want[s] > 0 and q == 0.0
        if not fresh and abs(sq - q) * px < MIN_NOTIONAL and abs(pq + q) * px < MIN_NOTIONAL:
            continue
        try:
            bk = {s: pr.fetch_book(s, now, get), s + SPOT: pr.fetch_book(s + SPOT, now, get)}
        except Exception as e:
            orders.append({"symbol": s, "status": f"not sent: book unavailable ({e!r})"[:120]})
            continue                                    # same order ids: the next pass this hour retries
        if any(b.crossed() for b in bk.values()):
            orders.append({"symbol": s, "status": "not sent: invalid book"})
            continue
        for inst, b in bk.items():
            risk.observe_book(ledger, b)
            if books is not None:
                books[inst] = b
        if fresh:
            q = size / bk[s].mid()
        for inst, target, cur in ((s + SPOT, q, sq), (s, -q, pq)):
            delta = target - cur
            if abs(delta) * bk[inst].mid() < MIN_NOTIONAL:
                continue
            reduce_only = abs(target) < abs(cur) and (target == 0 or (target > 0) == (cur > 0))
            r = eng.submit_taker(ledger, f"{ledger}|{hour}|{inst}", inst, "buy" if delta > 0 else "sell", abs(delta),
                                 bk[inst], reduce_only=reduce_only,
                                 signal_ref=f"{info['family']}.{info['function']}@{hour}")
            orders.append({"instrument": inst, "status": r["status"], "qty": abs(delta)})
    try:
        marked = pr._mark_hourly(db, eng, ledger, get, now, books)
    except Exception as e:
        marked = f"no mark prices: {e!r}"[:120]          # the next pass tries again
    rec = eng.reconcile(ledger)
    if not rec["ok"]:
        risk.trip_fail_closed("reconciliation", f"{ledger}: {rec['problems']}"[:500])
    return {"status": "ok", "orders": orders, "marked": marked, "reconciled": rec["ok"], "funding": len(funded),
            "signal": want}
