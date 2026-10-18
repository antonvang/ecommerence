"""Automatic promotion (research/PROTOCOL_V3.md amendment 4): the single decision function for the two steps that used
to need a human click per strategy:

    SCREEN_PASSED -> VALIDATION      (opens the sealed 2024 holdout, once)
    VALIDATED     -> PAPER_TRADING   (starts approved paper trading; simulated only)

It only acts while a human-enabled `policy.autopromote` is on. It never changes a threshold: every check reads the
recorded result of an existing gate. A closed gate means "wait", recorded with its reason. Shadow ledgers are never
read here. Nothing in this module can place an order; the paper runner asks `trading_authorized` before every entry.
"""
from __future__ import annotations

import json
import time

from lab import control, lifecycle, registry
from lab.risk import Risk

POLICY = "policy.autopromote"
ACTOR = "system:promotion"
SPEC = "research/PROTOCOL_V3.md"
SUPERVISOR_FRESH_S = 30
LIVE_UNSUPPORTED = {"metrics", "dvol", "stable", "taker", "rates"}     # paper runner has no live feed for these yet


def policy(db):
    r = db.one("SELECT id, actor, payload FROM events WHERE kind=? ORDER BY id DESC LIMIT 1", POLICY)
    if r is None:
        return {"on": False, "event_id": None}
    p = json.loads(r["payload"])
    return {"on": bool(p.get("on")) and r["actor"].startswith("human:"), "event_id": r["id"], "actor": r["actor"]}


def set_policy(db, on, actor, reason):
    if not actor.startswith("human:"):
        raise lifecycle.LifecycleError("only a human can switch automatic promotion")
    if not reason or len(reason.strip()) < 10:
        raise lifecycle.LifecycleError("a reason of at least 10 characters is required")
    if policy(db)["on"] == bool(on):
        return False
    db.event(POLICY, actor, None, {"on": bool(on), "reason": reason})
    return True


def supervisor_ok(db, now=None):
    r = db.one("SELECT ts, status FROM heartbeats WHERE worker='supervisor'")
    return bool(r and r["status"] == "running" and (now or time.time()) - r["ts"] <= SUPERVISOR_FRESH_S)


def _template(db, eid):
    return (json.loads(registry.latest(db, eid)["spec_json"] or "{}")).get("template")


def _latest(db, eid, label=None):
    q = "SELECT id, label, verdict FROM results WHERE exp_id=?" + (" AND label=?" if label else "")
    return db.one(q + " ORDER BY id DESC LIMIT 1", *((eid, label) if label else (eid,)))


def _ledgers_reconcile(db):
    from lab.paper import PaperEngine
    eng = PaperEngine(db)
    for r in db.q("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started'"):
        if not eng.reconcile(r[0])["ok"]:
            return False
    return True


def checks(db, eid, now=None):
    """(target state, [(gate, ok, detail)]) for an experiment that is waiting on an automatic step, else (None, [])."""
    from lab.engine import catalogue
    from lab.pipeline import NO_CLEAN_HOLDOUT
    st = lifecycle.state(db, eid)
    t = _template(db, eid)
    common = [("catalogue experiment (pre-registered template)", bool(eid.startswith("E_") and t in catalogue.TEMPLATES), t),
              ("lab not FAIL_CLOSED", not Risk(db).fail_closed(), None),
              ("supervisor healthy", supervisor_ok(db, now), None)]
    if st == "SCREEN_PASSED":
        res = _latest(db, eid)
        return "VALIDATION", common + [
            ("latest result is a PASS (screen incl. luck check, or forward test)",
             bool(res and (res["verdict"] or "").upper().startswith("PASS")), res["id"] if res else None),
            ("a clean 2024 holdout is possible (amendment 1)", t not in NO_CLEAN_HOLDOUT, t)]
    if st == "VALIDATED":
        res = _latest(db, eid, "VALIDATION")
        needs = set((catalogue.TEMPLATES.get(t) or {}).get("needs") or [])
        return "PAPER_TRADING", common + [
            ("holdout PASS recorded", bool(res and (res["verdict"] or "").startswith("PASS (holdout)")),
             res["id"] if res else None),
            ("paper runner has live data for this template", not (needs & LIVE_UNSUPPORTED), sorted(needs)),
            ("resources ok", control.resources()["ok"], None),
            ("all paper ledgers reconcile", _ledgers_reconcile(db), None)]
    return None, []


def decide(db, eid, now=None, execute=True):
    """The single place that may promote. Records every changed decision; promotes only when every gate is open."""
    to, gates = checks(db, eid, now)
    if to is None:
        return {"exp_id": eid, "applicable": False}
    pol = policy(db)
    gates = gates + [("automatic promotion policy on (human-enabled)", pol["on"], pol["event_id"])]
    closed = [g for g, ok, _ in gates if not ok]
    allowed = not closed
    payload = {"from": lifecycle.state(db, eid), "to": to, "allowed": allowed, "closed": closed,
               "evidence": {g: d for g, ok, d in gates}}
    last = db.one("SELECT payload FROM events WHERE kind='promotion.decision' AND exp_id=? ORDER BY id DESC LIMIT 1",
                  eid)
    prev = json.loads(last["payload"]) if last else None
    if prev is None or (prev.get("allowed"), prev.get("closed"), prev.get("to")) != (allowed, closed, to) or allowed:
        dec = db.event("promotion.decision", ACTOR, eid, payload)
    else:
        dec = None                                           # unchanged "waiting" decision: not logged again
    if allowed and execute:
        res = (_latest(db, eid) if to == "VALIDATION" else _latest(db, eid, "VALIDATION"))
        lifecycle.policy_transition(db, eid, to, ACTOR, f"automatic promotion: every gate open (decision #{dec})",
                                    {"decision_event_id": dec, "policy_event_id": pol["event_id"],
                                     "result_id": res["id"], "committed_files": [SPEC]})
    return {"exp_id": eid, "applicable": True, "to": to, "allowed": allowed, "closed": closed, "decision_event": dec}


def step(db, now=None):
    out = []
    for x in registry.status(db):
        if x["state"] in ("SCREEN_PASSED", "VALIDATED") and x["exp_id"].startswith("E_"):
            out.append(decide(db, x["exp_id"], now))
    return out


def trading_authorized(db, eid):
    """Approved paper trading may open positions only if its PAPER_TRADING entry is verifiable: a human approval, or
    an allowed decision of this module citing an active policy."""
    if lifecycle.state(db, eid) != "PAPER_TRADING":
        return False, f"{eid} is {lifecycle.state(db, eid)}"
    tr = db.one("SELECT actor, evidence FROM transitions WHERE exp_id=? AND to_state='PAPER_TRADING' ORDER BY id DESC "
                "LIMIT 1", eid)
    if tr is None:
        return False, "no PAPER_TRADING transition"
    if tr["actor"].startswith("human:"):
        return True, "human approval"
    ev = json.loads(tr["evidence"] or "{}")
    if tr["actor"] != ACTOR or not ev.get("decision_event_id"):
        return False, f"PAPER_TRADING entry by {tr['actor']} is not a verifiable approval"
    d = db.one("SELECT actor, payload FROM events WHERE id=? AND kind='promotion.decision' AND exp_id=?",
               ev["decision_event_id"], eid)
    if d is None or d["actor"] != ACTOR or not json.loads(d["payload"]).get("allowed"):
        return False, "cited promotion decision missing or not allowed"
    return True, f"automatic promotion decision #{ev['decision_event_id']}"
