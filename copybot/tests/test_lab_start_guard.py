"""START_LAB.sh refuses to start when the code differs from the committed version (a hard crash left freshly
written files empty on 2026-10-21) and when preflight does not answer PREFLIGHT OK."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
POSIX = os.name == "posix" and shutil.which("bash") and shutil.which("git")


def guard():
    with open(os.path.join(ROOT, "START_LAB.sh"), encoding="utf-8") as f:
        s = f.read()
    return s[s.index("# >>> code guard"):s.index("# <<< code guard")]


@unittest.skipUnless(POSIX, "needs bash and git")
class CodeGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labguard")
        os.makedirs(os.path.join(self.tmp, "lab"))
        for name, text in (("lab/__main__.py", "print('lab')\n"), ("START_LAB.sh", "echo start\n")):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write(text)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-qm", "c"]):
            subprocess.run(cmd, cwd=self.tmp, check=True, env=env)
        with open(os.path.join(self.tmp, "guard.sh"), "w") as f:
            f.write("now() { date -u +%FT%TZ; }\n" + guard() + "echo GUARD-PASSED\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_guard(self):
        p = subprocess.run(["bash", "guard.sh"], cwd=self.tmp, capture_output=True, text=True)
        return p.returncode, p.stdout

    def test_a_clean_tree_passes(self):
        self.assertEqual(self.run_guard(), (0, "GUARD-PASSED\n"))

    def test_an_emptied_source_file_stops_the_start(self):
        open(os.path.join(self.tmp, "lab", "__main__.py"), "w").close()     # what the crash left behind
        rc, out = self.run_guard()
        self.assertEqual(rc, 1)
        self.assertIn("lab/__main__.py", out)
        self.assertNotIn("GUARD-PASSED", out)

    def test_untracked_data_does_not_stop_the_start(self):
        with open(os.path.join(self.tmp, "lab", "notes.txt"), "w") as f:
            f.write("x")
        self.assertEqual(self.run_guard()[0], 0)


class PreflightAnswer(unittest.TestCase):
    def test_the_script_requires_the_preflight_ok_line(self):
        with open(os.path.join(ROOT, "START_LAB.sh"), encoding="utf-8") as f:
            s = f.read()
        self.assertIn('grep -q "^PREFLIGHT OK$"', s)
        from lab import preflight
        out = []
        preflight.main(os.path.join(tempfile.mkdtemp(prefix="labpf"), "none.db"), out=out.append)
        self.assertNotIn("PREFLIGHT OK", out)                  # a refused preflight never prints the OK line


if __name__ == "__main__":
    unittest.main()
