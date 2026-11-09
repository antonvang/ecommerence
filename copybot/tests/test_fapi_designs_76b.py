"""Director order 76-B: synthetic tests of the five mechanism designs (research/desk/fapi76b). No market data, no network,
no lab.db, and no file except the design note, the register snapshot and the module sources."""
import ast
import math
import os
import random
import statistics
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.desk.fapi76b import fapi_designs_76b as dg  # noqa: E402
from research.desk.fapi76b import fapi_evaluators_76b as ev  # noqa: E402
from research.desk.fapi76b import fapi_power_76b as pw  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402
from research.tools import validation_engine as ve  # noqa: E402

NOTE = os.path.join(HERE, "research", "desk", "fapi76b", "FAPI_DESIGNS_76B.md")
DAY, HOUR = ev.DAY, ev.HOUR


def bar(t, c, r=0.01, v=1.0):
    return {"ts": t * DAY, "close": c, "high": c * (1 + r), "low": c * (1 - r), "volume": v}


def compressed(n=130, c=100.0):
    """Quiet bars ending in a long, very tight stretch, so compression holds at the end."""
    bars = [bar(i, c, 0.02) for i in range(n - 25)]
    return bars + [bar(n - 25 + i, c, 0.004 - 0.0001 * i) for i in range(25)]


class Decide(unittest.TestCase):
    def test_verdicts(self):
        rng = random.Random(1)
        self.assertEqual(ev.decide([1.0] * 10)["verdict"], ev.UNTESTABLE)
        self.assertEqual(ev.decide([rng.gauss(-0.5, 1) for _ in range(60)])["verdict"], ev.FALSIFIED)
        self.assertEqual(ev.decide([rng.gauss(2, 1) for _ in range(60)])["verdict"], ev.PASS)
        self.assertEqual(ev.decide([1.0, -0.9] * 30)["verdict"], ev.INCONCLUSIVE)

    def test_daily_means_cluster_by_utc_day(self):
        got = ev.daily_means([(DAY + 5, 1.0), (DAY + 20, 3.0), (2 * DAY + 1, 10.0)])
        self.assertEqual(got, [2.0, 10.0])


class CB1Rules(unittest.TestCase):
    def test_breakout_with_volume_after_compression_fires_up_and_down(self):
        bars = compressed() + [bar(130, 110.0, 0.02, v=5.0)]
        self.assertEqual(ev.cb1_signal_series(bars)[-1], 1)
        bars = compressed() + [bar(130, 90.0, 0.02, v=5.0)]
        self.assertEqual(ev.cb1_signal_series(bars)[-1], -1)

    def test_no_signal_without_volume_or_without_compression(self):
        self.assertEqual(ev.cb1_signal_series(compressed() + [bar(130, 110.0, 0.02, v=1.0)])[-1], 0)
        wide = [bar(i, 100.0, 0.05) for i in range(130)] + [bar(130, 120.0, 0.05, v=5.0)]
        self.assertEqual(ev.cb1_signal_series(wide)[-1], 0)

    def test_dedup_blocks_a_second_signal_inside_14_days(self):
        bars = compressed() + [bar(130, 110.0, 0.02, v=5.0)]
        bars += [bar(131 + i, 110.0, 0.002) for i in range(5)] + [bar(136, 125.0, 0.02, v=5.0)]
        s = ev.cb1_signal_series(bars)
        self.assertEqual(s[130], 1)
        self.assertEqual(s[136], 0)

    def test_direction_net_uses_delayed_entry_and_never_fills_a_gap(self):
        close_ts = 10 * DAY
        entry, ex = close_ts + HOUR, close_ts + HOUR + 72 * HOUR
        hours = [(entry, 100.0), (ex, 110.0)]
        self.assertAlmostEqual(ev.cb1_direction_net(hours, close_ts, 1, 0.003), math.log(1.1) - 0.003)
        self.assertAlmostEqual(ev.cb1_direction_net(hours, close_ts, -1, 0.003), -math.log(1.1) - 0.003)
        self.assertIsNone(ev.cb1_direction_net([(entry, 100.0)], close_ts, 1, 0.003))


class Har(unittest.TestCase):
    def rv(self, n=200, seed=3):
        rng = random.Random(seed)
        x, out = 0.0, []
        for _ in range(n):
            x = 0.9 * x + rng.gauss(0, 0.3)
            out.append(0.02 * math.exp(x))
        return out

    def test_forecast_uses_only_known_rows(self):
        rv = self.rv()
        a = ev.har_log_forecast(rv, 150)
        b = ev.har_log_forecast(rv[:151], 150)
        self.assertAlmostEqual(a, b)

    def test_too_little_history_gives_none(self):
        self.assertIsNone(ev.har_log_forecast(self.rv(60), 50))

    def test_tracks_a_persistent_series(self):
        rv = self.rv(300)
        rmse = []
        for t in range(150, 295):
            f = ev.har_log_forecast(rv, t)
            rmse.append((f - math.log(statistics.fmean(rv[t + 1:t + 4]))) ** 2)
        naive = [(math.log(statistics.fmean(rv)) - math.log(statistics.fmean(rv[t + 1:t + 4]))) ** 2 for t in range(150, 295)]
        self.assertLess(statistics.fmean(rmse), statistics.fmean(naive))


class CB1World(unittest.TestCase):
    CFG = dict(ev.CB1, n_bins=1, min_controls=2)      # a small synthetic panel; the design itself uses deciles and 5

    def panel(self, seed=5, coins=40, days=270):
        """Null world: daily range and RV are i.i.d. lognormal, and random jump days (price + volume) are independent of it.
        An event is therefore a compressed coin that happens to jump; nothing about its later RV is special."""
        rng = random.Random(seed)
        panel = {}
        for k in range(coins):
            c, rv, bars = 100.0, [], []
            for d in range(days):
                vol = 0.02 * math.exp(rng.gauss(0, 0.5))
                c *= math.exp(rng.gauss(0, vol))
                bar_ = {"ts": d * DAY, "close": c, "high": c * (1 + vol), "low": c * (1 - vol), "volume": 1.0}
                if d > 100 and rng.random() < 1 / 15:
                    c *= 1.12
                    bar_ = dict(bar_, close=c, high=c * (1 + vol), low=c * (1 - vol) / 1.12, volume=6.0)
                bars.append(bar_)
                rv.append(vol)
            panel[f"C{k}"] = {"bars": bars, "rv": rv}
        return panel

    def planted(self, panel):
        """The same world, with the 3 days after each event given 3 x RV (the bars are unchanged)."""
        out = {}
        for s, p in panel.items():
            rv = list(p["rv"])
            for t, sig in enumerate(ev.cb1_signal_series(p["bars"], self.CFG)):
                if sig:
                    for j in range(t + 1, min(t + 4, len(rv))):
                        rv[j] *= 3.0
            out[s] = {"bars": p["bars"], "rv": rv}
        return out

    def test_planted_vol_expansion_is_found_and_absent_when_not_planted(self):
        base = self.panel()
        null = ev.daily_means(ev.cb1_vol_outcomes(base, self.CFG))
        planted = ev.daily_means(ev.cb1_vol_outcomes(self.planted(base), self.CFG))
        self.assertGreater(len(null), 20)
        got, none = ev.decide(planted, min_clusters=20), ev.decide(null, min_clusters=20)
        self.assertEqual(got["verdict"], ev.PASS)
        self.assertGreater(got["mean"], 0.7)                                       # ln 3 = 1.10 minus matching noise
        self.assertLess(abs(none["mean"]), 0.2)
        self.assertNotEqual(none["verdict"], ev.PASS)

    def test_controls_must_be_compressed_too(self):
        bars = compressed() + [bar(130, 110.0, 0.02, v=5.0)]
        wide = [bar(i, 100.0, 0.05) for i in range(131)]
        self.assertTrue(ev.cb1_compressed_series(bars)[130])
        self.assertFalse(any(ev.cb1_compressed_series(wide)))


class PR1Rules(unittest.TestCase):
    CFG = dict(ev.PR1, tau=0.0015)        # the synthetic tails stay below this, so only the planted premium is an event

    def rows(self, premiums, qvol=5e6):
        return [{"ts": i * HOUR, "mark": 100 * math.exp(p), "index": 100.0, "qvol": qvol} for i, p in enumerate(premiums)]

    def test_needs_two_hours_same_sign_above_tau(self):
        s = ev.pr1_signal_series(self.rows([0.0, 0.002, 0.003, -0.003]))
        self.assertEqual(s, [0, 0, 1, 0])

    def test_decay_share_and_dedup(self):
        path = [0.0, 0.002, 0.002] + [0.0] * 7 + [0.0002] + [0.0] * 2
        events = ev.pr1_events(self.rows(path))
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]["D"], 0.9, places=6)

    def world(self, thin_decay, liquid_decay=0.8, days=60, seed=9):
        rng = random.Random(seed)
        panel = {}
        for k in range(12):
            liquid = k < 6
            qv = (5e7 if liquid else 2e6) * (1 + k / 100)
            decay = liquid_decay if liquid else thin_decay
            rows, t = [], 0
            for d in range(days):
                for _ in range(3):
                    p0 = rng.choice((1, -1)) * 0.002
                    noise = rng.gauss(0, 0.05)
                    pp = [p0, p0, p0] + [p0 * (1 - min(1.0, decay + noise))] * 8
                    for p in pp:
                        rows.append({"ts": t * HOUR, "mark": 100 * math.exp(p), "index": 100.0, "qvol": qv})
                        t += 1
                while t % 24:
                    rows.append({"ts": t * HOUR, "mark": 100.0, "index": 100.0, "qvol": qv})
                    t += 1
            panel[f"S{k}"] = rows
        return panel

    def test_contrast_found_only_when_thin_coins_decay_slower(self):
        c, l = ev.pr1_daily_contrast(self.world(thin_decay=0.5), self.CFG)
        self.assertGreater(len(c), 40)
        self.assertEqual(ev.pr1_decide(c, l)["verdict"], ev.PASS)
        c, l = ev.pr1_daily_contrast(self.world(thin_decay=0.8), self.CFG)
        self.assertNotEqual(ev.pr1_decide(c, l)["verdict"], ev.PASS)

    def test_slow_liquid_decay_blocks_a_pass(self):
        c, l = ev.pr1_daily_contrast(self.world(thin_decay=0.3, liquid_decay=0.4), self.CFG)
        self.assertEqual(ev.pr1_decide(c, l)["verdict"], ev.INCONCLUSIVE)


class LD1Rules(unittest.TestCase):
    def test_classification_and_savings(self):
        self.assertEqual([ev.ld1_classify(z) for z in (3.5, 1.0, 2.5)], ["price", "liquidity", None])
        ev_rows = [{"ts": DAY, "z_abs": 4, "rt0": 40, "rt1": 20}, {"ts": DAY, "z_abs": 1, "rt0": 30, "rt1": 10},
                   {"ts": 2 * DAY, "z_abs": 1, "rt0": 50, "rt1": 10}]
        price, liq = ev.ld1_contrast(ev_rows)
        self.assertEqual(price, [10.0])
        self.assertEqual(liq, [10.0, 20.0])


class FL1Rules(unittest.TestCase):
    def rows(self, n=700, seed=2):
        rng = random.Random(seed)
        rows = [{"ts": i * HOUR, "r": rng.gauss(0, 0.01), "oi_chg": 0.0, "close": 100.0} for i in range(n)]
        return rows

    def test_flush_needs_the_drop_and_the_oi_fall_and_enough_history(self):
        rows = self.rows()
        rows[650] = dict(rows[650], r=-0.06, oi_chg=-0.05)
        self.assertEqual(ev.fl1_signal_series(rows)[650], 1)
        rows[650] = dict(rows[650], r=-0.06, oi_chg=0.0)
        self.assertEqual(ev.fl1_signal_series(rows)[650], 0)
        self.assertEqual(sum(ev.fl1_signal_series(rows[:300])), 0)

    def test_outcome_is_net_of_cost_from_the_next_bar(self):
        rows = self.rows()
        rows[650] = dict(rows[650], r=-0.06, oi_chg=-0.05)
        rows[651] = dict(rows[651], close=100.0)
        rows[675] = dict(rows[675], close=110.0)
        out = ev.fl1_outcomes(rows, 0.004)
        self.assertEqual(out[0][0], 650 * HOUR)
        self.assertAlmostEqual(out[0][1], math.log(1.1) - 0.004)


class TS1Rules(unittest.TestCase):
    def rows(self, days=40, seed=4, vol=lambda d: 0.002):
        rng = random.Random(seed)
        out = []
        for i in range(days * 24):
            d = i // 24
            out.append({"ts": i * HOUR, "r": rng.gauss(0, vol(d))})
        return out

    def test_only_session_hours_are_labelled(self):
        rows = self.rows(vol=lambda d: 0.004 if d % 2 == 0 else 0.001)
        s = ev.ts1_signal_series(rows)
        self.assertGreater(sum(s), 0)
        for i, v in enumerate(s):
            if v:
                self.assertTrue(13 <= (rows[i]["ts"] % DAY) // HOUR < 20)

    def test_session_return_subtracts_the_cost_once(self):
        rows = self.rows(vol=lambda d: 0.01 if d >= 30 else 0.001)
        rets = ev.ts1_session_returns(rows, 0.0011)
        day_rows = {}
        sig = ev.ts1_signal_series(rows)
        for i, r in enumerate(rows):
            if sig[i]:
                day_rows.setdefault(r["ts"] - r["ts"] % DAY, 0.0)
                day_rows[r["ts"] - r["ts"] % DAY] += r["r"]
        self.assertTrue(rets)
        for d, net in rets:
            self.assertAlmostEqual(net, day_rows[d] - 0.0011)


class Lookahead(unittest.TestCase):
    def test_every_signal_is_truncation_invariant(self):
        for did in dg.DESIGNS:
            fn, rows = dg.signal_for(did)
            res = ve.check_lookahead(signal_fn=fn, data=rows)
            self.assertEqual(res["status"], ve.PASS, did)

    def test_a_planted_leak_is_caught(self):
        fn, rows = dg.signal_for("PR1")

        def leaky(xs):
            base = fn(xs)
            return [base[i + 1] if i + 1 < len(base) else 0 for i in range(len(base))]
        self.assertEqual(ve.check_lookahead(signal_fn=leaky, data=rows)["status"], ve.FAIL)


class Power(unittest.TestCase):
    def test_mde_formula_and_register_bar_is_stricter(self):
        for name in pw.ENDPOINTS:
            row = pw.endpoint_row(name)
            e = pw.ENDPOINTS[name]
            n = e.get("n_power", e["n"])
            self.assertAlmostEqual(row["mde_alpha_f"], (2.2414 + 0.8416) * e["sd"] / math.sqrt(n), places=3)
            self.assertGreater(row["mde_register"], row["mde_alpha_f"])

    def test_register_n_is_the_snapshot_minimum_and_never_final(self):
        snap = dg.snapshot_counts()
        self.assertEqual(pw.REGISTER_N, snap["counts"]["variants"])
        self.assertEqual(snap["n"]["n_eff"], "MISSING_INPUT")
        self.assertGreater(pw.bonferroni_z(pw.REGISTER_N + 1), pw.bonferroni_z(pw.REGISTER_N))

    def test_simulated_power_near_80_and_size_controlled(self):
        e = pw.ENDPOINTS["CB1_DIR"]
        self.assertGreater(pw.sim_power(pw.endpoint_row("CB1_DIR")["mde_alpha_f"], e["sd"], e["n"], reps=500, seed=11), 0.72)
        self.assertLess(pw.sim_power(0.0, e["sd"], e["n"], reps=500, seed=12), 0.05)

    def test_reachability(self):
        self.assertTrue(pw.endpoint_row("CB1_VOL")["reachable"])
        self.assertFalse(pw.endpoint_row("CB1_DIR")["reachable"])
        self.assertFalse(pw.endpoint_row("FL1")["reachable"])
        self.assertAlmostEqual(pw.endpoint_row("CB1_DIR")["gross_needed_realistic_bps"], 122.9, delta=0.5)

    def test_sensitivity_is_monotone(self):
        grid = pw.sensitivity("CB1_VOL")
        self.assertLess(grid[(0.25, 180)], grid[(0.25, 60)])
        self.assertLess(grid[(0.20, 120)], grid[(0.35, 120)])


class Gates(unittest.TestCase):
    def test_verdicts_are_the_ones_in_the_note(self):
        self.assertEqual(dg.verdict("CB1")["CB1_VOL"][0], "OVERLEVER_BESKRIVENDE")
        self.assertEqual(dg.verdict("CB1")["CB1_DIR"], ("AFVIST", ["EFFECT_REACHABLE"]))
        self.assertEqual(dg.verdict("PR1")["PR1"][0], "OVERLEVER_BESKRIVENDE")
        self.assertEqual(dg.verdict("LD1")["LD1"], ("AFVIST", ["DISTINCT", "EFFECT_REACHABLE"]))
        self.assertEqual(dg.verdict("FL1")["FL1"], ("AFVIST", ["DISTINCT", "VALIDATION_PLAN", "EFFECT_REACHABLE"]))
        self.assertEqual(dg.verdict("TS1")["TS1"], ("AFVIST", ["MECHANISM", "DISTINCT", "EFFECT_REACHABLE"]))

    def test_no_design_needs_blocked_or_unapproved_data_as_primary(self):
        for d in dg.DESIGNS.values():
            for s in d["data_required"]:
                self.assertIn(dg.DATA[s]["status"], (dg.EXISTING, dg.CACHED))
        self.assertEqual(dg.DATA["metrics_archive_forward"]["status"], dg.BLOCKED_FWD)
        self.assertEqual(dg.DATA["premium_index_klines"]["status"], dg.NOT_APPROVED)

    def test_at_most_five_designs_and_every_lineage_is_honest(self):
        snap = dg.snapshot_counts()
        self.assertEqual(len(dg.DESIGNS), 5)
        self.assertEqual(dg.lineage_status("LD1", snap), "NOT_IN_SNAPSHOT")
        for did in ("CB1", "PR1", "FL1", "TS1"):
            self.assertEqual(dg.lineage_status(did, snap), "IN_SNAPSHOT", did)


class RegisterV2(unittest.TestCase):
    def test_each_design_is_a_valid_future_record_in_memory(self):
        chain = []
        text = dg.snapshot_text()
        for did in dg.DESIGNS:
            rec = dg.v2_record(did)
            self.assertEqual(v2.validate(rec), [], did)
            self.assertEqual(v2.completeness(rec)["missing"], ["variants_tested"], did)
            self.assertTrue(v2.snapshot_matches(rec, text)["matches"], did)
            self.assertFalse(rec["parameters"]["values"]["independent_discovery_claim"])
            self.assertFalse(rec["parameters"]["values"]["register_n_is_final"])
            self.assertEqual(rec["data_quality"]["status"], "NOT_CHECKED")
            v2.chain_append(chain, rec, "2026-11-09T00:00:00Z")
        self.assertTrue(v2.chain_verify(chain))
        self.assertEqual(len(v2.parse_jsonl(v2.render_jsonl(chain))), 5)

    def test_a_changed_lock_field_needs_a_deviation(self):
        chain = []
        rec = dg.v2_record("PR1")
        v2.chain_append(chain, rec, "t1")
        bad = dict(rec, data_period={"start": "2026-12-07", "end": "2027-12-31"})
        with self.assertRaises(v2.StatsError):
            v2.chain_append(chain, bad, "t2")


class ValidationEngine(unittest.TestCase):
    def test_no_design_is_ever_passed_before_data(self):
        for did in dg.DESIGNS:
            self.assertNotEqual(dg.assess_design(did)["status"], ve.PASS, did)

    def test_understated_n_is_refused(self):
        res = dg.assess_design("PR1", best_t=6.0, n_reported=10)
        self.assertEqual(res["checks"][ve.MULTIPLE_TESTING]["status"], ve.FAIL)

    def test_t_of_4_1_does_not_clear_the_register_n(self):
        r = ve.check_multiple_testing(best_t=4.1, n_tested=pw.REGISTER_N + 2)
        self.assertEqual(r["status"], ve.INCONCLUSIVE)
        self.assertEqual(r["metrics"]["n_used"], pw.REGISTER_N + 2)

    def test_a_holdout_window_is_contaminated(self):
        r = ve.check_contamination(windows=[("2024-02-01", "2024-02-28")], protected_windows=dg.PROTECTED, sources=["bn_census"],
                                   banned_sources=dg.BANNED_SOURCES, artifacts=[], quarantined=dg.QUARANTINED)
        self.assertEqual(r["status"], ve.CONTAMINATED)

    def test_design_windows_avoid_protected_periods(self):
        for did, d in dg.DESIGNS.items():
            r = ve.check_contamination(windows=[(d["window"]["start"], d["window"]["end"])], protected_windows=dg.PROTECTED,
                                       sources=d["data_required"], banned_sources=dg.BANNED_SOURCES, artifacts=[], quarantined=dg.QUARANTINED)
            self.assertEqual(r["status"], ve.PASS, did)

    def test_costs_below_the_floor_fail(self):
        self.assertEqual(ve.check_costs(gross_bps_per_trade=45.0, assumed_cost_bps=31.0, floor_cost_bps=46.0)["status"], ve.FAIL)


class Note(unittest.TestCase):
    def setUp(self):
        with open(NOTE, encoding="utf-8") as f:
            self.text = f.read()

    def test_marked_as_a_draft(self):
        self.assertIn("UDKAST, IKKE LÅST", self.text)

    def test_every_design_and_gate_named(self):
        for key in list(dg.DESIGNS) + list(dg.GATES) + ["PRIORITERET", "OVERLEVER_BESKRIVENDE", "AFVIST"]:
            self.assertIn(key, self.text, key)

    def test_headline_numbers_match_the_code(self):
        fmt = lambda x, d: f"{x:.{d}f}".replace(".", ",")  # noqa: E731
        t = pw.table()
        self.assertIn(fmt(t["CB1_VOL"]["mde_alpha_f"], 3), self.text)
        self.assertIn(fmt(100 * t["CB1_DIR"]["mde_alpha_f"], 2), self.text)
        self.assertIn(fmt(t["PR1"]["mde_alpha_f"], 3), self.text)
        self.assertIn(fmt(t["LD1"]["mde_alpha_f"], 1), self.text)
        self.assertIn(fmt(100 * t["FL1"]["mde_alpha_f"], 2), self.text)

    def test_register_note_and_snapshot_hash_are_cited(self):
        self.assertIn("19.438", self.text)
        self.assertIn(v2.snapshot_sha(dg.snapshot_text()), self.text)


class Sources(unittest.TestCase):
    def test_modules_have_no_network_or_market_data_access(self):
        banned = {"urllib", "requests", "socket", "sqlite3", "http", "subprocess", "ssl"}
        for mod in (dg, ev, pw):
            with open(mod.__file__, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names.add((node.module or "").split(".")[0])
            self.assertFalse(names & banned, mod.__file__)

    def test_snapshot_is_only_read(self):
        before = os.path.getmtime(dg.SNAPSHOT)
        dg.v2_record("PR1")
        self.assertEqual(before, os.path.getmtime(dg.SNAPSHOT))


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
