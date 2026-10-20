"""Why does the 11c review always pass? Compare the block placebo (24-bar blocks shuffled) with a circular-shift
placebo (same positions, turnover and exposure; shifted >= 7 days against the funding), and the 1-hour delay with a
24-hour delay, on lane candidates in explore0 (cached files only, no network)."""
import glob, importlib, json, random, statistics, sys
from unittest import mock
sys.path.insert(0, ".")
from lab.engine import adversarial, backtest, data
from lab import explore, families, lane
S, N_CAND, N_SIM = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
fam = families.load("fcarry")
with mock.patch.object(data, "CACHE", S + "/market"), mock.patch.object(explore, "fetch_allowed", lambda *a, **k: False):
    bars, funding, _, _ = explore._files(fam, explore.SPLIT)
cands = [r for f in sorted(glob.glob("/home/anton/ecommerence/copybot/data/lab/artifacts/_explore/*/fcarry_*.json"))
         for r in json.load(open(f)).get("results") or [] if r.get("candidate")]
random.Random(3).shuffle(cands)
costs = lane._stressed(fam["costs"])
print("candidates in artifacts:", len(cands), "| studied:", N_CAND, "| simulations each:", N_SIM, flush=True)
for r in cands[:N_CAND]:
    fn = getattr(importlib.import_module("lab.families.fcarry"), r["function"])
    b = {c: bars[c] for c in (r.get("coins") or sorted(bars)) if c in bars}
    f = {c: funding.get(c, {}) for c in b}
    pos = fn(b, f, r["params"], None)
    sh = lambda p: backtest.sharpe_ann(backtest.portfolio({s: backtest.apply_costs(backtest.gross(b[s], p[s]), f[s], costs) for s in b})) or 0.0
    base = sh(pos)
    blk = adversarial.placebo(b, pos, f, costs, n=N_SIM)
    rng, circ = random.Random(17), []
    for _ in range(N_SIM):
        circ.append(sh({s: (p[k:] + p[:k]) for s, p in pos.items() for k in [rng.randrange(168, len(p) - 168)]}))
    d1 = sh({s: [0.0] + p[:-1] for s, p in pos.items()})
    d24 = sh({s: [0.0] * 24 + p[:-24] for s, p in pos.items()})
    turn = statistics.mean(sum(abs(a - c) for a, c in zip(p[1:], p[:-1])) for p in pos.values())
    print(f"{r['function']:20} {json.dumps(r['params'])[:38]:38} SR {base:6.2f} | block p {blk['p']:.2f} mean {blk['placebo_mean']:6.2f} | circular p {sum(x >= base for x in circ)/N_SIM:.2f} mean {statistics.mean(circ):6.2f} | delay 1h {d1:6.2f} 24h {d24:6.2f} | switches/coin {turn:.0f}", flush=True)
