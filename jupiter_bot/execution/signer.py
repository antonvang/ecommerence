"""Restricted signer process. Standalone on purpose: no jupiter_bot imports.

Started by the engine as `python3 -I <this file> --mandate M --arm A --state S`
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
    System transfers only from the wallet and only when SOL is the input,
    Token instructions only SyncNative/CloseAccount-to-wallet, ATA creations
    paid by and owned by the wallet;
  * the bundle: sha256 matches the message, mints SOL/USDC and allowed, the
    trade notional <= max_trade_usdc;
  * its own per-UTC-day caps (count and notional) kept in its own state file,
    updated BEFORE the signature is released.
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
MANDATE_KEYS = ("wallet_pubkey", "keypair_path", "rpc_url", "max_trade_usdc", "max_position_usdc",
                "daily_loss_limit_usdc", "max_slippage_bps", "allowed_mints", "strategy", "params",
                "expires_at")
USDC_TEXT = re.compile(r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,6})?$")
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
    limits = {k: usdc_atoms(mandate[k]) for k in ("max_trade_usdc", "max_position_usdc")}
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


def keypair_file_problems(path, uid, repo=REPO):
    try:
        info = os.lstat(path)
    except OSError:
        return "keypair file missing or not inspectable"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return "keypair path is not a regular file"
    if info.st_uid != uid:
        return "keypair file is not owned by this user"
    if stat.S_IMODE(info.st_mode) & 0o077:
        return "keypair file permissions must be 600"
    real = os.path.realpath(path)
    if real == repo or real.startswith(repo.rstrip(os.sep) + os.sep):
        return "keypair file is inside the repository"
    return None


def load_keypair(path, uid, repo=REPO):
    problem = keypair_file_problems(path, uid, repo)
    if problem:
        raise Refused(problem)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
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


def check_message(msg, wallet, bundle):
    header, keys, instructions, loaded = parse_message(msg)
    if header[0] != 1 or header[1] != 0:
        raise Refused("message needs exactly one writable signer")
    if not keys or keys[0] != wallet:
        raise Refused("fee payer is not the mandate wallet")
    total = len(keys) + loaded
    priority_limit, price, seen, jupiter = None, 0, set(), 0
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
            if struct.unpack_from("<Q", data, 4)[0] > bundle["in_amount"]:
                raise Refused("system transfer larger than the order")
        elif program == TOKEN_PROGRAM:
            if len(data) != 1 or data[0] not in (9, 17):
                raise Refused("token instruction not allowed")
            if data[0] == 9 and (len(static) < 3 or static[1] != wallet or static[2] != wallet):
                raise Refused("close account must return to the wallet")
        elif program == ATA_PROGRAM:
            if data not in (b"", b"\x00", b"\x01") or len(static) < 6:
                raise Refused("bad associated token account instruction")
            if static[0] != wallet or static[2] != wallet:
                raise Refused("token account not paid by / owned by the wallet")
            if static[3] is not None and static[3] not in (bundle["input_mint"], bundle["output_mint"]):
                raise Refused("token account for a foreign mint")
        elif program == JUPITER_V6_PROGRAM:
            jupiter += 1
    limit = DEFAULT_CU_LIMIT if priority_limit is None else priority_limit
    if -(-price * limit // 1_000_000) > PRIORITY_CAP_LAMPORTS:
        raise Refused("priority fee above cap")
    if jupiter < 1:
        raise Refused("no Jupiter instruction")


def check_bundle(bundle, msg, mandate, limits):
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
    notional = bundle["in_amount"] if side == "BUY" else bundle["min_out"]
    if notional > limits["max_trade_usdc"]:
        raise Refused("trade notional above max_trade_usdc")
    return notional


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
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".signer-", dir=directory)
    with os.fdopen(fd, "w") as handle:
        json.dump(state, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return state


def load_nacl():
    try:
        import nacl.signing as signing  # noqa: PLC0415
        return signing
    except ImportError:
        return None


def handle(request, mandate_path, arm_path, state_path, now, signing, uid, repo=REPO):
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
    notional = check_bundle(bundle, msg, mandate, limits)
    check_message(msg, wallet, bundle)
    key = load_keypair(mandate["keypair_path"], uid, repo)
    try:
        signing_key = signing.SigningKey(bytes(key[:32]))
        derived = bytes(signing_key.verify_key)
        if derived != bytes(key[32:]) or derived != b58decode32(wallet):
            raise Refused("keypair does not belong to the mandate wallet")
        update_state(state_path, hashlib.sha256(msg).hexdigest(), notional, limits, now)
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
    if set(args) != {"--mandate", "--arm", "--state"} or len(argv) != 6:
        stdout.write(json.dumps({"error": "usage: signer.py --mandate M --arm A --state S"}))
        return 2
    signing = load_nacl() if signing is None else signing
    if signing is None:
        stdout.write(json.dumps({"error": NO_NACL}))
        return 3
    try:
        request = strict_json(stdin.read(200_000))
        signature = handle(request, args["--mandate"], args["--arm"], args["--state"],
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
