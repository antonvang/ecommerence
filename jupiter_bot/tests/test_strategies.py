import math
import unittest

from jupiter_bot.research import strategies as s
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401

T0 = 1_800_000_000.0 - (1_800_000_000.0 % 14400)   # a 4-hour UTC boundary


def snapshot(closes, as_of=None, start=T0):
    candles = [dict(start=start + 60 * i, end=start + 60 * (i + 1), close=str(c)) for i, c in enumerate(closes)]
    return dict(as_of=as_of if as_of is not None else candles[-1]["end"] + 7, candles=candles)


TS = {"lookback_min": 240, "rebalance_min": 240}
REV = {"k": 3.0, "drop_min": 30, "hold_min": 60, "vol_window_min": 360}


def wiggle(n, base=100.0, amp=0.001):
    return [base * (1 + amp * math.sin(i)) for i in range(n)]


class Momentum(unittest.TestCase):
    def test_up_trend_is_long_and_down_trend_flat(self):
        up = [100 + 0.01 * i for i in range(500)]
        down = [100 - 0.01 * i for i in range(500)]
        as_of = T0 + 480 * 60 + 7            # just after the second boundary
        self.assertEqual(s.tsmom(snapshot(up, as_of), TS), s.LONG)
        self.assertEqual(s.tsmom(snapshot(down, as_of), TS), s.FLAT)

    def test_signal_only_changes_at_boundaries(self):
        # rises until the boundary at bar 480, then falls hard: still LONG until the next boundary
        closes = [100 + 0.01 * i for i in range(480)] + [104.8 - 0.1 * i for i in range(1, 200)]
        self.assertEqual(s.tsmom(snapshot(closes, T0 + 670 * 60), TS), s.LONG)

    def test_too_little_history_is_flat(self):
        self.assertEqual(s.tsmom(snapshot([100 + i for i in range(100)]), TS), s.FLAT)
        self.assertEqual(s.tsmom(dict(as_of=T0, candles=[]), TS), s.FLAT)

    def test_bars_needed_covers_the_worst_case(self):
        self.assertEqual(s.tsmom_bars(TS), 481)


class Reversal(unittest.TestCase):
    def test_sharp_drop_triggers_and_expires(self):
        calm = wiggle(500)
        crash = [calm[-1] * (1 - 0.003 * i) for i in range(1, 31)]          # ~9 % in 30 min
        after = [crash[-1]] * 10
        snap = snapshot(calm + crash + after)
        self.assertEqual(s.reversal(snap, REV), s.LONG)
        later = calm + crash + [crash[-1] * (1 + 0.0001 * (i % 2)) for i in range(100)]
        # the 30-min window contains the crash for 30 more bars; +60 min hold; then out
        self.assertEqual(s.reversal(snapshot(later), REV), s.FLAT)

    def test_calm_market_stays_flat(self):
        self.assertEqual(s.reversal(snapshot(wiggle(600)), REV), s.FLAT)

    def test_rise_never_triggers(self):
        calm = wiggle(500)
        rise = [calm[-1] * (1 + 0.003 * i) for i in range(1, 41)]
        self.assertEqual(s.reversal(snapshot(calm + rise), REV), s.FLAT)

    def test_short_history_is_flat(self):
        self.assertEqual(s.reversal(snapshot(wiggle(100)), REV), s.FLAT)


class Registry(unittest.TestCase):
    def test_budget_matches_the_plan(self):
        self.assertEqual(s.TRIAL_BUDGET, 4)
        for fn, bars, grid in s.STRATEGIES.values():
            for params in grid:
                self.assertGreater(bars(params), 0)
                self.assertIn(fn(snapshot(wiggle(bars(params))), params), (s.LONG, s.FLAT))


if __name__ == "__main__":
    unittest.main()
