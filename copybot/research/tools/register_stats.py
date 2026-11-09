"""Director order 70 P1: optional statistics for the research register, and DSR / PBO that refuse to guess.

WHY A SEPARATE MODULE. factory.Ledger hashes every key of an entry, and registry.json is named by sha256 in registry.md.
A new key on an old row changes that row's hash and every hash after it; a re-dump of registry.json changes the pinned
digest. So nothing here touches factory.py, registry.json or a ledger row. Statistics live in side records keyed by the
register's id, with their own hash chain; `attach` joins the two read-only.

RULES (order 70):
- every field is optional, and an absent field stays absent: no default, no zero, no "normal returns" assumption;
- a measured value needs provenance (origin, hashed artifact, code commit). IMPUTED/ASSUMED is not an origin, so old
  experiments cannot be back-filled by assumption, and a return series cannot be reconstructed without documentation;
- DSR / PBO return status MISSING_INPUT (and no number) when an input is absent. This differs on purpose from
  lab.engine.backtest.deflated_sharpe, which defaults to skew 0 and kurtosis 3.

Formulas: DSR/PSR, Bailey & Lopez de Prado 2014 (JPM 40(5)); PBO by CSCV, Bailey, Borwein, Lopez de Prado & Zhu 2014,
delegated to lab.engine.pbo.cscv. Diagnostic only: this module decides nothing, opens no market data and writes no file.

    python3 research/tools/register_stats.py        # N table and synthetic null worlds as JSON
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import random
import re
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lab.engine import pbo as engine_pbo  # noqa: E402
from research.tools import factory  # noqa: E402

SCHEMA = "copybot.register_stats/1"
OK, MISSING_INPUT, INVALID_INPUT = "OK", "MISSING_INPUT", "INVALID_INPUT"

MEASURED = ("sharpe", "n_obs", "skew", "kurtosis", "net_returns", "net_returns_index", "variants_tested")
LABELS = ("variant_family", "lineage")
FIELDS = MEASURED + LABELS + ("variants_evidence", "provenance")
ORIGINS = ("RUN_OUTPUT", "DOCUMENTED_RECOMPUTE")

EULER_GAMMA = 0.5772156649          # same constant as video_triage.luck_bar and backtest.deflated_sharpe
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
NORMAL = statistics.NormalDist()

# The register's aggregate counts as given in director order 70 (registry.md: attempts, variants, lineages).
REGISTER_COUNTS = {"lineages": 43, "attempts": 206, "variants": 19438}


class StatsError(ValueError):
    pass


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _absent(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def _refuse(status, key, missing, reason):
    return {"status": status, key: None, "missing": list(missing), "reason": reason}


# ---------------------------------------------------------------- side records

def record(record_id, **fields):
    """A validated side record. A field passed as None is dropped: absent stays absent, nothing is defaulted."""
    rec = {"schema": SCHEMA, "record_id": record_id}
    rec.update({k: v for k, v in fields.items() if v is not None})
    errors = validate(rec)
    if errors:
        raise StatsError("; ".join(errors))
    return rec


def _check_series(e, rec):
    ret, idx = rec.get("net_returns"), rec.get("net_returns_index")
    if ret is not None:
        if not isinstance(ret, list) or not ret:
            e.append("net_returns must be a non-empty list")
        elif not all(v is None or _is_num(v) for v in ret):
            e.append("net_returns holds numbers, or None for a period with no observation (never NaN or infinity)")
        elif rec.get("n_obs") is not None and rec["n_obs"] != len(ret):
            e.append("n_obs differs from the length of net_returns")
    if idx is not None:
        if not isinstance(idx, list) or not idx or not (all(type(v) is int for v in idx) or
                                                        all(isinstance(v, str) for v in idx)):
            e.append("net_returns_index must be a list of ints or of strings")
        elif any(a >= b for a, b in zip(idx, idx[1:])):
            e.append("net_returns_index must be strictly increasing")
        elif isinstance(ret, list) and len(ret) != len(idx):
            e.append("net_returns and net_returns_index differ in length")
    if (ret is None) != (idx is None):
        e.append("net_returns and net_returns_index go together: a series without its time axis cannot be aligned")


def validate(rec):
    """List of errors (empty = valid)."""
    e = []
    if not isinstance(rec, dict):
        return ["a record must be a dict"]
    if rec.get("schema") != SCHEMA:
        e.append(f"schema must be {SCHEMA}")
    if not isinstance(rec.get("record_id"), str) or not rec["record_id"]:
        e.append("record_id must be a non-empty string")
    for k in rec:
        if k not in FIELDS and k not in ("schema", "record_id"):
            e.append(f"unknown field {k!r}")
    for k in FIELDS:
        if k in rec and rec[k] is None:
            e.append(f"{k}: leave a missing field out, do not store None")
    for k in ("sharpe", "skew", "kurtosis"):
        if rec.get(k) is not None and not _is_num(rec[k]):
            e.append(f"{k} must be a finite number")
    for k, low in (("n_obs", 2), ("variants_tested", 1)):
        v = rec.get(k)
        if v is not None and (type(v) is not int or v < low):
            e.append(f"{k} must be an integer >= {low}")
    if _is_num(rec.get("kurtosis")) and _is_num(rec.get("skew")) and rec["kurtosis"] < 1 + rec["skew"] ** 2 - 1e-9:
        e.append("kurtosis is Pearson kurtosis (normal = 3) and must be >= 1 + skew^2; excess kurtosis is not accepted")
    for k in LABELS:
        if rec.get(k) is not None and (not isinstance(rec[k], str) or not rec[k]):
            e.append(f"{k} must be a non-empty string")
    _check_series(e, rec)
    if any(rec.get(k) is not None for k in MEASURED):
        p = rec.get("provenance")
        if not isinstance(p, dict):
            e.append("a measured value needs provenance {origin, artifact, sha256, code_commit}")
        else:
            if p.get("origin") not in ORIGINS:
                e.append(f"provenance.origin must be one of {ORIGINS}: nothing imputed or assumed")
            if not isinstance(p.get("artifact"), str) or not p["artifact"]:
                e.append("provenance.artifact must name the source artifact")
            if not isinstance(p.get("sha256"), str) or not HEX64.match(p["sha256"]):
                e.append("provenance.sha256 must be 64 lowercase hex digits")
            if not isinstance(p.get("code_commit"), str) or not HEX_COMMIT.match(p["code_commit"]):
                e.append("provenance.code_commit must be a git commit")
    if rec.get("variants_tested") is not None:
        ev = rec.get("variants_evidence")
        if not isinstance(ev, dict) or not isinstance(ev.get("artifact"), str) or not ev["artifact"] or \
                not isinstance(ev.get("sha256"), str) or not HEX64.match(ev["sha256"]):
            e.append("variants_tested needs variants_evidence {artifact, sha256}")
    return e


def chain_append(chain, rec, ts):
    """Append a valid record to `chain` (a list, in memory; persisting it is the caller's). A correction is a new entry."""
    errors = validate(rec)
    if errors:
        raise StatsError("; ".join(errors))
    entry = {"seq": len(chain), "record_id": rec["record_id"], "ts": ts, "record": copy.deepcopy(rec),
             "prev": chain[-1]["hash"] if chain else "0" * 64}
    entry["hash"] = factory.sha(entry)
    chain.append(entry)
    return entry


def chain_verify(chain):
    prev = "0" * 64
    for i, entry in enumerate(chain):
        body = {k: v for k, v in entry.items() if k != "hash"}
        if entry["seq"] != i or entry["prev"] != prev or factory.sha(body) != entry["hash"] or validate(entry["record"]):
            raise StatsError(f"stats chain broken at entry {i}")
        prev = entry["hash"]
    return True


def attach(rows, chain=(), key="id"):
    """Read-only view: one item per register row with the row's own hash and its latest side record, or status
    MISSING_INPUT and stats None when there is none. Old rows are never changed and get nothing invented."""
    latest = {}
    for entry in chain:
        latest[entry["record_id"]] = entry["record"]
    out = []
    for row in rows:
        stats = latest.get(row.get(key))
        out.append({"record_id": row.get(key), "register_row_sha": factory.sha(row),
                    "status": OK if stats is not None else MISSING_INPUT,
                    "stats": copy.deepcopy(stats) if stats is not None else None})
    return out


# ---------------------------------------------------------------- expected maximum and effective N

def expected_max_z(n):
    """E[max of n iid standard normals], the Bailey & Lopez de Prado approximation (n may be a non-integer N_eff)."""
    if not _is_num(n) or n < 1:
        raise ValueError(f"N must be a number >= 1, got {n!r}")
    if n == 1:
        return 0.0
    z = (1 - EULER_GAMMA) * NORMAL.inv_cdf(1 - 1.0 / n) + EULER_GAMMA * NORMAL.inv_cdf(1 - 1.0 / (n * math.e))
    return max(0.0, z)                             # the approximation dips below zero for N just above 1


def expected_max_z_exact(n, a=-12.0, b=14.0, h=0.001):
    """The same expectation by Simpson quadrature of x * n * phi(x) * Phi(x)^(n-1), n an integer >= 1."""
    if type(n) is not int or n < 1:
        raise ValueError(f"N must be an integer >= 1, got {n!r}")
    if n == 1:
        return 0.0
    m = int((b - a) / h)
    m += m % 2
    step = (b - a) / m
    root2, ln_n, ln_2pi = math.sqrt(2), math.log(n), math.log(2 * math.pi)
    total = 0.0
    for i in range(m + 1):
        x = a + i * step
        weight = 1 if i in (0, m) else (4 if i % 2 else 2)
        log_cdf = math.log(0.5 * math.erfc(-x / root2)) if x < 0 else math.log1p(-0.5 * math.erfc(x / root2))
        total += weight * x * math.exp(ln_n - 0.5 * x * x - 0.5 * ln_2pi + (n - 1) * log_cdf)
    return total * step / 3


def flat_effective_n(mean_corr, n):
    """N_eff = rho + (1 - rho) N with one mean correlation over all pairs (Bailey & Lopez de Prado 2014). Shown for
    comparison: in clustered worlds it stays near N (see DSR_PBO_REGISTER_70.md)."""
    return mean_corr + (1 - mean_corr) * n


def block_effective_n(blocks):
    """N_eff = sum over blocks of rho_g + (1 - rho_g) n_g. blocks: (n_g, rho_g) per attempt, rho_g the mean pairwise
    correlation inside the block. Blocks are treated as independent. A block without a rho gives MISSING_INPUT."""
    if blocks is None or not len(blocks):
        return _refuse(MISSING_INPUT, "n_eff", ["blocks"], "no blocks given")
    gaps = [i for i, b in enumerate(blocks) if b is None or _absent(b[0]) or _absent(b[1])]
    if gaps:
        return _refuse(MISSING_INPUT, "n_eff", [f"blocks[{i}]" for i in gaps], "a block has no size or no correlation")
    total = 0.0
    for n, rho in blocks:
        if type(n) is not int or n < 1 or not _is_num(rho) or not -1 <= rho <= 1:
            return _refuse(INVALID_INPUT, "n_eff", [], f"bad block ({n!r}, {rho!r})")
        total += rho + (1 - rho) * n if n > 1 else 1.0
    return {"status": OK, "n_eff": total, "blocks": len(blocks), "missing": [], "reason": None}


def n_table(counts=None):
    """Expected max z for each way of counting N: the Bailey approximation (= luck_bar at T = 1) and the exact value."""
    counts = counts or REGISTER_COUNTS
    return {k: {"N": n, "expected_max_z": expected_max_z(n), "expected_max_z_exact": expected_max_z_exact(n)}
            for k, n in counts.items()}


def _sizes(total, k):
    base, extra = divmod(total, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


def synthetic_hierarchy(rho_attempt, rho_lineage=0.0, reps=2000, seed=70, counts=None):
    """SYNTHETIC null world: E[max z] over all variants, evenly split (lineages -> attempts -> variants). Independent
    across lineages; pairwise correlation rho_lineage between attempts of a lineage, rho_attempt inside an attempt
    (rho_attempt >= rho_lineage). The even split is an assumption of this world, not the register's real distribution."""
    if not 0 <= rho_lineage <= rho_attempt <= 1:
        raise ValueError("need 0 <= rho_lineage <= rho_attempt <= 1")
    c = counts or REGISTER_COUNTS
    per_lineage, per_attempt = _sizes(c["attempts"], c["lineages"]), _sizes(c["variants"], c["attempts"])
    rng = random.Random(seed)
    s_l, s_a, s_v = math.sqrt(rho_lineage), math.sqrt(rho_attempt - rho_lineage), math.sqrt(1 - rho_attempt)
    maxima = []
    for _ in range(reps):
        best, idx = -math.inf, 0
        for size in per_lineage:
            lineage = rng.gauss(0, 1)
            for _ in range(size):
                # the largest of n iid normals in one draw: its CDF value is U^(1/n)
                u = min((1 - rng.random()) ** (1.0 / per_attempt[idx]), 1 - 1e-16)
                idx += 1
                z = s_l * lineage + s_a * rng.gauss(0, 1) + (s_v * NORMAL.inv_cdf(u) if s_v else 0.0)
                best = max(best, z)
        maxima.append(best)
    return {"rho_attempt": rho_attempt, "rho_lineage": rho_lineage, "reps": reps, "seed": seed,
            "expected_max_z": statistics.fmean(maxima), "std_error": statistics.stdev(maxima) / math.sqrt(reps)}


def synthetic_mean_corr(rho_attempt, rho_lineage=0.0, counts=None):
    """Mean pairwise correlation over ALL variant pairs of that synthetic world (what a flat formula would be given)."""
    c = counts or REGISTER_COUNTS
    per_lineage, per_attempt = _sizes(c["attempts"], c["lineages"]), _sizes(c["variants"], c["attempts"])
    pairs = c["variants"] * (c["variants"] - 1)
    same_attempt = sum(n * (n - 1) for n in per_attempt)
    same_lineage, idx = 0, 0
    for size in per_lineage:
        group = per_attempt[idx:idx + size]
        idx += size
        same_lineage += sum(group) ** 2 - sum(n * n for n in group)
    return (rho_attempt * same_attempt + rho_lineage * same_lineage) / pairs


# ---------------------------------------------------------------- moments, DSR

def moments(net_returns):
    """Per-period Sharpe, n_obs, skew and Pearson kurtosis of a documented series (population moments, so that
    kurtosis >= 1 + skew^2 holds exactly). A gap is not filled: MISSING_INPUT."""
    if net_returns is None or not len(net_returns):
        return _refuse(MISSING_INPUT, "sharpe", ["net_returns"], "no series")
    gaps = [i for i, v in enumerate(net_returns) if _absent(v)]
    if gaps:
        return _refuse(MISSING_INPUT, "sharpe", [f"net_returns[{i}]" for i in gaps[:20]], "gaps are not filled")
    if not all(_is_num(v) for v in net_returns):
        return _refuse(INVALID_INPUT, "sharpe", [], "net_returns holds a non-number")
    if len(net_returns) < 3:
        return _refuse(MISSING_INPUT, "sharpe", ["net_returns"], "needs at least 3 observations")
    x = net_returns
    mean = math.fsum(x) / len(x)
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in x) / len(x))
    if sd <= 1e-15:
        return _refuse(INVALID_INPUT, "sharpe", [], "zero variance: the Sharpe ratio is undefined")
    return {"status": OK, "sharpe": mean / sd, "n_obs": len(x),
            "skew": math.fsum(((v - mean) / sd) ** 3 for v in x) / len(x),
            "kurtosis": math.fsum(((v - mean) / sd) ** 4 for v in x) / len(x), "missing": [], "reason": None}


def trial_sharpe_variance(sharpes):
    """Cross-sectional variance of per-period Sharpe ratios of the trials (population, as in backtest.deflated_sharpe)."""
    if sharpes is None or len(sharpes) < 2 or any(_absent(v) for v in sharpes):
        return _refuse(MISSING_INPUT, "sharpe_variance", ["sharpes"], "needs every trial's Sharpe, at least 2")
    if not all(_is_num(v) for v in sharpes):
        return _refuse(INVALID_INPUT, "sharpe_variance", [], "a trial's Sharpe is not a number")
    return {"status": OK, "sharpe_variance": statistics.pvariance(sharpes), "missing": [], "reason": None}


def deflated_sharpe(sharpe=None, n_obs=None, skew=None, kurtosis=None, n_trials=None, sharpe_variance=None):
    """Deflated Sharpe ratio. sharpe = per-period (not annualised), kurtosis = Pearson (normal = 3), n_trials = the
    number of independent trials (may be an N_eff), sharpe_variance = cross-sectional variance of the trials' per-period
    Sharpe (needed when n_trials > 1). With n_trials = 1 this is the PSR against zero. Nothing has a default."""
    needed = {"sharpe": sharpe, "n_obs": n_obs, "skew": skew, "kurtosis": kurtosis, "n_trials": n_trials}
    if _absent(n_trials) or not _is_num(n_trials) or n_trials > 1:
        needed["sharpe_variance"] = sharpe_variance
    missing = [k for k, v in needed.items() if _absent(v)]
    if missing:
        return _refuse(MISSING_INPUT, "dsr", missing, "DSR is not computed without its inputs")
    for k, v in needed.items():
        if not _is_num(v):
            return _refuse(INVALID_INPUT, "dsr", [], f"{k} is not a finite number")
    if type(n_obs) is not int or n_obs < 2:
        return _refuse(INVALID_INPUT, "dsr", [], "n_obs must be an integer >= 2")
    if n_trials < 1:
        return _refuse(INVALID_INPUT, "dsr", [], "n_trials must be >= 1")
    if kurtosis < 1 + skew ** 2 - 1e-9:
        return _refuse(INVALID_INPUT, "dsr", [], "kurtosis is Pearson (normal = 3) and must be >= 1 + skew^2")
    if n_trials > 1 and sharpe_variance <= 0:
        return _refuse(INVALID_INPUT, "dsr", [], "several trials with no Sharpe dispersion: sharpe_variance must be > 0")
    radicand = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe ** 2
    if radicand <= 0:
        return _refuse(INVALID_INPUT, "dsr", [], "the Sharpe standard error is not defined for these moments")
    sr0 = math.sqrt(sharpe_variance) * expected_max_z(n_trials) if n_trials > 1 else 0.0
    z = (sharpe - sr0) * math.sqrt(n_obs - 1) / math.sqrt(radicand)
    return {"status": OK, "dsr": NORMAL.cdf(z), "sr0": sr0, "z": z, "n_trials": n_trials, "missing": [], "reason": None,
            "method": "Bailey and Lopez de Prado 2014; diagnostic only"}


def deflated_sharpe_from_record(rec, n_trials=None, sharpe_variance=None):
    """DSR from a side record. Reads only what the record states; a missing record is MISSING_INPUT."""
    if rec is None:
        return deflated_sharpe(n_trials=n_trials, sharpe_variance=sharpe_variance)
    errors = validate(rec)
    if errors:
        return _refuse(INVALID_INPUT, "dsr", [], "; ".join(errors))
    return deflated_sharpe(rec.get("sharpe"), rec.get("n_obs"), rec.get("skew"), rec.get("kurtosis"),
                           n_trials, sharpe_variance)


# ---------------------------------------------------------------- PBO

def pbo_cscv(series=None, time_index=None, s=16):
    """PBO by CSCV (lab.engine.pbo.cscv) of N net-return series on one shared time axis. No gap is filled and no axis
    is assumed: an absent series, a gap, an unaligned series or too few periods gives MISSING_INPUT."""
    missing = [k for k, v in (("series", series), ("time_index", time_index)) if _absent(v)]
    if missing:
        return _refuse(MISSING_INPUT, "pbo", missing, "PBO is not computed without its inputs")
    if len(series) < 2:
        return _refuse(MISSING_INPUT, "pbo", ["series"], "CSCV needs at least 2 configurations")
    if type(s) is not int or s < 2 or s % 2:
        return _refuse(INVALID_INPUT, "pbo", [], "S must be an even integer >= 2")
    if any(a >= b for a, b in zip(time_index, time_index[1:])):
        return _refuse(INVALID_INPUT, "pbo", [], "time_index must be strictly increasing")
    for i, x in enumerate(series):
        if _absent(x):
            return _refuse(MISSING_INPUT, "pbo", [f"series[{i}]"], "a configuration has no series")
        if len(x) != len(time_index):
            return _refuse(MISSING_INPUT, "pbo", [f"series[{i}]"], "not on the common time axis")
        gaps = [j for j, v in enumerate(x) if _absent(v)]
        if gaps:
            return _refuse(MISSING_INPUT, "pbo", [f"series[{i}][{j}]" for j in gaps[:20]], "gaps are not filled")
        if not all(_is_num(v) for v in x):
            return _refuse(INVALID_INPUT, "pbo", [], f"series[{i}] holds a non-number")
    if len(time_index) < 2 * s:
        return _refuse(MISSING_INPUT, "pbo", ["time_index"], f"{len(time_index)} periods is too few for S = {s}")
    return {"status": OK, **engine_pbo.cscv([list(x) for x in series], s=s), "missing": [], "reason": None}


def pbo_from_records(records, s=16):
    """PBO from side records. Every record must carry its own series and the identical time axis."""
    if not records:
        return _refuse(MISSING_INPUT, "pbo", ["records"], "no records")
    for rec in records:
        errors = validate(rec)
        if errors:
            return _refuse(INVALID_INPUT, "pbo", [], f"{rec.get('record_id')}: " + "; ".join(errors))
    without = [r["record_id"] for r in records if r.get("net_returns") is None]
    if without:
        return _refuse(MISSING_INPUT, "pbo", [f"{k}.net_returns" for k in without], "no documented series")
    axis = records[0]["net_returns_index"]
    differ = [r["record_id"] for r in records if r["net_returns_index"] != axis]
    if differ:
        return _refuse(MISSING_INPUT, "pbo", [f"{k}.net_returns_index" for k in differ], "not on the common time axis")
    return pbo_cscv([r["net_returns"] for r in records], axis, s=s)


# ---------------------------------------------------------------- report

SCENARIOS = ((0.0, 0.0), (0.5, 0.0), (0.9, 0.0), (0.99, 0.0), (1.0, 0.0), (0.9, 0.5), (0.99, 0.5), (1.0, 1.0))


def _scenario(rho_attempt, rho_lineage, reps):
    sim = synthetic_hierarchy(rho_attempt, rho_lineage, reps=reps)
    c = REGISTER_COUNTS
    n_flat = flat_effective_n(synthetic_mean_corr(rho_attempt, rho_lineage), c["variants"])
    blocks = [(n, rho_attempt) for n in _sizes(c["variants"], c["attempts"])]
    n_block = block_effective_n(blocks)["n_eff"]
    return {**sim, "flat_n_eff": n_flat, "flat_z": expected_max_z(n_flat),
            "block_n_eff": n_block, "block_z": expected_max_z(n_block)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=6000)
    a = ap.parse_args(argv)
    print(json.dumps({"n_table": n_table(),
                      "synthetic": [_scenario(ra, rl, a.reps) for ra, rl in SCENARIOS]}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
