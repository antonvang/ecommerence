"""Experiment registry: discovery with graveyard deduplication, versioned specs, results that can only be superseded."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time

from lab.db import HERE
from lab.lifecycle import FINAL, LifecycleError, git_committed, state

REQUIRED_SPEC = ("hypothesis", "mechanism", "sources", "datasets", "methodology", "baseline", "costs",
                 "acceptance", "rejection", "alpha", "code")
EDITABLE_STATES = {"DISCOVERED", "REGISTERED"}       # specs are frozen once any evaluation data may be accessed
LABELS = ("EXPLORATORY", "VALIDATION", "PAPER", "LEGACY", "EXTERNAL")


class RegistryError(Exception):
    pass


def fingerprint(mechanism_tag, instrument, horizon, execution):
    return hashlib.sha256("|".join((mechanism_tag, instrument, horizon, execution)).encode()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=HERE, text=True, stderr=subprocess.DEVNULL).strip()


def blob_at(commit, path):
    """Git blob hash of `path` (relative to copybot/) at `commit`, or None."""
    try:
        return git("rev-parse", f"{commit}:copybot/{path}")
    except Exception:
        return None


def last_commit(path):
    try:
        return git("log", "-1", "--format=%H", "--", os.path.join(HERE, path)) or None
    except Exception:
        return None


def graveyard(db, mechanism_tag, execution, fp, exclude=()):
    """Rejected or withdrawn experiments with the same fingerprint, or the same mechanism and execution style.
    `exclude`: ids that never count (a family's own members, amendment 8 point 6)."""
    hits = []
    for r in db.q("SELECT exp_id, mechanism_tag, fingerprint, spec_json FROM experiments e WHERE version="
                  "(SELECT MAX(version) FROM experiments WHERE exp_id=e.exp_id)"):
        if r["exp_id"] in exclude or state(db, r["exp_id"]) not in ("REJECTED", "WITHDRAWN"):
            continue
        spec = json.loads(r["spec_json"] or "{}")
        if r["fingerprint"] == fp or (r["mechanism_tag"] == mechanism_tag and spec.get("execution") == execution):
            hits.append(r["exp_id"])
    return hits


def graveyard_related(db, tags, execution=None, exclude=()):
    """Rejected or withdrawn experiments whose mechanism tag is one of `tags` (a tag and its related tags from
    research/families/VOCABULARY.json, amendment 8 point 6); with `execution`, only that execution style."""
    hits = []
    for r in db.q("SELECT exp_id, mechanism_tag, spec_json FROM experiments e WHERE version="
                  "(SELECT MAX(version) FROM experiments WHERE exp_id=e.exp_id)"):
        if r["exp_id"] in exclude or r["mechanism_tag"] not in tags or \
                state(db, r["exp_id"]) not in ("REJECTED", "WITHDRAWN"):
            continue
        if execution is None or json.loads(r["spec_json"] or "{}").get("execution") == execution:
            hits.append(r["exp_id"])
    return hits


def covering(db, mechanism_tag, execution, fp, exclude=()):
    """Non-final experiments (incl. EXTERNAL) that already study this fingerprint or mechanism + execution."""
    hits = []
    for r in db.q("SELECT exp_id, mechanism_tag, fingerprint, spec_json FROM experiments e WHERE version="
                  "(SELECT MAX(version) FROM experiments WHERE exp_id=e.exp_id)"):
        if r["exp_id"] in exclude or state(db, r["exp_id"]) in FINAL or state(db, r["exp_id"]) in ("SUPPRESSED", None):
            continue
        spec = json.loads(r["spec_json"] or "{}")
        if r["fingerprint"] == fp or (r["mechanism_tag"] == mechanism_tag and spec.get("execution") == execution):
            hits.append(r["exp_id"])
    return hits


def _family_reserved(exp_id):
    from lab import families
    return families.reserved_id(exp_id)


def _family_instance(db, exp_id):
    from lab import families
    return families.is_instance(db, exp_id)


def discover(db, exp_id, hypothesis, mechanism_tag, instrument, horizon, execution, source, actor, extra=None,
             exclude=(), family_instance=False):
    """Create a DISCOVERED candidate, or SUPPRESSED if it matches the graveyard. Never evaluates profitability.
    Amendment 8 family instance ids (and ids with ':') are created only by families.discover_all (family_instance)."""
    if not family_instance and _family_reserved(exp_id):
        raise RegistryError(f"{exp_id}: ids of amendment 8 family instances (E_<fid>__<inst>_a8, anything ending in "
                            "_a8) and ids with ':' are reserved; the discovery agent proposes family instances from a "
                            "committed family file (amendment 8 point 6)")
    if db.one("SELECT 1 FROM experiments WHERE exp_id=?", exp_id):
        raise RegistryError(f"{exp_id} already exists")
    fp = fingerprint(mechanism_tag, instrument, horizon, execution)
    spec = {"hypothesis": hypothesis, "instrument": instrument, "horizon": horizon, "execution": execution,
            "sources": [source], **(extra or {})}
    dup = graveyard(db, mechanism_tag, execution, fp, exclude)
    with db.tx():
        db.append("experiments", exp_id=exp_id, version=1, created_ts=int(time.time()), mechanism_tag=mechanism_tag,
                  fingerprint=fp, spec_json=spec, note="discovered")
        db.append("transitions", exp_id=exp_id, ts=int(time.time()), from_state=None, to_state="DISCOVERED",
                  actor=actor, reason=f"discovered from {source}", evidence={"source": source})
        db.event("candidate.discovered", actor, exp_id, {"fingerprint": fp, "source": source})
        if dup:
            db.append("transitions", exp_id=exp_id, ts=int(time.time()), from_state="DISCOVERED",
                      to_state="SUPPRESSED", actor="system:graveyard",
                      reason=f"matches rejected experiment(s) {', '.join(dup)}", evidence={"matches": dup})
            db.event("candidate.suppressed", "system:graveyard", exp_id, {"matches": dup})
    return ("SUPPRESSED", dup) if dup else ("DISCOVERED", [])


def latest(db, exp_id):
    return db.one("SELECT * FROM experiments WHERE exp_id=? ORDER BY version DESC LIMIT 1", exp_id)


def add_version(db, exp_id, spec_path, actor):
    """Attach a complete spec (a committed JSON file). Refused once the experiment has left DISCOVERED/REGISTERED."""
    cur = state(db, exp_id)
    if cur is None:
        raise RegistryError(f"{exp_id} does not exist")
    prev = latest(db, exp_id)
    if _family_reserved(exp_id) or (prev and json.loads(prev["spec_json"] or "{}").get("family")):
        raise RegistryError(f"{exp_id} is an amendment 8 family instance (or a reserved id): its spec version 2 is "
                            "built from the approved family file at registration, never added by hand (amendment 8 "
                            "point 7)")
    if cur not in EDITABLE_STATES:
        raise RegistryError(f"{exp_id} is {cur}: its spec can no longer change; register a new experiment instead")
    if not git_committed(spec_path):
        raise RegistryError(f"{spec_path} must be committed (tracked, no local changes) before registration")
    with open(os.path.join(HERE, spec_path), encoding="utf-8") as f:
        spec = json.load(f)
    missing = [k for k in REQUIRED_SPEC if not spec.get(k)]
    if missing:
        raise RegistryError(f"spec is missing: {', '.join(missing)}")
    if not git_committed(spec["code"]):
        raise RegistryError(f"code {spec['code']} must be committed before registration")
    prev = latest(db, exp_id)
    commit = last_commit(spec_path)
    with db.tx():
        db.append("experiments", exp_id=exp_id, version=prev["version"] + 1, created_ts=int(time.time()),
                  mechanism_tag=spec.get("mechanism_tag") or prev["mechanism_tag"],
                  fingerprint=fingerprint(spec.get("mechanism_tag") or prev["mechanism_tag"], spec.get("instrument", ""),
                                          spec.get("horizon", ""), spec.get("execution", "")),
                  spec_json=spec, spec_path=spec_path, spec_commit=commit, code_hash=blob_at(commit, spec["code"])
                  or blob_at(last_commit(spec["code"]), spec["code"]), note=f"spec from {spec_path}")
        db.append("alpha_ledger", exp_id=exp_id, ts=int(time.time()), alpha=float(spec["alpha"]),
                  note=f"version {prev['version'] + 1}")
        db.event("exp.version_added", actor, exp_id, {"version": prev["version"] + 1, "spec_path": spec_path,
                                                      "spec_commit": commit})
    return prev["version"] + 1


def complete_spec_guard(db, exp_id, cur, to):
    """Guard for DISCOVERED -> REGISTERED: the latest version must carry a complete, committed spec."""
    if (cur, to) != ("DISCOVERED", "REGISTERED"):
        return
    v = latest(db, exp_id)
    spec = json.loads(v["spec_json"] or "{}")
    if not v["spec_path"] or any(not spec.get(k) for k in REQUIRED_SPEC):
        raise LifecycleError("registration requires a complete spec version (lab add-version)")
    if blob_at(v["spec_commit"], v["spec_path"]) is None:
        raise LifecycleError("the spec file is not present at its recorded commit")


def record_result(db, exp_id, label, verdict, metrics, evidence, actor, supersedes=None, reason=None):
    """Append a result. An earlier result is never changed; a correction supersedes it with a reason, both stay."""
    if label not in LABELS:
        raise RegistryError(f"label must be one of {LABELS}")
    if state(db, exp_id) is None:
        raise RegistryError(f"{exp_id} does not exist")
    if not actor.startswith("system:") and _family_instance(db, exp_id):
        raise RegistryError(f"{exp_id} is an amendment 8 family instance: its results are recorded only by its steps "
                            "(screen, forward test, holdout), never typed with lab result (amendment 8 points 8, 11 "
                            "and 12)")
    if supersedes is not None:
        old = db.one("SELECT exp_id FROM results WHERE id=?", supersedes)
        if old is None or old["exp_id"] != exp_id:
            raise RegistryError("superseded result not found for this experiment")
        if not reason or len(reason) < 10:
            raise RegistryError("superseding a result requires a reason")
    v = latest(db, exp_id)
    with db.tx():
        rid = db.append("results", exp_id=exp_id, version=v["version"], ts=int(time.time()), label=label,
                        verdict=verdict, metrics=metrics or {}, evidence=evidence or {}, supersedes=supersedes)
        db.event("result.recorded", actor, exp_id, {"result_id": rid, "label": label, "verdict": verdict,
                                                    "supersedes": supersedes, "reason": reason})
    return rid


def status(db):
    out = []
    for r in db.q("SELECT exp_id, version, mechanism_tag FROM experiments e WHERE version="
                  "(SELECT MAX(version) FROM experiments WHERE exp_id=e.exp_id) ORDER BY exp_id"):
        res = db.one("SELECT label, verdict FROM results WHERE exp_id=? AND id NOT IN "
                     "(SELECT supersedes FROM results WHERE supersedes IS NOT NULL) ORDER BY id DESC LIMIT 1", r["exp_id"])
        out.append({"exp_id": r["exp_id"], "version": r["version"], "mechanism": r["mechanism_tag"],
                    "state": state(db, r["exp_id"]), "final": state(db, r["exp_id"]) in FINAL,
                    "label": res["label"] if res else None, "verdict": res["verdict"] if res else None})
    return out


GATE_EDGES = {("SCREENING", "SCREEN_PASSED"), ("SCREENING", "REJECTED"), ("VALIDATION", "VALIDATED"),
              ("VALIDATION", "REJECTED"), ("PAPER_TRADING", "REJECTED"), ("PAUSED", "REJECTED"),
              ("SCREENING", "OBSERVATION"), ("OBSERVATION", "SCREEN_PASSED"), ("OBSERVATION", "REJECTED")}


def make_result_guard(evidence):
    """Gate outcomes must cite a recorded result of the same experiment; a pass must cite a PASS verdict. A family
    instance's gate edges also pass families.gate_problem (amendment 8 points 8, 11 and 12)."""
    def guard(db, exp_id, cur, to):
        if (cur, to) not in GATE_EDGES:
            return
        rid = (evidence or {}).get("result_id")
        r = db.one("SELECT exp_id, verdict FROM results WHERE id=?", rid) if rid is not None else None
        if r is None or r["exp_id"] != exp_id:
            raise LifecycleError(f"{cur} -> {to} must cite a recorded result of {exp_id} (evidence.result_id)")
        passed = (r["verdict"] or "").upper().startswith("PASS")
        if to in ("SCREEN_PASSED", "VALIDATED") and not passed:
            raise LifecycleError("a pass transition must cite a result whose verdict starts with PASS")
        if to == "REJECTED" and passed:
            raise LifecycleError("a rejection cannot cite a PASS result")
        if to == "OBSERVATION" and not (r["verdict"] or "").upper().startswith("OBSERVE"):
            raise LifecycleError("entering OBSERVATION must cite a result whose verdict starts with OBSERVE")
        if _family_instance(db, exp_id):
            from lab import families
            why = families.gate_problem(db, exp_id, cur, to, rid)
            if why:
                raise LifecycleError(why)
    return guard
