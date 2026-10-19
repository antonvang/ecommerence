"""Risk limits of the simulated ledgers (amendment 7 section 1, amendment 4 section 7): the 10 % drawdown breaker at
its boundary, stale / missing / crossed data, FAIL_CLOSED, repeated and concurrent resumes, and that a CLEAR of one
ledger never overrides another active block. Temporary databases only; no network, no order is ever sent."""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lab import lifecycle  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import Book, PaperEngine  # noqa: E402
from lab.risk import GLOBAL, Risk  # noqa: E402

L, OTHER = "SHADOW_E_mvrv_value_p3", "FWD_E_xs_momentum_p2"
NOW = 1792416000.0


def book(age=0.0, crossed=False, empty=False):
    if empty:
        return Book(ts=NOW - age, bids=(), asks=())
    bid, ask = (101.0, 100.0) if crossed else (100.0, 100.1)
    return Book(ts=NOW - age, bids=((bid, 5.0),), asks=((ask, 5.0),))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labrisk")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.risk = Risk(self.db, now=lambda: NOW)
        self.p = [mock.patch.object(Risk, "_shadow_ok", lambda self, ledger: True),          # an active shadow
                  mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mark(self, dd, ledger=L):
        self.db.append("sim_equity", exp_id=ledger, ts=int(NOW), equity=10000 * (1 - dd), cash=10000 * (1 - dd),
                       exposure=0.0, peak=10000.0, drawdown=dd)

    def clears(self, ledger=L):
        return self.db.one("SELECT COUNT(*) FROM risk_events WHERE exp_id=? AND action='CLEAR'", ledger)[0]


class DrawdownBoundary(Base):
    """The breaker pauses at drawdown >= 10 % (risk.after_equity) and a resume is refused at >= 10 % (the same
    unchanged breaker would pause again at the next mark)."""

    def test_the_breaker_at_the_boundary(self):
        for dd, paused in ((0.0999999, False), (0.10, True), (0.1000001, True)):
            with self.subTest(dd=dd):
                led = f"SHADOW_E_x{int(dd * 1e7)}"
                self.risk.after_equity(led, dd)
                self.assertEqual(self.risk.paused(led), paused)

    def test_a_resume_at_the_boundary(self):
        for dd, ok in ((0.0999999, True), (0.10, False), (0.1000001, False)):
            with self.subTest(dd=dd):
                led = f"FWD_E_x{int(dd * 1e7)}"
                self.risk.pause(led, "data_fetch", None, None, "fixture: a failed fetch")
                self.mark(dd, led)
                if ok:
                    self.assertTrue(self.risk.resume_simulated(led, "human:anton", "fixture: data is back again"))
                    self.assertFalse(self.risk.paused(led))
                else:
                    with self.assertRaises(lifecycle.LifecycleError):
                        self.risk.resume_simulated(led, "human:anton", "fixture: data is back again")
                    self.assertTrue(self.risk.paused(led))

    def test_the_engine_computes_drawdown_from_the_running_peak(self):
        eng = PaperEngine(self.db, now=lambda: NOW)
        eng.risk = self.risk
        with mock.patch.object(eng, "ledger", lambda exp_id: {"capital": 10000.0, "cash": 10000.0, "positions": {}}):
            r = eng.mark(L, {})
        self.assertEqual(r["drawdown"], 0.0)
        with mock.patch.object(eng, "ledger", lambda exp_id: {"capital": 10000.0, "cash": 12000.0, "positions": {}}):
            eng.mark(L, {})                                                              # a new peak: 12 000
        with mock.patch.object(eng, "ledger", lambda exp_id: {"capital": 10000.0, "cash": 10800.0, "positions": {}}):
            r = eng.mark(L, {})                                                          # 10 % below the peak
        self.assertAlmostEqual(r["drawdown"], 0.10)
        self.assertTrue(self.risk.paused(L))                                             # paused at exactly 10 %


class StaleMissingAndFailClosed(Base):
    def test_missing_stale_crossed_and_empty_books_block_entries(self):
        self.assertEqual(self.risk.entry_allowed(L, False, book())[0], True)
        for b, why in ((None, "no order book"), (book(age=61), "old"), (book(crossed=True), "crossed"),
                       (book(empty=True), "crossed or empty")):
            ok, msg = self.risk.entry_allowed(L, False, b)
            self.assertFalse(ok, msg)
            self.assertIn(why, msg)
        self.assertEqual(self.risk.entry_allowed(L, False, book(age=60))[0], True)       # 60 s is still fresh
        n = self.db.one("SELECT COUNT(*) FROM risk_events WHERE exp_id=? AND action='BLOCK'", L)[0]
        self.assertEqual(n, 4)                                                           # each block is recorded

    def test_fail_closed_blocks_new_exposure_but_lets_positions_be_reduced(self):
        self.risk.trip_fail_closed("reconciliation", "fixture: a mismatch")
        self.assertEqual(self.risk.entry_allowed(L, False, book()), (False, "lab is FAIL_CLOSED"))
        self.assertTrue(self.risk.entry_allowed(L, True, book())[0])                    # reduce-only still closes
        with self.assertRaises(lifecycle.LifecycleError):
            self.risk.clear_fail_closed("agent:risk-1", "an agent may not clear it")
        self.risk.clear_fail_closed("human:anton", "fixture: reconciled by hand")
        self.assertTrue(self.risk.entry_allowed(L, False, book())[0])


class RepeatedAndConcurrentResumes(Base):
    def test_a_repeated_resume_writes_nothing(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture: a failed fetch")
        self.mark(0.001)
        self.assertTrue(self.risk.resume_simulated(L, "human:anton", "fixture: the data is back"))
        rows = self.db.one("SELECT COUNT(*) FROM risk_events")[0], self.db.one("SELECT COUNT(*) FROM events")[0]
        self.assertFalse(self.risk.resume_simulated(L, "human:anton", "fixture: the data is back again"))
        self.assertEqual((self.db.one("SELECT COUNT(*) FROM risk_events")[0],
                          self.db.one("SELECT COUNT(*) FROM events")[0]), rows)
        self.assertEqual(self.clears(), 1)

    def test_two_resumes_at_once_record_one_clear(self):
        """Two terminals type sim-resume at the same moment: the second one checks after the first committed (the
        check runs inside the write transaction), so exactly one CLEAR is recorded."""
        self.risk.pause(L, "data_fetch", None, None, "fixture: a failed fetch")
        self.mark(0.001)
        other = DB(self.path)
        second = Risk(other, now=lambda: NOW)
        real_tx, fired, res = self.db.tx, [], {}

        def tx():
            if not fired:                                                                # the other terminal first
                fired.append(1)
                res["second"] = second.resume_simulated(L, "human:anton", "fixture: the second terminal")
            return real_tx()
        with mock.patch.object(self.db, "tx", tx):
            res["first"] = self.risk.resume_simulated(L, "human:anton", "fixture: the first terminal")
        other.close()
        self.assertEqual(sorted(res.values()), [False, True])
        self.assertEqual(self.clears(), 1)

    def test_threads_racing_record_one_clear(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture: a failed fetch")
        self.mark(0.001)
        start, out = threading.Barrier(4), []

        def go():
            db = DB(self.path)
            try:
                start.wait()
                out.append(Risk(db, now=lambda: NOW).resume_simulated(L, "human:anton", "fixture: racing terminals"))
            finally:
                db.close()
        ts = [threading.Thread(target=go) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
        self.assertEqual(sorted(out), [False, False, False, True])
        self.assertEqual(self.clears(), 1)


class AClearNeverOverridesAnotherBlock(Base):
    def test_a_resume_leaves_every_other_block_in_place(self):
        self.risk.pause(L, "data_fetch", None, None, "fixture: a failed fetch")
        self.risk.pause(OTHER, "max_drawdown", 0.12, 0.10, "fixture: drawdown 12 %")
        self.risk.trip_fail_closed("reconciliation", "fixture: a mismatch")
        self.risk.start_warmup(L)
        self.mark(0.001)
        self.assertTrue(self.risk.resume_simulated(L, "human:anton", "fixture: the data is back"))
        self.assertFalse(self.risk.paused(L))
        self.assertTrue(self.risk.paused(OTHER))                                         # another ledger's pause
        self.assertTrue(self.risk.fail_closed())                                         # the lab-wide stop
        self.assertEqual(self.risk.entry_allowed(L, False, book()), (False, "lab is FAIL_CLOSED"))
        self.risk.clear_fail_closed("human:anton", "fixture: reconciled by hand")
        self.assertEqual(self.risk.entry_allowed(L, False, book()), (False, "warming up after a restart"))
        self.assertTrue(self.risk.observe_book(L, book()))                               # fresh data ends warm-up
        self.assertFalse(self.risk.entry_allowed(L, False, book(age=120))[0])           # stale data still blocks
        with mock.patch.object(Risk, "_shadow_ok", lambda self, ledger: False):         # shadow no longer active
            self.assertFalse(self.risk.entry_allowed(L, False, book())[0])
        self.assertTrue(self.risk.entry_allowed(L, False, book())[0])

    def test_a_resume_is_refused_for_anything_but_a_simulated_ledger(self):
        for led in ("E_paper_x", GLOBAL):
            with self.assertRaises(lifecycle.LifecycleError):
                self.risk.resume_simulated(led, "human:anton", "fixture: not a simulated ledger")
        with self.assertRaises(lifecycle.LifecycleError):
            self.risk.resume_simulated(L, "agent:risk-1", "fixture: an agent may not resume")
        with self.assertRaises(lifecycle.LifecycleError):
            self.risk.resume_simulated(L, "human:anton", "short")



class ClearingFailClosedNeedsTheCauseGone(Base):
    """A human CLEAR of FAIL_CLOSED is refused while the cause still holds: broken hash chains or missing append-only
    triggers, an overfilled order, or a started ledger that does not reconcile. Reconciliation and disk are
    re-checked by the fleet within seconds anyway; integrity and overfill only at the next start, so without this a
    clear would let the lab trade on a broken registry until then."""

    def trip(self, rule):
        self.risk.trip_fail_closed(rule, f"fixture: {rule}")
        self.assertTrue(self.risk.fail_closed())

    def test_a_clean_lab_is_cleared(self):
        self.trip("worker_failed")
        self.risk.clear_fail_closed("human:anton", "fixture: the worker is back")
        self.assertFalse(self.risk.fail_closed())

    def test_broken_chains_or_missing_triggers_keep_it_closed(self):
        self.db.event("fixture.row", "fixture", None, {"n": 1})
        self.db.con.execute("DROP TRIGGER events_no_update")
        self.db.con.execute("UPDATE events SET payload='{\"n\": 2}' WHERE kind='fixture.row'")
        self.db.con.commit()
        self.trip("integrity")
        with self.assertRaises(lifecycle.LifecycleError) as c:
            self.risk.clear_fail_closed("human:anton", "fixture: looked at it")
        self.assertIn("integrity", str(c.exception))
        self.assertTrue(self.risk.fail_closed())

    def test_an_overfilled_order_keeps_it_closed(self):
        self.db.append("sim_orders", order_id="o1", exp_id=L, ts=int(NOW), instrument="XUSDT", side="buy", qty=1.0,
                       limit_px=None, style="taker", reduce_only=0, signal_ref="fixture", cost_model={})
        for i in range(2):
            self.db.append("sim_fills", fill_id=f"o1|{i}", order_id="o1", exp_id=L, ts=int(NOW), instrument="XUSDT",
                           side="buy", px=1.0, qty=1.0, fee=0.0, slippage=0.0, liquidity="taker", mid=1.0,
                           book_ts=NOW)
        self.trip("overfill")
        with self.assertRaises(lifecycle.LifecycleError) as c:
            self.risk.clear_fail_closed("human:anton", "fixture: looked at it")
        self.assertIn("overfill", str(c.exception))

    def test_a_ledger_that_does_not_reconcile_keeps_it_closed(self):
        self.db.event("paper.started", "human:anton", L, {"simulated": True})
        self.trip("reconciliation")
        with mock.patch.object(PaperEngine, "reconcile", lambda self, e: {"ok": False, "problems": ["fixture"]}):
            with self.assertRaises(lifecycle.LifecycleError) as c:
                self.risk.clear_fail_closed("human:anton", "fixture: looked at it")
        self.assertIn("reconcil", str(c.exception))
        with mock.patch.object(PaperEngine, "reconcile", lambda self, e: {"ok": True, "problems": []}):
            self.risk.clear_fail_closed("human:anton", "fixture: reconciled by hand now")
        self.assertFalse(self.risk.fail_closed())


class ClearingFailClosedIsAtomic(Base):
    """The checks and the CLEAR are one BEGIN IMMEDIATE transaction: a cause that arises while the checks run waits
    and is recorded after the CLEAR, instead of being swallowed by it. An error in a check refuses the clear."""

    def trip_meanwhile(self):
        """Run clear_fail_closed while another process trips disk_low during its checks; returns that thread."""
        done, orig = [], Risk.fail_closed_causes

        def trip():
            other = DB(self.path)
            try:
                Risk(other, now=lambda: NOW).trip_fail_closed("disk_low", "fixture: the disk filled up meanwhile")
                done.append(1)
            finally:
                other.close()
        t = threading.Thread(target=trip)

        def causes(risk):
            t.start()
            t.join(0.5)                       # the old code let it finish here: FAIL_CLOSED was still set, so no-op
            return orig(risk)
        with mock.patch.object(Risk, "fail_closed_causes", causes):
            self.assertTrue(self.risk.clear_fail_closed("human:anton", "fixture: the worker is back"))
        t.join(30)
        return done

    def test_a_cause_that_arises_during_the_checks_is_not_cleared(self):
        self.risk.trip_fail_closed("worker_failed", "fixture: a worker died")
        self.assertEqual(self.trip_meanwhile(), [1])
        self.assertTrue(self.risk.fail_closed())
        last = self.db.one("SELECT rule FROM risk_events WHERE exp_id=? AND action IN ('FAIL_CLOSED','CLEAR') "
                           "ORDER BY id DESC LIMIT 1", GLOBAL)[0]
        self.assertEqual(last, "disk_low")

    def test_an_error_in_a_check_refuses_the_clear(self):
        self.risk.trip_fail_closed("integrity", "fixture")
        rows = self.db.one("SELECT COUNT(*) FROM risk_events")[0]
        with mock.patch.object(DB, "verify", side_effect=RuntimeError("fixture: verify crashed")):
            with self.assertRaises(RuntimeError):
                self.risk.clear_fail_closed("human:anton", "fixture: looked at it")
        self.assertTrue(self.risk.fail_closed())
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM risk_events")[0], rows)
        self.assertFalse(self.db.con.in_transaction)                      # rolled back, the registry is writable

    def test_low_disk_keeps_it_closed(self):
        self.risk.trip_fail_closed("disk_low", "fixture")
        low = {"total": 1, "used": 1, "free": 5, "free_ok": False, "min_free": 10}
        with mock.patch("lab.ops.disk", lambda path: low):
            with self.assertRaises(lifecycle.LifecycleError) as c:
                self.risk.clear_fail_closed("human:anton", "fixture: looked at it")
        self.assertIn("disk", str(c.exception))
        self.assertTrue(self.risk.fail_closed())

    def test_a_clear_without_fail_closed_writes_nothing(self):
        rows = self.db.one("SELECT COUNT(*) FROM risk_events")[0], self.db.one("SELECT COUNT(*) FROM events")[0]
        self.assertFalse(self.risk.clear_fail_closed("human:anton", "fixture: nothing to clear"))
        self.assertEqual((self.db.one("SELECT COUNT(*) FROM risk_events")[0],
                          self.db.one("SELECT COUNT(*) FROM events")[0]), rows)


class ConcurrentTripsAndPauses(Base):
    """trip_fail_closed and pause check inside their write transaction: two at once record one row."""

    def first_lets_the_other_go(self, call_first, call_other):
        other = DB(self.path)
        real_tx, fired = self.db.tx, []

        def tx():
            if not fired:
                fired.append(1)
                call_other(Risk(other, now=lambda: NOW))
            return real_tx()
        with mock.patch.object(self.db, "tx", tx):
            call_first(self.risk)
        other.close()

    def test_two_trips_at_once_record_one_fail_closed(self):
        trip = lambda r: r.trip_fail_closed("worker_failed", "fixture: a worker died")      # noqa: E731
        self.first_lets_the_other_go(trip, trip)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM risk_events WHERE action='FAIL_CLOSED'")[0], 1)

    def test_two_pauses_at_once_record_one_pause(self):
        pause = lambda r: r.pause(L, "data_fetch", None, None, "fixture: a failed fetch")    # noqa: E731
        self.first_lets_the_other_go(pause, pause)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM risk_events WHERE exp_id=? AND action='PAUSE'", L)[0], 1)

    def test_threads_racing_trip_once(self):
        start = threading.Barrier(4)

        def go():
            db = DB(self.path)
            try:
                start.wait()
                Risk(db, now=lambda: NOW).trip_fail_closed("worker_failed", "fixture: racing workers")
            finally:
                db.close()
        ts = [threading.Thread(target=go) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM risk_events WHERE action='FAIL_CLOSED'")[0], 1)


class ClearFailClosedCommand(Base):
    """python3 -m lab clear-fail-closed: typed by a human in a terminal, refused while the cause holds."""

    def cli(self, *argv, guard=lambda step: None):
        from lab.__main__ import main
        lines = []
        with mock.patch("lab.__main__.TERMINAL_GUARD", guard):
            rc = main(list(argv), self.path, lines.append)
        return rc, "\n".join(lines)

    def test_a_human_in_a_terminal_clears_it(self):
        self.risk.trip_fail_closed("worker_failed", "fixture: a worker died")
        rc, txt = self.cli("clear-fail-closed", "--reason", "fixture: the worker is back")
        self.assertEqual(rc, 0, txt)
        self.assertIn("FAIL_CLOSED cleared", txt)
        self.assertFalse(self.risk.fail_closed())
        actor = self.db.one("SELECT actor FROM risk_events WHERE action='CLEAR' ORDER BY id DESC LIMIT 1")[0]
        self.assertTrue(actor.startswith("human:"), actor)
        rc, txt = self.cli("clear-fail-closed", "--reason", "fixture: the worker is back again")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to clear", txt)

    def test_it_prints_the_cause_and_keeps_it_closed(self):
        self.db.event("paper.started", "human:anton", L, {"simulated": True})
        self.risk.trip_fail_closed("reconciliation", "fixture")
        with mock.patch.object(PaperEngine, "reconcile", lambda self, e: {"ok": False, "problems": ["fixture"]}):
            rc, txt = self.cli("clear-fail-closed", "--reason", "fixture: looked at it")
        self.assertEqual(rc, 1)
        self.assertIn("refused: FAIL_CLOSED stays until the cause is gone", txt)
        self.assertTrue(self.risk.fail_closed())

    def test_an_assistant_session_or_no_terminal_is_refused(self):
        from lab import __main__ as cli_mod
        self.risk.trip_fail_closed("worker_failed", "fixture: a worker died")
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            rc, txt = self.cli("clear-fail-closed", "--reason", "an assistant clears it", guard=cli_mod.terminal_human)
        self.assertEqual(rc, 1)
        self.assertIn("an assistant session may not clear FAIL_CLOSED", txt)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("sys.stdin.isatty", lambda: False):
            rc, txt = self.cli("clear-fail-closed", "--reason", "no terminal clears it", guard=cli_mod.terminal_human)
        self.assertEqual(rc, 1)
        self.assertIn("must be typed in an interactive terminal", txt)
        self.assertTrue(self.risk.fail_closed())


if __name__ == "__main__":
    unittest.main()
