"""Director order 56: SYNTHETIC execution simulator for the fomo 30-second copy-trade claim.

Every path here is synthetic. These tests prove the simulator obeys pool physics and bookkeeping;
they say nothing about real profitability.
"""
import ast
import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.desk.fomo import sim  # noqa: E402

SIM_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "desk", "fomo", "sim.py")


def P(**kw):
    base = dict(size_sol=1.0, time_stop_s=600, bot_fee_frac=0.01, slippage_tolerance=1.0, follow_sells=False)
    base.update(kw)
    return sim.Params(**base)


def amm(sol=30.0, tokens=1e9, **kw):
    d = {"kind": "amm", "sol": sol, "tokens": tokens}
    d.update(kw)
    return d


def path(events, pool=None, end_t=None, pid="p"):
    p = {"id": pid, "pool": pool or amm(), "events": events}
    if end_t is not None:
        p["end_t"] = end_t
    return p


def reconcile(row):
    return row["net_pnl_sol"] - (row["gross_pnl_sol"] - sum(row["costs"].values()))


class AMMInvariants(unittest.TestCase):
    def test_k_never_decreases_after_fee_swap(self):
        for lp in (1.0, 0.5, 0.0):
            p = sim.AMMPool(30.0, 1e9, 0.0025, lp_fee_share=lp)
            k0 = p.k()
            p.buy(2.0)
            k1 = p.k()
            p.sell(1e7)
            k2 = p.k()
            self.assertGreaterEqual(k1, k0 * (1 - 1e-12))
            self.assertGreaterEqual(k2, k1 * (1 - 1e-12))
            if lp > 0:
                self.assertGreater(k1, k0)
                self.assertGreater(k2, k1)

    def test_round_trip_loses_at_least_both_fees(self):
        """Precise claim: buy s SOL then sell all tokens at once -> loss >= buy fee + sell fee, both in SOL
        as charged (fee-on-input; no fee left in the pool). Pinned finding: the literal loss >= 2*f*s is
        FALSE for fee-on-input x*y=k (loss -> s*(2f - f^2) for tiny s), so it is not asserted."""
        f = 0.0025
        for s in (0.001, 0.1, 1.0, 10.0, 100.0):
            p = sim.AMMPool(30.0, 1e9, f, lp_fee_share=0.0)
            qb = p.buy(s)
            qs = p.sell(qb["tokens_out"])
            loss = s - qs["sol_out"]
            self.assertGreaterEqual(loss, qb["fee_sol"] + qs["fee_sol"] - 1e-12)
            self.assertGreater(loss, f * s)  # at least one full fee
            self.assertLess(loss, 2 * f * s)  # the pinned finding
        p = sim.AMMPool(30.0, 1e9, f, lp_fee_share=1.0)  # fees kept by LPs: still a loss
        qb = p.buy(1.0)
        self.assertGreater(1.0 - p.sell(qb["tokens_out"])["sol_out"], 0.0)

    def test_bigger_size_worse_average_price(self):
        p = sim.AMMPool(30.0, 1e9, 0.0025)
        prev = 0.0
        for s in (0.01, 0.1, 0.5, 1, 2, 5, 10, 50):
            avg = s / p.quote_buy(s)["tokens_out"]
            self.assertGreater(avg, prev)
            self.assertGreater(avg, p.mid_price())
            prev = avg
        prev = float("inf")
        for n in (1e5, 1e6, 1e7, 1e8, 5e8):
            avg = p.quote_sell(n)["sol_out"] / n
            self.assertLess(avg, prev)
            self.assertLess(avg, p.mid_price())
            prev = avg


class BondingCurveTests(unittest.TestCase):
    def curve(self):
        return sim.make_venue({"kind": "curve"}, P())

    def test_price_rises_with_cumulative_buys(self):
        c = self.curve()
        prev = c.mid_price()
        for _ in range(10):
            c.buy(3.0)
            self.assertGreater(c.mid_price(), prev)
            prev = c.mid_price()

    def test_completion_closes_curve_and_migration(self):
        c = self.curve()
        q = c.buy(1000.0)
        self.assertLess(q["sol_used"], 1000.0)  # only filled to capacity
        self.assertTrue(c.complete)
        self.assertFalse(c.tradable())
        self.assertAlmostEqual(c.real_sol, 85.0, delta=0.1)  # ~85 SOL real at completion (ASSUMPTION constants)
        w = sim._World(c, P())
        w.apply({"t": 1, "type": "migrate", "success": True})
        self.assertIsInstance(w.venue, sim.AMMPool)
        self.assertAlmostEqual(w.venue.sol, c.real_sol)
        self.assertEqual(w.venue.tokens, sim.PUMPFUN_CURVE["migration_tokens"])

    def test_entry_after_failed_migration_not_executable(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 5, "type": "swap", "side": "buy", "size": 500.0},
               {"t": 10, "type": "migrate", "success": False}]
        r = sim.simulate_trade(path(evs, pool={"kind": "curve"}, end_t=1000), P())
        self.assertEqual(r["exit_reason"], "NOT_EXECUTABLE")
        self.assertEqual(r["status"], "NOT_FILLED")
        self.assertIn(r["not_executable_reason"], ("pool_dead", "curve_complete"))

    def test_holding_through_failed_migration_is_pool_dead(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 40, "type": "swap", "side": "buy", "size": 500.0},
               {"t": 50, "type": "migrate", "success": False}]
        r = sim.simulate_trade(path(evs, pool={"kind": "curve"}, end_t=1000), P())
        self.assertEqual(r["exit_reason"], "POOL_DEAD")
        self.assertEqual(r["follower"]["exit_sol_out"], 0.0)
        self.assertAlmostEqual(r["net_pnl_sol"], -r["cost_basis_sol"], places=12)

    def test_successful_migration_trades_on(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 40, "type": "swap", "side": "buy", "size": 500.0},
               {"t": 50, "type": "migrate", "success": True},
               {"t": 60, "type": "tick"}]
        r = sim.simulate_trade(path(evs, pool={"kind": "curve"}, end_t=1000), P(time_stop_s=100))
        self.assertIn(r["exit_reason"], ("TP_10X", "TIME_STOP"))
        self.assertGreaterEqual(r["t_exit"], 50.0)  # nothing executable while the curve was complete
        self.assertGreater(r["follower"]["exit_sol_out"], 0.0)


class DelayTests(unittest.TestCase):
    WINDOW = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
              {"t": 10, "type": "swap", "side": "buy", "size": 2.0},
              {"t": 20, "type": "swap", "side": "buy", "size": 3.0}]

    def test_follower_entry_not_better_than_leader(self):
        for size in (0.01, 1.0, 5.0):
            r = sim.simulate_trade(path(list(self.WINDOW), end_t=1000), P(size_sol=size))
            self.assertGreaterEqual(r["follower"]["entry_price"], r["leader"]["entry_price"])
            self.assertEqual(r["t_entry"], 30.0)
            self.assertEqual(sim.copy_never_better_than_leader(r), [])

    def test_delay_zero_still_pays_own_impact(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0}]
        r = sim.simulate_trade(path(evs, end_t=1000), P(delay_s=0, slippage_tolerance=0.0))
        f = r["follower"]
        self.assertEqual(r["status"], "CLOSED")
        self.assertGreater(f["entry_price"], f["mid_before_entry"])  # own impact (fee incl.)
        self.assertGreater(f["mid_after_entry"], f["mid_before_entry"])  # own buy moves the pool
        self.assertGreater(f["entry_price"], r["leader"]["entry_price"])  # still behind the leader
        self.assertEqual(f["entry_price"], f["quote_price_signal"])
        self.assertLess(f["exit_price"], f["mid_before_exit"])  # own sell has impact too

    def test_follower_net_not_above_leader_net(self):
        """Precise claim: leader and follower have the SAME size and tx fees; every swap by others between
        the leader's buy and the follower's entry is a buy (no adverse-selection reversal); the leader is
        marked at the follower's exit state. Then follower net SOL <= leader net SOL, for any later path."""
        for seed in range(25):
            rng = random.Random(seed)
            evs = list(self.WINDOW)
            t = 30.0
            for i in range(10):
                t += rng.uniform(1, 60)
                if rng.random() < 0.5:
                    evs.append({"t": t, "type": "swap", "side": "buy", "size": rng.uniform(0.1, 20), "actor": "x%d" % i})
                else:
                    evs.append({"t": t, "type": "swap", "side": "sell", "size": "all", "actor": "x%d" % (i - 1)})
            r = sim.simulate_trade(path(evs, end_t=t + 1000), P(time_stop_s=rng.choice([60, 200, 400]),
                                                               tp_trigger=rng.choice(["price", "executable"])))
            self.assertLessEqual(r["net_pnl_sol"], r["leader"]["net_pnl_sol"] + 1e-12, seed)
            self.assertLessEqual(r["net_pct"], r["leader"]["net_pct"] + 1e-9, seed)
            self.assertGreaterEqual(r["gap_net_pct"], -1e-9)


class TPTests(unittest.TestCase):
    def pump_path(self, pump_sol):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 0.1},
               {"t": 100, "type": "swap", "side": "buy", "size": pump_sol}]
        return path(evs, pool=amm(sol=10.0), end_t=10000)

    def test_mid_hit_but_not_executable_no_tp(self):
        r = sim.simulate_trade(self.pump_path(30.0), P(size_sol=5.0, tp_trigger="executable", time_stop_s=500))
        self.assertGreaterEqual(r["max_mid_multiple_seen"], 10.0)
        self.assertLess(r["max_exec_multiple_seen"], 10.0)
        self.assertNotEqual(r["exit_reason"], "TP_10X")
        self.assertEqual(r["exit_reason"], "TIME_STOP")

    def test_executable_hit_is_tp(self):
        r = sim.simulate_trade(self.pump_path(300.0), P(size_sol=5.0, tp_trigger="executable", time_stop_s=500))
        self.assertEqual(r["exit_reason"], "TP_10X")
        self.assertEqual(r["t_exit"], 100.0)
        self.assertGreaterEqual(r["net_pnl_sol"] + r["cost_basis_sol"], 10 * r["cost_basis_sol"] * (1 - 1e-9))

    def test_price_trigger_fires_but_net_far_below_900(self):
        """The video's rule: TP fires on a 10x spot price (market cap); the fill is the executable quote."""
        r = sim.simulate_trade(self.pump_path(30.0), P(size_sol=5.0, tp_trigger="price", time_stop_s=500))
        self.assertEqual(r["exit_reason"], "TP_10X")
        self.assertLess(r["net_pct"], 500.0)
        self.assertLess(r["max_exec_multiple_seen"], 10.0)

    def test_price_trigger_not_fired_below_10x(self):
        r = sim.simulate_trade(self.pump_path(3.0), P(size_sol=0.1, tp_trigger="price", time_stop_s=500))
        self.assertLess(r["max_mid_multiple_seen"], 10.0)
        self.assertEqual(r["exit_reason"], "TIME_STOP")


class TimeStopAndMissingTests(unittest.TestCase):
    EVS = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
           {"t": 10, "type": "swap", "side": "buy", "size": 2.0},
           {"t": 40, "type": "swap", "side": "buy", "size": 1.0},
           {"t": 70, "type": "swap", "side": "sell", "size": 5e6},
           {"t": 100, "type": "swap", "side": "buy", "size": 3.0},
           {"t": 130, "type": "tick"}]

    def replay_quote(self, prm, upto, tokens_expected):
        pool = sim.AMMPool(30.0, 1e9, prm.dex_fee_frac, prm.lp_fee_share)
        pool.buy(1.0)
        pool.buy(2.0)
        swap_in = prm.size_sol * (1 - prm.bot_fee_frac - prm.mev_frac)
        tok = pool.buy(swap_in)["tokens_out"]
        self.assertAlmostEqual(tok, tokens_expected, delta=tokens_expected * 1e-12)
        if upto >= 40:
            pool.buy(1.0)
        if upto >= 70:
            pool.sell(5e6)
        if upto >= 100:
            pool.buy(3.0)
        return pool.quote_sell(tok)["sol_out"]

    def test_time_stop_exact_with_executable_quote(self):
        prm = P(time_stop_s=60)
        r = sim.simulate_trade(path(list(self.EVS), end_t=200), prm)
        self.assertEqual(r["exit_reason"], "TIME_STOP")
        self.assertEqual(r["t_exit"], 90.0)  # first state >= entry 30 + 60
        self.assertEqual(r["follower"]["exit_sol_out"], self.replay_quote(prm, 90, r["follower"]["tokens"]))

    def test_missing_prices_exit_at_next_state_no_interpolation(self):
        prm = P(time_stop_s=60)
        evs = list(self.EVS) + [{"t": 80, "type": "missing", "until": 125}]
        r = sim.simulate_trade(path(evs, end_t=200), prm)
        self.assertEqual(r["exit_reason"], "TIME_STOP")
        self.assertEqual(r["t_exit"], 130.0)
        want = self.replay_quote(prm, 130, r["follower"]["tokens"])
        self.assertEqual(r["follower"]["exit_sol_out"], want)
        self.assertNotEqual(want, self.replay_quote(prm, 90, r["follower"]["tokens"]))

    def test_missing_to_the_end_is_kept_as_missing_price(self):
        prm = P(time_stop_s=60)
        evs = list(self.EVS) + [{"t": 35, "type": "missing", "until": 1e9}]
        rows = sim.simulate_batch([path(evs, end_t=200)], prm)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["exit_reason"], "MISSING_PRICE")
        self.assertEqual(r["status"], "MARKED_MISSING")
        self.assertLess(r["net_pnl_sol"], 0.0)  # never booked as a gain
        self.assertLess(abs(reconcile(r)), 1e-12)

    def test_time_stop_beyond_path_end_is_missing_price(self):
        r = sim.simulate_trade(path(list(self.EVS), end_t=200), P(time_stop_s=25200))
        self.assertEqual(r["exit_reason"], "MISSING_PRICE")
        self.assertLess(r["net_pnl_sol"], 0.0)


class IlliquidityAndSwingTests(unittest.TestCase):
    def test_tiny_pool_not_executable_reported(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 0.1},
               {"t": 10, "type": "swap", "side": "buy", "size": 0.5}]
        rows = sim.simulate_batch([path(evs, pool=amm(sol=0.5), end_t=1000)], P(size_sol=0.2, slippage_tolerance=0.05))
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["exit_reason"], "NOT_EXECUTABLE")
        self.assertEqual(r["not_executable_reason"], "slippage")
        self.assertAlmostEqual(r["net_pnl_sol"], -(r["params"]["priority_fee_sol"] + r["params"]["network_fee_sol"]))
        self.assertEqual(sim.summarise(rows)["n_by_exit_reason"], {"NOT_EXECUTABLE": 1})

    def test_x20_spike_shorter_than_delay_not_captured(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 0.5},
               {"t": 2, "type": "swap", "side": "buy", "size": 105.0, "actor": "pumper"},
               {"t": 3, "type": "leader_sell", "frac": 1.0},
               {"t": 10, "type": "swap", "side": "sell", "size": "all", "actor": "pumper"}]
        p0 = sim.AMMPool(30.0, 1e9, 0.0025)
        m0 = p0.mid_price()
        p0.buy(0.5)
        p0.buy(105.0)
        self.assertGreaterEqual(p0.mid_price() / m0, 20.0)  # the spike really is x20
        r = sim.simulate_trade(path(evs, end_t=1000), P(follow_sells=True, size_sol=0.5))
        self.assertLess(r["max_mid_multiple_seen"], 10.0)
        self.assertNotEqual(r["exit_reason"], "TP_10X")
        self.assertEqual(r["exit_reason"], "LEADER_SELL")
        self.assertLess(r["net_pct"], 0.0)
        self.assertGreater(r["leader"]["net_pct"], 500.0)


class DeathTests(unittest.TestCase):
    def test_rug_value_near_zero(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 60, "type": "rug", "frac": 0.99999}]
        r = sim.simulate_trade(path(evs, end_t=1000), P())
        self.assertEqual(r["exit_reason"], "RUG")
        self.assertLess(r["net_pct"], -99.0)
        self.assertLess(r["follower"]["exit_sol_out"], 0.01)

    def test_pool_dead_full_loss(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 60, "type": "pool_dead"}]
        r = sim.simulate_trade(path(evs, end_t=1000), P())
        self.assertEqual(r["exit_reason"], "POOL_DEAD")
        self.assertAlmostEqual(r["net_pct"], -100.0, places=9)
        s = sim.summarise([r])
        self.assertAlmostEqual(s["follower_net_sol_total"], r["net_pnl_sol"])


def mixed_batch():
    paths = [sim.random_path(s) for s in range(30)]
    paths.append({"id": "bad", "pool": amm(), "events": [{"t": 0, "type": "leader_buy", "size_sol": 1},
                                                          {"t": 1, "type": "leader_buy", "size_sol": 1}]})
    paths.append({"id": "bad2", "pool": {"kind": "nope"}, "events": [{"t": 0, "type": "leader_buy", "size_sol": 1}]})
    return paths


class CostTests(unittest.TestCase):
    def test_net_equals_gross_minus_costs(self):
        prm = P(mev_frac=0.005, priority_fee_sol=0.001, time_stop_s=300)
        rows = sim.simulate_batch(mixed_batch(), prm)
        checked = 0
        for r in rows:
            if r["status"] == "INVALID_INPUT":
                continue
            self.assertLess(abs(reconcile(r)), 1e-12, r["path_id"])
            self.assertLess(abs(r["total_costs_sol"] - sum(r["costs"].values())), 1e-12)
            checked += 1
        self.assertGreaterEqual(checked, 25)
        self.assertGreaterEqual(len({r["exit_reason"] for r in rows}), 3)

    def test_legacy_fee_scenario_reconciles(self):
        prm = P(**{**sim.LEGACY_COPYBOT_FEES, "time_stop_s": 300})
        for r in sim.simulate_batch([sim.random_path(s) for s in range(20)], prm):
            self.assertLess(abs(reconcile(r)), 1e-12)

    def test_bot_fee_sweep_net_decreases(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 10, "type": "swap", "side": "buy", "size": 2.0},
               {"t": 100, "type": "swap", "side": "buy", "size": 10.0}]
        nets = [sim.simulate_trade(path(evs, end_t=1000), P(bot_fee_frac=b, time_stop_s=200))["net_pnl_sol"]
                for b in (0.0, 0.01, 0.02)]
        self.assertGreater(nets[0], nets[1])
        self.assertGreater(nets[1], nets[2])

    def test_unknowns_have_no_default(self):
        with self.assertRaises(TypeError):
            sim.Params(size_sol=1.0, bot_fee_frac=0.01, slippage_tolerance=0.1, follow_sells=False)
        with self.assertRaises(TypeError):
            sim.Params(size_sol=1.0, time_stop_s=60, slippage_tolerance=0.1, follow_sells=False)
        with self.assertRaises(ValueError):
            P(tp_trigger="mid")


class BatchTests(unittest.TestCase):
    def test_no_silent_drops(self):
        paths = mixed_batch()
        rows = sim.simulate_batch(paths, P())
        self.assertEqual(len(rows), len(paths))
        self.assertEqual([r["path_id"] for r in rows], [p["id"] for p in paths])
        s = sim.summarise(rows)
        self.assertEqual(s["n"], len(paths))
        self.assertEqual(sum(s["n_by_status"].values()), s["n"])
        self.assertEqual(sum(s["n_by_exit_reason"].values()), s["n"])
        self.assertEqual(s["n_by_status"].get("INVALID_INPUT"), 2)
        self.assertEqual(s["n_without_pnl"], 2)
        for r in rows:
            self.assertIn(r["exit_reason"], sim.EXIT_REASONS)
            self.assertIn(r["status"], sim.STATUSES)

    def test_determinism(self):
        a = sim.summary_json(sim.simulate_batch(mixed_batch(), P()), seed=7)
        b = sim.summary_json(sim.simulate_batch(mixed_batch(), P()), seed=7)
        self.assertEqual(a, b)
        ra = json.dumps(sim.simulate_batch(mixed_batch(), P()), sort_keys=True)
        rb = json.dumps(sim.simulate_batch(mixed_batch(), P()), sort_keys=True)
        self.assertEqual(ra, rb)
        s = json.loads(a)
        lo, hi = s["bootstrap_ci_mean_net_pct"]
        self.assertLessEqual(lo, s["mean_net_pct"])
        self.assertGreaterEqual(hi, s["mean_net_pct"])


class LegacyTests(unittest.TestCase):
    def test_legacy_formulas_equal_feefree_xyk(self):
        p = sim.AMMPool(30.0, 1e9, 0.0)
        spot = p.mid_price()
        for s in (0.1, 1.0, 7.0):
            avg = s / p.quote_buy(s)["tokens_out"]
            self.assertAlmostEqual(sim.legacy_buy_avg_price(spot, spot * 0.5, s, 30.0) / avg, 1.0, places=12)
        for n in (1e6, 1e8):
            self.assertAlmostEqual(sim.legacy_sell_value(n, spot, spot * 2, 30.0) / p.quote_sell(n)["sol_out"], 1.0,
                                   places=12)
        self.assertTrue(sim.legacy_impact_ok(0.6, 30.0))
        self.assertFalse(sim.legacy_impact_ok(1.2, 30.0, 3.0))

    def test_legacy_floor_never_cheaper_than_leader(self):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 10, "type": "swap", "side": "sell", "size": 2e8}]  # others sell: physics lets the copy buy cheaper
        raw = sim.simulate_trade(path(evs, end_t=1000), P())
        self.assertLess(raw["follower"]["entry_price"], raw["leader"]["entry_price"])
        self.assertEqual(sim.copy_never_better_than_leader(raw), ["bought_cheaper_than_leader"])
        fl = sim.simulate_trade(path(evs, end_t=1000), P(legacy_floor=True))
        self.assertTrue(fl["legacy_floor_applied"])
        self.assertEqual(sim.copy_never_better_than_leader(fl), [])
        self.assertLess(fl["net_pnl_sol"], raw["net_pnl_sol"])
        self.assertLess(abs(reconcile(fl)), 1e-12)

    def test_legacy_fee_numbers(self):
        f = sim.LEGACY_COPYBOT_FEES
        self.assertEqual((f["dex_fee_frac"], f["bot_fee_frac"], f["mev_frac"], f["network_fee_sol"]),
                         (0.005, 0.01, 0.005, 0.0015))


class WorkedExampleTests(unittest.TestCase):
    def test_worked_example(self):
        a = sim.worked_example()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(sim.worked_example(), sort_keys=True))
        d30 = a["A_delay_30"]
        self.assertGreater(d30["follower_entry_price"], d30["leader_entry_price"])
        self.assertGreater(d30["follower_need_mid_x_vs_p0"], d30["leader_need_mid_x_vs_p0"])
        self.assertGreater(d30["follower_need_mid_x_vs_p0"], a["A_delay_0"]["follower_need_mid_x_vs_p0"])
        b = a["B_video"]
        self.assertAlmostEqual(b["mc_leader_entry_usd"], 47_600, delta=1e-6)
        self.assertAlmostEqual(b["mc_bot_entry_usd"], 49_800, delta=1e-3)
        self.assertEqual(b["legacy_fees"]["exit_reason"], "TP_10X")
        self.assertLess(b["legacy_fees"]["net_pct"], 900.0)
        self.assertLess(b["zero_fees"]["net_pct"], 900.0)
        nets = [v["net_pct"] for v in b["legacy_fees_size_sweep_sol"].values()]
        self.assertEqual(nets, sorted(nets, reverse=True))


class PurityTests(unittest.TestCase):
    ALLOW = {"math", "random", "statistics", "dataclasses", "json", "typing", "itertools", "collections", "enum",
             "hashlib"}
    BANNED = {"socket", "sqlite3", "urllib", "lab", "requests", "numpy", "http", "subprocess", "os"}

    def test_only_stdlib_allowlist(self):
        with open(SIM_PATH, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                mods.add((node.module or "").split(".")[0])
        self.assertTrue(mods <= self.ALLOW, mods - self.ALLOW)
        self.assertFalse(mods & self.BANNED)
        self.assertNotIn("__import__", {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
