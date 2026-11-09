"""Director order 69 P3: analytic power/MDE for the three original designs (ORIGINAL_DESIGNS_ORDER69.md).

Stdlib only. No market data, no network, no lab.db. Every sd, event rate and cost below is an ASSUMPTION written in
the design note before any data exists; nothing here is estimated from observations.

Contents:
- mde(): (z_{1-a} + z_{power}) * sd / sqrt(n) (PROTOCOL_V3 amendment 32 point 1), one- or two-sided;
- mde_t(): the same with a Student-t critical value (Cornish-Fisher expansion, df = n - 1);
- sim_power(): Monte Carlo power of the one-sided cluster t-test at a given true mean (synthetic normal or t(3) data);
- kappa1()/null_event_rate(): the Sanso-Arago-Carrion (2004) kappa_1 ICSS statistic used by design VB1, and its
  false-event rate per coin-week on synthetic i.i.d. fat-tailed returns (no break) with the design's online rule;
- table(): the headline numbers quoted in the note.
Run: python3 research/desk/order69_power.py
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist

Z = NormalDist()
POWER = 0.80
ALPHA_F = 0.0125            # PROTOCOL_V3 amendment 8: alpha per family (one-sided), if W0 alpha is ever granted
ALPHA_DESC = 0.05           # descriptive label when alpha = 0

# ---- design assumptions (ASSUMPTION; fixed in the note before data) ----
DESIGNS = {
    # VB1: net overlay benefit B per UTC-day cluster, fraction of capital; test B > 0
    "VB1": {"sd": 0.0045, "n": 78, "sens_sd": (0.0025, 0.0045, 0.0100), "sens_n": (40, 78, 120),
            "hurdle": 0.0037},
    # LQ1: per-side saving S in bp per UTC-day cluster; test S > 5 bp (threshold, not 0)
    "LQ1": {"sd": 10.0, "n": 60, "sens_sd": (5.0, 10.0, 30.0), "sens_n": (30, 60, 120), "threshold": 5.0},
    # EX1: net reversal y per expiry Friday, fraction; test y > 0
    "EX1": {"sd": 0.0035, "n": 52, "sens_sd": (0.0025, 0.0035, 0.0050), "sens_n": (26, 52),
            "cost_real": 0.0011, "cost_lane": 0.0024, "floor_21i": 0.0046, "controls_per_week": 4},
}


def z_crit(alpha, one_sided=True):
    return Z.inv_cdf(1 - alpha if one_sided else 1 - alpha / 2)


def mde(sd, n, alpha=ALPHA_F, one_sided=True, power=POWER):
    """Amendment 32 point 1: MDE = (z_{1-alpha} + z_power) * sd / sqrt(n)."""
    if sd <= 0 or n < 2:
        raise ValueError("sd > 0 and n >= 2 required")
    return (z_crit(alpha, one_sided) + Z.inv_cdf(power)) * sd / math.sqrt(n)


def t_quantile(p, df):
    """Student-t quantile by the Cornish-Fisher expansion around the normal (good to ~1e-3 for df >= 10)."""
    z = Z.inv_cdf(p)
    g1 = (z ** 3 + z) / 4
    g2 = (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96
    g3 = (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384
    return z + g1 / df + g2 / df ** 2 + g3 / df ** 3


def mde_t(sd, n, alpha=ALPHA_F, power=POWER):
    """One-sided MDE with t(n-1) quantiles (slightly larger than mde() for small n)."""
    df = n - 1
    return (t_quantile(1 - alpha, df) + t_quantile(power, df)) * sd / math.sqrt(n)


def _t_stat(xs, mu0):
    n = len(xs)
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1)
    return (m - mu0) / math.sqrt(v / n) if v > 0 else 0.0


def sim_power(true_mean, sd, n, alpha=ALPHA_F, mu0=0.0, reps=2000, seed=7, tails="normal"):
    """Share of synthetic samples (n clusters) where the one-sided t-test rejects H0: mean <= mu0."""
    rng = random.Random(seed)
    crit = t_quantile(1 - alpha, n - 1)
    scale = sd / math.sqrt(3.0) if tails == "t3" else sd          # t(3) has variance 3
    hits = 0
    for _ in range(reps):
        if tails == "t3":
            xs = []
            for _ in range(n):
                chi = sum(rng.gauss(0, 1) ** 2 for _ in range(3))
                xs.append(true_mean + scale * rng.gauss(0, 1) / math.sqrt(chi / 3))
        else:
            xs = [rng.gauss(true_mean, scale) for _ in range(n)]
        hits += _t_stat(xs, mu0) > crit
    return hits / reps


# ---- VB1 break detector (Sanso, Arago & Carrion 2004, kappa_1; Inclan & Tiao 1994 critical value) ----
KAPPA_CRIT, WINDOW_H, RECENT_H, DEDUP_H = 1.358, 168, 24, 168


def kappa1(a):
    """(statistic, break index k*) for returns a (assumed mean zero): sup_k |C_k - (k/T) C_T| / sqrt(T * omega4)."""
    T = len(a)
    sq = [x * x for x in a]
    CT = sum(sq)
    s2 = CT / T
    omega4 = sum((x - s2) ** 2 for x in sq) / T
    if omega4 <= 1e-12 * s2 * s2:                      # constant |r|: no variance change is possible
        return 0.0, 0
    best, kstar, c = 0.0, 0, 0.0
    for k in range(1, T + 1):
        c += sq[k - 1]
        b = abs(c - k / T * CT)
        if b > best:
            best, kstar = b, k
    return best / math.sqrt(T * omega4), kstar


def upward_break(a):
    """The design's online rule on the last WINDOW_H returns: kappa1 > 1.358, k* within the last RECENT_H hours and
    the variance after k* larger than before."""
    stat, k = kappa1(a)
    if stat <= KAPPA_CRIT or k < len(a) - RECENT_H or k >= len(a):
        return False
    pre, post = a[:k], a[k:]
    return sum(x * x for x in post) / len(post) > sum(x * x for x in pre) / len(pre)


def null_event_rate(weeks=60, seed=7, df=4, sigma=0.01, step=1):
    """Events per coin-week under NO break (i.i.d. t(df) returns), hourly evaluation and 7-day dedup."""
    rng = random.Random(seed)

    def draw():
        chi = sum(rng.gauss(0, 1) ** 2 for _ in range(df))
        return sigma * rng.gauss(0, 1) / math.sqrt(chi / df)

    hours = WINDOW_H + weeks * 168
    r = [draw() for _ in range(hours)]
    events, last = 0, -10 ** 9
    for t in range(WINDOW_H, hours, step):
        if t - last < DEDUP_H:
            continue
        if upward_break(r[t - WINDOW_H:t]):
            events, last = events + 1, t
    return events / weeks


def detects_doubling(seed=11, reps=40, sigma=0.01, factor=2.0, after=12):
    """Share of synthetic windows with a variance jump of `factor` (sd) `after` hours before the end that fire."""
    rng = random.Random(seed)
    hits = 0
    for _ in range(reps):
        a = [rng.gauss(0, sigma) for _ in range(WINDOW_H - after)] + [rng.gauss(0, sigma * factor)
                                                                     for _ in range(after)]
        hits += upward_break(a)
    return hits / reps


def detects_episode(seed=13, reps=100, sigma=0.01, factor=2.0):
    """Online, as the rule runs: a permanent sd jump of `factor` at hour B; the rule is evaluated every hour from B+1
    to B+24 on the last WINDOW_H returns. Share of episodes that fire at least once (and the median delay in hours)."""
    rng = random.Random(seed)
    hits, delays = 0, []
    for _ in range(reps):
        r = [rng.gauss(0, sigma) for _ in range(WINDOW_H)] + [rng.gauss(0, sigma * factor) for _ in range(RECENT_H)]
        for h in range(1, RECENT_H + 1):
            end = WINDOW_H + h
            if upward_break(r[end - WINDOW_H:end]):
                hits, _ = hits + 1, delays.append(h)
                break
    delays.sort()
    return hits / reps, (delays[len(delays) // 2] if delays else None)


def table():
    out = {}
    d = DESIGNS["VB1"]
    out["VB1"] = {"mde": mde(d["sd"], d["n"]), "mde_t": mde_t(d["sd"], d["n"]),
                  "gross_loss_needed": d["hurdle"] + mde(d["sd"], d["n"]),
                  "sens": {(s, n): mde(s, n) for s in d["sens_sd"] for n in d["sens_n"]}}
    d = DESIGNS["LQ1"]
    out["LQ1"] = {"mde_above_threshold": mde(d["sd"], d["n"]), "mde_t": mde_t(d["sd"], d["n"]),
                  "true_saving_needed": d["threshold"] + mde(d["sd"], d["n"]),
                  "sens": {(s, n): mde(s, n) for s in d["sens_sd"] for n in d["sens_n"]}}
    d = DESIGNS["EX1"]
    did_sd = d["sd"] * math.sqrt(1 + 1 / d["controls_per_week"])
    out["EX1"] = {"mde": mde(d["sd"], d["n"]), "mde_t": mde_t(d["sd"], d["n"]),
                  "mde_desc": mde(d["sd"], d["n"], alpha=ALPHA_DESC),
                  "gross_needed_real": d["cost_real"] + mde(d["sd"], d["n"]),
                  "gross_needed_lane": d["cost_lane"] + mde(d["sd"], d["n"]),
                  "ratio_vs_21i_floor": mde(d["sd"], d["n"]) / d["floor_21i"],
                  "mde_did_desc": mde(did_sd, d["n"], alpha=ALPHA_DESC),
                  "sens": {(s, n): mde(s, n) for s in d["sens_sd"] for n in d["sens_n"]}}
    return out


def _main():
    t = table()
    for k, v in t.items():
        print(k)
        for kk, vv in v.items():
            if kk == "sens":
                for (s, n), m in vv.items():
                    print(f"   sens sd={s:g} n={n}: MDE={m:.5g}")
            else:
                print(f"   {kk}: {vv:.5g}")
    print("sim power VB1 at MDE (normal):", sim_power(t["VB1"]["mde"], 0.0045, 78))
    print("sim power VB1 at MDE (t3):", sim_power(t["VB1"]["mde"], 0.0045, 78, tails="t3"))
    print("sim power LQ1 at 5+MDE (normal):", sim_power(5 + t["LQ1"]["mde_above_threshold"], 10.0, 60, mu0=5.0))
    print("sim power LQ1 at 5+MDE (t3):", sim_power(5 + t["LQ1"]["mde_above_threshold"], 10.0, 60, mu0=5.0,
                                                     tails="t3"))
    print("sim power EX1 at MDE (normal):", sim_power(t["EX1"]["mde"], 0.0035, 52))
    print("sim power EX1 at MDE (t3):", sim_power(t["EX1"]["mde"], 0.0035, 52, tails="t3"))
    print("sim size EX1 at 0 (normal):", sim_power(0.0, 0.0035, 52))
    print("VB1 null events per coin-week, t(4):", null_event_rate())
    print("VB1 detects sd doubling 12 h before end (one window):", detects_doubling())
    for f in (1.5, 2.0, 3.0):
        print(f"VB1 online episode, sd x{f}: (share fired, median delay h) =", detects_episode(factor=f))


if __name__ == "__main__":
    _main()
