"""KPIs show the deployed commit, whether the independent watcher runs, and the host boot time (display only)."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, ops  # noqa: E402
from lab.db import DB  # noqa: E402


class Status(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(os.path.join(self.tmp.name, "lab.db"))
        command._DEPLOYED.clear()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_kpis_carry_deploy_watcher_and_boot(self):
        k = command.kpis(self.db)
        self.assertIn("commit", k["deploy"])
        self.assertIn("running", k["watcher"])
        self.assertTrue(k["host_boot_ts"] is None or k["host_boot_ts"] > 1_600_000_000)

    def test_deployed_is_the_checkout_head_and_cached(self):
        d = command.deployed(now=1000.0)
        if d["commit"] is not None:                                  # a git checkout (always, in this repo)
            self.assertRegex(d["commit"], r"^[0-9a-f]{7,}$")
        with mock.patch("subprocess.check_output", side_effect=AssertionError("not cached")):
            self.assertEqual(command.deployed(now=1030.0), d)

    def test_watcher_state(self):
        for age, running in ((5.0, True), (command.WATCHER_STALE_S + 1, False), (None, False)):
            with mock.patch.object(ops, "external_freshness",
                                   return_value={"W_watch": {"last_write_age_s": age}}):
                w = command.watcher_state()
            self.assertEqual((w["age_s"], w["running"]), (age, running))


if __name__ == "__main__":
    unittest.main()
