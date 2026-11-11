"""Director order 90: the event farm synthetic driver. Synthetic fixtures only, written to a temporary directory; no market
data, no network. A production-cache path is refused before anything touches the file system."""
import inspect
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_driver as drv  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402
from research.tools import validation_engine as ve  # noqa: E402

T0 = ef.START


def minutes(rows, t0=T0):
    return [(t0 + 60 * k, o, h, l, c, 1.0) for k, (o, h, l, c) in enumerate(rows)]


def no_fs():
    """Every way to touch a file fails the test."""
    boom = AssertionError("the file system was touched")
    return [mock.patch("builtins.open", side_effect=boom), mock.patch("os.stat", side_effect=boom),
            mock.patch("os.lstat", side_effect=boom), mock.patch("os.path.realpath", side_effect=boom),
            mock.patch("os.path.exists", side_effect=boom), mock.patch("os.listdir", side_effect=boom)]


class Engine(unittest.TestCase):
    def test_frozen_engine_is_verified(self):
        self.assertIs(drv.engine(), ef)
        self.assertEqual(drv.ENGINE_COMMIT, "f686c9a")

    def test_a_changed_engine_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "event_farm.py")
            with open(p, "w") as f:
                f.write("# not the frozen engine\n")
            with self.assertRaises(drv.EngineMismatch):
                drv.engine(p)


class Register(unittest.TestCase):
    def test_315_tests_counted_once(self):
        tests = drv.all_tests()
        self.assertEqual(len(tests), 315)
        self.assertEqual(len(set(tests)), 315)
        self.assertEqual(len(drv.setup_test_ids()), 13)
        self.assertEqual(len(drv.event_test_ids()), 92)

    def test_v2_records_related_mechanism_no_independence(self):
        recs = drv.v2_records()
        self.assertEqual([r["record_id"] for r in recs], ["EVENT_FARM_EXPLORE0_SETUPS", "EVENT_FARM_EXPLORE0_EVENTS"])
        fam = []
        for r in recs:
            self.assertEqual(v2.validate(r), [])
            self.assertEqual((r["era"], r["trial_universe"]["size"]), (v2.FUTURE, 315))
            self.assertEqual(r["variants_tested"], v2.MISSING_INPUT)
            vals = r["parameters"]["values"]
            self.assertEqual(vals["classification"], "RELATED_MECHANISM")
            self.assertFalse(vals["independent_lineage"])
            self.assertFalse(vals["independent_discovery_claim"])
            for lid in ("MOVESCREEN_m21c", "E_daily_reversal_p1", "L21_m2_liquidation_reversal", "L03_sol_trend_hourly",
                        "L14_tsmom_v1", "E_donchian_trend_p1"):
                self.assertIn(lid, str(vals["related_lineages"]))
            self.assertIn("RELATED_MECHANISM", r["lineage"])
            self.assertEqual(r["code_hash"], drv.ENGINE_SHA256)
            fam.append(vals["family_tests"])
        self.assertEqual(fam, [39, 276])
        self.assertEqual(sum(fam), 315)
        inp = v2.validation_inputs(recs[0])
        mt = ve.check_multiple_testing(best_t=3.0, n_preregistered=inp["n_preregistered"], n_reported=40)
        self.assertEqual(mt["metrics"]["n_used"], 315)


class Aggregation(unittest.TestCase):
    def test_1m_to_5m_and_15m(self):
        rows = [(100 + k, 100.5 + k, 99.5 + k, 100.2 + k) for k in range(30)]
        b1 = minutes(rows)
        b5, g5 = drv.aggregate(b1, 300)
        self.assertEqual(len(b5), 6)
        self.assertEqual(b5[0], (T0, 100, 104.5, 99.5, 104.2, 5.0))
        b15, g15 = drv.aggregate(b1, 900)
        self.assertEqual(b15[1], (T0 + 900, 115, 129.5, 114.5, 129.2, 15.0))
        self.assertEqual((g5["dropped"], g15["dropped"]), (0, 0))

    def test_missing_minute_drops_the_whole_bucket(self):
        b1 = [b for k, b in enumerate(minutes([(100, 101, 99, 100)] * 30)) if k != 7]
        b5, g5 = drv.aggregate(b1, 300)
        self.assertEqual([b[0] for b in b5], [T0 + 300 * k for k in (0, 2, 3, 4, 5)])
        self.assertEqual((g5["dropped"], g5["minutes_in_dropped"]), (1, 4))
        b15, g15 = drv.aggregate(b1, 900)
        self.assertEqual([b[0] for b in b15], [T0 + 900])
        self.assertEqual(g15["dropped"], 1)

    def test_off_grid_and_duplicates_are_refused(self):
        b1 = minutes([(100, 101, 99, 100)] * 5)
        with self.assertRaises(ValueError):
            drv.aggregate(b1[:2] + [(b1[2][0] + 1,) + b1[2][1:]], 300)
        with self.assertRaises(ValueError):
            drv.aggregate(b1[:3] + [b1[2]], 300)


class KnownTs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b1 = drv.synthetic_1m(5, 3)
        cls.b5, _ = drv.aggregate(cls.b1, 300)
        cls.p = ef.params(bar_seconds=300)
        cls.ev = ef.detect(cls.b5, cls.p)

    def test_known_ts_is_the_end_of_the_5m_bucket(self):
        self.assertGreater(len(self.ev), 200)
        for e in self.ev:
            self.assertEqual(e["known_ts"], self.b5[e["known_i"]][0] + 300)
            self.assertEqual(e["known_ts"] % 300, 0)
        setups, _ = ef.build_setups(self.ev, self.b5, self.p)
        outs = [ef.setup_outcome(s, self.b5, self.p) for s in setups]
        self.assertEqual(drv.known_ts_violations(self.ev, setups, outs, self.b5, 300), [])

    def test_changing_minutes_after_a_bucket_changes_nothing_known_by_it(self):
        k = 400
        cut = self.b5[k][0] + 300                              # end of bucket k
        changed = [b if b[0] < cut else (b[0], b[1], b[2] * 1.01, b[3], b[4], b[5]) for b in self.b1]
        b5x, _ = drv.aggregate(changed, 300)
        self.assertEqual(b5x[:k + 1], self.b5[:k + 1])
        ev = ef.detect(b5x, self.p)
        self.assertEqual([e for e in ev if e["known_i"] <= k], [e for e in self.ev if e["known_i"] <= k])

    def test_the_checker_flags_leaks(self):
        e = dict(self.ev[10])
        bad = [dict(e, known_ts=e["known_ts"] - 300), dict(e, i=e["known_i"] + 1)]
        got = [r[2] for r in drv.known_ts_violations(bad, [], [], self.b5, 300)]
        self.assertIn("known_ts is not the close of bar known_i", got)
        self.assertEqual(got.count("pattern after known"), 2)
        s = {"kind": "setup_long", "known_i": 50, "known_ts": self.b5[50][0] + 300, "i": 40, "ts": self.b5[40][0],
             "sweep_known_i": 41, "break_known_i": 50, "anchor_known_i": 39, "entry_mode": "mid"}
        o = {"fill_i": 50, "exit_i": 49}
        got = [r[2] for r in drv.known_ts_violations([], [s], [o], self.b5, 300)]
        self.assertEqual(got, ["chain order", "fill before known", "exit before fill"])


class AmbiguousFills(unittest.TestCase):
    def test_5m_stop_first_and_1m_replay_finds_the_target_first(self):
        flat = [(100, 100.2, 99.8, 100)] * 5
        # bucket 1 (minutes 5-9): fill at 99.5, then the target 101 at minute 7, then the stop 99 at minute 9
        b1 = minutes(flat + [(100, 100, 99.5, 99.6), (99.6, 100.4, 99.6, 100.3), (100.3, 101.1, 100.2, 100.9),
                             (100.9, 100.9, 99.9, 100.0), (100.0, 100.0, 98.9, 99.2)] + flat)
        b5, _ = drv.aggregate(b1, 300)
        s = {"dir": 1, "entry": 99.5, "stop": 99.0, "target": 101.0, "risk": 0.5, "known_i": 0, "known_ts": T0 + 300,
             "entry_mode": "mid", "atr": 1.0}
        p = ef.params(bar_seconds=300)
        o5 = ef.setup_outcome(s, b5, p)
        self.assertEqual((o5["status"], o5["fill_i"], o5["exit_i"]), ("stop", 1, 1))          # fill bar: only the stop
        o1 = drv.replay_1m(s, b1, {b[0]: i for i, b in enumerate(b1)}, 300, p)
        self.assertEqual((o1["status"], o1["fill_i"], o1["exit_i"]), ("target", 5, 7))

    def test_both_hit_bar_after_fill_is_a_stop(self):
        b5 = [(T0, 100, 100.2, 99.4, 99.6, 1), (T0 + 300, 99.6, 101.2, 98.8, 100, 1)]
        s = {"dir": 1, "entry": 99.6, "stop": 99.0, "target": 101.0, "risk": 0.6, "known_i": 0,
             "known_ts": T0 + 300, "entry_mode": "market", "atr": 1.0}
        o = ef.setup_outcome(s, b5, ef.params(bar_seconds=300))
        self.assertEqual((o["status"], o["both_hit_bars"]), ("stop", 1))


class Null(unittest.TestCase):
    def test_null_is_seed_83_and_cannot_be_redrawn(self):
        self.assertNotIn("seed", inspect.signature(drv.null_reference).parameters)
        got = drv.null_reference(resolutions=(300,), instruments=1, days=2)["5m"]
        ref = ef.null_run(seed=83, instruments=1, days=2)
        self.assertEqual(got["seed"], 83)
        self.assertEqual((got["bars"], got["pooled_mean_gross_r"]), (ref["bars"], ref["pooled_mean_gross_r"]))
        self.assertEqual(drv.NULL_SEED, 83)


class Refusals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path, self.man = drv.write_fixture(self.tmp.name, "synthetic_ok.json", {"SYN1": drv.synthetic_1m(1, 1)},
                                                "synthetic_1m", 1, roots=[self.tmp.name])

    def refused_unopened(self, path, manifest, roots=None):
        patches = no_fs()
        for p in patches:
            p.start()
        try:
            with self.assertRaises(drv.DataSourceRefused):
                drv.load_fixture(path, manifest, roots)
        finally:
            for p in reversed(patches):
                p.stop()

    def test_production_cache_path_is_refused_without_being_opened(self):
        name = "synthetic_x.json"
        man = dict(self.man, fixture=name)
        for path in ("/home/anton/ecommerence/copybot/data/" + name,
                     "/home/anton/ecommerence/copybot/data/lab/market/klines_1m/" + name,
                     os.path.join("data", "lab", "market", name),
                     "/home/anton/ecommerence/copybot/data/lab/market/klines_1m/BTCUSDT-1m-2020-03.zip"):
            self.refused_unopened(path, man, roots=["/"])

    def test_non_synthetic_or_missing_manifest_is_refused_before_any_file(self):
        for man in (None, {}, dict(self.man, source="binance"), dict(self.man, source="Synthetic"),
                    dict(self.man, extra=1), dict(self.man, sha256="x"), dict(self.man, schema="other")):
            self.refused_unopened(self.path, man, roots=[self.tmp.name])

    def test_outside_roots_and_wrong_names_are_refused_unopened(self):
        self.refused_unopened(self.path, self.man, roots=[os.path.join(self.tmp.name, "elsewhere")])
        self.refused_unopened("/etc/synthetic_ok.json", self.man)
        self.refused_unopened(os.path.join(self.tmp.name, "prices.json"), dict(self.man, fixture="prices.json"),
                              roots=[self.tmp.name])

    def test_a_symlink_out_of_the_root_is_refused(self):
        inside = os.path.join(self.tmp.name, "in")
        os.mkdir(inside)
        link = os.path.join(inside, "synthetic_ok.json")
        os.symlink(self.path, link)
        with self.assertRaises(drv.DataSourceRefused):
            drv.load_fixture(link, self.man, roots=[inside])

    def test_content_must_match_the_manifest(self):
        bars, prov = drv.load_fixture(self.path, self.man, roots=[self.tmp.name])
        self.assertEqual((sorted(bars), prov["source"]), (["SYN1"], "synthetic"))
        with self.assertRaises(drv.DataSourceRefused):
            drv.load_fixture(self.path, dict(self.man, sha256="0" * 64), roots=[self.tmp.name])
        with self.assertRaises(drv.DataSourceRefused):
            drv.load_fixture(self.path, dict(self.man, seed=2), roots=[self.tmp.name])

    def test_real_looking_instruments_and_provenance_are_refused(self):
        with self.assertRaises(drv.DataSourceRefused):
            drv.write_fixture(self.tmp.name, "synthetic_b.json", {"BTCUSDT": []}, "g", 1, roots=[self.tmp.name])
        with self.assertRaises(drv.DataSourceRefused):
            drv.run_bars({"SYN1": drv.synthetic_1m(1, 1)}, {"source": "explore0"})
        with self.assertRaises(drv.DataSourceRefused):
            drv.run_bars({"ETHUSDT": drv.synthetic_1m(1, 1)}, {"source": "synthetic"})


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        b2 = [b for k, b in enumerate(drv.synthetic_1m(22, 2)) if k not in (100, 101, 2000)]
        cls.path, cls.man = drv.write_fixture(cls.tmp.name, "synthetic_e2e.json",
                                              {"SYN1": drv.synthetic_1m(21, 2), "SYN2": b2}, "synthetic_1m", 21,
                                              roots=[cls.tmp.name])
        kw = {"roots": [cls.tmp.name], "lookahead_slices": 1, "lookahead_bars": 300, "n_checks": 5}
        cls.out = drv.run_fixture(cls.path, cls.man, **kw)
        cls.again = drv.run_fixture(cls.path, cls.man, **kw)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_provenance_and_reproducibility(self):
        pv = self.out["provenance"]
        self.assertEqual((pv["source"], pv["engine"]["commit"], pv["engine"]["sha256"]),
                         ("synthetic", "f686c9a", drv.ENGINE_SHA256))
        self.assertEqual(pv["input"]["sha256"], self.man["sha256"])
        self.assertEqual(self.out["result_sha256"], self.again["result_sha256"])
        self.assertEqual(self.out, self.again)
        self.assertIn("SYNTETISK", drv.summary_markdown(self.out))

    def test_every_resolution_ran_clean_with_gaps_counted(self):
        self.assertEqual(sorted(self.out["resolutions"]), ["15m", "1m", "5m"])
        for r, res in self.out["resolutions"].items():
            self.assertEqual(res["P3"]["violations"], 0, r)
            self.assertTrue(res["P3"]["lookahead_ok"], r)
            self.assertEqual(len(res["R"]), 13)
            self.assertEqual(len(res["events_secondary"]), 92)
            self.assertEqual(res["multiple_testing"]["n_used"], 315)
            self.assertNotEqual(res["multiple_testing"]["status"], ve.PASS)
        self.assertEqual(self.out["resolutions"]["5m"]["gaps"]["SYN2"]["dropped"], 2)
        self.assertEqual(self.out["resolutions"]["15m"]["gaps"]["SYN2"]["dropped"], 2)
        self.assertEqual(self.out["resolutions"]["5m"]["gaps"]["SYN1"]["dropped"], 0)
        self.assertGreater(self.out["resolutions"]["5m"]["P2"]["setups_per_instrument_day"]["default"], 0)
        self.assertTrue(self.out["resolutions"]["5m"]["P5"]["default"]["replay_1m"])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
