"""Lease, crash, contention and result-transaction tests using throwaway DBs."""

import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from job_store import JobConflictError, JobStore, LeaseLostError


def _claim_once(path, worker, ready, start, results):
    with JobStore(path) as store:
        ready.put(worker)
        start.wait(15)
        job = store.claim(worker, now=100, lease_s=60)
        results.put(None if job is None else (job["job_id"], job["token"]))


def _claim_and_crash(path, pipe):
    store = JobStore(path)
    job = store.claim("crashing-worker", now=100, lease_s=10)
    pipe.send(job)
    pipe.close()
    os._exit(7)


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        work = Path("/workspace/work")
        work.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="job-store-", dir=work)
        self.path = Path(self.directory.name) / "jobs.sqlite3"
        self.store = JobStore(self.path)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_enqueue_replay_is_canonical_and_never_resets_budget_or_state(self):
        first = self.store.enqueue("a", {"z": 1, "a": [True, "æ"]}, max_attempts=1, now=10)
        replay = self.store.enqueue("a", {"a": [True, "æ"], "z": 1}, max_attempts=99, now=20)
        self.assertEqual(first, replay)
        self.assertEqual(replay["max_attempts"], 1)
        with self.assertRaises(JobConflictError):
            self.store.enqueue("a", {"z": 1.0, "a": [True, "æ"]}, now=20)
        claimed = self.store.claim("w", 20, 10)
        self.store.complete("a", claimed["token"], {"ok": True}, 21)
        replay = self.store.enqueue("a", {"a": [True, "æ"], "z": 1}, now=30)
        self.assertEqual(replay["status"], "succeeded")
        self.assertEqual(replay["attempts"], 1)
        self.assertIsNone(self.store.claim("other", 31, 10))

    def test_parallel_processes_cannot_double_claim(self):
        self.store.enqueue("one", {"task": "synthetic"}, now=0)
        context = multiprocessing.get_context("spawn")
        ready, results = context.Queue(), context.Queue()
        start = context.Event()
        workers = [context.Process(target=_claim_once, args=(str(self.path), str(i), ready, start, results))
                   for i in range(4)]
        try:
            for worker in workers:
                worker.start()
            for _ in workers:
                ready.get(timeout=20)
            start.set()
            claimed = [results.get(timeout=20) for _ in workers]
            for worker in workers:
                worker.join(20)
                self.assertEqual(worker.exitcode, 0)
            self.assertEqual(len([job for job in claimed if job is not None]), 1)
            self.assertEqual(self.store.get("one")["attempts"], 1)
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join()

    def test_crash_recovery_fences_stale_completion(self):
        self.store.enqueue("crash", {"task": "synthetic"}, max_attempts=2, now=0)
        context = multiprocessing.get_context("spawn")
        reader, writer = context.Pipe(duplex=False)
        worker = context.Process(target=_claim_and_crash, args=(str(self.path), writer))
        worker.start()
        self.assertTrue(reader.poll(20))
        abandoned = reader.recv()
        worker.join(20)
        self.assertEqual(worker.exitcode, 7)
        self.assertIsNone(self.store.claim("early", 109, 10))
        replacement = self.store.claim("replacement", 110, 10)
        self.assertEqual(replacement["attempts"], 2)
        self.assertNotEqual(replacement["token"], abandoned["token"])
        with self.assertRaises(LeaseLostError):
            self.store.complete("crash", abandoned["token"], {"wrong": True}, 111)
        self.store.complete("crash", replacement["token"], {"ok": True}, 111)
        self.store.close()
        self.store = JobStore(self.path)
        self.assertEqual(self.store.get("crash")["result"], {"ok": True})
        self.assertEqual(self.store.counts()["succeeded"], 1)

    def test_repeated_expiry_exhausts_retry_budget(self):
        self.store.enqueue("limited", {}, max_attempts=2, now=0)
        first = self.store.claim("w1", 100, 10)
        second = self.store.claim("w2", 110, 10)
        self.assertEqual(second["attempts"], 2)
        self.assertIsNone(self.store.claim("w3", 120, 10))
        terminal = self.store.get("limited")
        self.assertEqual((terminal["status"], terminal["attempts"]), ("failed", 2))
        self.assertEqual(terminal["error"]["code"], "LEASE_EXPIRED")
        with self.assertRaises(LeaseLostError):
            self.store.fail("limited", first["token"], "late failure", 121)

    def test_explicit_failure_retries_then_stops(self):
        self.store.enqueue("limited", {}, max_attempts=2, now=0)
        job = self.store.claim("w", 100, 10)
        retried = self.store.fail("limited", job["token"], {"code": "JOB_ERROR"}, 101)
        self.assertEqual(retried["status"], "queued")
        job = self.store.claim("w", 102, 10)
        terminal = self.store.fail("limited", job["token"], "still broken", 103)
        self.assertEqual((terminal["status"], terminal["error"]), ("failed", "still broken"))
        self.assertIsNone(self.store.claim("w", 104, 10))

    def test_completion_at_expiry_is_refused_and_renewal_is_fenced(self):
        self.store.enqueue("a", {}, now=0)
        job = self.store.claim("w", 100, 10)
        renewed = self.store.renew("a", job["token"], 105, 20)
        self.assertEqual(renewed["lease_until"], 125)
        self.assertIsNone(self.store.claim("other", 124, 10))
        with self.assertRaises(LeaseLostError):
            self.store.complete("a", job["token"], {}, 125)
        with self.assertRaises(LeaseLostError):
            self.store.renew("a", job["token"], 125, 10)

    def test_status_and_result_rollback_together(self):
        self.store.enqueue("a", {}, now=0)
        job = self.store.claim("w", 100, 10)
        with sqlite3.connect(self.path) as fault:
            fault.execute("""CREATE TRIGGER interrupt_completion BEFORE UPDATE OF status ON jobs
                WHEN NEW.status='succeeded' BEGIN SELECT RAISE(ABORT,'injected failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.complete("a", job["token"], {"complete": True}, 101)
        observed = self.store.get("a")
        self.assertEqual(observed["status"], "running")
        self.assertIsNone(observed["result"])
        self.assertEqual(observed["token"], job["token"])
        with sqlite3.connect(self.path) as fault:
            fault.execute("DROP TRIGGER interrupt_completion")
        completed = self.store.complete("a", job["token"], {"complete": True}, 102)
        self.assertEqual((completed["status"], completed["result"]), ("succeeded", {"complete": True}))

    def test_foreign_database_is_rejected_without_modification(self):
        foreign = Path(self.directory.name) / "foreign.sqlite3"
        with sqlite3.connect(foreign) as connection:
            connection.execute("CREATE TABLE existing_lab(value TEXT)")
            connection.execute("INSERT INTO existing_lab VALUES('leave alone')")
        before = foreign.read_bytes()
        with self.assertRaises(ValueError):
            JobStore(foreign)
        self.assertEqual(foreign.read_bytes(), before)
        with sqlite3.connect(foreign) as connection:
            self.assertEqual(connection.execute("SELECT * FROM existing_lab").fetchall(), [("leave alone",)])

    def test_invalid_arguments_fail_before_creating_or_changing_jobs(self):
        for payload in ([1], {"x": float("nan")}, {"x": float("inf")}, {1: "bad key"}, {"x": object()}):
            with self.subTest(payload=type(payload).__name__), self.assertRaises(ValueError):
                self.store.enqueue("bad", payload, now=0)
        for value in (0, -1, True, 1.0):
            with self.subTest(max_attempts=value), self.assertRaises(ValueError):
                self.store.enqueue("bad", {}, max_attempts=value, now=0)
        for now, lease in ((True, 10), (-1, 10), (0, 0), (0, True), ((1 << 63) - 1, 1)):
            with self.subTest(now=now, lease=lease), self.assertRaises(ValueError):
                self.store.claim("w", now, lease)
        self.assertEqual(self.store.counts(), dict(queued=0, running=0, succeeded=0, failed=0, total=0))
        with self.assertRaises(ValueError):
            self.store.list_jobs("unknown")
        with self.assertRaises(ValueError):
            JobStore(":memory:")
        with self.assertRaises(ValueError):
            JobStore(Path(self.directory.name) / "missing" / "jobs.sqlite3")


if __name__ == "__main__":
    unittest.main()
