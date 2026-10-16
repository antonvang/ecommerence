import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copybot import DEFAULTS  # noqa: E402
from funding import HOUR, WEEK, FundingCarry, pick, week_of  # noqa: E402
from report import funding_state  # noqa: E402

MONDAY = 1_791_763_200  # mandag 12.10.2026 00:00 UTC


class FakeHL:
    """Fast funding pr. time for hver coin."""

    def __init__(self, rates):
        self.rates = rates

    def liquid(self):
        return {c: r for c, r in self.rates.items()}

    def history(self, coin, start_ts):
        now = self.now
        first = (int(start_ts) + HOUR - 1) // HOUR * HOUR
        return [(t, self.rates[coin]) for t in range(first, now + 1, HOUR)]


class Funding(unittest.TestCase):
    def test_week_starts_monday_utc(self):
        self.assertEqual(week_of(MONDAY), week_of(MONDAY + WEEK - 1))
        self.assertEqual(week_of(MONDAY) + 1, week_of(MONDAY + WEEK))
        self.assertNotEqual(week_of(MONDAY - 1), week_of(MONDAY))

    def test_pick_top_above_threshold(self):
        weekly = {"A": 0.004, "B": 0.003, "C": 0.001, "D": 0.0001}  # pr. uge: x52 = 20,8 %, 15,6 %, 5,2 %, 0,5 %/år
        self.assertEqual([c for c, _ in pick(weekly, top=3, min_apr=0.10)], ["A", "B"])

    def test_rotation_costs_and_accrual(self):
        hl = FakeHL({"A": 0.00005, "B": 0.00003, "C": -0.00001})
        fc = FundingCarry(DEFAULTS, tempfile.mkdtemp(), hl=hl, log=lambda *a: None)
        hl.now = MONDAY + 3 * HOUR
        fc.step(hl.now)
        held = sorted(r["coin"] for r in fc.open_positions())
        self.assertEqual(held, ["A", "B"])  # C har negativ funding og vælges ikke
        notional = DEFAULTS["funding"]["capital_usd"] / 2 / DEFAULTS["funding"]["top"]
        hl.now = MONDAY + 13 * HOUR
        fc.step(hl.now)
        st = funding_state(fc.s.path, now=hl.now)
        self.assertAlmostEqual(st["earned"], 10 * notional * (0.00005 + 0.00003), places=6)  # 10 hele timer
        self.assertAlmostEqual(st["costs"], 2 * notional * 0.002 / 2, places=6)  # indgang for to coins
        # ny uge: B falder ud (nu negativ), A bliver (ingen ny udgift), udgang for B betales
        hl.rates = {"A": 0.00005, "B": -0.00002, "C": -0.00001}
        hl.now = MONDAY + WEEK + HOUR
        fc.step(hl.now)
        self.assertEqual([r["coin"] for r in fc.open_positions()], ["A"])
        st = funding_state(fc.s.path, now=hl.now)
        self.assertAlmostEqual(st["costs"], 3 * notional * 0.002 / 2, places=6)
        fc.s.close()


if __name__ == "__main__":
    unittest.main()
