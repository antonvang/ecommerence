"""Director order 80 P2: the PR1 estimator and placebo on synthetic worlds only. No market data, no network, no lab.db."""
import ast
import math
import os
import random
import statistics
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.desk.fapi76b import pr1_prereg_80 as pr  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402
from research.tools import validation_engine as ve  # noqa: E402

NOTE = os.path.join(HERE, "research", "desk", "fapi76b", "PR1_PREREG_DRAFT_80.md")
H, DAY = pr.HOUR, pr.DAY
START = 7 * DAY * 2900 - 3 * DAY          # a Monday 00:00 UTC under the module's week rule


def row(t, p, interval=8, nf=None):
    return {"ts": START + t * H, "mark": 100 * math.exp(p), "index": 100.0, "interval_h": interval, "next_funding_ts": nf}


def next_settlement(ts, interval):
    step = interval * H
    return ts - ts % step + step


def world(extra, coins=12, weeks=40, seed=3):
    """Hourly rows for 4 h and 8 h coins. The log ratio keeps its sign and shrinks by D per slot; D = 0.08 + noise + extra.
    When it gets small a slot is skipped (a gap) and it restarts, so a restart never counts as an outcome."""
    rng = random.Random(seed)
    events = []
    for k in range(coins * 2):
        interval = 4 if k % 2 == 0 else 8
        rows, m, sign, t = [], 0.002 + rng.random() * 0.0005, rng.choice((1, -1)), rng.randrange(24)
        end = weeks * 168 + 200
        while t < end:
            ts = START + t * H
            rows.append({"ts": ts, "mark": 100 * math.exp(sign * m), "index": 100.0, "interval_h": interval,
                         "next_funding_ts": next_settlement(ts, interval)})
            hour_next = ((ts + H) % DAY) // H
            settle = (ts + H) % (interval * H) == 0
            d = 0.08 + rng.gauss(0, 0.03) + extra(interval, hour_next, settle)
            m *= 1 - d
            t += 1
            if m < 0.0013:
                m, sign, t = 0.002 + rng.random() * 0.0005, rng.choice((1, -1)), t + 1
        evs, _ = pr.events_from_rows(rows)
        events.extend(evs)
    return events


def none(interval, hour, settle):
    return 0.0


class Estimator(unittest.TestCase):
    def test_log_ratio_is_not_filled(self):
        self.assertIsNone(pr.log_ratio({"mark": None, "index": 100.0}))
        self.assertIsNone(pr.log_ratio({"mark": 0.0, "index": 100.0}))
        self.assertAlmostEqual(pr.log_ratio({"mark": 101.0, "index": 100.0}), math.log(1.01))

    def test_share_gone_sign_and_clip(self):
        nf = START + 3 * H
        rows = [row(0, 0.002, 8, nf), row(1, 0.002, 8, nf), row(2, 0.001, 8, nf)]
        ev, _ = pr.events_from_rows(rows)
        self.assertEqual(len(ev), 1)
        self.assertAlmostEqual(ev[0]["D"], 0.5, places=6)
        self.assertFalse(ev[0]["settle"])
        rows = [row(0, -0.002, 8, nf), row(1, -0.002, 8, nf), row(2, 0.1, 8, nf)]
        ev, counts = pr.events_from_rows(rows)
        self.assertEqual(ev[0]["D"], 2.0)
        self.assertEqual(counts["clipped"], 1)

    def test_a_settlement_between_the_two_rows_is_flagged_from_the_actual_time(self):
        nf = START + 2 * H
        ev, _ = pr.events_from_rows([row(0, 0.002, 4, nf), row(1, 0.002, 4, nf), row(2, 0.001, 4, nf)])
        self.assertTrue(ev[0]["settle"])

    def test_the_interval_is_never_assumed(self):
        nf = START + 3 * H
        rows = [row(0, 0.002, None, nf), row(1, 0.002, None, nf), row(2, 0.001, None, nf)]
        ev, counts = pr.events_from_rows(rows)
        self.assertEqual((ev, counts["no_interval"]), ([], 1))
        rows = [row(0, 0.002, 4, None), row(1, 0.002, 4, None), row(2, 0.001, 4, None)]
        self.assertEqual(pr.events_from_rows(rows)[1]["no_next_funding"], 1)
        rows = [row(0, 0.002, 1, nf), row(1, 0.002, 1, nf), row(2, 0.001, 1, nf)]
        self.assertEqual(pr.events_from_rows(rows)[1]["other_interval"], 1)
        rows = [row(0, 0.002, 4, nf), row(1, 0.002, 8, nf), row(2, 0.001, 8, nf)]
        self.assertEqual(pr.events_from_rows(rows)[1]["interval_changed"], 1)

    def test_gaps_are_not_filled(self):
        nf = START + 3 * H
        rows = [row(0, 0.002, 8, nf), row(1, 0.002, 8, nf), row(3, 0.001, 8, nf)]
        ev, counts = pr.events_from_rows(rows)
        self.assertEqual((ev, counts["missing_outcome"]), ([], 1))
        self.assertEqual(sum(pr.selection_signal([row(0, 0.002), row(2, 0.002)])), 0)

    def test_selection_needs_two_slots_of_the_same_sign(self):
        self.assertEqual(pr.selection_signal([row(0, 0.002), row(1, -0.002), row(2, 0.002)]), [0, 0, 0])
        self.assertEqual(pr.selection_signal([row(0, 0.0005), row(1, 0.002)]), [0, 0])

    def test_selection_is_causal(self):
        rows = [row(t, 0.002 if t % 5 else 0.0) for t in range(120)]
        self.assertEqual(ve.check_lookahead(signal_fn=pr.selection_signal, data=rows)["status"], ve.PASS)

    def test_decay_over_the_actual_interval(self):
        rows = [row(t, 0.002 if t == 0 else 0.0005, 4, None) for t in range(6)]
        self.assertAlmostEqual(pr.decay_over_interval(rows, 0), 0.75, places=6)
        self.assertIsNone(pr.decay_over_interval(rows[:3], 0))


class Worlds(unittest.TestCase):
    def test_a_settlement_effect_is_found_and_the_placebo_stays_quiet(self):
        res = pr.evaluate(world(lambda i, h, s: 0.10 if s else 0.0))
        self.assertEqual(res["label"], pr.H0_REJECTED)
        self.assertGreater(res["theta"], 0.05)
        self.assertLess(abs(res["placebo_theta"]), 0.03)

    def test_ordinary_normalisation_is_not_mistaken_for_settlement(self):
        res = pr.evaluate(world(none))
        self.assertEqual(res["label"], pr.H0_NOT_REJECTED)
        self.assertLess(abs(res["theta"]), 0.03)

    def test_an_hour_of_day_effect_cancels_and_fools_only_the_naive_contrast(self):
        evs = world(lambda i, h, s: 0.10 if h in pr.A_HOURS else 0.0)
        self.assertGreater(pr.naive_single_difference(evs), 0.05)
        res = pr.evaluate(evs)
        self.assertEqual(res["label"], pr.H0_NOT_REJECTED)
        self.assertLess(abs(res["theta"]), 0.03)

    def test_a_coin_type_effect_cancels(self):
        res = pr.evaluate(world(lambda i, h, s: 0.05 if i == 4 else 0.0))
        self.assertEqual(res["label"], pr.H0_NOT_REJECTED)

    def test_the_placebo_catches_a_non_settlement_structure(self):
        res = pr.evaluate(world(lambda i, h, s: 0.10 if i == 4 and h in pr.PLACEBO_A else 0.0))
        self.assertEqual(res["label"], pr.PLACEBO_FAILED)

    def test_too_few_weeks_is_insufficient(self):
        self.assertEqual(pr.evaluate(world(none, weeks=10))["label"], pr.INSUFFICIENT)


class Cells(unittest.TestCase):
    def event(self, interval, hour, settle, d, ts=START):
        return {"ts": ts, "hour": hour, "interval": interval, "D": d, "settle": settle, "abs_p": 0.002}

    def full_week(self, hours_a=pr.A_HOURS, hours_c=pr.C_HOURS, placebo=False):
        out = []
        for interval in (4, 8):
            for hour in (hours_a[0], hours_c[0]):
                settle = (not placebo) and interval == 4 and hour in pr.A_HOURS
                out += [self.event(interval, hour, settle, 0.1)] * 3
        return out

    def test_a_full_week_gives_one_value(self):
        vals, c = pr.weekly_theta(self.full_week(), pr.A_HOURS, pr.C_HOURS)
        self.assertEqual((len(vals), c["mismatch"]), (1, 0))
        self.assertAlmostEqual(vals[0], 0.0)

    def test_a_thin_cell_drops_the_week(self):
        evs = self.full_week()[1:]
        vals, c = pr.weekly_theta(evs, pr.A_HOURS, pr.C_HOURS)
        self.assertEqual((vals, c["weeks_dropped"]), ([], 1))

    def test_a_schedule_that_disagrees_with_the_cell_is_excluded(self):
        evs = self.full_week() + [self.event(8, 4, True, 0.9)]
        vals, c = pr.weekly_theta(evs, pr.A_HOURS, pr.C_HOURS)
        self.assertEqual(c["mismatch"], 1)
        self.assertAlmostEqual(vals[0], 0.0)

    def test_placebo_hours_never_settle_and_never_overlap_real_settlement_hours(self):
        self.assertFalse(set(pr.PLACEBO_A + pr.PLACEBO_C) & set(pr.A_HOURS + (0, 8, 16)))
        self.assertEqual(tuple(sorted(pr.PLACEBO_A + pr.PLACEBO_C)), tuple(sorted(pr.C_HOURS)))
        self.assertEqual(tuple((h + 2) % 24 for h in pr.A_HOURS), pr.PLACEBO_A)


class CostAndSensitivity(unittest.TestCase):
    def test_hurdle_follows_21i(self):
        self.assertAlmostEqual(pr.hurdle_21i(1e8), 0.0046)
        self.assertAlmostEqual(pr.hurdle_21i(1e6), 2 * (0.0008 + math.exp(0.8999) * 1e6 ** -0.454), places=9)

    def test_share_above_hurdle(self):
        self.assertEqual(pr.share_above_hurdle([(0.01, 1e8), (0.001, 1e8)]), 0.5)
        self.assertIsNone(pr.share_above_hurdle([]))

    def test_mde_grid_is_monotone(self):
        g = pr.mde_grid()
        self.assertLess(g[(0.15, 52)], g[(0.30, 52)])
        self.assertLess(g[(0.30, 52)], g[(0.30, 26)])

    def test_no_power_at_an_assumed_effect(self):
        self.assertFalse(hasattr(pr, "analytic_power"))
        with open(pr.__file__, encoding="utf-8") as f:
            self.assertNotIn("sim_power(", f.read())


class RegisterRecord(unittest.TestCase):
    def test_valid_future_record_that_claims_nothing(self):
        rec = pr.register_v2_record()
        self.assertEqual(v2.validate(rec), [])
        self.assertEqual(v2.completeness(rec)["missing"], ["variants_tested"])
        self.assertEqual(rec["lineage"], "cross_venue_perp_gap")
        values = rec["parameters"]["values"]
        self.assertFalse(values["causal_claim"])
        self.assertFalse(values["independent_discovery_claim"])
        self.assertFalse(values["register_n_is_final"])
        self.assertEqual(values["status"], "UDKAST, IKKE LÅST")


class Note(unittest.TestCase):
    def setUp(self):
        with open(NOTE, encoding="utf-8") as f:
            self.text = f.read()

    def test_required_content(self):
        for key in ["UDKAST, IKKE LÅST", "ln(markPrice/indexPrice)", "ikke Binances officielle premium index", "H0", "placebo",
                    "korrelation", "kausal", "fwd_spec_journal", "UNVERIFIED", "21i", "følsomhed", "Stopkriterier", "K3", "G05"]:
            self.assertIn(key, self.text, key)

    def test_no_power_claim_and_no_assumed_interval(self):
        self.assertNotIn("styrke 1,00", self.text.lower())
        self.assertNotIn("standard-fundingperiode", self.text)

    def test_grid_numbers_are_the_code_numbers(self):
        g = pr.mde_grid()
        for k in [(0.15, 52), (0.30, 52), (0.45, 26)]:
            self.assertIn(f"{g[k]:.3f}".replace(".", ","), self.text, k)


class Sources(unittest.TestCase):
    def test_no_network_database_or_entry_point(self):
        with open(pr.__file__, encoding="utf-8") as f:
            src = f.read()
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertFalse(names & {"urllib", "requests", "socket", "sqlite3", "http", "subprocess", "ssl", "argparse"})
        self.assertNotIn("__main__", src)
        self.assertEqual(statistics.fmean([1.0, 3.0]), 2.0)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
