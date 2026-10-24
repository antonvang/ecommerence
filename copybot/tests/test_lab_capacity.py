"""Amendment 21v: the current capacity curve walks 500 levels at five sizes, marks sizes the 20 paper levels cannot fill,
stores a too-thin size empty and censored (never guessed), runs at most once per 23 h and records a source error."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import capacity, moves  # noqa: E402
from lab.db import DB  # noqa: E402

NOW = 1_793_000_000


def book(levels=30, qty=10.0):
    """Mid 100, spread 0.02, each level 1 000 USD per side at qty 10."""
    return {"bids": [[str(99.99 - i * 0.01), str(qty)] for i in range(levels)],
            "asks": [[str(100.01 + i * 0.01), str(qty)] for i in range(levels)]}


class Curve(unittest.TestCase):
    def test_sizes_censoring_and_the_20_level_mark(self):
        b = book()
        rows = capacity.curve([(float(p), float(q)) for p, q in b["bids"]],
                              [(float(p), float(q)) for p, q in b["asks"]])
        by = {r["size_usd"]: r for r in rows}
        self.assertEqual(sorted(by), list(capacity.SIZES))
        self.assertAlmostEqual(by[500]["round_trip"], 0.02 / 100, places=9)       # inside the top level: the spread
        self.assertTrue(by[5_000]["fits_20_levels"] and not by[5_000]["censored"])
        self.assertFalse(by[20_000]["fits_20_levels"])                             # 30 levels fill it, 20 cannot
        self.assertFalse(by[20_000]["censored"])
        self.assertTrue(by[50_000]["censored"])                                    # 30 000 USD per side: too thin
        self.assertIsNone(by[50_000]["round_trip"])
        self.assertGreater(by[20_000]["round_trip"], by[5_000]["round_trip"])

    def test_universe_urls_cadence_and_errors(self):
        db = DB(":memory:")
        db.append("sim_orders", order_id="o", exp_id="LANE_x", ts=NOW - 86400, instrument="ABCUSDT.SPOT", side="buy",
                  qty=1, limit_px=None, style="taker", reduce_only=0, signal_ref="s", cost_model={})
        db.append("sim_fills", fill_id="o|0", order_id="o", exp_id="LANE_x", ts=NOW - 86400, instrument="ABCUSDT.SPOT",
                  side="buy", px=1.0, qty=1.0, fee=0.0, slippage=0.0, liquidity="taker", mid=1.0, book_ts=1.0)
        uni = capacity.universe(db, NOW)
        self.assertIn("ABCUSDT.SPOT", uni)
        self.assertTrue(set(moves.WATCH) <= set(uni))
        urls = []

        def get(u):
            urls.append(u)
            if u.endswith("/fapi/v1/exchangeInfo"):                                 # 21x point 2
                return json.dumps({"symbols": [{"symbol": "ETHUSDT", "status": "SETTLING"},
                                               {"symbol": "XAUUSDT", "status": "TRADING"}]}).encode()
            if "BTCUSDT" in u:
                raise OSError("down")
            return json.dumps(book()).encode()
        r = capacity.run(db, get, NOW, sleep=lambda s: None)
        self.assertEqual((r["books"], r["errors"], r["not_trading"]), (len(uni) - 2, 1, 1))
        self.assertEqual(urls[0], "https://fapi.binance.com/fapi/v1/exchangeInfo")
        urls = urls[1:]
        self.assertFalse(any("ETHUSDT" in u for u in urls))                         # no book call for SETTLING
        self.assertTrue(all(u.endswith("&limit=500") for u in urls))
        self.assertIn("https://data-api.binance.vision/api/v3/depth?symbol=ABCUSDT&limit=500", urls)
        self.assertTrue(all(u.startswith(("https://fapi.binance.com/fapi/v1/depth?", "https://data-api.binance.vision/api/v3/depth?"))
                            for u in urls))
        self.assertIn("skipped", capacity.run(db, get, NOW + 22 * 3600))
        self.assertEqual(db.one("SELECT COUNT(*) FROM observations WHERE detector=? AND metric='error'",
                                capacity.DETECTOR)[0], 1)
        latest = capacity.latest(db)
        self.assertEqual(latest["ts"], NOW)
        self.assertEqual([x["size_usd"] for x in latest["books"]["ABCUSDT.SPOT"]], list(capacity.SIZES))
        self.assertEqual(latest["books"]["ABCUSDT.SPOT"][0]["label"], "nutidig, ikke historisk")
        self.assertNotIn("BTCUSDT", latest["books"])
        self.assertEqual(latest["missing"]["ETHUSDT"], {"kind": "not_trading", "detail": "SETTLING"})
        self.assertEqual(latest["missing"]["BTCUSDT"]["kind"], "error")

    def test_without_exchange_info_the_curve_runs_as_before(self):
        db = DB(":memory:")

        def get(u):
            if "exchangeInfo" in u:
                raise OSError("down")
            return json.dumps(book()).encode()
        r = capacity.run(db, get, NOW, sleep=lambda s: None)
        self.assertEqual((r["errors"], r["not_trading"]), (0, 0))
        self.assertEqual(r["books"], len(capacity.universe(db, NOW)))


if __name__ == "__main__":
    unittest.main()
