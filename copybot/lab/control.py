"""Fleet control state, derived from the append-only event log (so it survives restarts and is auditable).

- paused:  latest of system.paused / system.resumed is "paused"  -> agents claim no new jobs
- stop:    a system.stop_requested after the latest system.running, not yet followed by system.stopped
- hold:    latest of system.resource_hold / system.resource_ok is "hold" (RAM/disk below limits) -> no new jobs
"""
from __future__ import annotations

import ctypes
import os

from lab import ops

RAM_MIN_FREE = 0.5 * 1024 ** 3        # ESTIMATE: a job holds one window of 8 symbols x hourly bars (tens of MB)


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


def ram():
    """Free and total physical memory in bytes (Windows API; None elsewhere)."""
    if os.name != "nt":
        return None
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tot", ctypes.c_ulonglong),
                    ("avail", ctypes.c_ulonglong), ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong),
                    ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
    m = M()
    m.l = ctypes.sizeof(M)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return None
    return {"total": m.tot, "free": m.avail, "load_pct": m.load}


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
