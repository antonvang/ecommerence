"""Real-duration heartbeat and stale-token worker regression tests."""

from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from job_store import JobStore
import research_runner as runner


class WorkerLeaseTests(unittest.TestCase):
    def setUp(self):
        work = Path("/workspace/work")
        work.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="runner-leases-", dir=work)
        self.path = Path(self.directory.name) / "jobs.sqlite3"
        with JobStore(self.path) as store:
            store.enqueue("long-job", {"task": "synthetic"}, max_attempts=3)

    def tearDown(self):
        self.directory.cleanup()

    def test_job_longer_than_lease_is_claimed_and_completed_once(self):
        started = threading.Event()
        calls, errors, stolen = [], [], []

        def calculate(payload, owner_signers=None):
            calls.append(payload)
            started.set()
            time.sleep(4.2)  # Longer than the real three-second lease.
            return {"status": "COMPLETE", "synthetic": True}

        def execute():
            try:
                runner.worker(self.path, "long-worker", lease_s=3)
            except BaseException as error:
                errors.append(error)

        worker = threading.Thread(target=execute, daemon=True)
        with mock.patch.object(runner, "engines"), mock.patch.object(runner, "evaluate_payload", calculate):
            worker.start()
            try:
                self.assertTrue(started.wait(3), "computation did not start")
                with JobStore(self.path) as competitor:
                    deadline = time.monotonic() + 9
                    while worker.is_alive() and time.monotonic() < deadline:
                        claimed = competitor.claim("competitor", int(time.time()), lease_s=3)
                        if claimed is not None:
                            stolen.append(claimed)
                        time.sleep(0.15)
                worker.join(3)
                self.assertFalse(worker.is_alive(), "worker failed to terminate")
            finally:
                worker.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(stolen, [])
        self.assertEqual(len(calls), 1)
        with JobStore(self.path) as store:
            job = store.get("long-job")
            self.assertEqual((job["status"], job["attempts"]), ("succeeded", 1))
            self.assertEqual(job["result"], {"status": "COMPLETE", "synthetic": True})
            self.assertEqual(store.counts()["succeeded"], 1)
        self.assertFalse(any(thread.name.startswith("lease-heartbeat-long-worker-")
                             for thread in threading.enumerate()))

    def _replacement_claim(self):
        with JobStore(self.path) as store:
            replacement = store.claim("replacement", int(time.time()) + 20, lease_s=3)
            self.assertIsNotNone(replacement)
            return replacement

    def test_stale_completion_does_not_crash_or_overwrite_replacement(self):
        replacement = []

        def calculate(payload, owner_signers=None):
            replacement.append(self._replacement_claim())
            return {"status": "COMPLETE", "stale": True}

        with mock.patch.object(runner, "engines"), mock.patch.object(runner, "evaluate_payload", calculate):
            runner.worker(self.path, "stale-worker", lease_s=3)
        with JobStore(self.path) as store:
            job = store.get("long-job")
            self.assertEqual(job["status"], "running")
            self.assertEqual(job["token"], replacement[0]["token"])
            self.assertIsNone(job["result"])
        self.assertFalse(any(thread.name.startswith("lease-heartbeat-stale-worker-")
                             for thread in threading.enumerate()))

    def test_stale_failure_reporting_does_not_crash_worker(self):
        replacement = []

        def calculate(payload, owner_signers=None):
            replacement.append(self._replacement_claim())
            raise ValueError("calculation failed after lease ownership changed")

        with mock.patch.object(runner, "engines"), mock.patch.object(runner, "evaluate_payload", calculate):
            runner.worker(self.path, "failing-worker", lease_s=3)
        with JobStore(self.path) as store:
            job = store.get("long-job")
            self.assertEqual((job["status"], job["attempts"]), ("running", 2))
            self.assertEqual(job["token"], replacement[0]["token"])
            self.assertEqual(job["error"]["code"], "LEASE_EXPIRED")
            self.assertNotIn("type", job["error"])
        self.assertFalse(any(thread.name.startswith("lease-heartbeat-failing-worker-")
                             for thread in threading.enumerate()))

    def test_too_short_or_noninteger_lease_is_rejected_before_claim(self):
        with mock.patch.object(runner, "engines") as integrity_gate:
            for value in (0, 1, 2, True, 3.0):
                with self.subTest(lease=value), self.assertRaises(runner.StudyError):
                    runner.worker(self.path, "bad-worker", lease_s=value)
            integrity_gate.assert_not_called()
        with JobStore(self.path) as store:
            self.assertEqual(store.get("long-job")["attempts"], 0)


if __name__ == "__main__":
    unittest.main()
