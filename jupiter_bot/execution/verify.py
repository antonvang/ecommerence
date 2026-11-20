"""Verify the actual `/order` transaction before anything signs it. Default: reject.

1. Decode the versioned transaction (v0 only); exactly one required signature,
   and it is the mandate wallet (= fee payer = transaction id owner).
2. Resolve every address lookup table via `getAccountInfo` (owner must be the
   ALT program, table must be active) and rebuild the full account list.
3. Every top-level program is static (not from a table) and on the allowlist:
   System, ComputeBudget, SPL Token, Associated Token Account, Jupiter v6.
   Instructions of System/Token/ATA/ComputeBudget are decoded and limited to the
   few shapes a swap needs; Jupiter v6 data is not decoded (no public IDL), its
   effect is checked by simulation instead.
4. The blockhash still has headroom before `lastValidBlockHeight`.
5. `simulateTransaction` (sigVerify false) returns the post-state of the taker's
   SOL account and all of its token accounts; the deltas must show: spend <=
   intended input (+ fee cap for SOL), receive >= otherAmountThreshold (- fee cap
   when receiving SOL), no other balance decreases, no owner/delegate/close
   authority change on any taker token account.
"""
from __future__ import annotations

import base64
import hashlib
import struct
from dataclasses import dataclass

from ..core import SOL, USDC, Rejected
from . import config
from .solana_tx import (ALT_PROGRAM, ATA_PROGRAM, COMPUTE_BUDGET_PROGRAM, JUPITER_V6_PROGRAM, SYSTEM_PROGRAM,
                        TOKEN_2022_PROGRAM, TOKEN_PROGRAM, parse_lookup_table, parse_token_account,
                        parse_transaction, resolve_accounts)

ALLOWED_PROGRAMS = (SYSTEM_PROGRAM, COMPUTE_BUDGET_PROGRAM, TOKEN_PROGRAM, ATA_PROGRAM, JUPITER_V6_PROGRAM)
TOKEN_SYNC_NATIVE, TOKEN_CLOSE_ACCOUNT = 17, 9
SYSTEM_TRANSFER = 2


@dataclass(frozen=True)
class Verified:
    message_bytes: bytes
    message_sha256: str
    priority_lamports: int
    block_height: int
    created_atas: dict
    deltas: dict             # {"sol": int, mint: int, ...}
    sim_slot: int
    lookups: dict


def compute_budget(instructions):
    """(priority lamports upper bound). Rejects unknown or repeated ComputeBudget instructions."""
    seen, limit, price = set(), None, 0
    for ix in instructions:
        data = ix.data
        if ix.accounts or not data:
            raise Rejected("Malformed ComputeBudget instruction")
        kind = data[0]
        if kind in seen:
            raise Rejected("Repeated ComputeBudget instruction")
        seen.add(kind)
        if kind == 1 and len(data) == 5:             # RequestHeapFrame
            continue
        if kind == 2 and len(data) == 5:             # SetComputeUnitLimit
            limit, = struct.unpack_from("<I", data, 1)
        elif kind == 3 and len(data) == 9:           # SetComputeUnitPrice (micro-lamports)
            price, = struct.unpack_from("<Q", data, 1)
        elif kind == 4 and len(data) == 5:           # SetLoadedAccountsDataSizeLimit
            continue
        else:
            raise Rejected("Unknown ComputeBudget instruction %d" % kind)
    limit = config.DEFAULT_CU_LIMIT if limit is None else limit
    priority = -(-price * limit // 1_000_000)
    if priority > config.PRIORITY_CAP_LAMPORTS:
        raise Rejected("Priority fee %d lamports exceeds the cap %d" % (priority, config.PRIORITY_CAP_LAMPORTS))
    return priority


def resolve_lookups(message, rpc):
    tables = {}
    for lookup in message.lookups:
        if lookup.table in tables:
            continue
        account = rpc.account_info(lookup.table)
        if account is None:
            raise Rejected("Lookup table %s does not exist" % lookup.table)
        if account["owner"] != ALT_PROGRAM:
            raise Rejected("Lookup table %s is not owned by the ALT program" % lookup.table)
        tables[lookup.table] = parse_lookup_table(account["data"])
    return tables


def check_instructions(message, metas, wallet, request, taker_accounts):
    """Static rules on top-level instructions. `taker_accounts`: address -> TokenAccount (pre-state)."""
    keys = [m.key for m in metas]
    static = len(message.static_keys)
    swap_mints = (request.input_mint, request.output_mint)
    budget, created, jupiter = [], {}, 0
    for ix in message.instructions:
        if ix.program_index >= static:
            raise Rejected("Program %s is loaded from a lookup table" % keys[ix.program_index])
        program = keys[ix.program_index]
        if program not in ALLOWED_PROGRAMS:
            raise Rejected("Program %s is not on the allowlist" % program)
        if program == ATA_PROGRAM:
            accts = [keys[i] for i in ix.accounts]
            if ix.data not in (b"", b"\x00", b"\x01") or len(accts) < 6:
                raise Rejected("Unexpected associated-token-account instruction")
            payer, ata, owner, mint, system, token = accts[:6]
            if payer != wallet or owner != wallet:
                raise Rejected("Token account created for or paid by another wallet")
            if mint not in swap_mints:
                raise Rejected("Token account created for a mint outside the swap")
            if system != SYSTEM_PROGRAM or token != TOKEN_PROGRAM:
                raise Rejected("Token account uses an unexpected program")
            created[ata] = mint
    wsol = {a for a, m in created.items() if m == SOL.mint}
    wsol |= {a for a, t in taker_accounts.items() if t.mint == SOL.mint}
    mine = set(created) | set(taker_accounts)
    transferred = 0
    for ix in message.instructions:
        program = keys[ix.program_index]
        accts = [keys[i] for i in ix.accounts]
        if program == COMPUTE_BUDGET_PROGRAM:
            budget.append(ix)
        elif program == JUPITER_V6_PROGRAM:
            jupiter += 1
        elif program == SYSTEM_PROGRAM:
            if len(ix.data) != 12 or struct.unpack_from("<I", ix.data, 0)[0] != SYSTEM_TRANSFER or len(accts) < 2:
                raise Rejected("Only System transfers (SOL wrapping) are allowed")
            source, target = accts[:2]
            lamports, = struct.unpack_from("<Q", ix.data, 4)
            if request.input_mint != SOL.mint or source != wallet or target not in wsol:
                raise Rejected("System transfer is not a wrap into the taker's own wSOL account")
            transferred += lamports
        elif program == TOKEN_PROGRAM:
            kind = ix.data[0] if len(ix.data) == 1 else None
            if kind == TOKEN_SYNC_NATIVE and accts and accts[0] in wsol:
                continue
            if kind == TOKEN_CLOSE_ACCOUNT and len(accts) >= 3 and accts[0] in mine \
                    and accts[1] == wallet and accts[2] == wallet:
                continue
            raise Rejected("Token instruction other than SyncNative/CloseAccount on own accounts")
    if transferred > request.amount:
        raise Rejected("SOL wrapped exceeds the order amount")
    if jupiter < 1:
        raise Rejected("No Jupiter v6 instruction")
    return compute_budget(budget), created


def _view(wallet, addresses, accounts, label):
    """(sol value, {mint: amount}, issues). SOL value = lamports of wallet + wSOL token amounts."""
    sol, mints, issues = 0, {}, []
    for address, account in zip(addresses, accounts):
        if account is None:
            continue
        if address == wallet:
            sol += account["lamports"]
            continue
        if account["owner"] != TOKEN_PROGRAM:
            issues.append("%s: %s is not an SPL token account" % (label, address))
            continue
        token = parse_token_account(account["data"])
        if token.owner != wallet:
            issues.append("%s: token account %s is not owned by the taker" % (label, address))
            continue
        if token.delegate is not None or token.close_authority is not None:
            issues.append("%s: token account %s has a delegate or close authority" % (label, address))
        mints[token.mint] = mints.get(token.mint, 0) + token.amount
        if token.mint == SOL.mint:
            sol += token.amount
    return sol, mints, issues


def check_deltas(request, min_out, deltas):
    sol, usdc = deltas.get("sol", 0), deltas.get(USDC.mint, 0)
    if request.side == "BUY":
        if usdc < -request.amount:
            raise Rejected("Simulation spends more USDC than the order amount")
        if sol < min_out - config.FEE_CAP_LAMPORTS:
            raise Rejected("Simulation receives less SOL than otherAmountThreshold")
    else:
        if sol < -(request.amount + config.FEE_CAP_LAMPORTS):
            raise Rejected("Simulation spends more SOL than the order amount plus the fee cap")
        if usdc < min_out:
            raise Rejected("Simulation receives less USDC than otherAmountThreshold")
    for mint, delta in deltas.items():
        if mint not in ("sol", USDC.mint, SOL.mint) and delta < 0:
            raise Rejected("Simulation decreases another taker balance (%s)" % mint)


def verify(order, rpc, wallet):
    request = order.request
    tx = parse_transaction(order.transaction)
    message = tx.message
    if message.version != 0:
        raise Rejected("Only v0 transactions are accepted")
    if message.num_required_signatures != 1 or len(tx.signatures) != 1:
        raise Rejected("Transaction requires more than one signature")
    if message.fee_payer != wallet:
        raise Rejected("Fee payer / first signer is not the mandate wallet")
    if any(tx.signatures[0]):
        raise Rejected("Transaction arrived with a non-empty signature slot")
    tables = resolve_lookups(message, rpc)
    metas = resolve_accounts(message, tables)
    if any(m.signer for m in metas[1:]):
        raise Rejected("Extra signer")

    _, taker_list = rpc.token_accounts_by_owner(wallet)
    if len(taker_list) > config.MAX_TOKEN_ACCOUNTS:
        raise Rejected("Wallet has too many token accounts to verify; use a dedicated wallet")
    _, other = rpc.token_accounts_by_owner(wallet, program=TOKEN_2022_PROGRAM)
    if other:
        raise Rejected("Wallet holds Token-2022 accounts; use a dedicated wallet")
    taker_accounts = {}
    for address, account in taker_list:
        if account is None or account["owner"] != TOKEN_PROGRAM:
            raise Rejected("Token account list is inconsistent")
        token = parse_token_account(account["data"])
        if token.owner != wallet:
            raise Rejected("RPC returned a token account of another owner")
        taker_accounts[address] = token
    priority, created = check_instructions(message, metas, wallet, request, taker_accounts)

    height = rpc.block_height("confirmed")
    if height + config.SIGN_HEADROOM_BLOCKS >= order.last_valid_block_height:
        raise Rejected("Blockhash expired or about to expire (height %d, last valid %d)"
                       % (height, order.last_valid_block_height))

    addresses = [wallet] + sorted(set(taker_accounts) | set(created))
    pre_slot, pre = rpc.multiple_accounts(addresses)
    sim = rpc.simulate(base64.b64encode(order.transaction).decode(), addresses)
    if sim["err"] is not None:
        raise Rejected("Simulation failed: %s" % str(sim["err"])[:200])
    if sim["slot"] < pre_slot:
        raise Rejected("Simulation ran on an older slot than the balance snapshot")
    sol0, mints0, issues0 = _view(wallet, addresses, pre, "pre")
    sol1, mints1, issues1 = _view(wallet, addresses, sim["accounts"], "post")
    if issues0 or issues1:
        raise Rejected("; ".join(issues0 + issues1)[:300])
    deltas = {"sol": sol1 - sol0}
    for mint in set(mints0) | set(mints1):
        deltas[mint] = mints1.get(mint, 0) - mints0.get(mint, 0)
    check_deltas(request, order.min_out, deltas)
    return Verified(message.raw, hashlib.sha256(message.raw).hexdigest(), priority, height,
                    created, deltas, sim["slot"], {k: len(v) for k, v in tables.items()})
