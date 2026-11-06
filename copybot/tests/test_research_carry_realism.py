"""Director order 46 P0+P1: carry cost/capital realism is arithmetic on public fees and stated scenarios."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import carry_realism as cr  # noqa: E402


class CarryRealism(unittest.TestCase):
    def test_round_trips(self):
        self.assertAlmostEqual(cr.round_trip("taker/taker"), 0.008 * 2 + 0.0005 * 2)
        self.assertAlmostEqual(cr.round_trip("maker/taker"), 0.004 + 0.008 + 0.0002 + 0.0005)
        self.assertAlmostEqual(cr.round_trip("taker/maker", 0.0002), cr.round_trip("maker/taker") + 0.0008)
        self.assertAlmostEqual(cr.binance_round_trip(), 0.0048)                      # the books' 0.48 %

    def test_breakeven_matches_the_lab_rule_of_thumb(self):
        self.assertAlmostEqual(cr.breakeven_apr(0.0048, 14), 0.125142857, places=6)   # 12.5 % at 14 d

    def test_net_per_capital_is_zero_at_breakeven(self):
        rt = cr.round_trip("taker/taker")
        self.assertAlmostEqual(cr.net_per_capital(rt, cr.breakeven_apr(rt, 90), 90), 0.0)

    def test_close_out_and_touch(self):
        self.assertAlmostEqual(cr.close_out_rise(2), 0.25)
        self.assertLess(cr.touch_prob(0.25, 0.5, 14), cr.touch_prob(0.25, 0.5, 180))
        self.assertLess(cr.touch_prob(0.05, 0.5, 90), 1.0)
        self.assertEqual(cr.touch_prob(0.1, 0.5, 0), 0.0)

    def test_capital_denominator_includes_both_legs(self):
        rows = {r["leverage"]: r for r in cr.capital_rows()}
        self.assertEqual(rows[1]["allocated"], 10_000)
        self.assertEqual(rows[2]["allocated"], 7_500)

    def test_pair_list_is_the_books(self):
        from lab import pairs
        self.assertEqual(tuple(pairs.PAIRS), cr.PAIRS)

    def test_build_without_db(self):
        rep = cr.build(None, 0)
        self.assertEqual(rep["accounts"], [])
        self.assertEqual(len(rep["pairs_capital"]), len(cr.PAIRS) * len(cr.PAIR_LEVERAGE))


if __name__ == "__main__":
    unittest.main()
