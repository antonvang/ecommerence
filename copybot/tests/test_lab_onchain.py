"""Amendment 21q: forward point-in-time on-chain flows - only the last 3 days are asked for, the first value is kept,
a later different value is logged as a revision, at most every 6 hours, and an error stops nothing."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, onchain  # noqa: E402
from lab.db import DB  # noqa: E402

NOW = 1_793_000_000


def feed(v=100.0):
    urls = []

    def get(url):
        urls.append(url)
        return json.dumps({"data": [{"asset": "btc", "time": "2026-10-23T00:00:00.000000000Z", "FlowInExNtv": str(v),
                                     "FlowOutExNtv": "90.5", "SplyExNtv": "2300000"},
                                    {"asset": "eth", "time": "2026-10-23T00:00:00.000000000Z", "FlowInExNtv": "1",
                                     "FlowOutExNtv": "", "SplyExNtv": "17000000"}]}).encode()
    return get, urls


class Collector(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        onchain._STATE["last"] = 0.0

    def test_first_values_revisions_and_pace(self):
        get, urls = feed()
        self.assertEqual(onchain.run(self.db, get, NOW), {"first": 5, "revisions": 0, "rows": 2})
        self.assertIn("start_time=2026-10-23", urls[0])                              # NOW - 3 days, never history
        self.assertIn("skipped", onchain.run(self.db, get, NOW + 3600))               # < 6 h
        get2, _ = feed(v=120.0)
        r = onchain.run(self.db, get2, NOW + 7 * 3600)
        self.assertEqual((r["first"], r["revisions"]), (0, 1))
        rev = json.loads(self.db.one("SELECT payload FROM observations WHERE metric='flow_revision'")["payload"])
        self.assertEqual((rev["old"], rev["new"]), (100.0, 120.0))
        first = json.loads(self.db.one("SELECT payload FROM observations WHERE metric='flow_first' AND "
                                       "instrument='btc:FlowInExNtv'")["payload"])
        self.assertEqual((first["value"], first["usable_from"]), (100.0, NOW))       # the first value is kept

    def test_an_error_is_recorded_and_news_watch_goes_on(self):
        r = onchain.run(self.db, lambda url: (_ for _ in ()).throw(OSError("down")), NOW)
        self.assertIn("down", r["error"])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM observations WHERE metric='onchain_error'")[0], 1)
        from unittest import mock
        with mock.patch("lab.news.run", return_value={"stored": {}, "errors": []}), \
                mock.patch.object(onchain, "run", side_effect=RuntimeError("boom")):
            self.assertIn("boom", fleet.news_pass(self.db)["onchain"]["error"])


if __name__ == "__main__":
    unittest.main()
