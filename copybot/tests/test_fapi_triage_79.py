"""Director order 79: the FAPI triage (research/desk/fapi76b/triage_79.py and TRIAGE_79.md). Synthetic and documentary only."""
import ast
import hashlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.desk.fapi76b import fapi_designs_76b as dg  # noqa: E402
from research.desk.fapi76b import triage_79 as tr  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402

NOTE = os.path.join(HERE, "research", "desk", "fapi76b", "TRIAGE_79.md")


def axis(relation):
    return {"axis": "x", "relation": relation, "f2": "a", "cb1_vol": "b", "source": "s"}


class Verdicts(unittest.TestCase):
    def test_the_directors_rulings(self):
        self.assertEqual(tr.DIRECTOR_VERDICTS, {"PR1": "GO_DESCRIPTIVE_ONLY", "CB1_VOL": "HOLD", "CB1_DIR": "NO_GO", "LD1": "NO_GO",
                                                "FL1": "NO_GO", "TS1": "NO_GO"})

    def test_rejections_agree_with_the_gates(self):
        for name, r in tr.REJECTED.items():
            self.assertEqual(dg.verdict(r["design"])[name], ("AFVIST", r["gates_failed"]), name)


class Classification(unittest.TestCase):
    def test_rule_fails_closed(self):
        self.assertEqual(tr.classify([]), tr.INSUFFICIENT)
        self.assertEqual(tr.classify([axis(tr.SHARED), axis(tr.UNRESOLVED)]), tr.INSUFFICIENT)
        self.assertEqual(tr.classify([axis(tr.SHARED), axis(tr.SHARED)]), tr.SAME)
        self.assertEqual(tr.classify([axis(tr.SHARED), axis(tr.DIFFERENT)]), tr.RELATED)
        self.assertEqual(tr.classify([axis(tr.DIFFERENT)]), tr.DISTINCT)

    def test_cb1_vol_is_insufficient_and_only_distinct_is_excluded(self):
        self.assertEqual(tr.classify(tr.CB1_VOL_COMPARISON), tr.INSUFFICIENT)
        self.assertEqual(tr.ruled_out(tr.CB1_VOL_COMPARISON), [tr.DISTINCT])
        self.assertEqual(tr.DIRECTOR_VERDICTS["CB1_VOL"], tr.HOLD)

    def test_every_axis_cites_a_source(self):
        for a in tr.CB1_VOL_COMPARISON:
            self.assertTrue(a["source"].strip(), a["axis"])

    def test_the_cited_f2_text_is_the_locked_one(self):
        with open(os.path.join(HERE, tr.F2_SOURCE), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), tr.F2_SHA256)


class RejectedRecords(unittest.TestCase):
    def test_valid_in_memory_records_that_cannot_be_run(self):
        chain, text = [], dg.snapshot_text()
        for name in tr.REJECTED:
            rec = tr.rejected_record(name)
            self.assertEqual(v2.validate(rec), [], name)
            self.assertEqual(v2.completeness(rec)["missing"], ["variants_tested"], name)
            self.assertTrue(v2.snapshot_matches(rec, text)["matches"], name)
            values = rec["parameters"]["values"]
            self.assertEqual(values["triage_status"], "REJECTED_NO_GO_ORDER_79")
            self.assertTrue(values["never_run"])
            self.assertFalse(values["reoptimization_allowed"])
            self.assertFalse(values["ledger_row"])
            self.assertFalse(values["independent_discovery_claim"])
            self.assertFalse(values["register_n_is_final"])
            self.assertTrue(values["reason"] and values["overlap"], name)
            v2.chain_append(chain, rec, "2026-11-09T00:00:00Z")
        self.assertTrue(v2.chain_verify(chain))

    def test_lineages_are_stated_honestly(self):
        snap = dg.snapshot_counts()
        self.assertEqual(tr.rejected_record("CB1_DIR")["lineage"], "cross_sectional_momentum")
        self.assertEqual(tr.rejected_record("FL1")["lineage"], "liquidation_cascade_reversal")
        self.assertEqual(tr.rejected_record("TS1")["lineage"], "calendar_day_of_week")
        self.assertNotIn(tr.rejected_record("LD1")["lineage"], snap["lineage_map"])

    def test_a_rejected_parameter_cannot_be_rewritten_without_a_deviation(self):
        chain = []
        rec = tr.rejected_record("FL1")
        v2.chain_append(chain, rec, "t1")
        changed = dict(rec, parameters=v2.parameters_block({"triage_status": "REVIVED"}))
        with self.assertRaises(v2.StatsError):
            v2.chain_append(chain, changed, "t2")


class Limitations(unittest.TestCase):
    def test_all_five_stay_open(self):
        self.assertEqual(sorted(tr.OPEN_LIMITATIONS), sorted(["G05_CLUSTER_DAYS", "FORWARD_OI", "DELISTING_PROVENANCE",
                                                              "BINANCE_FORMULA_UNVERIFIED", "REGISTER_N_MINIMUM"]))


class Note(unittest.TestCase):
    def setUp(self):
        with open(NOTE, encoding="utf-8") as f:
            self.text = f.read()

    def test_required_content(self):
        for key in ["IKKE LÅST", "DESCRIPTIVE_ONLY", "ln(markPrice/indexPrice)", "UNVERIFIED", "INSUFFICIENT_EVIDENCE", "HOLD",
                    tr.F2_SHA256, "19.438", "N_eff", "G05", "census/1"]:
            self.assertIn(key, self.text, key)
        for name in tr.REJECTED:
            self.assertIn(name, self.text, name)
        for key in tr.OPEN_LIMITATIONS:
            self.assertIn(key, self.text, key)

    def test_the_formula_is_never_called_confirmed(self):
        low = self.text.lower()
        for phrase in ("formlen er bekræftet", "formlen er verificeret", "verified formula"):
            self.assertNotIn(phrase, low)


class Sources(unittest.TestCase):
    def test_no_network_or_database_imports(self):
        with open(tr.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertFalse(names & {"urllib", "requests", "socket", "sqlite3", "http", "subprocess", "ssl"})


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
