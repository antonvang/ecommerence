"""Director order 81 P1: research/desk/patches/81_close_terminal_state_v2.diff on a temporary copy of lab/paper_runner.py.
The committed order-80 patch is not changed. A close whose spot leg has no book closes nothing; terminal never means closed.
Simulated only; temporary databases; mocked books; no network, no DNS, no lab.db."""
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

PATCH = os.path.join(HERE, "research", "desk", "patches", "81_close_terminal_state_v2.diff")
DAY = 86400
RAW = ("sim_orders", "sim_fills", "sim_equity", "sim_funding")
TARGET = os.path.join(HERE, "lab", "paper_runner.py")


def apply(tmp):
    with open(PATCH, encoding="utf-8") as f:
        return apply_unified(f.read(), os.path.dirname(HERE), tmp)


class Base(unittest.TestCase):
    temporary_hosts = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab81")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pm = load("paper_runner_patched81", apply(self.tmp)["copybot/lab/paper_runner.py"])
        self.path = os.path.join(self.tmp, "db", "lab.db")
        self.db = DB(self.path)
        self.addCleanup(lambda: self.db.close())
        for p in (mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)):
            p.start()
            self.addCleanup(p.stop)
        self.permanent = None
        if self.temporary_hosts:
            self.set_permanent(())
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

    def set_permanent(self, value):
        if self.permanent:
            self.permanent.stop()
        self.permanent = mock.patch.object(self.pm, "PERMANENT_UNAVAILABLE_SUFFIXES", value)
        self.permanent.start()
        self.addCleanup(self._stop_permanent, self.permanent)

    def _stop_permanent(self, p):
        try:
            p.stop()
        except RuntimeError:
            pass

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

    def restart(self):
        self.db.close()
        self.db = DB(self.path)
        self.pm._HOURLY.clear()

    def depth_calls(self):
        return [u for u in self.urls if "depth" in u]


class Isolated(unittest.TestCase):
    def test_touches_only_paper_runner_and_the_repo_is_unpatched(self):
        with open(TARGET, "rb") as f:
            before = hashlib.sha256(f.read()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(apply(tmp)), ["copybot/lab/paper_runner.py"])
        with open(TARGET, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), before)
        self.assertFalse(hasattr(real, "CLOSE_STATE"))


class Pure(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.pm = load("paper_runner_patched81_pure", apply(tmp)["copybot/lab/paper_runner.py"])

    def test_seven_days_is_the_retry_default(self):
        self.assertEqual(self.pm.CLOSE_RETRY_MAX_S, 7 * DAY)

    def test_success_only_when_flat_and_marked_after_the_last_fill(self):
        for open_legs, reduced, fill, mark, blocked, exp in itertools.product(
                ([], [PERP], [SPOT], [PERP, SPOT]), (set(), {PERP}), (None, 100, 200), (None, 100, 200),
                (set(), {SPOT}, {PERP, SPOT}), (False, True)):
            s = self.pm.close_state_of(open_legs, reduced, fill, mark, blocked, exp)
            ok = not open_legs and fill is not None and mark is not None and mark >= fill
            self.assertEqual(s == self.pm.CLOSE_SUCCESS, ok, (open_legs, reduced, fill, mark, blocked, exp))

    def test_blocked_legs_are_the_permanent_leg_and_its_partner_only(self):
        pos = {"AUSDT": -1.0, "AUSDT.SPOT": 1.0, "BUSDT": -1.0}
        self.assertEqual(self.pm.blocked_legs(pos), {"AUSDT", "AUSDT.SPOT"})
        self.assertEqual(self.pm.blocked_legs({"BUSDT": -1.0}), set())


class PermanentSpot(Base):
    temporary_hosts = False

    def test_the_perp_leg_is_not_closed_and_the_close_is_incomplete(self):
        r = self.close(NOW + HOUR)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.assertTrue(r["terminal"])
        self.assertFalse(r["closed"])
        self.assertTrue(r["requires_decision"])
        self.assertEqual(set(self.positions()), {PERP, SPOT})
        self.assertEqual(self.counts()["sim_fills"], self.before["sim_fills"])
        (s,) = self.states()
        self.assertEqual(s["blocked_legs"], sorted([PERP, SPOT]))
        self.assertEqual(s["permanent_legs"], [SPOT])
        self.assertTrue(s["requires_decision"])
        self.assertFalse(s["closed"])

    def test_no_book_is_requested_for_either_leg(self):
        self.close(NOW + HOUR)
        self.assertEqual(self.depth_calls(), [])
        self.assertFalse([u for u in self.urls if u.startswith(self.pm.SPOT_REST)])

    def test_terminal_is_sticky_without_repeated_attempts(self):
        self.close(NOW + HOUR)
        rows, self.urls = self.counts(), []
        for t in (NOW + HOUR + 60, NOW + HOUR + 120):
            r = self.close(t)
            self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
            self.assertFalse(r["closed"])
            self.assertEqual(r["orders"], [])
        self.assertEqual(self.depth_calls(), [])
        self.assertEqual(self.counts()["sim_fills"], rows["sim_fills"])
        self.assertEqual(self.counts()["sim_orders"], rows["sim_orders"])
        self.assertEqual(len(self.states()), 1)

    def test_terminal_does_not_resume_when_the_host_answers(self):
        self.close(NOW + HOUR)
        self.set_permanent(())
        rows = self.counts()
        r = self.close(NOW + 2 * HOUR, spot=None)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.assertEqual(self.counts()["sim_fills"], rows["sim_fills"])
        self.assertEqual(set(self.positions()), {PERP, SPOT})

    def test_funding_on_the_open_perp_keeps_booking_without_doubling(self):
        self.close(NOW + HOUR)
        one = self.counts()["sim_funding"]
        t = NOW + 4 * HOUR                                 # past the 00:00 UTC settlement
        self.close(t)
        two = self.counts()["sim_funding"]
        self.assertGreater(two, one)
        self.close(t + 60)
        self.assertEqual(self.counts()["sim_funding"], two)
        self.assertEqual(self.depth_calls(), [])

    def test_restart_keeps_the_terminal_state(self):
        self.close(NOW + HOUR)
        rows = self.counts()
        self.restart()
        self.urls = []
        r = self.close(NOW + HOUR + 300)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.assertFalse(r["closed"])
        self.assertEqual(self.depth_calls(), [])
        self.assertEqual(self.counts()["sim_fills"], rows["sim_fills"])
        self.assertEqual(len(self.states()), 1)

    def test_never_success_while_a_leg_is_open(self):
        for t in (NOW + HOUR, NOW + 2 * HOUR, NOW + 8 * DAY):
            self.assertNotEqual(self.close(t)["close_state"], self.pm.CLOSE_SUCCESS)

    def test_no_row_is_lost(self):
        self.close(NOW + HOUR)
        self.close(NOW + 2 * HOUR)
        now = self.counts()
        for t, n in self.before.items():
            self.assertGreaterEqual(now[t], n, t)


class ALegAlreadyClosed(Base):
    def test_a_leg_closed_before_the_host_was_declared_gone_is_partial_terminal(self):
        r = self.close(NOW + HOUR, spot=DNS)               # the host is only down: the perp leg closes
        self.assertEqual(r["close_state"], self.pm.PARTIAL_RETRYING)
        self.set_permanent((".SPOT",))
        r = self.close(NOW + 2 * HOUR)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)
        self.assertFalse(r["closed"])
        self.assertTrue(r["terminal"])
        s = self.states()[-1]
        self.assertEqual(s["closed_legs"], [PERP])
        self.assertEqual(s["unpaired_open_legs"], [SPOT])
        self.assertEqual(set(self.positions()), {SPOT})


class TemporaryOutage(Base):
    def test_both_legs_close_is_the_only_closed_state(self):
        r = self.close(NOW + HOUR)
        self.assertEqual(r["close_state"], self.pm.CLOSE_SUCCESS)
        self.assertTrue(r["closed"])
        self.assertEqual(self.positions(), {})

    def test_retrying_then_success(self):
        r = self.close(NOW + HOUR, spot=DNS)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_RETRYING)
        self.assertFalse(r["closed"])
        r = self.close(NOW + 2 * HOUR)
        self.assertEqual(r["close_state"], self.pm.CLOSE_SUCCESS)

    def test_repeats_write_nothing_new(self):
        self.close(NOW + HOUR, spot=DNS)
        rows = self.counts()
        for t in (NOW + HOUR + 60, NOW + HOUR + 120, NOW + 2 * HOUR):
            self.close(t, spot=DNS)
        self.assertEqual(self.counts()["sim_fills"], rows["sim_fills"])
        self.assertEqual(self.counts()["sim_orders"], rows["sim_orders"])
        self.assertEqual(len(self.states()), 1)

    def test_retry_limit_ends_terminal_and_open_legs_are_not_closed(self):
        first = NOW + HOUR
        self.close(first, spot=DNS, perp=DNS)
        r = self.close(first + 7 * DAY - 1, spot=DNS, perp=DNS)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_RETRYING)
        r = self.close(first + 7 * DAY, spot=DNS, perp=DNS)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.assertFalse(r["closed"])
        self.assertEqual(set(self.positions()), {PERP, SPOT})
        self.urls = []
        r = self.close(first + 8 * DAY)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.assertEqual(self.depth_calls(), [])

    def test_restart_keeps_the_retry_clock(self):
        first = NOW + HOUR
        self.close(first, spot=DNS)
        self.restart()
        self.close(first + DAY, spot=DNS)
        self.assertEqual(self.states()[-1]["first_ts"], int(first))
        r = self.close(first + 7 * DAY, spot=DNS)
        self.assertEqual(r["close_state"], self.pm.PARTIAL_TERMINAL)

    def test_earlier_state_events_are_never_changed(self):
        self.close(NOW + HOUR, spot=DNS, perp=DNS)
        one = [dict(r) for r in self.db.q("SELECT * FROM events WHERE kind=? AND exp_id=?", self.pm.CLOSE_STATE, self.led)]
        self.close(NOW + 2 * HOUR, spot=DNS)
        self.close(NOW + 3 * HOUR)
        rows = [dict(r) for r in self.db.q("SELECT * FROM events WHERE kind=? AND exp_id=? ORDER BY id",
                                           self.pm.CLOSE_STATE, self.led)]
        self.assertEqual(rows[:len(one)], one)
        self.assertEqual(json.loads(rows[-1]["payload"])["state"], self.pm.CLOSE_SUCCESS)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
