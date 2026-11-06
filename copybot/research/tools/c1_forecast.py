"""Director order 51 P1: C1, an isolated, observation-only forward volatility FORECAST JOURNAL (infrastructure only).

Design (Danish): research/desk/C1_FORECAST_DESIGN.md. Stream entry: research/desk/stream_registry.json
`fwd_vol_forecast_register` (PROPOSED_NEEDS_SEPARATE_APPROVAL). C1 records forecasts; it never decides anything.

What this module may do today: synthetic data, synthetic forecasts, synthetic reveals, synthetic QLIKE/DM, and a
COUNTS-ONLY coverage report on census/1 (read-only lab.db, rows from 2026-10-27 only). It has no code path that writes a
real forecast: a journal is synthetic unless constructed with an explicit activation reference, and no CLI command
constructs one. It computes no return, RV level, model fit or loss on real data (director order 51: own forward
observations may be read for data quality only). It imports no network module and does not touch the Polymarket LP job or any collector.

Relation to F2 (research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md, CONDITIONAL, locked, unchanged): the model,
benchmark, loss and test below are the F2 ones (HAR-RV 1/7/30 with OLS on the preceding 365 days, EWMA lambda 0.94 on
the same RV series, QLIKE, d = L(EWMA) - L(HAR), one-sided Diebold-Mariano with Newey-West 5 lags on the equal-weight
cross-sectional daily mean of d). C1 is the forward recording infrastructure for that model pair. Nothing here is a
test of F2; any confirmatory use of C1 forecasts needs its own approved, locked protocol.

Definitions (all fixed in DEFAULT_CONFIG and hashed into every journal entry):
- slot: UTC hour [h, h+3600). The mark of slot h is the first census row with ts in [h, h+3600) (census_check
  convention); its price field (default markPrice) must be finite and > 0, otherwise the slot is missing. Never filled.
- day D: [D + day_offset_s, D + day_offset_s + 86400), default offset 0 = the UTC day. A day is COMPLETE when all 24
  slot marks are present. RV_D = sum over k=1..23 of ln(P_k / P_{k-1})^2, i.e. the 23 hourly log returns between the
  24 marks inside the day. The boundary return (last mark of D-1 -> first mark of D) belongs to no day: it is the
  embargo that lets a forecast be created strictly after its input cutoff and strictly before its target starts.
  An incomplete day has no RV (never interpolated, never rescaled).
- HAR-RV(1,7,30): RV_{t+1} = b0 + b1 RV_t + b7 mean(RV_{t-6..t}) + b30 mean(RV_{t-29..t}) + e, OLS. Estimation window:
  the est_window_days (365) regression rows whose target day lies in [L-364, L] for the last input day L; a row needs
  its target and all 30 lag days complete; the fit needs min_rows (365) usable rows, i.e. 395 consecutive complete
  days [L-394, L]. Forecast for day L+1 = b . (1, RV_L, mean7_L, mean30_L).
- EWMA(0.94): s_first = RV_first; s_t = lambda s_{t-1} + (1-lambda) RV_t; forecast for L+1 = s_L. The recursion runs
  over the contiguous run of complete days ending at L (a missing day restarts it), truncated to max_window_days (395,
  HAR's input span). Burn-in: the seed weight lambda^(n-1) must be <= 0.05, so n >= 50 complete days.
- QLIKE(RV, F) = RV/F - ln(RV/F) - 1 (Patton 2011), RV > 0 and F > 0 required (else the pair is refused).
- DM: d_{i,t} = QLIKE(RV, F_EWMA) - QLIKE(RV, F_HAR); dbar_t = equal-weight mean over symbols with both forecasts
  revealed; t = mean(dbar) / sqrt(LRV / T), LRV Newey-West with Bartlett weights 1 - k/(L+1), L = 5 fixed lags,
  autocovariances divided by T (same convention as hypo_engine.hac_t); p one-sided = 1 - Phi(t), H0 E[d] <= 0.

Journal (JSONL, append-only, hash-chained): see Journal. Fail-closed rules are listed in Journal.append_forecast,
Journal.append_reveal and evaluate.

    python3 research/tools/c1_forecast.py selftest
    python3 research/tools/c1_forecast.py synthetic --out DIR [--seed N]
    python3 research/tools/c1_forecast.py coverage [--db PATH] [--out research/data/c1] [--now EPOCH]
    python3 research/tools/c1_forecast.py verify JOURNAL
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time

VERSION = "c1_forecast/1"
HOUR, DAY = 3600, 86400
FORWARD_START_TS = calendar.timegm((2026, 10, 27, 0, 0, 0))     # own forward rows only; nothing earlier is ever read
SYN_START = 2_000_000_000                                       # 2033-05-18, as forward_obs: never a real period
SYN_DAY0 = SYN_START - SYN_START % DAY + DAY                    # first synthetic UTC midnight
GENESIS_PREV = "0" * 64
MODELS = {"har_rv_1_7_30": "har_rv_1_7_30/1", "ewma_094": "ewma_094/1"}
BENCHMARK, CANDIDATE = "ewma_094", "har_rv_1_7_30"
DEFAULT_PROD_DB = "/home/anton/ecommerence/copybot/data/lab/lab.db"

DEFAULT_CONFIG = {
    "version": "c1_config/1",
    "rule": "director order 51 P1; research/desk/C1_FORECAST_DESIGN.md; F2 (FACTORY_P2_PROTOCOLS_2026-11-06) unchanged",
    "source": {"table": "observations", "detector": "census/1", "metric": "snapshot", "price_field": "markPrice"},
    "slot_s": HOUR,
    "slot_rule": "mark of slot h = first row with ts in [h, h+3600); price finite and > 0; never filled",
    "day_offset_s": 0,
    "marks_per_day": 24,
    "rv_rule": "RV_D = sum of the 23 squared log returns between the 24 marks of a complete day; boundary return "
               "excluded (embargo); incomplete day -> no RV",
    "horizon_days": 1,
    "har": {"lags_days": [1, 7, 30], "est_window_days": 365, "min_rows": 365,
            "rule": "OLS on rows with target day in [L-364, L]; row needs target and 30 lag days complete"},
    "ewma": {"lambda": 0.94, "max_seed_weight": 0.05, "gap_policy": "restart", "max_window_days": 395},
    "min_coverage": 1.0,
    "settlement_lag_s": HOUR,
    "max_clock_skew_s": 60,
    "loss": "qlike: RV/F - ln(RV/F) - 1",
    "dm": {"d": "L(ewma_094) - L(har_rv_1_7_30)", "cross_section": "equal-weight daily mean", "nw_lags": 5,
           "kernel": "bartlett 1-k/(L+1)", "h0": "E[d] <= 0", "side": "one-sided", "min_days": 7},
}


class C1Error(Exception):
    """Base class: every refusal is an exception, nothing is silently dropped."""


class ForecastRefused(C1Error):
    pass


class RevealRefused(C1Error):
    pass


class EvaluationRefused(C1Error):
    pass


class JournalCorrupt(C1Error):
    pass


class ModelRefused(C1Error):
    pass


# ---------------------------------------------------------------------------------------------------------- hashing
def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def sha256_hex(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def config_sha256(cfg):
    return sha256_hex(cfg)


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_hex64(s):
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)


# ---------------------------------------------------------------------------------------------------------- marks, RV
def day_start(ts, cfg=DEFAULT_CONFIG):
    off = cfg["day_offset_s"]
    return int((ts - off) // DAY * DAY + off)


def to_slots(marks, cfg=DEFAULT_CONFIG):
    """marks: iterable of (ts, price) in arrival order. Returns {slot: (ts, price)}; the first row of a slot counts,
    an invalid price leaves the slot missing (a later row in the same slot does not replace a first invalid one)."""
    out, seen = {}, set()
    for ts, price in marks:
        s = int(ts - ts % cfg["slot_s"])
        if s in seen:
            continue
        seen.add(s)
        if _finite(price) and price > 0:
            out[s] = (ts, float(price))
    return out


def day_slots(day, cfg=DEFAULT_CONFIG):
    return [day + k * cfg["slot_s"] for k in range(cfg["marks_per_day"])]


def day_rv(slots, day, cfg=DEFAULT_CONFIG):
    """(rv or None, present count, last mark ts or None)."""
    ss = day_slots(day, cfg)
    got = [slots.get(s) for s in ss]
    present = sum(1 for g in got if g)
    if present < len(ss):
        return None, present, None
    rv = math.fsum(math.log(got[k][1] / got[k - 1][1]) ** 2 for k in range(1, len(got)))
    return rv, present, got[-1][0]


def rv_series(slots, first_day, last_day, cfg=DEFAULT_CONFIG, cache=None):
    """{day: rv or None} for every day in [first_day, last_day]. cache: optional {day: rv} memo for one symbol (the
    marks of a past day never change once read; the caller owns the memo)."""
    out = {}
    for d in range(first_day, last_day + 1, DAY):
        if cache is not None and d in cache:
            out[d] = cache[d]
            continue
        out[d] = day_rv(slots, d, cfg)[0]
        if cache is not None:
            cache[d] = out[d]
    return out


def span_identity(slots, symbol, first_day, last_day, cfg=DEFAULT_CONFIG):
    """sha256 of the exact marks in [first_day, last_day], coverage and the last mark ts. Preimage (UTF-8):
    'c1-input/1|<symbol>|<price_field>|<first_day>|<last_day>' then one line per present slot in slot order
    '<slot>,<repr(ts)>,<repr(price)>', lines joined by '\n'."""
    req = [s for d in range(first_day, last_day + 1, DAY) for s in day_slots(d, cfg)]
    lines = ["c1-input/1|%s|%s|%d|%d" % (symbol, cfg["source"]["price_field"], first_day, last_day)]
    cutoff, n = None, 0
    for s in req:
        m = slots.get(s)
        if m is None:
            continue
        n += 1
        lines.append("%d,%r,%r" % (s, float(m[0]), m[1]))
        cutoff = m[0] if cutoff is None or m[0] > cutoff else cutoff
    ident = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    return ident, (n / len(req) if req else 0.0), cutoff


# ---------------------------------------------------------------------------------------------------------- models
def _features(rv, t):
    d1 = [rv.get(t)]
    d7 = [rv.get(t - k * DAY) for k in range(7)]
    d30 = [rv.get(t - k * DAY) for k in range(30)]
    if any(v is None for v in d30):
        return None
    return [1.0, d1[0], math.fsum(d7) / 7, math.fsum(d30) / 30]


def solve(a, b):
    """Gauss-Jordan with partial pivoting; refuses a singular system."""
    n = len(b)
    m = [list(map(float, a[i])) + [float(b[i])] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            raise ModelRefused("singular normal equations")
        m[c], m[p] = m[p], m[c]
        piv = m[c][c]
        m[c] = [v / piv for v in m[c]]
        for r in range(n):
            if r != c and m[r][c] != 0.0:
                f = m[r][c]
                m[r] = [vr - f * vc for vr, vc in zip(m[r], m[c])]
    return [m[i][n] for i in range(n)]


def ols(X, y):
    k = len(X[0])
    xtx = [[math.fsum(row[i] * row[j] for row in X) for j in range(k)] for i in range(k)]
    xty = [math.fsum(row[i] * yy for row, yy in zip(X, y)) for i in range(k)]
    return solve(xtx, xty)


def har_fit(rv, last_day, cfg=DEFAULT_CONFIG):
    """Rows with target day in [L-W+1, L]; returns (coefs [b0, b1, b7, b30], rows used). Fit on data scaled by the
    mean target (numerics only; predictions are scale-equivariant, b0 is unscaled afterwards)."""
    w, need = cfg["har"]["est_window_days"], cfg["har"]["min_rows"]
    X, y = [], []
    for k in range(w):
        tgt = last_day - k * DAY
        f = _features(rv, tgt - DAY)
        if f is None or rv.get(tgt) is None:
            continue
        X.append(f)
        y.append(rv[tgt])
    if len(y) < need:
        raise ModelRefused("har: %d usable rows < min_rows %d" % (len(y), need))
    c = math.fsum(y) / len(y)
    if not c > 0:
        raise ModelRefused("har: non-positive mean target")
    b = ols([[1.0] + [v / c for v in r[1:]] for r in X], [v / c for v in y])
    return [b[0] * c, b[1], b[2], b[3]], len(y)


def har_input_span(last_day, cfg=DEFAULT_CONFIG):
    return last_day - (cfg["har"]["est_window_days"] + 29) * DAY, last_day


def har_forecast(rv, last_day, cfg=DEFAULT_CONFIG):
    coefs, n = har_fit(rv, last_day, cfg)
    f = _features(rv, last_day)
    if f is None:
        raise ModelRefused("har: lag days of the forecast origin incomplete")
    value = math.fsum(b * x for b, x in zip(coefs, f))
    return value, {"coefs": coefs, "rows": n}


def ewma_burn_in(cfg=DEFAULT_CONFIG):
    lam, w = cfg["ewma"]["lambda"], cfg["ewma"]["max_seed_weight"]
    n = 1
    while lam ** (n - 1) > w:
        n += 1
    return n


def ewma_forecast(rv, last_day, cfg=DEFAULT_CONFIG):
    lam, maxw = cfg["ewma"]["lambda"], cfg["ewma"]["max_window_days"]
    run = []
    d = last_day
    while rv.get(d) is not None and len(run) < maxw:
        run.append(rv[d])
        d -= DAY
    run.reverse()
    n = len(run)
    if n < ewma_burn_in(cfg):
        raise ModelRefused("ewma: complete run %d < burn-in %d" % (n, ewma_burn_in(cfg)))
    s = run[0]
    for v in run[1:]:
        s = lam * s + (1 - lam) * v
    return s, {"run_days": n, "seed_weight": lam ** (n - 1)}


def ewma_input_span(last_day, cfg=DEFAULT_CONFIG):
    return last_day - (ewma_burn_in(cfg) - 1) * DAY, last_day


def build_forecast(model, symbol, slots, last_day, cfg=DEFAULT_CONFIG, rv_cache=None):
    """A forecast record for day last_day + 1 (without created_ts; the journal stamps it). Raises ModelRefused."""
    if model == CANDIDATE:
        lo, hi = har_input_span(last_day, cfg)
        fn = har_forecast
    elif model == BENCHMARK:
        lo, hi = ewma_input_span(last_day, cfg)
        fn = ewma_forecast
    else:
        raise ModelRefused("unknown model %r" % model)
    data_lo = min(lo, last_day - (cfg["ewma"]["max_window_days"] - 1) * DAY)
    rv = rv_series(slots, data_lo, hi, cfg, rv_cache)
    value, info = fn(rv, last_day, cfg)
    if model == BENCHMARK:                       # identity covers the run actually used
        lo = last_day - (info["run_days"] - 1) * DAY
    ident, cov, cutoff = span_identity(slots, symbol, lo, hi, cfg)
    ts0 = last_day + DAY
    return {"model": model, "model_version": MODELS[model], "symbol": symbol, "horizon_days": cfg["horizon_days"],
            "input_first_day": lo, "input_last_day": hi, "input_cutoff_ts": cutoff, "input_sha256": ident,
            "coverage": cov, "target_start": ts0, "target_end": ts0 + cfg["horizon_days"] * DAY, "value": value,
            "fit": info}


def realized(slots, symbol, target_start, cfg=DEFAULT_CONFIG):
    """(status, rv or None, identity sha, coverage) for the target day."""
    rv, _, _ = day_rv(slots, target_start, cfg)
    ident, cov, _ = span_identity(slots, symbol, target_start, target_start, cfg)
    if rv is None or cov < cfg["min_coverage"] or not rv > 0:
        return "void", None, ident, cov
    return "ok", rv, ident, cov


# ---------------------------------------------------------------------------------------------------------- loss, DM
def qlike(rv, f):
    if not (_finite(rv) and _finite(f) and rv > 0 and f > 0):
        raise EvaluationRefused("qlike needs RV > 0 and F > 0 (rv=%r, f=%r)" % (rv, f))
    q = rv / f
    return q - math.log(q) - 1


def hac_t(x, lags):
    """Newey-West t statistic of the mean: Bartlett weights 1 - k/(lags+1), autocovariances / n (hypo_engine.hac_t
    convention)."""
    n = len(x)
    m = math.fsum(x) / n
    d = [v - m for v in x]
    s = math.fsum(v * v for v in d) / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * math.fsum(d[t] * d[t - k] for t in range(k, n)) / n
    se = math.sqrt(max(s, 1e-300) / n)
    return m / se, m, se


def p_one(t):
    return 0.5 * math.erfc(t / math.sqrt(2))


def dm_test(daily_d, lags):
    t, m, se = hac_t(daily_d, lags)
    return {"T": len(daily_d), "mean_d": m, "se_hac": se, "dm_t": t, "p_one": p_one(t), "nw_lags": lags}


# ---------------------------------------------------------------------------------------------------------- journal
FORECAST_KEYS = ("kind", "seq", "prev_hash", "model", "model_version", "config_sha256", "symbol", "horizon_days",
                 "input_first_day", "input_last_day", "input_cutoff_ts", "input_sha256", "coverage", "created_ts",
                 "target_start", "target_end", "value", "earliest_eval_ts", "fit")
REVEAL_KEYS = ("kind", "seq", "prev_hash", "forecast_hash", "symbol", "model", "target_start", "target_end",
               "status", "realized", "realized_sha256", "realized_coverage", "revealed_ts", "config_sha256")
GENESIS_KEYS = ("kind", "seq", "prev_hash", "journal_version", "config", "config_sha256", "created_ts", "synthetic",
                "activation_ref")


def entry_hash(entry):
    return sha256_hex({k: v for k, v in entry.items() if k != "entry_hash"})


class Journal:
    """Append-only, hash-chained JSONL. Every line: {..., seq, prev_hash, entry_hash}; entry_hash = sha256 over the
    canonical JSON of the line without entry_hash; prev_hash = the previous line's entry_hash (genesis: 64 zeros).
    Line 0 is a genesis entry binding the config (sha256) and the synthetic flag. There is no edit, delete or
    rewrite method; the file is only ever opened in append mode. `<path>.head` holds the last seq and hash (an anchor
    against tail truncation; commit it elsewhere for an external anchor). Every read re-verifies the whole chain and
    re-checks every rule, and any failure raises JournalCorrupt (fail-closed)."""

    def __init__(self, path, cfg=DEFAULT_CONFIG, clock=time.time, synthetic=True, activation_ref=None):
        if not synthetic and not activation_ref:
            raise ForecastRefused("a non-synthetic journal needs an activation reference (separate approval)")
        self.path, self.cfg, self.clock = path, cfg, clock
        self.cfg_sha = config_sha256(cfg)
        self.synthetic = synthetic
        entries = self.entries()
        if not entries:
            g = {"kind": "genesis", "seq": 0, "prev_hash": GENESIS_PREV, "journal_version": VERSION, "config": cfg,
                 "config_sha256": self.cfg_sha, "created_ts": self._now(), "synthetic": synthetic,
                 "activation_ref": activation_ref}
            self._write(g)
        else:
            g = entries[0]
            if g["config_sha256"] != self.cfg_sha or g["synthetic"] != synthetic:
                raise JournalCorrupt("journal genesis does not match this config / synthetic flag")

    # --- low level
    def _now(self):
        now = self.clock()
        if self.synthetic and now < SYN_DAY0:
            raise ForecastRefused("synthetic journal clock before the synthetic epoch")
        if not self.synthetic and now >= SYN_START:
            raise ForecastRefused("real journal clock inside the synthetic epoch")
        return now

    def _write(self, entry):
        entry["entry_hash"] = entry_hash(entry)
        line = canonical(entry).decode() + "\n"
        before = self.entries()                       # verified state the new line is appended to
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        tmp = self.path + ".head.tmp"
        head = json.dumps({"seq": entry["seq"], "entry_hash": entry["entry_hash"]})
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(head)
        os.replace(tmp, self.path + ".head")
        expected = (self._cache[0][0] if self._cache else b"") + line.encode()
        self._cache = ((expected, head.encode()), before + [entry])
        return entry

    def entries(self):
        """Full verification whenever the file (or its head) differs byte for byte from what this instance last
        verified or wrote itself; otherwise the cached, already verified entries."""
        try:
            with open(self.path, "rb") as fh:
                data = fh.read()
        except FileNotFoundError:
            data = b""
        head = b""
        if os.path.exists(self.path + ".head"):
            with open(self.path + ".head", "rb") as fh:
                head = fh.read()
        cache = getattr(self, "_cache", None)
        if cache and cache[0] == (data, head):
            return list(cache[1])
        es = verify_file(self.path)
        self._cache = ((data, head), es)
        return list(es)

    # --- appends
    def append_forecast(self, rec, created_ts=None):
        """Refused (ForecastRefused) if: model/version unknown; created_ts (wall clock at append) differs from a
        caller-supplied created_ts by more than max_clock_skew_s (backdating or future-dating); created_ts earlier than
        the last entry (the journal's time never runs backwards); created_ts >= target_start; input_cutoff_ts >
        created_ts; input_cutoff_ts > target_start; coverage < min_coverage; value not finite and > 0; target window
        not one aligned day of the configured horizon; a forecast for the same (model, symbol, target_start) already
        exists (never re-issued); or the chain does not verify."""
        cfg = self.cfg
        entries = self.entries()
        now = self._now()
        if created_ts is not None and abs(created_ts - now) > cfg["max_clock_skew_s"]:
            raise ForecastRefused("created_ts %r is not the wall clock %r (backdated/future-dated)" % (created_ts, now))
        created = now
        last = entries[-1]
        last_ts = last.get("created_ts", last.get("revealed_ts"))
        if created < last_ts:
            raise ForecastRefused("created_ts before the last journal entry")
        m = rec.get("model")
        if m not in MODELS or rec.get("model_version") != MODELS[m]:
            raise ForecastRefused("unknown model/version")
        ts0, ts1, cut = rec.get("target_start"), rec.get("target_end"), rec.get("input_cutoff_ts")
        if not all(_finite(v) for v in (ts0, ts1, cut)):
            raise ForecastRefused("target window / input cutoff missing")
        if created >= ts0:
            raise ForecastRefused("created at/after target start (created %r >= %r)" % (created, ts0))
        if cut > created:
            raise ForecastRefused("input cutoff after creation")
        if cut > ts0:
            raise ForecastRefused("input cutoff after target start")
        if ts1 - ts0 != cfg["horizon_days"] * DAY or day_start(ts0, cfg) != ts0 or rec.get("horizon_days") != \
                cfg["horizon_days"]:
            raise ForecastRefused("target window is not one aligned day of the configured horizon")
        if not (_finite(rec.get("coverage")) and rec["coverage"] >= cfg["min_coverage"]):
            raise ForecastRefused("coverage %r < min_coverage %r" % (rec.get("coverage"), cfg["min_coverage"]))
        if not (_finite(rec.get("value")) and rec["value"] > 0):
            raise ForecastRefused("forecast value must be finite and > 0")
        if not _is_hex64(rec.get("input_sha256")):
            raise ForecastRefused("input identity missing")
        if rec.get("input_last_day") is None or rec["input_last_day"] + DAY > ts0:
            raise ForecastRefused("input days overlap the target")
        for e in entries:
            if e["kind"] == "forecast" and (e["model"], e["symbol"], e["target_start"]) == (m, rec["symbol"], ts0):
                raise ForecastRefused("forecast already issued for this model/symbol/target (no re-issue)")
        entry = {"kind": "forecast", "seq": last["seq"] + 1, "prev_hash": last["entry_hash"], "model": m,
                 "model_version": MODELS[m], "config_sha256": self.cfg_sha, "symbol": rec["symbol"],
                 "horizon_days": rec["horizon_days"], "input_first_day": rec["input_first_day"],
                 "input_last_day": rec["input_last_day"], "input_cutoff_ts": cut, "input_sha256": rec["input_sha256"],
                 "coverage": rec["coverage"], "created_ts": created, "target_start": ts0, "target_end": ts1,
                 "value": rec["value"], "earliest_eval_ts": ts1 + cfg["settlement_lag_s"],
                 "fit": rec.get("fit", {})}
        return self._write(entry)

    def append_reveal(self, forecast_hash, status, realized_value, realized_sha256, realized_coverage):
        """Refused (RevealRefused) if: the forecast does not exist; it already has a reveal (once only); wall clock <
        earliest_eval_ts; status 'ok' without a finite RV > 0 at full coverage; status 'void' with a value; or the
        chain does not verify. 'void' = the target day is incomplete: the forecast is closed but never scored."""
        entries = self.entries()
        now = self._now()
        fc = [e for e in entries if e["kind"] == "forecast" and e["entry_hash"] == forecast_hash]
        if not fc:
            raise RevealRefused("no such forecast")
        fc = fc[0]
        if any(e["kind"] == "reveal" and e["forecast_hash"] == forecast_hash for e in entries):
            raise RevealRefused("forecast already revealed (once only)")
        if now < fc["earliest_eval_ts"]:
            raise RevealRefused("reveal before earliest evaluation ts (%r < %r)" % (now, fc["earliest_eval_ts"]))
        last = entries[-1]
        if now < last.get("created_ts", last.get("revealed_ts")):
            raise RevealRefused("journal time would run backwards")
        if status == "ok":
            if not (_finite(realized_value) and realized_value > 0 and _finite(realized_coverage)
                    and realized_coverage >= self.cfg["min_coverage"]):
                raise RevealRefused("ok reveal needs RV > 0 at full coverage")
        elif status == "void":
            if realized_value is not None:
                raise RevealRefused("void reveal carries no value")
        else:
            raise RevealRefused("status must be ok or void")
        if not _is_hex64(realized_sha256):
            raise RevealRefused("realized identity missing")
        entry = {"kind": "reveal", "seq": last["seq"] + 1, "prev_hash": last["entry_hash"],
                 "forecast_hash": forecast_hash, "symbol": fc["symbol"], "model": fc["model"],
                 "target_start": fc["target_start"], "target_end": fc["target_end"], "status": status,
                 "realized": realized_value, "realized_sha256": realized_sha256,
                 "realized_coverage": realized_coverage, "revealed_ts": now, "config_sha256": self.cfg_sha}
        return self._write(entry)


def _check_entry_rules(e, cfg, prior):
    """Re-check the append rules on read (defense in depth against a rewritten-and-rehashed file)."""
    if e["kind"] == "forecast":
        if not (e["created_ts"] < e["target_start"] and e["input_cutoff_ts"] <= e["created_ts"]
                and e["input_cutoff_ts"] <= e["target_start"] and e["coverage"] >= cfg["min_coverage"]
                and e["value"] > 0 and e["earliest_eval_ts"] == e["target_end"] + cfg["settlement_lag_s"]):
            raise JournalCorrupt("seq %d: forecast violates a journal rule" % e["seq"])
    elif e["kind"] == "reveal":
        fc = prior.get(e["forecast_hash"])
        if fc is None or fc.get("_revealed"):
            raise JournalCorrupt("seq %d: reveal without forecast or second reveal" % e["seq"])
        if e["revealed_ts"] < fc["earliest_eval_ts"]:
            raise JournalCorrupt("seq %d: early reveal" % e["seq"])
        fc["_revealed"] = True


def verify_file(path):
    """Full chain verification; returns the entries (without private marks). Empty/missing file -> []."""
    if not os.path.exists(path):
        return []
    out, prior, cfg, cfg_sha = [], {}, None, None
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    else:
        if lines:
            raise JournalCorrupt("last line not terminated (partial write)")
    prev, last_ts = GENESIS_PREV, -math.inf
    for i, line in enumerate(lines):
        try:
            e = json.loads(line)
        except ValueError:
            raise JournalCorrupt("line %d is not JSON" % i)
        keys = {"genesis": GENESIS_KEYS, "forecast": FORECAST_KEYS, "reveal": REVEAL_KEYS}.get(e.get("kind"))
        if keys is None or set(e) != set(keys) | {"entry_hash"}:
            raise JournalCorrupt("line %d: unknown kind or field set" % i)
        if e["seq"] != i or e["prev_hash"] != prev or e["entry_hash"] != entry_hash(e):
            raise JournalCorrupt("line %d: chain broken (seq/prev_hash/entry_hash)" % i)
        if (i == 0) != (e["kind"] == "genesis"):
            raise JournalCorrupt("line %d: genesis must be line 0 only" % i)
        if i == 0:
            cfg, cfg_sha = e["config"], e["config_sha256"]
            if config_sha256(cfg) != cfg_sha:
                raise JournalCorrupt("genesis config hash mismatch")
        elif e["config_sha256"] != cfg_sha:
            raise JournalCorrupt("line %d: config hash differs from genesis" % i)
        ts = e.get("created_ts", e.get("revealed_ts"))
        if ts < last_ts:
            raise JournalCorrupt("line %d: journal time runs backwards" % i)
        last_ts = ts
        _check_entry_rules(e, cfg, prior)
        if e["kind"] == "forecast":
            prior[e["entry_hash"]] = dict(e)
        prev = e["entry_hash"]
        out.append(e)
    head = path + ".head"
    if out and os.path.exists(head):
        with open(head, encoding="utf-8") as fh:
            h = json.load(fh)
        if h.get("seq") != out[-1]["seq"] or h.get("entry_hash") != out[-1]["entry_hash"]:
            raise JournalCorrupt("head anchor does not match the last entry (truncated or extended)")
    return out


# ---------------------------------------------------------------------------------------------------------- evaluation
def evaluate(entries, cfg=DEFAULT_CONFIG, now=None, require_all_due=True):
    """QLIKE per (symbol, target) for the pair (EWMA, HAR) and the DM/HAC test on the equal-weight daily mean of d.
    Refused (EvaluationRefused) if: any forecast due at `now` (earliest_eval_ts <= now) has no reveal; any evaluated
    forecast was not created strictly before its target window or has a cutoff after creation; the two reveals of a
    pair disagree on the realized value or its identity; or fewer than dm.min_days days remain. Only 'ok' reveals
    of pairs with both models are scored; void and unpaired forecasts are counted, never scored."""
    fcs = {e["entry_hash"]: e for e in entries if e["kind"] == "forecast"}
    rev = {e["forecast_hash"]: e for e in entries if e["kind"] == "reveal"}
    if now is None:
        now = max((e.get("created_ts", e.get("revealed_ts")) for e in entries), default=0)
    counts = {"forecasts": len(fcs), "due": 0, "revealed_ok": 0, "revealed_void": 0, "unpaired": 0}
    pairs = {}
    for h, f in fcs.items():
        if f["created_ts"] >= f["target_start"] or f["input_cutoff_ts"] > f["created_ts"]:
            raise EvaluationRefused("forecast %s was not created before its target window" % h[:12])
        if f["earliest_eval_ts"] > now:
            continue
        counts["due"] += 1
        r = rev.get(h)
        if r is None:
            if require_all_due:
                raise EvaluationRefused("forecast %s is due but has no reveal" % h[:12])
            continue
        if r["status"] != "ok":
            counts["revealed_void"] += 1
            continue
        counts["revealed_ok"] += 1
        pairs.setdefault((f["symbol"], f["target_start"]), {})[f["model"]] = (f, r)
    by_day = {}
    for (sym, ts0), p in sorted(pairs.items()):
        if set(p) != {BENCHMARK, CANDIDATE}:
            counts["unpaired"] += len(p)
            continue
        (fb, rb), (fc_, rc) = p[BENCHMARK], p[CANDIDATE]
        if rb["realized"] != rc["realized"] or rb["realized_sha256"] != rc["realized_sha256"]:
            raise EvaluationRefused("reveals of %s %d disagree" % (sym, ts0))
        d = qlike(rb["realized"], fb["value"]) - qlike(rc["realized"], fc_["value"])
        by_day.setdefault(ts0, []).append(d)
    days = sorted(by_day)
    daily = [math.fsum(by_day[t]) / len(by_day[t]) for t in days]
    if len(daily) < cfg["dm"]["min_days"]:
        raise EvaluationRefused("%d scored days < dm.min_days %d" % (len(daily), cfg["dm"]["min_days"]))
    res = dm_test(daily, cfg["dm"]["nw_lags"])
    res.update({"counts": counts, "days": len(days), "coin_days": sum(len(v) for v in by_day.values()),
                "first_day": days[0], "last_day": days[-1],
                "share_days_har_better": sum(1 for v in daily if v > 0) / len(daily)})
    return res


# ---------------------------------------------------------------------------------------------------------- synthetic
SYN_HAR = (1.35e-4, 0.35, 0.30, 0.20)          # b0, b1, b7, b30: persistent, stationary (sum of slopes 0.85)


def synth_marks(symbols=("SYNA", "SYNB", "SYNC"), n_days=60, seed=51, coefs=SYN_HAR, regime=False, start=SYN_DAY0,
                jitter_s=(5, 40), drop_slots=()):
    """Deterministic hourly marks per symbol: within day t the 23 hourly log returns (and the boundary return) are
    N(0, v_t / 23), v_t from the HAR recursion on past realized RVs. Mark ts = slot + jitter. drop_slots: (symbol,
    slot) pairs left out (to test coverage). Returns ({symbol: [(ts, price), ...]}, {symbol: {day: v_t}})."""
    rng = random.Random(seed)
    b0, b1, b7, b30 = coefs
    mean = b0 / (1 - b1 - b7 - b30)
    drop = set(drop_slots)
    marks, truth = {}, {}
    for sym in symbols:
        price, rvs, out, tv = 100.0, [], [], {}
        state = 0
        for i in range(n_days):
            if regime and rng.random() < 0.02:
                state = 1 - state
            mult = 3.0 if state else 1.0
            if len(rvs) >= 30:
                v = b0 * mult + b1 * rvs[-1] + b7 * math.fsum(rvs[-7:]) / 7 + b30 * math.fsum(rvs[-30:]) / 30
            else:
                v = mean * mult
            d = start + i * DAY
            tv[d] = v
            sd = math.sqrt(v / 23)
            rv = 0.0
            for k in range(24):
                r = rng.gauss(0.0, sd)
                price *= math.exp(r)
                if k > 0:
                    rv += r * r
                slot = d + k * HOUR
                if (sym, slot) not in drop:
                    out.append((slot + rng.uniform(*jitter_s), price))
            rvs.append(rv)
        marks[sym], truth[sym] = out, tv
    return marks, truth


class SimClock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def synthetic_run(out_dir, seed=51, symbols=("SYNA", "SYNB", "SYNC", "SYND"), eval_days=90, cfg=DEFAULT_CONFIG,
                  regime=True):
    """End to end on synthetic data: marks -> each evening (23:30 of input day L) reveal what is due, then freeze both
    forecasts for L+1 -> after the last target, reveal the rest -> evaluate. Writes only into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    span = cfg["har"]["est_window_days"] + 30
    n_days = span + eval_days + 1
    marks, _ = synth_marks(symbols, n_days, seed, regime=regime)
    slots = {s: to_slots(m, cfg) for s, m in marks.items()}
    clock = SimClock(SYN_DAY0)
    jpath = os.path.join(out_dir, "c1_synthetic_journal.jsonl")
    for p in (jpath, jpath + ".head"):
        if os.path.exists(p):
            os.remove(p)
    j = Journal(jpath, cfg, clock=clock, synthetic=True)
    refused = {"model": 0, "forecast": 0}
    memo = {sym: {} for sym in symbols}

    def reveal_due():
        es = j.entries()
        done = {x["forecast_hash"] for x in es if x["kind"] == "reveal"}
        for e in es:
            if e["kind"] != "forecast" or e["earliest_eval_ts"] > clock.t or e["entry_hash"] in done:
                continue
            st, val, ident, cov = realized(slots[e["symbol"]], e["symbol"], e["target_start"], cfg)
            j.append_reveal(e["entry_hash"], st, val, ident, cov)

    for i in range(span - 1, span - 1 + eval_days):
        last_day = SYN_DAY0 + i * DAY
        clock.t = last_day + 23 * HOUR + 1800
        reveal_due()
        for sym in symbols:
            for model in (BENCHMARK, CANDIDATE):
                try:
                    rec = build_forecast(model, sym, slots[sym], last_day, cfg, memo[sym])
                except ModelRefused:
                    refused["model"] += 1
                    continue
                try:
                    j.append_forecast(rec)
                except ForecastRefused:
                    refused["forecast"] += 1
    clock.t = SYN_DAY0 + (span - 1 + eval_days + 1) * DAY + cfg["settlement_lag_s"]
    reveal_due()
    entries = j.entries()
    res = evaluate(entries, cfg, now=clock.t)
    report = {"version": VERSION, "synthetic": True, "seed": seed, "symbols": list(symbols), "eval_days": eval_days,
              "config_sha256": config_sha256(cfg), "journal": os.path.basename(jpath),
              "journal_entries": len(entries), "journal_head": entries[-1]["entry_hash"], "refused": refused,
              "evaluation": res,
              "note": "synthetic only (timestamps from 2033); says nothing about real markets or about F2"}
    with open(os.path.join(out_dir, "c1_synthetic_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, sort_keys=True, indent=1)
    return report


# ---------------------------------------------------------------------------------------------------------- coverage
def open_ro(db_path):
    import sqlite3
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def _iso(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)) if ts is not None else None


def _date(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts is not None else None


def _ranges(slots_missing):
    out = []
    for s in sorted(slots_missing):
        if out and s == out[-1][1] + HOUR:
            out[-1][1] = s
        else:
            out.append([s, s])
    return [{"from": _iso(a), "to": _iso(b), "slots": (b - a) // HOUR + 1} for a, b in out]


def census_presence(con, since=FORWARD_START_TS, fields=("markPrice", "lastPrice")):
    """COUNTS ONLY. Returns per-snapshot-slot meta and, per symbol and field, the set of slots with a valid
    (finite, > 0) value. No price, return or RV leaves this function."""
    if since < FORWARD_START_TS:
        raise C1Error("C1 never reads rows before 2026-10-27")
    det = DEFAULT_CONFIG["source"]["detector"]
    rows_total, dup, errors, first_ts = 0, 0, 0, {}
    present = {f: {} for f in fields}
    seen = set()
    metrics = {}
    for metric, n in con.execute("SELECT metric, count(*) FROM observations WHERE detector=? AND ts>=? GROUP BY "
                                 "metric", (det, since)):
        metrics[metric] = n
    lag = []
    for ts, payload in con.execute("SELECT ts, payload FROM observations WHERE detector=? AND metric='snapshot' AND "
                                   "ts>=? ORDER BY ts, id", (det, since)):
        rows_total += 1
        s = ts - ts % HOUR
        if s in seen:
            dup += 1
            continue
        seen.add(s)
        first_ts[s] = ts
        p = json.loads(payload)
        cols = p["columns"]
        pt = p.get("premium_time_ms")
        if _finite(pt):
            lag.append(ts - pt / 1000.0)
        idx = {f: cols.index(f) for f in fields if f in cols}
        for sym, row in p["rows"].items():
            for f, j in idx.items():
                v = row[j] if j < len(row) else None
                if _finite(v) and v > 0:
                    present[f].setdefault(sym, set()).add(s)
        p = None
    errors = metrics.get("error", 0)
    return {"metrics": metrics, "rows": rows_total, "duplicate_rows": dup, "error_rows": errors,
            "snapshot_slots": sorted(seen), "first_ts": first_ts, "present": present,
            "offset_s": {"min": min(first_ts[s] - s for s in seen) if seen else None,
                         "max": max(first_ts[s] - s for s in seen) if seen else None,
                         "median": statistics.median([first_ts[s] - s for s in seen]) if seen else None},
            "row_minus_premium_time_s": {"min": min(lag) if lag else None, "max": max(lag) if lag else None}}


def symbol_days(slot_set, first_day, last_full_day, today, now_slot, cfg=DEFAULT_CONFIG):
    """Complete-day bookkeeping for one symbol (counts only). today: the day containing now; it is 'pending' if every
    slot up to now_slot is present."""
    complete, incomplete = [], []
    for d in range(first_day, last_full_day + 1, DAY):
        (complete if all(s in slot_set for s in day_slots(d, cfg)) else incomplete).append(d)
    today_ok = all(s in slot_set for s in day_slots(today, cfg) if s <= now_slot)
    run_end = last_full_day
    run = 0
    d = last_full_day
    cset = set(complete)
    while d >= first_day and d in cset:
        run += 1
        d -= DAY
    run_start = d + DAY if run else (last_full_day + DAY)
    if not today_ok:
        run, run_start = 0, today + DAY            # today already broken: a new run starts tomorrow
    return {"complete": complete, "incomplete": incomplete, "today_ok": today_ok, "run_days": run,
            "run_start": run_start, "run_end": run_end if run else None}


def first_valid_dates(run_start, cfg=DEFAULT_CONFIG):
    """Assuming no gaps from now on: the first target day each model can be issued for, and when it is created."""
    har_days = cfg["har"]["est_window_days"] + 30
    ew = ewma_burn_in(cfg)
    out = {}
    for name, need in (("har_rv_1_7_30", har_days), ("ewma_094", ew)):
        last_in = run_start + (need - 1) * DAY
        out[name] = {"complete_days_needed": need, "first_input_day": _date(run_start),
                     "last_input_day": _date(last_in), "first_target_day": _date(last_in + DAY),
                     "creation_window_utc": "after the 23:00 mark of %s, before %s 00:00" % (
                         _date(last_in), _date(last_in + DAY)),
                     "first_reveal_utc": _iso(last_in + 2 * DAY + cfg["settlement_lag_s"])}
    return out


def coverage_report(db_path, now=None, cfg=DEFAULT_CONFIG, focus=("BTCUSDT", "ETHUSDT")):
    now = int(time.time() if now is None else now)
    con = open_ro(db_path)
    try:
        cp = census_presence(con)
    finally:
        con.close()
    snaps = cp["snapshot_slots"]
    if not snaps:
        raise C1Error("no census/1 snapshots since 2026-10-27")
    first_slot, last_slot = snaps[0], snaps[-1]
    # the last slot whose row should exist by now (rows land ~20 s after the hour; 5 min grace)
    now_slot = now - now % HOUR - (HOUR if now % HOUR < 300 else 0)
    expected = list(range(first_slot, max(last_slot, now_slot) + HOUR, HOUR))
    snapset = set(snaps)
    missing = [s for s in expected if s not in snapset]
    today = day_start(now, cfg)
    first_full = day_start(first_slot, cfg) + (DAY if first_slot != day_start(first_slot, cfg) else 0)
    last_full_day = today - DAY
    global_set = set(snaps)
    glob = symbol_days(global_set, first_full, last_full_day, today, now_slot, cfg)
    per_field = {}
    for field, pres in cp["present"].items():
        stats = []
        focus_out = {}
        for sym, ss in pres.items():
            fs = min(ss)
            fd = day_start(fs, cfg) + (DAY if fs != day_start(fs, cfg) else 0)
            sd = symbol_days(ss, max(fd, first_full), last_full_day, today, now_slot, cfg)
            exp_sym = [s for s in expected if s >= fs]
            row = {"symbol": sym, "first_slot": fs, "slots_expected": len(exp_sym),
                   "slots_present": sum(1 for s in exp_sym if s in ss), "complete_days": len(sd["complete"]),
                   "run_days": sd["run_days"], "run_start": sd["run_start"], "today_ok": sd["today_ok"]}
            stats.append(row)
            if sym in focus:
                miss = [s for s in exp_sym if s not in ss]
                focus_out[sym] = {
                    "first_seen": _iso(fs), "slots_expected": len(exp_sym), "slots_present": row["slots_present"],
                    "coverage": row["slots_present"] / len(exp_sym), "missing_slot_ranges": _ranges(miss),
                    "complete_days": [_date(d) for d in sd["complete"]],
                    "incomplete_days": [_date(d) for d in sd["incomplete"]],
                    "current_complete_run_days": sd["run_days"],
                    "current_run_start": _date(sd["run_start"]), "today_so_far_complete": sd["today_ok"],
                    "first_valid": first_valid_dates(sd["run_start"], cfg)}
        cdays = [r["complete_days"] for r in stats]
        runs = [r["run_days"] for r in stats]
        starts = collections_counter(_date(r["run_start"]) for r in stats)
        cov = [r["slots_present"] / r["slots_expected"] for r in stats if r["slots_expected"]]
        per_field[field] = {
            "symbols": len(stats),
            "symbols_first_seen_after_start": sum(1 for r in stats if r["first_slot"] > first_slot),
            "slot_coverage": {"min": min(cov), "median": statistics.median(cov), "max": max(cov),
                              "symbols_100pct": sum(1 for c in cov if c == 1.0)},
            "complete_days": {"min": min(cdays), "median": statistics.median(cdays), "max": max(cdays)},
            "current_run_days": {"min": min(runs), "median": statistics.median(runs), "max": max(runs)},
            "current_run_start_counts": dict(sorted(starts.items())),
            "symbols_more_missing_than_global": sum(1 for r in stats if r["slots_present"] <
                                                    sum(1 for s in snaps if s >= r["first_slot"])),
            "focus": focus_out}
    global_run_start = glob["run_start"]
    return {
        "version": VERSION, "generated_utc": _iso(now), "config_sha256": config_sha256(cfg),
        "source": {"db": "file:%s?mode=ro + PRAGMA query_only=ON" % db_path, "table": "observations",
                   "detector": "census/1", "metric": "snapshot", "fields_checked": list(cp["present"]),
                   "price_field_for_c1": cfg["source"]["price_field"], "rows_since": _iso(FORWARD_START_TS),
                   "metrics_rows": cp["metrics"], "what_was_read": "slot presence and validity (finite > 0) only; "
                   "no price level, return, RV, fit or loss was computed or written"},
        "snapshots": {"first_slot": _iso(first_slot), "last_slot": _iso(last_slot), "expected_slots": len(expected),
                      "present_slots": len(snaps), "missing_slots": len(missing),
                      "coverage": len(snaps) / len(expected), "duplicate_rows": cp["duplicate_rows"],
                      "error_rows": cp["error_rows"], "missing_ranges": _ranges(missing),
                      "row_ts_minus_slot_s": cp["offset_s"],
                      "row_ts_minus_premium_time_s": cp["row_minus_premium_time_s"]},
        "days": {"first_full_day": _date(first_full), "last_full_day": _date(last_full_day),
                 "full_days_elapsed": (last_full_day - first_full) // DAY + 1,
                 "complete_days_all_snapshots": [_date(d) for d in glob["complete"]],
                 "incomplete_days": [_date(d) for d in glob["incomplete"]],
                 "today": _date(today), "today_so_far_complete": glob["today_ok"],
                 "current_complete_run_days": glob["run_days"], "current_run_start": _date(global_run_start)},
        "rule": {"complete_day": "24 of 24 slot marks present (UTC hours 00..23)", "rv_returns_per_day": 23,
                 "har_complete_days_needed": cfg["har"]["est_window_days"] + 30,
                 "har_estimation_window": "%d regression rows (target days), each needing 30 lag days; min_rows %d"
                                          % (cfg["har"]["est_window_days"], cfg["har"]["min_rows"]),
                 "ewma_burn_in_days": ewma_burn_in(cfg),
                 "ewma_burn_in_rule": "seed = first RV of the run; lambda^(n-1) <= %.2f" % cfg["ewma"][
                     "max_seed_weight"]},
        "first_valid_if_no_more_gaps": first_valid_dates(global_run_start, cfg),
        "fields": per_field,
        "power_note": power_note(),
    }


def collections_counter(it):
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


def power_note():
    """Hypothetical power only (no data): p2_power.dm_power for forward evaluation windows, F2 universe size 20,
    alpha_F 0.0125 (amendment 8 programme budget as cited in the F2 header)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import p2_power
    rows = []
    for days in (90, 180, 365):
        for e in (0.05, 0.10):
            p, ne = p2_power.dm_power(e, 20, days, 0.5, 0.0125, 1.5)
            rows.append({"eval_days": days, "coins": 20, "rho_c": 0.5, "alpha": 0.0125, "e": e,
                         "power": round(p, 3), "n_eff": round(ne, 1)})
    return {"rule": "p2_power.dm_power(e, coins, days, rho_c, alpha, hac=1.5); e = E[d]/sd(d) per coin-day is "
                    "UNKNOWN; purely arithmetic, no data", "rows": rows}


def coverage_md(rep):
    s, d, fv = rep["snapshots"], rep["days"], rep["first_valid_if_no_more_gaps"]
    lines = ["# C1 dækningsrapport (census/1, kun optællinger)", "",
             "Genereret %s UTC af `research/tools/c1_forecast.py coverage`. Kilde: `%s`, tabel `observations`, "
             "detector `census/1`, metric `snapshot`, felt `markPrice` (og `lastPrice` til sammenligning). "
             "Kun rækker fra 2026-10-27. Ingen pris, afkast, RV, modeltilpasning eller tab er beregnet."
             % (rep["generated_utc"], rep["source"]["db"]), "",
             "## Snapshots (timeslots)", "",
             "| | |", "|---|---|",
             "| første slot | %s |" % s["first_slot"], "| sidste slot | %s |" % s["last_slot"],
             "| forventede / tilstede / mangler | %d / %d / %d (%.1f %%) |" % (
                 s["expected_slots"], s["present_slots"], s["missing_slots"], 100 * s["coverage"]),
             "| dubletter / fejlrækker | %d / %d |" % (s["duplicate_rows"], s["error_rows"]),
             "| række-ts minus slot (s) | min %s, median %s, max %s |" % (
                 s["row_ts_minus_slot_s"]["min"], s["row_ts_minus_slot_s"]["median"], s["row_ts_minus_slot_s"]["max"]),
             "", "Manglende slots:", ""]
    for r in s["missing_ranges"]:
        lines.append("- %s → %s (%d)" % (r["from"], r["to"], r["slots"]))
    lines += ["", "## Hele UTC-døgn (24/24 marks)", "",
              "- fulde døgn siden start: %d (%s .. %s)" % (d["full_days_elapsed"], d["first_full_day"],
                                                          d["last_full_day"]),
              "- komplette døgn: %d: %s" % (len(d["complete_days_all_snapshots"]),
                                           ", ".join(d["complete_days_all_snapshots"]) or "-"),
              "- ufuldstændige døgn: %s" % (", ".join(d["incomplete_days"]) or "-"),
              "- i dag (%s) indtil nu komplet: %s" % (d["today"], d["today_so_far_complete"]),
              "- nuværende sammenhængende løb: %d døgn fra %s" % (d["current_complete_run_days"],
                                                                 d["current_run_start"]), "",
              "## Pr. symbol", ""]
    for field, f in rep["fields"].items():
        lines += ["### %s" % field, "",
                  "- symboler: %d (heraf %d først set efter start)" % (f["symbols"],
                                                                     f["symbols_first_seen_after_start"]),
                  "- slotdækning: min %.3f, median %.3f, max %.3f; 100 %%: %d symboler" % (
                      f["slot_coverage"]["min"], f["slot_coverage"]["median"], f["slot_coverage"]["max"],
                      f["slot_coverage"]["symbols_100pct"]),
                  "- komplette døgn pr. symbol: min %d, median %s, max %d" % (
                      f["complete_days"]["min"], f["complete_days"]["median"], f["complete_days"]["max"]),
                  "- nuværende løb (døgn): min %d, median %s, max %d" % (
                      f["current_run_days"]["min"], f["current_run_days"]["median"], f["current_run_days"]["max"]),
                  "- symboler med flere manglende slots end snapshot-hullerne: %d" % f[
                      "symbols_more_missing_than_global"],
                  "- løbsstart pr. dato (antal symboler): %s" % ", ".join(
                      "%s: %d" % kv for kv in f["current_run_start_counts"].items()), ""]
        for sym, x in f["focus"].items():
            lines.append("- **%s**: %d/%d slots (%.1f %%), komplette døgn %d, løb %d fra %s; HAR første måldøgn %s, "
                         "EWMA første måldøgn %s" % (sym, x["slots_present"], x["slots_expected"],
                                                     100 * x["coverage"], len(x["complete_days"]),
                                                     x["current_complete_run_days"], x["current_run_start"],
                                                     x["first_valid"]["har_rv_1_7_30"]["first_target_day"],
                                                     x["first_valid"]["ewma_094"]["first_target_day"]))
        lines.append("")
    h, e = fv["har_rv_1_7_30"], fv["ewma_094"]
    lines += ["## Første gyldige prognose (hvis indsamlingen fortsætter uden huller)", "",
              "| model | komplette døgn krævet | inputdøgn | første måldøgn | oprettes | første afsløring |",
              "|---|---|---|---|---|---|",
              "| HAR-RV(1,7,30), 365 rækker | %d | %s .. %s | **%s** | %s | %s |" % (
                  h["complete_days_needed"], h["first_input_day"], h["last_input_day"], h["first_target_day"],
                  h["creation_window_utc"], h["first_reveal_utc"]),
              "| EWMA 0,94, indkøring %d | %d | %s .. %s | **%s** | %s | %s |" % (
                  e["complete_days_needed"], e["complete_days_needed"], e["first_input_day"], e["last_input_day"],
                  e["first_target_day"], e["creation_window_utc"], e["first_reveal_utc"]),
              "", "Ethvert nyt manglende timeslot genstarter løbet: datoerne flyttes til (hullets døgn + 1) + "
              "395 / 50 døgn.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------- CLI
def selftest():
    import tempfile
    d = tempfile.mkdtemp(prefix="c1_selftest_")
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["har"].update(est_window_days=60, min_rows=60)
    rep = synthetic_run(d, eval_days=20, cfg=cfg, symbols=("SYNA", "SYNB"))
    print(json.dumps({"dir": d, "dm_t": rep["evaluation"]["dm_t"], "days": rep["evaluation"]["days"]}))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    s = sub.add_parser("synthetic")
    s.add_argument("--out", required=True)
    s.add_argument("--seed", type=int, default=51)
    s.add_argument("--eval-days", type=int, default=90)
    c = sub.add_parser("coverage")
    c.add_argument("--db", default=DEFAULT_PROD_DB)
    c.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                 "data", "c1"))
    c.add_argument("--now", type=int, default=None)
    v = sub.add_parser("verify")
    v.add_argument("journal")
    a = ap.parse_args(argv)
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "synthetic":
        rep = synthetic_run(a.out, seed=a.seed, eval_days=a.eval_days)
        print(json.dumps(rep["evaluation"], indent=1))
        return 0
    if a.cmd == "coverage":
        rep = coverage_report(a.db, now=a.now)
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "coverage.json"), "w", encoding="utf-8") as fh:
            json.dump(rep, fh, sort_keys=True, indent=1)
        with open(os.path.join(a.out, "coverage.md"), "w", encoding="utf-8") as fh:
            fh.write(coverage_md(rep))
        print(json.dumps({"snapshots": rep["snapshots"]["coverage"], "days": rep["days"],
                          "first_valid": rep["first_valid_if_no_more_gaps"]}, indent=1))
        return 0
    if a.cmd == "verify":
        es = verify_file(a.journal)
        print(json.dumps({"entries": len(es), "head": es[-1]["entry_hash"] if es else None}))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
