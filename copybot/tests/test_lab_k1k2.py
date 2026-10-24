"""Amendment 21y: sessions (DST, early close, holidays), settled funding forward only, and the K1/K2 screenings - a
planted weekend lead passes, noise fails, and nothing is estimated before 12 complete weekends."""
import datetime as dt
import json
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fundsettle, k1k2, sessions  # noqa: E402
from lab.db import DB  # noqa: E402

H = 3600
T = lambda s: int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())
START = T("2026-11-02T00:00")                     # a Monday


def plant(db, weeks, lead=0.003, seed=1, xau_premium=True):
    rng = random.Random(seed)
    marks = {"BTCUSDT": 80000.0, "ETHUSDT": 3000.0, "SPYUSDT": 760.0, "QQQUSDT": 600.0, "XAUUSDT": 4000.0}
    prev_sig = 0
    for i in range(weeks * 168):
        o = START + i * H
        scan = o + H + 120
        r_btc = rng.choice((-1, 1)) * 0.01
        wk = sessions.equity(o) == sessions.WEEKEND
        for sym in marks:
            if sym in ("SPYUSDT", "QQQUSDT"):
                step = (lead * prev_sig if wk else 0.0) + rng.gauss(0, 0.0005)
            else:
                step = rng.gauss(0, 0.001)
            marks[sym] *= math.exp(step)
            closed = sessions.closed("commodity", o) if sym == "XAUUSDT" else False
            prem = (0.004 if (closed and xau_premium) else 0.0005) * (1 + rng.random()) if sym == "XAUUSDT" else \
                0.0002                                                                 # placebos: flat premium
            p = {"open_s": o, "close_s": o + H, "ret_1h": r_btc if sym == "BTCUSDT" else step, "price": marks[sym],
                 "mark": marks[sym], "index": marks[sym] / (1 + prem), "quality": {"missing_bars": 0}}
            ts = scan + (1 if sym != "BTCUSDT" else 0)
            db.append("observations", ts=ts, detector="abnormal_move/1", source="t", instrument=sym, metric="z_1h",
                      value=0.0, threshold=4, flagged=0, payload=p)
            db.append("observations", ts=ts, detector="abnormal_move/1", source="t", instrument=sym, metric="book_rt",
                      value=0.0001, threshold=None, flagged=0, payload={})
        prev_sig = 1 if r_btc > 0 else -1


class Sessions(unittest.TestCase):
    def test_rth_dst_early_close_holiday_weekend(self):
        self.assertEqual(sessions.equity(T("2026-10-26T13:00")), sessions.OTHER)    # 09:00-10:00 EDT straddles open
        self.assertEqual(sessions.equity(T("2026-10-26T14:00")), sessions.RTH)
        self.assertEqual(sessions.equity(T("2026-10-26T19:00")), sessions.RTH)      # 15:00-16:00 EDT
        self.assertEqual(sessions.equity(T("2026-11-02T14:00")), sessions.OTHER)    # EST after 11-01: 09:00-10:00
        self.assertEqual(sessions.equity(T("2026-11-02T20:00")), sessions.RTH)
        self.assertEqual(sessions.equity(T("2026-11-27T17:00")), sessions.RTH)      # early close 13:00 EST
        self.assertEqual(sessions.equity(T("2026-11-27T18:00")), sessions.OTHER)
        self.assertEqual(sessions.equity(T("2026-11-26T16:00")), sessions.HOLIDAY)
        self.assertEqual(sessions.equity(T("2026-10-31T00:00")), sessions.WEEKEND)
        self.assertEqual(sessions.equity(T("2026-11-01T23:00")), sessions.WEEKEND)
        self.assertEqual(sessions.equity(T("2026-10-30T23:00")), sessions.OTHER)
        self.assertEqual(sessions.weekend_key(T("2026-11-01T05:00")), "2026-10-31")
        with self.assertRaises(ValueError):
            sessions.equity(T("2027-07-06T15:00"))                                 # no calendar: never guessed


def nyse_rules(year):
    """An independent rule-based NYSE calendar (closures, early closes) to cross-check the hand-written list."""
    d = dt.date
    obs = lambda x: x - dt.timedelta(days=1) if x.weekday() == 5 else x + dt.timedelta(days=1) if x.weekday() == 6 else x
    nth = lambda m, wd, n: [x for x in (d(year, m, k) for k in range(1, 29)) if x.weekday() == wd][n - 1]
    last = lambda m, wd: [x for x in (d(year, m, k) for k in range(1, 32) if k <= [31, 28, 31, 30, 31, 30, 31, 31,
                                                                                   30, 31, 30, 31][m - 1])
                          if x.weekday() == wd][-1]
    a, b, c = year % 19, year // 100, year % 100                    # Anonymous Gregorian Easter
    dd, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - dd - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    easter = d(year, (h + l_ - 7 * m + 114) // 31, ((h + l_ - 7 * m + 114) % 31) + 1)
    closed = {obs(d(year, 1, 1)), nth(1, 0, 3), nth(2, 0, 3), easter - dt.timedelta(days=2), last(5, 0),
              obs(d(year, 6, 19)), obs(d(year, 7, 4)), nth(9, 0, 1), nth(11, 3, 4), obs(d(year, 12, 25))}
    early = {nth(11, 3, 4) + dt.timedelta(days=1)}
    if d(year, 12, 24).weekday() < 5:
        early.add(d(year, 12, 24))
    if d(year, 7, 3).weekday() < 5:
        early.add(d(year, 7, 3))
    return {x for x in closed if x.weekday() < 5}, early


class Calendar(unittest.TestCase):
    def test_the_list_matches_an_independent_rule_based_calendar(self):     # 21y precision 3 point 4
        lo, hi = dt.date(2026, 10, 24), sessions.CALENDAR_UNTIL
        closed, early = set(), set()
        for y in (2026, 2027):
            c, e = nyse_rules(y)
            closed |= {x for x in c if lo <= x <= hi}
            early |= {x for x in e if lo <= x <= hi}
        self.assertEqual(set(sessions.NYSE_CLOSED), closed)
        self.assertEqual(set(sessions.NYSE_EARLY), early)


class Integrity(unittest.TestCase):
    def test_a_scan_before_the_close_is_never_usable_and_reasons_are_counted(self):
        db = DB(":memory:")
        o = T("2026-10-31T10:00")
        good = {"open_s": o, "close_s": o + H, "ret_1h": 0.01, "price": 1.0, "mark": 1.0, "index": 1.0,
                "quality": {"missing_bars": 0}}
        rows = [("BTCUSDT", o + H + 120, good), ("SPYUSDT", o + H - 5, good),            # before the close
                ("QQQUSDT", o + H + 900, good),                                          # late
                ("XAUUSDT", o + H + 120, dict(good, quality={"missing_bars": 2}))]
        for sym, ts, p in rows:
            db.append("observations", ts=ts, detector="abnormal_move/1", source="t", instrument=sym, metric="z_1h",
                      value=0.0, threshold=4, flagged=0, payload=p)
        why = {s: k1k2.hours(db, s)[o]["why"] for s, _, _ in rows}
        self.assertEqual(why, {"BTCUSDT": None, "SPYUSDT": "scan_before_close", "QQQUSDT": "late_scan",
                               "XAUUSDT": "missing_bars"})
        r = k1k2.readiness(db, o + 3 * H)
        w = r["weekends"][0]
        self.assertEqual(w["weekend"], "2026-10-31")
        self.assertEqual(w["markets"]["SPYUSDT"]["reasons"]["scan_before_close"], 1)
        self.assertEqual(w["markets"]["BTCUSDT"]["usable"], 1)
        self.assertEqual(w["markets"]["BTCUSDT"]["no_book"], 1)
        self.assertGreater(w["markets"]["BTCUSDT"]["reasons"]["no_scan"], 0)
        self.assertFalse(w["complete_k1"])
        self.assertNotIn("net", json.dumps(r))                                         # counts only

    def test_rescans_and_out_of_order_rows_use_the_earliest_scan(self):
        db = DB(":memory:")
        o = T("2026-10-31T10:00")
        for ts, mark in ((o + H + 900, 2.0), (o + H + 120, 1.0)):                     # later rescan stored first
            db.append("observations", ts=ts, detector="abnormal_move/1", source="t", instrument="SPYUSDT",
                      metric="z_1h", value=0.0, threshold=4, flagged=0,
                      payload={"open_s": o, "close_s": o + H, "ret_1h": 0.0, "price": mark, "mark": mark,
                               "index": mark, "quality": {"missing_bars": 0}})
        h = k1k2.hours(db, "SPYUSDT")[o]
        self.assertEqual((h["scan_ts"], h["mark"], h["usable"]), (o + H + 120, 1.0, True))


class Funding(unittest.TestCase):
    def test_forward_only_once_and_errors(self):
        db = DB(":memory:")
        start = fundsettle.START_MS
        rows = [{"fundingTime": start - 8 * H * 1000, "fundingRate": "0.9", "markPrice": "1"},
                {"fundingTime": start, "fundingRate": "0.0001", "markPrice": "100"},
                {"fundingTime": start + 8 * H * 1000, "fundingRate": "-0.0002", "markPrice": ""}]
        urls = []

        def get(u):
            urls.append(u)
            if "ETHUSDT" in u:
                raise OSError("down")
            return rows
        now = start // 1000 + 9 * H
        self.assertEqual(fundsettle.run(db, get, now), {"new": 2 * 11, "errors": 1})
        self.assertEqual(fundsettle.run(db, get, now), {"new": 0, "errors": 1})              # stored once
        self.assertTrue(all(f"startTime={start}" in u for u in urls))
        self.assertEqual(fundsettle.settled(db, "XAUUSDT", 0, 2 ** 40), [(start // 1000, 0.0001),
                                                                         (start // 1000 + 8 * H, -0.0002)])


class Screens(unittest.TestCase):
    def test_no_statistic_before_twelve_weekends(self):
        db = DB(":memory:")
        plant(db, weeks=3)
        now = START + 3 * 168 * H
        r = k1k2.k1(db, now)
        self.assertEqual(r["status"], "NO_DECISION")
        self.assertEqual(r["complete_weekends"], 3)
        self.assertNotIn("instruments", r)
        self.assertNotIn("net_mean", json.dumps(r))
        self.assertEqual(k1k2.k2(db, now)["status"], "NO_DECISION")
        self.assertEqual(k1k2.status(db, now)["K1"]["earliest_test"], "2027-01-18")

    def test_a_planted_weekend_lead_passes_and_noise_fails(self):
        db = DB(":memory:")
        plant(db, weeks=12)
        now = START + 12 * 168 * H
        r = k1k2.k1(db, now)
        self.assertEqual(r["complete_weekends"], 12)
        self.assertEqual(r["status"], "PASS", r)
        self.assertTrue(all(v["verdict"] == "PASS" for v in r["instruments"].values()))
        noise = DB(":memory:")
        plant(noise, weeks=12, lead=0.0, seed=2)
        r = k1k2.k1(noise, now)
        self.assertEqual(r["status"], "SCREEN_FAIL")
        self.assertFalse(r["instruments"]["SPYUSDT"]["checks"]["net_mean>0"])          # costs are paid

    def test_k2_mechanism_carry_and_placebo(self):
        db = DB(":memory:")
        plant(db, weeks=12)
        now = START + 12 * 168 * H
        for i in range(12 * 21):                                                       # 8-hourly settlements
            ft = START + i * 8 * H
            rate = 0.002 if sessions.closed("commodity", ft) else 0.0
            db.append("observations", ts=ft + 60, detector=fundsettle.DETECTOR, source="t", instrument="XAUUSDT",
                      metric="funding_settled", value=rate, threshold=None, flagged=0,
                      payload={"funding_time": ft, "rate": rate})
        r = k1k2.k2(db, now)
        x = r["instruments"]["XAUUSDT"]
        self.assertTrue(x["checks"]["holm_p<=0.005"], x)
        self.assertTrue(x["checks"]["placebo_p>0.05"], r["instruments"]["BTCUSDT"])
        self.assertGreater(x["carry_net_mean"], 0)
        self.assertEqual(x["verdict"], "PASS")
        self.assertNotIn("p", r["instruments"]["XAGUSDT"])                            # no data: not tested
        flat = DB(":memory:")
        plant(flat, weeks=12, xau_premium=False, seed=3)
        self.assertEqual(k1k2.k2(flat, now)["instruments"]["XAUUSDT"]["verdict"], "SCREEN_FAIL")

    def test_holm_and_wilcoxon(self):
        self.assertEqual(k1k2.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
        self.assertAlmostEqual(k1k2.wilcoxon_greater([1.0] * 12), 1 / 4096)            # exact (precision 2)
        self.assertLessEqual(k1k2.holm([1 / 4096] + [0.5] * 9)[0], 0.005)              # a PASS is reachable
        self.assertAlmostEqual(k1k2.wilcoxon_greater([1.0] * 11 + [-0.5]), 2 / 4096)   # the one miss is the smallest
        self.assertLessEqual(k1k2.holm([2 / 4096] + [0.5] * 9)[0], 0.005)
        self.assertGreater(k1k2.holm([k1k2.wilcoxon_greater([1.0] * 11 + [-2.0])] + [0.5] * 9)[0], 0.005)
        self.assertGreater(k1k2.wilcoxon_greater([1, -1] * 6), 0.5)                    # symmetric: no evidence
        self.assertLess(abs(k1k2.wilcoxon_greater(list(range(1, 31))) - 0.0), 1e-6)    # n > 25: normal approx


if __name__ == "__main__":
    unittest.main()
