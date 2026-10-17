import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import lifecycle  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.lifecycle import LifecycleError, state  # noqa: E402
from lab.paper import Book, CostModel, PaperEngine  # noqa: E402

COSTS = CostModel(taker_fee=0.001, maker_fee=-0.0002, extra_slippage=0.0005, expected_spread=0.002)


class Clock:
    def __init__(self, t=1_000_000):
        self.t = t

    def __call__(self):
        return self.t


def strategy(db, eid, st="PAPER_TRADING", risk=None):
    spec = {"execution": "taker", **({"risk": risk} if risk else {})}
    db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="t", fingerprint=eid, spec_json=spec)
    db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=st, actor="fixture",
              reason="fixture: strategy already approved for paper trading")


def book(clock, bid=99.9, ask=100.1, depth=10.0):
    return Book(ts=clock(), bids=((bid, depth), (bid - 0.2, depth)), asks=((ask, depth), (ask + 0.2, depth)))


class Base(unittest.TestCase):
    def setUp(self):
        self.db, self.clock = DB(":memory:"), Clock()
        self.pe = PaperEngine(self.db, self.clock)

    def tearDown(self):
        self.db.close()

    def started(self, eid="S1", risk=None, capital=10_000.0):
        strategy(self.db, eid, risk=risk)
        self.pe.start(eid, capital, COSTS)
        return eid


class Execution(Base):
    def test_taker_book_walk_partial_fill_fees_and_slippage(self):
        eid = self.started()
        r = self.pe.submit_taker(eid, "o1", "X", "buy", 15, book(self.clock))
        self.assertEqual(r["status"], "filled")
        self.assertEqual([round(f["px"], 6) for f in r["fills"]], [round(100.1 * 1.0005, 6), round(100.3 * 1.0005, 6)])
        self.assertEqual([f["qty"] for f in r["fills"]], [10, 5])
        self.assertAlmostEqual(r["fills"][0]["fee"], 0.001 * 100.1 * 1.0005 * 10)
        self.assertGreater(r["fills"][0]["slippage"], 0)                                   # half spread + allowance
        self.assertGreater(r["fills"][1]["slippage"], r["fills"][0]["slippage"])           # deeper level costs more
        r2 = self.pe.submit_taker(eid, "o2", "X", "buy", 50, book(self.clock), limit_px=100.15)
        self.assertEqual((r2["status"], r2["unfilled"]), ("partial", 40))   # limit stops the walk; IOC remainder
        self.assertTrue(self.db.one("SELECT 1 FROM sim_cancels WHERE order_id='o2'"))
        led = self.pe.ledger(eid)
        self.assertEqual(led["positions"], {"X": 25})
        self.assertTrue(led["simulated"])

    def test_maker_trade_through_only_and_rebate(self):
        eid = self.started()
        self.pe.submit_maker(eid, "m1", "X", "buy", 10, 99.5, book(self.clock))
        self.assertEqual(self.pe.on_trade("X", "t1", self.clock(), 99.5, 50), [])          # at price: no fill
        self.assertEqual(len(self.pe.on_trade("X", "t2", self.clock(), 99.5, 50, at_price=True)), 1)
        self.pe.submit_maker(eid, "m2", "X", "sell", 10, 101.0, book(self.clock))
        self.assertEqual(self.pe.on_trade("X", "t3", self.clock(), 101.2, 4), [{"order_id": "m2", "qty": 4, "px": 101.0}])
        f = self.db.one("SELECT fee, liquidity FROM sim_fills WHERE fill_id='m2|t3'")
        self.assertAlmostEqual(f["fee"], -0.0002 * 101.0 * 4)                              # rebate
        self.assertEqual(f["liquidity"], "maker")
        self.assertEqual(self.pe.on_trade("X", "t3", self.clock(), 101.2, 4), [])          # replayed print

    def test_idempotent_orders_and_isolated_ledgers(self):
        a, b = self.started("A"), self.started("B")
        r1 = self.pe.submit_taker(a, "same-id", "X", "buy", 5, book(self.clock))
        r2 = self.pe.submit_taker(a, "same-id", "X", "buy", 5, book(self.clock))
        self.assertEqual((r1["status"], r2["status"]), ("filled", "duplicate"))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_fills")[0], 1)
        self.pe.submit_taker(b, "b1", "X", "sell", 3, book(self.clock))
        self.assertEqual(self.pe.ledger(a)["positions"], {"X": 5})
        self.assertEqual(self.pe.ledger(b)["positions"], {"X": -3})

    def test_only_paper_trading_strategies_and_no_promotion(self):
        strategy(self.db, "V", st="VALIDATED")
        with self.assertRaises(LifecycleError):
            self.pe.start("V", 1000, COSTS)
        eid = self.started()
        self.assertEqual(self.pe.submit_taker("V", "x", "X", "buy", 1, book(self.clock))["status"], "refused")
        self.assertEqual(state(self.db, eid), "PAPER_TRADING")


class RiskControls(Base):
    def lose_round_trip(self, eid, n):
        self.pe.submit_taker(eid, f"in{n}", "X", "buy", 1, book(self.clock))
        return self.pe.submit_taker(eid, f"out{n}", "X", "sell", 1, book(self.clock, 98.0, 98.2), reduce_only=True)

    def test_two_losses_pause_not_reject_and_resume_needs_human(self):
        eid = self.started()
        self.lose_round_trip(eid, 1)
        self.assertEqual(state(self.db, eid), "PAPER_TRADING")
        self.lose_round_trip(eid, 2)
        self.assertEqual(state(self.db, eid), "PAUSED")
        actions = [r["action"] for r in self.db.q("SELECT action FROM risk_events WHERE rule='consecutive_losses'")]
        self.assertEqual(actions, ["WARN", "PAUSE"])
        r = self.pe.submit_taker(eid, "new", "X", "buy", 1, book(self.clock))
        self.assertEqual(r["status"], "refused")
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='paper.signal_while_paused'"))
        with self.assertRaises(LifecycleError):                          # no automatic resume
            lifecycle.auto_transition(self.db, eid, "PAPER_TRADING", "system:risk", "a later trade would have won")
        with self.assertRaises(LifecycleError):                          # human, but no committed revalidation
            lifecycle.request_approval(self.db, eid, "PAPER_TRADING", "human:t", "please resume now")
        self.assertNotIn("REJECTED", [r[0] for r in self.db.q("SELECT to_state FROM transitions")])
        code = lifecycle.request_approval(self.db, eid, "PAPER_TRADING", "human:t", "revalidation criteria met",
                                          {"committed_files": ["research/PM_LP_SPEC.md"]})
        lifecycle.confirm(self.db, code, "human:t")
        self.pe.risk.record_resume(eid, "human:t")
        self.clock.t += 10
        self.assertEqual(self.pe.submit_taker(eid, "after", "X", "buy", 1, book(self.clock))["status"], "filled")

    def test_paused_strategy_may_still_reduce_exposure(self):
        eid = self.started()
        self.pe.submit_taker(eid, "pos", "X", "buy", 2, book(self.clock))
        self.pe.risk.pause(eid, "manual_test", None, None, "fixture pause")
        self.assertEqual(self.pe.submit_taker(eid, "more", "X", "buy", 1, book(self.clock))["status"], "refused")
        self.assertEqual(self.pe.submit_taker(eid, "cut", "X", "sell", 2, book(self.clock), reduce_only=True)["status"],
                         "filled")
        self.assertEqual(self.pe.submit_taker(eid, "fake", "X", "sell", 1, book(self.clock), reduce_only=True)["status"],
                         "refused")                                      # would open a short

    def test_drawdown_pause_and_resting_entries_cancelled(self):
        eid = self.started(risk={"max_drawdown": 0.05}, capital=1000)
        self.pe.submit_taker(eid, "big", "X", "buy", 9, book(self.clock))
        self.pe.submit_maker(eid, "rest", "X", "buy", 1, 90.0, book(self.clock))
        self.pe.mark(eid, {"X": 90.0})
        self.assertEqual(state(self.db, eid), "PAUSED")
        self.assertTrue(self.db.one("SELECT 1 FROM sim_cancels WHERE order_id='rest'"))

    def test_stale_or_crossed_data_blocks_entries(self):
        eid = self.started()
        old = book(self.clock)
        self.clock.t += 120
        self.assertEqual(self.pe.submit_taker(eid, "s", "X", "buy", 1, old)["status"], "refused")
        crossed = Book(ts=self.clock(), bids=((101, 1),), asks=((100, 1),))
        self.assertEqual(self.pe.submit_taker(eid, "c", "X", "buy", 1, crossed)["status"], "refused")
        self.assertEqual([r["action"] for r in self.db.q("SELECT action FROM risk_events")], ["BLOCK", "BLOCK"])
        self.assertEqual(state(self.db, eid), "PAPER_TRADING")           # data guard is not a pause

    def test_spread_anomalies_investigate_then_pause(self):
        eid = self.started()
        wide = lambda: book(self.clock, 99.0, 101.0)                       # 2 % vs 0.2 % expected
        for i in range(3):
            self.pe.submit_taker(eid, f"w{i}", "X", "buy", 1, wide())
        acts = [r["action"] for r in self.db.q("SELECT action FROM risk_events WHERE rule='spread_anomaly'")]
        self.assertEqual(acts, ["INVESTIGATE", "INVESTIGATE", "INVESTIGATE", "PAUSE"])

    def test_exposure_mismatch_fails_closed_and_only_human_clears(self):
        a, b = self.started("A"), self.started("B")
        self.pe.submit_taker(a, "a1", "X", "buy", 2, book(self.clock))
        self.assertFalse(self.pe.risk.check_exposure(a, {"X": 3}, self.pe.ledger(a)["positions"]))
        self.assertEqual(self.pe.submit_taker(b, "b1", "X", "buy", 1, book(self.clock))["status"], "refused")
        with self.assertRaises(LifecycleError):
            self.pe.risk.clear_fail_closed("system:auto", "auto recovery")
        self.pe.risk.clear_fail_closed("human:t", "ledger reconciled by hand")
        self.assertEqual(self.pe.submit_taker(b, "b2", "X", "buy", 1, book(self.clock))["status"], "filled")
        chains, trig = self.db.verify()
        self.assertTrue(trig and all(x is None for _, x in chains.values()))

    def test_risk_module_cannot_reject(self):
        import inspect
        from lab import risk
        self.assertNotIn('"REJECTED"', inspect.getsource(risk))


if __name__ == "__main__":
    unittest.main()
