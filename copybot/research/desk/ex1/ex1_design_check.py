"""EX1 designkontrol (direktoerordre 70 P2): beslutningsregler og styrke i ren syntetik. UDKAST, IKKE LAAST.

Direktoeren har afvist adgang til K3-data. Denne fil laeser ingen filer og ingen database: alle tal skabes her af
`random.Random` med fast seed. EX1 er en beskrivende hypotese med lav forhaandssandsynlighed, ikke en handelsfordel.

Modellerer ORIGINAL_DESIGNS_ORDER69 afsnit 3.1, 3.5 og 3.7: r_pre, r_post, y_net, DiD-porten, placeboen, futilitet ved
26 fredage, dom ved 52 fredage. Kor: python3 research/desk/ex1/ex1_design_check.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))))

from research.desk.lq1.lq1_evaluator import one_sided_test          # noqa: E402

ALPHA_NET, ALPHA_DID, ALPHA_PLACEBO = 0.0125, 0.05, 0.05
TAKER = 0.0005                  # pr. side
FUTILITY_N, FINAL_N, MIN_VALID = 26, 52, 40
BOOK_MAX_AGE_H = 24
PASS, PASS_NOT_EXPIRY, FALSIFIED, INCONCLUSIVE = "PASS", "PASS_NOT_EXPIRY", "FALSIFIED", "INCONCLUSIVE"
UNTESTABLE, INVALID, STOPPED_FUTILE, CONTINUE = "UNTESTABLE", "INVALID", "STOPPED_FUTILE", "CONTINUE"
DEADLINE = dt.date(2027, 12, 31)
LOCK_ASSUMED = dt.date(2026, 11, 16)        # ANTAGELSE fra designnotatet; intet er laast


def returns_from_marks(marks):
    """r_pre = ln(m(-1)/m(-31)), r_post = ln(m(+31)/m(+1)). Manglende minut giver None for det afkast."""
    def ratio(a, b):
        if marks.get(a) is None or marks.get(b) is None or marks[a] <= 0 or marks[b] <= 0:
            return None
        return math.log(marks[a] / marks[b])
    return ratio(-1, -31), ratio(31, 1)


def y_gross(r_pre, r_post):
    """y = -s * r_post med s = fortegnet af r_pre. r_pre = 0 og manglende afkast udelukkes (None)."""
    if r_pre is None or r_post is None or r_pre == 0:
        return None
    return -math.copysign(1.0, r_pre) * r_post


def cost(book_rt, age_h):
    """c_t = 2 x 0,05 % + bog; maalingen maa hoejst vaere 24 t gammel, ellers udelukkes fredagen."""
    if book_rt is None or age_h is None or age_h > BOOK_MAX_AGE_H or age_h < 0 or book_rt < 0:
        return None
    return 2 * TAKER + book_rt


def week_row(week):
    """(y_gross, y_net, delta, placebo_gross) for en uge, eller None hvis fredagen er ugyldig. delta = fredag minus
    middel af man-tor kl. 08:00 (naar der findes mindst en gyldig kontroldag; ellers None)."""
    fri = week["fri"]
    g = y_gross(fri.get("r_pre"), fri.get("r_post"))
    c = cost(fri.get("book_rt"), fri.get("book_age_h"))
    if g is None or c is None:
        return None
    ctrl = [v for v in (y_gross(x.get("r_pre"), x.get("r_post")) for x in week.get("controls", [])) if v is not None]
    delta = g - math.fsum(ctrl) / len(ctrl) if ctrl else None
    pl = week.get("placebo") or {}
    return g, g - c, delta, y_gross(pl.get("r_pre"), pl.get("r_post"))


def final_decision(net, gross, deltas, placebo):
    """Dom ved 52 fredage (afsnit 3.5). Placebo fejlet men net+DiD bestaaet staar ikke i notatet: se EX1_DESIGN_CHECK."""
    mean_net = math.fsum(net) / len(net)
    if mean_net <= 0:
        return FALSIFIED, "NET_MEAN_NOT_POSITIVE"
    net_ok = one_sided_test(net, mu0=0.0)["p"] <= ALPHA_NET
    if not net_ok:
        return INCONCLUSIVE, "NET_NOT_SIGNIFICANT"
    did_ok = len(deltas) >= 2 and one_sided_test(deltas, mu0=0.0)["p"] <= ALPHA_DID
    if not did_ok:
        return PASS_NOT_EXPIRY, "DID_GATE_FAILED"
    if len(placebo) < 2:
        return INCONCLUSIVE, "PLACEBO_UNAVAILABLE"
    p1 = one_sided_test(placebo, mu0=0.0)["p"]
    if 2.0 * min(p1, 1.0 - p1) <= ALPHA_PLACEBO:
        return INCONCLUSIVE, "PLACEBO_FAILED"
    return PASS, "NET_AND_DID_AND_PLACEBO"


def evaluate(weeks, deadline_reached=False, source_ended=False):
    """Hele domstraeet paa syntetiske uger. Foer 52 gyldige fredage er svaret CONTINUE eller en stop-dom."""
    rows = [r for r in (week_row(w) for w in weeks) if r is not None]
    if source_ended:
        return {"verdict": INVALID, "reason": "DATA_SOURCE_ENDED", "valid_fridays": len(rows)}
    if deadline_reached and len(rows) < MIN_VALID:
        return {"verdict": UNTESTABLE, "reason": "FEWER_THAN_40_VALID", "valid_fridays": len(rows)}
    if len(rows) >= FUTILITY_N:
        gross26 = [r[0] for r in rows[:FUTILITY_N]]
        if math.fsum(gross26) / FUTILITY_N <= 0:
            return {"verdict": STOPPED_FUTILE, "reason": "GROSS_MEAN_NOT_POSITIVE_AT_26", "valid_fridays": len(rows)}
    if len(rows) < FINAL_N:
        return {"verdict": CONTINUE, "reason": "BEFORE_52", "valid_fridays": len(rows)}
    first = rows[:FINAL_N]
    verdict, reason = final_decision([r[1] for r in first], [r[0] for r in first],
                                     [r[2] for r in first if r[2] is not None],
                                     [r[3] for r in first if r[3] is not None])
    return {"verdict": verdict, "reason": reason, "valid_fridays": len(rows)}


# ---- kalender (ingen data) ----

def first_friday_on_or_after(d):
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def timeline(first_friday):
    """(futilitets-fredag, dom-fredag) for 26. og 52. fredag, hvis ingen falder ud."""
    return first_friday + dt.timedelta(weeks=FUTILITY_N - 1), first_friday + dt.timedelta(weeks=FINAL_N - 1)


def route_without_k3():
    """Direktoeren har afvist K3-raekkerne. Tilbage er kun den selvstaendige `ex1/1`-linje, som kraever ejerens ja og
    deploy (tidligst 2026-11-30). Foerste taellende fredag er derfor 2026-12-04."""
    first = dt.date(2026, 12, 4)
    futility, final = timeline(first)
    return {"route": "ex1/1 (kraever dateret ejer-ja og deploy)", "first_friday": first, "futility": futility,
            "final": final, "fridays_until_deadline": (DEADLINE - first).days // 7 + 1}


# ---- styrke og porte (syntetisk) ----

def sim_verdicts(gross_friday, gross_control, sd=0.0035, n=FINAL_N, cost_t=0.0011, reps=2000, seed=70):
    """Domsandele ved 52 fredage. Fredag ~ N(gross_friday, sd), fire kontroldage ~ N(gross_control, sd), placebo ~ N(0, sd)."""
    rng = random.Random(seed)
    counts = {}
    for _ in range(reps):
        gross = [rng.gauss(gross_friday, sd) for _ in range(n)]
        net = [g - cost_t for g in gross]
        deltas = [g - math.fsum(rng.gauss(gross_control, sd) for _ in range(4)) / 4 for g in gross]
        placebo = [rng.gauss(0.0, sd) for _ in range(n)]
        v, _ = final_decision(net, gross, deltas, placebo)
        counts[v] = counts.get(v, 0) + 1
    return {k: counts[k] / reps for k in sorted(counts)}


def false_stop_probability(gross_mean, sd=0.0035, n=FUTILITY_N, reps=20000, seed=71):
    """P(stop ved 26 | sand brutto-effekt): andel af simulerede stikprover med middel <= 0."""
    rng = random.Random(seed)
    se = sd / math.sqrt(n)
    return sum(rng.gauss(gross_mean, se) <= 0 for _ in range(reps)) / reps


def sim_futility_then_final(gross, sd=0.0035, reps=4000, seed=72, cost_t=0.0011):
    """Hele forloebet: stop ved 26, ellers dom ved 52. Viser, at futilitet ikke oeger type-I (kun stop tidligere)."""
    rng = random.Random(seed)
    out = {STOPPED_FUTILE: 0, "net_p_ok": 0}
    for _ in range(reps):
        xs = [rng.gauss(gross, sd) for _ in range(FINAL_N)]
        if math.fsum(xs[:FUTILITY_N]) / FUTILITY_N <= 0:
            out[STOPPED_FUTILE] += 1
            continue
        out["net_p_ok"] += one_sided_test([x - cost_t for x in xs], mu0=0.0)["p"] <= ALPHA_NET
    return {k: v / reps for k, v in out.items()}


def report(reps=2000):
    """Tallene i EX1_DESIGN_CHECK.md."""
    route = route_without_k3()
    return {"sim_mde_net_15bp_expiry_only": sim_verdicts(0.0026, 0.0, reps=reps),
            "sim_null_gross_0": sim_verdicts(0.0, 0.0, reps=reps),
            "sim_cost_only_gross_11bp": sim_verdicts(0.0011, 0.0, reps=reps),
            "sim_daily_08_effect_no_expiry": sim_verdicts(0.0026, 0.0026, reps=reps),
            "false_stop_at_26": {f"gross_{bp}bp": false_stop_probability(bp * 1e-4) for bp in (26, 11, 5, 0)},
            "sequential_size_gross_11bp": sim_futility_then_final(0.0011, reps=reps),
            "route_without_k3": {k: str(v) for k, v in route.items()}}


if __name__ == "__main__":
    print(json.dumps(report(), indent=1, sort_keys=True))
