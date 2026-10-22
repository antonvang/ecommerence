"""Speed-ups of adversarial.placebo_returns and _period_sharpe (2026-10-22) change no result: both are compared, on
random inputs with partial periods, uneven symbols, missing funding and zero positions, with the code as it was before
(copied verbatim below as ref_*), and must agree exactly (==, not approximately). No network, no files."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.engine import adversarial, backtest  # noqa: E402


# ---------- the code before the speed-up, verbatim (lab/engine/adversarial.py at 3816bb1) ----------
def ref_placebo_returns(per_symbol_bars, per_symbol_pos, funding, costs, n=60, min_days=7, seed=17, offset=3600):
    """Amendment 15 point 2 and 15a point 1 (replaces 11d's market shift and the block shuffle): each draw takes ONE
    whole number k of decision periods (UTC days from `offset`) in [min_days, periods - min_days), common to all
    symbols; the complete periods are shifted circularly by k: every bar takes the return (open and close relative to
    the previous close) of the bar at the same place in the source period, and every settlement the funding at the
    same place in the source period, so the price path is rebuilt without a jump and a position without timing gets
    exactly the same period results. Partial periods at the ends stay as they are. Positions are unchanged. Sharpe
    over decision periods as placebo_circular. Returns the share of placebos at or above the actual Sharpe (within
    1e-9: ties count against the strategy)."""
    rng = random.Random(seed)

    def period(ts):
        return (ts - offset) // 86400

    def core(bars):
        """{period: [bar index]} of the complete periods (24 bars), bar 0 excluded (it earns no return)."""
        per = {}
        for i in range(1, len(bars)):
            per.setdefault(period(bars[i][0]), []).append(i)
        return {p: ix for p, ix in per.items() if len(ix) == 24}

    def shifted(s, bars, k):
        f = funding.get(s, {})
        per = core(bars)
        ps = sorted(per)
        if len(ps) < 2 or not k:
            return bars, f
        src = {p: ps[(j + k) % len(ps)] for j, p in enumerate(ps)}
        g = {i: (bars[i][1] / bars[i - 1][2], bars[i][2] / bars[i - 1][2]) for i in range(1, len(bars))}
        nb, c = [bars[0]], bars[0][2]
        for i in range(1, len(bars)):
            p = period(bars[i][0])
            j = per[src[p]][per[p].index(i)] if p in src else i
            go, gc = g[j]
            nb.append((bars[i][0], c * go, c * gc))
            c *= gc
        nf = {}
        for t, v in f.items():
            p = period(t)
            nf[t] = f.get(t + (src[p] - p) * 86400, 0.0) if p in src else v
        return nb, nf

    if not per_symbol_bars:
        return {"actual": None, "p": None, "n": n}
    base, sims = ref_period_sharpe(per_symbol_bars, per_symbol_pos, funding, costs, offset), []
    periods = min(len(core(b)) for b in per_symbol_bars.values())
    for _ in range(n):
        k = rng.randrange(min_days, periods - min_days) if periods > 2 * min_days else 0
        bb, ff = {}, {}
        for s, b in per_symbol_bars.items():
            bb[s], ff[s] = shifted(s, b, k)
        sims.append(ref_period_sharpe(bb, per_symbol_pos, ff, costs, offset) or 0.0)
    if base is None:
        return {"actual": None, "p": None, "n": n}
    tol = 1e-9 * max(1.0, abs(base))
    return {"actual": base, "p": sum(1 for x in sims if x >= base - tol) / n, "n": n, "placebo_mean": sum(sims) / n,
            "method": "complete decision periods shifted by one common whole number; positions unchanged "
                      "(amendments 15 and 15a)"}


def ref_period_sharpe(bars_by, pos_by, fund_by, costs, offset=3600):
    """Annualised net Sharpe over decision periods (UTC days shifted by `offset`)."""
    rows = backtest.portfolio({s: backtest.apply_costs(backtest.gross(b, pos_by[s]), fund_by.get(s, {}), costs)
                               for s, b in bars_by.items()})
    per = {}
    for r in rows:
        per[(r[0] - offset) // 86400] = per.get((r[0] - offset) // 86400, 0.0) + r[7]
    x = [per[k] for k in sorted(per)]
    if len(x) < 2:
        return None
    m = math.fsum(x) / len(x)
    sd = math.sqrt(math.fsum((v - m) ** 2 for v in x) / (len(x) - 1))
    return m / sd * math.sqrt(365) if sd > 0 else None




def market(rng, symbols=3, days=40):
    start = 1609459200 + rng.randrange(0, 24) * 3600                   # partial first and last periods
    bars, pos, fund = {}, {}, {}
    for k in range(symbols):
        n = days * 24 - rng.randrange(0, 30)
        px, b = 100.0, []
        for i in range(n):
            o = px
            px *= math.exp(rng.gauss(0, 0.01))
            b.append((start + i * 3600, o, px))
        bars[f"S{k}"] = b
        pos[f"S{k}"] = [rng.choice((0.0, 0.0, 1.0, -1.0, 0.5)) for _ in range(n)]
        fund[f"S{k}"] = {start + i * 3600: rng.uniform(-0.0005, 0.001) for i in range(0, n, 8) if rng.random() > 0.1}
    return bars, pos, fund


class Identical(unittest.TestCase):
    def test_placebo_returns_and_period_sharpe_agree_exactly_with_the_old_code(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                bars, pos, fund = market(rng, symbols=1 + seed % 3)
                costs = {"taker_fee": rng.uniform(0, 0.001), "half_spread": rng.uniform(0, 0.0005),
                         "slippage": rng.uniform(0, 0.0005)}
                self.assertEqual(adversarial._period_sharpe(bars, pos, fund, costs),
                                 ref_period_sharpe(bars, pos, fund, costs))
                self.assertEqual(adversarial.placebo_returns(bars, pos, fund, costs, n=8, seed=seed),
                                 ref_placebo_returns(bars, pos, fund, costs, n=8, seed=seed))

    def test_edge_cases(self):
        costs = {"taker_fee": 0.0004, "half_spread": 0.0001, "slippage": 0.0002}
        self.assertEqual(adversarial.placebo_returns({}, {}, {}, costs), ref_placebo_returns({}, {}, {}, costs))
        rng = random.Random(9)
        bars, pos, fund = market(rng, symbols=1, days=3)                 # too few periods: no shift
        self.assertEqual(adversarial.placebo_returns(bars, pos, fund, costs, n=4),
                         ref_placebo_returns(bars, pos, fund, costs, n=4))
        flat = {k: [0.0] * len(v) for k, v in pos.items()}             # no position: sd 0, Sharpe None
        self.assertEqual(adversarial._period_sharpe(bars, flat, fund, costs),
                         ref_period_sharpe(bars, flat, fund, costs))


if __name__ == "__main__":
    unittest.main()
