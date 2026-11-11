"""Event farm (research/tools/event_farm.py): hand-built synthetic bars per detector (positive and negative cases),
lookahead by truncation and by rewriting the future, determinism, chain rules, outcome rules and the null test on a
synthetic random walk. No file, market data or network is used."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402
from research.tools import validation_engine as ve  # noqa: E402

T0 = ef.START
BS = 300
FLAT = (100.0, 100.5, 99.5, 100.0)


def mk(rows, t0=T0):
    return [(t0 + BS * i, o, h, l, c, 1.0) for i, (o, h, l, c) in enumerate(rows)]


def of(events, kind):
    return [e for e in events if e["kind"] == kind]


def P(**kw):
    base = {"atr_n": 5, "swing_k": 2, "sessions": (), "fvg_min_atr": 0.0}
    base.update(kw)
    return base


class Swings(unittest.TestCase):
    def test_pivot_is_known_only_k_bars_later(self):
        bars = mk([FLAT] * 5 + [(100, 102, 99.5, 100)] + [FLAT] * 2)
        sh = of(ef.detect(bars, P()), "swing_high")
        self.assertEqual(len(sh), 1)
        self.assertEqual((sh[0]["i"], sh[0]["known_i"], sh[0]["level"]), (5, 7, 102))
        self.assertEqual(sh[0]["ts"], T0 + 5 * BS)
        self.assertEqual(sh[0]["known_ts"], T0 + 7 * BS + BS)
        self.assertEqual(of(ef.detect(bars[:7], P()), "swing_high"), [])

    def test_equal_highs_give_one_pivot_and_a_higher_right_bar_none(self):
        eq = mk([FLAT] * 5 + [(100, 102, 99.5, 100)] * 2 + [FLAT] * 3)
        self.assertEqual([e["i"] for e in of(ef.detect(eq, P()), "swing_high")], [5])
        hi = mk([FLAT] * 5 + [(100, 102, 99.5, 100), FLAT, (100, 103, 99.5, 100)])
        self.assertEqual(of(ef.detect(hi, P()), "swing_high"), [])


class Pools(unittest.TestCase):
    def rows(self, second):
        return mk([FLAT] * 5 + [(100, 102, 99.5, 100)] + [FLAT] * 4 + [(100, second, 99.5, 100)] + [FLAT] * 2)

    def test_two_swings_within_tolerance_form_a_pool(self):
        pools = of(ef.detect(self.rows(101.95), P(pool_tol_atr=0.1)), "liquidity_pool_high")
        self.assertEqual(len(pools), 1)
        self.assertEqual((pools[0]["level"], pools[0]["members_i"], pools[0]["known_i"]), (102, [5, 10], 12))

    def test_swings_outside_tolerance_do_not(self):
        self.assertEqual(of(ef.detect(self.rows(101.7), P(pool_tol_atr=0.1)), "liquidity_pool_high"), [])


class Sweeps(unittest.TestCase):
    BASE = [FLAT] * 5 + [(100, 102, 99.5, 100)] + [FLAT] * 2          # swing high 102 known at bar 7

    def test_wick_through_and_close_back_is_a_sweep(self):
        ev = of(ef.detect(mk(self.BASE + [(100, 102.5, 99.8, 101.0)]), P()), "sweep_high")
        self.assertEqual(len(ev), 1)
        e = ev[0]
        self.assertEqual((e["level"], e["extreme"], e["known_i"], e["pierce_i"], e["dir"]), (102, 102.5, 8, 8, -1))

    def test_close_beyond_is_no_sweep(self):
        self.assertEqual(of(ef.detect(mk(self.BASE + [(100, 102.5, 99.8, 102.2)]), P()), "sweep_high"), [])

    def test_reclaim_window(self):
        rows = self.BASE + [(100, 102.5, 99.8, 102.2), (102.2, 102.4, 100.9, 101.0)]
        self.assertEqual(of(ef.detect(mk(rows), P(sweep_reclaim_bars=1)), "sweep_high"), [])
        ev = of(ef.detect(mk(rows), P(sweep_reclaim_bars=2)), "sweep_high")
        self.assertEqual([(e["pierce_i"], e["known_i"], e["extreme"], e["ts"]) for e in ev], [(8, 9, 102.5, T0 + 8 * BS)])

    def test_sweep_low_mirrors(self):
        rows = [FLAT] * 5 + [(100, 100.5, 98, 100)] + [FLAT] * 2 + [(100, 100.2, 97.5, 99.0)]
        ev = of(ef.detect(mk(rows), P()), "sweep_low")
        self.assertEqual([(e["level"], e["extreme"], e["dir"]) for e in ev], [(98, 97.5, 1)])


STRUCT = [(100, 100.5, 99.5, 100), (100, 101, 99.8, 100.5), (100.5, 100.8, 99.0, 99.2), (99.2, 99.5, 98.0, 98.3),
          (98.3, 99.0, 98.2, 98.8), (98.8, 99.0, 97.5, 97.6), (97.6, 97.8, 97.0, 97.2), (97.2, 98.0, 97.1, 97.9),
          (97.9, 98.4, 97.6, 97.7), (97.7, 97.9, 97.3, 97.4), (97.4, 98.8, 97.3, 98.7)]


class Structure(unittest.TestCase):
    def test_bos_then_mss(self):
        ev = ef.detect(mk(STRUCT), P(swing_k=1, atr_n=50))
        self.assertEqual([(e["kind"], e["known_i"], e["level"]) for e in ev if e["kind"].startswith(("bos", "mss"))],
                         [("bos_bear", 5, 98.0), ("mss_bull", 10, 98.4)])

    def test_close_short_of_the_swing_is_no_break(self):
        rows = STRUCT[:-1] + [(97.4, 98.8, 97.3, 98.3)]
        ev = ef.detect(mk(rows), P(swing_k=1, atr_n=50))
        self.assertEqual([e["kind"] for e in ev if e["kind"].startswith(("bos", "mss"))], ["bos_bear"])


class DisplacementAndOB(unittest.TestCase):
    BEAR = (100.2, 100.5, 99.5, 100.0)

    def test_displacement_and_its_order_block(self):
        ev = ef.detect(mk([FLAT] * 5 + [self.BEAR, (100, 101.6, 99.9, 101.5)]), P())
        d = of(ev, "displacement_bull")
        self.assertEqual([(e["known_i"], round(e["body_atr"], 9)) for e in d], [(6, 1.5)])
        ob = of(ev, "ob_bull")
        self.assertEqual([(e["i"], e["known_i"], e["zone_lo"], e["zone_hi"]) for e in ob], [(5, 6, 99.5, 100.5)])

    def test_small_body_is_no_displacement(self):
        ev = ef.detect(mk([FLAT] * 5 + [self.BEAR, (100, 101.1, 99.9, 101.0)]), P())
        self.assertEqual(of(ev, "displacement_bull") + of(ev, "ob_bull"), [])

    def test_no_opposite_bar_no_order_block(self):
        ev = ef.detect(mk([FLAT] * 6 + [(100, 101.6, 99.9, 101.5)]), P())
        self.assertEqual(len(of(ev, "displacement_bull")), 1)
        self.assertEqual(of(ev, "ob_bull"), [])


class FVG(unittest.TestCase):
    ROWS = [FLAT] * 3 + [(100, 102, 99.9, 101.9), (101.9, 102.5, 100.8, 102.3)]

    def test_three_bar_gap(self):
        ev = of(ef.detect(mk(self.ROWS), P()), "fvg_bull")
        self.assertEqual([(e["i"], e["known_i"], e["zone_lo"], e["zone_hi"], e["ts"]) for e in ev],
                         [(3, 4, 100.5, 100.8, T0 + 3 * BS)])

    def test_touching_bars_are_no_gap_and_a_minimum_size_applies(self):
        rows = self.ROWS[:-1] + [(101.9, 102.5, 100.5, 102.3)]
        self.assertEqual(of(ef.detect(mk(rows), P()), "fvg_bull"), [])
        self.assertEqual(of(ef.detect(mk(self.ROWS), P(atr_n=3, fvg_min_atr=0.5)), "fvg_bull"), [])

    def test_inversion(self):
        ev = ef.detect(mk(self.ROWS + [(102.3, 102.4, 100.2, 100.3)]), P())
        inv = of(ev, "ifvg_bear")
        self.assertEqual([(e["i"], e["known_i"], e["dir"]) for e in inv], [(3, 5, -1)])
        ev = ef.detect(mk(self.ROWS + [(102.3, 102.4, 100.6, 100.7)]), P())
        self.assertEqual(of(ev, "ifvg_bear"), [])


class SessionsAndRejections(unittest.TestCase):
    def test_session_open_bar(self):
        t0 = T0 + 6 * 3600 + 50 * 60
        bars = mk([FLAT] * 4, t0)
        ev = ef.detect(bars, P(sessions=(("london", "07:00"), ("x", "07:02"), ("y", "07:10"))))
        got = [(e["kind"], e["known_i"], e["session_ts"]) for e in ev if e["kind"].startswith("session")]
        self.assertEqual(got, [("session_open_london", 2, T0 + 7 * 3600), ("session_open_x", 2, T0 + 7 * 3600 + 120)])

    def test_rejection_needs_a_long_wick_and_a_wide_range(self):
        ev = ef.detect(mk([FLAT] * 5 + [(100, 101.5, 99.95, 100.1)]), P())
        self.assertEqual([e["known_i"] for e in of(ev, "rejection_high")], [5])
        ev = ef.detect(mk([FLAT] * 5 + [(100, 100.4, 99.95, 100.05)]), P())
        self.assertEqual(of(ev, "rejection_high"), [])


# A sell-side sweep (bar 13) in a down structure, then mss_bull at bar 15 with a bullish FVG known at bar 15.
CHAIN = [FLAT] * 4 + [(100, 101, 99.8, 100.6), (100.6, 100.7, 99.6, 99.7), (99.7, 99.9, 99.0, 99.1),
                      (99.1, 99.6, 99.05, 99.5), (99.5, 99.7, 98.5, 98.6), (98.6, 98.8, 98.0, 98.2),
                      (98.2, 98.9, 98.1, 98.8), (98.8, 99.2, 98.7, 99.0), (99.0, 99.1, 98.6, 98.7),
                      (98.7, 98.75, 97.6, 98.3), (98.3, 99.0, 98.2, 98.95), (98.95, 99.6, 98.9, 99.5)]
CP = P(swing_k=1, atr_n=3, cost_bps=1.0, rr=2.0, entry_mode="mid", anchor="fvg_then_ob")


def chain_setups(rows, **kw):
    bars = mk(rows)
    p = {**CP, **kw}
    setups, stats = ef.build_setups(ef.detect(bars, p), bars, p)
    return bars, setups, stats


class Chains(unittest.TestCase):
    def test_sweep_mss_fvg_gives_one_setup_fixed_at_the_break(self):
        bars, setups, stats = chain_setups(CHAIN)
        self.assertEqual(len(setups), 1, stats)
        s = setups[0]
        self.assertEqual((s["kind"], s["chain"], s["known_i"], s["sweep_known_i"]),
                         ("setup_long", "sweep_low>mss_bull>fvg_bull", 15, 13))
        self.assertAlmostEqual(s["entry"], (98.75 + 98.9) / 2)
        self.assertEqual(s["stop"], 97.6)
        self.assertAlmostEqual(s["target"], s["entry"] + 2 * (s["entry"] - 97.6))
        self.assertEqual(s["known_ts"], T0 + 15 * BS + BS)
        self.assertEqual(stats, {"setup": 1, "sweep_break": 1})

    def test_no_sweep_no_setup(self):
        rows = CHAIN[:13] + [(98.7, 98.75, 98.1, 98.3)] + CHAIN[14:]            # low stays above the swing low
        self.assertEqual(chain_setups(rows)[1], [])

    def test_no_anchor_is_counted_not_traded(self):
        _, setups, stats = chain_setups(CHAIN, anchor="ob")
        self.assertEqual(setups, [])
        self.assertEqual(stats.get("no_anchor"), 1)

    def test_window_and_break_kinds(self):
        self.assertEqual(chain_setups(CHAIN, mss_window=1)[1], [])
        self.assertEqual(len(chain_setups(CHAIN, chain_breaks=("bos",))[1]), 0)

    def test_market_and_edge_entries(self):
        self.assertEqual(chain_setups(CHAIN, entry_mode="market")[1][0]["entry"], 99.5)
        self.assertEqual(chain_setups(CHAIN, entry_mode="edge")[1][0]["entry"], 98.9)

    def test_tiny_risk_is_discarded(self):
        _, setups, stats = chain_setups(CHAIN, min_risk_atr=5.0)
        self.assertEqual((setups, stats.get("bad_risk")), ([], 1))


class Outcomes(unittest.TestCase):
    def run_rows(self, after, **kw):
        bars, setups, _ = chain_setups(CHAIN + after, **kw)
        p = {**CP, **kw}
        return setups[0], ef.setup_outcome(setups[0], bars, p)

    def test_fill_then_target(self):
        s, o = self.run_rows([(99.5, 99.7, 98.8, 99.0), (99.0, 101.4, 98.9, 101.3)])
        self.assertEqual((o["status"], o["fill_i"], o["exit_i"]), ("target", 16, 17))
        self.assertAlmostEqual(o["gross_r"], 2.0)
        self.assertAlmostEqual(o["net_r"], 2.0 - 1e-4 * s["entry"] / s["risk"])
        self.assertAlmostEqual(o["net_bps"], o["gross_bps"] - 1.0)

    def test_bar_hitting_both_is_a_stop(self):
        s, o = self.run_rows([(99.5, 99.7, 98.8, 99.0), (99.0, 101.4, 97.5, 99.0)])
        self.assertEqual((o["status"], o["both_hit_bars"]), ("stop", 1))
        self.assertAlmostEqual(o["gross_r"], -1.0)
        _, o2 = self.run_rows([(99.5, 99.7, 98.8, 99.0), (99.0, 101.4, 97.5, 99.0)], ambiguous="target_first")
        self.assertEqual(o2["status"], "target")

    def test_fill_bar_counts_only_the_stop(self):
        _, o = self.run_rows([(99.5, 101.4, 97.5, 99.0)])
        self.assertEqual((o["status"], o["fill_i"], o["exit_i"]), ("stop", 16, 16))

    def test_gap_through_the_stop_exits_at_the_open(self):
        s, o = self.run_rows([(99.5, 99.7, 98.8, 99.0), (97.0, 97.2, 96.8, 97.1)])
        self.assertEqual(o["exit_px"], 97.0)
        self.assertAlmostEqual(o["gross_r"], (97.0 - s["entry"]) / s["risk"])

    def test_missed_no_fill_timeout_incomplete(self):
        self.assertEqual(self.run_rows([(99.5, 101.3, 99.4, 101.0)])[1]["status"], "missed")
        self.assertEqual(self.run_rows([(99.5, 99.7, 99.4, 99.6)] * 2, fill_window=2)[1]["status"], "no_fill")
        s, o = self.run_rows([(99.5, 99.7, 98.8, 99.0)] + [(99.0, 99.2, 98.9, 99.1)] * 2, max_hold=2)
        self.assertEqual((o["status"], o["exit_px"]), ("timeout", 99.1))
        self.assertEqual(self.run_rows([(99.5, 99.7, 98.8, 99.0)])[1]["status"], "incomplete")
        self.assertIsNone(self.run_rows([(99.5, 99.7, 98.8, 99.0)])[1]["net_r"])

    def test_event_outcome_uses_only_later_bars(self):
        rows = [FLAT] * 5 + [(100.2, 100.5, 99.5, 100.0), (100, 101.6, 99.9, 101.5), (101.5, 102.0, 101.0, 101.8),
                             (101.8, 101.9, 100.9, 101.0)]
        bars = mk(rows)
        p = P(horizons=(1, 2, 3))
        d = of(ef.detect(bars, p), "displacement_bull")[0]
        o = ef.event_outcome(d, bars, p)
        a = ef.atr_at(bars, 6, 5)
        self.assertAlmostEqual(o["ret_atr"][1], 0.3 / a)
        self.assertAlmostEqual(o["ret_atr"][2], -0.5 / a)
        self.assertIsNone(o["ret_atr"][3])
        self.assertIsNone(o["mfe_atr"])                 # the longest horizon is not complete: no partial MFE
        self.assertAlmostEqual(o["net_bps"][1], 0.3 / 101.5 * 1e4 - 1.0)
        o2 = ef.event_outcome(d, bars + [(bars[-1][0] + BS, 101.0, 103.0, 100.0, 102.0, 1.0)], p)
        self.assertAlmostEqual(o2["mfe_atr"], (103.0 - 101.5) / a)
        self.assertAlmostEqual(o2["mae_atr"], (101.5 - 100.0) / a)


def continuation(bars, t, seed):
    """bars[:t + 1] followed by a different random walk from the same price and time."""
    rw = ef.random_walk_bars(seed, 2)
    f = bars[t][4] / rw[0][1]
    tail = [(bars[t][0] + BS * (k + 1), o * f, h * f, lo * f, c * f, v) for k, (_, o, h, lo, c, v) in enumerate(rw)]
    return bars[:t + 1] + tail


class Lookahead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bars = ef.random_walk_bars(7, 6)
        cls.p = ef.params()
        cls.full = ef.detect(cls.bars, cls.p)
        cls.setups = ef.build_setups(cls.full, cls.bars, cls.p)[0]

    def test_events_are_never_known_before_their_pattern(self):
        self.assertGreater(len(self.full), 500)
        for e in self.full + self.setups:
            self.assertLessEqual(e["i"], e["known_i"])
            self.assertEqual(e["known_ts"], self.bars[e["known_i"]][0] + BS)
            self.assertLessEqual(e["ts"], e["known_ts"] - BS)

    def test_truncating_or_rewriting_the_future_changes_nothing_known(self):
        for n, t in enumerate((40, 333, 900, 1500)):
            want_e = [e for e in self.full if e["known_i"] <= t]
            want_s = [s for s in self.setups if s["known_i"] <= t]
            cut = self.bars[:t + 1]
            self.assertEqual(ef.detect(cut, self.p), want_e)
            other = continuation(self.bars, t, 100 + n)
            self.assertNotEqual(other[t + 1:t + 50], self.bars[t + 1:t + 50])
            ev = ef.detect(other, self.p)
            self.assertEqual([e for e in ev if e["known_i"] <= t], want_e)
            st = ef.build_setups(ev, other, self.p)[0]
            self.assertEqual([s for s in st if s["known_i"] <= t], want_s)

    def test_validation_engine_truncation_check(self):
        r = ve.check_lookahead(signal_fn=ef.lookahead_signal(self.p), data=self.bars[:800], n_checks=10)
        self.assertEqual(r["status"], ve.PASS, r)

        def leaky(bars):                                 # negative control: peeks one bar ahead
            return [bars[min(t + 1, len(bars) - 1)][4] for t in range(len(bars))]
        self.assertEqual(ve.check_lookahead(signal_fn=leaky, data=self.bars[:800], n_checks=10)["status"], ve.FAIL)


class Determinism(unittest.TestCase):
    def test_same_input_same_output(self):
        bars = ef.random_walk_bars(11, 3)
        r1, r2 = ef.farm(bars), ef.farm(list(bars))
        self.assertEqual(r1, r2)
        st1 = ef.study_markdown(ef.study({"A": r1}, {"A": bars}))
        st2 = ef.study_markdown(ef.study({"A": r2}, {"A": bars}))
        self.assertEqual(st1, st2)
        self.assertIn("## Farm study pr. dag", st1)
        self.assertIn("| 2026-01-05 | 100 % |", st1)

    def test_bad_input_and_parameters_are_refused(self):
        with self.assertRaises(ValueError):
            ef.detect([(0, 1, 0.5, 0.4, 1, 1)])                       # high below open
        with self.assertRaises(ValueError):
            ef.detect([(5, 1, 1, 1, 1, 1), (5, 1, 1, 1, 1, 1)])       # ts not increasing
        with self.assertRaises(ValueError):
            ef.params(no_such=1)
        with self.assertRaises(ValueError):
            ef.params(ambiguous="optimistic")

    def test_coverage_counts_missing_bars(self):
        bars = [b for k, b in enumerate(ef.random_walk_bars(3, 1)) if k % 4]
        st = ef.study({"A": ef.farm(bars)}, {"A": bars})
        self.assertAlmostEqual(st["days"]["2026-01-05"]["coverage"]["A"], 0.75)


class NullOnNoise(unittest.TestCase):
    """The centre of the note: the same patterns appear in pure noise, and setups earn nothing there after costs."""

    @classmethod
    def setUpClass(cls):
        cls.s = ef.null_run(seed=83, instruments=1, days=30)

    def pooled_net(self, cost):
        vs = [v for v in self.s["variants"].values() if v["trades"]]
        return sum(v["net"][cost]["mean_net_r"] * v["trades"] for v in vs) / sum(v["trades"] for v in vs)

    def test_patterns_are_plentiful_in_noise(self):
        s = self.s
        self.assertEqual((s["days"], s["bars"]), (30, 30 * 288))
        self.assertGreater(s["events_per_instrument_day"], 100)
        for k in ("sweep_low", "sweep_high", "mss_bull", "mss_bear", "fvg_bull", "ob_bear", "liquidity_pool_high"):
            self.assertGreater(s["per_kind_per_instrument_day"][k], 0.5, k)
        self.assertGreater(s["pooled_trades"], 300)

    def test_setups_earn_nothing_and_lose_after_costs(self):
        s = self.s
        self.assertLess(abs(s["pooled_mean_gross_r"]), 0.1)
        for vid, v in s["variants"].items():
            if v["t_gross"] is not None:
                self.assertLess(abs(v["t_gross"]), 3.0, vid)
        self.assertLess(self.pooled_net("1"), self.pooled_net("0"))
        self.assertLess(self.pooled_net("5"), 0.0)

    def test_validation_engine_on_the_null(self):
        c = ef.validate_null(self.s, lookahead_bars=600)
        self.assertEqual(c["lookahead"]["status"], ve.PASS)
        self.assertNotEqual(c["multiple_testing"]["status"], ve.PASS)
        self.assertEqual(c["multiple_testing"]["metrics"]["n_used"], len(ef.VARIANTS))
        self.assertEqual(c["costs"]["status"], ve.FAIL)
        self.assertNotEqual(c["assess"]["status"], ve.PASS)

    def test_register_v2_records_are_valid_and_count_every_variant(self):
        recs = ef.v2_records(self.s)
        self.assertEqual([r["record_id"] for r in recs], ["EVENT_FARM_NULL_SETUPS", "EVENT_FARM_NULL_EVENTS"])
        for r in recs:
            self.assertEqual(v2.validate(r), [])
            self.assertEqual(r["era"], v2.FUTURE)
            self.assertEqual(r["variants_tested"]["count"], r["trial_universe"]["size"])
        self.assertEqual(recs[0]["variants_tested"]["count"], 12)
        n_kinds = len([k for k in ef.kinds() if not k.startswith("setup_")])
        self.assertEqual(recs[1]["variants_tested"]["count"], n_kinds * len(ef.DEFAULTS["horizons"]))
        self.assertEqual(v2.validation_inputs(recs[0])["n_tested"], 12)


class Hygiene(unittest.TestCase):
    def test_the_engine_opens_no_data_and_names_no_host(self):
        with open(os.path.join(HERE, "research", "tools", "event_farm.py"), encoding="utf-8") as f:
            src = f.read()
        for bad in ("http", "socket", "sqlite", "lab.db", "urllib", "requests", "data/"):
            self.assertNotIn(bad, src, bad)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
