"""Operational conformance fixes (mission audit step 1): idle agents do not take the write lock or rewrite an unchanged
heartbeat every tick, agent result summaries stay valid JSON, and the watcher checks the hourly paper marks."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, jobs, watch  # noqa: E402
from lab.db import DB  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labstep1")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class IdleAgents(Base):
    def test_an_idle_job_agent_neither_claims_nor_rewrites_an_unchanged_heartbeat(self):
        jobs.init(self.db)
        a = fleet.Agent("data-1", "data agent", kinds=("data",), db_path=self.path)
        clock = {"t": 1_000_000.0}
        writes = []
        real = fleet._beat
        with mock.patch.object(jobs, "claim", side_effect=AssertionError("claim must not run on an empty queue")), \
                mock.patch.object(fleet.time, "time", lambda: clock["t"]), \
                mock.patch.object(fleet, "_beat", lambda *x, **k: writes.append(clock["t"]) or real(*x, **k)):
            for _ in range(10):                                    # ten 1 s ticks
                a(self.db)
                clock["t"] += 1
            self.assertEqual(len(writes), 1)
            clock["t"] += fleet.QUIET_BEAT_S
            a(self.db)
            self.assertEqual(len(writes), 2)                       # still alive for the supervisor and dashboard
        jobs.enqueue(self.db, "data|E_x", "data", "E_x", {}, actor="system:t")
        self.assertTrue(jobs.runnable_any(self.db, ("data",)))
        self.assertFalse(jobs.runnable_any(self.db, ("cost",)))
        jobs.enqueue(self.db, "cost|E_x", "cost", "E_x", {}, depends_on=("data|E_x",), actor="system:t")
        self.assertTrue(jobs.runnable_any(self.db, ("cost",)))            # blocked: claim() must run to unblock it
        j = jobs.claim(self.db, "data-1", ("data",))
        self.db.con.execute("UPDATE jobs SET lease_until=0 WHERE job_id=?", (j["job_id"],))
        self.assertTrue(jobs.runnable_any(self.db, ("report",)))          # an expired lease anywhere: claim retries it


class Summary(unittest.TestCase):
    def test_a_large_result_is_summarised_as_valid_json(self):
        res = {"experiments": 11, "simulated": True, "results": {
            f"FWD_E_strategy_number_{i}": {"status": "ok", "orders": [{"symbol": "X", "status": "filled"}] * i,
                                          "pnl": {"equity": 10000.0 - i}} for i in range(11)}}
        s = fleet._summary(res)
        parsed = json.loads(s)                                     # was cut mid-string at 300 characters
        self.assertEqual(parsed["experiments"], 11)
        self.assertEqual(parsed["results"]["FWD_E_strategy_number_3"], "ok/3")
        self.assertEqual(json.loads(fleet._summary({"a": "x" * 5000}))["a"], "x" * 80)


class PaperWatch(Base):
    def setUp(self):
        super().setUp()
        self.now = time.time()
        self.db.event("system.running", "system:supervisor", None, {"pid": 1})
        self.started = self.db.one("SELECT MAX(ts) FROM events WHERE kind='system.running'")[0]
        for e in ("E_a", "E_b"):
            self.db.event("forward.approved", "human:anton", e, {"reason": "fixture forward test"})
            self.db.event("paper.started", "agent:paper-1", "FWD_" + e, {"capital": 10000})
        self.db.event("forward.stopped", "human:anton", "E_b", {"reason": "stopped: not judged any more"})
        self.sup = {"status": "running"}

    def mark(self, led, ts):
        self.db.append("sim_equity", exp_id=led, ts=int(ts), equity=10000.0, cash=10000.0, exposure=0.0,
                       peak=10000.0, drawdown=0.0)

    def test_hourly_marks_and_long_pauses_are_checked_for_active_ledgers_only(self):
        t = self.started + 3 * 3600
        self.mark("FWD_E_a", t - 1800)
        ok, why = watch._paper(self.path, t, self.sup)
        self.assertTrue(ok, why)                                   # FWD_E_b is stopped: not judged
        ok, why = watch._paper(self.path, t + 4 * 3600, self.sup)
        self.assertFalse(ok)
        self.assertIn("FWD_E_a", why)
        self.mark("FWD_E_a", t + 4 * 3600 - 60)
        self.db.append("risk_events", exp_id="FWD_E_a", ts=int(t), rule="max_drawdown", value=0.12, threshold=0.1,
                       action="PAUSE", detail="fixture", actor="system:risk")
        ok, why = watch._paper(self.path, t + 4 * 3600, self.sup)
        self.assertTrue(ok)
        self.assertIn("paused: FWD_E_a", why)
        self.mark("FWD_E_a", t + 26 * 3600 - 60)
        ok, why = watch._paper(self.path, t + 26 * 3600, self.sup)
        self.assertFalse(ok)
        self.assertIn("paused for over a day", why)
        self.assertIsNone(watch._paper(self.path, t, {"status": "stopped"})[0])


if __name__ == "__main__":
    unittest.main()
