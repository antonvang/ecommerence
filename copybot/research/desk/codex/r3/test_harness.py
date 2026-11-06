"""Check detector semantics and immutable artifacts without rerunning mutants."""
import hashlib
import importlib.util
import json
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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

    def test_source_trust_and_baseline_gates_survive_python_optimization(self):
        code = '''import importlib.util,json,sys
p=sys.argv[1]
s=importlib.util.spec_from_file_location("gate_under_test",p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.SOURCE_MANIFEST_SHA256="0"*64
try:
    m.verify_frozen()
except m.IntegrityError:
    pass
else:
    raise RuntimeError("wrong digest accepted")
m.SOURCE_MANIFEST_SHA256=sys.argv[2]
try:
    m.verify_baseline_contract("augmented",[None]*79,{"new_error":[{"path":".status","expected":"OK","actual":"NUMERIC_ERROR"}]})
except m.GateError:
    pass
else:
    raise RuntimeError("new baseline deviation accepted")
print("both runtime gates rejected")
'''
        for flags in (["-B"], ["-O", "-B"]):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable, *flags, "-c", code,
                                         str(ROOT / "run_mutants.py"), harness.SOURCE_MANIFEST_SHA256],
                                        check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout.strip(), "both runtime gates rejected")

    def test_input_hash_and_inventory_are_checked(self):
        manifest = harness.verify_source_manifest()
        fixture = next(name for name, entry in manifest["files"].items() if entry["role"] == "fixture")
        original = harness.sha256
        def tampered(path):
            return "0" * 64 if Path(path).resolve() == (harness.COPYBOT / fixture).resolve() else original(path)
        with mock.patch.object(harness, "sha256", side_effect=tampered):
            with self.assertRaisesRegex(harness.IntegrityError, "Trusted file changed"):
                harness.verify_source_manifest()
        with mock.patch.object(harness, "input_inventory", return_value=harness.input_inventory()[:-1]):
            with self.assertRaisesRegex(harness.IntegrityError, "Fixture inventory changed"):
                harness.verify_source_manifest()
        with mock.patch.object(harness, "input_inventory", return_value=harness.input_inventory() + [harness.COPYBOT / "research/desk/codex/r3/fixtures/unreviewed.json"]):
            with self.assertRaisesRegex(harness.IntegrityError, "Fixture inventory changed"):
                harness.verify_source_manifest()

    def test_only_the_exact_reviewed_baseline_difference_is_allowed(self):
        contract = json.loads((ROOT / "BASELINE_CONTRACT.json").read_text())
        allowed = contract["allowed_differences"]
        harness.verify_baseline_contract("augmented", [None] * 79, allowed)
        for changed in ({}, {**allowed, "unexpected": [{"path": ".mean_net", "expected": 1, "actual": 2}]}):
            with self.assertRaises(harness.GateError):
                harness.verify_baseline_contract("augmented", [None] * 79, changed)
        changed = copy.deepcopy(allowed)
        changed["R3_13_numeric_ledger"][0]["actual"] = "ValueError"
        with self.assertRaises(harness.GateError):
            harness.verify_baseline_contract("augmented", [None] * 79, changed)
        with self.assertRaises(harness.GateError):
            harness.verify_baseline_contract("augmented", [None] * 78, allowed)

    def test_fresh_summary_uses_current_run_and_never_overwrites_archives(self):
        archive_names = ["MUTATION_RESULTS_INITIAL.json", "MUTATION_RESULTS_AUGMENTED.json", "MUTATION_RESULTS.json"]
        before = {name: (ROOT / name).read_bytes() for name in archive_names}
        report = json.loads(before["MUTATION_RESULTS_AUGMENTED.json"])
        report["run_id"] = "unit-fresh"
        report["gate_passed"] = False
        report["rates"]["ØVRIG"] = dict(detected=0, total=15, rate=0.0)
        report["mutants"][0]["description"] = "fresh run marker"
        report["provenance"] = dict(source_manifest_sha256=harness.SOURCE_MANIFEST_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unit-fresh" / "augmented.json"
            path.parent.mkdir()
            report["report_path"] = str(path)
            harness.dump_new(path, report)
            summary = harness.finalize([report], report_dir=directory)
            self.assertEqual(summary["status"], "FAIL")
            self.assertEqual(summary["final_rates"]["ØVRIG"]["rate"], 0)
            self.assertEqual(summary["mutants"][0]["description"], "fresh run marker")
            self.assertEqual(json.loads(Path(summary["report_path"]).read_text()), summary)
            with self.assertRaises(FileExistsError):
                harness.finalize([report], report_dir=directory)
        self.assertEqual(before, {name: (ROOT / name).read_bytes() for name in archive_names})
        with self.assertRaises(harness.GateError):
            harness.finalize()

    def test_cli_failure_publishes_current_failure_and_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                sys, "argv", ["run_mutants.py", "--phase", "augmented", "--report-dir", directory]), mock.patch.object(
                harness, "run_phase", side_effect=harness.GateError("unexpected baseline")), mock.patch.object(
                sys, "stderr", new_callable=__import__("io").StringIO):
            self.assertEqual(harness.main(), 1)
            paths = list(Path(directory).glob("*/failure.json"))
            self.assertEqual(len(paths), 1)
            failure = json.loads(paths[0].read_text())
            self.assertEqual((failure["status"], failure["gate_passed"], failure["error_type"]),
                             ("FAIL", False, "GateError"))
            self.assertEqual(failure["error"], "unexpected baseline")


if __name__ == "__main__":
    unittest.main()
