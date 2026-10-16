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


class SniperOpen(unittest.TestCase):
    def test_same_coin_is_bought_once(self):
        import tempfile
        from copybot import DEFAULTS
        import sniper as sn_mod
        root = tempfile.mkdtemp()
        sn = sn_mod.Sniper(DEFAULTS, root, log=lambda *a: None)
        sn.sol_usd = 150.0
        sn._reserves = lambda rows: {"PoolSolVault": 84.0, "PoolTokVault": 206_900_000.0}
        g = parse_migration(migrate_tx())
        sn.open(g); sn.open(g)
        self.assertEqual(sn.s.one("SELECT COUNT(*) FROM snipes")[0], 3)  # 3 regler, ikke 6
        sn.s.close()


class SniperDetect(unittest.TestCase):
    def test_retries_transactions_that_are_not_ready_yet(self):
        import tempfile
        from copybot import DEFAULTS
        import sniper as sn_mod
        sn = sn_mod.Sniper(DEFAULTS, tempfile.mkdtemp(), log=lambda *a: None)
        sn.cursor = "old"
        ready = {"n": 0}
        sn.rpc.signatures = lambda *a, **k: [{"signature": "new", "err": None}]
        def tx(sig):
            ready["n"] += 1
            return migrate_tx() if ready["n"] >= 2 else None  # først klar ved andet forsøg
        sn.rpc.transaction = tx
        self.assertEqual(sn.detect(), [])
        sn.pending["new"][1] -= 5  # der er gået mere end 2 sek siden sidste forsøg
        sn.rpc.signatures = lambda *a, **k: []
        self.assertEqual([g["mint"] for g in sn.detect()], [MINT])
        sn.s.close()


if __name__ == "__main__":
    unittest.main()
