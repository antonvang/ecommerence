"""Director order 100 (design only): the isolated event farm forward paper book on synthetic 5m bars. Databases live in a
temporary directory; no market data, no network, no activation."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_forward as fw  # noqa: E402

BS = 300
SYMS = ["SYN1", "SYN2"]
CFG = {"warmup_bars": 50, "coverage_window_bars": 40}


def series(days=3):
    return {"SYN1": ef.random_walk_bars(31, days), "SYN2": ef.random_walk_bars(32, days)}


class Run:
    """A book in a temporary directory fed by a synthetic source with an injected clock."""

    def __init__(self, tmp, name="event_farm_forward_t.db", config=CFG):
        self.src, self.now = fw.SyntheticSource(), [0]
        self.path = os.path.join(tmp, name)
        self.config = config
        self.book = self.open()

    def open(self):
        return fw.ForwardBook(self.path, self.src, SYMS, clock=lambda: self.now[0], config=self.config)

    def feed(self, bars, k0, k1):
        for s in SYMS:
            self.src.publish(s, bars[s][k0:k1])
        self.now[0] = bars[SYMS[0]][k1 - 1][0] + BS
        return self.book.step()


def offline(bars, warmup):
    """What the engine says over the full history: setups from the warmup on and their outcomes."""
    out = {}
    for vid, v in fw.variants():
        pv = ef.params(**v)
        for s, bb in bars.items():
            st, _ = ef.build_setups(ef.detect(bb, pv), bb, pv)
            for x in st:
                if x["known_i"] >= warmup:
                    o = ef.setup_outcome(x, bb, pv)
                    status = "pending" if o["status"] == "incomplete" else o["status"]
                    out[(vid, s, x["known_ts"], x["kind"])] = (x["entry"], x["stop"], x["target"], status, o["exit_px"])
    return out


def booked(book):
    rows = book.db.execute("SELECT variant, symbol, known_ts, kind, entry, stop, target, status, exit_px FROM trades "
                           "WHERE status NOT LIKE 'not_taken%'").fetchall()
    return {r[:4]: tuple(r[4:]) for r in rows}


class Refusals(unittest.TestCase):
    def test_database_paths_are_checked_as_strings_before_any_file_access(self):
        boom = AssertionError("file system touched")
        with mock.patch("builtins.open", side_effect=boom), mock.patch("os.stat", side_effect=boom), \
                mock.patch("sqlite3.connect", side_effect=boom):
            for p in ("/home/anton/ecommerence/copybot/data/event_farm_forward.db",
                      "/home/anton/ecommerence/copybot/lab.db", "/tmp/x/pm_lp.db", "/tmp/x/lab.db",
                      "/tmp/x/forward.db", "/tmp/research/data/event_farm_forward.db", ""):
                with self.assertRaises(fw.SourceRefused):
                    fw.check_db_path(p)
                with self.assertRaises(fw.SourceRefused):
                    fw.ForwardBook(p, fw.SyntheticSource(), SYMS)

    def test_sources_symbols_and_live_mode_are_refused_before_a_database_exists(self):
        boom = AssertionError("database opened")
        ok = os.path.join(tempfile.gettempdir(), "event_farm_forward_never.db")
        with mock.patch("sqlite3.connect", side_effect=boom):
            with self.assertRaises(fw.SourceRefused):
                fw.ForwardBook(ok, fw.SyntheticSource({"source": "fapi_klines_5m"}), SYMS)
            with self.assertRaises(fw.SourceRefused):
                fw.ForwardBook(ok, fw.SyntheticSource(), ["BTCUSDT", "ETHUSDT"])
            with self.assertRaises(fw.SourceRefused):
                fw.ForwardBook(ok, fw.SyntheticSource(), SYMS, mode="paper")
            with self.assertRaises(fw.NotActivated):
                fw.ForwardBook(ok, fw.SyntheticSource({"source": "x"}), list(fw.LIVE_SYMBOLS), mode="live")

            class Say:
                def __init__(self, v):
                    self.v = v

                def approved(self, action):
                    return self.v
            for v in (False, 1, "yes", None):
                with self.assertRaises(fw.NotActivated):
                    fw.ForwardBook(ok, fw.SyntheticSource(), list(fw.LIVE_SYMBOLS), mode="live", activation=Say(v))
            with self.assertRaises(fw.SourceRefused):
                fw.ForwardBook(ok, fw.SyntheticSource(), list(fw.LIVE_SYMBOLS), mode="live", activation=Say(True),
                               config={"warmup_bars": 1})
        self.assertFalse(os.path.exists(ok))

    def test_the_module_has_no_network_code(self):
        with open(os.path.join(HERE, "research", "tools", "event_farm_forward.py"), encoding="utf-8") as f:
            src = f.read()
        for bad in ("import socket", "urllib", "http.client", "import requests", "://", "binance.com", "subprocess"):
            self.assertNotIn(bad, src, bad)


class Equivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bars = series()
        cls.n = len(cls.bars["SYN1"])
        cls.one = Run(cls.tmp.name, "event_farm_forward_one.db")
        for k in range(cls.n):
            cls.one.feed(cls.bars, k, k + 1)
        cls.chunk = Run(cls.tmp.name, "event_farm_forward_chunk.db")
        for k in range(0, cls.n, 37):
            cls.chunk.feed(cls.bars, k, min(cls.n, k + 37))

    @classmethod
    def tearDownClass(cls):
        cls.one.book.close()
        cls.chunk.book.close()
        cls.tmp.cleanup()

    def test_bar_by_bar_equals_the_offline_engine(self):
        want = offline(self.bars, CFG["warmup_bars"])
        got = booked(self.one.book)
        self.assertGreater(len(got), 100)
        self.assertEqual(got, want)

    def test_batching_does_not_change_the_book(self):
        self.assertEqual(self.one.book.dump(), self.chunk.book.dump())

    def test_known_ts_rules(self):
        db = self.one.book.db
        for known_ts, k, fill_ts, exit_ts, mode, delay in db.execute(
                "SELECT known_ts, known_i, fill_ts, exit_ts, entry_mode, booking_delay_s FROM trades"):
            self.assertEqual(known_ts, self.bars["SYN1"][k][0] + BS)
            self.assertEqual(delay, 0)                               # booked when its bar closed (injected clock)
            if fill_ts is not None:
                self.assertGreaterEqual(fill_ts + BS, known_ts)
                if mode != "market":
                    self.assertGreaterEqual(fill_ts, known_ts)
            if exit_ts is not None and fill_ts is not None:
                self.assertGreater(exit_ts, fill_ts)
        for k, known_ts in db.execute("SELECT known_i, known_ts FROM events WHERE symbol = 'SYN2'"):
            self.assertEqual(known_ts, self.bars["SYN2"][k][0] + BS)

    def test_warmup_setups_are_recorded_not_taken(self):
        rows = self.one.book.db.execute("SELECT known_i, status, exit_px FROM trades WHERE known_i < 50").fetchall()
        self.assertEqual(len(rows), len(offline(self.bars, 0)) - len(offline(self.bars, 50)))
        self.assertTrue(all(r[1] == "not_taken_warmup" and r[2] is None for r in rows))
        late = self.one.book.db.execute("SELECT COUNT(*) FROM trades WHERE known_i >= 50 AND status = "
                                        "'not_taken_warmup'").fetchone()[0]
        self.assertEqual(late, 0)

    def test_idempotent_steps(self):
        before = self.one.book.dump(with_steps=True)
        self.assertEqual(set(self.one.book.step().values()), {0})
        self.one.src.push_once("SYN1", self.bars["SYN1"][100:110])          # re-delivery of identical bars
        self.assertEqual(set(self.one.book.step().values()), {0})
        self.assertEqual(self.one.book.dump(with_steps=True), before)

    def test_report_is_deterministic_and_compares_with_the_null(self):
        null = ef.null_run(seed=83, instruments=1, days=2)
        r1, r2 = fw.report(self.one.book, null), fw.report(self.chunk.book, null)
        self.assertEqual(r1["variants"], r2["variants"])
        self.assertEqual(r1["null"]["seed"], 83)
        self.assertEqual(len(r1["variants"]), 12)
        self.assertIn("ingen evidens", r1["label"])
        v = r1["variants"]["fvg/rr2/market"]
        self.assertIn("null", v)
        self.assertEqual(set(v["mean_net_r_grid"]), {"0", "1", "5", "8"})


class Restart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bars = series(2)
        self.n = len(self.bars["SYN1"])

    def test_reopen_mid_run_gives_the_same_book(self):
        ref = Run(self.tmp.name, "event_farm_forward_ref.db")
        ref.feed(self.bars, 0, self.n)
        r = Run(self.tmp.name, "event_farm_forward_re.db")
        r.feed(self.bars, 0, 300)
        r.book.close()
        r.book = r.open()                                             # restart: state rebuilt from the file
        r.feed(self.bars, 300, self.n)
        self.assertEqual(r.book.dump(), ref.book.dump())
        r.book.close()
        ref.book.close()

    def test_a_crash_inside_a_step_rolls_back_and_the_next_step_recovers(self):
        ref = Run(self.tmp.name, "event_farm_forward_ref2.db")
        ref.feed(self.bars, 0, self.n)
        r = Run(self.tmp.name, "event_farm_forward_crash.db")
        r.feed(self.bars, 0, 250)
        before = r.book.dump(with_steps=True)
        calls = {"n": 0}
        real = r.book._book

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 40:
                raise OSError("simulated crash")
            return real(*a, **k)
        with mock.patch.object(r.book, "_book", side_effect=flaky):
            with self.assertRaises(OSError):
                r.feed(self.bars, 250, self.n)
        self.assertEqual(r.book.dump(with_steps=True), before)
        self.assertEqual(len(r.book.bars["SYN1"]), 250)
        r.book.step()                                                 # the source re-delivers everything after 250
        self.assertEqual(r.book.dump(), ref.book.dump())
        r.book.close()
        ref.book.close()

    def test_a_changed_identity_is_refused(self):
        r = Run(self.tmp.name, "event_farm_forward_id.db")
        r.feed(self.bars, 0, 10)
        r.book.close()
        with self.assertRaises(fw.IntegrityHalt):
            fw.ForwardBook(r.path, r.src, SYMS, clock=lambda: 0, config={"warmup_bars": 51})

    def test_an_integrity_break_halts_the_book_for_good(self):
        r = Run(self.tmp.name, "event_farm_forward_halt.db")
        r.feed(self.bars, 0, 60)
        before = r.book.dump(with_steps=True)
        real = r.book.farm["SYN1"].step

        def leak(bar):
            out = real(bar)
            return out + [dict(out[0], known_i=out[0]["known_i"] + 1)] if out else [{"kind": "swing_high", "ts": bar[0],
                                                                                     "known_ts": bar[0], "i": 0,
                                                                                     "known_i": -1, "dir": 0}]
        r.book.farm["SYN1"].step = leak
        with self.assertRaises(fw.IntegrityHalt):
            r.feed(self.bars, 60, 61)
        self.assertTrue(r.book.halted())
        self.assertEqual(r.book.dump(with_steps=True), before)
        with self.assertRaises(fw.IntegrityHalt):
            r.book.step()


class DataQuality(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bars = series(1)
        self.r = Run(self.tmp.name, "event_farm_forward_dq.db")
        self.db = self.r.book.db

    def publish(self, s, rows, now):
        self.r.src.publish(s, rows)
        self.r.now[0] = now
        return self.r.book.step()

    def test_gap_is_waited_for_then_declared_and_a_late_bar_is_never_processed(self):
        b = self.bars["SYN1"]
        self.publish("SYN1", b[:100], b[99][0] + BS)
        self.publish("SYN1", b[101:102], b[101][0] + BS)             # bar 100 missing, 300 s beyond: wait
        self.assertEqual(len(self.r.book.bars["SYN1"]), 100)
        self.publish("SYN1", b[102:103], b[102][0] + BS)             # 600 s beyond: gap declared
        self.assertEqual(len(self.r.book.bars["SYN1"]), 102)
        self.assertEqual(self.db.execute("SELECT from_ts, to_ts, n_bars FROM gaps").fetchall(), [(b[100][0], b[100][0], 1)])
        self.r.src.push_once("SYN1", [b[100]])
        self.r.book.step()
        self.assertEqual(self.db.execute("SELECT ts, in_gap FROM late_bars").fetchall(), [(b[100][0], 1)])
        self.assertNotIn(b[100], self.r.book.bars["SYN1"])
        self.assertEqual(fw.report(self.r.book)["data"]["SYN1"]["gaps"], (1, 1))

    def test_unclosed_offgrid_bad_and_revised_bars(self):
        b = self.bars["SYN1"]
        self.publish("SYN1", b[:10], b[8][0] + BS)                    # bar 9 is not closed yet
        self.assertEqual(len(self.r.book.bars["SYN1"]), 9)
        self.assertEqual(self.db.execute("SELECT reason FROM rejected").fetchall(), [("not_closed",)])
        self.r.now[0] = b[9][0] + BS
        self.r.book.step()
        self.assertEqual(len(self.r.book.bars["SYN1"]), 10)
        t = b[10][0]
        self.r.src.push_once("SYN1", [(t + 7,) + b[10][1:], (t, 1.0, 0.5, 0.9, 1.0, 1.0), "junk",
                                      (b[5][0], b[5][1], b[5][2] * 1.01, b[5][3], b[5][4], b[5][5])])
        self.r.now[0] = t + 10 * BS
        self.r.book.step()
        reasons = sorted(r[0] for r in self.db.execute("SELECT reason FROM rejected"))
        self.assertEqual(reasons, ["not_closed", "off_grid", "ohlc", "shape"])
        self.assertEqual(self.db.execute("SELECT ts, processed FROM conflicts").fetchall(), [(b[5][0], 1)])
        self.assertEqual(self.r.book.bars["SYN1"][5], b[5])           # the first value is kept

    def test_gap_affected_flags_match_the_gap_table(self):
        bb = series(2)
        r = Run(self.tmp.name, "event_farm_forward_gaps.db", config={"warmup_bars": 20, "coverage_window_bars": 10,
                                                                     "coverage_min": 0.5})
        for s in SYMS:
            r.src.publish(s, [x for k, x in enumerate(bb[s]) if not 200 <= k < 203 and not 400 <= k < 401])
        r.now[0] = bb["SYN1"][-1][0] + BS
        r.book.step()
        gaps = r.book.db.execute("SELECT symbol, from_ts, to_ts FROM gaps").fetchall()
        self.assertEqual(len(gaps), 4)
        last = r.book.bars["SYN1"][-1][0]
        n_flag = 0
        for s, kts, ex, flag, st in r.book.db.execute("SELECT symbol, known_ts, exit_ts, gap_affected, status FROM trades "
                                                      "WHERE status IN ('pending', 'target', 'stop', 'timeout')"):
            hi = ex if ex is not None else last
            want = any(g[0] == s and g[2] >= kts and g[1] <= hi for g in gaps)
            self.assertEqual(bool(flag), want)
            n_flag += flag
        self.assertGreater(n_flag, 0)
        rep = fw.report(r.book)
        self.assertTrue(all(v["worst_case_mean_net_r_lab"] is None or v["mean_net_r_lab"] is None or
                            v["worst_case_mean_net_r_lab"] <= v["mean_net_r_lab"] + 1e-12 or v["gap_affected"] == 0
                            for v in rep["variants"].values()))
        r.book.close()


class RegisterPlan(unittest.TestCase):
    def test_twelve_future_records_with_the_reference_n(self):
        from research.tools import register_v2 as v2
        from research.tools import validation_engine as ve
        recs = fw.v2_plan_records("2026-12-01", "2027-02-28")
        self.assertEqual(len(recs), 12)
        self.assertEqual(len({r["record_id"] for r in recs}), 12)
        for r in recs:
            self.assertEqual(v2.validate(r), [])
            self.assertEqual((r["era"], r["trial_universe"]["size"]), (v2.FUTURE, 12))
            vals = r["parameters"]["values"]
            self.assertEqual((vals["reference_n_min"], vals["reference_n_forward"]), (19753, 19765))
            self.assertFalse(vals["independent_lineage"] or vals["activated"])
            self.assertAlmostEqual(r["cost_model"]["round_trip_bps"], 28.0)
        mt = ve.check_multiple_testing(best_t=4.0, n_tested=12, n_reported=fw.REFERENCE_N_FORWARD)
        self.assertEqual(mt["metrics"]["n_used"], 19765)
        self.assertNotEqual(mt["status"], ve.PASS)


class Costs(unittest.TestCase):
    def test_lab_costs_charge_taker_slippage_and_half_spread_on_both_fills(self):
        c = fw.lab_costs({"dir": 1, "entry": 100.0, "risk": 1.0}, 102.0, fw.FROZEN_CONFIG)
        self.assertAlmostEqual(c["gross_usdt"], 20.0)
        self.assertAlmostEqual(c["fees_usdt"], 0.001 * 10 * 202)
        self.assertAlmostEqual(c["slippage_usdt"], 0.0004 * 10 * 202)
        self.assertAlmostEqual(c["net_r_lab"], (20.0 - 2.02 - 0.808) / 10)
        s = fw.lab_costs({"dir": -1, "entry": 100.0, "risk": 2.0}, 100.0, fw.FROZEN_CONFIG)
        self.assertAlmostEqual(s["net_usdt"], -(0.0014 * 10 * 200))

    def test_variant_stop_is_consistent_with_the_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            bb = series(2)
            r = Run(tmp, "event_farm_forward_stop.db", config={"warmup_bars": 20, "coverage_window_bars": 10,
                                                               "account_stop_usdt": 9999.0})
            r.feed(bb, 0, len(bb["SYN1"]))
            db = r.book.db
            stopped = db.execute("SELECT variant, known_ts FROM trades WHERE status = 'not_taken_variant_stopped'").fetchall()
            self.assertTrue(stopped)
            for vid, kts in stopped:
                acct = 10000 + db.execute("SELECT COALESCE(SUM(net_usdt), 0) FROM trades WHERE variant = ? AND "
                                          "exit_ts < ? AND status IN ('target', 'stop', 'timeout')", (vid, kts)).fetchone()[0]
                self.assertLessEqual(acct, 9999.0)
            r.book.close()


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
