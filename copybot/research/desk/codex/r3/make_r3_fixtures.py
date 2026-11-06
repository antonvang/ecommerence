"""Spec-only R3 seeds, created before inspecting the frozen implementation."""
import hashlib
import json
import math
from pathlib import Path


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def base(identifier, size=30):
    return dict(fixture_id=identifier, cadence_s=10, alpha=0.05, q_fdr=0.05,
                window=dict(start=1000, end=1000 + size * 10),
                universe={"A": dict(listed_from=1000, delisted_at=None)},
                hypotheses=[dict(hid="H", family="F", signal_key="s", rule="sign",
                                 cost_bps=0, funding=False)],
                observations=[dict(ts=1000 + i * 10, asset="A", ret=(-1) ** i * 0.25,
                    funding=0, signals={"s": dict(value=1, avail_ts=1000 + i * 10)})
                    for i in range(size)], ledger_requests=[])


def locked(f):
    f["lock"] = dict(protocol_sha256=hashlib.sha256(encode({k: f[k] for k in
        ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")})).hexdigest(),
        data_sha256=hashlib.sha256(encode(f["observations"])).hexdigest())


def build_cases():
    cases = []
    def add(name, attack, f=None):
        f = base(name) if f is None else f
        cases.append((name, attack, encode(f)))
        return f

    f = base("R3_01_holm_equality")
    f.update(alpha=0.5, q_fdr=0.5)
    add(f["fixture_id"], "p equals decision threshold exactly", f)
    f = base("R3_02_embargo_boundary", 31)
    f["window"]["embargo_s"] = 10
    f["hypotheses"][0]["cost_bps"] = 10
    add(f["fixture_id"], "first active bar exactly at embargo cutoff", f)
    f = base("R3_03_grid_origin")
    f["window"] = dict(start=1003, end=1303)
    f["universe"]["A"]["listed_from"] = 1003
    for row in f["observations"]:
        row["ts"] += 3
        row["signals"]["s"]["avail_ts"] += 3
    add(f["fixture_id"], "grid anchored at start rather than Unix zero", f)
    f = base("R3_04_short_funding")
    f["hypotheses"][0]["funding"] = True
    for row in f["observations"]:
        row["signals"]["s"]["value"] = -1
        row["funding"] = 0.01
    add(f["fixture_id"], "short positions receive positive funding", f)

    f = base("R3_05_range_exact", 1)
    f["hypotheses"][0].update(cost_bps=1e6, funding=True, rule="clip1")
    f["observations"][0].update(ret=1e6, funding=-1e6)
    f["observations"][0]["signals"]["s"]["value"] = 1e12
    add(f["fixture_id"], "all four size limits are inclusive", f)
    for i, field in enumerate(("ret", "funding", "value", "cost_bps"), 6):
        name = f"R3_{i:02d}_range_{field}"
        f = base(name, 1)
        target = (f["hypotheses"][0] if field == "cost_bps" else
                  f["observations"][0]["signals"]["s"] if field == "value" else
                  f["observations"][0])
        target[field] = math.nextafter(1e12 if field == "value" else 1e6, math.inf)
        add(name, "one ULP above the size limit", f)

    f = base("R3_10_lock_extra")
    locked(f)
    f["lock"]["comment"] = "unapproved field"
    add(f["fixture_id"], "unknown lock key despite valid digests", f)
    f = base("R3_11_lock_type")
    f["lock"] = []
    add(f["fixture_id"], "nonobject lock is BAD_TYPE", f)
    f = base("R3_12_replay_types")
    request = dict(key="K", hid="H", family="F", variants=1, alpha=0, ts=1000)
    f["ledger_requests"] = [request, dict(request, alpha=0.0),
                            dict(request, variants=True), dict(request, variants=1.0),
                            dict(request, ts=1001)]
    add(f["fixture_id"], "canonical replay identity retains numeric and bool types", f)
    f = base("R3_13_numeric_ledger")
    f["ledger_requests"] = [dict(key=str(i), hid="H", family="F", variants=1,
                                  alpha=1e308, ts=1000) for i in range(2)]
    add(f["fixture_id"], "ledger overflow must remove all partial results", f)
    f = base("R3_14_underflow")
    for row in f["observations"]:
        row["ret"] *= 1e-200
    add(f["fixture_id"], "HAC underflow is INSUFFICIENT rather than NUMERIC_ERROR", f)
    f = base("R3_15_missing_id")
    del f["fixture_id"]
    add("R3_15_missing_id", "null output id and input-stem fallback", f)
    for name, raw in (("R3_16_bad_nan", b'{"ret":NaN}'),
                      ("R3_17_bad_inf", b'{"ret":Infinity}'),
                      ("R3_18_bad_json", b'{"incomplete":')):
        cases.append((name, "strict JSON parser fail closed", raw))
    f = base("R3_19_zero_funding")
    f["hypotheses"][0]["funding"] = True
    for row in f["observations"]:
        row["signals"]["s"]["value"] = 0
        row["funding"] = None
    add(f["fixture_id"], "missing funding counts even at zero position", f)
    f = base("R3_20_signal_offgrid")
    f["observations"] = [f["observations"][0]]
    f["observations"][0]["ts"] = 999
    add(f["fixture_id"], "UNKNOWN_SIGNAL checks raw observations, not filtered rows", f)
    f = base("R3_21_terminal_cost")
    f["hypotheses"][0]["cost_bps"] = 100
    for row in f["observations"][:-1]:
        row["signals"]["s"]["value"] = 0
    add(f["fixture_id"], "last bar entry is not automatically liquidated", f)
    f = base("R3_22_missing_future")
    f["observations"][0]["ret"] = None
    f["observations"][0]["signals"]["s"]["avail_ts"] += 1
    add(f["fixture_id"], "missing return suppresses future-signal count", f)
    f = base("R3_23_unicode_hash", 1)
    f["hypotheses"][0].update(hid="idé", family="fælles")
    f["ledger_requests"] = [dict(key="nøgle", hid="idé", family="fælles",
                                  variants=1, alpha=0.01, ts=1000)]
    add(f["fixture_id"], "UTF-8 canonical ledger preimage", f)
    return cases


def main():
    root = Path(__file__).resolve().parent
    target = root / "fixtures"
    target.mkdir(exist_ok=True)
    manifest = []
    for name, attack, raw in build_cases():
        path = target / (name + ".json")
        if path.exists() and path.read_bytes() != raw:
            raise RuntimeError("Refusing to rewrite an existing fixture: " + name)
        if not path.exists():
            path.write_bytes(raw)
        manifest.append(dict(file=path.name, attack=attack,
                             sha256=hashlib.sha256(raw).hexdigest(), phase="initial"))
    (root / "fixture_manifest.json").write_bytes(encode(manifest))


if __name__ == "__main__":
    main()
