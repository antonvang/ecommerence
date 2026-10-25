"""Amendment 21d: the FOMC integration report - locked windows from the close at T, the detector's z for the event
hour, missing bars stay missing, news matched by the publisher's time, and no report before the 24 h window closes."""
import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import eventreport, moves  # noqa: E402
from lab.db import DB  # noqa: E402

H = 3600
T = 1793210400                                       # 2026-10-28 18:00 UTC


def klines(jump=0.0, drop=()):
    out, px = [], 100.0
    for i in range(-(moves.HIST + 2), 24):
        o = T + i * H
        px *= math.exp((0.001 if i % 2 else -0.001) + (jump if i == 0 else 0.0))
        if o not in drop:
            out.append([o * 1000, "0", "0", "0", f"{px:.8f}", "1", (o + H) * 1000 - 1, "1000", 1, "0", "0", "0"])
    return out


class Market(unittest.TestCase):
    def test_locked_windows_and_event_hour_z(self):
        m = eventreport.market(lambda url: klines(jump=0.01), "XAUUSDT", T)
        self.assertAlmostEqual(m["ret_1h"], 0.01 + (-0.001), places=9)            # bar 18:00-19:00 (i = 0, even)
        self.assertAlmostEqual(m["z_event_hour"], (0.01 - 0.001) / 0.001, places=6)
        self.assertAlmostEqual(m["volume_ratio_event_hour"], 1.0)
        self.assertEqual(m["missing"], [])
        self.assertEqual(len(m["sha256"]), 64)

    def test_missing_bars_stay_missing(self):
        m = eventreport.market(lambda url: klines(drop=(T + 3 * H,)), "XAUUSDT", T)
        self.assertIsNone(m["ret_4h"])
        self.assertIn("bar closing T + 4h", m["missing"])
        self.assertIn("error", eventreport.market(lambda url: (_ for _ in ()).throw(OSError("down")), "CLUSDT", T))


class Chain(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def test_records_news_and_calendar_are_reported(self):
        db = self.db
        db.append("observations", ts=T + 3720, detector="abnormal_move/1", source="s", instrument="XAUUSDT",
                  metric="z_1h", value=5.0, threshold=4.0, flagged=1, payload={"close_s": T + 3600})
        db.append("observations", ts=T + 3720, detector="abnormal_move/1", source="s", instrument="CLUSDT",
                  metric="error", value=None, threshold=None, flagged=0, payload={"error": "CLUSDT: boom"})
        db.append("events", ts=T + 3720, kind="opportunity.move", actor="system:scanner", exp_id=None, payload={
            "instrument": "XAUUSDT", "flags": ["z_1h"], "move_hour_s": T,
            "macro": {"releases": [{"event": "FOMC statement", "ts": T}]},
            "news": [{"title": "Fed holds", "published_ts": T + 60}, {"title": "later", "published_ts": T + 5000}]})
        db.append("observations", ts=T + 420, detector="news/1", source=eventreport.FED, instrument="fed:1",
                  metric="news_item", value=T + 30, threshold=None, flagged=0,
                  payload={"title": "Federal Reserve issues FOMC statement", "published_ts": T + 30})
        db.append("observations", ts=T + 900, detector="news/1", source=eventreport.OTHER_MACRO["cnbc_economy"],
                  instrument="cnbc:1", metric="news_item", value=T + 300, threshold=None, flagged=0,
                  payload={"title": "Federal Reserve issues FOMC statement", "published_ts": T + 300})
        s = eventreport.scanner(db.q, T)
        self.assertEqual(s["flags"][0]["delay_s"], 120)
        self.assertEqual(s["problems"][0]["detail"], "CLUSDT: boom")
        r = s["records"][0]
        self.assertTrue(r["fomc_in_macro"])
        self.assertEqual((r["news"], r["news_public_before_hour_end"]), (2, 1))
        n = eventreport.newschain(db.q, T)
        self.assertEqual(n["fed"][0]["latency_s"], 390)
        self.assertEqual(n["other_macro"]["cnbc_economy"], {"items": 1, "first_latency_s": 600})
        self.assertEqual(n["duplicate_titles"], 1)
        self.assertEqual((n["fed_status"], n["fed_latest_stored"]["label"], n["fed_errors"]), ("ok", "i vinduet", 0))

    def test_missing_and_stale_fed_data_are_marked_never_shown_as_current(self):
        db = self.db
        db.append("observations", ts=T - 9 * 86400, detector="news/1", source=eventreport.FED, instrument="fed:0",
                  metric="news_item", value=T - 9 * 86400, threshold=None, flagged=0,
                  payload={"title": "old release", "published_ts": T - 9 * 86400})
        db.append("observations", ts=T + 600, detector="news/1", source=eventreport.FED, instrument=None,
                  metric="news_error", value=None, threshold=None, flagged=0, payload={"error": "HTTPError 404"})
        n = eventreport.newschain(db.q, T)
        self.assertEqual((n["fed"], n["fed_status"], n["fed_errors"]), ([], "mangler", 1))
        self.assertEqual(n["fed_latest_stored"]["label"], "forældet")
        self.assertEqual(n["fed_latest_stored"]["published_ts"], T - 9 * 86400)
        empty = DB(":memory:")
        self.assertIsNone(eventreport.newschain(empty.q, T)["fed_latest_stored"])
        self.assertIsNone(eventreport.newschain(empty.q, T)["fed_last_fetch_ok"])
        db.append("observations", ts=T - 300, detector="news/1", source=eventreport.FED, instrument=None,
                  metric="news_fetch", value=40, threshold=None, flagged=0,
                  payload={"items": 40, "newest_published_ts": T - 9 * 86400})
        n = eventreport.newschain(db.q, T)                                   # a fetch before T only: not current
        self.assertEqual((n["fed_last_fetch_ok"], n["fed_last_fetch_label"]), (T - 300, "ingen hentning efter T"))
        self.assertEqual(n["fed_feed_newest_published"], T - 9 * 86400)
        db.append("observations", ts=T + 1200, detector="news/1", source=eventreport.FED, instrument=None,
                  metric="news_fetch", value=40, threshold=None, flagged=0,
                  payload={"items": 40, "newest_published_ts": T - 9 * 86400})
        n = eventreport.newschain(db.q, T)                                   # fetched after T, still nothing new:
        self.assertEqual((n["fed_last_fetch_label"], n["fed_status"]), ("efter T", "mangler"))   # never "current"

    def test_no_report_before_the_window_closes(self):
        with self.assertRaises(ValueError):
            eventreport.report(self.db.q, lambda url: [], T, now=T + 24 * H)
        rep = eventreport.report(self.db.q, lambda url: klines(), T, now=T + 26 * H)
        self.assertEqual(set(rep["markets"]), set(moves.WATCH))
        self.assertIn("never evidence", rep["label"])
        json.dumps(rep)


if __name__ == "__main__":
    unittest.main()
