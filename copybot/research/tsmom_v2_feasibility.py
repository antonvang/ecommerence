"""tsmom_v2 feasibility: can any untouched data support a confirmatory test of diversified momentum?

Uses only (a) listing dates (first daily candle) of Binance USDT spot pairs, including delisted ones, and
(b) the tsmom_v1 cache, whose periods are all already seen. No return of a new asset in a new period is read.
Run from copybot/:  python -m research.tsmom_v2_feasibility
"""
import json, math, re, statistics as st, time, urllib.request
from datetime import datetime, timezone

from research import tsmom as t

ARCHIVE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/spot/monthly/klines/"
STABLE = re.compile(r"^(USDC|BUSD|TUSD|USDP|PAX|FDUSD|DAI|USDS|EUR|GBP|AUD|BRL|TRY|RUB|UST|USTC|BIDR|IDRT|NGN|UAH|ZAR"
                    r"|PLN|RON|ARS|JPY|AEUR|EURI|XUSD|USD1|BFUSD|USDE)USDT$")
LEVERAGED = re.compile(r"(UP|DOWN|BULL|BEAR)USDT$")
Z_005, Z_05 = 2.5758 + 0.8416, 1.6449 + 0.8416      # one-sided alpha 0.005 / 0.05, power 80 %


def listing_dates():
    syms, marker = [], ""
    while True:
        url = ARCHIVE + (f"&marker={marker}" if marker else "")
        txt = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"}), timeout=30).read().decode()
        new = re.findall(r"<Prefix>data/spot/monthly/klines/([A-Z0-9]+)/</Prefix>", txt)
        syms += new
        if "<IsTruncated>true</IsTruncated>" not in txt:
            break
        marker = "data/spot/monthly/klines/" + new[-1] + "/"
    usdt = [s for s in syms if s.endswith("USDT") and not STABLE.match(s) and not LEVERAGED.search(s)]
    first = {}
    for s in usdt:
        k = t.get(f"https://api.binance.com/api/v3/klines?symbol={s}&interval=1d&startTime=0&limit=1")
        if k:
            first[s] = k[0][0] // 1000
        time.sleep(0.12)
    return len(syms), first


def weeks_with(first, n, start="2017-09-04", end="2019-09-30", history_weeks=5):
    m, e = t.ts(start), t.ts(end)
    while m < e and sum(1 for v in first.values() if v <= m - history_weeks * t.WEEK) < n:
        m += t.WEEK
    return datetime.fromtimestamp(m, timezone.utc).date().isoformat(), (e - m) // t.WEEK


def v1_correlations(d, period, L=4):
    ser, orig = {}, t.ASSETS
    try:
        for a in orig:
            t.ASSETS = {a: orig[a]}
            ser[a] = {w["monday"]: w["net"] * len(orig) for w in t.run(d, period, L, "ls") if a in w["positions"]}
    finally:
        t.ASSETS = orig
    common = sorted(set.intersection(*[set(s) for s in ser.values()]))
    sr = {a: st.mean([ser[a][m] for m in common]) / st.stdev([ser[a][m] for m in common]) for a in ser}
    ks = list(ser)
    rho = [st.correlation([ser[ks[i]][m] for m in common], [ser[ks[j]][m] for m in common])
           for i in range(len(ks)) for j in range(i + 1, len(ks))]
    return len(common), sr, st.mean(rho)


def factor(n, rho):
    """Sharpe multiplier of an equal-weight portfolio of n strategies with equal Sharpe and pairwise correlation rho."""
    return math.sqrt(n / (1 + (n - 1) * rho))


def main():
    total, first = listing_dates()
    print(f"archive spot symbols {total}; USDT pairs excl. stablecoins/leveraged with candles: {len(first)}")
    for n in (3, 5, 10, 20):
        print(f"  >= {n:2d} listed assets from {weeks_with(first, n)[0]}: {weeks_with(first, n)[1]} untouched weeks"
              " before 2019-09-30")
    d, _ = t.data_from_cache()
    rows = {}
    for name, per in (("dev+val", (t.DEV[0], t.VAL[1])), ("holdout", t.HOLDOUT)):
        n, sr, rho = v1_correlations(d, per)
        rows[name] = (sum(sr.values()) / len(sr), rho)
        print(f"v1 {name}: {n} weeks, per-asset weekly SR " + ", ".join(f"{a} {v:.3f}" for a, v in sr.items())
              + f"; mean strategy correlation {rho:.2f}")
    for name, (sr, _) in rows.items():
        for rho in (rows["dev+val"][1], rows["holdout"][1]):
            s = sr * factor(20, rho)
            print(f"  20 assets, per-asset SR as v1 {name} ({sr:.3f}), rho {rho:.2f}: weekly SR {s:.3f}"
                  f" (ann. {s * 52 ** 0.5:.2f}) -> n_req {math.ceil((Z_005 / s) ** 2)} weeks at alpha 0.005,"
                  f" {math.ceil((Z_05 / s) ** 2)} at 0.05; gain vs 3 assets x{factor(20, rho) / factor(3, rho):.2f}")


if __name__ == "__main__":
    main()
