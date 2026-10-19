"""PROTOCOL_V3 amendments 10, 10a and 10b: the automatic exploration lane. The fleet keeps searching for ideas without
the search ever counting as evidence, spending alpha or touching the data the families are tested on.

- Window: only explore0 = 2020-01..2021-12, before the families' train3. `_files` is the lane's only data access and
  refuses every other window (train3, validation3, the 2024 holdout, 2025+ reserved data, forward windows).
- Templates: the mechanism functions of families with a valid amendment 8 approval (families.binding_approval). First
  the fixed GRIDS, then variants drawn with a fixed seed from SPACES, each with a coin basket of >= MIN_COINS coins
  (10a), always inside the families' own limits (look-back at most 14 days). Scanner-flagged perp_premium coins come
  first in half of the baskets (10a point 3). 2x costs, the family's attribution rule.
- Universe (10a point 2): the union of the lab's coin lists for spot_perp_ratio, the family's candidates for
  spot_delivery_ratio.
- Jobs: at most one 'explore|<fid>|<UTC hour>' at a time lane-wide (backtest agents, lowest priority), at most BATCH
  new variants each and WEEKLY_MAX per ISO week; 'explore_report|<UTC day>' (report-1) after each day with at most
  PROPOSALS_MAX proposals and the number of variants tried. A variant counts as tried only once it was evaluated.
- Network (10b): only data.binance.vision, at most 2 downloads lab-wide (the families' slots), and only before
  2026-10-24 00:00 UTC or from 2026-11-14 00:00 UTC (COIN-M from 2026-11-28, amendment 8 point 17). Otherwise the
  lane reads only the files already in the cache and makes no request.
- Never: experiments, transitions, results, alpha rows, paper orders or a state change. It writes artifacts under
  _explore, the events research.explore / research.explore_proposals, job rows, and (when downloading) the shared
  market cache and its 404 list.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import random
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from lab import families, jobs, pipeline
from lab.engine import data

SPLIT = "explore0"
WINDOW = ((2020, 1), (2021, 12))
data.SPLITS.setdefault(SPLIT, WINDOW)          # the lane's own window; the gateway (lab/data.py) never serves it
LABEL = "EXPLORATORY_LANE"
WEEKLY_MAX = 5000                              # 10a point 4
BATCH = 30                                     # new variants per job (one job at a time, at most hourly)
PROPOSALS_MAX = 3
SHARPE_MIN = 1.0
THIRDS_MIN = 2
STRESS = 2.0
MIN_COINS = 5                                  # the lane's own floor (F2's design floor); decides nothing
PRIORITY = 200                                 # after every pipeline job (catalogue 50-100, families 120)
JOB = {"max_attempts": 2, "timeout_s": 1800}
REPORT_JOB = {"priority": 60, "max_attempts": 3, "timeout_s": 300}
REPORT_DELAY_S = 1800                          # the report of day D is queued from D+1 00:30 UTC
PLAN_EVERY = 3600                              # a new explore job at most hourly (read from the jobs table)
ELIGIBLE_TTL = 3600                            # the approval check reads git blobs: cached per registry for an hour
FOCUS_DAYS = 7                                 # scanner-flagged perp_premium coins of the last 7 days come first
DRAW_TRIES = 50                                # draws per wanted variant before a job stops looking
DIR = "_explore"
FETCH_UNTIL = int(datetime(2026, 10, 24, tzinfo=timezone.utc).timestamp())   # 10b: once, before pm_lp's validation
FETCH_FROM = int(datetime(2026, 11, 14, tzinfo=timezone.utc).timestamp())    # 10b: after pm_lp's holdout
SOURCES = (families.KIND_SOURCE["klines"], families.KIND_SOURCE["funding"], families.SPOT)
# amendment 10 point 3: fixed grids, inside the families' own limits (look-back <= 14 days)
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
# amendment 10a point 1: parameter spaces of the drawn variants (int: lo, hi; float: lo, hi, step). carry_hysteresis
# exits below its module's fixed entry level (fcarry.HYST_ENTER_APR = 0.219).
SPACES = {
    "fcarry": {
        "carry_filter": {"lookback_days": ("int", 1, 14), "enter_apr": ("float", 0.02, 0.5, 0.005)},
        "carry_filter_weekly": {"lookback_days": ("int", 1, 14), "enter_apr": ("float", 0.02, 0.5, 0.005)},
        "carry_hysteresis": {"lookback_days": ("int", 1, 14), "exit_apr": ("float", 0.0, 0.2, 0.005)},
        "carry_floor": {"days": ("int", 2, 14), "q": ("float", 0.5, 0.99, 0.01)},
    },
    "dbasis": {
        "basis_threshold": {"theta": ("float", 0.01, 0.3, 0.005)},
        "basis_hold_to_roll": {"theta": ("float", 0.01, 0.3, 0.005)},
        "basis_cross_section": {"k": ("int", 1, 10)},
    },
}
_ELIGIBLE = {}


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


def _day(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def _day_start(day):
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def key(fid, fn, params, coins=None):
    return f"{fid}.{fn}:{json.dumps(params, sort_keys=True)}" + (f"|{','.join(coins)}" if coins else "")


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


def draw(fid, i, coins, focus=()):
    """Variant i of the drawn sequence (fixed seed): (fn, params, coin basket), or None if nothing can be drawn."""
    space = SPACES.get(fid) or {}
    coins = sorted(coins)
    if not space or len(coins) < MIN_COINS:
        return None
    rng = random.Random(f"{fid}|{i}")
    fn = rng.choice(sorted(space))
    p = {}
    for name, spec in sorted(space[fn].items()):
        if spec[0] == "int":
            p[name] = rng.randint(spec[1], spec[2])
        else:
            p[name] = round(spec[1] + spec[3] * rng.randint(0, int(round((spec[2] - spec[1]) / spec[3]))), 6)
    if fn == "basis_cross_section":
        p["k"] = min(p["k"], len(coins))
    n = rng.randint(MIN_COINS, len(coins))
    first = [c for c in sorted(focus) if c in coins][:n] if rng.random() < 0.5 else []
    rest = [c for c in coins if c not in first]
    return fn, p, sorted(first + rng.sample(rest, n - len(first)))


def universe(fam):
    """10a point 2: the union of the lab's coin lists (spot_perp_ratio) or the family's candidates (delivery)."""
    if families.delivery_model(fam):
        return tuple(families.delivery_candidates(fam))
    return tuple(sorted(set(data.UNIVERSE_30) | set(data.UNIVERSE_30_V3) | set(data.UNIVERSE_CM16)
                        | set(data.UNIVERSE)))


def eligible(db):
    """Families with a valid approval, an approved instrument model and every lane function (cached per registry for
    ELIGIBLE_TTL: an approval or a revocation reaches the lane within the hour)."""
    hit = _ELIGIBLE.get(db.path)
    if hit and time.monotonic() - hit[0] < ELIGIBLE_TTL:
        return list(hit[1])
    out = []
    for fid in families.family_ids():
        if fid not in GRIDS or families.binding_approval(db, fid) is None:
            continue
        fam = families.load(fid)
        if fam.get("instrument_model", {}).get("type") not in families.INSTRUMENT_MODELS:
            continue
        mod = importlib.import_module(f"lab.families.{fid}")
        if all(hasattr(mod, fn) for fn in set(GRIDS[fid]) | set(SPACES.get(fid) or {})):
            out.append(fid)
    _ELIGIBLE[db.path] = (time.monotonic(), out)
    return list(out)


def tried(db, since=None, until=None):
    """{variant key} that explore events recorded as evaluated (all time, or in [since, until))."""
    out = set()
    for (p,) in db.q("SELECT payload FROM events WHERE kind='research.explore' AND ts>=? AND ts<?", since or 0,
                     until or 2 ** 62):
        out.update(json.loads(p).get("variants") or [])
    return out


def focus(db, now):
    """Coins with flagged perp_premium observations in the last FOCUS_DAYS days (10a point 3)."""
    return {r[0] for r in db.q("SELECT DISTINCT instrument FROM observations WHERE metric='perp_premium' AND "
                               "flagged=1 AND ts>=?", int(now) - FOCUS_DAYS * 86400)}


# ---------- network (10b) and data access ----------
def fetch_allowed(source, now=None):
    now = data.CLOCK() if now is None else now
    if source == families.KIND_SOURCE["delivery"]:
        return now >= families.EMBARGO_UNTIL                 # COIN-M: amendment 8 point 17 unchanged
    return source in SOURCES and (now < FETCH_UNTIL or now >= FETCH_FROM)


def guarded_get(fetch=None):
    """The `get` for data._fetch: data.binance.vision only, the 10b dates, a remembered 404 without the network, at
    most 2 downloads lab-wide (the families' slots). `fetch(url)` is the network read (tests inject it)."""
    def get(url):
        if url in families.absent():
            raise urllib.error.HTTPError(url, 404, "not in the archive (remembered 404)", None, None)
        src = families.source_of(url)
        if src is None or not fetch_allowed(src):
            raise families.Embargoed(f"the exploration lane may not fetch {url} now (amendment 10b)")
        with families._download_slot():
            try:
                return (fetch or families._urlopen)(url)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    families._mark_absent(url)
                raise
    get.guarded = True
    return get


def _cached(sym, split, dlv):
    """The files of one coin that are already in the cache (no request)."""
    e = data.expected_paths(sym, split, spot=True)
    have = lambda pairs: [p for _, p in pairs if os.path.exists(p)]           # noqa: E731
    out = {"klines": have(e["klines"]), "funding": have(e["funding"]), "spot": have(e["spot"])}
    if dlv:
        out["delivery"] = [{k: c[k] for k in ("contract", "expiry", "from", "to")} | {"paths": have(c["files"])}
                           for c in data.delivery_plan(sym, split)]
    return out


def _download(sym, split, dlv, get):
    return {**data.files_for(sym, split, get), "spot": data.spot_files_for(sym, split, get),
            **({"delivery": data.delivery_files_for(sym, split, get)} if dlv else {})}


def _coin(path):
    """The coin of a cached file name: BNBUSDT-1h-2020-01.zip, BNBUSDT-fundingRate-..., ADAUSD_201225-1h-... ."""
    name = os.path.basename(path).split("-")[0]
    return name.split("_")[0][:-3] + "USDT" if "_" in name else name


def _files(fam, split, get=None, now=None):
    """The lane's only data access: the family's instrument series in explore0 (refuses any other window). Downloads
    what is missing when 10b allows it, else reads only the cache. Returns (bars, funding, excluded, inputs)."""
    split = _guard(split)
    syms, dlv = universe(fam), families.delivery_model(fam)
    missing = families.missing(syms, (split,), delivery=dlv)
    if missing and all(fetch_allowed(x[0], now) for x in missing):
        get = get or guarded_get()
        with ThreadPoolExecutor(2) as ex:                      # the 2 lab-wide slots bound the real concurrency
            per_sym = dict(zip(syms, ex.map(lambda s: _download(s, split, dlv, get), syms)))
    else:
        per_sym = {s: _cached(s, split, dlv) for s in syms}
    bars, funding, dups, _ = families.transform({"instrument_model": fam["instrument_model"]["type"]}, per_sym, split)
    excluded = sorted(s for s in bars if not data.quality(bars[s], split, dups.get(s, 0))["ok"])
    for s in excluded:
        bars.pop(s, None), funding.pop(s, None)
    files = sorted(os.path.relpath(p, data.CACHE) + f":{os.path.getsize(p)}" for f in per_sym.values()
                   for k in ("klines", "funding", "spot") for p in f.get(k) or [])
    return bars, funding, excluded, {"files": len(files), "digest": hashlib.sha256(
        json.dumps(files).encode()).hexdigest()}


def thirds(daily):
    t = len(daily) // 3
    return [math.fsum(daily[:t]), math.fsum(daily[t:2 * t]), math.fsum(daily[2 * t:])] if t else []


def evaluate(fid, fam, fn, params, bars, funding, coins=None):
    """One variant: net metrics at 2x costs, the family's attribution rule and the chronological thirds."""
    if coins:
        bars, funding = {s: bars[s] for s in coins}, {s: funding.get(s, {}) for s in coins}
    mod = importlib.import_module(f"lab.families.{fid}")
    pos = getattr(mod, fn)(bars, funding, params, None)
    m = pipeline._evaluate(bars, funding, pos, fam["costs"], mult=STRESS)
    att = families.attribution({"family": fid}, m, bars=bars, pos=pos)
    th = thirds(m.get("daily_net") or [])
    sr = m.get("net_sharpe_ann")
    checks = {f"net Sharpe >= {SHARPE_MIN} at {STRESS:g}x costs": sr is not None and sr >= SHARPE_MIN,
              "attribution holds": bool(att["gates"]) and all(att["gates"].values()),
              f"positive in >= {THIRDS_MIN} of 3 thirds": sum(1 for x in th if x > 0) >= THIRDS_MIN}
    return {"key": key(fid, fn, params, coins), "family": fid, "function": fn, "params": params, "coins": coins,
            "label": LABEL, "net_sharpe_ann": sr, "net_total": m.get("net_total"), "days": m.get("days"),
            "max_drawdown": m.get("max_drawdown"), "fees": m.get("fees"), "funding": m.get("funding"),
            "attribution": att, "thirds": th, "checks": checks, "candidate": all(checks.values())}


def plan(fid, done, coins, foc, want):
    """The next `want` untried variants: the fixed grid (all coins), then the drawn sequence."""
    out, seen = [], set(done)
    for fn, p in variants(fid):
        if len(out) >= want:
            return out
        k = key(fid, fn, p)
        if k not in seen:
            out.append((fn, p, None))
            seen.add(k)
    i = sum(1 for k in done if "|" in k and k.startswith(f"{fid}."))   # drawn variants already tried: skip ahead
    for _ in range(want * DRAW_TRIES):
        if len(out) >= want:
            break
        d = draw(fid, i, coins, foc)
        i += 1
        if d is None:
            break
        k = key(fid, *d)
        if k not in seen:
            out.append(d)
            seen.add(k)
    return out


def step_explore(db, job, worker, get=None, load=None):
    """Evaluate up to BATCH untried variants of one family within the ISO week's cap. `load(fam)` replaces the data
    access (tests). Only evaluated variants are recorded as tried."""
    fid = (job.get("payload") or {}).get("family")
    now = time.time()
    if fid not in eligible(db):
        return {"family": fid, "skipped": "no valid amendment 8 approval (the lane explores approved families only)"}
    wk = week(now)
    left = WEEKLY_MAX - len(tried(db, *week_bounds(wk)))
    if left <= 0:
        return {"family": fid, "week": wk, "evaluated": 0, "why": "weekly cap reached"}
    fam = families.load(fid)
    try:
        bars, funding, excluded, inputs = load(fam) if load else _files(fam, SPLIT, get)
    except families.Embargoed as e:
        raise pipeline.Deferred(f"explore {fid}: {e}", FETCH_FROM if now < FETCH_FROM else
                                families.EMBARGO_UNTIL) from None
    except OSError as e:
        if not str(e).startswith("download failed"):
            raise
        raise pipeline.Deferred(f"explore {fid}: {e}", int(now) + pipeline.DOWNLOAD_RETRY_S) from None
    if len(bars) < MIN_COINS:
        res, why = [], f"{len(bars)} coins pass the data-quality rule in {SPLIT}, fewer than {MIN_COINS}"
    else:
        todo = plan(fid, tried(db), sorted(bars), focus(db, now), min(BATCH, left))
        res = [evaluate(fid, fam, fn, p, bars, funding, coins) for fn, p, coins in todo]
        why = None if res else "no untried variant left"
    art = pipeline.save_artifact(os.path.join(DIR, _day(now)), f"{fid}_{int(now)}",
                                 {"label": LABEL, "family": fid, "week": wk, "split": SPLIT, "excluded": excluded,
                                  "coins": sorted(bars), "inputs": inputs, "results": res, "why": why})
    db.event("research.explore", f"system:{worker}", None,
             {"family": fid, "week": wk, "variants": [r["key"] for r in res], "evaluated": len(res),
              "decisional": False, "label": LABEL, "candidates": [r["key"] for r in res if r["candidate"]],
              "why": why, "inputs": inputs, "artifact_sha256": art["sha256"]})
    return {"family": fid, "week": wk, "evaluated": len(res), "candidates": sum(1 for r in res if r["candidate"]),
            "why": why, "artifact": art}


def proposals(results, total_tried):
    """At most PROPOSALS_MAX candidates by net Sharpe (ties by key), each with the number of variants tried."""
    c = sorted((r for r in results if r.get("candidate")), key=lambda r: (-(r["net_sharpe_ann"] or 0), r["key"]))
    return [{**{k: r.get(k) for k in ("key", "family", "function", "params", "coins", "net_sharpe_ann", "net_total",
                                      "thirds", "checks")}, "variants_tried_total": total_tried, "label": LABEL}
            for r in c[:PROPOSALS_MAX]]


def _all_results(fids):
    out, root = {}, os.path.join(pipeline.ARTIFACTS, DIR)
    for day in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if not os.path.isdir(os.path.join(root, day)):       # <day>.json: a report, not results
            continue
        for f in sorted(os.listdir(os.path.join(root, day))):
            if f.endswith(".json"):
                with open(os.path.join(root, day, f), encoding="utf-8") as fh:
                    for r in json.load(fh).get("results") or []:
                        if r.get("family") in fids:          # a family whose approval ended is not proposed
                            out[r["key"]] = r
    return list(out.values())


def step_report(db, job, worker):
    day = (job.get("payload") or {}).get("day")
    end = _day_start(day) + 86400
    if time.time() < end + REPORT_DELAY_S:
        raise pipeline.Deferred(f"{day} is not over (+{REPORT_DELAY_S // 60} min)", end + REPORT_DELAY_S)
    fids = eligible(db)
    n = len(tried(db))
    props = proposals(_all_results(set(fids)), n)
    out = {"label": LABEL, "day": day, "variants_tried_total": n, "families": fids, "proposals": props,
           "rule": "amendment 10 point 5: a proposal becomes a family only through an amendment 8 draft and the "
                   "user's approval; nothing here is evidence or a reason to trade"}
    art = pipeline.save_artifact(DIR, day, out)
    db.event("research.explore_proposals", f"system:{worker}", None,
             {"day": day, "variants_tried_total": n, "proposals": [x["key"] for x in props], "decisional": False,
              "label": LABEL, "artifact_sha256": art["sha256"]})
    return {"day": day, "proposals": len(props), "variants_tried_total": n, "artifact": art}


def _ready(fam, now=None):
    """Data the lane can use now: what is missing may be fetched, or at least MIN_COINS coins are complete in the
    cache (no file of theirs is missing). `now` is the lab's data clock (data.CLOCK, as for the families' embargo)."""
    syms, dlv = universe(fam), families.delivery_model(fam)
    missing = families.missing(syms, (SPLIT,), delivery=dlv)
    if not missing or all(fetch_allowed(x[0], now) for x in missing):
        return True
    gaps = {_coin(x[3]) for x in missing}
    return sum(1 for s in syms if s not in gaps) >= MIN_COINS


def enqueue(db, now=None, actor="strategy-1"):
    """The report of the last ended UTC day with explore events, and at most one explore job lane-wide and at most one
    per PLAN_EVERY (both read from the jobs table) for the next eligible family whose data is ready (round robin).
    Returns the number of new jobs."""
    now = now or time.time()
    jobs.init(db)
    n = 0
    day = _day(now - 86400)
    a = _day_start(day)
    if db.one("SELECT 1 FROM events WHERE kind='research.explore' AND ts>=? AND ts<? LIMIT 1", a, a + 86400):
        n += jobs.enqueue(db, f"explore_report|{day}", "explore_report", None, {"day": day}, actor=f"system:{actor}",
                          not_before=a + 86400 + REPORT_DELAY_S, **REPORT_JOB)[1]
    if db.one("SELECT 1 FROM jobs WHERE kind='explore' AND (status IN ('queued', 'running', 'blocked') OR "
              "created_ts>?) LIMIT 1", now - PLAN_EVERY):
        return n
    if len(tried(db, *week_bounds(week(now)))) >= WEEKLY_MAX:
        return n
    fids = [f for f in eligible(db) if _ready(families.load(f))]           # network dates on the data clock
    if not fids:
        return n
    last = db.one("SELECT json_extract(payload, '$.family') FROM jobs WHERE kind='explore' ORDER BY created_ts DESC "
                  "LIMIT 1")
    nxt = fids[(fids.index(last[0]) + 1) % len(fids)] if last and last[0] in fids else fids[0]   # round robin
    hour = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H")
    n += jobs.enqueue(db, f"explore|{nxt}|{hour}", "explore", None, {"family": nxt}, priority=PRIORITY,
                      actor=f"system:{actor}", now=now, **JOB)[1]
    return n
