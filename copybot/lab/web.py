"""Lab dashboard server (ENGINE_PROPOSAL.md §7, stage S6). Read-only JSON API over the registry, plus four guarded
controls that call exactly the same lifecycle/risk functions as the CLI. Bound to 127.0.0.1 only.

Every number comes from a database query at request time. Simulated figures are labelled "simulated". There is no
control that resumes a strategy without its revalidation criteria, edits gates or results, or does anything live.

Controls require the per-process token embedded in the served page (blocks cross-site requests) and a same-origin
request. Approvals still need the one-time code step, exactly like the CLI.
"""
from __future__ import annotations

import getpass
import json
import math
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from lab import command, control, lifecycle, mission, registry
from lab.data import AccessRefused
from lab.db import DB, DEFAULT_DB
from lab.paper import PaperEngine
from lab.risk import GLOBAL, Risk

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 8770
LABEL_OF_STATE = {"DISCOVERED": "CANDIDATE", "SUPPRESSED": "SUPPRESSED", "REGISTERED": "REGISTERED",
                  "SCREENING": "EXPLORATORY", "SCREEN_PASSED": "EXPLORATORY", "VALIDATION": "VALIDATION",
                  "VALIDATED": "VALIDATED", "PAPER_TRADING": "PAPER (simulated)", "PAUSED": "PAPER (simulated, paused)",
                  "REJECTED": "REJECTED", "RETIRED": "RETIRED", "WITHDRAWN": "WITHDRAWN", "EXTERNAL": "EXTERNAL"}


def _clean(o):
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _j(s):
    try:
        return json.loads(s) if s else None
    except ValueError:
        return s


# ---------- read models (pure functions of the database) ----------
def overview(db):
    rk = Risk(db)
    st = registry.status(db)
    counts = {}
    for x in st:
        counts[x["state"]] = counts.get(x["state"], 0) + 1
    hb = [dict(r) | {"age_s": int(time.time() - r["ts"])} for r in db.q("SELECT * FROM heartbeats ORDER BY worker")]
    last_obs = db.one("SELECT MAX(ts) FROM observations")[0]
    tested = [x for x in st if x["state"] in ("REJECTED", "RETIRED", "WITHDRAWN")]
    by_mech = {}
    for x in tested:
        by_mech[x["mechanism"]] = by_mech.get(x["mechanism"], 0) + 1
    chains, triggers = db.verify()
    return {"fail_closed": rk.fail_closed(), "heartbeats": hb, "pipeline": counts, "experiments": len(st),
            "finished": len(tested), "rejected": counts.get("REJECTED", 0), "last_scan_ts": last_obs,
            "alpha_spent": db.one("SELECT COALESCE(SUM(alpha),0) FROM alpha_ledger")[0],
            "chain_ok": triggers and all(b is None for _, b in chains.values()),
            "rows": {t: n for t, (n, _) in chains.items()}, "finished_by_mechanism": by_mech,
            "paper_only": True, "now": int(time.time())}


def experiments(db):
    out = []
    for x in registry.status(db):
        last = db.one("SELECT ts, actor, reason FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", x["exp_id"])
        out.append({**x, "display_label": LABEL_OF_STATE.get(x["state"], x["state"]),
                    "since": last["ts"] if last else None, "last_reason": last["reason"] if last else None})
    return out


def experiment(db, exp_id):
    vs = db.q("SELECT * FROM experiments WHERE exp_id=? ORDER BY version", exp_id)
    if not vs:
        return None
    return {"exp_id": exp_id, "state": lifecycle.state(db, exp_id),
            "display_label": LABEL_OF_STATE.get(lifecycle.state(db, exp_id)),
            "next_actions": [{"to": b, "who": who} for (a, b), who in lifecycle.EDGES.items()
                             if a == lifecycle.state(db, exp_id)],
            "versions": [{k: (_j(v["spec_json"]) if k == "spec_json" else v[k]) for k in v.keys()} for v in vs],
            "transitions": [dict(r) | {"evidence": _j(r["evidence"])} for r in
                            db.q("SELECT * FROM transitions WHERE exp_id=? ORDER BY id", exp_id)],
            "results": [dict(r) | {"metrics": _j(r["metrics"]), "evidence": _j(r["evidence"])} for r in
                        db.q("SELECT * FROM results WHERE exp_id=? ORDER BY id", exp_id)],
            "datasets": [dict(r) for r in db.q("SELECT * FROM datasets WHERE exp_id=? ORDER BY id", exp_id)],
            "alpha": [dict(r) for r in db.q("SELECT * FROM alpha_ledger WHERE exp_id=? ORDER BY id", exp_id)],
            "events": [dict(r) | {"payload": _j(r["payload"])} for r in
                       db.q("SELECT * FROM events WHERE exp_id=? ORDER BY id DESC LIMIT 50", exp_id)]}


def candidates(db):
    cands = [x for x in experiments(db) if x["state"] in ("DISCOVERED", "SUPPRESSED")]
    for c in cands:
        spec = _j(db.one("SELECT spec_json FROM experiments WHERE exp_id=? ORDER BY version DESC LIMIT 1",
                         c["exp_id"])[0]) or {}
        c.update({"detector": spec.get("discovered_by", "manual"), "reason": spec.get("reason"),
                  "hypothesis": spec.get("hypothesis"), "data_requirements": spec.get("data_requirements"),
                  "source": (spec.get("sources") or [None])[0]})
    dedupe = [dict(r) | {"payload": _j(r["payload"])} for r in db.q(
        "SELECT ts, kind, exp_id, payload FROM events WHERE kind IN ('candidate.covered','candidate.seen_again',"
        "'candidate.suppressed','candidate.pending_persistence') ORDER BY id DESC LIMIT 30")]
    last = db.one("SELECT MAX(ts) FROM observations")[0]
    obs = [dict(r) | {"payload": _j(r["payload"])} for r in
           db.q("SELECT * FROM observations WHERE ts=? ORDER BY detector, metric, instrument", last)] if last else []
    return {"candidates": cands, "dedupe_events": dedupe, "last_scan_ts": last, "last_scan": obs}


def paper(db):
    pe, rk, out = PaperEngine(db), Risk(db), []
    for x in registry.status(db):
        if not db.one("SELECT 1 FROM events WHERE kind='paper.started' AND exp_id=?", x["exp_id"]):
            continue
        led = pe.ledger(x["exp_id"])
        fills = db.q("SELECT liquidity, COALESCE(SUM(fee),0) fees, COALESCE(SUM(ABS(slippage)*px*qty),0) slip, "
                     "COUNT(*) n FROM sim_fills WHERE exp_id=? GROUP BY liquidity", x["exp_id"])
        wins = losses = 0
        for _, pnl in reversed(led["trades"]):
            if pnl < 0 and wins == 0:
                losses += 1
            elif pnl >= 0 and losses == 0:
                wins += 1
            else:
                break
        out.append({"exp_id": x["exp_id"], "state": x["state"], "simulated": True,
                    "equity": [dict(r) for r in db.q("SELECT ts, equity, drawdown, exposure FROM sim_equity "
                                                     "WHERE exp_id=? ORDER BY id", x["exp_id"])],
                    "capital": led["capital"], "cash": led["cash"], "positions": led["positions"],
                    "trades": len(led["trades"]), "net_closed_pnl": sum(p for _, p in led["trades"]),
                    "trade_pnls": [{"ts": t, "pnl": p} for t, p in led["trades"][-200:]],
                    "streak": {"wins": wins, "losses": losses},
                    "costs": [dict(r) for r in fills], "open_orders": len(pe.open_orders(x["exp_id"])),
                    "paused": rk.paused(x["exp_id"]), "warming": rk.warming(x["exp_id"])})
    return {"strategies": out, "simulated": True}


def risk(db):
    rk = Risk(db)
    paused = [x["exp_id"] for x in registry.status(db) if x["state"] == "PAUSED"]
    return {"fail_closed": rk.fail_closed(),
            "events": [dict(r) for r in db.q("SELECT * FROM risk_events ORDER BY id DESC LIMIT 100")],
            "paused": [{"exp_id": e, "resume_requires": "human approval PAUSED -> PAPER_TRADING citing committed "
                                                        "revalidation evidence, then a logged CLEAR"} for e in paused]}


def data_quality(db):
    det = [dict(r) for r in db.q("SELECT detector, MAX(ts) last_ts, COUNT(*) n, SUM(flagged) flagged, "
                                 "SUM(CASE WHEN metric='error' THEN 1 ELSE 0 END) errors FROM observations "
                                 "GROUP BY detector ORDER BY detector")]
    blocks = [dict(r) for r in db.q("SELECT * FROM risk_events WHERE action='BLOCK' ORDER BY id DESC LIMIT 50")]
    ds = [dict(r) for r in db.q("SELECT exp_id, split, purpose, path, sha256, size, ts FROM datasets ORDER BY id DESC "
                                "LIMIT 100")]
    refused = [dict(r) | {"payload": _j(r["payload"])} for r in
               db.q("SELECT ts, exp_id, payload FROM events WHERE kind='data.refused' ORDER BY id DESC LIMIT 30")]
    return {"detectors": det, "data_blocks": blocks, "datasets": ds, "refused_reads": refused}


def audit(db, kind=None, limit=200):
    q = "SELECT id, ts, kind, actor, exp_id, payload, hash FROM events" + (" WHERE kind LIKE ?" if kind else "")
    rows = db.q(q + " ORDER BY id DESC LIMIT ?", *([kind + "%"] if kind else []), int(limit))
    chains, triggers = db.verify()
    return {"events": [dict(r) | {"payload": _j(r["payload"])} for r in rows],
            "chains": {t: {"rows": n, "broken_at": b} for t, (n, b) in chains.items()}, "triggers": triggers}


def _sse_event(r):
    p = _j(r["payload"]) or {}
    kind = p.get("kind") if isinstance(p, dict) else None
    return {"id": r["id"], "ts": r["ts"], "kind": r["kind"], "actor": r["actor"], "exp_id": r["exp_id"],
            "job_kind": kind, "stage": command.STAGE_OF_KIND.get(kind),
            "to": p.get("to") if isinstance(p, dict) else None}


# ---------- server ----------
class LabServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, addr, db_path):
        super().__init__(addr, Handler)
        self.db_path, self.token = db_path, secrets.token_hex(16)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(_clean(body), default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "dashboard.html"), encoding="utf-8") as f:
                html = f.read().replace("__LAB_TOKEN__", self.server.token)
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        db = DB(self.server.db_path)
        try:
            qs = parse_qs(u.query)
            routes = {"/api/overview": lambda: overview(db), "/api/experiments": lambda: experiments(db),
                      "/api/candidates": lambda: candidates(db), "/api/paper": lambda: paper(db),
                      "/api/risk": lambda: risk(db), "/api/data": lambda: data_quality(db),
                      "/api/audit": lambda: audit(db, (qs.get("kind") or [None])[0], (qs.get("limit") or [200])[0])}
            routes.update({"/api/mission": lambda: mission.mission(db), "/api/pipeline": lambda: mission.pipeline_rows(db),
                           "/api/throughput": lambda: mission.throughput(db), "/api/results": lambda: mission.results_view(db)})
            one = lambda k, d=None: (qs.get(k) or [d])[0]  # noqa: E731
            routes.update({
                "/api/kpis": lambda: command.kpis(db, int(one("window", 900))),
                "/api/agents": lambda: command.agents(db),
                "/api/jobs": lambda: command.job_list(db, one("status"), one("kind"), one("exp"), one("page", 1),
                                                      one("size", 50)),
                "/api/v2/experiments": lambda: command.experiments(db, one("market"), one("strategy"), one("worker"),
                                                                   one("status"), one("stage"), one("since"),
                                                                   one("page", 1), one("size", 50),
                                                                   one("catalogue") == "1"),
                "/api/distribution": lambda: command.distribution(db), "/api/costs": lambda: command.costs(db),
                "/api/paper2": lambda: command.paper_view(db), "/api/rejected": lambda: command.rejected(db)})
            if u.path.startswith("/api/agent/"):
                return self._send(200, command.agent_log(db, u.path.rsplit("/", 1)[1], int(one("limit", 50))))
            if u.path == "/api/stream":
                db.close()
                return self._stream()
            if u.path.startswith("/api/experiment/"):
                r = experiment(db, u.path.rsplit("/", 1)[1])
                return self._send(200 if r else 404, r or {"error": "not found"})
            if u.path in routes:
                return self._send(200, routes[u.path]())
            return self._send(404, {"error": "not found"})
        finally:
            db.close()

    def _stream(self):
        """Server-sent events: one message whenever new registry events or simulated fills appear (checked every 2 s),
        plus a keep-alive comment every 15 s. The client refreshes its views on each message."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last, quiet = None, 0.0
        try:
            while not getattr(self.server, "closing", False):
                db = DB(self.server.db_path)
                try:
                    top = db.one("SELECT COALESCE(MAX(id),0) FROM events")[0]
                    fills = db.one("SELECT COUNT(*) FROM sim_fills")[0]
                    beat = db.one("SELECT COALESCE(MAX(ts),0) FROM heartbeats")[0]
                    new = [] if last is None else [_sse_event(r) for r in db.q(
                        "SELECT id, ts, kind, actor, exp_id, payload FROM events WHERE id>? ORDER BY id LIMIT 40",
                        last[0])]
                finally:
                    db.close()
                state = (top, fills, beat)
                if state != last:
                    msg = {"last_event_id": top, "fills": fills, "heartbeat_ts": beat, "new_events": new,
                           "first": last is None}
                    self.wfile.write(("data: " + json.dumps(msg, default=str) + "\n\n").encode())
                    self.wfile.flush()
                    last, quiet = state, 0.0
                else:
                    quiet += 2
                    if quiet >= 15:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        quiet = 0.0
                time.sleep(2)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    def do_POST(self):
        host = f"127.0.0.1:{self.server.server_address[1]}"
        origin = self.headers.get("Origin")
        if self.headers.get("X-Lab-Token") != self.server.token or (origin and origin not in
                                                                    (f"http://{host}", f"http://localhost:{self.server.server_address[1]}")):
            return self._send(403, {"error": "missing or wrong control token / cross-origin request"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, {"error": "invalid JSON"})
        actor = f"human:{getpass.getuser() or 'unknown'}@dashboard"
        db = DB(self.server.db_path)
        try:
            p = urlparse(self.path).path
            if p == "/api/control/approve":
                ev = {"committed_files": body.get("committed") or []} if body.get("committed") else None
                code = lifecycle.request_approval(db, body["exp_id"], body["to"], actor, body.get("reason", ""), ev,
                                                  guards=(registry.complete_spec_guard,))
                return self._send(200, {"code": code, "expires_in_s": lifecycle.APPROVAL_SECONDS})
            if p == "/api/control/confirm":
                exp, to = lifecycle.confirm(db, body.get("code", ""), actor, guards=(registry.complete_spec_guard,))
                return self._send(200, {"exp_id": exp, "state": to})
            if p == "/api/control/pause":                 # risk-reducing: always allowed for a paper strategy
                if lifecycle.state(db, body["exp_id"]) != "PAPER_TRADING":
                    return self._send(400, {"error": "only a PAPER_TRADING strategy can be paused"})
                if len(body.get("reason", "")) < 10:
                    return self._send(400, {"error": "a reason of at least 10 characters is required"})
                Risk(db).pause(body["exp_id"], "manual_pause", None, None, f"{actor}: {body['reason']}",
                               PaperEngine(db).cancel_entries)
                return self._send(200, {"exp_id": body["exp_id"], "state": lifecycle.state(db, body["exp_id"])})
            if p == "/api/control/fleet":                 # pause / resume / graceful stop, logged in the event chain
                act = body.get("action")
                if act not in ("pause", "resume", "stop"):
                    return self._send(400, {"error": "action must be pause, resume or stop"})
                if len(body.get("reason", "")) < 10:
                    return self._send(400, {"error": "a reason of at least 10 characters is required"})
                fn = {"pause": control.pause, "resume": control.resume, "stop": control.request_stop}[act]
                changed = fn(db, actor, body["reason"])
                return self._send(200, {"action": act, "changed": changed, "control": control.state(db)})
            if p == "/api/control/clear-fail-closed":
                Risk(db).clear_fail_closed(actor, body.get("reason", ""))
                return self._send(200, {"fail_closed": Risk(db).fail_closed()})
            return self._send(404, {"error": "no such control"})
        except (lifecycle.LifecycleError, registry.RegistryError, AccessRefused, KeyError) as e:
            return self._send(400, {"error": str(e)})
        finally:
            db.close()


def serve(db_path=DEFAULT_DB, port=DEFAULT_PORT, tries=10):
    for p in range(port, port + tries):
        try:
            return LabServer(("127.0.0.1", p), db_path)
        except OSError:
            if p == port + tries - 1:
                raise


def run(db_path=DEFAULT_DB, port=DEFAULT_PORT, duration=None, log=print):
    srv = serve(db_path, port)
    log(f"lab dashboard: http://127.0.0.1:{srv.server_address[1]}  (read-only; Ctrl+C to stop)")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        if duration:
            time.sleep(duration)
        else:
            t.join()
    except KeyboardInterrupt:
        pass
    finally:
        srv.closing = True
        srv.shutdown()
        srv.server_close()
    return 0
