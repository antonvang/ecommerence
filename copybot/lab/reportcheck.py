"""Independent check of the daily lane report (`python3 -m lab report-verify`, research/LINUX_DRIFT.md 2026-10-22).

Read-only and deliberately separate from `lane.report`: plain SQL on a read-only connection, its own account selection
and arithmetic. Rows (name, ok, detail) like the deploy check; every deviation names both numbers.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

from lab import pipeline

DAY = 86400
TOL = 1e-6
PRICE_GAP_USD = 0.01                                # amendment 21t
FIELDS = ("equity", "net", "funding", "fees", "max_drawdown")


def _ro(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _day_start(day):
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def _events(con, kind):
    """{ledger: (time, payload)}: the payload's own clock `t` when present, else the event time (last one wins)."""
    out = {}
    for r in con.execute("SELECT ts, exp_id, payload FROM events WHERE kind=? ORDER BY id", (kind,)):
        p = json.loads(r["payload"] or "{}")
        out[r["exp_id"]] = (p.get("t", r["ts"]), p)
    return out


def _close(a, b):
    return a is not None and b is not None and abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def expected(con, day):
    """Every account of the day recomputed: started before the day ended and not retired before it began."""
    a = _day_start(day)
    end = a + DAY
    gone = _events(con, "lane.retired")
    out = {}
    for led, (t0, p) in _events(con, "lane.started").items():
        g = gone.get(led)
        if t0 >= end or (g is not None and g[0] < a):
            continue
        capital = float(p.get("capital") or 0.0)
        mark = con.execute("SELECT id, ts, equity, cash FROM sim_equity WHERE exp_id=? AND ts<? "
                           "ORDER BY ts DESC, id DESC LIMIT 1", (led, end)).fetchone()
        equity = mark["equity"] if mark else capital
        dd = con.execute("SELECT MAX(drawdown) FROM sim_equity WHERE exp_id=? AND ts<?", (led, end)).fetchone()[0]
        funding = con.execute("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=? AND ts<?",
                              (led, end)).fetchone()[0]
        fees = con.execute("SELECT COALESCE(SUM(fee), 0) FROM sim_fills WHERE exp_id=? AND ts<?", (led, end)).fetchone()[0]
        if g is not None and g[0] < end:
            status = f"stoppet: {g[1].get('rule')}"
        else:
            r = con.execute("SELECT action, rule FROM risk_events WHERE exp_id=? AND action IN ('PAUSE','CLEAR') "
                            "AND ts<? ORDER BY ts DESC, id DESC LIMIT 1", (led, end)).fetchone()
            status = f"pause: {r['rule']}" if r is not None and r["action"] == "PAUSE" else "aktiv"
        cash = None
        if mark is not None:
            ps = con.execute("SELECT payload FROM events WHERE kind='paper.started' AND exp_id=? ORDER BY id LIMIT 1",
                             (led,)).fetchone()
            base = float(json.loads(ps["payload"])["capital"]) if ps else capital
            flows = con.execute("SELECT COALESCE(SUM(CASE WHEN side='buy' THEN -px*qty ELSE px*qty END), 0), "
                                "COALESCE(SUM(fee), 0) FROM sim_fills WHERE exp_id=? AND ts<=?",
                                (led, mark["ts"])).fetchone()
            fund = con.execute("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=? AND ts<=?",
                               (led, mark["ts"])).fetchone()[0]
            cash = {"marked": mark["cash"], "replayed": base + flows[0] - flows[1] + fund}
            # 21t: residual price/basis (net - funding + fees + paid distance) = mid-based price P&L at the mark
            fs = con.execute("SELECT px, qty, mid, side, fee FROM sim_fills WHERE exp_id=? AND ts<=?",
                             (led, mark["ts"])).fetchall()
            paid = sum(abs(f["px"] - f["mid"]) * f["qty"] for f in fs if f["mid"])
            resid = (mark["equity"] - base) - fund + sum(f["fee"] for f in fs) + paid
            indep = sum((-1 if f["side"] == "buy" else 1) * f["mid"] * f["qty"] for f in fs if f["mid"]) \
                + (mark["equity"] - mark["cash"])
            cash["price_gap"] = resid - indep
        out[led] = {"equity": equity, "net": equity - capital, "funding": funding, "fees": fees,
                    "max_drawdown": dd or 0.0, "status": status, "cash": cash}
    return out


def checks(db_path, day=None, artifacts=None):
    out = []
    add = lambda name, ok, detail="": out.append((name, bool(ok), detail))  # noqa: E731
    con = _ro(db_path)
    try:
        q = "SELECT payload FROM events WHERE kind='research.lane_report'" + (" AND payload LIKE ?" if day else "") \
            + " ORDER BY id DESC LIMIT 1"
        ev = con.execute(q, (f'%"day":"{day}"%',) if day else ()).fetchone()
        if ev is None:
            add("a recorded report", False, f"no research.lane_report{' for ' + day if day else ''}")
            return out
        rec = json.loads(ev["payload"])
        day = rec["day"]
        path = os.path.join(artifacts or pipeline.ARTIFACTS, "_lane", f"{day}.json")
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            add(f"report {day}: artifact readable", False, repr(e)[:200])
            return out
        sha = hashlib.sha256(raw).hexdigest()
        add(f"report {day}: artifact SHA-256 is the recorded one", sha == rec.get("artifact_sha256"),
            f"file {sha[:12]}, recorded {str(rec.get('artifact_sha256'))[:12]}")
        art = json.loads(raw)
        rows = {r["ledger"]: r for r in art.get("accounts") or []}
        want = expected(con, day)
        add("accounts are exactly the ones live that day", set(rows) == set(want),
            f"report {len(rows)}, recomputed {len(want)}"
            + "".join(f"; missing {x}" for x in sorted(set(want) - set(rows)))
            + "".join(f"; extra {x}" for x in sorted(set(rows) - set(want))))
        for led in sorted(set(rows) & set(want)):
            r, w = rows[led], want[led]
            bad = [f"{k} {r.get(k)} vs {w[k]}" for k in FIELDS if not _close(r.get(k), w[k])]
            if r.get("status") != w["status"]:
                bad.append(f"status {r.get('status')!r} vs {w['status']!r}")
            if w["cash"] is not None and not _close(w["cash"]["marked"], w["cash"]["replayed"]):
                bad.append(f"marked cash {w['cash']['marked']} vs replayed {w['cash']['replayed']}")
            if w["cash"] is not None and abs(w["cash"].get("price_gap", 0.0)) > PRICE_GAP_USD:
                bad.append(f"price/basis residual differs from the mid-based price P&L by "
                           f"{w['cash']['price_gap']:.4f} USD (21t)")
            add(f"{led}", not bad, "; ".join(bad) or f"equity {w['equity']:.2f}, {w['status']}")
        total = sum(w["net"] for w in want.values())
        add("net_total is the sum", _close(art.get("net_total"), total) and _close(rec.get("net_total"), total),
            f"report {art.get('net_total')}, event {rec.get('net_total')}, recomputed {total}")
        add("accounts in the event", rec.get("accounts") == len(rows), f"event {rec.get('accounts')}, file {len(rows)}")
    finally:
        con.close()
    return out


def main(db_path, day=None, out=print, artifacts=None):
    rows = checks(db_path, day, artifacts)
    for name, ok, detail in rows:
        out(f"  [{'OK ' if ok else 'NO '}] {name}" + (f": {detail}" if detail else ""))
    ok = bool(rows) and all(r[1] for r in rows)
    out("REPORT OK" if ok else "REPORT MISMATCH")
    return 0 if ok else 1
