"""Independent EVALUATOR_SPEC v1.1 implementation; standard library only.

Source: ../crosscheck/EVALUATOR_SPEC_V1_1.md and its referenced v1 spec.
No other repository code
is imported or consulted. Inputs and output files are the only I/O.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile


def canonical_json(obj):
    """Section 8 encoding, rejecting accidental non-finite output."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _number(value):
    return type(value) in (int, float)


def _input_hash(obj):
    # Input IEEE numbers may be non-finite; v1's dumps defaults apply here.
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate(fixture):
    """Collect all locally decidable schema errors before doing any evaluation."""
    errors = set()

    def error(code, path):
        errors.add((code, path))

    def child(path, key):
        return (path + "." if path else "") + str(key)

    def shape(obj, path, required, optional=()):
        if not isinstance(obj, dict):
            error("BAD_TYPE", path)
            return False
        for key in required:
            if key not in obj:
                error("MISSING_FIELD", child(path, key))
        for key in obj:
            if key not in required and key not in optional:
                error("UNKNOWN_FIELD", child(path, key))
        return True

    def string(obj, key, path, nonempty=True):
        if key in obj and (not isinstance(obj[key], str)
                           or (nonempty and not obj[key])):
            error("BAD_TYPE", child(path, key))

    def timestamp(obj, key, path, type_code="BAD_TYPE"):
        if key not in obj:
            return
        value = obj[key]
        if type(value) is not int:
            error(type_code, child(path, key))
        if type(value) is not int or not 0 <= value <= 4102444800:
            error("BAD_TIME", child(path, key))

    required = ("fixture_id", "cadence_s", "alpha", "q_fdr", "window", "universe",
                "hypotheses", "observations", "ledger_requests")
    if not shape(fixture, "", required, ("lock",)):
        return [dict(code=c, path=p) for c, p in sorted(errors)]
    if "fixture_id" in fixture and (not isinstance(fixture["fixture_id"], str)
            or re.fullmatch(r"[A-Za-z0-9_-]+", fixture["fixture_id"]) is None):
        error("BAD_TYPE", "fixture_id")
    if "cadence_s" in fixture:
        cadence = fixture["cadence_s"]
        if type(cadence) is not int:
            error("BAD_TYPE", "cadence_s")
        elif cadence <= 0:
            error("BAD_VALUE", "cadence_s")
    for key in ("alpha", "q_fdr"):
        if key in fixture:
            if not _number(fixture[key]):
                error("BAD_TYPE", key)
            elif not math.isfinite(fixture[key]) or not 0 < fixture[key] < 1:
                error("BAD_VALUE", key)
    window = fixture.get("window")
    if "window" in fixture and shape(window, "window", ("start", "end"), ("embargo_s",)):
        for key in ("start", "end"):
            timestamp(window, key, "window")
        if "embargo_s" in window and type(window["embargo_s"]) is not int:
            error("BAD_TYPE", "window.embargo_s")
        start, end, embargo = window.get("start"), window.get("end"), window.get("embargo_s", 0)
        if type(start) is int and type(end) is int:
            if start >= end:
                error("BAD_VALUE", "window")
            if type(embargo) is int and (embargo < 0 or embargo >= end - start):
                error("BAD_VALUE", "window.embargo_s")
        elif type(embargo) is int and embargo < 0:
            error("BAD_VALUE", "window.embargo_s")
    universe = fixture.get("universe")
    if "universe" in fixture:
        if not isinstance(universe, dict):
            error("BAD_TYPE", "universe")
        else:
            for asset, listing in universe.items():
                path = "universe." + str(asset)
                if not isinstance(asset, str):
                    error("BAD_TYPE", path)
                if not shape(listing, path, ("listed_from", "delisted_at")):
                    continue
                timestamp(listing, "listed_from", path, "BAD_VALUE")
                if "delisted_at" in listing and listing["delisted_at"] is not None:
                    timestamp(listing, "delisted_at", path, "BAD_VALUE")
                    if (type(listing["delisted_at"]) is int
                            and type(listing.get("listed_from")) is int
                            and listing["delisted_at"] <= listing["listed_from"]):
                        error("BAD_VALUE", child(path, "delisted_at"))
    hypotheses = fixture.get("hypotheses")
    hids, used_signals = set(), []
    if "hypotheses" in fixture:
        if not isinstance(hypotheses, list):
            error("BAD_TYPE", "hypotheses")
        else:
            for i, h in enumerate(hypotheses):
                path = f"hypotheses[{i}]"
                if not shape(h, path, ("hid", "family", "signal_key", "rule", "cost_bps", "funding")):
                    continue
                for key in ("hid", "family", "signal_key"):
                    string(h, key, path)
                hid = h.get("hid")
                if isinstance(hid, str) and hid:
                    if hid in hids:
                        error("DUPLICATE_HID", child(path, "hid"))
                    hids.add(hid)
                signal = h.get("signal_key")
                if isinstance(signal, str) and signal:
                    used_signals.append((signal, child(path, "signal_key")))
                if "rule" in h and h["rule"] not in ("sign", "clip1"):
                    error("BAD_TYPE", child(path, "rule"))
                if "funding" in h and type(h["funding"]) is not bool:
                    error("BAD_TYPE", child(path, "funding"))
                if "cost_bps" in h:
                    cost = h["cost_bps"]
                    if not _number(cost):
                        error("BAD_TYPE", child(path, "cost_bps"))
                    elif not math.isfinite(cost) or cost < 0:
                        error("BAD_VALUE", child(path, "cost_bps"))
    observations = fixture.get("observations")
    known_signals = set()
    if "observations" in fixture:
        if not isinstance(observations, list):
            error("BAD_TYPE", "observations")
        else:
            for i, row in enumerate(observations):
                path = f"observations[{i}]"
                if not shape(row, path, ("ts", "asset", "ret", "funding", "signals")):
                    continue
                timestamp(row, "ts", path)
                string(row, "asset", path, False)
                for key in ("ret", "funding"):
                    if key in row and not _measurement(row[key]):
                        error("BAD_TYPE", child(path, key))
                if "signals" in row:
                    signals = row["signals"]
                    if not isinstance(signals, dict):
                        error("BAD_TYPE", child(path, "signals"))
                        continue
                    known_signals.update(signals)
                    for key, signal in signals.items():
                        spath = child(child(path, "signals"), key)
                        if not shape(signal, spath, ("value", "avail_ts")):
                            continue
                        timestamp(signal, "avail_ts", spath)
                        if "value" in signal and not _measurement(signal["value"]):
                            error("BAD_TYPE", child(spath, "value"))
    for signal, path in used_signals:
        if signal not in known_signals:
            error("UNKNOWN_SIGNAL", path)
    requests = fixture.get("ledger_requests")
    if "ledger_requests" in fixture:
        if not isinstance(requests, list):
            error("BAD_TYPE", "ledger_requests")
        else:
            for i, request in enumerate(requests):
                path = f"ledger_requests[{i}]"
                if not shape(request, path, ("key", "hid", "family", "variants", "alpha", "ts")):
                    continue
                for key in ("key", "hid", "family"):
                    string(request, key, path)
                timestamp(request, "ts", path)
    if "lock" in fixture:
        lock = fixture["lock"]
        if not isinstance(lock, dict):
            error("LOCK_MISMATCH", "lock")
        else:
            components = {
                "protocol_sha256": ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr"),
                "data_sha256": ("observations",)}
            for key, fields in components.items():
                try:
                    obj = ({field: fixture[field] for field in fields}
                           if key == "protocol_sha256" else fixture["observations"])
                    expected = _input_hash(obj)
                except (KeyError, TypeError, ValueError, OverflowError):
                    expected = None
                if key not in lock or expected is None or lock[key] != expected:
                    error("LOCK_MISMATCH", "lock." + key)
    return [dict(code=c, path=p) for c, p in sorted(errors)]


def _measurement(value):
    return (_number(value) or value is None
            or (isinstance(value, str) and value in ("NaN", "Infinity", "-Infinity")))


def _finite_number(value):
    # Section 1 admits these three strings as IEEE values, hence not finite.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _member(universe, asset, ts):
    listing = universe.get(asset)
    return (listing is not None and listing["listed_from"] <= ts
            and (listing["delisted_at"] is None or ts < listing["delisted_at"]))


def _prepare(fixture, grid):
    """Section 2: filter in numbered order; retain raw on-grid presence."""
    grid_set = set(grid)
    raw_times, seen = set(), set()
    rows = {}
    counts = dict(n_offgrid=0, n_embargo=0, n_duplicates=0, n_not_member=0)
    cutoff = fixture["window"]["start"] + fixture["window"].get("embargo_s", 0)
    for row in fixture["observations"]:
        ts, asset = row["ts"], row["asset"]
        if ts not in grid_set:
            counts["n_offgrid"] += 1
            continue
        if ts < cutoff:
            counts["n_embargo"] += 1
            continue
        raw_times.add(ts)
        key = (ts, asset)
        if key in seen:
            counts["n_duplicates"] += 1
            continue
        seen.add(key)
        if not _member(fixture["universe"], asset, ts):
            counts["n_not_member"] += 1
            continue
        rows.setdefault(ts, {})[asset] = row
    return rows, raw_times, counts


def hac_statistics(series):
    """Section 5 and section 8's short-series hac_lag convention."""
    size = len(series)
    result = dict(T=size, mean_net=math.fsum(series) / size if size else None,
                  hac_lag=None, se=None, t=None, p_one=None,
                  status="INSUFFICIENT")
    if size < 30:
        return result
    lag = min(size - 1, max(0, math.floor(4 * (size / 100) ** (2 / 9))))
    result["hac_lag"] = lag
    centered = [value - result["mean_net"] for value in series]
    gamma = [math.fsum(centered[t] * centered[t - k]
                 for t in range(k, size)) / size for k in range(lag + 1)]
    variance = math.fsum([gamma[0], 2 * math.fsum(
        (1 - k / (lag + 1)) * gamma[k] for k in range(1, lag + 1))])
    if variance <= 0:
        return result
    se = math.sqrt(variance / size)
    statistic = result["mean_net"] / se
    result.update(status="TESTED", se=se, t=statistic,
                  p_one=0.5 * math.erfc(statistic / math.sqrt(2)))
    return result


def adjust_multiple(results, alpha, q_fdr):
    """Section 6; dict order is the original hypothesis-list order."""
    tested = []
    for result in results.values():
        result["holm_reject"] = result["bh_reject"] = None
        if result["status"] == "TESTED":
            result["holm_reject"] = result["bh_reject"] = False
            tested.append(result)
    tested.sort(key=lambda result: result["p_one"])  # stable for equal p
    size = len(tested)
    for k, result in enumerate(tested):
        if result["p_one"] > alpha / (size - k):
            break
        result["holm_reject"] = True
    largest = 0
    for k, result in enumerate(tested, 1):
        if result["p_one"] <= k * q_fdr / size:
            largest = k
    for result in tested[:largest]:
        result["bh_reject"] = True


def evaluate_ledger(requests):
    """Section 7: only accepted keys enter the idempotency set."""
    seen, family_hids, family_alphas = {}, {}, {}
    head = "0" * 64
    entries, hits = 0, 0
    errors, totals = [], {}
    for request in requests:
        key = request["key"]
        payload = tuple(request[field] for field in ("hid", "family", "variants", "alpha"))
        if key in seen:
            if payload == seen[key]:
                hits += 1
            else:
                errors.append(dict(key=key, reason="key_conflict"))
            continue
        variants, alpha = request["variants"], request["alpha"]
        if type(variants) is not int or variants < 1:
            errors.append(dict(key=key, reason="variants"))
            continue
        if (not _number(alpha)
                or not math.isfinite(alpha) or alpha < 0):
            errors.append(dict(key=key, reason="alpha"))
            continue
        post = dict(seq=entries, key=key, hid=request["hid"],
                    family=request["family"], variants=variants, alpha=alpha,
                    ts=request["ts"], prev=head)
        head = hashlib.sha256(canonical_json(post).encode("utf-8")).hexdigest()
        seen[key] = payload
        entries += 1
        family = request["family"]
        total = totals.setdefault(family, dict(attempts=0, variants=0,
                                               alpha=0.0, hypotheses=0))
        total["attempts"] += 1
        total["variants"] += variants
        family_alphas.setdefault(family, []).append(alpha)
        total["alpha"] = math.fsum(family_alphas[family])
        family_hids.setdefault(family, set()).add(request["hid"])
        total["hypotheses"] = len(family_hids[family])
    return dict(entries=entries, head=head, idempotent_hits=hits,
                errors=errors, totals=totals)


def evaluate(fixture: dict) -> dict:
    """Evaluate one schema-conforming synthetic fixture without mutating it."""
    errors = validate(fixture)
    fid = fixture.get("fixture_id") if isinstance(fixture, dict) else None
    if not isinstance(fid, str) or re.fullmatch(r"[A-Za-z0-9_-]+", fid) is None:
        fid = None
    if errors:
        return dict(spec_version="1.1", fixture_id=fid,
                    status="INVALID_INPUT", errors=errors)
    grid = range(fixture["window"]["start"], fixture["window"]["end"],
                 fixture["cadence_s"])
    rows, raw_times, common_counts = _prepare(fixture, grid)
    cutoff = fixture["window"]["start"] + fixture["window"].get("embargo_s", 0)
    active_grid = [ts for ts in grid if ts >= cutoff]
    results, fingerprints = {}, {}
    for hypothesis in fixture["hypotheses"]:
        counts = dict(common_counts)
        counts.update(n_missing_ret=0, n_signal_missing=0, n_lookahead=0,
                      n_funding_missing=0, n_extreme=0, n_gap_bars=0,
                      n_empty_bars=0)
        previous = {}
        net_series, gross_series, costs, fundings = [], [], [], []
        for ts in active_grid:
            current, bar_net, bar_gross = {}, [], []
            for asset in sorted(fixture["universe"]):
                row = rows.get(ts, {}).get(asset)
                if row is None:
                    continue
                ret = _finite_number(row["ret"])
                if ret is None:
                    counts["n_missing_ret"] += 1
                    continue
                signal = row["signals"].get(hypothesis["signal_key"])
                value = None if signal is None else _finite_number(signal["value"])
                weight = 0.0
                if value is None:
                    counts["n_signal_missing"] += 1
                elif signal["avail_ts"] > ts:
                    counts["n_lookahead"] += 1
                elif hypothesis["rule"] == "sign":
                    weight = float((value > 0) - (value < 0))
                elif hypothesis["rule"] == "clip1":
                    weight = min(1.0, max(-1.0, value))
                else:
                    raise ValueError("Unknown hypothesis rule")
                current[asset] = weight
                cost = (hypothesis["cost_bps"] / 10000
                        * abs(weight - previous.get(asset, 0.0)))
                funding = 0.0
                if hypothesis["funding"]:
                    rate = _finite_number(row["funding"])
                    if rate is None:
                        counts["n_funding_missing"] += 1
                    else:
                        funding = weight * rate
                gross = weight * ret
                bar_gross.append(gross)
                bar_net.append(gross - cost - funding)
                costs.append(cost)
                fundings.append(funding)
                if abs(ret) > 0.5:
                    counts["n_extreme"] += 1
            previous = current  # a gap, nonmember, or MISSING resets to zero
            if ts not in raw_times:
                counts["n_gap_bars"] += 1
            elif not bar_net:
                counts["n_empty_bars"] += 1
            else:
                net_series.append(math.fsum(bar_net) / len(bar_net))
                gross_series.append(math.fsum(bar_gross) / len(bar_gross))
        result = dict(counts)
        result.update(hac_statistics(net_series))
        result.update(duplicate_of=None,
                      mean_gross=(math.fsum(gross_series) / len(gross_series)
                                  if gross_series else None),
                      total_cost=math.fsum(costs), total_funding=math.fsum(fundings))
        fingerprint = tuple(hypothesis[key] for key in
                            ("family", "signal_key", "rule"))
        if fingerprint in fingerprints:
            result.update(status="DUPLICATE",
                          duplicate_of=fingerprints[fingerprint])
        else:
            fingerprints[fingerprint] = hypothesis["hid"]
        results[hypothesis["hid"]] = result
    adjust_multiple(results, fixture["alpha"], fixture["q_fdr"])
    return dict(spec_version="1.1", fixture_id=fixture["fixture_id"], status="OK",
                hypotheses=results,
                ledger=evaluate_ledger(fixture["ledger_requests"]))


def atomic_write(path, data):
    """Write complete bytes beside the target, then atomically replace it."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix="." + path.name + ".", delete=False) as stream:
            temporary = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.fixtures:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        result = evaluate(fixture)
        # No trailing newline: exactly the section 8 json.dumps bytes.
        name = result["fixture_id"] or path.stem
        atomic_write(args.out / (name + ".json"), canonical_json(result).encode("utf-8"))


if __name__ == "__main__":
    main()
