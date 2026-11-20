"""Paths and fixed safety limits of the execution adapter.

The limits are code constants on purpose: the mandate (written by Anton) can
only make things *stricter* than these, never looser. `signer.py` keeps its own
copy of the ones it enforces; a test checks that both copies agree.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path("~/.config/jupiter-bot").expanduser()
DATA_DIR = Path("~/.local/share/jupiter-bot").expanduser()

# Network fees and costs (lamports) -------------------------------------------------
BASE_FEE_LAMPORTS = 5_000                  # per signature; we only allow one
PRIORITY_CAP_LAMPORTS = 500_000            # 0.0005 SOL, cap on CU price x CU limit
ATA_RENT_LAMPORTS = 2_039_280              # rent-exempt minimum of a 165-byte account
# Upper bound on SOL a swap may cost beyond the swap itself (fee + priority + 2 ATA rents).
FEE_CAP_LAMPORTS = BASE_FEE_LAMPORTS + PRIORITY_CAP_LAMPORTS + 2 * ATA_RENT_LAMPORTS
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

# Signer caps (mirrored in signer.py) ------------------------------------------------
SIGNER_MAX_SIGNATURES_PER_DAY = 24
SIGNER_DAILY_NOTIONAL_FACTOR = 8           # daily signed notional <= factor x max_position_usdc

DRY_RUNS_REQUIRED = 3


@dataclass(frozen=True)
class Paths:
    mandate: Path
    arm: Path
    ledger: Path
    signer_state: Path
    lock: Path
    journal: Path
    plan_lock: Path
    verdicts: Path
    review: Path
    repo: Path

    @classmethod
    def defaults(cls, mandate=None, data_dir=None, journal=None, repo=None):
        mandate = Path(mandate) if mandate else CONFIG_DIR / "mandate.json"
        data = Path(data_dir) if data_dir else DATA_DIR
        repo = Path(repo) if repo else REPO
        return cls(mandate=mandate, arm=mandate.parent / "armed.json",
                   ledger=data / "execution.db", signer_state=data / "signer-state.json",
                   lock=data / "execution.lock",
                   journal=Path(journal) if journal else data / "observations.db",
                   plan_lock=data / "research" / "plan_lock.json",
                   verdicts=data / "research" / "verdicts",
                   review=repo / "jupiter_bot" / "reviews" / "P3_REVIEW.md", repo=repo)
