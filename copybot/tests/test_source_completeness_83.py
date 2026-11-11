"""Director order 83 point 3: source completeness for STRAKS (12 perps) and PAR-BOG (8 perps). research/tools/
source_completeness.py is a dev design; the pinned lab/straks.py and lab/pairs.py are not changed. Missing data gives
DATA_INCOMPLETE and no recovery. Synthetic data, temporary databases, no network, no DNS, no lab.db."""
import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from lab import moves, pairs, paper_runner as real  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.risk import Risk  # noqa: E402
from research.tools import source_completeness as sc  # noqa: E402
from tests.test_lab_engine_remediation_67 import apply_unified, load  # noqa: E402
from tests.test_partial_close_78 import NOW, market, no_network  # noqa: E402

HOUR = 3600
FROZEN = {"straks.py": "7a110f1fa20fb7d28b76269fc039eec4c75ddfa7353602f2f8824490b722a542",
          "pairs.py": "5c9b60a4314a40a5e4d517427c4960220682b8f6179a445a5554903180ce1219"}
LED = "LANE_synthetic_book"


def fresh(book, now):
    return {s: {"bar_ts": now - 2 * HOUR, "book_ok": True} for s in sc.REQUIRED[book]}


class Required(unittest.TestCase):
    def test_the_markets_each_book_trades(self):
        self.assertEqual(sc.REQUIRED["straks"], tuple(sorted(moves.WATCH)))
        self.assertEqual(len(sc.REQUIRED["straks"]), 12)
        self.assertEqual(sc.REQUIRED["pairs"], tuple(sorted({s for p in pairs.PAIRS for s in p})))
        self.assertEqual(len(sc.REQUIRED["pairs"]), 8)

    def test_the_pinned_modules_are_unchanged(self):
        for f, h in FROZEN.items():
            with open(os.path.join(HERE, "lab", f), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), h, f)


class Assess(unittest.TestCase):
    T = 1_800_000_000

    def test_complete(self):
        self.assertEqual(sc.assess("pairs", fresh("pairs", self.T), self.T)["status"], sc.DATA_COMPLETE)
        self.assertEqual(sc.assess("straks", fresh("straks", self.T), self.T, signal_ts=self.T - 60)["status"],
                         sc.DATA_COMPLETE)

    def test_one_missing_market_is_incomplete_whatever_btc_says(self):
        obs = fresh("pairs", self.T)
        del obs["XAUUSDT"]
        a = sc.assess("pairs", obs, self.T)
        self.assertEqual(a["status"], sc.DATA_INCOMPLETE)
        self.assertEqual(a["missing"], ["XAUUSDT"])
        self.assertTrue(obs["BTCUSDT"]["book_ok"])

    def test_stale_bar_and_bad_book(self):
        obs = fresh("straks", self.T)
        obs["CLUSDT"]["bar_ts"] = self.T - 4 * HOUR
        obs["SPYUSDT"]["book_ok"] = False
        a = sc.assess("straks", obs, self.T, signal_ts=self.T)
        self.assertEqual((a["status"], a["stale_bars"], a["invalid_books"]), (sc.DATA_INCOMPLETE, ["CLUSDT"], ["SPYUSDT"]))

    def test_bar_age_boundary(self):
        obs = fresh("pairs", self.T)
        obs["BZUSDT"]["bar_ts"] = self.T - HOUR - sc.MAX_BAR_AGE_S
        self.assertEqual(sc.assess("pairs", obs, self.T)["status"], sc.DATA_COMPLETE)
        obs["BZUSDT"]["bar_ts"] -= 1
        self.assertEqual(sc.assess("pairs", obs, self.T)["status"], sc.DATA_INCOMPLETE)

    def test_straks_needs_its_signal_source(self):
        for sig in (None, self.T - sc.SIGNAL_MAX_AGE_S - 1):
            a = sc.assess("straks", fresh("straks", self.T), self.T, signal_ts=sig)
            self.assertEqual(a["stale_sources"], ["abnormal_move/1"])
        self.assertEqual(sc.assess("pairs", fresh("pairs", self.T), self.T)["stale_sources"], [])

    def test_unknown_book_and_malformed_input(self):
        with self.assertRaises(ValueError):
            sc.assess("carry90", {}, self.T)
        obs = fresh("pairs", self.T)
        obs["ETHUSDT"] = {"bar_ts": True, "book_ok": 1}
        a = sc.assess("pairs", obs, self.T)
        self.assertEqual((a["stale_bars"], a["invalid_books"]), (["ETHUSDT"], ["ETHUSDT"]))


class Recovery(unittest.TestCase):
    def test_needs_an_unbroken_complete_run(self):
        C, I = sc.DATA_COMPLETE, sc.DATA_INCOMPLETE
        self.assertEqual(sc.recovery([], 10_000), sc.NO_RECOVERY)
        self.assertEqual(sc.recovery([(0, C), (3000, C)], 3000), sc.RECOVERY_ALLOWED)
        self.assertEqual(sc.recovery([(0, C), (2999, C)], 2999), sc.NO_RECOVERY)
        self.assertEqual(sc.recovery([(0, C), (1000, I), (2000, C), (4000, C)], 4000), sc.NO_RECOVERY)
        self.assertEqual(sc.recovery([(0, C), (3500, I)], 3500), sc.NO_RECOVERY)


class WithRisk(unittest.TestCase):
    """The probes in the order-81 multi-source Risk.auto_resume (candidate 1, temporary copy)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(HERE, "research", "desk", "patches", "83_candidate_1_observability.diff"),
                  encoding="utf-8") as f:
            files = apply_unified(f.read(), os.path.dirname(HERE), tmp.name)
        self.rk = load("lab._risk_c83", files["copybot/lab/risk.py"], package="lab")
        self.db = DB(os.path.join(tmp.name, "db", "lab.db"))
        self.addCleanup(self.db.close)
        for p in (mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)):
            p.start()
            self.addCleanup(p.stop)
        self.t = NOW
        self.base = market()
        self.old = set()

        def get(path):
            if "klines" in path and any(f"symbol={s}&" in path for s in self.old):
                self.base.now = self.t - 10 * HOUR                   # this market's bars stopped 10 h ago
                try:
                    return self.base(path)
                finally:
                    self.base.now = self.t
            return self.base(path)
        self.get = get

    def resume(self, book, signal_age=60, minutes=120, risk_cls=None):
        risk = (risk_cls or self.rk.Risk)(self.db, now=lambda: self.t)
        risk.pause(LED, "data_fetch", None, None, "synthetic")
        for m in range(0, minutes + 1, 10):
            self.t = NOW + m * 60
            self.base.now = self.t
            real._HOURLY.clear()
            if risk.auto_resume(LED, sc.probes(book, self.t, self.get, signal_ts=self.t - signal_age)):
                return True
        return False

    def last_probe(self):
        return self.db.one("SELECT value, detail FROM risk_events WHERE exp_id=? AND action='PROBE' ORDER BY id DESC "
                           "LIMIT 1", LED)

    def test_all_markets_fresh_recovers(self):
        self.assertTrue(self.resume("pairs"))

    def test_one_stale_market_gives_data_incomplete_and_no_recovery(self):
        self.old = {"XAUUSDT"}
        self.assertFalse(self.resume("pairs", minutes=180))
        p = self.last_probe()
        self.assertEqual(p["value"], 0)
        self.assertIn("DATA_INCOMPLETE", p["detail"])
        self.assertIn("XAUUSDT", p["detail"])

    def test_straks_with_a_stale_signal_source_does_not_recover(self):
        self.assertFalse(self.resume("straks", signal_age=3 * HOUR, minutes=180))
        self.assertIn("abnormal_move/1", self.last_probe()["detail"])

    def test_the_frozen_one_book_probe_would_recover_the_same_case(self):
        self.old = {"XAUUSDT"}
        risk = Risk(self.db, now=lambda: self.t)
        risk.pause(LED, "data_fetch", None, None, "synthetic")
        resumed = False
        for m in range(0, 121, 10):
            self.t = NOW + m * 60
            self.base.now = self.t
            if risk.auto_resume(LED, lambda: real.fetch_book("BTCUSDT", self.t, self.get)):
                resumed = True
                break
        self.assertTrue(resumed)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
