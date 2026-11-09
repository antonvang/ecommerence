"""Director order 78: the real lab.paper_runner.close_ledger on a temporary database with mocked books, and the pure
classification in research/tools/partial_close.py. A partial close must never read as a success. Simulated only; no
network, no DNS, no lab.db, no change to paper_runner."""
import ast
import copy
import itertools
import os
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lab import carry90, lane, paper_runner as pr  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from research.tools import partial_close as pc  # noqa: E402

HOUR = 3600
NOW = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc).timestamp()
DNS = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
PERP, SPOT = "BTCUSDT", "BTCUSDT.SPOT"


def no_network(*a, **k):
    raise AssertionError("order 78 tests must not touch the network or DNS")


def market(px=100.0, spread=0.02, rate=0.0001):
    """Mocked public data. get.spot / get.perp: None (normal), an exception (leg unavailable) or a float (top-of-book size,
    a thin book)."""
    def book(size):
        return {"bids": [[str(px - spread / 2), str(size)]], "asks": [[str(px + spread / 2), str(size)]]}

    def get(path):
        if path.startswith(pr.SPOT_REST):
            if isinstance(get.spot, BaseException):
                raise get.spot
            return book(1000 if get.spot is None else get.spot)
        if path.startswith("https://"):
            raise AssertionError(path)
        if isinstance(get.perp, BaseException):
            raise get.perp
        if "/fapi/v1/depth" in path:
            return book(1000 if get.perp is None else get.perp)
        if "klines" in path:
            start = int(get.now) // HOUR * HOUR - 1000 * HOUR
            return [[(start + i * HOUR) * 1000, px, px, px, px, 1, (start + (i + 1) * HOUR) * 1000 - 1, 100.0]
                    for i in range(1001)]
        if "fundingRate" in path:
            last = int(get.now) // (8 * HOUR) * 8 * HOUR
            return [{"fundingTime": (last - k * 8 * HOUR) * 1000, "fundingRate": str(rate)} for k in range(199, -1, -1)]
        raise AssertionError(path)
    get.now, get.spot, get.perp = NOW, None, None
    return get


class CloseLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab78")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)]
        for p in self.p:
            p.start()
        pr._HOURLY.clear()
        self.get = market()
        with self.db.tx():
            self.db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                           metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(self.db, NOW - 60)
        self.led = {i["key"]: x for x, i in lane.started(self.db).items()}["carry90|BTCUSDT"]
        self.assertEqual(lane.run_one(self.db, self.led, self.get, NOW)["status"], "ok")
        self.before = dict(self.positions())
        self.assertEqual(set(self.before), {PERP, SPOT})
        self.assertLess(self.before[PERP], 0)
        self.assertGreater(self.before[SPOT], 0)
        lane.retire(self.db, self.led, "source", "synthetic test stop", None, NOW + 60)
        self.assertIn((self.led, self.led), pr.closing_ledgers(self.db))
        self.raw_before = self.raw_counts()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def positions(self):
        return PaperEngine(self.db).ledger(self.led)["positions"]

    def raw_counts(self):
        return {t: self.db.one(f"SELECT COUNT(*) FROM {t} WHERE exp_id=?", self.led)[0]
                for t in ("sim_orders", "sim_fills", "sim_equity", "sim_funding")}

    def close(self, t, spot=None, perp=None):
        self.get.now, self.get.spot, self.get.perp = t, spot, perp
        return pr.close_ledger(self.db, self.led, self.led, self.get, t)

    def close_fills(self):
        out, last = {}, None
        for r in self.db.q("SELECT f.instrument, f.qty, f.ts FROM sim_fills f JOIN sim_orders o ON o.order_id=f.order_id "
                           "WHERE f.exp_id=? AND o.reduce_only=1 AND o.order_id LIKE ?", self.led, f"{self.led}|close|%"):
            out[r["instrument"]] = out.get(r["instrument"], 0.0) + r["qty"]
            last = max(last or r["ts"], r["ts"])
        return out, last

    def status(self):
        closed, last_fill = self.close_fills()
        mark = self.db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", self.led)[0]
        return pc.classify_close(self.before, self.positions(), closed, last_fill, mark)

    def assert_no_row_lost(self):
        now = self.raw_counts()
        for t, n in self.raw_before.items():
            self.assertGreaterEqual(now[t], n, t)

    def test_runs_the_real_close_ledger(self):
        self.assertEqual(pr.close_ledger.__module__, "lab.paper_runner")
        self.assertNotIsInstance(pr.close_ledger, mock.Mock)

    def test_both_legs_close_is_the_only_success(self):
        r = self.close(NOW + HOUR)
        self.assertEqual(self.positions(), {})
        self.assertTrue(r["final_mark"])
        s = self.status()
        self.assertEqual(s["status"], pc.CLOSE_SUCCESS)
        self.assertTrue(s["success"])
        self.assertEqual(s["legs"], {PERP: pc.LEG_CLOSED, SPOT: pc.LEG_CLOSED})
        self.assert_no_row_lost()

    def test_spot_unavailable_is_partial_and_the_pass_still_says_closing(self):
        r = self.close(NOW + HOUR, spot=DNS)
        self.assertEqual(r["status"], "closing")                       # the engine's own word is not a verdict
        self.assertEqual(set(self.positions()), {SPOT})
        s = self.status()
        self.assertEqual(s["status"], pc.PARTIAL_CLOSE)
        self.assertFalse(s["success"])
        self.assertEqual(s["open_legs"], [SPOT])
        self.assertEqual(s["legs"][PERP], pc.LEG_CLOSED)
        self.assertEqual(s["legs"][SPOT], pc.LEG_OPEN)
        self.assertFalse(r["marked"])
        self.assertIn((self.led, self.led), pr.closing_ledgers(self.db))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=? AND exp_id=?", pr.MARK_FAILED,
                                     self.led)[0], 1)
        self.assert_no_row_lost()

    def test_perp_unavailable_is_partial(self):
        self.close(NOW + HOUR, perp=DNS)
        self.assertEqual(set(self.positions()), {PERP})
        s = self.status()
        self.assertEqual(s["status"], pc.PARTIAL_CLOSE)
        self.assertEqual(s["open_legs"], [PERP])
        self.assertFalse(s["success"])

    def test_both_unavailable_is_incomplete(self):
        n = self.raw_counts()
        r = self.close(NOW + HOUR, spot=DNS, perp=DNS)
        self.assertEqual(self.positions(), self.before)
        self.assertEqual(self.raw_counts()["sim_fills"], n["sim_fills"])
        self.assertFalse(r["marked"])
        s = self.status()
        self.assertEqual(s["status"], pc.CLOSE_INCOMPLETE)
        self.assertEqual(s["reason"], "no leg was reduced")
        self.assertFalse(s["success"])

    def test_thin_book_reduces_the_leg_without_closing_it(self):
        self.close(NOW + HOUR, spot=1.0)
        self.assertAlmostEqual(self.positions()[SPOT], self.before[SPOT] - 1.0)
        s = self.status()
        self.assertEqual(s["status"], pc.PARTIAL_CLOSE)
        self.assertEqual(s["legs"][SPOT], pc.LEG_REDUCED)
        self.assertFalse(s["success"])

    def test_both_books_thin_is_partial_never_success(self):
        self.close(NOW + HOUR, spot=1.0, perp=1.0)
        s = self.status()
        self.assertEqual(s["status"], pc.PARTIAL_CLOSE)
        self.assertEqual(set(s["legs"].values()), {pc.LEG_REDUCED})

    def test_repeated_attempts_do_not_close_a_leg_twice(self):
        self.close(NOW + HOUR, spot=DNS)
        first = self.raw_counts()["sim_fills"]
        self.close(NOW + HOUR + 60, spot=DNS)                          # same hour
        self.assertEqual(self.raw_counts()["sim_fills"], first)
        self.close(NOW + 2 * HOUR, spot=DNS)                           # next hour, spot still gone
        self.assertEqual(self.raw_counts()["sim_fills"], first)
        self.assertEqual(self.status()["status"], pc.PARTIAL_CLOSE)
        self.close(NOW + 3 * HOUR)                                     # the leg can be read again
        self.assertEqual(self.positions(), {})
        self.assertEqual(self.status()["status"], pc.CLOSE_SUCCESS)
        closed, _ = self.close_fills()
        self.assertAlmostEqual(closed[PERP], abs(self.before[PERP]))
        self.assertAlmostEqual(closed[SPOT], abs(self.before[SPOT]))

    def test_restart_between_two_closes(self):
        self.close(NOW + HOUR, spot=DNS)
        self.assertEqual(self.status()["status"], pc.PARTIAL_CLOSE)
        fills = self.raw_counts()["sim_fills"]
        self.db.close()
        pr._HOURLY.clear()
        self.db = DB(self.path)                                        # a fresh process sees only the database
        self.assertEqual(self.status()["status"], pc.PARTIAL_CLOSE)
        self.assertIn((self.led, self.led), pr.closing_ledgers(self.db))
        self.close(NOW + HOUR + 120, spot=DNS)                         # same hour after the restart: nothing doubles
        self.assertEqual(self.raw_counts()["sim_fills"], fills)
        self.close(NOW + 2 * HOUR)
        self.assertEqual(self.positions(), {})
        self.assertEqual(self.status()["status"], pc.CLOSE_SUCCESS)

    def test_flat_without_a_final_mark_is_not_success(self):
        self.close(NOW + HOUR)
        closed, last = self.close_fills()
        s = pc.classify_close(self.before, {}, closed, last, last - 1)  # the mark precedes the last fill
        self.assertEqual(s["status"], pc.CLOSE_INCOMPLETE)
        self.assertFalse(s["success"])

    def test_after_a_partial_close_current_equity_is_not_computable(self):
        self.close(NOW + HOUR, spot=DNS)
        t = NOW + HOUR
        led = PaperEngine(self.db).ledger(self.led)
        mark = self.db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", self.led)[0]
        rows = [(tb, r["ts"]) for tb in ("sim_equity", "sim_fills", "sim_funding")
                for r in self.db.q(f"SELECT ts FROM {tb} WHERE exp_id=?", self.led)]
        view = pc.ledger_view(rows, mark, led["cash"], led["positions"], {}, t, close=self.status())
        self.assertEqual(view["equity"]["status"], pc.EQUITY_NOT_COMPUTABLE)
        self.assertIsNone(view["equity"]["equity"])
        self.assertFalse(view["current_pnl_available"])
        self.assertEqual(view["close"]["status"], pc.PARTIAL_CLOSE)
        self.assertEqual(view["missing_spot_mark"]["legs"], [SPOT])
        self.assertEqual(sum(view["counts"].values()), len(rows))
        self.assertGreater(view["counts"][pc.FILL_AFTER_MARK], 0)


class Classify(unittest.TestCase):
    def test_success_only_when_every_leg_is_flat_accounted_for_and_marked(self):
        before = {"P": -2.0, "S.SPOT": 2.0}
        afters = [{}, {"P": 0.0, "S.SPOT": 0.0}, {"P": -2.0}, {"S.SPOT": 2.0}, {"P": -1.0, "S.SPOT": 1.0},
                  {"P": -2.0, "S.SPOT": 2.0}, {"P": 1.0}, {"P": -3.0, "S.SPOT": 2.0}]
        closeds = [{}, {"P": 2.0}, {"S.SPOT": 2.0}, {"P": 2.0, "S.SPOT": 2.0}, {"P": 1.0, "S.SPOT": 1.0}, {"Q": 1.0}]
        for after, closed, fill, mark in itertools.product(afters, closeds, (None, 100, 200), (None, 100, 200)):
            s = pc.classify_close(before, after, closed, fill, mark)
            self.assertIn(s["status"], pc.CLOSE_STATUSES)
            flat = all(abs(v) < 1e-12 for v in after.values())
            ok = flat and closed == {"P": 2.0, "S.SPOT": 2.0} and fill is not None and mark is not None and mark >= fill
            self.assertEqual(s["status"] == pc.CLOSE_SUCCESS, ok, (after, closed, fill, mark))
            self.assertEqual(s["success"], ok)

    def test_definitions(self):
        b = {"P": -2.0, "S.SPOT": 2.0}
        self.assertEqual(pc.classify_close(b, {"S.SPOT": 2.0}, {"P": 2.0})["status"], pc.PARTIAL_CLOSE)
        self.assertEqual(pc.classify_close(b, b, {})["status"], pc.CLOSE_INCOMPLETE)
        self.assertEqual(pc.classify_close({}, {}, {})["status"], pc.NO_POSITION)

    def test_flat_with_unexplained_fills_fails_closed(self):
        for closed in ({"P": 1.0, "S.SPOT": 2.0}, {"P": 2.0}, {}):
            s = pc.classify_close({"P": -2.0, "S.SPOT": 2.0}, {}, closed, 100, 200)
            self.assertEqual(s["status"], pc.CLOSE_INCOMPLETE, closed)

    def test_malformed_input_fails_closed(self):
        bad = float("nan")
        for args in (({"P": bad}, {}, {}), ({"P": 1.0}, {"P": bad}, {}), ({"P": 1.0}, {}, {"P": bad}), (None, {}, {}),
                     ({"P": 1.0}, None, {}), ({"P": 1.0}, {}, "x"), ({"": 1.0}, {}, {}), ({"P": True}, {}, {})):
            s = pc.classify_close(*args, 100, 200)
            self.assertEqual(s["status"], pc.CLOSE_INCOMPLETE, args)
            self.assertFalse(s["success"])

    def test_new_leg_grown_leg_and_sign_change_fail_closed(self):
        b = {"P": -2.0, "S.SPOT": 2.0}
        for after in ({"X": 1.0}, {"P": -3.0, "S.SPOT": 2.0}, {"P": 1.0}):
            self.assertEqual(pc.classify_close(b, after, {}, 100, 200)["status"], pc.CLOSE_INCOMPLETE, after)

    def test_inputs_are_not_changed(self):
        b, a, c = {"P": -2.0, "S.SPOT": 2.0}, {"S.SPOT": 2.0}, {"P": 2.0}
        snap = copy.deepcopy((b, a, c))
        pc.classify_close(b, a, c, 100, 200)
        self.assertEqual((b, a, c), snap)
        rows = [("sim_funding", 300), ("sim_equity", 100)]
        keep = list(rows)
        pc.ledger_view(rows, 100, 1000.0, a, {}, 400)
        self.assertEqual(rows, keep)

    def test_record_classes(self):
        cut = 1000
        self.assertEqual(pc.classify_record("sim_equity", 1000, cut), pc.VERIFIED_MARK)
        self.assertEqual(pc.classify_record("sim_equity", 1001, cut), pc.MARK_AFTER_CUTOFF)
        self.assertEqual(pc.classify_record("sim_funding", 1000, cut), pc.FUNDING_IN_MARK)
        self.assertEqual(pc.classify_record("sim_funding", 1001, cut), pc.FUNDING_AFTER_MARK)
        self.assertEqual(pc.classify_record("sim_fills", 999, cut), pc.FILL_IN_MARK)
        self.assertEqual(pc.classify_record("sim_fills", 1001, cut), pc.FILL_AFTER_MARK)
        self.assertEqual(pc.classify_record("other", 1, cut), pc.UNCLASSIFIED)
        self.assertEqual(pc.classify_record("sim_funding", None, cut), pc.UNCLASSIFIED)

    def test_no_class_calls_a_record_invalid(self):
        for c in pc.RECORD_CLASSES:
            self.assertNotIn("INVALID", c)

    def test_equity_needs_a_fresh_mark_for_every_open_leg(self):
        pos, t = {"P": -2.0, "S.SPOT": 2.0}, 100_000
        fresh = {"P": (100.0, t), "S.SPOT": (101.0, t - pc.MARK_MAX_AGE_S)}
        self.assertEqual(pc.equity_view(50.0, pos, fresh, t),
                         {"status": pc.EQUITY_COMPUTABLE, "equity": 52.0, "missing_marks": [], "reason": None})
        for marks in ({"P": (100.0, t)}, {"P": (100.0, t), "S.SPOT": (101.0, t - pc.MARK_MAX_AGE_S - 1)},
                      {"P": (100.0, t), "S.SPOT": (float("inf"), t)}, {"P": (100.0, t), "S.SPOT": (101.0, t + 1)}):
            v = pc.equity_view(50.0, pos, marks, t)
            self.assertEqual(v["status"], pc.EQUITY_NOT_COMPUTABLE, marks)
            self.assertIsNone(v["equity"])
            self.assertEqual(v["missing_marks"], ["S.SPOT"])

    def test_stale_equity_is_never_returned_as_current(self):
        v = pc.ledger_view([("sim_equity", 100)], 100, 9_990.0, {"S.SPOT": 2.0}, {"S.SPOT": (50.0, 100)}, 100 + 3 * 3600)
        self.assertIsNone(v["equity"]["equity"])
        self.assertFalse(v["current_pnl_available"])

    def test_missing_mark_hours(self):
        self.assertEqual(pc.missing_mark_hours(3600, 3600), 0)
        self.assertEqual(pc.missing_mark_hours(3600, 3599 + 3600), 0)
        self.assertEqual(pc.missing_mark_hours(3600, 3 * 3600), 2)
        self.assertEqual(pc.missing_mark_hours(None, 3600), 0)

    def test_module_is_pure(self):
        with open(pc.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or "").split(".")[0])
        self.assertEqual(names, {"math"})


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
