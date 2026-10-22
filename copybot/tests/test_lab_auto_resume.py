"""research/PROTOCOL_V3.md amendment 18: a data_fetch pause on a simulated ledger lifts itself once the full fetch has
worked in an unbroken run of probes for at least 50 minutes; at most 2 per ledger per 24 h, never at the drawdown
limit, and every other pause rule stays human-only. Temporary databases only; no network, no order is ever sent."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lab import command, lane  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.risk import AUTO_MAX, Risk  # noqa: E402
import test_lab_lane as tl  # noqa: E402

L = "FWD_E_xs_momentum_p2"
NOW = 1792416000.0
HOUR, DAY = 3600, 86400


def ok():
    return None


def fail():
    raise OSError("[Errno 113] No route to host")


class Rules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labauto")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.t = NOW
        self.risk = Risk(self.db, now=lambda: self.t)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def at(self, t, probe, ledger=L):
        self.t = t
        return self.risk.auto_resume(ledger, probe)

    def probes(self, ledger=L):
        return [r["value"] for r in self.db.q("SELECT value FROM risk_events WHERE exp_id=? AND action='PROBE' "
                                              "ORDER BY id", ledger)]

    def test_resumes_after_an_hour_of_working_data(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture: no route to host")
        self.assertFalse(self.at(NOW + HOUR, ok))                  # the first working probe only starts the run
        self.assertTrue(self.risk.paused(L))
        self.assertTrue(self.at(NOW + 2 * HOUR, ok))
        self.assertFalse(self.risk.paused(L))
        c = self.db.one("SELECT rule, actor, detail FROM risk_events WHERE exp_id=? AND action='CLEAR'", L)
        self.assertEqual((c["rule"], c["actor"]), ("auto_resume", "system:risk"))
        self.assertIn("amendment 18", c["detail"])
        self.assertEqual(self.probes(), [1])

    def test_a_failure_restarts_the_run(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture")
        self.assertFalse(self.at(NOW + HOUR, ok))
        self.assertFalse(self.at(NOW + 2 * HOUR, fail))
        self.assertFalse(self.at(NOW + 3 * HOUR, ok))
        self.assertTrue(self.risk.paused(L))
        self.assertEqual(self.probes(), [1, 0, 1])
        self.assertIn("No route to host", self.db.one("SELECT detail FROM risk_events WHERE exp_id=? AND action='PROBE' "
                                                      "AND value=0", L)[0])
        self.assertTrue(self.at(NOW + 4 * HOUR, ok))

    def test_less_than_fifty_minutes_is_not_enough(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture")
        self.assertFalse(self.at(NOW + 600, ok))
        self.assertFalse(self.at(NOW + 600 + 49 * 60, ok))
        self.assertTrue(self.risk.paused(L))
        self.assertTrue(self.at(NOW + 600 + 50 * 60, ok))

    def test_every_other_rule_stays_human_only(self):
        for rule in ("data_stale", "data_missing", "data_inconsistent", "max_drawdown", "spread"):
            with self.subTest(rule=rule):
                led = f"SHADOW_E_{rule}"
                self.risk.pause(led, rule, None, None, "fixture")
                for k in range(1, 5):
                    self.assertFalse(self.at(NOW + k * HOUR, ok, led))
                self.assertTrue(self.risk.paused(led))
                self.assertEqual(self.probes(led), [])

    def test_never_an_approved_strategy(self):
        self.risk.pause("E_real", "data_fetch", None, None, "fixture")
        for k in range(1, 4):
            self.assertFalse(self.at(NOW + k * HOUR, ok, "E_real"))
        self.assertTrue(self.risk.paused("E_real"))

    def test_not_at_the_drawdown_limit(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture")
        self.db.append("sim_equity", exp_id=L, ts=int(NOW), equity=9000.0, cash=9000.0, exposure=0.0, peak=10000.0,
                       drawdown=0.10)
        for k in range(1, 4):
            self.assertFalse(self.at(NOW + k * HOUR, ok))
        self.assertTrue(self.risk.paused(L))
        self.assertEqual(self.probes(), [0, 0, 0])

    def test_at_most_two_per_day_then_a_human(self):
        t = NOW
        for _ in range(AUTO_MAX):
            self.t = t
            self.risk.pause(L, "data_fetch", None, None, "fixture")
            self.assertFalse(self.at(t + HOUR, ok))
            self.assertTrue(self.at(t + 2 * HOUR, ok))
            t += 3 * HOUR
        self.t = t
        self.risk.pause(L, "data_fetch", None, None, "fixture")
        n = len(self.probes())
        for k in range(1, 6):
            self.assertFalse(self.at(t + k * HOUR, ok))
        self.assertEqual(len(self.probes()), n)                    # capped: no more probes are written
        self.assertTrue(self.risk.paused(L))
        self.assertTrue(self.risk.resume_simulated(L, "human:anton", "fixture: a human looked at it"))
        self.t = NOW + DAY + 1                                     # a day after the first automatic resume
        self.risk.pause(L, "data_fetch", None, None, "fixture")
        self.assertFalse(self.at(NOW + DAY + HOUR, ok))            # both automatic resumes are within 24 h
        self.assertFalse(self.at(NOW + DAY + 2 * HOUR, ok))        # the first has aged out: the run starts
        self.assertTrue(self.at(NOW + DAY + 4 * HOUR, ok))

    def test_a_human_resume_still_works_and_nothing_runs_when_not_paused(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture")
        self.assertTrue(self.risk.resume_simulated(L, "human:anton", "fixture: network is back"))
        self.assertFalse(self.at(NOW + HOUR, lambda: self.fail("no probe while not paused")))
        self.assertEqual(self.probes(), [])

    def test_the_dashboard_says_a_data_pause_lifts_itself(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture")
        self.risk.pause("SHADOW_E_x", "max_drawdown", 0.1, 0.1, "fixture")
        self.assertIn("amendment 18", command._pause_info(self.risk, L)["resume"])
        self.assertNotIn("amendment 18", command._pause_info(self.risk, "SHADOW_E_x")["resume"])


class LaneAccount(tl.Base):
    def test_a_lane_account_resumes_and_trades_in_the_same_pass(self):
        led = self.started()

        def down(path):
            raise OSError("[Errno 113] No route to host")
        r = lane.run_one(self.db, led, down, tl.NOW)
        self.assertEqual(r["status"], "paused")
        self.assertEqual(Risk(self.db).paused(led), True)
        get = tl.market()
        get.now = tl.NOW + HOUR
        self.assertEqual(lane.run_one(self.db, led, get, tl.NOW + HOUR)["status"], "paused")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", led)[0], 0)
        get.now = tl.NOW + 2 * HOUR
        r = lane.run_one(self.db, led, get, tl.NOW + 2 * HOUR)
        self.assertEqual(r["status"], "ok", r)
        self.assertFalse(Risk(self.db).paused(led))
        self.assertGreater(self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", led)[0], 0)

    def test_a_stale_lane_probe_does_not_resume(self):
        led = self.started()
        Risk(self.db, lambda: tl.NOW).pause(led, "data_fetch", None, None, "fixture")
        get = tl.market()
        for k in (1, 2, 3):
            get.now = tl.NOW - DAY                          # the bars end a day before the pass
            self.assertEqual(lane.run_one(self.db, led, get, tl.NOW + k * HOUR)["status"], "paused")
        self.assertTrue(Risk(self.db).paused(led))
        self.assertEqual([r[0] for r in self.db.q("SELECT value FROM risk_events WHERE exp_id=? AND action='PROBE'",
                                                  led)], [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
