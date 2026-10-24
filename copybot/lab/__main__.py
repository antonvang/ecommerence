"""Command line for the research registry (run from copybot/):

  python3 -m lab init | import-legacy | status | show EXP | verify
  python3 -m lab discover EXP --hypothesis .. --mechanism .. --instrument .. --horizon .. --execution .. --source ..
  python3 -m lab add-version EXP --spec research/registry/EXP/SPEC.json     (committed file; complete spec)
  python3 -m lab approve EXP TO_STATE --reason ".." [--committed FILE ...]   -> prints a one-time code (15 min)
  python3 -m lab confirm CODE
  python3 -m lab transition EXP TO_STATE --reason ".." --result-id N         (automatic edges only)
  python3 -m lab result EXP --label EXPLORATORY --verdict ".." [--metrics JSON] [--supersedes ID --reason ..]
  python3 -m lab reproduce tsmom|pmcal|all                                  (S2 acceptance: dev results through the lab)
  python3 -m lab datasets [EXP]                                             (data read through the gateway)
  python3 -m lab scan [--detector venue_subsidy|pricing_constraint]         (read-only public data; candidates only)
  python3 -m lab candidates                                                 (discovered, suppressed, covered, seen again)
  python3 -m lab supervise [--duration S] [--worker module:factory ...] [--no-default]   (manual start only)
  python3 -m lab health                                                     (heartbeats, FAIL_CLOSED, pauses, warm-up)
  python3 -m lab deploy-check [--commit SHA]                                (read-only: did the deploy land?)
  python3 -m lab report-verify [--day YYYY-MM-DD]                          (read-only: recompute the daily report)
  python3 -m lab hypo-audit                                                (read-only: hypothesis pipeline audit)
  python3 -m lab research-memory [--json FILE]                             (read-only: one learning record per decided hypothesis)
  python3 -m lab web [--port 8770] [--duration S]                           (dashboard on 127.0.0.1; manual start only)
  python3 -m lab gate [--require]                                           (S7 automation gate: 7 days of clean operation)
  python3 -m lab fleet [--duration S]                                       (research agent fleet under the supervisor; manual)
  python3 -m lab pause|resume|stop --reason ".."                           (fleet control, logged in the event chain)
  python3 -m lab jobs [--status S]                                          (persistent job queue)
  python3 -m lab approve-template TEMPLATE --reason ".."  -> code;  python3 -m lab confirm-template CODE
  python3 -m lab revoke-template TEMPLATE --reason ".."
  python3 -m lab shadow-start EXP --reason ".." | shadow-stop EXP --reason ".."   (simulated shadow ledger, OBSERVATION only)
  python3 -m lab forward-start --reason ".." | forward-stop [--exp EXP] --reason ".."   (amendment 7 forward tests)
  python3 -m lab sim-resume LEDGER --reason ".."                          (resume a paused SHADOW_/FWD_/LANE_ ledger)
  python3 -m lab lane-off|lane-on --reason ".."                          (amendment 11 lane accounts; terminal only)
  python3 -m lab capital --amount USD [--coins N --leverage L --funding RATE_8H --min-order USD]  (planning only)
  python3 -m lab clear-fail-closed --reason ".."                         (terminal only; refused while the cause holds)
  python3 -m lab family-check FILE                                        (amendment 8; read-only, no network)
  python3 -m lab approve-family FID --reason ".." -> code;  python3 -m lab confirm-family   (typed by the user)
  python3 -m lab revoke-family FID --reason ".." | families                 (amendment 8)
  python3 -m lab autopromote on|off --reason ".."                         (automatic promotion policy, amendment 4)
  python3 -m lab measure H1|H2|H3 [--data-dir DIR] [--record]             (amendment 14a measurement; no network)
  python3 -m lab measure H4|H5 [--data-dir DIR] [--record]                  (amendments 16a/16c; 2022-2023 funding)
  python3 -m lab news [--backfill]                                          (amendment 16: one news pass / backfill)
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time

from lab import legacy, lifecycle, registry
from lab.data import AccessRefused
from lab.db import DB, DEFAULT_DB


def human():
    return "human:" + (getpass.getuser() or "unknown")


def assistant_session():
    return bool(os.environ.get("CLAUDECODE")) or any(k.startswith("CLAUDE_CODE_") for k in os.environ)


def operator():
    """Who runs a fleet control command: the human, or an AI assistant acting for them (recorded as such, so the
    event chain never shows an assistant's stop as the human's own)."""
    return f"ai:claude-code for {human()}" if assistant_session() else human()


def terminal_human(step):
    """A human step typed in an interactive terminal outside an assistant session (amendment 7 point 1: only a human
    resumes a simulated ledger). Policy, not proof; the logged actor and this rule bind. Returns the refusal or None."""
    if assistant_session():
        return f"an assistant session may not {step}: type it yourself in a terminal"
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return f"{step} must be typed in an interactive terminal"
    return None


TERMINAL_GUARD = terminal_human                    # replaceable in tests


class _ReadOnly:
    """The q/one subset of DB over a mode=ro connection (nothing can be written)."""
    def __init__(self, path):
        import sqlite3
        self.con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row

    def q(self, sql, *a):
        return self.con.execute(sql, a).fetchall()

    def one(self, sql, *a):
        return self.con.execute(sql, a).fetchone()


def family_check(path, db_path, out=print):
    from lab import families
    db = _ReadOnly(db_path) if os.path.exists(db_path) else None
    try:
        r = families.check(db, path)
    finally:
        if db is not None:
            db.con.close()
    out(f"family {r['family']}: {'OK' if not r['problems'] else str(len(r['problems'])) + ' problem(s)'}")
    for p in r["problems"]:
        out(f"  problem: {p}")
    out(f"  graveyard (same or related tag): {', '.join(r['graveyard']) or 'none'}"
        + (f"; not acknowledged: {', '.join(r['unacknowledged'])}" if r["unacknowledged"] else ""))
    for d, (have, need) in r["cache"].items():
        out(f"  cache {d}: {have} of {need} files present")
    for k, b in r["blobs"].items():
        out(f"  blob {k:<10} {b['path']}: committed {(b['committed'] or '-')[:12]}, "
            f"working {(b['working'] or '-')[:12]}{'' if b['clean'] else '  (not committed as is)'}")
    a = r["alpha"]
    out(f"  alpha: family {a['family']}, amendment 8 already reserved {a['reserved']:.4f} of W0 {a['W0']}")
    for months, row in r["required_sharpe"].items():
        out(f"  required annualised Sharpe over {months} months: "
            + ", ".join(f"alpha {al:.5f} -> {s}" for al, s in row.items()))
    out(f"  power at true Sharpe 3.0 (alpha_F/3, 12 months): {r['power_at_3']}")
    return 0 if not r["problems"] else 1


def family_cmd(args, db, out, ask=input):
    """Amendment 8 point 5: approve-family and confirm-family are typed by the user in an interactive terminal."""
    from lab import families
    try:
        if args.cmd == "approve-family":
            if family_check(families.path_of(args.fid), db.path, out) != 0:
                out("refused: fix the problems above first")
                return 1
            code = families.request(db, args.fid, human(), args.reason)
            b = families.bound_blobs(args.fid)["family"]
            out("This approval binds (amendment 8 point 5):")
            for line in families.approval_summary(db, families.load(args.fid)):
                out(f"  {line}")
            out(f"approval code {code} (valid 15 min). Family file blob {b[:12]}.")
            out("Confirm by typing: python3 -m lab confirm-family   (it asks for the code and the first 8 "
                "characters of the blob)")
            return 0
        if args.cmd == "confirm-family":
            families.GUARD()
            code = ask("approval code: ")
            prefix = ask("first 8 characters of the family file blob: ")
            fid, eid = families.confirm(db, code, prefix, human())
            out(f"{fid}: family.approved (event {eid}); alpha reserved. The base instances register through the fleet "
                "(strategy-1), as one batch. Registration and the train/validation spot downloads are allowed until "
                "2026-10-24 00:00 UTC; from then on a registration or screening that still needs files waits until "
                "2026-11-28 00:00 UTC (amendment 9 point 1).")
            return 0
        if args.cmd == "revoke-family":
            released = families.revoke(db, args.fid, human(), args.reason)
            out(f"{args.fid}: family.revoked" + (f"; alpha {released} released" if released else ""))
            return 0
        reserved = families.alpha_reserved(db)
        out(f"amendment 8 alpha: {reserved:.4f} of W0 {families.W0} reserved or spent")
        for f in sorted(os.listdir(families.FAMILY_DIR)):
            if f.endswith(".json") and f != "VOCABULARY.json":
                fid = f[:-5]
                a, cf, c = families.approval(db, fid), families.cohort(db, fid), families.closed(db, fid)
                if a is None and families.registered(db, fid):      # pinned at registration (point 18)
                    a = (families.binding_approval(db, fid) or {}).get("event_id")
                out(f"  {fid}: {'approved (event ' + str(a) + ')' if a else 'not approved'}"
                    f"{', registered' if families.registered(db, fid) else ''}"
                    f"{', cohort ' + cf['cohort'] + ' M ' + str(cf['M']) if cf else ''}"
                    f"{', closed ' + str(c.get('outcome')) if c else ''}")
                for e in sorted(families.members(db, fid)):
                    out(f"    {e}: {lifecycle.state(db, e)}")
        return 0
    except families.FamilyError as e:
        out(f"refused: {e}")
        return 1


def measure_cmd(args, db_path, out):
    """Amendment 14a (H1-H3) and 16a (H4): run one measurement, save the result as an artifact and print it; with
    --record also write it unchanged as a research.measurement event (point 5), refused when that hypothesis already
    has one. H4 reads the announcements read-only from the registry and fetches checksum-verified funding archives."""
    from lab import ingest, measure, measure_h4, pipeline
    db = DB(db_path) if args.record else None
    try:
        if db and any(json.loads(r["payload"] or "{}").get("hypothesis") == args.hypothesis
                      for r in db.q("SELECT payload FROM events WHERE kind=?", measure.EVENT)):
            out(f"refused: {args.hypothesis} already has a recorded measurement (amendment 14a: one run each)")
            return 1
        h4 = args.hypothesis in ("H4", "H5")
        try:
            res = (measure_h4.run(args.data_dir, db_path) if args.hypothesis == "H4" else
                   measure_h4.run_h5(args.data_dir, db_path) if args.hypothesis == "H5" else
                   measure.run(args.hypothesis, args.data_dir))
        except (measure.Refused, ingest.Refused) as e:
            out(f"refused: {e}")
            return 1
        except OSError as e:
            if not h4:
                raise
            out(f"failed: {e} (nothing recorded; a rerun reuses the verified files already cached)")
            return 1
        art = {"H4": measure_h4.ARTIFACT_ID, "H5": measure_h4.H5_ARTIFACT_ID}.get(args.hypothesis, measure.ARTIFACT_ID)
        res["artifact"] = pipeline.save_artifact(art, f"{args.hypothesis}-{int(time.time())}", res)
        if db:
            res["event_id"] = db.event(measure.EVENT, operator(), None, res)
        out(json.dumps(res, indent=1, sort_keys=True, default=str))
        return 0
    finally:
        if db:
            db.close()


def main(argv=None, db_path=DEFAULT_DB, out=print):
    ap = argparse.ArgumentParser(prog="python3 -m lab")
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
    sub.choices["stop"].add_argument("--force", action="store_true",
                                     help="end a fleet that does not respond (SIGTERM, SIGKILL after 20 s)")
    jb = sub.add_parser("jobs"); jb.add_argument("--status")
    at = sub.add_parser("approve-template"); at.add_argument("template"); at.add_argument("--reason", required=True)
    ct = sub.add_parser("confirm-template"); ct.add_argument("code")
    ap_ = sub.add_parser("autopromote"); ap_.add_argument("state", choices=("on", "off"))
    ap_.add_argument("--reason", required=True)
    for c in ("shadow-start", "shadow-stop"):
        sp = sub.add_parser(c); sp.add_argument("exp"); sp.add_argument("--reason", required=True)
    for c in ("forward-start", "forward-stop"):
        fp = sub.add_parser(c); fp.add_argument("--exp"); fp.add_argument("--reason", required=True)
    sr = sub.add_parser("sim-resume"); sr.add_argument("ledger"); sr.add_argument("--reason", required=True)
    for c in ("lane-off", "lane-on"):
        sub.add_parser(c).add_argument("--reason", required=True)
    cp = sub.add_parser("capital")
    cp.add_argument("--amount", required=True); cp.add_argument("--coins", default=5)
    cp.add_argument("--leverage", default=1); cp.add_argument("--funding", default=None)
    cp.add_argument("--min-order", default=None)
    cf = sub.add_parser("clear-fail-closed"); cf.add_argument("--reason", required=True)   # terminal only
    fc = sub.add_parser("family-check"); fc.add_argument("file")
    af = sub.add_parser("approve-family"); af.add_argument("fid"); af.add_argument("--reason", required=True)
    sub.add_parser("confirm-family")
    rf = sub.add_parser("revoke-family"); rf.add_argument("fid"); rf.add_argument("--reason", required=True)
    sub.add_parser("families")
    fcv = sub.add_parser("family-coverage"); fcv.add_argument("fid")   # F2: HEAD check (family id or file path)
    rt = sub.add_parser("revoke-template"); rt.add_argument("template"); rt.add_argument("--reason", required=True)
    ex = sub.add_parser("export-db"); ex.add_argument("target")
    me = sub.add_parser("measure"); me.add_argument("hypothesis", choices=("H1", "H2", "H3", "H4", "H5"))
    me.add_argument("--data-dir", help="market cache with funding/ and ingest/ (default data/lab/market)")
    me.add_argument("--record", action="store_true", help="record the outcome as an event (once per hypothesis)")
    cbl = sub.add_parser("coinbase-listings")
    cbl.add_argument("--source", choices=("coinbase", "upbit"), default="coinbase",
                     help="amendment 17g (Coinbase USD) or 17h (Upbit KRW)")
    nw = sub.add_parser("news"); nw.add_argument("--backfill", action="store_true",
                                                 help="fetch Binance announcements backwards once (amendment 16)")
    wt = sub.add_parser("watch"); wt.add_argument("--once", action="store_true")
    wt.add_argument("--interval", type=float, default=30.0); wt.add_argument("--port", type=int, default=8770)
    pf = sub.add_parser("preflight"); pf.add_argument("--port", type=int, default=8770)
    dc = sub.add_parser("deploy-check"); dc.add_argument("--port", type=int, default=8770); dc.add_argument("--commit")
    rv = sub.add_parser("report-verify"); rv.add_argument("--day", help="UTC day (default: the latest report)")
    sub.add_parser("hypo-audit")
    rm = sub.add_parser("research-memory"); rm.add_argument("--json", default=None)
    pf.add_argument("--dashboard-running", action="store_true", help="only check whether the dashboard answers")
    wb = sub.add_parser("web"); wb.add_argument("--port", type=int, default=8770); wb.add_argument("--duration", type=float)
    args = ap.parse_args(argv)
    db_path = args.db or db_path
    if args.cmd == "watch":           # independent read-only watcher of lab + pm_lp collector (lab/watch.py)
        from lab import watch
        return watch.main(db_path, args.port, args.once, args.interval, out)
    if args.cmd == "preflight":       # read-only startup checks (START_LAB.sh)
        from lab import preflight
        if args.dashboard_running:
            return 0 if preflight.dashboard_running(args.port) else 1
        return preflight.main(db_path, args.port, out)
    if args.cmd == "deploy-check":    # read-only: did the deploy land? (research/LINUX_DRIFT.md 2026-10-22)
        from lab import deploycheck
        return deploycheck.main(port=args.port, commit=args.commit, out=out)
    if args.cmd == "hypo-audit":      # read-only: hypothesis pipeline audit (research/LINUX_DRIFT.md 2026-10-22)
        from lab import hypoaudit
        return hypoaudit.main(db_path, out)
    if args.cmd == "research-memory":     # read-only learning records (research/LINUX_DRIFT.md 2026-10-23)
        from lab import memory
        return memory.main(db_path, out, args.json)
    if args.cmd == "report-verify":   # read-only: recompute the daily lane report (research/LINUX_DRIFT.md 2026-10-22)
        from lab import reportcheck
        return reportcheck.main(db_path, args.day, out)
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
    if args.cmd == "family-check":    # research/PROTOCOL_V3.md amendment 8 point 4: read-only, no network
        return family_check(args.file, db_path, out)
    if args.cmd == "measure":         # research/PROTOCOL_V3.md amendment 14a: read-only data, one run per hypothesis
        return measure_cmd(args, db_path, out)
    if args.cmd == "coinbase-listings":   # amendments 17g/17h: first trade per Coinbase USD / Upbit KRW market
        from lab import coinbase
        db = DB(db_path)
        try:
            out(json.dumps(coinbase.backfill(db, source=args.source), indent=1, default=str))
            return 0
        finally:
            db.close()
    if args.cmd == "news":            # amendment 16: one pass, or the one-time Binance backfill (observations only)
        from lab import news
        db = DB(db_path)
        try:
            out(json.dumps(news.backfill(db) if args.backfill else news.run(db), indent=1, default=str))
            return 0
        finally:
            db.close()
    if args.cmd == "fleet":           # the research agent fleet runs inside the single-instance supervisor
        from lab import fleet, supervisor
        from research.pm_lp import install_dns_cache
        install_dns_cache()           # same cache as the pm_lp collector: fewer queries to the shared NAS DNS
        try:
            return supervisor.Supervisor(db_path, fleet.workers(db_path), log=out,
                                         on_stop=(fleet.shutdown,)).run(args.duration)
        except supervisor.AlreadyRunning as e:
            out(f"refused: {e}")
            return 3
    db = DB(db_path)
    try:
        if args.cmd == "stop":
            from lab import control
            return control.stop(db, operator(), args.reason, force=args.force, out=out)
        if args.cmd in ("pause", "resume"):
            from lab import control
            fn = {"pause": control.pause, "resume": control.resume}[args.cmd]
            out(f"{args.cmd}: {'recorded' if fn(db, operator(), args.reason) else 'already in that state (no-op)'}")
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
            from lab import families
            if args.cmd == "shadow-start" and families.is_instance(db, args.exp):   # amendment 8 point 16
                out(f"refused: {args.exp}: {families.NO_PAPER}")
                return 1
            kind = "shadow.approved" if args.cmd == "shadow-start" else "shadow.stopped"
            db.event(kind, human(), args.exp, {"reason": args.reason, "simulated": True})
            out(f"{args.exp}: {kind} (simulated shadow ledger SHADOW_{args.exp}; no effect on the formal tests)")
            return 0
        if args.cmd in ("forward-start", "forward-stop"):        # research/PROTOCOL_V3.md amendment 7
            from lab import pipeline
            from lab.paper import FORWARD_ACCOUNTS
            if len(args.reason.strip()) < 10:
                out("refused: a reason of at least 10 characters is required")
                return 1
            ids = [args.exp] if args.exp else list(FORWARD_ACCOUNTS)
            unknown = [e for e in ids if e not in FORWARD_ACCOUNTS]
            if unknown:
                out(f"refused: not on the amendment 7 list: {', '.join(unknown)}")
                return 1
            kind = "forward.approved" if args.cmd == "forward-start" else "forward.stopped"
            bad = [e for e in ids if kind == "forward.approved" and (
                pipeline.recorded_sha(db, e, "cost"), pipeline.recorded_sha(db, e, "backtest")) != FORWARD_ACCOUNTS[e]]
            if bad:                                     # all or nothing: nothing is started
                out(f"refused: recorded artifacts are not the pinned ones (amendment 7): {', '.join(bad)}")
                return 1
            with db.tx():
                for e in ids:
                    pins = FORWARD_ACCOUNTS[e]
                    db.event(kind, human(), e, {"reason": args.reason, "simulated": True, "ledger": "FWD_" + e,
                                                "cost_sha256": pins[0], "backtest_sha256": pins[1],
                                                "amendment": "PROTOCOL_V3 amendment 7"})
            for e in ids:
                out(f"{e}: {kind} (simulated forward-test ledger FWD_{e}; no effect on the formal tests)")
            return 0
        if args.cmd == "clear-fail-closed":           # a human in a terminal, once the cause is gone
            from lab.risk import Risk
            why = TERMINAL_GUARD("clear FAIL_CLOSED")
            if why:
                out(f"refused: {why}")
                return 1
            try:
                done = Risk(db).clear_fail_closed(human(), args.reason)
            except lifecycle.LifecycleError as e:
                out(f"refused: {e}")
                return 1
            out("FAIL_CLOSED cleared (CLEAR recorded)" if done else "the lab is not FAIL_CLOSED: nothing to clear")
            return 0
        if args.cmd == "sim-resume":
            from lab.risk import Risk
            why = TERMINAL_GUARD("resume a simulated ledger")
            if why:
                out(f"refused: {why}")
                return 1
            try:
                done = Risk(db).resume_simulated(args.ledger, human(), args.reason)
            except lifecycle.LifecycleError as e:
                out(f"refused: {e}")
                return 1
            out(f"{args.ledger}: {'resumed (CLEAR recorded)' if done else 'not paused: nothing to resume'}")
            return 0
        if args.cmd == "capital":                     # planning only: the user's own amount; no order, no account
            from lab import capital
            try:
                out(json.dumps(capital.plan(args.amount, args.coins, args.leverage, args.funding, args.min_order),
                               indent=1, default=str))
            except capital.CapitalError as e:
                out(f"refused: {e}")
                return 1
            return 0
        if args.cmd in ("lane-off", "lane-on"):       # amendment 11 point 5: a human switches the lane accounts
            from lab import lane
            why = TERMINAL_GUARD(f"switch the lane accounts {args.cmd[5:]}")
            if why:
                out(f"refused: {why}")
                return 1
            try:
                lane.set_policy(db, args.cmd == "lane-on", human(), args.reason)
            except lifecycle.LifecycleError as e:
                out(f"refused: {e}")
                return 1
            out("lane accounts on: the paper agent starts them by amendment 11" if args.cmd == "lane-on" else
                "lane accounts off: the paper agent retires every active one and closes its positions")
            return 0
        if args.cmd == "family-coverage":           # amendment 8 point 17: refused before 2026-11-28 00:00 UTC
            from lab import families
            from research.pm_lp import install_dns_cache
            install_dns_cache()                     # point 17: the fleet's DNS cache
            src = args.fid
            if not src.endswith(".json") and not os.path.exists(families.path_of(src)):
                src = os.path.join(families.FAMILY_DIR, "drafts", f"{src}.json")    # a draft before approval
            if not os.path.exists(src if src.endswith(".json") else families.path_of(src)):
                out(f"refused: no family file {args.fid} (research/families/ or research/families/drafts/)")
                return 1
            try:
                covered, checked = families.check_coverage(db, src, human())
            except families.FamilyError as e:
                out(f"refused: {e}")
                return 1
            except OSError as e:                    # network, 5xx, 403: nothing recorded, run it again later
                out(f"refused: the coverage check stopped without a record: {e!r}"[:300])
                return 1
            out(f"{args.fid}: {sum(checked.values())} of {len(checked)} quarterly zips present (HEAD, no data read)")
            out(f"  fully covered 2022-01..2024-12: {', '.join(covered) or 'none'}")
            return 0
        if args.cmd in ("approve-family", "confirm-family", "revoke-family", "families"):   # amendment 8
            return family_cmd(args, db, out)
        if args.cmd in ("approve-template", "confirm-template", "revoke-template"):
            from lab import templates
            try:
                if args.cmd == "approve-template":
                    code = templates.request(db, args.template, human(), args.reason)
                    out(f"confirm within 15 min: python3 -m lab confirm-template {code}")
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
                why = x["verdict"] or ""
                if x["final"] and why.upper().startswith("PASS"):      # a later final decision outranks an old pass
                    t = db.one("SELECT to_state, reason FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1",
                               x["exp_id"])
                    if t and t["reason"]:
                        why = f"{t['to_state']}: {t['reason']} (tidligere: {why})"
                out(f"{x['exp_id']:<30} {x['state'] or '-':<14} {x['label'] or '':<12} {why}")
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
        elif args.cmd == "approve":                 # a family instance: no code for a step lab confirm would refuse
            from lab import families
            code = lifecycle.request_approval(db, args.exp, args.to, human(), args.reason,
                                              {"committed_files": args.committed} if args.committed else None,
                                              guards=(registry.complete_spec_guard, families.terminal_guard))
            out(f"approval code for {args.exp} -> {args.to}: {code}   (confirm within 15 minutes: python3 -m lab confirm {code})")
        elif args.cmd == "confirm":                 # a family instance (amendment 8 point 6): interactive terminal only
            from lab import families
            exp, to = lifecycle.confirm(db, args.code, human(), guards=(registry.complete_spec_guard,
                                                                         families.terminal_guard))
            out(f"{exp} -> {to}")
        elif args.cmd == "transition":              # a family instance: families.gate_problem (amendment 8 p. 8-12)
            from lab import families
            cur = lifecycle.state(db, args.exp)
            if families.is_instance(db, args.exp) and (cur, args.to) not in registry.GATE_EDGES:
                raise lifecycle.LifecycleError(
                    f"{args.exp} is an amendment 8 family instance: lab transition takes only its gate edges, each on "
                    f"its step's result; {cur} -> {args.to} is the fleet's or a human terminal step (points 6-12)")
            ev = {"result_id": args.result_id} if args.result_id is not None else None
            lifecycle.auto_transition(db, args.exp, args.to, "system:cli", args.reason, ev,
                                      guards=(registry.make_result_guard(ev),))
            out(f"{args.exp} -> {args.to}")
        elif args.cmd == "result":                  # refused for a family instance: only its steps record results
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
                age = int(_t.time() - h["ts"])
                if not h["ok"]:
                    tag = "ERROR " + (h["detail"] or "")
                elif h["status"] == "stopped":
                    tag = "stopped"
                elif age > (h["stale_after"] or 300):
                    tag = f"STALE (no heartbeat for {age}s)"
                else:
                    tag = "ok"
                out(f"worker {h['worker']:<12} last beat {age}s ago, pid {h['pid']}, {tag}")
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
