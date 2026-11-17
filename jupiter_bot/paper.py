"""Atomic integer accounting for explicitly fictitious USDC/SOL balances."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from . import storage
from .core import Quote, Rejected, SOL, USDC, SOURCES, canonical


@dataclass(frozen=True)
class Limits:
    initial_usdc: int = 1_000_000_000
    max_buy_usdc: int = 25_000_000
    max_position_cost_usdc: int = 50_000_000
    adverse_bps: int = 25
    network_fee_usdc: int = 10_000

    def __post_init__(self):
        if any(type(value) is not int or value < 0 for value in asdict(self).values()):
            raise Rejected("Limits must be non-negative integers")
        if not (self.initial_usdc > 0 and self.max_buy_usdc > 0 and
                self.max_position_cost_usdc > 0 and self.adverse_bps < 10000):
            raise Rejected("Invalid paper limits")


# SQLite header field marking a file as this prototype's paper book ("JBP1").
# Any other non-empty database (e.g. copybot/data/paper.db) is never written.
APPLICATION_ID = 0x4A425031
SCHEMA_VERSION = 1
STATE_KEYS = ("usdc", "sol", "cost_usdc", "fills")


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS accounts(
         account TEXT PRIMARY KEY, config TEXT NOT NULL, usdc INTEGER NOT NULL CHECK(usdc >= 0),
         sol INTEGER NOT NULL CHECK(sol >= 0), cost_usdc INTEGER NOT NULL CHECK(cost_usdc >= 0))""",
    """CREATE TABLE IF NOT EXISTS fills(
         id INTEGER PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(account),
         quote_id TEXT NOT NULL, observed_at REAL NOT NULL, source TEXT NOT NULL,
         side TEXT NOT NULL, input_amount INTEGER NOT NULL, output_amount INTEGER NOT NULL,
         assumed_network_usdc INTEGER NOT NULL, assumed_adverse_bps INTEGER NOT NULL,
         realized_pnl_usdc INTEGER NOT NULL, audit_json TEXT NOT NULL,
         UNIQUE(account, quote_id))""",
    """CREATE TABLE IF NOT EXISTS decisions(
         id INTEGER PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(account),
         as_of REAL NOT NULL, audit_json TEXT NOT NULL)""",
)


class PaperBook:
    def __init__(self, path, source="SYNTHETIC", account="paper", limits=None, readonly=False):
        if source not in SOURCES or not account:
            raise Rejected("Invalid paper account provenance")
        self.source, self.account, self.limits = source, account, limits or Limits()
        self.readonly = readonly
        self.db = storage.connect(path, readonly)
        try:
            self._open()
        except Exception:
            self.db.close()
            raise

    def _open(self):
        if self.readonly:
            storage.is_marked(self.db, APPLICATION_ID, SCHEMA_VERSION, True, "paper")
            row = self.db.execute("SELECT config FROM accounts WHERE account=?", (self.account,)).fetchone()
            if row is None or json.loads(row[0]).get("source") != self.source:
                raise Rejected("Paper account not found for this source")
            self.config = json.loads(row[0])
            return
        config = canonical(dict(asdict(self.limits), source=self.source))

        def ensure_account(db):
            db.execute("INSERT OR IGNORE INTO accounts VALUES (?, ?, ?, 0, 0)",
                       (self.account, config, self.limits.initial_usdc))
            stored = db.execute("SELECT config FROM accounts WHERE account=?", (self.account,)).fetchone()[0]
            if stored != config:
                raise Rejected("Existing account has different source or frozen limits; use a new account")

        storage.initialise(self.db, APPLICATION_ID, SCHEMA_VERSION, SCHEMA, "paper", ensure_account)
        self.config = json.loads(config)

    def close(self):
        self.db.close()

    def state(self):
        row = self.db.execute("SELECT usdc, sol, cost_usdc FROM accounts WHERE account=?",
                              (self.account,)).fetchone()
        totals = self.db.execute("SELECT count(*), coalesce(sum(realized_pnl_usdc), 0) FROM fills WHERE account=?",
                                (self.account,)).fetchone()
        return dict(row, fills=totals[0], realized_pnl_usdc=totals[1], source=self.source,
                    mode="PAPER_ONLY", live_execution=False, onchain_confirmed=False)

    def decision(self, result):
        if self.readonly:
            raise Rejected("Read-only paper book")
        self.db.execute("INSERT INTO decisions(account, as_of, audit_json) VALUES (?, ?, ?)",
                        (self.account, result["as_of"], canonical(result)))

    def fill(self, quote, now=None, expect=None):
        """Book one simulated fill. `expect` is the account state the decision
        was made on; if another process changed it meanwhile, nothing is booked."""
        if self.readonly:
            raise Rejected("Read-only paper book")
        if not isinstance(quote, Quote):
            raise Rejected("A validated Quote is required")
        quote.require_fresh(time.time() if now is None else now)
        if quote.source != self.source:
            raise Rejected("Synthetic and observed quotes must use different accounts")
        # Revalidate the serialized evidence before any account mutation.
        checked = Quote.parse(quote.request, json.loads(quote.payload_json),
                              quote.started_at, quote.observed_at, quote.source)
        if checked != quote:
            raise Rejected("Quote differs from its audit evidence")
        amount = quote.request.amount
        output = quote.out_amount * (10000 - self.limits.adverse_bps) // 10000
        fee = self.limits.network_fee_usdc
        if output <= 0:
            raise Rejected("No output after adverse-price assumption")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT 1 FROM fills WHERE account=? AND quote_id=?",
                               (self.account, quote.quote_id)).fetchone():
                raise Rejected("Quote already filled on this paper account")
            state = self.state()
            if expect is not None and any(state[key] != expect[key] for key in STATE_KEYS):
                raise Rejected("Account changed after the decision; no fill")
            usdc, sol, cost = state["usdc"], state["sol"], state["cost_usdc"]
            if quote.request.input_asset == USDC:
                if amount > self.limits.max_buy_usdc:
                    raise Rejected("Paper buy exceeds order limit")
                if cost + amount + fee > self.limits.max_position_cost_usdc:
                    raise Rejected("Paper position exceeds cost limit")
                if usdc < amount + fee:
                    raise Rejected("Insufficient fictitious USDC")
                side, realized = "BUY", 0
                usdc, sol, cost = usdc - amount - fee, sol + output, cost + amount + fee
            else:
                if sol < amount:
                    raise Rejected("Insufficient fictitious SOL")
                received = output - fee
                if received <= 0:
                    raise Rejected("Output does not cover assumed network cost")
                # Round removed cost up: rounding may make realized P&L worse, never better.
                removed_cost = cost if amount == sol else -(-cost * amount // sol)
                side, realized = "SELL", received - removed_cost
                usdc, sol, cost = usdc + received, sol - amount, cost - removed_cost
            self.db.execute("UPDATE accounts SET usdc=?, sol=?, cost_usdc=? WHERE account=?",
                            (usdc, sol, cost, self.account))
            self.db.execute("""INSERT INTO fills(account, quote_id, observed_at, source, side,
                              input_amount, output_amount, assumed_network_usdc,
                              assumed_adverse_bps, realized_pnl_usdc, audit_json)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (self.account, quote.quote_id, quote.observed_at, quote.source, side,
                             amount, output, fee, self.limits.adverse_bps, realized,
                             canonical(dict(quote.as_dict(), kind="PAPER_SIMULATED",
                                            onchain_confirmed=False))))
            self.db.execute("COMMIT")
            return self.state()
        except Exception:
            storage.rollback(self.db)
            raise
