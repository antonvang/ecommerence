"""Reproducible isolated mutation harness; stdlib, synthetic files, no network.

Checksums and the pre-existing numeric-error path difference are reported but
excluded from semantic mutation scores, avoiding two automatic false kills.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parent
COPYBOT = ROOT.parents[3]
SOURCE = COPYBOT / "research/desk/crosscheck/claude_eval_v111.py"
TEST_FILES = ["test_research_desk_eval_v11.py", "test_research_desk_eval_v111.py",
              "test_research_desk_factory.py"]
WORK = Path("/workspace/work")
SOURCE_MANIFEST = ROOT / "READINESS_INTEGRITY.json"
SOURCE_MANIFEST_SHA256 = '272bc9d515d8ca3e5829452bc0b10aee1a60ad75c50be9e9433cc7c7d0f15a1f'
BASELINE_CONTRACT = ROOT / "BASELINE_CONTRACT.json"
BASELINE_CONTRACT_SHA256 = '962e765786ec088fd61ebc8669fe532edbfcd660e2b0cb9e1f38dc091d107a5e'


class IntegrityError(RuntimeError):
    """A reviewed source/input trust boundary has changed."""


class GateError(RuntimeError):
    """A fresh baseline or mutation acceptance gate did not pass."""


def require(condition, message, error=IntegrityError):
    # Runtime gates must remain active with -O and PYTHONOPTIMIZE.
    if not condition:
        raise error(str(message))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def trusted_json(path, digest):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, f"Trust document changed: {Path(path).name}")
    return json.loads(raw)


def verify_source_manifest():
    manifest = trusted_json(SOURCE_MANIFEST, SOURCE_MANIFEST_SHA256)
    require(manifest.get("schema_version") == 1, "Unsupported integrity manifest schema")
    base = COPYBOT.resolve()
    for name, entry in manifest["files"].items():
        path = (COPYBOT / name).resolve()
        require(path.is_relative_to(base), f"Manifest path leaves Copybot: {name}")
        require(path.is_file(), f"Missing trusted file: {name}")
        require(sha256(path) == entry["sha256"], f"Trusted file changed: {name}")
    actual_inputs = {str(path.relative_to(COPYBOT)) for path in input_inventory()}
    declared_inputs = {name for name, entry in manifest["files"].items() if entry["role"] == "fixture"}
    require(actual_inputs == declared_inputs, "Fixture inventory changed")
    actual_expected = {str(path.relative_to(COPYBOT)) for path in (ROOT / "expected").rglob("*.json")}
    declared_expected = {name for name, entry in manifest["files"].items() if entry["role"] == "expected"}
    require(actual_expected == declared_expected, "Expected-output inventory changed")
    return manifest


def input_inventory():
    return (sorted((COPYBOT / "research/desk/synthetic_fixtures").glob("*.json"))
            + sorted((ROOT.parent / "r2/fixtures").glob("*.json"))
            + sorted((ROOT / "fixtures").glob("*.json")))


def verify_baseline_contract(phase, paths, baseline_diffs):
    contract = trusted_json(BASELINE_CONTRACT, BASELINE_CONTRACT_SHA256)
    require(phase in contract["phases"], f"Unknown baseline phase: {phase}", GateError)
    require(len(paths) == contract["phases"][phase]["fixture_count"],
            f"Baseline fixture count changed for {phase}", GateError)
    actual = {key: value for key, value in baseline_diffs.items() if value}
    require(actual == contract["allowed_differences"],
            f"Baseline differs from the reviewed exact contract: {json.dumps(actual, ensure_ascii=False)}", GateError)
    return contract


def new_run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex


def fresh_path(report_dir, run_id, filename):
    require(isinstance(run_id, str) and run_id not in ("", ".", "..")
            and Path(run_id).name == run_id, "Invalid report run identity", GateError)
    destination = Path(report_dir) / run_id
    destination.mkdir(parents=True, exist_ok=True)
    return destination / filename


def dump_new(path, obj):
    """Publish complete fresh bytes without overwriting an existing report."""
    path = Path(path)
    raw = (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".report-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # atomic and exclusive: existing reports cannot be replaced
    finally:
        os.unlink(temporary)


def current_provenance():
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=COPYBOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=COPYBOT,
                           capture_output=True, text=True, check=True).stdout.strip()
    return dict(git_commit=commit, git_worktree_dirty=bool(dirty), python=sys.version, executable=sys.executable,
                optimization=sys.flags.optimize, source_manifest_sha256=SOURCE_MANIFEST_SHA256,
                baseline_contract_sha256=BASELINE_CONTRACT_SHA256,
                harness_sha256=sha256(Path(__file__)), recorded_at_utc=datetime.now(timezone.utc).isoformat())


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                   indent=2, allow_nan=False) + "\n", encoding="utf-8")


def differences(expected, actual, path=""):
    if isinstance(expected, bool) or isinstance(actual, bool):
        equal = type(expected) is type(actual) and expected == actual
    elif type(expected) in (int, float) and type(actual) in (int, float):
        equal = (math.isfinite(expected) and math.isfinite(actual)
                 and abs(expected - actual) <= 1e-9 * max(1, abs(expected), abs(actual)))
    elif isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            return [dict(path=path + ".keys", expected=sorted(expected), actual=sorted(actual))]
        return [d for key in expected for d in differences(expected[key], actual[key], path + "." + key)]
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [dict(path=path + ".length", expected=len(expected), actual=len(actual))]
        return [d for i, (a, b) in enumerate(zip(expected, actual))
                for d in differences(a, b, path + f"[{i}]")]
    else:
        equal = type(expected) is type(actual) and expected == actual
    return [] if equal else [dict(path=path, expected=expected, actual=actual)]


def verify_frozen():
    verify_source_manifest()
    trusted_json(BASELINE_CONTRACT, BASELINE_CONTRACT_SHA256)
    lock = json.loads((SOURCE.parent / "EVALUATOR_V1_1_1.lock").read_text())
    require(sha256(SOURCE) == lock["sha256"], "Frozen evaluator checksum mismatch")
    require(sha256(SOURCE.parent / "EVALUATOR_SPEC_V1_1_1.md") == lock["spec_sha256"], "Frozen spec checksum mismatch")
    provenance = json.loads((ROOT / "REFERENCE_PROVENANCE.json").read_text())
    for name, digest in provenance["sha256"].items():
        require(sha256(ROOT / name) == digest, f"Reference provenance mismatch: {name}")
    for name, digest in json.loads((ROOT / "EXPECTED_INITIAL_SHA256.json").read_text()).items():
        require(sha256(ROOT / name) == digest, f"Initial expected checksum mismatch: {name}")
    if (ROOT / "EXPECTED_ADDED_SHA256.json").exists():
        for name, digest in json.loads((ROOT / "EXPECTED_ADDED_SHA256.json").read_text()).items():
            require(sha256(ROOT / name) == digest, f"Added expected checksum mismatch: {name}")
    return lock


def fixtures(augmented=False):
    paths = (sorted((COPYBOT / "research/desk/synthetic_fixtures").glob("*.json"))
             + sorted((ROOT.parent / "r2/fixtures").glob("*.json"))
             + sorted((ROOT / "fixtures").glob("R3_[0-9]*.json")))
    if augmented:
        paths += sorted((ROOT / "fixtures").glob("R3_A*.json"))
    return paths


def expected(path):
    group = "r1" if path.parent.name == "synthetic_fixtures" else "r2" if "r2" in path.parts else "r3"
    return json.loads((ROOT / "expected" / group / path.name).read_text())


def cli(candidate, paths):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(COPYBOT))
    with tempfile.TemporaryDirectory(prefix="r3-cli-", dir=WORK) as directory:
        process = subprocess.run([sys.executable, "-B", str(candidate), *map(str, paths),
                                  "--out", directory], env=env, capture_output=True,
                                 text=True, timeout=45)
        outputs, encoding_errors = {}, []
        for path in paths:
            target = Path(directory) / path.name
            if not target.exists():
                outputs[path.stem] = dict(_missing_output=True)
                continue
            raw = target.read_bytes()
            try:
                value = json.loads(raw)
                canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False, allow_nan=False).encode()
                if canonical != raw:
                    encoding_errors.append(path.stem)
                outputs[path.stem] = value
            except (ValueError, UnicodeDecodeError):
                outputs[path.stem] = dict(_unparseable_output=True)
                encoding_errors.append(path.stem)
        return dict(exit_code=process.returncode, stderr=process.stderr[-5000:],
                    outputs=outputs, encoding_errors=encoding_errors)


def test_worker(candidate, augmented):
    """Only copied test files and candidate are writable; tools/lab stay original."""
    with tempfile.TemporaryDirectory(prefix="r3-tests-", dir=WORK) as directory:
        sandbox = Path(directory)
        # Include the factory's mkdtemp/keypair artifacts in this cleanup scope.
        tempfile.tempdir = str(sandbox)
        for package in ("research", "research/desk", "research/desk/crosscheck"):
            dest = sandbox / package
            dest.mkdir(parents=True, exist_ok=True)
            original = COPYBOT / package
            (dest / "__init__.py").write_text("__path__.append(" + repr(str(original)) + ")\n")
        tests = sandbox / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("")
        for name in TEST_FILES:
            shutil.copyfile(COPYBOT / "tests" / name, tests / name)
        cross = sandbox / "research/desk/crosscheck"
        shutil.copyfile(candidate, cross / "claude_eval_v111.py")
        shutil.copyfile(SOURCE.parent / "EVALUATOR_V1_1_1.lock", cross / "EVALUATOR_V1_1_1.lock")
        sys.path.insert(0, str(COPYBOT))
        sys.path.insert(0, str(sandbox))
        module = importlib.import_module("research.desk.crosscheck.claude_eval_v111")
        package = importlib.import_module("research.desk.crosscheck")
        sys.modules["research.desk.crosscheck.claude_eval_v11"] = module
        setattr(package, "claude_eval_v11", module)
        stream = io.StringIO()
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName("tests." + Path(name).stem)
                                   for name in TEST_FILES)
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            result = unittest.TextTestRunner(stream=stream).run(suite)
        failed = [dict(test=test.id(), detail=detail) for test, detail in result.failures + result.errors]
        checksum = [item for item in failed if item["test"].endswith(".test_frozen_checksum")]
        behavioral = [item for item in failed if not item["test"].endswith(".test_frozen_checksum")]
        extra = []
        if augmented:
            spec = importlib.util.spec_from_file_location("augmentation_tests", ROOT / "augmentation_tests.py")
            probes = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(probes)
            extra = probes.check(module)
        return dict(tests_run=result.testsRun, checksum_failures=checksum,
                    behavioral_failures=behavioral, added_test_failures=extra,
                    captured_output=stream.getvalue()[-2000:])


def run_tests(candidate, augmented):
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(candidate)]
    if augmented:
        command.append("--augmented-worker")
    process = subprocess.run(command, capture_output=True, text=True, timeout=45,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if process.returncode:
        raise RuntimeError("Test isolation failed: " + process.stderr[-5000:])
    return json.loads(process.stdout)


def same_statuses(a, b):
    return (a.get("status") == b.get("status") == "OK"
            and {k: v["status"] for k, v in a["hypotheses"].items()}
            == {k: v["status"] for k, v in b["hypotheses"].items()})


def run_phase(phase, *, report_dir=None, run_id=None):
    require(phase in ("initial", "augmented"), f"Unknown phase: {phase}", GateError)
    report_dir = Path(report_dir) if report_dir is not None else WORK / "mutation-runs"
    run_id = run_id or new_run_id()
    WORK.mkdir(parents=True, exist_ok=True)
    augmented = phase == "augmented"
    lock = verify_frozen()
    paths = fixtures(augmented)
    baseline_tests = run_tests(SOURCE, augmented)
    require(baseline_tests["tests_run"] == 25, "Baseline test inventory changed", GateError)
    require(not baseline_tests["behavioral_failures"] and not baseline_tests["checksum_failures"], baseline_tests, GateError)
    require(not baseline_tests["added_test_failures"], baseline_tests, GateError)
    baseline = cli(SOURCE, paths)
    require(baseline["exit_code"] == 0 and not baseline["encoding_errors"], baseline, GateError)
    baseline_diffs = {path.stem: differences(expected(path), baseline["outputs"][path.stem]) for path in paths}
    verify_baseline_contract(phase, paths, baseline_diffs)
    rows = []
    manifest = json.loads((ROOT / "mutant_manifest.json").read_text())
    for mutant in manifest:
        candidate = ROOT / "mutants" / mutant["file"]
        require(sha256(candidate) == mutant["sha256"], f"Mutant checksum mismatch: {mutant['id']}")
        tests = run_tests(candidate, augmented)
        require(tests["tests_run"] == 25, f"Test inventory changed for {mutant['id']}", GateError)
        observed = cli(candidate, paths)
        evidence, inherited, silent = [], [], None
        for path in paths:
            name = path.stem
            wanted, got = expected(path), observed["outputs"][name]
            raw_diffs = differences(wanted, got)
            known = {d["path"]: d for d in baseline_diffs[name]}
            novel = [d for d in raw_diffs if d["path"] not in known
                     or differences(known[d["path"]]["actual"], d["actual"])]
            if novel:
                evidence.append(dict(fixture=name, differences=novel[:12]))
                if silent is None and observed["exit_code"] == 0 and same_statuses(wanted, got):
                    silent = dict(fixture=name, difference=novel[0],
                                  exit_code=0, fixture_status="OK", hypothesis_statuses_unchanged=True)
            elif raw_diffs:
                inherited.append(name)
        tests_detected = bool(tests["behavioral_failures"] or tests["added_test_failures"])
        fixtures_detected = bool(evidence or observed["exit_code"] or observed["encoding_errors"])
        detection = "begge" if tests_detected and fixtures_detected else "tests" if tests_detected else "fixtures" if fixtures_detected else "ingen"
        sanity = observed["outputs"].get("R3_01_holm_equality", {})
        require(sanity.get("status") == "OK", (mutant["id"], "not a normal-running mutant", sanity), GateError)
        row = {key: mutant[key] for key in ("id", "description", "category", "classification",
                                              "equivalent", "equivalence_reason", "planned_silent", "sha256")}
        row.update(detected_by=detection, detected=tests_detected or fixtures_detected,
                   tests=tests, fixture_evidence=evidence, baseline_only_differences=inherited,
                   cli_exit_code=observed["exit_code"], cli_stderr=observed["stderr"],
                   encoding_errors=observed["encoding_errors"], silent_witness=silent,
                   checksum_detected=bool(tests["checksum_failures"]))
        if mutant["equivalent"]:
            require(not row["detected"], ("Claimed equivalence falsified", row), GateError)
        rows.append(row)
        print(phase, mutant["id"], detection, "equivalent" if mutant["equivalent"] else mutant["classification"], flush=True)
    rates = {}
    for classification in ("SIKKERHEDSKRITISK", "ØVRIG"):
        selected = [row for row in rows if row["classification"] == classification and not row["equivalent"]]
        rates[classification] = dict(detected=sum(row["detected"] for row in selected),
                                     total=len(selected), rate=sum(row["detected"] for row in selected) / len(selected))
    verify_frozen()  # reject source/input changes during the run before publishing success
    report = dict(phase=phase, frozen_sha256=lock["sha256"], fixtures=len(paths),
                  run_id=run_id, provenance=current_provenance(),
                  tolerance="abs(a-b)<=1e-9*max(1,abs(a),abs(b)); exact structural/nonfloat fields",
                  baseline_tests=baseline_tests,
                  baseline_reference_differences={key: value for key, value in baseline_diffs.items() if value},
                  rates=rates, mutants=rows,
                  survivors=[row["id"] for row in rows if not row["detected"] and not row["equivalent"]],
                  silent_witnesses=sum(row["silent_witness"] is not None for row in rows))
    report["gate_passed"] = (rates["SIKKERHEDSKRITISK"]["rate"] == 1.0
                             and rates["ØVRIG"]["rate"] >= 0.9)
    target = fresh_path(report_dir, run_id, phase + ".json")
    report["report_path"] = str(target)
    dump_new(target, report)
    return report


def finalize(reports=None, *, report_dir=None, run_id=None):
    """Summarize fresh phase results; historical experiment archives stay read-only."""
    require(isinstance(reports, list) and reports, "Fresh phase reports are required; archives are read-only", GateError)
    ids = {report.get("run_id") for report in reports}
    require(len(ids) == 1 and None not in ids, "Phase reports do not share a fresh run identity", GateError)
    run_id = run_id or next(iter(ids))
    require(ids == {run_id}, "Run identity mismatch", GateError)
    for report in reports:
        require(json.loads(Path(report["report_path"]).read_text()) == report,
                "Fresh report differs from its published bytes", GateError)
        require(report["provenance"]["source_manifest_sha256"] == SOURCE_MANIFEST_SHA256,
                "Phase was produced under another trust snapshot", GateError)
    current = {report["phase"]: report for report in reports}
    require(len(current) == len(reports), "Duplicate current phase", GateError)
    final = current.get("augmented", reports[-1])
    initial_path = ROOT / "MUTATION_RESULTS_INITIAL.json"
    initial = json.loads(initial_path.read_text())
    plan = json.loads((ROOT / "SUPPLEMENT_PLAN.json").read_text())
    require(sha256(initial_path) == plan["initial_results_sha256"], "Historical first-observation hash mismatch")
    first = {row["id"]: row for row in initial["mutants"]}
    mutants = []
    for last in final["mutants"]:
        row = dict(last)
        before = first[row["id"]]
        row.update(initial_detected_by=before["detected_by"],
                   initially_survived=not before["detected"] and not before["equivalent"],
                   detected_after_addition=not before["detected"] and last["detected"],
                   initial_fixture_witnesses=[e["fixture"] for e in before["fixture_evidence"]])
        literal_tests = bool(row["tests"]["checksum_failures"]
                             or row["tests"]["behavioral_failures"]
                             or row["tests"]["added_test_failures"])
        literal_fixtures = bool(row["fixture_evidence"] or row["baseline_only_differences"]
                               or row["cli_exit_code"] or row["encoding_errors"])
        row["specified_criterion_detected"] = literal_tests or literal_fixtures
        row["specified_criterion_detected_by"] = (
            "begge" if literal_tests and literal_fixtures else "tests" if literal_tests
            else "fixtures" if literal_fixtures else "ingen")
        row["semantic_detected_by"] = row["detected_by"]
        mutants.append(row)
    results = dict(run_id=run_id, status="PASS" if final["gate_passed"] else "FAIL",
                   gate_passed=final["gate_passed"], provenance=current_provenance(),
                   fresh_phase_reports={name: dict(path=report["report_path"], sha256=sha256(report["report_path"]))
                                        for name, report in current.items()},
                   mutants=mutants, total_mutants=len(mutants),
                   non_equivalent=sum(not row["equivalent"] for row in mutants),
                   equivalent_ids=[row["id"] for row in mutants if row["equivalent"]],
                   initial_rates=initial["rates"], final_rates=final["rates"],
                   fresh_initial_rates=current.get("initial", {}).get("rates"),
                   initial_survivors=initial["survivors"], final_survivors=final["survivors"],
                   silent_witnesses=final["silent_witnesses"],
                   original_tests_per_candidate=final["baseline_tests"]["tests_run"],
                   checksum_detected_count=sum(row["checksum_detected"] for row in mutants),
                   specified_criterion_detected_count=sum(row["specified_criterion_detected"] for row in mutants),
                   score_excludes_checksum_only_and_inherited_baseline_differences=True,
                   baseline_fixture_count=final["fixtures"],
                   baseline_matching_fixtures=final["fixtures"] - len(final["baseline_reference_differences"]),
                   baseline_reference_differences=final["baseline_reference_differences"],
                   tolerance=final["tolerance"], frozen_sha256=final["frozen_sha256"],
                   initial_report_sha256=plan["initial_results_sha256"])
    target = fresh_path(report_dir or WORK / "mutation-runs", run_id, "summary.json")
    results["report_path"] = str(target)
    dump_new(target, results)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--augmented-worker", action="store_true")
    parser.add_argument("--phase", choices=("initial", "augmented", "both"), default="both")
    parser.add_argument("--report-dir", type=Path, default=WORK / "mutation-runs")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if args.worker:
        verify_frozen()
        print(json.dumps(test_worker(args.worker, args.augmented_worker), ensure_ascii=False))
        return 0
    run_id = new_run_id()
    reports = []
    try:
        phases = ("initial", "augmented") if args.phase == "both" else (args.phase,)
        for phase in phases:
            report = run_phase(phase, report_dir=args.report_dir, run_id=run_id)
            reports.append(report)
            print(json.dumps(dict(phase=phase, run_id=run_id, rates=report["rates"],
                                  survivors=report["survivors"], gate_passed=report["gate_passed"],
                                  report_path=report["report_path"])), flush=True)
        summary = finalize(reports, report_dir=args.report_dir, run_id=run_id)
        print(json.dumps(dict(status=summary["status"], run_id=run_id,
                              report_path=summary["report_path"])), flush=True)
        return 0 if summary["gate_passed"] else 1
    except Exception as error:
        failure = dict(status="FAIL", gate_passed=False, run_id=run_id,
                       recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                       error_type=type(error).__name__, error=str(error),
                       completed_phase_reports=[report["report_path"] for report in reports])
        target = fresh_path(args.report_dir, run_id, "failure.json")
        failure["report_path"] = str(target)
        dump_new(target, failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
