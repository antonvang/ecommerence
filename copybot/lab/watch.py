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
REMIND_OVERRIDE = {"progress": 24 * 3600}   # idleness is reported once a day, not every hour
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
    from lab.fleet import ROLES
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
        last = con.execute("SELECT MAX(ts) FROM events WHERE kind='job.done'").fetchone()[0]
        try:
            runnable, running = con.execute("SELECT COALESCE(SUM(status='queued' AND next_run<=?), 0), "
                                            "COALESCE(SUM(status='running'), 0) FROM jobs", (now,)).fetchone()
        except sqlite3.OperationalError:                 # no jobs table yet: nothing was ever queued
            runnable = running = 0
    finally:
        con.close()
    done = "no job finished yet" if last is None else f"last finished job {int((now - last) // 60)} min ago"
    if runnable == 0 and running == 0 and (last is None or now - last > IDLE_ALERT_S):
        return (False, f"no research work: {done} and nothing runnable or running "
                       "(see research.idle_reason in /api/kpis)")
    return (True, f"{done}, {running} running, {runnable} runnable")


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
    for comp, fn in (("dashboard", lambda: check_dashboard(port)), ("collector", lambda: check_collector(pm_db, now)),
                     ("awake", check_awake)):
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
                 slept=sleep_offset, out=print):
        self.db_path, self.pm_db, self.port, self.notifier, self.clock = db_path, pm_db, port, notifier, clock
        self.log_dir = log_dir or os.path.join(os.path.dirname(os.path.abspath(db_path)), "logs")
        self.status_file, self.heartbeat_file, self.out = status_file, heartbeat_file, out
        self.state = self._load()                   # component -> {"ok", "since", "last_alert", "detail"}
        self.last_alive = 0.0
        self.suspends, self.slept = suspends, slept
        self.suspend_seen, self.slept_seen = suspends(), slept()

    def _load(self):
        try:
            with open(self.status_file, encoding="utf-8") as f:
                return {k: v for k, v in json.load(f).get("components", {}).items()
                        if isinstance(v, dict) and v.get("ok") in (True, False)}
        except (OSError, ValueError):
            return {}

    def _alert(self, kind, comp, detail, now):
        title = {"down": f"Copybot: {comp} NEDE", "still_down": f"Copybot: {comp} stadig nede",
                 "recovered": f"Copybot: {comp} virker igen",
                 "suspended": "Copybot: maskinen har været i dvale"}[kind]
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

    def tick(self):
        now = self.clock()
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
    for k in ("lab", "lab_state", "progress", "dashboard", "collector", "awake"):
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
