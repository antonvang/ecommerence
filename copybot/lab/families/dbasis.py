"""F2 dbasis: COIN-M quarterly cash-and-carry on altcoins, long spot / short the inverse quarterly in the same coin
(research/families/dbasis.json, research/PROTOCOL_V3.md amendment 8, design research/AENDRING8_DESIGN.md (D) F2).

The instrument is one spot/delivery ratio series per coin (lab.families.transform, model spot_delivery_ratio): per hour
(ts, spot_open / F_open, spot_close / F_close), where F is the price of the held quarterly (USD per coin). Long 1 coin
spot and short an inverse quarterly with face F0 USD is worth S * F0 / F, exactly the ratio S / F, which converges to 1
at delivery and so locks the basis. There is no funding (funding_by is empty).

The held contract is the nearest quarterly with more than 3 days to expiry (lab.engine.data.quarterlies): it rolls at
the first 01:00 UTC with no more than 3 days left (lab.engine.data.roll_time). The series switches contract at that bar,
so the bar that opens at the roll time carries a cross-contract return: every function holds 0 on it ("rolls are a
flat bar": both legs are charged twice). The same rule zeroes the first bar after any roll time inside a data gap, so no
position ever earns a return between two contracts.

Every function has the cross-sectional calling convention fn(bars_by, funding_by, params, fit=None, volume_by=None,
extra=None) and returns {coin: [position per bar]} with positions 0 or +1 (1x, never negative):
- decisions at 01:00 UTC (Mondays for xsbasis) use only closed bars: the close of the 00:00 bar, the price at which
  the engine fills the 01:00 bar (backtest.gross); a decision holds from the 01:00 bar on;
- on a roll day the 01:00 bar is the flat roll bar and the first bar of the new contract: the decision waits for its
  close (02:00 UTC), prices the contract it will hold and holds from the 02:00 bar on; without that bar it is flat;
- B = annualised basis of the held contract = (1 / ratio - 1) x 365 / days to its expiry, at the decision time;
- there is no lookback, so there is no warm-up; a day without its price bar makes no decision (the state is kept).
No signal or return was computed while this file was drafted (amendment 8 point 4).
"""
from __future__ import annotations

import bisect
import math

from lab.engine import data

DAY, HOUR = 86400, 3600
DECISION = HOUR                    # 01:00 UTC
XS_MIN = 0.05                      # xsbasis: only coins with B >= 5 % are eligible (dbasis.json)
EPS = 1e-12                        # float rounding only
ATTRIBUTION_NEEDS_POSITIONS = True  # lab.families.attribution passes the instrument bars and positions


def _monday(day):
    return (day // DAY + 3) % 7 == 0           # 1970-01-01 was a Thursday


def contracts(a, b):
    """[(expiry, held_from, held_to)] of the held quarterly over [a, b] (the same calendar as the transform)."""
    return data.quarterlies(a, b)


def expiry_at(ts, held):
    """Expiry of the contract held at ts, or None (held: contracts(...), sorted by held_from)."""
    i = bisect.bisect_right([h[1] for h in held], ts) - 1
    return held[i][0] if i >= 0 and held[i][1] <= ts < held[i][2] else None


def roll_bars(bars, held):
    """Indices i >= 1 whose bar is the first one at or after a roll time (bars[i - 1] lies before it): the bars that
    carry a return between two contracts, flat in every rule."""
    rolls = sorted({h[1] for h in held})
    out = set()
    for i in range(1, len(bars)):
        j = bisect.bisect_right(rolls, bars[i][0]) - 1
        if j >= 0 and bars[i - 1][0] < rolls[j] <= bars[i][0]:
            out.add(i)
    return out


def basis(ratio, t, expiry):
    """Annualised basis of the held contract priced at ratio S / F at time t: (F / S - 1) x 365 / days to expiry, or
    None."""
    if ratio is None or ratio <= 0 or expiry is None or expiry <= t:
        return None
    return (1.0 / ratio - 1.0) * 365.0 * DAY / (expiry - t)


def _price(at, T, rolls):
    """(decision time, close ratio) for the 01:00 decision of the day: the close of the 00:00 bar, or on a roll day the
    close of the roll bar (the new contract's first bar) with the decision at 02:00. (D, None) without that bar."""
    if T in rolls:
        bar = at.get(T)
        return T + HOUR, (bar[2] if bar else None)
    bar = at.get(T - HOUR)
    return T, (bar[2] if bar else None)


def _span(bars_by):
    ts = [b[0][0] for b in bars_by.values() if b] + [b[-1][0] for b in bars_by.values() if b]
    return (min(ts), max(ts)) if ts else (0, 0)


def _apply(bars, held, decisions):
    """Positions per bar from [(T, position)] decisions (each holds from the bar opening at T), zero on roll bars."""
    pos, cur, j = [], 0.0, 0
    for ts, _, _ in bars:
        while j < len(decisions) and decisions[j][0] <= ts:
            cur = decisions[j][1]
            j += 1
        pos.append(cur)
    for i in roll_bars(bars, held):
        pos[i] = 0.0
    return pos


def _daily(bars_by, decide):
    """{coin: positions}: decide(B or None, T, roll day?, cur) for each 01:00 UTC T from the coin's first to last bar,
    with B priced as in _price; the decision holds from its decision time (T, or T + 1 h on a roll day)."""
    a, b = _span(bars_by)
    held = contracts(a, b)
    rolls = {h[1] for h in held}
    out = {}
    for s, bars in bars_by.items():
        if not bars:
            out[s] = []
            continue
        at = {x[0]: x for x in bars}
        d, cur, dec = bars[0][0] - bars[0][0] % DAY, 0.0, []
        while d + DECISION <= bars[-1][0]:
            T = d + DECISION
            if T >= bars[0][0]:
                D, ratio = _price(at, T, rolls)
                cur = decide(basis(ratio, D, expiry_at(D, held)), T, T in rolls, cur)
                dec.append((D, cur))
            d += DAY
        out[s] = _apply(bars, held, dec)
    return out


def basis_threshold(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Daily 01:00 UTC: enter +1 at B >= theta, exit to 0 at B < theta / 2, otherwise keep the position. The roll (3
    days before expiry) is an exit, as in the design: on the next contract the position starts again only at
    B >= theta (decided at 02:00 on the roll day, on the new contract's first close)."""
    theta = p["theta"]

    def decide(b, T, roll, cur):
        if roll:                           # the design's 'or 3 days before expiry' exit; re-entry needs B >= theta
            cur = 0.0
        if b is None:                      # no price: keep the state (flat after a roll)
            return cur
        return 1.0 if b >= theta - EPS else (0.0 if b < theta / 2 - EPS else cur)
    return _daily(bars_by, decide)


def basis_hold_to_roll(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Only at the first 01:00 UTC after a roll day (the roll time + 1 day): enter +1 if B >= theta and hold to the next
    roll (3 days before expiry); otherwise stay flat until then. Flat from each roll time."""
    theta = p["theta"]
    a, z = _span(bars_by)
    rolls = {h[1] for h in contracts(a, z)}

    def decide(b, T, roll, cur):
        if roll:
            return 0.0
        if T - DAY in rolls:
            return 1.0 if b is not None and b >= theta - EPS else 0.0
        return cur
    return _daily(bars_by, decide)


def basis_cross_section(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Mondays 01:00 UTC: hold +1 in the k coins with the highest B among those with B >= 5 % (ties by coin name),
    0 elsewhere (a coin without its 00:00 close is not eligible), for the week. The roll is a flat bar; a held coin
    continues on the next contract."""
    k = p["k"]
    a, b = _span(bars_by)
    held = contracts(a, b)
    at = {s: {x[0]: x for x in bars} for s, bars in bars_by.items()}
    first = {s: bars[0][0] for s, bars in bars_by.items() if bars}
    last = max((bars[-1][0] for bars in bars_by.values() if bars), default=0)
    dec = {s: [] for s in bars_by}
    d = a - a % DAY
    rolls = {h[1] for h in held}
    while d + DECISION <= last:
        T = d + DECISION
        if _monday(d) and T not in rolls:                 # rolls are Wednesdays: never a Monday
            e = expiry_at(T, held)
            cand = []
            for s in bars_by:
                bar = at[s].get(T - HOUR)                 # the close of the 00:00 bar
                v = basis(bar[2], T, e) if bar is not None else None
                if v is not None and v >= XS_MIN - EPS:
                    cand.append((-v, s))
            pick = {s for _, s in sorted(cand)[:k]}
            for s in bars_by:
                if s in first and T >= first[s]:
                    dec[s].append((T, 1.0 if s in pick else 0.0))
        d += DAY
    return {s: _apply(bars, held, dec[s]) for s, bars in bars_by.items()}


def carry(bars, pos, held):
    """Per bar (from i = 1, as backtest.gross): the convergence the held contract actually delivered, accrued linearly
    while the position is held: pos_i x (ln(F / S) at the previous close - ln(F / S) at the contract's last close in
    the series) x (t_i - t_{i-1}) / (time of that last close - t_{i-1}). It is the systematic drift of the basis toward
    where the contract really ended (its roll, or the window end), measured ex post: a level that never converges (a
    USDT spot vs USD index offset, a basis that only oscillates) accrues nothing; the rest of the gross is timing, i.e.
    basis and price P&L."""
    last = {}
    for t, _, c in bars:
        e = expiry_at(t, held)
        if e is not None and c > 0:
            last[e] = (t + HOUR, -math.log(c))       # the close of the contract's last bar, at its end time
    out = []
    for i in range(1, len(bars)):
        p, c, t0, t1 = pos[i], bars[i - 1][2], bars[i - 1][0], bars[i][0]
        e = expiry_at(t0, held)
        end = last.get(e)
        v = p * (-math.log(c) - end[1]) * (t1 - t0) / (end[0] - t0) \
            if p and c > 0 and end is not None and end[0] > t0 else 0.0
        out.append((t1, v))
    return out


def attribution(m, bars=None, pos=None):
    """The family file's attribution rule (amendment 8 point 8) on portfolio metrics (lab/engine/backtest.metrics) and
    the instrument series: the cash flow is the convergence each held contract actually delivered, accrued while held
    (carry); the basis and price P&L is the gross ratio P&L minus that carry. Gates: carry - (fees + spread + slippage) > 0 AND basis and price P&L <= carry.
    The carry is summed as the engine sums gross: per hour the equal-weight mean over the coins with a row."""
    costs = (m.get("fees") or 0.0) + (m.get("spread") or 0.0) + (m.get("slippage") or 0.0)
    gross = m.get("gross_total") or 0.0
    cf = 0.0
    if bars and pos:
        a, z = _span(bars)
        held = contracts(a, z)
        acc = {}
        for s, x in bars.items():
            for ts, v in carry(x, pos[s], held):
                t = acc.setdefault(ts, [0.0, 0])
                t[0] += v
                t[1] += 1
        cf = math.fsum(v / n for v, n in acc.values())
    other = gross - cf
    return {"cash_flow": "locked_basis", "locked_basis_carry": cf, "costs": costs, "gross_ratio_pnl": gross,
            "basis_and_price_pnl": other, "cash_flow_minus_costs": cf - costs,
            "gates": {"locked basis carry - costs > 0": cf - costs > 0,
                      "basis and price P&L <= locked basis carry": other <= cf + 1e-12}}


# ---------- the synthetic convergence test (design (D) F2: "before approval: dbasis.py with roll stitching, plus a
# synthetic convergence test"); approve-family refuses the family unless it passes (lab.families._blocking_problems) ---
SELFTEST_TOL = 1e-9


def synthetic(coins=("AAAUSDT", "BBBUSDT", "CCCUSDT"), start=(2022, 1), months=18, basis0=0.12, jump=0.5):
    """Hourly stitched ratio bars built from the same calendar as the transform: spot S_t is a deterministic
    oscillation; the held quarterly is F_t = S_t * (1 + b_c * (e - t) / (e - f0)) for contract c held from f0 (its
    previous roll) to e (its expiry), so its basis converges linearly to 0 at expiry. Coin i has annual basis
    basis0 * (1 - i / len(coins)); contract c of coin i is shifted by `jump` (a large level difference between
    contracts, which a correct stitch never earns). Returns ({coin: bars}, {coin: {ts: (S, F, expiry)}})."""
    from datetime import datetime, timezone
    a = int(datetime(start[0], start[1], 1, tzinfo=timezone.utc).timestamp())
    y, m = start[0] + (start[1] - 1 + months) // 12, (start[1] - 1 + months) % 12 + 1
    b = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp()) - HOUR
    held = contracts(a, b)
    bars_by, truth = {}, {}
    for i, s in enumerate(coins):
        ann, out, tr = basis0 * (1 - i / len(coins)), [], {}
        for t in range(a, b + 1, HOUR):
            e = expiry_at(t, held)
            k = next(j for j, h in enumerate(held) if h[0] == e)
            f0 = held[k][1]
            S = 100.0 * (1 + 0.3 * math.sin(t / (9 * DAY) + i)) * (1 + jump * (k % 2) * 0)
            lock = ann * (e - f0) / (365.0 * DAY)          # the basis locked at the contract's start
            F = S * (1 + lock * (e - t) / (e - f0)) * (1 + jump * (k % 2))
            tr[t] = (S, F, e)
            out.append(t)
        # the series: ratio S / F per hour; open = the previous hour's close (continuous within a contract)
        bars, prev = [], None
        for t in out:
            S, F, e = tr[t]
            c = S / F
            o = c if prev is None or expiry_at(t, held) != expiry_at(t - HOUR, held) else prev
            bars.append((t, o, c))
            prev = c
        bars_by[s], truth[s] = bars, tr
    return bars_by, truth


def convergence_selftest():
    """Explicit pass/fail criteria, all on synthetic data (no file, no network, no real price):
    1. calendar: every contract's roll time is a Wednesday 01:00 UTC, 55 hours before a Friday 08:00 UTC expiry,
       held windows are contiguous (no gap, no overlap);
    2. basis: B at a known synthetic bar equals the constructed annual basis within 1e-9 (relative);
    3. flat rolls: every function holds 0 on every roll bar;
    4. no cross-contract return: with contract levels shifted by 50 % between contracts, the gross P&L of a position
       held through every contract equals the sum of within-contract ratio returns (the shift is never earned);
    5. convergence: at each contract's roll bar and last held bar, F/S equals the constructed linearly converging
       basis (within 1e-9), and a position held from the first non-roll bar to the last bar earns ln(F/S) at entry
       minus ln(F/S) at the last bar (the engine's simple returns within 1e-4 of the log difference);
    6. look-ahead: the exact truncation and poison tests of lab.engine.adversarial pass for all 3 functions and both
       variants;
    7. attribution: on converging contango both gates pass; with a flipped sign (backwardation) the carry - costs
       gate fails; a profitable mean-reversion book on a ratio that never converges fails the 'basis and price P&L <=
       carry' gate; a constant offset that never converges (USDT spot vs USD index) accrues no carry and fails;
    8. strict look-ahead: poisoning the decision bar itself and every later bar never changes a position up to it.
    Returns {"ok": bool, "checks": {criterion: bool}, "details": {...}}."""
    from lab.engine import adversarial, backtest
    checks, det = {}, {}
    bars_by, truth = synthetic(jump=0.0)
    jumped, _ = synthetic(jump=0.5)
    a = min(b[0][0] for b in bars_by.values())
    z = max(b[-1][0] for b in bars_by.values())
    held = contracts(a, z)
    ok = True
    for (e, f0, f1), nxt in zip(held, held[1:] + [None]):
        ok &= (f1 // DAY + 3) % 7 == 2 and f1 % DAY == HOUR and e - f1 == 55 * HOUR and (e // DAY + 3) % 7 == 4
        ok &= nxt is None or nxt[1] == f1
    checks["1 calendar: Wednesday 01:00 rolls, 55 h before Friday 08:00 expiries, contiguous"] = bool(ok)
    s0 = next(iter(bars_by))
    t = bars_by[s0][500][0]
    S, F, e = truth[s0][t]
    want = (F / S - 1) * 365 * DAY / (e - t)
    got = basis(S / F, t, e)
    det["basis"] = {"want": want, "got": got}
    checks["2 basis equals the constructed basis"] = got is not None and abs(got - want) <= SELFTEST_TOL * abs(want)
    fns = {"basis_threshold": ({"theta": 0.05}, {"theta": 0.10}), "basis_hold_to_roll": ({"theta": 0.05},
                                                                                        {"theta": 0.10}),
           "basis_cross_section": ({"k": 1}, {"k": 2})}
    flat, adv_ok = True, True
    for fn, grid in fns.items():
        f = globals()[fn]
        for p in grid:
            pos = f(bars_by, {}, p)
            for s, bars in bars_by.items():
                flat &= all(pos[s][i] == 0.0 for i in roll_bars(bars, held))
            tr = adversarial.truncation_test_xs(f, bars_by, {s: {} for s in bars_by}, p, samples=12)
            po = adversarial.poison_test_xs(f, bars_by, {s: {} for s in bars_by}, p)
            adv_ok &= tr["ok"] and po["ok"]
            det[f"{fn} {p}"] = {"truncation": tr, "poison": po}
    checks["3 every function is flat on every roll bar"] = bool(flat)
    strict = True                                       # the decision bar itself poisoned too (stricter than 6)
    ref = bars_by[s0]
    for i in range(len(ref) // 5, len(ref), len(ref) // 5):
        cut = ref[i][0]
        pb = {s: [(t, o, c) if t < cut else (t, o * 1000, c * 1000) for t, o, c in b] for s, b in bars_by.items()}
        for fn, grid in fns.items():
            for p in grid:
                a1, a2 = globals()[fn](bars_by, {}, p), globals()[fn](pb, {}, p)
                strict &= all(a1[s][j] == a2[s][j] for s, b in bars_by.items() for j, x in enumerate(b)
                              if x[0] <= cut)
    checks["6 exact truncation and poison tests pass"] = bool(adv_ok)
    checks["8 strict look-ahead: poisoning the decision bar and everything after never moves a position up to it"] = \
        bool(strict)
    always = {s: _apply(b, held, [(b[0][0], 1.0)]) for s, b in jumped.items()}
    leak = True
    for s, bars in jumped.items():
        g = sum(r[2] for r in backtest.gross(bars, always[s]))
        want = sum(always[s][i] * (bars[i][2] / bars[i - 1][2] - 1) for i in range(1, len(bars))
                   if expiry_at(bars[i][0], held) == expiry_at(bars[i - 1][0], held))
        leak &= abs(g - want) <= SELFTEST_TOL * max(1.0, abs(want))
    checks["4 no return is earned between two contracts"] = bool(leak)
    conv, bars, ann = True, bars_by[s0], 0.12
    for e, f0, f1 in held[1:-1]:
        idx = [i for i, x in enumerate(bars) if f0 <= x[0] < f1]
        if len(idx) < 3:
            continue
        i0, i1 = idx[1], idx[-1]                          # entry priced at the close of the roll bar idx[0]
        lock = ann * (e - f0) / (365.0 * DAY)
        S0, F0, _ = truth[s0][bars[idx[0]][0]]
        S1, F1, _ = truth[s0][bars[i1][0]]
        conv &= abs(math.log(F0 / S0) - math.log(1 + lock * (e - bars[idx[0]][0]) / (e - f0))) <= SELFTEST_TOL
        conv &= abs(F1 / S1 - 1 - lock * (e - bars[i1][0]) / (e - f0)) <= SELFTEST_TOL   # 56 h of basis left
        earned = sum(bars[i][2] / bars[i - 1][2] - 1 for i in range(i0, i1 + 1))
        conv &= abs(earned - (math.log(F0 / S0) - math.log(F1 / S1))) <= 1e-4          # simple vs log returns
    checks["5 within a contract the ratio converges to the constructed basis and earns it"] = bool(conv)
    pos = basis_threshold(bars_by, {}, {"theta": 0.05})
    rows = {s: backtest.apply_costs(backtest.gross(bars_by[s], pos[s]), {}, {"taker_fee": 0.0015,
                                                                             "half_spread": 0.0006,
                                                                             "slippage": 0.0006})
            for s in bars_by}
    m = backtest.metrics(backtest.portfolio(rows))
    att = attribution(m, bars_by, pos)

    def metrics_of(bars, positions):
        r = {s: backtest.apply_costs(backtest.gross(bars[s], positions[s]), {}, {"taker_fee": 0.0015,
                                                                                "half_spread": 0.0006,
                                                                                "slippage": 0.0006})
             for s in bars}
        return backtest.metrics(backtest.portfolio(r))
    flip = {s: [(t, 1 / o, 1 / c) for t, o, c in b] for s, b in bars_by.items()}
    ones = {s: _apply(b, held, [(b[0][0], 1.0)]) for s, b in flip.items()}
    att_b = attribution(metrics_of(flip, ones), flip, ones)
    noise = {s: [(t, 0.99 + 0.02 * math.sin(2 * math.pi * t / (12 * HOUR)),
                  0.99 + 0.02 * math.sin(2 * math.pi * (t + HOUR) / (12 * HOUR))) for t, _, _ in b]
             for s, b in bars_by.items()}               # never converges, oscillates every 12 h
    rev = {s: [0.0] + [1.0 if b[i - 1][2] < 0.99 else 0.0 for i in range(1, len(b))] for s, b in noise.items()}
    for s, b in noise.items():
        for i in roll_bars(b, held):
            rev[s][i] = 0.0
    m_n = metrics_of(noise, rev)
    att_n = attribution(m_n, noise, rev)
    flat = {s: [(t, 0.998, 0.998) for t, _, _ in b] for s, b in bars_by.items()}   # a 20 bp offset, never converging
    att_f = attribution(metrics_of(flat, ones), flat, ones)
    det["attribution"] = {"contango": att, "backwardation": att_b, "noise_trading": att_n, "constant_offset": att_f}
    checks["7 attribution: converging contango passes; backwardation, noise trading and a constant offset fail"] = \
        all(att["gates"].values()) and not att_b["gates"]["locked basis carry - costs > 0"] and \
        m_n["gross_total"] > 0 and not att_n["gates"]["basis and price P&L <= locked basis carry"] and \
        abs(att_f["locked_basis_carry"]) < 1e-12 and not att_f["gates"]["locked basis carry - costs > 0"]
    return {"ok": all(checks.values()), "checks": checks, "details": det}
