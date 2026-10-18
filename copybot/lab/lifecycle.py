"""Lifecycle state machine (ENGINE_PROPOSAL.md §4). Promotions need a logged human approval; there is no live state."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import time

from lab.db import HERE, canonical

STATES = ("DISCOVERED", "SUPPRESSED", "REGISTERED", "WITHDRAWN", "SCREENING", "SCREEN_PASSED", "VALIDATION",
          "VALIDATED", "PAPER_TRADING", "PAUSED", "REJECTED", "RETIRED", "EXTERNAL",
          "OBSERVATION")   # research/PROTOCOL_V3.md amendment 2: forward test on new, unseen data
FINAL = {"REJECTED", "RETIRED", "WITHDRAWN"}

# (from, to) -> who may perform it. 'auto' = the engine (downward/sideways only); 'human' = approval code required.
EDGES = {
    ("DISCOVERED", "REGISTERED"): "human",
    ("DISCOVERED", "SUPPRESSED"): "auto",
    ("DISCOVERED", "WITHDRAWN"): "human",
    ("SUPPRESSED", "DISCOVERED"): "human",
    ("REGISTERED", "SCREENING"): "auto",
    ("REGISTERED", "WITHDRAWN"): "human",
    ("SCREENING", "REJECTED"): "auto",
    ("SCREENING", "SCREEN_PASSED"): "auto",
    ("SCREENING", "OBSERVATION"): "auto",            # passed everything except the luck check (amendment 2)
    ("OBSERVATION", "SCREEN_PASSED"): "auto",        # forward test passed
    ("OBSERVATION", "REJECTED"): "auto",             # forward test failed
    ("SCREEN_PASSED", "VALIDATION"): "human",
    ("SCREEN_PASSED", "REJECTED"): "human",
    ("VALIDATION", "REJECTED"): "auto",
    ("VALIDATION", "VALIDATED"): "auto",
    ("VALIDATED", "PAPER_TRADING"): "human",
    ("VALIDATED", "RETIRED"): "human",
    ("PAPER_TRADING", "PAUSED"): "auto",
    ("PAPER_TRADING", "REJECTED"): "auto",
    ("PAPER_TRADING", "RETIRED"): "human",
    ("PAUSED", "PAPER_TRADING"): "human",
    ("PAUSED", "REJECTED"): "auto",
    ("EXTERNAL", "REJECTED"): "human",
    ("EXTERNAL", "RETIRED"): "human",
}
APPROVAL_SECONDS = 15 * 60
NEEDS_COMMITTED_EVIDENCE = {("SCREEN_PASSED", "VALIDATION"), ("PAUSED", "PAPER_TRADING")}


class LifecycleError(Exception):
    pass


def state(db, exp_id):
    r = db.one("SELECT to_state FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", exp_id)
    return r[0] if r else None


def git_committed(path):
    """True if `path` (relative to copybot/) is tracked and has no uncommitted changes."""
    try:
        full = os.path.join(HERE, path)
        tracked = subprocess.check_output(["git", "ls-files", "--error-unmatch", full], cwd=HERE, text=True,
                                          stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", full], cwd=HERE, text=True).strip()
        return bool(tracked) and not dirty
    except Exception:
        return False


def _check(db, exp_id, to, kind, reason, evidence, guards):
    if to not in STATES:
        raise LifecycleError(f"unknown state {to}")
    cur = state(db, exp_id)
    if cur is None:
        raise LifecycleError(f"{exp_id} does not exist")
    if cur in FINAL:
        raise LifecycleError(f"{exp_id} is {cur} (final); a revived idea must be a new experiment")
    who = EDGES.get((cur, to))
    if who is None:
        raise LifecycleError(f"transition {cur} -> {to} is not allowed")
    if who != kind:
        raise LifecycleError(f"transition {cur} -> {to} requires a {who} actor, not {kind}")
    if not reason or len(reason.strip()) < 10:
        raise LifecycleError("a reason of at least 10 characters is required")
    if (cur, to) == ("SUPPRESSED", "DISCOVERED") and "materially different" not in reason.lower():
        raise LifecycleError("reviving a suppressed idea requires a 'materially different because ...' justification")
    if (cur, to) in NEEDS_COMMITTED_EVIDENCE:
        paths = (evidence or {}).get("committed_files") or []
        if not paths or not all(git_committed(p) for p in paths):
            raise LifecycleError(f"{cur} -> {to} requires committed evidence files (frozen parameters / revalidation)")
    for g in guards:
        g(db, exp_id, cur, to)
    return cur


def _do(db, exp_id, cur, to, actor, reason, evidence):
    db.append("transitions", exp_id=exp_id, ts=int(time.time()), from_state=cur, to_state=to, actor=actor,
              reason=reason, evidence=evidence or {})
    db.event("lifecycle.transition", actor, exp_id, {"from": cur, "to": to, "reason": reason})


POLICY_EDGES = {("SCREEN_PASSED", "VALIDATION"), ("VALIDATED", "PAPER_TRADING")}
POLICY_DECISION_TTL_S = 60                                            # amendment 4a: used at once, or decide again


def policy_transition(db, exp_id, to, actor, reason, evidence):
    """Amendment 4: lab/promotion.decide may take the two policy edges, citing an allowed decision event. Nothing else
    may call this (enforced by the actor and the cited decision)."""
    if actor != "system:promotion":
        raise LifecycleError("policy transitions are reserved for system:promotion")
    ev = evidence or {}
    with db.tx():
        cur = state(db, exp_id)
        if (cur, to) not in POLICY_EDGES:
            raise LifecycleError(f"{cur} -> {to} is not a policy edge")
        did = ev.get("decision_event_id")
        d = db.one("SELECT ts, actor, payload FROM events WHERE id=? AND kind='promotion.decision' AND exp_id=?",
                   did, exp_id)
        p = json.loads(d["payload"]) if d else {}
        if d is None or d["actor"] != actor or not p.get("allowed") or (p.get("from"), p.get("to")) != (cur, to):
            raise LifecycleError("a policy transition must cite an allowed promotion decision for this step")
        v = db.one("SELECT version, fingerprint FROM experiments WHERE exp_id=? ORDER BY version DESC LIMIT 1", exp_id)
        if (p.get("version"), p.get("fingerprint")) != (v["version"], v["fingerprint"]):
            raise LifecycleError("the promotion decision was made for another spec version")
        if time.time() - d["ts"] > POLICY_DECISION_TTL_S:
            raise LifecycleError("the promotion decision is too old; decide again")
        marker = json.dumps({"decision_event_id": did}, sort_keys=True, separators=(",", ":"))
        if db.one("SELECT 1 FROM events WHERE kind='promotion.used' AND exp_id=? AND payload=?", exp_id, marker):
            raise LifecycleError("the promotion decision was already used")
        _check(db, exp_id, to, "human", reason, ev, ())
        _do(db, exp_id, cur, to, actor, reason, ev)
        db.event("promotion.used", actor, exp_id, {"decision_event_id": did})


def auto_transition(db, exp_id, to, actor, reason, evidence=None, guards=()):
    """Engine-side transitions: only edges marked 'auto' (never a promotion past a human gate)."""
    if not actor.startswith("system:"):
        raise LifecycleError("automatic transitions must use a 'system:<worker>' actor")
    with db.tx():
        cur = _check(db, exp_id, to, "auto", reason, evidence, guards)
        _do(db, exp_id, cur, to, actor, reason, evidence)


def request_approval(db, exp_id, to, actor, reason, evidence=None, guards=(), now=None):
    """Step 1 of a human transition: validates it and returns a one-time code (valid 15 minutes)."""
    if not actor.startswith("human:"):
        raise LifecycleError("approvals must come from a 'human:<name>' actor")
    now = int(now or time.time())
    code = secrets.token_hex(3)
    with db.tx():
        _check(db, exp_id, to, "human", reason, evidence, guards)
        db.append("approvals", code_hash=hashlib.sha256(code.encode()).hexdigest(), exp_id=exp_id, to_state=to, ts=now,
                  expires_ts=now + APPROVAL_SECONDS, actor=actor, reason=reason, evidence=evidence or {})
        db.event("approval.requested", actor, exp_id, {"to": to, "reason": reason})
    return code


def confirm(db, code, actor, guards=(), now=None):
    """Step 2: executes the approved transition once, re-checking every guard."""
    now = int(now or time.time())
    h = hashlib.sha256(code.encode()).hexdigest()
    a = db.one("SELECT * FROM approvals WHERE code_hash=?", h)
    if a is None:
        raise LifecycleError("unknown approval code")
    if not actor.startswith("human:"):
        raise LifecycleError("only a 'human:<name>' actor can confirm an approval")
    if now > a["expires_ts"]:
        raise LifecycleError("approval code expired")
    used = db.one("SELECT 1 FROM events WHERE kind='approval.used' AND payload=?", canonical({"approval_id": a["id"]}))
    if used:
        raise LifecycleError("approval code already used")
    import json
    evidence = json.loads(a["evidence"]) if a["evidence"] else {}
    with db.tx():
        cur = _check(db, a["exp_id"], a["to_state"], "human", a["reason"], evidence, guards)
        _do(db, a["exp_id"], cur, a["to_state"], actor, a["reason"], {**evidence, "approval_id": a["id"]})
        db.event("approval.used", actor, a["exp_id"], {"approval_id": a["id"]})
    return a["exp_id"], a["to_state"]
