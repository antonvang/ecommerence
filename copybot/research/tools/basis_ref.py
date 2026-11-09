"""Reference per-instrument round trips with the basis reset on a flip through zero (director order 67 P1, finding #7).

research/tools/net_report.py is pinned (NET_REPORT e8cac57c) and keeps the old basis when a fill flips a position
from long to short (or back): its realized price P&L, closed round trips, direction and open basis are then wrong for
that instrument. This helper is the corrected reference, kept apart from the pinned report and never called by it: the
part of a fill that closes the old position realizes against the old basis and ends a round trip; the excess opens the
new position at the fill price (the engine's rule, lab/paper.py PaperEngine.ledger). It changes no report.

    python3 research/tools/basis_ref.py --db PATH [--cutoff EPOCH]     # read-only comparison with net_report
"""
import argparse
import collections
import importlib.util
import json
import os
import sqlite3

EPS = 1e-12


def instruments(fills):
    """fills: (ts, order_id, instrument, side, px, qty, fee, mid) rows in id order (net_report's query). Returns
    {instrument: {direction_last, round_trips, realized_price_pnl, fees, open_qty, open_basis, open_since, flips}}."""
    st = collections.defaultdict(lambda: {"pos": 0.0, "basis": 0.0, "round_trips": 0, "realized": 0.0, "fees": 0.0,
                                          "direction": None, "open_since": None, "flips": 0})
    for ts, _oid, sym, side, px, q, fee, _mid in fills:
        s, sg = st[sym], (1 if side == "buy" else -1)
        s["fees"] += fee
        p0 = s["pos"]
        if p0 == 0 or (p0 > 0) == (sg > 0):                    # opening or adding
            if p0 == 0:
                s["direction"], s["open_since"] = ("long" if sg > 0 else "short"), ts
            s["basis"] = (s["basis"] * abs(p0) + px * q) / (abs(p0) + q)
            s["pos"] = p0 + sg * q
            continue
        closed = min(q, abs(p0))                               # reducing, closing or flipping
        s["realized"] += closed * (px - s["basis"]) * (1 if p0 > 0 else -1)
        s["pos"] = p0 + sg * q
        if abs(s["pos"]) < EPS:
            s["pos"], s["round_trips"] = 0.0, s["round_trips"] + 1
        elif (s["pos"] > 0) != (p0 > 0):                       # flipped: the old trip ends, the excess opens anew
            s["round_trips"] += 1
            s["flips"] += 1
            s["basis"], s["direction"], s["open_since"] = px, ("long" if s["pos"] > 0 else "short"), ts
    return {sym: {"direction_last": s["direction"], "round_trips": s["round_trips"],
                  "realized_price_pnl": s["realized"], "fees": s["fees"], "open_qty": s["pos"],
                  "open_basis": s["basis"] if s["pos"] else None, "open_since": s["open_since"] if s["pos"] else None,
                  "flips": s["flips"]} for sym, s in st.items()}


def _net_report():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("net_report_ref", os.path.join(here, "net_report.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def compare(con, cutoff=None):
    """Every ledger with fills: net_report's per-instrument numbers vs the reference (read-only)."""
    nr, lim, out = _net_report(), (2 ** 62 if cutoff is None else cutoff), []
    started = {}
    for ts, led, p in con.execute("SELECT ts, exp_id, payload FROM events WHERE kind='lane.started' ORDER BY id"):
        started[led] = json.loads(p)
    gone = {e for (e,) in con.execute("SELECT exp_id FROM events WHERE kind='lane.retired'")}   # as net_report.build
    for (led,) in con.execute("SELECT DISTINCT exp_id FROM sim_fills ORDER BY exp_id").fetchall():
        fills = con.execute("SELECT ts, order_id, instrument, side, px, qty, fee, mid FROM sim_fills WHERE exp_id=? "
                            "AND ts<=? ORDER BY id", (led, lim)).fetchall()
        ref = instruments(fills)
        old = nr.account(con, led, started.get(led, {}), lim)["instruments"]
        for sym, r in ref.items():
            o = old.get(sym, {})
            diff = {k: (o.get(k), r[k]) for k in ("direction_last", "round_trips", "realized_price_pnl", "open_basis")
                    if (o.get(k) != r[k]) and not (isinstance(r[k], float) and o.get(k) is not None
                                                   and abs(o[k] - r[k]) < 1e-9)}
            if diff:
                out.append({"ledger": led, "instrument": sym, "flips": r["flips"], "diff": diff,
                            "in_net_report": led in started and (led not in gone or started[led].get("source") in
                                                                 ("straks", "carry90", "pairs"))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--cutoff", type=int)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    rows = compare(con, a.cutoff)
    print(json.dumps(rows, indent=1, sort_keys=True))
    print(f"instruments that differ: {len(rows)}")


if __name__ == "__main__":
    main()
