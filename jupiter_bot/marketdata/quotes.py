"""Jupiter quote samples as observations: executable price for one fixed size.

This is the execution venue's own price, so it is the primary source for what
a swap would have returned. It is quote-only (no `taker`, no transaction) and
is never booked as a fill.
"""
from __future__ import annotations

from ..core import Quote, QuoteRequest, Rejected, strict_json
from .transport import Endpoint


class JupiterQuoteSample:
    kind = "quote"
    source = "jupiter_quote"
    endpoint = Endpoint("api.jup.ag", "/swap/v2/order", frozenset({"inputMint", "outputMint", "amount"}))
    min_interval = 2.1        # keyless budget is reported as 0.5 RPS; see DATA_SOURCES.md
    default_cooldown = 60.0
    ban_cooldown = 900.0

    def __init__(self, request):
        if not isinstance(request, QuoteRequest):
            raise Rejected("A QuoteRequest is required")
        self.request = request
        self.instrument = "%s/%s" % (request.input_asset.symbol, request.output_asset.symbol)

    def params(self):
        return self.request.params()

    def parse(self, body, requested_at, received_at, headers):
        return Quote.parse(self.request, strict_json(body), requested_at, received_at, "JUPITER_QUOTE")
