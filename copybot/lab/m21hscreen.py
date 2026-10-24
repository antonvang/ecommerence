"""PROTOCOL_V3 amendment 21h point 5: does funding add information to a 4-sigma move's next 24 hours (method m21h)?
Exploration on the cached explore0 crypto perps, never evidence; nothing here trades, locks or touches alpha.

Events are amendment 21c's. The signal is the last settled funding rate at or before the move hour's start (at most
12 h old): the crowd is long above the neutral 0.01 %/8 h, short below 0, neutral otherwise (excluded). A move with the
crowd is followed (d = s), a move against it is faded (d = -s). v = d * ln(C_h+25 / C_h+1) - d * the funding settled in
(h + 1 h, h + 25 h]. Day clusters, halves, placebo h - 30 d with the same d, cost hurdle 0.46 % (amendment 17's).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import subprocess
import sys

from lab import hypogen, m21fscreen, movescreen
from lab.engine import data

METHOD, RULE = "m21h", "research/PROTOCOL_V3.md amendment 21h point 5"
KEY = f"funding_crowd|squeeze_24h|{METHOD}"
HOUR, DAY = hypogen.HOUR, hypogen.DAY
NEUTRAL, MAX_AGE, MIN_SETTLED = 0.0001, 12 * HOUR, 2
EXIT = movescreen.OUTCOMES["cont_24h"]


def funding(reader, sym):
    """{settlement hour: rate} of one symbol over explore0 (cache only)."""
    return reader.series(sym, "funding", reader.a, reader.b - 1)


def value(px, fs, h, d, end):
    """(v, None) or (None, reason): d-signed log return from bar h+1 to h+25 net of the funding a d position pays."""
    y, why = movescreen.outcome(px, h, 1, EXIT, end)
    if y is None:
        return None, why
    paid = [r for t, r in fs.items() if h + HOUR < t <= h + EXIT * HOUR]
    if len(paid) < MIN_SETTLED:
        return None, "missing funding in the holding window"
    return d * y - d * math.fsum(paid), None


def crowd(fs, times, h):
    """(c, f) from the last settlement at or before h, or (None, reason)."""
    i = next((t for t in reversed(times) if t <= h), None)
    if i is None or h - i > MAX_AGE:
        return None, "no recent funding"
    f = fs[i]
    if f > NEUTRAL:
        return 1, f
    if f < 0:
        return -1, f
    return None, "neutral funding"


def screen(series, fund, a, b):
    rows, pl_rows, excl = [], [], collections.Counter()
    for sym in sorted(series):
        px, fs = series[sym], fund.get(sym) or {}
        times = sorted(fs)
        for h, s, _ in movescreen.events(px):
            if not fs:
                excl["no funding file"] += 1
                continue
            c, f = crowd(fs, times, h)
            if c is None:
                excl[f] += 1
                continue
            d = s if s == c else -s
            v, why = value(px, fs, h, d, b)
            if v is None:
                excl[why] += 1
                continue
            rows.append({"sym": sym, "h": h, "y": v, "with": s == c, "f": f})
            hp = h - movescreen.PLACEBO_SHIFT
            if hp - HOUR >= a:
                vp, _ = value(px, fs, hp, d, b)
                if vp is not None:
                    pl_rows.append({"sym": sym, "h": hp, "y": vp})

    def part(sel):
        v = [r["y"] for r in rows if sel(r)]
        return {"n_events": len(v), "mean": sum(v) / len(v) if v else None}
    days = collections.Counter(r["h"] // DAY for r in rows)
    coins = collections.Counter(r["sym"] for r in rows)
    top = lambda c: sum(n for _, n in c.most_common(5)) / len(rows) if rows else None  # noqa: E731
    return m21fscreen.judge(rows, pl_rows, KEY, hypogen.COST, {
        "excluded": dict(excl), "descriptive_not_tested": {
            "with the crowd (continuation)": part(lambda r: r["with"]),
            "against the crowd (reversal)": part(lambda r: not r["with"]),
            "share of events on the 5 busiest days": top(days), "share of events in the 5 busiest coins": top(coins)}})


def run(cache=None):
    if cache:
        data.CACHE = cache
    reader = hypogen.Reader(hypogen.SCREEN)                   # get=None: never a request
    syms = movescreen.universe()
    series = {s: movescreen.prices(reader, s) for s in syms}
    fund = {s: funding(reader, s) for s in syms}
    files = sorted(reader.files, key=lambda f: f["file"])
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        commit = None
    return {"rule": RULE, "method": METHOD, "code_commit": commit, "symbols": len(syms),
            "symbols_with_funding": sum(1 for v in fund.values() if v), "files": len(files),
            "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
            "results": [screen(series, fund, reader.a, reader.b)]}


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
