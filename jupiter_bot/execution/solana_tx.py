"""Solana wire format: base58, compact-u16, legacy/v0 messages, lookup tables.

Decoding only, and strict: anything malformed, ambiguous or unsupported is
`Rejected`. Nothing here talks to the network. Layouts follow
https://solana.com/docs/core/transactions/transaction-structure and
.../versioned-transactions (see research/JUPITER_API_FACTS.md section 7).
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from ..core import Rejected

B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {ch: i for i, ch in enumerate(B58_ALPHABET)}

PACKET_DATA_SIZE = 1232
SIGNATURE_LEN = 64
PUBKEY_LEN = 32
V0_PREFIX = 0x80

SYSTEM_PROGRAM = "11111111111111111111111111111111"
COMPUTE_BUDGET_PROGRAM = "ComputeBudget111111111111111111111111111111"
ALT_PROGRAM = "AddressLookupTab1e1111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
JUPITER_V6_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"

ALT_META_SIZE = 56
ALT_MAX_ADDRESSES = 256
U64_MAX = 2**64 - 1
TOKEN_ACCOUNT_LEN = 165


# base58 -------------------------------------------------------------------------

def b58encode(data):
    data = bytes(data)
    number = int.from_bytes(data, "big")
    out = []
    while number:
        number, rem = divmod(number, 58)
        out.append(B58_ALPHABET[rem])
    pad = len(data) - len(data.lstrip(b"\0"))
    return "1" * pad + "".join(reversed(out))


def b58decode(text, length=None):
    if not isinstance(text, str) or not text or len(text) > 128:
        raise Rejected("Invalid base58 string")
    number = 0
    for ch in text:
        if ch not in _B58_INDEX:
            raise Rejected("Invalid base58 character")
        number = number * 58 + _B58_INDEX[ch]
    pad = len(text) - len(text.lstrip("1"))
    body = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    raw = b"\0" * pad + body
    if b58encode(raw) != text:
        raise Rejected("Non-canonical base58 string")
    if length is not None and len(raw) != length:
        raise Rejected("base58 value has the wrong length")
    return raw


def pubkey_bytes(text):
    return b58decode(text, PUBKEY_LEN)


def is_pubkey(text):
    try:
        pubkey_bytes(text)
        return True
    except Rejected:
        return False


# ed25519 curve membership and program-derived addresses -----------------------------
# Only a point-validity test (like curve25519-dalek's CompressedEdwardsY::decompress,
# which Solana's `bytes_are_curve_point` uses). No signing, no secret maths.

_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
MAX_SEED_LEN, MAX_SEEDS = 32, 16


def is_on_curve(raw):
    raw = bytes(raw)
    if len(raw) != 32:
        raise Rejected("A curve point has 32 bytes")
    y = (int.from_bytes(raw, "little") & ((1 << 255) - 1)) % _P
    u, v = (y * y - 1) % _P, (_D * y * y + 1) % _P
    if v == 0:
        return u == 0
    x2 = u * pow(v, _P - 2, _P) % _P
    return x2 == 0 or pow(x2, (_P - 1) // 2, _P) == 1


def create_program_address(seeds, program_id):
    if len(seeds) > MAX_SEEDS or any(len(seed) > MAX_SEED_LEN for seed in seeds):
        raise Rejected("Invalid PDA seeds")
    digest = hashlib.sha256(b"".join(bytes(s) for s in seeds) + pubkey_bytes(program_id)
                            + b"ProgramDerivedAddress").digest()
    if is_on_curve(digest):
        raise Rejected("Seeds give an on-curve address")
    return b58encode(digest)


def find_program_address(seeds, program_id):
    for bump in range(255, -1, -1):
        try:
            return create_program_address(list(seeds) + [bytes([bump])], program_id), bump
        except Rejected:
            continue
    raise Rejected("No viable PDA bump")


def associated_token_address(wallet, mint, token_program=None):
    token_program = token_program or TOKEN_PROGRAM
    return find_program_address([pubkey_bytes(wallet), pubkey_bytes(token_program), pubkey_bytes(mint)],
                                ATA_PROGRAM)[0]


# compact-u16 --------------------------------------------------------------------

def encode_compact_u16(value):
    if type(value) is not int or not 0 <= value <= 0xFFFF:
        raise Rejected("compact-u16 out of range")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_compact_u16(buf, offset):
    value = 0
    for i in range(3):
        if offset + i >= len(buf):
            raise Rejected("Truncated compact-u16")
        byte = buf[offset + i]
        if i == 2 and byte > 0x03:
            raise Rejected("compact-u16 overflow")
        value |= (byte & 0x7F) << (7 * i)
        if not byte & 0x80:
            if i > 0 and byte == 0:
                raise Rejected("Non-canonical compact-u16")
            return value, offset + i + 1
    raise Rejected("compact-u16 too long")


class _Reader:
    def __init__(self, buf):
        self.buf, self.pos = bytes(buf), 0

    def take(self, n):
        if n < 0 or self.pos + n > len(self.buf):
            raise Rejected("Truncated transaction data")
        chunk = self.buf[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self):
        return self.take(1)[0]

    def compact(self):
        value, self.pos = decode_compact_u16(self.buf, self.pos)
        return value

    def done(self):
        if self.pos != len(self.buf):
            raise Rejected("Trailing bytes after transaction data")


# messages -----------------------------------------------------------------------

@dataclass(frozen=True)
class Instruction:
    program_index: int
    accounts: tuple
    data: bytes


@dataclass(frozen=True)
class Lookup:
    table: str
    writable: tuple
    readonly: tuple


@dataclass(frozen=True)
class Message:
    version: object          # None = legacy, 0 = v0
    num_required_signatures: int
    num_readonly_signed: int
    num_readonly_unsigned: int
    static_keys: tuple       # base58 strings
    recent_blockhash: str
    instructions: tuple
    lookups: tuple
    raw: bytes

    @property
    def fee_payer(self):
        return self.static_keys[0]

    @property
    def signers(self):
        return self.static_keys[:self.num_required_signatures]

    def loaded_count(self):
        return sum(len(l.writable) + len(l.readonly) for l in self.lookups)

    def static_writable(self, index):
        n, req = len(self.static_keys), self.num_required_signatures
        if index < req:
            return index < req - self.num_readonly_signed
        return index < n - self.num_readonly_unsigned


def parse_message(raw):
    raw = bytes(raw)
    r = _Reader(raw)
    if not raw:
        raise Rejected("Empty message")
    version = None
    if raw[0] & 0x80:
        if raw[0] != V0_PREFIX:
            raise Rejected("Unsupported transaction version (only legacy and v0 are decoded)")
        r.u8()
        version = 0
    num_req, ro_signed, ro_unsigned = r.u8(), r.u8(), r.u8()
    count = r.compact()
    keys = tuple(b58encode(r.take(PUBKEY_LEN)) for _ in range(count))
    if len(set(keys)) != len(keys):
        raise Rejected("Duplicate static account keys")
    if not 1 <= num_req <= len(keys):
        raise Rejected("Invalid signer count")
    if ro_signed >= num_req:
        raise Rejected("Fee payer must be a writable signer")
    if ro_unsigned > len(keys) - num_req:
        raise Rejected("Invalid read-only account count")
    blockhash = b58encode(r.take(32))
    instructions = []
    for _ in range(r.compact()):
        program = r.u8()
        accounts = tuple(r.u8() for _ in range(r.compact()))
        data = r.take(r.compact())
        instructions.append(Instruction(program, accounts, data))
    lookups = []
    if version == 0:
        for _ in range(r.compact()):
            table = b58encode(r.take(PUBKEY_LEN))
            writable = tuple(r.u8() for _ in range(r.compact()))
            readonly = tuple(r.u8() for _ in range(r.compact()))
            if not writable and not readonly:
                raise Rejected("Empty address table lookup")
            lookups.append(Lookup(table, writable, readonly))
    r.done()
    message = Message(version, num_req, ro_signed, ro_unsigned, keys, blockhash,
                      tuple(instructions), tuple(lookups), raw)
    total = len(keys) + message.loaded_count()
    if total > 256:
        raise Rejected("Too many accounts")
    for ix in message.instructions:
        if ix.program_index >= total or any(a >= total for a in ix.accounts):
            raise Rejected("Instruction references a missing account")
    return message


@dataclass(frozen=True)
class Transaction:
    signatures: tuple        # raw 64-byte values
    message: Message

    def serialize(self):
        return (encode_compact_u16(len(self.signatures)) + b"".join(self.signatures)
                + self.message.raw)


def parse_transaction(raw):
    raw = bytes(raw)
    if len(raw) > PACKET_DATA_SIZE:
        raise Rejected("Transaction larger than %d bytes" % PACKET_DATA_SIZE)
    count, offset = decode_compact_u16(raw, 0)
    end = offset + count * SIGNATURE_LEN
    if end > len(raw):
        raise Rejected("Truncated signatures")
    signatures = tuple(raw[offset + i * SIGNATURE_LEN: offset + (i + 1) * SIGNATURE_LEN]
                       for i in range(count))
    message = parse_message(raw[end:])
    if count != message.num_required_signatures:
        raise Rejected("Signature count does not match the message header")
    return Transaction(signatures, message)


def with_signature(tx, index, signature):
    if len(signature) != SIGNATURE_LEN or not 0 <= index < len(tx.signatures):
        raise Rejected("Bad signature placement")
    sigs = list(tx.signatures)
    sigs[index] = bytes(signature)
    return Transaction(tuple(sigs), tx.message)


# lookup tables and account resolution ---------------------------------------------

def parse_lookup_table(data):
    """Addresses of an ACTIVE address lookup table account (owner checked by caller)."""
    data = bytes(data)
    if len(data) < ALT_META_SIZE or (len(data) - ALT_META_SIZE) % PUBKEY_LEN:
        raise Rejected("Malformed address lookup table")
    tag, = struct.unpack_from("<I", data, 0)
    if tag != 1:
        raise Rejected("Account is not an initialised lookup table")
    deactivation_slot, = struct.unpack_from("<Q", data, 4)
    if deactivation_slot != U64_MAX:
        raise Rejected("Lookup table is deactivated")
    count = (len(data) - ALT_META_SIZE) // PUBKEY_LEN
    if count > ALT_MAX_ADDRESSES:
        raise Rejected("Lookup table too large")
    return [b58encode(data[ALT_META_SIZE + i * 32: ALT_META_SIZE + (i + 1) * 32]) for i in range(count)]


@dataclass(frozen=True)
class AccountMeta:
    key: str
    signer: bool
    writable: bool
    from_lookup: bool


def resolve_accounts(message, tables):
    """Full account list: static keys, then all ALT writable, then all ALT read-only.

    `tables` maps table address -> list of addresses (from parse_lookup_table).
    """
    metas = [AccountMeta(key, i < message.num_required_signatures, message.static_writable(i), False)
             for i, key in enumerate(message.static_keys)]
    writable, readonly = [], []
    for lookup in message.lookups:
        addresses = tables.get(lookup.table)
        if addresses is None:
            raise Rejected("Lookup table was not resolved")
        for target, indexes in ((writable, lookup.writable), (readonly, lookup.readonly)):
            for index in indexes:
                if index >= len(addresses):
                    raise Rejected("Lookup index outside the table")
                target.append(addresses[index])
    metas += [AccountMeta(k, False, True, True) for k in writable]
    metas += [AccountMeta(k, False, False, True) for k in readonly]
    keys = [m.key for m in metas]
    if len(set(keys)) != len(keys):
        raise Rejected("An account is loaded twice (static and/or lookup table)")
    return metas


# SPL token accounts -----------------------------------------------------------------

@dataclass(frozen=True)
class TokenAccount:
    mint: str
    owner: str
    amount: int
    delegate: object
    state: int
    close_authority: object


def parse_token_account(data):
    """Classic SPL Token account (165 bytes). Token-2022 extensions are rejected."""
    data = bytes(data)
    if len(data) != TOKEN_ACCOUNT_LEN:
        raise Rejected("Not a classic SPL token account")
    mint, owner = b58encode(data[0:32]), b58encode(data[32:64])
    amount, = struct.unpack_from("<Q", data, 64)

    def option_key(offset):
        tag, = struct.unpack_from("<I", data, offset)
        if tag not in (0, 1):
            raise Rejected("Malformed token account option")
        return b58encode(data[offset + 4: offset + 36]) if tag else None

    delegate = option_key(72)
    state = data[108]
    if state not in (1, 2):
        raise Rejected("Token account is not initialised")
    close_authority = option_key(129)
    return TokenAccount(mint, owner, amount, delegate, state, close_authority)
