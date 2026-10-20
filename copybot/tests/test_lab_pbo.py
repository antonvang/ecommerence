"""PBO / CSCV (lab/engine/pbo.py): checked on cases whose answer is known."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.engine import pbo  # noqa: E402


def noise(n, t, seed, drift=0.0):
    rng = random.Random(seed)
    return [[rng.gauss(drift, 0.01) for _ in range(t)] for _ in range(n)]


class CSCV(unittest.TestCase):
    def test_pure_noise_is_overfit_about_half_the_time(self):
        vals = [pbo.cscv(noise(20, 400, seed), s=8)["pbo"] for seed in range(12)]
        self.assertGreater(sum(vals) / len(vals), 0.3)        # the IS winner of pure noise is a coin flip OOS
        self.assertLess(sum(vals) / len(vals), 0.7)

    def test_one_real_edge_among_noise_is_not_overfit(self):
        rows = noise(19, 400, 5)
        rows.append([v + 0.004 for v in noise(1, 400, 99)[0]])   # Sharpe about 7.6 a year
        r = pbo.cscv(rows, s=8)
        self.assertLess(r["pbo"], 0.05)
        self.assertLess(r["prob_oos_loss"], 0.05)
        self.assertGreater(r["oos_sharpe_of_selected_mean"], 3)

    def test_all_combinations_and_a_cap(self):
        r = pbo.cscv(noise(4, 64, 1), s=8)
        self.assertEqual((r["combinations"], r["combinations_total"]), (70, math.comb(8, 4)))
        self.assertEqual(pbo.cscv(noise(4, 64, 1), s=8, max_combinations=10)["combinations"], 10)

    def test_aggregated_sharpe_equals_direct(self):
        x = noise(1, 101, 3)[0]
        n, s1, s2 = len(x), math.fsum(x), math.fsum(v * v for v in x)
        m = s1 / n
        sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
        self.assertAlmostEqual(pbo._sharpe(n, s1, s2), m / sd * math.sqrt(365), places=9)
        self.assertEqual(pbo._sharpe(5, 0.0, 0.0), 0.0)            # flat: zero, not infinite

    def test_blocks_cover_every_period_once(self):
        b = pbo._blocks(103, 16)
        self.assertEqual((b[0][0], b[-1][1], len(b)), (0, 103, 16))
        self.assertTrue(all(b[i][1] == b[i + 1][0] for i in range(15)))

    def test_ranks_with_ties(self):
        self.assertEqual(pbo._ranks([3, 1, 3, 2]), [3.5, 1, 3.5, 2])

    def test_invalid_input(self):
        for args, kw in (((noise(1, 100, 1),), {}), (([[0.0] * 10, [0.0] * 11],), {}),
                         ((noise(3, 100, 1),), {"s": 7}), ((noise(3, 20, 1),), {"s": 16})):
            with self.assertRaises(pbo.PBOError):
                pbo.cscv(*args, **kw)


if __name__ == "__main__":
    unittest.main()
