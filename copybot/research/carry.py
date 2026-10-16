"""carry_v1: delta-neutral funding carry på Hyperliquid (short perp + spot), præcis som research/CARRY_SPEC.md.

  python -m research.carry fetch      hent rådata (funding, daglige perp- og spot-candles) med SHA-256
  python -m research.carry dev        udvikling (allerede set periode): pipeline-tjek og støj -> skriver n_req-forslag
  python -m research.carry holdout    holdout (urørt), kræver at research/CARRY_FROZEN.md er committet

Kun læsning af offentlige data. Ingen ordrer, ingen nøgler.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "research", "carry")
API = "https://api.hyperliquid.xyz/info"
DAY = 86400
HOUR = 3600

CAPITAL, SLOTS = 1000.0, 5
N = CAPITAL / (2 * SLOTS)                       # 100 USDC spot + 100 USDC perp-short pr. coin
MIN_APR, AGREE, AGREE_DAYS = 0.10, 0.02, 6
MIN_SPOT_VOL, MIN_PERP_VOL = 500_000.0, 5_000_000.0
FEES = {"perp": 0.00045, "spot": 0.00070}       # pr. side, ESTIMERET (offentlig takst)
SPREAD = {"perp": 0.0002, "spot": 0.0005}       # pr. side, ESTIMERET
LIQ_MULT, LIQ_PENALTY = 1.9, 0.005
DEV = ("2026-04-13", "2026-10-05")
HOLDOUT = ("2023-05-15", "2026-04-06")


def ts(d):
    return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def mondays(a, b):
    t = ts(a)
    while t <= ts(b):
        yield t
        t += 7 * DAY


# ---------- data ----------
def post(body):
    for i in range(6):
        try:
            req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if i == 5:
                raise
            time.sleep(2 * (i + 1))


def pairs():
    """[(perp, spot_token, spot_coin_param)] for spot/USDC-par med en perp af samme navn eller U-navn."""
    sm = post({"type": "spotMeta"})
    toks = {t["index"]: t["name"] for t in sm["tokens"]}
    meta = post({"type": "meta"})
    perps = {a["name"] for a in meta["universe"]}
    out = []
    for p in sm["universe"]:
        base, quote = toks[p["tokens"][0]], toks[p["tokens"][1]]
        if quote != "USDC":
            continue
        perp = base if base in perps else (base[1:] if base.startswith("U") and base[1:] in perps else None)
        if perp:
            out.append((perp, base, p["name"]))
    return out


def save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    raw = json.dumps(obj, sort_keys=True).encode()
    with open(os.path.join(DATA, name + ".json"), "wb") as f:
        f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def load(name):
    with open(os.path.join(DATA, name + ".json"), "rb") as f:
        raw = f.read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def fetch(log=print):
    now = int(time.time() * 1000)
    ps = pairs()
    manifest = {"fetched": int(time.time()), "pairs": ps, "hashes": {}}
    for perp in sorted({p[0] for p in ps}):
        rows, t = [], 0
        while True:
            b = post({"type": "fundingHistory", "coin": perp, "startTime": t}) or []
            rows += [(int(x["time"]) // 1000, float(x["fundingRate"])) for x in b]
            if len(b) < 500:
                break
            t = int(b[-1]["time"]) + 1
            time.sleep(0.15)
        manifest["hashes"]["funding_" + perp] = save("funding_" + perp, rows)
        c = post({"type": "candleSnapshot", "req": {"coin": perp, "interval": "1d", "startTime": 0, "endTime": now}}) or []
        manifest["hashes"]["perp_" + perp] = save("perp_" + perp, c)
        log(f"{perp}: {len(rows)} funding-timer, {len(c)} perp-dage")
    for perp, base, coin in ps:
        c = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": 0, "endTime": now}}) or []
        manifest["hashes"]["spot_" + base] = save("spot_" + base, c)
        log(f"spot {base} ({coin}): {len(c)} dage")
    save("manifest", manifest)


# ---------- model ----------
class Market:
    """Daglige candles (dag-start -> dict) og timers funding for hvert par."""

    def __init__(self, ps, funding, perp_c, spot_c):
        self.ps = ps                      # [(perp, base)]
        # funding-tider har ms efter timen: rund ned til hel time, så de matcher timegitteret
        self.f = {k: {int(t) // HOUR * HOUR: r for t, r in v} for k, v in funding.items()}
        self.perp = {k: {int(c["t"]) // 1000: c for c in v} for k, v in perp_c.items()}
        self.spot = {k: {int(c["t"]) // 1000: c for c in v} for k, v in spot_c.items()}

    def signal(self, perp, monday):
        """Sum af de 168 timers funding før mandag og dækningsgrad (kun data før mandag)."""
        hrs = [self.f.get(perp, {}).get(t) for t in range(monday - 168 * HOUR, monday, HOUR)]
        have = [x for x in hrs if x is not None]
        return sum(have), len(have) / 168

    def eligible(self, monday):
        """[(perp, base, signal)] der opfylder spec §2, kun ud fra de 7 dage før mandag."""
        out, seen = [], set()
        for perp, base in self.ps:
            days = [monday - i * DAY for i in range(1, 8)]
            P, S = self.perp.get(perp, {}), self.spot.get(base, {})
            both = [(float(S[d]["c"]), float(P[d]["c"])) for d in days if d in P and d in S]
            if len(both) < AGREE_DAYS:
                continue
            if statistics.median(abs(s / p - 1) for s, p in both) >= AGREE:
                continue  # navnekollision eller dårlige data
            pv = statistics.mean(float(P[d]["v"]) * float(P[d]["c"]) for d in days if d in P)
            sv = statistics.mean(float(S[d]["v"]) * float(S[d]["c"]) for d in days if d in S)
            if pv < MIN_PERP_VOL or sv < MIN_SPOT_VOL:
                continue
            sig, cov = self.signal(perp, monday)
            if cov < 0.9 or perp in seen:
                continue
            seen.add(perp)
            out.append((perp, base, sig))
        return out

    def price(self, kind, key, day, field):
        book = self.perp if kind == "perp" else self.spot
        c = book.get(key, {}).get(day)
        return float(c[field]) if c else None

    def exit_price(self, kind, key, day, field):
        for k in range(4):  # spec: næste tilgængelige pris inden for 3 dage
            p = self.price(kind, key, day + k * DAY, field)
            if p:
                return p
        return None


def pick(mk, monday):
    el = [e for e in mk.eligible(monday) if e[2] * 52 > MIN_APR]
    return sorted(el, key=lambda e: -e[2])[:SLOTS]


def coin_week(mk, perp, base, monday, delay=False, entering=True, exiting=True, cost_mult=1.0):
    """P&L for én coin i én uge. delay=True: ind/ud ved mandagens LUKKEkurs (24 t forsinket)."""
    field = "c" if delay else "o"
    e_day, x_day = monday, monday + 7 * DAY
    pe, se = mk.price("perp", perp, e_day, field), mk.price("spot", base, e_day, field)
    if not pe or not se:
        return None
    px, sx = mk.exit_price("perp", perp, x_day, field), mk.exit_price("spot", base, x_day, field)
    if not px or not sx:
        return {"status": "ingen-exit", "perp": perp}
    start = e_day + (DAY if delay else 0)
    fund, missing = 0.0, 0
    for h in range(start, start + 7 * DAY, HOUR):
        r = mk.f.get(perp, {}).get(h)
        if r is None:
            missing += 1
            continue
        dc = mk.price("perp", perp, h - h % DAY, "c") or pe
        fund += r * N * dc / pe
    liq = any((mk.price("perp", perp, e_day + i * DAY, "h") or 0) >= LIQ_MULT * pe for i in range(7))
    spot_pnl = N * (sx / se - 1)
    perp_pnl = (-N - LIQ_PENALTY * N) if liq else -N * (px / pe - 1)
    side = lambda leg: (FEES[leg] + SPREAD[leg]) * cost_mult
    cost = (N * side("spot") + N * side("perp")) * ((1 if entering else 0) + (1 if exiting else 0))
    return {"status": "ok", "perp": perp, "funding": fund, "basis": spot_pnl + perp_pnl, "spot": spot_pnl, "perp_pnl": perp_pnl,
            "cost": cost, "net": fund + spot_pnl + perp_pnl - cost, "liquidated": liq, "missing_hours": missing,
            "abs_move_gap": abs((sx / se) - (px / pe))}


def run_period(mk, period, delay=False, cost_mult=1.0, miss_prob=0.0, only=None, seed=11):
    rng = random.Random(seed)
    weeks, held = [], set()
    ms = list(mondays(*period))
    for i, m in enumerate(ms):
        sel = pick(mk, m) if only is None else [e for e in mk.eligible(m) if e[0] in only]
        now = []
        for perp, base, sig in sel:
            if perp not in held and miss_prob and rng.random() < miss_prob:
                continue  # ordren blev ikke fyldt
            now.append((perp, base, sig))
        # lukkes positionen næste mandag? (besluttes med data før næste mandag). Åbne positioner ved periodens
        # slutning værdiansættes til markedspris uden exit-gebyr.
        nxt = {p for p, _, _ in (pick(mk, ms[i + 1]) if i + 1 < len(ms) and only is None else now)}
        rows = []
        for perp, base, sig in now:
            r = coin_week(mk, perp, base, m, delay, entering=perp not in held, exiting=perp not in nxt, cost_mult=cost_mult)
            if r:
                r["signal_apr"] = sig * 52
                rows.append(r)
        ok = [r for r in rows if r["status"] == "ok"]
        weeks.append({"monday": datetime.fromtimestamp(m, timezone.utc).strftime("%Y-%m-%d"), "coins": [r["perp"] for r in ok],
                      "net": sum(r["net"] for r in ok) / CAPITAL, "funding": sum(r["funding"] for r in ok) / CAPITAL,
                      "basis": sum(r["basis"] for r in ok) / CAPITAL, "cost": sum(r["cost"] for r in ok) / CAPITAL,
                      "liquidations": sum(r["liquidated"] for r in ok), "excluded": [r["perp"] for r in rows if r["status"] != "ok"],
                      "missing_hours": sum(r["missing_hours"] for r in ok), "max_gap": max((r["abs_move_gap"] for r in ok), default=0.0),
                      "active": bool(ok)})
        held = {r["perp"] for r in ok}
    return weeks


# ---------- statistik ----------
def block_lb(x, q, block=4, n=10000, seed=5):
    """Nedre q-percentil af middelværdien med blok-bootstrap (sammenhængende blokke à `block` uger)."""
    if len(x) < block:
        return None
    rng = random.Random(seed)
    starts = list(range(len(x) - block + 1))
    k = math.ceil(len(x) / block)
    means = sorted(statistics.mean([v for s in rng.choices(starts, k=k) for v in x[s:s + block]][:len(x)]) for _ in range(n))
    return means[int(q * n)]


def summarize(weeks):
    act = [w for w in weeks if w["active"]]
    r = [w["net"] for w in act]
    eq = peak = dd = 0.0
    for w in weeks:
        eq += w["net"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    third = len(r) // 3
    thirds = [sum(r[:third]), sum(r[third:2 * third]), sum(r[2 * third:])] if third else []
    return {"weeks": len(weeks), "active_weeks": len(act), "total_net": sum(r), "mean_week": statistics.mean(r) if r else None,
            "sd_week": statistics.stdev(r) if len(r) > 1 else None, "funding": sum(w["funding"] for w in act),
            "basis": sum(w["basis"] for w in act), "cost": sum(w["cost"] for w in act), "max_dd": dd,
            "worst_week": min(r) if r else None, "best_week": max(r) if r else None,
            "liquidations": sum(w["liquidations"] for w in act), "excluded_coin_weeks": sum(len(w["excluded"]) for w in weeks),
            "missing_funding_hours": sum(w["missing_hours"] for w in act), "thirds": thirds,
            "lb_99_4": block_lb(r, 0.006), "lb_97_5": block_lb(r, 0.025),
            "avg_coins": statistics.mean(len(w["coins"]) for w in act) if act else 0.0}


def n_req(mean, sd, z_a=2.512, z_b=0.8416):
    """Uger nødvendige for at påvise gennemsnittet (ensidet α = 0,05/8, 80 % styrke)."""
    if not mean or mean <= 0 or not sd:
        return None
    return math.ceil(((z_a + z_b) * sd / mean) ** 2)


def gates(s, adverse, nreq):
    g = {
        "G1 total netto > 0": s["total_net"] > 0,
        "G2 nedre 99,4 % grænse > 0": (s["lb_99_4"] or -1) > 0,
        "G3 aktive uger >= n_req": nreq is not None and s["active_weeks"] >= nreq,
        "G4 max drawdown <= 10 %": s["max_dd"] <= 0.10,
        "G5 værste uge >= -5 %": (s["worst_week"] if s["worst_week"] is not None else -1) >= -0.05,
        "G6 netto > 0 med 3x omkostninger og 24 t forsinkelse": adverse["total_net"] > 0,
        "G7 positiv i >= 2 af 3 tredjedele": sum(1 for t in s["thirds"] if t > 0) >= 2,
    }
    return g


def market_from_cache():
    man, mh = load("manifest")
    ps = [(p, b) for p, b, _ in man["pairs"]]
    f, pc, sc, hashes = {}, {}, {}, {"manifest": mh}
    for perp in {p for p, _ in ps}:
        f[perp], hashes["funding_" + perp] = load("funding_" + perp)
        pc[perp], hashes["perp_" + perp] = load("perp_" + perp)
    for _, base in ps:
        sc[base], hashes["spot_" + base] = load("spot_" + base)
    return Market(ps, f, pc, sc), hashes


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return None


def frozen_committed():
    p = os.path.join(HERE, "research", "CARRY_FROZEN.md")
    if not os.path.exists(p):
        return None
    try:
        st = subprocess.check_output(["git", "status", "--porcelain", p], cwd=HERE, text=True).strip()
        tracked = subprocess.check_output(["git", "ls-files", p], cwd=HERE, text=True).strip()
    except Exception:
        return None
    if st or not tracked:
        return None
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.startswith("n_req:"):
                v = line.split(":")[1].strip()
                return "none" if v == "none" else int(v)  # "none": udviklingens middel <= 0 -> G3 kan ikke opfyldes
    return None


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        fetch()
        return
    mk, hashes = market_from_cache()
    out_dir = os.path.join(HERE, "data", "research", "results")
    os.makedirs(out_dir, exist_ok=True)
    if cmd == "dev":
        weeks = run_period(mk, DEV)
        s = summarize(weeks)
        res = {"version": "carry_v1_dev", "built": int(time.time()), "git": git_head(), "period": DEV, "summary": s, "weeks": weeks,
               "majors": summarize(run_period(mk, DEV, only={"BTC", "ETH", "SOL"})), "n_req_proposed": n_req(s["mean_week"], s["sd_week"]),
               "data_hashes": hashes}
        json.dump(res, open(os.path.join(out_dir, "carry_v1_dev.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in res.items() if k not in ("weeks", "data_hashes")}, indent=1, default=str))
    elif cmd == "holdout":
        nreq = frozen_committed()
        if nreq is None:
            raise SystemExit("research/CARRY_FROZEN.md skal være committet (uden ændringer) før holdout åbnes")
        if nreq == "none":
            nreq = None
        weeks = run_period(mk, HOLDOUT)
        s = summarize(weeks)
        adverse = summarize(run_period(mk, HOLDOUT, delay=True, cost_mult=3.0))
        res = {"version": "carry_v1", "built": int(time.time()), "git": git_head(), "period": HOLDOUT, "n_req": nreq, "summary": s,
               "adverse": adverse, "missed_10pct": summarize(run_period(mk, HOLDOUT, miss_prob=0.10)),
               "majors": summarize(run_period(mk, HOLDOUT, only={"BTC", "ETH", "SOL"})), "gates": gates(s, adverse, nreq),
               "weeks": weeks, "data_hashes": hashes}
        json.dump(res, open(os.path.join(out_dir, "carry_v1.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in res.items() if k not in ("weeks", "data_hashes")}, indent=1, default=str))


if __name__ == "__main__":
    main()
