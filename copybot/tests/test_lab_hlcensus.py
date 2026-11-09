"""PROTOCOL_V3 amendment 38 A (D10): one Hyperliquid census snapshot per UTC hour from the metaAndAssetCtxs response
premium-watch already fetched (no new call), every universe name kept, null never 0, none after minute 10, a failure
never stops premium-watch, and nothing that decides reads hlcensus/1."""
import json
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lab import census, hlcensus, k3, scanner  # noqa: E402
from lab.db import DB  # noqa: E402

H = 1793044800                                                  # 2026-10-26 20:00 UTC
META = {"universe": [{"name": "BTC"}, {"name": "kPEPE"}, {"name": "OLD", "isDelisted": True}, {"name": ""}]}
CTXS = [{"funding": "0.0000125", "premium": "0.0001", "markPx": "90000", "oraclePx": "89990", "midPx": "90001",
         "openInterest": "1234.5", "dayNtlVlm": "1e9", "prevDayPx": "88000"},
        {"funding": "0.00002", "premium": "", "markPx": "0.012", "oraclePx": "0.012", "midPx": None,
         "openInterest": "0", "dayNtlVlm": "5", "prevDayPx": "0.011"},
        {"funding": None, "markPx": "1"}, {"funding": "1"}]
RES = [META, CTXS]


class HlCensus(unittest.TestCase):
    def setUp(self):
        hlcensus._DONE.clear()
        hlcensus._ERR.clear()
        self.db = DB(":memory:")

    def snaps(self):
        return [dict(r, payload=json.loads(r["payload"])) for r in
                self.db.q("SELECT * FROM observations WHERE detector='hlcensus/1' AND metric='snapshot' ORDER BY id")]

    def test_one_snapshot_per_hour_also_after_a_restart_and_none_after_minute_10(self):
        hlcensus.observe(self.db, H + 61, RES)
        hlcensus.observe(self.db, H + 121, RES)
        hlcensus._DONE.clear()                                  # a restart: the registry is checked
        hlcensus.observe(self.db, H + 181, RES)
        hlcensus.observe(self.db, H + 3600 + 601, RES)          # next hour, after minute 10
        self.assertEqual(len(self.snaps()), 1)
        hlcensus.observe(self.db, H + 7200 + 600, RES)          # minute 10 exactly still counts
        self.assertEqual(len(self.snaps()), 2)

    def test_raw_numbers_every_name_null_never_zero(self):
        hlcensus.observe(self.db, H + 61, RES)
        r = self.snaps()[0]
        p = r["payload"]
        self.assertEqual(p["columns"], ["funding", "premium", "markPx", "oraclePx", "midPx", "openInterest",
                                        "dayNtlVlm", "prevDayPx", "isDelisted"])
        self.assertEqual(sorted(p["rows"]), ["BTC", "OLD", "kPEPE"])      # k-prefixed and delisted kept, "" dropped
        self.assertEqual(p["rows"]["BTC"], [0.0000125, 0.0001, 90000.0, 89990.0, 90001.0, 1234.5, 1e9, 88000.0, 0.0])
        self.assertEqual(p["rows"]["kPEPE"][1], None)                      # "" is null
        self.assertEqual(p["rows"]["kPEPE"][4], None)                      # None is null
        self.assertEqual(p["rows"]["kPEPE"][5], 0.0)                       # a real 0 stays 0
        self.assertEqual(p["rows"]["OLD"], [None, None, 1.0] + [None] * 5 + [1.0])
        self.assertEqual((r["value"], r["flagged"], p["fetched_at"]), (3, 0, H + 61))
        self.assertIn("38 A", p["rule"])

    def test_premium_watch_stores_it_without_a_new_call_and_a_failure_never_stops_it(self):
        def get(url):
            if "exchangeInfo" in url:
                return {"symbols": [{"symbol": "AAAUSDT", "contractType": "PERPETUAL", "underlyingType": "COIN",
                                     "status": "TRADING", "quoteAsset": "USDT"}]}
            if "fundingInfo" in url:
                return []
            return [{"symbol": "AAAUSDT", "markPrice": "2.5", "indexPrice": "2.49", "lastFundingRate": "0.0001",
                     "time": 1000}]
        posts = []

        def post(url, body):
            posts.append(body["type"])
            return RES
        scanner._PERPS.clear()
        census._DONE.clear()
        with mock.patch.object(k3, "observe", return_value={"ok": 1}):
            out = scanner.premium_watch(self.db, get, H + 61, post=post)
            self.assertEqual(out["hlcensus"], {"coins": 3})
            self.assertEqual(posts, ["metaAndAssetCtxs"])                 # one HL call, as before
            with mock.patch.object(hlcensus, "snapshot", side_effect=RuntimeError("boom")):
                out = scanner.premium_watch(self.db, get, H + 3600 + 61, post=post)
            self.assertIn("boom", out["hlcensus"]["error"])
            self.assertGreater(out["observations"], 0)
            self.assertEqual(out["k3"], {"ok": 1})

            def badpost(url, body):
                raise TimeoutError("hl down")
            out = scanner.premium_watch(self.db, get, H + 7200 + 61, post=badpost)
            self.assertIsNone(out["hlcensus"])                            # no response: no snapshot that hour
        self.assertEqual(len(self.snaps()), 1)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM observations WHERE detector='hlcensus/1' "
                                     "AND metric='error'")[0], 1)
        with mock.patch.object(self.db, "append", side_effect=OSError("disk")):
            hlcensus._ERR.clear()
            self.assertIn("disk", hlcensus.guarded(self.db, H + 3 * 3600 + 61, RES)["error"])   # never raised


class Isolation(unittest.TestCase):
    def test_nothing_that_decides_reads_hlcensus(self):
        # the one exception is the descriptive, read-only first look (MISSION27_3 point 12b); 38 A point 2 forbids
        # accounts, rules, thresholds, alarms and HL lanes from reading the rows, and lab/ and pilot/ stay fully banned
        look = os.path.join(HERE, "research", "tools", "hlcensus_look.py")
        with open(look, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("mode=ro", src)
        self.assertNotRegex(src, r"db\.append\(|append\(\"|INSERT|UPDATE|DELETE|\.commit\(")
        for root in ("lab", "research", "pilot"):
            for dirpath, _, files in os.walk(os.path.join(HERE, root)):
                for f in files:
                    if not f.endswith(".py") or f in ("hlcensus.py", "scanner.py") or \
                            os.path.join(dirpath, f) == look:
                        continue
                    with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                        self.assertNotIn("hlcensus", fh.read(), f)
        with open(os.path.join(HERE, "lab", "scanner.py"), encoding="utf-8") as fh:
            self.assertEqual(len(re.findall(r"hlcensus\.guarded\(", fh.read())), 1)
        with open(os.path.join(HERE, "lab", "hlcensus.py"), encoding="utf-8") as fh:
            self.assertEqual(set(re.findall(r'append\("(\w+)"', fh.read())), {"observations"})


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
