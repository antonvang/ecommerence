"""Carry basis attack (plan: research/studies/CARRY_BASIS_PLAN.md, locked before prices were fetched).

For every trade of the Binance carry rule (coins with spot), adds the price P&L of the hedge (long spot, short perp,
equal notional) between entry and exit to the funding actually paid, then subtracts round-trip cost scenarios.

Usage: python3 research/tools/carry_basis.py <study_dir> [--fetch]
  --fetch downloads hourly klines (public GET, throttled) into <study_dir>/klines/ ; without it only the cache is read.
"""
import json
import os
import random
import statistics
import sys
import time
import urllib.parse
import urllib.request

X, FLOOR, WINDOW = 0.0005, 0.0001, 3
COSTS = (0.003, 0.006, 0.010, 0.0135, 0.015, 0.016)
BOOT_N, BOOT_SEED = 2000, 7
H = 3600
UA = {"User-Agent": "copybot-research/1.0 (read-only study)"}
SPOT = "https://data-api.binance.vision/api/v3/klines"
PERP = "https://fapi.binance.com/fapi/v1/klines"


def series(rows):
    """[(t, per-8h rate, paid rate)] from settled rows [(t, rate)]: the first row has no interval and is dropped."""
    rows = sorted(rows)
    out = []
    for (t0, _), (t1, v) in zip(rows, rows[1:]):
        h = max(1, round((t1 - t0) / H))
        out.append((t1, v * 8 / h, v))
    return out


def next_hour(t):
    return (int(t) // H + 1) * H


def trades(r):
    """Same rule and loop as research/tools/recent_study.py trades(), with times. Funding counts settlements strictly
    after the entry hour (plan): a settlement at the entry instant is not earned."""
    out, i = [], WINDOW
    while i < len(r):
        if r[i][1] >= X and statistics.mean(v for _, v, _ in r[i - WINDOW + 1:i + 1]) >= X / 2:
            entry = next_hour(r[i][0])
            j, low, got = i + 1, 0, 0.0
            exit_ts = None
            while j < len(r):
                if r[j][0] > entry:
                    got += r[j][2]
                low = low + 1 if r[j][1] < FLOOR else 0
                j += 1
                if low >= 2:
                    exit_ts = next_hour(r[j - 1][0])
                    break
            out.append({"signal_ts": r[i][0], "entry": entry, "exit": exit_ts, "funding": got})
            i = j + 1
        else:
            i += 1
    return out


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read())


def klines(kind, sym, a, b, cache, fetch):
    """{hour open ts: open price} for [a, b], from the cache or (with fetch) the public API."""
    path = os.path.join(cache, f"{kind}_{sym}.json")
    have = {}
    if os.path.exists(path):
        with open(path) as f:
            have = {int(k): v for k, v in json.load(f).items()}
    need = [t for t in range(a, b + H, H) if t not in have]
    if need and fetch:
        url = SPOT if kind == "spot" else PERP
        t = min(need)
        while t <= b:
            q = urllib.parse.urlencode({"symbol": sym, "interval": "1h", "startTime": t * 1000, "limit": 1000})
            rows = _get(f"{url}?{q}")
            for k in rows:
                have[int(k[0]) // 1000] = float(k[1])
            if not rows:
                break
            t = int(rows[-1][0]) // 1000 + H
            time.sleep(0.3)
        os.makedirs(cache, exist_ok=True)
        with open(path, "w") as f:
            json.dump(have, f)
    return have


def lower_bound(v):
    rng = random.Random(BOOT_SEED)
    m = sorted(statistics.mean(rng.choice(v) for _ in v) for _ in range(BOOT_N))
    return m[int(0.05 * BOOT_N)]


def summary(v):
    return {"n": len(v), "mean_pct": 100 * statistics.mean(v), "median_pct": 100 * statistics.median(v),
            "win": sum(x > 0 for x in v) / len(v), "lower95_pct": 100 * lower_bound(v)} if v else {"n": 0}


def main(argv):
    d = argv[1]
    fetch = "--fetch" in argv
    bn = json.load(open(os.path.join(d, "binance_funding.json")))
    spot = set(json.load(open(os.path.join(d, "spot_symbols.json"))))
    cache = os.path.join(d, "klines")
    rows, open_trades, no_price = [], [], []
    for sym, raw in sorted(bn.items()):
        if isinstance(raw, dict) or len(raw) < 10 or sym not in spot:
            continue
        for t in trades(series(raw)):
            if t["exit"] is None:
                open_trades.append({**t, "symbol": sym})
                continue
            sp = klines("spot", sym, t["entry"], t["exit"], cache, fetch)
            pp = klines("perp", sym, t["entry"], t["exit"], cache, fetch)
            if not all(x in sp and x in pp for x in (t["entry"], t["exit"])):
                no_price.append({**t, "symbol": sym})
                continue
            price = (sp[t["exit"]] / sp[t["entry"]] - 1) - (pp[t["exit"]] / pp[t["entry"]] - 1)
            rows.append({**t, "symbol": sym, "price": price, "hours": (t["exit"] - t["entry"]) // H})
    out = {"plan": "research/studies/CARRY_BASIS_PLAN.md", "closed_trades": len(rows), "open_trades": len(open_trades),
           "no_price": len(no_price), "coins": len({r["symbol"] for r in rows}),
           "median_hold_hours": statistics.median(r["hours"] for r in rows) if rows else None,
           "funding": summary([r["funding"] for r in rows]), "price": summary([r["price"] for r in rows]),
           "gross": summary([r["funding"] + r["price"] for r in rows])}
    for c in COSTS:
        out[f"net_{c*100:.2f}pct"] = summary([r["funding"] + r["price"] - c for r in rows])
    by = {}
    for r in rows:
        by[r["symbol"]] = by.get(r["symbol"], 0.0) + r["funding"] + r["price"]
    top = [s for s, _ in sorted(by.items(), key=lambda x: -x[1])[:3]]
    out["top3_gross_coins"] = top
    out["net_1.35pct_without_top3"] = summary([r["funding"] + r["price"] - 0.0135 for r in rows if r["symbol"] not in top])
    months = {}
    for r in rows:
        months.setdefault(time.strftime("%Y-%m", time.gmtime(r["entry"])), []).append(r["funding"] + r["price"] - 0.0135)
    out["net_1.35pct_by_month"] = {m: {"n": len(v), "mean_pct": 100 * statistics.mean(v)} for m, v in sorted(months.items())}
    out["trades"] = [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
