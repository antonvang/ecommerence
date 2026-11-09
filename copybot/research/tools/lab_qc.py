"""Director order 66 C: offline quality control of the paper-trading lab (read-only, stdlib only, no network).

    python3 research/tools/lab_qc.py [--db PATH] [--at YYYY-MM-DDTHH:MM:SSZ] [--out FILE.md] [--json]
                                     [--suite-log FILE] [--integrity-budget SECONDS] [--root DIR] [--prod-root DIR]

One CLI run, no process or timer. lab.db is opened as file:<path>?mode=ro with PRAGMA query_only=ON inside one read
transaction (one snapshot); nothing is written except the optional --out markdown. Market-data files are never opened.
Checks (each PASS / WARN / FAIL with counts and evidence ids, never raw rows; check 8 is SKIP without --suite-log):

1. DB integrity: PRAGMA integrity_check on its own read-only connection, time-boxed (falls back to quick_check);
   the lab schema tables (lab/db.py TABLES + heartbeats) are present.
2. Hash chains: the lab's own verifier lab.db.DB.verify (row_hash over prev|table|canonical row) for every chained
   table in lab/db.py, plus append-only triggers; any other table with prev_hash/hash gets a continuity-only check.
3. Stale and missing marks: research/tools/net_report.py build/freshness at --at (FRESH / STALE / MISSING_MARK) per
   active account. STALE and MISSING_MARK are WARN (old data, not wrong data).
4. Reports vs ledger: the latest complete-day lane report artifact (artifacts/_lane/<day>.json next to the DB) against a
   net_report recomputation from sim_equity cut at the same day end, reconciled by research/tools/net_reconcile.py.
   SAME_MARK = PASS, TIMING_MARK = WARN, UNEXPLAINED / ACCOUNTING_UNRECONCILED / internal total mismatch = FAIL.
5. Duplicates and sign sanity: duplicate fill_id / order_id, negative fees, non-finite numbers, fill price <= 0,
   fill qty <= 0 (FAIL); funding rows whose instrument has no open position (from sim_fills up to settle_ts), whose
   position sign differs or whose booked qty differs from that position (WARN only).
6. Protocol drift: nov14_readiness.verify_hashes (GATE_MATRIX pins vs NOV14_READINESS vs files) and the HFC-1
   rules-prefix hash (first 3178 bytes). Mismatch = FAIL.
7. Locked code: sha256 of lab/straks.py and lab/pairs.py in the dev checkout and (read-only) in production.
8. Test-failure log: Ran / OK / FAILED and the failing test names from a guarded-suite log (--suite-log).

Exit 0 = no FAIL, 1 = any FAIL, 2 = bad input.
"""
from __future__ import annotations

import argparse
import bisect
import calendar
import collections
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import traceback
import types

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from lab import db as labdb  # noqa: E402  (module import only: constants, row_hash and the verifier; no DB() object)
from research.tools import net_reconcile as nrec  # noqa: E402
from research.tools import net_report as nrep  # noqa: E402
from research.tools import nov14_readiness as n14  # noqa: E402

DB_DEFAULT = "/home/anton/ecommerence/copybot/data/lab/lab.db"
PROD_ROOT = "/home/anton/ecommerence/copybot"
LOCKED = {"lab/straks.py": "7a110f1fa20fb7d28b76269fc039eec4c75ddfa7353602f2f8824490b722a542",
          "lab/pairs.py": "5c9b60a4314a40a5e4d517427c4960220682b8f6179a445a5554903180ce1219"}
HFC1 = {"path": "research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md", "prefix_bytes": 3178,
        "sha256": "cd1b6fc66000544f6e58a5e202f4c3f0c2d10913c3882f3eda6b8d06cdfe53c6"}
SCHEMA_TABLES = tuple(labdb.TABLES) + ("heartbeats",)
MAX_IDS = 10                    # evidence ids listed per finding (counts are always complete)
INTEGRITY_BUDGET_S = 120.0
POS_EPS = 1e-9
DAY = 86400
ORDER = {"PASS": 0, "SKIP": 0, "WARN": 1, "FAIL": 2}


class BadInput(Exception):
    pass


def parse_at(s):
    try:
        return calendar.timegm(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").timetuple())
    except (TypeError, ValueError):
        raise BadInput("--at must be YYYY-MM-DDTHH:MM:SSZ (UTC), got %r" % (s,))


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts is not None else None


def open_ro(path):
    if not os.path.isfile(path):
        raise BadInput("no database file: %s" % path)
    uri = "file:" + path.replace("%", "%25").replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def sha256_path(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ids(seq):
    seq = list(seq)
    return seq[:MAX_IDS] + (["... +%d" % (len(seq) - MAX_IDS)] if len(seq) > MAX_IDS else [])


def result(cid, name, status, summary, counts=None, evidence=None, notes=None):
    return {"id": cid, "name": name, "status": status, "summary": summary, "counts": counts or {},
            "evidence": evidence or {}, "notes": notes or []}


def worst(statuses):
    return max(statuses, key=lambda s: ORDER[s]) if statuses else "PASS"


def tables_of(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def columns(con, table):
    return [r[1] for r in con.execute('PRAGMA table_info("%s")' % table.replace('"', '""'))]


# 1 -------------------------------------------------------------------------------------------------------------------
def _pragma_timeboxed(con, pragma, budget_s):
    deadline = time.monotonic() + budget_s
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
    try:
        return [r[0] for r in con.execute("PRAGMA %s" % pragma)], False
    except sqlite3.OperationalError as exc:
        if "interrupt" in str(exc).lower():
            return None, True
        raise
    finally:
        con.set_progress_handler(None, 0)


def check_integrity(db_path, budget_s=INTEGRITY_BUDGET_S):
    con = open_ro(db_path)
    try:
        present = tables_of(con)
        missing = sorted(set(SCHEMA_TABLES) - present)
        mode = "integrity_check"
        rows, timed_out = _pragma_timeboxed(con, mode, budget_s)
        notes = []
        if timed_out:
            notes.append("integrity_check exceeded the %.0f s budget; quick_check used instead (no index-content "
                         "verification)" % budget_s)
            mode = "quick_check"
            rows, timed_out = _pragma_timeboxed(con, mode, budget_s)
    finally:
        con.close()
    counts = {"schema_tables_expected": len(SCHEMA_TABLES), "schema_tables_missing": len(missing),
              "tables_in_db": len(present), "pragma": mode}
    ev = {}
    if missing:
        ev["missing_tables"] = missing
    if timed_out:
        notes.append("quick_check also exceeded the budget: integrity not established")
        status = "FAIL" if missing else "WARN"
        return result(1, "DB integrity", status, "%s not completed within %.0f s; %d schema table(s) missing"
                      % (mode, budget_s, len(missing)), counts, ev, notes)
    ok = rows == ["ok"]
    counts["pragma_messages"] = 0 if ok else len(rows)
    if not ok:
        ev["pragma_messages"] = ids(rows)
    status = "PASS" if ok and not missing else "FAIL"
    return result(1, "DB integrity", status, "%s %s; %d of %d schema tables present"
                  % (mode, "ok" if ok else "reported %d problem(s)" % len(rows), len(SCHEMA_TABLES) - len(missing),
                     len(SCHEMA_TABLES)), counts, ev, notes)


# 2 -------------------------------------------------------------------------------------------------------------------
def _continuity(con, table):
    prev, n, breaks = labdb.GENESIS, 0, []
    for rid, ph, h in con.execute('SELECT id, prev_hash, hash FROM "%s" ORDER BY id' % table):
        n += 1
        if ph != prev:
            breaks.append(rid)
        prev = h
    return n, breaks


def check_chains(con):
    present = tables_of(con)
    chained = sorted(t for t in present if {"prev_hash", "hash"} <= set(columns(con, t)))
    lab_tables = [t for t in labdb.TABLES if t in present]
    missing_lab = [t for t in labdb.TABLES if t not in present]
    notes, ev, bad = [], {}, []
    rows_verified = 0
    if not missing_lab:
        con.row_factory = sqlite3.Row
        try:
            out, triggers_ok = labdb.DB.verify(types.SimpleNamespace(con=con))
        finally:
            con.row_factory = None
        verifier = "lab.db.DB.verify"
        for t in lab_tables:
            n, first_bad = out[t]
            if first_bad is not None:
                bad.append("%s#%d" % (t, first_bad))
            else:
                rows_verified += n
    else:
        verifier = "none (lab tables missing)"
        triggers_ok = None
        notes.append("lab verifier not run: lab tables missing (%s); continuity-only check on present chained tables"
                     % ", ".join(missing_lab))
        ev["missing_lab_tables"] = missing_lab
    extra = [t for t in chained if t not in labdb.TABLES or missing_lab]
    for t in extra:
        n, breaks = _continuity(con, t)
        rows_verified += n - len(breaks)
        bad.extend("%s#%d" % (t, b) for b in breaks)
    if [t for t in chained if t not in labdb.TABLES]:
        notes.append("tables outside lab/db.py TABLES checked for prev_hash continuity only (no hash recomputation): "
                     + ", ".join(t for t in chained if t not in labdb.TABLES))
    if triggers_ok is False:
        ev["append_only_triggers"] = "missing for at least one chained table"
    counts = {"chained_tables": len(chained), "verified_full": 0 if missing_lab else len(lab_tables),
              "continuity_only": len(extra), "rows_ok": rows_verified, "broken_tables": len(bad)}
    if bad:
        ev["first_bad_row"] = ids(bad)
        notes.append("the lab verifier stops at the first bad row per table; rows after it are not counted as ok")
    status = "FAIL" if bad or triggers_ok is False or missing_lab else "PASS"
    return result(2, "Hash chains", status, "verifier %s: %d chained table(s), %d broken%s"
                  % (verifier, len(chained), len(bad), "" if triggers_ok is not False else "; triggers missing"),
                  counts, ev, notes)


# 3 -------------------------------------------------------------------------------------------------------------------
def check_marks(con, at):
    rep = nrep.build(con, at, at)
    acc = [r for r in rep["accounts"] if r["active"] and (r.get("started") is None or r["started"] <= at)]
    by = collections.Counter(r["mark_status"] for r in acc)
    stale = sorted(acc, key=lambda r: r["ledger"])
    ev = {}
    for st in ("STALE", "MISSING_MARK"):
        rows = [r for r in stale if r["mark_status"] == st]
        if rows:
            ev[st.lower()] = ids("%s (%s, %s)" % (r["ledger"], r["source"],
                                                  "age %.1f h" % (r["mark_age_s"] / 3600.0)
                                                  if r["mark_age_s"] is not None else "no mark") for r in rows)
    counts = {"active_accounts": len(acc), "fresh": by["FRESH"], "stale": by["STALE"],
              "missing_mark": by["MISSING_MARK"], "stale_threshold_s": nrep.STALE_S}
    status = "WARN" if by["STALE"] or by["MISSING_MARK"] else "PASS"
    return result(3, "Stale and missing marks", status, "at %s: FRESH %d, STALE %d, MISSING_MARK %d of %d active"
                  % (iso(at), by["FRESH"], by["STALE"], by["MISSING_MARK"], len(acc)), counts, ev,
                  ["net_report.freshness: a mark older than %d s at --at is STALE" % nrep.STALE_S])


# 4 -------------------------------------------------------------------------------------------------------------------
def latest_lane_artifact(db_path, at):
    d = os.path.join(os.path.dirname(os.path.abspath(db_path)), "artifacts", "_lane")
    if not os.path.isdir(d):
        return None, None
    days = sorted(f[:-5] for f in os.listdir(d) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f)
                  and nrec.day_start(f[:-5]) + DAY <= at)
    return (days[-1], os.path.join(d, days[-1] + ".json")) if days else (None, None)


def check_reports(con, db_path, at):
    day, path = latest_lane_artifact(db_path, at)
    if not day:
        return result(4, "Reports vs ledger", "WARN", "no complete-day lane report artifact at or before --at",
                      {"artifacts": 0})
    try:
        with open(path, encoding="utf-8") as fh:
            lane = json.load(fh)
        lane_acc = lane["accounts"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return result(4, "Reports vs ledger", "FAIL", "lane report %s unreadable: %s" % (day, type(exc).__name__),
                      {"artifacts": 1}, {"artifact": os.path.basename(path)})
    end = nrec.day_start(day) + DAY
    net = nrep.build(con, at, end - 0.001)          # same cutoff as the lane report: last mark with ts < day end
    res = nrec.reconcile(lane, net, con, day)
    causes = collections.Counter(r["cause"] for r in res["accounts"])
    lane_led = {a["ledger"] for a in lane_acc}
    only_ledger = sorted(r["ledger"] for r in res["accounts"] if r["ledger"] not in lane_led and r["lane_mark"])
    total_gap = (lane.get("net_total") - sum(a.get("net") or 0.0 for a in lane_acc)
                 if isinstance(lane.get("net_total"), (int, float)) else 0.0)
    ev = {"artifact": "artifacts/_lane/%s.json" % day}
    for c in ("UNEXPLAINED", "TIMING_MARK"):
        rows = [r for r in res["accounts"] if r["cause"] == c]
        if rows:
            ev[c.lower()] = ids("%s diff %+.4f lane_ok=%s" % (r["ledger"], r["diff"], r["lane_ok"]) for r in rows)
    if only_ledger:
        ev["marked_in_ledger_not_in_report"] = ids(only_ledger)
    if abs(total_gap) > nrec.TOL:
        ev["net_total_gap"] = round(total_gap, 6)
    counts = {"day": day, "accounts_report": res["lane_accounts"], "accounts_ledger": res["net_accounts"],
              "same_mark": causes["SAME_MARK"], "timing_mark": causes["TIMING_MARK"],
              "unexplained": causes["UNEXPLAINED"], "marked_not_in_report": len(only_ledger),
              "difference_total": round(res["difference"], 6)}
    if res["status"] != "RECONCILED" or causes["UNEXPLAINED"] or abs(total_gap) > nrec.TOL:
        status = "FAIL"
    elif causes["TIMING_MARK"] or only_ledger:
        status = "WARN"
    else:
        status = "PASS"
    return result(4, "Reports vs ledger", status, "lane report %s vs sim_equity at %s: %s (%d same mark, %d timing, "
                  "%d unexplained)" % (day, iso(end), res["status"], causes["SAME_MARK"], causes["TIMING_MARK"],
                                       causes["UNEXPLAINED"]), counts, ev,
                  ["net_reconcile.reconcile against net_report.build cut at the day end; tolerance %.3f" % nrec.TOL])


# 5 -------------------------------------------------------------------------------------------------------------------
NUMERIC = (("sim_fills", "px", False), ("sim_fills", "qty", False), ("sim_fills", "fee", False),
           ("sim_fills", "mid", True), ("sim_orders", "qty", True), ("sim_orders", "limit_px", True),
           ("sim_funding", "price", False), ("sim_funding", "rate", False), ("sim_funding", "amount", False),
           ("sim_funding", "qty", False), ("sim_equity", "equity", False))


def _bad_numbers(con, table, col, nullable):
    c = '"%s"' % col
    cond = ("(%s IS NOT NULL AND (typeof(%s) NOT IN ('integer','real') OR %s != %s OR %s > 1e308 OR %s < -1e308))"
            % ((c,) * 6))
    if not nullable:
        cond = "(%s IS NULL OR %s)" % (c, cond)
    return [r[0] for r in con.execute('SELECT id FROM "%s" WHERE %s ORDER BY id' % (table, cond))]


def _funding_without_position(con):
    fills = collections.defaultdict(list)
    for exp, inst, ts, side, qty, rid in con.execute(
            "SELECT exp_id, instrument, ts, side, qty, id FROM sim_fills ORDER BY ts, id"):
        fills[(exp, inst)].append((ts, (1 if side == "buy" else -1) * (qty or 0.0)))
    cum = {}
    for k, rows in fills.items():
        tss, pos, run = [], [], 0.0
        for ts, q in rows:
            run += q
            tss.append(ts)
            pos.append(run)
        cum[k] = (tss, pos)
    none, sign, size, n = [], [], [], 0
    for rid, exp, inst, settle, qty in con.execute(
            "SELECT id, exp_id, instrument, settle_ts, qty FROM sim_funding ORDER BY id"):
        n += 1
        tss, pos = cum.get((exp, inst), ((), ()))
        i = bisect.bisect_right(tss, settle)
        p = pos[i - 1] if i else 0.0
        if abs(p) <= POS_EPS:
            none.append(rid)
        elif qty is not None and abs(qty) > POS_EPS and (p > 0) != (qty > 0):
            sign.append(rid)
        elif qty is not None and abs(p - qty) > 1e-6 * max(1.0, abs(qty)):
            size.append(rid)
    return n, none, sign, size


def check_sanity(con):
    present = tables_of(con)
    need = ("sim_fills", "sim_orders", "sim_funding", "sim_equity")
    if any(t not in present for t in need):
        return result(5, "Duplicates and sign sanity", "FAIL", "sim tables missing",
                      evidence={"missing_tables": [t for t in need if t not in present]})
    fail, warn, ev = {}, {}, {}

    def dup(table, col):
        out = []
        for _, rows in con.execute('SELECT "%s", GROUP_CONCAT(id) FROM "%s" GROUP BY "%s" HAVING COUNT(*) > 1 '
                                   'ORDER BY MIN(id)' % (col, table, col)):
            out.extend("%s#%s" % (table, i) for i in sorted(int(x) for x in rows.split(",")))
        return out

    fail["duplicate_fill_id"] = dup("sim_fills", "fill_id")
    fail["duplicate_order_id"] = dup("sim_orders", "order_id")
    fail["negative_fee"] = ["sim_fills#%d" % r for (r,) in con.execute("SELECT id FROM sim_fills WHERE fee < 0 "
                                                                        "ORDER BY id")]
    nonfin = []
    for t, c, nullable in NUMERIC:
        nonfin.extend("%s.%s#%d" % (t, c, r) for r in _bad_numbers(con, t, c, nullable))
    fail["non_finite_number"] = nonfin
    fail["fill_price_le_0"] = ["sim_fills#%d" % r for (r,) in con.execute(
        "SELECT id FROM sim_fills WHERE px <= 0 ORDER BY id")]
    fail["fill_qty_le_0"] = ["sim_fills#%d" % r for (r,) in con.execute(
        "SELECT id FROM sim_fills WHERE qty <= 0 ORDER BY id")]
    n_fund, none, sign, size = _funding_without_position(con)
    warn["funding_no_open_position"] = ["sim_funding#%d" % r for r in none]
    warn["funding_sign_differs"] = ["sim_funding#%d" % r for r in sign]
    warn["funding_qty_differs"] = ["sim_funding#%d" % r for r in size]
    counts = {"fills": con.execute("SELECT COUNT(*) FROM sim_fills").fetchone()[0],
              "orders": con.execute("SELECT COUNT(*) FROM sim_orders").fetchone()[0], "funding_rows": n_fund}
    for k, v in list(fail.items()) + list(warn.items()):
        counts[k] = len(v)
        if v:
            ev[k] = ids(v)
    notes = ["funding rows are WARN only: the open position is rebuilt from sim_fills (same exp_id and instrument "
             "string, fills with ts <= settle_ts); a lane that books funding on a position snapshot, a fill stamped "
             "after the settlement second, or a different instrument spelling gives a hit without an accounting error "
             "- inspect the ids before acting"]
    status = "FAIL" if any(fail.values()) else "WARN" if any(warn.values()) else "PASS"
    return result(5, "Duplicates and sign sanity", status, "%d FAIL finding(s), %d WARN finding(s) over %d fills, %d "
                  "orders, %d funding rows" % (sum(map(len, fail.values())), sum(map(len, warn.values())),
                                                counts["fills"], counts["orders"], n_fund), counts, ev, notes)


# 6 -------------------------------------------------------------------------------------------------------------------
def check_protocols(root=HERE, matrix_path=None, readiness_path=None, hfc1=HFC1):
    matrix_path = matrix_path or os.path.join(root, "research", "desk", "GATE_MATRIX.json")
    readiness_path = readiness_path or os.path.join(root, "research", "desk", "NOV14_READINESS.md")
    try:
        matrix = n14.load(matrix_path)
    except (OSError, ValueError) as exc:
        return result(6, "Protocol drift", "FAIL", "gate matrix unreadable: %s" % type(exc).__name__)
    errs = n14.verify_hashes(matrix, readiness_path, root)
    p = os.path.join(root, hfc1["path"])
    got = n14.sha256_file(p, hfc1["prefix_bytes"]) if os.path.isfile(p) else "MISSING"
    hfc_ok = got == hfc1["sha256"]
    ev = {}
    if errs:
        ev["verify_hashes"] = ids(errs)
    if not hfc_ok:
        ev["hfc1_rules_prefix"] = "%s first %d bytes: expected %s, got %s" % (
            hfc1["path"], hfc1["prefix_bytes"], hfc1["sha256"][:12], got[:12])
    n = len(matrix.get("protocol_identities", []))
    counts = {"pinned_identities": n, "problems": len(errs), "hfc1_prefix_ok": hfc_ok}
    return result(6, "Protocol drift", "PASS" if not errs and hfc_ok else "FAIL",
                  "%d pinned identities, %d problem(s); HFC-1 rules prefix (%d bytes) %s"
                  % (n, len(errs), hfc1["prefix_bytes"], "ok" if hfc_ok else "MISMATCH"), counts, ev)


# 7 -------------------------------------------------------------------------------------------------------------------
def check_locked(roots, locked=LOCKED):
    bad, n = [], 0
    for label, root in roots:
        for rel, want in sorted(locked.items()):
            n += 1
            p = os.path.join(root, rel)
            got = sha256_path(p) if os.path.isfile(p) else "MISSING"
            if got != want:
                bad.append("%s:%s expected %s got %s" % (label, rel, want[:8], got[:8]))
    return result(7, "Locked code", "FAIL" if bad else "PASS", "%d of %d locked file hashes match (%s)"
                  % (n - len(bad), n, ", ".join(label for label, _ in roots)),
                  {"files_checked": n, "mismatches": len(bad)}, {"mismatch": bad} if bad else {})


# 8 -------------------------------------------------------------------------------------------------------------------
RAN = re.compile(r"^Ran (\d+) tests? in ([0-9.]+)s", re.M)
VERDICT = re.compile(r"^(OK|FAILED)\b(?: \(([^)]*)\))?\s*$", re.M)
FAILING = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)
BLOCKED = re.compile(r"^blocked attempts: (.*)$", re.M)


def parse_suite_log(text):
    ran = RAN.findall(text)
    verdict = VERDICT.findall(text)
    failing = sorted({"%s %s" % (k, cls if cls.endswith(name) else "%s.%s" % (cls, name))
                      for k, name, cls in FAILING.findall(text)})
    blocked = BLOCKED.findall(text)
    out = {"ran": int(ran[-1][0]) if ran else None, "verdict": verdict[-1][0] if verdict else None,
           "detail": verdict[-1][1] if verdict else None, "failing": failing,
           "blocked": blocked[-1].strip() if blocked else None, "runs_in_log": len(ran)}
    return out


def check_suite_log(path):
    if not path:
        return result(8, "Test-failure log", "SKIP", "no --suite-log given")
    with open(path, encoding="utf-8", errors="replace") as fh:
        p = parse_suite_log(fh.read())
    counts = {"ran": p["ran"], "verdict": p["verdict"], "detail": p["detail"], "failing": len(p["failing"]),
              "runs_in_log": p["runs_in_log"]}
    ev = {"log": os.path.basename(path)}
    if p["failing"]:
        ev["failing_tests"] = ids(p["failing"])
    if p["blocked"]:
        ev["guard"] = p["blocked"]
    if p["verdict"] is None or p["ran"] is None:
        status, summ = "WARN", "no complete unittest summary (Ran/OK/FAILED) in the log"
    elif p["verdict"] == "FAILED" or p["failing"]:
        status, summ = "FAIL", "Ran %d: FAILED (%s), %d failing test(s)" % (p["ran"], p["detail"], len(p["failing"]))
    else:
        status, summ = "PASS", "Ran %d: OK%s" % (p["ran"], " (%s)" % p["detail"] if p["detail"] else "")
    return result(8, "Test-failure log", status, summ, counts, ev)


# run -----------------------------------------------------------------------------------------------------------------
def run(db_path, at, suite_log=None, root=HERE, prod_root=PROD_ROOT, matrix_path=None, readiness_path=None,
        hfc1=HFC1, locked=LOCKED, integrity_budget=INTEGRITY_BUDGET_S):
    if suite_log and not os.path.isfile(suite_log):
        raise BadInput("no suite log: %s" % suite_log)
    checks = [check_integrity(db_path, integrity_budget)]
    con = open_ro(db_path)
    try:
        con.execute("BEGIN")                   # one read snapshot for checks 2-5
        for cid, name, fn in ((2, "Hash chains", lambda: check_chains(con)),
                              (3, "Stale and missing marks", lambda: check_marks(con, at)),
                              (4, "Reports vs ledger", lambda: check_reports(con, db_path, at)),
                              (5, "Duplicates and sign sanity", lambda: check_sanity(con))):
            try:
                checks.append(fn())
            except Exception as exc:          # a crash in a reused tool is itself a finding; the other checks still run
                where = traceback.extract_tb(exc.__traceback__)[-1]
                checks.append(result(cid, name, "FAIL", "check crashed: %s: %s" % (type(exc).__name__, exc),
                                     evidence={"raised_in": "%s:%d (%s)" % (os.path.relpath(where.filename, HERE),
                                                                            where.lineno, where.name)}))
        con.execute("ROLLBACK")
    finally:
        con.close()
    checks.append(check_protocols(root, matrix_path, readiness_path, hfc1))
    roots = [("dev", root)] + ([("prod", prod_root)] if prod_root else [])
    checks.append(check_locked(roots, locked))
    checks.append(check_suite_log(suite_log))
    overall = worst([c["status"] for c in checks])
    return {"tool": "research/tools/lab_qc.py", "rule": "director order 66 C (research/reviews/INBOX.md 2026-11-09)",
            "db": os.path.abspath(db_path), "at": iso(at), "overall": overall,
            "counts": dict(collections.Counter(c["status"] for c in checks)), "checks": checks}


def markdown(rep):
    out = ["# Lab-QC (ordre 66 C)", "", "- DB: `%s` (read-only)" % rep["db"], "- Tidspunkt (--at): %s" % rep["at"],
           "- **Samlet: %s** (%s)" % (rep["overall"], ", ".join("%s %d" % (k, rep["counts"][k])
                                                                  for k in ("PASS", "WARN", "FAIL", "SKIP")
                                                                  if k in rep["counts"])), "",
           "| # | Kontrol | Status | Resumé |", "|---|---|---|---|"]
    for c in rep["checks"]:
        out.append("| %d | %s | %s | %s |" % (c["id"], c["name"], c["status"], c["summary"].replace("|", "/")))
    for c in rep["checks"]:
        out += ["", "## %d. %s: %s" % (c["id"], c["name"], c["status"]), ""]
        if c["counts"]:
            out.append("- Tal: " + ", ".join("%s=%s" % (k, c["counts"][k]) for k in sorted(c["counts"])))
        for k in sorted(c["evidence"]):
            v = c["evidence"][k]
            out.append("- %s: %s" % (k, ", ".join(map(str, v)) if isinstance(v, list) else v))
        for n in c["notes"]:
            out.append("- Note: %s" % n)
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--at", help="UTC time YYYY-MM-DDTHH:MM:SSZ (default: now)")
    ap.add_argument("--out", help="write the markdown report here")
    ap.add_argument("--json", action="store_true", help="print JSON instead of markdown on stdout")
    ap.add_argument("--suite-log", help="guarded-suite log to parse (check 8)")
    ap.add_argument("--integrity-budget", type=float, default=INTEGRITY_BUDGET_S, help="seconds per integrity pragma")
    ap.add_argument("--root", default=HERE, help="dev checkout for checks 6-7 (default: this repo)")
    ap.add_argument("--prod-root", default=PROD_ROOT, help="production checkout for check 7 (read-only)")
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        at = parse_at(a.at) if a.at else int(time.time())
        if not a.integrity_budget > 0:
            raise BadInput("--integrity-budget must be > 0")
        rep = run(a.db, at, a.suite_log, root=a.root, prod_root=a.prod_root, integrity_budget=a.integrity_budget)
    except BadInput as exc:
        print("lab_qc: %s" % exc, file=sys.stderr)
        return 2
    md = markdown(rep)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(md)
    print(json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False) if a.json else md, end="" if not a.json
          else "\n")
    return 1 if rep["overall"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
