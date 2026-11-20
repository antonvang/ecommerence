"""Operations for the Linux collector: staleness alarm and journal backup.

    python3 -m jupiter_bot.ops health --journal J [--state S]
    python3 -m jupiter_bot.ops backup --journal J [--dest D] [--keep N]

Both only READ the journal. `health` exits 1 while any source is stale and
sends a desktop notification (notify-send) when the problem first appears,
when it changes, at most every RENOTIFY seconds while it lasts, and once on
recovery. `backup` writes a consistent SQLite copy (online backup API) per
UTC day, checks it with PRAGMA quick_check and keeps the newest N copies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from . import storage
from .marketdata.journal import Journal

# Seconds without an OK fetch before a source counts as stale.
MAX_AGE = {
    "binance_spot_klines": 15 * 60,   # fetched every minute
    "jupiter_quote": 15 * 60,         # fetched every minute
    "solana_status": 3 * 3600,        # hourly
    "jupiter_status": 3 * 3600,
    "agave_releases": 3 * 3600,
}
RENOTIFY = 6 * 3600
BACKUP_NAME = re.compile(r"^observations-\d{4}-\d{2}-\d{2}\.db$")


def stale_sources(status, now, max_age=MAX_AGE):
    """Problems as sorted strings, e.g. 'jupiter_quote: no OK for 42 min'."""
    last_ok = {}
    for row in status.get("outcomes", ()):
        if row.get("outcome") == "OK" and row.get("last") is not None:
            last_ok[row["source"]] = max(last_ok.get(row["source"], 0.0), float(row["last"]))
    problems = []
    for source, limit in max_age.items():
        if source not in last_ok:
            problems.append("%s: never OK" % source)
        elif now - last_ok[source] > limit:
            problems.append("%s: no OK for %d min" % (source, (now - last_ok[source]) // 60))
    return sorted(problems)


def decide(previous, problems, now, renotify=RENOTIFY):
    """(message or None, new state). Pure, so the throttling is testable."""
    keys = [p.split(":")[0] for p in problems]
    was = previous.get("stale", [])
    if not problems:
        message = "recovered: all sources OK again" if was else None
        return message, {"stale": [], "last_alert": None}
    if keys != was or now - (previous.get("last_alert") or 0) >= renotify:
        return "STALE: " + "; ".join(problems), {"stale": keys, "last_alert": now}
    return None, dict(previous, stale=keys)


def notify(message, urgent):
    # stderr lines prefixed <3>/<5> get that syslog priority in journald.
    print(("<3>" if urgent else "<5>") + message, file=sys.stderr)
    try:
        subprocess.run(["notify-send", "-u", "critical" if urgent else "normal",
                        "-a", "jupiter-collector", "jupiter-collector", message],
                       timeout=10, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass  # no desktop session: the journald line above is the record


def health(journal_path, state_path, now=None):
    now = time.time() if now is None else now
    journal = Journal(journal_path, readonly=True)
    try:
        problems = stale_sources(journal.status(), now)
    finally:
        journal.close()
    try:
        previous = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    message, state = decide(previous, problems, now)
    if message:
        notify(message, urgent=bool(problems))
    tmp = Path(str(state_path) + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, state_path)
    print(json.dumps({"at": now, "stale": problems}))
    return 1 if problems else 0


def backup(journal_path, dest, keep=7, now=None):
    now = time.time() if now is None else now
    Journal(journal_path, readonly=True).close()      # refuses anything that is not our journal
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / time.strftime("observations-%Y-%m-%d.db", time.gmtime(now))
    tmp = dest / (".%s.tmp" % final.name)
    tmp.unlink(missing_ok=True)
    src = storage.connect(journal_path, readonly=True)
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
            check = dst.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            dst.close()
    finally:
        src.close()
    if check != "ok":
        tmp.unlink(missing_ok=True)
        raise sqlite3.DatabaseError("backup failed quick_check: %s" % check)
    os.replace(tmp, final)
    copies = sorted(p for p in dest.iterdir() if BACKUP_NAME.match(p.name))
    removed = [p.name for p in copies[:-keep]] if keep > 0 else []
    for name in removed:
        (dest / name).unlink()
    print(json.dumps({"backup": str(final), "bytes": final.stat().st_size, "removed": removed}))
    return 0


def main(argv=None):
    data = Path.home() / ".local" / "share" / "jupiter-bot"
    parser = argparse.ArgumentParser(prog="python3 -m jupiter_bot.ops")
    commands = parser.add_subparsers(dest="command", required=True)
    h = commands.add_parser("health", help="alarm if a source has had no OK fetch for too long")
    h.add_argument("--journal", required=True)
    h.add_argument("--state", default=str(data / "health-state.json"))
    b = commands.add_parser("backup", help="consistent daily copy of the journal")
    b.add_argument("--journal", required=True)
    b.add_argument("--dest", default=str(data / "backups"))
    b.add_argument("--keep", type=int, default=7)
    args = parser.parse_args(argv)
    if args.command == "health":
        return health(Path(args.journal), Path(args.state))
    return backup(Path(args.journal), Path(args.dest), keep=args.keep)


if __name__ == "__main__":
    sys.exit(main())
