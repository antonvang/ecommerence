"""Finder køb og salg af memecoins i en wallets Solana-transaktion.

Virker for alle DEX'er (pump.fun, PumpSwap, Raydium, Meteora, Jupiter-ruter), fordi vi kun ser
på, hvad wallettens saldi ændrer sig med: én token op og SOL (eller USDC/USDT) ned = køb.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

WSOL = "So11111111111111111111111111111111111111112"
STABLES = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}
TOKEN_ACCOUNT_RENT_SOL = 0.00203928  # depositum for en token-konto; får man igen, når den lukkes
MIN_SOL = 0.005
MIN_STABLE = 1.0


@dataclass
class Swap:
    sig: str
    wallet: str
    ts: int
    side: str                 # "buy" eller "sell"
    mint: str
    tokens: float             # antal tokens købt/solgt
    quote_usd: float          # hvad handlen var værd i USD
    price_usd: float          # walletens gennemsnitspris pr. token
    leader_left: float        # tokens walletten har tilbage efter handlen
    reserve_usd: Optional[float]  # SOL-siden af poolen efter handlen (til slippage), hvis den kan findes


def _keys(tx):
    msg = tx["transaction"]["message"]
    keys, signers = [], set()
    for k in msg["accountKeys"]:
        if isinstance(k, dict):
            keys.append(k["pubkey"])
            if k.get("signer"):
                signers.add(k["pubkey"])
        else:
            keys.append(k)
    n = len(tx["meta"]["preBalances"])
    if len(keys) < n:
        la = tx["meta"].get("loadedAddresses") or {}
        keys += la.get("writable", []) + la.get("readonly", [])
    if not signers:
        signers = set(keys[: msg.get("header", {}).get("numRequiredSignatures", 1)])
    return keys, signers


def _amount(b):
    u = b["uiTokenAmount"]
    return int(u["amount"]) / (10 ** int(u["decimals"]))


def _owned(balances, owner):
    return {b["accountIndex"]: (b["mint"], _amount(b)) for b in balances or [] if b.get("owner") == owner}


def _reserve_sol(meta, i, wallet, sol_change):
    """SOL i poolen efter handlen: den konto, der modtog (købt) eller sendte (solgt) flest SOL.

    Dækker WSOL-vaults (Raydium, PumpSwap, Meteora) og pump.funs bonding curve (native SOL).
    """
    sign = 1 if sol_change < 0 else -1
    need = 0.5 * abs(sol_change)
    best_d, best_r = 0.0, None
    pre_tb = meta.get("preTokenBalances") or []
    post_tb = meta.get("postTokenBalances") or []
    pre = {b["accountIndex"]: _amount(b) for b in pre_tb if b["mint"] == WSOL and b.get("owner") != wallet}
    post = {b["accountIndex"]: _amount(b) for b in post_tb if b["mint"] == WSOL and b.get("owner") != wallet}
    for idx in set(pre) | set(post):
        d = post.get(idx, 0.0) - pre.get(idx, 0.0)
        if d * sign >= need and abs(d) > best_d:
            best_d, best_r = abs(d), post.get(idx, 0.0)
    token_idx = {b["accountIndex"] for b in pre_tb + post_tb}
    for k, (a, b) in enumerate(zip(meta["preBalances"], meta["postBalances"])):
        if k == i or k in token_idx:
            continue
        d = (b - a) / 1e9
        if d * sign >= need and abs(d) > best_d:
            best_d, best_r = abs(d), b / 1e9
    return best_r or None


def parse_swaps(tx, wallet, sol_usd: Callable[[int], float]):
    if not tx:
        return []
    meta = tx.get("meta")
    ts = tx.get("blockTime")
    if not meta or meta.get("err") is not None or not ts:
        return []
    keys, signers = _keys(tx)
    if wallet not in keys or wallet not in signers:
        return []
    i = keys.index(wallet)
    native = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9
    if i == 0:
        native += meta.get("fee", 0) / 1e9  # netværksgebyr er ikke en del af prisen

    pre = _owned(meta.get("preTokenBalances"), wallet)
    post = _owned(meta.get("postTokenBalances"), wallet)
    delta, rent = {}, 0.0
    for idx in set(pre) | set(post):
        mint = (post.get(idx) or pre.get(idx))[0]
        delta[mint] = delta.get(mint, 0.0) + post.get(idx, (mint, 0.0))[1] - pre.get(idx, (mint, 0.0))[1]
        if idx not in pre:
            rent += TOKEN_ACCOUNT_RENT_SOL
        elif idx not in post:
            rent -= TOKEN_ACCOUNT_RENT_SOL

    sol_change = native + delta.pop(WSOL, 0.0) + rent
    stable = sum(delta.pop(m) for m in list(delta) if m in STABLES)
    tokens = {m: d for m, d in delta.items() if abs(d) > 0}
    if len(tokens) != 1:
        return []  # ingen handel, eller token-til-token som vi ikke kopierer
    mint, d = next(iter(tokens.items()))
    side = "buy" if d > 0 else "sell"
    want = -1 if side == "buy" else 1
    if abs(sol_change) >= MIN_SOL and sol_change * want > 0:
        sp = sol_usd(ts)
        quote_usd = abs(sol_change) * sp
        r = _reserve_sol(meta, i, wallet, sol_change)
        reserve_usd = r * sp if r else None
    elif abs(stable) >= MIN_STABLE and stable * want > 0:
        quote_usd, reserve_usd = abs(stable), None
    else:
        return []
    left = sum(a for (m, a) in post.values() if m == mint)
    return [Swap(
        sig=tx["transaction"]["signatures"][0], wallet=wallet, ts=int(ts), side=side, mint=mint,
        tokens=abs(d), quote_usd=quote_usd, price_usd=quote_usd / abs(d), leader_left=left,
        reserve_usd=reserve_usd)]
