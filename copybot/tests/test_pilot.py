"""PROTOCOL_V3 amendments 29/29a: the simulated execution pilot logs a round before it is played, measures slippage and
cost, stops hard (loss cap, holdings mismatch, clock skew, an error with an open position) and stays stopped until a
human resumes in a terminal; it holds no account, key or order code (29a), and lab/ never imports it."""
import os
import random
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))

import pilot as P  # noqa: E402
from pilot import core  # noqa: E402
from pilot.exchange import DryExchange, floor_step, walk  # noqa: E402

T0 = 1793106600.0                                       # 2026-10-27 13:10 UTC (outside K3)


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def book_get(bid=100.0, ask=100.1, server=None, clock=None, asks=None, bids=None):
    def get(url):
        if "/api/v3/time" in url:
            return {"serverTime": int((server if server is not None else clock()) * 1000)}
        if "exchangeInfo" in url:
            return {"symbols": [{"baseAsset": "AAA", "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.001"}, {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "NOTIONAL", "minNotional": "5"}]}]}
        return {"bids": bids or [[str(bid), "1000"]], "asks": asks or [[str(ask), "1000"]]}
    return get


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pilot")
        self.ledger = core.Ledger(self.tmp)
        self.clock = Clock()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ex(self, **kw):
        return DryExchange(get=book_get(clock=self.clock, **kw), sleep=self.clock.sleep, usdt=100.0)

    def play(self, ex, mode="taker"):
        rng = random.Random(1)
        rng.choice = lambda xs: mode if "taker" in xs else "AAAUSDT"
        return core.play(ex, self.ledger, rng, now=self.clock, sleep=self.clock.sleep)


class Rounds(Base):
    def test_taker_round_is_planned_before_sending_and_measures_slippage_and_cost(self):
        ex = self.ex()
        sent = []
        orig = ex.buy_market_quote
        ex.buy_market_quote = lambda s, q: (sent.append(self.ledger.rows()[-1]["kind"]), orig(s, q))[1]
        r = self.play(ex)
        self.assertEqual(sent, ["plan"])                                    # the plan was on disk first
        self.assertAlmostEqual(r["buy_slip_bp"], 5.0, places=1)             # ask 100.1 vs mid 100.05
        self.assertAlmostEqual(r["sell_slip_bp"], 5.0, places=1)
        self.assertGreater(r["cost_bp"], 29)                                # 2 x 5 bp + 2 x 10 bp fee
        self.assertLess(r["cost_bp"], 31)
        self.assertTrue(r["fee_assumed"])

    def test_slippage_is_measured_against_the_book_each_fill_met(self):
        mids = iter([100.0, 100.0, 100.0, 110.0])        # the market moves between the sell-time read and the fill
        ex = self.ex()

        def book(symbol):
            m = next(mids, 110.0)
            return {"bids": [[str(m - 0.05), "1000"]], "asks": [[str(m + 0.05), "1000"]], "bid": m - 0.05,
                    "ask": m + 0.05}
        ex.book = book
        r = self.play(ex)
        self.assertAlmostEqual(r["buy_slip_bp"], 5.0, places=1)
        self.assertAlmostEqual(r["sell_slip_bp"], 4.5, places=1)            # 0.05 below a mid of 110, never negative

    def test_unfilled_maker_is_cancelled_and_costs_nothing(self):
        r = self.play(self.ex(), mode="maker")
        self.assertEqual((r["filled"], r["status"], r["pnl_usdt"]), (False, "CANCELED", 0.0))

    def test_wide_spread_skips_without_stopping(self):
        self.assertIsNone(self.play(self.ex(bid=100, ask=101)))
        self.assertIsNone(self.ledger.state()["stopped"])
        self.assertEqual(self.ledger.rows()[-1]["skipped"], "spread")

    def test_walk_and_step(self):
        self.assertEqual(walk([["10", "1"], ["20", "1"]], "buy", quote=20)[1], 1.5)
        self.assertAlmostEqual(floor_step(1.23456, 0.001), 1.234)


class Stops(Base):
    def test_loss_cap_stops_and_stays_stopped_until_a_human_resumes(self):
        self.ledger.append(kind="result", dry=True, pnl_usdt=-14.7, mode="taker")
        with self.assertRaises(core.Stopped):
            self.play(self.ex())
        with self.assertRaises(core.Stopped):
            self.play(self.ex())                                            # still stopped
        self.assertFalse(core.human_typed(P.RESUME_PHRASE, inp=lambda p: P.RESUME_PHRASE, tty=False))
        self.assertTrue(core.human_typed(P.RESUME_PHRASE, inp=lambda p: P.RESUME_PHRASE, tty=True))

    def test_clock_skew_stops(self):
        with self.assertRaises(core.Stopped) as cm:
            self.play(self.ex(server=T0 + 2))
        self.assertIn("urforskel", str(cm.exception))

    def test_holdings_mismatch_stops(self):
        ex = self.ex()
        orig = ex.sell_market
        ex.sell_market = lambda s, q: (orig(s, q), ex.wallet.__setitem__("AAA", 5.0))[0]   # something else moved
        with self.assertRaises(core.Stopped) as cm:
            self.play(ex)
        self.assertIn("beholdning", str(cm.exception))

    def test_an_error_with_an_open_position_sells_once_then_stops(self):
        ex = self.ex()

        def boom(*a):
            raise TimeoutError("read timed out")
        sells = []
        orig = ex.sell_market
        ex.sell_market = lambda s, q: (sells.append(q), orig(s, q))[1] if len(sells) else (sells.append(q), boom())
        with self.assertRaises(core.Stopped):
            self.play(ex)
        err = [r for r in self.ledger.rows() if r.get("kind") == "error"][0]
        self.assertTrue(err["position"])
        self.assertEqual(len(sells), 2)                                     # the round's sell, then one flatten

    def test_an_error_without_a_position_is_logged_and_skipped(self):
        ex = self.ex()

        def boom(*a):
            raise TimeoutError("read timed out")
        ex.buy_market_quote = boom
        self.assertIsNone(self.play(ex))
        self.assertIsNone(self.ledger.state()["stopped"])


class PaperOnly(Base):
    def test_resume_needs_a_terminal_and_the_exact_phrase(self):
        self.assertFalse(core.human_typed(P.RESUME_PHRASE, inp=lambda p: P.RESUME_PHRASE, tty=False))
        self.assertFalse(core.human_typed(P.RESUME_PHRASE, inp=lambda p: "ja", tty=True))

    def test_29a_no_account_key_or_order_code_exists(self):
        """Amendment 29a point 1: only the dry run; the rules of tests/test_lab_safety.py also hold for pilot/."""
        import ast
        import test_lab_safety as safety
        for f in sorted(os.listdir(os.path.join(HERE, "pilot"))):
            if not f.endswith(".py"):
                continue
            with open(os.path.join(HERE, "pilot", f), encoding="utf-8") as fh:
                src = fh.read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [n.name for n in node.names] + ([node.module] if getattr(node, "module", None) else [])
                    self.assertFalse({n.split(".")[0] for n in names} & safety.FORBIDDEN_IMPORTS, f)
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    self.assertNotRegex(node.name, safety.FORBIDDEN_NAMES, f)
            low = src.lower()
            for t in safety.FORBIDDEN_TEXT + ("api.binance.com", "signature", "method=\"post\"", "method=\"delete\""):
                self.assertNotIn(t, low, f)

    def test_limits_match_amendment_29(self):
        self.assertEqual((P.CAPITAL_USDT, P.LOSS_CAP_USDT, P.MAX_ORDER_USDT, P.MAX_ROUNDS), (100.0, 15.0, 20.0, 80))
        self.assertLessEqual(P.ROUND_USDT, P.MAX_ORDER_USDT)
        self.assertEqual(P.SYMBOLS, ("BTCUSDT", "ETHUSDT", "EPICUSDT", "XTZUSDT", "VETUSDT", "MITOUSDT", "HOTUSDT"))


class Schedule(Base):
    def test_rounds_never_start_in_a_k3_window(self):
        self.assertTrue(core.k3_window(1793102400 + 10 * 60))              # 12:10 UTC
        self.assertFalse(core.k3_window(T0))                                # 13:10 UTC
        self.assertTrue(core.k3_window(1793102400 + 85 * 60))               # 13:25 UTC (14:00 window)
        starts = []
        ex = self.ex()
        orig = core.play

        def spy(*a, **kw):
            starts.append(self.clock())
            return orig(*a, **kw)
        core.play = spy
        try:
            core.run(ex, self.ledger, 4, rng=random.Random(3), now=self.clock, sleep=self.clock.sleep)
        finally:
            core.play = orig
        self.assertEqual(len(starts), 4)
        self.assertFalse(any(core.k3_window(t) or core.k3_window(t + 120) for t in starts))


class Isolation(unittest.TestCase):
    def test_lab_never_imports_the_pilot(self):
        for root, _, files in os.walk(os.path.join(HERE, "lab")):
            for f in files:
                if f.endswith(".py"):
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        src = fh.read()
                    self.assertNotRegex(src, r"(?m)^\s*(from|import)\s+pilot\b", f)


if __name__ == "__main__":
    unittest.main()
