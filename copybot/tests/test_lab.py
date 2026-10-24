import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import legacy, lifecycle, registry  # noqa: E402
from lab.__main__ import main as cli  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.lifecycle import EDGES, FINAL, STATES, LifecycleError  # noqa: E402

LAB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab")
H, S = "human:tester", "system:test"
FULL = {"hypothesis": "h", "mechanism": "m", "sources": ["s"], "datasets": ["d"], "methodology": "x", "baseline": "b",
        "costs": "c", "acceptance": "a", "rejection": "r", "alpha": 0.001, "code": "lab/registry.py",
        "mechanism_tag": "test_tag", "execution": "taker"}


def fresh():
    return DB(":memory:")


def to_registered(db, exp="E1"):
    """Drive E1 to REGISTERED with a (faked) committed complete spec."""
    if not db.one("SELECT 1 FROM experiments WHERE exp_id=?", exp):
        registry.discover(db, exp, "h", "test_tag", "inst", "minutes", "taker", "unit test", H)
    with mock.patch.object(registry, "git_committed", return_value=True), \
            mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(FULL))), \
            mock.patch.object(registry, "last_commit", return_value="c0ffee"), \
            mock.patch.object(registry, "blob_at", return_value="b10b"):
        registry.add_version(db, exp, "research/registry/E1/SPEC.json", H)
        code = lifecycle.request_approval(db, exp, "REGISTERED", H, "complete spec committed",
                                          guards=(registry.complete_spec_guard,))
        lifecycle.confirm(db, code, H, guards=(registry.complete_spec_guard,))


class Storage(unittest.TestCase):
    def test_append_only_tables_refuse_update_and_delete(self):
        db = fresh()
        db.event("x", S)
        for sql in ("UPDATE events SET kind='y'", "DELETE FROM events"):
            with self.assertRaises(sqlite3.DatabaseError):
                db.con.execute(sql)

    def test_hash_chain_detects_tampering(self):
        db = fresh()
        for i in range(3):
            db.event(f"k{i}", S, payload={"i": i})
        chains, trig = db.verify()
        self.assertTrue(trig)
        self.assertEqual(chains["events"], (3, None))
        db.con.execute("DROP TRIGGER events_no_update")          # an attacker would have to do this first
        db.con.execute("UPDATE events SET payload='{\"i\":99}' WHERE id=2")
        chains, trig = db.verify()
        self.assertFalse(trig)
        self.assertEqual(chains["events"][1], 2)


class Lifecycle(unittest.TestCase):
    def test_no_live_state_and_no_automatic_promotion(self):
        self.assertNotIn("LIVE", " ".join(STATES))
        promotions = {("DISCOVERED", "REGISTERED"), ("SCREEN_PASSED", "VALIDATION"), ("VALIDATED", "PAPER_TRADING"),
                      ("PAUSED", "PAPER_TRADING"), ("SUPPRESSED", "DISCOVERED")}
        for e in promotions:
            self.assertEqual(EDGES[e], "human", e)
        self.assertTrue(all(who == "human" for (a, b), who in EDGES.items() if b == "PAPER_TRADING"))
        self.assertFalse(any(a in FINAL for a, _ in EDGES))

    def test_registration_needs_complete_spec_and_human(self):
        db = fresh()
        registry.discover(db, "E1", "h", "test_tag", "inst", "minutes", "taker", "unit test", H)
        with self.assertRaises(LifecycleError):
            lifecycle.auto_transition(db, "E1", "REGISTERED", S, "trying to skip the human")
        with self.assertRaises(LifecycleError):                  # partial spec
            lifecycle.request_approval(db, "E1", "REGISTERED", H, "please register this",
                                       guards=(registry.complete_spec_guard,))
        to_registered(db)
        self.assertEqual(lifecycle.state(db, "E1"), "REGISTERED")

    def test_approval_code_single_use_expiry_and_actor(self):
        db = fresh()
        registry.discover(db, "E2", "h", "tag2", "inst", "minutes", "taker", "unit test", H)
        with self.assertRaises(LifecycleError):
            lifecycle.request_approval(db, "E2", "WITHDRAWN", S, "systems cannot approve")
        code = lifecycle.request_approval(db, "E2", "WITHDRAWN", H, "no longer relevant", now=1000)
        with self.assertRaises(LifecycleError):
            lifecycle.confirm(db, code, H, now=1000 + 16 * 60)   # expired
        code = lifecycle.request_approval(db, "E2", "WITHDRAWN", H, "no longer relevant")
        with self.assertRaises(LifecycleError):
            lifecycle.confirm(db, code, S)                       # only humans confirm
        lifecycle.confirm(db, code, H)
        self.assertEqual(lifecycle.state(db, "E2"), "WITHDRAWN")
        with self.assertRaises(LifecycleError):
            lifecycle.confirm(db, code, H)                       # used / final

    def test_gate_transitions_must_cite_matching_results(self):
        db = fresh()
        to_registered(db)
        lifecycle.auto_transition(db, "E1", "SCREENING", S, "spec committed, screening starts")
        fail = registry.record_result(db, "E1", "EXPLORATORY", "FAIL: all variants negative", {}, {}, S)
        with self.assertRaises(LifecycleError):
            ev = {"result_id": fail}
            lifecycle.auto_transition(db, "E1", "SCREEN_PASSED", S, "pretend it passed", ev,
                                      guards=(registry.make_result_guard(ev),))
        ev = {"result_id": fail}
        lifecycle.auto_transition(db, "E1", "REJECTED", S, "development gates failed", ev,
                                  guards=(registry.make_result_guard(ev),))
        with self.assertRaises(LifecycleError):                  # final
            lifecycle.auto_transition(db, "E1", "SCREENING", S, "try again quietly")

    def test_validation_requires_committed_frozen_file(self):
        db = fresh()
        to_registered(db)
        lifecycle.auto_transition(db, "E1", "SCREENING", S, "spec committed, screening starts")
        ok = registry.record_result(db, "E1", "EXPLORATORY", "PASS (preliminary)", {}, {}, S)
        ev = {"result_id": ok}
        lifecycle.auto_transition(db, "E1", "SCREEN_PASSED", S, "development gates passed", ev,
                                  guards=(registry.make_result_guard(ev),))
        with self.assertRaises(LifecycleError):
            lifecycle.request_approval(db, "E1", "VALIDATION", H, "open the holdout once")
        with self.assertRaises(LifecycleError):
            lifecycle.request_approval(db, "E1", "VALIDATION", H, "open the holdout once",
                                       {"committed_files": ["research/does_not_exist.md"]})
        code = lifecycle.request_approval(db, "E1", "VALIDATION", H, "open the holdout once",
                                          {"committed_files": ["research/PMCAL_FROZEN.md"]})
        lifecycle.confirm(db, code, H)
        self.assertEqual(lifecycle.state(db, "E1"), "VALIDATION")


class Registry(unittest.TestCase):
    def test_spec_frozen_after_data_access(self):
        db = fresh()
        to_registered(db)
        lifecycle.auto_transition(db, "E1", "SCREENING", S, "spec committed, screening starts")
        with self.assertRaises(registry.RegistryError):
            registry.add_version(db, "E1", "research/registry/E1/SPEC.json", H)

    def test_results_superseded_not_rewritten(self):
        db = fresh()
        registry.discover(db, "E3", "h", "tag3", "inst", "minutes", "taker", "unit test", H)
        first = registry.record_result(db, "E3", "EXPLORATORY", "FAIL", {"x": 1}, {}, S)
        with self.assertRaises(registry.RegistryError):
            registry.record_result(db, "E3", "EXPLORATORY", "PASS", {}, {}, S, supersedes=first)
        second = registry.record_result(db, "E3", "EXPLORATORY", "FAIL (corrected cost)", {}, {}, S,
                                        supersedes=first, reason="fee constant was wrong, corrected")
        rows = db.q("SELECT id, verdict FROM results WHERE exp_id='E3' ORDER BY id")
        self.assertEqual([r["id"] for r in rows], [first, second])           # both stay
        self.assertEqual(registry.status(db)[0]["verdict"], "FAIL (corrected cost)")
        with self.assertRaises(registry.RegistryError):
            registry.record_result(db, "E3", "LIVE", "PASS", {}, {}, S)      # no such label

    def test_legacy_import_graveyard_and_evidence(self):
        db = fresh()
        imp, skip = legacy.import_legacy(db)
        self.assertEqual((len(imp), len(skip)), (len(legacy.HISTORY), 0))
        self.assertEqual(legacy.import_legacy(db), ([], [e[0] for e in legacy.HISTORY]))   # idempotent
        self.assertEqual(legacy.verify_evidence(db), [])
        st = {x["exp_id"]: x["state"] for x in registry.status(db)}
        self.assertEqual(st["X01_pm_lp_v1"], "EXTERNAL")
        self.assertEqual(st["L16_pmcal_v1"], "REJECTED")
        self.assertEqual(st["L15_tsmom_v2"], "WITHDRAWN")
        state, dup = registry.discover(db, "N1", "order flow again", "orderflow_imbalance", "eth_perp", "minutes",
                                       "taker", "unit test", H)
        self.assertEqual((state, dup), ("SUPPRESSED", ["L20_m1_orderflow"]))
        with self.assertRaises(LifecycleError):
            lifecycle.request_approval(db, "N1", "DISCOVERED", H, "please revive this idea")
        code = lifecycle.request_approval(db, "N1", "DISCOVERED", H,
                                          "materially different because it uses maker execution with queue data")
        lifecycle.confirm(db, code, H)
        with self.assertRaises(LifecycleError):                  # EXTERNAL cannot be promoted by the lab
            lifecycle.request_approval(db, "X01_pm_lp_v1", "PAPER_TRADING", H, "promote the external study")
        chains, trig = db.verify()
        self.assertTrue(trig and all(b is None for _, b in chains.values()))


class GitCaches(unittest.TestCase):
    """research/LINUX_DRIFT.md 2026-10-24: the git lookups are remembered only while their answer cannot change."""

    def setUp(self):
        for c in (registry._BLOBS, registry._LAST, registry._WORKING):
            c.clear()
        self.calls = []
        real = registry.git
        self.git = mock.patch.object(registry, "git", lambda *a: self.calls.append(a) or real(*a))
        self.git.start()
        self.addCleanup(self.git.stop)

    def test_a_blob_is_remembered_only_at_a_full_commit_sha(self):
        sha = registry.git("rev-parse", "HEAD")
        self.calls.clear()
        a, b = registry.blob_at(sha, "lab/db.py"), registry.blob_at(sha, "lab/db.py")
        self.assertEqual(a, b)
        self.assertEqual(len(self.calls), 1)
        registry.blob_at("HEAD", "lab/db.py"), registry.blob_at("HEAD", "lab/db.py")
        self.assertEqual(len(self.calls), 3)                               # a symbolic name is asked every time
        self.assertIsNone(registry.blob_at(sha, "no/such/file.py"))
        self.assertIsNone(registry.blob_at(sha, "no/such/file.py"))
        self.assertEqual(len(self.calls), 5)                               # a miss is never remembered

    def test_last_commit_is_asked_again_when_head_moves(self):
        keys = iter([("k1",), ("k1",), ("k2",)])
        with mock.patch.object(registry, "head_key", lambda: next(keys)):
            c = [registry.last_commit("lab/db.py") for _ in range(3)]
        self.assertEqual(len({x for x in c}), 1)
        self.assertEqual(len([x for x in self.calls if x[0] == "log"]), 2)
        with mock.patch.object(registry, "head_key", lambda: None):        # unreadable HEAD: nothing is cached
            registry.last_commit("lab/db.py"), registry.last_commit("lab/db.py")
        self.assertEqual(len([x for x in self.calls if x[0] == "log"]), 4)

    def test_the_real_head_key_is_readable_and_stable(self):
        k = registry.head_key()
        self.assertIsNotNone(k)
        self.assertEqual(k, registry.head_key())

    def test_a_working_file_is_hashed_again_after_any_write(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "x.json")
            with open(f, "w") as fh:
                fh.write("{}")
            a = registry.hash_object(f)
            st = os.stat(f)
            with open(f, "w") as fh:
                fh.write("[]")                                             # same size, possibly the same clock tick
            os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))               # and the old mtime put back
            c = registry.hash_object(f)
            self.assertNotEqual(a, c)                                      # a just-written file is never remembered
            self.assertEqual(c, registry.git("hash-object", f))
            self.assertEqual(len(self.calls), 3)

    def test_an_old_file_is_remembered_until_it_changes(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "x.json")
            with open(f, "w") as fh:
                fh.write("{}")
            later = os.stat(f).st_ctime + 10
            with mock.patch.object(registry.time, "time", lambda: later):
                a, b = registry.hash_object(f), registry.hash_object(f)
            self.assertEqual((a, len(self.calls)), (b, 1))                 # older than RACY_S: one git call
            with open(f, "w") as fh:
                fh.write("[1]")
            self.assertNotEqual(registry.hash_object(f), a)                # size and ctime moved: hashed again


class StatusCli(unittest.TestCase):
    def test_a_later_final_decision_outranks_an_old_pass_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, lines = os.path.join(tmp, "lab.db"), []
            db = DB(p)
            for e in ("E8", "E9"):
                registry.discover(db, e, "h", "tag_" + e, "inst", "minutes", "taker", "unit test", H)
                registry.record_result(db, e, "EXPLORATORY", "PASS (screen): all gates passed", {}, {}, S)
            code = lifecycle.request_approval(db, "E9", "WITHDRAWN", H, "owner decision: retire the old pass unused")
            lifecycle.confirm(db, code, H)
            db.close()
            self.assertEqual(cli(["status"], p, lines.append), 0)
            row = {x.split()[0]: x for x in lines if x.startswith("E")}
            self.assertIn("WITHDRAWN: owner decision: retire the old pass unused (tidligere: PASS", row["E9"])
            self.assertTrue(row["E8"].rstrip().endswith("PASS (screen): all gates passed"))   # not final: unchanged


class Safety(unittest.TestCase):
    def test_lab_has_no_order_or_credential_code(self):
        banned = ("private_key", "api_key", "apisecret", "place_order", "/order", "signtransaction", "withdraw(")
        for f in os.listdir(LAB):
            if f.endswith(".py"):
                with open(os.path.join(LAB, f), encoding="utf-8") as fh:
                    txt = fh.read().lower()
                for b in banned:
                    self.assertNotIn(b, txt, f"{f} contains {b}")

    def test_cli_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, lines = os.path.join(tmp, "lab.db"), []
            self.assertEqual(cli(["import-legacy"], p, lines.append), 0)
            self.assertEqual(cli(["verify"], p, lines.append), 0)
            self.assertEqual(cli(["status"], p, lines.append), 0)
            self.assertTrue(any("VERIFY OK" in x for x in lines))
            self.assertEqual(cli(["transition", "L16_pmcal_v1", "SCREENING", "--reason", "reopen quietly"],
                                 p, lines.append), 1)


if __name__ == "__main__":
    unittest.main()
