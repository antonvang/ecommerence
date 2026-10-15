import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copybot import DEFAULTS, merge, load_wallets  # noqa: E402
from engine import Engine  # noqa: E402
from market import BacktestMarket, Quote  # noqa: E402
from report import build_state  # noqa: E402
from backtest import replay, candle_ranges  # noqa: E402
from store import Store  # noqa: E402
from swaps import WSOL, Swap, parse_swaps  # noqa: E402

W = "Wa11etAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"[:44]
MINT = "MintXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXpump"[:44]
CURVE = "CurveBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"[:44]
FEE = "FeeRecipCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"[:43]
POOL_AUTH = "PoolAuthDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"[:44]
SOL = 1_000_000_000


def tb(idx, mint, owner, amount, decimals=6):
    return {"accountIndex": idx, "mint": mint, "owner": owner,
            "uiTokenAmount": {"amount": str(int(amount * 10 ** decimals)), "decimals": decimals}}


def tx(keys, pre, post, pre_tb, post_tb, fee=5000, err=None, ts=1_700_000_000, sig="sig1"):
    return {"blockTime": ts,
            "meta": {"err": err, "fee": fee, "preBalances": pre, "postBalances": post,
                     "preTokenBalances": pre_tb, "postTokenBalances": post_tb},
            "transaction": {"signatures": [sig], "message": {"accountKeys": [
                {"pubkey": k, "signer": i == 0, "writable": True} for i, k in enumerate(keys)]}}}


def pumpfun_buy():
    # wallet køber 1.000.000 tokens for 1 SOL på bonding curve; ny token-konto (rent) oprettes
    rent = 2_039_280
    keys = [W, CURVE, FEE, "WalletAta", "CurveAta", "Program"]
    pre = [10 * SOL, 30 * SOL, 5 * SOL, 0, rent, 1]
    post = [10 * SOL - SOL - rent - 5000, 30 * SOL + int(0.99 * SOL), 5 * SOL + int(0.01 * SOL), rent, rent, 1]
    return tx(keys, pre, post,
              [tb(4, MINT, CURVE, 800_000_000)],
              [tb(3, MINT, W, 1_000_000), tb(4, MINT, CURVE, 799_000_000)])


def raydium_sell(left=0.0):
    keys = [W, "WalletAta", "PoolWsol", "PoolTok", "Program"]
    pre = [5 * SOL, 2_039_280, 100 * SOL, 2_039_280, 1]
    post = [5 * SOL + int(1.5 * SOL) - 5000, 2_039_280, int(98.5 * SOL), 2_039_280, 1]
    return tx(keys, pre, post,
              [tb(1, MINT, W, 1_000_000), tb(2, WSOL, POOL_AUTH, 100, 9), tb(3, MINT, POOL_AUTH, 5_000_000)],
              [tb(1, MINT, W, left), tb(2, WSOL, POOL_AUTH, 98.5, 9), tb(3, MINT, POOL_AUTH, 6_000_000 - left)],
              sig="sig2", ts=1_700_000_600)


class SwapParsing(unittest.TestCase):
    sol = staticmethod(lambda ts: 150.0)

    def test_pumpfun_buy(self):
        (s,) = parse_swaps(pumpfun_buy(), W, self.sol)
        self.assertEqual(s.side, "buy")
        self.assertAlmostEqual(s.tokens, 1_000_000)
        self.assertAlmostEqual(s.quote_usd, 150.0, places=4)  # rent og gebyr regnes fra
        self.assertAlmostEqual(s.price_usd, 150.0 / 1_000_000)
        self.assertAlmostEqual(s.reserve_usd, 30.99 * 150, places=3)
        self.assertAlmostEqual(s.leader_left, 1_000_000)

    def test_raydium_sell(self):
        (s,) = parse_swaps(raydium_sell(), W, self.sol)
        self.assertEqual(s.side, "sell")
        self.assertAlmostEqual(s.quote_usd, 1.5 * 150, places=4)
        self.assertAlmostEqual(s.reserve_usd, 98.5 * 150, places=3)
        self.assertEqual(s.leader_left, 0.0)

    def test_partial_sell_left(self):
        (s,) = parse_swaps(raydium_sell(left=250_000), W, self.sol)
        self.assertAlmostEqual(s.tokens, 750_000)
        self.assertAlmostEqual(s.leader_left, 250_000)

    def test_ignores_failed_transfer_and_other_wallet(self):
        t = pumpfun_buy()
        t["meta"]["err"] = {"InstructionError": [0, "Custom"]}
        self.assertEqual(parse_swaps(t, W, self.sol), [])
        plain = tx([W, "Other"], [5 * SOL, 0], [4 * SOL - 5000, SOL], [], [])
        self.assertEqual(parse_swaps(plain, W, self.sol), [])
        self.assertEqual(parse_swaps(pumpfun_buy(), "SomeoneElse", self.sol), [])

    def test_token_to_token_ignored(self):
        t = pumpfun_buy()
        t["meta"]["preTokenBalances"].append(tb(5, "OtherMint", W, 10))
        t["meta"]["postTokenBalances"].append(tb(5, "OtherMint", W, 0))
        self.assertEqual(parse_swaps(t, W, self.sol), [])


class FakeMarket:
    def __init__(self):
        self.p, self.r = {}, {}

    def quote(self, mint, ts, swap=None):
        return Quote(self.p[mint], self.r.get(mint, 1e12), mint[:4]) if mint in self.p else None

    def quotes(self, mints, ts):
        return {m: self.quote(m, ts) for m in mints}

    def sol_usd(self, ts=None):
        return 100.0


def cfg(**over):
    c = merge(DEFAULTS, {"fees": {"dex_pct": 1.0, "bot_pct": 1.0, "mev_slippage_pct": 0.0, "network_fee_sol": 0.0015},
                         "next_trader": "list", "fire_after_losses": 2, "min_liquidity_usd": 0,
                         "min_leader_buy_usd": 0, "max_price_impact_pct": 100, "position_pct": 50})
    c.update(over)
    return c


WALLETS = [{"addr": "A" * 32, "label": "kai_blitz"}, {"addr": "B" * 32, "label": "0xnora"}]


def sw(wallet, side, mint, ts, price, tokens=1000.0, left=None):
    if left is None:
        left = tokens if side == "buy" else 0.0
    return Swap("s%d%s" % (ts, side), wallet, ts, side, mint, tokens, tokens * price, price, left, None)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.s, self.m = Store(), FakeMarket()

    def eng(self, **over):
        e = Engine(cfg(**over), self.s, self.m, WALLETS)
        e.start(0)
        return e

    def test_costs_flat_price_loses_fees(self):
        e = self.eng(shadow_trade_usd=10)
        self.m.p["M"] = 1.0
        e.on_swap(sw("A" * 32, "buy", "M", 10, 1.0))
        e.on_swap(sw("A" * 32, "sell", "M", 20, 1.0))
        sh = self.s.one("SELECT * FROM positions WHERE book='shadow'")
        s_eff = (10 - 0.15) * 0.98
        self.assertAlmostEqual(sh["pnl_usd"], s_eff * 0.98 - 0.15 - 10, places=6)
        port = self.s.one("SELECT * FROM positions WHERE book='port'")
        self.assertAlmostEqual(port["cost_usd"], 25.0)  # 50 % af $50
        self.assertLess(port["pnl_usd"], 0)
        self.assertAlmostEqual(self.s.get("cash"), 50 + port["pnl_usd"], places=6)

    def test_price_impact_constant_product(self):
        e = self.eng(shadow_trade_usd=10)
        self.m.p["M"] = 1.0
        self.m.r["M"] = 100.0  # lille pool
        e.on_swap(sw("A" * 32, "buy", "M", 10, 1.0))
        p = self.s.one("SELECT * FROM positions WHERE book='shadow'")
        s_eff = (10 - 0.15) * 0.98
        self.assertAlmostEqual(p["tokens"], s_eff / (1 + s_eff / 100.0), places=6)

    def test_cannot_buy_cheaper_than_leader(self):
        e = self.eng()
        self.m.p["M"] = 0.5  # forsinket pris under walletens egen
        e.on_swap(sw("A" * 32, "buy", "M", 10, 1.0))
        p = self.s.one("SELECT * FROM positions WHERE book='shadow'")
        self.assertAlmostEqual(p["last_price"], 1.0)

    def test_fire_after_two_losses_then_next_on_list(self):
        e = self.eng()
        a = "A" * 32
        for k, mint in enumerate(["M1", "M2"]):
            self.m.p[mint] = 1.0
            e.on_swap(sw(a, "buy", mint, 100 + k * 100, 1.0))
            self.m.p[mint] = 0.8
            e.on_swap(sw(a, "sell", mint, 150 + k * 100, 0.8))
        self.assertEqual(e.active, "B" * 32)
        self.assertEqual(self.s.get("fired"), [a])
        kinds = [r["kind"] for r in self.s.q("SELECT kind FROM events ORDER BY id")]
        self.assertIn("fired", kinds)
        # bænkens køb kopieres kun i shadow, ikke på kontoen
        self.m.p["M3"] = 1.0
        e.on_swap(sw(a, "buy", "M3", 400, 1.0))
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM positions WHERE book='port' AND mint='M3'")[0], 0)

    def test_win_resets_streak(self):
        e = self.eng()
        a = "A" * 32
        for k, (exitp) in enumerate([0.8, 1.5, 0.8]):
            m = f"M{k}"
            self.m.p[m] = 1.0
            e.on_swap(sw(a, "buy", m, 100 + k * 100, 1.0))
            self.m.p[m] = exitp
            e.on_swap(sw(a, "sell", m, 150 + k * 100, exitp))
        self.assertEqual(e.active, a)
        self.assertEqual(self.s.get("streak"), 1)

    def test_proportional_sell(self):
        e = self.eng()
        a = "A" * 32
        self.m.p["M"] = 1.0
        e.on_swap(sw(a, "buy", "M", 10, 1.0))
        tok = self.s.one("SELECT tokens FROM positions WHERE book='port'")[0]
        e.on_swap(sw(a, "sell", "M", 20, 1.0, tokens=600, left=400))
        p = self.s.one("SELECT * FROM positions WHERE book='port'")
        self.assertIsNone(p["closed_ts"])
        self.assertAlmostEqual(p["tokens_left"], tok * 0.4)
        e.on_swap(sw(a, "sell", "M", 30, 1.0, tokens=400, left=0))
        self.assertIsNotNone(self.s.one("SELECT closed_ts FROM positions WHERE book='port'")[0])

    def test_stop_loss_and_timeout(self):
        e = self.eng(stop_loss_pct=40, max_hold_hours=1)
        a = "A" * 32
        self.m.p["M"] = 1.0
        self.m.p["N"] = 1.0
        e.on_swap(sw(a, "buy", "M", 10, 1.0))
        e.on_swap(sw(a, "buy", "N", 10, 1.0))
        self.m.p["M"] = 0.5
        e.check(60)
        self.assertEqual(self.s.one("SELECT reason FROM positions WHERE book='port' AND mint='M'")[0], "stop")
        self.assertIsNone(self.s.one("SELECT closed_ts FROM positions WHERE book='port' AND mint='N'")[0])
        e.check(10 + 3600)
        self.assertEqual(self.s.one("SELECT reason FROM positions WHERE book='port' AND mint='N'")[0], "timeout")

    def test_filters(self):
        e = self.eng(min_liquidity_usd=20000, min_leader_buy_usd=50)
        a = "A" * 32
        self.m.p["M"] = 1.0
        self.m.r["M"] = 5000  # $10k likviditet
        e.on_swap(sw(a, "buy", "M", 10, 1.0, tokens=1000))
        self.m.p["S"] = 1.0
        e.on_swap(sw(a, "buy", "S", 10, 1.0, tokens=10))  # $10 køb
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM positions")[0], 0)
        self.assertEqual(self.s.get("skips"), {"lav likviditet": 1, "lille køb": 1})

    def test_best_shadow_waits_for_proof(self):
        e = self.eng(next_trader="best_shadow", warmup_hours=1, min_shadow_trades=2, min_median_hold_minutes=0)
        self.assertIsNone(e.active)
        b = "B" * 32
        for k in range(2):
            m = f"W{k}"
            self.m.p[m] = 1.0
            e.on_swap(sw(b, "buy", m, 4000 + k * 100, 1.0))
            self.m.p[m] = 2.0
            e.on_swap(sw(b, "sell", m, 4050 + k * 100, 2.0))
        self.assertEqual(e.active, b)
        self.assertEqual(self.s.one("SELECT COUNT(*) FROM positions WHERE book='port'")[0], 0)


class BacktestReplay(unittest.TestCase):
    def test_replay_and_dashboard_state(self):
        a, b = "A" * 32, "B" * 32
        candles = {"M": [(t, 1.0, 1.0, 1.0, 1.0 + (t - 1000) / 6000) for t in range(1000, 8000, 60)],
                   "R": [(t, 1.0, 1.0, 1.0, max(1.0 - (t - 1000) / 1000, 0.01)) for t in range(1000, 8000, 60)]}
        mk = BacktestMarket(candles, [(0, 100, 100, 100, 100)], {"M": "MOON", "R": "RUG"})
        swaps = [sw(a, "buy", "R", 1000, 1.0), sw(b, "buy", "M", 1100, 1.0), sw(b, "sell", "M", 4000, 1.5)]
        for s in swaps:
            s.reserve_usd = 1e6
        s = Store()
        replay(cfg(), WALLETS, swaps, mk, s, delay=10, start_ts=900, end_ts=9000)
        st = build_state(s)
        json.dumps(st)
        self.assertEqual(s.one("SELECT reason FROM positions WHERE book='port' AND mint='R'")[0], "stop")
        self.assertGreater(s.one("SELECT pnl_usd FROM positions WHERE book='shadow' AND mint='M'")[0], 0)
        self.assertEqual(st["mode"], "BACKTEST")
        self.assertTrue(math.isfinite(st["balance"]))

    def test_candle_ranges(self):
        swaps = [sw("A" * 32, "buy", "M", 1000, 1.0), sw("A" * 32, "sell", "M", 2000, 1.0)]
        self.assertEqual(candle_ranges(swaps, 24, 10 ** 9)["M"], (700, 2600))

    def test_interpolation(self):
        mk = BacktestMarket({"M": [(60, 1.0, 2.0, 0.5, 2.0)]}, [(0, 1, 1, 1, 100)], {})
        self.assertIsNone(mk.price_at("M", 30))
        self.assertAlmostEqual(mk.price_at("M", 90), 1.5)
        self.assertAlmostEqual(mk.price_at("M", 500), 2.0)


class Loading(unittest.TestCase):
    def test_wallets_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8-sig") as f:
            f.write("# kommentar\n7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU @kai_blitz\nikke-en-adresse\n\n")
        try:
            ws = load_wallets(f.name)
        finally:
            os.remove(f.name)
        self.assertEqual(ws, [{"addr": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "label": "kai_blitz"}])


if __name__ == "__main__":
    unittest.main()


class RouterReserve(unittest.TestCase):
    def test_route_via_other_quote_uses_memecoin_side(self):
        # wallet betaler 1 SOL til en router; memecoin-poolen er parret med en anden token (ikke SOL)
        keys = [W, "Router", "BigSolPool", "WalletAta", "PoolMemeVault", "PoolQuoteVault"]
        pre = [10 * SOL, 1 * SOL, 25000 * SOL, 0, 2_039_280, 2_039_280]
        post = [9 * SOL - 2_039_280 - 5000, 1 * SOL, 25001 * SOL, 2_039_280, 2_039_280, 2_039_280]
        t = tx(keys, pre, post,
               [tb(2, WSOL, "SolUsdcAuth", 25000, 9), tb(4, MINT, "MemePool", 10_000_000), tb(5, "Quote", "MemePool", 500)],
               [tb(2, WSOL, "SolUsdcAuth", 25001, 9), tb(3, MINT, W, 1_000_000), tb(4, MINT, "MemePool", 9_000_000),
                tb(5, "Quote", "MemePool", 600)])
        (s,) = parse_swaps(t, W, lambda ts: 150.0)
        self.assertAlmostEqual(s.reserve_usd, 9_000_000 * 150.0 / 1_000_000, places=3)  # ikke SOL/USDC-poolens 25.000 SOL
