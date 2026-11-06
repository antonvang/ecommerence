"""Deterministic synthetic fixtures for the EVALUATOR_SPEC v1 cross-check (director order 50 P3). Synthetic only.

    python3 research/desk/crosscheck/make_fixtures.py   # writes research/desk/synthetic_fixtures/*.json
"""
from __future__ import annotations

import json
import math
import os
import random

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "synthetic_fixtures")
H = 3600
T0 = 1_800_000_000 - (1_800_000_000 % H)


def base(fid, seed, n_bars, assets, ic=0.08, sigma=0.01):
    rng = random.Random(seed)
    obs = []
    for k in range(n_bars):
        ts = T0 + k * H
        for a in assets:
            z = rng.gauss(0, 1)
            noise = rng.gauss(0, 1)
            ret = sigma * (ic * z + math.sqrt(1 - ic * ic) * rng.gauss(0, 1))
            obs.append({"ts": ts, "asset": a, "ret": ret, "funding": rng.gauss(0.00001, 0.00003),
                        "signals": {"s_good": {"value": z, "avail_ts": ts},
                                    "s_noise": {"value": noise, "avail_ts": ts - H}}})
    return rng, {"fixture_id": fid, "cadence_s": H, "alpha": 0.05, "q_fdr": 0.10,
                 "window": {"start": T0, "end": T0 + n_bars * H},
                 "universe": {a: {"listed_from": T0, "delisted_at": None} for a in assets},
                 "hypotheses": [
                     {"hid": "H_good_sign", "family": "famA", "signal_key": "s_good", "rule": "sign",
                      "cost_bps": 5.0, "funding": False},
                     {"hid": "H_good_clip", "family": "famA", "signal_key": "s_good", "rule": "clip1",
                      "cost_bps": 5.0, "funding": True},
                     {"hid": "H_noise", "family": "famB", "signal_key": "s_noise", "rule": "sign",
                      "cost_bps": 2.0, "funding": False}],
                 "observations": obs,
                 "ledger_requests": [
                     {"key": "k1", "hid": "H_good_sign", "family": "famA", "variants": 1, "alpha": 0.0125, "ts": T0},
                     {"key": "k2", "hid": "H_good_clip", "family": "famA", "variants": 1, "alpha": 0.0, "ts": T0},
                     {"key": "k3", "hid": "H_noise", "family": "famB", "variants": 3, "alpha": 0.0125, "ts": T0}]}


def f1():
    return base("F1_clean", 101, 400, ["A1", "A2", "A3", "A4"])[1]


def f2():
    rng, f = base("F2_lookahead", 202, 400, ["A1", "A2", "A3", "A4"], ic=0.0)
    for o in f["observations"]:
        if rng.random() < 0.10:      # leaked: the signal equals the outcome but only becomes available after the bar
            o["signals"]["s_good"] = {"value": o["ret"], "avail_ts": o["ts"] + H}
    return f


def f3():
    rng, f = base("F3_gaps_nan", 303, 300, ["A1", "A2", "A3"])
    drop = {T0 + k * H for k in (10, 11, 12, 150, 299)}
    keep = []
    for o in f["observations"]:
        if o["ts"] in drop:
            continue
        u = rng.random()
        if u < 0.02:
            o["ret"] = None
        elif u < 0.03:
            o["ret"] = "NaN"
        elif u < 0.035:
            o["ret"] = "Infinity"
        elif u < 0.05:
            o["signals"]["s_good"]["value"] = None
        elif u < 0.055:
            del o["signals"]["s_noise"]
        if rng.random() < 0.05:
            o["funding"] = None if rng.random() < 0.5 else "NaN"
        keep.append(o)
    # one bar where rows exist but every return is missing (empty bar)
    for o in keep:
        if o["ts"] == T0 + 200 * H:
            o["ret"] = None
    f["observations"] = keep
    return f


def f4():
    rng, f = base("F4_survivorship", 404, 360, ["A1", "A2", "A3", "NEW", "DEAD"])
    f["universe"]["NEW"]["listed_from"] = T0 + 120 * H
    f["universe"]["DEAD"]["delisted_at"] = T0 + 240 * H
    keep = []
    for o in f["observations"]:
        if o["asset"] == "DEAD" and o["ts"] >= T0 + 240 * H:
            continue
        if o["asset"] == "DEAD" and o["ts"] == T0 + 239 * H:
            o["ret"] = -0.9                          # final collapse before delisting: must stay in the sample
            o["signals"]["s_good"]["value"] = 1.0
        keep.append(o)
    # rows for an asset that is not in the universe
    for k in range(0, 360, 7):
        keep.append({"ts": T0 + k * H, "asset": "GHOST", "ret": 0.05, "funding": 0.0,
                     "signals": {"s_good": {"value": 1.0, "avail_ts": T0 + k * H}}})
    f["observations"] = keep
    return f


def f5():
    rng, f = base("F5_extreme_dupes_offgrid", 505, 320, ["A1", "A2", "A3"])
    obs = f["observations"]
    extra = []
    for i in range(0, len(obs), 37):
        d = json.loads(json.dumps(obs[i]))
        d["ret"] = 0.3                               # duplicate rows: the first occurrence wins
        extra.append(d)
    for k in range(5, 320, 41):
        extra.append({"ts": T0 + k * H + 60, "asset": "A1", "ret": 0.2, "funding": 0.0,
                      "signals": {"s_good": {"value": 1.0, "avail_ts": T0}}})
    for i in (50, 400, 700):
        obs[i]["ret"] = 0.8 if i != 400 else -0.6
    obs[123]["signals"]["s_good"]["value"] = 0.0
    f["observations"] = obs + extra
    f["hypotheses"].append({"hid": "H_good_sign_copy", "family": "famA", "signal_key": "s_good", "rule": "sign",
                            "cost_bps": 9.0, "funding": False})
    f["ledger_requests"] += [
        {"key": "k1", "hid": "H_good_sign", "family": "famA", "variants": 1, "alpha": 0.0125, "ts": T0 + 1},
        {"key": "k4", "hid": "H_noise", "family": "famB", "variants": 1, "alpha": -0.01, "ts": T0 + 2},
        {"key": "k5", "hid": "H_noise", "family": "famB", "variants": 0, "alpha": 0.01, "ts": T0 + 3},
        {"key": "k6", "hid": "H_noise", "family": "famB", "variants": True, "alpha": 0.01, "ts": T0 + 4},
        {"key": "k7", "hid": "H_noise", "family": "famB", "variants": 2.5, "alpha": 0.01, "ts": T0 + 5},
        {"key": "k4", "hid": "H_noise", "family": "famB", "variants": 2, "alpha": 0.01, "ts": T0 + 6}]
    return f


def f6():
    return base("F6_short", 606, 25, ["A1", "A2"])[1]


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in (f1(), f2(), f3(), f4(), f5(), f6()):
        with open(os.path.join(OUT, f["fixture_id"] + ".json"), "w", encoding="utf-8") as fh:
            json.dump(f, fh, sort_keys=True, indent=None, separators=(",", ":"))
            fh.write("\n")
        print(f["fixture_id"], len(f["observations"]))


if __name__ == "__main__":
    main()
