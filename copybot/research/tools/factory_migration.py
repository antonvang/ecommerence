"""Director order 48 P1: versioned migration plan v1 — one explicit legacy decision per lab experiment (read-only).

Each lab experiment gets: legacy classes (from the factory shadow replay), evidence about its lock (was the spec
committed to git before screening started?), its universe type, and the decisions of the plan:

- results stay as recorded (never rewritten, never upgraded);
- approvals of record get documentation status UNVERIFIED_ORIGIN (order 48);
- data hashes recorded at access are labelled HASH_AT_ACCESS (identity of what was read, not a pre-access lock);
  a hash computed today for old data would be labelled POST_HOC_IDENTITY and is never presented as a lock;
- a fixed symbol list chosen after the window is labelled SURVIVORSHIP_UNKNOWN;
- running forward tests and paper books are never blocked by the migration (the factory applies only to experiments
  created after a future cutover, which needs a separate owner decision).

    python3 research/tools/factory_migration.py [--db PATH]     # -> research/data/factory/migration_v1.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import factory_shadow as fs  # noqa: E402

OUT = os.path.join(HERE, "research", "data", "factory", "migration_v1.json")
PLAN_VERSION = 1

DECISIONS = {
    "legacy": "LEGACY_RECORD: kept as recorded; 1 attempt in the ledger (lower bound); never re-tested",
    "delegated-approval": "UNVERIFIED_ORIGIN approval; results kept as exploratory evidence; no new instance of the "
                          "template without a fresh verified owner approval (order 48 P0)",
    "instruction-cited-approval": "same as delegated-approval",
    "family-approval": "UNVERIFIED_ORIGIN approval (text cannot prove origin); the family's locked forward test "
                       "continues under its own rules and is not blocked",
    "hash-at-access": "HASH_AT_ACCESS: the hashes identify what was read; the lock before data is the git commit of "
                      "the spec (see spec_locked_before_screening); no post-hoc hash is presented as a lock",
    "universe-asof-unrecorded": "SURVIVORSHIP_UNKNOWN: fixed symbol list without a point-in-time date; cross-sectional "
                                "results carry this flag; no re-test (a re-test would be a new experiment)",
    "no-charge": "LEDGER_GAP: verdict without trials/alpha rows; counted as 1 attempt",
}


def _git_time(commit):
    try:
        return int(subprocess.check_output(["git", "show", "-s", "--format=%ct", commit], cwd=HERE, text=True,
                                           stderr=subprocess.DEVNULL).strip())
    except Exception:
        return None


def build(con, git_time=_git_time):
    shadow = fs.pipeline_shadow(con)
    by_exp = {}
    for r in shadow["rows"]:
        e = by_exp.setdefault(r["exp_id"], {"exp_id": r["exp_id"], "classes": set(), "blocks": 0})
        e["classes"].update(r["classes"])
        e["blocks"] += r["factory"] == "BLOCK"
        if (r["from"], r["to"]) == ("DISCOVERED", "REGISTERED") and r["factory"] == "ALLOW":
            e["classes"].add("family-approval")
    screens = dict(con.execute("SELECT exp_id, MIN(ts) FROM transitions WHERE to_state='SCREENING' "
                               "GROUP BY exp_id").fetchall())
    specs = {e: (sc, json.loads(sj or "{}")) for e, sc, sj in con.execute(
        "SELECT exp_id, spec_commit, spec_json FROM experiments e WHERE version=(SELECT MAX(version) FROM experiments "
        "WHERE exp_id=e.exp_id)")}
    rows = []
    for exp, e in sorted(by_exp.items()):
        commit, spec = specs.get(exp, (None, {}))
        st = screens.get(exp)
        ct = git_time(commit) if commit else None
        uni = spec.get("universe")
        cls = sorted(c for c in e["classes"] if c not in ("propose", "no-op", "-"))
        rows.append({"exp_id": exp, "classes": cls,
                     "spec_locked_before_screening": (ct is not None and st is not None and ct <= st) if st else None,
                     "universe": f"list[{len(uni)}]" if isinstance(uni, list) else (None if uni is None else "rule"),
                     "decisions": [DECISIONS[c] for c in cls if c in DECISIONS],
                     "results": "unchanged", "approval_status": "UNVERIFIED_ORIGIN"
                     if any(c in cls for c in ("delegated-approval", "instruction-cited-approval", "family-approval"))
                     else None})
    counts = {}
    for r in rows:
        for c in r["classes"]:
            counts[c] = counts.get(c, 0) + 1
    unexplained = [r["exp_id"] for r in rows if "UNEXPLAINED" in r["classes"]]
    return {"schema": "copybot.factory_migration/1", "plan_version": PLAN_VERSION,
            "rule": "research/reviews/INBOX.md director order 48 P1", "experiments": len(rows),
            "class_counts": dict(sorted(counts.items())), "unexplained": unexplained,
            "screenings": sum(1 for r in rows if r["spec_locked_before_screening"] is not None),
            "spec_locked_before_screening": sum(1 for r in rows if r["spec_locked_before_screening"]),
            "decisions": DECISIONS, "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "lab", "lab.db"))
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    rep = build(sqlite3.connect(f"file:{a.db}?mode=ro", uri=True))
    body = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(body)
    print(hashlib.sha256(body.encode()).hexdigest(), rep["experiments"], rep["class_counts"],
          rep["screenings"], rep["spec_locked_before_screening"], rep["unexplained"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
