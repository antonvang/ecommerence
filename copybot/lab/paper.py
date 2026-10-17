"""Paper execution engine (ENGINE_PROPOSAL.md §2, stage S4). SIMULATION ONLY: no network, no exchange, no keys.

- Isolated ledgers: every order, fill and equity point carries its experiment id; positions and cash are always
  derived from the append-only fill log, never stored as mutable state.
- Taker orders walk the supplied order book level by level (partial fills, limit price, IOC remainder cancelled),
  paying the taker fee and an extra slippage allowance.
- Maker orders rest at a limit and fill only on trade-through prints (optionally at-price), at the limit, paying the
  maker fee (negative = rebate).
- Idempotency: deterministic order ids and fill ids under UNIQUE indexes; a replay after a crash cannot duplicate.
- Every figure produced here is simulated and labelled as such.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass

from lab import lifecycle
from lab.risk import Risk

SIMULATED = True


@dataclass(frozen=True)
class CostModel:
    taker_fee: float              # fraction of notional, e.g. 0.0005
    maker_fee: float = 0.0        # negative = rebate
    extra_slippage: float = 0.0   # fraction added against us on taker fills
    expected_spread: float = 0.0  # fraction; used by the spread-anomaly breaker


@dataclass(frozen=True)
class Book:
    ts: float
    bids: tuple                   # ((price, size), ...) best first
    asks: tuple

    def mid(self):
        return (self.bids[0][0] + self.asks[0][0]) / 2

    def spread(self):
        return (self.asks[0][0] - self.bids[0][0]) / self.mid()

    def crossed(self):
        return not self.bids or not self.asks or self.bids[0][0] >= self.asks[0][0]


class PaperEngine:
    def __init__(self, db, now=time.time):
        self.db, self.now = db, now
        self.risk = Risk(db, now)

    # ---------- ledger ----------
    def start(self, exp_id, capital, costs, actor="system:paper"):
        if lifecycle.state(self.db, exp_id) != "PAPER_TRADING":
            raise lifecycle.LifecycleError(f"{exp_id} is not PAPER_TRADING")
        if self.db.one("SELECT 1 FROM events WHERE kind='paper.started' AND exp_id=?", exp_id):
            return False
        self.db.event("paper.started", actor, exp_id, {"capital": capital, "costs": asdict(costs), "simulated": True})
        return True

    def config(self, exp_id):
        import json
        r = self.db.one("SELECT payload FROM events WHERE kind='paper.started' AND exp_id=? ORDER BY id LIMIT 1", exp_id)
        if r is None:
            raise lifecycle.LifecycleError(f"{exp_id} has no paper ledger (start it first)")
        p = json.loads(r["payload"])
        return p["capital"], CostModel(**p["costs"])

    def ledger(self, exp_id):
        """Cash, positions and completed round trips (close_ts, pnl incl. fees), all derived from fills."""
        capital, _ = self.config(exp_id)
        cash, pos, basis, realized, trades = capital, {}, {}, {}, []
        for f in self.db.q("SELECT * FROM sim_fills WHERE exp_id=? ORDER BY id", exp_id):
            inst, sgn = f["instrument"], (1 if f["side"] == "buy" else -1)
            q, px, fee = f["qty"], f["px"], f["fee"]
            cash -= sgn * px * q + fee
            p0 = pos.get(inst, 0.0)
            realized[inst] = realized.get(inst, 0.0) - fee
            if p0 == 0 or (p0 > 0) == (sgn > 0):                     # opening / adding
                basis[inst] = (basis.get(inst, 0.0) * abs(p0) + px * q) / (abs(p0) + q)
                pos[inst] = p0 + sgn * q
            else:                                                     # reducing (and possibly flipping)
                closed = min(q, abs(p0))
                realized[inst] += closed * (px - basis[inst]) * (1 if p0 > 0 else -1)
                pos[inst] = p0 + sgn * q
                if abs(pos[inst]) < 1e-12:
                    pos[inst] = 0.0
                    trades.append((f["ts"], realized[inst]))
                    realized[inst] = 0.0
                elif (pos[inst] > 0) != (p0 > 0):                     # flipped: the excess opens a new trade
                    trades.append((f["ts"], realized[inst]))
                    realized[inst] = 0.0
                    basis[inst] = px
        return {"cash": cash, "positions": {k: v for k, v in pos.items() if v}, "trades": trades,
                "capital": capital, "simulated": True}

    def open_orders(self, exp_id=None, instrument=None):
        q = ("SELECT o.* FROM sim_orders o WHERE o.style='maker' AND NOT EXISTS (SELECT 1 FROM sim_cancels c "
             "WHERE c.order_id=o.order_id)")
        args = []
        if exp_id:
            q += " AND o.exp_id=?"
            args.append(exp_id)
        if instrument:
            q += " AND o.instrument=?"
            args.append(instrument)
        out = []
        for o in self.db.q(q + " ORDER BY o.id", *args):
            filled = self.db.one("SELECT COALESCE(SUM(qty),0) FROM sim_fills WHERE order_id=?", o["order_id"])[0]
            if filled < o["qty"] - 1e-12:
                out.append((o, o["qty"] - filled))
        return out

    def cancel(self, order_id, reason):
        o = self.db.one("SELECT exp_id FROM sim_orders WHERE order_id=?", order_id)
        if o is None or self.db.one("SELECT 1 FROM sim_cancels WHERE order_id=?", order_id):
            return False
        with self.db.tx():
            self.db.append("sim_cancels", order_id=order_id, exp_id=o["exp_id"], ts=int(self.now()), reason=reason)
        return True

    def cancel_entries(self, exp_id, reason):
        for o, _ in self.open_orders(exp_id):
            if not o["reduce_only"]:
                self.cancel(o["order_id"], reason)

    # ---------- orders ----------
    def _existing(self, order_id):
        o = self.db.one("SELECT * FROM sim_orders WHERE order_id=?", order_id)
        if o is None:
            return None
        return {"status": "duplicate", "order_id": order_id,
                "fills": [dict(f) for f in self.db.q("SELECT * FROM sim_fills WHERE order_id=? ORDER BY id", order_id)],
                "simulated": True}

    def _reduces(self, exp_id, instrument, side, qty):
        p = self.ledger(exp_id)["positions"].get(instrument, 0.0)
        return (p > 0 and side == "sell" and qty <= p + 1e-12) or (p < 0 and side == "buy" and qty <= -p + 1e-12)

    def _gate(self, exp_id, order_id, instrument, side, qty, book, reduce_only, signal_ref):
        if reduce_only and not self._reduces(exp_id, instrument, side, qty):
            return False, "reduce_only order would not reduce the position"
        ok, why = self.risk.entry_allowed(exp_id, reduce_only, book)
        if not ok:
            kind = "paper.signal_while_paused" if "paused" in why else "paper.refused"
            self.db.event(kind, "system:paper", exp_id, {"order_id": order_id, "instrument": instrument, "side": side,
                                                         "qty": qty, "reason": why, "signal_ref": signal_ref,
                                                         "excluded_from_resume_decision": True})
        return ok, why

    def submit_taker(self, exp_id, order_id, instrument, side, qty, book, limit_px=None, reduce_only=False,
                     signal_ref=None):
        dup = self._existing(order_id)
        if dup:
            return dup
        ok, why = self._gate(exp_id, order_id, instrument, side, qty, book, reduce_only, signal_ref)
        if not ok:
            return {"status": "refused", "reason": why, "order_id": order_id, "fills": [], "simulated": True}
        _, costs = self.config(exp_id)
        levels = book.asks if side == "buy" else book.bids
        mid, now, rest, fills = book.mid(), int(self.now()), qty, []
        for i, (px, size) in enumerate(levels):
            if rest <= 1e-12 or (limit_px is not None and ((side == "buy" and px > limit_px) or
                                                          (side == "sell" and px < limit_px))):
                break
            q = min(rest, size)
            exe = px * (1 + costs.extra_slippage) if side == "buy" else px * (1 - costs.extra_slippage)
            fills.append({"fill_id": f"{order_id}|{i}", "px": exe, "qty": q, "fee": costs.taker_fee * exe * q,
                          "slippage": (exe - mid) / mid if side == "buy" else (mid - exe) / mid})
            rest -= q
        try:
            with self.db.tx():
                self.db.append("sim_orders", order_id=order_id, exp_id=exp_id, ts=now, instrument=instrument, side=side,
                               qty=qty, limit_px=limit_px, style="taker", reduce_only=int(reduce_only),
                               signal_ref=signal_ref, cost_model=asdict(costs))
                for f in fills:
                    self.db.append("sim_fills", order_id=order_id, exp_id=exp_id, ts=now, instrument=instrument,
                                   side=side, liquidity="taker", mid=mid, book_ts=book.ts, **f)
                if rest > 1e-12:
                    self.db.append("sim_cancels", order_id=order_id, exp_id=exp_id, ts=now,
                                   reason="IOC remainder (depth or limit)")
                self.db.event("paper.order", "system:paper", exp_id, {"order_id": order_id, "style": "taker",
                                                                      "filled": qty - rest, "simulated": True})
        except sqlite3.IntegrityError:
            return self._existing(order_id)
        self._after(exp_id, book.spread(), costs.expected_spread)
        return {"status": "filled" if rest <= 1e-12 else ("partial" if fills else "unfilled"), "order_id": order_id,
                "fills": fills, "unfilled": rest, "simulated": True}

    def submit_maker(self, exp_id, order_id, instrument, side, qty, limit_px, book, reduce_only=False, signal_ref=None):
        dup = self._existing(order_id)
        if dup:
            return dup
        ok, why = self._gate(exp_id, order_id, instrument, side, qty, book, reduce_only, signal_ref)
        if not ok:
            return {"status": "refused", "reason": why, "order_id": order_id, "fills": [], "simulated": True}
        _, costs = self.config(exp_id)
        try:
            with self.db.tx():
                self.db.append("sim_orders", order_id=order_id, exp_id=exp_id, ts=int(self.now()), instrument=instrument,
                               side=side, qty=qty, limit_px=limit_px, style="maker", reduce_only=int(reduce_only),
                               signal_ref=signal_ref, cost_model=asdict(costs))
                self.db.event("paper.order", "system:paper", exp_id, {"order_id": order_id, "style": "maker",
                                                                      "limit": limit_px, "simulated": True})
        except sqlite3.IntegrityError:
            return self._existing(order_id)
        return {"status": "resting", "order_id": order_id, "fills": [], "simulated": True}

    def on_trade(self, instrument, trade_id, ts, price, size, mid=None, at_price=False):
        """Feed one public trade print. Resting maker orders fill only if the print trades through their limit."""
        out, left = [], size
        for o, remaining in self.open_orders(instrument=instrument):
            if left <= 1e-12:
                break
            buy = o["side"] == "buy"
            through = price < o["limit_px"] if buy else price > o["limit_px"]
            if at_price:
                through = through or price == o["limit_px"]
            if not through:
                continue
            if not o["reduce_only"] and (self.risk.paused(o["exp_id"]) or self.risk.fail_closed()):
                continue
            q = min(remaining, left)
            _, costs = self.config(o["exp_id"])
            fid = f"{o['order_id']}|{trade_id}"
            try:
                with self.db.tx():
                    self.db.append("sim_fills", fill_id=fid, order_id=o["order_id"], exp_id=o["exp_id"], ts=int(ts),
                                   instrument=instrument, side=o["side"], px=o["limit_px"], qty=q,
                                   fee=costs.maker_fee * o["limit_px"] * q,
                                   slippage=((o["limit_px"] - mid) / mid * (1 if buy else -1)) if mid else None,
                                   liquidity="maker", mid=mid, book_ts=None)
            except sqlite3.IntegrityError:
                continue                                              # replayed print: already filled
            left -= q
            out.append({"order_id": o["order_id"], "qty": q, "px": o["limit_px"]})
            self._after(o["exp_id"], None, None)
        return out

    def mark(self, exp_id, marks):
        """Record simulated equity at the given mark prices; drives the drawdown breaker."""
        led = self.ledger(exp_id)
        exposure = sum(abs(q) * marks[i] for i, q in led["positions"].items())
        equity = led["cash"] + sum(q * marks[i] for i, q in led["positions"].items())
        prev = self.db.one("SELECT peak FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", exp_id)
        peak = max(led["capital"], equity, prev["peak"] if prev else led["capital"])
        dd = (peak - equity) / peak if peak > 0 else 0.0
        with self.db.tx():
            self.db.append("sim_equity", exp_id=exp_id, ts=int(self.now()), equity=equity, cash=led["cash"],
                           exposure=exposure, peak=peak, drawdown=dd)
        self.risk.after_equity(exp_id, dd, self.cancel_entries)
        return {"equity": equity, "drawdown": dd, "simulated": True}

    def _after(self, exp_id, spread, expected):
        led = self.ledger(exp_id)
        overfill = self.db.one("SELECT o.order_id FROM sim_orders o WHERE o.exp_id=? AND o.qty + 1e-9 < "
                               "(SELECT COALESCE(SUM(qty),0) FROM sim_fills f WHERE f.order_id=o.order_id) LIMIT 1", exp_id)
        if overfill:
            self.risk.trip_fail_closed("overfill", f"{exp_id}: order {overfill[0]} filled beyond its size")
        if spread is not None:
            self.risk.after_spread(exp_id, spread, expected, self.cancel_entries)
        self.risk.after_trade_closed(exp_id, led["trades"], self.cancel_entries)
