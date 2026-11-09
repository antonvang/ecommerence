"""Mark provenance prototype (director order 67 P2, finding #10). NOT WIRED IN: nothing in the lab calls it, and the
production schema is unchanged.

sim_equity stores equity, cash and gross exposure, but not the price each open position was marked at, so the
unrealized part of a two-leg book cannot be recomputed from the database alone. The design (research/desk/
PAPER_ENGINE_REMEDIATION_67.md, P2 #10) is one append-only row per instrument and mark, hash-chained like every
sim_* table, written in the same transaction as the sim_equity row:

    sim_marks(exp_id, ts, equity_id, instrument, qty, mark_px, bid, ask, book_ts, book_observed, source)

Until a dated approval adds that table, this module only builds and checks such rows in memory (and the tests use it
on synthetic data). A ledger's rows at one mark must reproduce its equity row: cash + sum(qty * mark_px) = equity and
sum(|qty| * mark_px) = exposure.
"""
from __future__ import annotations

COLUMNS = ("exp_id", "ts", "equity_id", "instrument", "qty", "mark_px", "bid", "ask", "book_ts", "book_observed",
           "source")
TOL = 1e-6


def rows(exp_id, ts, positions, marks, books=None, equity_id=None, source="book_mid"):
    """The provenance rows of one mark: positions {instrument: qty}, marks {instrument: price}, books {instrument:
    Book} (optional: best bid/ask and both book times)."""
    out = []
    for inst, qty in sorted(positions.items()):
        b = (books or {}).get(inst)
        out.append({"exp_id": exp_id, "ts": int(ts), "equity_id": equity_id, "instrument": inst, "qty": qty,
                    "mark_px": marks[inst], "bid": b.bids[0][0] if b and b.bids else None,
                    "ask": b.asks[0][0] if b and b.asks else None, "book_ts": getattr(b, "ts", None),
                    "book_observed": getattr(b, "observed", None), "source": source})
    return out


def check(prov, equity_row):
    """Problems (empty = consistent) between one mark's provenance rows and its sim_equity row."""
    problems = []
    value = sum(r["qty"] * r["mark_px"] for r in prov)
    gross = sum(abs(r["qty"]) * r["mark_px"] for r in prov)
    if abs(equity_row["cash"] + value - equity_row["equity"]) > TOL * max(1.0, abs(equity_row["equity"])):
        problems.append(f"cash {equity_row['cash']} + marked value {value} != equity {equity_row['equity']}")
    if abs(gross - equity_row["exposure"]) > TOL * max(1.0, gross):
        problems.append(f"gross {gross} != exposure {equity_row['exposure']}")
    for r in prov:
        if r["bid"] is not None and r["ask"] is not None and r["source"] == "book_mid" \
                and abs(r["mark_px"] - (r["bid"] + r["ask"]) / 2) > TOL * r["mark_px"]:
            problems.append(f"{r['instrument']}: mark {r['mark_px']} is not the book mid")
    return problems
