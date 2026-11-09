"""Amendment 36b: the sector side report removes the fixed pre-lock PC1 loading from s* and y*, separates a sector
reversal from a single-stock reversal, never changes m36 and refuses before 28 valid m36 days."""
import datetime as dt
import io
import json
import os
import random
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))
import m36_sector as m  # noqa: E402


def names(n=100):
    return [f"S{i:03d}USDT" for i in range(n)]


class Residualise(unittest.TestCase):
    def test_removes_the_loading_exactly(self):
        load = {s: (i % 10) / 10 - 0.45 for i, s in enumerate(names())}
        vals = {s: 0.3 + 2.0 * load[s] for s in load}
        res = m.residualise(vals, load)
        self.assertLess(max(abs(v) for v in res.values()), 1e-12)


class Day(unittest.TestCase):
    def setUp(self):
        rnd = random.Random(36)
        self.load = {s: rnd.gauss(0, 1) for s in names()}
        self.noise = {s: (rnd.gauss(0, 0.001), rnd.gauss(0, 0.001)) for s in names()}

    def test_a_pure_sector_reversal_vanishes(self):
        n36 = {s: (0.02 * L + e[0], -0.01 * L + e[1]) for (s, L), e in zip(self.load.items(), self.noise.values())}
        self.assertGreater(m.base.ls(list(n36.values())), 0.01)          # m36 would see a strong reversal
        r, rho = m.day(n36, self.load)
        self.assertLess(abs(r), 0.001)
        self.assertGreater(rho, 0.99)

    def test_a_single_stock_reversal_survives(self):
        rnd = random.Random(7)
        own = {s: rnd.gauss(0, 0.02) for s in self.load}
        n36 = {s: (own[s], -0.5 * own[s] + self.noise[s][1]) for s in self.load}
        r, rho = m.day(n36, self.load)
        self.assertGreater(r, 0.01)
        self.assertLess(abs(rho), 0.3)

    def test_under_50_symbols_gives_no_r(self):
        few = dict(list({s: (0.01, 0.0) for s in self.load}.items())[:40])
        self.assertIsNone(m.day(few, self.load)[0])


class Report(unittest.TestCase):
    def test_fields_and_decides_nothing(self):
        days = [(dt.date(2026, 11, 2) + dt.timedelta(days=i), 0.001 * ((-1) ** i) + 0.0005, 0.4 * ((-1) ** i))
                for i in range(30)]
        out = m.report(days)
        self.assertEqual(out["days"], 30)
        self.assertNotIn("verdict", out)
        self.assertAlmostEqual(out["share_abs_rho_gt_0_3"], 1.0)


class LoadingFile(unittest.TestCase):
    def test_fixed_pre_lock_loadings(self):
        d = json.load(open(m.PC1))
        u = set(json.load(open(m.base.U36))["universe"])
        self.assertEqual(len(d["loading"]), 132)
        self.assertTrue(set(d["loading"]) <= u)
        self.assertGreater(d["loading"]["AMDUSDT"], 0)
        self.assertLess(d["loading"]["KOUSDT"], 0)
        self.assertIn("36b", d["rule"])


class Refusal(unittest.TestCase):
    def test_refuses_below_28_valid_m36_days(self):
        with mock.patch.object(m.base, "count", return_value={"valid_days_m36": 5}), \
                mock.patch.object(m, "run") as r:
            buf = io.StringIO()
            with redirect_stdout(buf):
                m.main(["run", "--db", ":memory:"])
        r.assert_not_called()
        self.assertIn("refused", json.loads(buf.getvalue()))


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
