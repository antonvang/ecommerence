import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.arb import Series, best_trade, round_trip, simulate_window, swap_out  # noqa: E402

A_FEE, B_FEE = 0.0025, 0.00275


class ArbMath(unittest.TestCase):
    def test_no_opportunity_when_prices_equal(self):
        a = (100_000.0, 15_000_000.0, A_FEE)   # 150 USDC/SOL
        b = (40_000.0, 6_000_000.0, B_FEE)
        self.assertIsNone(best_trade(a, b))

    def test_best_trade_matches_brute_force_and_respects_capital(self):
        a = (100_000.0, 15_000_000.0, A_FEE)   # 150
        b = (40_000.0, 6_120_000.0, B_FEE)     # 153: købe i A, sælge i B
        d, u, g = best_trade(a, b, cap=1e9)
        brute = max((round_trip(x, a, b) - x, x) for x in [i * 100.0 for i in range(1, 20000)])
        self.assertEqual(d, "A->B")
        self.assertAlmostEqual(g, brute[0], delta=max(1.0, brute[0] * 1e-3))
        self.assertLessEqual(best_trade(a, b, cap=1000)[1], 1000)

    def test_fees_kill_small_gaps(self):
        a = (100_000.0, 15_000_000.0, A_FEE)
        b = (40_000.0, 6_024_000.0, B_FEE)     # 0,4 % forskel < 0,525 % gebyrer
        self.assertIsNone(best_trade(a, b))
        self.assertLess(swap_out(100, 15000, 1, 0.003), 150)


class ArbExecution(unittest.TestCase):
    def test_gap_closed_before_landing_is_a_reverted_tx(self):
        # slot 10: 2 % forskel; slot 11 (før vores landing i 12): en anden har lukket den
        A = Series([(10, 0, 100_000.0, 15_000_000.0), (11, 5, 100_000.0, 15_000_000.0)])
        B = Series([(10, 0, 40_000.0, 6_120_000.0), (11, 3, 40_400.0, 6_060_000.0)])
        decs, obs, runs = simulate_window(A, B, A_FEE, B_FEE, k=2, theta=0.0, tx_sol=0.001)
        self.assertEqual(obs, 1)
        self.assertEqual(len(decs), 1)
        self.assertFalse(decs[0]["executed"])
        self.assertAlmostEqual(decs[0]["pnl"], -decs[0]["cost"])   # kun gebyret tabt
        decs_ng, _, _ = simulate_window(A, B, A_FEE, B_FEE, k=2, theta=0.0, tx_sol=0.001, guard=False)
        self.assertLess(decs_ng[0]["pnl"], decs[0]["pnl"])         # uden sikring er tabet større

    def test_gap_still_open_executes_and_one_tx_in_flight(self):
        A = Series([(10, 0, 100_000.0, 15_000_000.0)])
        B = Series([(10, 0, 40_000.0, 6_120_000.0), (11, 0, 40_000.0, 6_120_000.0), (13, 0, 40_000.0, 6_120_000.0)])
        decs, obs, runs = simulate_window(A, B, A_FEE, B_FEE, k=2, theta=0.0, tx_sol=0.001)
        self.assertTrue(decs[0]["executed"])
        self.assertGreater(decs[0]["pnl"], 0)
        self.assertEqual([d["slot"] for d in decs], [10, 13])       # slot 11 springes over: handel i luften
        self.assertEqual(runs, [3])

    def test_series_dedup_and_order(self):
        s = Series([(12, 1, 2.0, 2.0), (12, 0, 1.0, 1.0), (12, 1, 2.0, 2.0), (11, 9, 9.0, 9.0)])
        self.assertEqual(s.at_end_of(12)[2], 2.0)    # sidste i slot efter transaktionsindeks
        self.assertEqual(s.at_end_of(11)[2], 9.0)
        self.assertIsNone(s.at_end_of(10))


if __name__ == "__main__":
    unittest.main()
