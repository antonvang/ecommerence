import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import gates, mission, ops, registry, supervisor, web  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.risk import Risk  # noqa: E402

NOW = 2_000_000_000


def exp(db, eid, st, spec=None, spec_path=None, verdict=None):
    db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=f"m_{eid}", fingerprint=eid,
              spec_json=spec or {"instrument": "polymarket_x"}, spec_path=spec_path)
    db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=st, actor="fixture", reason="fixture")
    if verdict:
        db.append("results", exp_id=eid, version=1, ts=0, label="LEGACY", verdict=verdict, metrics={}, evidence={})


def beat(db, name, ts, status, stale_after=30, interval=5.0, ok=1):
    db.con.execute("INSERT OR REPLACE INTO heartbeats(worker, ts, pid, ok, detail, status, stale_after, interval) "
                   "VALUES(?,?,?,?,?,?,?,?)", (name, ts, 1, ok, "x", status, stale_after, interval))


class WorkerHonesty(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def test_fresh_worker_is_offline_without_a_live_supervisor(self):
        beat(self.db, "scanner", NOW - 1, "idle", stale_after=300)
        w = mission.workers(self.db, NOW)
        self.assertEqual((w["supervisor"]["alive"], w["workers"][0]["state"], w["active"]), (False, "offline", 0))
        beat(self.db, "supervisor", NOW - 60, "running")              # supervisor beat too old
        self.assertEqual(mission.workers(self.db, NOW)["workers"][0]["state"], "offline")

    def test_states_with_live_supervisor(self):
        beat(self.db, "supervisor", NOW - 2, "running")
        beat(self.db, "a", NOW - 1, "running")
        beat(self.db, "b", NOW - 3, "idle", interval=60)
        beat(self.db, "c", NOW - 500, "idle", stale_after=100)
        beat(self.db, "d", NOW - 1, "error", ok=0)
        w = {x["worker"]: x for x in mission.workers(self.db, NOW)["workers"]}
        self.assertEqual({k: v["state"] for k, v in w.items()},
                         {"a": "running", "b": "scheduled", "c": "stale", "d": "error"})
        self.assertEqual(w["b"]["next_run_ts"], NOW - 3 + 60)
        self.assertEqual(mission.workers(self.db, NOW)["active"], 2)
        beat(self.db, "supervisor", NOW - 2, "stopped")               # stopped cleanly -> nothing active
        self.assertEqual(mission.workers(self.db, NOW)["active"], 0)


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        exp(self.db, "C1", "DISCOVERED")
        exp(self.db, "H1", "DISCOVERED", spec_path="research/x.json")
        exp(self.db, "R1", "REJECTED", verdict="FAIL: fixture")
        exp(self.db, "X01_pm_lp_v1", "EXTERNAL", {"instrument": "polymarket_reward_markets"})

    def test_stages_tests_reasons_next_actions(self):
        p = mission.pipeline_rows(self.db, NOW)
        rows = {r["exp_id"]: r for r in p["experiments"]}
        self.assertEqual(rows["C1"]["stage"], "DISCOVERY")
        self.assertEqual(rows["H1"]["stage"], "HYPOTHESIS")
        self.assertEqual(rows["R1"]["stage"], "REJECTED")
        self.assertEqual(rows["R1"]["tests_completed"], 1)
        self.assertEqual(rows["R1"]["reason"], "FAIL: fixture")
        self.assertEqual(rows["R1"]["next_actions"], [])                # final state
        self.assertIn({"to": "REGISTERED", "who": "human"}, rows["C1"]["next_actions"])
        self.assertIsNone(rows["C1"]["eta"])                            # no honest estimate exists
        self.assertEqual(p["counts"]["DISCOVERY"], 1)
        self.assertEqual(rows["X01_pm_lp_v1"]["market"], "prediction markets")

    def test_external_status_from_file_age_only(self):
        with mock.patch.object(ops, "external_freshness",
                               return_value={"X01_pm_lp_v1": {"label": "c", "last_write_age_s": 20, "basis": "f"}}):
            r = [x for x in mission.pipeline_rows(self.db, NOW)["experiments"] if x["exp_id"] == "X01_pm_lp_v1"][0]
        self.assertEqual(r["status"], "running (external process)")
        with mock.patch.object(ops, "external_freshness",
                               return_value={"X01_pm_lp_v1": {"label": "c", "last_write_age_s": 7200, "basis": "f"}}):
            r = [x for x in mission.pipeline_rows(self.db, NOW)["experiments"] if x["exp_id"] == "X01_pm_lp_v1"][0]
        self.assertEqual(r["status"], "external — no recent writes")

    def test_mission_counts_match_registry(self):
        m = mission.mission(self.db, NOW)
        st = {}
        for x in registry.status(self.db):
            st[x["state"]] = st.get(x["state"], 0) + 1
        self.assertEqual(m["counts"]["candidates"], st["DISCOVERED"])
        self.assertEqual(m["counts"]["rejected"], st["REJECTED"])
        self.assertEqual(m["counts"]["external"], 1)
        self.assertTrue(m["paper_only"] and m["chain_ok"])
        self.assertFalse(m["gate_s7"]["open"])

    def test_throughput_counts_real_events(self):
        for k in ("candidate.discovered", "candidate.discovered", "scan.finished", "risk.pause"):
            self.db.append("events", ts=NOW - 10, kind=k, actor="t", exp_id=None, payload={})
        day = [d for d in mission.throughput(self.db, 5, NOW)["days"] if d["day"] == (NOW - 10) // 86400 * 86400][0]
        self.assertEqual((day["discovered"], day["scans"], day["risk"]), (2, 1, 1))


class GateS7(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def alive(self, start, hours, step=3600):
        for h in range(hours):
            self.db.append("events", ts=start + h * step, kind="system.alive", actor="t", exp_id=None, payload={})

    def test_closed_without_operation_and_open_after_seven_clean_days(self):
        self.assertFalse(gates.s7_gate(self.db, NOW)["open"])
        self.alive(NOW - 7 * 86400 - 3600, 7 * 24 + 2)
        g = gates.s7_gate(self.db, NOW)
        self.assertTrue(g["open"], g)

    def test_gap_or_incident_resets_the_clock(self):
        self.alive(NOW - 8 * 86400, 2 * 24)                            # two days ...
        self.alive(NOW - 6 * 86400 + 5 * 3600, 6 * 24 - 5)             # ... then a 3 h gap, six more days
        self.assertFalse(gates.s7_gate(self.db, NOW)["open"])
        db2 = DB(":memory:")
        self.db = db2
        self.alive(NOW - 7 * 86400 - 3600, 7 * 24 + 2)
        db2.append("risk_events", exp_id="GLOBAL", ts=NOW - 86400, rule="x", value=None, threshold=None,
                   action="FAIL_CLOSED", detail="d", actor="t")
        g = gates.s7_gate(db2, NOW)
        self.assertFalse(g["open"])
        self.assertLess(g["covered_s"], 2 * 86400)

    def test_supervised_alive_record_and_disk_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            sup = supervisor.Supervisor(os.path.join(tmp, "lab.db"), [], log=lambda *a: None, check_evidence=False)
            sup.db = DB(os.path.join(tmp, "lab.db"))
            low = {"total": 1, "used": 1, "free": 10, "free_ok": False, "min_free": ops.DISK_MIN_FREE_BYTES}
            with mock.patch.object(ops, "disk", return_value=low):
                sup.housekeeping()
            self.assertEqual(sup.db.one("SELECT COUNT(*) FROM events WHERE kind='system.alive'")[0], 1)
            self.assertEqual(sup.db.one("SELECT status FROM heartbeats WHERE worker='supervisor'")[0], "running")
            self.assertTrue(Risk(sup.db).fail_closed())
            logs = os.listdir(os.path.join(tmp, "logs"))
            self.assertTrue(logs and logs[0].startswith("supervisor-") and logs[0].endswith(".jsonl"))
            with open(os.path.join(tmp, "logs", logs[0]), encoding="utf-8") as f:
                self.assertEqual(json.loads(f.readline())["kind"], "disk_low")
            sup.db.close()


class Endpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "lab.db")
        db = DB(cls.path)
        exp(db, "C1", "DISCOVERED")
        exp(db, "R1", "REJECTED", verdict="FAIL: fixture")
        db.close()
        cls.srv = web.LabServer(("127.0.0.1", 0), cls.path)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.closing = True
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, p):
        with urllib.request.urlopen(self.base + p, timeout=10) as r:
            return json.loads(r.read())

    def test_mission_endpoints(self):
        m = self.get("/api/mission")
        self.assertTrue(m["paper_only"])
        self.assertEqual(m["counts"]["rejected"], 1)
        self.assertEqual(m["workers"]["active"], 0)
        p = self.get("/api/pipeline")
        self.assertEqual({r["exp_id"] for r in p["experiments"]}, {"C1", "R1"})
        self.assertIn("days", self.get("/api/throughput"))
        self.assertIn("failure_patterns", self.get("/api/results"))

    def test_event_stream_sends_state_and_new_events(self):
        req = urllib.request.urlopen(self.base + "/api/stream", timeout=10)
        first = json.loads(req.readline().decode().removeprefix("data: "))
        req.readline()
        self.assertTrue(first["first"])
        db = DB(self.path)
        db.append("events", ts=int(time.time()), kind="candidate.discovered", actor="t", exp_id="C1", payload={})
        db.close()
        second = json.loads(req.readline().decode().removeprefix("data: "))
        self.assertFalse(second["first"])
        self.assertEqual(second["new_events"][0]["kind"], "candidate.discovered")
        req.close()

    def test_page_is_the_mission_control_and_paper_only(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            html = r.read().decode()
        self.assertIn("Mission Control", html)
        self.assertIn("PAPER ONLY", html)
        self.assertIn(self.srv.token, html)
        self.assertNotIn("__LAB_TOKEN__", html)


if __name__ == "__main__":
    unittest.main()
