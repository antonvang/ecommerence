import dataclasses
import tempfile
import threading
import unittest
from pathlib import Path

from jupiter_bot.__main__ import synthetic_bars
from jupiter_bot.core import Rejected, SOL
from jupiter_bot.paper import Limits, PaperBook
from jupiter_bot.runner import step
from jupiter_bot.tests.test_contracts import quote


class Accounting(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "paper.db"
        self.limits = Limits(adverse_bps=0)
        self.book = PaperBook(self.path, limits=self.limits)

    def tearDown(self):
        self.book.close()
        self.directory.cleanup()

    def test_round_trip_does_not_charge_swap_fees_twice(self):
        # Returned amounts are already net of the quoted swap fee.
        self.book.fill(quote(), now=100)
        self.assertEqual(self.book.state()["sol"], 250_000_000)
        self.book.fill(quote(SOL, 250_000_000, 25_000_000, observed=101), now=101)
        state = self.book.state()
        self.assertEqual(state["usdc"], self.limits.initial_usdc - 20_000)
        self.assertEqual(state["realized_pnl_usdc"], -20_000)
        self.assertEqual(state["cost_usdc"], 0)
        self.assertEqual(state["sol"], 0)

    def test_partial_sale_preserves_cost_basis(self):
        self.book.fill(quote(), now=100)
        self.book.fill(quote(SOL, 125_000_000, 12_500_000, observed=101), now=101)
        state = self.book.state()
        self.assertEqual(state["sol"], 125_000_000)
        self.assertEqual(state["cost_usdc"], 12_505_000)
        self.assertEqual(state["realized_pnl_usdc"], -15_000)

    def test_duplicate_after_restart_is_not_a_second_fill(self):
        original = quote()
        self.book.fill(original, now=100)
        before = self.book.state()
        self.book.close()
        self.book = PaperBook(self.path, limits=self.limits)
        with self.assertRaises(Rejected):
            self.book.fill(original, now=100)
        self.assertEqual(self.book.state(), before)

    def test_expired_or_tampered_quote_cannot_change_balances(self):
        before = self.book.state()
        for bad, now in ((quote(), 120), (dataclasses.replace(quote(), out_amount=999999999), 100)):
            with self.assertRaises(Rejected):
                self.book.fill(bad, now=now)
            self.assertEqual(self.book.state(), before)

    def test_oversized_buy_and_insufficient_tokens_roll_back(self):
        before = self.book.state()
        for bad in (quote(amount=26_000_000), quote(SOL, 1, 100000)):
            with self.assertRaises(Rejected):
                self.book.fill(bad, now=100)
            self.assertEqual(self.book.state(), before)

    def test_position_cost_cap_includes_assumed_network_fee(self):
        self.book.fill(quote(), now=100)
        before = self.book.state()
        with self.assertRaises(Rejected):
            self.book.fill(quote(observed=101), now=101)
        self.assertEqual(self.book.state(), before)

    def test_insufficient_cash_including_fee_rolls_back(self):
        small = PaperBook(":memory:", limits=Limits(initial_usdc=25_000_000))
        try:
            with self.assertRaises(Rejected):
                small.fill(quote(), now=100)
            self.assertEqual(small.state()["fills"], 0)
            self.assertEqual(small.state()["usdc"], 25_000_000)
        finally:
            small.close()

    def test_frozen_config_and_source_cannot_silently_change(self):
        for config in (dict(limits=Limits(adverse_bps=1)), dict(limits=self.limits, source="JUPITER_QUOTE")):
            with self.assertRaises(Rejected):
                PaperBook(self.path, **config)
        with self.assertRaises(Rejected):
            self.book.fill(quote(source="JUPITER_QUOTE"), now=100)
        self.assertEqual(self.book.state()["fills"], 0)

    def test_adverse_assumption_only_reduces_output(self):
        adverse = PaperBook(":memory:")
        try:
            adverse.fill(quote(), now=100)
            self.assertEqual(adverse.state()["sol"], 249_375_000)
        finally:
            adverse.close()

    def test_two_connections_cannot_fill_same_quote_twice(self):
        barrier, outcomes = threading.Barrier(2), []

        def worker():
            book = PaperBook(self.path, limits=self.limits)
            try:
                barrier.wait(timeout=5)
                try:
                    book.fill(quote(), now=100)
                    outcomes.append("filled")
                except Rejected:
                    outcomes.append("blocked")
            finally:
                book.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(sorted(outcomes), ["blocked", "filled"])
        self.assertEqual(self.book.state()["fills"], 1)

    def test_runner_records_decision_before_request_and_blocks_wrong_quote(self):
        bars = synthetic_bars()[:60]
        now = bars[-1].end

        def wrong_quote(request):
            self.assertEqual(self.book.db.execute("SELECT count(*) FROM decisions").fetchone()[0], 1)
            return quote(SOL, 100_000_000, 10_000_000, observed=now)

        with self.assertRaises(Rejected):
            step(bars, [], self.book, wrong_quote, now, lambda: now)
        self.assertEqual(self.book.state()["fills"], 0)
        self.assertEqual(self.book.db.execute("SELECT count(*) FROM decisions").fetchone()[0], 2)

    def test_runner_warmup_uses_no_quote(self):
        bars = synthetic_bars()[:49]

        def no_quote(request):
            self.fail("Warmup must not request a quote")

        result = step(bars, [], self.book, no_quote, bars[-1].end, lambda: bars[-1].end)
        self.assertEqual(result["execution"], "NO_ORDER")
