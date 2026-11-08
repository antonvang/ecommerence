"""HFC-1 3 d report readiness for 2026-11-08 (director order 53 P3; research/desk/HFC1_REPORT_READINESS.md).

Synthetic databases only (socket patched, the production lab.db is never opened). The committed cohort files in
research/data/hfc1/ are read (structure + pinned hashes) and combined with a SYNTHETIC census database; no real outcome
is computed. The tests in class Findings document B1-B4 from the readiness file; the patch was applied to
research/tools/hfc1_report3d.py on 2026-11-06 and they now pass as ordinary regression tests.
"""
import calendar
import datetime as dt
import hashlib
import io
import json
import os
import sqlite3
import unittest
from contextlib import closing
from unittest import mock

from tests import test_research_milestone_reports as mrt   # sys.path set up there; Base patches socket

hr = mrt.hr
Base, read, sha = mrt.Base, mrt.read, mrt.sha
HERE = mrt.HERE
DAY, DAY2, DAY7 = dt.date(2026, 11, 4), dt.date(2026, 11, 5), dt.date(2026, 11, 7)
PROTO = os.path.join(HERE, hr.PROTOCOL)
PROTO_RULES_LEN = 3178              # byte length of the protocol as committed before data (48a0a63)
PROTO_RULES_SHA = "cd1b6fc66000544f6e58a5e202f4c3f0c2d10913c3882f3eda6b8d06cdfe53c6"
COLS = ["markPrice", "indexPrice", "lastFundingRate", "lastPrice", "openPrice", "highPrice", "lowPrice",
        "quoteVolume", "count"]
ABSENT = object()


def ts_utc(y, mo, d, h=0, mi=0, s=0):
    return calendar.timegm((y, mo, d, h, mi, s))


# hand-computed times (independent of hr.window)
T0_1104, T1_1104 = ts_utc(2026, 11, 5), ts_utc(2026, 11, 8)
DUE_1104 = ts_utc(2026, 11, 8, 0, 35)
DUE_1105 = ts_utc(2026, 11, 9, 0, 35)


def build_db(path, series, t0, t1, coin=None, skip_hours=(), offset=120, wal_writer=False):
    """Hourly census/1 snapshots shaped like lab/census.py (float numbers, null for a missing field, coin_perps =
    COIN-underlying TRADING perps & rows) from 3 d before t0 to 2 h after t1. series: {symbol: f(ts) -> rate | None |
    ABSENT}; after t1 every rate is x5 (must never be used). coin: f(ts) -> set of coin perps (default: every row)."""
    con = sqlite3.connect(path)
    con.execute(hr.SCHEMA)
    n = 0
    for ts in range(t0 - 3 * 86400, t1 + 2 * 3600, 3600):
        if t0 <= ts < t1 and (ts - t0) // 3600 in skip_hours:
            continue
        rows = {}
        for s, f in series.items():
            v = f(ts)
            if v is ABSENT:
                continue
            rows[s] = [1.0, 1.0, None if v is None else v * (5 if ts >= t1 else 1)] + [None] * 6
        cp = sorted((coin(ts) if coin else set(rows)) & set(rows))
        n += 1
        con.execute("INSERT INTO observations(ts, detector, source, instrument, metric, value, flagged, payload, "
                    "prev_hash, hash) VALUES (?, 'census/1', 'x', NULL, 'snapshot', ?, 0, ?, '', ?)",
                    (ts + offset, len(rows), json.dumps({"columns": COLS, "rows": rows, "coin_perps": cp}), f"h{n}"))
    con.commit()
    con.close()
    return path


def write_cohort(cdir, day, rows, snapshots=72):
    os.makedirs(cdir, exist_ok=True)
    body = {"day": str(day), "run_ts": calendar.timegm(day.timetuple()) + 86400 + 2400, "snapshots": snapshots,
            "c0": len(rows), "rows": rows, "books": {}, "spot_info_sha256": "0" * 64}
    p = os.path.join(cdir, f"{day}.json")
    with open(p, "w") as f:
        json.dump(body, f, sort_keys=True)
    return p


def const(v):
    return lambda ts: v


def until(v, t_end):
    return lambda ts: v if ts < t_end else ABSENT


F = 2.0 ** -10                      # exact binary rate: 72-snapshot mean and x 9 x N are exact


def matrix_rows():
    """One cohort with every kind of member hfc1_daily.cohort() can write (keys as in the committed files)."""
    def passed(sym, m2, c1, c5, cov1=False, cov5=False, drop_size=None):
        r = {"symbol": sym, "f8h": 0.0003, "apr": 0.3285, "m2": m2, "cost_1000": c1, "cost_5000": c5,
             "spot_spread": 0.002, "perp_spread": 0.0005}
        for n, c, cv in (("1000", c1, cov1), ("5000", c5, cov5)):
            if c is not None:
                r[f"covered_3d_{n}"], r[f"covered_14d_{n}"] = cv, cv
        if drop_size:
            r["drop_size"] = drop_size
        return r
    return [
        passed("PASSAUSDT", True, 8.7890625, 60.0, cov1=True),
        passed("PASSBUSDT", False, 20.0, 120.0),
        {"symbol": "NOSPOTUSDT", "f8h": 0.0003, "apr": 0.3285, "m2": True, "drop": "F1 intet spotpar"},
        {"symbol": "1000MULTUSDT", "f8h": 0.0003, "apr": 0.3285, "m2": True, "drop": "F1 multiplikator"},
        {"symbol": "NOTTRADUSDT", "f8h": 0.0003, "apr": 0.13, "m2": False, "drop": "F2 perp ikke TRADING"},
        {"symbol": "NOBOOKUSDT", "f8h": 0.0003, "apr": 0.13, "m2": False, "drop": "F3 bog ikke hentet: URLError"},
        {"symbol": "EMPTYUSDT", "f8h": 0.0003, "apr": 0.13, "m2": False, "drop": "F3 tom side", "cost_1000": None,
         "cost_5000": None, "drop_size": ["F4 1000", "F4 5000"], "spot_spread": None, "perp_spread": 0.001},
        passed("CAP5USDT", False, 10.0, None, drop_size=["F4 5000"]),
        passed("CAP1USDT", False, None, None, drop_size=["F4 1000", "F4 5000"]),
        passed("DELISTUSDT", True, 1.0, 5.0, cov1=True),
        {"symbol": "STOCKUSDT", "f8h": 0.0003, "apr": 0.3285, "m2": True, "drop": "F1 intet spotpar"},
    ]


def matrix_series(t0):
    s = {r["symbol"]: const(0.0003) for r in matrix_rows()}
    s["PASSAUSDT"] = const(F)
    s["PASSBUSDT"] = const(-0.0001)
    s["DELISTUSDT"] = until(0.001, t0 + 48 * 3600)          # delisted after 48 of 72 hours
    return s


class Readiness(Base):
    def make_matrix(self, coin=None):
        self.db = build_db(os.path.join(self.tmp, "lab.db"), matrix_series(T0_1104), T0_1104, T1_1104, coin=coin)
        self.cdir = os.path.join(self.tmp, "hfc1")
        write_cohort(self.cdir, DAY, matrix_rows())

    def run3d(self, now=DUE_1104, days=(DAY,), out=None, **kw):
        rep, _ = hr.run(self.db, self.cdir, out or self.out, list(days), "3d", now, pins={}, **kw)
        return rep

    def members(self, rep, i=0):
        return {m["symbol"]: m for m in rep["cohorts"][i]["members"]}


# ---- R01-R04: windows, NOT_DUE, boundaries ---------------------------------------------------------------------------

class Windows(Readiness):
    def test_R01_windows_and_due_times_hand_computed(self):
        self.assertEqual(hr.window(DAY, "3d"), (T0_1104, T1_1104, DUE_1104))
        self.assertEqual(hr.window(DAY2, "3d"), (ts_utc(2026, 11, 6), ts_utc(2026, 11, 9), DUE_1105))
        self.assertEqual(hr.window(DAY, "14d")[2], ts_utc(2026, 11, 19, 0, 35))
        self.assertEqual(hr.window(dt.date(2026, 11, 24), "3d")[2], ts_utc(2026, 11, 28, 0, 35))   # last 3 d (11-28)
        self.assertEqual(hr.window(dt.date(2026, 11, 24), "14d")[1], ts_utc(2026, 12, 9))           # last 14 d (12-09)

    def test_R02_not_due_at_and_after_window_end_until_0035(self):
        self.make_matrix()
        for now in (T1_1104 - 1, T1_1104, T1_1104 + 34 * 60, DUE_1104 - 1):      # 23:59:59, 00:00:00, 00:34, 00:34:59
            with self.subTest(now=hr.utc(now)), self.assertRaises(hr.Refused) as c:
                self.run3d(now)
            self.assertEqual((c.exception.status, c.exception.code), ("NOT_DUE", 2))
            self.assertIn("2026-11-08 00:35:00 UTC", c.exception.detail)
            self.assertFalse(os.path.exists(self.out))                            # nothing written
        rep = self.run3d(DUE_1104)                                                  # 00:35:00 exactly
        self.assertEqual(rep["cohort_status"]["2026-11-04"]["status"], "REPORTED")

    def test_R02b_cli_uses_the_real_clock_at_the_boundary(self):
        self.make_matrix()
        args = ["--db", self.db, "--cohort-dir", self.cdir, "--out", self.out, "--cohort", "2026-11-04"]
        with mock.patch("time.time", lambda: DUE_1104 - 1):
            rc, msg = self.quiet(hr.main, args)
        self.assertEqual((rc, msg["status"]), (2, "NOT_DUE"))
        self.assertFalse(os.path.exists(self.out))
        with mock.patch("time.time", lambda: DUE_1104):                          # the CLI pins the real 11-04 hash
            rc, msg = self.quiet(hr.main, args)
        self.assertEqual((rc, msg["status"]), (3, "COHORT_HASH_MISMATCH"))      # a synthetic 11-04 file is refused
        self.assertFalse(os.path.exists(os.path.join(self.out, "hfc1_3d_2026-11-04.json")))
        with mock.patch("time.time", lambda: DUE_1104), mock.patch.dict(hr.PINNED, {}, clear=True):
            rc, msg = self.quiet(hr.main, args)
        self.assertEqual((rc, msg["status"], msg["cohorts"]), (0, "REPORTED", {"2026-11-04": "REPORTED"}))
        self.assertEqual(os.path.basename(msg["file"]), "hfc1_3d_2026-11-04.json")
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            hr.main(["--now", str(DUE_1104)])                                    # no clock override exists

    def test_R02c_not_due_never_opens_the_database(self):
        self.make_matrix()
        with mock.patch.object(hr.sqlite3, "connect", side_effect=AssertionError("db opened")):
            with self.assertRaises(hr.Refused) as c:
                hr.run(os.path.join(self.tmp, "absent.db"), self.cdir, self.out, [DAY], "3d", DUE_1104 - 1, pins={})
        self.assertEqual(c.exception.status, "NOT_DUE")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "absent.db")))

    def test_R03_second_cohort_has_its_own_window_end(self):
        self.make_matrix()
        self.db = build_db(os.path.join(self.tmp, "lab2.db"), matrix_series(T0_1104), T0_1104, ts_utc(2026, 11, 9))
        write_cohort(self.cdir, DAY2, matrix_rows())
        rep = self.run3d(DUE_1104, days=())                                         # default: all stored cohorts
        self.assertEqual(rep["cohort_status"]["2026-11-05"], {"status": "NOT_DUE",
                         "window_end_utc": "2026-11-09 00:00:00 UTC", "due_utc": "2026-11-09 00:35:00 UTC"})
        self.assertEqual([c["cohort"] for c in rep["cohorts"]], ["2026-11-04"])    # no numbers for 11-05
        with self.assertRaises(hr.Refused) as c:
            self.run3d(DUE_1105 - 1, days=(DAY2,), out=os.path.join(self.tmp, "o5"))
        self.assertEqual(c.exception.status, "NOT_DUE")
        rep = self.run3d(DUE_1105, days=(DAY2,), out=os.path.join(self.tmp, "o5"))
        self.assertEqual(rep["cohort_status"], {"2026-11-05": {"status": "REPORTED", "due_utc": "2026-11-09 00:35:00 UTC"}})

    def test_R04_14d_not_due_on_11_08(self):
        self.make_matrix()
        with self.assertRaises(hr.Refused) as c:
            hr.run(self.db, self.cdir, self.out, [DAY], "14d", DUE_1104 + 86400, pins={})
        self.assertEqual((c.exception.status, c.exception.code), ("NOT_DUE", 2))


# ---- R05-R12: members, groups, numbers -------------------------------------------------------------------------------

class Members(Readiness):
    def setUp(self):
        super().setUp()
        self.make_matrix()
        self.rep = self.run3d()
        self.c = self.rep["cohorts"][0]
        self.m = self.members(self.rep)
        self.g = self.c["groups"]

    def test_R05_every_c0_member_is_reported_no_survivor_selection(self):
        self.assertEqual([m["symbol"] for m in self.c["members"]], [r["symbol"] for r in matrix_rows()])
        g = self.g["C0"]
        self.assertEqual((g["members"], g["c0plus"], g["dropouts"], g["missing"], g["observed"]), (11, 5, 6, 1, 10))
        self.assertEqual(self.g["C0+"]["members"], 5)
        for step, n in (("frafald F1 intet spotpar", 2), ("frafald F1 multiplikator", 1),
                        ("frafald F2 perp ikke TRADING", 1), ("frafald F3 bog ikke hentet", 1),
                        ("frafald F3 tom side", 1), ("frafald F4 N1000", 1), ("frafald F4 N5000", 2)):
            self.assertEqual(self.g[step]["members"], n, step)
        self.assertEqual(self.g["bestod_F1-F5_N1000"]["members"], 4)          # PASSA, PASSB, CAP5, DELIST
        self.assertEqual(self.g["bestod_F1-F5_N5000"]["members"], 3)          # CAP5 fails F4 at 5 000
        self.assertEqual(self.g["bestod_F1-F6_3d_N1000"]["members"], 2)       # ex ante covered: PASSA, DELIST
        self.assertEqual(self.g["bestod_F1-F6_3d_N5000"]["members"], 0)

    def test_R06_delisted_member_stays_in_as_missing_never_success(self):
        d = self.m["DELISTUSDT"]
        self.assertTrue(d["missing"])
        self.assertFalse(d["present_in_last_snapshot"])
        self.assertEqual(d["n_obs"], 48)
        self.assertEqual(len(d["missing_reasons"]), 2)                       # > 25 % gap and absent at the end
        self.assertIsNone(d["realised_f8h"])
        self.assertAlmostEqual(d["partial_f8h_not_used"], 0.001)             # shown, not used
        self.assertIs(d["N1000"]["covered_ex_post"], False)                  # would be covered (9 >= 1) if counted
        self.assertIsNone(d["N1000"]["net"])
        self.assertTrue(d["status"].startswith("manglende"))
        self.assertEqual(self.g["bestod_F1-F6_3d_N1000"]["N1000"]["ex_ante_and_ex_post_covered"], 1)
        self.assertEqual(self.g["C0"]["absent_in_last_snapshot"], 1)
        md = read(os.path.join(self.out, "hfc1_3d_2026-11-04.md"))
        self.assertIn("- DELISTUSDT: ", md)

    def test_R07_dropouts_and_non_observable_are_separate_from_missing(self):
        for s in ("NOSPOTUSDT", "1000MULTUSDT", "NOTTRADUSDT", "NOBOOKUSDT", "EMPTYUSDT", "CAP1USDT", "STOCKUSDT"):
            m = self.m[s]
            self.assertFalse(m["missing"], s)                                # non-observable cost is not missing data
            self.assertAlmostEqual(m["realised_f8h"], 0.0003, msg=s)         # perp-only measure still computed
            for n in ("1000", "5000"):
                self.assertIsNone(m[f"N{n}"]["covered_ex_post"], s)          # n/a, neither covered nor not covered
                self.assertIsNone(m[f"N{n}"]["net"], s)
        n1 = self.g["C0"]["N1000"]
        self.assertEqual((n1["cost_known"], n1["cost_unknown_no_spot_or_book"]), (4, 7))
        n5 = self.g["C0"]["N5000"]
        self.assertEqual((n5["cost_known"], n5["cost_unknown_no_spot_or_book"]), (3, 8))
        self.assertEqual(self.g["frafald F1 intet spotpar"]["missing"], 0)

    def test_R08_breakeven_and_net_hand_computed_both_sizes(self):
        a = self.m["PASSAUSDT"]
        self.assertEqual(a["realised_f8h"], F)
        self.assertEqual(a["realised_apr"], 1.0693359375)                    # 2^-10 x 1095
        x = a["N1000"]                                                        # cost 8.7890625 = 2^-10 x 9 x 1000
        self.assertEqual(x["realised_funding"], 8.7890625)
        self.assertIs(x["covered_ex_post"], True)                             # equality counts as covered (>=)
        self.assertEqual((x["coverage_ratio"], x["net"], x["net_on_allocated"]), (1.0, 0.0, 0.0))
        self.assertAlmostEqual(x["breakeven_apr_perp_notional"], 1.0693359375, places=12)   # = realised APR
        y = a["N5000"]                                                        # cost 60 on 5 000 per leg
        self.assertEqual(y["realised_funding"], 43.9453125)
        self.assertEqual(y["net"], -16.0546875)
        self.assertAlmostEqual(y["net_on_allocated"], -16.0546875 / 10000)    # allocated 2N = 10 000 at 1x
        self.assertAlmostEqual(y["breakeven_apr_perp_notional"], 1.46)        # 60 / (5000 x 3/365)
        self.assertAlmostEqual(y["coverage_ratio"], 43.9453125 / 60)
        self.assertIs(y["covered_ex_post"], False)
        b = self.m["PASSBUSDT"]["N1000"]                                      # negative funding is paid, not dropped
        self.assertAlmostEqual(b["realised_funding"], -0.9)
        self.assertAlmostEqual(b["net"], -20.9)
        self.assertAlmostEqual(b["breakeven_apr_perp_notional"], 20.0 / (1000 * 3 / 365))

    def test_R09_group_shares_and_medians(self):
        n1 = self.g["C0"]["N1000"]
        self.assertEqual(n1["covered_ex_post"], 1)                            # PASSA only
        self.assertAlmostEqual(n1["covered_share_of_cost_known"], 1 / 4)
        self.assertAlmostEqual(n1["covered_share_strict_all_members"], 1 / 11)
        self.assertEqual(n1["coverage_ratio"]["n"], 3)                        # DELIST missing: no ratio
        self.assertAlmostEqual(n1["coverage_ratio"]["median"], 0.27)          # [-0.045, 0.27, 1.0]
        self.assertAlmostEqual(n1["net"]["median"], -7.3)
        self.assertAlmostEqual(n1["net"]["min"], -20.9)
        self.assertEqual(n1["net"]["max"], 0.0)
        self.assertEqual(n1["ex_ante_covered"], 2)
        self.assertEqual(n1["ex_ante_and_ex_post_covered"], 1)
        p = self.g["C0+"]["N1000"]                                            # C0+: PASSA, DELIST (+3 dropouts)
        self.assertEqual((p["cost_known"], p["covered_ex_post"]), (2, 1))

    def test_R10_costs_and_exit_assumption_labelled(self):
        md = read(os.path.join(self.out, "hfc1_3d_2026-11-04.md"))
        j = json.loads(read(os.path.join(self.out, "hfc1_3d_2026-11-04.json")))
        for line in hr.FIXED_LINES:
            self.assertIn(line, md)
            self.assertIn(line, j["fixed_lines"])
        self.assertTrue(any("bogens gennemgang ved kohortedannelsen" in s and "exit-bog er ikke observeret" in s
                            for s in j["fixed_lines"]))
        self.assertTrue(any("8 t-intervaller" in s for s in j["fixed_lines"]))
        self.assertIn("allokeret kapital 1x = 2.000", md)
        self.assertIn("allokeret kapital 1x = 10.000", md)
        self.assertEqual(j["sizes_usdt_per_leg"], [1000, 5000])
        self.assertTrue(j["research_status"].startswith("INCONCLUSIVE"))
        for w in hr.FORBIDDEN_WORDS:
            self.assertNotIn(w, md.lower())


class Coverage(Readiness):
    def test_R11_missing_hours_and_window_edges(self):
        series = {"EDGEUSDT": const(F)}
        self.db = build_db(os.path.join(self.tmp, "lab.db"), series, T0_1104, T1_1104, skip_hours=range(5, 15),
                           offset=0)                                         # snapshots exactly on t0 ... and on t1
        self.cdir = os.path.join(self.tmp, "hfc1")
        write_cohort(self.cdir, DAY, [{"symbol": "EDGEUSDT", "f8h": F, "apr": 0.2, "m2": True, "cost_1000": 1.0,
                                       "cost_5000": 2.0, "covered_3d_1000": True, "covered_3d_5000": True}])
        c = self.run3d()["cohorts"][0]
        self.assertEqual((c["census_snapshots_in_window"], c["census_hours_covered"], c["census_hours_missing"]),
                         (62, 62, 10))
        self.assertEqual(c["last_snapshot_utc"], "2026-11-07 23:00:00 UTC")  # the one on t1 (00:00:00) is excluded
        m = c["members"][0]
        self.assertEqual((m["n_obs"], m["expected_obs"], m["missing"]), (62, 72, False))
        self.assertAlmostEqual(m["obs_coverage"], 62 / 72)
        self.assertEqual(m["realised_f8h"], F)                               # the x5 rate at ts = t1 is not used

    def test_R12_25_percent_rule_boundary(self):
        def gap(lo, hi):
            return lambda ts: ABSENT if T0_1104 + lo * 3600 <= ts < T0_1104 + hi * 3600 else 0.0003
        series = {"S54USDT": gap(10, 28), "S53USDT": gap(10, 29)}             # 54 and 53 of 72 snapshots
        self.db = build_db(os.path.join(self.tmp, "lab.db"), series, T0_1104, T1_1104)
        self.cdir = os.path.join(self.tmp, "hfc1")
        write_cohort(self.cdir, DAY, [{"symbol": s, "f8h": 0.0003, "apr": 0.3, "m2": True, "drop": "F1 intet spotpar"}
                                      for s in ("S54USDT", "S53USDT")])
        m = self.members(self.run3d())
        self.assertEqual((m["S54USDT"]["n_obs"], m["S54USDT"]["missing"]), (54, False))
        self.assertEqual((m["S53USDT"]["n_obs"], m["S53USDT"]["missing"]), (53, True))
        self.assertTrue(m["S53USDT"]["missing_75pct_rule_only"])

    def test_R12b_no_snapshots_at_all_everyone_missing(self):
        self.db = build_db(os.path.join(self.tmp, "lab.db"), {"AUSDT": const(0.001)}, T0_1104, T1_1104,
                           skip_hours=range(72))
        self.cdir = os.path.join(self.tmp, "hfc1")
        write_cohort(self.cdir, DAY, [{"symbol": "AUSDT", "f8h": 0.001, "apr": 1.0, "m2": True, "cost_1000": 1.0,
                                       "cost_5000": 1.0, "covered_3d_1000": True, "covered_3d_5000": True}])
        c = self.run3d()["cohorts"][0]
        self.assertEqual((c["census_snapshots_in_window"], c["census_hours_missing"], c["last_snapshot_utc"]),
                         (0, 72, None))
        g = c["groups"]["C0"]
        self.assertEqual((g["missing"], g["N1000"]["covered_ex_post"], g["N5000"]["covered_ex_post"]), (1, 0, 0))

    def test_R12c_null_funding_field_counts_as_absent(self):
        self.db = build_db(os.path.join(self.tmp, "lab.db"),
                           {"NULLUSDT": lambda ts: None if ts >= T1_1104 - 3 * 3600 else 0.0003}, T0_1104, T1_1104)
        self.cdir = os.path.join(self.tmp, "hfc1")
        write_cohort(self.cdir, DAY, [{"symbol": "NULLUSDT", "f8h": 0.0003, "apr": 0.3, "m2": True,
                                       "drop": "F1 intet spotpar"}])
        m = self.members(self.run3d())["NULLUSDT"]
        self.assertEqual((m["n_obs"], m["present_in_last_snapshot"], m["missing"]), (69, False, True))


# ---- R13-R17: offdb, hash, overwrite, read-only, protocol -------------------------------------------------------------

class Integrity(Readiness):
    def test_R13_offdb_proposal_produced_never_written(self):
        self.make_matrix()
        before = sha(hr.OFFDB)
        rep = self.run3d()
        self.assertEqual(sha(hr.OFFDB), before)
        p = rep["offdb_proposal"]
        with open(hr.OFFDB, encoding="utf-8") as f:
            studies = json.load(f)["studies"]
        # the entry was added by hand after the real run (director order 55); the tool must report that, never write
        present = any(s.get("id") == p["entry"]["id"] for s in studies)
        self.assertEqual((p["written"], p["already_present"], p["target"]),
                         (False, present, "research/data/factory/offdb_studies.json"))
        schema = {tuple(sorted(s)) for s in studies}
        self.assertEqual(schema, {tuple(sorted(p["entry"]))})                 # exactly the existing entries' fields
        e = p["entry"]
        self.assertEqual((e["id"], e["lineage"], e["attempts"], e["alpha"]),
                         ("HFC1_OUTCOME_3D_2026-11-04", "delta_neutral_funding_carry", 0, 0.0))
        self.assertEqual(e["files"], ["research/data/hfc1_report3d/hfc1_3d_2026-11-04.json",
                                      "research/data/hfc1_report3d/hfc1_3d_2026-11-04.md"])
        self.assertIn('"written": false', read(os.path.join(self.out, "hfc1_3d_2026-11-04.md")))

    def test_R14_result_hash_deterministic_and_independently_recomputable(self):
        self.make_matrix()
        r1 = self.run3d(DUE_1104)
        r2 = self.run3d(DUE_1104 + 86400, out=os.path.join(self.tmp, "o2"))
        self.assertEqual(r1["result_sha256"], r2["result_sha256"])
        self.assertNotEqual(r1["run_utc"], r2["run_utc"])
        j = json.loads(read(os.path.join(self.out, "hfc1_3d_2026-11-04.json")))
        body = {k: v for k, v in j.items() if k not in ("result_sha256", "run_utc", "db_uri", "dry_run")}
        current = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()      # tool as of 65e4329
        body["cohort_status"] = {k: v for k, v in body["cohort_status"].items() if v["status"] == "REPORTED"}
        body["offdb_proposal"] = {k: v for k, v in body["offdb_proposal"].items() if k != "already_present"}
        patched = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()      # after patch B2
        self.assertIn(j["result_sha256"], (current, patched))

    def test_R14b_explicit_cohort_hash_ignores_other_cohort_files(self):
        self.make_matrix()
        r1 = self.run3d(DUE_1104, days=(DAY,))
        write_cohort(self.cdir, DAY7, matrix_rows())                          # 11-07's file lands later on 11-08
        r2 = self.run3d(DUE_1104 + 3600, days=(DAY,))                         # same out: idempotent, no EXISTS
        self.assertEqual(r1["result_sha256"], r2["result_sha256"])

    def test_R15_existing_reports_never_overwritten(self):
        self.make_matrix()
        self.run3d()
        jp, mp = (os.path.join(self.out, "hfc1_3d_2026-11-04" + e) for e in (".json", ".md"))
        h = sha(jp), sha(mp)
        self.run3d(DUE_1104 + 60)                                             # same result: idempotent
        self.assertEqual((sha(jp), sha(mp)), h)
        j = json.loads(read(jp))
        j["result_sha256"] = "0" * 64
        with open(jp, "w") as f:
            json.dump(j, f)
        h = sha(jp), sha(mp)
        with mock.patch("time.time", lambda: DUE_1104 + 60), mock.patch.dict(hr.PINNED, {}, clear=True):
            rc, msg = self.quiet(hr.main, ["--db", self.db, "--cohort-dir", self.cdir, "--out", self.out,
                                           "--cohort", "2026-11-04"])
        self.assertEqual((rc, msg["status"]), (3, "EXISTS"))
        self.assertEqual((sha(jp), sha(mp)), h)
        open(jp, "wb").close()                                                # crash-emptied file (0 bytes)
        with self.assertRaises(hr.Refused) as c:
            self.run3d()
        self.assertEqual((c.exception.status, c.exception.code), ("EXISTS", 3))
        self.assertEqual(os.path.getsize(jp), 0)

    def test_R16_read_only_rollback_db(self):
        self.make_matrix()
        before = sha(self.db)
        self.run3d()
        self.assert_untouched(self.db, before)
        with closing(hr.connect_ro(self.db)) as con:
            self.assertIn("mode=ro", hr.ro_uri(self.db))
            self.assertEqual(con.execute("PRAGMA query_only").fetchone()[0], 1)
            for q in ("INSERT INTO observations(ts, prev_hash, hash) VALUES (1, '', 'z')", "CREATE TABLE y(a)",
                      "DELETE FROM observations"):
                with self.assertRaises(sqlite3.OperationalError):
                    con.execute(q)
        self.assertEqual(sha(self.db), before)

    def test_R16b_read_only_with_live_wal_writer_like_production(self):
        self.make_matrix()
        w = sqlite3.connect(self.db)                                          # the collector: WAL, open, uncheckpointed
        self.addCleanup(w.close)
        self.assertEqual(w.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        w.execute("PRAGMA wal_autocheckpoint=0")
        w.execute("INSERT INTO observations(ts, detector, metric, payload, prev_hash, hash) "
                  "VALUES (1, 'other/1', 'x', '{}', '', 'wal-row')")
        w.commit()
        main, wal = sha(self.db), sha(self.db + "-wal")
        rep = self.run3d()
        self.assertEqual(rep["cohorts"][0]["census_snapshots_in_window"], 72)
        self.assertEqual((sha(self.db), sha(self.db + "-wal")), (main, wal))  # reader wrote neither file
        self.assertFalse(os.path.exists(self.db + "-journal"))

    def test_R16c_wal_db_without_writer_main_file_unchanged(self):
        """Limitation L5: on a WAL database with no open writer, SQLite's read-only open may create -wal/-shm side
        files (SQLite behaviour, also for hfc1_daily). The main file's bytes stay unchanged."""
        self.make_matrix()
        w = sqlite3.connect(self.db)
        w.execute("PRAGMA journal_mode=WAL")
        w.close()
        before = sha(self.db)
        self.run3d()
        self.assertEqual(sha(self.db), before)

    def test_R17_protocol_rules_unchanged_and_tool_run_changes_no_input(self):
        with open(PROTO, "rb") as f:
            head = f.read(PROTO_RULES_LEN)
        self.assertEqual(hashlib.sha256(head).hexdigest(), PROTO_RULES_SHA)   # rules as locked before data (48a0a63)
        watched = [PROTO, hr.OFFDB, os.path.abspath(hr.__file__)] + [os.path.join(hr.COHORTS, n)
                                                                      for n in sorted(os.listdir(hr.COHORTS))]
        before = {p: sha(p) for p in watched}
        canon = os.path.exists(hr.OUT) and sorted(os.listdir(hr.OUT))
        self.make_matrix()
        self.run3d()
        self.quiet(hr.main, ["--dry-run", "--out", os.path.join(self.tmp, "dry")])
        with mock.patch("time.time", lambda: DUE_1104 - 1):                   # a premature real-path CLI call
            rc, _ = self.quiet(hr.main, ["--db", os.path.join(self.tmp, "absent.db"), "--out", self.out + "x"])
        self.assertEqual(rc, 2)
        self.assertEqual({p: sha(p) for p in watched}, before)
        self.assertEqual(os.path.exists(hr.OUT) and sorted(os.listdir(hr.OUT)), canon)

    def test_R17b_static_read_only_no_network(self):
        import ast
        src = read(os.path.abspath(hr.__file__))
        src = src.replace(ast.get_docstring(ast.parse(src), clean=False), "", 1)    # the docstring says "never pm_lp"
        pre = src.split("# ---- synthetic data")[0]
        self.assertEqual(pre.count("sqlite3.connect("), 1)                   # only connect_ro
        self.assertIn("sqlite3.connect(ro_uri(path), uri=True)", pre)
        for bad in ("urllib.request", "import socket", "http.client", "pm_lp", "--now", "os.remove", "shutil"):
            self.assertNotIn(bad, src)


# ---- R18: the committed cohort files through the tool (synthetic census, no real outcome) ------------------------------

class CommittedCohorts(Readiness):
    def test_R18_real_cohort_schema_end_to_end_with_synthetic_census(self):
        with open(os.path.join(hr.COHORTS, "2026-11-04.json"), encoding="utf-8") as f:
            body = json.load(f)
        syms = [r["symbol"] for r in body["rows"]]
        self.db = build_db(os.path.join(self.tmp, "lab.db"), {s: const(0.0002) for s in syms}, T0_1104,
                           ts_utc(2026, 11, 9))
        self.cdir = hr.COHORTS                                                # committed files, real pins
        rep, path = hr.run(self.db, hr.COHORTS, self.out, [], "3d", DUE_1104)  # default invocation, real PINNED
        self.assertTrue(path.startswith(self.tmp))
        self.assertEqual(rep["cohort_status"]["2026-11-04"]["status"], "REPORTED")
        self.assertEqual(rep["cohort_status"]["2026-11-05"]["status"], "NOT_DUE")
        c = rep["cohorts"][0]
        self.assertTrue(c["cohort_file_pinned_in_protocol"])
        self.assertTrue(c["cohort_file_sha256"].startswith("a5f831c40c19"))
        g = c["groups"]
        self.assertEqual((g["C0"]["members"], g["C0+"]["members"]), (120, 72))
        self.assertEqual((g["frafald F1 intet spotpar"]["members"], g["frafald F1 multiplikator"]["members"]), (117, 1))
        for n in ("1000", "5000"):
            self.assertEqual(g[f"bestod_F1-F5_N{n}"]["members"], 2)
            self.assertEqual(g[f"bestod_F1-F6_3d_N{n}"]["members"], 0)        # 0 covered ex ante at 3 d (protocol)
            self.assertEqual(g["C0"][f"N{n}"]["cost_known"], 2)
            self.assertEqual(g["C0"][f"N{n}"]["cost_unknown_no_spot_or_book"], 118)
        self.assertEqual(g["C0"]["missing"], 0)
        rep2, _ = hr.run(self.db, hr.COHORTS, self.out, [DAY2], "3d", DUE_1105)
        self.assertEqual(rep2["cohorts"][0]["groups"]["C0"]["members"], 119)


# ---- findings B1-B4 (expected failures; see HFC1_REPORT_READINESS.md) ------------------------------------------------

class Findings(Readiness):
    def test_B1_non_coin_perp_not_labelled_not_trading(self):
        """census/1 coin_perps holds only COIN-underlying TRADING perps (lab/scanner._perps); a tokenised stock perp
        that trades the whole window is never in it, and the tool labels it 'perp ikke TRADING ved vinduets slut'."""
        self.make_matrix(coin=lambda ts: {"PASSAUSDT", "PASSBUSDT", "NOSPOTUSDT", "1000MULTUSDT", "NOBOOKUSDT",
                                          "EMPTYUSDT", "CAP5USDT", "CAP1USDT", "DELISTUSDT"})    # no STOCK, no NOTTRAD
        m = self.members(self.run3d())
        self.assertNotIn("ikke TRADING", m["STOCKUSDT"]["status"])
        self.assertIsNot(m["STOCKUSDT"]["perp_trading_at_end"], False)

    def test_B1_control_coin_perp_that_leaves_is_flagged(self):
        """The intended case works today: a COIN perp in coin_perps that leaves it before the end is flagged."""
        self.make_matrix(coin=lambda ts: {"PASSAUSDT"} if ts < T1_1104 - 3 * 3600 else set())
        m = self.members(self.run3d())
        self.assertIn("perp ikke TRADING ved vinduets slut", m["PASSAUSDT"]["status"])

    def test_B2_rerun_after_offdb_entry_added_is_not_an_integrity_failure(self):
        self.make_matrix()
        off = os.path.join(self.tmp, "offdb.json")
        with open(hr.OFFDB, encoding="utf-8") as f:
            data = json.load(f)
        with open(off, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with mock.patch.object(hr, "OFFDB", off):
            r1 = self.run3d()
            data["studies"].append(r1["offdb_proposal"]["entry"])            # the run procedure's manual step
            with open(off, "w", encoding="utf-8") as f:
                json.dump(data, f)
            r2 = self.run3d(DUE_1104 + 600)                                   # today: Refused EXISTS (exit 3)
        self.assertEqual(r1["result_sha256"], r2["result_sha256"])

    def test_B2b_default_invocation_hash_depends_on_not_due_cohort_files(self):
        self.make_matrix()
        r1 = self.run3d(DUE_1104, days=())
        write_cohort(self.cdir, DAY7, matrix_rows())                          # 11-07's file written after the run
        r2 = self.run3d(DUE_1104 + 3600, days=())                             # today: Refused EXISTS (exit 3)
        self.assertEqual(r1["result_sha256"], r2["result_sha256"])

    def test_B3_idempotent_rerun_does_not_leave_the_md_missing(self):
        self.make_matrix()
        self.run3d()
        mp = os.path.join(self.out, "hfc1_3d_2026-11-04.md")
        os.remove(mp)                                                         # crash between the two writes
        try:
            self.run3d(DUE_1104 + 60)
        except hr.Refused:
            return                                                            # refusing would also be acceptable
        self.assertTrue(os.path.exists(mp))                                   # today: success, md still missing

    def test_B4_due_cohort_without_file_is_not_reported_as_not_due(self):
        self.make_matrix()
        os.remove(os.path.join(self.cdir, "2026-11-04.json"))
        with self.assertRaises(hr.Refused) as c:
            self.run3d(DUE_1104 + 60)
        self.assertNotEqual(c.exception.status, "NOT_DUE")                    # today: NOT_DUE, exit 2
        self.assertEqual(c.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
