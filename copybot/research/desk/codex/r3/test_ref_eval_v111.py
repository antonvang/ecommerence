"""Spec-only tests written before opening Claude's frozen evaluator."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def local(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ref = local("ref_eval")
seeds = local("make_r3_fixtures")


class Spec111Tests(unittest.TestCase):
    def test_replay_is_type_preserving(self):
        f = seeds.base("unit")
        r = dict(key="k", hid="H", family="F", variants=1, alpha=0, ts=1000)
        f["ledger_requests"] = [r, dict(r, alpha=0.0), dict(r, variants=True),
                                dict(r, variants=1.0), dict(r, ts=1001)]
        ledger = ref.evaluate(f)["ledger"]
        self.assertEqual((ledger["entries"], ledger["idempotent_hits"]), (1, 1))
        self.assertEqual([e["reason"] for e in ledger["errors"]], ["key_conflict"] * 3)

    def test_lock_unknown_type_and_mismatch_accumulate(self):
        f = seeds.base("unit")
        f["lock"] = dict(extra=1, protocol_sha256=3)
        f["alpha"] = 1
        errors = ref.evaluate(f)["errors"]
        self.assertIn(dict(code="UNKNOWN_FIELD", path="lock.extra"), errors)
        self.assertIn(dict(code="LOCK_MISMATCH", path="lock.protocol_sha256"), errors)
        self.assertIn(dict(code="LOCK_MISMATCH", path="lock.data_sha256"), errors)
        f["lock"] = None
        self.assertIn(dict(code="BAD_TYPE", path="lock"), ref.evaluate(f)["errors"])

    def test_range_inclusive_and_over_boundaries(self):
        cases = {name: raw for name, _, raw in seeds.build_cases()}
        self.assertEqual(ref.evaluate(json.loads(cases["R3_05_range_exact"]))["status"], "OK")
        for name in ("R3_06_range_ret", "R3_07_range_funding", "R3_08_range_value", "R3_09_range_cost_bps"):
            self.assertEqual(ref.evaluate(json.loads(cases[name]))["errors"][0]["code"], "OUT_OF_RANGE")

    def test_numeric_overflow_no_partial_output(self):
        f = json.loads(dict((name, raw) for name, _, raw in seeds.build_cases())["R3_13_numeric_ledger"])
        result = ref.evaluate(f)
        self.assertEqual(set(result), {"spec_version", "fixture_id", "status", "errors"})
        self.assertEqual(result["status"], "NUMERIC_ERROR")
        self.assertEqual(result["errors"], [dict(code="NUMERIC_OVERFLOW", path="")])

    def test_underflow_and_exact_holm_threshold(self):
        cases = {name: raw for name, _, raw in seeds.build_cases()}
        h = ref.evaluate(json.loads(cases["R3_14_underflow"]))["hypotheses"]["H"]
        self.assertEqual((h["status"], h["hac_lag"]), ("INSUFFICIENT", 3))
        h = ref.evaluate(json.loads(cases["R3_01_holm_equality"]))["hypotheses"]["H"]
        self.assertEqual((h["t"], h["p_one"], h["holm_reject"]), (0.0, 0.5, True))

    def test_strict_json(self):
        for raw in ('NaN', 'Infinity', '-Infinity', '{"x":NaN}', '{'):
            with self.assertRaises(ValueError):
                ref.parse_fixture(raw)
        self.assertEqual(ref.parse_fixture('{"x":"NaN"}'), {"x": "NaN"})

    def test_analytic_hac(self):
        h = ref.hac_statistics([1.125, -0.875] * 15)
        self.assertAlmostEqual(h["se"], 1 / 30, places=14)
        self.assertAlmostEqual(h["t"], 3.75, places=12)


if __name__ == "__main__":
    unittest.main()
