"""MISSION27_3 point 12b: hlcensus/1 first-look measures on synthetic snapshots only; refusal below 48 snapshots."""
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))
import hlcensus_look as hl  # noqa: E402

COLS = ["funding", "premium", "markPx", "oraclePx", "midPx", "openInterest", "dayNtlVlm", "prevDayPx", "isDelisted"]


def row(funding, mark, oi, vol, delisted=0.0):
    return [funding, None, mark, None, None, oi, vol, None, delisted]


class Mapping(unittest.TestCase):
    def test_k_prefix_and_1000_contracts(self):
        syms = {"1000PEPEUSDT", "BTCUSDT"}
        self.assertTrue(hl.on_binance("kPEPE", syms))
        self.assertTrue(hl.on_binance("BTC", syms))
        self.assertFalse(hl.on_binance("HYPE", syms))
        self.assertEqual(hl.base("kBONK"), "BONK")
        self.assertEqual(hl.base("k"), "k")
        self.assertEqual(hl.base("kaito"), "kaito")       # not a k-prefix: rest is not upper case


class Summarise(unittest.TestCase):
    def test_measures(self):
        s1 = {"columns": COLS, "rows": {"BTC": row(0.00001, 100.0, 10.0, 1e9),
                                        "HYPE": row(0.00002, 10.0, 5.0, 6e6),
                                        "TINY": row(0.001, 1.0, 1.0, 1e3, 1.0)}}
        s2 = {"columns": COLS, "rows": {"BTC": row(0.00001, 100.0, 10.0, 1e9),
                                        "HYPE": row(None, 10.0, 5.0, 6e6),
                                        "NEW": row(0.0, 1.0, 1.0, 1e3)}}
        out = hl.summarise([(0, s1, {"BTCUSDT"}), (3600, s2, None)])
        self.assertEqual(out["snapshots"], 2)
        self.assertEqual(out["hours_with_census"], 1)
        self.assertEqual(out["universe"]["max"], 3)
        self.assertEqual(out["added_total"], 1)
        self.assertEqual(out["removed_total"], 1)
        self.assertEqual(out["delisted_median"], 0.5)
        self.assertEqual(out["hl_only_median"], 2)          # HYPE and TINY in hour 1
        self.assertEqual(out["hl_only_liquid_median"], 1)   # HYPE
        self.assertEqual(out["funding_apr_liquid_hl_only"]["n"], 1)   # hour 2 has no census: not pooled
        self.assertAlmostEqual(out["funding_apr_liquid_hl_only"]["median"], 0.00002 * 24 * 365)
        self.assertAlmostEqual(out["funding_apr_liquid_shared"]["median"], 0.00001 * 24 * 365)
        self.assertAlmostEqual(out["oi_top10_share_median"], 1.0)   # three or fewer names: top 10 is everything


class Refusal(unittest.TestCase):
    def test_refuses_below_48(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "lab.db")
            con = sqlite3.connect(p)
            con.execute("CREATE TABLE observations (ts INTEGER, detector TEXT, metric TEXT, payload TEXT)")
            for i in range(47):
                con.execute("INSERT INTO observations VALUES (?, 'hlcensus/1', 'snapshot', ?)",
                            (i * 3600, json.dumps({"columns": COLS, "rows": {}})))
            con.commit()
            con.close()
            buf = io.StringIO()
            with redirect_stdout(buf):
                hl.main(["run", "--db", p])
            self.assertIn("47 snapshots < 48", json.loads(buf.getvalue())["refused"])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
