"""PROTOCOL_V3 amendment 28: one census snapshot per UTC hour (also with two passes in the hour and after a restart),
none after minute 10, null never 0, a ticker failure keeps the premiumIndex part, a total failure never stops
premium-watch or K3, delivery contracts are left out, and nothing that decides reads census/1."""
import json
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lab import census, k3, scanner  # noqa: E402
from lab.db import DB  # noqa: E402

H = 1793044800                                                  # 2026-10-26 20:00 UTC (a K3 placebo hour)
PREM = [{"symbol": "AAAUSDT", "markPrice": "2.5", "indexPrice": "2.49", "lastFundingRate": "0.0001", "time": 1000},
        {"symbol": "XAUUSDT", "markPrice": "2700", "indexPrice": "2701", "lastFundingRate": "", "time": 3000},
        {"symbol": "BTCUSDT_261225", "markPrice": "90000", "indexPrice": "89000", "time": 2000}]
TICK = [{"symbol": "AAAUSDT", "lastPrice": "2.5", "openPrice": "2.0", "highPrice": "2.6", "lowPrice": "1.9",
         "quoteVolume": "12345.5", "count": 77, "closeTime": 5000},
        {"symbol": "NEWUSDT", "lastPrice": "1", "openPrice": "1", "highPrice": "1", "lowPrice": "1",
         "quoteVolume": "0", "count": 0, "closeTime": 7000}]


class Census(unittest.TestCase):
    def setUp(self):
        census._DONE.clear()
        census._ERR.clear()
        self.db = DB(":memory:")
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        return TICK

    def snaps(self):
        return [dict(r, payload=json.loads(r["payload"])) for r in
                self.db.q("SELECT * FROM observations WHERE detector='census/1' AND metric='snapshot' ORDER BY id")]

    def test_one_snapshot_per_hour_also_after_a_restart_and_none_after_minute_10(self):
        census.observe(self.db, H + 61, PREM, self.get, clock=lambda: H + 62.5)
        census.observe(self.db, H + 121, PREM, self.get)
        census._DONE.clear()                                    # a restart: the registry is checked
        census.observe(self.db, H + 181, PREM, self.get)
        census.observe(self.db, H + 3600 + 601, PREM, self.get)  # the next hour, after minute 10
        self.assertEqual(len(self.snaps()), 1)
        self.assertEqual(self.calls, ["https://fapi.binance.com/fapi/v1/ticker/24hr"])
        census.observe(self.db, 2 * 3600 + H + 600, PREM, self.get)   # minute 10 exactly still counts
        self.assertEqual(len(self.snaps()), 2)

    def test_raw_numbers_null_never_zero_and_no_delivery_contracts(self):
        census.observe(self.db, H + 61, PREM, self.get, clock=lambda: H + 62.5)
        r = self.snaps()[0]
        p = r["payload"]
        self.assertEqual(p["columns"], ["markPrice", "indexPrice", "lastFundingRate", "lastPrice", "openPrice",
                                        "highPrice", "lowPrice", "quoteVolume", "count"])
        self.assertEqual(sorted(p["rows"]), ["AAAUSDT", "NEWUSDT", "XAUUSDT"])
        self.assertEqual(p["rows"]["AAAUSDT"], [2.5, 2.49, 0.0001, 2.5, 2.0, 2.6, 1.9, 12345.5, 77.0])
        self.assertEqual(p["rows"]["XAUUSDT"], [2700.0, 2701.0, None, None, None, None, None, None, None])
        self.assertEqual(p["rows"]["NEWUSDT"][:3], [None, None, None])
        self.assertEqual(p["rows"]["NEWUSDT"][7:], [0.0, 0.0])              # a real 0 from Binance stays 0
        self.assertEqual((r["value"], p["premium_time_ms"], p["ticker_close_ms"]), (3, 2000, 6000))
        self.assertEqual((p["premium_fetched_at"], p["ticker_fetched_at"], p["ticker_error"]), (H + 61, H + 62.5, None))
        self.assertEqual(r["flagged"], 0)
        self.assertEqual(p["coin_perps"], [])                              # no exchangeInfo set given

    def test_28a_coin_perps_are_the_snapshot_members_premium_watch_marks_as_coin(self):
        census.observe(self.db, H + 61, PREM, self.get, perps={"AAAUSDT", "GONEUSDT"})
        self.assertEqual(self.snaps()[0]["payload"]["coin_perps"], ["AAAUSDT"])    # XAU is TradFi; GONE not in it

    def test_a_ticker_failure_keeps_the_premium_part(self):
        def bad(url):
            raise TimeoutError("read timed out")
        census.observe(self.db, H + 61, PREM, bad)
        p = self.snaps()[0]["payload"]
        self.assertIn("TimeoutError", p["ticker_error"])
        self.assertEqual(p["rows"]["AAAUSDT"][:3], [2.5, 2.49, 0.0001])
        self.assertEqual(p["rows"]["AAAUSDT"][3:], [None] * 6)

    def test_a_total_failure_never_stops_premium_watch_or_k3(self):
        def get(url):
            if "exchangeInfo" in url:
                return {"symbols": [{"symbol": "AAAUSDT", "contractType": "PERPETUAL", "underlyingType": "COIN",
                                     "status": "TRADING", "quoteAsset": "USDT"}]}
            if "fundingInfo" in url:
                return []
            return PREM
        scanner._PERPS.clear()
        with mock.patch.object(census, "snapshot", side_effect=RuntimeError("boom")), \
                mock.patch.object(k3, "observe", return_value={"ok": 1}) as k3obs:
            out = scanner.premium_watch(self.db, get, H + 61, post=lambda u, b: [{"universe": []}, []])
            scanner.premium_watch(self.db, get, H + 121, post=lambda u, b: [{"universe": []}, []])
        self.assertIn("boom", out["census"]["error"])
        with mock.patch.object(census, "observe", return_value=None) as obs:
            scanner.premium_watch(self.db, get, H + 3600 + 61, post=lambda u, b: [{"universe": []}, []])
        self.assertEqual(obs.call_args[0][4], {"AAAUSDT"})                  # premium-watch's COIN set is passed
        self.assertEqual(out["k3"], {"ok": 1})
        self.assertEqual(k3obs.call_count, 2)
        self.assertGreater(out["observations"], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM observations WHERE detector='census/1' "
                                     "AND metric='error'")[0], 1)          # at most once an hour
        with mock.patch.object(self.db, "append", side_effect=OSError("disk")):
            census._ERR.clear()
            self.assertIn("disk", census.guarded(self.db, H + 3600 + 61, PREM, get)["error"])   # never raised


class Isolation(unittest.TestCase):
    def test_nothing_that_decides_reads_the_census(self):
        for f in ("lab/paper.py", "lab/paper_runner.py", "lab/lane.py", "lab/capacity.py", "lab/costreport.py",
                  "lab/costrule.py", "lab/k3.py", "lab/moves.py", "lab/promotion.py", "lab/r3.py", "research/pm_lp.py"):
            path = os.path.join(HERE, f)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    self.assertNotIn("census", fh.read(), f)
        with open(os.path.join(HERE, "lab", "scanner.py"), encoding="utf-8") as fh:
            self.assertEqual(len(re.findall(r"census\.guarded\(", fh.read())), 1)   # one call site in premium-watch
        with open(os.path.join(HERE, "lab", "census.py"), encoding="utf-8") as fh:
            self.assertEqual(set(re.findall(r'append\("(\w+)"', fh.read())), {"observations"})


if __name__ == "__main__":
    unittest.main()
