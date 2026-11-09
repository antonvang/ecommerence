"""Director order 52 P0: EVALUATOR_SPEC v1.1.1 rules; frozen checksum."""
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.desk.crosscheck import claude_eval_v111 as ev  # noqa: E402
from tests.test_research_desk_eval_v11 import fixture  # noqa: E402

LOCK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "desk", "crosscheck",
                    "EVALUATOR_V1_1_1.lock")


class V111(unittest.TestCase):
    def test_frozen_checksum(self):
        with open(LOCK, encoding="utf-8") as f:
            lock = json.load(f)
        with open(ev.__file__, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), lock["sha256"])
        self.assertEqual(lock["spec_version"], ev.VERSION)

    def test_type_preserving_replay(self):
        base = {"key": "k", "hid": "H1", "family": "f", "variants": 1, "alpha": 0, "ts": 1}
        led = [base, dict(base, ts=2), dict(base, alpha=0.0, ts=3), dict(base, variants=True, ts=4)]
        L = ev.evaluate(fixture([0.0] * 40, ledger=led))["ledger"]
        self.assertEqual((L["entries"], L["idempotent_hits"]), (1, 1))
        self.assertEqual([e["reason"] for e in L["errors"]], ["key_conflict", "key_conflict"])

    def test_out_of_range_and_lock_fields(self):
        fx = fixture([0.0] * 40)
        fx["observations"][0]["ret"] = 2e6
        fx["observations"][1]["signals"]["s"]["value"] = -1e13
        fx["hypotheses"][0]["cost_bps"] = 2e6
        fx["lock"] = {"protocol_sha256": "x", "data_sha256": "y", "note": "z"}
        r = ev.evaluate(fx)
        codes = {(e["code"], e["path"]) for e in r["errors"]}
        self.assertEqual(r["status"], "INVALID_INPUT")
        self.assertTrue({("OUT_OF_RANGE", "observations[0].ret"), ("OUT_OF_RANGE", "observations[1].signals.s.value"),
                         ("OUT_OF_RANGE", "hypotheses[0].cost_bps"), ("UNKNOWN_FIELD", "lock.note"),
                         ("LOCK_MISMATCH", "lock.protocol_sha256"), ("LOCK_MISMATCH", "lock.data_sha256")} <= codes)

    def test_numeric_overflow_is_fail_closed(self):
        led = [{"key": f"k{i}", "hid": "H1", "family": "f", "variants": 1, "alpha": 1e308, "ts": 1} for i in range(2)]
        r = ev.evaluate(fixture([0.0] * 40, ledger=led))
        self.assertEqual(r["status"], "NUMERIC_ERROR")
        self.assertNotIn("hypotheses", r)
        self.assertNotIn("ledger", r)

    def test_missing_fixture_id_and_bad_json_naming(self):
        with tempfile.TemporaryDirectory() as d:
            p1, p2 = os.path.join(d, "no_id.json"), os.path.join(d, "bare_nan.json")
            fx = fixture([0.0] * 40)
            del fx["fixture_id"]
            with open(p1, "w", encoding="utf-8") as f:
                json.dump(fx, f)
            with open(p2, "w", encoding="utf-8") as f:
                f.write('{"fixture_id": "Y", "cadence_s": NaN}')
            out = os.path.join(d, "out")
            ev.main([p1, p2, "--out", out])
            with open(os.path.join(out, "no_id.json"), encoding="utf-8") as f:
                a = json.load(f)
            with open(os.path.join(out, "bare_nan.json"), encoding="utf-8") as f:
                b = json.load(f)
        self.assertEqual((a["status"], a["fixture_id"]), ("INVALID_INPUT", None))
        self.assertIn({"code": "MISSING_FIELD", "path": "fixture_id"}, a["errors"])
        self.assertEqual(b["errors"], [{"code": "BAD_JSON", "path": ""}])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
