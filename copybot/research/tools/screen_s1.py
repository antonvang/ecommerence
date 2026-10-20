"""Screen S1 (research/screens/S1_OPMAERK_FUNDING.md): attention shock vs the following week's change in settled
funding, explore0 only. Every parameter is the pre-registered one; the script refuses any other window.

Usage: python3 research/tools/screen_s1.py [market_dir]
"""
import csv
import io
import json
import math
import os
import random
import sys
import zipfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MARKET = os.path.join(HERE, "data", "lab", "market")
UTC = timezone.utc
FIRST_T = datetime(2020, 3, 23, tzinfo=UTC)
LAST_T = datetime(2021, 12, 20, tzinfo=UTC)
WINDOW = (datetime(2020, 3, 1, tzinfo=UTC), datetime(2022, 1, 1, tzinfo=UTC))     # explore0, end exclusive
PAIRS = (("BTCUSDT", "Bitcoin"), ("ETHUSDT", "Ethereum"), ("DOGEUSDT", "Dogecoin"), ("LTCUSDT", "Litecoin"),
         ("BNBUSDT", "Binance"), ("XRPUSDT", "Ripple_Labs"), ("ADAUSDT", "Cardano_(blockchain_platform)"),
         ("DOTUSDT", "Polkadot_(cryptocurrency)"), ("LINKUSDT", "Chainlink_(blockchain)"),
         ("AVAXUSDT", "Avalanche_(blockchain_platform)"))
MARKET_WIDE = "Cryptocurrency"
MIN_SETTLEMENTS = 18
BOOT_N, BOOT_SEED = 2000, 7
PLAC_N, PLAC_SEED, PLAC_MIN_SHIFT = 2000, 11, 4
ALPHA = 0.05
DAY = timedelta(days=1)


def months(a, b):
    y, m = a.year, a.month
    while (y, m) < (b.year, b.month) or (y, m) == (b.year, b.month):
        yield f"{y}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def funding(sym, market):
    out = []
    for mo in months(WINDOW[0], WINDOW[1] - DAY):
        p = os.path.join(market, "funding", f"{sym}-fundingRate-{mo}.zip")
        if not os.path.exists(p):
            continue
        with zipfile.ZipFile(p) as z, z.open(z.namelist()[0]) as f:
            for r in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                if not r or not r[0][:1].isdigit():
                    continue
                ts = datetime.fromtimestamp(int(r[0]) / 1000, UTC)
                if WINDOW[0] <= ts < WINDOW[1]:                     # explore0 only (pre-registration point 2)
                    out.append((ts, float(r[2])))
    return sorted(out)


def views(article, market):
    path = os.path.join(market, "ingest", "pageviews", f"{article}.json")
    if not os.path.exists(path):
        return {}                                                  # the coin then contributes no week (coins_used)
    with open(path) as f:
        rows = json.load(f)["rows"]
    return {r["date"]: r["views"] for r in rows}


def shock(v, t):
    """Point-in-time: only days <= t - 2 (usable from D + 2 00:00 UTC)."""
    def mean(a, b):
        days = [(t - k * DAY).strftime("%Y-%m-%d") for k in range(a, b + 1)]
        if any(d not in v or v[d] <= 0 for d in days):
            return None
        return sum(v[d] for d in days) / len(days)
    near, far = mean(2, 4), mean(5, 18)
    return None if near is None or far is None else math.log(near) - math.log(far)


def week_mean(f, a, b):
    xs = [x for ts, x in f if a <= ts < b]
    return sum(xs) / len(xs) if len(xs) >= MIN_SETTLEMENTS else None


def mondays():
    t = FIRST_T
    while t <= LAST_T:
        yield t
        t += 7 * DAY


def rank(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None


def build(market, article_of=None):
    """{(sym, week_index): (S, Y)} plus the week list."""
    weeks = list(mondays())
    rows = {}
    for sym, art in PAIRS:
        f = funding(sym, market)
        v = views(article_of or art, market)
        for i, t in enumerate(weeks):
            s = shock(v, t)
            after, before = week_mean(f, t, t + 7 * DAY), week_mean(f, t - 7 * DAY, t)
            if s is None or after is None or before is None:
                continue
            rows[(sym, i)] = (s, after - before)
    return rows, weeks


def rho_of(rows):
    v = list(rows.values())
    return spearman([a for a, _ in v], [b for _, b in v])


def bootstrap(rows, n_weeks):
    by_w = {}
    for (sym, i), sy in rows.items():
        by_w.setdefault(i, []).append(sy)
    ws = sorted(by_w)
    rng = random.Random(BOOT_SEED)
    le0 = 0
    for _ in range(BOOT_N):
        pick = [by_w[rng.choice(ws)] for _ in ws]
        flat = [sy for w in pick for sy in w]
        r = spearman([a for a, _ in flat], [b for _, b in flat])
        le0 += (r is None or r <= 0)
    return le0 / BOOT_N


def placebo(rows, n_weeks, actual):
    syms = sorted({s for s, _ in rows})
    rng = random.Random(PLAC_SEED)
    ge = 0
    for _ in range(PLAC_N):
        k = rng.randint(PLAC_MIN_SHIFT, n_weeks - PLAC_MIN_SHIFT)
        a, b = [], []
        for sym in syms:
            for (s2, i), (sv, yv) in rows.items():
                if s2 != sym:
                    continue
                j = (i + k) % n_weeks
                if (sym, j) in rows:
                    a.append(rows[(sym, j)][0])                     # the shock of another week, same coin
                    b.append(yv)
        r = spearman(a, b)
        ge += (r is not None and r >= actual)
    return (ge + 1) / (PLAC_N + 1)


def describe(rows):
    v = sorted(rows.values())
    cut = v[int(len(v) * 0.8)][0]
    top = [y for s, y in v if s >= cut]
    rest = [y for s, y in v if s < cut]
    return {"top_quintile_mean_dY_pct_8h": 100 * sum(top) / len(top), "rest_mean_dY_pct_8h": 100 * sum(rest) / len(rest),
            "top_n": len(top), "rest_n": len(rest)}


def main(argv):
    market = argv[1] if len(argv) > 1 else MARKET
    rows, weeks = build(market)
    rho = rho_of(rows)
    p_boot = bootstrap(rows, len(weeks))
    p_plac = placebo(rows, len(weeks), rho)
    per_coin = {}
    for sym, _ in PAIRS:
        sub = {k: v for k, v in rows.items() if k[0] == sym}
        per_coin[sym] = {"n": len(sub), "rho": rho_of(sub) if len(sub) >= 3 else None}
    mrows, _ = build(market, MARKET_WIDE)
    out = {"screen": "S1", "window": "explore0 2020-03..2021-12", "coin_weeks": len(rows), "weeks": len(weeks),
           "coins_used": sorted({s for s, _ in rows}), "rho": rho, "p_boot": p_boot, "p_placebo": p_plac,
           "passed": bool(rho is not None and rho > 0 and p_boot < ALPHA and p_plac < ALPHA),
           "descriptive": {"per_coin": per_coin, "quintiles": describe(rows),
                           "market_wide_rho": rho_of(mrows), "market_wide_coin_weeks": len(mrows)}}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
