"""Blind adversarial v1.1 inputs; no evaluator imports or external inputs."""

import copy
import hashlib
import json
from pathlib import Path
import random

SEED = 5100
START = 1000
CADENCE = 10


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def hypothesis(hid="H", **changes):
    value = dict(hid=hid, family="F", signal_key="s", rule="sign",
                 cost_bps=0, funding=False)
    value.update(changes)
    return value


def row(i, ret=0.25, value=1, asset="A", delay=0, funding=0):
    ts = START + CADENCE * i
    return dict(ts=ts, asset=asset, ret=ret, funding=funding,
                signals={"s": dict(value=value, avail_ts=ts + delay)})


def base(n=30, bias=0.125, scale=1):
    return dict(fixture_id="placeholder", cadence_s=CADENCE, alpha=0.05,
                q_fdr=0.05, window=dict(start=START, end=START + CADENCE * n),
                universe={"A": dict(listed_from=START, delisted_at=None)},
                hypotheses=[hypothesis()], observations=[
                    row(i, ret=scale * ((1 if i % 2 == 0 else -1) + bias))
                    for i in range(n)], ledger_requests=[])


def request(key="k", **changes):
    value = dict(key=key, hid="H", family="F", variants=1, alpha=0.01, ts=START)
    value.update(changes)
    return value


def lock(fixture):
    protocol = {key: fixture[key] for key in
                ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}
    fixture["lock"] = dict(
        protocol_sha256=hashlib.sha256(canonical(protocol)).hexdigest(),
        data_sha256=hashlib.sha256(canonical(fixture["observations"])).hexdigest())


def multiple(z_values):
    f = base()
    f["hypotheses"] = [hypothesis("H" + str(i + 1), family="F" + str(i),
        signal_key="s" + str(i), rule="clip1") for i in range(len(z_values))]
    for i, observation in enumerate(f["observations"]):
        observation["ret"] = 1
        observation["signals"] = {"s" + str(k): dict(
            value=0.25 * ((1 if i % 2 == 0 else -1) + z / 30),
            avail_ts=observation["ts"]) for k, z in enumerate(z_values)}
    return f


def build_cases():
    rng = random.Random(SEED)
    cases = []

    def add(slug, attack, f):
        f["fixture_id"] = "R2_" + slug
        cases.append((attack, f))

    f = base(32)
    f["hypotheses"][0].update(cost_bps=10, funding=True)
    f["observations"][1]["signals"]["s"]["avail_ts"] += 1
    for i in (2, 3):
        f["observations"][i].update(ret=None, funding=None)
    f["observations"][2]["signals"]["s"]["avail_ts"] += 1
    add("01_availability", "t+1 versus t; MISSING precedes signal/funding", f)

    f = base()
    f["hypotheses"][0]["cost_bps"] = 10
    f["observations"] = [row(i, ret=0, value=1 if i % 2 == 0 else -1) for i in range(30)]
    add("02_flip_cost", "entry plus 29 full flips; no terminal liquidation", f)

    f = base(6)
    f["hypotheses"][0].update(rule="clip1", cost_bps=10)
    f["observations"] = [row(i, ret=0, value=v) for i, v in
                            enumerate([0, 0.25, 0.75, -0.5, -1, 0])]
    add("03_clip_turnover", "fractional turnover versus sign or full notional", f)

    f = base(7)
    f["hypotheses"][0]["cost_bps"] = 10
    f["observations"] = [row(0), row(2), row(3, ret=None), row(4, value=-1),
                         row(5, value=None), row(6)]
    add("04_resets", "position reset at gap and MISSING; missing signal costs exit", f)

    f = base(4)
    f["window"]["embargo_s"] = 20
    f["hypotheses"][0]["cost_bps"] = 10
    f["observations"] = [row(0), row(0), row(1), row(2), row(3, value=-1), row(0, delay=1)]
    extra = row(0)
    extra["ts"] += 1
    f["observations"].append(extra)
    add("05_embargo_reset", "offgrid then embargo then dedup; first active entry", f)

    for slug, embargo in (("06_embargo_zero", 0), ("07_embargo_one", CADENCE)):
        f = base()
        f["window"]["embargo_s"] = embargo
        f["observations"] += [row(-1), row(30)]
        add(slug, "embargo boundary; before-start and exact-end are offgrid", f)

    for n in (29, 30, 31):
        add("08_T29" if n == 29 else "09_T30" if n == 30 else "10_T31",
            "sample-size threshold and analytic alternating HAC", base(n))

    f = base()
    f["observations"] = [row(i, ret=0.25) for i in range(30)]
    add("11_constant", "S=0 retains lag but nulls test fields", f)
    f = base()
    f["observations"] = [row(i, ret=8 if i == 15 else 0) for i in range(30)]
    add("12_outlier", "one extreme retained; no trimming or clipping returns", f)
    f = base()
    f["observations"] = [row(i, ret=None) if i % 2 == 0 else row(i, asset="X")
                         for i in range(30)]
    add("13_all_empty", "raw rows without valid portfolio bars are empty, not gaps", f)

    f = base()
    f["universe"] = {a: dict(listed_from=START, delisted_at=None) for a in "DCBA"}
    f["observations"] = [row(i, ret=v, asset=a) for i in range(30)
                         for a, v in zip("ABCD", [1e16, 1, -1e16, 3])]
    rng.shuffle(f["observations"])
    add("14_fsum_assets", "cancellation: fsum gives portfolio 1, naive sum 0.75", f)
    add("15_tiny", "small representable HAC products, scale invariance", base(scale=1e-140))
    add("16_large", "large representable HAC products, scale invariance", base(scale=1e140))
    add("17_holm_ties_all", "identical p across families; all rejected", multiple([2.4] * 3))
    add("18_holm_single", "m=1 inclusive ordinary threshold", multiple([1.875]))
    add("19_holm_stop", "first rejected then stop; later rank must stay false", multiple([3.5, 1.8, 1.7]))
    add("20_bh_vs_holm", "Holm none versus BH all; correlated hypotheses", multiple([2.05, 1.88, 1.76]))

    f = base()
    f["hypotheses"].append(hypothesis("COPY", cost_bps=10, funding=True))
    add("21_duplicate_cost", "same fingerprint different cost/funding excluded from m", f)
    f = base()
    f["observations"] = [row(i, ret=0.25) for i in range(30)]
    f["hypotheses"].append(hypothesis("COPY", cost_bps=10))
    add("22_duplicate_S0", "first INSUFFICIENT, duplicate testable but DUPLICATE wins", f)
    f = base(29)
    f["hypotheses"].append(hypothesis("COPY", cost_bps=10))
    add("23_duplicate_short", "short duplicate retains null test fields and DUPLICATE", f)

    f = base()
    f["ledger_requests"] = [request(alpha=0), request(alpha=0.0, ts=START + 1)]
    for field, changed in (("hid", "OTHER"), ("family", "G"), ("variants", 2), ("alpha", 0.02)):
        f["ledger_requests"] += [request(field), request(field, **{field: changed})]
    f["ledger_requests"] += [request("retry", variants=0), request("retry", variants=2),
        request("bad", variants=False, alpha=-1), request("bad", alpha="0.1"),
        request("bad", alpha=True), request("bad", alpha=0.03)]
    add("24_ledger_replay", "key_conflict per payload field; ts ignored; rejected key retried", f)
    for slug, amount in (("25_hash_int", 0), ("26_hash_float", 0.0)):
        f = base()
        f["ledger_requests"] = [request("repr", alpha=amount)]
        add(slug, "0 versus 0.0 preserved in hash preimage", f)
    f = base()
    f["ledger_requests"] = [request(str(i), alpha=a) for i, a in enumerate([1e16, 1.0, 1.0])]
    add("27_ledger_fsum", "ledger alpha total fsum, no artificial upper bound", f)

    f = base()
    del f["q_fdr"]
    del f["observations"][0]["funding"]
    add("28_missing", "MISSING_FIELD at top and nested paths; no partial output", f)
    f = base()
    f["extra"] = 1
    f["window"]["extra"] = 1
    f["universe"]["A"]["extra"] = 1
    f["hypotheses"][0]["slippage_bps"] = 1
    f["observations"][0]["extra"] = 1
    f["observations"][0]["signals"]["s"]["extra"] = 1
    f["ledger_requests"] = [request()]
    f["ledger_requests"][0]["extra"] = 1
    add("29_unknown", "UNKNOWN_FIELD at every schema object; hidden cost component", f)
    f = base()
    f["hypotheses"][0]["funding"] = 1
    f["observations"][0]["signals"]["s"]["value"] = "0.1"
    add("30_bad_type", "BAD_TYPE: bool versus int; numeric-looking measurement string", f)
    f = base()
    f["observations"][0]["ts"] = 4102444801
    f["observations"][1]["signals"]["s"]["avail_ts"] = -1
    add("31_bad_time", "BAD_TIME at both timestamp bounds", f)
    f = base()
    f.update(cadence_s=0, alpha=1, q_fdr=0)
    f["window"]["embargo_s"] = -1
    f["hypotheses"][0]["cost_bps"] = -0.1
    f["universe"]["A"]["delisted_at"] = START
    add("32_bad_value", "BAD_VALUE collected across protocol, cost and membership", f)
    f = base()
    f["hypotheses"].append(hypothesis())
    add("33_duplicate_hid", "DUPLICATE_HID cannot overwrite output dictionary", f)
    f = base()
    f["hypotheses"][0]["signal_key"] = "absent"
    add("34_unknown_signal", "UNKNOWN_SIGNAL cannot silently create all-zero strategy", f)

    for slug, component in (("35_lock_protocol", "protocol"), ("36_lock_data", "data"), ("37_lock_good", "none")):
        f = base()
        lock(f)
        if component == "protocol":
            f["hypotheses"][0]["cost_bps"] = 1
        if component == "data":
            f["observations"][0]["ret"] = 0.5
        add(slug, "LOCK_MISMATCH " + component + "; hash exact canonical input", f)
    f = base()
    lock(f)
    del f["q_fdr"]
    f["extra"] = 1
    f["hypotheses"] += [hypothesis()]
    f["hypotheses"][0].update(signal_key="absent", funding=1, cost_bps=-1)
    f["observations"][0]["ts"] = "2026-11-06T00:00:00+01:00"
    add("38_many_errors", "all eight codes; sorted unique errors before any evaluation", f)
    f = base()
    f["lock"] = {}
    add("39_lock_missing", "missing both lock digests must not disable locking", f)

    f = base(8)
    f["hypotheses"][0]["funding"] = True
    values = [None, "NaN", "Infinity", "-Infinity"]
    for i, v in enumerate(values):
        f["observations"][i]["ret"] = v
        f["observations"][i + 4]["signals"]["s"]["value"] = v
        f["observations"][i + 4]["funding"] = v
    add("40_measurement_missing", "allowed IEEE strings/null, missing-rule precedence", f)
    f = base(4)
    f["universe"]["B"] = dict(listed_from=START + CADENCE, delisted_at=START + 3 * CADENCE)
    f["observations"] += [row(0, asset="B"), row(1, asset="B", ret=-0.6),
        row(2, asset="B"), row(3, asset="B"), row(0, asset="X"), row(0, asset="X")]
    f["observations"][0]["ret"] = None
    f["observations"].append(row(0, ret=0.4))
    add("41_membership_dupes", "first MISSING wins; nonmember dedup; pre-delist history", f)
    add("42_restart", "replace previously truncated file; never append", base())
    f = base()
    shift = 4102444500 - START
    for key in ("start", "end"):
        f["window"][key] += shift
    f["universe"]["A"]["listed_from"] += shift
    for observation in f["observations"]:
        observation["ts"] += shift
        observation["signals"]["s"]["avail_ts"] += shift
    f["ledger_requests"] = [request(ts=4102444800)]
    add("43_time_upper_valid", "inclusive max UTC timestamp; exclusive window end", f)
    f = base()
    f.update(hypotheses=[], universe={}, observations=[])
    add("44_empty_collections", "empty schema-valid collections and empty ledger genesis", f)
    f = base()
    f.update(window=[], universe=[], hypotheses=[None], observations=[[]], ledger_requests={})
    add("45_container_types", "malformed containers must collect errors without crashing", f)
    f = base()
    f["window"]["embargo_s"] = 15
    add("46_embargo_fraction", "first active grid bar uses ceiling, not shifted grid", f)
    f = base()
    f["observations"][0]["ts"] = float(START)
    f["observations"][1]["signals"]["s"]["avail_ts"] = True
    add("47_time_types", "integer-valued float and bool timestamps rejected", f)
    return cases


def main():
    root = Path(__file__).resolve().parent
    target = root / "fixtures"
    target.mkdir(parents=True, exist_ok=True)
    manifest = []
    for attack, fixture in build_cases():
        identifier = fixture["fixture_id"]
        raw = canonical(fixture)
        (target / (identifier + ".json")).write_bytes(raw)
        manifest.append(dict(fixture_id=identifier, attack=attack,
                             sha256=hashlib.sha256(raw).hexdigest()))
    (root / "manifest.json").write_bytes(canonical(manifest))


if __name__ == "__main__":
    main()
