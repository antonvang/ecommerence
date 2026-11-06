"""Director order 48 P1: migration plan v1 on a synthetic lab database."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import factory_migration as fm  # noqa: E402
from tests.test_research_factory_shadow import synthetic_lab  # noqa: E402


class Migration(unittest.TestCase):
    def test_every_experiment_gets_explicit_decisions(self):
        rep = fm.build(synthetic_lab(), git_time=lambda c: 2)          # spec committed at t=2, screening at t=3
        rows = {r["exp_id"]: r for r in rep["rows"]}
        self.assertEqual(rows["E1"]["approval_status"], "UNVERIFIED_ORIGIN")
        self.assertIn("delegated-approval", rows["E1"]["classes"])
        self.assertIn("family-approval", rows["E2"]["classes"])
        self.assertTrue(rows["E1"]["spec_locked_before_screening"])
        self.assertEqual(rows["L1"]["classes"], ["legacy"])
        self.assertTrue(all(r["results"] == "unchanged" for r in rep["rows"]))
        self.assertEqual(rep["unexplained"], ["E3"])                   # unknown edges stay visible
        for r in rep["rows"]:
            for c in r["classes"]:
                self.assertTrue(c in fm.DECISIONS or c in ("human-verdict", "UNEXPLAINED"), c)

    def test_spec_after_screening_is_not_called_a_lock(self):
        rep = fm.build(synthetic_lab(), git_time=lambda c: 99)
        rows = {r["exp_id"]: r for r in rep["rows"]}
        self.assertFalse(rows["E1"]["spec_locked_before_screening"])
        self.assertEqual(rep["spec_locked_before_screening"], 0)


if __name__ == "__main__":
    unittest.main()
