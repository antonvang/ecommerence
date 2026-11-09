"""Director order 72 P2/P3: the two unapplied patches, applied strictly to temporary copies. Synthetic data, mocked http.
research/pm_lp.py, lab/ops.py and lab/fleet.py are not changed by this test or by the patches until separately approved.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from lab.db import DB  # noqa: E402
from lab.mission import EXTERNAL_RUNNING_S  # noqa: E402
from research import pm_lp as original  # noqa: E402
from tests.test_lab_engine_remediation_67 import apply_unified, load  # noqa: E402

PATCHES = os.path.join(HERE, "research", "desk", "patches")
REFUSED = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
REWARDS = {"data": [{"condition_id": "c1", "total_daily_rate": 50.0, "rewards_max_spread": 3, "rewards_min_size": 10}],
           "next_cursor": None}


class Stop(Exception):
    pass


def stop_after(n):
    calls = []

    def sleep(_):
        calls.append(1)
        if len(calls) >= n:
            raise Stop
    return sleep


def apply(name, tmp):
    with open(os.path.join(PATCHES, name), encoding="utf-8") as f:
        return apply_unified(f.read(), os.path.dirname(HERE), tmp)


class Clock:
    """time.time advancing one minute per call-free tick, driven by the patched sleep."""

    def __init__(self, start):
        self.now = start

    def time(self):
        return self.now


class Startup(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        files = apply("72_pm_lp_startup.diff", tmp.name)
        self.pm = load("pm_lp_patched72", files["copybot/research/pm_lp.py"])
        self.db = self.pm.open_db(os.path.join(tmp.name, "pm.db"))
        self.addCleanup(self.db.close)
        self.logged, self.urls = [], []
        self.d0 = self.pm.day_of(self.pm.time.time())

    def run_with(self, http, ticks):
        c = self.pm.Collector(self.db, log=self.logged.append)
        clock = Clock(self.pm.time.time())
        n = {"left": ticks}

        def sleep(_):
            n["left"] -= 1
            clock.now += 61
            if n["left"] <= 0:
                raise Stop

        def tracked(url, body=None, tries=5):
            self.urls.append(url)
            return http(url, body, tries)

        fake = mock.Mock(wraps=self.pm.time)
        fake.time, fake.sleep = clock.time, sleep
        with mock.patch.object(self.pm, "http", tracked), mock.patch.object(self.pm, "time", fake):
            with self.assertRaises(Stop):
                c.run(self.d0)
        return c

    def test_original_still_dies_at_startup(self):
        """The regression this patch is for. The real file is unchanged."""
        c = original.Collector(self.db, log=self.logged.append)
        with mock.patch.object(original, "http", side_effect=REFUSED):
            with self.assertRaises(urllib.error.URLError):
                c.run(self.d0)

    def test_failure_at_startup_stays_up_and_is_visible(self):
        def http(url, body, tries):
            raise REFUSED
        self.run_with(http, 3)
        self.assertEqual(sum("belønningsdata" in str(x) for x in self.logged), 3, self.logged)

    def test_nothing_is_invented_during_the_outage(self):
        def http(url, body, tries):
            raise REFUSED
        self.run_with(http, 3)
        for table in ("snaps", "polls", "panel", "rewards"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

    def test_no_empty_panel_is_formed_and_the_day_is_not_lost(self):
        """Without rewards data the panel waits; once the data is back the same day's panel is selected."""
        state = {"up": False}

        def http(url, body, tries):
            if not state["up"]:
                raise REFUSED
            if "rewards" in url:
                return REWARDS
            return {}
        calls = []
        real = self.pm.Collector.refresh_panel

        def spy(me, i, d):
            calls.append(bool(me.cfg))
            return real(me, i, d)

        with mock.patch.object(self.pm.Collector, "refresh_panel", spy):
            self.run_with(http, 2)
            self.assertEqual(calls, [])
            state["up"] = True
            self.run_with(http, 2)
        self.assertEqual(calls[:1], [True])

    def test_only_the_existing_endpoints_are_used(self):
        def http(url, body, tries):
            raise REFUSED
        self.run_with(http, 3)
        self.assertTrue(self.urls)
        for u in self.urls:
            self.assertTrue(u.startswith((original.CLOB, original.GAMMA)), u)

    def test_retry_is_hourly_again_once_data_is_there(self):
        def http(url, body, tries):
            if "rewards" in url:
                return REWARDS
            return {}
        with mock.patch.object(self.pm.Collector, "refresh_panel", lambda *a: None):
            self.run_with(http, 5)
        self.assertEqual(sum("rewards" in u for u in self.urls), 1)


class ExternalWatch(unittest.TestCase):
    EID = "X01_pm_lp_v1"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        files = apply("72_external_watch_data_activity.diff", tmp.name)
        self.ops = load("lab._ops72", files["copybot/lab/ops.py"], package="lab")
        self.fleet = load("lab._fleet72", files["copybot/lab/fleet.py"], package="lab")
        self.db = DB(os.path.join(tmp.name, "lab.db"))
        self.addCleanup(self.db.close)

    def pm_db(self, polls=(), status=()):
        p = os.path.join(self.tmp, "pm.db")
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE IF NOT EXISTS polls(t INTEGER, kind TEXT, cid TEXT, ok INTEGER)")
        con.execute("CREATE TABLE IF NOT EXISTS status(t INTEGER, cid TEXT, closed INTEGER, accepting INTEGER, "
                    "payout REAL)")
        con.executemany("INSERT INTO polls VALUES(?,'trades','c',?)", polls)
        con.executemany("INSERT INTO status VALUES(?,'c',0,1,NULL)", [(t,) for t in status])
        con.commit()
        con.close()
        return p

    def kinds(self):
        return [r[0] for r in self.db.q("SELECT kind FROM events WHERE kind LIKE 'external.%' ORDER BY id")]

    def watch(self, write_age, data_age):
        def fresh(now=None):
            return {self.EID: {"label": "x", "last_write_age_s": write_age, "last_data_age_s": data_age, "basis": "b"}}
        with mock.patch.object(self.fleet.ops, "external_freshness", fresh):
            return self.fleet.external_watch(self.db)

    def test_fresh_file_without_data_is_no_recovery(self):
        self.watch(EXTERNAL_RUNNING_S + 60, EXTERNAL_RUNNING_S + 60)
        self.assertEqual(self.kinds(), ["external.stale"])
        self.assertEqual(self.watch(2.0, EXTERNAL_RUNNING_S + 120), [self.EID])
        self.assertEqual(self.kinds(), ["external.stale"])

    def test_real_data_is_a_recovery(self):
        self.watch(EXTERNAL_RUNNING_S + 60, EXTERNAL_RUNNING_S + 60)
        self.watch(2.0, 30.0)
        self.assertEqual(self.kinds(), ["external.stale", "external.recovered"])

    def test_unreadable_database_decides_nothing(self):
        self.watch(EXTERNAL_RUNNING_S + 60, EXTERNAL_RUNNING_S + 60)
        self.watch(2.0, None)
        self.assertEqual(self.kinds(), ["external.stale"])

    def test_other_processes_keep_the_file_rule(self):
        fresh = lambda now=None: {"X": {"label": "x", "last_write_age_s": EXTERNAL_RUNNING_S + 1, "basis": "f"}}  # noqa: E731
        with mock.patch.object(self.fleet.ops, "external_freshness", fresh):
            self.assertEqual(self.fleet.external_watch(self.db), ["X"])

    def test_age_comes_from_the_newest_successful_row(self):
        self.assertEqual(self.ops.data_activity_age(self.pm_db([(900, 0), (800, 1)]), 1000), 200)

    def test_status_row_counts_as_activity(self):
        self.assertEqual(self.ops.data_activity_age(self.pm_db([(100, 0)], [950]), 1000), 50)

    def test_only_failures_give_an_age_of_at_least_the_window(self):
        self.assertEqual(self.ops.data_activity_age(self.pm_db([(600, 0), (700, 0)]), 1000), 400)

    def test_empty_or_missing_database(self):
        self.assertIsNone(self.ops.data_activity_age(self.pm_db(), 1000))
        self.assertIsNone(self.ops.data_activity_age(os.path.join(self.tmp, "none.db"), 1000))

    def test_the_read_does_not_change_the_database(self):
        p = self.pm_db([(600, 1)])
        before = open(p, "rb").read()
        self.ops.data_activity_age(p, 1000)
        self.assertEqual(open(p, "rb").read(), before)


if __name__ == "__main__":
    unittest.main()
