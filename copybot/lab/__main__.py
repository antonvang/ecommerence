"""Command line for the research registry (run from copybot/):

  python -m lab init | import-legacy | status | show EXP | verify
  python -m lab discover EXP --hypothesis .. --mechanism .. --instrument .. --horizon .. --execution .. --source ..
  python -m lab add-version EXP --spec research/registry/EXP/SPEC.json     (committed file; complete spec)
  python -m lab approve EXP TO_STATE --reason ".." [--committed FILE ...]   -> prints a one-time code (15 min)
  python -m lab confirm CODE
  python -m lab transition EXP TO_STATE --reason ".." --result-id N         (automatic edges only)
  python -m lab result EXP --label EXPLORATORY --verdict ".." [--metrics JSON] [--supersedes ID --reason ..]
  python -m lab reproduce tsmom|pmcal|all                                  (S2 acceptance: dev results through the lab)
  python -m lab datasets [EXP]                                             (data read through the gateway)
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from lab import legacy, lifecycle, registry
from lab.data import AccessRefused
from lab.db import DB, DEFAULT_DB


def human():
    return "human:" + (getpass.getuser() or "unknown")


def main(argv=None, db_path=DEFAULT_DB, out=print):
    ap = argparse.ArgumentParser(prog="python -m lab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("import-legacy")
    sub.add_parser("status")
    sub.add_parser("verify")
    s = sub.add_parser("show"); s.add_argument("exp")
    d = sub.add_parser("discover"); d.add_argument("exp")
    for k in ("hypothesis", "mechanism", "instrument", "horizon", "execution", "source"):
        d.add_argument(f"--{k}", required=True)
    v = sub.add_parser("add-version"); v.add_argument("exp"); v.add_argument("--spec", required=True)
    a = sub.add_parser("approve"); a.add_argument("exp"); a.add_argument("to")
    a.add_argument("--reason", required=True); a.add_argument("--committed", nargs="*", default=[])
    c = sub.add_parser("confirm"); c.add_argument("code")
    t = sub.add_parser("transition"); t.add_argument("exp"); t.add_argument("to")
    t.add_argument("--reason", required=True); t.add_argument("--result-id", type=int)
    r = sub.add_parser("result"); r.add_argument("exp"); r.add_argument("--label", required=True)
    r.add_argument("--verdict", required=True); r.add_argument("--metrics", default="{}")
    r.add_argument("--supersedes", type=int); r.add_argument("--reason")
    rp = sub.add_parser("reproduce"); rp.add_argument("which", choices=("tsmom", "pmcal", "all"))
    ds = sub.add_parser("datasets"); ds.add_argument("exp", nargs="?")
    args = ap.parse_args(argv)
    db = DB(db_path)
    try:
        if args.cmd == "init":
            out(f"registry ready: {db_path}")
        elif args.cmd == "import-legacy":
            imp, skip = legacy.import_legacy(db)
            out(f"imported {len(imp)}, already present {len(skip)}")
        elif args.cmd == "status":
            rows = registry.status(db)
            for x in rows:
                out(f"{x['exp_id']:<30} {x['state'] or '-':<14} {x['label'] or '':<12} {x['verdict'] or ''}")
            counts = {}
            for x in rows:
                counts[x["state"]] = counts.get(x["state"], 0) + 1
            out("states: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        elif args.cmd == "show":
            e = registry.latest(db, args.exp)
            if e is None:
                out(f"{args.exp}: not found")
                return 1
            out(json.dumps({"exp_id": e["exp_id"], "version": e["version"], "mechanism": e["mechanism_tag"],
                            "state": lifecycle.state(db, args.exp), "spec": json.loads(e["spec_json"] or "{}"),
                            "spec_path": e["spec_path"], "spec_commit": e["spec_commit"], "code_hash": e["code_hash"]},
                           indent=1, ensure_ascii=False))
            for tr in db.q("SELECT ts, from_state, to_state, actor, reason FROM transitions WHERE exp_id=? ORDER BY id",
                           args.exp):
                out(f"  {tr['ts']} {tr['from_state']} -> {tr['to_state']} by {tr['actor']}: {tr['reason']}")
            for rs in db.q("SELECT id, label, verdict, supersedes FROM results WHERE exp_id=? ORDER BY id", args.exp):
                out(f"  result #{rs['id']} [{rs['label']}] {rs['verdict']}"
                    + (f" (supersedes #{rs['supersedes']})" if rs["supersedes"] else ""))
        elif args.cmd == "verify":
            chains, triggers = db.verify()
            bad_ev = legacy.verify_evidence(db)
            ok = triggers and all(b is None for _, b in chains.values()) and not bad_ev
            for tname, (n, b) in chains.items():
                out(f"{tname:<13} rows {n:<6} {'OK' if b is None else f'BROKEN at id {b}'}")
            out(f"append-only triggers: {'present' if triggers else 'MISSING'}")
            out(f"cited evidence: {'all resolve in git' if not bad_ev else bad_ev}")
            out("VERIFY OK" if ok else "VERIFY FAILED")
            return 0 if ok else 2
        elif args.cmd == "discover":
            st, dup = registry.discover(db, args.exp, args.hypothesis, args.mechanism, args.instrument, args.horizon,
                                        args.execution, args.source, human())
            out(f"{args.exp}: {st}" + (f" (matches rejected: {', '.join(dup)})" if dup else ""))
        elif args.cmd == "add-version":
            out(f"{args.exp}: version {registry.add_version(db, args.exp, args.spec, human())} added")
        elif args.cmd == "approve":
            code = lifecycle.request_approval(db, args.exp, args.to, human(), args.reason,
                                              {"committed_files": args.committed} if args.committed else None,
                                              guards=(registry.complete_spec_guard,))
            out(f"approval code for {args.exp} -> {args.to}: {code}   (confirm within 15 minutes: python -m lab confirm {code})")
        elif args.cmd == "confirm":
            exp, to = lifecycle.confirm(db, args.code, human(), guards=(registry.complete_spec_guard,))
            out(f"{exp} -> {to}")
        elif args.cmd == "transition":
            ev = {"result_id": args.result_id} if args.result_id is not None else None
            lifecycle.auto_transition(db, args.exp, args.to, "system:cli", args.reason, ev,
                                      guards=(registry.make_result_guard(ev),))
            out(f"{args.exp} -> {args.to}")
        elif args.cmd == "result":
            rid = registry.record_result(db, args.exp, args.label, args.verdict, json.loads(args.metrics), {},
                                         human(), args.supersedes, args.reason)
            out(f"result #{rid} recorded")
        elif args.cmd == "reproduce":
            from lab import repro
            ok = True
            for name, fn in (("tsmom", repro.reproduce_tsmom), ("pmcal", repro.reproduce_pmcal)):
                if args.which in (name, "all"):
                    r = fn(db)
                    ok &= r["ok"]
                    out(f"{r['exp_id']}: {r['fields'] - len(r['mismatches'])}/{r['fields']} fields match"
                        + ("" if r["ok"] else f"; MISMATCH: {[m['field'] for m in r['mismatches']]}"))
            out("REPRODUCED EXACTLY" if ok else "REPRODUCTION FAILED")
            return 0 if ok else 2
        elif args.cmd == "datasets":
            q = "SELECT exp_id, split, purpose, path, sha256, size FROM datasets" + (" WHERE exp_id=?" if args.exp else "")
            for r in db.q(q + " ORDER BY id", *([args.exp] if args.exp else [])):
                out(f"{r['exp_id']:<16} {r['split']:<10} {r['purpose']:<9} {r['sha256'][:12]} {r['size']:>10} {r['path']}")
        return 0
    except (lifecycle.LifecycleError, registry.RegistryError, AccessRefused) as e:
        out(f"refused: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
