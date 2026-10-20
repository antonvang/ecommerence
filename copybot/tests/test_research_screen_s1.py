"""research/tools/screen_s1.py on synthetic data: a planted effect is found, noise is not, nothing outside explore0."""
import csv
import io
import json
import math
import os
import random
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))

import screen_s1 as s  # noqa: E402

UTC = timezone.utc


def market(tmp, effect, seed=3, outside=False, lag=(6, 11)):
    rng = random.Random(seed)
    os.makedirs(os.path.join(tmp, "funding"))
    os.makedirs(os.path.join(tmp, "ingest", "pageviews"))
    day0, day1 = datetime(2020, 1, 1, tzinfo=UTC), datetime(2022, 2, 1, tzinfo=UTC)
    for sym, art in s.PAIRS[:4]:
        logv, views, d = math.log(1000), {}, day0
        while d < day1:
            logv = 0.9 * logv + 0.1 * math.log(1000) + rng.gauss(0, 0.3)
            views[d.strftime("%Y-%m-%d")] = max(1, int(math.exp(logv)))
            d += timedelta(days=1)
        rows = [{"date": k, "views": v, "available_ts": 0} for k, v in sorted(views.items())]
        for a in (art, s.MARKET_WIDE):
            with open(os.path.join(tmp, "ingest", "pageviews", f"{a}.json"), "w") as f:
                json.dump({"rows": rows}, f)
        by_month, t = {}, day0
        while t < day1:
            # the hypothesised mechanism: funding follows attention with a lag of about a week (days 6-10 back)
            past = [views[(t - timedelta(days=k)).strftime("%Y-%m-%d")] for k in range(*lag)
                    if (t - timedelta(days=k)) >= day0]
            base = [views[(t - timedelta(days=k)).strftime("%Y-%m-%d")] for k in range(lag[1], lag[1] + 14)
                    if (t - timedelta(days=k)) >= day0]
            att = math.log(sum(past) / len(past)) - math.log(sum(base) / len(base)) if past and base else 0
            rate = 0.0001 + effect * att + rng.gauss(0, 0.0001)
            if outside and t >= datetime(2022, 1, 1, tzinfo=UTC):
                rate = 1.0                                       # poison: must never be read
            by_month.setdefault(t.strftime("%Y-%m"), []).append((int(t.timestamp() * 1000), rate))
            t += timedelta(hours=8)
        for mo, rs in by_month.items():
            b = io.StringIO()
            w = csv.writer(b)
            w.writerow(["calc_time", "funding_interval_hours", "last_funding_rate"])
            for ts, r in rs:
                w.writerow([ts, 8, f"{r:.8f}"])
            with zipfile.ZipFile(os.path.join(tmp, "funding", f"{sym}-fundingRate-{mo}.zip"), "w") as z:
                z.writestr("x.csv", b.getvalue())
    return tmp


class Screen(unittest.TestCase):
    def run_on(self, effect, outside=False):
        with tempfile.TemporaryDirectory() as tmp:
            rows, weeks = s.build(market(tmp, effect, outside=outside))
            rho = s.rho_of(rows)
            return rows, weeks, rho, s.bootstrap(rows, len(weeks)), s.placebo(rows, len(weeks), rho)

    def test_planted_effect_is_found(self):
        rows, weeks, rho, pb, pp = self.run_on(0.0005)
        self.assertGreater(rho, 0.2)
        self.assertLess(pb, 0.05)
        self.assertLess(pp, 0.05)

    def test_an_instant_reaction_is_not_a_prediction(self):
        # funding that reacts at once is already in the week before t: Y = after - before falls, the screen fails
        with tempfile.TemporaryDirectory() as tmp:
            rows, weeks = s.build(market(tmp, 0.0005, lag=(1, 4)))
            rho = s.rho_of(rows)
        self.assertLessEqual(rho, 0)

    def test_noise_does_not_pass(self):
        _rows, _w, rho, pb, pp = self.run_on(0.0)
        self.assertFalse(rho > 0 and pb < 0.05 and pp < 0.05)

    def test_window_and_point_in_time(self):
        rows, weeks, *_ = self.run_on(0.0, outside=True)
        self.assertEqual((weeks[0], weeks[-1]), (s.FIRST_T, s.LAST_T))
        self.assertTrue(all(abs(y) < 0.01 for _s, y in rows.values()))          # the 2022 poison never entered
        v = {"2020-03-21": 10, "2020-03-20": 10, "2020-03-19": 10}
        v.update({(s.FIRST_T - timedelta(days=k)).strftime("%Y-%m-%d"): 5 for k in range(5, 19)})
        self.assertAlmostEqual(s.shock(v, s.FIRST_T), math.log(2))               # uses t-4..t-2 only
        v["2020-03-22"] = 10 ** 9                                                # day t-1: not yet published
        self.assertAlmostEqual(s.shock(v, s.FIRST_T), math.log(2))

    def test_spearman_ties(self):
        self.assertAlmostEqual(s.spearman([1, 2, 3, 4], [1, 2, 3, 4]), 1.0)
        self.assertAlmostEqual(s.spearman([1, 1, 2, 2], [1, 1, 2, 2]), 1.0)


if __name__ == "__main__":
    unittest.main()
