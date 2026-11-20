"""Parsers against real responses captured once by `live-check` on 2026-11-20.

The bytes are unmodified public responses (see fixtures/live_20261120/meta.json).
They pin what the sources actually sent; they are not research data.
"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401
from jupiter_bot.core import SOL, USDC, Quote, QuoteRequest, Rejected
from jupiter_bot.marketdata.candles import BinanceKlines
from jupiter_bot.marketdata.journal import Journal
from jupiter_bot.marketdata.news import NEWS_FEEDS
from jupiter_bot.marketdata.observe import observe
from jupiter_bot.marketdata.quotes import JupiterQuoteSample
from jupiter_bot.marketdata.snapshot import build_snapshot
from jupiter_bot.marketdata.transport import RawResponse

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "live_20261120"
META = json.loads((FIXTURES / "meta.json").read_text(encoding="utf-8"))["files"]


def captured(name):
    body = (FIXTURES / name).read_bytes()
    meta = META[name]
    return body, meta


class Integrity(unittest.TestCase):
    def test_fixture_bytes_match_their_recorded_hashes(self):
        for name, meta in META.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest(), meta["body_sha256"])


class RealResponses(unittest.TestCase):
    def test_binance_klines_shape_and_open_bar(self):
        body, meta = captured("binance_klines_SOLUSDC_1m.json")
        batch = BinanceKlines(limit=5).parse(body, meta["requested_at"], meta["received_at"], meta["headers"])
        self.assertEqual((len(batch.bars), batch.open_skipped, batch.duplicates), (4, 1, 0))
        self.assertEqual(batch.bars[-1].close, "68.87")
        self.assertTrue(all(bar.end - bar.start == 60 for bar in batch.bars))

    def jupiter(self, name, input_asset, output_asset):
        body, meta = captured(name)
        payload = json.loads(body)
        request = QuoteRequest(input_asset, output_asset, int(payload["inAmount"]))
        quote = Quote.parse(request, payload, meta["requested_at"], meta["received_at"], "JUPITER_QUOTE")
        return payload, quote

    def test_jupiter_metis_quote_out_amount_is_net_of_output_side_fee(self):
        payload, quote = self.jupiter("jupiter_order_USDC_SOL_25.json", USDC, SOL)
        self.assertEqual((payload["feeMint"], payload["swapMode"], payload["router"]), (SOL.mint, "ExactIn", "metis"))
        self.assertIsNone(payload["taker"])
        route_out = sum(int(leg["swapInfo"]["outAmount"]) for leg in payload["routePlan"])
        fee = route_out * payload["feeBps"] // 10000
        # Evidence for "do not deduct the swap fee twice": outAmount = route output - fee.
        self.assertEqual(quote.out_amount, route_out - fee)
        self.assertEqual(payload["platformFee"]["feeBps"], payload["feeBps"])

    def test_jupiter_metis_quote_is_net_of_fee_even_when_fee_mint_is_the_input(self):
        payload, quote = self.jupiter("jupiter_order_SOL_USDC_0.1_metis.json", SOL, USDC)
        self.assertEqual((payload["feeMint"], payload["router"]), (SOL.mint, "metis"))  # fee labelled in input mint
        route_in = sum(int(leg["swapInfo"]["inAmount"]) for leg in payload["routePlan"])
        route_out = sum(int(leg["swapInfo"]["outAmount"]) for leg in payload["routePlan"])
        self.assertEqual(route_in, quote.request.amount)  # full input goes to the route
        # ...and the 2 bps come off the output: outAmount is still what is received.
        self.assertEqual(quote.out_amount, route_out - route_out * payload["feeBps"] // 10000)

    def test_jupiter_rfq_quote_with_input_side_fee(self):
        payload, quote = self.jupiter("jupiter_order_SOL_USDC_0.1.json", SOL, USDC)
        self.assertEqual((payload["feeMint"], payload["router"], payload["swapType"]), (SOL.mint, "jupiterz", "rfq"))
        self.assertTrue(payload["gasless"] and payload["guaranteedPrice"])
        # ExactIn: exactly inAmount is spent, so an input-side fee must come out of
        # it. The route still shows the full input; the split is not itemised.
        self.assertEqual(int(payload["routePlan"][0]["swapInfo"]["inAmount"]), quote.request.amount)
        self.assertEqual(int(payload["routePlan"][0]["swapInfo"]["outAmount"]), quote.out_amount)

    def test_no_expiry_field_and_no_network_fee_without_taker(self):
        for name in ("jupiter_order_USDC_SOL_25.json", "jupiter_order_SOL_USDC_0.1.json",
                     "jupiter_order_SOL_USDC_0.1_metis.json"):
            payload = json.loads((FIXTURES / name).read_bytes())
            with self.subTest(file=name):
                self.assertFalse({"expireAt", "expiresAt", "expiry", "lastValidBlockHeight"} & set(payload))
                self.assertEqual((payload["signatureFeeLamports"], payload["prioritizationFeeLamports"],
                                  payload["rentFeeLamports"]), (0, 0, 0))

    def test_jupiter_quote_with_transaction_would_still_be_refused(self):
        body, meta = captured("jupiter_order_USDC_SOL_25.json")
        payload = dict(json.loads(body), transaction="AQAB")
        request = QuoteRequest(USDC, SOL, 25_000_000)
        with self.assertRaises(Rejected):
            Quote.parse(request, payload, meta["requested_at"], meta["received_at"], "JUPITER_QUOTE")

    def test_solana_statuspage_parses_every_incident(self):
        body, meta = captured("solana_status_incidents.json")
        batch = NEWS_FEEDS["solana_status"]().parse(body, meta["requested_at"], meta["received_at"], meta["headers"])
        self.assertEqual((len(batch.items), batch.rejected, batch.duplicates), (30, 0, 0))
        self.assertTrue(all(item.url.startswith("https://") for item in batch.items))

    def test_jupiter_status_rss_with_minus_zero_zone(self):
        body, meta = captured("jupiter_status_feed.rss")
        batch = NEWS_FEEDS["jupiter_status"]().parse(body, meta["requested_at"], meta["received_at"], meta["headers"])
        self.assertEqual((len(batch.items), batch.rejected), (4, 0))  # all four were rejected before the fix


class RealResponsesThroughTheJournal(unittest.TestCase):
    def test_feed_updates_group_into_stories_with_first_publication(self):
        body, meta = captured("jupiter_status_feed.rss")
        bars, bars_meta = captured("binance_klines_SOLUSDC_1m.json")
        with tempfile.TemporaryDirectory() as directory:
            journal = Journal(Path(directory) / "j.db")
            try:
                now = [meta["received_at"]]
                fixed = iter([RawResponse(200, meta["headers"], body),
                              RawResponse(200, {}, bars)])  # headers dropped: replayed later than captured
                observe(journal, NEWS_FEEDS["jupiter_status"](), fetch=lambda url, endpoint: next(fixed),
                        clock=lambda: now[0])
                observe(journal, BinanceKlines(limit=5), fetch=lambda url, endpoint: next(fixed),
                        clock=lambda: now[0])
                snapshot = build_snapshot(journal, now[0] + 1, news_sources=["jupiter_status"])
            finally:
                journal.close()
        self.assertEqual(len(snapshot["news"]), 2)  # 4 update items -> 2 incidents
        by_title = {item["title"]: item for item in snapshot["news"]}
        parsing = by_title["Swap Program Events Parsing"]
        self.assertEqual(parsing["items"], 2)
        self.assertEqual(parsing["published_at"], 1758025140.0)  # 16 Sep 2025 12:19 UTC, the first update
        self.assertLess(parsing["published_at"], parsing["observed_at"])  # delayed publication kept as such

    def test_cloud_github_refusal_is_recorded_as_http_error(self):
        body, meta = captured("github_agave_releases_403_cloud_proxy.json")
        with tempfile.TemporaryDirectory() as directory:
            journal = Journal(Path(directory) / "j.db")
            try:
                with self.assertRaises(Rejected):
                    observe(journal, NEWS_FEEDS["agave_releases"](),
                            fetch=lambda url, endpoint: RawResponse(403, meta["headers"], body),
                            clock=lambda: meta["received_at"])
                row = journal.db.execute("SELECT outcome, http_status, body FROM fetches").fetchone()
                self.assertEqual((row[0], row[1], row[2]), ("HTTP_ERROR", 403, body))
                self.assertEqual(journal.db.execute("SELECT count(*) FROM news").fetchone()[0], 0)
            finally:
                journal.close()


class SampleAdapterUrl(unittest.TestCase):
    def test_live_quote_urls_had_no_taker(self):
        for name in ("jupiter_order_USDC_SOL_25.json", "jupiter_order_SOL_USDC_0.1.json"):
            self.assertNotIn("taker", META[name]["url"])
        adapter = JupiterQuoteSample(QuoteRequest(USDC, SOL, 25_000_000))
        self.assertEqual(set(adapter.params()), {"inputMint", "outputMint", "amount"})


if __name__ == "__main__":
    unittest.main()
