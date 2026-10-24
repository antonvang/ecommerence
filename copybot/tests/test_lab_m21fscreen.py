"""Amendment 21f: three families on explore0 - BTC-led alt excess, squeeze breakouts, moves with a dated catalyst;
the same day clusters, halves and placebo as 21c, stricter cost hurdles, no network."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypogen, m21fscreen as f, movescreen  # noqa: E402
from tests.test_lab_movescreen import A, B, H, walk  # noqa: E402


class Scan(unittest.TestCase):
    def test_same_events_as_21c_at_four_sigma(self):
        px = walk(3000, jumps={800: 0.02, 900: -0.03, 2000: 0.025})
        self.assertEqual(f.scan(px, 4.0), movescreen.events(px))

    def test_compression_needs_a_quiet_72_hours(self):
        px = walk(1100, jumps={1000: 0.012})                                       # 6 sigma on 0.002 noise
        self.assertEqual(len(f.scan(px, 2.5, 0.5)), 0)                              # not compressed: no event
        calm = walk(1100, jumps={1000: 0.012}, seed=3)
        lo = {}                                                                     # last 72 h at 1/4 of the noise
        prev = None
        for i, t in enumerate(sorted(calm)):
            if prev is None:
                lo[t] = calm[t]
            else:
                r = (calm[t] / calm[prev])
                lo[t] = lo[prev] * (r if not 928 <= i < 1000 else r ** 0.25)
            prev = t
        self.assertEqual([e[0] for e in f.scan(lo, 2.5, 0.5)], [A + 1000 * H])


class Families(unittest.TestCase):
    def series(self, n=30):
        out = {"BTCUSDT": walk(2600, seed=99, jumps={760 + 40 * k: 0.01 * (1 if k % 2 else -1) for k in range(n)})}
        for c in range(6):
            out[f"C{c}USDT"] = walk(2600, seed=c)
        return out

    def test_a_reports_the_basket_and_its_cost_hurdle(self):
        r = f.family_a(self.series(), A, B)
        self.assertEqual(r["key"], "btc_lead|alt_excess_24h|m21f")
        self.assertEqual(r["cost_hurdle"], 0.0111)
        self.assertGreaterEqual(r["n_events"], 25)
        self.assertEqual(r["descriptive_not_tested"]["mean alts per event"], 6)
        self.assertIn(r["verdict"], ("SCREEN_FAIL", "SCREEN_PASS"))

    def test_c_keeps_only_moves_with_a_catalyst_published_before_the_hour_ends(self):
        px = walk(3000, jumps={800: 0.03, 1500: 0.03, 2200: -0.03})
        hs = [h for h, _, _ in f.scan(px, 4.0)]
        cat = {"XUSDT"[:-4]: [hs[0] - 3600, hs[1] + 2 * H]}                        # before / after the move hour
        r = f.family_c({"XUSDT": px}, A, B, cat)
        self.assertEqual(r["n_events"], 1)
        self.assertEqual(r["descriptive_not_tested"]["4-sigma moves without a catalyst (not tested; ~m21c)"],
                         len(hs) - 1)
        self.assertEqual(r["verdict"], "UNTESTABLE")

    def test_catalysts_come_from_binance_items_naming_the_coin(self):
        rows = [(json.dumps({"published_ts": 100, "coins": ["FOO", "BAR"]}),), (json.dumps({"coins": ["FOO"]}),)]
        self.assertEqual(f.catalysts(lambda sql, *a: rows), {"FOO": [100.0], "BAR": [100.0]})

    def test_explore0_only(self):
        with self.assertRaises(hypogen.Refused):
            hypogen.Reader("explore0").month("BTCUSDT", "klines", 2022, 1)


if __name__ == "__main__":
    unittest.main()
