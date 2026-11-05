"""Straks-bog (research/PROTOCOL_V3.md amendment 41). SIMULATION ONLY: no exchange, no keys, no real money.

Two lane accounts (source "straks") trade every abnormal-move record (`opportunity.move`, amendment 21) at once on the
perp's public book: STRAKS-FØLG follows the move, STRAKS-MOD fades it. 1 000 USDT per position, at most one open
position per market per account, out after 24 hours, full costs (taker fee, slippage allowance, the book walk) and
settled funding. Never evidence; nothing here is a candidate, an alpha row or a lock.
"""
from __future__ import annotations

import json

from lab.paper import CostModel, PaperEngine
from lab.risk import Risk

SOURCE = "straks"
BOOKS = {"straks|cont": (+1, "STRAKS-FØLG", "straks_follow"), "straks|rev": (-1, "STRAKS-MOD", "straks_fade")}
LABEL = "STRAKS-KONTO (handler hver bevægelse straks, simuleret, aldrig bevis)"
RULE = "research/PROTOCOL_V3.md amendment 41"
CAPITAL = 10_000.0
SIZE_USD = 1_000.0                              # point 3
HOLD_S = 24 * 3600                              # point 4
FRESH_S = 2 * 3600                              # point 2: a record older than this when first seen is not traded
COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.002)   # point 3
LOSS = 0.20                                     # point 5
MAX_AGE_S = 90 * 86400
PAUSE_S = 86400
ACTOR = "system:lane"


def is_straks(info):
    return (info or {}).get("source") == SOURCE


def rules_text():
    return (f"handler hver usædvanlig bevægelse straks ({SIZE_USD:,.0f} USDT, ud efter {HOLD_S // 3600} t, højst én "
            f"position pr. marked); stoppes ved tab ≥ {LOSS:.0%}, 24 t pause eller {MAX_AGE_S // 86400} dage")


def ensure(db, now):
    """Point 1: start both accounts once (idempotent: a key that was ever started is never started again)."""
    from lab import lane, moves
    if not db.one("SELECT 1 FROM observations WHERE detector=? LIMIT 1", moves.DETECTOR + "/1"):
        return []                                                # no move scanner on this database: nothing to trade
    have = {p.get("key") for p in lane.started(db).values()}
    out = []
    for key, (sign, name, function) in BOOKS.items():
        if key in have:
            continue
        led = lane.ledger_id(key)
        db.event("lane.started", ACTOR, led, {
            "key": key, "source": SOURCE, "name": name, "function": function, "params": {"direction": sign,
            "size_usd": SIZE_USD, "hold_s": HOLD_S}, "family": "straks", "coins": sorted(moves.WATCH),
            "expectation": None, "capital": CAPITAL, "t": int(now), "costs": COSTS.__dict__, "label": LABEL,
            "simulated": True, "decisional": False, "rule": RULE})
        out.append(led)
    return out


def retire_reason(db, ledger, info, now):
    """Point 5: loss, a long pause, age. No source, flat or edge rule."""
    from lab import lane
    st, risk = lane.stats(db, ledger, now, info), Risk(db, lambda: now)
    if now - info["ts"] >= MAX_AGE_S:
        return "expired", f"{MAX_AGE_S // 86400} dage efter start", st
    if st["equity"] is not None and st["equity"] <= CAPITAL * (1 - LOSS):
        return "loss", f"værdi {st['equity']:.2f} er mindst {LOSS:.0%} under startkapitalen", st
    age, rule = lane._paused_for(risk, ledger, now)
    if age is not None and age >= PAUSE_S:
        return "paused", f"på pause i {age / 3600:.0f} timer ({rule})", st
    return None, None, st


def direction(move):
    """Point 2: the sign of the flagged horizon's return (z_1h first, then z_24h, else the 1 h return)."""
    flags = move.get("flags") or []
    r = move.get("ret_24h") if ("z_1h" not in flags and "z_24h" in flags) else move.get("ret_1h")
    if r is None or r == 0:
        return 0
    return 1 if r > 0 else -1


def _entries(db, ledger):
    """{instrument: (entry ts, move id)} of the open positions, from this account's own entry orders."""
    out = {}
    for r in db.q("SELECT order_id, instrument, ts FROM sim_orders WHERE exp_id=? AND reduce_only=0 ORDER BY id", ledger):
        out[r["instrument"]] = (r["ts"], int(r["order_id"].split("|")[2]))
    return out


def run_one(db, ledger, info, get, now, cache=None, books=None):
    """One pass: book funding, close what has been held 24 h, open on new move records, mark once an hour."""
    from lab import paper_runner as pr
    sign = info["params"]["direction"]
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    eng.start(ledger, CAPITAL, COSTS, actor=ACTOR)
    if risk.fail_closed():
        return {"status": "fail_closed"}
    if risk.paused(ledger) and not risk.auto_resume(ledger, lambda: pr.fetch_book("BTCUSDT", now, get)):
        return pr.mark_only(db, ledger, get, now, books, cache)  # amendment 4 section 7: hold and mark, open nothing
    funded = pr.book_funding(db, eng, ledger, now, pr._cached_funding(get, now, cache))
    pos = eng.ledger(ledger)["positions"]
    entries, orders = _entries(db, ledger), []

    def book(inst):
        b = (books or {}).get(inst) or pr.fetch_book(inst, now, get)
        if books is not None:
            books[inst] = b
        risk.observe_book(ledger, b)
        return b

    for inst, q in pos.items():                                  # point 4: out after HOLD_S
        ts, mid = entries.get(inst, (0, 0))
        if now - ts < HOLD_S:
            continue
        try:
            b = book(inst)
        except Exception as e:                                   # noqa: BLE001 - the next pass retries
            orders.append({"instrument": inst, "status": f"exit not sent: {e!r}"[:120]})
            continue
        r = eng.submit_taker(ledger, f"{ledger}|exit|{mid}|{inst}", inst, "sell" if q > 0 else "buy", abs(q), b,
                             reduce_only=True, signal_ref=f"straks.exit@{mid}")
        orders.append({"instrument": inst, "status": r["status"], "exit": mid})
    pos = eng.ledger(ledger)["positions"]
    seen = {int(r["order_id"].split("|")[2]) for r in db.q("SELECT order_id FROM sim_orders WHERE exp_id=? AND "
                                                          "reduce_only=0", ledger)}
    skipped = {r[0] for r in db.q("SELECT json_extract(payload, '$.move_id') FROM events WHERE kind='straks.skipped' "
                                  "AND exp_id=?", ledger)}
    for r in db.q("SELECT id, ts, payload FROM events WHERE kind='opportunity.move' AND exp_id IS NULL AND ts>=? "
                  "AND ts<=? ORDER BY id", int(info["ts"]), int(now)):      # 41b: only records from before this pass
        if r["id"] in seen or r["id"] in skipped:
            continue
        m = json.loads(r["payload"])
        inst, s = m["instrument"], direction(m) * sign
        why = ("for gammel" if now - r["ts"] > FRESH_S else "ingen retning" if s == 0 else
               "åben position på markedet" if abs(pos.get(inst, 0.0)) > 1e-12 else None)
        if why:
            db.event("straks.skipped", ACTOR, ledger, {"move_id": r["id"], "instrument": inst, "reason": why,
                                                       "simulated": True, "rule": RULE})
            continue
        try:
            b = book(inst)
        except Exception as e:                                   # noqa: BLE001 - the next pass retries (same id)
            orders.append({"instrument": inst, "status": f"entry not sent: {e!r}"[:120]})
            continue
        if b.crossed():
            orders.append({"instrument": inst, "status": "entry not sent: invalid book"})
            continue
        res = eng.submit_taker(ledger, f"{ledger}|entry|{r['id']}|{inst}", inst, "buy" if s > 0 else "sell",
                               SIZE_USD / b.mid(), b, signal_ref=f"straks.entry@{r['id']}")
        orders.append({"instrument": inst, "status": res["status"], "move": r["id"], "side": s})
    try:
        marked = pr._mark_hourly(db, eng, ledger, get, now, books)
    except Exception as e:                                       # noqa: BLE001
        marked = f"no mark prices: {e!r}"[:120]
    rec = eng.reconcile(ledger)
    if not rec["ok"]:
        risk.trip_fail_closed("reconciliation", f"{ledger}: {rec['problems']}"[:500])
    return {"status": "ok", "orders": orders, "marked": marked, "funding": len(funded), "reconciled": rec["ok"]}
