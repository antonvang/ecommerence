import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import tsmom  # noqa: E402
from research.tsmom import CAPITAL, DAY, NOTIONAL, WEEK, Data, block_lb, data_check, gates, n_req, psr, run, summarize, ts  # noqa: E402

M0 = ts("2022-01-03")  # mandag


def flat_then(prices, start=M0 - 40 * DAY):
    """Daglige candles: dag i -> (open, close) = prices(i)."""
    return [[start + i * DAY, prices(i), prices(i)] for i in range(120)]


def data(price_fn, rate=0.0, hl=None):
    c = {a: flat_then(price_fn) for a in tsmom.ASSETS}
    bf = {a: [[t, rate] for t in range(M0 - 40 * DAY, M0 + 80 * DAY, 8 * 3600)] for a in tsmom.ASSETS}
    hf = {a: [] for a in tsmom.ASSETS}
    return Data(c, bf, hf, hl or {a: [] for a in tsmom.ASSETS})


class Tsmom(unittest.TestCase):
    def test_signal_uses_only_closes_before_monday(self):
        d = data(lambda i: 100.0 + i)
        s = d.signal("BTC", M0, 1)
        sunday, prev = (M0 - DAY - (M0 - 40 * DAY)) // DAY, (M0 - DAY - WEEK - (M0 - 40 * DAY)) // DAY
        self.assertAlmostEqual(s, (100 + sunday) / (100 + prev) - 1)
        d2 = data(lambda i: 100.0 + i if i < 40 else 1.0)          # krak FRA mandag: må ikke ændre signalet
        self.assertAlmostEqual(d2.signal("BTC", M0, 1), s)

    def test_long_short_pnl_flip_costs_and_funding_sign(self):
        up = data(lambda i: 100.0 * (1.01 ** i), rate=0.0001)
        w = run(up, ("2022-01-03", "2022-01-10"), 1)
        self.assertGreater(w[0]["price"], 0)                        # stigende pris, long
        self.assertLess(w[0]["funding"], 0)                         # long betaler positiv funding
        self.assertAlmostEqual(w[0]["cost"] * CAPITAL, 3 * NOTIONAL * tsmom.FEE + NOTIONAL * sum(tsmom.HALF_SPREAD.values()))
        self.assertEqual(w[1]["cost"], 0.0)                         # uændret position: ingen omkostning
        # vending fra long til short koster 2 sider
        vshape = data(lambda i: 100.0 + i if i < 47 else 300.0 - 3 * i)
        ws = run(vshape, ("2022-01-03", "2022-01-17"), 1)
        flips = [w for w in ws if w["sides"] == 6]
        self.assertTrue(flips)

    def test_short_receives_funding(self):
        down = data(lambda i: 100.0 * (0.99 ** i), rate=0.0001)
        w = run(down, ("2022-01-10", "2022-01-10"), 1)
        self.assertGreater(w[0]["funding"], 0)
        self.assertGreater(w[0]["price"], 0)                        # short tjener på fald

    def test_missing_prices_and_funding_are_reported_not_invented(self):
        d = data(lambda i: 100.0 + i)
        for a in tsmom.ASSETS:
            d.c[a].pop(M0 + WEEK, None)                             # exit-pris mangler
            d.bf[a] = []
        w = run(d, ("2022-01-03", "2022-01-03"), 1)
        self.assertEqual(w[0]["price"], 0.0)
        w2 = run(data(lambda i: 100.0 + i), ("2022-01-03", "2022-01-03"), 1)
        d3 = data(lambda i: 100.0 + i)
        for a in tsmom.ASSETS:
            d3.bf[a] = []
        self.assertEqual(len(run(d3, ("2022-01-03", "2022-01-03"), 1)[0]["no_funding"]), 3)
        self.assertGreater(w2[0]["price"], 0)

    def test_delay_scenario_uses_monday_close(self):
        d = data(lambda i: 100.0 + i)
        for a in tsmom.ASSETS:                                      # mandagene: åbning 100, lukning 110 / 120
            d.c[a][M0] = (100.0, 110.0)
            d.c[a][M0 + WEEK] = (100.0, 120.0)
        on_open = run(d, ("2022-01-03", "2022-01-03"), 1)[0]["price"] * tsmom.CAPITAL
        on_close = run(d, ("2022-01-03", "2022-01-03"), 1, delay=True)[0]["price"] * tsmom.CAPITAL
        self.assertAlmostEqual(on_open, 0.0)                        # 100 -> 100
        self.assertAlmostEqual(on_close, 3 * NOTIONAL * (120 / 110 - 1))

    def test_data_check_and_stats(self):
        hl = {a: [[M0 - DAY, 100.0 + 39]] for a in tsmom.ASSETS}
        self.assertTrue(data_check(data(lambda i: 100.0 + i, hl=hl))["passed"])
        bad = {a: [[M0 - DAY, 200.0]] for a in tsmom.ASSETS}
        self.assertFalse(data_check(data(lambda i: 100.0 + i, hl=bad))["passed"])
        self.assertFalse(data_check(data(lambda i: 100.0 + i))["passed"])   # ingen fælles dage = ikke bestået
        r = [0.01, -0.005, 0.02, 0.0, 0.01, -0.01, 0.015, 0.005, 0.01, -0.002] * 3
        self.assertLess(block_lb(r, 0.005), sum(r) / len(r))
        self.assertGreater(psr(r), 0.5)
        self.assertIsNone(n_req(-0.001, 0.01))
        weeks = [{"net": x, "price": x, "funding": 0.0, "cost": 0.0, "skipped": [], "no_funding": [], "sides": 0} for x in r]
        s = summarize(weeks)
        g = gates(s, {"sharpe_ann": 99.0}, {"total_net": 1.0}, 10, {"passed": True})
        self.assertFalse(g["G4 Sharpe > køb-og-hold"])
        self.assertTrue(g["G3 uger >= n_req"])


if __name__ == "__main__":
    unittest.main()
