"""Director order 75 P1: a statistical validation engine that separates documented evidence, missing data and chance.

Every function is pure and deterministic (resampling takes an explicit seed). Each check returns
    {"check", "status", "reason", "metrics", "missing"}
with status one of PASS, FAIL, INCONCLUSIVE, MISSING_INPUT, CONTAMINATED. `assess` combines them; an overall PASS needs
every required check to have run and passed.

THE EIGHT CHECKS AND THEIR METHOD
- multiple testing: block-bootstrap max-t over the whole family (keeps correlation and autocorrelation); Bonferroni on
  the largest documented N when only part of the family exists. An understated N is a FAIL.
- correlation: pairwise correlation, clusters, max-equivalent N (diagnostic). A claimed N_eff or claimed independent
  confirmations that the correlation does not support is a FAIL.
- lookahead: timestamps, and truncation invariance of the signal computation. Returns alone cannot show lookahead.
- survivorship: point-in-time universe against what was tested and what was delisted.
- missing observations: gaps against the expected axis, fill-like runs, and gaps that follow losses.
- contamination: protected windows, banned sources, quarantined artifacts, train/test overlap, embargo.
- overfitting: PBO (CSCV) and DSR through register_stats, only on series with provenance or explicitly synthetic.
- costs: assumed cost against a documented floor, edge after the floor and after a stress of it, net reconciliation.

WHAT THE STATUSES MEAN. PASS: the check ran and found nothing wrong, or the effect survived it. FAIL: a defect, or a
claim refuted with enough power. INCONCLUSIVE: it ran and cannot tell. MISSING_INPUT: a needed input does not exist, and
nothing was filled in. CONTAMINATED: the data itself may not be used.

Max-z is a diagnostic and never a limit here: see max_z_diagnostic. Thresholds are stated as parameters and are decision
conventions, not calibrated bars. This module decides nothing about a strategy, opens no file and uses no network.
"""
from __future__ import annotations

import math
import operator
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import register_stats as rs  # noqa: E402

PASS, FAIL, INCONCLUSIVE, MISSING_INPUT, CONTAMINATED = "PASS", "FAIL", "INCONCLUSIVE", rs.MISSING_INPUT, "CONTAMINATED"
STATUSES = (PASS, FAIL, INCONCLUSIVE, MISSING_INPUT, CONTAMINATED)
ORDER = (CONTAMINATED, FAIL, MISSING_INPUT, INCONCLUSIVE, PASS)     # the worst status present wins

MULTIPLE_TESTING, CORRELATION, LOOKAHEAD, SURVIVORSHIP = "multiple_testing", "correlation", "lookahead", "survivorship"
MISSING_OBS, CONTAMINATION, OVERFITTING, COSTS = "missing_observations", "contamination", "overfitting", "costs"
ALL_CHECKS = (MULTIPLE_TESTING, CORRELATION, LOOKAHEAD, SURVIVORSHIP, MISSING_OBS, CONTAMINATION, OVERFITTING, COSTS)

MIN_PERIODS = 30                                         # below this the normal approximation is not used
NORMAL = statistics.NormalDist()


def result(check, status, reason, metrics=None, missing=()):
    return {"check": check, "status": status, "reason": reason, "metrics": metrics or {}, "missing": list(missing)}


def _is_num(v):
    return rs._is_num(v)


def _absent(v):
    return rs._absent(v)


def _names_absent(**inputs):
    return [k for k, v in inputs.items() if v is None]


def _matrix_problem(check, series, time_index):
    """A result when `series` is not N complete series on one stated axis, else None. A gap is never filled."""
    missing = _names_absent(series=series, time_index=time_index)
    if missing:
        return result(check, MISSING_INPUT, "no series without a stated shared time axis", missing=missing)
    if not len(series):
        return result(check, MISSING_INPUT, "no series", missing=["series"])
    if len(time_index) < 2 or any(a >= b for a, b in zip(time_index, time_index[1:])):
        return result(check, MISSING_INPUT, "time_index is not strictly increasing", missing=["time_index"])
    for i, x in enumerate(series):
        if x is None or len(x) != len(time_index):
            return result(check, MISSING_INPUT, "a series is not on the shared time axis", missing=[f"series[{i}]"])
        gaps = [j for j, v in enumerate(x) if _absent(v)]
        if gaps:
            return result(check, MISSING_INPUT, "gaps are not filled",
                          {"gaps": len(gaps)}, [f"series[{i}][{j}]" for j in gaps[:20]])
        if not all(_is_num(v) for v in x):
            return result(check, MISSING_INPUT, f"series[{i}] holds a non-number", missing=[f"series[{i}]"])
    return None


def _t_stat(x):
    """Mean over its standard error (population sd, as the bootstrap uses), or None for a flat series."""
    t = len(x)
    mean = math.fsum(x) / t
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in x) / t)
    return None if sd <= 1e-15 else mean / sd * math.sqrt(t)


def block_length(t):
    """Fixed block length 2 t^(1/3), rounded, at least 2. The order is Hall, Horowitz & Jing 1995; the factor 2 is a
    convention set on synthetic AR(1) worlds, because t^(1/3) alone over-rejected there (RESEARCH_EVIDENCE_ENGINE_75.md)."""
    return max(2, round(2 * t ** (1.0 / 3.0)))


def null_max_t(series, reps, seed, block=None):
    """Bootstrap distribution of the largest t over the family under H0 (each series centred on its own mean). Circular
    blocks, the same draw for every series, so cross-correlation and short-range autocorrelation are kept."""
    t, n = len(series[0]), len(series)
    block = block or block_length(t)
    if type(block) is not int or not 1 <= block <= t:
        raise ValueError("block must be an integer in 1..T")
    rng = random.Random(seed)
    prefix = []
    for x in series:
        s1, s2, a, b = [0.0], [0.0], 0.0, 0.0
        for v in list(x) + list(x):
            a += v
            b += v * v
            s1.append(a)
            s2.append(b)
        prefix.append((s1, s2, math.fsum(x) / t))
    maxima = []
    n_full, rest = divmod(t, block)
    for _ in range(reps):
        cuts = [(a, a + block) for a in (rng.randrange(t) for _ in range(n_full))]
        if rest:
            a = rng.randrange(t)
            cuts.append((a, a + rest))
        best = -math.inf
        for s1, s2, centre in prefix:
            m1 = sum(s1[e] - s1[s] for s, e in cuts) / t
            m2 = sum(s2[e] - s2[s] for s, e in cuts) / t
            var = m2 - m1 * m1
            if var > 1e-18:
                best = max(best, (m1 - centre) / math.sqrt(var) * math.sqrt(t))
        maxima.append(best if best != -math.inf else 0.0)
    return maxima, block


def max_z_diagnostic(n=None):
    """E[max z] for a stated N, as a diagnostic only. It is not a limit: no check compares a statistic with this number.
    The register's total is a conservative minimum and not a final N; N_eff stays MISSING_INPUT without return series."""
    n_ = rs.REGISTER_COUNTS["variants"] if n is None else n
    return {"kind": "DIAGNOSTIC", "n": n_, "n_is_final": False, "expected_max_z": rs.expected_max_z(n_),
            "calibrated_threshold": None, "n_eff": MISSING_INPUT,
            "reason": "expected maximum of N iid normals; not a calibrated significance limit"}


def check_multiple_testing(series=None, time_index=None, best_t=None, n_reported=None, n_tested=None, n_preregistered=None,
                           alpha=0.05, min_sharpe=None, power_target=0.8, reps=999, seed=75, block=None):
    """Does the best variant survive the search that produced it? `series` is the family of net returns; alternatively
    `best_t` alone, the t-statistic of the best variant. N is the largest documented count: n_tested (the register) and
    n_preregistered (the universe). n_reported is what the analyst claims, and alone proves nothing.
    min_sharpe (per period) is the smallest effect of interest: without it a null result is INCONCLUSIVE, never FAIL."""
    check = MULTIPLE_TESTING
    documented = [v for v in (n_tested, n_preregistered) if v is not None]
    if not documented:
        return result(check, MISSING_INPUT, "the number of variants is undocumented; it is not guessed",
                      {"n_reported": n_reported}, ["n_tested", "n_preregistered"])
    if any(type(v) is not int or v < 1 for v in documented + ([] if n_reported is None else [n_reported])):
        return result(check, MISSING_INPUT, "counts must be integers >= 1", missing=["n_tested"])
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if n_reported is not None and n_tested is not None and n_reported < n_tested:
        return result(check, FAIL, f"N understated: {n_reported} reported against {n_tested} registered as tested",
                      {"n_reported": n_reported, "n_tested": n_tested})
    n_used = max(documented + ([] if n_reported is None else [n_reported]))
    metrics = {"n_used": n_used, "n_tested": n_tested, "n_preregistered": n_preregistered, "n_reported": n_reported,
               "n_note": "largest documented count; never lowered"}
    if series is not None:
        problem = _matrix_problem(check, series, time_index)
        if problem:
            return problem
        if len(series) > n_used:
            return result(check, FAIL, f"{len(series)} series exist but only {n_used} were registered",
                          {**metrics, "series": len(series)})
        t = len(time_index)
        if t < MIN_PERIODS:
            return result(check, INCONCLUSIVE, f"{t} periods is below {MIN_PERIODS}", {**metrics, "periods": t})
        ts = [v for v in (_t_stat(x) for x in series) if v is not None]
        if not ts:
            return result(check, MISSING_INPUT, "every series is flat", metrics, ["series"])
        best = max(ts)
    else:
        if best_t is None:
            return result(check, MISSING_INPUT, "no family of series and no statistic", metrics, ["series", "best_t"])
        if not _is_num(best_t):
            return result(check, MISSING_INPUT, "best_t is not a number", metrics, ["best_t"])
        best, t = best_t, None
    bonf = min(1.0, n_used * (1.0 - NORMAL.cdf(best)))
    metrics.update(best_t=best, bonferroni_p=bonf, alpha=alpha, method="BONFERRONI")
    p = bonf
    if series is not None and len(series) == n_used:
        maxima, used_block = null_max_t(series, reps, seed, block)
        p = (1 + sum(1 for v in maxima if v >= best)) / (reps + 1)
        metrics.update(method="BLOCK_BOOTSTRAP_MAX_T", max_t_p=p, reps=reps, seed=seed, block=used_block)
    elif series is not None:
        metrics["note"] = f"only {len(series)} of {n_used} series exist, so the correlation cannot be used"
    if p <= alpha:
        return result(check, PASS, f"best t {best:.2f} survives the search over N = {n_used} (p = {p:.4g})", metrics)
    if min_sharpe is None or t is None:
        return result(check, INCONCLUSIVE, f"not significant over N = {n_used} (p = {p:.4g}), and no stated "
                      "smallest effect with a known sample size, so no effect can be ruled out", metrics)
    crit = NORMAL.inv_cdf(1 - alpha / n_used)
    power = NORMAL.cdf(min_sharpe * math.sqrt(t) - crit)
    metrics.update(min_sharpe=min_sharpe, power=power)
    if power >= power_target:
        return result(check, FAIL, f"not significant over N = {n_used} (p = {p:.4g}) with power {power:.2f} "
                      f"for a per-period Sharpe of {min_sharpe}", metrics)
    return result(check, INCONCLUSIVE, f"not significant over N = {n_used} (p = {p:.4g}), but power is only "
                  f"{power:.2f} for a per-period Sharpe of {min_sharpe}", metrics)


def _standardise(x):
    mean = math.fsum(x) / len(x)
    d = [v - mean for v in x]
    norm = math.sqrt(math.fsum(v * v for v in d))
    return None if norm <= 1e-15 else [v / norm for v in d]


def _implied_n(mean_max):
    """The N whose expected iid maximum equals this value: a max-equivalent diagnostic, not a documented N_eff."""
    if mean_max <= 0:
        return 1.0
    lo, hi = 1.0, 1e9
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        if rs.expected_max_z(mid) < mean_max:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def check_correlation(series=None, time_index=None, claimed_n_eff=None, confirming=None, cluster_threshold=0.9,
                      z_tolerance=0.25, reps=299, seed=75, block=None):
    """How much of the family's size is real diversity? Fails a claimed N_eff smaller than the family supports, and
    `confirming` (indices claimed as independent confirmations) that are mostly one cluster."""
    check = CORRELATION
    problem = _matrix_problem(check, series, time_index)
    if problem:
        return problem
    n, t = len(series), len(time_index)
    if n < 2:
        return result(check, MISSING_INPUT, "correlation needs at least 2 series", {"series": n}, ["series"])
    if t < MIN_PERIODS:
        return result(check, INCONCLUSIVE, f"{t} periods is below {MIN_PERIODS}", {"series": n, "periods": t})
    std = [_standardise(x) for x in series]
    if any(z is None for z in std):
        return result(check, INCONCLUSIVE, "a series is flat, so its correlation is undefined", {"series": n})
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    total = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            rho = sum(map(operator.mul, std[i], std[j]))
            total += rho
            if abs(rho) >= cluster_threshold:
                parent[find(i)] = find(j)
    mean_corr = total / (n * (n - 1) / 2)
    maxima, used_block = null_max_t(series, reps, seed, block)
    null_mean_max = statistics.fmean(maxima)
    metrics = {"series": n, "periods": t, "mean_correlation": mean_corr, "clusters": len({find(i) for i in range(n)}),
               "flat_n_eff": rs.flat_effective_n(mean_corr, n), "null_mean_max_t": null_mean_max,
               "max_equivalent_n": _implied_n(null_mean_max), "max_equivalent_n_kind": "DIAGNOSTIC, not a documented N_eff",
               "reps": reps, "seed": seed, "block": used_block}
    if claimed_n_eff is not None:
        if not _is_num(claimed_n_eff) or claimed_n_eff < 1:
            return result(check, MISSING_INPUT, "claimed_n_eff must be a number >= 1", metrics, ["claimed_n_eff"])
        claimed_z = rs.expected_max_z(claimed_n_eff)
        metrics.update(claimed_n_eff=claimed_n_eff, claimed_expected_max=claimed_z)
        if null_mean_max - claimed_z > z_tolerance:
            return result(check, FAIL, f"claimed N_eff {claimed_n_eff} implies an expected maximum of {claimed_z:.2f}, "
                          f"but the family's own null maximum is {null_mean_max:.2f}: selection is understated", metrics)
    if confirming is not None:
        if not confirming or any(type(i) is not int or not 0 <= i < n for i in confirming):
            return result(check, MISSING_INPUT, "confirming must list valid series indices", metrics, ["confirming"])
        distinct = len({find(i) for i in confirming})
        metrics.update(confirming=len(set(confirming)), distinct_confirming_clusters=distinct)
        if distinct < len(set(confirming)):
            return result(check, FAIL, f"{len(set(confirming))} claimed confirmations are only {distinct} distinct "
                          f"cluster(s) at |rho| >= {cluster_threshold}", metrics)
    return result(check, PASS, "correlation measured; no claim conflicts with it", metrics)


def check_lookahead(decision_times=None, feature_times=None, signal_fn=None, data=None, n_checks=20, tolerance=1e-12):
    """Was anything used before it was known? (a) feature_times[i] must not be later than decision_times[i] (numbers);
    (b) truncation invariance: signal_fn(data[:t + 1])[t] must equal signal_fn(data)[t]. signal_fn must be pure.
    Lookahead cannot be told from real skill in a return series alone, so with neither input the status is MISSING_INPUT."""
    check = LOOKAHEAD
    have_times = decision_times is not None or feature_times is not None
    have_fn = signal_fn is not None or data is not None
    if not have_times and not have_fn:
        return result(check, MISSING_INPUT, "no timestamps and no recomputable signal; returns alone cannot show lookahead",
                      missing=["decision_times", "feature_times", "signal_fn", "data"])
    metrics = {}
    if have_times:
        missing = _names_absent(decision_times=decision_times, feature_times=feature_times)
        if missing:
            return result(check, MISSING_INPUT, "timestamps come in pairs", missing=missing)
        if len(decision_times) != len(feature_times):
            return result(check, MISSING_INPUT, "timestamps differ in length", missing=["feature_times"])
        if not all(_is_num(d) and _is_num(f) for d, f in zip(decision_times, feature_times)):
            return result(check, MISSING_INPUT, "a timestamp is absent or not a number; none is assumed",
                          missing=["feature_times"])
        late = [i for i, (d, f) in enumerate(zip(decision_times, feature_times)) if f > d]
        metrics.update(timestamps_checked=len(decision_times), timestamps_late=len(late))
        if late:
            return result(check, FAIL, f"{len(late)} feature(s) dated after the decision (first at row {late[0]})", metrics)
    if have_fn:
        missing = _names_absent(signal_fn=signal_fn, data=data)
        if missing:
            return result(check, MISSING_INPUT, "a recomputation needs both the function and the data", metrics, missing)
        t = len(data)
        if t < 3 or type(n_checks) is not int or n_checks < 1:
            return result(check, INCONCLUSIVE, "too little data to truncate", {**metrics, "periods": t})
        try:
            full = list(signal_fn(list(data)))
            if len(full) != t:
                return result(check, INCONCLUSIVE, "signal_fn output differs in length from its input", metrics)
            points = sorted({round((i + 1) * (t - 1) / (n_checks + 1)) for i in range(n_checks)})
            differ = []
            for p in points:
                cut = list(signal_fn(list(data[:p + 1])))
                if len(cut) != p + 1:
                    return result(check, INCONCLUSIVE, "signal_fn output differs in length from its input", metrics)
                a, b = full[p], cut[p]
                same = (a is None and b is None) or \
                    (a is not None and b is not None and abs(a - b) <= tolerance * max(1.0, abs(a), abs(b)))
                if not same:
                    differ.append(p)
        except Exception as exc:                         # the function is the caller's; it cannot be judged if it fails
            return result(check, INCONCLUSIVE, f"signal_fn raised {type(exc).__name__}", metrics)
        metrics.update(truncation_points=len(points), truncation_differs=len(differ))
        if differ:
            return result(check, FAIL, f"the signal changes when future data is removed ({len(differ)} of "
                          f"{len(points)} checkpoints, first at row {differ[0]})", metrics)
    return result(check, PASS, "nothing was dated after its decision and truncation changes nothing", metrics)


def check_survivorship(universe=None, tested=None, delisted=None, universe_asof=None, period_start=None, excluded=None,
                       max_unexplained=0.05, asset_mean_returns=None):
    """Was the test run on the point-in-time universe, delisted members included? `delisted` is the list of members that
    left during the period ([] states there were none; None is unknown). `excluded` maps a member to its reason."""
    check = SURVIVORSHIP
    missing = _names_absent(universe=universe, tested=tested, delisted=delisted, universe_asof=universe_asof,
                            period_start=period_start)
    if missing:
        return result(check, MISSING_INPUT, "the universe cannot be judged without these; none is assumed", missing=missing)
    uni, got, gone = set(universe), set(tested), set(delisted)
    if not uni:
        return result(check, MISSING_INPUT, "the universe is empty", missing=["universe"])
    excluded = excluded or {}
    dropped = uni - got
    explained = {k for k in dropped if isinstance(excluded.get(k), str) and excluded[k].strip()}
    unexplained = dropped - explained
    delisted_dropped = dropped & gone
    metrics = {"universe": len(uni), "tested": len(got & uni), "dropped": len(dropped), "unexplained": len(unexplained),
               "delisted": len(gone), "delisted_dropped": len(delisted_dropped), "outside_universe": len(got - uni)}
    if asset_mean_returns is not None and uni <= set(asset_mean_returns) and got & uni:
        everyone = statistics.fmean(asset_mean_returns[k] for k in sorted(uni))
        kept = statistics.fmean(asset_mean_returns[k] for k in sorted(got & uni))
        metrics.update(mean_return_universe=everyone, mean_return_tested=kept, survivorship_bias=kept - everyone)
    if not _comparable(universe_asof, period_start):
        return result(check, MISSING_INPUT, "universe_asof and period_start are not comparable",
                      metrics, ["universe_asof", "period_start"])
    if universe_asof > period_start:
        return result(check, FAIL, f"universe fixed at {universe_asof}, after the period start {period_start}: the "
                      "members were chosen knowing who survived", metrics)
    if got - uni:
        return result(check, FAIL, f"{len(got - uni)} tested member(s) are outside the pre-registered universe", metrics)
    if delisted_dropped:
        return result(check, FAIL, f"{len(delisted_dropped)} delisted member(s) were left out of the test", metrics)
    if unexplained:
        if len(unexplained) / len(uni) > max_unexplained:
            return result(check, FAIL, f"{len(unexplained)} of {len(uni)} members dropped without a stated reason", metrics)
        return result(check, INCONCLUSIVE, f"{len(unexplained)} member(s) dropped without a stated reason", metrics)
    return result(check, PASS, "point-in-time universe tested, delisted members included", metrics)


def _longest_constant_run(values):
    best, run, prev = 0, 0, object()
    for v in values:
        if v is not None and v == prev:
            run += 1
        else:
            run = 1 if v is not None else 0
        prev = v
        best = max(best, run)
    return best


def check_missing_observations(values=None, time_index=None, expected_index=None, max_missing_share=0.05, fill_run=5,
                               flat_is_valid=False, loss_quantile=0.2, min_z=3.0):
    """Are the observations there, and is their absence innocent? `expected_index` is the axis that should exist.
    Silent holes in `time_index` and None values both count as missing. A long exactly-constant run looks like filling
    (heuristic; flat_is_valid=True for a book that really sits in cash). Gaps that follow losses are a biased sample."""
    check = MISSING_OBS
    missing = _names_absent(values=values, time_index=time_index, expected_index=expected_index)
    if missing:
        return result(check, MISSING_INPUT, "without the expected axis a gap cannot be seen", missing=missing)
    if len(values) != len(time_index):
        return result(check, MISSING_INPUT, "values and time_index differ in length", missing=["values"])
    if not expected_index:
        return result(check, MISSING_INPUT, "the expected axis is empty", missing=["expected_index"])
    if any(not (v is None or _is_num(v)) for v in values):
        return result(check, MISSING_INPUT, "values hold a non-number", missing=["values"])
    outside = set(time_index) - set(expected_index)
    by_time = dict(zip(time_index, values))
    aligned = [by_time.get(k) for k in expected_index]
    gaps = [i for i, v in enumerate(aligned) if v is None]
    share = len(gaps) / len(aligned)
    run = _longest_constant_run(aligned)
    metrics = {"expected": len(aligned), "observed": len(aligned) - len(gaps), "missing": len(gaps), "missing_share": share,
               "outside_expected": len(outside), "longest_constant_run": run}
    if outside:
        return result(check, FAIL, f"{len(outside)} observation(s) lie outside the expected axis", metrics)
    if not flat_is_valid and run >= fill_run:
        return result(check, FAIL, f"{run} consecutive identical values look like filled gaps", metrics)
    pairs = [(aligned[i], aligned[i + 1] is None) for i in range(len(aligned) - 1) if aligned[i] is not None]
    if len(pairs) >= MIN_PERIODS and 0 < loss_quantile < 1 and any(g for _, g in pairs):
        prior = sorted(v for v, _ in pairs)
        cut = prior[max(0, int(len(prior) * loss_quantile) - 1)]
        low = [g for v, g in pairs if v <= cut]
        rest = [g for v, g in pairs if v > cut]
        if low and rest:
            p1, p2 = sum(low) / len(low), sum(rest) / len(rest)
            pool = (sum(low) + sum(rest)) / len(pairs)
            denom = math.sqrt(pool * (1 - pool) * (1 / len(low) + 1 / len(rest))) if 0 < pool < 1 else 0.0
            z = (p1 - p2) / denom if denom else 0.0
            metrics.update(gap_rate_after_loss=p1, gap_rate_otherwise=p2, gap_loss_z=z)
            if z >= min_z and p1 > 2 * p2:
                return result(check, FAIL, f"gaps follow losses ({p1:.1%} after the worst {loss_quantile:.0%} of periods "
                              f"against {p2:.1%}): the observed sample is biased", metrics)
    if share > max_missing_share:
        return result(check, MISSING_INPUT, f"{share:.1%} of the expected observations are missing "
                      f"(limit {max_missing_share:.0%}); they are not filled", metrics, ["values"])
    return result(check, PASS, f"{share:.1%} missing, no filling, and no link between gaps and losses", metrics)


def _overlaps(a, b):
    return a[0] <= b[1] and b[0] <= a[1]


def _comparable(a, b):
    try:
        a < b
    except TypeError:
        return False
    return a is not None and b is not None


def check_contamination(windows=None, protected_windows=None, sources=None, banned_sources=None, artifacts=None,
                        quarantined=None, train_ids=None, test_ids=None, train_end=None, test_start=None, embargo=0,
                        declared_data_quality=None):
    """May this data be used at all? Windows are (start, end), inclusive and comparable. protected_windows and
    banned_sources and quarantined must be stated ([] = none); train/test ids and boundaries are checked when given."""
    check = CONTAMINATION
    missing = _names_absent(windows=windows, protected_windows=protected_windows, sources=sources,
                            banned_sources=banned_sources, artifacts=artifacts, quarantined=quarantined)
    if missing:
        return result(check, MISSING_INPUT, "contamination cannot be ruled out without these", missing=missing)
    spans = list(windows) + list(protected_windows)
    if any(not isinstance(w, (list, tuple)) or len(w) != 2 or not _comparable(w[0], w[1]) or
           not _comparable(w[0], spans[0][0]) for w in spans):
        return result(check, MISSING_INPUT, "a window is not a comparable (start, end) pair", missing=["windows"])
    if (train_end is None) != (test_start is None) or (train_end is not None and
                                                       not (_is_num(train_end) and _is_num(test_start))):
        return result(check, MISSING_INPUT, "train_end and test_start go together, as numbers",
                      missing=["train_end", "test_start"])
    found, metrics = [], {"windows": len(windows), "sources": len(sources), "artifacts": len(artifacts)}
    if declared_data_quality == "CONTAMINATED":
        found.append("the register declares this data CONTAMINATED")
    hit = [(w, p) for w in windows for p in protected_windows if _overlaps(w, p)]
    if hit:
        found.append(f"window {hit[0][0]} overlaps protected window {hit[0][1]}")
    banned = sorted(set(sources) & set(banned_sources))
    if banned:
        found.append(f"banned source(s) used: {banned}")
    bad = sorted(set(artifacts) & set(quarantined))
    if bad:
        found.append(f"{len(bad)} quarantined artifact(s) used")
    if train_ids is not None and test_ids is not None:
        common = set(train_ids) & set(test_ids)
        metrics["train_test_overlap"] = len(common)
        if common:
            found.append(f"{len(common)} row(s) are in both train and test")
    if train_end is not None and test_start is not None:
        metrics["train_test_gap"] = test_start - train_end
        if test_start - train_end <= embargo:
            found.append(f"train ends {train_end}, test starts {test_start}: embargo of {embargo} not kept")
    metrics["findings"] = len(found)
    if found:
        return result(check, CONTAMINATED, "; ".join(found), metrics)
    return result(check, PASS, "no protected window, banned source, quarantined artifact or leakage found", metrics)


def _series_from(records, series, time_index, synthetic):
    """(series, time_index, origin, problem). Only a validated record or an explicit synthetic label admits a series."""
    if records is not None:
        out = []
        for rec in records:
            errors = rs.validate(rec)
            if errors:
                return None, None, None, f"{rec.get('record_id')}: " + "; ".join(errors)
            if rec.get("net_returns") is None:
                return None, None, None, f"{rec['record_id']}: no documented series"
            out.append(rec["net_returns"])
        axis = records[0]["net_returns_index"] if records else None
        if any(r["net_returns_index"] != axis for r in records):
            return None, None, None, "records are not on one time axis"
        return out, axis, "PROVENANCE_RECORDS", None
    if series is not None and synthetic is True:
        return series, time_index, "SYNTHETIC_TEST", None
    if series is not None:
        return None, None, None, "a series without provenance is not used; pass register_stats records"
    return None, None, None, "no series"


def check_overfitting(records=None, series=None, time_index=None, n_tested=None, s=8, synthetic=False, pbo_fail=0.5,
                      pbo_pass=0.2, dsr_fail=0.5, dsr_pass=0.95, persistence_limit=0.5):
    """PBO by CSCV and the DSR of the best variant, both through register_stats and only when their inputs exist. A real
    series must arrive as register_stats records (hashed provenance). `series` needs synthetic=True, and the result then
    says so. The DSR uses N = n_tested and the Sharpe dispersion of every trial, so the family must be complete."""
    check = OVERFITTING
    data, axis, origin, problem = _series_from(records, series, time_index, synthetic)
    if problem:
        return result(check, MISSING_INPUT, problem, missing=["records"])
    matrix = _matrix_problem(check, data, axis)
    if matrix:
        return matrix
    metrics = {"origin": origin, "series": len(data), "periods": len(axis), "n_tested": n_tested}
    if n_tested is None:
        return result(check, MISSING_INPUT, "the number of trials is undocumented; DSR and PBO are not computed", metrics,
                      ["n_tested"])
    if len(data) != n_tested:
        return result(check, MISSING_INPUT, f"{len(data)} series against {n_tested} tested: DSR needs every trial", metrics,
                      ["series"])
    moments = [rs.moments(x) for x in data]
    bad = [i for i, m in enumerate(moments) if m["status"] != rs.OK]
    if bad:
        return result(check, MISSING_INPUT, f"series[{bad[0]}]: {moments[bad[0]]['reason']}", metrics, [f"series[{bad[0]}]"])
    variance = rs.trial_sharpe_variance([m["sharpe"] for m in moments])
    best_i = max(range(len(moments)), key=lambda i: moments[i]["sharpe"])
    m = moments[best_i]
    dsr = rs.deflated_sharpe(m["sharpe"], m["n_obs"], m["skew"], m["kurtosis"], n_tested, variance.get("sharpe_variance"))
    pbo = rs.pbo_cscv(data, axis, s=s)
    metrics.update(dsr_status=dsr["status"], pbo_status=pbo["status"], dsr=dsr.get("dsr"), pbo=pbo.get("pbo"),
                   best_index=best_i, best_sharpe=m["sharpe"])
    if dsr["status"] != rs.OK or pbo["status"] != rs.OK:
        return result(check, MISSING_INPUT, f"DSR: {dsr['reason']}; PBO: {pbo['reason']}", metrics, dsr["missing"] + pbo["missing"])
    phi = statistics.fmean(_lag1(x) for x in data)
    metrics["mean_lag1_autocorrelation"] = phi
    if pbo["pbo"] >= pbo_fail and dsr["dsr"] >= dsr_pass:
        return result(check, INCONCLUSIVE, f"PBO {pbo['pbo']:.2f} but DSR {dsr['dsr']:.2f}: choosing a variant does not "
                      "carry out of sample, yet the best variant's level survives deflation", metrics)
    if pbo["pbo"] >= pbo_fail or dsr["dsr"] < dsr_fail:
        return result(check, FAIL, f"PBO {pbo['pbo']:.2f}, DSR {dsr['dsr']:.2f} with N = {n_tested}: the selection does "
                      "not carry out of sample", metrics)
    if phi > persistence_limit:
        return result(check, INCONCLUSIVE, f"lag-1 autocorrelation {phi:.2f} makes a low PBO uninformative "
                      "(PBO_PERSISTENCE_2026-10-21.md)", metrics)
    if pbo["pbo"] <= pbo_pass and dsr["dsr"] >= dsr_pass:
        return result(check, PASS, f"PBO {pbo['pbo']:.2f}, DSR {dsr['dsr']:.2f} with N = {n_tested}", metrics)
    return result(check, INCONCLUSIVE, f"PBO {pbo['pbo']:.2f}, DSR {dsr['dsr']:.2f}: between the limits", metrics)


def _lag1(x):
    z = _standardise(x)
    return 0.0 if z is None else sum(map(operator.mul, z[:-1], z[1:]))


def check_costs(gross_bps_per_trade=None, assumed_cost_bps=None, floor_cost_bps=None, reported_net_bps_per_trade=None,
                stress=2.0, net_tolerance_bps=0.5):
    """Are the costs realistic, and does the edge survive them? floor_cost_bps is the documented minimum round-trip cost
    (fees plus spread), the caller's evidence. Assumed below the floor is a FAIL; so is no edge after the floor."""
    check = COSTS
    missing = _names_absent(gross_bps_per_trade=gross_bps_per_trade, assumed_cost_bps=assumed_cost_bps,
                            floor_cost_bps=floor_cost_bps)
    if missing:
        return result(check, MISSING_INPUT, "costs cannot be judged without these; none is assumed", missing=missing)
    for k, v in (("gross_bps_per_trade", gross_bps_per_trade), ("assumed_cost_bps", assumed_cost_bps),
                 ("floor_cost_bps", floor_cost_bps)):
        if not _is_num(v):
            return result(check, MISSING_INPUT, f"{k} is not a number", missing=[k])
    gross, assumed, floor = gross_bps_per_trade, assumed_cost_bps, floor_cost_bps
    metrics = {"gross_bps": gross, "assumed_cost_bps": assumed, "floor_cost_bps": floor, "stress": stress,
               "net_at_floor_bps": gross - floor, "net_at_stress_bps": gross - stress * max(assumed, floor)}
    if assumed < floor:
        return result(check, FAIL, f"assumed cost {assumed} bps is below the documented floor of {floor} bps", metrics)
    if reported_net_bps_per_trade is not None:
        if not _is_num(reported_net_bps_per_trade):
            return result(check, MISSING_INPUT, "reported net is not a number", metrics, ["reported_net_bps_per_trade"])
        implied = gross - assumed
        metrics.update(reported_net_bps=reported_net_bps_per_trade, implied_net_bps=implied)
        if abs(reported_net_bps_per_trade - implied) > net_tolerance_bps:
            return result(check, FAIL, f"reported net {reported_net_bps_per_trade} bps does not equal gross minus the "
                          f"assumed cost ({implied} bps)", metrics)
    if gross - max(assumed, floor) <= 0:
        return result(check, FAIL, f"no net edge: {gross} bps gross against {max(assumed, floor)} bps cost", metrics)
    if gross - stress * max(assumed, floor) <= 0:
        return result(check, INCONCLUSIVE, f"the edge does not survive {stress:g} times the cost", metrics)
    return result(check, PASS, f"{gross - max(assumed, floor):.1f} bps net per trade, and positive at {stress:g} times the cost",
                  metrics)


def assess(checks, required=ALL_CHECKS):
    """Combine check results. The worst status present wins; a required check that did not run counts as MISSING_INPUT,
    so PASS means every required check ran and passed."""
    by_name = {c["check"]: c for c in checks}
    absent = [k for k in required if k not in by_name]
    statuses = [c["status"] for c in checks] + ([MISSING_INPUT] if absent else [])
    if not statuses:
        statuses = [MISSING_INPUT]
    overall = next(s for s in ORDER if s in statuses)
    reasons = [f"{c['check']}: {c['status']}: {c['reason']}" for c in checks if c["status"] != PASS]
    if absent:
        reasons.append("not run: " + ", ".join(absent))
    if overall == PASS:
        reasons = ["every required check ran and passed"]
    return {"status": overall, "reasons": reasons, "missing_checks": absent, "checks": by_name,
            "note": "a diagnostic; it decides nothing about a strategy"}


CHECKS = {MULTIPLE_TESTING: check_multiple_testing, CORRELATION: check_correlation, LOOKAHEAD: check_lookahead,
          SURVIVORSHIP: check_survivorship, MISSING_OBS: check_missing_observations, CONTAMINATION: check_contamination,
          OVERFITTING: check_overfitting, COSTS: check_costs}


def evaluate(spec, required=ALL_CHECKS):
    """spec: check name -> keyword arguments. Unknown names are refused; the rest is `assess`."""
    unknown = [k for k in spec if k not in CHECKS]
    if unknown:
        raise ValueError(f"unknown check(s) {unknown}")
    return assess([CHECKS[name](**kwargs) for name, kwargs in spec.items()], required)
