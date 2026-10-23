"""research/LINUX_DRIFT.md 2026-10-23: `lab research-memory` gives one learning record per decided hypothesis."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypogen, memory  # noqa: E402
from lab.db import DB  # noqa: E402

FILES = [{"file": "BTCUSDT-1h-2022-01.zip", "sha256": "aa"}, {"file": "XUSDT-1h-2022-01.zip", "sha256": "bb"}]


class Memory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labmem")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        ev = lambda k, p: self.db.event(k, "system:test", None, p)  # noqa: E731
        ev("research.measurement", {"hypothesis": "x|sar_1d|m17", "verdict": "REJECTED", "alpha": 0.025,
                                    "reason": "validation3: one-sided p 0.4 >= 0.025", "draft_sha256": "ab" * 32,
                                    "phases": {"train3": {"n": 30, "mean": -0.05, "p": 0.01, "files": FILES},
                                               "validation3": {"n": 9, "mean": 0.01, "p": 0.4, "files": FILES[:1]}}})
        ev("research.measurement", {"hypothesis": "H9", "verdict": "PASS", "alpha": 0.05, "reason": "p < alpha",
                                    "decisional_for_trading": False,
                                    "validation": {"n": 26, "mean_Y": -0.003, "sign_flip_p": 1e-5,
                                                   "split": "validation3"}})
        ev(hypogen.EV_SCREEN, {"key": "a|ar_1d|m17", "verdict": "UNTESTABLE", "n": 3, "excluded": {"missing price": 9}})
        ev(hypogen.EV_SCREEN, {"key": "b|sar_7d|m17", "verdict": "SCREEN_FAIL", "n": 40, "mean": -0.1, "p": 0.001,
                               "checks": {"p <= 0.005": True, "same sign": False}})
        self.db.append("results", exp_id="E_v_p1", version=1, ts=1, label="EXPLORATORY", verdict="PASS (screen): ok",
                       metrics={"template": "v", "protocol_version": 1, "failed": []}, evidence={}, supersedes=None)
        self.db.append("transitions", exp_id="E_v_p1", ts=2, from_state="SCREEN_PASSED", to_state="REJECTED",
                       actor="human:t", reason="user decision", evidence={})
        self.db.append("results", exp_id="L01_x", version=1, ts=1, label="LEGACY", verdict="FAIL: costs",
                       metrics={}, evidence={}, supersedes=None)

    def tearDown(self):
        self.db.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def recs(self):
        lines = []
        path = os.path.join(self.tmp, "m.jsonl")
        self.assertEqual(memory.main(self.db.path, out=lines.append, json_path=path), 0)
        with open(path) as f:
            return {r["id"]: r for r in map(json.loads, f)}, "\n".join(lines)

    def test_a_locked_measurement_keeps_its_lock_lineage_result_and_retest_rule(self):
        r, text = self.recs()
        m = r["x|sar_1d|m17"]
        self.assertEqual(m["lock_sha256"], "ab" * 32)
        self.assertEqual(m["phases"]["train3"]["files"], 2)
        self.assertEqual(len(m["phases"]["train3"]["files_sha256"]), 64)
        self.assertNotEqual(m["phases"]["train3"]["files_sha256"], m["phases"]["validation3"]["files_sha256"])
        self.assertEqual(m["retest"], memory.RETEST["measurement"])
        self.assertEqual(r["H9"]["phases"]["validation3"], {"n": 26, "mean": -0.003, "p": 1e-5, "files": None,
                                                            "files_sha256": None})
        self.assertIn("locked measurements 2: PASS 1, REJECTED 1", text)
        self.assertIn("H9: PASS (p < alpha) alpha 0.05 [not decisional for trading]", text)

    def test_a_later_human_decision_overrides_a_recorded_pass(self):
        r, text = self.recs()
        self.assertEqual(r["E_v_p1"]["state"], "REJECTED")
        self.assertIn("catalogue 1: REJECTED 1", text)
        self.assertEqual(r["L01_x"]["source"], "legacy")

    def test_screens_carry_their_cause_and_fixed_rules(self):
        r, _ = self.recs()
        self.assertEqual(r["a|ar_1d|m17"]["retest"], memory.RETEST["UNTESTABLE"])
        self.assertEqual(r["b|sar_7d|m17"]["failed"], ["same sign"])
        self.assertEqual(r["b|sar_7d|m17"]["retest"], memory.RETEST["SCREEN_FAIL"])

    def test_it_writes_nothing_to_the_registry(self):
        before = self.db.one("SELECT COUNT(*) FROM events")[0]
        self.recs()
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events")[0], before)


if __name__ == "__main__":
    unittest.main()
