"""Amendment 21k point 1: the observed cost report groups class x session and markets, bootstraps over day
clusters, compares with the 21i estimate, separates move hours, and stays PRELIMINARY until 7 days and 2 weekends."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import costreport, m21iscreen  # noqa: E402
from lab.db import DB  # noqa: E402

T0 = 1_800_000_000 - 1_800_000_000 % 86400


class Report(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def add(self, ts, sym, cls, rt, off=False, z=0.5, flagged=False, vr=1.0, q1=1e6):
        a = self.db.append
        a("observations", ts=ts, detector="abnormal_move/1", source="s", instrument=sym, metric="z_1h", value=z,
          threshold=4.0, flagged=0, payload={"z_1h": z, "volume_ratio": vr, "quote_volume_1h": q1})
        if flagged:
            a("observations", ts=ts, detector="abnormal_move/1", source="s", instrument=sym, metric="volume_ratio",
              value=6.0, threshold=5.0, flagged=1, payload={})
        a("observations", ts=ts, detector="abnormal_move/1", source="d", instrument=sym, metric="book_rt", value=rt,
          threshold=None, flagged=0, payload={"class": cls, "off_hours": off, "spread": rt})

    def test_groups_model_moves_and_status(self):
        for h in range(48):
            ts = T0 + h * 3600
            self.add(ts, "BTCUSDT", "crypto", 1e-6)
            self.add(ts, "XAUUSDT", "commodity", 2e-5 if h % 2 else None, off=h < 24,
                     z=3.0 if h == 5 else 0.1, flagged=h == 7)
        r = costreport.report(self.db.q, now=T0 + 49 * 3600)
        self.assertEqual(r["status"], "PRELIMINARY")
        self.assertEqual(set(r["groups"]), {"crypto|regular", "tradfi|off_hours", "tradfi|regular"})
        x = r["markets"]["XAUUSDT"]
        self.assertEqual((x["n"], x["missing_book"], x["days"]), (48, 24, 2))
        self.assertEqual(x["move_hours"]["n"], 2)                                  # |z| >= 2 and a flag
        self.assertAlmostEqual(x["model_rt_median"], m21iscreen.rt_est(24e6))
        self.assertIsNotNone(r["markets"]["BTCUSDT"]["median_ci95_day_bootstrap"])
        # 21l: half of XAU's books are missing (too thin) -> the censored median is the upper bound (inf)
        self.assertEqual(x["median_upper_missing_as_inf"], float("inf"))
        self.assertAlmostEqual(x["bp"]["median"], 0.2)
        self.assertEqual(x["conclusion"], "too few data")                          # 2 days, 48 obs, 2 move hours
        t = r["decision_table"]["XAUUSDT"]
        self.assertEqual(t["recommendation"], "NO_DECISION")
        self.assertFalse(t["requirements"]["days >= 7"])
        self.assertIsNone(t["C"])                                                  # never shown before the gates
        self.assertAlmostEqual(r["markets"]["BTCUSDT"]["total_round_trip_bp_with_fees"], 10.01)
        self.assertIn("never added", " ".join(r["notes"]))

    def test_b_and_c_side_by_side_once_a_market_has_enough_data(self):
        start = T0 - (T0 // 86400 + 3) % 7 * 86400 + 5 * 86400                     # a Saturday (epoch day 0 = Thu)
        for h in range(16 * 24):
            self.add(start + h * 3600, "BTCUSDT", "crypto", 1e-6 * (1 + h % 3), z=3.0 if h % 10 == 0 else 0.1,
                     vr=1.0, q1=1e7)                                                # 24 x 1e7 = 240 M a day: liquid
        m = costreport.report(self.db.q)["markets"]["BTCUSDT"]
        self.assertEqual(m["conclusion"], "enough data")
        bc = m["B_vs_C"]
        self.assertTrue(bc["liquid"])
        self.assertAlmostEqual(bc["B"], 0.0046)                                     # the floor
        self.assertAlmostEqual(bc["C"], max(4 * 0.0004, 2 * (2 * 0.0004 + bc["q95"])))
        self.assertIn("never activated automatically", bc["note"])
        t = costreport.report(self.db.q)["decision_table"]["BTCUSDT"]                   # 21o point 2
        self.assertTrue(all(t["requirements"].values()))
        self.assertEqual(t["recommendation"], "can be put to the user")
        self.assertIn("transfer of 2026 costs to 2020-21 (explore0)", t["assumed_inputs"])

    def test_sufficiency_is_fixed_in_advance(self):
        self.assertFalse(costreport.sufficient({"days": 7, "n": 100}, {"n": 10}, weekends=1))   # 21n: 2 weekends
        self.assertTrue(costreport.sufficient({"days": 7, "n": 100}, {"n": 10}))
        self.assertFalse(costreport.sufficient({"days": 7, "n": 100}, {"n": 9}))
        self.assertFalse(costreport.sufficient({"days": 6, "n": 500}, {"n": 50}))

    def test_reads_only(self):
        self.add(T0, "BTCUSDT", "crypto", 1e-6)
        before = self.db.one("SELECT COUNT(*) FROM observations")[0]
        costreport.report(self.db.q)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM observations")[0], before)


if __name__ == "__main__":
    unittest.main()
