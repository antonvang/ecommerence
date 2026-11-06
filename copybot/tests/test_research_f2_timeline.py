"""Director order 53 P0: synthetic regression tests for the PROPOSED F2 timeline conventions
(research/tools/f2_timeline.py). No market data, no kline cache, no network; all prices are synthetic."""
import ast
import json
import math
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
import f2_timeline as ft  # noqa: E402
import p2_power  # noqa: E402

DAY, HOUR = ft.DAY, ft.HOUR
T = ft.ts(2023, 2, 1)


def synth_closes(first_day, n_days, seed=53, start_price=100.0, conv="B23"):
    """Hourly synthetic closes covering every bar needed by days [first_day, first_day + n_days)."""
    rng = random.Random(seed)
    lo = ft.day_bars(first_day, conv)[0]
    hi = ft.day_bars(first_day + (n_days - 1) * DAY, conv)[-1]
    out, p, vol = {}, start_price, 0.01
    o = lo
    while o <= hi:
        vol = max(0.002, min(0.05, vol * math.exp(rng.gauss(0, 0.05))))
        p *= math.exp(rng.gauss(0, vol))
        out[o] = p
        o += HOUR
    return out


def synth_rv(first_day, n_days, seed=7):
    rng = random.Random(seed)
    rv, s = {}, 1e-3
    for k in range(n_days):
        s = max(1e-5, 0.0002 + 0.8 * s + rng.gauss(0, 2e-4))
        rv[first_day + k * DAY] = s
    return rv


class Guarded(dict):
    """An RV dict that raises if any day at/after the target is read."""
    def __init__(self, data, forbidden_from):
        super().__init__(data)
        self.forbidden_from = forbidden_from

    def __getitem__(self, k):
        if k >= self.forbidden_from:
            raise AssertionError("read target-or-later day %s" % ft.iso(k))
        return super().__getitem__(k)

    def __contains__(self, k):
        if k >= self.forbidden_from:
            raise AssertionError("probed target-or-later day %s" % ft.iso(k))
        return super().__contains__(k)

    def get(self, k, default=None):
        if k >= self.forbidden_from:
            raise AssertionError("read target-or-later day %s" % ft.iso(k))
        return super().get(k, default)


class KlineFacts(unittest.TestCase):
    def test_close_time_and_availability(self):
        o = ft.ts(2023, 1, 31, 23)
        self.assertEqual(ft.bar_close_time_ms(o), ft.ts(2023, 2, 1) * 1000 - 1)
        self.assertEqual(ft.bar_available(o), ft.ts(2023, 2, 1))

    def test_validate_bars_fail_closed(self):
        o = ft.ts(2023, 1, 1) * 1000
        good = [(o, 1.0, o + 3_599_999), (o + 3_600_000, 1.1, o + 7_199_999)]
        self.assertEqual(len(ft.validate_bars(good)), 2)
        bad = [
            [(o + 1, 1.0, o + 3_600_000)],                                   # misaligned
            [(o, 1.0, o + 3_600_000)],                                       # wrong close_time
            [good[0], good[0]],                                              # duplicate
            [good[1], good[0]],                                              # decreasing
            [(o, 0.0, o + 3_599_999)],                                       # zero close
            [(o, float("nan"), o + 3_599_999)],                              # nan close
        ]
        for rows in bad:
            with self.assertRaises(ft.TimelineError):
                ft.validate_bars(rows)


class DayDefinition(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(ft.returns_per_day("B23"), 23)
        self.assertEqual(ft.returns_per_day("A24"), 24)
        self.assertEqual(ft.returns_per_day("A23"), 23)
        self.assertEqual(len(ft.day_bars(T, "B23")), 24)

    def test_b23_movement_inside_utc_day(self):
        mv = ft.movement_bars(T, "B23")
        self.assertEqual(mv[0], T)
        self.assertEqual(mv[-1], T + 22 * HOUR)
        self.assertTrue(all(T <= o and o + HOUR <= T + 23 * HOUR for o in mv))

    def test_day_bounds(self):
        self.assertEqual(ft.day_bounds(T + 5), (T, T + DAY))
        with self.assertRaises(ft.TimelineError):
            ft.day_bars(T + 1)

    def test_missing_bar_no_fill(self):
        closes = synth_closes(T - 3 * DAY, 5)
        self.assertIsNotNone(ft.day_rv(closes, T, "B23"))
        c2 = dict(closes)
        del c2[T + 5 * HOUR]
        self.assertIsNone(ft.day_rv(c2, T, "B23"))
        # the embargo bar of day T-1 (opened T-1 23:00) is the base close of day T, not part of day T-1
        c3 = dict(closes)
        del c3[T - HOUR]
        self.assertIsNotNone(ft.day_rv(c3, T - DAY, "B23"))
        self.assertIsNone(ft.day_rv(c3, T, "B23"))

    def test_rv_value(self):
        closes = synth_closes(T - DAY, 3)
        bars = ft.day_bars(T, "B23")
        want = math.fsum(math.log(closes[bars[k]] / closes[bars[k - 1]]) ** 2 for k in range(1, 24))
        self.assertAlmostEqual(ft.day_rv(closes, T, "B23"), want, places=15)


class Timeline(unittest.TestCase):
    def all_targets(self):
        for w in ("explore0", "train3+validation3"):
            r = ft.window_targets(w, "B23")
            d = r["first_target"]
            while d <= r["last_target"]:
                yield d
                d += DAY

    def test_no_input_timestamp_at_or_after_target_start(self):
        n = 0
        for tgt in self.all_targets():
            tl = ft.forecast_timeline(tgt, "B23")
            for o in tl["input_bars"]:
                self.assertLess(ft.bar_available(o), tl["target_start"])
                self.assertLess(ft.bar_close_time_ms(o), tl["target_start"] * 1000)
            self.assertLess(tl["input_cutoff"], tl["target_start"])
            n += 1
        self.assertEqual(n, 275 + 334)

    def test_lock_before_target_start_with_margin(self):
        for tgt in self.all_targets():
            tl = ft.forecast_timeline(tgt, "B23")
            self.assertLessEqual(tl["input_cutoff"], tl["lock"])
            self.assertLessEqual(tl["lock"], tl["target_start"] - ft.MARGIN_S)
            self.assertLess(tl["lock"] * 1000, tl["target_first_close_time_ms"])
            self.assertTrue(ft.check_timeline(tl)["lock_ok"])

    def test_example_2023_02_01(self):
        tl = ft.forecast_timeline(T, "B23")
        self.assertEqual(tl["last_input_bar_open"], ft.ts(2023, 1, 31, 22))
        self.assertEqual(tl["input_cutoff"], ft.ts(2023, 1, 31, 23))
        self.assertEqual(tl["lock"], ft.ts(2023, 1, 31, 23, 30))
        self.assertEqual((tl["target_start"], tl["target_end"]), (T, T + DAY))
        self.assertEqual(tl["target_data_complete"], ft.ts(2023, 2, 1, 23))
        self.assertEqual(tl["earliest_reveal"], ft.ts(2023, 2, 2, 1))

    def test_b23_no_shared_mark(self):
        for tgt in self.all_targets():
            chk = ft.check_timeline(ft.forecast_timeline(tgt, "B23"))
            self.assertEqual(chk["shared_mark"], [])
            self.assertEqual(chk["verdict"], "OK")

    def test_a24_flagged_last_close_at_target_start(self):
        tl = ft.forecast_timeline(T, "A24")
        chk = ft.check_timeline(tl)
        self.assertEqual(tl["input_cutoff"], tl["target_start"])        # last close final exactly at target start
        self.assertFalse(chk["content_leak"])                            # price itself is from day t
        self.assertTrue(chk["availability_at_or_after_target"])
        self.assertEqual(chk["shared_mark"], [T - HOUR])                 # bar opened 23:00 is input AND target base
        self.assertFalse(chk["lock_ok"])
        self.assertEqual(chk["verdict"], "NO_MARGIN")

    def test_l24_off_by_one_is_content_leak(self):
        chk = ft.check_timeline(ft.forecast_timeline(T, "L24"))
        self.assertTrue(chk["content_leak"])
        self.assertEqual(chk["verdict"], "LEAK")

    def test_a23_no_margin(self):
        chk = ft.check_timeline(ft.forecast_timeline(T, "A23"))
        self.assertFalse(chk["content_leak"])
        self.assertEqual(chk["shared_mark"], [])
        self.assertEqual(chk["verdict"], "NO_MARGIN")


class HAR(unittest.TestCase):
    def test_365_rows_need_395_complete_days(self):
        L = ft.ts(2023, 1, 31)
        need = ft.har_required_days(L)
        self.assertEqual(len(need), 395)
        self.assertEqual(need[0], L - 394 * DAY)
        self.assertEqual(need[-1], L)
        self.assertEqual([b - a for a, b in zip(need, need[1:])], [DAY] * 394)
        rv = synth_rv(L - 394 * DAY, 395)
        v, info = ft.har_forecast(rv, L)
        self.assertIsNotNone(v)
        self.assertEqual(info["rows"], 365)
        short = {d: x for d, x in rv.items() if d != L - 394 * DAY}
        self.assertEqual(ft.har_forecast(short, L), (None, "incomplete_span"))
        self.assertEqual(ft.rows_for_data_days(365), 335)

    def test_lags_never_include_target_day(self):
        L = ft.ts(2023, 1, 31)
        for tau, origin in ft.har_rows(L):
            self.assertLessEqual(tau, L)
            for days in ft.har_feature_days(origin).values():
                self.assertTrue(all(d < tau for d in days))
        f = ft.har_feature_days(L)
        self.assertEqual(f["w7"], [L - k * DAY for k in range(7)])
        self.assertEqual(len(f["m30"]), 30)
        self.assertTrue(all(d <= L for days in f.values() for d in days))

    def test_poisoned_target_never_read(self):
        L = ft.ts(2023, 1, 31)
        rv = synth_rv(L - 500 * DAY, 501)
        clean_h = ft.har_forecast(dict(rv), L)[0]
        clean_e = ft.ewma_forecast(dict(rv), L)[0]
        rv[L + DAY] = float("nan")
        rv[L + 2 * DAY] = -1.0
        guarded = Guarded(rv, L + DAY)
        self.assertEqual(ft.har_forecast(guarded, L)[0], clean_h)
        self.assertEqual(ft.ewma_forecast(guarded, L)[0], clean_e)

    def test_floor(self):
        self.assertEqual(ft.har_floor(2e-4, [1e-4]), (2e-4, False))
        self.assertEqual(ft.har_floor(-1e-5, [3e-4, 1e-4, 2e-4]), (1e-4, True))
        self.assertEqual(ft.har_floor(float("nan"), [3e-4]), (3e-4, True))
        self.assertEqual(ft.har_floor(0.0, [0.0]), (None, True))


class EWMA(unittest.TestCase):
    def test_burn_in(self):
        self.assertEqual(ft.ewma_burn_in(), 50)
        self.assertLessEqual(0.94 ** 49, 0.05)
        self.assertGreater(0.94 ** 48, 0.05)

    def test_missing_day_restarts_run(self):
        L = ft.ts(2023, 1, 31)
        rv = synth_rv(L - 199 * DAY, 200)
        v, info = ft.ewma_forecast(rv, L)
        self.assertEqual(info["run_days"], 200)
        gap10 = {d: x for d, x in rv.items() if d != L - 10 * DAY}
        self.assertEqual(ft.ewma_run(gap10, L)[0], L - 9 * DAY)
        self.assertEqual(ft.ewma_forecast(gap10, L), (None, "burn_in"))
        gap60 = {d: x for d, x in rv.items() if d != L - 60 * DAY}
        v60, i60 = ft.ewma_forecast(gap60, L)
        self.assertEqual((i60["run_start"], i60["run_days"]), (L - 59 * DAY, 60))
        s = gap60[L - 59 * DAY]
        for k in range(58, -1, -1):
            s = 0.94 * s + 0.06 * gap60[L - k * DAY]
        self.assertAlmostEqual(v60, s, places=18)
        self.assertNotAlmostEqual(v60, v, places=12)
        self.assertEqual(ft.har_forecast(gap60, L), (None, "incomplete_span"))

    def test_run_truncated_to_har_span(self):
        L = ft.ts(2023, 1, 31)
        rv = synth_rv(L - 999 * DAY, 1000)
        self.assertEqual(ft.ewma_forecast(rv, L)[1]["run_days"], 395)


class Windows(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(ft.window_targets("explore0")["targets"], 275)
        self.assertEqual(ft.window_targets("train3+validation3")["targets"], 334)
        self.assertEqual(ft.window_targets("train3")["targets"], 150)
        self.assertEqual(ft.window_targets("validation3")["targets"], 0)
        self.assertEqual(ft.window_targets("train3+validation3", carry_over=True)["targets"], 730)
        # C1 / NOV14 numbers (first RV day = window start) are reproduced by A23
        self.assertEqual(ft.window_targets("explore0", "A23")["targets"], 276)
        self.assertEqual(ft.window_targets("train3+validation3", "A23")["targets"], 335)
        self.assertEqual(ft.window_targets("train3+validation3")["first_target"], ft.ts(2023, 2, 1))
        self.assertEqual(ft.window_targets("explore0")["first_target"], ft.ts(2021, 4, 1))

    def test_window_edge_never_reaches_2024(self):
        for w in ft.WINDOWS:
            r = ft.window_targets(w, "B23")
            if r["targets"]:
                self.assertLess(r["max_bar_open_needed"], ft.HOLDOUT_START)
                self.assertLess(r["max_availability_needed"], ft.HOLDOUT_START)
        r = ft.window_targets("train3+validation3", "B23")
        self.assertEqual(r["last_target"], ft.ts(2023, 12, 31))
        d = r["first_target"]
        while d <= r["last_target"]:
            tl = ft.forecast_timeline(d)
            for o in tl["input_bars"] + tl["target_bars"]:
                self.assertGreaterEqual(o, ft.ts(2022, 1, 1))
                self.assertLess(ft.bar_available(o), ft.HOLDOUT_START)
            d += DAY
        # a forecast made on the last window day would target 2024-01-01: never inside the window's targets
        self.assertLess(r["last_target"], ft.HOLDOUT_START)

    def test_explore0_isolated(self):
        r = ft.window_targets("explore0", "B23")
        self.assertLess(r["max_availability_needed"], ft.WINDOWS["train3"][0])
        self.assertEqual(ft.first_rv_day(ft.WINDOWS["explore0"][0]), ft.ts(2020, 3, 2))

    def test_a_conventions_touch_the_boundary(self):
        r = ft.window_targets("train3+validation3", "A23")
        self.assertLess(r["max_bar_open_needed"], ft.HOLDOUT_START)
        self.assertEqual(r["max_availability_needed"], ft.HOLDOUT_START)

    def test_rv_series_isolation(self):
        start = ft.WINDOWS["train3"][0]
        closes = synth_closes(start - DAY, 4)
        rv = ft.rv_series(closes, start, start + 2 * DAY, "B23", lo_bound=start)
        self.assertNotIn(start, rv)                                     # needs the 2021-12-31 23:00 bar
        self.assertIn(start + DAY, rv)

    def test_flat_day_is_not_an_rv_day(self):
        closes = synth_closes(T - 2 * DAY, 4)
        for o in ft.day_bars(T, "B23"):
            closes[o] = 50.0
        rv = ft.rv_series(closes, T - DAY, T + DAY, "B23")
        self.assertEqual(ft.day_rv(closes, T, "B23"), 0.0)
        self.assertNotIn(T, rv)
        self.assertIn(T - DAY, rv)

    def test_coin_eligible_full_coverage(self):
        s, e = ft.WINDOWS["validation3"]
        closes = {o: 1.0 for o in range(s, e, HOUR)}
        self.assertEqual(ft.coin_eligible(closes, "validation3"), (True, 1.0))
        del closes[s + 100 * HOUR]
        ok, cov = ft.coin_eligible(closes, "validation3")
        self.assertFalse(ok)
        self.assertGreater(cov, 0.99)


class LossAndCrossSection(unittest.TestCase):
    def test_qlike(self):
        self.assertEqual(ft.qlike(1.0, 1.0), 0.0)
        self.assertAlmostEqual(ft.qlike(2.0, 1.0), 1 - math.log(2), places=15)
        for rv, f in ((0.0, 1.0), (1.0, 0.0), (1.0, -1.0)):
            with self.assertRaises(ft.TimelineError):
                ft.qlike(rv, f)

    def test_equal_weight(self):
        self.assertEqual(ft.daily_mean_d({"A": 1.0, "B": 3.0, "C": None}), 2.0)
        self.assertIsNone(ft.daily_mean_d({"A": None}))


class Power(unittest.TestCase):
    def test_locked_table_reproduced(self):
        for days, rho, e, want in ((730, 0.5, 0.02, 0.15), (730, 0.5, 0.05, 0.45), (730, 0.5, 0.10, 0.92),
                                   (730, 0.8, 0.05, 0.34), (730, 0.8, 0.10, 0.79), (546, 0.5, 0.10, 0.84)):
            self.assertEqual(round(p2_power.dm_power(e, 20, days, rho, 0.05)[0], 2), want)

    def test_shorter_windows(self):
        rows = {(r["days"], r["coins"], r["rho_c"]): r for r in ft.power_table()}
        self.assertEqual(rows[(334, 20, 0.5)]["e0.05"], 0.269)
        self.assertEqual(rows[(334, 20, 0.5)]["e0.10"], 0.661)
        self.assertEqual(rows[(334, 20, 0.8)]["e0.10"], 0.505)
        self.assertEqual(rows[(275, 20, 0.5)]["e0.10"], 0.589)
        self.assertEqual(rows[(276, 20, 0.5)]["e0.05"], 0.239)
        self.assertEqual(rows[(275, 15, 0.5)]["e0.05"], 0.236)
        self.assertEqual(rows[(335, 20, 0.5)]["e0.10"], 0.662)
        self.assertLess(rows[(730, 20, 0.5)]["e0.08"], 0.8)             # locked GO bar is not met even at 730 d
        self.assertAlmostEqual(ft.rho_max_for_power(0.08, 334), 0.19, places=2)

    def test_a8_translation(self):
        a8 = p2_power.a8_check()
        t = ft.a8_translation()
        self.assertEqual((t["6m"], t["12m"]), (a8["6m"], a8["12m"]))


class Hygiene(unittest.TestCase):
    def test_no_network_or_data_access(self):
        path = os.path.join(HERE, "research", "tools", "f2_timeline.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        mods = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.add((node.module or "").split(".")[0])
        self.assertEqual(mods - {"__future__", "calendar", "json", "math", "os", "sys", "time", "p2_power"}, set())
        for s in ("data/lab", "market/klines", "binance.vision", "fapi", "open(", "sqlite"):
            self.assertNotIn(s, src)

    def test_examples_deterministic_and_selftest(self):
        a = json.dumps(ft.examples(), sort_keys=True)
        b = json.dumps(ft.examples(), sort_keys=True)
        self.assertEqual(a, b)
        self.assertEqual(ft.selftest(), 0)


if __name__ == "__main__":
    unittest.main()
