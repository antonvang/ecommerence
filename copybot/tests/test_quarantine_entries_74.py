"""Order 74 P0: every supported test entry point refuses a quarantined path. Synthetic checkout and register in a
temporary directory: the real quarantine register and the files it lists are not used."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = '''import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SYNTH = os.path.join(ROOT, "research", "data", "SYNTH.json")


class Probe(unittest.TestCase):
    def test_refused(self):
        with self.assertRaises(Exception) as cm:
            open(SYNTH, "rb")
        self.assertEqual(type(cm.exception).__name__, "ProtectedFileAccess")
        with self.assertRaises(Exception) as cm:
            os.open(SYNTH, os.O_RDONLY)
        self.assertEqual(type(cm.exception).__name__, "ProtectedFileAccess")

    def test_other_files_open(self):
        with open(os.path.join(ROOT, "research", "data", "QUARANTINE.json"), encoding="utf-8") as f:
            self.assertIn("entries", f.read())
'''


class Entries(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        data, tests = os.path.join(self.root, "research", "data"), os.path.join(self.root, "tests")
        os.makedirs(data)
        os.makedirs(tests)
        with open(os.path.join(data, "QUARANTINE.json"), "w", encoding="utf-8") as f:
            json.dump({"entries": [{"id": "s", "path": "research/data/SYNTH.json"}, {"id": "n", "path": None}]}, f)
        with open(os.path.join(data, "SYNTH.json"), "w", encoding="utf-8") as f:
            f.write('{"synthetic": true}')
        for name in ("__init__.py", "offline_market.py", "test_000_quarantine_guard.py"):
            shutil.copy(os.path.join(HERE, "tests", name), tests)
        with open(os.path.join(tests, "test_probe.py"), "w", encoding="utf-8") as f:
            f.write(PROBE)

    def run_unittest(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "unittest", *args], cwd=self.root, env=env, capture_output=True,
                              text=True, timeout=120)

    def test_named_modules(self):
        """Documented form and scripts/suite_parallel.sh."""
        r = self.run_unittest("tests.test_probe")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_discover(self):
        """scripts/suite.sh."""
        r = self.run_unittest("discover", "-s", "tests")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Ran 3 tests", r.stderr)

    def test_the_probe_can_fail(self):
        """Control: without the guard the synthetic file really opens, so the two tests above prove something."""
        os.remove(os.path.join(self.root, "tests", "__init__.py"))
        os.remove(os.path.join(self.root, "tests", "test_000_quarantine_guard.py"))
        r = self.run_unittest("discover", "-s", "tests")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("test_refused", r.stderr)


class Layout(unittest.TestCase):
    def test_guard_module_sorts_before_every_other_test(self):
        names = sorted(f for f in os.listdir(os.path.join(HERE, "tests")) if f.startswith("test") and f.endswith(".py"))
        self.assertEqual(names[0], "test_000_quarantine_guard.py")


if __name__ == "__main__":
    unittest.main()
