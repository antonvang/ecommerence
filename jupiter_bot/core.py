"""Strict data contracts and a fixed, non-validated plumbing baseline."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


class Rejected(ValueError):
    """Bad or insufficient evidence: stop, do not invent a replacement."""


@dataclass(frozen=True)
class Asset:
    symbol: str
    mint: str
    decimals: int


SOL = Asset("SOL", "So11111111111111111111111111111111111111112", 9)
USDC = Asset("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6)
ASSETS = {asset.symbol: asset for asset in (SOL, USDC)}
ROUTERS = {"metis", "jupiterz", "dflow", "okx"}
SOURCES = {"JUPITER_QUOTE", "SYNTHETIC"}
U64_MAX = 2**64 - 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def reject_json_constant(value):
    raise Rejected("Non-finite JSON constant: " + value)


def decimal_value(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise Rejected("Expected a finite decimal")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise Rejected("Invalid decimal") from exc
    if not number.is_finite():
        raise Rejected("Non-finite decimal")
    return number


def positive_integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise Rejected("Expected an integer or integer string")
    if isinstance(value, str) and (not value.isascii() or not value.isdigit()):
        raise Rejected("Expected an unsigned integer string")
    number = int(value)
    if not 0 < number <= U64_MAX:
        raise Rejected("Amount outside positive u64 range")
    return number


def atoms(amount, asset):
    number = decimal_value(amount) * 10**asset.decimals
    if number != number.to_integral_value():
        raise Rejected("Amount has more precision than the asset allows")
    return positive_integer(int(number))


def timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Rejected("Timestamp must be a finite Unix number")
    if not math.isfinite(value) or value < 0:
        raise Rejected("Invalid timestamp")
    return float(value)


@dataclass(frozen=True)
class QuoteRequest:
    input_asset: Asset
    output_asset: Asset
    amount: int

    def __post_init__(self):
        for asset in (self.input_asset, self.output_asset):
            if ASSETS.get(asset.symbol) != asset:
                raise Rejected("Asset is not on the fixed allowlist")
        if self.input_asset == self.output_asset:
            raise Rejected("Input and output must differ")
        if type(self.amount) is not int:
            raise Rejected("Request amount must be an integer")
        positive_integer(self.amount)

    def params(self):
        return {"inputMint": self.input_asset.mint,
                "outputMint": self.output_asset.mint, "amount": str(self.amount)}


@dataclass(frozen=True)
class Quote:
    request: QuoteRequest
    out_amount: int
    router: str
    fee_bps: int
    started_at: float
    observed_at: float
    source: str
    payload_json: str

    @classmethod
    def parse(cls, request, payload, started_at, observed_at, source="JUPITER_QUOTE"):
        started_at, observed_at = timestamp(started_at), timestamp(observed_at)
        if observed_at < started_at or observed_at - started_at > 10:
            raise Rejected("Invalid or slow quote observation")
        if not isinstance(source, str) or source not in SOURCES or not isinstance(payload, dict):
            raise Rejected("Invalid quote provenance")
        if payload.get("error") or payload.get("errorCode") is not None:
            raise Rejected("Upstream reported an error")
        if "transaction" not in payload or payload["transaction"] is not None:
            raise Rejected("Only transaction-free quotes are accepted")
        for field, expected in (("inputMint", request.input_asset.mint),
                                ("outputMint", request.output_asset.mint)):
            if payload.get(field) != expected:
                raise Rejected("Quote mint does not match the request")
        if positive_integer(payload.get("inAmount")) != request.amount:
            raise Rejected("Quote amount does not match the request")
        output = positive_integer(payload.get("outAmount"))
        router, fee = payload.get("router"), payload.get("feeBps")
        if not isinstance(router, str) or router not in ROUTERS:
            raise Rejected("Unknown or missing router")
        if type(fee) is not int or not 0 <= fee < 10000:
            raise Rejected("Invalid or missing fee")
        if "routePlan" in payload and not payload["routePlan"]:
            raise Rejected("Empty route")
        try:
            raw = canonical(payload)
        except (ValueError, TypeError) as exc:
            raise Rejected("Quote is not finite JSON") from exc
        return cls(request, output, router, fee, started_at, observed_at, source, raw)

    @property
    def quote_id(self):
        identity = canonical([self.payload_json, self.started_at, self.observed_at, self.source])
        return hashlib.sha256(identity.encode()).hexdigest()

    def require_fresh(self, now, ttl=15):
        age = timestamp(now) - self.observed_at
        if not 0 <= age <= ttl:
            raise Rejected("Quote is expired or from the future")

    def as_dict(self):
        return {"quote_id": self.quote_id, "source": self.source,
                "started_at": self.started_at, "observed_at": self.observed_at,
                "request": self.request.params(), "response": json.loads(self.payload_json)}


@dataclass(frozen=True)
class Candle:
    start: float
    end: float
    observed_at: float
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @classmethod
    def parse(cls, row):
        return cls(timestamp(row["start"]), timestamp(row["end"]),
                   timestamp(row["observed_at"]),
                   *(decimal_value(row[k]) for k in ("open", "high", "low", "close", "volume")))

    def validate(self, as_of):
        if not self.start < self.end <= self.observed_at <= as_of:
            raise Rejected("Unclosed or future candle")
        if min(self.open, self.high, self.low, self.close) <= 0 or self.volume < 0:
            raise Rejected("Invalid candle values")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise Rejected("Inconsistent OHLC")


def analyse(candles, news, as_of):
    as_of = timestamp(as_of)
    interval = None
    for index, bar in enumerate(candles):
        bar.validate(as_of)
        width = bar.end - bar.start
        if interval is not None and (width != interval or bar.start != candles[index - 1].end):
            raise Rejected("Candle gap, duplicate or changing interval")
        interval = width
    if candles and as_of - candles[-1].end > 2 * interval:
        raise Rejected("Candle data is stale")
    for article in news:
        published = timestamp(article["published_at"])
        observed = timestamp(article["observed_at"])
        if not published <= observed <= as_of:
            raise Rejected("News was not available at the decision time")
        parsed = urlsplit(article["url"])
        if parsed.scheme != "https" or not parsed.hostname or not article.get("title"):
            raise Rejected("News needs a title and HTTPS source URL")
    result = {"action": "WAIT", "as_of": as_of, "bars": len(candles),
              "news_count": len(news), "news_used_for_signal": False,
              "rule": "EMA20_50_PLUMBING_BASELINE", "validated_edge": False}
    if len(candles) < 50:
        return dict(result, reason="WARMUP: at least 50 closed bars required")

    def ema(period):
        value = candles[0].close
        alpha = Decimal(2) / (period + 1)
        for bar in candles[1:]:
            value += alpha * (bar.close - value)
        return value

    fast, slow = ema(20), ema(50)
    result.update(action="BUY" if fast > slow else "SELL" if fast < slow else "WAIT",
                  ema20=str(fast), ema50=str(slow), reason="Fixed plumbing baseline; no profit claim")
    return result
