"""Amendment 29a point 3 (V1): the public-book sampler walks 15 quote units against mid, records errors instead of
filling them in, never samples in a K3 window, and reports per coin the median venue-minus-Binance round trip from
the same sample, with fees left unset until verified."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "research", "tools"))

import v1_books as v  # noqa: E402

T0 = 1793106600.0                                       # 13:10 UTC, outside K3


class Walk(unittest.TestCase):
    def test_walk_and_measure(self):
        m = v.measure([(99.9, 1.0)], [(100.1, 0.05), (100.3, 1.0)])
        self.assertAlmostEqual(m["mid"], 100.0)
        self.assertAlmostEqual(m["spread_bp"], 20.0)
        self.assertAlmostEqual(m["sell_bp"], 10.0, places=3)
        self.assertGreater(m["buy_bp"], 10.0)                       # 5.005 at 100.1, the rest at 100.3
        self.assertIsNone(v.measure([(99.9, 0.01)], [(100.1, 1)])["sell_bp"])   # too thin: None, not a guess
        self.assertIn("error", v.measure([(100.2, 1)], [(100.1, 1)]))


class Sample(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="v1")
        self.out = os.path.join(self.tmp, "b.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fetch(self, url):
        if "kraken" in url:
            raise TimeoutError("read timed out")
        wide = 0.2 if "coinbase" in url else 0.05
        book = {"bids": [[str(100 - wide), "10"]], "asks": [[str(100 + wide), "10"]]}
        if "okx" in url:
            return {"data": [book]}
        return book

    def test_run_skips_k3_records_errors_and_reports_diffs(self):
        t = [T0 + 14 * 60]                                  # 13:24: the next 2 min touch the 14:00 window

        def now():
            return t[0]

        def sleep(s):
            t[0] += s
        n = v.run(2, out=self.out, fetch=self.fetch, now=now, sleep=sleep)
        self.assertEqual(n, 2)
        with open(self.out) as fh:
            rows = [json.loads(x) for x in fh]
        self.assertTrue(all(not v.k3_window(r["ts"]) for r in rows))
        self.assertTrue(any("error" in r and r["venue"] == "Kraken" for r in rows))
        self.assertFalse(any(r["venue"] == "OKX" and r["coin"] == "VET" for r in rows))   # not listed: not asked
        rep = v.report(self.out)
        self.assertAlmostEqual(rep["coins"]["BTC"]["Coinbase"]["median_diff_bp"], 30.0, places=1)   # 40 - 10 bp
        self.assertNotIn("Kraken", rep["coins"]["BTC"])
        self.assertAlmostEqual(rep["coins"]["BTC"]["Coinbase"]["median_diff_with_fees_bp"], 110.0, places=1)  # 30+80
        self.assertAlmostEqual(rep["coins"]["BTC"]["OKX"]["median_diff_with_fees_bp"], 20.0, places=1)  # 0 + 2x(0.2-0.1)%
        self.assertAlmostEqual(rep["coins"]["BTC"]["Bitvavo"]["median_diff_with_fees_bp"], -10.0, places=1)  # USDC 0.05
        self.assertAlmostEqual(rep["coins"]["XTZ"]["Bitvavo"]["median_diff_with_fees_bp"], 30.0, places=1)   # EUR 0.25

    def test_fees_are_sourced_and_okx_uses_the_eu_host(self):
        """Amendment 29b: every set fee names the venue's own page; OKX is read on eea.okx.com."""
        for venue, f in v.FEES.items():
            self.assertIn(venue.lower(), f["url"])
            for c in v.COINS:
                self.assertTrue(f["quote"] and f["read"] == "2026-10-27" and 0 < v.taker(venue, c) < 0.01)
        self.assertAlmostEqual(v.with_fees("Kraken"), 140.0)
        self.assertAlmostEqual(v.with_fees("Bitvavo", "ETH"), -10.0)
        self.assertAlmostEqual(v.with_fees("Bitvavo", "VET"), 30.0)
        with mock.patch.dict(v.FEES, {"Bitstamp": None}):
            self.assertIsNone(v.with_fees("Bitstamp"))                      # uafklaret stays None
        self.assertTrue(v.VENUES["OKX"][0]("BTC").startswith("https://eea.okx.com/"))


if __name__ == "__main__":
    unittest.main()
