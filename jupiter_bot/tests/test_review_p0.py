"""Regression tests for the Claude P0 review (see reviews/CLAUDE_REVIEW.md)."""
import ast
import http.client
import io
import json
import socket
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jupiter_bot.tests.guard import NetworkBlocked, setUpModule, tearDownModule  # noqa: F401
from jupiter_bot.__main__ import PROTECTED, main, synthetic_bars
from jupiter_bot.core import SOL, USDC, Quote, QuoteRequest, Rejected, analyse, atoms, strict_json
from jupiter_bot.jupiter import public_get
from jupiter_bot.paper import APPLICATION_ID, Limits, PaperBook
from jupiter_bot.runner import step
from jupiter_bot.tests.test_contracts import quote

PACKAGE = Path(__file__).resolve().parent.parent


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def synthetic_quote(request, started, observed, out="1000"):
    payload = dict(request.params(), inAmount=str(request.amount), outAmount=out,
                   router="metis", feeBps=0, transaction=None)
    return Quote.parse(request, payload, started, observed, "SYNTHETIC")


class Isolation(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def foreign_db(self):
        path = self.root / "paper.db"  # same file name Copybot uses
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE trades(x)")
        db.commit()
        db.close()
        return path, path.read_bytes()

    def test_network_guard_is_active(self):
        with self.assertRaises(NetworkBlocked):
            socket.create_connection(("api.jup.ag", 443), timeout=1)
        with self.assertRaises(NetworkBlocked):
            socket.getaddrinfo("api.jup.ag", 443)

    def test_package_never_imports_copybot(self):
        for source in PACKAGE.rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                for name in names:
                    with self.subTest(file=source.name, module=name):
                        self.assertFalse(name.split(".")[0] == "copybot")
        self.assertFalse(any(name.split(".")[0] == "copybot" for name in sys.modules))

    def test_foreign_sqlite_database_is_never_written(self):
        path, before = self.foreign_db()
        for source in ("SYNTHETIC", "JUPITER_QUOTE"):
            code, _, err = run_cli("status", "--db", str(path), "--source", source)
            self.assertEqual(code, 2)
            self.assertIn("Not a jupiter_bot paper database", err)
        with self.assertRaises(Rejected):
            PaperBook(path)
        self.assertEqual(path.read_bytes(), before)

    def test_status_is_read_only_and_creates_nothing(self):
        path = self.root / "book.db"
        PaperBook(path, source="SYNTHETIC").close()
        before = path.read_bytes()
        code, _, err = run_cli("status", "--db", str(path), "--source", "JUPITER_QUOTE")
        self.assertEqual(code, 2)
        self.assertIn("not found", err)
        code, out, _ = run_cli("status", "--db", str(path), "--source", "SYNTHETIC")
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out)["live_execution"])
        self.assertEqual(path.read_bytes(), before)
        code, _, _ = run_cli("status", "--db", str(self.root / "missing.db"))
        self.assertEqual(code, 2)
        self.assertFalse((self.root / "missing.db").exists())

    def test_new_book_is_marked_with_application_id(self):
        path = self.root / "fresh.db"
        PaperBook(path).close()
        db = sqlite3.connect(path)
        self.assertEqual(db.execute("PRAGMA application_id").fetchone()[0], APPLICATION_ID)
        db.close()

    def test_protected_copybot_directory_is_refused_before_any_write(self):
        protected = PROTECTED[0]
        target = protected / "data" / "__jupiter_bot_must_not_create__.db"
        self.assertFalse(target.exists())
        code, _, err = run_cli("status", "--db", str(target))
        self.assertEqual(code, 2)
        self.assertIn("protected", err)
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text("{}")
            code, _, _ = run_cli("paper-step", "--snapshot", str(snapshot),
                                 "--quote-file", str(snapshot), "--db", str(target))
        self.assertEqual(code, 2)
        code, _, err = run_cli("quote", "--out", str(target.with_suffix(".json")))
        self.assertEqual(code, 2)
        self.assertIn("protected", err)
        self.assertFalse(target.exists() or target.with_suffix(".json").exists())


class Amounts(unittest.TestCase):
    def test_atoms_never_round_through_decimal_context(self):
        for amount in ("1000000000.0000000009999999999", "0.1" + "0" * 70 + "1", "1e30", "1e-30"):
            with self.subTest(amount=amount), self.assertRaises(Rejected):
                atoms(amount, SOL)
        self.assertEqual(atoms("18446744073.709551615", SOL), 2**64 - 1)
        with self.assertRaises(Rejected):
            atoms("18446744073.709551616", SOL)

    def test_partial_sale_rounding_never_improves_realized_pnl(self):
        book = PaperBook(":memory:", limits=Limits(adverse_bps=0, network_fee_usdc=0))
        try:
            book.fill(quote(amount=10_000_001, output=3), now=100)  # cost 10.000001 USDC for 3 atoms
            book.fill(quote(SOL, 1, 3_333_334, observed=101), now=101)  # exactly 1/3 of cost back
            state = book.state()
            # 10_000_001 / 3 = 3_333_333.67 -> removed 3_333_334, realized 0 (floor gave +1).
            self.assertEqual(state["realized_pnl_usdc"], 0)
            self.assertEqual(state["cost_usdc"], 6_666_667)
            book.fill(quote(SOL, 2, 6_666_667, observed=102), now=102)
            self.assertEqual(book.state()["cost_usdc"], 0)
            self.assertEqual(book.state()["realized_pnl_usdc"], 0)
        finally:
            book.close()

    def test_quote_mode_and_fee_asset_must_fit_the_paper_premise(self):
        valid = quote()
        original = json.loads(valid.payload_json)
        for change in (dict(swapMode="ExactOut"), dict(feeMint="So1anaFakeMint111111111111111111111111111111")):
            with self.subTest(change=change), self.assertRaises(Rejected):
                Quote.parse(valid.request, dict(original, **change), 99.75, 100)
        for fee_mint in (USDC.mint, SOL.mint):
            Quote.parse(valid.request, dict(original, feeMint=fee_mint, swapMode="ExactIn"), 99.75, 100)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(Rejected):
            strict_json('{"outAmount": "1", "outAmount": "999"}')


class Transport(unittest.TestCase):
    URL = "https://api.jup.ag/swap/v2/order?inputMint=a&outputMint=b&amount=1"

    def opener_returning(self, body=None, read_error=None):
        class Response(io.BytesIO):
            status = 200

            def read(self, *args):
                if read_error:
                    raise read_error
                return super().read(*args)

        class Opener:
            def open(self, request, timeout):
                return Response(body or b"{}")

        return patch("urllib.request.build_opener", return_value=Opener())

    def test_errors_while_reading_become_rejections(self):
        for error in (http.client.IncompleteRead(b"partial"), ConnectionResetError("reset"),
                      TimeoutError("slow")):
            with self.subTest(error=type(error).__name__), self.opener_returning(read_error=error):
                with self.assertRaises(Rejected):
                    public_get(self.URL)

    def test_duplicate_keys_and_bad_utf8_become_rejections(self):
        for body in (b'{"outAmount":"1","outAmount":"2"}', b"\xff\xfe", b"[NaN]"):
            with self.subTest(body=body), self.opener_returning(body=body):
                with self.assertRaises(Rejected):
                    public_get(self.URL)


class RunnerTiming(unittest.TestCase):
    def setUp(self):
        self.bars = synthetic_bars()[:60]
        self.as_of = self.bars[-1].end
        self.assertEqual(analyse(self.bars, [], self.as_of)["action"], "BUY")
        self.book = PaperBook(":memory:")

    def tearDown(self):
        self.book.close()

    def decisions(self):
        return [json.loads(row[0]) for row in self.book.db.execute("SELECT audit_json FROM decisions ORDER BY id")]

    def test_stale_decision_is_blocked_before_quote_and_journaled(self):
        week = 7 * 86400

        def provider(request):
            self.fail("A stale decision must not request a quote")

        with self.assertRaises(Rejected):
            step(self.bars, [], self.book, provider, self.as_of, lambda: self.as_of + week)
        self.assertEqual(self.book.state()["fills"], 0)
        self.assertEqual([d["event"] for d in self.decisions()], ["DECISION", "BLOCKED"])

    def test_slow_quote_that_ages_the_decision_is_blocked(self):
        clock = iter([self.as_of + 1, self.as_of + 61])

        def provider(request):
            return synthetic_quote(request, self.as_of + 59, self.as_of + 60)

        with self.assertRaises(Rejected):
            step(self.bars, [], self.book, provider, self.as_of, lambda: next(clock))
        self.assertEqual(self.book.state()["fills"], 0)

    def test_non_rejected_errors_are_journaled_and_never_fill(self):
        def provider(request):
            raise RuntimeError("upstream exploded")

        with self.assertRaises(RuntimeError):
            step(self.bars, [], self.book, provider, self.as_of, lambda: self.as_of + 1)
        self.assertEqual(self.book.state()["fills"], 0)
        blocked = self.decisions()[-1]
        self.assertEqual(blocked["event"], "BLOCKED")
        self.assertIn("RuntimeError", blocked["reason"])

    def test_provider_returning_non_quote_is_blocked(self):
        with self.assertRaises(Rejected):
            step(self.bars, [], self.book, lambda request: {"outAmount": "1"}, self.as_of,
                 lambda: self.as_of + 1)
        self.assertEqual(self.book.state()["fills"], 0)


class Concurrency(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "paper.db"
        # Zero fee: the cost cap alone no longer blocks a second 25 USDC buy.
        self.limits = Limits(network_fee_usdc=0, adverse_bps=0)
        PaperBook(self.path, limits=self.limits).close()
        self.bars = synthetic_bars()[:60]
        self.as_of = self.bars[-1].end

    def tearDown(self):
        self.directory.cleanup()

    def test_fill_rejects_when_account_changed_after_decision(self):
        book = PaperBook(self.path, limits=self.limits)
        try:
            seen = book.state()
            book.fill(quote(), now=100)
            with self.assertRaises(Rejected):
                book.fill(quote(observed=101), now=101, expect=seen)
            self.assertEqual(book.state()["fills"], 1)
        finally:
            book.close()

    def test_two_runners_cannot_open_two_positions(self):
        barrier, outcomes = threading.Barrier(2), []

        def worker(index):
            book = PaperBook(self.path, limits=self.limits)
            try:
                def provider(request):
                    barrier.wait(timeout=5)  # both decided on the same empty account
                    return synthetic_quote(request, self.as_of + 0.1, self.as_of + 0.2, str(1000 + index))

                try:
                    outcomes.append(step(self.bars, [], book, provider, self.as_of,
                                         lambda: self.as_of + 0.3)["execution"])
                except Rejected:
                    outcomes.append("BLOCKED")
            finally:
                book.close()

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(sorted(outcomes), ["BLOCKED", "PAPER_FILLED"])
        book = PaperBook(self.path, limits=self.limits)
        try:
            self.assertEqual(book.state()["fills"], 1)
        finally:
            book.close()

    def test_locked_database_reports_the_real_error(self):
        book = PaperBook(self.path, limits=self.limits)
        other = sqlite3.connect(self.path, isolation_level=None)
        try:
            book.db.execute("PRAGMA busy_timeout=50")
            other.execute("BEGIN IMMEDIATE")
            with self.assertRaises(sqlite3.OperationalError) as caught:
                book.fill(quote(), now=100)
            self.assertIn("locked", str(caught.exception))
            other.execute("ROLLBACK")
            self.assertEqual(book.state()["fills"], 0)
        finally:
            other.close()
            book.close()


class News(unittest.TestCase):
    def test_malformed_news_is_rejected_not_crashing(self):
        bars = synthetic_bars()[:60]
        now = bars[-1].end
        good = dict(title="t", url="https://example.com/a", published_at=now - 1, observed_at=now)
        for bad in ("text", dict(good, title=7), dict(good, title="  "), dict(good, url=None),
                    dict(good, url="http://example.com/a"), {k: v for k, v in good.items() if k != "observed_at"}):
            with self.subTest(bad=bad), self.assertRaises(Rejected):
                analyse(bars, [bad], now)


if __name__ == "__main__":
    unittest.main()
