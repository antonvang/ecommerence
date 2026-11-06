"""Director order 47 P3: factory shadow run (synthetic; pipeline replay on a synthetic lab database)."""
import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import factory as fa  # noqa: E402
from research.tools import factory_shadow as fs  # noqa: E402


class Suite(unittest.TestCase):
    def test_no_unauthorized_allow_and_no_false_block(self):
        cases = fs.suite()
        self.assertGreaterEqual(len(cases), 30)
        bad = [c for c in cases if c["unauthorized_allow"] or c["false_block"]]
        self.assertEqual(bad, [])


class Gate(unittest.TestCase):
    def test_delegation_markers(self):
        self.assertTrue(fa.delegated({"reason": "Approved by Claude (AI assistant) on behalf of the user"}))
        self.assertTrue(fa.delegated({"reason": "User instruction 2026-10-17: approve x"}))
        self.assertFalse(fa.delegated({"reason": "owner approves in person"}))

    def test_gate_changes_nothing(self):
        led, reg = fs.fresh()
        reg.propose("H", fs.prereg(), fs.NOW)
        before = json.dumps(reg.recs["H"], sort_keys=True, default=str)
        self.assertEqual(reg.gate("H", "APPROVED", fs.NOW + 1, fs.OWNER)[0], "ALLOW")
        self.assertEqual(json.dumps(reg.recs["H"], sort_keys=True, default=str), before)
        self.assertEqual(reg.log, [])

    def test_idempotent_charge(self):
        led = fa.Ledger()
        a = led.charge("H", "L", 1, 1, 0.01, "s", key="k")
        b = led.charge("H", "L", 1, 1, 0.01, "s", key="k")
        self.assertIs(a, b)
        led.charge("H", "L", 2, 1, 0.01, "s", key="k2")
        self.assertEqual(len(led.entries), 2)
        self.assertTrue(led.verify())


def synthetic_lab():
    con = sqlite3.connect(":memory:")
    con.executescript("""
    CREATE TABLE transitions(id INTEGER PRIMARY KEY, exp_id, ts, from_state, to_state, actor, reason, evidence);
    CREATE TABLE experiments(id INTEGER PRIMARY KEY, exp_id, version, spec_json, spec_commit);
    CREATE TABLE events(id INTEGER PRIMARY KEY, kind, actor, payload);
    CREATE TABLE datasets(id INTEGER PRIMARY KEY, exp_id, ts);
    CREATE TABLE trials(id INTEGER PRIMARY KEY, exp_id);
    CREATE TABLE alpha_ledger(id INTEGER PRIMARY KEY, exp_id, alpha);
    """)
    spec = {"template": "t", "mechanism": "m", "hypothesis": "h", "universe": ["A"], "datasets": ["d"],
            "sources": ["s"], "grid": {"k": [1]}, "acceptance": "a", "baseline": "b", "costs": "c", "rejection": "r"}
    con.executemany("INSERT INTO experiments(exp_id,version,spec_json,spec_commit) VALUES(?,?,?,?)",
                    [("E1", 1, json.dumps(spec), "c" * 40), ("E2", 1, json.dumps(spec), "c" * 40)])
    con.executemany("INSERT INTO events(id,kind,actor,payload) VALUES(?,?,?,?)", [
        (1, "template.approved", "human:anton", json.dumps({"reason": "Approved by Claude on behalf of the user"})),
        (2, "family.approved", "human:anton", json.dumps({}))])
    con.executemany("INSERT INTO transitions(exp_id,ts,from_state,to_state,actor,evidence) VALUES(?,?,?,?,?,?)", [
        ("E1", 1, None, "DISCOVERED", "discovery-catalogue", None),
        ("E1", 2, "DISCOVERED", "REGISTERED", "system", json.dumps({"template_approval_event": 1})),
        ("E1", 3, "REGISTERED", "SCREENING", "system", None),
        ("E1", 4, "SCREENING", "REJECTED", "system", None),
        ("E2", 1, None, "DISCOVERED", "system", None),
        ("E2", 2, "DISCOVERED", "REGISTERED", "system", json.dumps({"family_approval_event": 2})),
        ("E2", 3, "REGISTERED", "SCREENING", "system", None),
        ("E2", 5, "SCREENING", "REJECTED", "system", None),
        ("L1", 0, None, "REJECTED", "legacy-import", None),
        ("E3", 9, "PAPER_TRADING", "PAUSED", "system", None)])
    con.executemany("INSERT INTO datasets(exp_id,ts) VALUES(?,?)", [("E1", 3), ("E2", 3)])
    con.executemany("INSERT INTO trials(exp_id) VALUES(?)", [("E1",)])
    return con


class Pipeline(unittest.TestCase):
    def test_classes(self):
        p = fs.pipeline_shadow(synthetic_lab())
        by = {(r["exp_id"], r["to"]): r for r in p["rows"]}
        self.assertEqual(by[("E1", "REGISTERED")]["classes"], ["delegated-approval"])
        self.assertEqual(by[("E2", "REGISTERED")]["factory"], "ALLOW")
        self.assertIn("hash-at-access", by[("E1", "SCREENING")]["classes"])
        self.assertIn("universe-asof-unrecorded", by[("E1", "SCREENING")]["classes"])
        self.assertEqual(by[("E1", "REJECTED")]["factory"], "ALLOW")          # trials row = ledger charge
        self.assertEqual(by[("E2", "REJECTED")]["classes"], ["no-charge"])
        self.assertEqual(by[("L1", "REJECTED")]["classes"], ["legacy"])
        self.assertEqual([r["exp_id"] for r in p["unexplained"]], ["E3"])     # unknown edges are never silent


class Scale(unittest.TestCase):
    def test_small_world(self):
        w = fs.scale_world((0, 0.0, 10, 300))
        self.assertTrue(w["leak_caught"])
        self.assertEqual(w["blocked_without_approval"], w["candidates"])
        self.assertEqual(w["ledger_entries"], w["tested"])
        self.assertEqual(w["max_entries_per_candidate"], 1)
        self.assertAlmostEqual(w["alpha_charged"], 0.05)


if __name__ == "__main__":
    unittest.main()
