"""One observation: reserve -> fetch -> parse -> journal. No loop, no daemon.

Every path writes exactly one `fetches` row. Failures are recorded and then
raised as `Rejected`; they never produce an observation or a fallback value.
"""
from __future__ import annotations

import email.utils
import time

from ..core import Rejected
from .transport import build_url, https_get

MAX_RETRY_AFTER = 86400.0


def retry_after(headers, received_at):
    value = (headers or {}).get("retry-after")
    if value is None:
        return None
    value = value.strip()
    if value.isascii() and value.isdigit():
        seconds = float(value)
    else:
        try:
            seconds = email.utils.parsedate_to_datetime(value).timestamp() - received_at
        except (TypeError, ValueError, IndexError, AttributeError):
            return None
    return min(max(seconds, 1.0), MAX_RETRY_AFTER)


def observe(journal, adapter, fetch=https_get, clock=time.time):
    url = build_url(adapter.endpoint, adapter.params())
    journal.reserve(adapter, url, clock())
    requested_at = clock()
    try:
        response = fetch(url, adapter.endpoint)
    except Rejected as exc:
        journal.record(adapter, url, requested_at, None, None, "TRANSPORT_ERROR", error=str(exc),
                       penalty_until=requested_at + adapter.default_cooldown)
        raise
    received_at = clock()
    if response.status in (418, 429):
        wait = retry_after(response.headers, received_at)
        if wait is None:
            wait = adapter.ban_cooldown if response.status == 418 else adapter.default_cooldown
        error = "HTTP %d from %s; backing off %.0f s" % (response.status, adapter.source, wait)
        journal.record(adapter, url, requested_at, received_at, response, "RATE_LIMITED",
                       error=error, penalty_until=received_at + wait)
        raise Rejected(error)
    if response.status != 200:
        error = "HTTP %d from %s" % (response.status, adapter.source)
        penalty = received_at + adapter.default_cooldown if response.status >= 500 else None
        journal.record(adapter, url, requested_at, received_at, response, "HTTP_ERROR",
                       error=error, penalty_until=penalty)
        raise Rejected(error)
    try:
        batch = adapter.parse(response.body, requested_at, received_at, response.headers)
    except Exception as exc:
        error = "%s: %s" % (type(exc).__name__, exc)
        journal.record(adapter, url, requested_at, received_at, response, "PARSE_ERROR", error=error)
        raise Rejected("Unparseable response from %s: %s" % (adapter.source, error)) from exc
    return journal.record(adapter, url, requested_at, received_at, response, "OK", batch=batch)
