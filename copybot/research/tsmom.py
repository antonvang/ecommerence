"""tsmom_v1: ugentlig tidsserie-momentum på BTC, ETH, SOL, præcis som research/TSMOM_SPEC.md.

  python -m research.tsmom fetch      hent Binance-candles, Binance- og Hyperliquid-funding, Hyperliquid-candles (SHA-256)
  python -m research.tsmom dev        udvikling + validering: vælg L, beregn n_req (skriver tsmom_v1_dev.json)
  python -m research.tsmom holdout    urørt holdout én gang; kræver at research/TSMOM_FROZEN.md er committet

Kun offentlige data. Ingen ordrer, ingen nøgler.
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
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "research", "tsmom")
DAY, HOUR, WEEK = 86400, 3600, 7 * 86400

ASSETS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
CAPITAL = 10_000.0
NOTIONAL = CAPITAL / 3
FEE = 0.00045
HALF_SPREAD = {"BTC": 0.00002, "ETH": 0.00006, "SOL": 0.00015}   # 3 x målt 16.10.2026, ESTIMERET
LOOKBACKS = (1, 2, 4)
HL_START = int(datetime(2023, 5, 12, tzinfo=timezone.utc).timestamp())
DEV = ("2019-10-07", "2021-12-27")
VAL = ("2022-01-03", "2023-12-25")
HOLDOUT = ("2024-01-01", "2026-10-12")


def ts(d):
    return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def mondays(a, b):
    t = ts(a)
    while t <= ts(b):
        yield t
        t += WEEK


# ---------- data ----------
def get(url, body=None):
    for i in range(6):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json", "User-Agent": "copybot-research/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if i == 5:
                raise
            time.sleep(2 * (i + 1))


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
    man = {"fetched": int(time.time()), "hashes": {}}
    for a, sym in ASSETS.items():
        rows, t = [], ts("2017-01-01") * 1000
        while t < now:
            b = get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&startTime={t}&limit=1000")
            if not b:
                break
            rows += [[int(k[0]) // 1000, float(k[1]), float(k[4])] for k in b]   # dag-start, open, close
            t = int(b[-1][0]) + DAY * 1000
            time.sleep(0.2)
        man["hashes"]["candles_" + a] = save("candles_" + a, rows)
        fr, t = [], ts("2019-09-01") * 1000
        while t < now:
            b = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={t}&limit=1000")
            if not b:
                break
            fr += [[int(x["fundingTime"]) // 1000, float(x["fundingRate"])] for x in b]
            t = int(b[-1]["fundingTime"]) + 1
            if len(b) < 1000:
                break
            time.sleep(0.2)
        man["hashes"]["bfunding_" + a] = save("bfunding_" + a, fr)
        hf, t = [], HL_START * 1000
        while True:
            b = get("https://api.hyperliquid.xyz/info", {"type": "fundingHistory", "coin": a, "startTime": t}) or []
            hf += [[int(x["time"]) // 1000, float(x["fundingRate"])] for x in b]
            if len(b) < 500:
                break
            t = int(b[-1]["time"]) + 1
            time.sleep(0.15)
        man["hashes"]["hfunding_" + a] = save("hfunding_" + a, hf)
        hc = get("https://api.hyperliquid.xyz/info", {"type": "candleSnapshot", "req": {"coin": a, "interval": "1d", "startTime": 0, "endTime": now}}) or []
        man["hashes"]["hlcandles_" + a] = save("hlcandles_" + a, [[int(c["t"]) // 1000, float(c["c"])] for c in hc])
        log(f"{a}: {len(rows)} dage Binance, {len(fr)} Binance-funding, {len(hf)} HL-funding, {len(hc)} HL-dage")
    save("manifest", man)


# ---------- model ----------
class Data:
    def __init__(self, candles, bfund, hfund, hlc=None):
        self.c = {a: {r[0]: (r[1], r[2]) for r in v} for a, v in candles.items()}        # dag -> (open, close)
        self.bf = {a: sorted((r[0], r[1]) for r in v) for a, v in bfund.items()}
        self.hf = {a: sorted((r[0] // HOUR * HOUR, r[1]) for r in v) for a, v in hfund.items()}
        self.hlc = {a: {r[0]: r[1] for r in v} for a, v in (hlc or {}).items()}

    def close(self, a, day):
        x = self.c.get(a, {}).get(day)
        return x[1] if x else None

    def open(self, a, day):
        x = self.c.get(a, {}).get(day)
        return x[0] if x else None

    def signal(self, a, monday, L):
        """Afkast over de L uger før mandag, kun ud fra lukkekurser STRENGT før mandag (søndagens lukke)."""
        last, first = self.close(a, monday - DAY), self.close(a, monday - DAY - L * WEEK)
        if not last or not first:
            return None
        return last / first - 1

    def funding(self, a, t0, t1):
        """[(tid, rate)] i [t0, t1): Hyperliquid fra HL_START, Binance før."""
        src = self.hf.get(a, []) if t0 >= HL_START else self.bf.get(a, [])
        return [(t, r) for t, r in src if t0 <= t < t1]


def data_check(d):
    """Gate D: median |Binance close / Hyperliquid close - 1| over fælles dage < 0,5 % pr. aktiv."""
    out = {}
    for a in ASSETS:
        common = [abs(d.close(a, day) / hc - 1) for day, hc in d.hlc.get(a, {}).items() if d.close(a, day) and hc]
        out[a] = {"days": len(common), "median_gap": statistics.median(common) if common else None}
    out["passed"] = all(v["median_gap"] is not None and v["median_gap"] < 0.005 for k, v in out.items() if k in ASSETS)
    return out


def cost(a, n_sides, mult=1.0):
    return NOTIONAL * (FEE + HALF_SPREAD[a]) * n_sides * mult


def run(d, period, L, mode="ls", delay=False, cost_mult=1.0):
    """mode: 'ls' long/short, 'lf' long/flat, 'bh' altid long. Returnerer ugeliste (netto som andel af kapitalen)."""
    weeks, pos = [], {}
    for m in mondays(*period):
        day_in, day_out = m, m + WEEK
        row = {"monday": datetime.fromtimestamp(m, timezone.utc).strftime("%Y-%m-%d"), "price": 0.0, "funding": 0.0,
               "cost": 0.0, "skipped": [], "positions": {}, "no_funding": [], "sides": 0}
        for a in ASSETS:
            sig = d.signal(a, m, L) if mode != "bh" else 1.0
            pe = d.close(a, day_in) if delay else d.open(a, day_in)
            px = d.close(a, day_out) if delay else d.open(a, day_out)
            if sig is None or not pe or not px:
                if a in pos and pos[a] != 0:
                    row["skipped"].append(a)
                    pos[a] = 0       # ukendt pris: positionen lukkes ikke på en opfundet pris; rapporteres
                continue
            want = (1 if sig > 0 else (-1 if mode == "ls" else 0)) if mode != "bh" else 1
            prev = pos.get(a, 0)
            sides = abs(want - prev)                        # 0 = uændret, 1 = åbn/luk, 2 = vend
            row["cost"] += cost(a, sides, cost_mult)
            row["sides"] += sides
            pos[a] = want
            if want == 0:
                continue
            row["price"] += want * NOTIONAL * (px / pe - 1)
            t0 = day_in + (DAY if delay else 0)
            fr = d.funding(a, t0, t0 + WEEK)
            if not fr:
                row["no_funding"].append(a)   # ingen funding-data: tælles og rapporteres, ikke opfundet
            for t, r in fr:
                c = d.close(a, t - t % DAY) or pe
                row["funding"] += -want * r * NOTIONAL * c / pe   # long betaler positiv funding, short modtager
            row["positions"][a] = want
        net = row["price"] + row["funding"] - row["cost"]
        row.update({"net": net / CAPITAL, "price": row["price"] / CAPITAL, "funding": row["funding"] / CAPITAL,
                    "cost": row["cost"] / CAPITAL})
        weeks.append(row)
    return weeks


# ---------- statistik ----------
def block_lb(x, q, block=8, n=10000, seed=5):
    if len(x) < block:
        return None
    rng = random.Random(seed)
    starts = list(range(len(x) - block + 1))
    k = math.ceil(len(x) / block)
    means = sorted(statistics.mean([v for s in rng.choices(starts, k=k) for v in x[s:s + block]][:len(x)]) for _ in range(n))
    return means[int(q * n)]


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def psr(r, sr0=0.0):
    """Probabilistic Sharpe ratio (Bailey & López de Prado): P(sand Sharpe > sr0), ugentlig."""
    if len(r) < 3 or statistics.stdev(r) == 0:
        return None
    m, s = statistics.mean(r), statistics.stdev(r)
    sr = m / s
    n = len(r)
    g3 = sum((x - m) ** 3 for x in r) / n / s ** 3
    g4 = sum((x - m) ** 4 for x in r) / n / s ** 4
    den = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return norm_cdf((sr - sr0) * math.sqrt(n - 1) / den)


def summarize(weeks):
    r = [w["net"] for w in weeks]
    eq = peak = dd = 0.0
    for x in r:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    t = len(r) // 3
    sd = statistics.stdev(r) if len(r) > 1 else None
    return {"weeks": len(r), "total_net": sum(r), "mean_week": statistics.mean(r) if r else None, "sd_week": sd,
            "sharpe_ann": (statistics.mean(r) / sd * math.sqrt(52)) if sd else None, "max_dd": dd,
            "worst_week": min(r) if r else None, "price": sum(w["price"] for w in weeks), "funding": sum(w["funding"] for w in weeks),
            "cost": sum(w["cost"] for w in weeks), "thirds": [sum(r[:t]), sum(r[t:2 * t]), sum(r[2 * t:])] if t else [],
            "lb_99_5": block_lb(r, 0.005), "psr_0": psr(r), "skipped": sum(len(w["skipped"]) for w in weeks),
            "no_funding_asset_weeks": sum(len(w["no_funding"]) for w in weeks),
            "trades_per_year": sum(w["sides"] for w in weeks) / (len(r) / 52) if r else None}


def n_req(mean, sd, z_a=2.5758, z_b=0.8416):
    if not mean or mean <= 0 or not sd:
        return None
    return math.ceil(((z_a + z_b) * sd / mean) ** 2)


def gates(s, bh, adverse, nreq, dcheck):
    return {
        "D datatjek": bool(dcheck.get("passed")),
        "G1 total netto > 0": s["total_net"] > 0,
        "G2 nedre 99,5 % grænse > 0": (s["lb_99_5"] or -1) > 0,
        "G3 uger >= n_req": nreq is not None and s["weeks"] >= nreq,
        "G4 Sharpe > køb-og-hold": (s["sharpe_ann"] or -9) > (bh["sharpe_ann"] or -9),
        "G5 netto > 0 med 3x omk. og 24 t": adverse["total_net"] > 0,
        "G6 positiv i >= 2 af 3 tredjedele": sum(1 for x in s["thirds"] if x > 0) >= 2,
    }


def data_from_cache():
    man, mh = load("manifest")
    hashes = {"manifest": mh}
    c, bf, hf, hl = {}, {}, {}, {}
    for a in ASSETS:
        c[a], hashes["candles_" + a] = load("candles_" + a)
        bf[a], hashes["bfunding_" + a] = load("bfunding_" + a)
        hf[a], hashes["hfunding_" + a] = load("hfunding_" + a)
        hl[a], hashes["hlcandles_" + a] = load("hlcandles_" + a)
    return Data(c, bf, hf, hl), hashes


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return None


def frozen():
    p = os.path.join(HERE, "research", "TSMOM_FROZEN.md")
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
            if ":" in line and line.split(":")[0] in ("L", "n_req"):
                k, v = line.split(":", 1)
                vals[k] = None if v.strip() == "none" else int(v.strip())
    return vals if "L" in vals and "n_req" in vals else None


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        fetch()
        return
    d, hashes = data_from_cache()
    out = os.path.join(HERE, "data", "research", "results")
    os.makedirs(out, exist_ok=True)
    dc = data_check(d)
    if cmd == "dev":
        dev = {L: summarize(run(d, DEV, L)) for L in LOOKBACKS}
        L = max(LOOKBACKS, key=lambda k: dev[k]["sharpe_ann"] if dev[k]["sharpe_ann"] is not None else -9)
        val = summarize(run(d, VAL, L))
        both = [w["net"] for w in run(d, DEV, L) + run(d, VAL, L)]
        m, sd = statistics.mean(both), statistics.stdev(both)
        res = {"version": "tsmom_v1_dev", "built": int(time.time()), "git": git_head(), "data_check": dc, "dev_by_L": dev, "L": L,
               "validation": val, "dev_val_mean": m, "dev_val_sd": sd, "n_req": n_req(m, sd),
               "baseline_bh_dev": summarize(run(d, DEV, L, mode="bh")), "baseline_bh_val": summarize(run(d, VAL, L, mode="bh")),
               "data_hashes": hashes}
        json.dump(res, open(os.path.join(out, "tsmom_v1_dev.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in res.items() if k != "data_hashes"}, indent=1, default=str))
    elif cmd == "holdout":
        fz = frozen()
        if fz is None:
            raise SystemExit("research/TSMOM_FROZEN.md skal være committet (uden ændringer) før holdout åbnes")
        L, nreq = fz["L"], fz["n_req"]
        weeks = run(d, HOLDOUT, L)
        s = summarize(weeks)
        bh = summarize(run(d, HOLDOUT, L, mode="bh"))
        adverse = summarize(run(d, HOLDOUT, L, delay=True, cost_mult=3.0))
        res = {"version": "tsmom_v1", "built": int(time.time()), "git": git_head(), "period": HOLDOUT, "L": L, "n_req": nreq,
               "data_check": dc, "summary": s, "buy_and_hold": bh, "long_flat": summarize(run(d, HOLDOUT, L, mode="lf")),
               "adverse": adverse, "gates": gates(s, bh, adverse, nreq, dc), "weeks": weeks, "data_hashes": hashes}
        json.dump(res, open(os.path.join(out, "tsmom_v1.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in res.items() if k not in ("weeks", "data_hashes")}, indent=1, default=str))


if __name__ == "__main__":
    main()
