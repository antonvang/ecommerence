"""Director order 47 P2: power before activation for the protocol drafts F1-F3 (no market data; formulas and stated
scenarios only). Every number here is a scenario, not an estimate from data.

- Sharpe test (F1, F3): one-sided H0 SR <= 0 on daily (F1) or per-period (F3) net returns. Var(SR_hat) per Lo (2002)
  and Mertens (2002): (1 + SR^2/2 + (kurt - 3)/4 SR^2) * Lo AR(1) factor / n.
- Diebold-Mariano (F2): one-sided H0 E[d] <= 0 for the loss differential d = loss(benchmark) - loss(candidate),
  standardised effect e = E[d] / sd(d) per coin-day; pooled over N coins with cross-coin correlation rho_c, effective
  n = N T / (1 + (N - 1) rho_c), times an HAC factor for autocorrelation in d.
- Holm across K pre-registered primary variants: the first rejection needs p <= alpha / K, so power is computed at
  alpha / K (the worst case for the best variant).
- Amendment 8 point 14 requirement for forward families: power >= 0.5 at true SR 3.0, alpha_F / 3, window length.

    python3 research/tools/p2_power.py        # -> research/data/p2_power/
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from statistics import NormalDist

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(HERE, "research", "data", "p2_power")
N = NormalDist()
DAYS = 365
ALPHA_FAMILY = 0.05          # Holm, family-wise (historical phase, amendment 2 per-window budget)
ALPHA_F = 0.0125             # amendment 8 forward family
A8_SR, A8_POWER = 3.0, 0.5


def zq(p):
    return N.inv_cdf(1 - p)


def lo_factor(ac1, q=30):
    return 1 + 2 * sum((1 - k / q) * ac1 ** k for k in range(1, q))


def sr_power(sr_ann, n, per_year, alpha, ac1=0.0, kurt=3.0):
    """Power of a one-sided test of SR > 0 with n observations at `per_year` observations per year."""
    if n <= 1:
        return 0.0
    s = sr_ann / math.sqrt(per_year)
    se = math.sqrt((1 + 0.5 * s * s + (kurt - 3) / 4 * s * s) * lo_factor(ac1) / n)
    return 1 - N.cdf(zq(alpha) - s / se)


def sr_needed(n, per_year, alpha, power=0.8, ac1=0.0, kurt=3.0):
    """Smallest annual SR detectable with the given power (bisection)."""
    lo, hi = 0.0, 50.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if sr_power(mid, n, per_year, alpha, ac1, kurt) < power:
            lo = mid
        else:
            hi = mid
    return hi


def dm_power(effect, n_coins, days, rho_c, alpha, hac=1.5):
    n_eff = n_coins * days / (1 + (n_coins - 1) * rho_c) / hac
    return 1 - N.cdf(zq(alpha) - effect * math.sqrt(n_eff)), n_eff


def n_eff_overlap(n_units, periods, rho):
    return n_units * periods / (1 + (n_units - 1) * rho)


# ---------------------------------------------------------------- the three families

F1 = {"name": "F1 cross-sectional relative value (pre-defined crypto pairs, beta-neutral spread)",
      "windows": {"train3": 546, "validation3": 184, "train3+validation3": 730}, "K": [1, 3], "sr": [0.5, 1.0, 1.5, 2.0, 3.0],
      "ac1": 0.1, "kurt": 8.0}
F2 = {"name": "F2 volatility forecast (HAR-RV vs EWMA 0.94, QLIKE)",
      "windows": {"train3": 546, "validation3": 184, "train3+validation3": 730}, "K": [1, 3], "effects": [0.01, 0.02, 0.05, 0.10],
      "coins": [10, 20], "rho_c": [0.5, 0.8], "hac": 1.5}
F3 = {"name": "F3 dated futures basis persistence (COIN-M quarterly, held to expiry; data from 2026-11-28)",
      "expiries": {"train3": 6, "validation3": 2, "train3+validation3": 8}, "coins": [6, 12], "rho": [0.6, 0.8],
      "entries_per_expiry": 1, "sr_per_entry": [0.25, 0.5, 1.0, 2.0], "K": [1, 3]}


def f1_rows():
    rows = []
    for win, n in F1["windows"].items():
        for K in F1["K"]:
            for sr in F1["sr"]:
                rows.append({"window": win, "days": n, "K": K, "sr_true": sr,
                             "power": round(sr_power(sr, n, DAYS, ALPHA_FAMILY / K, F1["ac1"], F1["kurt"]), 4)})
            rows.append({"window": win, "days": n, "K": K, "sr_true": "MDE@0.8",
                         "power": round(sr_needed(n, DAYS, ALPHA_FAMILY / K, 0.8, F1["ac1"], F1["kurt"]), 3)})
    return rows


def f2_rows():
    rows = []
    for win, n in F2["windows"].items():
        for K in F2["K"]:
            for e in F2["effects"]:
                for c in F2["coins"]:
                    for rc in F2["rho_c"]:
                        p, ne = dm_power(e, c, n, rc, ALPHA_FAMILY / K, F2["hac"])
                        rows.append({"window": win, "days": n, "K": K, "effect": e, "coins": c, "rho_c": rc,
                                     "n_eff": round(ne, 1), "power": round(p, 4)})
    return rows


def f3_rows():
    """Per-entry Sharpe = mean net basis captured / its cross-entry sd (a scenario); entries held to expiry do not
    overlap within a coin; coins are correlated (rho)."""
    rows = []
    for win, ex in F3["expiries"].items():
        for c in F3["coins"]:
            for rho in F3["rho"]:
                ne = n_eff_overlap(c, ex * F3["entries_per_expiry"], rho)
                for K in F3["K"]:
                    for s in F3["sr_per_entry"]:
                        z = s * math.sqrt(ne)
                        rows.append({"window": win, "expiries": ex, "coins": c, "rho": rho, "K": K,
                                     "sr_per_entry": s, "n_eff": round(ne, 2),
                                     "power": round(1 - N.cdf(zq(ALPHA_FAMILY / K) - z), 4)})
    return rows


def a8_check():
    """Amendment 8 point 14 for a forward test: power at SR 3.0, alpha_F / 3, for 6 and 12 months of daily data."""
    return {f"{m}m": round(sr_power(A8_SR, int(m * 30.4), DAYS, ALPHA_F / 3), 3) for m in (6, 12)}


def build():
    return {"schema": "copybot.p2_power/1", "rule": "director order 47 P2 (INBOX 2026-11-06)",
            "alpha_family": ALPHA_FAMILY, "alpha_F": ALPHA_F, "F1": {**F1, "rows": f1_rows()},
            "F2": {**F2, "rows": f2_rows()}, "F3": {**F3, "rows": f3_rows()}, "a8_forward_check": a8_check(),
            "note": "scenarios only; no market data read"}


def main():
    rep = build()
    os.makedirs(OUT, exist_ok=True)
    body = json.dumps(rep, sort_keys=True, indent=1) + "\n"
    with open(os.path.join(OUT, "p2_power.json"), "w", encoding="utf-8") as f:
        f.write(body)
    print(hashlib.sha256(body.encode()).hexdigest())
    print("A8", rep["a8_forward_check"])
    for fam in ("F1", "F2", "F3"):
        print(fam)
        for r in rep[fam]["rows"]:
            print(" ", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
