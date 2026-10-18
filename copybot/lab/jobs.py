"""Persistent job queue (Mission 6). Operational table `jobs` (mutable state) + hash-chained `job.*` events (audit).

- Deduplication: `job_id` is deterministic (caller supplies a key, e.g. "backtest|EXP|v2"); enqueueing an existing id is
  a no-op that returns the existing job.
- Claiming is atomic: a single UPDATE ... WHERE status='queued' inside BEGIN IMMEDIATE, so two workers can never hold
  the same job. A claim is a lease (`lease_until`); an expired lease is a timeout and the job is retried.
- Retry with exponential backoff up to `max_attempts`; then the job is `failed` (dead letter).
- Dependencies: a job waits (`blocked`) until every job it depends on is `done`.
- Restart: on startup, `recover()` turns leases left by a dead process into retries.
"""
from __future__ import annotations

import json
import time

STATUSES = ("queued", "running", "done", "failed", "blocked", "cancelled")
BACKOFF_BASE, BACKOFF_MAX = 10, 600

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, exp_id TEXT, priority INTEGER DEFAULT 50, status TEXT NOT NULL,
  attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 3, timeout_s INTEGER DEFAULT 300,
  lease_owner TEXT, lease_until REAL, next_run REAL DEFAULT 0, depends_on TEXT, payload TEXT, result TEXT,
  error TEXT, created_ts REAL, started_ts REAL, finished_ts REAL, updated_ts REAL);
CREATE INDEX IF NOT EXISTS jobs_claim ON jobs(status, kind, priority, next_run);
CREATE INDEX IF NOT EXISTS jobs_exp ON jobs(exp_id);
"""


def init(db):
    db.con.executescript(SCHEMA)


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("payload", "result", "depends_on"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


def get(db, job_id):
    return _row(db.one("SELECT * FROM jobs WHERE job_id=?", job_id))


def enqueue(db, job_id, kind, exp_id=None, payload=None, priority=50, depends_on=(), max_attempts=3, timeout_s=300,
            actor="system:queue", now=None, not_before=0):
    """Idempotent: returns (job, created)."""
    now = now or time.time()
    init(db)
    with db.tx():
        existing = db.one("SELECT * FROM jobs WHERE job_id=?", job_id)
        if existing:
            return _row(existing), False
        status = "blocked" if depends_on else "queued"
        db.con.execute("INSERT INTO jobs(job_id, kind, exp_id, priority, status, max_attempts, timeout_s, next_run, "
                       "depends_on, payload, created_ts, updated_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       (job_id, kind, exp_id, priority, status, max_attempts, timeout_s, not_before,
                        json.dumps(list(depends_on)), json.dumps(payload or {}), now, now))
        db.event("job.enqueued", actor, exp_id, {"job_id": job_id, "kind": kind, "priority": priority,
                                                  "depends_on": list(depends_on)})
    return get(db, job_id), True


def _unblock(db, now):
    for r in db.q("SELECT job_id, depends_on FROM jobs WHERE status='blocked'"):
        deps = json.loads(r["depends_on"] or "[]")
        st = {x["job_id"]: x["status"] for x in db.q(
            f"SELECT job_id, status FROM jobs WHERE job_id IN ({','.join('?' * len(deps))})", *deps)} if deps else {}
        if any(st.get(d) in ("failed", "cancelled") for d in deps):
            db.con.execute("UPDATE jobs SET status='cancelled', error='dependency failed', updated_ts=? WHERE job_id=?",
                           (now, r["job_id"]))
            db.event("job.cancelled", "system:queue", None, {"job_id": r["job_id"], "reason": "dependency failed"})
        elif all(st.get(d) == "done" for d in deps):
            db.con.execute("UPDATE jobs SET status='queued', updated_ts=? WHERE job_id=?", (now, r["job_id"]))


def claim(db, worker_id, kinds, now=None):
    """Atomically lease the best runnable job of the given kinds, or return None."""
    now = now or time.time()
    init(db)
    with db.tx():
        _expire(db, now)
        _unblock(db, now)
        r = db.one(f"SELECT job_id, timeout_s FROM jobs WHERE status='queued' AND next_run<=? AND kind IN "
                   f"({','.join('?' * len(kinds))}) ORDER BY priority, created_ts LIMIT 1", now, *kinds)
        if r is None:
            return None
        cur = db.con.execute("UPDATE jobs SET status='running', lease_owner=?, lease_until=?, attempts=attempts+1, "
                             "started_ts=?, updated_ts=? WHERE job_id=? AND status='queued'",
                             (worker_id, now + r["timeout_s"], now, now, r["job_id"]))
        if cur.rowcount != 1:
            return None
        job = get(db, r["job_id"])
        db.event("job.started", worker_id, job["exp_id"], {"job_id": job["job_id"], "kind": job["kind"],
                                                           "attempt": job["attempts"]})
    return job


def heartbeat(db, job_id, worker_id, now=None):
    """Extend the lease of a long job (only the lease owner can)."""
    now = now or time.time()
    j = get(db, job_id)
    if j and j["status"] == "running" and j["lease_owner"] == worker_id:
        db.con.execute("UPDATE jobs SET lease_until=?, updated_ts=? WHERE job_id=?", (now + j["timeout_s"], now, job_id))
        return True
    return False


def complete(db, job_id, worker_id, result=None, now=None):
    now = now or time.time()
    with db.tx():
        cur = db.con.execute("UPDATE jobs SET status='done', result=?, finished_ts=?, updated_ts=?, lease_owner=NULL "
                             "WHERE job_id=? AND status='running' AND lease_owner=?",
                             (json.dumps(result or {}, default=str), now, now, job_id, worker_id))
        if cur.rowcount != 1:
            return False                                   # lease lost (timed out and taken over): result discarded
        j = get(db, job_id)
        art = (result or {}).get("artifact") if isinstance(result, dict) else None
        db.event("job.done", worker_id, j["exp_id"], {"job_id": job_id, "kind": j["kind"],
                                                      "duration_s": round(now - (j["started_ts"] or now), 3),
                                                      **({"artifact_sha256": art["sha256"]}
                                                         if isinstance(art, dict) and art.get("sha256") else {})})
    return True


def fail(db, job_id, worker_id, error, now=None, retryable=True):
    now = now or time.time()
    with db.tx():
        j = get(db, job_id)
        if not j or j["status"] != "running" or j["lease_owner"] != worker_id:
            return None
        if retryable and j["attempts"] < j["max_attempts"]:
            delay = min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (j["attempts"] - 1))
            db.con.execute("UPDATE jobs SET status='queued', next_run=?, error=?, lease_owner=NULL, updated_ts=? "
                           "WHERE job_id=?", (now + delay, str(error)[:500], now, job_id))
            db.event("job.retry", worker_id, j["exp_id"], {"job_id": job_id, "error": str(error)[:300],
                                                           "attempt": j["attempts"], "backoff_s": delay})
            return "retry"
        db.con.execute("UPDATE jobs SET status='failed', error=?, finished_ts=?, lease_owner=NULL, updated_ts=? "
                       "WHERE job_id=?", (str(error)[:500], now, now, job_id))
        db.event("job.failed", worker_id, j["exp_id"], {"job_id": job_id, "error": str(error)[:300],
                                                        "attempts": j["attempts"]})
        return "failed"


def release(db, job_id, worker_id, reason, now=None):
    """A job interrupted by a planned stop goes back to the queue at once and gets its attempt back: an interruption
    is not an error (event job.interrupted, never job.timeout or job.failed). Only the lease owner can."""
    now = now or time.time()
    with db.tx():
        j = get(db, job_id)
        if not j or j["status"] != "running" or j["lease_owner"] != worker_id:
            return False
        db.con.execute("UPDATE jobs SET status='queued', attempts=MAX(attempts - 1, 0), next_run=?, lease_owner=NULL, "
                       "lease_until=NULL, updated_ts=? WHERE job_id=?", (now, now, job_id))
        db.event("job.interrupted", worker_id, j["exp_id"], {"job_id": job_id, "kind": j["kind"],
                                                             "reason": str(reason)[:200]})
    return True


def _expire(db, now):
    for r in db.q("SELECT job_id, lease_owner, attempts, max_attempts, exp_id FROM jobs WHERE status='running' AND "
                  "lease_until<?", now):
        if r["attempts"] < r["max_attempts"]:
            delay = min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (r["attempts"] - 1))
            db.con.execute("UPDATE jobs SET status='queued', next_run=?, error='lease expired (timeout)', "
                           "lease_owner=NULL, updated_ts=? WHERE job_id=?", (now + delay, now, r["job_id"]))
            db.event("job.timeout", "system:queue", r["exp_id"], {"job_id": r["job_id"], "owner": r["lease_owner"],
                                                                  "action": "retry", "backoff_s": delay})
        else:
            db.con.execute("UPDATE jobs SET status='failed', error='lease expired (timeout), attempts exhausted', "
                           "finished_ts=?, lease_owner=NULL, updated_ts=? WHERE job_id=?", (now, now, r["job_id"]))
            db.event("job.failed", "system:queue", r["exp_id"], {"job_id": r["job_id"], "error": "timeout"})


def recover(db, now=None):
    """After a restart: every running job belongs to a dead process -> expire its lease immediately."""
    now = now or time.time()
    init(db)
    with db.tx():
        n = db.one("SELECT COUNT(*) FROM jobs WHERE status='running'")[0]
        db.con.execute("UPDATE jobs SET lease_until=0 WHERE status='running'")
        _expire(db, now)
    return n


def runnable(db, now=None):
    """Queued jobs whose time has come, per kind, and when the next queued job becomes due."""
    now = now or time.time()
    init(db)
    by = {r["kind"]: r["n"] for r in db.q("SELECT kind, COUNT(*) n FROM jobs WHERE status='queued' AND next_run<=? "
                                          "GROUP BY kind", now)}
    nxt = db.one("SELECT MIN(next_run) FROM jobs WHERE status='queued' AND next_run>?", now)[0]
    return {"by_kind": by, "total": sum(by.values()), "next_due_ts": nxt}


def counts(db):
    init(db)
    out = {s: 0 for s in STATUSES}
    for r in db.q("SELECT status, COUNT(*) n FROM jobs GROUP BY status"):
        out[r["status"]] = r["n"]
    return out


def cancel_all(db, reason, actor):
    """Controlled stop of queued/blocked work (running jobs finish or time out)."""
    init(db)
    with db.tx():
        n = db.con.execute("UPDATE jobs SET status='cancelled', error=?, updated_ts=? WHERE status IN ('queued','blocked')",
                           (reason, time.time())).rowcount
        db.event("job.cancel_all", actor, None, {"cancelled": n, "reason": reason})
    return n
