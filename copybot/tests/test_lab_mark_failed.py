"""Director orders 59-D/59-E: a failed hourly equity mark of a lane/carry account (lane.run_one and the pause path
paper_runner.mark_only) is recorded (paper.mark_failed), once per failure episode and error class, and the first real
mark after it is recorded too (paper.mark_recovered). Records only: no change to orders, fills, cash, marks, risk events
or gates. straks.py and pairs.py stay frozen (59-E). Simulated only; temporary databases; no network and no DNS."""
import hashlib
import os
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import carry90, command, lane, paper_runner as pr  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402

HOUR = 3600
NOW = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc).timestamp()
SIM_TABLES = ("sim_orders", "sim_fills", "sim_cancels", "sim_exec", "sim_equity", "sim_funding", "risk_events")
DNS = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
REFUSED = urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
LAB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab")
FROZEN = {"straks.py": "7a110f1fa20fb7d28b76269fc039eec4c75ddfa7353602f2f8824490b722a542",   # 59-E: STRAKS_CODE
          "pairs.py": "5c9b60a4314a40a5e4d517427c4960220682b8f6179a445a5554903180ce1219"}    # 59-E: PAIRS_CODE


def market(px=100.0, spread=0.02, rate=0.0001):
    """Public USD-M and spot data as the carry90 tests mock them; get.spot = None (book), "empty" (a book without
    levels: no mid) or an exception that the spot depth call raises."""
    def get(path):
        if path.startswith("https://data-api.binance.vision/api/v3/depth"):
            if isinstance(get.spot, BaseException):
                raise get.spot
            if get.spot == "empty":
                return {"bids": [], "asks": []}
            return {"bids": [[str(px - spread / 2), "1000"]], "asks": [[str(px + spread / 2), "1000"]]}
        if path.startswith("https://"):
            raise AssertionError(path)
        if "/fapi/v1/depth" in path:
            return {"bids": [[str(px - spread / 2), "1000"]], "asks": [[str(px + spread / 2), "1000"]]}
        if "klines" in path:
            start = int(get.now) // HOUR * HOUR - 1000 * HOUR
            return [[(start + i * HOUR) * 1000, px, px, px, px, 1, (start + (i + 1) * HOUR) * 1000 - 1, 100.0]
                    for i in range(1001)]
        if "fundingRate" in path:
            last = int(get.now) // (8 * HOUR) * 8 * HOUR
            return [{"fundingTime": (last - k * 8 * HOUR) * 1000, "fundingRate": str(rate)} for k in range(199, -1, -1)]
        raise AssertionError(path)
    get.now, get.spot = NOW, None
    return get


def no_network(*a, **k):
    raise AssertionError("59-D must not touch the network or DNS")


class MarkFailed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab59d")
        self.dbs = []
        self.db = self.new_db("lab.db")
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)]
        for p in self.p:
            p.start()
        pr._HOURLY.clear()
        self.get = market()

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

    def carry(self, db=None):
        """A carry lane (carry90 BTC: long spot, short perp) that opened and marked at NOW."""
        db = db or self.db
        with db.tx():
            db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                      metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(db, NOW - 60)
        led = {i["key"]: x for x, i in lane.started(db).items()}["carry90|BTCUSDT"]
        r = self.step(led, NOW, db=db)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(set(PaperEngine(db).ledger(led)["positions"]), {"BTCUSDT", "BTCUSDT.SPOT"})
        return led

    def step(self, led, t, spot=None, db=None):
        self.get.now, self.get.spot = t, spot
        return lane.run_one(db or self.db, led, self.get, t)

    def events(self, led, kind=pr.MARK_FAILED, db=None):
        return [pr._payload(r["payload"]) for r in (db or self.db).q(
            "SELECT payload FROM events WHERE kind=? AND exp_id=? ORDER BY id", kind, led)]

    def mark_events(self, db=None):
        return (db or self.db).one("SELECT COUNT(*) FROM events WHERE kind IN (?, ?)", pr.MARK_FAILED,
                                   pr.MARK_RECOVERED)[0]

    # ---------- P0 / P1 ----------
    def test_successful_marks_write_no_event_and_say_so(self):
        led = self.carry()
        for k in (1, 2, 3):
            r = self.step(led, NOW + k * HOUR)
            self.assertEqual((r["status"], r["marked"], r["run_completed"], r["mark_succeeded"], r["mark_failed"]),
                             ("ok", True, True, True, False))
        r = self.step(led, NOW + 3 * HOUR + 60)                      # already marked this hour: no mark was due
        self.assertEqual((r["marked"], r["mark_succeeded"], r["mark_failed"]), (False, False, False))
        self.assertEqual(self.mark_events(), 0)

    def test_dns_failure_writes_one_event_with_the_last_good_mark(self):
        led = self.carry()
        t = NOW + HOUR
        r = self.step(led, t, spot=DNS)
        self.assertEqual(r["status"], "ok")                          # unchanged for existing consumers
        self.assertTrue(r["marked"].startswith("no mark prices: URLError"))
        self.assertEqual((r["run_completed"], r["mark_succeeded"], r["mark_failed"]), (True, False, True))
        (e,) = self.events(led)
        self.assertEqual((e["ledger"], e["t"], e["marked"], e["simulated"]), (led, int(t), False, True))
        self.assertEqual((e["error_type"], e["error_class"]), ("URLError", "dns"))
        self.assertEqual(e["last_mark_ts"], int(NOW))
        self.assertEqual(e["last_mark_ts"], self.db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", led)[0])
        self.assertEqual((e["mark_age_s"], e["failing_since"], e["events_in_episode"]), (HOUR, int(t), 1))
        self.assertIsNone(e["previous_class"])
        row = self.db.one("SELECT actor, exp_id FROM events WHERE kind=?", pr.MARK_FAILED)
        self.assertEqual((row["actor"], row["exp_id"]), (pr.MARK_ACTOR, led))

    def test_refused_connection_is_one_connection_event(self):
        led = self.carry()
        self.step(led, NOW + HOUR, spot=REFUSED)
        (e,) = self.events(led)
        self.assertEqual((e["error_type"], e["error_class"]), ("URLError", "connection"))
        self.assertIn("Connection refused", e["error"])

    def test_a_missing_spot_price_is_no_price(self):
        led = self.carry()
        r = self.step(led, NOW + HOUR, spot="empty")
        self.assertTrue(r["mark_failed"])
        (e,) = self.events(led)
        self.assertEqual((e["error_type"], e["error_class"]), ("IndexError", "no_price"))

    def test_a_repeated_identical_failure_is_still_one_event(self):
        led = self.carry()
        for k in range(1, 6):
            r = self.step(led, NOW + k * HOUR, spot=DNS)
            self.assertTrue(r["mark_failed"])
            self.step(led, NOW + k * HOUR + 600, spot=DNS)           # a second pass in the same hour
        self.assertEqual(len(self.events(led)), 1)
        self.assertEqual(self.db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", led)[0], int(NOW))

    def test_a_new_error_class_writes_a_second_event(self):
        led = self.carry()
        self.step(led, NOW + HOUR, spot=DNS)
        self.step(led, NOW + 2 * HOUR, spot=DNS)
        self.step(led, NOW + 3 * HOUR, spot="empty")
        self.step(led, NOW + 4 * HOUR, spot="empty")
        a, b = self.events(led)
        self.assertEqual((a["error_class"], b["error_class"], b["previous_class"]), ("dns", "no_price", "dns"))
        self.assertEqual((b["failing_since"], b["events_in_episode"], b["last_mark_ts"]),
                         (int(NOW + HOUR), 2, int(NOW)))

    def test_recovery_is_a_written_mark_and_recorded_once(self):
        led = self.carry()
        self.step(led, NOW + HOUR, spot=DNS)
        self.step(led, NOW + 2 * HOUR, spot="empty")
        t = NOW + 3 * HOUR
        r = self.step(led, t)
        self.assertEqual((r["marked"], r["mark_succeeded"], r["mark_failed"]), (True, True, False))
        (rec,) = self.events(led, pr.MARK_RECOVERED)
        self.assertEqual((rec["ledger"], rec["first_mark_ts"], rec["failing_since"], rec["failure_duration_s"]),
                         (led, int(t), int(NOW + HOUR), 2 * HOUR))
        self.assertEqual((rec["last_mark_before_ts"], rec["mark_gap_s"], rec["error_class"], rec["events_in_episode"]),
                         (int(NOW), 3 * HOUR, "no_price", 2))
        self.assertEqual((rec["marked"], rec["simulated"]), (True, True))
        self.step(led, NOW + 4 * HOUR)                               # further successes: nothing more
        self.assertEqual(len(self.events(led, pr.MARK_RECOVERED)), 1)
        self.step(led, NOW + 5 * HOUR, spot=DNS)                     # a new failure after the recovery: recorded
        self.assertEqual(len(self.events(led)), 3)
        self.assertEqual(self.events(led)[-1]["events_in_episode"], 1)

    def test_a_pass_with_no_mark_due_is_not_a_recovery(self):
        led = self.carry()
        self.step(led, NOW + HOUR, spot=DNS)
        with mock.patch.object(pr, "_mark_hourly", lambda *a, **k: False):    # nothing due: no mark written
            r = self.step(led, NOW + 2 * HOUR)
        self.assertEqual((r["mark_succeeded"], r["mark_failed"]), (False, False))
        self.assertEqual(self.events(led, pr.MARK_RECOVERED), [])

    def test_the_error_text_is_safe(self):
        led = self.carry()
        err = urllib.error.URLError(ValueError(
            "GET https://user:pw@data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=20&apiKey=abc123 failed; "
            "token=sekret Bearer eyJhbGciOiJIUzI1NiJ9 sig=" + "f" * 64))
        self.step(led, NOW + HOUR, spot=err)
        (e,) = self.events(led)
        s = e["error"]
        self.assertIn("https://data-api.binance.vision", s)
        for bad in ("/api/v3", "symbol=", "abc123", "sekret", "eyJhbGciOiJIUzI1NiJ9", "f" * 32, "user:pw", "?"):
            self.assertNotIn(bad, s)
        self.assertLessEqual(len(s), 200)

    # ---------- the pause path (paper_runner.mark_only) ----------
    def test_mark_only_records_failure_and_recovery(self):
        led = self.carry()
        Risk(self.db, lambda: NOW + 60).pause(led, "drawdown", 0.1, 0.1, "test pause (not data_fetch)")
        for k in (1, 2):
            r = self.step(led, NOW + k * HOUR, spot=REFUSED)
            self.assertEqual((r["status"], r["marked"]), ("paused", False))
            self.assertTrue(r["reason"].startswith("no mark prices: URLError"))
            self.assertEqual((r["run_completed"], r["mark_succeeded"], r["mark_failed"]), (True, False, True))
        self.assertEqual(len(self.events(led)), 1)
        r = self.step(led, NOW + 3 * HOUR)
        self.assertEqual((r["status"], r["marked"], r["mark_succeeded"]), ("paused", True, True))
        (rec,) = self.events(led, pr.MARK_RECOVERED)
        self.assertEqual(rec["first_mark_ts"], int(NOW + 3 * HOUR))

    def test_mark_only_called_directly_for_a_held_experiment_ledger(self):
        led = self.carry()
        self.get.now, self.get.spot = NOW + HOUR, DNS
        r = pr.mark_only(self.db, led, self.get, NOW + HOUR)
        self.assertEqual((r["status"], r["mark_failed"]), ("paused", True))
        self.assertEqual(self.events(led)[0]["error_class"], "dns")

    def test_a_direct_mark_after_a_mark_only_failure_ends_the_episode(self):
        """E_ ledgers share mark_only; their run_one marks directly (eng.mark + note_marked) after a resume."""
        led = self.carry()
        self.get.now, self.get.spot = NOW + HOUR, DNS
        pr.mark_only(self.db, led, self.get, NOW + HOUR)
        PaperEngine(self.db, lambda: NOW + 2 * HOUR).mark(led, {"BTCUSDT": 100.0, "BTCUSDT.SPOT": 100.0})
        rec = pr.note_marked(self.db, led, NOW + 2 * HOUR)
        self.assertEqual((rec["first_mark_ts"], rec["failure_duration_s"]), (int(NOW + 2 * HOUR), HOUR))
        self.assertIsNone(pr.note_marked(self.db, led, NOW + 3 * HOUR))     # once

    def test_frozen_straks_and_pairs_are_unchanged(self):
        for name, pin in FROZEN.items():
            with open(os.path.join(LAB, name), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), pin, name)

    # ---------- no change to the books, risk or gates ----------
    def _scenario(self, db):
        led = self.carry(db)
        out = []
        for k, spot in ((1, DNS), (2, DNS), (3, "empty"), (4, REFUSED), (5, None), (6, DNS), (7, None)):
            out.append(self.step(led, NOW + k * HOUR, spot=spot, db=db))
        return led, out

    def test_books_risk_and_hashes_match_the_behaviour_before_59d(self):
        new_db, old_db = self.db, self.new_db("before.db")
        with mock.patch("time.time", lambda: NOW + 10 * HOUR):
            led, new = self._scenario(new_db)
            with mock.patch.object(pr, "note_mark_failed", lambda *a, **k: None), \
                    mock.patch.object(pr, "note_marked", lambda *a, **k: None):
                led_old, old = self._scenario(old_db)
        self.assertEqual(led, led_old)
        for t in SIM_TABLES:
            q = f"SELECT * FROM {t} ORDER BY id"
            self.assertEqual([tuple(r) for r in new_db.q(q)], [tuple(r) for r in old_db.q(q)], t)
        self.assertEqual(PaperEngine(new_db).ledger(led), PaperEngine(old_db).ledger(led))
        drop = ("run_completed", "mark_succeeded", "mark_failed")
        self.assertEqual([{k: v for k, v in r.items() if k not in drop} for r in new],
                         [{k: v for k, v in r.items() if k not in drop} for r in old])
        self.assertTrue(all(r["status"] == "ok" for r in new))          # fleet.paper_pass degrades only on
        self.assertFalse(any(r["status"] in ("blocked", "error") for r in new))   # blocked/error: unchanged
        self.assertEqual(self.mark_events(old_db), 0)
        self.assertEqual([e["error_class"] for e in self.events(led, db=new_db)], ["dns", "no_price", "connection",
                                                                                     "dns"])
        self.assertEqual(len(self.events(led, pr.MARK_RECOVERED, db=new_db)), 2)
        for d in (new_db, old_db):
            self.assertFalse(Risk(d).fail_closed())
            self.assertFalse(Risk(d).paused(led))
            self.assertEqual(d.one("SELECT COUNT(*) FROM risk_events WHERE action IN ('PAUSE', 'FAIL_CLOSED')")[0], 0)
            self.assertEqual(d.one("SELECT COUNT(*) FROM events WHERE kind IN ('paper.error', 'risk.pause', "
                                   "'risk.fail_closed')")[0], 0)
            chains, triggers = d.verify()                              # every hash chain intact
            self.assertTrue(triggers)
            self.assertEqual({t: bad for t, (_, bad) in chains.items() if bad is not None}, {})

    def test_mark_events_are_not_agent_output(self):
        self.assertIn(pr.MARK_FAILED, command.NOT_OUTPUT)
        self.assertIn(pr.MARK_RECOVERED, command.NOT_OUTPUT)


class ErrorClass(unittest.TestCase):
    def test_classes_from_the_exception_alone(self):
        with mock.patch("socket.getaddrinfo", no_network):
            cases = [(socket.gaierror(-2, "Name or service not known"), "dns"), (DNS, "dns"),
                     (urllib.error.URLError("[Errno -3] Temporary failure in name resolution"), "dns"),
                     (REFUSED, "connection"), (ConnectionResetError(104, "reset"), "connection"),
                     (urllib.error.URLError(TimeoutError("timed out")), "timeout"), (TimeoutError(), "timeout"),
                     (urllib.error.HTTPError("https://x.invalid/a?b=1", 451, "Unavailable", {}, None), "http"),
                     (IndexError("tuple index out of range"), "no_price"), (KeyError("bids"), "no_price"),
                     (ValueError("could not convert"), "no_price"), (RuntimeError("x"), "other")]
            for e, want in cases:
                self.assertEqual(pr.mark_error_class(e), want, repr(e))

    def test_a_chained_cause_is_followed(self):
        try:
            try:
                raise socket.gaierror(-2, "Name or service not known")
            except OSError as inner:
                raise RuntimeError("fetch failed") from inner
        except RuntimeError as e:
            self.assertEqual(pr.mark_error_class(e), "dns")


if __name__ == "__main__":
    unittest.main()
