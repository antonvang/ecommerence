"""Amendment 29a point 3, hypothesis V1: public order-book round-trip cost on EU-authorised venues against Binance.

Every 15 minutes outside K3 windows it reads each venue's public order book for the common coins (same minute,
seconds apart; no account) and stores, per venue and coin: mid, spread, and the walk cost of a 15-unit buy and sell
against mid in bp. `report` gives per coin the median of (venue - Binance) round trip in bp from the books alone;
published taker fees (FEES, amendment 29b) are added only once verified from the venue's own fee page; else None.

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
FEES = {   # lowest-tier spot taker fee read on the venue's own page (amendment 29b point 1); None = uafklaret
    "Binance": {"taker": 0.001, "read": "2026-10-27", "url": "https://www.binance.com/en/fee/schedule",
                "quote": "Regular User 0.100% / 0.100%"},
    "Kraken": {"taker": 0.008, "read": "2026-10-27", "url": "https://www.kraken.com/features/fee-schedule",
               "quote": "Tier 1 $0+ < $5M N/A 0.40 % 0.80 %"},
    "OKX": {"taker": 0.002, "read": "2026-10-27", "url": "https://www.okx.com/en-us/help/important-notice-upcoming-"
            "adjustment-to-vip-trading-volume-tiers-europe", "quote": "| Regular | 0 | 0 | 0.100% | 0.200% | (spot only)"},
    "Bitstamp": {"taker": 0.004, "read": "2026-10-27", "url": "https://www.bitstamp.net/fee-schedule/",
                 "quote": "< $10,000 | 0.30% | 0.40% (standard; valid from 21 October 2026)"},
    "Bitvavo": {"taker": {"EUR": 0.0025, "USDC": 0.0005}, "read": "2026-10-27", "url": "https://bitvavo.com/en/fees",
                "quote": "A, EUR markets: €0 + | 0.15% | 0.25%; B, USDC markets: €0 + | 0.05% | 0.05%"},
    "Coinbase": {"taker": 0.005, "read": "2026-10-27", "url": "https://www.coinbase.com/blog/were-lowering-fees-for-"
                 "many-active-traders-on-coinbase-advanced", "quote": "EU and UK: 0.25% maker & 0.50% taker"}}
QUOTE = {"Bitvavo": lambda c: "USDC" if c in ("BTC", "ETH") else "EUR"}   # the market V1 reads (see VENUES)


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
    "OKX": (lambda c: c in ("BTC", "ETH", "XTZ") and f"https://eea.okx.com/api/v5/market/books?instId={c}-USDT&sz=100",
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


def taker(venue, coin):
    """The venue's taker fee for the market V1 reads for `coin` (amendment 29c point 3), None if uafklaret."""
    f = FEES.get(venue)
    if not f:
        return None
    t = f["taker"]
    return t.get(QUOTE[venue](coin)) if isinstance(t, dict) else t


def with_fees(venue, coin="BTC"):
    """Extra round-trip fee in bp of `venue` over Binance (2 x taker each), None while either fee is uafklaret."""
    a, b = taker(venue, coin), taker("Binance", coin)
    if a is None or b is None:
        return None
    return 2 * (a - b) * 1e4


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
                fee_bp = with_fees(venue, coin)
                c[venue]["median_diff_with_fees_bp"] = (None if fee_bp is None else
                                                        round(statistics.median(diffs) + fee_bp, 2))
        out["coins"][coin] = c
    out["fees"] = FEES
    out["note"] = ("median_diff_with_fees_bp lægger 2 x taker-forskellen til (29b); uafklaret gebyr = None; "
                   "V1-dom kun med gebyr og >= 50 pr. mønt over >= 48 t")
    return out


LIMIT_BP, MIN_N, MIN_HOURS = 10.0, 50, 48.0          # amendment 29a point 3 and 29b point 2; never changed after data


def verdict(rep):
    """Amendment 29a point 3: V1 is rejected for a venue when the fee-inclusive median (venue - Binance) exceeds
    10 bp for at least half of the coins both have. No verdict while hours < 48, any common coin has n < 50 or a
    fee is uafklaret. Applies the locked rule only; it chooses no venue (amendment 30 point 2)."""
    out = {"rule": "research/PROTOCOL_V3.md amendment 29a point 3, 29b point 2", "limit_bp": LIMIT_BP,
           "hours": rep["hours"], "venues": {}}
    venues = sorted({v for c in rep["coins"].values() for v in c})
    for venue in venues:
        cells = {coin: c[venue] for coin, c in rep["coins"].items() if venue in c}
        why = []
        if rep["hours"] < MIN_HOURS:
            why.append(f"{rep['hours']} t < {MIN_HOURS:.0f} t")
        why += [f"{coin} n {x['n']} < {MIN_N}" for coin, x in cells.items() if x["n"] < MIN_N]
        why += [f"{coin} gebyr uafklaret" for coin, x in cells.items() if x["median_diff_with_fees_bp"] is None]
        over = sorted(coin for coin, x in cells.items()
                      if x["median_diff_with_fees_bp"] is not None and x["median_diff_with_fees_bp"] > LIMIT_BP)
        v = {"coins": len(cells), "over_limit": over,
             "median_with_fees_bp": {coin: x["median_diff_with_fees_bp"] for coin, x in cells.items()}}
        if why:
            v["verdict"], v["why"] = "ingen dom endnu", why
        else:
            v["verdict"] = "V1 forkastet" if 2 * len(over) >= len(cells) else "V1 ikke forkastet"
        out["venues"][venue] = v
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run").add_argument("--samples", type=int, default=400)
    sub.add_parser("report").add_argument("--path", default=OUT)
    sub.add_parser("verdict").add_argument("--path", default=OUT)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        print(run(a.samples), "prøver")
    elif a.cmd == "report":
        print(json.dumps(report(a.path), indent=1, ensure_ascii=False))
    else:
        print(json.dumps(verdict(report(a.path)), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
