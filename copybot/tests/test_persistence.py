import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from persistence import analyse, spearman  # noqa: E402
from store import Store  # noqa: E402


class Persistence(unittest.TestCase):
    def test_spearman(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_same_order_both_halves(self):
        s = Store()
        wallets = [{"addr": f"w{i}", "label": f"w{i}"} for i in range(4)]
        s.set("wallets", wallets)
        for i, w in enumerate(wallets):
            for t, pnl in ((1000, i - 1.5), (9000, 2 * (i - 1.5))):
                s.x("INSERT INTO positions(book,wallet,mint,opened_ts,closed_ts,cost_usd,pnl_usd) VALUES('shadow',?,?,?,?,10,?)",
                    w["addr"], "m", t, t + 60, pnl)
        with redirect_stdout(io.StringIO()):
            res = analyse(s)
        self.assertAlmostEqual(res["rho_total"], 1.0)
        self.assertEqual(res["best_h1"], "w3")
        self.assertEqual(res["best_h1_h2_rank"], 1)


if __name__ == "__main__":
    unittest.main()
