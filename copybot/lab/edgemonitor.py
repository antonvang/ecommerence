"""PROTOCOL_V3 amendment 21w: edge-decay monitor per paper ledger with adopted thresholds. Read-only from the register
(sim_equity, sim_fills, sim_orders, lane.decomposition); no new data, no lifecycle change, no automatic action.
"""
from __future__ import annotations

import collections
import json
import math
import statistics
import time

from lab import lane

DAY, WINDOW_DAYS = 86400, 28
INSUFFICIENT, STABLE, SUSPECT, UNSUPPORTED = ("utilstrækkelige data", "stabil", "forringelse mistænkt",
                                              "fordel ikke længere støttet")
NOT_APPLICABLE = "ikke anvendelig"                        # 21w precision 1: M2 for LANE_ ledgers
RANK = {NOT_APPLICABLE: -1, INSUFFICIENT: 0, STABLE: 1, SUSPECT: 2, UNSUPPORTED: 3}
RULE = "research/PROTOCOL_V3.md amendment 21w"
HOLM_NOTE = ("M1 er den eneste test; Holm pr. konto er derfor p selv. Ingen korrektion på tværs af konti, "
             "da statussen ikke udløser nogen handling")


def _betacf(a, b, x):
    """Continued fraction of the regularized incomplete beta (Numerical Recipes 6.4)."""
    qab, qap, qam, c, d = a + b, a + 1, a - 1, 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1 + aa * d
            d = 1 / (d if abs(d) > 1e-300 else 1e-300)
            c = 1 + aa / c
            c = c if abs(c) > 1e-300 else 1e-300
            h *= d * c
        if abs(d * c - 1) < 1e-12:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    """P(T <= t) for Student's t with `df` degrees of freedom."""
    tail = 0.5 * _ibeta(df / 2, 0.5, df / (df + t * t))
    return tail if t < 0 else 1 - tail


def _day(ts):
    return int(ts) // DAY * DAY


def daily_net(db, ledger, now):
    """Net per closed UTC day: last equity of the day minus the last of the day before (first day: the first mark)."""
    rows = db.q("SELECT ts, equity FROM sim_equity WHERE exp_id=? AND ts<=? ORDER BY ts, id", ledger, now)
    if not rows:
        return []
    last = collections.OrderedDict()
    for r in rows:
        last[_day(r["ts"])] = r["equity"]
    prev, out = rows[0]["equity"], []
    for d, eq in last.items():
        if d + DAY > now + 1:                     # a day is closed at its last second (as-of history)
            break
        out.append((d, eq - prev))
        prev = eq
    return out


def _status(value, n, need, suspect, unsupported):
    if n < need or value is None:
        return INSUFFICIENT
    return UNSUPPORTED if unsupported(value) else SUSPECT if suspect(value) else STABLE


def ledger(db, led, now, asof=False):
    """Every measure as of `now` (all reads ts <= now). With asof=True M3 is skipped: lane.decomposition is not as-of
    (LINUX_DRIFT 2026-10-24 23:11)."""
    days = daily_net(db, led, now)[-WINDOW_DAYS:]
    since = now - WINDOW_DAYS * DAY
    out = {}
    # M1 net expectation
    nets = [v for _, v in days]
    if len(nets) >= 2 and statistics.pstdev(nets) > 0:
        m, sd = statistics.mean(nets), statistics.stdev(nets)
        t = m / (sd / math.sqrt(len(nets)))
        p = t_cdf(t, len(nets) - 1)
    else:
        m, t, p = (statistics.mean(nets) if nets else None), None, None
    st = INSUFFICIENT if len(nets) < 14 or m is None else \
        UNSUPPORTED if p is not None and p < 0.05 else SUSPECT if m < 0 else STABLE
    out["M1"] = {"name": "nettoforventning", "n_days": len(nets), "mean_usd": m, "t": t, "p_one_sided": p,
                 "p_holm": p, "need": "≥ 14 døgn", "status": st}
    # M2 execution: realized vs modelled slippage, taker fills in the window
    fills = db.q("SELECT f.slippage, f.ts, f.book_ts, o.cost_model FROM sim_fills f JOIN sim_orders o "
                 "ON o.order_id=f.order_id WHERE f.exp_id=? AND f.ts>=? AND f.ts<=? AND f.liquidity='taker'", led, since, now)
    real, model = [], []
    for f in fills:
        cm = json.loads(f["cost_model"]) if f["cost_model"] else None
        if f["slippage"] is None or not cm or "expected_spread" not in cm:
            continue
        real.append(f["slippage"])
        model.append(cm["expected_spread"] / 2 + cm.get("extra_slippage", 0.0))
    r = (statistics.mean(real) / statistics.mean(model)) if real and statistics.mean(model) > 0 else None
    out["M2"] = {"name": "udførelse (realiseret/modelleret slippage)", "n_fills": len(real), "ratio": r,
                 "realized_mean": statistics.mean(real) if real else None,
                 "modelled_mean": statistics.mean(model) if model else None, "need": "≥ 30 fills",
                 "status": NOT_APPLICABLE if led.startswith("LANE_") else
                 _status(r, len(real), 30, lambda v: v > 1.25, lambda v: v > 2.0)}
    # M3 cost per gross edge, whole ledger (now only)
    dec = None if asof else lane.decomposition(db, led)
    gross = abs(dec["price_basis"]) if dec else None
    cost = -(dec["fees"] + dec["spread_slippage"]) if dec else None
    c = cost / gross if dec and gross > 0 else None
    n_all = len(daily_net(db, led, now))
    out["M3"] = {"name": "omkostning pr. bruttokant", "n_days": n_all, "ratio": c, "cost_usd": cost,
                 "gross_usd": gross, "need": "≥ 28 døgn",
                 "status": INSUFFICIENT if asof else _status(c, n_all, 28, lambda v: v >= 0.5, lambda v: v >= 1.0),
                 "asof": "kun nu" if asof else None}
    # M4 book age at fill
    ages = sorted(f["ts"] - f["book_ts"] for f in fills if f["book_ts"] is not None)
    p95 = ages[min(len(ages) - 1, math.ceil(0.95 * len(ages)) - 1)] if ages else None
    out["M4"] = {"name": "bogens alder ved fill (p95, s; ned til -1 s = under 1 s pga. hele sekunder)", "n_fills": len(ages), "p95_s": p95, "need": "≥ 30 fills",
                 "status": _status(p95, len(ages), 30, lambda v: v > 30, lambda v: v > 60)}
    # M5 concentration: share of the net from the 3 best days, only when the net is positive
    total = sum(nets)
    share = (sum(sorted(nets, reverse=True)[:3]) / total) if total > 0 else None
    out["M5"] = {"name": "koncentration (3 bedste døgn / netto)", "n_days": len(nets), "share": share,
                 "need": "≥ 28 døgn og netto > 0",
                 "status": _status(share, len(nets), 28, lambda v: v >= 0.75, lambda v: v >= 1.0)}
    # descriptive only
    orders = db.q("SELECT ts, signal_ref FROM sim_orders WHERE exp_id=? AND ts>=? AND ts<=?", led, since, now)
    lags = sorted(o["ts"] - int(o["signal_ref"].rsplit("@", 1)[1]) for o in orders
                  if o["signal_ref"] and "@" in o["signal_ref"] and o["signal_ref"].rsplit("@", 1)[1].isdigit())
    fund = db.one("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=? AND ts>=? AND ts<=?", led, since,
                  now)[0]
    status = max((x["status"] for x in out.values()), key=RANK.get)
    if status == STABLE and out["M1"]["status"] == INSUFFICIENT:            # 21w precision 2
        status = INSUFFICIENT
    flagged = [k for k, x in out.items() if x["status"] in (SUSPECT, UNSUPPORTED)]
    return {"ledger": led, "status": status, "flagged_by": flagged, "measures": out,
            "descriptive": {"funding_usd_window": fund, "funding_per_day": fund / len(nets) if nets else None,
                            "signal_lag_median_s": lags[len(lags) // 2] if lags else None, "n_orders": len(orders)}}


HISTORY_DAYS = 14
_HIST = {}                                       # (ledger, as-of) -> row: a closed day's reconstruction never changes


def history(db, led, now, days=HISTORY_DAYS):
    """The monitor as of the end of each of the last `days` closed UTC days, oldest first (LINUX_DRIFT 23:11)."""
    out = []
    for k in range(days, 0, -1):
        asof = (int(now) // DAY - k + 1) * DAY - 1
        key = (led, asof)
        if key not in _HIST:
            r = ledger(db, led, asof, asof=True)
            _HIST[key] = {"asof": asof, "status": r["status"], "flagged_by": r["flagged_by"],
                          "measures": {m: {k2: x.get(k2) for k2 in ("status", "n_days", "n_fills", "mean_usd",
                                                                    "p_one_sided", "ratio", "p95_s", "share")}
                                       for m, x in r["measures"].items()}}
        out.append(_HIST[key])
    return out


def view(db, now=None):
    now = now or time.time()
    leds = [r[0] for r in db.q("SELECT DISTINCT exp_id FROM sim_equity ORDER BY exp_id")]
    rows = [dict(ledger(db, led, now), history=history(db, led, now)) for led in leds]
    return {"rule": RULE, "now": now, "ledgers": rows,
            "by_status": dict(collections.Counter(r["status"] for r in rows)), "holm": HOLM_NOTE,
            "action": "ingen: monitoren skifter ingen tilstand og stopper intet (21w)",
            "history_note": f"as-of ved slutningen af hvert af de seneste {HISTORY_DAYS} afsluttede UTC-døgn; "
                            "M3 kun nu (opdelingen er ikke as-of)"}
