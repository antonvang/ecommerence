"""Strict look-ahead scan of the templates that need extra data (metrics, dvol, stable, rates, taker, volume) and the
two that take dollar volume: synthetic data, cuts at random hours and exactly at decision midnights; the extra data is
cut with adversarial.cut_bundle (hourly values before the cut, daily values of days closed by it)."""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab.engine import catalogue, adversarial
import strict_lookahead_scan as S
DAY, H = 86400, 3600
bars, fund = S.market(nsym=12, hours=24 * 160, seed=9)
bars["BTCUSDT"], fund["BTCUSDT"] = bars.pop("S0USDT"), fund.pop("S0USDT")       # btc_volume_share needs BTC
rng = random.Random(4)
hours = sorted({ts for b in bars.values() for ts, _, _ in b})
days = sorted({ts // DAY * DAY for ts in hours})
extra = {
    "metrics": {s: {d: {"rows": 288, "oi": abs(rng.gauss(1e6, 2e5)), "top": abs(rng.gauss(1.2, 0.2)),
                        "acct": abs(rng.gauss(1.1, 0.2))} for d in days} for s in bars},
    "dvol": {s.replace("USDT", ""): {d: abs(rng.gauss(60, 10)) for d in days} for s in bars},
    "stable": {d: 1e11 * (1 + 0.001 * i + rng.gauss(0, 0.002)) for i, d in enumerate(days)},
    "rates": {d: 1.5 + rng.gauss(0, 0.05) * i ** 0.5 for i, d in enumerate(days)},
    "volume": {s: {ts: abs(rng.gauss(1e6, 3e5)) for ts in hours} for s in bars},
    "taker": {s: {ts: abs(rng.gauss(5e5, 2e5)) for ts in hours} for s in bars},
}


def run(fam, params, kw, b, f):
    if kw == "volume_by":
        return fam(b, f, params, None, (extra if b is bars else cut)["volume"])
    return fam(b, f, params, None, extra=extra if b is bars else cut)


def strict(fam, params, kw, samples=15):
    global cut
    full = run(fam, params, kw, bars, fund)
    ref = min(bars, key=lambda s: len(bars[s]))
    lo = 24 * 100
    idx = random.Random(11).sample(range(lo, len(bars[ref])), samples)
    mid = [i for i, (ts, _, _) in enumerate(bars[ref]) if ts % DAY == 0 and i > lo]
    idx = sorted(set(idx + random.Random(12).sample(mid, min(15, len(mid)))
                     + [i for i in mid if catalogue._is_monday_midnight(bars[ref][i][0])]))
    bad = 0
    for i in idx:
        t = bars[ref][i][0]
        b2, f2 = S.cut_at(bars, fund, t)
        cut = adversarial.cut_bundle(extra, t)
        part = run(fam, params, kw, b2, f2)
        bad += any(abs(part[s][-1] - full[s][len(b2[s]) - 1]) > 1e-12 for s in bars)
    return len(idx), bad


cut = None


def cheat(b, f, p, fit=None, extra=None):                 # sanity: reads the current bar's close
    return {s: [0.0] + [1.0 if x[i][2] > x[i - 1][2] else -1.0 for i in range(1, len(x))] for s, x in b.items()}


print("sanity cheat:", strict(cheat, {}, "extra"))
names = [n for n, t in sorted(catalogue.TEMPLATES.items()) if t.get("needs") and "cm" not in t["needs"]]
names += [n for n, t in sorted(catalogue.TEMPLATES.items()) if t.get("needs_volume")]
for name in names:
    t = catalogue.TEMPLATES[name]
    kw = "volume_by" if t.get("needs_volume") else "extra"
    grid = t["grid"] if isinstance(t["grid"], list) else [S.first_params(t["grid"])]
    for params in grid[:2]:
        try:
            n, bad = strict(t["family"], params, kw)
            print(f"{name} {params}: {'OK' if not bad else 'LOOK-AHEAD'} ({bad}/{n} cuts)")
        except Exception as e:
            print(f"{name} {params}: ERROR {e!r}"[:200])
