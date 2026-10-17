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

from lab import jobs, lifecycle, registry, templates
from lab.data import Gateway
from lab.db import HERE
from lab.engine import adversarial, backtest, catalogue, data

ARTIFACTS = os.path.join(HERE, "data", "lab", "artifacts")
REPORTS = os.path.join(HERE, "data", "lab", "reports")
STEPS = ("data", "backtest", "cost", "adversarial", "validate", "report")
ALPHA_PER_EXPERIMENT = 0.005
SEED = 7
ENGINE_CODE = ["lab/engine/catalogue.py", "lab/engine/backtest.py", "lab/engine/adversarial.py", "lab/engine/data.py",
               "lab/pipeline.py"]


class StepError(Exception):
    pass


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


# ---------- discovery and registration ----------
def discover_catalogue(db, actor="discovery-catalogue"):
    """Propose every catalogue template that is not in the registry yet (graveyard applies in registry.discover)."""
    out = []
    for t, tpl in catalogue.TEMPLATES.items():
        eid = catalogue.exp_id(t)
        if db.one("SELECT 1 FROM experiments WHERE exp_id=?", eid):
            continue
        st, dup = registry.discover(db, eid, tpl["hypothesis"], tpl["mechanism_tag"], catalogue.INSTRUMENT_FAMILY,
                                    catalogue.HORIZON[t], "taker", "lab/engine/catalogue.py", actor,
                                    extra={"template": t, "title": t.replace("_", " "), "discovered_by": actor,
                                           "reason": tpl["rationale"], "evidence": tpl["evidence"],
                                           "data_requirements": ["Binance USD-M 1h klines", "funding rates"]})
        out.append((eid, st, dup))
    return out


def template_spec(t):
    tpl = catalogue.TEMPLATES[t]
    return {"template": t, "title": t.replace("_", " "), "hypothesis": tpl["hypothesis"], "mechanism": tpl["rationale"],
            "mechanism_tag": tpl["mechanism_tag"], "evidence": tpl["evidence"],
            "sources": ["lab/engine/catalogue.py"] + tpl["evidence"], "instrument": catalogue.INSTRUMENT_FAMILY,
            "universe": list(data.UNIVERSE), "timeframe": "1h", "horizon": catalogue.HORIZON[t], "execution": "taker",
            "long_only": tpl["long_only"],
            "datasets": {"source": "https://data.binance.vision (futures/um monthly klines 1h + fundingRate)",
                         "splits": {k: [f"{a[0]}-{a[1]:02d}", f"{b[0]}-{b[1]:02d}"] for k, (a, b) in data.SPLITS.items()},
                         "reserved_from": "2025-01-01 (never read)"},
            "grid": tpl["grid"], "methodology": catalogue.PROTOCOL, "baseline": "equal-weight buy-and-hold of the same "
            "8 perpetuals with the same costs and funding", "costs": catalogue.COSTS,
            "acceptance": catalogue.PROTOCOL["validation"], "rejection": "any validation, cost or adversarial gate fails",
            "alpha": ALPHA_PER_EXPERIMENT, "code": ENGINE_CODE, "seed": SEED,
            "protocol_version": catalogue.PROTOCOL_VERSION, "label": "EXPLORATORY until a sealed holdout passes"}


def register(db, eid, actor="strategy-1"):
    """Attach the full spec as a new version and register it through the approved-template path."""
    v = registry.latest(db, eid)
    t = json.loads(v["spec_json"] or "{}").get("template")
    if not t:
        raise StepError(f"{eid} is not a catalogue instance")
    if templates.approval(db, t) is None:
        return False
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
    enqueue_pipeline(db, eid, actor)
    return True


def enqueue_pipeline(db, eid, actor="strategy-1"):
    prio = 20 + list(catalogue.TEMPLATES).index(json.loads(registry.latest(db, eid)["spec_json"])["template"])
    prev = []
    for s in STEPS:
        jobs.enqueue(db, f"{s}|{eid}", s, eid, {"exp_id": eid}, priority=prio, depends_on=prev,
                     timeout_s=900 if s in ("backtest", "adversarial", "validate") else 300, actor=f"system:{actor}")
        prev = [f"{s}|{eid}"]


# ---------- helpers ----------
def _spec(db, eid):
    return json.loads(registry.latest(db, eid)["spec_json"])


def _files(db, eid, split, worker):
    """Download/reuse the split's files and record the read through the gateway (state rules apply)."""
    per_sym, all_files = {}, []
    for s in data.UNIVERSE:
        f = data.files_for(s, split)
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


def _positions(t, bars, funding, params, fit):
    fam = catalogue.TEMPLATES[t]["family"]
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
    report = {}
    for split in ("train", "validation"):
        per_sym = _files(db, eid, split, worker)
        bars, _, dups = _load(per_sym, split)
        report[split] = {s: data.quality(bars[s], split, dups[s]) for s in bars}
    ok = all(q["ok"] for sp in report.values() for q in sp.values())
    art = save_artifact(eid, "data", {"quality": report, "ok": ok})
    return {"ok": ok, "artifact": art, "symbols": len(data.UNIVERSE)}


def step_backtest(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    bars, funding, _ = _load(_files(db, eid, "train", worker), "train")
    out = []
    for k, params in enumerate(spec["grid"]):
        fit = _fit(spec["template"], bars, params)
        pos = _positions(spec["template"], bars, funding, params, fit)
        out.append({"variant": k, "params": params, "fit": fit,
                    "positions": {s: [round(x, 6) for x in p] for s, p in pos.items()}})
    art = save_artifact(eid, "backtest", {"split": "train", "variants": out})
    return {"variants": len(out), "artifact": art, "tests": len(out)}


def step_cost(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    bars, funding, _ = _load(_files(db, eid, "train", worker), "train")
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
    early = (best["net"]["net_sharpe_ann"] or -1) <= 0
    art = save_artifact(eid, "cost", {"variants": results, "benchmark": bench, "selected": best["variant"],
                                      "rejected_early": early, "cost_model": spec["costs"]})
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
    bars, funding, _ = _load(_files(db, eid, "train", worker), "train")
    fam = catalogue.TEMPLATES[t]["family"]
    trunc = {s: adversarial.truncation_test(fam, bars[s], funding[s], v["params"], (v["fit"] or {}).get(s), 20)
             for s in bars}
    poison = {s: adversarial.poison_test(fam, bars[s], funding[s], v["params"], (v["fit"] or {}).get(s)) for s in bars}
    dq = load_artifact(eid, "data")
    others = [r["net"]["net_sharpe_ann"] for r in cost["variants"] if r["variant"] != cost["selected"]]
    res = {"truncation": trunc, "poison": poison, "data_ok": dq["ok"],
           "delayed_one_bar": _strip(adversarial.delayed(bars, v["positions"], funding, spec["costs"])),
           "placebo": adversarial.placebo(bars, v["positions"], funding, spec["costs"]),
           "neighbours_net_sharpe": others}
    res["ok"] = all(x["ok"] for x in trunc.values()) and all(x["ok"] for x in poison.values()) and dq["ok"]
    art = save_artifact(eid, "adversarial", res)
    return {"ok": res["ok"], "placebo_p": res["placebo"]["p"], "artifact": art}


def step_validate(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    cost, adv = load_artifact(eid, "cost"), load_artifact(eid, "adversarial")
    if cost["rejected_early"]:
        art = save_artifact(eid, "validate", {"skipped": "rejected at cost check"})
        return {"skipped": True, "artifact": art}
    v = load_artifact(eid, "backtest")["variants"][cost["selected"]]
    bars, funding, _ = _load(_files(db, eid, "validation", worker), "validation")
    pos = _positions(spec["template"], bars, funding, v["params"], v["fit"])      # frozen params and train fit
    m = _evaluate(bars, funding, pos, spec["costs"])
    hi = _evaluate(bars, funding, pos, spec["costs"], catalogue.COST_HIGH_MULT)
    bench = _benchmark(bars, funding, spec["costs"])
    trials = [r[0] for r in db.q("SELECT sharpe_daily FROM trials WHERE sharpe_daily IS NOT NULL")]
    sr_d = (m["net_mean_daily"] / m["net_sd_daily"]) if m.get("net_sd_daily") else None
    dsr = backtest.deflated_sharpe(sr_d, trials, m["days"])
    gates = {"net_mean_daily > 0": (m["net_mean_daily"] or 0) > 0,
             "one-sided 90% lower bound > 0": (m["lb_one_sided"] or -1) > 0,
             "net Sharpe > buy-and-hold": (m["net_sharpe_ann"] or -9e9) > (bench["net_sharpe_ann"] or -9e9),
             "net total > 0 at 2x costs": hi["net_total"] > 0,
             "deflated Sharpe probability >= 0.95": (dsr or 0) >= 0.95,
             "adversarial checks pass": bool(adv.get("ok"))}
    art = save_artifact(eid, "validate", {"metrics": _strip(m), "metrics_2x_costs": _strip(hi),
                                          "benchmark": _strip(bench), "dsr": dsr, "trials_counted": len(trials),
                                          "gates": gates, "daily_net": m["daily_net"]})
    return {"passed": all(gates.values()), "artifact": art, "tests": 1}


def step_report(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    cost, adv, val = load_artifact(eid, "cost"), load_artifact(eid, "adversarial"), load_artifact(eid, "validate")
    sel = next(r for r in cost["variants"] if r["variant"] == cost["selected"])
    if cost["rejected_early"]:
        verdict = (f"REJECTED at cost check: best train net Sharpe {sel['net']['net_sharpe_ann']:.2f} <= 0 "
                   f"(gross Sharpe {sel['net']['gross_sharpe_ann'] or 0:.2f})")
        failed = ["train net Sharpe > 0"]
    else:
        failed = [k for k, ok in val["gates"].items() if not ok]
        verdict = ("PASS (screen): all validation gates passed; eligible for a human-approved sealed holdout"
                   if not failed else f"REJECTED at validation: failed {', '.join(failed)}")
    files = {s: f"data/lab/artifacts/{eid}/{s}.json" for s in STEPS if s != "report"}
    metrics = {"template": spec["template"], "selected_params": sel["params"], "train": sel["net"],
               "train_2x_costs": sel["net_2x_costs"], "train_benchmark": cost["benchmark"],
               "validation": val.get("metrics"), "validation_benchmark": val.get("benchmark"),
               "dsr": val.get("dsr"), "gates": val.get("gates"), "failed": failed,
               "placebo": adv.get("placebo"), "delayed_one_bar": adv.get("delayed_one_bar"),
               "cost_model": spec["costs"], "label": "EXPLORATORY", "returns_basis": "sum of hourly simple returns"}
    rid = registry.record_result(db, eid, "EXPLORATORY", verdict, metrics, {"artifacts": files}, f"system:{worker}")
    ev = {"result_id": rid}
    to = "SCREEN_PASSED" if verdict.startswith("PASS") else "REJECTED"
    lifecycle.auto_transition(db, eid, to, f"system:{worker}", verdict[:300], ev,
                              guards=(registry.make_result_guard(ev),))
    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, f"{eid}.md"), "w", encoding="utf-8") as f:
        f.write(render_report(eid, spec, verdict, metrics))
    return {"verdict": verdict, "result_id": rid, "state": to}


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


def step_holdout(db, job, worker):
    """Sealed 2024 holdout, only reachable after a human-approved SCREEN_PASSED -> VALIDATION transition."""
    eid = job["exp_id"]
    if lifecycle.state(db, eid) != "VALIDATION":
        raise StepError("holdout requires lifecycle VALIDATION")
    spec = _spec(db, eid)
    cost = load_artifact(eid, "cost")
    v = load_artifact(eid, "backtest")["variants"][cost["selected"]]
    bars, funding, _ = _load(_files(db, eid, "holdout", worker), "holdout")
    pos = _positions(spec["template"], bars, funding, v["params"], v["fit"])
    m = _evaluate(bars, funding, pos, spec["costs"], lb_q=0.05)
    bench = _benchmark(bars, funding, spec["costs"])
    gates = {"net_mean_daily > 0": (m["net_mean_daily"] or 0) > 0, "one-sided 95% lower bound > 0": (m["lb_one_sided"] or -1) > 0,
             "net Sharpe > buy-and-hold": (m["net_sharpe_ann"] or -9e9) > (bench["net_sharpe_ann"] or -9e9)}
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


HANDLERS = {"data": step_data, "backtest": step_backtest, "cost": step_cost, "adversarial": step_adversarial,
            "validate": step_validate, "report": step_report, "holdout": step_holdout}


def enqueue_holdouts(db, actor="strategy-1"):
    """Experiments a human moved into VALIDATION get exactly one holdout job."""
    n = 0
    for x in registry.status(db):
        if x["state"] == "VALIDATION" and x["exp_id"].startswith("E_"):
            _, created = jobs.enqueue(db, f"holdout|{x['exp_id']}", "holdout", x["exp_id"], {}, priority=5,
                                      max_attempts=2, timeout_s=900, actor=f"system:{actor}")
            n += created
    return n
