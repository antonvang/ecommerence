"""Durable evidence of owner authorization obtained before a forward window.

The owner signs the protocol bundle, never the later observations. Registration
uses owner_approval.verify at the real registration time; future checks reverify
the stored statement against the current trusted signer file at that historical
time. An expired statement therefore cannot create a new authorization, but does
not erase a valid prior authorization. Removing its public key revokes it.

This is a local, permission-protected receipt registry, not an external trusted
timestamp or an append-only database protected against its filesystem owner.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

try:
    from .job_store import APPLICATION_ID, SCHEMA_VERSION, JobConflictError, JobStore, canonical_json
except ImportError:
    from job_store import APPLICATION_ID, SCHEMA_VERSION, JobConflictError, JobStore, canonical_json

COPYBOT = Path(__file__).resolve().parents[4]
if str(COPYBOT) not in sys.path:
    sys.path.insert(0, str(COPYBOT))
from research.tools import owner_approval as owner  # noqa: E402

REGISTRY_KIND = "copybot-owner-authorization-v1"
PROTOCOL_FIELDS = {"schema_version", "study_id", "mode", "created_at", "alpha", "q_fdr",
                   "source_identity", "candidates"}
RECEIPT_FIELDS = {"kind", "protocol_sha256", "study_id", "protocol", "statement", "signature",
                  "verified_at", "owner_signers_sha256", "receipt_sha256"}
STATEMENT_FIELDS = {"scope", "template", "blob", "protocol", "nonce", "issued", "expires",
                    "owner_words", "namespace"}
TMAX = 4102444800


class AuthorizationError(ValueError):
    pass


def protocol_digest(protocol):
    return hashlib.sha256(canonical_json(protocol).encode("utf-8")).hexdigest()


def _require(condition, message):
    if not condition:
        raise AuthorizationError(message)


def _time(value):
    return type(value) is int and 0 <= value <= TMAX


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _bundle(protocol):
    _require(isinstance(protocol, dict) and set(protocol) == PROTOCOL_FIELDS,
             "Protocol must be the exact data-free protocol bundle")
    _require(protocol["schema_version"] == 1 and type(protocol["schema_version"]) is int,
             "Unsupported protocol schema version")
    _require(_text(protocol["study_id"]), "Invalid study id")
    _require(protocol["mode"] == "forward_paper", "Only forward_paper protocols need owner registration")
    _require(_time(protocol["created_at"]), "Invalid protocol creation time")
    _require(isinstance(protocol["candidates"], list) and bool(protocol["candidates"]),
             "Protocol needs candidates")
    starts = []
    for candidate in protocol["candidates"]:
        _require(isinstance(candidate, dict) and set(candidate) ==
                 {"candidate_id", "family", "protocol", "paper_plan"}, "Invalid protocol candidate")
        _require(_text(candidate["candidate_id"]) and _text(candidate["family"]), "Invalid candidate identity")
        specimen = candidate["protocol"]
        _require(isinstance(specimen, dict) and isinstance(specimen.get("window"), dict),
                 "Candidate protocol needs its frozen window")
        start = specimen["window"].get("start")
        end = specimen["window"].get("end")
        _require(_time(start) and _time(end) and start < end, "Invalid candidate window")
        starts.append(start)
    # Validate all remaining nested values as finite canonical JSON as well.
    canonical_json(protocol)
    return min(starts)


def _statement(statement, protocol_hash, study_id):
    _require(isinstance(statement, dict) and set(statement) == STATEMENT_FIELDS,
             "Approval statement has an unexpected schema")
    _require(statement["scope"] == "template" and statement["template"] == study_id,
             "Statement template must equal the study id")
    _require(statement["blob"] == protocol_hash and _digest(statement["blob"]),
             "Statement is for another protocol bundle")
    _require(type(statement["protocol"]) is int and statement["protocol"] == 1,
             "Statement protocol must be integer 1")
    _require(_text(statement["nonce"]), "Statement nonce is missing")
    _require(_text(statement["owner_words"]), "Owner words must be a nonempty string")
    _require(_time(statement["issued"]) and _time(statement["expires"])
             and statement["issued"] < statement["expires"], "Invalid statement validity times")
    canonical_json(statement)


def _db_path(path):
    raw = os.fspath(path)
    _require(isinstance(raw, str) and raw and raw != ":memory:",
             "An explicit separate durable authorization database is required")
    result = Path(raw).resolve()
    _require(result.parent.is_dir(), "Authorization database parent directory does not exist")
    return result


def _existing_registry(path):
    """Inspect existing databases read-only before JobStore can set pragmas."""
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        _require(connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID,
                 "Refusing foreign authorization database")
        _require(connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION,
                 "Unsupported authorization database version")
        objects = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        _require(objects == {"jobs", "jobs_ready", "authorization_metadata"},
                 "Database is not a separate authorization registry")
        rows = connection.execute("SELECT singleton,kind FROM authorization_metadata").fetchall()
        _require(rows == [(1, REGISTRY_KIND)], "Invalid authorization registry identity")
        for job_id, raw in connection.execute("SELECT job_id,payload_json FROM jobs"):
            payload = json.loads(raw)
            _require(isinstance(payload, dict) and payload.get("kind") == REGISTRY_KIND,
                     "Authorization registry contains another record type")
            nonce = payload.get("statement", {}).get("nonce") if isinstance(payload.get("statement"), dict) else None
            _require(_text(nonce) and job_id == _nonce_id(nonce),
                     "Authorization registry nonce index mismatch")


def _open_registry(path, create=False):
    path = _db_path(path)
    existed = path.exists()
    if existed:
        _existing_registry(path)
    else:
        _require(create, "Authorization has not been registered")
    store = JobStore(path)
    try:
        if not existed:
            with store._transaction():
                store._connection.execute("""
                    CREATE TABLE IF NOT EXISTS authorization_metadata (
                        singleton INTEGER PRIMARY KEY CHECK(singleton=1), kind TEXT NOT NULL
                    )
                """)
                store._connection.execute(
                    "INSERT OR IGNORE INTO authorization_metadata(singleton,kind) VALUES(1,?)",
                    (REGISTRY_KIND,))
        _existing_registry(path)
        return store
    except BaseException:
        store.close()
        raise


def _nonce_id(nonce):
    return "authorization-nonce:" + hashlib.sha256(nonce.encode("utf-8")).hexdigest()


def _receipt_body(receipt):
    return {key: value for key, value in receipt.items() if key != "receipt_sha256"}


def _check_receipt(receipt, protocol_hash, study_id, window_start, owner_signers_path):
    _require(isinstance(receipt, dict) and set(receipt) == RECEIPT_FIELDS,
             "Damaged authorization receipt")
    _require(receipt["kind"] == REGISTRY_KIND, "Unrecognized authorization receipt")
    _require(protocol_digest(_receipt_body(receipt)) == receipt["receipt_sha256"],
             "Authorization receipt hash mismatch")
    _require(receipt["protocol_sha256"] == protocol_hash and receipt["study_id"] == study_id,
             "Authorization belongs to another protocol or study")
    first_window = _bundle(receipt["protocol"])
    _require(protocol_digest(receipt["protocol"]) == protocol_hash,
             "Stored protocol bundle differs from the authorization")
    _require(receipt["protocol"]["study_id"] == study_id, "Stored study id mismatch")
    verified_at = receipt["verified_at"]
    _require(_time(verified_at) and _time(window_start)
             and receipt["protocol"]["created_at"] <= verified_at <= first_window
             and verified_at <= window_start, "Authorization was not registered before the window")
    _require(_digest(receipt["owner_signers_sha256"]), "Missing signer-file registration hash")
    _statement(receipt["statement"], protocol_hash, study_id)
    _require(_text(receipt["signature"]), "Stored signature is missing")
    # verify() checks validity at registration, while signature_ok() inside it
    # consults the CURRENT trusted keys. Current wall-clock expiry is irrelevant.
    signer_hash = hashlib.sha256(Path(owner_signers_path).read_bytes()).hexdigest()
    log = owner.AuditLog()
    decision, reasons = owner.verify(receipt["statement"], receipt["signature"],
                                    str(owner_signers_path), protocol_hash, 1, verified_at, log)
    _require(decision == "ACCEPTED", "Stored owner signature is no longer trusted: " + "; ".join(reasons))
    current_hash = hashlib.sha256(Path(owner_signers_path).read_bytes()).hexdigest()
    _require(current_hash == signer_hash, "Trusted owner keys changed during signature verification")
    return dict(status="OWNER_APPROVED", protocol_sha256=protocol_hash, study_id=study_id,
                receipt_sha256=receipt["receipt_sha256"], verified_at=verified_at,
                owner_signers_sha256=receipt["owner_signers_sha256"],
                current_owner_signers_sha256=current_hash,
                approval_basis="previously_registered_before_window")


def freeze_protocol(protocol: dict, statement: dict, signature: str, owner_signers_path,
                    db_path, now: int) -> dict:
    """Register a genuinely verified pre-window approval; never sign for owner."""
    store = None
    try:
        first_window = _bundle(protocol)
        protocol_hash = protocol_digest(protocol)
        study_id = protocol["study_id"]
        _require(_time(now), "Invalid authorization registration time")
        _statement(statement, protocol_hash, study_id)
        _require(_text(signature), "Owner signature is missing")
        path = _db_path(db_path)
        if path.exists():
            store = _open_registry(path)
            previous = store.get(_nonce_id(statement["nonce"]))
            if previous is not None:
                receipt = previous["payload"]
                _require(isinstance(receipt, dict), "Damaged authorization receipt")
                _require(receipt.get("protocol") == protocol
                         and canonical_json(receipt.get("protocol")) == canonical_json(protocol)
                         and canonical_json(receipt.get("statement")) == canonical_json(statement)
                         and receipt.get("signature") == signature,
                         "NONCE_REUSE_CONFLICT")
                result = _check_receipt(receipt, protocol_hash, study_id, first_window, owner_signers_path)
                return dict(result, idempotent=True, receipt=receipt)
        _require(protocol["created_at"] <= now <= first_window,
                 "Protocol must be authorized before every candidate window starts")
        signers = Path(owner_signers_path)
        signer_hash = hashlib.sha256(signers.read_bytes()).hexdigest()
        log = owner.AuditLog()
        decision, reasons = owner.verify(statement, signature, str(signers), protocol_hash, 1, now, log)
        _require(decision == "ACCEPTED", "Owner approval refused: " + "; ".join(reasons))
        _require(hashlib.sha256(signers.read_bytes()).hexdigest() == signer_hash,
                 "Trusted owner keys changed during signature verification")
        receipt = dict(kind=REGISTRY_KIND, protocol_sha256=protocol_hash, study_id=study_id,
                       protocol=protocol, statement=statement, signature=signature,
                       verified_at=now, owner_signers_sha256=signer_hash)
        receipt["receipt_sha256"] = protocol_digest(receipt)
        if store is None:
            store = _open_registry(path, create=True)
        try:
            stored = store.enqueue(_nonce_id(statement["nonce"]), receipt, max_attempts=1, now=now)
        except JobConflictError:
            # A concurrent first registration may have won. Only exact binding
            # is idempotent; preserve its original verified_at and signer hash.
            stored = store.get(_nonce_id(statement["nonce"]))
            existing = stored["payload"] if stored else {}
            _require(canonical_json(existing.get("protocol")) == canonical_json(protocol)
                     and canonical_json(existing.get("statement")) == canonical_json(statement)
                     and existing.get("signature") == signature, "NONCE_REUSE_CONFLICT")
            receipt = existing
            result = _check_receipt(receipt, protocol_hash, study_id, first_window, signers)
            return dict(result, idempotent=True, receipt=receipt)
        receipt = stored["payload"]
        result = _check_receipt(receipt, protocol_hash, study_id, first_window, signers)
        return dict(result, idempotent=False, receipt=receipt)
    except (AuthorizationError, ValueError, TypeError, OSError, sqlite3.Error) as error:
        return dict(status="BLOCKED_OWNER_APPROVAL", reasons=[str(error)])
    finally:
        if store is not None:
            store.close()


def verify_authorization(protocol_hash: str, study_id: str, window_start: int,
                         owner_signers_path, db_path) -> dict:
    """Use registered pre-window evidence; expiry now does not authorize new work."""
    store = None
    try:
        _require(_digest(protocol_hash) and _text(study_id) and _time(window_start),
                 "Invalid authorization lookup")
        store = _open_registry(db_path)
        reasons = []
        for row in store.list_jobs():
            receipt = row["payload"]
            _require(isinstance(receipt, dict), "Damaged authorization receipt")
            if receipt.get("protocol_sha256") != protocol_hash or receipt.get("study_id") != study_id:
                continue
            try:
                _require(row["job_id"] == _nonce_id(receipt["statement"]["nonce"]),
                         "Authorization nonce index mismatch")
                return _check_receipt(receipt, protocol_hash, study_id, window_start, owner_signers_path)
            except (AuthorizationError, ValueError, TypeError, KeyError, OSError) as error:
                reasons.append(str(error))
        return dict(status="BLOCKED_OWNER_APPROVAL", protocol_sha256=protocol_hash,
                    study_id=study_id, reasons=reasons or ["No registered owner authorization for this protocol"])
    except (AuthorizationError, ValueError, TypeError, OSError, sqlite3.Error) as error:
        return dict(status="BLOCKED_OWNER_APPROVAL", reasons=[str(error)])
    finally:
        if store is not None:
            store.close()
