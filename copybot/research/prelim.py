"""Fast preliminary screens, exactly as research/PRELIM_2026-10-17.md. Read-only, no orders, no account.

  python -m research.prelim p2                 one negRisk snapshot (run three times, 30 min apart)
  python -m research.prelim p1 explore         fetch + evaluate the exploration week
  python -m research.prelim p1 confirm         requires committed research/PRELIM_P1_CHOICE.md
"""
import collections, json, math, os, random, statistics, subprocess, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "data", "research", "prelim")
GAMMA, CLOB, DAPI, BINANCE = ("https://gamma-api.polymarket.com", "https://clob.polymarket.com",
                              "https://data-api.polymarket.com", "https://api.binance.com")
EXPLORE = ("2026-10-01T00:00:00", "2026-10-07T23:45:00")
CONFIRM = ("2026-10-08T00:00:00", "2026-10-14T23:45:00")
MS, THETAS = (10, 5, 2), (0.03, 0.05, 0.08, 0.12)
FEE, SPREAD = 0.07, 0.01


def http(url, body=None, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"User-Agent": "copybot-research/1.0", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def ts(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ---------- P1 ----------
def p_up(closes_elapsed, s_t, s0, sigma, m, window=15):
    """Model probability that the window TWAP >= start price, with m minutes left (random walk, zero drift)."""
    a = statistics.mean(closes_elapsed)
    exp_twap = ((window - m) * a + m * s_t) / window
    sd = (m / window) * s_t * sigma * math.sqrt(m / 3)
    if sd <= 0:
        return 1.0 if exp_twap >= s0 else 0.0
    return norm_cdf((exp_twap - s0) / sd)


def trade_return(q, payout):
    c = q + SPREAD + FEE * q * (1 - q)
    return (payout - c) / c


def decide(p_model, p_mkt, theta):
    """'up', 'down' or None."""
    if p_model - p_mkt >= theta:
        return "up"
    if p_mkt - p_model >= theta:
        return "down"
    return None


def klines(start, end):
    out, t = {}, start
    while t < end:
        r = http(f"{BINANCE}/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={t * 1000}&endTime={end * 1000}&limit=1000")
        if not r:
            break
        for k in r:
            out[k[0] // 1000] = (float(k[1]), float(k[4]))     # minute open time -> (open, close)
        t = r[-1][0] // 1000 + 60
    return out


def market(start):
    e = http(f"{GAMMA}/events?slug=btc-updown-15m-{start}")
    if not e or not e[0].get("markets"):
        return None
    m = e[0]["markets"][0]
    toks, outs, op = (json.loads(m.get(k) or "null") for k in ("clobTokenIds", "outcomes", "outcomePrices"))
    if not toks or outs != ["Up", "Down"] or not op:
        return None
    up_pay = float(op[0])
    if min(abs(up_pay - v) for v in (0.0, 0.5, 1.0)) > 0.01:
        return None
    return {"start": start, "cid": m["conditionId"], "up": toks[0], "down": toks[1], "up_pay": round(up_pay * 2) / 2,
            "volume": m.get("volumeNum")}


def trades_near_end(cid, start):
    """All trade prints from 11 minutes before the end, newest first, paginated until older."""
    end, rows, cur = start + 900, [], None
    while True:
        r = http(f"{DAPI}/v2/trades?condition={cid}&limit=500" + (f"&cursor={urllib.parse.quote(cur)}" if cur else ""))
        data = r.get("data") or []
        rows += [{"t": int(x["timestamp"]), "token": x["token_id"], "price": float(x["price"]), "size": float(x["size"])}
                 for x in data if int(x["timestamp"]) >= end - 11 * 60]
        cur = (r.get("pagination") or {}).get("next_cursor")
        if not cur or not data or min(int(x["timestamp"]) for x in data) < end - 11 * 60:
            return rows


def fetch_p1(period, log=print):
    a, b = ts(period[0]), ts(period[1])
    starts = list(range(a, b + 1, 900))
    kl = klines(a - 3600, b + 900)
    with ThreadPoolExecutor(6) as ex:
        mks = [m for m in ex.map(market, starts) if m]
    log(f"markets {len(mks)} of {len(starts)}")
    with ThreadPoolExecutor(6) as ex:
        trs = list(ex.map(lambda m: trades_near_end(m["cid"], m["start"]), mks))
    for m, t in zip(mks, trs):
        m["trades"] = t
    return {"period": period, "markets": mks, "klines": {str(k): v for k, v in kl.items()}}


def observations(data):
    """One row per (market, m) with model probability, market price and payouts."""
    kl = {int(k): v for k, v in data["klines"].items()}
    rows, gate = [], [0, 0]
    for mk in data["markets"]:
        s, end = mk["start"], mk["start"] + 900
        if s not in kl or any(s + 60 * i not in kl for i in range(15)):
            continue
        s0 = kl[s][0]
        full = statistics.mean(kl[s + 60 * i][1] for i in range(15))
        if mk["up_pay"] != 0.5:
            gate[0] += 1
            gate[1] += int((full >= s0) == (mk["up_pay"] == 1.0))
        for m in MS:
            td = end - 60 * m                               # decision time
            elapsed = [kl[s + 60 * i][1] for i in range(15 - m)]
            hist = [kl.get(td - 60 * j) for j in range(61, 0, -1)]
            if any(h is None for h in hist):
                continue
            lr = [math.log(hist[j + 1][1] / hist[j][1]) for j in range(len(hist) - 1)]
            sigma = statistics.stdev(lr)
            prior = [x for x in mk["trades"] if td - 60 <= x["t"] < td]
            if not prior:
                continue
            last = max(prior, key=lambda x: x["t"])
            p = last["price"] if last["token"] == mk["up"] else 1 - last["price"]
            rows.append({"start": s, "day": s // 86400, "m": m, "p_model": p_up(elapsed, kl[td - 60][1], s0, sigma, m),
                         "p_mkt": p, "up_pay": mk["up_pay"]})
    return rows, gate


def evaluate(rows, m, theta):
    out = []
    for r in rows:
        if r["m"] != m:
            continue
        d = decide(r["p_model"], r["p_mkt"], theta)
        if d is None:
            continue
        q = r["p_mkt"] if d == "up" else 1 - r["p_mkt"]
        pay = r["up_pay"] if d == "up" else 1 - r["up_pay"]
        if not 0 < q < 1:
            continue
        out.append({"day": r["day"], "r": trade_return(q, pay), "q": q})
    return out


def baseline(rows, m):
    out = []
    for r in rows:
        if r["m"] != m or r["p_mkt"] == 0.5:
            continue
        up = r["p_mkt"] > 0.5
        q = r["p_mkt"] if up else 1 - r["p_mkt"]
        pay = r["up_pay"] if up else 1 - r["up_pay"]
        if 0 < q < 1:
            out.append({"day": r["day"], "r": trade_return(q, pay), "q": q})
    return out


def day_lb(tr, q=0.01, n=10000, seed=5):
    by = collections.defaultdict(list)
    for x in tr:
        by[x["day"]].append(x["r"])
    cl = [(sum(v), len(v)) for v in by.values()]
    if len(cl) < 2:
        return None
    rng, means = random.Random(seed), []
    for _ in range(n):
        s = k = 0
        for a, b in rng.choices(cl, k=len(cl)):
            s += a
            k += b
        means.append(s / k)
    means.sort()
    return means[int(q * n)]


def summary(tr):
    r = [x["r"] for x in tr]
    return {"n": len(r), "mean": statistics.mean(r) if r else None, "win": (sum(1 for x in r if x > 0) / len(r)) if r else None,
            "lb99": day_lb(tr), "mean_price": statistics.mean(x["q"] for x in tr) if tr else None}


def committed(path):
    try:
        dirty = subprocess.check_output(["git", "status", "--porcelain", path], cwd=HERE, text=True).strip()
        tracked = subprocess.check_output(["git", "ls-files", path], cwd=HERE, text=True).strip()
        return bool(tracked) and not dirty
    except Exception:
        return False


# ---------- P3 ----------
P3_PERIOD = ("2026-09-15T00:00:00", "2026-10-14T23:59:59")
SHORT_RE = __import__("re").compile(r"up or down|\bup/down\b|price of .* (above|below) .* on|bitcoin above|ethereum above",
                                    __import__("re").I)


def p3_markets(exclude):
    a, b = P3_PERIOD
    rows, cur = [], None
    while True:
        r = http(f"{GAMMA}/markets/keyset?closed=true&limit=500&volume_num_min=10000&end_date_min={a}Z&end_date_max={b}Z"
                 + (f"&after_cursor={urllib.parse.quote(cur)}" if cur else ""))
        for m in r.get("markets") or []:
            toks, outs, op = (json.loads(m.get(k) or "null") for k in ("clobTokenIds", "outcomes", "outcomePrices"))
            if not toks or not outs or len(outs) != 2 or not op or SHORT_RE.search(m.get("question") or ""):
                continue
            try:
                y = float(op[0])
                life = ts(m["endDate"][:19]) - ts(m["createdAt"][:19])
            except (TypeError, ValueError, KeyError):
                continue
            if min(abs(y), abs(y - 1)) > 0.01 or life < 3 * 86400 or m["conditionId"] in exclude:
                continue
            rows.append({"cid": m["conditionId"], "yes": toks[0], "no": toks[1], "pay": round(y),
                         "end": ts(m["endDate"][:19]), "q": (m.get("question") or "")[:80]})
        cur = r.get("next_cursor")
        if not cur or not r.get("markets"):
            break
    rows.sort(key=lambda x: x["cid"])
    random.Random(17).shuffle(rows)
    return rows[:200]


def p3_trades(mk):
    since, out, cur = mk["end"] - 7 * 86400, [], None
    while True:
        r = http(f"{DAPI}/v2/trades?condition={mk['cid']}&limit=500&taker_only=true"
                 + (f"&cursor={urllib.parse.quote(cur)}" if cur else ""))
        data = r.get("data") or []
        for x in data:
            t = int(x["timestamp"])
            if since <= t <= mk["end"]:
                p = float(x["price"]) if x["token_id"] == mk["yes"] else 1 - float(x["price"])
                buy = (x["side"].upper() == "BUY") == (x["token_id"] == mk["yes"])   # taker buys YES-equivalent
                out.append({"t": t, "p": p, "size": float(x["size"]), "taker_buys_yes": buy})
        cur = (r.get("pagination") or {}).get("next_cursor")
        if not cur or not data or min(int(x["timestamp"]) for x in data) < since:
            return sorted(out, key=lambda x: x["t"])


def maker_pnl(tr, payout_yes, mark_yes):
    """Per-share P&L of the maker on the opposite side, marked to payout (resolution) or a later price."""
    return (tr["p"] - mark_yes) if tr["taker_buys_yes"] else (mark_yes - tr["p"])


def p3_eval(markets):
    clusters_res, clusters_1h, buckets = [], [], collections.defaultdict(lambda: [0.0, 0.0])
    for mk in markets:
        trs = mk["trades"]
        sr = s1 = n = 0.0
        for i, tr in enumerate(trs):
            if not 0.10 <= tr["p"] <= 0.90:
                continue
            later = [x for x in trs[i:] if x["t"] <= tr["t"] + 3600]
            mark1h = later[-1]["p"] if later else tr["p"]
            pr = maker_pnl(tr, mk["pay"], mk["pay"]) * tr["size"]
            sr += pr
            s1 += maker_pnl(tr, mk["pay"], mark1h) * tr["size"]
            n += tr["size"]
            bk = f"{int(tr['p'] * 10) / 10:.1f}"
            buckets[bk][0] += pr
            buckets[bk][1] += tr["size"]
        if n:
            clusters_res.append((sr, n))
            clusters_1h.append((s1, n))

    def stats(cl):
        tot = sum(a for a, _ in cl) / sum(b for _, b in cl)
        rng, means = random.Random(5), []
        for _ in range(10000):
            s = k = 0.0
            for a, b in rng.choices(cl, k=len(cl)):
                s += a
                k += b
            means.append(s / k)
        means.sort()
        return {"mean_cents": 100 * tot, "lb99_cents": 100 * means[100], "ub99_cents": 100 * means[9899],
                "markets": len(cl), "shares": sum(b for _, b in cl)}

    res, h1 = stats(clusters_res), stats(clusters_1h)
    if res["mean_cents"] <= -2 and res["ub99_cents"] < 0:
        signal = "negative"
    elif res["mean_cents"] >= 0 and res["lb99_cents"] > -1:
        signal = "positive"
    else:
        signal = "inconclusive"
    return {"resolution": res, "markout_1h": h1, "signal": signal,
            "by_price_bucket_cents": {k: 100 * v[0] / v[1] for k, v in sorted(buckets.items()) if v[1]}}


# ---------- P2 ----------
def p2_snapshot(log=print):
    evs, cur = [], None
    while True:
        r = http(f"{GAMMA}/events/keyset?active=true&closed=false&limit=500"
                 + (f"&after_cursor={urllib.parse.quote(cur)}" if cur else ""))
        evs += r.get("events") or []
        cur = r.get("next_cursor")
        if not cur or not r.get("events"):
            break
    cand = [e for e in evs if (e.get("negRisk") or e.get("enableNegRisk")) and not e.get("negRiskAugmented")]
    found, checked = [], 0
    for e in cand:
        mks = [m for m in e.get("markets") or [] if m.get("active") and not m.get("closed") and m.get("clobTokenIds")]
        if len(mks) < 2 or len(mks) != len(e.get("markets") or []):
            continue
        toks = [json.loads(m["clobTokenIds"])[0] for m in mks]
        books = {}
        for i in range(0, len(toks), 50):
            for bk in http(f"{CLOB}/books", [{"token_id": t} for t in toks[i:i + 50]]):
                books[bk["asset_id"]] = bk
        if len(books) != len(toks):
            continue
        checked += 1
        asks, bids = [], []
        for t in toks:
            a = [(float(o["price"]), float(o["size"])) for o in books[t].get("asks", [])]
            b = [(float(o["price"]), float(o["size"])) for o in books[t].get("bids", [])]
            asks.append(min(a) if a else None)
            bids.append(max(b) if b else None)
        if all(asks):
            cost = sum(p + FEE * p * (1 - p) for p, _ in asks)
            size = min(z for _, z in asks)
            if cost < 1 and size >= 5:
                found.append({"event": e.get("slug"), "kind": "buy_all_yes", "edge": 1 - cost, "size": size,
                              "profit": (1 - cost) * size, "legs": len(toks)})
        if all(bids):
            # all NO: pay (1 - bid) per leg (+ fee on the NO price), receive n - 1
            cost = sum((1 - p) + FEE * p * (1 - p) for p, _ in bids)
            size = min(z for _, z in bids)
            n = len(toks)
            if cost < n - 1 and size >= 5:
                found.append({"event": e.get("slug"), "kind": "buy_all_no", "edge": (n - 1) - cost, "size": size,
                              "profit": ((n - 1) - cost) * size, "legs": n})
    return {"t": int(time.time()), "events_active": len(evs), "negrisk_complete_checked": checked, "found": found}


def main():
    a = sys.argv[1:]
    os.makedirs(OUT, exist_ok=True)
    if a[:1] == ["p2"]:
        s = p2_snapshot()
        with open(os.path.join(OUT, "p2_snapshots.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(s) + "\n")
        print(json.dumps({k: v for k, v in s.items() if k != "found"}), "found:", len(s["found"]),
              "with >= $5:", sum(1 for x in s["found"] if x["profit"] >= 5))
        for x in sorted(s["found"], key=lambda x: -x["profit"])[:10]:
            print(" ", x)
    elif a[:2] == ["p1", "explore"]:
        p = os.path.join(OUT, "p1_explore.json")
        data = json.load(open(p)) if os.path.exists(p) else fetch_p1(EXPLORE)
        json.dump(data, open(p, "w"))
        rows, gate = observations(data)
        res = {"gate_D": {"n": gate[0], "match": gate[1], "share": gate[1] / gate[0] if gate[0] else None},
               "grid": {f"m{m}_t{t}": summary(evaluate(rows, m, t)) for m in MS for t in THETAS},
               "baseline": {f"m{m}": summary(baseline(rows, m)) for m in MS}, "observations": len(rows)}
        json.dump(res, open(os.path.join(OUT, "p1_explore_result.json"), "w"), indent=1)
        print(json.dumps(res, indent=1))
    elif a[:2] == ["p1", "confirm"]:
        ch = os.path.join(HERE, "research", "PRELIM_P1_CHOICE.md")
        if not committed(ch):
            raise SystemExit("research/PRELIM_P1_CHOICE.md must be committed before the confirmation week is fetched")
        vals = dict(line.split(":", 1) for line in open(ch, encoding="utf-8") if line.split(":")[0] in ("m", "theta"))
        m, t = int(vals["m"]), float(vals["theta"])
        data = fetch_p1(CONFIRM)
        json.dump(data, open(os.path.join(OUT, "p1_confirm.json"), "w"))
        rows, gate = observations(data)
        s, b = summary(evaluate(rows, m, t)), summary(baseline(rows, m))
        g = {"n>=100": s["n"] >= 100, "mean>0": (s["mean"] or -1) > 0, "lb99>0": (s["lb99"] or -1) > 0,
             "beats_baseline": (s["mean"] or -9) > (b["mean"] or -9)}
        res = {"m": m, "theta": t, "summary": s, "baseline": b, "gates": g,
               "verdict": "PASS (preliminary)" if all(g.values()) else "REJECT",
               "gate_D": {"n": gate[0], "match": gate[1]}}
        json.dump(res, open(os.path.join(OUT, "p1_confirm_result.json"), "w"), indent=1)
        print(json.dumps(res, indent=1))
    elif a[:1] == ["p3"]:
        import sqlite3
        db = os.path.join(HERE, "data", "research", "pm_lp", "pm_lp.db")
        exclude = set()
        if os.path.exists(db):   # read-only: only the panel's market ids, to exclude them
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
            exclude = {r[0] for r in con.execute("SELECT DISTINCT cid FROM panel")}
            con.close()
        mks = p3_markets(exclude)
        with ThreadPoolExecutor(6) as ex:
            for mk, tr in zip(mks, ex.map(p3_trades, mks)):
                mk["trades"] = tr
        json.dump(mks, open(os.path.join(OUT, "p3_markets.json"), "w"))
        res = {"markets": len(mks), "excluded_panel": len(exclude), **p3_eval(mks)}
        json.dump(res, open(os.path.join(OUT, "p3_result.json"), "w"), indent=1)
        print(json.dumps(res, indent=1))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
