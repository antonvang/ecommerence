"""Startup preflight (START_LAB.sh): refuse to start the lab unless it can run safely. Read-only: it writes nothing to
the registry, so a refused start leaves no trace in the S7 window.

Checks: Python version, database present with intact hash chains, no other supervisor holding the lock, dashboard
port free, disk and RAM above their floors, market cache present, and the frozen parameters of every experiment that
can still be evaluated or traded match their recorded SHA-256 (missing or changed files are never regenerated).
"""
from __future__ import annotations

import os
import socket
import sys

from lab import control, pipeline, registry
from lab.db import DB, HERE
from lab.supervisor import AlreadyRunning, acquire_lock, release_lock

NEEDS_FROZEN = ("VALIDATION", "VALIDATED", "OBSERVATION", "PAPER_TRADING", "PAUSED")


def _port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def checks(db_path, port=8770):
    out = []
    add = lambda name, ok, detail="": out.append((name, bool(ok), detail))  # noqa: E731
    add("python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0])
    if not os.path.exists(db_path):
        add("lab database present", False, f"{os.path.relpath(db_path, HERE)} missing (research/LINUX_FLYT.md)")
        return out
    lock_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "lab.lock")
    try:
        release_lock(acquire_lock(lock_path))
        add("no other lab running", True)
    except AlreadyRunning:
        add("no other lab running", False, "a supervisor already holds lab.lock: the lab is running")
    add("dashboard port free", _port_free(port), f"127.0.0.1:{port}")
    db = DB(db_path)
    try:
        chains, triggers = db.verify()
        broken = {t: b for t, (_, b) in chains.items() if b is not None}
        add("hash chains intact", not broken and triggers, broken or ("triggers missing" if not triggers else ""))
        res = control.resources(os.path.dirname(os.path.abspath(db_path)))
        add("disk above floor", res["disk"]["free_ok"], f"{res['disk']['free'] / 2 ** 30:.1f} GB free")
        ram = res["ram"]
        add("RAM above floor", ram is None or ram["free"] >= control.RAM_MIN_FREE,
            f"{ram['free'] / 2 ** 30:.1f} GB free" if ram else "not measurable on this platform")
        from lab.engine import data
        add("market cache present", os.path.isdir(data.CACHE), os.path.relpath(data.CACHE, HERE))
        bad = []
        for x in registry.status(db):
            if x["state"] in NEEDS_FROZEN and x["exp_id"].startswith("E_"):
                try:
                    pipeline.frozen_variant(db, x["exp_id"])
                except pipeline.ArtifactError as e:
                    bad.append(str(e))
                except (KeyError, IndexError, ValueError) as e:
                    bad.append(f"{x['exp_id']}: unreadable frozen parameters ({e!r})")
        add("frozen parameters verified", not bad, "; ".join(bad)[:400])
    finally:
        db.close()
    return out


def main(db_path, port=8770, out=print):
    rows = checks(db_path, port)
    for name, ok, detail in rows:
        out(f"  [{'OK ' if ok else 'NO '}] {name}" + (f": {detail}" if detail else ""))
    ok = all(r[1] for r in rows)
    out("PREFLIGHT OK" if ok else "PREFLIGHT FAILED: the lab was not started")
    return 0 if ok else 1

