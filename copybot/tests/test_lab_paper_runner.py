"""Paper runner (Mission 6): simulated orders from the frozen variant against a faked public REST feed."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import lifecycle, paper_runner, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.lab_fixtures import approve_paper  # noqa: E402

HOUR = 3600
EID = "E_day_of_week_p1"
SAT = datetime(2026, 10, 17, 10, 30, tzinfo=timezone.utc).timestamp()     # Saturday
MON = datetime(2026, 10, 19, 0, 30, tzinfo=timezone.utc).timestamp()      # Monday


def feed(last_closed_end, px=100.0, spread=0.02):
    """Fake GET for /fapi/v1 klines, fundingRate and depth."""
    def get(path):
        if "klines" in path:
            start = int(last_closed_end) // HOUR * HOUR - 1000 * HOUR
            return [[(start + i * HOUR) * 1000, px, px, px, px, 1, (start + (i + 1) * HOUR) * 1000 - 1]
                    for i in range(1000)]
        if "fundingRate" in path:
            return [{"fundingTime": (int(last_closed_end) // (8 * HOUR) * 8 * HOUR) * 1000, "fundingRate": "0.0001"}]
        if "depth" in path:
            return {"bids": [[str(px - spread / 2), "1000"]], "asks": [[str(px + spread / 2), "1000"]]}
        raise AssertionError(path)
    return get


class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labpaper")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts"))
        self.p.start()
        self.sup = mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True)
        self.sup.start()
        spec = {"template": "day_of_week", "execution": "taker"}
        self.db.append("experiments", exp_id=EID, version=1, created_ts=0, mechanism_tag="calendar_day_of_week",
                       fingerprint="f", spec_json=spec)
        approve_paper(self.db, EID)
        pipeline.save_artifact(EID, "cost", {"selected": 1})
        pipeline.save_artifact(EID, "backtest", {"variants": [
            {"variant": 0, "params": {"mode": "flat_weekend"}, "fit": None, "positions": {}},
            {"variant": 1, "params": {"mode": "weekend_only"}, "fit": None, "positions": {}}]})

    def tearDown(self):
        self.sup.stop()
        self.p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_orders_fills_pnl_idempotent_and_reconciled(self):
        r = paper_runner.run(self.db, feed(SAT), SAT)["results"][EID]
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(r["orders"]), len(data.UNIVERSE))                      # weekend: go long all 8
        self.assertTrue(all(o["status"] == "filled" for o in r["orders"]))
        pnl = r["pnl"]
        self.assertTrue(pnl["simulated"])
        self.assertAlmostEqual(pnl["total"], pnl["realized"] + pnl["unrealized"], places=9)
        fees = self.db.one("SELECT SUM(fee) FROM sim_fills")[0]
        self.assertAlmostEqual(pnl["realized"], -fees, places=6)                    # only fees realised so far
        self.assertLess(pnl["unrealized"], 0)                                       # paid half-spread + slippage
        self.assertTrue(r["reconciled"])
        n_orders = self.db.one("SELECT COUNT(*) FROM sim_orders")[0]
        paper_runner.run(self.db, feed(SAT), SAT + 60)                              # same hour again
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], n_orders)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_equity")[0], 1)       # one mark per hour
        # Monday: weekend_only goes flat with reduce-only sells; P&L is fully realised
        r2 = paper_runner.run(self.db, feed(MON), MON)["results"][EID]
        self.assertTrue(all(o["status"] == "filled" for o in r2["orders"]))
        self.assertEqual(PaperEngine(self.db).ledger(EID)["positions"], {})
        self.assertAlmostEqual(r2["pnl"]["unrealized"], 0.0, places=9)
        self.assertLess(r2["pnl"]["realized"], 0)                                   # flat prices: costs only
        self.assertTrue(PaperEngine(self.db).reconcile(EID)["ok"])

    def test_cross_sectional_strategy_trades_long_short_and_reconciles(self):
        eid = "E_xs_momentum_p2"
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="cross_sectional_momentum",
                       fingerprint="x", spec_json={"template": "xs_momentum", "execution": "taker"})
        approve_paper(self.db, eid)
        pipeline.save_artifact(eid, "cost", {"selected": 0})
        pipeline.save_artifact(eid, "backtest", {"variants": [{"variant": 0, "params": {"lookback_days": 7, "k": 2},
                                                               "fit": None, "positions": {}}]})
        r = paper_runner.run(self.db, feed(SAT), SAT)["results"][eid]
        self.assertEqual(r["status"], "ok")
        sides = {o["symbol"]: self.db.one("SELECT side FROM sim_orders WHERE order_id LIKE ?", f"{eid}|%|{o['symbol']}")[0]
                 for o in r["orders"]}
        self.assertEqual(sorted(sides.values()), ["buy", "buy", "sell", "sell"])   # k = 2 long, 2 short
        self.assertTrue(r["reconciled"])

    def test_stale_data_pauses_and_blocks_new_trades(self):
        r = paper_runner.run(self.db, feed(SAT - 5 * HOUR), SAT)["results"][EID]
        self.assertEqual(r["status"], "paused")
        self.assertEqual(lifecycle.state(self.db, EID), "PAUSED")
        self.assertTrue(Risk(self.db).paused(EID))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)

    def test_fetch_failure_pauses(self):
        def broken(path):
            raise IOError("network down")
        r = paper_runner.run(self.db, broken, SAT)["results"][EID]
        self.assertEqual(r["status"], "paused")
        self.assertEqual(lifecycle.state(self.db, EID), "PAUSED")

    def test_fail_closed_blocks_runner(self):
        Risk(self.db).trip_fail_closed("disk_low", "test")
        paper_runner.run(self.db, feed(SAT), SAT)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)

    def test_reconciliation_detects_orphan_fill(self):
        paper_runner.run(self.db, feed(SAT), SAT)
        self.db.append("sim_fills", fill_id="ghost", order_id="nope", exp_id=EID, ts=1, instrument="X", side="buy",
                       px=1.0, qty=1.0, fee=0.0, slippage=0.0, liquidity="taker", mid=1.0, book_ts=1)
        rec = PaperEngine(self.db).reconcile(EID)
        self.assertFalse(rec["ok"])
        self.assertIn("1 fills without an order", rec["problems"])


class Shadow(unittest.TestCase):
    """research/PROTOCOL_V3.md amendment 3: simulated shadow ledger for observation candidates."""
    EID = "E_mvrv_value_p3"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labshadow")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts"))
        self.p.start()
        self.sup = mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True)
        self.sup.start()
        self.db.append("experiments", exp_id=self.EID, version=1, created_ts=0, mechanism_tag="onchain_value_mvrv",
                       fingerprint="f", spec_json={"template": "mvrv_value", "execution": "taker"})
        self.db.append("transitions", exp_id=self.EID, ts=0, from_state=None, to_state="OBSERVATION", actor="fixture",
                       reason="fixture: on the observation list")
        pipeline.save_artifact(self.EID, "cost", {"selected": 0})
        pipeline.save_artifact(self.EID, "backtest", {"variants": [{"variant": 0, "params": {"mode": "level", "k": 3},
                                                                    "fit": None, "positions": {}}]})

    def tearDown(self):
        self.sup.stop()
        self.p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cm(self, url):
        rows = []
        for j, s in enumerate(data.UNIVERSE_CM16):
            for d in range(130):
                day = datetime.fromtimestamp(int(SAT) // 86400 * 86400 - (d + 1) * 86400, timezone.utc)
                rows.append({"asset": s.replace("USDT", "").lower(), "time": day.strftime("%Y-%m-%dT00:00:00.000000000Z"),
                             "CapMVRVCur": str(0.5 + 0.1 * j)})
        return {"data": rows}

    def counts(self):
        return {k: self.db.one(f"SELECT COUNT(*) FROM {k} WHERE exp_id=?", self.EID)[0]
                for k in ("results", "transitions", "trials")}

    def test_needs_a_human_start_while_in_observation(self):
        self.assertEqual(paper_runner.run(self.db, feed(SAT), SAT, cm_get=self.cm)["experiments"], 0)
        self.db.event("shadow.approved", "agent:x", self.EID, {"reason": "not a human"})
        self.assertEqual(paper_runner.run(self.db, feed(SAT), SAT, cm_get=self.cm)["experiments"], 0)
        with self.assertRaises(lifecycle.LifecycleError):
            PaperEngine(self.db).start("SHADOW_" + self.EID, 10_000.0, paper_runner.cost_model())

    def test_trades_long_short_on_a_separate_ledger_without_touching_the_formal_tests(self):
        before = self.counts()
        self.db.event("shadow.approved", "human:test", self.EID, {"reason": "user asked for shadow trading"})
        out = paper_runner.run(self.db, feed(SAT), SAT, cm_get=self.cm)["results"]
        r = out["SHADOW_" + self.EID]
        self.assertEqual(r["status"], "ok")
        sides = sorted(self.db.one("SELECT side FROM sim_orders WHERE order_id=?",
                                   f"SHADOW_{self.EID}|{int(SAT) // 3600 * 3600}|{o['symbol']}")[0] for o in r["orders"])
        self.assertEqual(sides, ["buy"] * 3 + ["sell"] * 3)                       # 3 cheapest long, 3 dearest short
        self.assertTrue(r["reconciled"])
        self.assertAlmostEqual(r["pnl"]["total"], r["pnl"]["realized"] + r["pnl"]["unrealized"], places=9)
        self.assertEqual(self.counts(), before)                                   # no results, transitions, trials
        self.assertEqual(lifecycle.state(self.db, self.EID), "OBSERVATION")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", self.EID)[0], 0)
        from lab import command
        b = command.balance(self.db)
        self.assertEqual((b["shadow"], b["active"]), (1, 1))
        v = command.paper_view(self.db)["strategies"][0]
        self.assertTrue(v["shadow"])
        self.assertIn("ikke godkendt", v["label"])
        self.assertIn("skyggehandel", v["name"])
        # leaving OBSERVATION ends shadow trading
        self.db.append("transitions", exp_id=self.EID, ts=1, from_state="OBSERVATION", to_state="REJECTED",
                       actor="fixture", reason="fixture: forward test failed")
        out = paper_runner.run(self.db, feed(SAT + 3600), SAT + 3600, cm_get=self.cm)["results"]
        self.assertEqual(out["SHADOW_" + self.EID]["status"], "closing")          # amendment 4: positions closed
        self.assertEqual(PaperEngine(self.db).ledger("SHADOW_" + self.EID)["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile("SHADOW_" + self.EID)["ok"])
        out = paper_runner.run(self.db, feed(SAT + 7200), SAT + 7200, cm_get=self.cm)
        self.assertEqual(out["experiments"], 0)                                    # nothing left to trade or close

    def test_a_coinmetrics_failure_pauses_the_shadow_ledger_only(self):
        self.db.event("shadow.approved", "human:test", self.EID, {"reason": "user asked for shadow trading"})

        def broken(url):
            raise IOError("coinmetrics down")
        r = paper_runner.run(self.db, feed(SAT), SAT, cm_get=broken)["results"]["SHADOW_" + self.EID]
        self.assertEqual(r["status"], "paused")
        self.assertTrue(Risk(self.db).paused("SHADOW_" + self.EID))
        self.assertEqual(lifecycle.state(self.db, self.EID), "OBSERVATION")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)


if __name__ == "__main__":
    unittest.main()
