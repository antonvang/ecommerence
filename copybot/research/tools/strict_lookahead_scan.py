"""Strict look-ahead scan: position i (which earns bar i's close-to-close return) must not change when bar i's close is
replaced by its open and every later bar and funding settlement is removed. Synthetic data only."""
import sys, math, random, itertools, importlib, traceback
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))))
from lab.engine import catalogue
H = 3600
START = 1_600_000_000 // (8 * H) * (8 * H)

def market(nsym=6, hours=24 * 75, seed=3, ratio=False):
    rng = random.Random(seed)
    bars, fund = {}, {}
    for k in range(nsym):
        s, c, b, f = f"S{k}USDT", (1.0 if ratio else 100.0 * (k + 1)), [], {}
        for h in range(hours):
            ts = START + h * H
            c2 = c * math.exp(rng.gauss(0, 0.0005 if ratio else 0.008))
            b.append((ts, c, c2)); c = c2
            if h % 8 == 0:
                f[ts] = rng.gauss(0.0001, 0.0003)
        bars[s], fund[s] = b, f
    return bars, fund

def cut_at(bars, fund, cut):
    out = {}
    for s, b in bars.items():
        pre = [x for x in b if x[0] < cut]
        cur = [x for x in b if x[0] == cut]
        out[s] = pre + ([(cut, cur[0][1], cur[0][1])] if cur else [])
    return out, {s: {k: v for k, v in f.items() if k <= cut} for s, f in fund.items()}

def strict(fn, bars, fund, samples=25, seed=11):
    full = fn(bars, fund)
    ref = min(bars, key=lambda s: len(bars[s]))
    rng = random.Random(seed)
    idx = sorted(rng.sample(range(30, len(bars[ref])), samples))
    bad = []
    for i in idx:
        cut = bars[ref][i][0]
        b2, f2 = cut_at(bars, fund, cut)
        part = fn(b2, f2)
        for s in bars:
            j = len(b2[s]) - 1
            if j >= 0 and abs(part[s][j] - full[s][j]) > 1e-12:
                bad.append((i, s)); break
    return len(idx), bad

def first_params(grid):
    if isinstance(grid, dict):
        return {k: (v[0] if isinstance(v, (list, tuple)) else v) for k, v in grid.items()}
    if isinstance(grid, (list, tuple)) and grid:
        return grid[0]
    return {}

bars, fund = market()
rows = []
for name, t in sorted(catalogue.TEMPLATES.items()):
    if t.get("needs"):
        rows.append((name, "SKIPPED (needs " + ",".join(t["needs"]) + ")")); continue
    fam, params = t["family"], first_params(t.get("grid"))
    try:
        if t.get("cross_sectional"):
            fn = lambda b, f: fam(b, f, params, None)
        else:
            fn = lambda b, f: {s: fam(b[s], f[s], params, None) for s in b}
        n, bad = strict(fn, bars, fund)
        rows.append((name, "OK" if not bad else f"LOOK-AHEAD at {len(bad)}/{n} cuts"))
    except Exception as e:
        rows.append((name, "ERROR " + repr(e)[:120]))
rb, rf = market(ratio=True)
import json
fc = importlib.import_module("lab.families.fcarry")
spec = json.load(open("/home/anton/copybot-dev/copybot/research/families/fcarry.json"))
seen = []
for inst in spec["instances"]:
    for it in (inst, inst.get("successor")):
        if not it: continue
        f = getattr(fc, it["function"])
        for params in it["grid"][:2]:
            try:
                n, bad = strict(lambda b, fu: f(b, fu, params, None), rb, rf)
                rows.append((f"fcarry.{it['function']} {params}", "OK" if not bad else f"LOOK-AHEAD at {len(bad)}/{n} cuts"))
            except Exception as e:
                rows.append((f"fcarry.{it['function']} {params}", "ERROR " + repr(e)[:120]))
for r in rows: print(f"{r[0]:40s} {r[1]}")
