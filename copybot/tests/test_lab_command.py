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
from unittest import mock

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

    def test_skipped_validation_is_not_counted_as_a_test(self):
        for eid, res in (("V1", {"passed": False, "tests": 1}), ("V2", {"skipped": True})):
            jobs.enqueue(self.db, f"validate|{eid}", "validate", eid, now=self.now)
            j = jobs.claim(self.db, "validation-1", ["validate"], now=self.now)
            jobs.complete(self.db, j["job_id"], "validation-1", res, now=self.now + 1)
        self.assertEqual(command.kpis(self.db, 900, self.now + 2)["tests_completed"]["validation_runs"], 1)

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

    def test_retired_workers_are_not_counted(self):
        db = self.db
        db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status) VALUES('heartbeat',?,1,1,'',"
                       "'stopped')", (int(time.time()) - 7200,))
        db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status) VALUES('data-1',?,1,1,'',"
                       "'idle')", (int(time.time()) - 7200,))
        r = command.agents(db)
        names = [a["agent"] for a in r["agents"]]
        self.assertNotIn("heartbeat", names)                         # not in the fleet roster and silent
        self.assertIn("data-1", names)                               # roster agents always show, even when silent
        self.assertEqual(r["retired"], ["heartbeat"])

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

    def test_template_approval_from_dashboard_is_two_step_and_guarded(self):
        a = self.get("/api/approvals")
        names = {r["template"]: r for r in a["templates"]}
        self.assertEqual(names["xs_momentum"]["name"], "Momentum")
        code, _ = self.post("/api/control/approve-template", {"template": "xs_momentum"}, token=False)
        self.assertEqual(code, 403)
        if not a["catalogue_committed"]:
            self.skipTest("catalogue has uncommitted changes in this checkout")
        code, r = self.post("/api/control/approve-template", {"template": "xs_momentum"})
        self.assertEqual(code, 200)
        self.assertFalse({x["template"]: x for x in self.get("/api/approvals")["templates"]}["xs_momentum"]["approved"])
        code, r = self.post("/api/control/confirm-template", {"code": r["code"]})
        self.assertEqual((code, r["approved"]), (200, True))
        row = {x["template"]: x for x in self.get("/api/approvals")["templates"]}["xs_momentum"]
        self.assertTrue(row["approved"])
        self.assertTrue(row["status"].startswith("Godkendt"))

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
        for s in ("Mars Command Center", "Mission Control", "PAPER ONLY", "ikke tilgængelig", "Rigtig konto", "Saldo (paper)"):
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


class FeedText(unittest.TestCase):
    def test_short_danish_reasons(self):
        self.assertEqual(command.short_reason("REJECTED at validation: failed a, b, c"),
                         "afvist i anden test: 3 af kravene ikke opfyldt")
        self.assertIn("købe og holde", command.short_reason("REJECTED at train gate: selected ..."))
        self.assertIn("allerede afvist", command.short_reason("matches rejected experiment(s) L14"))
        self.assertEqual(command.short_reason("something else"), "something else")


class Performance(unittest.TestCase):
    """Regressions: /api/approvals ran the git lookup once per template (about 6 s); /api/audit re-walked every hash
    chain on every refresh (about 6 s on the live registry)."""

    def test_approvals_look_up_the_catalogue_once(self):
        from lab import templates
        calls = []
        with mock.patch.object(templates, "catalogue_blob", lambda: calls.append(1) or "blob"):
            command.approvals(DB(":memory:"))
        self.assertEqual(len(calls), 1)

    def test_incremental_chain_verification_matches_full_and_catches_breaks(self):
        db = DB(":memory:")
        for i in range(5):
            db.event("x.test", "t", None, {"i": i})
        cache = {}
        a = web.verify_chains(db, cache)
        self.assertEqual(a, db.verify())
        for i in range(3):
            db.event("x.test", "t", None, {"i": i})
        b = web.verify_chains(db, cache)
        self.assertEqual(b, db.verify())
        self.assertEqual(b[0]["events"][0], 8)
        db.con.execute("DROP TRIGGER events_no_update")                    # tamper with a new row
        last = db.one("SELECT MAX(id) FROM events")[0]
        db.con.execute("UPDATE events SET payload='{}' WHERE id=?", (last,))
        db.event("x.test", "t", None, {"i": 99})
        c = web.verify_chains(db, cache)
        self.assertFalse(c[1])                                             # trigger missing is reported
        self.assertEqual(c[0]["events"][1], last)                          # and a full walk locates the broken row


class StopState(unittest.TestCase):
    def test_stop_is_pending_only_until_the_supervisor_stopped(self):
        db = DB(":memory:")
        db.event("system.running", "t")
        self.assertFalse(control.state(db)["stop"])
        control.request_stop(db, "human:t", "stop for the test")
        self.assertTrue(control.state(db)["stop"])
        db.event("system.stopped", "t")
        self.assertFalse(control.state(db)["stop"])
        db.event("system.running", "t")                                    # a new run is not blocked by the old stop
        self.assertFalse(control.state(db)["stop"])


class LinuxRam(unittest.TestCase):
    def test_meminfo_is_read_as_available_memory(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "meminfo")
            with open(p, "w") as f:
                f.write("MemTotal:       16000000 kB\nMemFree:          500000 kB\nMemAvailable:    4000000 kB\n")
            self.assertEqual(control._ram_linux(p), {"total": 16000000 * 1024, "free": 4000000 * 1024,
                                                     "load_pct": 75})
            self.assertIsNone(control._ram_linux(os.path.join(d, "missing")))


class WorkerProcesses(unittest.TestCase):
    def test_heavy_steps_spawn_fresh_processes_on_every_platform(self):
        """A forked child would inherit SQLite connections and POSIX locks (Linux default); spawn never does."""
        with mock.patch.object(fleet, "_pool", None):
            pool = fleet._get_pool()
            try:
                self.assertEqual(pool._mp_context.get_start_method(), "spawn")
            finally:
                pool.shutdown()


class ExportDb(unittest.TestCase):
    def test_export_refuses_while_running_and_copies_a_verified_chain(self):
        from lab.__main__ import main
        from tests.lab_fixtures import supervised
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "lab.db"), os.path.join(d, "copy.db")
            db = DB(src)
            db.event("x", "system:test")
            supervised(db)
            db.close()
            lines = []
            self.assertEqual(main(["--db", src, "export-db", dst], out=lines.append), 3)    # fleet running
            self.assertFalse(os.path.exists(dst))
            db = DB(src)
            supervised(db, status="stopped")
            db.close()
            self.assertEqual(main(["--db", src, "export-db", dst], out=lines.append), 0)
            self.assertIn("chain OK", lines[-1])
            copy = DB(dst)
            try:
                self.assertTrue(copy.one("SELECT 1 FROM events WHERE kind='lab.exported'"))
                self.assertEqual(copy.one("SELECT COUNT(*) FROM events")[0], 2)
            finally:
                copy.close()
            self.assertEqual(main(["--db", src, "export-db", dst], out=lines.append), 3)    # never overwrite


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
