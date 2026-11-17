"""Automatic decision -> quote -> paper fill, with an append-only decision trail."""
from __future__ import annotations

from .core import QuoteRequest, Rejected, SOL, USDC, analyse


def step(candles, news, book, quote_provider, as_of, execution_clock):
    decision = analyse(candles, news, as_of)
    state = book.state()
    request = None
    if decision["action"] == "BUY" and state["sol"] == 0:
        amount = min(book.limits.max_buy_usdc,
                     book.limits.max_position_cost_usdc - book.limits.network_fee_usdc,
                     state["usdc"] - book.limits.network_fee_usdc)
        if amount > 0:
            request = QuoteRequest(USDC, SOL, amount)
    elif decision["action"] == "SELL" and state["sol"] > 0:
        request = QuoteRequest(SOL, USDC, state["sol"])
    event = dict(decision, event="DECISION", order_requested=request is not None)
    book.decision(event)
    if request is None:
        return dict(event, execution="NO_ORDER", account=state)
    try:
        quote = quote_provider(request)
        if quote.request != request or quote.started_at < as_of:
            raise Rejected("Quote predates or does not match the decision")
        state = book.fill(quote, now=execution_clock())
        book.decision(dict(event, event="PAPER_FILL", quote_id=quote.quote_id))
        return dict(event, execution="PAPER_FILLED", quote_id=quote.quote_id, account=state)
    except Rejected as exc:
        book.decision(dict(event, event="BLOCKED", reason=str(exc)))
        raise
