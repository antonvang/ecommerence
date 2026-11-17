"""Automatic decision -> quote -> paper fill, with an append-only decision trail."""
from __future__ import annotations

from .core import Quote, QuoteRequest, Rejected, SOL, USDC, analyse, timestamp

# A decision is only executable shortly after it was made. Without this bound a
# week-old snapshot could be "executed" at today's price.
MAX_DECISION_AGE = 60.0


def _journal_blocked(book, event, exc):
    try:
        book.decision(dict(event, event="BLOCKED", reason="%s: %s" % (type(exc).__name__, exc)))
    except Exception:
        pass  # The original error is the one that must surface.


def step(candles, news, book, quote_provider, as_of, execution_clock, max_decision_age=MAX_DECISION_AGE):
    decision = analyse(candles, news, as_of)
    as_of = timestamp(as_of)
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
        def require_current(now):
            age = timestamp(now) - as_of
            if not 0 <= age <= max_decision_age:
                raise Rejected("Decision is %.1f s old at execution; limit %.0f s" % (age, max_decision_age))

        require_current(execution_clock())
        quote = quote_provider(request)
        if not isinstance(quote, Quote) or quote.request != request or quote.started_at < as_of:
            raise Rejected("Quote predates or does not match the decision")
        now = execution_clock()
        require_current(now)
        # `expect`: another process must not have traded this account meanwhile.
        state = book.fill(quote, now=now, expect=state)
        book.decision(dict(event, event="PAPER_FILL", quote_id=quote.quote_id))
        return dict(event, execution="PAPER_FILLED", quote_id=quote.quote_id, account=state)
    except Exception as exc:
        # Every failure is journaled and re-raised; none becomes a fill.
        _journal_blocked(book, event, exc)
        raise
