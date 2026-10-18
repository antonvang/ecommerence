"""Data gateway (ENGINE_PROPOSAL.md §2, stage S2): every evaluation read names (experiment, split) and is checked
against the lifecycle before any file is handed out. Each file read is hashed and recorded in the append-only
`datasets` table; a file whose content changed since an earlier read is refused.

Rules:
- dev / validation  -> state SCREENING (purpose "evaluate"), or a final state (purpose "reproduce", audit only)
- holdout           -> state VALIDATION only (after a human approval citing committed frozen parameters), opened
                       once: later reads must use the same code hash and the same files
- forward           -> state PAPER_TRADING only
- EXTERNAL experiments, unknown experiments and the pm_lp_v1 data directory are always refused.

Limitation: the gateway works on files. Files that mix periods (e.g. a full candle history) must be clipped to the
window by the caller with `clip()`; new experiments should store one file per split (as pmcal and pm_lp do).
"""
from __future__ import annotations

import hashlib
import os
import time

from lab.db import HERE
from lab.lifecycle import FINAL, state

SPLITS = ("dev", "validation", "holdout", "forward")
DENY = (os.path.normcase(os.path.join(HERE, "data", "research", "pm_lp")),)


class AccessRefused(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clip(rows, window, key):
    """Keep rows whose key (unix seconds) lies in [start, end]."""
    a, b = window
    return [r for r in rows if a <= key(r) <= b]


class Gateway:
    def __init__(self, db, actor):
        self.db, self.actor = db, actor

    def _refuse(self, exp_id, split, reason, paths):
        self.db.event("data.refused", self.actor, exp_id, {"split": split, "reason": reason, "paths": paths})
        raise AccessRefused(reason)

    def access(self, exp_id, split, paths, window, source, purpose="evaluate", code_hash=None, expected=None):
        """Authorise, hash and record a read. Returns {path: sha256}. `expected` maps path -> required sha256."""
        rel = [os.path.relpath(os.path.abspath(p), HERE).replace("\\", "/") for p in paths]   # one form on every OS
        st = state(self.db, exp_id)
        if st is None:
            self._refuse(exp_id, split, "unknown experiment", rel)
        if split not in SPLITS:
            self._refuse(exp_id, split, f"unknown split {split}", rel)
        if st == "EXTERNAL":
            self._refuse(exp_id, split, "EXTERNAL experiments are never read through the lab", rel)
        for p in paths:
            if any(os.path.normcase(os.path.abspath(p)).startswith(d) for d in DENY):
                self._refuse(exp_id, split, "pm_lp_v1 data is off limits", rel)
        if purpose == "reproduce":
            if st not in FINAL or split not in ("dev", "validation"):
                self._refuse(exp_id, split, "reproduction is limited to dev/validation of finished experiments", rel)
        elif purpose == "evaluate":
            need = {"dev": ("SCREENING",), "validation": ("SCREENING",), "holdout": ("VALIDATION",),
                    "forward": ("PAPER_TRADING", "OBSERVATION")}
            if st not in need[split]:
                self._refuse(exp_id, split, f"{split} data needs state {need[split]}, experiment is {st}", rel)
        else:
            self._refuse(exp_id, split, f"unknown purpose {purpose}", rel)

        shas = {}
        for p, r in zip(paths, rel):
            if not os.path.exists(p):
                self._refuse(exp_id, split, f"missing file {r}", rel)
            s = sha256_file(p)
            if expected and expected.get(p) not in (None, s):
                self._refuse(exp_id, split, f"{r} does not match its recorded hash", rel)
            prev = self.db.one("SELECT sha256 FROM datasets WHERE exp_id=? AND split=? AND path IN (?, ?) ORDER BY id "
                               "DESC LIMIT 1", exp_id, split, r, r.replace("/", "\\"))   # also rows read on Windows
            if prev and prev["sha256"] != s:
                self._refuse(exp_id, split, f"{r} changed since it was first read", rel)
            shas[p] = s

        if split == "holdout":
            opened = self.db.one("SELECT payload FROM events WHERE kind='holdout.opened' AND exp_id=? ORDER BY id LIMIT 1",
                                 exp_id)
            if opened:                 # research/PROTOCOL_V3.md amendment 7 section 8: one declared file set
                import json
                first = json.loads(opened["payload"])
                inside = set(shas.values()) <= set(first.get("sha256", [])) and (
                    first.get("paths") is None or set(rel) <= set(first["paths"]))
                if first.get("code_hash") != code_hash or not inside:
                    self._refuse(exp_id, split, "holdout already opened with different code or data: every later "
                                 "read must be part of the declared file set with identical hashes", rel)

        now = int(time.time())
        with self.db.tx():
            for p, r in zip(paths, rel):
                if not self.db.one("SELECT 1 FROM datasets WHERE exp_id=? AND split=? AND path IN (?, ?) AND sha256=?",
                                   exp_id, split, r, r.replace("/", "\\"), shas[p]):
                    self.db.append("datasets", exp_id=exp_id, split=split, source=source, path=r,
                                   window_start=window[0], window_end=window[1], ts=now, sha256=shas[p],
                                   size=os.path.getsize(p), purpose=purpose, code_hash=code_hash)
            if split == "holdout" and not self.db.one("SELECT 1 FROM events WHERE kind='holdout.opened' AND exp_id=?",
                                                      exp_id):
                self.db.event("holdout.opened", self.actor, exp_id, {"code_hash": code_hash,
                                                                     "sha256": sorted(shas.values()),
                                                                     "paths": sorted(rel)})
            self.db.event("data.accessed", self.actor, exp_id, {"split": split, "purpose": purpose, "paths": rel,
                                                                "window": list(window)})
        return shas
