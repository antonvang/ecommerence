"""Director decision 101: the three event farm context filters on synthetic bars only (no market data, no network)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_filters as ff  # noqa: E402
from research.tools import validation_engine as ve  # noqa: E402

T0 = ef.START                     # 2026-01-05 00:00 UTC
BS = 300
FLAT = (100.0, 100.5, 99.5, 100.0)


def mk(rows, t0=T0, v=1.0):
    return [(t0 + BS * k, o, h, l, c, v) for k, (o, h, l, c) in enumerate(rows)]


def expand(hours, t0=T0):
    """Each 1h (h, l) becomes 12 5m bars: the 3rd touches h, the 7th touches l, all inside [l, h]."""
    out = []
    for n, (h, l) in enumerate(hours):
        mid = (h + l) / 2
        for k in range(12):
            hi, lo = (h if k == 2 else mid + 0.1), (l if k == 6 else mid - 0.1)
            out.append((t0 + 3600 * n + BS * k, mid, hi, lo, mid, 1.0))
    return out


HIGHS = [10, 11, 13, 11, 10, 12, 14, 16, 14, 13, 15, 16]
UP = [(h, h - 2) for h in HIGHS]                      # swing highs 13, 16 and swing lows 8, 11 (k1 = 2)
DOWN = [(30 - l, 30 - h) for h, l in UP]              # the mirror image


class TrendFilter(unittest.TestCase):
    def test_up_trend_known_only_when_the_confirming_hour_has_closed(self):
        bars = expand(UP)
        tr = ff.trend_1h(bars)
        self.assertEqual(tr[-1], 1)                    # hour 11 closed: second swing low confirmed
        self.assertEqual(tr[-2], 0)                    # one 5m bar earlier: hour 11 not yet complete
        self.assertEqual(set(tr[:-1]), {0})
        self.assertTrue(ff.f1({"dir": 1, "known_i": len(bars) - 1}, ff.context(bars)))
        self.assertFalse(ff.f1({"dir": -1, "known_i": len(bars) - 1}, ff.context(bars)))
        self.assertFalse(ff.f1({"dir": 1, "known_i": len(bars) - 2}, ff.context(bars)))

    def test_down_trend_mirrors(self):
        bars = expand(DOWN)
        self.assertEqual(ff.trend_1h(bars)[-1], -1)
        self.assertTrue(ff.f1({"dir": -1, "known_i": len(bars) - 1}, ff.context(bars)))

    def test_an_hour_with_a_missing_5m_bar_is_never_used(self):
        bars = expand(UP)
        self.assertEqual(set(ff.trend_1h(bars[:-1])), {0})                      # last 5m bar of hour 11 missing
        holed = bars[:5] + bars[6:]                                             # one 5m bar of hour 0 missing
        self.assertEqual(ff.trend_1h(holed)[-1], 0)     # hour 0 dropped: swing high 13 has one left bar only


def prior_day(extra_high=101.0, n=288):
    rows = [FLAT] * n
    rows[100] = (100.0, extra_high, 99.5, 100.0)
    return mk(rows, T0)


def today(rows):
    return mk(rows, T0 + 86400)


BREAK = (100.0, 101.3, 100.9, 101.2)          # close > PDH 101
ABOVE = (101.2, 101.4, 101.1, 101.3)          # no touch
TOUCH = (101.3, 101.4, 100.95, 101.2)         # low <= 101, close above
BACK = (101.2, 101.3, 100.7, 100.9)           # close back below


class RetestFilter(unittest.TestCase):
    def ok_at_end(self, rows, prev=None):
        bars = (prev or prior_day()) + today(rows)
        return ff.prior_day_retest(bars)[-1], bars

    def test_breakout_then_retest_passes_with_entry_above(self):
        (pdh, pdl, lok, sok), bars = self.ok_at_end([FLAT] * 10 + [BREAK, ABOVE, TOUCH, ABOVE])
        self.assertEqual((pdh, pdl, lok, sok), (101.0, 99.5, True, False))
        ctx = ff.context(bars)
        k = len(bars) - 1
        self.assertTrue(ff.f2({"dir": 1, "known_i": k, "entry": 101.1}, ctx))
        self.assertFalse(ff.f2({"dir": 1, "known_i": k, "entry": 100.8}, ctx))
        self.assertFalse(ff.f2({"dir": -1, "known_i": k, "entry": 99.0}, ctx))

    def test_breakout_bar_itself_is_no_retest(self):
        self.assertFalse(self.ok_at_end([FLAT] * 10 + [(100.0, 101.3, 100.5, 101.2)])[0][2])

    def test_close_back_cancels(self):
        self.assertFalse(self.ok_at_end([FLAT] * 10 + [BREAK, TOUCH, BACK])[0][2])
        self.assertFalse(self.ok_at_end([FLAT] * 10 + [BREAK, BACK, TOUCH])[0][2])

    def test_no_touch_within_twelve_bars_spends_the_breakout(self):
        self.assertTrue(self.ok_at_end([FLAT] * 10 + [BREAK] + [ABOVE] * 11 + [TOUCH])[0][2])    # touch at b + 12
        self.assertFalse(self.ok_at_end([FLAT] * 10 + [BREAK] + [ABOVE] * 12 + [TOUCH])[0][2])   # b + 13: spent
        # a close back resets a spent breakout, and a new breakout with retest passes again
        self.assertTrue(self.ok_at_end([FLAT] * 10 + [BREAK] + [ABOVE] * 12 + [BACK, BREAK, TOUCH])[0][2])

    def test_incomplete_previous_day_gives_no_level(self):
        prev = [b for k, b in enumerate(prior_day()) if k % 15]                 # about 93 % of the day
        (pdh, pdl, lok, sok), _ = self.ok_at_end([FLAT] * 10 + [BREAK, TOUCH], prev)
        self.assertEqual((pdh, pdl, lok, sok), (None, None, False, False))

    def test_short_side_mirrors(self):
        rows = [FLAT] * 5 + [(99.6, 99.6, 99.2, 99.3), (99.3, 99.6, 99.25, 99.4)]
        (pdh, pdl, lok, sok), _ = self.ok_at_end(rows)
        self.assertEqual((pdl, sok, lok), (99.5, True, False))


class VwapFilter(unittest.TestCase):
    def test_vwap_and_stretch(self):
        rows = [FLAT] * 10 + [(98.0, 98.2, 97.8, 98.0)]
        bars = mk(rows)
        vw, status = ff.vwap_series(bars)[-1]
        want = (10 * (100.5 + 99.5 + 100) / 3 + (98.2 + 97.8 + 98) / 3) / 11
        self.assertEqual(status, "OK")
        self.assertAlmostEqual(vw, want)
        ctx = ff.context(bars)
        long_ = {"dir": 1, "known_i": 10, "atr": 1.0}
        self.assertAlmostEqual(ff.stretch(long_, ctx), want - 98.0)
        self.assertTrue(ff.f3(long_, ctx))                                      # about 1.8 ATR below
        self.assertFalse(ff.f3(dict(long_, dir=-1), ctx))
        self.assertFalse(ff.f3(dict(long_, atr=2.0), ctx))                     # 0.9 ATR: below the threshold

    def test_zero_or_missing_volume_blocks_the_rest_of_the_session(self):
        bars = mk([FLAT] * 10 + [(98.0, 98.2, 97.8, 98.0)])
        bars[4] = bars[4][:5] + (0.0,)
        series = ff.vwap_series(bars)
        self.assertEqual([s for _, s in series[:4]], ["OK"] * 4)
        self.assertEqual({s for _, s in series[4:]}, {"INCOMPLETE"})
        self.assertIsNone(series[-1][0])
        ctx = ff.context(bars)
        s = {"dir": 1, "known_i": 10, "atr": 1.0}
        self.assertEqual(ff.vwap_status(s, ctx), "INCOMPLETE")
        self.assertFalse(ff.f3(s, ctx))
        nan = mk([FLAT] * 3)
        nan[1] = nan[1][:5] + (float("nan"),)
        self.assertEqual(ff.vwap_series(nan)[2][1], "INCOMPLETE")

    def test_missing_bar_or_late_session_start_blocks_and_next_session_recovers(self):
        bars = mk([FLAT] * 10)
        self.assertEqual(ff.vwap_series(bars[:3] + bars[4:])[-1][1], "INCOMPLETE")
        self.assertEqual(ff.vwap_series(bars[1:])[0][1], "INCOMPLETE")         # session starts at 00:05
        two = mk([FLAT] * 300)
        two[5] = two[5][:5] + (0.0,)
        s = ff.vwap_series(two)
        self.assertEqual((s[287][1], s[288][1]), ("INCOMPLETE", "OK"))


class Lookahead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = ef.random_walk_bars(7, 4)
        cls.full = ff.context(cls.bars)

    def test_truncation_and_rewritten_future_change_nothing_known(self):
        for n, t in enumerate((50, 287, 288, 700, 1000)):
            cut = ff.context(self.bars[:t + 1])
            for key in ("trend", "pd", "vwap"):
                self.assertEqual(cut[key], self.full[key][:t + 1], (key, t))
            rw = ef.random_walk_bars(500 + n, 2)
            f = self.bars[t][4] / rw[0][1]
            other = self.bars[:t + 1] + [(self.bars[t][0] + BS * (k + 1), o * f, h * f, lo * f, c * f, v)
                                         for k, (_, o, h, lo, c, v) in enumerate(rw)]
            alt = ff.context(other)
            for key in ("trend", "pd", "vwap"):
                self.assertEqual(alt[key][:t + 1], self.full[key][:t + 1], (key, t))

    def test_validation_engine_truncation_check(self):
        r = ve.check_lookahead(signal_fn=ff.lookahead_signal(), data=self.bars, n_checks=12)
        self.assertEqual(r["status"], ve.PASS, r)

    def test_filters_read_only_the_known_bar(self):
        p = ef.params()
        setups, _ = ef.build_setups(ef.detect(self.bars, p), self.bars, p)
        self.assertTrue(setups)
        for s in setups:
            k = s["known_i"]
            small = ff.context(self.bars[:k + 1])
            for combo in ff.COMBOS:
                self.assertEqual(ff.passes(s, small, combo), ff.passes(s, self.full, combo), (combo, k))

    def test_determinism_and_baseline_unchanged(self):
        self.assertEqual(ff.context(list(self.bars)), self.full)
        p = ef.params()
        setups, _ = ef.build_setups(ef.detect(self.bars, p), self.bars, p)
        kept = ff.apply(setups, self.bars, "F1", self.full)
        self.assertTrue(all(any(s is x for x in setups) for s in kept))
        self.assertLessEqual(len(kept), len(setups))


class NullAndRegister(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = ff.null_with_filters(seed=83, instruments=1, days=20)

    def test_baseline_null_is_preserved(self):
        ref = ef.null_run(seed=83, instruments=1, days=20)
        base = ff.pooled(self.s, "base")
        self.assertEqual(base["trades"], ref["pooled_trades"])
        self.assertAlmostEqual(base["mean_gross_r"], ref["pooled_mean_gross_r"])

    def test_filters_only_remove_and_lose_after_costs(self):
        for combo in ff.COMBOS:
            for vid in [ef._variant_id(v) for v in ef.VARIANTS]:
                self.assertLessEqual(self.s["tests"][f"{combo}/{vid}"]["setups"], self.s["tests"][f"base/{vid}"]["setups"])
            p = ff.pooled(self.s, combo)
            if p["trades"] >= 30:
                self.assertLess(p["mean_net_r"]["8"], 0.0, combo)
        self.assertGreater(ff.pooled(self.s, "F1")["trades"], 30)

    def test_96_tests_and_n(self):
        self.assertEqual(len(self.s["tests"]), 96)
        self.assertEqual(len(ff.all_forward_tests()), 96)
        self.assertEqual(ff.reference_n(), 19753 + 96)

    def test_v2_records(self):
        from research.tools import register_v2 as v2
        recs = ff.v2_filter_records("2026-12-01", "2027-02-28")
        self.assertEqual(len(recs), 7)
        for r in recs:
            self.assertEqual(v2.validate(r), [])
            self.assertEqual(r["trial_universe"]["size"], 96)
            self.assertEqual(r["parameters"]["values"]["reference_n"], 19849)
            self.assertFalse(r["parameters"]["values"]["activated"])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
