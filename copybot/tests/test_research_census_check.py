"""Amendments 28/28a: census_check counts hours, gaps, duplicates, nulls and lags from the stored snapshots, and its
readiness counts C1 events and C2/C3 days without ever computing an outcome."""
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "research", "tools"))

import census_check as cc  # noqa: E402
from lab import census  # noqa: E402
from lab.db import DB  # noqa: E402

H0 = 1793059200                                                 # 2026-10-27 00:00 UTC


def prem(btc, spy, sym_extra=()):
    rows = [{"symbol": "BTCUSDT", "markPrice": str(btc), "indexPrice": str(btc), "lastFundingRate": "0.0001",
             "time": 0}, {"symbol": "SPYUSDT", "markPrice": str(spy), "indexPrice": str(spy), "lastFundingRate": "",
                          "time": 0}]
    return rows + [{"symbol": s, "markPrice": "1", "indexPrice": "1", "lastFundingRate": "0", "time": 0}
                   for s in sym_extra]


class Check(unittest.TestCase):
    def setUp(self):
        census._DONE.clear()
        self.tmp = tempfile.mkdtemp(prefix="cc")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def store(self, h, btc, spy, offset=61):
        rows = prem(btc, spy)
        for r in rows:
            r["time"] = (h + offset - 2) * 1000
        census.observe(self.db, h + offset, rows, lambda u: [], perps={"BTCUSDT"})

    def con(self):
        return sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)

    def test_hours_gaps_duplicates_nulls_and_lags(self):
        for k in range(6):
            if k != 3:                                          # one hour missing
                self.store(H0 + k * 3600, 100 + k, 500)
        self.db.append("observations", ts=H0 + 3600 + 300, detector="census/1", source="x", instrument=None,
                       metric="snapshot", value=0, threshold=None, flagged=0,
                       payload={"columns": ["markPrice"], "rows": {}})     # a duplicate in hour 1
        res = cc.check(self.con(), H0 + 5 * 3600 + 100)
        self.assertEqual((res["hours_expected"], res["hours_present"], res["hours_missing"]), (6, 5, 1))
        self.assertEqual(res["missing_first"], ["10-27 03:00"])
        self.assertEqual(res["duplicate_hours"], 1)
        self.assertEqual(res["row_behind_hour_s_max"], 61)
        self.assertEqual(res["premium_time_lag_s_median"], 2.0)
        self.assertEqual(res["coin_perps_min_median"], [1, 1])
        self.assertEqual(res["null_share"]["lastFundingRate"], 0.5)          # SPY's empty funding is null
        self.assertEqual(res["null_share"]["quoteVolume"], 1.0)              # no ticker rows in this test

    def test_readiness_counts_a_spy_shock_and_a_btc_day_without_outcomes(self):
        spy = 500.0
        for k in range(200):
            spy *= math.exp(0.001 * (1 if k % 2 else -1))
            if k == 190:
                spy *= math.exp(0.02)                           # a 20-sigma hour
            btc = 100.0 * (1.03 if k >= 24 else 1.0)            # +3 % from day 2
            self.store(H0 + k * 3600, btc, spy)
        r = cc.check(self.con(), H0 + 200 * 3600)["readiness"]
        self.assertEqual(r["c1_events"], 1)
        self.assertEqual(r["c2_candidate_days"], 1)
        self.assertGreaterEqual(r["c3_day_pairs"], 6)
        self.assertEqual(set(r), {"c1_events", "c1_clusters_need", "c2_candidate_days", "c2_clusters_need",
                                  "c3_day_pairs", "c3_need", "note"})                 # counts only, no outcome


if __name__ == "__main__":
    unittest.main()
