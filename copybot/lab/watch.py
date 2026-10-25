"""Independent watcher (Linux host): checks the lab and the pm_lp collector from outside both processes and raises an
alert when either stops making progress, including when the whole local fleet is down or hung.

Never changes database contents: lab.db and pm_lp.db are opened with mode=ro (opening lab.db, which is in WAL mode,
may create or update its -wal/-shm sidecar files; pm_lp.db is in rollback mode and gets none). The watcher writes only
its own log (data/lab/logs/watch-YYYYMMDD.jsonl), status file (data/lab/watch_status.json) and heartbeat file
(data/lab/watch.heartbeat, which the lab's risk agent watches in turn). It never starts, stops or restarts anything.
It is started by hand like the lab; installing it as an autostart, timer or service is S7 automation and stays closed
until the S7 gate opens (research/ENGINE_PROPOSAL.md section 10, lab/README.md, research/LINUX_DRIFT.md).

  python3 -m lab watch            loop (default every 30 s)
  python3 -m lab watch --once     one check; exit 0 if everything judged is up, 1 otherwise (external health check)

Components: lab (supervisor alive), lab_state (FAIL_CLOSED, long resource hold), agent:<name> per roster agent (not
judged while the supervisor is down), dashboard, collector, awake (a logind block on sleep, e.g. the desktop systemd-inhibit
line; not judged where logind cannot be asked); plus a one-off 'suspended' alert after the host slept.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

from lab import ops
from lab.db import DEFAULT_DB, HERE

LAB_STALE_S = 120              # the supervisor beats every second
HOLD_ALERT_S = 30 * 60         # a resource hold longer than this is an outage of the research
COLLECTOR_STALE_S = 300        # a snapshot round every ~61 s while quoting
STATUS_STALE_S = 7 * 3600      # resolution tracking only: status polls every 6 h
REMIND_S = 3600
REMIND_OVERRIDE = {"progress": 24 * 3600, "paper": 6 * 3600}   # idleness daily, paper marks every 6 h
PAPER_MARK_MAX_S = int(2.5 * 3600)   # every active simulated ledger is marked once an hour
PAPER_PAUSE_MAX_S = 24 * 3600        # a ledger paused longer than this is reported
IDLE_ALERT_S = 6 * 3600       # no finished job for this long while the fleet has run >= 2 h and nothing is runnable
SLEEP_JUMP_S = 5               # CLOCK_BOOTTIME - CLOCK_MONOTONIC grows only while the host is suspended or hibernated
PM_DB = os.path.join(HERE, "data", "research", "pm_lp", "pm_lp.db")
STATUS_FILE = os.path.join(HERE, "data", "lab", "watch_status.json")
HEARTBEAT_FILE = os.path.join(HERE, "data", "lab", "watch.heartbeat")
LOCK_FILE = os.path.join(HERE, "data", "lab", "watch.lock")
SUSPEND_COUNT = "/sys/power/suspend_stats/success"


def suspend_count(path=SUSPEND_COUNT):
    """Successful suspend-to-RAM transitions since boot (Linux)."""
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


DOWNTIME_S = 300                # a watcher restart after a longer silence is reported (reboot, kill, crash)


def boot_time(path="/proc/stat"):
    """When the host booted (Linux btime), or None where unsupported."""
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("btime "):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return None


def sleep_offset():
    """Seconds the host has spent suspended or hibernated since boot (any sleep type); None where unsupported."""
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME) - time.clock_gettime(time.CLOCK_MONOTONIC)
    except (AttributeError, OSError):
        return None


def _ro(path):
    if not os.path.exists(path):
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _processes(needle, proc_root="/proc", here=HERE):
    """PIDs whose command line contains `needle` and whose working directory is this checkout."""
    out = []
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return out
    for p in entries:
        if not p.isdigit() or int(p) == os.getpid():
            continue
        try:
            with open(os.path.join(proc_root, p, "cmdline"), "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode(errors="replace")
            cwd = os.readlink(os.path.join(proc_root, p, "cwd"))
        except OSError:
            continue
        if needle in cmd and os.path.realpath(cwd) == os.path.realpath(here):
            out.append(int(p))
    return out


def check_lab(db_path, now):
    """{component: (ok, detail)}; ok is None for 'not judged' (agents while the supervisor is down)."""
    from lab.command import STALE_PASSES
    from lab.fleet import ROLES, ROSTER
    every_of = {name: every for name, _r, _k, _fn, every, _h in ROSTER}
    con = _ro(db_path)
    if con is None:
        return {"lab": (False, "lab database missing"), "lab_state": (None, "not judged: no lab database"),
                **{f"agent:{n}": (None, "not judged") for n in ROLES}}
    try:
        rows = {r["worker"]: dict(r) for r in con.execute("SELECT * FROM heartbeats")}
        fc = con.execute("SELECT action, ts, detail FROM risk_events WHERE exp_id='GLOBAL' AND action IN "
                         "('FAIL_CLOSED','CLEAR') ORDER BY id DESC LIMIT 1").fetchone()
        hold = con.execute("SELECT kind, ts FROM events WHERE kind IN ('system.resource_hold','system.resource_ok') "
                           "ORDER BY id DESC LIMIT 1").fetchone()
        pause = con.execute("SELECT kind FROM events WHERE kind IN ('system.paused','system.resumed') "
                            "ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        con.close()
    out = {}
    if fc is not None and fc["action"] == "FAIL_CLOSED":
        out["lab_state"] = (False, f"FAIL_CLOSED since {int(now - fc['ts'])} s: {(fc['detail'] or '')[:120]} "
                                   "(research stopped; clearing needs a human)")
    elif hold is not None and hold["kind"] == "system.resource_hold" and now - hold["ts"] > HOLD_ALERT_S:
        out["lab_state"] = (False, f"resource hold for {int(now - hold['ts'])} s (RAM or disk below the floor)")
    elif pause is not None and pause["kind"] == "system.paused":
        out["lab_state"] = (True, "paused by the operator (not an outage)")
    else:
        out["lab_state"] = (True, "not FAIL_CLOSED, no long resource hold")
    try:
        out["progress"] = _progress(con_path=db_path, now=now, sup=rows.get("supervisor"))
    except Exception as e:                            # the progress probe must never break the liveness checks
        out["progress"] = (None, f"not judged: progress check failed {e!r}"[:200])
    try:
        out["paper"] = _paper(con_path=db_path, now=now, sup=rows.get("supervisor"))
    except Exception as e:
        out["paper"] = (None, f"not judged: paper check failed {e!r}"[:200])
    sup = rows.get("supervisor")
    if sup is None:
        out["lab"] = (False, "no supervisor heartbeat recorded")
    elif sup.get("status") != "running":
        out["lab"] = (False, f"supervisor status '{sup.get('status')}' ({int(now - sup['ts'])} s ago)")
    elif now - sup["ts"] > LAB_STALE_S:
        out["lab"] = (False, f"supervisor silent for {int(now - sup['ts'])} s (fleet down, hung or host asleep)")
    else:
        out["lab"] = (True, f"supervisor beat {int(now - sup['ts'])} s ago")
    for name in sorted(ROLES):
        r = rows.get(name)
        if not out["lab"][0]:
            out[f"agent:{name}"] = (None, "not judged while the supervisor is down")
        elif r is None:
            out[f"agent:{name}"] = (False, "no heartbeat")
        elif r.get("status") == "failed" or not r.get("ok"):
            out[f"agent:{name}"] = (False, f"failed: {(r.get('detail') or '')[:120]}")
        elif now - r["ts"] > (r.get("stale_after") or 300):
            out[f"agent:{name}"] = (False, f"heartbeat {int(now - r['ts'])} s old (hung)")
        elif every_of.get(name) and (r.get("last_ok_ts") or r.get("started_ts")) and \
                now - (r.get("last_ok_ts") or r["started_ts"]) > max(600, STALE_PASSES * every_of[name]):
            # a just-started agent gets one window for its first pass; a row with neither time is not judged by work
            ok = r.get("last_ok_ts")                     # a fresh heartbeat without work (research/LINUX_DRIFT.md)
            out[f"agent:{name}"] = (False, (f"no successful pass for {int(now - ok)} s" if ok else
                                            "no successful pass recorded") + f" (expected every {every_of[name]} s)")
        else:
            out[f"agent:{name}"] = (True, r.get("status") or "ok")
    return out


def _progress(con_path, now, sup):
    """Is research being done? Not judged while the fleet is down or younger than 2 h."""
    if not sup or sup.get("status") != "running":
        return (None, "not judged (fleet down)")
    con = _ro(con_path)
    if con is None:
        return (None, "not judged: no lab database")
    try:
        started = con.execute("SELECT MAX(ts) FROM events WHERE kind='system.running'").fetchone()[0] or now
        if now - started < 2 * 3600:
            return (None, "not judged (fleet up less than 2 h)")
        last = con.execute("SELECT MAX(ts) FROM events WHERE kind='job.done' AND COALESCE(json_extract(payload, "
                           "'$.kind'), '') NOT IN ('diagnose', 'scan_digest', 'scan_dossier', 'explore', "
                           "'explore_report', 'lane_report', 'lane_review', 'ingest')").fetchone()[0]
        # (non-decisional side jobs run daily; they must not hide an idle hypothesis pipeline)
        try:
            runnable, running = con.execute("SELECT COALESCE(SUM(status='queued' AND next_run<=?), 0), "
                                            "COALESCE(SUM(status='running'), 0) FROM jobs WHERE kind NOT IN "
                                            "('explore', 'explore_report', 'lane_report', 'lane_review', 'ingest')",
                                            (now,)).fetchone()
        except sqlite3.OperationalError:                 # no jobs table yet: nothing was ever queued
            runnable = running = 0
    finally:
        con.close()
    done = "no job finished yet" if last is None else f"last finished job {int((now - last) // 60)} min ago"
    if runnable == 0 and running == 0 and (last is None or now - last > IDLE_ALERT_S):
        return (False, f"no research work: {done} and nothing runnable or running "
                       "(see research.idle_reason in /api/kpis)")
    return (True, f"{done}, {running} running, {runnable} runnable")


def _active_ledgers(con):
    """Ledgers that should be marked hourly: approved strategies in PAPER_TRADING/PAUSED, an active shadow, an
    active forward test (amendments 3 and 7). Stopped or closed ledgers are not judged."""
    def latest(kinds, eid):
        r = con.execute(f"SELECT kind FROM events WHERE kind IN ({','.join('?' * len(kinds))}) AND exp_id=? "
                        "ORDER BY id DESC LIMIT 1", (*kinds, eid)).fetchone()
        return r[0] if r else None

    def state(eid):
        r = con.execute("SELECT to_state FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
        return r[0] if r else None
    out = []
    for (led,) in con.execute("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started'").fetchall():
        if led.startswith("FWD_"):
            ok = latest(("forward.approved", "forward.stopped"), led[4:]) == "forward.approved"
        elif led.startswith("LANE_"):                  # amendment 11
            ok = latest(("lane.started", "lane.retired"), led) == "lane.started"
        elif led.startswith("SHADOW_"):
            ok = latest(("shadow.approved", "shadow.stopped"), led[7:]) == "shadow.approved" \
                and state(led[7:]) == "OBSERVATION"
        else:
            ok = state(led) in ("PAPER_TRADING", "PAUSED")
        if ok:
            out.append(led)
    return out


class _ReadOnly:
    """The two read calls lab read models use (db.q / db.one), over the watcher's read-only connection."""
    def __init__(self, con):
        self.con = con

    def q(self, sql, *a):
        return self.con.execute(sql, a).fetchall()

    def one(self, sql, *a):
        return self.con.execute(sql, a).fetchone()


def _edge_note(con, active, now):
    """Non-decisional (amendment 9 section 4): ledgers live >= 14 full days whose daily net is more than 3 standard
    errors below the validation expectation. Only mentioned in the detail; never makes the component fail."""
    from lab import command
    db, low = _ReadOnly(con), []
    for led in active:
        try:
            if command.edge(db, led, now, expectation=False)["days"] < command.EDGE_WATCH_DAYS:
                continue                                  # no validate.json read before 14 days
            z = command.edge(db, led, now)["z"]
        except Exception:
            continue
        if z is not None and z < command.EDGE_WATCH_Z:
            low.append(f"{led} z={z:.1f}")
    return f"; edge below expectation (non-decisional, decides nothing): {', '.join(low)}" if low else ""


def _paper(con_path, now, sup):
    """Is every active simulated ledger marked hourly, and is none of them paused for more than a day? Ledgers far
    below their validation expectation are mentioned, never judged (amendment 9 section 4)."""
    if not sup or sup.get("status") != "running":
        return (None, "not judged (fleet down)")
    con = _ro(con_path)
    if con is None:
        return (None, "not judged: no lab database")
    try:
        started = con.execute("SELECT MAX(ts) FROM events WHERE kind='system.running'").fetchone()[0] or now
        active = _active_ledgers(con)
        if not active:
            return (None, "no active paper ledger")
        stale, long_paused, paused = [], [], []
        for led in active:
            last = con.execute("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", (led,)).fetchone()[0]
            if now - started > 1.5 * 3600 and (last is None or now - last > PAPER_MARK_MAX_S):
                stale.append(led)
            r = con.execute("SELECT action, ts FROM risk_events WHERE exp_id=? AND action IN ('PAUSE', 'CLEAR') "
                            "ORDER BY id DESC LIMIT 1", (led,)).fetchone()
            if r and r[0] == "PAUSE":
                (long_paused if now - r[1] > PAPER_PAUSE_MAX_S else paused).append(led)
        try:
            note = _edge_note(con, active, now)
        except Exception:                                 # the note must never change the paper verdict
            note = ""
    finally:
        con.close()
    if stale or long_paused:
        why = ([f"not marked for over {PAPER_MARK_MAX_S // 3600:.1f} h: {', '.join(stale)}"] if stale else []) + \
              ([f"paused for over a day: {', '.join(long_paused)}"] if long_paused else [])
        return (False, ("; ".join(why) + note)[:300])
    return (True, f"{len(active)} active ledgers marked hourly" + (f"; paused: {', '.join(paused)}" if paused else "")
            + note)


def check_collector(pm_db, now):
    """Up = a collector process runs from this checkout and data is fresh for the current study phase."""
    from research import pm_lp
    procs = _processes("research.pm_lp collect")
    try:
        con = _ro(pm_db)
        if con is None:
            return (False, "pm_lp database missing")
        try:
            d0 = con.execute("SELECT v FROM meta WHERE k='D0'").fetchone()
            last_snap = con.execute("SELECT MAX(t) FROM snaps").fetchone()[0]
            last_status = con.execute("SELECT MAX(t) FROM status").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as e:
        return (False, f"pm_lp database unreadable ({e!r}); collector {'pid ' + str(procs[0]) if procs else 'not running'}"
                       " - a hot journal left by a hard kill is rolled back when the collector next opens the database")
    if d0 is None:
        return (False, "pm_lp database has no D0")
    d0, day = int(d0[0]), int(now) // 86400
    if day > d0 + pm_lp.TAIL_END:
        return (True, "collection finished (after resolution tracking)")
    if not procs:
        return (False, "no collector process running")
    if day <= d0 + pm_lp.HOLD_DAYS[1]:
        age = now - (last_snap or 0)
        if age > COLLECTOR_STALE_S:
            return (False, f"collector pid {procs[0]} alive but last snapshot {int(age)} s old")
        return (True, f"pid {procs[0]}, last snapshot {int(age)} s ago")
    age = now - (last_status or 0)
    if age > STATUS_STALE_S:
        return (False, f"collector pid {procs[0]} alive but last status poll {int(age)} s old")
    return (True, f"pid {procs[0]}, resolution tracking, last status poll {int(age)} s ago")


def logind_inhibitors():
    """Active logind inhibitors (read-only call on the system bus; needs no authorisation)."""
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    rows = bus.call_sync("org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager",
                         "ListInhibitors", None, GLib.VariantType("(a(ssssuu))"), 0, 10_000, None).unpack()[0]
    return [{"what": w, "who": who, "why": why, "mode": m, "uid": u, "pid": p} for w, who, why, m, u, p in rows]


SLEEP_TARGETS = ("sleep.target", "suspend.target", "hibernate.target", "hybrid-sleep.target")


def sleep_masked():
    """Are all sleep targets masked in systemd (sleep disabled system-wide, also after a reboot)? Read-only call."""
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    return all(bus.call_sync("org.freedesktop.systemd1", "/org/freedesktop/systemd1",
                             "org.freedesktop.systemd1.Manager", "GetUnitFileState", GLib.Variant("(s)", (t,)),
                             GLib.VariantType("(s)"), 0, 10_000, None).unpack()[0].startswith("masked")
               for t in SLEEP_TARGETS)


def check_awake():
    """Is sleep impossible: sleep targets masked in systemd, or a logind block (research/LINUX_DRIFT.md:
    systemd-inhibit started on the desktop)? Not judged where neither can be asked."""
    try:
        if sleep_masked():
            return (True, "sleep disabled system-wide (systemd sleep targets masked)")
    except Exception:
        pass
    try:
        inh = logind_inhibitors()
    except Exception as e:
        return (None, f"logind not reachable ({type(e).__name__})")
    blocks = [i for i in inh if i["mode"] == "block" and "sleep" in i["what"].split(":")]
    ours = [i for i in blocks if i["who"] == "copybot"]
    if ours or blocks:
        i = (ours or blocks)[0]
        return (True, f"sleep blocked in logind by '{i['who']}' (pid {i['pid']})")
    return (False, "sleep is NOT blocked: run the systemd-inhibit line from research/LINUX_DRIFT.md on the desktop")


def check_dashboard(port):
    from lab.preflight import dashboard_running
    return (True, f"answers on 127.0.0.1:{port}") if dashboard_running(port) else \
        (False, f"no answer on 127.0.0.1:{port}")


PMCOV_MIN = 0.90                # research/pm_lp.py coverage: D1 needs >= 90 % snapshot coverage
PMCOV_AFTER_S = 2 * 3600        # judged after 2 h of the UTC day (fewer minutes say too little)
_PMCOV = {}                     # (pm_db, hour) -> result: the query runs at most once an hour per database


def check_pm_coverage(pm_db, now):
    """research/LINUX_DRIFT.md 2026-10-23 (the user's yes): today's running snapshot coverage = snapshots today /
    (markets in today's panel x minutes since 00:00 UTC), as research/pm_lp.py coverage counts it; below 90 % after
    2 h of the day is a fault. Read-only, at most once an hour; yesterday's full day is shown in the detail."""
    from research import pm_lp
    key = (pm_db, int(now) // 3600)
    if key in _PMCOV:
        return _PMCOV[key]
    con = _ro(pm_db)
    if con is None:
        return (None, "not judged: pm_lp database missing")
    try:
        d0 = con.execute("SELECT v FROM meta WHERE k='D0'").fetchone()
        day = int(now) // 86400
        if d0 is None or day > int(d0[0]) + pm_lp.HOLD_DAYS[1]:
            res = (None, "not judged: no snapshot phase today")
        else:
            def cov(d, minutes):
                q = con.execute("SELECT COUNT(*) FROM snaps s JOIN panel p ON p.cid=s.cid AND p.day=s.t/86400 "
                                "WHERE p.day=? AND s.t<?", (d, int(now))).fetchone()[0]
                md = con.execute("SELECT COUNT(*) FROM panel WHERE day=?", (d,)).fetchone()[0]
                return (q / (md * minutes)) if md and minutes else None
            mins = (now - day * 86400) / 60
            today, yday = cov(day, mins), cov(day - 1, 1440)
            prev = "" if yday is None else f"; yesterday {yday:.1%}"
            if today is None:
                res = (None, "not judged: no panel for today yet" + prev)
            elif now - day * 86400 < PMCOV_AFTER_S:
                res = (True, f"today {today:.1%} so far (judged from 02:00 UTC){prev}")
            elif today < PMCOV_MIN:
                res = (False, f"snapshot coverage today {today:.1%} < {PMCOV_MIN:.0%} (D1){prev}")
            else:
                res = (True, f"snapshot coverage today {today:.1%}{prev}")
    finally:
        con.close()
    _PMCOV.clear()
    _PMCOV[key] = res
    return res


SCAN_STALE_S = 70 * 60          # the hourly scan runs at HH:02 UTC (research/LINUX_DRIFT.md 2026-10-25)
WEEKEND_SCAN_BY_S = 12 * 60     # Sat/Sun UTC: the hour's scan must exist by HH:12 (K1/K2, PROTOCOL_V3 21y)
K3_ROUND_S, K3_DUE_S, K3_UNTIL_S = 4 * 3600, 30 * 60, 35 * 60      # amendment 22: selection or missed from S - 30 min


def check_scanner(db_path, now, lab_ok):
    """The hourly scan and K3's rounds. Judged only while the lab is up and its fleet has run for 5 min; an unreadable
    database is down (fail-closed), never ok."""
    if not lab_ok:
        return (None, "not judged (lab down)")
    try:
        con = _ro(db_path)
        if con is None:
            return (False, "lab database missing")
        try:
            started = con.execute("SELECT MAX(ts) FROM events WHERE kind='system.running'").fetchone()[0]
            last = con.execute("SELECT MAX(ts) FROM observations WHERE detector='abnormal_move/1' AND metric='z_1h'"
                               ).fetchone()[0]
            base = int(now) - int(now) % K3_ROUND_S
            due = [S for S in (base, base + K3_ROUND_S) if S - K3_DUE_S <= now <= S + K3_UNTIL_S]
            k3_missing = [S for S in due if not con.execute(
                "SELECT 1 FROM observations WHERE detector='k3/1' AND metric IN ('selection', 'missed') AND value=?",
                (S,)).fetchone()]
        finally:
            con.close()
    except sqlite3.Error as e:
        return (False, f"lab database unreadable: {e!r}"[:200])
    if started is None or now - started < 300:
        return (None, "not judged (fleet up less than 5 min)")
    why = []
    if last is None or now - last > SCAN_STALE_S:
        why.append("no hourly scan yet" if last is None else f"last hourly scan {int((now - last) // 60)} min ago")
    hour = int(now) - int(now) % 3600
    if datetime.fromtimestamp(now, timezone.utc).weekday() >= 5 and now - hour >= WEEKEND_SCAN_BY_S \
            and (last is None or last < hour):
        why.append("weekend: this hour's HH:02 scan is missing (K1/K2 hour lost)")
    for S in k3_missing:
        why.append(f"K3 round {datetime.fromtimestamp(S, timezone.utc).strftime('%H:%M')} UTC has no selection or missed")
    if why:
        return (False, "; ".join(why))
    return (True, f"last hourly scan {int((now - last) // 60)} min ago")


def check(db_path=DEFAULT_DB, pm_db=PM_DB, port=8770, now=None):
    """Every probe is isolated: one that raises marks its own component(s) down and the others are still judged."""
    from lab.fleet import ROLES
    now = now or time.time()
    out = {}
    try:
        out.update(check_lab(db_path, now))
    except Exception as e:
        out["lab"] = (False, f"check failed: {e!r}"[:300])
        out["lab_state"] = (None, "not judged: lab check failed")
        out.update({f"agent:{n}": (None, "not judged: lab check failed") for n in ROLES})
    try:
        out["scanner"] = check_scanner(db_path, now, out.get("lab", (None,))[0])
    except Exception as e:
        out["scanner"] = (False, f"check failed: {e!r}"[:300])
    for comp, fn in (("dashboard", lambda: check_dashboard(port)), ("collector", lambda: check_collector(pm_db, now)),
                     ("pm_coverage", lambda: check_pm_coverage(pm_db, now)), ("awake", check_awake)):
        try:
            out[comp] = fn()
        except Exception as e:
            out[comp] = (False, f"check failed: {e!r}"[:300])
    return {k: {"ok": ok if ok is None else bool(ok), "detail": d} for k, (ok, d) in out.items()}


def notify(title, body):
    """Desktop notification on the local session. Returns whether it was delivered; the log line is the record.
    COPYBOT_WATCH_NOTIFY=0 turns it off (isolated tests)."""
    if os.environ.get("COPYBOT_WATCH_NOTIFY") == "0" or not shutil.which("notify-send"):
        return False
    env = dict(os.environ)
    bus = f"/run/user/{os.getuid()}/bus" if hasattr(os, "getuid") else None
    if "DBUS_SESSION_BUS_ADDRESS" not in env and bus and os.path.exists(bus):
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    try:
        return subprocess.run(["notify-send", "-u", "critical", "-a", "Copybot", title, body], env=env,
                              timeout=10, capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class Watcher:
    def __init__(self, db_path=DEFAULT_DB, pm_db=PM_DB, port=8770, log_dir=None, status_file=STATUS_FILE,
                 heartbeat_file=HEARTBEAT_FILE, notifier=notify, clock=time.time, suspends=suspend_count,
                 slept=sleep_offset, booted=boot_time, out=print):
        self.db_path, self.pm_db, self.port, self.notifier, self.clock = db_path, pm_db, port, notifier, clock
        self.log_dir = log_dir or os.path.join(os.path.dirname(os.path.abspath(db_path)), "logs")
        self.status_file, self.heartbeat_file, self.out = status_file, heartbeat_file, out
        self.last_ts = None                         # the previous watcher's last tick (status file), if any
        self.state = self._load()                   # component -> {"ok", "since", "last_alert", "detail"}
        self.booted, self.downtime_checked = booted, False
        self.last_alive = 0.0
        self.suspends, self.slept = suspends, slept
        self.suspend_seen, self.slept_seen = suspends(), slept()

    def _load(self):
        try:
            with open(self.status_file, encoding="utf-8") as f:
                st = json.load(f)
            self.last_ts = st.get("ts") if isinstance(st.get("ts"), (int, float)) else None
            return {k: v for k, v in st.get("components", {}).items()
                    if isinstance(v, dict) and v.get("ok") in (True, False)}
        except (OSError, ValueError):
            return {}

    def _alert(self, kind, comp, detail, now):
        title = {"down": f"Copybot: {comp} NEDE", "still_down": f"Copybot: {comp} stadig nede",
                 "recovered": f"Copybot: {comp} virker igen",
                 "suspended": "Copybot: maskinen har været i dvale",
                 "downtime": "Copybot: overvågningen var nede"}[kind]
        delivered = bool(self.notifier(title, detail))
        ops.log_json("watch", kind, self.log_dir, component=comp, detail=detail, notified=delivered)
        self.out(f"{datetime.fromtimestamp(now, timezone.utc).isoformat(timespec='seconds')} {title}: {detail}"
                 + ("" if delivered else "  [no desktop notification delivered]"))

    def _host(self, now):
        n, off = self.suspends(), self.slept()
        why = []
        if n is not None and self.suspend_seen is not None and n > self.suspend_seen:
            why.append(f"{n - self.suspend_seen} suspend(s)")
        if off is not None and self.slept_seen is not None and off - self.slept_seen > SLEEP_JUMP_S:
            why.append(f"{int(off - self.slept_seen)} s asleep")
        if why:
            self._alert("suspended", "host", ", ".join(why) + " since the last check: every process was frozen; "
                        "pm_lp snapshots and lab heartbeats have a gap", now)
        self.suspend_seen = n if n is not None else self.suspend_seen
        self.slept_seen = off if off is not None else self.slept_seen

    def _downtime(self, now):
        """At the first tick: the previous watcher's last tick is older than DOWNTIME_S, or the host booted after it
        (a reboot, a kill, a crash). Every process was down with it: pm_lp snapshots, lab heartbeats and paper marks
        have a gap that nobody saw."""
        self.downtime_checked = True
        if self.last_ts is None:
            return
        b = self.booted()
        rebooted = b is not None and b > self.last_ts
        if rebooted or now - self.last_ts > DOWNTIME_S:
            iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")   # noqa: E731
            self._alert("downtime", "host", f"no watcher tick from {iso(self.last_ts)} to {iso(now)} "
                        f"({int(now - self.last_ts) // 60} min)" + (f"; the host booted at {iso(b)}" if rebooted
                                                                    else "") +
                        ": pm_lp snapshots, lab heartbeats and paper marks have a gap in that time", now)

    def tick(self):
        now = self.clock()
        if not self.downtime_checked:
            self._downtime(now)
        self._host(now)
        res = check(self.db_path, self.pm_db, self.port, now)
        for comp, r in res.items():
            if r["ok"] is None:                       # not judged: keep what we knew (no false 'recovered')
                continue
            prev = self.state.get(comp)
            if prev is None:
                self.state[comp] = {"ok": r["ok"], "since": now, "last_alert": 0.0}
                if not r["ok"]:
                    self._alert("down", comp, r["detail"], now)
                    self.state[comp]["last_alert"] = now
            elif prev["ok"] and not r["ok"]:
                self.state[comp] = {"ok": False, "since": now, "last_alert": now}
                self._alert("down", comp, r["detail"], now)
            elif not prev["ok"] and r["ok"]:
                self._alert("recovered", comp, f"{r['detail']} (was down {int(now - prev['since'])} s)", now)
                self.state[comp] = {"ok": True, "since": now, "last_alert": 0.0}
            elif not r["ok"] and now - prev.get("last_alert", 0) >= REMIND_OVERRIDE.get(comp, REMIND_S):
                self._alert("still_down", comp, f"{r['detail']} (down {int(now - prev['since'])} s)", now)
                prev["last_alert"] = now
            self.state[comp]["detail"] = r["detail"]
        if now - self.last_alive >= REMIND_S:
            ops.log_json("watch", "alive", self.log_dir,
                         down=sorted(k for k, v in self.state.items() if not v["ok"]))
            self.last_alive = now
        tmp = self.status_file + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "utc": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
                       "pid": os.getpid(), "components": self.state}, f, indent=1)
        os.replace(tmp, self.status_file)
        with open(self.heartbeat_file, "a", encoding="utf-8"):
            os.utime(self.heartbeat_file, None)
        return res


def summary(res):
    """Lines for --once: lab-level components, then agents (only the bad or unknown ones are listed)."""
    lines = []
    for k in ("lab", "lab_state", "progress", "paper", "dashboard", "collector", "pm_coverage", "awake"):
        if k in res:
            ok = res[k]["ok"]
            lines.append(f"  [{'OK ' if ok else '?? ' if ok is None else 'NO '}] {k}: {res[k]['detail']}")
    agents = {k: v for k, v in res.items() if k.startswith("agent:")}
    bad = {k: v for k, v in agents.items() if v["ok"] is False}
    unknown = [k for k, v in agents.items() if v["ok"] is None]
    if bad:
        lines += [f"  [NO ] {k}: {v['detail']}" for k, v in sorted(bad.items())]
    elif unknown:
        lines.append(f"  [?? ] agents: {len(unknown)} not judged ({agents[unknown[0]]['detail']})")
    else:
        lines.append(f"  [OK ] agents: {len(agents)} healthy")
    return lines


def main(db_path=DEFAULT_DB, port=8770, once=False, interval=30.0, out=print):
    if once:
        res = check(db_path, PM_DB, port)
        for line in summary(res):
            out(line)
        return 0 if all(r["ok"] for k, r in res.items() if r["ok"] is not None and k != "progress") \
            and res["lab"]["ok"] else 1                   # an idle lab is reported, but it is not an outage
    from lab.supervisor import AlreadyRunning, acquire_lock, release_lock
    try:
        lock = acquire_lock(LOCK_FILE)
    except AlreadyRunning:
        out("refused: another watcher holds data/lab/watch.lock")
        return 3
    try:
        w = Watcher(db_path, PM_DB, port, out=out)
        ops.log_json("watch", "started", w.log_dir, pid=os.getpid(), interval=interval)
        out(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} watcher started (every {interval:.0f} s; "
            "alerts in data/lab/logs/watch-*.jsonl, here, and as desktop notifications; never restarts anything)")
        while True:
            try:
                w.tick()
            except Exception as e:                       # e.g. disk full: say so where it can still be seen
                try:
                    ops.log_json("watch", "check_error", w.log_dir, error=repr(e)[:300])
                except Exception:
                    pass
                out(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} watcher tick failed: {e!r}")
            time.sleep(interval)
    finally:
        release_lock(lock)
