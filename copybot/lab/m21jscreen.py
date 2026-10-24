"""PROTOCOL_V3 amendment 21j: new information sources screened in explore0 (method m21j). Exploration, never evidence.

- J1 `macro_release|post_drift_24h`: scheduled FOMC, CPI and Employment Situation releases (amendment 14's calendar);
  s = sign of the BTC/ETH perp return in the bar holding the release; y = s * ln(C_H+25 / C_H+1), BTC and ETH averaged;
  placebo the same clock time 7 days earlier (14 if that day had a calendar event).
- J2 `attention_shock|cont_7d`: a Wikipedia week with >= 2x the mean views of the 8 weeks before, known Tuesday 00:00
  UTC (available_ts); y = sign(week's return) * the coin's perp return over the next 168 h from the Tuesday 00:00 bar's
  close; clusters by week; placebo 4 weeks earlier.
Only rows inside explore0 are kept from the calendar and pageview files; prices come from hypogen.Reader("explore0").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone

from lab import hypogen, m21iscreen, movescreen
from lab.engine import data

METHOD, RULE = "m21j", "research/PROTOCOL_V3.md amendment 21j"
HOUR, DAY, WEEK = hypogen.HOUR, hypogen.DAY, 7 * hypogen.DAY
EXIT_J1, HOLD_J2, SHOCK, LOOKBACK = 25, 168 * HOUR, 2.0, 8
ARTICLES = {"Bitcoin": "BTCUSDT", "Ethereum": "ETHUSDT", "Dogecoin": "DOGEUSDT", "Litecoin": "LTCUSDT",
            "Polkadot_(cryptocurrency)": "DOTUSDT", "Cardano_(blockchain_platform)": "ADAUSDT",
            "Chainlink_(blockchain)": "LINKUSDT"}


def _ingest(*p):
    return os.path.join(data.CACHE, "ingest", *p)


def _day(s):
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def calendar(a, b, root=None):
    """(scheduled [(ts, event)], {UTC days with any calendar event}) inside [a, b) from the cached calendar."""
    events, days = [], set()
    for y in (2020, 2021):
        for k in ("fomc", "bls"):
            path = os.path.join(root or _ingest("calendar"), f"{k}-{y}.json")
            if not os.path.exists(path):
                continue
            with open(path) as f:
                for e in json.load(f)["events"]:
                    d = _day(e["date"])
                    if a <= d < b:
                        days.add(d // DAY)
                        if e.get("scheduled") and e.get("ts") and a <= e["ts"] < b:
                            events.append((int(e["ts"]), e["event"]))
    return sorted(events), days


def _react(px, h, end):
    """y for one coin at reaction bar h: s from bar h's return, s-signed from bar h+1 to h+25; or None."""
    if h not in px or h - HOUR not in px:
        return None
    r0 = math.log(px[h] / px[h - HOUR])
    if r0 == 0:
        return None
    s = 1 if r0 > 0 else -1
    y, _ = movescreen.outcome(px, h, s, EXIT_J1, end)
    return None if y is None else y


def j1(px, vol, a, b, cal):
    events, busy = cal
    rows, pl_rows, by_type, excl = [], [], {}, {}
    for ts, ev in events:
        h = ts - ts % HOUR
        ys = [y for y in (_react(px[s], h, b) for s in ("BTCUSDT", "ETHUSDT")) if y is not None]
        if not ys:
            excl["missing price or window"] = excl.get("missing price or window", 0) + 1
            continue
        c = statistics.fmean([m21iscreen.cost(vol[s], h) or m21iscreen.FLOOR for s in ("BTCUSDT", "ETHUSDT")])
        rows.append({"sym": ev, "h": h, "y": statistics.fmean(ys), "c": c})
        by_type.setdefault(ev, []).append(statistics.fmean(ys))
        hp = h - WEEK if (h - WEEK) // DAY not in busy else h - 2 * WEEK
        if hp - HOUR >= a:
            yp = [y for y in (_react(px[s], hp, b) for s in ("BTCUSDT", "ETHUSDT")) if y is not None]
            if yp:
                pl_rows.append({"h": hp, "y": statistics.fmean(yp)})
    res = m21iscreen.judge(rows, pl_rows, f"macro_release|post_drift_24h|{METHOD}", {
        "excluded": excl, "descriptive_not_tested": {k: {"n": len(v), "mean": statistics.fmean(v)}
                                                     for k, v in sorted(by_type.items())}})
    res.update(method=METHOD, rule=RULE)
    return res


def weekly(rows, a, b):
    """{Monday ts: views} of complete ISO weeks inside [a, b) from pageview rows (only explore0 rows are read)."""
    daily = {_day(r["date"]): r["views"] for r in rows if a <= _day(r["date"]) < b}
    out = {}
    for d in daily:
        if datetime.fromtimestamp(d, timezone.utc).weekday() == 0 and all(d + i * DAY in daily for i in range(7)):
            out[d] = sum(daily[d + i * DAY] for i in range(7))
    return out


def j2(px, vol, a, b, views):
    rows, pl_rows, excl = [], [], {}
    for art, sym in ARTICLES.items():
        wk, p = views.get(art) or {}, px.get(sym) or {}
        for m in sorted(wk):
            prev = [wk.get(m - i * WEEK) for i in range(1, LOOKBACK + 1)]
            if any(v is None for v in prev) or statistics.fmean(prev) <= 0 or wk[m] / statistics.fmean(prev) < SHOCK:
                continue
            t = m + 8 * DAY                                  # Tuesday 00:00 UTC: Sunday's available_ts
            p0, p1, w0, w1 = p.get(t), p.get(t + HOLD_J2), p.get(m - HOUR), p.get(m + WEEK - HOUR)
            if t + HOLD_J2 + HOUR > b or not all((p0, p1, w0, w1)):
                excl["missing price or window"] = excl.get("missing price or window", 0) + 1
                continue
            s = 1 if w1 > w0 else -1
            c = m21iscreen.cost(vol.get(sym) or {}, t)
            if c is None:
                excl["no volume history"] = excl.get("no volume history", 0) + 1
                continue
            rows.append({"sym": sym, "h": m, "y": s * math.log(p1 / p0), "c": c, "ratio": wk[m] / statistics.fmean(prev)})
            tp = t - 4 * WEEK
            if p.get(tp) and p.get(tp + HOLD_J2) and tp - HOUR >= a:
                pl_rows.append({"sym": sym, "h": m - 4 * WEEK, "y": s * math.log(p[tp + HOLD_J2] / p[tp])})
    res = m21iscreen.judge(rows, pl_rows, f"attention_shock|cont_7d|{METHOD}", {
        "excluded": excl, "descriptive_not_tested": {"shocks per coin": {s: sum(1 for r in rows if r["sym"] == s)
                                                                         for s in sorted(set(ARTICLES.values()))}}})
    res.update(method=METHOD, rule=RULE)
    return res


def run(cache=None):
    if cache:
        data.CACHE = cache
    reader = hypogen.Reader(hypogen.SCREEN)                   # get=None: never a request
    syms = sorted(set(ARTICLES.values()))
    raw = {s: reader.series(s, "klines", reader.a, reader.b - 1) for s in syms}
    px = {s: {t: v[0] for t, v in raw[s].items() if v[0] > 0} for s in syms}
    vol = {s: {t: v[1] for t, v in raw[s].items()} for s in syms}
    views, used = {}, []
    for art in ARTICLES:
        path = _ingest("pageviews", f"{art}.json")
        if os.path.exists(path):
            with open(path, "rb") as f:
                blob = f.read()
            used.append({"file": os.path.basename(path), "sha256": hashlib.sha256(blob).hexdigest()})
            views[art] = weekly(json.loads(blob)["rows"], reader.a, reader.b)
    cal = calendar(reader.a, reader.b)
    files = sorted(reader.files, key=lambda f: f["file"]) + used
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        commit = None
    return {"rule": RULE, "method": METHOD, "code_commit": commit, "files": len(files), "calendar_events": len(cal[0]),
            "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
            "results": [j1(px, vol, reader.a, reader.b, cal), j2(px, vol, reader.a, reader.b, views)]}


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
