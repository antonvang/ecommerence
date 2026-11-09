"""Append-only status register (director order 81 P3, dev only). Separate from the alpha ledger, the paper books and every
protected study file: this module imports none of them and never opens them.

One JSON object per line, hash-chained. `effective_ts` is when the underlying observation happened, `recorded_ts` when the
line was written; they are never mixed. A correction is a new line with `supersedes`; nothing is edited or removed.

There is no default path and no command line. Paths inside either checkout are refused, so a real register cannot be
created by accident: the first production line needs a separate approval (order 81). Tests use temporary files with
synthetic events only.
"""
import fcntl
import hashlib
import json
import math
import os
import time

GENESIS = "0" * 64
STATUSES = ("DATA_SOURCE_UNAVAILABLE", "BLOCKED_DATA_SOURCE_UNAVAILABLE", "PARTIAL_CLOSE", "CLOSE_INCOMPLETE",
            "EQUITY_NOT_COMPUTABLE", "HOLDOUT_NOT_EVALUATED", "TERMINATED_DATA_QUALITY_FAILURE", "DESIGN_ONLY",
            "BLOCKED_DEPENDENCY")
FIELDS = ("seq", "prev_hash", "experiment_id", "status", "reason", "source", "effective_ts", "recorded_ts", "supersedes",
          "hash")
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
PROTECTED_ROOTS = (_HERE, "/home/anton/copybot-dev/copybot", "/home/anton/ecommerence")


class RegisterError(ValueError):
    pass


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _refuse_protected(path):
    real = os.path.realpath(path)
    for root in PROTECTED_ROOTS:
        r = os.path.realpath(root)
        if real == r or real.startswith(r + os.sep):
            raise RegisterError(f"refused: {real} lies inside a checkout; the first real register needs separate approval")


def line_hash(entry):
    """SHA-256 of the entry without its own hash, in canonical JSON."""
    body = {k: entry[k] for k in FIELDS if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _rows(raw):
    """[(line number, text)] of a register's bytes; a tail without newline is reported by verify."""
    return [(i, t) for i, t in enumerate(raw.decode("utf-8").split("\n"), 1) if t != ""]


def append(path, experiment_id, status, reason, source, effective_ts, recorded_ts=None, supersedes=None, clock=time.time):
    """Append one line and return it. Fails closed on invalid input or a broken chain; never rewrites the file."""
    _refuse_protected(path)
    if status not in STATUSES:
        raise RegisterError(f"unknown status: {status!r}")
    for name, v in (("experiment_id", experiment_id), ("reason", reason), ("source", source)):
        if not isinstance(v, str) or not v.strip():
            raise RegisterError(f"{name} is required")
    recorded = clock() if recorded_ts is None else recorded_ts
    if not _number(effective_ts) or not _number(recorded):
        raise RegisterError("effective_ts and recorded_ts must be finite numbers")
    if effective_ts > recorded:
        raise RegisterError("effective_ts lies after recorded_ts")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.lseek(fd, 0, os.SEEK_SET)
        raw = b""
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            raw += chunk
        state = _check(raw)
        if not state["ok"]:
            raise RegisterError(f"refused: the chain is broken: {state['problems'][:3]}")
        if supersedes is not None:
            target = next((e for e in state["entries_data"] if e["seq"] == supersedes), None)
            if target is None:
                raise RegisterError(f"supersedes: no line {supersedes}")
            if target["experiment_id"] != experiment_id:
                raise RegisterError("supersedes: a line of another experiment")
        if state["entries_data"] and recorded < state["entries_data"][-1]["recorded_ts"]:
            raise RegisterError("recorded_ts goes backwards")
        entry = {"seq": state["entries"] + 1, "prev_hash": state["head"], "experiment_id": experiment_id, "status": status,
                 "reason": reason, "source": source, "effective_ts": effective_ts, "recorded_ts": recorded,
                 "supersedes": supersedes}
        entry["hash"] = line_hash(entry)
        data = (json.dumps({k: entry[k] for k in FIELDS}, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    return entry


def _check(raw):
    problems, entries, head = [], [], GENESIS
    text = raw.decode("utf-8", errors="replace")
    if text and not text.endswith("\n"):
        problems.append("the last line has no newline (a torn write)")
    last_recorded = None
    for no, line in _rows(raw):
        try:
            e = json.loads(line)
        except ValueError:
            problems.append(f"line {no}: not JSON")
            continue
        if not isinstance(e, dict) or set(e) != set(FIELDS):
            problems.append(f"line {no}: wrong fields")
            continue
        if e["seq"] != len(entries) + 1:
            problems.append(f"line {no}: seq {e['seq']}, expected {len(entries) + 1}")
        if e["prev_hash"] != head:
            problems.append(f"line {no}: prev_hash does not continue the chain")
        if e["hash"] != line_hash(e):
            problems.append(f"line {no}: hash does not match its content")
        if e["status"] not in STATUSES:
            problems.append(f"line {no}: unknown status")
        if not _number(e["effective_ts"]) or not _number(e["recorded_ts"]):
            problems.append(f"line {no}: timestamps are not numbers")
        else:
            if e["effective_ts"] > e["recorded_ts"]:
                problems.append(f"line {no}: effective_ts after recorded_ts")
            if last_recorded is not None and e["recorded_ts"] < last_recorded:
                problems.append(f"line {no}: recorded_ts goes backwards")
            last_recorded = e["recorded_ts"]
        if e["supersedes"] is not None and not any(
                x["seq"] == e["supersedes"] and x["experiment_id"] == e["experiment_id"] for x in entries):
            problems.append(f"line {no}: supersedes no earlier line of this experiment")
        entries.append(e)
        head = e["hash"]
    return {"ok": not problems, "entries": len(entries), "head": head, "problems": problems, "entries_data": entries}


def verify(path, expected_head=None):
    """Chain integrity of a register. Read only. A cut-off tail looks like a shorter valid file unless the caller gives
    the head it recorded elsewhere (expected_head)."""
    with open(path, "rb") as f:
        state = _check(f.read())
    if expected_head is not None and state["head"] != expected_head:
        state["problems"].append("head differs from the expected head (lines may be missing)")
        state["ok"] = False
    state.pop("entries_data")
    return state


def current(path):
    """{experiment_id: latest line that no later line supersedes}. Derived on read; refuses a broken chain."""
    with open(path, "rb") as f:
        state = _check(f.read())
    if not state["ok"]:
        raise RegisterError(f"refused: the chain is broken: {state['problems'][:3]}")
    gone = {e["supersedes"] for e in state["entries_data"] if e["supersedes"] is not None}
    out = {}
    for e in state["entries_data"]:
        if e["seq"] not in gone:
            out[e["experiment_id"]] = e
    return out
