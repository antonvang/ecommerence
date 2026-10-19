"""The automatic exploration lane (research/PROTOCOL_V3.md amendment 10): its own window explore0 only, approved
families only, no registry rows or alpha, the weekly cap, the download embargo, at most 3 proposals with the number
of variants tried, and the fleet wiring."""
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, data as gateway, explore, families, fleet, jobs, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402

HOUR, DAY = 3600, 86400
T0 = int(datetime(2020, 3, 2, tzinfo=timezone.utc).timestamp())
NOW = int(datetime(2026, 12, 2, 12, tzinfo=timezone.utc).timestamp())       # a Wednesday, after the embargo
FORMAL = ("experiments", "transitions", "results", "trials", "approvals", "alpha_ledger", "datasets", "sim_orders",
          "sim_fills", "sim_equity", "risk_events")
REAL_ELIGIBLE, REAL_GRIDS = explore.eligible, explore.GRIDS
SMALL = {"fcarry": {"carry_filter": {"lookback_days": [3, 7], "enter_apr": [0.05, 0.219]},
                    "carry_floor": {"days": [7], "q": [0.8]}}}


def synthetic(coins=("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT"), days=90, rate=0.0003):
    """Flat spot/perp ratio with a little noise and positive funding every 8 h (cost convention: minus the rate)."""
    bars, funding = {}, {}
    for j, s in enumerate(coins):
        rows = []
        for h in range(days * 24):
            ts = T0 + h * HOUR
            x = 1.0 + 0.0002 * math.sin(h / 7.0 + j)
            rows.append((ts, x, x + 0.00005 * math.cos(h / 5.0 + j)))
        bars[s] = rows
        funding[s] = {T0 + h * HOUR: -(rate + 0.0001 * math.sin(h / 50.0 + j)) for h in range(0, days * 24, 8)}
    return bars, funding, []


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labexplore")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        jobs.init(self.db)
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch.object(explore, "GRIDS", SMALL),
                  mock.patch.object(explore, "eligible", lambda db: ["fcarry"]),
                  mock.patch.object(explore.time, "time", lambda: NOW),
                  mock.patch.object(data, "CLOCK", lambda: NOW)]                      # after the embargo
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def counts(self):
        return {t: self.db.one(f"SELECT COUNT(*) FROM {t}")[0] for t in FORMAL}

    def run_explore(self, wk=None, load=lambda fam: synthetic()):
        job = {"job_id": "x", "payload": {"family": "fcarry", "week": wk or explore.week(NOW)}}
        return explore.step_explore(self.db, job, "backtest-1", load=load)


class TheLaneReadsOnlyExplore0(Base):
    def test_explore0_lies_before_the_families_windows_and_is_not_reserved(self):
        a, b = data.window(explore.SPLIT)
        self.assertEqual(datetime.fromtimestamp(a, timezone.utc).strftime("%Y-%m"), "2020-01")
        self.assertLess(b, data.window("train3")[0])
        self.assertLess(b, data.RESERVED_FROM)

    def test_every_other_window_is_refused(self):
        for split in ("train3", "validation3", "holdout", "train", "validation", "fwd202612m12"):
            with self.assertRaises(data.ReservedData):
                explore._guard(split)
            with self.assertRaises(data.ReservedData):
                explore._files({"universe": {"base": "8"}, "instrument_model": {"type": "spot_perp_ratio"}},
                               split, None)

    def test_the_data_access_names_only_explore0(self):
        seen = []

        def files(sym, split, get=None):
            seen.append(split)
            return {"klines": [], "funding": []}

        def spot(sym, split, get=None):
            seen.append(split)
            return []
        fam = {"universe": {"base": "8"}, "instrument_model": {"type": "spot_perp_ratio"}}
        with mock.patch.object(data, "files_for", files), mock.patch.object(data, "spot_files_for", spot), \
                mock.patch.object(families, "blocked", lambda *a, **k: []):
            bars, funding, excluded = explore._files(fam, explore.SPLIT, None)
        self.assertEqual(set(seen), {explore.SPLIT})
        self.assertEqual(len(seen), 2 * len(data.UNIVERSE))

    def test_the_lab_gateway_never_serves_the_lane_window(self):
        g = gateway.Gateway(self.db, "unit")
        self.db.append("experiments", exp_id="E_x", version=1, created_ts=0, mechanism_tag="t", fingerprint="f",
                       spec_json={})
        self.db.append("transitions", exp_id="E_x", ts=0, from_state=None, to_state="SCREENING", actor="unit",
                       reason="fixture")
        with self.assertRaises(gateway.AccessRefused):
            g.access("E_x", explore.SPLIT, [], (0, 1), "unit")


class EmbargoAndNetwork(Base):
    def test_before_2026_11_28_the_job_waits_and_fetches_nothing(self):
        calls = []
        fam = {"universe": {"base": "8"}, "instrument_model": {"type": "spot_perp_ratio"}, "costs": {}}
        with mock.patch.object(data, "CLOCK", lambda: families.EMBARGO_UNTIL - 3600), \
                mock.patch.object(data, "CACHE", os.path.join(self.tmp, "cache")), \
                mock.patch.object(families, "load", lambda fid: fam), \
                mock.patch.object(families, "_urlopen", lambda url: calls.append(url)):
            with self.assertRaises(pipeline.Deferred) as c:
                explore.step_explore(self.db, {"job_id": "x", "payload": {"family": "fcarry",
                                                                           "week": explore.week(NOW)}}, "backtest-1")
        self.assertEqual(c.exception.until, families.EMBARGO_UNTIL)
        self.assertEqual(calls, [])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='research.explore'")[0], 0)


class NothingFormalChanges(Base):
    def test_evaluation_records_only_the_lane_event_and_artifact(self):
        before = self.counts()
        res = self.run_explore()
        self.assertEqual(res["variants"], len(explore.variants("fcarry")))
        self.assertEqual(res["evaluated"], res["variants"])
        self.assertEqual(self.counts(), before)
        ev = json.loads(self.db.one("SELECT payload FROM events WHERE kind='research.explore'")[0])
        self.assertFalse(ev["decisional"])
        self.assertEqual(ev["label"], "EXPLORATORY_LANE")
        self.assertEqual(sorted(ev["variants"]), sorted(explore.key("fcarry", f, p)
                                                        for f, p in explore.variants("fcarry")))
        with open(os.path.join(pipeline.ARTIFACTS, "_explore", explore.week(NOW), "fcarry.json")) as f:
            art = json.load(f)
        self.assertEqual(art["split"], "explore0")
        for r in art["results"]:
            self.assertEqual(set(r["checks"]), {"net Sharpe >= 1.0 at 2x costs", "attribution holds",
                                                "positive in >= 2 of 3 thirds"})
            self.assertEqual(r["candidate"], all(r["checks"].values()))

    def test_a_variant_is_evaluated_once_and_the_grid_ends(self):
        self.run_explore()
        again = self.run_explore()
        self.assertEqual(again["variants"], 0)
        self.assertEqual(again["why"], "grid done")
        self.assertEqual(explore.enqueue(self.db, now=NOW), 0)

    def test_the_weekly_cap(self):
        with mock.patch.object(explore, "WEEKLY_MAX", 3):
            self.assertEqual(self.run_explore()["variants"], 3)
            capped = self.run_explore()
        self.assertEqual(capped["variants"], 0)
        self.assertEqual(capped["why"], "weekly cap reached")
        next_week = explore.week(NOW + 7 * DAY)
        with mock.patch.object(explore, "WEEKLY_MAX", 3), \
                mock.patch.object(explore.time, "time", lambda: NOW + 7 * DAY):
            self.assertEqual(self.run_explore(next_week)["variants"], 2)

    def test_too_few_good_coins_evaluates_nothing(self):
        res = self.run_explore(load=lambda fam: ({"AAAUSDT": synthetic()[0]["AAAUSDT"]}, {"AAAUSDT": {}}, ["B"]))
        self.assertEqual(res["evaluated"], 0)
        why = json.loads(self.db.one("SELECT payload FROM events WHERE kind='research.explore'")[0])["why"]
        self.assertIn("fewer than", why)


class TheChecksDiscriminate(Base):
    def test_no_funding_means_no_candidate(self):
        fam = families.load("fcarry")
        bars, funding, _ = synthetic(rate=0.0)
        funding = {s: {} for s in funding}
        for fn, p in explore.variants("fcarry"):
            r = explore.evaluate("fcarry", fam, fn, p, bars, funding)
            self.assertFalse(r["candidate"], r["key"])
            self.assertFalse(r["checks"]["attribution holds"], r["key"])

    def test_the_f2_functions_run_in_the_lane_on_2020_synthetic_bars(self):
        from lab.families import dbasis
        fam = families.load(os.path.join(families.FAMILY_DIR, "drafts", "dbasis.json"))
        bars, _ = dbasis.synthetic(coins=("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT"), start=(2020, 3),
                                   months=12)
        with mock.patch.object(explore, "GRIDS", REAL_GRIDS):
            grid = explore.variants("dbasis")
        self.assertEqual(len(grid), 17)
        for fn in ("basis_threshold", "basis_hold_to_roll", "basis_cross_section"):
            p = next(prm for f, prm in grid if f == fn)
            r = explore.evaluate("dbasis", fam, fn, p, bars, {s: {} for s in bars})
            self.assertEqual(r["label"], "EXPLORATORY_LANE")
            self.assertIn("gates", r["attribution"])


class Proposals(Base):
    def test_at_most_three_with_the_number_tried(self):
        rs = [{"key": f"k{i}", "family": "fcarry", "function": "f", "params": {}, "net_sharpe_ann": float(i),
               "net_total": 1.0, "thirds": [1, 1, 1], "checks": {}, "candidate": i % 2 == 0} for i in range(10)]
        out = explore.proposals(rs, 123)
        self.assertEqual([x["key"] for x in out], ["k8", "k6", "k4"])
        self.assertTrue(all(x["variants_tried_total"] == 123 and x["label"] == "EXPLORATORY_LANE" for x in out))

    def test_the_report_waits_for_the_week_and_lists_the_candidates(self):
        self.run_explore()
        wk = explore.week(NOW)
        with self.assertRaises(pipeline.StepError):
            explore.step_report(self.db, {"payload": {"week": wk}}, "report-1")
        with mock.patch.object(explore.time, "time", lambda: explore.week_bounds(wk)[1] + 3600):
            res = explore.step_report(self.db, {"payload": {"week": wk}}, "report-1")
        self.assertLessEqual(res["proposals"], explore.PROPOSALS_MAX)
        self.assertEqual(res["variants_tried_total"], len(explore.variants("fcarry")))
        ev = json.loads(self.db.one("SELECT payload FROM events WHERE kind='research.explore_proposals'")[0])
        self.assertFalse(ev["decisional"])


class Scheduling(Base):
    def test_jobs_are_queued_at_the_lowest_priority_and_the_report_after_the_week(self):
        self.assertEqual(explore.enqueue(self.db, now=NOW), 1)
        j = jobs.get(self.db, f"explore|{explore.week(NOW)}|fcarry")
        self.assertEqual((j["kind"], j["priority"]), ("explore", explore.PRIORITY))
        self.assertGreater(explore.PRIORITY, families.PRIORITY)
        self.run_explore()
        later = NOW + 7 * DAY
        explore.enqueue(self.db, now=later)
        r = jobs.get(self.db, f"explore_report|{explore.week(NOW)}")
        self.assertEqual(r["kind"], "explore_report")
        self.assertGreaterEqual(r["next_run"], explore.week_bounds(explore.week(NOW))[1])

    def test_the_fleet_plans_the_lane_at_most_hourly(self):
        with mock.patch.object(explore, "_LAST_ENQUEUE", [0.0]):
            self.assertEqual(explore.enqueue(self.db, now=NOW, every=3600), 1)
            self.db.con.execute("DELETE FROM jobs")
            self.assertEqual(explore.enqueue(self.db, now=NOW, every=3600), 0)        # within the hour: skipped
            with mock.patch.object(explore.time, "time", lambda: NOW + 3601):
                self.assertEqual(explore.enqueue(self.db, now=NOW + 3601, every=3600), 1)

    def test_an_unapproved_family_is_never_explored(self):
        with mock.patch.object(explore, "eligible", REAL_ELIGIBLE):          # a fresh registry: no family approval
            self.assertEqual(REAL_ELIGIBLE(self.db), [])
            self.assertEqual(explore.enqueue(self.db, now=NOW), 0)
            res = explore.step_explore(self.db, {"payload": {"family": "fcarry", "week": explore.week(NOW)}}, "b")
        self.assertIn("skipped", res)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='research.explore'")[0], 0)

    def test_the_fleet_runs_the_lane_and_counts_it_as_side_work(self):
        roster = {a[0]: a[2] for a in fleet.ROSTER}
        self.assertIn("explore", roster["backtest-1"])
        self.assertIn("explore", roster["backtest-2"])
        self.assertIn("explore_report", roster["report-1"])
        self.assertIn("explore", pipeline.HANDLERS)
        self.assertIn("explore_report", pipeline.HANDLERS)
        self.assertIn("explore", command.NON_STAGE_KINDS)
        self.assertIn("explore_report", command.NON_STAGE_KINDS)


if __name__ == "__main__":
    unittest.main()
