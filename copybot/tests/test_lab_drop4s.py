"""Amendment 21m point 1: the descriptive leave-one-day-out of the post-hoc 4-sigma drop pattern; recorded as DROPPED."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import drop4s, memory  # noqa: E402

D = 86400
T0 = 1_600_000_000 - 1_600_000_000 % D


class Loo(unittest.TestCase):
    def test_leave_one_out_and_busiest_days(self):
        rows = [{"h": T0 + 3600 * i, "y": 0.2} for i in range(5)]                      # one crash day, 5 events
        rows += [{"h": T0 + d * D, "y": -0.01} for d in range(1, 10)]                 # nine quiet days
        r = drop4s.loo(rows, lambda h: h // D)
        self.assertEqual((r["clusters"], r["events"]), (10, 14))
        self.assertAlmostEqual(r["cluster_mean"], (0.2 - 0.09) / 10)
        self.assertAlmostEqual(r["leave_one_out"]["min"], -0.01)                       # without the crash day
        self.assertAlmostEqual(r["without_k_busiest"][1], -0.01)
        self.assertAlmostEqual(r["share_positive_clusters"], 0.1)

    def test_iso_weeks_start_on_monday(self):
        monday = 1_600_041_600                                                         # 2020-09-14 00:00 UTC, Monday
        self.assertEqual(drop4s._week(monday), drop4s._week(monday + 6 * D + 86399))
        self.assertNotEqual(drop4s._week(monday), drop4s._week(monday - 1))

    def test_dropped_has_a_fixed_retest_rule(self):
        self.assertIn("user", memory.RETEST["DROPPED"])


if __name__ == "__main__":
    unittest.main()
