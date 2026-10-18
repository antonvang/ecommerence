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
  python -m lab scan [--detector venue_subsidy|pricing_constraint]         (read-only public data; candidates only)
  python -m lab candidates                                                 (discovered, suppressed, covered, seen again)
  python -m lab supervise [--duration S] [--worker module:factory ...] [--no-default]   (manual start only)
  python -m lab health                                                     (heartbeats, FAIL_CLOSED, pauses, warm-up)
  python -m lab web [--port 8770] [--duration S]                           (dashboard on 127.0.0.1; manual start only)
  python -m lab gate [--require]                                           (S7 automation gate: 7 days of clean operation)
  python -m lab fleet [--duration S]                                       (research agent fleet under the supervisor; manual)
  python -m lab pause|resume|stop --reason ".."                           (fleet control, logged in the event chain)
  python -m lab jobs [--status S]                                          (persistent job queue)
  python -m lab approve-template TEMPLATE --reason ".."  -> code;  python -m lab confirm-template CODE
  python -m lab revoke-template TEMPLATE --reason ".."
  python -m lab shadow-start EXP --reason ".." | shadow-stop EXP --reason ".."   (simulated shadow ledger, OBSERVATION only)
  python -m lab autopromote on|off --reason ".."                         (automatic promotion policy, amendment 4)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from lab import legacy, lifecycle, registry
from lab.data import AccessRefused
from lab.db import DB, DEFAULT_DB


def human():
    return "human:" + (getpass.getuser() or "unknown")


def main(argv=None, db_path=DEFAULT_DB, out=print):
    ap = argparse.ArgumentParser(prog="python -m lab")
    ap.add_argument("--db", help="registry path (default data/lab/lab.db)")
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
    sc = sub.add_parser("scan"); sc.add_argument("--detector", action="append")
    sub.add_parser("candidates")
    sv = sub.add_parser("supervise"); sv.add_argument("--duration", type=float)
    sv.add_argument("--worker", action="append", default=[]); sv.add_argument("--no-default", action="store_true")
    sub.add_parser("health")
    gt = sub.add_parser("gate"); gt.add_argument("--require", action="store_true")
    fl = sub.add_parser("fleet"); fl.add_argument("--duration", type=float)
    for c in ("pause", "resume", "stop"):
        sub.add_parser(c).add_argument("--reason", required=True)
    jb = sub.add_parser("jobs"); jb.add_argument("--status")
    at = sub.add_parser("approve-template"); at.add_argument("template"); at.add_argument("--reason", required=True)
    ct = sub.add_parser("confirm-template"); ct.add_argument("code")
    ap_ = sub.add_parser("autopromote"); ap_.add_argument("state", choices=("on", "off"))
    ap_.add_argument("--reason", required=True)
    for c in ("shadow-start", "shadow-stop"):
        sp = sub.add_parser(c); sp.add_argument("exp"); sp.add_argument("--reason", required=True)
    rt = sub.add_parser("revoke-template"); rt.add_argument("template"); rt.add_argument("--reason", required=True)
    ex = sub.add_parser("export-db"); ex.add_argument("target")
    wb = sub.add_parser("web"); wb.add_argument("--port", type=int, default=8770); wb.add_argument("--duration", type=float)
    args = ap.parse_args(argv)
    db_path = args.db or db_path
    if args.cmd == "web":
        from lab import web
        return web.run(args.db or db_path, args.port, args.duration, out)
    if args.cmd == "supervise":       # opens its own connections; holds the single-instance lock
        from lab import supervisor
        specs = ([] if args.no_default else list(supervisor.DEFAULT_WORKERS)) + args.worker
        try:
            return supervisor.Supervisor(db_path, [supervisor.load_worker(s) for s in specs], log=out).run(args.duration)
        except supervisor.AlreadyRunning as e:
            out(f"refused: {e}")
            return 3
    if args.cmd == "fleet":           # the research agent fleet runs inside the single-instance supervisor
        from lab import fleet, supervisor
        try:
            return supervisor.Supervisor(db_path, fleet.workers(db_path), log=out).run(args.duration)
        except supervisor.AlreadyRunning as e:
            out(f"refused: {e}")
            return 3
    db = DB(db_path)
    try:
        if args.cmd in ("pause", "resume", "stop"):
            from lab import control
            fn = {"pause": control.pause, "resume": control.resume, "stop": control.request_stop}[args.cmd]
            out(f"{args.cmd}: {'recorded' if fn(db, human(), args.reason) else 'already in that state (no-op)'}")
            return 0
        if args.cmd == "export-db":                 # hand the lab over to another machine (research/LINUX_FLYT.md)
            import sqlite3
            from lab import promotion
            if promotion.supervisor_ok(db):
                out("refused: the fleet is running; stop it first so only one machine keeps the history")
                return 3
            if os.path.exists(args.target):
                out(f"refused: {args.target} already exists")
                return 3
            db.event("lab.exported", human(), None, {"target": os.path.basename(args.target),
                                                     "note": "history continues on the machine that imports this copy"})
            dst = sqlite3.connect(args.target)
            db.con.backup(dst)
            dst.close()
            copy = DB(args.target)
            try:
                chains, triggers = copy.verify()
            finally:
                copy.close()
            ok = triggers and all(b is None for _, b in chains.values())
            out(f"exported to {args.target}: {sum(n for n, _ in chains.values())} rows, chain "
                f"{'OK' if ok else 'BROKEN'}")
            return 0 if ok else 2
        if args.cmd == "jobs":
            from lab import jobs
            out(json.dumps(jobs.counts(db)))
            q = "SELECT job_id, status, attempts, lease_owner, error FROM jobs"
            rows = db.q(q + " WHERE status=? ORDER BY updated_ts DESC LIMIT 50", args.status) if args.status else                 db.q(q + " ORDER BY updated_ts DESC LIMIT 50")
            for r in rows:
                out(f"{r['job_id']:<45} {r['status']:<9} try {r['attempts']} {r['lease_owner'] or ''} {r['error'] or ''}")
            return 0
        if args.cmd == "autopromote":
            from lab import promotion
            changed = promotion.set_policy(db, args.state == "on", human(), args.reason)
            out(f"automatic promotion {args.state}: {'recorded' if changed else 'already in that state'}")
            return 0
        if args.cmd in ("shadow-start", "shadow-stop"):
            if len(args.reason.strip()) < 10:
                out("refused: a reason of at least 10 characters is required")
                return 1
            if args.cmd == "shadow-start" and lifecycle.state(db, args.exp) != "OBSERVATION":
                out(f"refused: {args.exp} is not in OBSERVATION")
                return 1
            kind = "shadow.approved" if args.cmd == "shadow-start" else "shadow.stopped"
            db.event(kind, human(), args.exp, {"reason": args.reason, "simulated": True})
            out(f"{args.exp}: {kind} (simulated shadow ledger SHADOW_{args.exp}; no effect on the formal tests)")
            return 0
        if args.cmd in ("approve-template", "confirm-template", "revoke-template"):
            from lab import templates
            try:
                if args.cmd == "approve-template":
                    code = templates.request(db, args.template, human(), args.reason)
                    out(f"confirm within 15 min: python -m lab confirm-template {code}")
                elif args.cmd == "confirm-template":
                    tpl, _ = templates.confirm(db, args.code, human())
                    out(f"template {tpl} approved for exploratory screening (catalogue blob bound)")
                else:
                    templates.revoke(db, args.template, human(), args.reason)
                    out(f"template {args.template} revoked")
            except templates.TemplateError as e:
                out(f"refused: {e}")
                return 1
            return 0
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
        elif args.cmd == "scan":
            from lab import scanner
            s = scanner.run(db, args.detector)
            out(f"observations {s['observations']} (flagged {s['flagged']}), proposals {s['proposals']}, "
                f"waiting for persistence {s['waiting_persistence']}")
            for k in ("created", "suppressed", "covered", "seen_again"):
                if s[k]:
                    out(f"  {k}: {', '.join(s[k])}")
            for e in s["errors"]:
                out(f"  detector error: {e}")
            out("CANDIDATES ONLY - nothing was evaluated or traded")
        elif args.cmd == "candidates":
            for r in db.q("SELECT exp_id, spec_json FROM experiments e WHERE version=(SELECT MAX(version) FROM "
                          "experiments WHERE exp_id=e.exp_id) ORDER BY exp_id"):
                st = lifecycle.state(db, r["exp_id"])
                if st not in ("DISCOVERED", "SUPPRESSED"):
                    continue
                spec = json.loads(r["spec_json"] or "{}")
                why = db.one("SELECT reason FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", r["exp_id"])[0]
                out(f"{r['exp_id']:<14} {st:<11} {spec.get('discovered_by', 'manual'):<21} {spec.get('reason', spec.get('hypothesis', ''))}")
                if st == "SUPPRESSED":
                    out(f"{'':<14} graveyard: {why}")
            for kind in ("candidate.covered", "candidate.seen_again", "candidate.pending_persistence"):
                for e in db.q("SELECT ts, exp_id, payload FROM events WHERE kind=? ORDER BY id DESC LIMIT 5", kind):
                    out(f"{kind:<30} {e['ts']} {e['exp_id'] or ''} {e['payload'][:120]}")
            last = db.one("SELECT MAX(ts) FROM observations")[0]
            if last:
                for o in db.q("SELECT detector, instrument, metric, value, flagged FROM observations WHERE ts=? "
                              "ORDER BY detector, metric", last):
                    v = o["value"]
                    out(f"  last scan: {o['detector']:<21} {o['metric']:<26} {o['instrument'] or '':<28} "
                        f"{'' if v is None else round(v, 6)}{'  FLAGGED' if o['flagged'] else ''}")
        elif args.cmd == "gate":
            from lab.gates import s7_gate
            g = s7_gate(db)
            out(f"S7 gate: {'OPEN' if g['open'] else 'CLOSED'} - {g['reason']} "
                f"({g['covered_s'] / 86400:.2f} of {g['required_s'] / 86400:.0f} days, {g['alive_records']} alive records)")
            return 0 if (g["open"] or not args.require) else 4
        elif args.cmd == "health":
            import time as _t
            from lab.risk import Risk
            rk = Risk(db)
            out(f"FAIL_CLOSED: {'YES' if rk.fail_closed() else 'no'}")
            for h in db.q("SELECT * FROM heartbeats ORDER BY worker"):
                out(f"worker {h['worker']:<12} last beat {int(_t.time() - h['ts'])}s ago, pid {h['pid']}, "
                    f"{'ok' if h['ok'] else 'ERROR ' + (h['detail'] or '')}")
            for x in registry.status(db):
                if x["state"] in ("PAPER_TRADING", "PAUSED"):
                    out(f"{x['exp_id']:<20} {x['state']:<14} paused={rk.paused(x['exp_id'])} warming={rk.warming(x['exp_id'])}")
            for e in db.q("SELECT ts, kind, payload FROM events WHERE kind LIKE 'system.%' OR kind LIKE 'worker.%' "
                          "ORDER BY id DESC LIMIT 8"):
                out(f"  {e['ts']} {e['kind']} {e['payload'][:140]}")
        return 0
    except (lifecycle.LifecycleError, registry.RegistryError, AccessRefused) as e:
        out(f"refused: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
