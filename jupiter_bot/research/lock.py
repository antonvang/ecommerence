"""Lock the P2 plan: record hashes of the plan and the evaluation code, once.

    python3 -m jupiter_bot.research.lock --approved-by Anton [--out DIR]

Refuses unless: the plan says it is approved (a line starting with
"Status: **GODKENDT"), the plan and code files are committed and unchanged in
git, the holdout window still lies in the future, and no lock exists yet.
`verify()` lets replay and the dashboard check that nothing changed since.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLAN = "jupiter_bot/research/P2_PLAN.md"
CODE = ("jupiter_bot/research/strategies.py", "jupiter_bot/research/replay.py")


def utc(text):
    return float(calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ")))


# Must match section 6 of P2_PLAN.md.
DEVELOPMENT = {"start": utc("2026-11-21T00:00:00Z"), "end": utc("2026-12-19T00:00:00Z")}
HOLDOUT = {"start": utc("2026-12-19T00:00:00Z"), "end": utc("2027-01-02T00:00:00Z")}
DEFAULT_OUT = Path.home() / ".local" / "share" / "jupiter-bot" / "research"


class LockError(RuntimeError):
    pass


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes(repo=REPO):
    return file_sha256(repo / PLAN), {name: file_sha256(repo / name) for name in CODE}


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def lock(approved_by, out=DEFAULT_OUT, repo=REPO, now=None, git=_git):
    now = time.time() if now is None else now
    out = Path(out)
    if not approved_by or not approved_by.strip():
        raise LockError("approved_by is required")
    plan_text = (repo / PLAN).read_text(encoding="utf-8")
    if not any(line.startswith("Status: **GODKENDT") for line in plan_text.splitlines()):
        raise LockError("the plan is not marked approved (Status: **GODKENDT ...)")
    if now >= HOLDOUT["start"]:
        raise LockError("the holdout window has already started; write a new plan with a future window")
    for name in (PLAN, *CODE):
        if not (repo / name).is_file():
            raise LockError("missing %s" % name)
        if git(repo, "ls-files", "--error-unmatch", name).returncode != 0:
            raise LockError("%s is not committed" % name)
        if git(repo, "diff", "--quiet", "HEAD", "--", name).returncode != 0:
            raise LockError("%s has uncommitted changes" % name)
    commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    plan_sha, code_sha = hashes(repo)
    record = {"plan_path": PLAN, "plan_sha256": plan_sha, "code_sha256": code_sha, "git_commit": commit,
              "locked_at": now, "approved_by": approved_by.strip(),
              "development": DEVELOPMENT, "holdout": HOLDOUT}
    out.mkdir(parents=True, exist_ok=True)
    target = out / "plan_lock.json"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        raise LockError("a lock already exists at %s; it is never replaced" % target) from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
    return record


def load(out=DEFAULT_OUT):
    path = Path(out) / "plan_lock.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def verify(record, repo=REPO):
    """List of mismatches between the lock and the files now (empty = intact)."""
    if not isinstance(record, dict) or not isinstance(record.get("code_sha256"), dict):
        return ["the lock record is malformed"]
    plan_sha, code_sha = hashes(repo)
    problems = []
    if plan_sha != record.get("plan_sha256"):
        problems.append("%s changed since the lock" % PLAN)
    missing = [name for name in CODE if name not in record["code_sha256"]]
    if missing:   # an empty or partial code list must not pass as "intact"
        problems.append("the lock does not cover %s" % ", ".join(missing))
    for name, digest in record["code_sha256"].items():
        if code_sha.get(name) != digest:
            problems.append("%s changed since the lock" % name)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m jupiter_bot.research.lock")
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--verify", action="store_true", help="only check an existing lock")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            record = load(args.out)
            if record is None:
                raise LockError("no lock found")
            problems = verify(record)
            print(json.dumps({"intact": not problems, "problems": problems}, indent=2))
            return 0 if not problems else 1
        print(json.dumps(lock(args.approved_by, args.out), indent=2, sort_keys=True))
        return 0
    except (LockError, OSError) as exc:
        print("STOP: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
