"""Independent watcher (lab/watch.py): judges lab, agents, dashboard and pm_lp collector from outside, read-only."""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import watch  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.fleet import ROLES  # noqa: E402
from research import pm_lp  # noqa: E402

D0 = 20743
NOW = (D0 + 1) * 86400 + 12 * 3600          # 2026-10-18 12:00 UTC (development period)
AGENT = sorted(ROLES)[0]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labwatch")
        self.lab = os.path.join(self.tmp, "lab.db")
        self.pm = os.path.join(self.tmp, "pm_lp.db")
        db = DB(self.lab)
        db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status, stale_after) "
                       "VALUES('supervisor', ?, 1, 1, '', 'running', 30)", (NOW - 2,))
        for name in ROLES:
            stale = 10800 if name == "discovery-scanner" else 180
            db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status, stale_after) "
                           "VALUES(?, ?, 1, 1, '', 'idle', ?)", (name, NOW - 1, stale))
        db.close()
        con = pm_lp.open_db(self.pm)
        con.execute("INSERT INTO meta VALUES('D0', ?)", (str(D0),))
        con.execute("INSERT INTO snaps VALUES(?, 'c', 0.4, 0.6, 0, 0, 0.04, 20, 10, 0.01)", (NOW - 50,))
        con.execute("INSERT INTO status VALUES(?, 'c', 0, 1, NULL)", (NOW - 3600,))
        con.commit()
        con.close()
        self.p = [mock.patch.object(watch, "_processes", lambda needle: [4242]),
                  mock.patch("lab.preflight.dashboard_running", lambda port, timeout=3: True),
                  mock.patch.object(watch, "check_awake", lambda: (True, "sleep blocked in logind by 'copybot'"))]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def res(self, now=NOW):
        return watch.check(self.lab, self.pm, 8770, now)

    def lab_sql(self, sql, *args):
        con = sqlite3.connect(self.lab)
        con.execute(sql, args)
        con.commit()
        con.close()

    def pm_sql(self, sql, *args):
        con = sqlite3.connect(self.pm)
        con.execute(sql, args)
        con.commit()
        con.close()

    def scan(self, ts):
        db = DB(self.lab)
        db.append("observations", ts=int(ts), detector="abnormal_move/1", source="t", instrument="BTCUSDT",
                  metric="z_1h", value=0.0, threshold=4, flagged=0, payload={})
        db.close()

    def k3(self, S, metric):
        db = DB(self.lab)
        db.append("observations", ts=int(S - 2100), detector="k3/1", source="t", instrument="round", metric=metric,
                  value=S, threshold=None, flagged=0, payload={})
        db.close()

    def lab_event(self, kind, ts):
        db = DB(self.lab)
        db.append("events", ts=int(ts), kind=kind, actor="test", exp_id=None, payload={})
        db.close()


class Checks(Base):
    def test_everything_up(self):
        self.lab_event("system.running", NOW - 3 * 3600)              # fleet up 3 h and doing research
        self.lab_event("job.done", NOW - 60)
        self.scan(NOW - 3480)                                            # 11:02 UTC
        self.k3(NOW, "selection")                                        # NOW is a K3 settlement (12:00 UTC)
        r = self.res()
        self.assertIsNone(r["paper"]["ok"])                              # no paper ledger: not judged
        self.assertTrue(all(v["ok"] for k, v in r.items() if k not in ("paper", "pm_coverage")),   # no panel here
                        {k: v for k, v in r.items() if not v["ok"]})
        self.assertEqual({k for k in r if not k.startswith("agent:")},
                         {"lab", "lab_state", "progress", "paper", "scanner", "dashboard", "collector", "pm_coverage",
                          "awake"})
        self.assertEqual(len([k for k in r if k.startswith("agent:")]), len(ROLES))

    def test_whole_fleet_down_or_hung_and_agents_are_not_judged_then(self):
        r = self.res(NOW + watch.LAB_STALE_S + 5)
        self.assertFalse(r["lab"]["ok"])
        self.assertTrue(all(r[f"agent:{n}"]["ok"] is None for n in ROLES))
        self.lab_sql("UPDATE heartbeats SET status='stopped' WHERE worker='supervisor'")
        self.assertIn("stopped", self.res()["lab"]["detail"])
        self.lab_sql("DELETE FROM heartbeats WHERE worker='supervisor'")
        self.assertFalse(self.res()["lab"]["ok"])
        os.remove(self.lab)
        self.assertFalse(self.res()["lab"]["ok"])

    def test_failed_hung_and_long_period_agents(self):
        self.lab_sql("UPDATE heartbeats SET status='failed', ok=0, detail='feed down' WHERE worker=?", AGENT)
        r = self.res()
        self.assertTrue(r["lab"]["ok"])
        self.assertFalse(r[f"agent:{AGENT}"]["ok"])
        self.assertIn("feed down", r[f"agent:{AGENT}"]["detail"])
        self.lab_sql("UPDATE heartbeats SET status='idle', ok=1, ts=? WHERE worker=?", NOW - 500, AGENT)
        self.assertIn("500 s old", self.res()[f"agent:{AGENT}"]["detail"])
        self.lab_sql("UPDATE heartbeats SET ts=? WHERE worker='discovery-scanner'", NOW - 3700)   # hourly agent
        self.assertTrue(self.res()["agent:discovery-scanner"]["ok"])

    def test_pm_lp_snapshot_coverage_below_90_percent_is_a_fault(self):
        """research/LINUX_DRIFT.md 2026-10-23 (the user's yes): today's running snapshot coverage, read-only."""
        day = int(NOW) // 86400                                   # 12:00 UTC: 720 minutes so far
        con = pm_lp.open_db(self.pm)
        con.execute("DELETE FROM snaps")
        con.executemany("INSERT INTO panel VALUES(?, ?)", [(day, "a"), (day, "b"), (day - 1, "a")])
        rows = lambda n, c: [(day * 86400 + 60 * i, c, 0.4, 0.6, 0, 0, 0.04, 20, 10, 0.01) for i in range(n)]  # noqa
        con.executemany("INSERT INTO snaps VALUES(?,?,?,?,?,?,?,?,?,?)", rows(720, "a") + rows(0, "b"))   # 50 %
        con.commit()
        con.close()
        watch._PMCOV.clear()
        r = self.res()["pm_coverage"]
        self.assertFalse(r["ok"])
        self.assertIn("snapshot coverage today 50.0% < 90% (D1)", r["detail"])
        con = pm_lp.open_db(self.pm)
        con.executemany("INSERT INTO snaps VALUES(?,?,?,?,?,?,?,?,?,?)", rows(650, "b"))                   # 95.1 %
        con.commit()
        con.close()
        self.assertFalse(self.res()["pm_coverage"]["ok"])                         # cached: at most once an hour
        watch._PMCOV.clear()
        r = self.res()["pm_coverage"]
        self.assertTrue(r["ok"])
        self.assertIn("snapshot coverage today 95.1%; yesterday 0.0%", r["detail"])
        watch._PMCOV.clear()
        self.assertTrue(watch.check_pm_coverage(self.pm, day * 86400 + 3600)[0])  # 01:00: too early to judge

    def test_a_fresh_heartbeat_without_a_successful_pass_is_not_healthy(self):
        """research/LINUX_DRIFT.md 2026-10-23: periodic agents are judged by their last successful pass."""
        self.lab_sql("UPDATE heartbeats SET last_ok_ts=?, started_ts=? WHERE worker='premium-watch'", NOW - 30,
                     NOW - 86400)                                                # every 60 s: fine
        self.assertTrue(self.res()["agent:premium-watch"]["ok"])
        self.lab_sql("UPDATE heartbeats SET last_ok_ts=? WHERE worker='premium-watch'", NOW - 700)   # > 600 s
        r = self.res()["agent:premium-watch"]
        self.assertFalse(r["ok"])
        self.assertIn("no successful pass for 700 s (expected every 60 s)", r["detail"])
        self.lab_sql("UPDATE heartbeats SET last_ok_ts=?, started_ts=? WHERE worker='discovery-scanner'", NOW - 7200,
                     NOW - 86400)                                                # hourly: 3 passes = 3 h
        self.assertTrue(self.res()["agent:discovery-scanner"]["ok"])
        self.lab_sql("UPDATE heartbeats SET last_ok_ts=NULL, started_ts=? WHERE worker='news-watch'", NOW - 300)
        self.assertTrue(self.res()["agent:news-watch"]["ok"])                    # just started: one window
        self.lab_sql("UPDATE heartbeats SET started_ts=? WHERE worker='news-watch'", NOW - 3600)
        self.assertIn("no successful pass recorded", self.res()["agent:news-watch"]["detail"])
        self.assertTrue(self.res()[f"agent:{AGENT}"]["ok"])                     # job agents: not judged by passes

    def test_blocked_agents_are_judged_through_lab_state(self):
        self.lab_sql("UPDATE heartbeats SET status='blocked', detail='lab FAIL_CLOSED' WHERE worker != 'supervisor'")
        db = DB(self.lab)
        db.append("risk_events", exp_id="GLOBAL", ts=NOW - 90, rule="disk_low", value=None, threshold=None,
                  action="FAIL_CLOSED", detail="disk below 2 GB", actor="system:risk")
        db.close()
        r = self.res()
        self.assertFalse(r["lab_state"]["ok"])
        self.assertIn("FAIL_CLOSED", r["lab_state"]["detail"])

    def test_long_resource_hold_and_operator_pause(self):
        self.lab_event("system.resource_hold", NOW - watch.HOLD_ALERT_S + 60)
        self.assertTrue(self.res()["lab_state"]["ok"])                               # short hold: fine
        self.assertFalse(self.res(NOW + 120)["lab_state"]["ok"])                       # long hold: outage
        self.lab_event("system.resource_ok", NOW)
        self.lab_event("system.paused", NOW)
        r = self.res(NOW + 120)
        self.assertTrue(r["lab_state"]["ok"])
        self.assertIn("paused", r["lab_state"]["detail"])

    def test_dashboard_down(self):
        with mock.patch("lab.preflight.dashboard_running", lambda port, timeout=3: False):
            self.assertFalse(self.res()["dashboard"]["ok"])

    def test_collector_process_missing_or_stale(self):
        with mock.patch.object(watch, "_processes", lambda needle: []):
            r = self.res()["collector"]
        self.assertFalse(r["ok"])
        self.assertIn("no collector process", r["detail"])
        r = self.res(NOW + watch.COLLECTOR_STALE_S)["collector"]
        self.assertFalse(r["ok"])
        self.assertIn("alive but last snapshot", r["detail"])

    def test_collector_phase_boundaries_follow_the_registered_calendar(self):
        last_quote_day = (D0 + pm_lp.HOLD_DAYS[1]) * 86400 + 3600
        self.pm_sql("INSERT INTO snaps VALUES(?, 'c', 0.4, 0.6, 0, 0, 0.04, 20, 10, 0.01)", last_quote_day - 30)
        self.assertTrue(self.res(last_quote_day)["collector"]["ok"])                   # D0+27: snapshots expected
        self.assertFalse(self.res(last_quote_day + watch.COLLECTOR_STALE_S + 10)["collector"]["ok"])
        tracking = (D0 + pm_lp.HOLD_DAYS[1] + 1) * 86400 + 600                          # D0+28: status polls only
        self.pm_sql("INSERT INTO status VALUES(?, 'c', 0, 1, NULL)", tracking - 3600)
        r = self.res(tracking)["collector"]
        self.assertTrue(r["ok"], r)
        self.assertIn("resolution tracking", r["detail"])
        self.assertFalse(self.res(tracking + watch.STATUS_STALE_S)["collector"]["ok"])
        last_tracking = (D0 + pm_lp.TAIL_END) * 86400 + 600                             # D0+41: still tracking
        with mock.patch.object(watch, "_processes", lambda needle: []):
            self.assertFalse(self.res(last_tracking)["collector"]["ok"])
            self.assertTrue(self.res((D0 + pm_lp.TAIL_END + 1) * 86400 + 60)["collector"]["ok"])   # finished

    def test_one_failing_probe_does_not_blind_the_others(self):
        with mock.patch.object(watch, "check_lab", side_effect=sqlite3.OperationalError("no such table: heartbeats")), \
                mock.patch.object(watch, "_processes", lambda needle: []):
            r = self.res()
        self.assertFalse(r["lab"]["ok"])
        self.assertIn("check failed", r["lab"]["detail"])
        self.assertIsNone(r[f"agent:{AGENT}"]["ok"])
        self.assertFalse(r["collector"]["ok"])                                          # still judged
        self.assertTrue(r["dashboard"]["ok"])

    def test_unreadable_pm_lp_database_is_an_outage_not_a_crash(self):
        with open(self.pm, "wb") as f:
            f.write(b"not a database" * 100)
        r = self.res()["collector"]
        self.assertFalse(r["ok"])
        self.assertIn("unreadable", r["detail"])

    def test_checks_never_change_database_contents(self):
        before = (sha(self.lab), sha(self.pm))
        for t in (NOW, NOW + 10_000):
            self.res(t)
        self.assertEqual((sha(self.lab), sha(self.pm)), before)
        self.assertFalse(os.path.exists(self.pm + "-journal"))
        self.assertFalse(os.path.exists(self.pm + "-wal"))

    def test_process_scan_matches_command_line_and_checkout(self):
        proc = os.path.join(self.tmp, "proc")
        here = os.path.join(self.tmp, "checkout")
        other = os.path.join(self.tmp, "elsewhere")
        os.makedirs(here)
        os.makedirs(other)
        for pid, cmd, cwd in ((101, b"python3\0-u\0-m\0research.pm_lp\0collect\0--approved\0", here),
                              (102, b"python3\0-m\0research.pm_lp\0collect\0", other),          # other checkout
                              (103, b"python3\0-m\0lab\0fleet\0", here),
                              (os.getpid(), b"python3\0research.pm_lp collect\0", here)):        # itself
            d = os.path.join(proc, str(pid))
            os.makedirs(d)
            with open(os.path.join(d, "cmdline"), "wb") as f:
                f.write(cmd)
            try:
                os.symlink(cwd, os.path.join(d, "cwd"))
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not available")
        os.makedirs(os.path.join(proc, "self"))
        self.p[0].stop()
        try:
            self.assertEqual(watch._processes("research.pm_lp collect", proc, here), [101])
            self.assertEqual(watch._processes("research.pm_lp collect", os.path.join(self.tmp, "none"), here), [])
        finally:
            self.p[0].start()


class Scanner(Base):
    """research/LINUX_DRIFT.md 2026-10-25: the hourly scan and K3 rounds, judged only while the lab runs; fail-closed."""
    def test_stale_weekend_hour_and_k3_round(self):
        self.lab_event("system.running", NOW - 3 * 3600)
        sun = NOW                                                        # Sunday 2026-10-18 12:00 UTC (a K3 S)
        self.scan(sun - 3480)
        self.k3(sun, "missed")                                           # a recorded miss is not a new alarm
        self.assertTrue(watch.check_scanner(self.lab, sun + 600, True)[0])          # 12:10: before HH:12
        r = watch.check_scanner(self.lab, sun + 720, True)                          # 12:12: the 12:02 scan is missing
        self.assertFalse(r[0])
        self.assertIn("weekend", r[1])
        self.scan(sun + 122)
        self.assertTrue(watch.check_scanner(self.lab, sun + 720, True)[0])
        self.assertFalse(watch.check_scanner(self.lab, sun + 122 + 71 * 60, True)[0])   # 71 min old
        mon = sun + 86400 - 12 * 3600 + 3 * 3600                         # Monday 03:00 UTC: weekday, no weekend rule
        self.scan(mon - 3480)
        self.assertTrue(watch.check_scanner(self.lab, mon + 720, True)[0])
        self.scan(mon + 122)                                                        # 03:02 UTC
        r = watch.check_scanner(self.lab, mon + 3600 - 30 * 60 + 1, True)          # 03:30: K3 04:00 is due
        self.assertFalse(r[0])
        self.assertIn("K3 round 04:00", r[1])
        self.k3(mon + 3600, "selection")
        self.assertTrue(watch.check_scanner(self.lab, mon + 3600 - 30 * 60 + 1, True)[0])

    def test_not_judged_while_down_or_starting_and_fail_closed(self):
        self.assertIsNone(watch.check_scanner(self.lab, NOW, False)[0])
        self.lab_event("system.running", NOW - 120)
        self.assertIsNone(watch.check_scanner(self.lab, NOW, True)[0])            # fleet up 2 min
        self.assertFalse(watch.check_scanner(os.path.join(self.tmp, "nope.db"), NOW, True)[0])
        bad = os.path.join(self.tmp, "bad.db")
        with open(bad, "wb") as f:
            f.write(b"not a database" * 100)
        self.assertFalse(watch.check_scanner(bad, NOW, True)[0])                   # unreadable: down, not ok
        r = self.res()
        self.assertIn("scanner", r)


class Alerts(Base):
    def setUp(self):
        super().setUp()
        self.sent, self.clock, self.lines = [], {"t": NOW}, []
        self.counter, self.offset, self.boot = {"n": 0}, {"s": 0.0}, {"t": NOW - 86400}
        self.w = self.watcher()

    def watcher(self, delivered=True):
        return watch.Watcher(self.lab, self.pm, 8770, log_dir=os.path.join(self.tmp, "logs"),
                             status_file=os.path.join(self.tmp, "status.json"),
                             heartbeat_file=os.path.join(self.tmp, "watch.heartbeat"),
                             notifier=lambda t, b: self.sent.append(t) or delivered, clock=lambda: self.clock["t"],
                             suspends=lambda: self.counter["n"], slept=lambda: self.offset["s"],
                             booted=lambda: self.boot.get("t"), out=self.lines.append)

    def tick(self, advance=0, lab_alive=True):
        """Advance the clock; the collector keeps writing; the lab beats unless lab_alive is False."""
        self.clock["t"] += advance
        if lab_alive:
            self.lab_sql("UPDATE heartbeats SET ts=?", self.clock["t"] - 1)
        self.pm_sql("INSERT INTO snaps VALUES(?, 'c', 0.4, 0.6, 0, 0, 0.04, 20, 10, 0.01)", self.clock["t"] - 5)
        return self.w.tick()

    def log(self):
        out = []
        for f in os.listdir(os.path.join(self.tmp, "logs")):
            out += [json.loads(l) for l in open(os.path.join(self.tmp, "logs", f))]
        return [r for r in out if r["kind"] != "alive"]

    def test_a_reboot_or_a_long_silence_is_reported_at_the_next_start(self):
        self.tick()
        self.assertEqual(self.sent, [])                                     # a first start ever: nothing to report
        self.clock["t"] += 60
        self.w = self.watcher()                                             # a quick restart: no report
        self.tick()
        self.assertEqual(self.sent, [])
        self.clock["t"] += 3 * 3600
        self.boot["t"] = self.clock["t"] - 600                              # the host rebooted in between
        self.w = self.watcher()
        self.tick()
        self.assertEqual(self.sent, ["Copybot: overvågningen var nede"])
        self.assertIn("the host booted at", self.lines[-1])
        self.assertIn("(180 min)", self.lines[-1])
        self.tick(30)
        self.assertEqual(len(self.sent), 1)                                 # once per start

    def test_down_once_reminder_hourly_and_recovery(self):
        self.tick()
        self.assertEqual(self.sent, [])
        with mock.patch.object(watch, "_processes", lambda needle: []):
            for _ in range(5):
                self.tick(30)
            self.assertEqual(self.sent, ["Copybot: collector NEDE"])
            self.tick(watch.REMIND_S)
            self.assertEqual(self.sent[-1], "Copybot: collector stadig nede")
        self.tick(30)
        self.assertEqual(self.sent[-1], "Copybot: collector virker igen")
        self.assertEqual([(r["kind"], r["component"]) for r in self.log()],
                         [("down", "collector"), ("still_down", "collector"), ("recovered", "collector")])
        self.assertTrue(all(r["notified"] for r in self.log()))
        self.assertTrue(json.load(open(os.path.join(self.tmp, "status.json")))["components"]["collector"]["ok"])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "watch.heartbeat")))

    def test_each_agent_failure_alerts_on_its_own(self):
        self.tick()
        self.lab_sql("UPDATE heartbeats SET status='failed', ok=0, detail='feed down' WHERE worker='paper-1'")
        self.w.tick()
        self.lab_sql("UPDATE heartbeats SET status='failed', ok=0, detail='hung' WHERE worker='risk-1'")
        self.w.tick()
        self.assertEqual(self.sent, ["Copybot: agent:paper-1 NEDE", "Copybot: agent:risk-1 NEDE"])

    def test_lab_down_does_not_fake_an_agent_recovery(self):
        self.tick()
        self.lab_sql("UPDATE heartbeats SET status='failed', ok=0, detail='feed down' WHERE worker='paper-1'")
        self.w.tick()
        self.tick(watch.LAB_STALE_S + 30, lab_alive=False)                       # the whole fleet stops beating
        self.assertIn("Copybot: lab NEDE", self.sent)
        self.assertNotIn("Copybot: agent:paper-1 virker igen", self.sent)
        self.lab_sql("UPDATE heartbeats SET ts=?", self.clock["t"])              # back, paper-1 still failed
        self.w.tick()
        self.assertIn("Copybot: lab virker igen", self.sent)
        self.assertEqual(self.sent.count("Copybot: agent:paper-1 NEDE"), 1)      # no second 'down' either

    def test_a_restarted_watcher_does_not_repeat_a_known_outage(self):
        with mock.patch.object(watch, "_processes", lambda needle: []):
            self.tick()
            self.assertEqual(len(self.sent), 1)
            self.w = self.watcher()
            self.tick(60)
        self.assertEqual(len(self.sent), 1)

    def test_starting_while_something_is_down_alerts_at_once(self):
        self.lab_sql("UPDATE heartbeats SET status='stopped' WHERE worker='supervisor'")
        self.w.tick()
        self.assertIn("Copybot: lab NEDE", self.sent)

    def test_sleep_is_reported_after_waking_by_counter_or_clocks(self):
        self.tick()
        self.counter["n"] = 1                                                    # suspend-to-RAM
        self.tick(30)
        self.offset["s"] += 3600                                                 # hibernate: counter unchanged
        self.tick(30)
        self.tick(30)
        self.assertEqual(self.sent.count("Copybot: maskinen har været i dvale"), 2)
        self.assertIsNone(watch.suspend_count(os.path.join(self.tmp, "missing")))

    def test_an_undelivered_notification_is_visible_in_log_and_output(self):
        self.w = self.watcher(delivered=False)
        with mock.patch.object(watch, "_processes", lambda needle: []):
            self.tick()
        self.assertFalse(self.log()[0]["notified"])
        self.assertIn("no desktop notification delivered", self.lines[-1])


class Cli(Base):
    def test_once_exit_codes_summary_and_single_instance(self):
        lines = []
        with mock.patch.object(watch, "PM_DB", self.pm), mock.patch.object(watch.time, "time", lambda: NOW):
            self.assertEqual(watch.main(self.lab, 8770, once=True, out=lines.append), 0)
            self.assertIn("  [OK ] agents: 18 healthy", lines)
            self.lab_sql("UPDATE heartbeats SET status='stopped' WHERE worker='supervisor'")
            lines.clear()
            self.assertEqual(watch.main(self.lab, 8770, once=True, out=lines.append), 1)
        self.assertTrue(any(l.startswith("  [NO ] lab") for l in lines))
        self.assertTrue(any("not judged" in l for l in lines))
        from lab.supervisor import acquire_lock, release_lock
        lock_path = os.path.join(self.tmp, "watch.lock")
        lock = acquire_lock(lock_path)
        try:
            with mock.patch.object(watch, "LOCK_FILE", lock_path):
                self.assertEqual(watch.main(self.lab, 8770, out=lines.append), 3)
        finally:
            release_lock(lock)

    def test_notify_can_be_disabled_and_uses_the_session_bus(self):
        with mock.patch.dict(os.environ, {"COPYBOT_WATCH_NOTIFY": "0"}):
            self.assertFalse(watch.notify("t", "b"))
        calls = []

        class R:
            returncode = 0
        env = {k: v for k, v in os.environ.items() if k not in ("DBUS_SESSION_BUS_ADDRESS", "COPYBOT_WATCH_NOTIFY")}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(watch.shutil, "which", lambda name: "/usr/bin/notify-send"), \
                mock.patch.object(watch.os.path, "exists", lambda p: True), \
                mock.patch.object(watch.subprocess, "run", lambda cmd, **k: calls.append(k["env"]) or R()):
            if hasattr(os, "getuid"):
                self.assertTrue(watch.notify("t", "b"))
                self.assertTrue(calls[0]["DBUS_SESSION_BUS_ADDRESS"].startswith("unix:path=/run/user/"))

    def test_awake_reads_logind_blocks(self):
        self.p[2].stop()
        masked = mock.patch.object(watch, "sleep_masked", lambda: False)
        masked.start()
        try:
            inh = [{"what": "sleep", "who": "NetworkManager", "why": "x", "mode": "delay", "uid": 0, "pid": 1}]
            with mock.patch.object(watch, "logind_inhibitors", lambda: inh):
                ok, detail = watch.check_awake()
                self.assertFalse(ok)                                           # delay locks do not block sleep
                self.assertIn("NOT blocked", detail)
            inh.append({"what": "sleep:idle", "who": "copybot", "why": "lab og pm_lp", "mode": "block", "uid": 1000,
                        "pid": 225567})
            with mock.patch.object(watch, "logind_inhibitors", lambda: inh):
                self.assertEqual(watch.check_awake(), (True, "sleep blocked in logind by 'copybot' (pid 225567)"))
            with mock.patch.object(watch, "logind_inhibitors", side_effect=RuntimeError("no system bus")):
                self.assertIsNone(watch.check_awake()[0])
        finally:
            masked.stop()
            self.p[2].start()

    def test_awake_accepts_sleep_masked_system_wide_without_an_inhibitor(self):
        self.p[2].stop()
        try:
            with mock.patch.object(watch, "sleep_masked", lambda: True), \
                    mock.patch.object(watch, "logind_inhibitors", lambda: []):
                ok, detail = watch.check_awake()
            self.assertTrue(ok)
            self.assertIn("masked", detail)
            with mock.patch.object(watch, "sleep_masked", side_effect=RuntimeError("no system bus")), \
                    mock.patch.object(watch, "logind_inhibitors", lambda: []):
                self.assertFalse(watch.check_awake()[0])                  # falls back to the logind check
        finally:
            self.p[2].start()

    def test_the_lab_watches_the_watcher(self):
        from lab import ops
        self.assertEqual(ops.EXTERNAL_FILES["W_watch"][1], ("data/lab/watch.heartbeat",))


if __name__ == "__main__":
    unittest.main()
