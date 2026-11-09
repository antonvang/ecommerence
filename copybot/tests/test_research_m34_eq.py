import datetime as dt
import math
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))
import m34_eq as m  # noqa: E402
from lab import sessions  # noqa: E402


def at(d, h, mi):
    return int(dt.datetime.combine(d, dt.time(h, mi), sessions.ET).timestamp())


class Points(unittest.TestCase):
    def test_pex_picks_last_before_open_first_after_30_min_and_last_an_hour_before_close(self):
        d = dt.date(2026, 11, 3)
        snaps = [(at(d, 9, 5), "P0"), (at(d, 9, 25), "P"), (at(d, 9, 55), "early"), (at(d, 10, 5), "E"),
                 (at(d, 14, 5), "X"), (at(d, 15, 5), "late")]
        p, e, x = m.pex(snaps, d)
        self.assertEqual((p[1], e[1], x[1]), ("P", "E", "X"))

    def test_early_close_day_moves_x(self):
        d = dt.date(2026, 11, 27)
        snaps = [(at(d, 9, 5), "P"), (at(d, 10, 5), "E"), (at(d, 11, 59), "X"), (at(d, 12, 5), "late")]
        self.assertEqual(m.pex(snaps, d)[2][1], "X")

    def test_holidays_and_weekends_are_not_trading_days(self):
        days = list(m.trading_days(dt.date(2026, 11, 25), dt.date(2026, 11, 30)))
        self.assertEqual(days, [dt.date(2026, 11, 25), dt.date(2026, 11, 27), dt.date(2026, 11, 30)])

    def test_a_late_snapshot_is_dropped(self):
        d = dt.date(2026, 11, 3)
        good, late = at(d, 9, 0), at(d, 9, 0) + m.LATE_S + 1

        class DB:
            def execute(self, q, a):
                return [(good, '{"columns": ["markPrice"], "rows": {}}'), (late, '{"columns": ["markPrice"], "rows": {}}')]
        got = [t for t, _ in m.snapshots(DB(), good - 10, late + 10)]
        self.assertEqual(got, [good])


class Signals(unittest.TestCase):
    def test_s_and_y(self):
        prev = (None, None, (0, {"A": {"indexPrice": 100.0}}))
        cur = ((0, {"A": {"markPrice": 110.0}}), (0, {"A": {"indexPrice": 100.0}}), (0, {"A": {"indexPrice": 90.0}}))
        s, y = m.sy(prev, cur, ["A", "B"])["A"]
        self.assertAlmostEqual(s, math.log(1.1))
        self.assertAlmostEqual(y, math.log(0.9))

    def test_long_short_is_bottom_minus_top_fifth_and_needs_50(self):
        pairs = [(i, -i / 100) for i in range(100)]          # high signal -> low outcome: a reversal
        self.assertGreater(m.ls(pairs), 0)
        self.assertIsNone(m.ls(pairs[:49]))

    def test_neutral_subtracts_beta_times_the_day_median(self):
        d = {"A": (0.01, 0.02), "B": (0.03, 0.00), "C": (0.05, -0.02)}       # medians: F_s 0.03, F_y 0.00
        n = m.neutral(d, {"A": 1.0, "B": 2.0, "C": 0.5, "Z": 9.0})
        self.assertAlmostEqual(n["A"][0], -0.02)
        self.assertAlmostEqual(n["B"][0], -0.03)
        self.assertAlmostEqual(n["C"][0], 0.035)
        self.assertAlmostEqual(n["C"][1], -0.02)
        self.assertNotIn("Z", n)


class Judge(unittest.TestCase):
    def days(self, vals):
        return [(dt.date(2026, 11, 2) + dt.timedelta(days=i), v) for i, v in enumerate(vals)]

    def test_untestable_below_28(self):
        self.assertEqual(m.judge(self.days([0.01] * 27), [])["verdict"], "UNTESTABLE")

    def test_pass_needs_the_floor(self):
        strong = [0.012 + 0.002 * ((i % 5) - 2) for i in range(30)]
        noise = [0.01 * ((-1) ** i) for i in range(30)]
        self.assertEqual(m.judge(self.days(strong), self.days(noise))["verdict"], "PASS")
        weak = [0.004 + 0.002 * ((i % 5) - 2) for i in range(30)]               # significant but under 0.60 %
        self.assertEqual(m.judge(self.days(weak), self.days(noise))["verdict"], "SCREEN_FAIL")

    def test_a_placebo_that_also_works_fails_it(self):
        strong = [0.012 + 0.002 * ((i % 5) - 2) for i in range(30)]
        self.assertEqual(m.judge(self.days(strong), self.days(strong))["verdict"], "SCREEN_FAIL")


class TTest(unittest.TestCase):
    def test_p_is_students_t_not_the_normal_approximation(self):
        xs = [1.0 + (-1) ** i * 0.5 * (1 + i % 3) for i in range(28)]
        t, p = m.tstat(xs)
        self.assertGreater(p, math.erfc(abs(t) / math.sqrt(2)))          # heavier tails than the normal

    def test_known_value(self):
        from lab.edgemonitor import t_cdf
        self.assertAlmostEqual(2 * (1 - t_cdf(3.0, 27)), 0.00575, places=4)


class Refusal(unittest.TestCase):
    def test_run_refuses_before_28_valid_days(self):
        with mock.patch.object(m, "count", return_value={"valid_days_m34": 3, "valid_days_m36": 3, "days": []}), \
                mock.patch.object(m, "run") as r, mock.patch("sys.argv", ["m34_eq", "run", "--db", ":memory:"]), \
                mock.patch("builtins.print"):
            m.main()
        r.assert_not_called()


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
