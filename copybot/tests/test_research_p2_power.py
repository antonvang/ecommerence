"""Director order 47 P2: power scenarios for the protocol drafts (formulas only)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import p2_power as pp  # noqa: E402


class Power(unittest.TestCase):
    def test_reproduces_amendment_8_point_14(self):
        # PROTOCOL_V3 amendment 8 point 14: power 0.63 at 12 months and 0.30 at 6 months (SR 3.0, alpha_F / 3)
        a = pp.a8_check()
        self.assertAlmostEqual(a["12m"], 0.63, delta=0.01)
        self.assertAlmostEqual(a["6m"], 0.30, delta=0.01)

    def test_monotone(self):
        self.assertLess(pp.sr_power(1.0, 365, 365, 0.05), pp.sr_power(1.0, 730, 365, 0.05))
        self.assertLess(pp.sr_power(1.0, 730, 365, 0.05 / 3), pp.sr_power(1.0, 730, 365, 0.05))
        self.assertLess(pp.sr_power(1.0, 730, 365, 0.05, ac1=0.3), pp.sr_power(1.0, 730, 365, 0.05))

    def test_mde_inverts_power(self):
        m = pp.sr_needed(730, 365, 0.05, 0.8)
        self.assertAlmostEqual(pp.sr_power(m, 730, 365, 0.05), 0.8, places=3)

    def test_dm_and_overlap(self):
        p1, n1 = pp.dm_power(0.05, 20, 730, 0.5, 0.05)
        p2, n2 = pp.dm_power(0.05, 20, 730, 0.8, 0.05)
        self.assertGreater(n1, n2)
        self.assertGreater(p1, p2)
        self.assertAlmostEqual(pp.n_eff_overlap(1, 8, 0.6), 8.0)
        self.assertAlmostEqual(pp.n_eff_overlap(10, 1, 1.0), 1.0)


if __name__ == "__main__":
    unittest.main()
