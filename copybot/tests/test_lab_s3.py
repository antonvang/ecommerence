import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import scanner  # noqa: E402
from lab.__main__ import main as cli  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.lifecycle import state  # noqa: E402
from lab.registry import fingerprint  # noqa: E402

DAY = 86400


class World:
    """Fake public APIs. `gap`, `premium`, `negrisk_ask` and `competition` control what the detectors see."""

    def __init__(self, gap=0.0, premium=0.0, negrisk_ask=0.55, competition=0.0, fail_binance=False):
        self.gap, self.premium, self.negrisk_ask, self.competition, self.fail = gap, premium, negrisk_ask, competition, fail_binance

    def get(self, url):
        if "rewards/markets/current" in url:
            return {"data": [{"condition_id": f"c{i}", "total_daily_rate": 20, "rewards_max_spread": 4.0,
                              "rewards_min_size": 20} for i in range(5)], "next_cursor": "LTE="}
        if "/markets/c" in url:
            return {"tokens": [{"token_id": "t" + url.rsplit("/c", 1)[1]}, {"token_id": "n"}]}
        if "/book?token_id=" in url:
            c = self.competition
            return {"bids": [{"price": "0.49", "size": str(c)}], "asks": [{"price": "0.51", "size": str(c)}]}
        if "exchangeInfo" in url:
            mk = lambda s, ct="PERPETUAL", ut="COIN": {"symbol": s, "contractType": ct, "underlyingType": ut,
                                                       "status": "TRADING", "quoteAsset": "USDT"}
            return {"symbols": [mk("ETHUSDT"), mk("SOLUSDT"), mk("PIXUSDT"), mk("SOLUSDT_261225", "CURRENT_QUARTER"),
                                mk("STOCKUSDT", ut="EQUITY")]}
        if "ticker/bookTicker" in url:
            if self.fail:
                raise OSError("binance unreachable")
            return [{"symbol": "ETHUSDT", "bidPrice": "1999.9", "askPrice": "2000.1"},
                    {"symbol": "PIXUSDT", "bidPrice": "0.999", "askPrice": "1.001"}]
        if "premiumIndex" in url:
            return [{"symbol": s, "markPrice": str(100 * (1 + p)), "indexPrice": "100", "lastFundingRate": "0.0001"}
                    for s, p in (("SOLUSDT", self.premium), ("SOLUSDT_261225", 0.02), ("STOCKUSDT", 0.02))]
        if "events/keyset" in url:
            return {"events": [{"slug": "who-wins", "negRisk": True, "markets": [
                {"active": True, "closed": False, "clobTokenIds": json.dumps([f"y{i}", f"n{i}"])} for i in range(2)]}]}
        raise AssertionError(url)

    def post(self, url, body):
        if url.endswith("/info"):
            return {"ETH": str(2000 * (1 + self.gap)), "kPEPE": "1", "PIX": "3.3"}   # PIX: identity mismatch
        if url.endswith("/books"):
            return [{"asset_id": b["token_id"], "asks": [{"price": str(self.negrisk_ask), "size": "100"}], "bids": []}
                    for b in body]
        raise AssertionError(url)


def graveyard_fixture(db, eid, tag, inst, horizon, execution, final="REJECTED"):
    db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=tag,
              fingerprint=fingerprint(tag, inst, horizon, execution), spec_json={"execution": execution})
    db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=final, actor="legacy-import",
              reason="fixture for scanner tests")


class Scanner(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")

    def tearDown(self):
        self.db.close()

    def scan(self, world, n, names=None):
        return [scanner.run(self.db, names, world.get, world.post, now=DAY * (100 + i)) for i in range(n)]

    def test_persistence_needs_scans_in_different_hours(self):
        w = World(gap=0.006)
        for k in range(3):                                             # three scans within the same hour
            s = scanner.run(self.db, ["pricing_constraint"], w.get, w.post, now=DAY * 50 + 60 * k)
        self.assertEqual((s["created"], s["waiting_persistence"]), ([], 1))
        s = scanner.run(self.db, ["pricing_constraint"], w.get, w.post, now=DAY * 50 + 3600)
        self.assertEqual(len(s["created"]), 1)

    def test_quiet_market_gives_observations_but_no_candidates(self):
        s = self.scan(World(competition=1e9), 1)[0]
        self.assertGreater(s["observations"], 0)
        self.assertEqual((s["flagged"], s["proposals"]), (0, 0))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM experiments")[0], 0)

    def test_persistence_then_created_then_seen_again(self):
        w = World(gap=0.006)
        first, second, third = self.scan(w, 3, ["pricing_constraint"])
        self.assertEqual(first["waiting_persistence"], 1)              # one scan is not enough
        self.assertEqual(len(second["created"]), 1)
        eid = second["created"][0]
        self.assertEqual(state(self.db, eid), "DISCOVERED")
        spec = json.loads(self.db.one("SELECT spec_json FROM experiments WHERE exp_id=?", eid)[0])
        self.assertEqual(spec["label"], "CANDIDATE (not evaluated)")
        self.assertEqual(third["seen_again"], [eid])                   # deduplicated

    def test_graveyard_suppresses_rejected_mechanisms(self):
        graveyard_fixture(self.db, "L22", "perp_premium_convergence", "btc_perp_spot", "minutes", "taker")
        graveyard_fixture(self.db, "L18", "negrisk_sum_arbitrage", "polymarket_negrisk", "instant", "taker")
        s = self.scan(World(premium=0.01, negrisk_ask=0.40), 2, ["pricing_constraint"])[1]
        self.assertEqual(len(s["suppressed"]), 2)
        self.assertIn("L18", s["suppressed"])                          # exact fingerprint of a rejected idea
        new = [e for e in s["suppressed"] if e != "L18"][0]               # same mechanism + execution as L22
        self.assertEqual(state(self.db, new), "SUPPRESSED")
        reason = self.db.one("SELECT reason FROM transitions WHERE exp_id=? AND to_state='SUPPRESSED'", new)[0]
        self.assertIn("L22", reason)

    def test_subsidy_covered_by_active_external_study(self):
        graveyard_fixture(self.db, "X01", "venue_subsidy_liquidity_rewards", "polymarket_reward_markets_panel", "days",
                          "maker", final="EXTERNAL")
        s = self.scan(World(competition=0.0), 2, ["venue_subsidy"])[1]
        self.assertEqual(s["covered"], ["X01"])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM experiments")[0], 1)

    def test_identity_mismatch_and_non_perpetuals_never_flag(self):
        self.scan(World(), 1, ["pricing_constraint"])
        rows = self.db.q("SELECT instrument, metric, flagged FROM observations")
        self.assertIn(("PIX", "identity_mismatch_suspected", 0), [tuple(r) for r in rows])
        flagged = [tuple(r) for r in rows if r["flagged"]]
        self.assertEqual(flagged, [])                                  # dated futures and stock contracts ignored
        self.assertTrue(all(r["detector"] == "pricing_constraint/2" for r in self.db.q("SELECT detector FROM observations")))

    def test_errors_recorded_and_no_evaluation_written(self):
        s = self.scan(World(fail_binance=True, premium=0.0), 1, ["pricing_constraint"])[0]
        self.assertTrue(any("binance unreachable" in e for e in s["errors"]))
        for t in ("results", "datasets", "approvals"):
            self.assertEqual(self.db.one(f"SELECT COUNT(*) FROM {t}")[0], 0, t)
        chains, trig = self.db.verify()
        self.assertTrue(trig and all(b is None for _, b in chains.values()))

    def test_cli_lists_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "lab.db")
            db = DB(p)
            for i in range(2):
                scanner.run(db, ["pricing_constraint"], World(gap=0.006).get, World(gap=0.006).post, now=DAY * (5 + i))
            db.close()
            lines = []
            self.assertEqual(cli(["candidates"], p, lines.append), 0)
            self.assertTrue(any("DISCOVERED" in x and "pricing_constraint" in x for x in lines))
            self.assertTrue(any("FLAGGED" in x for x in lines))


if __name__ == "__main__":
    unittest.main()
