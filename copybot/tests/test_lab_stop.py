"""`lab stop` never hangs on a frozen fleet: it reports the hung process at once and ends it with --force; the
supervisor shuts down gracefully on SIGTERM. Linux only (uses /proc and POSIX signals)."""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lab import control  # noqa: E402
from lab.db import DB  # noqa: E402

# A stand-in fleet: argv carries "lab fleet" like the real one, records system.running with its pid, leaves an old
# supervisor heartbeat and (with "lock") holds the database write lock, then waits to be frozen.
FAKE = """
import sys, time
sys.path.insert(0, sys.argv[1])
from lab.db import DB
db = DB(sys.argv[2])
db.event("system.running", "system:supervisor", None, {"pid": __import__("os").getpid()})
db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, status) VALUES('supervisor', ?, 0, 1, 'running') "
               "ON CONFLICT(worker) DO UPDATE SET ts=excluded.ts, status='running'", (int(time.time()) - 600,))
if sys.argv[3] == "lock":
    db.con.execute("BEGIN IMMEDIATE")
print("ready", flush=True)
time.sleep(600)
"""


@unittest.skipUnless(os.path.isdir("/proc") and hasattr(signal, "SIGSTOP"), "needs /proc and POSIX signals")
class Stop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labstop")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.lines, self.procs = [], []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
                p.wait()
            p.stdout.close()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, mode, freeze=True):
        p = subprocess.Popen([sys.executable, "-c", FAKE, ROOT, self.path, mode, "lab", "fleet"],
                             stdout=subprocess.PIPE, text=True)
        self.procs.append(p)
        self.assertEqual(p.stdout.readline().strip(), "ready")
        if freeze:
            os.kill(p.pid, signal.SIGSTOP)
        return p

    def run_stop(self, **k):
        t = time.time()
        rc = control.stop(self.db, "human:test", "test stop", out=self.lines.append, lock_wait=0.2, **k)
        return rc, time.time() - t

    def kinds(self):
        return [r["kind"] for r in self.db.q("SELECT kind FROM events ORDER BY id")]

    def test_frozen_fleet_holding_the_write_lock_is_reported_at_once_and_ended_with_force(self):
        p = self.fake("lock")
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
        p = self.fake("lock", freeze=False)
        os.kill(p.pid, signal.SIGSTOP)
        with mock.patch.object(control.signal, "SIGTERM", signal.SIGWINCH):     # as if SIGTERM were ignored
            rc, _ = self.run_stop(force=True, grace=1)
        self.assertEqual(rc, 0)
        self.assertEqual(p.wait(timeout=5), -signal.SIGKILL)
        self.assertIn("SIGKILL", self.lines[-1])

    def test_frozen_fleet_without_the_lock_gets_the_request_but_is_still_reported(self):
        self.fake("nolock")
        rc, _ = self.run_stop()
        self.assertEqual(rc, 3)
        self.assertIn("system.stop_requested", self.kinds())
        self.assertIn("nothing will act on it", self.lines[-1])

    def test_a_responding_fleet_gets_a_plain_graceful_request(self):
        self.db.event("system.running", "system:supervisor", None, {"pid": os.getpid()})
        self.db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, status) VALUES('supervisor', ?, 0, 1, "
                            "'running')", (int(time.time()),))
        rc, _ = self.run_stop()
        self.assertEqual((rc, self.lines), (0, ["stop: recorded"]))

    def test_a_lock_held_by_something_else_is_not_mistaken_for_the_fleet(self):
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


@unittest.skipUnless(hasattr(signal, "SIGTERM") and os.name != "nt", "POSIX signals")
class SupervisorSigterm(unittest.TestCase):
    def test_sigterm_stops_the_supervisor_gracefully(self):
        tmp = tempfile.mkdtemp(prefix="labterm")
        path = os.path.join(tmp, "lab.db")
        try:
            DB(path).close()
            p = subprocess.Popen([sys.executable, "-m", "lab", "--db", path, "supervise", "--no-default",
                                  "--duration", "60"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            db = DB(path)
            try:
                end = time.time() + 30
                while not db.one("SELECT 1 FROM events WHERE kind='system.running'") and time.time() < end:
                    time.sleep(0.2)
                os.kill(p.pid, signal.SIGTERM)
                self.assertEqual(p.wait(timeout=30), 0)
                self.assertTrue(db.one("SELECT 1 FROM events WHERE kind='system.stopped'"))
            finally:
                db.close()
                if p.poll() is None:
                    p.kill()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
