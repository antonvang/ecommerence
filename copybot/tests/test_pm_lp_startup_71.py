"""Director order 71 C: reproduce the pm_lp start-up failure synthetically.

Temporary database, mocked http, no network. research/pm_lp.py is imported as it is and is NOT changed; the
RobustStart class below only exists in this test as a design prototype.
"""
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from research import pm_lp  # noqa: E402

REFUSED = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
EMPTY = {"data": [], "next_cursor": None}


class Stop(Exception):
    """Ends Collector.run's endless loop from the patched sleep."""


def stop_after(n):
    calls = []

    def sleep(_seconds):
        calls.append(1)
        if len(calls) >= n:
            raise Stop

    return sleep


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = pm_lp.open_db(os.path.join(tmp.name, "pm_lp.db"))
        self.addCleanup(self.db.close)
        self.d0 = pm_lp.day_of(pm_lp.time.time())
        self.logged = []


class StartupFailure(Base):
    def test_dns_failure_at_startup_ends_the_process(self):
        """run() calls refresh_rewards() before the loop and outside its try/except."""
        c = pm_lp.Collector(self.db, log=self.logged.append)
        with mock.patch.object(pm_lp, "http", side_effect=REFUSED):
            with self.assertRaises(urllib.error.URLError):
                c.run(self.d0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM polls").fetchone()[0], 0)

    def test_same_failure_inside_the_loop_is_survived(self):
        """After one good start, the identical refused connection no longer stops the collector."""
        c = pm_lp.Collector(self.db, log=self.logged.append)
        answers = [EMPTY]

        def http(url, body=None, tries=5):
            if answers:
                return answers.pop()
            raise REFUSED

        with mock.patch.object(pm_lp, "http", side_effect=http), \
                mock.patch.object(pm_lp, "REWARDS_EVERY", 0), \
                mock.patch.object(pm_lp.time, "sleep", stop_after(3)):
            with self.assertRaises(Stop):           # the loop was still running when the test ended it
                c.run(self.d0)
        self.assertTrue(self.logged, "the failed panel step should be logged by the loop")


class RobustStart(pm_lp.Collector):
    """Design prototype only: the first refresh gets the same protection as the later ones."""

    started = False

    def refresh_rewards(self):
        if self.started:
            return super().refresh_rewards()
        self.started = True
        try:
            return super().refresh_rewards()
        except Exception as e:
            self.log(f"start uden belønningsdata: {e!r}")
            return None


class DesignPrototype(Base):
    def test_guarded_first_refresh_stays_up_and_recovers(self):
        c = RobustStart(self.db, log=self.logged.append)
        seen = {"n": 0}

        def http(url, body=None, tries=5):
            seen["n"] += 1
            if seen["n"] == 1:
                raise REFUSED
            return EMPTY

        with mock.patch.object(pm_lp, "http", side_effect=http), \
                mock.patch.object(pm_lp, "REWARDS_EVERY", 0), \
                mock.patch.object(pm_lp.time, "sleep", stop_after(3)):
            with self.assertRaises(Stop):
                c.run(self.d0)
        self.assertTrue(any("start uden" in str(x) for x in self.logged))
        self.assertGreater(seen["n"], 1, "the refresh must be tried again once the loop runs")


if __name__ == "__main__":
    unittest.main()
