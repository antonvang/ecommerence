"""Direktoerordre 70 P0: LQ1's syntetiske evaluator (UDKAST, IKKE LAAST). Kun fixtures; ingen data, intet netvaerk.

LQ1 er beskrivende forskning om omkostninger, ikke en dokumenteret handelsfordel. Testene dokumenterer reglerne."""
import ast
import glob
import json
import os
import random
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from research.desk.lq1 import lq1_evaluator as ev  # noqa: E402
from research.desk.lq1 import lq1_power as pw  # noqa: E402
from research.desk.lq1 import make_fixtures as mf  # noqa: E402

LQ1_DIR = os.path.join(ROOT, "research", "desk", "lq1")
EX1_DIR = os.path.join(ROOT, "research", "desk", "ex1")
FIXTURES = os.path.join(LQ1_DIR, "fixtures")
START_I = ev.START_D * 24       # indeks for L + 7 d, naar serien starter ved L
BASE = 80                       # 8 bp i 0,1 bp
N = mf.N_HOURS


def fx(name):
    return ev.evaluate_path(os.path.join(FIXTURES, name + ".json"))


def doc(cells=None, first=mf.LOCK, as_of=mf.AS_OF, **market):
    return {"synthetic": True, "schema": "lq1-fixture/1", "world": "t", "lock_ts": mf.LOCK, "as_of_ts": as_of,
            "first_h": first, "markets": {"SYN_A": {"series": cells if cells is not None else [BASE] * N, **market}}}


def run(document):
    return ev.find_events(ev.decode_fixture(document))


def flat(**changes):
    """Fladt marked pa 8 bp med celler aendret ved indeks."""
    cells = [BASE] * N
    for i, v in changes.items():
        cells[int(i[1:])] = v
    return cells


class Worlds(unittest.TestCase):
    """Null-verden, verden med effekt og de andre domme, alle fra committede fixtures."""

    def test_null_world_where_breaks_persist_is_falsified(self):
        r = fx("world_null_persistent")
        self.assertEqual((r["status"], r["verdict"]), ("OK", ev.FALSIFIED))
        self.assertLess(r["test"]["upper95"], 5.0)

    def test_null_world_at_the_threshold_does_not_pass(self):
        r = fx("world_null_at_threshold")
        self.assertEqual(r["verdict"], ev.INCONCLUSIVE)
        self.assertAlmostEqual(r["test"]["mean"], 5.0, delta=0.5)

    def test_world_with_an_effect_passes(self):
        r = fx("world_effect")
        self.assertEqual((r["verdict"], r["reason"]), (ev.PASS, "P_BELOW_ALPHA_AND_ROBUST"))
        self.assertGreater(r["test"]["mean"], 9.0)
        self.assertTrue(r["robustness"]["ok"])

    def test_one_market_cannot_carry_a_pass(self):
        r = fx("world_one_market_dominates")
        self.assertEqual((r["verdict"], r["reason"]), (ev.INCONCLUSIVE, "ROBUSTNESS_GATE_FAILED"))
        self.assertLessEqual(r["test"]["p"], ev.ALPHA_F)
        self.assertEqual(r["robustness"]["top_markets"], ["SYN_A"])
        self.assertLessEqual(r["robustness"]["s_bar_without_top"], 5.0)

    def test_too_few_events_low_coverage_and_censoring(self):
        self.assertEqual(fx("world_too_few_events")["verdict"], ev.UNTESTABLE)
        low = fx("world_low_coverage")
        self.assertEqual(low["verdict"], ev.INVALID)
        self.assertLess(low["counts"]["coverage"], 0.90)
        cen = fx("world_censored")
        self.assertEqual(cen["verdict"], ev.INCONCLUSIVE_CENSORED)
        self.assertGreater(cen["censored_share"], 0.20)

    def test_every_result_says_it_is_descriptive(self):
        for name in ("world_effect", "world_null_persistent", "err_not_synthetic", "small_not_due"):
            self.assertIn("ikke en dokumenteret handelsfordel", fx(name)["label"])
        self.assertEqual(fx("world_effect")["mode"], "BESKRIVENDE (alfa = 0)")

    def test_full_reversion_ceiling_is_reported(self):
        d = fx("world_effect")["descriptive"]["per_market"]["SYN_A"]
        self.assertGreater(d["s_full_reversion_bp"], d["s_bar_bp"] * 0.9)
        self.assertGreater(d["reverted_share"], 0.8)


class Reproducible(unittest.TestCase):
    def test_committed_fixtures_are_exactly_what_the_generator_builds(self):
        built = mf.all_fixtures()
        on_disk = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(FIXTURES, "*.json"))}
        self.assertEqual(on_disk, set(built))
        for name, document in built.items():
            with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), mf.dump(document), name)

    def test_same_fixture_gives_the_same_bytes_and_hash(self):
        a, b = fx("world_effect"), fx("world_effect")
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(len(a["result_sha256"]), 64)

    def test_world_generator_is_seed_stable(self):
        self.assertEqual(mf.dump(mf.world("x", 1, p=1 / 100)), mf.dump(mf.world("x", 1, p=1 / 100)))
        self.assertNotEqual(mf.dump(mf.world("x", 1, p=1 / 100)), mf.dump(mf.world("x", 2, p=1 / 100)))

    def test_fixtures_are_obviously_synthetic(self):
        for name, d in mf.all_fixtures().items():
            if name in ("err_not_synthetic",):
                continue
            self.assertIs(d["synthetic"], True, name)
            self.assertTrue(all(m.startswith("SYN_") for m in d["markets"]), name)
            if "lock_ts" in d:
                self.assertGreaterEqual(d["lock_ts"], mf.LOCK, name)


class BadInput(unittest.TestCase):
    """Manglende eller forkert input giver status ERROR og ingen dom."""

    def assert_error(self, result, needle=""):
        self.assertEqual((result["status"], result["verdict"]), ("ERROR", None))
        self.assertNotIn("test", result)
        self.assertIn(needle, result["error"])

    def test_committed_error_fixtures(self):
        for name, needle in (("err_not_synthetic", "synthetic"), ("err_negative_cell", "ugyldig celle"),
                             ("err_bad_cell_type", "ugyldig celle"), ("err_lock_not_on_hour", "timeskifte"),
                             ("err_unknown_market_key", "ukendte"), ("err_missing_field", "lock_ts"),
                             ("err_offhours_out_of_range", "off_hours")):
            self.assert_error(fx(name), needle)

    def test_each_required_field_is_required(self):
        for key in ("synthetic", "schema", "world", "lock_ts", "as_of_ts", "first_h", "markets"):
            d = doc()
            del d[key]
            self.assert_error(ev.evaluate_doc(d), key)

    def test_malformed_documents(self):
        bad = [doc(as_of=mf.LOCK - 1), {**doc(), "markets": {}}, {**doc(), "schema": "lq1-fixture/9"},
               {**doc(), "extra": 1}, doc(cells=[True, 80]), doc(cells=[0, 80]), doc(delays=[[0, -1]]),
               doc(delays=[[10 ** 6, 10]]), doc(extra_scans=[[0, 10, None]]), doc(extra_scans=[[0, 10]]),
               doc(off_hours=[[5, 2]]), {**doc(), "markets": {"SYN_A": {}}}, {**doc(), "markets": {"SYN_A": 3}}]
        for d in bad:
            self.assertEqual(ev.evaluate_doc(d)["status"], "ERROR", str(list(d)))
        self.assertEqual(ev.evaluate_doc([1, 2])["status"], "ERROR")

    def test_only_files_directly_in_the_fixture_folder_can_be_read(self):
        with tempfile.TemporaryDirectory() as d:
            outside = os.path.join(d, "world_effect.json")
            with open(outside, "w", encoding="utf-8") as fh:
                fh.write(mf.dump(doc()))
            self.assert_error(ev.evaluate_path(outside), "fixtures")
            self.assert_error(ev.evaluate_path(os.path.join(FIXTURES, "nope.txt")), "fixtures")
            self.assert_error(ev.evaluate_path(os.path.join(FIXTURES, "..", "lq1_evaluator.py")), "fixtures")
            link = os.path.join(d, "link.json")
            os.symlink(outside, link)
            self.assert_error(ev.evaluate_path(link), "fixtures")

    def test_missing_file_and_invalid_json(self):
        self.assert_error(ev.evaluate_path(os.path.join(FIXTURES, "nope.json")), "kan ikke")
        with tempfile.TemporaryDirectory() as d:
            real = os.path.realpath(d)
            path = os.path.join(real, "broken.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            with mock.patch.object(ev, "FIXTURE_DIR", real):
                self.assert_error(ev.evaluate_path(path), "JSON")


class EventRules(unittest.TestCase):
    def test_saving_is_half_the_drop_in_basis_points(self):
        events, _ = run(doc(flat(i300=400, i301=120)))
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]["s"], 0.5 * (40.0 - 12.0), places=9)
        self.assertAlmostEqual(events[0]["reverted"], (400 - 120) / (400 - 80), places=9)
        self.assertAlmostEqual(events[0]["full"], 0.5 * 32.0, places=9)

    def test_break_is_at_least_three_times_baseline(self):
        self.assertEqual(len(run(doc(flat(i300=240)))[0]), 1)
        self.assertEqual(len(run(doc(flat(i300=239)))[0]), 0)

    def test_events_only_inside_the_window(self):
        before = flat(**{f"i{START_I - 1}": 900})
        at_start = flat(**{f"i{START_I}": 900})
        last = ev.END_D * 24
        after = flat(**{f"i{last}": 900})
        inside = flat(**{f"i{last - 1}": 900})
        self.assertEqual(len(run(doc(before))[0]), 0)
        self.assertEqual(len(run(doc(at_start))[0]), 1)
        self.assertEqual(len(run(doc(after))[0]), 0)
        self.assertEqual(len(run(doc(inside))[0]), 1)

    def test_baseline_needs_120_usable_hours(self):
        cells = flat(i300=400)
        for i in range(0, 50):
            cells[i] = None
        events, c = run(doc(cells))             # hul foer: baseline har 250 brugbare timer ved 300, stadig nok
        self.assertEqual(len(events), 1)
        thin = [None] * 180 + [BASE] * (N - 180)
        thin[185] = 400
        events, c = run(doc(thin))              # kun 5 brugbare timer foer haendelsen
        self.assertEqual(events, [])
        self.assertGreater(c["no_baseline_hours"], 0)

    def test_baseline_uses_nothing_before_the_lock(self):
        pre = 200
        cells = [800] * pre + [BASE] * N        # dyrt foer laasen; maa ikke trykke baseline op
        idx = pre + START_I + 10
        cells[idx] = 300
        events, _ = run(doc(cells, first=mf.LOCK - pre * 3600))
        self.assertEqual(len(events), 1)

    def test_baseline_excludes_the_hour_itself_and_off_hours(self):
        cells = flat()
        off = [[100, 148]]
        for i in range(100, 148):
            cells[i] = 5000                     # EWMA-timer er dyre; de maa ikke trykke baseline op
        cells[200] = 300
        events, _ = run(doc(cells, off_hours=off))
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(ev.find_events(ev.decode_fixture(doc(cells, off_hours=off)))[0][0]["full"], 0.5 * (30 - 8))

    def test_off_hours_and_first_hour_after_reopen_are_excluded_and_counted(self):
        cells = flat(i300=400, i302=400)
        off = [[300, 302]]                      # 300-301 lukket; 302 er foerste time efter genaabning
        events, c = run(doc(cells, off_hours=off))
        self.assertEqual(events, [])
        self.assertEqual(c["excluded_off_hours_t"], 1)
        self.assertEqual(c["excluded_first_after_reopen"], 1)

    def test_t_plus_one_in_off_hours_or_missing_is_excluded(self):
        events, c = run(doc(flat(i300=400), off_hours=[[301, 305]]))
        self.assertEqual((events, c["excluded_off_hours_t1"]), ([], 1))
        events, c = run(doc(flat(i300=400, i301=None)))
        self.assertEqual((events, c["excluded_missing_t1"]), ([], 1))
        events, c = run(doc(flat(i300=400, i301="E")))
        self.assertEqual((events, c["excluded_missing_t1"]), ([], 1))
        events, c = run(doc(flat(i300=400), delays=[[301, 601]]))
        self.assertEqual((events, c["excluded_missing_t1"]), ([], 1))
        events, c = run(doc(flat(i300=400), delays=[[301, 600]]))
        self.assertEqual(len(events), 1)

    def test_censored_rt_t_counts_but_has_no_saving(self):
        events, c = run(doc(flat(i300="T")))
        self.assertEqual((len(events), c["censored_t"], events[0]["s"]), (1, 1, None))
        self.assertEqual(ev.cluster_means(events), [])

    def test_censored_rt_t_plus_one_is_a_zero_saving(self):
        events, c = run(doc(flat(i300=400, i301="T")))
        self.assertEqual((events[0]["s"], c["censored_t1"], c["censored_t"]), (0.0, 1, 0))

    def test_six_hour_dedup_per_market(self):
        self.assertEqual(len(run(doc(flat(i300=400, i305=400)))[0]), 1)
        self.assertEqual(len(run(doc(flat(i300=400, i306=400)))[0]), 2)
        _, c = run(doc(flat(i300=400, i305=400)))
        self.assertEqual(c["deduped"], 1)

    def test_a_candidate_with_a_missing_next_hour_still_uses_the_dedup(self):
        events, c = run(doc(flat(i300=400, i301=None, i303=400)))
        self.assertEqual((events, c["excluded_missing_t1"], c["deduped"]), ([], 1, 1))

    def test_only_the_earliest_scan_of_an_hour_counts(self):
        document = doc(flat(i300=400), extra_scans=[[300, 30, 90], [300, 590, 900]])
        events, c = run(document)
        self.assertEqual(events, [])            # 9 bp ved 30 s er tidligst: intet brud
        self.assertEqual(c["duplicate_scans_dropped"], 2)
        document = doc(flat(i300=400), delays=[[300, 700]], extra_scans=[[300, 610, 400]])
        self.assertEqual(run(document)[0], [])  # tidligste er efter 10 min: ingen maaling

    def test_other_scan_errors_are_missing_not_censored(self):
        events, c = run(doc(flat(i300="E")))
        self.assertEqual((events, c["censored_t"], c["missing_hours_error_scan"]), ([], 0, 1))

    def test_coverage_counts_only_hours_outside_off_hours(self):
        cells = flat()
        for i in range(START_I, START_I + 10):
            cells[i] = None
        _, c = run(doc(cells))
        self.assertEqual(c["market_hours_total"], (ev.END_D - ev.START_D) * 24)
        self.assertEqual(c["market_hours_scanned"], c["market_hours_total"] - 10)
        off = [[START_I, START_I + 24]]
        _, c = run(doc(cells, off_hours=off))
        self.assertEqual(c["market_hours_total"], (ev.END_D - ev.START_D) * 24 - 24)

    def test_cluster_means_weight_days_not_events(self):
        day = 86400
        events = [{"market": "A", "h": day, "s": 2.0}, {"market": "B", "h": day + 3600, "s": 4.0},
                  {"market": "A", "h": 2 * day, "s": 9.0}, {"market": "A", "h": 3 * day, "s": None}]
        self.assertEqual(ev.cluster_means(events), [3.0, 9.0])
        self.assertEqual(ev.cluster_means(events, without="A"), [4.0])


class NotDue(unittest.TestCase):
    def test_before_the_deadline_only_counts_are_reported(self):
        d = doc(flat(i300=400, i301=100), as_of=mf.LOCK + ev.DEADLINE_D * 86400 - 1)
        r = ev.evaluate_doc(d)
        self.assertEqual((r["status"], r["verdict"]), ("NOT_DUE", None))
        for key in ("test", "descriptive", "robustness", "censored_share"):
            self.assertNotIn(key, r)
        self.assertEqual(r["counts"]["events"], 1)
        self.assertEqual(fx("small_not_due")["status"], "NOT_DUE")

    def test_at_the_deadline_there_is_a_verdict(self):
        r = ev.evaluate_doc(doc(flat(i300=400, i301=100), as_of=mf.LOCK + ev.DEADLINE_D * 86400))
        self.assertEqual(r["status"], "OK")


class Decision(unittest.TestCase):
    PASSING = {"upper95": 9.0, "p": 0.001, "mean": 8.0}

    def test_order_of_verdicts(self):
        cases = [((0.89, 10, 0.5, self.PASSING, True), ev.INVALID),
                 ((0.90, 29, 0.5, self.PASSING, True), ev.UNTESTABLE),
                 ((0.90, 30, 0.21, self.PASSING, True), ev.INCONCLUSIVE_CENSORED),
                 ((0.90, 30, 0.20, {"upper95": 4.9, "p": 0.9, "mean": 3.0}, True), ev.FALSIFIED),
                 ((0.90, 30, 0.20, self.PASSING, True), ev.PASS),
                 ((0.90, 30, 0.20, self.PASSING, False), ev.INCONCLUSIVE),
                 ((0.90, 30, 0.20, {"upper95": 7.0, "p": 0.05, "mean": 5.5}, True), ev.INCONCLUSIVE),
                 ((0.90, 30, 0.20, {"upper95": 5.0, "p": 0.5, "mean": 5.0}, True), ev.INCONCLUSIVE)]
        for args, want in cases:
            self.assertEqual(ev.decide(*args)[0], want, args)

    def test_pass_and_falsified_cannot_both_hold(self):
        rng = random.Random(4)
        for _ in range(3000):
            n = rng.randint(30, 91)
            mu, sd = rng.uniform(-5, 20), rng.uniform(0.5, 30)
            t = ev.one_sided_test([rng.gauss(mu, sd) for _ in range(n)])
            self.assertFalse(t["p"] <= ev.ALPHA_F and t["mean"] > 5 and t["upper95"] < 5)

    def test_t_distribution_against_table_values(self):
        self.assertAlmostEqual(ev.t_quantile(0.975, 19), 2.0930, places=3)
        self.assertAlmostEqual(ev.t_quantile(0.95, 29), 1.6991, places=3)
        self.assertAlmostEqual(ev.t_quantile(0.975, 29), 2.0452, places=3)
        self.assertAlmostEqual(ev.t_quantile(0.9975, 59), 2.915, places=2)
        self.assertAlmostEqual(ev.t_sf(0.0, 12), 0.5, places=12)
        self.assertAlmostEqual(ev.t_sf(2.0452, 29) * 2, 0.05, places=4)
        self.assertAlmostEqual(ev.t_sf(-1.6991, 29), 0.95, places=4)

    def test_known_sample(self):
        t = ev.one_sided_test([6.0, 8.0, 10.0, 12.0], mu0=5.0)
        self.assertAlmostEqual(t["mean"], 9.0)
        self.assertAlmostEqual(t["sd"], 2.581988897, places=6)
        self.assertEqual(t["df"], 3)
        self.assertAlmostEqual(t["t"], 4.0 / (2.581988897 / 2.0), places=6)

    def test_all_savings_zero_is_falsified_not_a_crash(self):
        t = ev.one_sided_test([0.0] * 40)
        self.assertEqual((t["se"], t["p"], t["upper95"]), (0.0, 1.0, 0.0))
        self.assertEqual(ev.decide(1.0, 40, 0.0, t, True)[0], ev.FALSIFIED)
        with self.assertRaises(ev.LQ1InputError):
            ev.one_sided_test([1.0])

    def test_size_and_power_of_the_decision_layer(self):
        def share(mu, reps, seed):
            rng = random.Random(seed)
            return sum(ev.decide(1.0, 60, 0.0, ev.one_sided_test([rng.gauss(mu, 10.0) for _ in range(60)]), True)[0]
                       == ev.PASS for _ in range(reps)) / reps
        self.assertLess(share(5.0, 2000, 11), 0.022)          # alfa 0,0125 ved taersklen
        self.assertGreater(share(5.0, 2000, 11), 0.004)
        self.assertTrue(0.74 <= share(9.0, 1200, 12) <= 0.86)  # 80 % ved 9 bp, sd 10, n 60

    def test_robustness_gate(self):
        day = 86400
        ev2 = [{"market": "A", "h": day, "s": 9.0}, {"market": "B", "h": day, "s": 9.0}]
        self.assertFalse(ev.robustness(ev2)["ok"])              # kun to markeder
        ok = [{"market": m, "h": day * (i + 1), "s": 9.0} for i, m in enumerate("AABBCC")]
        self.assertTrue(ev.robustness(ok)["ok"])
        tie = [{"market": "A", "h": day, "s": 1.0}, {"market": "B", "h": 2 * day, "s": 9.0},
               {"market": "C", "h": 3 * day, "s": 9.0}]
        out = ev.robustness(tie)
        self.assertEqual(out["top_markets"], ["A", "B", "C"])
        self.assertEqual(out["s_bar_without_top"], 5.0)         # uden B eller C: (1 + 9) / 2 = 5, ikke > 5
        self.assertFalse(out["ok"])
        self.assertFalse(ev.robustness([])["ok"])


class Power(unittest.TestCase):
    def test_required_clusters_and_headline_numbers(self):
        self.assertEqual(pw.required_clusters(9.0, 10.0), 60)
        self.assertEqual(pw.required_clusters(7.0, 10.0), 238)
        self.assertAlmostEqual(pw.analytic_power(9.0, 10.0, 60), 0.80, delta=0.01)
        with self.assertRaises(ValueError):
            pw.required_clusters(5.0, 10.0)

    def test_tables_match_the_design_note(self):
        t = pw.tables()
        self.assertAlmostEqual(t["mde_bp_above_threshold"]["sd=10"]["n=60"], 4.0, delta=0.05)
        self.assertAlmostEqual(t["mde_bp_above_threshold"]["sd=30"]["n=30"], 16.9, delta=0.05)
        self.assertAlmostEqual(t["mde_bp_above_threshold"]["sd=5"]["n=120"], 1.4, delta=0.05)
        self.assertFalse(t["window"]["event_day_share=0.25"]["testable"])
        self.assertTrue(t["window"]["event_day_share=0.33"]["testable"])

    def test_whole_pipeline_is_deterministic_and_sane(self):
        a = pw.pipeline_mc(reps=4)
        self.assertEqual(a, pw.pipeline_mc(reps=4))
        self.assertEqual(a["ingen_tilbagevenden"]["verdicts"], {ev.FALSIFIED: 4})
        self.assertEqual(a["S9_ens_boeger"]["verdicts"], {ev.PASS: 4})


class Boundaries(unittest.TestCase):
    """Kun stdlib, ingen database eller netvaerk, og koden kender felterne i den rigtige scanner."""

    def imports(self, path):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                out.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                out.add(node.module)
        return out

    def test_evaluator_imports_only_harmless_stdlib(self):
        self.assertLessEqual(self.imports(os.path.join(LQ1_DIR, "lq1_evaluator.py")),
                             {"__future__", "bisect", "collections", "hashlib", "json", "math", "os", "sys"})
        self.assertLessEqual(self.imports(os.path.join(LQ1_DIR, "make_fixtures.py")),
                             {"__future__", "calendar", "json", "math", "os", "random"})
        self.assertLessEqual(self.imports(os.path.join(LQ1_DIR, "lq1_power.py")),
                             {"__future__", "collections", "json", "math", "os", "sys", "research.desk",
                              "research.desk.lq1"})

    def test_no_forbidden_names_in_the_new_folders(self):
        banned = ("sqlite3", "socket", "urllib", "requests", "http.client", "lab.db", "pm_lp", "quarantine",
                  "upbit", "hlcensus", "N4_KIMCHI")
        for folder in (LQ1_DIR, EX1_DIR):
            for p in glob.glob(os.path.join(folder, "**", "*"), recursive=True):
                if os.path.isfile(p) and "__pycache__" not in p and not p.endswith(".md"):
                    with open(p, encoding="utf-8") as fh:
                        text = fh.read().lower()
                    for word in banned:
                        self.assertNotIn(word.lower(), text, f"{p}: {word}")

    def test_the_draft_is_marked_unlocked_and_descriptive(self):
        with open(os.path.join(LQ1_DIR, "LQ1_PROTOCOL_DRAFT.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("UDKAST, IKKE LÅST", text)
        self.assertIn("ikke en dokumenteret handelsfordel", text)
        for verdict in ev.VERDICTS:
            self.assertIn(verdict, text)
        self.assertNotIn("upbit", text.lower())

    def test_documented_fields_exist_in_the_scanner_source(self):
        """Tekstkontrol af koden (ingen data): de felter, udkastet bygger paa, staar stadig i `lab/moves.py`."""
        with open(os.path.join(ROOT, "lab", "moves.py"), encoding="utf-8") as fh:
            src = fh.read()
        for needle in ('DETECTOR = "abnormal_move"', '"book_rt", b.get("round_trip")', '"off_hours": off_hours(cls',
                       '"book too thin for 5 000 USD"', "SIZE_USD = 5000.0", "DEDUP_S = 6 * 3600", '"open_s": rows[-1][0]'):
            self.assertIn(needle, src)
        tree = ast.parse(src)
        watch = next(n.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "WATCH")
        self.assertEqual(len(watch.keys), 12)


if __name__ == "__main__":
    unittest.main()
