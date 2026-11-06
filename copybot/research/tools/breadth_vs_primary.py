"""Director order 48 P2: broad screening vs one primary hypothesis per family (synthetic only; no alpha, no data).

Question (ChatGPT, INBOX 06/11): does the factory find more real, independent mechanisms by fixing ONE economically
motivated primary hypothesis per family before the test than by testing hundreds of correlated variants?

Worlds: n assets x T days with a market factor, Student-t shocks and a volatility regime (as research/tools/
hypo_engine.py). There are F = 8 mechanism families, each with its own observed persistent characteristic z_f (AR(1),
phi 0.9). In a world, M of the families are real: z_f at a TRUE LAG drawn at random from 1..6 shifts the next return by
ic * sigma_t * z_f. The other families are pure noise.

Variants per family: signal = mean of z_f over m days ending k days before the trade, k in 1..6, m in
{1, 2, 3, 5, 8, 13, 21}: 42 strongly correlated variants per family, 336 in total.

Approaches (all trade tercile long-short, 5 bp per unit of turnover, one-sided HAC t on the net daily mean, net > 0
required):
- A "broad": all 336 variants on the full window, Holm at 0.05 over 336. A family counts as found if any of its
  variants is selected.
- B "primary": one variant per family fixed BEFORE data by a rule that does not know the true lag (k = 1, m = 3: the
  most recent information, lightly smoothed), Holm at 0.05 over 8.
- C "explore -> confirm": first half of the window: pick each family's best variant by net t (exploration, no
  correction, never evidence); second half: test only the 8 picks, Holm at 0.05 over 8.

Metrics at the MECHANISM level: family-wise error (any noise family declared), power (share of real families found),
real and false mechanisms per world, Wilson 95 % intervals, and compute cost (portfolio evaluations, seconds).

    python3 research/tools/breadth_vs_primary.py [--reps N] [--procs K]   # -> research/data/breadth_vs_primary/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import hypo_engine as he  # noqa: E402

OUT = os.path.join(HERE, "research", "data", "breadth_vs_primary")
F, KS, MS = 8, list(range(1, 7)), [1, 2, 3, 5, 8, 13, 21]
PRIMARY = (1, 3)
COST, START, ALPHA = 0.0005, 30, 0.05


def world(seed, n=24, T=500, M=3, ic=0.03, rho=0.4, df=5.0, sigma=0.03, phi=0.9):
    rng = random.Random(seed)
    real = sorted(rng.sample(range(F), M)) if ic > 0 and M > 0 else []
    lags = {f: rng.randint(1, 6) for f in real}

    def tdraw():
        chi = sum(rng.gauss(0, 1) ** 2 for _ in range(int(df)))
        return rng.gauss(0, 1) / math.sqrt(chi / int(df)) * math.sqrt((df - 2) / df)

    state, s_t = 0, []
    for _ in range(T):
        if rng.random() < 0.02:
            state = 1 - state
        s_t.append(sigma * (2.0 if state else 1.0))
    z = [[[0.0] * T for _ in range(n)] for _ in range(F)]
    for f in range(F):
        for i in range(n):
            x = rng.gauss(0, 1)
            for t in range(T):
                x = phi * x + math.sqrt(1 - phi * phi) * rng.gauss(0, 1)
                z[f][i][t] = x
    r = [[0.0] * T for _ in range(n)]
    for t in range(T):
        m = tdraw()
        for i in range(n):
            v = s_t[t] * (math.sqrt(rho) * m + math.sqrt(1 - rho) * tdraw())
            for f in real:
                if t - lags[f] >= 0:
                    v += ic * s_t[t] * z[f][i][t - lags[f]]
            r[i][t] = v
    Z = [[[0.0] * (T + 1) for _ in range(n)] for _ in range(F)]
    for f in range(F):
        for i in range(n):
            acc = 0.0
            for t in range(T):
                acc += z[f][i][t]
                Z[f][i][t + 1] = acc
    return {"r": r, "Z": Z, "real": real, "lags": lags, "n": n, "T": T}


def net_series(w, f, k, m, lo, hi):
    """Daily net returns of the tercile long-short on family f's variant (k, m) for days lo..hi-1."""
    r, Zf, n = w["r"], w["Z"][f], w["n"]
    out, prev = [], {}
    for t in range(lo, hi):
        a, b = t - k - m + 1, t - k + 1
        if a < 0:
            out.append(0.0)
            continue
        xs = sorted(((Zf[i][b] - Zf[i][a]) / m, i) for i in range(n))
        q = n // 3
        wts = {i: -1.0 / q for _, i in xs[:q]}
        wts.update({i: 1.0 / q for _, i in xs[-q:]})
        g = sum(wv * r[i][t] for i, wv in wts.items())
        turn = sum(abs(wts.get(i, 0.0) - prev.get(i, 0.0)) for i in set(wts) | set(prev))
        prev = wts
        out.append(g - COST * turn)
    return out


def test(x):
    t, mean = he.hac_t(x)
    return he.p_one(t), mean, t


def one(args):
    name, rep, n, T, M, ic = args
    seed = int(hashlib.sha256(f"p48|{name}|{rep}".encode()).hexdigest()[:12], 16)
    w = world(seed, n=n, T=T, M=M, ic=ic)
    real = set(w["real"])
    res = {}

    # A: broad, all variants, full window, Holm over F * 42
    t0 = time.process_time()
    rows = []
    for f in range(F):
        for k in KS:
            for m in MS:
                p, mean, _ = test(net_series(w, f, k, m, START, T))
                rows.append((f, p, mean))
    sel = he.holm([p for _, p, _ in rows])
    fam = {f for (f, p, mean), s in zip(rows, sel) if s and mean > 0}
    res["A"] = {"found": fam, "evals": len(rows), "cpu": time.process_time() - t0}

    # B: one pre-fixed primary per family, Holm over F
    t0 = time.process_time()
    rows = [(f,) + test(net_series(w, f, PRIMARY[0], PRIMARY[1], START, T))[:2] for f in range(F)]
    sel = he.holm([p for _, p, _ in rows])
    res["B"] = {"found": {f for (f, p, mean), s in zip(rows, sel) if s and mean > 0}, "evals": F,
                "cpu": time.process_time() - t0}

    # C: explore first half (best net t per family), confirm the pick on the second half, Holm over F
    t0 = time.process_time()
    mid = (START + T) // 2
    picks = {}
    for f in range(F):
        best = None
        for k in KS:
            for m in MS:
                _, _, tt = test(net_series(w, f, k, m, START, mid))
                if best is None or tt > best[0]:
                    best = (tt, k, m)
        picks[f] = best[1:]
    rows = [(f,) + test(net_series(w, f, picks[f][0], picks[f][1], mid, T))[:2] for f in range(F)]
    sel = he.holm([p for _, p, _ in rows])
    res["C"] = {"found": {f for (f, p, mean), s in zip(rows, sel) if s and mean > 0}, "evals": F * 42 + F,
                "cpu": time.process_time() - t0, "pick_lag_right": sum(picks[f][0] == w["lags"][f] for f in real)}
    out = {"scenario": name, "rep": rep, "real": sorted(real)}
    for a, v in res.items():
        out[a] = {"true": len(v["found"] & real), "false": len(v["found"] - real), "evals": v["evals"],
                  "cpu": round(v["cpu"], 4)}
    out["C"]["pick_lag_right"] = res["C"]["pick_lag_right"]
    return out


SCENARIOS = {"null": (3, 0.0), "ic_0.015": (3, 0.015), "ic_0.02": (3, 0.02), "ic_0.03": (3, 0.03)}


def summarise(rows, M, ic):
    out = {}
    for a in ("A", "B", "C"):
        fw = sum(r[a]["false"] > 0 for r in rows)
        tot_true = sum(r[a]["true"] for r in rows)
        possible = len(rows) * (M if ic > 0 else 0)
        out[a] = {"fwer_mechanisms": fw / len(rows), "fwer_ci95": he.wilson(fw, len(rows)),
                  "power": (tot_true / possible) if possible else None,
                  "power_ci95": he.wilson(tot_true, possible) if possible else None,
                  "true_per_world": tot_true / len(rows), "false_per_world": sum(r[a]["false"] for r in rows) / len(rows),
                  "evals_per_world": rows[0][a]["evals"], "cpu_s_per_world": sum(r[a]["cpu"] for r in rows) / len(rows)}
    if ic > 0:
        out["C"]["pick_lag_right_share"] = sum(r["C"]["pick_lag_right"] for r in rows) / (len(rows) * M)
        # cluster-robust interval: the world is the unit (mechanisms in one world share returns); percentile
        # bootstrap over worlds, 2,000 draws, fixed seed
        rng = random.Random(48)
        for a in ("A", "B", "C"):
            per = [r[a]["true"] / M for r in rows]
            boots = sorted(sum(rng.choice(per) for _ in per) / len(per) for _ in range(2000))
            out[a]["power_ci95_cluster"] = (boots[49], boots[1949])
        diffs = [(r["B"]["true"] - r["A"]["true"]) / M for r in rows]
        bd = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(2000))
        out["B_minus_A_power"] = {"mean": sum(diffs) / len(diffs), "ci95_cluster": (bd[49], bd[1949])}
    out["per_world"] = [{a: r[a]["true"] for a in ("A", "B", "C")} | {f"{a}_false": r[a]["false"]
                                                                     for a in ("A", "B", "C")} for r in rows]
    return out


def build(reps=100, n=24, T=500, procs=4):
    jobs = [(s, i, n, T, M, ic) for s, (M, ic) in SCENARIOS.items() for i in range(reps)]
    t0 = time.time()
    if procs > 1:
        with Pool(procs) as pool:
            res = pool.map(one, jobs, chunksize=2)
    else:
        res = [one(j) for j in jobs]
    by = {}
    for r in res:
        by.setdefault(r["scenario"], []).append(r)
    return {"schema": "copybot.breadth_vs_primary/1", "rule": "research/reviews/INBOX.md director order 48 P2",
            "families": F, "variants_per_family": len(KS) * len(MS), "primary": PRIMARY, "n_assets": n, "days": T,
            "alpha": ALPHA, "cost_per_turnover": COST, "reps": reps, "wall_seconds": round(time.time() - t0, 1),
            "scenarios": {s: {"real_families": SCENARIOS[s][0] if SCENARIOS[s][1] else 0, "ic": SCENARIOS[s][1],
                              **summarise(by[s], *SCENARIOS[s])} for s in SCENARIOS}}


def md(rep, digest):
    L = ["# Broad screening vs one primary per family (order 48 P2, synthetic)", "",
         f"sha256 `{digest}`; {rep['families']} families x {rep['variants_per_family']} variants, {rep['reps']} worlds "
         f"per scenario, {rep['n_assets']} assets x {rep['days']} days, primary (k, m) = {tuple(rep['primary'])}, "
         f"wall {rep['wall_seconds']} s.", "",
         "| Scenario | Approach | FWER (mechanisms) [95 % CI] | Power per real mechanism [95 % CI] | Real found / world | "
         "False / world | Evaluations / world | CPU s / world |", "|---|---|---|---|---|---|---|---|"]

    def ci(c):
        return "—" if not c or c[0] is None else f"[{c[0]:.3f}, {c[1]:.3f}]"
    for s, o in rep["scenarios"].items():
        for a in ("A", "B", "C"):
            x = o[a]
            pw = "—" if x["power"] is None else f"{x['power']:.3f} {ci(x['power_ci95'])}"
            L.append(f"| {s} | {a} | {x['fwer_mechanisms']:.3f} {ci(x['fwer_ci95'])} | {pw} | "
                     f"{x['true_per_world']:.2f} | {x['false_per_world']:.3f} | {x['evals_per_world']} | "
                     f"{x['cpu_s_per_world']:.2f} |")
    L += ["", "World-clustered 95 % intervals for power (bootstrap over worlds) and B - A:", ""]
    for s, o in rep["scenarios"].items():
        if "B_minus_A_power" in o:
            cl = ", ".join(f"{a} {ci(o[a]['power_ci95_cluster'])}" for a in ("A", "B", "C"))
            d = o["B_minus_A_power"]
            L.append(f"- {s}: {cl}; B - A {d['mean']:+.3f} {ci(d['ci95_cluster'])}")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args(argv)
    rep = build(reps=a.reps, procs=a.procs)
    os.makedirs(OUT, exist_ok=True)
    body = json.dumps(rep, sort_keys=True, indent=1) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as f:
        f.write(body)
    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8") as f:
        f.write(md(rep, digest))
    print(md(rep, digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
