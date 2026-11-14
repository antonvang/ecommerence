"""Forward positioning/liquidation collector (research/tools/fapi_collector.py, amendment 49): fixed URL allowlist,
no backfill, first value kept, websocket framing, liquidation parsing, ping answered. No network: fake transports."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from research.tools import fapi_collector as fc  # noqa: E402

START = 1_800_000_000


class Urls(unittest.TestCase):
    def test_allowlist(self):
        fc.check_url("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT")
        fc.check_url("https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=ETHUSDT&period=5m&limit=2")
        fc.check_url("wss://fstream.binance.com/market/ws/!forceOrder@arr")
        fc.check_url("https://fapi.binance.com/fapi/v1/klines?symbol=SOLUSDT&interval=5m&limit=2")
        for bad in ("https://api.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",
                    "https://fapi.binance.com/fapi/v1/order?symbol=BTCUSDT",
                    "https://fapi.binance.com/fapi/v2/account",
                    "https://fapi.binance.com/fapi/v1/openInterest?symbol=PEPEUSDT",
                    "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=500",
                    "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=2&startTime=1",
                    "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT&signature=x",
                    "http://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",
                    "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=2",
                    "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=1500",
                    "wss://fstream.binance.com/ws/!forceOrder@arr", "wss://fstream.binance.com/market/ws/btcusdt@aggTrade",
                    "wss://evil.example/market/ws/!forceOrder@arr"):
            with self.assertRaises(fc.UrlRefused, msg=bad):
                fc.check_url(bad)


class Poll(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = fc.open_db(os.path.join(self.d, "p.db"))
        self.urls = []

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.d)

    def fake(self, url):
        fc.check_url(url)
        self.urls.append(url)
        if "/fapi/v1/klines" in url:
            k = [[(START - 300) * 1000, "1", "2", "0.5", "1.5", "10", START * 1000 - 1],
                 [START * 1000, "1.5", "2", "1", "1.8", "11", (START + 300) * 1000 - 1],
                 [(START + 300) * 1000, "1.8", "2", "1", "1.9", "3", (START + 600) * 1000 - 1]]   # last one open
            return 200, json.dumps(k).encode()
        if "/fapi/v1/openInterest" in url:
            return 200, json.dumps({"symbol": "X", "openInterest": "123.4", "time": (START + 60) * 1000}).encode()
        rows = [{"timestamp": (START - 300) * 1000, "v": "old"}, {"timestamp": START * 1000, "v": "new"}]
        return 200, json.dumps(rows).encode()

    def test_one_slot_no_backfill_first_value_kept(self):
        ins, calls, fails = fc.poll_once(self.db, START + 301, self.fake, start=START)   # bar START closed
        self.assertEqual((calls, fails), (60, 0))
        self.assertEqual(ins, 10 + 10 + 40)                    # rows before START and the open bar are discarded
        self.assertEqual(self.db.execute("SELECT ts FROM positioning WHERE metric = 'kline'").fetchall()[0], (START,))
        self.assertEqual(self.db.execute("SELECT MIN(ts) FROM positioning").fetchone()[0], START)
        again, _, _ = fc.poll_once(self.db, START + 361, self.fake, start=START)
        self.assertEqual(again, 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM calls WHERE status = 200").fetchone()[0], 120)
        self.assertTrue(all(u.startswith("https://fapi.binance.com/") for u in self.urls))

    def test_errors_logged_and_unreachable_host_stops_early(self):
        def down(url):
            raise OSError("no route")
        ins, calls, fails = fc.poll_once(self.db, START, down, start=START)
        self.assertEqual((ins, calls, fails), (0, 6, 6))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM calls WHERE status = -1").fetchone()[0], 6)

    def test_start_ts_is_the_first_start(self):
        self.assertEqual(fc.start_ts(self.db, 100.0), 100.0)
        self.assertEqual(fc.start_ts(self.db, 999.0), 100.0)


class FakeSock:
    def __init__(self, data):
        self.buf, self.sent = data, b""

    def recv(self, n):
        if not self.buf:
            raise socket.timeout()
        c, self.buf = self.buf[:n], self.buf[n:]
        return c

    def sendall(self, b):
        self.sent += b

    def settimeout(self, t):
        pass

    def close(self):
        pass


def liq(sym, e_ms):
    return json.dumps({"e": "forceOrder", "E": e_ms, "o": {"s": sym, "S": "SELL", "o": "LIMIT", "f": "IOC", "q": "0.5",
                                                          "p": "60000", "ap": "60010", "X": "FILLED", "l": "0.5",
                                                          "z": "0.5", "T": e_ms - 5}}).encode()


class Ws(unittest.TestCase):
    def test_frames_roundtrip_and_fragments(self):
        big = b"x" * 70000
        op, p = fc.ws_read(FakeSock(fc.ws_frame(big, 1, mask=True)))
        self.assertEqual((op, p), (1, big))
        f1 = bytes([0x01, 3]) + b"abc"                        # text, not final
        f2 = bytes([0x80, 2]) + b"de"                         # continuation, final
        self.assertEqual(fc.ws_read(FakeSock(f1 + f2)), (1, b"abcde"))

    def test_loop_stores_liquidations_answers_ping_skips_before_start(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        db = fc.open_db(os.path.join(d, "p.db"))
        stop = threading.Event()
        data = (fc.ws_frame(liq("BTCUSDT", (START + 5) * 1000), mask=False) + bytes([0x89, 2]) + b"hi" +
                fc.ws_frame(liq("BTCUSD_PERP", (START + 6) * 1000), mask=False) +
                fc.ws_frame(liq("ETHUSD_270326", (START + 7) * 1000), mask=False) +
                fc.ws_frame(liq("ETHUSDT", (START - 5) * 1000), mask=False) +
                fc.ws_frame(json.dumps({"e": "other"}).encode(), mask=False))
        socks = []

        def connect():
            if socks:
                stop.set()
                raise ConnectionError("done")
            socks.append(FakeSock(data))
            return socks[0]

        ticks = iter(range(10 ** 6))

        def clock():
            t = next(ticks)
            if t > 40:
                stop.set()
            return START + t

        fc.ws_loop(db, threading.Lock(), START, stop, connect=connect, clock=clock)
        rows = db.execute("SELECT symbol, side, qty, avg_price FROM liquidations").fetchall()
        self.assertEqual(rows, [("BTCUSDT", "SELL", 0.5, 60010.0)])
        self.assertEqual(db.execute("SELECT v FROM meta WHERE k = 'coinm_dropped'").fetchone(), ('2',))
        pong = socks[0].sent
        self.assertEqual(pong[0], 0x8A)                       # pong frame with the ping payload (masked)
        db.close()


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401
    unittest.main()
