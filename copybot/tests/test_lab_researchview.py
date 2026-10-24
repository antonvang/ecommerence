"""LINUX_DRIFT 2026-10-24 22:28: the dashboard research pipeline keeps research-memory's statuses apart, lists the
forward tests and shows capacity as UNTESTABLE_CAPACITY per paper ledger without any curve."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypogen, researchview  # noqa: E402
from lab.db import DB  # noqa: E402


class View(unittest.TestCase):
    def test_statuses_stay_apart_and_capacity_is_untestable(self):
        db = DB(":memory:")
        db.event(hypogen.EV_SCREEN, "system:test", None, {"key": "a|ar_1d|m17", "verdict": "UNTESTABLE", "n": 3})
        db.event(hypogen.EV_SCREEN, "system:test", None, {"key": "b|ar_1d|m17", "verdict": "SCREEN_FAIL", "n": 40,
                                                          "checks": {"p <= 0.005": False}})
        db.append("sim_orders", order_id="o", exp_id="LANE_x", ts=1, instrument="X", side="buy", qty=1, limit_px=None,
                  style="taker", reduce_only=0, signal_ref="s", cost_model={})
        db.append("sim_fills", fill_id="o|0", order_id="o", exp_id="LANE_x", ts=1, instrument="X", side="buy", px=1.0,
                  qty=1.0, fee=0.0, slippage=0.0, liquidity="taker", mid=1.0, book_ts=1.0)
        v = researchview.view(db, now=10)
        st = {r["id"]: r["status"] for r in v["records"]}
        self.assertEqual((st["a|ar_1d|m17"], st["b|ar_1d|m17"]), ("UNTESTABLE", "SCREEN_FAIL"))
        self.assertGreaterEqual(v["by_status"]["SCREEN_FAIL"], 1)                   # committed studies are counted too
        self.assertEqual(v["capacity"], [{"ledger": "LANE_x", "status": "UNTESTABLE_CAPACITY",
                                          "why": researchview.CAPACITY_WHY}])
        self.assertEqual([s["stage"] for s in v["stages"]], list(researchview.STAGES))
        self.assertIn("M1F", [f["hypothesis"] for f in v["forward"]])


if __name__ == "__main__":
    unittest.main()
