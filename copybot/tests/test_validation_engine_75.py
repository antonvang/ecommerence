"""Director order 75 P1: the validation engine on synthetic worlds only. Each error type is planted into a world that
otherwise passes; a clean null world and a world with a real effect must come out right. No file or market data."""
import math
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import register_stats as rs  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402
from research.tools import validation_engine as ve  # noqa: E402

SOURCE = os.path.join(HERE, "research", "tools", "validation_engine.py")
PROV = {"origin": "RUN_OUTPUT", "artifact": "synthetic/fixture.json", "sha256": "a" * 64, "code_commit": "abc1234"}


def noise(n, t, seed, sd=0.01):
    r = random.Random(seed)
    return [[r.gauss(0, sd) for _ in range(t)] for _ in range(n)]


def axis(t):
    return list(range(t))


def factor_family(n, t, seed, rho, drifts=None, sd=0.01):
    """n series with pairwise correlation rho and the given per-period drifts."""
    r = random.Random(seed)
    common = [r.gauss(0, 1) for _ in range(t)]
    drifts = drifts or [0.0] * n
    a, b = math.sqrt(rho), math.sqrt(1 - rho)
    return [[drifts[i] + sd * (a * common[k] + b * r.gauss(0, 1)) for k in range(t)] for i in range(n)]


def real_effect_series(n=20, t=600, seed=7):
    return factor_family(n, t, seed, 0.3, [0.004 * i / (n - 1) for i in range(n)])


def causal_signal(data):
    out = []
    for i in range(len(data)):
        out.append(None if i < 4 else sum(data[i - 4:i + 1]) / 5)
    return out


def peeking_signal(data):
    """A centred moving average: it reads two values into the future. This is the planted bug."""
    out = []
    for i in range(len(data)):
        window = data[max(0, i - 2):i + 3]
        out.append(sum(window) / len(window))
    return out


def normalised_signal(data):
    """Normalising by the full-sample mean is the subtler form of the same bug."""
    mean = sum(data) / len(data)
    return [v - mean for v in data]


MEMBERS = [f"C{i}" for i in range(40)]


def clean_spec(series, n_tested=None, t=None, gross=40.0, min_sharpe=None, **mt):
    t = t or len(series[0])
    n_tested = n_tested or len(series)
    best = max(range(len(series)), key=lambda i: sum(series[i]))
    data = [v * 100 for v in series[best]]
    return {
        ve.MULTIPLE_TESTING: {"series": series, "time_index": axis(t), "n_tested": n_tested, "n_preregistered": n_tested,
                              "n_reported": n_tested, "reps": 299, "min_sharpe": min_sharpe, **mt},
        ve.CORRELATION: {"series": series, "time_index": axis(t), "reps": 99},
        ve.LOOKAHEAD: {"decision_times": axis(t), "feature_times": axis(t), "signal_fn": causal_signal, "data": data},
        ve.SURVIVORSHIP: {"universe": MEMBERS, "tested": MEMBERS, "delisted": MEMBERS[:3], "universe_asof": "2025-01-01",
                          "period_start": "2025-01-01"},
        ve.MISSING_OBS: {"values": series[best], "time_index": axis(t), "expected_index": axis(t)},
        ve.CONTAMINATION: {"windows": [(20250101, 20251231)], "protected_windows": [(20240101, 20241231)],
                           "sources": ["synthetic"], "banned_sources": ["banned.example"], "artifacts": ["a1"],
                           "quarantined": ["q1"], "train_ids": ["t1"], "test_ids": ["t2"], "train_end": 100,
                           "test_start": 110, "embargo": 5},
        ve.OVERFITTING: {"series": series, "time_index": axis(t), "n_tested": n_tested, "synthetic": True, "s": 8},
        ve.COSTS: {"gross_bps_per_trade": gross, "assumed_cost_bps": 12.0, "floor_cost_bps": 10.0},
    }


class Vocabulary(unittest.TestCase):
    def test_statuses_are_exactly_the_five(self):
        self.assertEqual(set(ve.STATUSES), {"PASS", "FAIL", "INCONCLUSIVE", "MISSING_INPUT", "CONTAMINATED"})

    def test_every_check_is_listed_and_returns_the_shape(self):
        self.assertEqual(len(ve.ALL_CHECKS), 8)
        for name in ve.ALL_CHECKS:
            got = ve.CHECKS[name]()
            self.assertEqual(set(got), {"check", "status", "reason", "metrics", "missing"}, name)
            self.assertEqual(got["status"], ve.MISSING_INPUT, name)
            self.assertTrue(got["reason"], name)
            self.assertTrue(got["missing"], name)


class Worlds(unittest.TestCase):
    """One world for each error type, planted into the world that otherwise passes."""

    @classmethod
    def setUpClass(cls):
        cls.series = real_effect_series()
        cls.n = len(cls.series)
        cls.t = len(cls.series[0])

    def spec(self):
        return clean_spec(self.series)

    def planted(self, name, status, **change):
        spec = self.spec()
        spec[name] = {**spec[name], **change}
        got = ve.evaluate(spec)
        self.assertEqual(got["checks"][name]["status"], status, got["checks"][name]["reason"])
        self.assertEqual(got["status"], status, got["reasons"])
        others = [k for k in ve.ALL_CHECKS if k != name]
        self.assertEqual([k for k in others if got["checks"][k]["status"] != ve.PASS], [], "only the planted check moves")
        self.assertTrue(got["reasons"])
        return got

    def test_real_effect_world_passes_every_check(self):
        got = ve.evaluate(self.spec())
        self.assertEqual(got["status"], ve.PASS, got["reasons"])
        for name in ve.ALL_CHECKS:
            self.assertEqual(got["checks"][name]["status"], ve.PASS, got["checks"][name]["reason"])
        self.assertEqual(got["checks"][ve.MULTIPLE_TESTING]["metrics"]["method"], "BLOCK_BOOTSTRAP_MAX_T")

    def test_clean_null_world_is_not_passed_and_blames_chance_not_data(self):
        series = noise(20, 600, 11)
        got = ve.evaluate(clean_spec(series, gross=0.4, min_sharpe=0.3))
        self.assertEqual(got["status"], ve.FAIL, got["reasons"])
        self.assertEqual(got["checks"][ve.MULTIPLE_TESTING]["status"], ve.FAIL)
        self.assertNotEqual(got["checks"][ve.OVERFITTING]["status"], ve.PASS)
        for name in (ve.CORRELATION, ve.LOOKAHEAD, ve.SURVIVORSHIP, ve.MISSING_OBS, ve.CONTAMINATION):
            self.assertEqual(got["checks"][name]["status"], ve.PASS, name)
        self.assertNotIn(ve.CONTAMINATED, [c["status"] for c in got["checks"].values()])

    def test_null_without_a_smallest_effect_is_inconclusive_not_fail(self):
        got = ve.check_multiple_testing(series=noise(20, 300, 12), time_index=axis(300), n_tested=20, reps=199)
        self.assertEqual(got["status"], ve.INCONCLUSIVE, got["reason"])

    def test_plant_multiple_testing_understated_n(self):
        got = self.planted(ve.MULTIPLE_TESTING, ve.FAIL, n_reported=1)
        self.assertIn("understated", got["checks"][ve.MULTIPLE_TESTING]["reason"])

    def test_plant_correlation_understated_n_eff(self):
        got = self.planted(ve.CORRELATION, ve.FAIL, claimed_n_eff=1.0)
        self.assertIn("N_eff", got["checks"][ve.CORRELATION]["reason"])

    def test_plant_correlation_cloned_confirmations(self):
        clones = [list(self.series[0])] + [[v + 1e-7 * (k % 2) for k, v in enumerate(self.series[0])] for _ in range(4)]
        got = ve.check_correlation(clones + self.series[1:6], axis(self.t), confirming=[0, 1, 2, 3, 4], reps=49)
        self.assertEqual(got["status"], ve.FAIL, got["reason"])
        self.assertEqual(got["metrics"]["distinct_confirming_clusters"], 1)

    def test_plant_lookahead_late_timestamps(self):
        late = list(axis(self.t))
        late[50] = 51
        got = self.planted(ve.LOOKAHEAD, ve.FAIL, feature_times=late)
        self.assertIn("after the decision", got["checks"][ve.LOOKAHEAD]["reason"])

    def test_plant_lookahead_centred_window(self):
        got = self.planted(ve.LOOKAHEAD, ve.FAIL, signal_fn=peeking_signal)
        self.assertGreater(got["checks"][ve.LOOKAHEAD]["metrics"]["truncation_differs"], 0)

    def test_plant_lookahead_full_sample_normalisation(self):
        self.planted(ve.LOOKAHEAD, ve.FAIL, signal_fn=normalised_signal)

    def test_plant_survivorship_delisted_dropped(self):
        got = self.planted(ve.SURVIVORSHIP, ve.FAIL, tested=MEMBERS[3:])
        self.assertEqual(got["checks"][ve.SURVIVORSHIP]["metrics"]["delisted_dropped"], 3)

    def test_plant_survivorship_universe_chosen_afterwards(self):
        self.planted(ve.SURVIVORSHIP, ve.FAIL, universe_asof="2026-01-01")

    def test_plant_missing_observations_gaps_after_losses(self):
        r = random.Random(3)
        values = [r.gauss(0, 0.01) for _ in range(3000)]
        cut = sorted(values)[450]
        kept = []
        previous_bad = False
        for i, v in enumerate(values):
            if previous_bad and r.random() < 0.6:
                kept.append(None)
                previous_bad = False
            else:
                kept.append(v)
                previous_bad = v <= cut
        got = ve.check_missing_observations(kept, axis(3000), axis(3000), max_missing_share=0.2)
        self.assertEqual(got["status"], ve.FAIL, got["reason"])
        self.assertIn("gaps follow losses", got["reason"])

    def test_plant_missing_observations_silent_holes(self):
        values = [random.Random(5).gauss(0, 0.01) * (1 + i % 7) for i in range(1000)]
        kept = [(i, v) for i, v in enumerate(values) if i % 4]
        got = ve.check_missing_observations([v for _, v in kept], [i for i, _ in kept], axis(1000))
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])
        self.assertEqual(got["metrics"]["missing"], 250)

    def test_plant_missing_observations_filled_with_zero(self):
        r = random.Random(6)
        values = [r.gauss(0, 0.01) for _ in range(500)]
        for i in range(100, 130):
            values[i] = 0.0
        got = ve.check_missing_observations(values, axis(500), axis(500))
        self.assertEqual(got["status"], ve.FAIL, got["reason"])
        self.assertIn("filled", got["reason"])
        self.assertEqual(ve.check_missing_observations(values, axis(500), axis(500), flat_is_valid=True)["status"], ve.PASS)

    def test_plant_contamination_holdout_window(self):
        self.planted(ve.CONTAMINATION, ve.CONTAMINATED, windows=[(20240601, 20240630)])

    def test_plant_contamination_quarantined_artifact(self):
        self.planted(ve.CONTAMINATION, ve.CONTAMINATED, artifacts=["q1"])

    def test_plant_contamination_banned_source(self):
        self.planted(ve.CONTAMINATION, ve.CONTAMINATED, sources=["banned.example"])

    def test_plant_contamination_train_test_overlap(self):
        self.planted(ve.CONTAMINATION, ve.CONTAMINATED, test_ids=["t1"])

    def test_plant_contamination_embargo(self):
        self.planted(ve.CONTAMINATION, ve.CONTAMINATED, test_start=103)

    def test_plant_contamination_declared_by_register(self):
        got = self.planted(ve.CONTAMINATION, ve.CONTAMINATED, declared_data_quality="CONTAMINATED")
        self.assertIn("declares", got["checks"][ve.CONTAMINATION]["reason"])

    def test_plant_overfitting_regime_fitted_family(self):
        n, t, s = 30, 480, 8
        r = random.Random(21)
        block = t // s
        series = []
        for _ in range(n):
            up = set(r.sample(range(s), s // 2))
            series.append([(0.01 if k // block in up else -0.01) + r.gauss(0, 0.002) for k in range(t)])
        got = ve.check_overfitting(series=series, time_index=axis(t), n_tested=n, synthetic=True, s=s)
        self.assertEqual(got["status"], ve.FAIL, got["reason"])
        self.assertGreater(got["metrics"]["pbo"], 0.9)

    def test_plant_overfitting_best_of_many_noise_is_not_passed(self):
        got = ve.check_overfitting(series=noise(40, 400, 22), time_index=axis(400), n_tested=40, synthetic=True, s=8)
        self.assertIn(got["status"], (ve.FAIL, ve.INCONCLUSIVE), got["reason"])
        self.assertLess(got["metrics"]["dsr"], 0.95)

    def test_plant_costs_below_floor(self):
        got = self.planted(ve.COSTS, ve.FAIL, assumed_cost_bps=2.0)
        self.assertIn("below", got["checks"][ve.COSTS]["reason"])

    def test_plant_costs_zero(self):
        self.planted(ve.COSTS, ve.FAIL, assumed_cost_bps=0.0)

    def test_plant_costs_net_equals_gross(self):
        got = self.planted(ve.COSTS, ve.FAIL, reported_net_bps_per_trade=40.0)
        self.assertIn("does not equal", got["checks"][ve.COSTS]["reason"])


class MultipleTesting(unittest.TestCase):
    def test_undocumented_n_is_missing_not_guessed(self):
        got = ve.check_multiple_testing(best_t=5.0, n_reported=10)
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])
        self.assertIn("n_tested", got["missing"])

    def test_preregistered_universe_counts_when_fewer_were_run(self):
        got = ve.check_multiple_testing(best_t=3.0, n_tested=2, n_preregistered=500, n_reported=2)
        self.assertEqual(got["metrics"]["n_used"], 500)
        self.assertNotEqual(got["status"], ve.PASS)

    def test_a_good_looking_t_from_a_search_is_not_a_pass(self):
        best = max(ve._t_stat(x) for x in noise(200, 500, 31))
        self.assertGreater(best, 2.0)                           # looks significant taken alone
        naive = ve.check_multiple_testing(best_t=best, n_tested=1)
        honest = ve.check_multiple_testing(best_t=best, n_tested=200)
        self.assertLess(naive["metrics"]["bonferroni_p"], 0.05)
        self.assertNotEqual(honest["status"], ve.PASS)

    def test_register_total_with_a_max_z_sized_t_is_not_a_pass(self):
        # 4.1 is above the diagnostic expected maximum near 4.02, and that is exactly why it must not be a bar.
        n = rs.REGISTER_COUNTS["variants"]
        got = ve.check_multiple_testing(best_t=4.1, n_tested=n)
        self.assertNotEqual(got["status"], ve.PASS)
        self.assertGreater(got["metrics"]["bonferroni_p"], 0.05)

    def test_max_z_is_diagnostic_and_the_register_n_is_not_final(self):
        got = ve.max_z_diagnostic()
        self.assertEqual(got["kind"], "DIAGNOSTIC")
        self.assertIsNone(got["calibrated_threshold"])
        self.assertFalse(got["n_is_final"])
        self.assertEqual(got["n_eff"], ve.MISSING_INPUT)
        self.assertAlmostEqual(got["expected_max_z"], 4.02, delta=0.05)

    def test_engine_has_no_hardcoded_bar(self):
        with open(SOURCE, encoding="utf-8") as f:
            src = f.read()
        for bad in ("4.02", "19438", "19_438", "open(", "socket", "sqlite3", "urllib"):
            self.assertNotIn(bad, src, bad)

    def test_more_series_than_registered_is_a_fail(self):
        got = ve.check_multiple_testing(series=noise(9, 100, 1), time_index=axis(100), n_tested=5, reps=19)
        self.assertEqual(got["status"], ve.FAIL, got["reason"])

    def test_partial_family_falls_back_to_bonferroni_on_the_full_n(self):
        got = ve.check_multiple_testing(series=noise(5, 300, 2), time_index=axis(300), n_tested=50, reps=19)
        self.assertEqual(got["metrics"]["method"], "BONFERRONI")
        self.assertIn("only 5 of 50", got["metrics"]["note"])

    def test_gaps_and_axis(self):
        series = noise(3, 100, 3)
        series[1][4] = None
        got = ve.check_multiple_testing(series=series, time_index=axis(100), n_tested=3)
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])
        got = ve.check_multiple_testing(series=noise(3, 100, 3), n_tested=3)
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])
        self.assertIn("time_index", got["missing"])

    def test_short_sample_is_inconclusive(self):
        got = ve.check_multiple_testing(series=noise(3, 20, 3), time_index=axis(20), n_tested=3)
        self.assertEqual(got["status"], ve.INCONCLUSIVE, got["reason"])

    def test_low_power_null_is_inconclusive(self):
        got = ve.check_multiple_testing(series=noise(5, 40, 4), time_index=axis(40), n_tested=5, min_sharpe=0.1, reps=99)
        self.assertEqual(got["status"], ve.INCONCLUSIVE, got["reason"])
        self.assertLess(got["metrics"]["power"], 0.8)

    def test_correlated_family_gets_credit_only_through_the_bootstrap(self):
        t, n = 400, 30
        series = factor_family(n, t, 41, 0.97, [0.0010] * n)   # drift chosen so the two tests disagree
        got = ve.check_multiple_testing(series=series, time_index=axis(t), n_tested=n, reps=999)
        self.assertEqual(got["metrics"]["method"], "BLOCK_BOOTSTRAP_MAX_T")
        self.assertGreater(got["metrics"]["bonferroni_p"], 0.05, "Bonferroni alone would refuse this")
        self.assertLessEqual(got["metrics"]["max_t_p"], 0.05)
        self.assertEqual(got["status"], ve.PASS, got["reason"])

    def test_max_t_false_positive_rate_on_null_worlds(self):
        rejected, worlds, alpha = 0, 60, 0.2
        for seed in range(worlds):
            got = ve.check_multiple_testing(series=noise(8, 120, 500 + seed), time_index=axis(120), n_tested=8, alpha=alpha,
                                            reps=99, seed=seed)
            rejected += got["status"] == ve.PASS
        self.assertLessEqual(rejected, worlds * alpha + 2 * math.sqrt(worlds * alpha * (1 - alpha)) + 1, rejected)

    def test_deterministic(self):
        kw = dict(series=real_effect_series(6, 200, 5), time_index=axis(200), n_tested=6, reps=99)
        self.assertEqual(ve.check_multiple_testing(**kw), ve.check_multiple_testing(**kw))
        self.assertNotEqual(ve.check_multiple_testing(**kw)["metrics"]["max_t_p"], None)


class Correlation(unittest.TestCase):
    def test_independent_family_has_max_equivalent_near_n(self):
        got = ve.check_correlation(noise(40, 400, 51), axis(400), reps=199)
        self.assertEqual(got["status"], ve.PASS)
        self.assertLess(abs(got["metrics"]["mean_correlation"]), 0.05)
        self.assertGreater(got["metrics"]["max_equivalent_n"], 15)

    def test_correlated_family_has_lower_max_equivalent(self):
        t = 400
        wide = ve.check_correlation(noise(40, t, 52), axis(t), reps=199)
        narrow = ve.check_correlation(factor_family(40, t, 52, 0.98), axis(t), reps=199)
        self.assertLess(narrow["metrics"]["max_equivalent_n"], wide["metrics"]["max_equivalent_n"] / 2)
        self.assertGreater(narrow["metrics"]["mean_correlation"], 0.9)
        self.assertEqual(narrow["metrics"]["max_equivalent_n_kind"], "DIAGNOSTIC, not a documented N_eff")

    def test_honest_n_eff_claim_passes(self):
        t = 400
        got = ve.check_correlation(factor_family(40, t, 53, 0.98), axis(t), claimed_n_eff=40, reps=99)
        self.assertEqual(got["status"], ve.PASS, got["reason"])

    def test_inputs(self):
        self.assertEqual(ve.check_correlation(noise(1, 100, 1), axis(100))["status"], ve.MISSING_INPUT)
        self.assertEqual(ve.check_correlation(noise(3, 10, 1), axis(10))["status"], ve.INCONCLUSIVE)
        flat = noise(3, 100, 1)
        flat[1] = [0.0] * 100
        self.assertEqual(ve.check_correlation(flat, axis(100))["status"], ve.INCONCLUSIVE)
        got = ve.check_correlation(noise(3, 100, 1), axis(100), confirming=[9], reps=9)
        self.assertEqual(got["status"], ve.MISSING_INPUT)


class Lookahead(unittest.TestCase):
    def test_returns_alone_are_not_enough(self):
        got = ve.check_lookahead()
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])
        self.assertIn("returns alone", got["reason"])

    def test_causal_signal_passes(self):
        data = [random.Random(1).random() * i for i in range(200)]
        self.assertEqual(ve.check_lookahead(signal_fn=causal_signal, data=data)["status"], ve.PASS)

    def test_half_an_input_is_missing(self):
        self.assertEqual(ve.check_lookahead(decision_times=[1])["status"], ve.MISSING_INPUT)
        self.assertEqual(ve.check_lookahead(signal_fn=causal_signal)["status"], ve.MISSING_INPUT)
        self.assertEqual(ve.check_lookahead(decision_times=[1, 2], feature_times=[1, None])["status"], ve.MISSING_INPUT)

    def test_a_failing_function_is_inconclusive(self):
        def broken(data):
            raise RuntimeError("no")
        self.assertEqual(ve.check_lookahead(signal_fn=broken, data=[1.0] * 50)["status"], ve.INCONCLUSIVE)


class Survivorship(unittest.TestCase):
    def test_unknown_delisting_is_missing_and_stated_none_passes(self):
        kw = dict(universe=MEMBERS, tested=MEMBERS, universe_asof="2025-01-01", period_start="2025-01-01")
        self.assertEqual(ve.check_survivorship(delisted=None, **kw)["status"], ve.MISSING_INPUT)
        self.assertEqual(ve.check_survivorship(delisted=[], **kw)["status"], ve.PASS)

    def test_explained_exclusion_passes_unexplained_does_not(self):
        kw = dict(universe=MEMBERS, delisted=[], universe_asof="2025-01-01", period_start="2025-01-01")
        tested = MEMBERS[1:]
        self.assertEqual(ve.check_survivorship(tested=tested, excluded={"C0": "stablecoin"}, **kw)["status"], ve.PASS)
        self.assertEqual(ve.check_survivorship(tested=tested, **kw)["status"], ve.INCONCLUSIVE)
        self.assertEqual(ve.check_survivorship(tested=MEMBERS[5:], **kw)["status"], ve.FAIL)

    def test_dates_that_cannot_be_compared_are_missing(self):
        got = ve.check_survivorship(universe=MEMBERS, tested=MEMBERS, delisted=[], universe_asof=20250101,
                                    period_start="2025-01-01")
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])

    def test_tested_outside_universe_fails(self):
        got = ve.check_survivorship(universe=MEMBERS, tested=MEMBERS + ["X"], delisted=[], universe_asof="2025-01-01",
                                    period_start="2025-01-01")
        self.assertEqual(got["status"], ve.FAIL)

    def test_bias_is_measured_when_returns_exist(self):
        means = {m: 0.01 for m in MEMBERS}
        means.update({m: -0.5 for m in MEMBERS[:4]})
        got = ve.check_survivorship(universe=MEMBERS, tested=MEMBERS[4:], delisted=MEMBERS[:4], universe_asof="2025-01-01",
                                    period_start="2025-01-01", asset_mean_returns=means)
        self.assertEqual(got["status"], ve.FAIL)
        self.assertGreater(got["metrics"]["survivorship_bias"], 0.04)


class MissingObservations(unittest.TestCase):
    def test_no_expected_axis_is_missing(self):
        self.assertEqual(ve.check_missing_observations([1.0], [0])["status"], ve.MISSING_INPUT)

    def test_few_random_gaps_pass(self):
        r = random.Random(8)
        values = [None if r.random() < 0.02 else r.gauss(0, 0.01) for _ in range(800)]
        got = ve.check_missing_observations(values, axis(800), axis(800))
        self.assertEqual(got["status"], ve.PASS, got["reason"])
        self.assertLess(got["metrics"]["gap_loss_z"], 3.0)

    def test_outside_axis_fails(self):
        got = ve.check_missing_observations([1.0, 2.0, 3.0], [0, 1, 99], [0, 1, 2])
        self.assertEqual(got["status"], ve.FAIL, got["reason"])


class Contamination(unittest.TestCase):
    def test_unstated_guard_is_missing_and_empty_is_a_statement(self):
        base = dict(windows=[(1, 2)], sources=["s"], banned_sources=[], artifacts=[], quarantined=[])
        self.assertEqual(ve.check_contamination(protected_windows=None, **base)["status"], ve.MISSING_INPUT)
        self.assertEqual(ve.check_contamination(protected_windows=[], **base)["status"], ve.PASS)

    def test_malformed_windows_are_missing_not_a_crash(self):
        base = dict(sources=[], banned_sources=[], artifacts=[], quarantined=[])
        for windows in ([(1, None)], [("a", 2)], [(1,)], [5]):
            got = ve.check_contamination(windows=windows, protected_windows=[(1, 2)], **base)
            self.assertEqual(got["status"], ve.MISSING_INPUT, str(windows))
        got = ve.check_contamination(windows=[(1, 2)], protected_windows=[], train_end=5, **base)
        self.assertEqual(got["status"], ve.MISSING_INPUT)

    def test_boundary_touch_is_an_overlap(self):
        got = ve.check_contamination(windows=[(5, 10)], protected_windows=[(10, 20)], sources=[], banned_sources=[],
                                     artifacts=[], quarantined=[])
        self.assertEqual(got["status"], ve.CONTAMINATED, got["reason"])


class Overfitting(unittest.TestCase):
    def test_series_without_provenance_gets_no_number(self):
        got = ve.check_overfitting(series=noise(5, 100, 1), time_index=axis(100), n_tested=5)
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])
        self.assertNotIn("dsr", got["metrics"])
        self.assertNotIn("pbo", got["metrics"])

    def test_synthetic_label_is_visible(self):
        got = ve.check_overfitting(series=real_effect_series(), time_index=axis(600), n_tested=20, synthetic=True)
        self.assertEqual(got["metrics"]["origin"], "SYNTHETIC_TEST")

    def test_records_with_provenance_are_used(self):
        n, t = 6, 200
        series = real_effect_series(n, t, 9)
        recs = [rs.record(f"V{i}", net_returns=x, net_returns_index=axis(t), provenance=PROV) for i, x in enumerate(series)]
        got = ve.check_overfitting(records=recs, n_tested=n, s=6)
        self.assertEqual(got["metrics"]["origin"], "PROVENANCE_RECORDS")
        self.assertEqual(got["metrics"]["dsr_status"], rs.OK)
        self.assertEqual(got["metrics"]["pbo_status"], rs.OK)

    def test_records_without_series_are_missing(self):
        recs = [rs.record("V0", lineage="x"), rs.record("V1", lineage="x")]
        got = ve.check_overfitting(records=recs, n_tested=2)
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])

    def test_undocumented_or_partial_family_is_missing(self):
        kw = dict(series=noise(5, 200, 1), time_index=axis(200), synthetic=True)
        self.assertEqual(ve.check_overfitting(n_tested=None, **kw)["status"], ve.MISSING_INPUT)
        got = ve.check_overfitting(n_tested=50, **kw)
        self.assertEqual(got["status"], ve.MISSING_INPUT)
        self.assertNotIn("dsr", got["metrics"])

    def test_gaps_give_no_number(self):
        series = noise(5, 200, 1)
        series[0][3] = None
        got = ve.check_overfitting(series=series, time_index=axis(200), n_tested=5, synthetic=True)
        self.assertEqual(got["status"], ve.MISSING_INPUT)

    def test_too_few_periods_for_s_is_missing(self):
        got = ve.check_overfitting(series=noise(5, 40, 1), time_index=axis(40), n_tested=5, synthetic=True, s=30)
        self.assertEqual(got["status"], ve.MISSING_INPUT, got["reason"])
        self.assertEqual(got["metrics"]["pbo_status"], rs.MISSING_INPUT)

    def test_persistent_family_cannot_pass_on_a_low_pbo(self):
        r = random.Random(61)
        n, t = 10, 480
        series = []
        for i in range(n):
            x, out = 0.0, []
            for _ in range(t):
                x = 0.97 * x + r.gauss(0, 0.002)
                out.append(0.0008 * (i + 1) + x)
            series.append(out)
        got = ve.check_overfitting(series=series, time_index=axis(t), n_tested=n, synthetic=True, s=8)
        self.assertGreater(got["metrics"]["mean_lag1_autocorrelation"], 0.5)
        self.assertNotEqual(got["status"], ve.PASS, got["reason"])

    def test_homogeneous_real_effect_is_inconclusive_not_fail(self):
        # PBO measures selection within the family, not the level: equal drifts leave the winner a coin flip.
        statuses, seen = [], 0
        for seed in range(12):
            r = random.Random(700 + seed)
            series = [[0.003 + r.gauss(0, 0.01) for _ in range(480)] for _ in range(10)]
            got = ve.check_overfitting(series=series, time_index=axis(480), n_tested=10, synthetic=True, s=8)
            statuses.append(got["status"])
            self.assertGreaterEqual(got["metrics"]["dsr"], 0.95)
            if got["metrics"]["pbo"] >= 0.5:
                seen += 1
                self.assertEqual(got["status"], ve.INCONCLUSIVE, got["reason"])
        self.assertGreater(seen, 0, "no world reached the case under test")
        self.assertNotIn(ve.FAIL, statuses)

    def test_dsr_equals_the_register_stats_computation(self):
        n, t = 6, 200
        series = real_effect_series(n, t, 9)
        got = ve.check_overfitting(series=series, time_index=axis(t), n_tested=n, synthetic=True, s=6)
        moments = [rs.moments(x) for x in series]
        best = max(moments, key=lambda m: m["sharpe"])
        direct = rs.deflated_sharpe(best["sharpe"], t, best["skew"], best["kurtosis"], n,
                                    rs.trial_sharpe_variance([m["sharpe"] for m in moments])["sharpe_variance"])
        self.assertEqual(got["metrics"]["dsr"], direct["dsr"])
        self.assertEqual(got["metrics"]["pbo"], rs.pbo_cscv(series, axis(t), s=6)["pbo"])


class Costs(unittest.TestCase):
    def test_no_floor_is_missing(self):
        got = ve.check_costs(gross_bps_per_trade=40.0, assumed_cost_bps=12.0)
        self.assertEqual(got["status"], ve.MISSING_INPUT)
        self.assertEqual(got["missing"], ["floor_cost_bps"])

    def test_no_edge_fails_and_marginal_edge_is_inconclusive(self):
        self.assertEqual(ve.check_costs(5.0, 12.0, 10.0)["status"], ve.FAIL)
        self.assertEqual(ve.check_costs(15.0, 10.0, 10.0)["status"], ve.INCONCLUSIVE)
        self.assertEqual(ve.check_costs(40.0, 10.0, 10.0)["status"], ve.PASS)

    def test_higher_assumed_cost_than_floor_is_used(self):
        self.assertEqual(ve.check_costs(30.0, 20.0, 10.0)["status"], ve.INCONCLUSIVE)


class Combination(unittest.TestCase):
    def test_precedence(self):
        make = lambda s: ve.result("x", s, "r")      # noqa: E731
        order = [(ve.CONTAMINATED, ve.FAIL), (ve.FAIL, ve.MISSING_INPUT), (ve.MISSING_INPUT, ve.INCONCLUSIVE),
                 (ve.INCONCLUSIVE, ve.PASS)]
        for worse, better in order:
            checks = [dict(make(better), check="a"), dict(make(worse), check="b")]
            self.assertEqual(ve.assess(checks, required=("a", "b"))["status"], worse)

    def test_a_check_that_did_not_run_blocks_pass(self):
        spec = clean_spec(real_effect_series())
        spec.pop(ve.COSTS)
        got = ve.evaluate(spec)
        self.assertEqual(got["status"], ve.MISSING_INPUT)
        self.assertEqual(got["missing_checks"], [ve.COSTS])

    def test_empty_is_missing(self):
        self.assertEqual(ve.assess([])["status"], ve.MISSING_INPUT)

    def test_unknown_check_is_refused(self):
        with self.assertRaises(ValueError):
            ve.evaluate({"nope": {}})

    def test_evaluate_is_deterministic(self):
        spec = clean_spec(real_effect_series(10, 300, 3))
        spec[ve.OVERFITTING]["s"] = 6
        self.assertEqual(ve.evaluate(spec), ve.evaluate(spec))


class RegisterLink(unittest.TestCase):
    def test_a_historical_record_gives_missing_input_all_the_way(self):
        got = v2.validation_inputs(v2.record("OLD", v2.HISTORICAL))
        mt = ve.check_multiple_testing(best_t=5.0, n_tested=got["n_tested"], n_preregistered=got["n_preregistered"])
        self.assertEqual(mt["status"], ve.MISSING_INPUT)
        cost = ve.check_costs(gross_bps_per_trade=40.0, assumed_cost_bps=got["assumed_cost_bps"], floor_cost_bps=10.0)
        self.assertEqual(cost["status"], ve.MISSING_INPUT)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
