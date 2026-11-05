"""Pairs book (research/PROTOCOL_V3.md amendment 43). SIMULATION ONLY: no exchange, no keys, no real money.

One lane account (source "pairs") trades four fixed proxy pairs of USD-M perps on the z-score of their hourly log
spread against its own trailing 720 hours: short the rich leg and long the cheap one at |z| >= 2, out at |z| <= 0.5,
at |z| >= 4 or after 72 hours. 1 000 USDT per leg, full costs, funding booked. Never evidence.
"""
from __future__ import annotations

import math
import statistics

from lab.paper import CostModel, PaperEngine
from lab.risk import Risk

SOURCE = "pairs"
KEY = "pairs|v1"
PAIRS = (("BZUSDT", "CLUSDT"), ("ETHUSDT", "BTCUSDT"), ("QQQUSDT", "SPYUSDT"), ("XAGUSDT", "XAUUSDT"))   # point 1
LABEL = "PAR-KONTO (marked mod proxy, simuleret, aldrig bevis)"
RULE = "research/PROTOCOL_V3.md amendment 43"
CAPITAL = 10_000.0
LEG_USD = 1_000.0                               # point 4
Z_IN, Z_OUT, Z_STOP = 2.0, 0.5, 4.0             # points 4-5
HIST, MIN_HIST = 720, 600                       # point 3
HOLD_S = 72 * 3600                              # point 5
MAX_BAR_AGE = 2 * 3600
COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.002)
HOUR = 3600
ACTOR = "system:lane"


def is_pairs(info):
    return (info or {}).get("source") == SOURCE


def rules_text():
    return (f"fire par mod proxy på z af log-spreadet ({HIST} t): ind ved |z| ≥ {Z_IN:g}, ud ved |z| ≤ {Z_OUT:g}, "
            f"|z| ≥ {Z_STOP:g} eller {HOLD_S // HOUR} t; {LEG_USD:,.0f} USDT pr. ben; stoppes ved tab ≥ 20 %, 24 t pause "
            f"eller 90 dage")


def ensure(db, now):
    """Point 2: start the account once, where the move scanner (and so the paper runner's perp data) runs."""
    from lab import lane, moves
    if not db.one("SELECT 1 FROM observations WHERE detector=? LIMIT 1", moves.DETECTOR + "/1"):
        return []
    if any(p.get("key") == KEY for p in lane.started(db).values()):
        return []
    led = lane.ledger_id(KEY)
    db.event("lane.started", ACTOR, led, {
        "key": KEY, "source": SOURCE, "name": "PAR-BOG", "function": "pair_z", "family": SOURCE,
        "params": {"pairs": [list(p) for p in PAIRS], "z_in": Z_IN, "z_out": Z_OUT, "z_stop": Z_STOP, "hist_h": HIST,
                   "hold_h": HOLD_S // HOUR, "leg_usd": LEG_USD},
        "coins": sorted({s for p in PAIRS for s in p}), "expectation": None, "capital": CAPITAL, "t": int(now),
        "costs": COSTS.__dict__, "label": LABEL, "simulated": True, "decisional": False, "rule": RULE})
    return [led]


def zscore(bars_a, bars_b, now):
    """Point 3: (z, bar open ts) of the latest common closed hour, or (None, reason)."""
    a = {t: c for t, _, c in bars_a}
    b = {t: c for t, _, c in bars_b}
    common = sorted(t for t in a if t in b and a[t] > 0 and b[t] > 0)
    if not common:
        return None, "ingen fælles timer"
    last = common[-1]
    if now - (last + HOUR) > MAX_BAR_AGE:
        return None, "data for gamle"
    s = [math.log(a[t]) - math.log(b[t]) for t in common]
    hist = s[-1 - HIST:-1]
    if len(hist) < MIN_HIST:
        return None, f"kun {len(hist)} fælles timer (< {MIN_HIST})"
    sd = statistics.pstdev(hist)
    if sd <= 0:
        return None, "spread uden variation"
    return (s[-1] - statistics.fmean(hist)) / sd, last


def _entry_ts(db, ledger, inst):
    r = db.one("SELECT MAX(ts) FROM sim_orders WHERE exp_id=? AND instrument=? AND reduce_only=0", ledger, inst)
    return r[0] if r else None


def run_one(db, ledger, info, get, now, cache=None, books=None):
    """One pass: funding, then per pair exit or entry on the latest closed hour, then the hourly mark."""
    from lab import paper_runner as pr
    eng, risk = PaperEngine(db, lambda: now), Risk(db, lambda: now)
    eng.start(ledger, CAPITAL, COSTS, actor=ACTOR)
    if risk.fail_closed():
        return {"status": "fail_closed"}
    if risk.paused(ledger) and not risk.auto_resume(ledger, lambda: pr.fetch_book("BTCUSDT", now, get)):
        return pr.mark_only(db, ledger, get, now, books, cache)
    funded = pr.book_funding(db, eng, ledger, now, pr._cached_funding(get, now, cache))
    hour, pos, out = int(now) // HOUR * HOUR, eng.ledger(ledger)["positions"], []
    for a, b in PAIRS:
        tag = f"{a}-{b}"
        try:
            z, at = zscore(pr.hourly(a, now, get, cache)[0], pr.hourly(b, now, get, cache)[0], now)
        except Exception as e:                                   # noqa: BLE001 - the next pass retries
            out.append({"pair": tag, "status": f"no bars: {e!r}"[:120]})
            continue
        qa, qb = pos.get(a, 0.0), pos.get(b, 0.0)
        held = abs(qa) > 1e-12 or abs(qb) > 1e-12
        if z is None:
            out.append({"pair": tag, "status": at, "held": held})
            if not held:
                continue
        if held:
            since = _entry_ts(db, ledger, a) or 0
            why = ("tid" if now - since >= HOLD_S else None) if z is None else (
                "normal" if abs(z) <= Z_OUT else "stop" if abs(z) >= Z_STOP else "tid" if now - since >= HOLD_S
                else None)
            if not why:
                out.append({"pair": tag, "status": "holder", "z": z})
                continue
            legs = [(s, q) for s, q in ((a, qa), (b, qb)) if abs(q) > 1e-12]
            side = lambda q: "sell" if q > 0 else "buy"                                  # noqa: E731
            reduce = True
        else:
            if abs(z) < Z_IN:
                out.append({"pair": tag, "status": "intet signal", "z": z})
                continue
            sa = -1 if z > 0 else 1                              # point 4: sell the rich leg, buy the cheap one
            legs, why, reduce = [(a, sa), (b, -sa)], "ind", False
            side = lambda q: "buy" if q > 0 else "sell"                                  # noqa: E731
        try:
            bk = {s: (books or {}).get(s) or pr.fetch_book(s, now, get) for s, _ in legs}
        except Exception as e:                                   # noqa: BLE001 - both legs or neither
            out.append({"pair": tag, "status": f"not sent: {e!r}"[:120]})
            continue
        if any(x.crossed() for x in bk.values()):
            out.append({"pair": tag, "status": "not sent: invalid book"})
            continue
        for s, x in bk.items():
            risk.observe_book(ledger, x)
            if books is not None:
                books[s] = x
        if not reduce:                                           # 43a: both legs fill fully after lot rounding
            from lab import lane, lots
            qty, why_not = {}, None
            for s, q in legs:
                st = lots.step((s,))
                if st is None:
                    why_not = f"BLOCKED: ukendt lot-størrelse for {s}"
                    break
                qty[s] = lots.round_down(LEG_USD / bk[s].mid(), st)
                if not lots.min_ok(s, qty[s], bk[s].mid()):
                    why_not = f"ikke sendt: {s} under minimumsnotional"
                elif lane.walk(bk[s], side(q), qty[s]) is None:
                    why_not = f"ikke sendt: bog for tynd ({s})"
                if why_not:
                    break
            if why_not:
                out.append({"pair": tag, "status": why_not, "z": z})
                continue
        for s, q in legs:
            qty_s = abs(q) if reduce else qty[s]
            r = eng.submit_taker(ledger, f"{ledger}|{'out' if reduce else 'in'}|{tag}|{hour}|{s}", s, side(q), qty_s,
                                 bk[s], reduce_only=reduce, signal_ref=f"pairs.{why}@{hour}:z={z}")
            out.append({"pair": tag, "instrument": s, "status": r["status"], "why": why, "z": z})
    try:
        marked = pr._mark_hourly(db, eng, ledger, get, now, books)
    except Exception as e:                                       # noqa: BLE001
        marked = f"no mark prices: {e!r}"[:120]
    rec = eng.reconcile(ledger)
    if not rec["ok"]:
        risk.trip_fail_closed("reconciliation", f"{ledger}: {rec['problems']}"[:500])
    return {"status": "ok", "pairs": out, "marked": marked, "funding": len(funded), "reconciled": rec["ok"]}
