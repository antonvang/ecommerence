"""F1 fcarry: hedged Binance funding carry, long spot / short USD-M perp in the same coin
(research/families/fcarry.json, research/PROTOCOL_V3.md amendment 8).

The instrument is one spot/perp ratio series per coin (lab.families.transform, model spot_perp_ratio). The funding the
functions get is in the cost convention of backtest.apply_costs (minus the settled rate: a +1 position earns it), so the
signal is its negative. Every function has the cross-sectional calling convention
fn(bars_by, funding_by, params, fit=None, volume_by=None, extra=None) and returns {coin: [position per bar]} with
positions 0 or +1 (1x, never negative):
- decisions at 01:00 UTC (Mondays for the weekly rules) use only funding settled before the decision; a decision holds
  from the bar that opens at 01:00, so an entry never collects the 00:00 settlement (amendment 8 point 3);
- signals are sums of settled funding over whole days, annualised x 365/L, so the settlement interval (8, 4 or 2 hours)
  does not matter;
- flat until the lookback lies inside the window (from the coin's first bar): no history crosses windows;
- settled rates have 8 decimals, so a sum exactly at a threshold reaches it: comparisons allow EPS for float rounding.
No signal or return was computed while this file was drafted (amendment 8 point 4).
"""
from __future__ import annotations

import bisect
import math

DAY, HOUR = 86400, 3600
DECISION = HOUR                    # 01:00 UTC
FLOOR_DAY = 0.0003                 # the 0.01 %/8h interest floor, per day
HYST_ENTER_APR = 0.219             # carry_hysteresis enters at APR_7 >= 0.219 (fcarry.json)
EPS = 1e-10                        # far below one rate step (1e-8): float rounding only


def _monday(day):
    return (day // DAY + 3) % 7 == 0           # 1970-01-01 was a Thursday


def _settled(funding):
    """Settlement times and the settled rates (the negated cost-convention funding)."""
    ts = sorted(funding)
    return ts, [-funding[t] for t in ts]


def _sum(st, a, b):
    """Exactly rounded sum of the rates settled at a <= t < b."""
    ts, r = st
    return math.fsum(r[bisect.bisect_left(ts, a):bisect.bisect_left(ts, b)])


def _rule(bars_by, funding_by, back, decide, weekly=False):
    """{coin: positions}. decide(settled, T, previous position) runs at each 01:00 UTC T (Mondays if weekly) from the
    coin's first to its last bar once the lookback, which starts `back` seconds before T, lies inside the window (from
    the coin's first bar); before that the position is 0. Each bar holds the latest decision at or before it."""
    out = {}
    for s, bars in bars_by.items():
        st, pos, cur = _settled(funding_by.get(s) or {}), [], 0.0
        if not bars:
            out[s] = pos
            continue
        start, d, dec = bars[0][0], bars[0][0] - bars[0][0] % DAY, []
        while d + DECISION <= bars[-1][0]:
            if not weekly or _monday(d):
                cur = decide(st, d + DECISION, cur) if d + DECISION - back >= start else 0.0
                dec.append((d + DECISION, cur))
            d += DAY
        cur, j = 0.0, 0
        for ts, _, _ in bars:
            while j < len(dec) and dec[j][0] <= ts:
                cur = dec[j][1]
                j += 1
            pos.append(cur)
        out[s] = pos
    return out


def apr(st, T, days):
    """Funding settled in the `days` days before the decision time T, annualised (x 365 / days)."""
    return _sum(st, T - days * DAY, T) * 365 / days


def carry_filter(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Daily 01:00 UTC: hold +1 iff APR_L >= enter_apr."""
    L = p["lookback_days"]
    return _rule(bars_by, funding_by, L * DAY, lambda st, T, cur: float(apr(st, T, L) >= p["enter_apr"] - EPS))


def carry_filter_weekly(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """The same rule decided only on Mondays 01:00 UTC (successor filt_w)."""
    L = p["lookback_days"]
    return _rule(bars_by, funding_by, L * DAY, lambda st, T, cur: float(apr(st, T, L) >= p["enter_apr"] - EPS),
                 weekly=True)


def carry_hysteresis(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Daily 01:00 UTC: enter +1 at APR_L >= 0.219, exit to 0 at APR_L < exit_apr, otherwise keep the position."""
    L = p["lookback_days"]

    def decide(st, T, cur):
        a = apr(st, T, L)
        return 1.0 if a >= HYST_ENTER_APR - EPS else (0.0 if a < p["exit_apr"] - EPS else cur)
    return _rule(bars_by, funding_by, L * DAY, decide)


def carry_floor(bars_by, funding_by, p, fit=None, volume_by=None, extra=None):
    """Mondays 01:00 UTC: share = fraction of the last `days` completed UTC days whose summed settled funding is at
    least the interest floor (0.0003 per day); hold +1 for the week iff share >= q."""
    n = p["days"]

    def decide(st, T, cur):
        d0 = T - DECISION
        share = sum(_sum(st, d0 - k * DAY, d0 - (k - 1) * DAY) >= FLOOR_DAY - EPS for k in range(1, n + 1)) / n
        return float(share >= p["q"] - EPS)
    return _rule(bars_by, funding_by, n * DAY + DECISION, decide, weekly=True)


def attribution(m):
    """The family file's attribution rule on portfolio metrics (lab/engine/backtest.metrics): funding income - (fees +
    spread + slippage) > 0 AND gross ratio P&L <= funding income. The metrics book funding as a cost, so income is
    minus their funding."""
    income = -(m.get("funding") or 0.0)
    costs = (m.get("fees") or 0.0) + (m.get("spread") or 0.0) + (m.get("slippage") or 0.0)
    gross = m.get("gross_total") or 0.0
    return {"cash_flow": "funding_income", "funding_income": income, "costs": costs, "gross_ratio_pnl": gross,
            "cash_flow_minus_costs": income - costs,
            "gates": {"funding income - costs > 0": income - costs > 0,
                      "gross ratio P&L <= funding income": gross <= income}}
