"""Director order 90: the event farm SYNTHETIC driver (research/desk/EVENT_FARM_DRIVER_90.md).

It loads ONLY synthetic 1m fixtures, aggregates them to 5m and 15m, runs the frozen engine (research/tools/event_farm.py
at f686c9a, sha256 checked before import), checks the known_ts rules of EVENT_FARM_PLAN_88.md section 6, replays 5m/15m
setups on 1m (fill uncertainty) and returns a deterministic summary with provenance. It also holds the Register V2
records of the study (in code, never persisted) and the enumeration of all 315 tests.

FAIL-CLOSED DATA RULES (checked in this order; nothing is opened until every earlier step passed):
1. the manifest is a dict with exactly the keys of MANIFEST_KEYS, schema MANIFEST_SCHEMA and source == "synthetic";
2. the path is checked as a string only: no forbidden fragment (production cache, market cache, databases, quarantine,
   research/data, archives), basename synthetic_<name>.json, the manifest names that basename, and the path lies
   under an allowed root (research/desk/synthetic_fixtures or the system temp directory, or roots given by the caller);
3. only then is the path resolved (symlinks) and checked again;
4. the file is opened, its sha256 must equal the manifest's, its embedded provenance must equal the manifest's and every
   instrument name must start with "SYN".
Anything else raises DataSourceRefused. There is no switch that admits market data: a run on real data needs a new,
approved module (plan 88 section 4) and is not this driver.

UDKAST til forskning, ingen strategi: no lock, alpha, ledger row, status change or activation. No network, no file write
except write_fixture (synthetic, inside an allowed root).
"""
from __future__ import annotations

import collections
import hashlib
import importlib
import json
import math
import os
import re
import statistics
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ENGINE_PATH = os.path.join(HERE, "research", "tools", "event_farm.py")
ENGINE_COMMIT = "f686c9a"
ENGINE_SHA256 = "7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76"

STUDY_ID = "EVENT_FARM"
RESOLUTIONS = (60, 300, 900)                       # 1m as given, 5m and 15m aggregated
COST_GRID_BPS = (0.0, 1.0, 5.0, 8.0)
HORIZONS = (1, 3, 6, 12)
NULL_SEED, NULL_INSTRUMENTS, NULL_DAYS = 83, 3, 60  # the null is fixed (plan 88 section 9) and never redrawn

MANIFEST_SCHEMA = "event_farm_fixture_manifest/1"
FIXTURE_SCHEMA = "event_farm_fixture/1"
MANIFEST_KEYS = ("schema", "source", "generator", "seed", "fixture", "sha256")
NAME = re.compile(r"^synthetic_[A-Za-z0-9_-]{1,64}\.json$")
INSTRUMENT = re.compile(r"^SYN[A-Z0-9_]{0,16}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN = ("/home/anton/ecommerence/", "/ecommerence/copybot/data", "data/lab/", "/lab/market", "klines",
             "/quarantine", "quarantine/", "lab.db", "pm_lp.db", ".db", ".sqlite", "research/data", ".zip", ".csv",
             ".parquet", "/data/")

# P0: the study is related to existing reversal and trend lineages; it claims no independent lineage.
CLASSIFICATION = "RELATED_MECHANISM"
RELATED = {
    "liquidation_cascade_reversal": ["MOVESCREEN_m21c", "E_daily_reversal_p1", "L21_m2_liquidation_reversal"],
    "cross_sectional_momentum": ["L03_sol_trend_hourly", "L14_tsmom_v1", "E_donchian_trend_p1", "E_donchian_trend_p2"],
}
LINEAGE = ("event_farm (RELATED_MECHANISM: liquidation_cascade_reversal, cross_sectional_momentum; "
           "ingen selvstændig lineage, ingen uafhængighedspåstand)")


class DataSourceRefused(Exception):
    """A data source, manifest or path that is not an authorised synthetic fixture."""


class EngineMismatch(Exception):
    """event_farm.py is not the frozen version."""


# ---------------------------------------------------------------- engine and own provenance

def _sha_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def engine(path=None):
    """The engine module, after its sha256 equals the frozen one. Checked before import, so a changed file never runs."""
    path = path or ENGINE_PATH
    got = _sha_file(path)
    if got != ENGINE_SHA256:
        raise EngineMismatch(f"event_farm.py sha256 {got} is not {ENGINE_SHA256} ({ENGINE_COMMIT})")
    mod = importlib.import_module("research.tools.event_farm")
    if os.path.realpath(mod.__file__) != os.path.realpath(ENGINE_PATH):
        raise EngineMismatch(f"imported engine {mod.__file__} is not {ENGINE_PATH}")
    return mod


def driver_sha256():
    return _sha_file(os.path.abspath(__file__))


# ---------------------------------------------------------------- P0: tests and Register V2

def setup_test_ids():
    ef = engine()
    return ["default"] + [ef._variant_id(v) for v in ef.VARIANTS]


def event_test_ids():
    ef = engine()
    return [f"{k}@{h}" for k in ef.kinds() if not k.startswith("setup_") for h in HORIZONS]


def all_tests():
    """The 315 tests: 3 resolutions x (13 setup tests + 92 event-kind x horizon tests)."""
    out = []
    for bs in RESOLUTIONS:
        out += [f"{bs // 60}m/setup/{t}" for t in setup_test_ids()]
        out += [f"{bs // 60}m/event/{t}" for t in event_test_ids()]
    return out


def v2_records():
    """Two FUTURE records sharing one universe of 315 tests. variants_tested stays MISSING_INPUT: nothing has run on
    real data. The data source is the planned one (plan 88, access blocked); it is described, not opened."""
    from research.tools import factory, register_v2 as v2
    ef = engine()
    tests = all_tests()
    universe = {"definition": f"{len(tests)} tests: 3 opløsninger x (13 setup + 92 hændelse x horisont), én samlet "
                              "multiple-testing-eksponering", "size": len(tests), "members_sha256": factory.sha(tests)}
    values = {"study_id": STUDY_ID, "classification": CLASSIFICATION, "related_lineages": RELATED,
              "independent_lineage": False, "independent_discovery_claim": False, "status": "UDKAST, IKKE LÅST",
              "engine": {"commit": ENGINE_COMMIT, "sha256": ENGINE_SHA256},
              "defaults": {k: (list(v) if isinstance(v, tuple) else v) for k, v in sorted(ef.DEFAULTS.items())
                           if k != "sessions"} | {"sessions": [list(s) for s in ef.DEFAULTS["sessions"]]},
              "resolutions_s": list(RESOLUTIONS), "cost_grid_bps": list(COST_GRID_BPS), "n_tests": len(tests),
              "activated": False, "alpha": 0}
    src = {"name": "explore0 1m BTCUSDT/ETHUSDT 2020-03..2021-12 (planlagt; tidligere eksponeret; adgang blokeret)",
           "sha256": factory.sha({"plan": "EVENT_FARM_PLAN_88.md", "files": 44, "window": ["2020-03", "2021-12"]})}
    cost = {"name": "rundturgitter 0/1/5/8 bps (8 = 2 x 0,040 %)", "round_trip_bps": 8.0,
            "sha256": factory.sha(list(COST_GRID_BPS))}
    recs = []
    for rid, n, method in (("EVENT_FARM_EXPLORE0_SETUPS", 3 * len(setup_test_ids()), "P1-P5 beskrivende; R kun bilag"),
                           ("EVENT_FARM_EXPLORE0_EVENTS", 3 * len(event_test_ids()), "hændelsesfrekvens og afkast i ATR")):
        recs.append(v2.record(
            rid, v2.FUTURE, hypothesis_id=f"{STUDY_ID}:{rid}", lineage=LINEAGE, trial_universe=universe,
            variants_tested=None, parameters=v2.parameters_block({**values, "family_tests": n}),
            code_hash=ENGINE_SHA256, data_source=src, data_period={"start": "2020-03-01", "end": "2021-12-31"},
            cost_model=cost, evaluation_method={"name": method, "sha256": factory.sha(method)},
            data_quality={"status": "NOT_CHECKED"}, deviations=[]))
    return recs


# ---------------------------------------------------------------- fail-closed loading

def _roots(roots):
    base = roots if roots is not None else (os.path.join(HERE, "research", "desk", "synthetic_fixtures"),
                                             tempfile.gettempdir())
    return [os.path.normpath(os.path.abspath(r)) for r in base]


def _check_manifest(manifest):
    if not isinstance(manifest, dict):
        raise DataSourceRefused("no provenance manifest: refused")
    if sorted(manifest) != sorted(MANIFEST_KEYS):
        raise DataSourceRefused(f"manifest keys {sorted(manifest)} are not {sorted(MANIFEST_KEYS)}: refused")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise DataSourceRefused("unknown manifest schema: refused")
    if manifest["source"] != "synthetic":
        raise DataSourceRefused(f"source {manifest['source']!r} is not 'synthetic': refused")
    if not isinstance(manifest["generator"], str) or not manifest["generator"].strip() or type(manifest["seed"]) is not int:
        raise DataSourceRefused("manifest needs a generator name and an integer seed")
    if not isinstance(manifest["sha256"], str) or not HEX64.match(manifest["sha256"]):
        raise DataSourceRefused("manifest sha256 is not a sha256")
    if not isinstance(manifest["fixture"], str) or not NAME.match(manifest["fixture"]):
        raise DataSourceRefused("manifest fixture name is not synthetic_<name>.json")


def _check_path_string(path, manifest, roots):
    """String checks only: no stat, open or resolve happens here."""
    if not isinstance(path, str) or not path:
        raise DataSourceRefused("no path")
    norm = os.path.normpath(os.path.abspath(path))
    low = norm.lower() + "/"
    for frag in FORBIDDEN:
        if frag in low:
            raise DataSourceRefused(f"path contains forbidden fragment {frag!r}: refused unopened")
    base = os.path.basename(norm)
    if not NAME.match(base):
        raise DataSourceRefused(f"{base!r} is not synthetic_<name>.json: refused unopened")
    if base != manifest["fixture"]:
        raise DataSourceRefused("the manifest names another fixture: refused unopened")
    if not any(norm.startswith(r + os.sep) for r in roots):
        raise DataSourceRefused("path is outside the allowed synthetic roots: refused unopened")
    return norm


def load_fixture(path, manifest, roots=None):
    """The 1m bars of an authorised synthetic fixture, as {instrument: [(ts, o, h, l, c, v), ...]}, and its provenance."""
    _check_manifest(manifest)
    rts = _roots(roots)
    norm = _check_path_string(path, manifest, rts)
    real = os.path.realpath(norm)
    if real != norm:
        _check_path_string(real, manifest, rts)
    with open(real, "rb") as f:
        raw = f.read()
    if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
        raise DataSourceRefused("fixture sha256 differs from the manifest: refused")
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("schema") != FIXTURE_SCHEMA:
        raise DataSourceRefused("unknown fixture schema: refused")
    prov = doc.get("provenance")
    if prov != {"source": "synthetic", "generator": manifest["generator"], "seed": manifest["seed"]}:
        raise DataSourceRefused("embedded provenance differs from the manifest: refused")
    bars = doc.get("bars_1m")
    if not isinstance(bars, dict) or not bars:
        raise DataSourceRefused("no bars")
    out = {}
    for name in sorted(bars):
        if not INSTRUMENT.match(name):
            raise DataSourceRefused(f"instrument {name!r} is not a synthetic name (SYN...): refused")
        out[name] = [tuple(r) for r in bars[name]]
    return out, {**manifest, "path_basename": os.path.basename(real)}


def synthetic_1m(seed, days):
    """A synthetic 1m random walk with the engine's per-5m volatility (sigma per 1m bar = 0.0011 / sqrt 5)."""
    ef = engine()
    return ef.random_walk_bars(seed, days, bar_seconds=60, sub_steps=12, sigma_bar=ef.NULL_SIGMA_BAR / math.sqrt(5))


def write_fixture(directory, name, bars_by_inst, generator, seed, roots=None):
    """Write a synthetic fixture (only inside an allowed root) and return (path, manifest)."""
    path = os.path.join(directory, name)
    probe = {"schema": MANIFEST_SCHEMA, "source": "synthetic", "generator": generator, "seed": seed, "fixture": name,
             "sha256": "0" * 64}
    _check_manifest(probe)
    _check_path_string(path, probe, _roots(roots))
    for inst in bars_by_inst:
        if not INSTRUMENT.match(inst):
            raise DataSourceRefused(f"instrument {inst!r} is not a synthetic name")
    doc = {"schema": FIXTURE_SCHEMA, "provenance": {"source": "synthetic", "generator": generator, "seed": seed},
           "bars_1m": {k: [list(b) for b in v] for k, v in sorted(bars_by_inst.items())}}
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    with open(path, "wb") as f:
        f.write(raw)
    return path, {**probe, "sha256": hashlib.sha256(raw).hexdigest()}


# ---------------------------------------------------------------- aggregation

def aggregate(bars_1m, bs):
    """1m -> bs-second bars. A bucket needs all bs/60 minutes, else it is dropped and counted; nothing is interpolated.
    Refuses ts off the minute grid, duplicates and unordered input."""
    if bs % 60 or bs < 60:
        raise ValueError("bs must be a positive multiple of 60")
    prev = None
    for b in bars_1m:
        if b[0] % 60:
            raise ValueError(f"ts {b[0]} is not on the minute grid")
        if prev is not None and b[0] <= prev:
            raise ValueError(f"ts {b[0]} is a duplicate or out of order")
        prev = b[0]
    need = bs // 60
    buckets = collections.OrderedDict()
    for b in bars_1m:
        buckets.setdefault(b[0] // bs * bs, []).append(b)
    out, dropped, minutes_dropped = [], 0, 0
    for start, mins in buckets.items():
        if len(mins) != need:
            dropped += 1
            minutes_dropped += len(mins)
            continue
        out.append((start, mins[0][1], max(m[2] for m in mins), min(m[3] for m in mins), mins[-1][4],
                    math.fsum(m[5] for m in mins)))
    return out, {"buckets": len(buckets), "kept": len(out), "dropped": dropped, "minutes_in_dropped": minutes_dropped}


# ---------------------------------------------------------------- known_ts rules (plan 88 section 6)

def known_ts_violations(events, setups, outcomes, bars, bs):
    v = []
    for e in list(events) + list(setups):
        k = e["known_i"]
        if not 0 <= k < len(bars) or e["known_ts"] != bars[k][0] + bs:
            v.append((e["kind"], k, "known_ts is not the close of bar known_i"))
        if e["i"] > k or e["ts"] > e["known_ts"] - bs:
            v.append((e["kind"], k, "pattern after known"))
    for s, o in zip(setups, outcomes):
        if not (s["sweep_known_i"] <= s["break_known_i"] and s["anchor_known_i"] <= s["break_known_i"]
                and s["anchor_known_i"] >= s["i"]):
            v.append((s["kind"], s["known_i"], "chain order"))
        if o["fill_i"] is not None:
            if o["fill_i"] < s["known_i"] or (s["entry_mode"] != "market" and o["fill_i"] <= s["known_i"]):
                v.append((s["kind"], s["known_i"], "fill before known"))
            if o["exit_i"] is not None and o["exit_i"] < o["fill_i"]:
                v.append((s["kind"], s["known_i"], "exit before fill"))
    return v


# ---------------------------------------------------------------- 1m replay of 5m / 15m setups

def replay_1m(setup, bars_1m, idx_1m, bs, p):
    """The same entry, stop and target on 1m from the first minute after known_ts; windows times bs/60."""
    ef = engine()
    last = setup["known_ts"] - 60
    if last not in idx_1m:
        return {"status": "incomplete"}
    s = dict(setup, known_i=idx_1m[last])
    pr = ef.params(**{**p, "bar_seconds": 60, "fill_window": p["fill_window"] * bs // 60,
                      "max_hold": p["max_hold"] * bs // 60})
    return ef.setup_outcome(s, bars_1m, pr)


# ---------------------------------------------------------------- the run

def _variant_params(ef, bs, test_id):
    base = {"bar_seconds": bs}
    if test_id == "default":
        return ef.params(**base)
    v = next(v for v in ef.VARIANTS if ef._variant_id(v) == test_id)
    return ef.params(**{**base, **v})


def _touch_only(s, o, bars):
    if o["fill_i"] is None or s["entry_mode"] == "market":
        return False
    b = bars[o["fill_i"]]
    return b[3] == s["entry"] if s["dir"] > 0 else b[2] == s["entry"]


def run_bars(bars_1m_by_inst, provenance, resolutions=RESOLUTIONS, lookahead_slices=3, lookahead_bars=2000, n_checks=20,
             replay=True):
    """The driver on in-memory 1m bars whose provenance says source 'synthetic'. Raises on any known_ts violation or
    truncation failure (plan 88 section 10: stop before results)."""
    if not isinstance(provenance, dict) or provenance.get("source") != "synthetic":
        raise DataSourceRefused("provenance is not synthetic: refused")
    for name in bars_1m_by_inst:
        if not INSTRUMENT.match(name):
            raise DataSourceRefused(f"instrument {name!r} is not a synthetic name (SYN...): refused")
    ef = engine()
    from research.tools import factory, validation_engine as ve
    tests_setup, tests_event = setup_test_ids(), event_test_ids()
    days_by = {n: sorted({ef._day(b[0]) for b in bars}) for n, bars in bars_1m_by_inst.items()}
    inst_days = sum(len(d) for d in days_by.values())
    idx_1m = {n: {b[0]: i for i, b in enumerate(bars)} for n, bars in bars_1m_by_inst.items()}
    out = {"provenance": {"source": "synthetic", "input": dict(sorted(provenance.items())),
                          "engine": {"commit": ENGINE_COMMIT, "sha256": ENGINE_SHA256},
                          "driver_sha256": driver_sha256(), "study_id": STUDY_ID,
                          "label": "SYNTETISK - ikke markedsdata; beskrivende, ingen strategi"},
           "instruments": sorted(bars_1m_by_inst), "instrument_days": inst_days, "resolutions": {}}
    for bs in resolutions:
        res = {"gaps": {}, "bars": 0, "P1": {}, "P2": {}, "P3": {}, "P4": {}, "P5": {}, "R": {}, "events_secondary": {}}
        kinds_tot = collections.Counter()
        per_test = {t: {"setups": 0, "status": collections.Counter(), "both": 0, "touch": 0, "filled": 0,
                        "gross": [], "cost_r": [], "switch": collections.Counter(), "daily": collections.Counter()}
                    for t in tests_setup}
        ev_ret = collections.defaultdict(list)
        chain_stats = collections.Counter()
        violations, look = [], []
        for name in sorted(bars_1m_by_inst):
            b1 = bars_1m_by_inst[name]
            ef.check_bars(b1)
            bars, gap = (aggregate(b1, bs) if bs != 60 else aggregate(b1, 60))
            res["gaps"][name] = gap
            res["bars"] += len(bars)
            p0 = ef.params(bar_seconds=bs)
            events = ef.detect(bars, p0)
            kinds_tot.update(e["kind"] for e in events)
            for e in events:
                o = ef.event_outcome(e, bars, p0)
                for h in HORIZONS:
                    r = o["ret_atr"].get(h)
                    if r is not None:
                        ev_ret[f"{e['kind']}@{h}"].append(r)
            for t in tests_setup:
                pv = _variant_params(ef, bs, t)
                setups, stats = ef.build_setups(events, bars, pv)
                if t == "default":
                    chain_stats.update(stats)
                outs = [ef.setup_outcome(s, bars, pv) for s in setups]
                violations += known_ts_violations(events if t == "default" else [], setups, outs, bars, bs)
                d = per_test[t]
                d["setups"] += len(setups)
                for s, o in zip(setups, outs):
                    d["status"][o["status"]] += 1
                    if o["fill_i"] is not None:
                        d["filled"] += 1
                        d["touch"] += _touch_only(s, o, bars)
                    if o["gross_r"] is not None:
                        d["both"] += o["both_hit_bars"] > 0
                        d["gross"].append(o["gross_r"])
                        d["cost_r"].append(1e-4 * s["entry"] / s["risk"])
                        d["daily"][ef.known_day(s, bs)] += o["net_r"]
                    if replay and bs != 60:
                        d["switch"][f"{o['status']}->{replay_1m(s, b1, idx_1m[name], bs, pv)['status']}"] += 1
            n = len(bars)
            starts = sorted({0, max(0, n // 2 - lookahead_bars // 2), max(0, n - lookahead_bars)})[:lookahead_slices]
            for st in starts:
                chunk = bars[st:st + lookahead_bars]
                if len(chunk) >= 3:
                    look.append(ve.check_lookahead(signal_fn=ef.lookahead_signal(p0), data=chunk, n_checks=n_checks))
        res["P3"] = {"violations": len(violations), "first": violations[:5],
                     "lookahead": [c["status"] for c in look],
                     "lookahead_ok": all(c["status"] == ve.PASS for c in look)}
        if violations or not res["P3"]["lookahead_ok"]:
            raise RuntimeError(f"known_ts rules broken at {bs}s: {res['P3']} - stop before results")
        res["P1"] = {k: {"per_instrument_day": kinds_tot[k] / max(1, inst_days),
                         "per_1000_bars": 1000 * kinds_tot[k] / max(1, res["bars"])} for k in sorted(kinds_tot)}
        res["P2"] = {"chain_stats_default": dict(sorted(chain_stats.items())),
                     "setups_per_instrument_day": {t: per_test[t]["setups"] / max(1, inst_days) for t in tests_setup}}
        for t in tests_setup:
            d = per_test[t]
            tot = max(1, d["setups"])
            res["P4"][t] = {k: v / tot for k, v in sorted(d["status"].items())}
            traded = max(1, len(d["gross"]))
            res["P5"][t] = {"both_hit_share": d["both"] / traded, "touch_only_fill_share": d["touch"] / max(1, d["filled"]),
                            "replay_1m": dict(sorted(d["switch"].items())),
                            "replay_switch_share": (sum(v for k, v in d["switch"].items()
                                                        if k.split("->")[0] != k.split("->")[1]) / max(1, d["setups"])
                                                    if d["switch"] else None)}
            res["R"][t] = {"trades": len(d["gross"]),
                           "mean_gross_r": statistics.fmean(d["gross"]) if d["gross"] else None,
                           "mean_net_r": {f"{c:g}": (statistics.fmean([g - c * k for g, k in zip(d["gross"], d["cost_r"])])
                                                     if d["gross"] else None) for c in COST_GRID_BPS}}
        res["events_secondary"] = {t: {"n": len(ev_ret[t]), "mean_ret_atr": statistics.fmean(ev_ret[t]) if ev_ret[t] else None}
                                   for t in tests_event}
        day_keys = sorted({d for t in tests_setup for d in per_test[t]["daily"]} | {d for ds in days_by.values() for d in ds})
        series = [[per_test[t]["daily"][d] for d in day_keys] for t in tests_setup]
        mt = ve.check_multiple_testing(series=series, time_index=list(range(len(day_keys))), n_tested=315,
                                       n_preregistered=315, reps=199, seed=85)
        res["multiple_testing"] = {"status": mt["status"], "reason": mt["reason"], "n_used": mt["metrics"].get("n_used")}
        out["resolutions"][f"{bs // 60}m"] = res
    out["result_sha256"] = factory.sha(json.loads(json.dumps(out, sort_keys=True)))
    return out


def run_fixture(path, manifest, roots=None, **kw):
    bars, prov = load_fixture(path, manifest, roots)
    return run_bars(bars, prov, **kw)


def null_reference(resolutions=RESOLUTIONS, instruments=NULL_INSTRUMENTS, days=NULL_DAYS):
    """The fixed engine null (seed 83) per resolution; the seed is not a parameter. Counts and pooled gross R only."""
    ef = engine()
    out = {}
    for bs in resolutions:
        s = ef.null_run(seed=NULL_SEED, instruments=instruments, days=days, p={"bar_seconds": bs})
        out[f"{bs // 60}m"] = {"seed": s["seed"], "instruments": s["instruments"], "days": s["days"], "bars": s["bars"],
                               "events_per_instrument_day": s["events_per_instrument_day"],
                               "pooled_mean_gross_r": s["pooled_mean_gross_r"], "pooled_trades": s["pooled_trades"]}
    return out


def summary_markdown(out):
    pv = out["provenance"]
    lines = [f"# Event farm driver ({pv['label']})", "",
             f"- kilde: {pv['source']}; input: {pv['input'].get('generator')} seed {pv['input'].get('seed')}",
             f"- motor {pv['engine']['commit']} sha256 {pv['engine']['sha256']}; driver sha256 {pv['driver_sha256']}",
             f"- resultat sha256 {out['result_sha256']}", ""]
    for r, res in out["resolutions"].items():
        lines.append(f"## {r}: {res['bars']} barer, huller {sum(g['dropped'] for g in res['gaps'].values())} spande, "
                     f"known_ts-brud {res['P3']['violations']}, lookahead {'/'.join(res['P3']['lookahead'])}")
        sp = res["P2"]["setups_per_instrument_day"]
        lines.append(f"- setups pr. instrument-dag (standard): {sp['default']:.2f}; kæder {res['P2']['chain_stats_default']}")
        lines.append(f"- multiple testing (N = 315): {res['multiple_testing']['status']}")
        lines.append("")
    return "\n".join(lines)


__all__ = ["run_fixture", "run_bars", "load_fixture", "write_fixture", "aggregate", "replay_1m", "known_ts_violations",
           "v2_records", "all_tests", "null_reference", "engine", "DataSourceRefused", "EngineMismatch"]
