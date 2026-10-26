"""Post-deploy check (`python3 -m lab deploy-check`): one read-only command that says whether a deploy landed.

Rows (name, ok, detail), like the preflight: the dashboard reports the expected commit, the dashboard endpoints answer,
the fleet, dashboard, watcher and pm_lp collector processes run (a `watch --once` check is not the watcher, and the
watcher's heartbeat file must be at most 2 minutes old and newer than the host's boot), the last start printed PREFLIGHT OK, the pm_lp
collector could restart from the checkout, no tracked file is empty, the checkout has no local changes, FAIL_CLOSED
is off and every agent is active. It sends no signal, writes nothing and never touches the collector.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request

from lab.db import HERE

ENDPOINTS = ("kpis", "lanes", "coverage", "experiments", "overview")
PROCS = {"fleet": "python3 -m lab fleet", "dashboard": "python3 -m lab web", "watcher": "python3 -m lab watch",
         "pm_lp collector": "research.pm_lp collect"}


def _get(port, path, timeout):
    t = time.time()
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/{path}", timeout=timeout) as r:
        body = r.read()
        return r.status, body, time.time() - t


def _cmdlines():
    out = []
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    out.append(f.read().replace(b"\0", b" ").decode(errors="replace").strip())
            except OSError:
                continue
    return out


def _git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=60).stdout


def last_preflight(log_path):
    """The last PREFLIGHT verdict line of the start log (read as bytes: the log may hold NUL bytes), or None."""
    try:
        with open(log_path, "rb") as f:
            f.seek(max(0, os.path.getsize(log_path) - 200_000))
            text = f.read().decode(errors="replace")
    except OSError:
        return None
    lines = [x.strip() for x in text.splitlines() if x.strip().startswith("PREFLIGHT")]
    return lines[-1] if lines else None


WATCHER_BEAT_S = 120                                         # the watcher touches its heartbeat every 30 s


def watcher_beat(root, now=None, boot=None):
    """(ok, detail) for data/lab/watch.heartbeat: at most WATCHER_BEAT_S old and newer than the host's boot."""
    from lab.watch import boot_time
    now = time.time() if now is None else now
    boot = boot_time() if boot is None else boot
    try:
        beat = os.path.getmtime(os.path.join(root, "data", "lab", "watch.heartbeat"))
    except OSError:
        return False, "no data/lab/watch.heartbeat"
    if now - beat > WATCHER_BEAT_S:
        return False, f"heartbeat {int(now - beat)} s old"
    if boot is not None and boot <= now and beat < boot:
        return False, "no heartbeat since the host booted"
    return True, f"heartbeat {int(now - beat)} s ago"


def checks(root=HERE, port=8770, commit=None, timeout=120, procs=None, get=None, git=_git, restart=None, wait_s=90,
           sleep=time.sleep, beat=None):
    from lab import preflight
    out = []
    add = lambda name, ok, detail="": out.append((name, bool(ok), detail))  # noqa: E731
    get = get or (lambda path: _get(port, path, timeout))
    repo = os.path.dirname(os.path.abspath(root))
    head = git(repo, "rev-parse", "--short", "HEAD").strip()
    want = commit or head
    kpis = None
    for e in ENDPOINTS:
        try:
            status, body, took = get(e)
            add(f"/api/{e}", status == 200, f"{status} in {took:.1f} s")
            if e == "kpis":
                kpis = json.loads(body)
        except Exception as ex:                             # noqa: BLE001 - reported, not raised
            add(f"/api/{e}", False, repr(ex)[:200])
    dep = ((kpis or {}).get("deploy") or {}).get("commit")
    add("dashboard runs the expected commit", dep and want and (dep.startswith(want) or want.startswith(dep)),
        f"dashboard {dep}, expected {want} (checkout HEAD {head})")
    waited = 0
    while kpis is not None and kpis.get("agents_active") != kpis.get("agents_total") and waited < wait_s:
        sleep(5)                                            # a fresh fleet starts its agents within a minute
        waited += 5
        try:
            kpis = json.loads(get("kpis")[1])
        except Exception:                                   # noqa: BLE001 - judged below on the last answer
            pass
    if kpis is not None:
        add("FAIL_CLOSED off", kpis.get("fail_closed") is False, f"fail_closed={kpis.get('fail_closed')}")
        add("all agents active", kpis.get("agents_active") == kpis.get("agents_total"),
            f"{kpis.get('agents_active')} of {kpis.get('agents_total')}" + (f" (after {waited} s)" if waited else ""))
    lines = _cmdlines() if procs is None else procs
    for name, pat in PROCS.items():
        n = sum(1 for c in lines if pat in c and not (name == "watcher" and "--once" in c))
        add(f"{name} running", n >= 1, f"{n} process(es)")
    add("watcher heartbeat fresh", *(beat or watcher_beat)(root))
    pf = last_preflight(os.path.join(root, "data", "lab", "start.log"))
    add("last start printed PREFLIGHT OK", pf == "PREFLIGHT OK", pf or "no PREFLIGHT line in data/lab/start.log")
    add("pm_lp collector could restart", *(restart or preflight.collector_restart)(root))
    empty = [f for f in git(repo, "ls-files", "copybot").splitlines()
             if os.path.isfile(os.path.join(repo, f)) and os.path.getsize(os.path.join(repo, f)) == 0]
    add("no tracked file is empty", not empty, ", ".join(empty[:10]))
    dirty = [x for x in git(repo, "status", "--porcelain", "--untracked-files=no").splitlines() if x.strip()]
    add("checkout has no local changes", not dirty, "; ".join(dirty[:10]))
    return out


def main(root=HERE, port=8770, commit=None, out=print, **kw):
    rows = checks(root, port, commit, **kw)
    for name, ok, detail in rows:
        out(f"  [{'OK ' if ok else 'NO '}] {name}" + (f": {detail}" if detail else ""))
    ok = all(r[1] for r in rows)
    out("DEPLOY OK" if ok else "DEPLOY CHECK FAILED")
    return 0 if ok else 1
