import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jupiter_bot.core import SOL, USDC, Rejected
from jupiter_bot.execution import config, solana_tx as T
from jupiter_bot.execution import mandate as M
from jupiter_bot.execution.http import SafeHTTP, TransportTimeout
from jupiter_bot.execution.jupiter_exec import JupiterExec, make_request
from jupiter_bot.execution.ledger import CONFIRMED, FAILED, INTENT, SIGNED, VERIFIED, Ledger
from jupiter_bot.execution.rpc import Rpc, RpcError
from jupiter_bot.tests import execution_fakes as F
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401


class Base58(unittest.TestCase):
    def test_roundtrip_and_leading_zeros(self):
        for raw in (b"", b"\0", b"\0\0\x01", bytes(range(32)), b"\xff" * 64):
            if raw:
                self.assertEqual(T.b58decode(T.b58encode(raw)), raw)
        self.assertEqual(T.b58encode(b"\0" * 32), T.SYSTEM_PROGRAM)
        self.assertEqual(T.pubkey_bytes(SOL.mint)[:1], b"\x06")

    def test_rejects_bad_input(self):
        for text in ("", "0OIl", "abc!", 5, "1" * 200):
            with self.assertRaises(Rejected):
                T.b58decode(text)
        with self.assertRaises(Rejected):
            T.pubkey_bytes("3yZe7d")          # valid base58, wrong length


class CompactU16(unittest.TestCase):
    VECTORS = [(0, b"\x00"), (0x7F, b"\x7f"), (0x80, b"\x80\x01"), (0x3FFF, b"\xff\x7f"),
               (0x4000, b"\x80\x80\x01"), (0xFFFF, b"\xff\xff\x03")]

    def test_vectors(self):
        for value, raw in self.VECTORS:
            self.assertEqual(T.encode_compact_u16(value), raw)
            self.assertEqual(T.decode_compact_u16(raw, 0), (value, len(raw)))

    def test_rejects_non_canonical_and_overflow(self):
        for raw in (b"\x80\x00", b"\xff\xff\x04", b"\x80", b"\x80\x80\x80\x01"):
            with self.assertRaises(Rejected):
                T.decode_compact_u16(raw, 0)
        with self.assertRaises(Rejected):
            T.encode_compact_u16(0x10000)


class Messages(unittest.TestCase):
    def test_parse_v0_swap_and_resolve_lookups(self):
        raw, table = F.build_swap_tx("SELL", 10**8)
        tx = T.parse_transaction(raw)
        m = tx.message
        self.assertEqual((m.version, m.num_required_signatures, m.fee_payer), (0, 1, F.WALLET))
        self.assertEqual(tx.serialize(), raw)
        metas = T.resolve_accounts(m, {F.ALT: table})
        self.assertEqual([x.key for x in metas[-3:]], F.DEX)
        self.assertEqual([(x.writable, x.from_lookup) for x in metas[-3:]], [(True, True), (True, True), (False, True)])
        self.assertTrue(metas[0].signer and metas[0].writable)
        self.assertFalse(any(x.signer for x in metas[1:]))
        with self.assertRaises(Rejected):
            T.resolve_accounts(m, {F.ALT: table[:2]})       # index outside table
        with self.assertRaises(Rejected):
            T.resolve_accounts(m, {})

    def test_rejects_malformed(self):
        raw, _ = F.build_swap_tx("BUY", 10**6)
        with self.assertRaises(Rejected):
            T.parse_transaction(raw + b"\0")                 # trailing byte
        with self.assertRaises(Rejected):
            T.parse_transaction(raw[:-3])
        v1 = bytearray(raw)
        v1[65] = 0x81
        with self.assertRaises(Rejected):
            T.parse_transaction(bytes(v1))
        with self.assertRaises(Rejected):
            T.parse_transaction(b"\x02" + raw[1:])           # signature count != header
        with self.assertRaises(Rejected):
            T.parse_transaction(raw + b"\0" * 2000)

    def test_with_signature(self):
        raw, _ = F.build_swap_tx("BUY", 10**6)
        tx = T.with_signature(T.parse_transaction(raw), 0, b"\x07" * 64)
        self.assertEqual(T.parse_transaction(tx.serialize()).signatures[0], b"\x07" * 64)
        with self.assertRaises(Rejected):
            T.with_signature(tx, 1, b"\x07" * 64)

    def test_lookup_table_and_token_account(self):
        self.assertEqual(T.parse_lookup_table(F.alt_data(F.DEX)), F.DEX)
        with self.assertRaises(Rejected):
            T.parse_lookup_table(F.alt_data(F.DEX, deactivated=True))
        with self.assertRaises(Rejected):
            T.parse_lookup_table(F.alt_data(F.DEX)[:-1])
        token = T.parse_token_account(F.token_data(USDC.mint, F.WALLET, 42, delegate=F.DEX[0]))
        self.assertEqual((token.mint, token.owner, token.amount, token.delegate), (USDC.mint, F.WALLET, 42, F.DEX[0]))
        with self.assertRaises(Rejected):
            T.parse_token_account(b"\0" * 170)


class DerivedAddresses(unittest.TestCase):
    """F12: create/find_program_address with a pure-Python ed25519 point-validity check."""

    def test_solana_sdk_create_program_address_vectors(self):
        # solana-program pubkey.rs `test_create_program_address`
        program = "BPFLoaderUpgradeab1e11111111111111111111111"
        seed_key = T.pubkey_bytes("SeedPubey1111111111111111111111111111111111")
        for seeds, expected in (([b"", bytes([1])], "BwqrghZA2htAcqq8dzP1WDAhTXYTYWj7CHxF5j7TDBAe"),
                                (["\u2609".encode(), bytes([0])], "13yWmRpaTR4r5nAktwLqMpRNr28tnVUZw26rTvPSSB19"),
                                ([b"Talking", b"Squirrels"], "2fnQrngrQT4SeLcdToJAD96phoEjNL2man2kfRLCASVk"),
                                ([seed_key, bytes([1])], "976ymqVnfE32QFe6NfGDctSvVa36LWnvYxhU6G2232YL")):
            self.assertEqual(T.create_program_address(seeds, program), expected)
        with self.assertRaises(Rejected):
            T.create_program_address([b"x" * 33], program)

    def test_curve_check_against_rfc8032_public_keys(self):
        for hexkey in ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
                       "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
                       "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025"):
            self.assertTrue(T.is_on_curve(bytes.fromhex(hexkey)))
        self.assertTrue(T.is_on_curve(b"\x01" + b"\0" * 31))           # the identity point (0, 1)
        address, bump = T.find_program_address([b"Talking", b"Squirrels"], "BPFLoaderUpgradeab1e11111111111111111111111")
        self.assertFalse(T.is_on_curve(T.pubkey_bytes(address)))
        self.assertEqual(T.create_program_address([b"Talking", b"Squirrels", bytes([bump])],
                                                  "BPFLoaderUpgradeab1e11111111111111111111111"), address)

    def test_ata_is_off_curve_and_deterministic(self):
        ata = T.associated_token_address(F.WALLET, USDC.mint)
        self.assertFalse(T.is_on_curve(T.pubkey_bytes(ata)))
        self.assertNotEqual(ata, T.associated_token_address(F.WALLET, SOL.mint))
        self.assertEqual(ata, F.USDC_ATA)

    def test_uninitialised_token_account_rejected(self):
        with self.assertRaises(Rejected):
            T.parse_token_account(F.token_data(USDC.mint, F.WALLET, 1, state=0))


class Mandates(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = F.Env(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def parse(self, **changes):
        self.env.mandate(**changes)
        return M.parse(self.env.paths.mandate.read_bytes())

    def test_valid_mandate_in_atoms(self):
        m = self.parse(max_trade_usdc="12.5", max_trade_sol="0.093456789")   # 18.69 USDC at 200 <= 1.5 x 12.5
        self.assertEqual((m.max_trade_usdc, m.max_position_usdc, m.daily_loss_limit_usdc), (12_500_000, 50_000_000, 10_000_000))
        self.assertEqual(m.max_trade_sol, 93_456_789)
        self.assertEqual(m.rpc_host, F.RPC_HOST)
        self.assertEqual(M.problems(m, F.NOW, self.env.repo, price=200), [])
        self.assertIn("no journal price", M.problems(m, F.NOW, self.env.repo)[0])     # fail closed
        public = json.dumps(m.public())
        self.assertNotIn("secret-token", public)
        self.assertNotIn("keys", public)

    def test_strict_rejections(self):
        bad = [dict(extra=1), dict(max_trade_usdc=25), dict(max_trade_usdc="25.0000001"),
               dict(max_trade_usdc="60"), dict(max_slippage_bps=301), dict(max_slippage_bps=True),
               dict(allowed_mints=[SOL.mint, F.OTHER_MINT]), dict(allowed_mints=[]),
               dict(strategy="nope"), dict(params={"lookback_min": 241, "rebalance_min": 240}),
               dict(rpc_url="http://rpc.example.org"), dict(rpc_url="https://user:pw@rpc.example.org"),
               dict(rpc_url="https://api.jup.ag/x"), dict(keypair_path="keys/bot.json"),
               dict(wallet_pubkey="not-a-key"), dict(expires_at="2027-01-01"), dict(max_trade_usdc="0.5"),
               dict(max_trade_sol=0.5), dict(max_trade_sol="0.0000000001"), dict(max_trade_sol="0"),
               dict(max_trade_sol=F.DROP)]
        for change in bad:
            with self.assertRaises(Rejected, msg=change):
                self.parse(**change)
        self.env.mandate()
        text = self.env.paths.mandate.read_text()
        with self.assertRaises(Rejected):
            M.parse(text.replace("{", '{"wallet_pubkey": "x", ', 1).encode())   # duplicate key
        data = json.loads(text)
        del data["expires_at"]
        with self.assertRaises(Rejected):
            M.parse(json.dumps(data).encode())

    def test_usage_problems(self):
        m = self.parse(expires_at=F.NOW - 1)
        self.assertIn("mandate expired", M.problems(m, F.NOW, self.env.repo))
        os.chmod(self.env.keypair, 0o644)
        self.assertTrue(any("permissions" in p for p in M.problems(m, F.NOW, self.env.repo)))
        os.chmod(self.env.keypair, 0o600)
        inside = self.env.repo / "bot.json"
        inside.write_text("[]")
        os.chmod(inside, 0o600)
        self.assertTrue(any("inside the repository" in p for p in M.keypair_problems(inside, self.env.repo)))
        link = Path(self.dir.name) / "link.json"
        link.symlink_to(self.env.keypair)
        self.assertTrue(any("symlink" in p for p in M.keypair_problems(link, self.env.repo)))
        self.assertTrue(any("owned" in p for p in M.keypair_problems(self.env.keypair, self.env.repo, uid=12345)))
        self.assertIn("keypair file does not exist", M.keypair_problems("/nonexistent/k.json", self.env.repo))

    def test_max_trade_sol_plausibility(self):                       # N6
        m = self.parse(max_trade_usdc="25", max_trade_sol="0.1875")      # 37.5 USDC at 200 = 1.5 x 25
        self.assertIsNone(M.sol_cap_problem(m, 200))
        m = self.parse(max_trade_usdc="25", max_trade_sol="0.1876")
        self.assertIn("more than 1.5 x", M.sol_cap_problem(m, 200))
        m = self.parse(max_trade_sol="1000")
        self.assertTrue(any("max_trade_sol" in p for p in M.problems(m, F.NOW, self.env.repo, price=200)))
        self.assertIsNone(M.sol_cap_problem(self.parse(max_trade_sol="0.15"), 200))

    def test_tls_trust_ignores_environment(self):                     # F16
        from unittest import mock
        from jupiter_bot.execution import http
        with mock.patch.dict("os.environ", {"SSL_CERT_FILE": "/nonexistent", "SSL_CERT_DIR": "/nonexistent"}):
            if any(__import__("os").path.isfile(p) for p in http.SYSTEM_CA_FILES):
                context = http.tls_context()
                self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
                self.assertEqual(context.verify_mode, __import__("ssl").CERT_REQUIRED)
        with self.assertRaises(Rejected):
            http.tls_context(candidates=("/nonexistent/ca.crt",))

    def test_public_rpc(self):
        for host in ("api.mainnet.solana.com", "api.mainnet-beta.solana.com", "solana.com", "API.Mainnet.Solana.com."):
            self.assertTrue(M.is_public_rpc(host), host)
        for host in ("rpc.example.org", "solana.com.evil.org", "mainnet.helius-rpc.com"):
            self.assertFalse(M.is_public_rpc(host), host)


class Ledgers(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "execution.db"

    def tearDown(self):
        self.dir.cleanup()

    def test_append_only_and_transitions(self):
        ledger = Ledger(self.path)
        order = ledger.create_intent("BUY", USDC.mint, SOL.mint, 5, "sha", {"price": "200"}, 1.0)
        with self.assertRaises(Rejected):
            ledger.create_intent("BUY", USDC.mint, SOL.mint, 5, "sha", {}, 2.0)      # one open order only
        with self.assertRaises(Rejected):
            ledger.transition(order, SIGNED, {}, 2.0)                                 # INTENT -> SIGNED illegal
        ledger.transition(order, VERIFIED, {"min_out": 1}, 2.0)
        ledger.event("note", {}, 2.0)
        for sql in ("UPDATE orders SET in_amount=1", "DELETE FROM order_events", "UPDATE events SET kind='x'"):
            with self.assertRaises(sqlite3.DatabaseError):
                ledger.db.execute(sql)
        ledger.transition(order, FAILED, {"reason": "test"}, 3.0)
        with self.assertRaises(Rejected):
            ledger.transition(order, CONFIRMED, {}, 4.0)                              # terminal stays terminal
        self.assertEqual(ledger.order(order)["state"], FAILED)
        self.assertEqual(ledger.counts(), {"total": 1, "pending": 0, "confirmed": 0, "failed": 1, "unknown": 0})
        self.assertEqual([e["state"] for e in ledger.order(order)["events"]], [INTENT, VERIFIED, FAILED])
        ledger.close()

    def test_average_cost_pnl(self):
        ledger = Ledger(self.path)
        for side, sol, usdc in (("BUY", 100_000_000, -20_000_000), ("SELL", -50_000_000, 12_000_000)):
            order = ledger.create_intent(side, USDC.mint, SOL.mint, 5, "sha", {}, 1.0)
            ledger.transition(order, VERIFIED, {}, 1.0)
            ledger.transition(order, SIGNED, {}, 1.0)
            ledger.transition(order, "SUBMITTED", {}, 1.0)
            ledger.book_fill(order, 86400.0, "SWAP", side, sol, usdc, 5000, 1, "sig" + side, "200", {}, CONFIRMED, {})
        self.assertEqual(ledger.position(), (50_000_000, 10_000_000))
        self.assertEqual(ledger.realized_on("1970-01-02"), 2_000_000)
        ledger.close()

    def book(self, ledger, side, sol, usdc, at, fee=5000):
        order = ledger.create_intent(side, USDC.mint, SOL.mint, 5, "sha", {}, at)
        for state in (VERIFIED, SIGNED, "SUBMITTED"):
            ledger.transition(order, state, {}, at)
        return ledger.book_fill(order, at, "SWAP", side, sol, usdc, fee, 1, "sig%s%s" % (side, at), "200", {},
                                CONFIRMED, {})

    def test_position_follows_insertion_not_the_clock(self):            # F10, review probe E3
        ledger = Ledger(self.path)
        self.book(ledger, "BUY", 100_000_000, -20_000_000, 2000.0)
        self.book(ledger, "BUY", 100_000_000, -20_000_000, 1000.0)       # clock stepped backwards
        self.assertEqual(ledger.position(), (200_000_000, 40_000_000))
        ledger.close()

    def test_full_sell_books_the_fee_beyond_the_position(self):         # F14
        ledger = Ledger(self.path)
        self.book(ledger, "BUY", 100_000_000, -20_000_000, 1.0)
        realized = self.book(ledger, "SELL", -(100_000_000 + 5_000), 21_000_000, 2.0)
        self.assertEqual(ledger.position(), (0, 0))
        self.assertEqual(realized, 1_000_000 - 1_000)                    # 5000 lamports at 200 = 1000 atoms
        ledger.close()

    def test_foreign_database_refused(self):
        db = sqlite3.connect(str(self.path))
        db.execute("CREATE TABLE copybot(x)")
        db.commit()
        db.close()
        with self.assertRaises(Rejected):
            Ledger(self.path)
        with self.assertRaises(Rejected):
            Ledger(self.path, readonly=True)


class Transport(unittest.TestCase):
    def test_allowlist(self):
        http = SafeHTTP(["api.jup.ag"], transport=lambda *a: (200, b"{}"))
        for url in ("http://api.jup.ag/x", "https://evil.org/x", "https://u@api.jup.ag/x"):
            with self.assertRaises(Rejected):
                http.request("GET", url)
        self.assertEqual(http.request("GET", "https://api.jup.ag/x"), (200, {}))
        with self.assertRaises(Rejected):
            http.request("PUT", "https://api.jup.ag/x")
        big = SafeHTTP(["api.jup.ag"], transport=lambda *a: (200, b" " * 5_000_000))
        with self.assertRaises(Rejected):
            big.request("GET", "https://api.jup.ag/x")

    def test_rpc_errors_hide_the_url(self):
        rpc = Rpc(F.RPC_URL, SafeHTTP([F.RPC_HOST], transport=lambda *a: (
            200, b'{"jsonrpc":"2.0","id":1,"error":{"code":-32005,"message":"x"}}')))
        with self.assertRaises(RpcError) as ctx:
            rpc.block_height("finalized")
        self.assertNotIn("secret-token", str(ctx.exception))
        rpc = Rpc(F.RPC_URL, SafeHTTP([F.RPC_HOST], transport=lambda *a: (503, b"")))
        with self.assertRaises(RpcError):
            rpc.block_height("finalized")

    def test_order_parameters_and_execute_unknown(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = F.Env(tmp.name)
        env.mandate()
        mandate = M.parse(env.paths.mandate.read_bytes())
        jupiter = JupiterExec(SafeHTTP(["api.jup.ag"], env.transport), clock=env.clock,
                              monotonic=lambda: 0.0, sleep=lambda s: None)
        order = jupiter.order(make_request("BUY", 25_000_000, mandate), reference_price="200")
        params = env.jupiter.orders[0]
        self.assertEqual((params["taker"], params["slippageBps"], params["excludeRouters"], params["swapMode"]),
                         (F.WALLET, "50", config.EXCLUDED_ROUTERS, "ExactIn"))
        self.assertEqual(params["priorityFeeLamports"], str(config.PRIORITY_CAP_LAMPORTS))
        self.assertEqual(order.out_amount, 125_000_000)

        def timeout(*args):
            raise TransportTimeout("timeout")
        late = JupiterExec(SafeHTTP(["api.jup.ag"], timeout))
        self.assertEqual(late.execute(b"x", "req", "sig").outcome, "UNKNOWN")
        for status, body in ((500, b'{"signature":"sig","error":"x"}'), (200, b'{"status":"Failed","code":-1005}'),
                             (200, b'{"status":"Success","signature":"other"}'), (200, b"not json")):
            answer = JupiterExec(SafeHTTP(["api.jup.ag"], lambda *a, s=status, b=body: (s, b))).execute(b"x", "req", "sig")
            self.assertEqual(answer.outcome, "UNKNOWN", body)
        ok = JupiterExec(SafeHTTP(["api.jup.ag"], lambda *a: (200, b'{"status":"Success","signature":"sig"}')))
        self.assertEqual(ok.execute(b"x", "req", "sig").outcome, "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
