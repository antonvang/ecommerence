"""PROTOCOL_V3 amendment 27: the diagnostic 500-level measurement after a 12g thin-book rejection - full and
insufficient depth, missing data, HTTP 429/418 without retry, duplicates, errors never block the scanner, the decision
is byte for byte unchanged, nothing that decides reads depth500/1, and only observations rows are written."""
import json
import os
import re
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import depth500, lane  # noqa: E402
import tests.test_lab_lane as tl  # noqa: E402

NOW, Base, hi = tl.NOW, tl.Base, tl.hi

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPOT, PERP = "BBBUSDT.SPOT", "BBBUSDT"


def book(n, px=100.0, size=1.0, step=0.01):
    """n levels a side around px, `size` coins each."""
    return {"lastUpdateId": 42, "E": 1, "T": 2,
            "bids": [[str(px - step * (i + 1)), str(size)] for i in range(n)],
            "asks": [[str(px + step * (i + 1)), str(size)] for i in range(n)]}


def trigger(qty=30.0):
    return {"execution": {"qty": qty, "size_usd_per_leg": qty * 100.0,
                          "spot": {"instrument": SPOT, "fetched_at": 1000.0},
                          "perp": {"instrument": PERP, "fetched_at": 1000.5}}}


class Probe(Base):
    def rows(self, metric=None):
        sql = "SELECT * FROM observations WHERE detector=?" + (" AND metric=?" if metric else "") + " ORDER BY id"
        return [dict(r, payload=json.loads(r["payload"])) for r in
                self.db.q(sql, *((depth500.DET, metric) if metric else (depth500.DET,)))]

    def test_full_depth_measures_both_windows_and_censors_only_the_thin_one(self):
        calls = []
        get = lambda u: calls.append(u) or book(500)                         # noqa: E731 - 500 coins a side
        depth500.probe(self.db, 7, "scan|BBBUSDT|1", trigger(qty=30.0), get, clock=lambda: 1003.0)
        self.assertEqual(len(calls), 2)                                     # one read per leg, 500 levels
        self.assertTrue(all("limit=500" in u for u in calls))
        self.assertTrue(calls[0].startswith("https://data-api.binance.vision/api/v3/depth?symbol=BBBUSDT&"))
        self.assertTrue(calls[1].startswith("/fapi/v1/depth?symbol=BBBUSDT&"))
        r = self.rows("thin_probe")
        self.assertEqual(len(r), 2)
        p = r[0]["payload"]
        self.assertEqual((p["event_id"], p["event_key"], p["rule"], p["qty"]), (7, "scan|BBBUSDT|1", "12g", 30.0))
        self.assertEqual(p["censored_20"], {"buy": True, "sell": True})      # 20 coins cannot fill 30
        self.assertEqual(p["censored_500"], {"buy": False, "sell": False})
        self.assertIsNone(p["buy_vwap_distance_20"])
        self.assertAlmostEqual(p["buy_vwap_distance_500"], (sum(100 + 0.01 * (i + 1) for i in range(30)) / 30) / 100 - 1)
        self.assertAlmostEqual(r[0]["value"], p["buy_vwap_distance_500"] + p["sell_vwap_distance_500"])
        self.assertEqual((p["lastUpdateId"], p["fetched_at"], p["age_vs_decision_book_s"]), (42, 1003.0, 3.0))
        self.assertEqual(p["levels"], [500, 500])
        self.assertIn("ikke en fill", p["label"])

    def test_insufficient_depth_is_null_and_censored_never_zero(self):
        depth500.probe(self.db, 8, "scan|BBBUSDT|2", trigger(qty=30.0), lambda u: book(10), clock=lambda: 1.0)
        for r in self.rows("thin_probe"):
            self.assertIsNone(r["value"])
            self.assertEqual(r["payload"]["censored_500"], {"buy": True, "sell": True})
            self.assertIsNone(r["payload"]["sell_vwap_distance_500"])
            self.assertNotIn(0, [r["payload"][k] for k in ("buy_vwap_distance_500", "sell_vwap_distance_500")])

    def test_missing_data_429_and_418_are_one_error_row_each_and_never_retried(self):
        for code, key in ((429, "k1"), (418, "k2")):
            calls = []

            def get(u, code=code):
                calls.append(u)
                raise urllib.error.HTTPError(u, code, "limit", None, None)
            depth500.probe(self.db, code, key, trigger(), get, clock=lambda: 1.0)
            self.assertEqual(len(calls), 2)                                  # one try per leg, no retry
        empty = lambda u: {"bids": [], "asks": []}                           # noqa: E731
        depth500.probe(self.db, 3, "k3", trigger(), empty, clock=lambda: 1.0)
        errs = self.rows("error")
        self.assertEqual([e["payload"]["http_status"] for e in errs], [429, 429, 418, 418, None, None])
        self.assertIn("empty or crossed", errs[-1]["payload"]["error"])
        self.assertEqual(self.rows("thin_probe"), [])

    def test_duplicates_are_measured_once(self):
        get = mock.Mock(side_effect=lambda u: book(500))
        depth500.probe(self.db, 9, "scan|BBBUSDT|3", trigger(), get, clock=lambda: 1.0)
        depth500.probe(self.db, 9, "scan|BBBUSDT|3", trigger(), get, clock=lambda: 2.0)    # a restart
        depth500.probe(self.db, 10, "scan|BBBUSDT|3", trigger(), get, clock=lambda: 3.0)   # same key and legs
        self.assertEqual(get.call_count, 2)
        self.assertEqual(len(self.rows()), 2)

    def test_no_execution_record_writes_nothing(self):
        get = mock.Mock(side_effect=AssertionError("no read"))
        self.assertEqual(depth500.probe(self.db, 1, "k", {}, get), [])
        self.assertEqual(depth500.probe(self.db, 1, "k", {"execution": {"qty": 1}}, get), [])


class Scanner12g(Base):
    """The probe inside manage_scanner: the decision is unchanged and errors never block."""
    def setUp(self):
        super().setUp()
        from lab import scanner
        scanner.LIVE.clear()

    def scan(self, ts, fund):
        tl.Scanner.scan(self, ts, fund)

    @staticmethod
    def thin(log=None):
        def get(path):
            if log is not None:
                log.append(path)
            g = hi()
            g.now = NOW
            if "depth" in path:
                return {"bids": [["99.99", "1"]], "asks": [["100.01", "1"]]}       # 100 USD a side: 12g too thin
            return g(path)
        get.now = NOW
        return get

    def skipped(self):
        return [r for r in self.db.q("SELECT kind, exp_id, payload FROM events WHERE kind IN ('lane.skipped', "
                                     "'lane.started') ORDER BY id")]

    def test_the_decision_is_byte_for_byte_the_same_with_and_without_the_probe(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        log = []
        with mock.patch.object(lane, "_wall", lambda: 1000.0):                # 12h's wall clock, fixed in both runs
            out = lane.manage(self.db, NOW, self.thin(log), fids=[])["scanner"]
        with_probe = [tuple(r) for r in self.skipped()]
        probes = self.db.q("SELECT metric, instrument FROM observations WHERE detector='depth500/1'")
        self.assertEqual(out["skipped"], ["BBBUSDT"])
        self.assertEqual(out["started"], [])
        self.assertEqual(len(with_probe), 1)
        self.assertIn("too thin for the account", with_probe[0][2])
        self.assertEqual(sorted((m, i) for m, i in probes), [("thin_probe", "BBBUSDT"), ("thin_probe", "BBBUSDT.SPOT")])
        self.assertEqual(sum("limit=500" in u for u in log), 2)
        # the same pass with the probe switched off writes the identical decision
        tmp_db = self.db.__class__(os.path.join(self.tmp, "other.db"))
        try:
            tl.Scanner.scan(type("S", (), {"db": tmp_db})(), NOW - 60, {"BBBUSDT": 0.003})
            with mock.patch.object(lane, "_depth500", lambda *a, **k: None), \
                    mock.patch.object(lane, "_wall", lambda: 1000.0):
                lane.manage(tmp_db, NOW, self.thin(), fids=[])
            without = [tuple(r) for r in tmp_db.q("SELECT kind, exp_id, payload FROM events WHERE kind IN "
                                                  "('lane.skipped', 'lane.started') ORDER BY id")]
            self.assertEqual(without, with_probe)
            self.assertEqual(tmp_db.one("SELECT COUNT(*) FROM observations WHERE detector='depth500/1'")[0], 0)
        finally:
            tmp_db.close()

    def test_an_error_in_the_probe_never_blocks_the_scanner(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003, "CCCUSDT": 0.003})
        with mock.patch.object(depth500, "probe", side_effect=RuntimeError("boom")):
            out = lane.manage(self.db, NOW, self.thin(), fids=[])["scanner"]
        self.assertEqual(sorted(out["skipped"]), ["BBBUSDT", "CCCUSDT"])      # the pass went on to the next coin
        errs = self.db.q("SELECT payload FROM observations WHERE detector='depth500/1' AND metric='error'")
        self.assertEqual(len(errs), 1)                                          # at most once an hour
        self.assertIn("boom", errs[0]["payload"])

    def test_other_rejections_never_trigger_a_probe(self):
        wide = tl.market(rate=0.0008, spread=1.0)
        self.scan(NOW - 60, {"BBBUSDT": 0.0006})                               # 12g: funding does not cover
        log = []

        def get(path):
            log.append(path)
            return wide(path)
        get.now = NOW
        wide.now = NOW
        lane.manage(self.db, NOW, get, fids=[])
        self.assertIn("do not cover the round-trip cost", self.skipped()[-1]["payload"])
        self.assertFalse(any("limit=500" in u for u in log))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM observations WHERE detector='depth500/1'")[0], 0)
        for reason in ("intet spotpar på Binance (19)", "ValueError('funding not persistent: x')",
                       "ValueError('likviditetsgate (25): VELO.SPOT: bogen er for tynd til 5000 USD')"):
            self.assertFalse(depth500.wanted(reason))
        self.assertTrue(depth500.wanted("ValueError(\"a book is too thin for the account's size (12g)\")"))


class Isolation(unittest.TestCase):
    def test_nothing_that_decides_or_prices_reads_depth500(self):
        for f in ("lab/paper.py", "lab/paper_runner.py", "lab/capacity.py", "lab/costreport.py", "lab/costrule.py",
                  "lab/k3.py", "lab/moves.py", "lab/scanner.py", "research/pm_lp.py"):
            with open(os.path.join(HERE, f), encoding="utf-8") as fh:
                self.assertNotIn("depth500", fh.read(), f)
        with open(os.path.join(HERE, "lab", "lane.py"), encoding="utf-8") as fh:
            src = fh.read()
        for fn in ("def _cost_gate", "def liquidity_gate", "def round_trip_cost", "def walk"):
            body = src.split(fn, 1)[1].split("\ndef ", 1)[0]
            self.assertNotIn("depth500", body, fn)
        self.assertEqual(len(re.findall(r"_depth500\(db, eid", src)), 1)        # one call site, after the event

    def test_the_probe_writes_only_observations(self):
        with open(os.path.join(HERE, "lab", "depth500.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertEqual(set(re.findall(r'append\("(\w+)"', src)), {"observations"})
        self.assertNotIn("sim_", src)


if __name__ == "__main__":
    unittest.main()
