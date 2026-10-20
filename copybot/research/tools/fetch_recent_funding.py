"""Fetch recent settled funding (public, read-only): Binance USD-M fundingRate (limit 1000 per perp) and Hyperliquid
fundingHistory (last 60 days). Throttled well below both venues' limits. Writes JSON files to the output dir."""
import json, os, sys, time, urllib.request
out = sys.argv[1]
UA = {"User-Agent": "copybot-research/1.0 (read-only study)"}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read())

def post(body):
    req = urllib.request.Request("https://api.hyperliquid.xyz/info", data=json.dumps(body).encode(),
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

info = get("https://fapi.binance.com/fapi/v1/exchangeInfo")
perps = sorted(s["symbol"] for s in info["symbols"] if s.get("contractType") == "PERPETUAL"
               and s.get("underlyingType") == "COIN" and s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT")
bn = {}
for i, s in enumerate(perps):
    try:
        bn[s] = [(int(x["fundingTime"]) // 1000, float(x["fundingRate"])) for x in
                 get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={s}&limit=1000")]
    except Exception as e:
        bn[s] = {"error": repr(e)}
    time.sleep(0.7)                       # fundingRate: 500 requests / 5 min / IP; this is ~85
json.dump(bn, open(os.path.join(out, "binance_funding.json"), "w"))
spot_info = get("https://data-api.binance.vision/api/v3/exchangeInfo")   # public spot market data (GET only)
spot = sorted(s["symbol"] for s in spot_info["symbols"] if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT")
json.dump(spot, open(os.path.join(out, "spot_symbols.json"), "w"))      # recent_study.py: coins with a Binance spot
meta, ctxs = post({"type": "metaAndAssetCtxs"})
coins = [a["name"] for a in meta["universe"] if not a.get("isDelisted") and not a["name"].startswith(("k", "@"))]
hl, start = {}, int(time.time() * 1000) - 60 * 86400 * 1000
for c in coins:
    rows, t = [], start
    try:
        for _ in range(4):
            got = post({"type": "fundingHistory", "coin": c, "startTime": t})
            rows += [(int(x["time"]) // 1000, float(x["fundingRate"])) for x in got]
            if len(got) < 500:
                break
            t = int(got[-1]["time"]) + 1
            time.sleep(0.3)
        hl[c] = rows
    except Exception as e:
        hl[c] = {"error": repr(e)}
    time.sleep(0.3)
json.dump(hl, open(os.path.join(out, "hl_funding.json"), "w"))
print("binance perps", len(perps), "errors", sum(isinstance(v, dict) for v in bn.values()),
      "| hl coins", len(coins), "errors", sum(isinstance(v, dict) for v in hl.values()))
