"""research/PROTOCOL_V3.md amendment 43: the pairs book sells the rich leg and buys the cheap one at |z| >= 2 of the
720 h log spread, out at |z| <= 0.5, |z| >= 4 or 72 h. Simulated only; never evidence."""
import math
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import lane, pairs, paper_runner  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402

HOUR = 3600
NOW = datetime(2026, 11, 5, 22, 30, tzinfo=timezone.utc).timestamp()


def market(shock):
    """BZ wiggles around WTI; `shock(i_last)` is BZ's log offset on the latest closed bar."""
    def close(sym, i, last):
        base = 100.0 if sym != "BZUSDT" else 100.0 * math.exp(0.001 * math.sin(i) + (shock() if i == last else 0.0))
        return base

    def get(path):
        if path.startswith("https://"):
            raise AssertionError(path)
        sym = path.split("symbol=")[1].split("&")[0]
        start = int(get.now) // HOUR * HOUR - 1000 * HOUR
        last = 999
        if "klines" in path:
            return [[(start + i * HOUR) * 1000, close(sym, i, last), 0, 0, close(sym, i, last), 1,
                     (start + (i + 1) * HOUR) * 1000 - 1, 100.0] for i in range(1001)]
        if "fundingRate" in path:
            return []
        if "/fapi/v1/depth" in path:
            px = close(sym, last, last)
            return {"bids": [[str(px * 0.9999), "1000"]], "asks": [[str(px * 1.0001), "1000"]]}
        raise AssertionError(path)
    get.now = NOW
    return get


class Pairs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labpairs")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch.object(pairs, "PAIRS", (("BZUSDT", "CLUSDT"),))]
        for p in self.p:
            p.start()
        paper_runner._HOURLY.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def account(self):
        with self.db.tx():
            self.db.append("observations", ts=NOW - 7200, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                           metric="z_1h", value=0.0, flagged=0, payload={})
        pairs.ensure(self.db, NOW - 60)
        (led, info), = lane.started(self.db).items()
        return led, info

    def test_starts_once_only_where_the_move_scanner_runs(self):
        self.assertEqual(pairs.ensure(self.db, NOW), [])
        led, info = self.account()
        self.assertEqual(pairs.ensure(self.db, NOW), [])
        self.assertTrue(lane.is_pairs(info) and not lane.is_lane(info))
        self.assertEqual(lane.legs(info, "BZUSDT"), ("BZUSDT",))

    def test_sells_the_rich_leg_then_exits_when_the_spread_is_normal(self):
        led, _ = self.account()
        s = {"v": 0.02}                                             # 20x the wiggle: z far above 2 (and below 4?)
        get = market(lambda: s["v"])
        z, _ = pairs.zscore(paper_runner.hourly("BZUSDT", NOW, get)[0], paper_runner.hourly("CLUSDT", NOW, get)[0], NOW)
        s["v"] = 0.002                                             # pick a shock with 2 <= z < 4
        z, _ = pairs.zscore(paper_runner.hourly("BZUSDT", NOW, get)[0], paper_runner.hourly("CLUSDT", NOW, get)[0], NOW)
        self.assertTrue(2 <= z < 4, z)
        lane.run_one(self.db, led, get, NOW)
        pos = PaperEngine(self.db).ledger(led)["positions"]
        self.assertLess(pos["BZUSDT"], 0)
        self.assertGreater(pos["CLUSDT"], 0)
        self.assertAlmostEqual(pos["CLUSDT"] * 100, pairs.LEG_USD, delta=5)
        s["v"] = 0.0                                                # back to normal next hour
        get.now = NOW + HOUR
        lane.run_one(self.db, led, get, NOW + HOUR)
        led_ = PaperEngine(self.db).ledger(led)
        self.assertEqual(led_["positions"], {})
        self.assertEqual(len(led_["trades"]), 2)

    def test_no_signal_no_order_and_time_exit(self):
        led, _ = self.account()
        s = {"v": 0.0}
        get = market(lambda: s["v"])
        lane.run_one(self.db, led, get, NOW)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", led)[0], 0)
        s["v"] = 0.002
        lane.run_one(self.db, led, get, NOW + 60)
        self.assertTrue(PaperEngine(self.db).ledger(led)["positions"])
        t = NOW + 60 + 72 * HOUR                                     # the shock stays: only the 72 h rule closes
        get.now = t
        lane.run_one(self.db, led, get, t)
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})

    def test_short_history_gives_no_z(self):
        bars = [(i * HOUR, 1.0, 1.0 + 0.01 * (i % 3)) for i in range(100)]
        z, why = pairs.zscore(bars, bars, 100 * HOUR + 60)
        self.assertIsNone(z)
        self.assertIn("fælles timer", why)


if __name__ == "__main__":
    unittest.main()
