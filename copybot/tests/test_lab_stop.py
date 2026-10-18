"""`lab stop` never hangs on a frozen fleet, never blames the fleet for another process's write lock, and ends a hung
fleet with --force; the supervisor stops on SIGTERM without false restarts and without waiting for heavy jobs, which
are re-run after the next start. Linux only (uses /proc and POSIX signals)."""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lab import control, jobs  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.supervisor import Supervisor, Worker  # noqa: E402

POSIX = os.path.isdir("/proc") and hasattr(signal, "SIGSTOP")

# A stand-in fleet: records system.running with its pid and a supervisor heartbeat ("stale" = 10 min old, "fresh" =
# renewed every 0.3 s), and with "lock" holds the database write lock. Its argv ends in "fake-fleet".
FAKE = """
import sys, time
sys.path.insert(0, sys.argv[1])
from lab.db import DB
db = DB(sys.argv[2])
db.event("system.running", "system:supervisor", None, {"pid": __import__("os").getpid()})
def beat(ts):
    db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, status) VALUES('supervisor', ?, 0, 1, 'running') "
                   "ON CONFLICT(worker) DO UPDATE SET ts=excluded.ts, status='running'", (int(ts),))
beat(time.time() - 600 if sys.argv[3] != "fresh" else time.time())
if sys.argv[3] == "lock":
    db.con.execute("BEGIN IMMEDIATE")
print("ready", flush=True)
end = time.time() + 600
while time.time() < end:
    time.sleep(0.3)
    if sys.argv[3] == "fresh":
        try:
            beat(time.time())
        except Exception:
            pass
"""


def _fake_argv(argv):
    return argv[-1:] == ["fake-fleet"]


@unittest.skipUnless(POSIX, "needs /proc and POSIX signals")
class Stop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labstop")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.lines, self.procs = [], []
        self.p = mock.patch.object(control, "_is_supervisor", _fake_argv)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        for p in self.procs:
            if p.poll() is None:
                p.kill()
                p.wait()
            p.stdout.close()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, mode, freeze=True):
        p = subprocess.Popen([sys.executable, "-c", FAKE, ROOT, self.path, mode, "fake-fleet"], cwd=ROOT,
                             stdout=subprocess.PIPE, text=True)
        self.procs.append(p)
        self.assertEqual(p.stdout.readline().strip(), "ready")
        if freeze:
            os.kill(p.pid, signal.SIGSTOP)
        return p

    def run_stop(self, **k):
        k.setdefault("lock_wait", 0.2)
        t = time.time()
        rc = control.stop(self.db, "human:test", "test stop", out=self.lines.append, **k)
        return rc, time.time() - t

    def kinds(self):
        return [r["kind"] for r in self.db.q("SELECT kind FROM events ORDER BY id")]

    def test_frozen_fleet_holding_the_write_lock_is_reported_at_once_and_ended_with_force(self):
        p = self.fake("lock")
        self.assertEqual(control.write_lock_holder(self.path), p.pid)
        rc, took = self.run_stop()
        self.assertEqual(rc, 3)
        self.assertLess(took, 5)
        self.assertIn(f"pid {p.pid}", self.lines[-2])
        self.assertIn("stopped/frozen", self.lines[-2])
        self.assertIn("--force", self.lines[-1])
        self.assertNotIn("system.stop_requested", self.kinds())
        self.assertIsNone(p.poll())
        rc, took = self.run_stop(force=True, grace=3)
        self.assertEqual(rc, 0)
        self.assertLess(took, 10)
        p.wait(timeout=5)
        self.assertIn("system.stop_forced", self.kinds())

    def test_force_falls_back_to_sigkill_when_sigterm_is_ignored(self):
        p = self.fake("lock")
        with mock.patch.object(control.signal, "SIGTERM", signal.SIGWINCH):     # as if SIGTERM were ignored
            rc, _ = self.run_stop(force=True, grace=1)
        self.assertEqual(rc, 0)
        self.assertEqual(p.wait(timeout=5), -signal.SIGKILL)
        self.assertIn("SIGKILL", self.lines[-1])

    def test_frozen_fleet_without_the_lock_gets_the_request_but_is_still_reported(self):
        self.fake("stale")
        rc, _ = self.run_stop()
        self.assertEqual(rc, 3)
        self.assertIn("system.stop_requested", self.kinds())
        self.assertIn("nothing will act on it", self.lines[-1])

    def test_a_responding_fleet_gets_a_plain_graceful_request_and_is_left_running(self):
        p = self.fake("fresh", freeze=False)
        self.assertEqual(control.supervisor_pid(self.db), p.pid)
        rc, _ = self.run_stop(force=True)
        self.assertEqual((rc, self.lines), (0, ["stop: recorded"]))
        self.assertIsNone(p.poll())
        self.assertIn("system.stop_requested", self.kinds())

    def test_a_third_party_lock_never_gets_the_running_fleet_killed(self):
        p = self.fake("fresh", freeze=False)
        other = DB(self.path)
        other.con.execute("BEGIN IMMEDIATE")
        try:
            rc, took = self.run_stop(force=True, max_wait=1)
            self.assertIsNone(p.poll())
            self.assertEqual(rc, 3)
            self.assertEqual(control.write_lock_holder(self.path), os.getpid())
            self.assertLess(took, 8)
            self.assertIn(f"process {os.getpid()}", self.lines[-1])
            self.assertIn("not the fleet", self.lines[-1])
            with mock.patch.object(control, "_beat_age", lambda db: 600.0):      # its beats are blocked by the lock
                rc, _ = self.run_stop(force=True, max_wait=1)
            self.assertEqual(rc, 3)
        finally:
            other.con.execute("ROLLBACK")
            other.close()
        self.assertIsNone(p.poll())
        self.assertNotIn("system.stop_forced", self.kinds())

    def test_a_lock_held_by_something_else_without_a_fleet_is_reported(self):
        other = DB(self.path)
        other.con.execute("BEGIN IMMEDIATE")
        try:
            rc, took = self.run_stop()
        finally:
            other.con.execute("ROLLBACK")
            other.close()
        self.assertEqual(rc, 3)
        self.assertLess(took, 5)
        self.assertIn("NOT recorded", self.lines[-1])


class Recognition(unittest.TestCase):
    def test_argv_must_be_the_lab_fleet_or_supervise_command(self):
        yes = (["python3", "-m", "lab", "fleet"], ["/usr/bin/python3", "-u", "-m", "lab", "--db", "x.db", "supervise"],
               ["python3", "-m", "lab", "--db=x.db", "fleet", "--duration", "5"])
        no = (["python3", "-m", "lab", "stop", "--reason", "fleet"], ["python3", "-m", "lab", "web", "fleet"],
              ["python3", "-c", "x", "-m", "lab", "fleet"], ["python3", "-m", "research.pm_lp", "collect"],
              ["python3", "-m", "lab"], ["bash", "./START_LAB.sh"])
        for a in yes:
            self.assertTrue(control._is_supervisor(a), a)
        for a in no:
            self.assertFalse(control._is_supervisor(a), a)

    @unittest.skipUnless(POSIX, "needs /proc")
    def test_a_supervisor_from_another_directory_or_an_older_run_is_not_this_fleet(self):
        tmp = tempfile.mkdtemp(prefix="labwho")
        path = os.path.join(tmp, "lab.db")
        procs = []
        db = DB(path)
        try:
            def start(cwd):
                p = subprocess.Popen([sys.executable, "-m", "lab", "--db", path, "supervise", "--no-default",
                                      "--duration", "60"], cwd=cwd, env={**os.environ, "PYTHONPATH": ROOT},
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                procs.append(p)
                end = time.time() + 30
                while time.time() < end and not db.one("SELECT 1 FROM events WHERE kind='system.running' AND "
                                                       "payload LIKE ?", f'%"pid":{p.pid}%'):
                    time.sleep(0.2)
                return p

            here = start(ROOT)
            self.assertEqual(control.supervisor_pid(db), here.pid)
            real_one = db.one
            with mock.patch.object(db, "one", lambda q, *a: {"ts": int(time.time()) + 3600,
                                                             "payload": f'{{"pid": {here.pid}}}'}
                                   if "system.running" in q else real_one(q, *a)):
                self.assertIsNone(control.supervisor_pid(db))     # a recorded start long after the process began
            os.kill(here.pid, signal.SIGTERM)
            self.assertEqual(here.wait(timeout=30), 0)
            there = start(tmp)
            self.assertIsNone(control.supervisor_pid(db))           # the same command from another checkout
            os.kill(there.pid, signal.SIGTERM)
            there.wait(timeout=30)
        finally:
            db.close()
            for p in procs:
                if p.poll() is None:
                    p.kill()
                    p.wait()
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(POSIX, "POSIX signals")
class SupervisorSigterm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labterm")
        self.path = os.path.join(self.tmp, "lab.db")
        self.prev = signal.signal(signal.SIGTERM, lambda *_: None)     # a stray SIGTERM must never end the test run

    def tearDown(self):
        signal.signal(signal.SIGTERM, self.prev)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sigterm_with_idle_workers_stops_without_false_restarts(self):
        ws = [Worker(f"idle-{i}", lambda db: None, interval=0.2) for i in range(4)]
        sup = Supervisor(self.path, ws, log=lambda *a: None, check_evidence=False)
        threading.Timer(2.0, os.kill, (os.getpid(), signal.SIGTERM)).start()
        t = time.time()
        self.assertEqual(sup.run(duration=30), 0)
        self.assertLess(time.time() - t, 15)
        db = DB(self.path)
        try:
            kinds = [r["kind"] for r in db.q("SELECT kind FROM events ORDER BY id")]
        finally:
            db.close()
        self.assertIn("system.stopped", kinds)
        self.assertNotIn("worker.restarted", kinds)
        self.assertNotIn("worker.failed", kinds)

    def test_sigterm_during_a_heavy_job_stops_at_once_and_the_job_is_rerun_after_restart(self):
        script = os.path.join(self.tmp, "heavy_fleet.py")
        with open(script, "w") as f:
            f.write(HEAVY)
        env = {**os.environ, "LABSTOP_ROOT": ROOT, "LABSTOP_TMP": self.tmp}
        p = subprocess.Popen([sys.executable, script], env=env, cwd=self.tmp,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        child = os.path.join(self.tmp, "child.pid")
        try:
            end = time.time() + 60
            while not os.path.exists(child) and time.time() < end:
                time.sleep(0.2)
            time.sleep(0.5)
            with open(child) as f:
                cpid = int(f.read())
            t = time.time()
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=60), 0)
            took = time.time() - t
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
        self.assertLess(took, 15)                                     # not the job's 120 s
        self.assertIsNone(control._proc(cpid))                          # the job process is gone
        db = DB(self.path)
        try:
            kinds = [r["kind"] for r in db.q("SELECT kind FROM events ORDER BY id")]
            for k in ("worker.failed", "worker.restarted", "job.failed", "job.retry", "job.timeout"):
                self.assertNotIn(k, kinds)
            self.assertIn("system.stopped", kinds)
            self.assertIn("job.interrupted", kinds)                          # amendment 6: not an error
            j = jobs.get(db, "slow|1")
            self.assertEqual((j["status"], j["attempts"]), ("queued", 0))      # back in the queue, attempt kept
            self.assertEqual(jobs.recover(db, time.time()), 0)
        finally:
            db.close()


# Run as a file so the spawned job process re-imports it and knows the slow handler.
HEAVY = """
import os, sys, time
sys.path.insert(0, os.environ["LABSTOP_ROOT"])
from lab import fleet, jobs, pipeline
TMP = os.environ["LABSTOP_TMP"]


def slow(db, job, worker):
    with open(os.path.join(TMP, "child.pid"), "w") as f:
        f.write(str(os.getpid()))
    time.sleep(120)
    return {"ok": True}


pipeline.HANDLERS["slowtest"] = slow

if __name__ == "__main__":
    from lab.db import DB
    from lab.supervisor import Supervisor, Worker
    path = os.path.join(TMP, "lab.db")
    db = DB(path)
    jobs.enqueue(db, "slow|1", "slowtest", timeout_s=600)
    db.close()
    fleet.STOPPING.clear()
    a = fleet.Agent("heavy-test", "test", kinds=("slowtest",), heavy=True, db_path=path, interval=0.5)
    w = Worker(a.name, a, a.interval, stale_after=a.stale_after, beats_itself=True, role=a.role)
    sys.exit(Supervisor(path, [w], log=lambda *x: None, check_evidence=False, on_stop=(fleet.shutdown,)).run(300))
"""


if __name__ == "__main__":
    unittest.main()
