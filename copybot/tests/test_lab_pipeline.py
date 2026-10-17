"""Mission 6 pipeline and fleet tests on a synthetic fixture market (no network, no real data).

The fixture plants a strong weekend effect, so `day_of_week` (weekend_only) should pass the screen, while
`hour_of_day` sees pure noise and must be rejected. Template approvals come from a human actor; the catalogue blob is
pinned so the tests do not depend on git state.
"""
import csv
import functools
import io
import json
import os
import random
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import control, fleet, jobs, lifecycle, pipeline, registry, templates  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import backtest, data  # noqa: E402
from lab.supervisor import Supervisor  # noqa: E402

HOUR = 3600
_PLACEBO = __import__("lab.engine.adversarial", fromlist=["placebo"]).placebo


def make_market(root, seed=3):
    """Monthly kline + funding zips for 2023 for every universe symbol, Binance CSV layout."""
    rng = random.Random(seed)
    a = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
    b = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    for sym in data.UNIVERSE:
        px, by_month, fund = 100.0, {}, {}
        for ts in range(a, b, HOUR):
            wd = datetime.fromtimestamp(ts, timezone.utc).weekday()
            drift = 0.0012 if wd >= 5 else -0.0003
            o = px
            px = px * (1 + drift + rng.gauss(0, 0.004))
            d = datetime.fromtimestamp(ts, timezone.utc)
            by_month.setdefault((d.year, d.month), []).append([ts * 1000, o, max(o, px), min(o, px), px, 1, ts * 1000 + 3599999])
            if ts % (8 * HOUR) == 0:
                fund.setdefault((d.year, d.month), []).append([ts * 1000, 8, rng.gauss(0.0001, 0.0002)])
        for (y, m), rows in by_month.items():
            _zip(os.path.join(root, "klines", f"{sym}-1h-{y}-{m:02d}.zip"),
                 ["open_time", "open", "high", "low", "close", "volume", "close_time"], rows)
            _zip(os.path.join(root, "funding", f"{sym}-fundingRate-{y}-{m:02d}.zip"),
                 ["calc_time", "funding_interval_hours", "last_funding_rate"], fund[(y, m)])


def _zip(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(os.path.basename(path).replace(".zip", ".csv"), buf.getvalue())


class Env(unittest.TestCase):
    market = None

    @classmethod
    def setUpClass(cls):
        cls.market = tempfile.mkdtemp(prefix="labmkt")
        make_market(cls.market)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labpipe")
        self.db_path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.db_path)
        self.patches = [mock.patch.object(data, "CACHE", self.market),
                        mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                        mock.patch.object(pipeline, "REPORTS", os.path.join(self.tmp, "reports")),
                        mock.patch.object(templates, "catalogue_blob", lambda: "blob-test"),
                        mock.patch.object(registry, "last_commit", lambda path: "c0ffee"),
                        mock.patch.object(registry, "blob_at", lambda c, p: "blob-test"),
                        mock.patch.object(data, "_fetch", self._no_network),
                        mock.patch.object(pipeline.adversarial, "placebo", functools.partial(_PLACEBO, n=5))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _no_network(self, url, path, get=None):
        if os.path.exists(path):
            return path
        raise AssertionError(f"test tried to download {url}")

    def approve(self, *names):
        for t in names:
            code = templates.request(self.db, t, "human:test", "fixture approval for tests")
            templates.confirm(self.db, code, "human:test")

    def drain(self, agents, limit=200):
        """Run job agents round-robin until nothing is runnable."""
        for _ in range(limit):
            for a in agents:
                a(self.db)
            c = jobs.counts(self.db)
            if c["queued"] == 0 and c["running"] == 0 and c["blocked"] == 0:
                break
        return jobs.counts(self.db)


class Pipeline(Env):
    def test_registration_needs_human_template_approval(self):
        pipeline.discover_catalogue(self.db)
        eid = "E_day_of_week_p1"
        self.assertEqual(lifecycle.state(self.db, eid), "DISCOVERED")
        self.assertFalse(pipeline.register(self.db, eid))                        # no approval yet
        with self.assertRaises(templates.TemplateError):
            templates.request(self.db, "day_of_week", "system:bot", "automation may not approve")
        self.approve("day_of_week")
        self.assertTrue(pipeline.register(self.db, eid))
        self.assertEqual(lifecycle.state(self.db, eid), "REGISTERED")
        spec = json.loads(registry.latest(self.db, eid)["spec_json"])
        for k in ("hypothesis", "mechanism", "datasets", "baseline", "costs", "acceptance", "rejection", "seed", "grid"):
            self.assertIn(k, spec)
        self.assertEqual(jobs.counts(self.db)["queued"] + jobs.counts(self.db)["blocked"], len(pipeline.STEPS))
        templates.revoke(self.db, "day_of_week", "human:test", "revoked in test")
        self.assertIsNone(templates.approval(self.db, "day_of_week"))

    def test_full_pipeline_pass_and_reject(self):
        pipeline.discover_catalogue(self.db)
        self.approve("day_of_week", "hour_of_day")
        fleet.strategy_pass(self.db)
        ag = [a for a in fleet.agents(self.db_path) if a.kinds]
        c = self.drain(ag)
        self.assertEqual(c["failed"], 0, c)
        self.assertEqual(c["done"], 2 * len(pipeline.STEPS))
        self.assertEqual(lifecycle.state(self.db, "E_day_of_week_p1"), "SCREEN_PASSED")
        self.assertEqual(lifecycle.state(self.db, "E_hour_of_day_p1"), "REJECTED")
        # every variant is in the trials ledger (multiple-testing record)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM trials")[0], 4)
        # the train/validation reads went through the gateway in SCREENING; nothing from the holdout
        splits = {r[0] for r in self.db.q("SELECT DISTINCT split FROM datasets")}
        self.assertEqual(splits, {"dev", "validation"})
        val = pipeline.load_artifact("E_day_of_week_p1", "validate")
        self.assertTrue(all(val["gates"].values()), val["gates"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "reports", "E_day_of_week_p1.md")))
        # holdout: no job without a human-approved VALIDATION transition, and the handler refuses
        self.assertEqual(pipeline.enqueue_holdouts(self.db), 0)
        with self.assertRaises(pipeline.StepError):
            pipeline.step_holdout(self.db, {"exp_id": "E_day_of_week_p1"}, "t")

    def test_reserved_window_refused(self):
        with mock.patch.dict(data.SPLITS, {"late": ((2025, 1), (2025, 2))}):
            with self.assertRaises(data.ReservedData):
                data.window("late")

    def test_cost_math(self):
        bars = [(i * HOUR, 100.0, 100.0 * (1.01 if i == 1 else 1.0)) for i in range(4)]
        rows = backtest.apply_costs(backtest.gross(bars, [0.0, 1.0, 1.0, 0.0]), {}, {"taker_fee": 0.0005,
                                    "half_spread": 0.0002, "slippage": 0.0002})
        fees = sum(r[3] for r in rows)
        spread = sum(r[4] for r in rows)
        slip = sum(r[5] for r in rows)
        self.assertAlmostEqual(fees, 2 * 0.0005)                     # two unit turnovers (enter, exit)
        self.assertAlmostEqual(spread, 2 * 0.0002)
        self.assertAlmostEqual(slip, 2 * 0.0002)
        gross = sum(r[2] for r in rows)
        self.assertAlmostEqual(sum(r[7] for r in rows), gross - fees - spread - slip)

    def test_step_failure_retries_then_dead_letters_and_cancels_dependants(self):
        pipeline.discover_catalogue(self.db)
        self.approve("day_of_week")
        fleet.strategy_pass(self.db)
        boom = mock.patch.dict(pipeline.HANDLERS, {"data": mock.Mock(side_effect=IOError("disk read error"))})
        with boom:
            a = [x for x in fleet.agents(self.db_path) if x.name == "data-1"][0]
            a(self.db)
            j = jobs.get(self.db, "data|E_day_of_week_p1")
            self.assertEqual(j["status"], "queued")                   # retry with backoff
            self.assertGreater(j["next_run"], time.time())
            self.db.con.execute("UPDATE jobs SET next_run=0")
            a(self.db)
            self.db.con.execute("UPDATE jobs SET next_run=0")
            a(self.db)
        self.assertEqual(jobs.get(self.db, "data|E_day_of_week_p1")["status"], "failed")
        jobs.claim(self.db, "x", ["backtest"])                          # triggers dependency resolution
        self.assertEqual(jobs.get(self.db, "backtest|E_day_of_week_p1")["status"], "cancelled")
        hb = self.db.one("SELECT errors, retries FROM heartbeats WHERE worker='data-1'")
        self.assertEqual((hb["errors"], hb["retries"]), (3, 2))


class Control(Env):
    def test_pause_hold_and_stop_block_claims(self):
        pipeline.discover_catalogue(self.db)
        self.approve("day_of_week")
        fleet.strategy_pass(self.db)
        a = [x for x in fleet.agents(self.db_path) if x.name == "data-1"][0]
        control.pause(self.db, "human:test", "operator pause in test")
        a(self.db)
        hb = self.db.one("SELECT status, next_action FROM heartbeats WHERE worker='data-1'")
        self.assertEqual(hb["status"], "blocked")
        self.assertEqual(jobs.counts(self.db)["running"] + jobs.counts(self.db)["done"], 0)
        control.resume(self.db, "human:test", "operator resume in test")
        control.update_hold(self.db, "t", {"ok": False, "disk": {"free": 1}, "ram": {"free": 1}})
        a(self.db)
        self.assertEqual(jobs.counts(self.db)["done"], 0)
        control.update_hold(self.db, "t", {"ok": True, "disk": {"free": 10 ** 12}, "ram": {"free": 10 ** 10}})
        a(self.db)
        self.assertEqual(jobs.get(self.db, "data|E_day_of_week_p1")["status"], "done")

    def test_resource_limits(self):
        r = control.resources()
        self.assertIn("ok", r)
        with mock.patch.object(control, "ram", lambda: {"total": 16e9, "free": 0.2e9, "load_pct": 99}):
            self.assertFalse(control.resources()["ok"])
        with mock.patch.object(control, "ram", lambda: {"total": 16e9, "free": 8e9, "load_pct": 50}):
            self.assertEqual(control.resources()["ok"], control.ops.disk()["free_ok"])

    def test_supervised_fleet_runs_in_parallel_and_stops_on_request(self):
        """Real supervisor threads: job agents + strategy agent; a stop request ends the run gracefully."""
        pipeline.discover_catalogue(self.db)
        self.approve("day_of_week", "hour_of_day", "vol_managed_long")
        ws = [w for w in fleet.workers(self.db_path) if w.name not in ("discovery-scanner", "paper-1", "risk-1",
                                                                         "discovery-catalogue")]
        sup = Supervisor(self.db_path, ws, log=lambda *a: None, check_evidence=False)
        import threading
        t = threading.Thread(target=sup.run, kwargs={"duration": 240})
        t.start()
        deadline = time.time() + 230
        while time.time() < deadline:
            c = jobs.counts(self.db)
            if c["done"] + c["failed"] + c["cancelled"] >= 3 * len(pipeline.STEPS):
                break
            time.sleep(0.5)
        control.request_stop(self.db, "human:test", "stop in test")
        t.join(30)
        self.assertFalse(t.is_alive())
        c = jobs.counts(self.db)
        self.assertEqual(c["done"], 3 * len(pipeline.STEPS), c)
        starts = self.db.q("SELECT payload FROM events WHERE kind='job.started'")
        ids = [json.loads(r[0])["job_id"] for r in starts]
        self.assertEqual(len(ids), len(set(ids)))                       # no job processed twice
        roles = {r[0] for r in self.db.q("SELECT role FROM heartbeats WHERE role IS NOT NULL")}
        self.assertGreaterEqual(len(roles), 6)
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='system.stopped'"))


if __name__ == "__main__":
    unittest.main()
