"""Forward paper view on a synthetic journal. No network, no real journal."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jupiter_bot.core import Rejected
from jupiter_bot.research import forward, replay
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401
from jupiter_bot.tests.test_replay import END, T0, alternating, build_standard

REGISTRY = {"alt": (alternating, lambda params: 30, [{"every": 10}, {"every": 20}])}


class Forward(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = Path(cls.template_dir.name) / "template.db"
        build_standard(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.journal = self.root / "observations.db"
        shutil.copy(self.template, self.journal)
        self.lock = self.root / "plan_lock.json"
        self.out = self.root / "forward"
        patcher = patch.object(forward, "STRATEGIES", REGISTRY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.dir.cleanup()

    def write_lock(self, code=None, dev_start=T0):
        lock = dict(plan_sha256="p", code_sha256=code if code is not None else replay.code_hashes(alternating),
                    development=dict(start=dev_start, end=END + 86400),
                    holdout=dict(start=END + 86400, end=END + 2 * 86400))
        self.lock.write_text(json.dumps(lock))

    def run_at(self, now):
        return forward.run(self.journal, self.lock, self.out, clock=lambda: now)

    def test_nothing_without_a_lock(self):
        with self.assertRaises(Rejected):
            self.run_at(END + 120)
        self.assertFalse(self.out.exists())

    def test_one_file_per_grid_entry_replaced_each_run(self):
        self.write_lock()
        rows = self.run_at(END + 120)
        self.assertEqual([r["status"] for r in rows], ["OK", "OK"])
        files = sorted(p.name for p in self.out.glob("*.json"))
        self.assertEqual(files, ["alt-0.json", "alt-1.json"])
        first = json.loads((self.out / "alt-0.json").read_text())
        self.assertEqual((first["label"], first["delay_s"], first["extra_cost_bps"]), ("forward", 120, 25))
        self.assertEqual(first["period"], {"start": T0, "end": END})
        self.assertIn("now_target", first)
        self.run_at(END + 180)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), files)     # replaced, no temp leftovers
        self.assertEqual(json.loads((self.out / "alt-0.json").read_text())["updated_at"], END + 180)

    def test_changed_code_is_reported_not_run(self):
        self.write_lock(code={"jupiter_bot/research/replay.py": "0" * 64})
        rows = self.run_at(END + 120)
        self.assertEqual({r["status"] for r in rows}, {"REJECTED"})
        self.assertIn("differs from the locked code", json.loads((self.out / "alt-0.json").read_text())["error"])

    def test_forward_must_start_at_the_development_start(self):
        self.write_lock(dev_start=T0 + 600)
        with self.assertRaises(Rejected):
            replay.run(self.journal, "alt", alternating, {"every": 10}, T0, END, 120, 25, "forward",
                       bars=30, out_dir=self.root / "x", plan_lock=self.lock, controls=0, clock=lambda: END + 120)

    def test_cli_has_no_forward_label(self):
        with self.assertRaises(SystemExit):
            replay.main(["--journal", str(self.journal), "--strategy", "tsmom", "--start", "2026-11-21T00:00:00Z",
                         "--end", "2026-11-22T00:00:00Z", "--label", "forward"])


if __name__ == "__main__":
    unittest.main()
