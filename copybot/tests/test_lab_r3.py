"""Amendment 24: R3 - no request before 2026-11-14, only the 44 allowed files, a 404 recorded and never replaced, the
reaction rule (s from bar 0, entry bar 1, exit bar 61, nothing before T used), a planted reaction passes, noise fails,
too few clusters are UNTESTABLE, and the placebo moves 14 days when 7 days earlier was a calendar day."""
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import r3  # noqa: E402
from lab.engine import data  # noqa: E402

T = lambda s: int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
A, B = T("2020-03-01T00:00"), T("2022-01-01T00:00")


def zipped(rows, header=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        text = ("open_time,open,high,low,close,volume\n" if header else "") + \
               "".join(f"{t * 1000},{o},{o},{o},{c},1\n" for t, o, c in rows)
        z.writestr("x.csv", text)
    return buf.getvalue()


def bars_for(t, s, drift, rng, noise=0.0005):
    """Minute bars 0..61 around a release at t: bar 0 moves in direction s, then a drift from bar 1 to bar 61."""
    out, px = {}, 100.0
    for k in range(-5, 0):
        out[t + k * 60] = (px, px)
    c0 = px * math.exp(s * 0.001)
    out[t] = (px, c0)
    c1 = c0 * math.exp(rng.gauss(0, noise))
    out[t + 60] = (c0, c1)
    c61 = c1 * math.exp(s * drift + rng.gauss(0, noise))
    out[t + 61 * 60] = (c1, c61)
    return out


class Fetch(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = data.CACHE, tempfile.mkdtemp(prefix="r3")
        data.CACHE = self.tmp

    def tearDown(self):
        data.CACHE = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_refused_before_the_14th_and_only_allowed_files_after(self):
        calls = []
        with self.assertRaises(r3.Refused):
            r3.fetch(now=r3.FETCH_FROM - 1, get=lambda u: calls.append(u))
        self.assertEqual(calls, [])                                                # no request at all

        def get(u):
            calls.append(u)
            if u.endswith("ETHUSDT-1m-2020-03.zip"):
                raise urllib.error.HTTPError(u, 404, "nf", None, None)
            return zipped([(A, 1.0, 1.0)])
        out = r3.fetch(now=r3.FETCH_FROM, get=get)
        self.assertEqual(len(calls), 44)
        self.assertTrue(all(c.startswith("https://data.binance.vision/data/futures/um/monthly/klines/") for c in calls))
        self.assertTrue(all(("-2020-" in c or "-2021-" in c) and "-2020-01" not in c and "-2020-02" not in c
                            for c in calls))
        self.assertEqual(out["absent"], ["ETHUSDT-1m-2020-03.zip"])               # recorded, never replaced
        with open(r3.log_path()) as f:
            log = [json.loads(line) for line in f]
        self.assertEqual(log[0]["status"], "refused")                             # the early run left a record
        self.assertEqual(log[1]["counts"], {"fetched": 43, "present": 0, "absent": 1, "failed": 0})
        self.assertEqual(len(log[1]["files"]["BTCUSDT-1m-2020-03.zip"]["sha256"]), 64)
        self.assertEqual(len(out["fetched"]), 43)
        calls.clear()
        again = r3.fetch(now=r3.FETCH_FROM + 1, get=get)
        self.assertEqual((len(again["present"]), calls), (43, ["https://data.binance.vision/data/futures/um/monthly/"
                                                               "klines/ETHUSDT/1m/ETHUSDT-1m-2020-03.zip"]))

    def test_other_errors_are_recorded_as_failed_and_do_not_stop_the_run(self):
        def get(u):
            if "BTCUSDT-1m-2021-07" in u:
                raise TimeoutError("read timed out")
            if "ETHUSDT-1m-2020-05" in u:
                raise urllib.error.HTTPError(u, 503, "busy", None, None)
            return zipped([(A, 1.0, 1.0)])
        out = r3.fetch(now=r3.FETCH_FROM, get=get)
        self.assertEqual(sorted(out["failed"]), ["BTCUSDT-1m-2021-07.zip", "ETHUSDT-1m-2020-05.zip"])
        self.assertEqual(len(out["fetched"]), 42)
        self.assertFalse(os.path.exists(r3.path("BTCUSDT", 2021, 7)))                 # nothing put in its place
        with open(r3.log_path()) as f:
            last = json.loads(f.readlines()[-1])
        self.assertEqual(last["files"]["ETHUSDT-1m-2020-05.zip"], {"status": "failed", "error": "HTTP 503"})

    def test_24a_early_window_only_in_k3_free_slots_and_never_in_pm_lp_d1(self):
        U = lambda x: T(x)                                                         # UTC
        allowed = {"2026-10-27T14:35": True, "2026-10-27T14:34": False,           # S7 test and K3 14:00 +- 35
                   "2026-10-27T15:24": True, "2026-10-27T15:25": False,           # K3 16:00 opens at 15:25
                   "2026-10-27T16:34": False, "2026-10-27T16:35": True,
                   "2026-10-30T23:24": True, "2026-10-30T23:25": False,           # last slot before 10-31
                   "2026-10-31T00:35": False, "2026-11-05T14:40": False,          # pm_lp's D1: never
                   "2026-11-13T23:59": False, "2026-11-14T00:00": True,           # amendment 24 unchanged
                   "2026-11-14T00:10": True, "2026-10-26T20:40": False}
        for when, want in allowed.items():
            self.assertEqual(r3.allowed(U(when)), want, when)
        calls = []
        with self.assertRaises(r3.Refused):
            r3.fetch(now=U("2026-10-27T13:00"), get=lambda u: calls.append(u))
        self.assertEqual(calls, [])

    def test_24a_a_run_that_leaves_the_slot_stops_and_records_the_rest(self):
        clock = iter([T("2026-10-27T14:35")] + [T("2026-10-27T15:00")] * 10 + [T("2026-10-27T15:25")] * 100)
        calls = []
        out = r3.fetch(get=lambda u: calls.append(u) or zipped([(A, 1.0, 1.0)]), clock=lambda: next(clock))
        self.assertEqual(len(calls), 10)                                           # no request after the slot ended
        self.assertEqual(len(out["stopped"]), 34)
        with open(r3.log_path()) as f:
            last = json.loads(f.readlines()[-1])
        self.assertEqual(last["counts"]["stopped"], 34)
        self.assertEqual(last["files"]["ETHUSDT-1m-2021-12.zip"], {"status": "stopped"})
        again = r3.fetch(get=lambda u: calls.append(u) or zipped([(A, 1.0, 1.0)]),
                         clock=lambda: T("2026-10-27T16:40"))                      # the next slot fetches the rest
        self.assertEqual((len(again["present"]), len(again["fetched"])), (10, 34))

    def test_bars_read_files_with_and_without_header(self):
        os.makedirs(os.path.join(self.tmp, "klines_1m"))
        with open(r3.path("BTCUSDT", 2020, 3), "wb") as f:
            f.write(zipped([(A, 1.0, 2.0)], header=True))
        with open(r3.path("BTCUSDT", 2020, 4), "wb") as f:
            f.write(zipped([(A + 60, 2.0, 3.0)]))
        b, files = r3.bars("BTCUSDT")
        self.assertEqual(b, {A: (1.0, 2.0), A + 60: (2.0, 3.0)})
        self.assertEqual(len(files), 2)


class Rule(unittest.TestCase):
    def test_reaction_uses_bar0_sign_bar1_entry_bar61_exit_and_nothing_before_t(self):
        t, rng = T("2020-06-10T12:30"), random.Random(1)
        b = bars_for(t, -1, 0.004, rng, noise=0.0)
        y, why = r3.reaction(b, t)
        self.assertIsNone(why)
        self.assertAlmostEqual(y, 0.004, places=12)                               # s = -1, price fell 0.4 % more
        b2 = dict(b)
        b2[t - 60] = (1.0, 999.0)                                                  # a bar before T changes nothing
        self.assertEqual(r3.reaction(b2, t)[0], y)
        del b2[t + 61 * 60]
        self.assertEqual(r3.reaction(b2, t), (None, "missing minute bar"))
        flat = dict(b)
        flat[t] = (100.0, 100.0)
        self.assertEqual(r3.reaction(flat, t)[1], "flat first bar (s = 0)")


def calendar(n, start="2020-03-04T13:30"):
    """n releases on separate days spread over 2020-03..2021-12, 9 days apart."""
    t0 = T(start)
    return [(t0 + i * 9 * 86400, "CPI") for i in range(n)]


class Screen(unittest.TestCase):
    def build(self, events, drift, seed=1):
        rng = random.Random(seed)
        px = {s: {} for s in r3.SYMS}
        for t, _ in events:
            for s in r3.SYMS:
                d = rng.choice((-1, 1))
                px[s].update(bars_for(t, d, drift, rng))
                px[s].update(bars_for(t - r3.WEEK, rng.choice((-1, 1)), 0.0, rng))      # placebo: no reaction
                px[s].update(bars_for(t - 2 * r3.WEEK, rng.choice((-1, 1)), 0.0, rng))
        return px

    def test_planted_reaction_passes_noise_fails_and_few_events_are_untestable(self):
        ev = calendar(70)
        r = r3.screen(self.build(ev, 0.008), {}, ev, set(), A, B)
        self.assertEqual(r["verdict"], "SCREEN_PASS", r.get("reason"))
        self.assertEqual(r["key"], "macro_release|minute_drift_60m|m24")
        r = r3.screen(self.build(ev, 0.003), {}, ev, set(), A, B)                  # real but below the 0.46 % floor
        self.assertEqual(r["verdict"], "SCREEN_FAIL")
        self.assertIn("|mean|", r["reason"])
        r = r3.screen(self.build(ev, 0.0, seed=3), {}, ev, set(), A, B)
        self.assertEqual(r["verdict"], "SCREEN_FAIL")
        few = calendar(10)
        self.assertEqual(r3.screen(self.build(few, 0.008), {}, few, set(), A, B)["verdict"], "UNTESTABLE")

    def test_placebo_moves_14_days_on_a_calendar_day_and_missing_bars_are_counted(self):
        ev = calendar(20)
        px = self.build(ev, 0.008)
        busy = {(t - r3.WEEK) // r3.DAY for t, _ in ev[:5]}
        for s in r3.SYMS:
            for t, _ in ev[5:7]:
                px[s].pop(t + 61 * 60)
        r = r3.screen(px, {}, ev, busy, A, B)
        self.assertEqual(r["excluded_coin_events"], {"missing minute bar": 4})
        self.assertEqual(r["n_events"], 18)
        self.assertEqual(r["placebo"]["n_events"], 18)              # -14 d puts events 0 and 1 before explore0
        self.assertEqual(r3.screen(px, {}, ev, set(), A, B)["placebo"]["n_events"], 19)   # -7 d: only event 0


if __name__ == "__main__":
    unittest.main()
