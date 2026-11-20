"""Allowlisted HTTPS for execution: Jupiter and the mandate's own RPC host only.

No redirects, no cookies, no credentials of ours, a timeout and a body cap.
Error messages name the host, never the full URL (an RPC URL can carry an API key).
"""
from __future__ import annotations

import http.client
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from ..core import Rejected, strict_json
from ..jupiter import NoRedirect

MAX_BODY = 4_000_000
USER_AGENT = "jupiter-bot-execution/0.3"


class TransportError(Rejected):
    """No usable HTTP response (connection failed, reset, unreadable)."""


class TransportTimeout(TransportError):
    """The request may or may not have reached the server."""


def urllib_transport(method, url, body, headers, timeout):
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        try:
            # ProxyHandler({}): ignore HTTPS_PROXY & co. from the environment (F16)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
            with opener.open(request, timeout=timeout) as response:
                return response.status, response.read(MAX_BODY + 1)
        except urllib.error.HTTPError as exc:
            return exc.code, (exc.read(MAX_BODY + 1) if exc.fp is not None else b"")
    except Rejected:
        raise
    except (socket.timeout, TimeoutError) as exc:
        raise TransportTimeout("timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise TransportTimeout("timeout") from exc
        raise TransportError("connection failed: %s" % type(exc.reason).__name__) from exc
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise TransportError("request failed: %s" % type(exc).__name__) from exc


class SafeHTTP:
    """`transport(method, url, body, headers, timeout) -> (status, body bytes)` behind an allowlist."""

    def __init__(self, allowed_hosts, transport=urllib_transport, timeout=15.0):
        self.allowed = frozenset(h.lower() for h in allowed_hosts if h)
        self.transport, self.timeout = transport, timeout

    def _check(self, url):
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or host not in self.allowed or parts.username or parts.fragment:
            raise Rejected("Non-allowlisted endpoint (%s)" % (host or "?"))
        return host

    def request(self, method, url, payload=None, timeout=None):
        """(status, parsed JSON or None). JSON is parsed strictly; non-JSON gives None."""
        host = self._check(url)
        if method not in ("GET", "POST"):
            raise Rejected("Method not allowed")
        body = None
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
            headers["Content-Type"] = "application/json"
        try:
            status, raw = self.transport(method, url, body, headers, timeout or self.timeout)
        except TransportError:
            raise
        except Rejected:
            raise
        except Exception as exc:  # a transport seam must not leak odd exceptions upward
            raise TransportError("request to %s failed: %s" % (host, type(exc).__name__)) from exc
        if len(raw) > MAX_BODY:
            raise TransportError("response from %s larger than %d bytes" % (host, MAX_BODY))
        try:
            parsed = strict_json(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, ValueError):
            parsed = None
        return status, parsed
