"""research/tools/carry_basis.py: trade timing on synthetic settlements (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))

import carry_basis as cb  # noqa: E402

H = 3600
T0 = 1_780_000_000 // (8 * H) * (8 * H)        # an 8-hour boundary


class Timing(unittest.TestCase):
    def test_entry_exit_and_funding_window(self):
        # 8-hour settlements; the series drops the first row, so k=4 is index 3, the first that can signal
        rates = [0.0001, 0.0001, 0.0001, 0.0001, 0.0006, 0.00005, 0.00005, 0.0001]
        rows = [(T0 + k * 8 * H, r) for k, r in enumerate(rates)]
        tr = cb.trades(cb.series(rows))
        self.assertEqual(len(tr), 1)
        t = tr[0]
        self.assertEqual(t["signal_ts"], T0 + 4 * 8 * H)          # 0.06 % >= X and the 3-point mean 0.027 % >= X/2
        self.assertEqual(t["entry"], T0 + 4 * 8 * H + H)
        self.assertAlmostEqual(t["funding"], 0.0001)              # k=5 and k=6 paid (both below the floor -> exit)
        self.assertEqual(t["exit"], T0 + 6 * 8 * H + H)

    def test_a_settlement_at_the_entry_instant_is_not_earned(self):
        rows = [(T0 + k * H, r) for k, r in enumerate([0.0001] + [0.0001] * 3 + [0.0001, 0.0, 0.0])]
        # 1-hour settlements of 0.01 % normalise to 0.08 %/8h >= X: entry one hour after the 4th point
        tr = cb.trades(cb.series(rows))
        t = tr[0]
        self.assertEqual(t["entry"], t["signal_ts"] + H)
        self.assertAlmostEqual(t["funding"], 0.0)             # the next settlement is exactly at entry: not counted

    def test_open_trade_has_no_exit(self):
        rows = [(T0 + k * 8 * H, 0.0006) for k in range(8)]
        self.assertIsNone(cb.trades(cb.series(rows))[0]["exit"])


if __name__ == "__main__":
    unittest.main()
