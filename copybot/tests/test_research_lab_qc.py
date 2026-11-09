"""Director order 66 C: offline lab quality control (research/tools/lab_qc.py). Synthetic temp DBs with planted faults;
the DB stays byte-identical, no network (socket patched), deterministic output. The real lab.db is never opened."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lab import db as labdb  # noqa: E402
from research.tools import lab_qc as qc  # noqa: E402

END = 1794182400                  # 2026-11-09 00:00:00 UTC (end of the lane-report day 2026-11-08)
DAY = "2026-11-08"
AT = END + 14 * 3600              # 2026-11-09T14:00:00Z
AT_S = "2026-11-09T14:00:00Z"
L1, L2 = "LANE_aaaaaaaaaa", "LANE_bbbbbbbbbb"
NET_CALLS = []


def _no_net(*a, **k):
    NET_CALLS.append(a)
    raise OSError("network disabled in test")


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def make_db(d, stale=False, broken_chain=False, dup_fill=False, neg_fee=False, inf_px=False, zero_qty=False, orphan_funding=False,
            drop_table=None):
    path = os.path.join(d, "data", "lab", "lab.db")
    db = labdb.DB(path)
    a = db.append
    for led, src in ((L1, "straks"), (L2, "pairs")):
        a("events", ts=END - 2 * 86400, kind="lane.started", actor="t", exp_id=led,
          payload={"source": src, "name": led[-4:]})
        a("events", ts=END - 2 * 86400, kind="paper.started", actor="t", exp_id=led, payload={"capital": 10000})
    a("sim_orders", order_id="o1", exp_id=L1, ts=END - 86400, instrument="BTCUSDT", side="buy", qty=1.0,
      limit_px=None, style="market", reduce_only=0, signal_ref="s", cost_model="c")
    a("sim_orders", order_id="o2", exp_id=L2, ts=END - 86400, instrument="ETHUSDT", side="sell", qty=2.0,
      limit_px=None, style="market", reduce_only=0, signal_ref="s", cost_model="c")
    a("sim_fills", fill_id="f1", order_id="o1", exp_id=L1, ts=END - 86400, instrument="BTCUSDT", side="buy",
      px=100.0, qty=1.0, fee=0.05, slippage=0.0, liquidity="taker", mid=100.0, book_ts=END - 86400)
    a("sim_fills", fill_id="f2", order_id="o2", exp_id=L2, ts=END - 86400, instrument="ETHUSDT", side="sell",
      px=50.0, qty=2.0, fee=0.05, slippage=0.0, liquidity="taker", mid=50.0, book_ts=END - 86400)
    if dup_fill:
        db.con.execute("DROP INDEX sim_fills_fid")
        a("sim_fills", fill_id="f1", order_id="o1", exp_id=L1, ts=END - 86000, instrument="BTCUSDT", side="buy",
          px=100.0, qty=1.0, fee=0.05, slippage=0.0, liquidity="taker", mid=100.0, book_ts=END - 86000)
    if neg_fee or inf_px or zero_qty:
        a("sim_fills", fill_id="f3", order_id="o2", exp_id=L2, ts=END - 80000, instrument="XRPUSDT", side="buy",
          px=float("inf") if inf_px else 1.0, qty=0.0 if zero_qty else 1.0, fee=-0.01 if neg_fee else 0.01,
          slippage=0.0, liquidity="taker", mid=1.0, book_ts=END - 80000)
    a("sim_funding", exp_id=L1, ts=END - 57600, settle_ts=END - 57600, instrument="BTCUSDT", qty=1.0, rate=1e-4,
      price=100.0, amount=-0.01)
    a("sim_funding", exp_id=L2, ts=END - 57600, settle_ts=END - 57600, instrument="ETHUSDT", qty=-2.0, rate=1e-4,
      price=50.0, amount=0.01)
    if orphan_funding:
        a("sim_funding", exp_id=L1, ts=END - 57600, settle_ts=END - 57600, instrument="SOLUSDT", qty=3.0, rate=1e-4,
          price=10.0, amount=-0.003)
    last = AT - (3 * 3600 if stale else 600)
    for led in (L1, L2):
        for ts, eq in ((END - 1800, 10005.0), (last, 10010.0)):
            a("sim_equity", exp_id=led, ts=ts, equity=eq, cash=eq, exposure=100.0, peak=eq, drawdown=0.0)
    if broken_chain:
        trig = db.con.execute("SELECT sql FROM sqlite_master WHERE name='sim_orders_no_update'").fetchone()[0]
        db.con.execute("DROP TRIGGER sim_orders_no_update")
        db.con.execute("UPDATE sim_orders SET qty=5.0 WHERE order_id='o2'")
        db.con.execute(trig)
    if drop_table:
        db.con.execute("DROP TABLE %s" % drop_table)
    db.close()
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=DELETE")      # self-contained file: a read-only open needs no -wal/-shm
    con.close()
    lane = os.path.join(d, "data", "lab", "artifacts", "_lane")
    os.makedirs(lane)
    with open(os.path.join(lane, DAY + ".json"), "w") as fh:
        json.dump({"day": DAY, "net_total": 10.0, "accounts": [{"ledger": L1, "net": 5.0}, {"ledger": L2, "net": 5.0}]},
                  fh)
    with open(os.path.join(lane, "2026-11-09.json"), "w") as fh:     # not complete at AT: must be ignored
        json.dump({"day": "2026-11-09", "accounts": [{"ledger": L1, "net": 999.0}]}, fh)
    return path


def make_root(d):
    """A checkout copy for checks 6-7: a synthetic pinned file, the HFC-1 protocol and the two locked files."""
    root = os.path.join(d, "root")
    for rel in (qc.HFC1["path"], "lab/straks.py", "lab/pairs.py"):
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        shutil.copyfile(os.path.join(HERE, rel), os.path.join(root, rel))
    pin = os.path.join(root, "research", "P_TEST.md")
    with open(pin, "w") as fh:
        fh.write("locked synthetic protocol\n")
    ids = [{"id": "P_TEST", "path": "research/P_TEST.md", "commit": "abcdef1", "sha256": sha(pin)},
           {"id": "HFC1_PROTOCOL", "path": qc.HFC1["path"], "commit": "48a0a63", "sha256": qc.HFC1["sha256"],
            "prefix_bytes": qc.HFC1["prefix_bytes"]}]
    os.makedirs(os.path.join(root, "research", "desk"))
    with open(os.path.join(root, "research", "desk", "GATE_MATRIX.json"), "w") as fh:
        json.dump({"protocol_identities": ids, "gates": []}, fh)
    rows = "\n".join("| `%s` | `%s` | `%s` | `%s` |" % (r["id"], r["path"], r["commit"], r["sha256"]) for r in ids)
    with open(os.path.join(root, "research", "desk", "NOV14_READINESS.md"), "w") as fh:
        fh.write("<!-- protocol-identities:start -->\n| id | fil | commit | sha256 |\n|---|---|---|---|\n%s\n"
                 "<!-- protocol-identities:end -->\n" % rows)
    return root


class Base(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(socket, "socket", _no_net), mock.patch.object(socket, "create_connection", _no_net),
                  mock.patch.object(socket, "getaddrinfo", _no_net)):
            p.start()
            self.addCleanup(p.stop)
        NET_CALLS.clear()
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.root = make_root(self.d)
        self.prod = os.path.join(self.d, "prod")
        shutil.copytree(os.path.join(self.root, "lab"), os.path.join(self.prod, "lab"))

    def tearDown(self):
        self.assertEqual(NET_CALLS, [])

    def run_qc(self, db, **kw):
        kw.setdefault("root", self.root)
        kw.setdefault("prod_root", self.prod)
        return qc.run(db, AT, **kw)

    def check(self, rep, cid):
        return next(c for c in rep["checks"] if c["id"] == cid)


class Clean(Base):
    def test_all_clean(self):
        db = make_db(self.d)
        rep = self.run_qc(db)
        self.assertEqual({c["id"]: c["status"] for c in rep["checks"]},
                         {1: "PASS", 2: "PASS", 3: "PASS", 4: "PASS", 5: "PASS", 6: "PASS", 7: "PASS", 8: "SKIP"})
        self.assertEqual(rep["overall"], "PASS")
        self.assertEqual(self.check(rep, 4)["counts"]["day"], DAY)            # the incomplete 11-09 artifact is skipped
        self.assertEqual(self.check(rep, 4)["counts"]["same_mark"], 2)
        self.assertEqual(self.check(rep, 2)["counts"]["verified_full"], len(labdb.TABLES))

    def test_db_byte_identical_and_no_side_files(self):
        db = make_db(self.d)
        before, files = sha(db), sorted(os.listdir(os.path.dirname(db)))
        mtime = os.stat(db).st_mtime_ns
        self.run_qc(db)
        self.assertEqual(sha(db), before)
        self.assertEqual(os.stat(db).st_mtime_ns, mtime)
        self.assertEqual(sorted(os.listdir(os.path.dirname(db))), files)

    def test_deterministic(self):
        db = make_db(self.d)
        a, b = self.run_qc(db), self.run_qc(db)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(qc.markdown(a), qc.markdown(b))

    def test_connection_is_read_only(self):
        con = qc.open_ro(make_db(self.d))
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("CREATE TABLE x(a)")
        con.close()


class Faults(Base):
    def test_broken_hash_chain(self):
        rep = self.run_qc(make_db(self.d, broken_chain=True))
        c = self.check(rep, 2)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["evidence"]["first_bad_row"], ["sim_orders#2"])
        self.assertEqual(rep["overall"], "FAIL")

    def test_duplicate_fill_id(self):
        rep = self.run_qc(make_db(self.d, dup_fill=True))
        c = self.check(rep, 5)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["counts"]["duplicate_fill_id"], 2)
        self.assertEqual(c["evidence"]["duplicate_fill_id"], ["sim_fills#1", "sim_fills#3"])
        self.assertEqual(self.check(rep, 2)["status"], "PASS")              # appended through the chain: chain intact

    def test_negative_fee(self):
        c = self.check(self.run_qc(make_db(self.d, neg_fee=True)), 5)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["evidence"]["negative_fee"], ["sim_fills#3"])
        self.assertEqual(c["counts"]["duplicate_fill_id"], 0)

    def test_inf_price(self):
        c = self.check(self.run_qc(make_db(self.d, inf_px=True)), 5)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["evidence"]["non_finite_number"], ["sim_fills.px#3"])
        self.assertEqual(c["counts"]["fill_qty_le_0"], 0)

    def test_zero_qty_fill_and_crash_isolation(self):
        """A qty-0 fill on a flat instrument makes net_report divide by zero; lab_qc reports the crash as FAIL for
        checks 3 and 4 and still runs every other check."""
        rep = self.run_qc(make_db(self.d, zero_qty=True))
        c = self.check(rep, 5)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["evidence"]["fill_qty_le_0"], ["sim_fills#3"])
        for cid in (3, 4):
            self.assertEqual(self.check(rep, cid)["status"], "FAIL")
            self.assertIn("ZeroDivisionError", self.check(rep, cid)["summary"])
            self.assertIn("net_report.py", self.check(rep, cid)["evidence"]["raised_in"])
        self.assertEqual([c["id"] for c in rep["checks"]], list(range(1, 9)))

    def test_funding_without_position_is_warn_only(self):
        rep = self.run_qc(make_db(self.d, orphan_funding=True))
        c = self.check(rep, 5)
        self.assertEqual(c["status"], "WARN")
        self.assertEqual(c["evidence"]["funding_no_open_position"], ["sim_funding#3"])
        self.assertEqual(c["counts"]["funding_sign_differs"], 0)
        self.assertEqual(rep["overall"], "WARN")

    def test_stale_mark(self):
        rep = self.run_qc(make_db(self.d, stale=True))
        c = self.check(rep, 3)
        self.assertEqual(c["status"], "WARN")
        self.assertEqual((c["counts"]["stale"], c["counts"]["fresh"]), (2, 0))
        self.assertTrue(c["evidence"]["stale"][0].startswith(L1))
        self.assertEqual(self.check(rep, 4)["status"], "PASS")             # the day-end marks are still reconciled

    def test_report_differs_from_ledger(self):
        db = make_db(self.d)
        p = os.path.join(os.path.dirname(db), "artifacts", "_lane", DAY + ".json")
        with open(p, "w") as fh:
            json.dump({"day": DAY, "net_total": 12.0, "accounts": [{"ledger": L1, "net": 7.0},
                                                                    {"ledger": L2, "net": 5.0}]}, fh)
        c = self.check(self.run_qc(db), 4)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["counts"]["unexplained"], 1)
        self.assertTrue(c["evidence"]["unexplained"][0].startswith(L1))

    def test_report_internal_total_mismatch(self):
        db = make_db(self.d)
        p = os.path.join(os.path.dirname(db), "artifacts", "_lane", DAY + ".json")
        with open(p, "w") as fh:
            json.dump({"day": DAY, "net_total": 11.0, "accounts": [{"ledger": L1, "net": 5.0},
                                                                    {"ledger": L2, "net": 5.0}]}, fh)
        c = self.check(self.run_qc(db), 4)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["evidence"]["net_total_gap"], 1.0)

    def test_no_artifact_is_warn(self):
        db = make_db(self.d)
        shutil.rmtree(os.path.join(os.path.dirname(db), "artifacts"))
        self.assertEqual(self.check(self.run_qc(db), 4)["status"], "WARN")

    def test_pin_mismatch_in_temp_copy(self):
        with open(os.path.join(self.root, "research", "P_TEST.md"), "a") as fh:
            fh.write("drift\n")
        rep = self.run_qc(make_db(self.d))
        c = self.check(rep, 6)
        self.assertEqual(c["status"], "FAIL")
        self.assertTrue(c["evidence"]["verify_hashes"][0].startswith("HASH_MISMATCH research/P_TEST.md"))
        self.assertEqual(rep["overall"], "FAIL")

    def test_hfc1_rules_prefix(self):
        p = os.path.join(self.root, qc.HFC1["path"])
        with open(p, "ab") as fh:                                     # appended notes after the rules: still locked
            fh.write(b"\nappend-only note\n")
        db = make_db(self.d)
        self.assertEqual(self.check(self.run_qc(db), 6)["status"], "PASS")
        with open(p, "r+b") as fh:
            fh.seek(100)
            b = fh.read(1)
            fh.seek(100)
            fh.write(b"X" if b != b"X" else b"Y")
        c = self.check(self.run_qc(db), 6)
        self.assertEqual(c["status"], "FAIL")
        self.assertFalse(c["counts"]["hfc1_prefix_ok"])

    def test_locked_code_mismatch_in_prod_copy(self):
        with open(os.path.join(self.prod, "lab", "straks.py"), "a") as fh:
            fh.write("# drift\n")
        c = self.check(self.run_qc(make_db(self.d)), 7)
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["counts"], {"files_checked": 4, "mismatches": 1})
        self.assertTrue(c["evidence"]["mismatch"][0].startswith("prod:lab/straks.py expected 7a110f1f"))

    def test_missing_schema_table(self):
        rep = self.run_qc(make_db(self.d, drop_table="sim_cancels"))
        self.assertEqual(self.check(rep, 1)["status"], "FAIL")
        self.assertEqual(self.check(rep, 1)["evidence"]["missing_tables"], ["sim_cancels"])
        self.assertEqual(self.check(rep, 2)["status"], "FAIL")

    def test_integrity_time_box(self):
        db = make_db(self.d)
        calls = []

        def fake(con, pragma, budget):
            calls.append(pragma)
            return (["ok"], False) if pragma == "quick_check" and fallback_ok else (None, True)
        fallback_ok = True
        with mock.patch.object(qc, "_pragma_timeboxed", fake):
            c = qc.check_integrity(db, 5.0)
        self.assertEqual((c["status"], c["counts"]["pragma"]), ("PASS", "quick_check"))
        self.assertIn("quick_check used instead", c["notes"][0])
        fallback_ok = False
        with mock.patch.object(qc, "_pragma_timeboxed", fake):
            c = qc.check_integrity(db, 5.0)
        self.assertEqual(c["status"], "WARN")
        self.assertEqual(calls, ["integrity_check", "quick_check"] * 2)

    def test_progress_handler_interrupts(self):
        con = qc.open_ro(make_db(self.d))
        self.assertEqual(qc._pragma_timeboxed(con, "integrity_check", -1.0), (None, True))
        self.assertEqual(qc._pragma_timeboxed(con, "integrity_check", 60.0), (["ok"], False))
        con.close()


class SuiteLog(Base):
    def write(self, text):
        p = os.path.join(self.d, "suite.log")
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def test_ok(self):
        c = qc.check_suite_log(self.write("x\n----\nRan 1766 tests in 849.609s\n\nOK (skipped=1)\n"
                                          "blocked attempts: network 0, download 0, file-guard 0\n"))
        self.assertEqual((c["status"], c["counts"]["ran"], c["counts"]["failing"]), ("PASS", 1766, 0))
        self.assertEqual(c["evidence"]["guard"], "network 0, download 0, file-guard 0")

    def test_failed(self):
        c = qc.check_suite_log(self.write(
            "FAIL: test_only_n4_kimchi_names_the_host (test_research_gates.UpbitHost.test_only_n4_kimchi_names_the_host)\n"
            "ERROR: test_b (test_x.C)\n----\nRan 1749 tests in 837.249s\n\nFAILED (failures=1, errors=1, skipped=1)\n"))
        self.assertEqual(c["status"], "FAIL")
        self.assertEqual(c["evidence"]["failing_tests"],
                         ["ERROR test_x.C.test_b",
                          "FAIL test_research_gates.UpbitHost.test_only_n4_kimchi_names_the_host"])

    def test_incomplete_and_absent(self):
        self.assertEqual(qc.check_suite_log(self.write("Traceback ...\n"))["status"], "WARN")
        self.assertEqual(qc.check_suite_log(None)["status"], "SKIP")


class Cli(Base):
    def main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = qc.main(list(args))
        return code, out.getvalue()

    def test_exit_codes_and_outputs(self):
        db = make_db(self.d)
        md = os.path.join(self.d, "qc.md")
        code, out = self.main("--db", db, "--at", AT_S, "--root", self.root, "--prod-root", self.prod, "--out", md,
                              "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["overall"], "PASS")
        with open(md) as fh:
            self.assertIn("**Samlet: PASS**", fh.read())
        with open(os.path.join(self.root, "research", "P_TEST.md"), "a") as fh:
            fh.write("drift\n")
        code, out = self.main("--db", db, "--at", AT_S, "--root", self.root, "--prod-root", self.prod)
        self.assertEqual(code, 1)
        self.assertIn("| 6 | Protocol drift | FAIL |", out)

    def test_bad_input(self):
        db = make_db(self.d)
        self.assertEqual(self.main("--db", db, "--at", "2026-11-09 14:00")[0], 2)
        self.assertEqual(self.main("--db", os.path.join(self.d, "nope.db"), "--at", AT_S)[0], 2)
        self.assertEqual(self.main("--db", db, "--at", AT_S, "--suite-log", os.path.join(self.d, "nope.log"))[0], 2)
        self.assertEqual(self.main("--bogus")[0], 2)


if __name__ == "__main__":
    unittest.main()
