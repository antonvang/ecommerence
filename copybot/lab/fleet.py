"""Research agent fleet (Mission 6). Each agent is a supervisor worker with one role and its own heartbeat row.

Job agents claim jobs of their kinds from the persistent queue (lab/jobs.py) and run the matching pipeline step.
Periodic agents run a function on an interval. Every agent checks the control state first: while the lab is paused,
held for resources, stopping or FAIL_CLOSED no new job is claimed (the agent reports `blocked` with the reason).

Heavy steps share a global slot limit (HEAVY_SLOTS) so the machine is never overcommitted; an agent waiting for a slot
reports `queued`. A lease keeper thread extends the job lease and the heartbeat while a long step runs, up to the job's
timeout; after that the lease expires, the queue retries the job and the late result is discarded.

Nothing here places a real order. The paper agent only simulates fills for experiments a human moved to PAPER_TRADING.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback

from lab import control, jobs, lifecycle, ops, pipeline
from lab.db import DB
from lab.risk import Risk
from lab.supervisor import Worker

HEAVY = {"backtest", "cost", "adversarial", "validate", "holdout"}
HEAVY_SLOTS = 2
LEASE_EVERY = 15
_slots = threading.BoundedSemaphore(HEAVY_SLOTS)


def _beat(db, name, role, status, **f):
    """Upsert the agent's operational heartbeat row (mutable, not hash-chained)."""
    cols = {"worker": name, "ts": int(time.time()), "pid": os.getpid(), "ok": int(status != "failed"),
            "status": status, "role": role, **f}
    keys = list(cols)
    db.con.execute(f"INSERT INTO heartbeats({','.join(keys)}) VALUES({','.join('?' * len(keys))}) "
                   f"ON CONFLICT(worker) DO UPDATE SET {','.join(f'{k}=excluded.{k}' for k in keys if k != 'worker')}",
                   [cols[k] for k in keys])


def blocked_reason(db):
    st = control.state(db)
    if st["stop"]:
        return "stop requested"
    if st["paused"]:
        return "lab paused by operator"
    if st["hold"]:
        return "resource hold (RAM or disk below limit)"
    if Risk(db).fail_closed():
        return "lab FAIL_CLOSED"
    return None


class Agent:
    def __init__(self, name, role, kinds=None, every=None, fn=None, interval=2.0, stale_after=120, heavy=False,
                 db_path=None):
        self.name, self.role, self.kinds, self.every, self.fn = name, role, tuple(kinds or ()), every, fn
        self.interval, self.stale_after, self.heavy, self.db_path = interval, stale_after, heavy, db_path
        self.started = time.time()
        self.next_periodic = 0.0
        self.counters = None

    # ---------- bookkeeping ----------
    def _load_counters(self, db):
        r = db.one("SELECT tasks_done, errors, retries FROM heartbeats WHERE worker=?", self.name)
        self.counters = {"tasks_done": (r and r["tasks_done"]) or 0, "errors": (r and r["errors"]) or 0,
                         "retries": (r and r["retries"]) or 0}

    def beat(self, db, status, **f):
        _beat(db, self.name, self.role, status, started_ts=self.started, stale_after=self.stale_after,
              interval=self.interval, **self.counters, **f)

    def log(self, kind, **fields):
        ops.log_json("agents", kind, agent=self.name, role=self.role, **fields)

    # ---------- one tick (called by the supervisor worker loop) ----------
    def __call__(self, db):
        if self.counters is None:
            self._load_counters(db)
        why = blocked_reason(db)
        if why:
            self.beat(db, "blocked", detail=why, current_job=None, current_exp=None, next_action="wait: " + why)
            return
        if self.kinds:
            return self._job_tick(db)
        return self._periodic_tick(db)

    def _periodic_tick(self, db):
        now = time.time()
        if now < self.next_periodic:
            self.beat(db, "idle", detail="waiting for next run", current_job=None, current_exp=None,
                      next_action=f"next run in {int(self.next_periodic - now)} s")
            return
        self.beat(db, "running", detail=f"{self.role} pass", current_job=f"{self.name}:periodic", current_exp=None,
                  next_action="finish pass")
        try:
            res = self.fn(db)
            self.counters["tasks_done"] += 1
            summary = _summary(res)
            self.log("periodic.done", result=summary)
            self.next_periodic = time.time() + self.every
            self.beat(db, "idle", detail="ok", current_job=None, current_exp=None, last_result=summary,
                      next_action=f"next run in {int(self.every)} s")
        except Exception as e:
            self.counters["errors"] += 1
            self.next_periodic = time.time() + min(self.every, 60)
            self.log("periodic.error", error=repr(e))
            db.event("agent.error", f"agent:{self.name}", None, {"agent": self.name, "error": repr(e)[:300]})
            self.beat(db, "idle", detail=repr(e)[:200], current_job=None, current_exp=None,
                      last_result=f"error: {repr(e)[:150]}", next_action="retry next pass")

    def _job_tick(self, db):
        slot = False
        if self.heavy:
            slot = _slots.acquire(blocking=False)
            if not slot:
                self.beat(db, "queued", detail=f"waiting for a compute slot ({HEAVY_SLOTS} shared)",
                          current_job=None, current_exp=None, next_action="claim when a slot frees")
                return
        try:
            job = jobs.claim(db, self.name, self.kinds)
            if job is None:
                self.beat(db, "idle", detail="queue empty for " + ",".join(self.kinds), current_job=None,
                          current_exp=None, next_action="poll queue")
                return
            self._run(db, job)
        finally:
            if slot:
                _slots.release()

    def _run(self, db, job):
        jid, eid = job["job_id"], job["exp_id"]
        self.beat(db, "running", detail=f"{job['kind']} attempt {job['attempts']}", current_job=jid,
                  current_exp=eid, next_action=f"finish {job['kind']}")
        self.log("job.start", job=jid, exp=eid, attempt=job["attempts"])
        stop = threading.Event()
        keeper = threading.Thread(target=self._keep_lease, args=(job, stop), daemon=True, name=f"lease-{self.name}")
        keeper.start()
        t0 = time.time()
        try:
            res = pipeline.HANDLERS[job["kind"]](db, job, self.name)
            stop.set()
            keeper.join(5)
            if jobs.complete(db, jid, self.name, res):
                self.counters["tasks_done"] += 1
                last = _summary(res)
            else:
                last = "lease lost (timed out): result discarded"
            self.log("job.done", job=jid, exp=eid, seconds=round(time.time() - t0, 2), result=last)
            self.beat(db, "idle", detail="ok", current_job=None, current_exp=None, last_result=last,
                      next_action="claim next job")
        except Exception as e:
            stop.set()
            keeper.join(5)
            retryable = not isinstance(e, (lifecycle.LifecycleError, pipeline.StepError, KeyError))
            outcome = jobs.fail(db, jid, self.name, repr(e), retryable=retryable)
            self.counters["errors"] += 1
            if outcome == "retry":
                self.counters["retries"] += 1
            self.log("job.error", job=jid, exp=eid, error=repr(e), outcome=outcome,
                     trace=traceback.format_exc()[-1500:])
            self.beat(db, "idle", detail=repr(e)[:200], current_job=None, current_exp=None,
                      last_result=f"{job['kind']} {outcome}: {repr(e)[:120]}", next_action="claim next job")

    def _keep_lease(self, job, stop):
        """Own connection (sqlite objects are per thread). Extends the lease until the job's own timeout is reached."""
        db = DB(self.db_path) if self.db_path else None
        if db is None:
            return
        deadline = time.time() + job["timeout_s"]
        try:
            while not stop.wait(LEASE_EVERY):
                if time.time() + LEASE_EVERY >= deadline:
                    break                                   # let the lease run out: the queue treats it as a timeout
                jobs.heartbeat(db, job["job_id"], self.name)
                db.con.execute("UPDATE heartbeats SET ts=? WHERE worker=?", (int(time.time()), self.name))
        finally:
            db.close()


def _summary(res):
    if res is None:
        return "ok"
    if isinstance(res, dict):
        keep = {k: v for k, v in res.items() if k != "artifact"}
        return json.dumps(keep, default=str)[:300]
    return json.dumps(res, default=str)[:300]


# ---------- periodic functions ----------
def strategy_pass(db):
    """Register DISCOVERED catalogue instances whose template has a valid human approval; queue approved holdouts."""
    from lab import registry
    found = [x["exp_id"] for x in registry.status(db) if x["state"] == "DISCOVERED" and x["exp_id"].startswith("E_")]
    registered = pipeline.register_batch(db, found, "strategy-1") if found else []     # one batch per pass (v2)
    return {"registered": registered, "holdouts_queued": pipeline.enqueue_holdouts(db)}


def risk_pass(db_path):
    def run(db):
        res = control.resources(os.path.dirname(os.path.abspath(db_path)))
        control.update_hold(db, "agent:risk-1", res)
        problems = {}
        from lab import paper
        eng = paper.PaperEngine(db)
        for r in db.q("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started'"):
            rec = eng.reconcile(r[0])
            if not rec["ok"]:
                problems[r[0]] = rec["problems"]
        if problems and not Risk(db).fail_closed():
            Risk(db).trip_fail_closed("reconciliation", json.dumps(problems)[:500])
        return {"resources_ok": res["ok"], "ram_free_gb": round(((res["ram"] or {}).get("free") or 0) / 1e9, 2),
                "disk_free_gb": round(res["disk"]["free"] / 1e9, 1), "reconciliation_problems": len(problems)}
    return run


def paper_pass(db):
    from lab import paper_runner
    return paper_runner.run(db)


def catalogue_pass(db):
    return [{"exp_id": e, "state": s, "duplicate_of": d} for e, s, d in pipeline.discover_catalogue(db)]


def scanner_pass(db):
    from lab import scanner
    return scanner.run(db)


# ---------- roster ----------
ROSTER = (
    # name, role, kinds, periodic fn, every s, heavy
    ("data-1", "Data agent: downloads and quality-checks market data per experiment", ("data",), None, None, False),
    ("discovery-scanner", "Discovery agent: live-market anomaly scanner (S3 detectors)", None, scanner_pass, 3600, False),
    ("discovery-catalogue", "Discovery agent: proposes catalogue hypotheses (graveyard dedup)", None, catalogue_pass,
     600, False),
    ("strategy-1", "Strategy agent: registers approved-template instances, queues approved holdouts", None,
     strategy_pass, 30, False),
    ("backtest-1", "Backtest agent: grid positions on the train window", ("backtest",), None, None, True),
    ("backtest-2", "Backtest agent: grid positions on the train window", ("backtest",), None, None, True),
    ("cost-1", "Cost agent: net results, 2x cost stress, trials ledger, selection", ("cost",), None, None, True),
    ("adversarial-1", "Adversarial agent: look-ahead, poison, delay, placebo", ("adversarial",), None, None, True),
    ("validation-1", "Validation agent: frozen variant on validation; sealed holdout after approval",
     ("validate", "holdout"), None, None, True),
    ("report-1", "Reporting agent: results, lifecycle verdicts, markdown reports", ("report",), None, None, False),
    ("paper-1", "Paper execution agent: simulated orders for PAPER_TRADING experiments only", None, paper_pass, 60,
     False),
    ("risk-1", "Risk supervisor agent: RAM/disk holds, paper reconciliation", None, None, 15, False),
)


def agents(db_path):
    out = []
    for name, role, kinds, fn, every, heavy in ROSTER:
        if name == "risk-1":
            fn = risk_pass(db_path)
        out.append(Agent(name, role, kinds=kinds, every=every, fn=fn, heavy=heavy, db_path=db_path,
                         interval=1.0 if kinds else 2.0, stale_after=180 if kinds else max(180, 3 * (every or 60))))
    return out


def workers(db_path):
    return [Worker(a.name, a, a.interval, stale_after=a.stale_after, beats_itself=True, role=a.role)
            for a in agents(db_path)]


ROLES = {name: role for name, role, *_ in ROSTER}
