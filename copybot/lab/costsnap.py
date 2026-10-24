"""PROTOCOL_V3 amendment 21h point 2: one descriptive snapshot of execution cost across Binance USD-M perps.

For every trading USDT perpetual (crypto and TradFi): the half spread and the book round trip of 5 000 USD (buy and sell
VWAP through `fapi/v1/depth`, the same walk as amendment 21), its 24 h quote volume and class. Public GET on the allowed
fapi host, at most 4 depth calls a second. One moment, no history: a description, never a decision.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time

from lab import moves

PACE_S = 0.25                                                  # at most 4 depth calls a second
FEE = {"crypto": 0.0005, "tradfi": 0.0004}                     # per side: lab model (crypto), verified promo (21g)
HURDLES = (0.0046, 0.0065)


def snapshot(get, sleep=time.sleep, now=None):
    info = get(f"{moves.BN}/fapi/v1/exchangeInfo")
    vol = {t["symbol"]: float(t.get("quoteVolume") or 0) for t in get(f"{moves.BN}/fapi/v1/ticker/24hr")}
    rows = []
    for s in info["symbols"]:
        if s.get("status") != "TRADING" or s.get("quoteAsset") != "USDT" or \
                s.get("contractType") not in ("PERPETUAL", "TRADIFI_PERPETUAL"):
            continue
        cls = "tradfi" if s["contractType"] == "TRADIFI_PERPETUAL" else "crypto"
        b = moves.book_cost(get, s["symbol"])
        sleep(PACE_S)
        rows.append({"symbol": s["symbol"], "class": cls, "underlying": s.get("underlyingType"),
                     "volume_24h": vol.get(s["symbol"], 0.0), "round_trip": b.get("round_trip"),
                     "spread": b.get("spread"), "error": b.get("error")})
    return {"rule": "research/PROTOCOL_V3.md amendment 21h point 2", "ts": now or time.time(), "size_usd": moves.SIZE_USD,
            "fee_per_side": FEE, "rows": rows, "summary": summary(rows)}


def summary(rows):
    ok = [r for r in rows if r["round_trip"] is not None and r["volume_24h"] > 0]
    out = {"symbols": len(rows), "with_cost": len(ok), "too_thin_or_error": len(rows) - len(ok)}
    for cls in ("crypto", "tradfi"):
        sub = sorted((r for r in ok if r["class"] == cls), key=lambda r: r["volume_24h"])
        if not sub:
            continue
        k = len(sub)
        deciles = []
        for i in range(10):
            part = sub[i * k // 10:(i + 1) * k // 10]
            if part:
                deciles.append({"n": len(part), "volume_median": statistics.median(r["volume_24h"] for r in part),
                                "round_trip_median": statistics.median(r["round_trip"] for r in part),
                                "round_trip_max": max(r["round_trip"] for r in part)})
        net = [r["round_trip"] + 2 * FEE[cls] for r in sub]
        xs = [math.log(r["volume_24h"]) for r in sub if r["round_trip"] > 0]
        ys = [math.log(r["round_trip"]) for r in sub if r["round_trip"] > 0]
        fit = None
        if len(xs) >= 3 and statistics.pvariance(xs) > 0:
            mx, my = statistics.fmean(xs), statistics.fmean(ys)
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
            fit = {"slope": slope, "intercept": my - slope * mx, "n": len(xs)}
        out[cls] = {"n": k, "deciles_by_volume": deciles, "loglog_fit": fit,
                    "share_net_over": {str(h): sum(1 for v in net if v > h) / k for h in HURDLES},
                    "net_median": statistics.median(net)}
    out["thin_or_error_symbols"] = [r["symbol"] for r in rows if r["round_trip"] is None][:50]
    return out


def main(argv=None):
    from lab import news
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="write <out>.json")
    a = ap.parse_args(argv)
    rep = snapshot(lambda url: json.loads(news.http_get(url)))
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(json.dumps(rep["summary"], indent=1))


if __name__ == "__main__":
    sys.exit(main())
