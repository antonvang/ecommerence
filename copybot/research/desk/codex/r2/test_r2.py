"""Independent analytic oracles and artifact/restart checks for blind R2 cases."""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from ref_eval import canonical_json, evaluate
from make_r2_fixtures import build_cases, canonical


class AnalyticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {f["fixture_id"]: f for _, f in build_cases()}

    def result(self, slug):
        return evaluate(self.inputs["R2_" + slug])

    def test_alternating_closed_form_and_scale(self):
        # gamma_k=(-1)^k*(30-k)/30, L=3 => S=1/30 exactly.
        gamma = [Fraction((-1) ** k * (30 - k), 30) for k in range(4)]
        s = gamma[0] + 2 * sum((1 - Fraction(k, 4)) * gamma[k] for k in range(1, 4))
        self.assertEqual(s, Fraction(1, 30))
        for slug, scale in (("09_T30", 1), ("15_tiny", 1e-140), ("16_large", 1e140)):
            h = self.result(slug)["hypotheses"]["H"]
            self.assertEqual((h["T"], h["hac_lag"], h["status"]), (30, 3, "TESTED"))
            self.assertTrue(math.isclose(h["mean_net"], scale / 8, rel_tol=1e-13))
            self.assertTrue(math.isclose(h["se"], scale / 30, rel_tol=1e-13))
            self.assertAlmostEqual(h["t"], 3.75, places=12)
            self.assertAlmostEqual(h["p_one"], 0.00008841728520080039, places=15)

    def test_flip_closed_form_including_hac(self):
        h = self.result("02_flip_cost")["hypotheses"]["H"]
        q = Fraction(1, 1000)
        expected_s = Fraction(173, 5400) * q * q
        expected_se = math.sqrt(float(expected_s / 30))
        self.assertAlmostEqual(h["total_cost"], float(59 * q), places=15)
        self.assertAlmostEqual(h["mean_net"], float(-59 * q / 30), places=15)
        self.assertTrue(math.isclose(h["se"], expected_se, rel_tol=1e-13))
        self.assertTrue(math.isclose(h["t"], float(-59 * q / 30) / expected_se, rel_tol=1e-13))

    def test_fractional_turnover_closed_form(self):
        h = self.result("03_clip_turnover")["hypotheses"]["H"]
        # |.25-0|+|.75-.25|+|-.5-.75|+|-1+.5|+|0+1| = 7/2.
        total = Fraction(7, 2) / 1000
        self.assertEqual(h["T"], 6)
        self.assertAlmostEqual(h["total_cost"], float(total), places=15)
        self.assertAlmostEqual(h["mean_net"], float(-total / 6), places=15)

    def test_holm_bh_analytic_thresholds(self):
        cases = [
            ("17_holm_ties_all", [2.4] * 3, [True] * 3, [True] * 3),
            ("18_holm_single", [1.875], [True], [True]),
            ("19_holm_stop", [3.5, 1.8, 1.7], [True, False, False], [True] * 3),
            ("20_bh_vs_holm", [2.05, 1.88, 1.76], [False] * 3, [True] * 3)]
        for slug, z_values, holm, bh in cases:
            hypotheses = self.result(slug)["hypotheses"]
            for i, z in enumerate(z_values):
                h = hypotheses["H" + str(i + 1)]
                self.assertAlmostEqual(h["t"], z, places=12)
                self.assertAlmostEqual(h["p_one"], math.erfc(z / math.sqrt(2)) / 2, places=14)
                self.assertEqual((h["holm_reject"], h["bh_reject"]), (holm[i], bh[i]))

    def test_cancellation_and_reset_counts(self):
        h = self.result("14_fsum_assets")["hypotheses"]["H"]
        self.assertEqual((h["mean_net"], h["mean_gross"], h["status"]), (1.0, 1.0, "INSUFFICIENT"))
        h = self.result("04_resets")["hypotheses"]["H"]
        self.assertEqual((h["n_gap_bars"], h["n_empty_bars"], h["n_missing_ret"], h["n_signal_missing"]), (1, 1, 1, 1))
        self.assertAlmostEqual(h["total_cost"], 0.005, places=15)
        h = self.result("05_embargo_reset")["hypotheses"]["H"]
        self.assertEqual((h["n_embargo"], h["n_duplicates"], h["n_offgrid"], h["T"]), (4, 0, 1, 2))
        self.assertAlmostEqual(h["total_cost"], 0.003, places=15)


class ArtifactTests(unittest.TestCase):
    def test_deterministic_generator_canonical_inputs_and_size(self):
        first, second = build_cases(), build_cases()
        self.assertGreaterEqual(len(first), 20)
        self.assertEqual([canonical(f) for _, f in first], [canonical(f) for _, f in second])
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(len(manifest), len(first))
        for entry, (attack, fixture) in zip(manifest, first):
            raw = canonical(fixture)
            self.assertEqual(raw, (ROOT / "fixtures" / (fixture["fixture_id"] + ".json")).read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
            self.assertEqual(attack, entry["attack"])
            window, cadence = fixture["window"], fixture["cadence_s"]
            if isinstance(window, dict) and type(cadence) is int and cadence > 0:
                self.assertLessEqual(len(range(window["start"], window["end"], cadence)), 60)
            observations = fixture["observations"]
            if isinstance(observations, list):
                rows = [r for r in observations if isinstance(r, dict)]
                self.assertLessEqual(len({r["asset"] for r in rows}), 4)
                self.assertLessEqual(len({r["ts"] for r in rows}), 60)

    def test_all_codes_and_no_partial_results(self):
        codes = set()
        for _, fixture in build_cases():
            before = canonical(fixture)
            result = evaluate(fixture)
            self.assertEqual(before, canonical(fixture))
            if result["status"] == "INVALID_INPUT":
                self.assertEqual(set(result), {"spec_version", "fixture_id", "status", "errors"})
                pairs = [(e["code"], e["path"]) for e in result["errors"]]
                self.assertEqual(pairs, sorted(set(pairs)))
                codes.update(c for c, _ in pairs)
        self.assertEqual(codes, {"MISSING_FIELD", "UNKNOWN_FIELD", "BAD_TYPE", "BAD_TIME",
                                 "BAD_VALUE", "DUPLICATE_HID", "UNKNOWN_SIGNAL", "LOCK_MISMATCH"})

    def test_cli_two_runs_restart_and_expected_bytes(self):
        script = ROOT.parent / "ref_eval.py"
        inputs = sorted((ROOT / "fixtures").glob("*.json"))
        with tempfile.TemporaryDirectory(prefix="r2-", dir="/workspace/work") as scratch:
            out = Path(scratch)
            target = out / "R2_42_restart.json"
            target.write_bytes(b'{"fixture_id":"R2_42_restart","unfinished":')
            # A stale sibling must not be mistaken for the final output.
            stale = out / ".R2_42_restart.json.interrupted"
            stale.write_bytes(b"incomplete temporary bytes")
            for _ in range(2):
                subprocess.run([sys.executable, "-I", str(script), *map(str, inputs),
                                "--out", str(out)], check=True)
                for path in inputs:
                    actual = (out / path.name).read_bytes()
                    self.assertEqual(actual, (ROOT / "expected" / path.name).read_bytes())
                    self.assertEqual(actual, canonical_json(json.loads(actual)).encode())
                    self.assertFalse(actual.endswith(b"\n"))
            self.assertEqual(stale.read_bytes(), b"incomplete temporary bytes")


if __name__ == "__main__":
    unittest.main()
