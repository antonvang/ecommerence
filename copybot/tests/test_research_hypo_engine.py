"""Director order 47 P1: hypothesis engine on synthetic data (small sizes; the full run is the report)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import factory as fa  # noqa: E402
from research.tools import hypo_engine as he  # noqa: E402


class Stats(unittest.TestCase):
    def test_holm_and_bh(self):
        ps = [0.001, 0.02, 0.03, 0.5]
        self.assertEqual(he.holm(ps, 0.05), [True, False, False, False])
        self.assertEqual(he.bh(ps, 0.10), [True, True, True, False])

    def test_p_and_wilson(self):
        self.assertAlmostEqual(he.p_one(0.0), 0.5)
        self.assertAlmostEqual(he.p_one(1.6448536269514722), 0.05, places=6)
        lo, hi = he.wilson(5, 100)
        self.assertLess(lo, 0.05)
        self.assertGreater(hi, 0.05)


class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.null = he.world(11, n=12, T=260, ic=0.0)
        cls.sig = he.world(12, n=12, T=400, ic=0.08)

    def test_signals_use_no_future_except_the_leak(self):
        for fam, L in [("mom", 20), ("rev", 1), ("vol", 10), ("char", 1)]:
            self.assertFalse(he.truncation_leak(fam, L, self.null, 1), (fam, L))
        self.assertTrue(he.truncation_leak("leak", 0, self.null, 1))

    def test_leak_is_never_selected(self):
        rows, _ = he.evaluate(self.null, [("leak", 0), ("mom", 20)], 0.0005, start=125)
        leak = rows[0]
        self.assertTrue(leak["leak"])
        self.assertLess(leak["p_net"], 1e-6)            # it looks wonderful ...
        self.assertFalse(any(leak[r] for r in ("raw", "holm", "bh", "bonf_neff")))   # ... and is rejected

    def test_planted_signal_is_found(self):
        rows, _ = he.evaluate(self.sig, [("char", 1), ("mom", 20)], 0.0005, start=125)
        self.assertTrue(rows[0]["holm"])

    def test_costs_kill_a_gross_edge(self):
        rows, _ = he.evaluate(self.sig, [("char", 1)], 0.05, start=125)
        self.assertLessEqual(rows[0]["net_mean"], 0)
        self.assertFalse(any(rows[0][r] for r in ("raw", "holm", "bh", "bonf_neff")))

    def test_engine_only_proposes(self):
        led = fa.Ledger()
        reg = fa.Register(led, {})
        ids = he.propose(reg, [("mom", 20), ("char", 1)], 0, {}, 250)
        self.assertTrue(all(reg.recs[i]["status"] == "PROPOSED" for i in ids))
        for i in ids:
            for k in ("falsifier", "not_arbitraged", "costs_capacity", "similar_rejected", "priority"):
                self.assertIn(k, reg.recs[i])
        with self.assertRaises(fa.FactoryError):
            reg.move(ids[0], "APPROVED", 1, {"actor": "engine:hypo"})

    def test_priority_ignores_returns_and_discounts_rejections(self):
        self.assertGreater(he.priority("mom", 500, 0), he.priority("mom", 500, 3))
        self.assertGreater(he.priority("mom", 2000, 0), he.priority("mom", 200, 0))

    def test_deterministic(self):
        a = he.one_rep(("null_base", 3, 10, 200))
        b = he.one_rep(("null_base", 3, 10, 200))
        self.assertEqual(a[1], b[1])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
