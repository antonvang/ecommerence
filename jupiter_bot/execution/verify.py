"""Verify the actual `/order` transaction before anything signs it. Default: reject.

1. Decode the versioned transaction (v0 only); exactly one required signature,
   and it is the mandate wallet (= fee payer = transaction id owner).
2. Resolve every address lookup table via `getAccountInfo` (owner must be the
   ALT program, table must be active), rebuild the full account list and reject
   any account that appears twice (F12).
3. Every top-level program is static and on the allowlist: System, ComputeBudget,
   SPL Token, Associated Token Account, Jupiter v6. System/Token/ATA/ComputeBudget
   instructions are decoded and limited to what a swap needs; ATA addresses and
   the wrap target must equal the locally derived PDA (F12).
4. Exactly ONE Jupiter v6 instruction, of an accepted route variant, whose
   decoded arguments match the order: in_amount == request, slippage <= the
   mandate, platform fee <= cap, and its on-chain floor
   quoted_out * (10000 - slippage) / 10000 >= otherAmountThreshold (F3).
5. Every executable account of the transaction and every program invoked during
   simulation (innerInstructions) is on a pinned allowlist; an RPC that does not
   return inner instructions -> reject (F4).
6. The blockhash still has headroom before `lastValidBlockHeight`.
7. `simulateTransaction` (sigVerify false) returns the post-state of the wallet
   and all its token accounts. The wallet must stay a System-owned, empty,
   non-executable account (F2); token accounts stay initialised, unfrozen, owned
   by the taker, no delegate/close authority. Deltas must show exactly: spend <=
   input (+ the transaction's own exact fee for SOL), receive >= threshold
   (- that fee when receiving SOL), nothing else decreases (F6).
"""
from __future__ import annotations

import base64
import hashlib
import struct
from dataclasses import dataclass

from ..core import SOL, USDC, Rejected
from . import config, jupiter_ix
from .solana_tx import (ALT_PROGRAM, ATA_PROGRAM, COMPUTE_BUDGET_PROGRAM, JUPITER_V6_PROGRAM, SYSTEM_PROGRAM,
                        TOKEN_2022_PROGRAM, TOKEN_PROGRAM, associated_token_address, parse_lookup_table,
                        parse_token_account, parse_transaction, resolve_accounts)

ALLOWED_PROGRAMS = (SYSTEM_PROGRAM, COMPUTE_BUDGET_PROGRAM, TOKEN_PROGRAM, ATA_PROGRAM, JUPITER_V6_PROGRAM)
INNER_ALLOWED = frozenset(ALLOWED_PROGRAMS) | {config.MEMO_PROGRAM} | frozenset(config.DEX_PROGRAMS)
TOKEN_SYNC_NATIVE, TOKEN_CLOSE_ACCOUNT = 17, 9
SYSTEM_TRANSFER = 2


@dataclass(frozen=True)
class Verified:
    message_bytes: bytes
    message_sha256: str
    priority_lamports: int
    network_fee: int          # signatures x base fee + priority
    expected_fee: int         # network fee + rent of ATAs this tx leaves behind
    block_height: int
    created_atas: dict
    persisting_atas: tuple
    deltas: dict              # {"sol": int, mint: int, ...}
    sim_slot: int
    lookups: dict
    swap: dict                # decoded Jupiter arguments (recorded in DRY_RUN)
    inner_programs: tuple
    pre: dict                 # wallet view before the order (for the EXPIRED rule)


def compute_budget(instructions):
    """Priority fee in lamports. Rejects unknown or repeated ComputeBudget instructions."""
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
    """Static rules on top-level instructions. Returns (priority, created ATAs, decoded swap)."""
    keys = [m.key for m in metas]
    static = len(message.static_keys)
    swap_mints = (request.input_mint, request.output_mint)
    budget, created, swaps = [], {}, []
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
            if ata != associated_token_address(wallet, mint):
                raise Rejected("Created token account is not the wallet's derived ATA")
            created[ata] = mint
    wsol = associated_token_address(wallet, SOL.mint)
    mine = set(created) | set(taker_accounts)
    transferred = 0
    for ix in message.instructions:
        program = keys[ix.program_index]
        accts = [keys[i] for i in ix.accounts]
        if program == COMPUTE_BUDGET_PROGRAM:
            budget.append(ix)
        elif program == JUPITER_V6_PROGRAM:
            swaps.append(jupiter_ix.decode(ix.data))
        elif program == SYSTEM_PROGRAM:
            if len(ix.data) != 12 or struct.unpack_from("<I", ix.data, 0)[0] != SYSTEM_TRANSFER or len(accts) < 2:
                raise Rejected("Only System transfers (SOL wrapping) are allowed")
            source, target = accts[:2]
            lamports, = struct.unpack_from("<Q", ix.data, 4)
            if request.input_mint != SOL.mint or source != wallet or target != wsol:
                raise Rejected("System transfer is not a wrap into the wallet's own wSOL ATA")
            transferred += lamports
        elif program == TOKEN_PROGRAM:
            kind = ix.data[0] if len(ix.data) == 1 else None
            if kind == TOKEN_SYNC_NATIVE and accts and accts[0] == wsol:
                continue
            if kind == TOKEN_CLOSE_ACCOUNT and len(accts) >= 3 and accts[0] in mine \
                    and accts[1] == wallet and accts[2] == wallet:
                continue
            raise Rejected("Token instruction other than SyncNative/CloseAccount on own accounts")
    if transferred > request.amount:
        raise Rejected("SOL wrapped exceeds the order amount")
    if len(swaps) != 1:
        raise Rejected("Expected exactly one Jupiter v6 instruction, found %d" % len(swaps))
    return compute_budget(budget), created, swaps[0]


def check_swap(swap, request, min_out):
    if swap.in_amount != request.amount:
        raise Rejected("Jupiter instruction in_amount %d != order %d" % (swap.in_amount, request.amount))
    if swap.slippage_bps > request.slippage_bps:
        raise Rejected("Jupiter instruction slippage %d bps above the mandate" % swap.slippage_bps)
    if swap.platform_fee_bps > config.MAX_FEE_BPS:
        raise Rejected("Jupiter instruction platform fee %d bps above the cap" % swap.platform_fee_bps)
    if swap.min_out < min_out:
        raise Rejected("Jupiter instruction floor %d is below otherAmountThreshold %d" % (swap.min_out, min_out))


def check_programs(metas, executable_keys, inner_programs):
    for key in executable_keys:
        if key not in INNER_ALLOWED:
            raise Rejected("Executable account %s is not on the program allowlist" % key)
    if inner_programs is None:
        raise Rejected("RPC did not return innerInstructions; cannot check invoked programs (fail closed)")
    names = []
    for program in inner_programs:
        if isinstance(program, int):
            if not 0 <= program < len(metas):
                raise Rejected("Inner instruction program index out of range")
            program = metas[program].key
        if program not in INNER_ALLOWED:
            raise Rejected("Inner instruction invokes %s, not on the program allowlist" % program)
        names.append(program)
    return tuple(sorted(set(names)))


def check_wallet_account(account, label):
    if account is None:
        raise Rejected("%s: wallet account missing" % label)
    if account["owner"] != SYSTEM_PROGRAM or account["executable"] or account["data"]:
        raise Rejected("%s: wallet account is not a plain System account (owner/data/executable)" % label)


def view(wallet, addresses, accounts, label):
    """(sol value, {mint: amount}, issues). SOL value = lamports of wallet + wSOL token amounts."""
    sol, mints, issues = 0, {}, []
    for address, account in zip(addresses, accounts):
        if address == wallet:
            check_wallet_account(account, label)
            sol += account["lamports"]
            continue
        if account is None:
            continue
        if account["owner"] != TOKEN_PROGRAM or account["executable"]:
            issues.append("%s: %s is not an SPL token account" % (label, address))
            continue
        token = parse_token_account(account["data"])
        if token.owner != wallet:
            issues.append("%s: token account %s is not owned by the taker" % (label, address))
            continue
        if token.state != 1:
            issues.append("%s: token account %s is frozen" % (label, address))
        if token.delegate is not None or token.close_authority is not None:
            issues.append("%s: token account %s has a delegate or close authority" % (label, address))
        mints[token.mint] = mints.get(token.mint, 0) + token.amount
        if token.mint == SOL.mint:
            sol += token.amount
    return sol, mints, issues


def check_deltas(request, min_out, deltas, expected_fee):
    """Exact rule (F6): only this transaction's own fee may be added on the SOL side."""
    sol, usdc = deltas.get("sol", 0), deltas.get(USDC.mint, 0)
    if request.side == "BUY":
        if usdc < -request.amount:
            raise Rejected("Spends more USDC than the order amount")
        if sol + expected_fee < min_out:
            raise Rejected("Receives less SOL than otherAmountThreshold (after the exact fee %d)" % expected_fee)
    else:
        if -sol > request.amount + expected_fee:
            raise Rejected("Spends more SOL than the order amount plus the exact fee %d" % expected_fee)
        if usdc < min_out:
            raise Rejected("Receives less USDC than otherAmountThreshold")
    for mint, delta in deltas.items():
        if mint not in ("sol", USDC.mint, SOL.mint) and delta < 0:
            raise Rejected("Decreases another taker balance (%s)" % mint)


def _executable(rpc, keys):
    found = []
    for start in range(0, len(keys), 100):
        chunk = keys[start:start + 100]
        _, accounts = rpc.multiple_accounts(chunk, no_data=True)
        found += [k for k, a in zip(chunk, accounts) if a is not None and a["executable"]]
    return found


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
    priority, created, swap = check_instructions(message, metas, wallet, request, taker_accounts)
    check_swap(swap, request, order.min_out)
    executable = _executable(rpc, [m.key for m in metas])

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
    inner = check_programs(metas, executable, sim["inner_programs"])
    sol0, mints0, issues0 = view(wallet, addresses, pre, "pre")
    sol1, mints1, issues1 = view(wallet, addresses, sim["accounts"], "post")
    if issues0 or issues1:
        raise Rejected("; ".join(issues0 + issues1)[:300])
    deltas = {"sol": sol1 - sol0}
    for mint in set(mints0) | set(mints1):
        deltas[mint] = mints1.get(mint, 0) - mints0.get(mint, 0)
    post = dict(zip(addresses, sim["accounts"]))
    persisting = tuple(sorted(a for a in created if post.get(a) is not None and pre[addresses.index(a)] is None))
    network_fee = config.BASE_FEE_LAMPORTS * message.num_required_signatures + priority
    expected_fee = network_fee + config.ATA_RENT_LAMPORTS * len(persisting)
    check_deltas(request, order.min_out, deltas, expected_fee)
    return Verified(message.raw, hashlib.sha256(message.raw).hexdigest(), priority, network_fee, expected_fee,
                    height, created, persisting, deltas, sim["slot"], {k: len(v) for k, v in tables.items()},
                    swap.as_dict(), inner, {"sol": sol0, "mints": mints0, "addresses": addresses})
