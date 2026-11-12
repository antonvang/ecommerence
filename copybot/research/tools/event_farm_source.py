"""Director order 103 (ISOLATED DEVELOPMENT ONLY): the 5m kline source adapter for ForwardBookV2.

CONTRACT (nothing else is ever requested):
    GET https://fapi.binance.com/fapi/v1/klines?symbol=<BTCUSDT|ETHUSDT>&interval=5m&startTime=<ms>&limit=<3|499>
No other host, path or parameter, no API key or signed request, no account or order endpoint. `check_url` refuses
everything else, and every request passes it before the transport sees it.

NO CALL WITHOUT ACTIVATION. KlineSource needs an activation object whose approved(ACTION) is exactly True, and the only
transport that can reach the real host (HttpTransport with the real base) needs one as well. Nothing in the lab builds
such an object today. Tests use a loopback HTTP server or an injected transport together with a test activation.

FAIL-CLOSED. A transport error, timeout, HTTP status other than 200, invalid JSON, a malformed row, a duplicate or
unordered row, a row before startTime or a close time that is not open time + 299,999 ms rejects the WHOLE response
(no bar is delivered; the book then waits and, if needed, records a gap). A bar that has not closed (open + 300 s >
now or close time >= now) is dropped and fetched again later. 429/418 pause the adapter until Retry-After (at least 300
s). Revisions: each request starts at the LAST stored bar, so a changed value of that bar reaches the book's conflict
log. No backfill: nothing before `start_ts` (the activation slot) is ever requested.

CALL LOG. Every request (and every refusal before a request) is one JSON line appended to its own file
event_farm_source_calls*.jsonl, chained by the sha256 of the previous line; the chain is verified on open and a broken
chain refuses the adapter. Each line holds the time, endpoint and parameters, status, error, rows received, bars
delivered, bars dropped as unclosed, gaps inside the response, the response sha256 and, per delivered bar, the exact
open time [0], close time [6] and volume [5] as received.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ACTION = "event_farm_forward_source"
HOST = "fapi.binance.com"
BASE = "https://" + HOST
PATH = "/fapi/v1/klines"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
INTERVAL = "5m"
BAR_MS = 300_000
LIMITS = (3, 499)
TIMEOUT_S = 10.0
MIN_BACKOFF_S = 300
LOG_NAME = re.compile(r"^event_farm_source_calls[A-Za-z0-9_-]{0,48}\.jsonl$")
LOG_FORBIDDEN = ("/home/anton/ecommerence/", "lab.db", "pm_lp.db", "/quarantine", "quarantine/", "research/data",
                 "data/lab/", "/lab/market")
GENESIS = "0" * 64
PROVENANCE_SOURCE = "fapi_klines_5m"


class NotActivated(Exception):
    """No approving activation object: no request can be made."""


class ContractViolation(Exception):
    """A request outside the single allowed contract."""


class LogBroken(Exception):
    """The append-only call log is not intact."""


def _approved(activation):
    return activation is not None and callable(getattr(activation, "approved", None)) and \
        activation.approved(ACTION) is True


def build_url(symbol, start_ms, limit):
    url = f"{BASE}{PATH}?" + urllib.parse.urlencode(
        [("symbol", symbol), ("interval", INTERVAL), ("startTime", str(start_ms)), ("limit", str(limit))])
    check_url(url)
    return url


def check_url(url):
    """Refuse every URL except the contract. Returns the parsed parameters."""
    if not isinstance(url, str):
        raise ContractViolation("not a URL")
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.netloc != HOST or u.path != PATH or u.fragment or u.username or u.password:
        raise ContractViolation(f"only {BASE}{PATH} is allowed: {url!r}")
    q = urllib.parse.parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
    keys = [k for k, _ in q]
    if keys != ["symbol", "interval", "startTime", "limit"]:
        raise ContractViolation(f"parameters must be exactly symbol, interval, startTime, limit: {keys}")
    p = dict(q)
    if p["symbol"] not in SYMBOLS or p["interval"] != INTERVAL:
        raise ContractViolation("symbol must be BTCUSDT or ETHUSDT and interval 5m")
    if not p["startTime"].isdigit() or int(p["startTime"]) % BAR_MS or not p["limit"].isdigit() or \
            int(p["limit"]) not in LIMITS:
        raise ContractViolation("startTime must be on the 5m grid (ms) and limit 3 or 499")
    return {"symbol": p["symbol"], "startTime": int(p["startTime"]), "limit": int(p["limit"])}


class HttpTransport:
    """GET with a fixed timeout and no headers beyond a generic user agent. The real base needs an activation; the
    only other base allowed is a loopback test server (http://127.0.0.1:<port>), which gets the same path and query."""

    def __init__(self, base=BASE, activation=None, timeout=TIMEOUT_S):
        if base == BASE:
            if not _approved(activation):
                raise NotActivated("the real host needs an approving activation object")
        elif not re.match(r"^http://127\.0\.0\.1:\d{1,5}$", base or ""):
            raise ContractViolation("a transport base is the real host or a loopback test server")
        self.base, self.timeout = base, timeout

    def get(self, url):
        import urllib.error
        import urllib.request
        check_url(url)
        u = urllib.parse.urlsplit(url)
        target = self.base + u.path + "?" + u.query
        req = urllib.request.Request(target, method="GET", headers={"User-Agent": "research-client"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, dict(r.headers.items()), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers.items()) if e.headers else {}, e.read() if e.fp else b""


def check_log_path(path):
    if not isinstance(path, str) or not path:
        raise ContractViolation("no call-log path")
    norm = os.path.normpath(os.path.abspath(path))
    if any(f in norm.lower() for f in LOG_FORBIDDEN) or not LOG_NAME.match(os.path.basename(norm)):
        raise ContractViolation("call log must be event_farm_source_calls*.jsonl outside lab/pm_lp/data paths")
    return norm


def verify_log(path):
    """(lines, last hash). Raises LogBroken if a line does not chain to the previous one."""
    if not os.path.exists(path):
        return 0, GENESIS
    prev, n = GENESIS, 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            rec = json.loads(line)
            if rec.get("prev") != prev or rec.get("seq") != n:
                raise LogBroken(f"call log broken at line {n + 1}")
            prev, n = hashlib.sha256(line.encode()).hexdigest(), n + 1
    return n, prev


def _num(s):
    if isinstance(s, bool) or not isinstance(s, (str, int, float)):
        raise ValueError("not a number")
    v = float(s)
    if not math.isfinite(v):
        raise ValueError("not finite")
    return v


def parse_rows(body, start_ms, now_s):
    """(bars, kept_raw, dropped_unclosed, gaps) or raises ValueError for a response that must be rejected whole."""
    rows = json.loads(body.decode("utf-8"))
    if not isinstance(rows, list):
        raise ValueError("response is not a list")
    bars, raw, dropped, gaps, prev = [], [], 0, 0, None
    for r in rows:
        if not isinstance(r, list) or len(r) < 7 or isinstance(r[0], bool) or not isinstance(r[0], int) or \
                isinstance(r[6], bool) or not isinstance(r[6], int):
            raise ValueError("malformed row")
        o_ms, c_ms = r[0], r[6]
        if o_ms % BAR_MS or c_ms != o_ms + BAR_MS - 1:
            raise ValueError("open/close time off the 5m contract")
        if o_ms < start_ms:
            raise ValueError("row before startTime")
        if prev is not None and o_ms <= prev:
            raise ValueError("duplicate or unordered row")
        if prev is not None and o_ms > prev + BAR_MS:
            gaps += 1
        prev = o_ms
        o, h, l, c, v = (_num(x) for x in r[1:6])
        if v < 0 or h < max(o, c) or l > min(o, c):
            raise ValueError("invalid OHLCV")
        if o_ms // 1000 + 300 > now_s or c_ms >= now_s * 1000:
            dropped += 1                       # not closed yet: fetched again next time
            continue
        bars.append((o_ms // 1000, o, h, l, c, v))
        raw.append([o_ms, c_ms, r[5]])
    return bars, raw, dropped, gaps


class KlineSource:
    """The injected source for ForwardBookV2 (fetch(symbol, since_ts)). One request per call, at most."""

    def __init__(self, activation, start_ts, log_path, transport=None, clock=None, adapter_sha256=None):
        if not _approved(activation):
            raise NotActivated("the event farm source is not activated")
        if type(start_ts) is not int or start_ts % 300:
            raise ContractViolation("start_ts must be the activation slot on the 5m grid (s)")
        self.log_path = check_log_path(log_path)
        self.n, self.last = verify_log(self.log_path)
        self.transport = transport or HttpTransport(BASE, activation)
        self.clock = clock or time.time
        self.start_ts = start_ts
        self.backoff_until = 0.0
        self.provenance = {"source": PROVENANCE_SOURCE, "endpoint": f"GET {PATH}", "host": HOST, "interval": INTERVAL,
                           "start_ts": start_ts, "adapter_sha256": adapter_sha256 or file_sha256(__file__)}

    def _log(self, rec):
        rec = {"seq": self.n, "prev": self.last, **rec}
        line = json.dumps(rec, sort_keys=True, separators=(",", ":"))
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.n, self.last = self.n + 1, hashlib.sha256(line.encode()).hexdigest()

    def fetch(self, symbol, since_ts):
        now = self.clock()
        if symbol not in SYMBOLS:
            raise ContractViolation(f"symbol {symbol!r} is outside the contract")
        start = self.start_ts if since_ts is None else max(self.start_ts, int(since_ts))
        if start + 300 > now:
            return []                                              # nothing can have closed yet
        if now < self.backoff_until:
            self._log({"wall_ts": now, "symbol": symbol, "status": None, "error": "backoff", "rows": 0,
                       "delivered": 0, "endpoint": f"GET {PATH}"})
            return []
        missing = int((now - start) // 300) + 1
        limit = LIMITS[0] if missing <= LIMITS[0] else LIMITS[1]
        url = build_url(symbol, start * 1000, limit)
        rec = {"wall_ts": now, "symbol": symbol, "endpoint": f"GET {PATH}", "startTime": start * 1000, "limit": limit,
               "status": None, "error": None, "rows": 0, "delivered": 0, "dropped_unclosed": 0, "gaps": 0,
               "body_sha256": None, "bars": []}
        try:
            status, headers, body = self.transport.get(url)
        except Exception as e:                                     # timeout, refused connection, DNS failure
            rec["error"] = f"transport: {type(e).__name__}"
            self._log(rec)
            return []
        rec["status"] = status
        rec["body_sha256"] = hashlib.sha256(body or b"").hexdigest()
        if status in (418, 429):
            retry = headers.get("Retry-After") or headers.get("retry-after")
            wait = max(MIN_BACKOFF_S, int(retry) if str(retry or "").isdigit() else 0)
            self.backoff_until = now + wait
            rec["error"] = f"rate limited, pause {wait} s"
            self._log(rec)
            return []
        if status != 200:
            rec["error"] = "http status"
            self._log(rec)
            return []
        try:
            bars, raw, dropped, gaps = parse_rows(body, start * 1000, now)
            rec["rows"] = len(json.loads(body.decode("utf-8")))
        except (ValueError, UnicodeDecodeError) as e:
            rec["error"] = f"rejected: {e}"
            self._log(rec)
            return []
        rec.update(delivered=len(bars), dropped_unclosed=dropped, gaps=gaps, bars=raw)
        self._log(rec)
        return bars


def file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


__all__ = ["KlineSource", "HttpTransport", "build_url", "check_url", "parse_rows", "verify_log", "NotActivated",
           "ContractViolation", "LogBroken", "ACTION", "SYMBOLS"]
