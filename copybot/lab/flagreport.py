"""PROTOCOL_V3 amendment 21n point 1: the abnormal_move flag report. Descriptive; NO_DECISION until 14 days and 2
weekends; never changes a threshold.

One row per (market, move hour open_s, metric): repeated scans of the same hour (restarts, deploys) are duplicates.
Independent events: flags in the same move hour on several markets are one event. Data quality: the flag's value
against the same scan's z_1h payload (volume_ratio) and its data age; the 720 h median behind volume_ratio is not
stored, so a full recomputation would need the klines again and is not done here. Following cost: the flag scan's
book_rt against the market's median book_rt (from 2026-10-24 18:21).
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import statistics
import sys
import time

DAY, MIN_DAYS, MIN_WEEKENDS = 86400, 14, 2


def _p(raw):
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def report(q, now=None):
    now = now or time.time()
    scans = [r[0] for r in q("SELECT DISTINCT ts FROM observations WHERE detector='abnormal_move/1' ORDER BY ts")]
    z = {}
    hours = collections.defaultdict(set)                       # market -> observed move hours
    for ts, sym, raw in q("SELECT ts, instrument, payload FROM observations WHERE detector='abnormal_move/1' AND "
                          "metric='z_1h'"):
        p = _p(raw)
        z[(ts, sym)] = p
        if p.get("open_s"):
            hours[sym].add(p["open_s"])
    books = collections.defaultdict(list)
    book_at = {}
    for ts, sym, val in q("SELECT ts, instrument, value FROM observations WHERE detector='abnormal_move/1' AND "
                          "metric='book_rt'"):
        if val is not None:
            books[sym].append(val)
            book_at[(ts, sym)] = val
    seen, flags, dupes = set(), [], 0
    for ts, sym, metric, val in q("SELECT ts, instrument, metric, value FROM observations WHERE "
                                  "detector='abnormal_move/1' AND flagged=1 ORDER BY ts"):
        p = z.get((ts, sym)) or {}
        key = (sym, p.get("open_s"), metric)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        same = p.get(metric) if metric in ("volume_ratio", "z_1h", "z_24h") else None
        wd = time.gmtime(p["open_s"]).tm_wday if p.get("open_s") else None
        flags.append({"market": sym, "metric": metric, "open_s": p.get("open_s"), "value": val,
                      "consistent_with_scan": same is not None and abs(same - val) < 1e-9 * max(1.0, abs(val)),
                      "age_s": p.get("age_s"), "weekend": wd is not None and wd >= 5,
                      "book_rt": book_at.get((ts, sym)),
                      "market_median_book_rt": statistics.median(books[sym]) if books.get(sym) else None})
    events = collections.defaultdict(list)
    for f in flags:
        events[f["open_s"]].append(f["market"])
    per = collections.defaultdict(lambda: {"flags": 0, "weekend": 0})
    for f in flags:
        d = per[(f["market"], f["metric"])]
        d["flags"] += 1
        d["weekend"] += f["weekend"]
    by_market = {f"{m}|{k}": {**v, "observed_hours": len(hours.get(m, ())),
                              "rate": v["flags"] / len(hours[m]) if hours.get(m) else None}
                 for (m, k), v in sorted(per.items())}
    span_days = (scans[-1] - scans[0]) / DAY if scans else 0
    weekends = len({s // (7 * DAY) for s in scans if time.gmtime(s).tm_wday >= 5})
    enough = span_days >= MIN_DAYS and weekends >= MIN_WEEKENDS
    return {"rule": "research/PROTOCOL_V3.md amendment 21n point 1", "generated": now, "scans": len(scans),
            "span_days": span_days, "weekends": weekends,
            "observed_market_hours": sum(len(v) for v in hours.values()),
            "flag_rows": len(flags) + dupes, "duplicate_rows": dupes, "flags": len(flags),
            "independent_events": len(events),
            "events": [{"open_s": t, "markets": sorted(set(m))} for t, m in sorted(events.items())],
            "by_market_metric": by_market,
            "data_quality": {"inconsistent": sum(1 for f in flags if not f["consistent_with_scan"]),
                             "older_than_2h": sum(1 for f in flags if (f["age_s"] or 0) > 7200),
                             "note": "the 720 h median behind volume_ratio is not stored; no full recomputation"},
            "following_cost": [{k: f[k] for k in ("market", "open_s", "book_rt", "market_median_book_rt")}
                               for f in flags if f["book_rt"] is not None],
            "conclusion": "enough data for a dated proposal" if enough else "NO_DECISION",
            "missing": None if enough else f"need >= {MIN_DAYS} days and >= {MIN_WEEKENDS} weekends of scans "
                                           f"(have {span_days:.1f} days, {weekends} weekend(s))"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/lab/lab.db")
    ap.add_argument("--out", help="write <out>.json")
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    text = json.dumps(report(lambda sql, *args: con.execute(sql, args).fetchall()), indent=1, sort_keys=True)
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
