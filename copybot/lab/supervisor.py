"""Supervisor (ENGINE_PROPOSAL.md §8, stage S5): one instance, worker threads with heartbeats, restart with exponential
backoff, and a fail-closed startup recovery. It is started only by hand (`python -m lab supervise`); there is no
autostart and it never changes experiment rules or promotes anything.

Startup recovery, before any worker runs:
1. verify hash chains, append-only triggers and cited evidence -> on failure the lab goes FAIL_CLOSED, no workers;
2. scan for overfilled simulated orders -> FAIL_CLOSED;
3. reconcile pauses: a PAUSE in the risk log without the matching lifecycle state is applied (logged);
4. every PAPER_TRADING strategy enters WARMUP: new entries are blocked until fresh data passes the guards;
5. heartbeats left by a previous run are reported as stale.
"""
from __future__ import annotations

import importlib
import os
import threading
import time

from lab import legacy, lifecycle, ops
from lab.db import DB, DEFAULT_DB
from lab.risk import Risk

BACKOFF_BASE, BACKOFF_MAX = 5.0, 300.0
SUPERVISOR_BEAT = "supervisor"
ALIVE_EVERY = 3600          # append-only proof of continuous operation (used by the S7 gate)
DISK_EVERY = 60
MAX_RESTARTS_PER_HOUR = 5
ACTOR = "system:supervisor"


class AlreadyRunning(Exception):
    pass


def acquire_lock(path):
    """Exclusive, non-blocking file lock released by the OS when the process ends (also on a hard kill)."""
    f = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise AlreadyRunning(f"another supervisor holds {path}")
    return f


def release_lock(f):
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    f.close()


class Worker:
    """fn(db) is called every `interval` seconds in its own thread with its own DB connection."""

    def __init__(self, name, fn, interval, stale_after=None, critical=False):
        self.name, self.fn, self.interval, self.critical = name, fn, interval, critical
        self.stale_after = stale_after or max(3 * interval, 10)
        self.thread, self.restarts, self.next_start, self.failed = None, [], 0.0, False


def heartbeat_worker():
    """Built-in no-op worker: only proves the supervisor loop and heartbeats work."""
    return Worker("heartbeat", lambda db: None, interval=5)


def scanner_worker():
    from lab import scanner
    return Worker("scanner", lambda db: scanner.run(db), interval=3600, stale_after=3 * 3600)


DEFAULT_WORKERS = ("lab.supervisor:scanner_worker",)


def load_worker(spec):
    mod, fn = spec.split(":")
    return getattr(importlib.import_module(mod), fn)()


def recover(db, risk, stale_after=60, now=time.time, check_evidence=True):
    """Fail-closed startup checks. Returns (ok, report)."""
    report = {}
    chains, triggers = db.verify()
    broken = {t: b for t, (_, b) in chains.items() if b is not None}
    bad_ev = legacy.verify_evidence(db) if check_evidence else []
    report["integrity"] = {"broken": broken, "triggers": triggers, "evidence_problems": bad_ev}
    if broken or not triggers or bad_ev:
        risk.trip_fail_closed("integrity", f"startup verify failed: {report['integrity']}")
        db.event("system.startup", ACTOR, None, {"ok": False, **report})
        return False, report
    over = db.q("SELECT o.order_id, o.exp_id FROM sim_orders o WHERE o.qty + 1e-9 < "
                "(SELECT COALESCE(SUM(qty),0) FROM sim_fills f WHERE f.order_id=o.order_id)")
    if over:
        risk.trip_fail_closed("overfill", f"startup: {[tuple(r) for r in over]}")
        report["overfill"] = [r["order_id"] for r in over]
        db.event("system.startup", ACTOR, None, {"ok": False, **report})
        return False, report
    paper = [r[0] for r in db.q("SELECT DISTINCT exp_id FROM transitions")
             if lifecycle.state(db, r[0]) == "PAPER_TRADING"]
    reconciled, warm = [], []
    for e in paper:
        if risk.paused(e):
            lifecycle.auto_transition(db, e, "PAUSED", "system:risk",
                                      "recovery: pause recorded in the risk log but lifecycle not updated")
            reconciled.append(e)
        else:
            risk.start_warmup(e)
            warm.append(e)
    stale = [r["worker"] for r in db.q("SELECT worker, ts FROM heartbeats") if now() - r["ts"] > stale_after]
    for w in stale:
        db.event("worker.heartbeat_stale", ACTOR, None, {"worker": w, "from": "previous run"})
    report.update({"reconciled_pauses": reconciled, "warmup": warm, "stale_heartbeats": stale,
                   "fail_closed": risk.fail_closed()})
    db.event("system.startup", ACTOR, None, {"ok": True, **report})
    return True, report


class Supervisor:
    def __init__(self, db_path=DEFAULT_DB, workers=(), now=time.time, sleep=time.sleep, log=print,
                 check_evidence=True):
        self.db_path, self.workers, self.now, self.sleep, self.log = db_path, list(workers), now, sleep, log
        self.check_evidence = check_evidence
        self.stop = threading.Event()
        self.db = None
        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "logs")
        self.last_alive = self.last_disk = 0.0

    # ---------- workers ----------
    def beat(self, db, name, ok, detail, status, stale_after, interval):
        db.con.execute("INSERT OR REPLACE INTO heartbeats(worker, ts, pid, ok, detail, status, stale_after, interval) "
                       "VALUES(?,?,?,?,?,?,?,?)", (name, int(self.now()), os.getpid(), ok, detail, status,
                                                   int(stale_after), interval))

    def _loop(self, w):
        db = DB(self.db_path)
        try:
            while not self.stop.is_set():
                self.beat(db, w.name, 1, "working", "running", w.stale_after, w.interval)
                try:
                    w.fn(db)
                    ok, detail = 1, "ok"
                except Exception as e:
                    db.event("worker.error", ACTOR, None, {"worker": w.name, "error": repr(e)})
                    ops.log_json("supervisor", "worker.error", self.log_dir, worker=w.name, error=repr(e))
                    ok, detail = 0, repr(e)[:200]
                self.beat(db, w.name, ok, detail, "idle" if ok else "error", w.stale_after, w.interval)
                if not ok:
                    return                                            # crashed: the supervisor decides on restart
                self.stop.wait(w.interval)
        finally:
            db.close()

    def _start(self, w):
        w.thread = threading.Thread(target=self._loop, args=(w,), name=f"lab-{w.name}", daemon=True)
        w.thread.start()

    def housekeeping(self):
        """Supervisor heartbeat, hourly alive record and disk-space guard."""
        now = self.now()
        self.beat(self.db, SUPERVISOR_BEAT, 1, "supervising", "running", 30, 1.0)
        if now - self.last_alive >= ALIVE_EVERY:
            self.last_alive = now
            self.db.event("system.alive", ACTOR, None, {"pid": os.getpid(), "workers": [w.name for w in self.workers]})
        if now - self.last_disk >= DISK_EVERY:
            self.last_disk = now
            d = ops.disk(os.path.dirname(os.path.abspath(self.db_path)))
            if not d["free_ok"]:
                self.db.event("system.disk_low", ACTOR, None, d)
                ops.log_json("supervisor", "disk_low", self.log_dir, **d)
                Risk(self.db, self.now).trip_fail_closed("disk_low", f"free {d['free']} bytes < {d['min_free']}")

    def check(self):
        """One supervision pass: restart dead or stale workers with exponential backoff; give up after too many."""
        now = self.now()
        for w in self.workers:
            if w.failed:
                continue
            hb = self.db.one("SELECT ts FROM heartbeats WHERE worker=?", w.name)
            alive = w.thread is not None and w.thread.is_alive()
            stale = hb is not None and now - hb["ts"] > w.stale_after
            if alive and not stale:
                continue
            if stale and alive:
                self.db.event("worker.heartbeat_stale", ACTOR, None, {"worker": w.name, "age": now - hb["ts"]})
            w.restarts = [t for t in w.restarts if now - t < 3600]
            if len(w.restarts) >= MAX_RESTARTS_PER_HOUR:
                w.failed = True
                self.db.event("worker.failed", ACTOR, None, {"worker": w.name, "restarts_last_hour": len(w.restarts)})
                if w.critical:
                    Risk(self.db, self.now).trip_fail_closed("worker_failed", w.name)
                continue
            if now < w.next_start or alive:
                continue                                              # a stale-but-alive thread is not duplicated
            delay = min(BACKOFF_MAX, BACKOFF_BASE * 2 ** len(w.restarts))
            w.restarts.append(now)
            w.next_start = now + delay
            self.db.event("worker.restarted", ACTOR, None, {"worker": w.name, "attempt": len(w.restarts),
                                                            "next_backoff_s": delay})
            ops.log_json("supervisor", "worker.restarted", self.log_dir, worker=w.name, attempt=len(w.restarts))
            self._start(w)

    # ---------- main ----------
    def run(self, duration=None):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        lock = acquire_lock(os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "lab.lock"))
        self.db = DB(self.db_path)
        try:
            ok, report = recover(self.db, Risk(self.db, self.now), now=self.now, check_evidence=self.check_evidence)
            self.log(f"startup recovery: {'ok' if ok else 'FAILED (FAIL_CLOSED)'} {report}")
            ops.log_json("supervisor", "startup", self.log_dir, ok=ok, report=report, pid=os.getpid())
            if not ok:
                return 2
            for w in self.workers:
                self._start(w)
            self.db.event("system.running", ACTOR, None, {"workers": [w.name for w in self.workers], "pid": os.getpid()})
            t0 = self.now()
            while not self.stop.is_set() and (duration is None or self.now() - t0 < duration):
                self.housekeeping()
                self.sleep(1.0)
                self.check()
            return 0
        finally:
            self.stop.set()
            for w in self.workers:
                if w.thread is not None:
                    w.thread.join(timeout=10)
            self.db.event("system.stopped", ACTOR, None, {"pid": os.getpid()})
            self.beat(self.db, SUPERVISOR_BEAT, 1, "stopped cleanly", "stopped", 30, 1.0)
            for w in self.workers:
                self.db.con.execute("UPDATE heartbeats SET status='stopped' WHERE worker=?", (w.name,))
            ops.log_json("supervisor", "stopped", self.log_dir, pid=os.getpid())
            self.db.close()
            release_lock(lock)
