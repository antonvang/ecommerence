"""Operations helpers: structured JSON-lines logs, disk-space checks and file freshness of external processes.

Logs go to data/lab/logs/<name>-YYYYMMDD.jsonl (one object per line, UTC timestamps). They complement, never replace,
the hash-chained event log in the registry.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime, timezone

from lab.db import HERE

LOG_DIR = os.path.join(HERE, "data", "lab", "logs")
DISK_MIN_FREE_BYTES = 2 * 1024 ** 3          # below this the supervisor fails the lab closed
_lock = threading.Lock()

# processes that run outside the lab; their freshness is read from file modification times only (no file is opened)
EXTERNAL_FILES = {
    "X01_pm_lp_v1": ("pm_lp_v1 collector", ("data/research/pm_lp/pm_lp.db-wal", "data/research/pm_lp/pm_lp.db")),
    "X02_copybot_paper": ("copy-bot paper process", ("data/paper.db-wal", "data/paper.db")),
    "X03_funding_live_v0": ("funding live paper test", ("data/funding.db-wal", "data/funding.db")),
    "W_watch": ("uafhængig overvågning (lab watch)", ("data/lab/watch.heartbeat",)),
}


def log_json(name, kind, log_dir=LOG_DIR, **fields):
    os.makedirs(log_dir, exist_ok=True)
    now = time.time()
    rec = {"ts": round(now, 3), "utc": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
           "kind": kind, **fields}
    path = os.path.join(log_dir, f"{name}-{datetime.fromtimestamp(now, timezone.utc):%Y%m%d}.jsonl")
    with _lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return path


def disk(path=HERE):
    u = shutil.disk_usage(path)
    return {"total": u.total, "used": u.used, "free": u.free, "free_ok": u.free >= DISK_MIN_FREE_BYTES,
            "min_free": DISK_MIN_FREE_BYTES}


def file_age(rel_paths, now=None):
    """Seconds since the newest of the given files was last written (None if none exist)."""
    now = now or time.time()
    m = [os.path.getmtime(os.path.join(HERE, p)) for p in rel_paths if os.path.exists(os.path.join(HERE, p))]
    return (now - max(m)) if m else None


def external_freshness(now=None):
    out = {}
    for exp_id, (label, files) in EXTERNAL_FILES.items():
        out[exp_id] = {"label": label, "last_write_age_s": file_age(files, now), "basis": "file modification time"}
    return out


def data_sizes():
    out = {}
    for rel in ("data/lab/lab.db", "data/research/pm_lp/pm_lp.db", "data/paper.db"):
        p = os.path.join(HERE, rel)
        if os.path.exists(p):
            out[rel] = os.path.getsize(p)
    return out
