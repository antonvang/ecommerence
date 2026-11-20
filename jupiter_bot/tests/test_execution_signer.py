"""The restricted signer re-checks everything itself. No real key and no real ed25519
is used: a fake `nacl.signing` stands in, so only the signer's own logic is tested."""
import base64
import hashlib
import struct
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from jupiter_bot.core import SOL, USDC
from jupiter_bot.execution import config, gates
from jupiter_bot.execution import mandate as M
from jupiter_bot.execution import signer as S
from jupiter_bot.execution import solana_tx as T
from jupiter_bot.execution import verify as V
from jupiter_bot.execution.signer_client import MINIMAL_ENV, SIGNER_PATH, SignerRefused, SubprocessSigner
from jupiter_bot.tests import execution_fakes as F
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401


class _VerifyKey:
    def __init__(self, raw):
        self.raw = raw

    def __bytes__(self):
        return self.raw


class _SigningKey:
    def __init__(self, seed):
        assert len(seed) == 32
        self.seed = seed
        self.verify_key = _VerifyKey(hashlib.sha256(b"pk" + seed).digest())

    def sign(self, message):
        return types.SimpleNamespace(signature=hashlib.sha512(self.seed + message).digest())


FAKE_NACL = types.SimpleNamespace(SigningKey=_SigningKey)
SEED = bytes([7] * 32)
PUB = hashlib.sha256(b"pk" + SEED).digest()
WALLET = T.b58encode(PUB)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = F.Env(self.dir.name)
        self.env.keypair.write_text(json.dumps(list(SEED + PUB)))
        os.chmod(self.env.keypair, 0o600)
        self.env.mandate(wallet_pubkey=WALLET)
        self.arm()
        self.registry = str(self.env.paths.wallets)
        self.state = Path(S.state_path(self.registry, WALLET))

    def tearDown(self):
        self.env.close()
        self.dir.cleanup()

    def arm(self, mode="LIVE", wallet=WALLET):
        gates.write_arm(self.env.paths.arm, {"mode": mode, "mandate_sha256": M.read(self.env.paths.mandate)[1],
                                             "wallet_pubkey": wallet, "armed_at": F.NOW, "overrides": []})

    def request(self, side="BUY", amount=25_000_000, min_out=None, message=None, **tx_options):
        if min_out is None:     # the floor the fake route instruction encodes (50 bps)
            quoted = amount * 1000 // F.PRICE if side == "BUY" else amount * F.PRICE // 1000
            min_out = tx_options.get("quoted_out", quoted) * 9950 // 10000
        if message is None:
            raw, _ = F.build_swap_tx(side, amount, wallet=tx_options.pop("wallet", WALLET), **tx_options)
            message = T.parse_transaction(raw).message.raw
        mints = (USDC.mint, SOL.mint) if side == "BUY" else (SOL.mint, USDC.mint)
        bundle = {"message_sha256": hashlib.sha256(message).hexdigest(), "order_id": "o1", "side": side,
                  "input_mint": mints[0], "output_mint": mints[1], "in_amount": amount, "min_out": min_out}
        return {"message_b64": base64.b64encode(message).decode(), "bundle": bundle}, message

    def sign(self, request, now=F.NOW, signing=FAKE_NACL, uid=None):
        return S.handle(request, str(self.env.paths.mandate), str(self.env.paths.arm), self.registry, now,
                        signing, os.getuid() if uid is None else uid)

    def refused(self, text, request=None, **kwargs):
        request = request or self.request()[0]
        with self.assertRaises(S.Refused) as ctx:
            self.sign(request, **kwargs)
        self.assertIn(text, str(ctx.exception))
        return ctx.exception


class Signing(Base):
    def test_signs_after_checks_and_counts(self):
        request, message = self.request()
        signature = self.sign(request)
        self.assertEqual(signature, hashlib.sha512(SEED + message).digest())
        state = json.loads(self.state.read_text())
        self.assertEqual((state["count"], state["notional_usdc_atoms"]), (1, 25_000_000))
        self.sign(request)                                  # same bytes again: not a new trade
        self.assertEqual(json.loads(self.state.read_text())["count"], 1)
        sell, _ = self.request("SELL", 125_000_000)
        self.sign(sell)
        self.assertEqual(json.loads(self.state.read_text())["count"], 2)

    def test_main_protocol_and_no_secret_in_output(self):
        request, _ = self.request()
        out = io.StringIO()
        code = S.main(["--mandate", str(self.env.paths.mandate), "--arm", str(self.env.paths.arm),
                       "--registry", self.registry], io.StringIO(json.dumps(request)), out, FAKE_NACL, F.NOW)
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(len(T.b58decode(json.loads(out.getvalue())["signature"])), 64)
        out = io.StringIO()
        bad = dict(request, bundle=dict(request["bundle"], in_amount=30_000_000))
        code = S.main(["--mandate", str(self.env.paths.mandate), "--arm", str(self.env.paths.arm),
                       "--registry", self.registry], io.StringIO(json.dumps(bad)), out, FAKE_NACL, F.NOW)
        self.assertEqual(code, 4)
        self.assertNotIn(json.dumps(list(SEED)), out.getvalue())
        self.assertNotIn(str(list(SEED)[0:4])[1:-1], out.getvalue())


class Refusals(Base):
    def test_refuses_without_nacl(self):
        self.refused("PyNaCl", signing=None)
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"nacl": None, "nacl.signing": None}):
            self.assertIsNone(S.load_nacl())
            code = S.main(["--mandate", "m", "--arm", "a", "--registry", "r"], io.StringIO("{}"), out)
        self.assertEqual(code, 3)
        self.assertIn("python3-nacl", json.loads(out.getvalue())["error"])

    @unittest.skipIf(importlib.util.find_spec("nacl") is not None, "PyNaCl is installed here")
    def test_real_process_refuses_to_start_without_nacl(self):
        done = subprocess.run([sys.executable, "-I", str(SIGNER_PATH), "--mandate", str(self.env.paths.mandate),
                               "--arm", str(self.env.paths.arm), "--registry", self.registry],
                              input=b"{}", capture_output=True, timeout=30, env=dict(MINIMAL_ENV), cwd="/")
        self.assertEqual(done.returncode, 3)
        self.assertIn("refuses to start", json.loads(done.stdout)["error"])
        self.assertFalse(self.state.exists())

    def test_bad_keypair_file(self):
        os.chmod(self.env.keypair, 0o644)
        self.refused("permissions")
        os.chmod(self.env.keypair, 0o600)
        self.refused("owned", uid=os.getuid() + 1)
        link = self.env.tmp / "link.json"
        link.symlink_to(self.env.keypair)
        self.env.mandate(wallet_pubkey=WALLET, keypair_path=str(link))
        self.arm()
        self.refused("regular file")
        self.assertFalse(self.state.exists())                # refused before counting

    def test_keypair_inside_repo(self):
        self.assertEqual(S.keypair_file_problems(str(self.env.keypair), os.getuid(), str(self.env.tmp)),
                         "keypair file is inside the repository")

    def test_keypair_of_another_wallet(self):
        other = bytes([9] * 32)
        self.env.keypair.write_text(json.dumps(list(other + hashlib.sha256(b"pk" + other).digest())))
        self.refused("does not belong")
        self.env.keypair.write_text("not json")
        self.refused("solana-keygen")

    def test_mismatched_message(self):
        request, _ = self.request()
        other, _ = self.request(cu_price=2000)       # a different message
        self.refused("does not match", request=dict(request, message_b64=other["message_b64"]))

    def test_not_armed_or_other_mandate(self):
        gates.remove_arm(self.env.paths.arm)
        self.refused("not armed")
        self.arm(mode="DRY_RUN")
        self.refused("not armed for LIVE")
        self.arm()
        self.env.mandate(wallet_pubkey=WALLET, max_trade_usdc="20")    # edit after arming
        self.refused("does not match the current mandate")

    def test_expired_mandate(self):
        self.refused("expired", now=F.NOW + 365 * 86400)

    def test_bundle_limits(self):
        request, _ = self.request(amount=26_000_000)
        self.refused("max_trade_usdc", request=request)
        request, _ = self.request("SELL", 600_000_000)                 # 0.6 SOL > max_trade_sol 0.5
        self.refused("max_trade_sol", request=request)
        request, _ = self.request(ix_in_amount=24_000_000)
        self.refused("in_amount differs", request=request)
        request, _ = self.request(ix_slippage=10_000)
        self.refused("slippage", request=request)
        request, _ = self.request(min_out=124_999_999)                  # the engine claims a tighter floor
        self.refused("floor below", request=request)
        request, _ = self.request()
        request["bundle"]["side"] = "SELL"
        self.refused("inconsistent", request=request)

    def test_message_rules(self):
        cases = [("one writable signer", dict(extra_signer=F.key("maker"))),
                 ("fee payer", dict(fee_payer=F.key("gas"))),
                 ("program not in static keys", dict(alt_program=F.EVIL_PROGRAM)),
                 ("priority fee", dict(cu_price=10**7, cu_limit=1_400_000)),
                 ("foreign mint", dict(ata_mint=F.OTHER_MINT)),
                 ("token instruction", dict(extra_token_ix=b"\x03" + bytes(8)))]
        for text, options in cases:
            with self.subTest(options=options):
                request, _ = self.request(**options)
                self.refused(text, request=request)
        raw, _ = F.build_swap_tx("BUY", 25_000_000, wallet=WALLET)
        message = T.parse_transaction(raw).message.raw
        sell_shaped, _ = F.build_swap_tx("SELL", 25_000_000, wallet=WALLET)
        request, _ = self.request(message=T.parse_transaction(sell_shaped).message.raw)   # BUY bundle, wrap ix
        self.refused("system transfer", request=request)
        request, _ = self.request(message=message + b"\0")
        self.refused("trailing", request=request)

    def test_sol_outflow_is_bounded(self):                             # review probes S1-S3
        attacker = F.key("attacker")
        keys = [WALLET, attacker, T.SYSTEM_PROGRAM, T.JUPITER_V6_PROGRAM]

        def drain(transfers, lamports, in_amount):
            ixs = [(2, [0, 1], struct.pack("<I", 2) + struct.pack("<Q", lamports)) for _ in range(transfers)]
            ixs.append((3, [0], F.route_data(in_amount, 25_000_000, 50)))
            return F.encode_message(1, 0, 2, keys, F.BLOCKHASH, ixs, [])
        for transfers, lamports, in_amount in ((1, 125_000_000, 125_000_000), (8, 125_000_000, 125_000_000),
                                               (1, 50 * 10**9, 50 * 10**9)):
            request, _ = self.request("SELL", in_amount, min_out=1, message=drain(transfers, lamports, in_amount))
            with self.subTest(transfers=transfers, lamports=lamports):
                self.refused("", request=request)
        request, _ = self.request("SELL", 125_000_000, min_out=1, message=drain(1, 125_000_000, 125_000_000))
        self.refused("own wSOL", request=request)
        # to the right account, but several transfers summing above the swap input
        request, _ = self.request("SELL", 125_000_000, transfers=3, transfer_lamports=50_000_000)
        self.refused("exceeds the swap input", request=request)
        request, _ = self.request("SELL", 125_000_000, transfers=2)    # 2 x 62.5M = the input: fine
        self.sign(request)

    def test_derived_accounts_and_single_route(self):
        self.refused("derived ATA", request=self.request(ata_address=F.key("not-a-pda"))[0])
        self.refused("exactly one Jupiter", request=self.request(jupiter_count=2)[0])
        self.refused("not an accepted route", request=self.request(variant="route_with_token_ledger")[0])

    def test_keypair_directory_permissions(self):
        os.chmod(self.env.keypair.parent, 0o777)
        try:
            self.refused("keypair directory")
        finally:
            os.chmod(self.env.keypair.parent, 0o700)

    def test_state_file_is_per_wallet_in_the_registry(self):
        self.sign(self.request()[0])
        self.assertEqual(self.state.parent, self.env.paths.wallets)
        self.assertTrue(self.state.name.startswith(WALLET))

    def test_daily_caps(self):
        for i in range(S.MAX_SIGNATURES_PER_DAY):
            request, _ = self.request(amount=1_000_000, cu_price=1000 + i)
            self.sign(request)
        request, _ = self.request(amount=2_000_000, cu_price=999)
        self.refused("count cap", request=request)
        self.sign(request, now=F.NOW + 86400)               # next UTC day resets
        self.state.unlink()
        for i in range(16):                                  # 16 x 25 = 400 = 8 x max_position (50)
            self.sign(self.request(cu_price=5000 + i)[0])
        self.refused("notional cap", request=self.request(amount=1_000_000, cu_price=1)[0])
        self.state.write_text("{broken")
        self.refused("corrupt", request=self.request(cu_price=2)[0])


class Consistency(unittest.TestCase):
    def test_signer_copies_match_engine_constants(self):
        self.assertEqual(set(S.ALLOWED_PROGRAMS), set(V.ALLOWED_PROGRAMS))
        self.assertEqual((S.SOL_MINT, S.USDC_MINT), (SOL.mint, USDC.mint))
        self.assertEqual(S.PRIORITY_CAP_LAMPORTS, config.PRIORITY_CAP_LAMPORTS)
        self.assertEqual(S.DEFAULT_CU_LIMIT, config.DEFAULT_CU_LIMIT)
        self.assertEqual(S.MAX_SIGNATURES_PER_DAY, config.SIGNER_MAX_SIGNATURES_PER_DAY)
        self.assertEqual(S.DAILY_NOTIONAL_FACTOR, config.SIGNER_DAILY_NOTIONAL_FACTOR)
        self.assertEqual(S.MANDATE_KEYS, M.KEYS)
        self.assertEqual(S.USDC_TEXT.pattern, M.USDC_TEXT.pattern)
        self.assertEqual(S.REPO, os.path.realpath(str(config.REPO)))
        self.assertEqual(S.SOL_TEXT.pattern, M.SOL_TEXT.pattern)
        self.assertEqual(S.MAX_FEE_BPS, config.MAX_FEE_BPS)
        from jupiter_bot.execution import jupiter_ix
        self.assertEqual(set(S.JUPITER_ROUTES), set(jupiter_ix.ACCEPTED))
        for wallet in (WALLET, F.WALLET):
            for mint in (SOL.mint, USDC.mint):
                self.assertEqual(S.ata(wallet, mint), T.associated_token_address(wallet, mint))

    def test_signer_is_standalone(self):
        source = SIGNER_PATH.read_text()
        self.assertNotIn("jupiter_bot", "\n".join(l for l in source.splitlines() if l.startswith(("import", "from"))))


class Client(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = F.Env(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_isolated_process_and_minimal_env(self):
        seen = {}

        def runner(cmd, **kwargs):
            seen.update(cmd=cmd, **kwargs)
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"signature": T.b58encode(b"\x05" * 64)}).encode(), b"")
        signer = SubprocessSigner(self.env.paths, runner=runner)
        self.assertEqual(signer.sign(b"msg", {"x": 1}), b"\x05" * 64)
        self.assertEqual(seen["cmd"][1:3], ["-I", str(SIGNER_PATH)])
        self.assertEqual(seen["env"], MINIMAL_ENV)
        self.assertEqual(seen["cwd"], "/")
        self.assertEqual(json.loads(seen["input"])["message_b64"], base64.b64encode(b"msg").decode())

    def test_refusal_and_garbage(self):
        for out, code in ((b'{"error": "refused: not armed"}', 4), (b"garbage", 0), (b'{"signature": "xx"}', 0)):
            signer = SubprocessSigner(self.env.paths, runner=lambda cmd, o=out, c=code, **k:
                                      subprocess.CompletedProcess(cmd, c, o, b""))
            with self.assertRaises(Exception) as ctx:
                signer.sign(b"msg", {})
            self.assertIsInstance(ctx.exception, (SignerRefused, ValueError))

        def slow(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 1)
        with self.assertRaises(SignerRefused):
            SubprocessSigner(self.env.paths, runner=slow).sign(b"msg", {})


if __name__ == "__main__":
    unittest.main()
