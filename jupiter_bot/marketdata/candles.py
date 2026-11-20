"""Candle adapters. Parsing only; the journal decides what is new or revised.

An adapter turns one raw response into closed bars. It never fills a missing
bar, never carries a last price forward and never returns a still-open bar.
Unexpected shapes reject the whole response, so an API change fails closed.
"""
from __future__ import annotations

import email.utils
from dataclasses import dataclass
from decimal import Decimal

from ..core import Rejected, decimal_value, strict_json
from .transport import Endpoint

INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}
# A bar counts as closed only this long after its end, by the earlier of our
# clock and the server's Date header, so a fast local clock cannot close it early.
SETTLE_SECONDS = 5.0


def canonical_decimal(value):
    number = decimal_value(value)
    text = format(number.normalize(), "f")
    return "0" if text in ("-0", "") else text


@dataclass(frozen=True)
class Bar:
    start: float
    end: float
    open: str
    high: str
    low: str
    close: str
    volume: str

    def values(self):
        return (self.open, self.high, self.low, self.close, self.volume)


@dataclass(frozen=True)
class CandleBatch:
    instrument: str
    interval_s: int
    bars: tuple
    open_skipped: int
    duplicates: int


def check_bar(bar):
    o, h, l, c, v = (Decimal(x) for x in bar.values())
    if min(o, h, l, c) <= 0 or v < 0:
        raise Rejected("Invalid candle values")
    if not l <= min(o, c) <= max(o, c) <= h:
        raise Rejected("Inconsistent OHLC")


def server_now(headers, received_at):
    """The earlier of our receive time and the server's Date header."""
    date = (headers or {}).get("date")
    if not date:
        return received_at
    try:
        parsed = email.utils.parsedate_to_datetime(date)
    except (TypeError, ValueError, IndexError):
        raise Rejected("Unparseable Date header")
    if parsed is None or parsed.tzinfo is None:
        raise Rejected("Date header without timezone")
    return min(received_at, parsed.timestamp())


def collect(instrument, interval_s, bars, received_at, headers):
    """Drop open bars, merge identical duplicates, reject conflicting ones."""
    closed_by = server_now(headers, received_at) - SETTLE_SECONDS
    by_start, open_skipped, duplicates = {}, 0, 0
    for bar in bars:
        if bar.end - bar.start != interval_s or bar.start % interval_s:
            raise Rejected("Bar does not match the requested interval grid")
        check_bar(bar)
        if bar.end > closed_by:
            open_skipped += 1
            continue
        if bar.start in by_start:
            if by_start[bar.start] != bar:
                raise Rejected("Conflicting duplicate bar in one response")
            duplicates += 1
            continue
        by_start[bar.start] = bar
    ordered = tuple(by_start[start] for start in sorted(by_start))
    return CandleBatch(instrument, interval_s, ordered, open_skipped, duplicates)


class BinanceKlines:
    """Binance Spot public market data, SOLUSDC. Keyless; see DATA_SOURCES.md."""

    kind = "candles"
    source = "binance_spot_klines"
    endpoint = Endpoint("api.binance.com", "/api/v3/klines",
                        frozenset({"symbol", "interval", "limit"}))
    min_interval = 2.0          # far below the documented weight budget
    default_cooldown = 60.0     # when 429 arrives without Retry-After
    ban_cooldown = 900.0        # HTTP 418: IP ban; back off much longer
    symbols = {"SOL/USDC": "SOLUSDC"}

    def __init__(self, instrument="SOL/USDC", interval="1m", limit=200):
        if instrument not in self.symbols or interval not in INTERVALS:
            raise Rejected("Unsupported instrument or interval")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise Rejected("limit must be 1..1000")
        self.instrument, self.interval, self.limit = instrument, interval, limit
        self.interval_s = INTERVALS[interval]

    def params(self):
        return {"symbol": self.symbols[self.instrument], "interval": self.interval, "limit": str(self.limit)}

    def parse(self, body, requested_at, received_at, headers):
        rows = strict_json(body)
        if not isinstance(rows, list):
            raise Rejected("Expected a JSON array of klines")
        step_ms = self.interval_s * 1000
        bars = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 7:
                raise Rejected("Unexpected kline shape")
            open_ms, close_ms = row[0], row[6]
            if type(open_ms) is not int or type(close_ms) is not int or close_ms != open_ms + step_ms - 1:
                raise Rejected("Kline times do not match the interval")
            if not all(isinstance(value, str) for value in row[1:6]):
                raise Rejected("Kline prices and volume must be decimal strings")
            bars.append(Bar(open_ms / 1000, (close_ms + 1) / 1000,
                            *(canonical_decimal(value) for value in row[1:6])))
        return collect(self.instrument, self.interval_s, bars, received_at, headers)
