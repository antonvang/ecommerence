"""Minimal Solana JSON-RPC client for the mandate's own RPC endpoint.

Only the methods the adapter needs. Every result is shape-checked; an RPC
error, a missing field or a wrong type is `RpcError` (a `Rejected`).
"""
from __future__ import annotations

import base64
import itertools
from urllib.parse import urlsplit

from ..core import Rejected
from .http import SafeHTTP
from .solana_tx import TOKEN_PROGRAM, is_pubkey


class RpcError(Rejected):
    pass


def _int(value, what):
    if type(value) is not int or value < 0:
        raise RpcError("RPC %s is not an unsigned integer" % what)
    return value


def decode_account(value):
    """Normalise a base64-encoded account object or None."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RpcError("RPC account is not an object")
    data = value.get("data")
    if not (isinstance(data, list) and len(data) == 2 and data[1] == "base64" and isinstance(data[0], str)):
        raise RpcError("RPC account data is not base64")
    owner = value.get("owner")
    if not isinstance(owner, str) or not is_pubkey(owner):
        raise RpcError("RPC account owner is invalid")
    try:
        raw = base64.b64decode(data[0], validate=True)
    except ValueError as exc:
        raise RpcError("RPC account data is not valid base64") from exc
    return {"lamports": _int(value.get("lamports"), "lamports"), "owner": owner, "data": raw,
            "executable": value.get("executable") is True}


class Rpc:
    def __init__(self, url, http=None, timeout=15.0):
        self.url = url
        self.http = http or SafeHTTP([urlsplit(url).hostname])
        self.timeout = timeout
        self._ids = itertools.count(1)

    def call(self, method, params):
        request_id = next(self._ids)
        status, body = self.http.request("POST", self.url, {"jsonrpc": "2.0", "id": request_id,
                                                            "method": method, "params": params},
                                         timeout=self.timeout)
        if status != 200 or not isinstance(body, dict):
            raise RpcError("RPC %s: HTTP %s" % (method, status))
        if body.get("error") is not None:
            error = body["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise RpcError("RPC %s error %s" % (method, code))
        if body.get("id") != request_id or "result" not in body:
            raise RpcError("RPC %s: malformed response" % method)
        return body["result"]

    @staticmethod
    def _context(result, method):
        if not isinstance(result, dict) or not isinstance(result.get("context"), dict):
            raise RpcError("RPC %s: missing context" % method)
        return _int(result["context"].get("slot"), "slot"), result.get("value")

    def block_height(self, commitment):
        return _int(self.call("getBlockHeight", [{"commitment": commitment}]), "block height")

    def multiple_accounts(self, addresses, commitment="confirmed"):
        result = self.call("getMultipleAccounts", [list(addresses), {"encoding": "base64",
                                                                     "commitment": commitment}])
        slot, value = self._context(result, "getMultipleAccounts")
        if not isinstance(value, list) or len(value) != len(addresses):
            raise RpcError("getMultipleAccounts returned the wrong number of accounts")
        return slot, [decode_account(v) for v in value]

    def account_info(self, address, commitment="confirmed"):
        result = self.call("getAccountInfo", [address, {"encoding": "base64", "commitment": commitment}])
        _, value = self._context(result, "getAccountInfo")
        return decode_account(value)

    def token_accounts_by_owner(self, owner, program=TOKEN_PROGRAM, commitment="confirmed"):
        result = self.call("getTokenAccountsByOwner", [owner, {"programId": program},
                                                       {"encoding": "base64", "commitment": commitment}])
        slot, value = self._context(result, "getTokenAccountsByOwner")
        if not isinstance(value, list):
            raise RpcError("getTokenAccountsByOwner value is not a list")
        out = []
        for item in value:
            if not isinstance(item, dict) or not is_pubkey(item.get("pubkey") or ""):
                raise RpcError("getTokenAccountsByOwner item is malformed")
            out.append((item["pubkey"], decode_account(item.get("account"))))
        return slot, out

    def simulate(self, tx_b64, addresses):
        result = self.call("simulateTransaction", [tx_b64, {
            "encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": False,
            "commitment": "confirmed",
            "accounts": {"encoding": "base64", "addresses": list(addresses)}}])
        slot, value = self._context(result, "simulateTransaction")
        if not isinstance(value, dict):
            raise RpcError("simulateTransaction value is not an object")
        accounts = value.get("accounts")
        if not isinstance(accounts, list) or len(accounts) != len(addresses):
            raise RpcError("simulateTransaction did not return the requested accounts")
        logs = value.get("logs") if isinstance(value.get("logs"), list) else []
        return {"slot": slot, "err": value.get("err"), "logs": [str(l)[:300] for l in logs[:200]],
                "accounts": [decode_account(a) for a in accounts],
                "units": value.get("unitsConsumed")}

    def signature_status(self, signature):
        result = self.call("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
        _, value = self._context(result, "getSignatureStatuses")
        if not isinstance(value, list) or len(value) != 1:
            raise RpcError("getSignatureStatuses returned the wrong number of entries")
        status = value[0]
        if status is None:
            return None
        if not isinstance(status, dict) or status.get("confirmationStatus") not in (
                "processed", "confirmed", "finalized"):
            raise RpcError("getSignatureStatuses entry is malformed")
        return {"slot": status.get("slot"), "err": status.get("err"),
                "confirmation": status["confirmationStatus"]}

    def transaction(self, signature):
        result = self.call("getTransaction", [signature, {"commitment": "finalized", "encoding": "json",
                                                          "maxSupportedTransactionVersion": 0}])
        if result is not None and not isinstance(result, dict):
            raise RpcError("getTransaction result is malformed")
        return result
