"""H27-F draft (MISSION27_3 point 6b, method n6): do BTC vol, trend and quarterly basis forecast next week's
market-wide funding beyond the current level?

  python3 research/tools/n6_funding.py run     refuses until PROTOCOL_V3.md holds a locked amendment for method n6
                                               and the date is >= 2026-11-14 (no historical query before that)

Written before any explore0 funding, kline or basis row was read. This file holds the statistics only (weeks,
outcome, predictors, OLS with Newey-West HAC, the PASS rule); the data loader is written after the lock.
"""
import datetime as dt
import json
import math
import os
import re
import statistics as st
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
from lab.edgemonitor import t_cdf  # noqa: E402

PROTOCOL = os.path.join(HERE, "research", "PROTOCOL_V3.md")
EARLIEST = dt.date(2026, 11, 14)
FIRST_WEEK = dt.date(2020, 3, 2)
LAST_DAY = dt.date(2021, 12, 31)
MIN_COINS = 20             # point 2
MIN_PRINTS = 18            # of 21 per week
LAGS = 4                   # point 5
ALPHA = 0.005              # point 6
MIN_PAIRS_X3 = 52          # point 7
PLACEBO_SHIFT = 4          # point 6


def weeks():
    """The 95 explore0 week starts (Mondays) whose week ends by 2022-01-01 00:00 UTC (point 2)."""
    out, w = [], FIRST_WEEK
    while w + dt.timedelta(7) <= LAST_DAY + dt.timedelta(1):
        out.append(w)
        w += dt.timedelta(7)
    return out


def outcome(rates_by_coin):
    """M_t: cross-sectional median of each coin's mean 8 h funding in the week; None below MIN_COINS valid coins.
    rates_by_coin = {sym: [rate, ...]} for one week (point 3)."""
    means = [st.fmean(r) for r in rates_by_coin.values() if len(r) >= MIN_PRINTS]
    return st.median(means) if len(means) >= MIN_COINS else None


def share_above(rates_by_coin, level=0.0003):
    means = [st.fmean(r) for r in rates_by_coin.values() if len(r) >= MIN_PRINTS]
    return sum(m > level for m in means) / len(means) if len(means) >= MIN_COINS else None


def x1_vol(closes):
    """Annualised sd of 1 h log returns in the week (point 4, X1)."""
    r = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    return st.stdev(r) * math.sqrt(24 * 365) if len(r) >= 2 else None


def x2_ret(first_close, last_close):
    return math.log(last_close / first_close)


def x3_basis(days, perp_rates):
    """Week mean of daily annualised basis (F/S - 1) * 365 / tau minus annualised perp funding (point 4, X3).
    days = [(F, S, tau_days)], perp_rates = the week's 8 h BTCUSDT funding rates."""
    if not days or not perp_rates:
        return None
    basis = st.fmean((f / s - 1) * 365 / tau for f, s, tau in days)
    return basis - st.fmean(perp_rates) * 3 * 365


def _inv(m):
    n = len(m)
    a = [row[:] + [float(i == j) for j in range(n)] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-300:
            raise ValueError("singular")
        a[c], a[p] = a[p], a[c]
        piv = a[c][c]
        a[c] = [v / piv for v in a[c]]
        for r in range(n):
            if r != c and a[r][c]:
                f = a[r][c]
                a[r] = [v - f * w for v, w in zip(a[r], a[c])]
    return [row[n:] for row in a]


def ols_hac(y, X, lags=LAGS):
    """OLS of y on the rows of X (include the constant yourself) with Newey-West (Bartlett) HAC.
    Returns (beta, se, t, p) with p two-sided from Student t on n - k df (point 5)."""
    n, k = len(y), len(X[0])
    xtx = [[sum(X[t][i] * X[t][j] for t in range(n)) for j in range(k)] for i in range(k)]
    xty = [sum(X[t][i] * y[t] for t in range(n)) for i in range(k)]
    inv = _inv(xtx)
    beta = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]
    e = [y[t] - sum(beta[i] * X[t][i] for i in range(k)) for t in range(n)]
    s = [[sum(e[t] ** 2 * X[t][i] * X[t][j] for t in range(n)) for j in range(k)] for i in range(k)]
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        for i in range(k):
            for j in range(k):
                s[i][j] += w * sum(e[t] * e[t - lag] * (X[t][i] * X[t - lag][j] + X[t - lag][i] * X[t][j])
                                   for t in range(lag, n))
    v = [[sum(inv[i][a] * s[a][b] * inv[b][j] for a in range(k) for b in range(k)) for j in range(k)]
         for i in range(k)]
    se = [math.sqrt(max(v[i][i], 0.0)) for i in range(k)]
    tt = [beta[i] / se[i] if se[i] else None for i in range(k)]
    p = [2 * (1 - t_cdf(abs(x), n - k)) if x is not None else None for x in tt]
    return beta, se, tt, p


def _fit(M, X, shift):
    """b_k from M_{t+1} = a + c M_t + b X_{t-shift}; only t where all three exist."""
    rows = [(M[t + 1], M[t], X[t - shift]) for t in range(shift, len(M) - 1)
            if None not in (M[t + 1], M[t], X[t - shift])]
    if len(rows) < 8:
        return None
    beta, se, tt, p = ols_hac([r[0] for r in rows], [[1.0, r[1], r[2]] for r in rows])
    return {"n": len(rows), "b": beta[2], "t": tt[2], "p": p[2], "rows": rows}


def test_k(M, X, min_pairs=8):
    """Point 6 for one predictor: p <= 0.005, same sign of b in each chronological half, placebo |t| < 2."""
    main = _fit(M, X, 0)
    if main is None or main["n"] < min_pairs:
        return {"verdict": "UNTESTABLE", "n": main["n"] if main else 0}
    rows = main.pop("rows")
    half = len(rows) // 2
    hb = []
    for part in (rows[:half], rows[half:]):
        b, _, _, _ = ols_hac([r[0] for r in part], [[1.0, r[1], r[2]] for r in part], lags=0)
        hb.append(b[2])
    pl = _fit(M, X, PLACEBO_SHIFT)
    pt = pl["t"] if pl else None
    ok = (main["p"] is not None and main["p"] <= ALPHA and (hb[0] > 0) == (hb[1] > 0) == (main["b"] > 0)
          and pt is not None and abs(pt) < 2)
    return {"verdict": "PASS" if ok else "SCREEN_FAIL", **main, "halves_b": hb, "placebo_t": pt}


def locked(text):
    """A locked amendment for method n6 is a PROTOCOL_V3 heading naming 'metode n6'."""
    return re.search(r"^## Ændring [^\n]*metode n6\b", text, re.M) is not None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    today = dt.datetime.now(dt.timezone.utc).date()
    if argv[:1] != ["run"]:
        print("usage: n6_funding.py run")
        return
    if today < EARLIEST or not locked(open(PROTOCOL, encoding="utf-8").read()):
        print(json.dumps({"refused": "no locked amendment for method n6 or before 2026-11-14 (no historical query)"}))
        return
    print(json.dumps({"refused": "data loader not written yet; it is written after the lock"}))


if __name__ == "__main__":
    main()
