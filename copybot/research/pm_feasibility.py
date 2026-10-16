"""Feasibility checks for a prediction-market calibration experiment (Polymarket). Availability and costs only.

Reads market metadata (dates, volume, event id; prices and outcomes are not used), current order books, and computes
the required sample sizes. No historical price is joined to any outcome here.
Run from copybot/:  python -m research.pm_feasibility        (metadata cached in data/research/pm_feasibility/)
"""
import collections, json, math, os, random, re, statistics as st, time, urllib.parse, urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "research", "pm_feasibility")
GAMMA, CLOB = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
SHORT = re.compile(r"up or down|\bup/down\b|price of .* (above|below) .* on|bitcoin above|ethereum above", re.I)
Z_B = 0.8416                                           # 80 % power
FEE_RATE = {"crypto": 0.07, "sports": 0.05, "politics": 0.04, "geopolitics": 0.0}   # docs.polymarket.com, 16.10.2026


def get(url):
    for i in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception:
            if i == 5:
                raise
            time.sleep(3 * (i + 1))


def parse(s):
    if not s:
        return None
    s = s.replace(" ", "T").replace("Z", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def metadata():
    path = os.path.join(OUT, "closed_markets_meta.json")
    if os.path.exists(path):
        return json.load(open(path))
    rows, cur = [], None
    while True:
        r = get(f"{GAMMA}/markets/keyset?closed=true&limit=500&volume_num_min=10000"
                + (f"&after_cursor={urllib.parse.quote(cur)}" if cur else ""))
        for m in r.get("markets") or []:
            ev = (m.get("events") or [{}])[0]
            rows.append({"id": m["id"], "created": m.get("createdAt") or m.get("startDate"),
                         "closed": m.get("closedTime") or m.get("endDate"), "vol": m.get("volumeNum"),
                         "event": ev.get("id") or m["id"], "q": (m.get("question") or "")[:90],
                         "clob": bool(m.get("clobTokenIds"))})
        cur = r.get("next_cursor")
        if not cur or not r.get("markets"):
            break
    os.makedirs(OUT, exist_ok=True)
    json.dump(rows, open(path, "w"))
    return rows


def eligible(rows):
    out = []
    for r in rows:
        a, b = parse(r["created"]), parse(r["closed"])
        if r["clob"] and a and b and (b - a).total_seconds() >= 2 * 86400 and not SHORT.search(r["q"]):
            out.append((r, b))
    return out


def books(n=400, seed=1):
    ms = []
    for off in range(0, 1000, 100):
        ms += get(f"{GAMMA}/markets?active=true&closed=false&limit=100&offset={off}&volume_num_min=10000"
                  "&order=volumeNum&ascending=false")
    random.Random(seed).shuffle(ms)
    res = collections.defaultdict(list)
    for m in ms[:n]:
        try:
            b = get(f"{CLOB}/book?token_id={json.loads(m['clobTokenIds'])[0]}")
        except Exception:
            continue
        bids = [float(x["price"]) for x in b.get("bids", [])]
        asks = [float(x["price"]) for x in b.get("asks", [])]
        if bids and asks:
            res[min(int((max(bids) + min(asks)) / 2 * 10), 9)].append(min(asks) - max(bids))
    return res


def n_req(p, edge, alpha):
    z_a = {0.05: 1.6449, 0.005 / 3: 2.9352}[alpha]
    return math.ceil(((z_a + Z_B) * math.sqrt(p * (1 - p)) / edge) ** 2)


def main():
    rows = metadata()
    el = eligible(rows)
    print(f"closed markets with volume >= $10k: {len(rows)}; eligible (order book, life >= 2 days, "
          f"not short crypto): {len(el)}")
    half = collections.defaultdict(lambda: [0, set()])
    for r, b in el:
        k = f"{b.year}-H{1 if b.month <= 6 else 2}"
        half[k][0] += 1
        half[k][1].add(r["event"])
    for k in sorted(half):
        print(f"  {k}: {half[k][0]:6d} markets, {len(half[k][1]):6d} distinct events")
    wk = collections.defaultdict(set)
    for r, b in el:
        if b.year == 2026:
            wk[b.isocalendar()[1]].add(r["event"])
    last = [len(wk[k]) for k in sorted(wk) if k < datetime.now(timezone.utc).isocalendar()[1]][-20:]
    print(f"distinct events resolving per week, last 20 full weeks: median {st.median(last)}, "
          f"min {min(last)}, max {max(last)}")
    for k, v in sorted(books().items()):
        print(f"  current books, mid {k / 10:.1f}-{(k + 1) / 10:.1f}: n {len(v):3d}, median spread "
              f"{st.median(v) * 100:.2f}c, p75 {sorted(v)[int(.75 * len(v))] * 100:.2f}c")
    for p in (0.9, 0.8):
        for e in (0.005, 0.01, 0.02):
            print(f"  n_req price {p}, net edge {e * 100:.1f} pp: {n_req(p, e, 0.005 / 3)} (alpha 0.005/3), "
                  f"{n_req(p, e, 0.05)} (alpha 0.05)")
    for cat, rate in FEE_RATE.items():
        print(f"  cost at 0.90, {cat}: half-spread 0.50c + fee {rate * 0.09 * 100:.2f}c")


if __name__ == "__main__":
    main()
