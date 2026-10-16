import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import carry  # noqa: E402
from research.carry import DAY, HOUR, N, Market, block_lb, coin_week, gates, n_req, pick, summarize, ts  # noqa: E402

MON = ts("2026-03-02")  # en mandag


def candles(start, days, price, high=None, vol=1e7, step=0.0):
    return [{"t": (start + i * DAY) * 1000, "o": str(price + i * step), "c": str(price + i * step), "h": str(high or price + i * step), "v": str(vol / price)}
            for i in range(days)]


def market(spot_price=100.0, perp_price=100.0, rate=0.0001, perp_high=None, spot_vol=1e7, gap_hours=0, perp_step=0.0, spot_step=0.0):
    start = MON - 10 * DAY
    hours = [(h + 1, rate) for h in range(start, MON + 20 * DAY, HOUR)]  # sekunder (som i cachen), 1 s efter timen
    if gap_hours:
        hours = [x for x in hours if not (MON + DAY <= x[0] < MON + DAY + gap_hours * HOUR)]
    return Market([("X", "UX")], {"X": hours}, {"X": candles(start, 30, perp_price, perp_high, step=perp_step)},
                  {"UX": candles(start, 30, spot_price, vol=spot_vol, step=spot_step)})


class Carry(unittest.TestCase):
    def test_funding_is_paid_hourly_on_drifting_notional(self):
        r = coin_week(market(rate=0.0001), "X", "UX", MON, entering=False, exiting=False)
        self.assertAlmostEqual(r["funding"], 168 * 0.0001 * N, places=9)   # tider rundes ned til hel time
        self.assertAlmostEqual(r["net"], r["funding"], places=9)            # flad pris, ingen gebyrer
        up = coin_week(market(rate=0.0001, perp_step=1.0, spot_step=1.0), "X", "UX", MON, entering=False, exiting=False)
        self.assertGreater(up["funding"], r["funding"])                     # notionel stiger med prisen

    def test_costs_only_on_entry_and_exit(self):
        mk = market(rate=0.0)
        keep = coin_week(mk, "X", "UX", MON, entering=False, exiting=False)["cost"]
        both = coin_week(mk, "X", "UX", MON, entering=True, exiting=True)["cost"]
        self.assertEqual(keep, 0.0)
        self.assertAlmostEqual(both, 2 * N * (0.00070 + 0.0005 + 0.00045 + 0.0002))
        self.assertAlmostEqual(coin_week(mk, "X", "UX", MON, entering=True, exiting=True, cost_mult=3)["cost"], 3 * both)

    def test_hedged_price_move_cancels_and_liquidation_is_charged(self):
        r = coin_week(market(perp_step=1.0, spot_step=1.0), "X", "UX", MON, entering=False, exiting=False)
        self.assertAlmostEqual(r["basis"], 0.0, places=9)
        liq = coin_week(market(perp_high=200.0), "X", "UX", MON, entering=False, exiting=False)
        self.assertTrue(liq["liquidated"])
        self.assertAlmostEqual(liq["perp_pnl"], -N * 1.005)

    def test_missing_funding_hours_are_counted_not_invented(self):
        r = coin_week(market(rate=0.0001, gap_hours=5), "X", "UX", MON, entering=False, exiting=False)
        self.assertEqual(r["missing_hours"], 5)
        self.assertAlmostEqual(r["funding"], 163 * 0.0001 * N, places=9)

    def test_universe_is_point_in_time_and_rejects_name_collisions(self):
        self.assertEqual([e[0] for e in pick(market(rate=0.0001), MON)], ["X"])        # 0,0001 x 168 x 52 > 10 %
        self.assertEqual(pick(market(spot_price=50.0), MON), [])                         # spot != perp: anden token
        self.assertEqual(pick(market(rate=0.00001), MON), [])                            # under 10 %/år
        self.assertEqual(pick(market(rate=0.0001, spot_vol=1e5), MON), [])               # for lidt spot-volumen
        mk = market(rate=0.0001)
        future = [(t, 0.05) for t in range(MON, MON + 7 * DAY, HOUR)]                     # enorm funding EFTER mandag
        mk2 = Market(mk.ps, {"X": [(t, r) for t, r in mk.f["X"].items() if t < MON] + future},
                     {"X": list(mk.perp["X"].values())}, {"UX": list(mk.spot["UX"].values())})
        self.assertAlmostEqual(mk2.signal("X", MON)[0], mk.signal("X", MON)[0])          # fremtiden påvirker ikke signalet

    def test_stats_and_gates(self):
        weeks = [{"active": True, "net": x, "funding": x, "basis": 0.0, "cost": 0.0, "liquidations": 0, "excluded": [], "missing_hours": 0,
                  "coins": ["X"]} for x in [0.002, 0.001, 0.003, -0.001, 0.002, 0.002, 0.001, 0.002, 0.003]]
        s = summarize(weeks)
        self.assertAlmostEqual(s["max_dd"], 0.001)
        self.assertEqual(len(s["thirds"]), 3)
        self.assertLess(block_lb([w["net"] for w in weeks], 0.006), s["mean_week"])
        self.assertIsNone(n_req(-0.001, 0.002))
        self.assertEqual(n_req(0.001, 0.001), 12)
        g = gates(s, {"total_net": 0.01}, 12)
        self.assertFalse(g["G3 aktive uger >= n_req"])   # 9 aktive uger < 12


if __name__ == "__main__":
    unittest.main()
