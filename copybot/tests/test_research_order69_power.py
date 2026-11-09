"""Director order 69 P3: the power/MDE numbers in research/desk/ORIGINAL_DESIGNS_ORDER69.md (synthetic only)."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.desk import order69_power as p  # noqa: E402


class Formula(unittest.TestCase):
    def test_amendment32_formula(self):
        # (z_0.9875 + z_0.80) * sd / sqrt(n) = (2.2414 + 0.8416) * 1 / 10
        self.assertAlmostEqual(p.mde(1.0, 100), (2.2414 + 0.8416) / 10, places=3)
        self.assertAlmostEqual(p.mde(1.0, 100, alpha=0.05, one_sided=False), (1.9600 + 0.8416) / 10, places=3)

    def test_mde_monotone(self):
        self.assertLess(p.mde(1.0, 80), p.mde(1.0, 40))
        self.assertLess(p.mde(1.0, 50), p.mde(2.0, 50))
        self.assertLess(p.mde(1.0, 50, alpha=0.05), p.mde(1.0, 50, alpha=0.0125))
        with self.assertRaises(ValueError):
            p.mde(0.0, 10)

    def test_t_quantile_close_to_tables(self):
        # t(19) 0.975 = 2.093, t(59) 0.9975 = 2.915 (K3 note), t(51) 0.9875 = 2.31
        self.assertAlmostEqual(p.t_quantile(0.975, 19), 2.093, delta=0.003)
        self.assertAlmostEqual(p.t_quantile(0.9975, 59), 2.915, delta=0.01)
        self.assertGreater(p.mde_t(1.0, 52), p.mde(1.0, 52))


class HeadlineNumbers(unittest.TestCase):
    """The numbers quoted in the note (rounded as written there)."""

    def test_table(self):
        t = p.table()
        self.assertAlmostEqual(t["VB1"]["mde"] * 1e4, 15.7, delta=0.1)          # bp of capital
        self.assertAlmostEqual(t["VB1"]["gross_loss_needed"] * 1e4, 52.7, delta=0.1)
        self.assertAlmostEqual(t["LQ1"]["mde_above_threshold"], 4.0, delta=0.05)  # bp per side
        self.assertAlmostEqual(t["LQ1"]["true_saving_needed"], 9.0, delta=0.05)
        self.assertAlmostEqual(t["EX1"]["mde"] * 1e4, 15.0, delta=0.1)
        self.assertAlmostEqual(t["EX1"]["mde_desc"] * 1e4, 12.1, delta=0.1)
        self.assertAlmostEqual(t["EX1"]["gross_needed_real"] * 1e4, 26.0, delta=0.1)
        self.assertAlmostEqual(t["EX1"]["mde_did_desc"] * 1e4, 13.5, delta=0.1)
        self.assertAlmostEqual(t["EX1"]["ratio_vs_21i_floor"], 0.33, delta=0.01)
        self.assertAlmostEqual(t["EX1"]["sens"][(0.0035, 26)] * 1e4, 21.2, delta=0.1)


class SyntheticPower(unittest.TestCase):
    def test_power_at_mde_is_about_80(self):
        t = p.table()
        self.assertTrue(0.74 <= p.sim_power(t["EX1"]["mde"], 0.0035, 52, reps=1500) <= 0.86)
        self.assertTrue(0.74 <= p.sim_power(5 + t["LQ1"]["mde_above_threshold"], 10.0, 60, mu0=5.0,
                                            reps=1500) <= 0.86)

    def test_size_under_null(self):
        self.assertLessEqual(p.sim_power(0.0, 0.0035, 52, reps=3000), 0.0125 + 0.008)

    def test_fat_tails_do_not_destroy_power(self):
        t = p.table()
        self.assertGreater(p.sim_power(t["VB1"]["mde"], 0.0045, 78, reps=1000, tails="t3"), 0.74)


class BreakDetector(unittest.TestCase):
    def test_kappa1_fires_on_clear_jump_not_on_flat(self):
        rng = random.Random(3)
        flat = [rng.gauss(0, 0.01) for _ in range(168)]
        jump = flat[:150] + [rng.gauss(0, 0.04) for _ in range(18)]
        self.assertTrue(p.upward_break(jump))
        stat, _ = p.kappa1([0.01 * (-1) ** i for i in range(168)])     # constant |r|: no break at all
        self.assertEqual(stat, 0.0)

    def test_downward_or_old_breaks_are_not_events(self):
        rng = random.Random(4)
        down = [rng.gauss(0, 0.04) for _ in range(150)] + [rng.gauss(0, 0.01) for _ in range(18)]
        self.assertFalse(p.upward_break(down))
        old = [rng.gauss(0, 0.01) for _ in range(60)] + [rng.gauss(0, 0.04) for _ in range(108)]
        self.assertFalse(p.upward_break(old))          # k* is far outside the last 24 h

    def test_null_rate_is_small(self):
        self.assertLess(p.null_event_rate(weeks=40, seed=5), 0.1)

    def test_online_episode_detection(self):
        share3, delay3 = p.detects_episode(reps=60, factor=3.0)
        self.assertGreater(share3, 0.9)
        self.assertLessEqual(delay3, 24)
        share15, _ = p.detects_episode(reps=60, factor=1.5)
        self.assertLess(share15, share3)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
