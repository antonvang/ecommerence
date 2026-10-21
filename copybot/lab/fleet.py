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

HEAVY = {"backtest", "cost", "adversarial", "validate", "holdout", "observe", "observe_interim"}
# Heavy steps run in worker processes (Python threads cannot use several cores at once). One slot per process;
# two cores stay free for the supervisor, agents, dashboard and the rest of the PC. LAB_SLOTS overrides,
# LAB_THREADS=1 runs heavy steps in-thread (used by tests that patch module state).
HEAVY_SLOTS = int(os.environ.get("LAB_SLOTS") or max(2, (os.cpu_count() or 4) - 2))
PROCESSES = os.environ.get("LAB_THREADS") != "1"
LEASE_EVERY = 15
QUIET_BEAT_S = 15        # an unchanged waiting heartbeat is written at most this often (was every 1-2 s tick)
_slots = threading.BoundedSemaphore(HEAVY_SLOTS)
_pool, _pool_lock = None, threading.Lock()
STOPPING = threading.Event()     # set by shutdown(): no new claims; interrupted jobs are re-run after the next start


def _get_pool():
    global _pool
    with _pool_lock:
        if STOPPING.is_set():
            raise RuntimeError("fleet is stopping")
        if _pool is None:
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor
            # spawn everywhere: a forked child would inherit the parent's SQLite connections and POSIX file locks
            # (database is locked, risk of corruption). Windows always spawns; Linux defaults to fork.
            _pool = ProcessPoolExecutor(max_workers=HEAVY_SLOTS, mp_context=multiprocessing.get_context("spawn"))
        return _pool


def _reset_pool(broken):
    """A job process died outside a stop (OOM killer, kill): that executor refuses all further work, so the next
    heavy job gets a fresh one. Only the broken pool is replaced (another job may already have made a new one)."""
    global _pool
    with _pool_lock:
        if _pool is not broken:
            return
        _pool = None
    broken.shutdown(wait=False, cancel_futures=True)


def shutdown():
    """Supervisor on_stop hook: claim nothing new, cancel queued pool work and kill running job processes (Python
    would otherwise wait for them at exit). Each interrupted job is put back in the queue by its agent (jobs.release:
    job.interrupted, the attempt is not used up); if that cannot be written, jobs.recover re-runs it after the next
    start. Nothing is recorded as a failure."""
    global _pool
    STOPPING.set()
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is None:
        return
    procs = list((getattr(pool, "_processes", None) or {}).values())
    pool.shutdown(wait=False, cancel_futures=True)
    for p in procs:
        if p.is_alive():
            p.kill()
    for p in procs:
        p.join(2)


STOP_GRACE_S = 3                         # a job process killed with the whole process group (PC shutdown) dies
                                         # before the supervisor sets STOPPING; wait this long before calling it
                                         # a failure
JOB_RAM_DEFAULT = 400 * 2 ** 20          # used until worker processes have reported a measured peak


def _peak_bytes():
    """Peak working set of this process (Windows) or max RSS elsewhere; None if unknown."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import c_size_t, c_ulong

            class PMC(ctypes.Structure):
                _fields_ = [("cb", c_ulong), ("faults", c_ulong), ("peak_ws", c_size_t), ("ws", c_size_t),
                            ("a", c_size_t), ("b", c_size_t), ("c", c_size_t), ("d", c_size_t),
                            ("pagefile", c_size_t), ("peak_pagefile", c_size_t)]
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p            # 64-bit handle: never let ctypes truncate it
            k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), c_ulong]
            m = PMC()
            m.cb = ctypes.sizeof(PMC)
            ok = k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(m), m.cb)
            return m.peak_ws if ok else None
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except Exception:
        return None


def job_ram_estimate(db):
    """Largest measured worker peak among the last 50 heavy jobs (bytes), or the default."""
    peaks = []
    for (r,) in db.q("SELECT result FROM jobs WHERE status='done' AND kind IN ('backtest','cost','adversarial',"
                     "'validate','holdout') AND result LIKE '%peak_mb%' ORDER BY finished_ts DESC LIMIT 50"):
        try:
            peaks.append(json.loads(r)["peak_mb"])
        except (ValueError, KeyError, TypeError):
            pass
    return max(peaks) * 2 ** 20 if peaks else JOB_RAM_DEFAULT


def _overrides():
    from lab.engine import data as mdata
    return {"ARTIFACTS": pipeline.ARTIFACTS, "REPORTS": pipeline.REPORTS, "PLACEBO_N": pipeline.PLACEBO_N,
            "CACHE": mdata.CACHE}


def _child(kind, db_path, job, worker, overrides):
    """Runs in a worker process: same handler, own DB connection, same paths as the parent."""
    from lab.engine import data as mdata
    pipeline.ARTIFACTS, pipeline.REPORTS = overrides["ARTIFACTS"], overrides["REPORTS"]
    pipeline.PLACEBO_N, mdata.CACHE = overrides["PLACEBO_N"], overrides["CACHE"]
    db = DB(db_path)
    try:
        res = pipeline.HANDLERS[kind](db, job, worker)
        peak = _peak_bytes()
        extra = {"pid": os.getpid(), **({"peak_mb": round(peak / 2 ** 20, 1)} if peak else {})}
        return {**res, **extra} if isinstance(res, dict) else res
    finally:
        db.close()


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
    if st["stop"] or STOPPING.is_set():
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
        self.always_run = name == "risk-1"
        self.next_periodic = 0.0
        self.counters = None
        self.failing = None                # last periodic error until a pass succeeds: alive is not healthy
        self._quiet = (None, 0.0)          # (status, detail) of the last waiting heartbeat and when it was written

    # ---------- bookkeeping ----------
    def _load_counters(self, db):
        r = db.one("SELECT tasks_done, errors, retries FROM heartbeats WHERE worker=?", self.name)
        self.counters = {"tasks_done": (r and r["tasks_done"]) or 0, "errors": (r and r["errors"]) or 0,
                         "retries": (r and r["retries"]) or 0}

    def beat(self, db, status, **f):
        self._quiet = (None, 0.0)
        _beat(db, self.name, self.role, status, started_ts=self.started, stale_after=self.stale_after,
              interval=self.interval, **self.counters, **f)

    def _quiet_beat(self, db, status, **f):
        """A waiting state that has not changed is written at most every QUIET_BEAT_S; a change is written at once."""
        key, now = (status, f.get("detail")), time.time()
        if self._quiet[0] == key and now - self._quiet[1] < QUIET_BEAT_S:
            return
        self.beat(db, status, **f)
        self._quiet = (key, now)

    def log(self, kind, **fields):
        log_dir = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "logs") if self.db_path else ops.LOG_DIR
        ops.log_json("agents", kind, log_dir, agent=self.name, role=self.role, **fields)

    # ---------- one tick (called by the supervisor worker loop) ----------
    def __call__(self, db):
        if self.counters is None:
            self._load_counters(db)
        why = blocked_reason(db)
        if why and self.always_run and why != "stop requested":
            why = None                     # the risk agent must keep checking, or it could never lift its own hold
        if why:
            self._quiet_beat(db, "blocked", detail=why, current_job=None, current_exp=None, next_action="wait: " + why)
            return
        if self.kinds:
            return self._job_tick(db)
        return self._periodic_tick(db)

    def _periodic_tick(self, db):
        now = time.time()
        if now < self.next_periodic:
            if self.failing:
                self._quiet_beat(db, "failed", detail=f"last pass failed: {self.failing}"[:200], current_job=None,
                                 current_exp=None, next_action=f"retry in {int(self.next_periodic - now)} s")
            else:
                self._quiet_beat(db, "idle", detail="waiting for next run", current_job=None, current_exp=None,
                                 next_action=f"next run in {int(self.next_periodic - now)} s")
            return
        self.beat(db, "running", detail=f"{self.role} pass", current_job=f"{self.name}:periodic", current_exp=None,
                  next_action="finish pass")
        t0 = time.time()
        try:
            res = self.fn(db)
            self.counters["tasks_done"] += 1
            summary = _summary(res)
            self.log("periodic.done", result=summary, seconds=round(time.time() - t0, 2))
            self.next_periodic = time.time() + self.every
            if self.failing:
                db.event("agent.recovered", f"agent:{self.name}", None, {"agent": self.name, "after": self.failing})
            self.failing = None
            self.beat(db, "idle", detail="ok", current_job=None, current_exp=None, last_result=summary,
                      last_ok_ts=time.time(), next_action=f"next run in {int(self.every)} s")
        except Exception as e:
            self.counters["errors"] += 1
            self.next_periodic = time.time() + min(self.every, 60)
            self.log("periodic.error", error=repr(e), seconds=round(time.time() - t0, 2),
                     trace=traceback.format_exc()[-1500:])
            if self.failing != repr(e)[:300]:                    # a changed or new failure is recorded once
                db.event("agent.error", f"agent:{self.name}", None, {"agent": self.name, "error": repr(e)[:300]})
            self.failing = repr(e)[:300]
            self.beat(db, "failed", detail=repr(e)[:200], current_job=None, current_exp=None,
                      last_result=f"error: {repr(e)[:150]}", last_error=repr(e)[:300], last_error_ts=time.time(),
                      next_action="retry next pass")

    def _job_tick(self, db):
        slot = False
        if self.heavy:
            r = control.ram()
            need = job_ram_estimate(db)
            if r and r["free"] < control.RAM_MIN_FREE + need:
                self._quiet_beat(db, "queued", detail=f"waiting for RAM: {r['free'] / 2 ** 30:.1f} GB free, a heavy job "
                          f"needs about {need / 2 ** 20:.0f} MB above the {control.RAM_MIN_FREE / 2 ** 30:.1f} GB floor",
                          current_job=None, current_exp=None, next_action="claim when memory frees")
                return
            slot = _slots.acquire(blocking=False)
            if not slot:
                self._quiet_beat(db, "queued", detail=f"waiting for a compute slot ({HEAVY_SLOTS} shared)",
                          current_job=None, current_exp=None, next_action="claim when a slot frees")
                return
        try:
            job = jobs.claim(db, self.name, self.kinds) if jobs.runnable_any(db, self.kinds) else None
            if job is None:
                self._quiet_beat(db, "idle", detail="queue empty for " + ",".join(self.kinds), current_job=None,
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
        pool = None
        try:
            if self.heavy and PROCESSES and self.db_path:
                pool = _get_pool()
                res = pool.submit(_child, job["kind"], self.db_path, job, self.name, _overrides()).result()
            else:
                res = pipeline.HANDLERS[job["kind"]](db, job, self.name)
            stop.set()
            keeper.join(5)
            if jobs.complete(db, jid, self.name, res):
                self.counters["tasks_done"] += 1
                last = _summary(res)
                done = {"last_ok_ts": time.time()}
            else:
                last, done = "lease lost (timed out): result discarded", {}
            self.log("job.done", job=jid, exp=eid, seconds=round(time.time() - t0, 2), result=last)
            self.beat(db, "idle", detail="ok", current_job=None, current_exp=None, last_result=last,
                      next_action="claim next job", **done)
        except Exception as e:
            stop.set()
            keeper.join(5)
            if isinstance(e, pipeline.Deferred):            # amendment 9: waiting for the embargo is not a failure
                done = jobs.defer(db, jid, self.name, str(e), e.until)
                self.log("job.deferred", job=jid, exp=eid, until=e.until, error=repr(e), deferred=done)
                self.beat(db, "idle", detail=f"deferred: {e}"[:200], current_job=None, current_exp=None,
                          last_result=f"{job['kind']} deferred", next_action="claim next job")
                return
            broken = type(e).__name__ == "BrokenProcessPool"
            if STOPPING.is_set() or (broken and STOPPING.wait(STOP_GRACE_S)):   # a stop killed it: not a failure
                try:
                    requeued = jobs.release(db, jid, self.name, f"interrupted by shutdown: {e!r}")
                except Exception:                       # database busy at shutdown: jobs.recover re-runs it later
                    requeued = False
                self.log("job.interrupted", job=jid, exp=eid, seconds=round(time.time() - t0, 2), error=repr(e),
                         requeued=requeued)
                self.beat(db, "stopped", detail="interrupted by shutdown; re-run after the next start",
                          current_job=None, current_exp=None, next_action="none (stopping)")
                return
            if broken and pool is not None:
                _reset_pool(pool)
            retryable = not isinstance(e, (lifecycle.LifecycleError, pipeline.StepError, KeyError))
            outcome = jobs.fail(db, jid, self.name, repr(e), retryable=retryable)
            self.counters["errors"] += 1
            if outcome == "retry":
                self.counters["retries"] += 1
            self.log("job.error", job=jid, exp=eid, error=repr(e), outcome=outcome,
                     trace=traceback.format_exc()[-1500:])
            self.beat(db, "idle", detail=repr(e)[:200], current_job=None, current_exp=None,
                      last_result=f"{job['kind']} {outcome}: {repr(e)[:120]}", last_error=repr(e)[:300],
                      last_error_ts=time.time(), next_action="claim next job")

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


def _shape(v):
    """A short, still meaningful stand-in for a large value (paper results: status and order count per ledger)."""
    if isinstance(v, dict) and v and all(isinstance(x, dict) and "status" in x for x in v.values()):
        return {k: x["status"] + (f"/{len(x['orders'])}" if x.get("orders") else "") for k, x in v.items()}
    if isinstance(v, dict):
        return f"{len(v)} keys"
    if isinstance(v, (list, tuple)):
        return f"{len(v)} items"
    return str(v)[:80]


def _summary(res, limit=300):
    """Always valid JSON (it was cut mid-string at 300 characters): large values are summarised, not truncated."""
    if res is None:
        return "ok"
    keep = {k: v for k, v in res.items() if k != "artifact"} if isinstance(res, dict) else res
    s = json.dumps(keep, default=str)
    if len(s) <= limit:
        return s
    if isinstance(keep, dict):
        s = json.dumps({k: (v if isinstance(v, (int, float, bool, type(None))) or (isinstance(v, str) and len(v) <= 80)
                            else _shape(v)) for k, v in keep.items()}, default=str)
        if len(s) <= 2 * limit:
            return s
        return json.dumps({"summary": "large result", "keys": list(keep)[:20]})
    return json.dumps({"summary": _shape(keep)})


# ---------- periodic functions ----------
def strategy_pass(db):
    """Register DISCOVERED catalogue instances whose template has a valid human approval, and instances of approved
    families (amendment 8: one batch per family); queue approved holdouts."""
    from lab import families, registry
    found = [x["exp_id"] for x in registry.status(db) if x["state"] == "DISCOVERED" and x["exp_id"].startswith("E_")]
    # one batch per pass (v2); also with nothing found, so a family batch that stopped part-way completes (amendment 8)
    registered = pipeline.register_batch(db, found, "strategy-1")
    fams = families.pass_(db, "strategy-1")                                             # errors contained per family
    from lab import promotion
    decisions = [d for d in promotion.step(db) if d.get("applicable")]                 # amendment 4: one decision path
    from lab import explore, ingest, lane, scanresearch
    return {"registered": registered, "promotions": [(d["exp_id"], d["to"], d["allowed"]) for d in decisions],
            "holdouts_queued": pipeline.enqueue_holdouts(db), "diagnostics_queued": pipeline.enqueue_diagnostics(db),
            "scan_research_queued": scanresearch.enqueue(db),           # amendment 9 section 3: digest and dossiers
            "explore_queued": explore.enqueue(db),          # amendments 10/10a: one lane job at a time, hourly
            "lane_report_queued": lane.enqueue_report(db),  # amendment 12d: the daily account report
            "lane_reviews_queued": lane.enqueue_reviews(db),  # amendment 11c: adversarial review of candidates
            "ingest_queued": ingest.enqueue(db) if ingest.auto(db) else 0,   # amendment 14: one unit at a time
            **({"families": fams} if fams else {})}


def external_watch(db, now=None):
    """External processes on this host (e.g. the pm_lp collector) that stopped writing: one hash-chained
    external.stale event per outage and external.recovered when writes resume. Processes whose files are not on this
    host are skipped. Nothing is restarted."""
    from lab.mission import EXTERNAL_RUNNING_S
    stale_now = []
    for eid, x in ops.external_freshness(now).items():
        age = x["last_write_age_s"]
        if age is None:
            continue
        last = db.one("SELECT kind FROM events WHERE kind IN ('external.stale','external.recovered') AND exp_id=? "
                      "ORDER BY id DESC LIMIT 1", eid)
        was = bool(last and last["kind"] == "external.stale")
        if age > EXTERNAL_RUNNING_S:
            stale_now.append(eid)
            if not was:
                db.event("external.stale", "agent:risk-1", eid, {"label": x["label"], "last_write_age_s": round(age),
                                                                 "threshold_s": EXTERNAL_RUNNING_S})
        elif was:
            db.event("external.recovered", "agent:risk-1", eid, {"label": x["label"], "last_write_age_s": round(age)})
    return stale_now


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
                "disk_free_gb": round(res["disk"]["free"] / 1e9, 1), "reconciliation_problems": len(problems),
                "external_stale": external_watch(db)}
    return run


class AgentDegraded(RuntimeError):
    """The pass ran, but part of its task could not be done: the agent is reported as failed."""


def paper_pass(db):
    from lab import paper_runner
    res = paper_runner.run(db)
    bad = {k: v.get("reason") or v["status"] for k, v in res["results"].items() if v.get("status") in
           ("blocked", "error")}
    if bad:
        raise AgentDegraded(f"paper ledgers not processed: {json.dumps(bad)[:250]}")
    return res


def catalogue_pass(db):
    """Catalogue templates, then the instances of every committed, valid family file (amendment 8 point 6)."""
    from lab import families
    return [{"exp_id": e, "state": s, "duplicate_of": d} for e, s, d in
            pipeline.discover_catalogue(db) + families.discover_all(db)]


def scanner_pass(db):
    from lab import scanner
    return scanner.run(db)


def news_pass(db):
    from lab import news                      # amendment 16: announcements and news (observations only)
    return news.run(db)


def premium_pass(db):
    from lab import scanner                   # amendment 12a: the perp premium every minute (observations only)
    return scanner.premium_watch(db)


# ---------- roster ----------
ROSTER = (
    # name, role, kinds, periodic fn, every s, heavy
    ("data-1", "Data agent: downloads and quality-checks market data per experiment; free new sources (amendment 14)",
     ("data", "ingest"), None, None, False),
    ("discovery-scanner", "Discovery agent: live-market anomaly scanner (S3 detectors)", None, scanner_pass, 3600, False),
    ("premium-watch", "Discovery agent: Binance perp premium every minute (amendment 12a)", None, premium_pass, 60,
     False),
    ("news-watch", "Discovery agent: exchange announcements and crypto news every 10 min (amendment 16, data only)",
     None, news_pass, 600, False),
    ("discovery-catalogue", "Discovery agent: proposes catalogue hypotheses (graveyard dedup)", None, catalogue_pass,
     600, False),
    ("strategy-1", "Strategy agent: registers approved-template instances, queues approved holdouts", None,
     strategy_pass, 30, False),
    ("backtest-1", "Backtest agent: grid positions on the train window; exploration lane (amendment 10)",
     ("backtest", "explore"), None, None, True),
    ("backtest-2", "Backtest agent: grid positions on the train window; exploration lane (amendment 10)",
     ("backtest", "explore"), None, None, True),
    ("cost-1", "Cost agent: net results, 2x cost stress, trials ledger, selection", ("cost",), None, None, True),
    ("cost-2", "Cost agent: net results, 2x cost stress, trials ledger, selection", ("cost",), None, None, True),
    ("adversarial-1", "Adversarial agent: look-ahead, poison, delay, placebo; lane reviews (11c)",
     ("adversarial", "lane_review"), None, None, True),
    ("adversarial-2", "Adversarial agent: look-ahead, poison, delay, placebo; lane reviews (11c)",
     ("adversarial", "lane_review"), None, None, True),
    ("adversarial-3", "Adversarial agent: look-ahead, poison, delay, placebo; lane reviews (11c)",
     ("adversarial", "lane_review"), None, None, True),
    ("validation-1", "Validation agent: frozen variant on validation; forward test; sealed holdout after approval",
     ("validate", "holdout", "observe", "observe_interim"), None, None, True),
    ("validation-2", "Validation agent: frozen variant on validation; forward test; sealed holdout after approval",
     ("validate", "holdout", "observe", "observe_interim"), None, None, True),
    ("report-1", "Reporting agent: results, lifecycle verdicts, markdown reports; diagnostics of finished experiments",
     ("report", "diagnose", "scan_digest", "scan_dossier", "explore_report", "lane_report"), None, None, False),
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
    STOPPING.clear()                     # a new fleet in this process (tests) starts unstopped
    return [Worker(a.name, a, a.interval, stale_after=a.stale_after, beats_itself=True, role=a.role)
            for a in agents(db_path)]


ROLES = {name: role for name, role, *_ in ROSTER}
