"""Engine life cycle against fake Jupiter + fake RPC: ledger-before-send, unknown
outcomes, restart, daily loss stop, kill switch, mandate edits, gate overrides, status."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal

from jupiter_bot.core import USDC, Rejected
from jupiter_bot.dashboard import data as dashboard
from jupiter_bot.execution import __main__ as cli
from jupiter_bot.execution import config, gates
from jupiter_bot.execution import mandate as M
from jupiter_bot.execution.engine import arm, decide, process_lock
from jupiter_bot.execution.ledger import CONFIRMED, EXPIRED, FAILED, INTENT, SIGNED, SUBMITTED, UNKNOWN, VERIFIED
from jupiter_bot.research.strategies import FLAT, LONG
from jupiter_bot.tests import execution_fakes as F
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = F.Env(self.dir.name)

    def tearDown(self):
        self.env.close()
        self.dir.cleanup()

    def states(self, order_id):
        ledger = self.env.ledger()
        try:
            return [e["state"] for e in ledger.order(order_id)["events"]]
        finally:
            ledger.close()


class HappyPath(Base):
    def test_buy_to_confirmed_with_booked_fill(self):
        self.env.ready_live()
        engine = self.env.engine()
        result = engine.run_once()
        self.assertEqual((result["action"], result["state"]), ("ORDER", CONFIRMED))
        self.assertEqual(self.states(result["order_id"]), [INTENT, VERIFIED, SIGNED, SUBMITTED, CONFIRMED])
        fill = engine.ledger().fills()[0]
        self.assertEqual((fill["side"], fill["usdc_delta"], fill["kind"]), ("BUY", -25_000_000, "SWAP"))
        self.assertEqual(fill["sol_delta"], 125_000_000 - 5_300)        # net of the network fee
        self.assertEqual(fill["fee_lamports"], 5_300)
        self.assertEqual(engine.ledger().position(), (124_994_700, 25_000_000))
        # the signer got the verified bytes plus the bundle; /execute got the signed tx
        self.assertEqual(self.env.signer.calls[0]["side"], "BUY")
        self.assertEqual(len(self.env.jupiter.executes), 1)
        status, _ = engine.status()
        self.assertEqual(status["orders"], {"total": 1, "pending": 0, "confirmed": 1, "failed": 0, "unknown": 0})
        # intent was stored before the first network request of the order
        order = engine.ledger().order(result["order_id"])
        self.assertEqual(order["facts"]["request_id"], "req-1")
        self.assertIn("signed_tx_b64", order["facts"])
        self.assertNotIn("secret-token", json.dumps(order, default=str))

    def test_buy_then_sell_books_realised_pnl(self):
        self.env.ready_live()
        engine = self.env.engine()
        engine.run_once()
        self.env.target, self.env.price, self.env.jupiter.price = FLAT, 190, 190   # whole position <= max trade
        result = engine.run_once()
        self.assertEqual(result["state"], CONFIRMED)
        fills = engine.ledger().fills()
        self.assertEqual(fills[1]["side"], "SELL")
        self.assertEqual(engine.ledger().position(), (0, 0))
        # the network fee of the full sell (5_300 lamports beyond the position) is a cost too (F14)
        expected = 124_994_700 * 190 // 1000 - 25_000_000 - (-(-5_300 * 190 // 1000))
        self.assertEqual(fills[1]["realized_pnl_usdc"], expected)
        self.assertAlmostEqual(engine.status()[0]["today_realized_pnl_usdc"], expected / 1e6)

    def test_position_limit_stops_buying(self):
        self.env.ready_live()
        engine = self.env.engine()
        engine.run_once()
        engine.run_once()
        third = engine.run_once()
        self.assertEqual(third["action"], "NONE")
        self.assertIn("max position", third["reason"])
        self.assertEqual(len(self.env.jupiter.orders), 2)


class UnknownOutcomes(Base):
    def setUp(self):
        super().setUp()
        self.env.mandate(max_position_usdc="25")
        self.env.review()
        self.env.dry_runs()
        self.env.arm()

    def test_execute_timeout_then_confirmed(self):
        self.env.jupiter.execute_mode = "timeout_landed"
        self.env.chain.land_status = "confirmed"          # not final yet
        engine = self.env.engine()
        first = engine.run_once()
        self.assertEqual(first["state"], UNKNOWN)
        second = engine.run_once()
        self.assertEqual(second["action"], "WAIT")
        self.assertEqual(len(self.env.jupiter.orders), 1)   # never a second order while UNKNOWN
        self.assertEqual(len(self.env.jupiter.executes), 1)  # and never a blind re-send
        self.env.chain.land_status = "finalized"
        third = engine.run_once()
        self.assertEqual(third["resolved"][0][1], CONFIRMED)
        self.assertEqual(self.states(first["order_id"])[-2:], [UNKNOWN, CONFIRMED])
        self.assertEqual(len(engine.ledger().fills()), 1)
        self.assertEqual(third["action"], "NONE")           # max position reached

    def test_execute_timeout_then_expired(self):
        self.env.jupiter.execute_mode = "timeout_lost"
        engine = self.env.engine()
        first = engine.run_once()
        self.assertEqual(first["state"], UNKNOWN)
        self.env.chain.height += 160                          # past lastValid but inside the safety margin
        self.assertEqual(engine.run_once()["action"], "WAIT")
        self.assertEqual(len(self.env.jupiter.orders), 1)
        self.env.chain.height += 200                          # finalized height > lastValid + margin
        self.env.jupiter.execute_mode = "ok"
        third = engine.run_once()
        self.assertEqual(third["resolved"][0][1], EXPIRED)
        self.assertEqual(self.states(first["order_id"])[-1], EXPIRED)
        self.assertEqual(third["state"], CONFIRMED)          # only now a NEW order was allowed
        self.assertEqual(len(self.env.jupiter.orders), 2)

    def test_http_500_with_signature_is_unknown_until_chain_says(self):
        self.env.jupiter.execute_mode = "500_landed"
        result = self.env.engine().run_once()
        self.assertEqual(self.states(result["order_id"])[-2:], [UNKNOWN, CONFIRMED])

    def test_failed_on_chain_books_fee_only(self):
        self.env.chain.land_err = {"InstructionError": [3, {"Custom": 6001}]}
        engine = self.env.engine()
        result = engine.run_once()
        self.assertEqual(result["state"], FAILED)
        fill = engine.ledger().fills()[0]
        self.assertEqual((fill["kind"], fill["usdc_delta"]), ("FEE_ONLY", 0))
        self.assertLess(fill["realized_pnl_usdc"], 0)
        self.assertEqual(engine.ledger().position(), (0, 0))

    def test_fee_above_verified_is_an_anomaly(self):
        self.env.chain.land_effect = None
        original = F.tx_effect
        F.tx_effect = lambda raw: (lambda e, f: (e, f + 1))(*original(raw))          # chain charges 1 more
        try:
            result = self.env.engine().run_once()
        finally:
            F.tx_effect = original
        self.assertEqual(result["state"], CONFIRMED)
        self.assertFalse(self.env.paths.arm.exists())

    def test_anomalous_fill_is_booked_and_disarms(self):
        self.env.chain.land_effect = {"lamports": 1_000_000, USDC.mint: -25_000_000}   # far below threshold
        engine = self.env.engine()
        result = engine.run_once()
        self.assertEqual(result["state"], CONFIRMED)
        self.assertFalse(self.env.paths.arm.exists())
        self.assertEqual(engine.ledger().events("anomaly_disarmed")[0]["data"]["order_id"], result["order_id"])
        self.assertEqual(engine.status()[0]["mode"], "DISARMED")


class ExpiryEvidence(Base):
    """F5: EXPIRED only on positive evidence; a lagging or history-less RPC keeps the order UNKNOWN."""

    def setUp(self):
        super().setUp()
        self.env.mandate()
        self.env.review()
        self.env.dry_runs()
        self.env.arm()

    def test_history_less_rpc_after_landing_stays_unknown(self):        # review probe E1
        self.env.jupiter.execute_mode = "timeout_landed"
        self.env.chain.land_status = "confirmed"
        engine = self.env.engine()
        first = engine.run_once()
        self.assertEqual(first["state"], UNKNOWN)
        self.env.chain.history = False                                  # the provider forgot it
        self.env.chain.height += 400
        self.env.jupiter.execute_mode = "ok"
        second = engine.run_once()
        self.assertEqual(second["action"], "WAIT")
        self.assertIn("balances changed", second["resolved"][0][1])
        self.assertEqual(self.states(first["order_id"])[-1], UNKNOWN)
        self.assertEqual(len(self.env.jupiter.orders), 1)               # no second BUY
        self.assertEqual(engine.ledger().events("expiry_blocked")[0]["data"]["order_id"], first["order_id"])
        self.env.chain.history, self.env.chain.land_status = True, "finalized"   # a better RPC
        third = engine.run_once()
        self.assertEqual(third["resolved"][0][1], CONFIRMED)

    def test_lagging_status_node_stays_unknown(self):
        self.env.jupiter.execute_mode = "timeout_lost"
        engine = self.env.engine()
        first = engine.run_once()
        self.env.chain.height += 400
        self.env.chain.status_lag = 100                                 # answer older than the finalized slot
        second = engine.run_once()
        self.assertIn("older than the finalized", second["resolved"][0][1])
        self.assertEqual(self.states(first["order_id"])[-1], UNKNOWN)
        self.env.chain.status_lag = 0
        third = engine.run_once()
        self.assertEqual(third["resolved"][0][1], EXPIRED)
        expired = engine.ledger().order(first["order_id"])["events"][-1]["data"]
        self.assertGreaterEqual(expired["status_context_slot"], expired["finalized_slot"])

    def test_found_via_history_only_is_booked(self):
        self.env.jupiter.execute_mode = "timeout_landed"
        self.env.chain.land_status = "confirmed"
        engine = self.env.engine()
        first = engine.run_once()
        self.env.chain.height += 400
        self.env.chain.land_status = "finalized"
        status = self.env.chain.rpc
        self.env.chain.rpc = lambda m, p: ({"context": {"slot": 10**6}, "value": [None]}
                                           if m == "getSignatureStatuses" else status(m, p))
        engine.run_once()
        self.assertEqual(self.states(first["order_id"])[-1], CONFIRMED)

    def test_force_expire_needs_phrase_and_chain_proof(self):
        from jupiter_bot.execution.engine import force_expire
        self.env.jupiter.execute_mode = "timeout_lost"
        engine = self.env.engine()
        order_id = engine.run_once()["order_id"]
        with self.assertRaises(Rejected):
            force_expire(engine, order_id, lambda p: "EXPIRE %s" % order_id[:8], True)     # can still land
        self.env.chain.height += 400
        with self.assertRaises(Rejected):
            force_expire(engine, order_id, lambda p: "EXPIRE %s" % order_id[:8], False)    # no terminal
        with self.assertRaises(Rejected):
            force_expire(engine, order_id, lambda p: "yes", True)
        self.assertEqual(force_expire(engine, order_id, lambda p: "EXPIRE %s" % order_id[:8], True),
                         [(order_id, EXPIRED)])


class WalletWide(Base):
    """F7: one wallet = one ledger and one lock, whatever --data-dir says."""

    def test_second_data_dir_cannot_trade_the_same_wallet(self):        # review probe E2
        self.env.ready_live()
        self.env.jupiter.execute_mode = "timeout_lost"
        a = self.env.engine()
        self.assertEqual(a.run_once()["state"], UNKNOWN)
        other = config.Paths.defaults(mandate=self.env.paths.mandate, data_dir=self.env.tmp / "data2",
                                      journal=self.env.paths.journal, repo=self.env.repo,
                                      wallets=self.env.paths.wallets)
        b = self.env.engine()
        b.paths = other
        for _ in range(3):
            b.dry_run_once()
        status, state = b.status()
        self.assertEqual(status["mode"], "DISARMED")
        self.assertIn("not bound to this ledger", state.reason)
        self.env.jupiter.execute_mode = "ok"
        self.assertEqual(b.run_once()["action"], "NONE")
        with self.assertRaises(Rejected):                               # and it cannot re-arm itself there
            from jupiter_bot.execution.engine import arm as arm_fn
            from jupiter_bot.execution.ledger import Ledger
            ledger = Ledger(other.ledger)
            try:
                arm_fn(other, "LIVE", [], lambda p: "ARM LIVE %s" % F.WALLET[:8], True, F.NOW, ledger,
                       self.env.gate_options(), out=lambda *x: None)
            finally:
                ledger.close()

    def test_wallet_lock_is_shared_across_data_dirs(self):
        self.env.mandate()
        with process_lock(self.env.paths.wallet_lock(F.WALLET)):
            with self.assertRaises(Rejected):
                self.env.engine().dry_run_once()


class Restart(Base):
    def setUp(self):
        super().setUp()
        self.env.mandate(max_position_usdc="25")
        self.env.review()
        self.env.dry_runs()
        self.env.arm()

    def test_crash_after_send_resumes_from_ledger(self):
        self.env.jupiter.execute_mode = "crash_landed"
        with self.assertRaises(F.Crash):
            self.env.engine().run_once()
        ledger = self.env.ledger()
        (row,) = ledger.non_terminal()
        self.assertEqual(row["state"], SIGNED)
        ledger.close()
        with process_lock(self.env.paths.lock):     # the crashed run released its lock
            pass
        restarted = self.env.engine()               # new process: nothing in flight
        result = restarted.run_once()
        self.assertEqual(self.states(row["order_id"])[-3:], [SIGNED, UNKNOWN, CONFIRMED])
        self.assertEqual(len(self.env.jupiter.executes), 1)  # the restart never re-sent it
        self.assertEqual(result["action"], "NONE")

    def test_crash_before_signing_is_abandoned(self):
        self.env.jupiter.crash_on_order = True
        with self.assertRaises(F.Crash):
            self.env.engine().run_once()
        ledger = self.env.ledger()
        (row,) = ledger.non_terminal()
        self.assertEqual(row["state"], INTENT)
        ledger.close()
        self.env.jupiter.crash_on_order = False
        result = self.env.engine().run_once()
        self.assertEqual(self.states(row["order_id"]), [INTENT, FAILED])
        self.assertEqual(result["state"], CONFIRMED)

    def test_execute_redirect_is_unknown_not_a_crash(self):                # review probe E4
        def redirect(body):
            self.env.jupiter.executes.append(body)
            raise Rejected("Redirect rejected; no alternate endpoint is allowed")
        self.env.jupiter.execute = redirect
        result = self.env.engine().run_once()
        self.assertEqual(result["state"], UNKNOWN)

    def test_second_process_is_locked_out(self):
        with process_lock(self.env.paths.lock):
            with self.assertRaises(Rejected):
                self.env.engine().run_once()


class SignatureCheck(unittest.TestCase):
    """The engine's own PyNaCl check, with and without nacl importable (F9)."""

    def test_default_verifier(self):
        import types
        from unittest import mock
        from jupiter_bot.execution.engine import _verify_signature

        class BadSignatureError(Exception):
            pass

        class VerifyKey:
            def __init__(self, raw):
                self.raw = raw

            def verify(self, message, signature):
                if signature != b"good" * 16:
                    raise BadSignatureError()
        signing = types.SimpleNamespace(VerifyKey=VerifyKey)
        exceptions = types.SimpleNamespace(BadSignatureError=BadSignatureError)
        nacl = types.SimpleNamespace(signing=signing, exceptions=exceptions)
        with mock.patch.dict(sys.modules, {"nacl": nacl, "nacl.signing": signing, "nacl.exceptions": exceptions}):
            _verify_signature(F.WALLET, b"m", b"good" * 16)
            with self.assertRaises(Rejected):
                _verify_signature(F.WALLET, b"m", b"bad!" * 16)
        with mock.patch.dict(sys.modules, {"nacl": None, "nacl.signing": None, "nacl.exceptions": None}):
            self.assertIsNone(_verify_signature(F.WALLET, b"m", b"anything"))


class Limits(Base):
    def test_daily_loss_stop_blocks_buy_but_not_sell(self):
        self.env.ready_live()
        engine = self.env.engine()
        engine.run_once()                                          # BUY 25 USDC at 200
        self.env.target, self.env.price, self.env.jupiter.price = FLAT, 100, 100
        engine.run_once()                                          # SELL at 100: about -12.5 USDC
        self.assertLess(engine.ledger().realized_on("2027-01-15"), -10_000_000)
        self.env.target, self.env.price, self.env.jupiter.price = LONG, 100, 100
        result = engine.run_once()
        self.assertEqual(result["action"], "NONE")
        self.assertIn("daily loss limit", result["reason"])
        self.env.now += 86400                                      # next UTC day
        self.assertEqual(self.env.engine().run_once()["state"], CONFIRMED)

    def test_decide_rules(self):
        self.env.mandate()
        m = M.parse(self.env.paths.mandate.read_bytes())
        price = Decimal(200)
        loss = -m.daily_loss_limit_usdc
        self.assertEqual(decide(m, LONG, price, 0, 0, 10**9, 10**8, loss)["side"], None)
        sell = decide(m, FLAT, price, 125_000_000, 25_000_000, 10**9, 0, loss)
        self.assertEqual((sell["side"], sell["amount"]), ("SELL", 125_000_000))   # selling is allowed after the stop
        big = decide(m, FLAT, price, 500_000_000, 50_000_000, 10**9, 0, 0)
        self.assertEqual(big["amount"], 125_000_000)                               # capped at max_trade
        self.assertEqual(decide(m, LONG, price, 0, 0, 10**9, 10**8, 0)["amount"], 25_000_000)
        self.assertEqual(decide(m, LONG, price, 0, 0, 10**9, 5_000_000, 0)["amount"], 5_000_000)
        self.assertIsNone(decide(m, LONG, price, 0, 0, config.SOL_RESERVE_LAMPORTS - 1, 10**8, 0)["side"])
        self.assertEqual(decide(m, LONG, price, 200_000_000, 40_000_000, 10**9, 10**8, 0)["amount"], 10_000_000)
        self.assertIsNone(decide(m, LONG, price, 250_000_000, 40_000_000, 10**9, 10**8, 0)["side"])   # value 50 = max
        partial = decide(m, LONG, price, 150_000_000, 30_000_000, 10**9, 10**8, 0)
        self.assertEqual(partial["amount"], 20_000_000)
        with self.assertRaises(Rejected):
            decide(m, "SHORT", price, 0, 0, 0, 0, 0)


class KillSwitch(Base):
    def test_disarm_between_cycles(self):
        self.env.ready_live()
        engine = self.env.engine()
        engine.run_once()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--mandate", str(self.env.paths.mandate), "--data-dir",
                                       str(self.env.paths.ledger.parent), "disarm"]), 0)
        result = engine.run_once()
        self.assertEqual((result["mode"], result["action"]), ("DISARMED", "NONE"))
        self.assertEqual(len(self.env.jupiter.orders), 1)
        self.assertEqual(engine.ledger().events("disarm")[0]["data"], {"removed": True})

    def test_disarm_during_order_stops_before_signing(self):
        self.env.ready_live()
        self.env.jupiter.on_order = lambda: gates.remove_arm(self.env.paths.arm)
        result = self.env.engine().run_once()
        self.assertEqual(result["state"], FAILED)
        self.assertEqual(self.env.signer.calls, [])
        self.assertIn("disarmed before signing", self.env.engine().ledger().order(result["order_id"])["facts"]["reason"])

    def test_disarm_after_signing_is_never_sent(self):
        self.env.ready_live()
        sign = self.env.signer.sign

        def sign_then_disarm(message, bundle):
            signature = sign(message, bundle)
            gates.remove_arm(self.env.paths.arm)
            return signature
        self.env.signer.sign = sign_then_disarm
        engine = self.env.engine()
        result = engine.run_once()
        # not sent, but kept open until it provably expired: no new order meanwhile (F13 follow-up)
        self.assertEqual(self.states(result["order_id"]), [INTENT, VERIFIED, SIGNED, UNKNOWN])
        self.assertEqual(self.env.jupiter.executes, [])
        self.env.chain.height += 400
        engine.run_once()
        self.assertEqual(self.states(result["order_id"])[-1], EXPIRED)
        self.assertEqual(len(self.env.jupiter.orders), 1)                # still disarmed: nothing new

    def test_mandate_change_disarms(self):
        self.env.ready_live()
        self.env.mandate(max_trade_usdc="20")
        status, state = self.env.engine().status()
        self.assertEqual(status["mode"], "DISARMED")
        self.assertIn("another mandate version", state.reason)
        self.assertEqual(self.env.engine().run_once()["action"], "NONE")
        self.assertEqual(self.env.jupiter.orders, [])

    def test_failing_gate_after_arming_disarms(self):
        self.env.ready_live()
        self.env.paths.review.write_text("Verdict: CHANGES REQUESTED\n")
        status, state = self.env.engine().status()
        self.assertEqual(status["mode"], "DISARMED")
        self.assertIn("review_done", state.reason)

    def test_signer_refusal_fails_the_order(self):
        self.env.ready_live()
        self.env.signer.refuse = "daily signature count cap reached"
        result = self.env.engine().run_once()
        self.assertEqual(result["state"], FAILED)
        self.assertEqual(self.env.jupiter.executes, [])

    def test_disarmed_by_default(self):
        self.env.mandate()
        status, state = self.env.engine().status()
        self.assertEqual((status["mode"], status["armed"]), ("DISARMED", False))
        self.assertEqual(self.env.engine().run_once()["action"], "NONE")
        self.assertEqual(self.env.transport.hosts, [])        # disarmed: no network at all


class Arming(Base):
    def setUp(self):
        super().setUp()
        self.env.mandate()
        self.env.dry_runs()

    def test_failing_gates_need_explicit_override(self):
        self.env.p2_pass = False
        with self.assertRaises(Rejected) as ctx:
            self.env.arm()
        self.assertIn("p2_holdout_pass", str(ctx.exception))
        self.assertIn("review_done", str(ctx.exception))
        self.assertFalse(self.env.paths.arm.exists())
        record = self.env.arm(overrides=("review_done", "p2_holdout_pass"))
        self.assertEqual(record["overrides"], ["p2_holdout_pass", "review_done"])
        status, _ = self.env.engine().status()
        self.assertEqual(status["mode"], "LIVE")
        details = {g["name"]: g["detail"] for g in status["gates"]}
        self.assertTrue(details["review_done"].startswith("OVERRIDDEN"))
        self.assertTrue(details["p2_holdout_pass"].startswith("OVERRIDDEN"))
        self.assertFalse({g["name"]: g["ok"] for g in status["gates"]}["review_done"])   # still shown as failing
        ledger = self.env.ledger()
        self.assertEqual(sorted(e["data"]["gate"] for e in ledger.events("override")), ["p2_holdout_pass", "review_done"])
        ledger.close()

    def test_never_overridable(self):
        for gate in ("mandate_valid", "private_rpc", "nonsense"):
            with self.assertRaises(Rejected):
                self.env.arm(overrides=(gate,))
        self.env.mandate(rpc_url="https://api.mainnet.solana.com")
        self.env.review()
        with self.assertRaises(Rejected) as ctx:
            self.env.arm()
        self.assertIn("private_rpc", str(ctx.exception))
        self.env.mandate(expires_at=F.NOW - 1)
        with self.assertRaises(Rejected):
            self.env.arm(overrides=("dry_run_ok",))

    def test_phrases_and_terminal_required(self):
        self.env.review()
        ledger = self.env.ledger()
        try:
            with self.assertRaises(Rejected):
                arm(self.env.paths, "LIVE", [], lambda p: "yes", True, F.NOW, ledger, self.env.gate_options(),
                    out=lambda *a: None)
            with self.assertRaises(Rejected):
                arm(self.env.paths, "LIVE", [], lambda p: "ARM LIVE %s" % F.WALLET[:8], False, F.NOW, ledger,
                    self.env.gate_options(), out=lambda *a: None)
            self.env.p2_pass = False
            answers = iter(["ARM LIVE %s" % F.WALLET[:8], "OVERRIDE wrong"])
            with self.assertRaises(Rejected):
                arm(self.env.paths, "LIVE", ["p2_holdout_pass"], lambda p: next(answers), True, F.NOW, ledger,
                    self.env.gate_options(), out=lambda *a: None)
        finally:
            ledger.close()
        self.assertFalse(self.env.paths.arm.exists())

    def test_arm_file_is_private_and_bound_to_mandate(self):
        self.env.review()
        self.env.arm()
        self.assertEqual(self.env.paths.arm.stat().st_mode & 0o777, 0o600)
        record, _ = gates.read_arm(self.env.paths.arm)
        self.assertEqual(record["mandate_sha256"], M.read(self.env.paths.mandate)[1])

    def test_dry_run_mode_never_signs(self):
        self.env.arm(mode="DRY_RUN")
        engine = self.env.engine()
        result = engine.run_once()
        self.assertEqual((result["mode"], result["action"], result["ok"]), ("DRY_RUN", "DRY_RUN", True))
        self.assertEqual((self.env.signer.calls, self.env.jupiter.executes), ([], []))
        self.assertEqual(engine.ledger().counts()["total"], 0)
        self.assertEqual(engine.ledger().dry_runs_ok(M.read(self.env.paths.mandate)[1]), 4)


class DryRun(Base):
    def test_dry_run_once_records_and_feeds_the_gate(self):
        self.env.mandate()
        engine = self.env.engine()
        for _ in range(3):
            self.assertTrue(engine.dry_run_once()["ok"])
        self.assertTrue(engine.status()[1].gate("dry_run_ok")["ok"])
        self.assertEqual(self.env.signer.calls, [])
        self.assertEqual(self.env.jupiter.executes, [])
        self.assertEqual(self.env.jupiter.orders[0]["taker"], F.WALLET)

    def test_dry_run_records_decoded_instruction_for_review(self):
        self.env.mandate()
        detail = self.env.engine().dry_run_once()["detail"]
        self.assertEqual(detail["jupiter_instruction"]["variant"], "route")
        self.assertEqual(detail["jupiter_instruction"]["in_amount"], detail["amount"])
        self.assertEqual(detail["expected_fee"], 5_300)
        self.assertIn(F.WHIRLPOOL, detail["inner_programs"])
        self.env.jupiter.tx_options = {"variant": "route_v2"}
        failed = self.env.engine().dry_run_once()["detail"]
        self.assertIn(F.disc("route_v2").hex(), failed["error"])        # Anton sees which variant Jupiter used

    def test_dry_run_probe_when_no_trade_needed_and_failure_recorded(self):
        self.env.mandate()
        self.env.target = FLAT
        engine = self.env.engine()
        result = engine.dry_run_once()
        self.assertTrue(result["detail"]["probe"])
        self.env.jupiter.overrides = {"gasless": True}
        failed = engine.dry_run_once()
        self.assertFalse(failed["ok"])
        self.assertIn("Gasless", failed["detail"]["error"])
        self.assertEqual(engine.ledger().dry_runs_ok(M.read(self.env.paths.mandate)[1]), 1)

    def test_dry_run_needs_valid_mandate_and_private_rpc(self):
        with self.assertRaises(Rejected):
            self.env.engine().dry_run_once()
        self.env.mandate(rpc_url="https://api.mainnet-beta.solana.com")
        with self.assertRaises(Rejected):
            self.env.engine().dry_run_once()


class Status(Base):
    KEYS = {"armed", "mode", "mandate", "gates", "orders", "today_realized_pnl_usdc"}

    def check_shape(self, status):
        self.assertEqual(set(status), self.KEYS)
        self.assertIn(status["mode"], ("DISARMED", "DRY_RUN", "LIVE"))
        self.assertIsInstance(status["armed"], bool)
        self.assertEqual([g["name"] for g in status["gates"]], list(gates.GATES))
        for gate in status["gates"]:
            self.assertEqual(set(gate), {"name", "ok", "detail"})
            self.assertIsInstance(gate["ok"], bool)
        self.assertEqual(set(status["orders"]), {"total", "pending", "confirmed", "failed", "unknown"})
        self.assertTrue(all(type(v) is int for v in status["orders"].values()))
        self.assertIsInstance(status["today_realized_pnl_usdc"], float)
        if status["mandate"] is not None:
            self.assertEqual(set(status["mandate"]), {"wallet_pubkey", "max_position_usdc", "max_trade_usdc",
                                                      "daily_loss_limit_usdc", "allowed_mints", "expires_at"})
        json.dumps(status, allow_nan=False)

    def cli_status(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--mandate", str(self.env.paths.mandate), "--data-dir",
                             str(self.env.paths.ledger.parent), "status", "--json"])
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def test_shape_without_anything(self):
        status = self.cli_status()
        self.check_shape(status)
        self.assertEqual((status["mode"], status["mandate"]), ("DISARMED", None))
        self.assertFalse(self.env.paths.ledger.exists())           # status never creates the ledger

    def test_shape_live_and_dashboard_accepts_it(self):
        self.env.ready_live()
        self.env.engine().run_once()
        status, _ = self.env.engine().status()
        self.check_shape(status)
        self.assertEqual(status["mandate"]["max_trade_usdc"], 25.0)
        text = json.dumps(status)
        self.assertNotIn("secret-token", text)
        self.assertNotIn(str(self.env.keypair), text)
        paths = dashboard.Paths.defaults(journal=self.env.paths.journal, data_dir=self.env.paths.ledger.parent,
                                         mandate=self.env.paths.mandate, repo=self.env.repo)
        (self.env.repo / "jupiter_bot" / "execution").mkdir(parents=True, exist_ok=True)
        view = dashboard.execution(paths, F.NOW, runner=lambda p: json.loads(json.dumps(status)))
        self.assertEqual((view["mode"], view["armed"], view["orders"]["confirmed"]), ("LIVE", True, 1))
        self.assertEqual([g["name"] for g in view["gates"]], list(gates.GATES))
        self.check_shape(self.cli_status())

    def test_invalid_mandate_shows_reason_not_contents(self):
        self.env.mandate(extra_secret="hunter2")
        status = self.cli_status()
        self.assertIsNone(status["mandate"])
        self.assertIn("Unknown mandate keys", status["gates"][1]["detail"])
        self.assertNotIn("hunter2", json.dumps(status))

    def test_module_entry_point(self):
        done = subprocess.run([sys.executable, "-m", "jupiter_bot.execution", "--mandate",
                               str(self.env.paths.mandate), "--data-dir", str(self.env.paths.ledger.parent),
                               "status", "--json"], capture_output=True, timeout=60,
                              cwd=str(config.REPO), stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.check_shape(json.loads(done.stdout))


if __name__ == "__main__":
    unittest.main()
