"""Pre-registered hypothesis families (research/PROTOCOL_V3.md amendment 8).

A family is a committed JSON file research/families/<fid>.json (schema lab.family/1) plus one mechanism module
lab/families/<fid>.py. Only non-price-prediction mechanisms with positions hedged in the same asset are allowed; the
mechanism tag comes from the controlled vocabulary research/families/VOCABULARY.json. This module is the shared layer
over the existing catalogue, approvals, register_batch, job chain and forward test: it never edits
lab/engine/catalogue.py and never injects anything into catalogue.TEMPLATES.

Phase A1: loading, the schema and vocabulary rules, the power rule, cache status and the graveyard check behind the
read-only `python3 -m lab family-check`. Phase A2: the approval typed by the user, the alpha budget and the binding.
Phase A3: discovery, the template view and spec of an instance, registration rules, and the download embargo (amendment
8 point 17 with amendment 9 point 1): every network request for family data goes through guarded_get. Phase A4: the
instrument model (transform), the benchmark data and the mechanism attribution of the screen (point 8). Phase A5:
successors from frozen training artifacts (point 9), the cohort and its alpha (points 10 and 13), the forward test and
the reject-only interim look (points 11 and 12, in lab/pipeline.py), the family close and the programme stop (point 15),
and the code pin (point 18). Phase A6: the sealed 2024 holdout after a forward PASS (point 16: typed in a terminal, one
declared file set with the spot files, the family blob as code hash, BTC/ETH/SOL never read; lab/pipeline.py) and the
read-only families card of the dashboard (lab/command.py; no approval endpoint).
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import statistics
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from lab.db import HERE
from lab.engine.data import ReservedData

FAMILY_DIR = os.path.join(HERE, "research", "families")
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
VOCABULARY = os.path.join(FAMILY_DIR, "VOCABULARY.json")
SCHEMA = "lab.family/1"

K_MAX = 3                      # base instances per family (amendment 8 point 3)
GRID = 2                       # variants per instance
LOOKBACK_MAX_DAYS = 14
FORWARD_MONTHS, INTERIM_MONTHS, EARLIEST_START = 12, 6, "2026-12-01"
W0, ALPHA_F_MAX = 0.05, 0.0125             # programme wealth and the per-family reservation (point 13)
RESERVE_NOTE, SPEND_NOTE, RELEASE_NOTE = "A8 reserve", "A8 spend", "A8 release"   # alpha_ledger notes (point 13)
A8_NOTES = (RESERVE_NOTE, SPEND_NOTE, RELEASE_NOTE)
TAG_MAX = 2                                # point 3: at most 2 families per canonical tag in the whole programme
POWER_SHARPE, POWER_MIN = 3.0, 0.5         # point 14: power >= 0.5 at true Sharpe 3.0 with alpha_F / K_MAX
DECISION_TIME = "01:00"
ALLOWED_CLASSES = ("carry", "structural", "subsidy", "flow", "liquidity_provision")
INSTRUMENT_MODELS = ("spot_perp_ratio", "spot_delivery_ratio")
CASH_FLOWS = ("funding_income", "locked_basis", "reward")
DELIVERY_MIN_COINS = 5                        # F2 design: fewer than 5 coins with quarterlies -> not approved
COVERAGE_SPLITS = ("train3", "validation3", "holdout")   # continuous quarterlies 2022-01..2024-12 (F2 design)
TRIGGER_ARTIFACTS = ("cost", "adversarial")
ACK_PREFIX, ACK_MIN = "materially different because", 40
UNIVERSES = {"30v3": "UNIVERSE_30_V3", "30": "UNIVERSE_30", "cm16": "UNIVERSE_CM16", "8": "UNIVERSE"}
FILE_PATTERNS = {"binance_um_klines_1h": "{sym}-1h-{y}-{m:02d}.zip",
                 "binance_um_fundingRate": "{sym}-fundingRate-{y}-{m:02d}.zip",
                 "binance_spot_klines_1h": "{sym}-1h-{y}-{m:02d}.zip"}


# ---------- loading ----------
def path_of(fid):
    return os.path.join(FAMILY_DIR, f"{fid}.json")


def load(path_or_fid):
    p = path_or_fid if path_or_fid.endswith(".json") else path_of(path_or_fid)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def vocabulary():
    with open(VOCABULARY, encoding="utf-8") as f:
        return json.load(f)


def module_path(fid):
    return os.path.join(MODULE_DIR, f"{fid}.py")


# ---------- statistics (same PSR as lab/engine/backtest.psr: skew 0, kurtosis 3) ----------
def days(months):
    return int(months * 365 / 12)


def required_sharpe(alpha, months):
    """Annualised Sharpe whose PSR (skew 0, kurtosis 3) over the window just reaches 1 - alpha."""
    z, n = statistics.NormalDist().inv_cdf(1 - alpha), days(months)
    return z / math.sqrt(n - 1 - z * z / 2) * math.sqrt(365)


def power(true_sharpe, alpha, months):
    """Probability that a strategy with this true annualised Sharpe passes PSR >= 1 - alpha over the window."""
    n = days(months)
    sr, req = true_sharpe / math.sqrt(365), required_sharpe(alpha, months) / math.sqrt(365)
    return statistics.NormalDist().cdf((sr - req) * math.sqrt(n - 1) / math.sqrt(1 + sr * sr / 2))


# ---------- the rules of amendment 8 that need no database ----------
def validate(fam, vocab=None):
    """Every schema and vocabulary rule of amendment 8 points 1-5, 9, 10, 13, 14 and 17. Returns problems (empty = ok)."""
    from lab.engine import catalogue
    vocab = vocab or vocabulary()
    tags, bad = vocab["tags"], []
    if fam.get("schema") != SCHEMA:
        bad.append(f"schema must be {SCHEMA}")
    fid = fam.get("family_id") or ""
    if not re.fullmatch(r"[a-z0-9]{3,12}", fid):
        bad.append("family_id must match [a-z0-9]{3,12}")
    for k in ("title", "amendment", "drafted_by", "drafting_data_access"):
        if not fam.get(k):
            bad.append(f"{k} is required")
    m = fam.get("mechanism") or {}
    tag = m.get("tag")
    if tag not in tags:
        bad.append(f"mechanism tag {tag!r} is not in the vocabulary (a new tag needs a vocabulary change)")
    else:
        cls = tags[tag]["class"]
        if cls not in ALLOWED_CLASSES:
            bad.append(f"mechanism class {cls!r} is not allowed (only {', '.join(ALLOWED_CLASSES)})")
        if not tags[tag].get("runnable"):
            bad.append(f"tag {tag!r} has no instrument model under amendment 8 (needs a later amendment)")
        if m.get("class") not in (None, cls):
            bad.append(f"mechanism class {m.get('class')!r} differs from the vocabulary ({cls!r})")
        missing = [t for t in tags[tag].get("related", []) if t not in (fam.get("related_tags_reviewed") or [])]
        if missing:
            bad.append(f"related tags not reviewed: {', '.join(missing)}")
    if m.get("price_exposure") != "hedged_same_asset":
        bad.append("price_exposure must be hedged_same_asset (directional or cross-coin books are refused)")
    for k in ("return_source", "non_price_prediction"):
        if not m.get(k):
            bad.append(f"mechanism.{k} is required")
    att = m.get("attribution") or {}
    if att.get("cash_flow") not in CASH_FLOWS or not att.get("rule"):
        bad.append(f"mechanism.attribution needs cash_flow in {CASH_FLOWS} and a rule")
    if (fam.get("instrument_model") or {}).get("type") not in INSTRUMENT_MODELS:
        bad.append(f"instrument_model.type must be one of {INSTRUMENT_MODELS}")
    for a in fam.get("graveyard_acknowledged") or []:
        why = a.get("materially_different_because") or ""
        if not why.startswith(ACK_PREFIX) or len(why) < ACK_MIN or not a.get("lessons_addressed"):
            bad.append(f"graveyard acknowledgement for {a.get('exp_id')} needs '{ACK_PREFIX} ...' "
                       f"(>= {ACK_MIN} chars) and lessons_addressed")
    if fam.get("decision_time_utc") != DECISION_TIME:
        bad.append(f"decision_time_utc must be {DECISION_TIME}")
    fw = fam.get("forward") or {}
    if fw.get("months") != FORWARD_MONTHS or fw.get("interim_futility_months") != INTERIM_MONTHS:
        bad.append(f"forward window must be {FORWARD_MONTHS} months with one reject-only look at {INTERIM_MONTHS}")
    if (fw.get("earliest_start") or "") < EARLIEST_START:
        bad.append(f"forward.earliest_start must be on or after {EARLIEST_START}")
    alpha_f = (fam.get("alpha") or {}).get("family")
    if not isinstance(alpha_f, (int, float)) or abs(alpha_f - ALPHA_F_MAX) > 1e-12:
        bad.append(f"alpha.family must be {ALPHA_F_MAX} (amendment 8 point 13: alpha_F = 0,0125 per family)")
    costs = fam.get("costs") or {}
    for k in ("taker_fee", "half_spread", "slippage"):
        if not isinstance(costs.get(k), (int, float)) or costs[k] < catalogue.COSTS[k]:
            bad.append(f"costs.{k} must be >= the catalogue's {catalogue.COSTS[k]}")
    if (fam.get("universe") or {}).get("base") not in UNIVERSES:
        bad.append(f"universe.base must be one of {sorted(UNIVERSES)}")
    if (fam.get("instrument_model") or {}).get("type") == "spot_delivery_ratio":   # F2: an explicit coin list
        from lab.engine import data
        u = fam.get("universe") or {}
        syms, base = u.get("symbols"), getattr(data, UNIVERSES.get(u.get("base"), "UNIVERSE"), ())
        if not (isinstance(syms, list) and len(set(syms)) == len(syms) >= DELIVERY_MIN_COINS and
                all(x in base for x in syms)):
            bad.append(f"universe.symbols must list at least {DELIVERY_MIN_COINS} distinct coins of the base universe "
                       f"(spot_delivery_ratio: the coins with COIN-M quarterlies)")
        else:
            if set(syms) & set(data.HOLDOUT_SEEN):
                bad.append("universe.symbols must exclude BTC, ETH and SOL, so a clean 2024 holdout exists")
            want = max(DELIVERY_MIN_COINS, math.ceil(0.8 * len(syms)))
            if u.get("min_symbols") != want:
                bad.append(f"universe.min_symbols must be max({DELIVERY_MIN_COINS}, ceil(0.8 n)) = {want}")
    inst = fam.get("instances") or []
    if not 1 <= len(inst) <= K_MAX:
        bad.append(f"1 to {K_MAX} base instances are allowed")
    seen = set()
    for i in inst:
        bad += _instance_problems(i, seen, successor=False)
        s = i.get("successor")
        if s:
            bad += _instance_problems({**i, **s, "successor": None}, seen, successor=True)
            t = s.get("trigger") or {}
            if t.get("artifact") not in TRIGGER_ARTIFACTS or not t.get("all"):
                bad.append(f"successor {s.get('id')}: the trigger may only read a frozen training artifact "
                           f"({', '.join(TRIGGER_ARTIFACTS)}) and needs conditions")
            for c in t.get("all") or []:
                try:
                    condition(c, {})                       # parse only: a mechanical rule, never eval
                except FamilyError as e:
                    bad.append(f"successor {s.get('id')}: {e}")
            if not s.get("why"):
                bad.append(f"successor {s.get('id')}: why is required")
    if isinstance(alpha_f, (int, float)) and alpha_f > 0:
        pw = power(POWER_SHARPE, alpha_f / K_MAX, FORWARD_MONTHS)
        if pw < POWER_MIN:
            bad.append(f"power {pw:.2f} < {POWER_MIN} at true Sharpe {POWER_SHARPE} and alpha {alpha_f / K_MAX:.5f}")
    return bad


def _instance_problems(i, seen, successor):
    bad, iid = [], i.get("id") or ""
    what = "successor" if successor else "instance"
    if not re.fullmatch(r"[a-z0-9_]{2,12}", iid):
        bad.append(f"{what} id {iid!r} must match [a-z0-9_]{{2,12}}")
    if iid in seen:
        bad.append(f"{what} id {iid!r} is used twice")
    seen.add(iid)
    if not i.get("function"):
        bad.append(f"{what} {iid}: function is required")
    if i.get("execution") != "taker":
        bad.append(f"{what} {iid}: execution must be taker")
    if not isinstance(i.get("max_lookback_days"), int) or not 1 <= i["max_lookback_days"] <= LOOKBACK_MAX_DAYS:
        bad.append(f"{what} {iid}: max_lookback_days must be 1..{LOOKBACK_MAX_DAYS}")
    g = i.get("grid")
    if not (isinstance(g, list) and len(g) == GRID and all(isinstance(x, dict) and x for x in g)):
        bad.append(f"{what} {iid}: grid must be exactly {GRID} parameter sets")
    else:                                              # point 3: every lookback in the grid, not only the declared one
        top = i.get("max_lookback_days") if isinstance(i.get("max_lookback_days"), int) else LOOKBACK_MAX_DAYS
        for x in g:
            for k, v in x.items():
                if str(k).endswith("days") and (not isinstance(v, (int, float)) or not 0 < v <= min(top,
                                                                                                    LOOKBACK_MAX_DAYS)):
                    bad.append(f"{what} {iid}: grid {k}={v} exceeds max_lookback_days {top} (at most "
                               f"{LOOKBACK_MAX_DAYS} days, amendment 8 point 3)")
    return bad


# ---------- what the database and the disk say (read-only) ----------
def graveyard_hits(db, fam, vocab=None):
    """REJECTED/WITHDRAWN experiments with the family's tag or a related tag, and which of them lack an
    acknowledgement (amendment 8 point 6)."""
    from lab.lifecycle import state
    tags = (vocab or vocabulary())["tags"]
    tag = (fam.get("mechanism") or {}).get("tag")
    wanted = {tag} | set(tags.get(tag, {}).get("related", []))
    own = set(members(db, fam.get("family_id"))) if fam.get("family_id") else set()   # siblings never count
    hits = sorted({r["exp_id"] for r in db.q("SELECT DISTINCT exp_id, mechanism_tag FROM experiments")
                   if r["mechanism_tag"] in wanted and r["exp_id"] not in own and
                   state(db, r["exp_id"]) in ("REJECTED", "WITHDRAWN")})
    acked = {a.get("exp_id") for a in fam.get("graveyard_acknowledged") or []}
    return hits, [h for h in hits if h not in acked]


def expected_files(fam, splits=("train3", "validation3")):
    """{cache_dir: [paths]} the screening will read (no network; spot zips in their own directory)."""
    from lab.engine import data
    syms = symbols(fam)
    out = {}
    for d in fam.get("data") or []:
        if d.get("source") == KIND_SOURCE["delivery"]:       # the held quarterlies (calendar, no network)
            out[d["cache_dir"]] = [p for sp in splits if sp in data.SPLITS for s in syms
                                   for c in data.delivery_plan(s, sp) for _, p in c["files"]]
            continue
        pat = FILE_PATTERNS.get(d.get("source"))
        if not pat:
            continue
        folder = os.path.join(HERE, d["cache_dir"])
        out[d["cache_dir"]] = [os.path.join(folder, pat.format(sym=s, y=y, m=m))
                               for sp in splits if sp in data.SPLITS for (y, m) in data.months(sp) for s in syms]
    return out


def cache_status(fam):
    return {d: (sum(os.path.exists(p) for p in ps), len(ps)) for d, ps in expected_files(fam).items()}


def alpha_reserved(db):
    """Amendment 8 wealth already reserved or spent: the A8 rows (reserve, spend, release) of family:<fid> plus the
    alpha_i spend rows of the instances a cohort spent it on (a spend moves alpha_F from family:<fid> to its M
    instances, so the sum is unchanged). No other row counts, whatever its id or sign: a row another path wrote under a
    family-like id never frees W0 (finding protocol-statistics #3)."""
    return db.one("SELECT COALESCE(SUM(alpha), 0) FROM alpha_ledger WHERE (substr(exp_id, 1, 7) = 'family:' AND note "
                  "IN (?, ?, ?)) OR (note = ? AND exp_id GLOB 'E_*__*_a8')", *A8_NOTES, SPEND_NOTE)[0]


def blobs(fid):
    """Committed and working-tree git blobs of the four files an approval binds (amendment 8 point 5)."""
    from lab import registry
    files = {"family": os.path.join("research", "families", f"{fid}.json"),
             "module": os.path.join("lab", "families", f"{fid}.py"),
             "adapter": os.path.join("lab", "families", "__init__.py"),
             "vocabulary": os.path.join("research", "families", "VOCABULARY.json")}
    out = {}
    for k, rel in files.items():
        full = os.path.join(HERE, rel)
        committed = registry.blob_at(registry.last_commit(rel) or "HEAD", rel.replace(os.sep, "/"))
        try:
            working = registry.git("hash-object", full) if os.path.exists(full) else None
        except Exception:
            working = None
        out[k] = {"path": rel.replace(os.sep, "/"), "committed": committed, "working": working,
                  "clean": committed is not None and committed == working}
    return out


def check(db, path):
    """Everything `family-check` shows. Read-only: no market data, no network, no writes."""
    fam = load(path)
    vocab = vocabulary()
    problems = validate(fam, vocab)
    fid = fam.get("family_id") or "?"
    if not os.path.exists(module_path(fid)):
        problems.append(f"mechanism module lab/families/{fid}.py is missing")
    hits, unacked = graveyard_hits(db, fam, vocab) if db is not None else ([], [])
    problems += [f"graveyard: {e} has the same or a related tag and is not acknowledged" for e in unacked]
    problems += tag_problems(db, fam) if db is not None else []
    if delivery_model(fam) and os.path.exists(module_path(fid)):    # F2: both checks are shown before approval
        problems += selftest_problems(fid) + (coverage_problems(db, fam) if db is not None else [])
    alpha_f = (fam.get("alpha") or {}).get("family") or 0
    used = alpha_reserved(db) if db is not None else 0.0
    if used + alpha_f > W0 + 1e-12:
        problems.append(f"alpha budget: {used:.4f} of {W0} already reserved; this family needs {alpha_f}")
    table = {m: {a: round(required_sharpe(a, m), 2) for a in (alpha_f, alpha_f / 2, alpha_f / 3)}
             for m in (FORWARD_MONTHS, INTERIM_MONTHS)} if alpha_f else {}
    return {"family": fid, "problems": problems, "graveyard": hits, "unacknowledged": unacked,
            "cache": cache_status(fam), "blobs": blobs(fid), "alpha": {"family": alpha_f, "reserved": used, "W0": W0},
            "required_sharpe": table,
            "power_at_3": round(power(POWER_SHARPE, alpha_f / K_MAX, FORWARD_MONTHS), 2) if alpha_f else None}


# ---------- phase A2: approval typed by the user, alpha budget, binding (amendment 8 points 5 and 13) ----------
APPROVAL_SECONDS = 15 * 60


class FamilyError(Exception):
    pass


def thresholds():
    """The gate values a family approval binds: any change voids the approval before registration."""
    import hashlib
    import inspect
    from lab import pipeline
    from lab.engine import backtest, catalogue
    return {"PLACEBO_P_MAX": catalogue.PLACEBO_P_MAX, "DSR_MIN": catalogue.DSR_MIN,
            "COST_HIGH_MULT": catalogue.COST_HIGH_MULT, "seed": pipeline.SEED,
            "bootstrap_code": hashlib.sha256(inspect.getsource(backtest.metrics).encode()).hexdigest()[:16]}


def interactive_human():
    """Amendment 8 point 5: approvals are typed by the user in an interactive terminal, never by an assistant.
    (Policy, not proof: a faked terminal is possible; the rule and the logged actor are what bind.)"""
    import sys
    if os.environ.get("CLAUDECODE") or any(k.startswith("CLAUDE_CODE_") for k in os.environ):
        raise FamilyError("an assistant session may not take a human step of an amendment 8 family (approve, "
                          "confirm, revive, revoke or open a holdout; amendment 8 point 5)")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):           # the CLI adds the 'refused: ' prefix once
        raise FamilyError("the human steps of an amendment 8 family (approve, confirm, revive, revoke, holdout) must be "
                          "typed in an interactive terminal")


GUARD = interactive_human


def bound_blobs(fid):
    """The committed blobs an approval binds. Every bound file must exist and be committed exactly as it is."""
    b = blobs(fid)
    dirty = [v["path"] for v in b.values() if not v["clean"]]
    if dirty:
        raise FamilyError(f"commit these files exactly as they are first: {', '.join(dirty)}")
    return {k: v["committed"] for k, v in b.items()}


def registered(db, fid):
    """True once the family's base batch is registered: its batch.registered event (point 7). A batch that stopped
    part-way (some members REGISTERED, no event) is not registered yet: register_batch completes it in a later pass."""
    return fid in _base_batches(db)


def _base_batches(db):
    """The families whose base batch.registered event exists (a successor's batch carries successor_of)."""
    return {p.get("family") for p in (json.loads(r[0]) for r in db.q(
        "SELECT payload FROM events WHERE kind='batch.registered'")) if p.get("family") and not p.get("successor_of")}


def registration_started(db, fid):
    """True once any instance of the family was registered, a batch that stopped part-way included: from then on the
    family can be neither approved again nor revoked (point 5). Discovered or suppressed candidates do not count."""
    prefix = f"E_{fid}__"
    return any((instance_of(r[0]) or (None,))[0] == fid for r in db.q(
        "SELECT DISTINCT exp_id FROM transitions WHERE to_state='REGISTERED' AND substr(exp_id, 1, ?) = ?",
        len(prefix), prefix))


def not_discovered(db, fam):
    """The family file's base instances that are not DISCOVERED, as 'id (state)' ('missing' if never discovered)."""
    from lab.lifecycle import state
    fid, out = fam.get("family_id"), []
    for i in fam.get("instances") or []:
        e = exp_id(fid, i.get("id"))
        st = state(db, e)
        if st != "DISCOVERED":
            out.append(f"{e} ({st or 'not discovered yet: the fleet discovers it from the committed family file'})")
    return out


REVIVE_FIRST = "revive before approve-family"


def _programme_limits(db, fam):
    """The limits other families' approvals change: W0 (point 13), the programme stop (point 15) and the per-tag limits
    (point 3). confirm checks them again inside the transaction that writes the reservation."""
    alpha_f = (fam.get("alpha") or {}).get("family") or 0
    bad = []
    if alpha_reserved(db) + alpha_f > W0 + 1e-12:
        bad.append(f"alpha budget: {alpha_reserved(db):.4f} of {W0} reserved; this family needs {alpha_f}")
    bad += programme_stop(db)                              # point 15: no new approvals once the programme stopped
    bad += tag_problems(db, fam)                           # point 3: <= 2 families per tag, <= 1 open at a time
    return bad


def _blocking_problems(db, fam):
    fid = fam.get("family_id")
    bad = validate(fam)
    if not os.path.exists(module_path(fid)):
        bad.append(f"mechanism module lab/families/{fid}.py is missing")
    elif delivery_model(fam):                  # F2 design: approved only after both checks (before registration)
        bad += selftest_problems(fid) + coverage_problems(db, fam)
    _, unacked = graveyard_hits(db, fam)
    bad += [f"graveyard: {e} is not acknowledged" for e in unacked]
    bad += _programme_limits(db, fam)
    if registration_started(db, fid):
        bad.append(f"{fid} is already registered: approvals and revocations are only possible before registration")
    held = reserved(db, fid)
    if held > 1e-12 and last_approval_kind(db, fid) != "family.revoked":     # point 13: alpha_F once per family
        bad.append(f"{fid} already holds its alpha_F reservation ({held:.4f}) from an earlier approval: revoke-family "
                   f"first (it releases the reservation), then approve again (amendment 8 point 13)")
    gone = not_discovered(db, fam)
    if gone:                                               # points 6 and 7: every base instance, revived first
        bad.append(f"{REVIVE_FIRST}: base instance(s) not DISCOVERED: {', '.join(gone)} (amendment 8 point 6: "
                   f"revival is a separate step before approve-family; point 7: the base instances register once, "
                   f"together, as one batch)")
    elif not bad:                                          # written by the discovery agent from this file (point 6)
        bad += [b for i in fam.get("instances") or [] for b in spec_problems(db, exp_id(fid, i.get("id")), fam)]
    return bad


def approval_summary(db, fam):
    """Point 5: what an approval would bind, one line per instance: its id and state, and whether it is active (a base
    instance, or a successor the approval names because it is DISCOVERED now) or dropped (a successor still SUPPRESSED
    or missing: it never registers under this approval)."""
    from lab.lifecycle import state
    fid, named, out = fam.get("family_id"), set(discovered_successors(db, fam)), []
    for i, parent in instances(fam):
        e = exp_id(fid, i["id"])
        st = state(db, e) or "missing"
        if parent is None:
            out.append(f"{e}: {st}, base instance, active")
        elif e in named:
            out.append(f"{e}: {st}, successor of {parent}, active (registers only if its trigger is met)")
        else:
            out.append(f"{e}: {st}, successor of {parent}, DROPPED: not DISCOVERED, so this approval does not name it "
                       f"and it never registers (revive it first, then approve-family, to keep it)")
    return out


def discovered_successors(db, fam):
    """The family's successors that are DISCOVERED now (revived before approve-family). Only these may register later
    (point 9); the approval names them."""
    from lab.lifecycle import state
    fid = fam.get("family_id")
    return sorted(exp_id(fid, i["id"]) for i, parent in instances(fam)
                  if parent and state(db, exp_id(fid, i["id"])) == "DISCOVERED")


def request(db, fid, actor, reason, now=None):
    """Step 1 of 2: checks every rule and returns a one-time code (15 min). Nothing is approved yet."""
    import hashlib
    import secrets
    import time
    GUARD()
    if not actor.startswith("human:"):
        raise FamilyError("family approvals come from a human actor")
    if not reason or len(reason.strip()) < 10:
        raise FamilyError("a reason of at least 10 characters is required")
    fam = load(fid)
    bad = _blocking_problems(db, fam)
    if bad:
        raise FamilyError("; ".join(bad))
    b = bound_blobs(fid)
    now = int(now or time.time())
    code = secrets.token_hex(3)
    with db.tx():
        db.append("approvals", code_hash=hashlib.sha256(code.encode()).hexdigest(), exp_id=f"family:{fid}",
                  to_state="FAMILY_APPROVED", ts=now, expires_ts=now + APPROVAL_SECONDS, actor=actor,
                  reason=reason.strip(),
                  evidence={"blobs": b, "thresholds": thresholds(), "alpha_family": fam["alpha"]["family"],
                            "instances": [i["id"] for i in fam["instances"]],
                            "successors": discovered_successors(db, fam),
                            "dropped_successors": sorted(exp_id(fid, i["id"]) for i, parent in instances(fam)
                                                         if parent and exp_id(fid, i["id"]) not in
                                                         discovered_successors(db, fam))})
        db.event("family.approval_requested", actor, None, {"family": fid, "reason": reason.strip()})
    return code


def confirm(db, code, blob_prefix, actor, now=None):
    """Step 2 of 2: the user types the code and the first 8 characters of the family file's blob."""
    import hashlib
    import time
    from lab.db import canonical
    GUARD()
    now = int(now or time.time())
    if not actor.startswith("human:"):
        raise FamilyError("only a human can confirm a family")
    a = db.one("SELECT * FROM approvals WHERE code_hash=? AND to_state='FAMILY_APPROVED'",
               hashlib.sha256((code or "").strip().encode()).hexdigest())
    if a is None:
        raise FamilyError("unknown approval code")
    if now > a["expires_ts"]:
        raise FamilyError("approval code expired")
    if db.one("SELECT 1 FROM events WHERE kind='approval.used' AND payload=?", canonical({"approval_id": a["id"]})):
        raise FamilyError("approval code already used")
    ev, fid = json.loads(a["evidence"]), a["exp_id"].split(":", 1)[1]
    b = bound_blobs(fid)
    if b != ev["blobs"]:
        raise FamilyError("a bound file changed since the approval was requested")
    prefix = (blob_prefix or "").strip().lower()
    if len(prefix) < 8 or not b["family"].startswith(prefix):
        raise FamilyError("the typed blob prefix does not match the committed family file")
    if thresholds() != ev["thresholds"]:
        raise FamilyError("a bound gate value changed since the approval was requested")
    bad = _blocking_problems(db, load(fid))
    if bad:
        raise FamilyError("; ".join(bad))
    if discovered_successors(db, load(fid)) != (ev.get("successors") or []):   # a revival since the request
        raise FamilyError("the family's instances changed since approve-family (a successor was revived or left "
                          "DISCOVERED): run approve-family again for a new code, so the approval names what you see "
                          "(amendment 8 point 5)")
    with db.tx():                                        # BEGIN IMMEDIATE: another confirm waits for this one
        if reserved(db, fid) > 1e-12:                    # two codes confirmed at once: alpha_F is reserved once
            raise FamilyError(f"{fid} already holds its alpha_F reservation: revoke-family first, then approve again "
                              "(amendment 8 point 13)")
        bad = _programme_limits(db, load(fid))           # two families confirmed at once: W0, stop and tags hold
        if bad:
            raise FamilyError("; ".join(bad))
        eid = db.event("family.approved", actor, None, {"family": fid, "blobs": b, "thresholds": ev["thresholds"],
                                                        "alpha_family": ev["alpha_family"],
                                                        "instances": ev["instances"],
                                                        "successors": ev.get("successors") or [],
                                                        "dropped_successors": ev.get("dropped_successors") or [],
                                                        "approval_id": a["id"],
                                                        "reason": a["reason"]})
        db.event("approval.used", actor, None, {"approval_id": a["id"]})
        db.append("alpha_ledger", exp_id=f"family:{fid}", ts=now, alpha=ev["alpha_family"], note="A8 reserve")
    return fid, eid


def revoke(db, fid, actor, reason, now=None):
    """Only a human in an interactive terminal (point 5), only before registration. A reserved alpha is released (a
    negative A8 release row). The checks run inside the write transaction, so two revokes, or a revoke and the fleet's
    registration, cannot both pass."""
    import time
    GUARD()
    if not actor.startswith("human:"):
        raise FamilyError("only a human can revoke a family")
    if not reason or len(reason.strip()) < 10:
        raise FamilyError("a reason of at least 10 characters is required")
    with db.tx():                                        # BEGIN IMMEDIATE: the registration and another revoke wait
        if registration_started(db, fid):
            raise FamilyError(f"{fid} is already registered: it can no longer be revoked")
        held = reserved(db, fid)
        db.event("family.revoked", actor, None, {"family": fid, "reason": reason.strip()})
        if held > 0:
            db.append("alpha_ledger", exp_id=f"family:{fid}", ts=int(now or time.time()), alpha=-held,
                      note="A8 release")
    return held


def last_approval_kind(db, fid):
    """'family.approved' or 'family.revoked', whichever the family's latest approval event is, or None."""
    for r in db.q("SELECT kind, payload FROM events WHERE kind IN ('family.approved', 'family.revoked') "
                  "ORDER BY id DESC"):
        if json.loads(r["payload"]).get("family") == fid:
            return r["kind"]
    return None


def approval(db, fid):
    """The id of the valid family.approved event, or None (never approved, revoked, or a bound file or gate value
    changed). A change to lab/engine/catalogue.py does not void a family approval."""
    p = approval_payload(db, fid)
    return p["event_id"] if p else None


def binding_approval(db, fid):
    """The approval that binds what registers next. Before the base batch is registered: the valid approval
    (approval_payload; any change to a bound file or gate value voids it, point 5). Once the base batch is registered:
    the approval its registration cited (registered_approval), so a later change to a file the steps do not pin (the
    adapter, the vocabulary, a gate value read by thresholds) never drops a named successor or fixes the cohort early
    (review of fdd898a), as long as the working family file and module are still the approved blobs (point 18 pins
    those; otherwise None and the family fails closed)."""
    if not registered(db, fid):
        return approval_payload(db, fid)
    p = registered_approval(db, fid)
    try:
        b = blobs(fid)
    except FamilyError:
        return None
    if p is None or any(b[k]["working"] != (p.get("blobs") or {}).get(k) for k in ("family", "module")):
        return None
    return p


def approval_payload(db, fid):
    """The payload of the valid family.approved event (plus its event_id), or None (see approval)."""
    for r in db.q("SELECT id, kind, payload FROM events WHERE kind IN ('family.approved', 'family.revoked') "
                  "ORDER BY id DESC"):
        p = json.loads(r["payload"])
        if p.get("family") != fid:
            continue
        if r["kind"] == "family.revoked":
            return None
        try:
            ok = bound_blobs(fid) == p.get("blobs") and thresholds() == p.get("thresholds")
        except FamilyError:
            ok = False
        return {**p, "event_id": r["id"]} if ok else None
    return None


# ---------- phase A3: discovery, instance specs, registration rules, the download embargo ----------
EMBARGO_FROM = int(datetime(2026, 10, 24, tzinfo=timezone.utc).timestamp())    # amendment 9 point 1
EMBARGO_UNTIL = int(datetime(2026, 11, 28, tzinfo=timezone.utc).timestamp())   # amendment 8 point 17
PROGRAMME_END = int(datetime(2028, 7, 1, tzinfo=timezone.utc).timestamp())     # point 15 (c): a forward PASS by 06-30
SCREEN_SPLITS = ("train3", "validation3")
OPEN_MAX = 3                                   # point 3: at most 3 open families
PRIORITY = 120                                 # job priority of family instances (after every catalogue template)
SPOT = "binance_spot_klines_1h"
KIND_SOURCE = {"klines": "binance_um_klines_1h", "funding": "binance_um_fundingRate", "spot": SPOT,
               "delivery": "binance_cm_klines_1h"}
DATA_HOST = "https://data.binance.vision/"
INSTANCE_RE = re.compile(r"E_([a-z0-9]{3,12})__([a-z0-9_]{2,12})_a8")
FORWARD_PASS = "PASS (family forward test)"    # verdict prefix of a family forward PASS (point 11)
EMBARGO_REASON = ("screening files are missing and may not be downloaded before 2026-11-28 00:00 UTC (amendment 8 "
                  "point 17, amendment 9 point 1)")
_DOWNLOAD_SLOTS = 2                           # amendment 9 point 1: at most 2 downloads at a time, lab-wide
_DOWNLOADS = threading.BoundedSemaphore(_DOWNLOAD_SLOTS)
_ABSENT_LOCK = threading.Lock()


class Embargoed(ReservedData):
    """A family download refused by the embargo (data._fetch re-raises it instead of retrying)."""


def embargo_reason(split):
    """EMBARGO_REASON, naming the split for holdout and forward files (they may be fetched only after 2026-11-27)."""
    return EMBARGO_REASON if split in SCREEN_SPLITS else EMBARGO_REASON.replace("screening", split, 1)


def family_ids():
    return sorted(f[:-5] for f in os.listdir(FAMILY_DIR) if f.endswith(".json") and f != "VOCABULARY.json")


def exp_id(fid, iid):
    return f"E_{fid}__{iid}_a8"


def instance_of(eid):
    """(family id, instance id) of an amendment 8 instance id, else None."""
    m = INSTANCE_RE.fullmatch(eid or "")
    return (m.group(1), m.group(2)) if m else None


def is_instance(db, eid):
    if instance_of(eid):
        return True
    v = db.one("SELECT spec_json FROM experiments WHERE exp_id=? ORDER BY version DESC LIMIT 1", eid)
    return bool(v and json.loads(v["spec_json"] or "{}").get("family"))


def instances(fam):
    """Every pre-enumerated instance as (instance, parent id or None): each base instance, then its successor. A
    successor inherits the fields it does not set from its parent (as validate checks it)."""
    out = []
    for i in fam.get("instances") or []:
        out.append((dict(i), None))
        if i.get("successor"):
            out.append(({**i, **i["successor"], "successor": None}, i["id"]))
    return out


def members(db, fid):
    """Every experiment id of the family, in any state: amendment 8 instance ids E_<fid>__<inst>_a8 only, never another
    experiment whose name merely starts with E_<fid>__ (points 6, 7 and 10)."""
    prefix = f"E_{fid}__"
    return [r[0] for r in db.q("SELECT DISTINCT exp_id FROM experiments WHERE substr(exp_id, 1, ?) = ?",
                               len(prefix), prefix) if (instance_of(r[0]) or (None,))[0] == fid]


def instrument(fam):
    return f"binance_{(fam.get('instrument_model') or {}).get('type')}_{(fam.get('universe') or {}).get('base')}"


def symbols(fam_or_spec):
    """The universe: frozen in a registered spec, else the family file's explicit coin list (universe.symbols, a subset
    of its base universe), else its base universe."""
    if fam_or_spec.get("universe_base"):
        return tuple(fam_or_spec["universe"])
    from lab.engine import data
    u = fam_or_spec.get("universe") or {}
    if u.get("symbols") and delivery_model(fam_or_spec):
        return tuple(u["symbols"])
    return getattr(data, UNIVERSES.get(u.get("base"), "UNIVERSE"))


def delivery_model(fam_or_spec):
    """True for the instrument model spot_delivery_ratio (a family file has a dict, a registered spec a string)."""
    m = fam_or_spec.get("instrument_model")
    return (m.get("type") if isinstance(m, dict) else m) == "spot_delivery_ratio"


def discover_all(db, actor="discovery-catalogue"):
    """Point 6: the discovery agent proposes every instance (base and successor) of every committed, valid family file
    through registry.discover. The graveyard applies as for the catalogue (an exact hit gives SUPPRESSED, and only a
    human revives it with 'materially different because ...'); the family's own members never count. Errors are
    contained per family. Returns [(exp_id, state, graveyard matches)]."""
    from lab import lifecycle, registry
    out = []
    for fid in family_ids():
        rel = f"research/families/{fid}.json"
        try:
            if not lifecycle.git_committed(rel):
                continue
            fam = load(fid)
            if fam.get("family_id") != fid or validate(fam):
                continue
            own = members(db, fid)
            for inst, parent in instances(fam):
                eid = exp_id(fid, inst["id"])
                if eid in own:
                    continue
                text = inst.get("why") if parent else inst.get("rule")
                st, dup = registry.discover(
                    db, eid, f"{fam['title']} - {inst['id']}: {text}", fam["mechanism"]["tag"], instrument(fam),
                    inst["horizon"], inst["execution"], rel, actor, exclude=own, family_instance=True,
                    extra={"template": f"{fid}__{inst['id']}", "family": fid, "instance": inst["id"],
                           "parent": parent, "function": inst["function"], "title": f"{fam['title']} - {inst['id']}",
                           "discovered_by": actor, "reason": text, "amendment": 8,
                           "evidence": [e.get("ref") for e in fam["mechanism"].get("evidence") or []],
                           "data_requirements": [d.get("source") for d in fam.get("data") or []]})
                own.append(eid)
                out.append((eid, st, dup))
        except Exception as e:                       # one broken family never stops the others
            out.append((f"family:{fid}", f"error: {e!r}"[:200], []))
    return out


def template(spec):
    """The template view of a registered instance for the pipeline: the calling convention of a cross-sectional
    catalogue template, built from the frozen spec and the family's mechanism module. It is never put into
    catalogue.TEMPLATES. The module function is called as fn(bars_by, funding_by, params, fit, volume_by=, extra=)."""
    fid, fn = spec["family"], spec["function"]

    def family(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
        import importlib
        return getattr(importlib.import_module(f"lab.families.{fid}"), fn)(bars_by, funding_by, p, fit,
                                                                          volume_by=volume_by, extra=extra)
    return {"family": family, "cross_sectional": True, "universe": spec.get("universe_base"), "protocol": 3,
            "mechanism_tag": spec.get("mechanism_tag"), "hypothesis": spec.get("hypothesis"), "grid": spec.get("grid"),
            "long_only": True, "family_id": fid, "instance": spec.get("instance")}


class FamilyData:
    """A family's market data next to its instrument series: the perp bars and the raw settled funding of each coin,
    for the benchmark (equal-weight buy-and-hold of the same perps with the catalogue's costs and funding, point 8).
    The mechanism functions never see it (extra=None)."""

    def __init__(self, perp, funding):
        self.perp, self.funding = perp, funding

    def drop(self, s):
        self.perp.pop(s, None), self.funding.pop(s, None)


def transform(spec, per_sym, split):
    """Instrument model spot_perp_ratio (fcarry.json instrument_model): per coin one series (ts, spot_open / perp_open,
    spot_close / perp_close) on the intersection of hours, and the funding in the cost convention of
    backtest.apply_costs: minus the settled rate, so a +1 position (long spot, short perp) earns it. A missing hour of
    either leg lowers the coin's coverage (the existing quality rule excludes it); a non-positive price leaves a
    non-positive ratio, which the quality rule flags. Returns (bars, funding, duplicates, FamilyData)."""
    from lab.engine import data
    model = spec.get("instrument_model")
    if model == "spot_delivery_ratio":
        return _transform_delivery(per_sym, split)
    if model != "spot_perp_ratio":
        raise FamilyError(f"instrument model {model!r} is not implemented")
    bars, funding, dups, perp, raw = {}, {}, {}, {}, {}
    for s, f in per_sym.items():
        pb, fr, d1 = data.load(f, split)
        sb, _, d2 = data.load({"klines": f.get("spot") or [], "funding": []}, split)
        spot = {ts: (o, c) for ts, o, c in sb}
        bars[s] = [(ts, spot[ts][0] / o if o > 0 else 0.0, spot[ts][1] / c if c > 0 else 0.0)
                   for ts, o, c in pb if ts in spot]
        funding[s] = {ts: -r for ts, r in fr.items()}
        dups[s], perp[s], raw[s] = d1 + d2, pb, fr
    return bars, funding, dups, FamilyData(perp, raw)


def _transform_delivery(per_sym, split):
    """Instrument model spot_delivery_ratio (F2 dbasis): per coin one series (ts, spot_open / F_open, spot_close /
    F_close) stitched from the held quarterlies (data.quarterlies: each contract from the previous roll time up to its
    own), on the hours both the spot and the held contract have. No funding (a delivery future has none). The bar that
    opens at a roll time carries a return between two contracts; the mechanism module holds 0 on it. A missing hour of
    either leg lowers the coin's coverage (the quality rule excludes it). The perp bars and settled funding are kept for
    the benchmark only (point 8: equal-weight buy-and-hold of the same perps). Returns (bars, funding, duplicates,
    FamilyData)."""
    from lab.engine import data
    bars, funding, dups, perp, raw = {}, {}, {}, {}, {}
    for s, f in per_sym.items():
        pb, fr, d1 = data.load(f, split)
        sb, _, d2 = data.load({"klines": f.get("spot") or [], "funding": []}, split)
        spot, series, d3 = {ts: (o, c) for ts, o, c in sb}, [], 0
        for c in f.get("delivery") or []:
            cb, _, dd = data.load({"klines": c.get("paths") or [], "funding": []}, split)
            d3 += dd
            series += [(ts, spot[ts][0] / o if o > 0 else 0.0, spot[ts][1] / cl if cl > 0 else 0.0)
                       for ts, o, cl in cb if c["from"] <= ts < c["to"] and ts in spot]
        series.sort()
        bars[s], funding[s], dups[s], perp[s], raw[s] = series, {}, d2 + d3, pb, fr
    return bars, funding, dups, FamilyData(perp, raw)


def attribution(spec, m, bars=None, pos=None):
    """Mechanism attribution (point 8, stricter): the family module's rule on portfolio metrics; for fcarry funding
    income minus all costs > 0 and gross ratio P&L <= funding income. A module that declares
    ATTRIBUTION_NEEDS_POSITIONS (dbasis: the locked basis is booked per held segment) also gets the instrument bars
    and positions. Returns {..., 'gates': {name: ok}}."""
    import importlib
    mod = importlib.import_module(f"lab.families.{spec['family']}")
    if getattr(mod, "ATTRIBUTION_NEEDS_POSITIONS", False):
        return mod.attribution(m, bars=bars, pos=pos)
    return mod.attribution(m)


def instance_spec(fam, iid, blobs, engine_blobs):
    """Experiment version 2 of one instance (design (B) 'Registration mapping', point 18): every
    registry.REQUIRED_SPEC field, a truthy alpha dict (so it can never go through registry.add_version, which does
    float(alpha)), template '<fid>__<inst>', and the blobs of the 4 bound files plus the engine files."""
    from lab import pipeline
    from lab.engine import catalogue
    fid = fam["family_id"]
    inst, parent = next((i, p) for i, p in instances(fam) if i["id"] == iid)
    m, u, c = fam["mechanism"], fam["universe"], fam["costs"]
    rel = f"research/families/{fid}.json"
    text = inst.get("why") if parent else inst.get("rule")
    refs = [e.get("ref") for e in m.get("evidence") or []]
    return {"template": f"{fid}__{iid}", "family": fid, "instance": iid, "parent": parent, "function": inst["function"],
            "title": f"{fam['title']} - {iid}", "hypothesis": f"{m['return_source']}: {text}",
            "mechanism": m["non_price_prediction"], "mechanism_tag": m["tag"], "attribution": m["attribution"],
            "evidence": [f"{e.get('ref')} ({e.get('status')})" for e in m.get("evidence") or []],
            "sources": [rel] + refs, "instrument": instrument(fam), "instrument_model": fam["instrument_model"]["type"],
            "universe": list(symbols(fam)), "universe_base": u["base"], "min_symbols": u["min_symbols"],
            "holdout_exclude": list(u.get("holdout_exclude") or []), "clean_holdout": bool(u.get("clean_holdout")),
            "timeframe": "1h", "horizon": inst["horizon"], "execution": inst["execution"], "long_only": True,
            "decision_time_utc": fam["decision_time_utc"], "max_lookback_days": inst["max_lookback_days"],
            "datasets": {"source": [d["url"] for d in fam["data"]], "splits": pipeline._windows(3),
                         "reserved_from": "2025-01-01 (never read)",
                         "downloads": "data.binance.vision only, through the embargo guard (amendment 8 point 17, "
                                      "amendment 9 point 1)"},
            "grid": inst["grid"],
            "methodology": {**catalogue.PROTOCOLS[3], "amendment": "research/PROTOCOL_V3.md amendment 8",
                            "screen": "a filter only: every PROTOCOL v3 gate plus mechanism attribution; DSR is "
                                      "recorded and decides nothing (point 8)"},
            "baseline": fam["instrument_model"]["benchmark"],
            "costs": {"taker_fee": c["taker_fee"], "half_spread": c["half_spread"], "slippage": c["slippage"],
                      "funding": c.get("funding"), "per": c.get("per")},
            "benchmark_costs": catalogue.COSTS,
            "acceptance": "every PROTOCOL v3 gate plus mechanism attribution in the screen; a survivor goes to the "
                          "family forward test (OBSERVATION), which alone decides (amendment 8 points 8, 10, 11)",
            "rejection": "train gate, pre-validation gate, any validation gate except DSR, or mechanism attribution "
                         "fails (research/PROTOCOL_V3.md amendment 8)",
            "alpha": {"in_sample": 0, "forward_family": fam["alpha"]["family"],
                      "rule": "alpha_F / M at cohort.fixed, M <= 3 (amendment 8 point 13)"},
            "code": [f"lab/families/{fid}.py", "lab/families/__init__.py"] + list(pipeline.ENGINE_CODE),
            "code_blobs": {**{k: blobs[k] for k in ("family", "module", "adapter", "vocabulary")}, **engine_blobs},
            "seed": pipeline.SEED, "protocol_version": 3, "amendment": 8, "observation_test": False,
            "forward": fam["forward"], "label": "EXPLORATORY (the screen is a filter; the family forward test decides)"}


def reserved(db, fid):
    """alpha_F the family still holds: the A8 rows of family:<fid> only (reserve, spend, release; point 13)."""
    return db.one("SELECT COALESCE(SUM(alpha), 0) FROM alpha_ledger WHERE exp_id=? AND note IN (?, ?, ?)",
                  f"family:{fid}", *A8_NOTES)[0]


BOUND = ("family", "module", "adapter", "vocabulary")      # the files an approval binds (point 5)


def reserved_id(eid):
    """Ids only the discovery agent may create, from a committed family file (families.discover_all): a family
    instance id E_<fid>__<inst>_a8 (anything containing one, in any case, or ending in _a8 after trimming), and any id
    with ':' (family:<fid> names a family's alpha reservation, point 13), and any id that starts like a family
    instance (E_<fid>__, in any case), so no other experiment can look like a member of a family."""
    e = (eid or "").strip()
    return ":" in e or e.lower().endswith("_a8") or bool(re.search(INSTANCE_RE.pattern, e, re.IGNORECASE)) or \
        bool(re.match(r"E_[a-z0-9]{3,12}__", e, re.IGNORECASE))


def spec_problems(db, eid, fam, p=None, need_v2=False):
    """Amendment 8 points 6 and 7: what registers is exactly what the family file and its approval bind. Version 1 was
    written by the discovery agent from the family file (family and instance set, the agent as the actor of the first
    transition, the file's mechanism tag and fingerprint). Version 2, when it exists (and `need_v2`), carries the same
    tag and fingerprint, the family file as spec_path, the approved family blob as code_hash, and a spec equal field for
    field to instance_spec(the family file, the approval's blobs, the engine blobs recorded in it); no other version.
    Returns problems (empty = it may register)."""
    from lab import pipeline, registry
    from lab.db import canonical
    fid, x = fam.get("family_id"), instance_of(eid)
    inst = next((i for i, _ in instances(fam) if x and x[0] == fid and i.get("id") == x[1]), None)
    if inst is None:
        return [f"{eid} is not an instance of the family file {fid}"]
    tag = fam["mechanism"]["tag"]
    fp = registry.fingerprint(tag, instrument(fam), inst["horizon"], inst["execution"])
    rows = db.q("SELECT version, mechanism_tag, fingerprint, spec_json, spec_path, code_hash FROM experiments "
                "WHERE exp_id=? ORDER BY version", eid)
    first = db.one("SELECT from_state, to_state, actor FROM transitions WHERE exp_id=? ORDER BY id LIMIT 1", eid)
    v1 = json.loads(rows[0]["spec_json"] or "{}") if rows else {}
    by = str(v1.get("discovered_by") or "")
    bad = []
    if not rows or rows[0]["version"] != 1 or (v1.get("family"), v1.get("instance")) != (fid, inst["id"]) or \
            not by.startswith("discovery-") or first is None or \
            (first["from_state"], first["to_state"], first["actor"]) != (None, "DISCOVERED", by):
        bad.append(f"{eid}: version 1 was not written by the discovery agent from the family file (amendment 8 "
                   f"point 6)")
    if any((r["mechanism_tag"], r["fingerprint"]) != (tag, fp) for r in rows):
        bad.append(f"{eid}: a spec version does not carry the family file's mechanism tag {tag} and fingerprint")
    if len(rows) > 2:
        bad.append(f"{eid}: spec version {rows[-1]['version']} exists; a family instance registers only with version "
                   f"2, built from the approved family file (amendment 8 point 7)")
    elif len(rows) == 2 and p is not None:
        v, spec = rows[1], json.loads(rows[1]["spec_json"] or "{}")
        engine = {f: (spec.get("code_blobs") or {}).get(f) for f in pipeline.ENGINE_CODE}
        want = json.loads(canonical(instance_spec(fam, inst["id"], p["blobs"], engine)))
        if spec != want or not all(engine.values()) or v["spec_path"] != f"research/families/{fid}.json" or \
                v["code_hash"] != p["blobs"]["family"]:
            bad.append(f"{eid}: spec version 2 is not the one built from the approved family file and blobs "
                       f"(amendment 8 point 7)")
    elif need_v2 and len(rows) < 2:
        bad.append(f"{eid}: registration needs the spec version 2 built from the approved family file")
    return bad


def cited_approval(db, eid):
    """The family.approved payload (plus event_id) that eid's registration cited (register_transition's evidence), or
    None."""
    r = db.one("SELECT evidence FROM transitions WHERE exp_id=? AND to_state='REGISTERED' ORDER BY id LIMIT 1", eid)
    aid = json.loads((r and r["evidence"]) or "{}").get("family_approval_event")
    ev = db.one("SELECT payload FROM events WHERE id=? AND kind='family.approved'", aid) if aid is not None else None
    return {**json.loads(ev["payload"]), "event_id": aid} if ev else None


def base_waiting(db, fid, p):
    """Points 6 and 7: the approved base instances register only together, as one batch, when every one of them is
    DISCOVERED (or REGISTERED under this approval in a batch that stopped part-way). Returns the waiting reason naming
    the others (empty = the batch may register)."""
    from lab.lifecycle import state
    gone = []
    for iid in p.get("instances") or []:
        e = exp_id(fid, iid)
        st = state(db, e)
        if st == "DISCOVERED" or (st == "REGISTERED" and
                                  (cited_approval(db, e) or {}).get("event_id") == p["event_id"]):
            continue
        gone.append(f"{e} ({st or 'missing'})")
    if not gone:
        return []
    return [f"base instance(s) not DISCOVERED: {', '.join(gone)}. The base instances register only together, as one "
            f"batch (amendment 8 point 7), and revival comes before approve-family (point 6)"
            + ("" if registration_started(db, fid) else ": revoke-family, revive them in a terminal (python3 -m lab "
                                                        "approve / confirm), then approve-family again")]


PARTIAL_VOID = ("a registration batch stopped part-way and the family approval is no longer valid (a bound file or "
                "gate value changed): restore the bound files exactly as approved and the batch completes (amendment 8 "
                "points 5 and 7)")


def unfinished(db):
    """Families whose registration stopped part-way (point 7): a member in REGISTERED without the family's base
    batch.registered event, or a member in REGISTERED or SCREENING without all of its screening jobs. register_batch
    completes them in a later pass."""
    import sqlite3
    from lab.lifecycle import state
    from lab.pipeline import STEPS
    done, out = _base_batches(db), set()
    for r in db.q("SELECT DISTINCT exp_id FROM transitions WHERE to_state='REGISTERED'"):
        x, st = instance_of(r[0]), state(db, r[0])
        if not x or x[0] in out or st not in ("REGISTERED", "SCREENING"):
            continue
        try:
            n = db.one(f"SELECT COUNT(*) FROM jobs WHERE job_id IN ({','.join('?' * len(STEPS))})",
                       *(f"{s}|{r[0]}" for s in STEPS))[0]
        except sqlite3.OperationalError:          # no job table yet
            n = 0
        if n < len(STEPS) or (st == "REGISTERED" and x[0] not in done):
            out.add(x[0])
    return sorted(out)


def register_transition(db, eid, fid, actor):
    """DISCOVERED -> REGISTERED for an instance of an approved family (mirrors templates.register_transition; the only
    registration path for families, amendment 8 point 7): a valid family approval, its reserved alpha, an approved
    instance, and the spec version 2 built from the approved family file, equal field for field (spec_problems). Inside
    a transaction of the caller (pipeline._register_family_one writes version 2 in the same one) it writes into it, so
    a refusal leaves no version 2 behind."""
    import contextlib
    import time
    from lab import lifecycle, registry
    if lifecycle.state(db, eid) != "DISCOVERED":
        raise lifecycle.LifecycleError(f"{eid} is not DISCOVERED")
    p = binding_approval(db, fid)
    if p is None:
        raise lifecycle.LifecycleError(f"family {fid} has no valid human approval")
    if reserved(db, fid) < p["alpha_family"] - 1e-12:
        raise lifecycle.LifecycleError(f"family {fid} has no reserved alpha")
    v = registry.latest(db, eid)
    spec = json.loads(v["spec_json"] or "{}")
    bad = spec_problems(db, eid, load(fid), p, need_v2=True)
    if bad or spec.get("family") != fid or v["version"] != 2 or \
            any(not spec.get(k) for k in registry.REQUIRED_SPEC) or not spec.get("seed") or \
            (spec.get("parent") or spec.get("instance")) not in p.get("instances", []):
        raise lifecycle.LifecycleError("registration requires the family spec version 2 built from the approved file, "
                                       "blobs and instances" + (f": {'; '.join(bad)}" if bad else ""))
    with (contextlib.nullcontext() if db.con.in_transaction else db.tx()):
        db.append("transitions", exp_id=eid, ts=int(time.time()), from_state="DISCOVERED", to_state="REGISTERED",
                  actor=actor, reason=f"instance of approved family {fid} (amendment 8)",
                  evidence={"family_approval_event": p["event_id"]})
        db.event("lifecycle.transition", actor, eid, {"from": "DISCOVERED", "to": "REGISTERED",
                                                     "reason": f"approved family {fid}"})


# ---------- F2: the coverage of the COIN-M quarterlies and the synthetic convergence test (design (D) F2) ----------
def selftest_problems(fid):
    """The module's synthetic convergence test (explicit criteria in its docstring), or [] if it has none or passes."""
    import importlib
    mod = importlib.import_module(f"lab.families.{fid}")
    if not hasattr(mod, "convergence_selftest"):
        return ["the mechanism module has no synthetic convergence test (F2 design: required before approval)"]
    r = mod.convergence_selftest()
    return [] if r["ok"] else [f"synthetic convergence test fails: {k}" for k, ok in r["checks"].items() if not ok]


TRUST_INJECTED_COVERAGE = False               # tests only: a coverage record from an injected HEAD counts


def delivery_candidates(fam):
    """Every coin the coverage check examines: the base universe without holdout_exclude (BTC, ETH, SOL), so the
    universe is the mechanically covered set and never a hand-picked list (no researcher degree of freedom)."""
    from lab.engine import data
    u = fam.get("universe") or {}
    base = getattr(data, UNIVERSES.get(u.get("base"), "UNIVERSE"), ())
    return [s for s in base if s not in set(u.get("holdout_exclude") or []) | set(data.HOLDOUT_SEEN)]


def delivery_urls(syms, splits=COVERAGE_SPLITS):
    """{coin: [url]} of every quarterly kline zip the screen and the holdout read (calendar only, no network)."""
    from lab.engine import data
    return {s: [u for sp in splits for c in data.delivery_plan(s, sp) for u, _ in c["files"]] for s in syms}


def _head(url):
    """{present, status, length, etag} from a HEAD request: present only on HTTP 200, absent only on 404; anything
    else raises, so no record is written (never 'absent' on a doubt)."""
    if not url.startswith(DATA_HOST + "data/futures/cm/"):
        raise FamilyError(f"coverage checks only COIN-M files on {DATA_HOST}: {url}")
    with _download_slot():
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={
                    "User-Agent": "copybot-research/1.0"}), timeout=60) as r:
                if r.status != 200:
                    raise FamilyError(f"HEAD {url} answered {r.status}: not counted either way")
                return {"present": True, "status": 200, "length": r.headers.get("Content-Length"),
                        "etag": r.headers.get("ETag")}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"present": False, "status": 404}
            raise


def check_coverage(db, fid, actor, head=None, now=None):  # fid: a family id or a family file path (a draft)
    """F2 design: before approval, HEAD requests establish which coins have every quarterly zip of 2022-01..2024-12
    (train3, validation3, holdout). Point 17: no request before 2026-11-28 00:00 UTC. HEAD reads no data. Records
    family.coverage {family, checked: {url: present}, covered}. Returns (covered coins, {url: present})."""
    from lab.engine import data
    now = data.CLOCK() if now is None else now
    if now < EMBARGO_UNTIL:
        raise FamilyError("the coverage check sends HEAD requests: none before 2026-11-28 00:00 UTC (amendment 8 "
                          "point 17; pm_lp uses the network until 2026-11-27)")
    fam = load(fid)
    fid = fam.get("family_id") or fid
    if not delivery_model(fam):
        raise FamilyError(f"{fid} is not a spot_delivery_ratio family: it has no quarterlies to check")
    urls = delivery_urls(delivery_candidates(fam))
    evidence = {}
    for us in urls.values():
        for u in us:
            r = (head or _head)(u)
            evidence[u] = r if isinstance(r, dict) else {"present": bool(r)}
    checked = {u: bool(r.get("present")) for u, r in evidence.items()}
    covered = sorted(s for s, us in urls.items() if all(checked[u] for u in us))
    db.event("family.coverage", actor, None, {"family": fid, "splits": list(COVERAGE_SPLITS), "checked": checked,
                                               "evidence": evidence, "covered": covered, "coins": list(urls),
                                               "via": "http" if head is None else "injected"})
    return covered, checked


def coverage_problems(db, fam):
    """Approval and registration of a spot_delivery_ratio family: every coin of universe.symbols must have every
    quarterly zip of train3, validation3 and holdout recorded present by a family.coverage check (the latest record
    of each URL counts), and at least 5 coins (F2 design). Returns problems."""
    seen = {}
    for r in db.q("SELECT payload FROM events WHERE kind='family.coverage' ORDER BY id"):
        p = json.loads(r[0])
        if p.get("via") == "http" or (TRUST_INJECTED_COVERAGE and p.get("via") == "injected"):
            seen.update(p.get("checked") or {})
    cand = delivery_candidates(fam)
    urls = delivery_urls(cand)
    unchecked = [s for s in cand if not all(u in seen for u in urls[s])]
    covered = sorted(s for s in cand if s not in unchecked and all(seen[u] for u in urls[s]))
    out = []
    if unchecked:
        out.append(f"COIN-M quarterly coverage is not recorded for {len(unchecked)} candidate coin(s) "
                   f"({', '.join(unchecked[:6])}{' ...' if len(unchecked) > 6 else ''}): run python3 -m lab "
                   f"family-coverage <family file> (from 2026-11-28; amendment 8 point 17)")
    elif sorted(symbols(fam)) != covered:
        out.append(f"universe.symbols must be exactly the coins with verified continuous quarterlies 2022-01..2024-12 "
                   f"({', '.join(covered) or 'none'}): no coin added or left out by hand")
    if not unchecked and len(covered) < DELIVERY_MIN_COINS:
        out.append(f"fewer than {DELIVERY_MIN_COINS} coins with verified continuous quarterlies 2022-01..2024-12: "
                   f"F2 is not approved (design)")
    return out


# ---------- the download embargo (amendment 8 point 17 with amendment 9 point 1) ----------
def fetch_allowed(source, split, now=None):
    """Before 2026-10-24 00:00 UTC only the train3/validation3 spot klines of a family may be downloaded; from then until
    2026-11-28 00:00 UTC nothing; from 2026-11-28 what the family needs, holdout and forward data included (only after
    2026-11-27). Reserved windows stay refused by data.window. The clock is data.CLOCK (replaceable in tests)."""
    from lab.engine import data
    now = data.CLOCK() if now is None else now
    if now >= EMBARGO_UNTIL:
        return True
    return now < EMBARGO_FROM and source == SPOT and split in SCREEN_SPLITS


def source_of(url):
    if url.startswith(DATA_HOST + "data/spot/") and "/klines/" in url:
        return SPOT
    if url.startswith(DATA_HOST + "data/futures/cm/") and "/klines/" in url:   # F2: COIN-M quarterlies (point 17)
        return KIND_SOURCE["delivery"]
    if url.startswith(DATA_HOST + "data/futures/um/"):
        return KIND_SOURCE["funding"] if "/fundingRate/" in url else KIND_SOURCE["klines"] if "/klines/" in url \
            else None
    return None


def _absent_file():
    from lab.engine import data
    return os.path.join(data.CACHE, "absent_404.json")


def absent():
    """URLs the archive answered with 404 (never requested again: a missing month of 2022-2024 does not appear)."""
    try:
        with open(_absent_file(), encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def _mark_absent(url):
    path = _absent_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _ABSENT_LOCK, _flock(path + ".lock"):           # heavy workers are separate processes
        urls = absent() | {url}
        part = f"{path}.{os.getpid()}.{threading.get_ident()}.part"
        with open(part, "w", encoding="utf-8") as f:
            json.dump(sorted(urls), f)
        os.replace(part, path)


@contextlib.contextmanager
def _flock(path, blocking=True):
    """An exclusive lock on `path` across processes (fcntl.flock; a no-op where fcntl does not exist). Yields True when
    held; with blocking=False it yields False at once if another holder has it."""
    try:
        import fcntl
    except ImportError:                                # not the Linux runtime host: threads only
        yield True
        return
    f = open(path, "a+")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    finally:
        f.close()


@contextlib.contextmanager
def _download_slot():
    """One of the 2 download slots of amendment 9 point 1, across every process of the lab (the data step runs in the
    fleet's main process, the forward and holdout steps in heavy worker processes): a thread semaphore inside this
    process and one of 2 slot lock files in the market cache across processes."""
    from lab.engine import data
    d = os.path.join(data.CACHE, ".download_slots")
    os.makedirs(d, exist_ok=True)
    with _DOWNLOADS:
        while True:
            for i in range(_DOWNLOAD_SLOTS):
                with _flock(os.path.join(d, f"slot{i}.lock"), blocking=False) as held:
                    if held:
                        yield
                        return
            time.sleep(0.2)


def _urlopen(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"}),
                                  timeout=120).read()


def guarded_get(split, fetch=None):
    """The `get` given to data._fetch for every family file. Before each request: a remembered 404 is answered without
    the network, only data.binance.vision is used, and the embargo is checked (Embargoed otherwise). At most 2
    downloads run at a time (amendment 9). `fetch(url)` is the network read (tests inject it). A forward window's 404 is
    never remembered nor answered from memory: a monthly file published late is fetched by the next run (finding
    protocol-statistics #8)."""
    fwd = split.startswith("fwd")

    def get(url):
        if not fwd and url in absent():
            raise urllib.error.HTTPError(url, 404, "not in the archive (remembered 404)", None, None)
        src = source_of(url)
        if src is None:
            raise Embargoed(f"family data comes only from {DATA_HOST} klines and funding files: {url}")
        if not fetch_allowed(src, split):
            raise Embargoed(embargo_reason(split))
        with _download_slot():
            try:
                return (fetch or _urlopen)(url)
            except urllib.error.HTTPError as e:
                if e.code == 404 and not fwd:
                    _mark_absent(url)
                raise
    get.guarded = True
    return get


def expected_paths(syms, splits, spot=True, delivery=False):
    """[(source, split, url, cache path)] of every file the screening reads for these symbols (no network); with
    `delivery` also the COIN-M quarterlies of instrument model spot_delivery_ratio."""
    from lab.engine import data
    return [(KIND_SOURCE[kind], sp, u, p) for sp in splits for s in syms
            for kind, pairs in data.expected_paths(s, sp, spot, delivery=delivery).items() for u, p in pairs]


def missing(syms, splits, spot=True, delivery=False):
    """Files not in the cache and not known to be absent from the archive."""
    gone = absent()
    return [x for x in expected_paths(syms, splits, spot, delivery) if x[2] not in gone and not os.path.exists(x[3])]


def blocked(syms, splits, now=None, delivery=False):
    """Missing files that may not be downloaded now (empty = the step can read or fetch everything)."""
    return [x for x in missing(syms, splits, delivery=delivery) if not fetch_allowed(x[0], x[1], now)]


def ready(syms, splits, now=None, delivery=False):
    return not blocked(syms, splits, now, delivery)


# ---------- registration rules (point 7) ----------
def forward_passes(db, by=None):
    """Family instances with a forward PASS, and their families as family:<fid> (point 15): only a forward result of
    its cohort counts (forward_result: the step recorded it, with the cohort id and its hash-matching observe.json),
    never a row typed or forged past it, nor a family.closed event on its own. `by`: only results recorded before
    that time (point 15 c: a forward PASS by 2028-06-30)."""
    passes = set()
    for e in {r[0] for r in db.q("SELECT DISTINCT exp_id FROM results WHERE label='VALIDATION'")}:
        if instance_of(e) and any(forward_result(db, e, r) == "PASS" for r in db.q(
                "SELECT id, verdict, metrics, evidence, ts FROM results WHERE exp_id=? AND label='VALIDATION' "
                "ORDER BY id", e) if by is None or (r["ts"] or 0) < by):
            passes.add(e)
    return passes | {f"family:{instance_of(e)[0]}" for e in passes}


def _closed(db):
    """family.closed payloads in order: {family, outcome in PASS, FAIL, FUTILE_IN_SAMPLE, UNTESTABLE}."""
    return [json.loads(r["payload"]) for r in db.q("SELECT payload FROM events WHERE kind='family.closed' ORDER BY id")]


def programme_stop(db, now=None):
    """Point 15 (b) and (c): 3 families in a row closed without a forward PASS, or no forward PASS by 2028-06-30. Only a
    new dated amendment restarts the programme, so the stop latches: (b) holds once any 3 consecutive closes lack a
    forward PASS, whatever closes later; (c) counts only forward PASS results recorded before 2028-07-01 00:00 UTC. A
    close counts as a PASS only when a member has a forward PASS that counts (forward_passes), never on the outcome
    field of the event alone. (a), wealth below alpha_F, is the budget rule of an approval."""
    from lab.engine import data
    now = data.CLOCK() if now is None else now
    passed, run, bad = forward_passes(db), 0, []
    for p in _closed(db):
        run = 0 if f"family:{p.get('family')}" in passed else run + 1
        if run >= 3:
            bad.append("programme stopped: 3 families in a row closed without a forward PASS (amendment 8 point 15 b)")
            break
    if now >= PROGRAMME_END and not forward_passes(db, by=PROGRAMME_END):
        bad.append("programme stopped: no forward PASS by 2028-06-30 (amendment 8 point 15 c)")
    return bad


def open_families(db):
    """Families with a registered instance and no family.closed event."""
    reg ={instance_of(r[0])[0] for r in db.q("SELECT DISTINCT exp_id FROM transitions WHERE to_state='REGISTERED'")
           if instance_of(r[0])}
    return reg - {p.get("family") for p in _closed(db)}


def family_tags(db):
    """{fid: canonical tags} of every family in the programme (point 3): its registration started, or its latest
    approval event is an approval (valid or void, not revoked). The tags are those its instances carry in the registry
    (discovered from its family file and checked at registration, spec_problems), else its family file's tag."""
    fids = {x[0] for x in (instance_of(r[0]) for r in db.q(
        "SELECT DISTINCT exp_id FROM transitions WHERE to_state='REGISTERED'")) if x}
    last = {}
    for r in db.q("SELECT kind, payload FROM events WHERE kind IN ('family.approved', 'family.revoked') ORDER BY id"):
        last[json.loads(r["payload"]).get("family")] = r["kind"]
    fids |= {f for f, k in last.items() if f and k == "family.approved"}
    out = {}
    for f in sorted(fids):
        prefix = f"E_{f}__"
        tags = {r[0] for r in db.q("SELECT DISTINCT mechanism_tag FROM experiments WHERE substr(exp_id, 1, ?) = ?",
                                   len(prefix), prefix) if r[0]}
        if not tags:
            try:
                tags = {load(f)["mechanism"]["tag"]}
            except Exception:                        # no family file (an id from another lab): no tag known
                tags = set()
        out[f] = tags
    return out


def tag_problems(db, fam, registration=False):
    """Point 3: at most 2 families per canonical tag in the whole programme (family_tags), and at most 1 open family
    per tag at a time. At approval every other family on the tag that is not closed is open (approved and waiting, or
    registered); at registration only the registered ones without a family.closed event are (open_families), so two
    approvals from before this rule never block each other. Returns problems (empty = allowed)."""
    fid, tag = fam.get("family_id"), (fam.get("mechanism") or {}).get("tag")
    others = sorted(f for f, tags in family_tags(db).items() if f != fid and tag in tags)
    bad = []
    if len(others) >= TAG_MAX:
        bad.append(f"at most {TAG_MAX} families per canonical tag in the whole programme: {tag} already has "
                   f"{', '.join(others)} (amendment 8 point 3)")
    live = sorted(set(others) & open_families(db)) if registration else [f for f in others if closed(db, f) is None]
    if live:
        bad.append(f"at most 1 open family per tag at a time: {', '.join(live)} on {tag} is not closed (amendment 8 "
                   f"point 3)")
    return bad


def graveyard_recheck(db, fam, vocab=None):
    """Point 6 at registration: graveyard hits (same tag and execution or fingerprint, and related tags) that the
    family file does not acknowledge. The family's own members never count."""
    from lab import registry
    tags = (vocab or vocabulary())["tags"]
    tag, own = fam["mechanism"]["tag"], set(members(db, fam["family_id"]))
    hits = set(registry.graveyard_related(db, {tag} | set(tags.get(tag, {}).get("related", [])), exclude=own))
    for inst, _ in instances(fam):
        fp = registry.fingerprint(tag, instrument(fam), inst["horizon"], inst["execution"])
        hits |= set(registry.graveyard(db, tag, inst["execution"], fp, exclude=own))
    return sorted(hits - {a.get("exp_id") for a in fam.get("graveyard_acknowledged") or []})


def registration_block(db, fam, now=None, successor=None):
    """Why the family's base instances (or, with `successor`, that successor) may not register now (empty = they may),
    point 7 with amendment 9 point 1: a valid approval with its reserved alpha, the base registered only once, no
    programme stop, at most 3 open families, the per-tag limits of point 3 (tag_problems), no open experiment outside
    the family on the same tag and execution (a DISCOVERED candidate covers nothing yet), the graveyard re-check, and
    no screening file that is missing and may not be downloaded now. A successor (point 9) registers as an extra batch
    of its open family: after the base batch,
    before the cohort is fixed, and only when its parent's frozen training artifact meets the trigger."""
    from lab import lifecycle, registry
    fid = fam["family_id"]
    p = binding_approval(db, fid)
    if p is None:
        return ["no valid family approval"]
    bad = []
    if reserved(db, fid) < p["alpha_family"] - 1e-12:
        bad.append("alpha_F is not reserved for the family")
    if successor is None and registered(db, fid):
        bad.append("the base instances are already registered (once, as one batch)")
    if successor is not None:
        inst, parent = next(((i, q) for i, q in instances(fam) if exp_id(fid, i["id"]) == successor), (None, None))
        if parent is None or parent not in p.get("instances", []):
            bad.append(f"{successor} is not a successor of an approved instance")
        elif successor not in (p.get("successors") or []):
            bad.append(f"{successor} was not DISCOVERED when approve-family was requested, so the approval does not "
                       f"name it: a successor revived after the approval never registers (amendment 8 points 5, 6 "
                       f"and 9)")
        elif not ever_registered(db, exp_id(fid, parent)):
            bad.append(f"its parent {exp_id(fid, parent)} is not registered")
        else:
            st, why = trigger_state(db, inst, exp_id(fid, parent))
            if st != "met":
                bad.append(f"successor trigger {st}: {why}")
        if cohort(db, fid) is not None:
            bad.append("the family cohort is fixed: successors register only before (point 9)")
    bad += programme_stop(db, now)
    others = open_families(db) - {fid}
    if successor is None and len(others) >= OPEN_MAX:
        bad.append(f"{OPEN_MAX} families are already open: {', '.join(sorted(others))}")
    if successor is None:
        bad += tag_problems(db, fam, registration=True)
    own, tag, cover = set(members(db, fid)), fam["mechanism"]["tag"], set()
    for inst, _ in instances(fam):
        fp = registry.fingerprint(tag, instrument(fam), inst["horizon"], inst["execution"])
        cover |= {e for e in registry.covering(db, tag, inst["execution"], fp, exclude=own)
                  if lifecycle.state(db, e) != "DISCOVERED"}
    if cover:
        bad.append(f"open experiment(s) outside the family cover the same tag and execution: {', '.join(sorted(cover))}")
    if delivery_model(fam):
        bad += coverage_problems(db, fam)
    unacked = graveyard_recheck(db, fam)
    if unacked:
        bad.append(f"graveyard re-check: {', '.join(unacked)} not acknowledged in the family file")
    n = len(blocked(symbols(fam), SCREEN_SPLITS, now, delivery=delivery_model(fam)))
    if n:
        bad.append(f"{n} {EMBARGO_REASON}")
    return bad


def waiting(db, fid, reasons, actor, topic=None):
    """family.waiting, written once per change of reasons (the strategy pass runs every 30 s) and topic (registration
    when None, or the cohort). True if written."""
    reasons = list(reasons)
    for r in db.q("SELECT payload FROM events WHERE kind='family.waiting' ORDER BY id DESC"):
        p = json.loads(r["payload"])
        if p.get("family") == fid and p.get("topic") == topic:
            if p.get("reasons") == reasons:
                return False
            break
    db.event("family.waiting", actor if ":" in actor else f"system:{actor}", None,
             {"family": fid, "reasons": reasons, **({"topic": topic} if topic else {})})
    return True


def pass_(db, actor="strategy-1", now=None):
    """Strategy-1's family pass (point 19: only in a fleet a human started; no timers). An approved family whose base
    instances are not all DISCOVERED waits (family.waiting, the same reason register_batch writes: revival comes before
    approve-family); registration itself is pipeline.register_batch (the base batch, completed in a later pass if it
    stopped part-way, and triggered successors). A registered family goes through cohort_pass: the cohort, its alpha,
    the forward jobs and the family close. Errors are contained per family. Returns {family: status}."""
    out = {}
    for fid in family_ids():
        try:
            if registered(db, fid):
                out[fid] = cohort_pass(db, fid, actor, now)
                continue
            p, started = approval_payload(db, fid), registration_started(db, fid)
            why = ([PARTIAL_VOID] if started else []) if p is None else base_waiting(db, fid, p)
            if why:
                waiting(db, fid, why, actor)
                out[fid] = "waiting: " + why[0]
            elif p is None:
                out[fid] = "not approved"
            else:
                out[fid] = ("registering: the base batch stopped part-way; register_batch completes it" if started else
                            "approved: registers through register_batch when nothing blocks it")
        except Exception as e:
            out[fid] = f"error: {e!r}"[:200]
    return out


# ---------- phase A5: successor triggers (point 9) ----------
LITERALS = {"true": True, "false": False, "null": None}
_TOKEN = re.compile(r"\s*(?:(\d+\.\d*|\.\d+|\d+)|(==|!=|>=|<=|>|<|\+|-)|([A-Za-z_][A-Za-z0-9_.]*))")


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _value(art, path):
    """A dotted path in a frozen training artifact; in cost.json `selected` is the selected variant's row."""
    node = art
    for k, key in enumerate(path.split(".")):
        if k == 0 and key == "selected" and isinstance(art.get("variants"), list):
            node = next((v for v in art["variants"] if v.get("variant") == art.get("selected")), None)
        elif isinstance(node, dict):
            node = node.get(key)
        else:
            return None
    return node


def condition(cond, art):
    """One mechanical trigger condition `expr OP expr` on a frozen training artifact: expr = terms joined by + and -, a
    term a number, true/false/null or a dotted path, optionally negated; OP one of == != >= <= > <. A missing value makes
    the condition false. Parsed by hand (never eval); FamilyError if it cannot be parsed."""
    toks, i, c = [], 0, (cond or "").strip()
    while i < len(c):
        m = _TOKEN.match(c, i)
        if not m or not any(m.groups()):
            raise FamilyError(f"cannot parse trigger condition {cond!r}")
        num, op, name = m.groups()
        toks.append(("num", float(num)) if num else ("op", op) if op else ("name", name))
        i = m.end()
    pos = [0]

    def take():
        if pos[0] >= len(toks):
            raise FamilyError(f"incomplete trigger condition {cond!r}")
        pos[0] += 1
        return toks[pos[0] - 1]

    def term():
        kind, v = take()
        if (kind, v) == ("op", "-"):
            x = term()
            return -x if _num(x) else None
        if kind == "num":
            return v
        if kind == "name":
            return LITERALS[v] if v in LITERALS else _value(art, v)
        raise FamilyError(f"unexpected {v!r} in trigger condition {cond!r}")

    def expr():
        x = term()
        while pos[0] < len(toks) and toks[pos[0]] in (("op", "+"), ("op", "-")):
            op, y = take()[1], term()
            x = (x + y if op == "+" else x - y) if _num(x) and _num(y) else None
        return x
    left = expr()
    kind, op = take()
    if kind != "op" or op in "+-":
        raise FamilyError(f"trigger condition {cond!r} needs a comparison")
    right = expr()
    if pos[0] != len(toks):
        raise FamilyError(f"trailing input in trigger condition {cond!r}")
    if left is None or right is None:
        return False
    if op in ("==", "!="):
        same = isinstance(left, bool) == isinstance(right, bool) and left == right
        return same if op == "==" else not same
    if not (_num(left) and _num(right)):
        return False
    return {">": left > right, ">=": left >= right, "<": left < right, "<=": left <= right}[op]


def ever_registered(db, eid):
    return db.one("SELECT 1 FROM transitions WHERE exp_id=? AND to_state='REGISTERED' LIMIT 1", eid) is not None


def trigger_state(db, inst, parent):
    """Point 9: a successor triggers only from its parent's hash-verified training artifact (cost.json or
    adversarial.json); validation, forward, holdout or live numbers never trigger anything. Returns (state, why) with
    state 'pending' (the parent's step has not recorded the artifact yet), 'met' or 'not met' (a missing or altered
    artifact fails closed)."""
    from lab import pipeline
    t = inst.get("trigger") or {}
    name = t.get("artifact")
    if name not in TRIGGER_ARTIFACTS:
        return "not met", f"trigger artifact {name!r} is not a frozen training artifact"
    if pipeline.recorded_sha(db, parent, name) is None:
        return "pending", f"{parent}/{name}.json is not recorded yet"
    try:
        art = pipeline.frozen_artifact(db, parent, name)
        ok = all(condition(c, art) for c in t.get("all") or [])
    except (pipeline.ArtifactError, FamilyError) as e:
        return "not met", f"fails closed: {e}"
    return ("met" if ok else "not met"), f"{parent}/{name}.json: {' AND '.join(t.get('all') or [])}"


def triggered(db, fam, eids):
    """The DISCOVERED successors among `eids` whose registered parent's frozen artifact meets the trigger."""
    from lab.lifecycle import state
    fid, out = fam["family_id"], []
    for inst, parent in instances(fam):
        e = exp_id(fid, inst["id"])
        if parent and e in eids and state(db, e) == "DISCOVERED" and ever_registered(db, exp_id(fid, parent)) and \
                trigger_state(db, inst, exp_id(fid, parent))[0] == "met":
            out.append(e)
    return out


def successors_open(db, fam):
    """Successors that can still register (point 10: the cohort waits for them): named by the binding approval, DISCOVERED
    with a registered, unfinished parent whose trigger artifact is not recorded yet, or triggered and not refused by a
    registration rule."""
    from lab.lifecycle import FINAL, state
    fid, out = fam["family_id"], []
    p = binding_approval(db, fid)
    named = set((p or {}).get("successors") or [])
    for inst, parent in instances(fam):
        e, pe = exp_id(fid, inst["id"]), exp_id(fid, parent) if parent else None
        if not parent or e not in named or state(db, e) != "DISCOVERED" or not ever_registered(db, pe):
            continue
        st, _ = trigger_state(db, inst, pe)
        if (st == "pending" and state(db, pe) not in FINAL) or \
                (st == "met" and not registration_block(db, fam, successor=e)):
            out.append(e)
    return out


# ---------- phase A5: the cohort, its alpha and the family close (points 10, 13 and 15) ----------
COHORT_CAP = 3                                 # point 10: M <= 3
OBSERVE = "OBSERVE (family forward test)"     # the screen's verdict for a survivor (point 8)
FORWARD_FAIL = "FAIL (family forward test)"
FUTILITY = "FAIL (forward futility)"           # the interim look (point 12)
NOT_SELECTED = "REJECTED: not selected (family cohort cap 3)"
DATA_GATES = ("data quality", "validation data quality")


def _ts(day):
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def cohort(db, fid):
    """The family's cohort.fixed payload, or None. It is written once: M and alpha_i are never recomputed."""
    for r in db.q("SELECT payload FROM events WHERE kind='cohort.fixed' ORDER BY id"):
        p = json.loads(r["payload"])
        if p.get("family") == fid:
            return p
    return None


def cohort_of(db, eid):
    """The cohort.fixed payload that selected eid for the forward test, or None."""
    fid = (instance_of(eid) or (None,))[0]
    p = cohort(db, fid) if fid else None
    return p if p and eid in p.get("selected", []) else None


def closed(db, fid):
    return next((p for p in _closed(db) if p.get("family") == fid), None)


def registered_members(db, fid):
    return [e for e in members(db, fid) if ever_registered(db, e)]


def registered_approval(db, fid):
    """The family.approved payload a registration of the family cited (its alpha_F is the one the cohort spends)."""
    for r in db.q("SELECT exp_id, evidence FROM transitions WHERE to_state='REGISTERED' ORDER BY id"):
        if (instance_of(r["exp_id"]) or (None,))[0] == fid:
            aid = json.loads(r["evidence"] or "{}").get("family_approval_event")
            ev = db.one("SELECT payload FROM events WHERE id=? AND kind='family.approved'", aid)
            if ev:
                return {**json.loads(ev["payload"]), "event_id": aid}
    return None


def pin_problems(spec, approved):
    """Point 18 (design test 26), before every step of a registered instance: the spec's code_blobs of the four bound
    files are the blobs of the family approval its registration cited (`approved`, see cited_approval), every engine
    file has a recorded blob, and the working family file and module are still the registered blobs. Otherwise every
    later step fails closed (also in 2027); nothing is regenerated, and a correction needs a dated amendment. Point 18
    pins the family file and the module after registration; the engine blobs are recorded, not pinned."""
    from lab import pipeline
    want = spec.get("code_blobs") or {}
    if not approved or approved.get("family") != spec.get("family"):
        return ["the registration cites no approval of this family (amendment 8 point 18: fails closed)"]
    bad = [f"spec code_blobs.{k} is not the blob the family approval bound (amendment 8 point 18: fails closed)"
           for k in BOUND if not want.get(k) or want[k] != (approved.get("blobs") or {}).get(k)]
    bad += [f"spec code_blobs has no recorded blob of {f} (amendment 8 point 18: fails closed)"
            for f in pipeline.ENGINE_CODE if not want.get(f)]
    b = blobs(spec["family"])
    return bad + [f"{b[k]['path']} is not the blob registered in the spec (amendment 8 point 18: fails closed)"
                  for k in ("family", "module") if not want.get(k) or b[k]["working"] != want[k]]


def family_pin(db, fid):
    """pin_problems over every registered member of the family (each against the approval its registration cited, and
    on its registered version 2)."""
    from lab import registry
    out = []
    for e in registered_members(db, fid):
        v = registry.latest(db, e)
        for b in ([] if v["version"] == 2 else [f"{e}: spec version {v['version']} is not the registered version 2 "
                                                f"(amendment 8 points 7 and 18: fails closed)"]) + \
                pin_problems(json.loads(v["spec_json"] or "{}"), cited_approval(db, e)):
            if b not in out:
                out.append(b)
    return out


def _result(db, eid, label=None):
    q = "SELECT id, label, verdict, metrics FROM results WHERE exp_id=?" + (" AND label=?" if label else "")
    return db.one(q + " ORDER BY id DESC LIMIT 1", *((eid, label) if label else (eid,)))


def settled(db, eid):
    """A registered member is settled for the cohort once its screen took its edge: OBSERVATION (a survivor) or a final
    state. A result recorded without its edge (a crash between the two, a pass in between) is not settled yet: the
    report job's retry takes the edge first, so the cohort never fixes without a survivor (point 10)."""
    from lab.lifecycle import FINAL, state
    return state(db, eid) in FINAL | {"OBSERVATION"}


def untestable(db, eid):
    """Point 15: a member whose screen failed for too few symbols or too little data."""
    from lab import pipeline
    r = _result(db, eid)
    failed = (json.loads(r["metrics"] or "{}").get("failed") or []) if r else []
    if any(g in DATA_GATES for g in failed):
        return True
    try:
        return pipeline.frozen_artifact(db, eid, "data").get("ok") is False
    except pipeline.ArtifactError:
        return False


def forward_outcome(db, eid):
    """'PASS' or 'FAIL' once the forward test (or its interim look) decided eid, else None. Only a forward result of its
    cohort counts (forward_result), never a row typed or forged past the step."""
    from lab.lifecycle import FINAL, state
    got = forward_results(db, eid)
    if "PASS" in got:                                                 # a later holdout result never changes it
        return "PASS"
    if "FAIL" in got or state(db, eid) in FINAL:
        return "FAIL"
    return None


FORWARD_ARTIFACT = {FORWARD_PASS: "observe", FORWARD_FAIL: "observe", FUTILITY: "observe_interim"}


def _obj(text):
    """A results row's metrics or evidence as a dict ({} for anything else)."""
    try:
        v = json.loads(text or "{}")
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def recorded_by(db, eid, rid):
    """The actor of the result.recorded event of result rid of eid, or None."""
    for r in db.q("SELECT actor, payload FROM events WHERE kind='result.recorded' AND exp_id=? ORDER BY id DESC", eid):
        if json.loads(r["payload"] or "{}").get("result_id") == rid:
            return r["actor"]
    return None


def cites(eid, evidence, name):
    """True if `evidence` cites artifacts/<eid>/<name>.json (its recorded path) with the SHA-256 the file has now."""
    import hashlib
    from lab import pipeline
    path = os.path.join(pipeline.ARTIFACTS, eid, f"{name}.json")
    try:
        rel = os.path.relpath(path, HERE).replace("\\", "/")
        with open(path, "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
    except (OSError, ValueError):
        return False
    arts = evidence.get("artifacts")
    return isinstance(arts, list) and any(isinstance(a, dict) and a.get("path") == rel and a.get("sha256") == sha
                                          for a in arts)


def forward_result(db, eid, r):
    """Points 11 and 12: 'PASS', 'FAIL' or None for result row r (id, verdict, metrics, evidence) of eid. A forward
    decision counts only if its step recorded it (a system actor; `lab result` refuses family instances), its metrics
    carry the id of the fixed cohort that selected eid, and it cites its hash-matching artifact: observe.json for the
    final test, observe_interim.json for the futility look (finding protocol-statistics #2)."""
    v = r["verdict"] or ""
    kind = next((k for k in (FORWARD_PASS, FORWARD_FAIL, FUTILITY) if v.startswith(k)), None)
    cf = cohort_of(db, eid) if kind else None
    if cf is None or not (recorded_by(db, eid, r["id"]) or "").startswith("system:") or \
            _obj(r["metrics"]).get("cohort") != cf.get("cohort") or \
            not cites(eid, _obj(r["evidence"]), FORWARD_ARTIFACT[kind]):
        return None
    return "PASS" if kind == FORWARD_PASS else "FAIL"


def forward_results(db, eid):
    """The forward decisions on eid that count (forward_result), as a set of 'PASS' / 'FAIL'."""
    return {forward_result(db, eid, r) for r in db.q("SELECT id, verdict, metrics, evidence FROM results WHERE "
                                                     "exp_id=? AND label='VALIDATION' ORDER BY id", eid)} - {None}


FAMILY_KINDS = ("data", "backtest", "cost", "adversarial", "validate", "report", "observe_interim", "observe")


def failed_jobs(db, eids):
    """Screening and forward jobs of these experiments that failed permanently (point 15: the family stops without
    closing its cohort). Non-decisional diagnostics do not count."""
    import sqlite3
    if not eids:
        return []
    try:
        return [r[0] for r in db.q(f"SELECT job_id FROM jobs WHERE status='failed' AND kind IN "
                                   f"({','.join('?' * len(FAMILY_KINDS))}) AND exp_id IN ({','.join('?' * len(eids))}) "
                                   f"ORDER BY job_id", *FAMILY_KINDS, *eids)]
    except sqlite3.OperationalError:              # no job table yet
        return []


def window_start(fam, now):
    """Point 10: 00:00 UTC on the 1st of the month after the close, never before 2026-12-01 (nor the family file's
    forward.earliest_start)."""
    from lab import pipeline
    return max(pipeline._next_month(now), _ts(EARLIEST_START), _ts(fam["forward"]["earliest_start"]))


def _val_sharpe(db, eid):
    r = _result(db, eid, "EXPLORATORY")
    s = ((json.loads(r["metrics"] or "{}").get("validation") or {}) if r else {}).get("net_sharpe_ann")
    return s if _num(s) else None


def fix_cohort(db, fid, fam, regs, actor, now):
    """Point 10 and 13, written once in one transaction: cohort.fixed with id, members, M <= 3 (the survivors with the
    highest validation net Sharpe), alpha_F, alpha_i = alpha_F / M and the windows fwdYYYYMMm12 / fwdYYYYMMm06, starting
    00:00 UTC on the 1st of the month after the close and never before 2026-12-01. M >= 1 spends alpha_F (moved from
    family:<fid> to the M instances, alpha_i each) and releases whatever the family holds above alpha_F (a second
    reservation from before the point 13 fix: alpha_excess_released); M = 0 releases it and closes the family
    FUTILE_IN_SAMPLE (UNTESTABLE when every member failed for data). Returns the payload, or None when the reservation
    is missing (fails closed)."""
    from lab.engine import data
    from lab.lifecycle import state
    ap = registered_approval(db, fid)
    if ap is None or reserved(db, fid) < ap["alpha_family"] - 1e-12:
        waiting(db, fid, ["the cohort cannot be fixed: the registration cites no family approval with a reserved "
                          "alpha_F (fails closed)"], actor, topic="cohort")
        return None
    alpha_f = ap["alpha_family"]
    surv = [e for e in regs if state(db, e) == "OBSERVATION" and
            ((_result(db, e) or {"verdict": ""})["verdict"] or "").startswith(OBSERVE)]
    ranking = {e: _val_sharpe(db, e) for e in surv}
    ranked = sorted(surv, key=lambda e: (-(ranking[e] if ranking[e] is not None else -math.inf), e))
    sel, cut = ranked[:COHORT_CAP], ranked[COHORT_CAP:]
    m = len(sel)
    p = {"family": fid, "members": sorted(regs), "survivors": sorted(surv), "selected": sel, "not_selected": cut,
         "validation_net_sharpe": ranking, "M": m, "alpha_F": alpha_f, "alpha_i": alpha_f / m if m else None,
         "approval_event": ap["event_id"], "closed_at": int(now),
         "rule": "amendment 8 points 10 and 13: M <= 3 by validation net Sharpe; alpha_i = alpha_F / M, never "
                 "recomputed"}
    if m:
        start = window_start(fam, now)
        w12 = data.forward_split(start, FORWARD_MONTHS, tagged=True)
        w6 = data.forward_split(start, INTERIM_MONTHS, tagged=True)
        a, b = data.window_bounds(w12)                   # inclusive ends; a window ends at b + 1 (00:00 UTC)
        b6 = data.window_bounds(w6)[1]
        p.update(cohort=f"{fid}:{w12}", window=w12, sub_window=w6, start=a, end=b, sub_end=b6,
                 interim_not_before=b6 + 1 + data.FORWARD_LAG_S, final_not_before=b + 1 + data.FORWARD_LAG_S)
    else:
        outcome = "UNTESTABLE" if regs and all(untestable(db, e) for e in regs) else "FUTILE_IN_SAMPLE"
        p.update(cohort=f"{fid}:M0", window=None, sub_window=None, outcome=outcome)
    sys_actor = actor if ":" in actor else f"system:{actor}"
    with db.tx():
        excess = reserved(db, fid) - alpha_f if m else 0.0
        if excess > 1e-12:                   # safety net: a second reservation (before the point 13 fix) is released
            p["alpha_excess_released"] = excess
        db.event("cohort.fixed", sys_actor, None, p)
        if m:
            db.append("alpha_ledger", exp_id=f"family:{fid}", ts=int(now), alpha=-alpha_f, note=SPEND_NOTE)
            for e in sel:
                db.append("alpha_ledger", exp_id=e, ts=int(now), alpha=alpha_f / m, note=SPEND_NOTE)
                db.event("observation.started", sys_actor, e, {"window": p["window"], "start": p["start"],
                                                               "end": p["end"], "cohort": p["cohort"],
                                                               "sub_window": p["sub_window"], "family": fid})
            if excess > 1e-12:
                db.append("alpha_ledger", exp_id=f"family:{fid}", ts=int(now), alpha=-excess, note=RELEASE_NOTE)
        else:
            released = reserved(db, fid)
            db.append("alpha_ledger", exp_id=f"family:{fid}", ts=int(now), alpha=-released, note=RELEASE_NOTE)
            db.event("family.closed", sys_actor, None, {"family": fid, "outcome": p["outcome"], "cohort": p["cohort"],
                                                        "alpha_released": released})
    return p


def settle(db, fid, cf, actor):
    """What a fixed cohort still has to do, idempotent (a pass completes what an interrupted one left): capped-out
    members REJECTED 'not selected', every DISCOVERED member (an untriggered successor) SUPPRESSED, one interim job per
    selected member (not_before = sub-window end + 7 days), and the family close (PASS if any member passed its forward
    test, else FAIL) once every selected member is decided. Writes only after the code pin holds."""
    from lab import jobs, lifecycle, registry
    from lab.lifecycle import state
    sys_actor = actor if ":" in actor else f"system:{actor}"
    cut = [e for e in cf["not_selected"] if state(db, e) == "OBSERVATION"]
    sup = [e for e in members(db, fid) if state(db, e) == "DISCOVERED"]
    queue = [e for e in cf["selected"] if not db.one("SELECT 1 FROM jobs WHERE job_id=?", f"observe_interim|{e}")]
    done = {e: forward_outcome(db, e) for e in cf["selected"]}
    close = bool(cf["M"]) and all(done.values()) and closed(db, fid) is None
    if cut or sup or queue or close:
        bad = family_pin(db, fid)
        if bad:
            waiting(db, fid, bad, actor, topic="cohort")
            return "stopped: " + bad[0]
    for e in cut:
        r = _result(db, e)
        rid = r["id"] if r and (r["verdict"] or "").startswith(NOT_SELECTED) else registry.record_result(
            db, e, "EXPLORATORY", f"{NOT_SELECTED}: validation net Sharpe {cf['validation_net_sharpe'].get(e)} ranks "
                                  f"below the {COHORT_CAP} selected members of cohort {cf['cohort']}",
            {"cohort": cf["cohort"], "selected": cf["selected"], "validation_net_sharpe": cf["validation_net_sharpe"]},
            {"cohort_fixed": cf["cohort"]}, sys_actor)
        ev = {"result_id": rid}
        lifecycle.auto_transition(db, e, "REJECTED", sys_actor, NOT_SELECTED, ev,
                                  guards=(registry.make_result_guard(ev),))
    for e in sup:
        lifecycle.auto_transition(db, e, "SUPPRESSED", sys_actor,
                                  f"not registered when the family cohort {cf['cohort']} was fixed: a successor registers "
                                  f"only before (amendment 8 point 9)", {"cohort": cf["cohort"]})
    for e in queue:
        jobs.enqueue(db, f"observe_interim|{e}", "observe_interim", e,
                     {"start": cf["start"], "months": INTERIM_MONTHS, "cohort": cf["cohort"]}, priority=5,
                     max_attempts=3, timeout_s=1800, actor=sys_actor, not_before=cf["interim_not_before"])
    if close:
        out = "PASS" if "PASS" in done.values() else "FAIL"
        db.event("family.closed", sys_actor, None, {"family": fid, "outcome": out, "cohort": cf["cohort"],
                                                    "results": done})
    c = closed(db, fid)
    if c is not None:
        return f"closed: {c.get('outcome')}"
    if not cf["M"]:
        return f"cohort {cf['cohort']} fixed with M 0"
    return f"forward test: cohort {cf['cohort']}, M {cf['M']}, alpha_i {cf['alpha_i']:.5f}; " \
           f"{sum(1 for v in done.values() if v)} of {cf['M']} decided"


def cohort_pass(db, fid, actor="strategy-1", now=None):
    """Point 10 in strategy-1's pass: the cohort closes at the first pass where every registered member has a result
    and no successor can still trigger. A permanent job failure stops the family without closing its cohort (point 15);
    a changed family file or module fails closed (point 18). Running forward tests continue after a programme stop."""
    from lab.engine import data
    now = data.CLOCK() if now is None else now
    c, cf = closed(db, fid), cohort(db, fid)
    if c is None:
        dead = failed_jobs(db, registered_members(db, fid))
        if dead:
            waiting(db, fid, [f"job {j} failed permanently: the family stops without closing its cohort (amendment 8 "
                              f"point 15)" for j in dead], actor, topic="cohort")
            return f"stopped: {len(dead)} job(s) failed permanently"
    elif cf is None:
        return f"closed: {c.get('outcome')}"
    if cf is None:
        regs = registered_members(db, fid)
        pending = [e for e in regs if not settled(db, e)]
        if pending:
            return f"screening: {len(regs) - len(pending)} of {len(regs)} registered members have a result"
        fam = load(fid)
        still = successors_open(db, fam)
        if still:
            return f"waiting for successor(s) that can still register: {', '.join(still)}"
        bad = family_pin(db, fid)                         # the family file read above is the registered one
        if bad:
            waiting(db, fid, bad, actor, topic="cohort")
            return "stopped: " + bad[0]
        cf = fix_cohort(db, fid, fam, regs, actor, now)
        if cf is None:
            return "waiting: the cohort cannot be fixed (no reserved alpha_F)"
    return settle(db, fid, cf, actor)


# ---------- phase A5: the forward test (points 11 and 12; the steps are in lab/pipeline.py) ----------
def _first_delivery_file(s, split):
    from lab.engine import data
    plan = data.delivery_plan(s, split)
    return plan[0]["files"][0][1] if plan and plan[0]["files"] else None


def unlisted(symbols, split, delivery=False):
    """Point 11 (amendment 7 point 5): coins without a perp or spot file (and, for spot_delivery_ratio, the held
    quarterly's file) for the window's first month, excluded before any computation (read from the cache after the
    guarded download)."""
    from lab.engine import data
    out = []
    for s in symbols:
        e = data.expected_paths(s, split, spot=True)
        if not (os.path.exists(e["klines"][0][1]) and os.path.exists(e["spot"][0][1])) or \
                (delivery and not os.path.exists(_first_delivery_file(s, split) or "")):
            out.append(s)
    return out


COVERAGE_MIN = 0.99                            # data.quality's coverage rule


PUBLICATION_WAIT_MAX_S = 60 * 86400           # spot_delivery_ratio: a quarterly leg unpublished for 60 days is gone


def unpublished(symbols, split, delivery=False, now=None):
    """A forward window's last month that the archive has published for none of the coins (perp klines or spot klines,
    read after the guarded download): a publication delay, never a delisting of every coin (review of fdd898a). The
    reason to wait, or None."""
    from lab.engine import data
    if not split.startswith("fwd") or not symbols:
        return None
    late = delivery and (data.CLOCK() if now is None else now) > data.window_bounds(split)[1] + PUBLICATION_WAIT_MAX_S
    for kind in ("klines", "spot") + (("delivery",) if delivery and not late else ()):
        if not any(os.path.exists(data.expected_paths(s, split, spot=True, delivery=delivery)[kind][-1][1])
                   for s in symbols):
            y, m = data.months(split)[-1]
            return (f"the archive has not published {y}-{m:02d} {kind} files for any coin of {split} yet: the forward "
                    f"test waits a day and reads nothing before (amendment 8 point 11)")
    return None


def delisted(bars, split, delivery=False):
    """Point 11 cites amendment 7 point 5: a coin delisted in the window is excluded from the day after, not from the
    whole window (finding protocol-statistics #8, survivorship). {coin: last listed hour} for the coins whose instrument
    series stops before the window's last hour while the cache has no perp or no spot klines file for every later month
    (read after the guarded download: the archive had none). A gap followed by more data is no delisting; the quality
    rule keeps judging it over the whole window."""
    from lab.engine import data
    end, mon, out = data.window_bounds(split)[1] + 1 - data.HOUR, data.months(split), {}
    for s, x in bars.items():
        if not x or x[-1][0] >= end:
            continue
        d = datetime.fromtimestamp(x[-1][0], timezone.utc)
        e = data.expected_paths(s, split, spot=True)
        held = _delivery_months(s, split) if delivery else None
        if all(not (os.path.exists(e["klines"][k][1]) and os.path.exists(e["spot"][k][1]) and
                    (held is None or held.get(ym)))
               for k, ym in enumerate(mon) if ym > (d.year, d.month)):
            out[s] = x[-1][0]
    return out


def _delivery_months(s, split):
    """{(year, month): True if a file of a quarterly held in that month is in the cache}."""
    from lab.engine import data
    out = {}
    for c in data.delivery_plan(s, split):
        for u, p in c["files"]:
            y, m = (int(v) for v in p[-11:-4].split("-"))
            out[(y, m)] = out.get((y, m), False) or os.path.exists(p)
    return out


def listed_quality(bars, split, dups, last):
    """data.quality of a delisted coin over its listed hours only (window start to its last listed hour, same rule)."""
    from lab.engine import data
    q = data.quality(bars, split, dups)
    exp = (last - data.window_bounds(split)[0]) // data.HOUR + 1
    cov = len(bars) / exp if exp > 0 else 0.0
    return {**q, "expected": exp, "coverage": cov, "listed_until": last,
            "ok": cov >= COVERAGE_MIN and q["nonpositive_prices"] == 0 and q["monotonic"] and q["duplicates"] == 0}


def listed_only(bars, funding, fd, last):
    """Nothing of a delisted coin after its last listed hour: instrument bars, funding, and the benchmark's perp bars and
    settled funding (both legs leave the book together)."""
    for s, t in last.items():
        bars[s] = [x for x in bars[s] if x[0] <= t]
        funding[s] = {k: v for k, v in (funding.get(s) or {}).items() if k <= t}
        if isinstance(fd, FamilyData):
            fd.perp[s] = [x for x in fd.perp.get(s) or [] if x[0] <= t]
            fd.funding[s] = {k: v for k, v in (fd.funding.get(s) or {}).items() if k <= t}


def psr_cons(daily):
    """Point 11: PSR_cons = the smallest of the PSR with skew 0 and kurtosis 3 (as today), the PSR with the sample's skew
    and kurtosis, and the PSR with the effective n = n / max(1, 1 + 2 sum_{k=1..5} (1 - k/6) rho_k), never above n.
    Never more lenient than today's PSR. Returns (psr_cons or None, details)."""
    from lab.engine import backtest
    n = len(daily)
    if n < 3:
        return None, {"n": n}
    mu = math.fsum(daily) / n
    sd = statistics.stdev(daily)
    dev = [x - mu for x in daily]
    m2 = math.fsum(d * d for d in dev) / n
    if sd <= 0 or m2 <= 0:
        return None, {"n": n}
    sr = mu / sd
    skew, kurt = math.fsum(d ** 3 for d in dev) / n / m2 ** 1.5, math.fsum(d ** 4 for d in dev) / n / m2 ** 2
    rho = [math.fsum(dev[t] * dev[t - k] for t in range(k, n)) / (n * m2) for k in range(1, 6)]
    n_eff = min(n, n / max(1.0, 1 + 2 * math.fsum((1 - k / 6) * r for k, r in enumerate(rho, 1))))
    parts = {"iid": backtest.psr(sr, n), "sample_moments": backtest.psr(sr, n, skew=skew, kurt=kurt),
             "effective_n": backtest.psr(sr, n_eff)}
    vals = list(parts.values())
    return (None if None in vals else min(vals)), {**parts, "n": n, "n_eff": n_eff, "skew": skew, "kurtosis": kurt,
                                                   "rho_1_5": rho, "sr_daily": sr}


# ---------- gate edges of family instances (points 8, 11 and 12) ----------
def gate_problem(db, eid, cur, to, rid):
    """registry.make_result_guard for a family instance, so for its steps and `lab transition` alike: the cited result
    was recorded by a step (a system actor; `lab result` refuses family instances); never SCREENING -> SCREEN_PASSED
    (point 8); SCREENING -> OBSERVATION only on the screen's OBSERVE result; OBSERVATION -> SCREEN_PASSED / REJECTED
    only on a forward result of the cohort that selected it (forward_result: its cohort id and hash-matching
    observe.json, or observe_interim.json for the futility look) or, rejected, on the 'not selected' result of a member
    the fixed cohort capped out (point 10); VALIDATION -> VALIDATED / REJECTED only on the holdout step's 'PASS
    (holdout)' / 'FAIL (holdout)' result citing its hash-matching holdout.json (point 16: the sealed holdout is never
    skipped). Returns the refusal, or None (finding protocol-statistics #2; review of 4c32ff6, finding 2)."""
    if (cur, to) == ("SCREENING", "SCREEN_PASSED"):
        return (f"{eid}: a family instance never goes directly to SCREEN_PASSED; a screen survivor goes to OBSERVATION "
                f"and only its family forward test decides (amendment 8 point 8)")
    r = db.one("SELECT id, verdict, metrics, evidence FROM results WHERE id=? AND exp_id=?", rid, eid)
    if r is None or not (recorded_by(db, eid, r["id"]) or "").startswith("system:"):
        return (f"{eid}: a gate transition of a family instance cites a result recorded by its step (a system actor), "
                f"never one typed with lab result (amendment 8 points 8, 11 and 12)")
    v = r["verdict"] or ""
    if (cur, to) == ("SCREENING", "OBSERVATION") and not v.startswith(OBSERVE):
        return f"{eid}: entering OBSERVATION needs the screen's '{OBSERVE}' result (amendment 8 point 8)"
    if (cur, to) == ("SCREENING", "REJECTED") and (not v.startswith("REJECTED") or v.startswith(NOT_SELECTED)):
        return (f"{eid}: SCREENING -> REJECTED needs the screen's own 'REJECTED' result; a survivor goes to OBSERVATION "
                f"and only its forward test decides (amendment 8 points 8 and 11)")
    if cur == "VALIDATION" and to in ("VALIDATED", "REJECTED"):
        want = "PASS (holdout)" if to == "VALIDATED" else "FAIL (holdout)"
        if not v.startswith(want) or not cites(eid, _obj(r["evidence"]), "holdout"):
            return (f"{eid}: VALIDATION -> {to} needs the holdout step's '{want}' result citing its hash-matching "
                    f"holdout.json (amendment 8 point 16: the sealed holdout is never skipped)")
    if cur == "OBSERVATION" and to in ("SCREEN_PASSED", "REJECTED"):
        fid = (instance_of(eid) or (None,))[0]
        cf = cohort(db, fid) if fid else None
        cut = to == "REJECTED" and v.startswith(NOT_SELECTED) and cf is not None and \
            eid in (cf.get("not_selected") or []) and _obj(r["metrics"]).get("cohort") == cf.get("cohort")
        if not cut and forward_result(db, eid, r) != ("PASS" if to == "SCREEN_PASSED" else "FAIL"):
            return (f"{eid}: OBSERVATION -> {to} needs a forward result of the cohort that selected it, recorded by "
                    f"its step with the cohort id and citing its hash-matching observe.json (observe_interim.json for "
                    f"the futility look), or the 'not selected' result of the fixed cohort (amendment 8 points 10-12)")
    return None


# ---------- human transitions of family instances (point 6) ----------
REGISTER_ONLY_BATCH = ("family instances register only through register_batch with a valid family approval "
                       "(amendment 8 point 7)")
NO_PAPER = ("simulated trading of a family instance needs a live spot feed and a later amendment (amendment 8 point "
            "16)")
PAPER_EDGES = {("VALIDATED", "PAPER_TRADING"), ("PAUSED", "PAPER_TRADING")}
MEMBERSHIP_EDGES = {("SUPPRESSED", "DISCOVERED"), ("DISCOVERED", "WITHDRAWN"), ("REGISTERED", "WITHDRAWN")}
MEMBERSHIP_FIXED = ("the family is approved (or registering): no instance is revived or withdrawn by hand any more; "
                    "revivals come before approve-family, and revoke-family first if the approval must change "
                    "(amendment 8 points 5, 6 and 9)")


def terminal_guard(db, eid, cur, to):
    """Lifecycle guard of `lab approve` and `lab confirm`: a human transition of a family instance (above all its
    revival SUPPRESSED -> DISCOVERED, and the sealed 2024 holdout SCREEN_PASSED -> VALIDATION) is typed in an interactive
    terminal outside an assistant session. DISCOVERED -> REGISTERED is never a human step for a family instance (point
    7: register_batch), nor is paper trading (point 16: a live spot feed and a later amendment first). Without a clean
    holdout in the family file the instance stops at SCREEN_PASSED (point 16). Once the family is approved (and not
    revoked) or its registration started, no instance is revived or withdrawn by hand (points 5, 6 and 9: membership is
    fixed by the approval, never chosen after in-sample results are known)."""
    from lab import registry
    from lab.lifecycle import LifecycleError
    if is_instance(db, eid):
        if (cur, to) == ("DISCOVERED", "REGISTERED"):
            raise LifecycleError(f"{eid}: {REGISTER_ONLY_BATCH}")
        if (cur, to) in MEMBERSHIP_EDGES:
            fid = (instance_of(eid) or (None,))[0] or json.loads(registry.latest(db, eid)["spec_json"] or "{}").get(
                "family")
            if last_approval_kind(db, fid) == "family.approved" or registration_started(db, fid):
                raise LifecycleError(f"{eid}: {MEMBERSHIP_FIXED}")
        if (cur, to) in PAPER_EDGES:
            raise LifecycleError(f"{eid}: {NO_PAPER}")
        try:
            GUARD()
        except FamilyError as e:
            raise LifecycleError(str(e)) from None
        v = registry.latest(db, eid)
        if (cur, to) == ("SCREEN_PASSED", "VALIDATION") and not json.loads((v and v["spec_json"]) or "{}").get(
                "clean_holdout"):
            raise LifecycleError(f"{eid}: the family file declares no clean 2024 holdout, so the instance stops at "
                                 "SCREEN_PASSED (amendment 8 point 16)")


def no_web_guard(db, eid, cur, to):
    """The dashboard has no route for the human steps of a family instance (point 5: no dashboard endpoint)."""
    from lab.lifecycle import LifecycleError
    if is_instance(db, eid):
        if (cur, to) == ("DISCOVERED", "REGISTERED"):
            raise LifecycleError(f"{eid} is an amendment 8 family instance: {REGISTER_ONLY_BATCH}")
        if (cur, to) in PAPER_EDGES:
            raise LifecycleError(f"{eid} is an amendment 8 family instance: {NO_PAPER}")
        raise LifecycleError(f"{eid} is an amendment 8 family instance: its human steps are typed in a terminal "
                             "(python3 -m lab approve / confirm)")
