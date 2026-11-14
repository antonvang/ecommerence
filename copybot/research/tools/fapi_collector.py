"""Forward collector of Binance public positioning and liquidations (PROTOCOL_V3 amendment 49, gate G32).

Streams (research/desk/stream_registry.json):
- fwd_bn_positioning: every 5 min (slot + 40 s), for 10 fixed USDT perps, public GET on fapi.binance.com
  (amendment 49b adds /fapi/v1/klines interval=5m limit=2, closed bars only):
  /fapi/v1/openInterest, /futures/data/openInterestHist, /futures/data/takerlongshortRatio,
  /futures/data/globalLongShortAccountRatio, /futures/data/topLongShortPositionRatio (period 5m, limit 2);
- fwd_bn_liquidations: the public websocket wss://fstream.binance.com/market/ws/!forceOrder@arr (amendment 49a).

Rules: every URL is checked against a fixed allowlist before the call (check_url); no key, no order or account
endpoint; no backfill (rows with a timestamp before the collector's first start are discarded); first value per
(symbol, metric, ts) is kept; own database ~/fapi_collector/positioning.db. A STOP file in the home stops the loop.
The owner installs the systemd unit (research/ops/fapi_collector/INSTALL.md). Data only; kun papir og forskning.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import socket
import sqlite3
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~/fapi_collector")
REST_HOST = "fapi.binance.com"
WS_HOST = "fstream.binance.com"
WS_PATH = "/market/ws/!forceOrder@arr"            # routed path (amendment 49a); /ws/ is retired
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT",
           "LTCUSDT")
HIST = {"oi_hist": "/futures/data/openInterestHist", "taker": "/futures/data/takerlongshortRatio",
        "global_ls": "/futures/data/globalLongShortAccountRatio", "top_ls": "/futures/data/topLongShortPositionRatio"}
OI_NOW = "/fapi/v1/openInterest"
KLINES = "/fapi/v1/klines"                          # amendment 49b: closed 5m bars (price for outcomes)
ALLOWED_PATHS = {OI_NOW: {"symbol"}, KLINES: {"symbol", "interval", "limit"},
                 **{p: {"symbol", "period", "limit"} for p in HIST.values()}}
SLOT, OFFSET = 300, 40
USDM = re.compile(r"^[^_\s]+(USDT|USDC)$")              # amendment 49c: USDⓈ-M only; COIN-M (XXXUSD_PERP, _YYMMDD) dropped
UA = "copybot-research/1.0"


class UrlRefused(Exception):
    pass


def check_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme == "wss":
        if u.netloc != WS_HOST or u.path != WS_PATH or u.query or u.fragment:
            raise UrlRefused(f"websocket url not allowed: {url}")
        return
    if u.scheme != "https" or u.netloc != REST_HOST or u.path not in ALLOWED_PATHS or u.fragment:
        raise UrlRefused(f"url not allowed: {url}")
    q = urllib.parse.parse_qs(u.query, strict_parsing=True)
    if set(q) - ALLOWED_PATHS[u.path] or any(len(v) != 1 for v in q.values()):
        raise UrlRefused(f"query not allowed: {url}")
    if q.get("symbol", [None])[0] not in SYMBOLS:
        raise UrlRefused(f"symbol not allowed: {url}")
    if "period" in q and q["period"] != ["5m"] or "interval" in q and q["interval"] != ["5m"] or \
            "limit" in q and q["limit"] != ["2"]:
        raise UrlRefused(f"period/limit not allowed: {url}")


def http_get(url, timeout=15):
    check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS positioning (symbol TEXT, metric TEXT, ts INTEGER, data TEXT, fetched_ts REAL,
    PRIMARY KEY (symbol, metric, ts));
CREATE TABLE IF NOT EXISTS oi_now (symbol TEXT, ts INTEGER, open_interest REAL, fetched_ts REAL,
    PRIMARY KEY (symbol, ts));
CREATE TABLE IF NOT EXISTS liquidations (event_ms INTEGER, trade_ms INTEGER, symbol TEXT, side TEXT, otype TEXT,
    qty REAL, price REAL, avg_price REAL, status TEXT, filled_qty REAL, recv_ts REAL, raw TEXT);
CREATE INDEX IF NOT EXISTS liq_sym_ts ON liquidations (symbol, event_ms);
CREATE TABLE IF NOT EXISTS calls (ts REAL, kind TEXT, target TEXT, status INTEGER, ms INTEGER, rows INTEGER,
    error TEXT);
"""


def open_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=30, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def start_ts(db, now):
    row = db.execute("SELECT v FROM meta WHERE k = 'start_ts'").fetchone()
    if row:
        return float(row[0])
    db.execute("INSERT INTO meta VALUES ('start_ts', ?)", (repr(now),))
    db.commit()
    return now


def log_call(db, kind, target, status, ms, rows, error=None):
    db.execute("INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?)",
               (time.time(), kind, target, status, ms, rows, error))


def poll_once(db, now, get=http_get, start=None, lock=None):
    """One slot: OI now + 4 history endpoints for every symbol. Returns (inserted, calls, failures)."""
    start = start_ts(db, now) if start is None else start
    lock = lock or threading.Lock()
    ins = calls = fails = 0
    for s in SYMBOLS:
        jobs = [("oi_now", f"https://{REST_HOST}{OI_NOW}?symbol={s}"),
                ("kline", f"https://{REST_HOST}{KLINES}?symbol={s}&interval=5m&limit=2")] + \
               [(m, f"https://{REST_HOST}{p}?symbol={s}&period=5m&limit=2") for m, p in HIST.items()]
        for metric, url in jobs:
            t0 = time.time()
            calls += 1
            try:
                status, body = get(url)
                rows = json.loads(body) if status == 200 else None
            except Exception as e:                              # noqa: BLE001 - logged, next call
                with lock:
                    log_call(db, "rest", f"{metric}:{s}", -1, int(1000 * (time.time() - t0)), 0,
                             f"{type(e).__name__}: {e}"[:300])
                fails += 1
                continue
            n = 0
            with lock:
                if status != 200:
                    fails += 1
                elif metric == "kline":
                    for r in rows:
                        ts, close_ms = int(r[0]) // 1000, int(r[6])
                        if ts < start or close_ms >= now * 1000:          # no backfill, no open bar
                            continue
                        n += db.execute("INSERT OR IGNORE INTO positioning VALUES (?, ?, ?, ?, ?)",
                                        (s, metric, ts, json.dumps(r[:7]), now)).rowcount
                elif metric == "oi_now":
                    ts = int(rows["time"]) // 1000
                    if ts >= start:
                        n += db.execute("INSERT OR IGNORE INTO oi_now VALUES (?, ?, ?, ?)",
                                        (s, ts, float(rows["openInterest"]), now)).rowcount
                else:
                    for r in rows:
                        ts = int(r["timestamp"]) // 1000
                        if ts < start:
                            continue
                        n += db.execute("INSERT OR IGNORE INTO positioning VALUES (?, ?, ?, ?, ?)",
                                        (s, metric, ts, json.dumps(r, sort_keys=True), now)).rowcount
                log_call(db, "rest", f"{metric}:{s}", status, int(1000 * (time.time() - t0)), n,
                         None if status == 200 else body[:200].decode("utf-8", "replace"))
            ins += n
        if fails >= 5 and calls == fails:                       # host unreachable: do not hammer
            break
    with lock:
        db.commit()
    return ins, calls, fails


# ------------------------------------------------------------------------------------------------ websocket
def ws_frame(payload, opcode=1, mask=True):
    b = bytearray([0x80 | opcode])
    n = len(payload)
    m = 0x80 if mask else 0
    if n < 126:
        b.append(m | n)
    elif n < 65536:
        b += bytes([m | 126]) + struct.pack(">H", n)
    else:
        b += bytes([m | 127]) + struct.pack(">Q", n)
    if mask:
        key = os.urandom(4)
        b += key + bytes(c ^ key[i % 4] for i, c in enumerate(payload))
    else:
        b += payload
    return bytes(b)


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except socket.timeout:
            if not buf:
                raise
            continue                                            # never drop the rest of a started frame
        if not chunk:
            raise ConnectionError("websocket closed")
        buf += chunk
    return buf


def ws_read(sock):
    """(opcode, payload) of one complete message (continuation frames joined)."""
    data, first_op = b"", None
    while True:
        h1, h2 = _recv_exact(sock, 2)
        fin, op = h1 & 0x80, h1 & 0x0F
        n = h2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", _recv_exact(sock, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", _recv_exact(sock, 8))[0]
        key = _recv_exact(sock, 4) if h2 & 0x80 else None
        p = _recv_exact(sock, n)
        if key:
            p = bytes(c ^ key[i % 4] for i, c in enumerate(p))
        if op >= 8:                                             # control frames are never fragmented
            return op, p
        first_op = op if first_op is None else first_op
        data += p
        if fin:
            return first_op, data


def ws_connect(timeout=30):
    check_url(f"wss://{WS_HOST}{WS_PATH}")
    raw = socket.create_connection((WS_HOST, 443), timeout=timeout)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=WS_HOST)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((f"GET {WS_PATH} HTTP/1.1\r\nHost: {WS_HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: {UA}\r\n\r\n").encode())
    head = b""
    while b"\r\n\r\n" not in head:
        c = sock.recv(1)
        if not c:
            raise ConnectionError("handshake closed")
        head += c
        if len(head) > 8192:
            raise ConnectionError("handshake too long")
    if b" 101 " not in head.split(b"\r\n", 1)[0]:
        raise ConnectionError(f"handshake refused: {head[:80]!r}")
    return sock


def store_liquidation(db, msg, recv_ts, start):
    e = json.loads(msg)
    o = e.get("o") or {}
    if e.get("e") != "forceOrder" or o.get("s") is None:
        return 0
    if not USDM.match(o["s"]):                                  # COIN-M contracts: never stored (G09 until 11-28)
        return -1
    if int(e["E"]) // 1000 < start:
        return 0
    db.execute("INSERT INTO liquidations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (int(e["E"]), int(o.get("T") or 0), o["s"], o.get("S"), o.get("o"), float(o.get("q") or 0),
                float(o.get("p") or 0), float(o.get("ap") or 0), o.get("X"), float(o.get("z") or 0), recv_ts,
                json.dumps(e, sort_keys=True)))
    return 1


def ws_loop(db, lock, start, stop, connect=ws_connect, clock=time.time, max_age=23 * 3600):
    """Read liquidations until stop is set; reconnect with backoff; reconnect before Binance's 24 h limit."""
    backoff = 5
    while not stop.is_set():
        t0 = clock()
        try:
            sock = connect()
            with lock:
                log_call(db, "ws", "connect", 101, 0, 0)
                db.commit()
            backoff = 5
            sock.settimeout(60)
            n, last_commit = 0, clock()
            while not stop.is_set() and clock() - t0 < max_age:
                try:
                    op, p = ws_read(sock)
                except socket.timeout:
                    continue
                if op == 9:
                    sock.sendall(ws_frame(p, 10))
                elif op == 8:
                    raise ConnectionError("server closed")
                elif op == 1:
                    with lock:
                        r = store_liquidation(db, p.decode("utf-8"), clock(), start)
                        n += max(r, 0)
                        if r < 0:
                            db.execute("INSERT OR REPLACE INTO meta VALUES ('coinm_dropped', CAST(COALESCE((SELECT v "
                                       "FROM meta WHERE k = 'coinm_dropped'), 0) AS INTEGER) + 1)")
                        if clock() - last_commit > 10:
                            db.commit()
                            last_commit = clock()
            try:
                sock.sendall(ws_frame(b"", 8))
                sock.close()
            except OSError:
                pass
        except Exception as e:                                  # noqa: BLE001 - logged, reconnect
            with lock:
                log_call(db, "ws", "error", -1, int(1000 * (clock() - t0)), 0, f"{type(e).__name__}: {e}"[:300])
                db.commit()
            stop.wait(backoff)
            backoff = min(300, backoff * 2)
        finally:
            with lock:
                db.commit()


# ------------------------------------------------------------------------------------------------ run
def write_status(home, rec):
    p = os.path.join(home, "status.json")
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(rec, f, sort_keys=True)
    os.replace(p + ".tmp", p)


def counts(db):
    return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("positioning", "oi_now", "liquidations", "calls")}


def run(home=HOME, once=False, ws_seconds=0, get=http_get):
    db = open_db(os.path.join(home, "positioning.db"))
    lock = threading.Lock()
    start = start_ts(db, time.time())
    stop = threading.Event()
    th = None
    if not once or ws_seconds:
        th = threading.Thread(target=ws_loop, args=(db, lock, start, stop), daemon=True)
        th.start()
    try:
        while True:
            if os.path.exists(os.path.join(home, "STOP")):
                print("STOP file present", flush=True)
                break
            if not once:
                now = time.time()
                nxt = (now // SLOT + 1) * SLOT + OFFSET
                if nxt - now > SLOT:
                    nxt -= SLOT
                time.sleep(max(0.0, nxt - now))
            ins, calls, fails = poll_once(db, time.time(), get, start, lock)
            with lock:
                c = counts(db)
            write_status(home, {"ts": time.time(), "start_ts": start, "last_slot": {"inserted": ins, "calls": calls,
                                                                                    "failures": fails}, "counts": c})
            print(json.dumps({"ts": round(time.time(), 1), "inserted": ins, "calls": calls, "failures": fails,
                              **c}), flush=True)
            if once:
                if ws_seconds:
                    time.sleep(ws_seconds)
                break
    finally:
        stop.set()
        if th:
            th.join(timeout=10)
        with lock:
            db.commit()
            print(json.dumps({"final": counts(db)}), flush=True)
        db.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="forward positioning + liquidation collector (PROTOCOL_V3 amendment 49)")
    ap.add_argument("cmd", choices=["run", "once", "status"])
    ap.add_argument("--home", default=HOME)
    ap.add_argument("--ws-seconds", type=int, default=0, help="with once: also listen to liquidations this long")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        db = open_db(os.path.join(a.home, "positioning.db"))
        print(json.dumps(counts(db)))
        return 0
    return run(a.home, once=a.cmd == "once", ws_seconds=a.ws_seconds)


if __name__ == "__main__":
    sys.exit(main())
