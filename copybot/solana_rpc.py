"""Minimal Solana JSON-RPC-klient (læser kun, sender aldrig transaktioner)."""
from __future__ import annotations

from net import DiskCache, Throttle, http_json


class RPCError(Exception):
    pass


class RPC:
    def __init__(self, url, requests_per_second=3, cache_dir=None, log=print):
        self.url = url
        self.th = Throttle(1.0 / max(requests_per_second, 0.1))
        self.cache = DiskCache(cache_dir)
        self.log = log

    def call(self, method, params):
        self.th.wait()
        r = http_json(self.url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, log=self.log)
        if "error" in r:
            raise RPCError(f"{method}: {r['error']}")
        return r.get("result")

    def signatures(self, address, before=None, until=None, limit=1000):
        opts = {"limit": limit, "commitment": "confirmed"}
        if before:
            opts["before"] = before
        if until:
            opts["until"] = until
        return self.call("getSignaturesForAddress", [address, opts]) or []

    def transaction(self, signature):
        tx = self.cache.get("tx:" + signature)
        if tx is not None:
            return tx
        tx = self.call("getTransaction", [signature, {
            "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
        if tx is not None:
            self.cache.put("tx:" + signature, tx)
        return tx
