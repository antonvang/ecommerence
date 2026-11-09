"""Director addendum 59 B: the lane-report vs net-report reconciliation explains timing differences and flags the rest."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import net_reconcile as nr  # noqa: E402

DAY = "2026-11-08"
END = nr.day_start(DAY) + 86400


def db_with(rows):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "lab.db")
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE sim_equity (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, equity REAL)")
    con.executemany("INSERT INTO sim_equity (exp_id, ts, equity) VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()
    return nr.ro(p)


class Reconcile(unittest.TestCase):
    def test_timing_difference_is_explained(self):
        con = db_with([("A", END - 3541, 9893.28), ("A", END + 48, 9892.04), ("B", END - 62000, 9989.99)])
        lane = {"accounts": [{"ledger": "A", "net": -106.72}, {"ledger": "B", "net": -10.01}]}
        net = {"accounts": [{"ledger": "A", "net": -107.96, "capital": 10000, "marked_at": END + 48, "source": "straks"},
                            {"ledger": "B", "net": -10.01, "capital": 10000, "marked_at": END - 62000, "source": "carry90"}]}
        r = nr.reconcile(lane, net, con, DAY)
        self.assertEqual(r["status"], "RECONCILED")
        self.assertAlmostEqual(r["difference"], -1.24, places=6)
        self.assertEqual([x["cause"] for x in r["accounts"]], ["TIMING_MARK", "SAME_MARK"])
        self.assertGreater(r["accounts"][1]["stale_h"], 17)

    def test_unexplained_difference_is_flagged(self):
        con = db_with([("A", END - 3541, 9893.28), ("A", END + 48, 9892.04)])
        lane = {"accounts": [{"ledger": "A", "net": -106.72}]}
        net = {"accounts": [{"ledger": "A", "net": -110.00, "capital": 10000, "marked_at": END + 48, "source": "straks"}]}
        r = nr.reconcile(lane, net, con, DAY)
        self.assertEqual(r["status"], "ACCOUNTING_UNRECONCILED")
        self.assertEqual(r["accounts"][0]["cause"], "UNEXPLAINED")

    def test_database_is_read_only(self):
        con = db_with([("A", END, 1.0)])
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("INSERT INTO sim_equity (exp_id, ts, equity) VALUES ('X', 1, 1.0)")


if __name__ == "__main__":
    unittest.main()
