"""Director order 47 P0: the research factory's register and multiple-testing ledger (research/reviews/INBOX.md).

It sits ON TOP of the existing pipeline and never replaces it: the lab's experiments, transitions, trials, alpha
ledger, approvals and datasets (lab/db.py), the amendment-17 hypothesis pipeline (events research.hypothesis*) and
the exploration lane (events research.explore) stay the source of truth. This module

1. maps every lab experiment onto one factory record with the order's fields and status vocabulary
   (PROPOSED -> APPROVED -> FROZEN -> TESTED -> REJECTED / INCONCLUSIVE / VALIDATED, plus CLOSED and EXTERNAL);
2. groups hypotheses into lineages (connected components of the `related` graph in research/families/VOCABULARY.json),
   so a renamed idea or a new parameter variant keeps counting against the same lineage;
3. keeps an append-only multiple-testing ledger in which every attempt counts, alpha is never refunded and a
   rejected hypothesis cannot be tested again under its own id;
4. enforces the state machine for NEW factory records (synthetic tests): approval only by a human actor, freezing only
   with a complete pre-registration and dataset hashes, testing only after a ledger charge made after the freeze and
   with unchanged data, and no protected window (2024 holdout; COIN-M before 2026-11-28).

Read-only against the lab database (`mode=ro`). It opens no market data, approves nothing (approve-template stays the
owner's) and promotes nothing to paper trading.

    python3 research/tools/factory.py [--db PATH] [--out DIR]     # snapshot -> research/data/factory/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # copybot/
VOCAB = os.path.join(HERE, "research", "families", "VOCABULARY.json")
OUT = os.path.join(HERE, "research", "data", "factory")

STATUSES = ("PROPOSED", "APPROVED", "FROZEN", "TESTED", "REJECTED", "INCONCLUSIVE", "VALIDATED", "CLOSED", "EXTERNAL")
FINAL = {"REJECTED", "VALIDATED", "CLOSED"}
VERDICTS = {"REJECTED", "INCONCLUSIVE", "VALIDATED"}
EDGES = {("PROPOSED", "APPROVED"), ("PROPOSED", "CLOSED"), ("APPROVED", "FROZEN"), ("APPROVED", "CLOSED"),
         ("FROZEN", "TESTED"), ("TESTED", "REJECTED"), ("TESTED", "INCONCLUSIVE"), ("TESTED", "VALIDATED"),
         ("INCONCLUSIVE", "TESTED")}      # an inconclusive result may be tested again, but only with a new charge

# lab lifecycle state (lab/lifecycle.py STATES) -> factory status
LAB_MAP = {"DISCOVERED": "PROPOSED", "SUPPRESSED": "PROPOSED", "REGISTERED": "APPROVED", "SCREENING": "FROZEN",
           "SCREEN_PASSED": "TESTED", "VALIDATION": "TESTED", "OBSERVATION": "INCONCLUSIVE",
           "VALIDATED": "VALIDATED", "PAPER_TRADING": "VALIDATED", "PAUSED": "VALIDATED", "REJECTED": "REJECTED",
           "WITHDRAWN": "CLOSED", "RETIRED": "CLOSED", "EXTERNAL": "EXTERNAL"}

PREREG = ("family", "mechanism", "direction", "universe", "windows", "sources", "datasets", "parameter_family",
          "estimand", "benchmark", "cost_model", "rejection", "spec_commit")

HOLDOUT = (int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()),
           int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()))
COINM_FROM = int(datetime(2026, 11, 28, tzinfo=timezone.utc).timestamp())


class FactoryError(Exception):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


# ---------------------------------------------------------------- lineages

def lineages(vocab):
    """tag -> lineage id: connected components of the vocabulary's `related` graph (undirected); the id is the
    alphabetically first tag of the component."""
    tags = vocab.get("tags", {})
    parent = {t: t for t in tags}

    def find(t):
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    for t, d in tags.items():
        for r in d.get("related", []):
            parent.setdefault(r, r)
            a, b = find(t), find(r)
            if a != b:
                parent[max(a, b)] = min(a, b)
    return {t: find(t) for t in parent}


def lineage_of(tag, lmap):
    """Lineage of a mechanism tag; a tag outside the vocabulary is its own lineage and is flagged."""
    if tag in lmap:
        return lmap[tag], True
    return tag or "UNTAGGED", False


# ---------------------------------------------------------------- ledger

class Ledger:
    """Append-only multiple-testing ledger. Every attempt is an entry; nothing is removed or refunded."""

    def __init__(self):
        self.entries = []

    def charge(self, hid, lineage, ts, variants, alpha, source, note=""):
        if not isinstance(variants, int) or variants < 1:
            raise FactoryError("every attempt tests at least one variant")
        if alpha < 0:
            raise FactoryError("alpha is never refunded")
        e = {"seq": len(self.entries), "hid": hid, "lineage": lineage, "ts": ts, "variants": variants,
             "alpha": alpha, "source": source, "note": note}
        e["prev"] = self.entries[-1]["hash"] if self.entries else "0" * 64
        e["hash"] = sha({k: v for k, v in e.items() if k != "hash"})
        self.entries.append(e)
        return e

    def verify(self):
        prev = "0" * 64
        for i, e in enumerate(self.entries):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e["seq"] != i or e["prev"] != prev or sha(body) != e["hash"]:
                raise FactoryError(f"ledger broken at entry {i}")
            prev = e["hash"]
        return True

    def charges(self, hid, since=None):
        return [e for e in self.entries if e["hid"] == hid and (since is None or e["ts"] >= since)]

    def totals(self):
        out = {}
        for e in self.entries:
            t = out.setdefault(e["lineage"], {"attempts": 0, "variants": 0, "alpha": 0.0, "hypotheses": set()})
            t["attempts"] += 1
            t["variants"] += e["variants"]
            t["alpha"] += e["alpha"]
            t["hypotheses"].add(e["hid"])
        return {k: {**v, "hypotheses": len(v["hypotheses"])} for k, v in sorted(out.items())}


# ---------------------------------------------------------------- register (new factory records)

def fingerprint(rec):
    """Identity of a hypothesis: mechanism tag, direction, universe and estimand. A new name with the same
    fingerprint is the same hypothesis."""
    return sha([rec.get("mechanism_tag"), rec.get("direction"), sorted(rec.get("universe") or []), rec.get("estimand")])


def protected(datasets, now):
    """Reasons a dataset list touches a protected window (2024 holdout; COIN-M before 2026-11-28)."""
    bad = []
    for d in datasets or []:
        s, e = d.get("window_start"), d.get("window_end")
        if s is not None and e is not None and s < HOLDOUT[1] and e > HOLDOUT[0]:
            bad.append(f"{d.get('path')}: overlaps the 2024 holdout")
        if "coin-m" in str(d.get("source", "")).lower() and now < COINM_FROM:
            bad.append(f"{d.get('path')}: COIN-M before 2026-11-28")
    return bad


class Register:
    def __init__(self, ledger, lmap):
        self.ledger, self.lmap, self.recs, self.log = ledger, lmap, {}, []

    def propose(self, hid, rec, ts):
        if hid in self.recs:
            raise FactoryError(f"{hid} exists")
        fp = fingerprint(rec)
        for other, r in self.recs.items():
            if r["fingerprint"] == fp:
                raise FactoryError(f"same hypothesis as {other} (fingerprint); a new name does not reset its budget")
        lin, known = lineage_of(rec.get("mechanism_tag"), self.lmap)
        self.recs[hid] = {**rec, "id": hid, "status": "PROPOSED", "fingerprint": fp, "lineage": lin,
                          "lineage_known": known, "history": [("PROPOSED", ts, None)]}
        return self.recs[hid]

    def move(self, hid, to, ts, evidence=None):
        r = self.recs.get(hid)
        if r is None:
            raise FactoryError(f"{hid} does not exist")
        cur, ev = r["status"], evidence or {}
        if cur in FINAL:
            raise FactoryError(f"{hid} is {cur} (final); a revived idea is a new hypothesis in the same lineage")
        if (cur, to) not in EDGES:
            raise FactoryError(f"transition {cur} -> {to} is not allowed")
        if to == "APPROVED" and not str(ev.get("actor", "")).startswith("human:"):
            raise FactoryError("approval needs a human actor (approve-template stays the owner's)")
        if to == "FROZEN":
            missing = [k for k in PREREG if not r.get(k)]
            if missing:
                raise FactoryError(f"pre-registration incomplete: {missing}")
            if any(not d.get("sha256") for d in r["datasets"]):
                raise FactoryError("every dataset needs a sha256 before freezing")
            bad = protected(r["datasets"], ts)
            if bad:
                raise FactoryError(f"protected data: {bad}")
            r["frozen"] = {"ts": ts, "datasets": sha(r["datasets"]), "prereg": sha({k: r[k] for k in PREREG})}
        if to == "TESTED":
            last = max(t for s, t, _ in r["history"] if s in ("FROZEN", "TESTED", "INCONCLUSIVE"))
            if not self.ledger.charges(hid, since=last):
                raise FactoryError("no ledger charge for this attempt (every attempt counts)")
            if sha(ev.get("datasets", r["datasets"])) != r["frozen"]["datasets"]:
                raise FactoryError("data changed after the lock")
            if sha({k: r[k] for k in PREREG}) != r["frozen"]["prereg"]:
                raise FactoryError("pre-registration changed after the lock")
            if protected(ev.get("datasets", r["datasets"]), ts):
                raise FactoryError("protected data")
        if to == "VALIDATED" and ev.get("promote_to_paper"):
            raise FactoryError("the factory never promotes to paper trading")
        r["status"] = to
        r["history"].append((to, ts, ev.get("actor")))
        self.log.append((hid, cur, to, ts))
        return r


# ---------------------------------------------------------------- snapshot of the existing lab

def _q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def snapshot(con, vocab, offdb):
    """Factory view of the lab database (read-only connection) plus the off-database studies list."""
    lmap = lineages(vocab)
    exps = {}
    for exp_id, ver, tag, spec_json, spec_path, spec_commit, created in _q(
            con, "SELECT exp_id, version, mechanism_tag, spec_json, spec_path, spec_commit, created_ts FROM experiments e "
                 "WHERE version=(SELECT MAX(version) FROM experiments WHERE exp_id=e.exp_id) ORDER BY exp_id"):
        spec = json.loads(spec_json or "{}")
        exps[exp_id] = {"id": exp_id, "version": ver, "mechanism_tag": tag, "spec_path": spec_path,
                        "spec_commit": spec_commit, "created_ts": created, "spec_keys": sorted(spec)}
    for exp_id, st in _q(con, "SELECT exp_id, to_state FROM transitions t WHERE id=(SELECT MAX(id) FROM transitions "
                              "WHERE exp_id=t.exp_id)"):
        if exp_id in exps:
            exps[exp_id]["lab_state"] = st
    trials = {}
    for exp_id, split, n in _q(con, "SELECT exp_id, split, COUNT(*) FROM trials GROUP BY exp_id, split"):
        trials.setdefault(exp_id, {})[split] = n
    datasets = {e: (n, k) for e, n, k in _q(con, "SELECT exp_id, COUNT(*), COUNT(DISTINCT sha256) FROM datasets "
                                                 "GROUP BY exp_id")}
    results = {e: n for e, n in _q(con, "SELECT exp_id, COUNT(*) FROM results GROUP BY exp_id")}
    alpha_pos, alpha_neg = {}, {}
    for exp_id, a in _q(con, "SELECT exp_id, alpha FROM alpha_ledger ORDER BY id"):
        d = alpha_pos if a >= 0 else alpha_neg
        d[exp_id] = d.get(exp_id, 0.0) + a

    ledger = Ledger()
    records = []
    for exp_id, e in exps.items():
        lin, known = lineage_of(e["mechanism_tag"], lmap)
        lab_state = e.get("lab_state")
        n_trials = sum(trials.get(exp_id, {}).values())
        rec = {**e, "status": LAB_MAP.get(lab_state, "UNKNOWN"), "lineage": lin, "lineage_known": known,
               "trials": n_trials, "datasets": datasets.get(exp_id, (0, 0))[0],
               "dataset_hashes": datasets.get(exp_id, (0, 0))[1], "results": results.get(exp_id, 0),
               "alpha_spent": round(alpha_pos.get(exp_id, 0.0), 10)}
        records.append(rec)
        tested = rec["status"] in ("TESTED", "REJECTED", "INCONCLUSIVE", "VALIDATED")
        if n_trials or alpha_pos.get(exp_id) or tested:
            note = "trials table + alpha_ledger" if (n_trials or alpha_pos.get(exp_id)) else \
                "tested but no trials/alpha rows (legacy): counted as 1 attempt, a lower bound"
            ledger.charge(exp_id, lin, e["created_ts"] or 0, max(n_trials, 1), alpha_pos.get(exp_id, 0.0), "lab", note)
    # family-level alpha rows that are not experiments (e.g. family:fcarry allocations and offsets)
    family_alpha = {k: round(v, 10) for k, v in sorted({**alpha_pos, **alpha_neg}.items()) if k not in exps}
    offsets = {k: round(v, 10) for k, v in sorted(alpha_neg.items())}

    hyp = {}
    for kind, payload in _q(con, "SELECT kind, payload FROM events WHERE kind IN ('research.hypothesis', "
                                 "'research.hypothesis_screen', 'research.measurement') ORDER BY id"):
        p = json.loads(payload or "{}")
        key = p.get("key") or p.get("hypothesis") or "?"
        h = hyp.setdefault(key, {"key": key, "candidate": 0, "screens": 0, "measurements": 0, "alpha": 0.0,
                                 "type": p.get("type")})
        if kind == "research.hypothesis":
            h["candidate"] += 1
        elif kind == "research.hypothesis_screen":
            h["screens"] += 1
        else:
            h["measurements"] += 1
            h["alpha"] += float(p.get("alpha") or 0)
    for key, h in sorted(hyp.items()):
        attempts = h["screens"] + h["measurements"]
        if attempts:
            ledger.charge(key, f"m17:{h['type'] or key.split('|')[0]}", 0, attempts, h["alpha"], "amendment 17",
                          "screens are exploratory (never evidence) but still count as attempts")
    explore_runs = _q(con, "SELECT COUNT(*) FROM events WHERE kind='research.explore'")[0][0]
    seen = set()
    for (payload,) in _q(con, "SELECT payload FROM events WHERE kind='research.explore'"):
        seen.update(json.loads(payload or "{}").get("candidates") or [])
    explore_candidates = len(seen)            # unique candidates; a candidate proposed in many runs counts once
    if explore_candidates:
        ledger.charge("explore0", "explore0", 0, explore_candidates, 0.0, "exploration lane",
                      "explore0 window only; never evidence; counted so breadth stays visible")
    for s in offdb:
        if s.get("attempts"):
            ledger.charge(s["id"], s.get("lineage") or s["id"], 0, int(s["attempts"]), float(s.get("alpha") or 0),
                          "off-database study", s.get("note", ""))
    ledger.verify()

    gaps = {
        "unknown_lab_state": sorted(r["id"] for r in records if r["status"] == "UNKNOWN"),
        "tag_outside_vocabulary": sorted({r["mechanism_tag"] for r in records if not r["lineage_known"]}),
        "tested_without_trials_or_alpha (counted as 1 attempt)": sorted(r["id"] for r in records
                                                 if r["status"] in ("TESTED", "REJECTED", "INCONCLUSIVE", "VALIDATED")
                                                 and not r["trials"] and not r["alpha_spent"]),
        "offdb_unknown_fields": sorted(s["id"] for s in offdb if any(v is None for v in s.values())),
    }
    by_status = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    members = {}
    for t, root in lmap.items():
        members.setdefault(root, []).append(t)
    return {"schema": "copybot.factory/1", "lineage_members": {k: sorted(v) for k, v in sorted(members.items())
                                                                if len(v) > 1}, "rule": "research/reviews/INBOX.md director order 47 P0",
            "records": records, "by_status": dict(sorted(by_status.items())),
            "hypothesis_pipeline": sorted(hyp.values(), key=lambda h: h["key"]),
            "exploration": {"runs": explore_runs, "candidates": explore_candidates},
            "offdb_studies": offdb, "family_alpha_rows": family_alpha, "alpha_offsets": offsets,
            "ledger": {"entries": ledger.entries, "lineages": ledger.totals(),
                       "attempts": len(ledger.entries), "variants": sum(e["variants"] for e in ledger.entries),
                       "alpha_gross": round(sum(e["alpha"] for e in ledger.entries), 10)},
            "gaps": gaps}


def md(rep, digest):
    L = ["# Factory register (director order 47 P0) — snapshot", "",
         f"Generated by `research/tools/factory.py`; data `research/data/factory/registry.json` (sha256 `{digest}`).",
         "Read-only view on top of the lab; the lab database stays the source of truth.", "",
         "## Status (lab experiments mapped to the factory vocabulary)", "", "| Status | Count |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in rep["by_status"].items()]
    lg = rep["ledger"]
    L += ["", "## Multiple-testing ledger", "",
          f"Attempts {lg['attempts']}, variants {lg['variants']}, gross alpha charged {lg['alpha_gross']:.6f}. "
          "Every attempt counts (screens, exploration and off-database studies included); nothing is refunded.", "",
          "| Lineage | Hypotheses | Attempts | Variants | Alpha |", "|---|---|---|---|---|"]
    for k, v in sorted(lg["lineages"].items(), key=lambda kv: (-kv[1]["variants"], kv[0])):
        L.append(f"| {k} | {v['hypotheses']} | {v['attempts']} | {v['variants']} | {v['alpha']:.6f} |")
    L += ["", "Lineages with several tags (a lineage is named after its alphabetically first tag):", ""]
    L += [f"- {k}: {', '.join(v)}" for k, v in rep["lineage_members"].items()]
    L += ["", f"Exploration lane: {rep['exploration']['runs']} runs, {rep['exploration']['candidates']} unique "
          "candidates (explore0 only, never evidence).", "",
          "Amendment-17 measurements (m17:H1-H5) are the MAALING 14a/16a/16c studies; the off-database inventory must "
          "not count them twice.", "",
          f"Family-level alpha rows (not experiments): `{canonical(rep['family_alpha_rows'])}`. Negative rows in the lab's "
          f"alpha_ledger (offsets, reported, not refunds in the factory ledger): `{canonical(rep['alpha_offsets'])}`.", "",
          "## Gaps (UNKNOWN until closed)", ""]
    for k, v in rep["gaps"].items():
        L.append(f"- {k}: {len(v)}" + (f" — {', '.join(map(str, v[:12]))}{' …' if len(v) > 12 else ''}" if v else ""))
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "lab", "lab.db"))
    ap.add_argument("--offdb", default=os.path.join(OUT, "offdb_studies.json"))
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    with open(VOCAB, encoding="utf-8") as f:
        vocab = json.load(f)
    offdb = []
    if os.path.exists(a.offdb):
        with open(a.offdb, encoding="utf-8") as f:
            offdb = json.load(f)["studies"]
    rep = snapshot(con, vocab, offdb)
    os.makedirs(a.out, exist_ok=True)
    body = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    with open(os.path.join(a.out, "registry.json"), "w", encoding="utf-8") as f:
        f.write(body)
    with open(os.path.join(a.out, "registry.md"), "w", encoding="utf-8") as f:
        f.write(md(rep, digest))
    print(digest, rep["by_status"], rep["ledger"]["attempts"], rep["ledger"]["variants"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
