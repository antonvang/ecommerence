"""Durable, fenced SQLite job leases for the synthetic research runner.

Only the explicitly supplied database is opened. Existing foreign schemas are
rejected before any schema/journal changes. Each process owns its JobStore
connection. All supplied times are integer Unix seconds; no network is used.
"""

from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import time


APPLICATION_ID = 0x434A5155
SCHEMA_VERSION = 1
STATUSES = ("queued", "running", "succeeded", "failed")
MAX_INT = (1 << 63) - 1


class JobConflictError(ValueError):
    """An existing job id was submitted with a different payload."""


class LeaseLostError(RuntimeError):
    """The worker no longer owns an active lease for this job."""


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be a nonempty string")
    return value


def _integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_INT:
        raise ValueError(f"{name} must be an integer in [{minimum}, {MAX_INT}]")
    return value


def _json_value(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, list):
        for element in value:
            _json_value(element)
        return
    if isinstance(value, dict):
        for key, element in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            _json_value(element)
        return
    raise ValueError("Only JSON values are accepted; no custom objects or pickle")


def canonical_json(value):
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


class JobStore:
    """Queue with bounded retries and result/status commits in one transaction.

    Attempts are charged at claim, including attempts whose workers crash.
    Expired running jobs are recovered by the next claim. Replay of the same
    job id/payload is a read: it never resets state or expands the retry budget.
    """

    def __init__(self, path):
        raw_path = os.fspath(path)
        if not isinstance(raw_path, str) or not raw_path or raw_path == ":memory:":
            raise ValueError("An explicit durable database path is required")
        self.path = Path(raw_path).resolve()
        if not self.path.parent.is_dir():
            raise ValueError("Database parent directory must already exist")
        self._connection = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        try:
            self._connection.execute("PRAGMA busy_timeout=30000")
            self._initialize()
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
        except BaseException:
            self._connection.close()
            self._closed = True
            raise

    def _check_open(self):
        if self._closed:
            raise RuntimeError("JobStore is closed")

    @contextmanager
    def _transaction(self):
        self._check_open()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _initialize(self):
        with self._transaction():
            app_id = self._connection.execute("PRAGMA application_id").fetchone()[0]
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            objects = self._connection.execute(
                "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if app_id == 0 and not objects and version == 0:
                self._connection.execute("""
                    CREATE TABLE jobs (
                        job_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
                        attempts INTEGER NOT NULL CHECK(attempts >= 0),
                        max_attempts INTEGER NOT NULL CHECK(max_attempts >= 1),
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        worker_id TEXT,
                        token TEXT,
                        lease_until INTEGER,
                        result_json TEXT,
                        error_json TEXT
                    )
                """)
                self._connection.execute(
                    "CREATE INDEX jobs_ready ON jobs(status, created_at, job_id)"
                )
                self._connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif app_id != APPLICATION_ID or version != SCHEMA_VERSION:
                raise ValueError("Refusing an existing foreign or unsupported database schema")
            else:
                columns = [row[1] for row in self._connection.execute("PRAGMA table_info(jobs)")]
                expected = ["job_id", "payload_json", "status", "attempts", "max_attempts",
                            "created_at", "updated_at", "worker_id", "token", "lease_until",
                            "result_json", "error_json"]
                if columns != expected:
                    raise ValueError("Unsupported or damaged job database schema")

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("payload", "result", "error"):
            raw = result.pop(key + "_json")
            result[key] = json.loads(raw) if raw is not None else None
        return result

    def _get(self, job_id):
        return self._connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()

    def enqueue(self, job_id, payload, max_attempts=3, now=None):
        _text(job_id, "job_id")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        raw = canonical_json(payload)
        _integer(max_attempts, "max_attempts", 1)
        now = int(time.time()) if now is None else _integer(now, "now")
        with self._transaction():
            previous = self._get(job_id)
            if previous is not None:
                if previous["payload_json"] != raw:
                    raise JobConflictError("Existing job_id has a different canonical payload")
                return self._decode(previous)
            self._connection.execute("""
                INSERT INTO jobs(job_id,payload_json,status,attempts,max_attempts,created_at,updated_at)
                VALUES(?,?,'queued',0,?,?,?)
            """, (job_id, raw, max_attempts, now, now))
            return self._decode(self._get(job_id))

    def _recover(self, now):
        exhausted = canonical_json(dict(code="LEASE_EXPIRED", message="Retry budget exhausted after expired lease"))
        retry = canonical_json(dict(code="LEASE_EXPIRED", message="Worker lease expired; job queued for retry"))
        self._connection.execute("""
            UPDATE jobs SET
                status=CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
                error_json=CASE WHEN attempts >= max_attempts THEN ? ELSE ? END,
                worker_id=NULL, token=NULL, lease_until=NULL, updated_at=?
            WHERE status='running' AND lease_until <= ?
        """, (exhausted, retry, now, now))

    def claim(self, worker_id, now, lease_s):
        _text(worker_id, "worker_id")
        _integer(now, "now")
        _integer(lease_s, "lease_s", 1)
        if now + lease_s > MAX_INT:
            raise ValueError("Lease expiry exceeds SQLite integer range")
        with self._transaction():
            self._recover(now)
            ready = self._connection.execute("""
                SELECT job_id FROM jobs WHERE status='queued' AND attempts < max_attempts
                ORDER BY created_at, job_id LIMIT 1
            """).fetchone()
            if ready is None:
                return None
            token = secrets.token_hex(32)
            self._connection.execute("""
                UPDATE jobs SET status='running',attempts=attempts+1,worker_id=?,
                    token=?,lease_until=?,updated_at=? WHERE job_id=?
            """, (worker_id, token, now + lease_s, now, ready["job_id"]))
            return self._decode(self._get(ready["job_id"]))

    def _owned(self, job_id, token, now):
        row = self._get(job_id)
        if (row is None or row["status"] != "running" or row["token"] != token
                or row["lease_until"] <= now):
            raise LeaseLostError("Job has no active lease owned by this token")
        return row

    def complete(self, job_id, token, result, now):
        _text(job_id, "job_id")
        _text(token, "token")
        _integer(now, "now")
        if not isinstance(result, dict):
            raise ValueError("result must be a JSON object")
        raw = canonical_json(result)
        with self._transaction():
            self._owned(job_id, token, now)
            self._connection.execute("""
                UPDATE jobs SET status='succeeded',result_json=?,error_json=NULL,
                    worker_id=NULL,token=NULL,lease_until=NULL,updated_at=? WHERE job_id=?
            """, (raw, now, job_id))
            return self._decode(self._get(job_id))

    def fail(self, job_id, token, error, now):
        _text(job_id, "job_id")
        _text(token, "token")
        _integer(now, "now")
        if not isinstance(error, (str, dict)):
            raise ValueError("error must be a string or JSON object")
        raw = canonical_json(error)
        with self._transaction():
            row = self._owned(job_id, token, now)
            status = "failed" if row["attempts"] >= row["max_attempts"] else "queued"
            self._connection.execute("""
                UPDATE jobs SET status=?,error_json=?,worker_id=NULL,token=NULL,
                    lease_until=NULL,updated_at=? WHERE job_id=?
            """, (status, raw, now, job_id))
            return self._decode(self._get(job_id))

    def renew(self, job_id, token, now, lease_s):
        """Extend a current lease; an already expired lease cannot be renewed."""
        _text(job_id, "job_id")
        _text(token, "token")
        _integer(now, "now")
        _integer(lease_s, "lease_s", 1)
        if now + lease_s > MAX_INT:
            raise ValueError("Lease expiry exceeds SQLite integer range")
        with self._transaction():
            row = self._owned(job_id, token, now)
            until = max(row["lease_until"], now + lease_s)
            self._connection.execute(
                "UPDATE jobs SET lease_until=?,updated_at=? WHERE job_id=?", (until, now, job_id)
            )
            return self._decode(self._get(job_id))

    def get(self, job_id):
        self._check_open()
        _text(job_id, "job_id")
        return self._decode(self._get(job_id))

    def list_jobs(self, status=None):
        self._check_open()
        if status is not None and status not in STATUSES:
            raise ValueError("Unknown job status")
        sql = "SELECT * FROM jobs"
        arguments = ()
        if status is not None:
            sql += " WHERE status=?"
            arguments = (status,)
        rows = self._connection.execute(sql + " ORDER BY created_at,job_id", arguments)
        return [self._decode(row) for row in rows]

    def counts(self):
        self._check_open()
        result = dict.fromkeys(STATUSES, 0)
        for row in self._connection.execute("SELECT status,COUNT(*) AS n FROM jobs GROUP BY status"):
            result[row["status"]] = row["n"]
        result["total"] = sum(result.values())
        return result

    def close(self):
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *args):
        self.close()
