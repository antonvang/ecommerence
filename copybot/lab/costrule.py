"""PROTOCOL_V3 amendment 21m point 2: option C for future screenings, with amendment 21l point 2's formula unchanged.

For a market with 24 h volume >= 100 M USD at the event (24 x the median hourly quote volume over the 720 h before) and
an R1 measurement with "enough data" (amendment 21l point 1): c = max(2 * 2 * fee, 2 * (2 * fee + q95)), q95 = the 95 %
quantile of the observed book_rt in move hours. Otherwise amendment 21i's rule (B) applies. In explore0 this assumes the
2026 quantile holds for 2020-21; every report using it must say so.
"""
from __future__ import annotations

import statistics

from lab import costreport, m21iscreen

LIQUID_USD, HOUR = 1e8, 3600
ASSUMPTION = "option C (21m): the 2026 observed move-hour q95 of the book is assumed to hold for 2020-21"


def observed_q95(q):
    """{market: q95 of move-hour book_rt} for markets whose R1 conclusion is 'enough data'; empty until then."""
    rep, rs = costreport.report(q), costreport.rows(q)
    out = {}
    for sym, m in rep["markets"].items():
        if m["conclusion"] != "enough data":
            continue
        vals = sorted(r["rt"] for r in rs if r["market"] == sym and r["rt"] is not None and
                      (r["flagged"] or (r["z"] is not None and abs(r["z"]) >= costreport.MOVE_Z)))
        if len(vals) >= costreport.MIN_MOVE:
            out[sym] = statistics.quantiles(vals, n=20)[-1]
    return out


def v24(vol, h):
    hrs = [vol[t] for t in range(h - 720 * HOUR, h, HOUR) if t in vol]
    return 24 * statistics.median(hrs) if len(hrs) >= 600 else None


def hurdle(sym, vol, h, q95):
    """(c, rule) for an event of `sym` at h; q95 from observed_q95 (empty -> B everywhere)."""
    v = v24(vol, h)
    if sym in q95 and v is not None and v >= LIQUID_USD:
        fee = m21iscreen.FEE
        return max(4 * fee, 2 * (2 * fee + q95[sym])), "C"
    return m21iscreen.cost(vol, h), "B"
