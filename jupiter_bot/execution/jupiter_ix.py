"""Decode the fixed arguments of a Jupiter v6 swap instruction (F3).

SOURCE AND STATUS: no Jupiter v6 IDL is available locally and the docs (facts §4)
do not publish one. The layout below is the Anchor/Borsh layout of the Jupiter
v6 program `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` as published in its
IDL (jup-ag `jupiter-cpi` / on-chain IDL account), reproduced from memory and
therefore **UNCONFIRMED**. The discriminators are recomputed here from
`sha256("global:<name>")[:8]` (Anchor's rule); they equal the values known for
`route` (e517cb977ae3ad2a) and `shared_accounts_route` (c1209b3341d69c81).

    route(route_plan: Vec<RoutePlanStep>, in_amount: u64, quoted_out_amount: u64,
          slippage_bps: u16, platform_fee_bps: u8)
    shared_accounts_route(id: u8, route_plan: Vec<RoutePlanStep>, in_amount: u64,
          quoted_out_amount: u64, slippage_bps: u16, platform_fee_bps: u8)

Both end with the same 19 fixed bytes, so they are read from the END of the data
(the variable route_plan, a Vec of a large enum, is not decoded). Only these two
ExactIn variants are accepted:
  * *_with_token_ledger variants have no in_amount (it comes from a ledger account),
    so the amount cannot be checked statically -> rejected;
  * exact_out variants are not ExactIn -> rejected;
  * route_v2 / shared_accounts_route_v2 exist in newer program versions but their
    argument order could not be confirmed -> rejected until a real /order
    transaction from DRY_RUN shows the layout and a reviewer approves the change.
Every DRY_RUN records the decoded fields and, on rejection, the discriminator hex,
so the layout can be checked against a real transaction before arming.
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
TRAILER = struct.Struct("<QQHB")       # in_amount, quoted_out_amount, slippage_bps, platform_fee_bps
MIN_LEN = {"route": 8 + 4 + TRAILER.size, "shared_accounts_route": 8 + 1 + 4 + TRAILER.size}


@dataclass(frozen=True)
class SwapArgs:
    variant: str
    in_amount: int
    quoted_out_amount: int
    slippage_bps: int
    platform_fee_bps: int

    @property
    def min_out(self):
        """The floor the program enforces: quoted * (10000 - slippage) / 10000, rounded down."""
        return self.quoted_out_amount * (10_000 - self.slippage_bps) // 10_000

    def as_dict(self):
        return {"variant": self.variant, "in_amount": self.in_amount,
                "quoted_out_amount": self.quoted_out_amount, "slippage_bps": self.slippage_bps,
                "platform_fee_bps": self.platform_fee_bps, "min_out": self.min_out}


def decode(data):
    data = bytes(data)
    head = data[:8]
    variant = ACCEPTED.get(head)
    if variant is None:
        name = KNOWN_REJECTED.get(head, "unknown")
        raise Rejected("Jupiter instruction %s (discriminator %s) is not accepted" % (name, head.hex()))
    if len(data) < MIN_LEN[variant]:
        raise Rejected("Jupiter %s instruction data too short" % variant)
    in_amount, quoted, slippage, fee = TRAILER.unpack(data[-TRAILER.size:])
    if in_amount <= 0 or quoted <= 0 or slippage > 10_000:
        raise Rejected("Jupiter %s arguments out of range" % variant)
    return SwapArgs(variant, in_amount, quoted, slippage, fee)
