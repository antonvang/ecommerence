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
        spec = {"template": "day_of_week", "execution": "taker"}
        self.db.append("experiments", exp_id=EID, version=1, created_ts=0, mechanism_tag="calendar_day_of_week",
                       fingerprint="f", spec_json=spec)
        self.db.append("transitions", exp_id=EID, ts=0, from_state=None, to_state="PAPER_TRADING", actor="fixture",
                       reason="fixture: approved for paper trading")
        pipeline.save_artifact(EID, "cost", {"selected": 1})
        pipeline.save_artifact(EID, "backtest", {"variants": [
            {"variant": 0, "params": {"mode": "flat_weekend"}, "fit": None, "positions": {}},
            {"variant": 1, "params": {"mode": "weekend_only"}, "fit": None, "positions": {}}]})

    def tearDown(self):
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


if __name__ == "__main__":
    unittest.main()
