"""PROTOCOL_V3 amendment 10: the automatic exploration lane. The fleet keeps searching for ideas without the search
ever counting as evidence, spending alpha or touching the data the families are tested on.

- Window: only explore0 = 2020-01..2021-12, before the families' train3. `_files` is the lane's only data access and
  refuses every other window (train3, validation3, the 2024 holdout, 2025+ reserved data, forward windows).
- Templates: the mechanism functions of families with a valid amendment 8 approval (families.binding_approval), with
  the fixed parameter grids in GRIDS (look-back at most 14 days, as the families' own rule), the family's universe and
  costs at 2x stress. A family the user has not approved is never explored.
- Jobs: 'explore|<ISO week>|<fid>' (backtest agents, lowest priority) evaluates the untried variants, at most
  WEEKLY_MAX per ISO week across all families; 'explore_report|<ISO week>' (report-1, after the week) writes at most
  PROPOSALS_MAX proposals with the number of variants tried. Both write artifacts under _explore and one event each.
- Never: experiments, transitions, results, alpha rows, paper orders or a state change. Downloads only from
  2026-11-28 through the families' guard (data.binance.vision, at most 2 at a time); before that the job waits.
"""
from __future__ import annotations

import importlib
import json
import math
import os
import time
from datetime import datetime, timezone

from lab import families, jobs, pipeline
from lab.engine import data

SPLIT = "explore0"
WINDOW = ((2020, 1), (2021, 12))
data.SPLITS.setdefault(SPLIT, WINDOW)          # the lane's own window; the gateway (lab/data.py) never serves it
LABEL = "EXPLORATORY_LANE"
WEEKLY_MAX = 500
PROPOSALS_MAX = 3
SHARPE_MIN = 1.0
THIRDS_MIN = 2
STRESS = 2.0
MIN_COINS = 5                                  # the lane's own floor (F2's design floor); decides nothing
PRIORITY = 200                                 # after every pipeline job (catalogue 50-100, families 120)
JOB = {"max_attempts": 2, "timeout_s": 1800}
REPORT_JOB = {"priority": 60, "max_attempts": 2, "timeout_s": 120}
REPORT_DELAY_S = 1800                          # the report of week W is queued 30 min after W ended
DIR = "_explore"
ENQUEUE_EVERY = 3600                           # the strategy pass (every 30 s) plans the lane at most hourly
_LAST_ENQUEUE = [0.0]
# amendment 10 point 3: fixed grids per mechanism function, inside the families' own limits (look-back <= 14 days)
GRIDS = {
    "fcarry": {
        "carry_filter": {"lookback_days": [3, 7, 14], "enter_apr": [0.05, 0.1095, 0.15, 0.219, 0.3]},
        "carry_filter_weekly": {"lookback_days": [3, 7, 14], "enter_apr": [0.05, 0.1095, 0.15, 0.219, 0.3]},
        "carry_hysteresis": {"lookback_days": [3, 7, 14], "exit_apr": [0.0, 0.05, 0.1095]},
        "carry_floor": {"days": [7, 14], "q": [0.6, 0.7, 0.8, 0.9, 0.95]},
    },
    "dbasis": {
        "basis_threshold": {"theta": [0.03, 0.05, 0.075, 0.1, 0.15, 0.2]},
        "basis_hold_to_roll": {"theta": [0.03, 0.05, 0.075, 0.1, 0.15, 0.2]},
        "basis_cross_section": {"k": [2, 3, 4, 5, 7]},
    },
}


class Refused(data.ReservedData):
    pass


def _guard(split):
    """The lane reads explore0 and nothing else (amendment 10 point 2)."""
    if split != SPLIT:
        raise Refused(f"the exploration lane reads only {SPLIT} ({WINDOW[0][0]}-{WINDOW[0][1]:02d}.."
                      f"{WINDOW[1][0]}-{WINDOW[1][1]:02d}), never {split!r}")
    return split


def week(ts):
    y, w, _ = datetime.fromtimestamp(ts, timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(name):
    y, w = int(name[:4]), int(name[6:])
    a = int(datetime.fromisocalendar(y, w, 1).replace(tzinfo=timezone.utc).timestamp())
    return a, a + 7 * 86400


def key(fid, fn, params):
    return f"{fid}.{fn}:{json.dumps(params, sort_keys=True)}"


def variants(fid):
    """[(fn, params)] of the fixed grid, in a fixed order."""
    out = []
    for fn, grid in sorted((GRIDS.get(fid) or {}).items()):
        names = sorted(grid)
        combos = [{}]
        for n in names:
            combos = [{**c, n: v} for c in combos for v in grid[n]]
        out += [(fn, c) for c in combos]
    return out


def eligible(db):
    """Families with a valid approval and an approved instrument model whose module defines every grid function."""
    out = []
    for fid in families.family_ids():
        if fid not in GRIDS or families.binding_approval(db, fid) is None:
            continue
        fam = families.load(fid)
        if fam.get("instrument_model", {}).get("type") not in families.INSTRUMENT_MODELS:
            continue
        mod = importlib.import_module(f"lab.families.{fid}")
        if all(hasattr(mod, fn) for fn in GRIDS[fid]):
            out.append(fid)
    return out


def tried(db, since=None):
    """{variant key} recorded by explore events (all time, or from `since`)."""
    out = set()
    for (p,) in db.q("SELECT payload FROM events WHERE kind='research.explore' AND ts>=?", since or 0):
        out.update(json.loads(p).get("variants") or [])
    return out


def _files(fam, split, get):
    """The lane's only data access: the family's instrument series in explore0 (refuses any other window)."""
    split = _guard(split)
    syms, dlv = families.symbols(fam), families.delivery_model(fam)
    if families.blocked(syms, (split,), delivery=dlv):
        raise families.Embargoed(families.embargo_reason(split))
    per_sym = {s: {**data.files_for(s, split, get), "spot": data.spot_files_for(s, split, get),
                   **({"delivery": data.delivery_files_for(s, split, get)} if dlv else {})} for s in syms}
    bars, funding, dups, _ = families.transform({"instrument_model": fam["instrument_model"]["type"]}, per_sym, split)
    excluded = sorted(s for s in bars if not data.quality(bars[s], split, dups.get(s, 0))["ok"])
    for s in excluded:
        bars.pop(s, None), funding.pop(s, None)
    return bars, funding, excluded


def thirds(daily):
    t = len(daily) // 3
    return [math.fsum(daily[:t]), math.fsum(daily[t:2 * t]), math.fsum(daily[2 * t:])] if t else []


def evaluate(fid, fam, fn, params, bars, funding):
    """One variant: net metrics at 2x costs, the family's attribution rule and the chronological thirds."""
    mod = importlib.import_module(f"lab.families.{fid}")
    pos = getattr(mod, fn)(bars, funding, params, None)
    m = pipeline._evaluate(bars, funding, pos, fam["costs"], mult=STRESS)
    att = families.attribution({"family": fid}, m, bars=bars, pos=pos)
    th = thirds(m.get("daily_net") or [])
    sr = m.get("net_sharpe_ann")
    checks = {f"net Sharpe >= {SHARPE_MIN} at {STRESS:g}x costs": sr is not None and sr >= SHARPE_MIN,
              "attribution holds": bool(att["gates"]) and all(att["gates"].values()),
              f"positive in >= {THIRDS_MIN} of 3 thirds": sum(1 for x in th if x > 0) >= THIRDS_MIN}
    return {"key": key(fid, fn, params), "family": fid, "function": fn, "params": params, "label": LABEL,
            "net_sharpe_ann": sr, "net_total": m.get("net_total"), "days": m.get("days"),
            "max_drawdown": m.get("max_drawdown"), "fees": m.get("fees"), "funding": m.get("funding"),
            "attribution": att, "thirds": th, "checks": checks, "candidate": all(checks.values())}


def step_explore(db, job, worker, get=None, load=None):
    """Evaluate the family's untried grid variants, within the week's cap. `load(fam)` replaces the data access (tests)."""
    p = job.get("payload") or {}
    fid, wk = p.get("family"), p.get("week")
    if fid not in eligible(db):
        return {"family": fid, "skipped": "no valid amendment 8 approval (the lane explores approved families only)"}
    a, _ = week_bounds(wk)
    left = WEEKLY_MAX - len(tried(db, a))
    todo = [(fn, prm) for fn, prm in variants(fid) if key(fid, fn, prm) not in tried(db)][:max(0, left)]
    if not todo:
        return {"family": fid, "week": wk, "variants": 0, "why": "grid done" if left > 0 else "weekly cap reached"}
    fam = families.load(fid)
    try:
        bars, funding, excluded = load(fam) if load else _files(fam, SPLIT, get or families.guarded_get(SPLIT))
    except families.Embargoed as e:
        raise pipeline.Deferred(f"explore {fid}: {e}", families.EMBARGO_UNTIL) from None
    except OSError as e:
        if not str(e).startswith("download failed"):
            raise
        raise pipeline.Deferred(f"explore {fid}: {e}", int(time.time()) + pipeline.DOWNLOAD_RETRY_S) from None
    need = MIN_COINS
    if len(bars) < need:
        res = []
        why = f"{len(bars)} coins pass the data-quality rule in {SPLIT}, fewer than {need}: nothing evaluated"
    else:
        res, why = [evaluate(fid, fam, fn, prm, bars, funding) for fn, prm in todo], None
    keys = [key(fid, fn, prm) for fn, prm in todo]
    art = pipeline.save_artifact(os.path.join(DIR, wk), fid, {"label": LABEL, "family": fid, "week": wk,
                                                             "split": SPLIT, "excluded": excluded,
                                                             "coins": sorted(bars), "results": res, "why": why})
    db.event("research.explore", f"system:{worker}", None,
             {"family": fid, "week": wk, "variants": keys, "evaluated": len(res), "decisional": False,
              "label": LABEL, "candidates": [r["key"] for r in res if r["candidate"]], "why": why,
              "artifact_sha256": art["sha256"]})
    return {"family": fid, "week": wk, "variants": len(keys), "evaluated": len(res),
            "candidates": sum(1 for r in res if r["candidate"]), "artifact": art}


def proposals(results, total_tried):
    """At most PROPOSALS_MAX candidates by net Sharpe (ties by key), each with the number of variants tried."""
    c = sorted((r for r in results if r.get("candidate")), key=lambda r: (-(r["net_sharpe_ann"] or 0), r["key"]))
    return [{**{k: r[k] for k in ("key", "family", "function", "params", "net_sharpe_ann", "net_total", "thirds",
                                  "checks")}, "variants_tried_total": total_tried, "label": LABEL}
            for r in c[:PROPOSALS_MAX]]


def _all_results():
    out, root = {}, os.path.join(pipeline.ARTIFACTS, DIR)
    for wk in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if not os.path.isdir(os.path.join(root, wk)):           # <week>.json: a report, not results
            continue
        for f in sorted(os.listdir(os.path.join(root, wk))):
            if f.endswith(".json"):
                with open(os.path.join(root, wk, f), encoding="utf-8") as fh:
                    for r in json.load(fh).get("results") or []:
                        out[r["key"]] = r                     # one result per variant (deterministic data)
    return list(out.values())


def step_report(db, job, worker):
    wk = (job.get("payload") or {}).get("week")
    _, b = week_bounds(wk)
    if time.time() < b + REPORT_DELAY_S:
        raise pipeline.StepError(f"{wk} is not over (+{REPORT_DELAY_S // 60} min)")
    n = len(tried(db))
    props = proposals(_all_results(), n)
    out = {"label": LABEL, "week": wk, "variants_tried_total": n, "proposals": props,
           "rule": "amendment 10 point 5: a proposal becomes a family only through an amendment 8 draft and the "
                   "user's approval; nothing here is evidence or a reason to trade"}
    art = pipeline.save_artifact(DIR, wk, out)
    db.event("research.explore_proposals", f"system:{worker}", None,
             {"week": wk, "variants_tried_total": n, "proposals": [x["key"] for x in props], "decisional": False,
              "label": LABEL, "artifact_sha256": art["sha256"]})
    return {"week": wk, "proposals": len(props), "variants_tried_total": n, "artifact": art}


def enqueue(db, now=None, actor="strategy-1", every=0):
    """One explore job per eligible family and ISO week (while the grid has untried variants), and the report of the
    last ended week if any explore ran in it. `every`: skip if the last call was less than that many seconds ago (the
    fleet passes ENQUEUE_EVERY: the approval check reads git blobs). Returns the number of new jobs."""
    if every and time.time() - _LAST_ENQUEUE[0] < every:
        return 0
    _LAST_ENQUEUE[0] = time.time()
    now = now or time.time()
    jobs.init(db)
    n, wk = 0, week(now)
    done = tried(db)
    for fid in eligible(db):
        fam = families.load(fid)
        if families.blocked(families.symbols(fam), (SPLIT,), delivery=families.delivery_model(fam)):
            continue                                  # embargo (before 2026-11-28): no job that could only wait
        if any(key(fid, fn, prm) not in done for fn, prm in variants(fid)):
            n += jobs.enqueue(db, f"explore|{wk}|{fid}", "explore", None, {"family": fid, "week": wk},
                              priority=PRIORITY, actor=f"system:{actor}", **JOB)[1]
    last = week(now - 7 * 86400)
    a, b = week_bounds(last)
    if db.one("SELECT 1 FROM events WHERE kind='research.explore' AND ts>=? AND ts<? LIMIT 1", a, b):
        n += jobs.enqueue(db, f"explore_report|{last}", "explore_report", None, {"week": last},
                          actor=f"system:{actor}", not_before=b + REPORT_DELAY_S, **REPORT_JOB)[1]
    return n
