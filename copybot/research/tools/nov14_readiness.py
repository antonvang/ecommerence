"""Director order 52 P1: synthetic November-14 readiness checker (stdlib only, read-only, no network).

Loads research/desk/GATE_MATRIX.json and, for a SIMULATED 'now' (never the wall clock unless asked), says whether an
action is allowed or blocked for a study given a set of owner/lock flags. Fail-closed everywhere: an unknown action, an
unknown gate, an unknown study, a naive or unparsable time, a missing flag or a gate that has not reached its date gives
BLOCKED. A 'never' gate blocks always. Nothing here opens, locks, signs, fetches or writes anything; the flags are only
simulated inputs. The checker also verifies that the protocol sha256s listed in research/desk/NOV14_READINESS.md equal
the matrix and the files in the repo (read-only), and that no gate opens before its date.

    python3 research/tools/nov14_readiness.py validate
    python3 research/tools/nov14_readiness.py verify-hashes
    python3 research/tools/nov14_readiness.py status --now 2026-11-14T00:00:00Z
    python3 research/tools/nov14_readiness.py check --now 2026-11-14T00:00:00Z --action historical_fetch \
        --study A_n6 --flag owner_confirms_lock_A --flag lock_A_committed
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import functools
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATRIX = os.path.join(HERE, "research", "desk", "GATE_MATRIX.json")
READINESS = os.path.join(HERE, "research", "desk", "NOV14_READINESS.md")
KINDS = {"date", "date+owner", "date+lock", "owner", "never", "constraint"}
STATUSES = {"CLOSED", "OPEN", "OPENS_AT"}
FLOORS = {"historical_market_data": "2026-11-14T00:00:00Z", "coinm_files": "2026-11-28T00:00:00Z",
          "host_restart": "2026-11-28T00:00:00Z"}
# gates whose date may never be earlier than the floor (fail-closed cross-check of the matrix itself)
FLOOR_GATES = {"G01_HIST_1114": "historical_market_data", "G08_UPBIT_N4": "historical_market_data",
               "G13_LOCK_A": "historical_market_data", "G14_LOCK_B": "historical_market_data",
               "G17_F2_CALIBRATION": "historical_market_data", "G16_F2_WINDOW": "historical_market_data",
               "G18_C1_ACTIVATION": "historical_market_data", "G09_COINM_1128": "coinm_files",
               "G10_FAMILY_NET_1128": "coinm_files", "G25_F3_DEFERRED": "coinm_files",
               "G11_RESTART_1128": "host_restart"}
ID_BLOCK = re.compile(r"<!-- protocol-identities:start -->(.*?)<!-- protocol-identities:end -->", re.S)
ID_ROW = re.compile(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|\s*`([^`]+)`\s*\|\s*`([0-9a-f]{7,40})`\s*\|\s*`([0-9a-f]{64})`\s*\|",
                    re.M)


class MatrixError(Exception):
    pass


@functools.lru_cache(maxsize=None)
def parse_utc(s):
    """'YYYY-MM-DDTHH:MM:SSZ' -> epoch seconds. Anything else (naive, offset, junk) raises MatrixError."""
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", s):
        raise MatrixError("time must be UTC 'YYYY-MM-DDTHH:MM:SSZ': %r" % (s,))
    return calendar.timegm(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").timetuple())


def to_epoch(now):
    """Accept an epoch number, a tz-aware datetime or a UTC 'Z' string; a naive datetime is refused (fail-closed)."""
    if isinstance(now, bool):
        raise MatrixError("bad time")
    if isinstance(now, (int, float)):
        return float(now)
    if isinstance(now, dt.datetime):
        if now.tzinfo is None or now.utcoffset() is None:
            raise MatrixError("naive datetime refused")
        return now.timestamp()
    if not isinstance(now, str):
        raise MatrixError("bad time type %s" % type(now).__name__)
    return float(parse_utc(now))


def load(path=MATRIX):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def gate_index(matrix):
    return {g["id"]: g for g in matrix.get("gates", [])}


def action_index(matrix):
    return {a["id"]: a for a in matrix.get("actions", [])}


def gate_earliest(g):
    e = g.get("earliest_utc")
    return None if e is None else parse_utc(e)


def gate_status(g, now, flags=frozenset()):
    """Status of one gate at `now` for the given flags (CLOSED / OPEN / OPENS_AT)."""
    t = to_epoch(now)
    kind = g.get("kind")
    if kind not in KINDS:
        return "CLOSED"
    if kind == "never":
        return "CLOSED"
    if kind == "constraint":
        return "OPEN"
    e = gate_earliest(g)
    have = set(g.get("required_flags", [])) <= set(flags)
    if kind == "owner":
        return "OPEN" if have and (e is None or t >= e) else "CLOSED"
    if e is None:                                   # a dated kind without a date is malformed: fail-closed
        return "CLOSED"
    if t < e:
        return "OPENS_AT"
    if kind == "date":
        return "OPEN"
    return "OPEN" if have else "CLOSED"


def decide(matrix, action, now, study=None, flags=()):
    """(allowed, reasons). Fail-closed: anything unknown or missing blocks. 'gates' must all be OPEN; 'constraints'
    are prohibitions the allowed action must obey (they must exist and be never/constraint kinds, nothing more)."""
    flags = frozenset(flags or ())
    reasons = []
    try:
        t = to_epoch(now)
    except MatrixError as exc:
        return False, ["BAD_TIME: %s" % exc]
    gates, actions = gate_index(matrix), action_index(matrix)
    a = actions.get(action)
    if a is None:
        return False, ["UNKNOWN_ACTION: %r" % (action,)]
    if not a.get("gates"):
        return False, ["ACTION_WITHOUT_GATES: %r" % (action,)]
    for gid in a["gates"]:
        g = gates.get(gid)
        if g is None:
            reasons.append("UNKNOWN_GATE: %s" % gid)
            continue
        st = gate_status(g, t, flags)
        if g.get("kind") == "never":
            reasons.append("NEVER: %s" % gid)
        elif st == "OPENS_AT":
            reasons.append("NOT_YET: %s opens %s" % (gid, g.get("earliest_utc")))
        elif st != "OPEN":
            missing = sorted(set(g.get("required_flags", [])) - flags)
            reasons.append("GATE_CLOSED: %s missing %s" % (gid, missing))
    for gid in a.get("constraints", []):
        g = gates.get(gid)
        if g is None:
            reasons.append("UNKNOWN_GATE: %s" % gid)
        elif g.get("kind") not in ("never", "constraint"):
            reasons.append("CONSTRAINT_NOT_A_PROHIBITION: %s" % gid)
    allowed_studies = a.get("studies") or {}
    if not allowed_studies:
        reasons.append("NO_STUDY_MAY_DO_THIS: %s" % action)
    elif study is None:
        reasons.append("STUDY_REQUIRED")
    elif study not in allowed_studies:
        reasons.append("STUDY_NOT_ALLOWED: %r for %s" % (study, action))
    else:
        missing = sorted(set(allowed_studies[study]) - flags)
        if missing:
            reasons.append("MISSING_FLAGS: %s" % missing)
    return (not reasons), reasons


def derived_earliest(matrix, action):
    """The latest earliest_utc over the action's gates (None if no dated gate)."""
    gates = gate_index(matrix)
    ts = [gate_earliest(gates[g]) for g in action_index(matrix)[action]["gates"]
          if g in gates and gates[g].get("earliest_utc")]
    return max(ts) if ts else None


def tool_earliest(rel):
    """EARLIEST = dt.date(Y, M, D) in a research tool, read as text (the module is not imported)."""
    with open(os.path.join(HERE, rel), encoding="utf-8") as fh:
        m = re.search(r"^EARLIEST\s*=\s*dt\.date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)", fh.read(), re.M)
    if not m:
        raise MatrixError("no EARLIEST in %s" % rel)
    return calendar.timegm((int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0))


def validate(matrix, check_tools=True):
    """List of problems (empty = valid). Checks structure, floors, as-of statuses and that no gate opens early."""
    errs = []
    gates, actions = matrix.get("gates", []), matrix.get("actions", [])
    gids = [g.get("id") for g in gates]
    if len(gids) != len(set(gids)):
        errs.append("duplicate gate ids")
    aids = [a.get("id") for a in actions]
    if len(aids) != len(set(aids)):
        errs.append("duplicate action ids")
    gi = gate_index(matrix)
    studies = set(matrix.get("studies", {}))
    try:
        as_of = parse_utc(matrix.get("as_of_utc"))
    except MatrixError as exc:
        errs.append("as_of_utc: %s" % exc)
        as_of = None
    for k, v in FLOORS.items():
        if matrix.get("date_floors", {}).get(k) != v:
            errs.append("date floor %s is not %s" % (k, v))
    for g in gates:
        gid = g.get("id")
        if g.get("kind") not in KINDS:
            errs.append("%s: unknown kind %r" % (gid, g.get("kind")))
        if g.get("status_at_as_of") not in STATUSES:
            errs.append("%s: unknown status %r" % (gid, g.get("status_at_as_of")))
        if not g.get("source") or not all(s.get("file") and s.get("loc") for s in g["source"]):
            errs.append("%s: no rule source" % gid)
        for s in g.get("studies", []):
            if s not in studies:
                errs.append("%s: unknown study %s" % (gid, s))
        try:
            e = gate_earliest(g)
        except MatrixError as exc:
            errs.append("%s: %s" % (gid, exc))
            continue
        if g.get("kind") in ("date", "date+owner", "date+lock") and e is None:
            errs.append("%s: dated kind without earliest_utc" % gid)
        if gid in FLOOR_GATES:
            floor = parse_utc(FLOORS[FLOOR_GATES[gid]])
            if e is None or e < floor:
                errs.append("%s opens before its floor %s" % (gid, FLOORS[FLOOR_GATES[gid]]))
        if as_of is not None:
            want = gate_status(g, as_of)
            if want != g.get("status_at_as_of"):
                errs.append("%s: status_at_as_of %s but computed %s" % (gid, g.get("status_at_as_of"), want))
    for a in actions:
        if not a.get("gates"):
            errs.append("%s: no gates" % a.get("id"))
        for gid in a.get("gates", []) + a.get("constraints", []):
            if gid not in gi:
                errs.append("%s: unknown gate %s" % (a.get("id"), gid))
        if a.get("studies") and any(gi.get(g, {}).get("kind") == "never" for g in a.get("gates", [])):
            errs.append("%s: allowed studies but a 'never' gate in gates" % a.get("id"))
        for s in (a.get("studies") or {}):
            if s not in studies:
                errs.append("%s: unknown study %s" % (a.get("id"), s))
    if check_tools:
        g1 = gi.get("G01_HIST_1114")
        for rel in ("research/tools/n6_funding.py", "research/tools/n4_kimchi.py"):
            try:
                if g1 is None or gate_earliest(g1) < tool_earliest(rel):
                    errs.append("G01 opens before %s EARLIEST" % rel)
            except (MatrixError, OSError) as exc:
                errs.append("tool check %s: %s" % (rel, exc))
    errs += no_early_opening(matrix)
    return errs


def no_early_opening(matrix, step_s=3600):
    """Scan hourly from as_of to horizon_end with ALL flags set: no gate may be OPEN before its earliest_utc and no
    action may be allowed before its derived earliest time or while a 'never' gate is in it."""
    errs = []
    try:
        t0, t1 = parse_utc(matrix["as_of_utc"]), parse_utc(matrix["horizon_end_utc"])
    except (KeyError, MatrixError) as exc:
        return ["scan window: %s" % exc]
    every = set()
    for g in matrix.get("gates", []):
        every |= set(g.get("required_flags", []))
    for a in matrix.get("actions", []):
        for fl in (a.get("studies") or {}).values():
            every |= set(fl)
    t0 -= t0 % step_s
    probes = set(range(int(t0), int(t1) + 1, step_s))
    for g in matrix.get("gates", []):
        if g.get("earliest_utc"):
            e = parse_utc(g["earliest_utc"])
            probes |= {e - 1, e}
    dearly = {a["id"]: derived_earliest(matrix, a["id"]) for a in matrix.get("actions", [])}
    for t in sorted(probes):
        for g in matrix.get("gates", []):
            e = g.get("earliest_utc")
            if e and gate_status(g, t, every) == "OPEN" and t < parse_utc(e):
                errs.append("%s OPEN at %d before %s" % (g["id"], t, e))
            if g.get("kind") == "never" and gate_status(g, t, every) != "CLOSED":
                errs.append("%s (never) not CLOSED at %d" % (g["id"], t))
        for a in matrix.get("actions", []):
            de = dearly[a["id"]]
            for s in (a.get("studies") or {}):
                ok, _ = decide(matrix, a["id"], t, s, every)
                if ok and de is not None and t < de:
                    errs.append("%s/%s allowed at %d before %d" % (a["id"], s, t, de))
    return errs


def readiness_identities(path=READINESS):
    with open(path, encoding="utf-8") as fh:
        m = ID_BLOCK.search(fh.read())
    if not m:
        raise MatrixError("no protocol-identities block in %s" % path)
    return [dict(zip(("id", "path", "commit", "sha256"), r)) for r in ID_ROW.findall(m.group(1))]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_hashes(matrix, readiness_path=READINESS, root=HERE):
    """Problems (empty = all match): the NOV14_READINESS table must equal the matrix, and each file's sha256 in the
    repo must equal the listed one. Files are only read."""
    errs = []
    try:
        md = readiness_identities(readiness_path)
    except (MatrixError, OSError) as exc:
        return ["readiness table: %s" % exc]
    js = matrix.get("protocol_identities", [])
    if not js:
        errs.append("matrix has no protocol_identities")
    key = lambda r: (r["id"], r["path"], r["commit"], r["sha256"])   # noqa: E731
    if sorted(map(key, md)) != sorted(map(key, js)):
        errs.append("NOV14_READINESS table and GATE_MATRIX protocol_identities differ")
    for r in js:
        p = os.path.join(root, r["path"])
        if not os.path.isfile(p):
            errs.append("MISSING %s" % r["path"])
            continue
        got = sha256_file(p)
        if got != r["sha256"]:
            errs.append("HASH_MISMATCH %s listed %s repo %s" % (r["path"], r["sha256"][:12], got[:12]))
    return errs


def statuses(matrix, now, flags=()):
    return {g["id"]: gate_status(g, now, frozenset(flags)) for g in matrix.get("gates", [])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("verify-hashes")
    s = sub.add_parser("status")
    s.add_argument("--now", required=True)
    s.add_argument("--flag", action="append", default=[])
    c = sub.add_parser("check")
    c.add_argument("--now", required=True)
    c.add_argument("--action", required=True)
    c.add_argument("--study")
    c.add_argument("--flag", action="append", default=[])
    ap.add_argument("--matrix", default=MATRIX)
    args = ap.parse_args(argv)
    m = load(args.matrix)
    if args.cmd == "validate":
        errs = validate(m)
        print(json.dumps({"valid": not errs, "problems": errs}, ensure_ascii=False, indent=1))
        return 0 if not errs else 1
    if args.cmd == "verify-hashes":
        errs = verify_hashes(m)
        print(json.dumps({"match": not errs, "problems": errs}, ensure_ascii=False, indent=1))
        return 0 if not errs else 1
    if args.cmd == "status":
        print(json.dumps(statuses(m, args.now, args.flag), indent=1))
        return 0
    ok, why = decide(m, args.action, args.now, args.study, args.flag)
    must_obey = action_index(m).get(args.action, {}).get("constraints", [])
    print(json.dumps({"action": args.action, "study": args.study, "now": args.now, "allowed": ok, "reasons": why,
                      "must_obey": must_obey}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
