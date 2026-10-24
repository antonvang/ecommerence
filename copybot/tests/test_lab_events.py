"""LINUX_DRIFT 2026-10-24 23:11: the events view lists only what is recorded - a move with its known time, co-moving
markets, news as a coincidence (never a cause), alternative explanations and next step; data pauses, on-chain revisions
and missing books - newest first, and writes nothing."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import events  # noqa: E402
from lab.db import DB  # noqa: E402

NOW = 1_793_000_000


class View(unittest.TestCase):
    def test_kinds_order_and_honest_news(self):
        db = DB(":memory:")
        db.event("opportunity.move", "system:test", None, {
            "instrument": "XAUUSDT", "label": "Guld", "flags": ["z_1h"], "move_hour_s": NOW - 7200, "scan_ts": NOW - 3480,
            "z_1h": 4.5, "others": {"XAGUSDT": {"z_1h": 2.4}, "BTCUSDT": {"z_1h": 0.3}}, "news": [],
            "triage": {"verdict": "NOT_SCREENED", "explanations": ["unexplained"], "next": "kræver en dateret lås"}})
        db.event("risk.pause", "system:test", "FWD_x", {"rule": "data_fetch", "detail": "reset"})
        db.append("observations", ts=int(NOW - 60), detector="capacity/1", source="x", instrument="EPICUSDT",
                  metric="error", value=None, threshold=None, flagged=0, payload={"error": "empty book"})
        db.append("observations", ts=int(NOW - 100 * 3600), detector="capacity/1", source="x", instrument="OLD",
                  metric="error", value=None, threshold=None, flagged=0, payload={"error": "too old"})
        before = db.one("SELECT COUNT(*) FROM events")[0]
        v = events.view(db, NOW + 10)
        self.assertEqual(db.one("SELECT COUNT(*) FROM events")[0], before)
        kinds = [e["kind"] for e in v["events"]]
        self.assertEqual(sorted(kinds), ["book_missing", "data_pause", "move"])     # 100 h old: outside 72 h
        mv = next(e for e in v["events"] if e["kind"] == "move")
        self.assertEqual(mv["markets"], ["XAUUSDT", "XAGUSDT"])
        self.assertEqual(mv["known_ts"], NOW - 3480)
        self.assertTrue(mv["current"])
        self.assertEqual(mv["news_note"], "ingen nyhed i kilderne inden for ±3 timer")
        self.assertEqual(mv["explanations"], ["unexplained"])
        self.assertEqual(kinds[0], "book_missing")                                  # newest first
        self.assertIn("ændring 18", next(e for e in v["events"] if e["kind"] == "data_pause")["next"])

    def test_news_is_a_coincidence(self):
        db = DB(":memory:")
        db.event("opportunity.move", "system:test", None, {"instrument": "BTCUSDT", "scan_ts": NOW - 30 * 3600,
                                                          "news": [{"title": "t", "source": "s"}], "triage": {}})
        e = events.view(db, NOW)["events"][0]
        self.assertEqual(e["news_note"], events.CAUSE_NOTE)
        self.assertFalse(e["current"])


if __name__ == "__main__":
    unittest.main()
