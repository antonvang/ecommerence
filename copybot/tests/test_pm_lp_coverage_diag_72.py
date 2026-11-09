"""Director order 72 P1: the diagnostic coverage tool, on synthetic data only. Gate D1 itself must stay byte-identical."""
import hashlib
import inspect
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "research", "tools")]

import pm_lp_coverage_diag as diag  # noqa: E402
from research import pm_lp  # noqa: E402

D = 20000
WIN = (D, D + 1)
FULL = 2 * 1440                     # panel of 2 markets
END = (D + 2) * 86400


def day(panel, snaps):
    return {"panel": panel, "snaps": snaps}


class Denominator(unittest.TestCase):
    def test_whole_day_without_panel_counts_in_full(self):
        r = diag.diagnose({D: day(2, FULL)}, WIN, 2, END)
        self.assertEqual(r["coverage_whole_window"], 0.5)
        self.assertEqual(r["locked_formula_for_comparison"], 1.0)      # the blind spot this tool exists to show
        self.assertEqual([x["status"] for x in r["rows"]], ["OBSERVED", "NO_PANEL"])

    def test_short_panel_counts_the_full_panel(self):
        r = diag.diagnose({D: day(1, 1440), D + 1: day(2, FULL)}, WIN, 2, END)
        self.assertEqual(r["coverage_whole_window"], 0.75)
        self.assertEqual(r["rows"][0]["status"], "SHORT_PANEL")

    def test_partial_day_counts_only_the_elapsed_part_so_far(self):
        noon = D * 86400 + 43200
        r = diag.diagnose({D: day(2, FULL // 2)}, WIN, 2, noon)
        self.assertEqual(r["coverage_elapsed"], 1.0)
        self.assertEqual(r["coverage_whole_window"], 0.25)
        self.assertEqual(r["best_case_whole_window"], 1.0)
        self.assertEqual(r["rows"][1]["status"], "FUTURE")

    def test_snaps_can_never_exceed_the_expected_count(self):
        r = diag.diagnose({D: day(2, FULL * 3), D + 1: day(2, 0)}, WIN, 2, END)
        self.assertEqual(r["coverage_whole_window"], 0.5)

    def test_no_data_at_all(self):
        r = diag.diagnose({}, WIN, 2, END)
        self.assertEqual(r["coverage_whole_window"], 0.0)
        self.assertIsNone(r["locked_formula_for_comparison"])

    def test_failed_polls_and_best_case(self):
        noon = D * 86400 + 43200
        r = diag.diagnose({D: day(2, 0)}, WIN, 2, noon, {D: {"polls": 100, "failed": 10}})
        self.assertEqual(r["poll_fail_rate"], 0.1)
        self.assertAlmostEqual(r["poll_fail_rate_best_case"], 10 / 250)


class Database(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = pm_lp.open_db(os.path.join(tmp.name, "pm_lp.db"))
        self.addCleanup(self.db.close)

    def snap(self, t, cid="a"):
        self.db.execute("INSERT INTO snaps(t, cid) VALUES(?,?)", (t, cid))

    def test_utc_day_change(self):
        for d in WIN:
            self.db.execute("INSERT INTO panel VALUES(?,?)", (d, "a"))
        self.snap((D + 1) * 86400 - 1)
        self.snap((D + 1) * 86400)
        days, _ = diag.load(self.db, WIN)
        self.assertEqual((days[D]["snaps"], days[D + 1]["snaps"]), (1, 1))

    def test_snap_outside_the_days_panel_is_not_counted(self):
        self.db.execute("INSERT INTO panel VALUES(?,?)", (D, "a"))
        self.snap(D * 86400 + 60, "b")
        days, _ = diag.load(self.db, WIN)
        self.assertEqual(days[D]["snaps"], 0)

    def test_dns_outage_is_counted_as_failed_trade_polls_only(self):
        t = D * 86400
        rows = [(t, "trades", "a", 0), (t + 60, "trades", "a", 1), (t + 120, "other", "a", 0)]
        self.db.executemany("INSERT INTO polls VALUES(?,?,?,?)", rows)
        _, polls = diag.load(self.db, WIN)
        self.assertEqual(polls[D], {"polls": 2, "failed": 1})

    def test_restart_gap_is_found_in_the_minutes(self):
        t = D * 86400
        for m in list(range(0, 10)) + list(range(50, 60)):
            self.snap(t + m * 60)
        start = D * 1440
        minutes = diag.minutes_seen(self.db, WIN)
        self.assertEqual(diag.gaps(minutes, start, start + 60, min_gap=30), [(start + 10, start + 50)])


class Gaps(unittest.TestCase):
    def test_edges(self):
        self.assertEqual(diag.gaps([], 0, 100, min_gap=30), [(0, 100)])
        self.assertEqual(diag.gaps([50], 0, 100, min_gap=30), [(0, 50), (51, 100)])
        self.assertEqual(diag.gaps(list(range(100)), 0, 100, min_gap=1), [])

    def test_short_holes_are_ignored(self):
        self.assertEqual(diag.gaps([0, 4], 0, 5, min_gap=5), [])


class LockedEvaluator(unittest.TestCase):
    def test_coverage_is_byte_identical(self):
        src = inspect.getsource(pm_lp.coverage).encode()
        self.assertEqual(hashlib.sha256(src).hexdigest(),
                         "0bb9e972037c8a5905ce02323e3a508b95285a7c1febcaca42083cbe7a537151")

    def test_the_tool_does_not_import_the_collector(self):
        with open(diag.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import pm_lp", src)
        self.assertNotIn("urllib", src)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
