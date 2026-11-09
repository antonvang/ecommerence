"""MISSION27_3 point 6b/6c drafts: n6 (funding regime) and n4 (kimchi) statistics on synthetic data only; both
refuse to run without a locked amendment and before 2026-11-14."""
import datetime as dt
import io
import json
import math
import os
import random
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))
import n4_kimchi as n4  # noqa: E402
import n6_funding as n6  # noqa: E402


class Weeks(unittest.TestCase):
    def test_95_mondays_inside_explore0(self):
        w = n6.weeks()
        self.assertEqual(len(w), 95)
        self.assertEqual(w[0], dt.date(2020, 3, 2))
        self.assertEqual(w[-1], dt.date(2021, 12, 20))
        self.assertTrue(all(d.weekday() == 0 for d in w))


class Outcome(unittest.TestCase):
    def test_median_of_coin_means_and_validity(self):
        rates = {f"C{i}": [0.0001 * i] * 21 for i in range(25)}
        self.assertAlmostEqual(n6.outcome(rates), 0.0012)
        rates["SHORT"] = [1.0] * 5                         # too few prints: ignored
        self.assertAlmostEqual(n6.outcome(rates), 0.0012)
        self.assertIsNone(n6.outcome({f"C{i}": [0.0001] * 21 for i in range(19)}))

    def test_predictors(self):
        self.assertAlmostEqual(n6.x2_ret(100, 110), math.log(1.1))
        self.assertIsNone(n6.x1_vol([100]))
        self.assertGreater(n6.x1_vol([100, 101, 100, 102]), 0)
        # basis 1 % with 36.5 days left = 10 % a year; perp 0.01 %/8 h = 10.95 % a year
        self.assertAlmostEqual(n6.x3_basis([(101, 100, 36.5)], [0.0001]), 0.10 - 0.1095)


class OlsHac(unittest.TestCase):
    def test_recovers_noiseless_coefficients(self):
        X = [[1.0, t / 10, (t % 7) / 3] for t in range(40)]
        y = [0.5 + 2 * r[1] - 3 * r[2] for r in X]
        b, _, _, _ = n6.ols_hac(y, X)
        for got, want in zip(b, (0.5, 2, -3)):
            self.assertAlmostEqual(got, want, places=9)

    def test_constant_only_lag0_is_hc0(self):
        y = [1.0, 2.0, 4.0, 7.0]
        _, se, _, _ = n6.ols_hac(y, [[1.0]] * 4, lags=0)
        m = sum(y) / 4
        self.assertAlmostEqual(se[0], math.sqrt(sum((v - m) ** 2 for v in y)) / 4)


def series(b, seed, n=95):
    rnd = random.Random(seed)
    X = [rnd.gauss(0, 1) for _ in range(n)]
    M = [0.0]
    for t in range(n - 1):
        M.append(0.5 * M[-1] + b * X[t] + rnd.gauss(0, 1))
    return M, X


class TestK(unittest.TestCase):
    def test_strong_predictor_passes(self):
        M, X = series(1.0, 1)
        out = n6.test_k(M, X)
        self.assertEqual(out["verdict"], "PASS")
        self.assertEqual(out["n"], 94)

    def test_no_predictor_fails(self):
        M, X = series(0.0, 2)
        self.assertEqual(n6.test_k(M, X)["verdict"], "SCREEN_FAIL")

    def test_missing_weeks_and_x3_minimum(self):
        M, X = series(1.0, 3)
        X = [None] * 40 + X[40:]                           # basis only from week 40: 54 pairs
        self.assertEqual(n6.test_k(M, X, min_pairs=n6.MIN_PAIRS_X3)["n"], 54)
        X2 = [None] * 50 + X[50:]
        self.assertEqual(n6.test_k(M, X2, min_pairs=n6.MIN_PAIRS_X3)["verdict"], "UNTESTABLE")


class Kimchi(unittest.TestCase):
    def setUp(self):
        rnd = random.Random(4)
        self.coins = [f"K{i:02d}" for i in range(50)]
        self.prev = {c: rnd.gauss(0, 0.02) for c in self.coins}
        self.today = {c: self.prev[c] + rnd.gauss(0, 0.01) for c in self.coins}

    def test_fx_and_multiplier_cancel(self):
        s = n4.signal(self.today, self.prev)
        fx = {c: v + 0.03 for c, v in self.today.items()}       # USD/KRW moved 3 % for everyone
        s2 = n4.signal(fx, self.prev)
        for c in s:
            self.assertAlmostEqual(s[c], s2[c], places=12)
        self.assertAlmostEqual(n4.q(1000, 1) - n4.q(1000, 1000), math.log(1000))   # constant shift only

    def test_under_40_coins_is_invalid(self):
        few = dict(list(self.today.items())[:39])
        self.assertIsNone(n4.signal(few, self.prev))

    def test_quintile_sign(self):
        s = n4.signal(self.today, self.prev)
        y = {c: 0.5 * v for c, v in s.items()}
        self.assertGreater(n4.quintile_ls(s, y), 0)
        self.assertLess(n4.quintile_ls(s, {c: -v for c, v in y.items()}), 0)

    def test_outcome_is_return_against_btc(self):
        self.assertAlmostEqual(n4.outcome(100, 110, 50, 55), 0.0)


class Judge(unittest.TestCase):
    def days(self, mean, seed, n=550, sd=0.0361):
        rnd = random.Random(seed)
        return [rnd.gauss(mean, sd) for _ in range(n)]

    def test_categories(self):
        placebo = self.days(0.0, 9)
        self.assertEqual(n4.judge(self.days(0.012, 1), placebo)["verdict"], "SCREEN_PASS")
        self.assertEqual(n4.judge(self.days(0.0035, 2, sd=0.005), placebo)["verdict"], "SIGNAL_BELOW_FLOOR")
        self.assertEqual(n4.judge(self.days(-0.012, 3), placebo)["verdict"], "REVERSED")
        self.assertEqual(n4.judge(self.days(0.0, 4), placebo)["verdict"], "SCREEN_FAIL")

    def test_placebo_signal_blocks_pass(self):
        self.assertNotEqual(n4.judge(self.days(0.012, 1), self.days(0.012, 5))["verdict"], "SCREEN_PASS")


class Refusal(unittest.TestCase):
    def run_main(self, mod, text, today):
        fake = mock.MagicMock()
        fake.now.return_value = dt.datetime.combine(today, dt.time(12), dt.timezone.utc)
        with mock.patch.object(mod.dt, "datetime", fake), \
                mock.patch("builtins.open", mock.mock_open(read_data=text)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                mod.main(["run"])
        return json.loads(buf.getvalue())

    def test_refuses_before_lock_and_before_11_14(self):
        for mod, tag in ((n6, "n6"), (n4, "n4")):
            lock = f"## Ændring 38 (2026-11-14 kl. 10:00 lokal): x (metode {tag})\n"
            self.assertIn("no locked amendment", self.run_main(mod, "", dt.date(2026, 11, 20))["refused"])
            self.assertIn("no locked amendment", self.run_main(mod, lock, dt.date(2026, 11, 13))["refused"])
            self.assertIn("loader not written", self.run_main(mod, lock, dt.date(2026, 11, 14))["refused"])

    def test_current_protocol_has_no_lock(self):
        with open(n6.PROTOCOL, encoding="utf-8") as f:
            text = f.read()
        self.assertFalse(n6.locked(text))
        self.assertFalse(n4.locked(text))

    def test_the_tool_has_no_pair_file_constant(self):
        """Order 73: the former content checks of the real list are gone, because no test may read it."""
        self.assertFalse(hasattr(n4, "PAIRS"))


if __name__ == "__main__":
    unittest.main()
