"""research/tools/depth_study.py: the impact model checked by hand (descriptive tool, decides nothing)."""
import csv
import gzip
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))

import depth_study as d  # noqa: E402

LINEAR = {1: 10_000, 2: 20_000, 3: 30_000, 4: 40_000, 5: 50_000}


class Impact(unittest.TestCase):
    def test_linear_book(self):
        self.assertAlmostEqual(d.impact(5_000, LINEAR), 0.0025)       # consumes to 0.5 %, average 0.25 %
        self.assertAlmostEqual(d.impact(15_000, LINEAR), 0.0075)
        self.assertIsNone(d.impact(60_000, LINEAR))                    # larger than the 5 % depth

    def test_thin_segment_costs_more(self):
        self.assertGreater(d.impact(15_000, {**LINEAR, 2: 12_000}), d.impact(15_000, LINEAR))

    def test_only_the_train_window_is_read(self):
        cols = ["hour_ts", "available_ts", "snapshots"] + [f"{k}_usd_{s}{p}" for k in ("mean", "min")
                                                            for s in "-+" for p in range(1, 6)]
        with tempfile.TemporaryDirectory() as tmp:
            for month in ("2023-03", "2023-10"):                       # train, validation
                with gzip.open(os.path.join(tmp, f"BNBUSDT-{month}.csv.gz"), "wt", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(cols)
                    w.writerow([0, 3600, 1] + [LINEAR[p] for _k in "ab" for _s in "-+" for p in range(1, 6)])
            res = d.study(tmp)
        self.assertEqual(res[("BNBUSDT", "mean", 5_000)]["hours"], 2)  # one hour x two sides, March only


if __name__ == "__main__":
    unittest.main()
