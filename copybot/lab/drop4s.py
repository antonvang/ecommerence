"""PROTOCOL_V3 amendment 21m point 1: the descriptive leave-one-day-out of the post-hoc 4-sigma-drop pattern, then
DROPPED by the user's decision. explore0 cache only; no verdict from the numbers, no alpha, no lock.

Events: amendment 21c's down moves (s = -1); y = ln(C_h+25 / C_h+1). (a) the UTC-day cluster mean with each day left out
(min, median, max), (b) without the k busiest days, k = 1..10, (c) the same with ISO-week clusters, (d) the share of days
with a positive mean, (e) the unconditional 24 h return (all coins, every 6th hour) as the baseline.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import sys

from lab import hypogen, movescreen
from lab.engine import data

KEY = "abnormal_move_drop|rebound_24h|posthoc"
HOUR, DAY, WEEK = hypogen.HOUR, hypogen.DAY, 7 * hypogen.DAY
EXIT = movescreen.OUTCOMES["cont_24h"]


def drops(series, end):
    rows = []
    for sym in sorted(series):
        px = series[sym]
        for h, s, _ in movescreen.events(px):
            if s < 0:
                y, _ = movescreen.outcome(px, h, 1, EXIT, end)
                if y is not None:
                    rows.append({"sym": sym, "h": h, "y": y})
    return rows


def _week(t):
    return (t + 3 * DAY) // WEEK                          # ISO weeks start on Monday; 1970-01-01 was a Thursday


def loo(rows, key):
    by = collections.defaultdict(list)
    for r in rows:
        by[key(r["h"])].append(r["y"])
    means = {k: statistics.fmean(v) for k, v in by.items()}
    allm = statistics.fmean(means.values())
    left = [statistics.fmean([m for j, m in means.items() if j != k]) for k in means]
    busiest = [k for k, _ in sorted(by.items(), key=lambda kv: -len(kv[1]))]
    drop_k = {}
    for k in range(1, 11):
        rest = [m for j, m in means.items() if j not in set(busiest[:k])]
        drop_k[k] = statistics.fmean(rest) if rest else None
    return {"clusters": len(means), "events": len(rows), "cluster_mean": allm,
            "leave_one_out": {"min": min(left), "median": statistics.median(left), "max": max(left)},
            "without_k_busiest": drop_k, "share_positive_clusters": sum(m > 0 for m in means.values()) / len(means)}


def baseline(series, end):
    by = collections.defaultdict(list)
    for px in series.values():
        for h in px:
            if h % (6 * HOUR) == 0:
                y, _ = movescreen.outcome(px, h, 1, EXIT, end)
                if y is not None:
                    by[h // DAY].append(y)
    return {"days": len(by), "day_cluster_mean": statistics.fmean([statistics.fmean(v) for v in by.values()])}


def run(cache=None):
    if cache:
        data.CACHE = cache
    reader = hypogen.Reader(hypogen.SCREEN)                   # get=None: never a request
    series = {s: movescreen.prices(reader, s) for s in movescreen.universe()}
    rows = drops(series, reader.b)
    files = sorted(reader.files, key=lambda f: f["file"])
    return {"rule": "research/PROTOCOL_V3.md amendment 21m point 1", "label": "DESCRIPTIVE (post hoc), never evidence",
            "files": len(files), "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
            "events_sha256": hashlib.sha256(json.dumps([[r["sym"], r["h"], round(r["y"], 10)] for r in rows]
                                                       ).encode()).hexdigest(),
            "by_day": loo(rows, lambda h: h // DAY), "by_iso_week": loo(rows, _week),
            "baseline_unconditional_24h": baseline(series, reader.b),
            "results": [{"key": KEY, "verdict": "DROPPED", "rule": "research/PROTOCOL_V3.md amendment 21m point 1",
                         "n_events": len(rows), "reason": "the user's decision 2026-10-24 (option 3 after 1a); no test"}]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", help="market cache directory (default: the lab's)")
    ap.add_argument("--out", help="write <out>.json")
    a = ap.parse_args(argv)
    text = json.dumps(run(a.cache), indent=1, sort_keys=True)
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
