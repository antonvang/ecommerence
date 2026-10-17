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
                        mock.patch.object(pipeline.adversarial, "placebo", functools.partial(_PLACEBO, n=5)),
                        mock.patch.object(pipeline, "PLACEBO_N", 5),
                        mock.patch.object(fleet, "PROCESSES", False)]          # tests patch module state
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
        eid = "E_day_of_week_p2"
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
        ag = [a for a in fleet.agents(self.db_path) if a.kinds]
        self.approve("day_of_week")                          # batch 1: the planted weekend effect
        fleet.strategy_pass(self.db)
        self.drain(ag)
        self.approve("hour_of_day")                          # batch 2: pure noise
        fleet.strategy_pass(self.db)
        c = self.drain(ag)
        self.assertEqual(c["failed"], 0, c)
        self.assertEqual(c["done"], 2 * len(pipeline.STEPS))
        self.assertEqual(lifecycle.state(self.db, "E_day_of_week_p2"), "SCREEN_PASSED")
        self.assertEqual(lifecycle.state(self.db, "E_hour_of_day_p2"), "REJECTED")
        # every variant is in the trials ledger (multiple-testing record)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM trials")[0], 4)
        # the train/validation reads went through the gateway in SCREENING; nothing from the holdout
        splits = {r[0] for r in self.db.q("SELECT DISTINCT split FROM datasets")}
        self.assertEqual(splits, {"dev", "validation"})
        val = pipeline.load_artifact("E_day_of_week_p2", "validate")
        self.assertTrue(all(val["gates"].values()), val["gates"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "reports", "E_day_of_week_p2.md")))
        # holdout: no job without a human-approved VALIDATION transition, and the handler refuses
        self.assertEqual(pipeline.enqueue_holdouts(self.db), 0)
        with self.assertRaises(pipeline.StepError):
            pipeline.step_holdout(self.db, {"exp_id": "E_day_of_week_p2"}, "t")

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
            j = jobs.get(self.db, "data|E_day_of_week_p2")
            self.assertEqual(j["status"], "queued")                   # retry with backoff
            self.assertGreater(j["next_run"], time.time())
            self.db.con.execute("UPDATE jobs SET next_run=0")
            a(self.db)
            self.db.con.execute("UPDATE jobs SET next_run=0")
            a(self.db)
        self.assertEqual(jobs.get(self.db, "data|E_day_of_week_p2")["status"], "failed")
        jobs.claim(self.db, "x", ["backtest"])                          # triggers dependency resolution
        self.assertEqual(jobs.get(self.db, "backtest|E_day_of_week_p2")["status"], "cancelled")
        hb = self.db.one("SELECT errors, retries FROM heartbeats WHERE worker='data-1'")
        self.assertEqual((hb["errors"], hb["retries"]), (3, 2))


class FamiliesAreCausal(unittest.TestCase):
    """Regression: daily_reversal p1 read bars[-1] (the last bar of the window) at i = 24. The poison test caught it on
    real data; here every family is poisoned at early and late cut points and must not change earlier positions."""

    def test_every_family_ignores_the_future(self):
        from lab.engine import catalogue
        rng = random.Random(1)
        t0 = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
        px, bars = 100.0, []
        for k in range(24 * 120):
            o = px
            px *= 1 + rng.gauss(0, 0.002) + (0.006 if k // 24 == 30 else 0.0)   # large move on day 30: first z decision
            bars.append((t0 + k * HOUR, o, px))
        bars[-1] = (bars[-1][0], bars[-1][1], bars[23][2])   # last close = early close: wrap-around reads look normal
        funding = {t0 + k * 8 * HOUR: rng.gauss(0.0001, 0.0003) for k in range(3 * 120)}
        for name, tpl in catalogue.TEMPLATES.items():
            if tpl.get("cross_sectional"):
                continue                                     # covered by test_cross_sectional_families_ignore_the_future
            for params in tpl["grid"]:
                fit = tpl["fit"](bars[:24 * 60], params) if tpl.get("fit") else None
                full = tpl["family"](bars, funding, params, fit)
                for cut in (24, 25, 30, 24 * 32, 24 * 40, 24 * 100):
                    pb = bars[:cut + 1] + [(ts, o * 1000, c * 1000) for ts, o, c in bars[cut + 1:]]
                    pf = {k: (v if k <= bars[cut][0] else 1.0) for k, v in funding.items()}
                    got = tpl["family"](pb, pf, params, fit)
                    self.assertEqual(full[:cut + 1], got[:cut + 1], f"{name} {params} looks ahead (cut {cut})")


    def test_cross_sectional_families_ignore_the_future(self):
        """Every cross-sectional family, on its own universe (8 or 30 symbols), with volume where it needs it."""
        from lab.engine import catalogue
        t0 = int(datetime(2023, 1, 2, tzinfo=timezone.utc).timestamp())          # a Monday
        n = 24 * 200
        cache = {}

        def market(symbols):
            key = tuple(symbols)
            if key not in cache:
                rng = random.Random(2)
                bars_by, funding_by, vol_by = {}, {}, {}
                for j, s in enumerate(symbols):
                    px, b, v = 100.0, [], {}
                    for k in range(n):
                        o = px
                        px *= 1 + rng.gauss(0.00005 * ((j % 7) - 3), 0.003 + 0.0006 * (j % 9))
                        b.append((t0 + k * HOUR, o, px))
                        v[t0 + k * HOUR] = 1e6 * (1 + j) * (1 + 0.5 * rng.random()) * (3 if (k // 24) % 23 == j % 23 else 1)
                    bars_by[s], vol_by[s] = b, v
                    funding_by[s] = {t0 + k * 8 * HOUR: rng.gauss(0.0001, 0.0003) for k in range(n // 8)}
                cache[key] = (bars_by, funding_by, vol_by)
            return cache[key]

        def call(tpl, bars_by, funding_by, params, vol_by):
            if tpl.get("needs_volume"):
                return tpl["family"](bars_by, funding_by, params, None, vol_by)
            return tpl["family"](bars_by, funding_by, params)

        for name, tpl in catalogue.TEMPLATES.items():
            if not tpl.get("cross_sectional"):
                continue
            bars_by, funding_by, vol_by = market(catalogue.universe(name))
            ref = catalogue.universe(name)[0]
            for params in tpl["grid"]:
                full = call(tpl, bars_by, funding_by, params, vol_by)
                self.assertTrue(any(any(full[s]) for s in full), f"{name} {params} never takes a position")
                for cut_i in (24 * 7, 24 * 60, 24 * 61 + 5, 24 * 130):
                    cut = bars_by[ref][cut_i][0]
                    pb = {s: [(ts, o, c) if ts <= cut else (ts, o * 1000, c * 1000) for ts, o, c in b]
                          for s, b in bars_by.items()}
                    pv = {s: {k: (q if k <= cut else q * 1000) for k, q in v.items()} for s, v in vol_by.items()}
                    got = call(tpl, pb, funding_by, params, pv)
                    for s in bars_by:
                        self.assertEqual(full[s][:cut_i + 1], got[s][:cut_i + 1],
                                         f"{name} {params} looks ahead on {s} (cut {cut_i})")


class ProtocolV2(Env):
    """research/PROTOCOL_V2.md: train gate, pre-validation gate, batch-level (order-independent) DSR."""

    def _val_reads(self, eid):
        return self.db.one("SELECT COUNT(*) FROM datasets WHERE exp_id=? AND split='validation'", eid)[0]

    def test_batch_barrier_and_order_independent_dsr(self):
        pipeline.discover_catalogue(self.db)
        self.approve("day_of_week", "hour_of_day")
        fleet.strategy_pass(self.db)
        b = pipeline.batch_of(self.db, "E_day_of_week_p2")
        self.assertEqual(b["exp_ids"], ["E_day_of_week_p2", "E_hour_of_day_p2"])
        self.assertIn("cost|E_hour_of_day_p2", jobs.get(self.db, "validate|E_day_of_week_p2")["depends_on"])
        # run day_of_week as far as it can go first: it must stop before validation until hour_of_day's cost is done
        ag = {a.name: a for a in fleet.agents(self.db_path)}
        for _ in range(10):
            for n in ("data-1", "backtest-1", "cost-1", "adversarial-1", "validation-1"):
                job = jobs.claim(self.db, n, ag[n].kinds)
                if job and job["exp_id"] != "E_day_of_week_p2":
                    self.db.con.execute("UPDATE jobs SET status='queued', lease_owner=NULL, attempts=attempts-1 "
                                        "WHERE job_id=?", (job["job_id"],))          # hold the other member back
                elif job:
                    ag[n]._run(self.db, job) if ag[n].counters else (ag[n]._load_counters(self.db),
                                                                      ag[n]._run(self.db, job))
        self.assertEqual(jobs.get(self.db, "validate|E_day_of_week_p2")["status"], "blocked")
        self.assertEqual(self._val_reads("E_day_of_week_p2"), 0)
        c = self.drain([a for a in fleet.agents(self.db_path) if a.kinds])
        self.assertEqual(c["failed"], 0, c)
        val = pipeline.load_artifact("E_day_of_week_p2", "validate")
        self.assertEqual(val["trials_counted"], 4)                    # 2 batch members x 2 variants, nothing earlier
        # a later batch adds trials; the first batch's trial set does not change
        self.approve("vol_managed_long")
        fleet.strategy_pass(self.db)
        self.drain([a for a in fleet.agents(self.db_path) if a.kinds])
        spec = json.loads(registry.latest(self.db, "E_day_of_week_p2")["spec_json"])
        self.assertEqual(len(pipeline.dsr_trials(self.db, "E_day_of_week_p2", spec)), 4)
        later = pipeline.batch_of(self.db, "E_vol_managed_long_p2")
        self.assertEqual(later["trial_cutoff_id"], 4)
        self.assertEqual(len(pipeline.dsr_trials(self.db, "E_vol_managed_long_p2",
                                                 json.loads(registry.latest(self.db, "E_vol_managed_long_p2")
                                                            ["spec_json"]))), 6)

    def test_train_gate_rejects_without_reading_validation(self):
        pipeline.discover_catalogue(self.db)
        self.approve("day_of_week")
        fleet.strategy_pass(self.db)
        real = pipeline._benchmark

        def strong_benchmark(*a, **k):
            m = real(*a, **k)
            m["net_sharpe_ann"] = 99.0
            return m
        with mock.patch.object(pipeline, "_benchmark", strong_benchmark):
            self.drain([a for a in fleet.agents(self.db_path) if a.kinds])
        eid = "E_day_of_week_p2"
        self.assertEqual(lifecycle.state(self.db, eid), "REJECTED")
        self.assertEqual(self._val_reads(eid), 0)
        r = self.db.one("SELECT verdict FROM results WHERE exp_id=?", eid)["verdict"]
        self.assertTrue(r.startswith("REJECTED at train gate"), r)
        self.assertIn("buy-and-hold", r)

    def test_placebo_gate_rejects_before_validation(self):
        pipeline.discover_catalogue(self.db)
        self.approve("day_of_week")
        fleet.strategy_pass(self.db)
        fake = lambda *a, **k: {"actual": 1.0, "p": 0.5, "n": 5, "placebo_mean": 1.2}  # noqa: E731
        with mock.patch.object(pipeline.adversarial, "placebo", fake):
            self.drain([a for a in fleet.agents(self.db_path) if a.kinds])
        eid = "E_day_of_week_p2"
        self.assertEqual(lifecycle.state(self.db, eid), "REJECTED")
        self.assertEqual(self._val_reads(eid), 0)
        r = self.db.one("SELECT verdict FROM results WHERE exp_id=?", eid)["verdict"]
        self.assertIn("REJECTED before validation", r)
        self.assertIn("placebo p < 0.1", r)

    def test_v1_specs_keep_v1_dsr_rule(self):
        self.db.append("trials", exp_id="X", ts=1, variant=0, split="train", sharpe_daily=0.1, n_days=10,
                       net_total=0.0, params={})
        self.assertEqual(len(pipeline.dsr_trials(self.db, "any", {"protocol_version": 1})), 1)
        with self.assertRaises(pipeline.StepError):
            pipeline.dsr_trials(self.db, "unbatched", {"protocol_version": 2})


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
        self.assertEqual(jobs.get(self.db, "data|E_day_of_week_p2")["status"], "done")

    def test_resource_limits(self):
        r = control.resources()
        self.assertIn("ok", r)
        with mock.patch.object(control, "ram", lambda: {"total": 16e9, "free": 0.2e9, "load_pct": 99}):
            self.assertFalse(control.resources()["ok"])
        with mock.patch.object(control, "ram", lambda: {"total": 16e9, "free": 8e9, "load_pct": 50}):
            self.assertEqual(control.resources()["ok"], control.ops.disk()["free_ok"])

    def test_supervised_fleet_runs_in_parallel_and_stops_on_request(self):
        """Real supervisor threads, heavy steps in worker processes; a stop request ends the run gracefully."""
        fleet.PROCESSES = True                                       # restored by the patch in tearDown
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
        pids = {json.loads(r[0]).get("pid") for r in self.db.q("SELECT result FROM jobs WHERE kind IN "
                                                              "('backtest','cost','adversarial','validate')")}
        self.assertNotIn(None, pids)                                    # every heavy step ran in a worker process
        self.assertNotIn(os.getpid(), pids)
        roles = {r[0] for r in self.db.q("SELECT role FROM heartbeats WHERE role IS NOT NULL")}
        self.assertGreaterEqual(len(roles), 6)
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='system.stopped'"))


if __name__ == "__main__":
    unittest.main()
