"""Replay a LONG/FLAT strategy over the observation journal, minute by minute.

Strategy interface
------------------
    strategy(snapshot: dict, params: dict) -> "LONG" | "FLAT"

`snapshot` is what `marketdata.snapshot.build_snapshot(journal, t, bars=...)`
returns at the decision time `t` (see `PointInTimeCandles` for the exact,
faster equivalent used by default). The return value is the TARGET position.
A strategy that raises `Rejected` is treated like an unusable snapshot.

Semantics (each one is tested in tests/test_replay.py)
------------------------------------------------------
- Decisions at every minute boundary in [start, end) plus `decision_offset_s`
  (default 30 s: the collector fetches at :07, so the bar that just closed
  is normally in the journal by :30). Only bars first seen by `t`, in the
  version known at `t`, are visible.
- Unusable snapshot (no bars, stale, invalid) or `Rejected` from the
  strategy: WAIT, position held, counted in `metrics.missing`.
- An order is placed when the target differs from the position and no order
  is in flight. It fills on the FIRST journaled Jupiter quote in its direction
  (by mints) with `t + delay_s <= observed_at <= t + delay_s + 120` and
  `observed_at < end`. Otherwise it is `MISSING_QUOTE`: not filled, position
  unchanged, and the next order can be placed from `t + delay_s + 120`.
  Decisions made while an order is in flight do not create orders.
- `outAmount` is already net of Jupiter's `feeBps`; it is not subtracted
  again. Per fill: `extra_cost_bps` adverse on the output, then the paper
  book's network fee (0.01 USDC).
- Account: 25.01 USDC = one 25 USDC buy quote + one network fee, so the first
  buy uses the quote's `outAmount` exactly. LONG is all-in: later buys spend
  all cash minus the fee and sells sell all SOL, both priced by scaling the
  fixed-size quote's rate linearly (an assumption; recorded in the output).
- Benchmarks: cash (0 %) and hold SOL (25 USDC bought on the first buy quote
  in the period, valued like an open position at the end).
- Open SOL is valued as a sale on the last sell quote observed in the 300 s
  before the time of valuation, with the same costs. No such quote at `end`
  rejects the evaluation (a REJECTED file is still written).
- Negative controls with the same pricing: random entries (same number of
  target changes, random times) and shuffled signals (the strategy's own
  targets permuted over its usable minutes). Seeds are in the output.

Every evaluation writes `<out>/<run_id>.json` (INTERFACES.md), created
exclusively and never rewritten, also when the result is bad or rejected.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import datetime
import hashlib
import importlib
import inspect
import json
import os
import random
import secrets
import sys
import time
import types
from collections import Counter
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

from ..core import SOL, USDC, Candle, Rejected, canonical, positive_integer, strict_json, timestamp
from ..marketdata.journal import Journal
from ..marketdata.snapshot import DEFAULT_BARS, build_snapshot
from ..paper import Limits

LONG, FLAT = "LONG", "FLAT"
BUY, SELL = "BUY", "SELL"
LABELS = ("development", "holdout", "synthetic", "forward")   # forward: dashboard view after the lock

DATA_DIR = Path("~/.local/share/jupiter-bot").expanduser()
DEFAULT_OUT = DATA_DIR / "research" / "evaluations"
DEFAULT_PLAN_LOCK = DATA_DIR / "research" / "plan_lock.json"

DECISION_OFFSET_S = 30.0
MAX_QUOTE_WAIT_S = 120.0      # after decision + delay
MARK_WINDOW_S = 300.0         # a sell quote older than this does not value a position
NETWORK_FEE_USDC = Limits().network_fee_usdc          # 0.01 USDC, as the paper book
QUOTE_BUY_USDC = 25_000_000                            # collector's fixed sizes
QUOTE_SELL_SOL = 350_000_000
INITIAL_USDC = QUOTE_BUY_USDC + NETWORK_FEE_USDC        # 25.01 USDC
DEFAULT_CONTROLS = 400
DEFAULT_SEED = 20261120
DEFAULT_DELAYS = (60, 120, 300)
DEFAULT_COSTS = (0, 10, 25, 50)

REPO = Path(__file__).resolve().parents[2]
PCT = Decimal("0.000001")
SHARE = Decimal("0.0001")
USDC_Q = Decimal("0.000001")


# Point-in-time candles, fast and exact ------------------------------------

class PointInTimeCandles:
    """`build_snapshot` for increasing `as_of`, without re-querying every minute.

    Loads the series once (bars visible by `until`, revisions seen by
    `until`) and replays visibility events in time order, so `snapshot(t)`
    sees exactly the rows `Journal.bars_as_of(t)` would return: bars with
    `first_seen_at <= t` and `end <= t`, each in its latest revision with
    `seen_at <= t`, the latest `bars` of them, cut at the last gap.

    Equal to `build_snapshot` except two provenance fields: `fetches` and
    `analyse_check` are omitted (`fast_path: true` instead). Its validation
    (gap, stale, invalid bars) is reproduced: windows containing a bar that
    is invalid or off the interval width, or any request with news sources,
    fall back to the real `build_snapshot`. The tests compare both on every
    minute of synthetic journals with late bars, gaps and revisions.
    """

    def __init__(self, journal, until, candle_source="binance_spot_klines", instrument="SOL/USDC",
                 interval_s=60, bars=DEFAULT_BARS, news_sources=()):
        if instrument != "SOL/USDC":
            raise Rejected("Only SOL/USDC snapshots are supported")
        if type(bars) is not int or bars < 1:
            raise Rejected("bars must be a positive integer")
        self.journal, self.until = journal, timestamp(until)
        self.source, self.instrument, self.interval_s, self.count = candle_source, instrument, interval_s, bars
        self.news_sources = tuple(news_sources)
        key = (candle_source, instrument, interval_s)
        self.original = {}
        events = []
        for row in journal.db.execute(
                """SELECT c.*, f.body_sha256 FROM candles c JOIN fetches f ON f.id = c.fetch_id
                   WHERE c.source=? AND c.instrument=? AND c.interval_s=? AND c.first_seen_at<=? AND c.end<=?""",
                key + (self.until, self.until)):
            row = dict(row)
            self.original[row["start"]] = row
            events.append((max(row["first_seen_at"], row["end"]), row["start"]))
        events.sort()
        self.bar_events = events
        self.revision_events = [dict(row) for row in journal.db.execute(
            """SELECT r.*, f.body_sha256 FROM candle_revisions r JOIN fetches f ON f.id = r.fetch_id
               WHERE r.source=? AND r.instrument=? AND r.interval_s=? AND r.seen_at<=?
               ORDER BY r.seen_at, r.id""", key + (self.until,))]
        self.next_bar = self.next_revision = 0
        self.revision = {}            # start -> latest applied revision row
        self.starts, self.rows = [], []
        self.flags = {}               # start -> (revised, anomalous) of the current version
        self.revised, self.anomalous = [], []    # sorted visible starts
        self.run_start = 0
        self.as_of = None
        self.fallbacks = 0

    def _version(self, start):
        base = self.original[start]
        revision = self.revision.get(start)
        source = revision if revision is not None else base
        observed = revision["seen_at"] if revision is not None else base["first_seen_at"]
        candle = dict(start=base["start"], end=base["end"], observed_at=observed,
                      **{k: source[k] for k in ("open", "high", "low", "close", "volume")})
        anomalous = base["end"] - base["start"] != self.interval_s
        if not anomalous:
            try:
                Candle.parse(candle).validate(observed)
            except Rejected:
                anomalous = True
        return types.MappingProxyType(candle), (revision is not None, anomalous)

    def _set_flags(self, start, flags):
        old = self.flags.get(start, (False, False))
        for flag, store, was in ((flags[0], self.revised, old[0]), (flags[1], self.anomalous, old[1])):
            if was and not flag:
                store.pop(bisect.bisect_left(store, start))
            elif flag and not was:
                bisect.insort(store, start)
        self.flags[start] = flags

    def _show(self, start):
        proxy, flags = self._version(start)
        index = bisect.bisect_left(self.starts, start)
        if index < len(self.starts) and self.starts[index] == start:
            raise Rejected("Duplicate bar start in candle series")
        self.starts.insert(index, start)
        self.rows.insert(index, proxy)
        self._set_flags(start, flags)
        if index == len(self.starts) - 1:
            if index == 0 or self.rows[index - 1]["end"] != start:
                self.run_start = index
        else:
            i = len(self.rows) - 1
            while i > 0 and self.rows[i]["start"] == self.rows[i - 1]["end"]:
                i -= 1
            self.run_start = i

    def _revise(self, revision):
        start = revision["start"]
        self.revision[start] = revision
        if start not in self.original:
            return
        index = bisect.bisect_left(self.starts, start)
        if index < len(self.starts) and self.starts[index] == start:
            proxy, flags = self._version(start)
            self.rows[index] = proxy
            self._set_flags(start, flags)

    def _advance(self, as_of):
        if self.as_of is not None and as_of < self.as_of:
            raise Rejected("PointInTimeCandles needs non-decreasing as_of")
        if as_of > self.until:
            raise Rejected("as_of after the loaded period")
        self.as_of = as_of
        # Revisions first: a bar becoming visible takes its version known at as_of.
        while self.next_revision < len(self.revision_events) and \
                self.revision_events[self.next_revision]["seen_at"] <= as_of:
            self._revise(self.revision_events[self.next_revision])
            self.next_revision += 1
        while self.next_bar < len(self.bar_events) and self.bar_events[self.next_bar][0] <= as_of:
            self._show(self.bar_events[self.next_bar][1])
            self.next_bar += 1

    def snapshot(self, as_of):
        as_of = timestamp(as_of)
        self._advance(as_of)
        if self.news_sources:
            self.fallbacks += 1
            return self._slow(as_of)
        n = len(self.rows)
        if n == 0:
            raise Rejected("No observed closed bars at as_of")
        first, cut = max(0, n - self.count), None
        if self.run_start > first:
            first = self.run_start
            cut = dict(missing_after=self.rows[first - 1]["end"], resumes_at=self.rows[first]["start"])
        low, high = self.starts[first], self.starts[-1]
        if bisect.bisect_right(self.anomalous, high) > bisect.bisect_left(self.anomalous, low):
            self.fallbacks += 1
            return self._slow(as_of)
        last = self.rows[-1]
        if as_of - last["end"] > 2 * (last["end"] - last["start"]):
            raise Rejected("Candle data is stale")
        candles = self.rows[first:]
        revised = bisect.bisect_right(self.revised, high) - bisect.bisect_left(self.revised, low)
        return dict(market=self.instrument, source="RECORDED", as_of=as_of, candles=candles, news=[],
                    provenance=dict(
                        candle_source=self.source, interval_s=self.interval_s,
                        bars_requested=self.count, bars_used=len(candles), cut_at_gap=cut,
                        revised_bars=revised, news_sources=[], news_excluded={},
                        note="Observations only; no profit claim, no live execution", fast_path=True))

    def _slow(self, as_of):
        return build_snapshot(self.journal, as_of, candle_source=self.source, instrument=self.instrument,
                              interval_s=self.interval_s, bars=self.count, news_sources=self.news_sources)


# Quotes ----------------------------------------------------------------------

class QuoteBook:
    """Journaled Jupiter quotes in [start - MARK_WINDOW_S, end), by direction."""

    def __init__(self, journal, start, end):
        self.quotes = {BUY: [], SELL: []}
        mints = {(USDC.mint, SOL.mint): BUY, (SOL.mint, USDC.mint): SELL}
        for row in journal.db.execute(
                """SELECT quote_id, input_mint, output_mint, in_amount, out_amount, router, fee_bps,
                          started_at, observed_at FROM quotes
                   WHERE observed_at>=? AND observed_at<? ORDER BY observed_at, quote_id""",
                (start - MARK_WINDOW_S, end)):
            side = mints.get((row["input_mint"], row["output_mint"]))
            if side is None:
                continue
            quote = dict(row)
            positive_integer(quote["in_amount"])
            positive_integer(quote["out_amount"])
            self.quotes[side].append(quote)
        self.times = {side: [q["observed_at"] for q in quotes] for side, quotes in self.quotes.items()}

    def first_at_or_after(self, side, at):
        index = bisect.bisect_left(self.times[side], at)
        return index if index < len(self.times[side]) else None

    def last_in(self, side, low, high):
        """Index of the last quote with low <= observed_at <= high, or None."""
        index = bisect.bisect_right(self.times[side], high) - 1
        return index if index >= 0 and self.times[side][index] >= low else None


def sell_value(quote, sol, keep):
    """USDC from selling `sol` atoms on `quote`'s rate, linear, after costs (may be <= 0)."""
    return quote["out_amount"] * sol // quote["in_amount"] * keep // 10000 - NETWORK_FEE_USDC


def buy_amount(quote, cash, keep):
    spend = cash - NETWORK_FEE_USDC
    if spend <= 0:
        raise Rejected("Cash does not cover the assumed network fee")
    got = quote["out_amount"] * spend // quote["in_amount"] * keep // 10000
    if got <= 0:
        raise Rejected("No SOL after costs")
    return spend, got


# Decisions -------------------------------------------------------------------

def decision_times(start, end, offset):
    first = -(-start // 60) * 60
    times, boundary = [], first
    while boundary < end:
        if boundary + offset < end:
            times.append(float(boundary + offset))
        boundary += 60
    return times


class Decisions:
    def __init__(self, times, targets, reasons, coverage, bars):
        self.times, self.targets, self.reasons, self.coverage, self.bars = times, targets, reasons, coverage, bars
        self.valid = [i for i, target in enumerate(targets) if target is not None]
        self.longs = [i for i in self.valid if targets[i] == LONG]
        self.flats = [i for i in self.valid if targets[i] == FLAT]
        previous, changes = FLAT, 0
        for i in self.valid:
            if targets[i] != previous:
                changes, previous = changes + 1, targets[i]
        self.changes = changes

    def digest(self):
        return hashlib.sha256(canonical([self.times, self.targets]).encode()).hexdigest()


def decide(journal, strategy_fn, params, start, end, bars=DEFAULT_BARS, decision_offset_s=DECISION_OFFSET_S,
           candle_source="binance_spot_klines", news_sources=(), fast=True):
    times = decision_times(start, end, decision_offset_s)
    if not times:
        raise Rejected("Period holds no decision time")
    candles = PointInTimeCandles(journal, end, candle_source, bars=bars, news_sources=news_sources) if fast else None
    targets, reasons = [], Counter()
    for t in times:
        try:
            snapshot = candles.snapshot(t) if fast else build_snapshot(
                journal, t, candle_source=candle_source, bars=bars, news_sources=news_sources)
        except Rejected as exc:
            targets.append(None)
            reasons["snapshot: %s" % exc] += 1
            continue
        try:
            target = strategy_fn(snapshot, copy.deepcopy(params))
        except Rejected as exc:
            targets.append(None)
            reasons["strategy: %s" % exc] += 1
            continue
        if not isinstance(target, str) or target not in (LONG, FLAT):
            raise Rejected("Strategy returned %r; expected LONG or FLAT" % (target,))
        targets.append(target)
    return Decisions(times, targets, reasons, candle_coverage(journal, candle_source, start, end,
                                                              decision_offset_s), bars)


def period_minutes(start, end):
    first = -(-start // 60) * 60
    return [float(m) for m in range(int(first), int(-(-end // 1)), 60) if m < end]


def candle_coverage(journal, candle_source, start, end, offset, interval_s=60):
    """Minutes in the period whose bar was first seen by bar end + offset."""
    minutes = period_minutes(start, end)
    on_time = {row[0] for row in journal.db.execute(
        """SELECT start FROM candles WHERE source=? AND instrument='SOL/USDC' AND interval_s=?
           AND start>=? AND start<? AND first_seen_at <= start + ? + ?""",
        (candle_source, interval_s, start, end, interval_s, offset))}
    return dict(minutes=len(minutes), candle_minutes=sum(1 for m in minutes if m in on_time))


def quote_coverage(book, start, end):
    minutes = period_minutes(start, end)
    first = minutes[0] if minutes else start
    result = {}
    for side in (BUY, SELL):
        seen = {int((t - first) // 60) for t in book.times[side] if first <= t < end}
        result[side] = sum(1 for index in range(len(minutes)) if index in seen)
    return result


# Simulation ------------------------------------------------------------------

class Cell:
    """Fill lookups for one (delay, cost), shared by the strategy and its controls."""

    def __init__(self, decisions, book, end, delay_s, extra_cost_bps):
        self.decisions, self.book, self.end = decisions, book, end
        self.delay_s, self.extra_cost_bps, self.keep = delay_s, extra_cost_bps, 10000 - extra_cost_bps
        times = decisions.times
        self.fill, self.resume = {}, {}
        for side in (BUY, SELL):
            fills, resumes = [], []
            quote_times = book.times[side]
            for t in times:
                target = t + delay_s
                deadline = target + MAX_QUOTE_WAIT_S
                index = bisect.bisect_left(quote_times, target)
                if index < len(quote_times) and quote_times[index] <= deadline:
                    fills.append(index)
                    resumes.append(bisect.bisect_left(times, quote_times[index]))
                else:
                    fills.append(-1)
                    resumes.append(bisect.bisect_left(times, deadline))
            self.fill[side], self.resume[side] = fills, resumes


def simulate(cell, longs, flats, trades=None):
    """Replay target indices; returns (cash, sol, fills, orders, missing).

    `longs`/`flats` are the sorted decision indices with that target. Only
    the minutes where the target differs from the position matter, so the
    loop jumps between them (equal to a minute-by-minute loop; tested).
    """
    times, quotes = cell.decisions.times, cell.book.quotes
    cash, sol, i, orders, missing, fills = INITIAL_USDC, 0, 0, 0, 0, []
    n = len(times)
    while i < n:
        wanted, side = (longs, BUY) if sol == 0 else (flats, SELL)
        k = bisect.bisect_left(wanted, i)
        if k == len(wanted):
            break
        j = wanted[k]
        orders += 1
        index = cell.fill[side][j]
        if index < 0:
            missing += 1
            if trades is not None:
                trades.append(dict(decided_at=times[j], target_at=times[j] + cell.delay_s, filled_at=None,
                                   side=side, quote_id=None, in_amount=None, out_amount=None,
                                   status="MISSING_QUOTE"))
        else:
            quote = quotes[side][index]
            if side == BUY:
                try:
                    spent, got = buy_amount(quote, cash, cell.keep)
                except Rejected:
                    break           # ruined: cash cannot pay the fee or buys nothing; no further trade
                cash, sol, paid = 0, got, spent
            else:
                got = max(0, sell_value(quote, sol, cell.keep))   # worth less than the fee: nothing back
                paid, cash, sol = sol, cash + got, 0
            fills.append((quote["observed_at"], side, cash, sol))
            if trades is not None:
                trades.append(dict(decided_at=times[j], target_at=times[j] + cell.delay_s,
                                   filled_at=quote["observed_at"], side=side, quote_id=quote["quote_id"],
                                   in_amount=paid, out_amount=got, status="FILLED",
                                   quote_in_amount=quote["in_amount"], quote_out_amount=quote["out_amount"],
                                   quote_fee_bps=quote["fee_bps"], router=quote["router"],
                                   extra_cost_bps=cell.extra_cost_bps, network_fee_usdc=NETWORK_FEE_USDC))
        i = cell.resume[side][j]
    return cash, sol, fills, orders, missing


def final_value(cell, valuation, cash, sol):
    if sol == 0:
        return cash
    return cash + max(0, sell_value(valuation, sol, cell.keep))


def pct(numerator, denominator):
    if not denominator:
        return "0"
    return str((Decimal(numerator) * 100 / Decimal(denominator)).quantize(PCT, ROUND_HALF_EVEN))


def return_pct(value):
    return pct(value - INITIAL_USDC, INITIAL_USDC)


def usdc_dec(value):
    return str((Decimal(value) / Decimal(10 ** 6)).quantize(USDC_Q))


def nearest_rank(sorted_values, p):
    index = max(0, -(-len(sorted_values) * p // 100) - 1)
    return sorted_values[index]


def equity_and_exposure(cell, fills, final):
    times, book = cell.decisions.times, cell.book
    equity, long_slots, pointer = [], 0, 0
    cash, sol = INITIAL_USDC, 0
    for t in times:
        while pointer < len(fills) and fills[pointer][0] <= t:
            _, _, cash, sol = fills[pointer]
            pointer += 1
        if sol == 0:
            equity.append((t, cash))
            continue
        long_slots += 1
        index = book.last_in(SELL, t - MARK_WINDOW_S, t)
        if index is not None:
            equity.append((t, cash + max(0, sell_value(book.quotes[SELL][index], sol, cell.keep))))
    equity.append((cell.end, final))
    peak, drawdown = None, Decimal(0)
    for _, value in equity:
        peak = value if peak is None or value > peak else peak
        if peak > 0:
            drawdown = max(drawdown, Decimal(peak - value) / Decimal(peak))
    return equity, long_slots, str((drawdown * 100).quantize(PCT, ROUND_HALF_EVEN))


def control_sequences(decisions, runs, seed):
    """Yield (kind, longs, flats) for the negative controls, deterministically."""
    valid = decisions.valid
    rng = random.Random("%s/random_entries" % seed)
    for _ in range(runs):
        cuts = sorted(rng.sample(range(len(valid)), decisions.changes)) + [len(valid)]
        longs, flats, state, previous = [], [], FLAT, 0
        for cut in cuts:
            (longs if state == LONG else flats).extend(valid[previous:cut])
            previous, state = cut, (FLAT if state == LONG else LONG)
        yield "random_entries", longs, flats
    rng = random.Random("%s/shuffled_signals" % seed)
    for _ in range(runs):
        # A uniform permutation of the targets over the usable minutes: the
        # LONG targets land on a uniform random subset of the same size.
        chosen = sorted(rng.sample(range(len(valid)), len(decisions.longs)))
        chosen_set = set(chosen)
        yield ("shuffled_signals", [valid[p] for p in chosen],
               [valid[p] for p in range(len(valid)) if p not in chosen_set])


def run_controls(cell, valuation, runs, seed, strategy_final):
    finals = {"random_entries": [], "shuffled_signals": []}
    for kind, longs, flats in control_sequences(cell.decisions, runs, seed):
        cash, sol, _, _, _ = simulate(cell, longs, flats)
        finals[kind].append(final_value(cell, valuation, cash, sol))
    result = {}
    for kind, values in finals.items():
        values.sort()
        entry = dict(runs=len(values), seed="%s/%s" % (seed, kind))
        if values:
            beating = sum(1 for value in values if value > strategy_final)
            entry.update(return_pct_p50=return_pct(nearest_rank(values, 50)),
                         return_pct_p95=return_pct(nearest_rank(values, 95)),
                         share_beating_strategy=str((Decimal(beating) / len(values)).quantize(SHARE)))
        else:
            entry.update(return_pct_p50=None, return_pct_p95=None, share_beating_strategy=None)
        result[kind] = entry
    result["target_changes"] = cell.decisions.changes
    return result


def hold_sol(cell, valuation, start):
    index = cell.book.first_at_or_after(BUY, start)
    if index is None:
        return None, None
    quote = cell.book.quotes[BUY][index]
    _, got = buy_amount(quote, INITIAL_USDC, cell.keep)
    return final_value(cell, valuation, 0, got), quote


# Guards, hashes, output --------------------------------------------------------

def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def code_key(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def code_hashes(strategy_fn, strategy_file=None):
    source = strategy_file or inspect.getsourcefile(strategy_fn)
    if source is None:
        raise Rejected("Cannot locate the strategy's source file for its hash")
    return {code_key(path): file_sha256(path) for path in (Path(__file__), Path(source))}


def read_lock(plan_lock):
    if plan_lock is None or not Path(plan_lock).is_file():
        return None, None
    raw = Path(plan_lock).read_bytes()
    lock = strict_json(raw.decode("utf-8"))
    try:
        windows = {name: (timestamp(lock[name]["start"]), timestamp(lock[name]["end"]))
                   for name in ("development", "holdout")}
        if not isinstance(lock["code_sha256"], dict) or not isinstance(lock["plan_sha256"], str):
            raise TypeError
    except (KeyError, TypeError) as exc:
        raise Rejected("plan_lock.json lacks windows, plan or code hashes") from exc
    return dict(lock, windows=windows), hashlib.sha256(raw).hexdigest()


def check_period(label, start, end, plan_lock, hashes, now):
    """Refuse a holdout run unless it is exactly the locked window with locked code."""
    if label not in LABELS:
        raise Rejected("label must be one of %s" % ", ".join(LABELS))
    if not start < end:
        raise Rejected("start must be before end")
    if end > now:
        raise Rejected("The period has not ended; refusing a replay of incomplete data")
    lock, lock_sha = read_lock(plan_lock)
    if label == "forward":
        # The running paper view (P2_PLAN.md section 6): only with a lock and the locked
        # code, always from the start of the development window. Never an evaluation.
        if lock is None:
            raise Rejected("Forward run refused: no plan_lock.json at %s" % plan_lock)
        if start != lock["windows"]["development"][0]:
            raise Rejected("Forward run refused: it must start at the locked development start")
        for path, digest in hashes.items():
            if lock["code_sha256"].get(path) != digest:
                raise Rejected("Forward run refused: %s differs from the locked code" % path)
        return lock["plan_sha256"], lock_sha
    if label == "holdout":
        if lock is None:
            raise Rejected("Holdout evaluation refused: no plan_lock.json at %s" % plan_lock)
        if (start, end) != lock["windows"]["holdout"]:
            raise Rejected("Holdout evaluation refused: period is not the locked holdout window")
        for path, digest in hashes.items():
            if lock["code_sha256"].get(path) != digest:
                raise Rejected("Holdout evaluation refused: %s differs from the locked code" % path)
    elif lock is not None:
        low, high = lock["windows"]["holdout"]
        if start < high and end > low:
            raise Rejected("Period overlaps the locked holdout window; label it holdout or move it")
    return (lock["plan_sha256"] if lock else None), lock_sha


def new_run_id(created_at):
    return "%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(created_at)), secrets.token_hex(4))


def write_evaluation(out_dir, record):
    """Write `record` as a new `<run_id>.json`; an existing file is never replaced."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for _ in range(20):
        run_id = new_run_id(record["created_at"])
        record["run_id"] = run_id
        data = (json.dumps(record, sort_keys=True, allow_nan=False, indent=1) + "\n").encode()
        final, temp = out_dir / (run_id + ".json"), out_dir / (".%s.%s.tmp" % (run_id, os.getpid()))
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, final)   # fails if the name exists: no overwrite, no partial file
        except FileExistsError:
            continue
        finally:
            temp.unlink()
        return final
    raise Rejected("Could not find a free run_id")


ASSUMPTIONS = [
    "Decisions at each minute boundary in [start, end) + decision_offset_s, from bars (and revisions) "
    "first seen by then; unusable snapshots and Rejected strategies hold the position (metrics.missing).",
    "Fill = first journaled Jupiter quote in the trade direction with decision+delay_s <= observed_at <= "
    "decision+delay_s+120 s and observed_at < period end; otherwise MISSING_QUOTE and the position is "
    "unchanged. One order in flight at a time; decisions meanwhile place no order.",
    "Jupiter outAmount is taken as net of feeBps; feeBps is not subtracted again.",
    "Per fill: extra_cost_bps adverse on the output, then 0.01 USDC assumed network fee (paper book).",
    "Account starts with 25.01 USDC (one 25 USDC buy quote + one network fee), all-in LONG or FLAT; the "
    "first buy uses the quote's outAmount exactly.",
    "LINEAR SCALING: later buys spend all cash minus the fee and every sale sells the whole SOL holding "
    "at the rate of the fixed-size quote (25 USDC buy, 0.35 SOL sell), scaled linearly; price impact "
    "is assumed proportional to size.",
    "A sale worth less than the network fee returns 0 USDC; an account whose cash cannot pay the fee "
    "or buy any SOL stops trading (ruin). Only churning controls can get there.",
    "Open SOL is valued as a sale (same costs) on the last sell quote observed within 300 s before the "
    "valuation time; equity points without such a quote are omitted.",
    "Controls use the same pricing and delay: random_entries places the strategy's number of target "
    "changes at random usable minutes; shuffled_signals permutes the strategy's targets over its "
    "usable minutes. Seeds: random.Random('<seed>/<kind>').",
    "Percentiles are nearest-rank; share_beating_strategy counts controls with a strictly higher "
    "final value.",
]


def evaluate(journal_path, strategy_name, strategy_fn, params, start, end, label,
             delays=DEFAULT_DELAYS, costs=DEFAULT_COSTS, *, bars=DEFAULT_BARS, out_dir=DEFAULT_OUT,
             plan_lock=DEFAULT_PLAN_LOCK, controls=DEFAULT_CONTROLS, seed=DEFAULT_SEED,
             decision_offset_s=DECISION_OFFSET_S, strategy_file=None, news_sources=(), fast=True,
             clock=time.time, extra=None):
    """Decide once, then price every (delay, cost) cell; one file per cell.

    Returns the list of written records (each with `path`). Raises Rejected
    before writing anything if a guard refuses the run; raises Rejected after
    writing REJECTED files if the data cannot be evaluated.
    """
    start, end = timestamp(start), timestamp(end)
    if not isinstance(strategy_name, str) or not strategy_name or not callable(strategy_fn):
        raise Rejected("A strategy name and callable are required")
    if not isinstance(params, dict):
        raise Rejected("params must be a JSON object")
    try:
        canonical(params)
    except (TypeError, ValueError) as exc:
        raise Rejected("params must be JSON-serialisable") from exc
    delays, costs = list(delays), list(costs)
    for delay in delays:
        timestamp(delay)
    if not delays or not costs:
        raise Rejected("At least one delay and one cost are required")
    for cost in costs:
        if type(cost) is not int or not 0 <= cost < 10000:
            raise Rejected("extra_cost_bps must be an integer in 0..9999")
    if type(controls) is not int or controls < 0:
        raise Rejected("controls must be a non-negative integer")
    hashes = code_hashes(strategy_fn, strategy_file)
    plan_sha, lock_sha = check_period(label, start, end, plan_lock, hashes, clock())
    journal_sha = file_sha256(journal_path)
    created_at = clock()
    base = dict(kind="replay", created_at=created_at, label=label, plan_sha256=plan_sha,
                plan_lock_sha256=lock_sha, code_sha256=hashes, journal_sha256=journal_sha,
                period=dict(start=start, end=end), strategy=strategy_name, params=params, bars=bars,
                decision_offset_s=decision_offset_s, seed=seed, assumptions=list(ASSUMPTIONS),
                verdict=None, **(extra or {}))
    cells = [(delay, cost) for delay in delays for cost in costs]
    records = []
    journal = Journal(journal_path, readonly=True)
    try:
        try:
            decisions = decide(journal, strategy_fn, params, start, end, bars, decision_offset_s,
                               news_sources=news_sources, fast=fast)
            book = QuoteBook(journal, start, end)
        except Rejected as exc:
            for delay, cost in cells:
                records.append(_rejected(out_dir, base, delay, cost, exc))
            raise Rejected("Evaluation rejected (%s); files written: %s"
                           % (exc, ", ".join(r["path"] for r in records))) from exc
        quotes_seen = quote_coverage(book, start, end)
        failures = []
        for delay, cost in cells:
            try:
                record = _cell_record(base, decisions, book, start, end, delay, cost, controls, seed, quotes_seen)
            except Rejected as exc:
                records.append(_rejected(out_dir, base, delay, cost, exc))
                failures.append(str(exc))
                continue
            after = file_sha256(journal_path)
            if after != journal_sha:
                record["journal_sha256_after"] = after
                record["missing"].append("Journal file changed during the run (live journal?); "
                                         "evaluate a backup copy for a reproducible hash.")
            record["path"] = str(write_evaluation(out_dir, record))
            records.append(record)
        if failures:
            raise Rejected("Some cells rejected: %s" % "; ".join(sorted(set(failures))))
        return records
    finally:
        journal.close()


def _rejected(out_dir, base, delay, cost, exc):
    record = dict(base, status="REJECTED", error=str(exc), delay_s=delay, extra_cost_bps=cost, trades=[],
                  equity=[], metrics=None, benchmarks=None, controls=None, missing=[str(exc)])
    record["path"] = str(write_evaluation(out_dir, record))
    return record


def _cell_record(base, decisions, book, start, end, delay, cost, controls, seed, quotes_seen):
    cell = Cell(decisions, book, end, delay, cost)
    index = book.last_in(SELL, end - MARK_WINDOW_S, end)
    if index is None:
        raise Rejected("No sell quote in the 300 s before the period end to value positions")
    valuation = book.quotes[SELL][index]
    trades = []
    cash, sol, fills, orders, missing_quotes = simulate(cell, decisions.longs, decisions.flats, trades)
    final = final_value(cell, valuation, cash, sol)
    equity, long_slots, drawdown = equity_and_exposure(cell, fills, final)
    minutes = decisions.coverage["minutes"]
    missing_list = ["%d decision(s) WAIT, %s" % (n, reason) for reason, n in sorted(decisions.reasons.items())]
    if missing_quotes:
        missing_list.append("%d order(s) MISSING_QUOTE" % missing_quotes)
    hold_final, hold_quote = hold_sol(cell, valuation, start)
    if hold_quote is None:
        missing_list.append("hold_sol benchmark: no buy quote in the period")
    metrics = dict(
        final_usdc_dec=usdc_dec(final), return_pct=return_pct(final), max_drawdown_pct=drawdown,
        trades=len(fills), missing=len(decisions.times) - len(decisions.valid),
        exposure_pct=pct(long_slots, len(decisions.times)),
        round_trips=sum(1 for fill in fills if fill[1] == SELL),
        orders=orders, missing_quotes=missing_quotes, missing_quote_pct=pct(missing_quotes, orders),
        decisions=len(decisions.times), usable_decisions=len(decisions.valid),
        candle_coverage_pct=pct(decisions.coverage["candle_minutes"], minutes),
        quote_coverage_buy_pct=pct(quotes_seen[BUY], minutes),
        quote_coverage_sell_pct=pct(quotes_seen[SELL], minutes),
        period_minutes=minutes, open_position_at_end=sol > 0,
        fill_lag_s_max=max((t["filled_at"] - t["decided_at"] for t in trades if t["filled_at"]), default=None))
    benchmarks = dict(cash_return_pct="0",
                      hold_sol_return_pct=return_pct(hold_final) if hold_quote else None,
                      hold_sol_quote_id=hold_quote["quote_id"] if hold_quote else None,
                      hold_sol_bought_at=hold_quote["observed_at"] if hold_quote else None,
                      valuation_quote_id=valuation["quote_id"], valuation_observed_at=valuation["observed_at"])
    return dict(base, status="OK", delay_s=delay, extra_cost_bps=cost, trades=trades,
                equity=[[t, round(v / 1e6, 6)] for t, v in equity], metrics=metrics, benchmarks=benchmarks,
                controls=run_controls(cell, valuation, controls, seed, final), missing=missing_list,
                decisions_sha256=decisions.digest())


def run(journal, strategy_name, strategy_fn, params, start, end, delay_s, extra_cost_bps, label, **options):
    """One evaluation, one file. `options` as for `evaluate` (out_dir, plan_lock, bars, ...)."""
    return evaluate(journal, strategy_name, strategy_fn, params, start, end, label,
                    delays=(delay_s,), costs=(extra_cost_bps,), **options)[0]


def sensitivity(journal, strategy_name, strategy_fn, params, start, end, label,
                delays=DEFAULT_DELAYS, costs=DEFAULT_COSTS, **options):
    """Delay x cost grid; decisions computed once; one file per cell."""
    return evaluate(journal, strategy_name, strategy_fn, params, start, end, label,
                    delays=delays, costs=costs, **options)


# CLI ---------------------------------------------------------------------------

def parse_time(text):
    try:
        return timestamp(float(text))
    except ValueError:
        pass
    try:
        moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Rejected("Invalid time %r" % text) from exc
    if moment.tzinfo is None:
        raise Rejected("Time %r needs a timezone (e.g. Z)" % text)
    return moment.timestamp()


def parse_list(text, kind):
    try:
        return [kind(part) for part in text.split(",") if part.strip()]
    except ValueError as exc:
        raise Rejected("Invalid list %r" % text) from exc


def resolve_strategy(name):
    """`jupiter_bot.research.strategies.STRATEGIES[name]` = (fn, bars_needed(params), grid)."""
    module = importlib.import_module("jupiter_bot.research.strategies")
    try:
        fn, bars_needed, grid = module.STRATEGIES[name]
    except KeyError as exc:
        raise Rejected("Unknown strategy %r; known: %s" % (name, ", ".join(sorted(module.STRATEGIES)))) from exc
    return module, fn, bars_needed, list(grid)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m jupiter_bot.research.replay",
                                     description="Point-in-time replay; one file per (params, delay, cost).")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--label", required=True, choices=[l for l in LABELS if l != "forward"])   # forward: research.forward only
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--plan-lock", default=str(DEFAULT_PLAN_LOCK))
    parser.add_argument("--delays", default=",".join(map(str, DEFAULT_DELAYS)))
    parser.add_argument("--costs", default=",".join(map(str, DEFAULT_COSTS)))
    parser.add_argument("--params", help="JSON object; must be one of the strategy's grid entries "
                                         "unless --label synthetic")
    parser.add_argument("--controls", type=int, default=DEFAULT_CONTROLS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    try:
        module, fn, bars_needed, grid = resolve_strategy(args.strategy)
        if args.params is not None:
            params = strict_json(args.params)
            if params not in grid and args.label != "synthetic":
                raise Rejected("--params is not in the %s grid (the trial budget)" % args.strategy)
            selected = [params]
        else:
            selected = grid
        start, end = parse_time(args.start), parse_time(args.end)
        delays, costs = parse_list(args.delays, float), parse_list(args.costs, int)
        batch = dict(id=secrets.token_hex(8), strategy=args.strategy, delays=delays, costs=costs,
                     params=selected, trial_budget=getattr(module, "TRIAL_BUDGET", None))
        failed = False
        for params in selected:
            extra = dict(batch=batch, grid_index=grid.index(params) if params in grid else None)
            try:
                records = evaluate(args.journal, args.strategy, fn, params, start, end, args.label, delays, costs,
                                   bars=bars_needed(params), out_dir=args.out, plan_lock=args.plan_lock,
                                   controls=args.controls, seed=args.seed, strategy_file=module.__file__,
                                   extra=extra)
            except Rejected as exc:
                print(json.dumps(dict(params=params, status="REJECTED", error=str(exc))), file=sys.stderr)
                failed = True
                continue
            for record in records:
                print(json.dumps(dict(path=record["path"], params=params, delay_s=record["delay_s"],
                                      extra_cost_bps=record["extra_cost_bps"], status=record["status"])))
        return 1 if failed else 0
    except Rejected as exc:
        print("Rejected: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
