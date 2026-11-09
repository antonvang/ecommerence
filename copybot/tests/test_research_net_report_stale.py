"""Director addendum 59-C: STALE/FRESH/MISSING_MARK at the report's explicit cutoff, at-mark columns, read-only."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import net_report as nr  # noqa: E402

CUT = 1794182400          # 2026-11-09 00:00:00 UTC


def make_db(equity, fills=(), funding=(), nomark=True):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "lab.db")
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE events (id INTEGER PRIMARY KEY, ts INTEGER, kind TEXT, exp_id TEXT, payload TEXT);
        CREATE TABLE sim_equity (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, equity REAL, cash REAL,
                                 exposure REAL, peak REAL, drawdown REAL);
        CREATE TABLE sim_fills (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, order_id TEXT, instrument TEXT,
                                side TEXT, px REAL, qty REAL, fee REAL, mid REAL);
        CREATE TABLE sim_funding (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, instrument TEXT, amount REAL);
    """)
    for led in sorted({e[0] for e in equity} | ({"NOMARK"} if nomark else set())):
        con.execute("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, 'lane.started', ?, ?)",
                    (CUT - 86400, led, json.dumps({"source": "straks", "name": led})))
        con.execute("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, 'paper.started', ?, ?)",
                    (CUT - 86400, led, json.dumps({"capital": 10000})))
    con.executemany("INSERT INTO sim_equity (exp_id, ts, equity, cash, exposure, peak, drawdown) "
                    "VALUES (?, ?, ?, 0, 0, 0, 0)", equity)
    con.executemany("INSERT INTO sim_fills (exp_id, ts, order_id, instrument, side, px, qty, fee, mid) "
                    "VALUES (?, ?, 'o', 'XUSDT', ?, 100, 1, ?, 100)", fills)
    con.executemany("INSERT INTO sim_funding (exp_id, ts, instrument, amount) VALUES (?, ?, 'XUSDT', ?)", funding)
    con.commit()
    con.close()
    ro = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    ro.execute("PRAGMA query_only=ON")
    return ro, p


def acc(rep, led):
    return [a for a in rep["accounts"] if a["ledger"] == led][0]


class Stale(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(nr.freshness(CUT - 7200, CUT), ("FRESH", 7200))      # exactly 2 h is FRESH
        self.assertEqual(nr.freshness(CUT - 7201, CUT), ("STALE", 7201))
        self.assertEqual(nr.freshness(None, CUT), ("MISSING_MARK", None))

    def test_status_counts_and_no_current_total_when_stale(self):
        con, _ = make_db([("FRESH1", CUT - 600, 10010.0), ("OLD", CUT - 62000, 9990.0)])
        rep = nr.build(con, CUT + 2280, CUT)
        self.assertEqual((acc(rep, "FRESH1")["mark_status"], acc(rep, "OLD")["mark_status"],
                          acc(rep, "NOMARK")["mark_status"]), ("FRESH", "STALE", "MISSING_MARK"))
        sm = rep["summary"]
        self.assertEqual((sm["fresh"], sm["stale"], sm["missing_mark"]), (1, 1, 1))
        self.assertAlmostEqual(sm["net_fresh_total"], 10.0)
        self.assertAlmostEqual(sm["net_stale_last_known"], -10.0)
        self.assertIsNone(sm["portfolio_current_total"])
        self.assertIn("ingen aktuel porteføljeværdi", nr.md(rep))

    def test_current_total_only_when_all_fresh(self):
        con, _ = make_db([("A", CUT - 60, 10005.0), ("B", CUT - 7200, 9997.0)], nomark=False)
        sm = nr.build(con, CUT, CUT)["summary"]
        self.assertEqual((sm["fresh"], sm["stale"], sm["missing_mark"]), (2, 0, 0))
        self.assertAlmostEqual(sm["portfolio_current_total"], 2.0)
        self.assertNotIn("ingen aktuel porteføljeværdi", nr.md(nr.build(con, CUT, CUT)))

    def test_fills_and_funding_after_the_mark_are_split_out(self):
        con, _ = make_db([("A", CUT - 3541, 9893.28)],
                         fills=[("A", CUT - 7000, "buy", 1.0), ("A", CUT - 600, "sell", 2.0)],
                         funding=[("A", CUT - 7000, 0.5), ("A", CUT - 60, 0.25)])
        r = acc(nr.build(con, CUT + 2280, CUT), "A")
        self.assertEqual((r["fills"], r["at_mark"]["fills"], r["after_mark"]["fills"]), (2, 1, 1))
        self.assertAlmostEqual(r["at_mark"]["fees"], 1.0)
        self.assertAlmostEqual(r["after_mark"]["fees"], 2.0)
        self.assertAlmostEqual(r["at_mark"]["funding"], 0.5)
        self.assertAlmostEqual(r["after_mark"]["funding"], 0.25)
        a = r["at_mark"]
        self.assertAlmostEqual(r["net"], a["funding"] - a["fees"] - a["book"] - a["allowance"] + a["price_move"],
                               places=9)

    def test_cutoff_selects_the_mark(self):
        con, _ = make_db([("A", CUT - 3541, 9893.28), ("A", CUT + 48, 9892.04)])
        before = acc(nr.build(con, CUT + 2280, CUT), "A")
        after = acc(nr.build(con, CUT + 2280, CUT + 2280), "A")
        self.assertAlmostEqual(before["net"], -106.72, places=6)
        self.assertAlmostEqual(after["net"], -107.96, places=6)
        self.assertEqual(before["marked_at"], CUT - 3541)

    def test_rows_after_cutoff_are_ignored_and_db_unchanged(self):
        con, p = make_db([("A", CUT - 60, 10000.0)], fills=[("A", CUT + 600, "buy", 9.0)],
                         funding=[("A", CUT + 600, 9.0)])
        with open(p, "rb") as f:
            h0 = f.read()
        r = acc(nr.build(con, CUT + 3600, CUT), "A")
        self.assertEqual((r["fills"], r["fees"], r["funding"]), (0, 0.0, 0.0))
        with open(p, "rb") as f:
            self.assertEqual(f.read(), h0)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM sim_equity")


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
