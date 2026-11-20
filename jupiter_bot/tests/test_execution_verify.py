"""The order checks and the pre-sign transaction verifier reject by default."""
import tempfile
import unittest

from jupiter_bot.core import SOL, USDC, Rejected
from jupiter_bot.execution import config
from jupiter_bot.execution import mandate as M
from jupiter_bot.execution.jupiter_exec import make_request
from jupiter_bot.execution.verify import verify
from jupiter_bot.tests import execution_fakes as F
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = F.Env(self.dir.name, chain=self.chain())
        self.env.mandate()
        self.mandate = M.parse(self.env.paths.mandate.read_bytes())
        self.jupiter, self.rpc = self.env.engine()._clients(self.mandate)

    def tearDown(self):
        self.env.close()
        self.dir.cleanup()

    def chain(self):
        return F.Chain()

    def run_verify(self, side="BUY", amount=None, reference="200", **tx_options):
        amount = amount or (25_000_000 if side == "BUY" else 125_000_000)
        self.env.jupiter.tx_options = tx_options
        order = self.jupiter.order(make_request(side, amount, self.mandate), reference_price=reference)
        return order, verify(order, self.rpc, F.WALLET)

    def assertRejected(self, text, **kwargs):
        with self.assertRaises(Rejected) as ctx:
            self.run_verify(**kwargs)
        self.assertIn(text, str(ctx.exception))


class HappyPath(Base):
    def test_buy_and_sell_verify(self):
        order, verified = self.run_verify("BUY")
        self.assertEqual(verified.deltas[USDC.mint], -25_000_000)
        self.assertGreaterEqual(verified.deltas["sol"], order.min_out - config.FEE_CAP_LAMPORTS)
        self.assertEqual(verified.priority_lamports, 300)
        self.assertEqual(verified.created_atas, {F.WSOL_ATA: SOL.mint})
        self.assertEqual(verified.lookups, {F.ALT: 3})
        order, verified = self.run_verify("SELL")
        self.assertGreaterEqual(verified.deltas[USDC.mint], order.min_out)
        # every RPC call went to the mandate host, Jupiter calls to api.jup.ag only
        self.assertEqual(set(self.env.transport.hosts), {"api.jup.ag", F.RPC_HOST})


class TransactionRejections(Base):
    def test_extra_signer(self):
        self.assertRejected("more than one signature", extra_signer=F.key("maker"))

    def test_wrong_fee_payer(self):
        self.assertRejected("Fee payer", fee_payer=F.key("gas-sponsor"))

    def test_unknown_program_via_lookup_table(self):
        self.assertRejected("loaded from a lookup table", alt_program=F.EVIL_PROGRAM)

    def test_token_account_for_foreign_mint(self):
        self.assertRejected("mint outside the swap", ata_mint=F.OTHER_MINT)

    def test_sol_transfer_to_foreign_account(self):
        self.assertRejected("System transfer", side="SELL", transfer_to="alt")

    def test_other_token_instruction(self):
        self.assertRejected("Token instruction", extra_token_ix=b"\x03" + (1).to_bytes(8, "little"))

    def test_priority_fee_cap(self):
        self.assertRejected("Priority fee", cu_price=10**7, cu_limit=1_400_000)

    def test_legacy_transaction(self):
        self.assertRejected("", legacy=True)      # rejected while decoding (no tables) or as non-v0

    def test_deactivated_lookup_table(self):
        self.env.chain.alt_deactivated = True
        with self.assertRaises(Rejected) as ctx:
            self.run_verify()
        self.assertIn("deactivated", str(ctx.exception))

    def test_expired_blockhash(self):
        self.env.jupiter.overrides = {"lastValidBlockHeight": str(self.env.chain.height + 10)}
        self.assertRejected("Blockhash expired")


class SimulationRejections(Base):
    def test_output_below_threshold(self):
        self.env.chain.sim_effect = {"lamports": 100_000_000, USDC.mint: -25_000_000}
        self.assertRejected("receives less SOL")

    def test_sell_output_below_threshold(self):
        self.env.chain.sim_effect = {"lamports": -125_005_300, USDC.mint: 20_000_000}
        self.assertRejected("receives less USDC", side="SELL")

    def test_spends_more_than_intended(self):
        self.env.chain.sim_effect = {"lamports": 124_000_000, USDC.mint: -26_000_000}
        self.assertRejected("spends more USDC")

    def test_sol_drain_on_sell(self):
        self.env.chain.sim_effect = {"lamports": -(125_000_000 + 10**9 // 2), USDC.mint: 25_000_000}
        self.assertRejected("spends more SOL", side="SELL")

    def test_delegate_set_during_swap(self):
        self.env.chain.sim_delegate = True
        self.assertRejected("delegate")


class DrainOfAnotherToken(Base):
    def chain(self):
        return F.Chain(other=1_000_000)

    def test_other_balance_decrease(self):
        self.env.chain.sim_effect = {"lamports": 124_990_000, USDC.mint: -25_000_000, F.OTHER_MINT: -1}
        self.assertRejected("decreases another taker balance")


class OrderRejections(Base):
    def check(self, text, side="BUY", reference="200", **overrides):
        self.env.jupiter.overrides = overrides
        with self.assertRaises(Rejected) as ctx:
            self.run_verify(side=side, reference=reference)
        self.assertIn(text, str(ctx.exception))

    def test_order_response_rejections(self):
        cases = [("Router", dict(router="jupiterz")), ("Router", dict(router="dflow")),
                 ("Gasless", dict(gasless=True)), ("Gasless", dict(gasless=F.DROP)),
                 ("RFQ", dict(quoteId="q1")), ("RFQ", dict(maker=F.key("mm"))),
                 ("fee payer", dict(signatureFeePayer=F.key("gas"))),
                 ("prioritizationFeePayer", dict(prioritizationFeePayer=F.key("gas"))),
                 ("taker", dict(taker=F.key("someone"))),
                 ("mints", dict(outputMint=F.OTHER_MINT)), ("inAmount", dict(inAmount="24000000")),
                 ("slippageBps", dict(slippageBps=100)), ("otherAmountThreshold", dict(otherAmountThreshold="1")),
                 ("otherAmountThreshold", dict(otherAmountThreshold="999999999999")),
                 ("feeBps", dict(feeBps=80)), ("Fee charged", dict(feeMint=F.OTHER_MINT)),
                 ("v0", dict(transactionVersion=1)), ("Route leg", dict(routePlan=[{"swapInfo": {
                     "inputMint": USDC.mint, "outputMint": F.OTHER_MINT}}])),
                 ("route", dict(routePlan=[])), ("error", dict(errorCode=1, transaction="")),
                 ("no transaction", dict(transaction="")), ("requestId", dict(requestId="bad id!")),
                 ("lastValidBlockHeight", dict(lastValidBlockHeight=F.DROP)),
                 ("ExactIn", dict(swapMode="ExactOut"))]
        for text, overrides in cases:
            with self.subTest(overrides=overrides):
                self.check(text, **overrides)

    def test_price_far_from_journal(self):
        self.check("deviates", reference="150")

    def test_mandate_mints_and_amounts(self):
        mandate = M.parse(self.env.paths.mandate.read_bytes())
        object.__setattr__(mandate, "allowed_mints", (USDC.mint,))
        with self.assertRaises(Rejected):
            make_request("BUY", 1_000_000, mandate)
        with self.assertRaises(Rejected):
            make_request("BUY", 1.5, self.mandate)
        with self.assertRaises(Rejected):
            make_request("HOLD", 1, self.mandate)


if __name__ == "__main__":
    unittest.main()
