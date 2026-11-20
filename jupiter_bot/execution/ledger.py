"""execution.db: append-only, self-identifying ledger of orders, fills and events.

Every table refuses UPDATE and DELETE (triggers). An order's state is its most
recent `order_events` row; transitions are checked here. The intent is written
before anything is sent; the signed bytes and signature before `/execute`.
"""
from __future__ import annotations

import json
import time
import uuid
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

from .. import storage
from ..core import Rejected, canonical

APPLICATION_ID = 0x4A424558  # "JBEX"
SCHEMA_VERSION = 1

INTENT, VERIFIED, SIGNED, SUBMITTED = "INTENT", "VERIFIED", "SIGNED", "SUBMITTED"
CONFIRMED, FAILED, EXPIRED, UNKNOWN = "CONFIRMED", "FAILED", "EXPIRED", "UNKNOWN"
TERMINAL = (CONFIRMED, FAILED, EXPIRED)
PENDING = (INTENT, VERIFIED, SIGNED, SUBMITTED)
TRANSITIONS = {
    INTENT: (VERIFIED, FAILED),
    VERIFIED: (SIGNED, FAILED),
    SIGNED: (SUBMITTED, UNKNOWN, FAILED),     # FAILED only when known not sent (same process)
    SUBMITTED: (CONFIRMED, FAILED, EXPIRED, UNKNOWN),
    UNKNOWN: (CONFIRMED, FAILED, EXPIRED),
}

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS orders(
         order_id TEXT PRIMARY KEY, created_at REAL NOT NULL, side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
         input_mint TEXT NOT NULL, output_mint TEXT NOT NULL, in_amount INTEGER NOT NULL CHECK(in_amount > 0),
         mandate_sha256 TEXT NOT NULL, decision TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS order_events(
         id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL REFERENCES orders(order_id),
         at REAL NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS fills(
         order_id TEXT PRIMARY KEY REFERENCES orders(order_id), at REAL NOT NULL, utc_day TEXT NOT NULL,
         kind TEXT NOT NULL CHECK(kind IN ('SWAP','FEE_ONLY')), side TEXT NOT NULL,
         sol_delta INTEGER NOT NULL, usdc_delta INTEGER NOT NULL, fee_lamports INTEGER NOT NULL,
         realized_pnl_usdc INTEGER NOT NULL, position_sol_after INTEGER NOT NULL,
         cost_basis_usdc_after INTEGER NOT NULL, slot INTEGER, signature TEXT NOT NULL, data TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS dry_runs(
         id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, mandate_sha256 TEXT NOT NULL,
         ok INTEGER NOT NULL CHECK(ok IN (0,1)), data TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS events(
         id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS order_events_by_order ON order_events(order_id, id)",
]
for _table in ("orders", "order_events", "fills", "dry_runs", "events"):
    for _event in ("UPDATE", "DELETE"):
        SCHEMA.append("""CREATE TRIGGER IF NOT EXISTS %s_no_%s BEFORE %s ON %s
                         BEGIN SELECT RAISE(ABORT, 'append-only ledger'); END""" % (
            _table, _event.lower(), _event, _table))


def utc_day(at):
    return time.strftime("%Y-%m-%d", time.gmtime(at))


def _json(data):
    return canonical(data if data is not None else {})


class Ledger:
    def __init__(self, path, readonly=False):
        self.readonly = readonly
        if not readonly:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = storage.connect(path, readonly)
        try:
            if readonly:
                storage.is_marked(self.db, APPLICATION_ID, SCHEMA_VERSION, True, "execution")
            else:
                storage.initialise(self.db, APPLICATION_ID, SCHEMA_VERSION, SCHEMA, "execution")
        except Exception:
            self.db.close()
            raise

    @classmethod
    def open_readonly_if_exists(cls, path):
        return cls(path, readonly=True) if Path(path).is_file() else None

    def close(self):
        self.db.close()

    def _write(self, work):
        if self.readonly:
            raise Rejected("Read-only ledger")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            result = work()
            self.db.execute("COMMIT")
            return result
        except Exception:
            storage.rollback(self.db)
            raise

    # events -----------------------------------------------------------------------

    def event(self, kind, data, at):
        self._write(lambda: self.db.execute("INSERT INTO events(at, kind, data) VALUES (?,?,?)",
                                            (at, kind, _json(data))))

    def events(self, kind=None):
        sql, args = "SELECT * FROM events", ()
        if kind:
            sql, args = sql + " WHERE kind=?", (kind,)
        return [dict(row, data=json.loads(row["data"])) for row in self.db.execute(sql + " ORDER BY id", args)]

    # orders -----------------------------------------------------------------------

    def state_of(self, order_id):
        row = self.db.execute("SELECT state FROM order_events WHERE order_id=? ORDER BY id DESC LIMIT 1",
                              (order_id,)).fetchone()
        return row["state"] if row else None

    def non_terminal(self):
        rows = self.db.execute(
            """SELECT o.*, (SELECT state FROM order_events e WHERE e.order_id=o.order_id ORDER BY id DESC LIMIT 1)
               AS state FROM orders o ORDER BY o.rowid""").fetchall()
        return [dict(row) for row in rows if row["state"] not in TERMINAL]

    def create_intent(self, side, input_mint, output_mint, in_amount, mandate_sha, decision, at):
        order_id = uuid.uuid4().hex

        def work():
            open_orders = [o for o in self.non_terminal()]
            if open_orders:
                raise Rejected("An order is still open (%s); no new order" % open_orders[0]["order_id"])
            self.db.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
                            (order_id, at, side, input_mint, output_mint, in_amount, mandate_sha,
                             _json(decision)))
            self.db.execute("INSERT INTO order_events(order_id, at, state, data) VALUES (?,?,?,?)",
                            (order_id, at, INTENT, _json({})))
        self._write(work)
        return order_id

    def _transition(self, order_id, state, data, at):
        current = self.state_of(order_id)
        if current is None:
            raise Rejected("Unknown order")
        if state not in TRANSITIONS.get(current, ()):
            raise Rejected("Illegal transition %s -> %s" % (current, state))
        self.db.execute("INSERT INTO order_events(order_id, at, state, data) VALUES (?,?,?,?)",
                        (order_id, at, state, _json(data)))

    def transition(self, order_id, state, data, at):
        self._write(lambda: self._transition(order_id, state, data, at))

    def order(self, order_id):
        row = self.db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if row is None:
            return None
        result = dict(row, decision=json.loads(row["decision"]))
        result["events"] = [dict(e, data=json.loads(e["data"])) for e in self.db.execute(
            "SELECT * FROM order_events WHERE order_id=? ORDER BY id", (order_id,))]
        result["state"] = result["events"][-1]["state"]
        merged = {}
        for e in result["events"]:
            merged.update(e["data"])
        result["facts"] = merged
        return result

    def counts(self):
        counts = {"total": 0, "pending": 0, "confirmed": 0, "failed": 0, "unknown": 0}
        rows = self.db.execute(
            """SELECT (SELECT state FROM order_events e WHERE e.order_id=o.order_id ORDER BY id DESC LIMIT 1)
               AS state FROM orders o""").fetchall()
        for row in rows:
            counts["total"] += 1
            state = row["state"]
            if state in PENDING:
                counts["pending"] += 1
            elif state == CONFIRMED:
                counts["confirmed"] += 1
            elif state in (FAILED, EXPIRED):
                counts["failed"] += 1
            elif state == UNKNOWN:
                counts["unknown"] += 1
        return counts

    # fills and P&L ---------------------------------------------------------------------

    def position(self):
        # insertion order, never wall-clock order (F10)
        row = self.db.execute("SELECT position_sol_after, cost_basis_usdc_after FROM fills "
                              "ORDER BY rowid DESC LIMIT 1").fetchone()
        return (row[0], row[1]) if row else (0, 0)

    def realized_on(self, day):
        row = self.db.execute("SELECT COALESCE(SUM(realized_pnl_usdc),0) FROM fills WHERE utc_day=?",
                              (day,)).fetchone()
        return row[0]

    def book_fill(self, order_id, at, kind, side, sol_delta, usdc_delta, fee_lamports, slot, signature,
                  price_usdc_per_sol, data, state, state_data):
        """Append a fill and the order's terminal state in ONE transaction.

        Realised P&L uses average cost. Returns the realised USDC atoms."""
        def work():
            position, cost = self.position()
            if kind == "FEE_ONLY":
                # fee paid from the SOL reserve, valued at the decision price; position unchanged
                cost_atoms = Decimal(fee_lamports) * Decimal(price_usdc_per_sol) / 1000
                realized = int((-cost_atoms).to_integral_value(ROUND_FLOOR))   # round the loss up
                new_position, new_cost = position, cost
            elif side == "BUY":
                realized = 0
                new_position, new_cost = position + max(sol_delta, 0), cost + max(-usdc_delta, 0)
            else:
                spent = max(-sol_delta, 0)
                sold = min(spent, position)
                removed = cost * sold // position if position else 0
                realized = usdc_delta - removed
                # SOL spent beyond the position (fees on a full sell) is a cost too (F14)
                excess = Decimal(spent - sold) * Decimal(price_usdc_per_sol) / 1000
                realized -= int(excess.to_integral_value(ROUND_CEILING))
                new_position, new_cost = position - sold, cost - removed
            self.db.execute("INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (order_id, at, utc_day(at), kind, side, sol_delta, usdc_delta, fee_lamports,
                             realized, new_position, new_cost, slot, signature, _json(data)))
            self._transition(order_id, state, state_data, at)
            return realized
        return self._write(work)

    def fills(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM fills ORDER BY rowid")]

    # dry runs ---------------------------------------------------------------------------

    def record_dry_run(self, mandate_sha, ok, data, at):
        self._write(lambda: self.db.execute("INSERT INTO dry_runs(at, mandate_sha256, ok, data) VALUES (?,?,?,?)",
                                            (at, mandate_sha, 1 if ok else 0, _json(data))))

    def dry_runs_ok(self, mandate_sha):
        return self.db.execute("SELECT count(*) FROM dry_runs WHERE mandate_sha256=? AND ok=1",
                               (mandate_sha,)).fetchone()[0]

    def dry_runs(self):
        return [dict(row, data=json.loads(row["data"])) for row in self.db.execute("SELECT * FROM dry_runs ORDER BY id")]
