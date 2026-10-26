"""research/LINUX_DRIFT.md 2026-10-22: `lab deploy-check` says, read-only, whether a deploy landed. Fakes only: no
dashboard, no processes, no git."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import deploycheck  # noqa: E402

PROCS = ["python3 -m lab fleet", "python3 -m lab web --port 8770", "python3 -m lab watch --port 8770",
         "python3 -u -m research.pm_lp collect --approved"]


class DeployCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labdc")
        self.root = os.path.join(self.tmp, "copybot")
        os.makedirs(os.path.join(self.root, "data", "lab"))
        with open(os.path.join(self.root, "data", "lab", "start.log"), "wb") as f:
            f.write(b"PREFLIGHT OK\n\x00\x00binary\nPREFLIGHT FAILED: x\nlater\nPREFLIGHT OK\n")
        with open(os.path.join(self.root, "a.py"), "w") as f:
            f.write("x = 1\n")
        open(os.path.join(self.root, "data", "lab", "watch.heartbeat"), "w").close()   # touched now
        self.kpis = [{"deploy": {"commit": "abc1234"}, "fail_closed": False, "agents_active": 18, "agents_total": 18}]
        self.status = ""

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        if path == "kpis":
            return 200, json.dumps(self.kpis.pop(0) if len(self.kpis) > 1 else self.kpis[0]).encode(), 0.1
        return 200, b"{}", 0.2

    def git(self, repo, *args):
        return {"rev-parse": "abc1234\n", "ls-files": "copybot/a.py\n", "status": self.status}[args[0]]

    def run_checks(self, **kw):
        kw = {"procs": PROCS, "get": self.get, "git": self.git, "restart": lambda root: (True, "ok"),
              "sleep": lambda s: None, **kw}
        return {n: (ok, d) for n, ok, d in deploycheck.checks(self.root, **kw)}

    def test_everything_in_place(self):
        r = self.run_checks()
        self.assertTrue(all(ok for ok, _ in r.values()), r)
        self.assertEqual(r["last start printed PREFLIGHT OK"], (True, "PREFLIGHT OK"))   # NUL bytes in the log

    def test_each_failure_is_reported(self):
        self.kpis = [{"deploy": {"commit": "0000000"}, "fail_closed": True, "agents_active": 3, "agents_total": 18}]
        self.status = " M copybot/lab/risk.py\n"
        with open(os.path.join(self.root, "a.py"), "w"):
            pass                                                   # a crash left it at 0 bytes
        r = self.run_checks(procs=PROCS[:2], restart=lambda root: (False, "import fails"))
        for name in ("dashboard runs the expected commit", "FAIL_CLOSED off", "all agents active", "watcher running",
                     "pm_lp collector running", "pm_lp collector could restart", "no tracked file is empty",
                     "checkout has no local changes"):
            self.assertFalse(r[name][0], name)
        self.assertIn("after 90 s", r["all agents active"][1])

    def test_a_watch_once_check_or_a_stale_heartbeat_is_not_a_running_watcher(self):
        """research/LINUX_DRIFT.md Mission 15 (2026-10-26)."""
        once = PROCS[:2] + ["python3 -m lab watch --once"] + PROCS[3:]
        r = self.run_checks(procs=once)
        self.assertEqual(r["watcher running"], (False, "0 process(es)"))
        hb = os.path.join(self.root, "data", "lab", "watch.heartbeat")
        t = os.path.getmtime(hb)
        self.assertEqual(deploycheck.watcher_beat(self.root, now=t + 300, boot=t - 600), (False, "heartbeat 300 s old"))
        self.assertEqual(deploycheck.watcher_beat(self.root, now=t + 30, boot=t + 10),
                         (False, "no heartbeat since the host booted"))
        self.assertEqual(deploycheck.watcher_beat(self.root, now=t + 30, boot=t - 600), (True, "heartbeat 30 s ago"))
        os.remove(hb)
        r = self.run_checks()
        self.assertEqual(r["watcher heartbeat fresh"], (False, "no data/lab/watch.heartbeat"))

    def test_waits_for_a_fresh_fleet(self):
        self.kpis = [{**self.kpis[0], "agents_active": 0}, {**self.kpis[0], "agents_active": 9}, self.kpis[0]]
        r = self.run_checks()
        self.assertEqual(r["all agents active"], (True, "18 of 18 (after 10 s)"))

    def test_an_endpoint_that_fails_and_the_verdict_line(self):
        def get(path):
            if path == "overview":
                raise TimeoutError("timed out")
            return self.get(path)
        lines = []
        rc = deploycheck.main(self.root, out=lines.append, procs=PROCS, get=get, git=self.git,
                              restart=lambda root: (True, "ok"), sleep=lambda s: None)
        self.assertEqual((rc, lines[-1]), (1, "DEPLOY CHECK FAILED"))
        self.assertIn("  [NO ] /api/overview: TimeoutError('timed out')", lines)
        self.assertEqual(deploycheck.main(self.root, out=lines.append, procs=PROCS, get=self.get, git=self.git,
                                          restart=lambda root: (True, "ok"), sleep=lambda s: None), 0)
        self.assertEqual(lines[-1], "DEPLOY OK")
        self.assertEqual(deploycheck.last_preflight(os.path.join(self.tmp, "absent.log")), None)


if __name__ == "__main__":
    unittest.main()
