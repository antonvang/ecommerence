"""research/PROTOCOL_V3.md amendment 42: the long carry book holds BTC and ETH long spot / short perp, 5 000 USDT per
leg, without the 14-day source rule. Simulated only; never evidence."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import carry90, lane  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402

HOUR, DAY = 3600, 86400
NOW = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc).timestamp()


def market(px=100.0, spread=0.02, rate=0.0001):
    def get(path):
        if path.startswith("https://data-api.binance.vision/api/v3/depth"):
            return {"bids": [[str(px - spread / 2), "1000"]], "asks": [[str(px + spread / 2), "1000"]]}
        if path.startswith("https://"):
            raise AssertionError(path)
        if "/fapi/v1/depth" in path:
            return {"bids": [[str(px - spread / 2), "1000"]], "asks": [[str(px + spread / 2), "1000"]]}
        if "klines" in path:
            start = int(get.now) // HOUR * HOUR - 1000 * HOUR
            return [[(start + i * HOUR) * 1000, px, px, px, px, 1, (start + (i + 1) * HOUR) * 1000 - 1, 100.0]
                    for i in range(1001)]
        if "fundingRate" in path:
            last = int(get.now) // (8 * HOUR) * 8 * HOUR
            return [{"fundingTime": (last - k * 8 * HOUR) * 1000, "fundingRate": str(rate)} for k in range(199, -1, -1)]
        raise AssertionError(path)
    get.now = NOW
    return get


class Carry90(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labc90")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True)]
        for p in self.p:
            p.start()
        self.get = market()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def accounts(self):
        with self.db.tx():
            self.db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                           metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(self.db, NOW - 60)
        return {i["key"]: (led, i) for led, i in lane.started(self.db).items()}

    def test_no_accounts_without_the_census(self):
        self.assertEqual(carry90.ensure(self.db, NOW), [])

    def test_two_accounts_once_outside_every_slot(self):
        acc = self.accounts()
        self.assertEqual(set(acc), {"carry90|BTCUSDT", "carry90|ETHUSDT", "carry90|XAUUSDT"})
        self.assertEqual(carry90.ensure(self.db, NOW), [])
        for led, i in acc.values():
            self.assertTrue(lane.is_carry90(i))
            self.assertFalse(lane.is_lane(i) or lane.is_scanner(i) or lane.is_hl(i) or lane.is_straks(i))
            self.assertEqual(lane.label(i), carry90.LABEL)

    def test_holds_5k_per_leg_and_never_rebalances(self):
        led = self.accounts()["carry90|BTCUSDT"][0]
        lane.run_one(self.db, led, self.get, NOW)
        pos = PaperEngine(self.db).ledger(led)["positions"]
        self.assertAlmostEqual(pos["BTCUSDT.SPOT"] * 100, 5000, delta=10)
        self.assertAlmostEqual(pos["BTCUSDT"] * 100, -5000, delta=10)
        n = self.db.one("SELECT COUNT(*) FROM sim_fills WHERE exp_id=?", led)[0]
        for k in range(1, 30):                                     # a month of hourly passes: no new fills
            self.get.now = NOW + k * DAY
            lane.run_one(self.db, led, self.get, NOW + k * DAY)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_fills WHERE exp_id=?", led)[0], n)

    def test_no_source_rule_at_14_days_but_loss_and_age(self):
        led, _ = self.accounts()["carry90|BTCUSDT"]
        info = lane.started(self.db)[led]
        lane.run_one(self.db, led, self.get, NOW)
        self.assertIsNone(lane._retire_reason(self.db, led, info, NOW + 20 * DAY, set())[0])
        self.assertEqual(lane._retire_reason(self.db, led, info, info["ts"] + 180 * DAY, set())[0], "expired")
        with self.db.tx():
            self.db.append("sim_equity", exp_id=led, ts=int(NOW + 3600), equity=9499.0, cash=9499.0, exposure=0.0,
                           peak=10000.0, drawdown=0.05)
        self.assertEqual(lane._retire_reason(self.db, led, info, NOW + 2 * HOUR, set())[0], "loss")

    def test_gold_trades_paxg_spot_against_the_xau_perp(self):
        led, info = self.accounts()["carry90|XAUUSDT"]
        self.assertEqual(lane.legs(info, "XAUUSDT"), ("XAUUSDT", "PAXGUSDT.SPOT"))
        seen = []
        g = self.get

        def log(path):
            seen.append(path)
            return g(path)
        log.now = NOW
        lane.run_one(self.db, led, log, NOW)
        pos = PaperEngine(self.db).ledger(led)["positions"]
        self.assertEqual(set(pos), {"PAXGUSDT.SPOT", "XAUUSDT"})
        self.assertAlmostEqual(pos["PAXGUSDT.SPOT"], -pos["XAUUSDT"], places=9)
        self.assertTrue(any("symbol=PAXGUSDT" in p for p in seen))
        self.assertFalse(any("symbol=XAUUSDT" in p and "data-api" in p for p in seen))

    def test_rules_text_on_the_dashboard(self):
        _, info = self.accounts()["carry90|ETHUSDT"]
        self.assertIn("180 dage", lane.rules_text(info))


if __name__ == "__main__":
    unittest.main()
