import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import MIGRATION, buy, parse_migration, sell  # noqa: E402
from swaps import WSOL  # noqa: E402

MINT = "MemeMintXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXpump"


def bal(idx, mint, owner, amount, dec):
    return {"accountIndex": idx, "mint": mint, "owner": owner, "uiTokenAmount": {"amount": str(int(amount * 10 ** dec)), "decimals": dec}}


def migrate_tx(sol=84.0, logs=("Program log: Instruction: Migrate",), err=None):
    keys = [MIGRATION, "Pool", "PoolSolVault", "PoolTokVault", "Curve"]
    return {"blockTime": 1_700_000_000, "transaction": {"signatures": ["s"], "message": {"accountKeys": [
                {"pubkey": k, "signer": i == 0} for i, k in enumerate(keys)]}},
            "meta": {"err": err, "logMessages": list(logs), "preBalances": [0] * 5, "postBalances": [0] * 5,
                     "postTokenBalances": [bal(2, WSOL, "Pool", sol, 9), bal(3, MINT, "Pool", 206_900_000, 6)]}}


class Sniper(unittest.TestCase):
    def test_parse_real_graduation(self):
        g = parse_migration(migrate_tx())
        self.assertEqual((g["mint"], g["pool"], g["sol_vault"], g["tok_vault"]), (MINT, "Pool", "PoolSolVault", "PoolTokVault"))

    def test_ignores_non_graduations(self):
        self.assertIsNone(parse_migration(migrate_tx(sol=2.0)))           # for lidt SOL: ikke en rigtig graduation
        self.assertIsNone(parse_migration(migrate_tx(logs=("other",))))   # ikke Migrate
        self.assertIsNone(parse_migration(migrate_tx(err={"x": 1})))      # fejlet

    def test_round_trip_at_same_price_costs_fees_and_impact(self):
        t = buy(50, 0.001, 12_000, 0.0075, 0.3)
        got = sell(t, 0.001, 12_000, 0.0075, 0.3)
        self.assertLess(got, 50)
        self.assertGreater(got, 47)  # ~1,5 % gebyr + 2 x tip + lidt pris-påvirkning
        self.assertAlmostEqual(sell(t, 0.002, 12_000, 0.0, 0.0) / sell(t, 0.001, 12_000, 0.0, 0.0), 2, delta=0.02)


if __name__ == "__main__":
    unittest.main()
