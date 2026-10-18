"""Pre-registered hypothesis families (research/PROTOCOL_V3.md amendment 8).

A family is a committed JSON file research/families/<fid>.json (schema lab.family/1) plus one mechanism module
lab/families/<fid>.py. Only non-price-prediction mechanisms with positions hedged in the same asset are allowed; the
mechanism tag comes from the controlled vocabulary research/families/VOCABULARY.json. This module is the shared layer
over the existing catalogue, approvals, register_batch, job chain and forward test: it never edits
lab/engine/catalogue.py and never injects anything into catalogue.TEMPLATES.

Phase A1 (this file so far): loading, the schema and vocabulary rules, the power rule, cache status and the graveyard
check behind the read-only `python3 -m lab family-check`. Nothing here reads market data or uses the network.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics

from lab.db import HERE

FAMILY_DIR = os.path.join(HERE, "research", "families")
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
VOCABULARY = os.path.join(FAMILY_DIR, "VOCABULARY.json")
SCHEMA = "lab.family/1"

K_MAX = 3                      # base instances per family (amendment 8 point 3)
GRID = 2                       # variants per instance
LOOKBACK_MAX_DAYS = 14
FORWARD_MONTHS, INTERIM_MONTHS, EARLIEST_START = 12, 6, "2026-12-01"
W0, ALPHA_F_MAX = 0.05, 0.0125             # programme wealth and the per-family reservation (point 13)
POWER_SHARPE, POWER_MIN = 3.0, 0.5         # point 14: power >= 0.5 at true Sharpe 3.0 with alpha_F / K_MAX
DECISION_TIME = "01:00"
ALLOWED_CLASSES = ("carry", "structural", "subsidy", "flow", "liquidity_provision")
INSTRUMENT_MODELS = ("spot_perp_ratio", "spot_delivery_ratio")
CASH_FLOWS = ("funding_income", "locked_basis", "reward")
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
    if not isinstance(alpha_f, (int, float)) or not 0 < alpha_f <= ALPHA_F_MAX:
        bad.append(f"alpha.family must be in (0, {ALPHA_F_MAX}]")
    costs = fam.get("costs") or {}
    for k in ("taker_fee", "half_spread", "slippage"):
        if not isinstance(costs.get(k), (int, float)) or costs[k] < catalogue.COSTS[k]:
            bad.append(f"costs.{k} must be >= the catalogue's {catalogue.COSTS[k]}")
    if (fam.get("universe") or {}).get("base") not in UNIVERSES:
        bad.append(f"universe.base must be one of {sorted(UNIVERSES)}")
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
    return bad


# ---------- what the database and the disk say (read-only) ----------
def graveyard_hits(db, fam, vocab=None):
    """REJECTED/WITHDRAWN experiments with the family's tag or a related tag, and which of them lack an
    acknowledgement (amendment 8 point 6)."""
    from lab.lifecycle import state
    tags = (vocab or vocabulary())["tags"]
    tag = (fam.get("mechanism") or {}).get("tag")
    wanted = {tag} | set(tags.get(tag, {}).get("related", []))
    hits = sorted({r["exp_id"] for r in db.q("SELECT DISTINCT exp_id, mechanism_tag FROM experiments")
                   if r["mechanism_tag"] in wanted and state(db, r["exp_id"]) in ("REJECTED", "WITHDRAWN")})
    acked = {a.get("exp_id") for a in fam.get("graveyard_acknowledged") or []}
    return hits, [h for h in hits if h not in acked]


def expected_files(fam, splits=("train3", "validation3")):
    """{cache_dir: [paths]} the screening will read (no network; spot zips in their own directory)."""
    from lab.engine import data
    syms = getattr(data, UNIVERSES.get((fam.get("universe") or {}).get("base"), "UNIVERSE"))
    out = {}
    for d in fam.get("data") or []:
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
    """Amendment 8 wealth already reserved or spent (alpha_ledger rows of family:<fid>)."""
    return db.one("SELECT COALESCE(SUM(alpha), 0) FROM alpha_ledger WHERE exp_id LIKE 'family:%'")[0]


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
