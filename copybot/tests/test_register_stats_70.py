"""Director order 70 P1: optional register statistics, DSR and PBO that refuse to guess. Synthetic data only; the one
real file read is the tracked factory register (research/data/factory/), for byte and hash identity, no rows printed."""
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from lab.engine import backtest, pbo as engine_pbo  # noqa: E402
from research.tools import factory as fa  # noqa: E402
from research.tools import register_stats as rs  # noqa: E402
from research.tools.video_triage import luck_bar  # noqa: E402

FACTORY_DIR = os.path.join(HERE, "research", "data", "factory")
NOTE = os.path.join(HERE, "research", "desk", "DSR_PBO_REGISTER_70.md")
PROV = {"origin": "RUN_OUTPUT", "artifact": "runs/x.json", "sha256": "ab" * 32, "code_commit": "c0f2b30"}
EVIDENCE = {"artifact": "runs/variants.json", "sha256": "cd" * 32}
# Bailey & Lopez de Prado 2014, worked example: annual SR 2.5 over 1,250 days, 250 days a year
PAPER = {"sharpe": 2.5 / math.sqrt(250), "n_obs": 1250, "skew": -3, "kurtosis": 10, "sharpe_variance": 0.5 / 250}


def noise(n, t, seed):
    r = random.Random(seed)
    return [[r.gauss(0, 0.01) for _ in range(t)] for _ in range(n)]


def axis(t):
    return list(range(t))


class Schema(unittest.TestCase):
    def test_every_field_is_optional_and_absent_stays_absent(self):
        rec = rs.record("X1")
        self.assertEqual(rec, {"schema": rs.SCHEMA, "record_id": "X1"})
        rec = rs.record("X1", sharpe=None, skew=None, lineage="carry")
        self.assertEqual(rec, {"schema": rs.SCHEMA, "record_id": "X1", "lineage": "carry"})

    def test_stored_none_is_refused(self):
        self.assertTrue(rs.validate({"schema": rs.SCHEMA, "record_id": "X1", "sharpe": None}))

    def test_full_record(self):
        rec = rs.record("X1", sharpe=0.1, n_obs=3, skew=0.0, kurtosis=3.0, net_returns=[0.1, None, 0.2],
                        net_returns_index=[1, 2, 3], variant_family="f", lineage="l", variants_tested=5,
                        variants_evidence=EVIDENCE, provenance=PROV)
        self.assertEqual(rec["variants_tested"], 5)
        self.assertEqual(rec["net_returns"][1], None)          # a gap is stored as a gap

    def test_measured_value_needs_provenance(self):
        for field in ({"sharpe": 0.1}, {"n_obs": 10}, {"skew": 0.0}, {"kurtosis": 3.0}, {"variants_tested": 3},
                      {"net_returns": [0.1], "net_returns_index": [1]}):
            with self.assertRaises(rs.StatsError, msg=str(field)):
                rs.record("X1", **field)

    def test_nothing_imputed_can_be_recorded(self):
        for origin in ("IMPUTED", "ASSUMED", "BACKFILL", "", None):
            with self.assertRaises(rs.StatsError, msg=str(origin)):
                rs.record("X1", sharpe=0.1, provenance={**PROV, "origin": origin})

    def test_provenance_must_be_hashed(self):
        with self.assertRaises(rs.StatsError):
            rs.record("X1", sharpe=0.1, provenance={**PROV, "sha256": "nope"})
        with self.assertRaises(rs.StatsError):
            rs.record("X1", sharpe=0.1, provenance={**PROV, "code_commit": ""})

    def test_variant_count_needs_evidence(self):
        with self.assertRaises(rs.StatsError):
            rs.record("X1", variants_tested=5, provenance=PROV)

    def test_unknown_field_is_refused(self):
        with self.assertRaises(rs.StatsError):
            rs.record("X1", imputed_sharpe=1.0)

    def test_excess_kurtosis_is_refused(self):
        with self.assertRaises(rs.StatsError):
            rs.record("X1", skew=0.0, kurtosis=0.0, provenance=PROV)

    def test_bad_values_are_refused(self):
        for f in ({"sharpe": float("nan")}, {"sharpe": float("inf")}, {"sharpe": True}, {"n_obs": 1}, {"n_obs": 2.5},
                  {"variants_tested": 0, "variants_evidence": EVIDENCE}):
            with self.assertRaises(rs.StatsError, msg=str(f)):
                rs.record("X1", provenance=PROV, **f)

    def test_series_needs_its_axis_and_matching_lengths(self):
        for f in ({"net_returns": [0.1, 0.2]}, {"net_returns_index": [1, 2]},
                  {"net_returns": [0.1], "net_returns_index": [1, 2]},
                  {"net_returns": [0.1, 0.2], "net_returns_index": [2, 1]},
                  {"net_returns": [0.1, float("nan")], "net_returns_index": [1, 2]},
                  {"net_returns": [0.1, 0.2], "net_returns_index": [1, 2], "n_obs": 3}):
            with self.assertRaises(rs.StatsError, msg=str(f)):
                rs.record("X1", provenance=PROV, **f)


class Chain(unittest.TestCase):
    def _chain(self):
        chain = []
        rs.chain_append(chain, rs.record("X1", sharpe=0.1, provenance=PROV), 100)
        rs.chain_append(chain, rs.record("X2", lineage="l"), 101)
        return chain

    def test_verifies_and_links(self):
        chain = self._chain()
        self.assertTrue(rs.chain_verify(chain))
        self.assertEqual(chain[1]["prev"], chain[0]["hash"])

    def test_tampering_is_detected(self):
        chain = self._chain()
        chain[0]["record"]["sharpe"] = 9.9
        with self.assertRaises(rs.StatsError):
            rs.chain_verify(chain)

    def test_an_invalid_record_cannot_enter(self):
        with self.assertRaises(rs.StatsError):
            rs.chain_append([], {"schema": rs.SCHEMA, "record_id": "X1", "sharpe": 0.1}, 100)

    def test_a_correction_is_a_new_entry_and_the_latest_counts(self):
        chain = self._chain()
        rs.chain_append(chain, rs.record("X1", sharpe=0.2, provenance=PROV), 102)
        self.assertEqual(len(chain), 3)
        self.assertEqual(rs.attach([{"id": "X1"}], chain)[0]["stats"]["sharpe"], 0.2)


class LegacyRows(unittest.TestCase):
    ROWS = [{"id": "E1", "status": "REJECTED", "trials": 8, "alpha_spent": 0.01},
            {"id": "E2", "status": "TESTED", "trials": 1, "alpha_spent": 0.0}]

    def test_old_rows_get_nothing_invented(self):
        for view in rs.attach(self.ROWS):
            self.assertEqual(view["status"], rs.MISSING_INPUT)
            self.assertIsNone(view["stats"])

    def test_old_rows_are_not_changed(self):
        before = json.dumps(self.ROWS, sort_keys=True)
        chain = []
        rs.chain_append(chain, rs.record("E1", sharpe=0.1, provenance=PROV), 100)
        views = rs.attach(self.ROWS, chain)
        self.assertEqual(json.dumps(self.ROWS, sort_keys=True), before)
        self.assertEqual(views[0]["status"], rs.OK)
        self.assertEqual(views[1]["status"], rs.MISSING_INPUT)
        self.assertEqual(views[0]["register_row_sha"], fa.sha(self.ROWS[0]))

    def test_a_view_does_not_expose_the_chain(self):
        chain = []
        rs.chain_append(chain, rs.record("E1", sharpe=0.1, provenance=PROV), 100)
        rs.attach(self.ROWS, chain)[0]["stats"]["sharpe"] = 5.0
        self.assertEqual(chain[0]["record"]["sharpe"], 0.1)


class RegisterHashesUnchanged(unittest.TestCase):
    """The proof that existing rows verify byte for byte and keep their hash."""
    GOLDEN = (
        (b'{"alpha":0.0125,"hid":"H1","lineage":"lin_a","note":"golden row","prev":"' + b"0" * 64 +
         b'","seq":0,"source":"lab","ts":1700000000,"variants":3}',
         "89efc73741ec066a0a93d589006b3841eadf4b27c468aa93dceebb14a0be5bd3"),
        ('{"alpha":0.0,"hid":"H2","key":"k1","lineage":"lin_b","note":"æøå","prev":"89efc73741ec066a0a93d589006b3841ea'
         'df4b27c468aa93dceebb14a0be5bd3","seq":1,"source":"off-database study","ts":1700000100,"variants":1}'.encode(),
         "06de1ccd38129a5242fc3d33074ef5499b26957c51605ff30de91d866ad3fe10"),
    )

    def test_golden_rows_literal_bytes(self):
        """Hash of hand-written bytes, with no code from factory or this module."""
        for body, digest in self.GOLDEN:
            self.assertEqual(hashlib.sha256(body).hexdigest(), digest)

    def test_factory_still_produces_the_golden_hashes(self):
        led = fa.Ledger()
        a = led.charge("H1", "lin_a", 1700000000, 3, 0.0125, "lab", "golden row")
        b = led.charge("H2", "lin_b", 1700000100, 1, 0.0, "off-database study", "æøå", key="k1")
        for e, (body, digest) in zip((a, b), self.GOLDEN):
            self.assertEqual(e["hash"], digest)
            self.assertEqual(fa.canonical({k: v for k, v in e.items() if k != "hash"}).encode(), body)
        self.assertTrue(led.verify())

    def _register(self):
        with open(os.path.join(FACTORY_DIR, "registry.json"), "rb") as f:
            raw = f.read()
        with open(os.path.join(FACTORY_DIR, "registry.md"), encoding="utf-8") as f:
            md = f.read()
        return raw, json.loads(raw), md

    def test_real_register_digest_matches_its_pin(self):
        raw, _, md = self._register()
        pin = re.search(r"registry\.json` \(sha256 `([0-9a-f]{64})`\)", md)
        self.assertIsNotNone(pin, "registry.md names no sha256")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), pin.group(1))

    def test_real_register_reserialises_byte_for_byte(self):
        raw, rep, _ = self._register()
        self.assertEqual((json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode(), raw)

    def test_real_ledger_chain_verifies(self):
        _, rep, _ = self._register()
        led = fa.Ledger()
        led.entries = rep["ledger"]["entries"]
        self.assertTrue(led.verify())
        self.assertTrue(led.entries)

    def test_attaching_leaves_the_real_register_identical(self):
        raw, rep, _ = self._register()
        records = rep["records"]
        before = [fa.sha(r) for r in records]
        entries_before = [dict(e) for e in rep["ledger"]["entries"]]
        chain = []
        rs.chain_append(chain, rs.record(records[0]["id"], sharpe=0.1, provenance=PROV), 100)
        views = rs.attach(records, chain)
        self.assertEqual([v["register_row_sha"] for v in views], before)
        self.assertEqual([fa.sha(r) for r in records], before)
        self.assertEqual(rep["ledger"]["entries"], entries_before)
        self.assertEqual((json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode(), raw)
        with open(os.path.join(FACTORY_DIR, "registry.json"), "rb") as f:
            self.assertEqual(f.read(), raw)

    def test_no_real_record_has_statistics_in_the_register(self):
        """No row carries a Sharpe today; if a future snapshot adds one, this test is the place to re-think."""
        _, rep, _ = self._register()
        for r in rep["records"]:
            self.assertFalse({"sharpe", "skew", "kurtosis", "net_returns"} & set(r), r["id"])
        views = rs.attach(rep["records"])
        self.assertTrue(all(v["status"] == rs.MISSING_INPUT and v["stats"] is None for v in views))


class ExpectedMax(unittest.TestCase):
    def test_matches_luck_bar(self):
        for n in (2, 43, 206, 19438):
            self.assertAlmostEqual(rs.expected_max_z(n), luck_bar(n, 1.0), places=12)

    def test_three_counts(self):
        t = rs.n_table()
        self.assertEqual({k: v["N"] for k, v in t.items()}, {"lineages": 43, "attempts": 206, "variants": 19438})
        self.assertEqual(round(t["lineages"]["expected_max_z"], 2), 2.22)
        self.assertEqual(round(t["attempts"]["expected_max_z"], 2), 2.78)          # the task's stated bar
        self.assertEqual(round(t["variants"]["expected_max_z"], 2), 4.02)

    def test_exact_order_statistics(self):
        """N = 2 and 3 are closed forms (1/sqrt(pi), 3/(2 sqrt(pi))); the rest are published normal order statistics."""
        known = {2: 1 / math.sqrt(math.pi), 3: 3 / (2 * math.sqrt(math.pi)), 5: 1.16296, 10: 1.53875, 100: 2.50759,
                 1000: 3.24144}
        for n, v in known.items():
            self.assertAlmostEqual(rs.expected_max_z_exact(n), v, places=4, msg=str(n))

    def test_edge_cases(self):
        self.assertEqual(rs.expected_max_z(1), 0.0)
        self.assertEqual(rs.expected_max_z_exact(1), 0.0)
        self.assertGreaterEqual(rs.expected_max_z(1.1), 0.0)
        for bad in (0, 0.5, True, "2", float("nan")):
            with self.assertRaises(ValueError):
                rs.expected_max_z(bad)


class DSR(unittest.TestCase):
    def test_paper_example(self):
        r = rs.deflated_sharpe(n_trials=100, **PAPER)
        self.assertEqual(r["status"], rs.OK)
        self.assertAlmostEqual(r["dsr"], 0.9004, places=4)
        self.assertAlmostEqual(r["sr0"] * math.sqrt(250), 1.7894, places=3)

    def test_paper_example_with_46_trials(self):
        self.assertAlmostEqual(rs.deflated_sharpe(n_trials=46, **PAPER)["dsr"], 0.9505, places=4)

    def test_every_input_is_required(self):
        for name in ("sharpe", "n_obs", "skew", "kurtosis", "sharpe_variance"):
            r = rs.deflated_sharpe(n_trials=100, **{**PAPER, name: None})
            self.assertEqual(r["status"], rs.MISSING_INPUT, name)
            self.assertIsNone(r["dsr"])
            self.assertEqual(r["missing"], [name])
        r = rs.deflated_sharpe(**PAPER)
        self.assertEqual((r["status"], r["missing"], r["dsr"]), (rs.MISSING_INPUT, ["n_trials"], None))

    def test_no_arguments_at_all(self):
        r = rs.deflated_sharpe()
        self.assertEqual(r["status"], rs.MISSING_INPUT)
        self.assertEqual(r["missing"], ["sharpe", "n_obs", "skew", "kurtosis", "n_trials", "sharpe_variance"])

    def test_nan_counts_as_missing(self):
        r = rs.deflated_sharpe(n_trials=100, **{**PAPER, "skew": float("nan")})
        self.assertEqual((r["status"], r["missing"]), (rs.MISSING_INPUT, ["skew"]))

    def test_invalid_input_gives_no_number(self):
        for over in ({"n_obs": 1}, {"n_obs": 12.5}, {"kurtosis": 0.0}, {"sharpe_variance": 0.0}, {"sharpe": "1"},
                     {"sharpe": True}, {"sharpe": float("inf")}):
            r = rs.deflated_sharpe(n_trials=100, **{**PAPER, **over})
            self.assertEqual(r["status"], rs.INVALID_INPUT, str(over))
            self.assertIsNone(r["dsr"])
        r = rs.deflated_sharpe(n_trials=0.5, **PAPER)
        self.assertEqual(r["status"], rs.INVALID_INPUT)

    def test_one_trial_is_the_psr_and_needs_no_variance(self):
        over = {k: v for k, v in PAPER.items() if k != "sharpe_variance"}
        r = rs.deflated_sharpe(n_trials=1, **over)
        self.assertEqual(r["sr0"], 0.0)
        z = PAPER["sharpe"] * math.sqrt(1249) / math.sqrt(1 + 3 * PAPER["sharpe"] + 2.25 * PAPER["sharpe"] ** 2)
        self.assertAlmostEqual(r["dsr"], statistics.NormalDist().cdf(z), places=12)

    def test_more_trials_deflate_more(self):
        a = rs.deflated_sharpe(n_trials=43, **PAPER)["dsr"]
        b = rs.deflated_sharpe(n_trials=206, **PAPER)["dsr"]
        c = rs.deflated_sharpe(n_trials=19438, **PAPER)["dsr"]
        self.assertGreater(a, b)
        self.assertGreater(b, c)

    def test_worse_moments_deflate_more(self):
        good = rs.deflated_sharpe(n_trials=100, **{**PAPER, "skew": 0, "kurtosis": 3})["dsr"]
        self.assertGreater(good, rs.deflated_sharpe(n_trials=100, **PAPER)["dsr"])

    def test_agrees_with_the_engine_when_all_inputs_are_given(self):
        r = random.Random(4)
        trials = [r.gauss(0.02, 0.05) for _ in range(30)]
        sr, n_obs, skew, kurt = 0.2, 500, -0.4, 5.0
        ours = rs.deflated_sharpe(sr, n_obs, skew, kurt, 30, rs.trial_sharpe_variance(trials)["sharpe_variance"])
        self.assertAlmostEqual(ours["dsr"], backtest.deflated_sharpe(sr, trials, n_obs, skew, kurt), places=12)

    def test_from_record(self):
        rec = rs.record("X1", sharpe=PAPER["sharpe"], n_obs=1250, skew=-3.0, kurtosis=10.0, provenance=PROV)
        r = rs.deflated_sharpe_from_record(rec, 100, PAPER["sharpe_variance"])
        self.assertAlmostEqual(r["dsr"], 0.9004, places=4)

    def test_from_a_record_that_lacks_a_moment(self):
        rec = rs.record("X1", sharpe=0.1, n_obs=1250, provenance=PROV)
        r = rs.deflated_sharpe_from_record(rec, 100, 0.002)
        self.assertEqual((r["status"], r["missing"], r["dsr"]), (rs.MISSING_INPUT, ["skew", "kurtosis"], None))

    def test_from_no_record(self):
        r = rs.deflated_sharpe_from_record(None, 100, 0.002)
        self.assertEqual((r["status"], r["dsr"]), (rs.MISSING_INPUT, None))
        self.assertEqual(r["missing"], ["sharpe", "n_obs", "skew", "kurtosis"])

    def _null_best(self, n, t, seed):
        rows = noise(n, t, seed)
        stats = [rs.moments(x) for x in rows]
        srs = [s["sharpe"] for s in stats]
        return stats[max(range(n), key=lambda i: srs[i])], srs

    def test_null_world_single_trial_is_uniform(self):
        """No skill, N = 1: the PSR is roughly uniform, so about 5 % of runs exceed 0.95."""
        hits = 0
        for seed in range(400):
            s, _ = self._null_best(1, 250, seed)
            hits += rs.deflated_sharpe(s["sharpe"], s["n_obs"], s["skew"], s["kurtosis"], 1)["dsr"] > 0.95
        self.assertLess(abs(hits / 400 - 0.05), 0.035)

    def test_null_world_best_of_many_is_deflated(self):
        """No skill, best of 20: ignoring the search (PSR) nearly always looks significant, the DSR does not."""
        psr_hits, dsr_hits, reps = 0, 0, 120
        for seed in range(reps):
            s, srs = self._null_best(20, 250, seed)
            var = rs.trial_sharpe_variance(srs)["sharpe_variance"]
            psr_hits += rs.deflated_sharpe(s["sharpe"], s["n_obs"], s["skew"], s["kurtosis"], 1)["dsr"] > 0.95
            dsr_hits += rs.deflated_sharpe(s["sharpe"], s["n_obs"], s["skew"], s["kurtosis"], 20, var)["dsr"] > 0.95
        self.assertGreater(psr_hits / reps, 0.5)
        self.assertLessEqual(dsr_hits / reps, 0.05)

    def test_null_world_best_of_many_centres_near_half(self):
        vals = []
        for seed in range(120):
            s, srs = self._null_best(20, 250, 5000 + seed)
            var = rs.trial_sharpe_variance(srs)["sharpe_variance"]
            vals.append(rs.deflated_sharpe(s["sharpe"], s["n_obs"], s["skew"], s["kurtosis"], 20, var)["dsr"])
        self.assertLess(abs(statistics.median(vals) - 0.5), 0.15)


class Moments(unittest.TestCase):
    def test_hand_computed(self):
        r = rs.moments([1.0, 2.0, 3.0, 4.0])
        self.assertAlmostEqual(r["sharpe"], 2.5 / math.sqrt(1.25), places=12)
        self.assertEqual(r["n_obs"], 4)
        self.assertAlmostEqual(r["skew"], 0.0, places=12)
        self.assertAlmostEqual(r["kurtosis"], 1.64, places=12)

    def test_missing_and_gaps(self):
        for x in (None, [], [0.1, None, 0.2], [0.1, float("nan"), 0.2], [0.1, 0.2]):
            r = rs.moments(x)
            self.assertEqual((r["status"], r["sharpe"]), (rs.MISSING_INPUT, None), str(x))

    def test_flat_series_has_no_sharpe(self):
        self.assertEqual(rs.moments([0.1, 0.1, 0.1])["status"], rs.INVALID_INPUT)

    def test_variance_needs_every_trial(self):
        self.assertEqual(rs.trial_sharpe_variance(None)["status"], rs.MISSING_INPUT)
        self.assertEqual(rs.trial_sharpe_variance([0.1])["status"], rs.MISSING_INPUT)
        self.assertEqual(rs.trial_sharpe_variance([0.1, None])["status"], rs.MISSING_INPUT)
        self.assertAlmostEqual(rs.trial_sharpe_variance([1.0, 3.0])["sharpe_variance"], 1.0)


class PBO(unittest.TestCase):
    def test_hand_computed_overfit(self):
        """N = 2, T = 4, S = 2. A wins block 0 and loses block 1, B the opposite: the IS winner is always OOS worst."""
        a, b = [0.01, 0.03, -0.02, 0.0], [-0.01, 0.01, 0.03, 0.05]
        r = rs.pbo_cscv([a, b], axis(4), s=2)
        self.assertEqual((r["status"], r["pbo"], r["combinations"]), (rs.OK, 1.0, 2))
        self.assertAlmostEqual(r["lambda_median"], math.log(0.5), places=12)       # w = 1/3, so lambda = ln(1/2)

    def test_hand_computed_no_overfit(self):
        """A beats B in every block: the IS winner is always OOS best."""
        a, b = [0.02, 0.04, 0.01, 0.03], [-0.02, 0.0, -0.03, -0.01]
        r = rs.pbo_cscv([a, b], axis(4), s=2)
        self.assertEqual(r["pbo"], 0.0)

    def test_missing_inputs(self):
        cases = (([None, None], {}), ((noise(2, 64, 1), None), {}), ((None, axis(64)), {}))
        for args, kw in cases:
            r = rs.pbo_cscv(*args, **kw)
            self.assertEqual((r["status"], r["pbo"]), (rs.MISSING_INPUT, None), str(args)[:40])
        self.assertEqual(rs.pbo_cscv()["missing"], ["series", "time_index"])

    def test_one_configuration_is_missing_input(self):
        self.assertEqual(rs.pbo_cscv(noise(1, 64, 1), axis(64), s=8)["status"], rs.MISSING_INPUT)

    def test_a_gap_is_missing_input_and_not_filled(self):
        rows = noise(3, 64, 1)
        rows[1][7] = None
        r = rs.pbo_cscv(rows, axis(64), s=8)
        self.assertEqual((r["status"], r["missing"], r["pbo"]), (rs.MISSING_INPUT, ["series[1][7]"], None))
        rows[1][7] = float("nan")
        self.assertEqual(rs.pbo_cscv(rows, axis(64), s=8)["status"], rs.MISSING_INPUT)

    def test_unaligned_series_are_missing_input(self):
        rows = noise(3, 64, 1)
        rows[2] = rows[2][:-1]
        r = rs.pbo_cscv(rows, axis(64), s=8)
        self.assertEqual((r["status"], r["missing"]), (rs.MISSING_INPUT, ["series[2]"]))

    def test_too_few_periods_is_missing_input(self):
        r = rs.pbo_cscv(noise(3, 20, 1), axis(20), s=16)
        self.assertEqual((r["status"], r["pbo"]), (rs.MISSING_INPUT, None))

    def test_invalid_inputs(self):
        self.assertEqual(rs.pbo_cscv(noise(3, 64, 1), axis(64), s=7)["status"], rs.INVALID_INPUT)
        self.assertEqual(rs.pbo_cscv(noise(3, 64, 1), axis(64)[::-1], s=8)["status"], rs.INVALID_INPUT)
        rows = noise(3, 64, 1)
        rows[0][0] = float("inf")
        self.assertEqual(rs.pbo_cscv(rows, axis(64), s=8)["status"], rs.INVALID_INPUT)

    def test_equals_the_engine(self):
        rows = noise(6, 96, 3)
        ours = rs.pbo_cscv(rows, axis(96), s=8)
        self.assertEqual(ours["pbo"], engine_pbo.cscv(rows, s=8)["pbo"])

    def _null_mean(self, n, t, s, seeds, base=0):
        return statistics.fmean(rs.pbo_cscv(noise(n, t, base + i), axis(t), s=s)["pbo"] for i in range(seeds))

    def test_null_world_even_n_is_one_half(self):
        """No skill: the IS winner's OOS rank is uniform on 1..N, so P(rank <= (N + 1) / 2) = 1/2 for even N.
        A seed's PBO has sd of about 0.24 (measured), so 150 seeds give se 0.02; the tolerance is about 3.5 se."""
        self.assertLess(abs(self._null_mean(10, 240, 8, 150) - 0.5), 0.07)

    def test_null_world_odd_n_counts_the_median(self):
        """With N = 3 the median rank has lambda = 0 and counts, so the null PBO is 2/3, not 1/2. Sd per seed about 0.28."""
        self.assertLess(abs(self._null_mean(3, 160, 8, 150, base=1000) - 2 / 3), 0.08)

    def test_real_skill_gives_a_low_pbo(self):
        rows = noise(10, 240, 9)
        rows[4] = [v + 0.01 for v in rows[4]]
        self.assertLess(rs.pbo_cscv(rows, axis(240), s=8)["pbo"], 0.1)

    def test_from_records(self):
        rows = noise(4, 64, 2)
        recs = [rs.record(f"V{i}", net_returns=x, net_returns_index=axis(64), provenance=PROV)
                for i, x in enumerate(rows)]
        self.assertEqual(rs.pbo_from_records(recs, s=8)["pbo"], rs.pbo_cscv(rows, axis(64), s=8)["pbo"])

    def test_from_records_without_a_series(self):
        recs = [rs.record("V0", net_returns=noise(1, 64, 1)[0], net_returns_index=axis(64), provenance=PROV),
                rs.record("V1", lineage="l")]
        r = rs.pbo_from_records(recs, s=8)
        self.assertEqual((r["status"], r["missing"], r["pbo"]), (rs.MISSING_INPUT, ["V1.net_returns"], None))

    def test_from_records_on_different_axes(self):
        x = noise(1, 64, 1)[0]
        recs = [rs.record("V0", net_returns=x, net_returns_index=axis(64), provenance=PROV),
                rs.record("V1", net_returns=x, net_returns_index=[i + 1 for i in axis(64)], provenance=PROV)]
        r = rs.pbo_from_records(recs, s=8)
        self.assertEqual((r["status"], r["missing"], r["pbo"]), (rs.MISSING_INPUT, ["V1.net_returns_index"], None))

    def test_from_no_records(self):
        self.assertEqual(rs.pbo_from_records([])["status"], rs.MISSING_INPUT)


class EffectiveN(unittest.TestCase):
    def test_block_rule_limits(self):
        self.assertEqual(rs.block_effective_n([(100, 0.0), (50, 0.0)])["n_eff"], 150.0)
        self.assertEqual(rs.block_effective_n([(100, 1.0), (50, 1.0)])["n_eff"], 2.0)
        self.assertAlmostEqual(rs.block_effective_n([(100, 0.9)])["n_eff"], 10.9, places=9)

    def test_a_block_of_one_is_one_trial(self):
        self.assertEqual(rs.block_effective_n([(1, 0.3)])["n_eff"], 1.0)

    def test_missing_correlation_gives_no_number(self):
        for blocks in (None, [], [(10, None)], [(None, 0.5)], [(10, 0.5), (10, float("nan"))]):
            r = rs.block_effective_n(blocks)
            self.assertEqual((r["status"], r["n_eff"]), (rs.MISSING_INPUT, None), str(blocks))

    def test_invalid_block(self):
        self.assertEqual(rs.block_effective_n([(10, 1.5)])["status"], rs.INVALID_INPUT)
        self.assertEqual(rs.block_effective_n([(0, 0.5)])["status"], rs.INVALID_INPUT)

    def test_flat_formula_limits(self):
        self.assertEqual(rs.flat_effective_n(0.0, 100), 100.0)
        self.assertEqual(rs.flat_effective_n(1.0, 100), 1.0)

    def test_synthetic_independent_world_matches_all_variants(self):
        sim = rs.synthetic_hierarchy(0.0, 0.0, reps=2000)
        self.assertLess(abs(sim["expected_max_z"] - rs.expected_max_z_exact(19438)), 0.04)

    def test_synthetic_perfect_duplicates_match_attempts_and_lineages(self):
        """rho = 1 inside an attempt: 206 independent attempts. rho = 1 inside a lineage: 43."""
        self.assertLess(abs(rs.synthetic_hierarchy(1.0, 0.0, reps=2000)["expected_max_z"] -
                            rs.expected_max_z_exact(206)), 0.04)
        self.assertLess(abs(rs.synthetic_hierarchy(1.0, 1.0, reps=2000)["expected_max_z"] -
                            rs.expected_max_z_exact(43)), 0.04)

    def test_flat_correlation_misleads_in_a_clustered_world(self):
        """Variants nearly identical inside each attempt. The mean over all pairs stays near zero, so the flat formula
        keeps N near 19,438, while the block rule lands within 0.1 of the simulated maximum."""
        sim = rs.synthetic_hierarchy(0.99, 0.0, reps=2000)["expected_max_z"]
        flat = rs.expected_max_z(rs.flat_effective_n(rs.synthetic_mean_corr(0.99, 0.0), 19438))
        blocks = [(n, 0.99) for n in rs._sizes(19438, 206)]
        block = rs.expected_max_z(rs.block_effective_n(blocks)["n_eff"])
        self.assertGreater(flat - sim, 0.9)
        self.assertLess(abs(block - sim), 0.1)

    def test_synthetic_mean_corr_edges(self):
        self.assertEqual(rs.synthetic_mean_corr(0.0, 0.0), 0.0)
        self.assertLess(rs.synthetic_mean_corr(1.0, 0.0), 0.01)

    def test_rejects_bad_correlations(self):
        with self.assertRaises(ValueError):
            rs.synthetic_hierarchy(0.3, 0.5, reps=1)


class NoSideEffects(unittest.TestCase):
    def test_module_writes_no_file_and_names_no_data_source(self):
        with open(rs.__file__, encoding="utf-8") as f:
            src = f.read()
        for bad in ("open(", "urllib", "requests", "socket", "sqlite3", "subprocess"):
            self.assertNotIn(bad, src, bad)


class Note(unittest.TestCase):
    def test_note_carries_the_computed_bars(self):
        with open(NOTE, encoding="utf-8") as f:
            text = f.read()
        for row in rs.n_table().values():
            self.assertIn(f"{row['expected_max_z']:.2f}".replace(".", ","), text)
            self.assertIn(f"{row['expected_max_z_exact']:.2f}".replace(".", ","), text)
        self.assertIn("MISSING_INPUT", text)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
