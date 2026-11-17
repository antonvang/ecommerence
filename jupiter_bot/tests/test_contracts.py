"""Offline, synthetic tests. Never import Copybot or its protected data."""
import dataclasses
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from jupiter_bot.__main__ import demo, read_quote, synthetic_bars
from jupiter_bot.core import ASSETS, SOL, USDC, Asset, Candle, Quote, QuoteRequest, Rejected, analyse, atoms
from jupiter_bot.jupiter import JupiterQuotes, public_get


def quote(input_asset=USDC, amount=25_000_000, output=250_000_000,
          observed=100.0, source="SYNTHETIC", fee=100):
    output_asset = SOL if input_asset == USDC else USDC
    request = QuoteRequest(input_asset, output_asset, amount)
    payload = dict(request.params(), inAmount=str(amount), outAmount=str(output),
                   router="metis", feeBps=fee, transaction=None)
    return Quote.parse(request, payload, observed - 0.25, observed, source)


class Contracts(unittest.TestCase):
    def test_atomic_units_never_silently_round(self):
        self.assertEqual(atoms("0.000000001", SOL), 1)
        self.assertEqual(atoms("25", USDC), 25_000_000)
        for amount in ("0", "-1", "0.0000001", "NaN", "Infinity", True):
            with self.subTest(amount=amount), self.assertRaises(Rejected):
                atoms(amount, USDC)

    def test_allowlist_is_not_just_a_symbol_check(self):
        with self.assertRaises(Rejected):
            QuoteRequest(Asset("SOL", USDC.mint, 9), USDC, 10)
        for amount in (1.0, True, "10", -1, 0):
            with self.subTest(amount=amount), self.assertRaises(Rejected):
                QuoteRequest(SOL, USDC, amount)

    def test_quote_must_match_request_and_have_no_transaction(self):
        valid = quote()
        original = json.loads(valid.payload_json)
        changes = {"inputMint": SOL.mint, "outputMint": USDC.mint, "inAmount": "24999999",
                   "outAmount": "0", "transaction": "encoded-transaction", "router": "unknown",
                   "feeBps": True, "errorCode": 4, "routePlan": []}
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaises(Rejected):
                Quote.parse(valid.request, dict(original, **{field: value}), 99.75, 100)
        for missing in ("transaction", "feeBps", "router", "outAmount"):
            payload = dict(original)
            del payload[missing]
            with self.subTest(missing=missing), self.assertRaises(Rejected):
                Quote.parse(valid.request, payload, 99.75, 100)
        with self.assertRaises(Rejected):
            Quote.parse(valid.request, dict(original, router=[]), 99.75, 100)

    def test_expired_future_and_slow_quotes_are_rejected(self):
        valid = quote()
        for now in (99, 116, float("nan")):
            with self.subTest(now=now), self.assertRaises(Rejected):
                valid.require_fresh(now)
        with self.assertRaises(Rejected):
            Quote.parse(valid.request, json.loads(valid.payload_json), 80, 100)

    def test_client_uses_only_public_parameters_and_rate_limits(self):
        mono = [0.0]
        sleeps, urls = [], []

        def sleep(delay):
            sleeps.append(delay)
            mono[0] += delay

        def fetch(url):
            urls.append(url)
            return json.loads(quote(input_asset=SOL, amount=100_000_000, output=10_000_000).payload_json)

        client = JupiterQuotes(fetch=fetch, clock=lambda: 100, monotonic=lambda: mono[0], sleep=sleep)
        request = QuoteRequest(SOL, USDC, 100_000_000)
        client.quote(request)
        client.quote(request)
        self.assertAlmostEqual(sum(sleeps), 2.1)
        self.assertTrue(all("taker" not in url and "api-key" not in url and "/execute" not in url for url in urls))

    def test_unapproved_url_is_rejected_before_network(self):
        urls = ["https://api.jup.ag/swap/v2/execute", "https://other.example/swap/v2/order",
                "https://api.jup.ag/swap/v2/order?inputMint=x&outputMint=y&amount=1&taker=z"]
        with patch("urllib.request.build_opener", side_effect=AssertionError("network")):
            for url in urls:
                with self.subTest(url=url), self.assertRaises(Rejected):
                    public_get(url)

    def test_saved_quote_tampering_is_detected(self):
        record = quote().as_dict()
        record["response"]["outAmount"] = "999999999"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quote.json"
            path.write_text(json.dumps(record))
            with self.assertRaises(Rejected):
                read_quote(path)


class ResearchTiming(unittest.TestCase):
    def setUp(self):
        self.bars = synthetic_bars()[:60]
        self.now = self.bars[-1].end

    def test_future_candle_and_unclosed_bar_are_rejected(self):
        for bad in (dataclasses.replace(self.bars[-1], observed_at=self.now + 1),
                    dataclasses.replace(self.bars[-1], end=self.now + 1)):
            with self.assertRaises(Rejected):
                analyse(self.bars[:-1] + [bad], [], self.now)

    def test_gap_duplicate_and_stale_candles_are_rejected(self):
        for bars, now in ((self.bars[:-2] + self.bars[-1:], self.now),
                          (self.bars + self.bars[-1:], self.now),
                          (self.bars, self.now + 121)):
            with self.assertRaises(Rejected):
                analyse(bars, [], now)

    def test_invalid_ohlc_and_nonfinite_values_are_rejected(self):
        with self.assertRaises(Rejected):
            analyse(self.bars[:-1] + [dataclasses.replace(self.bars[-1], low=Decimal(999))], [], self.now)
        with self.assertRaises(Rejected):
            Candle.parse(dict(start=0, end=60, observed_at=60, open="NaN", high=1, low=1, close=1, volume=1))

    def test_news_first_observed_later_is_not_available_earlier(self):
        article = dict(title="Synthetic headline", url="https://example.com/source",
                       published_at=self.now - 120, observed_at=self.now + 1)
        with self.assertRaises(Rejected):
            analyse(self.bars, [article], self.now)

    def test_news_is_context_and_does_not_invent_direction(self):
        article = dict(title="Synthetic headline", url="https://example.com/source",
                       published_at=self.now - 120, observed_at=self.now)
        without = analyse(self.bars, [], self.now)
        with_news = analyse(self.bars, [article], self.now)
        self.assertEqual(without["action"], with_news["action"])
        self.assertFalse(with_news["news_used_for_signal"])
        self.assertFalse(with_news["validated_edge"])

    def test_warmup_never_requests_an_order(self):
        result = analyse(self.bars[:49], [], self.bars[48].end)
        self.assertEqual(result["action"], "WAIT")

    def test_synthetic_demo_buys_and_sells_and_labels_evidence(self):
        result = demo()
        self.assertEqual(result["account"]["fills"], 2)
        self.assertEqual(result["account"]["sol"], 0)
        self.assertFalse(result["evidence_of_profit"])
        self.assertFalse(result["account"]["live_execution"])
