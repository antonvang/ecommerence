"""Director order 44 P2: the net report's parts match lane.decomposition and sum to net."""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import lane, straks  # noqa: E402
from lab.db import DB  # noqa: E402
from research.tools import net_report  # noqa: E402
from tests.test_lab_straks import NOW, market  # noqa: E402


class NetReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labnet")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.p = mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parts_sum_to_net_and_match_the_lane_decomposition(self):
        with self.db.tx():
            self.db.append("observations", ts=NOW - 7200, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                           metric="z_1h", value=0.0, flagged=0, payload={})
        straks.ensure(self.db, NOW - 3600)
        led = [l for l, i in lane.started(self.db).items() if i["key"] == "straks|cont"][0]
        with mock.patch("time.time", lambda: NOW - 600):
            self.db.event("opportunity.move", "system:scanner", None, {"instrument": "CLUSDT", "flags": ["z_1h"],
                                                                     "ret_1h": 0.03, "ret_24h": 0.0})
        get = market()
        lane.run_one(self.db, led, get, NOW)
        get2 = market(px=101.0)
        get2.now = NOW + 24 * 3600
        lane.run_one(self.db, led, get2, NOW + 24 * 3600)
        con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        rep = net_report.build(con, NOW + 24 * 3600)
        r = [a for a in rep["accounts"] if a["ledger"] == led][0]
        d = lane.decomposition(self.db, led)
        self.assertAlmostEqual(r["net"], d["net"], places=6)
        self.assertAlmostEqual(-r["fees"], d["fees"], places=6)
        self.assertAlmostEqual(-r["book"], d["book"], places=6)
        self.assertAlmostEqual(-r["allowance"], d["allowance"], places=6)
        self.assertAlmostEqual(r["price_move"], d["price_basis"], places=6)
        self.assertAlmostEqual(r["net"], r["funding"] - r["fees"] - r["book"] - r["allowance"] + r["price_move"],
                               places=9)
        cl = r["instruments"]["CLUSDT"]
        self.assertEqual((cl["round_trips"], cl["direction_last"], cl["open_qty"]), (1, "long", 0.0))
        self.assertGreater(cl["realized_price_pnl"], 0)
        self.assertIn("Nettorapport", net_report.md(rep))

    def test_41b_flags(self):
        self.assertTrue(net_report.flagged("LANE_x|entry|58416|CLUSDT"))
        self.assertFalse(net_report.flagged("LANE_x|entry|60000|CLUSDT"))
        self.assertFalse(net_report.flagged("LANE_x|1793900000|BTCUSDT"))


if __name__ == "__main__":
    unittest.main()
