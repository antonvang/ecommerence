"""Director order 76-B: analytic power/MDE for the five mechanism designs in FAPI_DESIGNS_76B.md.

Stdlib only. No market data, no network, no lab.db. Every sd, cluster count, cost and "plausible effect" below is an
ASSUMPTION written before any data exists; nothing is estimated from observations. MDEs use the amendment-32 formula
(order69_power.mde). The register-wide figure is a Bonferroni bar at N = 19,438 + K, which is a conservative MINIMUM and
not a final N: it is a diagnostic, not a calibrated limit, and N is never lowered to make a design pass.

Run: python3 research/desk/fapi76b/fapi_power_76b.py
"""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.desk.order69_power import ALPHA_F, POWER, Z, mde, mde_t, sim_power  # noqa: E402

REGISTER_N = 19438                 # SNAPSHOT_v1 counts.variants; a conservative minimum, never a final N
REGISTER_ALPHA = 0.05              # one-sided Bonferroni convention used in LITERATURE_REVIEW_ORDER69 (table of N)

# ---- ASSUMPTIONS (not data). unit = what sd, effect and cost are in. n = planned independent clusters in the forward
# window; n_power = the n used for the standard error when it differs (two-group contrast of subsets). ----
ENDPOINTS = {
    "CB1_VOL": {"design": "CB1", "unit": "log", "sd": 0.25, "n": 180, "plausible_net": 0.08, "cost_rt_bps": 0.0,
                "floor_bps": None, "note": "ln RV(3 d) mod HAR, minus matched kontrol; all perps, about 180 hændelsesdøgn pr. 12 mdr."},
    "CB1_DIR": {"design": "CB1", "unit": "frac", "sd": 0.040, "n": 180, "plausible_net": 0.0014, "cost_rt_bps": 31.0,
                "floor_bps": 46.0, "note": "3 d-afkast med udbruddet, netto; 31 bp realistisk (2x5 + bog + funding)"},
    "PR1": {"design": "PR1", "unit": "frac", "sd": 0.25, "n": 170, "plausible_net": 0.10, "cost_rt_bps": 0.0,
            "floor_bps": None, "note": "D (likvid) minus D (tynd), andel af premium væk efter 8 t, døgnklynger, 6 mdr."},
    "LD1": {"design": "LD1", "unit": "bp", "sd": 10.0, "n": 60, "n_power": 14.4, "plausible_net": 3.0, "cost_rt_bps": 0.0,
            "floor_bps": None, "note": "kursledt mod likviditetsledt besparelse; 24 og 36 klynger giver n_eff 14,4 (LQ1's 60 klynger)"},
    "FL1": {"design": "FL1", "unit": "frac", "sd": 0.050, "n": 45, "plausible_net": 0.002, "cost_rt_bps": 40.0,
            "floor_bps": 46.0, "note": "train3 og validation3, 24 t-afkast efter tvunget salg; bruttoskøn ca. 0,6 %"},
    "TS1": {"design": "TS1", "unit": "frac", "sd": 0.0136, "n": 125, "plausible_net": -0.0007, "cost_rt_bps": 11.0,
            "floor_bps": 46.0, "note": "US-session i BTC i højvol-regime; bruttoskøn 4 bp"},
}


def bonferroni_z(n, alpha=REGISTER_ALPHA):
    """One-sided critical z for family size n (Bonferroni). Diagnostic: not a calibrated bar."""
    return Z.inv_cdf(1 - alpha / n)


def mde_register(sd, n, own_variants=1, alpha=REGISTER_ALPHA, power=POWER):
    """MDE at the register-wide Bonferroni bar with N = REGISTER_N + own_variants, a floor for N and never lowered."""
    if sd <= 0 or n < 2:
        raise ValueError("sd > 0 and n >= 2 required")
    z = bonferroni_z(REGISTER_N + own_variants, alpha)
    return (z + Z.inv_cdf(power)) * sd / math.sqrt(n)


def analytic_power(effect, sd, n, alpha=ALPHA_F):
    """Normal-approximation power of the one-sided test at a true effect."""
    return Z.cdf(effect * math.sqrt(n) / sd - Z.inv_cdf(1 - alpha))


def endpoint_row(name):
    """Headline numbers for one endpoint; every input is an assumption from ENDPOINTS."""
    e = ENDPOINTS[name]
    n_power = e.get("n_power", e["n"])
    k = sum(1 for v in ENDPOINTS.values() if v["design"] == e["design"])
    m = mde(e["sd"], n_power)
    return {"name": name, "unit": e["unit"], "sd": e["sd"], "n": e["n"], "n_power": n_power,
            "mde_alpha_f": m, "mde_t": mde_t(e["sd"], n_power) if n_power >= 12 else None,
            "mde_register": mde_register(e["sd"], n_power, k), "power_at_plausible": analytic_power(e["plausible_net"], e["sd"], n_power),
            "plausible_net": e["plausible_net"], "reachable": e["plausible_net"] >= m,
            "gross_needed_realistic_bps": None if e["unit"] != "frac" or e["cost_rt_bps"] == 0 else
            1e4 * m + e["cost_rt_bps"], "cost_rt_bps": e["cost_rt_bps"], "floor_bps": e["floor_bps"]}


def table():
    return {k: endpoint_row(k) for k in ENDPOINTS}


# Sensitivity of the two surviving endpoints: MDE (alpha_F) over assumed sd and clusters.
SENSITIVITY = {"CB1_VOL": {"sd": (0.20, 0.25, 0.35), "n": (60, 120, 180)}, "PR1": {"sd": (0.15, 0.25, 0.35), "n": (85, 170, 340)}}


def sensitivity(name):
    grid = SENSITIVITY[name]
    return {(s, n): mde(s, n) for s in grid["sd"] for n in grid["n"]}


def _main():
    for k, r in table().items():
        print(k, {a: (round(b, 5) if isinstance(b, float) else b) for a, b in r.items() if a != "name"})
    for k in SENSITIVITY:
        print(k, {a: round(b, 4) for a, b in sensitivity(k).items()})
    e = ENDPOINTS["CB1_DIR"]
    print("sim power CB1_DIR at MDE (normal):", sim_power(mde(e["sd"], e["n"]), e["sd"], e["n"]))
    print("sim power CB1_DIR at MDE (t3):", sim_power(mde(e["sd"], e["n"]), e["sd"], e["n"], tails="t3"))
    print("sim size CB1_DIR at 0 (normal):", sim_power(0.0, e["sd"], e["n"]))


if __name__ == "__main__":
    _main()
