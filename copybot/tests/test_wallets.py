import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.wallets import wallet_features  # noqa: E402


class FakeLaunch:
    def __init__(self, mint, ts, buyers, outcome):
        self.g = {"mint": mint, "grad_ts": ts}
        self.events = [{"side": "buy", "ts": ts + 10, "trader": w, "sol": sol} for w, sol in buyers.items()]
        self.oc = outcome


class Wallets(unittest.TestCase):
    def test_only_outcomes_known_before_decision_count(self):
        H = 3600
        hist = [FakeLaunch(f"h{i}", 1000 + i * 100, {"W": 1.0}, 0.5) for i in range(3)]          # kendt længe før
        late = FakeLaunch("late", 100_000 - H + 100, {"W": 1.0}, -9.0)                          # udfald ikke kendt endnu
        target = FakeLaunch("t", 100_000, {"W": 2.0, "X": 1.0}, None)
        f = wallet_features([target], hist + [late], lambda x: x.oc)["t"]
        self.assertEqual((f["known_buyers"], f["smart_count"]), (1, 1))
        self.assertAlmostEqual(f["smart_wscore"], 0.5)   # 'late' (-9) må ikke indgå
        self.assertEqual(f["history_used"], 3)

    def test_needs_three_launches_and_target_never_sees_itself(self):
        hist = [FakeLaunch(f"h{i}", 1000 + i, {"W": 1.0}, -0.5) for i in range(2)]
        target = FakeLaunch("t", 50_000, {"W": 1.0}, 99.0)
        f = wallet_features([target], hist + [target], lambda x: x.oc)["t"]
        self.assertEqual(f["known_buyers"], 0)  # kun 2 tidligere launches, og target selv tæller ikke
        self.assertEqual(f["bad_share"], 0.0)

    def test_bad_share(self):
        hist = [FakeLaunch(f"h{i}", 1000 + i, {"B": 1.0}, -0.6) for i in range(3)]
        target = FakeLaunch("t", 50_000, {"B": 3.0, "N": 1.0}, None)
        self.assertAlmostEqual(wallet_features([target], hist, lambda x: x.oc)["t"]["bad_share"], 0.75)


if __name__ == "__main__":
    unittest.main()
