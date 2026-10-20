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


class Deferred(StepError):
    """The step may not run yet (amendment 9: family files under the download embargo). The fleet puts the job back
    until `until` without using an attempt (jobs.defer); it is never a failure."""

    def __init__(self, reason, until):
        super().__init__(reason, until)
        self.until = until

    def __str__(self):
        return str(self.args[0])


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
    spec = json.loads(registry.latest(db, eid)["spec_json"] or "{}")
    if not spec.get("template") and not spec.get("family"):
        raise StepError(f"{eid} is not a catalogue or family instance")
    return spec.get("template")


def register_batch(db, eids, actor="strategy-1"):
    """PROTOCOL v2 batch: register every approved instance in `eids` together. Logs `batch.registered` with the
    trials-ledger cutoff, then queues the jobs so that no member validates before every member finished its cost step.
    Instances without a valid template approval are skipped. Family instances (amendment 8) are split off: each
    approved family registers its base instances as its own batch (see _register_family), a family whose registration
    stopped part-way is completed, and an error stays inside its family (recorded once as family.waiting). Returns the
    registered ids."""
    from lab import families
    fams, cat = {}, []
    for e in eids:
        fid = json.loads(registry.latest(db, e)["spec_json"] or "{}").get("family")
        if fid:
            fams.setdefault(fid, []).append(e)
        else:
            cat.append(e)
    for fid in families.unfinished(db):               # amendment 8 point 7: a batch that stopped part-way resumes
        fams.setdefault(fid, [])
    out = []
    if cat:
        blob = templates.catalogue_blob()
        out += _batch(db, sorted(e for e in cat if templates.approval(db, _template(db, e), blob) is not None), actor)
    for fid in sorted(fams):
        try:                                          # promotions, holdouts and diagnostics still run after an error
            out += _register_family(db, fid, fams[fid], actor)
        except Exception as e:
            try:
                families.waiting(db, fid, [f"registration error: {e!r}"[:200]], actor)
            except Exception:
                pass
    return out


def _batch(db, ok, actor, family=None, extra=None):
    if not ok:
        return []
    for eid in ok:
        if not (family and lifecycle.state(db, eid) == "REGISTERED"):    # a family batch resumes where it stopped
            _register_one(db, eid, actor)
    cutoff = db.one("SELECT COALESCE(MAX(id),0) FROM trials")[0]
    batch = "B-" + hashlib.sha256("|".join(ok).encode()).hexdigest()[:12]
    db.event("batch.registered", f"system:{actor}", None, {"batch": batch, "exp_ids": ok, "trial_cutoff_id": cutoff,
                                                          "protocol_version": 3 if family else max(
                                                              catalogue.protocol_of(_template(db, e)) for e in ok),
                                                          **({"family": family, "amendment": 8} if family else {}),
                                                          **(extra or {})})
    for eid in ok:
        enqueue_pipeline(db, eid, actor, batch_members=ok)
    return ok


def _register_family(db, fid, eids, actor):
    """Amendment 8 point 7: every approved base instance of an approved family registers once, together, as one batch:
    only when all of them are DISCOVERED (revival comes before approve-family, point 6), every spec is the one the
    family file and the approval bind (families.spec_problems), and families.registration_block finds nothing in the way
    (approval and reserved alpha, programme stop, open families, covering, graveyard re-check, embargo). A batch that
    stopped part-way is completed in a later pass (_resume_family). Point 9: a DISCOVERED successor whose registered
    parent's frozen training artifact meets its trigger registers as an extra batch of the family, before the cohort is
    fixed. An unapproved family is skipped silently; any other block is recorded once as family.waiting."""
    from lab import families
    out = _resume_family(db, fid, actor) if families.registered(db, fid) else []   # also under a void approval
    p = families.binding_approval(db, fid)          # once registered: the approval the registration cited
    if p is None:
        return out
    fam, why = families.load(fid), []
    if not families.registered(db, fid):
        base = sorted(families.exp_id(fid, i) for i in p.get("instances") or [])
        why = families.base_waiting(db, fid, p) or families.registration_block(db, fam) or [
            b for e in base if lifecycle.state(db, e) == "DISCOVERED" for b in families.spec_problems(db, e, fam, p)]
        if base and not why:
            out += _batch(db, base, actor, family=fid)
    for e in sorted(families.triggered(db, fam, eids) if families.registered(db, fid) else []):
        block = families.registration_block(db, fam, successor=e) or families.spec_problems(db, e, fam, p)
        if block:
            why += [f"{e}: {b}" for b in block]
        else:
            parent = families.exp_id(fid, json.loads(registry.latest(db, e)["spec_json"])["parent"])
            out += _batch(db, [e], actor, family=fid, extra={"successor_of": parent})
    if why:
        families.waiting(db, fid, why, actor)
    return out


def _resume_family(db, fid, actor):
    """Amendment 8 point 7 after a pass that stopped part-way once the base batch event was written: a REGISTERED
    successor outside every batch.registered event of its family gets its batch of one, and every batch member in
    REGISTERED or SCREENING (data-1 moves a member on as soon as its data job runs) gets the screening jobs it lacks
    (enqueue is idempotent). It runs whatever the approval says now: the batch was registered under a valid one, and
    the steps keep their own code pin. Returns the ids whose batch was written now."""
    from lab import families
    jobs.init(db)
    batches = [b for b in (json.loads(r[0]) for r in db.q("SELECT payload FROM events WHERE kind='batch.registered' "
                                                          "ORDER BY id")) if b.get("family") == fid]
    inside, out = {e for b in batches for e in b["exp_ids"]}, []
    for e in families.registered_members(db, fid):
        parent = json.loads(registry.latest(db, e)["spec_json"] or "{}").get("parent")
        if e not in inside and parent and lifecycle.state(db, e) == "REGISTERED":
            out += _batch(db, [e], actor, family=fid, extra={"successor_of": families.exp_id(fid, parent)})
    for b in batches:
        for e in b["exp_ids"]:
            if lifecycle.state(db, e) in ("REGISTERED", "SCREENING") and db.one(
                    f"SELECT COUNT(*) FROM jobs WHERE job_id IN ({','.join('?' * len(STEPS))})",
                    *(f"{s}|{e}" for s in STEPS))[0] < len(STEPS):
                enqueue_pipeline(db, e, actor, batch_members=b["exp_ids"])
    return out


def _register_one(db, eid, actor):
    v = registry.latest(db, eid)
    if json.loads(v["spec_json"] or "{}").get("family"):
        return _register_family_one(db, eid, v, actor)
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


def _register_family_one(db, eid, v, actor):
    """Version 2 always from families.instance_spec of the family file (spec_path = the family file, code_hash = its
    approved blob), a screening alpha row of 0 (amendment 8 point 13) and families.register_transition, which checks it
    field for field, in one transaction (a refusal leaves no version 2). A version 2 left by an older pass is checked
    the same way; any other version is refused."""
    from lab import families
    fid, iid = json.loads(v["spec_json"])["family"], json.loads(v["spec_json"])["instance"]
    if v["version"] not in (1, 2):
        raise lifecycle.LifecycleError(f"{eid} has spec version {v['version']}: a family instance registers only with "
                                       f"version 2, built from the approved family file (amendment 8 point 7)")
    if v["version"] == 2:
        return families.register_transition(db, eid, fid, f"system:{actor}")
    p = families.binding_approval(db, fid)
    if p is None:
        raise lifecycle.LifecycleError(f"family {fid} has no valid human approval")
    rel = f"research/families/{fid}.json"
    engine = {f: registry.blob_at(registry.last_commit(f), f) for f in ENGINE_CODE}
    spec = families.instance_spec(families.load(fid), iid, p["blobs"], engine)
    commit = registry.last_commit(rel)
    with db.tx():
        db.append("experiments", exp_id=eid, version=2, created_ts=int(time.time()),
                  mechanism_tag=v["mechanism_tag"], fingerprint=v["fingerprint"], spec_json=spec, spec_path=rel,
                  spec_commit=commit, code_hash=p["blobs"]["family"],
                  note=f"family {fid} instance {iid} spec (amendment 8)")
        db.append("alpha_ledger", exp_id=eid, ts=int(time.time()), alpha=0.0, note="A8 in-sample filter")
        db.event("exp.version_added", actor, eid, {"version": 2, "template": spec["template"], "family": fid})
        families.register_transition(db, eid, fid, f"system:{actor}")


def _priority(spec):
    """Job priority: the catalogue order, family instances after every catalogue template."""
    if spec.get("family"):
        from lab import families
        return families.PRIORITY
    return 20 + list(catalogue.TEMPLATES).index(spec["template"])


def enqueue_pipeline(db, eid, actor="strategy-1", batch_members=()):
    """Chain the steps. Under v2 the validate step also waits for the cost step of every batch member. A family's data
    step fetches its spot files at most 2 at a time (amendment 9), so it gets a longer lease."""
    spec = json.loads(registry.latest(db, eid)["spec_json"])
    prio = _priority(spec)
    prev = []
    for s in STEPS:
        deps = list(prev)
        if s == "validate":
            deps += [f"cost|{m}" for m in batch_members if m != eid]
        jobs.enqueue(db, f"{s}|{eid}", s, eid, {"exp_id": eid}, priority=prio, depends_on=deps,
                     timeout_s=900 if s in ("backtest", "adversarial", "validate") else
                     1800 if s == "data" and spec.get("family") else 300, actor=f"system:{actor}")
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
    v = registry.latest(db, eid)
    spec = json.loads(v["spec_json"])
    if spec.get("family") and v["version"] >= 2:          # amendment 8 point 18: a registered instance's code pin
        from lab import families                          # (before every step; fails closed, nothing is regenerated)
        bad = ([] if v["version"] == 2 else [f"spec version {v['version']} is not the registered version 2 "
                                             f"(amendment 8 points 7 and 18: fails closed)"]) + \
            families.pin_problems(spec, families.cited_approval(db, eid))
        if bad:
            raise StepError(f"{eid}: {'; '.join(bad)}")
    return spec


def _tpl(spec):
    """The template dict of a spec: the catalogue's, or a family instance's view (lab/families; never injected into
    catalogue.TEMPLATES)."""
    if spec.get("family"):
        from lab import families
        return families.template(spec)
    return catalogue.TEMPLATES[spec["template"]]


def _universe(spec):
    return tuple(spec["universe"]) if spec.get("family") else catalogue.universe(spec["template"])


def _min_symbols(spec):
    return spec["min_symbols"] if spec.get("family") else catalogue.min_symbols(spec["template"])


def _symbols(spec, split):
    """The coins a step reads for a data split. A family's 2024 holdout never reads its holdout_exclude coins, nor
    BTC/ETH/SOL (seen by L14_tsmom_v1, amendment 1): they are outside the declared set (amendment 8 point 16)."""
    if spec.get("family") and split == "holdout":
        drop = set(spec.get("holdout_exclude") or ()) | set(data.HOLDOUT_SEEN)
        return tuple(s for s in _universe(spec) if s not in drop)
    return _universe(spec)


PUBLICATION_RETRY_S = 86400                      # a forward month the archive has not published for any coin yet
DOWNLOAD_RETRY_S = 3600                          # a family download that failed (network, 5xx, 429) waits this long


def _download(db, eid, spec, split, worker, symbols):
    """{symbol: {'klines', 'funding'[, 'spot']}} downloaded or reused (parallel threads). A family's files (spot zips in
    their own directory) go through the embargo guard; a file that may not be fetched yet defers the job with a
    family.waiting event instead of failing it (amendment 8 point 17, amendment 9 point 1). A family download that
    fails (data._fetch gave up: network, 5xx, 429; never a 404) defers the job by DOWNLOAD_RETRY_S without using an
    attempt, so an outage never fails the job for good and stops the family (review of fdd898a)."""
    from concurrent.futures import ThreadPoolExecutor
    if not spec.get("family"):
        with ThreadPoolExecutor(DOWNLOAD_THREADS) as ex:
            return dict(ex.map(lambda s: (s, data.files_for(s, split)), symbols))
    from lab import families
    get, dlv = families.guarded_get(split), families.delivery_model(spec)
    try:
        if families.blocked(symbols, (split,), delivery=dlv):
            raise families.Embargoed(families.embargo_reason(split))
        with ThreadPoolExecutor(DOWNLOAD_THREADS) as ex:
            return dict(ex.map(lambda s: (s, {**data.files_for(s, split, get),
                                              "spot": data.spot_files_for(s, split, get),
                                              **({"delivery": data.delivery_files_for(s, split, get)} if dlv else {})}),
                               symbols))
    except families.Embargoed as e:
        families.waiting(db, spec["family"], [str(e)], f"system:{worker}",
                         topic=None if split in families.SCREEN_SPLITS else split)
        raise Deferred(f"{eid}: {e}", families.EMBARGO_UNTIL) from None
    except OSError as e:                             # the archive or the network failed (never a 404): wait, retry
        if not str(e).startswith("download failed"):
            raise
        families.waiting(db, spec["family"], [f"{e}; the step retries in {DOWNLOAD_RETRY_S // 60} minutes (a "
                                              f"download failure never stops a family)"], f"system:{worker}",
                         topic=None if split in families.SCREEN_SPLITS else split)
        raise Deferred(f"{eid}: {e}", int(time.time()) + DOWNLOAD_RETRY_S) from None


def _files(db, eid, split, worker, symbols=None, spec=None):
    """Download/reuse the split's files (parallel threads) and record the read through the gateway (state rules apply).
    A family's spot files are recorded in the same access as its perp files."""
    spec = spec or _spec(db, eid)
    symbols = symbols or _universe(spec)
    per_sym, all_files = _download(db, eid, spec, split, worker, symbols), []
    for s, f in per_sym.items():
        all_files += f["klines"] + f["funding"] + f.get("spot", []) + _delivery_paths(f)
    Gateway(db, f"system:{worker}").access(eid, data.GATEWAY_SPLIT[split],
                                           [os.path.join(HERE, p) if not os.path.isabs(p) else p for p in all_files],
                                           data.window(split), "https://data.binance.vision", "evaluate",
                                           _code_hash(spec))
    return per_sym


def _delivery_paths(f):
    """The COIN-M quarterly zips of one symbol's files (instrument model spot_delivery_ratio), else []."""
    return [p for c in f.get("delivery") or [] for p in c.get("paths") or []]


def _load(per_sym, split):
    bars, funding, dups = {}, {}, {}
    for s, f in per_sym.items():
        bars[s], funding[s], dups[s] = data.load(f, split)
    return bars, funding, dups


V3_SPLITS = {"train": "train3", "validation": "validation3", "holdout": "holdout"}


def _sp(spec, split):
    """Logical split -> data window of the experiment's protocol (v3 uses longer windows)."""
    return V3_SPLITS.get(split, split) if (spec.get("protocol_version") or 1) >= 3 else split


def _code_hash(spec=None):
    """The gateway's code hash: the catalogue blob, or for a family instance its registered family file blob (amendment
    8 point 16), so a catalogue change never locks a family holdout."""
    if spec and spec.get("family"):
        return spec["code_blobs"]["family"]
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
    tpl = _tpl(spec)
    symbols = _symbols(spec, split)
    per_sym = _files(db, eid, split, worker, symbols, spec)
    if spec.get("family"):            # amendment 8: the instrument series, and the perps for the benchmark
        from lab import families
        bars, funding, dups, fd = families.transform(spec, per_sym, split)
        _drop(bars, funding, fd, exclude, spec)
        for s in exclude:
            dups.pop(s, None)
        return bars, funding, dups, fd
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
    split = _sp(spec, split)
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
    return q, excluded, series_ok and len(q) - len(excluded) >= _min_symbols(spec)


def _t(t):
    """A template given by catalogue name or as a template dict (_tpl)."""
    return catalogue.TEMPLATES[t] if isinstance(t, str) else t


def _family(t):
    """The template's family with one calling convention: (bars_by, funding_by, params, fit=None, data=None)."""
    tpl = _t(t)
    fam = tpl["family"]
    if tpl.get("needs"):
        return lambda b, f, p, fit=None, volume_by=None: fam(b, f, p, None, extra=volume_by)
    return fam


def _positions(t, bars, funding, params, fit, vol=None):
    tpl = _t(t)
    fam = tpl["family"]
    if tpl.get("family_id"):          # amendment 8: a mechanism function sees only its instrument series and funding
        return fam(bars, funding, params, None)
    if tpl.get("needs"):
        return fam(bars, funding, params, None, extra=vol)
    if tpl.get("cross_sectional"):
        return fam(bars, funding, params, None, vol) if vol is not None else fam(bars, funding, params, None)
    return {s: fam(bars[s], funding[s], params, fit.get(s) if fit else None) for s in bars}


def _fit(t, bars, params):
    f = _t(t).get("fit")
    return {s: f(b, params) for s, b in bars.items()} if f else None


def _evaluate(bars, funding, pos, costs, mult=1.0, seed=SEED, lb_q=0.10):
    rows = {s: backtest.apply_costs(backtest.gross(bars[s], pos[s]), funding[s], costs, mult) for s in bars}
    return backtest.metrics(backtest.portfolio(rows), seed=seed, lb_q=lb_q)


def _benchmark(bars, funding, costs, seed=SEED):
    pos = {s: [0.0] + [1.0] * (len(b) - 1) for s, b in bars.items()}
    return _evaluate(bars, funding, pos, costs, seed=seed)


def _bench(bars, funding, spec, vol=None):
    """A step's buy-and-hold benchmark: the universe with the spec's costs and funding, or for a family instance
    (amendment 8 point 8) the same perps with the catalogue's costs and their settled funding, never the instrument."""
    from lab import families
    if isinstance(vol, families.FamilyData):
        return _benchmark(vol.perp, vol.funding, catalogue.COSTS)
    return _benchmark(bars, funding, spec["costs"])


def _strip(m):
    return {k: v for k, v in m.items() if k != "daily_net"}


DSR_GATE = "deflated Sharpe probability >= 0.95"


# ---------- step handlers (each returns a JSON-able result) ----------
def step_data(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)                       # a family's code pin fails closed before anything (amendment 8 p. 18)
    if lifecycle.state(db, eid) == "REGISTERED":
        lifecycle.auto_transition(db, eid, "SCREENING", f"system:{worker}", "screening starts: data fetch and checks")
    report, excluded, oks = {}, {}, []
    if spec.get("family"):            # amendment 9 point 1: every screening file is fetched now (guarded), not read
        _download(db, eid, spec, _sp(spec, "validation"), worker, _universe(spec))
    for split in (("train",) if _v2(spec) else ("train", "validation")):     # v2: validation is read only to validate
        bars, _, dups, bundle = _market(db, eid, split, worker, spec)
        report[split], excluded[split], ok_split = _quality(bars, split, dups, spec, bundle)
        oks.append(ok_split)
    ok = all(oks)
    art = save_artifact(eid, "data", {"quality": report, "ok": ok, "excluded": excluded,
                                      "min_symbols": _min_symbols(spec)})
    return {"ok": ok, "artifact": art, "symbols": len(_universe(spec)),
            "excluded": sum(len(v) for v in excluded.values())}


def step_backtest(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    bars, funding, _, vol = _train(db, eid, worker, spec)
    out = []
    for k, params in enumerate(spec["grid"]):
        fit = _fit(_tpl(spec), bars, params)
        pos = _positions(_tpl(spec), bars, funding, params, fit, vol)
        out.append({"variant": k, "params": params, "fit": fit,
                    "positions": {s: [round(x, 6) for x in p] for s, p in pos.items()}})
    art = save_artifact(eid, "backtest", {"split": "train", "variants": out})
    return {"variants": len(out), "artifact": art, "tests": len(out)}


def step_cost(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    bars, funding, _, vol = _train(db, eid, worker, spec)
    bt = load_artifact(eid, "backtest")
    results = []
    seen = {r["variant"] for r in db.q("SELECT variant FROM trials WHERE exp_id=? AND split='train'", eid)}
    for v in bt["variants"]:
        m = _evaluate(bars, funding, v["positions"], spec["costs"])
        hi = _evaluate(bars, funding, v["positions"], spec["costs"], catalogue.COST_HIGH_MULT)
        sr_d = (m["net_mean_daily"] / m["net_sd_daily"]) if m.get("net_sd_daily") else None
        if v["variant"] not in seen:            # a re-run after an interrupted stop is the same trial (amendment 6)
            db.append("trials", exp_id=eid, ts=int(time.time()), variant=v["variant"], split="train",
                      sharpe_daily=sr_d, n_days=m["days"], net_total=m["net_total"], params=v["params"])
        results.append({"variant": v["variant"], "params": v["params"], "net": _strip(m), "net_2x_costs": _strip(hi)})
    bench = _strip(_bench(bars, funding, spec, vol))
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
    tpl, v = _tpl(spec), load_artifact(eid, "backtest")["variants"][cost["selected"]]
    bars, funding, _, vol = _train(db, eid, worker, spec)
    if spec.get("family"):            # amendment 8 point 8: tests and placebo on the instrument series alone
        vol = None
    fam = _family(tpl)
    if tpl.get("cross_sectional"):
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
    pos = _positions(_tpl(spec), bars, funding, v["params"], v["fit"], vol)  # frozen params and train fit
    m = _evaluate(bars, funding, pos, spec["costs"])
    hi = _evaluate(bars, funding, pos, spec["costs"], catalogue.COST_HIGH_MULT)
    bench = _bench(bars, funding, spec, vol)
    trials = dsr_trials(db, eid, spec)
    sr_d = (m["net_mean_daily"] / m["net_sd_daily"]) if m.get("net_sd_daily") else None
    dsr = backtest.deflated_sharpe(sr_d, trials, m["days"])
    gates = {"net_mean_daily > 0": (m["net_mean_daily"] or 0) > 0,
             "one-sided 90% lower bound > 0": (m["lb_one_sided"] or -1) > 0,
             "net Sharpe > buy-and-hold": (m["net_sharpe_ann"] or -9e9) > (bench["net_sharpe_ann"] or -9e9),
             "net total > 0 at 2x costs": hi["net_total"] > 0,
             DSR_GATE: (dsr or 0) >= catalogue.DSR_MIN,
             "adversarial checks pass": bool(adv.get("ok"))}
    if _v2(spec):
        gates["validation data quality"] = v_enough
    extra = {}
    if spec.get("family"):            # amendment 8 point 8: mechanism attribution, a stricter gate
        from lab import families
        extra["attribution"] = families.attribution(spec, m, bars, pos)
        gates.update({f"mechanism attribution: {k}": ok for k, ok in extra["attribution"]["gates"].items()})
    art = save_artifact(eid, "validate", {"metrics": _strip(m), "metrics_2x_costs": _strip(hi),
                                          "benchmark": _strip(bench), "dsr": dsr, "trials_counted": len(trials),
                                          "gates": gates, "daily_net": m["daily_net"], "validation_quality": vq,
                                          "validation_excluded": v_excluded, **extra})
    return {"passed": all(gates.values()), "artifact": art, "tests": 1}


def _report_resume(db, eid, worker):
    """A family instance's report job retried after a crash or a lost lease (review of 4c32ff6, finding 5): the screen
    result its first run recorded (by the step, for the current spec version) takes the edge it decided, or is returned
    once that edge was taken; nothing is recorded twice. None when the step has not recorded one."""
    from lab import families
    v = registry.latest(db, eid)["version"]
    for r in db.q("SELECT id, verdict FROM results WHERE exp_id=? AND label='EXPLORATORY' AND version=? ORDER BY id DESC",
                  eid, v):
        verdict = r["verdict"] or ""
        if not verdict.startswith(("OBSERVE (family forward test)", "REJECTED")) or \
                verdict.startswith(families.NOT_SELECTED) or not str(families.recorded_by(db, eid, r["id"]) or "").startswith("system:"):
            continue
        st = lifecycle.state(db, eid)
        if st == "SCREENING":
            ev = {"result_id": r["id"]}
            lifecycle.auto_transition(db, eid, "OBSERVATION" if verdict.startswith("OBSERVE") else "REJECTED",
                                      f"system:{worker}", verdict[:300], ev, guards=(registry.make_result_guard(ev),))
            st = lifecycle.state(db, eid)
        return {"verdict": verdict, "result_id": r["id"], "state": st, "resumed": True}
    return None


def step_report(db, job, worker):
    eid = job["exp_id"]
    spec = _spec(db, eid)
    if spec.get("family"):
        done = _report_resume(db, eid, worker)
        if done is not None:
            return done
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
        if spec.get("observation_test") and failed == [DSR_GATE]:
            start = _next_month(time.time())
            verdict = (f"OBSERVE (forward test): passed every validation gate except the luck check (DSR "
                       f"{val.get('dsr') or 0:.3f}); forward window {_ymd(start)} + {OBSERVATION_MONTHS} months "
                       f"(research/PROTOCOL_V3.md amendment 2)")
        if spec.get("family") and set(failed) <= {DSR_GATE}:    # amendment 8 point 8: the screen is only a filter
            verdict = (f"OBSERVE (family forward test): passed every screening gate"
                       f"{' except the luck check' if failed else ''} (DSR {val.get('dsr') or 0:.3f} is recorded and "
                       f"decides nothing); the family cohort fixes the forward window (research/PROTOCOL_V3.md "
                       f"amendment 8 points 8 and 10)")
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
    to = "SCREEN_PASSED" if verdict.startswith("PASS") and not spec.get("family") else (   # a family: never
        "OBSERVATION" if verdict.startswith("OBSERVE") else "REJECTED")
    lifecycle.auto_transition(db, eid, to, f"system:{worker}", verdict[:300], ev,
                              guards=(registry.make_result_guard(ev),))
    if to == "OBSERVATION" and not spec.get("family"):     # a family's cohort starts its window (amendment 8 point 10)
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
    """Forward test on new, unseen data (amendment 2; a family instance: amendment 8 point 11). The data window cannot be
    read before it has ended. The amendment 2 cohort N counts only events without a cohort key (amendment 8 point 10),
    so MVRV's N stays 1."""
    eid = job["exp_id"]
    if lifecycle.state(db, eid) != "OBSERVATION":
        from lab import families      # a family's retry after its edge was taken completes (engineering finding #3)
        done = _forward_resume(db, eid, worker, (families.FORWARD_PASS, families.FORWARD_FAIL)) \
            if families.is_instance(db, eid) else None
        if done is not None:
            return done
        raise StepError("forward test requires lifecycle OBSERVATION")
    pl = job["payload"]
    spec = _spec(db, eid)
    if spec.get("family"):            # amendment 8 point 11: the family forward test of a fixed cohort decides
        return _family_forward(db, eid, worker, spec)
    split = data.forward_split(pl["start"], pl.get("months", OBSERVATION_MONTHS))
    v = frozen_variant(db, eid)                                          # verified against the recorded hashes
    bars, funding, dups, vol = _market(db, eid, split, worker, spec)      # data.window() refuses unfinished windows
    q, excluded, enough = _quality(bars, split, dups, spec, vol)
    _drop(bars, funding, vol, excluded, spec)
    pos = _positions(_tpl(spec), bars, funding, v["params"], v["fit"], vol)
    m = _evaluate(bars, funding, pos, spec["costs"])
    hi = _evaluate(bars, funding, pos, spec["costs"], catalogue.COST_HIGH_MULT)
    bench = _bench(bars, funding, spec, vol)
    a, _ = data.window_bounds(split)
    cohort = 0
    for r in db.q("SELECT ts, payload FROM events WHERE kind='observation.started'"):
        p = json.loads(r["payload"])
        if p.get("window") == split and r["ts"] < a and not p.get("cohort"):    # amendment 8 cohorts count apart
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


def _forward_market(db, eid, worker, spec, months):
    """Amendment 8 points 11 and 12: the window a fixed cohort declared (months 1-12, or 1-6 for the interim look) on
    archive data, read only after it ended plus the 7-day publication lag. Coins with no perp or spot file for the first
    month are excluded before any computation, then the quality rule with min_symbols; the frozen variant runs on the
    instrument series, the benchmark is the same perps' buy-and-hold, and the family module's attribution applies.
    A coin delisted in the window is excluded from the day after (amendment 7 point 5, which point 11 cites): its data
    up to its last listed hour stays in, judged by the same quality rule over those hours, its position is closed at
    that hour (the exit is charged) and the weight goes to the rest. The min_symbols count is unchanged: only coins
    with the whole window count, so a delisting never helps the data-quality gate."""
    from lab import families
    cf = families.cohort_of(db, eid)
    if cf is None:
        raise StepError(f"{eid} is not a selected member of a fixed family cohort (amendment 8 point 10)")
    split = data.forward_split(cf["start"], months, tagged=True)
    if split != cf["window" if months == families.FORWARD_MONTHS else "sub_window"]:
        raise StepError(f"{split} is not a window cohort {cf['cohort']} declared")
    data.window(split)                                   # refuses an unfinished window before anything is read
    v = frozen_variant(db, eid)                          # verified against the recorded hashes
    bars, funding, dups, fd = _market(db, eid, split, worker, spec)
    dlv = families.delivery_model(spec)
    late = families.unpublished(list(bars), split, delivery=dlv)
    if late:                                             # never a delisting of every coin: wait, read nothing yet
        families.waiting(db, cf["family"], [late], f"system:{worker}", topic=split)
        raise Deferred(f"{eid}: {late}", int(time.time()) + PUBLICATION_RETRY_S)
    gone = families.unlisted(list(bars), split, delivery=dlv)
    _drop(bars, funding, fd, gone, spec)
    for s in gone:
        dups.pop(s, None)
    q, excluded, enough = _quality(bars, split, dups, spec, fd)      # enough: whole-window coins only, as before
    late = families.delisted({s: bars[s] for s in excluded}, split, delivery=dlv)
    for s, last in late.items():
        q[s] = families.listed_quality(bars[s], split, dups[s], last)
    kept = {s: last for s, last in late.items() if q[s]["ok"]}
    excluded = [s for s in excluded if s not in kept]
    _drop(bars, funding, fd, excluded, spec)
    families.listed_only(bars, funding, fd, kept)
    pos = _positions(_tpl(spec), bars, funding, v["params"], v["fit"], fd)
    for s in kept:                                       # flat after the last listed hour: the exit is charged there
        if pos.get(s):
            pos[s] = list(pos[s][:-1]) + [0.0]
    m = _evaluate(bars, funding, pos, spec["costs"])
    return cf, split, {"m": m, "hi": _evaluate(bars, funding, pos, spec["costs"], catalogue.COST_HIGH_MULT),
                       "bench": _bench(bars, funding, spec, fd), "attribution": families.attribution(spec, m, bars, pos),
                       "quality": q, "excluded": excluded, "unlisted": gone, "enough": enough,
                       "delisted": {s: {"last_listed_hour": t, "excluded_from": _ymd(t - t % DAY_S + DAY_S)}
                                    for s, t in sorted(kept.items())}, "symbols": sorted(bars)}


def step_observe_interim(db, job, worker):
    """Amendment 8 point 12: the reject-only look at months 1-6 of a family cohort's window, at the earliest 7 days
    after the sub-window ended. Net mean per day <= 0 or cash flow minus costs <= 0 is 'FAIL (forward futility)' ->
    REJECTED; otherwise the final forward test is queued (not_before = window end + 7 days). It never passes and changes
    neither M nor alpha_i. A retry after a crash or a lost lease completes what the first run decided (_interim_resume)
    and reads nothing again."""
    from lab import families
    eid = job["exp_id"]
    spec = _spec(db, eid)                                # the code pin fails closed first (amendment 8 point 18)
    if not spec.get("family"):
        raise StepError("the interim look is for amendment 8 family instances only")
    done = _interim_resume(db, eid, worker)
    if done is not None:
        return done
    if lifecycle.state(db, eid) != "OBSERVATION":
        raise StepError("the interim look requires lifecycle OBSERVATION")
    cf, split, f = _forward_market(db, eid, worker, spec, families.INTERIM_MONTHS)
    m, att = f["m"], f["attribution"]
    checks = {"net_mean_daily > 0": (m.get("net_mean_daily") or 0) > 0,
              "cash flow - costs > 0": (att.get("cash_flow_minus_costs") or 0) > 0}
    failed = [k for k, ok in checks.items() if not ok]
    art = save_artifact(eid, "observe_interim", {"window": split, "cohort": cf["cohort"], "metrics": _strip(m),
                                                 "attribution": att, "checks": checks, "quality": f["quality"],
                                                 "excluded": f["excluded"], "unlisted": f["unlisted"],
                                                 "delisted": f["delisted"], "symbols": f["symbols"],
                                                 "decisional": "reject-only", "daily_net": m.get("daily_net") or []})
    if failed:
        verdict = (f"{families.FUTILITY}: failed {', '.join(failed)} on {split} (reject-only interim look, amendment 8 "
                   f"point 12)")
        rid = registry.record_result(db, eid, "VALIDATION", verdict, {"interim": _strip(m), "attribution": att,
                                                                      "checks": checks, "window": split,
                                                                      "cohort": cf["cohort"]},
                                     {"artifacts": [art]}, f"system:{worker}")
        ev = {"result_id": rid}
        lifecycle.auto_transition(db, eid, "REJECTED", f"system:{worker}", verdict[:300], ev,
                                  guards=(registry.make_result_guard(ev),))
        return {"verdict": verdict, "result_id": rid, "state": "REJECTED", "artifact": art, "tests": 1}
    db.event("family.interim", f"system:{worker}", eid, {"cohort": cf["cohort"], "window": split, "outcome": "continue",
                                                         "checks": checks, "artifact_sha256": art["sha256"]})
    _queue_final(db, eid, cf, worker)
    return {"verdict": INTERIM_CONTINUE, "state": "OBSERVATION", "artifact": art, "tests": 1}


INTERIM_CONTINUE = "continue: the final forward test is queued"


def _queue_final(db, eid, cf, worker):
    """The deciding forward test of a selected member (not_before = window end + 7 days); enqueue is idempotent."""
    from lab import families
    jobs.enqueue(db, f"observe|{eid}", "observe", eid, {"start": cf["start"], "months": families.FORWARD_MONTHS,
                                                        "cohort": cf["cohort"]}, priority=5, max_attempts=3,
                 timeout_s=1800, actor=f"system:{worker}", not_before=cf["final_not_before"])


def _forward_resume(db, eid, worker, kinds):
    """Engineering finding #3: a forward step retried after a crash or a lost lease completes what its earlier run
    recorded instead of failing for good, and reads and records nothing again. A forward result of the member's cohort
    (families.forward_result: recorded by the step, its cohort id, its hash-matching artifact) whose verdict starts with
    one of `kinds` takes the OBSERVATION edge it decides, or is returned once that edge was taken. Else None."""
    from lab import families
    st = lifecycle.state(db, eid)
    for r in db.q("SELECT id, verdict, metrics, evidence FROM results WHERE exp_id=? AND label='VALIDATION' ORDER BY id",
                  eid):
        v = r["verdict"] or ""
        out = families.forward_result(db, eid, r) if v.startswith(kinds) else None
        to = {"PASS": "SCREEN_PASSED", "FAIL": "REJECTED"}.get(out)
        if to is None or st not in ("OBSERVATION", to):
            continue
        ev = {"result_id": r["id"]}
        if st == "OBSERVATION":
            lifecycle.auto_transition(db, eid, to, f"system:{worker}", v[:300], ev,
                                      guards=(registry.make_result_guard(ev),))
        art = next((a for a in families._obj(r["evidence"]).get("artifacts") or [] if isinstance(a, dict)), None)
        return {"verdict": v, "result_id": r["id"], "state": to, "artifact": art, "tests": 0, "resumed": True}
    return None


def _interim_resume(db, eid, worker):
    """The interim look's retry (engineering finding #3): its 'continue' event (re)queues the final test, its futility
    result rejects (_forward_resume). The look itself runs once (amendment 8 point 12). None when it has not decided."""
    from lab import families
    ev = db.one("SELECT payload FROM events WHERE kind='family.interim' AND exp_id=? ORDER BY id LIMIT 1", eid)
    if ev is None:
        return _forward_resume(db, eid, worker, (families.FUTILITY,))
    p, cf = json.loads(ev["payload"]), families.cohort_of(db, eid)
    if lifecycle.state(db, eid) != "OBSERVATION" or cf is None or p.get("outcome") != "continue" or \
            p.get("cohort") != cf["cohort"]:
        raise StepError(f"{eid}: the interim look runs once (amendment 8 point 12)")
    _queue_final(db, eid, cf, worker)
    path = os.path.relpath(os.path.join(ARTIFACTS, eid, "observe_interim.json"), HERE).replace("\\", "/")
    return {"verdict": INTERIM_CONTINUE, "state": "OBSERVATION", "artifact": {"path": path,
                                                                             "sha256": p.get("artifact_sha256")},
            "tests": 0, "resumed": True}


def _family_forward(db, eid, worker, spec):
    """Amendment 8 point 11, the deciding forward test of a selected cohort member (after its interim look continued):
    the gates of amendment 2 point 4 against the perps' buy-and-hold, data quality with min_symbols, the mechanism
    attribution, and PSR_cons >= 1 - alpha_i with alpha_i from cohort.fixed (never recomputed). PASS -> SCREEN_PASSED,
    FAIL -> REJECTED; the result is a VALIDATION row. Families never take the automatic promotion path (point 16)."""
    from lab import families
    if not db.one("SELECT 1 FROM events WHERE kind='family.interim' AND exp_id=?", eid):
        raise StepError(f"{eid}: the final forward test follows the interim look (amendment 8 point 12)")
    done = _forward_resume(db, eid, worker, (families.FORWARD_PASS, families.FORWARD_FAIL))   # a retry: no 2nd read
    if done is not None:
        return done
    cf, split, f = _forward_market(db, eid, worker, spec, families.FORWARD_MONTHS)
    m, hi, bench, att = f["m"], f["hi"], f["bench"], f["attribution"]
    need = 1 - cf["alpha_i"]
    prob, psr_detail = families.psr_cons(m.get("daily_net") or [])
    gates = {"net_mean_daily > 0": (m.get("net_mean_daily") or 0) > 0,
             "one-sided 90% lower bound > 0": (m.get("lb_one_sided") or -1) > 0,
             "net Sharpe > buy-and-hold": (m.get("net_sharpe_ann") or -9e9) > (bench.get("net_sharpe_ann") or -9e9),
             "net total > 0 at 2x costs": (hi.get("net_total") or 0) > 0,
             f"forward luck check PSR_cons >= {need:.4f}": (prob or 0) >= need,
             "forward data quality": f["enough"],
             **{f"mechanism attribution: {k}": ok for k, ok in att["gates"].items()}}
    failed = [k for k, ok in gates.items() if not ok]
    verdict = (f"{families.FORWARD_PASS}: every gate passed on the unseen window {split} (M {cf['M']}, alpha_i "
               f"{cf['alpha_i']:.5f}); the 2024 holdout and simulated trading need human approvals (amendment 8 "
               f"point 16)" if not failed else f"{families.FORWARD_FAIL}: failed {', '.join(failed)}")
    art = save_artifact(eid, "observe", {"window": split, "cohort": cf["cohort"], "M": cf["M"], "alpha_i": cf["alpha_i"],
                                         "metrics": _strip(m), "metrics_2x_costs": _strip(hi),
                                         "benchmark": _strip(bench), "psr_cons": prob, "psr": psr_detail,
                                         "attribution": att, "gates": gates, "quality": f["quality"],
                                         "excluded": f["excluded"], "unlisted": f["unlisted"],
                                         "delisted": f["delisted"], "symbols": f["symbols"],
                                         "daily_net": m.get("daily_net") or []})
    rid = registry.record_result(db, eid, "VALIDATION", verdict, {"forward": _strip(m), "benchmark": _strip(bench),
                                                                  "psr_cons": prob, "psr": psr_detail,
                                                                  "alpha_i": cf["alpha_i"], "M": cf["M"],
                                                                  "cohort": cf["cohort"], "gates": gates,
                                                                  "attribution": att, "window": split},
                                 {"artifacts": [art]}, f"system:{worker}")
    ev = {"result_id": rid}
    to = "SCREEN_PASSED" if not failed else "REJECTED"
    lifecycle.auto_transition(db, eid, to, f"system:{worker}", verdict[:300], ev,
                              guards=(registry.make_result_guard(ev),))
    return {"verdict": verdict, "result_id": rid, "state": to, "artifact": art, "tests": 1}


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
    from lab import families
    tpl = _tpl(spec)
    for s in symbols:
        bars.pop(s, None), funding.pop(s, None)
        if isinstance(vol, families.FamilyData):
            vol.drop(s)
        elif vol is not None and tpl.get("needs_volume"):
            vol.pop(s, None)
        elif vol is not None:
            for k in ("volume", "taker", "metrics"):
                (vol.get(k) or {}).pop(s, None)
            for per in (vol.get("cm") or {}).values():
                per.pop(s, None)


def _declare_holdout(db, eid, spec, worker):
    """Amendment 7 section 8: open the holdout once with every file of every source the step will read (bars,
    funding and the template's extra series). Later reads in the step must be part of this set, unchanged. A family's
    spot files are part of the set, its excluded coins are not (_symbols), its files come through the embargo guard
    (2024 data only after 2026-11-27) and its family file blob is the code hash (amendment 8 point 16)."""
    tpl, sp = _tpl(spec), _sp(spec, "holdout")
    symbols, needs = _symbols(spec, sp), tpl.get("needs") or []
    paths = []
    per = _download(db, eid, spec, sp, worker, symbols) if spec.get("family") else \
        {s: data.files_for(s, sp) for s in symbols}
    for s, f in per.items():                           # the same paths as _files and _extra read them
        paths += [os.path.join(HERE, p) if not os.path.isabs(p) else p for p in f["klines"] + f["funding"]
                  + f.get("spot", []) + _delivery_paths(f)]
    if "metrics" in needs:
        paths += [data.metrics_for(s, sp) for s in symbols]
    if "dvol" in needs:
        paths += [data.dvol_for(c, sp) for c in sorted({s.replace("USDT", "") for s in symbols})]
    if "rates" in needs:
        paths.append(data.fred_for("DFII10", sp))
    if "cm" in needs:
        paths += [data.cm_for(m, sp, symbols) for m in tpl.get("cm_metrics", [])]
    if "stable" in needs:
        paths.append(data.stable_for(sp))
    return Gateway(db, f"system:{worker}").access(eid, data.GATEWAY_SPLIT[sp], paths, data.window(sp),
                                                 "holdout: every source in one declared set", "evaluate",
                                                 _code_hash(spec))


def _holdout_resume(db, eid, worker):
    """A family instance's holdout job retried after a crash or a lost lease (review of fdd898a): the holdout result its
    first run recorded (by the step, citing its hash-matching holdout.json) takes the edge it decided, or is returned
    once that edge was taken; the sealed holdout is never read or recorded twice. None when there is none."""
    from lab import families
    v = registry.latest(db, eid)["version"]
    for r in db.q("SELECT id, verdict, evidence FROM results WHERE exp_id=? AND label='VALIDATION' AND version=? "
                  "ORDER BY id DESC", eid, v):
        verdict = r["verdict"] or ""
        if not verdict.startswith(("PASS (holdout)", "FAIL (holdout)")) or \
                not str(families.recorded_by(db, eid, r["id"]) or "").startswith("system:") or \
                not families.cites(eid, families._obj(r["evidence"]), "holdout"):
            continue
        if lifecycle.state(db, eid) == "VALIDATION":
            ev = {"result_id": r["id"]}
            lifecycle.auto_transition(db, eid, "VALIDATED" if verdict.startswith("PASS") else "REJECTED",
                                      f"system:{worker}", verdict, ev, guards=(registry.make_result_guard(ev),))
        return {"verdict": verdict, "result_id": r["id"], "state": lifecycle.state(db, eid), "resumed": True}
    return None


def step_holdout(db, job, worker):
    """Sealed 2024 holdout, only reachable after a human-approved SCREEN_PASSED -> VALIDATION transition (a family
    instance: typed in a terminal, never the automatic path or the dashboard, amendment 8 point 16)."""
    eid = job["exp_id"]
    if json.loads((registry.latest(db, eid) or {"spec_json": "{}"})["spec_json"] or "{}").get("family"):
        done = _holdout_resume(db, eid, worker)          # a retry never reads the sealed holdout twice
        if done is not None:
            return done
    if lifecycle.state(db, eid) != "VALIDATION":
        raise StepError("holdout requires lifecycle VALIDATION")
    spec = _spec(db, eid)
    if spec.get("template") in NO_CLEAN_HOLDOUT:
        raise StepError("no clean holdout possible: BTC/ETH 2024 data was already seen by L14_tsmom_v1 "
                        "(research/PROTOCOL_V3.md amendment 1)")
    if spec.get("family") and not spec.get("clean_holdout"):
        raise StepError("no clean holdout declared in the family file: the instance stops at SCREEN_PASSED "
                        "(research/PROTOCOL_V3.md amendment 8 point 16)")
    v = frozen_variant(db, eid)                                          # verified against the recorded hashes
    _declare_holdout(db, eid, spec, worker)                              # amendment 7 section 8
    bars, funding, dups, vol = _market(db, eid, "holdout", worker, spec)
    hq, h_excluded, h_enough = _quality(bars, "holdout", dups, spec, vol)
    if _tpl(spec).get("universe") in ("30", "30v3", "cm16"):
        h_excluded = sorted(set(h_excluded) | set(data.HOLDOUT_SEEN))
    h_left = [s for s in hq if s not in h_excluded]
    h_enough = bool(h_enough) and len(h_left) >= _min_symbols(spec)   # amendment 5 (stricter)
    _drop(bars, funding, vol, h_excluded, spec)
    pos = _positions(_tpl(spec), bars, funding, v["params"], v["fit"], vol)
    m = _evaluate(bars, funding, pos, spec["costs"], lb_q=0.05)
    bench = _bench(bars, funding, spec, vol)
    gates = {"net_mean_daily > 0": (m["net_mean_daily"] or 0) > 0, "one-sided 95% lower bound > 0": (m["lb_one_sided"] or -1) > 0,
             "net Sharpe > buy-and-hold": (m["net_sharpe_ann"] or -9e9) > (bench["net_sharpe_ann"] or -9e9),
             "holdout data quality (min symbols)": h_enough}
    passed = all(gates.values())
    verdict = "PASS (holdout): paper-eligible after a human approval" if passed else \
        f"FAIL (holdout): failed {', '.join(k for k, ok in gates.items() if not ok)}"
    extra = {}
    if spec.get("family"):            # recorded for the human steps; amendment 8 point 16 adds no holdout gate
        from lab import families
        extra = {"not_read": sorted(set(_universe(spec)) - set(_symbols(spec, "holdout"))), "excluded": h_excluded,
                 "attribution_recorded": families.attribution(spec, m, bars, pos)}
        if passed:
            verdict = ("PASS (holdout): simulated trading of a family instance needs a live spot feed and a later "
                       "amendment (research/PROTOCOL_V3.md amendment 8 point 16)")
    art = save_artifact(eid, "holdout", {"metrics": _strip(m), "benchmark": _strip(bench), "gates": gates,
                                         "daily_net": m["daily_net"], **extra})
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
            "diagnose": step_diagnose, "observe_interim": step_observe_interim,
            # PROTOCOL_V3 amendment 9 section 3; lab/scanresearch.py imports this module, so it is resolved per call
            "scan_digest": lambda db, job, worker: __import__("lab.scanresearch", fromlist=["step_digest"])
            .step_digest(db, job, worker),
            "scan_dossier": lambda db, job, worker: __import__("lab.scanresearch", fromlist=["step_dossier"])
            .step_dossier(db, job, worker),
            # PROTOCOL_V3 amendment 10: the exploration lane (decides nothing; lab/explore.py imports this module)
            "explore": lambda db, job, worker: __import__("lab.explore", fromlist=["step_explore"])
            .step_explore(db, job, worker),
            "explore_report": lambda db, job, worker: __import__("lab.explore", fromlist=["step_report"])
            .step_report(db, job, worker),
            # amendment 12d: the daily report on lane and scanner accounts (decides nothing)
            "lane_report": lambda db, job, worker: __import__("lab.lane", fromlist=["step_report"])
            .step_report(db, job, worker),
            # amendment 11c: the adversarial review of a lane candidate (gates only a simulated lane account)
            "lane_review": lambda db, job, worker: __import__("lab.lane", fromlist=["step_review"])
            .step_review(db, job, worker),
            # amendment 14: one unit of free public data, summarised; decides nothing
            "ingest": lambda db, job, worker: __import__("lab.ingest", fromlist=["step_ingest"])
            .step_ingest(db, job, worker)}


def enqueue_holdouts(db, actor="strategy-1"):
    """Experiments a human moved into VALIDATION get exactly one holdout job. A family instance fetches its 2024 spot
    and perp files at most 2 at a time (amendment 9), so it gets the longer lease of its data step."""
    n = 0
    for x in registry.status(db):
        if x["state"] == "VALIDATION" and x["exp_id"].startswith("E_"):
            fam = json.loads(registry.latest(db, x["exp_id"])["spec_json"] or "{}").get("family")
            _, created = jobs.enqueue(db, f"holdout|{x['exp_id']}", "holdout", x["exp_id"], {}, priority=5,
                                      max_attempts=2, timeout_s=1800 if fam else 900, actor=f"system:{actor}")
            n += created
    return n
