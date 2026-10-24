"""Mission-control read models for the dashboard. Every value is computed from persisted data at request time:
the registry (hash-chained), the operational heartbeats table, committed files, and file modification times of
processes that run outside the lab. Nothing here is estimated unless it says so in its `basis` field.
"""
from __future__ import annotations

import json
import os
import time

from lab import lifecycle, ops, registry
from lab.db import HERE
from lab.gates import s7_gate
from lab.risk import Risk

SUPERVISOR_STALE_S = 30
EXTERNAL_RUNNING_S = 15 * 60
LABEL_OF_STATE = {"DISCOVERED": "CANDIDATE", "SUPPRESSED": "SUPPRESSED", "REGISTERED": "REGISTERED",
                  "SCREENING": "EXPLORATORY", "SCREEN_PASSED": "EXPLORATORY", "VALIDATION": "VALIDATION",
                  "VALIDATED": "VALIDATED", "PAPER_TRADING": "PAPER (simulated)", "PAUSED": "PAPER (simulated, paused)", "OBSERVATION": "OBSERVATION (forward test)",
                  "REJECTED": "REJECTED", "RETIRED": "RETIRED", "WITHDRAWN": "WITHDRAWN", "EXTERNAL": "EXTERNAL"}
STAGES = ("DISCOVERY", "HYPOTHESIS", "REGISTERED", "SCREENING", "VALIDATION", "PAPER TRADING", "PAUSED", "REJECTED")
STAGE_OF_STATE = {"REGISTERED": "REGISTERED", "SCREENING": "SCREENING", "SCREEN_PASSED": "SCREENING",
                  "VALIDATION": "VALIDATION", "VALIDATED": "VALIDATION", "PAPER_TRADING": "PAPER TRADING",
                  "PAUSED": "PAUSED", "REJECTED": "REJECTED", "SUPPRESSED": "REJECTED", "WITHDRAWN": "REJECTED",
                  "RETIRED": "COMPLETED", "EXTERNAL": "EXTERNAL"}
# documented failure pattern per finished idea (research/NEXT_CANDIDATES.md §1, MISSION2_DECISION.md, MISSION3_FAST_SCREEN.md)
FAILURE_PATTERN = {
    "L01_copy_kol": "no copyable signal", "L02_self_found_traders": "speed race (latency)",
    "L03_sol_trend_hourly": "costs x turnover", "L04_buy_graduations": "adverse selection (new tokens)",
    "L05_graduation_sniper": "speed race (latency)", "L06_short_new_hl_listings": "insufficient sample",
    "L07_funding_carry_v0": "invalid test", "L08_funding_carry_leverage": "costs x turnover",
    "L09_stop_when_ahead": "no copyable signal", "L10_launch_v1": "overfitting / non-persistence",
    "L11_smart_v2": "no copyable signal", "L12_arb_v1": "speed race (latency)",
    "L13_carry_v1": "edge decayed below costs", "L14_tsmom_v1": "insufficient sample",
    "L15_tsmom_v2": "insufficient sample", "L16_pmcal_v1": "unstable sign out of sample",
    "L17_p1_btc15m_model": "speed race (latency)", "L18_p2_negrisk_arb": "speed race (latency)",
    "L19_p3_maker_fills": "inconclusive", "L20_m1_orderflow": "cost wall", "L21_m2_liquidation_reversal": "cost wall",
    "L22_m3_premium_convergence": "cost wall"}
# finished holdout summaries that state an uncertainty bound (net values exactly as recorded in the result files)
RESULT_ESTIMATES = {
    "L14_tsmom_v1": ("tsmom_v1.json", "mean_week", "lb_99_5", "weeks", "net return per week"),
    "L13_carry_v1": ("carry_v1.json", "mean_week", "lb_99_4", "weeks", "net return per week"),
    "L16_pmcal_v1": ("pmcal_v1.json", "mean", "lb_99_5", "events", "net return per event"),
}


def _j(s):
    try:
        return json.loads(s) if s else None
    except ValueError:
        return s


def market_class(text):
    t = (text or "").lower()
    for keys, label in ((("polymarket",), "prediction markets"),
                        (("pumpfun", "memecoin"), "Solana memecoins"),
                        (("perp", "hyperliquid", "binance", "funding"), "crypto derivatives"),
                        (("btc", "eth", "sol", "crypto", "pools", "spot"), "crypto spot")):
        if any(k in t for k in keys):
            return label
    return "unspecified"


def workers(db, now=None):
    """Honest worker status: nothing counts as active unless the supervisor itself beat within 30 s."""
    now = now or time.time()
    rows = {r["worker"]: dict(r) for r in db.q("SELECT * FROM heartbeats")}
    sup = rows.pop("supervisor", None)
    sup_alive = bool(sup and sup.get("status") == "running" and now - sup["ts"] <= SUPERVISOR_STALE_S)
    out = []
    for name, r in sorted(rows.items()):
        age = now - r["ts"]
        stale_after = r.get("stale_after") or 300
        if not sup_alive:
            st = "offline"
        elif r.get("status") == "error":
            st = "error"
        elif age > stale_after:
            st = "stale"
        elif r.get("status") == "running":
            st = "running"
        elif r.get("status") == "idle":
            st = "scheduled"
        else:
            st = r.get("status") or "unknown"
        nxt = (r["ts"] + r["interval"]) if (st == "scheduled" and r.get("interval")) else None
        out.append({"worker": name, "state": st, "age_s": age, "ok": bool(r["ok"]), "detail": r.get("detail"),
                    "next_run_ts": nxt, "pid": r["pid"]})
    last_run = db.one("SELECT MAX(ts) FROM events WHERE kind IN ('system.running','system.stopped','system.alive')")[0]
    return {"supervisor": {"alive": sup_alive, "age_s": (now - sup["ts"]) if sup else None,
                           "status": sup.get("status") if sup else None, "last_run_ts": last_run},
            "workers": out, "active": sum(1 for w in out if w["state"] in ("running", "scheduled")),
            "running": sum(1 for w in out if w["state"] == "running")}


def pm_lp_schedule(now=None):
    """Calendar milestones of the external pm_lp_v1 study (committed start date + spec constants; no data read)."""
    now = now or time.time()
    try:
        from research import pm_lp
        d0 = pm_lp.start_day()
    except Exception:
        d0 = None
    if d0 is None:
        return None
    ms = [("development ends", d0 + pm_lp.DEV_DAYS[1] + 1),
          ("validation ends; dev/val evaluation may run", d0 + pm_lp.VAL_DAYS[1] + 1),
          ("holdout collection ends", d0 + pm_lp.HOLD_DAYS[1] + 1),
          ("resolution tracking ends; final verdict may run", d0 + pm_lp.TAIL_END + 1)]
    items = [{"label": l, "ts": day * 86400, "passed": now >= day * 86400} for l, day in ms]
    nxt = next((m for m in items if not m["passed"]), None)
    return {"d0_ts": d0 * 86400, "milestones": items, "next": nxt, "remaining_s": (nxt["ts"] - now) if nxt else 0,
            "basis": "calendar dates fixed in research/PM_LP_START.md and PM_LP_SPEC.md"}


def status_category(state, exp_id, ext, rk, wk):
    if state == "EXTERNAL":
        age = (ext.get(exp_id) or {}).get("last_write_age_s")
        if age is None:
            return "external — no data file found"
        return "running (external process)" if age <= EXTERNAL_RUNNING_S else "external — no recent writes"
    return {"DISCOVERED": "awaiting registration (human)", "SUPPRESSED": "suppressed by graveyard",
            "REGISTERED": "scheduled — waiting for screening",
            "SCREENING": "screening" if wk["active"] else "screening — waiting for a worker",
            "SCREEN_PASSED": "awaiting validation approval (human)", "VALIDATION": "validation open",
            "VALIDATED": "awaiting paper-trading approval (human)",
            "PAPER_TRADING": "warming up after restart" if rk.warming(exp_id) else "paper trading (simulated)",
            "PAUSED": "paused", "REJECTED": "completed — rejected", "RETIRED": "completed",
            "WITHDRAWN": "withdrawn"}.get(state, state)


def pipeline_rows(db, now=None):
    now = now or time.time()
    rk, ext, wk = Risk(db), ops.external_freshness(now), workers(db, now)
    sched = pm_lp_schedule(now)
    out = []
    for x in registry.status(db):
        eid, st = x["exp_id"], x["state"]
        v = db.one("SELECT spec_json, spec_path FROM experiments WHERE exp_id=? ORDER BY version DESC LIMIT 1", eid)
        spec = _j(v["spec_json"]) or {}
        stage = STAGE_OF_STATE.get(st) or ("HYPOTHESIS" if (st == "DISCOVERED" and v["spec_path"]) else "DISCOVERY")
        ev = db.one("SELECT kind, ts FROM events WHERE exp_id=? ORDER BY id DESC LIMIT 1", eid)
        tr = db.one("SELECT reason, ts FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", eid)
        ds = db.one("SELECT MAX(ts) FROM datasets WHERE exp_id=?", eid)[0]
        if st == "EXTERNAL":
            fresh = {"age_s": (ext.get(eid) or {}).get("last_write_age_s"), "basis": "external file last write"}
        elif ds:
            fresh = {"age_s": now - ds, "basis": "last gateway data read"}
        elif spec.get("scan_ts"):
            fresh = {"age_s": now - spec["scan_ts"], "basis": "scan that discovered it"}
        else:
            fresh = {"age_s": None, "basis": "no data read through the lab"}
        reason = None
        if st == "PAUSED":
            p = db.one("SELECT detail FROM risk_events WHERE exp_id=? AND action='PAUSE' ORDER BY id DESC LIMIT 1", eid)
            reason = p[0] if p else (tr["reason"] if tr else None)
        elif st in ("REJECTED", "RETIRED", "WITHDRAWN"):
            reason = x["verdict"] or (tr["reason"] if tr else None)
        elif st == "SUPPRESSED":
            reason = tr["reason"] if tr else None
        eta = None
        if eid == "X01_pm_lp_v1" and sched and sched["next"]:
            eta = {"label": sched["next"]["label"], "ts": sched["next"]["ts"], "remaining_s": sched["remaining_s"],
                   "basis": sched["basis"]}
        out.append({"exp_id": eid, "title": spec.get("title") or spec.get("hypothesis") or eid,
                    "mechanism": x["mechanism"], "instrument": spec.get("instrument"),
                    "market": market_class(spec.get("instrument") or x["mechanism"]), "state": st, "stage": stage,
                    "display_label": LABEL_OF_STATE.get(st, st), "status": status_category(st, eid, ext, rk, wk),
                    "latest_event": {"kind": ev["kind"], "ts": ev["ts"]} if ev else None,
                    "source": (spec.get("sources") or [None])[0], "freshness": fresh,
                    "tests_completed": db.one("SELECT COUNT(*) FROM results WHERE exp_id=?", eid)[0],
                    "result": {"label": x["label"], "verdict": x["verdict"]} if x["verdict"] else None,
                    "eta": eta, "reason": reason,
                    "next_actions": [{"to": b, "who": who} for (a, b), who in lifecycle.EDGES.items() if a == st],
                    "failure_pattern": FAILURE_PATTERN.get(eid)})
    counts = {s: 0 for s in STAGES + ("COMPLETED", "EXTERNAL")}
    for r in out:
        counts[r["stage"]] = counts.get(r["stage"], 0) + 1
    return {"stages": list(STAGES), "counts": counts, "experiments": out, "pm_lp_schedule": sched}


def mission(db, now=None, verify=None):
    """`verify` returns (chains, triggers) like db.verify(); the dashboard passes its incremental check."""
    now = now or time.time()
    pr = pipeline_rows(db, now)
    st = {}
    for r in pr["experiments"]:
        st[r["state"]] = st.get(r["state"], 0) + 1
    chains, triggers = (verify or db.verify)()
    detectors = [dict(r) for r in db.q("SELECT detector, MAX(ts) last_ts, COUNT(*) n, SUM(flagged) flagged, "
                                       "SUM(CASE WHEN metric='error' THEN 1 ELSE 0 END) errors FROM observations "
                                       "GROUP BY detector ORDER BY detector")]
    return {"now": now, "paper_only": True, "fail_closed": Risk(db).fail_closed(),
            "chain_ok": bool(triggers and all(b is None for _, b in chains.values())),
            "workers": workers(db, now),
            "counts": {"experiments": len(pr["experiments"]), "candidates": st.get("DISCOVERED", 0),
                       "suppressed": st.get("SUPPRESSED", 0),
                       "running": st.get("SCREENING", 0) + st.get("VALIDATION", 0),
                       "awaiting": st.get("DISCOVERED", 0) + st.get("REGISTERED", 0) + st.get("SCREEN_PASSED", 0)
                       + st.get("VALIDATED", 0),
                       "accepted": st.get("VALIDATED", 0) + st.get("PAPER_TRADING", 0), "paused": st.get("PAUSED", 0),
                       "rejected": st.get("REJECTED", 0), "completed": st.get("RETIRED", 0) + st.get("WITHDRAWN", 0),
                       "external": st.get("EXTERNAL", 0), "paper_active": st.get("PAPER_TRADING", 0),
                       "discovered_total": db.one("SELECT COUNT(*) FROM events WHERE kind='candidate.discovered'")[0]},
            "stage_counts": pr["counts"], "last_scan_ts": db.one("SELECT MAX(ts) FROM observations")[0],
            "detectors": detectors, "external": ops.external_freshness(now), "disk": ops.disk(),
            "sizes": ops.data_sizes(), "gate_s7": s7_gate(db, now), "pm_lp_schedule": pr["pm_lp_schedule"],
            "last_event_id": db.one("SELECT COALESCE(MAX(id),0) FROM events")[0]}


def throughput(db, days=30, now=None):
    now = now or time.time()
    start = (int(now) // 86400 - days + 1) * 86400
    cat = {"candidate.discovered": "discovered", "candidate.suppressed": "suppressed",
           "lifecycle.transition": "transitions", "result.recorded": "results", "legacy.imported": "results",
           "repro.verified": "results", "scan.finished": "scans", "data.accessed": "data reads"}
    buckets = {}
    for r in db.q("SELECT ts, kind FROM events WHERE ts>=?", start):
        c = cat.get(r["kind"]) or ("risk" if r["kind"].startswith("risk.") else
                                   "system" if r["kind"].startswith(("system.", "worker.")) else "other")
        d = int(r["ts"]) // 86400
        buckets.setdefault(d, {}).setdefault(c, 0)
        buckets[d][c] += 1
    return {"days": [{"day": d * 86400, **buckets.get(d, {})} for d in range(start // 86400, int(now) // 86400 + 1)],
            "categories": ["discovered", "suppressed", "transitions", "results", "scans", "data reads", "risk",
                           "system", "other"]}


def results_view(db):
    est = []
    verdicts = {x["exp_id"]: x["verdict"] for x in registry.status(db)}
    for eid, (fname, mk, lk, nk, unit) in RESULT_ESTIMATES.items():
        path = os.path.join(HERE, "data", "research", "results", fname)
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f).get("summary") or {}
        except (OSError, ValueError):
            continue
        if s.get(mk) is None:
            continue
        est.append({"exp_id": eid, "mean": s.get(mk), "lower_bound": s.get(lk), "lb_quantile": lk, "n": s.get(nk),
                    "n_unit": nk, "unit": unit, "label": "HOLDOUT", "net": True, "verdict": verdicts.get(eid),
                    "source": f"data/research/results/{fname}"})
    finished = [r for r in pipeline_rows(db)["experiments"] if r["state"] in ("REJECTED", "RETIRED", "WITHDRAWN")]
    patterns = {}
    for r in finished:
        k = r["failure_pattern"] or "unclassified"
        patterns[k] = patterns.get(k, 0) + 1
    return {"estimates": est, "failure_patterns": dict(sorted(patterns.items(), key=lambda kv: -kv[1])),
            "finished": [{"exp_id": r["exp_id"], "label": (r["result"] or {}).get("label"), "verdict": r["reason"],
                          "pattern": r["failure_pattern"], "mechanism": r["mechanism"]} for r in finished]}
