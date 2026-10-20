"""Lane accounts (research/PROTOCOL_V3.md amendment 11). SIMULATION ONLY: no exchange, no keys, no real money.

The exploration lane's candidates (amendment 10 point 5) trade automatically on separate simulated ledgers
`LANE_<10 hex>` and retire automatically by fixed rules. Never evidence: no results, trials, transitions, approvals,
alpha rows or formal balance; a candidate becomes formal only through an amendment 8 family draft and the user.

- start (system:lane): at most SLOTS active, PER_FUNCTION per mechanism function, one new account per START_EVERY
  (12b); both legs' public books must load for at least MIN_COINS coins;
- trade: the family's own function on the latest 1h perp bars and settled funding; +1 = long spot and short perp of the
  same quantity, sized at opening and held until the signal is 0 (no rebalancing); a partly filled leg is brought up
  to the other leg's quantity later;
- retire: family approval gone, MAX_AGE_S, loss >= LOSS_RETIRE of capital, paused for PAUSE_RETIRE_S, the source does
  not pay (funding - fees <= 0 after SOURCE_DAYS), edge missing (z <= Z_RETIRE after MIN_DAYS daily returns), or a
  human `lane-off`. Positions are then closed reduce-only.
"""
from __future__ import annotations

import collections
import hashlib
import importlib
import json
import math
import os
import statistics
import time

from lab import explore, families, jobs, lifecycle, pipeline
from lab.paper import CostModel, PaperEngine
from lab.risk import Risk

PREFIX = "LANE_"
ACTOR = "system:lane"
LABEL = "BANEKONTO (udforskning, simuleret, aldrig bevis)"
POLICY = "lane.policy"
SPOT = ".SPOT"                                  # instrument suffix of the spot leg (book from the spot API)
MODEL = "spot_perp_ratio"                       # point 2: the only instrument model with a live feed here
CAPITAL = 10_000.0
SLOTS = 6                                       # 12b
START_EVERY = 600                               # 12b: one new lane account per 10 minutes
PER_FUNCTION = 2                                # 12b: at most two active accounts per mechanism function
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
LANE_FLAT_S = 3 * DAY                           # 11b: a lane account without a position for 3 days retires
RETRY_S = DAY                                   # 11b: a variant that would hold nothing now may be tried a day later
# amendment 12: scanner accounts (source "scanner"): one coin, the scanner's perp premium decides in and out
SCAN_LABEL = "SCANNERKONTO (scannerfund, simuleret, aldrig bevis)"
SCAN_SLOTS = 10                                 # 12b
SCAN_FUND_MIN = 0.0005                          # 12f: predicted funding >= 0.05 % per 8 h to enter (was 0.10 %)
SCAN_FUND_PERSIST = 0.00025                     # 12f: mean of the last 3 settled rates >= 0.025 % (was 0.05 %)
SCAN_FUND_EXIT = 0.0001                         # 12f: out after two SETTLED rates in a row below the 0.01 % floor
SCAN_LIVE_MAX_S = 300                           # 12e: an in-memory reading older than this is not used
SCAN_SKIP_COOLDOWN_S = HOUR                     # 12e point 4: a skipped coin may be tried again after an hour
SCAN_STALE_S = 3 * HOUR                         # an older latest scan: nothing new opens, a position is held
SCAN_COOLDOWN_S = DAY
SCAN_LOSS = 0.05
SCAN_SOURCE_S = 3 * DAY
SCAN_FLAT_S = 2 * DAY
SCAN_MAX_AGE_S = 60 * DAY                       # 12f: winners hold for weeks (study median 58-89 settlements)
SCAN_HOLD_S = 12 * HOUR                         # 12c: without a booked settlement, a position may close after 12 h
# amendment 13: Hyperliquid funding accounts (source "hl"): long Binance spot, short Hyperliquid perp
HL_LABEL = "HL-KONTO (Hyperliquid-funding, simuleret, aldrig bevis)"
HL_PERP = "HL:"                                 # the perp leg's instrument prefix (paper_runner.HL_PREFIX)
HL_SLOTS = 10
HL_HOLD_S = 8 * HOUR                            # 13 point 5: out no earlier than 8 h after the entry
HL_PERSIST_HOURS = 24                           # 13 point 4: mean of the last 24 settled hours x 8 >= HL_FUND_PERSIST
HL_FUND_MIN = 0.001                             # 13a: predicted funding x 8 >= 0.10 % (2026 study: +0.51 %, 61 % won)
HL_FUND_PERSIST = 0.0005                        # 13a: the 24-hour mean x 8 >= 0.05 %
_CANDIDATES = {}                                # (registry, last research.explore id, families) -> candidates


def is_scanner(info):
    return (info or {}).get("source") == "scanner"


def is_hl(info):
    return (info or {}).get("source") == "hl"


def is_lane(info):
    """An account of the lane itself (amendment 11), not a scanner (12) or Hyperliquid (13) account."""
    return not (info or {}).get("source")


def label(info):
    return HL_LABEL if is_hl(info) else SCAN_LABEL if is_scanner(info) else LABEL


def rules_text(info):
    """The automatic stop rules, in Danish, for the dashboard."""
    if is_hl(info):
        return (f"ind ved Hyperliquid-funding ×8 ≥ {HL_FUND_MIN:.2%} og snit af {HL_PERSIST_HOURS} timer ×8 ≥ "
                f"{HL_FUND_PERSIST:.3%}; ud når to afregnede timer ×8 er < {SCAN_FUND_EXIT:.2%} og efter mindst "
                f"{HL_HOLD_S // HOUR} t; "
                f"stoppes ved tab ≥ {SCAN_LOSS:.0%}, 24 t pause, funding − gebyrer ≤ 0 efter {SCAN_SOURCE_S // DAY} "
                f"dage, {SCAN_FLAT_S // DAY} døgn uden position eller {SCAN_MAX_AGE_S // DAY} dage")
    if is_scanner(info):
        return (f"ind ved forventet funding ≥ {SCAN_FUND_MIN:.2%} og snit af 3 afregninger ≥ {SCAN_FUND_PERSIST:.3%}; "
                f"ud når to afregnede rater er < {SCAN_FUND_EXIT:.2%} og en afregning er bogført (højst "
                f"{SCAN_HOLD_S // HOUR} t); "
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


def tried_keys(db, now=None):
    """Keys never to start again: every started key and every skip, except an 11b skip ("would hold nothing now")
    whose RETRY_S has passed."""
    now = now or time.time()
    return {p.get("key") for _, _, _, _, p in _events(db, "lane.started")} | {
        p.get("key") for _, ts, _, _, p in _events(db, "lane.skipped")
        if not p.get("retry") or now - p.get("t", ts) < RETRY_S}


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
    if is_scanner(info) or is_hl(info):
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
    led_ = _paid(db, ledger, now)
    if not led_["positions"]:                                    # 11b: flat for LANE_FLAT_S frees the slot
        last = db.one("SELECT MAX(ts) FROM sim_fills WHERE exp_id=?", ledger)[0]
        if now - max(info["ts"], last or 0) >= LANE_FLAT_S:
            return "flat", f"ingen position i {LANE_FLAT_S // DAY} døgn", st
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


def _would_hold(r, coins, get, now):
    """11b: the coins in which the variant's own function holds +1 on the live data it would trade on, or [] (also
    when the data cannot be read)."""
    from lab import paper_runner as pr
    cache = pr._HOURLY if get is pr._get else None
    try:
        market = {}
        for s in coins:
            bars, funding, _, _ = pr.hourly(s, now, get, cache)
            market[s] = (bars, funding)
        want = _signal({"family": r["family"], "function": r["function"], "params": r["params"]}, market)
    except Exception:
        return []
    return [s for s, v in want.items() if v > 0]


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
    held = _would_hold(r, coins, get, now)                          # 11b: it must hold a coin on live data now
    if not held:
        db.event("lane.skipped", ACTOR, led, {**base, "coins": coins, "reason": "would hold nothing now (11b)",
                                              "retry": True, "t": int(now), "simulated": True})
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
        elif (is_lane(info[led]) and st["days"] >= PROMISING_DAYS and st["mean"] is not None and st["mean"] > 0 and st["z"] is not None
              and st["z"] > PROMISING_Z and not db.one("SELECT 1 FROM events WHERE kind='lane.promising' AND "
                                                       "exp_id=?", led)):
            db.event("lane.promising", ACTOR, led, {"stats": st, "decisional": False, "label": LABEL,
                                                    "next": "an amendment 8 family draft for the user's approval"})
            out["promising"].append(led)
    if not on or get is None or Risk(db, lambda: now).fail_closed():
        return out
    out["scanner"] = manage_scanner(db, now, get)
    out["hl"] = manage_hl(db, now, get)
    info = started(db)
    act = [a for a in active(db) if is_lane(info[a])]
    last = max((i["ts"] for i in info.values() if is_lane(i)), default=None)
    if len(act) >= SLOTS or (last is not None and now - last < START_EVERY):
        return out
    busy = collections.Counter((info[a]["family"], info[a]["function"]) for a in act)
    done = tried_keys(db, now)
    probes = 0
    for r in candidates(db, fids):
        if r["key"] in done or busy[(r["family"], r["function"])] >= PER_FUNCTION:
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


# ---------- scanner accounts (amendments 12, 12c, 12e) ----------
def scans(db, now, n=2):
    """The latest n measurement times with a USD-M premiumIndex read (symbols_compared is written every time)."""
    return [r[0] for r in db.q("SELECT DISTINCT ts FROM observations WHERE metric='symbols_compared' AND "
                               "instrument='binance_perps' AND ts<=? ORDER BY ts DESC LIMIT ?", int(now), n)]


def fundings(db, ts):
    """12e: {symbol: predicted funding} flagged (>= SCAN_FUND_MIN) at measurement time ts."""
    return {r["instrument"]: r["value"] for r in db.q("SELECT instrument, value FROM observations WHERE "
                                                      "metric='predicted_funding' AND flagged=1 AND ts=?", ts)}


def _last_two(db, now):
    ts = scans(db, now)
    return ts, [fundings(db, t) for t in ts]


def live_funding(coin, now):
    """12e: the latest in-memory predicted funding of `coin` and when it was measured, or (None, None) if older than
    SCAN_LIVE_MAX_S (premium-watch fills it in the same process)."""
    from lab import scanner
    hit = scanner.LIVE.get(scanner.BN)
    if not hit or now - hit[0] > SCAN_LIVE_MAX_S:
        return None, None
    return hit[1].get(coin), hit[0]


def entry_ts(db, ledger, inst):
    """When `inst` last went from flat to a position in `ledger` (the fill that opened it), or None."""
    pos, t = 0.0, None
    for f in db.q("SELECT ts, side, qty FROM sim_fills WHERE exp_id=? AND instrument=? ORDER BY ts, id", ledger, inst):
        was = pos
        pos += f["qty"] if f["side"] == "buy" else -f["qty"]
        if abs(was) < 1e-12 and abs(pos) >= 1e-12:
            t = f["ts"]
    return t


def settled_since_entry(db, ledger, coin, now):
    """12c: a funding settlement after the entry is booked for the perp leg (instrument `coin`), or SCAN_HOLD_S has
    passed."""
    t = entry_ts(db, ledger, coin)
    if t is None:
        return True
    if now - t >= SCAN_HOLD_S:
        return True
    return db.one("SELECT 1 FROM sim_funding WHERE exp_id=? AND instrument=? AND settle_ts>?", ledger, coin, t) is not None


def _two_settled_low(settled, mult=1):
    """12f: the last two settled rates (x mult) are both below SCAN_FUND_EXIT."""
    last = [settled[t] * mult for t in sorted(settled or {})[-2:]]
    return len(last) == 2 and all(v < SCAN_FUND_EXIT for v in last)


def scan_signal(db, coin, holding, now, ledger=None, settled=None):
    """12e/12f. Holding: out after two settled rates in a row below the floor and a settlement since the entry (or
    12 h); without settled data the position is held. Flat: in when the latest measurement (a new account) or the two
    latest measurements (a reopening) flag predicted funding >= SCAN_FUND_MIN; nothing opens on a measurement older
    than SCAN_STALE_S."""
    if holding:
        if ledger is None:
            return 1.0
        return 0.0 if (_two_settled_low(settled) and settled_since_entry(db, ledger, coin, now)) else 1.0
    ts, fs = _last_two(db, now)
    if not ts or now - ts[0] > SCAN_STALE_S or fs[0].get(coin, 0) < SCAN_FUND_MIN:
        return 0.0
    fresh = ledger is None or not db.one("SELECT 1 FROM sim_fills WHERE exp_id=? LIMIT 1", ledger)
    return 1.0 if fresh or (len(fs) > 1 and fs[1].get(coin, 0) >= SCAN_FUND_MIN) else 0.0


def scan_candidates(db, now):
    """Coins whose latest measurement flags predicted funding >= SCAN_FUND_MIN, highest first."""
    ts, fs = _last_two(db, now)
    if not ts or now - ts[0] > SCAN_STALE_S:
        return []
    return sorted((c for c, v in fs[0].items() if v >= SCAN_FUND_MIN), key=lambda c: (-fs[0][c], c))


def _cooling(db, coin, now, source="scanner"):
    """A coin gets a new account SCAN_COOLDOWN_S after its last one (of this source) stopped, SCAN_SKIP_COOLDOWN_S
    after a skip."""
    info = started(db)
    for kind, wait in (("lane.retired", SCAN_COOLDOWN_S), ("lane.skipped", SCAN_SKIP_COOLDOWN_S)):
        for _, ts, _, led, p in _events(db, kind):
            i = p if kind == "lane.skipped" else info.get(led, {})
            if i.get("source") == source and coin in (i.get("coins") or []) and now - p.get("t", ts) < wait:
                return True
    return False


def manage_scanner(db, now, get):
    """Start scanner accounts for every coin that meets 12e point 2, up to SCAN_SLOTS."""
    from lab import paper_runner
    info = started(db)
    held = {info[a]["coins"][0] for a in active(db) if is_scanner(info[a])}
    out, probes = {"started": [], "skipped": []}, 0
    ts, fs = _last_two(db, now)
    for coin in scan_candidates(db, now):
        if len(held) >= SCAN_SLOTS or probes >= PROBES:
            break
        if coin in held or _cooling(db, coin, now):
            continue
        probes += 1
        key, hour = f"scan|{coin}|{int(now) // HOUR * HOUR}", int(now) // HOUR * HOUR
        led = ledger_id(key)
        trigger = {"scan_ts": ts[:2], "funding": fs[0].get(coin), "rule": "research/PROTOCOL_V3.md amendment 12e"}
        base = {"key": key, "source": "scanner", "family": "fcarry", "function": "scanner_funding", "params": {},
                "coin": coin, "trigger": trigger, "label": SCAN_LABEL, "simulated": True, "decisional": False,
                "t": int(now)}
        try:
            _, settled, _, _ = paper_runner.hourly(coin, now, get)
            last3 = [settled[t] for t in sorted(settled)[-3:]]
            trigger["settled_avg3"] = sum(last3) / len(last3) if len(last3) == 3 else None
            if trigger["settled_avg3"] is None or trigger["settled_avg3"] < SCAN_FUND_PERSIST:
                raise ValueError(f"funding not persistent: last 3 settled {last3}")
            for inst in (coin, coin + SPOT):
                if paper_runner.fetch_book(inst, now, get).crossed():
                    raise ValueError("crossed or empty book")
        except Exception as e:
            db.event("lane.skipped", ACTOR, led, {**base, "coins": [coin], "reason": f"{e!r}"[:200]})
            out["skipped"].append(coin)
            continue
        db.event("lane.started", ACTOR, led, {**base, "coins": [coin], "expectation": None, "capital": CAPITAL,
                                              "costs": COSTS.__dict__, "hour": hour,
                                              "rule": "research/PROTOCOL_V3.md amendments 12 and 12e"})
        held.add(coin)
        out["started"].append(led)
    return out


# ---------- Hyperliquid funding accounts (amendment 13) ----------
def scanner_eight():
    from lab import scanner
    return scanner.HL_EIGHT


def hl_scans(db, now, n=2):
    """The latest n Hyperliquid measurement times (hl_symbols_compared is written every time)."""
    return [r[0] for r in db.q("SELECT DISTINCT ts FROM observations WHERE metric='hl_symbols_compared' AND ts<=? "
                               "ORDER BY ts DESC LIMIT ?", int(now), n)]


def hl_fundings(db, ts):
    """{coin: predicted funding x 8} flagged (>= HL_FUND_MIN) at Hyperliquid measurement time ts."""
    return {r["instrument"]: r["value"] for r in db.q("SELECT instrument, value FROM observations WHERE "
                                                      "metric='hl_predicted_funding' AND flagged=1 AND ts=?", ts)}


def hl_live(coin, now):
    """The latest in-memory Hyperliquid predicted funding x 8 of `coin` and its time, or (None, None) when stale."""
    from lab import scanner
    hit = scanner.HL_LIVE.get(scanner.HL_INFO)
    if not hit or now - hit[0] > SCAN_LIVE_MAX_S:
        return None, None
    return hit[1].get(coin), hit[0]


def hl_signal(db, coin, holding, now, ledger=None, settled=None):
    """13/12f. Holding: out after two settled hours in a row (x 8) below the floor and HL_HOLD_S since the entry;
    without settled data the position is held. Flat: in on the latest (a new account) or the two latest (a
    reopening) flagged measurements; nothing opens on a measurement older than SCAN_STALE_S."""
    if holding:
        if ledger is None:
            return 1.0
        t = entry_ts(db, ledger, HL_PERP + coin)
        return 0.0 if (_two_settled_low(settled, scanner_eight()) and (t is None or now - t >= HL_HOLD_S)) else 1.0
    ts = hl_scans(db, now)
    fs = [hl_fundings(db, t) for t in ts]
    if not ts or now - ts[0] > SCAN_STALE_S or fs[0].get(coin, 0) < HL_FUND_MIN:
        return 0.0
    fresh = ledger is None or not db.one("SELECT 1 FROM sim_fills WHERE exp_id=? LIMIT 1", ledger)
    return 1.0 if fresh or (len(fs) > 1 and fs[1].get(coin, 0) >= HL_FUND_MIN) else 0.0


def hl_candidates(db, now):
    ts = hl_scans(db, now, 1)
    if not ts or now - ts[0] > SCAN_STALE_S:
        return [], {}
    fs = hl_fundings(db, ts[0])
    return sorted((c for c, v in fs.items() if v >= HL_FUND_MIN), key=lambda c: (-fs[c], c)), fs


def manage_hl(db, now, get):
    """Start Hyperliquid funding accounts for every coin that meets 13 point 4, up to HL_SLOTS."""
    from lab import paper_runner
    info = started(db)
    held = {info[a]["coins"][0] for a in active(db) if is_hl(info[a])}
    out, probes = {"started": [], "skipped": []}, 0
    cands, fs = hl_candidates(db, now)
    for coin in cands:
        if len(held) >= HL_SLOTS or probes >= PROBES:
            break
        if coin in held or _cooling(db, coin, now, "hl"):
            continue
        probes += 1
        key, hour = f"hl|{coin}|{int(now) // HOUR * HOUR}", int(now) // HOUR * HOUR
        led = ledger_id(key)
        trigger = {"funding": fs.get(coin), "rule": "research/PROTOCOL_V3.md amendment 13"}
        base = {"key": key, "source": "hl", "family": "fcarry", "function": "hl_funding", "params": {},
                "coin": coin, "trigger": trigger, "label": HL_LABEL, "simulated": True, "decisional": False,
                "t": int(now)}
        try:
            settled, _ = paper_runner.hl_hourly(coin, now)
            last = [settled[t] for t in sorted(settled)[-HL_PERSIST_HOURS:]]
            avg = sum(last) / len(last) * 8 if len(last) == HL_PERSIST_HOURS else None
            trigger["settled_avg3"] = avg                  # shown like the scanner's (here: 24 hours x 8)
            trigger["settled_hours"] = len(last)
            if avg is None or avg < HL_FUND_PERSIST:
                raise ValueError(f"funding not persistent: mean of last {len(last)} settled hours x 8 = {avg}")
            p_inst, s_inst = HL_PERP + coin, f"{coin}USDT{SPOT}"
            for inst in (p_inst, s_inst):
                if paper_runner.fetch_book(inst, now, get).crossed():
                    raise ValueError(f"{inst}: crossed or empty book")
        except Exception as e:
            db.event("lane.skipped", ACTOR, led, {**base, "coins": [coin], "reason": f"{e!r}"[:200]})
            out["skipped"].append(coin)
            continue
        db.event("lane.started", ACTOR, led, {**base, "coins": [coin], "expectation": None, "capital": CAPITAL,
                                              "costs": COSTS.__dict__, "hour": hour,
                                              "legs": {"perp": p_inst, "spot": s_inst},
                                              "rule": "research/PROTOCOL_V3.md amendment 13"})
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


def legs(info, coin):
    """(perp instrument, spot instrument) of one coin: USD-M and Binance spot, or (13) Hyperliquid and Binance spot."""
    if is_hl(info):
        return HL_PERP + coin, f"{coin}USDT{SPOT}"
    return coin, coin + SPOT


def run_one(db, ledger, get, now, cache=None, books=None):
    from lab import paper_runner as pr
    info = started(db)[ledger]
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    eng.start(ledger, CAPITAL, COSTS, actor=ACTOR)
    if risk.fail_closed():
        return {"status": "fail_closed"}
    if risk.paused(ledger):
        return pr.mark_only(db, ledger, get, now, books, cache)
    hour, market, opens, price = int(now) // HOUR * HOUR, {}, {}, {}
    try:
        for s in info["coins"]:
            if is_hl(info):                              # amendment 13: Hyperliquid funding and 1h opens
                funding, op = pr.hl_hourly(s, now)
                market[s], opens[s] = (None, funding), op
            else:
                bars, funding, _, op = pr.hourly(s, now, get, cache)
                market[s], opens[s] = (bars, funding), op
    except Exception as e:
        risk.pause(ledger, "data_fetch", None, None, f"public market data fetch failed: {e!r}"[:300],
                   eng.cancel_entries)
        return {"status": "paused", "reason": "data fetch failed"}
    for s, (bars, _) in market.items():
        last = (max(opens[s]) if opens[s] else None) if bars is None else (bars[-1][0] + HOUR if bars else None)
        if last is None or now - last > pr.MAX_BAR_AGE:
            risk.pause(ledger, "data_stale", None, pr.MAX_BAR_AGE, f"{s}: stale bars", eng.cancel_entries)
            return {"status": "paused", "reason": f"{s} data stale"}
        price[s] = opens[s][max(opens[s])] if bars is None else bars[-1][2]
    perp = {legs(info, s)[0]: s for s in market}
    funded = pr.book_funding(db, eng, ledger, now, lambda syms: {
        x: (market[perp[x]][1], opens[perp[x]]) if x in perp else ({}, {}) for x in syms})   # spot: no funding
    pos = eng.ledger(ledger)["positions"]
    if is_scanner(info) or is_hl(info):                  # amendments 12e and 13: one coin, live funding decides
        c = info["coins"][0]
        p_inst, s_inst = legs(info, c)
        holding = pos.get(s_inst, 0.0) > 0 or pos.get(p_inst, 0.0) < 0
        want = {c: (hl_signal if is_hl(info) else scan_signal)(db, c, holding, now, ledger, market[c][1])}
    else:
        want = _signal(info, market)
    last = db.one("SELECT equity FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", ledger)
    size = (last["equity"] if last else CAPITAL) / (UNIT_CAPITAL * len(info["coins"]))
    orders = []
    for s in info["coins"]:
        p_inst, s_inst = legs(info, s)
        sq, pq, px = pos.get(s_inst, 0.0), pos.get(p_inst, 0.0), price[s]
        q = max(sq, -pq, 0.0) if want[s] > 0 else 0.0
        fresh = want[s] > 0 and q == 0.0
        if not fresh and abs(sq - q) * px < MIN_NOTIONAL and abs(pq + q) * px < MIN_NOTIONAL:
            continue
        try:
            bk = {p_inst: pr.fetch_book(p_inst, now, get), s_inst: pr.fetch_book(s_inst, now, get)}
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
            q = size / bk[p_inst].mid()
        for inst, target, cur in ((s_inst, q, sq), (p_inst, -q, pq)):
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


# ---------- daily report (amendment 12d; decides nothing) ----------
REPORT_DIR = "_lane"
REPORT_JOB = {"priority": 60, "max_attempts": 3, "timeout_s": 300}
REPORT_DELAY_S = 1800                           # day D is reported from D+1 00:30 UTC (the day's last mark is in)
PILOT_DAYS, PILOT_DD = 3, 0.03                  # research/PILOT_BANE_UDKAST.md point 1 (the user's 3 days)


def _in_day(info, gone, a):
    """Started before the day ended and not retired before it began."""
    return info["ts"] < a + DAY and (gone is None or gone["ts"] >= a)


def enqueue_report(db, now=None, actor="strategy-1"):
    """lane_report|<day> for the last ended UTC day if a lane account was active in it. Returns the number of new jobs."""
    now = now or time.time()
    day = explore._day(now - DAY)
    a, gone = explore._day_start(day), retired(db)
    if not any(_in_day(i, gone.get(led), a) for led, i in started(db).items()):
        return 0
    jobs.init(db)
    return jobs.enqueue(db, f"lane_report|{day}", "lane_report", None, {"day": day}, actor=f"system:{actor}",
                        not_before=a + DAY + REPORT_DELAY_S, **REPORT_JOB)[1]


def account_row(db, ledger, info, gone, end):
    """One account as of `end` (the day's end): the figures of point 2 and the pilot's paper criteria (point 3)."""
    eq = db.one("SELECT equity FROM sim_equity WHERE exp_id=? AND ts<? ORDER BY id DESC LIMIT 1", ledger, end)
    dd = db.one("SELECT MAX(drawdown) FROM sim_equity WHERE exp_id=? AND ts<?", ledger, end)[0] or 0.0
    funding = db.one("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=? AND ts<?", ledger, end)[0]
    fees = db.one("SELECT COALESCE(SUM(fee), 0) FROM sim_fills WHERE exp_id=? AND ts<?", ledger, end)[0]
    p = db.one("SELECT action, rule FROM risk_events WHERE exp_id=? AND action IN ('PAUSE','CLEAR') AND ts<? "
               "ORDER BY id DESC LIMIT 1", ledger, end)
    if gone is not None and gone["ts"] < end:
        status = f"stoppet: {gone.get('rule')}"
    else:
        status = f"pause: {p['rule']}" if p is not None and p["action"] == "PAUSE" else "aktiv"
    equity = eq["equity"] if eq else CAPITAL
    days = int(max(0, end - info["ts"]) // DAY)
    crit = {f"hele døgn live >= {PILOT_DAYS}": days >= PILOT_DAYS, "netto > 0": equity > CAPITAL,
            "funding - gebyrer > 0": funding - fees > 0, f"største fald < {PILOT_DD:.0%}": dd < PILOT_DD,
            "ikke stoppet": not status.startswith("stoppet"), "slippage mod modellen": "ikke målt"}
    met = all(v is True for k, v in crit.items() if k != "slippage mod modellen")
    return {"ledger": ledger, "source": info.get("source") or "lane", "function": info.get("function"),
            "params": info.get("params"), "coins": info.get("coins"), "started": info["ts"], "status": status,
            "equity": equity, "net": equity - CAPITAL, "net_pct": (equity - CAPITAL) / CAPITAL, "funding": funding,
            "fees": fees, "funding_minus_fees": funding - fees, "max_drawdown": dd, "days_live": days,
            "pilot_paper_criteria": crit, "pilot_paper_criteria_met": met, "simulated": True}


def report(db, day):
    a = explore._day_start(day)
    gone = retired(db)
    rows = [account_row(db, led, i, gone.get(led), a + DAY) for led, i in sorted(started(db).items())
            if _in_day(i, gone.get(led), a)]
    return {"day": day, "accounts": rows, "met": [r["ledger"] for r in rows if r["pilot_paper_criteria_met"]],
            "net_total": sum(r["net"] for r in rows), "decisional": False, "simulated": True,
            "rule": "research/PROTOCOL_V3.md amendment 12d: decides nothing; a pilot needs the user's numbers, key and "
                    "a dated protocol"}


def step_report(db, job, worker):
    day = (job.get("payload") or {}).get("day")
    end = explore._day_start(day) + DAY
    if time.time() < end + REPORT_DELAY_S:
        raise pipeline.Deferred(f"{day} is not over (+{REPORT_DELAY_S // 60} min)", end + REPORT_DELAY_S)
    out = report(db, day)
    art = pipeline.save_artifact(REPORT_DIR, day, out)
    db.event("research.lane_report", f"system:{worker}", None,
             {"day": day, "accounts": len(out["accounts"]), "met": out["met"], "net_total": out["net_total"],
              "decisional": False, "artifact_sha256": art["sha256"]})
    return {"day": day, "accounts": len(out["accounts"]), "met": out["met"], "artifact": art}
