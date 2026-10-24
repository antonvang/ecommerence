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
import re
import statistics
import time

from lab import explore, families, jobs, lifecycle, news, pipeline
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
LANE_NEVER_S = DAY                              # 11f: a lane account that never traded retires a day after start
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
SPOT_LIST_EVERY = HOUR                          # 19: the Binance spot pair list is read at most once an hour
_SPOT_LIST = {}                                 # 19: {"at": read at, "pairs": trading spot symbols}, memory only
NO_SPOT = "intet spotpar på Binance (19)"
# amendment 13: Hyperliquid funding accounts (source "hl"): long Binance spot, short Hyperliquid perp
HL_LABEL = "HL-KONTO (Hyperliquid-funding, simuleret, aldrig bevis)"
HL_PERP = "HL:"                                 # the perp leg's instrument prefix (paper_runner.HL_PREFIX)
HL_SLOTS = 10
HL_HOLD_S = 8 * HOUR                            # 13 point 5: out no earlier than 8 h after the entry
# amendment 16e: Binance delisting announcements (news-watch, amendment 16) keep scanner and HL accounts away
DELIST_WINDOW_S = 30 * DAY
DELIST_SPOT = ("Binance Will Delist", "Binance to Delist")
DELIST_FUTURES = ("Binance Futures Will Delist", "Binance Futures to Delist")
DELIST_DROP = {"USD", "USDT", "USDC", "BUSD", "M"}
HL_PERSIST_HOURS = 24                           # 13 point 4: mean of the last 24 settled hours x 8 >= HL_FUND_PERSIST
HL_FUND_MIN = 0.001                             # 13a: predicted funding x 8 >= 0.10 % (13a's study figures are not
                                                # reproducible; corrected study: research/studies/CARRY_COST_2026-10-21.md)
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
                if r.get("candidate") and r.get("family") in fids and all((r.get("checks") or {}).values()) \
                        and r.get("method") == explore.METHOD:            # amendment 15 point 3: selection on S
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
            "source": "explore0 selection window (2020) result at 2x costs (amendments 11 point 6 and 15 point 3)"}


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
    coin = (info.get("coins") or [""])[0]
    title = delistings(db, now, spot_only=is_hl(info)).get(_base(coin, info.get("source")))
    if title:                                                    # 16e point 5
        return "delisting", f"afnotering annonceret (16e): {title}"[:200], st
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


def delist_coins(title):
    """16e point 2: the upper-case words (at least one letter) after "Delist", quote suffixes cut (IPUSDT -> IP)."""
    out = []
    for w in re.split(r"[\s,&()]+", title.split("Delist", 1)[1] if "Delist" in title else ""):
        if not re.fullmatch(r"[A-Z0-9]*[A-Z][A-Z0-9]*", w) or w in DELIST_DROP:
            continue
        for q in ("USDT", "USDC", "BUSD"):
            if w.endswith(q) and len(w) > len(q):
                w = w[:-len(q)]
                break
        if w not in out:
            out.append(w)
    return out


def delistings(db, now, spot_only=False):
    """16e points 1 and 3: {coin: title} of the delisting announcements usable by now and published within
    DELIST_WINDOW_S."""
    prefixes, out = DELIST_SPOT if spot_only else DELIST_SPOT + DELIST_FUTURES, {}
    for r in db.q("SELECT payload FROM observations WHERE detector=? AND metric='news_item' AND ts>=? "
                  "AND payload LIKE '%delisting%' ORDER BY ts, rowid", news.DETECTOR, int(now - DELIST_WINDOW_S)):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        t, title = p.get("usable_from"), p.get("title") or ""
        if p.get("category") == "delisting" and t is not None and t <= now \
                and now - DELIST_WINDOW_S < (p.get("published_ts") or t) and title.startswith(prefixes):
            for c in delist_coins(title):
                out.setdefault(c, title)
    return out


def spot_pairs(get, now):
    """19: Binance spot symbols with status TRADING (public exchangeInfo from the market-data host, at most once an
    hour). A failed read keeps the last list; None while no list was ever read (then nothing is skipped)."""
    from lab import paper_runner
    at = _SPOT_LIST.get("at")
    if at is None or not 0 <= now - at < SPOT_LIST_EVERY:
        _SPOT_LIST["at"] = now
        try:
            d = get(f"{paper_runner.SPOT_REST}/api/v3/exchangeInfo?symbolStatus=TRADING")
            pairs = {x["symbol"] for x in d["symbols"] if x.get("status") == "TRADING"}
            if pairs:
                _SPOT_LIST["pairs"] = pairs
        except Exception:                                       # noqa: BLE001 - the last list (or none) is kept
            pass
    return _SPOT_LIST.get("pairs")


def _no_spot(get, now, symbol):
    """19: True only when a spot list is known and `symbol` is not in it."""
    pairs = spot_pairs(get, now)
    return pairs is not None and symbol not in pairs


def _base(coin, source):
    """The coin name in announcement titles: a scanner trades the USD-M symbol (MITOUSDT), an HL account the coin."""
    return coin[:-4] if source == "scanner" and coin.endswith("USDT") else coin


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
        if last is None and now - info["ts"] >= LANE_NEVER_S:
            return "flat", f"ingen position siden start i {LANE_NEVER_S // HOUR} timer (11f)", st
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


def _would_hold(r, coins, get, now, skip_unreadable=False):
    """11b: the coins in which the variant's own function holds +1 on the live data it would trade on, or [] (also
    when the data cannot be read). 11h's check before the books: a coin whose data cannot be read is left out, as
    _probe would leave it out."""
    from lab import paper_runner as pr
    cache = pr._HOURLY if get is pr._get else None
    try:
        market = {}
        for s in coins:
            try:
                bars, funding, _, _ = pr.hourly(s, now, get, cache)
            except Exception:
                if not skip_unreadable:
                    raise
                continue
            market[s] = (bars, funding)
        if not market:
            return []
        want = _signal({"family": r["family"], "function": r["function"], "params": r["params"]}, market)
    except Exception:
        return []
    return [s for s, v in want.items() if v > 0]


def _lane_base(r):
    return {k: r.get(k) for k in ("key", "family", "function", "params", "net_sharpe_ann", "artifact",
                                  "artifact_sha256", "evaluated_coins")} | {"basket": r.get("coins")}


def _basket(r, fam):
    return list(r.get("evaluated_coins") or r.get("coins") or explore.universe(fam))   # the coins _probe reads


def _skip_unheld(db, r, basket, now, **extra):
    """11b/11h: the variant holds nothing now on the basket's hourly data; retried after RETRY_S."""
    db.event("lane.skipped", ACTOR, ledger_id(r["key"]), {
        **_lane_base(r), "coins": basket, "dropped": [], "books_read": False, "reason": "would hold nothing now (11b)",
        "retry": True, "t": int(now), "simulated": True, **extra})


def _start(db, r, get, now):
    led, fam = ledger_id(r["key"]), families.load(r["family"])
    base = _lane_base(r)
    basket = _basket(r, fam)
    if not _would_hold(r, basket, get, now, skip_unreadable=True):  # 11h: before any book is read
        _skip_unheld(db, r, basket, now)
        return None
    coins, dropped = _probe(r, fam, get, now)
    base["dropped"] = dropped
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
    if len(act) >= SLOTS:
        return out
    out["reviews_queued"] = enqueue_reviews(                    # 11i: only for a candidate that holds something now
        db, now, actor="paper-1", fids=fids, cap=SLOTS - len(act),
        holds=lambda r: bool(_would_hold(r, _basket(r, families.load(r["family"])), get, now, skip_unreadable=True)))
    if last is not None and now - last < START_EVERY:
        return out
    busy = collections.Counter((info[a]["family"], info[a]["function"]) for a in act)
    done, passed = tried_keys(db, now), {k for k, p in reviews(db).items() if p.get("ok")}    # 11c
    probes = 0
    for r in candidates(db, fids):
        if r["key"] in done or r["key"] not in passed or busy[(r["family"], r["function"])] >= PER_FUNCTION:
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


COST_DAYS = 3                                   # 12g: 3 days of predicted funding must cover the round trip


def walk(book, side, qty):
    """Mean fill price of a taker order of `qty` walked through the book, as a fraction away from the mid (always >= 0),
    or None when the book is too thin for the whole quantity."""
    levels, mid, rest, cost = (book.asks if side == "buy" else book.bids), book.mid(), qty, 0.0
    for px, size in levels:
        q = min(rest, size)
        cost += q * px
        rest -= q
        if rest <= 1e-12:
            avg = cost / qty
            return (avg - mid) / mid if side == "buy" else (mid - avg) / mid
    return None


def round_trip_cost(spot_book, perp_book, notional, costs=COSTS):
    """12g: the cost of opening and closing both legs of `notional` USD each, as a fraction of one leg: fees and the
    extra slippage per fill plus the walked distance from the mid (spot bought then sold, perp sold then bought).
    None when a book cannot fill the size."""
    qty = notional / perp_book.mid()
    w = [walk(spot_book, "buy", qty), walk(spot_book, "sell", qty), walk(perp_book, "sell", qty),
         walk(perp_book, "buy", qty)]
    if any(x is None for x in w):
        return None
    return sum(w) + 4 * (costs.taker_fee + costs.extra_slippage)


EXEC_SKEW_MAX = 5.0                             # 12h: the two books must be fetched within 5 s of each other
_wall = time.time                               # replaceable in tests


def leg_stats(book, qty, instrument=None, fetched_at=None):
    """12h point 1, observed: spread, depth on each side of the 20 levels (USD) and the VWAP distance from the mid for
    `qty` bought and sold (None = the book cannot fill it). The mid is a reference, never a fill price."""
    mid = book.mid()
    return {"instrument": instrument, "fetched_at": fetched_at, "mid": mid,
            "spread": (book.asks[0][0] - book.bids[0][0]) / mid,
            "depth_bid_usd": sum(p * q for p, q in book.bids), "depth_ask_usd": sum(p * q for p, q in book.asks),
            "vwap_buy": walk(book, "buy", qty), "vwap_sell": walk(book, "sell", qty)}


def fetch_pair(pr, insts, now, get):
    """Both books with the wall-clock time each was read (12h point 2)."""
    books, at = {}, {}
    for inst in insts:
        books[inst] = pr.fetch_book(inst, now, get)
        at[inst] = _wall()
    return books, at


def _cost_gate(trigger, spot_book, perp_book, funding_8h, at=None, insts=(None, None)):
    """12g point 2 and 12h: record the execution observed in both books, then refuse (ValueError, so the coin is
    skipped) unsynchronised books, a book too thin for the size, or COST_DAYS of predicted funding below the cost."""
    size = CAPITAL / UNIT_CAPITAL
    qty = size / perp_book.mid()
    cost = round_trip_cost(spot_book, perp_book, size)
    earn = (funding_8h or 0.0) * 3 * COST_DAYS          # 12i: funding_8h is per 8 hours for every interval
    skew = abs(at[insts[0]] - at[insts[1]]) if at and None not in insts else None
    trigger["round_trip_cost"], trigger["funding_3d"] = cost, earn
    trigger["execution"] = {
        "size_usd_per_leg": size, "qty": qty, "skew_s": skew,
        "spot": leg_stats(spot_book, qty, insts[0], at.get(insts[0]) if at else None),
        "perp": leg_stats(perp_book, qty, insts[1], at.get(insts[1]) if at else None),
        "basis": spot_book.mid() / perp_book.mid() - 1,
        "fees_round_trip": 4 * COSTS.taker_fee, "extra_slippage_round_trip": 4 * COSTS.extra_slippage,
        "round_trip_cost": cost if cost is not None else "UNKNOWN", "funding_3d": earn,
        "observed": ["spread", "depth", "vwap", "basis", "skew"], "assumed": ["fees (VIP0)", "extra slippage"]}
    if skew is not None and skew > EXEC_SKEW_MAX:
        trigger["execution"]["round_trip_cost"] = "UNKNOWN"
        raise ValueError(f"unsynchronised books: {skew:.1f} s apart (12h)")
    if cost is None:
        raise ValueError("a book is too thin for the account's size (12g)")
    if earn < cost:
        raise ValueError(f"3 days of predicted funding {earn:.4%} do not cover the round-trip cost {cost:.4%} (12g)")


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


def per8h(settled):
    """12i: {settle ts: rate per 8 hours}, each Binance settlement scaled by the hours since the previous one (the first
    by the hours to the next; a single settlement is taken as 8-hourly)."""
    ts = sorted(settled or {})
    out = {}
    for i, t in enumerate(ts):
        gap = (t - ts[i - 1]) if i else ((ts[1] - t) if len(ts) > 1 else 8 * HOUR)
        h = max(1, round(gap / HOUR))
        out[t] = settled[t] * 8 / h
    return out


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
        return 0.0 if (_two_settled_low(per8h(settled)) and settled_since_entry(db, ledger, coin, now)) else 1.0
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
    gone = delistings(db, now)
    for coin in scan_candidates(db, now):
        if len(held) >= SCAN_SLOTS or probes >= PROBES:
            break
        if coin in held or _cooling(db, coin, now):
            continue
        key, hour = f"scan|{coin}|{int(now) // HOUR * HOUR}", int(now) // HOUR * HOUR
        led = ledger_id(key)
        trigger = {"scan_ts": ts[:2], "funding": fs[0].get(coin), "rule": "research/PROTOCOL_V3.md amendment 12e"}
        base = {"key": key, "source": "scanner", "family": "fcarry", "function": "scanner_funding", "params": {},
                "coin": coin, "trigger": trigger, "label": SCAN_LABEL, "simulated": True, "decisional": False,
                "t": int(now)}
        if _base(coin, "scanner") in gone:                      # 16e point 4: before a probe is spent
            db.event("lane.skipped", ACTOR, led, {**base, "coins": [coin], "reason":
                                                  f"afnotering annonceret (16e): {gone[_base(coin, 'scanner')]}"[:200]})
            out["skipped"].append(coin)
            continue
        if _no_spot(get, now, coin):                            # 19: before a probe is spent
            db.event("lane.skipped", ACTOR, led, {**base, "coins": [coin], "reason": NO_SPOT})
            out["skipped"].append(coin)
            continue
        probes += 1
        try:
            _, settled, _, _ = paper_runner.hourly(coin, now, get)
            norm = per8h(settled)                                                      # 12i: per 8 hours
            last3 = [norm[t] for t in sorted(norm)[-3:]]
            trigger["settled_raw3"] = [settled[t] for t in sorted(settled)[-3:]]
            trigger["settled_avg3"] = sum(last3) / len(last3) if len(last3) == 3 else None
            if trigger["settled_avg3"] is None or trigger["settled_avg3"] < SCAN_FUND_PERSIST:
                raise ValueError(f"funding not persistent: last 3 settled {last3}")
            bks, at = fetch_pair(paper_runner, (coin + SPOT, coin), now, get)
            if any(b.crossed() for b in bks.values()):
                raise ValueError("crossed or empty book")
            _cost_gate(trigger, bks[coin + SPOT], bks[coin], fs[0].get(coin), at, (coin + SPOT, coin))   # 12g/12h
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
    gone = delistings(db, now, spot_only=True)
    for coin in cands:
        if len(held) >= HL_SLOTS or probes >= PROBES:
            break
        if coin in held or _cooling(db, coin, now, "hl"):
            continue
        key, hour = f"hl|{coin}|{int(now) // HOUR * HOUR}", int(now) // HOUR * HOUR
        led = ledger_id(key)
        trigger = {"funding": fs.get(coin), "rule": "research/PROTOCOL_V3.md amendment 13"}
        base = {"key": key, "source": "hl", "family": "fcarry", "function": "hl_funding", "params": {},
                "coin": coin, "trigger": trigger, "label": HL_LABEL, "simulated": True, "decisional": False,
                "t": int(now)}
        if coin in gone:                                        # 16e points 4 and 6: spot delistings only
            db.event("lane.skipped", ACTOR, led, {**base, "coins": [coin],
                                                  "reason": f"afnotering annonceret (16e): {gone[coin]}"[:200]})
            out["skipped"].append(coin)
            continue
        if _no_spot(get, now, f"{coin}USDT"):                   # 19: the spot leg, before a probe is spent
            db.event("lane.skipped", ACTOR, led, {**base, "coins": [coin], "reason": NO_SPOT})
            out["skipped"].append(coin)
            continue
        probes += 1
        try:
            settled, _ = paper_runner.hl_hourly(coin, now)
            last = [settled[t] for t in sorted(settled)[-HL_PERSIST_HOURS:]]
            avg = sum(last) / len(last) * 8 if len(last) == HL_PERSIST_HOURS else None
            trigger["settled_avg3"] = avg                  # shown like the scanner's (here: 24 hours x 8)
            trigger["settled_hours"] = len(last)
            if avg is None or avg < HL_FUND_PERSIST:
                raise ValueError(f"funding not persistent: mean of last {len(last)} settled hours x 8 = {avg}")
            p_inst, s_inst = HL_PERP + coin, f"{coin}USDT{SPOT}"
            bks, at = fetch_pair(paper_runner, (s_inst, p_inst), now, get)
            for inst, b in bks.items():
                if b.crossed():
                    raise ValueError(f"{inst}: crossed or empty book")
            _cost_gate(trigger, bks[s_inst], bks[p_inst], fs.get(coin), at, (s_inst, p_inst))   # 12g/12h (x 8 already)
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


def _fetch(info, now, get, cache):
    """Each coin's (closed 1h bars or None, settled funding) and its 1h opens; raises if any fetch fails."""
    from lab import paper_runner as pr
    market, opens = {}, {}
    for s in info["coins"]:
        if is_hl(info):                                  # amendment 13: Hyperliquid funding and 1h opens
            funding, op = pr.hl_hourly(s, now)
            market[s], opens[s] = (None, funding), op
        else:
            bars, funding, _, op = pr.hourly(s, now, get, cache)
            market[s], opens[s] = (bars, funding), op
    return market, opens


def _stale(market, opens, now):
    """The first coin whose last closed bar (or Hyperliquid open) is older than MAX_BAR_AGE, else None."""
    from lab import paper_runner as pr
    for s, (bars, _) in market.items():
        last = (max(opens[s]) if opens[s] else None) if bars is None else (bars[-1][0] + HOUR if bars else None)
        if last is None or now - last > pr.MAX_BAR_AGE:
            return s
    return None


def _data_probe(info, now, get, cache):
    """Amendment 18: the same fetch and check a pass trades on, for an account paused by data_fetch; raises on any
    failure and never orders."""
    market, opens = _fetch(info, now, get, cache)
    bad = _stale(market, opens, now)
    if bad:
        raise ValueError(f"{bad}: stale bars")


def run_one(db, ledger, get, now, cache=None, books=None):
    from lab import paper_runner as pr
    info = started(db)[ledger]
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    eng.start(ledger, CAPITAL, COSTS, actor=ACTOR)
    if risk.fail_closed():
        return {"status": "fail_closed"}
    if risk.paused(ledger) and not risk.auto_resume(ledger, lambda: _data_probe(info, now, get, cache)):
        return pr.mark_only(db, ledger, get, now, books, cache)
    hour, price = int(now) // HOUR * HOUR, {}
    try:
        market, opens = _fetch(info, now, get, cache)
    except Exception as e:
        risk.pause(ledger, "data_fetch", None, None, f"public market data fetch failed: {e!r}"[:300],
                   eng.cancel_entries)
        return {"status": "paused", "reason": "data fetch failed"}
    bad = _stale(market, opens, now)
    if bad:
        risk.pause(ledger, "data_stale", None, pr.MAX_BAR_AGE, f"{bad}: stale bars", eng.cancel_entries)
        return {"status": "paused", "reason": f"{bad} data stale"}
    for s, (bars, _) in market.items():
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


# ---------- classification and observed decomposition (amendment 12h; display only) ----------
READY_TRADES = 30                               # 12h point 4: closed trades of the same mechanism before "ready"
CLASSES = ("afvist af omkostninger", "utilstrækkelige data", "afventer fremadtest",
           "klar til formel, menneskegodkendt validering")


def classify(kind, payload, ready=False):
    """12h point 4 for one start attempt (lane.started / lane.skipped of a scanner or HL account)."""
    if kind == "lane.started":
        return CLASSES[3] if ready else CLASSES[2]
    reason = str(payload.get("reason") or "")
    if "do not cover the round-trip cost" in reason:
        return CLASSES[0]
    return CLASSES[1]


def decomposition(db, ledger):
    """12h point 3, observed from the fills: net = funding - fees - paid distance from the mid + the rest (price and
    basis moves measured at the mid). Each part counted once; the parts sum to net. The paid distance splits into the
    measured book distance (`book`) and the modelled slippage allowance (`allowance`)."""
    fills = db.q("SELECT px, qty, fee, mid, side FROM sim_fills WHERE exp_id=?", ledger)
    funding = db.one("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=?", ledger)[0]
    eq = db.one("SELECT equity, cash, ts FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", ledger)
    net = (eq["equity"] if eq else CAPITAL) - CAPITAL
    fees = sum(f["fee"] for f in fills)
    paid = sum(abs(f["px"] - f["mid"]) * f["qty"] for f in fills if f["mid"])
    unknown = sum(1 for f in fills if not f["mid"])
    s = (started(db).get(ledger, {}).get("costs") or {}).get("extra_slippage", COSTS.extra_slippage)
    # research/LINUX_DRIFT.md 2026-10-24: a fill's price is the book level x (1 +- s); the allowance is modelled
    allowance = sum(f["px"] * f["qty"] * s / ((1 + s) if f["side"] == "buy" else (1 - s)) for f in fills if f["mid"])
    # 21t: the residual checked against an independent mid-based price P&L from the same mark
    mv = (eq["equity"] - eq["cash"]) if eq else 0.0
    indep = sum((-1 if f["side"] == "buy" else 1) * f["mid"] * f["qty"] for f in fills if f["mid"]) + mv
    better = sum(1 for f in fills if f["mid"] and ((f["side"] == "buy" and f["px"] < f["mid"]) or
                                                   (f["side"] == "sell" and f["px"] > f["mid"])))
    after = db.one("SELECT COUNT(*) FROM sim_fills WHERE exp_id=? AND ts>?", ledger, eq["ts"])[0] if eq else len(fills)
    resid = net - funding + fees + paid
    return {"net": net, "funding": funding, "fees": -fees, "spread_slippage": -paid,
            "book": -(paid - allowance), "allowance": -allowance,
            "price_basis": resid, "fills": len(fills),
            "fills_without_mid": unknown, "observed": True,
            "price_basis_independent": indep, "price_basis_gap": resid - indep,
            "fills_better_than_mid": better, "fills_after_mark": after}


def closed_trades(db, source):
    """Closed perp-leg round trips over every account of `source` (for the "ready" class)."""
    n = 0
    for led, i in started(db).items():
        if (i.get("source") or "lane") != source:
            continue
        if db.one("SELECT 1 FROM events WHERE kind='paper.started' AND exp_id=?", led):
            n += len(PaperEngine(db).ledger(led)["trades"]) // 2       # each round trip closes two legs
    return n


# ---------- adversarial review of lane candidates (amendment 11c) ----------
REVIEW_DIR = "_lane_review"
REVIEW_QUEUE_MAX = 6
REVIEW_JOB = {"priority": 150, "max_attempts": 2, "timeout_s": 1800}
REVIEW_DELAY_SHARPE = 1.0                       # the delayed net Sharpe at 2x costs, as the candidate itself
REVIEW_DELAY_BARS = 24                          # 11d: one decision period (the rules decide once a day)
REVIEW_METHOD = "15"                            # reviews by an older method do not count (amendment 15)
REVIEW_PLACEBO_N = 60


def review_id(key):
    """Job and artifact name of a review by the current method: an older method's job row and artifact (named by the
    key alone) are never reused or overwritten."""
    return hashlib.sha256(f"{REVIEW_METHOD}|{key}".encode()).hexdigest()[:10]


def reviews(db):
    """{key: research.lane_review payload}: the latest review of each candidate by the current method (15)."""
    return {p.get("key"): p for _, _, _, _, p in _events(db, "research.lane_review")
            if p.get("method") == REVIEW_METHOD}


REVIEW_HOLD_CHECKS = 20                         # 11i: 11b checks of unreviewed candidates per pass at most


def enqueue_reviews(db, now=None, actor="strategy-1", fids=None, holds=None, cap=None):
    """Point 3: queue reviews for the best unreviewed candidates, at most REVIEW_QUEUE_MAX waiting or running, and
    (amendment 11e) only while a lane slot is free: with every slot taken a review cannot lead to a start; (11g) nor
    for a function that already has PER_FUNCTION active accounts. 11i: with `holds` (the lane start pass), a candidate
    is first checked by 11b on the hourly data: holding nothing, it gets 11b's skip and 24 h retry instead of a review;
    at most `cap` (the free slots) reviews wait or run, and at most REVIEW_HOLD_CHECKS candidates are checked."""
    now = now or time.time()
    jobs.init(db)
    info = started(db)
    act = [a for a in active(db) if is_lane(info[a])]
    if len(act) >= SLOTS:
        return 0
    busy = collections.Counter((info[a]["family"], info[a]["function"]) for a in act)       # 11g
    limit = REVIEW_QUEUE_MAX if cap is None else min(REVIEW_QUEUE_MAX, cap)
    waiting = db.one("SELECT COUNT(*) FROM jobs WHERE kind='lane_review' AND status IN ('queued','running','blocked')")[0]
    if waiting >= limit:
        return 0
    done, tried, n, checks = reviews(db), tried_keys(db, now), 0, 0
    queued = {r[0] for r in db.q("SELECT job_id FROM jobs WHERE kind='lane_review' AND status IN "
                                 "('queued','running','blocked')")}
    for r in candidates(db, explore.eligible(db) if fids is None else fids):
        if waiting >= limit:
            break
        if r["key"] in done or r["key"] in tried or busy[(r["family"], r["function"])] >= PER_FUNCTION:
            continue
        if f"lane_review|{review_id(r['key'])}" in queued:
            continue
        if holds is not None:
            if checks >= REVIEW_HOLD_CHECKS:
                break
            checks += 1
            if not holds(r):
                _skip_unheld(db, r, _basket(r, families.load(r["family"])), now, reviewed=False)
                continue
        added = jobs.enqueue(db, f"lane_review|{review_id(r['key'])}", "lane_review", None, {"key": r["key"]},
                             actor=f"system:{actor}", now=now, **REVIEW_JOB)[1]
        waiting, n = waiting + added, n + added
    return n


def _stressed(costs):
    return {**costs, **{k: costs[k] * explore.STRESS for k in ("taker_fee", "half_spread", "slippage")}}


def review(r, bars, funding):
    """11c point 1 as amendment 15 sets it, on the candidate's own coins: exact look-ahead (also strict) and poison
    tests on all of explore0; the one-period delay at 2x costs and the returns placebo on the review window R only
    (positions from all of explore0). Returns the checks and their numbers."""
    from lab.engine import adversarial, catalogue
    fam = families.load(r["family"])
    coins = [c for c in (r.get("coins") or r.get("evaluated_coins") or sorted(bars)) if c in bars]
    bars = {c: bars[c] for c in coins}
    funding = {c: funding.get(c, {}) for c in coins}
    fn = getattr(importlib.import_module(f"lab.families.{r['family']}"), r["function"])
    trunc = adversarial.truncation_test_xs(fn, bars, funding, r["params"], 20)
    strict = adversarial.strict_truncation_test_xs(fn, bars, funding, r["params"], 20)
    poison = adversarial.poison_test_xs(fn, bars, funding, r["params"])
    rb, rf, pos = explore.window(bars, funding, fn(bars, funding, r["params"], None), *explore.REVIEW)
    costs = _stressed(fam["costs"])
    late = adversarial.delayed_by(rb, pos, rf, costs, REVIEW_DELAY_BARS)
    plac = adversarial.placebo_returns(rb, pos, rf, costs, n=REVIEW_PLACEBO_N)
    checks = {"look-ahead truncation exact": trunc["ok"], "strict look-ahead exact": strict["ok"],
              "poison exact": poison["ok"],
              f"{REVIEW_DELAY_BARS}-bar delay net Sharpe >= {REVIEW_DELAY_SHARPE} at 2x costs":
                  (late.get("net_sharpe_ann") or -1e9) >= REVIEW_DELAY_SHARPE,
              f"placebo p < {catalogue.PLACEBO_P_MAX}": plac["p"] is not None and plac["p"] < catalogue.PLACEBO_P_MAX}
    return {"coins": coins, "checks": checks, "ok": all(checks.values()), "truncation": trunc, "strict": strict,
            "poison": poison, "window": "2021-01-01..2021-12-31 (review, amendment 15 point 3)",
            "delayed_net_sharpe": late.get("net_sharpe_ann"), "delayed_net_total": late.get("net_total"),
            "placebo": plac}


def step_review(db, job, worker, load=None):
    """The lane_review job: `load(fam)` replaces the lane's data access in tests."""
    key = (job.get("payload") or {}).get("key")
    cand = {r["key"]: r for r in candidates(db, explore.eligible(db))}.get(key)
    if cand is None:
        return {"key": key, "skipped": "no longer a candidate of an approved family"}
    fam = families.load(cand["family"])
    bars, funding, _, inputs = load(fam) if load else explore._files(fam, explore.SPLIT)
    res = review(cand, bars, funding)
    out = {**res, "key": key, "family": cand["family"], "function": cand["function"], "params": cand["params"],
           "split": explore.SPLIT, "inputs": inputs, "label": explore.LABEL, "decisional": False,
           "method": REVIEW_METHOD, "rule": "research/PROTOCOL_V3.md amendments 11c, 11d and 15"}
    art = pipeline.save_artifact(REVIEW_DIR, review_id(key), out)
    db.event("research.lane_review", f"system:{worker}", None,
             {"key": key, "ok": res["ok"], "checks": res["checks"], "placebo_p": res["placebo"]["p"],
              "delayed_net_sharpe": res["delayed_net_sharpe"], "artifact_sha256": art["sha256"],
              "method": REVIEW_METHOD, "decisional": False, "label": explore.LABEL})
    return {"key": key, "ok": res["ok"], "artifact": art}


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


def verify_report(db, day, worker, artifacts=None):
    """research/LINUX_DRIFT.md 2026-10-23: the independent recomputation (lab/reportcheck.py, read-only) right after
    the report; its outcome is recorded, and a failure of the check itself is recorded as not verified."""
    from lab import reportcheck
    try:
        rows = reportcheck.checks(db.path, day, artifacts)
        ok = bool(rows) and all(r[1] for r in rows)
        failed = [f"{n}: {d}"[:160] for n, k, d in rows if not k][:10]
        p = {"day": day, "ok": ok, "checks": len(rows), "failed": failed}
    except Exception as e:                                  # noqa: BLE001 - never stops the report itself
        p = {"day": day, "ok": False, "checks": 0, "failed": [f"check failed: {e!r}"[:200]]}
    db.event("research.lane_report_verified", f"system:{worker}", None, {**p, "decisional": False})
    return p


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
    verify_report(db, day, worker)
    return {"day": day, "accounts": len(out["accounts"]), "met": out["met"], "artifact": art}
