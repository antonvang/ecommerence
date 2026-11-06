"""Director order 45 P1: power of a forward test of a Donchian trend ensemble against equal-weight buy-and-hold.

No market data, no strategy code: every input is an explicit scenario assumption (listed in SCENARIO and GRID). The
estimands are the two the hypothesis could use (research/studies/ONLINE_EDGES_2026-11-05.md section 2):

  dSR   difference of annualised Sharpe ratios, trend minus buy-and-hold (Memmel 2003 variance of the Jobson-Korkie
        statistic, inflated by Lo 2002's autocorrelation factor and by excess kurtosis);
  alpha annualised intercept of trend returns on buy-and-hold returns (OLS t on the residual vol).

Correlated coins are not independent observations: the test runs on the two portfolio return series, one per day, and
the effective count of a pooled cross-section is reported as N / (1 + (N - 1) rho) for comparison only. A Monte Carlo
on synthetic bivariate fat-tailed AR(1) returns (fixed seed) checks the analytic size and power of the dSR test.

    python3 research/tools/donchian_power.py [--out DIR] [--reps N]

Writes <out>/donchian_power.json and .md and prints the sha256. Descriptive; decides nothing on its own.
"""
import argparse
import hashlib
import json
import math
import os
import random
from statistics import NormalDist

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(HERE, "research", "data", "donchian_power")
DAYS = 365                                   # crypto trades every day
POWER = 0.80
ALPHAS = (0.005, 0.05)                       # lab's alpha (amendment 21i) and a conventional one, both one-sided
SCENARIO = {                                 # base case (assumptions, not estimates from data)
    "years": 2.0,                            # the 24-month forward window in the hypothesis
    "sr_bh": 0.6,                            # annualised Sharpe of equal-weight top-20 buy-and-hold
    "rho": 0.6,                              # daily correlation trend vs buy-and-hold (long/flat follows the market)
    "vol_trend": 0.25,                       # vol target of the ensemble
    "ac1": 0.05,                             # first-order autocorrelation of daily returns (both series)
    "kurt": 8.0,                             # daily return kurtosis (normal = 3)
    "n_coins": 20, "rho_coins": 0.65,        # for the effective-count comparison only
}
EFFECTS_DSR = (0.3, 0.5, 1.0)                # annualised Sharpe gains to detect
EFFECTS_ALPHA = (0.05, 0.108, 0.18)          # 0.108 = Zarattini et al. 2025 reported alpha vs BTC; 0.18 their net CAGR
COSTS = {"turnover": (5, 15), "per_side": (0.001, 0.0025, 0.005)}   # one-way turnover x capital per year; cost/side
GRID = {"rho": (0.4, 0.6, 0.8), "years": (1, 2, 5, 10), "kurt": (3.0, 8.0, 15.0), "ac1": (0.0, 0.05, 0.15)}


def z(a):
    return NormalDist().inv_cdf(1 - a)


def lo_factor(ac1, q=DAYS):
    """Lo (2002): variance factor of an annualised Sharpe when daily returns follow AR(1) with coefficient ac1."""
    s = sum((1 - k / q) * ac1 ** k for k in range(1, q))
    return 1 + 2 * s


def var_dsr_daily(sr1, sr2, rho, t, kurt=3.0, ac1=0.0):
    """Variance of the daily Sharpe difference (Memmel 2003), times Lo's AR factor and a kurtosis term
    (Mertens 2002: (kurt - 3) / 4 * SR^2 per series, negligible for daily SR; kept for completeness)."""
    base = 2 * (1 - rho) + 0.5 * (sr1 ** 2 + sr2 ** 2 - 2 * sr1 * sr2 * rho ** 2)
    base += (kurt - 3) / 4 * (sr1 ** 2 + sr2 ** 2)
    return base * lo_factor(ac1) / t


def se_dsr_ann(sr_bh, d, rho, years, kurt=3.0, ac1=0.0):
    t = int(round(years * DAYS))
    s1, s2 = (sr_bh + d) / math.sqrt(DAYS), sr_bh / math.sqrt(DAYS)
    return math.sqrt(var_dsr_daily(s1, s2, rho, t, kurt, ac1) * DAYS)


def mde_dsr(sc, alpha, power=POWER):
    """Smallest annualised Sharpe gain detectable one-sided at alpha with the given power (fixed point in d)."""
    d = 1.0
    for _ in range(50):
        d = (z(alpha) + z(1 - power)) * se_dsr_ann(sc["sr_bh"], d, sc["rho"], sc["years"], sc["kurt"], sc["ac1"])
    return d


def years_for_dsr(sc, d, alpha, power=POWER):
    k = (z(alpha) + z(1 - power)) / d
    return k ** 2 * se_dsr_ann(sc["sr_bh"], d, sc["rho"], 1.0, sc["kurt"], sc["ac1"]) ** 2


def resid_vol(sc):
    return sc["vol_trend"] * math.sqrt(1 - sc["rho"] ** 2)


def mde_alpha(sc, alpha, power=POWER):
    return (z(alpha) + z(1 - power)) * resid_vol(sc) * math.sqrt(lo_factor(sc["ac1"])) / math.sqrt(sc["years"])


def years_for_alpha(sc, a, alpha, power=POWER):
    return ((z(alpha) + z(1 - power)) * resid_vol(sc) / a) ** 2 * lo_factor(sc["ac1"])


def n_eff(n, rho):
    return n / (1 + (n - 1) * rho)


def _t_unit(rng, kurt):
    """Unit-variance draw with the given kurtosis (Student t, df from kurt = 3 + 6 / (df - 4)); normal at 3."""
    if kurt <= 3.0:
        return rng.gauss(0, 1)
    df = 4 + 6 / (kurt - 3)
    x = rng.gauss(0, 1) / math.sqrt(rng.gammavariate(df / 2, 2 / df))
    return x * math.sqrt((df - 2) / df)


def simulate(sc, d, reps, alpha, seed=45):
    """Share of synthetic forward windows in which the analytic one-sided dSR test rejects at alpha."""
    rng = random.Random(seed)
    t = int(round(sc["years"] * DAYS))
    vb, vs = 0.70 / math.sqrt(DAYS), sc["vol_trend"] / math.sqrt(DAYS)
    mb, ms = sc["sr_bh"] / math.sqrt(DAYS) * vb, (sc["sr_bh"] + d) / math.sqrt(DAYS) * vs
    phi, r, crit, hits = sc["ac1"], sc["rho"], z(alpha), 0
    for _ in range(reps):
        e1 = e2 = 0.0
        b, s = [], []
        for _ in range(t):
            u1, u2 = _t_unit(rng, sc["kurt"]), _t_unit(rng, sc["kurt"])
            e1 = phi * e1 + math.sqrt(1 - phi ** 2) * u1
            e2 = phi * e2 + math.sqrt(1 - phi ** 2) * (r * u1 + math.sqrt(1 - r ** 2) * u2)
            b.append(mb + vb * e1)
            s.append(ms + vs * e2)
        mbh, msh = sum(b) / t, sum(s) / t
        sb = math.sqrt(sum((x - mbh) ** 2 for x in b) / (t - 1))
        ss = math.sqrt(sum((x - msh) ** 2 for x in s) / (t - 1))
        rh = sum((x - mbh) * (y - msh) for x, y in zip(b, s)) / ((t - 1) * sb * ss)
        sr1, sr2 = msh / ss, mbh / sb
        se = math.sqrt(var_dsr_daily(sr1, sr2, rh, t, sc["kurt"], sc["ac1"]))
        hits += (sr1 - sr2) / se > crit
    return hits / reps


def cost_drag():
    return [{"turnover": tv, "per_side": c, "drag": tv * c} for tv in COSTS["turnover"] for c in COSTS["per_side"]]


def build(reps):
    sc = dict(SCENARIO)
    out = {"rule": "director order 45 P1 (research/reviews/INBOX.md 2026-11-06)", "scenario": sc, "power": POWER,
           "lo_factor_base": lo_factor(sc["ac1"]),
           "n_eff_coins": n_eff(sc["n_coins"], sc["rho_coins"]),
           "base": {str(a): {"mde_dsr": mde_dsr(sc, a), "mde_alpha": mde_alpha(sc, a),
                             "years_dsr": {str(d): years_for_dsr(sc, d, a) for d in EFFECTS_DSR},
                             "years_alpha": {str(x): years_for_alpha(sc, x, a) for x in EFFECTS_ALPHA}}
                    for a in ALPHAS},
           "sensitivity": [], "cost_drag": cost_drag(), "monte_carlo": {}}
    for key, vals in GRID.items():
        for v in vals:
            s = dict(sc, **{key: v})
            out["sensitivity"].append({"vary": key, "value": v, "mde_dsr_0.005": mde_dsr(s, 0.005),
                                       "mde_dsr_0.05": mde_dsr(s, 0.05), "mde_alpha_0.005": mde_alpha(s, 0.005),
                                       "mde_alpha_0.05": mde_alpha(s, 0.05)})
    if reps:
        mc = {"reps": reps, "seed": 45, "size_0.05": simulate(sc, 0.0, reps, 0.05)}
        for d in EFFECTS_DSR:
            mc[f"power_0.05_dsr_{d}"] = simulate(sc, d, reps, 0.05)
        mc["analytic_power_0.05"] = {str(d): 1 - NormalDist().cdf(z(0.05) - d / se_dsr_ann(
            sc["sr_bh"], d, sc["rho"], sc["years"], sc["kurt"], sc["ac1"])) for d in EFFECTS_DSR}
        out["monte_carlo"] = mc
    b, c = out["base"]["0.05"], out["base"]["0.005"]
    out["verdict"] = ("INSUFFICIENT POWER" if min(c["mde_dsr"], b["mde_dsr"]) > max(EFFECTS_DSR)
                      or c["mde_alpha"] > max(EFFECTS_ALPHA) else "GO")
    return out


def md(rep):
    sc, b = rep["scenario"], rep["base"]
    L = ["# Donchian-ensemble: styrkeberegning (direktørordre 45 P1)", "",
         "Ingen markedsdata, ingen strategikode; alle input er antagelser (scenarie nedenfor). Ensidet test, styrke "
         f"{rep['power']:.0%}.", "",
         f"Basisscenarie: {sc['years']:g} år fremadrettet, købe-og-hold-Sharpe {sc['sr_bh']}, korrelation trend/købe-og-hold "
         f"{sc['rho']}, vol-target {sc['vol_trend']:.0%}, AR(1) {sc['ac1']}, kurtosis {sc['kurt']:g}. Los faktor "
         f"{rep['lo_factor_base']:.3f}. {sc['n_coins']} mønter med parvis korrelation {sc['rho_coins']} svarer til "
         f"{rep['n_eff_coins']:.2f} uafhængige.", "",
         "| α (ensidet) | MDE ΔSharpe (år) | MDE alfa p.a. | År for ΔSR 0,3 / 0,5 / 1,0 | År for alfa 5 % / 10,8 % / 18 % |",
         "|---|---|---|---|---|"]
    for a, r in b.items():
        yd = " / ".join(f"{v:.1f}" for v in r["years_dsr"].values())
        ya = " / ".join(f"{v:.1f}" for v in r["years_alpha"].values())
        L.append(f"| {a} | {r['mde_dsr']:.2f} | {r['mde_alpha']:.1%} | {yd} | {ya} |")
    L += ["", "## Følsomhed (én antagelse ad gangen)", "",
          "| Varieret | Værdi | MDE ΔSR α 0,005 | MDE ΔSR α 0,05 | MDE alfa α 0,005 | MDE alfa α 0,05 |", "|---|---|---|---|---|---|"]
    for s in rep["sensitivity"]:
        L.append(f"| {s['vary']} | {s['value']:g} | {s['mde_dsr_0.005']:.2f} | {s['mde_dsr_0.05']:.2f} | "
                 f"{s['mde_alpha_0.005']:.1%} | {s['mde_alpha_0.05']:.1%} |")
    L += ["", "## Omkostningstræk (trækkes fra den bruttoeffekt, der skal påvises)", "",
          "| Omsætning (x kapital/år, én vej) | Omk. pr. side | Træk p.a. |", "|---|---|---|"]
    for c in rep["cost_drag"]:
        L.append(f"| {c['turnover']} | {c['per_side']:.2%} | {c['drag']:.1%} |")
    mc = rep["monte_carlo"]
    if mc:
        L += ["", f"## Monte Carlo-kontrol ({mc['reps']} gentagelser, seed {mc['seed']}; syntetiske fedhalede AR(1)-afkast)", "",
              f"- Størrelse ved ΔSR 0 og α 0,05: {mc['size_0.05']:.3f}."]
        for d in EFFECTS_DSR:
            L.append(f"- Styrke ved ΔSR {d}: simuleret {mc[f'power_0.05_dsr_{d}']:.3f}, analytisk "
                     f"{mc['analytic_power_0.05'][str(d)]:.3f}.")
    L += ["", f"**Dom: {rep['verdict']}**", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--reps", type=int, default=400)
    a = ap.parse_args()
    rep = build(a.reps)
    os.makedirs(a.out, exist_ok=True)
    raw = json.dumps(rep, sort_keys=True, indent=1).encode()
    with open(os.path.join(a.out, "donchian_power.json"), "wb") as f:
        f.write(raw)
    with open(os.path.join(a.out, "donchian_power.md"), "w") as f:
        f.write(md(rep))
    print(f"donchian_power.json sha256 {hashlib.sha256(raw).hexdigest()} verdict {rep['verdict']}")


if __name__ == "__main__":
    main()
