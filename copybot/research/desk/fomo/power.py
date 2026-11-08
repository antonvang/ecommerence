"""Order 56 P3/P4: power and feasibility of the fomo 30 s copy falsification (synthetic, no data).

Model of one copied trade under the video's rule (TP 10x, time stop, no stop-loss):
  with probability p the take-profit fills -> net return r_tp (after costs),
  otherwise the trade ends at the time stop / rug -> net return ~ Normal(L, sd_l) clipped to [-1, r_tp].
The verdict uses a 95 % interval for the mean net return per trade:
  FALSIFIED_UNDER_TESTED_CONDITIONS if upper <= 0, PRELIMINARY_POSITIVE if lower > 0 (plus robustness checks),
  otherwise INCONCLUSIVE; n < N_MIN -> INSUFFICIENT_DATA.
Analytic (normal) probabilities plus a seeded Monte Carlo with the same normal interval on each simulated sample.
Standard library only; deterministic.
"""
import json
import math
import random
import statistics

N_MIN = 30
Z = 1.959963984540054
R_TP = 8.5            # +850 % net when TP fills: 10x minus legacy fees (2 % per side) and network fee on 0.25 SOL
P_GRID = (0.01, 0.03, 0.05, 0.08, 0.12)
L_GRID = (-0.4, -0.6, -0.8)
SD_L = 0.4
N_GRID = (30, 70, 140, 300, 600)
SEED = 56
REPS = 2000


def moments(p, l_mean, sd_l=SD_L, r_tp=R_TP):
    mu = p * r_tp + (1 - p) * l_mean
    var = p * (r_tp - mu) ** 2 + (1 - p) * ((l_mean - mu) ** 2 + sd_l ** 2)
    return mu, math.sqrt(var)


def breakeven_p(l_mean, r_tp=R_TP):
    return -l_mean / (r_tp - l_mean)


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def analytic(p, l_mean, n):
    mu, sd = moments(p, l_mean)
    se = sd / math.sqrt(n)
    return {"falsified": _phi(-Z - mu / se), "positive": _phi(mu / se - Z)}


def simulate(p, l_mean, n, reps=REPS, seed=SEED):
    rng = random.Random(f"{seed}|{p}|{l_mean}|{n}")
    fals = pos = 0
    for _ in range(reps):
        xs = []
        for _ in range(n):
            if rng.random() < p:
                xs.append(R_TP)
            else:
                xs.append(min(R_TP, max(-1.0, rng.gauss(l_mean, SD_L))))
        m = statistics.fmean(xs)
        se = statistics.stdev(xs) / math.sqrt(n)
        if m + Z * se <= 0:
            fals += 1
        elif m - Z * se > 0:
            pos += 1
    return {"falsified": fals / reps, "positive": pos / reps}


def table():
    rows = []
    for l_mean in L_GRID:
        for p in P_GRID:
            mu, sd = moments(p, l_mean)
            for n in N_GRID:
                a = analytic(p, l_mean, n)
                s = simulate(p, l_mean, n)
                rows.append({"L": l_mean, "p": p, "mean": round(mu, 4), "sd": round(sd, 4), "n": n,
                             "p_falsified_normal": round(a["falsified"], 3), "p_falsified_mc": round(s["falsified"], 3),
                             "p_positive_normal": round(a["positive"], 3), "p_positive_mc": round(s["positive"], 3)})
    return rows


def main():
    out = {"r_tp": R_TP, "sd_l": SD_L, "seed": SEED, "reps": REPS,
           "breakeven_p": {str(l): round(breakeven_p(l), 4) for l in L_GRID}, "rows": table()}
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
