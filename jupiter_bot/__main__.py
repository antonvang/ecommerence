"""Run with python -m jupiter_bot. All execution here is fictitious."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from decimal import Decimal
from pathlib import Path

from .core import (ASSETS, SOL, USDC, Candle, Quote, QuoteRequest, Rejected, atoms, canonical,
                   positive_integer, strict_json, timestamp)
from .jupiter import JupiterQuotes
from .marketdata.candles import INTERVALS, BinanceKlines
from .marketdata import collect, livecheck
from .marketdata.journal import Journal
from .marketdata.news import NEWS_FEEDS
from .marketdata.observe import observe
from .marketdata.quotes import JupiterQuoteSample
from .marketdata.snapshot import build_snapshot
from .paper import PaperBook
from .runner import step


# The old Copybot lab lives next to this package. Nothing here may write there.
PROTECTED = (Path(__file__).resolve().parent.parent / "copybot",)


def allowed_path(path):
    """Resolve a user-supplied path and refuse protected locations (even for reads)."""
    resolved = Path(path).resolve()
    for protected in PROTECTED:
        if resolved == protected or protected in resolved.parents:
            raise Rejected("Refusing to write inside protected directory %s" % protected)
    return resolved


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return strict_json(handle.read())


def read_quote(path):
    record = read_json(path)
    by_mint = {asset.mint: asset for asset in ASSETS.values()}
    request = record["request"]
    quote = Quote.parse(QuoteRequest(by_mint[request["inputMint"]], by_mint[request["outputMint"]],
                                     positive_integer(request["amount"])),
                        record["response"], record["started_at"], record["observed_at"], record["source"])
    if record["quote_id"] != quote.quote_id:
        raise Rejected("Saved quote identity mismatch")
    return quote


def synthetic_bars():
    # Entirely invented prices. The calendar date does not identify market data.
    start = 1794916800
    bars, previous = [], Decimal(100)
    for index in range(160):
        close = Decimal(100) + Decimal(index) / 5 if index < 90 else Decimal(118) - Decimal(index - 90) * Decimal("0.6")
        end = start + (index + 1) * 60
        bars.append(Candle.parse(dict(start=end - 60, end=end, observed_at=end,
                                      open=str(previous), high=str(max(previous, close) + 1),
                                      low=str(min(previous, close) - 1), close=str(close), volume="10000")))
        previous = close
    return bars


def demo():
    book = PaperBook(":memory:")
    try:
        bars = synthetic_bars()
        for index in range(len(bars) - 1):
            decision_at = bars[index].end
            fill_at = decision_at + 0.5
            next_open = bars[index + 1].open

            def provider(request):
                if request.input_asset == USDC:
                    gross = Decimal(request.amount) / 10**USDC.decimals / next_open * 10**SOL.decimals
                else:
                    gross = Decimal(request.amount) / 10**SOL.decimals * next_open * 10**USDC.decimals
                # Invented quote already includes 50 bps. PaperBook adds only its
                # separately stated adverse-price and network assumptions.
                payload = dict(request.params(), inAmount=str(request.amount),
                               outAmount=str(int(gross * Decimal("0.995"))),
                               router="metis", feeBps=50, transaction=None)
                return Quote.parse(request, payload, decision_at + 0.25, fill_at, "SYNTHETIC")

            step(bars[:index + 1], [], book, provider, decision_at, lambda: fill_at)
        return dict(mode="SYNTHETIC_PAPER", evidence_of_profit=False, bars=len(bars),
                    notice="Invented prices and costs; plumbing demonstration only", account=book.state())
    finally:
        book.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Jupiter research prototype: quotes and paper execution only")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Offline synthetic automatic buy/sell demonstration")
    quote_parser = commands.add_parser("quote", help="One public quote, no wallet or transaction")
    quote_parser.add_argument("--input", choices=ASSETS, default="SOL")
    quote_parser.add_argument("--output", choices=ASSETS, default="USDC")
    quote_parser.add_argument("--amount", default="0.1")
    quote_parser.add_argument("--out", help="Save audit record to a NEW JSON file")
    paper_parser = commands.add_parser("paper-step", help="One automatic paper decision using supplied observations")
    paper_parser.add_argument("--snapshot", required=True)
    paper_parser.add_argument("--quote-file", required=True)
    paper_parser.add_argument("--db", required=True)
    status_parser = commands.add_parser("status", help="Read an existing paper account")
    status_parser.add_argument("--db", required=True)
    status_parser.add_argument("--source", choices=["SYNTHETIC", "JUPITER_QUOTE"], default="JUPITER_QUOTE")
    observe_parser = commands.add_parser("observe", help="ONE fetch of market data into the journal; no loop")
    kinds = observe_parser.add_subparsers(dest="kind", required=True)
    candles_parser = kinds.add_parser("candles", help="Binance Spot SOLUSDC klines")
    candles_parser.add_argument("--journal", required=True)
    candles_parser.add_argument("--interval", choices=INTERVALS, default="1m")
    candles_parser.add_argument("--limit", type=int, default=200)
    news_parser = kinds.add_parser("news", help="One official status/release feed")
    news_parser.add_argument("--journal", required=True)
    news_parser.add_argument("--feed", choices=NEWS_FEEDS, required=True)
    sample_parser = kinds.add_parser("quote", help="One Jupiter quote sample (observation, never a fill)")
    sample_parser.add_argument("--journal", required=True)
    sample_parser.add_argument("--input", choices=ASSETS, default="USDC")
    sample_parser.add_argument("--output", choices=ASSETS, default="SOL")
    sample_parser.add_argument("--amount", default="25")
    snapshot_parser = commands.add_parser("snapshot", help="Point-in-time snapshot from the journal (read-only)")
    snapshot_parser.add_argument("--journal", required=True)
    snapshot_parser.add_argument("--out", required=True, help="NEW JSON file for paper-step --snapshot")
    snapshot_parser.add_argument("--as-of", type=float, help="Unix time; default now")
    snapshot_parser.add_argument("--interval", choices=INTERVALS, default="1m")
    snapshot_parser.add_argument("--bars", type=int, default=200)
    snapshot_parser.add_argument("--news", nargs="*", choices=NEWS_FEEDS, default=[])
    journal_parser = commands.add_parser("journal-status", help="Counts, gaps, outcomes and cooldowns (read-only)")
    journal_parser.add_argument("--journal", required=True)
    collect_parser = commands.add_parser("collect", help="ONE collection cycle over the fixed schedule (for a timer)")
    collect_parser.add_argument("--journal", required=True)
    live_parser = commands.add_parser("live-check", help="One fetch per source to check real formats; no loop")
    live_parser.add_argument("--out-dir", help="NEW directory; default jupiter_bot/runtime/live-check-<UTC time>")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo()
        elif args.command == "quote":
            input_asset, output_asset = ASSETS[args.input], ASSETS[args.output]
            request = QuoteRequest(input_asset, output_asset, atoms(args.amount, input_asset))
            # Validate the destination before spending a rate-limited network call.
            destination = allowed_path(args.out) if args.out else None
            if destination is not None and destination.exists():
                raise Rejected("Output file already exists; refusing to overwrite")
            result = JupiterQuotes().quote(request).as_dict()
            if destination is not None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("x", encoding="utf-8") as handle:
                    handle.write(canonical(result) + "\n")
        elif args.command == "paper-step":
            snapshot, quote = read_json(args.snapshot), read_quote(args.quote_file)
            now = time.time()
            if snapshot.get("market") != "SOL/USDC" or snapshot.get("source") != "RECORDED":
                raise Rejected("Expected recorded SOL/USDC observations")
            as_of = timestamp(snapshot.get("as_of"))
            if as_of > now or quote.source != "JUPITER_QUOTE":
                raise Rejected("Future decision or non-observed quote")
            quote.require_fresh(now)
            destination = allowed_path(args.db)
            destination.parent.mkdir(parents=True, exist_ok=True)
            book = PaperBook(destination, source="JUPITER_QUOTE")
            try:
                result = step([Candle.parse(row) for row in snapshot["candles"]],
                              snapshot.get("news", []), book, lambda request: quote,
                              as_of, time.time)
            finally:
                book.close()
        elif args.command == "observe":
            destination = allowed_path(args.journal)
            if args.kind == "candles":
                adapter = BinanceKlines(interval=args.interval, limit=args.limit)
            elif args.kind == "news":
                adapter = NEWS_FEEDS[args.feed]()
            else:
                input_asset, output_asset = ASSETS[args.input], ASSETS[args.output]
                adapter = JupiterQuoteSample(QuoteRequest(input_asset, output_asset,
                                                          atoms(args.amount, input_asset)))
            destination.parent.mkdir(parents=True, exist_ok=True)
            journal = Journal(destination)
            try:
                result = observe(journal, adapter)
            finally:
                journal.close()
        elif args.command == "snapshot":
            destination = allowed_path(args.out)
            if destination.exists():
                raise Rejected("Output file already exists; refusing to overwrite")
            journal = Journal(allowed_path(args.journal), readonly=True)
            try:
                result = build_snapshot(journal, time.time() if args.as_of is None else args.as_of,
                                        interval_s=INTERVALS[args.interval], bars=args.bars,
                                        news_sources=args.news)
            finally:
                journal.close()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8") as handle:
                handle.write(canonical(result) + "\n")
        elif args.command == "collect":
            destination = allowed_path(args.journal)
            destination.parent.mkdir(parents=True, exist_ok=True)
            journal = Journal(destination)
            try:
                report = collect.collect(journal)
            finally:
                journal.close()
            # One compact line per cycle: readable in `journalctl --user -u jupiter-collect`.
            print(json.dumps(dict(cycle_at=round(time.time(), 3), jobs=report), separators=(",", ":"),
                             allow_nan=False))
            return collect.exit_code(report)
        elif args.command == "live-check":
            default = Path(__file__).resolve().parent / "runtime" / time.strftime("live-check-%Y%m%dT%H%M%SZ", time.gmtime())
            result = livecheck.run(allowed_path(args.out_dir or default))
        elif args.command == "journal-status":
            journal = Journal(allowed_path(args.journal), readonly=True)
            try:
                result = journal.status()
            finally:
                journal.close()
        else:
            # Read-only: status never creates tables or accounts in any file.
            book = PaperBook(allowed_path(args.db), source=args.source, readonly=True)
            try:
                result = book.state()
            finally:
                book.close()
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (Rejected, KeyError, TypeError, OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps(dict(status="BLOCKED", live_execution=False, reason=str(exc))), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
