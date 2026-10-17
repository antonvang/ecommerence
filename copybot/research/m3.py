"""Mission 3 fast screens M1-M3, exactly as research/MISSION3_REGISTRATION.md. Free Binance archives, read-only.

  python -m research.m3 dev            download 2023 data and run every registered variant
  python -m research.m3 confirm        requires committed research/MISSION3_CHOICE.md; downloads 2024 only then
"""
import bisect, collections, csv, io, json, math, os, random, statistics, subprocess, sys, time, urllib.request, zipfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "data", "research", "m3", "raw")
OUT = os.path.join(HERE, "data", "research", "m3")
BASE = "https://data.binance.vision/data"
YEARS = {"dev": 2023, "confirm": 2024}
FUT_FEE, SPOT_FEE = 0.0005, 0.0010
COST_M1 = 2 * FUT_FEE + 2 * 0.0001
COST_M2 = 2 * FUT_FEE + 2 * 0.0005
COST_M3 = 2 * FUT_FEE + 2 * SPOT_FEE + 4 * 0.0001
MIN_N = {"M1": 200, "M2": 30, "M3": 30}


def fetch(url, path):
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for i in range(5):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"}),
                                          timeout=120).read()
            with open(path + ".part", "wb") as f:
                f.write(data)
            os.replace(path + ".part", path)
            return path
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def rows(zpath):
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            with z.open(name) as f:
                for r in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if r and r[0][:1].isdigit():
                        yield r


def ms(x):
    v = int(float(x))
    return v // 1000 if v > 10 ** 14 else v      # microseconds (newer spot files) -> ms


def klines(kind, year):
    """kind: 'fut', 'spot', 'prem'. Returns {minute_sec: (open, close, volume, taker_buy_volume)}."""
    path = {"fut": "futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-{y}-{m:02d}.zip",
            "spot": "spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-{y}-{m:02d}.zip",
            "prem": "futures/um/monthly/premiumIndexKlines/BTCUSDT/1m/BTCUSDT-1m-{y}-{m:02d}.zip"}[kind]
    out = {}
    for m in range(1, 13):
        rel = path.format(y=year, m=m)
        z = fetch(f"{BASE}/{rel}", os.path.join(RAW, kind, os.path.basename(rel)))
        if not z:
            continue
        for r in rows(z):
            out[ms(r[0]) // 1000] = (float(r[1]), float(r[4]), float(r[5]), float(r[9]) if len(r) > 9 else 0.0)
    return out


def metrics(year):
    out = {}
    d = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
    while datetime.fromtimestamp(d, timezone.utc).year == year:
        day = datetime.fromtimestamp(d, timezone.utc).strftime("%Y-%m-%d")
        z = fetch(f"{BASE}/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-{day}.zip",
                  os.path.join(RAW, "metrics", f"BTCUSDT-metrics-{day}.zip"))
        if z:
            for r in rows(z):
                t = int(datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
                out[t] = float(r[2])
        d += 86400
    return out


# ---------- statistics ----------
def day_lb(trades, q=0.01, n=10000, seed=5):
    by = collections.defaultdict(list)
    for t in trades:
        by[t["t"] // 86400].append(t["net"])
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


def summary(trades, lb=True):
    if not trades:
        return {"n": 0, "mean_net_bp": None, "mean_gross_bp": None, "lb99_bp": None, "win": None}
    net = [t["net"] for t in trades]
    return {"n": len(net), "mean_net_bp": 1e4 * statistics.mean(net),
            "mean_gross_bp": 1e4 * statistics.mean(t["gross"] for t in trades),
            "lb99_bp": (1e4 * day_lb(trades)) if lb and day_lb(trades) is not None else None,
            "win": sum(1 for x in net if x > 0) / len(net)}


# ---------- M1 ----------
def m1_signal(fut, k):
    ts = sorted(fut)
    cs_v, cs_b, acc_v, acc_b = [], [], 0.0, 0.0
    for t in ts:
        acc_v += fut[t][2]
        acc_b += 2 * fut[t][3] - fut[t][2]
        cs_v.append(acc_v)
        cs_b.append(acc_b)
    sig = {}
    for i in range(k, len(ts)):
        if ts[i] - ts[i - k] != 60 * k:
            continue
        v = cs_v[i] - cs_v[i - k]
        if v > 0:
            sig[ts[i]] = (cs_b[i] - cs_b[i - k]) / v
    return sig


def quantiles(values, q):
    s = sorted(values)
    return s[int(q * len(s))], s[int((1 - q) * len(s)) - 1]


def m1_trades(fut, sig, lo, hi, h, direction):
    out, busy = [], 0
    for t in sorted(sig):
        if t < busy:
            continue
        s = sig[t]
        side = 1 if s >= hi else (-1 if s <= lo else 0)
        if not side:
            continue
        if direction == "reversal":
            side = -side
        e, x = fut.get(t + 60), fut.get(t + 60 + 60 * h)
        if not e or not x:
            continue
        g = side * (x[0] / e[0] - 1)
        out.append({"t": t, "gross": g, "net": g - COST_M1})
        busy = t + 60 + 60 * h
    return out


def random_trades(fut, n, h, cost, seed=11):
    ts = sorted(fut)
    rng, out = random.Random(seed), []
    for _ in range(n):
        t = rng.choice(ts)
        e, x = fut.get(t + 60), fut.get(t + 60 + 60 * h)
        if e and x:
            g = rng.choice((1, -1)) * (x[0] / e[0] - 1)
            out.append({"t": t, "gross": g, "net": g - cost})
    return out


def m1(fut, frozen=None):
    res, thresholds = {}, {}
    for k in (1, 5, 15):
        sig = m1_signal(fut, k)
        for q in (0.01, 0.001):
            lo, hi = frozen[f"k{k}_q{q}"] if frozen else quantiles(list(sig.values()), q)
            thresholds[f"k{k}_q{q}"] = (lo, hi)
            for h in (1, 5, 15):
                for d in ("continuation", "reversal"):
                    tr = m1_trades(fut, sig, lo, hi, h, d)
                    res[f"k{k}_q{q}_h{h}_{d}"] = {**summary(tr, lb=False),
                                                   "baseline_net_bp": summary(random_trades(fut, len(tr), h, COST_M1), False)["mean_net_bp"]}
    return res, thresholds


# ---------- M2 ----------
def m2_trades(fut, oi, x, y, h):
    out, busy = [], 0
    for t in sorted(oi):
        if t < busy or (t - 300) not in oi or oi[t - 300] <= 0:
            continue
        d_oi = oi[t] / oi[t - 300] - 1
        a, b = fut.get(t - 300 - (t % 60)), fut.get(t - (t % 60))
        if d_oi > -x or not a or not b:
            continue
        dp = b[0] / a[0] - 1
        side = 1 if dp <= -y else (-1 if dp >= y else 0)
        if not side:
            continue
        te = t - (t % 60) + 60 if t % 60 == 0 else t - (t % 60) + 120     # >= 60 s after the snapshot
        e, xx = fut.get(te), fut.get(te + 60 * h)
        if not e or not xx:
            continue
        g = side * (xx[0] / e[0] - 1)
        out.append({"t": t, "gross": g, "net": g - COST_M2, "side": side})
        busy = te + 60 * h
    return out


def m2_baseline(fut, trades, h):
    if not trades:
        return None
    ts = sorted(fut)
    fwd = [fut[t + 60 * h][0] / fut[t][0] - 1 for t in ts if (t + 60 * h) in fut]
    mu = statistics.mean(fwd)
    return 1e4 * statistics.mean(t["side"] * mu - COST_M2 for t in trades)


def m2(fut, oi):
    res = {}
    for x in (0.005, 0.01, 0.02):
        for y in (0.005, 0.01):
            for h in (15, 60, 240):
                tr = m2_trades(fut, oi, x, y, h)
                res[f"x{x}_y{y}_h{h}"] = {**summary(tr, lb=False), "baseline_net_bp": m2_baseline(fut, tr, h),
                                         "longs": sum(1 for t in tr if t["side"] == 1)}
    return res


# ---------- M3 ----------
def m3_trades(fut, spot, prem, theta, hmax):
    out, busy = [], 0
    ts = sorted(prem)
    idx = {t: i for i, t in enumerate(ts)}
    for t in ts:
        if t < busy or prem[t][1] < theta:
            continue
        te = t + 60
        fe, se = fut.get(te), spot.get(te)
        if not fe or not se:
            continue
        tx = te + 60 * hmax
        i = idx[t] + 1
        while i < len(ts) and ts[i] < te + 60 * hmax:
            if ts[i] >= te and prem[ts[i]][1] <= 0:
                tx = ts[i] + 60
                break
            i += 1
        fx, sx = fut.get(tx), spot.get(tx)
        if not fx or not sx:
            continue
        g = (sx[0] / se[0] - 1) - (fx[0] / fe[0] - 1)
        out.append({"t": t, "gross": g, "net": g - COST_M3, "hold_min": (tx - te) / 60})
        busy = tx
    return out


def m3(fut, spot, prem):
    res = {}
    for theta in (0.0005, 0.001, 0.002):
        for hmax in (60, 480):
            tr = m3_trades(fut, spot, prem, theta, hmax)
            res[f"theta{theta}_H{hmax}"] = {**summary(tr, lb=False), "baseline_net_bp": 0.0,
                                           "mean_hold_min": statistics.mean(t["hold_min"] for t in tr) if tr else None}
    return res


def best(res, minimum):
    ok = {k: v for k, v in res.items() if v["n"] >= minimum and (v["mean_net_bp"] or -1e9) > 0}
    return max(ok, key=lambda k: ok[k]["mean_net_bp"]) if ok else None


def committed(path):
    try:
        dirty = subprocess.check_output(["git", "status", "--porcelain", path], cwd=HERE, text=True).strip()
        tracked = subprocess.check_output(["git", "ls-files", path], cwd=HERE, text=True).strip()
        return bool(tracked) and not dirty
    except Exception:
        return False


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    os.makedirs(OUT, exist_ok=True)
    if cmd == "dev":
        y = YEARS["dev"]
        fut, spot, prem, oi = klines("fut", y), klines("spot", y), klines("prem", y), metrics(y)
        quality = {"fut_minutes": len(fut), "spot_minutes": len(spot), "prem_minutes": len(prem), "oi_snapshots": len(oi),
                   "expected_minutes": 525600, "expected_oi": 105120}
        r1, thr = m1(fut)
        r2 = m2(fut, oi)
        r3 = m3(fut, spot, prem)
        res = {"version": "m3_dev", "year": y, "quality": quality, "M1": r1, "M1_thresholds": thr, "M2": r2, "M3": r3,
               "best": {"M1": best(r1, MIN_N["M1"]), "M2": best(r2, MIN_N["M2"]), "M3": best(r3, MIN_N["M3"])}}
        json.dump(res, open(os.path.join(OUT, "m3_dev.json"), "w"), indent=1)
        print(json.dumps({"quality": quality, "best": res["best"]}, indent=1))
    elif cmd == "confirm":
        ch = os.path.join(HERE, "research", "MISSION3_CHOICE.md")
        if not committed(ch):
            raise SystemExit("research/MISSION3_CHOICE.md must be committed before 2024 data is downloaded")
        raise SystemExit("confirmation code is written only after the development choice (see MISSION3_CHOICE.md)")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
