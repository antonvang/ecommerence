"""Director order 56 P3: the fomo power model is internally consistent (synthetic, fast cells only)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.desk.fomo import power  # noqa: E402


class FomoPower(unittest.TestCase):
    def test_breakeven_gives_zero_mean(self):
        for l_mean in power.L_GRID:
            p = power.breakeven_p(l_mean)
            mu, _ = power.moments(p, l_mean)
            self.assertAlmostEqual(mu, 0.0, places=12)

    def test_documented_breakeven_values(self):
        self.assertAlmostEqual(power.breakeven_p(-0.6), 0.0659, places=4)
        self.assertAlmostEqual(power.breakeven_p(-0.4), 0.0449, places=4)

    def test_power_monotone_in_n_for_losing_copy(self):
        a = [power.analytic(0.01, -0.6, n)["falsified"] for n in power.N_GRID]
        self.assertEqual(a, sorted(a))
        self.assertGreater(a[-1], 0.99)

    def test_mc_deterministic_and_bounded(self):
        s1 = power.simulate(0.03, -0.6, 70, reps=200)
        s2 = power.simulate(0.03, -0.6, 70, reps=200)
        self.assertEqual(s1, s2)
        self.assertLessEqual(s1["falsified"] + s1["positive"], 1.0)

    def test_no_positive_when_clearly_losing(self):
        self.assertEqual(power.simulate(0.01, -0.8, 140, reps=200)["positive"], 0.0)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
