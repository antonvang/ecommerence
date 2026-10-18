"""Job queue and fleet robustness (research/PROTOCOL_V3.md amendment 6): a planned stop is not an error, leases are
recovered before any worker claims, a broken process pool is replaced, a busy database never kills the fleet, and a
re-run cost step records each variant once."""
import os
import shutil
import signal
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures.process import BrokenProcessPool
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import control, fleet, jobs, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.supervisor import Supervisor, Worker  # noqa: E402

ERRORS = ("job.retry", "job.timeout", "job.failed")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labjobs")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)

    def tearDown(self):
        fleet.STOPPING.clear()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kinds(self):
        return [r["kind"] for r in self.db.q("SELECT kind FROM events ORDER BY id")]

    def agent(self, heavy=False):
        a = fleet.Agent("t-1", "test agent", kinds=("slowtest",), heavy=heavy, db_path=self.path)
        a._load_counters(self.db)
        return a

    def claimed(self, max_attempts=3):
        jobs.enqueue(self.db, "slowtest|E_x", "slowtest", "E_x", {}, max_attempts=max_attempts, actor="system:t")
        return jobs.claim(self.db, "t-1", ("slowtest",))


class Release(Base):
    def test_an_interrupted_job_goes_back_to_the_queue_with_its_attempt(self):
        j = self.claimed()
        self.assertEqual(j["attempts"], 1)
        self.assertFalse(jobs.release(self.db, j["job_id"], "someone-else", "stop"))   # only the lease owner
        self.assertTrue(jobs.release(self.db, j["job_id"], "t-1", "interrupted by shutdown"))
        r = jobs.get(self.db, j["job_id"])
        self.assertEqual((r["status"], r["attempts"], r["lease_owner"]), ("queued", 0, None))
        self.assertIn("job.interrupted", self.kinds())
        self.assertFalse(set(ERRORS) & set(self.kinds()))
        self.assertEqual(jobs.recover(self.db, time.time()), 0)                     # nothing left for recovery

    def test_a_stop_during_a_job_is_an_interruption_not_a_failure(self):
        j = self.claimed(max_attempts=2)                                              # like a holdout job

        def killed(db, job, worker):
            fleet.STOPPING.set()                                                      # the stop killed it mid-run
            raise RuntimeError("job process killed")

        for _ in range(3):                                                            # three stops in a row
            with mock.patch.dict(pipeline.HANDLERS, {"slowtest": killed}):
                self.agent()._run(self.db, j)
            fleet.STOPPING.clear()
            j = jobs.claim(self.db, "t-1", ("slowtest",))
            self.assertIsNotNone(j)
            self.assertEqual(j["attempts"], 1)                                        # never used up
        self.assertEqual(self.kinds().count("job.interrupted"), 3)
        self.assertFalse(set(ERRORS) & set(self.kinds()))

    def test_a_job_process_killed_with_the_process_group_counts_as_an_interruption(self):
        j = self.claimed()

        class Pool:
            def submit(self, *a):
                threading.Timer(0.2, fleet.STOPPING.set).start()                   # the supervisor gets there later
                raise BrokenProcessPool("A process in the process pool was terminated abruptly")

        with mock.patch.object(fleet, "_pool", Pool()), mock.patch.object(fleet, "PROCESSES", True), \
                mock.patch.object(fleet, "STOP_GRACE_S", 2):
            self.agent(heavy=True)._run(self.db, j)
        r = jobs.get(self.db, j["job_id"])
        self.assertEqual((r["status"], r["attempts"]), ("queued", 0))
        self.assertIn("job.interrupted", self.kinds())
        self.assertNotIn("job.retry", self.kinds())


class BrokenPool(Base):
    def test_a_dead_job_process_does_not_break_every_later_heavy_job(self):
        j = self.claimed()
        shut = []

        class Pool:
            def submit(self, *a):
                raise BrokenProcessPool("A child process terminated abruptly, the process pool is not usable")

            def shutdown(self, wait=True, cancel_futures=False):
                shut.append(cancel_futures)

        broken = Pool()
        with mock.patch.object(fleet, "_pool", broken), mock.patch.object(fleet, "PROCESSES", True), \
                mock.patch.object(fleet, "STOP_GRACE_S", 0.05):
            self.agent(heavy=True)._run(self.db, j)
            self.assertIsNone(fleet._pool)                                            # the next job gets a new pool
            self.assertEqual(shut, [True])
            fresh = object()
            fleet._pool = fresh
            fleet._reset_pool(broken)                                                 # a late reset never hits it
            self.assertIs(fleet._pool, fresh)
        r = jobs.get(self.db, j["job_id"])
        self.assertEqual((r["status"], r["attempts"]), ("queued", 1))                 # a real failure: retried
        self.assertIn("job.retry", self.kinds())


class Startup(Base):
    def setUp(self):
        super().setUp()
        self.prev = signal.signal(signal.SIGTERM, lambda *_: None)

    def tearDown(self):
        signal.signal(signal.SIGTERM, self.prev)
        super().tearDown()

    def test_leases_are_recovered_before_any_worker_can_claim(self):
        seen = []
        real = jobs.recover

        def recover(db, now=None):
            seen.append(sorted(t.name for t in threading.enumerate() if t.name.startswith("lab-")))
            return real(db, now)

        sup = Supervisor(self.path, [Worker("w-1", lambda db: None, interval=0.2)], log=lambda *a: None,
                         check_evidence=False)
        with mock.patch.object(jobs, "recover", recover):
            self.assertEqual(sup.run(duration=1.0), 0)
        self.assertEqual(seen, [[]])

    def test_a_database_locked_longer_than_the_busy_timeout_does_not_kill_the_fleet(self):
        connect = sqlite3.connect

        def short(*a, **k):
            k["timeout"] = 0.5
            return connect(*a, **k)

        def hold():
            con = connect(self.path, timeout=5, isolation_level=None)
            con.execute("BEGIN IMMEDIATE")
            time.sleep(3.0)                                       # six busy timeouts
            con.execute("COMMIT")
            con.close()

        sup = Supervisor(self.path, [Worker("w-1", lambda db: None, interval=0.2)], log=lambda *a: None,
                         check_evidence=False)
        threading.Timer(1.5, hold).start()
        with mock.patch.object(sqlite3, "connect", short):
            self.assertEqual(sup.run(duration=7.0), 0)
        k = self.kinds()
        self.assertIn("system.db_busy", k)                        # recorded once the lock was gone
        self.assertIn("system.stopped", k)                        # it ran to its planned end
        self.assertNotIn("worker.failed", k)
        busy = self.db.one("SELECT payload FROM events WHERE kind='system.db_busy'")[0]
        self.assertIn("seconds", busy)


class CostRerun(Base):
    def test_a_rerun_cost_step_records_each_variant_once(self):
        variants = [{"variant": f"v{i}", "params": {"k": i}, "positions": None} for i in range(3)]
        m = {"net_mean_daily": 0.001, "net_sd_daily": 0.01, "days": 100, "net_total": 0.1, "net_sharpe_ann": 1.0}
        with mock.patch.object(pipeline, "_spec", lambda db, e: {"costs": {}, "template": "t"}), \
                mock.patch.object(pipeline, "_train", lambda *a: ({}, {}, None, None)), \
                mock.patch.object(pipeline, "load_artifact", lambda e, s: {"variants": variants}), \
                mock.patch.object(pipeline, "_evaluate", lambda *a: dict(m)), \
                mock.patch.object(pipeline, "_benchmark", lambda *a: dict(m)), \
                mock.patch.object(pipeline, "save_artifact", lambda *a: {"sha256": "0" * 64}):
            for _ in range(2):
                r = pipeline.step_cost(self.db, {"exp_id": "E_x"}, "t")
                self.assertEqual(r["tests"], 3)
        rows = self.db.q("SELECT variant FROM trials WHERE exp_id='E_x' ORDER BY id")
        self.assertEqual([x["variant"] for x in rows], ["v0", "v1", "v2"])


class Portability(unittest.TestCase):
    def test_write_lock_holder_without_proc_locks_reports_unknown(self):
        fake = types.SimpleNamespace(stat=lambda p: types.SimpleNamespace(st_dev=1, st_ino=2))   # no os.major
        with mock.patch.object(control, "os", fake):
            self.assertIsNone(control.write_lock_holder("x.db"))


if __name__ == "__main__":
    unittest.main()
