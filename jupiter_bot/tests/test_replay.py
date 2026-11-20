"""Replay harness on synthetic journals only. No network (guard), no real journal.

Prices here are invented; nothing in this file says anything about markets.
"""
import hashlib
import io
import json
import random
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401
from jupiter_bot.core import SOL, USDC, Quote, QuoteRequest, Rejected
from jupiter_bot.marketdata.candles import BinanceKlines, Bar, CandleBatch
from jupiter_bot.marketdata.journal import Journal
from jupiter_bot.marketdata.quotes import JupiterQuoteSample
from jupiter_bot.marketdata.snapshot import build_snapshot
from jupiter_bot.marketdata.transport import RawResponse
from jupiter_bot.research import replay

T0 = 1794916800          # aligned to 60 s; invented calendar position
NOW = T0 + 30 * 86400    # test clock: the synthetic periods are long over
MINUTES = 120            # period [T0, T0 + MINUTES*60)
END = T0 + MINUTES * 60
BUY_REQUEST = QuoteRequest(USDC, SOL, 25_000_000)
SELL_REQUEST = QuoteRequest(SOL, USDC, 350_000_000)


def price(i):
    return 100 + (i % 17) - 8 + i / 50


def add_bars(journal, rows, seen_at):
    """rows: [(minute_index, close)] or [(minute_index, (o, h, l, c))]; one fetch, seen at `seen_at`."""
    bars = []
    for index, value in rows:
        start = T0 + index * 60
        if isinstance(value, tuple):
            o, h, l, c = value
        else:
            o, c = value - 0.05, value
            h, l = max(o, c) + 0.5, min(o, c) - 0.5
        bars.append(Bar(float(start), float(start + 60), *("%.4f" % x for x in (o, h, l, c)), "10"))
    batch = CandleBatch("SOL/USDC", 60, tuple(bars), 0, 0)
    journal.record(BinanceKlines(limit=10), "https://api.binance.com/api/v3/klines", seen_at, seen_at,
                   RawResponse(200, {}, b"[]"), "OK", batch=batch)


def add_quote(journal, side, observed_at, out_amount, fee_bps=2):
    request = BUY_REQUEST if side == "BUY" else SELL_REQUEST
    payload = dict(request.params(), inAmount=str(request.amount), outAmount=str(out_amount),
                   router="metis", feeBps=fee_bps, transaction=None)
    del payload["amount"]
    quote = Quote.parse(request, payload, observed_at - 0.5, observed_at)
    journal.record(JupiterQuoteSample(request), "https://api.jup.ag/swap/v2/order", observed_at - 0.5,
                   observed_at, RawResponse(200, {}, json.dumps(payload).encode()), "OK", batch=quote)
    return quote.quote_id


def buy_out(i):
    return int(25e9 / price(i))


def sell_out(i):
    return int(350_000 * price(i))


def build_standard(path, skip_buy=(), skip_sell=(), late=None, bars_from=-60, quotes_until=MINUTES + 10):
    """Bars every minute seen at end + 7; buy quote at :08, sell quote at :10 of each minute."""
    journal = Journal(path)
    try:
        for i in range(bars_from, MINUTES + 10):
            seen = T0 + (i + 1) * 60 + 7
            if late and i in late:
                continue
            add_bars(journal, [(i, price(i))], seen)
        for i, seen in (late or {}).items():
            add_bars(journal, [(i, price(i))], seen)
        for i in range(-10, quotes_until):
            if i not in skip_buy:
                add_quote(journal, "BUY", T0 + i * 60 + 8, buy_out(i))
            if i not in skip_sell:
                add_quote(journal, "SELL", T0 + i * 60 + 10, sell_out(i))
    finally:
        journal.close()


def scripted(snapshot, params):
    """LONG inside [long_from, long_until) minutes after T0, FLAT otherwise."""
    minute = (snapshot["as_of"] - T0) // 60
    return "LONG" if params["long_from"] <= minute < params["long_until"] else "FLAT"


def alternating(snapshot, params):
    minute = int((snapshot["as_of"] - T0) // 60)
    return "LONG" if (minute // params["every"]) % 2 else "FLAT"


SEEN = []


def recorder(snapshot, params):
    SEEN.append((snapshot["as_of"], snapshot["candles"][-1]["start"], len(snapshot["candles"])))
    return "FLAT"


def picky(snapshot, params):
    if len(snapshot["candles"]) < params["min_bars"]:
        raise Rejected("strategy warmup")
    return "LONG"


class ReplayCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = Path(cls.template_dir.name) / "template.db"
        build_standard(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "observations.db"
        shutil.copy(self.template, self.path)
        self.out = self.root / "evaluations"
        self.lock = self.root / "plan_lock.json"        # absent unless a test writes it

    def tearDown(self):
        self.directory.cleanup()

    def evaluate(self, fn, params, delays=(60,), costs=(0,), path=None, label="synthetic", **options):
        options.setdefault("controls", 0)
        options.setdefault("bars", 30)
        return replay.evaluate(path or self.path, fn.__name__, fn, params, T0, END, label, delays, costs,
                               out_dir=self.out, plan_lock=self.lock, clock=lambda: NOW, **options)

    def files(self):
        return sorted(self.out.glob("*.json")) if self.out.exists() else []


class PointInTime(ReplayCase):
    def test_bar_first_seen_after_decision_is_not_used(self):
        path = self.root / "late.db"
        build_standard(path, late={50: T0 + 51 * 60 + 200})   # bar 50 ends at 51*60, seen 200 s later
        SEEN.clear()
        self.evaluate(recorder, {}, path=path)
        by_time = {as_of: (last, n) for as_of, last, n in SEEN}
        decision = T0 + 51 * 60 + 30
        self.assertEqual(by_time[decision][0], T0 + 49 * 60)            # bar 50 not yet visible
        self.assertEqual(by_time[decision + 60][0], T0 + 51 * 60)       # 51 seen, 50 still missing -> cut
        self.assertEqual(by_time[decision + 60][1], 1)
        self.assertEqual(by_time[decision + 180][0], T0 + 53 * 60)      # after 50 was seen: contiguous
        self.assertEqual(by_time[decision + 180][1], 30)
        # the reference path (build_snapshot every minute) sees exactly the same
        fast_seen = list(SEEN)
        SEEN.clear()
        journal = Journal(path, readonly=True)
        try:
            replay.decide(journal, recorder, {}, T0, END, bars=30, fast=False)
        finally:
            journal.close()
        self.assertEqual(SEEN, fast_seen)

    def test_fast_snapshot_equals_build_snapshot_every_minute(self):
        path = self.root / "messy.db"
        journal = Journal(path)
        try:
            for i in range(-5, 100):
                if i in (20, 21, 40) or 60 <= i < 66:
                    continue
                add_bars(journal, [(i, price(i))], T0 + (i + 1) * 60 + 7)
            add_bars(journal, [(20, price(20)), (21, price(21))], T0 + 25 * 60)           # late fill of a gap
            add_bars(journal, [(10, price(10) + 1)], T0 + 30 * 60 + 3)                     # revision
            add_bars(journal, [(22, price(22) - 1)], T0 + 22 * 60)                          # revision before... seen
            add_bars(journal, [(10, price(10) + 2)], T0 + 50 * 60 + 3)                     # second revision
            add_bars(journal, [(i, price(i)) for i in range(60, 66)], T0 + 72 * 60)        # stale, then backfill
            add_bars(journal, [(100, (10, 9, 11, 10))], T0 + 101 * 60 + 7)                 # inconsistent OHLC
            add_bars(journal, [(101, price(101))], T0 + 102 * 60 + 7)
        finally:
            journal.close()
        journal = Journal(path, readonly=True)
        try:
            for bars in (7, 30, 200):
                fast = replay.PointInTimeCandles(journal, T0 + 110 * 60, bars=bars)
                for minute in range(-6, 110):
                    for offset in (0, 7, 30, 59):
                        t = T0 + minute * 60 + offset
                        self.assertSnapshotsEqual(journal, fast, t, bars)
                self.assertGreater(fast.fallbacks, 0)   # the invalid bar was handled by build_snapshot
        finally:
            journal.close()

    def assertSnapshotsEqual(self, journal, fast, t, bars):
        try:
            expected = build_snapshot(journal, t, bars=bars)
        except Rejected as exc:
            with self.assertRaises(Rejected) as caught:
                fast.snapshot(t)
            self.assertEqual(str(caught.exception), str(exc), t)
            return
        got = fast.snapshot(t)
        got = dict(got, candles=[dict(c) for c in got["candles"]])
        for snapshot in (expected, got):
            for key in ("fetches", "analyse_check", "fast_path"):
                snapshot["provenance"].pop(key, None)
        self.assertEqual(got, expected, t)

    def test_rejected_snapshot_is_wait_and_counted(self):
        path = self.root / "gap.db"
        journal = Journal(path)
        try:
            for i in range(-60, MINUTES + 10):
                if not 40 <= i < 50:
                    add_bars(journal, [(i, price(i))], T0 + (i + 1) * 60 + 7)
            for i in range(-10, MINUTES + 10):
                add_quote(journal, "BUY", T0 + i * 60 + 8, buy_out(i))
                add_quote(journal, "SELL", T0 + i * 60 + 10, sell_out(i))
        finally:
            journal.close()
        record = self.evaluate(scripted, {"long_from": 0, "long_until": 1000}, path=path)[0]
        # bars 40..49 missing: decisions at 42:30 .. 50:30 see a last bar >= 150 s old
        self.assertEqual(record["metrics"]["missing"], 9)
        self.assertTrue(any("Candle data is stale" in line for line in record["missing"]))

    def test_strategy_rejection_is_missing_not_a_trade(self):
        record = self.evaluate(picky, {"min_bars": 10_000})[0]
        self.assertEqual(record["metrics"]["missing"], record["metrics"]["decisions"])
        self.assertEqual(record["trades"], [])
        self.assertEqual(record["metrics"]["return_pct"], "0.000000")


class Pricing(ReplayCase):
    def test_delay_picks_the_first_quote_after_decision_plus_delay(self):
        fills = {}
        for delay in (60, 120, 300):
            trade = self.evaluate(scripted, {"long_from": 10, "long_until": 1000}, delays=(delay,))[0]["trades"][0]
            fills[delay] = trade
            self.assertEqual(trade["decided_at"], T0 + 10 * 60 + 30)
            self.assertGreaterEqual(trade["filled_at"], trade["decided_at"] + delay)
        # buy quotes at :08 of each minute
        self.assertEqual(fills[60]["filled_at"], T0 + 12 * 60 + 8)
        self.assertEqual(fills[120]["filled_at"], T0 + 13 * 60 + 8)
        self.assertEqual(fills[300]["filled_at"], T0 + 16 * 60 + 8)
        self.assertEqual(len({trade["quote_id"] for trade in fills.values()}), 3)

    def test_missing_quote_is_not_filled_and_position_unchanged(self):
        path = self.root / "noquote.db"
        build_standard(path, skip_buy=set(range(11, 15)))
        record = self.evaluate(scripted, {"long_from": 10, "long_until": 1000}, path=path)[0]
        first, second = record["trades"][:2]
        self.assertEqual(first["status"], "MISSING_QUOTE")
        self.assertIsNone(first["filled_at"])
        self.assertIsNone(first["out_amount"])
        # no new order until decision + delay + 120 s has passed
        self.assertEqual(second["decided_at"], T0 + 13 * 60 + 30)
        self.assertEqual(second["status"], "FILLED")
        self.assertEqual(second["filled_at"], T0 + 15 * 60 + 8)
        self.assertEqual(record["metrics"]["missing_quotes"], 1)
        self.assertEqual(record["metrics"]["missing_quote_pct"], "50.000000")
        self.assertEqual(record["metrics"]["exposure_pct"], replay.pct(MINUTES - 15, MINUTES))

    def test_quote_after_period_end_is_never_used(self):
        record = self.evaluate(scripted, {"long_from": MINUTES - 2, "long_until": 1000})[0]
        self.assertEqual([t["status"] for t in record["trades"]], ["MISSING_QUOTE"])
        self.assertTrue(all(t["filled_at"] is None or t["filled_at"] < END for t in record["trades"]))

    def test_fee_bps_not_double_counted_and_costs_exact(self):
        path = self.root / "fee.db"
        journal = Journal(path)
        try:
            for i in range(-60, MINUTES + 10):
                add_bars(journal, [(i, price(i))], T0 + (i + 1) * 60 + 7)
            for i in range(-10, MINUTES + 10):
                add_quote(journal, "BUY", T0 + i * 60 + 8, 240_000_000, fee_bps=500)
                add_quote(journal, "SELL", T0 + i * 60 + 10, 36_000_000, fee_bps=500)
        finally:
            journal.close()
        for cost in (0, 25):
            keep = 10000 - cost
            record = self.evaluate(scripted, {"long_from": 10, "long_until": 50}, costs=(cost,), path=path)[0]
            buy, sell = record["trades"]
            self.assertEqual(buy["in_amount"], 25_000_000)                         # exactly the quoted size
            self.assertEqual(buy["out_amount"], 240_000_000 * keep // 10000)       # outAmount as-is, no feeBps cut
            sol = buy["out_amount"]
            usdc = 36_000_000 * sol // 350_000_000 * keep // 10000 - 10_000       # linear scaling, then costs
            self.assertEqual(sell["in_amount"], sol)
            self.assertEqual(sell["out_amount"], usdc)
            self.assertEqual(record["metrics"]["final_usdc_dec"], replay.usdc_dec(usdc))
            self.assertEqual(record["metrics"]["return_pct"], replay.pct(usdc - 25_010_000, 25_010_000))
            self.assertEqual(record["metrics"]["round_trips"], 1)
            hold = 36_000_000 * (240_000_000 * keep // 10000) // 350_000_000 * keep // 10000 - 10_000
            self.assertEqual(record["benchmarks"]["hold_sol_return_pct"],
                             replay.pct(hold - 25_010_000, 25_010_000))
            self.assertEqual(record["benchmarks"]["cash_return_pct"], "0")

    def test_open_position_valued_at_last_sell_quote_before_end(self):
        record = self.evaluate(scripted, {"long_from": 5, "long_until": 1000})[0]
        self.assertTrue(record["metrics"]["open_position_at_end"])
        sol = record["trades"][0]["out_amount"]
        last = MINUTES - 1
        expected = sell_out(last) * sol // 350_000_000 - 10_000
        self.assertEqual(record["metrics"]["final_usdc_dec"], replay.usdc_dec(expected))
        self.assertEqual(record["benchmarks"]["valuation_observed_at"], T0 + last * 60 + 10)
        self.assertEqual(record["equity"][-1], [END, round(expected / 1e6, 6)])

    def test_jump_simulation_equals_minute_loop(self):
        path = self.root / "holes.db"
        rng = random.Random(7)
        build_standard(path, skip_buy={i for i in range(MINUTES) if rng.random() < 0.3},
                       skip_sell={i for i in range(MINUTES) if rng.random() < 0.3})
        journal = Journal(path, readonly=True)
        try:
            book = replay.QuoteBook(journal, T0, END)
            times = replay.decision_times(T0, END, replay.DECISION_OFFSET_S)
            for trial in range(30):
                targets = [rng.choice(["LONG", "FLAT", None]) for _ in times]
                decisions = replay.Decisions(times, targets, {}, {}, 30)
                for delay in (0, 60, 300):
                    cell = replay.Cell(decisions, book, END, delay, 25)
                    got = replay.simulate(cell, decisions.longs, decisions.flats)
                    self.assertEqual(got[:2], naive(book, times, targets, delay, 25), (trial, delay))
        finally:
            journal.close()


def naive(book, times, targets, delay, cost):
    """Reference: minute-by-minute loop straight from the documented rules."""
    keep, cash, sol, pending = 10000 - cost, replay.INITIAL_USDC, 0, None
    for t, target in zip(times, targets):
        if pending is not None and pending[0] <= t:
            if pending[1] is not None:
                cash, sol = pending[1]
            pending = None
        if target is None or pending is not None or (target == "LONG") == (sol > 0):
            continue
        side = "BUY" if target == "LONG" else "SELL"
        quote = next((q for q in book.quotes[side]
                      if t + delay <= q["observed_at"] <= t + delay + 120 and q["observed_at"] < END), None)
        if quote is None:
            pending = (t + delay + 120, None)
        elif side == "BUY":
            got = quote["out_amount"] * (cash - 10_000) // quote["in_amount"] * keep // 10000
            if cash <= 10_000 or got <= 0:
                break                                   # ruin: no further trade
            pending = (quote["observed_at"], (0, got))
        else:
            got = max(0, quote["out_amount"] * sol // quote["in_amount"] * keep // 10000 - 10_000)
            pending = (quote["observed_at"], (cash + got, 0))
    if pending is not None and pending[1] is not None:
        cash, sol = pending[1]
    return cash, sol


class Ruin(ReplayCase):
    def test_churn_to_dust_stops_trading_instead_of_failing(self):
        path = self.root / "dust.db"
        journal = Journal(path)
        try:
            for i in range(-60, MINUTES + 10):
                add_bars(journal, [(i, price(i))], T0 + (i + 1) * 60 + 7)
            for i in range(-10, MINUTES + 10):
                add_quote(journal, "BUY", T0 + i * 60 + 8, 250_000_000)
                add_quote(journal, "SELL", T0 + i * 60 + 10, 1_000)     # selling returns almost nothing
        finally:
            journal.close()
        record = self.evaluate(alternating, {"every": 2}, path=path, controls=3)[0]
        self.assertEqual(record["status"], "OK")
        self.assertEqual([t["side"] for t in record["trades"]], ["BUY", "SELL"])
        self.assertEqual(record["trades"][1]["out_amount"], 0)
        self.assertEqual(record["metrics"]["final_usdc_dec"], "0.000000")
        self.assertEqual(record["metrics"]["return_pct"], "-100.000000")


class Controls(ReplayCase):
    def test_controls_deterministic_with_seed(self):
        params = {"every": 15}
        one = self.evaluate(alternating, params, controls=50, seed=11)[0]
        two = self.evaluate(alternating, params, controls=50, seed=11)[0]
        three = self.evaluate(alternating, params, controls=50, seed=12)[0]
        self.assertEqual(one["controls"], two["controls"])
        self.assertEqual(one["seed"], 11)
        self.assertEqual(one["controls"]["random_entries"]["seed"], "11/random_entries")
        self.assertEqual(one["controls"]["random_entries"]["runs"], 50)
        self.assertEqual(one["controls"]["shuffled_signals"]["runs"], 50)
        for kind in ("random_entries", "shuffled_signals"):
            share = float(one["controls"][kind]["share_beating_strategy"])
            self.assertTrue(0 <= share <= 1)
        journal = Journal(self.path, readonly=True)
        try:
            decisions = replay.decide(journal, alternating, params, T0, END, bars=30)
        finally:
            journal.close()
        first = [(k, l) for k, l, _ in replay.control_sequences(decisions, 20, 11)]
        again = [(k, l) for k, l, _ in replay.control_sequences(decisions, 20, 11)]
        other = [(k, l) for k, l, _ in replay.control_sequences(decisions, 20, 12)]
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertNotEqual(three["controls"], one["controls"])

    def test_control_sequences_keep_change_count_and_targets(self):
        journal = Journal(self.path, readonly=True)
        try:
            decisions = replay.decide(journal, alternating, {"every": 15}, T0, END, bars=30)
        finally:
            journal.close()
        for kind, longs, flats in replay.control_sequences(decisions, 25, 3):
            self.assertEqual(sorted(longs + flats), decisions.valid)
            if kind == "shuffled_signals":
                self.assertEqual(len(longs), len(decisions.longs))
            else:
                targets = {i: "LONG" for i in longs}
                state, changes = "FLAT", 0
                for i in decisions.valid:
                    if targets.get(i, "FLAT") != state:
                        state, changes = targets.get(i, "FLAT"), changes + 1
                self.assertEqual(changes, decisions.changes)


class Guards(ReplayCase):
    def write_lock(self, holdout, code=None):
        hashes = code or replay.code_hashes(scripted)
        self.lock.write_text(json.dumps(dict(
            plan_path="jupiter_bot/research/P2_PLAN.md", plan_sha256="ab" * 32, code_sha256=hashes,
            git_commit="0" * 40, locked_at=float(T0 - 86400), approved_by="test",
            development=dict(start=float(T0 - 86400), end=float(T0)),
            holdout=dict(start=float(holdout[0]), end=float(holdout[1])))))

    def test_holdout_refused_without_lock(self):
        with self.assertRaisesRegex(Rejected, "no plan_lock.json"):
            self.evaluate(scripted, {"long_from": 0, "long_until": 9}, label="holdout")
        self.assertEqual(self.files(), [])

    def test_holdout_refused_for_other_window_or_changed_code(self):
        self.write_lock((T0, END + 60))
        with self.assertRaisesRegex(Rejected, "not the locked holdout window"):
            self.evaluate(scripted, {"long_from": 0, "long_until": 9}, label="holdout")
        self.write_lock((T0, END), code={"jupiter_bot/research/replay.py": "0" * 64})
        with self.assertRaisesRegex(Rejected, "differs from the locked code"):
            self.evaluate(scripted, {"long_from": 0, "long_until": 9}, label="holdout")
        self.assertEqual(self.files(), [])

    def test_holdout_runs_only_on_the_locked_window(self):
        self.write_lock((T0, END))
        record = self.evaluate(scripted, {"long_from": 0, "long_until": 9}, label="holdout")[0]
        self.assertEqual(record["label"], "holdout")
        self.assertEqual(record["plan_sha256"], "ab" * 32)
        self.assertEqual(record["plan_lock_sha256"], hashlib.sha256(self.lock.read_bytes()).hexdigest())

    def test_development_may_not_overlap_the_locked_holdout(self):
        self.write_lock((END - 600, END + 86400))
        with self.assertRaisesRegex(Rejected, "overlaps the locked holdout"):
            self.evaluate(scripted, {"long_from": 0, "long_until": 9}, label="development")

    def test_unfinished_period_refused(self):
        with self.assertRaisesRegex(Rejected, "has not ended"):
            replay.evaluate(self.path, "scripted", scripted, {}, T0, END, "synthetic", (60,), (0,),
                            out_dir=self.out, plan_lock=self.lock, clock=lambda: END - 1)

    def test_journal_opened_read_only_and_hashed(self):
        before = self.path.read_bytes()
        with patch("jupiter_bot.research.replay.Journal", wraps=Journal) as opened:
            record = self.evaluate(scripted, {"long_from": 3, "long_until": 9})[0]
        self.assertEqual(opened.call_args.kwargs, {"readonly": True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(record["journal_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(set(record["code_sha256"]), {"jupiter_bot/research/replay.py",
                                                     "jupiter_bot/tests/test_replay.py"})


class Output(ReplayCase):
    def test_every_run_writes_a_new_file_and_never_overwrites(self):
        tokens = iter(["deadbeef", "deadbeef", "cafebabe"])
        with patch("jupiter_bot.research.replay.secrets.token_hex", lambda n: next(tokens)):
            first = self.evaluate(scripted, {"long_from": 3, "long_until": 9})[0]
            original = Path(first["path"]).read_bytes()
            second = self.evaluate(scripted, {"long_from": 4, "long_until": 9})[0]
        self.assertTrue(first["run_id"].endswith("-deadbeef"))
        self.assertTrue(second["run_id"].endswith("-cafebabe"))
        self.assertEqual(Path(first["path"]).read_bytes(), original)
        self.assertEqual(len(self.files()), 2)
        self.assertEqual([p.name for p in self.out.iterdir() if p.name.startswith(".")], [])

    def test_record_shape(self):
        record = self.evaluate(alternating, {"every": 20}, controls=5)[0]
        stored = json.loads(Path(record["path"]).read_text())
        for key in ("run_id", "created_at", "kind", "label", "plan_sha256", "code_sha256", "journal_sha256",
                    "period", "strategy", "params", "delay_s", "extra_cost_bps", "trades", "equity",
                    "metrics", "benchmarks", "controls", "assumptions", "missing", "verdict", "bars"):
            self.assertIn(key, stored)
        for key in ("final_usdc_dec", "return_pct", "max_drawdown_pct", "trades", "missing", "exposure_pct",
                    "round_trips", "missing_quote_pct", "candle_coverage_pct", "quote_coverage_buy_pct",
                    "quote_coverage_sell_pct"):
            self.assertIn(key, stored["metrics"])
        self.assertIsNone(stored["verdict"])
        self.assertTrue(any("LINEAR SCALING" in line for line in stored["assumptions"]))
        self.assertEqual(stored["metrics"]["candle_coverage_pct"], "100.000000")
        self.assertEqual(stored["metrics"]["quote_coverage_buy_pct"], "100.000000")

    def test_coverage_metrics(self):
        path = self.root / "cov.db"
        build_standard(path, skip_buy=set(range(0, 12)), late={30: T0 + 31 * 60 + 45, 31: T0 + 32 * 60 + 29})
        record = self.evaluate(scripted, {"long_from": 50, "long_until": 60}, path=path)[0]
        self.assertEqual(record["metrics"]["quote_coverage_buy_pct"], replay.pct(MINUTES - 12, MINUTES))
        self.assertEqual(record["metrics"]["quote_coverage_sell_pct"], "100.000000")
        self.assertEqual(record["metrics"]["candle_coverage_pct"], replay.pct(MINUTES - 1, MINUTES))

    def test_unvaluable_run_still_writes_a_rejected_file(self):
        path = self.root / "short.db"
        build_standard(path, quotes_until=MINUTES - 10)
        with self.assertRaisesRegex(Rejected, "No sell quote"):
            self.evaluate(scripted, {"long_from": 3, "long_until": 9}, path=path, costs=(0, 25))
        records = [json.loads(p.read_text()) for p in self.files()]
        self.assertEqual(len(records), 2)
        self.assertEqual({r["status"] for r in records}, {"REJECTED"})

    def test_sensitivity_decides_once_and_writes_every_cell(self):
        calls = []

        def counting(snapshot, params):
            calls.append(snapshot["as_of"])
            return alternating(snapshot, params)

        records = replay.sensitivity(self.path, "counting", counting, {"every": 10}, T0, END, "synthetic",
                                     delays=(60, 120, 300), costs=(0, 50), out_dir=self.out, plan_lock=self.lock,
                                     clock=lambda: NOW, controls=3, bars=30)
        self.assertEqual(len(calls), MINUTES)
        self.assertEqual(len(records), 6)
        self.assertEqual(len(self.files()), 6)
        self.assertEqual({(r["delay_s"], r["extra_cost_bps"]) for r in records},
                         {(d, c) for d in (60, 120, 300) for c in (0, 50)})
        self.assertEqual(len({r["decisions_sha256"] for r in records}), 1)
        returns = {r["extra_cost_bps"]: r["metrics"]["return_pct"] for r in records if r["delay_s"] == 60}
        self.assertLess(float(returns[50]), float(returns[0]))

    def test_cli_runs_every_grid_entry_and_rejects_off_grid_params(self):
        module = types.ModuleType("jupiter_bot.research.strategies")
        module.__file__ = __file__
        module.STRATEGIES = {"alt": (alternating, lambda params: 30, [{"every": 10}, {"every": 20}])}
        module.TRIAL_BUDGET = 2
        args = ["--journal", str(self.path), "--strategy", "alt", "--start", "2026-11-17T12:00:00Z",
                "--end", str(END), "--label", "synthetic", "--out", str(self.out), "--plan-lock", str(self.lock),
                "--delays", "60,120", "--costs", "0,25", "--controls", "2"]
        out = io.StringIO()
        with patch.dict(sys.modules, {"jupiter_bot.research.strategies": module}), redirect_stdout(out):
            code = replay.main(args)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(len(lines), 8)
        records = [json.loads(p.read_text()) for p in self.files()]
        self.assertEqual(len(records), 8)
        self.assertEqual({r["grid_index"] for r in records}, {0, 1})
        self.assertEqual({r["bars"] for r in records}, {30})
        self.assertEqual(len({r["batch"]["id"] for r in records}), 1)
        err = io.StringIO()
        with patch.dict(sys.modules, {"jupiter_bot.research.strategies": module}), redirect_stderr(err):
            code = replay.main(args[:-6] + ["--label", "development", "--params", '{"every": 7}'])
        self.assertEqual(code, 2)
        self.assertIn("not in the alt grid", err.getvalue())


if __name__ == "__main__":
    unittest.main()
