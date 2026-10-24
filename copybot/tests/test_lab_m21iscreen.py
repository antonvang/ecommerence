"""Amendment 21i: the prospective per-event cost hurdle, spot-perp lead/lag (S1), perp-led vs spot-led moves (S2) and the
descriptive Abdi-Ranaldo spread; explore0 only, nothing invented."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypogen, m21iscreen as m  # noqa: E402
from tests.test_lab_movescreen import A, B, H  # noqa: E402


class Cost(unittest.TestCase):
    def test_floor_estimate_and_missing_history(self):
        self.assertAlmostEqual(m.rt_est(1e6), math.exp(0.8999) * 1e6 ** -0.454)
        liquid = {A + i * H: 1e8 / 24 for i in range(800)}                         # 100 M a day
        thin = {A + i * H: 1e6 / 24 for i in range(800)}                           # 1 M a day
        self.assertEqual(m.cost(liquid, A + 760 * H), hypogen.COST)                # the 0.46 % floor
        self.assertAlmostEqual(m.cost(thin, A + 760 * H), 2 * (2 * 0.0004 + m.rt_est(1e6)))
        self.assertIsNone(m.cost(thin, A + 100 * H))                               # < half of the 30 days


def pair(n=2600, seed=1, lead=None):
    """perp and spot {t: (close, qvol)}; at hours in `lead` spot jumps first and the perp follows one hour later."""
    rnd, p, s, perp, spot = random.Random(seed), 100.0, 100.0, {}, {}
    lead = lead or set()
    for i in range(n):
        r = rnd.gauss(0, 0.002)
        p *= math.exp(r + (0.004 if i - 1 in lead else 0.0) + rnd.gauss(0, 0.0003))
        s *= math.exp(r + (0.004 if i in lead else 0.0) + rnd.gauss(0, 0.0003))
        perp[A + i * H], spot[A + i * H] = (p, 1e6 / 24), (s, 1.0)
    return perp, spot


class Spot(unittest.TestCase):
    def test_s1_finds_a_planted_catch_up(self):
        perp, spot = {}, {}
        for c in range(20):
            perp[f"C{c}USDT"], spot[f"C{c}USDT"] = pair(seed=c, lead={760 + 70 * k + c for k in range(25)})
        r = m.s1(perp, spot, A, B)
        self.assertEqual(r["key"], "spot_lead|perp_1h|m21i")
        self.assertGreater(r["mean"], 0.001)                    # the catch-up hour is an event too: about half
        self.assertGreaterEqual(r["cost_hurdle"], hypogen.COST)
        self.assertIn("information only", r["label_extra"])

    def test_s2_splits_perp_and_spot_led_moves(self):
        perp, spot = pair(lead=set())
        t = A + 1000 * H
        perp = dict(perp)
        perp[t] = (perp[t][0] * math.exp(0.05), perp[t][1])                       # perp-only 5 % jump: perp-led
        fund = {"XUSDT": {A + i * 8 * H: 0.0001 for i in range(330)}}
        r = m.s2({"XUSDT": perp}, {"XUSDT": spot}, fund, A, B)
        self.assertEqual(r["descriptive_not_tested"]["perp-led (faded)"]["n_events"], 1)
        self.assertEqual(r["verdict"], "UNTESTABLE")


class Spread(unittest.TestCase):
    def test_abdi_ranaldo_is_zero_without_bounce_and_positive_with_it(self):
        flat = {A + i * H: (101.0, 100 / 1.01, 100.0) for i in range(48)}            # log-symmetric range
        self.assertTrue(all(v == 0 for v in m.ar_daily(flat).values()))
        bounce = {A + i * H: (100.2, 99.8, 100.2 if i % 2 else 99.8) for i in range(48)}
        self.assertTrue(all(v > 0 for v in m.ar_daily(bounce).values()))

    def test_the_hl_reader_keeps_the_phase_guard(self):
        with self.assertRaises(hypogen.Refused):
            m.HLReader("explore0").month("BTCUSDT", "klines", 2024, 2)


if __name__ == "__main__":
    unittest.main()
