"""Director order 103: the 5m kline source adapter, tested ONLY against a fake HTTP server on loopback (127.0.0.1) or an
injected transport, with a test activation object. No real request is ever made; the protected loader blocks
everything except loopback anyway. Bars are synthetic."""
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_filters as ff  # noqa: E402
from research.tools import event_farm_forward as fw  # noqa: E402
from research.tools import event_farm_forward_v2 as fv  # noqa: E402
from research.tools import event_farm_source as src  # noqa: E402

BS = 300
T0 = ef.START
SYMS = list(src.SYMBOLS)


class Act:
    def __init__(self, v=True):
        self.v = v

    def approved(self, action):
        return self.v


def truth(days=2):
    """Synthetic 'exchange' bars for BTCUSDT and ETHUSDT (random walks; nothing real)."""
    return {"BTCUSDT": ef.random_walk_bars(61, days), "ETHUSDT": ef.random_walk_bars(62, days, price=3000.0)}


class FakeExchange:
    """A loopback HTTP server answering GET /fapi/v1/klines like the contract: closed bars from startTime, plus the
    forming bar with partial data when it has started. Faults can be injected per request."""

    def __init__(self, bars, now):
        self.bars, self.now, self.faults, self.requests, self.hidden = bars, now, [], [], set()
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                outer.requests.append((u.path, q))
                fault = outer.faults.pop(0) if outer.faults else None
                if fault == "sleep":
                    time.sleep(0.6)
                if isinstance(fault, int):
                    self.send_response(fault)
                    self.send_header("Retry-After", "600")
                    self.end_headers()
                    return
                body = outer.body(q, fault)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):        # the client gave up (timeout test)
                    pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def rows(self, sym, start_ms, limit):
        out, now = [], self.now[0]
        for b in self.bars[sym]:
            ms = b[0] * 1000
            if ms < start_ms or b[0] in self.hidden:
                continue
            if b[0] + BS <= now:
                out.append([ms, repr(b[1]), repr(b[2]), repr(b[3]), repr(b[4]), repr(b[5]), ms + 299_999, "0", 1, "0",
                            "0", "0"])
            elif b[0] <= now:                                         # the forming bar, partial data
                out.append([ms, repr(b[1]), repr(b[1]), repr(b[1]), repr(b[1]), "0.5", ms + 299_999, "0", 1, "0", "0", "0"])
            if len(out) >= limit:
                break
        return out

    def body(self, q, fault):
        rows = self.rows(q["symbol"], int(q["startTime"]), int(q["limit"]))
        if fault == "badjson":
            return b"{not json"
        if fault == "dup" and rows:
            rows = rows + [rows[-1]]
        if fault == "early" and rows:
            rows = [[rows[0][0] - 300_000] + rows[0][1:6] + [rows[0][0] - 1] + rows[0][7:]] + rows
        if fault == "closetime" and rows:
            rows[0][6] += 1
        if fault == "revise" and rows:
            rows[0][2] = repr(float(rows[0][2]) * 1.01)
        return json.dumps(rows).encode()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class Contract(unittest.TestCase):
    def test_only_the_contract_url_passes(self):
        good = src.build_url("BTCUSDT", T0 * 1000, 3)
        self.assertEqual(good, f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&startTime={T0 * 1000}"
                               "&limit=3")
        bad = [good.replace("https://", "http://"), good.replace("fapi.binance.com", "api.binance.com"),
               good.replace("fapi.binance.com", "fapi.binance.com.example.org"),
               good.replace("fapi.binance.com", "127.0.0.1"), good.replace("/fapi/v1/klines", "/fapi/v1/order"),
               good.replace("/fapi/v1/klines", "/fapi/v2/account"), good.replace("/fapi/v1/klines", "/fapi/v1/klines/"),
               good + "&signature=x", good + "&timestamp=1", good + "&apiKey=k", good + "&endTime=1",
               good.replace("&limit=3", ""), good.replace("interval=5m", "interval=1m"),
               good.replace("BTCUSDT", "SOLUSDT"), good.replace("limit=3", "limit=1000"),
               good.replace(f"startTime={T0 * 1000}", f"startTime={T0 * 1000 + 1}"), good + "#x",
               good.replace("https://", "https://user:pw@"), None, "ftp://fapi.binance.com/fapi/v1/klines"]
        for u in bad:
            with self.assertRaises(src.ContractViolation, msg=u):
                src.check_url(u)

    def test_no_request_without_activation(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with self.assertRaises(src.NotActivated):
                src.HttpTransport(src.BASE)
            for v in (False, 1, "yes", None):
                with self.assertRaises(src.NotActivated):
                    src.HttpTransport(src.BASE, Act(v))
                with self.assertRaises(src.NotActivated):
                    src.KlineSource(Act(v), T0, os.path.join(tempfile.gettempdir(), "event_farm_source_calls_x.jsonl"))
            for base in ("https://example.org", "http://10.0.0.1:80", "http://localhost:80", "https://127.0.0.1:1"):
                with self.assertRaises(src.ContractViolation):
                    src.HttpTransport(base, Act())
            t = src.HttpTransport("http://127.0.0.1:9", Act())
            with self.assertRaises(src.ContractViolation):
                t.get("https://fapi.binance.com/fapi/v1/order?symbol=BTCUSDT")

    def test_module_names_one_host_and_no_private_endpoint(self):
        with open(src.__file__, encoding="utf-8") as f:
            text = f.read()
        import re
        self.assertIsNone(re.search(r"(?<![a-z.])api\.binance\.com", text))
        for bad in ("X-MBX-APIKEY", "/order", "/account", "listenKey", "POST", "DELETE", "hmac", "socket.", "dapi.",
                    "data-api"):
            self.assertFalse(bad in text, bad)
        self.assertEqual(text.count("fapi.binance.com"), 2)          # the HOST constant and the docstring

    def test_log_path_rules(self):
        for p in ("/tmp/x/calls.jsonl", "/home/anton/ecommerence/copybot/event_farm_source_calls.jsonl",
                  "/tmp/research/data/event_farm_source_calls.jsonl", ""):
            with self.assertRaises(src.ContractViolation):
                src.check_log_path(p)


class Loopback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bars = truth(1)
        self.now = [T0 + 20]
        self.ex = FakeExchange(self.bars, self.now)
        self.addCleanup(self.ex.stop)
        self.log = os.path.join(self.tmp.name, "event_farm_source_calls_t.jsonl")
        self.s = self.source()

    def source(self, timeout=2.0):
        return src.KlineSource(Act(), T0, self.log, transport=src.HttpTransport(self.ex.base, timeout=timeout),
                               clock=lambda: self.now[0])

    def lines(self):
        with open(self.log, encoding="utf-8") as f:
            return [json.loads(x) for x in f]

    def test_closed_bars_only_exact_fields_and_no_backfill(self):
        self.now[0] = T0 + 2 * BS + 20                    # bars 0..1 closed, bar 2 forming
        got = self.s.fetch("BTCUSDT", None)
        self.assertEqual(got, self.bars["BTCUSDT"][:2])
        path, q = self.ex.requests[-1]
        self.assertEqual((path, q["startTime"], q["limit"], q["interval"]), ("/fapi/v1/klines", str(T0 * 1000), "3", "5m"))
        rec = self.lines()[-1]
        self.assertEqual((rec["status"], rec["rows"], rec["delivered"], rec["dropped_unclosed"]), (200, 3, 2, 1))
        b = self.bars["BTCUSDT"][0]
        self.assertEqual(rec["bars"][0], [b[0] * 1000, b[0] * 1000 + 299_999, repr(b[5])])
        self.assertEqual(self.s.fetch("BTCUSDT", T0 + BS), [self.bars["BTCUSDT"][1]])     # restarts at the last bar
        self.assertEqual(self.ex.requests[-1][1]["startTime"], str((T0 + BS) * 1000))
        self.now[0] = T0 + 100 * BS
        self.s.fetch("ETHUSDT", T0)
        self.assertEqual(self.ex.requests[-1][1]["limit"], "499")    # catch-up after a pause
        self.assertTrue(all(int(q["startTime"]) >= T0 * 1000 for _, q in self.ex.requests))

    def test_faults_reject_the_whole_response(self):
        self.now[0] = T0 + 5 * BS + 20
        for fault, err in (("badjson", "rejected"), ("dup", "duplicate"), ("early", "before startTime"),
                           ("closetime", "off the 5m"), (500, "http status")):
            self.ex.faults = [fault]
            self.assertEqual(self.s.fetch("BTCUSDT", None), [], fault)
            self.assertIn(err, self.lines()[-1]["error"], fault)
        self.assertEqual(len(self.s.fetch("BTCUSDT", None)), 5)

    def test_timeout_and_refused_connection(self):
        self.now[0] = T0 + 2 * BS + 20
        s = self.source(timeout=0.2)
        self.ex.faults = ["sleep"]
        self.assertEqual(s.fetch("BTCUSDT", None), [])
        self.assertTrue(self.lines()[-1]["error"].startswith("transport"))
        self.ex.stop()
        self.assertEqual(s.fetch("BTCUSDT", None), [])
        self.assertTrue(self.lines()[-1]["error"].startswith("transport"))
        self.ex = FakeExchange(self.bars, self.now)                    # a fresh server for cleanup
        self.addCleanup(self.ex.stop)

    def test_rate_limit_pauses_without_requests(self):
        self.now[0] = T0 + 2 * BS + 20
        self.ex.faults = [429]
        self.assertEqual(self.s.fetch("BTCUSDT", None), [])
        n = len(self.ex.requests)
        self.now[0] += 300
        self.assertEqual(self.s.fetch("BTCUSDT", None), [])
        self.assertEqual(len(self.ex.requests), n)                    # paused: no request
        self.assertEqual(self.lines()[-1]["error"], "backoff")
        self.now[0] += 301
        self.assertTrue(self.s.fetch("BTCUSDT", None))

    def test_gap_in_response_is_delivered_and_counted(self):
        self.now[0] = T0 + 6 * BS + 20
        self.ex.hidden = {T0 + 2 * BS}
        got = self.s.fetch("BTCUSDT", None)
        self.assertEqual([b[0] for b in got], [T0 + k * BS for k in (0, 1, 3, 4, 5)])
        self.assertEqual(self.lines()[-1]["gaps"], 1)

    def test_call_log_is_chained_and_tamper_refused(self):
        self.now[0] = T0 + 2 * BS + 20
        self.s.fetch("BTCUSDT", None)
        self.s.fetch("ETHUSDT", None)
        self.assertEqual(src.verify_log(self.log)[0], 2)
        again = self.source()                                          # reopen continues the chain
        again.fetch("BTCUSDT", T0 + BS)
        self.assertEqual(src.verify_log(self.log)[0], 3)
        with open(self.log, encoding="utf-8") as f:
            lines = f.readlines()
        lines[1] = lines[1].replace('"status":200', '"status":201')
        with open(self.log, "w", encoding="utf-8") as f:
            f.writelines(lines)
        with self.assertRaises(src.LogBroken):
            self.source()


def offline(bars, warmup):
    out = {}
    for s, bb in bars.items():
        ctx = ff.context(bb)
        events = ef.detect(bb, ef.params())
        for v in ef.VARIANTS:
            vid = ef._variant_id(v)
            pv = ef.params(**v)
            setups, _ = ef.build_setups(events, bb, pv)
            for x in setups:
                if x["known_i"] < warmup:
                    continue
                o = ef.setup_outcome(x, bb, pv)
                val = (x["entry"], x["stop"], x["target"], "pending" if o["status"] == "incomplete" else o["status"],
                       o["exit_px"])
                for combo in ("base",) + ff.COMBOS:
                    if combo == "base" or ff.passes(x, ctx, combo):
                        out[(f"{combo}/{vid}", s, x["known_ts"], x["kind"])] = val
    return out


class WithBookV2(unittest.TestCase):
    """The adapter feeding ForwardBookV2 in its live configuration (BTCUSDT, ETHUSDT, frozen config), with test
    activations and the loopback exchange. One pass per 5m slot, 20 s after the boundary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bars = truth(2)
        self.now = [T0]
        self.ex = FakeExchange(self.bars, self.now)
        self.addCleanup(self.ex.stop)

    def open(self, name):
        log = os.path.join(self.tmp.name, f"event_farm_source_calls_{name}.jsonl")
        s = src.KlineSource(Act(), T0, log, transport=src.HttpTransport(self.ex.base), clock=lambda: self.now[0])
        b = fv.ForwardBookV2(os.path.join(self.tmp.name, f"event_farm_forward_{name}.db"), s, SYMS, mode="live",
                             activation=Act(), clock=lambda: self.now[0])
        return s, b

    def run_slots(self, book, k0, k1):
        for k in range(k0, k1):
            self.now[0] = T0 + k * BS + 20
            book.step()

    def test_end_to_end_equals_offline_and_restart_and_crash_are_reproducible(self):
        n = len(self.bars["BTCUSDT"])
        s1, ref = self.open("ref")
        self.run_slots(ref, 1, n + 1)
        for sym in SYMS:
            self.assertEqual(ref.bars[sym], self.bars[sym])
        self.assertEqual(fw.report(ref)["data"]["BTCUSDT"]["gaps"], (0, 0))
        got = {r[:4]: tuple(r[4:]) for r in ref.db.execute(
            "SELECT variant, symbol, known_ts, kind, entry, stop, target, status, exit_px FROM trades "
            "WHERE status NOT LIKE 'not_taken%'")}
        self.assertEqual(got, offline(self.bars, fw.FROZEN_CONFIG["warmup_bars"]))
        self.assertTrue(got)
        calls = src.verify_log(s1.log_path)[0]
        self.assertEqual(calls, 2 * n)                                  # one GET per symbol per slot

        s2, b2 = self.open("re")
        self.run_slots(b2, 1, 300)
        b2.close()
        s2, b2 = self.open("re")                                        # restart: same provenance, same identity
        real = b2._insert
        cnt = {"n": 0}

        def flaky(*a, **k):
            cnt["n"] += 1
            if cnt["n"] == 5:
                raise OSError("simulated crash")
            return real(*a, **k)
        with mock.patch.object(b2, "_insert", side_effect=flaky):
            with self.assertRaises(OSError):
                self.run_slots(b2, 300, n + 1)
        k_crash = (self.now[0] - 20 - T0) // BS
        self.run_slots(b2, k_crash, n + 1)
        self.assertEqual(b2.dump(), ref.dump())
        src.verify_log(s2.log_path)
        b2.close()
        ref.close()

    def test_outage_then_catch_up_and_exchange_gap(self):
        s, b = self.open("out")
        self.run_slots(b, 1, 100)
        self.ex.stop()
        self.run_slots(b, 100, 140)                                     # 40 slots without the exchange
        self.ex = FakeExchange(self.bars, self.now)
        self.addCleanup(self.ex.stop)
        s.transport = src.HttpTransport(self.ex.base)
        self.ex.hidden = {T0 + 200 * BS}                                # a bar the exchange never publishes
        self.run_slots(b, 140, 260)
        bb = b.bars["BTCUSDT"]
        self.assertEqual([x[0] for x in bb], [x[0] for x in self.bars["BTCUSDT"][:259] if x[0] != T0 + 200 * BS])
        self.assertEqual(b.db.execute("SELECT symbol, from_ts FROM gaps").fetchall(),
                         [("BTCUSDT", T0 + 200 * BS), ("ETHUSDT", T0 + 200 * BS)])
        errors = [json.loads(x)["error"] for x in open(s.log_path, encoding="utf-8")]
        self.assertGreaterEqual(sum(1 for e in errors if e and e.startswith("transport")), 80)
        self.assertIn("499", [q["limit"] for _, q in self.ex.requests])
        b.close()

    def test_revised_bar_reaches_the_conflict_log(self):
        s, b = self.open("rev")
        self.run_slots(b, 1, 20)
        self.ex.faults = ["revise"]
        self.run_slots(b, 20, 21)
        self.assertEqual(b.db.execute("SELECT symbol, ts, processed FROM conflicts").fetchall(),
                         [("BTCUSDT", T0 + 18 * BS, 1)])
        b.close()


class FinalText103(unittest.TestCase):
    AMEND = os.path.join(HERE, "research", "desk", "EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.md")

    def test_sha256_file_matches_and_every_referenced_file_is_current(self):
        with open(self.AMEND[:-3] + ".sha256", encoding="utf-8") as f:
            sha, name = f.read().split()
        self.assertEqual((sha, name), (src.file_sha256(self.AMEND), os.path.basename(self.AMEND)))
        with open(self.AMEND, encoding="utf-8") as f:
            text = f.read()
        self.assertLess(len(text), 8000)
        refs = ["research/tools/event_farm.py", "research/tools/event_farm_driver.py", "research/tools/event_farm_filters.py",
                "research/tools/event_farm_forward.py", "research/tools/event_farm_forward_v2.py",
                "research/tools/event_farm_source.py", "research/desk/EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md",
                "research/desk/EVENT_FARM.md"]
        for rel in refs:
            line = next(x for x in text.splitlines() if x.startswith(f"| `{rel}`"))
            self.assertIn(f"`{src.file_sha256(os.path.join(HERE, rel))}`", line, rel)
        for word in ("ANTAGELSE", "19.849", "[5]", "[6]", "NotActivated"):
            self.assertIn(word, text)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
