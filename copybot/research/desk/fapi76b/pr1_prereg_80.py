"""Director order 80 P2: estimator, placebo and sensitivity for the PR1 draft (PR1_PREREG_DRAFT_80.md). UDKAST, IKKE LÅST.

Pure functions over lists the caller hands in: no file, no network, no database, no scheduler and no command-line entry.
Nothing here runs an evaluation by itself.

The observable is ln(markPrice/indexPrice), a ratio of two fields. It is NOT Binance's official premium index, and no
formula of Binance's is assumed. The primary contrast is a difference in differences of a one-slot change, so settlement
timing is separated from ordinary normalisation (hour of day and coin-type effects cancel). The funding interval and the
next settlement must be supplied per row; a missing interval is an exclusion, never a default of 8 hours.

A rejected null is an ASSOCIATION with the settlement slot. It does not show that funding causes the change.
"""
from __future__ import annotations

import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.desk import order69_power as op  # noqa: E402
from research.desk.fapi76b import fapi_designs_76b as dg  # noqa: E402
from research.tools import factory, register_v2 as v2  # noqa: E402

DAY, HOUR, WEEK = 86400, 3600, 604800
STATUS = "UDKAST, IKKE LÅST"

CFG = {"tau": 0.0010, "intervals": (4, 8), "clip": (-1.0, 2.0), "min_cell": 3, "min_weeks": 20, "alpha": 0.0125,
       "placebo_alpha": 0.05, "placebo_ratio": 0.5}
A_HOURS, C_HOURS = (4, 12, 20), (2, 6, 10, 14, 18, 22)             # UTC hour of the slot after the event
PLACEBO_A, PLACEBO_C = (6, 14, 22), (2, 10, 18)                    # the real A hours shifted +2; none of them settles
H0_REJECTED, H0_NOT_REJECTED, PLACEBO_FAILED, INSUFFICIENT = "H0_REJECTED", "H0_NOT_REJECTED", "PLACEBO_FAILED", "INSUFFICIENT_DATA"


def log_ratio(row):
    """ln(markPrice/indexPrice) for a row, or None when a price is missing or not positive. Never filled."""
    m, i = row.get("mark"), row.get("index")
    return None if not m or not i or m <= 0 or i <= 0 else math.log(m / i)


def selection_signal(rows, cfg=CFG):
    """1 at slot t if |p| >= tau at t and at t-1 with the same sign and contiguous slots. Uses only rows up to t."""
    out = [0] * len(rows)
    for t in range(1, len(rows)):
        a, b = log_ratio(rows[t - 1]), log_ratio(rows[t])
        if a is not None and b is not None and rows[t]["ts"] - rows[t - 1]["ts"] == HOUR \
                and abs(a) >= cfg["tau"] and abs(b) >= cfg["tau"] and a * b > 0:
            out[t] = 1
    return out


def events_from_rows(rows, cfg=CFG):
    """(events, counts). Each event is one contiguous one-slot change of a selected row. Exclusions are counted by reason;
    nothing is filled and no funding interval is assumed."""
    counts = {"no_interval": 0, "no_next_funding": 0, "interval_changed": 0, "other_interval": 0, "missing_outcome": 0, "clipped": 0}
    sig = selection_signal(rows, cfg)
    events = []
    for t in range(1, len(rows)):
        if not sig[t]:
            continue
        if t + 1 >= len(rows) or rows[t + 1]["ts"] - rows[t]["ts"] != HOUR or log_ratio(rows[t + 1]) is None:
            counts["missing_outcome"] += 1
            continue
        interval = rows[t].get("interval_h")
        if interval is None:
            counts["no_interval"] += 1
            continue
        if rows[t - 1].get("interval_h") != interval or rows[t + 1].get("interval_h") != interval:
            counts["interval_changed"] += 1
            continue
        if interval not in cfg["intervals"]:
            counts["other_interval"] += 1
            continue
        nf = rows[t].get("next_funding_ts")
        if nf is None:
            counts["no_next_funding"] += 1
            continue
        p0, p1 = log_ratio(rows[t]), log_ratio(rows[t + 1])
        sign = 1 if p0 > 0 else -1
        raw = (abs(p0) - sign * p1) / abs(p0)
        low, high = cfg["clip"]
        d = min(high, max(low, raw))
        counts["clipped"] += d != raw
        events.append({"ts": rows[t]["ts"], "hour": (rows[t + 1]["ts"] % DAY) // HOUR, "interval": interval, "D": d,
                       "settle": rows[t]["ts"] < nf <= rows[t + 1]["ts"], "abs_p": abs(p0)})
    return events, counts


def decay_over_interval(rows, t):
    """Descriptive only: share of |p| gone after the row's own actual interval, or None if any slot is missing."""
    interval = rows[t].get("interval_h")
    if interval is None or t + interval >= len(rows) or rows[t + interval]["ts"] - rows[t]["ts"] != interval * HOUR:
        return None
    if any(r.get("interval_h") != interval for r in rows[t:t + interval + 1]):
        return None
    p0, p1 = log_ratio(rows[t]), log_ratio(rows[t + interval])
    if p0 is None or p1 is None or p0 == 0:
        return None
    return (abs(p0) - (1 if p0 > 0 else -1) * p1) / abs(p0)


def _week(ts):
    return (ts + 3 * DAY) // WEEK                                   # weeks start on Monday 00:00 UTC


def _expected_settle(interval, hour, placebo):
    return not placebo and interval == 4 and hour in A_HOURS


def weekly_theta(events, a_hours, c_hours, placebo=False, cfg=CFG):
    """One value per week: (4h A - 4h C) - (8h A - 8h C) of the cell means of D. An event whose actual settlement flag
    disagrees with the schedule the cell assumes is dropped and counted. Weeks with a thin cell are dropped and counted."""
    cells, mismatch = {}, 0
    for e in events:
        side = "A" if e["hour"] in a_hours else ("C" if e["hour"] in c_hours else None)
        if side is None:
            continue
        if e["settle"] != _expected_settle(e["interval"], e["hour"], placebo):
            mismatch += 1
            continue
        cells.setdefault(_week(e["ts"]), {}).setdefault((e["interval"], side), []).append(e["D"])
    out, dropped = [], 0
    keys = [(4, "A"), (4, "C"), (8, "A"), (8, "C")]
    for w in sorted(cells):
        if any(len(cells[w].get(k, [])) < cfg["min_cell"] for k in keys):
            dropped += 1
            continue
        m = {k: statistics.fmean(cells[w][k]) for k in keys}
        out.append((m[(4, "A")] - m[(4, "C")]) - (m[(8, "A")] - m[(8, "C")]))
    return out, {"mismatch": mismatch, "weeks_dropped": dropped}


def naive_single_difference(events):
    """(4h coins, A hours) minus (4h coins, C hours), without the 8h control. Kept only to show in tests what it confuses."""
    a = [e["D"] for e in events if e["interval"] == 4 and e["hour"] in A_HOURS]
    c = [e["D"] for e in events if e["interval"] == 4 and e["hour"] in C_HOURS]
    return statistics.fmean(a) - statistics.fmean(c)


def _t(values):
    sd = statistics.stdev(values)
    return statistics.fmean(values) / (sd / math.sqrt(len(values))) if sd > 0 else 0.0


def evaluate(events, cfg=CFG):
    """The labels are descriptive. H0: theta <= 0. PLACEBO_FAILED means the primary contrast is not interpreted at all."""
    theta, tc = weekly_theta(events, A_HOURS, C_HOURS, False, cfg)
    placebo, pc = weekly_theta(events, PLACEBO_A, PLACEBO_C, True, cfg)
    out = {"n_weeks": len(theta), "n_placebo_weeks": len(placebo), "counts": tc, "placebo_counts": pc}
    if len(theta) < cfg["min_weeks"] or len(placebo) < cfg["min_weeks"]:
        return dict(out, label=INSUFFICIENT)
    mean, t = statistics.fmean(theta), _t(theta)
    half = op.t_quantile(0.975, len(theta) - 1) * statistics.stdev(theta) / math.sqrt(len(theta))
    pmean, pt = statistics.fmean(placebo), _t(placebo)
    crit, pcrit = op.t_quantile(1 - cfg["alpha"], len(theta) - 1), op.t_quantile(1 - cfg["placebo_alpha"] / 2, len(placebo) - 1)
    out.update(theta=mean, t=t, crit=crit, ci95=(mean - half, mean + half), placebo_theta=pmean, placebo_t=pt, placebo_crit=pcrit)
    rejected = mean > 0 and t > crit
    if abs(pt) > pcrit or (rejected and abs(pmean) >= cfg["placebo_ratio"] * abs(mean)):
        return dict(out, label=PLACEBO_FAILED)
    return dict(out, label=H0_REJECTED if rejected else H0_NOT_REJECTED)


def rt_est(v):
    """Amendment 21i point 2: the book round trip for 5,000 USD as a fraction, for one leg. An estimate from one snapshot."""
    return math.exp(0.8999) * v ** (-0.4540)


def hurdle_21i(v):
    """Amendment 21i point 2: c = max(0.46 %, 2 * (2 * 0.040 % + RT_est(V))) as a fraction, V = 30-day mean quote volume."""
    return max(0.0046, 2 * (2 * 0.0004 + rt_est(v)))


def share_above_hurdle(items):
    """items: (abs_p, v). Share of events whose whole gap is at least the hurdle, i.e. the only events a full convergence
    could even pay for. Descriptive: it is not a return, a fill or an executable price."""
    items = list(items)
    return sum(p >= hurdle_21i(v) for p, v in items) / len(items) if items else None


# Sensitivity only: the MDE over assumed spreads and lengths. This module deliberately has no power-at-an-assumed-effect.
SENS_SD, SENS_WEEKS = (0.15, 0.30, 0.45), (26, 52)


def mde_grid(alpha=CFG["alpha"]):
    return {(s, n): op.mde(s, n, alpha=alpha) for s in SENS_SD for n in SENS_WEEKS}


def register_v2_record():
    """A FUTURE record in memory. The window is a planning assumption, and the interval source is not approved today."""
    params = v2.parameters_block({
        "status": STATUS, "cfg": {k: (list(x) if isinstance(x, tuple) else x) for k, x in CFG.items()}, "a_hours": list(A_HOURS),
        "c_hours": list(C_HOURS), "placebo_a": list(PLACEBO_A), "placebo_c": list(PLACEBO_C), "alpha": "0 beskrivende",
        "independent_discovery_claim": False, "causal_claim": False, "register_n_minimum": 19438, "register_n_is_final": False,
        "n_eff": "MISSING_INPUT", "requires_unapproved_stream": "fwd_spec_journal"})
    source = {"census/1": "EXISTING_ACTIVE", "fwd_spec_journal": "PROPOSED_NEEDS_SEPARATE_APPROVAL"}
    return v2.record(
        "PR1-PREREG-80", v2.FUTURE, hypothesis_id="PR1", lineage="cross_venue_perp_gap",
        trial_universe={"definition": "primær kontrast K = 1: theta", "size": 1, "members_sha256": factory.sha(["theta"])},
        variants_tested=None, parameters=params, code_hash=_own_sha(),
        data_source={"name": "census/1 + fwd_spec_journal", "sha256": factory.sha(source)},
        data_period={"start": "2027-01-04", "end": "2028-01-02"},
        cost_model={"name": "ingen ordrer; 21i-gulv kun som beskrivende tærskel", "round_trip_bps": 0.0, "sha256": factory.sha({"floor_bps": 46})},
        evaluation_method={"name": "ugevis difference-in-differences; placebo-gate; beskrivende", "sha256": factory.sha({"t": "one-sided", "alpha": CFG["alpha"]})},
        data_quality={"status": "NOT_CHECKED"}, deviations=[],
        register_snapshot={"sha256": v2.snapshot_sha(dg.snapshot_text()), "rules_version": 1})


def _own_sha():
    import hashlib
    with open(__file__, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
