"""Director order 50 P1: the forward data observatory's quality model. SYNTHETIC-ONLY library.

Pure functions over in-memory records (lists of dicts) plus a deterministic synthetic collector simulator that injects
known faults. It opens no database, reads no market file, imports no network module and writes nothing unless
`write_report` is called with an explicit path. Plan: research/desk/FORWARD_DATA_PLAN.md; the same rules as JSON:
research/desk/data_quality_schema.json (a test keeps that file equal to SCHEMA below).

Record kinds (field `kind`): book (top of book), funding (settled funding), basis (spot/perp pair, derived),
universe (one row per symbol per metadata snapshot), forecast (frozen before its target window) and outcome.
Every record has `stream`, `ts` (collection time, epoch seconds UTC) and, except forecast/outcome, `venue`, `symbol`.

Rules (all explicit; nothing is ever filled in, interpolated or silently dropped):
- required fields and types per kind; a number must be finite; bool is not a number;
- timestamps must not go backwards per key (stream, kind, venue, symbol) in arrival order -> out_of_order (dropped;
  forecast and outcome records are keyed by their target window instead and are exempt);
- same key and ts: identical content -> duplicate, different content -> conflicting_duplicate (both dropped; the
  first record of a key/ts stays);
- staleness: venue quote time older than max_quote_age_s (default: half the cadence) -> stale (dropped); without a venue
  time, an unchanged quote for >= repeat_n samples -> stale_suspected (kept, warning);
- gaps: between consecutive valid samples, and from the active window's start/end, a distance > (gap_factor +
  gap_jitter_factor) x cadence is listed with its start, end and missing slot count (the 10 % jitter allowance keeps
  collector timing jitter from deciding whether one lost sample is a gap; every lost slot is still counted in
  coverage); slots are never filled;
- coverage per key: expected slots in the key's active window (listing..delisting from the universe stream), valid,
  dropped (records arrived but were rejected) and missing (nothing arrived) counted separately;
- cross-field: bid <= ask (bid == ask is "locked", a warning), prices > 0, funding interval in the allowed set and
  consecutive funding times one interval apart, basis only from spot and perp read within basis_tol_s of each other;
- point in time universe: a symbol first seen at t cannot be in a universe dated before t; a symbol live at t
  (first seen <= t, not yet delisted) missing from a universe dated t is a survivorship omission;
- forecasts: issued strictly before target_start, hash over the canonical fields, the first issue per
  (model, symbol, target_start) is the frozen one and any later issue is a revision (never scored).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys

VERSION = "forward_obs/1"

# ---------------------------------------------------------------------------------------------------------- schema
SCHEMA = {
    "version": VERSION,
    "rule": "director order 50 P1; research/desk/FORWARD_DATA_PLAN.md",
    "types": {"number": "int or float, finite, not bool", "int": "int, not bool", "str": "non-empty str",
              "bool": "bool", "number|null": "number or null", "int|null": "int or null", "str|null": "str or null"},
    "common_required": {"kind": "str", "stream": "str", "ts": "number"},
    "kinds": {
        "book": {"required": {"venue": "str", "symbol": "str", "market": "str", "bid": "number", "ask": "number",
                              "bid_qty": "number", "ask_qty": "number"},
                 "optional": {"quote_ts": "number|null"},
                 "checks": ["bid > 0 and ask > 0", "bid_qty >= 0 and ask_qty >= 0", "bid <= ask (bid == ask: locked)",
                            "ts - quote_ts <= max_quote_age_s", "repeat_n unchanged quotes without quote_ts: suspected"],
                 "market_values": ["perp", "spot"]},
        "funding": {"required": {"venue": "str", "symbol": "str", "rate": "number", "interval_h": "int",
                                 "funding_time": "int"},
                    "optional": {"mark": "number|null"},
                    "checks": ["interval_h in allowed_funding_intervals_h",
                               "funding_time[i] - funding_time[i-1] == interval_h * 3600 per symbol",
                               "|rate| <= max_abs_funding_rate"]},
        "basis": {"required": {"venue": "str", "symbol": "str", "spot_ts": "number", "perp_ts": "number",
                               "spot_mid": "number", "perp_mid": "number", "basis": "number"},
                  "checks": ["|spot_ts - perp_ts| <= basis_tol_s", "basis == perp_mid / spot_mid - 1 (1e-9)"]},
        "universe": {"required": {"venue": "str", "symbol": "str", "status": "str"},
                     "optional": {"onboard_ts": "int|null", "contract_type": "str|null", "tick_size": "number|null"},
                     "checks": ["versions from consecutive snapshots: listed, delisted, relisted, spec_changed",
                                "first_seen(symbol) <= as_of for every universe dated as_of"]},
        "forecast": {"required": {"model_id": "str", "symbol": "str", "issued_ts": "number",
                                  "target_start": "number", "target_end": "number", "value": "number", "hash": "str"},
                     "checks": ["issued_ts < target_start", "target_start < target_end", "hash == forecast_hash()",
                                "first issue per (model_id, symbol, target_start) is frozen; later ones are revisions"]},
        "outcome": {"required": {"symbol": "str", "target_start": "number", "target_end": "number",
                                 "realized": "number"},
                    "checks": ["ts >= target_end"]},
    },
    "defaults": {"gap_factor": 2.0, "gap_jitter_factor": 0.1, "max_quote_age_factor": 0.5, "repeat_n": 5, "basis_tol_s": 5.0,
                 "allowed_funding_intervals_h": [1, 2, 4, 8], "max_abs_funding_rate": 0.03,
                 "trading_status": ["TRADING"]},
    "coverage": {"expected": "slots of the cadence inside the key's active window [max(start, listed), "
                             "min(end, delisted))",
                 "valid": "slots with >= 1 accepted record", "dropped": "slots with records, all rejected",
                 "missing": "slots with no record at all", "coverage_pct": "100 * valid / expected"},
    "errors": ["invalid", "out_of_order", "duplicate", "conflicting_duplicate", "crossed", "stale",
               "bad_funding_interval", "funding_step_mismatch", "funding_rate_out_of_range", "basis_time_mismatch",
               "basis_recompute_mismatch", "gaps", "pit_violations", "survivorship_omissions", "lookahead",
               "revised", "tampered", "outcome_early"],
    "warnings": ["locked", "stale_suspected", "unpaired_basis", "missing_outcome"],
    "info": ["listings", "delistings", "relistings", "spec_changes"],
}
DEFAULTS = SCHEMA["defaults"]
KEY_KINDS = ("book", "funding", "basis", "universe")


# ---------------------------------------------------------------------------------------------------------- types
def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def type_ok(value, spec):
    if spec.endswith("|null"):
        return value is None or type_ok(value, spec[:-5])
    if spec == "number":
        return _is_number(value)
    if spec == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if spec == "str":
        return isinstance(value, str) and value != ""
    if spec == "bool":
        return isinstance(value, bool)
    raise ValueError(f"unknown type {spec}")


def validate_record(rec):
    """Schema problems of one record: [] when it is well-formed."""
    if not isinstance(rec, dict):
        return ["not a dict"]
    out = []
    for f, t in SCHEMA["common_required"].items():
        if f not in rec:
            out.append(f"missing {f}")
        elif not type_ok(rec[f], t):
            out.append(f"bad type {f}")
    kind = rec.get("kind")
    spec = SCHEMA["kinds"].get(kind)
    if spec is None:
        return out + [f"unknown kind {kind!r}"]
    for f, t in spec["required"].items():
        if f not in rec:
            out.append(f"missing {f}")
        elif not type_ok(rec[f], t):
            out.append(f"bad type {f}")
    for f, t in spec.get("optional", {}).items():
        if f in rec and not type_ok(rec[f], t):
            out.append(f"bad type {f}")
    if kind == "book" and rec.get("market") not in (None, *spec["market_values"]) and "missing market" not in out:
        out.append("bad value market")
    return out


def key_of(rec):
    if rec.get("kind") in ("forecast", "outcome"):
        return (rec.get("stream"), rec.get("kind"), rec.get("model_id", ""), rec.get("symbol"))
    if rec.get("kind") == "book":           # spot and perp books of one symbol are separate series
        return (rec.get("stream"), "book", f"{rec.get('venue')}:{rec.get('market')}", rec.get("symbol"))
    return (rec.get("stream"), rec.get("kind"), rec.get("venue"), rec.get("symbol"))


def _content(rec):
    return json.dumps(rec, sort_keys=True, default=str)


def _ref(i, rec, **extra):
    d = {"index": i, "key": list(key_of(rec)), "ts": rec.get("ts")}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------------------------------------- order
def screen_order(records):
    """Pass 1 over arrival order: schema, monotonic timestamps, duplicates. Returns (accepted indices, findings)."""
    f = {"invalid": [], "out_of_order": [], "duplicate": [], "conflicting_duplicate": []}
    last, seen, accepted = {}, {}, []
    for i, rec in enumerate(records):
        probs = validate_record(rec)
        if probs:
            f["invalid"].append({"index": i, "problems": probs,
                                 "key": list(key_of(rec)) if isinstance(rec, dict) else None})
            continue
        k, ts = key_of(rec), rec["ts"]
        if (k, ts) in seen:
            first = seen[(k, ts)]
            same = _content(records[first]) == _content(rec)
            f["duplicate" if same else "conflicting_duplicate"].append(_ref(i, rec, first_index=first))
            continue
        if rec["kind"] not in ("forecast", "outcome") and k in last and ts < last[k]:
            f["out_of_order"].append(_ref(i, rec, previous_max_ts=last[k]))
            continue
        seen[(k, ts)] = i
        last[k] = ts
        accepted.append(i)
    return accepted, f


# ---------------------------------------------------------------------------------------------------------- books
def check_books(records, idx, cadence_s, max_quote_age_s=None, repeat_n=None):
    """Cross-field and staleness checks of accepted book records. Returns (rejected indices, findings)."""
    max_age = max_quote_age_s if max_quote_age_s is not None else cadence_s * DEFAULTS["max_quote_age_factor"]
    repeat_n = repeat_n or DEFAULTS["repeat_n"]
    f = {"crossed": [], "locked": [], "stale": [], "stale_suspected": [], "nonpositive": []}
    bad, runs = set(), {}
    for i in idx:
        r = records[i]
        if r["kind"] != "book":
            continue
        if r["bid"] <= 0 or r["ask"] <= 0 or r["bid_qty"] < 0 or r["ask_qty"] < 0:
            f["nonpositive"].append(_ref(i, r))
            bad.add(i)
            continue
        if r["bid"] > r["ask"]:
            f["crossed"].append(_ref(i, r, bid=r["bid"], ask=r["ask"]))
            bad.add(i)
            continue
        if r["bid"] == r["ask"]:
            f["locked"].append(_ref(i, r))
        q = r.get("quote_ts")
        if q is not None:
            age = r["ts"] - q
            if age > max_age:
                f["stale"].append(_ref(i, r, quote_age_s=round(age, 3), max_age_s=max_age))
                bad.add(i)
            continue
        k, sig = key_of(r), (r["bid"], r["ask"], r["bid_qty"], r["ask_qty"])
        run = runs.get(k)
        if run and run[0] == sig:
            run[1].append(i)
        else:
            runs[k] = run = [sig, [i]]
        if len(run[1]) == repeat_n:
            f["stale_suspected"].append(_ref(i, r, first_index=run[1][0], unchanged_samples=repeat_n))
    return bad, f


# ---------------------------------------------------------------------------------------------------------- funding
def check_funding(records, idx, allowed=None, max_abs_rate=None):
    allowed = set(allowed or DEFAULTS["allowed_funding_intervals_h"])
    max_abs = max_abs_rate if max_abs_rate is not None else DEFAULTS["max_abs_funding_rate"]
    f = {"bad_funding_interval": [], "funding_step_mismatch": [], "funding_rate_out_of_range": []}
    bad, prev = set(), {}
    for i in idx:
        r = records[i]
        if r["kind"] != "funding":
            continue
        if r["interval_h"] not in allowed:
            f["bad_funding_interval"].append(_ref(i, r, interval_h=r["interval_h"]))
            bad.add(i)
            continue
        if abs(r["rate"]) > max_abs:
            f["funding_rate_out_of_range"].append(_ref(i, r, rate=r["rate"]))
            bad.add(i)
            continue
        k = key_of(r)
        if k in prev:
            step = r["funding_time"] - prev[k]["funding_time"]
            if step != r["interval_h"] * 3600:
                f["funding_step_mismatch"].append(_ref(i, r, step_s=step, interval_h=r["interval_h"]))
        prev[k] = r
    return bad, f


# ---------------------------------------------------------------------------------------------------------- basis
def basis_record(spot, perp, stream="basis"):
    s_mid, p_mid = (spot["bid"] + spot["ask"]) / 2, (perp["bid"] + perp["ask"]) / 2
    return {"kind": "basis", "stream": stream, "ts": max(spot["ts"], perp["ts"]), "venue": perp["venue"],
            "symbol": perp["symbol"], "spot_ts": spot["ts"], "perp_ts": perp["ts"], "spot_mid": s_mid,
            "perp_mid": p_mid, "basis": p_mid / s_mid - 1}


def compute_basis(books, start, cadence_s, tol_s=None):
    """Basis only from a spot and a perp book of the same symbol in the same slot read within tol_s of each other.
    Books must be accepted (valid) ones. Returns (basis records, unpaired, time mismatches); nothing is interpolated."""
    tol = DEFAULTS["basis_tol_s"] if tol_s is None else tol_s
    slots = {}
    for r in books:
        slots.setdefault((r["symbol"], int((r["ts"] - start) // cadence_s)), {}).setdefault(r["market"], r)
    out, unpaired, mismatch = [], [], []
    for (sym, slot), m in sorted(slots.items()):
        if "spot" not in m or "perp" not in m:
            unpaired.append({"symbol": sym, "slot": slot, "have": sorted(m)})
            continue
        dt_s = abs(m["spot"]["ts"] - m["perp"]["ts"])
        if dt_s > tol:
            mismatch.append({"symbol": sym, "slot": slot, "dt_s": round(dt_s, 3), "tol_s": tol})
            continue
        out.append(basis_record(m["spot"], m["perp"]))
    return out, unpaired, mismatch


def check_basis(records, idx, tol_s=None):
    """Stored basis records: same-time legs and a recomputable value."""
    tol = DEFAULTS["basis_tol_s"] if tol_s is None else tol_s
    f = {"basis_time_mismatch": [], "basis_recompute_mismatch": []}
    bad = set()
    for i in idx:
        r = records[i]
        if r["kind"] != "basis":
            continue
        if abs(r["spot_ts"] - r["perp_ts"]) > tol:
            f["basis_time_mismatch"].append(_ref(i, r, dt_s=round(abs(r["spot_ts"] - r["perp_ts"]), 3)))
            bad.add(i)
        elif r["spot_mid"] <= 0 or abs(r["perp_mid"] / r["spot_mid"] - 1 - r["basis"]) > 1e-9:
            f["basis_recompute_mismatch"].append(_ref(i, r))
            bad.add(i)
    return bad, f


# ---------------------------------------------------------------------------------------------------------- universe
def universe_versions(records, trading=None):
    """Versions from universe snapshots (records sharing stream, venue and ts form one snapshot). A symbol is live in a
    snapshot when its status is a trading status. Listing time is known only to snapshot resolution:
    listed_after = the previous snapshot's ts (None for the first snapshot: present at start, not a listing)."""
    trading = set(trading or DEFAULTS["trading_status"])
    snaps = {}
    for r in records:
        if r.get("kind") == "universe":
            snaps.setdefault((r["stream"], r["venue"]), {}).setdefault(r["ts"], {})[r["symbol"]] = r
    out = {"symbols": {}, "listings": [], "delistings": [], "relistings": [], "spec_changes": [], "snapshots": {}}
    for (stream, venue), by_ts in sorted(snaps.items()):
        times = sorted(by_ts)
        out["snapshots"][f"{stream}|{venue}"] = times
        prev_t, prev_live, prev_rows = None, set(), {}
        for t in times:
            rows = by_ts[t]
            live = {s for s, r in rows.items() if r["status"] in trading}
            for s in sorted(live):
                info = out["symbols"].setdefault(s, {"venue": venue, "first_seen": t, "listed_after": prev_t,
                                                     "intervals": []})
                if s not in prev_live:
                    info["intervals"].append([t, None])
                    if prev_t is not None:
                        kind = "relistings" if len(info["intervals"]) > 1 else "listings"
                        out[kind].append({"symbol": s, "venue": venue, "first_seen": t, "listed_after": prev_t})
                elif _spec(prev_rows[s]) != _spec(rows[s]):
                    out["spec_changes"].append({"symbol": s, "venue": venue, "ts": t, "before": _spec(prev_rows[s]),
                                                "after": _spec(rows[s])})
            for s in sorted(prev_live - live):
                out["symbols"][s]["intervals"][-1][1] = t
                out["delistings"].append({"symbol": s, "venue": venue, "last_seen": prev_t, "gone_at": t,
                                          "status": rows[s]["status"] if s in rows else "absent"})
            prev_t, prev_live, prev_rows = t, live, rows
    return out


def _spec(r):
    return {k: r.get(k) for k in ("onboard_ts", "contract_type", "tick_size")}


def live_at(versions, t):
    """Symbols live at t by point-in-time knowledge: an interval [first, gone) with first <= t < gone."""
    return sorted(s for s, info in versions["symbols"].items()
                  if any(a <= t and (b is None or t < b) for a, b in info["intervals"]))


def check_universe_pit(claims, versions):
    """claims: [{"as_of": t, "symbols": [...], "label": optional}]. A symbol first seen after as_of (or unknown) is a
    point-in-time violation; a symbol live at as_of but absent is a survivorship omission."""
    f = {"pit_violations": [], "survivorship_omissions": []}
    for c in claims:
        t, have = c["as_of"], set(c["symbols"])
        for s in sorted(have):
            info = versions["symbols"].get(s)
            if info is None or info["first_seen"] > t:
                f["pit_violations"].append({"as_of": t, "symbol": s, "label": c.get("label"),
                                            "first_seen": info["first_seen"] if info else None})
        for s in live_at(versions, t):
            if s not in have:
                f["survivorship_omissions"].append({"as_of": t, "symbol": s, "label": c.get("label")})
    return f


# ---------------------------------------------------------------------------------------------------------- forecasts
FORECAST_FIELDS = ("model_id", "symbol", "issued_ts", "target_start", "target_end", "value")


def forecast_hash(rec):
    return hashlib.sha256(json.dumps([rec.get(k) for k in FORECAST_FIELDS], separators=(",", ":")).encode()).hexdigest()


def make_forecast(model_id, symbol, issued_ts, target_start, target_end, value, stream="forecast"):
    rec = {"kind": "forecast", "stream": stream, "ts": issued_ts, "model_id": model_id, "symbol": symbol,
           "issued_ts": issued_ts, "target_start": target_start, "target_end": target_end, "value": value}
    rec["hash"] = forecast_hash(rec)
    return rec


def check_forecasts(records, idx, now=None):
    """Frozen-before-outcome rules. Returns findings and the evaluable (frozen forecast, outcome) pairs."""
    f = {"lookahead": [], "revised": [], "tampered": [], "outcome_early": [], "missing_outcome": []}
    frozen, outcomes = {}, {}
    for i in idx:
        r = records[i]
        if r["kind"] == "outcome":
            if r["ts"] < r["target_end"]:
                f["outcome_early"].append(_ref(i, r))
            else:
                outcomes.setdefault((r["symbol"], r["target_start"], r["target_end"]), r)
            continue
        if r["kind"] != "forecast":
            continue
        if r["hash"] != forecast_hash(r):
            f["tampered"].append(_ref(i, r))
            continue
        if not r["issued_ts"] < r["target_start"] < r["target_end"]:
            f["lookahead"].append(_ref(i, r, issued_ts=r["issued_ts"], target_start=r["target_start"]))
            continue
        k = (r["model_id"], r["symbol"], r["target_start"])
        if k in frozen:
            f["revised"].append(_ref(i, r, frozen_index=frozen[k][0]))
            continue
        frozen[k] = (i, r)
    pairs = []
    for (model, sym, ts0), (i, r) in sorted(frozen.items()):
        o = outcomes.get((sym, ts0, r["target_end"]))
        if o is not None:
            pairs.append({"model_id": model, "symbol": sym, "target_start": ts0, "forecast": r["value"],
                          "realized": o["realized"]})
        elif now is not None and now >= r["target_end"]:
            f["missing_outcome"].append(_ref(i, r))
    return f, pairs


# ---------------------------------------------------------------------------------------------------------- gaps
def find_gaps(times, start, end, cadence_s, gap_factor=None, key=None):
    """Distances > gap_factor x cadence between consecutive valid samples, and from the window start to the first
    sample / from the last sample to the window end. missing_slots: cadence slots inside the gap with no valid sample."""
    g = ((DEFAULTS["gap_factor"] if gap_factor is None else gap_factor) + DEFAULTS["gap_jitter_factor"]) * cadence_s
    pts = sorted(set(t for t in times if start <= t < end))
    marks = [(start, "start")] + [(t, None) for t in pts] + [(end, "end")]
    if pts and pts[0] - start < cadence_s:
        marks = marks[1:]               # the first slot is covered: no start edge
    out = []
    for (a, ea), (b, eb) in zip(marks, marks[1:]):
        if b - a <= g:
            continue
        slots = (b - a) / cadence_s
        missing = int(math.floor(slots)) if (ea or eb) else int(round(slots)) - 1
        out.append({"key": list(key) if key else None, "from_ts": a, "to_ts": b, "duration_s": round(b - a, 3),
                    "missing_slots": missing, "edge": ea or eb})
    return out


def coverage_key(rec):
    """Coverage is per symbol, except a universe stream, whose unit is the snapshot (all symbols at one ts)."""
    if rec.get("kind") == "universe":
        return (rec.get("stream"), "universe", rec.get("venue"), "*")
    return key_of(rec)


def coverage(slots_valid, slots_any, lo, hi, start, cadence_s):
    """Counts over slot indices [lo, hi): valid, dropped (records arrived, none accepted) and missing."""
    expected = max(0, hi - lo)
    valid = sum(1 for s in range(lo, hi) if s in slots_valid)
    dropped = sum(1 for s in range(lo, hi) if s in slots_any and s not in slots_valid)
    return {"expected": expected, "valid": valid, "dropped": dropped, "missing": expected - valid - dropped,
            "coverage_pct": round(100.0 * valid / expected, 3) if expected else None}


# ---------------------------------------------------------------------------------------------------------- report
def assess(records, start, end, cadence, universe_claims=(), now=None, basis_tol_s=None, gap_factor=None,
           max_quote_age_s=None):
    """The full quality report. cadence: {stream: seconds} for book/basis/universe streams; funding keys use their
    own interval. Universe streams give each symbol's active window (listing..delisting) for expected counts."""
    accepted, f = screen_order(records)
    bad = set()
    book_idx = [i for i in accepted if records[i]["kind"] == "book"]
    by_stream = {}
    for i in book_idx:
        by_stream.setdefault(records[i]["stream"], []).append(i)
    for stream, ids in by_stream.items():
        b, fb = check_books(records, ids, cadence[stream], max_quote_age_s)
        bad |= b
        for k, v in fb.items():
            f.setdefault(k, []).extend(v)
    b, ff = check_funding(records, accepted)
    bad |= b
    f.update(ff)
    b, fbs = check_basis(records, accepted, basis_tol_s)
    bad |= b
    f.update(fbs)
    ok_idx = [i for i in accepted if i not in bad]
    versions = universe_versions([records[i] for i in ok_idx])
    for k in ("listings", "delistings", "relistings", "spec_changes"):
        f[k] = versions[k]
    f.update(check_universe_pit(universe_claims, versions))
    ff, pairs = check_forecasts(records, ok_idx, now=now)
    f.update(ff)
    # basis from books (derived, same-time only)
    valid_books = [records[i] for i in ok_idx if records[i]["kind"] == "book"]
    basis_by_stream = {}
    for r in valid_books:
        basis_by_stream.setdefault(r["stream"], []).append(r)
    derived, f["unpaired_basis"] = [], []
    f.setdefault("basis_time_mismatch", [])
    for stream, rows in sorted(basis_by_stream.items()):
        d, unp, mis = compute_basis(rows, start, cadence[stream], basis_tol_s)
        derived += d
        f["unpaired_basis"] += [dict(u, stream=stream) for u in unp]
        f["basis_time_mismatch"] += [dict(m, stream=stream, derived=True) for m in mis]
    # gaps and coverage per key
    keys_any, keys_ok = {}, {}
    for i in range(len(records)):
        r = records[i]
        if isinstance(r, dict) and r.get("kind") in KEY_KINDS and _is_number(r.get("ts")):
            keys_any.setdefault(coverage_key(r), []).append(r)
    for i in ok_idx:
        r = records[i]
        if r["kind"] in KEY_KINDS:
            keys_ok.setdefault(coverage_key(r), []).append(r)
    f["gaps"], cov = [], {}
    for k in sorted(keys_any, key=lambda x: tuple(str(v) for v in x)):
        stream, kind, venue, sym = k
        rows_ok = keys_ok.get(k, [])
        if kind == "funding":
            ivs = [r["interval_h"] for r in rows_ok]
            if not ivs:
                continue
            cad = max(set(ivs), key=ivs.count) * 3600
            times_ok, times_any = [r["funding_time"] for r in rows_ok], [r.get("funding_time") for r in keys_any[k]]
        else:
            cad = cadence.get(stream)
            if cad is None:
                continue
            times_ok, times_any = [r["ts"] for r in rows_ok], [r["ts"] for r in keys_any[k]]
        lo_t, hi_t = start, end
        if kind != "universe":
            info = versions["symbols"].get(sym)
            if info is not None and info["intervals"]:
                lo_t = max(start, info["intervals"][0][0] if info["listed_after"] is not None else start)
                last_gone = info["intervals"][-1][1]
                hi_t = min(end, last_gone) if last_gone is not None else end
        lo, hi = int((lo_t - start) // cad), int(-(-(hi_t - start) // cad))
        s_ok = {int((t - start) // cad) for t in times_ok}
        s_any = {int((t - start) // cad) for t in times_any if _is_number(t)}
        f["gaps"] += find_gaps(times_ok, lo_t, hi_t, cad, gap_factor, key=k)
        cov["|".join(str(x) for x in k)] = coverage(s_ok, s_any, lo, hi, start, cad)
    totals = {"expected": sum(c["expected"] for c in cov.values()), "valid": sum(c["valid"] for c in cov.values()),
              "dropped": sum(c["dropped"] for c in cov.values()), "missing": sum(c["missing"] for c in cov.values())}
    totals["coverage_pct"] = round(100.0 * totals["valid"] / totals["expected"], 3) if totals["expected"] else None
    errors = {k: len(f.get(k, [])) for k in SCHEMA["errors"]}
    errors["nonpositive"] = len(f.get("nonpositive", []))
    warnings = {k: len(f.get(k, [])) for k in SCHEMA["warnings"]}
    return {"version": VERSION, "window": {"start": start, "end": end}, "records_in": len(records),
            "accepted": len(ok_idx), "ok": not any(errors.values()), "errors": errors, "warnings": warnings,
            "info": {k: len(f.get(k, [])) for k in SCHEMA["info"]}, "findings": f, "coverage": cov,
            "totals": totals, "basis_derived": len(derived), "forecast_pairs": len(pairs)}


def report_sha256(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()


def write_report(report, path):
    """The only writer in this module: an explicit path chosen by the caller."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, sort_keys=True, indent=1, default=str)
    return path


# ---------------------------------------------------------------------------------------------------------- simulator
SYN_START = 2_000_000_000          # 2033-05-18: deliberately not a real collection period


def simulate(seed=50, hours=6, cadence_s=60, symbols=("AAA", "BBB", "CCC"), faults=True, list_sym="NEWX",
             delist_sym="OLDX", universe_every_s=3600 // 4, funding_interval_h=1):
    """A deterministic synthetic collector. Returns (records, truth, params). truth lists every injected fault with
    the identifiers a detector must report. faults=False gives clean data (still with a mid-period listing and a
    delisting, which are information, not errors)."""
    rng = random.Random(seed)
    start, end = SYN_START, SYN_START + hours * 3600
    n = hours * 3600 // cadence_s
    list_step, delist_step = n // 3, 2 * n // 3
    snap_every = universe_every_s // cadence_s
    # align listing/delisting with a universe snapshot so the active window is exact
    list_step -= list_step % snap_every
    delist_step -= delist_step % snap_every
    syms = list(symbols) + [list_sym, delist_sym]
    price = {s: 100.0 * (1 + i) for i, s in enumerate(syms)}
    recs, truth = [], []

    def active(s, step):
        if s == list_sym:
            return step >= list_step
        if s == delist_sym:
            return step < delist_step
        return True

    plan = {}
    if faults:
        a, b, c = symbols[0], symbols[1], symbols[2 % len(symbols)]
        plan = {"gap": (a, n // 6, 4), "stale": (b, n // 5, 3), "duplicate": (c, n // 4),
                "conflicting_duplicate": (a, n // 2 + 7), "crossed": (b, n // 2), "out_of_order": (c, n // 2 + 3),
                "basis_time_mismatch": (a, 3 * n // 4 + 5), "spot_gap": (c, 5 * n // 6, 3)}
    last_quote = {}
    pending_late = []
    for step in range(n):
        base = start + step * cadence_s
        for s in syms:
            if not active(s, step):
                continue
            price[s] *= math.exp(rng.gauss(0, 0.001))
            for market in ("perp", "spot"):
                ts = base + round(rng.uniform(0.0, 1.0), 3)
                mid = price[s] * (1.0005 if market == "perp" else 1.0)
                half = mid * rng.uniform(0.0001, 0.0004)
                rec = {"kind": "book", "stream": "syn_book", "ts": ts, "venue": "synx", "symbol": s,
                       "market": market, "bid": round(mid - half, 6), "ask": round(mid + half, 6),
                       "bid_qty": round(rng.uniform(1, 50), 3), "ask_qty": round(rng.uniform(1, 50), 3),
                       "quote_ts": round(ts - rng.uniform(0.01, 2.0), 3)}
                k = (s, market)
                g = plan.get("gap")
                if market == "perp" and g and s == g[0] and g[1] <= step < g[1] + g[2]:
                    if step == g[1]:
                        truth.append({"fault": "gap", "key": ["syn_book", "book", "synx:perp", s],
                                      "from_step": g[1], "steps": g[2]})
                    continue
                sg = plan.get("spot_gap")
                if market == "spot" and sg and s == sg[0] and sg[1] <= step < sg[1] + sg[2]:
                    if step == sg[1]:
                        truth.append({"fault": "gap", "key": ["syn_book", "book", "synx:spot", s],
                                      "from_step": sg[1], "steps": sg[2]})
                    continue
                st = plan.get("stale")
                if market == "perp" and st and s == st[0] and st[1] <= step < st[1] + st[2] and k in last_quote:
                    old = last_quote[k]
                    rec.update({x: old[x] for x in ("bid", "ask", "bid_qty", "ask_qty", "quote_ts")})
                    truth.append({"fault": "stale", "key": ["syn_book", "book", "synx:perp", s], "ts": ts})
                cr = plan.get("crossed")
                if market == "perp" and cr and s == cr[0] and step == cr[1]:
                    rec["bid"], rec["ask"] = rec["ask"] * 1.001, rec["bid"]
                    truth.append({"fault": "crossed", "key": ["syn_book", "book", "synx:perp", s], "ts": ts})
                bt = plan.get("basis_time_mismatch")
                if market == "spot" and bt and s == bt[0] and step == bt[1]:
                    rec["ts"] = round(base + 25.0, 3)
                    rec["quote_ts"] = round(rec["ts"] - 0.5, 3)
                    truth.append({"fault": "basis_time_mismatch", "symbol": s, "slot": step})
                oo = plan.get("out_of_order")
                if market == "perp" and oo and s == oo[0] and step == oo[1]:
                    pending_late.append((step + 2, rec))
                    truth.append({"fault": "out_of_order", "key": ["syn_book", "book", "synx:perp", s], "ts": rec["ts"]})
                    continue
                recs.append(rec)
                if market == "perp":
                    last_quote[k] = rec
                du = plan.get("duplicate")
                if market == "perp" and du and s == du[0] and step == du[1]:
                    recs.append(dict(rec))
                    truth.append({"fault": "duplicate", "key": ["syn_book", "book", "synx:perp", s], "ts": rec["ts"]})
                cd = plan.get("conflicting_duplicate")
                if market == "perp" and cd and s == cd[0] and step == cd[1]:
                    recs.append(dict(rec, bid_qty=rec["bid_qty"] + 1.0))
                    truth.append({"fault": "conflicting_duplicate", "key": ["syn_book", "book", "synx:perp", s],
                                  "ts": rec["ts"]})
        for due, late in list(pending_late):
            if due == step:
                recs.append(late)
                pending_late.remove((due, late))
        if step % snap_every == 0:          # universe snapshot
            for s in syms:
                if s == list_sym and step < list_step:
                    continue
                status = "TRADING" if active(s, step) else "SETTLING"
                if s == delist_sym and step >= delist_step + snap_every:
                    continue                # gone from the list one snapshot after it stopped trading
                recs.append({"kind": "universe", "stream": "syn_universe", "ts": base, "venue": "synx", "symbol": s,
                             "status": status, "onboard_ts": start - 86400 if s != list_sym else start
                             + list_step * cadence_s, "contract_type": "PERPETUAL", "tick_size": 0.0001})
        if (step * cadence_s) % (funding_interval_h * 3600) == 0:   # settled funding
            for s in syms:
                if not active(s, step):
                    continue
                recs.append({"kind": "funding", "stream": "syn_funding", "ts": base + 30, "venue": "synx",
                             "symbol": s, "rate": round(rng.uniform(-0.0005, 0.0010), 7),
                             "interval_h": funding_interval_h, "funding_time": base, "mark": round(price[s], 6)})
    if faults:                              # one funding record with an interval outside the allowed set
        s = symbols[0]
        recs.append({"kind": "funding", "stream": "syn_funding", "ts": end + 30, "venue": "synx", "symbol": s,
                     "rate": 0.0001, "interval_h": 3, "funding_time": end, "mark": round(price[s], 6)})
        truth.append({"fault": "bad_funding_interval", "key": ["syn_funding", "funding", "synx", s]})
    # forecasts issued one minute before each hour for that hour; outcomes after the hour
    for h in range(1, hours):
        t0 = start + h * 3600
        for s in symbols:
            recs.append(make_forecast("syn_vol/1", s, t0 - 60, t0, t0 + 3600, round(rng.uniform(0.01, 0.03), 6)))
            recs.append({"kind": "outcome", "stream": "outcome", "ts": t0 + 3600 + 5, "symbol": s,
                         "target_start": t0, "target_end": t0 + 3600, "realized": round(rng.uniform(0.01, 0.03), 6)})
    if faults:
        s, t0 = symbols[0], start + 2 * 3600
        late = make_forecast("syn_vol/1", s, t0 + 10, t0 + 3600 - 3600, t0 + 3600, 0.02)   # issued after start
        recs.append(late)
        truth.append({"fault": "lookahead", "symbol": s, "target_start": t0})
        rev = make_forecast("syn_vol/1", symbols[1], t0 - 30, t0, t0 + 3600, 0.5)
        recs.append(rev)
        truth.append({"fault": "revised", "symbol": symbols[1], "target_start": t0})
        tam = make_forecast("syn_vol/1", symbols[2 % len(symbols)], start + 3 * 3600 - 60, start + 3 * 3600,
                            start + 4 * 3600, 0.02)
        tam["value"] = 0.03                 # changed after the hash was taken
        recs.append(dict(tam, model_id="syn_vol/2"))
        truth.append({"fault": "tampered", "symbol": symbols[2 % len(symbols)]})
    params = {"start": start, "end": end, "cadence": {"syn_book": cadence_s, "syn_universe": universe_every_s},
              "list_sym": list_sym, "delist_sym": delist_sym, "list_ts": start + list_step * cadence_s,
              "delist_ts": start + delist_step * cadence_s, "seed": seed}
    return recs, truth, params


def selftest(seed=50):
    out = {}
    for label, faults in (("clean", False), ("faulty", True)):
        recs, truth, p = simulate(seed=seed, faults=faults)
        claims = [{"as_of": p["list_ts"] - 1, "symbols": ["AAA", "BBB", "CCC", "OLDX"], "label": "before listing"}]
        if faults:
            claims.append({"as_of": p["list_ts"] - 1, "symbols": ["AAA", "BBB", "CCC", "OLDX", "NEWX"],
                           "label": "future symbol"})
        rep = assess(recs, p["start"], p["end"], p["cadence"], claims, now=p["end"] + 7200)
        out[label] = {"ok": rep["ok"], "errors": {k: v for k, v in rep["errors"].items() if v},
                      "warnings": {k: v for k, v in rep["warnings"].items() if v}, "info": rep["info"],
                      "totals": rep["totals"], "injected": len(truth), "sha256": report_sha256(rep)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("selftest", help="run the synthetic simulator (clean and faulty) and print the summary")
    s.add_argument("--seed", type=int, default=50)
    a = ap.parse_args(argv)
    if a.cmd == "selftest":
        print(json.dumps(selftest(a.seed), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
