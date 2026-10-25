"""Amendment 26: one sim_exec row per paper taker order - book age, spread, depth, the walk on both sides at the order's
size, the estimated book round trip, the filled share and the actual fill distance; written after the order and never
able to change it."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import paper  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import Book, CostModel, PaperEngine  # noqa: E402
from tests.test_lab_s4 import Clock, strategy  # noqa: E402

COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.0004)


class ExecLog(unittest.TestCase):
    def setUp(self):
        self.db, self.clock = DB(":memory:"), Clock()
        self.pe = PaperEngine(self.db, self.clock)
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch.object(self.pe.risk, "after_trade_closed", lambda *a, **k: None),
                  mock.patch.object(self.pe.risk, "after_spread", lambda *a, **k: None)]
        for x in self.p:
            x.start()
        strategy(self.db, "R")
        self.pe.start("R", 10_000.0, COSTS)
        paper._EXEC_ERR.clear()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.db.close()

    def rows(self, metric="taker_order"):
        out = [json.loads(r["payload"]) for r in self.db.q("SELECT payload FROM sim_exec ORDER BY id")]
        return [r for r in out if ("error" in r) == (metric == "error")]

    def test_one_row_with_book_age_spread_depth_and_both_sides(self):
        book = Book(ts=self.clock() - 2, bids=((99.0, 1.0), (98.0, 1.0)), asks=((101.0, 1.0), (102.0, 1.0)))
        self.pe.submit_taker("R", "o1", "X", "buy", 2.0, book)                       # walks both ask levels
        r = self.rows()[0]
        self.assertEqual((r["order_id"], r["side"], r["qty"], r["reduce_only"]), ("o1", "buy", 2.0, False))
        self.assertAlmostEqual(r["book_age_s"], 2, places=6)
        self.assertAlmostEqual(r["spread"], 0.02)
        self.assertEqual(r["levels"], [2, 2])
        self.assertAlmostEqual(r["depth_ask_usd"], 203.0)
        self.assertAlmostEqual(r["walk_same_side"], 0.015)                           # (101 + 102) / 2 vs mid 100
        self.assertAlmostEqual(r["walk_other_side"], 0.015)                          # (99 + 98) / 2
        self.assertAlmostEqual(r["book_round_trip"], 0.03)
        self.assertEqual(r["filled_share"], 1.0)
        self.assertAlmostEqual(r["fill_distance"], 1.5 * 1.0002 / 100 + 0.0002, places=6)   # with the 0.02 % add-on
        self.assertEqual(len(self.rows()), 1)

    def test_partial_fill_and_a_side_too_thin_for_a_round_trip(self):
        book = Book(ts=self.clock(), bids=((99.0, 0.5),), asks=((101.0, 1.0),))
        out = self.pe.submit_taker("R", "o2", "X", "buy", 1.5, book)
        self.assertEqual(out["status"], "partial")
        r = self.rows()[0]
        self.assertAlmostEqual(r["filled_share"], 1 / 1.5)
        self.assertIsNone(r["book_round_trip"])                                      # neither side holds 1.5
        self.assertAlmostEqual(r["walk_same_side"], 0.01)

    def test_a_failing_log_never_changes_the_order_and_is_reported_once_an_hour(self):
        real = self.db.append

        def broken(table, **row):
            if table == "sim_exec" and "error" not in (row.get("payload") or {}):
                raise RuntimeError("disk full")
            return real(table, **row)
        book = Book(ts=self.clock(), bids=((99.9, 10.0),), asks=((100.1, 10.0),))
        with mock.patch.object(self.db, "append", broken):
            a = self.pe.submit_taker("R", "o3", "X", "buy", 1.0, book)
            b = self.pe.submit_taker("R", "o4", "X", "sell", 1.0, book)
        self.assertEqual((a["status"], b["status"]), ("filled", "filled"))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_fills")[0], 2)
        self.assertEqual(len(self.rows("error")), 1)                                 # once an hour
        self.assertIn("disk full", self.rows("error")[0]["error"])

    def test_sim_exec_is_append_only_and_hash_chained(self):
        import sqlite3
        book = Book(ts=self.clock(), bids=((99.9, 10.0),), asks=((100.1, 10.0),))
        self.pe.submit_taker("R", "o7", "X", "buy", 1.0, book)
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.con.execute("UPDATE sim_exec SET payload='{}'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.con.execute("DELETE FROM sim_exec")
        chains, triggers = self.db.verify()
        self.assertTrue(triggers)
        self.assertEqual(chains["sim_exec"], (1, None))

    def test_refused_and_duplicate_orders_are_not_logged(self):
        book = Book(ts=self.clock(), bids=((99.9, 10.0),), asks=((100.1, 10.0),))
        self.pe.submit_taker("R", "o5", "X", "buy", 1.0, book)
        self.pe.submit_taker("R", "o5", "X", "buy", 1.0, book)                      # duplicate
        self.pe.submit_taker("R", "o6", "X", "sell", 5.0, book, reduce_only=True)   # would not reduce: refused
        self.assertEqual([r["order_id"] for r in self.rows()], ["o5"])


if __name__ == "__main__":
    unittest.main()
