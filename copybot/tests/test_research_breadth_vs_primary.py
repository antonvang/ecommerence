"""Director order 48 P2: broad screening vs one primary per family (small synthetic sizes)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import breadth_vs_primary as bp  # noqa: E402


class Design(unittest.TestCase):
    def test_primary_is_fixed_and_blind(self):
        # the primary rule is a constant chosen before any world exists; the true lag is drawn per world
        self.assertEqual(bp.PRIMARY, (1, 3))
        lags = {tuple(sorted(bp.world(s, n=6, T=40, M=3, ic=0.03)["lags"].values())) for s in range(12)}
        self.assertGreater(len(lags), 1)

    def test_null_world_has_no_real_family(self):
        w = bp.world(1, n=6, T=40, M=3, ic=0.0)
        self.assertEqual(w["real"], [])

    def test_signal_uses_only_past_z(self):
        w = bp.world(2, n=9, T=60, M=1, ic=0.0)
        a = bp.net_series(w, 0, 1, 1, 40, 41)
        w["Z"][0] = [row[:41] + [x + 1e6 for x in row[41:]] for row in w["Z"][0]]   # poison z from day 40 on
        self.assertEqual(a, bp.net_series(w, 0, 1, 1, 40, 41))

    def test_one_world_runs_and_counts(self):
        r = bp.one(("ic_0.03", 0, 12, 200, 3, 0.03))
        for a in ("A", "B", "C"):
            self.assertLessEqual(r[a]["true"], 3)
            self.assertLessEqual(r[a]["true"] + r[a]["false"], bp.F)
        self.assertEqual(r["A"]["evals"], bp.F * 42)
        self.assertEqual(r["B"]["evals"], bp.F)


if __name__ == "__main__":
    unittest.main()
