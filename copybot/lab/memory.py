"""Read-only research memory (`python3 -m lab research-memory`, research/LINUX_DRIFT.md 2026-10-23).

One learning record per decided hypothesis, from what the registry already holds: the locked measurements
(`research.measurement`), the catalogue and family experiments (`results`) and the amendment 17 screening. Each record
names its lock, data lineage, result, costs, reason and the fixed rule for what new evidence could justify a retest.
The retest rule is the same for every record of a kind; it is never a new criterion. It changes and decides nothing.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from lab import hypogen

RETEST = {
    "measurement": "only a new dated amendment with a forward window after the lock (2022-2023 used, 2024 holdout, "
                   "2025+ reserved)",
    "catalogue": "the catalogue is closed (amendment 8): only as a family with a non-price-predicting mechanism",
    "family": "the family's own forward cohort decides (amendment 8); no rerun on the screening windows",
    "legacy": "the recorded legacy or external result stands (imported before PROTOCOL v1); no rerun",
    "SCREEN_FAIL": "explore0 is used: none without new data",
    "UNTESTABLE": ">= 15 events with data in a phase the protocol allows",
    "SCREEN_PASS": "a LÅS-17 lock, then the locked measurement decides",
}


def _payloads(con, kind):
    for (raw,) in con.execute("SELECT payload FROM events WHERE kind=? ORDER BY id", (kind,)):
        yield json.loads(raw)


def _lineage(phase):
    files = phase.get("files") or []
    blob = "\n".join(sorted(f"{f.get('file')} {f.get('sha256')}" for f in files))
    return len(files), (hashlib.sha256(blob.encode()).hexdigest() if files else None)


def measurements(con):
    out = {}
    for p in _payloads(con, "research.measurement"):
        phases = {}
        for name, ph in (p.get("phases") or {}).items():
            n_files, sha = _lineage(ph)
            phases[name] = {"n": ph.get("n"), "mean": ph.get("mean"), "p": ph.get("p"), "files": n_files,
                            "files_sha256": sha}
        for name in ("train", "validation"):                             # H1-H5 record their splits directly
            v = p.get(name)
            if not phases.get(name) and isinstance(v, dict) and "n" in v:
                phases[v.get("split") or name] = {"n": v.get("n"), "mean": v.get("mean_Y", v.get("mean")),
                                                  "p": v.get("sign_flip_p", v.get("p")), "files": None,
                                                  "files_sha256": None}
        out[p.get("hypothesis")] = {
            "source": "measurement", "id": p.get("hypothesis"), "name": p.get("name"), "rule": p.get("rule"),
            "lock_sha256": p.get("draft_sha256"), "alpha": p.get("alpha"), "verdict": p.get("verdict"),
            "reason": p.get("reason"), "phases": phases,
            "decisional_for_trading": p.get("decisional_for_trading", False), "retest": RETEST["measurement"]}
    return list(out.values())                                             # the latest record per hypothesis


def _states(con):
    """The lifecycle state per experiment: a later human decision can override a result (E_vol_managed_long_p1:
    PASS (screen) recorded, then REJECTED by the user 2026-10-17)."""
    return {e: st for e, st in con.execute("SELECT exp_id, to_state FROM transitions t WHERE id = "
                                           "(SELECT MAX(id) FROM transitions WHERE exp_id = t.exp_id)")}


def experiments(con):
    out, states = [], _states(con)
    for exp_id, label, verdict, metrics in con.execute(
            "SELECT exp_id, label, verdict, metrics FROM results r WHERE id = (SELECT MAX(id) FROM results "
            "WHERE exp_id = r.exp_id) ORDER BY exp_id"):
        m = json.loads(metrics or "{}") if (metrics or "").startswith("{") else {}
        kind = "legacy" if label in ("LEGACY", "EXTERNAL") else "family" if exp_id.endswith("_a8") else "catalogue"
        out.append({"source": kind, "id": exp_id, "label": label, "state": states.get(exp_id), "template": m.get("template"),
                    "protocol_version": m.get("protocol_version"), "verdict": verdict, "failed": m.get("failed"),
                    "dsr": m.get("dsr"), "dsr_trials": m.get("dsr_trials"), "cost_model": m.get("cost_model"),
                    "retest": RETEST[kind]})
    return out


def screens(con, measured=None):
    """A screen pass that a locked measurement has since decided points to that decision, not to a lock it already
    had (research/LINUX_DRIFT.md 2026-10-23: four measured passes still read "a LÅS-17 lock, then ...")."""
    res, measured = {}, measured or {}
    for p in _payloads(con, hypogen.EV_SCREEN):
        res[p["key"]] = p
    out = []
    for k, p in sorted(res.items()):
        m = measured.get(k)
        out.append({"source": "screen", "id": k, "verdict": p.get("verdict"), "n": p.get("n"), "mean": p.get("mean"),
                    "p": p.get("p"), "excluded": p.get("excluded"),
                    "failed": [c for c, ok in (p.get("checks") or {}).items() if not ok] or None,
                    "measured": m,
                    "retest": (f"decided by its locked measurement: {m}; " + RETEST["measurement"]) if m else
                              RETEST.get(p.get("verdict"), RETEST["SCREEN_FAIL"])})
    return out


def memory(con):
    meas = measurements(con)
    return meas + experiments(con) + screens(con, {r["id"]: r["verdict"] for r in meas})


def main(db_path, out=print, json_path=None):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        recs = memory(con)
    finally:
        con.close()
    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, sort_keys=True, default=str) + "\n")
    meas = [r for r in recs if r["source"] == "measurement"]
    out(f"locked measurements {len(meas)}: PASS {sum(1 for r in meas if r['verdict'] == 'PASS')}, "
        f"REJECTED {sum(1 for r in meas if r['verdict'] == 'REJECTED')}")
    for r in meas:
        ph = "; ".join(f"{k} n={v['n']} mean={v['mean'] if v['mean'] is None else round(v['mean'], 4)} "
                       f"p={v['p'] if v['p'] is None else format(v['p'], '.2g')}" for k, v in r["phases"].items())
        out(f"  {r['id']}: {r['verdict']} ({r['reason']}) alpha {r['alpha']}"
            f"{' [not decisional for trading]' if not r['decisional_for_trading'] else ''}" + (f" | {ph}" if ph else ""))
    for kind in ("catalogue", "family", "legacy", "screen"):
        rs = [r for r in recs if r["source"] == kind]
        verdicts = {}
        for r in rs:
            v = r.get("state") or (r["verdict"] or "?").split(" ")[0].split(":")[0]   # the lifecycle state first
            verdicts[v] = verdicts.get(v, 0) + 1
        out(f"{kind} {len(rs)}: " + ", ".join(f"{v} {n}" for v, n in sorted(verdicts.items())))
    out("retest rules (fixed per kind, never a new criterion):")
    for k, v in RETEST.items():
        out(f"  {k}: {v}")
    if json_path:
        out(f"wrote {len(recs)} records to {json_path}")
    return 0
