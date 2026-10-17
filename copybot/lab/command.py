"""Command-center read models (Mission 6). Pure functions of the database and the job queue, computed per request.

Rules: every value comes from persisted data; a value that does not exist is returned as None and the dashboard shows
"ikke tilgængelig". Backtest, validation, holdout and paper figures are kept apart and labelled. There is no real
account in this system, so real-account profit is always reported as not available.
"""
from __future__ import annotations

import json
import math
import os
import time

from lab import control, jobs, lifecycle, mission, registry
from lab.db import HERE
from lab.engine import data as mdata
from lab.gates import s7_gate
from lab.risk import Risk

PIPE = ("DISCOVERED", "QUEUED", "RUNNING", "COST_CHECK", "VALIDATION", "PAPER_ELIGIBLE", "PAPER_TRADING", "ACCEPTED",
        "REJECTED", "PAUSED")
STAGE_OF_KIND = {"data": "RUNNING", "backtest": "RUNNING", "cost": "COST_CHECK", "adversarial": "VALIDATION",
                 "validate": "VALIDATION", "report": "VALIDATION", "holdout": "VALIDATION"}
STAGE_OF_STATE = {"DISCOVERED": "DISCOVERED", "REGISTERED": "QUEUED", "SCREENING": "RUNNING",
                  "SCREEN_PASSED": "VALIDATION", "VALIDATION": "VALIDATION", "VALIDATED": "PAPER_ELIGIBLE",
                  "PAPER_TRADING": "PAPER_TRADING", "PAUSED": "PAUSED", "REJECTED": "REJECTED",
                  "SUPPRESSED": "REJECTED", "WITHDRAWN": "REJECTED", "RETIRED": None, "EXTERNAL": None}
WAITING_HUMAN = {"DISCOVERED": "template approval (human) before registration",
                 "SCREEN_PASSED": "human approval to open the sealed holdout",
                 "VALIDATED": "human approval to start PAPER trading",
                 "PAUSED": "human-approved revalidation before resume"}
TEST_KINDS = ("backtest", "cost", "adversarial", "validate", "holdout")
REAL_ACCOUNT = {"value": None, "reason": "no real account, broker or live execution path exists in this system"}


def _j(s):
    try:
        return json.loads(s) if s else None
    except ValueError:
        return s


def _page(rows, page, size):
    page, size = max(1, int(page or 1)), max(1, min(200, int(size or 50)))
    return {"items": rows[(page - 1) * size: page * size], "page": page, "size": size, "total": len(rows),
            "pages": max(1, math.ceil(len(rows) / size))}


# ---------- stages ----------
def job_state(db, eid):
    """(stage, phase, job) for a catalogue experiment from its jobs: the running job, else the next pending one."""
    jobs.init(db)
    js = [dict(r) for r in db.q("SELECT job_id, kind, status, lease_owner, attempts, error, started_ts, updated_ts "
                                "FROM jobs WHERE exp_id=? ORDER BY created_ts", eid)]
    run = next((j for j in js if j["status"] == "running"), None)
    if run:
        return STAGE_OF_KIND.get(run["kind"], "RUNNING"), "running", run
    pend = next((j for j in js if j["status"] in ("queued", "blocked")), None)
    if pend:
        done = any(j["status"] == "done" for j in js)
        return (STAGE_OF_KIND.get(pend["kind"], "RUNNING") if done else "QUEUED"), "queued", pend
    return None, None, None


def stage(db, eid, state):
    s, phase, job = job_state(db, eid)
    if s and state in ("REGISTERED", "SCREENING", "VALIDATION"):
        return s, phase, job
    return STAGE_OF_STATE.get(state), ("waiting for human" if state in WAITING_HUMAN else None), None


# ---------- agents ----------
def agents(db, now=None):
    now = now or time.time()
    wk = mission.workers(db, now)
    rows = {r["worker"]: dict(r) for r in db.q("SELECT * FROM heartbeats")}
    out = []
    for w in wk["workers"]:
        r = rows.get(w["worker"], {})
        st = w["state"]
        raw = r.get("status")
        if st not in ("offline", "stale", "error"):
            st = {"running": "running", "idle": "idle", "blocked": "blocked", "queued": "queued",
                  "failed": "failed"}.get(raw, st)
        if st == "scheduled":
            st = "idle"
        job = jobs.get(db, r["current_job"]) if r.get("current_job") and "|" in (r.get("current_job") or "") else None
        kind = job["kind"] if job else None
        out.append({"agent": w["worker"], "role": r.get("role") or "built-in supervisor worker", "status": st,
                    "raw_status": raw, "current_job": r.get("current_job") if st == "running" else None,
                    "current_exp": r.get("current_exp") if st == "running" else None,
                    "stage": STAGE_OF_KIND.get(kind) if st == "running" else None,
                    "started_ts": r.get("started_ts"), "heartbeat_ts": r.get("ts"), "heartbeat_age_s": w["age_s"],
                    "job_running_s": (now - job["started_ts"]) if (job and st == "running" and job["started_ts"]) else None,
                    "uptime_s": (r["ts"] - r["started_ts"]) if r.get("started_ts") else None,
                    "tasks_done": r.get("tasks_done"), "errors": r.get("errors"), "retries": r.get("retries"),
                    "last_result": r.get("last_result"), "next_action": r.get("next_action"), "detail": r.get("detail"),
                    "pid": r.get("pid")})
    return {"supervisor": wk["supervisor"], "agents": out, "total": len(out),
            "active": sum(1 for a in out if a["status"] in ("running", "idle", "queued", "blocked")),
            "running": sum(1 for a in out if a["status"] == "running")}


def agent_log(db, name, limit=50):
    rows = db.q("SELECT id, ts, kind, exp_id, payload FROM events WHERE actor IN (?,?,?) ORDER BY id DESC LIMIT ?",
                name, f"agent:{name}", f"system:{name}", int(limit))
    return {"agent": name, "events": [dict(r) | {"payload": _j(r["payload"])} for r in rows]}


# ---------- KPIs ----------
def last_data_update(db):
    ds = db.one("SELECT MAX(ts) FROM datasets")[0]
    newest = None
    for sub in ("klines", "funding"):
        d = os.path.join(mdata.CACHE, sub)
        if os.path.isdir(d):
            for f in os.scandir(d):
                newest = max(newest or 0, f.stat().st_mtime)
    return {"last_gateway_read_ts": ds, "last_download_ts": newest}


def kpis(db, window_s=900, now=None):
    now = now or time.time()
    ag = agents(db, now)
    jc = jobs.counts(db)
    since = now - window_s
    trials_win = db.one("SELECT COUNT(*) FROM trials WHERE ts>=?", int(since))[0]
    evals_win = db.one("SELECT COUNT(*) FROM jobs WHERE status='done' AND kind IN ('validate','holdout') AND "
                       "COALESCE(result,'') NOT LIKE '%skipped%' AND "
                       "finished_ts>=?", since)[0]
    jobs_win = db.one("SELECT COUNT(*) FROM jobs WHERE status='done' AND finished_ts>=?", since)[0]
    errors_win = db.one("SELECT COUNT(*) FROM events WHERE kind IN ('job.failed','job.timeout','agent.error',"
                        "'worker.error') AND ts>=?", int(since))[0]
    retries_win = db.one("SELECT COUNT(*) FROM events WHERE kind IN ('job.retry','job.timeout') AND ts>=?", int(since))[0]
    res = control.resources()
    ctl = control.state(db)
    minutes = window_s / 60
    return {
        "now": now, "window_s": window_s,
        "supervisor": ag["supervisor"], "control": ctl, "fail_closed": Risk(db).fail_closed(),
        "agents_active": ag["active"], "agents_total": ag["total"], "agents_running": ag["running"],
        "jobs": jc, "queued_jobs": jc["queued"] + jc["blocked"],
        "tests_running": db.one(f"SELECT COUNT(*) FROM jobs WHERE status='running' AND kind IN "
                                f"({','.join('?' * len(TEST_KINDS))})", *TEST_KINDS)[0],
        "tests_completed": {"variant_evaluations": db.one("SELECT COUNT(*) FROM trials")[0],
                            "validation_runs": db.one("SELECT COUNT(*) FROM jobs WHERE status='done' AND kind IN "
                                                      "('validate','holdout') AND COALESCE(result,'') NOT LIKE "
                                                      "'%skipped%'")[0]},
        "tests_per_min": (trials_win + evals_win) / minutes, "jobs_per_min": jobs_win / minutes,
        "tests_per_min_basis": f"variant evaluations (trials ledger) + validation runs finished in the last "
                               f"{int(minutes)} min, divided by {int(minutes)}",
        "errors_window": errors_win, "retries_window": retries_win,
        "errors_total": db.one("SELECT COUNT(*) FROM events WHERE kind IN ('job.failed','job.timeout','agent.error',"
                               "'worker.error')")[0],
        "retries_total": db.one("SELECT COUNT(*) FROM events WHERE kind IN ('job.retry','job.timeout')")[0],
        "disk": res["disk"], "ram": res["ram"], "ram_min_free": res["ram_min_free"], "resources_ok": res["ok"],
        "data": last_data_update(db), "gate_s7": s7_gate(db, now), "real_account_profit": REAL_ACCOUNT,
        "last_event_id": db.one("SELECT COALESCE(MAX(id),0) FROM events")[0]}


# ---------- experiments ----------
def _result(db, eid, label=None):
    q = "SELECT id, ts, label, verdict, metrics FROM results WHERE exp_id=?" + (" AND label=?" if label else "")
    r = db.one(q + " ORDER BY id DESC LIMIT 1", *((eid, label) if label else (eid,)))
    return (dict(r) | {"metrics": _j(r["metrics"])}) if r else None


def experiment_record(db, x, now=None):
    eid, st = x["exp_id"], x["state"]
    v = registry.latest(db, eid)
    spec = _j(v["spec_json"]) or {}
    stg, phase, job = stage(db, eid, st)
    res = _result(db, eid)
    m = (res or {}).get("metrics") or {}
    val, tr = m.get("validation") or {}, m.get("train") or {}
    tr_reason = db.one("SELECT reason FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", eid)
    is_cat = eid.startswith("E_")
    last_job = db.one("SELECT lease_owner, kind, updated_ts FROM jobs WHERE exp_id=? AND status='running'", eid)
    worker = last_job["lease_owner"] if last_job else None
    if not worker:
        ev = db.one("SELECT actor FROM events WHERE exp_id=? AND kind LIKE 'job.%' ORDER BY id DESC LIMIT 1", eid)
        worker = ev["actor"] if ev else None
    holdout = _result(db, eid, "VALIDATION") if is_cat else None
    return {
        "exp_id": eid, "title": spec.get("title") or spec.get("hypothesis") or eid, "template": spec.get("template"),
        "hypothesis": spec.get("hypothesis"), "mechanism": x["mechanism"],
        "market": mission.market_class(spec.get("instrument") or x["mechanism"]),
        "instrument": spec.get("instrument"), "universe": spec.get("universe"), "timeframe": spec.get("timeframe"),
        "data_period": (spec.get("datasets") or {}).get("splits") if isinstance(spec.get("datasets"), dict) else None,
        "split": {"train": "2023-01..2023-08", "validation": "2023-09..2023-12", "holdout": "2024 (sealed)"}
        if is_cat else None,
        "grid": spec.get("grid"), "selected_params": m.get("selected_params"), "seed": spec.get("seed"),
        "benchmark": spec.get("baseline"), "cost_assumptions": spec.get("costs"),
        "state": st, "stage": stg, "phase": phase, "current_job": job["job_id"] if job else None, "worker": worker,
        "train": {k: tr.get(k) for k in ("gross_total", "net_total", "net_sharpe_ann", "max_drawdown", "exposure",
                                         "position_changes", "win_rate_days", "expectancy_per_change", "fees",
                                         "spread", "slippage", "funding", "ci95")} if tr else None,
        "validation": {k: val.get(k) for k in ("gross_total", "net_total", "net_sharpe_ann", "max_drawdown", "exposure",
                                               "position_changes", "win_rate_days", "expectancy_per_change", "fees",
                                               "spread", "slippage", "funding", "lb_one_sided", "lb_quantile",
                                               "ci95", "days")} if val else None,
        "benchmark_result": {"train_sharpe": (m.get("train_benchmark") or {}).get("net_sharpe_ann"),
                             "validation_sharpe": (m.get("validation_benchmark") or {}).get("net_sharpe_ann")}
        if m.get("train_benchmark") else None,
        "dsr": m.get("dsr"), "gates": m.get("gates"), "failed_gates": m.get("failed"),
        "holdout": (holdout or {}).get("metrics"), "result_label": (res or {}).get("label"),
        "verdict": (res or {}).get("verdict") or x.get("verdict"),
        "rejection_reason": ((res or {}).get("verdict") or (tr_reason["reason"] if tr_reason else None))
        if st in ("REJECTED", "SUPPRESSED", "WITHDRAWN") else None,
        "next_action": WAITING_HUMAN.get(st) or ({"REGISTERED": "screening jobs queued",
                                                  "SCREENING": f"job {job['job_id']} {phase}" if job else "screening",
                                                  "VALIDATION": "sealed holdout job",
                                                  "PAPER_TRADING": "simulated execution each hour"}.get(st)),
        "report": f"data/lab/reports/{eid}.md" if is_cat and res else None, "catalogue": is_cat,
        "trials": db.one("SELECT COUNT(*) FROM trials WHERE exp_id=?", eid)[0]}


def experiments(db, market=None, strategy=None, worker=None, status=None, stage_f=None, since=None, page=1, size=50,
                catalogue_only=False):
    rows = []
    for x in registry.status(db):
        if catalogue_only and not x["exp_id"].startswith("E_"):
            continue
        r = experiment_record(db, x)
        if market and r["market"] != market:
            continue
        if strategy and (r["template"] or r["mechanism"]) != strategy:
            continue
        if worker and r["worker"] != worker:
            continue
        if status and r["state"] != status:
            continue
        if stage_f and r["stage"] != stage_f:
            continue
        if since:
            last = db.one("SELECT MAX(ts) FROM events WHERE exp_id=?", r["exp_id"])[0] or 0
            if last < float(since):
                continue
        rows.append(r)
    counts = {s: 0 for s in PIPE}
    for r in rows:
        if r["stage"] in counts:
            counts[r["stage"]] += 1
    out = _page(rows, page, size)
    out.update({"stages": PIPE, "stage_counts": counts,
                "filters": {"markets": sorted({r["market"] for r in rows}),
                            "strategies": sorted({r["template"] or r["mechanism"] for r in rows if r["template"] or r["mechanism"]}),
                            "workers": sorted({r["worker"] for r in rows if r["worker"]}),
                            "statuses": sorted({r["state"] for r in rows})}})
    return out


def job_list(db, status=None, kind=None, exp=None, page=1, size=50):
    q, a = "SELECT * FROM jobs WHERE 1=1", []
    for col, val in (("status", status), ("kind", kind), ("exp_id", exp)):
        if val:
            q += f" AND {col}=?"
            a.append(val)
    rows = [jobs._row(r) for r in db.q(q + " ORDER BY updated_ts DESC", *a)]
    out = _page(rows, page, size)
    out["counts"] = jobs.counts(db)
    return out


# ---------- results, paper, costs ----------
def distribution(db):
    """Variant evaluations from the trials ledger (all attempts, multiple-testing record) and per-experiment validation
    estimates with their 95 % bootstrap interval."""
    trials = [dict(r) for r in db.q("SELECT exp_id, variant, split, sharpe_daily, n_days, net_total, ts FROM trials "
                                    "ORDER BY id")]
    for t in trials:
        t["sharpe_ann"] = t["sharpe_daily"] * math.sqrt(365) if t["sharpe_daily"] is not None else None
    est = []
    for x in registry.status(db):
        if not x["exp_id"].startswith("E_"):
            continue
        res = _result(db, x["exp_id"], "EXPLORATORY")
        m = (res or {}).get("metrics") or {}
        va = m.get("validation")
        if va:
            est.append({"exp_id": x["exp_id"], "split": "validation", "mean_daily": va.get("net_mean_daily"),
                        "ci95": va.get("ci95"), "lb_one_sided": va.get("lb_one_sided"), "days": va.get("days"),
                        "sharpe_ann": va.get("net_sharpe_ann"),
                        "benchmark_sharpe": (m.get("validation_benchmark") or {}).get("net_sharpe_ann"),
                        "state": x["state"], "label": res["label"]})
    return {"trials": trials, "estimates": est, "unit": "net return per day (fraction), validation window",
            "source": "lab.db tables trials and results"}


def costs(db):
    out = []
    for x in registry.status(db):
        if not x["exp_id"].startswith("E_"):
            continue
        res = _result(db, x["exp_id"], "EXPLORATORY")
        m = (res or {}).get("metrics") or {}
        t = m.get("train") or {}
        if not t:
            continue
        out.append({"exp_id": x["exp_id"], "split": "train", "gross": t.get("gross_total"), "net": t.get("net_total"),
                    "fees": t.get("fees"), "spread": t.get("spread"), "slippage": t.get("slippage"),
                    "funding": t.get("funding"), "net_2x_costs": (m.get("train_2x_costs") or {}).get("net_total"),
                    "benchmark_net": (m.get("train_benchmark") or {}).get("net_total")})
    return {"rows": out, "unit": "sum of daily portfolio returns (fraction of capital), train window",
            "cost_model": __import__("lab.engine.catalogue", fromlist=["COSTS"]).COSTS}


def paper_view(db):
    from lab.paper import PaperEngine
    pe, rk, out = PaperEngine(db), Risk(db), []
    for r in db.q("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started' ORDER BY exp_id"):
        eid = r[0]
        led = pe.ledger(eid)
        eq = [dict(e) for e in db.q("SELECT ts, equity, cash, exposure, peak, drawdown FROM sim_equity WHERE exp_id=? "
                                    "ORDER BY id", eid)]
        realized = led["cash"] + sum(q * led["basis"][i] for i, q in led["positions"].items()) - led["capital"]
        last = eq[-1] if eq else None
        unreal = (last["equity"] - led["capital"] - realized) if last else None
        day = int(time.time()) // 86400 * 86400
        before = [e for e in eq if e["ts"] < day]
        today = ([before[-1]] if before else []) + [e for e in eq if e["ts"] >= day]
        day_peak = max((e["equity"] for e in today), default=None)
        daily_dd = ((day_peak - today[-1]["equity"]) / day_peak) if (today and day_peak) else None
        orders = db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", eid)[0]
        refused = db.one("SELECT COUNT(*) FROM events WHERE exp_id=? AND kind IN ('paper.refused',"
                         "'paper.signal_while_paused')", eid)[0]
        out.append({"exp_id": eid, "state": lifecycle.state(db, eid), "simulated": True, "label": "PAPER (simulated)",
                    "capital": led["capital"], "cash": led["cash"], "positions": led["positions"],
                    "open_positions": len(led["positions"]), "closed_trades": len(led["trades"]),
                    "equity": eq, "realized": realized, "unrealized": unreal,
                    "total_pnl": (last["equity"] - led["capital"]) if last else None,
                    "max_drawdown": max((e["drawdown"] for e in eq), default=None),
                    "daily_drawdown": daily_dd,
                    "orders": orders, "fills": db.one("SELECT COUNT(*) FROM sim_fills WHERE exp_id=?", eid)[0],
                    "rejected_orders": refused, "reconciliation": pe.reconcile(eid),
                    "paused": rk.paused(eid), "warming": rk.warming(eid)})
    return {"strategies": out, "simulated": True, "real_account_profit": REAL_ACCOUNT,
            "source": "lab.db sim_orders / sim_fills / sim_equity (simulated fills against public order books)",
            "eligible": [x["exp_id"] for x in registry.status(db) if x["state"] == "VALIDATED"]}


def rejected(db, limit=100):
    out = []
    for x in registry.status(db):
        if x["state"] not in ("REJECTED", "SUPPRESSED", "WITHDRAWN"):
            continue
        r = experiment_record(db, x)
        out.append({"exp_id": r["exp_id"], "state": r["state"], "mechanism": r["mechanism"], "market": r["market"],
                    "reason": r["rejection_reason"], "failed_gates": r["failed_gates"],
                    "pattern": mission.FAILURE_PATTERN.get(r["exp_id"]),
                    "ts": db.one("SELECT MAX(ts) FROM transitions WHERE exp_id=?", r["exp_id"])[0]})
    out.sort(key=lambda r: -(r["ts"] or 0))
    return {"items": out[:limit], "total": len(out)}
