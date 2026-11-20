import json
import tempfile
import unittest
from pathlib import Path

from jupiter_bot.research import verdict as V
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401


def cell(delay, cost, ret="2.5", random_share="0.0050", shuffled_share="0.0000", round_trips=12,
         missing_pct="0.000000", coverage="99.000000", label="development", status="OK", index=0):
    record = dict(run_id="r-%d-%d-%d" % (delay, cost, index), label=label, status=status, delay_s=delay,
                  extra_cost_bps=cost, strategy="tsmom", params={"lookback_min": 240}, plan_sha256="p",
                  batch={"id": "b1"}, grid_index=index)
    if status == "OK":
        record.update(metrics=dict(return_pct=ret, round_trips=round_trips, trades=2 * round_trips,
                                   missing_quote_pct=missing_pct, candle_coverage_pct=coverage,
                                   quote_coverage_buy_pct=coverage, quote_coverage_sell_pct=coverage),
                      controls=dict(random_entries=dict(share_beating_strategy=random_share),
                                    shuffled_signals=dict(share_beating_strategy=shuffled_share)))
    else:
        record.update(error="no quotes", metrics=None, controls=None)
    return record


def grid(**overrides):
    cells = [cell(d, c, **overrides) for d in (60, 120, 300) for c in (0, 10, 25, 50)]
    return cells


class Development(unittest.TestCase):
    def test_clear_pass(self):
        self.assertEqual(V.development(grid())[0], "PASS_DEV")

    def test_losing_after_costs_fails(self):
        self.assertEqual(V.development(grid(ret="-0.1"))[0], "FAIL")

    def test_random_controls_at_bonferroni_edge(self):
        self.assertEqual(V.development(grid(random_share="0.0125"))[0], "PASS_DEV")
        self.assertEqual(V.development(grid(random_share="0.0150"))[0], "FAIL")

    def test_shuffled_control_also_counts(self):
        self.assertEqual(V.development(grid(shuffled_share="0.0200"))[0], "FAIL")

    def test_must_survive_slow_and_expensive_fills(self):
        cells = grid()
        for r in cells:
            if (r["delay_s"], r["extra_cost_bps"]) == (300, 25):
                r["metrics"]["return_pct"] = "-0.2"
        self.assertEqual(V.development(cells)[0], "FAIL")

    def test_too_few_round_trips_is_inconclusive(self):
        self.assertEqual(V.development(grid(round_trips=9))[0], "INCONCLUSIVE")

    def test_poor_data_is_inconclusive_data(self):
        self.assertEqual(V.development(grid(coverage="94.9"))[0], "INCONCLUSIVE_DATA")
        self.assertEqual(V.development([c for c in grid() if c["delay_s"] != 120])[0], "INCONCLUSIVE_DATA")

    def test_missing_quotes_fail(self):
        self.assertEqual(V.development(grid(missing_pct="5.1"))[0], "FAIL")


class Holdout(unittest.TestCase):
    def test_holdout_is_looser_on_controls_but_strict_on_return(self):
        self.assertEqual(V.holdout([cell(120, 25, random_share="0.0400", label="holdout")])[0], "PASS")
        self.assertEqual(V.holdout([cell(120, 25, random_share="0.0600", label="holdout")])[0], "FAIL")
        self.assertEqual(V.holdout([cell(120, 25, ret="0", label="holdout")])[0], "FAIL")
        self.assertEqual(V.holdout([cell(120, 25, round_trips=4, label="holdout")])[0], "INCONCLUSIVE")


class Selection(unittest.TestCase):
    def test_lowest_random_share_then_fewest_trades(self):
        def result(share, trades, verdict="PASS_DEV"):
            return dict(verdict=verdict, trades=trades, strategy="s%s%d" % (share, trades),
                        checks=[dict(check="random entries beating it <= 1.25 %", ok=True, value=share)])
        chosen = V.select([result("0.0100", 10), result("0.0050", 30), result("0.0050", 20),
                           result("0.0000", 5, verdict="FAIL")])
        self.assertEqual(chosen["strategy"], "s0.005020")
        self.assertIsNone(V.select([result("0.0", 1, verdict="FAIL")]))


class Files(unittest.TestCase):
    def test_batch_writes_one_write_once_verdict_per_grid_entry(self):
        with tempfile.TemporaryDirectory() as d:
            evals, out = Path(d) / "e", Path(d) / "v"
            evals.mkdir()
            for i, r in enumerate(grid() + grid(index=1, ret="-1")):
                (evals / ("%03d.json" % i)).write_text(json.dumps(r))
            results = V.judge_batch(evals, "b1", out, now=1.0)
            self.assertEqual([r["verdict"] for r in results], ["PASS_DEV", "FAIL"])
            self.assertEqual(len(list(out.glob("development-b1-*.json"))), 2)
            with self.assertRaises(FileExistsError):
                V.judge_batch(evals, "b1", out, now=2.0)
            with self.assertRaises(ValueError):
                V.judge_batch(evals, "nope", out)


if __name__ == "__main__":
    unittest.main()
