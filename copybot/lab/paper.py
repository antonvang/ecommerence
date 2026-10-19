"""Paper execution engine (ENGINE_PROPOSAL.md §2, stage S4). SIMULATION ONLY: no network, no exchange, no keys.

- Isolated ledgers: every order, fill and equity point carries its experiment id; positions and cash are always
  derived from the append-only fill log, never stored as mutable state.
- Taker orders walk the supplied order book level by level (partial fills, limit price, IOC remainder cancelled),
  paying the taker fee and an extra slippage allowance.
- Maker orders rest at a limit and fill only on trade-through prints (optionally at-price), at the limit, paying the
  maker fee (negative = rebate).
- Idempotency: deterministic order ids and fill ids under UNIQUE indexes; a replay after a crash cannot duplicate.
- Funding (research/PROTOCOL_V3.md amendment 9 section 2): settled funding of held positions after T_F is booked as an
  append-only cash flow (sim_funding, one row per ledger, instrument and settlement) and is part of cash and P&L.
- Every figure produced here is simulated and labelled as such.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass

from lab import lifecycle
from lab.risk import Risk

SIMULATED = True
HOUR = 3600
SHADOW = "SHADOW_"          # research/PROTOCOL_V3.md amendment 3: shadow ledgers for observation candidates


def funding_t0(db):
    """T_F (amendment 9 section 2): the runner's clock when it first booked funding (first paper.funding_started);
    None before. Settlements at or before T_F are never booked."""
    r = db.one("SELECT ts, payload FROM events WHERE kind='paper.funding_started' ORDER BY id LIMIT 1")
    if r is None:
        return None
    return int((json.loads(r["payload"] or "{}") or {}).get("t_f") or r["ts"])


def held_before(fills, points):
    """{(instrument, ts): signed position held just before ts} from fills (rows with ts, instrument, side, qty)."""
    fs, out, pos, i = sorted(fills, key=lambda f: f["ts"]), {}, {}, 0
    for inst, t in sorted(points, key=lambda p: p[1]):
        while i < len(fs) and fs[i]["ts"] < t:
            f = fs[i]
            pos[f["instrument"]] = pos.get(f["instrument"], 0.0) + (f["qty"] if f["side"] == "buy" else -f["qty"])
            i += 1
        out[(inst, t)] = pos.get(inst, 0.0)
    return out


def shadow_base(ledger):
    return ledger[len(SHADOW):] if ledger.startswith(SHADOW) else None


def shadow_active(db, exp_id):
    """A human started shadow trading for this experiment, has not stopped it, and it is still in OBSERVATION."""
    r = db.one("SELECT kind, actor FROM events WHERE kind IN ('shadow.approved','shadow.stopped') AND exp_id=? "
               "ORDER BY id DESC LIMIT 1", exp_id)
    return bool(r and r["kind"] == "shadow.approved" and r["actor"].startswith("human:")
                and lifecycle.state(db, exp_id) == "OBSERVATION")


FORWARD = "FWD_"          # research/PROTOCOL_V3.md amendment 7: forward paper tests of frozen variants
FORWARD_ACCOUNTS = {      # exp_id -> (SHA-256 cost.json, SHA-256 backtest.json), fixed by amendment 7 section 2
    "E_vol_managed_long_p1": ("88c8bf0a73c503ce185b2f4e8a000720cfd7e132c7d5ad5feba260fe1dd4d1b6",
                              "04082bdbc350924a788b233a4c8e4091a99bb7b85c0d29b43fff0320a97c264a"),
    "E_day_of_week_p1": ("0b3ed84fde00458af08be5240960740b3049f43a92241da07e82d504361274a8",
                         "511d5d9970b5dc90971b34821416c311f724284b98478aab2b513a7ae76e6df4"),
    "E_hour_of_day_p1": ("6eb4d899312eea97a8fa3505ba8cd1608464772bce8e239aa02914feab4da004",
                         "ed151ff19a0ba3866566bd717acd7af9dff77fcc6e1c19a0beda4a7b741a89fa"),
    "E_funding_contrarian_p1": ("f713d01e6ed6025b5f027c462566ab2c7ef935386220988b697f8569303f33aa",
                                "0061c8ca4bbb9c743a91737056fb3356e907c62495477bd6a5c75ac8bd90f9ef"),
    "E_daily_reversal_p1": ("290c89e69cc98ac74180c3929a5d0c2aba9586aad9b8a6688b56390215f54108",
                            "bc10953b2feeed3f31a0f6cb259a1c6946adadce044ee7de85da7c2cb3c37c26"),
    "E_xs_momentum_p2": ("9348a84f7ac1cc60c634c284c3c9be7b97051f88134b371627ab33eae667a281",
                         "5d8ebbedd5607100952c1891208ac176ea07b20c331f877674571d80a812e572"),
    "E_xs_max_lottery_p2": ("5c3c4c7d16d85fb5af8d83f5077e531babbca23d5813b2780c5fa07c4c8f2087",
                            "713c7f656e5552bddb3b7ef242124fe8ea3a215656554e6374e491462781f9c0"),
    "E_xs_low_volatility_p2": ("ec4bb4bb6d965661b155bf87c864e490336d26586661476e0e737a8d5bd897ab",
                               "17c9ae82f6bc75710fe26a63cf652ea9b209d75ba8f159c82e83cf3aab2134d7"),
    "E_xs_betting_against_beta_p2": ("1b85e44a0122af7e50c1ae45e2ad190d81c119efa77a41575b294ab217a9398a",
                                     "503857c886a128eb0171595bfbe1f31bcb3ff3d963c6aea861c0480082c58fb0"),
    "E_supply_dilution_p3": ("b28aed4201d32acabb72b94398cf37126926854061b31d161d144513d57fa886",
                             "2b8c44767ce1a3169288438d00c56f4778673062c7519e98645a73f922d0212a"),
}
def forward_base(ledger):
    return ledger[len(FORWARD):] if ledger.startswith(FORWARD) else None


def forward_active(db, exp_id):
    """Amendment 7: on the fixed list, started by a human and not stopped, and its artifacts are still the pinned ones."""
    pins = FORWARD_ACCOUNTS.get(exp_id)
    if not pins:
        return False
    r = db.one("SELECT kind, actor FROM events WHERE kind IN ('forward.approved','forward.stopped') AND exp_id=? "
               "ORDER BY id DESC LIMIT 1", exp_id)
    if not (r and r["kind"] == "forward.approved" and r["actor"].startswith("human:")):
        return False
    from lab import pipeline
    return (pipeline.recorded_sha(db, exp_id, "cost"), pipeline.recorded_sha(db, exp_id, "backtest")) == pins


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
        base = shadow_base(exp_id)
        if base is not None:
            if not shadow_active(self.db, base):
                raise lifecycle.LifecycleError(f"{base} has no active, human-started shadow trading in OBSERVATION")
        elif exp_id.startswith("LANE_"):
            from lab import lane
            if not lane.is_active(self.db, exp_id):
                raise lifecycle.LifecycleError(f"{exp_id} is not an active lane account (amendment 11)")
        elif forward_base(exp_id) is not None:
            if not forward_active(self.db, forward_base(exp_id)):
                raise lifecycle.LifecycleError(f"{forward_base(exp_id)} has no active, human-started forward test "
                                               "with its pinned artifacts (amendment 7)")
        else:
            from lab import promotion
            ok, why = promotion.trading_authorized(self.db, exp_id)
            if not ok:
                raise lifecycle.LifecycleError(f"{exp_id} has no verifiable paper approval: {why}")
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

    def ledger(self, exp_id, until=None):
        """Cash, positions and completed round trips (close_ts, pnl incl. fees), all derived from fills and booked
        funding (cash includes funding). realized = closed P&L + fees + funding, from the trades themselves.
        until: the ledger as it stood at that time (fills and funding booked at or before it)."""
        capital, _ = self.config(exp_id)
        cash, pos, basis, realized, trades, fees = capital, {}, {}, {}, [], 0.0
        cut = " AND ts<=?" if until is not None else ""
        args = (exp_id,) + ((int(until),) if until is not None else ())
        for f in self.db.q(f"SELECT * FROM sim_fills WHERE exp_id=?{cut} ORDER BY id", *args):
            inst, sgn = f["instrument"], (1 if f["side"] == "buy" else -1)
            q, px, fee = f["qty"], f["px"], f["fee"]
            cash -= sgn * px * q + fee
            fees += fee
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
        funding = self.db.one(f"SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=?{cut}", *args)[0]
        cash += funding
        return {"cash": cash, "positions": {k: v for k, v in pos.items() if v}, "trades": trades,
                "basis": {k: basis[k] for k, v in pos.items() if v}, "capital": capital, "fees": fees,
                "funding": funding, "realized": sum(p for _, p in trades) + sum(realized.values()) + funding,
                "simulated": True}

    def pnl(self, exp_id, marks):
        """Simulated P&L split: unrealized = open positions marked to `marks` vs their cost basis; realized = the rest
        (closed trades, fees and booked funding). Total = equity - capital."""
        led = self.ledger(exp_id)
        equity = led["cash"] + sum(q * marks[i] for i, q in led["positions"].items())
        unreal = sum(q * (marks[i] - led["basis"][i]) for i, q in led["positions"].items())
        total = equity - led["capital"]
        return {"equity": equity, "total": total, "unrealized": unreal, "realized": total - unreal,
                "funding": led["funding"], "simulated": True}

    # ---------- funding (amendment 9 section 2) ----------
    def _fills(self, exp_id):
        return self.db.q("SELECT ts, instrument, side, qty FROM sim_fills WHERE exp_id=? ORDER BY ts, id", exp_id)

    def funding_due(self, exp_id, t_f):
        """Instruments that may have a settlement to book: held at some time after the later of T_F and their last
        booked settlement, with a full hour inside (since, now] (Binance settles on the hour). Bounds the data fetch."""
        now, fills, last_fill = int(self.now()), self._fills(exp_id), {}
        for f in fills:                                               # ordered by ts
            last_fill[f["instrument"]] = f["ts"]
        booked = {r[0]: r[1] for r in self.db.q("SELECT instrument, MAX(settle_ts) FROM sim_funding WHERE exp_id=? "
                                                "GROUP BY instrument", exp_id)}
        since = {i: max(t_f, booked.get(i) or t_f) for i in last_fill}
        since = {i: t for i, t in since.items() if now // HOUR * HOUR > t}     # a settlement time in (since, now]
        held = held_before(fills, [(i, t + 1) for i, t in since.items()])
        return sorted(i for i, t in since.items() if abs(held[(i, t + 1)]) > 1e-12 or last_fill[i] > t)

    def book_funding(self, exp_id, data, t_f):
        """Book each settled funding of an instrument held at the settlement, after T_F and after the ledger's last
        booked settlement of that instrument: amount = -qty * price * rate (a long pays a positive rate, a short
        receives it), qty = the position just before the settlement, price = open of the 1h bar starting at it.
        data: {instrument: (funding {settle_ts: rate}, opens {bar_open_ts: open})}. A settlement whose bar is not
        out yet waits (in order) for a later pass; a replay cannot book twice (UNIQUE exp_id, instrument, settle_ts)."""
        now, fills, out = int(self.now()), None, []
        for inst, (funding, opens) in sorted(data.items()):
            last = self.db.one("SELECT MAX(settle_ts) FROM sim_funding WHERE exp_id=? AND instrument=?", exp_id, inst)[0]
            since = max(t_f, last if last is not None else t_f)
            for st in sorted(t for t in funding if since < t <= now):
                if fills is None:
                    fills = self._fills(exp_id)
                qty = held_before(fills, [(inst, st)])[(inst, st)]
                if abs(qty) < 1e-12:
                    continue                                          # flat then: nothing to book, never blocks
                if st not in opens:
                    if opens and st < min(opens):                     # older than the fetched bars: unpriceable
                        self._funding_gap(exp_id, inst, st)
                        continue
                    break                                             # its bar is not out yet: wait, in order
                rate, px = funding[st], opens[st]
                try:
                    with self.db.tx():
                        self.db.append("sim_funding", exp_id=exp_id, ts=now, settle_ts=st, instrument=inst, qty=qty,
                                       rate=rate, price=px, amount=-qty * px * rate)
                except sqlite3.IntegrityError:
                    continue                                          # already booked
                out.append({"instrument": inst, "settle_ts": st, "qty": qty, "rate": rate, "amount": -qty * px * rate})
        return out

    def _funding_gap(self, exp_id, inst, st):
        """A held settlement older than the fetched bars cannot be priced: recorded once, then skipped."""
        if not self.db.one("SELECT 1 FROM events WHERE kind='paper.funding_gap' AND exp_id=? AND payload LIKE ?",
                           exp_id, f'%"instrument":"{inst}"%"settle_ts":{st}%'):
            self.db.event("paper.funding_gap", "agent:paper-1", exp_id, {"instrument": inst, "settle_ts": st,
                                                                         "reason": "no price bar left for it"})

    def reconcile(self, exp_id):
        """The checks below on ONE read snapshot: a fill or funding row committed by another connection between two
        reads must never look like a mismatch (that would fail the whole lab closed)."""
        own = not self.db.con.in_transaction
        if own:
            self.db.con.execute("BEGIN")
        try:
            return self._reconcile(exp_id)
        finally:
            if own:
                self.db.con.execute("COMMIT")

    def _reconcile(self, exp_id):
        """Orders vs fills vs cancels vs positions, and cash = capital + fill cash flows - fees + funding (amendment 9
        section 2) with every funding row checked against the fills. Any problem is returned (the caller fails the lab
        closed)."""
        problems = []
        for o in self.db.q("SELECT * FROM sim_orders WHERE exp_id=?", exp_id):
            fills = self.db.q("SELECT * FROM sim_fills WHERE order_id=?", o["order_id"])
            filled = sum(f["qty"] for f in fills)
            if filled > o["qty"] + 1e-9:
                problems.append(f"overfill {o['order_id']}")
            for f in fills:
                if (f["exp_id"], f["instrument"], f["side"]) != (o["exp_id"], o["instrument"], o["side"]):
                    problems.append(f"fill {f['fill_id']} does not match its order")
            cancelled = self.db.one("SELECT 1 FROM sim_cancels WHERE order_id=?", o["order_id"])
            if o["style"] == "taker" and filled < o["qty"] - 1e-9 and not cancelled:
                problems.append(f"taker order {o['order_id']} partially filled without IOC cancel")
        orphan = self.db.one("SELECT COUNT(*) FROM sim_fills f WHERE f.exp_id=? AND NOT EXISTS "
                             "(SELECT 1 FROM sim_orders o WHERE o.order_id=f.order_id)", exp_id)[0]
        if orphan:
            problems.append(f"{orphan} fills without an order")
        fills = self.db.q("SELECT ts, instrument, side, qty, px, fee FROM sim_fills WHERE exp_id=? ORDER BY ts, id",
                          exp_id)
        fund = self.db.q("SELECT settle_ts, instrument, qty, rate, price, amount FROM sim_funding WHERE exp_id=? "
                         "ORDER BY settle_ts, id", exp_id)
        t_f = funding_t0(self.db) if fund else None
        held = held_before(fills, [(r["instrument"], r["settle_ts"]) for r in fund])
        for r in fund:
            where = f"funding {r['instrument']}@{r['settle_ts']}"
            if t_f is None or r["settle_ts"] <= t_f:
                problems.append(f"{where} is not after T_F")
            want = held[(r["instrument"], r["settle_ts"])]
            if abs(r["qty"] - want) > 1e-9 * max(1.0, abs(want)):
                problems.append(f"{where}: qty {r['qty']} is not the position held before the settlement ({want})")
            if abs(r["amount"] + r["qty"] * r["price"] * r["rate"]) > 1e-9 * max(1.0, abs(r["amount"])):
                problems.append(f"{where}: amount is not -qty * price * rate")
        cash = None
        if self.db.one("SELECT 1 FROM events WHERE kind='paper.started' AND exp_id=?", exp_id):
            capital, _ = self.config(exp_id)
            flows = sum((f["px"] * f["qty"]) * (-1 if f["side"] == "buy" else 1) for f in fills)
            fees, funding = sum(f["fee"] for f in fills), sum(r["amount"] for r in fund)
            cash = {"capital": capital, "fill_flows": flows, "fees": fees, "funding": funding,
                    "cash": capital + flows - fees + funding}
            if abs(cash["cash"] - self.ledger(exp_id)["cash"]) > 1e-6:
                problems.append("cash is not capital + fill cash flows - fees + funding")
        elif fills or fund:
            problems.append("fills or funding without a started ledger")
        return {"ok": not problems, "problems": problems, "cash": cash}

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
