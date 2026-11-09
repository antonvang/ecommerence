"""The EVIDENS section of the paper dashboard: synthetic registers only, plus the failure path."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "research", "tools")]

import paper_evidence as pe  # noqa: E402


def register():
    return {"schema": "copybot.factory/1", "records": [
        {"id": "R1", "status": "REJECTED", "name": "<script>x</script>"},
        {"id": "R2", "status": "VALIDATED"},
        {"id": "R3", "status": "PROPOSED"}],
        "offdb_studies": [], "hypothesis_pipeline": [], "gaps": {}, "lineage_members": {},
        "ledger": {"attempts": 0, "variants": 0, "alpha_gross": 0.0, "entries": [], "lineages": {}}}


class Section(unittest.TestCase):
    def render(self, reg):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "registry.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(reg, f)
            return pe.section(p)

    def test_counts_and_order(self):
        _, doc = self.render(register())
        self.assertIn('id="evidens"', doc)
        self.assertLess(doc.index(">R3<"), doc.index(">R1<"))              # BLOCKED before FAIL

    def test_validated_without_documentation_is_never_pass(self):
        _, doc = self.render(register())
        self.assertIn('0 uafhængigt validerede', doc)
        self.assertIn('<b class="ev-p">0</b>', doc)
        self.assertIn("intet promoveres", doc)

    def test_markup_in_the_register_is_escaped(self):
        reg = register()
        reg["records"][0]["id"] = "<b>x</b>"
        _, doc = self.render(reg)
        self.assertNotIn("<b>x</b>", doc)

    def test_no_script_or_external_resource(self):
        css, doc = self.render(register())
        self.assertNotIn("<script", doc)
        self.assertNotIn("http", css + doc)

    def test_unreadable_register_gives_a_notice(self):
        css, doc = pe.section("/nonexistent/registry.json")
        self.assertIn("kan ikke læses", doc)
        self.assertTrue(css)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
