"""Amendment 29a point 3, hypothesis V1: public order-book round-trip cost on EU-authorised venues against Binance.

Every 15 minutes outside K3 windows it reads each venue's public order book for the common coins (same minute,
seconds apart; no account) and stores, per venue and coin: mid, spread, and the walk cost of a 15-unit buy and sell
against mid in bp. `report` gives per coin the median of (venue - Binance) round trip in bp from the books alone;
published taker fees are added only once verified from the venue's own fee page (FEES, status per venue).

  python3 research/tools/v1_books.py run [--samples N]     (writes data/v1/books.jsonl)
  python3 research/tools/v1_books.py report
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
from pilot.core import k3_window  # noqa: E402

OUT = os.path.join(HERE, "data", "v1", "books.jsonl")
NOTIONAL = 15.0                                 # in the book's quote currency (EUR books: 15 EUR)
EVERY_S = 15 * 60
COINS = ("BTC", "ETH", "XTZ", "VET")
FEES = {   # published lowest-tier spot taker fee: None until read from the venue's own page (amendment 29a point 3)
    "Binance": None, "Kraken": None, "Bitstamp": None, "OKX": None, "Bitvavo": None, "Coinbase": None}


BITSTAMP = {"BTC": "btcusdt", "ETH": "ethusdt", "XTZ": "xtzeur"}     # no XTZ/USDT, no VET (1cb4581)


def _levels(xs):
    return [(float(a[0]), float(a[1])) for a in xs]


VENUES = {   # name -> (url per coin or None, parser -> (bids, asks))
    "Binance": (lambda c: f"https://data-api.binance.vision/api/v3/depth?symbol={c}USDT&limit=100",
                lambda d: (_levels(d["bids"]), _levels(d["asks"]))),
    "Kraken": (lambda c: f"https://api.kraken.com/0/public/Depth?pair={'XBT' if c == 'BTC' else c}USDT&count=100",
               lambda d: next((_levels(v["bids"]), _levels(v["asks"])) for v in d["result"].values())),
    "Bitstamp": (lambda c: BITSTAMP.get(c) and f"https://www.bitstamp.net/api/v2/order_book/{BITSTAMP[c]}/",
                 lambda d: (_levels(d["bids"]), _levels(d["asks"]))),
    "OKX": (lambda c: c in ("BTC", "ETH", "XTZ") and f"https://www.okx.com/api/v5/market/books?instId={c}-USDT&sz=100",
            lambda d: (_levels(d["data"][0]["bids"]), _levels(d["data"][0]["asks"]))),
    "Bitvavo": (lambda c: f"https://api.bitvavo.com/v2/{c}-{'USDC' if c in ('BTC', 'ETH') else 'EUR'}/book?depth=100",
                lambda d: (_levels(d["bids"]), _levels(d["asks"]))),
    "Coinbase": (lambda c: f"https://api.exchange.coinbase.com/products/{c}-{'USDT' if c in ('BTC', 'ETH') else 'USD'}"
                           f"/book?level=2",
                 lambda d: (_levels(d["bids"]), _levels(d["asks"]))),
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "copybot-research"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def walk_bp(levels, mid, notional):
    """Cost in bp against mid of filling `notional` quote units through `levels`; None if the book is too thin."""
    got_q, got_quote = 0.0, 0.0
    for px, q in levels:
        take = min(q, (notional - got_quote) / px)
        got_q += take
        got_quote += take * px
        if got_quote >= notional - 1e-9:
            return abs(got_quote / got_q - mid) / mid * 1e4
    return None


def measure(bids, asks, notional=NOTIONAL):
    bids, asks = sorted(bids, key=lambda x: -x[0]), sorted(asks, key=lambda x: x[0])
    if not bids or not asks or bids[0][0] >= asks[0][0]:
        return {"error": "crossed or empty book"}
    mid = (bids[0][0] + asks[0][0]) / 2
    buy, sell = walk_bp(asks, mid, notional), walk_bp(bids, mid, notional)
    return {"mid": mid, "spread_bp": round((asks[0][0] - bids[0][0]) / mid * 1e4, 3),
            "buy_bp": None if buy is None else round(buy, 3), "sell_bp": None if sell is None else round(sell, 3),
            "rt_bp": None if buy is None or sell is None else round(buy + sell, 3)}


def sample(fetch=get, now=time.time):
    rows = []
    for coin in COINS:
        for venue, (url_of, parse) in VENUES.items():
            url = url_of(coin)
            if not url:
                continue
            t = now()
            try:
                row = measure(*parse(fetch(url)))
            except Exception as e:                              # noqa: BLE001 - recorded, never filled in
                row = {"error": repr(e)[:160]}
            rows.append({"ts": round(t, 3), "coin": coin, "venue": venue, **row})
    return rows


def run(samples, out=OUT, fetch=get, now=time.time, sleep=time.sleep):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    done = 0
    while done < samples:
        while k3_window(now()) or k3_window(now() + 120):
            sleep(60)
        with open(out, "a", encoding="utf-8") as fh:
            for r in sample(fetch, now):
                fh.write(json.dumps(r) + "\n")
        done += 1
        if done < samples:
            sleep(EVERY_S)
    return done


def report(path=OUT):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    by = {}
    for r in rows:
        if r.get("rt_bp") is not None:
            by.setdefault((r["coin"], int(r["ts"] // 600)), {})[r["venue"]] = r["rt_bp"]    # same 10-minute sample
    out = {"rows": len(rows), "errors": sum(1 for r in rows if "error" in r), "coins": {}}
    hours = (rows[-1]["ts"] - rows[0]["ts"]) / 3600 if len(rows) > 1 else 0
    out["hours"] = round(hours, 1)
    for coin in COINS:
        c = {}
        for venue in VENUES:
            if venue == "Binance":
                continue
            diffs = [v[venue] - v["Binance"] for (k, _), v in by.items() if k == coin and venue in v and "Binance" in v]
            if diffs:
                c[venue] = {"n": len(diffs), "median_diff_bp": round(statistics.median(diffs), 2),
                            "books_only": True}
        out["coins"][coin] = c
    out["fees"] = FEES
    out["note"] = "kun ordrebøger; gebyrer lægges til, når de er læst på børsens egen side; V1-dom kræver >= 50 pr. mønt over >= 48 t"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run").add_argument("--samples", type=int, default=400)
    sub.add_parser("report")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        print(run(a.samples), "prøver")
    else:
        print(json.dumps(report(), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
