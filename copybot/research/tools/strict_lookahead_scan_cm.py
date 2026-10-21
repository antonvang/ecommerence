import sys, math, random
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))); sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from lab.engine import catalogue, adversarial
import strict_lookahead_scan as S
DAY = 86400
bars, fund = S.market(nsym=12, hours=24 * 160, seed=9)
rng = random.Random(4)
days = sorted({ts // DAY * DAY for b in bars.values() for ts, _, _ in b})
cm = {"cm": {m: {s: {d: abs(rng.gauss(2.0, 0.5)) * (1 + 0.001 * i) for i, d in enumerate(days)} for s in bars}
             for m in ("CapMVRVCur", "SplyCur")}}
def strict_extra(fam, params, samples=20):
    full = fam(bars, fund, params, None, extra=cm)
    ref = min(bars, key=lambda s: len(bars[s]))
    idx = sorted(random.Random(11).sample(range(24 * 100, len(bars[ref])), samples))
    # also force cuts exactly at Monday midnights, where the weekly decisions happen
    mondays = [i for i, (ts, _, _) in enumerate(bars[ref]) if catalogue._is_monday_midnight(ts) and i > 24 * 100]
    bad = 0
    for i in idx + mondays:
        cut = bars[ref][i][0]
        b2, f2 = S.cut_at(bars, fund, cut)
        part = fam(b2, f2, params, None, extra=adversarial.cut_bundle(cm, cut))
        bad += any(abs(part[s][-1] - full[s][len(b2[s]) - 1]) > 1e-12 for s in bars)
    return len(idx) + len(mondays), bad
# sanity: a family that cheats with the current close must be caught
def cheat(b, f, p, fit=None, extra=None):
    return {s: [0.0] + [1.0 if x[i][2] > x[i - 1][2] else -1.0 for i in range(1, len(x))] for s, x in b.items()}
print("sanity cheat:", strict_extra(cheat, {}))
for name in ("mvrv_value", "supply_dilution"):
    t = catalogue.TEMPLATES[name]
    for params in t["grid"][:2]:
        n, bad = strict_extra(t["family"], params)
        print(f"{name} {params}: {'OK' if not bad else 'LOOK-AHEAD'} ({bad}/{n} cuts)")
