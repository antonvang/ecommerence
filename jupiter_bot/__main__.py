"""Run with python -m jupiter_bot. All execution here is fictitious."""
from __future__ import annotations

import argparse
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from .core import ASSETS, SOL, USDC, Candle, Quote, QuoteRequest, Rejected, atoms, canonical, positive_integer, reject_json_constant
from .jupiter import JupiterQuotes
from .paper import PaperBook
from .runner import step


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle, parse_constant=reject_json_constant)


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
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo()
        elif args.command == "quote":
            input_asset, output_asset = ASSETS[args.input], ASSETS[args.output]
            result = JupiterQuotes().quote(QuoteRequest(input_asset, output_asset, atoms(args.amount, input_asset))).as_dict()
            if args.out:
                destination = Path(args.out)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("x", encoding="utf-8") as handle:
                    handle.write(canonical(result) + "\n")
        elif args.command == "paper-step":
            snapshot, quote = read_json(args.snapshot), read_quote(args.quote_file)
            now = time.time()
            if snapshot.get("market") != "SOL/USDC" or snapshot.get("source") != "RECORDED":
                raise Rejected("Expected recorded SOL/USDC observations")
            if snapshot["as_of"] > now or quote.source != "JUPITER_QUOTE":
                raise Rejected("Future decision or non-observed quote")
            quote.require_fresh(now)
            destination = Path(args.db)
            destination.parent.mkdir(parents=True, exist_ok=True)
            book = PaperBook(destination, source="JUPITER_QUOTE")
            try:
                result = step([Candle.parse(row) for row in snapshot["candles"]],
                              snapshot.get("news", []), book, lambda request: quote,
                              snapshot["as_of"], time.time)
            finally:
                book.close()
        else:
            if not Path(args.db).is_file():
                raise Rejected("Paper database does not exist")
            book = PaperBook(args.db, source=args.source)
            try:
                result = book.state()
            finally:
                book.close()
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (Rejected, KeyError, TypeError, OSError, ValueError) as exc:
        print(json.dumps(dict(status="BLOCKED", live_execution=False, reason=str(exc))), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
