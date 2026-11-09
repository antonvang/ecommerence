"""Director order 68 (research/desk/PAPER_ENGINE_REMEDIATION_67.md, section "Ordre 68"): correctness gates.

- P0 MEASURE parity: a 28-pass, multi-hour scenario over a lane (spot/perp), three carry90, the two STRAKS and the
  PAR-BOG accounts (run as they are: lab/straks.py and lab/pairs.py are executed, never modified), with data failures,
  a pause, an auto-resume, mark failures and a same-hour rerun. BOOK_AGE_MODE "measure" must leave every sim_* row
  (sim_exec: all but its three new fields), every risk_events row, every event and every return dict identical to "off".
- P2 FUNDING fail_closed: missing bar, missing rate, unknown interval, interval change, recovery, idempotency, no double
  settlement, and the effect on a booking-dependent rule. Default stays "legacy".
Synthetic data, temporary databases, no network, no DNS."""
import json
import math
import os
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from dataclasses import asdict
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lab import carry90, lane, pairs, paper, paper_runner as pr, straks  # noqa: E402
from lab import risk as risk_mod  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import CostModel, PaperEngine  # noqa: E402

HOUR, DAY = 3600, 86400
T0 = datetime(2026, 11, 5, 21, 0, 30, tzinfo=timezone.utc).timestamp()
DNS = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
BASE = {"BTCUSDT": 70_000.0, "ETHUSDT": 2_500.0, "XAUUSDT": 2_600.0, "PAXGUSDT": 2_601.0, "ADAUSDT": 0.5,
        "LINKUSDT": 15.0, "CLUSDT": 70.0, "BZUSDT": 74.0, "QQQUSDT": 500.0, "SPYUSDT": 580.0, "XAGUSDT": 31.0}
NEW_FIELDS = ("book_observed_wall", "exec_wall", "book_age_exec_s")
SIM = ("sim_orders", "sim_fills", "sim_cancels", "sim_equity", "sim_funding", "risk_events")


def no_network(*a, **k):
    raise AssertionError("order 68 tests must not touch the network or DNS")


def px(sym, t):
    """Deterministic prices: a daily wave per symbol and a short BZ premium around T0 (so PAR-BOG enters and exits)."""
    phase = sorted(BASE).index(sym) * 0.7
    spike = 1.012 if sym == "BZUSDT" and T0 - 2 * HOUR <= t < T0 + 5 * HOUR else 1.0
    return BASE[sym] * (1 + 0.01 * math.sin(2 * math.pi * t / DAY + phase)) * spike


class Market:
    """Fake public REST for every path the scenario reaches. fail: set of "klines", "spot", "perp_depth"."""
    def __init__(self):
        self.now, self.fail, self._bars = T0, set(), {}

    def depth(self, sym):
        p = px(sym, self.now)
        return {"bids": [[str(p * (1 - 1e-4 * k)), "1000"] for k in range(1, 4)],
                "asks": [[str(p * (1 + 1e-4 * k)), "1000"] for k in range(1, 4)]}

    def __call__(self, path):
        if path.startswith("https://data-api.binance.vision/api/v3/depth"):
            if "spot" in self.fail:
                raise DNS
            return self.depth(path.split("symbol=")[1].split("&")[0])
        if path.startswith("https://"):
            raise AssertionError(path)
        sym = path.split("symbol=")[1].split("&")[0]
        if "/fapi/v1/depth" in path:
            if "perp_depth" in self.fail:
                raise DNS
            return self.depth(sym)
        if "klines" in path:
            if "klines" in self.fail:
                raise DNS
            hour = int(self.now) // HOUR * HOUR
            key = (sym, hour)
            if key not in self._bars:
                start = hour - 1000 * HOUR
                self._bars[key] = [[(start + i * HOUR) * 1000, px(sym, start + i * HOUR), 0, 0,
                                    px(sym, start + (i + 1) * HOUR), 1, (start + (i + 1) * HOUR) * 1000 - 1, 1e6]
                                   for i in range(1001)]
            return self._bars[key]
        if "fundingRate" in path:
            if "klines" in self.fail:
                raise DNS
            last = int(self.now) // (8 * HOUR) * 8 * HOUR
            return [{"fundingTime": (last - k * 8 * HOUR) * 1000, "fundingRate": "0.0003"} for k in range(199, -1, -1)]
        raise AssertionError(path)


# (pass time, failures) - 28 passes: hourly, a same-hour rerun, a klines/funding outage (pause, probes, auto-resume),
# a spot outage (mark failures), a perp-book outage (orders not sent), straks exits after 24 h
PASSES = [(T0 + h * HOUR, set()) for h in range(27)]
PASSES[6] = (T0 + 6 * HOUR, {"klines"})
PASSES[10] = (T0 + 10 * HOUR, {"spot"})
PASSES[14] = (T0 + 14 * HOUR, {"perp_depth"})
PASSES.insert(13, (T0 + 12 * HOUR + 1800, set()))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab68")
        self.dbs = []
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)]
        for p in self.p:
            p.start()
        pr._HOURLY.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        for d in self.dbs:
            d.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def new_db(self, name):
        d = DB(os.path.join(self.tmp, name))
        self.dbs.append(d)
        return d


# ======================================================================= P0 MEASURE parity
class MeasureParity(Base):
    def setup_books(self, db):
        with db.tx():
            for det, inst in (("census/1", "binance"), ("abnormal_move/1", "CLUSDT")):
                db.append("observations", ts=int(T0 - 7200), detector=det, source="x", instrument=inst,
                          metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(db, T0 - 60)
        straks.ensure(db, T0 - 3600)
        pairs.ensure(db, T0 - 3600)
        db.event("lane.started", lane.ACTOR, lane.ledger_id("fcarry.carry_filter|parity"), {
            "key": "fcarry.carry_filter|parity", "family": "fcarry", "function": "carry_filter",
            "params": {"lookback_days": 7, "enter_apr": 0.1}, "coins": ["ADAUSDT", "LINKUSDT"],
            "evaluated_coins": ["ADAUSDT", "LINKUSDT"], "expectation": None, "capital": lane.CAPITAL,
            "t": int(T0 - 60), "costs": lane.COSTS.__dict__, "label": lane.LABEL, "simulated": True})
        for at, sym, r1 in ((T0 - 600, "CLUSDT", 0.03), (T0 + 3 * HOUR - 600, "BTCUSDT", 0.02),
                            (T0 + 5 * HOUR - 600, "ETHUSDT", -0.025)):
            with mock.patch("time.time", lambda: at):
                db.event("opportunity.move", "system:scanner", None, {"instrument": sym, "flags": ["z_1h"],
                                                                    "ret_1h": r1, "ret_24h": 0.0})

    def scenario(self, db, mode):
        self.setup_books(db)
        get, results = Market(), []
        with mock.patch.object(risk_mod, "BOOK_AGE_MODE", mode):
            for t, fail in PASSES:
                get.now, get.fail, books = t, fail, {}                 # one shared book cache per pass, as pr.run
                for led in lane.active(db):
                    results.append((t, led, pr._guarded(db, led, lambda: lane.run_one(db, led, get, t, None, books))))
        return results

    def rows(self, db, table):
        return [dict(r) for r in db.q(f"SELECT * FROM {table} ORDER BY id")]

    def test_measure_changes_nothing_but_the_three_sim_exec_fields(self):
        off, meas = self.new_db("off.db"), self.new_db("measure.db")
        r_off, r_meas = self.scenario(off, "off"), self.scenario(meas, "measure")
        self.assertEqual(r_off, r_meas)                                            # every return dict
        for t in SIM:                                                              # every row, hashes included
            self.assertEqual(self.rows(off, t), self.rows(meas, t), t)
        ev = lambda d: [(r["kind"], r["actor"], r["exp_id"], r["payload"]) for r in d.q(  # noqa: E731
            "SELECT kind, actor, exp_id, payload FROM events ORDER BY id")]            # (ts is the wall clock)
        self.assertEqual(ev(off), ev(meas))
        xo, xm = self.rows(off, "sim_exec"), self.rows(meas, "sim_exec")
        self.assertEqual(len(xo), len(xm))
        for a, b in zip(xo, xm):
            pa, pb = json.loads(a.pop("payload")), json.loads(b.pop("payload"))
            for r in (a, b):
                r.pop("hash"), r.pop("prev_hash")                                  # differ only through the payload
            self.assertEqual(a, b)
            self.assertFalse(set(NEW_FIELDS) & set(pa))
            self.assertEqual(pa, {k: v for k, v in pb.items() if k not in NEW_FIELDS})
            self.assertTrue(all(k in pb for k in NEW_FIELDS))
        # the scenario really reached every path
        src = {led: (i.get("source") or "lane") for led, i in lane.started(off).items()}
        traded = {src[r[0]] for r in off.q("SELECT DISTINCT exp_id FROM sim_fills")}
        self.assertEqual(traded, {"lane", "carry90", "straks", "pairs"})
        kinds = {r[0] for r in off.q("SELECT DISTINCT kind FROM events")}
        self.assertTrue({"paper.mark_failed", "paper.mark_recovered", "paper.error", "risk.pause", "risk.clear"}
                        <= kinds, kinds)
        self.assertTrue(off.one("SELECT COUNT(*) FROM sim_funding")[0] > 0)
        self.assertTrue(off.one("SELECT 1 FROM sim_orders WHERE order_id LIKE '%|exit|%'"))      # straks 24 h exits
        self.assertTrue(off.one("SELECT 1 FROM sim_orders WHERE order_id LIKE '%|out|%'"))       # PAR exit
        self.assertTrue(any(isinstance(r[2].get("orders"), list) and any("not sent" in str(o.get("status"))
                                                                         for o in r[2]["orders"]) for r in r_off))


# ======================================================================= P2 FUNDING fail_closed
COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.0004)
NOW = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc).timestamp()
H8 = 8 * HOUR


class Funding(Base):
    def setUp(self):
        super().setUp()
        self.db = self.new_db("lab.db")

    def ledger(self, led="LANE_68f0000001", db=None):
        db = db or self.db
        db.event("lane.started", "system:lane", led, {"key": led, "source": "scanner", "coins": ["X"],
                                                      "capital": 10_000.0, "t": int(NOW - 5 * DAY)})
        db.event("paper.started", "system:test", led, {"capital": 10_000.0, "costs": asdict(COSTS), "simulated": True})
        return led

    def fill(self, led, ts, side, qty, px_=100.0, inst="X"):
        oid = f"{led}|{int(ts)}|{inst}|{side}"
        with self.db.tx():
            self.db.append("sim_orders", order_id=oid, exp_id=led, ts=int(ts), instrument=inst, side=side, qty=qty,
                           limit_px=None, style="taker", reduce_only=0, signal_ref="test", cost_model=asdict(COSTS))
            self.db.append("sim_fills", fill_id=f"{oid}|0", order_id=oid, exp_id=led, ts=int(ts), instrument=inst,
                           side=side, px=px_, qty=qty, fee=0.0, slippage=0.0, liquidity="taker", mid=px_,
                           book_ts=int(ts))

    def grid(self, n=10, end=None, drop=(), step=H8):
        end = end or int(NOW) // H8 * H8
        return {end - k * step: 0.0001 for k in range(n) if end - k * step not in drop}

    def opens(self, lo, drop=()):
        return {t: 100.0 for t in range(int(lo) // HOUR * HOUR, int(NOW), HOUR) if t not in drop}

    def book(self, mode, data, t_f, now=NOW, db=None):
        with mock.patch.object(paper, "FUNDING_MISSING_MODE", mode):
            eng = PaperEngine(db or self.db, lambda: now)
            out = eng.book_funding(self.led, data, t_f)
            return out, pr.funding_fields(eng) if mode != "legacy" else {}, eng

    def booked(self, db=None):
        return sorted(r[0] for r in (db or self.db).q("SELECT settle_ts FROM sim_funding WHERE exp_id=?", self.led))

    def missing(self, state=None):
        rows = [json.loads(r[0]) for r in self.db.q("SELECT payload FROM events WHERE kind=?", paper.FUNDING_MISSING)]
        return [r for r in rows if state is None or r["state"] == state]

    def start(self, t_f_back=4 * DAY):
        self.led = self.ledger()
        t_f = int(NOW - t_f_back)
        self.db.event("paper.funding_started", "agent:paper-1", None, {"t_f": t_f})     # what reconcile checks
        self.fill(self.led, t_f + 60, "buy", 1.0)                    # held from just after T_F
        return t_f

    def window(self, t_f):
        last = int(NOW) // H8 * H8
        return [t for t in range(last - 20 * H8, last + 1, H8) if t_f < t <= NOW]

    # --- missing settlement bar
    def test_missing_bar_same_booking_in_both_modes_visible_only_in_fail_closed(self):
        t_f = self.start()
        win = self.window(t_f)
        hole = win[3]
        data = {"X": (self.grid(20), self.opens(t_f - DAY, drop={hole}))}
        legacy, _, _ = self.book("legacy", data, t_f)
        self.assertEqual(self.booked(), win[:3])                      # legacy waits silently at the hole
        out, f, _ = self.book("fail_closed", data, t_f)
        self.assertEqual((out, self.booked()), ([], win[:3]))          # the same booking: nothing behind the hole
        self.assertEqual((f["funding_status"], [m["settle_ts"] for m in self.missing("MISSING_BAR")]),
                         ("ERROR", [hole]))

    # --- missing rate in the middle of the series
    def test_missing_rate_legacy_skips_it_fail_closed_holds_everything_after_it(self):
        t_f = self.start()
        win = self.window(t_f)
        hole = win[4]
        data = {"X": (self.grid(20, drop={hole}), self.opens(t_f - DAY))}
        legacy_db = self.new_db("legacy.db")
        led = self.ledger(self.led, db=legacy_db)
        self.assertEqual(led, self.led)
        self.db, keep = legacy_db, self.db
        self.fill(self.led, t_f + 60, "buy", 1.0)
        self.book("legacy", data, t_f)
        self.assertEqual(self.booked(), [t for t in win if t != hole])     # legacy: the hole is simply never booked
        self.db = keep
        _, f, _ = self.book("fail_closed", data, t_f)
        self.assertEqual(self.booked(), win[:4])                       # BOOKING DIFFERENCE: nothing at/after the hole
        (m,) = self.missing("MISSING_RATE")
        self.assertEqual((m["settle_ts"], m["interval_h"], m["next_known_ts"], f["funding_status"]),
                         (hole, 8, win[5], "ERROR"))
        data_full = {"X": (self.grid(20), self.opens(t_f - DAY))}      # recovery: the rate appears later
        out, f, _ = self.book("fail_closed", data_full, t_f)
        self.assertEqual(self.booked(), win)
        self.assertEqual(([o["settle_ts"] for o in out], f["funding_status"]), (win[4:], "OK"))

    def test_a_missing_rate_while_flat_is_no_error(self):
        t_f = self.start()
        win = self.window(t_f)
        self.fill(self.led, win[1] + 60, "sell", 1.0)                  # flat from after the 2nd settlement
        _, f, _ = self.book("fail_closed", {"X": (self.grid(20, drop={win[3]}), self.opens(t_f - DAY))}, t_f)
        self.assertEqual((self.booked(), f["funding_status"], self.missing()), (win[:2], "OK", []))

    # --- unknown funding interval
    def test_unknown_interval_legacy_books_fail_closed_waits_then_recovers(self):
        t_f = self.start(t_f_back=10 * HOUR)
        st = int(NOW) // H8 * H8
        one = {"X": ({st: 0.0001}, self.opens(t_f - DAY))}             # a new listing: one settlement known
        legacy_db = self.new_db("legacy.db")
        self.db, keep = legacy_db, self.db
        self.ledger(self.led, db=legacy_db)
        self.fill(self.led, t_f + 60, "buy", 1.0)
        self.book("legacy", one, t_f)
        self.assertEqual(self.booked(), [st])
        self.db = keep
        _, f, _ = self.book("fail_closed", one, t_f)
        self.assertEqual((self.booked(), f["funding_status"]), ([], "ERROR"))      # BOOKING DIFFERENCE (delay)
        self.assertEqual(len(self.missing("UNKNOWN_INTERVAL")), 1)
        three = {"X": ({st - 2 * H8: 0.0001, st - H8: 0.0001, st: 0.0001}, self.opens(t_f - DAY))}
        out, f, _ = self.book("fail_closed", three, t_f)                # the interval is known: books in order
        self.assertEqual((self.booked(), f["funding_status"]), ([st], "OK"))

    def test_an_interval_increase_is_held_back_until_the_series_shows_it(self):
        """4 h -> 8 h: the new 8 h gaps look like missing 4 h rates until most of the last 10 gaps are 8 h. A false
        MISSING_RATE delays funding (here: until the series catches up); legacy books at once."""
        t_f = self.start(t_f_back=3 * DAY)
        end = int(NOW) // H8 * H8
        old = {end - 2 * H8 - k * 4 * HOUR: 0.0001 for k in range(20)}             # 4-hourly before
        new = {end - H8: 0.0001, end: 0.0001}                                        # then 8-hourly
        _, f, _ = self.book("fail_closed", {"X": ({**old, **new}, self.opens(t_f - DAY))}, t_f)
        self.assertEqual(f["funding_status"], "ERROR")
        self.assertEqual(self.missing("MISSING_RATE")[0]["interval_h"], 4)
        self.assertNotIn(end, self.booked())
        later = {**{end + k * H8: 0.0001 for k in range(1, 8)}, **new, **old}       # 8 h now dominates the last 10
        with mock.patch.object(paper, "FUNDING_MISSING_MODE", "fail_closed"):
            eng = PaperEngine(self.db, lambda: NOW + 8 * H8)
            eng.book_funding(self.led, {"X": (later, {t: 100.0 for t in range(int(t_f) // HOUR * HOUR - DAY,
                                                                                  int(NOW + 8 * H8), HOUR)})}, t_f)
        self.assertIn(end, self.booked())                               # recovered, in order

    # --- idempotency and no double settlement
    def test_repeated_passes_and_two_writers_book_each_settlement_once(self):
        t_f = self.start()
        win = self.window(t_f)
        bad = {"X": (self.grid(20), self.opens(t_f - DAY, drop={win[3]}))}
        for _ in range(3):
            self.book("fail_closed", bad, t_f)
        self.assertEqual((self.booked(), len(self.missing())), (win[:3], 1))
        other = DB(self.db.path)
        try:
            good = {"X": (self.grid(20), self.opens(t_f - DAY))}
            a = self.book("fail_closed", good, t_f)[0]
            b = self.book("fail_closed", good, t_f, db=other)[0]
            c = self.book("legacy", good, t_f, db=other)[0]
        finally:
            other.close()
        self.assertEqual(([o["settle_ts"] for o in a], b, c), (win[3:], [], []))
        self.assertEqual(self.booked(), win)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM (SELECT 1 FROM sim_funding GROUP BY exp_id, instrument, "
                                     "settle_ts HAVING COUNT(*) > 1)")[0], 0)
        self.assertTrue(PaperEngine(self.db).reconcile(self.led)["ok"])
        self.assertEqual(len(self.missing()), 1)                        # the event stays as history, nothing new

    def test_spot_legs_and_flat_instruments_raise_no_error(self):
        t_f = self.start()
        self.fill(self.led, t_f + 120, "buy", 1.0, inst="X.SPOT")
        _, f, _ = self.book("fail_closed", {"X.SPOT": ({}, {}), "Y": ({}, {})}, t_f)
        self.assertEqual((f["funding_status"], self.missing()), ("OK", []))
        _, f, _ = self.book("fail_closed", {"X": ({}, self.opens(t_f - DAY))}, t_f)      # held perp, empty series
        self.assertEqual((f["funding_status"], [m["state"] for m in self.missing()], self.booked()),
                         ("ERROR", ["UNKNOWN_INTERVAL"], []))

    # --- a booking difference changes later simulated behaviour
    def test_held_back_funding_changes_the_scanner_exit_rule(self):
        """12c: a scanner position may close once a settlement after its entry is BOOKED (or after 12 h). Holding a
        settlement back (fail_closed) therefore delays that exit: a change in future simulated behaviour."""
        t_f = self.start(t_f_back=10 * HOUR)
        st = int(NOW) // H8 * H8
        entry = st - 3 * HOUR
        self.fill(self.led, entry, "sell", 1.0, inst="COINUSDT")
        one = {"COINUSDT": ({st: 0.0001}, self.opens(t_f - DAY))}
        legacy_db = self.new_db("legacy.db")
        self.db, keep = legacy_db, self.db
        self.ledger(self.led, db=legacy_db)
        self.fill(self.led, entry, "sell", 1.0, inst="COINUSDT")
        self.book("legacy", one, t_f)
        self.assertTrue(lane.settled_since_entry(self.db, self.led, "COINUSDT", NOW))
        self.db = keep
        self.book("fail_closed", one, t_f)
        self.assertFalse(lane.settled_since_entry(self.db, self.led, "COINUSDT", NOW))

    def test_report_mode_records_every_case_but_books_exactly_as_legacy(self):
        """The pure-recording variant: same events and status as fail_closed, same sim_funding rows as legacy."""
        t_f = self.start()
        win = self.window(t_f)
        st = int(NOW) // H8 * H8
        cases = [{"X": (self.grid(20, drop={win[4]}), self.opens(t_f - DAY))},          # missing rate
                 {"X": (self.grid(20), self.opens(t_f - DAY, drop={win[2]}))},          # missing bar
                 {"X": ({st: 0.0001}, self.opens(t_f - DAY))}]                           # unknown interval
        states = []
        for k, data in enumerate(cases):
            dl, dr = self.new_db(f"l{k}.db"), self.new_db(f"r{k}.db")
            for d in (dl, dr):
                self.db = d
                self.start()
            self.db = dl
            self.book("legacy", data, t_f)
            self.db = dr
            _, f, _ = self.book("report", data, t_f)
            states.append([m["state"] for m in self.missing()])
            self.assertEqual(f["funding_status"], "ERROR")
            self.assertEqual([r[0] for r in dl.q("SELECT hash FROM sim_funding ORDER BY id")],
                             [r[0] for r in dr.q("SELECT hash FROM sim_funding ORDER BY id")])
        self.assertEqual(states, [["MISSING_RATE"], ["MISSING_BAR"], ["UNKNOWN_INTERVAL"]])

    def test_default_is_legacy(self):
        self.assertEqual((paper.FUNDING_MISSING_MODE, risk_mod.BOOK_AGE_MODE, lane.DAILY_RETURNS_MODE),
                         ("legacy", "off", "legacy"))


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
