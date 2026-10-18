"""Integration tests for automatic promotion (research/PROTOCOL_V3.md amendments 4 and 4a).

The genuinely eligible candidate is a PROTOCOL v3 catalogue experiment (mvrv_value: live inputs exist for it) driven
through the strategy agent's real pass, the lifecycle, the paper runner and the paper engine against faked public feeds.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, jobs, lifecycle, paper_runner, pipeline, promotion, registry  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402
from lab.paper import Book, PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.lab_fixtures import approve_paper, frozen, supervised  # noqa: E402
from tests.test_lab_paper_runner import SAT, feed  # noqa: E402

HOUR = 3600
GOOD = "E_mvrv_value_p3"


def cm_feed(now=SAT):
    def get(url):
        rows = []
        for j, s in enumerate(data.UNIVERSE_CM16):
            for d in range(130):
                day = datetime.fromtimestamp(int(now) // 86400 * 86400 - (d + 1) * 86400, timezone.utc)
                rows.append({"asset": s.replace("USDT", "").lower(), "time": day.strftime("%Y-%m-%dT00:00:00.000000000Z"),
                             "CapMVRVCur": str(0.5 + 0.1 * j), "SplyCur": str(1e9 * (1 + 0.001 * d))})
        return {"data": rows}
    return get


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labpromo")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.patches = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                        mock.patch.object(promotion.control, "resources", lambda *a, **k: {"ok": True})]
        for p in self.patches:
            p.start()
        supervised(self.db, SAT)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- fixtures ----------
    def experiment(self, eid, template, state, verdict=None, label="EXPLORATORY"):
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint=eid,
                       spec_json={**pipeline.template_spec(template)})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=state, actor="fixture",
                       reason="fixture: experiment state")
        if verdict:
            registry.record_result(self.db, eid, label, verdict, {}, {}, "system:test")
        params = {"mode": "level", "k": 3} if template == "mvrv_value" else {"mode": "weekend_only"}
        frozen(self.db, eid, "cost", {"selected": 0})
        frozen(self.db, eid, "backtest", {"variants": [{"variant": 0, "params": params, "fit": None,
                                                               "positions": {}}]})

    def screen_passed(self, eid=GOOD):
        self.experiment(eid, "mvrv_value", "SCREEN_PASSED", "PASS (screen): all validation gates passed")

    def holdout_pass(self, eid=GOOD):
        """Records the holdout outcome exactly as pipeline.step_holdout does (result + guarded automatic edge)."""
        rid = registry.record_result(self.db, eid, "VALIDATION", "PASS (holdout): paper-eligible", {}, {}, "system:t")
        ev = {"result_id": rid}
        lifecycle.auto_transition(self.db, eid, "VALIDATED", "system:validation-1", "holdout passed", ev,
                                  guards=(registry.make_result_guard(ev),))
        return rid

    def promoted(self, eid=GOOD):
        self.experiment(eid, "mvrv_value", "VALIDATED", "PASS (holdout): paper-eligible", label="VALIDATION")
        self.policy_on()
        d = promotion.decide(self.db, eid, SAT)
        self.assertTrue(d["allowed"], d)
        return d

    def policy_on(self):
        promotion.set_policy(self.db, True, "human:test", "user enabled automatic promotion in the test")

    def run_paper(self, now=SAT, get=None, cm=None):
        return paper_runner.run(self.db, get or feed(now), now, cm_get=cm or cm_feed(now))

    def orders(self, ledger=None):
        if ledger:
            return self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", ledger)[0]
        return self.db.one("SELECT COUNT(*) FROM sim_orders")[0]

    def positions(self, ledger=GOOD):
        return PaperEngine(self.db).ledger(ledger)["positions"]

    def book(self, now=SAT):
        return Book(ts=now, bids=((99.99, 1000),), asks=((100.01, 1000),))


class A_RejectedCannotTrade(Base):
    def test_rejected_candidate_is_not_promoted_and_places_no_order(self):
        self.policy_on()
        self.experiment("E_rej", "mvrv_value", "REJECTED", "REJECTED at validation: failed net Sharpe > buy-and-hold")
        self.assertFalse(promotion.decide(self.db, "E_rej", SAT)["applicable"])
        self.assertFalse(promotion.trading_authorized(self.db, "E_rej")[0])
        self.run_paper()
        self.assertEqual(self.orders(), 0)
        with self.assertRaises(lifecycle.LifecycleError):
            PaperEngine(self.db).start("E_rej", 10_000.0, paper_runner.cost_model())


class B_PendingGatesWait(Base):
    def test_every_closed_gate_means_wait_and_no_order(self):
        self.experiment("E_obs", "mvrv_value", "OBSERVATION", "OBSERVE (forward test): luck check pending")
        self.experiment("E_nohold", "vrp_timing", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        self.experiment("E_v1", "day_of_week", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        self.experiment("E_nolive", "oi_growth", "VALIDATED", "PASS (holdout): paper-eligible", label="VALIDATION")
        self.screen_passed()
        d = promotion.decide(self.db, GOOD, SAT)                                  # policy still off
        self.assertEqual(d["closed"], ["automatic promotion policy on (human-enabled)"])
        self.policy_on()
        expect = {"E_nohold": "a clean 2024 holdout is possible (amendment 1)",
                  "E_v1": "registered under PROTOCOL v3 (amendment 4a)",
                  "E_nolive": "paper runner has live data for this template"}
        for eid, gate in expect.items():
            d = promotion.decide(self.db, eid, SAT)
            self.assertFalse(d["allowed"], eid)
            self.assertIn(gate, d["closed"], eid)
        self.assertFalse(promotion.decide(self.db, "E_obs", SAT)["applicable"])        # forward test not done yet
        self.assertEqual([lifecycle.state(self.db, e) for e in ("E_obs", "E_nohold", "E_v1", "E_nolive")],
                         ["OBSERVATION", "SCREEN_PASSED", "SCREEN_PASSED", "VALIDATED"])
        self.run_paper()
        self.assertEqual(self.orders(), 0)

    def test_a_non_pass_verdict_is_not_a_pass(self):
        self.policy_on()
        self.experiment("E_odd", "mvrv_value", "SCREEN_PASSED", "PASSIVE note: not a pass")
        self.assertIn("latest result is a PASS (screen incl. luck check, or forward test)",
                      promotion.decide(self.db, "E_odd", SAT)["closed"])


class C_QualifiedPromotesAutomatically(Base):
    def test_hypothesis_to_paper_orders_without_a_per_strategy_click(self):
        self.policy_on()
        self.screen_passed()
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            r1 = fleet.strategy_pass(self.db)                                 # the strategy agent's normal pass
        self.assertIn((GOOD, "VALIDATION", True), r1["promotions"])
        self.assertEqual(lifecycle.state(self.db, GOOD), "VALIDATION")
        self.assertEqual(jobs.get(self.db, f"holdout|{GOOD}")["status"], "queued")     # sealed holdout queued once
        self.holdout_pass()
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            r2 = fleet.strategy_pass(self.db)
        self.assertIn((GOOD, "PAPER_TRADING", True), r2["promotions"])
        ok, why = promotion.trading_authorized(self.db, GOOD)
        self.assertTrue(ok, why)
        r = self.run_paper()["results"][GOOD]
        self.assertEqual(r["status"], "ok")
        filled = [o["symbol"] for o in r["orders"] if o["status"] == "filled"]
        self.assertEqual(len(filled), 6)                                      # 3 long, 3 short (k=3)
        self.assertTrue(r["reconciled"])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM transitions WHERE exp_id=? AND actor LIKE 'human:%'",
                                     GOOD)[0], 0)                              # no per-strategy human click


class D_DataAndHealthFailuresStopNewExposure(Base):
    def setUp(self):
        super().setUp()
        self.promoted()

    def test_stale_market_data_pauses_without_orders(self):
        r = self.run_paper(SAT, feed(SAT - 5 * HOUR))["results"][GOOD]
        self.assertEqual(r["status"], "paused")
        self.assertEqual(self.orders(), 0)

    def test_missing_market_data_pauses_without_orders(self):
        def broken(path):
            raise OSError("network down")
        self.assertEqual(self.run_paper(SAT, broken)["results"][GOOD]["status"], "paused")
        self.assertEqual(self.orders(), 0)

    def test_missing_onchain_data_pauses_without_orders(self):
        def broken(url):
            raise OSError("coinmetrics down")
        self.assertEqual(self.run_paper(SAT, cm=broken)["results"][GOOD]["status"], "paused")
        self.assertEqual(self.orders(), 0)

    def test_invalid_book_is_refused_by_the_engine(self):
        eng = PaperEngine(self.db, lambda: SAT)
        eng.start(GOOD, 10_000.0, paper_runner.cost_model())
        crossed = Book(ts=SAT, bids=((101, 10),), asks=((100, 10),))
        self.assertEqual(eng.submit_taker(GOOD, "x1", "ADAUSDT", "buy", 1, crossed)["status"], "refused")
        stale = Book(ts=SAT - 3600, bids=((99.9, 10),), asks=((100.1, 10),))
        self.assertEqual(eng.submit_taker(GOOD, "x2", "ADAUSDT", "buy", 1, stale)["status"], "refused")
        self.assertEqual(self.orders(), 0)

    def test_supervisor_timeout_blocks_runner_and_direct_engine_calls(self):
        supervised(self.db, SAT - 3600)                                      # stale heartbeat
        self.assertTrue(self.run_paper()["blocked"])
        eng = PaperEngine(self.db, lambda: SAT)
        eng.start(GOOD, 10_000.0, paper_runner.cost_model())
        r = eng.submit_taker(GOOD, "direct|1", "ADAUSDT", "buy", 1, self.book())
        self.assertEqual(r["status"], "refused")
        self.assertIn("supervisor", r["reason"])
        supervised(self.db, SAT, status="stopped")
        self.assertEqual(eng.submit_taker(GOOD, "direct|2", "ADAUSDT", "buy", 1, self.book())["status"], "refused")
        self.assertEqual(self.orders(), 0)

    def test_accounting_mismatch_fails_closed_and_blocks_promotion(self):
        self.run_paper()
        self.db.append("sim_fills", order_id="ghost", exp_id=GOOD, ts=int(SAT), instrument="ADAUSDT", side="buy",
                       liquidity="taker", mid=100.0, book_ts=SAT, fill_id="ghost|0", px=100.0, qty=1.0, fee=0.0,
                       slippage=0.0)                                         # a fill without an order
        supervised(self.db, SAT + HOUR)
        self.run_paper(SAT + HOUR, feed(SAT + HOUR))
        self.assertTrue(Risk(self.db).fail_closed())
        before = self.orders()
        supervised(self.db, SAT + 2 * HOUR)
        self.assertEqual(self.run_paper(SAT + 2 * HOUR, feed(SAT + 2 * HOUR))["results"][GOOD]["status"], "fail_closed")
        self.assertEqual(self.orders(), before)
        self.screen_passed("E_mvrv_value_p3b")
        self.assertIn("lab not FAIL_CLOSED", promotion.decide(self.db, "E_mvrv_value_p3b", SAT + 2 * HOUR)["closed"])

    def test_risk_breach_pauses_and_blocks_new_exposure(self):
        self.run_paper()
        Risk(self.db, lambda: SAT).pause(GOOD, "drawdown", 0.3, 0.2, "test breach")
        self.assertEqual(lifecycle.state(self.db, GOOD), "PAUSED")
        self.assertFalse(promotion.trading_authorized(self.db, GOOD)[0])
        n = self.orders()
        supervised(self.db, SAT + HOUR)
        self.run_paper(SAT + HOUR, feed(SAT + HOUR))
        self.assertEqual(self.orders(), n)
        eng = PaperEngine(self.db, lambda: SAT + HOUR)
        self.assertEqual(eng.submit_taker(GOOD, "direct|p", "ADAUSDT", "buy", 1, self.book(SAT + HOUR))["status"],
                         "refused")


class E_ForgedExpiredMismatchedApprovals(Base):
    def forged(self, eid, actor, evidence, from_state="VALIDATED"):
        self.experiment(eid, "mvrv_value", "VALIDATED", "PASS (holdout): paper-eligible", label="VALIDATION")
        self.db.append("transitions", exp_id=eid, ts=0, from_state=from_state, to_state="PAPER_TRADING", actor=actor,
                       reason="forged paper approval", evidence=evidence)

    def assert_no_trade(self, eid):
        ok, why = promotion.trading_authorized(self.db, eid)
        self.assertFalse(ok)
        self.assertEqual(self.run_paper()["results"][eid]["status"], "not authorized")
        with self.assertRaises(lifecycle.LifecycleError):
            PaperEngine(self.db).start(eid, 10_000.0, paper_runner.cost_model())
        self.assertEqual(self.orders(eid), 0)
        return why

    def test_status_field_alone_is_not_an_approval(self):
        self.forged("E_f1", "system:somebody", {})
        self.assert_no_trade("E_f1")

    def test_human_name_without_a_used_approval_code_is_forged(self):
        self.forged("E_f2", "human:mallory", {})
        self.assertIn("approval code", self.assert_no_trade("E_f2"))

    def test_approval_code_of_another_experiment_is_rejected(self):
        approve_paper(self.db, "E_other")
        aid = self.db.one("SELECT id FROM approvals WHERE exp_id='E_other'")[0]
        self.forged("E_f3", "human:fixture", {"approval_id": aid})
        self.assert_no_trade("E_f3")

    def test_requested_but_never_confirmed_code_is_not_an_approval(self):
        aid = self.db.append("approvals", code_hash="h1", exp_id="E_f5", to_state="PAPER_TRADING", ts=0, expires_ts=900,
                             actor="human:fixture", reason="requested, never confirmed", evidence={})
        self.forged("E_f5", "human:fixture", {"approval_id": aid})
        self.assertIn("exactly once", self.assert_no_trade("E_f5"))

    def test_code_used_by_another_human_is_not_this_approval(self):
        aid = self.db.append("approvals", code_hash="h2", exp_id="E_f6", to_state="PAPER_TRADING", ts=0, expires_ts=900,
                             actor="human:alice", reason="requested by alice", evidence={})
        self.db.event("approval.used", "human:alice", "E_f6", {"approval_id": aid})
        self.forged("E_f6", "human:mallory", {"approval_id": aid})
        self.assert_no_trade("E_f6")

    def test_code_of_another_experiment_with_a_forged_use_marker_is_rejected(self):
        approve_paper(self.db, "E_other")
        aid = self.db.one("SELECT id FROM approvals WHERE exp_id='E_other'")[0]
        self.db.event("approval.used", "human:fixture", "E_f7", {"approval_id": aid})
        self.forged("E_f7", "human:fixture", {"approval_id": aid})
        self.assertIn("matching approval", self.assert_no_trade("E_f7"))

    def test_unused_decision_for_another_step_is_rejected(self):
        self.policy_on()
        self.screen_passed()
        early = promotion.decide(self.db, GOOD, SAT, execute=False)          # SCREEN_PASSED -> VALIDATION, unused
        promotion.decide(self.db, GOOD, SAT)
        self.holdout_pass()                                                   # now VALIDATED
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.policy_transition(self.db, GOOD, "PAPER_TRADING", promotion.ACTOR, "cite the early decision",
                                        {"decision_event_id": early["decision_event"],
                                         "committed_files": [promotion.SPEC]})
        self.assertEqual(lifecycle.state(self.db, GOOD), "VALIDATED")

    def test_a_decision_already_marked_used_cannot_promote(self):
        self.policy_on()
        self.experiment(GOOD, "mvrv_value", "VALIDATED", "PASS (holdout): paper-eligible", label="VALIDATION")
        d = promotion.decide(self.db, GOOD, SAT, execute=False)
        self.db.event("promotion.used", promotion.ACTOR, GOOD, {"decision_event_id": d["decision_event"]})
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.policy_transition(self.db, GOOD, "PAPER_TRADING", promotion.ACTOR, "second use of decision",
                                        {"decision_event_id": d["decision_event"], "committed_files": [promotion.SPEC]})
        self.assertEqual(lifecycle.state(self.db, GOOD), "VALIDATED")

    def test_hand_written_decision_by_another_actor_is_rejected(self):
        self.policy_on()
        dec = self.db.event("promotion.decision", "system:paper", "E_f4", {"from": "VALIDATED", "to": "PAPER_TRADING",
                                                                            "allowed": True})
        self.forged("E_f4", promotion.ACTOR, {"decision_event_id": dec})
        self.assert_no_trade("E_f4")
        self.experiment("E_f4b", "mvrv_value", "VALIDATED", "PASS (holdout): x", label="VALIDATION")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.policy_transition(self.db, "E_f4b", "PAPER_TRADING", "system:paper", "sneaky actor here",
                                        {"decision_event_id": dec})

    def test_decision_for_another_step_or_experiment_cannot_be_replayed(self):
        self.policy_on()
        self.screen_passed()
        d1 = promotion.decide(self.db, GOOD, SAT)                             # allowed, used for -> VALIDATION
        self.holdout_pass()
        with self.assertRaises(lifecycle.LifecycleError):                     # wrong step
            lifecycle.policy_transition(self.db, GOOD, "PAPER_TRADING", promotion.ACTOR, "replay old decision",
                                        {"decision_event_id": d1["decision_event"], "committed_files": [promotion.SPEC]})
        self.screen_passed("E_mvrv_value_p3x")
        with self.assertRaises(lifecycle.LifecycleError):                     # other experiment
            lifecycle.policy_transition(self.db, "E_mvrv_value_p3x", "VALIDATION", promotion.ACTOR, "borrowed decision",
                                        {"decision_event_id": d1["decision_event"], "committed_files": [promotion.SPEC]})
        d2 = promotion.decide(self.db, GOOD, SAT)
        self.assertEqual(lifecycle.state(self.db, GOOD), "PAPER_TRADING")
        with self.assertRaises(lifecycle.LifecycleError):                     # same decision twice
            lifecycle.policy_transition(self.db, GOOD, "PAPER_TRADING", promotion.ACTOR, "use it again please",
                                        {"decision_event_id": d2["decision_event"], "committed_files": [promotion.SPEC]})

    def test_stale_decision_is_refused(self):
        self.policy_on()
        self.experiment(GOOD, "mvrv_value", "VALIDATED", "PASS (holdout): paper-eligible", label="VALIDATION")
        d = promotion.decide(self.db, GOOD, SAT, execute=False)
        real = time.time
        with mock.patch("lab.lifecycle.time.time", lambda: real() + 120):
            with self.assertRaises(lifecycle.LifecycleError):
                lifecycle.policy_transition(self.db, GOOD, "PAPER_TRADING", promotion.ACTOR, "late use of decision",
                                            {"decision_event_id": d["decision_event"], "committed_files": [promotion.SPEC]})
        self.assertEqual(lifecycle.state(self.db, GOOD), "VALIDATED")

    def test_decision_for_another_spec_version_is_rejected(self):
        self.promoted()
        self.db.append("experiments", exp_id=GOOD, version=2, created_ts=1, mechanism_tag="m", fingerprint="changed",
                       spec_json={**pipeline.template_spec("mvrv_value")})
        self.assertIn("spec version", promotion.trading_authorized(self.db, GOOD)[1])

    def test_switching_the_policy_off_expires_automatic_approval_but_allows_reduction(self):
        self.promoted()
        self.run_paper()
        pos = self.positions()
        self.assertTrue(pos)
        promotion.set_policy(self.db, False, "human:test", "user switched automatic promotion off")
        self.assertIn("policy is off", promotion.trading_authorized(self.db, GOOD)[1])
        eng = PaperEngine(self.db, lambda: SAT)
        s, q = next(iter(pos.items()))
        self.assertEqual(eng.submit_taker(GOOD, "add|1", s, "buy" if q > 0 else "sell", 1, self.book())["status"],
                         "refused")
        self.assertEqual(eng.submit_taker(GOOD, "cut|1", s, "sell" if q > 0 else "buy", abs(q) / 2, self.book(),
                                          reduce_only=True)["status"], "filled")


class F_RestartRetryDuplicates(Base):
    def test_restart_and_duplicate_decisions_create_nothing_twice(self):
        self.promoted()
        for _ in range(3):
            promotion.step(self.db, SAT)                                     # duplicate decision passes
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            self.assertEqual(fleet.strategy_pass(self.db)["promotions"], [])
        self.run_paper()
        n = self.orders(GOOD)
        self.assertGreater(n, 0)
        self.db.close()                                                       # restart: new connection, same hour
        self.db = DB(self.path)
        supervised(self.db, SAT + 60)
        promotion.step(self.db, SAT + 60)
        self.run_paper(SAT + 60, feed(SAT))
        self.assertEqual(self.orders(GOOD), n)
        one = lambda q: self.db.one(q, GOOD)[0]  # noqa: E731
        self.assertEqual(one("SELECT COUNT(*) FROM events WHERE kind='paper.started' AND exp_id=?"), 1)
        self.assertEqual(one("SELECT COUNT(*) FROM transitions WHERE exp_id=? AND to_state='PAPER_TRADING'"), 1)
        self.assertEqual(one("SELECT COUNT(*) FROM events WHERE kind='promotion.used' AND exp_id=?"), 1)

    def test_holdout_job_is_enqueued_once(self):
        self.policy_on()
        self.screen_passed()
        promotion.decide(self.db, GOOD, SAT)
        for _ in range(3):
            pipeline.enqueue_holdouts(self.db)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM jobs WHERE job_id=?", f"holdout|{GOOD}")[0], 1)

    def test_partial_fetch_failure_places_nothing(self):
        self.promoted()
        calls = {"n": 0}
        good = feed(SAT)

        def flaky(path):                                                      # depth fails after a few symbols
            if "depth" in path:
                calls["n"] += 1
                if calls["n"] == 4:
                    raise OSError("connection reset")
            return good(path)
        self.assertEqual(self.run_paper(SAT, flaky)["results"][GOOD]["status"], "paused")
        self.assertEqual(self.orders(GOOD), 0)                               # fetch everything first, then trade
        self.run_paper()                                                      # paused stays paused until a human
        self.assertEqual(self.orders(GOOD), 0)

    def test_retried_order_id_is_idempotent(self):
        self.promoted()
        eng = PaperEngine(self.db, lambda: SAT)
        eng.start(GOOD, 10_000.0, paper_runner.cost_model())
        a = eng.submit_taker(GOOD, f"{GOOD}|1|ADAUSDT", "ADAUSDT", "buy", 1, self.book())
        b = eng.submit_taker(GOOD, f"{GOOD}|1|ADAUSDT", "ADAUSDT", "buy", 1, self.book())
        self.assertEqual(a["status"], "filled")
        self.assertEqual(self.orders(GOOD), 1)
        self.assertAlmostEqual(self.positions()["ADAUSDT"], 1.0)
        self.assertEqual(b["order_id"], a["order_id"])


class G_ShadowCannotInfluence(Base):
    def test_shadow_pnl_changes_no_formal_decision(self):
        self.policy_on()
        self.experiment(GOOD, "mvrv_value", "OBSERVATION", "OBSERVE (forward test): luck check pending")
        self.db.event("shadow.approved", "human:test", GOOD, {"reason": "shadow for research"})
        self.run_paper()                                                      # real shadow trades
        self.assertGreater(self.orders("SHADOW_" + GOOD), 0)
        self.db.append("sim_equity", exp_id="SHADOW_" + GOOD, ts=int(SAT) + 1, equity=99_999.0, cash=99_999.0,
                       exposure=0, peak=99_999.0, drawdown=0.0)               # an absurdly good shadow result
        counts = lambda: {k: self.db.one(f"SELECT COUNT(*) FROM {k} WHERE exp_id=?", GOOD)[0]  # noqa: E731
                          for k in ("results", "transitions", "trials")}
        before = counts()
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            self.assertEqual(fleet.strategy_pass(self.db)["promotions"], [])
        self.assertEqual(counts(), before)
        self.assertEqual(lifecycle.state(self.db, GOOD), "OBSERVATION")
        self.assertFalse(promotion.trading_authorized(self.db, GOOD)[0])
        self.assertEqual(self.orders(GOOD), 0)
        self.assertIsNone(self.db.one("SELECT 1 FROM events WHERE kind='promotion.decision'"))


class H_ClosingAfterRejection(Base):
    def setUp(self):
        super().setUp()
        self.promoted()
        self.run_paper()
        self.assertTrue(self.positions())

    def reject(self):
        rid = registry.record_result(self.db, GOOD, "PAPER", "FAIL (paper review): test", {}, {}, "system:t")
        lifecycle.auto_transition(self.db, GOOD, "REJECTED", "system:risk", "paper review failed", {"result_id": rid},
                                  guards=(registry.make_result_guard({"result_id": rid}),))

    def test_rejection_closes_every_position(self):
        self.reject()
        supervised(self.db, SAT + HOUR)
        out = self.run_paper(SAT + HOUR, feed(SAT + HOUR))["results"]
        self.assertEqual(out[GOOD]["status"], "closing")
        self.assertEqual(self.positions(), {})
        self.assertTrue(PaperEngine(self.db).reconcile(GOOD)["ok"])

    def test_closing_still_works_without_a_supervisor_and_under_fail_closed(self):
        self.reject()
        Risk(self.db).trip_fail_closed("reconciliation", "test")
        supervised(self.db, SAT - 3600)                                      # supervisor unknown
        out = self.run_paper(SAT + HOUR, feed(SAT + HOUR))
        self.assertTrue(out["blocked"])
        self.assertEqual(out["results"][GOOD]["status"], "closing")
        self.assertEqual(self.positions(), {})

    def test_retirement_closes_too(self):
        code = lifecycle.request_approval(self.db, GOOD, "RETIRED", "human:test", "retire after the review")
        lifecycle.confirm(self.db, code, "human:test")
        supervised(self.db, SAT + HOUR)
        self.run_paper(SAT + HOUR, feed(SAT + HOUR))
        self.assertEqual(self.positions(), {})


class I_AuditTrail(Base):
    def test_every_decision_names_its_gates_and_only_the_decision_function_can_promote(self):
        self.screen_passed()
        promotion.decide(self.db, GOOD, SAT)                                   # waiting (policy off): logged once
        promotion.decide(self.db, GOOD, SAT)
        rows = self.db.q("SELECT payload FROM events WHERE kind='promotion.decision' AND exp_id=?", GOOD)
        self.assertEqual(len(rows), 1)
        wait = json.loads(rows[0][0])
        self.assertEqual((wait["allowed"], wait["closed"]), (False, ["automatic promotion policy on (human-enabled)"]))
        self.assertEqual(set(wait["evidence"]), {"catalogue experiment (pre-registered template)",
                                                 "registered under PROTOCOL v3 (amendment 4a)", "lab not FAIL_CLOSED",
                                                 "supervisor healthy",
                                                 "latest result is a PASS (screen incl. luck check, or forward test)",
                                                 "a clean 2024 holdout is possible (amendment 1)",
                                                 "automatic promotion policy on (human-enabled)"})
        self.policy_on()
        d = promotion.decide(self.db, GOOD, SAT)
        tr = self.db.one("SELECT actor, evidence FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", GOOD)
        self.assertEqual(tr["actor"], promotion.ACTOR)
        self.assertEqual(json.loads(tr["evidence"])["decision_event_id"], d["decision_event"])
        p = json.loads(self.db.one("SELECT payload FROM events WHERE id=?", d["decision_event"])[0])
        self.assertTrue(p["allowed"])
        self.assertEqual((p["version"], p["fingerprint"], p["from"], p["to"]), (1, GOOD, "SCREEN_PASSED", "VALIDATION"))
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='promotion.used' AND exp_id=?", GOOD))
        with self.assertRaises(lifecycle.LifecycleError):
            promotion.set_policy(self.db, True, "system:bot", "automation may not enable itself")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM transitions WHERE actor='system:promotion'")[0], 1)
        chains, triggers = self.db.verify()
        self.assertTrue(triggers and all(b is None for _, b in chains.values()))

    def test_refused_orders_are_logged_with_the_reason(self):
        self.experiment("E_f", "mvrv_value", "VALIDATED", "PASS (holdout): x", label="VALIDATION")
        self.db.append("transitions", exp_id="E_f", ts=0, from_state="VALIDATED", to_state="PAPER_TRADING",
                       actor="system:somebody", reason="forged paper approval")
        self.run_paper()
        ev = self.db.one("SELECT payload FROM events WHERE kind='paper.not_authorized' AND exp_id='E_f'")
        self.assertIn("not a verifiable approval", json.loads(ev[0])["reason"])


if __name__ == "__main__":
    unittest.main()
