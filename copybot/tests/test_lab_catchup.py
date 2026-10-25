"""Amendment 21z: in-window catch-up scans for markets whose hourly scan failed, the pre-weekend readiness check and
its Friday alert, and the weekend guard on `lab stop`. Synthetic data only."""
import datetime as dt
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, fundsettle, k1k2, moves, scanner  # noqa: E402
from lab import __main__ as cli  # noqa: E402
from lab.db import DB  # noqa: E402
from tests.test_lab_k1k2 import plant  # noqa: E402
from tests.test_lab_moves import NOW, market  # noqa: E402

H = 3600
CLOSE = NOW - 120
T = lambda s: int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())


class Clock:
    """A fake clock; wait() advances it and reports whether the fleet is stopping."""
    def __init__(self, t, stopping=False):
        self.t, self.stopping, self.waits = t, stopping, []

    def __call__(self):
        return self.t

    def wait(self, s):
        self.waits.append(s)
        self.t += s
        return self.stopping


def run_pass(db, get, clock):
    real_run = scanner.run
    with mock.patch.object(scanner, "run", lambda db, now: real_run(db, names=["abnormal_move"], get=get, now=now)), \
            mock.patch.object(scanner, "http_get", get), \
            mock.patch.object(fundsettle, "run", lambda db, get: {"stored": 0}):
        return fleet.scanner_pass(db, clock=clock, wait=clock.wait)


def flaky(fail_times):
    """market() whose fetches for a symbol fail its first `fail_times[sym]` scans (a scan = its klines call)."""
    left, good = dict(fail_times), market()

    def get(url):
        sym = url.split("symbol=")[1].split("&")[0]
        if left.get(sym):
            if "/klines" in url:
                left[sym] -= 1
            raise OSError("No route to host")
        return good(url)
    return get


class CatchUp(unittest.TestCase):
    def test_a_failed_market_is_rescanned_in_the_window_and_becomes_the_hours_scan(self):
        db, clock = DB(":memory:"), Clock(NOW)
        res = run_pass(db, flaky({"BTCUSDT": 2}), clock)
        self.assertEqual([r["attempt"] for r in res["catch_up"]], [1, 2])
        self.assertEqual(res["catch_up"][0]["markets"], ["BTCUSDT"])                 # only the failed market
        self.assertEqual(res["catch_up"][1]["failed"], [])
        o = CLOSE - H
        h = k1k2.hours(db, "BTCUSDT")[o]
        self.assertEqual((h["scan_ts"], h["usable"], h["catch_up"]), (NOW + 240, True, True))
        self.assertLessEqual(h["scan_ts"] - CLOSE, scanner.CATCHUP_LAST_S)
        self.assertEqual(db.one("SELECT COUNT(*) FROM observations WHERE instrument='SPYUSDT' AND metric='z_1h'")[0], 1)
        tag = db.one("SELECT payload FROM observations WHERE instrument='BTCUSDT' AND metric='z_1h'")[0]
        self.assertIn('"after_error_ts":%d' % NOW, tag)
        r = k1k2.readiness(db, NOW + 600)["weekends"]
        self.assertTrue(all(w["markets"]["BTCUSDT"]["catch_up"] <= 1 for w in r))

    def test_at_most_three_attempts_and_none_after_close_plus_480(self):
        db, clock = DB(":memory:"), Clock(NOW)
        res = run_pass(db, flaky({"SPYUSDT": 99}), clock)
        self.assertEqual(len(res["catch_up"]), 3)
        self.assertEqual(res["catch_up"][-1]["ts"] - CLOSE, 480)
        self.assertEqual(res["catch_up"][-1]["failed"], ["SPYUSDT"])
        self.assertNotIn(CLOSE - H, k1k2.hours(db, "SPYUSDT"))                       # the hour stays lost

    def test_no_catch_up_mid_hour_while_stopping_or_for_short_history(self):
        db, clock = DB(":memory:"), Clock(NOW + 1500)                                 # a start-up scan at HH:27
        self.assertEqual(run_pass(db, flaky({"BTCUSDT": 1}), clock)["catch_up"], [])
        self.assertEqual(clock.waits, [])
        db, clock = DB(":memory:"), Clock(NOW, stopping=True)
        self.assertEqual(run_pass(db, flaky({"BTCUSDT": 1}), clock)["catch_up"], [])
        db, clock = DB(":memory:"), Clock(NOW)
        good = market(short=("XAUUSDT",))
        self.assertEqual(run_pass(db, good, clock)["catch_up"], [])                  # history_short is not a failure
        self.assertEqual(scanner.failed_moves(db, NOW), set())

    def test_a_failing_detector_retries_every_market(self):
        db = DB(":memory:")
        db.append("observations", ts=NOW, detector="abnormal_move/1", source="detector", instrument=None,
                  metric="error", value=None, threshold=None, flagged=0, payload={"error": "x"})
        self.assertEqual(scanner.failed_moves(db, NOW), set(moves.WATCH))


class Preflight(unittest.TestCase):
    def test_ready_risk_and_one_alert_per_weekend(self):
        db = DB(":memory:")
        plant(db, weeks=1)                                                            # Mon 2026-11-02 .. Sun 11-08
        now = T("2026-11-06T13:00")
        p = k1k2.preflight(db, now)
        self.assertEqual((p["weekend"], p["status"], p["calendar_ok"]), ("2026-11-07", "KLAR", True))
        self.assertEqual(p["markets"]["SPYUSDT"]["hours"], 71)   # the 12:00 bar is not yet 600 s past its close
        self.assertNotIn("net", str(p))
        db = DB(":memory:")                                                           # SPY misses its last 10 hours
        for o in range(now - 80 * H, now - H, H):
            for sym in ("BTCUSDT", "SPYUSDT", "QQQUSDT"):
                if sym == "SPYUSDT" and o >= now - 11 * H:
                    continue
                db.append("observations", ts=o + H + 120, detector="abnormal_move/1", source="t", instrument=sym,
                          metric="z_1h", value=0.0, threshold=4, flagged=0,
                          payload={"open_s": o, "close_s": o + H, "ret_1h": 0.0, "price": 1.0, "mark": 1.0,
                                   "index": 1.0, "quality": {"missing_bars": 0}})
        p = k1k2.preflight(db, now)
        self.assertEqual(p["status"], "RISIKO")
        self.assertTrue(any(r.startswith("SPYUSDT") for r in p["reasons"]))
        self.assertIn("seneste scanning", " ".join(k1k2.preflight(db, now + 5 * H)["reasons"]))
        self.assertIsNone(k1k2.preflight_alert(db, T("2026-11-06T11:00")))           # before Friday 12:00 UTC
        self.assertEqual(k1k2.preflight_alert(db, now)["status"], "RISIKO")
        self.assertIsNone(k1k2.preflight_alert(db, now + H))                         # once per weekend
        self.assertIsNone(k1k2.preflight_alert(db, T("2026-11-09T13:00")))           # Monday
        self.assertEqual(db.one("SELECT COUNT(*) FROM events WHERE kind='research.k_preflight'")[0], 1)
        from lab import events
        ev = [e for e in events.view(db)["events"] if e["kind"] == "k_preflight"]
        self.assertEqual((len(ev), ev[0]["title"]), (1, "K1/K2-weekend 2026-11-07: RISIKO"))
        self.assertEqual(k1k2._next_saturday(T("2026-11-08T23:00")).isoformat(), "2026-11-07")   # Sunday: this one
        self.assertFalse(k1k2.preflight(db, T("2027-07-02T13:00"))["calendar_ok"])   # beyond the NYSE list


class StopGuard(unittest.TestCase):
    def test_weekend_minutes_0_to_12_are_refused_without_the_flag(self):
        self.assertTrue(cli.weekend_scan_window(T("2026-10-31T10:05")))
        self.assertFalse(cli.weekend_scan_window(T("2026-10-31T10:13")))
        self.assertFalse(cli.weekend_scan_window(T("2026-10-30T10:05")))             # Friday
        self.assertTrue(cli.weekend_scan_window(T("2026-11-01T23:00")))
        out = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cli.time, "time", return_value=T("2026-10-31T10:05")):
            path = os.path.join(d, "lab.db")
            DB(path)
            self.assertEqual(cli.main(["stop", "--reason", "test"], db_path=path, out=out.append), 2)
        self.assertIn("21z", out[0])


if __name__ == "__main__":
    unittest.main()
