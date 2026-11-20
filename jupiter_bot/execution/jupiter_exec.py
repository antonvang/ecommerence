"""Jupiter `/swap/v2/order` (with taker) and `/swap/v2/execute`.

The order request pins everything we can: taker, explicit slippageBps, a priority
fee cap, v0 transactions, and excludes every router except metis (Jupiter v6),
so the taker is the fee payer and the only signer and the transaction id is
known before `/execute` (JUPITER_API_FACTS.md sections 3-4).

`check_order` rejects any response that does not match the request exactly.
`/execute` answers are recorded but never trusted for the outcome: the chain is.
"""
from __future__ import annotations

import base64
import re
import time
import urllib.parse
from dataclasses import dataclass
from decimal import Decimal

from ..core import SOL, USDC, Rejected, positive_integer
from . import config
from .http import SafeHTTP, TransportError, TransportTimeout

BASE = "https://api.jup.ag/swap/v2"
ORDER_URL = BASE + "/order"
EXECUTE_URL = BASE + "/execute"
REQUEST_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")


@dataclass(frozen=True)
class OrderRequest:
    side: str              # BUY = USDC -> SOL, SELL = SOL -> USDC
    input_mint: str
    output_mint: str
    amount: int
    taker: str
    slippage_bps: int

    def params(self):
        return {"inputMint": self.input_mint, "outputMint": self.output_mint, "amount": str(self.amount),
                "taker": self.taker, "slippageBps": str(self.slippage_bps), "swapMode": "ExactIn",
                "excludeRouters": config.EXCLUDED_ROUTERS, "maxSupportedTransactionVersion": "0",
                "priorityFeeLamports": str(config.PRIORITY_CAP_LAMPORTS), "broadcastFeeType": "maxCap"}


def make_request(side, amount, mandate):
    if side == "BUY":
        input_mint, output_mint = USDC.mint, SOL.mint
    elif side == "SELL":
        input_mint, output_mint = SOL.mint, USDC.mint
    else:
        raise Rejected("Unknown side")
    if input_mint not in mandate.allowed_mints or output_mint not in mandate.allowed_mints:
        raise Rejected("Order mints are not in the mandate's allowed_mints")
    if type(amount) is not int:
        raise Rejected("Order amount must be integer atoms")
    positive_integer(amount)
    return OrderRequest(side, input_mint, output_mint, amount, mandate.wallet_pubkey, mandate.max_slippage_bps)


@dataclass(frozen=True)
class Order:
    request: OrderRequest
    request_id: str
    transaction: bytes
    out_amount: int
    min_out: int               # otherAmountThreshold
    last_valid_block_height: int
    fee_bps: int
    received_at: float
    payload: dict


def _price_usdc_per_sol(request, out_amount):
    if request.side == "BUY":   # USDC atoms in, lamports out
        return Decimal(request.amount) / 10**6 / (Decimal(out_amount) / 10**9)
    return Decimal(out_amount) / 10**6 / (Decimal(request.amount) / 10**9)


def check_order(request, payload, received_at, reference_price=None):
    """Return a verified `Order` or raise Rejected. Unknown extra fields are ignored."""
    if not isinstance(payload, dict):
        raise Rejected("/order response is not an object")
    if payload.get("error") or payload.get("errorMessage") or payload.get("errorCode") not in (None, 0):
        raise Rejected("/order reported an error (code %r)" % payload.get("errorCode"))
    router = payload.get("router")
    if router not in config.ACCEPTED_ROUTERS:
        raise Rejected("Router %r is not accepted (only metis)" % router)
    if payload.get("gasless") is not False:
        raise Rejected("Gasless or unknown gasless state")
    for field in ("quoteId", "maker", "expireAt"):
        if payload.get(field) not in (None, ""):
            raise Rejected("RFQ field %s present; RFQ orders are not accepted" % field)
    if payload.get("taker") != request.taker:
        raise Rejected("Order taker does not match the mandate wallet")
    if payload.get("signatureFeePayer") != request.taker:
        raise Rejected("Signature fee payer is not the taker")
    for field in ("prioritizationFeePayer", "rentFeePayer"):
        if payload.get(field) not in (None, request.taker):
            raise Rejected("%s is not the taker" % field)
    if payload.get("inputMint") != request.input_mint or payload.get("outputMint") != request.output_mint:
        raise Rejected("Order mints do not match the request")
    if positive_integer(payload.get("inAmount")) != request.amount:
        raise Rejected("Order inAmount does not match the request")
    if payload.get("swapMode", "ExactIn") != "ExactIn":
        raise Rejected("Only ExactIn orders are accepted")
    slippage = payload.get("slippageBps")
    if type(slippage) is not int or slippage != request.slippage_bps:
        raise Rejected("Order slippageBps does not equal the requested value")
    out_amount = positive_integer(payload.get("outAmount"))
    min_out = positive_integer(payload.get("otherAmountThreshold"))
    floor = -(-out_amount * (10_000 - request.slippage_bps) // 10_000)   # ceil
    if not floor <= min_out <= out_amount:
        raise Rejected("otherAmountThreshold violates the slippage limit")
    fee = payload.get("feeBps")
    if type(fee) is not int or not 0 <= fee <= config.MAX_FEE_BPS:
        raise Rejected("feeBps missing or above %d" % config.MAX_FEE_BPS)
    if payload.get("feeMint") not in (None, request.input_mint, request.output_mint):
        raise Rejected("Fee charged in a mint outside the swap")
    if payload.get("transactionVersion") not in (None, 0):
        raise Rejected("Only v0 transactions are accepted")
    route = payload.get("routePlan")
    if not isinstance(route, list) or not route:
        raise Rejected("Empty or missing route plan")
    for leg in route:
        info = leg.get("swapInfo") if isinstance(leg, dict) else None
        if not isinstance(info, dict) or info.get("inputMint") not in (SOL.mint, USDC.mint) \
                or info.get("outputMint") not in (SOL.mint, USDC.mint):
            raise Rejected("Route leg uses a mint outside SOL/USDC")
    request_id = payload.get("requestId")
    if not isinstance(request_id, str) or not REQUEST_ID.match(request_id):
        raise Rejected("Missing or malformed requestId")
    lvbh = payload.get("lastValidBlockHeight")
    if isinstance(lvbh, bool) or not isinstance(lvbh, (str, int)):
        raise Rejected("Missing lastValidBlockHeight")
    last_valid = positive_integer(lvbh)
    tx_b64 = payload.get("transaction")
    if not isinstance(tx_b64, str) or not tx_b64:
        raise Rejected("Order has no transaction")
    try:
        tx = base64.b64decode(tx_b64, validate=True)
    except ValueError as exc:
        raise Rejected("Order transaction is not base64") from exc
    if reference_price is not None:
        price = _price_usdc_per_sol(request, out_amount)
        deviation = abs(price / Decimal(reference_price) - 1) * 10_000
        if deviation > config.MAX_PRICE_DEVIATION_BPS:
            raise Rejected("Order price %.4f deviates %.0f bps from the journal price %s"
                           % (price, deviation, reference_price))
    return Order(request, request_id, tx, out_amount, min_out, last_valid, fee, received_at, payload)


@dataclass(frozen=True)
class ExecuteAnswer:
    outcome: str        # "ACCEPTED" (200 + Success + our signature) or "UNKNOWN"
    http_status: object
    detail: str
    payload: object


class JupiterExec:
    def __init__(self, http=None, clock=time.time, monotonic=time.monotonic, sleep=time.sleep,
                 execute_timeout=60.0):
        self.http = http or SafeHTTP(["api.jup.ag"])
        self.clock, self.monotonic, self.sleep = clock, monotonic, sleep
        self.execute_timeout = execute_timeout
        self._last = None

    def _pace(self):
        # keyless limit is 0.5 RPS; one order per cycle anyway
        if self._last is not None:
            wait = 2.1 - (self.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.monotonic()

    def order(self, request, reference_price=None):
        self._pace()
        url = ORDER_URL + "?" + urllib.parse.urlencode(sorted(request.params().items()))
        status, body = self.http.request("GET", url)
        received = self.clock()
        if status != 200:
            raise Rejected("/order HTTP %s" % status)
        return check_order(request, body, received, reference_price)

    def execute(self, signed_tx, request_id, expected_signature):
        """Never raises for network trouble: returns UNKNOWN instead."""
        payload = {"signedTransaction": base64.b64encode(signed_tx).decode(), "requestId": request_id}
        try:
            status, body = self.http.request("POST", EXECUTE_URL, payload, timeout=self.execute_timeout)
        except TransportTimeout:
            return ExecuteAnswer("UNKNOWN", None, "timeout", None)
        except TransportError as exc:
            return ExecuteAnswer("UNKNOWN", None, str(exc), None)
        if status == 200 and isinstance(body, dict) and body.get("status") == "Success":
            if body.get("signature") == expected_signature:
                return ExecuteAnswer("ACCEPTED", status, "Success", body)
            return ExecuteAnswer("UNKNOWN", status, "Success with a different signature", body)
        code = body.get("code") if isinstance(body, dict) else None
        return ExecuteAnswer("UNKNOWN", status, "HTTP %s code %r" % (status, code), body)
