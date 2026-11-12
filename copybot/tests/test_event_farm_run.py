"""The event farm forward runner (PROTOCOL_V3 amendment 46): gate checks on the real repo state, fail-closed paths, and
one end-to-end step against a loopback fake exchange with synthetic bars. No real request is made; host resolution
is injected."""
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from research.tools import event_farm_forward as fw  # noqa: E402
from research.tools import event_farm_run as run  # noqa: E402
from research.tools import event_farm_source as src  # noqa: E402
from test_event_farm_source import FakeExchange, truth, T0  # noqa: E402

with open(os.path.join(HERE, run.STATEMENT), encoding="utf-8") as _f:
    STMT = json.load(_f)
NOW = STMT["issued"] + 3600                     # inside the signed statement's validity


def public(host, port, proto=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("65.9.46.68", port))]


def blocked(host, port, proto=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("0.0.0.0", port))]


class Checks(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home)

    def test_without_green_tests_the_gate_stays_closed_and_nothing_is_written(self):
        book, checks = run.open_book(HERE, self.home, NOW, resolve=public, env={})
        self.assertIsNone(book)
        self.assertFalse(checks["loader_tests_green"][0])
        self.assertFalse(checks["decide"][0])
        self.assertEqual(os.listdir(self.home), [])

    def test_all_flags_pass_on_the_committed_state(self):
        run.mark_tests_green(HERE, self.home, "test")
        checks, stmt, slot = run.run_checks(HERE, self.home, NOW, resolve=public, env={})
        bad = {k: v for k, v in checks.items() if not v[0]}
        self.assertEqual(bad, {})
        self.assertEqual(stmt["blob"], run.AMEND_SHA)
        self.assertEqual(slot % 300, 0)
        self.assertGreaterEqual(slot, NOW)

    def test_host_bypass_or_block_closes_the_gate(self):
        self.assertFalse(run.check_host(blocked, {})[0])
        self.assertFalse(run.check_host(public, {"HTTPS_PROXY": "http://x:1"})[0])

        def fail(*a, **k):
            raise socket.gaierror("no")
        self.assertFalse(run.check_host(fail, {})[0])
        self.assertTrue(run.check_host(public, {})[0])

    def test_expired_statement_cannot_activate(self):
        run.mark_tests_green(HERE, self.home, "test")
        checks, _, _ = run.run_checks(HERE, self.home, STMT["expires"] + 1, resolve=public, env={})
        self.assertFalse(checks["validity"][0])

    def test_changed_code_is_refused(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        for rel in run.CODE:
            os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
            shutil.copy(os.path.join(HERE, rel), os.path.join(root, rel))
        self.assertTrue(run.code_ok(root)[0])
        with open(os.path.join(root, "research/tools/event_farm.py"), "a") as f:
            f.write("\n")
        self.assertFalse(run.code_ok(root)[0])

    def test_activation_approves_only_the_two_actions(self):
        a = run.Activation({"x": (True, "")})
        self.assertTrue(a.approved(fw.ACTION) and a.approved(src.ACTION))
        self.assertFalse(a.approved("real_money_order"))
        self.assertFalse(run.Activation({"x": (True, ""), "y": (False, "")}).approved(fw.ACTION))


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home)
        run.mark_tests_green(HERE, self.home, "test")
        self.slot = run.next_slot(NOW)
        d = self.slot - T0
        self.bars = {s: [(b[0] + d,) + tuple(b[1:]) for b in rows] for s, rows in truth(1).items()}
        self.now = [NOW]
        self.ex = FakeExchange(self.bars, self.now)
        self.addCleanup(self.ex.stop)

    def open(self):
        orig = run.check_host
        run.check_host = lambda *a, **k: (True, "test")
        try:
            return run.open_book(HERE, self.home, self.now[0], transport=src.HttpTransport(self.ex.base, timeout=2.0),
                                 clock=lambda: self.now[0])
        finally:
            run.check_host = orig

    def test_one_step_books_closed_bars_and_logs_the_call(self):
        book, checks = self.open()
        self.assertIsNotNone(book, checks)
        act = run.read_activation(self.home)
        self.assertEqual(act["start_ts"], self.slot)
        self.now[0] = self.slot + 3 * 300 + 20
        what, stats = run.step_once(HERE, self.home, book, self.now[0])
        self.assertEqual(what, "ok")
        self.assertEqual(stats["new_bars"], 6)                                 # 3 closed bars x 2 symbols
        self.assertTrue(all(int(q["startTime"]) >= self.slot * 1000 for _, q in self.ex.requests))   # no backfill
        status = json.load(open(os.path.join(self.home, "status.json")))
        self.assertIsNone(status["halted"])
        with open(os.path.join(self.home, "event_farm_source_calls.jsonl")) as f:
            self.assertEqual(len(f.readlines()), 2)
        book.db.close()
        book2, _ = self.open()                                                  # restart keeps the slot and the db
        self.assertEqual(run.read_activation(self.home)["start_ts"], self.slot)
        self.assertEqual(len(book2.bars["BTCUSDT"]) + len(book2.bars["ETHUSDT"]), 6)
        book2.db.close()

    def test_stop_file_stops_before_any_call(self):
        book, _ = self.open()
        open(os.path.join(self.home, "STOP"), "w").close()
        n = len(self.ex.requests)
        self.assertEqual(run.step_once(HERE, self.home, book, self.slot + 920)[0], "stopped")
        self.assertEqual(len(self.ex.requests), n)
        book.db.close()


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
