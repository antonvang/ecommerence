"""Decode a Jupiter v6 swap instruction FRONT TO BACK, exactly as Anchor/Borsh does (F3, N1).

SOURCE AND STATUS: no Jupiter v6 IDL is available locally, and the docs (facts §4)
do not publish one. The layout below is the Anchor/Borsh layout of the program
`JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` as published in its IDL (jup-ag
`jupiter-cpi` / on-chain IDL account), REPRODUCED FROM MEMORY and therefore
**UNCONFIRMED**. It must be confirmed against real `/order` transactions in
DRY_RUN before arming. The discriminators are computed as `sha256("global:<name>")[:8]`
(Anchor's rule). For `route` (e517cb977ae3ad2a) and `shared_accounts_route`
(c1209b3341d69c81) they equal the known values.

    route(route_plan: Vec<RoutePlanStep>, in_amount: u64, quoted_out_amount: u64,
          slippage_bps: u16, platform_fee_bps: u8)
    shared_accounts_route(id: u8, route_plan: Vec<RoutePlanStep>, in_amount: u64,
          quoted_out_amount: u64, slippage_bps: u16, platform_fee_bps: u8)
    RoutePlanStep { swap: Swap, percent: u8, input_index: u8, output_index: u8 }
    Vec<T> = u32 length + elements; Swap = u8 variant tag + that variant's fields.

Every byte must be consumed, so appended data is rejected (N1: Anchor reads from
the front and may ignore a tail, so a tail must never be what we check). Only
the `Swap` variants pinned in SWAP_VARIANTS are accepted; any other tag means we
do not know where the step ends, so the instruction is rejected. For SOL/USDC
direct routes every step must go input_index 0 -> output_index 1, and the
percents must sum to exactly 100.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from ..core import Rejected


def discriminator(name):
    return hashlib.sha256(("global:" + name).encode()).digest()[:8]


ACCEPTED = {discriminator("route"): "route", discriminator("shared_accounts_route"): "shared_accounts_route"}
KNOWN_REJECTED = {discriminator(n): n for n in (
    "route_with_token_ledger", "shared_accounts_route_with_token_ledger", "exact_out_route",
    "shared_accounts_exact_out_route", "route_v2", "shared_accounts_route_v2", "exact_out_route_v2",
    "shared_accounts_exact_out_route_v2")}

# Swap enum tag -> (name, field layout). Field kinds: "bool" (u8 0/1), "side" (u8 enum Bid=0/Ask=1).
# PINNED FROM MEMORY (UNCONFIRMED): only variants whose position and fields I am confident of,
# and that map to programs on config.DEX_PROGRAMS. Everything else is rejected.
SWAP_VARIANTS = {
    7: ("Raydium", ()),
    17: ("Whirlpool", ("bool",)),          # a_to_b
    25: ("LifinityV2", ()),
    26: ("RaydiumClmm", ()),
    28: ("Phoenix", ("side",)),
    38: ("MeteoraDlmm", ()),
    39: ("OpenBookV2", ("side",)),
    46: ("RaydiumCP", ()),
}
MAX_STEPS = 8
ARGS = struct.Struct("<QQHB")      # in_amount, quoted_out_amount, slippage_bps, platform_fee_bps


@dataclass(frozen=True)
class SwapArgs:
    variant: str
    in_amount: int
    quoted_out_amount: int
    slippage_bps: int
    platform_fee_bps: int
    steps: tuple = ()

    @property
    def min_out(self):
        """The floor the program enforces: quoted * (10000 - slippage) / 10000, rounded down."""
        return self.quoted_out_amount * (10_000 - self.slippage_bps) // 10_000

    def as_dict(self):
        return {"variant": self.variant, "in_amount": self.in_amount,
                "quoted_out_amount": self.quoted_out_amount, "slippage_bps": self.slippage_bps,
                "platform_fee_bps": self.platform_fee_bps, "min_out": self.min_out,
                "steps": [dict(s) for s in self.steps]}


class _Reader:
    def __init__(self, data):
        self.data, self.pos = bytes(data), 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise Rejected("Jupiter instruction data is truncated")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self):
        return self.take(1)[0]


def _step(reader):
    tag = reader.u8()
    if tag not in SWAP_VARIANTS:
        raise Rejected("Jupiter route uses Swap variant tag %d, which is not pinned" % tag)
    name, fields = SWAP_VARIANTS[tag]
    values = []
    for kind in fields:
        value = reader.u8()
        if value not in (0, 1):
            raise Rejected("Jupiter route step %s has an invalid %s value %d" % (name, kind, value))
        values.append(value)
    percent, input_index, output_index = reader.u8(), reader.u8(), reader.u8()
    return {"swap": name, "tag": tag, "fields": values, "percent": percent,
            "input_index": input_index, "output_index": output_index}


def decode(data):
    data = bytes(data)
    head = data[:8]
    variant = ACCEPTED.get(head)
    if variant is None:
        name = KNOWN_REJECTED.get(head, "unknown")
        raise Rejected("Jupiter instruction %s (discriminator %s) is not accepted" % (name, head.hex()))
    reader = _Reader(data)
    reader.take(8)
    if variant == "shared_accounts_route":
        reader.u8()                                    # id
    count, = struct.unpack("<I", reader.take(4))
    if not 1 <= count <= MAX_STEPS:
        raise Rejected("Jupiter route has %d steps" % count)
    steps = tuple(_step(reader) for _ in range(count))
    in_amount, quoted, slippage, fee = ARGS.unpack(reader.take(ARGS.size))
    if reader.pos != len(data):
        raise Rejected("Jupiter instruction has %d unexplained trailing bytes" % (len(data) - reader.pos))
    if any((s["input_index"], s["output_index"]) != (0, 1) for s in steps):
        raise Rejected("Jupiter route is not a direct input->output route")
    if any(not 1 <= s["percent"] <= 100 for s in steps) or sum(s["percent"] for s in steps) != 100:
        raise Rejected("Jupiter route percents do not sum to 100")
    if in_amount <= 0 or quoted <= 0 or slippage > 10_000:
        raise Rejected("Jupiter %s arguments out of range" % variant)
    return SwapArgs(variant, in_amount, quoted, slippage, fee, steps)
