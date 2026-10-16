import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import pm_lp  # noqa: E402
from research.pm_lp import (DAY, INV_CAP, Q, Maker, ceil_tick, cluster_lb, combine, competing_q,  # noqa: E402
                            evaluate, floor_tick, gates, n_req, quotes, score, select_panel, simulate, summarize,
                            to_yes, verdict)

T0 = 20000 * DAY          # en vilkårlig UTC-dag
D = 20000


def snap(t, bb=0.49, ba=0.51, q1=0.0, q2=0.0, v=0.04, rate=14.4, tick=0.01):
    return {"t": t, "bb": bb, "ba": ba, "q1": q1, "q2": q2, "v": v, "min_size": 20, "rate": rate, "tick": tick}


def trade(t, side, price, size, token="Y"):
    return {"t": t, "side": side, "price": price, "size": size, "token": token}


class RewardRule(unittest.TestCase):
    def test_score_matches_published_example(self):
        # docs: midpoint 0.50, max spread 3 cents: 100 @ 1 cent -> ((3-1)/3)^2 * 100
        self.assertAlmostEqual(score(0.03, 0.01) * 100, (2 / 3) ** 2 * 100)
        self.assertEqual(score(0.03, 0.03), 0.0)
        self.assertEqual(score(0.03, 0.05), 0.0)

    def test_two_sided_minimum_and_single_sided_third(self):
        self.assertEqual(combine(30, 9, 0.5), 10)        # max(min=9, max/3=10)
        self.assertEqual(combine(30, 9, 0.95), 9)        # udenfor [0.10, 0.90]: kun to-sidet
        self.assertEqual(combine(30, 0, 0.05), 0)

    def test_competing_q_filters_size_and_spread(self):
        q1, q2 = competing_q([(0.49, 100), (0.48, 10), (0.40, 500)], [(0.51, 50)], 0.50, 0.03, 20)
        self.assertAlmostEqual(q1, score(0.03, 0.01) * 100)   # 10 < min size, 0.40 er udenfor v
        self.assertAlmostEqual(q2, score(0.03, 0.01) * 50)

    def test_ticks_and_quotes(self):
        self.assertEqual(floor_tick(0.4799999, 0.01), 0.47)
        self.assertEqual(ceil_tick(0.52, 0.01), 0.52)
        self.assertEqual(quotes(0.50, 0.04, 0.01), (0.48, 0.52))
        self.assertEqual(quotes(0.015, 0.04, 0.01)[0], None)          # bud ville være <= 0

    def test_to_yes(self):
        self.assertEqual(to_yes("BUY", 0.3, "Y", "Y"), ("buy", 0.3))
        self.assertEqual(to_yes("BUY", 0.3, "N", "Y"), ("sell", 0.7))
        self.assertEqual(to_yes("SELL", 0.3, "N", "Y"), ("buy", 0.7))


class Simulation(unittest.TestCase):
    def test_reward_share_and_day_pnl(self):
        snaps = [snap(T0 + 60 * i, q1=0, q2=0) for i in range(1440)]   # ingen konkurrence hele dagen
        per, end = simulate(snaps, [], "Y", {D})
        self.assertAlmostEqual(per[D]["reward"], 14.4, places=6)       # hele puljen
        self.assertAlmostEqual(per[D]["pnl"], 14.4, places=6)
        comp = [snap(T0 + 60 * i, q1=score(0.04, 0.02) * Q, q2=score(0.04, 0.02) * Q) for i in range(1440)]
        per2, _ = simulate(comp, [], "Y", {D})
        ours = score(0.04, 0.02) * Q
        self.assertAlmostEqual(per2[D]["reward"], 14.4 * ours / (ours + 2 * ours), places=6)

    def test_no_reward_outside_panel_days(self):
        per, _ = simulate([snap(T0 + 60)], [], "Y", set())
        self.assertEqual(per, {})

    def test_trade_through_fill_and_adverse_mark(self):
        snaps = [snap(T0), snap(T0 + 120, bb=0.39, ba=0.41)]
        trades = [trade(T0 + 30, "SELL", 0.47, 80)]                    # gennem vores bud 0.48
        per, end = simulate(snaps, trades, "Y", {D})
        self.assertEqual(end["inv"], 80)
        reward = per[D]["reward"]
        self.assertAlmostEqual(per[D]["pnl"] - reward, 80 * (0.40 - 0.48), places=9)   # markeret til ny mid

    def test_at_price_fills_only_in_sensitivity(self):
        trades = [trade(T0 + 30, "SELL", 0.48, 50)]
        self.assertEqual(simulate([snap(T0)], trades, "Y", {D})[1]["inv"], 0)
        self.assertEqual(simulate([snap(T0)], trades, "Y", {D}, rule="at")[1]["inv"], 50)

    def test_no_token_trade_converted(self):
        trades = [trade(T0 + 30, "BUY", 0.55, 30, token="N")]           # = YES-salg til 0.45 < bud 0.48
        self.assertEqual(simulate([snap(T0)], trades, "Y", {D})[1]["inv"], 30)

    def test_quote_size_and_inventory_cap(self):
        m = Maker("Y")
        m.on_snapshot(snap(T0))
        self.assertEqual(m.on_trade(T0 + 1, "SELL", 0.40, 1000, "Y"), Q)  # højst Q pr. interval
        self.assertEqual(m.on_trade(T0 + 2, "SELL", 0.40, 1000, "Y"), 0)
        m.inv = INV_CAP
        m.on_snapshot(snap(T0 + 60))
        self.assertIsNone(m.quote[1])                                     # buddet slukket ved loftet
        self.assertIsNotNone(m.quote[2])

    def test_stale_snapshot_gives_no_fill(self):
        trades = [trade(T0 + 400, "SELL", 0.40, 50)]
        self.assertEqual(simulate([snap(T0)], trades, "Y", {D})[1]["inv"], 0)

    def test_resolution_settles_inventory(self):
        snaps = [snap(T0)]
        trades = [trade(T0 + 30, "SELL", 0.40, 100)]
        per, end = simulate(snaps, trades, "Y", {D}, resolution=(T0 + 3 * DAY, 0.0))
        self.assertEqual(end["settled"], 0.0)
        self.assertAlmostEqual(per[D + 3]["pnl"], -100 * 0.50, places=9)     # mid 0.50 -> udbetaling 0
        self.assertIn(D + 1, per)                                             # dage med beholdning tæller

    def test_reward_multiplier(self):
        snaps = [snap(T0 + 60 * i) for i in range(10)]
        a = simulate(snaps, [], "Y", {D})[0][D]["reward"]
        b = simulate(snaps, [], "Y", {D}, reward_mult=0.5)[0][D]["reward"]
        self.assertAlmostEqual(b, a / 2)


class Statistics(unittest.TestCase):
    def days(self, vals):
        return [{"market": f"m{i % 20}", "day": D + i % 9, "pnl": v, "reward": 1.5, "fills": 0.0, "quoting": True}
                for i, v in enumerate(vals)]

    def test_summary_tail_and_bootstrap(self):
        s = summarize(self.days([1.0] * 100 + [-0.5] * 20), tails={"m1": -3.0})
        self.assertAlmostEqual(s["total_net"], 100 - 10 - 3)
        self.assertEqual(s["market_days"], 120)
        self.assertLess(s["lb_99_5"], s["mean"])
        self.assertEqual(s["median_reward_quoting_day"], 1.5)
        self.assertEqual(cluster_lb([(1.0, 1), (2.0, 1)]), cluster_lb([(1.0, 1), (2.0, 1)]))

    def test_n_req_and_gates_and_verdict(self):
        self.assertIsNone(n_req(-1, 1))
        self.assertEqual(n_req(1.0, 10.0), 1168)        # ceil((3.4174*10)^2)
        s = summarize(self.days([1.0] * 120))
        ok = {"total_net": 1.0}
        g = gates(s, ok, ok, ok, 100, True, True)
        self.assertTrue(all(g.values()))
        self.assertEqual(verdict(g, 0.5, 0.2), "PASS (observational)")
        self.assertEqual(verdict(g, 0.5, -0.1), "FAIL")
        g2 = gates(s, ok, ok, {"total_net": -1.0}, 100, True, True)
        self.assertEqual(verdict(g2, 0.5, 0.2), "INSUFFICIENT")


class PanelAndSeal(unittest.TestCase):
    def test_panel_selection_deterministic_and_excludes(self):
        a = select_panel(["c", "a", "b", "d"], 2, 3)
        self.assertEqual(a, select_panel(["d", "b", "a", "c"], 2, 3))
        self.assertNotIn("a", select_panel(["c", "a", "b", "d"], 4, 3, exclude=["a"]))

    def test_seal_requires_committed_files(self):
        orig = pm_lp.HERE
        try:
            pm_lp.HERE = os.path.join(orig, "does-not-exist")
            self.assertIsNone(pm_lp.frozen())
            self.assertIsNone(pm_lp.start_day())
        finally:
            pm_lp.HERE = orig

    def test_collect_refuses_without_approval_flag(self):
        argv = sys.argv
        try:
            sys.argv = ["pm_lp", "collect"]
            with self.assertRaises(SystemExit):
                pm_lp.main()
        finally:
            sys.argv = argv

    def test_evaluate_carries_inventory_across_periods(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pm_lp.open_db(os.path.join(tmp, "t.db"))
            db.execute("INSERT INTO markets VALUES('c','Y','N','q','[]','2030-01-01',NULL)")
            db.executemany("INSERT INTO panel VALUES(?,?)", [(D, "c"), (D + 1, "c")])
            db.execute("INSERT INTO snaps VALUES(?,?,?,?,?,?,?,?,?,?)", (T0, "c", 0.49, 0.51, 0, 0, 0.04, 20, 14.4, 0.01))
            db.execute("INSERT INTO trades VALUES('k',1,'c',?,'w','Y','SELL',0.40,10)", (T0 + 30,))
            db.execute("INSERT INTO snaps VALUES(?,?,?,?,?,?,?,?,?,?)", (T0 + DAY + 10, "c", 0.29, 0.31, 0, 0, 0.04, 20, 14.4, 0.01))
            db.commit()
            later, _ = evaluate(db, D, D + 1, D + 1)          # periode 2 ser beholdning fra periode 1
            self.assertEqual(len(later), 1)
            self.assertAlmostEqual(later[0]["pnl"] - later[0]["reward"], 10 * (0.30 - 0.50), places=9)
            db.close()


if __name__ == "__main__":
    unittest.main()
