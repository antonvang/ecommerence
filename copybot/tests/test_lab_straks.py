"""research/PROTOCOL_V3.md amendment 41: the straks-bog trades every abnormal-move record at once on paper (follow and
fade), 1 000 USDT per position, at most one per market, out after 24 h. Simulated only; never evidence."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import lane, paper_runner, straks  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402

HOUR = 3600
NOW = datetime(2026, 11, 5, 21, 0, tzinfo=timezone.utc).timestamp()


def market(px=100.0, spread=0.02):
    def get(path):
        if path.startswith("https://"):
            raise AssertionError(path)
        if "/fapi/v1/depth" in path:
            return {"bids": [[str(px - spread / 2), "1000"]], "asks": [[str(px + spread / 2), "1000"]]}
        if "klines" in path:
            start = int(get.now) // HOUR * HOUR - 50 * HOUR
            return [[(start + i * HOUR) * 1000, px, px, px, px, 1, (start + (i + 1) * HOUR) * 1000 - 1, 100.0]
                    for i in range(51)]
        if "fundingRate" in path:
            return []
        raise AssertionError(path)
    get.now = NOW
    return get


class Straks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labstraks")
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

    def scanner_ran(self, ts=NOW - 7200):
        with self.db.tx():
            self.db.append("observations", ts=ts, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                           metric="z_1h", value=0.0, flagged=0, payload={})

    def move(self, sym="CLUSDT", ret_1h=0.03, flags=("z_1h",), ret_24h=0.01, at=None):
        with mock.patch("time.time", lambda: at or NOW):
            self.db.event("opportunity.move", "system:scanner", None, {"instrument": sym, "flags": list(flags),
                                                                     "ret_1h": ret_1h, "ret_24h": ret_24h})

    def accounts(self, now=NOW):
        self.scanner_ran()
        straks.ensure(self.db, now - 3600)
        info = lane.started(self.db)
        return {i["key"]: (led, i) for led, i in info.items()}

    def step(self, led, now):
        self.get.now = now
        return lane.run_one(self.db, led, self.get, now)

    def test_no_accounts_without_the_move_scanner(self):
        self.assertEqual(straks.ensure(self.db, NOW), [])
        self.assertEqual(lane.started(self.db), {})

    def test_two_accounts_once_outside_every_slot(self):
        acc = self.accounts()
        self.assertEqual(set(acc), set(straks.BOOKS))
        self.assertEqual(straks.ensure(self.db, NOW), [])                         # idempotent
        for led, i in acc.values():
            self.assertTrue(lane.is_active(self.db, led))
            self.assertTrue(lane.is_straks(i))
            self.assertFalse(lane.is_lane(i) or lane.is_scanner(i) or lane.is_hl(i))
            self.assertEqual(lane.label(i), straks.LABEL)

    def test_direction_rule(self):
        self.assertEqual(straks.direction({"flags": ["z_1h"], "ret_1h": 0.02, "ret_24h": -0.05}), 1)
        self.assertEqual(straks.direction({"flags": ["z_24h"], "ret_1h": 0.02, "ret_24h": -0.05}), -1)
        self.assertEqual(straks.direction({"flags": ["volume_ratio"], "ret_1h": -0.01, "ret_24h": 0.05}), -1)
        self.assertEqual(straks.direction({"flags": ["z_1h"], "ret_1h": 0.0}), 0)

    def test_follow_buys_fade_sells_then_both_exit_after_24h(self):
        acc = self.accounts()
        self.move(at=NOW - 600)
        (cont, _), (rev, _) = acc["straks|cont"], acc["straks|rev"]
        self.step(cont, NOW)
        self.step(rev, NOW)
        pc = PaperEngine(self.db).ledger(cont)["positions"]["CLUSDT"]
        pr_ = PaperEngine(self.db).ledger(rev)["positions"]["CLUSDT"]
        self.assertAlmostEqual(pc * 100, straks.SIZE_USD, delta=5)
        self.assertAlmostEqual(pr_ * 100, -straks.SIZE_USD, delta=5)
        self.step(cont, NOW + 23 * HOUR)                                           # held
        self.assertIn("CLUSDT", PaperEngine(self.db).ledger(cont)["positions"])
        self.step(cont, NOW + 24 * HOUR)
        self.step(rev, NOW + 24 * HOUR)
        for led in (cont, rev):
            led_ = PaperEngine(self.db).ledger(led)
            self.assertEqual(led_["positions"], {})
            self.assertEqual(len(led_["trades"]), 1)
            self.assertLess(led_["trades"][0][1], 0)                               # flat price: costs only

    def test_one_position_per_market_and_stale_records_skipped(self):
        acc = self.accounts()
        cont = acc["straks|cont"][0]
        self.move(at=NOW - 600)
        self.step(cont, NOW)
        self.move(at=NOW + 300)                                                   # same market while open
        self.move(sym="XAUUSDT", at=NOW - 1800)                                   # 2.5 h old at the next pass
        self.step(cont, NOW + 2 * HOUR)
        sk = [json.loads(r["payload"])["reason"] for r in self.db.q(
            "SELECT payload FROM events WHERE kind='straks.skipped' AND exp_id=? ORDER BY id", cont)]
        self.assertEqual(sorted(sk), ["for gammel", "åben position på markedet"])
        self.assertEqual(set(PaperEngine(self.db).ledger(cont)["positions"]), {"CLUSDT"})
        n = self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", cont)[0]
        self.step(cont, NOW + 2 * HOUR + 300)                                      # replays nothing
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", cont)[0], n)

    def test_retires_on_loss_only_not_when_flat(self):
        acc = self.accounts()
        led, info = acc["straks|cont"]
        info = lane.started(self.db)[led]
        self.assertEqual(lane._retire_reason(self.db, led, info, NOW + 10 * 86400, set())[0], None)
        PaperEngine(self.db, lambda: NOW).start(led, straks.CAPITAL, straks.COSTS)
        with self.db.tx():
            self.db.append("sim_equity", exp_id=led, ts=int(NOW), equity=7900.0, cash=7900.0, exposure=0.0,
                           peak=10000.0, drawdown=0.21)
        self.assertEqual(lane._retire_reason(self.db, led, info, NOW + 3600, set())[0], "loss")

    def test_no_network_beyond_fapi(self):
        acc = self.accounts()
        self.move(at=NOW - 600)
        seen = []
        g = self.get

        def log(path):
            seen.append(path)
            return g(path)
        log.now = NOW
        lane.run_one(self.db, acc["straks|cont"][0], log, NOW)
        self.assertTrue(seen)
        self.assertTrue(all(p.startswith("/fapi/v1/") for p in seen), seen)

    def test_a_record_written_after_the_pass_started_waits_for_the_next_pass(self):
        acc = self.accounts()
        cont = acc["straks|cont"][0]
        self.move(at=NOW + 30)                                    # 41b: written after this pass's clock
        self.step(cont, NOW)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", cont)[0], 0)
        self.step(cont, NOW + 60)
        o = self.db.one("SELECT ts FROM sim_orders WHERE exp_id=?", cont)
        self.assertGreaterEqual(o["ts"], NOW + 30)

    def test_dashboard_and_daily_report_show_the_accounts(self):
        from lab import command
        acc = self.accounts()
        self.move(at=NOW - 600)
        self.step(acc["straks|cont"][0], NOW)
        view = command.lane_view(self.db, NOW + 60)
        rows = {r["ledger"]: r for r in view["active"]}
        cont = rows[acc["straks|cont"][0]]
        self.assertEqual(cont["held"], ["CLUSDT"])
        self.assertIn("straks", cont["rules"])
        day = datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%d")
        rep = lane.report(self.db, day)
        self.assertEqual({r["source"] for r in rep["accounts"]}, {"straks"})


if __name__ == "__main__":
    unittest.main()
