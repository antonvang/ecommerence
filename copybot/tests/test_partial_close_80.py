"""Director order 80 P0: the unapplied patch research/desk/patches/80_close_terminal_state.diff, applied strictly to a
temporary copy of lab/paper_runner.py. The lane account is opened by the real, unpatched lab code; only the patched copy's
close_ledger runs after that. Simulated only; temporary databases; mocked books; no network, no DNS, no lab.db."""
import hashlib
import itertools
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from lab import carry90, lane, paper_runner as real  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from tests.test_lab_engine_remediation_67 import apply_unified, load  # noqa: E402
from tests.test_partial_close_78 import DNS, HOUR, NOW, PERP, SPOT, market, no_network  # noqa: E402

PATCH = os.path.join(HERE, "research", "desk", "patches", "80_close_terminal_state.diff")
DAY = 86400
RAW = ("sim_orders", "sim_fills", "sim_equity", "sim_funding")
TARGET = os.path.join(HERE, "lab", "paper_runner.py")


def apply(tmp):
    with open(PATCH, encoding="utf-8") as f:
        return apply_unified(f.read(), os.path.dirname(HERE), tmp)


class Base(unittest.TestCase):
    temporary_hosts = True                                 # False: the spot host is as order 76 says, permanently gone

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab80")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        files = apply(self.tmp)
        self.pm = load("paper_runner_patched80", files["copybot/lab/paper_runner.py"])
        self.path = os.path.join(self.tmp, "db", "lab.db")
        self.db = DB(self.path)
        self.addCleanup(lambda: self.db.close())
        for p in (mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)):
            p.start()
            self.addCleanup(p.stop)
        if self.temporary_hosts:
            p = mock.patch.object(self.pm, "PERMANENT_UNAVAILABLE_SUFFIXES", ())
            p.start()
            self.addCleanup(p.stop)
        real._HOURLY.clear()
        self.get = market()
        with self.db.tx():
            self.db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                           metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(self.db, NOW - 60)
        self.led = {i["key"]: x for x, i in lane.started(self.db).items()}["carry90|BTCUSDT"]
        self.assertEqual(lane.run_one(self.db, self.led, self.get, NOW)["status"], "ok")
        lane.retire(self.db, self.led, "source", "synthetic test stop", None, NOW + 60)
        self.before = self.counts()
        self.urls = []

    def counts(self):
        return {t: self.db.one(f"SELECT COUNT(*) FROM {t} WHERE exp_id=?", self.led)[0] for t in RAW}

    def positions(self):
        return PaperEngine(self.db).ledger(self.led)["positions"]

    def close(self, t, spot=None, perp=None):
        self.get.now, self.get.spot, self.get.perp = t, spot, perp

        def spy(path):
            self.urls.append(path)
            return self.get(path)
        return self.pm.close_ledger(self.db, self.led, self.led, spy, t)

    def states(self):
        return [json.loads(r["payload"]) for r in self.db.q(
            "SELECT payload FROM events WHERE kind=? AND exp_id=? ORDER BY id", self.pm.CLOSE_STATE, self.led)]

    def assert_rows_kept(self):
        now = self.counts()
        for t, n in self.before.items():
            self.assertGreaterEqual(now[t], n, t)

    def restart(self):
        self.db.close()
        self.db = DB(self.path)
        self.pm._HOURLY.clear()


class IsolatedPatch(unittest.TestCase):
    def test_touches_only_paper_runner_and_the_repo_file_is_unpatched(self):
        with open(TARGET, "rb") as f:
            before = hashlib.sha256(f.read()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(apply(tmp)), ["copybot/lab/paper_runner.py"])
        with open(TARGET, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), before)
        self.assertFalse(hasattr(real, "CLOSE_STATE"))
        self.assertFalse(hasattr(real, "close_state_of"))


class Pure(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.pm = load("paper_runner_patched80_pure", apply(tmp)["copybot/lab/paper_runner.py"])

    def test_success_only_when_flat_and_marked_after_the_last_fill(self):
        for open_legs, reduced, fill, mark, perm, exp in itertools.product(
                ([], [PERP], [SPOT], [PERP, SPOT]), (set(), {PERP}), (None, 100, 200), (None, 100, 200),
                (set(), {SPOT}), (False, True)):
            s = self.pm.close_state_of(open_legs, reduced, fill, mark, perm, exp)
            ok = not open_legs and fill is not None and mark is not None and mark >= fill
            self.assertEqual(s == self.pm.CLOSE_SUCCESS, ok, (open_legs, reduced, fill, mark, perm, exp))

    def test_the_named_states_are_distinct(self):
        pm = self.pm
        self.assertEqual(pm.close_state_of([SPOT], {PERP}, 1, 1, set(), False), pm.PARTIAL_RETRYING)
        self.assertEqual(pm.close_state_of([SPOT], {PERP}, 1, 1, {SPOT}, False), pm.PARTIAL_TERMINAL)
        self.assertEqual(pm.close_state_of([PERP, SPOT], set(), 1, 1, set(), False), pm.INCOMPLETE_RETRYING)
        self.assertEqual(pm.close_state_of([PERP, SPOT], set(), 1, 1, set(), True), pm.INCOMPLETE_TERMINAL)
        self.assertEqual(pm.close_state_of([PERP, SPOT], set(), 1, 1, {SPOT}, False), pm.INCOMPLETE_RETRYING)
        self.assertEqual(len({pm.CLOSE_SUCCESS, pm.PARTIAL_RETRYING, pm.PARTIAL_TERMINAL, pm.INCOMPLETE_RETRYING,
                              pm.INCOMPLETE_TERMINAL}), 5)


class PermanentSpot(Base):
    temporary_hosts = False

    def test_perp_closes_spot_stays_and_the_state_says_so(self):
        r = self.close(NOW + HOUR)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)
        self.assertTrue(r["terminal"])
        self.assertEqual(set(self.positions()), {SPOT})
        (s,) = self.states()
        self.assertEqual(s["open_legs"], [SPOT])
        self.assertEqual(s["closed_legs"], [PERP])
        self.assertEqual(s["unpaired_open_legs"], [SPOT])
        self.assertEqual(s["permanent_legs"], [SPOT])
        self.assert_rows_kept()

    def test_the_blocked_host_is_never_contacted_and_nothing_is_invented(self):
        self.close(NOW + HOUR)
        self.assertFalse([u for u in self.urls if u.startswith(self.pm.SPOT_REST)])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_equity WHERE exp_id=? AND ts>?", self.led, NOW + 61)[0], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_fills WHERE exp_id=? AND instrument=? AND ts>?", self.led,
                                     SPOT, NOW + 61)[0], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=? AND exp_id=?", self.pm.MARK_FAILED,
                                     self.led)[0], 0)

    def test_terminal_is_sticky_silent_and_books_nothing_more(self):
        self.close(NOW + HOUR)
        rows, self.urls = self.counts(), []
        for t in (NOW + HOUR + 60, NOW + 2 * HOUR, NOW + 30 * DAY):
            r = self.close(t, spot=None)                   # even if the host answers
            self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)
            self.assertTrue(r["terminal"])
            self.assertEqual(r["orders"], [])
        self.assertEqual(self.urls, [])
        self.assertEqual(self.counts(), rows)
        self.assertEqual(len(self.states()), 1)

    def test_restart_keeps_the_terminal_state(self):
        self.close(NOW + HOUR)
        rows = self.counts()
        self.restart()
        self.urls = []
        r = self.close(NOW + 5 * HOUR, spot=None)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)
        self.assertEqual(self.urls, [])
        self.assertEqual(self.counts(), rows)
        self.assertEqual(len(self.states()), 1)

    def test_perp_down_keeps_retrying_until_only_the_permanent_leg_is_left(self):
        r = self.close(NOW + HOUR, perp=DNS)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_RETRYING)
        self.assertFalse(r["terminal"])
        r = self.close(NOW + 2 * HOUR)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)
        self.assertEqual([s["state"] for s in self.states()], [self.pm.INCOMPLETE_RETRYING, self.pm.PARTIAL_TERMINAL])

    def test_never_success_while_a_leg_is_open(self):
        for t in (NOW + HOUR, NOW + 2 * HOUR):
            self.assertNotEqual(self.close(t)["close_state"], self.pm.CLOSE_SUCCESS)
        self.assertNotIn(self.pm.CLOSE_SUCCESS, [s["state"] for s in self.states()])


class TemporaryOutage(Base):
    def test_both_legs_close_is_success_with_one_event(self):
        r = self.close(NOW + HOUR)
        self.assertEqual(r["close_state"], self.pm.CLOSE_SUCCESS)
        self.assertEqual(self.positions(), {})
        self.assertEqual([s["state"] for s in self.states()], [self.pm.CLOSE_SUCCESS])
        self.assertNotIn((self.led, self.led), self.pm.closing_ledgers(self.db))

    def test_one_leg_closed_is_retrying_then_success(self):
        r = self.close(NOW + HOUR, spot=DNS)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_RETRYING)
        self.assertFalse(r["terminal"])
        self.assertEqual(self.states()[-1]["unpaired_open_legs"], [SPOT])
        r = self.close(NOW + 2 * HOUR)
        self.assertEqual(r["close_state"], self.pm.CLOSE_SUCCESS)
        self.assertEqual(self.positions(), {})

    def test_repeated_attempts_write_no_new_rows_or_state_events(self):
        self.close(NOW + HOUR, spot=DNS)
        rows = self.counts()
        for t in (NOW + HOUR + 60, NOW + HOUR + 120, NOW + 2 * HOUR):
            self.close(t, spot=DNS)
        self.assertEqual(self.counts()["sim_fills"], rows["sim_fills"])
        self.assertEqual(self.counts()["sim_orders"], rows["sim_orders"])
        self.assertEqual(len(self.states()), 1)

    def test_retrying_is_bounded_and_ends_terminal(self):
        first = NOW + HOUR
        self.close(first, spot=DNS, perp=DNS)
        limit = self.pm.CLOSE_RETRY_MAX_S
        r = self.close(first + limit - 1, spot=DNS, perp=DNS)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_RETRYING)
        r = self.close(first + limit, spot=DNS, perp=DNS)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.urls = []
        r = self.close(first + limit + DAY)                # the data are back: a terminal state does not resume
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.assertEqual(self.urls, [])
        self.assertEqual(set(self.positions()), {PERP, SPOT})
        self.assertEqual([s["first_ts"] for s in self.states()], [int(first), int(first)])

    def test_partial_runs_out_of_time_as_partial_terminal(self):
        first = NOW + HOUR
        self.close(first, spot=DNS)
        r = self.close(first + self.pm.CLOSE_RETRY_MAX_S, spot=DNS)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)
        self.assertEqual(self.states()[-1]["open_legs"], [SPOT])

    def test_restart_keeps_the_retry_clock(self):
        first = NOW + HOUR
        self.close(first, spot=DNS)
        self.restart()
        r = self.close(first + DAY, spot=DNS)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_RETRYING)
        self.assertEqual(self.states()[-1]["first_ts"], int(first))
        self.assertEqual(len(self.states()), 1)
        r = self.close(first + self.pm.CLOSE_RETRY_MAX_S, spot=DNS)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)

    def test_thin_book_stays_partial_and_is_never_success(self):
        r = self.close(NOW + HOUR, spot=1.0, perp=1.0)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_RETRYING)
        self.assertEqual(set(self.positions()), {PERP, SPOT})

    def test_state_events_are_append_only(self):
        self.close(NOW + HOUR, spot=DNS, perp=DNS)
        one = [dict(r) for r in self.db.q("SELECT * FROM events WHERE kind=? AND exp_id=?", self.pm.CLOSE_STATE, self.led)]
        self.close(NOW + 2 * HOUR, spot=DNS)
        self.close(NOW + 3 * HOUR)
        rows = [dict(r) for r in self.db.q("SELECT * FROM events WHERE kind=? AND exp_id=? ORDER BY id",
                                           self.pm.CLOSE_STATE, self.led)]
        self.assertEqual(rows[:len(one)], one)
        self.assertEqual([json.loads(r["payload"])["state"] for r in rows],
                         [self.pm.INCOMPLETE_RETRYING, self.pm.PARTIAL_RETRYING, self.pm.CLOSE_SUCCESS])
        self.assert_rows_kept()


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
