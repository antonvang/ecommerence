"""Fleet control state, derived from the append-only event log (so it survives restarts and is auditable).

- paused:  latest of system.paused / system.resumed is "paused"  -> agents claim no new jobs
- stop:    a system.stop_requested after the latest system.running, not yet followed by system.stopped
- hold:    latest of system.resource_hold / system.resource_ok is "hold" (RAM/disk below limits) -> no new jobs
"""
from __future__ import annotations

import ctypes
import json
import os
import signal
import sqlite3
import time

from lab import ops

RAM_MIN_FREE = 0.5 * 1024 ** 3        # ESTIMATE: a job holds one window of 8 symbols x hourly bars (tens of MB)
STOP_LOCK_WAIT_S = 5                  # one attempt to take the database write lock for the stop request
STOP_MAX_WAIT_S = 60                  # `lab stop` gives up on a busy-but-alive fleet after this long
TERM_GRACE_S = 20                     # after SIGTERM the supervisor shuts down itself; SIGKILL only after this
FRESH_S = 30                          # = promotion.SUPERVISOR_FRESH_S (the supervisor beats every second)


def _latest(db, kinds):
    q = f"SELECT kind, id FROM events WHERE kind IN ({','.join('?' * len(kinds))}) ORDER BY id DESC LIMIT 1"
    r = db.one(q, *kinds)
    return (r["kind"], r["id"]) if r else (None, 0)


def state(db):
    pk, _ = _latest(db, ("system.paused", "system.resumed"))
    hk, _ = _latest(db, ("system.resource_hold", "system.resource_ok"))
    _, run_id = _latest(db, ("system.running",))
    _, stop_id = _latest(db, ("system.stop_requested",))
    _, stopped_id = _latest(db, ("system.stopped",))
    return {"paused": pk == "system.paused", "hold": hk == "system.resource_hold",
            "stop": stop_id > run_id > 0 and not stopped_id > stop_id}      # pending until the supervisor has stopped


def pause(db, actor, reason):
    if state(db)["paused"]:
        return False
    db.event("system.paused", actor, None, {"reason": reason})
    return True


def resume(db, actor, reason):
    if not state(db)["paused"]:
        return False
    db.event("system.resumed", actor, None, {"reason": reason})
    return True


def request_stop(db, actor, reason):
    if state(db)["stop"]:
        return False
    db.event("system.stop_requested", actor, None, {"reason": reason})
    return True


def _proc(pid):
    """(state letter, argv) of a live process from /proc, or None (gone, or no /proc as on Windows)."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            st = f.read().rsplit(")", 1)[1].split()[0]
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except (OSError, IndexError):
        return None
    return st, argv


def _is_supervisor(argv):
    return "lab" in argv and ("fleet" in argv or "supervise" in argv)


def supervisor_pid(db):
    """pid of the running supervisor (from its latest system.running event, checked against the live process)."""
    r = db.one("SELECT payload FROM events WHERE kind='system.running' ORDER BY id DESC LIMIT 1")
    pid = (json.loads(r["payload"] or "{}").get("pid") if r else None)
    p = _proc(pid) if pid else None
    return pid if p and p[0] != "Z" and _is_supervisor(p[1]) else None


def _beat_age(db):
    r = db.one("SELECT ts, status FROM heartbeats WHERE worker='supervisor'")
    return None if r is None or r["status"] == "stopped" else time.time() - r["ts"]


def _children(pid):
    kids = []
    for d in os.listdir("/proc") if os.path.isdir("/proc") else ():
        if d.isdigit():
            try:
                with open(f"/proc/{d}/stat") as f:
                    if int(f.read().rsplit(")", 1)[1].split()[1]) == pid:
                        kids.append(int(d))
            except (OSError, IndexError, ValueError):
                pass
    return kids


def _gone(pid, within):
    end = time.time() + within
    while True:
        p = _proc(pid)
        if p is None or p[0] == "Z":
            return True
        if time.time() >= end:
            return False
        time.sleep(0.2)


def terminate(pid, grace=TERM_GRACE_S):
    """End a hung supervisor: SIGTERM + SIGCONT (a frozen process resumes and shuts down gracefully), SIGKILL
    after `grace` s, then its job processes, which would otherwise finish and write for a dead fleet."""
    kids = _children(pid)
    os.kill(pid, signal.SIGTERM)
    os.kill(pid, signal.SIGCONT)
    how = "SIGTERM"
    if not _gone(pid, grace):
        os.kill(pid, signal.SIGKILL)
        _gone(pid, 5)
        how = "SIGKILL"
    for k in kids:
        p = _proc(k)
        if p and p[0] != "Z" and any("multiprocessing" in a for a in p[1]):
            os.kill(k, signal.SIGKILL)
    return how


def stop(db, actor, reason, force=False, out=print, lock_wait=STOP_LOCK_WAIT_S, max_wait=STOP_MAX_WAIT_S,
         grace=TERM_GRACE_S):
    """`lab stop`: record a graceful stop request. Never waits on a frozen fleet: a fleet that holds the database
    write lock or has a stale heartbeat cannot read the request, so it is reported at once (exit 3), and ended
    with force=True. Returns the exit code."""
    db.con.execute(f"PRAGMA busy_timeout={int(lock_wait * 1000)}")
    t0, recorded, locked = time.time(), False, False
    while True:
        try:
            recorded, locked = request_stop(db, actor, reason), False
            break
        except sqlite3.OperationalError as e:
            if "locked" not in str(e):
                raise
            locked = True
            age = _beat_age(db)
            if age is None or age > FRESH_S or time.time() - t0 >= max_wait:
                break
            out(f"stop: database busy, fleet heartbeat {age:.0f} s old; waiting ...")
    pid, age = supervisor_pid(db), _beat_age(db)
    hung = pid is not None and (locked or (age is not None and age > FRESH_S))
    if not hung:
        if locked:
            out("stop: NOT recorded: another process holds the database write lock and no running fleet was found")
            return 3
        out(f"stop: {'recorded' if recorded else 'already in that state (no-op)'}")
        return 0
    st = _proc(pid)[0]
    why = "holds the database write lock" if locked else f"has not beaten for {age:.0f} s"
    out(f"stop: the fleet (pid {pid}, process state {st}{' = stopped/frozen' if st == 'T' else ''}) does not "
        f"respond: it {why}, so it cannot read a stop request.")
    if not force:
        out(f"  {'The request is recorded, but nothing will act on it. ' if recorded else ''}"
            f"End the fleet with: python3 -m lab stop --force --reason \"...\"")
        return 3
    how = terminate(pid, grace)
    db.event("system.stop_forced", actor, None, {"pid": pid, "reason": reason, "signal": how, "why": why})
    out(f"stop: the fleet (pid {pid}) is ended with {how}"
        + ("" if how == "SIGTERM" else "; START_LAB.sh logs it as an unexpected stop and the dashboard keeps running"))
    return 0


def ram():
    """Free and total physical memory in bytes (Windows API, Linux /proc/meminfo; None elsewhere)."""
    if os.name != "nt":
        return _ram_linux()
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tot", ctypes.c_ulonglong),
                    ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                    ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
    m = M()
    m.l = ctypes.sizeof(M)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return None
    return {"total": m.tot, "free": m.avail, "load_pct": m.load}


def _ram_linux(path="/proc/meminfo"):
    try:
        with open(path) as f:
            kb = {k.strip(): int(v.split()[0]) for k, v in (line.split(":", 1) for line in f if ":" in line)}
        tot, free = kb["MemTotal"] * 1024, kb["MemAvailable"] * 1024
    except (OSError, KeyError, ValueError):
        return None
    return {"total": tot, "free": free, "load_pct": round(100 * (1 - free / tot)) if tot else None}


def resources(path=None):
    d = ops.disk(path) if path else ops.disk()
    r = ram()
    ok = d["free_ok"] and (r is None or r["free"] >= RAM_MIN_FREE)
    return {"disk": d, "ram": r, "ram_min_free": RAM_MIN_FREE, "ok": ok}


def update_hold(db, actor, res):
    """Record a hold / release only when the state changes."""
    held = state(db)["hold"]
    if not res["ok"] and not held:
        db.event("system.resource_hold", actor, None, {"disk_free": res["disk"]["free"],
                                                       "ram_free": (res["ram"] or {}).get("free")})
    elif res["ok"] and held:
        db.event("system.resource_ok", actor, None, {"disk_free": res["disk"]["free"],
                                                     "ram_free": (res["ram"] or {}).get("free")})
