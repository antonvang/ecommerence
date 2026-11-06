"""Paper-book contracts with hand-computable fills and deliberate bad events."""
import copy
import hashlib
import json
import math
import unittest

from paper_engine import simulate_paper


def plan(**changes):
    value = dict(protocol_id="locked-test", initial_cash=1000.0,
                 max_gross_fraction=1.0, max_asset_fraction=0.5,
                 fee_bps=0.0, max_drawdown_fraction=0.4,
                 max_quote_age_s=10, allowed_assets=["A", "B"])
    value.update(changes)
    return value


def event(key="1", ts=1000, asset="A", bid=10.0, ask=10.0, signal=1.0, **changes):
    value = dict(key=key, ts=ts, asset=asset, bid=bid, ask=ask,
                 quote_ts=ts, signal=signal, avail_ts=ts)
    value.update(changes)
    return value


class PaperTests(unittest.TestCase):
    def test_bid_ask_and_fee_are_cash_costs(self):
        result = simulate_paper(plan(fee_bps=10), [event(bid=9, ask=11)])
        self.assertEqual(result["status"], "OK")
        fill = result["fills"][0]
        self.assertEqual((fill["side"], fill["price"]), ("BUY", 11))
        self.assertAlmostEqual(fill["fee"], fill["units"] * 11 / 1000)
        self.assertAlmostEqual(result["cash"], 1000 - fill["units"] * 11 - fill["fee"])
        self.assertAlmostEqual(result["end_equity"], result["cash"] + fill["units"] * 10)
        self.assertLessEqual(result["positions"]["A"]["notional"], result["end_equity"] * 0.5)

    def test_long_and_short_funding_sign(self):
        for direction in (1, -1):
            result = simulate_paper(plan(), [event(signal=direction),
                event("2", ts=1001, signal=direction, funding_rate=0.01)])
            self.assertAlmostEqual(result["total_funding"], direction * 5)
            self.assertAlmostEqual(result["end_equity"], 1000 - direction * 5)

    def test_sell_hits_bid(self):
        result = simulate_paper(plan(), [event(signal=-1, bid=9, ask=11)])
        self.assertEqual(result["fills"][0]["price"], 9)
        self.assertEqual(result["fills"][0]["side"], "SELL")

    def test_bad_events_never_update_marks_positions_or_cash(self):
        wrong = [event(avail_ts=1001), event(quote_ts=1001), event(quote_ts=989),
                 event(bid=12, ask=11), event(signal=float("nan")), event(asset="X")]
        result = simulate_paper(plan(), wrong)
        self.assertEqual(result["status"], "REJECTED_EVENTS")
        self.assertEqual(result["fills"], [])
        self.assertEqual(result["accepted_events"], 0)
        self.assertEqual(result["end_equity"], 1000)
        self.assertEqual([e["code"] for e in result["errors"]],
                         ["LOOKAHEAD_SIGNAL", "FUTURE_QUOTE", "STALE_QUOTE", "BAD_QUOTE",
                          "NONFINITE_EVENT", "UNKNOWN_ASSET"])

    def test_out_of_order_and_idempotency_precedence(self):
        first = event()
        result = simulate_paper(plan(), [first, event("2", ts=1001), first,
                                         event("3", ts=999)])
        self.assertEqual(result["idempotent_hits"], 1)
        self.assertEqual(result["accepted_events"], 2)
        self.assertEqual([e["code"] for e in result["errors"]], ["OUT_OF_ORDER"])

    def test_conflicting_key_and_invalid_key_retry(self):
        first = event()
        result = simulate_paper(plan(), [event(signal=2), first, dict(first, signal=-1)])
        self.assertEqual(result["accepted_events"], 1)
        self.assertEqual([e["code"] for e in result["errors"]], ["BAD_SIGNAL", "KEY_CONFLICT"])
        self.assertEqual(len(result["fills"]), 1)
        self.assertEqual(result["fills"][0]["side"], "BUY")

    def test_gross_and_asset_caps_include_costs_and_all_assets(self):
        result = simulate_paper(plan(max_gross_fraction=0.6, max_asset_fraction=0.5, fee_bps=10),
                                [event(), event("2", ts=1000, asset="B")])
        gross = math.fsum(abs(p["notional"]) for p in result["positions"].values())
        self.assertLessEqual(gross, result["end_equity"] * 0.6)
        for position in result["positions"].values():
            self.assertLessEqual(abs(position["notional"]), result["end_equity"] * 0.5)
        self.assertTrue(any(f["reason"] == "RISK_CAPPED_TARGET" for f in result["fills"]))

    def test_drawdown_stop_is_sticky_and_closes_at_current_quote(self):
        result = simulate_paper(plan(max_asset_fraction=1.0, max_drawdown_fraction=0.1),
                                [event(), event("2", ts=1001, bid=8, ask=8),
                                 event("3", ts=1002, bid=10, ask=10)])
        self.assertEqual(result["status"], "RISK_STOPPED")
        self.assertIn("DRAWDOWN_LIMIT", result["stop_reasons"])
        self.assertEqual(result["positions"], {})
        self.assertAlmostEqual(result["end_equity"], 800)
        self.assertEqual(len(result["fills"]), 2)
        self.assertEqual(result["fills"][-1]["reason"], "RISK_LIQUIDATION")

    def test_stale_residual_is_disclosed_and_later_liquidated(self):
        settings = plan(max_gross_fraction=0.8, max_asset_fraction=0.4,
                        max_drawdown_fraction=0.01, max_quote_age_s=1)
        result = simulate_paper(settings, [event(), event("2", ts=1000, asset="B"),
            event("3", ts=1003, asset="B", bid=9, ask=9)])
        self.assertEqual(result["status"], "RISK_STOPPED")
        self.assertEqual(result["unliquidated_assets"], ["A"])
        self.assertEqual(set(result["positions"]), {"A"})
        later = simulate_paper(settings, [event(), event("2", ts=1000, asset="B"),
            event("3", ts=1003, asset="B", bid=9, ask=9), event("4", ts=1004)])
        self.assertEqual(later["positions"], {})
        self.assertEqual(later["unliquidated_assets"], [])

    def test_old_other_asset_mark_cannot_fund_a_new_position(self):
        result = simulate_paper(plan(max_quote_age_s=1),
                                [event(), event("2", ts=1003, asset="B")])
        self.assertEqual(result["status"], "RISK_STOPPED")
        self.assertIn("STALE_PORTFOLIO_QUOTE", result["stop_reasons"])
        self.assertNotIn("B", result["positions"])
        self.assertEqual(result["unliquidated_assets"], ["A"])

    def test_input_is_unchanged_and_audit_chain_recomputes(self):
        settings, rows = plan(), [event(), event("2", ts=1001, signal=0)]
        before = copy.deepcopy((settings, rows))
        result = simulate_paper(settings, rows)
        self.assertEqual((settings, rows), before)
        self.assertEqual(result, simulate_paper(settings, rows))
        head = "0" * 64
        for entry in result["audit"]:
            post = dict(entry)
            digest = post.pop("hash")
            self.assertEqual(post["prev"], head)
            head = hashlib.sha256(json.dumps(post, sort_keys=True, separators=(",", ":"),
                                            ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            self.assertEqual(digest, head)
        self.assertEqual(result["audit_head"], head)

    def test_audit_commits_input_even_when_book_stays_flat(self):
        first = simulate_paper(plan(), [event(signal=0, funding_rate=0)])
        second = simulate_paper(plan(), [event(signal=0, funding_rate=0.1)])
        self.assertEqual(first["end_equity"], second["end_equity"])
        self.assertEqual(first["audit"][0]["book_sha256"], second["audit"][0]["book_sha256"])
        self.assertNotEqual(first["audit_head"], second["audit_head"])

    def test_bad_plan_and_numeric_failure_have_no_book(self):
        for settings in (plan(initial_cash=True), plan(allowed_assets=["A", "A"]),
                         plan(max_asset_fraction=2), None):
            result = simulate_paper(settings, [])
            self.assertEqual(result["status"], "INVALID_INPUT")
            self.assertNotIn("cash", result)
        settings = plan(initial_cash=1e308, max_asset_fraction=1.0, fee_bps=1e308)
        result = simulate_paper(settings, [event()])
        self.assertEqual(result["status"], "NUMERIC_ERROR")
        self.assertNotIn("fills", result)


if __name__ == "__main__":
    unittest.main()
