"""Director order 66 track B: synthetic reproductions for the paper-engine audit
(research/desk/PAPER_ENGINE_QUALITY_REPORT.md). Temporary databases, mocked market data, no network, no DNS.

- CLEARED: behaviour the audit checked and found right (these pass).
- CONFIRMED + fixed on this branch: the test passes only with the fix.
- CONFIRMED + STOP: `expectedFailure` documents a bug whose fix would touch a pinned/frozen file or change an active
  book's rules; it turns into an "unexpected success" the day it is fixed.
lab/straks.py and lab/pairs.py are never modified (their pins are checked at the end)."""
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from dataclasses import asdict
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lab import carry90, lane, paper_runner as pr, pipeline, reportcheck, straks  # noqa: E402
from lab import risk as risk_mod  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import Book, CostModel, PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.test_lab_mark_failed import market as carry_market  # noqa: E402  (a function, not a TestCase)
from tests.test_lab_straks import market as straks_market  # noqa: E402

HOUR, DAY = 3600, 86400
NOW = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc).timestamp()
DNS = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.0004)
FROZEN = {"straks.py": "7a110f1fa20fb7d28b76269fc039eec4c75ddfa7353602f2f8824490b722a542",
          "pairs.py": "5c9b60a4314a40a5e4d517427c4960220682b8f6179a445a5554903180ce1219"}


def no_network(*a, **k):
    raise AssertionError("order 66 audit tests must not touch the network or DNS")


def load_net_report():
    spec = importlib.util.spec_from_file_location("net_report_66b", os.path.join(HERE, "research", "tools",
                                                                                "net_report.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab66b")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)]
        for p in self.p:
            p.start()
        pr._HOURLY.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ledger(self, led="LANE_66b0000001", capital=10_000.0, source="straks"):
        """A bare simulated ledger: lane.started (so the risk gate sees an active lane) and paper.started."""
        self.db.event("lane.started", "system:lane", led, {"key": led, "source": source, "name": "T", "coins": ["X"],
                                                           "capital": capital, "t": int(NOW - DAY),
                                                           "costs": asdict(COSTS)})
        self.db.event("paper.started", "system:test", led, {"capital": capital, "costs": asdict(COSTS),
                                                            "simulated": True})
        return led

    def fill(self, led, ts, side, qty, px, inst="X", fee=0.0, mid=None):
        n = self.db.one("SELECT COUNT(*) FROM sim_orders")[0]
        oid = f"{led}|t{n}|{inst}"
        with self.db.tx():
            self.db.append("sim_orders", order_id=oid, exp_id=led, ts=int(ts), instrument=inst, side=side, qty=qty,
                           limit_px=None, style="taker", reduce_only=0, signal_ref="test", cost_model=asdict(COSTS))
            self.db.append("sim_fills", fill_id=f"{oid}|0", order_id=oid, exp_id=led, ts=int(ts), instrument=inst,
                           side=side, px=px, qty=qty, fee=fee, slippage=0.0, liquidity="taker", mid=mid or px,
                           book_ts=int(ts))


# ---------------------------------------------------------------- 4. positions, flips and equity
class Positions(Base):
    def test_cleared_engine_flip_resets_basis_and_splits_the_fee(self):
        led = self.ledger()
        self.fill(led, NOW, "buy", 1.0, 100.0, fee=0.1)
        self.fill(led, NOW + 60, "sell", 3.0, 110.0, fee=0.33)          # closes 1 long (+10), opens 2 short @ 110
        led_ = PaperEngine(self.db).ledger(led)
        self.assertEqual(led_["positions"], {"X": -2.0})
        self.assertEqual(led_["basis"], {"X": 110.0})
        (t1,) = led_["trades"]
        self.assertAlmostEqual(t1[1], 10.0 - 0.1 - 0.11)               # its own fee and a third of the flip fee
        self.fill(led, NOW + 120, "buy", 2.0, 105.0, fee=0.21)         # closes the short: +10
        led_ = PaperEngine(self.db).ledger(led)
        self.assertEqual(led_["positions"], {})
        self.assertAlmostEqual(led_["trades"][1][1], 10.0 - 0.22 - 0.21)
        self.assertAlmostEqual(led_["realized"], led_["cash"] - 10_000.0)   # flat: realized is the whole cash change

    @unittest.expectedFailure
    def test_confirmed_stop_net_report_keeps_the_old_basis_through_a_flip(self):
        """net_report.py (pinned NET_REPORT e8cac57c) keeps the long basis after a flip to short, so the per-instrument
        realized price P&L, round trips and direction are wrong after any flip. Real DB: no flip in its accounts."""
        led = self.ledger()
        self.fill(led, NOW, "buy", 1.0, 100.0)
        self.fill(led, NOW + 60, "sell", 2.0, 110.0)                   # flip: long 1 -> short 1 @ 110
        self.fill(led, NOW + 120, "buy", 1.0, 100.0)                   # close the short: +10
        info = lane.started(self.db)[led]
        con = sqlite3.connect(f"file:{self.db.path}?mode=ro", uri=True)
        try:
            row = load_net_report().account(con, led, info, int(NOW + DAY))
        finally:
            con.close()
        x = row["instruments"]["X"]
        self.assertEqual(len(PaperEngine(self.db).ledger(led)["trades"]), 2)
        self.assertAlmostEqual(x["realized_price_pnl"], 20.0)          # engine: +10 long, +10 short
        self.assertEqual(x["round_trips"], 2)

    def test_cleared_marks_cash_peak_and_drawdown_agree_with_a_replay(self):
        led = self.ledger()
        eng = PaperEngine(self.db, lambda: NOW + 300)
        self.fill(led, NOW, "buy", 10.0, 100.0, fee=1.0)
        a = eng.mark(led, {"X": 110.0})
        b = PaperEngine(self.db, lambda: NOW + HOUR).mark(led, {"X": 95.0})
        rows = self.db.q("SELECT equity, cash, peak, drawdown FROM sim_equity WHERE exp_id=? ORDER BY id", led)
        self.assertAlmostEqual(rows[0]["cash"], 10_000.0 - 1_000.0 - 1.0)
        self.assertAlmostEqual(a["equity"], 10_099.0)
        self.assertAlmostEqual(rows[1]["peak"], 10_099.0)               # the running peak never falls
        self.assertAlmostEqual(b["drawdown"], (10_099.0 - 9_949.0) / 10_099.0)


# ---------------------------------------------------------------- 2. funding
class Funding(Base):
    def test_cleared_sign_flat_and_replay(self):
        led = self.ledger()
        t_f, st = int(NOW - 10 * HOUR), int(NOW // HOUR * HOUR - 8 * HOUR)
        self.fill(led, st - 600, "sell", 2.0, 100.0)                   # short before the settlement
        self.fill(led, st + 600, "buy", 2.0, 100.0)                    # flat after it
        data = {"X": ({st: 0.001, st + 8 * HOUR: 0.001}, {st: 50.0, st + 8 * HOUR: 50.0})}
        eng = PaperEngine(self.db, lambda: NOW)
        (r,) = eng.book_funding(led, data, t_f)
        self.assertAlmostEqual(r["amount"], 2.0 * 50.0 * 0.001)        # a short receives a positive rate
        self.assertEqual(eng.book_funding(led, data, t_f), [])          # replay: nothing twice; flat: nothing
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_funding")[0], 1)

    @unittest.expectedFailure
    def test_confirmed_stop_a_missing_middle_bar_stalls_funding_silently(self):
        """book_funding waits (`break`) for a settlement whose 1h bar is absent although later bars exist: that
        instrument books nothing more until the bar falls out of the fetched window (1000 h Binance, 48 h HL) and
        no event says so. Real DB: 0 of 559 cross-checked settlements missing, 0 funding_gap events.
        Order 67 P0-C: in the default ("legacy") mode it stays silent; FUNDING_MISSING_MODE "fail_closed" makes it a
        visible error (tests/test_lab_engine_remediation_67.py) and still books nothing after it."""
        led = self.ledger()
        t_f, st = int(NOW - 20 * HOUR), int(NOW // HOUR * HOUR - 16 * HOUR)
        self.fill(led, st - 600, "buy", 1.0, 100.0)
        funding = {st: 0.0001, st + 8 * HOUR: 0.0001}
        opens = {t: 100.0 for t in range(st - 4 * HOUR, int(NOW), HOUR) if t != st}     # the bar at st is missing
        PaperEngine(self.db, lambda: NOW).book_funding(led, {"X": (funding, opens)}, t_f)
        booked = {r[0] for r in self.db.q("SELECT settle_ts FROM sim_funding")}
        seen = self.db.one("SELECT COUNT(*) FROM events WHERE kind='paper.funding_missing'")[0]
        self.assertEqual((booked, seen), (set(), 1))                   # nothing invented, but visible


# ---------------------------------------------------------------- 5/8. idempotency and races
class Idempotency(Base):
    def book(self, ts):
        return Book(ts=ts, bids=((99.99, 1000.0),), asks=((100.01, 1000.0),))

    def test_cleared_a_lost_check_race_on_one_order_id_books_one_fill(self):
        led = self.ledger()
        other = DB(self.db.path)                                       # a second process on the same file
        try:
            a, b = PaperEngine(self.db, lambda: NOW), PaperEngine(other, lambda: NOW)
            ra = a.submit_taker(led, f"{led}|h|X", "X", "buy", 1.0, self.book(NOW))
            real = b._existing
            with mock.patch.object(b, "_existing", side_effect=[None, real(f"{led}|h|X")]):
                rb = b.submit_taker(led, f"{led}|h|X", "X", "buy", 1.0, self.book(NOW))   # passed the check first
            self.assertEqual((ra["status"], rb["status"]), ("filled", "duplicate"))
            self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_fills")[0], 1)
            chains, triggers = self.db.verify()
            self.assertTrue(triggers)
            self.assertEqual({t: bad for t, (_, bad) in chains.items() if bad is not None}, {})
        finally:
            other.close()

    def test_cleared_interleaved_writers_keep_every_hash_chain(self):
        led = self.ledger()
        other = DB(self.db.path)
        try:
            for k in range(6):
                (self.db if k % 2 else other).append("sim_equity", exp_id=led, ts=int(NOW + k), equity=1.0, cash=1.0,
                                                     exposure=0.0, peak=1.0, drawdown=0.0)
            chains, _ = other.verify()
            self.assertEqual(chains["sim_equity"], (6, None))
        finally:
            other.close()

    def test_confirmed_fixed_a_maker_order_cannot_fill_on_an_older_print(self):
        """on_trade (no live caller today; 0 maker orders in the real DB) filled a resting maker order on a print
        time-stamped before the order existed: a look-back fill."""
        led = self.ledger()
        eng = PaperEngine(self.db, lambda: NOW)
        eng.submit_maker(led, "m1", "X", "buy", 1.0, 100.0, self.book(NOW))
        self.assertEqual(eng.on_trade("X", "old", NOW - 60, 99.0, 5.0), [])          # before the order: never
        self.assertEqual(len(eng.on_trade("X", "new", NOW + 60, 99.0, 5.0)), 1)      # after it: fills as before

    @unittest.expectedFailure
    def test_confirmed_stop_book_and_fill_times_are_the_pass_clock_not_the_read_time(self):
        """fetch_book stamps Book.ts with the pass's `now`, so order, fill, book_ts and the 60 s data_max_age_s guard
        all use the pass start: a book read minutes into a pass is recorded as read at its start and its age is
        always 0. Real DB: 3908/3908 sim_exec rows have book_age_s 0; the paper.order event (wall clock) is 1-168 s
        (p50 8, p99 52) after the recorded order time; 35 orders > 60 s; 1 crossed an hour, no funding effect.
        Order 67 P0-A: the real observation time is now on the book (Book.observed) and BOOK_AGE_MODE "guard" uses it;
        the default "off" keeps the pass-clock gate, so a book read 120 s before execution still trades."""
        led = self.ledger()
        with mock.patch.object(risk_mod, "WALL", lambda: NOW):         # read at the pass start
            b = pr.fetch_book("BTCUSDT", NOW, carry_market())
        with mock.patch.object(risk_mod, "WALL", lambda: NOW + 120):   # executed two minutes later
            r = PaperEngine(self.db, lambda: NOW).submit_taker(led, "o-age", "BTCUSDT", "buy", 1.0, b)
        self.assertEqual(r["status"], "refused")


# ---------------------------------------------------------------- 3/6. stale data, mark failures, gaps
class Marks(Base):
    def carry(self):
        with self.db.tx():
            self.db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                           metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(self.db, NOW - 60)
        led = {i["key"]: x for x, i in lane.started(self.db).items()}["carry90|BTCUSDT"]
        self.get = carry_market()
        self.assertEqual(lane.run_one(self.db, led, self.get, NOW)["status"], "ok")
        return led

    def events(self, led, kind=pr.MARK_FAILED):
        return self.db.q("SELECT payload FROM events WHERE kind=? AND exp_id=?", kind, led)

    def test_cleared_59d_lane_mark_failure_is_recorded(self):
        led = self.carry()
        self.get.now, self.get.spot = NOW + HOUR, DNS
        r = lane.run_one(self.db, led, self.get, NOW + HOUR)
        self.assertTrue(r["mark_failed"])
        self.assertEqual(len(self.events(led)), 1)

    def test_cleared_a_rerun_in_the_same_hour_duplicates_nothing(self):
        led = self.carry()
        n = {t: self.db.one(f"SELECT COUNT(*) FROM {t}")[0] for t in ("sim_orders", "sim_fills", "sim_equity",
                                                                       "sim_funding")}
        lane.run_one(self.db, led, self.get, NOW + 600)
        self.assertEqual(n, {t: self.db.one(f"SELECT COUNT(*) FROM {t}")[0] for t in n})

    def test_confirmed_fixed_closing_ledger_mark_failure_is_recorded(self):
        """close_ledger swallowed a failed hourly mark (marked=False, no event): a retired ledger still holding a
        leg could freeze its equity unseen, like 59-D before its fix."""
        led = self.carry()
        lane.retire(self.db, led, "human", "test", None, NOW + 60)
        self.assertIn((led, led), pr.closing_ledgers(self.db))
        t = NOW + HOUR
        self.get.now, self.get.spot = t, DNS                           # the spot leg cannot be read: no close, no mark
        r = pr.close_ledger(self.db, led, led, self.get, t)
        self.assertFalse(r["marked"])
        self.assertIn("BTCUSDT.SPOT", PaperEngine(self.db).ledger(led)["positions"])
        (e,) = self.events(led)
        self.assertEqual(json.loads(e["payload"])["error_class"], "dns")
        self.get.now, self.get.spot = t + HOUR, None                   # the spot leg closes; the final mark ends it
        r = pr.close_ledger(self.db, led, led, self.get, t + HOUR)
        self.assertTrue(r["marked"])
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertEqual(len(self.events(led, pr.MARK_RECOVERED)), 1)

    @unittest.expectedFailure
    def test_confirmed_stop_straks_mark_failure_is_silent(self):
        """straks.run_one (frozen until 20/11) swallows a failed mark into its return value; no paper.mark_failed.
        pairs.run_one has the identical pattern. Real DB: no unexplained straks/pairs mark gaps so far."""
        with self.db.tx():
            self.db.append("observations", ts=NOW - 7200, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                           metric="z_1h", value=0.0, flagged=0, payload={})
        straks.ensure(self.db, NOW - 3600)
        led = {i["key"]: x for x, i in lane.started(self.db).items()}["straks|cont"]
        with mock.patch("time.time", lambda: NOW - 600):
            self.db.event("opportunity.move", "system:scanner", None, {"instrument": "CLUSDT", "flags": ["z_1h"],
                                                                     "ret_1h": 0.03, "ret_24h": 0.01})
        base = straks_market()

        def get(path):
            if "/fapi/v1/depth" in path and get.fail:
                raise DNS
            return base(path)
        get.fail, base.now = False, NOW
        lane.run_one(self.db, led, get, NOW)
        self.assertIn("CLUSDT", PaperEngine(self.db).ledger(led)["positions"])
        get.fail, base.now = True, NOW + HOUR
        r = lane.run_one(self.db, led, get, NOW + HOUR)
        self.assertTrue(str(r["marked"]).startswith("no mark prices"))
        self.assertEqual(len(self.events(led)), 1)

    @unittest.expectedFailure
    def test_confirmed_stop_a_missing_utc_day_is_merged_into_one_daily_return(self):
        """lane.daily_returns pairs consecutive MARKED days, so a day without marks makes a two-day return count as
        one daily return in the z rule (amendment 11 'edge', 'promising'). Real DB: 9 active ledgers (6 lane, 3
        carry90) miss 2026-11-07 after the 34.7 h spot-mark outage."""
        led = self.ledger(source=None)
        d0 = int(NOW // DAY * DAY) - 5 * DAY
        for day, eq in ((0, 10_000.0), (1, 10_100.0), (3, 10_302.0)):  # day 2 has no mark
            self.db.append("sim_equity", exp_id=led, ts=d0 + day * DAY + 23 * HOUR, equity=eq, cash=eq, exposure=0.0,
                           peak=eq, drawdown=0.0)
        self.assertEqual(len(lane.daily_returns(self.db, led, d0 + 4 * DAY + HOUR)), 1)


# ---------------------------------------------------------------- 9. lane report vs reportcheck
class ReportOrder(Base):
    def test_confirmed_fixed_reportcheck_reads_latest_by_id_like_the_report(self):
        """lane.report and Risk.paused take the latest row by id; reportcheck took it by ts. A row written later with
        an older pass clock made the independent check disagree with a correct report. Real DB: 0 inversions."""
        led = self.ledger(source=None)
        day = datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%d")
        Risk(self.db, lambda: NOW + 100).pause(led, "data_fetch", None, None, "fixture")
        Risk(self.db, lambda: NOW + 50).resume_simulated(led, "human:test", "resumed in the fixture")
        for ts, eq in ((NOW + 200, 10_050.0), (NOW + 100, 10_020.0)):  # the later row carries the older clock
            self.db.append("sim_equity", exp_id=led, ts=int(ts), equity=eq, cash=10_000.0, exposure=0.0,
                           peak=10_050.0, drawdown=0.0)
        self.assertFalse(Risk(self.db, lambda: NOW).paused(led))
        out = lane.report(self.db, day)
        art = pipeline.save_artifact(lane.REPORT_DIR, day, out)
        self.db.event("research.lane_report", "system:test", None,
                      {"day": day, "accounts": len(out["accounts"]), "met": out["met"],
                       "net_total": out["net_total"], "decisional": False, "artifact_sha256": art["sha256"]})
        (row,) = out["accounts"]
        self.assertEqual((row["status"], row["equity"]), ("aktiv", 10_020.0))
        rows = reportcheck.checks(self.db.path, day, pipeline.ARTIFACTS)
        self.assertTrue(all(ok for _, ok, _ in rows), [r for r in rows if not r[1]])


class Frozen(unittest.TestCase):
    def test_straks_and_pairs_are_untouched(self):
        for name, sha in FROZEN.items():
            with open(os.path.join(HERE, "lab", name), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), sha, name)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
