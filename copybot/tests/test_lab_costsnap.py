"""Amendment 21h point 2: the cost snapshot walks every trading USDT perp's book for 5 000 USD, paced, and summarises
by volume decile and class without inventing a cost for a thin book."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import costsnap  # noqa: E402


def market(n=30):
    syms = [{"symbol": f"C{i}USDT", "status": "TRADING", "quoteAsset": "USDT", "contractType": "PERPETUAL"}
            for i in range(n)]
    syms += [{"symbol": "XAUUSDT", "status": "TRADING", "quoteAsset": "USDT", "contractType": "TRADIFI_PERPETUAL",
              "underlyingType": "COMMODITY"},
             {"symbol": "OLDUSDT", "status": "SETTLING", "quoteAsset": "USDT", "contractType": "PERPETUAL"},
             {"symbol": "BTCUSDT_261225", "status": "TRADING", "quoteAsset": "USDT", "contractType": "CURRENT_QUARTER"},
             {"symbol": "THINUSDT", "status": "TRADING", "quoteAsset": "USDT", "contractType": "PERPETUAL"}]

    def get(url):
        if url.endswith("exchangeInfo"):
            return {"symbols": syms}
        if url.endswith("ticker/24hr"):
            return [{"symbol": s["symbol"], "quoteVolume": str(1e6 * (int(s["symbol"][1:-4]) + 1)
                                                               if s["symbol"][1:-4].isdigit() else 5e5)} for s in syms]
        sym = url.split("symbol=")[1].split("&")[0]
        if sym == "THINUSDT":
            return {"bids": [["1.0", "10"]], "asks": [["1.01", "10"]]}
        k = int(sym[1:-4]) + 1 if sym[1:-4].isdigit() else 5
        step = 0.01 / k                                               # deeper and tighter with more volume
        return {"bids": [[f"{100 - step * (j + 1):.6f}", "10"] for j in range(100)],
                "asks": [[f"{100 + step * (j + 1):.6f}", "10"] for j in range(100)]}
    return get


class Snapshot(unittest.TestCase):
    def test_only_trading_usdt_perps_paced_and_no_invented_costs(self):
        waits = []
        rep = costsnap.snapshot(market(), sleep=waits.append, now=1.0)
        syms = [r["symbol"] for r in rep["rows"]]
        self.assertNotIn("OLDUSDT", syms)
        self.assertNotIn("BTCUSDT_261225", syms)
        self.assertEqual(len(waits), len(syms))
        self.assertTrue(all(w == costsnap.PACE_S for w in waits))
        thin = next(r for r in rep["rows"] if r["symbol"] == "THINUSDT")
        self.assertIsNone(thin["round_trip"])
        self.assertIn("thin", thin["error"])
        s = rep["summary"]
        self.assertEqual(s["too_thin_or_error"], 1)
        self.assertEqual(s["tradfi"]["n"], 1)
        self.assertLess(s["crypto"]["loglog_fit"]["slope"], 0)                    # cheaper with more volume
        self.assertEqual(len(s["crypto"]["deciles_by_volume"]), 10)


if __name__ == "__main__":
    unittest.main()
