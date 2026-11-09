"""Director order 78: pure classification of a ledger's close and of its records after the last verified mark.

No database, no network, no clock, no state. The caller passes numbers it read; nothing is written, repaired or
recomputed from market data. Read research/desk/PARTIAL_CLOSE_78.md for why each class exists.

Close status (classify_close), fail-closed:
  NO_POSITION       no leg was open before the close.
  CLOSE_SUCCESS     every leg that was open is flat, its reduce-only fills account for the whole position, and an equity
                    mark exists at or after the last close fill. The only status that means "closed".
  PARTIAL_CLOSE     at least one leg was reduced or closed and at least one leg is still open.
  CLOSE_INCOMPLETE  anything else: no leg was reduced, the legs are flat but the final mark is missing, or the inputs do
                    not account for the positions.

Record classes (classify_record) never say "invalid": a funding row after the last mark can be a correctly recorded
simulated event even though equity cannot be computed at that time.
"""
import math

NO_POSITION = "NO_POSITION"
CLOSE_SUCCESS = "CLOSE_SUCCESS"
PARTIAL_CLOSE = "PARTIAL_CLOSE"
CLOSE_INCOMPLETE = "CLOSE_INCOMPLETE"
CLOSE_STATUSES = (NO_POSITION, CLOSE_SUCCESS, PARTIAL_CLOSE, CLOSE_INCOMPLETE)

LEG_CLOSED, LEG_REDUCED, LEG_OPEN, LEG_INCONSISTENT = "CLOSED", "REDUCED", "OPEN", "INCONSISTENT"

VERIFIED_MARK = "VERIFIED_HISTORICAL_MARK"
MARK_AFTER_CUTOFF = "MARK_AFTER_LAST_VERIFIED"
FUNDING_IN_MARK = "FUNDING_UP_TO_LAST_VERIFIED_MARK"
FUNDING_AFTER_MARK = "SIMULATED_FUNDING_AFTER_LAST_MARK"
FILL_IN_MARK = "SIMULATED_FILL_UP_TO_LAST_VERIFIED_MARK"
FILL_AFTER_MARK = "SIMULATED_FILL_AFTER_LAST_MARK"
UNCLASSIFIED = "UNCLASSIFIED"
RECORD_CLASSES = (VERIFIED_MARK, MARK_AFTER_CUTOFF, FUNDING_IN_MARK, FUNDING_AFTER_MARK, FILL_IN_MARK, FILL_AFTER_MARK,
                  UNCLASSIFIED)

MISSING_SPOT_MARK = "MISSING_SPOT_MARK"
EQUITY_COMPUTABLE = "EQUITY_COMPUTABLE"
EQUITY_NOT_COMPUTABLE = "EQUITY_NOT_COMPUTABLE"

QTY_TOL = 1e-9
MARK_MAX_AGE_S = 7200                  # net_report's FRESH limit (research/desk/STALE_EQUITY_59C.md)
SPOT_SUFFIX = ".SPOT"
_HOUR = 3600


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _flat(q, scale=1.0):
    return abs(q) <= QTY_TOL * max(1.0, abs(scale))


def _incomplete(reason, legs=None):
    return {"status": CLOSE_INCOMPLETE, "reason": reason, "legs": legs or {}, "open_legs": [], "success": False}


def _qty_map(m):
    return isinstance(m, dict) and all(isinstance(k, str) and k and _number(v) for k, v in m.items())


def _leg(before, after, closed):
    """(state, reason) of one leg; `closed` is the absolute quantity of its reduce-only close fills."""
    if not _number(after) or not _number(closed) or closed < -QTY_TOL:
        return LEG_INCONSISTENT, "non-numeric quantity"
    if not _flat(after, before) and (after > 0) != (before > 0):
        return LEG_INCONSISTENT, "the position changed sign"
    if abs(after) > abs(before) + QTY_TOL * max(1.0, abs(before)):
        return LEG_INCONSISTENT, "the position grew during the close"
    reduced = abs(before) - abs(after)
    if abs(closed - reduced) > QTY_TOL * max(1.0, abs(before)):
        return LEG_INCONSISTENT, "close fills do not account for the change in position"
    if _flat(after, before):
        return LEG_CLOSED, None
    return (LEG_REDUCED if reduced > QTY_TOL * max(1.0, abs(before)) else LEG_OPEN), None


def classify_close(before, after, closed=None, last_fill_ts=None, last_mark_ts=None):
    """before / after: {instrument: signed quantity}; closed: {instrument: absolute quantity of reduce-only close fills};
    last_fill_ts: time of the last close fill; last_mark_ts: time of the last equity mark."""
    closed = {} if closed is None else closed
    if not _qty_map(before) or not _qty_map(after) or not _qty_map(closed):
        return _incomplete("malformed input")
    held = {k: v for k, v in before.items() if not _flat(v)}
    extra = sorted(k for k, v in after.items() if k not in held and not _flat(v))
    if extra:
        return _incomplete(f"position in a leg that was not open before: {', '.join(extra)}")
    unknown = sorted(k for k, v in closed.items() if k not in held and not _flat(v))
    if unknown:
        return _incomplete(f"close fills in a leg that was not open before: {', '.join(unknown)}")
    if not held:
        return {"status": NO_POSITION, "reason": None, "legs": {}, "open_legs": [], "success": False}
    legs, why = {}, []
    for inst, q in held.items():
        legs[inst], reason = _leg(q, after.get(inst, 0.0), closed.get(inst, 0.0))
        if reason:
            why.append(f"{inst}: {reason}")
    open_legs = sorted(k for k, s in legs.items() if s != LEG_CLOSED)
    if why:
        out = _incomplete("; ".join(sorted(why)), legs)
        out["open_legs"] = open_legs
        return out
    progressed = any(s in (LEG_CLOSED, LEG_REDUCED) for s in legs.values())
    if open_legs and progressed:
        return {"status": PARTIAL_CLOSE, "reason": "at least one leg is still open", "legs": legs,
                "open_legs": open_legs, "success": False}
    if open_legs:
        return {"status": CLOSE_INCOMPLETE, "reason": "no leg was reduced", "legs": legs, "open_legs": open_legs,
                "success": False}
    if not _number(last_fill_ts) or not _number(last_mark_ts) or last_mark_ts < last_fill_ts:
        return {"status": CLOSE_INCOMPLETE, "reason": "all legs are flat but no equity mark follows the last fill",
                "legs": legs, "open_legs": [], "success": False}
    return {"status": CLOSE_SUCCESS, "reason": None, "legs": legs, "open_legs": [], "success": True}


def classify_record(table, ts, last_verified_mark_ts):
    """The class of one raw row, by its table and time. Never changes or rejects the row."""
    if not _number(ts) or not _number(last_verified_mark_ts):
        return UNCLASSIFIED
    after = ts > last_verified_mark_ts
    if table == "sim_equity":
        return MARK_AFTER_CUTOFF if after else VERIFIED_MARK
    if table == "sim_funding":
        return FUNDING_AFTER_MARK if after else FUNDING_IN_MARK
    if table == "sim_fills":
        return FILL_AFTER_MARK if after else FILL_IN_MARK
    return UNCLASSIFIED


def missing_mark_hours(last_mark_ts, as_of):
    """Clock hours in (last_mark_ts, as_of] without an equity mark, given that none was written after last_mark_ts."""
    if not _number(last_mark_ts) or not _number(as_of) or as_of <= last_mark_ts:
        return 0
    return int(as_of) // _HOUR - int(last_mark_ts) // _HOUR


def equity_view(cash, positions, marks, as_of, max_age_s=MARK_MAX_AGE_S):
    """Current equity only if every open leg has a finite mark no older than max_age_s; otherwise equity is None, never
    a stale value. marks: {instrument: (price, ts)}."""
    if not _number(cash) or not _qty_map(positions) or not isinstance(marks, dict) or not _number(as_of):
        return {"status": EQUITY_NOT_COMPUTABLE, "equity": None, "missing_marks": [], "reason": "malformed input"}
    held = {k: v for k, v in positions.items() if not _flat(v)}
    missing = []
    for inst in held:
        m = marks.get(inst)
        fresh = (isinstance(m, (tuple, list)) and len(m) == 2 and _number(m[0]) and _number(m[1])
                 and 0 <= as_of - m[1] <= max_age_s)
        if not fresh:
            missing.append(inst)
    if missing:
        return {"status": EQUITY_NOT_COMPUTABLE, "equity": None, "missing_marks": sorted(missing),
                "reason": "no fresh mark for every open leg"}
    return {"status": EQUITY_COMPUTABLE, "equity": cash + sum(q * marks[i][0] for i, q in held.items()),
            "missing_marks": [], "reason": None}


def ledger_view(records, last_verified_mark_ts, cash, positions, marks, as_of, close=None):
    """One account in the terms of order 78. records: iterable of (table, ts). Counts only; the rows are not kept, changed
    or rejected, and `current_pnl_available` is False unless equity is computable."""
    counts = {c: 0 for c in RECORD_CLASSES}
    for table, ts in records:
        counts[classify_record(table, ts, last_verified_mark_ts)] += 1
    eq = equity_view(cash, positions, marks, as_of)
    open_spot = sorted(i for i, q in positions.items() if i.endswith(SPOT_SUFFIX) and not _flat(q)) \
        if _qty_map(positions) else []
    spot_gap = bool(open_spot) and any(i in eq["missing_marks"] for i in open_spot)
    return {"counts": counts, "last_verified_mark_ts": last_verified_mark_ts, "equity": eq,
            "current_pnl_available": eq["status"] == EQUITY_COMPUTABLE,
            "missing_spot_mark": {"class": MISSING_SPOT_MARK, "legs": open_spot,
                                  "hours": missing_mark_hours(last_verified_mark_ts, as_of)} if spot_gap else None,
            "close": close}
