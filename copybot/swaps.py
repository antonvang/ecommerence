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


def _reserve_sol(meta, keys, i, wallet, mint, sol_change):
    """SOL i poolen efter handlen: den konto, der modtog (købt) eller sendte (solgt) flest SOL.

    Dækker WSOL-vaults (Raydium, PumpSwap, Meteora) og pump.funs bonding curve (native SOL).
    Kontoen skal høre til en pool, der også holder selve memecoinen. Ellers er det fx sidste led i en
    rute via USDC (en kæmpe SOL/USDC-pool), og så kender vi ikke memecoinens likviditet.
    """
    sign = 1 if sol_change < 0 else -1
    need = 0.5 * abs(sol_change)
    best_d, best_r = 0.0, None
    pre_tb = meta.get("preTokenBalances") or []
    post_tb = meta.get("postTokenBalances") or []
    pools = {b.get("owner") for b in pre_tb + post_tb if b["mint"] == mint and b.get("owner") not in (None, wallet)}
    pre = {b["accountIndex"]: _amount(b) for b in pre_tb if b["mint"] == WSOL and b.get("owner") in pools}
    post = {b["accountIndex"]: _amount(b) for b in post_tb if b["mint"] == WSOL and b.get("owner") in pools}
    for idx in set(pre) | set(post):
        d = post.get(idx, 0.0) - pre.get(idx, 0.0)
        if d * sign >= need and abs(d) > best_d:
            best_d, best_r = abs(d), post.get(idx, 0.0)
    token_idx = {b["accountIndex"] for b in pre_tb + post_tb}
    for k, (a, b) in enumerate(zip(meta["preBalances"], meta["postBalances"])):
        if k == i or k in token_idx or k >= len(keys) or keys[k] not in pools:
            continue
        d = (b - a) / 1e9
        if d * sign >= need and abs(d) > best_d:
            best_d, best_r = abs(d), b / 1e9
    return best_r or None


def _reserve_token_side(meta, wallet, mint, d):
    """Antal memecoins i poolen efter handlen: den pool-konto, hvis beholdning flyttede sig mest modsat walletten.

    I en x*y=k-pool er de to sider lige meget værd, så tokens * pris = poolens anden side i USD,
    uanset om den er parret med SOL, USDC eller en tredje token (fx via en router).
    """
    pre = {b["accountIndex"]: _amount(b) for b in meta.get("preTokenBalances") or []
           if b["mint"] == mint and b.get("owner") != wallet}
    post = {b["accountIndex"]: _amount(b) for b in meta.get("postTokenBalances") or []
            if b["mint"] == mint and b.get("owner") != wallet}
    best_d, best_r = 0.0, None
    for idx in set(pre) | set(post):
        moved = post.get(idx, 0.0) - pre.get(idx, 0.0)
        if moved * d < 0 and abs(moved) >= 0.5 * abs(d) and abs(moved) > best_d:
            best_d, best_r = abs(moved), post.get(idx, 0.0)
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
    sig = tx["transaction"]["signatures"][0]
    gone = [m for m, d in tokens.items() if d < 0]
    if len(gone) == 1 and (len(tokens) == 2 or (len(tokens) == 1 and abs(sol_change) < MIN_SOL and abs(stable) < MIN_STABLE)):
        # walletten kommer af med en coin uden at få SOL/USDC: solgt for en anden token, eller flyttet til en
        # anden wallet. Prisen kender vi ikke her (0 = brug markedsprisen), men det er et exit, vi skal følge.
        mint = gone[0]
        return [Swap(sig=sig, wallet=wallet, ts=int(ts), side="sell", mint=mint, tokens=-tokens[mint], quote_usd=0.0,
                     price_usd=0.0, leader_left=sum(a for (m, a) in post.values() if m == mint), reserve_usd=None)]
    if len(tokens) != 1:
        return []  # ingen handel, eller køb betalt med en anden token, som vi ikke kopierer
    mint, d = next(iter(tokens.items()))
    side = "buy" if d > 0 else "sell"
    want = -1 if side == "buy" else 1
    if abs(sol_change) >= MIN_SOL and sol_change * want > 0:
        sp = sol_usd(ts)
        quote_usd = abs(sol_change) * sp
        r = _reserve_sol(meta, keys, i, wallet, mint, sol_change)
        reserve_usd = r * sp if r else None
    elif abs(stable) >= MIN_STABLE and stable * want > 0:
        quote_usd, reserve_usd = abs(stable), None
    else:
        return []
    if reserve_usd is None:
        t = _reserve_token_side(meta, wallet, mint, d)
        reserve_usd = t * quote_usd / abs(d) if t else None
    left = sum(a for (m, a) in post.values() if m == mint)
    return [Swap(
        sig=sig, wallet=wallet, ts=int(ts), side=side, mint=mint,
        tokens=abs(d), quote_usd=quote_usd, price_usd=quote_usd / abs(d), leader_left=left,
        reserve_usd=reserve_usd)]
