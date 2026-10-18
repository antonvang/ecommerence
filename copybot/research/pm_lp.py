"""pm_lp_v1: observationsstudie af likviditetsbelønninger på Polymarket, præcis som research/PM_LP_SPEC.md.

  python -m research.pm_lp collect    fremadrettet indsamling (KRÆVER brugerens godkendelse før start)
  python -m research.pm_lp dev        udvikling + validering (dag D0..D0+13), n_req
  python -m research.pm_lp holdout    kræver committet research/PM_LP_FROZEN.md; åbner holdout én gang

Ingen ordrer, ingen konto, ingen wallet, ingen nøgler. Kun offentlige, læse-only API'er.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import random
import socket
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "research", "pm_lp")
DB = os.path.join(DATA, "pm_lp.db")
CLOB, DAPI, GAMMA = "https://clob.polymarket.com", "https://data-api.polymarket.com", "https://gamma-api.polymarket.com"
DAY = 86400

PANEL = 200
MIN_RATE = 5.0
Q = 100.0                   # aktier pr. side
INV_CAP = 500.0
SNAP_EVERY, TRADES_EVERY, REWARDS_EVERY, STATUS_EVERY = 60, 300, 3600, 6 * 3600
STALE = 180                 # et snapshot gælder højst 180 s
SEED_BASE = 20261017
DEV_DAYS, VAL_DAYS, HOLD_DAYS, TAIL_END = (0, 6), (7, 13), (14, 27), 41
Z_A, Z_B = 2.5758, 0.8416


# ---------- belønningsregel (§4) ----------
def score(v, s):
    return ((v - s) / v) ** 2 if v > 0 and 0 <= s < v else 0.0


def floor_tick(x, tick):
    return round(math.floor(x / tick + 1e-9) * tick, 6)


def ceil_tick(x, tick):
    return round(math.ceil(x / tick - 1e-9) * tick, 6)


def competing_q(bids, asks, mid, v, min_size):
    """(Q1, Q2): konkurrerende score på bud- og udbudssiden af YES-bogen (prisniveauer)."""
    q1 = sum(score(v, mid - p) * z for p, z in bids if z >= min_size and mid - p < v)
    q2 = sum(score(v, p - mid) * z for p, z in asks if z >= min_size and p - mid < v)
    return q1, q2


def combine(q1, q2, mid):
    if 0.10 <= mid <= 0.90:
        return max(min(q1, q2), max(q1, q2) / 3)
    return min(q1, q2)


def quotes(mid, v, tick):
    b, a = floor_tick(mid - v / 2, tick), ceil_tick(mid + v / 2, tick)
    return (b if b > 0 else None), (a if a < 1 else None)


def to_yes(side, price, token, yes_token):
    """Takerens retning i YES-termer: ('buy'|'sell', pris)."""
    side = side.upper()
    if token == yes_token:
        return ("buy" if side == "BUY" else "sell"), price
    return ("sell" if side == "BUY" else "buy"), 1 - price


# ---------- simulation (§4-5) ----------
class Maker:
    """Hypotetisk passiv market maker i ét marked."""

    def __init__(self, yes_token, rule="through"):
        self.yes, self.rule = yes_token, rule
        self.cash = self.inv = 0.0
        self.mark = None
        self.quote = None           # (t, bid, ask, rest_bid, rest_ask)
        self.reward = collections.defaultdict(float)
        self.fills = collections.defaultdict(float)
        self.settled = None

    def value(self):
        return self.cash + self.inv * (self.mark or 0.0)

    def on_snapshot(self, s, quoting=True, reward_mult=1.0):
        """s: dict med t, bb, ba, q1, q2, v, min_size, rate, tick."""
        if self.settled is not None:
            return
        if s["bb"] is None or s["ba"] is None:
            self.quote = None
            return
        mid = (s["bb"] + s["ba"]) / 2
        self.mark = mid
        if not quoting or not s["v"]:
            self.quote = None
            return
        b, a = quotes(mid, s["v"], s["tick"])
        bid_on = b is not None and self.inv < INV_CAP
        ask_on = a is not None and self.inv > -INV_CAP
        q1 = score(s["v"], mid - b) * Q if bid_on else 0.0
        q2 = score(s["v"], a - mid) * Q if ask_on else 0.0
        ours = combine(q1, q2, mid)
        comp = (s["q1"] or 0.0) + (s["q2"] or 0.0)
        if ours > 0 and s["rate"]:
            self.reward[day_of(s["t"])] += reward_mult * s["rate"] / 1440 * ours / (ours + comp)
        self.quote = (s["t"], b if bid_on else None, a if ask_on else None, Q, Q)

    def on_trade(self, t, side, price, size, token):
        if self.settled is not None or self.quote is None or t - self.quote[0] > STALE or t < self.quote[0]:
            return 0.0
        ts, b, a, rb, ra = self.quote
        d, p = to_yes(side, price, token, self.yes)
        x = 0.0
        if d == "sell" and b is not None and (p < b or (self.rule == "at" and p <= b)):
            x = min(size, rb, INV_CAP - self.inv)
            if x > 0:
                self.cash -= b * x
                self.inv += x
                rb -= x
        elif d == "buy" and a is not None and (p > a or (self.rule == "at" and p >= a)):
            x = min(size, ra, INV_CAP + self.inv)
            if x > 0:
                self.cash += a * x
                self.inv -= x
                ra -= x
        self.quote = (ts, b, a, rb, ra)
        if x > 0:
            self.fills[day_of(t)] += x
        return max(x, 0.0)

    def settle(self, payout):
        if self.settled is None:
            self.mark = payout
            self.cash += self.inv * payout
            self.inv = 0.0
            self.settled = payout
            self.quote = None


def day_of(t):
    return int(t // DAY)


def simulate(snaps, trades, yes_token, quoting_days, resolution=None, rule="through", reward_mult=1.0):
    """Én markeds forløb -> {dag: {'reward', 'pnl', 'fills', 'quoting'}} og slutbeholdning.

    snaps/trades: lister sorteret efter tid. quoting_days: dage (unix-dag) hvor markedet er i panelet.
    resolution: (t, payout) eller None. P&L pr. dag = belønning + ændring i markeret værdi.
    """
    m = Maker(yes_token, rule)
    ev = [(s["t"], 0, s) for s in snaps] + [(tr["t"], 1, tr) for tr in trades]
    if resolution:
        ev.append((resolution[0], 2, resolution[1]))
    ev.sort(key=lambda e: (e[0], e[1]))
    out, v0 = {}, 0.0
    held = set()
    starts = [day_of(e[0]) for e in ev[:1]] + ([min(quoting_days)] if quoting_days else [])
    cur = min(starts) if starts else None

    def close_day(d):
        out[d] = {"reward": m.reward.get(d, 0.0), "pnl": m.reward.get(d, 0.0) + m.value() - v0,
                  "fills": m.fills.get(d, 0.0), "quoting": d in quoting_days}

    def advance(to):
        nonlocal cur, v0
        while cur < to:
            if m.inv != 0:
                held.add(cur)
            if cur in quoting_days or cur in held:
                close_day(cur)
            v0 = m.value()
            cur += 1

    for t, kind, x in ev:
        d = day_of(t)
        advance(d)
        if m.inv != 0:
            held.add(d)
        if kind == 0:
            m.on_snapshot(x, quoting=d in quoting_days, reward_mult=reward_mult)
        elif kind == 1:
            m.on_trade(t, x["side"], x["price"], x["size"], x["token"])
            if m.inv != 0:
                held.add(d)
        else:
            if m.inv != 0:
                held.add(d)
            m.settle(x)
    if cur is not None:
        advance(max([cur] + list(quoting_days)))
        if m.inv != 0:
            held.add(cur)
        if cur in quoting_days or cur in held:
            close_day(cur)
    return out, {"inv": m.inv, "mark": m.mark, "settled": m.settled, "value": m.value()}


# ---------- statistik (§6-8) ----------
def cluster_lb(clusters, q=0.005, n=10000, seed=5):
    """clusters: liste af (sum_pnl, antal_markedsdage) pr. marked."""
    cl = [c for c in clusters if c[1] > 0]
    if len(cl) < 2:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        s = k = 0.0
        for a, b in rng.choices(cl, k=len(cl)):
            s += a
            k += b
        means.append(s / k)
    means.sort()
    return means[int(q * n)]


def n_req(mean, sd):
    if mean is None or mean <= 0 or not sd:
        return None
    return math.ceil(((Z_A + Z_B) * sd / mean) ** 2)


def summarize(days, tails=None, bootstrap=True):
    """days: liste af {'market','day','pnl','reward','fills','quoting'}; tails: {market: hale-P&L}."""
    tails = tails or {}
    pnl = [x["pnl"] for x in days]
    total = sum(pnl) + sum(tails.values())
    cl = collections.defaultdict(lambda: [0.0, 0])
    for x in days:
        cl[x["market"]][0] += x["pnl"]
        cl[x["market"]][1] += 1
    for mkt, v in tails.items():
        cl[mkt][0] += v
    by_day = collections.defaultdict(float)
    for x in days:
        by_day[x["day"]] += x["pnl"]
    ds = sorted(by_day)
    t = len(ds) // 3
    thirds = [sum(by_day[d] for d in ds[:t]), sum(by_day[d] for d in ds[t:2 * t]),
              sum(by_day[d] for d in ds[2 * t:]) + sum(tails.values())] if t else []
    rewards = [x["reward"] for x in days if x["quoting"]]
    rw = sum(x["reward"] for x in days)
    return {"market_days": len(days), "markets": len(cl), "total_net": total,
            "mean": total / len(days) if days else None,
            "sd": statistics.stdev(pnl) if len(pnl) > 1 else None,
            "lb_99_5": cluster_lb([tuple(v) for v in cl.values()]) if bootstrap else None,
            "thirds": thirds, "reward_total": rw, "fill_pnl_total": total - rw,
            "median_reward_quoting_day": statistics.median(rewards) if rewards else None,
            "fills_per_day": statistics.mean(x["fills"] for x in days) if days else None,
            "tail_total": sum(tails.values())}


def gates(s, half, at, worst, nreq, d1, d2):
    return {
        "D1 dækning >= 90 % og <= 1 % fejlede trade-polls": bool(d1),
        "D2 >= 50 % af maker-wallets fik REWARD": bool(d2),
        "G1 total netto > 0": s["total_net"] > 0,
        "G2 nedre 99,5 % grænse > 0": (s["lb_99_5"] if s["lb_99_5"] is not None else -1) > 0,
        "G3 markedsdage >= n_req": nreq is not None and s["market_days"] >= nreq,
        "G4 netto > 0 med belønning x 0,5": half["total_net"] > 0,
        "G5 netto > 0 med at-or-through fills": at["total_net"] > 0,
        "G6 positiv i >= 2 af 3 tredjedele": sum(1 for x in s["thirds"] if x > 0) >= 2,
        "G7 median belønning pr. kvoterende dag >= $1": (s["median_reward_quoting_day"] or 0) >= 1.0,
        "G8 netto > 0 med worst-case for uafgjort beholdning": worst["total_net"] > 0,
    }


def verdict(g, dev_val_mean, val_mean):
    if dev_val_mean is None or dev_val_mean <= 0 or val_mean is None or val_mean <= 0:
        return "FAIL"
    if not (g["G1 total netto > 0"] and g["G2 nedre 99,5 % grænse > 0"]):
        return "FAIL"
    return "PASS (observational)" if all(g.values()) else "INSUFFICIENT"


# ---------- panel (§3) ----------
def select_panel(eligible, need, day_index, exclude=()):
    pool = sorted(c for c in eligible if c not in set(exclude))
    random.Random(SEED_BASE + day_index).shuffle(pool)
    return pool[:need]


# ---------- git / segl ----------
def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return None


def committed_values(name, keys):
    p = os.path.join(HERE, "research", name)
    try:
        dirty = subprocess.check_output(["git", "status", "--porcelain", p], cwd=HERE, text=True).strip()
        tracked = subprocess.check_output(["git", "ls-files", p], cwd=HERE, text=True).strip()
    except Exception:
        return None
    if dirty or not tracked:
        return None
    vals = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            if ":" in line and line.split(":")[0].strip() in keys:
                k, v = (x.strip() for x in line.split(":", 1))
                vals[k] = v
    return vals if all(k in vals for k in keys) else None


def start_day():
    v = committed_values("PM_LP_START.md", ("D0",))
    return None if v is None else day_of(datetime.strptime(v["D0"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def frozen():
    v = committed_values("PM_LP_FROZEN.md", ("n_req",))
    return None if v is None else {"n_req": None if v["n_req"] == "none" else int(v["n_req"])}


# ---------- netværk ----------
DNS_TTL = 300
_dns, _real_getaddrinfo = {}, socket.getaddrinfo


def _cached_getaddrinfo(host, port, *a, **k):
    """Amendment 4: successful lookups are kept DNS_TTL seconds in this process (Linux has no local DNS cache and the
    first resolver sometimes drops a query, costing a 5 s timeout). Failures are never kept."""
    key = (host, port, a, tuple(sorted(k.items())))
    hit = _dns.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < DNS_TTL:
        return hit[1]
    res = _real_getaddrinfo(host, port, *a, **k)
    _dns[key] = (now, res)
    return res


def install_dns_cache():
    socket.getaddrinfo = _cached_getaddrinfo


def forget_host(url):
    host = urllib.parse.urlsplit(url).hostname
    for key in [k for k in _dns if k[0] == host]:
        _dns.pop(key, None)


def http(url, body=None, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"User-Agent": "copybot-research/1.0", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            forget_host(url)                      # a failed request never keeps a possibly stale address
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


# ---------- database ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS markets(cid TEXT PRIMARY KEY, yes TEXT, no TEXT, question TEXT, tags TEXT, end_date TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS panel(day INTEGER, cid TEXT, PRIMARY KEY(day, cid));
CREATE TABLE IF NOT EXISTS rewards(t INTEGER, cid TEXT, rate REAL, v REAL, min_size REAL);
CREATE TABLE IF NOT EXISTS snaps(t INTEGER, cid TEXT, bb REAL, ba REAL, q1 REAL, q2 REAL, v REAL, min_size REAL, rate REAL, tick REAL);
CREATE INDEX IF NOT EXISTS snaps_cid_t ON snaps(cid, t);
CREATE TABLE IF NOT EXISTS books_raw(t INTEGER, cid TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS trades(k TEXT, taker INTEGER, cid TEXT, t INTEGER, wallet TEXT, token TEXT, side TEXT,
                                  price REAL, size REAL, PRIMARY KEY(k, taker));
CREATE INDEX IF NOT EXISTS trades_cid_t ON trades(cid, t);
CREATE TABLE IF NOT EXISTS status(t INTEGER, cid TEXT, closed INTEGER, accepting INTEGER, payout REAL);
CREATE TABLE IF NOT EXISTS polls(t INTEGER, kind TEXT, cid TEXT, ok INTEGER);
CREATE TABLE IF NOT EXISTS reward_payouts(wallet TEXT, t INTEGER, size REAL, tx TEXT, PRIMARY KEY(wallet, tx, t));
CREATE TABLE IF NOT EXISTS runs(t INTEGER, host TEXT, pid INTEGER, d0 INTEGER, git TEXT);
"""


def open_db(path=DB):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=60, check_same_thread=False)   # skrivninger går gennem Collector.lock
    db.executescript(SCHEMA)
    return db


def trade_key(x):
    return f"{x.get('transaction_hash')}|{x.get('proxy_wallet')}|{x.get('token_id')}|{x.get('size')}|{x.get('side')}"


# ---------- indsamling (§2-3); startes kun efter brugerens godkendelse ----------
class Collector:
    def __init__(self, db, log=print):
        self.db, self.log, self.lock = db, log, threading.Lock()
        self.cfg = {}                   # cid -> (rate, v, min_size)
        self.last_trade = {}

    def refresh_rewards(self):
        rows, cur = [], ""
        while True:
            r = http(f"{CLOB}/rewards/markets/current" + (f"?next_cursor={urllib.parse.quote(cur)}" if cur else ""))
            rows += r.get("data") or []
            cur = r.get("next_cursor")
            if not cur or cur == "LTE=" or not r.get("data"):
                break
        now = int(time.time())
        self.cfg = {x["condition_id"]: (x.get("total_daily_rate") or 0.0, (x.get("rewards_max_spread") or 0) / 100,
                                        x.get("rewards_min_size") or 0.0) for x in rows}
        with self.lock:
            self.db.executemany("INSERT INTO rewards VALUES(?,?,?,?,?)",
                                [(now, c, *v) for c, v in self.cfg.items()])
            self.db.commit()

    def market(self, cid):
        with self.lock:
            row = self.db.execute("SELECT yes, no FROM markets WHERE cid=?", (cid,)).fetchone()
        if row:
            return row
        m = http(f"{CLOB}/markets/{cid}")
        toks = m.get("tokens") or []
        if len(toks) != 2:
            return None
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO markets VALUES(?,?,?,?,?,?,?)",
                            (cid, toks[0]["token_id"], toks[1]["token_id"], m.get("question"),
                             json.dumps(m.get("tags")), m.get("end_date_iso"), json.dumps(m)))
            self.db.commit()
        return toks[0]["token_id"], toks[1]["token_id"]

    def is_eligible(self, cid, now):
        """§3 (ændring 1): markeds- og bogkrav for én kandidat."""
        try:
            m = http(f"{CLOB}/markets/{cid}")
            end = m.get("end_date_iso")
            end_t = datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp() if end else None
            if (not m.get("active") or m.get("closed") or not m.get("accepting_orders") or len(m.get("tokens") or []) != 2
                    or end_t is None or end_t < now + 3 * DAY):
                return False
            b = http(f"{CLOB}/book?token_id={m['tokens'][0]['token_id']}")
        except Exception:
            return False
        bids = [float(o["price"]) for o in b.get("bids", [])]
        asks = [float(o["price"]) for o in b.get("asks", [])]
        return bool(bids and asks and 0.10 <= (max(bids) + min(asks)) / 2 <= 0.90)

    def refresh_panel(self, day_index, today):
        with self.lock:
            done = self.db.execute("SELECT COUNT(*) FROM panel WHERE day=?", (today,)).fetchone()[0]
        if done:                       # genstart samme dag: fortsæt med dagens panel, vælg ikke igen
            self.log(f"panel dag {day_index}: genoptaget ({done} markeder)")
            return
        cur = [r[0] for r in self.db.execute("SELECT cid FROM panel WHERE day=?", (today - 1,))]
        keep = []
        for cid in cur:
            try:
                m = http(f"{CLOB}/markets/{cid}")
            except Exception:
                continue
            if m.get("active") and not m.get("closed") and m.get("accepting_orders") and \
                    self.cfg.get(cid, (0,))[0] >= MIN_RATE:
                keep.append(cid)
        need = PANEL - len(keep)
        ever = [r[0] for r in self.db.execute("SELECT DISTINCT cid FROM panel")]
        cands = [c for c, (rate, _, _) in self.cfg.items() if rate >= MIN_RATE]
        now = time.time()
        new = []
        for c in select_panel(cands, len(cands), day_index, exclude=ever):
            if len(new) >= need:
                break
            if self.is_eligible(c, now):
                new.append(c)
        with self.lock:
            self.db.executemany("INSERT OR IGNORE INTO panel VALUES(?,?)", [(today, c) for c in keep + new])
            self.db.commit()
        for c in new:
            self.market(c)
        self.log(f"panel dag {day_index}: {len(keep)} beholdt, {len(new)} nye")

    def snapshot(self, cids, raw=False):
        now = int(time.time())
        toks = {}
        for c in cids:
            mk = self.market(c)
            if mk:
                toks[mk[0]] = c
        rows, raws = [], []
        items = list(toks)
        for i in range(0, len(items), 50):
            try:
                books = http(f"{CLOB}/books", [{"token_id": t} for t in items[i:i + 50]])
            except Exception:
                continue
            for b in books:
                cid = toks.get(b.get("asset_id"))
                if not cid:
                    continue
                bids = [(float(o["price"]), float(o["size"])) for o in b.get("bids", [])]
                asks = [(float(o["price"]), float(o["size"])) for o in b.get("asks", [])]
                rate, v, ms = self.cfg.get(cid, (0.0, 0.0, 0.0))
                bb = max((p for p, _ in bids), default=None)
                ba = min((p for p, _ in asks), default=None)
                q1 = q2 = None
                if bb is not None and ba is not None and v:
                    q1, q2 = competing_q(bids, asks, (bb + ba) / 2, v, ms)
                rows.append((now, cid, bb, ba, q1, q2, v, ms, rate, float(b.get("tick_size") or 0.01)))
                if raw:
                    raws.append((now, cid, json.dumps(b)))
        with self.lock:
            self.db.executemany("INSERT INTO snaps VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
            self.db.executemany("INSERT INTO books_raw VALUES(?,?,?)", raws)
            self.db.commit()

    def trades(self, cid):
        start = self.last_trade.get(cid, int(time.time()) - 600) - 120
        got, ok = [], 1
        for taker in (1, 0):
            cur = None
            try:
                while True:   # nyeste først; 'start' filtrerer ikke på serveren (tjekket 16.10), så vi stopper selv
                    u = (f"{DAPI}/v2/trades?condition={cid}&limit=500&taker_only="
                         f"{'true' if taker else 'false'}" + (f"&cursor={urllib.parse.quote(cur)}" if cur else ""))
                    r = http(u)
                    rows = r.get("data") or []
                    for x in rows:
                        if int(x["timestamp"]) >= start:
                            got.append((trade_key(x), taker, cid, int(x["timestamp"]), x.get("proxy_wallet"),
                                        x.get("token_id"), x.get("side"), float(x["price"]), float(x["size"])))
                    cur = (r.get("pagination") or {}).get("next_cursor")
                    if not cur or not rows or min(int(x["timestamp"]) for x in rows) < start:
                        break
            except Exception:
                ok = 0
        if ok:
            self.last_trade[cid] = int(time.time())
        with self.lock:   # én forbindelse delt mellem tråde: al adgang under låsen
            self.db.executemany("INSERT OR IGNORE INTO trades VALUES(?,?,?,?,?,?,?,?,?)", got)
            self.db.execute("INSERT INTO polls VALUES(?,?,?,?)", (int(time.time()), "trades", cid, ok))
            self.db.commit()

    def status(self, cid):
        try:
            m = http(f"{CLOB}/markets/{cid}")
            payout = None
            if m.get("closed"):
                g = http(f"{GAMMA}/markets?condition_ids={cid}")
                op = json.loads(g[0].get("outcomePrices") or "null") if g else None
                if op:
                    y = float(op[0])
                    payout = next((v for v in (0.0, 0.5, 1.0) if abs(y - v) <= 0.01), None)
            with self.lock:
                self.db.execute("INSERT INTO status VALUES(?,?,?,?,?)", (int(time.time()), cid, int(bool(m.get("closed"))),
                                                                         int(bool(m.get("accepting_orders"))), payout))
                self.db.commit()
        except Exception:
            pass

    def run(self, d0):
        """d0: unix-dag for D0. Kvotering/bøger til og med D0+27; status til og med D0+41."""
        self.refresh_rewards()
        last = {"rewards": time.time(), "trades": 0.0, "status": 0.0, "snap": 0.0}
        n_snap = 0
        today = None
        while True:
            now = time.time()
            d = day_of(now)
            if d > d0 + TAIL_END:
                self.log("indsamling færdig")
                return
            if now - last["rewards"] >= REWARDS_EVERY:
                try:
                    self.refresh_rewards()
                except Exception:
                    pass
                last["rewards"] = now
            try:
                if d != today and d <= d0 + HOLD_DAYS[1]:
                    self.refresh_panel(d - d0, d)
                    today = d
                with self.lock:
                    quoting = [r[0] for r in self.db.execute("SELECT cid FROM panel WHERE day=?", (d,))] \
                        if d <= d0 + HOLD_DAYS[1] else []
                if quoting and now - last["snap"] >= SNAP_EVERY:
                    n_snap += 1
                    last["snap"] = now
                    self.snapshot(quoting, raw=n_snap % 15 == 0)
                if quoting and now - last["trades"] >= TRADES_EVERY:
                    last["trades"] = now
                    with ThreadPoolExecutor(4) as ex:
                        list(ex.map(self.trades, quoting))
                if now - last["status"] >= STATUS_EVERY:
                    last["status"] = now
                    with self.lock:
                        ever = [r[0] for r in self.db.execute("SELECT DISTINCT cid FROM panel")]
                    with ThreadPoolExecutor(4) as ex:
                        list(ex.map(self.status, ever))
            except Exception as e:      # ét fejlet trin må ikke stoppe indsamlingen; huller tæller i D1
                self.log(f"fejl {datetime.now(timezone.utc).isoformat()}: {e!r}")
            time.sleep(5)


# ---------- evaluering ----------
def load_market(db, cid, t_end):
    yes = db.execute("SELECT yes FROM markets WHERE cid=?", (cid,)).fetchone()
    snaps = [dict(zip(("t", "bb", "ba", "q1", "q2", "v", "min_size", "rate", "tick"), r)) for r in db.execute(
        "SELECT t, bb, ba, q1, q2, v, min_size, rate, tick FROM snaps WHERE cid=? AND t<? ORDER BY t", (cid, t_end))]
    trades = [dict(zip(("t", "side", "price", "size", "token"), r)) for r in db.execute(
        "SELECT t, side, price, size, token FROM trades WHERE cid=? AND taker=1 AND t<? ORDER BY t", (cid, t_end))]
    res = db.execute("SELECT MIN(t), payout FROM status WHERE cid=? AND payout IS NOT NULL AND t<?", (cid, t_end)).fetchone()
    return (yes[0] if yes else None), snaps, trades, (res if res and res[0] is not None else None)


def evaluate(db, d0, first_day, last_day, rule="through", reward_mult=1.0, worst=False, tail_to=None):
    """Simulerer fra D0 (beholdning føres videre mellem perioder) og returnerer markedsdage first_day..last_day,
    plus en valgfri hale: værdiændring efter last_day til og med tail_to (§5)."""
    panel = collections.defaultdict(set)
    for day, cid in db.execute("SELECT day, cid FROM panel WHERE day BETWEEN ? AND ?", (d0, last_day)):
        panel[cid].add(day)
    t_end = ((tail_to if tail_to is not None else last_day) + 1) * DAY
    days, tails = [], {}
    for cid, qd in panel.items():
        yes, snaps, trades, res = load_market(db, cid, t_end)
        if yes is None:
            continue
        per, end = simulate(snaps, trades, yes, qd, res, rule, reward_mult)
        if not any(first_day <= d <= last_day for d in qd) and not any(
                first_day <= d <= last_day for d in per):
            continue
        for d, x in per.items():
            if first_day <= d <= last_day:
                days.append({"market": cid, "day": d, **x})
        if tail_to is not None:
            tails[cid] = sum(x["pnl"] for d, x in per.items() if d > last_day)
            if worst and end["settled"] is None and end["inv"]:
                tails[cid] += end["inv"] * ((0.0 if end["inv"] > 0 else 1.0) - (end["mark"] or 0.0))
    return days, tails


def coverage(db, d0, last_day):
    q = db.execute("SELECT COUNT(*) FROM snaps s JOIN panel p ON p.cid=s.cid AND p.day=s.t/86400 "
                   "WHERE p.day BETWEEN ? AND ?", (d0, last_day)).fetchone()[0]
    md = db.execute("SELECT COUNT(*) FROM panel WHERE day BETWEEN ? AND ?", (d0, last_day)).fetchone()[0]
    polls = db.execute("SELECT COUNT(*), SUM(1-ok) FROM polls WHERE kind='trades' AND t BETWEEN ? AND ?",
                       (d0 * DAY, (last_day + 1) * DAY)).fetchone()
    snap_cov = q / (md * 1440) if md else 0.0
    fail = (polls[1] or 0) / polls[0] if polls[0] else 1.0
    return {"snapshot_coverage": snap_cov, "trade_poll_fail_rate": fail, "ok": snap_cov >= 0.90 and fail <= 0.01}


def payout_check(db, d0, last_day, log=print):
    a, b = d0 * DAY, (last_day + 1) * DAY
    taker = {r[0] for r in db.execute("SELECT k FROM trades WHERE taker=1 AND t BETWEEN ? AND ?", (a, b))}
    wallets = sorted({r[1] for r in db.execute("SELECT k, wallet FROM trades WHERE taker=0 AND t BETWEEN ? AND ?", (a, b))
                      if r[0] not in taker and r[1]})
    paid = 0
    for w in wallets:
        try:
            r = http(f"{DAPI}/v2/activity?user={w}&type=REWARD&start={a}&end={b}&limit=100")
        except Exception:
            continue
        rows = r.get("data") or []
        db.executemany("INSERT OR IGNORE INTO reward_payouts VALUES(?,?,?,?)",
                       [(w, int(x["timestamp"]), float(x.get("usdc_size") or 0), x.get("transaction_hash")) for x in rows])
        paid += bool(rows)
    db.commit()
    share = paid / len(wallets) if wallets else 0.0
    return {"maker_wallets": len(wallets), "with_reward": paid, "share": share, "ok": share >= 0.50}


def export_manifest(db_path=DB):
    h = hashlib.sha256()
    with open(db_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(path=None, run=True, log=print):
    """Start (or resume) collection. D0 is set once and then always read back (amendment 3): a restart never moves
    the schedule. One collector at a time; every start is recorded in `runs`."""
    from lab.supervisor import AlreadyRunning, acquire_lock, release_lock
    path = path or DB
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        lock = acquire_lock(os.path.join(os.path.dirname(path), "collector.lock"))
    except AlreadyRunning:
        raise SystemExit("en anden pm_lp-indsamler kører allerede (collector.lock): ingen ny startet") from None
    try:
        db = open_db(path)
        row = db.execute("SELECT v FROM meta WHERE k='D0'").fetchone()
        d0 = int(row[0]) if row else day_of(time.time()) + 1
        committed = start_day() if path == DB else None
        if committed is not None and committed != d0:
            raise SystemExit(f"D0 i databasen ({d0}) passer ikke med research/PM_LP_START.md ({committed}): stoppet")
        if row is None:
            db.execute("INSERT INTO meta VALUES('D0', ?)", (str(d0),))
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (int(time.time()), socket.gethostname(), os.getpid(), d0,
                                                          git_head()))
        db.commit()
        day0 = datetime.fromtimestamp(d0 * DAY, timezone.utc).strftime("%Y-%m-%d")
        log(f"start {datetime.now(timezone.utc).isoformat(timespec='seconds')} på {socket.gethostname()}: D0 = {day0}"
            + ("" if row else " (ny; commit research/PM_LP_START.md med denne dato)"))
        if run:
            install_dns_cache()
            Collector(db, log=log).run(d0)
        return d0
    finally:
        release_lock(lock)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    out = os.path.join(HERE, "data", "research", "results")
    os.makedirs(out, exist_ok=True)
    if cmd == "collect":
        if "--approved" not in args:
            raise SystemExit("Indsamlingen kræver brugerens godkendelse: kør med --approved når den er givet.")
        return collect()
    d0 = start_day()
    if d0 is None:
        raise SystemExit("research/PM_LP_START.md (D0) skal være committet")
    db = open_db()
    if cmd == "dev":
        if day_of(time.time()) <= d0 + VAL_DAYS[1]:
            raise SystemExit("validering er ikke slut endnu")
        dev_days, _ = evaluate(db, d0, d0 + DEV_DAYS[0], d0 + DEV_DAYS[1])
        val_days, _ = evaluate(db, d0, d0 + VAL_DAYS[0], d0 + VAL_DAYS[1])
        both = [x["pnl"] for x in dev_days + val_days]
        m = statistics.mean(both) if both else None
        sd = statistics.stdev(both) if len(both) > 1 else None
        res = {"version": "pm_lp_v1_dev", "built": int(time.time()), "git": git_head(), "D0": d0,
               "development": summarize(dev_days), "validation": summarize(val_days),
               "coverage_dev": coverage(db, d0 + DEV_DAYS[0], d0 + DEV_DAYS[1]),
               "coverage_val": coverage(db, d0 + VAL_DAYS[0], d0 + VAL_DAYS[1]),
               "dev_val_mean": m, "dev_val_sd": sd, "n_req": n_req(m, sd), "db_sha256": export_manifest()}
        json.dump(res, open(os.path.join(out, "pm_lp_v1_dev.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps(res, indent=1, default=str))
    elif cmd == "holdout":
        fz = frozen()
        if fz is None:
            raise SystemExit("research/PM_LP_FROZEN.md skal være committet (uden ændringer) før holdout åbnes")
        if day_of(time.time()) <= d0 + TAIL_END:
            raise SystemExit("resolutionssporingen (til D0+41) er ikke slut endnu")
        dv = json.load(open(os.path.join(out, "pm_lp_v1_dev.json"), encoding="utf-8"))
        a, b, tail = d0 + HOLD_DAYS[0], d0 + HOLD_DAYS[1], d0 + TAIL_END
        days, tails = evaluate(db, d0, a, b, tail_to=tail)
        s = summarize(days, tails)
        half = summarize(*evaluate(db, d0, a, b, reward_mult=0.5, tail_to=tail), bootstrap=False)
        at = summarize(*evaluate(db, d0, a, b, rule="at", tail_to=tail), bootstrap=False)
        worst = summarize(*evaluate(db, d0, a, b, worst=True, tail_to=tail), bootstrap=False)
        cov = coverage(db, a, b)
        pay = payout_check(db, a, b)
        g = gates(s, half, at, worst, fz["n_req"], cov["ok"], pay["ok"])
        res = {"version": "pm_lp_v1", "built": int(time.time()), "git": git_head(), "D0": d0, "n_req": fz["n_req"],
               "summary": s, "rewards_half": half, "fills_at_or_through": at, "worst_case_unresolved": worst,
               "coverage": cov, "payout_check": pay, "gates": g,
               "verdict": verdict(g, dv.get("dev_val_mean"), (dv.get("validation") or {}).get("mean")),
               "db_sha256": export_manifest()}
        json.dump(res, open(os.path.join(out, "pm_lp_v1.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps(res, indent=1, default=str))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
