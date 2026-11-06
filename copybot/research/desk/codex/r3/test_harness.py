"""Check detector semantics and immutable artifacts without rerunning mutants."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("harness", ROOT / "run_mutants.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class HarnessTests(unittest.TestCase):
    def test_exact_structure_and_fixed_numeric_tolerance(self):
        self.assertEqual(harness.differences(1.0, 1.0 + 5e-10), [])
        self.assertTrue(harness.differences(1.0, 1.0 + 2e-9))
        self.assertTrue(harness.differences(True, 1))
        self.assertTrue(harness.differences(None, 0))
        self.assertTrue(harness.differences({"a": 1}, {"b": 1}))
        self.assertTrue(harness.differences([1], [1, 2]))
        self.assertTrue(harness.differences(float("inf"), float("inf")))

    def test_frozen_reference_expected_and_evaluator(self):
        self.assertEqual(harness.verify_frozen()["spec_version"], "1.1.1")

    def test_first_observations_preserved_and_initial_survivors_explicit(self):
        plan = json.loads((ROOT / "SUPPLEMENT_PLAN.json").read_text())
        initial_raw = (ROOT / "MUTATION_RESULTS_INITIAL.json").read_bytes()
        self.assertEqual(hashlib.sha256(initial_raw).hexdigest(), plan["initial_results_sha256"])
        initial = json.loads(initial_raw)
        self.assertEqual(initial["survivors"], ["M23", "M27", "M41", "M45"])
        self.assertEqual(initial["rates"]["SIKKERHEDSKRITISK"], dict(detected=28, total=28, rate=1.0))

    def test_final_scores_equivalents_and_silent_witnesses(self):
        report = json.loads((ROOT / "MUTATION_RESULTS.json").read_text())
        self.assertEqual((report["total_mutants"], report["non_equivalent"]), (45, 43))
        self.assertEqual(report["equivalent_ids"], ["M43", "M44"])
        self.assertEqual(report["final_survivors"], [])
        self.assertGreaterEqual(report["silent_witnesses"], 5)
        for classification in ("SIKKERHEDSKRITISK", "ØVRIG"):
            self.assertEqual(report["final_rates"][classification]["rate"], 1.0)
        for mutant in report["mutants"]:
            self.assertEqual(mutant["tests"]["tests_run"], 25)
            if mutant["equivalent"]:
                self.assertEqual(mutant["detected_by"], "ingen")
            if mutant["id"] in report["initial_survivors"]:
                self.assertTrue(mutant["initially_survived"])
                self.assertTrue(mutant["detected_after_addition"])
        self.assertEqual(report["baseline_matching_fixtures"], report["baseline_fixture_count"] - 1)


if __name__ == "__main__":
    unittest.main()
