"""PROTOCOL_V3 amendment 21c: do abnormal moves (amendment 21's |z_1h| >= 4) carry a tradable direction? Exploration on
the crypto USD-M perps cached for explore0, never evidence; nothing here trades or touches a family, gate or alpha.

- Universe (point 1): every `<coin>USDT` with a cached 1 h kline month in explore0, BTCDOMUSDT excepted; read through
  `hypogen.Reader("explore0")` without network (it refuses every other month and everything from 2024-01-01).
- Events (point 2): the detector's rule on closed hourly bars, sigma over the 720 preceding hours (>= 600 returns), at
  most one per coin per 24 h. Direction s = sign of the event hour's return.
- Outcomes (point 3): entry at the close of the next bar (one hour after the flag can be seen); cont_4h / cont_24h =
  s * log return to the close 4 / 24 hours later. Positive = continuation, negative = reversal.
- Test (points 4-5): events are averaged per UTC day (clusters); two-sided sign flip on the clusters, halves 2020/2021,
  placebo h - 30 days with the same s, and the 0.46 % round trip.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys

from lab import hypogen, moves
from lab.engine import data

METHOD, RULE = "m21c", "research/PROTOCOL_V3.md amendment 21c"
HOUR, DAY = hypogen.HOUR, hypogen.DAY
Z, HIST, MIN_RETURNS = moves.Z1, moves.HIST, moves.MIN_RETURNS
DEDUP_S = DAY
OUTCOMES = {"cont_4h": 5, "cont_24h": 25}                    # exit at the close of bar h + k; entry at bar h + 1
EXCLUDE = {"BTCDOMUSDT"}                                      # an index, not a coin
MIN_CLUSTERS, MIN_HALF = hypogen.MIN_SCREEN, hypogen.MIN_HALF
P_SCREEN, P_PLACEBO, COST = hypogen.P_SCREEN, hypogen.P_PLACEBO, hypogen.COST
PLACEBO_SHIFT, HALF = hypogen.PLACEBO_SHIFT, hypogen.HALF
FAST_MARGIN = 0.98                                            # running-sum sigma pre-filter; exact pstdev decides


def universe(cache=None):
    """Symbols with at least one cached explore0 kline month (point 1), sorted."""
    a, b = hypogen.bounds(hypogen.SCREEN)
    months = {f"{y}-{m:02d}" for y, m in hypogen._months(a, b - 1)}
    d = os.path.join(cache or data.CACHE, "klines")
    out = set()
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.endswith(".zip") and "-1h-" in f:
            sym, rest = f[:-4].split("-1h-")
            if rest in months and sym.endswith("USDT") and sym not in EXCLUDE:
                out.add(sym)
    return sorted(out)


def prices(reader, sym):
    """{bar open ts: close} of one symbol over explore0 (cache only)."""
    s = reader.series(sym, "klines", reader.a, reader.b - 1)
    return {ts: v[0] for ts, v in s.items() if v[0] > 0}


def events(px):
    """[(h, s, z)] by the detector's rule (point 2): r_h between two present consecutive bars, sigma = pstdev of the
    returns of the 720 preceding hours (>= 600), |z| >= 4, at most one per DEDUP_S."""
    ret = {h: math.log(px[h] / px[h - HOUR]) for h in px if h - HOUR in px}
    hours = sorted(ret)
    out, last, n, s1, s2 = [], None, 0, 0.0, 0.0
    window = collections.deque()                              # hours currently in the trailing window
    for h in hours:
        while window and window[0] < h - HIST * HOUR:         # keep hours in [h - 720 h, h - 1 h]
            g = window.popleft()
            n, s1, s2 = n - 1, s1 - ret[g], s2 - ret[g] ** 2
        if n >= MIN_RETURNS and (last is None or h - last >= DEDUP_S):
            var = max(0.0, s2 / n - (s1 / n) ** 2)
            if var > 0 and abs(ret[h]) >= FAST_MARGIN * Z * math.sqrt(var):
                sigma = statistics.pstdev([ret[g] for g in window])          # exact, as moves.stats
                if sigma > 0 and abs(ret[h] / sigma) >= Z:
                    out.append((h, 1 if ret[h] > 0 else -1, ret[h] / sigma))
                    last = h
        window.append(h)
        n, s1, s2 = n + 1, s1 + ret[h], s2 + ret[h] ** 2
    return out


def outcome(px, h, s, k, end):
    """(y, None) or (None, reason) for an event at bar h with direction s and exit bar h + k (point 3)."""
    if h + (k + 1) * HOUR > end:
        return None, "window outside the phase"
    p0, p1 = px.get(h + HOUR), px.get(h + k * HOUR)
    if not p0 or not p1:
        return None, "missing price"
    return s * math.log(p1 / p0), None


def clusters(rows):
    """{UTC day: mean y} (point 4)."""
    by = {}
    for r in rows:
        by.setdefault(r["h"] // DAY * DAY, []).append(r["y"])
    return {d: statistics.fmean(v) for d, v in sorted(by.items())}


def screen(series, name, a, b):
    """One candidate `abnormal_move|<name>|m21c` on {symbol: prices}; returns the result dict (point 5)."""
    k = OUTCOMES[name]
    rows, excl, pl_rows = [], {}, []
    for sym in sorted(series):
        px = series[sym]
        for h, s, z in events(px):
            y, why = outcome(px, h, s, k, b)
            if y is None:
                excl[why] = excl.get(why, 0) + 1
                continue
            rows.append({"sym": sym, "h": h, "s": s, "z": z, "y": y})
            hp = h - PLACEBO_SHIFT
            if hp - HOUR >= a:
                yp, _ = outcome(px, hp, s, k, b)
                if yp is not None:
                    pl_rows.append({"sym": sym, "h": hp, "y": yp})
    key = f"abnormal_move|{name}|{METHOD}"
    cl = clusters(rows)
    vals = list(cl.values())
    res = {"key": key, "outcome": name, "method": METHOD, "rule": RULE, "window": "explore0 2020-03..2021-12",
           "label": "EXPLORATORY (never evidence)", "symbols": len(series), "events": len(rows) + sum(excl.values()),
           "n_events": len(rows), "n_clusters": len(vals), "excluded": excl,
           "events_sha256": hashlib.sha256(json.dumps([[r["sym"], r["h"], r["s"], round(r["y"], 10)] for r in rows]
                                                      ).encode()).hexdigest()}
    if len(vals) < MIN_CLUSTERS:
        res.update(verdict="UNTESTABLE", reason=f"{len(vals)} day clusters with data (< {MIN_CLUSTERS})")
        return res
    mean, p = statistics.fmean(vals), hypogen.p_two(vals)
    h1 = [v for d, v in cl.items() if d < HALF]
    h2 = [v for d, v in cl.items() if d >= HALF]
    pl = list(clusters(pl_rows).values())
    pp = hypogen.p_two(pl) if len(pl) >= MIN_CLUSTERS else None
    sign = 1 if mean > 0 else -1
    checks = {f"p <= {P_SCREEN}": p <= P_SCREEN,
              "same sign in 2020 and 2021": len(h1) >= MIN_HALF and len(h2) >= MIN_HALF and
              statistics.fmean(h1) * sign > 0 and statistics.fmean(h2) * sign > 0,
              f"placebo p > {P_PLACEBO} (>= {MIN_CLUSTERS} clusters)": pp is not None and pp > P_PLACEBO,
              f"|mean| >= {COST}": abs(mean) >= COST}
    ys = [r["y"] for r in rows]

    def part(sel):                                            # descriptive splits (point 6): not tested
        v = [r["y"] for r in rows if sel(r)]
        return {"n_events": len(v), "mean": statistics.fmean(v) if v else None}
    res.update(mean=mean, direction="continuation" if sign > 0 else "reversal", p=p,
               event_mean=statistics.fmean(ys), event_median=statistics.median(ys),
               share_positive=sum(y > 0 for y in ys) / len(ys),
               halves={"2020": [len(h1), statistics.fmean(h1) if h1 else None],
                       "2021": [len(h2), statistics.fmean(h2) if h2 else None]},
               placebo={"n_events": len(pl_rows), "n_clusters": len(pl), "mean": statistics.fmean(pl) if pl else None,
                        "p": pp, "shift_days": -PLACEBO_SHIFT // DAY},
               checks=checks,
               descriptive_not_tested={"up moves": part(lambda r: r["s"] > 0), "down moves": part(lambda r: r["s"] < 0),
                                       "BTC+ETH": part(lambda r: r["sym"] in ("BTCUSDT", "ETHUSDT")),
                                       "other coins": part(lambda r: r["sym"] not in ("BTCUSDT", "ETHUSDT"))})
    ok = all(checks.values())
    res.update(verdict="SCREEN_PASS" if ok else "SCREEN_FAIL",
               reason="all screening checks hold" if ok else "failed: " + "; ".join(c for c, v in checks.items()
                                                                                       if not v))
    return res


def run(cache=None):
    """Both candidates over the cached universe; cache only (no network). Returns the report dict."""
    if cache:
        data.CACHE = cache
    reader = hypogen.Reader(hypogen.SCREEN)                   # get=None: never a request
    syms = universe()
    series = {s: prices(reader, s) for s in syms}
    files = sorted(reader.files, key=lambda f: f["file"])
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        commit = None
    return {"rule": RULE, "method": METHOD, "code_commit": commit, "symbols": syms, "files": len(files),
            "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
            "results": [screen(series, n, reader.a, reader.b) for n in OUTCOMES]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", help="market cache directory (default: the lab's)")
    ap.add_argument("--out", help="write <out>.json")
    a = ap.parse_args(argv)
    rep = run(a.cache)
    text = json.dumps(rep, indent=1, sort_keys=True)
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
