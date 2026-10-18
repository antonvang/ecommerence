"""Integration tests for automatic promotion (research/PROTOCOL_V3.md amendment 4), cases A-G of the brief."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, lifecycle, paper_runner, pipeline, promotion, registry  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.test_lab_paper_runner import SAT, feed  # noqa: E402

HOUR = 3600


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labpromo")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.patches = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                        mock.patch.object(promotion.control, "resources", lambda *a, **k: {"ok": True})]
        for p in self.patches:
            p.start()
        self.beat(SAT)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def beat(self, ts, status="running"):
        self.db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status) VALUES('supervisor',?,1,1,'',?) "
                            "ON CONFLICT(worker) DO UPDATE SET ts=excluded.ts, status=excluded.status", (int(ts), status))

    def experiment(self, eid, template, state, verdict=None, label="EXPLORATORY"):
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint=eid,
                       spec_json={**pipeline.template_spec(template)})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=state, actor="fixture",
                       reason="fixture: experiment state")
        if verdict:
            registry.record_result(self.db, eid, label, verdict, {}, {}, "system:test")
        pipeline.save_artifact(eid, "cost", {"selected": 1})
        pipeline.save_artifact(eid, "backtest", {"variants": [
            {"variant": 0, "params": {"mode": "flat_weekend"}, "fit": None, "positions": {}},
            {"variant": 1, "params": {"mode": "weekend_only"}, "fit": None, "positions": {}}]})

    def policy_on(self):
        promotion.set_policy(self.db, True, "human:test", "user enabled automatic promotion in the test")

    def run_paper(self, now=SAT, get=None):
        return paper_runner.run(self.db, get or feed(now), now)

    def orders(self, ledger=None):
        if ledger:
            return self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", ledger)[0]
        return self.db.one("SELECT COUNT(*) FROM sim_orders")[0]


class A_RejectedCannotTrade(Base):
    def test_rejected_strategy_is_not_promoted_and_cannot_trade(self):
        self.policy_on()
        self.experiment("E_rej", "day_of_week", "REJECTED", "REJECTED at validation: failed net Sharpe > buy-and-hold")
        self.assertFalse(promotion.decide(self.db, "E_rej", SAT)["applicable"])
        self.assertEqual(lifecycle.state(self.db, "E_rej"), "REJECTED")
        self.assertFalse(promotion.trading_authorized(self.db, "E_rej")[0])
        self.run_paper()
        self.assertEqual(self.orders(), 0)


class B_WaitingCannotTrade(Base):
    def test_closed_gates_wait_and_never_trade(self):
        self.experiment("E_obs", "mvrv_value", "OBSERVATION", "OBSERVE (forward test): luck check pending")
        self.experiment("E_nohold", "vrp_timing", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        self.experiment("E_pol", "day_of_week", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        d = promotion.decide(self.db, "E_pol", SAT)                       # policy still off
        self.assertFalse(d["allowed"])
        self.assertIn("automatic promotion policy on (human-enabled)", d["closed"])
        self.policy_on()
        d = promotion.decide(self.db, "E_nohold", SAT)
        self.assertFalse(d["allowed"])
        self.assertIn("a clean 2024 holdout is possible (amendment 1)", d["closed"])
        self.assertFalse(promotion.decide(self.db, "E_obs", SAT)["applicable"])        # forward test not done
        self.assertEqual((lifecycle.state(self.db, "E_obs"), lifecycle.state(self.db, "E_nohold")),
                         ("OBSERVATION", "SCREEN_PASSED"))
        self.run_paper()
        self.assertEqual(self.orders(), 0)


class C_FullPassTradesWithoutAClick(Base):
    def test_hypothesis_to_paper_trading_automatically(self):
        self.policy_on()
        self.experiment("E_ok", "day_of_week", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            fleet.strategy_pass(self.db)                                   # the strategy agent's normal pass
        self.assertEqual(lifecycle.state(self.db, "E_ok"), "VALIDATION")
        self.assertTrue(self.db.one("SELECT 1 FROM jobs WHERE job_id='holdout|E_ok'"))   # holdout queued, once
        # the holdout job records its result and decides through the existing automatic edge
        rid = registry.record_result(self.db, "E_ok", "VALIDATION", "PASS (holdout): paper-eligible", {}, {}, "system:t")
        lifecycle.auto_transition(self.db, "E_ok", "VALIDATED", "system:validation-1", "holdout passed",
                                  {"result_id": rid}, guards=(registry.make_result_guard({"result_id": rid}),))
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            fleet.strategy_pass(self.db)
        self.assertEqual(lifecycle.state(self.db, "E_ok"), "PAPER_TRADING")
        ok, why = promotion.trading_authorized(self.db, "E_ok")
        self.assertTrue(ok, why)
        r = self.run_paper()["results"]["E_ok"]
        self.assertEqual(r["status"], "ok")
        self.assertGreater(self.orders("E_ok"), 0)
        self.assertTrue(r["reconciled"])
        humans = self.db.one("SELECT COUNT(*) FROM transitions WHERE exp_id='E_ok' AND actor LIKE 'human:%'")[0]
        self.assertEqual(humans, 0)                                        # no per-strategy click


class D_ShadowCannotPromote(Base):
    def test_shadow_profits_change_nothing(self):
        self.policy_on()
        self.experiment("E_mv", "mvrv_value", "OBSERVATION", "OBSERVE (forward test): luck check pending")
        self.db.event("shadow.approved", "human:test", "E_mv", {"reason": "shadow for research"})
        PaperEngine(self.db).start("SHADOW_E_mv", 10_000.0, paper_runner.cost_model())
        self.db.append("sim_equity", exp_id="SHADOW_E_mv", ts=int(SAT), equity=99_999.0, cash=99_999.0, exposure=0,
                       peak=99_999.0, drawdown=0.0)                          # an absurdly good shadow result
        before = self.db.one("SELECT COUNT(*) FROM results WHERE exp_id='E_mv'")[0]
        with mock.patch.object(promotion, "supervisor_ok", lambda db, now=None: True):
            fleet.strategy_pass(self.db)
        self.assertEqual(lifecycle.state(self.db, "E_mv"), "OBSERVATION")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM results WHERE exp_id='E_mv'")[0], before)
        self.assertFalse(promotion.trading_authorized(self.db, "E_mv")[0])
        self.assertFalse(promotion.decide(self.db, "E_mv", SAT)["applicable"])


class E_RestartNoDuplicates(Base):
    def test_restart_keeps_one_instance_and_no_duplicate_orders(self):
        self.policy_on()
        self.experiment("E_ok", "day_of_week", "VALIDATED", "PASS (holdout): paper-eligible", label="VALIDATION")
        promotion.decide(self.db, "E_ok", SAT)
        self.assertEqual(lifecycle.state(self.db, "E_ok"), "PAPER_TRADING")
        self.run_paper()
        n = self.orders("E_ok")
        self.db.close()                                                    # "restart": new connection, same hour
        self.db = DB(self.path)
        self.beat(SAT + 60)
        promotion.decide(self.db, "E_ok", SAT + 60)                        # not applicable anymore: no second promotion
        self.run_paper(SAT + 60, feed(SAT))
        self.assertEqual(self.orders("E_ok"), n)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='paper.started' AND exp_id='E_ok'")[0], 1)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM transitions WHERE exp_id='E_ok' AND to_state='PAPER_TRADING'")[0], 1)


class F_FailuresStopNewTrades(Base):
    def setUp(self):
        super().setUp()
        self.policy_on()
        self.experiment("E_ok", "day_of_week", "VALIDATED", "PASS (holdout): paper-eligible", label="VALIDATION")
        promotion.decide(self.db, "E_ok", SAT)

    def test_stale_data_pauses(self):
        r = self.run_paper(SAT, feed(SAT - 5 * HOUR))["results"]["E_ok"]
        self.assertEqual(r["status"], "paused")
        self.assertEqual(self.orders(), 0)

    def test_fail_closed_blocks_promotion_and_trading(self):
        self.experiment("E_next", "day_of_week", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        Risk(self.db).trip_fail_closed("reconciliation", "test")
        self.assertIn("lab not FAIL_CLOSED", promotion.decide(self.db, "E_next", SAT)["closed"])
        self.run_paper()
        self.assertEqual(self.orders(), 0)

    def test_unknown_supervisor_state_blocks_everything(self):
        self.beat(SAT - 3600)                                              # stale heartbeat
        self.assertTrue(self.run_paper()["blocked"])
        self.assertEqual(self.orders(), 0)

    def test_unverifiable_approval_blocks_entries(self):
        self.db.append("transitions", exp_id="E_fake", ts=0, from_state=None, to_state="PAPER_TRADING",
                       actor="system:somebody", reason="forged promotion without a decision")
        self.db.append("experiments", exp_id="E_fake", version=1, created_ts=0, mechanism_tag="m", fingerprint="x",
                       spec_json={**pipeline.template_spec("day_of_week")})
        self.assertFalse(promotion.trading_authorized(self.db, "E_fake")[0])
        out = self.run_paper()["results"]
        self.assertEqual(out["E_fake"]["status"], "not authorized")
        self.assertEqual(self.orders("E_fake"), 0)

    def test_rejection_after_paper_closes_positions(self):
        self.run_paper()
        self.assertTrue(PaperEngine(self.db).ledger("E_ok")["positions"])
        rid = registry.record_result(self.db, "E_ok", "PAPER", "FAIL (paper review): test", {}, {}, "system:t")
        lifecycle.auto_transition(self.db, "E_ok", "REJECTED", "system:risk", "paper review failed", {"result_id": rid},
                                  guards=(registry.make_result_guard({"result_id": rid}),))
        self.beat(SAT + HOUR)
        out = self.run_paper(SAT + HOUR, feed(SAT + HOUR))["results"]
        self.assertEqual(out["E_ok"]["status"], "closing")
        self.assertEqual(PaperEngine(self.db).ledger("E_ok")["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile("E_ok")["ok"])


class G_AuditTrail(Base):
    def test_every_decision_is_traceable_and_only_the_decision_function_can_promote(self):
        self.experiment("E_ok", "day_of_week", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        promotion.decide(self.db, "E_ok", SAT)                             # waiting (policy off): logged once
        promotion.decide(self.db, "E_ok", SAT)
        waits = self.db.q("SELECT payload FROM events WHERE kind='promotion.decision' AND exp_id='E_ok'")
        self.assertEqual(len(waits), 1)
        self.policy_on()
        d = promotion.decide(self.db, "E_ok", SAT)
        self.assertTrue(d["allowed"])
        tr = self.db.one("SELECT actor, evidence FROM transitions WHERE exp_id='E_ok' ORDER BY id DESC LIMIT 1")
        ev = json.loads(tr["evidence"])
        self.assertEqual(tr["actor"], "system:promotion")
        self.assertEqual(ev["decision_event_id"], d["decision_event"])
        p = json.loads(self.db.one("SELECT payload FROM events WHERE id=?", d["decision_event"])[0])
        self.assertTrue(p["allowed"])
        self.assertIn("latest result is a PASS (screen incl. luck check, or forward test)", p["evidence"])
        # no other actor, and no transition without an allowed decision
        self.experiment("E_x", "day_of_week", "SCREEN_PASSED", "PASS (screen): all validation gates passed")
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.policy_transition(self.db, "E_x", "VALIDATION", "system:paper", "sneaky", {})
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.policy_transition(self.db, "E_x", "VALIDATION", "system:promotion", "no decision cited",
                                        {"decision_event_id": d["decision_event"]})          # decision of another exp
        with self.assertRaises(lifecycle.LifecycleError):
            promotion.set_policy(self.db, True, "system:bot", "automation may not enable itself")
        self.assertTrue(self.db.verify()[1])


if __name__ == "__main__":
    unittest.main()
