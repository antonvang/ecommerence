import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.experiment import metrics  # noqa: E402
from research.features import features  # noqa: E402
from research.launch_data import fetch_events, open_db, parse_pool_tx, snapshot  # noqa: E402
from research.simulate import Costs, PoolHistory, buy_tokens, sell_tokens, simulate  # noqa: E402
from swaps import WSOL  # noqa: E402

MINT = "MemeMint1111111111111111111111111111111pump"
G = {"mint": MINT, "pool": "Pool", "sol_vault": "SolVault", "tok_vault": "TokVault", "grad_ts": 1000, "sol0": 80.0, "tok0": 200_000_000.0}


def bal(idx, mint, amount, dec):
    return {"accountIndex": idx, "mint": mint, "owner": "Pool", "uiTokenAmount": {"amount": str(int(round(amount * 10 ** dec))), "decimals": dec}}


def pool_tx(sig, slot, ts, pre, post, trader="Trader", err=None):
    keys = [trader, "Pool", "SolVault", "TokVault"]
    meta = {"err": err, "fee": 5000, "preBalances": [0] * 4, "postBalances": [0] * 4,
            "preTokenBalances": [bal(2, WSOL, pre[0], 9), bal(3, MINT, pre[1], 6)] if pre else [],
            "postTokenBalances": [bal(2, WSOL, post[0], 9), bal(3, MINT, post[1], 6)]}
    return {"slot": slot, "transactionIndex": 0, "blockTime": ts, "meta": meta,
            "transaction": {"signatures": [sig], "message": {"accountKeys": keys, "header": {"numRequiredSignatures": 1}}}}


def ev(sig, ts, side, sol, tokens, res_sol, res_tok, trader="T", slot=None):
    return {"sig": sig, "ts": ts, "slot": slot or ts, "idx": 0, "trader": trader, "side": side, "sol": sol, "tokens": tokens,
            "res_sol": res_sol, "res_tok": res_tok}


class Amm(unittest.TestCase):
    def test_round_trip_costs_fees_and_bigger_size_costs_more(self):
        t = buy_tokens(80, 2e8, 1.0, 0.003)
        self.assertLess(sell_tokens(80 + 0.997, 2e8 - t, t, 0.003), 1.0)
        small = buy_tokens(80, 2e8, 0.1, 0.003) / 0.1
        big = buy_tokens(80, 2e8, 20, 0.003) / 20
        self.assertLess(big, small * 0.85)  # kraftig slippage ved stor ordre i forhold til poolen

    def test_liquidity_gone_before_exit_is_near_total_loss(self):
        hist = PoolHistory(80, 2e8, 1000, [])
        t = simulate(MINT, hist, 1062, (0.05, 2e8 * 50, "s"), 1300, 0.25)
        self.assertLess(t.net_return, -0.99)

    def test_missing_exit_data_is_not_a_trade_and_counts_pessimistically(self):
        hist = PoolHistory(80, 2e8, 1000, [])
        ok = simulate(MINT, hist, 1062, (80, 2e8, "s"), 1300, 0.25)
        miss = simulate(MINT, hist, 1062, None, 1300, 0.25)
        self.assertEqual(miss.status, "ingen-exit-data")
        self.assertIsNone(miss.net_return)
        m = metrics([ok, miss])
        self.assertEqual((m["n"], m["n_missing_exit"]), (1, 1))
        self.assertAlmostEqual(m["pessimistic_mean"], (ok.net_return - 1.0) / 2)

    def test_trade_records_its_inputs(self):
        hist = PoolHistory(80, 2e8, 1000, [ev("a", 1050, "buy", 5, 1e7, 85, 1.9e8)])
        t = simulate(MINT, hist, 1062, (90, 1.8e8, "x"), 1300, 0.25, Costs(0.003, 0.0005)).as_dict()
        for k in ("entry_sig", "entry_res_sol", "exit_sig", "exit_res_sol", "costs", "t_entry", "t_exit", "size_sol"):
            self.assertIn(k, t)
        self.assertEqual((t["entry_sig"], t["entry_res_sol"], t["exit_sig"]), ("a", 85, "x"))


class History(unittest.TestCase):
    def test_duplicates_and_out_of_order_events(self):
        e1 = ev("a", 1010, "buy", 1, 1e6, 81, 1.99e8)
        e2 = ev("b", 1020, "buy", 1, 1e6, 82, 1.98e8)
        h = PoolHistory(80, 2e8, 1000, [e2, e1, e1])
        self.assertEqual([r[5] for r in h.rows], [None, "a", "b"])
        self.assertEqual(h.state_at(1015)[3], 81)
        self.assertEqual(h.state_at(1020)[3], 82)   # samme sekund regnes som før os
        self.assertIsNone(h.state_at(999))           # før graduation findes poolen ikke


class NoLookAhead(unittest.TestCase):
    def test_future_events_do_not_change_features(self):
        past = [ev("a", 1030, "buy", 2, 1e6, 82, 1.99e8, "A"), ev("b", 1059, "sell", 1, 5e5, 81, 1.995e8, "B")]
        future = [ev("c", 1060, "buy", 50, 3e7, 131, 1.7e8, "C"), ev("d", 1500, "sell", 40, 3e7, 91, 2e8, "D")]
        self.assertEqual(features(G, past, 60), features(G, past + future, 60))
        f = features(G, past, 60)
        self.assertEqual((f["n_buys"], f["n_sells"], f["uniq_buyers"]), (1, 1, 1))
        self.assertAlmostEqual(f["net_sol"], 1.0)


class Parsing(unittest.TestCase):
    def test_buy_sell_migration_and_failed(self):
        buy = parse_pool_tx(pool_tx("b", 5, 1001, (80, 2e8), (81, 1.97e8)), G)
        self.assertEqual((buy["side"], round(buy["sol"], 6), buy["trader"], buy["res_sol"]), ("buy", 1.0, "Trader", 81))
        sell = parse_pool_tx(pool_tx("s", 6, 1002, (81, 1.97e8), (80.5, 1.98e8)), G)
        self.assertEqual(sell["side"], "sell")
        self.assertIsNone(parse_pool_tx(pool_tx("m", 4, 1000, None, (80, 2e8)), G))           # migrationen selv
        self.assertIsNone(parse_pool_tx(pool_tx("f", 7, 1003, (80, 2e8), (81, 1.97e8), err={"x": 1}), G))  # fejlet
        self.assertIsNone(parse_pool_tx(pool_tx("l", 8, 1004, (80, 2e8), (90, 2.2e8)), G))  # likviditet tilføjet

    def test_fetch_is_idempotent_and_snapshot_missing_is_marked(self):
        class FakeRPC:
            def call(self, method, params):
                if params[1].get("sortOrder") == "desc":
                    return {"data": []}  # ingen data: må ALDRIG blive til et signal
                return {"data": [pool_tx("b", 5, 1001, (80, 2e8), (81, 1.97e8)), pool_tx("b", 5, 1001, (80, 2e8), (81, 1.97e8))],
                        "paginationToken": None}
        db = open_db(os.path.join(tempfile.mkdtemp(), "t.db"))
        db.execute("INSERT INTO grads(mint,pool,sol_vault,tok_vault,grad_ts,sol0,tok0) VALUES(?,?,?,?,?,?,?)",
                   (MINT, "Pool", "SolVault", "TokVault", 1000, 80.0, 2e8))
        g = db.execute("SELECT * FROM grads").fetchone()
        fetch_events(db, FakeRPC(), g, 180)
        fetch_events(db, FakeRPC(), g, 180)  # genstart: ingen dubletter
        self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
        snapshot(db, FakeRPC(), g, 1300)
        self.assertEqual(db.execute("SELECT status FROM snapshots").fetchone()[0], "mangler")
        db.close()


class Sampling(unittest.TestCase):
    def test_holdout_is_disjoint_same_period_and_stable_on_restart(self):
        from research.launch_data import sample_chronological
        db = open_db(os.path.join(tempfile.mkdtemp(), "s.db"))
        db.executemany("INSERT INTO grads(mint, grad_ts, grad_slot) VALUES(?,?,?)", [(f"m{i}", 1000 + i, i) for i in range(40)])
        self.assertEqual(sample_chronological(db, 10, 1, None), 10)
        last1 = db.execute("SELECT MAX(grad_ts) FROM grads WHERE sampled=1").fetchone()[0]
        db.executemany("INSERT INTO grads(mint, grad_ts, grad_slot) VALUES(?,?,?)", [(f"n{i}", 2000 + i, 100 + i) for i in range(5)])
        self.assertEqual(sample_chronological(db, 10, 2, last1), 10)
        one = {r[0] for r in db.execute("SELECT mint FROM grads WHERE sampled=1")}
        two = {r[0] for r in db.execute("SELECT mint FROM grads WHERE sampled=2")}
        self.assertFalse(one & two)
        self.assertTrue(all(db.execute("SELECT grad_ts FROM grads WHERE mint=?", (m,)).fetchone()[0] <= last1 for m in two))
        self.assertEqual(sample_chronological(db, 10, 2, last1), 0)  # genstart: stikprøven ændres ikke
        db.close()


class ResearchState(unittest.TestCase):
    def test_counts_pools_not_sample_numbers(self):
        from report import research_state
        root = tempfile.mkdtemp()
        db = open_db(os.path.join(root, "research", "launches.db"))
        db.executemany("INSERT INTO grads(mint, grad_ts, sampled, events_status) VALUES(?,?,?,?)",
                       [("a", 1, 1, "ok"), ("b", 2, 2, "ok"), ("c", 3, 2, None), ("d", 4, 0, None)])
        db.commit(); db.close()
        d = research_state(root)["dataset"]
        self.assertEqual((d["graduations"], d["sampled"], d["fetched"]), (4, 3, 2))  # ikke 1+2+2=5


class ResearchStateArb(unittest.TestCase):
    def test_arbitrage_results_are_shown_without_inventing_numbers(self):
        import json
        from report import research_state
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "research", "results"))
        part = {"slots_with_update": 100, "observed_opportunities": 0, "primary": {"decisions": 0, "executed": 0}}
        json.dump({"version": "arb_v1", "built": 1, "parts": {"train": part, "validation": part, "test": part}, "verdict": "REJECTED",
                   "splits": None}, open(os.path.join(root, "research", "results", "arb_v1.json"), "w"))
        h = research_state(root)["experiments"][0]["hypotheses"][0]
        self.assertEqual((h["id"], h["verdict"], h["test_mean"], h["test_n"]), ("ARB", "REJECTED", None, 0))
        self.assertIn("0 muligheder i 300 slots", h["desc"])


class Metrics(unittest.TestCase):
    def test_profit_factor_drawdown_and_ex_top3(self):
        class T:
            def __init__(self, r):
                self.status, self.net_return = "ok", r
        m = metrics([T(x) for x in (0.5, -0.2, -0.3, 1.0, -0.1, 2.0)])
        self.assertAlmostEqual(m["pf"], 3.5 / 0.6)
        self.assertAlmostEqual(m["max_dd_positions"], 0.5)
        self.assertAlmostEqual(m["mean_ex_top3"], (-0.3 - 0.2 - 0.1) / 3)
        self.assertLessEqual(m["ci95"][0], m["mean"])


if __name__ == "__main__":
    unittest.main()
