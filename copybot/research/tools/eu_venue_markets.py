"""Amendment 30 point 1: build research/data/eu_venue_markets.json, the static source of the "EU-tradable" label.

It reads ESMA's interim MiCA register (CASPS.csv) and each listed venue's public market list (no account), keeps a
venue only if its legal entity is in the register with service b or e, no end date and Denmark in its country list,
and records per venue the base coins traded against USDT, USDC, EUR or USD. Every source is stored with URL, fetch
time and sha256. Whether a venue's public API is the registered EU entity's own is not verified here: "uafklaret".

  python3 research/tools/eu_venue_markets.py [--out research/data/eu_venue_markets.json]
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
import urllib.request

REGISTER = "https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv"
QUOTES = ("USDT", "USDC", "EUR", "USD")
KRAKEN_ALIASES = {"XBT": "BTC", "XDG": "DOGE"}


def _pairs_kraken(d):
    out = []
    for v in d["result"].values():
        if "/" in (v.get("wsname") or ""):
            b, q = v["wsname"].split("/")
            out.append((KRAKEN_ALIASES.get(b, b), KRAKEN_ALIASES.get(q, q)))
    return out


VENUES = {   # name -> (legal entity exactly as in CASPS.csv, public market list, parser)
    "Kraken": ("Payward Europe Solutions Limited", "https://api.kraken.com/0/public/AssetPairs", _pairs_kraken),
    "Bitstamp": ("Bitstamp Europe S.A.", "https://www.bitstamp.net/api/v2/trading-pairs-info/",
                 lambda d: [tuple(x["name"].split("/")) for x in d if x.get("trading") == "Enabled"]),
    "OKX": ("OKX Europe Limited", "https://www.okx.com/api/v5/public/instruments?instType=SPOT",
            lambda d: [(x["baseCcy"], x["quoteCcy"]) for x in d["data"] if x.get("state") == "live"]),
    "Bitvavo": ("Bitvavo B.V.", "https://api.bitvavo.com/v2/markets",
                lambda d: [(x["base"], x["quote"]) for x in d if x.get("status") == "trading"]),
    "Coinbase": ("Coinbase Luxembourg S.A.", "https://api.exchange.coinbase.com/products",
                 lambda d: [(x["base_currency"], x["quote_currency"]) for x in d
                            if x.get("status") == "online" and not x.get("trading_disabled")]),
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "copybot-research"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return raw, r.headers.get("Last-Modified")


def register_rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def qualifies(row):
    """Service b (trading platform) or e (execution of orders), no end date, Denmark in the country list."""
    codes = {s.strip()[:1] for s in row["ac_serviceCode"].split("|") if s.strip()}
    countries = {c.strip() for c in row["ac_serviceCode_cou"].split("|")}
    return bool(codes & {"b", "e"}) and not row["ac_authorisationEndDate"].strip() and "DK" in countries, sorted(codes)


def build(get=fetch, now=time.time):
    raw, modified = get(REGISTER)
    rows = register_rows(raw)
    by_name = {r["ae_lei_name"].strip(): r for r in rows}
    out = {"generated_at": int(now()), "rule": "research/PROTOCOL_V3.md amendment 30",
           "register": {"url": REGISTER, "sha256": hashlib.sha256(raw).hexdigest(), "last_modified": modified,
                        "rows": len(rows), "binance_listed": any("binance" in (r["ae_lei_name"] + r["ae_commercial_name"])
                                                                 .lower() for r in rows)},
           "venues": {}}
    for name, (entity, url, parse) in VENUES.items():
        row = by_name.get(entity)
        v = {"entity": entity, "in_register": row is not None, "api_entity": "uafklaret", "url": url}
        if row is not None:
            ok, codes = qualifies(row)
            v.update(lei=row["ae_lei"], home=row["ae_homeMemberState"].strip(), services=codes, qualifies=ok,
                     authorised=row["ac_authorisationNotificationDate"])
        if not v.get("qualifies"):
            out["venues"][name] = v
            continue
        try:
            raw_m, _ = get(url)
            coins = {}
            for b, q in parse(json.loads(raw_m)):
                if q in QUOTES:
                    coins.setdefault(b.upper(), set()).add(q)
            v.update(fetched_at=int(now()), sha256=hashlib.sha256(raw_m).hexdigest(),
                     coins={b: sorted(qs) for b, qs in sorted(coins.items())})
        except Exception as e:                                  # noqa: BLE001 - recorded, never guessed
            v.update(error=repr(e)[:200], coins=None)
        out["venues"][name] = v
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join("research", "data", "eu_venue_markets.json"))
    a = ap.parse_args(argv)
    res = build()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print(json.dumps({k: {"qualifies": v.get("qualifies"), "coins": len(v.get("coins") or {})}
                      for k, v in res["venues"].items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
