"""Paths and fixed safety limits of the execution adapter.

The limits are code constants on purpose: the mandate (written by Anton) can
only make things *stricter* than these, never looser. `signer.py` keeps its own
copy of the ones it enforces; a test checks that both copies agree.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path("~/.config/jupiter-bot").expanduser()
DATA_DIR = Path("~/.local/share/jupiter-bot").expanduser()
# Wallet-wide state that must NOT follow --data-dir or --mandate (F7): one lock, one
# ledger binding and the signer's daily-cap file per wallet public key.
WALLETS_DIR = CONFIG_DIR / "wallets"

# Network fees and costs (lamports) -------------------------------------------------
BASE_FEE_LAMPORTS = 5_000                  # per signature; we only allow one
PRIORITY_CAP_LAMPORTS = 500_000            # 0.0005 SOL, cap on CU price x CU limit
ATA_RENT_LAMPORTS = 2_039_280              # rent-exempt minimum of a 165-byte account
# There is no fixed fee tolerance: each transaction's exact expected cost is computed
# (signatures x base fee + its own ComputeBudget priority + rent of ATAs it leaves behind).
SOL_RESERVE_LAMPORTS = 30_000_000          # 0.03 SOL kept for fees; also keeps us off gasless (< 0.01 SOL)
DEFAULT_CU_LIMIT = 1_400_000               # used when a tx sets a price but no limit (worst case)

# Order handling -------------------------------------------------------------------
HARD_MAX_SLIPPAGE_BPS = 300                # the mandate may not exceed this
MAX_FEE_BPS = 50                           # reject a quoted Jupiter fee above this (SOL-stable is 2)
MAX_PRICE_DEVIATION_BPS = 300              # quote price vs the journal's last close
MIN_TRADE_USDC_ATOMS = 1_000_000           # 1 USDC; smaller changes are ignored
ORDER_MAX_AGE_S = 25.0                     # /order -> signature must happen within this
SIGN_HEADROOM_BLOCKS = 30                  # need at least this many blocks left before lastValidBlockHeight
EXPIRY_MARGIN_BLOCKS = 150                 # EXPIRED only when finalized height > lastValid + this
MAX_TOKEN_ACCOUNTS = 16                    # a dedicated wallet has very few token accounts
EXCLUDED_ROUTERS = "dflow,jupiterz,okx"    # only metis: Jupiter v6, taker signs alone
ACCEPTED_ROUTERS = ("metis",)

# Programs that may be INVOKED inside the swap (CPI), checked via simulateTransaction
# innerInstructions and via the executable accounts of the transaction (F4).
# PINNED FROM MEMORY, NOT YET CHECKED against Jupiter's /swap/v2/program-id-to-label:
# confirm in DRY_RUN (unknown programs are rejected and named) and re-review any change.
MEMO_PROGRAM = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
DEX_PROGRAMS = {
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora pools",
    "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY": "Phoenix",
    "opnb2LAfJYbRMAHHvqjCwQxanZn7ReEHp1k81EohpZb": "OpenBook v2",
    "2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3c": "Lifinity v2",
    "SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe": "SolFi",
    "obriQD1zbpyLz95G5n7nJe6a4DPjpFwa5XYPoNm113y": "Obric v2",
}

# Signer caps (mirrored in signer.py) ------------------------------------------------
SIGNER_MAX_SIGNATURES_PER_DAY = 24
SIGNER_DAILY_NOTIONAL_FACTOR = 8           # daily signed notional <= factor x max_position_usdc

DRY_RUNS_REQUIRED = 3

# N6: max_trade_sol at the latest journal price may be worth at most this many times
# max_trade_usdc. The signer's SELL cap is only as good as this number, so it is held
# to the USDC limit Anton chose. No price available -> the mandate is not usable.
MAX_TRADE_SOL_VALUE_FACTOR = Decimal("1.5")


@dataclass(frozen=True)
class Paths:
    mandate: Path
    arm: Path
    ledger: Path
    wallets: Path
    lock: Path
    journal: Path
    plan_lock: Path
    verdicts: Path
    review: Path
    repo: Path

    @classmethod
    def defaults(cls, mandate=None, data_dir=None, journal=None, repo=None, wallets=None):
        mandate = Path(mandate) if mandate else CONFIG_DIR / "mandate.json"
        data = Path(data_dir) if data_dir else DATA_DIR
        repo = Path(repo) if repo else REPO
        return cls(mandate=mandate, arm=mandate.parent / "armed.json",
                   ledger=data / "execution.db", wallets=Path(wallets) if wallets else WALLETS_DIR,
                   lock=data / "execution.lock",
                   journal=Path(journal) if journal else data / "observations.db",
                   plan_lock=data / "research" / "plan_lock.json",
                   verdicts=data / "research" / "verdicts",
                   review=repo / "jupiter_bot" / "reviews" / "P3_REVIEW.md", repo=repo)

    def wallet_lock(self, wallet):
        return self.wallets / ("%s.lock" % wallet)

    def wallet_binding(self, wallet):
        return self.wallets / ("%s.json" % wallet)

    def signer_state(self, wallet):
        return self.wallets / ("%s.signer-state.json" % wallet)
