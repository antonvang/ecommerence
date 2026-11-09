"""Direktoerordre 70 P2: EX1's regler og styrke i ren syntetik. UDKAST, IKKE LAAST. K3-data aabnes ikke."""
import ast
import datetime as dt
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from research.desk.ex1 import ex1_design_check as ex  # noqa: E402

MOD = os.path.join(ROOT, "research", "desk", "ex1", "ex1_design_check.py")


def week(fri_post=-0.003, book=0.0001, ctrl_post=0.0, placebo_post=0.0003, r_pre=0.002):
    """En uge hvor r_pre > 0 og fredagens r_post < 0 er en rekyl (y > 0)."""
    return {"fri": {"r_pre": r_pre, "r_post": fri_post, "book_rt": book, "book_age_h": 0},
            "controls": [{"r_pre": 0.002, "r_post": ctrl_post} for _ in range(4)],
            "placebo": {"r_pre": 0.002, "r_post": placebo_post}}


def noisy_weeks(n, mean_gross, seed, ctrl_mean=0.0, sd=0.0035):
    """Syntetiske uger med normalfordelte afkast (r_pre > 0, saa y = -r_post)."""
    rng = random.Random(seed)
    return [{"fri": {"r_pre": 0.001, "r_post": -rng.gauss(mean_gross, sd), "book_rt": 0.0001, "book_age_h": 1},
             "controls": [{"r_pre": 0.001, "r_post": -rng.gauss(ctrl_mean, sd)} for _ in range(4)],
             "placebo": {"r_pre": 0.001, "r_post": -rng.gauss(0.0, sd)}} for _ in range(n)]


class Definitions(unittest.TestCase):
    def test_returns_use_the_right_minutes(self):
        m = {-31: 100.0, -1: 101.0, 1: 102.0, 31: 100.0}
        pre, post = ex.returns_from_marks(m)
        self.assertAlmostEqual(pre, math.log(101 / 100))
        self.assertAlmostEqual(post, math.log(100 / 102))

    def test_missing_minutes_give_none(self):
        self.assertEqual(ex.returns_from_marks({-1: 100.0, 1: 100.0}), (None, None))
        self.assertEqual(ex.returns_from_marks({-31: 0.0, -1: 100.0, 1: 100.0, 31: 100.0})[0], None)

    def test_gross_is_a_reversal_and_zero_pre_is_excluded(self):
        self.assertAlmostEqual(ex.y_gross(0.01, -0.005), 0.005)
        self.assertAlmostEqual(ex.y_gross(-0.01, -0.005), -0.005)
        self.assertIsNone(ex.y_gross(0.0, 0.01))
        self.assertIsNone(ex.y_gross(None, 0.01))

    def test_cost_uses_two_takers_plus_book_and_a_24_hour_limit(self):
        self.assertAlmostEqual(ex.cost(0.0001, 0), 0.0011)
        self.assertAlmostEqual(ex.cost(0.0001, 24), 0.0011)
        self.assertIsNone(ex.cost(0.0001, 24.01))
        self.assertIsNone(ex.cost(None, 1))
        self.assertIsNone(ex.cost(-0.1, 1))

    def test_week_without_valid_friday_is_dropped_and_did_needs_a_control(self):
        self.assertIsNone(ex.week_row(week(book=None)))
        self.assertIsNone(ex.week_row({**week(), "fri": {"r_pre": 0.0, "r_post": 0.1, "book_rt": 0.0, "book_age_h": 0}}))
        w = week(fri_post=-0.003)
        w["controls"] = []
        self.assertIsNone(ex.week_row(w)[2])
        g, net, delta, placebo = ex.week_row(week(fri_post=-0.003, ctrl_post=0.001))
        self.assertAlmostEqual(g, 0.003)
        self.assertAlmostEqual(net, 0.003 - 0.0011)
        self.assertAlmostEqual(delta, 0.003 - (-0.001))
        self.assertAlmostEqual(placebo, -0.0003)


class DecisionTree(unittest.TestCase):
    def test_source_end_and_untestable(self):
        self.assertEqual(ex.evaluate(noisy_weeks(60, 0.01, 1), source_ended=True)["verdict"], ex.INVALID)
        self.assertEqual(ex.evaluate(noisy_weeks(39, 0.01, 1), deadline_reached=True)["verdict"], ex.UNTESTABLE)
        self.assertEqual(ex.evaluate(noisy_weeks(40, 0.01, 1), deadline_reached=True)["verdict"], ex.CONTINUE)

    def test_futility_stops_at_26_and_only_on_gross(self):
        bad = noisy_weeks(26, -0.002, 2)
        self.assertEqual(ex.evaluate(bad)["verdict"], ex.STOPPED_FUTILE)
        self.assertEqual(ex.evaluate(noisy_weeks(26, 0.02, 2))["verdict"], ex.CONTINUE)
        self.assertEqual(ex.evaluate(noisy_weeks(25, -0.002, 2))["verdict"], ex.CONTINUE)

    def test_final_verdicts(self):
        self.assertEqual(ex.evaluate(noisy_weeks(52, 0.006, 3))["verdict"], ex.PASS)
        self.assertEqual(ex.evaluate(noisy_weeks(52, -0.0005, 4, sd=0.0005))["verdict"], ex.STOPPED_FUTILE)
        self.assertEqual(ex.evaluate(noisy_weeks(52, 0.0009, 5, sd=0.0004))["verdict"], ex.FALSIFIED)
        self.assertEqual(ex.evaluate(noisy_weeks(52, 0.006, 6, ctrl_mean=0.006))["verdict"], ex.PASS_NOT_EXPIRY)

    def test_final_decision_gaps_are_explicit(self):
        net, gross = [0.01, 0.012] * 26, [0.011, 0.013] * 26
        delta = [0.01, 0.012] * 26
        bad_placebo = [0.01, 0.012] * 26
        self.assertEqual(ex.final_decision(net, gross, delta, bad_placebo), (ex.INCONCLUSIVE, "PLACEBO_FAILED"))
        self.assertEqual(ex.final_decision(net, gross, delta, []), (ex.INCONCLUSIVE, "PLACEBO_UNAVAILABLE"))
        self.assertEqual(ex.final_decision(net, gross, [], [0.0, 0.001] * 26)[0], ex.PASS_NOT_EXPIRY)
        self.assertEqual(ex.final_decision([-0.001, -0.002] * 26, gross, delta, [])[0], ex.FALSIFIED)

    def test_decisions_use_only_the_first_52_valid_fridays(self):
        wk = noisy_weeks(52, 0.006, 7) + noisy_weeks(40, -0.02, 8)
        self.assertEqual(ex.evaluate(wk)["verdict"], ex.evaluate(wk[:52])["verdict"])


class DesignControl(unittest.TestCase):
    def test_placebo_gate_costs_about_five_points_of_power(self):
        sim = ex.sim_verdicts(0.0026, 0.0, reps=1200)
        self.assertTrue(0.66 <= sim.get(ex.PASS, 0) <= 0.82, sim)

    def test_size_under_nulls(self):
        self.assertLessEqual(ex.sim_verdicts(0.0, 0.0, reps=1500).get(ex.PASS, 0), 0.01)
        self.assertLessEqual(ex.sim_verdicts(0.0011, 0.0, reps=1500).get(ex.PASS, 0), 0.025)

    def test_daily_0800_effect_is_not_called_an_expiry_effect(self):
        sim = ex.sim_verdicts(0.0026, 0.0026, reps=1200)
        self.assertLessEqual(sim.get(ex.PASS, 0), 0.08)
        self.assertGreater(sim.get(ex.PASS_NOT_EXPIRY, 0), 0.6)

    def test_futility_rarely_kills_a_real_effect_but_often_a_small_one(self):
        self.assertLess(ex.false_stop_probability(0.0026), 0.002)
        self.assertAlmostEqual(ex.false_stop_probability(0.0), 0.5, delta=0.02)
        self.assertTrue(0.18 <= ex.false_stop_probability(0.0005) <= 0.30)

    def test_futility_look_does_not_raise_the_false_positive_rate(self):
        out = ex.sim_futility_then_final(0.0011, reps=2000)
        self.assertLessEqual(out["net_p_ok"], 0.0125 + 0.01)

    def test_simulation_is_deterministic(self):
        self.assertEqual(ex.sim_verdicts(0.001, 0.0, reps=200), ex.sim_verdicts(0.001, 0.0, reps=200))


class Calendar(unittest.TestCase):
    def test_first_friday(self):
        self.assertEqual(ex.first_friday_on_or_after(dt.date(2026, 11, 16)), dt.date(2026, 11, 20))
        self.assertEqual(ex.first_friday_on_or_after(dt.date(2026, 11, 20)), dt.date(2026, 11, 20))
        self.assertEqual(dt.date(2026, 12, 4).weekday(), 4)

    def test_design_note_dates_hold(self):
        self.assertEqual(ex.timeline(dt.date(2026, 11, 20)), (dt.date(2027, 5, 14), dt.date(2027, 11, 12)))
        self.assertEqual(ex.timeline(dt.date(2026, 12, 4)), (dt.date(2027, 5, 28), dt.date(2027, 11, 26)))

    def test_without_k3_only_the_new_data_line_remains(self):
        r = ex.route_without_k3()
        self.assertEqual((r["first_friday"], r["final"]), (dt.date(2026, 12, 4), dt.date(2027, 11, 26)))
        self.assertIn("ejer-ja", r["route"])
        self.assertGreaterEqual(r["fridays_until_deadline"], ex.FINAL_N)


class Boundaries(unittest.TestCase):
    def test_module_reads_no_files_and_imports_no_data_access(self):
        with open(MOD, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module)
            self.assertFalse(isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open", "no open() here")
        self.assertLessEqual(names, {"__future__", "datetime", "json", "math", "os", "random", "sys",
                                     "research.desk.lq1.lq1_evaluator"})

    def test_folder_has_only_code_and_a_note(self):
        here = os.path.dirname(MOD)
        names = {f for f in os.listdir(here) if f != "__pycache__"}
        self.assertEqual(names, {"__init__.py", "ex1_design_check.py", "EX1_DESIGN_CHECK.md"})


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
