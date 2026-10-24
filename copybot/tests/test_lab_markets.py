"""LINUX_DRIFT 2026-10-24 22:23: the dashboard market scanner reads the detector's own observations - one sparkline
point per market hour (earliest scan), fresh/stale/error states, flags and the latest investigation."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import markets, moves  # noqa: E402
from lab.db import DB  # noqa: E402

H = 3600
NOW = 1_800_000_000 - 1_800_000_000 % H + 300


class View(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def obs(self, ts, sym, metric, value, payload, flagged=0):
        self.db.append("observations", ts=ts, detector="abnormal_move/1", source="s", instrument=sym, metric=metric,
                       value=value, threshold=None, flagged=flagged, payload=payload)

    def scan(self, ts, sym, price, open_s, flags=(), book=1e-5):
        p = {"open_s": open_s, "close_s": open_s + H, "price": price, "ret_1h": 0.001, "ret_24h": -0.002, "z_1h": 0.5,
             "z_24h": -0.1, "volume_ratio": 6.0 if flags else 1.0, "quote_volume_1h": 1e6, "mark": 100.1, "index": 100.0,
             "flags": list(flags)}
        self.obs(ts, sym, "z_1h", 0.5, p)
        self.obs(ts, sym, "book_rt", book, {"off_hours": True, "spread": 1e-5})

    def test_states_spark_flags_and_investigation(self):
        for k in range(3):                                                      # three hours, one rescan of the last
            self.scan(NOW - (3 - k) * H, "XAUUSDT", 100 + k, NOW - (4 - k) * H)
        self.scan(NOW - H + 1800, "XAUUSDT", 999, NOW - 2 * H,
                  flags=[{"metric": "volume_ratio", "value": 6.0, "threshold": 5.0, "rule": "21 point 4"}])
        self.scan(NOW - 5 * H, "BTCUSDT", 50, NOW - 6 * H)                       # last seen 5 h ago: stale
        self.obs(NOW - H + 1800, "CLUSDT", "error", None, {"error": "CLUSDT: boom"})
        self.db.append("events", ts=NOW - H, kind="opportunity.move", actor="system:scanner", exp_id=None,
                       payload={"instrument": "XAUUSDT", "flags": ["volume_ratio"], "news": [],
                                "triage": {"verdict": "FORWARD_ONLY", "explanations": ["off_hours"]}})
        v = markets.view(self.db, now=NOW)
        by = {m["symbol"]: m for m in v["markets"]}
        self.assertEqual(len(v["markets"]), len(moves.WATCH))
        x = by["XAUUSDT"]
        self.assertEqual(x["status"], "frisk")
        self.assertEqual([p for _, p in x["spark"]], [100, 101, 102])            # the rescan's 999 is not a new hour
        self.assertEqual(x["flags"][0]["metric"], "volume_ratio")
        self.assertEqual(x["investigation"]["triage"]["verdict"], "FORWARD_ONLY")
        self.assertAlmostEqual(x["premium"], 0.001)
        self.assertTrue(x["off_hours"])
        self.assertEqual(by["BTCUSDT"]["status"], "forældet")
        self.assertEqual(by["CLUSDT"]["status"], "fejl")
        self.assertEqual(by["SPYUSDT"]["status"], "ingen data")
        self.assertIn("ikke realtid", v["cadence"])

    def test_empty_registry(self):
        v = markets.view(self.db, now=NOW)
        self.assertIsNone(v["last_scan_ts"])
        self.assertTrue(all(m["status"] == "ingen data" and m["price"] is None for m in v["markets"]))


if __name__ == "__main__":
    unittest.main()
