"""Director order 47 P1: hypothesis engine with falsification control, on SYNTHETIC data only.

The engine proposes candidates across a synthetic cross-section, evaluates them, and reports how often the decision
rule is fooled. It never approves, freezes or promotes anything: proposals enter a factory Register
(research/tools/factory.py) as PROPOSED, and only a human actor can move them on.

Synthetic worlds (`world`): n assets x T days; a common market factor (correlation rho), Student-t shocks (fat tails),
a two-state volatility regime, randomly missing returns, and optionally a planted signal: an observed, persistent
characteristic z (AR(1)) that shifts the next day's return by ic * sigma_t * z. Without a planted signal z is pure
noise, so every candidate is a true null.

Candidates (`grid`): cross-sectional long-short terciles on signals that use only returns before the traded day:
momentum (lookbacks 5..120), short-term reversal (1..8), low volatility (5..60), the characteristic z at lags 1..6,
plus one deliberately leaking candidate that uses the traded day's own return. Variants of a family are strongly
correlated; they are not independent discoveries.

Decision rule (`evaluate`): a candidate can only be SELECTED if (1) the exact truncation test finds no look-ahead,
(2) its mean NET daily return (after costs per unit of turnover) is positive, and (3) its one-sided HAC (Newey-West)
p-value survives the multiple-testing correction across all candidates of the batch. Holm controls the family-wise
error rate (FWER); Benjamini-Hochberg (FDR) and Bonferroni at the effective number of trials (N_eff, Bailey and Lopez
de Prado 2014) are reported beside it. A SELECTED candidate is a proposal for a human pre-registration, never evidence.

Priority (`priority`) ranks proposals by information value and falsifiability (expected power from the number of
usable observations, discounted by the number of rejected hypotheses in the same lineage), never by expected return.

    python3 research/tools/hypo_engine.py [--reps N] [--procs K]     # -> research/data/hypo_engine/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # copybot/
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import factory as fa  # noqa: E402

OUT = os.path.join(HERE, "research", "data", "hypo_engine")
ALPHA, Q_FDR, NW_LAGS = 0.05, 0.10, 5

FAMILIES = {
    "mom": {"lookbacks": list(range(5, 125, 5)), "tag": "cross_sectional_momentum",
            "mechanism": "slow diffusion of information: past winners keep outperforming",
            "falsifier": "net long-short return of past winners minus losers <= 0 after costs",
            "not_arbitraged": "capacity limits and crash risk keep arbitrageurs out (UNKNOWN in crypto)",
            "costs": "monthly-ish turnover; short legs need borrow/perps; crowding in large coins"},
    "rev": {"lookbacks": list(range(1, 9)), "tag": "short_term_reversal_liquidity",
            "mechanism": "liquidity providers are paid for absorbing short-term order imbalance",
            "falsifier": "net return of buying recent losers and selling recent winners <= 0 after costs",
            "not_arbitraged": "the premium is a fee for capital at risk; it shrinks with competition",
            "costs": "daily turnover; costs usually exceed the gross premium in liquid markets"},
    "vol": {"lookbacks": list(range(5, 65, 5)), "tag": "low_volatility_anomaly",
            "mechanism": "leverage-constrained or lottery-seeking traders overpay for volatile assets",
            "falsifier": "net return of low-minus-high volatility <= 0 after costs",
            "not_arbitraged": "benchmarked and leverage-constrained investors cannot exploit it",
            "costs": "low turnover; short leg in volatile coins is expensive to hold"},
    "char": {"lookbacks": list(range(1, 7)), "tag": "synthetic_characteristic",
             "mechanism": "SYNTHETIC: an observed persistent characteristic shifts next-day returns (planted or noise)",
             "falsifier": "net long-short return on the characteristic <= 0 after costs",
             "not_arbitraged": "synthetic placeholder; a real family must argue this before pre-registration",
             "costs": "turnover set by the characteristic's persistence"},
    "leak": {"lookbacks": [0], "tag": "synthetic_leak",
             "mechanism": "DELIBERATE LOOK-AHEAD: uses the traded day's own return",
             "falsifier": "must be rejected by the truncation test before any statistic is read",
             "not_arbitraged": "not applicable", "costs": "not applicable"},
}


# ---------------------------------------------------------------- synthetic worlds

def world(seed, n=24, T=500, rho=0.4, df=5.0, sigma=0.03, regime=True, missing=0.01, ic=0.0, phi=0.9):
    """Returns r[i][t] (None = missing) and the observed characteristic z[i][t]."""
    rng = random.Random(seed)

    def tdraw():
        if df is None:
            return rng.gauss(0, 1)
        chi = sum(rng.gauss(0, 1) ** 2 for _ in range(int(df)))
        return rng.gauss(0, 1) / math.sqrt(chi / int(df)) * math.sqrt((df - 2) / df)

    state, s_t = 0, []
    for _ in range(T):
        if regime and rng.random() < 0.02:
            state = 1 - state
        s_t.append(sigma * (2.0 if state else 1.0))
    z = [[0.0] * T for _ in range(n)]
    for i in range(n):
        x = rng.gauss(0, 1)
        for t in range(T):
            x = phi * x + math.sqrt(1 - phi * phi) * rng.gauss(0, 1)
            z[i][t] = x
    r = [[0.0] * T for _ in range(n)]
    for t in range(T):
        m = tdraw()
        for i in range(n):
            v = s_t[t] * (math.sqrt(rho) * m + math.sqrt(1 - rho) * tdraw())
            if ic and t > 0:
                v += ic * s_t[t] * z[i][t - 1]
            r[i][t] = None if rng.random() < missing else v
    return {"r": r, "z": z, "sigma": s_t, "seed": seed, "ic": ic}


def prefix(r):
    n, T = len(r), len(r[0])
    P = [[0.0] * (T + 1) for _ in range(n)]
    Q = [[0.0] * (T + 1) for _ in range(n)]
    M = [[0] * (T + 1) for _ in range(n)]
    for i in range(n):
        for t in range(T):
            v = r[i][t]
            P[i][t + 1] = P[i][t] + (v or 0.0)
            Q[i][t + 1] = Q[i][t] + (v or 0.0) ** 2
            M[i][t + 1] = M[i][t] + (v is None)
    return P, Q, M


def grid(families=("mom", "rev", "vol", "char", "leak")):
    return [(f, L) for f in families for L in FAMILIES[f]["lookbacks"]]


def signal(fam, L, w, pre, i, t):
    """Signal of asset i for a position held during day t (None = not usable). Uses data before t only, except the
    deliberate leak."""
    P, Q, M = pre
    r, z = w["r"], w["z"]
    if fam == "leak":
        return r[i][t]
    if fam == "char":
        return z[i][t - L] if t - L >= 0 else None
    if t - L < 0 or M[i][t] - M[i][t - L] > 0.2 * L:
        return None
    s = P[i][t] - P[i][t - L]
    if fam == "mom":
        return s
    if fam == "rev":
        return -s
    mean = s / L
    var = (Q[i][t] - Q[i][t - L]) / L - mean * mean
    return -math.sqrt(max(var, 0.0))


def portfolio(fam, L, w, pre, start, cost):
    """Daily gross and net long-short tercile returns and turnover, positions decided before each day."""
    r = w["r"]
    n, T = len(r), len(r[0])
    gross, net, prev = [], [], {}
    for t in range(start, T):
        xs = [(s, i) for i in range(n) if r[i][t] is not None
              for s in (signal(fam, L, w, pre, i, t),) if s is not None]
        if len(xs) < 6:
            gross.append(0.0)
            net.append(0.0)
            continue
        xs.sort()
        k = len(xs) // 3
        wts = {i: -1.0 / k for _, i in xs[:k]}
        wts.update({i: 1.0 / k for _, i in xs[-k:]})
        g = sum(wv * r[i][t] for i, wv in wts.items())
        turn = sum(abs(wts.get(i, 0.0) - prev.get(i, 0.0)) for i in set(wts) | set(prev))
        prev = wts
        gross.append(g)
        net.append(g - cost * turn)
    return gross, net


def truncation_leak(fam, L, w, seed, samples=5):
    """Exact truncation test: replace every return from day t on with fresh noise; a signal for day t that changes
    uses the future."""
    rng = random.Random(seed)
    T = len(w["r"][0])
    pre = prefix(w["r"])
    for _ in range(samples):
        t = rng.randrange(130, T - 1)
        r2 = [row[:t] + [rng.gauss(0, 0.03) for _ in range(T - t)] for row in w["r"]]
        w2 = {**w, "r": r2}
        pre2 = prefix(r2)
        for i in range(len(r2)):
            a, b = signal(fam, L, w, pre, i, t), signal(fam, L, w2, pre2, i, t)
            if a != b:
                return True
    return False


# ---------------------------------------------------------------- statistics

def hac_t(x, lags=NW_LAGS):
    n = len(x)
    m = math.fsum(x) / n
    d = [v - m for v in x]
    g0 = math.fsum(v * v for v in d) / n
    s = g0
    for k in range(1, lags + 1):
        gk = math.fsum(d[t] * d[t - k] for t in range(k, n)) / n
        s += 2 * (1 - k / (lags + 1)) * gk
    se = math.sqrt(max(s, 1e-30) / n)
    return m / se, m


def p_one(tstat):
    return 0.5 * math.erfc(tstat / math.sqrt(2))


def holm(ps, alpha=ALPHA):
    order = sorted(range(len(ps)), key=lambda j: ps[j])
    rej = [False] * len(ps)
    m = len(ps)
    for k, j in enumerate(order):
        if ps[j] <= alpha / (m - k):
            rej[j] = True
        else:
            break
    return rej


def bh(ps, q=Q_FDR):
    order = sorted(range(len(ps)), key=lambda j: ps[j])
    m, kmax = len(ps), -1
    for k, j in enumerate(order):
        if ps[j] <= (k + 1) * q / m:
            kmax = k
    rej = [False] * len(ps)
    for k in range(kmax + 1):
        rej[order[k]] = True
    return rej


def effective_trials(series):
    from lab.engine.pbo import effective_trials as et
    return et(series)["n_eff"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, c - h), min(1.0, c + h))


# ---------------------------------------------------------------- engine

def evaluate(w, cands, cost, start=125, seed=0):
    rows, nets = [], []
    pre = prefix(w["r"])
    for j, (fam, L) in enumerate(cands):
        leak = truncation_leak(fam, L, w, seed * 1000 + j)
        gross, net = portfolio(fam, L, w, pre, start, cost)
        tg, mg = hac_t(gross)
        tn, mn = hac_t(net)
        rows.append({"fam": fam, "L": L, "leak": leak, "gross_mean": mg, "net_mean": mn, "p_gross": p_one(tg),
                     "p_net": p_one(tn)})
        nets.append(net)
    ps = [x["p_net"] for x in rows]
    h, b = holm(ps), bh(ps)
    neff = effective_trials(nets)
    for x, hj, bj in zip(rows, h, b):
        ok = (not x["leak"]) and x["net_mean"] > 0
        x["raw"] = ok and x["p_net"] <= ALPHA
        x["holm"] = ok and hj
        x["bh"] = ok and bj
        x["bonf_neff"] = ok and x["p_net"] <= ALPHA / max(neff, 1.0)
        x["gross_sig_cost_killed"] = (not x["leak"]) and x["p_gross"] <= ALPHA and x["net_mean"] <= 0
    return rows, neff


def priority(fam, n_obs, rejected_in_lineage, sd_daily=0.03, min_effect=0.0005):
    """Information value, not expected return: approximate power to see a `min_effect` daily mean with n_obs days at
    one-sided alpha, discounted by the lineage's rejection count (each rejection lowers the prior)."""
    zcrit = 1.6448536269514722
    power = 0.5 * math.erfc(-(min_effect / (sd_daily / math.sqrt(max(n_obs, 1))) - zcrit) / math.sqrt(2))
    return round(power / (1 + rejected_in_lineage), 6)


def propose(register, cands, ts, lineage_rejections, n_obs):
    """Enter candidates as PROPOSED factory records with the order's falsification fields. Returns the ids."""
    ids = []
    for fam, L in cands:
        meta = FAMILIES[fam]
        hid = f"SYN_{fam}_{L}"
        lin, _ = fa.lineage_of(meta["tag"], register.lmap)
        register.propose(hid, {"family": fam, "mechanism": meta["mechanism"], "mechanism_tag": meta["tag"],
                               "direction": 1, "universe": ["synthetic"], "estimand": f"net mean daily {fam} L={L}",
                               "falsifier": meta["falsifier"], "not_arbitraged": meta["not_arbitraged"],
                               "costs_capacity": meta["costs"],
                               "similar_rejected": lineage_rejections.get(lin, 0),
                               "priority": priority(fam, n_obs, lineage_rejections.get(lin, 0))}, ts)
        ids.append(hid)
    return ids


# ---------------------------------------------------------------- Monte Carlo

SCENARIOS = {
    "null_base": {"ic": 0.0, "cost": 0.0005, "df": 5.0, "regime": True, "missing": 0.01, "rho": 0.4},
    "null_gauss_calm": {"ic": 0.0, "cost": 0.0005, "df": None, "regime": False, "missing": 0.0, "rho": 0.4},
    "null_fat_regime": {"ic": 0.0, "cost": 0.0005, "df": 3.0, "regime": True, "missing": 0.05, "rho": 0.7},
    "signal": {"ic": 0.03, "cost": 0.0005, "df": 5.0, "regime": True, "missing": 0.01, "rho": 0.4},
    "signal_cost_killed": {"ic": 0.015, "cost": 0.004, "df": 5.0, "regime": True, "missing": 0.01, "rho": 0.4},
}


def one_rep(args):
    name, rep, n, T = args
    sc = SCENARIOS[name]
    seed = int(hashlib.sha256(f"{name}|{rep}".encode()).hexdigest()[:12], 16)
    w = world(seed, n=n, T=T, rho=sc["rho"], df=sc["df"], regime=sc["regime"], missing=sc["missing"], ic=sc["ic"])
    rows, neff = evaluate(w, grid(), sc["cost"], seed=rep)
    return name, rows, neff


def summarise(name, reps):
    true_fam = {"char"} if SCENARIOS[name]["ic"] else set()
    out = {"scenario": SCENARIOS[name], "reps": len(reps)}
    tests = [x for rows, _ in reps for x in rows if x["fam"] != "leak"]
    nulls = [x for x in tests if x["fam"] not in true_fam]
    k = sum(x["p_net"] <= ALPHA for x in nulls)
    out["per_test_type1_net"] = {"rate": k / len(nulls), "ci95": wilson(k, len(nulls)), "n_tests": len(nulls),
                                 "note": "tests within a world are correlated; the interval treats them as "
                                         "independent and is too narrow"}
    for rule in ("raw", "holm", "bh", "bonf_neff"):
        fw = sum(any(x[rule] for x in rows if x["fam"] not in true_fam) for rows, _ in reps)
        sel = sum(sum(x[rule] for x in rows) for rows, _ in reps)
        false_sel = sum(sum(x[rule] for x in rows if x["fam"] not in true_fam) for rows, _ in reps)
        worlds_with_true = sum(any(x[rule] for x in rows if x["fam"] in true_fam) for rows, _ in reps)
        out[rule] = {"fwer": fw / len(reps), "fwer_ci95": wilson(fw, len(reps)),
                     "selected": sel, "false_selected": false_sel,
                     "fdp_pooled": (false_sel / sel) if sel else None,
                     "worlds_with_a_true_selection": worlds_with_true if true_fam else None}
    out["leak_caught"] = sum(all(x["leak"] for x in rows if x["fam"] == "leak") for rows, _ in reps) / len(reps)
    out["leak_false_alarm"] = sum(sum(x["leak"] for x in rows if x["fam"] != "leak") for rows, _ in reps)
    out["profit_pass_with_net_mean_le_0"] = sum(sum(x[r] and x["net_mean"] <= 0 for r in ("raw", "holm", "bh",
                                                                                          "bonf_neff"))
                                                for rows, _ in reps for x in rows)
    out["gross_significant_killed_by_costs"] = sum(sum(x["gross_sig_cost_killed"] for x in rows) for rows, _ in reps)
    out["n_eff_mean"] = sum(n for _, n in reps) / len(reps)
    return out


def build(reps=200, n=24, T=500, procs=4, scenarios=None):
    names = list(scenarios or SCENARIOS)
    jobs = [(s, r, n, T) for s in names for r in range(reps)]
    if procs > 1:
        with Pool(procs) as pool:
            res = pool.map(one_rep, jobs, chunksize=4)
    else:
        res = [one_rep(j) for j in jobs]
    by = {}
    for name, rows, neff in res:
        by.setdefault(name, []).append((rows, neff))
    return {"schema": "copybot.hypo_engine/1", "rule": "research/reviews/INBOX.md director order 47 P1",
            "alpha": ALPHA, "q_fdr": Q_FDR, "nw_lags": NW_LAGS, "n_assets": n, "days": T,
            "candidates": len(grid()), "families": {f: len(FAMILIES[f]["lookbacks"]) for f in FAMILIES},
            "scenarios": {s: summarise(s, by[s]) for s in names}}


def md(rep, digest):
    L = ["# Hypothesis engine P1 — synthetic falsification report", "",
         f"`research/tools/hypo_engine.py`; data `research/data/hypo_engine/report.json` (sha256 `{digest}`). "
         f"{rep['n_assets']} assets x {rep['days']} days, {rep['candidates']} candidates per world "
         f"({', '.join(f'{k} {v}' for k, v in rep['families'].items())}), alpha {rep['alpha']}, BH q {rep['q_fdr']}, "
         f"HAC lags {rep['nw_lags']}. Synthetic data only.", "",
         "| Scenario | Reps | Per-test type I (net) | FWER raw | FWER Holm [95 % CI] | FWER BH | FWER Bonf(N_eff) | "
         "FDP Holm | FDP BH | True found (Holm) | Leak caught | Cost-killed gross hits | Profit-PASS with net<=0 | "
         "N_eff |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def f(x):
        return "—" if x is None else f"{x:.3f}"
    for s, o in rep["scenarios"].items():
        ci = o["holm"]["fwer_ci95"]
        L.append(f"| {s} | {o['reps']} | {o['per_test_type1_net']['rate']:.3f} | {o['raw']['fwer']:.3f} | "
                 f"{o['holm']['fwer']:.3f} [{f(ci[0])}, {f(ci[1])}] | {o['bh']['fwer']:.3f} | "
                 f"{o['bonf_neff']['fwer']:.3f} | {f(o['holm']['fdp_pooled'])} | {f(o['bh']['fdp_pooled'])} | "
                 f"{o['holm']['worlds_with_a_true_selection'] if o['holm']['worlds_with_a_true_selection'] is not None else '—'} | "
                 f"{o['leak_caught']:.3f} | {o['gross_significant_killed_by_costs']} | "
                 f"{o['profit_pass_with_net_mean_le_0']} | {o['n_eff_mean']:.1f} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    rep = build(reps=a.reps, procs=a.procs)
    os.makedirs(a.out, exist_ok=True)
    body = json.dumps(rep, sort_keys=True, indent=1) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
        fh.write(body)
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(md(rep, digest))
    print(digest)
    print(md(rep, digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
