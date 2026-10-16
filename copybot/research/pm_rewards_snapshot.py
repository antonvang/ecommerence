"""Read-only snapshot: Polymarket liquidity-reward pools versus competing qualifying liquidity.

For a random sample of reward-eligible markets it estimates the reward share and the daily reward yield on capital
of a hypothetical two-sided quote, using the published scoring rule
(docs.polymarket.com/programs/liquidity-rewards: S = ((v - s) / v)^2, two-sided minimum, single-sided / 3).
This is a GROSS estimate from one order-book snapshot. It ignores adverse selection, inventory risk, sampling
across the day and the size-cutoff-adjusted midpoint. It places no orders and needs no account.
Run from copybot/:  python -m research.pm_rewards_snapshot [n_markets] [seed]
"""
import json, random, statistics as st, sys, time, urllib.parse, urllib.request

CLOB = "https://clob.polymarket.com"
SIZE = 100            # hypothetical shares per side
MIN_RATE = 5          # USD/day pools only


def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception:
            if i == 3:
                raise
            time.sleep(1 + i)


def reward_markets():
    rows, cur = [], ""
    while True:
        r = get(f"{CLOB}/rewards/markets/current" + (f"?next_cursor={urllib.parse.quote(cur)}" if cur else ""))
        rows += r.get("data") or []
        cur = r.get("next_cursor")
        if not cur or cur == "LTE=" or not r.get("data"):
            return rows


def score(v, s):
    return ((v - s) / v) ** 2 if 0 <= s < v else 0.0


def competing_q(bids, asks, mid, v, min_size):
    """Total qualifying score already on the book (YES book mirrors NO orders; price levels, not single orders)."""
    q1 = sum(score(v, mid - p) * z for p, z in bids if z >= min_size)
    q2 = sum(score(v, p - mid) * z for p, z in asks if z >= min_size)
    return min(q1, q2) if (mid < 0.10 or mid > 0.90) else max(min(q1, q2), max(q1, q2) / 3)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    rows = reward_markets()
    total = sum(x.get("total_daily_rate") or 0 for x in rows)
    print(f"reward markets: {len(rows)}, configured pools: {total:,.0f} USD/day (caps, not realised payouts)")
    cand = [x for x in rows if (x.get("total_daily_rate") or 0) >= MIN_RATE]
    random.Random(seed).shuffle(cand)
    res = []
    for x in cand[:n]:
        try:
            m = get(f"{CLOB}/markets/{x['condition_id']}")
            if not m.get("active") or m.get("closed"):
                continue
            b = get(f"{CLOB}/book?token_id={m['tokens'][0]['token_id']}")
        except Exception:
            continue
        bids = [(float(o["price"]), float(o["size"])) for o in b.get("bids", [])]
        asks = [(float(o["price"]), float(o["size"])) for o in b.get("asks", [])]
        if not bids or not asks:
            continue
        mid = (max(p for p, _ in bids) + min(p for p, _ in asks)) / 2
        v, s = x["rewards_max_spread"] / 100, x["rewards_max_spread"] / 200
        if mid - s <= 0 or mid + s >= 1:
            continue
        q = competing_q(bids, asks, mid, v, x["rewards_min_size"])
        ours = score(v, s) * SIZE
        share = ours / (q + ours)
        cap = SIZE * (mid - s) + SIZE * (1 - mid - s)
        res.append({"rate": x["total_daily_rate"], "share": share, "usd_day": share * x["total_daily_rate"],
                    "capital": cap, "yield_day": share * x["total_daily_rate"] / cap, "no_competition": q == 0})
    y = sorted(r["yield_day"] for r in res)
    pct = lambda q: 100 * y[min(int(q * len(y)), len(y) - 1)]
    print(f"sampled markets (pool >= {MIN_RATE} USD/day): {len(res)}")
    print(f"gross daily reward yield on capital, {SIZE}-share two-sided quote at half max spread: "
          f"p25 {pct(.25):.2f} %, median {pct(.5):.2f} %, p75 {pct(.75):.2f} %, p90 {pct(.9):.2f} %")
    print(f"median USD/day {st.median(r['usd_day'] for r in res):.2f}, median capital {st.median(r['capital'] for r in res):.0f}, "
          f"no qualifying competition: {sum(r['no_competition'] for r in res) / len(res):.0%}")


if __name__ == "__main__":
    main()
