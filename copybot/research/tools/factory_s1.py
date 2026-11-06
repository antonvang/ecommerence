"""Director order 49 P0: S1 — isolated, read-only shadow job of the research factory.

What it does, each run: open the lab database READ-ONLY (`mode=ro` + `PRAGMA query_only=ON`), replay every lab
transition through the factory's rules (research/tools/factory_shadow.py, same classes as the order 47 P3 replay),
and append the decision for each transition it has not seen before to its own report. The lab performed every
transition, so the lab's decision is ALLOW; the factory's is ALLOW or BLOCK with reason codes.

Isolation (tested in tests/test_research_factory_s1.py):
- writes only under its own directory (default research/data/factory_s1/): decisions.jsonl (append-only, hash-chained),
  state.json (last transition id, baseline), summary.md, errors.jsonl;
- never writes the lab database, the ledger, approvals or research status; never touches paper books, collectors,
  forward tests or pm_lp; it is not part of the lab pipeline and not a service: it runs only when invoked (the
  assistant's hourly check runs it);
- resource limits: address space 1 GiB, CPU 120 s per run;
- stop: a file named STOP in its directory makes every run exit immediately (exit code 3) without reading anything;
  an error stops only this run (recorded in errors.jsonl, exit code 2); the lab is never affected.

The first run records the BASELINE (all transitions that existed at S1 start) separately from later observations; the
14-day observation period of order 49 P3 counts from the documented start time.

    python3 research/tools/factory_s1.py [--db PATH] [--dir DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import factory_shadow as fs  # noqa: E402

DIR = os.path.join(HERE, "research", "data", "factory_s1")
S1_VERSION = 1
MEM_LIMIT = 1 << 30
CPU_LIMIT = 120


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def limit_resources():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT, CPU_LIMIT))
    except Exception:                       # noqa: BLE001 - limits are best effort on platforms without them
        pass


def open_ro(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def verify_chain(entries):
    prev = "0" * 64
    for i, e in enumerate(entries):
        body = {k: v for k, v in e.items() if k != "hash"}
        if e.get("prev") != prev or hashlib.sha256(canonical(body).encode()).hexdigest() != e.get("hash"):
            raise RuntimeError(f"decisions.jsonl broken at entry {i}")
        prev = e["hash"]
    return prev


def protocol_versions(con):
    out = {}
    for exp, sj in con.execute("SELECT exp_id, spec_json FROM experiments e WHERE version=(SELECT MAX(version) "
                               "FROM experiments WHERE exp_id=e.exp_id)"):
        try:
            out[exp] = json.loads(sj or "{}").get("protocol_version")
        except ValueError:
            out[exp] = None
    return out


def run(db, d=DIR, now=None):
    """One S1 run. Returns (exit_code, info)."""
    now = int(now if now is not None else time.time())
    if os.path.exists(os.path.join(d, "STOP")):
        return 3, {"stopped": True}
    os.makedirs(d, exist_ok=True)
    dec_path, state_path = os.path.join(d, "decisions.jsonl"), os.path.join(d, "state.json")
    try:
        entries = _read_jsonl(dec_path)
        prev = verify_chain(entries)
        state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else None
        con = open_ro(db)
        shadow = fs.pipeline_shadow(con)
        pv = protocol_versions(con)
        con.close()
        rows = shadow["rows"]
        first = state is None
        last_id = -1 if first else state["last_transition_id"]
        new = [r for r in rows if r["id"] > last_id]
        phase = "BASELINE" if first else "OBSERVATION"
        with open(dec_path, "a", encoding="utf-8") as f:
            for r in new:
                e = {"s1_version": S1_VERSION, "run_ts": now, "phase": phase, "transition_id": r["id"],
                     "exp_id": r["exp_id"], "from": r["from"], "to": r["to"], "lab": r["lab"],
                     "factory": r["factory"], "reasons": r["classes"], "protocol_version": pv.get(r["exp_id"]),
                     "unexplained": "UNEXPLAINED" in r["classes"], "prev": prev}
                e["hash"] = hashlib.sha256(canonical(e).encode()).hexdigest()
                prev = e["hash"]
                f.write(canonical(e) + "\n")
        state = {"s1_version": S1_VERSION, "started_ts": now if first else state["started_ts"],
                 "baseline_transitions": len(new) if first else state["baseline_transitions"],
                 "baseline_last_id": (max((r["id"] for r in new), default=-1) if first
                                      else state["baseline_last_id"]),
                 "last_transition_id": max([last_id] + [r["id"] for r in new]), "last_run_ts": now,
                 "runs": (0 if first else state["runs"]) + 1, "chain_head": prev}
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, sort_keys=True, indent=1)
        os.replace(tmp, state_path)
        _log_run(d, now, 0, len(new))
        write_summary(d, state, _read_jsonl(dec_path), now)
        return 0, {"new": len(new), "phase": phase, "state": state}
    except Exception as e:                  # noqa: BLE001 - stop only this run, record it, never touch the lab
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "errors.jsonl"), "a", encoding="utf-8") as f:
            f.write(canonical({"ts": now, "error": f"{type(e).__name__}: {e}"}) + "\n")
        _log_run(d, now, 2, 0)
        return 2, {"error": str(e)}


GAP_S = 2 * 3600        # the check runs hourly; more than 2 h without a successful run is a MONITORING_GAP


def _log_run(d, now, code, new):
    with open(os.path.join(d, "runs.jsonl"), "a", encoding="utf-8") as f:
        f.write(canonical({"ts": now, "exit": code, "new": new}) + "\n")


def coverage(runs, started, now):
    """Monitoring coverage: expected hourly runs since the start, successful runs, longest gap and every gap longer
    than GAP_S (MONITORING_GAP), including the open gap up to `now`."""
    ok = sorted(r["ts"] for r in runs if r["exit"] == 0)
    points = [started] + [t for t in ok if t >= started] + [now]
    gaps = [(a, b) for a, b in zip(points, points[1:]) if b - a > GAP_S]
    longest = max((b - a for a, b in zip(points, points[1:])), default=0)
    return {"expected_runs": int((now - started) // 3600) + 1, "successful_runs": len(ok),
            "failed_runs": sum(r["exit"] != 0 for r in runs), "longest_gap_s": longest,
            "monitoring_gaps": [{"from": a, "to": b, "hours": round((b - a) / 3600, 2)} for a, b in gaps]}


def write_summary(d, state, entries, now=None):
    obs = [e for e in entries if e["phase"] == "OBSERVATION"]
    base = [e for e in entries if e["phase"] == "BASELINE"]

    def tally(es):
        t = {}
        for e in es:
            for c in e["reasons"] or ["-"]:
                k = f"{e['factory']}:{c}"
                t[k] = t.get(k, 0) + 1
        return dict(sorted(t.items()))
    started = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(state["started_ts"]))
    L = ["# Factory S1 shadow report (director order 49)", "",
         f"S1 started {started}; runs {state['runs']}; last run "
         f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(state['last_run_ts']))}; chain head `{state['chain_head']}`.",
         "", f"Baseline: {len(base)} transitions (all that existed at S1 start; not observations).",
         f"Observation period (order 49 P3 counts 14 full days from the start): {len(obs)} new transitions, "
         f"{sum(e['unexplained'] for e in obs)} unexplained, {sum(e['factory'] == 'BLOCK' for e in obs)} BLOCK.", ""]
    cov = coverage(_read_jsonl(os.path.join(d, "runs.jsonl")), state["started_ts"], now or state["last_run_ts"])
    L += [f"Monitoring coverage: {cov['successful_runs']} successful runs over {cov['expected_runs']} elapsed hourly "
          f"slots, "
          f"{cov['failed_runs']} failed; longest gap {cov['longest_gap_s'] / 3600:.2f} h; MONITORING_GAP periods "
          f"(> {GAP_S // 3600} h): {len(cov['monitoring_gaps'])}."]
    L += [f"- MONITORING_GAP {time.strftime('%Y-%m-%d %H:%M', time.gmtime(g['from']))} -> "
          f"{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(g['to']))} ({g['hours']} h)" for g in cov["monitoring_gaps"]]
    L += ["", "Event coverage: few new transitions mean INSUFFICIENT_OBSERVATION at the evaluation, never an automatic "
          "PASS.", "",
         "| Phase | Factory decision : reason | Count |", "|---|---|---|"]
    L += [f"| BASELINE | {k} | {v} |" for k, v in tally(base).items()]
    L += [f"| OBSERVATION | {k} | {v} |" for k, v in tally(obs).items()]
    with open(os.path.join(d, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "lab", "lab.db"))
    ap.add_argument("--dir", default=DIR)
    a = ap.parse_args(argv)
    limit_resources()
    code, info = run(a.db, a.dir)
    print(code, json.dumps(info, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
