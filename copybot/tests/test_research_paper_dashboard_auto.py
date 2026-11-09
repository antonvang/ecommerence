"""Director order 63: the 5-minute dashboard automation (meta refresh, atomic write, read-only, no network,
STALE/MISSING_MARK kept, last good snapshot kept on failure) and its user-systemd units."""
import hashlib
import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import paper_dashboard as pd  # noqa: E402
from tests.test_research_paper_dashboard import CUT, make_db  # noqa: E402

UNITS = os.path.join(HERE, "research", "ops", "dashboard_timer")


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Auto(unittest.TestCase):
    def setUp(self):
        self.db = make_db(equity=[("FRESH", CUT - 600, 10010.0), ("OLD", CUT - 62000, 9990.0)],
                          ledgers=[("FRESH", "straks"), ("OLD", "carry90"), ("NOMARK", "lane")])
        self.out = os.path.join(tempfile.mkdtemp(), "dash.html")

    def run_main(self, *extra):
        return pd.main(["--db", self.db, "--cutoff", "2026-11-09T00:00:00Z", "--out", self.out, *extra], now=CUT)

    def test_meta_refresh_and_no_script(self):
        self.run_main("--refresh", "300")
        doc = open(self.out, encoding="utf-8").read()
        self.assertIn('<meta http-equiv="refresh" content="300">', doc)
        self.assertNotIn("<script", doc.lower())

    def test_refresh_off_by_default_and_bounded(self):
        self.run_main()
        self.assertNotIn("http-equiv", open(self.out, encoding="utf-8").read())
        with self.assertRaises(SystemExit):
            self.run_main("--refresh", "5")

    def test_stale_and_missing_mark_kept(self):
        self.run_main("--refresh", "300")
        doc = open(self.out, encoding="utf-8").read()
        self.assertIn("Ikke tilgængelig", doc)
        self.assertIn("MISSING_MARK", doc)
        self.assertIn("Forældet", doc)

    def test_db_read_only_and_unchanged_no_network(self):
        before = sha(self.db)
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network")), \
                mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("dns")):
            self.run_main("--refresh", "300")
        self.assertEqual(sha(self.db), before)
        con = pd.connect_ro(self.db)
        with self.assertRaises(Exception):
            con.execute("DELETE FROM sim_fills")

    def test_atomic_write_keeps_last_good_snapshot_on_failure(self):
        self.run_main()
        good = sha(self.out)
        with mock.patch.object(pd.os, "replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                self.run_main("--refresh", "300")
        self.assertEqual(sha(self.out), good)
        left = [f for f in os.listdir(os.path.dirname(self.out)) if f.endswith(".tmp")]
        self.assertEqual(left, [])

    def test_render_failure_leaves_snapshot(self):
        self.run_main()
        good = sha(self.out)
        with mock.patch.object(pd, "render", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.run_main()
        self.assertEqual(sha(self.out), good)


class Units(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(UNITS, name), encoding="utf-8") as f:
            return f.read()

    def test_service_is_oneshot_read_only_command_without_restart(self):
        s = self.read("copybot-dashboard.service")
        self.assertIn("Type=oneshot", s)
        self.assertNotIn("Restart=", s)
        self.assertIn("research/tools/paper_dashboard.py", s)
        self.assertIn("--refresh 300", s)
        self.assertIn("flock -n", s)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", s)
        body = "\n".join(ln for ln in s.splitlines() if not ln.startswith("#"))
        for bad in ("pm_lp", "sudo", "lab fleet", "-m lab", "systemctl", "quarantine", "N4_KIMCHI"):
            self.assertNotIn(bad, body)

    def test_timer_every_five_minutes(self):
        t = self.read("copybot-dashboard.timer")
        self.assertIn("OnUnitActiveSec=5min", t)
        self.assertIn("Unit=copybot-dashboard.service", t)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
