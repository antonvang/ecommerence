"""Director order 49 P0: S1 shadow job isolation and traceability (synthetic lab database on disk)."""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import factory_s1 as s1  # noqa: E402
from tests.test_research_factory_shadow import synthetic_lab  # noqa: E402


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class S1(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.db = os.path.join(self.root, "lab.db")
        mem = synthetic_lab()
        mem.commit()                    # an open write transaction would block the backup
        disk = sqlite3.connect(self.db)
        mem.backup(disk)
        disk.close()
        self.out = os.path.join(self.root, "s1")

    def tearDown(self):
        shutil.rmtree(self.root)

    def files(self):
        return sorted(os.path.relpath(os.path.join(p, f), self.root) for p, _, fs in os.walk(self.root) for f in fs)

    def test_read_only_connection_cannot_write(self):
        con = s1.open_ro(self.db)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("INSERT INTO trials(exp_id) VALUES('X')")
        con.close()

    def test_lab_db_unchanged_and_writes_only_own_dir(self):
        before_sha, before_files = sha(self.db), self.files()
        code, info = s1.run(self.db, self.out, now=1000)
        self.assertEqual(code, 0)
        self.assertEqual(sha(self.db), before_sha)
        new = set(self.files()) - set(before_files)
        self.assertTrue(new)
        self.assertTrue(all(p.startswith("s1" + os.sep) for p in new), new)
        self.assertEqual(info["phase"], "BASELINE")

    def test_baseline_then_observation_and_chain(self):
        s1.run(self.db, self.out, now=1000)
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO transitions(exp_id,ts,from_state,to_state,actor) VALUES('E9',7,NULL,'DISCOVERED','system')")
        con.commit()
        con.close()
        code, info = s1.run(self.db, self.out, now=2000)
        self.assertEqual((code, info["new"], info["phase"]), (0, 1, "OBSERVATION"))
        code, info = s1.run(self.db, self.out, now=3000)
        self.assertEqual(info["new"], 0)                       # each transition is recorded once
        entries = s1._read_jsonl(os.path.join(self.out, "decisions.jsonl"))
        s1.verify_chain(entries)
        self.assertEqual([e["phase"] for e in entries].count("OBSERVATION"), 1)
        state = json.load(open(os.path.join(self.out, "state.json")))
        self.assertEqual(state["started_ts"], 1000)
        self.assertEqual(state["runs"], 3)
        self.assertTrue(os.path.exists(os.path.join(self.out, "summary.md")))

    def test_stop_file(self):
        os.makedirs(self.out)
        open(os.path.join(self.out, "STOP"), "w").close()
        before = self.files()
        code, info = s1.run(self.db, self.out, now=1000)
        self.assertEqual(code, 3)
        self.assertEqual(self.files(), before)

    def test_error_stops_only_this_run(self):
        before_sha = sha(self.db)
        code, _ = s1.run(os.path.join(self.root, "missing.db"), self.out, now=1000)
        self.assertEqual(code, 2)
        self.assertTrue(os.path.exists(os.path.join(self.out, "errors.jsonl")))
        self.assertEqual(sha(self.db), before_sha)
        self.assertFalse(os.path.exists(os.path.join(self.root, "missing.db")))   # mode=ro never creates a db

    def test_tampered_report_is_refused(self):
        s1.run(self.db, self.out, now=1000)
        p = os.path.join(self.out, "decisions.jsonl")
        text = open(p).read().replace('"factory":"BLOCK"', '"factory":"ALLOW"', 1)
        open(p, "w").write(text)
        code, _ = s1.run(self.db, self.out, now=2000)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
