"""Amendment 21h point 5: funding x 4-sigma move - the crowd from the last settlement before the move hour, follow
with the crowd and fade against it, net of the funding paid while holding, explore0 only."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypogen, m21hscreen as m  # noqa: E402
from tests.test_lab_movescreen import A, B, H, walk  # noqa: E402


def settlements(rate, n=3000):
    return {A + i * 8 * H: rate for i in range(n // 8)}


class Crowd(unittest.TestCase):
    def test_known_before_the_move_and_at_most_12_hours_old(self):
        fs = {A: 0.0005, A + 8 * H: -0.0002, A + 16 * H: 0.0001}
        t = sorted(fs)
        self.assertEqual(m.crowd(fs, t, A + 7 * H), (1, 0.0005))
        self.assertEqual(m.crowd(fs, t, A + 8 * H), (-1, -0.0002))              # settled at the hour's start: known
        self.assertEqual(m.crowd(fs, t, A + 17 * H), (None, "neutral funding"))
        self.assertEqual(m.crowd(fs, t, A + 29 * H), (None, "no recent funding"))
        self.assertEqual(m.crowd(fs, t, A - H), (None, "no recent funding"))


class Value(unittest.TestCase):
    def test_net_of_the_funding_a_position_pays(self):
        px = {A + i * H: 100.0 * math.exp(0.001 * i) for i in range(40)}
        fs = {A + 8 * H: 0.001, A + 16 * H: 0.001, A + 24 * H: 0.001, A + 32 * H: 0.001}
        v, _ = m.value(px, fs, A, 1, B)                                         # long pays 3 settlements in (h+1, h+25]
        self.assertAlmostEqual(v, 0.024 - 0.003)
        v, _ = m.value(px, fs, A, -1, B)
        self.assertAlmostEqual(v, -0.024 + 0.003)
        self.assertEqual(m.value(px, {}, A, 1, B), (None, "missing funding in the holding window"))


class Screen(unittest.TestCase):
    def test_reports_with_and_against_and_exclusions(self):
        series = {f"C{c}USDT": walk(2600, seed=c, jumps={760 + 50 * c: 0.03 * (1 if c % 2 else -1)}) for c in range(20)}
        fund = {s: settlements(0.0005 if i % 3 else 0.00005, 2600) for i, s in enumerate(sorted(series))}
        fund["C0USDT"] = {}
        r = m.screen(series, fund, A, B)
        self.assertEqual(r["key"], "funding_crowd|squeeze_24h|m21h")
        self.assertEqual(r["cost_hurdle"], hypogen.COST)
        self.assertIn("neutral funding", r["excluded"])
        self.assertIn("no funding file", r["excluded"])
        d = r["descriptive_not_tested"]
        self.assertEqual(d["with the crowd (continuation)"]["n_events"] + d["against the crowd (reversal)"]["n_events"],
                         r["n_events"])


if __name__ == "__main__":
    unittest.main()
