#!/usr/bin/env python3
"""Flag dated notes whose written local time lies after the commit that wrote the line (research/LINUX_DRIFT.md
2026-10-24): a "text before code/data" claim is only as good as its time. Read-only; uses git blame.

Usage: python3 scripts/check_note_times.py [--since YYYY-MM-DD] [files...]   (default: every research/**/*.md)
Exit 1 if any line says "<YYYY-MM-DD> kl. HH:MM" (or "<date> HH:MM") later than its own commit on that date; a "ca."
time may round up by at most ROUND_MIN minutes. --since checks only lines committed on or after that date.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})(?: (kl\.|ca\.|kl|ca))? (\d{2}):(\d{2})(?!\d|:\d)")
ROUND_MIN = 5


def blame(path):
    """[(commit local date 'YYYY-MM-DD', commit local 'HH:MM', line text)] for a tracked file."""
    out = subprocess.run(["git", "blame", "--line-porcelain", "--", path], cwd=HERE, capture_output=True, text=True)
    rows, info = [], {}
    for line in out.stdout.splitlines():
        if line.startswith("committer-time "):
            info["t"] = int(line.split()[1])
        elif line.startswith("committer-tz "):
            tz = line.split()[1]
            info["tz"] = (1 if tz[0] == "+" else -1) * (int(tz[1:3]) * 3600 + int(tz[3:5]) * 60)
        elif line.startswith("\t"):
            t = time.gmtime(info["t"] + info["tz"])
            rows.append((time.strftime("%Y-%m-%d", t), time.strftime("%H:%M", t), line[1:]))
    return rows


def check(paths, since=""):
    bad = []
    for p in paths:
        for day, hhmm, text in blame(p):
            if day < since:
                continue
            for d, word, h, m in STAMP.findall(text):
                late = (int(h) * 60 + int(m)) - (int(hhmm[:2]) * 60 + int(hhmm[3:]))
                if d == day and late > (ROUND_MIN if word.startswith("ca") else 0):
                    bad.append((os.path.relpath(p, HERE), d, f"{h}:{m}", hhmm, text.strip()[:100]))
    return bad


def main(argv):
    since = ""
    if argv[:1] == ["--since"]:
        since, argv = argv[1], argv[2:]
    paths = argv or sorted(glob.glob(os.path.join(HERE, "research", "**", "*.md"), recursive=True))
    bad = check(paths, since)
    for f, d, written, committed, text in bad:
        print(f"{f}: {d} {written} written in a commit at {committed}: {text}")
    print(f"{len(bad)} line(s) with a time after their own commit")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
