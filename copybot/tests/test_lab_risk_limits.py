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


if __name__ == "__main__":
    unittest.main()
