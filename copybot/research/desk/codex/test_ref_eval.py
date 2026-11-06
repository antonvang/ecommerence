"""Spec-derived unit tests using only small, hand-authored synthetic inputs."""

import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ref_eval import (adjust_multiple, atomic_write, canonical_json, evaluate,
                      evaluate_ledger, hac_statistics)


def hypothesis(hid="H", **changes):
    result = dict(hid=hid, family="F", signal_key="s", rule="sign",
                  cost_bps=0.0, funding=False)
    result.update(changes)
    return result


def row(ts, asset="A", ret=0.1, value=1.0, avail_ts=None, funding=0.0):
    return dict(ts=ts, asset=asset, ret=ret, funding=funding,
                signals={"s": dict(value=value,
                                   avail_ts=ts if avail_ts is None else avail_ts)})


def fixture(observations=(), end=1, hypotheses=None, universe=None, cadence=1):
    return dict(fixture_id="unit", cadence_s=cadence, alpha=0.05, q_fdr=0.05,
                window=dict(start=0, end=end),
                universe=({"A": dict(listed_from=0, delisted_at=None)}
                          if universe is None else universe),
                hypotheses=[hypothesis()] if hypotheses is None else hypotheses,
                observations=list(observations), ledger_requests=[])


def only(data):
    return evaluate(data)["hypotheses"]["H"]


def request(key="k", **changes):
    result = dict(key=key, hid="H", family="F", variants=1, alpha=0.01, ts=0)
    result.update(changes)
    return result


class TimeAndMembershipTests(unittest.TestCase):
    def test_grid_start_end_cadence_and_first_file_row(self):
        data = fixture([row(13, ret=0.3), row(10, ret=0.2), row(10, ret=0.9),
                        row(11), row(16), row(7)], end=16, cadence=3)
        data["window"]["start"] = 10
        data["universe"]["A"]["listed_from"] = 10
        result = only(data)
        self.assertEqual((result["T"], result["n_offgrid"], result["n_duplicates"]),
                         (2, 3, 1))
        self.assertEqual(result["mean_net"], 0.25)

    def test_filter_order_offgrid_then_duplicates_then_membership(self):
        data = fixture([row(99, "X"), row(99, "X"), row(0, "X"), row(0, "X")])
        result = only(data)
        self.assertEqual((result["n_offgrid"], result["n_duplicates"],
                          result["n_not_member"]), (2, 1, 1))
        self.assertEqual((result["n_gap_bars"], result["n_empty_bars"]), (0, 1))

    def test_membership_boundaries_and_delisted_history(self):
        universe = {"A": dict(listed_from=1, delisted_at=3)}
        result = only(fixture([row(t) for t in range(4)] + [row(2, "X")],
                              end=4, universe=universe))
        self.assertEqual((result["T"], result["n_not_member"]), (2, 3))
        self.assertAlmostEqual(result["mean_net"], 0.1)
        self.assertEqual(result["n_empty_bars"], 2)

    def test_common_counts_repeated_for_each_hypothesis(self):
        data = fixture([row(99), row(0, "X"), row(0, "X"), row(0)],
                       hypotheses=[hypothesis(), hypothesis("J", rule="clip1")])
        results = evaluate(data)["hypotheses"]
        for result in results.values():
            self.assertEqual([result[k] for k in ("n_offgrid", "n_duplicates",
                                                  "n_not_member")], [1, 1, 1])


class PositionAndPortfolioTests(unittest.TestCase):
    def test_missing_returns_skip_signal_funding_cost_and_extreme(self):
        invalid = [None, "NaN", "Infinity", "-Infinity", float("nan"),
                   float("inf"), -float("inf")]
        observations = [row(i, ret=value, value=None, funding=None)
                        for i, value in enumerate(invalid)]
        result = only(fixture(observations, end=len(invalid),
                              hypotheses=[hypothesis(funding=True, cost_bps=10)]))
        self.assertEqual(result["n_missing_ret"], len(invalid))
        for key in ("n_signal_missing", "n_lookahead", "n_funding_missing",
                    "n_extreme", "total_cost", "total_funding", "T"):
            self.assertEqual(result[key], 0)
        self.assertIsNone(result["mean_net"])
        self.assertEqual(result["n_empty_bars"], len(invalid))

    def test_missing_signal_precedes_lookahead_and_still_exits(self):
        observations = [row(0), row(1, value=None, avail_ts=99),
                        row(2, value="NaN"), row(3, value="Infinity"),
                        row(4, value="-Infinity"), row(5)]
        observations[-1]["signals"] = {}
        result = only(fixture(observations, end=6,
                              hypotheses=[hypothesis(cost_bps=10)]))
        self.assertEqual(result["n_signal_missing"], 5)
        self.assertEqual(result["n_lookahead"], 0)
        self.assertEqual(result["T"], 6)
        self.assertAlmostEqual(result["total_cost"], 0.002)
        self.assertAlmostEqual(result["mean_net"], (0.1 - 0.002) / 6)

    def test_availability_equal_allowed_future_blocked_and_charged(self):
        result = only(fixture([row(0, avail_ts=0), row(1, avail_ts=2),
                               row(2, avail_ts=1)], end=3,
                              hypotheses=[hypothesis(cost_bps=10)]))
        self.assertEqual(result["n_lookahead"], 1)
        self.assertEqual(result["n_signal_missing"], 0)
        self.assertAlmostEqual(result["total_cost"], 0.003)
        self.assertAlmostEqual(result["mean_net"], 0.197 / 3)

    def test_sign_and_clip_rules(self):
        values = [-2.0, -0.25, 0.0, 0.5, 2.0]
        observations = [row(i, ret=0.2, value=v) for i, v in enumerate(values)]
        results = evaluate(fixture(observations, end=5, hypotheses=[
            hypothesis(), hypothesis("clip", rule="clip1")]))["hypotheses"]
        self.assertAlmostEqual(results["H"]["mean_net"], 0.0)
        self.assertAlmostEqual(results["clip"]["mean_net"], 0.01)

    def test_turnover_entry_reversal_fraction_and_flat(self):
        observations = [row(i, ret=0.0, value=v)
                        for i, v in enumerate([0.5, -1, -1, 0])]
        result = only(fixture(observations, end=4, hypotheses=[
            hypothesis(rule="clip1", cost_bps=100)]))
        self.assertAlmostEqual(result["total_cost"], 0.03)
        self.assertAlmostEqual(result["mean_net"], -0.0075)

    def test_gap_and_missing_return_reset_previous_position(self):
        for middle in ([], [row(1, ret=None)]):
            with self.subTest(middle=middle):
                result = only(fixture([row(0)] + middle + [row(2, value=-1)],
                                      end=3, hypotheses=[hypothesis(cost_bps=10)]))
                self.assertAlmostEqual(result["total_cost"], 0.002)
                self.assertEqual(result["T"], 2)
                self.assertEqual(result["n_gap_bars"], int(not middle))
                self.assertEqual(result["n_empty_bars"], int(bool(middle)))

    def test_asset_hole_resets_even_when_other_asset_has_a_bar(self):
        universe = {asset: dict(listed_from=0, delisted_at=None)
                    for asset in ("A", "B")}
        result = only(fixture([row(0), row(1, "B", value=0), row(2)], end=3,
                              universe=universe,
                              hypotheses=[hypothesis(cost_bps=10)]))
        self.assertAlmostEqual(result["total_cost"], 0.002)
        self.assertEqual(result["T"], 3)
        self.assertEqual(result["n_gap_bars"], 0)

    def test_funding_sign_missing_and_disabled(self):
        observations = [row(0, ret=0, value=1, funding=0.01),
                        row(1, ret=0, value=-1, funding=0.02),
                        row(2, ret=0, value=0, funding=None),
                        row(3, ret=0, funding="Infinity")]
        results = evaluate(fixture(observations, end=4, hypotheses=[
            hypothesis(), hypothesis("fund", funding=True, family="other")
        ]))["hypotheses"]
        self.assertEqual(results["H"]["n_funding_missing"], 0)
        self.assertEqual(results["H"]["total_funding"], 0)
        self.assertEqual(results["fund"]["n_funding_missing"], 2)
        self.assertAlmostEqual(results["fund"]["total_funding"], -0.01)
        self.assertAlmostEqual(results["fund"]["mean_net"], 0.0025)

    def test_extreme_is_strict_and_kept_even_for_zero_position(self):
        result = only(fixture([row(0, ret=0.5), row(1, ret=-0.5),
                               row(2, ret=0.6), row(3, ret=-0.6, value=0)], end=4))
        self.assertEqual(result["n_extreme"], 2)
        self.assertEqual(result["T"], 4)
        self.assertAlmostEqual(result["mean_net"], 0.15)

    def test_equal_weight_valid_bars_including_zero_weight(self):
        universe = {a: dict(listed_from=0, delisted_at=None) for a in "ABC"}
        observations = [row(0, "A", ret=0.2), row(0, "B", ret=0.4, value=None),
                        row(0, "C", ret=None), row(1, "A", ret=0.4)]
        result = only(fixture(observations, end=2, universe=universe,
                              hypotheses=[hypothesis(cost_bps=100, funding=True)]))
        self.assertAlmostEqual(result["mean_gross"], 0.25)
        self.assertAlmostEqual(result["mean_net"], 0.2475)
        self.assertAlmostEqual(result["total_cost"], 0.01)
        self.assertEqual(result["n_missing_ret"], 1)

    def test_gap_empty_and_no_valid_series(self):
        result = only(fixture([row(1, "X"), row(2, ret=None)], end=4))
        self.assertEqual((result["n_gap_bars"], result["n_empty_bars"]), (2, 2))
        self.assertEqual(result["T"], 0)
        for key in ("mean_gross", "mean_net", "hac_lag", "se", "t", "p_one",
                    "holm_reject", "bh_reject"):
            self.assertIsNone(result[key])

    def test_empty_window(self):
        result = evaluate(fixture(end=0))
        self.assertEqual(result["status"], "INVALID_INPUT")
        self.assertIn(dict(code="BAD_VALUE", path="window"), result["errors"])


class StatisticsAndMultiplicityTests(unittest.TestCase):
    def test_short_series_and_zero_variance(self):
        for series in ([], [1.0, -1.0] * 14 + [1.0], [0.0] * 30):
            with self.subTest(size=len(series)):
                result = hac_statistics(series)
                self.assertEqual(result["status"], "INSUFFICIENT")
                for key in ("se", "t", "p_one"):
                    self.assertIsNone(result[key])
                self.assertEqual(result["hac_lag"], 3 if len(series) == 30 else None)

    def test_hac_against_closed_form_alternating_series(self):
        # T=30, L=3; gamma_k=(-1)^k*(30-k)/30 gives S=1/30.
        base = [1.0, -1.0] * 15
        result = hac_statistics(base)
        self.assertEqual(result["status"], "TESTED")
        self.assertEqual(result["hac_lag"], 3)
        self.assertAlmostEqual(result["se"], 1 / 30, places=14)
        self.assertEqual(result["t"], 0.0)
        self.assertEqual(result["p_one"], 0.5)
        positive = hac_statistics([x + 0.125 for x in base])
        negative = hac_statistics([x - 0.125 for x in base])
        self.assertAlmostEqual(positive["t"], 3.75, places=12)
        self.assertAlmostEqual(positive["p_one"], 0.00008841728520080039, places=15)
        self.assertAlmostEqual(positive["p_one"] + negative["p_one"], 1.0)

    def test_lag_formula_at_distinct_lengths(self):
        for size, lag in ((30, 3), (100, 4), (400, 5)):
            self.assertEqual(hac_statistics([1.0, -1.0] * (size // 2))["hac_lag"], lag)

    def test_hac_uses_compressed_valid_series(self):
        observations = [row(2 * i, ret=(1 if i % 2 == 0 else -1)) for i in range(30)]
        result = only(fixture(observations, end=60))
        self.assertEqual((result["T"], result["n_gap_bars"]), (30, 30))
        self.assertAlmostEqual(result["se"], 1 / 30, places=14)

    def test_duplicate_fingerprint_ignores_cost_and_funding_keeps_statistics(self):
        hypotheses = [hypothesis(), hypothesis("copy", cost_bps=10, funding=True),
                      hypothesis("copy2"), hypothesis("family", family="other"),
                      hypothesis("rule", rule="clip1"),
                      hypothesis("signal", signal_key="different")]
        observations = [row(i, ret=(0.2 if i % 2 == 0 else -0.1)) for i in range(30)]
        for observation in observations:
            observation["signals"]["different"] = dict(value=1, avail_ts=0)
        results = evaluate(fixture(observations, end=30,
                                   hypotheses=hypotheses))["hypotheses"]
        for hid in ("copy", "copy2"):
            self.assertEqual(results[hid]["status"], "DUPLICATE")
            self.assertEqual(results[hid]["duplicate_of"], "H")
            self.assertIsNotNone(results[hid]["p_one"])
            self.assertIsNone(results[hid]["holm_reject"])
            self.assertIsNone(results[hid]["bh_reject"])
        self.assertNotEqual(results["copy"]["mean_net"], results["H"]["mean_net"])
        for hid in ("family", "rule", "signal"):
            self.assertIsNone(results[hid]["duplicate_of"])
        short = evaluate(fixture([observations[0]], hypotheses=hypotheses))["hypotheses"]
        self.assertEqual(short["copy"]["status"], "DUPLICATE")
        self.assertIsNone(short["copy"]["t"])

    def test_holm_stops_bh_uses_largest_qualifying_rank(self):
        results = {"C": dict(status="TESTED", p_one=0.04),
                   "A": dict(status="TESTED", p_one=0.02),
                   "B": dict(status="TESTED", p_one=0.03),
                   "D": dict(status="DUPLICATE", p_one=0.0),
                   "I": dict(status="INSUFFICIENT", p_one=None)}
        adjust_multiple(results, 0.05, 0.05)
        for hid in "ABC":
            self.assertFalse(results[hid]["holm_reject"])
            self.assertTrue(results[hid]["bh_reject"])
        for hid in "DI":
            self.assertIsNone(results[hid]["holm_reject"])
            self.assertIsNone(results[hid]["bh_reject"])

    def test_inclusive_thresholds_sorting_equal_p_and_no_rejections(self):
        results = {"third": dict(status="TESTED", p_one=0.03),
                   "first": dict(status="TESTED", p_one=0.01),
                   "second": dict(status="TESTED", p_one=0.01)}
        adjust_multiple(results, 0.03, 0.03)
        self.assertTrue(all(r["holm_reject"] for r in results.values()))
        self.assertTrue(all(r["bh_reject"] for r in results.values()))
        adjust_multiple(results, 0.0, 0.0)
        self.assertFalse(any(r["holm_reject"] or r["bh_reject"] for r in results.values()))
        adjust_multiple({}, 0.05, 0.05)


class LedgerTests(unittest.TestCase):
    def test_empty_ledger_genesis(self):
        self.assertEqual(evaluate_ledger([]), dict(entries=0, head="0" * 64,
                         idempotent_hits=0, errors=[], totals={}))

    def test_canonical_hash_chain_and_request_order(self):
        # Literal preimages keep this independent of post construction code.
        preimage0 = ('{"alpha":0.01,"family":"F","hid":"H","key":"k",'
                     '"prev":"' + "0" * 64 + '","seq":0,"ts":0,"variants":1}')
        head0 = hashlib.sha256(preimage0.encode()).hexdigest()
        first = evaluate_ledger([request()])
        self.assertEqual(first["head"], head0)
        preimage1 = ('{"alpha":0.02,"family":"F","hid":"J","key":"j",'
                     '"prev":"' + head0 + '","seq":1,"ts":1,"variants":2}')
        second = request("j", hid="J", alpha=0.02, variants=2, ts=1)
        both = evaluate_ledger([request(), second])
        self.assertEqual(both["head"], hashlib.sha256(preimage1.encode()).hexdigest())
        self.assertEqual(both["entries"], 2)
        self.assertNotEqual(evaluate_ledger([second, request()])["head"], both["head"])

    def test_idempotency_precedes_validation(self):
        result = evaluate_ledger([request(), request(variants=False, alpha=-1)])
        self.assertEqual(result["entries"], 1)
        self.assertEqual(result["idempotent_hits"], 0)
        self.assertEqual(result["errors"], [dict(key="k", reason="key_conflict")])
        self.assertEqual(result["head"], evaluate_ledger([request()])["head"])

    def test_invalid_variants_reason_precedence_and_retry(self):
        invalid = [True, False, 0, -1, 1.0, 2.5, "1", None, [], {}]
        requests = [request(str(i), variants=v, alpha=-1)
                    for i, v in enumerate(invalid)]
        result = evaluate_ledger(requests + [request("0", variants=2)])
        self.assertEqual(result["entries"], 1)
        self.assertEqual(result["idempotent_hits"], 0)
        self.assertEqual(result["errors"], [dict(key=str(i), reason="variants")
                                            for i in range(len(invalid))])

    def test_invalid_alpha_and_rejected_key_can_retry(self):
        invalid = [-0.01, float("inf"), -float("inf"), float("nan")]
        requests = [request(str(i), alpha=a) for i, a in enumerate(invalid)]
        result = evaluate_ledger(requests + [request("0", alpha=0.0)])
        self.assertEqual(result["entries"], 1)
        self.assertEqual(result["idempotent_hits"], 0)
        self.assertEqual(result["errors"], [dict(key=str(i), reason="alpha")
                                            for i in range(4)])

    def test_totals_count_only_accepted_posts_distinct_hids_per_family(self):
        result = evaluate_ledger([request(), request(), request("b", variants=3),
                                  request("c", hid="J", alpha=0.02),
                                  request("d", family="G", variants=2, alpha=1.5),
                                  request("bad", family="bad", variants=0)])
        self.assertEqual(result["totals"], {
            "F": dict(attempts=3, variants=5, alpha=0.04, hypotheses=2),
            "G": dict(attempts=1, variants=2, alpha=1.5, hypotheses=1)})
        self.assertEqual(result["idempotent_hits"], 1)


class OutputTests(unittest.TestCase):
    def test_output_schema_and_no_input_mutation(self):
        data = fixture([row(0)])
        before = copy.deepcopy(data)
        result = evaluate(data)
        self.assertEqual(data, before)
        self.assertEqual(set(result), {"spec_version", "fixture_id", "status", "hypotheses", "ledger"})
        self.assertEqual((result["spec_version"], result["status"]), ("1.1", "OK"))
        expected = ("status duplicate_of T n_offgrid n_duplicates n_not_member n_missing_ret "
                    "n_signal_missing n_lookahead n_funding_missing n_extreme n_gap_bars "
                    "n_empty_bars n_embargo mean_gross mean_net total_cost total_funding hac_lag "
                    "se t p_one holm_reject bh_reject").split()
        self.assertEqual(set(result["hypotheses"]["H"]), set(expected))
        self.assertEqual(json.loads(canonical_json(result)), result)

    def test_canonical_unicode_and_finite_guard(self):
        self.assertEqual(canonical_json({"z": 1.25, "a": "æ"}), '{"a":"æ","z":1.25}')
        with self.assertRaises(ValueError):
            canonical_json({"bad": float("nan")})

    def test_cli_multiple_inputs_exact_encoding_and_repeated_bytes(self):
        script = Path(__file__).with_name("ref_eval.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = []
            for i in range(2):
                data = fixture([row(0, ret=0.1 * i)])
                data["fixture_id"] = "unit" + str(i)
                path = root / (str(i) + ".json")
                path.write_text(json.dumps(data), encoding="utf-8")
                inputs.append(str(path))
            for name in ("one", "two"):
                subprocess.run([sys.executable, "-I", str(script), *inputs,
                                "--out", str(root / name)], check=True)
            for i in range(2):
                path = "unit" + str(i) + ".json"
                output = (root / "one" / path).read_bytes()
                self.assertEqual(output, (root / "two" / path).read_bytes())
                expected = evaluate(json.loads(Path(inputs[i]).read_text()))
                self.assertEqual(output, canonical_json(expected).encode("utf-8"))


class Version11Tests(unittest.TestCase):
    def test_embargo_filter_precedes_dedup_and_first_position_is_zero(self):
        data = fixture([row(0), row(0), row(1), row(2), row(3, value=-1)],
                       end=4, cadence=2, hypotheses=[hypothesis(cost_bps=10)])
        data["window"]["embargo_s"] = 2
        result = only(data)
        self.assertEqual((result["n_embargo"], result["n_offgrid"],
                          result["n_duplicates"], result["T"]), (2, 2, 0, 1))
        self.assertAlmostEqual(result["total_cost"], 0.001)
        self.assertEqual((result["n_gap_bars"], result["n_empty_bars"]), (0, 0))

    def test_non_aligned_embargo_and_zero(self):
        data = fixture([row(t) for t in (0, 2, 4)], end=6, cadence=2)
        data["window"]["embargo_s"] = 3
        self.assertEqual((only(data)["T"], only(data)["n_embargo"]), (1, 2))
        data["window"]["embargo_s"] = 0
        self.assertEqual(only(data)["T"], 3)

    def test_fsum_portfolio_funding_and_ledger_totals(self):
        universe = {a: dict(listed_from=0, delisted_at=None) for a in "DCBA"}
        observations = [row(0, a, ret=v, funding=v)
                        for a, v in zip("ABCD", [1e16, 1.0, -1e16, 3.0])]
        result = only(fixture(observations, universe=universe,
                              hypotheses=[hypothesis(funding=True)]))
        self.assertEqual(result["mean_gross"], 1.0)
        self.assertEqual(result["total_funding"], 4.0)
        ledger = evaluate_ledger([request(str(i), alpha=a)
                                  for i, a in enumerate([1e16, 1.0, 1.0])])
        self.assertEqual(ledger["totals"]["F"]["alpha"], 10000000000000002.0)

    def test_key_replay_ignores_ts_and_compares_parsed_numeric_values(self):
        result = evaluate_ledger([request(alpha=0), request(alpha=0.0, ts=1),
                                  request(alpha=0.1)])
        self.assertEqual((result["entries"], result["idempotent_hits"]), (1, 1))
        self.assertEqual(result["errors"], [dict(key="k", reason="key_conflict")])
        self.assertNotEqual(evaluate_ledger([request(alpha=0)])["head"],
                            evaluate_ledger([request(alpha=0.0)])["head"])

    def test_ledger_nonnumeric_alpha_is_post_error_not_invalid_input(self):
        data = fixture([row(0)])
        data["ledger_requests"] = [request(str(i), alpha=value)
                                   for i, value in enumerate([None, "0.1", True, [], {}])]
        result = evaluate(data)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["ledger"]["entries"], 0)
        self.assertEqual([e["reason"] for e in result["ledger"]["errors"]], ["alpha"] * 5)

    def test_validation_collects_errors_sorted_and_never_evaluates(self):
        data = fixture([row(0)])
        del data["q_fdr"]
        data["surprise"] = 1
        data["hypotheses"][0]["cost_bps"] = -1
        data["hypotheses"][0]["fee_bps"] = 2
        data["observations"][0]["ts"] = "UTC"
        with patch("ref_eval.hac_statistics", side_effect=AssertionError("partial work")):
            result = evaluate(data)
        self.assertEqual(set(result), {"spec_version", "fixture_id", "status", "errors"})
        pairs = [(e["code"], e["path"]) for e in result["errors"]]
        self.assertEqual(pairs, sorted(set(pairs)))
        self.assertEqual(set(c for c, p in pairs),
                         {"MISSING_FIELD", "UNKNOWN_FIELD", "BAD_VALUE", "BAD_TIME", "BAD_TYPE"})

    def test_all_timestamp_locations_boundaries_and_bool_rejection(self):
        for name in ("window", "listing", "delisting", "row", "signal", "ledger"):
            data = fixture([row(0)])
            data["ledger_requests"] = [request()]
            targets = {
                "window": (data["window"], "start"),
                "listing": (data["universe"]["A"], "listed_from"),
                "delisting": (data["universe"]["A"], "delisted_at"),
                "row": (data["observations"][0], "ts"),
                "signal": (data["observations"][0]["signals"]["s"], "avail_ts"),
                "ledger": (data["ledger_requests"][0], "ts")}
            target, key = targets[name]
            for value in (True, 0.0, -1, 4102444801, "2026-01-01T00:00:00Z"):
                target[key] = value
                with self.subTest(name=name, value=value):
                    self.assertIn("BAD_TIME", [e["code"] for e in evaluate(data)["errors"]])

    def test_missing_id_is_null_and_malformed_containers_fail_closed(self):
        data = fixture([row(0)])
        del data["fixture_id"]
        self.assertIsNone(evaluate(data)["fixture_id"])
        for value in (None, [], 1, "fixture"):
            self.assertEqual(evaluate(value)["status"], "INVALID_INPUT")
        data = fixture([row(0)])
        data.update(hypotheses=[None], observations=[[]], universe=[], ledger_requests={})
        self.assertEqual(evaluate(data)["status"], "INVALID_INPUT")

    def test_lock_components_are_independently_checked(self):
        data = fixture([row(0)])
        digest = lambda obj: hashlib.sha256(canonical_json(obj).encode()).hexdigest()
        data["lock"] = dict(protocol_sha256=digest({k: data[k] for k in
            ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}),
            data_sha256=digest(data["observations"]))
        self.assertEqual(evaluate(data)["status"], "OK")
        for kind in ("protocol_sha256", "data_sha256"):
            changed = copy.deepcopy(data)
            changed["lock"][kind] = "0" * 64
            self.assertEqual(evaluate(changed)["errors"],
                             [dict(code="LOCK_MISMATCH", path="lock." + kind)])
        data["lock"] = {}
        self.assertEqual(len(evaluate(data)["errors"]), 2)

    def test_atomic_replace_restart_and_replace_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "restart.json"
            target.write_bytes(b'{"broken":')
            atomic_write(target, b'{"complete":true}')
            self.assertEqual(target.read_bytes(), b'{"complete":true}')
            with patch("ref_eval.os.replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    atomic_write(target, b'{"next":true}')
            self.assertEqual(target.read_bytes(), b'{"complete":true}')
            self.assertEqual(list(Path(directory).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
