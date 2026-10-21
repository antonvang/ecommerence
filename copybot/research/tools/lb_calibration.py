"""Calibration behind amendment 15b: false-find rate of "one-sided lower 10 % bound > 0" on zero-mean AR(1) daily
series (184 days), for 5-day blocks, the automatic block length (15a) and the lab's rule (backtest.metrics with
block="auto"). Synthetic data only. Usage: python3 research/tools/lb_calibration.py [series]"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lab.engine import backtest  # noqa: E402


def ar(phi, n, seed, mu=0.0):
    r, x, out = random.Random(seed), 0.0, []
    for _ in range(n):
        x = phi * x + r.gauss(0, 1)
        out.append(x + mu)
    return out


def lb5(x):
    b = backtest.bootstrap_means(x, 5, 2000, 7)
    return b[int(0.1 * len(b))]


def lab_rule(x):
    rows = [(i * 86400, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, v) for i, v in enumerate(x)]
    return backtest.metrics(rows, block="auto")["lb_one_sided"]


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    for name, f in (("5-day blocks", lb5), ("lab rule (15a/15b)", lab_rule)):
        print(name, [round(sum(f(ar(p, 184, 5000 + s)) > 0 for s in range(N)) / N, 3) for p in (0.0, 0.3, 0.8)],
              "power", round(sum(f(ar(0.0, 184, 9000 + s, 0.15)) > 0 for s in range(N)) / N, 3))
