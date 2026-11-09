"""Director order 75 P4: the evidence report gives every hypothesis of the factory register all fields, states
MISSING_INPUT where the register is silent, maps statuses explicitly, gives no PASS without documented independent
validation, is deterministic, and writes nothing but --out. Synthetic registers only."""
import ast
import builtins
import copy
import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import evidence_report as er  # noqa: E402

FULL = {"passed": True, "validator": "ekstern replikation", "method": "uafhængig genberegning",
        "source": "research/desk/replikation.md"}
NOTE_LAB = "trials table + alpha_ledger"
NOTE_M17 = "screens are exploratory (never evidence) but still count as attempts"


def rec(rid, status="REJECTED", **kw):
    base = {"id": rid, "status": status, "lab_state": status, "mechanism_tag": "tag_a", "lineage": "lin_a",
            "spec_keys": ["costs", "hypothesis"], "spec_path": "lab/spec.py", "spec_commit": "a" * 40, "results": 1,
            "trials": 2, "datasets": 3, "dataset_hashes": 3, "alpha_spent": 0.01}
    return {**base, **kw}


def entry(hid, seq=0, source="lab", note=NOTE_LAB):
    return {"seq": seq, "hid": hid, "lineage": "lin_a", "ts": 0, "variants": 2, "alpha": 0.01, "source": source,
            "note": note, "prev": "0", "hash": "1"}


def register(records=(), offdb=(), pipeline=(), entries=None, **kw):
    entries = [entry(r["id"], i) for i, r in enumerate(records)] if entries is None else list(entries)
    by_status = {}
    for r in records:
        by_status[str(r["status"])] = by_status.get(str(r["status"]), 0) + 1
    reg = {"schema": "copybot.factory/1", "records": list(records), "offdb_studies": list(offdb),
           "hypothesis_pipeline": list(pipeline), "by_status": by_status, "gaps": {er.GAP_LEGACY: [],
                                                                                   "offdb_unknown_fields": []},
           "exploration": {"runs": 4, "candidates": 9},
           "ledger": {"entries": entries, "attempts": len(entries), "variants": 2 * len(entries), "alpha_gross": 0.0}}
    reg.update(kw)
    return reg


def rows_of(reg):
    return {r["id"]: r for r in er.build(reg)["rows"]}


def report_of(reg):
    return er.render(er.build(reg), "f" * 64)


class Fields(unittest.TestCase):
    def test_every_source_gets_every_field(self):
        off = {"id": "S1", "lineage": "x", "attempts": 2, "alpha": 0.0, "confidence": "high", "evidence": "md status",
               "note": "n", "counted_elsewhere": None, "files": ["research/studies/S1.md"]}
        pipe = {"key": "airdrop|ar_1d|m17", "type": "airdrop", "candidate": 1, "screens": 1, "measurements": 0, "alpha": 0.0}
        entries = [entry("E1", 0), entry("S1", 1, "off-database study", "inventory"),
                   entry("airdrop|ar_1d|m17", 2, "amendment 17", NOTE_M17),
                   entry("explore0", 3, "exploration lane", "explore0 window only; never evidence")]
        rows = er.build(register([rec("E1")], [off], [pipe], entries))["rows"]
        self.assertEqual([r["group"] for r in rows], ["records", "offdb_studies", "hypothesis_pipeline", "ledger_only"])
        for r in rows:
            for f in er.FIELDS:
                self.assertIn(f, r)
                self.assertTrue(str(r[f]).strip(), f"{r['id']} {f}")
            self.assertIn(r["verdict"], er.VERDICTS)

    def test_record_facts_come_from_the_register(self):
        r = rows_of(register([rec("E1")]))["E1"]
        self.assertIn("trials=2", r["undersoegt"])
        self.assertIn("resultatrækker=1", r["undersoegt"])
        self.assertIn("datasets=3", r["data_findes"])
        self.assertIn("varianter=2", r["undersoegt"])

    def test_exploratory_only_from_the_ledger_note(self):
        pipe = {"key": "k|m17", "type": "t", "candidate": 1, "screens": 2, "measurements": 0, "alpha": 0.0}
        r = rows_of(register(pipeline=[pipe], entries=[entry("k|m17", 0, "amendment 17", NOTE_M17)]))["k|m17"]
        self.assertTrue(r["validering"].startswith("EKSPLORATIV"))
        self.assertTrue(r["statistik"].startswith("NEJ"))

    def test_measurements_are_not_called_exploratory(self):
        pipe = {"key": "H1", "type": None, "candidate": 0, "screens": 0, "measurements": 1, "alpha": 0.05}
        r = rows_of(register(pipeline=[pipe], entries=[entry("H1", 0, "amendment 17", NOTE_M17)]))["H1"]
        self.assertTrue(er.is_missing(r["validering"]))
        self.assertTrue(er.is_missing(r["statistik"]))


class MissingInput(unittest.TestCase):
    def test_bare_record_is_missing_everywhere(self):
        r = rows_of(register([{"id": "E1", "status": "REJECTED"}], entries=[]))["E1"]
        for f in ("data_findes", "validering", "omkostninger", "statistik"):
            self.assertTrue(er.is_missing(r[f]), f)
        self.assertEqual(r["undersoegt"], "ikke i ledgeren")

    def test_name_says_nothing(self):
        r = rows_of(register([{"id": "E_costs_included_validated_oos", "status": "REJECTED"}], entries=[]))
        row = r["E_costs_included_validated_oos"]
        self.assertTrue(er.is_missing(row["omkostninger"]))
        self.assertTrue(er.is_missing(row["validering"]))

    def test_spec_field_is_not_a_yes_for_costs(self):
        r = rows_of(register([rec("E1")]))["E1"]
        self.assertTrue(er.is_missing(r["omkostninger"]))
        self.assertIn("costs", r["omkostninger"])

    def test_costs_only_from_a_real_bool(self):
        self.assertEqual(rows_of(register([rec("E1", costs_included=True)]))["E1"]["omkostninger"], "JA")
        self.assertEqual(rows_of(register([rec("E1", costs_included=False)]))["E1"]["omkostninger"], "NEJ")
        self.assertTrue(er.is_missing(rows_of(register([rec("E1", costs_included="yes")]))["E1"]["omkostninger"]))

    def test_evidence_text_about_costs_stays_missing(self):
        off = {"id": "S1", "evidence": "6 cost scenarios", "attempts": 1}
        r = rows_of(register(offdb=[off], entries=[]))["S1"]
        self.assertTrue(er.is_missing(r["omkostninger"]))

    def test_gap_is_reported_as_missing_data(self):
        reg = register([rec("L1", trials=0, alpha_spent=0.0)])
        reg["gaps"][er.GAP_LEGACY] = ["L1"]
        r = rows_of(reg)["L1"]
        self.assertIn("tested_without_trials_or_alpha", r["data_mangler"])
        self.assertTrue(r["statistik"].startswith("NEJ"))

    def test_absent_top_level_keys_are_flagged(self):
        view = er.build({"schema": "x"})
        for name in ("ledger", "records", "offdb_studies", "hypothesis_pipeline", "by_status", "gaps"):
            self.assertTrue(any(name in f and er.MISSING in f for f in view["flags"]), name)
        self.assertEqual(view["rows"], [])


class StatusMapping(unittest.TestCase):
    EXPECTED = {"REJECTED": "FAIL", "INCONCLUSIVE": "INCONCLUSIVE", "TESTED": "INCONCLUSIVE", "PROPOSED": "BLOCKED",
                "APPROVED": "BLOCKED", "FROZEN": "BLOCKED", "CLOSED": "INCONCLUSIVE", "EXTERNAL": "INCONCLUSIVE",
                "UNKNOWN": "INCONCLUSIVE"}

    def test_each_status(self):
        for st, verdict in self.EXPECTED.items():
            self.assertEqual(rows_of(register([rec("E1", st)]))["E1"]["verdict"], verdict, st)

    def test_factory_vocabulary_is_covered(self):
        from research.tools import factory
        for st in factory.STATUSES:
            self.assertIn(st, er.STATUS_MAP, st)

    def test_unknown_status_is_inconclusive_with_reason(self):
        for st in ("SOMETHING_NEW", "PASS", "pass", "VALIDATED "):
            r = rows_of(register([rec("E1", st)]))["E1"]
            self.assertEqual(r["verdict"], "INCONCLUSIVE", st)
            self.assertIn("ukendt status", r["hvorfor"])

    def test_non_string_status_is_inconclusive(self):
        for st in (None, 1, True, ["VALIDATED"]):
            r = rows_of(register([{"id": "E1", "status": st}], entries=[]))["E1"]
            self.assertEqual(r["verdict"], "INCONCLUSIVE")

    def test_rows_without_a_string_id_are_flagged_and_left_out(self):
        view = er.build(register([{"id": ["E1"], "status": "REJECTED"}, {"id": None, "status": "REJECTED"}, rec("E2")],
                                 entries=[]))
        self.assertEqual([r["id"] for r in view["rows"]], ["E2"])
        self.assertTrue(any("2 rækker uden gyldigt id" in f for f in view["flags"]))

    def test_rows_without_status(self):
        off = {"id": "S1", "evidence": "md status"}
        pipe = {"key": "k", "candidate": 1, "screens": 1, "measurements": 0}
        rows = rows_of(register(offdb=[off], pipeline=[pipe], entries=[]))
        for rid in ("S1", "k"):
            self.assertEqual(rows[rid]["verdict"], "INCONCLUSIVE")
            self.assertIn("intet statusfelt", rows[rid]["hvorfor"])

    def test_mapping_is_printed(self):
        text = report_of(register([rec("E1")]))
        self.assertIn("## Statusmapping", text)
        for st in er.STATUS_MAP:
            self.assertIn(f"| {st} |", text)

    def test_reason_says_rejection_cause_is_not_in_the_register(self):
        self.assertIn("årsagen", rows_of(register([rec("E1")]))["E1"]["hvorfor"])


class NoPassWithoutValidation(unittest.TestCase):
    def test_validated_without_documentation_is_not_pass(self):
        r = rows_of(register([rec("E1", "VALIDATED")]))["E1"]
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("ingen dokumenteret uafhængig validering", r["hvorfor"])

    def test_partial_documentation_is_not_pass(self):
        for bad in ({**FULL, "passed": False}, {**FULL, "passed": "true"}, {**FULL, "validator": ""},
                    {**FULL, "source": "   "}, {k: v for k, v in FULL.items() if k != "method"}, {}, "ja", True):
            r = rows_of(register([rec("E1", "VALIDATED", independent_validation=bad)]))["E1"]
            self.assertEqual(r["verdict"], "INCONCLUSIVE", repr(bad))

    def test_documented_validation_gives_pass(self):
        r = rows_of(register([rec("E1", "VALIDATED", independent_validation=FULL)]))["E1"]
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(r["validering"].startswith("UAFHAENGIGT_VALIDERET"))

    def test_documentation_without_validated_status_is_not_pass(self):
        for st in ("REJECTED", "INCONCLUSIVE", "PROPOSED", "CLOSED", "EXTERNAL", "TESTED"):
            r = rows_of(register([rec("E1", st, independent_validation=FULL)]))["E1"]
            self.assertNotEqual(r["verdict"], "PASS", st)

    def test_text_cannot_give_pass(self):
        off = {"id": "S1", "evidence": "md 'PASS p=0.00001' VALIDATED", "status_note": "PASS"}
        pipe = {"key": "PASS", "candidate": 1, "screens": 1, "measurements": 1}
        rows = rows_of(register(offdb=[off], pipeline=[pipe], entries=[]))
        self.assertTrue(all(r["verdict"] != "PASS" for r in rows.values()))

    def test_offdb_and_pipeline_with_status_validated_need_documentation(self):
        off = {"id": "S1", "status": "VALIDATED"}
        pipe = {"key": "k", "status": "VALIDATED"}
        rows = rows_of(register(offdb=[off], pipeline=[pipe], entries=[]))
        self.assertTrue(all(r["verdict"] == "INCONCLUSIVE" for r in rows.values()))

    def test_no_pass_across_every_status(self):
        recs = [rec(f"E{i}", st) for i, st in enumerate(list(er.STATUS_MAP) + ["X", "PASS"])]
        self.assertFalse([r for r in er.build(register(recs))["rows"] if r["verdict"] == "PASS"])

    def test_known_table_never_passes(self):
        self.assertTrue(all(k["verdict"] != "PASS" for k in er.KNOWN))

    def test_report_says_no_validated(self):
        text = report_of(register([rec("E1"), rec("E2", "INCONCLUSIVE")]))
        self.assertIn("Lab'et har ingen VALIDATED hypoteser", text)
        self.assertIn("Ingen automatisk promovering", text)
        self.assertIn("PASS i denne rapport: 0", text)

    def test_report_does_not_claim_none_when_there_are_some(self):
        text = report_of(register([rec("E1", "VALIDATED")]))
        self.assertNotIn("Lab'et har ingen VALIDATED", text)
        self.assertIn("1 af 1 lab-eksperimenter har status VALIDATED, og 0 af dem", text)


class KnownFacts(unittest.TestCase):
    def test_n4_and_lq1_are_extra_rows(self):
        extra = {r["id"]: r for r in er.build(register([rec("E1")]))["known_extra"]}
        self.assertEqual(extra["N4"]["status"], "HOLDOUT_ACCESS_CONTAMINATED")
        self.assertEqual(extra["N4"]["verdict"], "BLOCKED")
        self.assertIn("SECURITY_DEVIATION_N4", extra["N4"]["hvorfor"])
        self.assertEqual(extra["LQ1"]["verdict"], "BLOCKED")
        self.assertIn("LIQREC1", extra["LQ1"]["hvorfor"])
        for r in extra.values():
            for f in er.FIELDS:
                self.assertIn(f, r)

    def test_pm_lp_overrides_the_register_row_by_exact_id(self):
        r = rows_of(register([rec("X01_pm_lp_v1", "EXTERNAL")]))["X01_pm_lp_v1"]
        self.assertEqual(r["status"], "PASS_UNREACHABLE / PENDING_FORMAL_CLOSE")
        self.assertEqual(r["status_register"], "EXTERNAL")
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("PM_LP_D1_STATUS_72", r["hvorfor"])
        self.assertIn("trials=2", r["undersoegt"])

    def test_similar_name_does_not_match(self):
        r = rows_of(register([rec("X02_pm_lp_v1", "EXTERNAL")]))["X02_pm_lp_v1"]
        self.assertEqual(r["status"], "EXTERNAL")

    def test_known_table_is_dated_and_sourced(self):
        text = report_of(register())
        for k in er.KNOWN:
            self.assertRegex(k["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn(k["source"], text)


class Safety(unittest.TestCase):
    def test_holdout_text_is_left_out(self):
        off = {"id": "S1", "evidence": "holdout sharpe 3.1", "counted_elsewhere": "2024 window"}
        r = rows_of(register(offdb=[off], entries=[]))["S1"]
        self.assertNotIn("sharpe", r["undersoegt"])
        self.assertNotIn("2024 window", r["undersoegt"])
        self.assertIn("udeladt", r["undersoegt"])

    def test_urls_are_removed(self):
        self.assertNotIn("example.org", er.text("se https://example.org/x"))

    def test_table_cells_cannot_break_the_table(self):
        off = {"id": "S1", "evidence": "a | b\nc"}
        text = report_of(register(offdb=[off], entries=[]))
        line = next(ln for ln in text.splitlines() if ln.startswith("| S1 "))
        self.assertIn("a \\| b c", line)

    def test_long_text_is_capped(self):
        self.assertLessEqual(len(er.text("x" * 5000)), er.MAX_TEXT)

    def test_only_stdlib_imports(self):
        with open(er.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertEqual(names, {"argparse", "collections", "hashlib", "json", "os", "re", "sys"})


class Determinism(unittest.TestCase):
    def setUp(self):
        self.reg = register([rec("B"), rec("A", "PROPOSED")], [{"id": "S2", "evidence": "e"}, {"id": "S1", "evidence": "f"}],
                            [{"key": "z", "screens": 1}, {"key": "y", "screens": 2}],
                            [entry("B", 0), entry("A", 1), entry("explore0", 2, "exploration lane", "never evidence")])

    def test_same_input_same_output(self):
        self.assertEqual(report_of(copy.deepcopy(self.reg)), report_of(copy.deepcopy(self.reg)))

    def test_input_order_does_not_matter(self):
        other = copy.deepcopy(self.reg)
        rnd = random.Random(7)
        for key in ("records", "offdb_studies", "hypothesis_pipeline"):
            rnd.shuffle(other[key])
        self.assertEqual(report_of(self.reg), report_of(other))

    def test_same_bytes_from_two_paths(self):
        outs = []
        for _ in range(2):
            d = tempfile.mkdtemp()
            p = os.path.join(d, "registry.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.reg, f)
            out = os.path.join(d, "r.md")
            self.assertEqual(er.main(["--registry", p, "--out", out]), 0)
            with open(out, "rb") as f:
                outs.append(f.read())
        self.assertEqual(outs[0], outs[1])
        self.assertNotIn(b"/tmp", outs[0])


class WritesOnlyOut(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.reg_path = os.path.join(self.dir, "registry.json")
        with open(self.reg_path, "w", encoding="utf-8") as f:
            json.dump(register([rec("E1")]), f)
        self.out = os.path.join(self.dir, "ud", "rapport.md")
        os.mkdir(os.path.dirname(self.out))

    def tree(self):
        return sorted(os.path.join(r, n) for r, _, fs in os.walk(self.dir) for n in fs)

    def test_only_out_is_opened_for_writing(self):
        with open(self.reg_path, "rb") as f:
            before = f.read()
        real, writes, reads = builtins.open, [], []

        def spy(file, mode="r", *a, **k):
            (writes if set(mode) & set("wax+") else reads).append(str(file))
            return real(file, mode, *a, **k)

        builtins.open = spy
        try:
            code = er.main(["--registry", self.reg_path, "--out", self.out])
        finally:
            builtins.open = real
        self.assertEqual(code, 0)
        self.assertEqual(writes, [self.out])
        self.assertEqual(reads, [self.reg_path])
        self.assertEqual(self.tree(), sorted([self.reg_path, self.out]))
        with open(self.reg_path, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_out_is_required(self):
        with self.assertRaises(SystemExit):
            er.main(["--registry", self.reg_path])

    def test_refuses_any_other_input_file(self):
        other = os.path.join(self.dir, "lab.db")
        with open(other, "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertEqual(er.main(["--registry", other, "--out", self.out]), 2)
        self.assertFalse(os.path.exists(self.out))

    def test_refuses_to_overwrite_the_register(self):
        with open(self.reg_path, "rb") as f:
            before = f.read()
        self.assertEqual(er.main(["--registry", self.reg_path, "--out", self.reg_path]), 2)
        with open(self.reg_path, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_malformed_register_writes_nothing(self):
        with open(self.reg_path, "w", encoding="utf-8") as f:
            f.write("{ikke json")
        self.assertEqual(er.main(["--registry", self.reg_path, "--out", self.out]), 2)
        self.assertFalse(os.path.exists(self.out))

    def test_register_that_is_not_an_object_writes_nothing(self):
        with open(self.reg_path, "w", encoding="utf-8") as f:
            f.write("[]")
        self.assertEqual(er.main(["--registry", self.reg_path, "--out", self.out]), 2)
        self.assertFalse(os.path.exists(self.out))


class Consistency(unittest.TestCase):
    def test_wrong_ledger_total_is_flagged_not_fixed(self):
        reg = register([rec("E1")])
        reg["ledger"]["attempts"] = 99
        view = er.build(reg)
        self.assertTrue(any("99" in f for f in view["flags"]))
        self.assertEqual(view["attempts"], 99)

    def test_wrong_by_status_is_flagged(self):
        reg = register([rec("E1")])
        reg["by_status"] = {"REJECTED": 5}
        self.assertTrue(any("by_status" in f for f in er.build(reg)["flags"]))

    def test_clean_register_has_no_flags(self):
        self.assertEqual(er.build(register([rec("E1")]))["flags"], [])

    def test_missing_counts_are_in_the_report(self):
        text = report_of(register([{"id": "E1", "status": "REJECTED"}], entries=[]))
        self.assertIn(f"## Hyppighed af {er.MISSING}", text)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
