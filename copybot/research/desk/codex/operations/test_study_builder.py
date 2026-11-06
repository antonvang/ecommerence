"""Determinism, causal signals and schema checks for synthetic study proposals."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest

from study_builder import (ASSETS, CADENCE_S, RECIPES, START, build_demo,
                           signals_from_history)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


class StudyBuilderTests(unittest.TestCase):
    def test_seed_determinism_and_predeclared_recipe_order(self):
        first = build_demo(seed=52, bars=12)
        self.assertEqual(canonical(first), canonical(build_demo(seed=52, bars=12)))
        self.assertNotEqual(first["candidates"][0]["fixture"]["observations"],
                            build_demo(seed=53, bars=12)["candidates"][0]["fixture"]["observations"])
        self.assertEqual([(c["protocol"]["recipe"], c["protocol"]["lookback"])
                          for c in first["candidates"]], list(RECIPES))
        self.assertEqual((first["mode"], first["source"]), ("synthetic", {"kind": "synthetic", "seed": 52}))
        self.assertLess(first["created_at"], START)

    def test_closing_price_never_enters_same_bar_signal(self):
        mids = [100.0, 101.0, 99.0, 104.0, 103.0, 107.0]
        funding = [0.00001, -0.00002, 0.00003, -0.00004, 0.00005]
        for recipe, lookback in RECIPES:
            before = signals_from_history(recipe, lookback, mids, funding)
            changed = list(mids)
            changed[-1] *= 100
            self.assertEqual(before, signals_from_history(recipe, lookback, changed, funding))
            changed = list(mids)
            changed[3] *= 2
            self.assertEqual(before[:3], signals_from_history(recipe, lookback, changed, funding)[:3])

    def test_future_funding_does_not_change_earlier_signals(self):
        mids = [100.0, 101.0, 102.0, 103.0, 104.0]
        funding = [0.00001, -0.00002, 0.00003, 0.00004]
        for recipe, lookback in RECIPES:
            before = signals_from_history(recipe, lookback, mids, funding)
            for i in range(len(funding)):
                changed = funding[:i] + [-0.1] * (len(funding) - i)
                after = signals_from_history(recipe, lookback, mids, changed)
                self.assertEqual(before[:i + 1], after[:i + 1])

    def test_funding_carry_uses_completed_bars_only(self):
        values = signals_from_history("funding_carry", 3, [100.0] * 5,
                                      [0.00001, -0.00002, 0.00003, 0.9])
        self.assertEqual(values[0], 0.0)
        self.assertAlmostEqual(values[1], -0.1)
        self.assertAlmostEqual(values[2], 0.05)
        self.assertAlmostEqual(values[3], -(0.00001 - 0.00002 + 0.00003) / 3 / 0.0001)

    def test_fixture_locks_consistency_order_and_paper_events(self):
        study = build_demo("unit", bars=40, candidates=9)
        ids = []
        for candidate in study["candidates"]:
            ids.append(candidate["candidate_id"])
            protocol, fixture = candidate["protocol"], candidate["fixture"]
            hypothesis = fixture["hypotheses"][0]
            self.assertEqual(hypothesis["hid"], candidate["candidate_id"])
            self.assertEqual(hypothesis["family"], candidate["family"])
            for key in ("rule", "signal_key", "cost_bps", "funding"):
                self.assertEqual(protocol[key], hypothesis[key])
            for key in ("window", "cadence_s", "universe"):
                self.assertEqual(protocol[key], fixture[key])
            core = {k: fixture[k] for k in
                    ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}
            self.assertEqual(fixture["lock"]["protocol_sha256"], hashlib.sha256(canonical(core)).hexdigest())
            self.assertEqual(fixture["lock"]["data_sha256"],
                             hashlib.sha256(canonical(fixture["observations"])).hexdigest())
            rows, events = fixture["observations"], candidate["paper_events"]
            self.assertEqual(len(rows), 40 * len(ASSETS))
            self.assertEqual([(r["ts"], r["asset"]) for r in rows],
                             sorted((r["ts"], r["asset"]) for r in rows))
            self.assertEqual(len({event["key"] for event in events}), len(events))
            for row, event in zip(rows, events):
                signal = row["signals"][protocol["signal_key"]]
                self.assertEqual((row["ts"], row["asset"], signal["value"]),
                                 (event["ts"], event["asset"], event["signal"]))
                self.assertLessEqual(signal["avail_ts"], row["ts"])
                self.assertEqual((event["avail_ts"], event["quote_ts"]), (row["ts"], row["ts"]))
                self.assertLess(event["bid"], event["ask"])
                self.assertLessEqual(abs(event["signal"]), 1)
                self.assertTrue(math.isfinite(row["ret"]))
            self.assertEqual(candidate["paper_plan"]["protocol_id"], candidate["candidate_id"])
        self.assertEqual(len(set(ids)), len(ids))

    def test_last_return_binds_terminal_mark_without_an_extra_trade(self):
        for candidate in build_demo(bars=7, candidates=9)["candidates"]:
            rows, events = candidate["fixture"]["observations"], candidate["paper_events"]
            self.assertEqual(len(events), 7 * len(ASSETS))
            self.assertEqual(set(candidate["terminal_marks"]), set(ASSETS))
            for asset in ASSETS:
                last_row = next(row for row in reversed(rows) if row["asset"] == asset)
                last_event = next(event for event in reversed(events) if event["asset"] == asset)
                current_mid = (last_event["bid"] + last_event["ask"]) / 2
                terminal_mid = candidate["terminal_marks"][asset]
                self.assertGreater(terminal_mid, 0)
                self.assertTrue(math.isfinite(terminal_mid))
                self.assertAlmostEqual(last_row["ret"], terminal_mid / current_mid - 1, places=14)

    def test_fixtures_pass_independent_v111_schema(self):
        path = Path(__file__).resolve().parents[1] / "r3/ref_eval.py"
        spec = importlib.util.spec_from_file_location("study_test_ref_eval", path)
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        for candidate in build_demo(bars=30)["candidates"]:
            self.assertEqual(reference.validate(candidate["fixture"]), [])

    def test_generated_candidates_do_not_share_mutable_protocol_or_data(self):
        study = build_demo(bars=3, candidates=2)
        first, second = study["candidates"]
        saved_second = copy.deepcopy(second)
        first["fixture"]["universe"]["SYN_A"]["listed_from"] = 0
        first["fixture"]["observations"][0]["ret"] = 0.5
        self.assertEqual(second, saved_second)
        self.assertEqual(first["protocol"]["universe"]["SYN_A"]["listed_from"], START)

    def test_bad_builder_arguments(self):
        invalid = [dict(study_id=""), dict(study_id="../x"), dict(study_id="æ"),
                   dict(study_id="x" * 129), dict(seed=True), dict(seed=1.0),
                   dict(bars=True), dict(bars=0), dict(bars=1001), dict(bars=30.0),
                   dict(candidates=0), dict(candidates=10), dict(candidates=True)]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_demo(**changes)

    def test_bad_history_arguments(self):
        invalid = [("unknown", 1, [100, 101], [0]), ("momentum", True, [100, 101], [0]),
                   ("momentum", 1, [100], [0]), ("momentum", 1, [100, 0], [0]),
                   ("momentum", 1, [100, float("inf")], [0]),
                   ("funding_carry", 1, [100, 101], [float("nan")]),
                   ("momentum", 1, [True, 101], [0])]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                signals_from_history(*args)


if __name__ == "__main__":
    unittest.main()
