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

    def test_known_limitation_persistent_noise_looks_not_overfit(self):
        # documented in research/studies/PBO_PERSISTENCE_2026-10-21.md: no skill, AR(1) phi 0.98 -> PBO well below 0.5
        vals = []
        for seed in range(6):
            rng = random.Random(500 + seed)
            rows = []
            for _ in range(20):
                x, out = 0.0, []
                for _ in range(400):
                    x = 0.98 * x + math.sqrt(1 - 0.98 ** 2) * rng.gauss(0, 1)
                    out.append(0.01 * x)
                rows.append(out)
            vals.append(pbo.cscv(rows, s=8)["pbo"])
        self.assertLess(sum(vals) / len(vals), 0.4)

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



class EffectiveTrials(unittest.TestCase):
    def test_identical_series_count_as_one(self):
        x = noise(1, 300, 4)[0]
        r = pbo.effective_trials([x, x, x, x, x])
        self.assertAlmostEqual(r["mean_correlation"], 1.0)
        self.assertAlmostEqual(r["n_eff"], 1.0)

    def test_independent_series_count_as_n(self):
        r = pbo.effective_trials(noise(40, 2000, 8))
        self.assertLess(abs(r["mean_correlation"]), 0.01)
        self.assertGreater(r["n_eff"], 39)

    def test_mean_correlation_equals_the_pairwise_mean(self):
        rows = noise(6, 200, 2)
        rows = [[a + 0.5 * b for a, b in zip(r, rows[0])] for r in rows]          # shared component
        r = pbo.effective_trials(rows)
        def corr(a, b):
            ma, mb = sum(a) / len(a), sum(b) / len(b)
            num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            return num / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
        pairs = [corr(rows[i], rows[j]) for i in range(6) for j in range(i + 1, 6)]
        self.assertAlmostEqual(r["mean_correlation"], sum(pairs) / len(pairs), places=9)

    def test_flat_series_are_left_out(self):
        r = pbo.effective_trials([[0.0] * 50] + noise(3, 50, 1))
        self.assertEqual((r["used"], r["flat"]), (3, 1))

    def test_deflated_sharpe_with_fewer_effective_trials_is_less_harsh(self):
        from lab.engine import backtest
        trials = [x / 100 for x in range(-50, 51)]
        full = backtest.deflated_sharpe(0.2, trials, 500)
        eff = backtest.deflated_sharpe(0.2, trials, 500, n=5)
        self.assertGreater(eff, full)
        self.assertEqual(backtest.deflated_sharpe(0.2, trials, 500, n=len(trials)), full)   # default unchanged


class EffectiveSample(unittest.TestCase):
    """Amendment 15 point 4: the forward PSR uses n (1 - rho) / (1 + rho) when returns are autocorrelated."""
    def ar1(self, phi, n=400, seed=3):
        rng, x, out = random.Random(seed), 0.0, []
        for _ in range(n):
            x = phi * x + rng.gauss(0, 1)
            out.append(x)
        return out

    def test_persistence_shrinks_the_sample_and_never_grows_it(self):
        from lab.engine import backtest
        n8, r8 = backtest.effective_n(self.ar1(0.8))
        self.assertAlmostEqual(r8, 0.8, delta=0.1)
        self.assertLess(n8, 400 * 0.2)
        self.assertEqual(backtest.effective_n(self.ar1(-0.5))[0], 400.0)     # negative rho: n, never more
        self.assertEqual(backtest.effective_n([1.0, 2.0])[0], 2.0)

    def test_the_corrected_psr_is_lower_for_a_persistent_series(self):
        from lab.engine import backtest
        x = [v / 10 + 0.05 for v in self.ar1(0.8)]
        sr = sum(x) / len(x) / (sum((v - sum(x) / len(x)) ** 2 for v in x) / len(x)) ** 0.5
        self.assertLess(backtest.psr(sr, backtest.effective_n(x)[0]), backtest.psr(sr, len(x)))


if __name__ == "__main__":
    unittest.main()
