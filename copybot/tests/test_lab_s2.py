import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import legacy, lifecycle, registry, repro, stats  # noqa: E402
from lab.data import DENY, AccessRefused, Gateway, clip  # noqa: E402
from lab.db import DB, HERE  # noqa: E402
from research import carry, m3, pm_lp, pmcal, tsmom  # noqa: E402
from tests.test_lab import H, S, to_registered  # noqa: E402


class StatsEquivalence(unittest.TestCase):
    """lab.stats must reproduce every research-module statistic exactly."""

    def setUp(self):
        rng = random.Random(1)
        self.x = [rng.gauss(0.01, 0.05) for _ in range(150)]
        self.rows = [{"week": f"W{rng.randrange(30)}", "r": rng.gauss(0, 1), "market": f"m{rng.randrange(40)}",
                      "t": 86400 * rng.randrange(60), "net": rng.gauss(0, 1), "y": 1.0, "q": 0.5, "end": i, "event": str(i)}
                     for i in range(500)]

    def test_block_bootstrap(self):
        self.assertEqual(stats.block_lb(self.x, 0.005, block=8), tsmom.block_lb(self.x, 0.005))
        self.assertEqual(stats.block_lb(self.x, 0.005, block=4), carry.block_lb(self.x, 0.005))
        self.assertIsNone(stats.block_lb(self.x[:3], 0.005))

    def test_cluster_bootstraps(self):
        cl = stats.clusters_in_order(self.rows, lambda r: r["week"], lambda r: r["r"])
        self.assertEqual(stats.cluster_lb(cl, 0.005), pmcal.cluster_lb(self.rows))
        days = [{"market": r["market"], "pnl": r["r"]} for r in self.rows]
        by_m = stats.clusters_in_order(days, lambda r: r["market"], lambda r: r["pnl"])
        self.assertEqual(stats.cluster_lb(by_m, 0.005), pm_lp.cluster_lb(by_m))
        by_d = stats.clusters_in_order(self.rows, lambda r: r["t"] // 86400, lambda r: r["net"], builtin_sum=True)
        self.assertEqual(stats.cluster_lb(by_d, 0.01), m3.day_lb(self.rows))

    def test_n_req_and_psr(self):
        for z, mod in ((2.5758, tsmom), (2.512, carry), (3.0233, pmcal)):
            self.assertEqual(stats.n_req(0.002, 0.05, z_a=z), mod.n_req(0.002, 0.05))
        self.assertAlmostEqual(stats.z_one_sided(0.005), 2.5758, places=4)
        self.assertEqual(stats.psr(self.x), tsmom.psr(self.x))
        self.assertEqual(stats.max_drawdown([1, -2, 3, -4]), 4)


class GatewayRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = os.path.join(self.tmp.name, "d.json")
        with open(self.f, "w") as fh:
            fh.write("[1,2,3]")
        self.db = DB(":memory:")
        self.gw = Gateway(self.db, S)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def acc(self, split, purpose="evaluate", code="c1", exp="E1"):
        return self.gw.access(exp, split, [self.f], (0, 10), "unit", purpose, code)

    def test_split_needs_matching_state(self):
        to_registered(self.db)
        with self.assertRaises(AccessRefused):
            self.acc("dev")                                       # REGISTERED: no data yet
        lifecycle.auto_transition(self.db, "E1", "SCREENING", S, "spec committed, screening starts")
        self.assertIn(self.f, self.acc("dev"))
        for split in ("holdout", "forward"):
            with self.assertRaises(AccessRefused):
                self.acc(split)
        refused = self.db.q("SELECT payload FROM events WHERE kind='data.refused'")
        self.assertEqual(len(refused), 3)

    def test_holdout_once_and_changed_data(self):
        to_registered(self.db)
        lifecycle.auto_transition(self.db, "E1", "SCREENING", S, "spec committed, screening starts")
        ok = registry.record_result(self.db, "E1", "EXPLORATORY", "PASS (preliminary)", {}, {}, S)
        ev = {"result_id": ok}
        lifecycle.auto_transition(self.db, "E1", "SCREEN_PASSED", S, "development gates passed", ev,
                                  guards=(registry.make_result_guard(ev),))
        code = lifecycle.request_approval(self.db, "E1", "VALIDATION", H, "open the holdout once",
                                          {"committed_files": ["research/PMCAL_FROZEN.md"]})
        lifecycle.confirm(self.db, code, H)
        self.acc("holdout", code="c1")
        self.acc("holdout", code="c1")                            # identical rerun is allowed
        with self.assertRaises(AccessRefused):
            self.acc("holdout", code="c2")                        # changed code after opening
        with open(self.f, "w") as fh:
            fh.write("[9]")
        with self.assertRaises(AccessRefused):
            self.acc("holdout", code="c1")                        # changed data
        self.assertEqual(len(self.db.q("SELECT 1 FROM events WHERE kind='holdout.opened'")), 1)

    def test_external_pm_lp_reproduce_and_expected_hash(self):
        legacy_like = [("X01", "EXTERNAL"), ("L01", "REJECTED"), ("L02", "SCREENING")]
        for eid, st in legacy_like:
            self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="t", fingerprint=eid)
            self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=st, actor="legacy-import",
                           reason="fixture for gateway tests")
        with self.assertRaises(AccessRefused):
            self.acc("dev", "reproduce", exp="X01")               # EXTERNAL
        with self.assertRaises(AccessRefused):
            self.gw.access("L02", "dev", [os.path.join(DENY[0], "pm_lp.db")], (0, 1), "x", "evaluate")
        self.acc("dev", "reproduce", exp="L01")                   # finished experiment, audit read
        with self.assertRaises(AccessRefused):
            self.acc("holdout", "reproduce", exp="L01")           # never the holdout
        with self.assertRaises(AccessRefused):
            self.acc("dev", "reproduce", exp="L02")               # not finished
        with self.assertRaises(AccessRefused):
            self.gw.access("L01", "validation", [self.f], (0, 1), "x", "reproduce", None, {self.f: "0" * 64})
        self.assertEqual(clip([{"t": 1}, {"t": 5}, {"t": 11}], (0, 10), lambda r: r["t"]), [{"t": 1}, {"t": 5}])
        chains, trig = self.db.verify()
        self.assertTrue(trig and all(b is None for _, b in chains.values()))


@unittest.skipUnless(os.path.exists(os.path.join(HERE, "data", "research", "results", "pmcal_v1_dev.json")) and
                     os.path.exists(os.path.join(HERE, "data", "research", "tsmom", "manifest.json")),
                     "research caches not present")
class Acceptance(unittest.TestCase):
    def test_tsmom_and_pmcal_dev_reproduce_exactly(self):
        db = DB(":memory:")
        legacy.import_legacy(db)
        for fn in (repro.reproduce_tsmom, repro.reproduce_pmcal):
            r = fn(db)
            self.assertTrue(r["ok"], r["mismatches"])
            self.assertGreaterEqual(r["fields"], 40)
        self.assertEqual(db.one("SELECT COUNT(*) FROM datasets WHERE split='holdout'")[0], 0)
        db.close()


if __name__ == "__main__":
    unittest.main()
