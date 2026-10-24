"""Amendment 21w and its precision: the edge-decay monitor's thresholds per measure, 'stabil' only with M1's 14 days,
M2 not applicable to LANE_ ledgers, Student's t, and no write of any kind."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import edgemonitor as em  # noqa: E402
from lab.db import DB  # noqa: E402

DAY = 86400
T0 = 1_790_000_000 // DAY * DAY
CM = {"expected_spread": 0.0004, "extra_slippage": 0.0002, "taker_fee": 0.0005, "maker_fee": 0.0}


def ledger(db, led, nets, fills=0, slip=0.0003, age=0.2):
    eq = 10_000.0
    db.append("sim_equity", exp_id=led, ts=T0, equity=eq, cash=eq, exposure=0, peak=eq, drawdown=0)
    for i, n in enumerate(nets):
        eq += n
        db.append("sim_equity", exp_id=led, ts=T0 + i * DAY + 3600, equity=eq, cash=eq, exposure=0, peak=eq, drawdown=0)
    end = T0 + len(nets) * DAY
    for k in range(fills):
        ts = end - 3600 - k
        db.append("sim_orders", order_id=f"{led}{k}", exp_id=led, ts=ts, instrument="X", side="buy", qty=1,
                  limit_px=None, style="taker", reduce_only=0, signal_ref=f"x@{ts - 60}", cost_model=CM)
        db.append("sim_fills", fill_id=f"{led}{k}|0", order_id=f"{led}{k}", exp_id=led, ts=ts, instrument="X",
                  side="buy", px=1.0, qty=1.0, fee=0.0, slippage=slip, liquidity="taker", mid=1.0, book_ts=ts - age)
    return end + 60


class Monitor(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def test_student_t(self):
        self.assertAlmostEqual(em.t_cdf(-2.160, 13), 0.025, places=3)
        self.assertAlmostEqual(em.t_cdf(0.0, 5), 0.5, places=9)
        self.assertAlmostEqual(em.t_cdf(1.96, 10_000), 0.975, places=3)

    def test_few_days_is_insufficient_even_when_execution_is_fine(self):
        now = ledger(self.db, "FWD_a", [5, -3, 4, 2, 1, 0.5], fills=40)
        r = em.ledger(self.db, "FWD_a", now)
        self.assertEqual(r["measures"]["M2"]["status"], em.STABLE)
        self.assertEqual(r["measures"]["M1"]["status"], em.INSUFFICIENT)
        self.assertEqual(r["status"], em.INSUFFICIENT)                       # precision 2: no 'stabil' without M1

    def test_a_losing_ledger_is_no_longer_supported(self):
        nets = [-10 + (i % 3) for i in range(20)]
        r = em.ledger(self.db, "FWD_b", ledger(self.db, "FWD_b", nets))
        self.assertEqual(r["measures"]["M1"]["n_days"], 20)
        self.assertLess(r["measures"]["M1"]["p_one_sided"], 0.05)
        self.assertEqual(r["status"], em.UNSUPPORTED)
        self.assertEqual(r["flagged_by"], ["M1"])

    def test_execution_thresholds_and_lane_exemption(self):
        now = ledger(self.db, "FWD_c", [1] * 3, fills=30, slip=0.0004 * 1.3)  # r = 1.3 > 1.25
        self.assertEqual(em.ledger(self.db, "FWD_c", now)["status"], em.SUSPECT)
        now = ledger(self.db, "FWD_d", [1] * 3, fills=30, slip=0.0004 * 2.1)
        self.assertEqual(em.ledger(self.db, "FWD_d", now)["status"], em.UNSUPPORTED)
        now = ledger(self.db, "LANE_e", [1] * 3, fills=30, slip=0.0004 * 8)    # precision 1
        r = em.ledger(self.db, "LANE_e", now)
        self.assertEqual(r["measures"]["M2"]["status"], em.NOT_APPLICABLE)
        self.assertAlmostEqual(r["measures"]["M2"]["ratio"], 8.0)            # still shown, descriptively
        self.assertEqual(r["status"], em.INSUFFICIENT)

    def test_book_age_and_concentration(self):
        now = ledger(self.db, "FWD_f", [1] * 3, fills=30, age=45)
        self.assertEqual(em.ledger(self.db, "FWD_f", now)["measures"]["M4"]["status"], em.SUSPECT)
        nets = [100, 90, 80] + [-1] * 27
        r = em.ledger(self.db, "FWD_g", ledger(self.db, "FWD_g", nets))
        self.assertGreaterEqual(r["measures"]["M5"]["share"], 1.0)
        self.assertEqual(r["measures"]["M5"]["status"], em.UNSUPPORTED)
        self.assertEqual(r["measures"]["M1"]["n_days"], em.WINDOW_DAYS)      # the window is the last 28 days

    def test_history_is_as_of_each_closed_day(self):
        now = ledger(self.db, "FWD_i", [1.0] * 5, fills=0)
        h = em.history(self.db, "FWD_i", now, days=3)
        self.assertEqual([x["measures"]["M1"]["n_days"] for x in h], [3, 4, 5])
        self.assertEqual([x["asof"] % DAY for x in h], [DAY - 1] * 3)
        self.assertTrue(all(x["measures"]["M3"]["status"] == em.INSUFFICIENT for x in h))     # M3 only now
        later = T0 + 5 * DAY + 3 * 3600                                    # a mark after the as-of time is not read
        self.db.append("sim_equity", exp_id="FWD_i", ts=later, equity=1.0, cash=1.0, exposure=0, peak=1.0, drawdown=0)
        em._HIST.clear()
        self.assertEqual(em.history(self.db, "FWD_i", now, days=3)[-1]["measures"]["M1"]["mean_usd"], 1.0)

    def test_boundaries_missing_data_and_account_types(self):
        r = lambda led, **kw: em.ledger(self.db, led, ledger(self.db, led, **kw))
        # M2: > 1.25 and > 2.0 are strict; exactly at the line is the milder status
        self.assertEqual(r("FWD_m1", nets=[1] * 3, fills=30, slip=0.0004 * 1.25)["measures"]["M2"]["status"], em.STABLE)
        self.assertEqual(r("FWD_m2", nets=[1] * 3, fills=30, slip=0.0004 * 2.0)["measures"]["M2"]["status"], em.SUSPECT)
        self.assertEqual(r("FWD_m3", nets=[1] * 3, fills=29, slip=0.0004 * 9)["measures"]["M2"]["status"],
                         em.INSUFFICIENT)                                   # 29 fills: below the sample
        self.assertEqual(r("SHADOW_m4", nets=[1] * 3, fills=30, slip=0.0004 * 2.1)["measures"]["M2"]["status"],
                         em.UNSUPPORTED)                                    # shadow ledgers keep M2
        # M4: > 30 s strict
        self.assertEqual(r("FWD_m5", nets=[1] * 3, fills=30, age=30)["measures"]["M4"]["status"], em.STABLE)
        # M1: 13 days insufficient, 14 measured; one outlier day decides nothing alone
        self.assertEqual(r("FWD_m6", nets=[-5] * 13)["measures"]["M1"]["status"], em.INSUFFICIENT)
        m1 = r("FWD_m7", nets=[2, 1, 3, 2, 1, 2, 3, 1, 2, 2, 1, 3, 2, -200])["measures"]["M1"]
        self.assertEqual((m1["n_days"], m1["status"]), (14, em.SUSPECT))   # mean < 0, but p is not < 0.05
        self.assertGreater(m1["p_one_sided"], 0.05)
        # M5: >= 0.75 inclusive; a non-positive net has no share
        m5 = r("FWD_m8", nets=[30, 30, 30] + [0.5] * 23 + [-2.5, -2.5])["measures"]["M5"]      # exactly 28 days
        self.assertAlmostEqual(m5["share"], 90 / 96.5)
        self.assertEqual(m5["status"], em.SUSPECT)
        self.assertIsNone(r("FWD_m9", nets=[-1] * 30)["measures"]["M5"]["share"])
        # a fill without a cost model is left out of M2, not guessed
        led = "FWD_m10"
        now = ledger(self.db, led, nets=[1] * 3, fills=30)
        self.db.append("sim_orders", order_id="x", exp_id=led, ts=now - 100, instrument="X", side="buy", qty=1,
                       limit_px=None, style="taker", reduce_only=0, signal_ref="x@1", cost_model=None)
        self.db.append("sim_fills", fill_id="x|0", order_id="x", exp_id=led, ts=now - 100, instrument="X", side="buy",
                       px=1.0, qty=1.0, fee=0.0, slippage=0.5, liquidity="taker", mid=1.0, book_ts=now - 100.5)
        self.assertEqual(em.ledger(self.db, led, now)["measures"]["M2"]["n_fills"], 30)
        # an account with no marks at all
        self.assertEqual(em.ledger(self.db, "FWD_none", T0)["status"], em.INSUFFICIENT)

    def test_the_view_writes_nothing(self):
        now = ledger(self.db, "FWD_h", [1, 2], fills=3)
        before = self.db.one("SELECT COUNT(*) FROM events")[0], self.db.one("SELECT COUNT(*) FROM observations")[0]
        v = em.view(self.db, now)
        self.assertEqual(v["by_status"], {em.INSUFFICIENT: 1})
        self.assertEqual(before, (self.db.one("SELECT COUNT(*) FROM events")[0],
                                  self.db.one("SELECT COUNT(*) FROM observations")[0]))
        json.dumps(v)


if __name__ == "__main__":
    unittest.main()
