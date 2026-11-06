"""Director order 45 P1: the Donchian power calculation is pure arithmetic on stated assumptions (no data, no network)."""
import math
import os
import sys
import unittest
from statistics import NormalDist

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import donchian_power as dp  # noqa: E402


class DonchianPower(unittest.TestCase):
    def test_lo_factor_is_one_without_autocorrelation(self):
        self.assertAlmostEqual(dp.lo_factor(0.0), 1.0)
        self.assertGreater(dp.lo_factor(0.1), 1.0)

    def test_memmel_variance_reduces_to_two_one_minus_rho_for_zero_sharpe(self):
        self.assertAlmostEqual(dp.var_dsr_daily(0, 0, 0.6, 100), 2 * 0.4 / 100)

    def test_alpha_mde_matches_the_textbook_formula(self):
        sc = dict(dp.SCENARIO, ac1=0.0, years=4.0)
        k = NormalDist().inv_cdf(0.95) + NormalDist().inv_cdf(0.80)
        want = k * sc["vol_trend"] * math.sqrt(1 - sc["rho"] ** 2) / 2.0
        self.assertAlmostEqual(dp.mde_alpha(sc, 0.05), want)
        self.assertAlmostEqual(dp.years_for_alpha(sc, want, 0.05), 4.0)

    def test_more_years_and_higher_alpha_shrink_the_mde(self):
        sc = dict(dp.SCENARIO)
        self.assertLess(dp.mde_dsr(dict(sc, years=10), 0.05), dp.mde_dsr(sc, 0.05))
        self.assertLess(dp.mde_dsr(sc, 0.05), dp.mde_dsr(sc, 0.005))

    def test_effective_count_of_correlated_coins(self):
        self.assertAlmostEqual(dp.n_eff(20, 0.0), 20)
        self.assertAlmostEqual(dp.n_eff(20, 1.0), 1)

    def test_build_is_deterministic(self):
        a, b = dp.build(5), dp.build(5)
        self.assertEqual(a, b)
        self.assertIn(a["verdict"], ("GO", "INSUFFICIENT POWER"))


if __name__ == "__main__":
    unittest.main()
