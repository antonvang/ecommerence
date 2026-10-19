"""The automatic exploration lane (research/PROTOCOL_V3.md amendments 10, 10a, 10b): its own window explore0 only,
approved families only, no registry rows or alpha, only evaluated variants count as tried, the fixed grid then drawn
variants with coin baskets, scanner focus coins, the weekly cap, the 10b network dates, one job at a time, daily
proposals with the number of variants tried, and the fleet wiring."""
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
NOW = int(datetime(2026, 12, 2, 12, tzinfo=timezone.utc).timestamp())       # a Wednesday, the network open again
GAP = int(datetime(2026, 11, 1, 12, tzinfo=timezone.utc).timestamp())       # pm_lp's holdout: no lane request
EARLY = int(datetime(2026, 10, 20, 12, tzinfo=timezone.utc).timestamp())    # before 10-24: the one-time download
FORMAL = ("experiments", "transitions", "results", "trials", "approvals", "alpha_ledger", "datasets", "sim_orders",
          "sim_fills", "sim_equity", "risk_events")
COINS = ("AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT", "FFFUSDT", "GGGUSDT")
SMALL = {"fcarry": {"carry_filter": {"lookback_days": [3, 7], "enter_apr": [0.05, 0.219]},
                    "carry_floor": {"days": [7], "q": [0.8]}}}
REAL_ELIGIBLE, REAL_GRIDS = explore.eligible, explore.GRIDS


def synthetic(coins=COINS, days=60, rate=0.0003):
    """Flat spot/perp ratio with a little noise and positive funding every 8 h (cost convention: minus the rate)."""
    bars, funding = {}, {}
    for j, s in enumerate(coins):
        rows = []
        for h in range(days * 24):
            x = 1.0 + 0.0002 * math.sin(h / 7.0 + j)
            rows.append((T0 + h * HOUR, x, x + 0.00005 * math.cos(h / 5.0 + j)))
        bars[s] = rows
        funding[s] = {T0 + h * HOUR: -(rate + 0.0001 * math.sin(h / 50.0 + j)) for h in range(0, days * 24, 8)}
    return bars, funding, [], {"files": 0, "digest": "synthetic"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labexplore")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        jobs.init(self.db)
        self.clock = [NOW]
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch.object(data, "CACHE", os.path.join(self.tmp, "cache")),
                  mock.patch.object(explore, "GRIDS", SMALL),
                  mock.patch.object(explore, "eligible", lambda db: ["fcarry"]),
                  mock.patch.object(explore.time, "time", lambda: self.clock[0]),
                  mock.patch.object(data, "CLOCK", lambda: self.clock[0])]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def counts(self):
        return {t: self.db.one(f"SELECT COUNT(*) FROM {t}")[0] for t in FORMAL}

    def run_explore(self, load=lambda fam: synthetic()):
        return explore.step_explore(self.db, {"job_id": "x", "payload": {"family": "fcarry"}}, "backtest-1",
                                    load=load)

    def tried(self):
        return explore.tried(self.db)


class TheLaneReadsOnlyExplore0(Base):
    def test_explore0_lies_before_the_families_windows_and_is_not_reserved(self):
        a, b = data.window(explore.SPLIT)
        self.assertEqual(datetime.fromtimestamp(a, timezone.utc).strftime("%Y-%m"), "2020-03")
        self.assertLess(b, data.window("train3")[0])
        self.assertLess(b, data.RESERVED_FROM)

    def test_every_other_window_is_refused(self):
        fam = {"universe": {"base": "8"}, "instrument_model": {"type": "spot_perp_ratio"}}
        for split in ("train3", "validation3", "holdout", "train", "validation", "fwd202612m12"):
            with self.assertRaises(data.ReservedData):
                explore._guard(split)
            with self.assertRaises(data.ReservedData):
                explore._files(fam, split)

    def test_downloading_and_cached_reads_name_only_explore0(self):
        seen = []

        def files(sym, split, get=None):
            seen.append(split)
            return {"klines": [], "funding": []}

        def spot(sym, split, get=None):
            seen.append(split)
            return []

        def paths(sym, split, spot=False, delivery=False):
            seen.append(split)
            return {"klines": [], "funding": [], "spot": []}
        fam = {"universe": {"base": "8"}, "instrument_model": {"type": "spot_perp_ratio"}}
        fetchable = [(families.SPOT, explore.SPLIT, "u", "p")]
        with mock.patch.object(data, "files_for", files), mock.patch.object(data, "spot_files_for", spot), \
                mock.patch.object(families, "missing", lambda *a, **k: fetchable):
            explore._files(fam, explore.SPLIT, get=lambda u: b"", now=EARLY)            # download mode
        with mock.patch.object(data, "expected_paths", paths), \
                mock.patch.object(families, "missing", lambda *a, **k: fetchable):
            explore._files(fam, explore.SPLIT, now=GAP)                                   # cached mode
        self.assertEqual(set(seen), {explore.SPLIT})
        self.assertEqual(len(seen), 3 * len(explore.universe(fam)))

    def test_the_lab_gateway_never_serves_the_lane_window(self):
        g = gateway.Gateway(self.db, "unit")
        self.db.append("experiments", exp_id="E_x", version=1, created_ts=0, mechanism_tag="t", fingerprint="f",
                       spec_json={})
        self.db.append("transitions", exp_id="E_x", ts=0, from_state=None, to_state="SCREENING", actor="unit",
                       reason="fixture")
        with self.assertRaises(gateway.AccessRefused):
            g.access("E_x", explore.SPLIT, [], (0, 1), "unit")

    def test_the_universe_is_the_union_of_the_lab_coin_lists(self):
        u = explore.universe({"instrument_model": {"type": "spot_perp_ratio"}})
        self.assertTrue(set(data.UNIVERSE_30) | set(data.UNIVERSE_30_V3) | set(data.UNIVERSE_CM16) <= set(u))
        d = explore.universe({"instrument_model": {"type": "spot_delivery_ratio"}, "universe": {"base": "30v3"}})
        self.assertNotIn("BTCUSDT", d)


class Network10b(Base):
    URL = "https://data.binance.vision/data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-2020-01.zip"

    def test_the_dates(self):
        um, spot, cm = families.KIND_SOURCE["klines"], families.SPOT, families.KIND_SOURCE["delivery"]
        for now, ok in ((EARLY, True), (explore.FETCH_UNTIL, False), (GAP, False), (explore.FETCH_FROM, True)):
            self.assertEqual((explore.fetch_allowed(um, now), explore.fetch_allowed(spot, now)), (ok, ok), now)
        self.assertFalse(explore.fetch_allowed(cm, explore.FETCH_FROM))
        self.assertTrue(explore.fetch_allowed(cm, families.EMBARGO_UNTIL))
        self.assertFalse(explore.fetch_allowed("binance_um_metrics", EARLY))

    def test_in_pm_lps_holdout_the_lane_makes_no_request(self):
        calls = []
        self.clock[0] = GAP
        get = explore.guarded_get(fetch=lambda u: calls.append(u))
        with self.assertRaises(families.Embargoed):
            get(self.URL)
        with self.assertRaises(families.Embargoed):
            get("https://example.com/x.zip")
        self.assertEqual(calls, [])
        fam = {"universe": {"base": "8"}, "instrument_model": {"type": "spot_perp_ratio"}}
        with mock.patch.object(families, "_urlopen", lambda u: calls.append(u)):
            bars, _, _, inputs = explore._files(fam, explore.SPLIT)                    # empty cache: reads nothing
        self.assertEqual((calls, bars, inputs["files"]), ([], {}, 0))

    def test_before_10_24_it_fetches_through_the_slots_and_remembers_a_404(self):
        self.clock[0] = EARLY
        got = []
        self.assertEqual(explore.guarded_get(fetch=lambda u: got.append(u) or b"zip")(self.URL), b"zip")
        self.assertEqual(got, [self.URL])

        def gone(u):
            raise families.urllib.error.HTTPError(u, 404, "gone", None, None)
        with self.assertRaises(families.urllib.error.HTTPError):
            explore.guarded_get(fetch=gone)(self.URL.replace("01.zip", "02.zip"))
        self.assertIn(self.URL.replace("01.zip", "02.zip"), families.absent())
        self.assertFalse(explore.fetch_allowed(families.KIND_SOURCE["delivery"]))       # COIN-M: from 11-28 only


class TriedMeansEvaluated(Base):
    def test_nothing_formal_changes_and_the_event_lists_what_was_evaluated(self):
        before = self.counts()
        res = self.run_explore()
        self.assertEqual(res["evaluated"], explore.BATCH)
        self.assertEqual(self.counts(), before)
        ev = json.loads(self.db.one("SELECT payload FROM events WHERE kind='research.explore'")[0])
        self.assertFalse(ev["decisional"])
        self.assertEqual(ev["label"], "EXPLORATORY_LANE")
        self.assertEqual(len(ev["variants"]), explore.BATCH)
        grid = [explore.key("fcarry", f, p) for f, p in explore.variants("fcarry")]
        self.assertEqual(ev["variants"][:len(grid)], grid)                              # the fixed grid first
        self.assertTrue(all("|" in k for k in ev["variants"][len(grid):]))              # then drawn baskets

    def test_too_few_good_coins_records_no_variant(self):
        res = self.run_explore(load=lambda fam: synthetic(coins=COINS[:2]))
        self.assertEqual(res["evaluated"], 0)
        self.assertIn("fewer than", res["why"])
        self.assertEqual(self.tried(), set())                                          # nothing used up
        self.assertEqual(self.run_explore()["evaluated"], explore.BATCH)

    def test_the_lane_keeps_going_past_the_grid_and_never_repeats(self):
        for i in range(4):
            self.clock[0] = NOW + i * HOUR
            self.run_explore()
        keys = sorted(self.tried())
        self.assertEqual(len(keys), 4 * explore.BATCH)
        self.assertEqual(len(set(keys)), len(keys))


class Drawing(Base):
    def test_draws_are_deterministic_inside_the_spaces_and_baskets_are_big_enough(self):
        for fid in ("fcarry", "dbasis"):
            for i in range(200):
                d = explore.draw(fid, i, COINS)
                self.assertEqual(d, explore.draw(fid, i, COINS))
                fn, p, basket = d
                self.assertGreaterEqual(len(basket), explore.MIN_COINS)
                self.assertTrue(set(basket) <= set(COINS))
                for name, spec in explore.SPACES[fid][fn].items():
                    self.assertTrue(spec[1] <= p[name] <= spec[2], (fid, fn, name, p[name]))
                self.assertLessEqual(p.get("lookback_days", p.get("days", 1)), 14)

    def test_scanner_focus_coins_come_first_in_about_half_the_baskets(self):
        coins = COINS + ("ZZZUSDT",)
        with_focus = sum(1 for i in range(400) if "ZZZUSDT" in explore.draw("fcarry", i, coins, focus={"ZZZUSDT"})[2])
        without = sum(1 for i in range(400) if "ZZZUSDT" in explore.draw("fcarry", i, coins)[2])
        self.assertGreater(with_focus, without)

    def test_focus_reads_flagged_perp_premium_of_the_last_week(self):
        for ts, metric, flagged, inst in ((NOW - DAY, "perp_premium", 1, "XRPUSDT"),
                                          (NOW - 9 * DAY, "perp_premium", 1, "OLDUSDT"),
                                          (NOW - DAY, "perp_premium", 0, "NOTUSDT"),
                                          (NOW - DAY, "cross_venue_gap", 1, "GAPUSDT")):
            self.db.append("observations", ts=ts, detector="pricing_constraint/2", source="unit", instrument=inst,
                           metric=metric, value=0.01, threshold=0.001, flagged=flagged, payload={})
        self.assertEqual(explore.focus(self.db, NOW), {"XRPUSDT"})


class TheChecksDiscriminate(Base):
    def test_no_funding_means_no_candidate(self):
        fam = families.load("fcarry")
        bars, funding, _, _ = synthetic(rate=0.0)
        for fn, p in explore.variants("fcarry"):
            r = explore.evaluate("fcarry", fam, fn, p, bars, {s: {} for s in funding})
            self.assertFalse(r["candidate"], r["key"])
            self.assertFalse(r["checks"]["attribution holds"], r["key"])

    def test_the_f2_functions_run_in_the_lane_on_2020_synthetic_bars(self):
        from lab.families import dbasis
        fam = families.load(os.path.join(families.FAMILY_DIR, "drafts", "dbasis.json"))
        bars, _ = dbasis.synthetic(coins=COINS[:5], start=(2020, 3), months=12)
        with mock.patch.object(explore, "GRIDS", REAL_GRIDS):
            grid = explore.variants("dbasis")
        self.assertEqual(len(grid), 17)
        for fn in ("basis_threshold", "basis_hold_to_roll", "basis_cross_section"):
            p = next(prm for f, prm in grid if f == fn)
            r = explore.evaluate("dbasis", fam, fn, p, bars, {s: {} for s in bars})
            self.assertEqual(r["label"], "EXPLORATORY_LANE")
            self.assertIn("gates", r["attribution"])


class CapAndProposals(Base):
    def test_the_weekly_cap(self):
        with mock.patch.object(explore, "WEEKLY_MAX", 3):
            self.assertEqual(self.run_explore()["evaluated"], 3)
            self.assertEqual(self.run_explore()["why"], "weekly cap reached")
            self.clock[0] = NOW + 7 * DAY
            self.assertEqual(self.run_explore()["evaluated"], 3)

    def test_at_most_three_by_sharpe_with_the_number_tried(self):
        rs = [{"key": f"k{i}", "family": "fcarry", "function": "f", "params": {}, "net_sharpe_ann": float(i),
               "net_total": 1.0, "thirds": [1, 1, 1], "checks": {}, "candidate": i % 2 == 0} for i in range(10)]
        out = explore.proposals(rs, 123)
        self.assertEqual([x["key"] for x in out], ["k8", "k6", "k4"])
        self.assertTrue(all(x["variants_tried_total"] == 123 and x["label"] == "EXPLORATORY_LANE" for x in out))

    def test_the_daily_report_waits_lists_the_best_and_drops_an_ended_approval(self):
        self.run_explore()
        day = explore._day(NOW)
        with self.assertRaises(pipeline.Deferred):
            explore.step_report(self.db, {"payload": {"day": day}}, "report-1")
        self.clock[0] = explore._day_start(day) + DAY + explore.REPORT_DELAY_S
        res = explore.step_report(self.db, {"payload": {"day": day}}, "report-1")
        self.assertEqual(res["proposals"], explore.PROPOSALS_MAX)                      # the synthetic carry is easy
        self.assertEqual(res["variants_tried_total"], explore.BATCH)
        with open(os.path.join(pipeline.ARTIFACTS, "_explore", f"{day}.json")) as f:
            sr = [p["net_sharpe_ann"] for p in json.load(f)["proposals"]]
        self.assertEqual(sr, sorted(sr, reverse=True))
        with mock.patch.object(explore, "eligible", lambda db: []):
            self.assertEqual(explore.step_report(self.db, {"payload": {"day": day}}, "report-1")["proposals"], 0)


class Scheduling(Base):
    def ready(self):
        return mock.patch.object(explore, "_ready", lambda fam, now=None: True)

    def test_one_lane_job_at_a_time_at_most_hourly_at_the_lowest_priority(self):
        with self.ready():
            self.assertEqual(explore.enqueue(self.db, now=NOW), 1)
            self.assertEqual(explore.enqueue(self.db, now=NOW + 10), 0)                 # one is queued
            j = self.db.one("SELECT job_id, priority FROM jobs WHERE kind='explore'")
            self.assertEqual(j[1], explore.PRIORITY)
            self.assertGreater(explore.PRIORITY, families.PRIORITY)
            self.db.con.execute("UPDATE jobs SET status='done' WHERE job_id=?", (j[0],))
            self.assertEqual(explore.enqueue(self.db, now=NOW + 600), 0)                # done, but within the hour
            self.assertEqual(explore.enqueue(self.db, now=NOW + HOUR + 1), 1)

    def test_round_robin_between_families(self):
        with self.ready(), mock.patch.object(explore, "eligible", lambda db: ["dbasis", "fcarry"]), \
                mock.patch.object(families, "load", lambda fid: {"instrument_model": {"type": "spot_perp_ratio"}}):
            fams = []
            for i in range(4):
                explore.enqueue(self.db, now=NOW + i * (HOUR + 1))
                fams.append(self.db.one("SELECT json_extract(payload, '$.family') FROM jobs WHERE kind='explore' "
                                        "ORDER BY created_ts DESC LIMIT 1")[0])
                self.db.con.execute("UPDATE jobs SET status='done' WHERE kind='explore'")
        self.assertEqual(fams, ["dbasis", "fcarry", "dbasis", "fcarry"])

    def test_no_job_while_the_lane_could_only_wait(self):
        self.clock[0] = GAP
        gone = [(families.SPOT, explore.SPLIT, "u", os.path.join("x", f"{s}-1h-2020-01.zip"))
                for s in explore.universe(families.load("fcarry"))]
        with mock.patch.object(families, "missing", lambda *a, **k: gone):
            self.assertEqual(explore.enqueue(self.db, now=GAP), 0)
        with mock.patch.object(families, "missing", lambda *a, **k: gone[explore.MIN_COINS:]):   # 5 coins cached
            self.assertEqual(explore.enqueue(self.db, now=GAP), 1)

    def test_the_report_of_the_last_day_is_queued_after_it(self):
        self.run_explore()
        with mock.patch.object(explore, "_ready", lambda fam, now=None: False):
            explore.enqueue(self.db, now=NOW + DAY)
        r = jobs.get(self.db, f"explore_report|{explore._day(NOW)}")
        self.assertEqual(r["kind"], "explore_report")
        self.assertEqual(r["next_run"], explore._day_start(explore._day(NOW)) + DAY + explore.REPORT_DELAY_S)


class Approval(Base):
    def test_only_families_with_a_valid_approval(self):
        with mock.patch.object(explore, "eligible", REAL_ELIGIBLE):
            explore._ELIGIBLE.clear()
            with mock.patch.object(families, "binding_approval", lambda db, fid: None):
                self.assertEqual(explore.eligible(self.db), [])
            explore._ELIGIBLE.clear()
            with mock.patch.object(families, "binding_approval",
                                   lambda db, fid: {"event_id": 1} if fid == "fcarry" else None):
                self.assertEqual(explore.eligible(self.db), ["fcarry"])
            explore._ELIGIBLE.clear()

    def test_an_unapproved_family_is_never_explored(self):
        with mock.patch.object(explore, "eligible", REAL_ELIGIBLE):          # a fresh registry: no family approval
            explore._ELIGIBLE.clear()
            self.assertEqual(explore.enqueue(self.db, now=NOW), 0)
            res = explore.step_explore(self.db, {"payload": {"family": "fcarry"}}, "b")
            explore._ELIGIBLE.clear()
        self.assertIn("skipped", res)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='research.explore'")[0], 0)


class FleetWiring(Base):
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
