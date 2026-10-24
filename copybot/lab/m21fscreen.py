"""PROTOCOL_V3 amendment 21f: three hypothesis families screened on the cached explore0 crypto perps (method m21f).
Exploration, never evidence; nothing here trades, locks or touches a family, gate or alpha.

- A `btc_lead|alt_excess_24h`: after a BTC hour with |z| >= 3, does the equal-weight alt excess over BTC from bar h+1 to
  h+25 continue BTC's direction? Cost hurdle 1.11 % (a long/short basket).
- B `squeeze_break|cont_24h`: a breakout |z| >= 2.5 after compression (sigma of the 72 h before / sigma <= 0.5); does
  the coin continue? Hurdle 0.65 %.
- C `catalyst_move|cont_24h`: amendment 21c's 4-sigma moves with a Binance announcement naming the coin published in
  [h - 24 h, h + 1 h]; do they continue? Hurdle 0.65 %.
Common: hypogen.Reader("explore0") without network, sigma over the 720 preceding hourly returns (>= 600), entry at the
close of bar h+1, exit at the close of bar h+25, UTC-day clusters, two-sided sign flip, halves, placebo h - 30 days.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import sqlite3
import statistics
import subprocess
import sys

from lab import hypogen, movescreen
from lab.engine import data

METHOD, RULE = "m21f", "research/PROTOCOL_V3.md amendment 21f"
HOUR, DAY = hypogen.HOUR, hypogen.DAY
HIST, MIN_RETURNS, MIN_72, WIN_72 = 720, 600, 65, 72
EXIT = 25                                                     # exit bar h + 25; entry bar h + 1
COST_ALT, COST_PAIR = 0.0065, 0.0111
Z_A, Z_B, COMPRESS, Z_C = 3.0, 2.5, 0.5, 4.0
CATALYST_BEFORE, CATALYST_AFTER = DAY, HOUR
BINANCE = "https://www.binance.com%"
FAST = 0.98


def scan(px, z, compress=None):
    """[(h, s, z)]: |r_h / sigma| >= z with sigma over the 720 preceding hours (>= 600 returns), optionally with
    sigma_72 / sigma <= compress (>= 65 returns in the 72 h before h); at most one per 24 h."""
    ret = {h: math.log(px[h] / px[h - HOUR]) for h in px if h - HOUR in px}
    w, w72 = collections.deque(), collections.deque()
    n, s1, s2, out, last = 0, 0.0, 0.0, [], None
    for h in sorted(ret):
        while w and w[0] < h - HIST * HOUR:
            g = w.popleft()
            n, s1, s2 = n - 1, s1 - ret[g], s2 - ret[g] ** 2
        while w72 and w72[0] < h - WIN_72 * HOUR:
            w72.popleft()
        if n >= MIN_RETURNS and (last is None or h - last >= DAY):
            var = max(0.0, s2 / n - (s1 / n) ** 2)
            if var > 0 and abs(ret[h]) >= FAST * z * math.sqrt(var):
                sigma = statistics.pstdev([ret[g] for g in w])
                ok = sigma > 0 and abs(ret[h] / sigma) >= z
                if ok and compress is not None:
                    ok = len(w72) >= MIN_72 and statistics.pstdev([ret[g] for g in w72]) / sigma <= compress
                if ok:
                    out.append((h, 1 if ret[h] > 0 else -1, ret[h] / sigma))
                    last = h
        w.append(h)
        w72.append(h)
        n, s1, s2 = n + 1, s1 + ret[h], s2 + ret[h] ** 2
    return out


def leg(px, h, end):
    """ln(C_h+25 / C_h+1) or (None, reason)."""
    if h + (EXIT + 1) * HOUR > end:
        return None, "window outside the phase"
    p0, p1 = px.get(h + HOUR), px.get(h + EXIT * HOUR)
    if not p0 or not p1:
        return None, "missing price"
    return math.log(p1 / p0), None


def judge(rows, pl_rows, key, cost, extra=None):
    """The amendment's SCREEN_PASS rule on UTC-day clusters of rows [{'h', 'y', ...}]."""
    cl, pl = movescreen.clusters(rows), list(movescreen.clusters(pl_rows).values())
    vals = list(cl.values())
    res = {"key": key, "method": METHOD, "rule": RULE, "window": "explore0 2020-03..2021-12",
           "label": "EXPLORATORY (never evidence)", "n_events": len(rows), "n_clusters": len(vals), "cost_hurdle": cost,
           "events_sha256": hashlib.sha256(json.dumps([[r.get("sym"), r["h"], round(r["y"], 10)] for r in rows]
                                                      ).encode()).hexdigest(), **(extra or {})}
    if len(vals) < movescreen.MIN_CLUSTERS:
        res.update(verdict="UNTESTABLE", reason=f"{len(vals)} day clusters with data (< {movescreen.MIN_CLUSTERS})")
        return res
    mean, p = statistics.fmean(vals), hypogen.p_two(vals)
    h1 = [v for d, v in cl.items() if d < movescreen.HALF]
    h2 = [v for d, v in cl.items() if d >= movescreen.HALF]
    pp = hypogen.p_two(pl) if len(pl) >= movescreen.MIN_CLUSTERS else None
    sign = 1 if mean > 0 else -1
    checks = {f"p <= {movescreen.P_SCREEN}": p <= movescreen.P_SCREEN,
              "same sign in 2020 and 2021": len(h1) >= movescreen.MIN_HALF and len(h2) >= movescreen.MIN_HALF and
              statistics.fmean(h1) * sign > 0 and statistics.fmean(h2) * sign > 0,
              f"placebo p > {movescreen.P_PLACEBO} (>= {movescreen.MIN_CLUSTERS} clusters)":
              pp is not None and pp > movescreen.P_PLACEBO,
              f"|mean| >= {cost}": abs(mean) >= cost}
    ys = [r["y"] for r in rows]
    sd = statistics.stdev(vals) if len(vals) > 1 else None
    res.update(mean=mean, se=sd / math.sqrt(len(vals)) if sd else None, p=p, direction="continuation" if sign > 0
               else "reversal", event_mean=statistics.fmean(ys), event_median=statistics.median(ys),
               share_positive=sum(y > 0 for y in ys) / len(ys),
               halves={"2020": [len(h1), statistics.fmean(h1) if h1 else None],
                       "2021": [len(h2), statistics.fmean(h2) if h2 else None]},
               placebo={"n_events": len(pl_rows), "n_clusters": len(pl), "mean": statistics.fmean(pl) if pl else None,
                        "p": pp, "shift_days": -movescreen.PLACEBO_SHIFT // DAY}, checks=checks)
    ok = all(checks.values())
    res.update(verdict="SCREEN_PASS" if ok else "SCREEN_FAIL",
               reason="all screening checks hold" if ok else "failed: " + "; ".join(c for c, v in checks.items()
                                                                                       if not v))
    return res


def _basket(series, h, end):
    """Equal-weight alt excess over BTC from bar h+1 to h+25, or (None, reason)."""
    b, why = leg(series["BTCUSDT"], h, end)
    if b is None:
        return None, why
    xs = [x - b for s, px in series.items() if s != "BTCUSDT" for x, _ in [leg(px, h, end)] if x is not None]
    return (statistics.fmean(xs), len(xs)) if xs else (None, "no alt prices")


def family_a(series, a, b):
    rows, pl_rows, excl, same_hour = [], [], {}, []
    btc = series.get("BTCUSDT", {})
    for h, s, z in scan(btc, Z_A):
        got, info = _basket(series, h, b)
        if got is None:
            excl[info] = excl.get(info, 0) + 1
            continue
        rows.append({"sym": "BTCUSDT", "h": h, "y": s * got, "alts": info})
        rb = math.log(btc[h] / btc[h - HOUR])
        now = [math.log(px[h] / px[h - HOUR]) - rb for sym, px in series.items()
               if sym != "BTCUSDT" and h in px and h - HOUR in px]
        if now:
            same_hour.append(s * statistics.fmean(now))
        hp = h - movescreen.PLACEBO_SHIFT
        if hp - HOUR >= a:
            gp, _ = _basket(series, hp, b)
            if gp is not None:
                pl_rows.append({"h": hp, "y": s * gp})
    return judge(rows, pl_rows, f"btc_lead|alt_excess_24h|{METHOD}", COST_PAIR, {
        "excluded": excl, "descriptive_not_tested": {
            "alt excess in the event hour (s-signed, mean)": statistics.fmean(same_hour) if same_hour else None,
            "mean alts per event": statistics.fmean([r["alts"] for r in rows]) if rows else None}})


def _single(series, events, a, b, key, extra=None):
    rows, pl_rows, excl = [], [], {}
    for sym, h, s in events:
        px = series[sym]
        y, why = leg(px, h, b)
        if y is None:
            excl[why] = excl.get(why, 0) + 1
            continue
        rows.append({"sym": sym, "h": h, "y": s * y})
        hp = h - movescreen.PLACEBO_SHIFT
        if hp - HOUR >= a:
            yp, _ = leg(px, hp, b)
            if yp is not None:
                pl_rows.append({"sym": sym, "h": hp, "y": s * yp})
    return judge(rows, pl_rows, key, COST_ALT, {"excluded": excl, **(extra or {})})


def family_b(series, a, b):
    evs = [(sym, h, s) for sym in sorted(series) for h, s, _ in scan(series[sym], Z_B, COMPRESS)]
    return _single(series, evs, a, b, f"squeeze_break|cont_24h|{METHOD}")


def catalysts(q):
    """{coin: sorted publication times} of Binance announcements in the registry that name the coin."""
    out = collections.defaultdict(list)
    for (raw,) in q("SELECT payload FROM observations WHERE detector='news/1' AND metric='news_item' AND source LIKE ?",
                    BINANCE):
        p = json.loads(raw) if isinstance(raw, str) else raw
        if p.get("published_ts"):
            for c in p.get("coins") or []:
                out[c].append(float(p["published_ts"]))
    return {c: sorted(v) for c, v in out.items()}


def family_c(series, a, b, cat):
    evs, without = [], 0
    for sym in sorted(series):
        times = cat.get(sym[:-4], [])
        for h, s, _ in scan(series[sym], Z_C):
            if any(h - CATALYST_BEFORE <= t <= h + CATALYST_AFTER for t in times):
                evs.append((sym, h, s))
            else:
                without += 1
    return _single(series, evs, a, b, f"catalyst_move|cont_24h|{METHOD}",
                   {"descriptive_not_tested": {"4-sigma moves without a catalyst (not tested; ~m21c)": without}})


def run(cache=None, db_path=None):
    if cache:
        data.CACHE = cache
    reader = hypogen.Reader(hypogen.SCREEN)                   # get=None: never a request
    syms = movescreen.universe()
    series = {s: movescreen.prices(reader, s) for s in syms}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) if db_path else None
    cat = catalysts(lambda sql, *a: con.execute(sql, a).fetchall()) if con else {}
    files = sorted(reader.files, key=lambda f: f["file"])
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        commit = None
    return {"rule": RULE, "method": METHOD, "code_commit": commit, "symbols": len(syms), "files": len(files),
            "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
            "catalyst_coins": len(cat), "results": [family_a(series, reader.a, reader.b),
                                                    family_b(series, reader.a, reader.b),
                                                    family_c(series, reader.a, reader.b, cat)]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", help="market cache directory (default: the lab's)")
    ap.add_argument("--db", help="registry for the catalysts (opened read-only)")
    ap.add_argument("--out", help="write <out>.json")
    a = ap.parse_args(argv)
    text = json.dumps(run(a.cache, a.db), indent=1, sort_keys=True)
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
