"""PROTOCOL_V3 amendment 27: a diagnostic 500-level book measurement after a 12g thin-book rejection.

After a scanner account's `lane.skipped` says "a book is too thin for the account's size (12g)", each leg's public book
is read once more with 500 levels and stored in `observations` (detector depth500/1): depth, spread, mid and the
VWAP distance for the quantity the decision used, within 20 and within 500 levels. A side that cannot fill the
quantity is censored (null), never 0 and never estimated. This is diagnostics only: nothing in 12g, amendment 25, the
paper engine, R1, K3 or pm_lp reads it, and it never changes a decision, starts a lane or simulates a fill. One
measurement per event and leg; a failed read is one error row and never retried.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.parse

DET, RULE = "depth500/1", "research/PROTOCOL_V3.md amendment 27"
TRIGGER = "a book is too thin for the account's size (12g)"
LEVELS, PAPER_LEVELS = 500, 20
SPOT_SUFFIX = ".SPOT"
LABEL = "diagnostik: ikke en afgørelse, ikke en fill; papirmotoren og 12g bruger kun 20 niveauer"


def url(inst):
    """The same hosts the paper engine reads its 20-level books from (paper_runner.fetch_book), with 500 levels."""
    from lab.paper_runner import SPOT_REST
    if inst.endswith(SPOT_SUFFIX):
        return f"{SPOT_REST}/api/v3/depth?symbol={urllib.parse.quote(inst[:-len(SPOT_SUFFIX)], safe='')}&limit={LEVELS}"
    return f"/fapi/v1/depth?symbol={urllib.parse.quote(inst, safe='')}&limit={LEVELS}"


def walk(levels, qty):
    """Mean fill price of `qty` walked through [(price, size)], or None when the levels cannot fill it."""
    rest, cost = qty, 0.0
    for px, size in levels:
        q = min(rest, size)
        cost += q * px
        rest -= q
        if rest <= 1e-12:
            return cost / qty
    return None


def measure(d, qty):
    """The payload fields of one 500-level book for `qty`; raises ValueError for an empty or crossed book."""
    bids = [(float(p), float(q)) for p, q in d.get("bids") or []]
    asks = [(float(p), float(q)) for p, q in d.get("asks") or []]
    if not bids or not asks or bids[0][0] >= asks[0][0]:
        raise ValueError("empty or crossed book")
    mid = (bids[0][0] + asks[0][0]) / 2
    out = {"levels": [len(bids), len(asks)], "mid": mid, "spread": (asks[0][0] - bids[0][0]) / mid}
    for n in (PAPER_LEVELS, LEVELS):
        b, a = bids[:n], asks[:n]
        buy, sell = walk(a, qty), walk(b, qty)
        out[f"depth_bid_usd_{n}"] = sum(p * q for p, q in b)
        out[f"depth_ask_usd_{n}"] = sum(p * q for p, q in a)
        out[f"buy_vwap_distance_{n}"] = None if buy is None else buy / mid - 1
        out[f"sell_vwap_distance_{n}"] = None if sell is None else 1 - sell / mid
        out[f"censored_{n}"] = {"buy": buy is None, "sell": sell is None}
    return out


def _done(db, event_id, key, inst):
    return db.one("SELECT 1 FROM observations WHERE detector=? AND instrument=? AND "
                  "(json_extract(payload, '$.event_id')=? OR json_extract(payload, '$.event_key')=?) LIMIT 1",
                  DET, inst, event_id, key)


def probe(db, event_id, key, trigger, get, clock=time.time):
    """Amendment 27 for one lane.skipped event: one row per leg (thin_probe or error); returns the written ids.
    Writes nothing when the event already has a measurement or the trigger has no execution record."""
    ex = (trigger or {}).get("execution") or {}
    legs = [ex.get(side) for side in ("spot", "perp")]
    qty, size = ex.get("qty"), ex.get("size_usd_per_leg")
    if not qty or any(not (leg or {}).get("instrument") for leg in legs):
        return []
    ids = []
    for leg in legs:
        inst = leg["instrument"]
        if _done(db, event_id, key, inst):
            continue
        base = {"event_id": event_id, "event_key": key, "rule": "12g", "size_usd": size, "qty": qty,
                "decision_book_fetched_at": leg.get("fetched_at"), "label": LABEL, "amendment": RULE}
        try:
            d = get(url(inst))
            at = clock()                                        # wall clock at the read (as 12h's skew)
            m = measure(d, qty)
        except urllib.error.HTTPError as e:
            ids.append(_error(db, inst, base, f"HTTP {e.code}", e.code, clock))
            continue
        except Exception as e:                              # noqa: BLE001 - recorded once, never retried
            ids.append(_error(db, inst, base, repr(e)[:200], None, clock))
            continue
        dec = base["decision_book_fetched_at"]
        b5, s5 = m["buy_vwap_distance_500"], m["sell_vwap_distance_500"]
        ids.append(db.append("observations", ts=int(at), detector=DET, source=url(inst), instrument=inst,
                             metric="thin_probe", value=None if b5 is None or s5 is None else b5 + s5,
                             threshold=None, flagged=0,
                             payload={**base, **m, "fetched_at": at,
                                      "age_vs_decision_book_s": None if dec is None else at - dec,
                                      "lastUpdateId": d.get("lastUpdateId"), "E": d.get("E"), "T": d.get("T")}))
    return ids


def _error(db, inst, base, why, code, clock):
    return db.append("observations", ts=int(clock()), detector=DET, source=url(inst),
                     instrument=inst, metric="error", value=None, threshold=None, flagged=0,
                     payload={**base, "error": why, "http_status": code})


def wanted(reason):
    return TRIGGER in (reason or "")

