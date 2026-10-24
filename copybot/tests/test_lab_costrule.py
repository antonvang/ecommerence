"""Amendment 21m point 2: option C applies only to liquid markets with enough observed R1 data; otherwise 21i (B)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import costrule, m21iscreen  # noqa: E402
from lab.db import DB  # noqa: E402
from tests import test_lab_costreport as cr  # noqa: E402

H = 3600
T0 = 1_600_000_000 - 1_600_000_000 % H


class Rule(unittest.TestCase):
    def test_c_only_for_liquid_markets_with_observed_data(self):
        liquid = {T0 + i * H: 2e8 / 24 for i in range(800)}
        thin = {T0 + i * H: 1e6 / 24 for i in range(800)}
        h = T0 + 760 * H
        c, rule = costrule.hurdle("BTCUSDT", liquid, h, {"BTCUSDT": 0.0002})
        self.assertEqual(rule, "C")
        self.assertAlmostEqual(c, 2 * (2 * m21iscreen.FEE + 0.0002))
        self.assertEqual(costrule.hurdle("BTCUSDT", liquid, h, {})[1], "B")              # no R1 data yet
        self.assertEqual(costrule.hurdle("XUSDT", thin, h, {"XUSDT": 0.0002})[1], "B")    # not liquid
        self.assertEqual(costrule.hurdle("BTCUSDT", liquid, h, {"BTCUSDT": 0.0})[0], 4 * m21iscreen.FEE)

    def test_no_observed_quantile_before_enough_data(self):
        r = cr.Report("test_groups_model_moves_and_status")
        r.setUp()
        for i in range(48):
            r.add(T0 + i * H, "BTCUSDT", "crypto", 1e-6, z=3.0)
        self.assertEqual(costrule.observed_q95(r.db.q), {})                               # 2 days: too few


if __name__ == "__main__":
    unittest.main()
