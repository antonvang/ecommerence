"""Reliability audit (Linux host): agent health is real task health, frozen parameters fail closed, and the
startup preflight refuses an unsafe start."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, fleet, jobs, lifecycle, paper_runner, pipeline, promotion, registry  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from tests.lab_fixtures import approve_paper, frozen, supervised  # noqa: E402
from tests.test_lab_paper_runner import SAT, feed  # noqa: E402
from tests.test_lab_promotion import cm_feed  # noqa: E402

GOOD = "E_mvrv_value_p3"


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labrel")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch.object(promotion.control, "resources", lambda *a, **k: {"ok": True})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class AgentHealth(Tmp):
    def agent(self, fn, every=60):
        return fleet.Agent("probe-1", "probe agent", every=every, fn=fn, db_path=self.path)

    def row(self):
        return dict(self.db.one("SELECT * FROM heartbeats WHERE worker='probe-1'"))

    def test_a_failing_periodic_agent_stays_failed_until_a_pass_succeeds(self):
        calls = {"n": 0}

        def fn(db):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise OSError("feed down")
            return {"done": True}
        a = self.agent(fn)
        a(self.db)                                                          # fails
        self.assertEqual((self.row()["status"], self.row()["ok"]), ("failed", 0))
        for _ in range(3):
            a(self.db)                                                      # waiting ticks keep the failure visible
        r = self.row()
        self.assertEqual(r["status"], "failed")
        self.assertIn("feed down", r["detail"])
        self.assertIn("feed down", r["last_error"])
        self.assertIsNone(r["last_ok_ts"])
        a.next_periodic = 0
        a(self.db)                                                          # fails again: same error logged once
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='agent.error'")[0], 1)
        a.next_periodic = 0
        a(self.db)                                                          # succeeds
        r = self.row()
        self.assertEqual((r["status"], r["ok"]), ("idle", 1))
        self.assertIsNotNone(r["last_ok_ts"])
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='agent.recovered'"))
        a(self.db)
        self.assertEqual(self.row()["status"], "idle")

    def test_failed_agents_show_red_in_the_dashboard_api(self):
        def fn(db):
            raise RuntimeError("cannot complete")
        a = self.agent(fn)
        supervised(self.db)
        a(self.db)
        a(self.db)
        with mock.patch.object(fleet, "ROLES", {"probe-1": "probe agent"}):
            out = {x["agent"]: x for x in command.agents(self.db)["agents"]}
        self.assertEqual(out["probe-1"]["status"], "failed")
        self.assertIn("cannot complete", out["probe-1"]["last_error"])
        self.assertNotIn("probe-1", [x["agent"] for x in command.agents(self.db)["agents"]
                                     if x["status"] in ("idle", "running")])

    def test_job_agent_records_last_success_and_last_error(self):
        jobs.enqueue(self.db, "data|E_x", "data", "E_x", {}, actor="system:t")
        a = fleet.Agent("data-9", "data agent", kinds=("data",), db_path=self.path)
        with mock.patch.dict(pipeline.HANDLERS, {"data": lambda db, job, w: (_ for _ in ()).throw(
                pipeline.StepError("no market"))}):
            a(self.db)
        r = dict(self.db.one("SELECT * FROM heartbeats WHERE worker='data-9'"))
        self.assertIn("no market", r["last_error"])
        jobs.enqueue(self.db, "data|E_y", "data", "E_y", {}, actor="system:t")
        with mock.patch.dict(pipeline.HANDLERS, {"data": lambda db, job, w: {"ok": True}}):
            a(self.db)
        self.assertIsNotNone(self.db.one("SELECT last_ok_ts FROM heartbeats WHERE worker='data-9'")[0])


class FrozenParameters(Tmp):
    def setUp(self):
        super().setUp()
        supervised(self.db, SAT)
        self.db.append("experiments", exp_id=GOOD, version=1, created_ts=0, mechanism_tag="m", fingerprint=GOOD,
                       spec_json={**pipeline.template_spec("mvrv_value")})
        approve_paper(self.db, GOOD)
        frozen(self.db, GOOD, "cost", {"selected": 0})
        frozen(self.db, GOOD, "backtest", {"variants": [{"variant": 0, "params": {"mode": "level", "k": 3},
                                                         "fit": None, "positions": {}}]})

    def run_paper(self, now=SAT):
        return paper_runner.run(self.db, feed(now), now, cm_get=cm_feed(now))

    def apath(self, name):
        return os.path.join(pipeline.ARTIFACTS, GOOD, f"{name}.json")

    def test_intact_parameters_trade(self):
        self.assertEqual(self.run_paper()["results"][GOOD]["status"], "ok")

    def test_missing_parameters_block_without_orders_or_regeneration(self):
        os.remove(self.apath("backtest"))
        r = self.run_paper()["results"][GOOD]
        self.assertEqual(r["status"], "blocked")
        self.assertIn("missing", r["reason"])
        self.assertFalse(os.path.exists(self.apath("backtest")))           # never regenerated
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='paper.blocked' AND exp_id=?", GOOD))

    def test_changed_parameters_block(self):
        with open(self.apath("cost"), "w") as f:
            json.dump({"selected": 0, "note": "edited by hand"}, f)
        r = self.run_paper()["results"][GOOD]
        self.assertEqual(r["status"], "blocked")
        self.assertIn("differs", r["reason"])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)

    def test_unrecorded_parameters_block(self):
        pipeline.save_artifact("E_mvrv_value_p3", "cost", {"selected": 0})   # same bytes, but recorded hash is
        self.db.event("job.done", "system:fixture", GOOD, {"job_id": f"cost|{GOOD}", "kind": "cost"})  # the newest
        with mock.patch.object(pipeline, "recorded_sha", lambda db, e, n: None):
            self.assertEqual(self.run_paper()["results"][GOOD]["status"], "blocked")

    def test_paper_agent_is_failed_while_a_ledger_is_blocked_and_other_ledgers_still_close(self):
        self.run_paper()
        self.assertTrue(PaperEngine(self.db).ledger(GOOD)["positions"])
        other = "E_mvrv_value_p3b"
        self.db.append("experiments", exp_id=other, version=1, created_ts=0, mechanism_tag="m", fingerprint=other,
                       spec_json={**pipeline.template_spec("mvrv_value")})
        approve_paper(self.db, other)
        os.makedirs(os.path.join(pipeline.ARTIFACTS, other), exist_ok=True)   # no frozen parameters at all
        rid = registry.record_result(self.db, GOOD, "PAPER", "FAIL (paper review): test", {}, {}, "system:t")
        lifecycle.auto_transition(self.db, GOOD, "REJECTED", "system:risk", "paper review failed", {"result_id": rid},
                                  guards=(registry.make_result_guard({"result_id": rid}),))
        supervised(self.db, SAT + 3600)
        real_run = paper_runner.run
        offline = lambda db: real_run(db, feed(SAT + 3600), SAT + 3600, cm_get=cm_feed(SAT + 3600))  # noqa: E731
        with mock.patch.object(paper_runner, "run", offline):              # no network in tests
            with self.assertRaises(fleet.AgentDegraded) as cm:
                fleet.paper_pass(self.db)
        self.assertIn(other, str(cm.exception))
        self.assertEqual(PaperEngine(self.db).ledger(GOOD)["positions"], {})  # the rejected one was still closed

    def test_job_done_chains_the_artifact_hash(self):
        jobs.enqueue(self.db, "cost|E_z", "cost", "E_z", {}, actor="system:t")
        j = jobs.claim(self.db, "cost-1", ["cost"])
        art = pipeline.save_artifact("E_z", "cost", {"selected": 0})
        jobs.complete(self.db, j["job_id"], "cost-1", {"selected": 0, "artifact": art})
        p = json.loads(self.db.one("SELECT payload FROM events WHERE kind='job.done' AND exp_id='E_z'")[0])
        self.assertEqual(p["artifact_sha256"], art["sha256"])
        self.assertEqual(pipeline.recorded_sha(self.db, "E_z", "cost"), art["sha256"])

    def test_holdout_and_forward_test_refuse_unverified_parameters(self):
        os.remove(self.apath("cost"))
        with self.assertRaises(pipeline.ArtifactError):
            pipeline.frozen_variant(self.db, GOOD)
        self.assertTrue(issubclass(pipeline.ArtifactError, pipeline.StepError))   # not retried by the job agents


class Preflight(Tmp):
    def setUp(self):
        super().setUp()
        self.p.pop(1).stop()                                                # real disk and RAM figures
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.p.append(mock.patch("lab.engine.data.CACHE", self.tmp))
        self.p[-1].start()
        self.db.append("experiments", exp_id=GOOD, version=1, created_ts=0, mechanism_tag="m", fingerprint=GOOD,
                       spec_json={**pipeline.template_spec("mvrv_value")})
        self.db.append("transitions", exp_id=GOOD, ts=0, from_state=None, to_state="OBSERVATION", actor="fixture",
                       reason="fixture: on the observation list")
        frozen(self.db, GOOD, "cost", {"selected": 0})
        frozen(self.db, GOOD, "backtest", {"variants": [{"variant": 0, "params": {"k": 3}, "fit": None,
                                                         "positions": {}}]})

    def result(self):
        from lab import preflight
        return {name: (ok, detail) for name, ok, detail in preflight.checks(self.path, self.port)}

    def test_ok_when_everything_is_in_place(self):
        r = self.result()
        self.assertTrue(all(ok for ok, _ in r.values()), r)

    def test_refuses_while_another_lab_holds_the_lock(self):
        from lab.supervisor import acquire_lock, release_lock
        lock = acquire_lock(os.path.join(self.tmp, "lab.lock"))
        try:
            self.assertFalse(self.result()["no other lab running"][0])
        finally:
            release_lock(lock)
        self.assertTrue(self.result()["no other lab running"][0])

    def test_refuses_when_the_dashboard_port_is_taken(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", self.port))
        s.listen(1)
        try:
            self.assertFalse(self.result()["dashboard port free"][0])
        finally:
            s.close()

    def test_refuses_missing_frozen_parameters(self):
        os.remove(os.path.join(pipeline.ARTIFACTS, GOOD, "backtest.json"))
        ok, detail = self.result()["frozen parameters verified"]
        self.assertFalse(ok)
        self.assertIn(GOOD, detail)

    def test_refuses_without_a_database(self):
        from lab import preflight
        r = preflight.checks(os.path.join(self.tmp, "absent", "lab.db"), self.port)
        self.assertEqual([(n, ok) for n, ok, _ in r][-1], ("lab database present", False))

    def test_cli_exit_code(self):
        from lab.__main__ import main
        lines = []
        self.assertEqual(main(["--db", self.path, "preflight", "--port", str(self.port)], out=lines.append), 0)
        os.remove(os.path.join(pipeline.ARTIFACTS, GOOD, "cost.json"))
        self.assertEqual(main(["--db", self.path, "preflight", "--port", str(self.port)], out=lines.append), 1)
        self.assertIn("PREFLIGHT FAILED", lines[-1])


if __name__ == "__main__":
    unittest.main()
