"""Template approvals (ENGINE_PROPOSAL.md §3.2). A human approves a catalogue template once; instances of an approved
template may then be registered automatically. An approval is bound to the git blob of lab/engine/catalogue.py at
approval time: any later change to the catalogue invalidates every approval until it is approved again.

Approvals cover EXPLORATORY screening only (train + validation windows). Opening a holdout and starting paper trading
remain separate human lifecycle approvals.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time

from lab import lifecycle
from lab.db import canonical
from lab.engine import catalogue
from lab.registry import blob_at, last_commit

CATALOGUE = "lab/engine/catalogue.py"
APPROVAL_SECONDS = 15 * 60


class TemplateError(Exception):
    pass


def catalogue_blob():
    """Blob of the committed catalogue, or None if it has uncommitted changes."""
    if not lifecycle.git_committed(CATALOGUE):
        return None
    c = last_commit(CATALOGUE)
    return blob_at(c, CATALOGUE) if c else None


def request(db, template, actor, reason, now=None):
    if template not in catalogue.TEMPLATES:
        raise TemplateError(f"unknown template {template}")
    if not actor.startswith("human:"):
        raise TemplateError("template approvals come from a human actor")
    if not reason or len(reason) < 10:
        raise TemplateError("a reason of at least 10 characters is required")
    blob = catalogue_blob()
    if blob is None:
        raise TemplateError("lab/engine/catalogue.py must be committed before any template can be approved")
    now = int(now or time.time())
    code = secrets.token_hex(3)
    with db.tx():
        db.append("approvals", code_hash=hashlib.sha256(code.encode()).hexdigest(), exp_id=f"template:{template}",
                  to_state="TEMPLATE_APPROVED", ts=now, expires_ts=now + APPROVAL_SECONDS, actor=actor, reason=reason,
                  evidence={"catalogue_blob": blob, "protocol_version": catalogue.PROTOCOL_VERSION})
        db.event("template.approval_requested", actor, None, {"template": template, "reason": reason})
    return code


def confirm(db, code, actor, now=None):
    now = int(now or time.time())
    if not actor.startswith("human:"):
        raise TemplateError("only a human can confirm")
    a = db.one("SELECT * FROM approvals WHERE code_hash=? AND to_state='TEMPLATE_APPROVED'",
               hashlib.sha256(code.encode()).hexdigest())
    if a is None:
        raise TemplateError("unknown approval code")
    if now > a["expires_ts"]:
        raise TemplateError("approval code expired")
    if db.one("SELECT 1 FROM events WHERE kind='approval.used' AND payload=?", canonical({"approval_id": a["id"]})):
        raise TemplateError("approval code already used")
    ev = json.loads(a["evidence"])
    if ev["catalogue_blob"] != catalogue_blob():
        raise TemplateError("the catalogue changed since the approval was requested")
    template = a["exp_id"].split(":", 1)[1]
    with db.tx():
        eid = db.event("template.approved", actor, None, {"template": template, "catalogue_blob": ev["catalogue_blob"],
                                                          "protocol_version": ev["protocol_version"],
                                                          "approval_id": a["id"], "reason": a["reason"]})
        db.event("approval.used", actor, None, {"approval_id": a["id"]})
    return template, eid


def revoke(db, template, actor, reason):
    if not actor.startswith("human:"):
        raise TemplateError("only a human can revoke")
    db.event("template.revoked", actor, None, {"template": template, "reason": reason})


_UNSET = object()


def approval(db, template, blob=_UNSET):
    """The valid approval event row for a template, or None (revoked, never approved, or catalogue changed).
    Pass `blob` (from catalogue_blob()) when checking many templates: the git lookup is the slow part."""
    if blob is _UNSET:
        blob = catalogue_blob()
    for r in db.q("SELECT id, kind, payload FROM events WHERE kind IN ('template.approved','template.revoked') "
                  "ORDER BY id DESC"):
        p = json.loads(r["payload"])
        if p.get("template") != template:
            continue
        if r["kind"] == "template.revoked":
            return None
        return r["id"] if (blob is not None and p.get("catalogue_blob") == blob) else None
    return None


def register_transition(db, exp_id, template, actor):
    """DISCOVERED -> REGISTERED for an instance of an approved template (the only automatic registration path)."""
    if lifecycle.state(db, exp_id) != "DISCOVERED":
        raise lifecycle.LifecycleError(f"{exp_id} is not DISCOVERED")
    aid = approval(db, template)
    if aid is None:
        raise lifecycle.LifecycleError(f"template {template} has no valid human approval for the current catalogue")
    v = db.one("SELECT spec_json FROM experiments WHERE exp_id=? ORDER BY version DESC LIMIT 1", exp_id)
    spec = json.loads(v["spec_json"] or "{}")
    if spec.get("template") != template or any(not spec.get(k) for k in
                                                 ("hypothesis", "mechanism", "datasets", "methodology", "baseline",
                                                  "costs", "acceptance", "rejection", "alpha", "code", "seed")):
        raise lifecycle.LifecycleError("registration requires a complete template spec version")
    with db.tx():
        db.append("transitions", exp_id=exp_id, ts=int(time.time()), from_state="DISCOVERED", to_state="REGISTERED",
                  actor=actor, reason=f"instance of approved template {template}",
                  evidence={"template_approval_event": aid})
        db.event("lifecycle.transition", actor, exp_id, {"from": "DISCOVERED", "to": "REGISTERED",
                                                         "reason": f"approved template {template}"})
