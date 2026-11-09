"""LQ1-styrke (UDKAST, IKKE LAAST): hvor lang tid tager testen, og hvad kan den finde? Kun syntetisk.

Genbruger ordre 69's formel (order69_power.mde). Spredning og haendelsesrate er ANTAGELSER fra ORIGINAL_DESIGNS_ORDER69
afsnit 2.7 og er ikke estimeret fra data. `pipeline_mc` koerer hele evaluatoren paa opdigtede verdener.

Kor: python3 research/desk/lq1/lq1_power.py [antal gentagelser]
"""
from __future__ import annotations

import collections
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))))

from research.desk import order69_power as p                  # noqa: E402
from research.desk.lq1 import lq1_evaluator as ev             # noqa: E402
from research.desk.lq1 import make_fixtures as mf             # noqa: E402

THRESHOLD = ev.THRESHOLD_BP
WINDOW_DAYS = ev.END_D - ev.START_D
SDS = (5.0, 10.0, 30.0)
TRUE_SAVINGS = (6.0, 7.0, 8.0, 9.0, 12.0)
EVENT_DAY_SHARES = (0.25, 0.33, 0.50, 2 / 3)        # andel af kalenderdoegn med mindst en haendelse (ANTAGELSE)


def required_clusters(true_s, sd, power=p.POWER):
    """Klyngedoegn der kraeves for `power` ved en sand besparelse true_s > taerskel."""
    if true_s <= THRESHOLD or sd <= 0:
        raise ValueError("true_s > taerskel og sd > 0 kraeves")
    z = p.z_crit(p.ALPHA_F) + p.Z.inv_cdf(power)
    return math.ceil((z * sd / (true_s - THRESHOLD)) ** 2)


def analytic_power(true_s, sd, n):
    return p.Z.cdf((true_s - THRESHOLD) * math.sqrt(n) / sd - p.z_crit(p.ALPHA_F))


def calendar_days(n, share):
    return math.ceil(n / share)


def tables():
    t = {"mde_bp_above_threshold": {f"sd={s:g}": {f"n={n}": round(p.mde(s, n), 2) for n in (30, 60, 91, 120)}
                                    for s in SDS},
         "mde_t_sd10_n60": round(p.mde_t(10.0, 60), 2),
         "required_clusters": {f"sd={s:g}": {f"S={x:g}": required_clusters(x, s) for x in TRUE_SAVINGS} for s in SDS}}
    t["window"] = {f"event_day_share={q:.2f}": {
        "clusters_in_91_days": int(q * WINDOW_DAYS),
        "testable": int(q * WINDOW_DAYS) >= ev.MIN_CLUSTER_DAYS,
        "power_sd10_true_S": {f"S={x:g}": round(analytic_power(x, 10.0, int(q * WINDOW_DAYS)), 3)
                              for x in TRUE_SAVINGS}} for q in EVENT_DAY_SHARES}
    t["days_needed_sd10"] = {f"S={x:g}": {f"share={q:.2f}": calendar_days(required_clusters(x, 10.0), q)
                                          for q in EVENT_DAY_SHARES} for x in TRUE_SAVINGS}
    return t


# Opdigtede verdener til hele kaeden. HET har forskellige bogniveauer, saa besparelsen sidder i de tynde markeder.
WORLDS = {
    "ved_taerskel_ens_boeger": {"bases": mf.EQUAL_BASES, "rho": mf.RHO_AT_THRESHOLD},
    "S9_ens_boeger": {"bases": mf.EQUAL_BASES, "rho": 1.0 - 9.0 / (0.5 * 3.15 * 8.0)},
    "S9_blandede_boeger": {"bases": (2.0, 4.0, 12.0, 30.0), "rho": 1.0 - 9.0 / (0.5 * 3.15 * 12.0)},
    "ingen_tilbagevenden": {"bases": mf.MIXED_BASES, "rho": 1.0},
}


def pipeline_mc(reps=200, seed0=90000):
    """Domfordeling gennem hele evaluatoren. `test_only_pass` er andelen med p <= alfa uden robusthedsporten."""
    out = {}
    for name, kw in WORLDS.items():
        verdicts, sds, ns, test_only = collections.Counter(), [], [], 0
        for r in range(reps):
            res = ev.evaluate_world(ev.decode_fixture(mf.world(name, seed0 + r, **kw)))
            verdicts[res["verdict"]] += 1
            t = res.get("test")
            if t:
                sds.append(t["sd"])
                ns.append(t["n"])
                test_only += t["p"] <= ev.ALPHA_F and t["mean"] > ev.THRESHOLD_BP
        out[name] = {"reps": reps, "verdicts": dict(sorted(verdicts.items())), "pass_share": verdicts[ev.PASS] / reps,
                     "test_only_pass": round(test_only / reps, 4),
                     "mean_cluster_sd_bp": round(math.fsum(sds) / len(sds), 2) if sds else None,
                     "mean_clusters": round(math.fsum(ns) / len(ns), 1) if ns else None}
    return out


def main(argv):
    reps = int(argv[1]) if len(argv) > 1 else 200
    print(json.dumps({"tables": tables(), "pipeline_mc": pipeline_mc(reps), "alpha_F": p.ALPHA_F}, indent=1,
                     sort_keys=True))


if __name__ == "__main__":
    main(sys.argv)
