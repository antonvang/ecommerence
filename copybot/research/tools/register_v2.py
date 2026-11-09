"""Director order 75 P0: register V2, the side record for FUTURE studies.

WHY A NEW CHAIN. factory.Ledger hashes every key of a row and registry.json is pinned by sha256, so nothing here touches
research/data/factory/*, a ledger row or the register_stats chain. A V2 record is keyed by an id of the caller's choice
(for a historical row: the ledger row's own hash) and joined read-only by `historical_view`.

WHAT A RECORD HOLDS: hypothesis id and lineage; the pre-registered trial universe; variants tested; parameters and code
hash; data source and period; cost model; evaluation method; data-quality status; protocol deviations. Optionally a
pointer to a register snapshot (register_snapshot.py) and to a register_stats side record.

RULES:
- A field that is not documented holds the sentinel MISSING_INPUT. There is no default and no "probably": `deviations`
  absent means UNKNOWN, and [] means none, which only a statement can say.
- A FUTURE record must state everything fixed before the run. Only `variants_tested` may wait for the run. A HISTORICAL
  record may leave any field MISSING_INPUT, and old experiments stay MISSING_INPUT until an artifact documents them.
- A correction is a new entry. A locked field may only change when the same entry adds a deviation naming that field;
  deviations only grow; the count of variants tested never falls; CONTAMINATED cannot be cleared without a deviation.

This module decides nothing, opens no file, adds no ledger row and approves nothing. Persistence is the caller's.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import factory  # noqa: E402
from research.tools import register_stats as rs  # noqa: E402

SCHEMA = "copybot.register_v2/1"
OK, MISSING_INPUT = rs.OK, rs.MISSING_INPUT
StatsError = rs.StatsError

FUTURE, HISTORICAL = "FUTURE", "HISTORICAL"
ERAS = (FUTURE, HISTORICAL)
DQ_STATUSES = ("VERIFIED", "DEGRADED", "CONTAMINATED", "NOT_CHECKED")

LOCKED = ("hypothesis_id", "lineage", "trial_universe", "parameters", "code_hash", "data_source", "data_period",
          "cost_model", "evaluation_method")
FIELDS = LOCKED + ("variants_tested", "data_quality", "deviations")
OPTIONAL = ("register_snapshot", "stats_ref")
AWAITS_RUN = ("variants_tested",)                # the only field a FUTURE record may leave open at registration

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEX64 = rs.HEX64
GENESIS = "0" * 64


def parameters_block(values):
    """The stored form of a parameter set: the values and the hash of exactly those values."""
    return {"values": copy.deepcopy(values), "sha256": factory.sha(values)}


def snapshot_sha(text):
    """sha256 of a snapshot file's content, as register_snapshot prints it (str or bytes)."""
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def record(record_id, era, **fields):
    """A validated V2 record. An omitted field, or one passed as None, is stored as MISSING_INPUT; nothing is defaulted."""
    unknown = [k for k in fields if k not in FIELDS + OPTIONAL]
    if unknown:
        raise StatsError(f"unknown field(s) {unknown}")
    rec = {"schema": SCHEMA, "record_id": record_id, "era": era}
    for k in FIELDS:
        value = fields.get(k)
        rec[k] = MISSING_INPUT if value is None else copy.deepcopy(value)
    for k in OPTIONAL:
        if fields.get(k) is not None:
            rec[k] = copy.deepcopy(fields[k])
    errors = validate(rec)
    if errors:
        raise StatsError("; ".join(errors))
    return rec


def _text(v):
    return isinstance(v, str) and bool(v.strip())


def _sha(v):
    return isinstance(v, str) and bool(HEX64.match(v))


def _date(v):
    if not isinstance(v, str) or not DATE.match(v):
        return False
    try:
        datetime.date.fromisoformat(v)
    except ValueError:
        return False
    return True


def _evidence(v):
    return isinstance(v, dict) and _text(v.get("artifact")) and _sha(v.get("sha256"))


def _check_universe(v):
    if not isinstance(v, dict) or not _text(v.get("definition")) or type(v.get("size")) is not int or v["size"] < 1 \
            or not _sha(v.get("members_sha256")):
        return "trial_universe needs {definition, size >= 1, members_sha256}"
    return None


def _check_variants(v):
    if not isinstance(v, dict) or type(v.get("count")) is not int or v["count"] < 1 or not _evidence(v):
        return "variants_tested needs {count >= 1, artifact, sha256}"
    return None


def _check_parameters(v):
    if not isinstance(v, dict) or not isinstance(v.get("values"), dict) or not _sha(v.get("sha256")):
        return "parameters needs {values, sha256}; use parameters_block"
    if factory.sha(v["values"]) != v["sha256"]:
        return "parameters.sha256 is not the hash of parameters.values"
    return None


def _check_code(v):
    if not isinstance(v, str) or not (HEX64.match(v) or rs.HEX_COMMIT.match(v)):
        return "code_hash must be a git commit or a sha256"
    return None


def _check_source(v):
    if not isinstance(v, dict) or not _text(v.get("name")) or not _sha(v.get("sha256")):
        return "data_source needs {name, sha256}"
    return None


def _check_period(v):
    if not isinstance(v, dict) or not _date(v.get("start")) or not _date(v.get("end")):
        return "data_period needs {start, end} as valid YYYY-MM-DD dates"
    if v["start"] > v["end"]:
        return "data_period.start is after data_period.end"
    return None


def _check_cost(v):
    if not isinstance(v, dict) or not _text(v.get("name")) or not _sha(v.get("sha256")) or \
            not rs._is_num(v.get("round_trip_bps")) or v["round_trip_bps"] < 0:
        return "cost_model needs {name, round_trip_bps >= 0, sha256}"
    return None


def _check_evaluation(v):
    if not isinstance(v, dict) or not _text(v.get("name")) or not _sha(v.get("sha256")):
        return "evaluation_method needs {name, sha256}"
    return None


def _check_quality(v):
    if not isinstance(v, dict) or v.get("status") not in DQ_STATUSES:
        return f"data_quality.status must be one of {DQ_STATUSES}"
    if v["status"] != "NOT_CHECKED" and not _evidence(v.get("evidence")):
        return "data_quality needs evidence {artifact, sha256} unless NOT_CHECKED"
    return None


def _check_deviations(v):
    if not isinstance(v, list):
        return "deviations must be a list ([] states that there are none)"
    for i, d in enumerate(v):
        if not isinstance(d, dict) or not _date(d.get("date")) or not _text(d.get("description")) or \
                not isinstance(d.get("fields"), list) or not d["fields"] or \
                any(f not in FIELDS for f in d["fields"]):
            return f"deviations[{i}] needs {{date, fields (known field names), description}}"
    return None


CHECKS = {"trial_universe": _check_universe, "variants_tested": _check_variants, "parameters": _check_parameters,
          "code_hash": _check_code, "data_source": _check_source, "data_period": _check_period, "cost_model": _check_cost,
          "evaluation_method": _check_evaluation, "data_quality": _check_quality, "deviations": _check_deviations}


def validate(rec):
    """List of errors (empty = valid)."""
    if not isinstance(rec, dict):
        return ["a record must be a dict"]
    e = []
    if rec.get("schema") != SCHEMA:
        e.append(f"schema must be {SCHEMA}")
    if not _text(rec.get("record_id")):
        e.append("record_id must be a non-empty string")
    if rec.get("era") not in ERAS:
        e.append(f"era must be one of {ERAS}")
    for k in rec:
        if k not in FIELDS + OPTIONAL and k not in ("schema", "record_id", "era"):
            e.append(f"unknown field {k!r}")
    for k in FIELDS:
        if k not in rec:
            e.append(f"{k} is absent: an undocumented field holds {MISSING_INPUT}")
            continue
        value = rec[k]
        if value == MISSING_INPUT:
            if rec.get("era") == FUTURE and k not in AWAITS_RUN:
                e.append(f"{k}: a FUTURE record must state this before the run")
        elif k in ("hypothesis_id", "lineage"):
            if not _text(value):
                e.append(f"{k} must be a non-empty string")
        else:
            problem = CHECKS[k](value)
            if problem:
                e.append(problem)
    for k in OPTIONAL:
        if k in rec and rec[k] is None:
            e.append(f"{k}: leave an absent pointer out, do not store None")
    snap = rec.get("register_snapshot")
    if snap is not None and (not isinstance(snap, dict) or not _sha(snap.get("sha256")) or
                             type(snap.get("rules_version")) is not int or snap["rules_version"] < 1):
        e.append("register_snapshot needs {sha256, rules_version >= 1}")
    ref = rec.get("stats_ref")
    if ref is not None and (not isinstance(ref, dict) or not _text(ref.get("record_id")) or not _sha(ref.get("entry_hash"))):
        e.append("stats_ref needs {record_id, entry_hash}")
    if not e:
        e.extend(_cross_checks(rec))
    return e


def _named_by_deviation(rec, field):
    return isinstance(rec["deviations"], list) and any(field in d["fields"] for d in rec["deviations"])


def _cross_checks(rec):
    tested, universe = rec["variants_tested"], rec["trial_universe"]
    if tested != MISSING_INPUT and universe != MISSING_INPUT and tested["count"] > universe["size"] and \
            not _named_by_deviation(rec, "trial_universe"):
        return [f"{tested['count']} variants tested exceeds the pre-registered universe of {universe['size']}; "
                "record a deviation naming trial_universe"]
    return []


def _revision_errors(prev, rec):
    """Rules for a new entry on an existing record id. prev and rec are valid records."""
    e = []
    if prev["era"] != rec["era"]:
        e.append("era cannot change")
    old, new = prev["deviations"], rec["deviations"]
    added = []
    if old != MISSING_INPUT:
        if new == MISSING_INPUT or new[:len(old)] != old:
            e.append("deviations only grow: earlier deviations cannot be changed or removed")
        else:
            added = new[len(old):]
    elif new != MISSING_INPUT:
        added = new
    named = {f for d in added for f in d["fields"]}
    for k in LOCKED:
        if prev[k] != MISSING_INPUT and prev[k] != rec[k] and k not in named:
            e.append(f"{k} changed after registration without a new deviation naming it")
    if prev["variants_tested"] != MISSING_INPUT:
        if rec["variants_tested"] == MISSING_INPUT:
            e.append("variants_tested cannot return to MISSING_INPUT")
        elif rec["variants_tested"]["count"] < prev["variants_tested"]["count"]:
            e.append("variants_tested cannot fall: every attempt keeps counting")
    was, now = prev["data_quality"], rec["data_quality"]
    if was != MISSING_INPUT and was["status"] == "CONTAMINATED" and \
            (now == MISSING_INPUT or now["status"] != "CONTAMINATED") and "data_quality" not in named:
        e.append("CONTAMINATED cannot be cleared without a new deviation naming data_quality")
    return e


def _latest(chain):
    out = {}
    for entry in chain:
        out[entry["record_id"]] = entry["record"]
    return out


def chain_append(chain, rec, ts):
    """Append a valid record to `chain` (a list, in memory). A correction is a new entry under the same record id."""
    errors = validate(rec)
    if errors:
        raise StatsError("; ".join(errors))
    if not _text(ts):
        raise StatsError("ts must be a non-empty string")
    prev = _latest(chain).get(rec["record_id"])
    if prev is not None:
        errors = _revision_errors(prev, rec)
        if errors:
            raise StatsError("; ".join(errors))
    entry = {"seq": len(chain), "record_id": rec["record_id"], "ts": ts, "record": copy.deepcopy(rec),
             "prev": chain[-1]["hash"] if chain else GENESIS}
    entry["hash"] = factory.sha(entry)
    chain.append(entry)
    return entry


def chain_verify(chain):
    """True, or StatsError naming the first broken entry: hash, link, record validity and the revision rules, replayed."""
    prev_hash, seen = GENESIS, {}
    for i, entry in enumerate(chain):
        body = {k: v for k, v in entry.items() if k != "hash"}
        if entry["seq"] != i or entry["prev"] != prev_hash or factory.sha(body) != entry["hash"] or \
                validate(entry["record"]) or entry["record_id"] != entry["record"]["record_id"]:
            raise StatsError(f"v2 chain broken at entry {i}")
        prev = seen.get(entry["record_id"])
        if prev is not None and _revision_errors(prev, entry["record"]):
            raise StatsError(f"v2 chain broken at entry {i}: revision rules")
        seen[entry["record_id"]] = entry["record"]
        prev_hash = entry["hash"]
    return True


def render_jsonl(chain):
    """The chain as text, one canonical entry per line. Writing it anywhere is the caller's."""
    return "".join(factory.canonical(e) + "\n" for e in chain)


def parse_jsonl(text):
    chain = [json.loads(line) for line in text.splitlines() if line.strip()]
    chain_verify(chain)
    return chain


def completeness(rec):
    """Which fields are still MISSING_INPUT."""
    missing = [k for k in FIELDS if rec[k] == MISSING_INPUT]
    return {"status": MISSING_INPUT if missing else OK, "missing": missing}


def historical_view(rows, chain=(), key="id"):
    """One item per register row, without touching it: the row's hash and every V2 field, MISSING_INPUT unless a V2
    record documents it. Ledger rows have no field `id`; join them with key="hash", the row's own chain hash."""
    latest = _latest(chain)
    out = []
    for row in rows:
        rec = latest.get(row.get(key))
        fields = {k: copy.deepcopy(rec[k]) if rec is not None else MISSING_INPUT for k in FIELDS}
        out.append({"record_id": row.get(key), "register_row_sha": factory.sha(row),
                    "status": completeness(fields)["status"], "fields": fields})
    return out


def snapshot_matches(rec, text):
    """Does the record point at exactly this snapshot file? No pointer gives MISSING_INPUT, not False."""
    snap = rec.get("register_snapshot")
    if snap is None:
        return {"status": MISSING_INPUT, "matches": None, "reason": "the record names no snapshot"}
    return {"status": OK, "matches": snap["sha256"] == snapshot_sha(text), "reason": None}


def stats_ref_matches(rec, stats_chain):
    """Does the record point at an entry that exists in a verified register_stats chain?"""
    ref = rec.get("stats_ref")
    if ref is None:
        return {"status": MISSING_INPUT, "matches": None, "reason": "the record names no stats entry"}
    rs.chain_verify(stats_chain)
    found = any(e["record_id"] == ref["record_id"] and e["hash"] == ref["entry_hash"] for e in stats_chain)
    return {"status": OK, "matches": found, "reason": None}


def validation_inputs(rec):
    """What validation_engine can read from a record. An undocumented value is None, so the engine says MISSING_INPUT."""
    def get(field, *path):
        value = rec[field]
        if value == MISSING_INPUT:
            return None
        for p in path:
            value = value[p]
        return value
    return {"n_tested": get("variants_tested", "count"), "n_preregistered": get("trial_universe", "size"),
            "assumed_cost_bps": get("cost_model", "round_trip_bps"),
            "declared_data_quality": get("data_quality", "status"), "data_period": get("data_period")}


__all__ = ["SCHEMA", "record", "validate", "chain_append", "chain_verify", "historical_view", "completeness",
           "parameters_block", "snapshot_sha", "snapshot_matches", "stats_ref_matches", "validation_inputs",
           "render_jsonl", "parse_jsonl", "MISSING_INPUT", "FUTURE", "HISTORICAL"]
