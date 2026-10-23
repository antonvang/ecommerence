"""research/LINUX_DRIFT.md 2026-10-23: forward tests next to the buy-and-hold of the coins they traded (display only)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import benchmark, command  # noqa: E402
from lab.db import DB  # noqa: E402

T0 = 1_792_400_000                                   # the ledger's first mark
NOW = T0 + 5 * 86400


class Feed:
    def __init__(self, start, now):
        self.start, self.now, self.calls = start, now, []

    def __call__(self, path):
        self.calls.append(path)
        if path.startswith("/fapi/v1/ticker/price"):
            return [{"symbol": s, "price": str(p)} for s, p in self.now.items()]
        sym = path.split("symbol=")[1].split("&")[0]
        return [[T0 // 3600 * 3600 * 1000, str(self.start[sym]), "0", "0", "0", "0"]]


class Benchmark(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labbh")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        led = "FWD_E_x_p1"
        for ts, eq in ((T0, 10000.0), (NOW - 600, 10279.0)):
            self.db.append("sim_equity", exp_id=led, ts=ts, equity=eq, cash=1000.0, exposure=9000.0, peak=eq,
                           drawdown=0.0)
        for i, sym in enumerate(("AAAUSDT", "BBBUSDT")):
            self.db.append("sim_fills", fill_id=f"f{i}", order_id=f"o{i}", exp_id=led, ts=T0, instrument=sym,
                           side="buy", px=1.0, qty=1.0, fee=0.0, slippage=0.0, liquidity="taker", mid=1.0, book_ts=T0)
        benchmark._TRIED["t"] = 0.0
        self.feed = Feed({"AAAUSDT": 100.0, "BBBUSDT": 10.0}, {"AAAUSDT": 106.0, "BBBUSDT": 10.0, "CCCUSDT": 1.0})

    def tearDown(self):
        self.db.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_equal_weight_buy_and_hold_of_the_traded_coins_once_an_hour(self):
        self.assertEqual(benchmark.update(self.db, NOW, self.feed), 1)
        b = benchmark.latest(self.db)["FWD_E_x_p1"]
        self.assertAlmostEqual(b["bh_return"], 0.03)                 # (+6 % + 0 %) / 2
        self.assertEqual(b["symbols"], 2)
        self.assertEqual(benchmark.update(self.db, NOW + 600, self.feed), 0)          # not again within the hour
        n = len(self.feed.calls)
        benchmark._TRIED["t"] = 0.0
        self.assertEqual(benchmark.update(self.db, NOW + 3700, self.feed), 1)
        self.assertEqual(len(self.feed.calls), n + 1)               # start prices kept: one ticker call only

    def test_a_failed_attempt_waits_ten_minutes_before_the_next_network_call(self):
        def down(path):
            raise OSError("network down")
        with self.assertRaises(OSError):
            benchmark.update(self.db, NOW, down)
        self.assertEqual(benchmark.update(self.db, NOW + 60, self.feed), 0)
        self.assertEqual(self.feed.calls, [])
        self.assertEqual(benchmark.update(self.db, NOW + 700, self.feed), 1)

    def test_the_balance_shows_forward_pnl_next_to_buy_and_hold(self):
        benchmark.update(self.db, NOW, self.feed)
        fw = [{"exp_id": "FWD_E_x_p1", "capital": 10000.0, "equity": [{"equity": 10279.0}]}]
        r = command._forward_vs_buy_and_hold(self.db, fw)
        self.assertEqual(r["bh_ledgers"], 1)
        self.assertAlmostEqual(r["bh_pnl"], 300.0)
        self.assertAlmostEqual(r["vs_bh"], -21.0)                    # +279 USD is 21 USD behind buy-and-hold
        self.assertEqual(command._forward_vs_buy_and_hold(self.db, [])["bh_ledgers"], 0)


if __name__ == "__main__":
    unittest.main()
