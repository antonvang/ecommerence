import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import pmcal  # noqa: E402
from research.pmcal import (BASE, DAY, HIGH, HOUR, cluster_lb, cost, entry_price, gates, n_req, payout,  # noqa: E402
                            random_side, run, select, side_for, summarize, ts)

END = ts("2025-03-20T00:00:00Z")


def mk(mid, event="E1", p_final=("1", "0"), created="2025-01-01T00:00:00Z", closed="2025-03-20 12:00:00+00",
       end="2025-03-20T00:00:00Z", vol=50_000, q="Will it happen?", outcomes=("Yes", "No")):
    return {"id": mid, "question": q, "outcomes": list(outcomes), "outcomePrices": list(p_final),
            "clobTokenIds": [f"t{mid}a", f"t{mid}b"], "createdAt": created, "closedTime": closed, "endDate": end,
            "volumeNum": vol, "event": event, "event_title": "", "event_slug": ""}


def daily(price_fn, start=END - 60 * DAY, days=61):
    return [{"t": start + i * DAY + 2, "p": price_fn(start + i * DAY)} for i in range(days)]


class Pmcal(unittest.TestCase):
    def test_timestamp_formats(self):
        self.assertEqual(ts("2024-01-01 20:32:09+00"), ts("2024-01-01T20:32:09Z"))
        self.assertEqual(ts("2025-03-20"), END)

    def test_entry_price_ignores_points_after_entry_and_needs_prior_point(self):
        te = END - 7 * DAY
        h = daily(lambda t: 0.9 if t < te else 0.1)            # pris ændres efter entry: må ikke ses
        self.assertAlmostEqual(entry_price(h, te), 0.9)
        self.assertIsNone(entry_price([{"t": te - HOUR, "p": 0.5}], te))           # intet p0
        self.assertIsNone(entry_price(daily(lambda t: 0.5, start=te - 60 * DAY, days=20), te))  # forældet

    def test_select_lowest_id_open_market_without_price_or_outcome(self):
        hist = {"t2a": daily(lambda t: 0.9), "t5a": daily(lambda t: 0.3), "t1a": daily(lambda t: 0.5)}
        early = mk(1, closed="2025-03-01 00:00:00+00")         # lukket før entry
        m, p, _ = select([mk(5), early, mk(2)], 7, 10_000, hist.get)
        self.assertEqual(m["id"], 2)
        self.assertAlmostEqual(p, 0.9)
        late = mk(2, created="2025-03-12T12:00:00Z")           # oprettet under 24 t før entry
        self.assertEqual(select([late, mk(5)], 7, 10_000, hist.get)[0]["id"], 5)
        self.assertIsNone(select([mk(2, vol=500)], 7, 10_000, hist.get)[0])
        self.assertIsNone(select([mk(2, q="Bitcoin Up or Down on March 20?")], 7, 10_000, hist.get)[0])
        self.assertIsNone(select([mk(2, outcomes=("A", "B", "C"))], 7, 10_000, hist.get)[0])

    def test_sides_costs_and_payouts(self):
        self.assertEqual(side_for(0.9, "fav"), (0, 0.9))
        self.assertEqual(side_for(0.9, "long"), (1, 0.09999999999999998))
        self.assertEqual(side_for(0.15, "fav"), (1, 0.85))
        m = mk(1)
        self.assertAlmostEqual(cost(0.9, m, BASE), 0.9 + 0.005 + 0.05 * 0.9 * 0.1)
        self.assertAlmostEqual(cost(0.9, mk(1, q="Will Bitcoin hit 100k?"), BASE), 0.9 + 0.005 + 0.07 * 0.09)
        self.assertAlmostEqual(cost(0.9, m, HIGH), 0.9 + 0.015 + 0.07 * 0.09)
        self.assertEqual(payout(mk(1, p_final=("0.5", "0.5")), 0), 0.5)
        self.assertIsNone(payout(mk(1, p_final=("0.73", "0.27")), 0))
        self.assertEqual(payout(mk(1, p_final=("0.0000001", "0.9999999")), 1), 1.0)

    def test_run_returns_and_buckets(self):
        events = {"A": [mk(1, "A", ("1", "0"))], "B": [mk(2, "B", ("0", "1"))], "C": [mk(3, "C")]}
        hist = {"t1a": daily(lambda t: 0.9), "t2a": daily(lambda t: 0.9), "t3a": daily(lambda t: 0.6)}
        rows, excl, d = run(events, "F7", hist_of=hist.get)
        self.assertEqual(len(rows), 2)
        self.assertEqual(excl["outside_bucket"], 1)            # 0.6 er ikke i [0.80, 0.95]
        c = 0.9 + 0.005 + 0.05 * 0.09
        self.assertAlmostEqual(sorted(x["r"] for x in rows)[1], (1 - c) / c)
        self.assertAlmostEqual(sorted(x["r"] for x in rows)[0], -1.0)
        self.assertEqual(d, [3, 3])
        lrows, _, _ = run(events, "L7", hist_of=hist.get)       # longshot-siden af samme kontrakter
        self.assertEqual({x["event"] for x in lrows}, {"A", "B"})
        self.assertTrue(all(abs(x["q"] - 0.1) < 1e-9 for x in lrows))

    def test_random_side_baseline_is_deterministic_and_uses_same_events(self):
        self.assertEqual(random_side("123"), random_side("123"))
        events = {str(i): [mk(i, str(i))] for i in range(1, 40)}
        hist = {f"t{i}a": daily(lambda t: 0.9) for i in range(1, 40)}
        rule = run(events, "F7", hist_of=hist.get)[0]
        base = run(events, "F7", hist_of=hist.get, baseline=True)[0]
        self.assertEqual([x["event"] for x in rule], [x["event"] for x in base])
        self.assertTrue(any(x["q"] < 0.5 for x in base))

    def test_statistics_and_gates(self):
        rows = [{"event": str(i), "end": END + (i % 10) * 7 * DAY, "week": f"W{i % 10}", "q": 0.9,
                 "y": 1.0, "c": 0.91, "r": 0.01 if i % 7 else -0.02, "crypto": False} for i in range(300)]
        s = summarize(rows)
        self.assertEqual(s["events"], 300)
        self.assertLess(s["lb_99_5"], s["mean"])
        self.assertEqual(cluster_lb(rows), cluster_lb(rows))   # fast seed
        self.assertIsNone(n_req(-0.01, 0.1))
        self.assertEqual(n_req(0.01, 0.3), 13444)              # ceil(((3.0233+0.8416)*0.3/0.01)^2)
        g = gates(s, {"mean": -0.01}, {"total_net": 1.0}, 200, (100, 95))
        self.assertTrue(all(g.values()))
        self.assertFalse(gates(s, {"mean": -0.01}, {"total_net": 1.0}, 200, (100, 89))["D datatjek >= 90 %"])
        self.assertFalse(gates(s, {"mean": -0.01}, {"total_net": 1.0}, None, (100, 95))["G3 events >= n_req"])

    def test_holdout_requires_committed_frozen_file(self):
        orig = pmcal.HERE
        try:
            pmcal.HERE = os.path.join(orig, "does-not-exist")
            self.assertIsNone(pmcal.frozen())
            with self.assertRaises(SystemExit):
                pmcal.fetch("holdout", log=lambda *_: None)
        finally:
            pmcal.HERE = orig


if __name__ == "__main__":
    unittest.main()
