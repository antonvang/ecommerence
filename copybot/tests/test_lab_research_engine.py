"""Research engine increment (research/PROTOCOL_V3.md amendment 5): market events with a recorded decision, scanner
fixes, non-decisional diagnostics run as fleet jobs, the stricter holdout gate, gateway path continuity, and honest
progress reporting."""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, diagnose, fleet, jobs, lifecycle, pipeline, registry, scanner, watch  # noqa: E402
from lab.data import AccessRefused, Gateway  # noqa: E402
from lab.db import DB, HERE  # noqa: E402
from tests.lab_fixtures import frozen  # noqa: E402
from tests.test_lab import S, to_registered  # noqa: E402
from tests.test_lab_s3 import World, graveyard_fixture  # noqa: E402

DAY = 86400


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labengine")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts"))]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def events(self, kind):
        return [json.loads(r[0]) for r in self.db.q("SELECT payload FROM events WHERE kind=? ORDER BY id", kind)]


class ScannerDecisions(Base):
    def scan(self, w, t, names=("pricing_constraint",)):
        return scanner.run(self.db, list(names), w.get, w.post, now=t)

    def test_persistence_counts_only_the_last_24_hours(self):
        w = World(gap=0.006)
        self.scan(w, DAY * 10)
        s = self.scan(w, DAY * 12)                                   # two days later: the old flag no longer counts
        self.assertEqual((s["created"], s["waiting_persistence"]), ([], 1))
        s = self.scan(w, DAY * 12 + 3600)                            # a second hour within 24 h
        self.assertEqual(len(s["created"]), 1)

    def test_every_proposal_gets_one_decision_and_repeats_are_deduplicated(self):
        w = World(gap=0.006)
        self.scan(w, DAY * 10)
        ev = self.events("market.event")
        self.assertEqual(ev[-1]["decision"], "NO_ACTION")
        self.assertIn("waiting for persistence", ev[-1]["why"])
        s = self.scan(w, DAY * 10 + 3600)
        cand = s["created"][0]
        inv = [e for e in self.events("market.event") if e["decision"] == "INVESTIGATE"]
        self.assertEqual(len(inv), 1)
        self.assertIn(cand, inv[0]["why"])
        self.assertGreater(inv[0]["priority"], 0)
        self.assertGreater(inv[0]["magnitude"], 1)                   # 0.6 % gap against a 0.3 % threshold
        self.assertEqual(inv[0]["persistence_hours_24h"], 2)
        before = len(self.events("market.event"))
        self.scan(w, DAY * 10 + 7200)                                # now registered: the decision changes
        ev = self.events("market.event")
        self.assertEqual(len(ev), before + 1)
        self.assertEqual((ev[-1]["decision"], ev[-1]["why"]), ("NO_ACTION", f"already registered: {cand} is DISCOVERED"))
        self.scan(w, DAY * 10 + 10800)                               # same decision and reason within 6 h: no record
        self.assertEqual(len(self.events("market.event")), before + 1)
        self.scan(w, DAY * 10 + 7200 + scanner.EVENT_DEDUP_S + 1)    # after 6 h it is recorded again
        self.assertEqual(len(self.events("market.event")), before + 2)
        self.assertEqual(lifecycle.state(self.db, cand), "DISCOVERED")   # a record, never a state change or a trade
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM results")[0], 0)

    def test_negative_deviations_have_a_positive_size(self):
        w = World(premium=-0.01)                                     # perp 1 % below the index
        self.scan(w, DAY * 10)
        self.scan(w, DAY * 10 + 3600)
        inv = [e for e in self.events("market.event") if e["decision"] == "INVESTIGATE"]
        self.assertTrue(inv)
        self.assertGreater(inv[0]["magnitude"], 1)
        self.assertGreater(inv[0]["priority"], 0)

    def test_suppressed_candidates_stay_in_the_graveyard(self):
        graveyard_fixture(self.db, "L22", "perp_premium_convergence", "btc_perp_spot", "minutes", "taker")
        w = World(premium=0.01)
        self.scan(w, DAY * 10)
        s = self.scan(w, DAY * 10 + 3600)
        sup = s["suppressed"][0]
        self.assertEqual(lifecycle.state(self.db, sup), "SUPPRESSED")
        s = self.scan(w, DAY * 10 + 7200)
        self.assertEqual((s["suppressed"], s["seen_again"]), ([sup], []))  # before amendment 5 it was 'seen again'
        decisions = {e["decision"] for e in self.events("market.event") if e.get("key", {}).get("metric") == "perp_premium"}
        self.assertEqual(decisions, {"NO_ACTION"})

    def test_an_unstable_data_source_is_a_market_event(self):
        self.scan(World(fail_binance=True), DAY * 10)
        err = [e for e in self.events("market.event") if e["key"].get("metric") == "error"]
        self.assertTrue(err)
        self.assertEqual(err[0]["decision"], "NO_ACTION")
        self.assertIn("binance unreachable", err[0]["why"])


class Diagnostics(Base):
    def finished(self, eid, daily, gates, state="REJECTED"):
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint=eid,
                       spec_json={"template": "day_of_week"})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=state, actor="fixture",
                       reason="fixture: finished experiment")
        registry.record_result(self.db, eid, "EXPLORATORY", "REJECTED at validation: fixture", {}, {}, "system:t")
        frozen(self.db, eid, "validate", {"daily_net": daily, "gates": gates})

    def test_series_and_lessons_are_deterministic(self):
        r = [0.01] * 3 + [0.0] * 37 + [-0.0001] * 40 + [0.0] * 40       # thirds: +0.03, -0.004, 0
        s = diagnose.series(r)
        self.assertEqual(s["n"], 120)
        self.assertEqual(s["positive_thirds"], 1)
        self.assertAlmostEqual(s["best_days_share"], 1.0)
        self.assertAlmostEqual(s["active_days"], 43 / 120)
        self.assertAlmostEqual(s["max_drawdown"], 0.004)
        self.assertEqual(s["longest_drawdown_days"], 80)
        ls, failed = diagnose.lessons(s, {"net Sharpe > buy-and-hold": False, "deflated Sharpe probability >= 0.95": True})
        self.assertEqual(ls, ["unstable: positive in fewer than 2 of 3 chronological thirds",
                              "concentrated: the best 5 days carry 100% of positive net",
                              "beaten by buy-and-hold over the same period"])
        self.assertEqual(failed, ["net Sharpe > buy-and-hold"])
        ls, _ = diagnose.lessons(diagnose.series([-0.001] * 50), {})
        self.assertIn("no edge: net total <= 0 on validation", ls)
        self.assertEqual(diagnose.series(r), s)

    def test_a_finished_experiment_is_diagnosed_once_by_the_report_agent_without_changing_anything(self):
        self.finished("E_a", [0.001, -0.002, 0.003] * 40, {"deflated Sharpe probability >= 0.95": False})
        counts = lambda: {t: self.db.one(f"SELECT COUNT(*) FROM {t}")[0] for t in ("results", "trials", "transitions")}  # noqa
        before = counts()
        self.assertEqual(pipeline.enqueue_diagnostics(self.db), 1)
        self.assertEqual(pipeline.enqueue_diagnostics(self.db), 0)              # exactly one job
        agent = [a for a in fleet.agents(self.path) if a.name == "report-1"][0]
        with mock.patch.object(fleet, "PROCESSES", False):
            agent(self.db)
        j = jobs.get(self.db, "diagnose|E_a")
        self.assertEqual(j["status"], "done", j)
        with open(os.path.join(pipeline.ARTIFACTS, "_diagnostic", "E_a", "diagnose.json"), encoding="utf-8") as f:
            out = json.load(f)
        self.assertFalse(out["decisional"])
        self.assertEqual(out["lessons"], ["failed only the luck check (multiple testing)"])
        ev = self.events("research.diagnostic")[0]
        self.assertEqual(ev["lessons"], out["lessons"])
        done = self.events("job.done")[-1]
        self.assertEqual(done["artifact_sha256"], ev["artifact_sha256"])     # the result is chained
        self.assertEqual(counts(), before)                                       # no verdict, trial or state touched
        self.assertEqual(lifecycle.state(self.db, "E_a"), "REJECTED")

    def test_only_finished_experiments_and_only_verified_series(self):
        self.finished("E_b", [0.001] * 30, {}, state="OBSERVATION")
        self.assertEqual(pipeline.enqueue_diagnostics(self.db), 0)
        self.finished("E_s", [], {})                                            # rejected before validation
        jobs.enqueue(self.db, "validate|E_s", "validate", "E_s", {}, actor="system:t")
        self.db.con.execute("UPDATE jobs SET status='done', result=? WHERE job_id='validate|E_s'",
                            (json.dumps({"skipped": True}),))
        self.assertEqual(pipeline.enqueue_diagnostics(self.db), 0)             # no series: nothing to learn from
        with self.assertRaises(pipeline.StepError):
            pipeline.step_diagnose(self.db, {"exp_id": "E_b"}, "t")
        self.finished("E_c", [0.001] * 30, {})
        with open(os.path.join(pipeline.ARTIFACTS, "E_c", "validate.json"), "w") as f:
            json.dump({"daily_net": [0.5] * 30, "gates": {}}, f)                # tampered after the fact
        with self.assertRaises(pipeline.ArtifactError):
            pipeline.step_diagnose(self.db, {"exp_id": "E_c"}, "t")


class HoldoutGate(Base):
    def test_too_few_symbols_fail_the_holdout(self):
        eid = "E_day_of_week_p2"
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint=eid,
                       spec_json={**pipeline.template_spec("day_of_week")})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="VALIDATION", actor="fixture",
                       reason="fixture: holdout opened")
        good = {"net_mean_daily": 0.01, "lb_one_sided": 0.001, "net_sharpe_ann": 3.0, "daily_net": [0.01]}
        with mock.patch.object(pipeline, "frozen_variant", lambda db, e: {"params": {}, "fit": None}), \
                mock.patch.object(pipeline, "_market", lambda *a, **k: ({"BTCUSDT": []}, {}, {}, None)), \
                mock.patch.object(pipeline, "_quality", lambda *a, **k: ({"BTCUSDT": {}}, [], True)), \
                mock.patch.object(pipeline, "_positions", lambda *a, **k: {}), \
                mock.patch.object(pipeline, "_evaluate", lambda *a, **k: dict(good)), \
                mock.patch.object(pipeline, "_benchmark", lambda *a, **k: {"net_sharpe_ann": 0.1}), \
                mock.patch.object(pipeline.catalogue, "min_symbols", lambda t: 2):
            r = pipeline.step_holdout(self.db, {"exp_id": eid}, "t")
        self.assertIn("holdout data quality (min symbols)", r["verdict"])
        self.assertEqual(lifecycle.state(self.db, eid), "REJECTED")


class GatewayContinuity(unittest.TestCase):
    def test_a_file_first_read_on_windows_is_still_protected_on_linux(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            f = os.path.join(tmp.name, "d.json")
            with open(f, "w") as fh:
                fh.write("[1,2,3]")
            db = DB(":memory:")
            to_registered(db)
            lifecycle.auto_transition(db, "E1", "SCREENING", S, "spec committed, screening starts")
            rel = os.path.relpath(os.path.abspath(f), HERE).replace("\\", "/")
            db.append("datasets", exp_id="E1", split="dev", source="unit", path=rel.replace("/", "\\"), window_start=0,
                      window_end=10, ts=0, sha256="0" * 64, size=1, purpose="evaluate", code_hash="c1")
            with self.assertRaises(AccessRefused) as cm:
                Gateway(db, S).access("E1", "dev", [f], (0, 10), "unit", "evaluate", "c1")
            self.assertIn("changed since it was first read", str(cm.exception))
            db.close()
        finally:
            tmp.cleanup()


class Progress(Base):
    def test_kpis_explain_why_the_lab_is_idle_and_agents_say_they_have_no_work(self):
        from lab.engine import catalogue
        for t in catalogue.TEMPLATES:                                     # every template already has an experiment
            eid = catalogue.exp_id(t)
            self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=t, fingerprint=eid,
                           spec_json={})
        jobs.enqueue(self.db, "observe|E_x", "observe", "E_x", {}, actor="system:t", not_before=time.time() + 30 * DAY)
        r = command.research_progress(self.db)
        self.assertEqual(r["runnable_jobs"], 0)
        self.assertIn("catalogue exhausted", r["idle_reason"])
        self.assertIn("next queued job due", r["idle_reason"])
        self.db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status, started_ts) "
                            "VALUES('supervisor', ?, 1, 1, '', 'running', ?)", (int(time.time()), time.time()))
        self.db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status, started_ts) "
                            "VALUES('data-1', ?, 1, 1, '', 'idle', ?)", (int(time.time()), time.time()))
        a = {x["agent"]: x for x in command.agents(self.db)["agents"]}
        self.assertTrue(a["data-1"]["work"].startswith("no work"))
        self.assertIn("catalogue exhausted", a["data-1"]["work"])
        self.assertEqual(a["data-1"]["jobs_done_this_run"], 0)
        jobs.enqueue(self.db, "data|E_y", "data", "E_y", {}, actor="system:t")
        r = command.research_progress(self.db)
        self.assertEqual(r["runnable_jobs"], 1)
        self.assertIsNone(r["idle_reason"])                               # work is waiting: not idle

    def test_an_idle_agent_does_not_claim_the_catalogue_is_exhausted_when_it_is_not(self):
        for w, st in (("supervisor", "running"), ("data-1", "idle")):
            self.db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status, started_ts) "
                                "VALUES(?, ?, 1, 1, '', ?, ?)", (w, int(time.time()), st, time.time()))
        a = {x["agent"]: x for x in command.agents(self.db)["agents"]}
        self.assertTrue(a["data-1"]["work"].startswith("no work"))
        self.assertNotIn("catalogue exhausted", a["data-1"]["work"])

    def test_feed_shows_market_events_diagnostics_and_risk(self):
        self.db.event("market.event", "system:scanner", None, {"key": {"metric": "perp_premium", "instrument": "SOL"},
                                                               "decision": "INVESTIGATE", "why": "new candidate C_x",
                                                               "priority": 2.0})
        self.db.event("research.diagnostic", "system:report-1", "E_a", {"lessons": ["no edge: net total <= 0"]})
        self.db.event("risk.pause", "system:risk", "E_a", {"rule": "drawdown", "detail": "test"})
        items = command.feed(self.db)["items"]
        tags = [i["tag"] for i in items]
        self.assertEqual(tags[:3], ["RISIKO", "LÆRDOM", "UNDERSØG"])

    def test_every_scan_is_visible_as_search_activity(self):
        s = scanner.run(self.db, ["pricing_constraint"], World(gap=0.006).get, World(gap=0.006).post, now=DAY * 10)
        item = command.feed(self.db)["items"][0]
        self.assertEqual(item["tag"], "SØGNING")
        self.assertEqual(item["text"], f"Søgning: {s['observations']} målinger · {s['flagged']} markeret · "
                                       f"{s['proposals']} forslag · 0 nye · 0 undersøges")
        r = command.research_progress(self.db)
        self.assertEqual(r["scans_24h"], 1)
        self.assertIsNotNone(r["last_scan_ts"])
        names = {x[0] for x in self.db.q("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertTrue({"events_kind", "sim_fills_order", "sim_equity_ts"} <= names)

    def test_watcher_judges_progress_only_on_a_fleet_that_has_run_two_hours(self):
        run = {"status": "running"}
        self.assertIsNone(watch._progress(self.path, time.time(), {"status": "stopped"})[0])
        self.db.event("system.running", "system:supervisor", None, {"pid": 1})
        t = self.db.one("SELECT MAX(ts) FROM events WHERE kind='system.running'")[0]
        self.assertIsNone(watch._progress(self.path, t + 3600, run)[0])           # up 1 h: not judged
        ok, why = watch._progress(self.path, t + 3 * 3600, run)                   # up 3 h, nothing ever done
        self.assertFalse(ok)
        self.assertIn("no research work", why)
        jobs.enqueue(self.db, "report|E_x", "report", "E_x", {}, actor="system:t")
        self.assertTrue(watch._progress(self.path, t + 3 * 3600, run)[0])       # runnable work is progress

    def test_an_idle_lab_is_reported_once_a_day_not_every_hour(self):
        sent, clock = [], {"t": 1_000_000.0}
        w = watch.Watcher(self.path, os.path.join(self.tmp, "pm.db"), 8770, log_dir=os.path.join(self.tmp, "logs"),
                          status_file=os.path.join(self.tmp, "status.json"),
                          heartbeat_file=os.path.join(self.tmp, "watch.heartbeat"),
                          notifier=lambda t, b: sent.append(t) or True, clock=lambda: clock["t"],
                          suspends=lambda: None, slept=lambda: None, out=lambda s: None)
        idle = {"progress": {"ok": False, "detail": "no research work"}}
        n = []
        with mock.patch.object(watch, "check", lambda *a: idle):
            for advance in (0, 3600, 6 * 3600, 16 * 3600, 3600):              # 0 h, 1 h, 7 h, 23 h, 24 h
                clock["t"] += advance
                w.tick()
                n.append(len(sent))
        self.assertEqual(n, [1, 1, 1, 1, 2])                                     # other components remind hourly
        self.assertEqual(sent, ["Copybot: progress NEDE", "Copybot: progress stadig nede"])


if __name__ == "__main__":
    unittest.main()
