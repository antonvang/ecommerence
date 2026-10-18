"""Paper engine conformance (research/PROTOCOL_V3.md amendment 4 section 7) and network economy: a paused ledger keeps
and marks its positions every hour, orders walk a book read just before the order, and hourly data is fetched once
per hour for all ledgers."""
import collections
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import lifecycle, paper_runner, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.lab_fixtures import approve_paper, frozen  # noqa: E402
from tests import test_lab_paper_runner as tpr  # noqa: E402
from tests.test_lab_paper_runner import EID, HOUR, SAT, feed  # noqa: E402


def counted(get):
    n = collections.Counter()

    def g(path):
        n[next(k for k in ("klines", "fundingRate", "depth", "coinmetrics") if k in path)] += 1
        return get(path)
    return g, n


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labconf")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True)]
        for p in self.p:
            p.start()
        self.db.append("experiments", exp_id=EID, version=1, created_ts=0, mechanism_tag="calendar_day_of_week",
                       fingerprint="f", spec_json={"template": "day_of_week", "execution": "taker"})
        approve_paper(self.db, EID)
        frozen(self.db, EID, "cost", {"selected": 1})
        frozen(self.db, EID, "backtest", {"variants": [
            {"variant": 0, "params": {"mode": "flat_weekend"}, "fit": None, "positions": {}},
            {"variant": 1, "params": {"mode": "weekend_only"}, "fit": None, "positions": {}}]})

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def n(self, table):
        return self.db.one(f"SELECT COUNT(*) FROM {table}")[0]


class Pause(Base):
    def test_a_paused_strategy_keeps_its_positions_and_is_marked_every_hour(self):
        paper_runner.run(self.db, feed(SAT), SAT)                                 # weekend: long all 8
        held = PaperEngine(self.db).ledger(EID)["positions"]
        self.assertEqual(len(held), len(data.UNIVERSE))
        Risk(self.db, lambda: SAT).pause(EID, "consecutive_losses", 2, 2, "test pause")
        self.assertEqual(lifecycle.state(self.db, EID), "PAUSED")
        orders, marks = self.n("sim_orders"), self.n("sim_equity")
        for t, marked in ((SAT + HOUR, True), (SAT + HOUR + 60, False), (SAT + 2 * HOUR, True)):
            r = paper_runner.run(self.db, feed(t), t)["results"][EID]
            self.assertEqual((r["status"], r["marked"]), ("paused", marked), t)
        self.assertEqual(self.n("sim_orders"), orders)                            # nothing new opened
        self.assertEqual(self.n("sim_equity"), marks + 2)                         # one mark per hour
        self.assertEqual(PaperEngine(self.db).ledger(EID)["positions"], held)     # kept, not dropped

    def test_a_paused_shadow_ledger_is_marked_too(self):
        s = tpr.Shadow("test_needs_a_human_start_while_in_observation")
        s.setUp()
        try:
            led = "SHADOW_" + s.EID
            s.db.event("shadow.approved", "human:test", s.EID, {"reason": "user asked for shadow trading"})
            paper_runner.run(s.db, feed(SAT), SAT, cm_get=s.cm)
            Risk(s.db, lambda: SAT).pause(led, "consecutive_losses", 2, 2, "test pause")
            orders = s.db.one("SELECT COUNT(*) FROM sim_orders")[0]
            r = paper_runner.run(s.db, feed(SAT + HOUR), SAT + HOUR, cm_get=s.cm)["results"][led]
            self.assertEqual((r["status"], r["marked"]), ("paused", True))
            self.assertEqual(s.db.one("SELECT COUNT(*) FROM sim_orders")[0], orders)
            self.assertEqual(s.db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", led)[0], int(SAT + HOUR))
        finally:
            s.tearDown()


class FreshBook(Base):
    def test_each_order_walks_a_book_read_just_before_it(self):
        g, n = counted(feed(SAT))
        paper_runner.run(self.db, g, SAT)
        self.assertEqual(n["depth"], 2 * len(data.UNIVERSE))                      # one for marks, one per order

    def test_an_unreadable_book_skips_the_order_without_a_pause_and_the_next_pass_sends_it(self):
        base, seen = feed(SAT), collections.Counter()

        def flaky(path):
            if "depth" in path:
                seen[path] += 1
                if seen[path] == 2:                                                # the order-time read fails
                    raise IOError("book timeout")
            return base(path)
        r = paper_runner.run(self.db, flaky, SAT)["results"][EID]
        self.assertEqual(r["status"], "ok")
        self.assertTrue(all(o["status"].startswith("not sent") for o in r["orders"]))
        self.assertFalse(Risk(self.db).paused(EID))
        self.assertEqual(self.n("sim_orders"), 0)
        r = paper_runner.run(self.db, feed(SAT), SAT + 60)["results"][EID]       # same hour: same order ids
        self.assertTrue(all(o["status"] == "filled" for o in r["orders"]))


class HourlyData(Base):
    def test_bars_and_funding_are_fetched_once_per_hour_and_the_book_every_pass(self):
        cache = {}
        g, n = counted(feed(SAT))
        paper_runner.run(self.db, g, SAT, cache=cache)
        self.assertEqual((n["klines"], n["fundingRate"]), (len(data.UNIVERSE),) * 2)
        paper_runner.run(self.db, g, SAT + 60, cache=cache)                      # same hour: book only
        self.assertEqual((n["klines"], n["fundingRate"]), (len(data.UNIVERSE),) * 2)
        self.assertEqual(n["depth"], 3 * len(data.UNIVERSE))                      # 2 on the first pass, 1 now
        g2, n2 = counted(feed(SAT + HOUR))
        paper_runner.run(self.db, g2, SAT + HOUR, cache=cache)                   # a new bar closed: fetched again
        self.assertEqual(n2["klines"], len(data.UNIVERSE))

    def test_bars_without_the_latest_close_are_not_cached(self):
        cache = {}
        g, n = counted(feed(SAT - HOUR))                                           # the 10:00 bar is not out yet
        paper_runner.run(self.db, g, SAT, cache=cache)
        paper_runner.run(self.db, g, SAT + 60, cache=cache)
        self.assertEqual(n["klines"], 2 * len(data.UNIVERSE))                     # asked again next pass
        self.assertEqual(cache, {})

    def test_coinmetrics_is_read_once_per_hour(self):
        s = tpr.Shadow("test_needs_a_human_start_while_in_observation")
        s.setUp()
        try:
            s.db.event("shadow.approved", "human:test", s.EID, {"reason": "user asked for shadow trading"})
            calls = []
            cm = lambda url: calls.append(url) or s.cm(url)                       # noqa: E731
            cm_cache = {}
            for t in (SAT, SAT + 60, SAT + 120):
                paper_runner.run(s.db, feed(SAT), t, cm_get=cm, cm_cache=cm_cache)
            self.assertEqual(len(calls), 1)
            paper_runner.run(s.db, feed(SAT + HOUR), SAT + HOUR, cm_get=cm, cm_cache=cm_cache)
            self.assertEqual(len(calls), 2)
        finally:
            s.tearDown()


if __name__ == "__main__":
    unittest.main()
