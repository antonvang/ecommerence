"""Mission 6 command-center API: numbers match the backend, honest offline/stale agents, guarded fleet controls,
stage-tagged live events, pagination and filters, S7 gate refusal."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, control, fleet, jobs, web  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.gates import s7_gate  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def seed(db, now):
    for i in range(30):
        jobs.enqueue(db, f"backtest|E{i}", "backtest", f"E{i}", now=now)
    for i in range(5):
        j = jobs.claim(db, "backtest-1", ["backtest"], now=now)
        jobs.complete(db, j["job_id"], "backtest-1", {"ok": 1}, now=now + 1)
    jobs.claim(db, "backtest-2", ["backtest"], now=now)
    for i in range(12):
        db.append("trials", exp_id="E1", ts=int(now) - 60, variant=i, split="train", sharpe_daily=0.01 * i, n_days=200,
                  net_total=0.1, params={"k": i})
    db.append("trials", exp_id="E1", ts=int(now) - 4000, variant=99, split="train", sharpe_daily=0.0, n_days=200,
              net_total=0.0, params={})
    db.append("experiments", exp_id="E_a_p1", version=1, created_ts=0, mechanism_tag="m", fingerprint="f",
              spec_json={"template": "day_of_week", "instrument": "binance_usdm_perps_8alt"})
    db.append("transitions", exp_id="E_a_p1", ts=0, from_state=None, to_state="REJECTED", actor="fixture",
              reason="fixture rejection: failed validation gates")


class ReadModels(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        self.now = time.time()
        seed(self.db, self.now)

    def test_kpis_match_backend(self):
        k = command.kpis(self.db, 900, self.now + 2)
        c = jobs.counts(self.db)
        self.assertEqual(k["jobs"], c)
        self.assertEqual(k["queued_jobs"], c["queued"] + c["blocked"])
        self.assertEqual(k["tests_running"], 1)
        self.assertEqual(k["tests_completed"]["variant_evaluations"], 13)
        self.assertAlmostEqual(k["tests_per_min"], 12 / 15)               # only the 12 trials inside the window
        self.assertAlmostEqual(k["jobs_per_min"], 5 / 15)
        self.assertIsNone(k["real_account_profit"]["value"])

    def test_agents_offline_without_supervisor_and_running_with_it(self):
        db = self.db
        a = fleet.Agent("backtest-1", "Backtest agent", kinds=("backtest",))
        a.counters = {"tasks_done": 5, "errors": 0, "retries": 0}
        a.beat(db, "running", current_job="backtest|E9", current_exp="E9", next_action="finish")
        r = command.agents(db)
        self.assertEqual(r["agents"][0]["status"], "offline")             # no supervisor heartbeat
        self.assertIsNone(r["agents"][0]["current_job"])
        db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status) VALUES('supervisor',?,1,1,'',"
                       "'running')", (int(time.time()),))
        jobs.enqueue(db, "backtest|E9", "backtest", "E9")
        r = command.agents(db)
        x = r["agents"][0]
        self.assertEqual((x["status"], x["current_job"], x["stage"], x["tasks_done"]), ("running", "backtest|E9",
                                                                                       "RUNNING", 5))
        db.con.execute("UPDATE heartbeats SET ts=ts-1000 WHERE worker='backtest-1'")
        db.con.execute("UPDATE heartbeats SET stale_after=60 WHERE worker='backtest-1'")
        self.assertEqual(command.agents(db)["agents"][0]["status"], "stale")

    def test_pagination_and_filters(self):
        j = command.job_list(self.db, page=2, size=10)
        self.assertEqual((j["total"], j["pages"], len(j["items"]), j["page"]), (30, 3, 10, 2))
        self.assertEqual(command.job_list(self.db, status="done")["total"], 5)
        e = command.experiments(self.db, status="REJECTED")
        self.assertEqual(e["total"], 1)
        self.assertEqual(e["items"][0]["stage"], "REJECTED")
        self.assertIn("fixture rejection", e["items"][0]["rejection_reason"])
        self.assertEqual(command.experiments(self.db, market="prediction markets")["total"], 0)
        self.assertEqual(command.rejected(self.db)["total"], 1)

    def test_paper_view_without_strategies_is_honest(self):
        p = command.paper_view(self.db)
        self.assertEqual(p["strategies"], [])
        self.assertIsNone(p["real_account_profit"]["value"])

    def test_stage_mapping_follows_jobs(self):
        db = DB(":memory:")
        db.append("experiments", exp_id="E_x_p1", version=1, created_ts=0, mechanism_tag="m", fingerprint="f",
                  spec_json={})
        db.append("transitions", exp_id="E_x_p1", ts=0, from_state=None, to_state="SCREENING", actor="t", reason="t")
        jobs.enqueue(db, "data|E_x_p1", "data", "E_x_p1")
        jobs.enqueue(db, "cost|E_x_p1", "cost", "E_x_p1", depends_on=["data|E_x_p1"])
        self.assertEqual(command.stage(db, "E_x_p1", "SCREENING")[0], "QUEUED")
        j = jobs.claim(db, "data-1", ["data"])
        self.assertEqual(command.stage(db, "E_x_p1", "SCREENING")[:2], ("RUNNING", "running"))
        jobs.complete(db, j["job_id"], "data-1")
        jobs.claim(db, "cost-1", ["cost"])
        self.assertEqual(command.stage(db, "E_x_p1", "SCREENING")[0], "COST_CHECK")


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "lab.db")
        db = DB(cls.path)
        seed(db, time.time())
        db.close()
        cls.srv = web.serve(cls.path, 18790)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.closing = True
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, p):
        with urllib.request.urlopen(self.base + p, timeout=10) as r:
            return json.loads(r.read())

    def post(self, p, body, token=True):
        req = urllib.request.Request(self.base + p, json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"X-Lab-Token": self.srv.token} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_endpoints_agree_with_database(self):
        k = self.get("/api/kpis")
        db = DB(self.path)
        try:
            self.assertEqual(k["jobs"], jobs.counts(db))
            self.assertEqual(self.get("/api/jobs?size=7&page=1")["total"], db.one("SELECT COUNT(*) FROM jobs")[0])
            self.assertEqual(self.get("/api/distribution")["trials"].__len__(), db.one("SELECT COUNT(*) FROM trials")[0])
        finally:
            db.close()
        self.assertEqual(self.get("/api/v2/experiments?status=REJECTED")["total"], 1)
        self.assertIn("agents", self.get("/api/agents"))
        self.assertEqual(self.get("/api/paper2")["strategies"], [])

    def test_fleet_controls_are_guarded_idempotent_and_audited(self):
        code, _ = self.post("/api/control/fleet", {"action": "pause", "reason": "pause for the test run"}, token=False)
        self.assertEqual(code, 403)
        code, r = self.post("/api/control/fleet", {"action": "pause", "reason": "short"})
        self.assertEqual(code, 400)
        code, r = self.post("/api/control/fleet", {"action": "pause", "reason": "pause for the test run"})
        self.assertEqual((code, r["changed"], r["control"]["paused"]), (200, True, True))
        code, r = self.post("/api/control/fleet", {"action": "pause", "reason": "pause for the test run"})
        self.assertFalse(r["changed"])                                     # idempotent
        code, r = self.post("/api/control/fleet", {"action": "resume", "reason": "resume after the test"})
        self.assertFalse(r["control"]["paused"])
        db = DB(self.path)
        try:
            self.assertEqual(db.one("SELECT COUNT(*) FROM events WHERE kind='system.paused' AND actor LIKE "
                                    "'human:%@dashboard'")[0], 1)
        finally:
            db.close()

    def test_stream_events_carry_stage(self):
        req = urllib.request.urlopen(self.base + "/api/stream", timeout=10)
        json.loads(req.readline().decode().removeprefix("data: "))
        req.readline()
        db = DB(self.path)
        jobs.enqueue(db, "cost|E_s", "cost", "E_s")
        jobs.claim(db, "cost-1", ["cost"])
        db.close()
        msg = json.loads(req.readline().decode().removeprefix("data: "))
        started = [e for e in msg["new_events"] if e["kind"] == "job.started"]
        self.assertEqual(started[0]["stage"], "COST_CHECK")
        self.assertEqual(started[0]["actor"], "cost-1")
        req.close()

    def test_page_is_the_command_center(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            html = r.read().decode()
        for s in ("Mars Command Center", "Mission Control", "PAPER ONLY", "ikke tilgængelig", "Real account profit"):
            self.assertIn(s, html)
        self.assertIn(self.srv.token, html)


class Gate(unittest.TestCase):
    def test_s7_gate_closed_and_installer_refuses(self):
        db = DB(":memory:")
        self.assertFalse(s7_gate(db)["open"])
        ps = os.path.join(HERE, "lab", "automation", "s7_install_task.ps1")
        self.assertTrue(os.path.exists(ps))
        with open(ps, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("gate --require", src)                              # installer is gated on the S7 check


class Resources(unittest.TestCase):
    def test_hold_recorded_only_on_change(self):
        db = DB(":memory:")
        bad = {"ok": False, "disk": {"free": 1}, "ram": {"free": 1}}
        control.update_hold(db, "t", bad)
        control.update_hold(db, "t", bad)
        self.assertEqual(db.one("SELECT COUNT(*) FROM events WHERE kind='system.resource_hold'")[0], 1)
        self.assertTrue(control.state(db)["hold"])
        self.assertEqual(fleet.blocked_reason(db), "resource hold (RAM or disk below limit)")


if __name__ == "__main__":
    unittest.main()
