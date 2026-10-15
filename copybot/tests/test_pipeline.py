"""Hele backtest-kæden med falske API-svar (ingen netværk)."""
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest  # noqa: E402
import market  # noqa: E402
import net  # noqa: E402
import solana_rpc  # noqa: E402
from copybot import DEFAULTS, merge  # noqa: E402
from store import Store  # noqa: E402
from swaps import WSOL  # noqa: E402
from tests.test_copybot import MINT, W, pumpfun_buy, raydium_sell  # noqa: E402

NOW = int(time.time())
T_BUY, T_SELL = NOW - 3 * 86400, NOW - 3 * 86400 + 1800


def fake_http(url, payload=None, **kw):
    if payload is not None:  # Solana RPC
        m, p = payload["method"], payload["params"]
        if m == "getSignaturesForAddress":
            if p[1].get("before"):
                return {"result": []}
            return {"result": [{"signature": "sig2", "blockTime": T_SELL, "err": None},
                               {"signature": "sig1", "blockTime": T_BUY, "err": None}]}
        if m == "getTransaction":
            t = pumpfun_buy() if p[0] == "sig1" else raydium_sell()
            t["blockTime"] = T_BUY if p[0] == "sig1" else T_SELL
            return {"result": t}
    if "dexscreener" in url:
        if WSOL in url:
            return [{"baseToken": {"address": WSOL, "symbol": "SOL"}, "quoteToken": {"address": market.USDC},
                     "pairAddress": "SOLPOOL", "liquidity": {"usd": 1e7}, "priceUsd": "150"}]
        return [{"baseToken": {"address": MINT, "symbol": "TOAD"}, "quoteToken": {"address": WSOL},
                 "pairAddress": "TOADPOOL", "liquidity": {"usd": 9000}, "priceUsd": "0.0003"}]
    if "geckoterminal" in url:
        before = int(url.split("before_timestamp=")[1].split("&")[0])
        if "/ohlcv/hour" in url:
            return {"data": {"attributes": {"ohlcv_list": [[t, 150, 150, 150, 150, 1] for t in range(before - 3600 * 999, before, 3600)][::-1]}}}
        start = T_BUY - 300
        rows = [[t, 0.00015, 0.00015, 0.00015, 0.00015 + (t - start) * 1e-8, 1] for t in range(start - start % 60, T_SELL + 900, 60) if t < before]
        return {"data": {"attributes": {"ohlcv_list": rows[::-1]}}}
    raise AssertionError(url)


class Pipeline(unittest.TestCase):
    def test_backtest_end_to_end(self):
        root = tempfile.mkdtemp()
        cfg = merge(DEFAULTS, {"min_liquidity_usd": 5000, "next_trader": "list", "rpc_requests_per_second": 1000})
        out = io.StringIO()
        try:
            with mock.patch.object(market, "http_json", fake_http), mock.patch.object(solana_rpc, "http_json", fake_http), \
                    mock.patch.object(net.Throttle, "wait", lambda self: None), redirect_stdout(out):
                backtest.run_backtest(cfg, [{"addr": W, "label": "kai_blitz"}], root, days=7, sweep=True, log=print)
            text = out.getvalue()
            self.assertIn("BACKTEST", text)
            self.assertIn("Videoens regel", text)
            s = Store(os.path.join(root, "backtest.db"))
            rows = s.q("SELECT * FROM positions ORDER BY book")
            self.assertEqual({r["book"] for r in rows}, {"port", "shadow"})
            for r in rows:
                self.assertEqual(r["reason"], "leader")
                self.assertEqual(r["symbol"], "TOAD")
            s.close()
        finally:
            shutil.rmtree(root)


class HeliusHistory(unittest.TestCase):
    def test_backtest_with_get_transactions_for_address(self):
        calls = []

        def http(url, payload=None, **kw):
            if payload is not None and payload["method"] == "getTransactionsForAddress":
                calls.append(payload["params"][1])
                b, s = pumpfun_buy(), raydium_sell()
                b["blockTime"], s["blockTime"] = T_BUY, T_SELL
                if payload["params"][1].get("paginationToken"):
                    return {"result": {"data": [b], "paginationToken": None}}
                return {"result": {"data": [s], "paginationToken": "1:1"}}
            if payload is not None:
                raise AssertionError(f"langsom metode brugt: {payload['method']}")
            return fake_http(url, payload, **kw)

        root = tempfile.mkdtemp()
        cfg = merge(DEFAULTS, {"min_liquidity_usd": 5000, "next_trader": "list", "rpc_url": "https://mainnet.helius-rpc.com/?api-key=x"})
        try:
            with mock.patch.object(market, "http_json", http), mock.patch.object(solana_rpc, "http_json", http), \
                    mock.patch.object(net.Throttle, "wait", lambda self: None), redirect_stdout(io.StringIO()):
                backtest.run_backtest(cfg, [{"addr": W, "label": "kai_blitz"}], root, days=7, sweep=False, log=print)
            s = Store(os.path.join(root, "backtest.db"))
            self.assertEqual({r["reason"] for r in s.q("SELECT reason FROM positions")}, {"leader"})
            s.close()
        finally:
            shutil.rmtree(root)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["filters"]["status"], "succeeded")

    def test_falls_back_when_method_missing(self):
        def http(url, payload=None, **kw):
            return {"error": {"code": -32601, "message": "Method not found"}}

        with mock.patch.object(solana_rpc, "http_json", http), mock.patch.object(net.Throttle, "wait", lambda self: None):
            rpc = solana_rpc.RPC("https://mainnet.helius-rpc.com/?api-key=x", log=lambda *a: None)
            self.assertIsNone(rpc.history("w", 0))
            self.assertFalse(rpc.has_history)


class TxVersion(unittest.TestCase):
    def test_retries_with_newer_transaction_version(self):
        asked = []

        def http(url, payload=None, **kw):
            v = payload["params"][1]["maxSupportedTransactionVersion"]
            asked.append(v)
            if v < 2:
                return {"error": {"code": -32015, "message": "Transaction version (2) is not supported by the requesting "
                                  "client. Please try the request again with the following configuration parameter: "
                                  "\"maxSupportedTransactionVersion\": 2"}}
            return {"result": {"version": 2}}

        with mock.patch.object(solana_rpc, "http_json", http), mock.patch.object(net.Throttle, "wait", lambda self: None):
            rpc = solana_rpc.RPC("x")
            self.assertEqual(rpc.transaction("a"), {"version": 2})
            self.assertEqual(rpc.transaction("b"), {"version": 2})
        self.assertEqual(asked, [1, 2, 2])


if __name__ == "__main__":
    unittest.main()
