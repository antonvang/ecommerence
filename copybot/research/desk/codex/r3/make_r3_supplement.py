"""Add new cases only after preserving the observed initial survivors."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def load_seeds():
    spec = importlib.util.spec_from_file_location("seeds", ROOT / "make_r3_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    initial_raw = (ROOT / "MUTATION_RESULTS_INITIAL.json").read_bytes()
    initial = json.loads(initial_raw)
    assert initial["survivors"] == ["M23", "M27", "M41", "M45"]
    seeds = load_seeds()
    cases = []
    for name, target in (("R3_A01_holm_duplicate_denominator", "M23"),
                         ("R3_A02_bh_level", "M27")):
        fixture = seeds.base(name)
        for i, row in enumerate(fixture["observations"]):
            row["ret"] = 0.25 * ((-1) ** i + 1.875 / 30)
        if target == "M23":
            fixture["hypotheses"].append(dict(fixture["hypotheses"][0], hid="COPY", cost_bps=1))
        else:
            fixture.update(alpha=0.01, q_fdr=0.05)
        cases.append((fixture, target))
    fixture = seeds.base("R3_A03_extreme_equality", 2)
    for row, value in zip(fixture["observations"], (0.5, -0.5)):
        row["ret"] = value
    cases.append((fixture, "M45"))
    plan = dict(initial_results_sha256=hashlib.sha256(initial_raw).hexdigest(),
                initial_survivors=initial["survivors"],
                fixtures=[dict(fixture_id=f["fixture_id"], target=target) for f, target in cases],
                added_test=dict(target="M41", name="atomic_interruption_preserves_previous_file"),
                critical_survivors_initial=[])
    plan_path = ROOT / "SUPPLEMENT_PLAN.json"
    if plan_path.exists():
        assert json.loads(plan_path.read_text()) == plan
    else:
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    inputs = []
    for fixture, target in cases:
        path = ROOT / "fixtures" / (fixture["fixture_id"] + ".json")
        raw = seeds.encode(fixture)
        if path.exists():
            assert path.read_bytes() == raw
        else:
            path.write_bytes(raw)
        inputs.append(path)
    manifest = {}
    with tempfile.TemporaryDirectory(prefix="r3-added-", dir="/workspace/work") as directory:
        subprocess.run([sys.executable, "-B", str(ROOT / "ref_eval.py"),
                        *map(str, inputs), "--out", directory], check=True)
        for path in inputs:
            target = ROOT / "expected/r3" / path.name
            raw = (Path(directory) / path.name).read_bytes()
            if target.exists():
                assert target.read_bytes() == raw
            else:
                target.write_bytes(raw)
            manifest[str(target.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
    (ROOT / "EXPECTED_ADDED_SHA256.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
