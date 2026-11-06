"""Director order 49 P1: the five security components of the research factory, built and tested in ISOLATION
(synthetic data, throwaway test keys; nothing is wired into the lab and no owner key is generated, read or used).

1. Owner key binding (`KeyRegistry`): the set of keys that may sign approvals is DERIVED from a signed registry, never
   read from an allowed_signers file. The first (root) key is accepted only if its fingerprint equals an external
   trust anchor that the owner publishes and the assistant cannot write (e.g. the owner's GitHub account keys or a
   fingerprint the owner reads out and pins outside this host). Every later key addition or revocation must be signed
   by a key that is valid at that point (namespace copybot-keyreg). Editing allowed_signers therefore grants nothing.
2. Rollback-proof audit checkpoint (`checkpoint_*`): the owner (or an off-host witness key) signs a statement
   {log id, length, head hash, time} (namespace copybot-checkpoint). A log is accepted only if it EXTENDS the latest
   signed checkpoint: same hash at position length-1 and at least that length. Replacing the log with an older valid
   version, truncating it or forking it is detected. A checkpoint committed by the assistant to the same repository
   is not enough; the signature must come from a key the assistant cannot use.
3. Immutable legacy identity (`LegacyManifest`): the legacy exemption is the exact set of (exp_id, spec_commit,
   protocol_version) triples from migration v1, pinned by its sha256 in a signed statement. A new experiment that
   reuses an old exp_id with another commit or protocol is not exempt; an altered manifest exempts nothing.
4. Verifiable data identity (`DataLock`): per file the lock records the checksum, its source (URL of the host's own
   checksum file), when it was fetched and when the lock was made. At access the file's sha256 must equal the locked
   checksum, and the lock must precede the access. A checksum from the same host as the data proves integrity, not
   that the file was unchanged at lock time; without an independent historical witness the result carries the
   limitation `CHECKSUM_SAME_SOURCE`.
5. Point-in-time universe (`UniverseRule`): the universe is a rule fixed before data (listed before the window start,
   minimum history, delisted symbols included) applied to an archive index (symbol -> first/last date). The derived
   list and the index are hashed at the lock. A list derived from an index fetched after the lock is labelled
   RECONSTRUCTED and never presented as the locked universe; a changed index or rule fails the check.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile

NS_KEYREG, NS_CHECKPOINT = "copybot-keyreg", "copybot-checkpoint"
PRINCIPAL = "owner"


class SecurityError(Exception):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


# ---------------------------------------------------------------- ssh signature helpers (test keys only)

def ssh_sign(obj, key_path, namespace):
    with tempfile.TemporaryDirectory() as d:
        msg = os.path.join(d, "m")
        with open(msg, "w", encoding="utf-8") as f:
            f.write(canonical(obj))
        r = subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", key_path, "-n", namespace, msg],
                           capture_output=True, timeout=30)
        if r.returncode:
            raise SecurityError(r.stderr.decode(errors="replace").strip())
        with open(msg + ".sig", encoding="utf-8") as f:
            return f.read()


def ssh_verify(obj, sig, pubkeys, namespace):
    """True if `sig` over canonical(obj) verifies for one of `pubkeys` (OpenSSH public key lines)."""
    if not sig or not pubkeys:
        return False
    with tempfile.TemporaryDirectory() as d:
        allowed, s = os.path.join(d, "allowed"), os.path.join(d, "sig")
        with open(allowed, "w", encoding="utf-8") as f:
            for k in pubkeys:
                f.write(f'{PRINCIPAL} namespaces="{namespace}" {k}\n')
        with open(s, "w", encoding="utf-8") as f:
            f.write(sig)
        r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", allowed, "-I", PRINCIPAL, "-n", namespace, "-s", s],
                           input=canonical(obj).encode(), capture_output=True, timeout=30)
        return r.returncode == 0


def fingerprint(pubkey):
    r = subprocess.run(["ssh-keygen", "-lf", "-"], input=pubkey.encode(), capture_output=True, timeout=30)
    if r.returncode:
        raise SecurityError("not a public key")
    return r.stdout.decode().split()[1]                 # SHA256:...


# ---------------------------------------------------------------- 1. key binding

def keyreg_entry(action, pubkey, seq, ts, note=""):
    return {"action": action, "pubkey": pubkey, "seq": seq, "ts": ts, "note": note, "namespace": NS_KEYREG}


class KeyRegistry:
    """entries: list of (entry, signature). Entry 0 is the root ("add") and must match the external anchor
    fingerprint; it is self-signed. Every later entry must be signed by a key valid before it."""

    @staticmethod
    def valid_keys(entries, anchor_fingerprint):
        if not entries:
            raise SecurityError("empty key registry")
        valid = []
        for i, (e, sig) in enumerate(entries):
            if e.get("seq") != i or e.get("namespace") != NS_KEYREG:
                raise SecurityError(f"registry entry {i}: bad sequence or namespace")
            if i == 0:
                if e["action"] != "add" or fingerprint(e["pubkey"]) != anchor_fingerprint:
                    raise SecurityError("root key does not match the external trust anchor")
                if not ssh_verify(e, sig, [e["pubkey"]], NS_KEYREG):
                    raise SecurityError("root entry not self-signed")
                valid.append(e["pubkey"])
                continue
            if not ssh_verify(e, sig, valid, NS_KEYREG):
                raise SecurityError(f"registry entry {i} not signed by a valid owner key")
            if e["action"] == "add":
                valid.append(e["pubkey"])
            elif e["action"] == "revoke":
                if e["pubkey"] not in valid:
                    raise SecurityError(f"registry entry {i}: revoking an unknown key")
                valid.remove(e["pubkey"])
            else:
                raise SecurityError(f"registry entry {i}: unknown action")
        if not valid:
            raise SecurityError("no valid owner key left")
        return valid


# ---------------------------------------------------------------- 2. rollback-proof checkpoint

def checkpoint_statement(log_id, entries, ts):
    return {"log_id": log_id, "length": len(entries), "head": entries[-1]["hash"] if entries else "0" * 64,
            "ts": ts, "namespace": NS_CHECKPOINT}


def verify_against_checkpoint(log_id, entries, checkpoint, sig, owner_keys):
    """The log must extend the latest signed checkpoint (no rollback, truncation or fork)."""
    if checkpoint.get("log_id") != log_id or checkpoint.get("namespace") != NS_CHECKPOINT:
        raise SecurityError("checkpoint is for another log")
    if not ssh_verify(checkpoint, sig, owner_keys, NS_CHECKPOINT):
        raise SecurityError("checkpoint signature not valid for an owner key")
    n = checkpoint["length"]
    if len(entries) < n:
        raise SecurityError("log shorter than the signed checkpoint (rollback or truncation)")
    if n and entries[n - 1].get("hash") != checkpoint["head"]:
        raise SecurityError("log does not extend the signed checkpoint (fork or replaced history)")
    return True


# ---------------------------------------------------------------- 3. legacy identity

class LegacyManifest:
    def __init__(self, triples):
        self.triples = sorted({(e, c, p) for e, c, p in triples})
        self.digest = sha(self.triples)

    def exempt(self, exp_id, spec_commit, protocol, pinned_digest):
        if self.digest != pinned_digest:
            raise SecurityError("legacy manifest altered: nothing is exempt")
        return (exp_id, spec_commit, protocol) in set(map(tuple, self.triples))


# ---------------------------------------------------------------- 4. data identity

def data_lock(files, checksum_source, fetched_ts, lock_ts):
    """files: {name: sha256 hex as published by the source}."""
    if lock_ts < fetched_ts:
        raise SecurityError("lock before the checksums were fetched")
    return {"files": dict(sorted(files.items())), "checksum_source": checksum_source, "fetched_ts": fetched_ts,
            "lock_ts": lock_ts, "limitations": ["CHECKSUM_SAME_SOURCE"]}


def verify_access(lock, name, content, access_ts, pinned_digest):
    if sha(lock) != pinned_digest:
        raise SecurityError("data lock altered after the lock")
    if access_ts < lock["lock_ts"]:
        raise SecurityError("data accessed before the lock")
    if name not in lock["files"]:
        raise SecurityError(f"{name} is not in the locked data set")
    if hashlib.sha256(content).hexdigest() != lock["files"][name]:
        raise SecurityError(f"{name}: content differs from the locked checksum")
    return list(lock["limitations"])


# ---------------------------------------------------------------- 5. point-in-time universe

def universe(rule, index):
    """rule: {window_start, min_history_days, include_delisted}; index: {symbol: [first_ts, last_ts or None]}."""
    out = []
    for sym, (first, last) in sorted(index.items()):
        if first > rule["window_start"] - rule["min_history_days"] * 86400:
            continue                                   # not listed long enough before the window
        if last is not None and last < rule["window_start"]:
            continue                                   # gone before the window: not a member then
        if last is not None and not rule.get("include_delisted", True):
            raise SecurityError("excluding later-delisted symbols is survivorship bias")
        out.append(sym)
    return out


def universe_lock(rule, index, rule_ts, index_fetched_ts, lock_ts):
    if rule_ts > lock_ts:
        raise SecurityError("rule written after the lock")
    if rule_ts > index_fetched_ts:
        raise SecurityError("rule written after the archive index was seen")
    status = "LOCKED" if index_fetched_ts <= lock_ts else "RECONSTRUCTED"
    members = universe(rule, index)
    return {"rule": rule, "rule_ts": rule_ts, "index_sha256": sha(index), "members": members,
            "members_sha256": sha(members), "index_fetched_ts": index_fetched_ts, "lock_ts": lock_ts,
            "status": status}


def verify_universe(lock, rule, index):
    if lock["status"] != "LOCKED":
        raise SecurityError("a reconstructed universe is never the locked universe")
    if rule != lock["rule"]:
        raise SecurityError("universe rule changed after the lock")
    if sha(index) != lock["index_sha256"] or sha(universe(rule, index)) != lock["members_sha256"]:
        raise SecurityError("archive index or members changed after the lock")
    return lock["members"]


# ---------------------------------------------------------------- owner actions (none done by the assistant)

OWNER_ACTIONS = [
    "Create the approval/checkpoint signing key yourself, on another device or with a passphrase the assistant never "
    "receives; do not use ~/.ssh/id_ed25519 on this host and do not load the key into an ssh-agent on this host.",
    "Publish the key's fingerprint at a trust anchor the assistant cannot write (e.g. your GitHub account's SSH keys) "
    "or read it out so it can be pinned outside this host.",
    "Sign the root key registry entry (self-signature) and any later key additions/revocations.",
    "Sign audit-log checkpoints periodically (or keep an off-host witness key that does).",
    "Sign the pinned digest of the legacy manifest (migration v1) once.",
    "Approve each new template with a signed statement (order 48 P0); a general instruction never counts.",
]
