"""Director order 48 P0: verifiable owner approval (design + synthetic tests; not wired into the lab).

Problem (order 47 P3): all 30 lab template approvals carry actor `human:anton`, but the assistant executed them (6 say
"Approved by Claude", 24 cite a general "User instruction"). A label or a general instruction cannot prove that the
owner approved a specific template. Those 30 keep their results and get documentation status UNVERIFIED_ORIGIN.

Mechanism: the owner signs ONE canonical approval statement per template version with an SSH signing key that the
assistant cannot use, and the factory verifies it with `ssh-keygen -Y verify`.

- Statement (canonical JSON): scope "template", template id, the exact git blob of the template's code/catalogue,
  the protocol version, a fresh nonce, issued/expiry times, and the owner's own words. Generic scopes ("all", "*",
  "everything") are refused.
- Signature: `ssh-keygen -Y sign -n copybot-approval` by a key listed for principal `owner` in an allowed_signers file
  kept in the repo (public keys only). The private key must live where processes on this host cannot use it: a key on
  another device, or a passphrase-protected key whose passphrase the assistant never receives (the assistant never
  enters passwords). The owner's existing ~/.ssh/id_ed25519 on this host must NOT be used: anything running as the
  same user can read it.
- Verification (`verify`): signature valid for principal `owner` and namespace `copybot-approval`; statement fields
  match the template version being approved (blob, protocol); not expired; nonce never seen (replay); no delegation
  markers in the owner's words; scope specific. Every decision, accepted or refused, goes into an append-only,
  hash-chained audit log.
- Legacy: approvals without such a signature get UNVERIFIED_ORIGIN; they are never upgraded or rewritten.

What it cannot do: it cannot stop someone who holds the private key and its passphrase; it only proves that the holder
of the owner's key signed this exact statement. Revocation is by removing the public key from allowed_signers.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile

NAMESPACE = "copybot-approval"
PRINCIPAL = "owner"
GENERIC = {"all", "*", "everything", "alt", "any"}
DELEGATION = ("claude", "chatgpt", "codex", "ai assistant", "on behalf", "på vegne", "user instruction",
              "brugerens instruks", "du må gøre alt", "gør alt")


class ApprovalError(Exception):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def statement(template, blob, protocol, nonce, issued, expires, words):
    return {"scope": "template", "template": template, "blob": blob, "protocol": protocol, "nonce": nonce,
            "issued": issued, "expires": expires, "owner_words": words, "namespace": NAMESPACE}


def _run(args, data=None):
    return subprocess.run(args, input=data, capture_output=True, timeout=30)


def sign(stmt, key_path):
    """Owner side (tests use throwaway keys). Returns the armored signature."""
    with tempfile.TemporaryDirectory() as d:
        msg = os.path.join(d, "stmt.json")
        with open(msg, "w", encoding="utf-8") as f:
            f.write(canonical(stmt))
        r = _run(["ssh-keygen", "-q", "-Y", "sign", "-f", key_path, "-n", NAMESPACE, msg])
        if r.returncode:
            raise ApprovalError(r.stderr.decode(errors="replace").strip())
        with open(msg + ".sig", encoding="utf-8") as f:
            return f.read()


def signature_ok(stmt, sig, allowed_signers):
    with tempfile.TemporaryDirectory() as d:
        s = os.path.join(d, "sig")
        with open(s, "w", encoding="utf-8") as f:
            f.write(sig)
        r = _run(["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", PRINCIPAL, "-n", NAMESPACE, "-s", s],
                 canonical(stmt).encode())
        return r.returncode == 0


class AuditLog:
    """Append-only, hash-chained log of every approval decision."""

    def __init__(self, path=None):
        self.path, self.entries = path, []
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.entries = [json.loads(line) for line in f if line.strip()]
        self.verify()

    def verify(self):
        prev = "0" * 64
        for i, e in enumerate(self.entries):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev") != prev or hashlib.sha256(canonical(body).encode()).hexdigest() != e.get("hash"):
                raise ApprovalError(f"audit log broken at entry {i}")
            prev = e["hash"]
        return True

    def nonces_accepted(self):
        return {e["nonce"] for e in self.entries if e.get("decision") == "ACCEPTED"}

    def append(self, **row):
        e = {**row, "prev": self.entries[-1]["hash"] if self.entries else "0" * 64}
        e["hash"] = hashlib.sha256(canonical(e).encode()).hexdigest()
        self.entries.append(e)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(canonical(e) + "\n")
        return e


def verify(stmt, sig, allowed_signers, expected_blob, expected_protocol, now, log):
    """Return ("ACCEPTED", []) or ("REFUSED", reasons); the decision is logged either way. Fail-closed."""
    reasons = []
    try:
        log.verify()
    except ApprovalError as e:
        return "REFUSED", [str(e)]                    # a broken log cannot record anything; nothing is accepted
    try:
        if not isinstance(stmt, dict) or stmt.get("scope") != "template":
            reasons.append("scope must be 'template'")
        if str(stmt.get("template", "")).strip().lower() in GENERIC or not stmt.get("template"):
            reasons.append("generic or missing template: a general instruction is never a specific approval")
        if stmt.get("namespace") != NAMESPACE:
            reasons.append("wrong namespace")
        if stmt.get("blob") != expected_blob:
            reasons.append("statement is for another template version (blob)")
        if stmt.get("protocol") != expected_protocol:
            reasons.append("statement is for another protocol version")
        if not (stmt.get("issued", 0) <= now < stmt.get("expires", 0)):
            reasons.append("expired or not yet valid")
        if stmt.get("expires", 0) - stmt.get("issued", 0) > 7 * 86400:
            reasons.append("validity longer than 7 days")
        if not stmt.get("nonce") or stmt.get("nonce") in log.nonces_accepted():
            reasons.append("nonce missing or already used (replay)")
        words = str(stmt.get("owner_words", "")).lower()
        if any(m in words for m in DELEGATION):
            reasons.append("delegation in the owner's words: an AI or a general instruction cannot approve")
        if not sig or not signature_ok(stmt, sig, allowed_signers):
            reasons.append("signature not valid for principal 'owner'")
    except Exception as e:                            # noqa: BLE001 - anything unexpected refuses
        reasons.append(f"error: {e}")
    decision = "REFUSED" if reasons else "ACCEPTED"
    log.append(ts=now, decision=decision, template=stmt.get("template") if isinstance(stmt, dict) else None,
               blob=stmt.get("blob") if isinstance(stmt, dict) else None,
               nonce=stmt.get("nonce") if isinstance(stmt, dict) else None, reasons=reasons,
               statement_sha256=hashlib.sha256(canonical(stmt).encode()).hexdigest() if isinstance(stmt, dict) else None)
    return decision, reasons


def legacy_status(_approval_reason):
    """Documentation status of an existing lab approval (none carries an owner signature): always UNVERIFIED_ORIGIN.
    A legacy approval is never upgraded; a verified approval must be obtained anew through `verify`."""
    return "UNVERIFIED_ORIGIN"
