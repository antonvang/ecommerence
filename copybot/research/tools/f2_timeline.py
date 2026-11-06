"""F2 timeline conventions (director order 53 P0) - PROPOSAL ONLY, synthetic only.

Implements, as pure functions, the conventions proposed in research/desk/F2_AMBIGUITY_RESOLUTION_PROPOSAL.md for the
locked F2 draft (research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md, section F2). Nothing here changes F2, reads market
data, opens the kline cache or touches the network. Every timestamp is computed from calendar arithmetic; every price in
the tests is synthetic.

Kline facts used (Binance archive convention, DATA_CONTRACT_F2_C1 section 4):
- a 1h bar is identified by its open_time o (UTC, aligned to the hour); it covers trades in [o, o + 3600 s);
- close_time = o + 3 599 999 ms; its `close` is the last trade price at or before close_time;
- the bar is final, and so may be used, only from o + 3600 s ("availability", PROTOCOL_V3 section 4: only closed bars).

Day conventions (which bars' closes make up UTC day D; returns are log ratios of consecutive closes):
- B23 (recommended, MATERIEL): closes of bars D-1 23:00 .. D 22:00 (24 closes, 23 returns = the movement during bars
  opened D 00:00 .. D 22:00). The movement of bar D 23:00 belongs to no day (embargo hour).
- A24 (literal full day): closes of bars D-1 23:00 .. D 23:00 (25 closes, 24 returns). Leak-free in content, but the
  last input close is available exactly at target start (no margin) and is shared with the target.
- A23: closes of bars D 00:00 .. D 23:00 (24 closes, 23 returns). Same availability problem as A24.
- L24 (off-by-one, LEAK): "the 00:00 close of day D+1" read as the bar OPENED at D+1 00:00; its price is formed inside
  the target day. Only here as a negative control.

    python3 research/tools/f2_timeline.py examples      # JSON: timelines, window counts, power (no data)
    python3 research/tools/f2_timeline.py selftest
"""
from __future__ import annotations

import calendar
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p2_power  # noqa: E402  (stdlib-only scenario module)

VERSION = "f2_timeline/1 (PROPOSED, order 53 P0)"
HOUR = 3600
DAY = 86400


def ts(y, m, d, hh=0, mm=0, ss=0):
    return calendar.timegm((y, m, d, hh, mm, ss))


def iso(t):
    """UTC ISO text for seconds (int or float; floats keep milliseconds)."""
    whole = int(math.floor(t))
    ms = int(round((t - whole) * 1000))
    base = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(whole))
    return base + (".%03d" % ms if ms else "")


HOLDOUT_START = ts(2024, 1, 1)
RESERVED_START = ts(2025, 1, 1)
# half-open [start, end), PROTOCOL_V3 section 2 and 10c
WINDOWS = {
    "explore0": (ts(2020, 3, 1), ts(2022, 1, 1)),
    "train3": (ts(2022, 1, 1), ts(2023, 7, 1)),
    "validation3": (ts(2023, 7, 1), ts(2024, 1, 1)),
    "train3+validation3": (ts(2022, 1, 1), ts(2024, 1, 1)),
}

CONVENTIONS = {
    "B23": {"first_bar_h": -1, "n_closes": 24, "status": "PROPOSED_RECOMMENDED_MATERIEL"},
    "A24": {"first_bar_h": -1, "n_closes": 25, "status": "LITERAL_NO_MARGIN"},
    "A23": {"first_bar_h": 0, "n_closes": 24, "status": "NO_MARGIN"},
    "L24": {"first_bar_h": 0, "n_closes": 25, "status": "NEGATIVE_CONTROL_LEAK"},
}

HAR_ROWS = 365          # proposed reading of "OLS paa de foregaaende 365 dage": 365 regression rows (AMB-03)
HAR_LAGS = (1, 7, 30)
EWMA_LAMBDA = 0.94
EWMA_MAX_SEED_WEIGHT = 0.05
LOCK_DELAY_S = 1800     # nominal lock 30 min after the input cutoff
MARGIN_S = 300          # lock must be at least 5 min before target start


class TimelineError(Exception):
    pass


# ------------------------------------------------------------------ bars and days

def bar_close_time_ms(o):
    return o * 1000 + 3_599_999


def bar_available(o):
    return o + HOUR


def day_start(t):
    return int(t - t % DAY)


def day_bounds(t):
    s = day_start(t)
    return s, s + DAY


def day_bars(day, conv="B23"):
    c = CONVENTIONS[conv]
    if day % DAY:
        raise TimelineError("day not aligned to 00:00 UTC")
    return [day + (c["first_bar_h"] + k) * HOUR for k in range(c["n_closes"])]


def returns_per_day(conv="B23"):
    return CONVENTIONS[conv]["n_closes"] - 1


def movement_bars(day, conv="B23"):
    """Bars whose price movement forms the day's returns (all closes but the first are return end points)."""
    return day_bars(day, conv)[1:]


def validate_bars(rows):
    """rows: [(open_time_ms, close, close_time_ms)] in file order. Returns {open_time_s: close}. Fail-closed:
    misaligned hour, wrong close_time, duplicate or non-increasing open_time, non-finite or non-positive close."""
    out, prev = {}, None
    for o_ms, close, ct_ms in rows:
        if not isinstance(o_ms, int) or o_ms % (HOUR * 1000):
            raise TimelineError("open_time not aligned to the hour")
        if ct_ms != o_ms + 3_599_999:
            raise TimelineError("close_time != open_time + 3599999 ms")
        if prev is not None and o_ms <= prev:
            raise TimelineError("duplicate or decreasing open_time")
        if not (isinstance(close, (int, float)) and math.isfinite(close) and close > 0):
            raise TimelineError("close not finite and > 0")
        out[o_ms // 1000] = float(close)
        prev = o_ms
    return out


def day_rv(closes, day, conv="B23"):
    """RV of day or None if any needed close is missing (never filled, interpolated or rescaled)."""
    bars = day_bars(day, conv)
    got = [closes.get(o) for o in bars]
    if any(v is None for v in got):
        return None
    return math.fsum(math.log(got[k] / got[k - 1]) ** 2 for k in range(1, len(got)))


def rv_series(closes, first_day, last_day, conv="B23", lo_bound=None, hi_bound=None):
    """{day: rv} for complete days in [first_day, last_day]. Bars outside [lo_bound, hi_bound) are never read
    (window isolation: no history carries over between windows)."""
    out = {}
    d = first_day
    while d <= last_day:
        bars = day_bars(d, conv)
        if (lo_bound is None or bars[0] >= lo_bound) and (hi_bound is None or bars[-1] < hi_bound):
            v = day_rv(closes, d, conv)
            if v is not None and v > 0:     # RV = 0 (all-flat day) makes QLIKE undefined: treated as incomplete
                out[d] = v
        d += DAY
    return out


# ------------------------------------------------------------------ cutoff, lock, target

def forecast_timeline(target_day, conv="B23", lock_delay=LOCK_DELAY_S):
    """The forecast for target_day uses days <= target_day - 1. Only the last input day matters for the timeline."""
    last_in = target_day - DAY
    inp = day_bars(last_in, conv)
    tgt = day_bars(target_day, conv)
    cutoff = max(bar_available(o) for o in inp)
    return {
        "convention": conv,
        "target_day": target_day,
        "last_input_day": last_in,
        "input_bars": inp,
        "last_input_bar_open": max(inp),
        "last_input_close_time_ms": bar_close_time_ms(max(inp)),
        "input_cutoff": cutoff,
        "lock": cutoff + lock_delay,
        "target_start": target_day,
        "target_end": target_day + DAY,
        "target_bars": tgt,
        "target_first_close_time_ms": bar_close_time_ms(min(tgt)),
        "target_data_complete": max(bar_available(o) for o in tgt),
        "earliest_reveal": target_day + DAY + HOUR,
    }


def check_timeline(tl, margin=MARGIN_S):
    """Flags: content_leak (an input bar has trades at/after target start), availability_at_or_after_target (an input
    is only final at/after target start), shared_mark (a close is both input and target), lock_ok (cutoff <= lock <=
    target_start - margin and lock before the first target close), reveal_ok."""
    s = tl["target_start"]
    content = [o for o in tl["input_bars"] if o + HOUR > s]
    avail = [o for o in tl["input_bars"] if bar_available(o) >= s]
    shared = sorted(set(tl["input_bars"]) & set(tl["target_bars"]))
    lock_ok = (tl["input_cutoff"] <= tl["lock"] <= s - margin
               and tl["lock"] * 1000 < tl["target_first_close_time_ms"])
    reveal_ok = tl["earliest_reveal"] >= tl["target_data_complete"] and tl["earliest_reveal"] > tl["target_end"]
    if content:
        verdict = "LEAK"
    elif avail or shared or not lock_ok:
        verdict = "NO_MARGIN"
    else:
        verdict = "OK"
    return {"content_leak": bool(content), "availability_at_or_after_target": bool(avail), "shared_mark": shared,
            "lock_ok": lock_ok, "reveal_ok": reveal_ok, "verdict": verdict}


# ------------------------------------------------------------------ HAR(1,7,30)

def har_feature_days(origin):
    """Features at origin day t: daily RV_t, weekly mean RV_{t-6..t}, monthly mean RV_{t-29..t}."""
    return {"d1": [origin], "w7": [origin - k * DAY for k in range(7)], "m30": [origin - k * DAY for k in range(30)]}


def har_rows(last_input_day, n_rows=HAR_ROWS):
    """Regression rows (target tau, feature origin tau - 1) for tau in [L - n_rows + 1, L]."""
    return [(last_input_day - k * DAY, last_input_day - (k + 1) * DAY) for k in range(n_rows)]


def har_required_days(last_input_day, n_rows=HAR_ROWS):
    need = set()
    for tau, origin in har_rows(last_input_day, n_rows):
        need.add(tau)
        for days in har_feature_days(origin).values():
            need.update(days)
    for days in har_feature_days(last_input_day).values():
        need.update(days)
    return sorted(need)


def _x(rv, origin):
    f = har_feature_days(origin)
    vals = [rv[d] for d in f["m30"]]     # KeyError -> incomplete
    return [1.0, rv[origin], math.fsum(vals[:7]) / 7, math.fsum(vals) / 30]


def _solve(a, b):
    n = len(b)
    m = [list(map(float, a[i])) + [float(b[i])] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-300:
            raise TimelineError("singular normal equations")
        m[c], m[p] = m[p], m[c]
        piv = m[c][c]
        m[c] = [v / piv for v in m[c]]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [vr - f * vc for vr, vc in zip(m[r], m[c])]
    return [m[i][n] for i in range(n)]


def har_forecast(rv, last_input_day, n_rows=HAR_ROWS):
    """(value, info) or (None, reason). Every required day must be complete (no gap, no fill). Uses only days
    <= last_input_day. A value <= 0 or non-finite is floored (proposal AMB-07) at the smallest positive target RV
    in the estimation rows and flagged."""
    try:
        rows = har_rows(last_input_day, n_rows)
        X = [_x(rv, origin) for _, origin in rows]
        y = [rv[tau] for tau, _ in rows]
        x0 = _x(rv, last_input_day)
    except KeyError:
        return None, "incomplete_span"
    c = math.fsum(y) / len(y)
    if not c > 0:
        return None, "non_positive_mean"
    Xs = [[1.0] + [v / c for v in r[1:]] for r in X]
    ys = [v / c for v in y]
    k = 4
    xtx = [[math.fsum(r[i] * r[j] for r in Xs) for j in range(k)] for i in range(k)]
    xty = [math.fsum(r[i] * yy for r, yy in zip(Xs, ys)) for i in range(k)]
    b = _solve(xtx, xty)
    coefs = [b[0] * c, b[1], b[2], b[3]]
    value = math.fsum(bb * xx for bb, xx in zip(coefs, x0))
    value, floored = har_floor(value, y)
    if value is None:
        return None, "no_positive_target"
    return value, {"coefs": coefs, "rows": len(y), "floored": floored}


def har_floor(value, est_targets):
    """AMB-07 proposal: a HAR forecast <= 0 or non-finite is replaced by the smallest positive target RV of its own
    estimation rows (point-in-time) and flagged; the coin-day is never dropped (dropping would favour HAR)."""
    if math.isfinite(value) and value > 0:
        return value, False
    pos = [v for v in est_targets if v > 0]
    if not pos:
        return None, True
    return min(pos), True


# ------------------------------------------------------------------ EWMA 0.94

def ewma_burn_in(lam=EWMA_LAMBDA, max_seed_weight=EWMA_MAX_SEED_WEIGHT):
    n = 1
    while lam ** (n - 1) > max_seed_weight:
        n += 1
    return n


def ewma_run(rv, last_input_day, max_span=HAR_ROWS + 30):
    """Consecutive complete days ending at last_input_day (newest last), truncated to max_span. A missing day ends
    the run: the recursion restarts after it."""
    run = []
    d = last_input_day
    while d in rv and len(run) < max_span:
        run.append(d)
        d -= DAY
    run.reverse()
    return run


def ewma_forecast(rv, last_input_day, lam=EWMA_LAMBDA, burn_in=None, max_span=HAR_ROWS + 30):
    burn_in = ewma_burn_in(lam) if burn_in is None else burn_in
    run = ewma_run(rv, last_input_day, max_span)
    if len(run) < burn_in:
        return None, "burn_in"
    s = rv[run[0]]
    for d in run[1:]:
        s = lam * s + (1 - lam) * rv[d]
    return s, {"run_start": run[0], "run_days": len(run), "seed_weight": lam ** (len(run) - 1)}


# ------------------------------------------------------------------ windows and counts

def first_rv_day(win_start, conv="B23"):
    d = win_start
    while day_bars(d, conv)[0] < win_start:
        d += DAY
    return d


def window_targets(window, conv="B23", n_rows=HAR_ROWS, carry_over=False):
    """Scorable HAR targets inside a window. Without carry-over (PROTOCOL_V3 section 2) the first HAR target needs
    n_rows + 30 complete RV days inside the window. A target is scorable only if all its bars and the day itself
    lie inside the window; a forecast whose target is outside is never produced."""
    start, end = WINDOWS[window]
    if carry_over:
        first_target = start
    else:
        d0 = first_rv_day(start, conv)
        first_target = d0 + (n_rows + 30) * DAY
    last_target = end - DAY
    while last_target >= first_target and max(day_bars(last_target, conv)) >= end:
        last_target -= DAY
    n = 0 if last_target < first_target else (last_target - first_target) // DAY + 1
    needed_hi = max(day_bars(last_target, conv)) if n else None
    return {"window": window, "convention": conv, "rows": n_rows, "carry_over": carry_over,
            "first_target": first_target if n else None, "last_target": last_target if n else None,
            "targets": n, "max_bar_open_needed": needed_hi,
            "max_availability_needed": bar_available(needed_hi) if n else None}


def rows_for_data_days(data_days):
    """Reading R6b: 'the preceding 365 days' = 365 data days incl. the 30 lag days -> data_days - 30 rows."""
    return data_days - 30


def coin_eligible(closes, window):
    """Literal 'fuld daekning' (AMB-05 proposal): every hourly bar in [start, end) present and valid."""
    start, end = WINDOWS[window]
    need = range(start, end, HOUR)
    have = sum(1 for o in need if closes.get(o) is not None)
    total = len(need)
    return have == total, have / total


# ------------------------------------------------------------------ loss and cross-section

def qlike(rv, f):
    if not (rv > 0 and f > 0):
        raise TimelineError("QLIKE needs rv > 0 and f > 0")
    q = rv / f
    return q - math.log(q) - 1


def daily_mean_d(d_by_coin):
    """Equal-weight cross-sectional mean over coins with a scored pair that day (AMB-08 proposal)."""
    vals = [v for v in d_by_coin.values() if v is not None]
    return math.fsum(vals) / len(vals) if vals else None


# ------------------------------------------------------------------ power

def power_table(days=(730, 546, 335, 334, 276, 275), coins=(20, 15), rhos=(0.5, 0.8),
                effects=(0.02, 0.05, 0.08, 0.10), alpha=0.05, hac=1.5):
    rows = []
    for d in days:
        for c in coins:
            for r in rhos:
                row = {"days": d, "coins": c, "rho_c": r}
                for e in effects:
                    row["e%.2f" % e] = round(p2_power.dm_power(e, c, d, r, alpha, hac)[0], 3)
                row["mde80"] = round(mde(d, c, r, alpha=alpha, hac=hac), 4)
                rows.append(row)
    return rows


def mde(days, coins, rho_c, power=0.8, alpha=0.05, hac=1.5):
    lo, hi = 0.0, 5.0
    for _ in range(80):
        m = (lo + hi) / 2
        if p2_power.dm_power(m, coins, days, rho_c, alpha, hac)[0] < power:
            lo = m
        else:
            hi = m
    return hi


def rho_max_for_power(effect, days, coins=20, power=0.8, alpha=0.05, hac=1.5):
    z = p2_power.zq(alpha) + p2_power.zq(1 - power)
    n_eff = (z / effect) ** 2
    return (coins * days / hac / n_eff - 1) / (coins - 1)


def a8_translation():
    """AMB-11 option: read amendment 8 point 14 on the daily cross-sectional mean dbar, SR_d = mean/sd * sqrt(365).
    Returns the power at SR 3.0 and alpha_F / 3 for 6, 9 and 12 months (same formula as p2_power.a8_check)."""
    return {"%dm" % m: round(p2_power.sr_power(3.0, int(m * 30.4), 365, p2_power.ALPHA_F / 3), 3) for m in (6, 9, 12)}


# ------------------------------------------------------------------ CLI

def _tl_text(tl):
    out = {k: (iso(v) if k in ("target_day", "last_input_day", "input_cutoff", "lock", "target_start", "target_end",
                               "target_data_complete", "earliest_reveal", "last_input_bar_open") else v)
           for k, v in tl.items() if k not in ("input_bars", "target_bars")}
    out["last_input_close_time"] = iso(tl["last_input_close_time_ms"] / 1000)
    out["target_first_close_time"] = iso(tl["target_first_close_time_ms"] / 1000)
    del out["last_input_close_time_ms"], out["target_first_close_time_ms"]
    out["input_bar_opens"] = "%s .. %s" % (iso(tl["input_bars"][0]), iso(tl["input_bars"][-1]))
    out["target_bar_opens"] = "%s .. %s" % (iso(tl["target_bars"][0]), iso(tl["target_bars"][-1]))
    out["check"] = check_timeline(tl)
    return out


def examples():
    t = ts(2023, 2, 1)
    rep = {"version": VERSION, "note": "calendar arithmetic only; no market data",
           "timelines_2023_02_01": {c: _tl_text(forecast_timeline(t, c)) for c in CONVENTIONS},
           "windows": [], "power": power_table(), "a8_translation": a8_translation(),
           "rho_max_e0.08_p0.8": {str(d): round(rho_max_for_power(0.08, d), 3) for d in (730, 334)}}
    for w in WINDOWS:
        for conv in ("B23", "A23"):
            for co in (False, True):
                r = window_targets(w, conv, carry_over=co)
                for k in ("first_target", "last_target", "max_bar_open_needed", "max_availability_needed"):
                    if r[k] is not None:
                        r[k] = iso(r[k])
                rep["windows"].append(r)
    return rep


def selftest():
    for conv, want in (("B23", "OK"), ("A24", "NO_MARGIN"), ("A23", "NO_MARGIN"), ("L24", "LEAK")):
        got = check_timeline(forecast_timeline(ts(2023, 2, 1), conv))["verdict"]
        assert got == want, (conv, got)
    assert len(har_required_days(ts(2023, 1, 31))) == 395
    assert window_targets("train3+validation3")["targets"] == 334
    assert window_targets("explore0")["targets"] == 275
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "examples"
    if cmd == "selftest":
        r = selftest()
        print("selftest OK")
        return r
    if cmd == "examples":
        print(json.dumps(examples(), indent=1, sort_keys=True))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
