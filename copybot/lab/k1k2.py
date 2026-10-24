"""PROTOCOL_V3 amendment 21y sections C-E (and its precision): K1 and K2 as forward screenings.

Read-only from the scanner's observations (one per market hour, earliest scan) and settled funding. Before 12 complete
weekends nothing is estimated: only counts and data quality are returned (NO_DECISION). No LÅS, no alpha.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import statistics
import time

from lab import edgemonitor, fundsettle, moves, sessions

DET, H = "abnormal_move/1", 3600
MAX_SCAN_DELAY_S, MIN_WEEKEND_HOURS, MIN_WEEKENDS = 600, 44, 12
P_SCREEN, P_PLACEBO, PERMS, SEED, MIN_SHIFT = 0.005, 0.05, 1000, 21, 3
FEE = 0.0004                        # TradFi taker promotion (21g); 0.0005 if the promotion ends (21y D)
DEADLINE = dt.date(2027, 3, 31)
EARLIEST = "2027-01-18"
K1_SYMS, PLACEBO = ("SPYUSDT", "QQQUSDT"), ("BTCUSDT", "ETHUSDT")
K2_SYMS = tuple(s for s, v in moves.WATCH.items() if v[0] != "crypto")
RULE = "research/PROTOCOL_V3.md amendment 21y"


def _p(raw):
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def hours(db, sym):
    """{open_s: hour} from the earliest scan of each market hour, with its usability (21y C)."""
    bad = {r["ts"] for r in db.q("SELECT ts FROM observations WHERE detector=? AND instrument=? AND metric IN "
                                 "('error', 'history_short')", DET, sym)}
    book = {}
    for r in db.q("SELECT ts, value FROM observations WHERE detector=? AND instrument=? AND metric='book_rt'", DET, sym):
        book.setdefault(r["ts"], r["value"])
    out = {}
    for r in db.q("SELECT ts, payload FROM observations WHERE detector=? AND instrument=? AND metric='z_1h' "
                  "ORDER BY ts, id", DET, sym):
        p = _p(r["payload"])
        o = p.get("open_s")
        if o is None or o in out:
            continue
        ts = r["ts"]
        usable = (ts - p["close_s"] <= MAX_SCAN_DELAY_S and (p.get("quality") or {}).get("missing_bars", 0) == 0
                  and not any(abs(ts - b) <= 60 for b in bad) and p.get("mark") and p.get("index"))
        out[o] = {"open_s": o, "scan_ts": ts, "ret_1h": p.get("ret_1h"), "close": p.get("price"), "mark": p.get("mark"),
                  "index": p.get("index"), "sigma_1h": p.get("sigma_1h"), "book_rt": book.get(ts),
                  "premium": ((p["mark"] - p["index"]) / p["index"]) if p.get("index") else None,
                  "usable": bool(usable)}
    return out


def _weekend_of(t):
    """21y precision 3: the Saturday (UTC date) of the bar's UTC week for Fri, Sat and Sun bars."""
    u = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    shift = {4: 1, 5: 0, 6: -1}.get(u.weekday())
    return None if shift is None else (u.date() + dt.timedelta(days=shift)).isoformat()


def holm(ps):
    """Holm-adjusted p-values in input order."""
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def t_greater(xs):
    """One-sided p for mean > 0 (Student's t, df = n - 1)."""
    if len(xs) < 2 or statistics.stdev(xs) == 0:
        return None
    t = statistics.mean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs)))
    return 1 - edgemonitor.t_cdf(t, len(xs) - 1)


def wilcoxon_greater(ds):
    """One-sided signed-rank p for median d > 0, normal approximation, zeros dropped, average ranks for ties."""
    ds = [d for d in ds if d != 0]
    n = len(ds)
    if n < 2:
        return None
    order = sorted(range(n), key=lambda i: abs(ds[i]))
    ranks, i = [0.0] * n, 0
    while i < n:
        j = i
        while j + 1 < n and abs(ds[order[j + 1]]) == abs(ds[order[i]]):
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    w = sum(r for r, d in zip(ranks, ds) if d > 0)
    if n <= 25:                                   # 21y precision 2: exact null distribution over 2^n sign patterns
        dist = {0: 1}
        for r in ranks:
            r2 = int(round(2 * r))                # doubled ranks are integers even with midranks
            nxt = dict(dist)
            for k, c in dist.items():
                nxt[k + r2] = nxt.get(k + r2, 0) + c
            dist = nxt
        w2 = int(round(2 * w))
        return sum(c for k, c in dist.items() if k >= w2) / 2 ** n
    mu, sd = n * (n + 1) / 4, math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    return 1 - 0.5 * (1 + math.erf((w - mu) / sd / math.sqrt(2)))


def _gate(complete, now):
    if len(complete) >= MIN_WEEKENDS:
        return None
    status = "UNTESTABLE" if dt.datetime.fromtimestamp(now, dt.timezone.utc).date() > DEADLINE else "NO_DECISION"
    return {"status": status, "complete_weekends": len(complete), "needed": MIN_WEEKENDS, "earliest_test": EARLIEST,
            "why": f"{len(complete)} af {MIN_WEEKENDS} komplette weekender; ingen statistik før (21y)"}


# ---------------- K1 ----------------

def k1_pairs(btc, x, fee=FEE):
    """Signal from BTC bar b, mark-to-mark outcome over bar b+1 after both scans of bar b (21y D)."""
    out, no_cost = [], 0
    for b in sorted(btc):
        sb, xb, xn = btc[b], x.get(b), x.get(b + H)
        if not (xb and xn and sb["usable"] and xb["usable"] and xn["usable"]) or sb["ret_1h"] in (None, 0):
            continue
        if xb["scan_ts"] < sb["scan_ts"]:
            continue                                            # point in time: entry after the signal is known
        if xb["book_rt"] is None:
            no_cost += 1
            continue                                            # precision 1: no guessed cost
        s = 1 if sb["ret_1h"] > 0 else -1
        y = math.log(xn["mark"] / xb["mark"])
        c = 2 * fee + xb["book_rt"]
        out.append({"b": b, "s": s, "y": y, "c": c, "gross": s * y, "net": s * y - c,
                    "session": sessions.equity(b + H), "weekend": sessions.weekend_key(b + H)})
    return out, no_cost


def complete_weekends(hmaps, closed_of):
    """Weekends with >= 44 usable closed hours in every market of `hmaps` (21y C)."""
    per = {}
    for hm in hmaps:
        cnt = {}
        for o, h in hm.items():
            w = closed_of(o)
            if w and h["usable"]:
                cnt[w] = cnt.get(w, 0) + 1
        per[id(hm)] = cnt
    keys = set.intersection(*(set(c) for c in per.values())) if per else set()
    return sorted(w for w in keys if all(per[id(hm)].get(w, 0) >= MIN_WEEKEND_HOURS for hm in hmaps))


def _wk_means(pairs, field):
    by = {}
    for p in pairs:
        by.setdefault(p["weekend"], []).append(p[field])
    return [statistics.mean(v) for _, v in sorted(by.items())]


def k1(db, now=None, min_weekends=MIN_WEEKENDS):
    now = now or time.time()
    btc = hours(db, "BTCUSDT")
    xs = {s: hours(db, s) for s in K1_SYMS}
    eq_weekend = lambda o: sessions.weekend_key(o) if sessions.equity(o) == sessions.WEEKEND else None
    complete = complete_weekends([btc] + list(xs.values()), eq_weekend)
    base = {"rule": RULE + " D", "usable_hours": {s: sum(h["usable"] for h in hm.values())
                                                  for s, hm in [("BTCUSDT", btc)] + list(xs.items())}}
    gate = _gate(complete, now) if min_weekends == MIN_WEEKENDS else (
        None if len(complete) >= min_weekends else {"status": "NO_DECISION", "complete_weekends": len(complete)})
    if gate:
        return {**base, **gate}
    res, ps = {}, []
    for sym, x in xs.items():
        pairs, no_cost = k1_pairs(btc, x)
        wk = [p for p in pairs if p["session"] == sessions.WEEKEND and p["weekend"] in complete]
        rth = [p for p in pairs if p["session"] == sessions.RTH]
        means = _wk_means(wk, "net")
        p = t_greater(means)
        rng, obs = random.Random(SEED), statistics.mean(means) if means else None
        by = {}
        for q in wk:
            by.setdefault(q["weekend"], []).append(q)
        hits = 0
        for _ in range(PERMS):
            sim = []
            for w, qs in sorted(by.items()):
                n = len(qs)
                k = rng.randint(MIN_SHIFT, n - MIN_SHIFT) if n > 2 * MIN_SHIFT else 0
                sig = [q["s"] for q in qs]
                sig = sig[k:] + sig[:k]
                sim.append(statistics.mean(sv * q["y"] - q["c"] for sv, q in zip(sig, qs)))
            hits += statistics.mean(sim) >= obs
        same = [(btc[o]["ret_1h"], x[o]["ret_1h"]) for o in x if o in btc and btc[o]["usable"] and x[o]["usable"]
                and sessions.equity(o) == sessions.WEEKEND and btc[o]["ret_1h"] is not None and x[o]["ret_1h"] is not None]
        res[sym] = {"n_pairs_weekend": len(wk), "n_weekends": len(means), "net_mean": obs, "p": p,
                    "p_perm": (hits + 1) / (PERMS + 1),
                    "gross_weekend": statistics.mean(q["gross"] for q in wk) if wk else None,
                    "gross_rth": statistics.mean(q["gross"] for q in rth) if rth else None,
                    "corr_simultaneous": statistics.correlation(*zip(*same)) if len(same) > 2 else None,
                    "pairs_without_book": no_cost}
        ps.append(p if p is not None else 1.0)
    for sym, ph in zip(res, holm(ps)):
        r = res[sym]
        r["p_holm"] = ph
        r["checks"] = {"holm_p<=0.005": ph <= P_SCREEN, "net_mean>0": (r["net_mean"] or 0) > 0,
                       "p_perm<=0.05": r["p_perm"] <= P_PLACEBO,
                       "weekend>rth": r["gross_weekend"] is not None and r["gross_rth"] is not None
                       and r["gross_weekend"] > r["gross_rth"]}
        r["verdict"] = "PASS" if all(r["checks"].values()) else "SCREEN_FAIL"
    return {**base, "status": "PASS" if any(r["verdict"] == "PASS" for r in res.values()) else "SCREEN_FAIL",
            "complete_weekends": len(complete), "instruments": res,
            "note": "en PASS er kun en screening; validering kræver en ny dateret LÅS"}


# ---------------- K2 ----------------

def k2_weekend_d(hm, cls, w, closed_hours):
    """d_w = median |premium| closed - median |premium| open in the 5 trading days before (21y E)."""
    sat = dt.date.fromisoformat(w)
    first = min(o for o in closed_hours)
    lo = int(dt.datetime(sat.year, sat.month, sat.day, tzinfo=dt.timezone.utc).timestamp()) - 6 * 86400
    open_p = [abs(h["premium"]) for o, h in hm.items() if lo <= o < first and h["usable"] and h["premium"] is not None
              and sessions.opened(cls, o)]
    cl_p = [abs(hm[o]["premium"]) for o in closed_hours if hm[o]["premium"] is not None]
    if not open_p or not cl_p:
        return None
    return statistics.median(cl_p) - statistics.median(open_p)


def k2(db, now=None, min_weekends=MIN_WEEKENDS):
    now = now or time.time()
    out, ps, complete_any = {}, [], set()
    for sym in K2_SYMS + PLACEBO:
        cls = moves.WATCH[sym][0]
        win_cls = "equity_etf" if cls == "crypto" else cls                 # precision 4: placebo on equity windows
        hm = hours(db, sym)
        closed_of = lambda o, c=win_cls: (_weekend_of(o) if sessions.closed(c, o) else None)
        comp = complete_weekends([hm], closed_of)
        complete_any |= set(comp)
        entry = {"complete_weekends": len(comp), "usable_hours": sum(h["usable"] for h in hm.values())}
        if len(comp) < min_weekends:
            out[sym] = entry
            continue
        ds, carry, hits, n_sec = [], [], 0, 0
        for w in comp:
            ch = sorted(o for o, h in hm.items() if closed_of(o) == w and h["usable"])
            d = k2_weekend_d(hm, win_cls, w, ch)
            if d is not None:
                ds.append(d)
            e = hm[ch[0]]
            if e["premium"] and e["book_rt"] is not None:
                pos = -1 if e["premium"] > 0 else 1                       # precision 5: against the premium
                fund = sum(-pos * r for _, r in fundsettle.settled(db, sym, ch[0], ch[-1] + H))
                carry.append(fund - (2 * FEE + e["book_rt"]))
            last = hm[ch[-1]]
            nxt = next((hm[o] for o in sorted(hm) if o > ch[-1] and hm[o]["usable"] and sessions.opened(win_cls, o)), None)
            if nxt and last["premium"] and last["close"] and nxt["close"]:
                gap = math.log(nxt["close"] / last["close"])
                if gap:
                    n_sec += 1
                    hits += (gap > 0) == (last["premium"] > 0)
        entry.update({"d": ds, "p": wilcoxon_greater(ds), "median_d": statistics.median(ds) if ds else None,
                      "carry_net_mean": statistics.mean(carry) if carry else None, "carry_n": len(carry),
                      "premium_predicts_gap": {"hits": hits, "n": n_sec}})
        out[sym] = entry
    tested = [s for s in K2_SYMS if "p" in out[s]]
    if not tested:
        gate = _gate(sorted(complete_any), now) if min_weekends == MIN_WEEKENDS else {"status": "NO_DECISION"}
        return {"rule": RULE + " E", **(gate or {"status": "NO_DECISION"}), "instruments": out}
    for s, ph in zip(tested, holm([out[s]["p"] if out[s]["p"] is not None else 1.0 for s in tested])):
        out[s]["p_holm"] = ph
    placebo_ok = all(out[s].get("complete_weekends", 0) >= min_weekends and "d" in out[s]   # precision 2
                     and (out[s]["p"] is None or out[s]["p"] > P_PLACEBO) for s in PLACEBO)
    for s in tested:
        r = out[s]
        r["checks"] = {"holm_p<=0.005": r["p_holm"] <= P_SCREEN, "placebo_p>0.05": placebo_ok,
                       "carry>cost": (r["carry_net_mean"] or 0) > 0}
        r["verdict"] = ("PASS" if all(r["checks"].values()) else
                        "SCREEN_FAIL (mekanisme bekræftet, ingen handlebar carry)"
                        if r["checks"]["holm_p<=0.005"] and placebo_ok else "SCREEN_FAIL")
    return {"rule": RULE + " E", "status": "PASS" if any(out[s]["verdict"] == "PASS" for s in tested) else "SCREEN_FAIL",
            "instruments": out, "note": "en PASS er kun en screening; validering kræver en ny dateret LÅS"}


def status(db, now=None):
    """Counts only, for the dashboard: never a statistic before 12 complete weekends."""
    now = now or time.time()
    a, b = k1(db, now), k2(db, now)
    strip = lambda r: {k: v for k, v in r.items() if k in ("status", "complete_weekends", "needed", "earliest_test",
                                                             "why", "usable_hours", "rule")}
    return {"K1": strip(a), "K2": {**strip(b), "complete_weekends": max(
        (v.get("complete_weekends", 0) for v in b.get("instruments", {}).values()), default=0)}}
