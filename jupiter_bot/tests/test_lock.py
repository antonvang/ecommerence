import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from jupiter_bot.research import lock as L
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401

BEFORE = L.HOLDOUT["start"] - 86400


def ok_git(repo, *args):
    out = "abc123\n" if args[0] == "rev-parse" else ""
    return subprocess.CompletedProcess(args, 0, out, "")


class Lock(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.dir.name) / "repo"
        for name in (L.PLAN, *L.CODE):
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text("x = 1\n")
        self.approve()
        self.out = Path(self.dir.name) / "out"

    def tearDown(self):
        self.dir.cleanup()

    def approve(self, status="Status: **GODKENDT af Anton 2026-11-21.**"):
        (self.repo / L.PLAN).write_text("# Plan\n\n%s\n" % status)

    def test_lock_records_hashes_once(self):
        record = L.lock("Anton", self.out, self.repo, now=BEFORE, git=ok_git)
        self.assertEqual(record["git_commit"], "abc123")
        self.assertEqual(json.loads((self.out / "plan_lock.json").read_text())["plan_sha256"], record["plan_sha256"])
        self.assertEqual(L.verify(record, self.repo), [])
        with self.assertRaises(L.LockError):
            L.lock("Anton", self.out, self.repo, now=BEFORE, git=ok_git)

    def test_draft_plan_is_refused(self):
        self.approve("Status: **UDKAST — afventer Antons godkendelse.**")
        with self.assertRaises(L.LockError):
            L.lock("Anton", self.out, self.repo, now=BEFORE, git=ok_git)

    def test_too_late_is_refused(self):
        with self.assertRaises(L.LockError):
            L.lock("Anton", self.out, self.repo, now=L.HOLDOUT["start"], git=ok_git)

    def test_uncommitted_change_is_refused(self):
        def dirty(repo, *args):
            code = 1 if args[0] == "diff" else 0
            return subprocess.CompletedProcess(args, code, "", "")
        with self.assertRaises(L.LockError):
            L.lock("Anton", self.out, self.repo, now=BEFORE, git=dirty)
        self.assertFalse((self.out / "plan_lock.json").exists())

    def test_verify_detects_a_changed_strategy(self):
        record = L.lock("Anton", self.out, self.repo, now=BEFORE, git=ok_git)
        (self.repo / L.CODE[0]).write_text("x = 2\n")
        self.assertEqual(L.verify(record, self.repo), ["%s changed since the lock" % L.CODE[0]])

    def test_windows_match_the_plan_text(self):
        plan = (L.REPO / L.PLAN).read_text(encoding="utf-8")
        for text in ("2026-11-21 00:00", "2026-12-19 00:00", "2027-01-02 00:00"):
            self.assertIn(text, plan)


if __name__ == "__main__":
    unittest.main()
