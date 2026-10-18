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
SCREEN_PASSES = ("PASS (screen)", "PASS (forward test)")
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


def _version(db, eid):
    r = registry.latest(db, eid)
    return {"version": r["version"], "fingerprint": r["fingerprint"]} if r else {}


def used_marker(did):
    return json.dumps({"decision_event_id": did}, sort_keys=True, separators=(",", ":"))


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
              ("registered under PROTOCOL v3 (amendment 4a)",
               bool(t in catalogue.TEMPLATES and catalogue.protocol_of(t) == 3), t),
              ("lab not FAIL_CLOSED", not Risk(db).fail_closed(), None),
              ("supervisor healthy", supervisor_ok(db, now), None)]
    if st == "SCREEN_PASSED":
        res = _latest(db, eid)
        return "VALIDATION", common + [
            ("latest result is a PASS (screen incl. luck check, or forward test)",
             bool(res and (res["verdict"] or "").startswith(SCREEN_PASSES)), res["id"] if res else None),
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
               "evidence": {g: d for g, ok, d in gates}, **_version(db, eid)}
    last = db.one("SELECT payload FROM events WHERE kind='promotion.decision' AND exp_id=? ORDER BY id DESC LIMIT 1",
                  eid)
    prev = json.loads(last["payload"]) if last else None
    if prev is None or (prev.get("allowed"), prev.get("closed"), prev.get("to"), prev.get("from")) != \
            (allowed, closed, to, payload["from"]) or allowed:
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


def _human_ok(db, eid, tr, ev):
    """Amendment 4a: a human entry cites its one-time approval (same experiment, same target, used once, same actor)."""
    aid = ev.get("approval_id")
    a = db.one("SELECT exp_id, to_state FROM approvals WHERE id=?", aid) if aid is not None else None
    if a is None or a["exp_id"] != eid or a["to_state"] != "PAPER_TRADING":
        return False, "human entry does not cite a matching approval code"
    used = db.q("SELECT actor FROM events WHERE kind='approval.used' AND exp_id=? AND payload=?", eid,
                json.dumps({"approval_id": aid}, sort_keys=True, separators=(",", ":")))
    if len(used) != 1 or used[0]["actor"] != tr["actor"]:
        return False, "approval code was not used exactly once by the approving human"
    return True, f"human approval #{aid}"


def _auto_ok(db, eid, tr, ev):
    """Amendment 4a: an automatic entry cites one allowed decision for this step and spec version, used once, a
    holdout PASS of this experiment, and the policy is still on (switching it off ends new exposure)."""
    did = ev.get("decision_event_id")
    d = db.one("SELECT actor, payload FROM events WHERE id=? AND kind='promotion.decision' AND exp_id=?", did, eid) \
        if did else None
    p = json.loads(d["payload"]) if d else {}
    if d is None or d["actor"] != ACTOR or not p.get("allowed") or (p.get("from"), p.get("to")) != \
            ("VALIDATED", "PAPER_TRADING") or tr["from_state"] != "VALIDATED":
        return False, "cited promotion decision missing, not allowed or for another step"
    if {k: p.get(k) for k in ("version", "fingerprint")} != _version(db, eid):
        return False, "promotion decision was made for another spec version"
    if db.one("SELECT COUNT(*) FROM events WHERE kind='promotion.used' AND exp_id=? AND payload=?", eid,
              used_marker(did))[0] != 1:
        return False, "promotion decision was not used exactly once"
    r = db.one("SELECT verdict FROM results WHERE id=? AND exp_id=? AND label='VALIDATION'", ev.get("result_id"), eid)
    if r is None or not (r["verdict"] or "").startswith("PASS (holdout)"):
        return False, "cited result is not this experiment's holdout PASS"
    if not policy(db)["on"]:
        return False, "automatic promotion policy is off (approval expired)"
    return True, f"automatic promotion decision #{did}"


def trading_authorized(db, eid):
    """Approved paper trading may open positions only if its current PAPER_TRADING entry is verifiable."""
    st = lifecycle.state(db, eid)
    if st != "PAPER_TRADING":
        return False, f"{eid} is {st}"
    tr = db.one("SELECT actor, from_state, to_state, evidence FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1",
                eid)
    ev = json.loads(tr["evidence"] or "{}")
    if tr["actor"].startswith("human:"):
        return _human_ok(db, eid, tr, ev)
    if tr["actor"] == ACTOR:
        return _auto_ok(db, eid, tr, ev)
    return False, f"PAPER_TRADING entry by {tr['actor']} is not a verifiable approval"


def exposure_allowed(db, ledger, now=None):
    """Amendment 4a: the one check for new exposure, called by the engine's risk gate for every non-reducing order."""
    if not supervisor_ok(db, now):
        return False, "supervisor heartbeat missing or stale: no new exposure"
    if ledger.startswith(("SHADOW_", "FWD_")):
        return True, "simulated ledger (checked by the shadow / forward-test rule)"
    return trading_authorized(db, ledger)
