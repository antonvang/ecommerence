"""Director order 74 P2: the register snapshot procedure. Synthetic registers; the tracked aggregate register is read only
to prove reproducibility and is not changed."""
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
import register_snapshot as snap  # noqa: E402


def entry(seq, lineage, variants, hid="H"):
    return {"seq": seq, "hid": f"{hid}{seq}", "lineage": lineage, "variants": variants, "alpha": 0.0, "note": "",
            "prev": "0", "source": "s", "ts": 1, "hash": f"h{seq}"}


def register():
    es = [entry(0, "a", 10), entry(1, "a", 5), entry(2, "b", 1)]
    return {"ledger": {"alpha_gross": 0.5, "attempts": 3, "variants": 16, "entries": es,
                       "lineages": {"a": {}, "b": {}}}}


def raw(reg):
    return json.dumps(reg).encode()


class Build(unittest.TestCase):
    def test_counts_and_lineage_map(self):
        s = snap.build(raw(register()))
        self.assertEqual(s["counts"], {"attempts": 3, "variants": 16, "lineages": 2, "hypotheses": 3})
        self.assertEqual(s["lineage_map"]["a"]["variants"], 15)
        self.assertEqual(s["lineage_map"]["a"]["hypotheses"], ["H0", "H1"])

    def test_identical_input_gives_identical_bytes(self):
        self.assertEqual(snap.render(snap.build(raw(register()))), snap.render(snap.build(raw(register()))))

    def test_no_timestamp_in_the_snapshot(self):
        self.assertNotIn("generated", snap.render(snap.build(raw(register()))))

    def test_any_change_of_an_entry_changes_the_digest(self):
        reg = register()
        reg["ledger"]["entries"][0]["hash"] = "other"
        self.assertNotEqual(snap.build(raw(reg))["entries_sha256"], snap.build(raw(register()))["entries_sha256"])

    def test_n_is_a_reference_and_n_eff_stays_missing(self):
        s = snap.build(raw(register()))
        self.assertEqual(s["n"]["conservative_reference"], 16)
        self.assertEqual(s["n"]["n_eff"], snap.MISSING)
        self.assertEqual((s["dsr"], s["pbo"]), (snap.MISSING, snap.MISSING))
        self.assertEqual(set(s["n"]["diagnostic_expected_max_z"]), {"lineages", "attempts", "variants"})

    def test_totals_that_disagree_with_the_entries_are_refused(self):
        reg = register()
        reg["ledger"]["variants"] = 15
        with self.assertRaises(ValueError):
            snap.build(raw(reg))

    def test_holes_and_bad_entries_are_refused(self):
        for edit in (lambda r: r["ledger"]["entries"].pop(1),
                     lambda r: r["ledger"]["entries"][0].update(variants=0),
                     lambda r: r["ledger"]["entries"][0].update(lineage="")):
            reg = copy.deepcopy(register())
            edit(reg)
            with self.assertRaises(ValueError):
                snap.build(raw(reg))


class RealRegister(unittest.TestCase):
    def test_aggregates_and_committed_snapshot(self):
        with open(snap.REGISTER, "rb") as f:
            data = f.read()
        s = snap.build(data)
        self.assertEqual((s["counts"]["attempts"], s["counts"]["variants"], s["counts"]["lineages"]), (206, 19438, 43))
        self.assertEqual(s["n"]["diagnostic_expected_max_z"]["variants"], 4.0202)
        committed = os.path.join(HERE, "research", "desk", "register_snapshots", "SNAPSHOT_v1.json")
        with open(committed, encoding="utf-8") as f:
            frozen = json.load(f)
        self.assertEqual(frozen["source"]["sha256"], hashlib.sha256(data).hexdigest(), "the register has moved: "
                         "take a new snapshot under a new name, never edit this one")
        self.assertEqual(frozen, json.loads(snap.render(s)))

    def test_cli_writes_only_where_told(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "s.json")
            snap.main(["--out", out])
            self.assertTrue(os.path.getsize(out) > 0)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
