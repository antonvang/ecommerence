"""Amendment 21n point 1: the flag report deduplicates repeated scans of one hour, counts flags in the same hour on
several markets as one event, checks consistency and age, and stays NO_DECISION until 14 days and 2 weekends."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import flagreport  # noqa: E402
from lab.db import DB  # noqa: E402

H, D = 3600, 86400
SAT = 1_800_057_600                                                  # 2027-01-16 00:00 UTC, a Saturday


class Flags(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def scan(self, ts, sym, vr, flagged, open_s, book=None, stored=None):
        a = self.db.append
        a("observations", ts=ts, detector="abnormal_move/1", source="s", instrument=sym, metric="z_1h", value=0.1,
          threshold=4.0, flagged=0, payload={"open_s": open_s, "volume_ratio": vr, "z_1h": 0.1, "age_s": ts - open_s - H})
        a("observations", ts=ts, detector="abnormal_move/1", source="s", instrument=sym, metric="volume_ratio",
          value=stored if stored is not None else vr, threshold=5.0, flagged=int(flagged), payload={})
        if book is not None:
            a("observations", ts=ts, detector="abnormal_move/1", source="d", instrument=sym, metric="book_rt",
              value=book, threshold=None, flagged=0, payload={})

    def test_duplicates_events_quality_and_cost(self):
        h = SAT + 10 * H
        self.scan(h + H + 120, "BTCUSDT", 6.0, True, h, book=2e-6)
        self.scan(h + H + 900, "BTCUSDT", 6.0, True, h)                      # a restart re-scans the same hour
        self.scan(h + H + 120, "ETHUSDT", 5.5, True, h, stored=9.9)          # same hour, other market; inconsistent
        self.scan(h + 2 * H + 120, "BTCUSDT", 1.0, False, h + H, book=1e-6)
        r = flagreport.report(self.db.q)
        self.assertEqual((r["flags"], r["duplicate_rows"], r["independent_events"]), (2, 1, 1))
        self.assertEqual(r["events"][0]["markets"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(r["data_quality"]["inconsistent"], 1)
        self.assertEqual(r["by_market_metric"]["BTCUSDT|volume_ratio"]["observed_hours"], 2)
        self.assertEqual(r["by_market_metric"]["BTCUSDT|volume_ratio"]["weekend"], 1)
        self.assertEqual(r["following_cost"][0]["book_rt"], 2e-6)
        self.assertEqual(r["conclusion"], "NO_DECISION")
        self.assertIn("14 days", r["missing"])


if __name__ == "__main__":
    unittest.main()
