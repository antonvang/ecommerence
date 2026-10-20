"""The capital model: the user's own amount for a hedged carry book, planning only (no order, no account)."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import __main__ as cli, capital, web  # noqa: E402
from lab.db import DB  # noqa: E402


class Plan(unittest.TestCase):
    def test_numbers_checked_by_hand(self):
        p = capital.plan(1000, 5, 1, 0.0005)
        # capital per coin 200 = N (spot) + N (perp margin at 1x) + 0.2 N (buffer) -> N = 200 / 2.2
        n = 200 / 2.2
        self.assertAlmostEqual(p["per_coin"]["spot_notional_usd"], n)
        self.assertAlmostEqual(p["per_coin"]["perp_margin_usd"], n)
        self.assertAlmostEqual(p["per_coin"]["capital_usd"], 200)
        entry = n * (0.001 + 0.0005 + 2 * 0.0004)                       # both legs' fees + 2 x (slippage + half spread)
        self.assertAlmostEqual(p["costs"]["round_trip_usd_per_coin"], 2 * entry)
        self.assertAlmostEqual(p["costs"]["round_trip_pct_of_capital"], 2 * entry * 5 / 1000)
        per_day = 5 * n * 0.0005 * 3
        self.assertAlmostEqual(p["income"]["per_day_usd_book"], per_day)
        self.assertAlmostEqual(p["income"]["break_even_days"], 2 * entry * 5 / per_day)
        self.assertAlmostEqual(p["income"]["apr_on_capital"], per_day * 365 / 1000)
        self.assertAlmostEqual(p["liquidation_rise_approx"], 1.2)
        self.assertEqual(p["book"]["net_price_exposure_usd"], 0.0)
        self.assertAlmostEqual(p["book"]["max_share_per_coin"], 0.2)

    def test_the_whole_amount_is_accounted_for(self):
        for amount, coins, lev in ((200, 1, 1), (537.33, 7, 3), (10_000, 10, 2)):
            p = capital.plan(amount, coins, lev)
            pc = p["per_coin"]
            self.assertAlmostEqual((pc["spot_notional_usd"] + pc["perp_margin_usd"] + pc["margin_buffer_usd"]) * coins,
                                   amount, places=9)

    def test_leverage_frees_capital_and_brings_liquidation_closer(self):
        a, b = capital.plan(1000, 5, 1), capital.plan(1000, 5, 5)      # 5x: margin 20 % + buffer 20 % = 40 %
        self.assertGreater(b["per_coin"]["spot_notional_usd"], a["per_coin"]["spot_notional_usd"])
        self.assertLess(b["liquidation_rise_approx"], a["liquidation_rise_approx"])
        self.assertTrue(all(x["covered_without_topup"] for x in a["scenarios"]["adverse_price"]))
        self.assertFalse(b["scenarios"]["adverse_price"][-1]["covered_without_topup"])   # +50 % at 5x
        self.assertAlmostEqual(b["liquidation_rise_approx"], 0.4)

    def test_unknowns_are_reported_not_invented(self):
        p = capital.plan(500, 5)
        self.assertEqual(p["min_order_ok"], capital.UNKNOWN)
        self.assertEqual(p["income"]["break_even_days"], capital.UNKNOWN)
        items = {u["item"] for u in p["unknown"]}
        self.assertIn("minimum order value per coin", items)
        self.assertIn("maintenance margin tiers and exact liquidation price", items)

    def test_minimum_order(self):
        p = capital.plan(100, 10, 1, None, min_order=5)          # 10 USD per coin -> 4.55 USD per leg
        self.assertFalse(p["min_order_ok"])
        self.assertEqual(p["max_coins_at_min_order"], 9)         # 100 // (5 x 2.2)
        self.assertTrue(capital.plan(100, 1, 1, None, min_order=5)["min_order_ok"])

    def test_funding_at_or_below_zero_never_breaks_even(self):
        self.assertIsNone(capital.plan(1000, 5, 1, 0.0)["income"]["break_even_days"])
        self.assertLess(capital.plan(1000, 5, 1, -0.0001)["income"]["per_day_usd_book"], 0)

    def test_invalid_input_is_refused(self):
        for kw in ({"amount": 0}, {"amount": -5}, {"amount": "abc"}, {"amount": float("nan")},
                   {"amount": 100, "coins": 0}, {"amount": 100, "coins": 2.5}, {"amount": 100, "leverage": 0.5},
                   {"amount": 100, "leverage": 50}, {"amount": 100, "funding_8h": 0.5},
                   {"amount": 100, "min_order": -1}, {"amount": 100, "costs": {"spot_taker_fee": 0.5}},
                   {"amount": 100, "costs": {"buffer": 2}}):
            args = {"coins": 5, **kw}
            with self.assertRaises(capital.CapitalError, msg=kw):
                capital.plan(**args)

    def test_sensitivity_grid(self):
        s = capital.sensitivity(amounts=(200, 1000), coin_counts=(1, 5), funding_8h=0.0005)
        self.assertEqual(len(s["rows"]), 4)
        r = {(x["amount_usd"], x["coins"]): x for x in s["rows"]}
        self.assertAlmostEqual(r[(1000, 5)]["notional_per_coin_usd"], 200 / 2.2)
        # the cost share does not depend on the amount when only fees scale (no fixed costs)
        self.assertAlmostEqual(r[(200, 1)]["round_trip_pct_of_capital"], r[(1000, 5)]["round_trip_pct_of_capital"])


class Surfaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "lab.db")
        DB(cls.path).close()
        cls.srv = web.serve(cls.path, 18791)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.closing = True
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, p):
        try:
            with urllib.request.urlopen(self.base + p, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_api(self):
        code, body = self.get("/api/capital?amount=1000&coins=5&leverage=1&funding=0.0005&min_order=")
        self.assertEqual(code, 200)
        self.assertAlmostEqual(body["plan"]["per_coin"]["spot_notional_usd"], 200 / 2.2)
        self.assertEqual(body["plan"]["min_order_ok"], capital.UNKNOWN)
        self.assertEqual(len(body["sensitivity"]["rows"]), 20)
        code, body = self.get("/api/capital?amount=-3")
        self.assertEqual((code, "amount" in body["error"]), (400, True))

    def test_cli(self):
        lines = []
        self.assertEqual(cli.main(["capital", "--amount", "500", "--coins", "2"], db_path=self.path,
                                  out=lines.append), 0)
        self.assertAlmostEqual(json.loads(lines[0])["per_coin"]["capital_usd"], 250)
        lines = []
        self.assertEqual(cli.main(["capital", "--amount", "x"], db_path=self.path, out=lines.append), 1)
        self.assertTrue(lines[0].startswith("refused"))


if __name__ == "__main__":
    unittest.main()
