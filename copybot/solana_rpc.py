"""Minimal Solana JSON-RPC-klient (læser kun, sender aldrig transaktioner)."""
from __future__ import annotations

import queue
import re
import threading

from net import DiskCache, Throttle, http_json


class RPCError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


class RPC:
    def __init__(self, url, requests_per_second=3, cache_dir=None, log=print):
        self.url = url
        self.th = Throttle(1.0 / max(requests_per_second, 0.1))
        self.cache = DiskCache(cache_dir)
        self.log = log
        self.tx_version = 1  # Solana har version 0 og 1 transaktioner; nyere versioner fanges i transaction()
        self.has_history = "helius" in url  # Helius' getTransactionsForAddress: hele transaktioner, 1000 pr. kald

    def call(self, method, params):
        self.th.wait()
        r = http_json(self.url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, log=self.log)
        if "error" in r:
            err = r["error"]
            raise RPCError(f"{method}: {err}", err.get("code") if isinstance(err, dict) else None)
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
        try:
            tx = self._get_tx(signature)
        except RPCError as e:
            m = re.search(r'"maxSupportedTransactionVersion": (\d+)', str(e))
            if e.code != -32015 or not m or int(m.group(1)) <= self.tx_version:
                raise
            self.tx_version = int(m.group(1))  # ny transaktionsversion på kæden: spørg efter den fremover
            tx = self._get_tx(signature)
        if tx is not None:
            self.cache.put("tx:" + signature, tx)
        return tx

    def history(self, address, t0, t1=None):
        """Alle lykkedes transaktioner for en adresse i [t0, t1), nyeste først. None hvis RPC'en ikke kan det.

        Meget hurtigere end signatures() + transaction() for wallets, der får tusindvis af spam-transaktioner.
        """
        if not self.has_history:
            return None
        bt = {"gte": int(t0)}
        if t1:
            bt["lt"] = int(t1)
        out, token = [], None
        while True:
            opts = {"transactionDetails": "full", "encoding": "jsonParsed", "maxSupportedTransactionVersion": self.tx_version,
                    "sortOrder": "desc", "limit": 1000, "commitment": "confirmed",
                    "filters": {"blockTime": bt, "status": "succeeded"}}
            if token:
                opts["paginationToken"] = token
            try:
                r = self.call("getTransactionsForAddress", [address, opts]) or {}
            except RPCError as e:
                if out:
                    raise
                self.has_history = False
                self.log(f"  getTransactionsForAddress virker ikke her ({e}) · bruger den langsomme metode")
                return None
            out += r.get("data") or []
            token = r.get("paginationToken")
            if not token or not r.get("data"):
                return out

    def prefetch(self, signatures, extra=(), log=None):
        """Henter ikke-cachede transaktioner parallelt fra denne og ekstra RPC'er (hver med sin egen hastighed).

        Fejler et kald, springes det over her; transaction() prøver så igen bagefter.
        """
        todo = [sg for sg in signatures if self.cache.get("tx:" + sg) is None]
        if not todo:
            return
        clients = [self] + [RPC(e["url"], e.get("rps", 1), self.cache.folder, log=lambda *a: None) for e in extra]
        q = queue.Queue()
        for sg in todo:
            q.put(sg)
        done = [0]
        lock = threading.Lock()

        def work(c):
            while True:
                try:
                    sg = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    c.transaction(sg)
                except Exception:
                    pass
                with lock:
                    done[0] += 1
                    if log and done[0] % 200 == 0:
                        log(f"    hentet {done[0]}/{len(todo)} (fra {len(clients)} servere)")

        ts = [threading.Thread(target=work, args=(c,), daemon=True) for c in clients]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

    def _get_tx(self, signature):
        return self.call("getTransaction", [signature, {
            "encoding": "jsonParsed", "maxSupportedTransactionVersion": self.tx_version, "commitment": "confirmed"}])
