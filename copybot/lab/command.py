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
                 "validate": "VALIDATION", "report": "VALIDATION", "holdout": "VALIDATION", "observe": "VALIDATION",
                 "observe_interim": "VALIDATION"}
NON_STAGE_KINDS = ("diagnose", "scan_digest", "scan_dossier", "explore", "explore_report", "lane_report")   # decide nothing: never move an experiment on the orbit
STAGE_OF_STATE = {"DISCOVERED": "DISCOVERED", "REGISTERED": "QUEUED", "SCREENING": "RUNNING",
                  "SCREEN_PASSED": "VALIDATION", "VALIDATION": "VALIDATION", "VALIDATED": "PAPER_ELIGIBLE",
                  "OBSERVATION": "VALIDATION",
                  "PAPER_TRADING": "PAPER_TRADING", "PAUSED": "PAUSED", "REJECTED": "REJECTED",
                  "SUPPRESSED": "REJECTED", "WITHDRAWN": "REJECTED", "RETIRED": None, "EXTERNAL": None}
WAITING_HUMAN = {"DISCOVERED": "template approval (human) before registration",
                 "SCREEN_PASSED": "human approval to open the sealed holdout",
                 "VALIDATED": "human approval to start PAPER trading",
                 "PAUSED": "human-approved revalidation before resume"}
TEST_KINDS = ("backtest", "cost", "adversarial", "validate", "holdout")
RETIRED_AFTER_S = 3600           # a worker outside the current roster that is silent this long is not counted
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
                                "FROM jobs WHERE exp_id=? ORDER BY created_ts", eid) if r["kind"] not in NON_STAGE_KINDS]
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
    from lab.fleet import ROLES, ROSTER
    kinds_of = {name: k for name, _r, k, *_ in ROSTER}
    run = jobs.runnable(db, now)
    exhausted = not _untested_templates(db)
    made_by = _events_24h(db, now)
    out, retired = [], []
    for w in wk["workers"]:
        r = rows.get(w["worker"], {})
        if w["worker"] not in ROLES and (w["age_s"] or 0) > RETIRED_AFTER_S:
            retired.append(w["worker"])                      # e.g. the S5 'heartbeat' demo worker: not in the fleet
            continue
        st = w["state"]
        raw = r.get("status")
        if st not in ("offline", "stale", "error"):
            st = {"running": "running", "idle": "idle", "blocked": "blocked", "queued": "queued",
                  "failed": "failed"}.get(raw, st)
        if st == "scheduled":
            st = "idle"
        job = jobs.get(db, r["current_job"]) if r.get("current_job") and "|" in (r.get("current_job") or "") else None
        kind = job["kind"] if job else None
        kinds = kinds_of.get(w["worker"]) or ()
        run_done = db.one("SELECT COUNT(*) FROM events WHERE kind='job.done' AND actor=? AND ts>=?", w["worker"],
                          int(r.get("started_ts") or 0))[0] if kinds else None
        work = None
        if kinds and st == "idle":
            n = sum(run["by_kind"].get(k, 0) for k in kinds)
            work = (f"{n} runnable {'/'.join(kinds)} job(s) waiting" if n else
                    f"no work: no runnable {'/'.join(kinds)} job" + (" (catalogue exhausted, see research.idle_reason)"
                                                                       if exhausted and not run["total"] else ""))
        made = _output_24h(made_by, w["worker"])
        out.append({"agent": w["worker"], "role": r.get("role") or "built-in supervisor worker", "status": st,
                    "raw_status": raw, "current_job": r.get("current_job") if st == "running" else None,
                    "current_exp": r.get("current_exp") if st == "running" else None,
                    "stage": STAGE_OF_KIND.get(kind) if st == "running" else None,
                    "started_ts": r.get("started_ts"), "heartbeat_ts": r.get("ts"), "heartbeat_age_s": w["age_s"],
                    "job_running_s": (now - job["started_ts"]) if (job and st == "running" and job["started_ts"]) else None,
                    "uptime_s": (r["ts"] - r["started_ts"]) if r.get("started_ts") else None,
                    "tasks_done": r.get("tasks_done"), "errors": r.get("errors"), "retries": r.get("retries"),
                    "last_result": r.get("last_result"), "next_action": r.get("next_action"), "detail": r.get("detail"),
                    "last_ok_ts": r.get("last_ok_ts"), "last_error": r.get("last_error"),
                    "last_error_ts": r.get("last_error_ts"), "kinds": list(kinds), "jobs_done_this_run": run_done,
                    "work": work, "pid": r.get("pid"), **made})
    return {"supervisor": wk["supervisor"], "agents": out, "total": len(out), "retired": retired,
            "active": sum(1 for a in out if a["status"] in ("running", "idle", "queued", "blocked")),
            "running": sum(1 for a in out if a["status"] == "running"),
            "job_agents_without_work": sum(1 for a in out if (a["work"] or "").startswith("no work")),
            "with_output_24h": sum(1 for a in out if a["output_24h"])}


AGENT_ACTORS = {"discovery-scanner": ("system:scanner",), "paper-1": ("system:paper",), "risk-1": ("system:risk",)}
NOT_OUTPUT = ("job.started", "job.retry", "job.failed", "job.timeout", "job.interrupted", "agent.error",
              "agent.recovered", "worker.error", "paper.error", "paper.refused", "paper.signal_while_paused",
              "paper.not_authorized", "paper.blocked", "paper.unsupported", "data.accessed",
              "data.refused")                     # bookkeeping (incl. the data gateway's read audit) and errors


def _actors(name):
    return (name, f"agent:{name}", f"system:{name}") + AGENT_ACTORS.get(name, ())


def _events_24h(db, now):
    """{actor: {kind: n}} for the last 24 h, plus the owners of lease timeouts (written by the queue)."""
    out = {}
    for r in db.q("SELECT actor, kind, COUNT(*) n FROM events WHERE ts>=? GROUP BY actor, kind", int(now - 86400)):
        out.setdefault(r["actor"], {})[r["kind"]] = r["n"]
    for r in db.q("SELECT payload FROM events WHERE kind='job.timeout' AND ts>=?", int(now - 86400)):
        owner = (_j(r["payload"]) or {}).get("owner")
        if owner:
            out.setdefault(owner, {})["job.timeout"] = out.get(owner, {}).get("job.timeout", 0) + 1
    return out


def _output_24h(made_by, name):
    """Recorded work of one agent in the last 24 h (hash-chained events under its own or its module's actor):
    finished jobs, failed attempts (retry, failure, lease timeout) and output = every event that is not bookkeeping
    or an error (job.done, scan.finished, market.event, paper.order, candidate.discovered, ...)."""
    kinds = {}
    for a in _actors(name):
        for k, n in made_by.get(a, {}).items():
            kinds[k] = kinds.get(k, 0) + n
    return {"jobs_done_24h": kinds.get("job.done", 0),
            "jobs_failed_24h": sum(kinds.get(k, 0) for k in ("job.retry", "job.failed", "job.timeout")),
            "output_24h": sum(n for k, n in kinds.items() if k not in NOT_OUTPUT)}


def agent_log(db, name, limit=50):
    """An agent's own events, including those its code writes under a module actor (scanner, paper engine, risk)."""
    actors = (name, f"agent:{name}", f"system:{name}") + AGENT_ACTORS.get(name, ())
    rows = db.q(f"SELECT id, ts, kind, exp_id, payload FROM events WHERE actor IN ({','.join('?' * len(actors))}) "
                f"ORDER BY id DESC LIMIT ?", *actors, int(limit))
    return {"agent": name, "events": [dict(r) | {"payload": _j(r["payload"])} for r in rows]}


# ---------- KPIs ----------
def last_data_update(db):
    """Newest data the lab used: research reads through the gateway and downloads, and live market data (the last
    scanner pass and the last hourly paper mark, both read from public markets)."""
    ds = db.one("SELECT MAX(ts) FROM datasets")[0]
    newest = None
    for sub in ("klines", "funding"):
        d = os.path.join(mdata.CACHE, sub)
        if os.path.isdir(d):
            for f in os.scandir(d):
                newest = max(newest or 0, f.stat().st_mtime)
    scan = db.one("SELECT MAX(ts) FROM events WHERE kind='scan.finished'")[0]
    mark = db.one("SELECT MAX(ts) FROM sim_equity")[0]
    srcs = {"research read": ds, "research download": newest, "scanner pass": scan, "paper mark": mark}
    best = max((v, k) for k, v in srcs.items() if v) if any(srcs.values()) else (None, None)
    return {"last_gateway_read_ts": ds, "last_download_ts": newest, "last_scan_ts": scan, "last_mark_ts": mark,
            "newest_ts": best[0], "newest_source": best[1]}


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
        "agents_with_output_24h": ag["with_output_24h"],
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
        "research": research_progress(db, now), "families": families_card(db, now),
        "last_event_id": db.one("SELECT COALESCE(MAX(id),0) FROM events")[0]}


# ---------- amendment 8 hypothesis families (read-only) ----------
FAMILY_VERIFY_S = 60          # the approval binding is checked with git at most once a minute (dashboard polls: 10 s)
_family_verified = {}         # (db path, approval event id, family) -> (checked ts, still valid)
REASON_DA = (                                   # the dashboard is Danish; the registry keeps the English reasons
    ("may not be downloaded before 2026-11-28", "filer mangler og må først hentes fra 2026-11-28 (ændring 8 punkt 17, "
                                                 "ændring 9 punkt 1)"),
    ("download failed", "en download fejlede; trinnet prøver igen om en time (familien stopper ikke)"),
    ("has not published", "arkivet har ikke udgivet vinduets sidste måned endnu; fremadtesten venter en dag"),
    ("base instance(s) not DISCOVERED", "basisinstanser er ikke genoplivet; genoplivning sker før approve-family "
                                        "(ændring 8 punkt 6)"),
    ("failed permanently", "et job fejlede permanent; familien er stoppet uden at lukke kohorten (ændring 8 punkt 15)"),
    ("fails closed", "en låst fil er ændret efter registreringen; familien fejler lukket (ændring 8 punkt 18)"),
    ("registration error", "fejl under registreringen; den prøves igen i næste gennemløb"),
    ("not acknowledged", "et kirkegårdsfund er ikke kvitteret i familiefilen (ændring 8 punkt 6)"),
    ("open experiment(s) outside the family", "et åbent eksperiment uden for familien dækker samme mekanisme "
                                              "(ændring 8 punkt 7)"),
    ("programme stopped", "programmet er stoppet; kun en ny dateret ændring genstarter det (ændring 8 punkt 15)"),
    ("families are already open", "der er allerede 3 åbne familier (ændring 8 punkt 3)"),
    ("per canonical tag", "grænsen for familier pr. mekanisme er nået (ændring 8 punkt 3)"),
    ("open family per tag", "en anden familie på samme mekanisme er stadig åben (ændring 8 punkt 3)"),
    ("approval is no longer valid", "registreringen stoppede halvvejs, og godkendelsen er ikke længere gyldig "
                                    "(ændring 8 punkt 5 og 7)"),
    ("successor trigger", "en efterfølger venter på sin udløser"),
    ("was not DISCOVERED when approve-family was requested", "en efterfølger blev genoplivet efter godkendelsen og "
                                                             "registreres aldrig (ændring 8 punkt 5, 6 og 9)"),
)


def reason_da(reason):
    """The Danish dashboard text of a family.waiting reason (the English reason stays in the registry and the tooltip)."""
    r = str(reason or "")
    return next((da for key, da in REASON_DA if key in r), r)


FAMILY_PROGRESS = ("family.approved", "family.revoked", "batch.registered", "cohort.fixed", "family.closed")
MEMBER_PROGRESS = ("job.done", "lifecycle.transition", "result.recorded", "family.interim", "holdout.opened")


def _family_events(db, kinds, fid):
    return [r for r in db.q(f"SELECT id, ts, kind, payload FROM events WHERE kind IN ({','.join('?' * len(kinds))}) "
                            f"ORDER BY id", *kinds) if (_j(r["payload"]) or {}).get("family") == fid]


def _family_approval(db, fid, now):
    """(state, event row): approved, void (a bound file or gate value changed since), revoked, or not approved."""
    from lab import families
    ev = _family_events(db, ("family.approved", "family.revoked"), fid)
    if not ev:
        return "not approved", None
    if ev[-1]["kind"] == "family.revoked":
        return "revoked", ev[-1]
    if families.registered(db, fid):                # registered: the approval its registration cited binds (point 18)
        ok = families.binding_approval(db, fid) is not None
        return ("approved" if ok else "registered; the family file or module changed since: every step fails "
                "closed (amendment 8 point 18)"), ev[-1]
    key = (db.path, ev[-1]["id"], fid)
    hit = _family_verified.get(key)
    if hit is None or now - hit[0] > FAMILY_VERIFY_S:
        hit = _family_verified[key] = (now, families.approval(db, fid) == ev[-1]["id"])
    return ("approved" if hit[1] else "void: a bound file or gate value changed since the approval"), ev[-1]


def _family_row(db, fid, now):
    from lab import families
    fam = families.load(fid)
    state, ev = _family_approval(db, fid, now)
    members, by_state = families.members(db, fid), {}
    for e in members:
        st = lifecycle.state(db, e)
        by_state[st] = by_state.get(st, 0) + 1
    held = db.q("SELECT alpha, note FROM alpha_ledger WHERE exp_id=? AND note IN (?, ?, ?)", f"family:{fid}",
                *families.A8_NOTES)                       # the A8 rows only, as families.reserved
    spent = sum(r[0] for r in db.q(f"SELECT alpha FROM alpha_ledger WHERE note=? AND exp_id IN "
                                   f"({','.join('?' * len(members))})", families.SPEND_NOTE, *members)) \
        if members else 0.0
    cf, c, waiting = families.cohort(db, fid), families.closed(db, fid), None
    w = _family_events(db, ("family.waiting",), fid)
    if w:
        p = _j(w[-1]["payload"]) or {}
        later = [r["id"] for r in _family_events(db, FAMILY_PROGRESS, fid)]
        if members:
            later.append(db.one(f"SELECT COALESCE(MAX(id), 0) FROM events WHERE kind IN "
                                f"({','.join('?' * len(MEMBER_PROGRESS))}) AND exp_id IN "
                                f"({','.join('?' * len(members))})", *MEMBER_PROGRESS, *members)[0])
        waiting = {"reasons": p.get("reasons"), "reasons_da": [reason_da(r) for r in p.get("reasons") or []],
                   "topic": p.get("topic") or "registration", "ts": w[-1]["ts"],
                   "current": w[-1]["id"] > max(later, default=0)}     # until a later step of the family
    return {"family": fid, "title": fam.get("title"), "tag": (fam.get("mechanism") or {}).get("tag"),
            "approval": state, "approval_event": ev["id"] if ev else None, "approval_ts": ev["ts"] if ev else None,
            "registered": families.registered(db, fid), "members": by_state,
            "alpha": {"family": (fam.get("alpha") or {}).get("family"),
                      "reserved": sum(r[0] for r in held),                # held for the family until a cohort uses it
                      "spent": spent,                                      # alpha_i of the cohort's instances
                      "released": -sum(r[0] for r in held if r[1] == families.RELEASE_NOTE)},
            "cohort": {k: cf.get(k) for k in ("cohort", "M", "alpha_F", "alpha_i", "window", "sub_window", "start",
                                              "end", "interim_not_before", "final_not_before", "selected",
                                              "not_selected")} if cf else None,
            "closed": c.get("outcome") if c else None, "waiting": waiting}


def families_card(db, now=None):
    """Amendment 8, read-only: each committed family file with its approval state, alpha reserved/spent/released, the
    fixed cohort and its forward windows, the close and the latest waiting reason ('current' until a later step of the
    family). Approvals are typed in a terminal only (python3 -m lab approve-family / confirm-family): no endpoint."""
    from lab import families
    now = now or time.time()
    try:
        fids = families.family_ids()
    except OSError:
        fids = []
    rows = []
    for fid in fids:
        try:
            rows.append(_family_row(db, fid, now))
        except Exception as e:                    # one broken family file never breaks the KPIs
            rows.append({"family": fid, "error": repr(e)[:200]})
    used = families.alpha_reserved(db)
    return {"families": rows, "W0": families.W0, "alpha_used": used, "alpha_left": families.W0 - used,
            "open": sorted(families.open_families(db)), "open_max": families.OPEN_MAX,
            "programme_stop": families.programme_stop(db, now),
            "approval": "terminal only: python3 -m lab approve-family / confirm-family (amendment 8 point 5)"}


def _untested_templates(db):
    from lab.engine import catalogue
    known = {r[0] for r in db.q("SELECT DISTINCT exp_id FROM experiments")}
    return [t for t in catalogue.TEMPLATES if catalogue.exp_id(t) not in known]


def research_progress(db, now=None):
    """Is the lab doing research? Last finished job, last verdict, runnable work, and why it is idle."""
    from lab.engine import catalogue
    now = now or time.time()
    run = jobs.runnable(db, now)
    busy = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM jobs WHERE status IN "
                                              "('running', 'blocked') GROUP BY status")}
    side = ",".join(f"'{k}'" for k in NON_STAGE_KINDS)        # diagnostics and scan research: not pipeline work
    last_done = db.one(f"SELECT MAX(ts) FROM events WHERE kind='job.done' AND "
                       f"COALESCE(json_extract(payload, '$.kind'), '') NOT IN ({side})")[0]
    last_side = db.one(f"SELECT MAX(ts) FROM events WHERE kind='job.done' AND "
                       f"json_extract(payload, '$.kind') IN ({side})")[0]
    last_verdict = db.one("SELECT MAX(ts) FROM results")[0]
    last_exp = db.one("SELECT MAX(created_ts) FROM experiments WHERE substr(exp_id, 1, 2)='E_'")[0]
    untested = _untested_templates(db)
    reasons = []
    if not run["total"] and not busy.get("running"):
        reasons.append("no runnable or running job" + (f" ({busy['blocked']} blocked on dependencies)"
                                                        if busy.get("blocked") else ""))
        if not untested:
            reasons.append(f"catalogue exhausted: all {len(catalogue.TEMPLATES)} templates have an experiment")
        if run["next_due_ts"]:
            reasons.append(f"next queued job due {time.strftime('%Y-%m-%d', time.gmtime(run['next_due_ts']))}")
    return {"runnable_jobs": run["total"], "runnable_by_kind": run["by_kind"], "next_job_due_ts": run["next_due_ts"],
            "running_jobs": busy.get("running", 0), "blocked_jobs": busy.get("blocked", 0),
            "last_side_job_done_ts": last_side, "last_job_done_ts": last_done, "last_job_done_age_s": (now - last_done) if last_done else None,
            "last_verdict_ts": last_verdict, "last_verdict_age_s": (now - last_verdict) if last_verdict else None,
            "last_new_experiment_ts": last_exp, "untested_templates": untested,
            "idle_reason": "; ".join(reasons) or None,
            "last_scan_ts": db.one("SELECT MAX(ts) FROM events WHERE kind='scan.finished'")[0],
            "scans_24h": db.one("SELECT COUNT(*) FROM events WHERE kind='scan.finished' AND ts>=?", int(now - 86400))[0],
            "diagnostics_total": db.one("SELECT COUNT(*) FROM events WHERE kind='research.diagnostic'")[0],
            "market_events_24h": db.one("SELECT COUNT(*) FROM events WHERE kind='market.event' AND ts>=?",
                                        int(now - 86400))[0]}


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
    name, explain, round_ = plain(db, eid)
    return {
        "exp_id": eid, "name": name, "explain": explain, "round": round_, "status_plain": STATE_PLAIN.get(st, st),
        "reason_plain": short_reason(((res or {}).get("verdict") or (tr_reason["reason"] if tr_reason else None)))
        if st in ("REJECTED", "SUPPRESSED", "WITHDRAWN") else None,
        "title": spec.get("title") or spec.get("hypothesis") or eid, "template": spec.get("template"),
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


EDGE_MIN_DAYS = 2               # amendment 9 section 4: a z-value needs at least two daily returns
EDGE_WATCH_DAYS, EDGE_WATCH_Z = 14, -3.0      # the watcher mentions (never fails on) a ledger this far below


def _base(ledger):
    for p in ("SHADOW_", "FWD_"):
        if ledger.startswith(p):
            return ledger[len(p):]
    return ledger


def edge(db, ledger, now=None, expectation=True):
    """Non-decisional edge monitoring (research/PROTOCOL_V3.md amendment 9 section 4). Live: daily closes (the last
    hourly mark of each finished UTC day) of sim_equity, which is after costs and includes funding from T_F; one
    return per pair of consecutive closes. Expectation: mean and sd of daily_net in the base experiment's
    hash-verified validate.json. z = (live mean - expected mean) / (expected sd / sqrt(days)) from EDGE_MIN_DAYS days.
    Decides nothing: pauses follow only the risk rules, and a good stretch is never a PASS. Uses only db.q/db.one
    (the watcher calls it on a read-only connection)."""
    import statistics
    from lab import pipeline
    from lab.paper import funding_t0
    now = now or time.time()
    rows = db.q("SELECT ts, equity FROM sim_equity WHERE exp_id=? ORDER BY id", ledger)
    today, closes = int(now) // 86400 * 86400, {}
    for x in rows:
        if x["ts"] < today:
            closes[x["ts"] // 86400] = x["equity"]
    days = sorted(closes)
    pairs = [(closes[b] / closes[a] - 1, closes[b] - closes[a]) for a, b in zip(days, days[1:]) if closes[a] > 0]
    n = len(pairs)
    live = statistics.mean(p[0] for p in pairs) if n else None
    out = {"days_live": (now - rows[0]["ts"]) / 86400 if rows else 0.0, "days": n, "net_per_day_pct": live,
           "net_per_day": statistics.mean(p[1] for p in pairs) if n else None, "t_f": funding_t0(db),
           "expectation": None, "no_expectation": None, "z": None, "decisional": False,
           "basis": "daily closes of sim_equity after costs, funding included from T_F; validate.json daily_net"}
    if not expectation:
        return out
    try:
        series = pipeline.frozen_artifact(db, _base(ledger), "validate").get("daily_net") or []
        why = "ingen valideringsserie i validate.json"
    except Exception as e:                              # display only: no verified series, no expectation
        series, why = [], str(e)
    if len(series) < 2:
        out["no_expectation"] = f"ingen forventning ({why})"
        return out
    m, sd = statistics.mean(series), statistics.stdev(series)
    out["expectation"] = {"mean": m, "sd": sd, "days": len(series), "source": "validate.json daily_net (hash-verified)"}
    if n >= EDGE_MIN_DAYS and sd > 0:
        out["z"] = (live - m) / (sd / math.sqrt(n))
    return out


def _pause_info(rk, eid):
    """Why a paused ledger is paused (its last PAUSE risk event) and how a human resumes a simulated one, or None."""
    if not rk.paused(eid):
        return None
    r = rk._last(eid, ("PAUSE",))
    sim = eid.startswith(("SHADOW_", "FWD_", "LANE_"))
    return {"rule": r["rule"], "detail": r["detail"], "ts": r["ts"],
            "resume": f'python3 -m lab sim-resume {eid} --reason "..." (typed in a terminal)' if sim else
            "revalidation and a human approval (amendment 4)"}


def paper_view(db, reconcile=True, edges=True, now=None):
    """Every paper ledger. P&L is as of its last hourly mark: realized (closed trades, fees and booked funding) from a
    replay of the ledger up to the mark, unrealized = position value at the mark minus cost basis."""
    from lab import lane
    from lab.paper import PaperEngine, forward_active, funding_t0
    now = now or time.time()
    pe, rk, out = PaperEngine(db), Risk(db), []
    lanes = lane.started(db)
    for r in db.q("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started' ORDER BY exp_id"):
        eid = r[0]
        led = pe.ledger(eid)
        eq = [dict(e) for e in db.q("SELECT ts, equity, cash, exposure, peak, drawdown FROM sim_equity WHERE exp_id=? "
                                    "ORDER BY id", eid)]
        last = eq[-1] if eq else None
        if last:
            at = pe.ledger(eid, until=last["ts"])
            realized = at["realized"]
            unreal = (last["equity"] - last["cash"]) - sum(q * at["basis"][i] for i, q in at["positions"].items())
        else:
            realized, unreal = led["realized"], None
        day = int(now) // 86400 * 86400
        before = [e for e in eq if e["ts"] < day]
        today = ([before[-1]] if before else []) + [e for e in eq if e["ts"] >= day]
        day_peak = max((e["equity"] for e in today), default=None)
        daily_dd = ((day_peak - today[-1]["equity"]) / day_peak) if (today and day_peak) else None
        orders = db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", eid)[0]
        refused = db.one("SELECT COUNT(*) FROM events WHERE exp_id=? AND kind IN ('paper.refused',"
                         "'paper.signal_while_paused')", eid)[0]
        shadow, forward, is_lane = eid.startswith("SHADOW_"), eid.startswith("FWD_"), eid.startswith(lane.PREFIX)
        base = eid[len("SHADOW_"):] if shadow else eid[len("FWD_"):] if forward else eid
        out.append({"exp_id": eid, "name": plain(db, eid)[0], "shadow": shadow, "forward": forward, "lane": is_lane,
                    "active": forward_active(db, base) if forward else lane.is_active(db, eid) if is_lane else None,
                    "state": None if is_lane else lifecycle.state(db, base), "simulated": True,
                    "lane_info": ({**lanes.get(eid, {}), "stats": lane.stats(db, eid, now, lanes.get(eid)),
                                   "rules": lane.rules_text(lanes.get(eid)), "scanner": lane.is_scanner(lanes.get(eid)),
                                   "retired": (lane.retired(db).get(eid) if not lane.is_active(db, eid) else None)}
                                  if is_lane else None),
                    "label": (lane.label(lanes.get(eid)) if is_lane else
                              "SKYGGEHANDEL (simuleret, ikke godkendt, inkl. funding fra T_F)" if shadow else
                              "FREMADTEST (simuleret, ikke godkendt, inkl. funding fra T_F)" if forward else
                              "PAPER (simulated, incl. funding from T_F)"),
                    "capital": led["capital"], "cash": led["cash"], "positions": led["positions"],
                    "open_positions": len(led["positions"]), "closed_trades": len(led["trades"]),
                    "equity": eq, "realized": realized, "unrealized": unreal, "fees": led["fees"],
                    "funding": led["funding"],
                    "total_pnl": (last["equity"] - led["capital"]) if last else None,
                    "max_drawdown": max((e["drawdown"] for e in eq), default=None),
                    "daily_drawdown": daily_dd,
                    "orders": orders, "fills": db.one("SELECT COUNT(*) FROM sim_fills WHERE exp_id=?", eid)[0],
                    "rejected_orders": refused, "reconciliation": pe.reconcile(eid) if reconcile else None,
                    "paused": rk.paused(eid), "warming": rk.warming(eid), "pause": _pause_info(rk, eid),
                    "edge": edge(db, eid, now) if (edges and not is_lane) else None})
    out.sort(key=lambda s: (s["lane"], s["forward"], s["shadow"], s["exp_id"]))  # approved, shadow, forward, lane
    return {"strategies": out, "simulated": True, "real_account_profit": REAL_ACCOUNT, "funding_t0": funding_t0(db),
            "source": "lab.db sim_orders / sim_fills / sim_equity / sim_funding (simulated fills against public order "
                      "books; settled funding from T_F)",
            "eligible": [x["exp_id"] for x in registry.status(db) if x["state"] == "VALIDATED"]}


def rejected(db, limit=100):
    out = []
    for x in registry.status(db):
        if x["state"] not in ("REJECTED", "SUPPRESSED", "WITHDRAWN"):
            continue
        r = experiment_record(db, x)
        out.append({"exp_id": r["exp_id"], "name": r["name"], "round": r["round"], "reason_plain": r["reason_plain"],
                    "state": r["state"], "mechanism": r["mechanism"], "market": r["market"],
                    "reason": r["rejection_reason"], "failed_gates": r["failed_gates"],
                    "pattern": mission.FAILURE_PATTERN.get(r["exp_id"]),
                    "ts": db.one("SELECT MAX(ts) FROM transitions WHERE exp_id=?", r["exp_id"])[0]})
    out.sort(key=lambda r: -(r["ts"] or 0))
    return {"items": out[:limit], "total": len(out)}


# ---------- money box and event feed (Mission 7 dashboard) ----------
MONEY = ("capital", "equity", "pnl", "realized", "unrealized", "fees", "funding")
BAL_TOL = 1e-6


def _eq(s):
    return s["equity"][-1]["equity"] if s["equity"] else s["capital"]


def _money(rows):
    """Sums over ledgers (None when there is none)."""
    if not rows:
        return {k: None for k in MONEY}
    cap, eq = sum(s["capital"] for s in rows), sum(_eq(s) for s in rows)
    return {"capital": cap, "equity": eq, "pnl": eq - cap, "realized": sum(s["realized"] or 0 for s in rows),
            "unrealized": sum(s["unrealized"] or 0 for s in rows), "fees": sum(s["fees"] for s in rows),
            "funding": sum(s["funding"] for s in rows)}


def _balance_reconciliation(db, out, st, fw):
    """Amendment 9 section 5: the overview adds up, to BAL_TOL. Per ledger equity - capital = realized + unrealized
    (realized from the ledger's own trades and funding, so this checks the stored mark against the fills); the formal
    and forward blocks are the sums of their ledgers; combined = formal + forward; fees and funding equal the
    sim_fills / sim_funding table sums for the same ledgers."""
    checks = []

    def chk(name, a, b):
        checks.append({"check": name, "ok": abs((a or 0) - (b or 0)) <= BAL_TOL, "diff": (a or 0) - (b or 0)})
    for s in st + fw:
        chk(f"{s['exp_id']}: equity - capital = realized + unrealized", _eq(s) - s["capital"],
            (s["realized"] or 0) + (s["unrealized"] or 0))
    formal, fwd, comb = {k: out[k] for k in MONEY}, out["forward"], out["combined"]
    for k in MONEY:
        if st:
            chk(f"formal {k} = sum of formal ledgers", formal[k], _money(st)[k])
        if fw:
            chk(f"forward {k} = sum of forward ledgers", fwd[k], _money(fw)[k])
        chk(f"combined {k} = formal + forward", comb[k], (formal[k] or 0) + (fwd[k] or 0))
    ids = [s["exp_id"] for s in st + fw]
    marks = ",".join("?" * len(ids))
    fees = db.one(f"SELECT COALESCE(SUM(fee), 0) FROM sim_fills WHERE exp_id IN ({marks})", *ids)[0] if ids else 0.0
    fund = db.one(f"SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id IN ({marks})", *ids)[0] if ids else 0.0
    chk("fees = sim_fills table sum", comb["fees"], fees)
    chk("funding = sim_funding table sum", comb["funding"], fund)
    other = {"fees": db.one(f"SELECT COALESCE(SUM(fee), 0) FROM sim_fills WHERE exp_id NOT IN ({marks})", *ids)[0],
             "funding": db.one(f"SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id NOT IN ({marks})",
                               *ids)[0]} if ids else None
    bad = [c["check"] for c in checks if not c["ok"]]
    return {"ok": not bad, "tolerance": BAL_TOL, "checks": len(checks), "problems": bad,
            "details": [c for c in checks if not c["ok"]] or None, "outside_ledgers": other}


def balance(db, now=None):
    """_balance on ONE read snapshot, so the reconciliation never compares numbers read before and after a write."""
    own = not db.con.in_transaction
    if own:
        db.con.execute("BEGIN")
    try:
        return _balance(db, now)
    finally:
        if own:
            db.con.execute("COMMIT")


def _balance(db, now=None):
    """Simulated paper account. The formal headline (capital ... history) is every approved paper and shadow ledger,
    as before; forward tests (amendment 7) are never in it. Amendment 9 section 5 adds, for display only: `forward`
    (the forward-test ledgers), `combined` (formal + forward, simulated and not approved) and `reconciliation`.
    No real account exists."""
    now = now or time.time()
    p = paper_view(db, reconcile=False, edges=False, now=now)   # no reconciliation here (risk-1 does it) or edge
    fw = [s for s in p["strategies"] if s.get("forward")]      # amendment 7: never in the headline numbers
    ln = [s for s in p["strategies"] if s.get("lane")]         # amendment 11: never in any headline or combined sum
    st = [s for s in p["strategies"] if not s.get("forward") and not s.get("lane")]
    active = [s for s in st if s["state"] == "PAPER_TRADING" or (s["shadow"] and s["state"] == "OBSERVATION")
              or s["state"] == "PAUSED"]
    out = {"simulated": True, "strategies": len(st),
           "forward": {**_money(fw), "ledgers": len(fw), "open_positions": sum(s["open_positions"] for s in fw),
                       "paused": sum(1 for s in fw if s["paused"]),
                       "running": sum(1 for s in fw if s["active"] and not s["paused"]),
                       "simulated": True, "approved": False, "label": "FREMADTEST (simuleret, ikke godkendt)"},
           "lane": {**_money(ln), "ledgers": len(ln), "running": sum(1 for s in ln if s["active"] and not s["paused"]),
                    "scanner": sum(1 for s in ln if (s.get("lane_info") or {}).get("scanner")),
                    "active": sum(1 for s in ln if s["active"]), "paused": sum(1 for s in ln if s["paused"]),
                    "open_positions": sum(s["open_positions"] for s in ln), "simulated": True, "approved": False,
                    "evidence": False, "label": "BANE- OG SCANNERKONTI (simuleret, aldrig bevis)"},
           "active": sum(1 for s in st if s["state"] == "PAPER_TRADING" or (s["shadow"] and s["state"] == "OBSERVATION")),
           "trading": sum(1 for s in active if not s["paused"] and s["state"] != "PAUSED"),
           "paused": sum(1 for s in active if s["paused"] or s["state"] == "PAUSED"),
           "shadow": sum(1 for s in st if s["shadow"]), "funding_t0": p["funding_t0"],
           "real_account_profit": REAL_ACCOUNT, "source": p["source"]}
    if not st:
        out.update({"capital": None, "equity": None, "pnl": None, "pnl_pct": None, "today": None, "realized": None,
                    "unrealized": None, "fees": None, "funding": None, "open_positions": 0, "closed_trades": 0,
                    "win_rate": None, "history": []})
        _combine(db, out, st, fw)
        return out
    capital = sum(s["capital"] for s in st)
    last = {s["exp_id"]: (s["equity"][-1]["equity"] if s["equity"] else s["capital"]) for s in st}
    equity = sum(last.values())
    pts, cur = [], {}
    for ts, eid, eq in sorted((e["ts"], s["exp_id"], e["equity"]) for s in st for e in s["equity"]):
        cur[eid] = eq
        total = sum(cur.get(s["exp_id"], s["capital"]) for s in st)
        if pts and pts[-1][0] == ts:
            pts[-1] = (ts, total)
        else:
            pts.append((ts, total))
    day0 = int(now) // 86400 * 86400
    before = [v for ts, v in pts if ts < day0]
    start_today = before[-1] if before else capital
    trades = [t for s in st for t in __import__("lab.paper", fromlist=["PaperEngine"]).PaperEngine(db).ledger(s["exp_id"])["trades"]]
    wins = sum(1 for _, pnl in trades if pnl > 0)
    out.update({"capital": capital, "equity": equity, "pnl": equity - capital, "pnl_pct": (equity - capital) / capital,
                "today": equity - start_today, "realized": sum(s["realized"] or 0 for s in st),
                "unrealized": sum(s["unrealized"] or 0 for s in st), "open_positions": sum(s["open_positions"] for s in st),
                "fees": sum(s["fees"] for s in st), "funding": sum(s["funding"] for s in st),
                "closed_trades": len(trades), "win_rate": (wins / len(trades)) if trades else None,
                "history": [{"ts": ts, "equity": v} for ts, v in pts]})
    _combine(db, out, st, fw)
    return out


def _combine(db, out, st, fw):
    """combined = formal headline + forward block, flagged simulated and not approved; then the reconciliation."""
    f = out["forward"]
    out["combined"] = {k: ((out[k] or 0) + (f[k] or 0)) if (st or fw) else None for k in MONEY} | {
        "ledgers": len(st) + len(fw), "simulated": True, "approved": False,
        "label": "SIMULERET SAMLET (ikke godkendt)", "parts": "formel saldo + fremadtest; intet tælles to gange"}
    out["reconciliation"] = _balance_reconciliation(db, out, st, fw)


STAGE_DA = {"DISCOVERED": "opdaget", "SUPPRESSED": "sorteret fra", "REGISTERED": "registreret", "SCREENING": "testes",
            "SCREEN_PASSED": "bestod screening", "VALIDATION": "holdout åbnet", "VALIDATED": "bestod holdout",
            "OBSERVATION": "sat til observation på nye data (simuleret)",
            "PAPER_TRADING": "handler nu (paper)", "PAUSED": "sat på pause", "REJECTED": "afvist",
            "RETIRED": "pensioneret", "WITHDRAWN": "trukket tilbage"}
TAG_OF_STATE = {"OBSERVATION": "OBSERVERES", "SCREEN_PASSED": "BESTÅET", "VALIDATED": "GODKENDT", "PAPER_TRADING": "HANDLER", "REJECTED": "AFVIST",
                "PAUSED": "PAUSE", "VALIDATION": "HOLDOUT", "SCREENING": "TEST", "REGISTERED": "TEST",
                "SUPPRESSED": "SORTERET"}
FOUND_STATES = ("SCREEN_PASSED", "VALIDATED", "PAPER_TRADING")


def short_reason(reason):
    """Short Danish summary of a verdict for the feed (the full text stays available as `detail`)."""
    r = reason or ""
    n = len([x for x in r.split("failed", 1)[-1].split(",") if x.strip()]) if "failed" in r else 0
    for key, da in (("at train gate", "afvist i første test: dårligere end bare at købe og holde"),
                    ("before validation", "afvist i første test: kunne ikke skelnes fra tilfældighed"),
                    ("at cost check", "afvist: taber penge efter gebyrer"),
                    ("at validation", f"afvist i anden test: {n} af kravene ikke opfyldt" if n else "afvist i anden test"),
                    ("FAIL (holdout)", "afvist i slut-testen"), ("FAIL (paper", "afvist efter simuleret handel"),
                    ("matches rejected", "sorteret fra: samme idé er allerede afvist"),
                    ("circuit breaker", "sat på pause af risikostyring")):
        if key in r:
            return da
    return r[:120]


def feed(db, limit=40):
    from lab import scanresearch as sr                       # Danish texts for research events (stored events unchanged)
    kinds = ("candidate.discovered", "lifecycle.transition", "batch.registered", "template.approved", "paper.order",
             "job.failed", "system.running", "system.stopped", "system.stop_forced", "system.paused", "system.resumed",
             "system.resource_hold", "risk.pause", "risk.fail_closed", "risk.clear", "agent.error",
             "agent.recovered", "external.stale", "external.recovered", "job.timeout", "market.event",
             "research.diagnostic", "scan.finished", "forward.approved", "forward.stopped", "research.digest",
             "research.dossier", "lane.started", "lane.retired", "lane.promising")
    rows = db.q(f"SELECT id, ts, kind, actor, exp_id, payload FROM events WHERE kind IN ({','.join('?' * len(kinds))}) "
                f"AND NOT (kind='paper.order' AND substr(exp_id, 1, 4)='FWD_') "     # shown per account instead
                f"AND NOT (kind='paper.order' AND substr(exp_id, 1, 5)='LANE_') "
                f"ORDER BY id DESC LIMIT ?", *kinds, int(limit))
    out = []
    for r in rows:
        p = _j(r["payload"]) or {}
        e = {"id": r["id"], "ts": r["ts"], "exp_id": r["exp_id"], "found": False, "pnl": None}
        nm = plain(db, r["exp_id"])[0] if r["exp_id"] else None
        k = r["kind"]
        if k == "candidate.discovered":
            e.update(tag="IDÉ", text=f"Ny idé: {nm}")
        elif k == "lifecycle.transition":
            to = p.get("to")
            short = short_reason(p.get("reason")) if to in ("REJECTED", "PAUSED", "SUPPRESSED") else None
            e.update(tag=TAG_OF_STATE.get(to, "STATUS"), found=to in FOUND_STATES, detail=p.get("reason"),
                     text=f"{nm}: {short}" if short else f"{nm}: {STAGE_DA.get(to, to)}")
        elif k == "batch.registered":
            e.update(tag="TEST", text=f"Ny testrunde startet: {', '.join(plain(db, x)[0] for x in p.get('exp_ids', []))}")
        elif k == "template.approved":
            e.update(tag="GODKENDT", text=f"Godkendt til test: {TEMPLATE_DA.get(p.get('template'), (p.get('template'),))[0]}")
        elif k == "paper.order":
            o = db.one("SELECT side, instrument, qty FROM sim_orders WHERE order_id=?", p.get("order_id"))
            side = (o["side"] if o else "?")
            e.update(tag="KØB" if side == "buy" else "SÆLG",
                     text=f"{nm}: {'køb' if side == 'buy' else 'salg'} {o['instrument'] if o else ''} "
                          f"(simuleret, fyldt {p.get('filled', 0):.4g})")
        elif k == "job.failed":
            e.update(tag="FEJL", text=f"En opgave fejlede ({str(p.get('job_id', '')).split('|')[0]}) — prøves ikke igen automatisk",
                     detail=str(p.get("error", "")))
        elif k == "system.running":
            e.update(tag="START", text=f"Flåden startet ({len(p.get('workers', []))} agenter)")
        elif k == "system.stopped":
            e.update(tag="STOP", text="Flåden stoppet")
        elif k == "system.stop_forced":
            e.update(tag="STOP", text=f"Flåden stoppet med magt ({p.get('signal')}): den svarede ikke")
        elif k == "system.paused":
            e.update(tag="PAUSE", text=f"Flåden sat på pause: {p.get('reason', '')}")
        elif k == "system.resumed":
            e.update(tag="START", text="Flåden genoptaget")
        elif k == "system.resource_hold":
            e.update(tag="RESSOURCER", text="Lav RAM eller disk: nye jobs holdes tilbage")
        elif k == "agent.error":
            e.update(tag="FEJL", text=f"Agenten {p.get('agent')} fejler — markeret rød, indtil den virker igen",
                     detail=str(p.get("error", "")))
        elif k == "agent.recovered":
            e.update(tag="OK", text=f"Agenten {p.get('agent')} virker igen")
        elif k == "external.stale":
            e.update(tag="FEJL", text=f"{p.get('label')} har ikke skrevet data i {int(p.get('last_write_age_s', 0)) // 60} "
                                      f"min — tjek at den kører", detail=r["exp_id"])
        elif k == "external.recovered":
            e.update(tag="OK", text=f"{p.get('label')} skriver data igen")
        elif k == "market.event":
            key = p.get("key") or {}
            what = f"{sr.metric_da(key.get('metric'))} {key.get('instrument') or key.get('source') or ''}".strip()
            e.update(tag="UNDERSØG" if p.get("decision") == "INVESTIGATE" else "INGEN HANDLING",
                     text=f"Marked: {what} - {sr.why_da(p.get('why'), STAGE_DA)}"[:220], detail=p.get("decision"),
                     priority=p.get("priority"))
        elif k in ("lane.started", "lane.retired", "lane.promising"):
            e.update(tag="BANEKONTO", text=(f"{nm} startet (simuleret, aldrig bevis)" if k == "lane.started"
                                            else f"{nm} stoppet: {p.get('detail')}" if k == "lane.retired"
                                            else f"{nm} lovende: kandidat til et familieudkast")[:220])
        elif k in ("forward.approved", "forward.stopped"):
            e.update(tag="FREMADTEST", text=f"Fremadtest {'startet' if k == 'forward.approved' else 'stoppet'}: "
                                            f"{nm} (simuleret, ikke godkendt)")
        elif k == "scan.finished":
            e.update(tag="SØGNING", text=f"Søgning: {p.get('observations', 0)} målinger · {p.get('flagged', 0)} markeret · "
                                        f"{p.get('proposals', 0)} forslag · {len(p.get('created') or [])} nye · "
                                        f"{p.get('investigate', 0)} undersøges")
        elif k == "research.diagnostic":
            e.update(tag="LÆRDOM", text=f"{nm}: " + "; ".join(sr.lesson_da(x) for x in p.get("lessons") or [])[:200])
        elif k == "research.digest":
            e.update(tag="UNDERSØG" if p.get("investigate") else "SØGNING", text=sr.digest_da(p)[:220],
                     detail=p.get("artifact_sha256"))
        elif k == "research.dossier":
            e.update(tag="UNDERSØG" if p.get("advice") == "family_draft" else "SØGNING",
                     text=sr.dossier_da(p)[:220], detail=p.get("recommendation"))
        elif k in ("risk.pause", "risk.fail_closed", "risk.clear"):
            e.update(tag="RISIKO", text=f"Risiko: {nm + ' - ' if nm else ''}{k.split('.')[1]} - {p.get('rule')}: "
                                        f"{p.get('detail')}"[:220])
        elif k == "job.timeout":
            e.update(tag="FEJL", text=f"Et job tog for lang tid: {p.get('job_id')}")
        else:
            e.update(tag=k.upper(), text=k)
        out.append(e)
    return {"items": out}


# ---------- plain-language names (Mission 7: less code language in the dashboard) ----------
TEMPLATE_DA = {
    "vol_managed_long": ("Rolig-marked-køb", "Køber mønterne, men skruer ned for indsatsen, når markedet er uroligt"),
    "day_of_week": ("Ugedags-mønster", "Er kun med på bestemte ugedage"),
    "hour_of_day": ("Bedste timer på døgnet", "Køber kun i de timer, der historisk steg mest"),
    "funding_contrarian": ("Mod flokken (funding)", "Går imod flokken, når finansieringsrenten er ekstrem"),
    "daily_reversal": ("Dagens tilbagefald", "Satser på, at et meget stort dagsudsving delvist vender"),
    "donchian_trend": ("Trendfølger", "Køber nye toppe og sælger nye bunde"),
    "xs_momentum": ("Momentum", "Køber de stærkeste mønter og sælger de svageste"),
    "xs_max_lottery": ("Anti-lotteri", "Sælger mønter med vilde hop og køber de rolige"),
    "xs_low_volatility": ("Lav uro", "Køber de roligste mønter og sælger de mest urolige"),
    "xs_betting_against_beta": ("Lav markedsfølsomhed", "Køber mønter, der følger markedet mindst, og sælger dem, der følger mest"),
    "xs_illiquidity": ("Illikvid-præmie", "Køber de mindst handlede mønter og sælger de mest handlede (30 mønter)"),
    "xs_high_volume": ("Volumen-spring", "Køber mønter med usædvanligt meget handel og sælger dem med usædvanligt lidt (30 mønter)"),
    "xs_downside_beta": ("Nedturs-risiko", "Køber mønter, der falder mest med markedet på dårlige dage, og sælger de mest stabile (30 mønter)"),
    "xs_coskewness": ("Skævheds-præmie", "Køber mønter, der giver porteføljen flere store fald, og sælger det modsatte (30 mønter)"),
    "xs_near_high": ("Tæt på toppen", "Køber mønter tæt på deres seneste top og sælger dem langt under (30 mønter)"),
    "turn_of_month": ("Månedsskifte", "Er kun med i dagene omkring månedsskiftet (30 mønter)"),
    "btc_lead_lag": ("Følg Bitcoin", "Efter et stort Bitcoin-hop handles de andre mønter samme vej næste dag (30 mønter)"),
    "oi_growth": ("Åben-interesse-vækst", "Køber mønter, hvor flere penge bindes i futures, og sælger dem, hvor pengene trækkes ud"),
    "oi_confirmed_return": ("Ny penge eller short-dækning", "Følger kursbevægelser med nye penge bag sig og går imod dem uden"),
    "smart_vs_crowd": ("Smart money mod flokken", "Følger de største tradere, når de er mere optimistiske end de almindelige konti"),
    "leverage_cycle": ("Gearings-cyklus", "Holder markedet, men går ud, når gearingen bygges hurtigere op end kurserne"),
    "vrp_timing": ("Frygtpræmie", "Holder BTC og ETH, når optionsmarkedet betaler ekstra for beskyttelse"),
    "stablecoin_flow": ("Stablecoin-tilførsel", "Holder markedet, når der kommer flere stablecoins i omløb"),
    "btc_volume_share": ("Bitcoin-dominans (volumen)", "Køber BTC mod resten, når Bitcoins andel af handlen stiger, og omvendt"),
    "real_rate_filter": ("Realrente-filter", "Holder markedet, når de reale renter falder eller står stille, og går ud, når de stiger"),
    "supply_dilution": ("Udvanding", "Køber mønter med få nye tokens og sælger dem med mange (16 mønter)"),
    "mvrv_value": ("Værdi på kæden (MVRV)", "Køber mønter tæt på ejernes gennemsnitspris og sælger dem med store papirgevinster (16 mønter)"),
    "taker_pressure": ("Købspres", "Køber mønter med usædvanligt aggressive køb og sælger dem med det modsatte"),
}
LEGACY_DA = {
    "L01_copy_kol": "Kopiér kendte wallets", "L02_self_found_traders": "Kopiér selvfundne tradere",
    "L03_sol_trend_hourly": "SOL-trend pr. time", "L04_buy_graduations": "Køb nye pump.fun-mønter",
    "L05_graduation_sniper": "Sniper på nye mønter", "L06_short_new_hl_listings": "Sælg nye Hyperliquid-mønter",
    "L07_funding_carry_v0": "Funding-rente (første version)", "L08_funding_carry_leverage": "Funding-rente med gearing",
    "L09_stop_when_ahead": "Stop når foran", "L10_launch_v1": "Udvælg nye mønter tidligt",
    "L11_smart_v2": "Følg tidlige købere", "L12_arb_v1": "Prisforskel mellem to børser (SOL)",
    "L13_carry_v1": "Funding-rente uden kursrisiko", "L14_tsmom_v1": "Ugentlig trend BTC/ETH/SOL",
    "L15_tsmom_v2": "Bred trend på mange mønter", "L16_pmcal_v1": "Polymarket favorit-skævhed",
    "L17_p1_btc15m_model": "BTC op/ned på 15 min", "L18_p2_negrisk_arb": "Polymarket prisfejl",
    "L19_p3_maker_fills": "Passive ordrer på Polymarket", "L20_m1_orderflow": "Ordrestrøms-ubalance",
    "L21_m2_liquidation_reversal": "Køb efter tvangslukninger", "L22_m3_premium_convergence": "Præmie-udligning på perps",
    "X01_pm_lp_v1": "Polymarket likviditets-belønning", "X02_copybot_paper": "CopyBot paper-test",
    "X03_funding_live_v0": "Funding live paper-test", "C_0755f34d6d": "Perp-præmie vender (scanner-fund)",
    "C_ce89a47faa": "Prisforskel Hyperliquid/Binance (scanner-fund)",
}


def plain(db, eid):
    """(name, one-line explanation, version label) for any experiment id."""
    if eid and eid.startswith("SHADOW_"):
        n, x, v = plain(db, eid[len("SHADOW_"):])
        return f"{n} — skyggehandel", x, v
    if eid and eid.startswith("FWD_"):
        n, x, v = plain(db, eid[len("FWD_"):])
        return f"{n} — fremadtest", x, v
    if eid and eid.startswith("LANE_"):
        r = db.one("SELECT payload FROM events WHERE kind='lane.started' AND exp_id=? ORDER BY id LIMIT 1", eid)
        p = _j(r["payload"]) if r else {}
        if (p or {}).get("source") == "scanner":
            return (f"Scannerkonto {((p.get('coins') or ['?'])[0])}", "Scannerens perp-præmie handlet live på papir; "
                    "aldrig bevis", None)
        return (f"Banekonto {(p or {}).get('family', '?')}.{(p or {}).get('function', '?')} "
                f"({len((p or {}).get('coins') or [])} mønter)", "Udforskning fra banen, handlet live på papir; aldrig bevis",
                None)
    if eid in LEGACY_DA:
        return LEGACY_DA[eid], None, None
    v = registry.latest(db, eid) if eid else None
    spec = _j(v["spec_json"]) if v else {}
    t = (spec or {}).get("template")
    if t in TEMPLATE_DA:
        n, x = TEMPLATE_DA[t]
        ver = eid.rsplit("_p", 1)[-1] if "_p" in eid else None
        return n, x, (f"testrunde {ver}" if ver else None)
    return (spec or {}).get("title") or eid, None, None


STATE_PLAIN = {"DISCOVERED": "Ny idé", "SUPPRESSED": "Sorteret fra (prøvet før)", "REGISTERED": "Står i kø",
               "SCREENING": "Testes nu", "SCREEN_PASSED": "Bestod første test — venter på din godkendelse",
               "VALIDATION": "Slut-test kører", "VALIDATED": "Bestod alle tests — venter på din godkendelse",
               "OBSERVATION": "Observeres på nye data (simuleret) — afgøres automatisk, når perioden er slut",
               "PAPER_TRADING": "Handler (simuleret)", "PAUSED": "Sat på pause", "REJECTED": "Afvist",
               "RETIRED": "Afsluttet", "WITHDRAWN": "Trukket tilbage", "EXTERNAL": "Ekstern undersøgelse"}
NEEDS_YOU = {"SCREEN_PASSED": ("VALIDATION", "Start slut-testen på 2024-data (kan kun gøres én gang)"),
             "VALIDATED": ("PAPER_TRADING", "Start simuleret handel med strategien"),
             "PAUSED": ("PAPER_TRADING", "Genoptag simuleret handel (kræver dokumenteret gen-test)")}


def approvals(db):
    """What a human can approve, in plain words: strategy types (templates) and experiments waiting for a decision."""
    from lab import templates as tpl_mod
    from lab.engine import catalogue
    waiting = []
    for x in registry.status(db):
        if x["state"] in NEEDS_YOU:
            n, ex, ver = plain(db, x["exp_id"])
            to, what = NEEDS_YOU[x["state"]]
            spec = _j(registry.latest(db, x["exp_id"])["spec_json"]) or {}
            tpl = spec.get("template")
            if x["state"] == "SCREEN_PASSED" and tpl in ("vrp_timing", "btc_volume_share"):
                to, what = None, "Ingen ren slut-test mulig: BTC/ETH-data for 2024 er allerede set (PROTOCOL v3 ændring 1)"
            elif spec.get("family"):                  # amendment 8 points 5 and 16: typed in a terminal, no button
                to, what = None, (
                    f"Kun i terminalen: python3 -m lab approve {x['exp_id']} VALIDATION --reason ... --committed ... "
                    f"og derefter python3 -m lab confirm <kode> (ændring 8 punkt 16)"
                    if to == "VALIDATION" and spec.get("clean_holdout") else
                    "Ingen ren slut-test i familiefilen: standser her (ændring 8 punkt 16)" if to == "VALIDATION" else
                    "Simuleret handel for familier kræver et live spot-feed og en senere ændring (ændring 8 "
                    "punkt 16)")
            waiting.append({"exp_id": x["exp_id"], "name": n, "explain": ex, "round": ver, "state": x["state"],
                            "status": STATE_PLAIN[x["state"]], "to": to, "action": what,
                            "needs_evidence": x["state"] in ("SCREEN_PASSED", "PAUSED")})
    rows = []
    blob = tpl_mod.catalogue_blob()
    for t in catalogue.TEMPLATES:
        n, ex = TEMPLATE_DA.get(t, (t, None))
        eid = catalogue.exp_id(t)
        st = lifecycle.state(db, eid)
        approved = tpl_mod.approval(db, t, blob) is not None
        if st in ("REJECTED", "SUPPRESSED", "WITHDRAWN", "RETIRED"):
            status, can = ("Afvist i test" if st == "REJECTED" else "Sorteret fra — samme idé er afvist før"), False
        elif st and st != "DISCOVERED":
            status, can = STATE_PLAIN.get(st, st), False
        elif approved:
            status, can = "Godkendt — testes, når flåden kører", False
        else:
            status, can = "Ikke godkendt endnu", blob is not None
        rows.append({"template": t, "name": n, "explain": ex, "status": status, "state": st, "approved": approved,
                     "can_approve": can})
    return {"waiting": waiting, "templates": rows, "catalogue_committed": blob is not None}
