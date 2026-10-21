import sys, json, random
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))); sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import strict_lookahead_scan as S
from lab.families import dbasis
spec = json.load(open("/home/anton/copybot-dev/copybot/research/families/drafts/dbasis.json"))
# ratio S/F slightly below 1 (contango), 200 days, includes quarterly rolls
bars, fund = S.market(nsym=6, hours=24 * 200, seed=21, ratio=True)
bars = {s: [(ts, o * 0.985, c * 0.985) for ts, o, c in b] for s, b in bars.items()}
held = dbasis.contracts(min(b[0][0] for b in bars.values()), max(b[-1][0] for b in bars.values()))
print("rolls in sample:", len(held))
for inst in spec["instances"]:
    f = getattr(dbasis, inst["function"])
    for params in inst["grid"][:2]:
        fn = lambda b, fu: f(b, fu, params, None)
        full = fn(bars, fund)
        n, bad = S.strict(fn, bars, fund, samples=40)
        # also cut exactly at 01:00 and 02:00 UTC decision bars
        ref = min(bars, key=lambda s: len(bars[s]))
        extra_bad = 0
        for i, (ts, _, _) in enumerate(bars[ref]):
            if i > 30 and ts % 86400 in (3600, 7200) and i % 5 == 0:
                b2, f2 = S.cut_at(bars, fund, ts)
                part = fn(b2, f2)
                extra_bad += any(abs(part[s][-1] - full[s][len(b2[s]) - 1]) > 1e-12 for s in bars)
        held_any = sum(1 for s in full for v in full[s] if v)
        print(f"{inst['function']} {params}: {'OK' if not bad and not extra_bad else 'LOOK-AHEAD'} "
              f"(random {len(bad)}/{n}, decision-hour cuts {extra_bad}); bars with a position: {held_any}")
