"""Experiment pipeline (Mission 6): discovery -> registration -> data -> backtest -> cost check -> adversarial ->
validation -> report, and the sealed holdout after a human approval.

Every step is a persistent job (lab/jobs.py) handled by one agent role. Each step writes a content-addressed artifact
(data/lab/artifacts/<exp>/<step>.json, SHA-256 in the job result and in the registry evidence). Display stages map to
lifecycle states plus the step that is queued or running (see STAGE_OF in lab/mission.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
from datetime import datetime, timezone

from lab import jobs, lifecycle, registry, templates
from lab.data import Gateway
from lab.db import HERE
from lab.engine import adversarial, backtest, catalogue, data

ARTIFACTS = os.path.join(HERE, "data", "lab", "artifacts")
REPORTS = os.path.join(HERE, "data", "lab", "reports")
STEPS = ("data", "backtest", "cost", "adversarial", "validate", "report")
ALPHA_PER_EXPERIMENT = 0.005
SEED = 7
PLACEBO_N = 60
DOWNLOAD_THREADS = 8
ENGINE_CODE = ["lab/engine/catalogue.py", "lab/engine/backtest.py", "lab/engine/adversarial.py", "lab/engine/data.py",
               "lab/pipeline.py"]


class StepError(Exception):
    pass


class ArtifactError(StepError):
    """A frozen artifact is missing, unrecorded or differs from its recorded SHA-256: fail closed, never regenerate."""


# ---------- artifacts ----------
def save_artifact(exp_id, name, obj):
    os.makedirs(os.path.join(ARTIFACTS, exp_id), exist_ok=True)
    raw = json.dumps(obj, sort_keys=True, default=str).encode()
    path = os.path.join(ARTIFACTS, exp_id, f"{name}.json")
    with open(path + ".part", "wb") as f:
        f.write(raw)
    os.replace(path + ".part", path)
    return {"path": os.path.relpath(path, HERE).replace("\\", "/"), "sha256": hashlib.sha256(raw).hexdigest()}


def load_artifact(exp_id, name):
    with open(os.path.join(ARTIFACTS, exp_id, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def recorded_sha(db, exp_id, name):
    """The SHA-256 recorded when step `name` of `exp_id` finished: the hash-chained job.done event (newer runs), else
    the job's stored result (runs before the hash was chained). None if nothing was recorded."""
    jid = f"{name}|{exp_id}"
    for r in db.q("SELECT payload FROM events WHERE kind='job.done' AND exp_id=? ORDER BY id DESC", exp_id):
        p = json.loads(r["payload"])
        if p.get("job_id") == jid and p.get("artifact_sha256"):
            return p["artifact_sha256"]
    j = db.one("SELECT status, result FROM jobs WHERE job_id=?", jid)
    if j and j["status"] == "done" and j["result"]:
        return ((json.loads(j["result"]) or {}).get("artifact") or {}).get("sha256")
    return None


def frozen_artifact(db, exp_id, name):
    """Load a frozen artifact only if its bytes match the recorded SHA-256 (fail closed otherwise)."""
    path = os.path.join(ARTIFACTS, exp_id, f"{name}.json")
    want = recorded_sha(db, exp_id, name)
    if want is None:
        raise ArtifactError(f"{exp_id}/{name}.json has no recorded SHA-256")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        raise ArtifactError(f"{exp_id}/{name}.json is missing (frozen parameters are never regenerated)") from None
    if hashlib.sha256(raw).hexdigest() != want:
        raise ArtifactError(f"{exp_id}/{name}.json differs from its recorded SHA-256")
    return json.loads(raw)


def frozen_variant(db, exp_id):
    cost = frozen_artifact(db, exp_id, "cost")
    return frozen_artifact(db, exp_id, "backtest")["variants"][cost["selected"]]


# ---------- discovery and registration ----------
def discover_catalogue(db, actor="discovery-catalogue"):
    """Propose every catalogue template that is not in the registry yet (graveyard applies in registry.discover)."""
    out = []
    for t, tpl in catalogue.TEMPLATES.items():
        eid = catalogue.exp_id(t)
        if db.one("SELECT 1 FROM experiments WHERE exp_id=?", eid):
            continue
        st, dup = registry.discover(db, eid, tpl["hypothesis"], tpl["mechanism_tag"], catalogue.instrument_family(t),
                                    catalogue.HORIZON[t], "taker", "lab/engine/catalogue.py", actor,
                                    extra={"template": t, "title": t.replace("_", " "), "discovered_by": actor,
                                           "reason": tpl["rationale"], "evidence": tpl["evidence"],
                                           "data_requirements": ["Binance USD-M 1h klines", "funding rates"]})
        out.append((eid, st, dup))
    return out


def _windows(protocol):
    keys = {"train": "train3", "validation": "validation3", "holdout": "holdout"} if protocol >= 3 else \
        {"train": "train", "validation": "validation", "holdout": "holdout"}
    return {k: [f"{data.SPLITS[v][0][0]}-{data.SPLITS[v][0][1]:02d}", f"{data.SPLITS[v][1][0]}-{data.SPLITS[v][1][1]:02d}"]
            for k, v in keys.items()}


def template_spec(t):
    tpl = catalogue.TEMPLATES[t]
    proto = catalogue.protocol_of(t)
    needs = tpl.get("needs") or []
    extra_sources = [x for k, x in (("metrics", "Binance futures/um daily metrics (open interest, long/short ratios)"),
                                    ("taker", "Binance klines column 11 (taker buy quote volume)"),
                                    ("dvol", "Deribit public get_volatility_index_data (DVOL, daily)"),
                                    ("stable", "DefiLlama stablecoincharts/all (window rows only)")) if k in needs]
    return {"template": t, "title": t.replace("_", " "), "hypothesis": tpl["hypothesis"], "mechanism": tpl["rationale"],
            "mechanism_tag": tpl["mechanism_tag"], "evidence": tpl["evidence"],
            "sources": ["lab/engine/catalogue.py"] + tpl["evidence"], "instrument": catalogue.instrument_family(t),
            "universe": list(catalogue.universe(t)), "min_symbols": catalogue.min_symbols(t), "timeframe": "1h",
            "horizon": catalogue.HORIZON[t], "execution": "taker",
            "long_only": tpl["long_only"],
            "datasets": {"source": "https://data.binance.vision (futures/um monthly klines 1h + fundingRate)",
                         "extra_sources": extra_sources, "splits": _windows(proto),
                         "reserved_from": "2025-01-01 (never read)"},
            "grid": tpl["grid"], "methodology": catalogue.PROTOCOLS[proto], "baseline": "equal-weight buy-and-hold of "
            "the same universe with the same costs and funding", "costs": catalogue.COSTS,
            "acceptance": catalogue.PROTOCOLS[proto]["validation"],
            "rejection": "train gate, pre-validation gate or any validation gate fails ("
                         + catalogue.PROTOCOLS[proto].get("spec", "research/PROTOCOL_V2.md") + ")",
            "alpha": ALPHA_PER_EXPERIMENT, "code": ENGINE_CODE, "seed": SEED,
            "protocol_version": proto, "observation_test": bool(tpl.get("observation")),
            "label": "EXPLORATORY until a sealed holdout passes"}


def register(db, eid, actor="strategy-1"):
    """Register one instance as a batch of one (see register_batch)."""
    return bool(register_batch(db, [eid], actor))


def _template(db, eid):
    t = json.loads(registry.latest(db, eid)["spec_json"] or "{}").get("template")
    if not t:
        raise StepError(f"{eid} is not a catalogue instance")
    return t


def register_batch(db, eids, actor="strategy-1"):
    """PROTOCOL v2 batch: register every approved instance in `eids` together. Logs `batch.registered` with the
    trials-ledger cutoff, then queues the jobs so that no member validates before every member finished its cost step.
    Instances without a valid template approval are skipped. Returns the registered ids."""
    blob = templates.catalogue_blob()
    ok = sorted(e for e in eids if templates.approval(db, _template(db, e), blob) is not None)
    if not ok:
        return []
    for eid in ok:
        _register_one(db, eid, actor)
    cutoff = db.one("SELECT COALESCE(MAX(id),0) FROM trials")[0]
    batch = "B-" + hashlib.sha256("|".join(ok).encode()).hexdigest()[:12]
    db.event("batch.registered", f"system:{actor}", None, {"batch": batch, "exp_ids": ok, "trial_cutoff_id": cutoff,
                                                          "protocol_version": max(catalogue.protocol_of(
                                                              _template(db, e)) for e in ok)})
    for eid in ok:
        enqueue_pipeline(db, eid, actor, batch_members=ok)
    return ok


def _register_one(db, eid, actor):
    v = registry.latest(db, eid)
    t = _template(db, eid)
    if v["version"] == 1:
        commit = registry.last_commit(templates.CATALOGUE)
        with db.tx():
            db.append("experiments", exp_id=eid, version=2, created_ts=int(time.time()),
                      mechanism_tag=v["mechanism_tag"], fingerprint=v["fingerprint"], spec_json=template_spec(t),
                      spec_path=templates.CATALOGUE, spec_commit=commit,
                      code_hash=registry.blob_at(commit, templates.CATALOGUE), note=f"template {t} spec")
            db.append("alpha_ledger", exp_id=eid, ts=int(time.time()), alpha=ALPHA_PER_EXPERIMENT,
                      note="exploratory screening")
            db.event("exp.version_added", actor, eid, {"version": 2, "template": t})
    templates.register_transition(db, eid, t, f"system:{actor}")


def enqueue_pipeline(db, eid, actor="strategy-1", batch_members=()):
    """Chain the steps. Under v2 the validate step also waits for the cost step of every batch member."""
    prio = 20 + list(catalogue.TEMPLATES).index(json.loads(registry.latest(db, eid)["spec_json"])["template"])
    prev = []
    for s in STEPS:
        deps = list(prev)
        if s == "validate":
            deps += [f"cost|{m}" for m in batch_members if m != eid]
        jobs.enqueue(db, f"{s}|{eid}", s, eid, {"exp_id": eid}, priority=prio, depends_on=deps,
                     timeout_s=900 if s in ("backtest", "adversarial", "validate") else 300, actor=f"system:{actor}")
        prev = [f"{s}|{eid}"]


def _v2(spec):
    return (spec.get("protocol_version") or 1) >= 2


def batch_of(db, eid):
    """The batch.registered payload that contains eid, or None (v1 experiments have no batch)."""
    for r in db.q("SELECT payload FROM events WHERE kind='batch.registered' ORDER BY id DESC"):
        p = json.loads(r["payload"])
        if eid in p["exp_ids"]:
            return p
    return None


def dsr_trials(db, eid, spec):
    """v1: every trial recorded so far. v2: trials up to the batch cutoff plus the batch's own trials."""
    if not _v2(spec):
        return [r[0] for r in db.q("SELECT sharpe_daily FROM trials WHERE sharpe_daily IS NOT NULL")]
    b = batch_of(db, eid)
    if b is None:
        raise StepError(f"{eid} has no registered batch (PROTOCOL v2 requires one)")
    q = (f"SELECT sharpe_daily FROM trials WHERE sharpe_daily IS NOT NULL AND (id<=? OR exp_id IN "
         f"({','.join('?' * len(b['exp_ids']))})) ORDER BY id")
    return [r[0] for r in db.q(q, b["trial_cutoff_id"], *b["exp_ids"])]


# ---------- helpers ----------
def _spec(db, eid):
    return json.loads(registry.latest(db, eid)["spec_json"])


def _files(db, eid, split, worker, symbols=None):
    """Download/reuse the split's files (parallel threads) and record the read through the gateway (state rules apply)."""
    from concurrent.futures import ThreadPoolExecutor
    symbols = symbols or catalogue.universe(_spec(db, eid)["template"])
    with ThreadPoolExecutor(DOWNLOAD_THREADS) as ex:
        got = list(ex.map(lambda s: (s, data.files_for(s, split)), symbols))
    per_sym, all_files = {}, []
    for s, f in got:
        per_sym[s] = f
        all_files += f["klines"] + f["funding"]
    Gateway(db, f"system:{worker}").access(eid, data.GATEWAY_SPLIT[split],
                                           [os.path.join(HERE, p) if not os.path.isabs(p) else p for p in all_files],
                                           data.window(split), "https://data.binance.vision", "evaluate",
                                           registry.blob_at(registry.last_commit(templates.CATALOGUE), templates.CATALOGUE))
    return per_sym


def _load(per_sym, split):
    bars, funding, dups = {}, {}, {}
    for s, f in per_sym.items():
        bars[s], funding[s], dups[s] = data.load(f, split)
    return bars, funding, dups


V3_SPLITS = {"train": "train3", "validation": "validation3", "holdout": "holdout"}


def _sp(spec, split):
    """Logical split -> data window of the experiment's protocol (v3 uses longer windows)."""
    return V3_SPLITS.get(split, split) if (spec.get("protocol_version") or 1) >= 3 else split


def _code_hash():
    return registry.blob_at(registry.last_commit(templates.CATALOGUE), templates.CATALOGUE)


def _extra(db, eid, split, worker, symbols, per_sym, needs, tpl=None):
    """PROTOCOL v3 data bundle: hourly volume/taker, daily metrics, DVOL, stablecoins; reads go through the gateway."""
    from concurrent.futures import ThreadPoolExecutor
    gw, win, b = Gateway(db, f"system:{worker}"), data.window(split), {}
    if "volume" in needs:
        b["volume"] = {s: data.load_volume(per_sym[s], split) for s in per_sym}
    if "taker" in needs:
        b["taker"] = {s: data.load_taker(per_sym[s], split) for s in per_sym}
    if "metrics" in needs:
        with ThreadPoolExecutor(4) as ex:
            paths = dict(zip(symbols, ex.map(lambda s: data.metrics_for(s, split), symbols)))
        gw.access(eid, data.GATEWAY_SPLIT[split], list(paths.values()), win, data.METRICS_URL, "evaluate", _code_hash())
        b["metrics"] = {s: data.load_metrics(p) for s, p in paths.items()}
    if "dvol" in needs:
        curs = sorted({s.replace("USDT", "") for s in symbols})
        paths = {c: data.dvol_for(c, split) for c in curs}
        gw.access(eid, data.GATEWAY_SPLIT[split], list(paths.values()), win, "https://www.deribit.com/api/v2/public",
                  "evaluate", _code_hash())
        b["dvol"] = {c: data.load_days(p) for c, p in paths.items()}
    if "rates" in needs:
        p = data.fred_for("DFII10", split)
        gw.access(eid, data.GATEWAY_SPLIT[split], [p], win, "https://fred.stlouisfed.org", "evaluate", _code_hash())
        b["rates"] = data.load_days(p)
    if "cm" in needs:
        b["cm"] = {}
        for metric in (tpl or {}).get("cm_metrics", []):
            p = data.cm_for(metric, split, symbols)
            gw.access(eid, data.GATEWAY_SPLIT[split], [p], win, "https://community-api.coinmetrics.io", "evaluate",
                      _code_hash())
            b["cm"][metric] = data.load_cm(p)
    if "stable" in needs:
        p = data.stable_for(split)
        gw.access(eid, data.GATEWAY_SPLIT[split], [p], win, "https://stablecoins.llama.fi", "evaluate", _code_hash())
        b["stable"] = data.load_days(p)
    return b


def _market(db, eid, split, worker, spec, exclude=()):
    """Bars, funding, duplicates and the template's extra data (hourly volume for the older 30-coin templates, or the
    PROTOCOL v3 bundle), without the symbols excluded by the data rule."""
    split = _sp(spec, split)
    tpl = catalogue.TEMPLATES[spec["template"]]
    symbols = catalogue.universe(spec["template"])
    per_sym = _files(db, eid, split, worker, symbols)
    bars, funding, dups = _load(per_sym, split)
    if tpl.get("needs_volume"):
        vol = {s: data.load_volume(per_sym[s], split) for s in per_sym}
    elif tpl.get("needs"):
        vol = _extra(db, eid, split, worker, symbols, per_sym, tpl["needs"], tpl)
    else:
        vol = None
    for s in exclude:
        for d in (bars, funding, dups):
            d.pop(s, None)
        if vol is not None and tpl.get("needs_volume"):
            vol.pop(s, None)
        elif vol is not None:
            for k in ("volume", "taker", "metrics"):
                (vol.get(k) or {}).pop(s, None)
            for per in (vol.get("cm") or {}).values():
                per.pop(s, None)
    return bars, funding, dups, vol


def _train(db, eid, worker, spec):
    excluded = (load_artifact(eid, "data").get("excluded") or {}).get("train", [])
    return _market(db, eid, "train", worker, spec, excluded)


METRICS_MIN_COVERAGE, SERIES_MIN_COVERAGE = 0.95, 0.95
DAY_S = 86400
OBSERVATION_MONTHS = 6


def _quality(bars, split, dups, spec, bundle=None):
    """Per-symbol quality (klines; plus daily metrics coverage for v3) and whether enough symbols remain. External
    series (DVOL, stablecoins) below 95 % day coverage fail the data gate."""
    t, split = spec["template"], _sp(spec, split)
    q = {s: data.quality(bars[s], split, dups[s]) for s in bars}
    series_ok = True
    if isinstance(bundle, dict) and "metrics" in bundle:
        for s in q:
            days = bundle["metrics"].get(s) or {}
            cov = data.coverage({d for d, v in days.items() if v.get("rows", 0) >= data.METRICS_MIN_ROWS}, split)
            q[s]["metrics_coverage"] = cov
            q[s]["ok"] = q[s]["ok"] and cov >= METRICS_MIN_COVERAGE
    if isinstance(bundle, dict):
        for key in ("dvol",):
            for cur, days in (bundle.get(key) or {}).items():
                series_ok = series_ok and data.coverage(days, split) >= SERIES_MIN_COVERAGE
        if "stable" in bundle:
            series_ok = series_ok and data.coverage(bundle["stable"], split) >= SERIES_MIN_COVERAGE
        if "rates" in bundle:                          # business-day series: >= 90 % of weekdays
            a, b = data.window(split)
            weekdays = [d for d in range(a, b + 1, DAY_S) if datetime.fromtimestamp(d, timezone.utc).weekday() < 5]
            series_ok = series_ok and len([d for d in weekdays if d in bundle["rates"]]) >= 0.9 * len(weekdays)
        for metric, per in (bundle.get("cm") or {}).items():
            for s in q:
                cov = data.coverage(per.get(s) or {}, split)
                q[s][f"{metric}_coverage"] = cov
                q[s]["ok"] = q[s]["ok"] and cov >= METRICS_MIN_COVERAGE
    excluded = sorted(s for s, x in q.items() if not x["ok"])
    return q, excluded, series_ok and len(q) - len(excluded) >= catalogue.min_symbols(t)


def _family(t):
    """The template's family with one calling convention: (bars_by, funding_by, params, fit=None, data=None)."""
    tpl = catalogue.TEMPLATES[t]
    fam = tpl["family"]
    if tpl.get("needs"):
        return lambda b, f, p, fit=None, volume_by=None: fam(b, f, p, None, extra=volume_by)
    return fam


def _positions(t, bars, funding, params, fit, vol=None):
    fam = catalogue.TEMPLATES[t]["family"]
    if catalogue.TEMPLATES[t].get("needs"):
        return fam(bars, funding, params, None, extra=vol)
    if catalogue.TEMPLATES[t].get("cross_sectional"):
        return fam(bars, funding, params, None, vol) if vol is not None else fam(bars, funding, params, None)
    return {s: fam(bars[s], funding[s], params, fit.get(s) if fit else None) for s in bars}


def _fit(t, bars, params):
    f = catalogue.TEMPLATES[t].get("fit")
    return {s: f(b, params) for s, b in bars.items()} if f else None


def _evaluate(bars, funding, pos, costs, mult=1.0, seed=SEED, lb_q=0.10):
    rows = {s: backtest.apply_costs(backtest.gross(bars[s], pos[s]), funding[s], costs, mult) for s in bars}
    return backtest.metrics(backtest.portfolio(rows), seed=seed, lb_q=lb_q)


def _benchmark(bars, funding, costs, seed=SEED):
    pos = {s: [0.0] + [1.0] * (len(b) - 1) for s, b in bars.items()}
    return _evaluate(bars, funding, pos, costs, seed=seed)


def _strip(m):
    return {k: v for k, v in m.items() if k != "daily_net"}


# ---------- step handlers (each returns a JSON-able result) ----------
def step_data(db, job, worker):
    eid = job["exp_id"]
    if lifecycle.state(db, eid) == "REGISTERED":
        lifecycle.auto_transition(db, eid, "SCREENING", f"system:{worker}", "screening starts: data fetch and checks")
    report, excluded, oks = {}, {}, []
    spec = _spec(db, eid)
    for split in (("train",) if _v2(spec) else ("train", "validation")):     # v2: validation is read only to validate
        bars, _, dups, bundle = _market(db, eid, split, worker, spec)
        report[split], excluded[split], ok_split = _quality(bars, split, dups, spec, bundle)
        oks.append(ok_split)
    ok = all(oks)
    art = save_artifact(eid, "data", {"quality": report, "ok": ok, "excluded": excluded,
                                      "min_symbols": catalogue.min_symbols(spec["template"])})
    return {"ok": ok, "artifact": art, "symbols": len(catalogue.universe(spec["template"])),
            "excluded": sum(len(v) for v in excluded.values())}


def step_backtest(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    bars, funding, _, vol = _train(db, eid, worker, spec)
    out = []
    for k, params in enumerate(spec["grid"]):
        fit = _fit(spec["template"], bars, params)
        pos = _positions(spec["template"], bars, funding, params, fit, vol)
        out.append({"variant": k, "params": params, "fit": fit,
                    "positions": {s: [round(x, 6) for x in p] for s, p in pos.items()}})
    art = save_artifact(eid, "backtest", {"split": "train", "variants": out})
    return {"variants": len(out), "artifact": art, "tests": len(out)}


def step_cost(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    bars, funding, _, _ = _train(db, eid, worker, spec)
    bt = load_artifact(eid, "backtest")
    results = []
    for v in bt["variants"]:
        m = _evaluate(bars, funding, v["positions"], spec["costs"])
        hi = _evaluate(bars, funding, v["positions"], spec["costs"], catalogue.COST_HIGH_MULT)
        sr_d = (m["net_mean_daily"] / m["net_sd_daily"]) if m.get("net_sd_daily") else None
        db.append("trials", exp_id=eid, ts=int(time.time()), variant=v["variant"], split="train", sharpe_daily=sr_d,
                  n_days=m["days"], net_total=m["net_total"], params=v["params"])
        results.append({"variant": v["variant"], "params": v["params"], "net": _strip(m), "net_2x_costs": _strip(hi)})
    bench = _strip(_benchmark(bars, funding, spec["costs"]))
    best = max(results, key=lambda r: r["net"]["net_sharpe_ann"] if r["net"]["net_sharpe_ann"] is not None else -9e9)
    sel_sr = best["net"]["net_sharpe_ann"]
    early, reasons = (sel_sr or -1) <= 0, []
    if early:
        reasons.append("train net Sharpe > 0")
    if _v2(spec) and (sel_sr is None or bench["net_sharpe_ann"] is None or sel_sr <= bench["net_sharpe_ann"]):
        early = True
        reasons.append("train net Sharpe > buy-and-hold train net Sharpe")
    art = save_artifact(eid, "cost", {"variants": results, "benchmark": bench, "selected": best["variant"],
                                      "rejected_early": early, "early_reasons": reasons, "cost_model": spec["costs"],
                                      "protocol_version": spec.get("protocol_version") or 1})
    return {"selected": best["variant"], "train_net_sharpe": best["net"]["net_sharpe_ann"], "rejected_early": early,
            "artifact": art, "tests": len(results)}


def step_adversarial(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    cost = load_artifact(eid, "cost")
    if cost["rejected_early"]:
        art = save_artifact(eid, "adversarial", {"skipped": "rejected at cost check"})
        return {"skipped": True, "artifact": art}
    t, v = spec["template"], load_artifact(eid, "backtest")["variants"][cost["selected"]]
    bars, funding, _, vol = _train(db, eid, worker, spec)
    fam = _family(t)
    if catalogue.TEMPLATES[t].get("cross_sectional"):
        trunc = {"ALL": adversarial.truncation_test_xs(fam, bars, funding, v["params"], 20, volume_by=vol)}
        poison = {"ALL": adversarial.poison_test_xs(fam, bars, funding, v["params"], volume_by=vol)}
    else:
        trunc = {s: adversarial.truncation_test(fam, bars[s], funding[s], v["params"], (v["fit"] or {}).get(s), 20)
                 for s in bars}
        poison = {s: adversarial.poison_test(fam, bars[s], funding[s], v["params"], (v["fit"] or {}).get(s))
                  for s in bars}
    dq = load_artifact(eid, "data")
    others = [r["net"]["net_sharpe_ann"] for r in cost["variants"] if r["variant"] != cost["selected"]]
    res = {"truncation": trunc, "poison": poison, "data_ok": dq["ok"],
           "delayed_one_bar": _strip(adversarial.delayed(bars, v["positions"], funding, spec["costs"])),
           "placebo": adversarial.placebo(bars, v["positions"], funding, spec["costs"], n=PLACEBO_N),
           "neighbours_net_sharpe": others}
    res["ok"] = all(x["ok"] for x in trunc.values()) and all(x["ok"] for x in poison.values()) and dq["ok"]
    if _v2(spec):
        pp = res["placebo"]["p"]
        exact = all(x["ok"] for x in trunc.values()) and all(x["ok"] for x in poison.values())
        checks = (("exact look-ahead and poison tests", exact), ("data quality", dq["ok"]),
                  (f"train placebo p < {catalogue.PLACEBO_P_MAX}", pp is not None and pp < catalogue.PLACEBO_P_MAX))
        res["pre_validation_failed"] = [k for k, ok in checks if not ok]
        res["pre_validation_ok"] = not res["pre_validation_failed"]
    art = save_artifact(eid, "adversarial", res)
    return {"ok": res["ok"], "placebo_p": res["placebo"]["p"], "pre_validation_ok": res.get("pre_validation_ok"),
            "artifact": art}


def step_validate(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    cost, adv = load_artifact(eid, "cost"), load_artifact(eid, "adversarial")
    if cost["rejected_early"]:
        art = save_artifact(eid, "validate", {"skipped": "rejected at the train gate"})
        return {"skipped": True, "artifact": art}
    if _v2(spec) and not adv.get("pre_validation_ok"):
        art = save_artifact(eid, "validate", {"skipped": "rejected before validation: "
                                                         + ", ".join(adv.get("pre_validation_failed") or [])})
        return {"skipped": True, "artifact": art}                           # validation data is never read
    v = load_artifact(eid, "backtest")["variants"][cost["selected"]]
    bars, funding, dups, vol = _market(db, eid, "validation", worker, spec)
    vq, v_excluded, v_enough = _quality(bars, "validation", dups, spec, vol)
    _drop(bars, funding, vol, v_excluded, spec)
    pos = _positions(spec["template"], bars, funding, v["params"], v["fit"], vol)  # frozen params and train fit
    m = _evaluate(bars, funding, pos, spec["costs"])
    hi = _evaluate(bars, funding, pos, spec["costs"], catalogue.COST_HIGH_MULT)
    bench = _benchmark(bars, funding, spec["costs"])
    trials = dsr_trials(db, eid, spec)
    sr_d = (m["net_mean_daily"] / m["net_sd_daily"]) if m.get("net_sd_daily") else None
    dsr = backtest.deflated_sharpe(sr_d, trials, m["days"])
    gates = {"net_mean_daily > 0": (m["net_mean_daily"] or 0) > 0,
             "one-sided 90% lower bound > 0": (m["lb_one_sided"] or -1) > 0,
             "net Sharpe > buy-and-hold": (m["net_sharpe_ann"] or -9e9) > (bench["net_sharpe_ann"] or -9e9),
             "net total > 0 at 2x costs": hi["net_total"] > 0,
             "deflated Sharpe probability >= 0.95": (dsr or 0) >= catalogue.DSR_MIN,
             "adversarial checks pass": bool(adv.get("ok"))}
    if _v2(spec):
        gates["validation data quality"] = v_enough
    art = save_artifact(eid, "validate", {"metrics": _strip(m), "metrics_2x_costs": _strip(hi),
                                          "benchmark": _strip(bench), "dsr": dsr, "trials_counted": len(trials),
                                          "gates": gates, "daily_net": m["daily_net"], "validation_quality": vq,
                                          "validation_excluded": v_excluded})
    return {"passed": all(gates.values()), "artifact": art, "tests": 1}


def step_report(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    cost, adv, val = load_artifact(eid, "cost"), load_artifact(eid, "adversarial"), load_artifact(eid, "validate")
    sel = next(r for r in cost["variants"] if r["variant"] == cost["selected"])
    if cost["rejected_early"] and _v2(spec):
        failed = cost.get("early_reasons") or ["train gate"]
        verdict = (f"REJECTED at train gate: selected train net Sharpe {sel['net']['net_sharpe_ann'] or 0:.2f}, "
                   f"buy-and-hold {cost['benchmark']['net_sharpe_ann'] or 0:.2f}; failed {', '.join(failed)}")
    elif cost["rejected_early"]:
        verdict = (f"REJECTED at cost check: best train net Sharpe {sel['net']['net_sharpe_ann']:.2f} <= 0 "
                   f"(gross Sharpe {sel['net']['gross_sharpe_ann'] or 0:.2f})")
        failed = ["train net Sharpe > 0"]
    elif _v2(spec) and not adv.get("pre_validation_ok"):
        failed = adv.get("pre_validation_failed") or ["pre-validation gate"]
        verdict = f"REJECTED before validation (no validation data read): failed {', '.join(failed)}"
    else:
        failed = [k for k, ok in val["gates"].items() if not ok]
        verdict = ("PASS (screen): all validation gates passed; eligible for a human-approved sealed holdout"
                   if not failed else f"REJECTED at validation: failed {', '.join(failed)}")
        if spec.get("observation_test") and failed == ["deflated Sharpe probability >= 0.95"]:
            start = _next_month(time.time())
            verdict = (f"OBSERVE (forward test): passed every validation gate except the luck check (DSR "
                       f"{val.get('dsr') or 0:.3f}); forward window {_ymd(start)} + {OBSERVATION_MONTHS} months "
                       f"(research/PROTOCOL_V3.md amendment 2)")
    files = {s: f"data/lab/artifacts/{eid}/{s}.json" for s in STEPS if s != "report"}
    metrics = {"template": spec["template"], "selected_params": sel["params"], "train": sel["net"],
               "train_2x_costs": sel["net_2x_costs"], "train_benchmark": cost["benchmark"],
               "validation": val.get("metrics"), "validation_benchmark": val.get("benchmark"),
               "dsr": val.get("dsr"), "gates": val.get("gates"), "failed": failed,
               "placebo": adv.get("placebo"), "delayed_one_bar": adv.get("delayed_one_bar"),
               "cost_model": spec["costs"], "label": "EXPLORATORY", "returns_basis": "sum of hourly simple returns",
               "protocol_version": spec.get("protocol_version") or 1, "dsr_trials": val.get("trials_counted"),
               "batch": (batch_of(db, eid) or {}).get("batch")}
    rid = registry.record_result(db, eid, "EXPLORATORY", verdict, metrics, {"artifacts": files}, f"system:{worker}")
    ev = {"result_id": rid}
    to = "SCREEN_PASSED" if verdict.startswith("PASS") else ("OBSERVATION" if verdict.startswith("OBSERVE") else "REJECTED")
    lifecycle.auto_transition(db, eid, to, f"system:{worker}", verdict[:300], ev,
                              guards=(registry.make_result_guard(ev),))
    if to == "OBSERVATION":
        start = _next_month(time.time())
        split = data.forward_split(start, OBSERVATION_MONTHS)
        a, b = data.window_bounds(split)
        db.event("observation.started", f"system:{worker}", eid, {"window": split, "start": a, "end": b,
                                                                   "result_id": rid})
        jobs.enqueue(db, f"observe|{eid}", "observe", eid, {"start": a, "months": OBSERVATION_MONTHS}, priority=5,
                     max_attempts=3, timeout_s=1800, actor=f"system:{worker}", not_before=b + data.FORWARD_LAG_S)
    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, f"{eid}.md"), "w", encoding="utf-8") as f:
        f.write(render_report(eid, spec, verdict, metrics))
    return {"verdict": verdict, "result_id": rid, "state": to}


def _next_month(ts):
    d = datetime.fromtimestamp(ts, timezone.utc)
    return int(datetime(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1, tzinfo=timezone.utc).timestamp())


def _ymd(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def step_observe(db, job, worker):
    """Forward test on new, unseen data (amendment 2). The data window cannot be read before it has ended."""
    eid = job["exp_id"]
    if lifecycle.state(db, eid) != "OBSERVATION":
        raise StepError("forward test requires lifecycle OBSERVATION")
    pl = job["payload"]
    split = data.forward_split(pl["start"], pl.get("months", OBSERVATION_MONTHS))
    spec = _spec(db, eid)
    v = frozen_variant(db, eid)                                          # verified against the recorded hashes
    bars, funding, dups, vol = _market(db, eid, split, worker, spec)      # data.window() refuses unfinished windows
    q, excluded, enough = _quality(bars, split, dups, spec, vol)
    _drop(bars, funding, vol, excluded, spec)
    pos = _positions(spec["template"], bars, funding, v["params"], v["fit"], vol)
    m = _evaluate(bars, funding, pos, spec["costs"])
    hi = _evaluate(bars, funding, pos, spec["costs"], catalogue.COST_HIGH_MULT)
    bench = _benchmark(bars, funding, spec["costs"])
    a, _ = data.window_bounds(split)
    cohort = 0
    for r in db.q("SELECT ts, payload FROM events WHERE kind='observation.started'"):
        p = json.loads(r["payload"])
        if p.get("window") == split and r["ts"] < a:
            cohort += 1
    need = 1 - 0.05 / max(1, cohort)
    sr_d = (m["net_mean_daily"] / m["net_sd_daily"]) if m.get("net_sd_daily") else None
    prob = backtest.psr(sr_d, m["days"])
    gates = {"net_mean_daily > 0": (m["net_mean_daily"] or 0) > 0,
             "one-sided 90% lower bound > 0": (m["lb_one_sided"] or -1) > 0,
             "net Sharpe > buy-and-hold": (m["net_sharpe_ann"] or -9e9) > (bench["net_sharpe_ann"] or -9e9),
             "net total > 0 at 2x costs": hi["net_total"] > 0,
             f"forward luck check PSR >= {need:.4f}": (prob or 0) >= need,
             "forward data quality": enough}
    failed = [k for k, ok in gates.items() if not ok]
    verdict = ("PASS (forward test): every gate passed on new, unseen data; eligible for the human-approved steps"
               if not failed else f"FAIL (forward test): failed {', '.join(failed)}")
    art = save_artifact(eid, "observe", {"window": split, "metrics": _strip(m), "metrics_2x_costs": _strip(hi),
                                         "benchmark": _strip(bench), "psr": prob, "cohort": cohort, "gates": gates,
                                         "quality": q, "excluded": excluded, "daily_net": m["daily_net"]})
    rid = registry.record_result(db, eid, "VALIDATION", verdict, {"forward": _strip(m), "benchmark": _strip(bench),
                                                                  "psr": prob, "cohort": cohort, "gates": gates,
                                                                  "window": split}, {"artifacts": [art]},
                                 f"system:{worker}")
    ev = {"result_id": rid}
    to = "SCREEN_PASSED" if verdict.startswith("PASS") else "REJECTED"
    lifecycle.auto_transition(db, eid, to, f"system:{worker}", verdict[:300], ev,
                              guards=(registry.make_result_guard(ev),))
    return {"verdict": verdict, "result_id": rid, "state": to, "tests": 1}


def render_report(eid, spec, verdict, m):
    def fmt(x, pct=True):
        return "n/a" if x is None else (f"{x * 100:.2f} %" if pct else f"{x:.2f}")
    tr, va = m["train"], m.get("validation") or {}
    lines = [f"# {eid}", "", f"**Verdict:** {verdict}", "", f"Hypothesis: {spec['hypothesis']}", "",
             f"Mechanism: {spec['mechanism']}", "", "Evidence: " + "; ".join(spec["evidence"]), "",
             f"Universe: {', '.join(spec['universe'])} (1h); selected parameters {m['selected_params']}", "",
             "| | Train net | Validation net |", "|---|---|---|",
             f"| Total (sum of daily) | {fmt(tr.get('net_total'))} | {fmt(va.get('net_total'))} |",
             f"| Sharpe (ann.) | {fmt(tr.get('net_sharpe_ann'), False)} | {fmt(va.get('net_sharpe_ann'), False)} |",
             f"| Max drawdown | {fmt(tr.get('max_drawdown'))} | {fmt(va.get('max_drawdown'))} |",
             f"| Fees / spread / slippage / funding | {fmt(tr.get('fees'))} / {fmt(tr.get('spread'))} / "
             f"{fmt(tr.get('slippage'))} / {fmt(tr.get('funding'))} | |", "",
             f"Benchmark (buy-and-hold, same costs): train Sharpe {fmt((m.get('train_benchmark') or {}).get('net_sharpe_ann'), False)}, "
             f"validation Sharpe {fmt((m.get('validation_benchmark') or {}).get('net_sharpe_ann'), False)}", "",
             f"Deflated Sharpe probability: {m.get('dsr')}", "", "Gates: " + json.dumps(m.get("gates")), "",
             "All values are exploratory, simulated and net of the documented cost model unless marked gross."]
    return "\n".join(lines) + "\n"


NO_CLEAN_HOLDOUT = ("vrp_timing", "btc_volume_share")


def _drop(bars, funding, vol, symbols, spec):
    tpl = catalogue.TEMPLATES[spec["template"]]
    for s in symbols:
        bars.pop(s, None), funding.pop(s, None)
        if vol is not None and tpl.get("needs_volume"):
            vol.pop(s, None)
        elif vol is not None:
            for k in ("volume", "taker", "metrics"):
                (vol.get(k) or {}).pop(s, None)
            for per in (vol.get("cm") or {}).values():
                per.pop(s, None)


def step_holdout(db, job, worker):
    """Sealed 2024 holdout, only reachable after a human-approved SCREEN_PASSED -> VALIDATION transition."""
    eid = job["exp_id"]
    if lifecycle.state(db, eid) != "VALIDATION":
        raise StepError("holdout requires lifecycle VALIDATION")
    spec = _spec(db, eid)
    if spec["template"] in NO_CLEAN_HOLDOUT:
        raise StepError("no clean holdout possible: BTC/ETH 2024 data was already seen by L14_tsmom_v1 "
                        "(research/PROTOCOL_V3.md amendment 1)")
    v = frozen_variant(db, eid)                                          # verified against the recorded hashes
    bars, funding, dups, vol = _market(db, eid, "holdout", worker, spec)
    hq, h_excluded, h_enough = _quality(bars, "holdout", dups, spec, vol)
    if catalogue.TEMPLATES[spec["template"]].get("universe") in ("30", "30v3", "cm16"):
        h_excluded = sorted(set(h_excluded) | set(data.HOLDOUT_SEEN))
    h_left = [s for s in hq if s not in h_excluded]
    h_enough = bool(h_enough) and len(h_left) >= catalogue.min_symbols(spec["template"])   # amendment 5 (stricter)
    _drop(bars, funding, vol, h_excluded, spec)
    pos = _positions(spec["template"], bars, funding, v["params"], v["fit"], vol)
    m = _evaluate(bars, funding, pos, spec["costs"], lb_q=0.05)
    bench = _benchmark(bars, funding, spec["costs"])
    gates = {"net_mean_daily > 0": (m["net_mean_daily"] or 0) > 0, "one-sided 95% lower bound > 0": (m["lb_one_sided"] or -1) > 0,
             "net Sharpe > buy-and-hold": (m["net_sharpe_ann"] or -9e9) > (bench["net_sharpe_ann"] or -9e9),
             "holdout data quality (min symbols)": h_enough}
    passed = all(gates.values())
    verdict = "PASS (holdout): paper-eligible after a human approval" if passed else \
        f"FAIL (holdout): failed {', '.join(k for k, ok in gates.items() if not ok)}"
    art = save_artifact(eid, "holdout", {"metrics": _strip(m), "benchmark": _strip(bench), "gates": gates,
                                         "daily_net": m["daily_net"]})
    rid = registry.record_result(db, eid, "VALIDATION", verdict, {"holdout": _strip(m), "benchmark": _strip(bench),
                                                                   "gates": gates}, {"artifacts": [art]},
                                 f"system:{worker}")
    ev = {"result_id": rid}
    lifecycle.auto_transition(db, eid, "VALIDATED" if passed else "REJECTED", f"system:{worker}", verdict, ev,
                              guards=(registry.make_result_guard(ev),))
    return {"verdict": verdict}


def step_diagnose(db, job, worker):
    """Non-decisional diagnostics of a finished experiment (PROTOCOL_V3 amendment 5): reads only its recorded,
    hash-verified validate.json; writes artifacts/_diagnostic/<exp>/diagnose.json and a research.diagnostic event."""
    from lab import diagnose
    eid = job["exp_id"]
    st = lifecycle.state(db, eid)
    if st not in lifecycle.FINAL:
        raise StepError(f"diagnostics are for finished experiments only; {eid} is {st}")
    val = frozen_artifact(db, eid, "validate")
    s = diagnose.series(val.get("daily_net") or [])
    lessons, failed = diagnose.lessons(s, val.get("gates"))
    verdict = db.one("SELECT verdict FROM results WHERE exp_id=? ORDER BY id DESC LIMIT 1", eid)
    out = {"exp_id": eid, "state": st, "verdict": verdict[0] if verdict else None, "series": s, "lessons": lessons,
           "failed_gates": failed, "source": "validate.json (hash-verified)", "decisional": False,
           "rules": {"best_days": diagnose.BEST_DAYS, "concentrated": diagnose.CONCENTRATED,
                     "low_activity": diagnose.LOW_ACTIVITY}}
    art = save_artifact(os.path.join("_diagnostic", eid), "diagnose", out)
    db.event("research.diagnostic", f"system:{worker}", eid, {"lessons": lessons, "failed_gates": failed,
                                                             "artifact_sha256": art["sha256"], "n_days": s.get("n")})
    return {"lessons": lessons, "artifact": art}


def enqueue_diagnostics(db, actor="strategy-1"):
    """Every finished catalogue experiment with a recorded validation series gets exactly one diagnose job."""
    jobs.init(db)
    n = 0
    for x in registry.status(db):
        eid = x["exp_id"]
        if not (x["state"] in lifecycle.FINAL and eid.startswith("E_")):
            continue
        if db.one("SELECT 1 FROM jobs WHERE job_id=?", f"diagnose|{eid}"):
            continue
        v = db.one("SELECT result FROM jobs WHERE job_id=?", f"validate|{eid}")
        if v and '"skipped"' in (v["result"] or ""):
            continue                                  # rejected before validation: no series to learn from
        if recorded_sha(db, eid, "validate"):
            _, created = jobs.enqueue(db, f"diagnose|{eid}", "diagnose", eid, {}, priority=60, max_attempts=2,
                                      timeout_s=120, actor=f"system:{actor}")
            n += created
    return n


HANDLERS = {"data": step_data, "backtest": step_backtest, "cost": step_cost, "adversarial": step_adversarial,
            "validate": step_validate, "report": step_report, "holdout": step_holdout, "observe": step_observe,
            "diagnose": step_diagnose}


def enqueue_holdouts(db, actor="strategy-1"):
    """Experiments a human moved into VALIDATION get exactly one holdout job."""
    n = 0
    for x in registry.status(db):
        if x["state"] == "VALIDATION" and x["exp_id"].startswith("E_"):
            _, created = jobs.enqueue(db, f"holdout|{x['exp_id']}", "holdout", x["exp_id"], {}, priority=5,
                                      max_attempts=2, timeout_s=900, actor=f"system:{actor}")
            n += created
    return n
