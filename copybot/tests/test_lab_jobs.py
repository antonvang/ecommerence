import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import jobs  # noqa: E402
from lab.db import DB  # noqa: E402

T = 1_000_000.0


class Queue(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def test_enqueue_is_idempotent(self):
        a, c1 = jobs.enqueue(self.db, "k|1", "backtest", "E1", {"x": 1}, now=T)
        b, c2 = jobs.enqueue(self.db, "k|1", "backtest", "E1", {"x": 2}, now=T)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(b["payload"], {"x": 1})
        self.assertEqual(jobs.counts(self.db)["queued"], 1)

    def test_priority_kinds_and_single_claim(self):
        jobs.enqueue(self.db, "low", "backtest", priority=80, now=T)
        jobs.enqueue(self.db, "high", "backtest", priority=10, now=T)
        jobs.enqueue(self.db, "other", "report", priority=1, now=T)
        j = jobs.claim(self.db, "w1", ["backtest"], now=T)
        self.assertEqual(j["job_id"], "high")
        self.assertEqual(jobs.claim(self.db, "w2", ["backtest"], now=T)["job_id"], "low")
        self.assertIsNone(jobs.claim(self.db, "w3", ["backtest"], now=T))
        self.assertTrue(jobs.complete(self.db, "high", "w1", {"ok": 1}, now=T + 1))
        self.assertFalse(jobs.complete(self.db, "low", "w1", {}, now=T + 1))     # not the lease owner

    def test_retry_backoff_then_dead_letter(self):
        jobs.enqueue(self.db, "j", "backtest", max_attempts=2, now=T)
        jobs.claim(self.db, "w", ["backtest"], now=T)
        self.assertEqual(jobs.fail(self.db, "j", "w", "boom", now=T), "retry")
        self.assertIsNone(jobs.claim(self.db, "w", ["backtest"], now=T + 5))       # backoff 10 s
        jobs.claim(self.db, "w", ["backtest"], now=T + 11)
        self.assertEqual(jobs.fail(self.db, "j", "w", "boom again", now=T + 12), "failed")
        self.assertEqual(jobs.get(self.db, "j")["status"], "failed")

    def test_timeout_lease_expiry_and_lost_lease(self):
        jobs.enqueue(self.db, "j", "backtest", timeout_s=30, now=T)
        jobs.claim(self.db, "w1", ["backtest"], now=T)
        self.assertIsNone(jobs.claim(self.db, "w2", ["backtest"], now=T + 20))
        self.assertIsNone(jobs.claim(self.db, "w2", ["backtest"], now=T + 31))   # expired now -> 10 s backoff
        j = jobs.claim(self.db, "w2", ["backtest"], now=T + 42)
        self.assertEqual((j["lease_owner"], j["attempts"]), ("w2", 2))
        self.assertFalse(jobs.complete(self.db, "j", "w1", {}, now=T + 43))       # old owner's result discarded
        self.assertTrue(jobs.complete(self.db, "j", "w2", {}, now=T + 43))
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='job.timeout'"))

    def test_dependencies_and_cancellation(self):
        jobs.enqueue(self.db, "a", "fetch", now=T)
        jobs.enqueue(self.db, "b", "backtest", depends_on=["a"], now=T)
        jobs.enqueue(self.db, "c", "report", depends_on=["b"], now=T)
        self.assertIsNone(jobs.claim(self.db, "w", ["backtest"], now=T))
        jobs.claim(self.db, "w", ["fetch"], now=T)
        jobs.complete(self.db, "a", "w", now=T)
        self.assertEqual(jobs.claim(self.db, "w", ["backtest"], now=T)["job_id"], "b")
        jobs.fail(self.db, "b", "w", "bad", now=T, retryable=False)
        jobs.claim(self.db, "w", ["report"], now=T)
        self.assertEqual(jobs.get(self.db, "c")["status"], "cancelled")

    def test_recover_after_restart(self):
        jobs.enqueue(self.db, "j", "backtest", now=T)
        jobs.claim(self.db, "dead-worker", ["backtest"], now=T)
        self.assertEqual(jobs.recover(self.db, now=T + 1), 1)
        self.assertEqual(jobs.get(self.db, "j")["status"], "queued")
        self.assertEqual(jobs.cancel_all(self.db, "stop", "human:t"), 1)

    def test_parallel_workers_never_share_a_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "q.db")
            db = DB(path)
            for i in range(60):
                jobs.enqueue(db, f"j{i}", "backtest", now=T)
            db.close()
            claimed, lock = [], threading.Lock()

            def work(name):
                d = DB(path)
                while True:
                    j = jobs.claim(d, name, ["backtest"])
                    if j is None:
                        break
                    with lock:
                        claimed.append(j["job_id"])
                    jobs.complete(d, j["job_id"], name)
                d.close()
            ts = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(6)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(sorted(claimed), sorted(f"j{i}" for i in range(60)))     # each exactly once
            db = DB(path)
            self.assertEqual(jobs.counts(db)["done"], 60)
            chains, trig = db.verify()
            self.assertTrue(trig and all(b is None for _, b in chains.values()))
            db.close()


if __name__ == "__main__":
    unittest.main()
