"""Director order 80 P1: CB1_VOL registered as RELATED_MECHANISM with FACTORY F2. In-memory records only."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.desk.fapi76b import decision_80 as d  # noqa: E402
from research.desk.fapi76b import fapi_designs_76b as dg  # noqa: E402
from research.desk.fapi76b import triage_79 as tr  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402

NOTE = os.path.join(HERE, "research", "desk", "fapi76b", "CB1_VOL_RELATED_80.md")


class Classification(unittest.TestCase):
    def test_the_ruling_and_the_documentary_finding_are_kept_apart(self):
        self.assertEqual(d.CLASSIFICATION, "RELATED_MECHANISM")
        self.assertEqual(d.DOCUMENTARY_FINDING_79, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(tr.classify(tr.CB1_VOL_COMPARISON), tr.INSUFFICIENT)     # order 79's rule is not rewritten
        self.assertEqual(d.STATUS_CB1_VOL, "HOLD")


class Record(unittest.TestCase):
    def test_no_independent_lineage(self):
        rec = d.revised_record()
        self.assertEqual(rec["lineage"], "betting_against_beta")
        self.assertIn(rec["lineage"], dg.snapshot_counts()["lineage_map"])
        o = rec["parameters"]["values"]["order_80"]
        self.assertFalse(o["independent_lineage"])
        self.assertFalse(o["identical_mechanism_claim"])
        self.assertFalse(o["sealed_f2_results_opened"])
        self.assertFalse(o["f2_protocol_changed"])
        self.assertFalse(o["activated"])

    def test_the_correction_is_a_valid_new_entry_with_a_deviation(self):
        chain = d.update_chain()
        self.assertEqual(len(chain), 2)
        self.assertTrue(v2.chain_verify(chain))
        self.assertEqual(chain[0]["record"]["lineage"], "cross_sectional_momentum")
        self.assertEqual(chain[1]["record"]["deviations"][0]["fields"], ["lineage", "parameters"])
        self.assertEqual(chain[1]["record"]["record_id"], chain[0]["record_id"])

    def test_the_correction_needs_its_deviation(self):
        chain = []
        v2.chain_append(chain, dg.v2_record("CB1"), "t1")
        rec = dict(d.revised_record(), deviations=[])
        with self.assertRaises(v2.StatsError):
            v2.chain_append(chain, rec, "t2")

    def test_the_committed_builder_is_unchanged(self):
        self.assertEqual(dg.v2_record("CB1")["lineage"], "cross_sectional_momentum")


class OverlapAudit(unittest.TestCase):
    def test_f2_studies_count_and_ledger_flags_match_the_snapshot(self):
        ids = {a["id"] for a in d.F2_OVERLAP_AUDIT}
        self.assertTrue({"FACTORY_F2", "C1"} <= ids)
        members = set(dg.snapshot_counts()["lineage_map"]["betting_against_beta"]["hypotheses"])
        for a in d.F2_OVERLAP_AUDIT:
            self.assertEqual(a["id"] in members, a["ledger"], a["id"])
        self.assertTrue(members <= ids)


class Note(unittest.TestCase):
    def test_required_content(self):
        with open(NOTE, encoding="utf-8") as f:
            text = f.read()
        for key in ["RELATED_MECHANISM", "HOLD", "betting_against_beta", "ikke en påstand om identisk mekanisme", "INSUFFICIENT_EVIDENCE",
                    "FACTORY_F2", "C1", tr.F2_SHA256, "IKKE LÅST"]:
            self.assertIn(key, text, key)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
