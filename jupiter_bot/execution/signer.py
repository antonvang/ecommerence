"""Restricted signer process. Standalone on purpose: no jupiter_bot imports.

Started by the engine as `python3 -I <this file> --mandate M --arm A --registry DIR`
with a minimal environment. It reads ONE JSON request on stdin:

    {"message_b64": "...", "bundle": {"message_sha256", "order_id", "side",
     "input_mint", "output_mint", "in_amount", "min_out"}}

and writes `{"signature": "<base58>"}` or `{"error": "..."}` on stdout.

Before signing it independently re-checks, with its own code:
  * PyNaCl is importable (otherwise it refuses to start; no home-made ed25519);
  * the mandate parses, is unexpired, and the arm file is LIVE for exactly this
    mandate file (sha256) -> deleting the arm file stops signing too;
  * the keypair file: regular file, not a symlink, owned by us, mode 0600/0400,
    outside the repository; its public key equals the mandate wallet;
  * the message: v0, one required signature, fee payer = wallet, every
    top-level program static and allowlisted, ComputeBudget priority capped,
    System transfers only from the wallet, only on a SELL, only to the wallet's
    own (locally derived) wSOL ATA, and their SUM <= the swap input; Token
    instructions only SyncNative/CloseAccount on own derived ATAs back to the
    wallet; ATA creations paid by and owned by the wallet at the derived PDA;
  * exactly one Jupiter v6 route instruction, decoded: its in_amount equals the
    bundle, its slippage <= the mandate, platform fee <= 50 bps, its on-chain
    floor >= the bundle's minimum; BUY input <= max_trade_usdc, SELL input <=
    max_trade_sol (both from the mandate the signer read itself);
  * its own per-UTC-day caps (count and notional) kept in a per-wallet state
    file in the wallet registry, updated BEFORE the signature is released.
The keypair bytes never leave this process; errors never contain them.
"""
import base64
import hashlib
import json
import os
import re
import stat
import struct
import sys
import tempfile
import time

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
COMPUTE_BUDGET_PROGRAM = "ComputeBudget111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
JUPITER_V6_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
ALLOWED_PROGRAMS = (SYSTEM_PROGRAM, COMPUTE_BUDGET_PROGRAM, TOKEN_PROGRAM, ATA_PROGRAM, JUPITER_V6_PROGRAM)
PRIORITY_CAP_LAMPORTS = 500_000
DEFAULT_CU_LIMIT = 1_400_000
MAX_SIGNATURES_PER_DAY = 24
DAILY_NOTIONAL_FACTOR = 8
MANDATE_KEYS = ("wallet_pubkey", "keypair_path", "rpc_url", "max_trade_usdc", "max_trade_sol", "max_position_usdc",
                "daily_loss_limit_usdc", "max_slippage_bps", "allowed_mints", "strategy", "params",
                "expires_at")
USDC_TEXT = re.compile(r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,6})?$")
SOL_TEXT = re.compile(r"^(0|[1-9][0-9]{0,8})(\.[0-9]{1,9})?$")
MAX_FEE_BPS = 50
# Jupiter v6 route variants accepted (Anchor discriminator = sha256("global:<name>")[:8]).
# Decoded front to back (Borsh): [id u8 if shared] Vec<RoutePlanStep> in_amount u64
# quoted_out_amount u64 slippage_bps u16 platform_fee_bps u8, every byte consumed.
# RoutePlanStep = Swap (u8 tag + fields) percent u8 input_index u8 output_index u8.
# Same UNCONFIRMED layout as jupiter_ix.py (own copy); must be confirmed in DRY_RUN.
JUPITER_ROUTES = {hashlib.sha256(b"global:" + n).digest()[:8]: n.decode()
                  for n in (b"route", b"shared_accounts_route")}
SWAP_FIELD_BYTES = {7: 0, 17: 1, 25: 0, 26: 0, 28: 1, 38: 0, 39: 1, 46: 0}   # tag -> u8 fields (bool/side)
MAX_STEPS = 8
REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
NO_NACL = ("PyNaCl (nacl.signing) is not importable; the signer refuses to start. "
           "Install the Debian package python3-nacl (the signer runs with python3 -I, so a pip --user "
           "install is not visible). No home-made ed25519 is used.")


class Refused(Exception):
    pass


# encoding ---------------------------------------------------------------------------

def b58encode(data):
    number = int.from_bytes(bytes(data), "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = B58[rem] + out
    return "1" * (len(data) - len(bytes(data).lstrip(b"\0"))) + out


def b58decode32(text):
    if not isinstance(text, str) or not 32 <= len(text) <= 44:
        raise Refused("bad public key")
    number = 0
    for ch in text:
        if ch not in B58:
            raise Refused("bad public key")
        number = number * 58 + B58.index(ch)
    pad = len(text) - len(text.lstrip("1"))
    raw = b"\0" * pad + (number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b"")
    if len(raw) != 32 or b58encode(raw) != text:
        raise Refused("bad public key")
    return raw


def compact(buf, pos):
    value = 0
    for i in range(3):
        if pos + i >= len(buf):
            raise Refused("truncated message")
        byte = buf[pos + i]
        value |= (byte & 0x7F) << (7 * i)
        if not byte & 0x80:
            if i and byte == 0:
                raise Refused("non-canonical length")
            return value, pos + i + 1
    raise Refused("bad length")


def parse_message(msg):
    """(header, static keys, instructions) of a v0 message. Strict, no trailing bytes."""
    if not msg or msg[0] != 0x80:
        raise Refused("not a v0 message")
    pos = 1
    if len(msg) < 4:
        raise Refused("truncated message")
    header = (msg[1], msg[2], msg[3])
    pos = 4
    count, pos = compact(msg, pos)
    if pos + 32 * count + 32 > len(msg):
        raise Refused("truncated message")
    keys = [b58encode(msg[pos + 32 * i: pos + 32 * (i + 1)]) for i in range(count)]
    pos += 32 * count + 32          # keys + blockhash
    n_ix, pos = compact(msg, pos)
    instructions = []
    for _ in range(n_ix):
        if pos >= len(msg):
            raise Refused("truncated message")
        program = msg[pos]
        pos += 1
        n_acc, pos = compact(msg, pos)
        accounts = list(msg[pos:pos + n_acc])
        pos += n_acc
        n_data, pos = compact(msg, pos)
        data = msg[pos:pos + n_data]
        pos += n_data
        if len(accounts) != n_acc or len(data) != n_data:
            raise Refused("truncated message")
        instructions.append((program, accounts, data))
    n_lookups, pos = compact(msg, pos)
    loaded = 0
    for _ in range(n_lookups):
        pos += 32
        for _ in range(2):
            n, pos = compact(msg, pos)
            pos += n
            loaded += n
    if pos != len(msg):
        raise Refused("trailing or truncated message bytes")
    if len(set(keys)) != len(keys):
        raise Refused("duplicate keys")
    return header, keys, instructions, loaded


# checks --------------------------------------------------------------------------

def usdc_atoms(text):
    if not isinstance(text, str) or not USDC_TEXT.match(text):
        raise Refused("mandate amount is not a USDC decimal string")
    whole, _, frac = text.partition(".")
    return int(whole) * 10**6 + int((frac + "000000")[:6])


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Refused("duplicate JSON key")
        out[key] = value
    return out


def strict_json(text):
    def bad_constant(value):
        raise Refused("non-finite JSON")
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=bad_constant)


def amount_atoms(text, pattern, decimals, what):
    if not isinstance(text, str) or not pattern.match(text):
        raise Refused("mandate %s is not a decimal string" % what)
    whole, _, frac = text.partition(".")
    return int(whole) * 10**decimals + int((frac + "0" * decimals)[:decimals])


def load_mandate(path, now):
    with open(path, "rb") as handle:
        raw = handle.read(65537)
    mandate = strict_json(raw.decode("utf-8"))
    if not isinstance(mandate, dict) or set(mandate) != set(MANDATE_KEYS):
        raise Refused("mandate keys are not exactly the expected set")
    b58decode32(mandate["wallet_pubkey"])
    expires = mandate["expires_at"]
    if isinstance(expires, bool) or not isinstance(expires, (int, float)) or expires <= now:
        raise Refused("mandate expired or invalid expires_at")
    mints = mandate["allowed_mints"]
    if not isinstance(mints, list) or any(m not in (SOL_MINT, USDC_MINT) for m in mints):
        raise Refused("mandate allowed_mints invalid")
    slippage = mandate["max_slippage_bps"]
    if type(slippage) is not int or not 1 <= slippage <= 300:
        raise Refused("mandate max_slippage_bps invalid")
    limits = {k: usdc_atoms(mandate[k]) for k in ("max_trade_usdc", "max_position_usdc")}
    limits["max_trade_sol"] = amount_atoms(mandate["max_trade_sol"], SOL_TEXT, 9, "max_trade_sol")
    limits["max_slippage_bps"] = slippage
    if limits["max_trade_sol"] <= 0:
        raise Refused("mandate max_trade_sol must be positive")
    return mandate, hashlib.sha256(raw).hexdigest(), limits


def check_arm(path, mandate_sha, wallet):
    try:
        with open(path, "rb") as handle:
            arm = strict_json(handle.read(16384).decode("utf-8"))
    except FileNotFoundError:
        raise Refused("not armed (no arm file)") from None
    if not isinstance(arm, dict) or arm.get("mode") != "LIVE":
        raise Refused("not armed for LIVE")
    if arm.get("mandate_sha256") != mandate_sha or arm.get("wallet_pubkey") != wallet:
        raise Refused("arm file does not match the current mandate")


# program-derived addresses (own copy; validity test only, no signing maths) ---------

_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def is_on_curve(raw):
    y = (int.from_bytes(raw, "little") & ((1 << 255) - 1)) % _P
    u, v = (y * y - 1) % _P, (_D * y * y + 1) % _P
    if v == 0:
        return u == 0
    x2 = u * pow(v, _P - 2, _P) % _P
    return x2 == 0 or pow(x2, (_P - 1) // 2, _P) == 1


def find_program_address(seeds, program_id):
    for bump in range(255, -1, -1):
        digest = hashlib.sha256(b"".join(seeds) + bytes([bump]) + b58decode32(program_id)
                                + b"ProgramDerivedAddress").digest()
        if not is_on_curve(digest):
            return b58encode(digest)
    raise Refused("no PDA")


def ata(wallet, mint):
    return find_program_address([b58decode32(wallet), b58decode32(TOKEN_PROGRAM), b58decode32(mint)], ATA_PROGRAM)


# keypair ----------------------------------------------------------------------------

def keypair_file_problems(path, uid, repo=REPO):
    try:
        info = os.lstat(path)
        parent = os.lstat(os.path.dirname(os.path.abspath(path)))
    except OSError:
        return "keypair file missing or not inspectable"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return "keypair path is not a regular file"
    if info.st_uid != uid:
        return "keypair file is not owned by this user"
    if stat.S_IMODE(info.st_mode) & 0o077:
        return "keypair file permissions must be 600"
    if stat.S_ISLNK(parent.st_mode) or parent.st_uid != uid or stat.S_IMODE(parent.st_mode) & 0o022:
        return "keypair directory must be yours, not a symlink, not group/other-writable"
    real = os.path.realpath(path)
    if real == repo or real.startswith(repo.rstrip(os.sep) + os.sep):
        return "keypair file is inside the repository"
    return None


def load_keypair(path, uid, repo=REPO):
    problem = keypair_file_problems(path, uid, repo)
    if problem:
        raise Refused(problem)
    checked = os.lstat(path)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())      # the file we opened is the file we checked (F15)
        if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino) or opened.st_uid != uid \
                or not stat.S_ISREG(opened.st_mode) or stat.S_IMODE(opened.st_mode) & 0o077:
            raise Refused("keypair file changed while it was opened")
        raw = handle.read(4097)
    try:
        values = json.loads(raw.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise Refused("keypair file is not a solana-keygen JSON array") from None
    if not isinstance(values, list) or len(values) != 64 or \
            any(type(v) is not int or not 0 <= v <= 255 for v in values):
        raise Refused("keypair file is not a solana-keygen JSON array")
    key = bytearray(values)
    del values, raw
    return key


# message ------------------------------------------------------------------------------

def decode_jupiter(data):
    data = bytes(data)
    variant = JUPITER_ROUTES.get(data[:8])
    if variant is None:
        raise Refused("Jupiter instruction %s is not an accepted route variant" % data[:8].hex())
    pos = 8 + (1 if variant == "shared_accounts_route" else 0)

    def take(n):
        nonlocal pos
        if pos + n > len(data):
            raise Refused("Jupiter instruction truncated")
        chunk = data[pos:pos + n]
        pos += n
        return chunk
    count = struct.unpack("<I", take(4))[0]
    if not 1 <= count <= MAX_STEPS:
        raise Refused("Jupiter route step count out of range")
    total = 0
    for _ in range(count):
        tag = take(1)[0]
        if tag not in SWAP_FIELD_BYTES:
            raise Refused("Jupiter route uses an unpinned Swap variant %d" % tag)
        if any(b not in (0, 1) for b in take(SWAP_FIELD_BYTES[tag])):
            raise Refused("Jupiter route step field invalid")
        percent, in_index, out_index = take(3)
        if (in_index, out_index) != (0, 1) or not 1 <= percent <= 100:
            raise Refused("Jupiter route step is not a direct input->output step")
        total += percent
    if total != 100:
        raise Refused("Jupiter route percents do not sum to 100")
    in_amount, quoted, slippage, fee = struct.unpack("<QQHB", take(19))
    if pos != len(data):
        raise Refused("Jupiter instruction has trailing bytes")
    if in_amount <= 0 or quoted <= 0 or slippage > 10_000:
        raise Refused("Jupiter instruction arguments out of range")
    return {"in_amount": in_amount, "quoted_out": quoted, "slippage_bps": slippage, "fee_bps": fee,
            "min_out": quoted * (10_000 - slippage) // 10_000}


def check_message(msg, wallet, bundle):
    """Static rules. Returns the decoded Jupiter arguments (the signer's own view of the trade)."""
    header, keys, instructions, loaded = parse_message(msg)
    if header[0] != 1 or header[1] != 0:
        raise Refused("message needs exactly one writable signer")
    if not keys or keys[0] != wallet:
        raise Refused("fee payer is not the mandate wallet")
    total = len(keys) + loaded
    wsol = ata(wallet, SOL_MINT)
    own_atas = {ata(wallet, bundle["input_mint"]), ata(wallet, bundle["output_mint"])}
    priority_limit, price, seen, swaps, outflow = None, 0, set(), [], 0
    for program_index, accounts, data in instructions:
        if program_index >= len(keys):
            raise Refused("program not in static keys")
        if any(a >= total for a in accounts):
            raise Refused("account index out of range")
        program = keys[program_index]
        if program not in ALLOWED_PROGRAMS:
            raise Refused("program %s not allowed" % program)
        static = [keys[a] if a < len(keys) else None for a in accounts]
        if program == COMPUTE_BUDGET_PROGRAM:
            if accounts or not data or data[0] in seen:
                raise Refused("bad compute budget instruction")
            seen.add(data[0])
            if data[0] == 2 and len(data) == 5:
                priority_limit = struct.unpack_from("<I", data, 1)[0]
            elif data[0] == 3 and len(data) == 9:
                price = struct.unpack_from("<Q", data, 1)[0]
            elif data[0] not in (1, 4) or len(data) != 5:
                raise Refused("unknown compute budget instruction")
        elif program == SYSTEM_PROGRAM:
            if len(data) != 12 or struct.unpack_from("<I", data, 0)[0] != 2 or len(static) < 2:
                raise Refused("system instruction other than transfer")
            if bundle["input_mint"] != SOL_MINT or static[0] != wallet:
                raise Refused("system transfer not allowed here")
            if static[1] != wsol:
                raise Refused("system transfer destination is not the wallet's own wSOL account")
            outflow += struct.unpack_from("<Q", data, 4)[0]
        elif program == TOKEN_PROGRAM:
            if len(data) != 1 or data[0] not in (9, 17):
                raise Refused("token instruction not allowed")
            if data[0] == 17 and (not static or static[0] != wsol):
                raise Refused("sync native on a foreign account")
            if data[0] == 9 and (len(static) < 3 or static[0] not in own_atas
                                 or static[1] != wallet or static[2] != wallet):
                raise Refused("close account must be an own ATA and return to the wallet")
        elif program == ATA_PROGRAM:
            if data not in (b"", b"\x00", b"\x01") or len(static) < 6:
                raise Refused("bad associated token account instruction")
            if static[0] != wallet or static[2] != wallet:
                raise Refused("token account not paid by / owned by the wallet")
            if static[3] is not None and static[3] not in (bundle["input_mint"], bundle["output_mint"]):
                raise Refused("token account for a foreign mint")
            if static[1] not in own_atas or (static[3] is not None and static[1] != ata(wallet, static[3])):
                raise Refused("created token account is not the wallet's derived ATA")
        elif program == JUPITER_V6_PROGRAM:
            swaps.append(decode_jupiter(data))
    limit = DEFAULT_CU_LIMIT if priority_limit is None else priority_limit
    if -(-price * limit // 1_000_000) > PRIORITY_CAP_LAMPORTS:
        raise Refused("priority fee above cap")
    if len(swaps) != 1:
        raise Refused("need exactly one Jupiter route instruction")
    swap = swaps[0]
    if outflow > swap["in_amount"]:          # the SUM of all transfers, not per instruction (F1)
        raise Refused("SOL transferred exceeds the swap input")
    return swap


def check_bundle(bundle, msg, mandate, limits, swap):
    """Bounds come from the mandate and the decoded instruction, not from the engine (F1/F3)."""
    side = bundle["side"]
    if swap["in_amount"] != bundle["in_amount"]:
        raise Refused("instruction in_amount differs from the bundle")
    if swap["slippage_bps"] > limits["max_slippage_bps"] or swap["fee_bps"] > MAX_FEE_BPS:
        raise Refused("instruction slippage or fee above the mandate")
    if swap["min_out"] < bundle["min_out"]:
        raise Refused("instruction floor below the order's minimum")
    if side == "BUY":
        if swap["in_amount"] > limits["max_trade_usdc"]:
            raise Refused("BUY input above max_trade_usdc")
        return swap["in_amount"]
    if swap["in_amount"] > limits["max_trade_sol"]:
        raise Refused("SELL input above max_trade_sol")
    return min(swap["min_out"], limits["max_trade_usdc"])


def check_bundle_shape(bundle, msg, mandate):
    if not isinstance(bundle, dict):
        raise Refused("bundle missing")
    if bundle.get("message_sha256") != hashlib.sha256(msg).hexdigest():
        raise Refused("message does not match the verification bundle")
    side, mint_in, mint_out = bundle.get("side"), bundle.get("input_mint"), bundle.get("output_mint")
    expected = {"BUY": (USDC_MINT, SOL_MINT), "SELL": (SOL_MINT, USDC_MINT)}.get(side)
    if expected is None or (mint_in, mint_out) != expected:
        raise Refused("bundle side/mints are inconsistent")
    if mint_in not in mandate["allowed_mints"] or mint_out not in mandate["allowed_mints"]:
        raise Refused("mint not allowed by the mandate")
    for key in ("in_amount", "min_out"):
        if type(bundle.get(key)) is not int or bundle[key] <= 0:
            raise Refused("bundle %s invalid" % key)


def update_state(path, msg_sha, notional, limits, now):
    """Count this signature against today's caps, persist, then allow signing."""
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    state = {"day": day, "count": 0, "notional_usdc_atoms": 0, "messages": []}
    try:
        with open(path, "rb") as handle:
            loaded = strict_json(handle.read(1_000_000).decode("utf-8"))
        if isinstance(loaded, dict) and loaded.get("day") == day:
            state = loaded
    except FileNotFoundError:
        pass
    except (ValueError, UnicodeDecodeError, Refused):
        raise Refused("signer state file is corrupt; inspect it by hand") from None
    if msg_sha in state["messages"]:
        return state          # same bytes -> same deterministic signature; not a new trade
    if state["count"] + 1 > MAX_SIGNATURES_PER_DAY:
        raise Refused("daily signature count cap reached")
    if state["notional_usdc_atoms"] + notional > DAILY_NOTIONAL_FACTOR * limits["max_position_usdc"]:
        raise Refused("daily signed notional cap reached")
    state = {"day": day, "count": state["count"] + 1,
             "notional_usdc_atoms": state["notional_usdc_atoms"] + notional,
             "messages": state["messages"] + [msg_sha]}
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".signer-", dir=directory)
    with os.fdopen(fd, "w") as handle:
        json.dump(state, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return state


def state_path(registry, wallet):
    """The daily-cap file is per WALLET, in the wallet registry, not caller-chosen (F7)."""
    return os.path.join(registry, "%s.signer-state.json" % wallet)


def load_nacl():
    try:
        import nacl.signing as signing  # noqa: PLC0415
        return signing
    except ImportError:
        return None


def handle(request, mandate_path, arm_path, registry, now, signing, uid, repo=REPO):
    """All checks, then the signature. Returns the signature bytes or raises Refused."""
    if signing is None:
        raise Refused(NO_NACL)
    if not isinstance(request, dict) or not isinstance(request.get("message_b64"), str):
        raise Refused("malformed request")
    try:
        msg = base64.b64decode(request["message_b64"], validate=True)
    except ValueError:
        raise Refused("message is not base64") from None
    mandate, mandate_sha, limits = load_mandate(mandate_path, now)
    wallet = mandate["wallet_pubkey"]
    check_arm(arm_path, mandate_sha, wallet)
    bundle = request.get("bundle")
    check_bundle_shape(bundle, msg, mandate)
    swap = check_message(msg, wallet, bundle)
    notional = check_bundle(bundle, msg, mandate, limits, swap)
    key = load_keypair(mandate["keypair_path"], uid, repo)
    try:
        # PyNaCl needs an immutable bytes seed; that copy cannot be wiped (residual, DESIGN §10)
        signing_key = signing.SigningKey(bytes(key[:32]))
        derived = bytes(signing_key.verify_key)
        if derived != bytes(key[32:]) or derived != b58decode32(wallet):
            raise Refused("keypair does not belong to the mandate wallet")
        update_state(state_path(registry, wallet), hashlib.sha256(msg).hexdigest(), notional, limits, now)
        signature = bytes(signing_key.sign(msg).signature)
    finally:
        for i in range(len(key)):
            key[i] = 0
    if len(signature) != 64:
        raise Refused("signature has the wrong length")
    return signature


def main(argv=None, stdin=None, stdout=None, signing=None, now=None, uid=None):
    argv = sys.argv[1:] if argv is None else argv
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    args = dict(zip(argv[::2], argv[1::2]))
    if set(args) != {"--mandate", "--arm", "--registry"} or len(argv) != 6:
        stdout.write(json.dumps({"error": "usage: signer.py --mandate M --arm A --registry DIR"}))
        return 2
    signing = load_nacl() if signing is None else signing
    if signing is None:
        stdout.write(json.dumps({"error": NO_NACL}))
        return 3
    try:
        request = strict_json(stdin.read(200_000))
        signature = handle(request, args["--mandate"], args["--arm"], args["--registry"],
                           time.time() if now is None else now, signing,
                           os.getuid() if uid is None else uid)
    except Refused as exc:
        stdout.write(json.dumps({"error": "refused: %s" % exc}))
        return 4
    except Exception as exc:  # never echo contents; type name only
        stdout.write(json.dumps({"error": "signer failure: %s" % type(exc).__name__}))
        return 5
    stdout.write(json.dumps({"signature": b58encode(signature)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
