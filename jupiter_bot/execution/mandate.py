"""The mandate: Anton's hand-written limits for real execution.

Strict: unknown or missing keys, wrong types, JSON numbers for money, more than
6 decimals, NaN, duplicate keys -> Rejected. USDC amounts are DECIMAL STRINGS
in whole USDC (e.g. "25" or "25.50"); they are converted to integer atoms
internally. The keypair file is only `lstat`-ed here, never opened.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from ..core import SOL, USDC, Rejected, atoms, canonical, strict_json, timestamp
from ..research.strategies import STRATEGIES
from . import config
from .solana_tx import is_pubkey

KEYS = ("wallet_pubkey", "keypair_path", "rpc_url", "max_trade_usdc", "max_trade_sol", "max_position_usdc",
        "daily_loss_limit_usdc", "max_slippage_bps", "allowed_mints", "strategy", "params",
        "expires_at")
MAX_BYTES = 64 * 1024
USDC_TEXT = re.compile(r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,6})?$")
SOL_TEXT = re.compile(r"^(0|[1-9][0-9]{0,8})(\.[0-9]{1,9})?$")
ALLOWED = (SOL.mint, USDC.mint)


@dataclass(frozen=True)
class Mandate:
    wallet_pubkey: str
    keypair_path: str
    rpc_url: str
    max_trade_usdc: int          # atoms
    max_trade_sol: int           # lamports; the signer caps every SELL's input with it
    max_position_usdc: int       # atoms
    daily_loss_limit_usdc: int   # atoms
    max_slippage_bps: int
    allowed_mints: tuple
    strategy: str
    params_json: str
    expires_at: float
    sha256: str

    @property
    def params(self):
        return json.loads(self.params_json)

    @property
    def rpc_host(self):
        return urlsplit(self.rpc_url).hostname

    def public(self):
        """The status/dashboard view. No rpc_url (may hold an API key), no keypair path."""
        return {"wallet_pubkey": self.wallet_pubkey,
                "max_position_usdc": self.max_position_usdc / 1e6,
                "max_trade_usdc": self.max_trade_usdc / 1e6,
                "daily_loss_limit_usdc": self.daily_loss_limit_usdc / 1e6,
                "allowed_mints": list(self.allowed_mints), "expires_at": self.expires_at}


def _usdc(raw, key):
    value = raw[key]
    if not isinstance(value, str) or not USDC_TEXT.match(value):
        raise Rejected("%s must be a decimal string in USDC, e.g. \"25.00\"" % key)
    return atoms(value, USDC)


def check_rpc_url(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise Rejected("rpc_url must be a string")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise Rejected("rpc_url must be an https URL")
    if parts.username or parts.password or parts.fragment:
        raise Rejected("rpc_url must not contain user info or a fragment")
    if parts.hostname == "api.jup.ag":
        raise Rejected("rpc_url must be a Solana RPC, not Jupiter")
    return url


def is_public_rpc(host):
    host = (host or "").lower().rstrip(".")
    return host == "solana.com" or host.endswith(".solana.com")


def parse(raw_bytes):
    if len(raw_bytes) > MAX_BYTES:
        raise Rejected("mandate.json is too large")
    try:
        raw = strict_json(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise Rejected("mandate.json is not strict JSON: %s" % exc) from None
    if not isinstance(raw, dict):
        raise Rejected("mandate.json must be a JSON object")
    unknown = sorted(set(raw) - set(KEYS))
    if unknown:
        raise Rejected("Unknown mandate keys: %s" % ", ".join(unknown))
    missing = [k for k in KEYS if k not in raw]
    if missing:
        raise Rejected("Missing mandate keys: %s" % ", ".join(missing))
    wallet = raw["wallet_pubkey"]
    if not isinstance(wallet, str) or not is_pubkey(wallet):
        raise Rejected("wallet_pubkey is not a base58 public key")
    keypair = raw["keypair_path"]
    if not isinstance(keypair, str) or not os.path.isabs(keypair):
        raise Rejected("keypair_path must be an absolute path")
    rpc_url = check_rpc_url(raw["rpc_url"])
    trade, position, loss = (_usdc(raw, k) for k in
                             ("max_trade_usdc", "max_position_usdc", "daily_loss_limit_usdc"))
    sol_text = raw["max_trade_sol"]
    if not isinstance(sol_text, str) or not SOL_TEXT.match(sol_text):
        raise Rejected("max_trade_sol must be a decimal string in SOL, e.g. \"0.15\"")
    trade_sol = atoms(sol_text, SOL)
    if trade > position:
        raise Rejected("max_trade_usdc must not exceed max_position_usdc")
    if trade < config.MIN_TRADE_USDC_ATOMS:
        raise Rejected("max_trade_usdc must be at least 1 USDC")
    slippage = raw["max_slippage_bps"]
    if type(slippage) is not int or not 1 <= slippage <= config.HARD_MAX_SLIPPAGE_BPS:
        raise Rejected("max_slippage_bps must be an integer 1..%d" % config.HARD_MAX_SLIPPAGE_BPS)
    mints = raw["allowed_mints"]
    if (not isinstance(mints, list) or not mints or len(set(mints)) != len(mints)
            or any(m not in ALLOWED for m in mints)):
        raise Rejected("allowed_mints must be a non-empty subset of the SOL and USDC mints")
    strategy, params = raw["strategy"], raw["params"]
    if not isinstance(strategy, str) or strategy not in STRATEGIES:
        raise Rejected("strategy is not in research.strategies.STRATEGIES")
    if not isinstance(params, dict) or params not in STRATEGIES[strategy][2]:
        raise Rejected("params are not one of the registered grid entries for %s" % strategy)
    expires = raw["expires_at"]
    if isinstance(expires, bool) or not isinstance(expires, (int, float)):
        raise Rejected("expires_at must be Unix seconds")
    return Mandate(wallet, keypair, rpc_url, trade, trade_sol, position, loss, slippage, tuple(mints),
                   strategy, canonical(params), timestamp(expires),
                   hashlib.sha256(raw_bytes).hexdigest())


def read(path):
    """(raw_bytes, sha256) or (None, None) if absent."""
    path = Path(path)
    if not path.exists():
        return None, None
    data = path.read_bytes()[:MAX_BYTES + 1]
    return data, hashlib.sha256(data).hexdigest()


def load_once(path):
    """(Mandate | None, error | None, sha256 | None) from ONE read of the file."""
    try:
        data, sha = read(path)
    except OSError as exc:
        return None, "mandate.json cannot be read: %s" % type(exc).__name__, None
    if data is None:
        return None, None, None
    try:
        return parse(data), None, sha
    except Rejected as exc:
        return None, str(exc), sha


def load(path):
    """(Mandate | None, error text | None). Absent -> (None, None)."""
    mandate, error, _ = load_once(path)
    return mandate, error


def keypair_problems(path, repo=config.REPO, uid=None):
    """Checks on the keypair FILE (lstat only; contents are never read here)."""
    uid = os.getuid() if uid is None else uid
    problems = []
    path = Path(path)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return ["keypair file does not exist"]
    except OSError as exc:
        return ["keypair file cannot be inspected: %s" % type(exc).__name__]
    if stat.S_ISLNK(info.st_mode):
        problems.append("keypair path is a symlink")
    elif not stat.S_ISREG(info.st_mode):
        problems.append("keypair path is not a regular file")
    if info.st_uid != uid:
        problems.append("keypair file is not owned by the current user")
    if stat.S_IMODE(info.st_mode) & 0o077:
        problems.append("keypair file permissions are %o; must be 600 (or 400)" % stat.S_IMODE(info.st_mode))
    try:
        parent = os.lstat(path.parent)
        if stat.S_ISLNK(parent.st_mode) or parent.st_uid != uid or stat.S_IMODE(parent.st_mode) & 0o022:
            problems.append("keypair directory must be owned by you, not a symlink, not group/other-writable")
    except OSError:
        problems.append("keypair directory cannot be inspected")
    try:
        resolved, root = Path(os.path.realpath(path)), Path(os.path.realpath(repo))
        if resolved == root or root in resolved.parents:
            problems.append("keypair file is inside the repository")
    except OSError:
        problems.append("keypair path cannot be resolved")
    return problems


def sol_cap_problem(mandate, price):
    """N6: max_trade_sol must not be worth more than 1.5 x max_trade_usdc at `price` (USDC/SOL)."""
    if price is None:
        return "no journal price to check max_trade_sol against max_trade_usdc"
    value = Decimal(mandate.max_trade_sol) * Decimal(price) / 1000          # USDC atoms
    if value > config.MAX_TRADE_SOL_VALUE_FACTOR * mandate.max_trade_usdc:
        return ("max_trade_sol %s SOL is worth %.2f USDC at %s USDC/SOL, more than %s x max_trade_usdc"
                % (Decimal(mandate.max_trade_sol) / 10**9, value / 10**6, price, config.MAX_TRADE_SOL_VALUE_FACTOR))
    return None


def problems(mandate, now, repo=config.REPO, uid=None, price=None):
    """Reasons a structurally valid mandate cannot be used right now. `price`: latest USDC/SOL."""
    found = []
    cap = sol_cap_problem(mandate, price)
    if cap:
        found.append(cap)
    if mandate.expires_at <= now:
        found.append("mandate expired")
    found += keypair_problems(mandate.keypair_path, repo, uid)
    if SOL.mint not in mandate.allowed_mints or USDC.mint not in mandate.allowed_mints:
        found.append("the SOL/USDC strategy needs both mints in allowed_mints")
    return found
