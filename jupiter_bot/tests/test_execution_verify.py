"""The order checks and the pre-sign transaction verifier reject by default."""
import struct
import tempfile
import unittest

from jupiter_bot.core import SOL, USDC, Rejected
from jupiter_bot.execution import mandate as M
from jupiter_bot.execution.jupiter_exec import make_request
from jupiter_bot.execution.solana_tx import TOKEN_PROGRAM
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
        self.assertEqual(verified.deltas["sol"], order.out_amount - 5_300)       # computed from the tx itself
        self.assertEqual((verified.priority_lamports, verified.network_fee, verified.expected_fee), (300, 5_300, 5_300))
        self.assertEqual(verified.swap, {"variant": "route", "in_amount": 25_000_000,
                                         "quoted_out_amount": 125_000_000, "slippage_bps": 50,
                                         "platform_fee_bps": 0, "min_out": order.min_out,
                                         "steps": [{"swap": "Whirlpool", "tag": 17, "fields": [0], "percent": 100,
                                                    "input_index": 0, "output_index": 1}]})
        self.assertEqual(verified.inner_programs, tuple(sorted({F.WHIRLPOOL, TOKEN_PROGRAM})))
        self.assertEqual(verified.pre["sol"], 1_000_000_000)
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
        self.assertRejected("Receives less SOL")

    def test_sell_output_below_threshold(self):
        self.env.chain.sim_effect = {"lamports": -125_005_300, USDC.mint: 20_000_000}
        self.assertRejected("Receives less USDC", side="SELL")

    def test_spends_more_than_intended(self):
        self.env.chain.sim_effect = {"lamports": 124_000_000, USDC.mint: -26_000_000}
        self.assertRejected("Spends more USDC")

    def test_sol_drain_on_sell(self):
        self.env.chain.sim_effect = {"lamports": -(125_000_000 + 10**9 // 2), USDC.mint: 25_000_000}
        self.assertRejected("Spends more SOL", side="SELL")

    def test_delegate_set_during_swap(self):
        self.env.chain.sim_delegate = True
        self.assertRejected("delegate")


class ExactFee(Base):
    """F6: no fixed tolerance; only this transaction's own fee may be added on the SOL side."""

    def test_small_buy_cannot_hide_a_bad_fill_in_a_fee_cap(self):          # review probe P2
        self.env.chain.sim_effect = {"lamports": 400_000, USDC.mint: -1_000_000}
        self.assertRejected("Receives less SOL", amount=1_000_000)

    def test_sell_cannot_leak_extra_sol(self):                               # review probe P3
        self.env.chain.sim_effect = {"lamports": -(125_000_000 + 4_500_000), USDC.mint: 25_000_000}
        self.assertRejected("Spends more SOL", side="SELL")
        self.env.chain.sim_effect = {"lamports": -(125_000_000 + 5_301), USDC.mint: 25_000_000}
        self.assertRejected("Spends more SOL", side="SELL")                 # one lamport over the exact fee
        self.env.chain.sim_effect = {"lamports": -(125_000_000 + 5_300), USDC.mint: 25_000_000}
        self.run_verify(side="SELL")                                         # exactly the fee: fine


class WalletAccount(Base):
    """F2: the wallet must stay a plain System account in the simulated post-state."""

    def test_owner_change_rejected(self):                                    # review probe P1
        self.env.chain.sim_wallet = {"owner": F.EVIL_PROGRAM}
        self.assertRejected("plain System account")

    def test_data_or_executable_rejected(self):
        self.env.chain.sim_wallet = {"data": b"\x01" * 64}
        self.assertRejected("plain System account")
        self.env.chain.sim_wallet = {"executable": True}
        self.assertRejected("plain System account")


class JupiterInstruction(Base):
    """F3: the route instruction's own arguments are decoded and checked before signing."""

    def test_in_amount_must_match(self):
        self.assertRejected("in_amount", ix_in_amount=24_000_000)

    def test_slippage_and_fee(self):
        self.assertRejected("slippage", ix_slippage=10_000)                  # a loose floor = sandwich bait
        self.assertRejected("platform fee", ix_fee=200)

    def test_floor_below_threshold(self):
        self.assertRejected("floor", quoted_out=100_000_000)

    def test_variants(self):
        self.assertRejected("route_with_token_ledger", variant="route_with_token_ledger")
        self.assertRejected("route_v2", variant="route_v2")
        self.assertRejected("unknown", raw_route=b"\x00" * 40)
        self.assertRejected("steps", raw_route=F.disc("route") + b"\x00" * 5)
        order, verified = self.run_verify(variant="shared_accounts_route")
        self.assertEqual(verified.swap["variant"], "shared_accounts_route")

    def route(self, in_amount=25_000_000, quoted=125_000_000, slippage=50, **kwargs):
        return F.route_data(in_amount, quoted, slippage, **kwargs)

    def test_appended_fake_tail_rejected(self):                       # N1, review probe
        real = self.route(quoted=1, slippage=10_000)                     # what the program would read
        evil = real + struct.pack("<QQHB", 25_000_000, 125_000_000, 50, 0)
        self.assertRejected("trailing bytes", raw_route=evil)

    def test_front_to_back_structure(self):
        self.assertRejected("not pinned", raw_route=self.route(steps=(b"\x63\x64\x00\x01",)))   # tag 99
        self.assertRejected("truncated", raw_route=self.route()[:-3])
        self.assertRejected("truncated", raw_route=F.disc("route") + struct.pack("<I", 1) + b"\x11")
        self.assertRejected("invalid", raw_route=self.route(steps=(b"\x11\x07\x64\x00\x01",)))  # bool = 7
        self.assertRejected("sum to 100", raw_route=self.route(steps=(b"\x11\x00\x32\x00\x01",)))
        self.assertRejected("direct", raw_route=self.route(steps=(b"\x11\x00\x64\x00\x02",)))
        split = (b"\x11\x01\x3c\x00\x01", b"\x26\x28\x00\x01")       # Whirlpool 60% + MeteoraDlmm 40%
        order, verified = self.run_verify(raw_route=self.route(steps=split))
        self.assertEqual([s["swap"] for s in verified.swap["steps"]], ["Whirlpool", "MeteoraDlmm"])
        self.assertEqual([s["percent"] for s in verified.swap["steps"]], [60, 40])

    def test_exactly_one_route(self):
        self.assertRejected("exactly one Jupiter", jupiter_count=2)


class Programs(Base):
    """F4 and the static allowlist."""

    def test_unknown_static_program(self):
        self.assertRejected("not on the allowlist", static_program=F.EVIL_PROGRAM)

    def test_empty_inner_instructions_rejected(self):                 # N4, review probe P7b
        self.env.chain.inner = []
        self.assertRejected("no Token CPI")

    def test_inner_instructions_must_include_token_cpi_under_jupiter(self):
        self.env.chain.inner = [F.WHIRLPOOL]                             # no Token transfer
        self.assertRejected("no Token CPI")
        self.env.chain.inner = [TOKEN_PROGRAM]
        self.env.chain.inner_index = 0                                   # reported under another instruction
        self.assertRejected("no Token CPI")

    def test_rpc_without_inner_instructions_fails_closed(self):
        self.env.chain.inner = None
        self.assertRejected("innerInstructions")

    def test_inner_program_not_allowlisted(self):
        self.env.chain.inner = [F.WHIRLPOOL, F.EVIL_PROGRAM]
        self.assertRejected("Inner instruction invokes %s" % F.EVIL_PROGRAM)

    def test_executable_account_in_lookup_table(self):
        original = F.build_swap_tx

        def with_program_in_table(*args, **kwargs):
            raw, table = original(*args, **kwargs)
            return raw, table[:2] + [F.EVIL_PROGRAM]
        self.env.chain.executables.add(F.EVIL_PROGRAM)
        F.build_swap_tx = with_program_in_table
        try:
            self.assertRejected("Executable account %s" % F.EVIL_PROGRAM)
        finally:
            F.build_swap_tx = original

    def test_token_2022_accounts_rejected(self):
        self.env.chain.token_2022 = [{"pubkey": F.key("t22"), "account": None}]
        self.assertRejected("Token-2022")


class Structure(Base):
    """F12: duplicate accounts and derived addresses are checked locally."""

    def test_account_loaded_twice(self):                                     # review probe P5
        self.assertRejected("loaded twice", alt_duplicate=True)

    def test_ata_at_non_derived_address(self):                               # review probe P6
        self.assertRejected("derived ATA", ata_address=F.key("attacker-chosen"))

    def test_wrap_to_non_derived_account(self):
        self.assertRejected("own wSOL ATA", side="SELL", transfer_to=F.key("attacker-chosen"))


class DrainOfAnotherToken(Base):
    def chain(self):
        return F.Chain(other=1_000_000)

    def test_other_balance_decrease(self):
        self.env.chain.sim_effect = {"lamports": 124_990_000, USDC.mint: -25_000_000, F.OTHER_MINT: -1}
        self.assertRejected("Decreases another taker balance")


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
