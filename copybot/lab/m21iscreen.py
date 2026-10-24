"""PROTOCOL_V3 amendment 21i: spot-perp lead/lag on the cached explore0 coins (method m21i), the prospective per-event
cost hurdle, and a descriptive (estimated) spread by regime. Exploration, never evidence; nothing trades or locks.

- Cost (point 2): c_i = max(0.46 %, 2 * (2 * 0.040 % + RT_est(V_i))), RT_est(V) = exp(0.8999) * V^-0.4540 from the
  2026-10-24 snapshot, V_i = the coin's mean 24 h quote volume over the 30 days before the event (point-in-time).
- S1 (point 3): x_t = r_spot,t - r_perp,t; |x_t / sigma_x| >= 3 (sigma over the 720 preceding hours); y = sign(x_t) *
  r_perp,t+1. Zero-latency entry: information only.
- S2 (point 4): amendment 21c's 4-sigma perp moves; perp-led (s * (r_perp - r_spot) > 0) are faded, spot-led followed;
  v net of funding as amendment 21h.
- Spread regimes (point 6): Abdi & Ranaldo (2017) estimate from 1 h high/low/close, described, never tested.
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

from lab import hypogen, m21fscreen, m21hscreen, movescreen
from lab.engine import data

METHOD, RULE = "m21i", "research/PROTOCOL_V3.md amendment 21i"
HOUR, DAY = hypogen.HOUR, hypogen.DAY
FLOOR, FEE, MARGIN = hypogen.COST, 0.0004, 2.0
RT_A, RT_B = 0.8999, -0.4540                                   # research/studies/COSTS_2026-10-24.md (crypto, n 516)
Z_S1, HIST, MIN_RETURNS, VOL_DAYS = 3.0, 720, 600, 30


def rt_est(v):
    return math.exp(RT_A) * v ** RT_B if v and v > 0 else None


def cost(vol, h):
    """c_i for an event at h from {bar open: quote volume}; None without volume history."""
    hrs = [vol[t] for t in range(h - VOL_DAYS * DAY, h, HOUR) if t in vol]
    if len(hrs) < 0.5 * VOL_DAYS * 24:
        return None
    rt = rt_est(statistics.fmean(hrs) * 24)
    return max(FLOOR, MARGIN * (2 * FEE + rt)) if rt is not None else None


def judge(rows, pl_rows, key, extra=None):
    """As m21f's rule, with the hurdle = the mean of the clusters' mean costs (point 2)."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["h"] // DAY * DAY].append(r["c"])
    hurdle = statistics.fmean([statistics.fmean(v) for v in by.values()]) if by else None
    res = m21fscreen.judge(rows, pl_rows, key, hurdle if hurdle is not None else FLOOR, extra)
    res.update(method=METHOD, rule=RULE, cost_rule="max(0.46 %, 2 x (2 x 0.040 % + RT_est(V_30d))) per event; "
               "RT_est from the 2026-10-24 snapshot is an ESTIMATE carried back to 2020-21")
    return res


def _series(reader, sym, kind):
    return reader.series(sym, kind, reader.a, reader.b - 1)


def s1(perp, spot, a, b):
    rows, pl_rows, excl = [], [], collections.Counter()
    for sym in sorted(perp):
        p, s = perp[sym], spot.get(sym)
        if not s:
            continue
        pc = {t: v[0] for t, v in p.items() if v[0] > 0}
        sc = {t: v[0] for t, v in s.items() if v[0] > 0}
        vol = {t: v[1] for t, v in p.items()}
        x = {t: math.log(sc[t] / sc[t - HOUR]) - math.log(pc[t] / pc[t - HOUR]) for t in pc
             if t in sc and t - HOUR in pc and t - HOUR in sc}
        w, n, s1_, s2_ = collections.deque(), 0, 0.0, 0.0
        for t in sorted(x):
            while w and w[0] < t - HIST * HOUR:
                g = w.popleft()
                n, s1_, s2_ = n - 1, s1_ - x[g], s2_ - x[g] ** 2
            if n >= MIN_RETURNS:
                var = max(0.0, s2_ / n - (s1_ / n) ** 2)
                if var > 0 and abs(x[t]) >= 0.98 * Z_S1 * math.sqrt(var):
                    sig = statistics.pstdev([x[g] for g in w])
                    if sig > 0 and abs(x[t] / sig) >= Z_S1:
                        sg = 1 if x[t] > 0 else -1
                        if t + 2 * HOUR > b or t + HOUR not in pc:
                            excl["window outside the phase or missing price"] += 1
                        else:
                            c = cost(vol, t)
                            if c is None:
                                excl["no volume history"] += 1
                            else:
                                rows.append({"sym": sym, "h": t, "y": sg * math.log(pc[t + HOUR] / pc[t]), "c": c})
                                tp = t - movescreen.PLACEBO_SHIFT
                                if tp - HOUR >= a and tp in pc and tp + HOUR in pc:
                                    pl_rows.append({"sym": sym, "h": tp, "y": sg * math.log(pc[tp + HOUR] / pc[tp])})
            w.append(t)
            n, s1_, s2_ = n + 1, s1_ + x[t], s2_ + x[t] ** 2
    return judge(rows, pl_rows, f"spot_lead|perp_1h|{METHOD}", {
        "excluded": dict(excl), "label_extra": "zero-latency entry: information only, not a tradable result",
        "descriptive_not_tested": {"symbols with spot and perp": sum(1 for s in perp if spot.get(s))}})


def s2(perp, spot, fund, a, b):
    rows, pl_rows, excl, led = [], [], collections.Counter(), collections.Counter()
    for sym in sorted(perp):
        p, s, fs = perp[sym], spot.get(sym) or {}, fund.get(sym) or {}
        pc = {t: v[0] for t, v in p.items() if v[0] > 0}
        vol = {t: v[1] for t, v in p.items()}
        for h, sg, _ in movescreen.events(pc):
            if h not in s or h - HOUR not in s or s[h][0] <= 0 or s[h - HOUR][0] <= 0:
                excl["no spot bar"] += 1
                continue
            if not fs:
                excl["no funding file"] += 1
                continue
            e = sg * (math.log(pc[h] / pc[h - HOUR]) - math.log(s[h][0] / s[h - HOUR][0]))
            d = -sg if e > 0 else sg
            v, why = m21hscreen.value(pc, fs, h, d, b)
            if v is None:
                excl[why] += 1
                continue
            c = cost(vol, h)
            if c is None:
                excl["no volume history"] += 1
                continue
            led["perp-led" if e > 0 else "spot-led"] += 1
            rows.append({"sym": sym, "h": h, "y": v, "c": c, "perp_led": e > 0})
            hp = h - movescreen.PLACEBO_SHIFT
            if hp - HOUR >= a:
                vp, _ = m21hscreen.value(pc, fs, hp, d, b)
                if vp is not None:
                    pl_rows.append({"sym": sym, "h": hp, "y": vp})

    def part(sel):
        v = [r["y"] for r in rows if sel(r)]
        return {"n_events": len(v), "mean": statistics.fmean(v) if v else None}
    return judge(rows, pl_rows, f"perp_led|move_24h|{METHOD}", {
        "excluded": dict(excl), "descriptive_not_tested": {"perp-led (faded)": part(lambda r: r["perp_led"]),
                                                           "spot-led (followed)": part(lambda r: not r["perp_led"])}})


class HLReader(hypogen.Reader):
    """The same phase guard as hypogen.Reader, keeping (high, low, close) for the spread estimate (point 6)."""

    def month(self, sym, kind, y, m):
        if not (self.a <= hypogen._T(y, m) < self.b) or hypogen._T(y, m) >= hypogen.END:
            raise hypogen.Refused(f"{sym} {kind} {y}-{m:02d} is outside {self.phase} (amendment 21i)")
        path = hypogen._path(sym, kind, y, m)
        out = {}
        if path and os.path.exists(path):
            for r in data._rows(path):
                ts = int(r[0]) // 1000
                if self.a <= ts < self.b and ts < hypogen.END and float(r[3]) > 0:
                    out[ts] = (float(r[2]), float(r[3]), float(r[4]))
        return out


def ar_daily(hlc):
    """{UTC day: Abdi-Ranaldo spread estimate} from {bar open: (high, low, close)} (>= 20 pairs a day)."""
    by = collections.defaultdict(list)
    ts = sorted(hlc)
    for t0, t1 in zip(ts, ts[1:]):
        if t1 - t0 != HOUR or t0 // DAY != t1 // DAY:
            continue
        h0, l0, c0 = (math.log(v) for v in hlc[t0])
        h1, l1, _ = (math.log(v) for v in hlc[t1])
        by[t0 // DAY].append(max(0.0, 4 * (c0 - (h0 + l0) / 2) * (c0 - (h1 + l1) / 2)))
    return {d: math.sqrt(statistics.fmean(v)) for d, v in by.items() if len(v) >= 20}


def spread_regimes(hl, perp):
    """Point 6: estimated spread on m21c event days vs the same coin 30 days earlier, and by volatility tercile."""
    pairs, terc = [], {0: [], 1: [], 2: []}
    for sym in sorted(hl):
        sp = ar_daily(hl[sym])
        pc = {t: v[0] for t, v in perp[sym].items() if v[0] > 0}
        for h, _, _ in movescreen.events(pc):
            d = h // DAY
            if d in sp and d - 30 in sp:
                pairs.append((sp[d], sp[d - 30]))
        rv = collections.defaultdict(list)
        for t in pc:
            if t - HOUR in pc:
                rv[t // DAY].append(math.log(pc[t] / pc[t - HOUR]))
        days = sorted((statistics.pstdev(v), d) for d, v in rv.items() if len(v) >= 20 and d in sp)
        for i, (_, d) in enumerate(days):
            terc[min(2, 3 * i // len(days))].append(sp[d])
    return {"label": "ESTIMATED (Abdi-Ranaldo from 1 h bars), descriptive, not tested",
            "event_days_vs_placebo": {"n": len(pairs),
                                      "median_event": statistics.median(p[0] for p in pairs) if pairs else None,
                                      "median_placebo": statistics.median(p[1] for p in pairs) if pairs else None,
                                      "share_event_higher": sum(p[0] > p[1] for p in pairs) / len(pairs) if pairs else None},
            "by_volatility_tercile_median": {k: statistics.median(v) if v else None for k, v in
                                             zip(("low", "mid", "high"), terc.values())}}


def run(cache=None):
    if cache:
        data.CACHE = cache
    reader = hypogen.Reader(hypogen.SCREEN)                   # get=None: never a request
    hlr = HLReader(hypogen.SCREEN)
    syms = movescreen.universe()
    perp = {s: _series(reader, s, "klines") for s in syms}
    spot = {s: _series(reader, s, "spot") for s in syms}
    fund = {s: m21hscreen.funding(reader, s) for s in syms}
    hl = {s: hlr.series(s, "klines", hlr.a, hlr.b - 1) for s in syms}
    files = sorted(reader.files, key=lambda f: f["file"])
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        commit = None
    return {"rule": RULE, "method": METHOD, "code_commit": commit, "symbols": len(syms),
            "symbols_with_spot": sum(1 for v in spot.values() if v), "files": len(files),
            "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(),
            "results": [s1(perp, spot, reader.a, reader.b), s2(perp, spot, fund, reader.a, reader.b)],
            "spread_regimes": spread_regimes(hl, perp)}


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
