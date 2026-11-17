"""Keyless, allowlisted HTTPS GET that returns the raw bytes for the journal.

No credentials, cookies, POST or redirects. Each adapter names one exact host,
path and set of query parameters; anything else is refused before the network.
"""
from __future__ import annotations

import http.client
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ..core import Rejected
from ..jupiter import NoRedirect

MAX_BODY = 2_000_000
TIMEOUT = 10
USER_AGENT = "jupiter-bot-research/0.2"
# Response headers worth keeping as evidence (clock, rate limits, caching).
KEEP_HEADERS = ("date", "retry-after", "content-type", "etag", "last-modified",
                "x-mbx-used-weight-1m")


class TransportError(Rejected):
    """The request did not produce an HTTP response."""


@dataclass(frozen=True)
class Endpoint:
    host: str
    path: str
    params: frozenset = frozenset()
    accept: str = "application/json"


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: dict
    body: bytes


def build_url(endpoint, params=None):
    query = urllib.parse.urlencode(sorted((params or {}).items()))
    url = "https://%s%s%s" % (endpoint.host, endpoint.path, "?" + query if query else "")
    check_url(url, endpoint)
    return url


def check_url(url, endpoint):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != endpoint.host or parsed.path != endpoint.path
            or parsed.fragment or parsed.username or parsed.password):
        raise Rejected("Non-allowlisted endpoint")
    query = urllib.parse.parse_qs(parsed.query, strict_parsing=True) if parsed.query else {}
    if not set(query) <= endpoint.params or any(len(values) != 1 for values in query.values()):
        raise Rejected("Query parameters outside the adapter allowlist")


def _headers(source):
    if not source:
        return {}
    return {name: source.get(name) for name in KEEP_HEADERS if source.get(name) is not None}


def https_get(url, endpoint):
    check_url(url, endpoint)
    request = urllib.request.Request(url, method="GET", headers={
        "Accept": endpoint.accept, "User-Agent": USER_AGENT})
    try:
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT) as response:
                status, headers, body = response.status, _headers(response.headers), response.read(MAX_BODY + 1)
        except urllib.error.HTTPError as exc:
            # Keep error bodies too: they are evidence of what the source said.
            status, headers = exc.code, _headers(exc.headers)
            body = exc.read(MAX_BODY + 1) if exc.fp is not None else b""
    except Rejected:
        raise
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise TransportError("Request failed: %s" % type(exc).__name__) from exc
    if len(body) > MAX_BODY:
        raise TransportError("Response larger than %d bytes" % MAX_BODY)
    return RawResponse(status, headers, body)
