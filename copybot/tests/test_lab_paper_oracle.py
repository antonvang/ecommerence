"""An independent accounting oracle for the paper ledger: random seeded fill sequences (adds, partial closes, flips,
fees on every fill) are replayed by a plain average-cost model, and the engine's cash, positions, basis, unrealized,
realized and per-trade P&L must agree after every event. The equity invariant is
equity = capital + closed trading P&L - fees + unrealized (no funding in these sequences)."""
import os
import random
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.db import DB  # noqa: E402
from lab.paper import Book, CostModel, PaperEngine  # noqa: E402
from tests.test_lab_s4 import Clock, strategy  # noqa: E402

COSTS = CostModel(taker_fee=0.0005, extra_slippage=0.0002, expected_spread=0.01)
CAP = 1_000_000.0


class Oracle:
    """Average cost; a flip closes the old position at the fill price and opens the rest at it; each fill's fee is
    split pro rata between the closing and the opening quantity."""

    def __init__(self):
        self.cash, self.pos, self.avg, self.closed_pnl, self.fees, self.trade, self.trades = CAP, 0.0, 0.0, 0.0, 0.0, 0.0, []

    def fill(self, side, q, px, fee):
        s = 1 if side == "buy" else -1
        self.cash -= s * px * q + fee
        self.fees += fee
        if self.pos == 0 or (self.pos > 0) == (s > 0):
            self.avg = (self.avg * abs(self.pos) + px * q) / (abs(self.pos) + q)
            self.pos += s * q
            self.trade -= fee
            return
        closing = min(q, abs(self.pos))
        pnl = closing * (px - self.avg) * (1 if self.pos > 0 else -1)
        self.closed_pnl += pnl
        self.trade += pnl - fee * closing / q
        self.pos += s * q
        if abs(self.pos) < 1e-12:
            self.pos = 0.0
            self.trades.append(self.trade)
            self.trade = 0.0
        elif (self.pos > 0) == (s > 0):                                   # flipped
            self.trades.append(self.trade)
            self.trade = -fee * (q - closing) / q
            self.avg = px


class Ledger(unittest.TestCase):
    def setUp(self):
        self.db, self.clock = DB(":memory:"), Clock()
        self.pe = PaperEngine(self.db, self.clock)
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch.object(self.pe.risk, "after_trade_closed", lambda *a, **k: None),   # no breaker pauses
                  mock.patch.object(self.pe.risk, "after_spread", lambda *a, **k: None)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.db.close()

    def run_sequence(self, seed, steps=60):
        rnd, o = random.Random(seed), Oracle()
        strategy(self.db, f"S{seed}")
        self.pe.start(f"S{seed}", CAP, COSTS)
        eid, px = f"S{seed}", 100.0
        for i in range(steps):
            px *= 1 + rnd.gauss(0, 0.01)
            side = rnd.choice(("buy", "sell"))
            q = round(rnd.uniform(0.1, 3.0) * (2 if rnd.random() < 0.2 else 1), 4)        # some fills flip
            bid, ask = round(px * 0.9995, 6), round(px * 1.0005, 6)
            book = Book(ts=self.clock(), bids=((bid, 1e9),), asks=((ask, 1e9),))
            r = self.pe.submit_taker(eid, f"o{seed}-{i}", "X", side, q, book)
            self.assertEqual(r["status"], "filled", r)
            for f in r["fills"]:
                o.fill(side, f["qty"], f["px"], f["fee"])
            mark = px
            led, pnl = self.pe.ledger(eid), self.pe.pnl(eid, {"X": mark})
            unreal = o.pos * (mark - o.avg) if o.pos else 0.0
            equity = o.cash + o.pos * mark
            self.assertAlmostEqual(led["cash"], o.cash, places=6)
            self.assertAlmostEqual(led["positions"].get("X", 0.0), o.pos, places=9)
            if o.pos:
                self.assertAlmostEqual(led["basis"]["X"], o.avg, places=6)
            self.assertAlmostEqual(pnl["equity"], equity, places=6)
            self.assertAlmostEqual(pnl["unrealized"], unreal, places=6)
            self.assertAlmostEqual(equity, CAP + o.closed_pnl - o.fees + unreal, places=6)   # the invariant
            self.assertAlmostEqual(led["realized"], pnl["realized"], places=6)
            self.assertEqual(len(led["trades"]), len(o.trades))
            for (_, got), want in zip(led["trades"], o.trades):
                self.assertAlmostEqual(got, want, places=6)
            self.assertTrue(self.pe.reconcile(eid)["ok"])
        return o

    def test_random_sequences_with_flips_agree_with_an_independent_oracle(self):
        flips = 0
        for seed in range(8):
            o = self.run_sequence(seed)
            flips += len(o.trades)
        self.assertGreater(flips, 20)

    def test_a_replayed_order_changes_nothing(self):
        strategy(self.db, "R")
        self.pe.start("R", CAP, COSTS)
        book = Book(ts=self.clock(), bids=((99.9, 10.0),), asks=((100.1, 10.0),))
        self.pe.submit_taker("R", "o1", "X", "buy", 1.0, book)
        before = self.pe.ledger("R")
        self.assertEqual(self.pe.submit_taker("R", "o1", "X", "buy", 1.0, book)["status"], "duplicate")
        self.assertEqual(self.pe.ledger("R"), before)


if __name__ == "__main__":
    unittest.main()
