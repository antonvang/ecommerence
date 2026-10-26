"""research/LINUX_DRIFT.md 2026-10-23: the Linux S7 automation is prepared, refuses while the S7 gate is closed, and
never starts anything now."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.db import DB  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTO = os.path.join(HERE, "lab", "automation")
SCRIPT = os.path.join(AUTO, "s7_install_linux.sh")


class Units(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(AUTO, name), encoding="utf-8") as f:
            return f.read()

    def test_the_lab_starts_at_boot_and_is_never_restarted_after_a_crash(self):
        u = self.read("copybot-lab.service")
        self.assertIn("ExecStart=%h/ecommerence/copybot/START_LAB.sh", u)
        self.assertIn("Restart=no", u)
        self.assertNotIn("Restart=on-failure", u)
        self.assertIn("WantedBy=default.target", u)
        # the DNS wait (at most 120 x 5 s) must fit in the start timeout: with Restart=no a cut wait is never retried
        self.assertIn("[ $$i -ge 120 ]", u)
        self.assertIn("\nTimeoutStartSec=15min\n", u)

    def test_the_watcher_restarts_itself_and_only_runs_the_read_only_watch(self):
        u = self.read("copybot-watch.service")
        self.assertIn("ExecStart=%h/ecommerence/copybot/START_WATCH.sh", u)
        self.assertIn("Restart=on-failure", u)
        with open(os.path.join(HERE, "START_WATCH.sh"), encoding="utf-8") as f:
            self.assertIn("exec python3 -m lab watch", f.read())


class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labs7")
        self.units = os.path.join(self.tmp, "units")
        self.calls = os.path.join(self.tmp, "calls")
        fake = os.path.join(self.tmp, "systemctl")
        with open(fake, "w") as f:
            f.write(f'#!/bin/sh\necho "$@" >> {self.calls}\n')
        os.chmod(fake, 0o755)
        self.env = {**os.environ, "SYSTEMD_USER_DIR": self.units, "SYSTEMCTL": fake,
                    "LAB_DB": os.path.join(self.tmp, "lab.db")}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_it(self):
        return subprocess.run([SCRIPT], env=self.env, capture_output=True, text=True, timeout=120)

    def test_it_refuses_and_installs_nothing_while_the_s7_gate_is_closed(self):
        DB(self.env["LAB_DB"]).con.close()
        r = self.run_it()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("IKKE installeret", r.stdout)
        self.assertFalse(os.path.exists(self.units))
        self.assertFalse(os.path.exists(self.calls))

    def test_with_the_gate_open_it_enables_both_units_without_starting_them(self):
        db, now = DB(self.env["LAB_DB"]), int(time.time())
        for h in range(8 * 24, -1, -1):
            db.append("events", ts=now - h * 3600, kind="system.alive", actor="t", exp_id=None, payload={})
        db.con.close()
        r = self.run_it()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(self.units)), ["copybot-lab.service", "copybot-watch.service"])
        with open(self.calls) as f:
            calls = f.read().splitlines()
        self.assertEqual(calls, ["--user daemon-reload", "--user enable copybot-lab copybot-watch"])
        self.assertFalse(any("--now" in c or " start" in c for c in calls))
        self.assertEqual(self.run_it().returncode, 3)                  # a second run changes nothing


if __name__ == "__main__":
    unittest.main()
