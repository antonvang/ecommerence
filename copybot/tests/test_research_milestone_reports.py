"""Milestone report tools (research/desk/MILESTONE_REPORT_TOOLS.md): HFC-1 3 d outcome (hfc1_report3d.py), STRAKS 7 d
(straks_report.py) and PAR-BOG 14 d (parbog_report.py). Synthetic databases only; no network (socket patched); the
production lab.db is never opened here."""
import datetime as dt
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
from contextlib import closing, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
sys.path.insert(0, HERE)
import hfc1_report3d as hr  # noqa: E402
import parbog_report as pb  # noqa: E402
import straks_report as sr  # noqa: E402

DAY = dt.date(2026, 11, 4)
PROD = "/home/anton/ecommerence/copybot/data/lab/lab.db"
TOOLS = ("hfc1_report3d.py", "straks_report.py", "parbog_report.py")


def _no_net(*a, **k):
    raise AssertionError("network used")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(socket, "socket", _no_net), mock.patch.object(socket, "create_connection", _no_net),
                  mock.patch.object(socket, "getaddrinfo", _no_net)):
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.mkdtemp(prefix="milestone_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = os.path.join(self.tmp, "out")

    def assert_untouched(self, db, before):
        self.assertEqual(sha(db), before)
        for side in ("-wal", "-shm", "-journal"):
            self.assertFalse(os.path.exists(db + side), side)

    def quiet(self, fn, *a, **k):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = fn(*a, **k)
        return rc, json.loads(buf.getvalue().strip().splitlines()[-1])


# ---- HFC-1 ------------------------------------------------------------------------------------------------------------

class HFC1(Base):
    def make(self, **kw):
        self.db, self.cdir = hr.synthetic(self.tmp, **kw)
        self.due = hr.window(DAY, "3d")[2]

    def report(self, now=None, **kw):
        rep, _ = hr.run(self.db, self.cdir, self.out, [DAY], "3d", now or self.due, pins={}, **kw)
        return rep, rep["cohorts"][0]

    def test_window_and_due_time(self):
        t0, t1, due = hr.window(DAY, "3d")
        self.assertEqual(hr.utc(t0), "2026-11-05 00:00:00 UTC")
        self.assertEqual(hr.utc(t1), "2026-11-08 00:00:00 UTC")
        self.assertEqual(hr.utc(due), "2026-11-08 00:35:00 UTC")
        self.assertEqual(hr.utc(hr.window(DAY, "14d")[1]), "2026-11-19 00:00:00 UTC")

    def test_not_due_before_window_end_writes_nothing(self):
        self.make()
        with self.assertRaises(hr.Refused) as c:
            hr.run(self.db, self.cdir, self.out, [DAY], "3d", self.due - 1, pins={})
        self.assertEqual((c.exception.status, c.exception.code), ("NOT_DUE", 2))
        self.assertFalse(os.path.exists(self.out))
        with mock.patch("time.time", lambda: self.due - 3600):               # CLI: the real clock decides
            rc, msg = self.quiet(hr.main, ["--db", self.db, "--cohort-dir", self.cdir, "--out", self.out])
        self.assertEqual((rc, msg["status"]), (2, "NOT_DUE"))
        self.assertFalse(os.path.exists(self.out))

    def test_due_cohort_reported_later_cohort_not_due(self):
        self.make()
        body = json.loads(read(os.path.join(self.cdir, "2026-11-04.json")))
        body["day"] = "2026-11-05"
        with open(os.path.join(self.cdir, "2026-11-05.json"), "w") as f:
            json.dump(body, f)
        with closing(hr.connect_ro(self.db)) as con:
            status, reps = hr.build(con, self.cdir, [], "3d", self.due, pins={})
        self.assertEqual(status["2026-11-04"]["status"], "REPORTED")
        self.assertEqual(status["2026-11-05"]["status"], "NOT_DUE")
        self.assertEqual([r["cohort"] for r in reps], ["2026-11-04"])
        with closing(hr.connect_ro(self.db)) as con:
            status, reps = hr.build(con, self.cdir, [DAY], "14d", self.due, pins={})
        self.assertEqual((status["2026-11-04"]["status"], reps), ("NOT_DUE", []))

    def test_all_c0_members_incl_no_spot_pair(self):
        self.make()
        _, c = self.report()
        syms = {m["symbol"]: m for m in c["members"]}
        self.assertEqual(set(syms), {"AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "1000EEEUSDT"})
        self.assertEqual(c["groups"]["C0"]["members"], 5)
        self.assertEqual(c["groups"]["C0+"]["members"], 4)
        cc = syms["CCCUSDT"]
        self.assertFalse(cc["missing"])                                # no spot pair is not missing data
        self.assertAlmostEqual(cc["realised_f8h"], 0.0004)              # perp-only measure computed for a dropout
        self.assertIsNone(cc["N1000"]["covered_ex_post"])               # coverage n/a, not "not covered"
        g = c["groups"]["frafald F1 intet spotpar"]
        self.assertEqual((g["members"], g["missing"], g["dropouts"], g["N1000"]["cost_known"]), (2, 0, 2, 0))
        self.assertEqual(c["groups"]["frafald F1 multiplikator"]["members"], 1)
        self.assertEqual(c["census_snapshots_in_window"], 72)

    def test_values_both_sizes_and_post_window_snapshots_excluded(self):
        self.make()
        _, c = self.report()
        a = {m["symbol"]: m for m in c["members"]}["AAAUSDT"]
        self.assertAlmostEqual(a["realised_f8h"], 0.0006)              # the 5x rate after the window is not used
        self.assertAlmostEqual(a["N1000"]["realised_funding"], 0.0006 * 9 * 1000)
        self.assertAlmostEqual(a["N1000"]["net"], 5.4 - 9.0)
        self.assertAlmostEqual(a["N1000"]["net_on_allocated"], (5.4 - 9.0) / 2000)
        self.assertAlmostEqual(a["N1000"]["breakeven_apr_perp_notional"], 9.0 / (1000 * 3 / 365))
        self.assertAlmostEqual(a["N5000"]["realised_funding"], 0.0006 * 9 * 5000)
        self.assertFalse(a["N5000"]["covered_ex_post"])
        g = c["groups"]
        self.assertEqual(g["bestod_F1-F5_N1000"]["members"], 2)
        self.assertEqual(g["bestod_F1-F5_N5000"]["members"], 1)          # BBB fails F4 at 5 000
        self.assertEqual(g["frafald F4 N5000"]["members"], 1)
        self.assertEqual(g["bestod_F1-F6_3d_N1000"]["members"], 0)        # nothing covered ex ante at 3 d
        self.assertEqual(g["C0"]["N1000"]["cost_known"], 2)
        self.assertEqual(g["C0"]["N1000"]["cost_unknown_no_spot_or_book"], 3)

    def test_missing_and_dropout_are_separate_and_missing_never_success(self):
        self.make(drop_last=("CCCUSDT",), sparse=("AAAUSDT",))
        _, c = self.report()
        m = {x["symbol"]: x for x in c["members"]}
        self.assertTrue(m["CCCUSDT"]["missing"])                        # vanished: survivorship kept, status shown
        self.assertFalse(m["CCCUSDT"]["present_in_last_snapshot"])
        self.assertFalse(m["CCCUSDT"]["missing_75pct_rule_only"])       # 66 of 72: only the "absent later" reading
        self.assertTrue(m["AAAUSDT"]["missing"] and m["AAAUSDT"]["missing_75pct_rule_only"])
        self.assertIs(m["AAAUSDT"]["N1000"]["covered_ex_post"], False)  # missing with a cost: not covered
        self.assertIsNone(m["AAAUSDT"]["realised_f8h"])
        g = c["groups"]["C0"]
        self.assertEqual((g["members"], g["missing"], g["dropouts"]), (5, 2, 3))
        self.assertEqual(g["absent_in_last_snapshot"], 2)                # CCC vanished; sparse AAA not in the last
        self.assertEqual(c["groups"]["frafald F1 intet spotpar"]["missing"], 1)
        self.assertEqual(c["groups"]["bestod_F1-F5_N1000"]["missing"], 1)

    def test_snapshot_parse_matches_hfc1_daily(self):
        import hfc1_daily
        self.make()
        t0, t1, _ = hr.window(DAY, "3d")
        with closing(hr.connect_ro(self.db)) as con:
            mine = [(ts, r) for ts, r, _ in hr.snapshots(con, t0, t1)]
            theirs = [(ts, r) for ts, r, _ in hfc1_daily.snapshots(con, t0, t1)]
        self.assertEqual(mine, theirs)

    def test_pinned_cohort_hashes(self):
        self.make()
        with self.assertRaises(hr.Refused) as c:
            hr.run(self.db, self.cdir, self.out, [DAY], "3d", self.due, pins={"2026-11-04": "deadbeef"})
        self.assertEqual((c.exception.status, c.exception.code), ("COHORT_HASH_MISMATCH", 3))
        for d in ("2026-11-04", "2026-11-05"):                         # the stored files match the protocol text
            body, s, pinned = hr.load_cohort(os.path.join(hr.COHORTS, f"{d}.json"), dt.date.fromisoformat(d))
            self.assertTrue(pinned and s.startswith(hr.PINNED[d]))
            self.assertEqual(len(body["rows"]), body["c0"])

    def test_read_only_deterministic_offdb_proposal(self):
        self.make()
        before, off = sha(self.db), sha(hr.OFFDB)
        rep1, _ = self.report()
        rep2, _ = hr.run(self.db, self.cdir, os.path.join(self.tmp, "o2"), [DAY], "3d", self.due + 999, pins={})
        self.assert_untouched(self.db, before)
        self.assertEqual(sha(hr.OFFDB), off)                             # proposed, never written
        self.assertEqual(rep1["result_sha256"], rep2["result_sha256"])
        self.assertIn("mode=ro", rep1["db_uri"])
        p = rep1["offdb_proposal"]
        self.assertFalse(p["written"])
        self.assertEqual(p["entry"]["id"], "HFC1_OUTCOME_3D_2026-11-04")
        self.assertEqual(set(p["entry"]), {"id", "files", "lineage", "attempts", "alpha", "note", "counted_elsewhere",
                                           "evidence", "confidence"})
        text = read(os.path.join(self.out, "hfc1_3d_2026-11-04.md"))
        self.assertIn("3 dage siger intet om langsigtet profit", text)
        for w in hr.FORBIDDEN_WORDS:
            self.assertNotIn(w, text.lower())
        with closing(hr.connect_ro(self.db)) as con, self.assertRaises(sqlite3.OperationalError):
            con.execute("CREATE TABLE x(a)")

    def test_existing_different_report_not_overwritten(self):
        self.make()
        self.report()
        p = os.path.join(self.out, "hfc1_3d_2026-11-04.json")
        j = json.loads(read(p))
        j["result_sha256"] = "x"
        with open(p, "w") as f:
            json.dump(j, f)
        with self.assertRaises(hr.Refused) as c:
            self.report()
        self.assertEqual(c.exception.status, "EXISTS")

    def test_dry_run_cli(self):
        rc, msg = self.quiet(hr.main, ["--dry-run", "--out", self.out])
        self.assertEqual((rc, msg["status"]), (0, "REPORTED"))
        self.assertTrue(os.path.basename(msg["file"]).startswith("DRYRUN_"))


# ---- STRAKS -----------------------------------------------------------------------------------------------------------

class Straks(Base):
    def setUp(self):
        super().setUp()
        self.db = sr.synthetic(self.tmp)
        self.now = sr.CUTOFF + sr.SETTLE_S

    def build(self, now=None):
        con = sr.connect_ro(self.db)
        try:
            return sr.build(con, now or self.now)
        finally:
            con.close()

    def test_times(self):
        self.assertEqual(sr.utc(sr.START_TS), "2026-11-05 17:01:51 UTC")
        self.assertEqual(sr.utc(sr.CUTOFF), "2026-11-12 17:01:51 UTC")
        self.assertEqual(set(sr.ACCOUNTS), {"LANE_35f39bb233", "LANE_a751c1f595"})
        from lab import lane
        self.assertEqual(lane.ledger_id("straks|cont"), "LANE_35f39bb233")
        self.assertEqual(lane.ledger_id("straks|rev"), "LANE_a751c1f595")

    def test_not_due(self):
        with self.assertRaises(sr.Refused) as c:
            self.build(sr.CUTOFF + sr.SETTLE_S - 1)
        self.assertEqual((c.exception.status, c.exception.code), ("NOT_DUE", 2))
        with mock.patch("time.time", lambda: sr.CUTOFF - 86400):
            rc, msg = self.quiet(sr.main, ["--db", self.db, "--out", self.out])
        self.assertEqual((rc, msg["status"]), (2, "NOT_DUE"))
        self.assertFalse(os.path.exists(self.out))

    def test_cutoff_excludes_post_cutoff_rows(self):
        a = self.build()["accounts"]["LANE_35f39bb233"]
        w = a["with_41b"]
        self.assertEqual(w["signals"]["seen"], 4)                       # move 60004 after the cutoff is not seen
        self.assertEqual((w["trades"]["round_trips"], w["trades"]["open_at_cutoff"]), (2, 1))
        xau = [t for t in a["trades"] if t["instrument"] == "XAUUSDT"][0]
        self.assertTrue(xau["open"])                                     # its exit fill at cutoff + 50 s is ignored
        self.assertEqual(a["account_at_last_mark"]["marked_at"], sr.CUTOFF - 1800)
        self.assertEqual(a["account_at_last_mark"]["fills_after_last_mark_before_cutoff"], 0)

    def test_values_follow_and_fade(self):
        r = self.build()["accounts"]
        f, m = r["LANE_35f39bb233"]["with_41b"]["trades"], r["LANE_a751c1f595"]["with_41b"]["trades"]
        self.assertAlmostEqual(f["gross"], 60.0, places=6)
        self.assertAlmostEqual(m["gross"], -60.0, places=6)
        for t in (f, m):
            self.assertEqual(t["decomposition_failures"], 0)
            self.assertAlmostEqual(t["net"], t["gross"] - t["fees"] - t["book"] - t["allowance"] + t["funding"])
        self.assertAlmostEqual(f["funding"], 0.5)
        acct = r["LANE_35f39bb233"]["account_at_last_mark"]
        self.assertAlmostEqual(acct["net"], acct["funding"] - acct["fees"] - acct["book"] - acct["allowance"]
                               + acct["price_move"])

    def test_with_and_without_41b(self):
        a = self.build()["accounts"]["LANE_35f39bb233"]
        w, wo = a["with_41b"], a["without_41b"]
        self.assertEqual(w["timing"]["entry_before_signal_move_ids"], [58416])
        self.assertEqual(w["timing"]["entry_before_signal_not_flagged_41b"], [])
        self.assertEqual(wo["timing"]["entry_before_signal_move_ids"], [])
        self.assertEqual((w["signals"]["traded"], wo["signals"]["traded"]), (3, 2))
        self.assertEqual((w["trades"]["round_trips"], wo["trades"]["round_trips"]), (2, 1))
        flagged = [t for t in a["trades"] if t["flag_41b"]][0]
        self.assertAlmostEqual(a["account_net_without_41b"]["net"], a["account_at_last_mark"]["net"] - flagged["net"])
        self.assertAlmostEqual(w["trades"]["net"] - wo["trades"]["net"], flagged["net"])

    def test_unflagged_timing_deviation_is_reported(self):
        con = sqlite3.connect(self.db)
        led = "LANE_35f39bb233"
        con.execute("INSERT INTO events(id, ts, kind, actor, exp_id, payload, prev_hash, hash) VALUES (70000, ?, "
                    "'opportunity.move', 't', NULL, ?, '', 'zz1')", (sr.START_TS + 50000, json.dumps(
                        {"instrument": "SPYUSDT", "class": "equity_etf", "flags": ["z_1h"], "ret_1h": 0.01})))
        con.execute("INSERT INTO sim_orders(order_id, exp_id, ts, instrument, side, qty, reduce_only, signal_ref, "
                    "prev_hash, hash) VALUES (?, ?, ?, 'SPYUSDT', 'buy', 1, 0, 'x', '', 'zz2')",
                    (f"{led}|entry|70000|SPYUSDT", led, sr.START_TS + 49990))
        con.execute("INSERT INTO sim_fills(fill_id, order_id, exp_id, ts, instrument, side, px, qty, fee, mid, "
                    "prev_hash, hash) VALUES ('f|0', ?, ?, ?, 'SPYUSDT', 'buy', 650.2, 1, 0.65, 650, '', 'zz3')",
                    (f"{led}|entry|70000|SPYUSDT", led, sr.START_TS + 49990))
        con.commit()
        con.close()
        a = self.build()["accounts"][led]
        self.assertEqual(a["with_41b"]["timing"]["entry_before_signal_not_flagged_41b"], [70000])
        self.assertIn("aktieindeks", a["with_41b"]["per_subclass"])

    def test_skipped_reasons_and_classes(self):
        a = self.build()["accounts"]["LANE_a751c1f595"]
        w = a["with_41b"]
        self.assertEqual(w["signals"]["skipped"], {"åben position på markedet": 1})
        self.assertEqual(w["signals"]["unresolved"], {})
        self.assertEqual(set(w["per_subclass"]), {"krypto", "energi", "metaller"})
        self.assertEqual(set(w["per_class"]), {"crypto", "commodity"})
        self.assertEqual(w["per_subclass"]["krypto"]["signals"]["seen"], 2)
        mm = w["market_move_after_signal"]["signed_ret_24h_after"]
        self.assertEqual(mm["n"], 2)
        self.assertAlmostEqual(mm["median"], -0.03)                     # MOD's sign; the simulated result is apart

    def test_start_mismatch_fails_closed(self):
        with closing(sr.connect_ro(self.db)) as con, self.assertRaises(sr.Refused) as c:
            sr.build(con, self.now, start_ts=sr.START_TS + 1)
        self.assertEqual((c.exception.status, c.exception.code), ("START_MISMATCH", 3))

    def test_direction_matches_lab(self):
        from lab import straks
        for m in ({"flags": ["z_1h"], "ret_1h": 0.1, "ret_24h": -0.2}, {"flags": ["z_24h"], "ret_1h": 0.1,
                  "ret_24h": -0.2}, {"flags": ["volume"], "ret_1h": -0.1, "ret_24h": 0.2}, {"flags": [], "ret_1h": 0},
                  {"flags": ["z_1h", "z_24h"], "ret_1h": -0.1, "ret_24h": 0.3}):
            self.assertEqual(sr.direction(m), straks.direction(m), m)

    def test_read_only_deterministic_and_md(self):
        before = sha(self.db)
        rep1, p1 = sr.run(self.db, self.out, self.now)
        rep2, _ = sr.run(self.db, os.path.join(self.tmp, "o2"), self.now + 5000)
        self.assert_untouched(self.db, before)
        self.assertEqual(rep1["result_sha256"], rep2["result_sha256"])
        self.assertTrue(p1.endswith("straks_7d_2026-11-12.json"))
        text = read(p1[:-5] + ".md")
        self.assertIn("2026-11-12 17:01:51 UTC", text)
        self.assertIn("ikke økonomiske spejlbilleder", text)
        with closing(sr.connect_ro(self.db)) as con, self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM events")

    def test_dry_run_cli(self):
        rc, msg = self.quiet(sr.main, ["--dry-run", "--out", self.out])
        self.assertEqual((rc, msg["status"]), (0, "REPORTED"))


class StraksLabEngine(Base):
    """End to end: the real lab engine writes the straks rows; the report's account net matches lane.decomposition."""

    def test_matches_lane_decomposition(self):
        from lab import lane, straks
        from lab.db import DB
        from tests.test_lab_straks import NOW, market
        path = os.path.join(self.tmp, "lab.db")
        db = DB(path)
        with mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True):
            with db.tx():
                db.append("observations", ts=NOW - 7200, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                          metric="z_1h", value=0.0, flagged=0, payload={})
            straks.ensure(db, NOW - 3600)
            with mock.patch("time.time", lambda: NOW - 600):
                db.event("opportunity.move", "system:scanner", None, {"instrument": "CLUSDT", "class": "commodity",
                                                                    "flags": ["z_1h"], "ret_1h": 0.03, "ret_24h": 0.0})
            for led in sr.ACCOUNTS:
                lane.run_one(db, led, market(), NOW)
                g = market(px=101.0)
                g.now = NOW + 24 * 3600
                lane.run_one(db, led, g, NOW + 24 * 3600)
        start = db.one("SELECT ts FROM events WHERE kind='lane.started' AND exp_id=?", "LANE_35f39bb233")[0]
        cutoff = NOW + 30 * 3600
        with closing(sr.connect_ro(path)) as con:
            rep = sr.build(con, cutoff + sr.SETTLE_S, cutoff=cutoff, start_ts=int(start))
        for led, (_, sign, _) in sr.ACCOUNTS.items():
            a, d = rep["accounts"][led], lane.decomposition(db, led)
            x = a["account_at_last_mark"]
            self.assertAlmostEqual(x["net"], d["net"], places=6)
            self.assertAlmostEqual(-x["fees"], d["fees"], places=6)
            self.assertAlmostEqual(-x["book"], d["book"], places=6)
            self.assertAlmostEqual(x["price_move"], d["price_basis"], places=6)
            t = a["with_41b"]["trades"]
            self.assertEqual((t["round_trips"], t["decomposition_failures"]), (1, 0))
            self.assertEqual(a["with_41b"]["signals"]["traded"], 1)
            self.assertEqual(sign * a["trades"][0]["gross"] > 0, True)       # CL rose 100 -> 101
        db.close()


# ---- PAR-BOG ----------------------------------------------------------------------------------------------------------

class Parbog(Base):
    def setUp(self):
        super().setUp()
        self.db = pb.synthetic(self.tmp)
        self.now = pb.CUTOFF + pb.SETTLE_S

    def build(self, now=None):
        con = sr.connect_ro(self.db)
        try:
            return pb.build(con, now or self.now)
        finally:
            con.close()

    def test_times(self):
        self.assertEqual(sr.utc(pb.START_TS), "2026-11-05 20:41:09 UTC")
        self.assertEqual(sr.utc(pb.CUTOFF), "2026-11-19 20:41:09 UTC")
        from lab import lane, pairs
        self.assertEqual(lane.ledger_id(pairs.KEY), pb.LEDGER)
        self.assertEqual(pairs.PAIRS, pb.PAIRS)

    def test_not_due(self):
        with self.assertRaises(sr.Refused) as c:
            self.build(pb.CUTOFF)
        self.assertEqual((c.exception.status, c.exception.code), ("NOT_DUE", 2))
        with mock.patch("time.time", lambda: pb.CUTOFF - 1):
            rc, msg = self.quiet(pb.main, ["--db", self.db, "--out", self.out])
        self.assertEqual((rc, msg["status"]), (2, "NOT_DUE"))

    def test_exit_reason_split_and_cutoff(self):
        r = self.build()
        br = r["by_exit_reason"]
        self.assertEqual({k: v["trades"] for k, v in br.items()}, {"normal": 1, "stop": 1, "tid": 1,
                                                                   "åben ved skæring": 1})
        self.assertEqual(r["per_pair"]["BZUSDT-CLUSDT"]["by_exit_reason"]["åben ved skæring"]["trades"], 1)
        self.assertEqual(r["per_pair"]["QQQUSDT-SPYUSDT"]["by_exit_reason"]["stop"]["closed"], 1)
        self.assertAlmostEqual(br["normal"]["gross"], 10.0, places=6)    # short ETH 4000 -> 3960, BTC flat
        self.assertEqual(r["total"]["decomposition_failures"], 0)
        self.assertEqual(r["integrity_problems"], [])
        self.assertEqual(r["total"]["partial_legs"], 1)                  # 43a: the half-filled XAG leg is shown
        self.assertAlmostEqual(br["normal"]["funding"], 0.3)
        tid = [t for t in r["trades"] if t["exit_reason"] == "tid"][0]
        self.assertAlmostEqual(tid["hold_h"], 72.0)
        self.assertAlmostEqual(tid["net_notional_at_entry"], -500.0, delta=1)
        self.assertTrue(all(v is None for v in r["not_sent_not_recorded_in_db"].values()))
        a = r["account_at_last_mark"]
        self.assertAlmostEqual(a["net"], a["funding"] - a["fees"] - a["book"] - a["allowance"] + a["price_move"])

    def test_exit_without_entry_is_an_integrity_problem(self):
        con = sqlite3.connect(self.db)
        oid = f"{pb.LEDGER}|out|ETHUSDT-BTCUSDT|{pb.START_TS + 9 * 86400}|ETHUSDT"
        con.execute("INSERT INTO sim_orders(order_id, exp_id, ts, instrument, side, qty, reduce_only, signal_ref, "
                    "prev_hash, hash) VALUES (?, ?, ?, 'ETHUSDT', 'buy', 0.25, 1, 'pairs.stop@1:z=4.5', '', 'q1')",
                    (oid, pb.LEDGER, pb.START_TS + 9 * 86400))
        con.commit()
        con.close()
        self.assertTrue(any("uden indgang" in p for p in self.build()["integrity_problems"]))

    def test_parse_ref_lab_format(self):
        self.assertEqual(pb.parse_ref("pairs.normal@1794000000:z=0.41234"), ("normal", 0.41234))
        self.assertEqual(pb.parse_ref("pairs.stop@1794000000:z=-4.0000001"), ("stop", -4.0000001))
        self.assertEqual(pb.parse_ref("pairs.tid@1794000000:z=None"), ("tid", None))
        self.assertEqual(pb.parse_ref("pairs.ind@1794000000:z=2.1e-01"), ("ind", 0.21))
        self.assertEqual(pb.parse_ref("straks.entry@5"), (None, None))

    def test_read_only_and_deterministic(self):
        before = sha(self.db)
        r1, p1 = pb.run(self.db, self.out, self.now)
        r2, _ = pb.run(self.db, os.path.join(self.tmp, "o2"), self.now + 77)
        self.assert_untouched(self.db, before)
        self.assertEqual(r1["result_sha256"], r2["result_sha256"])
        self.assertTrue(p1.endswith("parbog_2026-11-19.json"))
        self.assertIn("2026-11-19 20:41:09 UTC", read(p1[:-5] + ".md"))

    def test_dry_run_cli(self):
        rc, msg = self.quiet(pb.main, ["--dry-run", "--out", self.out])
        self.assertEqual((rc, msg["status"]), (0, "REPORTED"))


class PairsLabEngine(Base):
    """End to end: lab/pairs.py writes an entry and a 'normal' exit; the report finds the reason and the net."""

    def test_normal_exit_from_the_real_engine(self):
        from lab import lane, pairs, paper_runner
        from lab.db import DB
        from tests.test_lab_pairs import NOW, HOUR, market
        path = os.path.join(self.tmp, "lab.db")
        db = DB(path)
        paper_runner._HOURLY.clear()
        with mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True), \
                mock.patch.object(pairs, "PAIRS", (("BZUSDT", "CLUSDT"),)):
            with db.tx():
                db.append("observations", ts=NOW - 7200, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                          metric="z_1h", value=0.0, flagged=0, payload={})
            pairs.ensure(db, NOW - 60)
            (led, _), = lane.started(db).items()
            s = {"v": 0.002}
            get = market(lambda: s["v"])
            lane.run_one(db, led, get, NOW)
            s["v"] = 0.0
            get.now = NOW + HOUR
            lane.run_one(db, led, get, NOW + HOUR)
        paper_runner._HOURLY.clear()
        start = int(db.one("SELECT ts FROM events WHERE kind='lane.started' AND exp_id=?", led)[0])
        cutoff = int(NOW + 3 * HOUR)
        with closing(sr.connect_ro(path)) as con:
            rep = pb.build(con, cutoff + pb.SETTLE_S, cutoff=cutoff, start_ts=start)
        self.assertEqual(rep["by_exit_reason"]["normal"]["closed"], 1)
        self.assertEqual(rep["total"]["decomposition_failures"], 0)
        self.assertEqual(rep["integrity_problems"], [])
        d = lane.decomposition(db, led)
        self.assertAlmostEqual(rep["account_at_last_mark"]["net"], d["net"], places=6)
        t = rep["trades"][0]
        self.assertGreater(t["z_entry"], 2)
        db.close()


class NotDueNeverOpensTheDatabase(Base):
    def test_missing_db_still_not_due(self):
        nodb = os.path.join(self.tmp, "absent.db")
        _, cdir = hr.synthetic(self.tmp)
        for fn, args in ((hr.run, (nodb, cdir, self.out, [DAY], "3d", hr.window(DAY, "3d")[2] - 1)),
                         (sr.run, (nodb, self.out, sr.CUTOFF)), (pb.run, (nodb, self.out, pb.CUTOFF + 1))):
            with self.assertRaises(sr.Refused if fn is not hr.run else hr.Refused) as c:
                fn(*args)
            self.assertEqual(c.exception.status, "NOT_DUE")
            self.assertFalse(os.path.exists(nodb))
        with self.assertRaises(sr.Refused) as c:
            sr.run(nodb, self.out, sr.CUTOFF + sr.SETTLE_S)
        self.assertEqual((c.exception.status, c.exception.code), ("NO_DB", 3))


class CrashSafeWrites(Base):
    """Order 60 A/C (MILESTONE_DRYRUN_60AC.md): straks_report.write_outputs (shared with parbog_report) gets the same
    crash rule as hfc1_report3d B3: a .json without its .md (crash between the two writes) is completed on a rerun with
    the same result, never left half; a lone .md or an empty .json is refused (EXISTS) and kept; no .tmp is left."""

    def runs(self):
        sdb, pdb = sr.synthetic(self.mk("s")), pb.synthetic(self.mk("p"))
        return (("straks", lambda out: sr.run(sdb, out, sr.CUTOFF + sr.SETTLE_S, True)),
                ("parbog", lambda out: pb.run(pdb, out, pb.CUTOFF + pb.SETTLE_S, True)))

    def mk(self, name):
        d = os.path.join(self.tmp, name)
        os.makedirs(d)
        return d

    def test_rerun_after_crash_between_json_and_md_completes_the_md(self):
        for name, run in self.runs():
            out = os.path.join(self.tmp, "out_" + name)
            rep, jp = run(out)
            mp = jp[:-5] + ".md"
            md_before = read(mp)
            os.remove(mp)                                                  # crash: .json on disk, .md not
            rep2, _ = run(out)
            self.assertEqual(rep2["result_sha256"], rep["result_sha256"], name)
            self.assertTrue(os.path.exists(mp), name)
            self.assertEqual(read(mp), md_before, name)
            self.assertEqual([n for n in os.listdir(out) if n.endswith(".tmp")], [], name)

    def test_lone_md_or_empty_json_is_refused_and_kept(self):
        for name, run in self.runs():
            out = os.path.join(self.tmp, "out_" + name)
            _, jp = run(out)
            mp = jp[:-5] + ".md"
            os.remove(jp)                                                  # lone .md: never trusted
            before = sha(mp)
            with self.assertRaises(sr.Refused) as c:
                run(out)
            self.assertEqual((c.exception.status, c.exception.code), ("EXISTS", 3), name)
            self.assertEqual(sha(mp), before, name)
            open(jp, "wb").close()                                         # zero-length .json after a crash
            with self.assertRaises(sr.Refused) as c:
                run(out)
            self.assertEqual((c.exception.status, c.exception.code), ("EXISTS", 3), name)
            self.assertEqual(os.path.getsize(jp), 0, name)
            self.assertEqual([n for n in os.listdir(out) if n.endswith(".tmp")], [], name)


class Static(unittest.TestCase):
    """The tools stay stdlib-only, network-free, read-only and away from pm_lp (module docstrings excluded)."""

    def code(self, name):
        import ast
        src = read(os.path.join(HERE, "research", "tools", name))
        doc = ast.get_docstring(ast.parse(src), clean=False) or ""
        return src.replace(doc, "", 1)

    def test_sources(self):
        for name in TOOLS:
            src = self.code(name)
            for bad in ("urllib.request", "import socket", "http.client", "import requests", "pm_lp", "api.upbit",
                        "import lab", "from lab", "news/1"):
                self.assertNotIn(bad, src, (name, bad))
            pre = src.split("# ---- synthetic data")[0]                  # writers only in the synthetic builders
            for bad in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "CREATE "):
                self.assertNotIn(bad, pre, (name, bad))
        for name in ("hfc1_report3d.py", "straks_report.py"):
            src = self.code(name)
            self.assertIn('con.execute("PRAGMA query_only=ON")', src)
            self.assertIn('DB = "' + PROD + '"', src)
        self.assertIn("sr.connect_ro(db)", self.code("parbog_report.py"))

    def test_production_uri_form(self):
        self.assertEqual(sr.ro_uri(PROD), "file:" + PROD + "?mode=ro")
        self.assertEqual(hr.ro_uri(PROD), "file:" + PROD + "?mode=ro")


if __name__ == "__main__":
    unittest.main()
