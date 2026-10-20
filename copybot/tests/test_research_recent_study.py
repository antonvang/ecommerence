"""research/tools/recent_study.py: income is the rate actually paid, not the rate normalised to 8 hours."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))

import recent_study as rs  # noqa: E402

H = 3600


class Income(unittest.TestCase):
    def test_a_4h_coin_is_not_counted_twice(self):
        # 0.05 % every 4 hours for 4 settlements, then two below the floor
        rates = [0.0005] * 6 + [0.0, 0.0]
        rows = [(i * 4 * H, r) for i, r in enumerate(rates)]
        ser = rs.binance_series({"XUSDT": rows + [(len(rates) * 4 * H + k * 4 * H, 0.0) for k in range(3)]})
        self.assertAlmostEqual(ser["XUSDT"][0][0], 0.001)             # normalised: 0.1 % per 8 h
        tr = rs.trades(ser, 3, 0.0005)
        self.assertEqual(len(tr), 1)
        # entry at the 4th normalised point (3-settlement window); one more 0.05 % is paid, then two zeros exit.
        # The old code summed the normalised 0.1 % instead: twice the income.
        self.assertAlmostEqual(tr[0][0], 0.0005)

    def test_hourly_hyperliquid_is_not_multiplied_by_8(self):
        ser = rs.hl_series({"X": [(i * H, 0.0001) for i in range(60)] + [(60 * H + i * H, 0.0) for i in range(3)]})
        tr = rs.trades(ser, 24, 0.0005)
        self.assertEqual(len(tr), 1)
        self.assertAlmostEqual(tr[0][0], 0.0001 * 35, places=9)        # 35 paid hours of 0.01 %, not 8x that


if __name__ == "__main__":
    unittest.main()
