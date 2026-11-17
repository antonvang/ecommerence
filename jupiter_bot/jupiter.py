"""Public, quote-only Jupiter transport. No wallet, credentials or POST."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .core import Quote, Rejected, reject_json_constant


ENDPOINT = "https://api.jup.ag/swap/v2/order"
MAX_RESPONSE = 1_000_000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise Rejected("Redirect rejected; no alternate endpoint is allowed")


def public_get(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "api.jup.ag" or parsed.path != "/swap/v2/order":
        raise Rejected("Non-allowlisted endpoint")
    query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
    if set(query) != {"inputMint", "outputMint", "amount"} or any(len(v) != 1 for v in query.values()):
        raise Rejected("Only three public quote parameters are allowed")
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                  "User-Agent": "jupiter-bot-prototype/0.1"}, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            if response.status != 200:
                raise Rejected("Quote HTTP status %s" % response.status)
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise Rejected("Quote response too large")
            return json.loads(raw, parse_constant=reject_json_constant)
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After", "unknown") if exc.headers else "unknown"
        raise Rejected("Quote HTTP %s; no retry; Retry-After=%s" % (exc.code, retry_after)) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError) as exc:
        raise Rejected("Quote request failed: %s" % type(exc).__name__) from exc


class JupiterQuotes:
    def __init__(self, fetch=public_get, clock=time.time, monotonic=time.monotonic, sleep=time.sleep):
        self.fetch, self.clock, self.monotonic, self.sleep = fetch, clock, monotonic, sleep
        self._last_started = None
        self._lock = threading.Lock()

    def quote(self, request):
        # Hold the lock through the request: no parallel calls from this client.
        with self._lock:
            if self._last_started is not None:
                delay = 2.1 - (self.monotonic() - self._last_started)
                if delay > 0:
                    self.sleep(delay)
            self._last_started = self.monotonic()
            start = self.clock()
            payload = self.fetch(ENDPOINT + "?" + urllib.parse.urlencode(request.params()))
            return Quote.parse(request, payload, start, self.clock())
