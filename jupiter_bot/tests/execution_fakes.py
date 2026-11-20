"""Fakes for the execution tests: a tiny v0 transaction encoder, a fake chain
behind a fake JSON-RPC, a fake Jupiter /order + /execute, and a fake signer.
Nothing here touches the network; the transport seam is called directly.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import urllib.parse
from pathlib import Path

from jupiter_bot.core import SOL, USDC
from jupiter_bot.execution import config
from jupiter_bot.execution import mandate as mandate_mod
from jupiter_bot.execution.engine import Engine
from jupiter_bot.execution.http import TransportTimeout
from jupiter_bot.execution.ledger import Ledger
from jupiter_bot.execution.solana_tx import (ALT_PROGRAM, ATA_PROGRAM, COMPUTE_BUDGET_PROGRAM, JUPITER_V6_PROGRAM,
                                             SYSTEM_PROGRAM, TOKEN_PROGRAM, b58decode, b58encode,
                                             encode_compact_u16, parse_transaction)

NOW = 1_800_000_000.0
PRICE = 200            # USDC per SOL
RPC_HOST = "rpc.example.org"
RPC_URL = "https://%s/secret-token-123" % RPC_HOST
OTHER_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def key(name):
    return b58encode(hashlib.sha256(name.encode()).digest())


WALLET = key("wallet")
WSOL_ATA, USDC_ATA, OTHER_ATA = key("wsol-ata"), key("usdc-ata"), key("other-ata")
ALT = key("alt")
DEX = [key("dex-a"), key("dex-b"), key("dex-c")]
EVIL_PROGRAM = key("evil-program")
BLOCKHASH = key("blockhash")


# encoder -------------------------------------------------------------------------

def encode_message(num_req, ro_signed, ro_unsigned, keys, blockhash, instructions, lookups=(), v0=True):
    out = bytearray(b"\x80" if v0 else b"")
    out += bytes([num_req, ro_signed, ro_unsigned])
    out += encode_compact_u16(len(keys)) + b"".join(b58decode(k, 32) for k in keys)
    out += b58decode(blockhash, 32)
    out += encode_compact_u16(len(instructions))
    for program, accounts, data in instructions:
        out += bytes([program]) + encode_compact_u16(len(accounts)) + bytes(accounts)
        out += encode_compact_u16(len(data)) + data
    if v0:
        out += encode_compact_u16(len(lookups))
        for table, writable, readonly in lookups:
            out += b58decode(table, 32) + encode_compact_u16(len(writable)) + bytes(writable)
            out += encode_compact_u16(len(readonly)) + bytes(readonly)
    return bytes(out)


def encode_tx(message, num_sigs):
    return encode_compact_u16(num_sigs) + b"\0" * (64 * num_sigs) + message


def alt_data(addresses, deactivated=False):
    meta = struct.pack("<I", 1) + struct.pack("<Q", 5 if deactivated else 2**64 - 1)
    meta += struct.pack("<Q", 0) + b"\0" + b"\0" + b"\0" * 32 + b"\0\0"
    assert len(meta) == 56
    return meta + b"".join(b58decode(a, 32) for a in addresses)


def token_data(mint, owner, amount, delegate=None):
    data = b58decode(mint, 32) + b58decode(owner, 32) + struct.pack("<Q", amount)
    data += (struct.pack("<I", 1) + b58decode(delegate, 32)) if delegate else b"\0" * 36
    data += b"\x01" + b"\0" * 12 + struct.pack("<Q", 0) + b"\0" * 36
    assert len(data) == 165
    return data


def build_swap_tx(side, amount, wallet=WALLET, extra_signer=None, fee_payer=None, alt_program=None,
                  ata_mint=SOL.mint, transfer_to=None, cu_price=1000, cu_limit=300_000, legacy=False,
                  extra_token_ix=None):
    """A Jupiter-like v0 swap: compute budget, wSOL ATA, (wrap), route, close wSOL.

    Returns (tx bytes with zeroed signatures, lookup table addresses)."""
    if fee_payer:
        signers, writable = [fee_payer], [wallet, WSOL_ATA, USDC_ATA]
    else:
        signers, writable = [wallet] + ([extra_signer] if extra_signer else []), [WSOL_ATA, USDC_ATA]
    readonly = [SOL.mint, USDC.mint, SYSTEM_PROGRAM, TOKEN_PROGRAM, ATA_PROGRAM, COMPUTE_BUDGET_PROGRAM,
                JUPITER_V6_PROGRAM]
    if ata_mint not in readonly:
        readonly.append(ata_mint)
    keys = signers + writable + readonly
    i = {k: n for n, k in enumerate(keys)}
    static = len(keys)
    table = DEX + ([alt_program] if alt_program else [])
    lookups = [(ALT, [0, 1], [2] + ([3] if alt_program else []))]
    alt_index = {DEX[0]: static, DEX[1]: static + 1, DEX[2]: static + 2}
    w = i[wallet]
    ixs = [(i[COMPUTE_BUDGET_PROGRAM], [], b"\x02" + struct.pack("<I", cu_limit)),
           (i[COMPUTE_BUDGET_PROGRAM], [], b"\x03" + struct.pack("<Q", cu_price)),
           (i[ATA_PROGRAM], [w, i[WSOL_ATA], w, i[ata_mint], i[SYSTEM_PROGRAM], i[TOKEN_PROGRAM]], b"\x01")]
    if side == "SELL":
        target = alt_index[DEX[0]] if transfer_to == "alt" else i[WSOL_ATA]
        ixs.append((i[SYSTEM_PROGRAM], [w, target], struct.pack("<I", 2) + struct.pack("<Q", amount)))
        ixs.append((i[TOKEN_PROGRAM], [i[WSOL_ATA]], b"\x11"))
    ixs.append((i[JUPITER_V6_PROGRAM], [w, i[WSOL_ATA], i[USDC_ATA], alt_index[DEX[0]], alt_index[DEX[1]],
                                        alt_index[DEX[2]], i[TOKEN_PROGRAM]], b"route-data"))
    if alt_program:
        ixs.append((static + 3, [w], b"evil"))
    if extra_token_ix:
        ixs.append((i[TOKEN_PROGRAM], [i[USDC_ATA], alt_index[DEX[0]], w], extra_token_ix))
    ixs.append((i[TOKEN_PROGRAM], [i[WSOL_ATA], w, w], b"\x09"))
    message = encode_message(len(signers), 0, len(readonly), keys, BLOCKHASH, ixs,
                             [] if legacy else lookups, v0=not legacy)
    return encode_tx(message, len(signers)), table


# fake chain + RPC -------------------------------------------------------------------

class Chain:
    def __init__(self, lamports=1_000_000_000, usdc=100_000_000, other=None):
        self.lamports = lamports
        self.tokens = {USDC_ATA: [USDC.mint, usdc]}
        if other is not None:
            self.tokens[OTHER_ATA] = [OTHER_MINT, other]
        self.height = 1000
        self.alt_addresses = list(DEX)
        self.alt_deactivated = False
        self.sim_effect = None          # override: dict of deltas for simulation only
        self.land_effect = None         # override: dict of deltas when landing
        self.sim_delegate = False
        self.landed = {}                # signature -> record
        self.land_status = "finalized"  # or "confirmed"
        self.land_err = None
        self.calls = []

    @staticmethod
    def default_effect(side, in_amount, out_amount):
        fee = config.BASE_FEE_LAMPORTS + 300
        if side == "BUY":
            return {"lamports": out_amount - fee, USDC.mint: -in_amount}
        return {"lamports": -(in_amount + fee), USDC.mint: out_amount}

    def _accounts(self, lamports, tokens, delegate=False):
        accounts = {WALLET: {"lamports": lamports, "owner": SYSTEM_PROGRAM, "data": b""}}
        for address, (mint, amount) in tokens.items():
            accounts[address] = {"lamports": 2_039_280, "owner": TOKEN_PROGRAM,
                                 "data": token_data(mint, WALLET, amount, WALLET if delegate else None)}
        return accounts

    def apply(self, effect):
        lamports = self.lamports + effect.get("lamports", 0)
        tokens = {a: [m, v] for a, (m, v) in self.tokens.items()}
        for address, (mint, amount) in tokens.items():
            tokens[address][1] = amount + effect.get(mint, 0)
        return lamports, tokens

    def account_json(self, account):
        if account is None:
            return None
        return {"lamports": account["lamports"], "owner": account["owner"], "executable": False,
                "rentEpoch": 0, "space": len(account["data"]),
                "data": [base64.b64encode(account["data"]).decode(), "base64"]}

    def current(self):
        return self._accounts(self.lamports, self.tokens)

    def rpc(self, method, params):
        self.calls.append(method)
        ctx = {"slot": self.height + 500}
        if method == "getBlockHeight":
            commitment = params[0]["commitment"]
            return self.height if commitment == "confirmed" else self.height - 30
        if method == "getAccountInfo":
            if params[0] == ALT:
                return {"context": ctx, "value": self.account_json(
                    {"lamports": 1, "owner": ALT_PROGRAM, "data": alt_data(self.alt_addresses, self.alt_deactivated)})}
            return {"context": ctx, "value": self.account_json(self.current().get(params[0]))}
        if method == "getMultipleAccounts":
            accounts = self.current()
            return {"context": ctx, "value": [self.account_json(accounts.get(a)) for a in params[0]]}
        if method == "getTokenAccountsByOwner":
            if params[1]["programId"] != TOKEN_PROGRAM:
                return {"context": ctx, "value": []}
            accounts = self.current()
            return {"context": ctx, "value": [{"pubkey": a, "account": self.account_json(accounts[a])}
                                              for a in self.tokens]}
        if method == "simulateTransaction":
            tx = parse_transaction(base64.b64decode(params[0]))
            effect = self.sim_effect if self.sim_effect is not None else self._pending_effect
            lamports, tokens = self.apply(effect)
            post = self._accounts(lamports, tokens, self.sim_delegate)
            return {"context": ctx, "value": {"err": None, "logs": ["ok"], "unitsConsumed": 100_000,
                                              "accounts": [self.account_json(post.get(a))
                                                           for a in params[1]["accounts"]["addresses"]],
                                              "_keys": len(tx.message.static_keys)}}
        if method == "getSignatureStatuses":
            record = self.landed.get(params[0][0])
            value = None if record is None else {"slot": record["slot"], "confirmations": None,
                                                 "err": self.land_err, "confirmationStatus": self.land_status}
            return {"context": ctx, "value": [value]}
        if method == "getTransaction":
            record = self.landed.get(params[0])
            if record is None or self.land_status != "finalized":
                return None
            return record["tx_json"]
        raise AssertionError("unexpected RPC method %s" % method)

    _pending_effect = {}

    def land(self, signed_tx, side, in_amount, out_amount):
        tx = parse_transaction(signed_tx)
        signature = b58encode(tx.signatures[0])
        if signature in self.landed:
            return signature
        effect = self.land_effect if self.land_effect is not None else self.default_effect(side, in_amount, out_amount)
        if self.land_err is not None:
            effect = {"lamports": -(config.BASE_FEE_LAMPORTS + 300)}
        pre_l, pre_t = self.lamports, {a: list(v) for a, v in self.tokens.items()}
        self.lamports, self.tokens = self.apply(effect)
        keys = list(tx.message.static_keys)
        pre_bal = [pre_l] + [0] * (len(keys) - 1 + 3)
        post_bal = [self.lamports] + [0] * (len(keys) - 1 + 3)

        def token_balances(tokens):
            out = []
            for address, (mint, amount) in tokens.items():
                index = keys.index(address) if address in keys else len(keys) + 2
                out.append({"accountIndex": index, "mint": mint, "owner": WALLET, "programId": TOKEN_PROGRAM,
                            "uiTokenAmount": {"amount": str(amount), "decimals": 6}})
            return out
        self.landed[signature] = {"slot": self.height + 501, "tx_json": {
            "slot": self.height + 501, "blockTime": int(NOW), "version": 0,
            "meta": {"err": self.land_err, "fee": config.BASE_FEE_LAMPORTS + 300,
                     "preBalances": pre_bal, "postBalances": post_bal,
                     "preTokenBalances": token_balances(pre_t), "postTokenBalances": token_balances(self.tokens),
                     "loadedAddresses": {"writable": DEX[:2], "readonly": DEX[2:3]}},
            "transaction": {"signatures": [signature], "message": {"accountKeys": keys}}}}
        return signature


# fake Jupiter ----------------------------------------------------------------------

class Jupiter:
    def __init__(self, chain):
        self.chain = chain
        self.orders, self.executes = [], []
        self.overrides = {}
        self.tx_options = {}
        self.execute_mode = "ok"       # ok | timeout_landed | timeout_lost | 500_landed | 400 | crash_landed
        self.last = None
        self.price = PRICE
        self.on_order = None
        self.crash_on_order = False

    def order(self, params):
        self.orders.append(params)
        if self.crash_on_order:
            raise Crash("process killed during /order")
        if self.on_order:
            self.on_order()
        side = "BUY" if params["inputMint"] == USDC.mint else "SELL"
        amount = int(params["amount"])
        out = amount * 1000 // self.price if side == "BUY" else amount * self.price // 1000
        slippage = int(params["slippageBps"])
        tx, table = build_swap_tx(side, amount, wallet=params["taker"], **self.tx_options)
        self.chain.alt_addresses = table
        self.chain._pending_effect = Chain.default_effect(side, amount, out)
        payload = {"mode": "manual", "router": "metis", "gasless": False, "taker": params["taker"],
                   "inputMint": params["inputMint"], "outputMint": params["outputMint"],
                   "inAmount": str(amount), "outAmount": str(out),
                   "otherAmountThreshold": str(out * (10_000 - slippage) // 10_000 + 1),
                   "swapMode": "ExactIn", "slippageBps": slippage, "feeBps": 2, "feeMint": SOL.mint,
                   "signatureFeePayer": params["taker"], "prioritizationFeePayer": params["taker"],
                   "rentFeePayer": params["taker"], "transactionVersion": 0,
                   "routePlan": [{"swapInfo": {"inputMint": params["inputMint"], "outputMint": params["outputMint"],
                                               "label": "Whirlpool"}, "bps": 10000}],
                   "transaction": base64.b64encode(tx).decode(), "lastValidBlockHeight": str(self.chain.height + 150),
                   "requestId": "req-%d" % len(self.orders), "guaranteedPrice": True}
        payload.update(self.overrides)
        payload = {k: v for k, v in payload.items() if v is not _DROP}
        self.last = (side, amount, out)
        return 200, payload

    def execute(self, body):
        self.executes.append(body)
        signed = base64.b64decode(body["signedTransaction"])
        side, amount, out = self.last
        mode = self.execute_mode
        if mode in ("ok", "timeout_landed", "500_landed", "crash_landed"):
            signature = self.chain.land(signed, side, amount, out)
        else:
            signature = b58encode(parse_transaction(signed).signatures[0])
        if mode == "crash_landed":
            raise Crash("process killed after /execute reached Jupiter")
        if mode.startswith("timeout"):
            raise TransportTimeout("timeout")
        if mode == "500_landed":
            return 500, {"signature": signature, "error": "internal"}
        if mode == "400":
            return 400, {"error": "bad", "code": -2}
        return 200, {"status": "Success", "signature": signature, "slot": "1", "code": 0}


class Crash(BaseException):
    """Simulates the process dying (not an Exception, so nothing catches it)."""


_DROP = object()
DROP = _DROP


class Transport:
    """The `transport` seam of SafeHTTP: routes to the fakes, records every URL host."""

    def __init__(self, chain, jupiter):
        self.chain, self.jupiter, self.hosts = chain, jupiter, []

    def __call__(self, method, url, body, headers, timeout):
        parts = urllib.parse.urlsplit(url)
        self.hosts.append(parts.hostname)
        if parts.hostname == "api.jup.ag" and parts.path == "/swap/v2/order" and method == "GET":
            params = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
            status, payload = self.jupiter.order(params)
        elif parts.hostname == "api.jup.ag" and parts.path == "/swap/v2/execute" and method == "POST":
            status, payload = self.jupiter.execute(json.loads(body))
        elif parts.hostname == RPC_HOST and method == "POST":
            request = json.loads(body)
            status, payload = 200, {"jsonrpc": "2.0", "id": request["id"],
                                    "result": self.chain.rpc(request["method"], request["params"])}
        else:
            raise AssertionError("unexpected request %s %s" % (method, parts.hostname))
        return status, json.dumps(payload).encode()


class FakeSigner:
    def __init__(self):
        self.calls = []
        self.refuse = None
        self.crash_after = False

    def sign(self, message, bundle):
        from jupiter_bot.execution.signer_client import SignerRefused
        self.calls.append(bundle)
        if self.refuse:
            raise SignerRefused(self.refuse)
        assert bundle["message_sha256"] == hashlib.sha256(message).hexdigest()
        return hashlib.sha512(message).digest()


# environment ----------------------------------------------------------------------

class Env:
    def __init__(self, tmp, chain=None):
        self.tmp = Path(tmp)
        self.repo = self.tmp / "repo"
        (self.repo / "jupiter_bot" / "reviews").mkdir(parents=True)
        self.paths = config.Paths.defaults(mandate=self.tmp / "config" / "mandate.json",
                                           data_dir=self.tmp / "data", journal=self.tmp / "data" / "obs.db",
                                           repo=self.repo)
        self.keypair = self.tmp / "keys" / "bot.json"
        self.keypair.parent.mkdir()
        self.keypair.write_text("[0]")
        os.chmod(self.keypair, 0o600)
        self.chain = chain or Chain()
        self.jupiter = Jupiter(self.chain)
        self.transport = Transport(self.chain, self.jupiter)
        self.signer = FakeSigner()
        self.now = NOW
        self.target = "LONG"
        self.price = PRICE
        self.p2_pass = True
        self._engines = []

    def clock(self):
        return self.now

    def mandate(self, **changes):
        data = {"wallet_pubkey": WALLET, "keypair_path": str(self.keypair), "rpc_url": RPC_URL,
                "max_trade_usdc": "25", "max_position_usdc": "50", "daily_loss_limit_usdc": "10",
                "max_slippage_bps": 50, "allowed_mints": [SOL.mint, USDC.mint], "strategy": "tsmom",
                "params": {"lookback_min": 240, "rebalance_min": 240}, "expires_at": NOW + 30 * 86400}
        data.update(changes)
        self.paths.mandate.parent.mkdir(parents=True, exist_ok=True)
        self.paths.mandate.write_text(json.dumps(data))
        return data

    def verdicts(self, directory):
        if not self.p2_pass:
            return []
        return [{"label": "holdout", "verdict": "PASS", "plan_sha256": "plan", "strategy": "tsmom",
                 "params": {"lookback_min": 240, "rebalance_min": 240}, "_file": "v.json"}]

    def gate_options(self):
        return dict(verdict_loader=self.verdicts, lock_loader=lambda: {"plan_sha256": "plan"},
                    lock_verify=lambda record: [])

    def engine(self, **kwargs):
        options = dict(transport=self.transport, signer=self.signer, clock=self.clock,
                       monotonic=lambda: 0.0, sleep=lambda s: None,
                       snapshot_fn=lambda mandate, now: {"as_of": now, "candles": [{"close": str(self.price),
                                                                                     "end": now - 30}]},
                       target_fn=lambda mandate, snapshot: self.target)
        options.update(self.gate_options())
        options.update(kwargs)
        engine = Engine(self.paths, **options)
        self._engines.append(engine)
        return engine

    def close(self):
        for engine in self._engines:
            engine.close()

    def review(self, text="Verdict: APPROVED\n"):
        self.paths.review.write_text(text)

    def dry_runs(self, count=3):
        ledger = Ledger(self.paths.ledger)
        _, sha = mandate_mod.read(self.paths.mandate)
        for _ in range(count):
            ledger.record_dry_run(sha, True, {"seeded": True}, self.now)
        ledger.close()

    def arm(self, mode="LIVE", overrides=()):
        from jupiter_bot.execution.engine import arm
        ledger = Ledger(self.paths.ledger)
        try:
            phrases = iter(["ARM %s %s" % (mode, WALLET[:8]), "OVERRIDE %s" % ",".join(sorted(overrides))])
            return arm(self.paths, mode, list(overrides), lambda prompt: next(phrases), True, self.now, ledger,
                       self.gate_options(), out=lambda *a: None)
        finally:
            ledger.close()

    def ready_live(self):
        """Mandate + all gates OK + armed LIVE."""
        self.mandate()
        self.review()
        self.dry_runs()
        self.arm()

    def ledger(self):
        return Ledger(self.paths.ledger)

