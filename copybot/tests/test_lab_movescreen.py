"""Amendment 21c: abnormal-move continuation/reversal screen - the detector's rule on closed bars, one event per coin
per 24 h, entry one hour after the flag, day clusters, explore0 only and no network."""
import io
import math
import os
import random
import shutil
import statistics
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypogen, movescreen  # noqa: E402
from lab.engine import data  # noqa: E402

H, D = 3600, 86400
A, B = hypogen.bounds("explore0")


def walk(n, start=A, seed=1, jumps=None, sd=0.002):
    """{bar open: close} for n consecutive hours with gaussian noise and {index: extra log return}."""
    rnd, px, out = random.Random(seed), 100.0, {}
    for i in range(n):
        px *= math.exp(rnd.gauss(0, sd) + (jumps or {}).get(i, 0.0))
        out[start + i * H] = px
    return out


class Events(unittest.TestCase):
    def test_the_detector_rule_with_an_exact_sigma(self):
        px = walk(900, jumps={800: 0.02})
        ev = movescreen.events(px)
        self.assertEqual([e[0] for e in ev], [A + 800 * H])
        h = A + 800 * H
        rets = [math.log(px[g] / px[g - H]) for g in range(h - 720 * H, h, H)]
        self.assertAlmostEqual(ev[0][2], math.log(px[h] / px[h - H]) / statistics.pstdev(rets), places=9)
        self.assertEqual(ev[0][1], 1)

    def test_one_event_per_coin_per_day_and_none_on_short_history(self):
        self.assertEqual(len(movescreen.events(walk(900, jumps={700: 0.02, 710: -0.02}))), 1)
        self.assertEqual(len(movescreen.events(walk(900, jumps={700: 0.02, 730: -0.02}))), 2)
        self.assertEqual(movescreen.events(walk(900, jumps={500: 0.05})), [])         # < 600 trailing returns

    def test_gaps_break_returns(self):
        px = walk(900, jumps={800: 0.02})
        del px[A + 799 * H]                                                         # no r_h without bar h - 1
        self.assertEqual(movescreen.events(px), [])


class Outcome(unittest.TestCase):
    def test_entry_one_hour_after_the_flag_and_signed(self):
        px = {A + i * H: 100.0 + i for i in range(40)}
        y, _ = movescreen.outcome(px, A, -1, 5, B)
        self.assertAlmostEqual(y, -math.log(105 / 101))
        self.assertEqual(movescreen.outcome(px, A + 20 * H, 1, 25, B), (None, "missing price"))
        self.assertEqual(movescreen.outcome(px, B - 10 * H, 1, 25, B), (None, "window outside the phase"))


class Screen(unittest.TestCase):
    def test_continuation_is_found_and_reported_with_clusters_and_placebo(self):
        series = {}
        for c in range(30):
            j = 760 + 30 * c                                                        # one move per coin, different days
            jumps = {j: 0.03 * (1 if c % 2 else -1)}
            for k in range(2, 26):
                jumps[j + k] = 0.002 * (1 if c % 2 else -1)                         # drift on in the same direction
            series[f"C{c}USDT"] = walk(2000, seed=c, jumps=jumps)
        r = movescreen.screen(series, "cont_24h", A, B)
        self.assertGreaterEqual(r["n_events"], 30)                                 # the planted 30 (+ chance 4-sigma hours)
        self.assertGreaterEqual(r["n_clusters"], 15)
        self.assertEqual(r["direction"], "continuation")
        self.assertGreater(r["mean"], movescreen.COST)
        self.assertIn("placebo", r)
        self.assertGreaterEqual(r["descriptive_not_tested"]["up moves"]["n_events"], 15)
        self.assertIn(r["verdict"], ("SCREEN_PASS", "SCREEN_FAIL"))                 # halves: all events are in 2020

    def test_few_clusters_are_untestable(self):
        r = movescreen.screen({"XUSDT": walk(900, jumps={800: 0.03})}, "cont_4h", A, B)
        self.assertEqual(r["verdict"], "UNTESTABLE")


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="movescreen")
        self.orig = data.CACHE
        os.makedirs(os.path.join(self.tmp, "klines"))

    def tearDown(self):
        data.CACHE = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def month(self, sym, y, m, n=24 * 28):
        t0 = hypogen._T(y, m)
        buf = io.StringIO()
        for i in range(n):
            ts = (t0 + i * H) * 1000
            buf.write(f"{ts},1,1,1,{100 + (i % 7) * 0.01},1,{ts + H * 1000 - 1},1000,1,0,0,0\n")
        with zipfile.ZipFile(os.path.join(self.tmp, "klines", f"{sym}-1h-{y}-{m:02d}.zip"), "w") as z:
            z.writestr(f"{sym}-1h-{y}-{m:02d}.csv", buf.getvalue())

    def test_explore0_cache_only_and_no_network(self):
        self.month("AAAUSDT", 2020, 4)
        self.month("AAAUSDT", 2022, 1)                                   # train3: never read
        self.month("BTCDOMUSDT", 2020, 4)                                # an index: excluded
        self.month("ZZZUSDT", 2024, 2)                                   # holdout: not even in the universe
        with mock.patch.object(data, "_fetch", side_effect=AssertionError("network")):
            rep = movescreen.run(self.tmp)
        self.assertEqual(rep["symbols"], ["AAAUSDT"])
        self.assertEqual(rep["files"], 1)
        self.assertEqual([r["key"] for r in rep["results"]],
                         ["abnormal_move|cont_4h|m21c", "abnormal_move|cont_24h|m21c"])
        self.assertTrue(all(r["verdict"] == "UNTESTABLE" for r in rep["results"]))
        with self.assertRaises(hypogen.Refused):
            hypogen.Reader("explore0").month("AAAUSDT", "klines", 2022, 1)


if __name__ == "__main__":
    unittest.main()
