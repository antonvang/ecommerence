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

import json
import math
import os
import re
import statistics
import threading
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
    """Amendment 8 wealth already reserved or spent: the rows of family:<fid> plus the alpha_i rows of the instances a
    cohort spent it on (a spend moves alpha_F from family:<fid> to its M instances, so the sum is unchanged)."""
    return db.one("SELECT COALESCE(SUM(alpha), 0) FROM alpha_ledger WHERE exp_id LIKE 'family:%' OR note=?",
                  SPEND_NOTE)[0]


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
        raise FamilyError("refused: an assistant session may not approve or confirm a family (amendment 8 point 5)")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise FamilyError("refused: family approvals and confirmations for family instances must be typed in an "
                          "interactive terminal")


GUARD = interactive_human


def bound_blobs(fid):
    """The committed blobs an approval binds. Every bound file must exist and be committed exactly as it is."""
    b = blobs(fid)
    dirty = [v["path"] for v in b.values() if not v["clean"]]
    if dirty:
        raise FamilyError(f"commit these files exactly as they are first: {', '.join(dirty)}")
    return {k: v["committed"] for k, v in b.items()}


def registered(db, fid):
    """True once an instance of the family was registered. Discovered or suppressed candidates do not count: discovery
    and revival come before approve-family (point 6)."""
    prefix = f"E_{fid}__"
    return db.one("SELECT 1 FROM transitions WHERE to_state='REGISTERED' AND substr(exp_id, 1, ?) = ? LIMIT 1",
                  len(prefix), prefix) is not None


def _blocking_problems(db, fam):
    fid = fam.get("family_id")
    bad = validate(fam)
    if not os.path.exists(module_path(fid)):
        bad.append(f"mechanism module lab/families/{fid}.py is missing")
    _, unacked = graveyard_hits(db, fam)
    bad += [f"graveyard: {e} is not acknowledged" for e in unacked]
    alpha_f = (fam.get("alpha") or {}).get("family") or 0
    if alpha_reserved(db) + alpha_f > W0 + 1e-12:
        bad.append(f"alpha budget: {alpha_reserved(db):.4f} of {W0} reserved; this family needs {alpha_f}")
    bad += programme_stop(db)                              # point 15: no new approvals once the programme stopped
    if registered(db, fid):
        bad.append(f"{fid} is already registered: approvals and revocations are only possible before registration")
    return bad


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
                            "instances": [i["id"] for i in fam["instances"]]})
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
    with db.tx():
        eid = db.event("family.approved", actor, None, {"family": fid, "blobs": b, "thresholds": ev["thresholds"],
                                                        "alpha_family": ev["alpha_family"],
                                                        "instances": ev["instances"], "approval_id": a["id"],
                                                        "reason": a["reason"]})
        db.event("approval.used", actor, None, {"approval_id": a["id"]})
        db.append("alpha_ledger", exp_id=f"family:{fid}", ts=now, alpha=ev["alpha_family"], note="A8 reserve")
    return fid, eid


def revoke(db, fid, actor, reason, now=None):
    """Only a human, only before registration. A reserved alpha is released (a negative A8 release row)."""
    import time
    if not actor.startswith("human:"):
        raise FamilyError("only a human can revoke a family")
    if not reason or len(reason.strip()) < 10:
        raise FamilyError("a reason of at least 10 characters is required")
    if registered(db, fid):
        raise FamilyError(f"{fid} is already registered: it can no longer be revoked")
    reserved = db.one("SELECT COALESCE(SUM(alpha), 0) FROM alpha_ledger WHERE exp_id=?", f"family:{fid}")[0]
    with db.tx():
        db.event("family.revoked", actor, None, {"family": fid, "reason": reason.strip()})
        if reserved > 0:
            db.append("alpha_ledger", exp_id=f"family:{fid}", ts=int(now or time.time()), alpha=-reserved,
                      note="A8 release")
    return reserved


def approval(db, fid):
    """The id of the valid family.approved event, or None (never approved, revoked, or a bound file or gate value
    changed). A change to lab/engine/catalogue.py does not void a family approval."""
    p = approval_payload(db, fid)
    return p["event_id"] if p else None


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
KIND_SOURCE = {"klines": "binance_um_klines_1h", "funding": "binance_um_fundingRate", "spot": SPOT}
DATA_HOST = "https://data.binance.vision/"
INSTANCE_RE = re.compile(r"E_([a-z0-9]{3,12})__([a-z0-9_]{2,12})_a8")
FORWARD_PASS = "PASS (family forward test)"    # verdict prefix of a family forward PASS (point 11)
EMBARGO_REASON = ("screening files are missing and may not be downloaded before 2026-11-28 00:00 UTC (amendment 8 "
                  "point 17, amendment 9 point 1)")
_DOWNLOADS = threading.BoundedSemaphore(2)    # amendment 9 point 1: at most 2 downloads at a time
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
    """Every experiment id of the family, in any state."""
    prefix = f"E_{fid}__"
    return [r[0] for r in db.q("SELECT DISTINCT exp_id FROM experiments WHERE substr(exp_id, 1, ?) = ?",
                               len(prefix), prefix)]


def instrument(fam):
    return f"binance_{(fam.get('instrument_model') or {}).get('type')}_{(fam.get('universe') or {}).get('base')}"


def symbols(fam_or_spec):
    """The universe: frozen in a registered spec, else the family file's base universe."""
    if fam_or_spec.get("universe_base"):
        return tuple(fam_or_spec["universe"])
    from lab.engine import data
    return getattr(data, UNIVERSES.get((fam_or_spec.get("universe") or {}).get("base"), "UNIVERSE"))


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
                    inst["horizon"], inst["execution"], rel, actor, exclude=own,
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
    if model != "spot_perp_ratio":
        raise FamilyError(f"instrument model {model!r} is not implemented (spot_delivery_ratio is phase B)")
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


def attribution(spec, m):
    """Mechanism attribution (point 8, stricter): the family module's rule on portfolio metrics; for fcarry funding
    income minus all costs > 0 and gross ratio P&L <= funding income. Returns {..., 'gates': {name: ok}}."""
    import importlib
    return importlib.import_module(f"lab.families.{spec['family']}").attribution(m)


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
    return db.one("SELECT COALESCE(SUM(alpha), 0) FROM alpha_ledger WHERE exp_id=?", f"family:{fid}")[0]


def register_transition(db, eid, fid, actor):
    """DISCOVERED -> REGISTERED for an instance of an approved family (mirrors templates.register_transition; the only
    automatic registration path for families): a valid family approval, its reserved alpha and a complete version 2
    spec bound to the approved family file and module."""
    import time
    from lab import lifecycle, registry
    if lifecycle.state(db, eid) != "DISCOVERED":
        raise lifecycle.LifecycleError(f"{eid} is not DISCOVERED")
    p = approval_payload(db, fid)
    if p is None:
        raise lifecycle.LifecycleError(f"family {fid} has no valid human approval")
    if reserved(db, fid) < p["alpha_family"] - 1e-12:
        raise lifecycle.LifecycleError(f"family {fid} has no reserved alpha")
    v = registry.latest(db, eid)
    spec = json.loads(v["spec_json"] or "{}")
    if spec.get("family") != fid or v["version"] < 2 or any(not spec.get(k) for k in registry.REQUIRED_SPEC) or \
            not spec.get("seed") or v["code_hash"] != p["blobs"]["family"] or \
            (spec.get("code_blobs") or {}).get("module") != p["blobs"]["module"] or \
            (spec.get("parent") or spec.get("instance")) not in p.get("instances", []):
        raise lifecycle.LifecycleError("registration requires a complete family spec version bound to the approved "
                                       "files and instances")
    with db.tx():
        db.append("transitions", exp_id=eid, ts=int(time.time()), from_state="DISCOVERED", to_state="REGISTERED",
                  actor=actor, reason=f"instance of approved family {fid} (amendment 8)",
                  evidence={"family_approval_event": p["event_id"]})
        db.event("lifecycle.transition", actor, eid, {"from": "DISCOVERED", "to": "REGISTERED",
                                                     "reason": f"approved family {fid}"})


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
    with _ABSENT_LOCK:
        urls = absent() | {url}
        path = _absent_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".part", "w", encoding="utf-8") as f:
            json.dump(sorted(urls), f)
        os.replace(path + ".part", path)


def _urlopen(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"}),
                                  timeout=120).read()


def guarded_get(split, fetch=None):
    """The `get` given to data._fetch for every family file. Before each request: a remembered 404 is answered without
    the network, only data.binance.vision is used, and the embargo is checked (Embargoed otherwise). At most 2
    downloads run at a time (amendment 9). `fetch(url)` is the network read (tests inject it)."""
    def get(url):
        if url in absent():
            raise urllib.error.HTTPError(url, 404, "not in the archive (remembered 404)", None, None)
        src = source_of(url)
        if src is None:
            raise Embargoed(f"family data comes only from {DATA_HOST} klines and funding files: {url}")
        if not fetch_allowed(src, split):
            raise Embargoed(embargo_reason(split))
        with _DOWNLOADS:
            try:
                return (fetch or _urlopen)(url)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    _mark_absent(url)
                raise
    get.guarded = True
    return get


def expected_paths(syms, splits, spot=True):
    """[(source, split, url, cache path)] of every file the screening reads for these symbols (no network)."""
    from lab.engine import data
    return [(KIND_SOURCE[kind], sp, u, p) for sp in splits for s in syms
            for kind, pairs in data.expected_paths(s, sp, spot).items() for u, p in pairs]


def missing(syms, splits, spot=True):
    """Files not in the cache and not known to be absent from the archive."""
    gone = absent()
    return [x for x in expected_paths(syms, splits, spot) if x[2] not in gone and not os.path.exists(x[3])]


def blocked(syms, splits, now=None):
    """Missing files that may not be downloaded now (empty = the step can read or fetch everything)."""
    return [x for x in missing(syms, splits) if not fetch_allowed(x[0], x[1], now)]


def ready(syms, splits, now=None):
    return not blocked(syms, splits, now)


# ---------- registration rules (point 7) ----------
def forward_passes(db):
    """Family instances with a forward PASS (point 15)."""
    passes = {r["exp_id"] for r in db.q("SELECT exp_id, verdict FROM results WHERE label='VALIDATION'")
              if instance_of(r["exp_id"]) and (r["verdict"] or "").startswith(FORWARD_PASS)}
    return passes | {f"family:{p.get('family')}" for p in _closed(db) if p.get("outcome") == "PASS"}


def _closed(db):
    """family.closed payloads in order: {family, outcome in PASS, FAIL, FUTILE_IN_SAMPLE, UNTESTABLE}."""
    return [json.loads(r["payload"]) for r in db.q("SELECT payload FROM events WHERE kind='family.closed' ORDER BY id")]


def programme_stop(db, now=None):
    """Point 15 (b) and (c): 3 families in a row closed without a forward PASS, or no forward PASS by 2028-06-30. Only a
    new dated amendment restarts the programme. (a), wealth below alpha_F, is the budget rule of an approval."""
    from lab.engine import data
    now = data.CLOCK() if now is None else now
    last, bad = _closed(db)[-3:], []
    if len(last) == 3 and all(p.get("outcome") != "PASS" for p in last):
        bad.append("programme stopped: 3 families in a row closed without a forward PASS (amendment 8 point 15 b)")
    if now >= PROGRAMME_END and not forward_passes(db):
        bad.append("programme stopped: no forward PASS by 2028-06-30 (amendment 8 point 15 c)")
    return bad


def open_families(db):
    """Families with a registered instance and no family.closed event."""
    reg ={instance_of(r[0])[0] for r in db.q("SELECT DISTINCT exp_id FROM transitions WHERE to_state='REGISTERED'")
           if instance_of(r[0])}
    return reg - {p.get("family") for p in _closed(db)}


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
    programme stop, at most 3 open families, no open experiment outside the family on the same tag and execution (a
    DISCOVERED candidate covers nothing yet), the graveyard re-check, and no screening file that is missing and may not
    be downloaded now. A successor (point 9) registers as an extra batch of its open family: after the base batch,
    before the cohort is fixed, and only when its parent's frozen training artifact meets the trigger."""
    from lab import lifecycle, registry
    fid = fam["family_id"]
    p = approval_payload(db, fid)
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
    own, tag, cover = set(members(db, fid)), fam["mechanism"]["tag"], set()
    for inst, _ in instances(fam):
        fp = registry.fingerprint(tag, instrument(fam), inst["horizon"], inst["execution"])
        cover |= {e for e in registry.covering(db, tag, inst["execution"], fp, exclude=own)
                  if lifecycle.state(db, e) != "DISCOVERED"}
    if cover:
        bad.append(f"open experiment(s) outside the family cover the same tag and execution: {', '.join(sorted(cover))}")
    unacked = graveyard_recheck(db, fam)
    if unacked:
        bad.append(f"graveyard re-check: {', '.join(unacked)} not acknowledged in the family file")
    n = len(blocked(symbols(fam), SCREEN_SPLITS, now))
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
    instances are not DISCOVERED waits (family.waiting); registration itself is pipeline.register_batch (base batch and
    triggered successors). A registered family goes through cohort_pass: the cohort, its alpha, the forward jobs and the
    family close. Errors are contained per family. Returns {family: status}."""
    from lab.lifecycle import state
    out = {}
    for fid in family_ids():
        try:
            if registered(db, fid):
                out[fid] = cohort_pass(db, fid, actor, now)
            elif approval(db, fid) is None:
                out[fid] = "not approved"
            elif any(state(db, exp_id(fid, i["id"])) == "DISCOVERED" for i in load(fid)["instances"]):
                out[fid] = "approved: registers through register_batch when nothing blocks it"
            else:
                why = ["no base instance is DISCOVERED: the discovery agent proposes them, and a SUPPRESSED instance "
                       "is revived only by a human in a terminal (python3 -m lab approve / confirm)"]
                waiting(db, fid, why, actor)
                out[fid] = "waiting: " + why[0]
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
    """Successors that can still register (point 10: the cohort waits for them): DISCOVERED with a registered, unfinished
    parent whose trigger artifact is not recorded yet, or triggered and not refused by a registration rule."""
    from lab.lifecycle import FINAL, state
    fid, out = fam["family_id"], []
    for inst, parent in instances(fam):
        e, pe = exp_id(fid, inst["id"]), exp_id(fid, parent) if parent else None
        if not parent or state(db, e) != "DISCOVERED" or not ever_registered(db, pe):
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


def pin_problems(spec):
    """Point 18: the family file and the module must still be the blobs written into the registered spec; otherwise
    every later step fails closed (also in 2027). A correction needs a dated amendment."""
    want, b = spec.get("code_blobs") or {}, blobs(spec["family"])
    return [f"{b[k]['path']} is not the blob registered in the spec (amendment 8 point 18: fails closed)"
            for k in ("family", "module") if not want.get(k) or b[k]["working"] != want[k]]


def family_pin(db, fid):
    from lab import registry
    regs = registered_members(db, fid)
    return pin_problems(json.loads(registry.latest(db, regs[0])["spec_json"])) if regs else []


def _result(db, eid, label=None):
    q = "SELECT id, label, verdict, metrics FROM results WHERE exp_id=?" + (" AND label=?" if label else "")
    return db.one(q + " ORDER BY id DESC LIMIT 1", *((eid, label) if label else (eid,)))


def settled(db, eid):
    """A registered member is settled for the cohort once its screen recorded a result (or it left the family)."""
    from lab.lifecycle import FINAL, state
    return _result(db, eid) is not None or state(db, eid) in FINAL


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
    """'PASS' or 'FAIL' once the forward test (or its interim look) decided eid, else None."""
    from lab.lifecycle import FINAL, state
    vs = [r[0] or "" for r in db.q("SELECT verdict FROM results WHERE exp_id=? AND label='VALIDATION'", eid)]
    if any(v.startswith(FORWARD_PASS) for v in vs):                  # a later holdout result never changes it
        return "PASS"
    if any(v.startswith((FORWARD_FAIL, FUTILITY)) for v in vs) or state(db, eid) in FINAL:
        return "FAIL"
    return None


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
    family:<fid> to the M instances, alpha_i each); M = 0 releases it and closes the family FUTILE_IN_SAMPLE (UNTESTABLE
    when every member failed for data). Returns the payload, or None when the reservation is missing (fails closed)."""
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
        db.event("cohort.fixed", sys_actor, None, p)
        if m:
            db.append("alpha_ledger", exp_id=f"family:{fid}", ts=int(now), alpha=-alpha_f, note=SPEND_NOTE)
            for e in sel:
                db.append("alpha_ledger", exp_id=e, ts=int(now), alpha=alpha_f / m, note=SPEND_NOTE)
                db.event("observation.started", sys_actor, e, {"window": p["window"], "start": p["start"],
                                                               "end": p["end"], "cohort": p["cohort"],
                                                               "sub_window": p["sub_window"], "family": fid})
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
def unlisted(symbols, split):
    """Point 11 (amendment 7 point 5): coins without a perp or spot file for the window's first month, excluded before
    any computation (read from the cache after the guarded download)."""
    from lab.engine import data
    out = []
    for s in symbols:
        e = data.expected_paths(s, split, spot=True)
        if not (os.path.exists(e["klines"][0][1]) and os.path.exists(e["spot"][0][1])):
            out.append(s)
    return out


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


# ---------- human transitions of family instances (point 6) ----------
def terminal_guard(db, eid, cur, to):
    """Lifecycle guard of `lab confirm`: a human transition of a family instance (above all its revival SUPPRESSED ->
    DISCOVERED, and the sealed 2024 holdout SCREEN_PASSED -> VALIDATION) is typed in an interactive terminal outside an
    assistant session. Without a clean holdout in the family file the instance stops at SCREEN_PASSED (point 16)."""
    from lab import registry
    from lab.lifecycle import LifecycleError
    if is_instance(db, eid):
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
        raise LifecycleError(f"{eid} is an amendment 8 family instance: its human steps are typed in a terminal "
                             "(python3 -m lab approve / confirm)")
