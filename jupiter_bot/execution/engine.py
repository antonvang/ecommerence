"""Execution engine: resolve -> decide -> (at most) one order per cycle.

Order life cycle (ledger.py): INTENT is stored before any request leaves the
machine; VERIFIED after the order response and the transaction passed every
check; SIGNED (signature known locally) before `/execute`; then SUBMITTED or
UNKNOWN. Only the chain decides the end: CONFIRMED / FAILED / EXPIRED. While
any order is not terminal, no new order is created, and nothing is ever re-sent
as a new order. The kill switch (arm file + mandate hash) is re-checked right
before signing and right before sending.
"""
from __future__ import annotations

import base64
import fcntl
import os
import time
from contextlib import contextmanager
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from ..core import SOL, USDC, Rejected
from ..research.strategies import FLAT, LONG, STRATEGIES
from . import config, gates
from . import mandate as mandate_mod
from .http import SafeHTTP, urllib_transport
from .jupiter_exec import ExecuteAnswer, JupiterExec, OrderRequest, make_request
from .ledger import (CONFIRMED, EXPIRED, FAILED, INTENT, SIGNED, SUBMITTED, UNKNOWN, VERIFIED, Ledger,
                     utc_day)
from .rpc import Rpc
from .signer_client import SubprocessSigner
from .solana_tx import b58encode, parse_token_account, parse_transaction, with_signature
from .verify import check_deltas, verify, view


@contextmanager
def process_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Rejected("another execution process holds the lock") from None
        yield
    finally:
        os.close(fd)


@contextmanager
def wallet_locks(paths):
    """The data-dir lock AND one lock per wallet, independent of --data-dir (F7)."""
    mandate, _, _ = mandate_mod.load_once(paths.mandate)
    with process_lock(paths.lock):
        if mandate is None:
            yield
        else:
            with process_lock(paths.wallet_lock(mandate.wallet_pubkey)):
                yield


def sol_for_usdc(usdc_atoms, price):
    """Lamports worth `usdc_atoms` at `price` USDC/SOL (rounded down)."""
    return int((Decimal(usdc_atoms) * 1000 / Decimal(price)).to_integral_value(ROUND_FLOOR))


def usdc_value(lamports, price):
    return int((Decimal(lamports) * Decimal(price) / 1000).to_integral_value(ROUND_FLOOR))


def decide(mandate, target, price, position_sol, cost_basis, lamports, usdc_balance, today_pnl):
    """Pure sizing rule. Returns {"side": None|"BUY"|"SELL", "amount": int, "reason": str}."""
    value = usdc_value(position_sol, price)
    if target == LONG:
        if today_pnl <= -mandate.daily_loss_limit_usdc:
            return {"side": None, "amount": 0, "reason": "daily loss limit reached; no BUY until next UTC day"}
        room = mandate.max_position_usdc - max(cost_basis, value)
        amount = min(mandate.max_trade_usdc, room, usdc_balance)
        if lamports < config.SOL_RESERVE_LAMPORTS:
            return {"side": None, "amount": 0, "reason": "SOL balance below the fee reserve"}
        if amount < config.MIN_TRADE_USDC_ATOMS:
            return {"side": None, "amount": 0, "reason": "LONG: at max position or no USDC to spend"}
        return {"side": "BUY", "amount": amount, "reason": "LONG target; position below max"}
    if target == FLAT:
        if value < config.MIN_TRADE_USDC_ATOMS:
            return {"side": None, "amount": 0, "reason": "FLAT: no position to sell"}
        amount = position_sol if value <= mandate.max_trade_usdc else sol_for_usdc(mandate.max_trade_usdc, price)
        amount = min(amount, mandate.max_trade_sol, lamports - config.SOL_RESERVE_LAMPORTS)
        if usdc_value(max(amount, 0), price) < config.MIN_TRADE_USDC_ATOMS:
            return {"side": None, "amount": 0, "reason": "FLAT: not enough SOL above the fee reserve"}
        return {"side": "SELL", "amount": amount, "reason": "FLAT target; selling the position"}
    raise Rejected("Strategy returned an unknown target %r" % (target,))


def default_snapshot(paths):
    def snapshot(mandate, now):
        from ..marketdata.journal import Journal
        from ..marketdata.snapshot import build_snapshot
        _, bars_needed, _ = STRATEGIES[mandate.strategy]
        journal = Journal(paths.journal, readonly=True)
        try:
            return build_snapshot(journal, now, bars=bars_needed(mandate.params))
        finally:
            journal.close()
    return snapshot


def default_target(mandate, snapshot):
    return STRATEGIES[mandate.strategy][0](snapshot, mandate.params)


def _verify_signature(wallet, message, signature):
    """Extra check when PyNaCl is importable here; the signer already guarantees it."""
    try:
        import nacl.exceptions
        import nacl.signing
    except ImportError:
        return
    from .solana_tx import pubkey_bytes
    try:
        nacl.signing.VerifyKey(pubkey_bytes(wallet)).verify(message, signature)
    except nacl.exceptions.BadSignatureError:
        raise Rejected("signature does not verify against the wallet") from None


def _text(exc):
    return str(exc) if isinstance(exc, Rejected) else "%s: %s" % (type(exc).__name__, str(exc)[:200])


class Engine:
    def __init__(self, paths, transport=urllib_transport, signer=None, clock=time.time,
                 monotonic=time.monotonic, sleep=time.sleep, snapshot_fn=None, target_fn=None,
                 verdict_loader=gates.load_verdicts, lock_loader=None, lock_verify=None, uid=None,
                 signature_verifier=None):
        self.paths, self.transport, self.clock = paths, transport, clock
        self.signature_verifier = signature_verifier or _verify_signature
        self.monotonic, self.sleep = monotonic, sleep
        self.signer = signer or SubprocessSigner(paths)
        self.snapshot_fn = snapshot_fn or default_snapshot(paths)
        self.target_fn = target_fn or default_target
        self.gate_options = dict(verdict_loader=verdict_loader, lock_loader=lock_loader,
                                 lock_verify=lock_verify, uid=uid)
        self._ledger = None
        self._inflight = set()

    # plumbing -------------------------------------------------------------------------

    def ledger(self):
        if self._ledger is None:
            self._ledger = Ledger(self.paths.ledger)
        return self._ledger

    def close(self):
        if self._ledger is not None:
            self._ledger.close()
            self._ledger = None

    def state(self, ledger=None):
        return gates.evaluate(self.paths, self.clock(), ledger, **self.gate_options)

    def _http(self, mandate):
        return SafeHTTP(["api.jup.ag", mandate.rpc_host], self.transport)

    def _clients(self, mandate):
        http = self._http(mandate)
        return (JupiterExec(http, self.clock, self.monotonic, self.sleep), Rpc(mandate.rpc_url, http))

    def _still_live(self, ledger, mandate_sha):
        state = self.state(ledger)
        return state.mode == "LIVE" and state.mandate_sha == mandate_sha

    # status ---------------------------------------------------------------------------

    def status(self):
        now = self.clock()
        ledger = Ledger.open_readonly_if_exists(self.paths.ledger)
        try:
            state = gates.evaluate(self.paths, now, ledger, **self.gate_options)
            orders = ledger.counts() if ledger else {"total": 0, "pending": 0, "confirmed": 0,
                                                    "failed": 0, "unknown": 0}
            pnl = ledger.realized_on(utc_day(now)) if ledger else 0
        finally:
            if ledger:
                ledger.close()
        result = {"armed": state.mode == "LIVE", "mode": state.mode,
                  "mandate": state.mandate.public() if state.mandate else None,
                  "gates": state.gates, "orders": orders, "today_realized_pnl_usdc": pnl / 1e6}
        return result, state

    # resolver -------------------------------------------------------------------------

    def resolve(self):
        """Advance every non-terminal order using the chain. Never sends anything."""
        ledger = self.ledger()
        pending = [o for o in ledger.non_terminal() if o["order_id"] not in self._inflight]
        if not pending:
            return []
        mandate, error = mandate_mod.load(self.paths.mandate)   # expiry does not matter for resolving
        rpc = Rpc(mandate.rpc_url, self._http(mandate)) if mandate else None
        results = []
        for row in pending:
            order_id = row["order_id"]
            order = ledger.order(order_id)
            state, now = order["state"], self.clock()
            if state in (INTENT, VERIFIED):
                ledger.transition(order_id, FAILED, {"reason": "abandoned before signing (process ended); "
                                                     "never signed, cannot land"}, now)
                results.append((order_id, FAILED))
                continue
            if state == SIGNED:
                ledger.transition(order_id, UNKNOWN, {"reason": "process ended after signing; "
                                                      "may have been sent"}, now)
                state = UNKNOWN
            if rpc is None:
                results.append((order_id, "UNRESOLVED: no readable mandate/rpc_url (%s)" % error))
                continue
            try:
                outcome = self._check_chain(ledger, ledger.order(order_id), rpc, mandate.wallet_pubkey)
            except Rejected as exc:
                ledger.event("resolve_error", {"order_id": order_id, "error": str(exc)[:300]}, now)
                outcome = "UNRESOLVED: %s" % exc
            results.append((order_id, outcome or state))
        return results

    def _check_chain(self, ledger, order, rpc, wallet):
        """Book a finalized landing; EXPIRED only on positive evidence that it cannot land (F5)."""
        facts = order["facts"]
        signature = facts["signature"]
        fin_slot, fin_height = rpc.epoch_info("finalized")
        status_slot, status = rpc.signature_status_at(signature)
        if status is not None:
            if status["confirmation"] != "finalized":
                return None
            tx = rpc.transaction(signature)
            return self._book(ledger, order, tx, wallet) if tx is not None else None
        if fin_height <= facts["last_valid_block_height"] + config.EXPIRY_MARGIN_BLOCKS:
            return None                                   # can still land: wait
        if status_slot < fin_slot:
            return "UNKNOWN: RPC status answer (slot %d) is older than the finalized expiry slot %d" % (
                status_slot, fin_slot)
        tx = rpc.transaction(signature)
        if tx is not None:                                # status cache lost it but history has it
            return self._book(ledger, order, tx, wallet)
        status_slot, status = rpc.signature_status_at(signature)
        if status is not None or status_slot < fin_slot:
            return None
        pre = facts.get("pre")
        if not pre:
            return "UNKNOWN: no pre-order balance snapshot; resolve by hand"
        try:
            _, accounts = rpc.multiple_accounts(pre["addresses"])
            sol, mints, issues = view(facts.get("wallet", wallet), pre["addresses"], accounts, "now")
        except Rejected as exc:
            return "UNKNOWN: cannot read wallet balances: %s" % exc
        if issues or sol != pre["sol"] or {m: v for m, v in mints.items() if v} != \
                {m: v for m, v in pre["mints"].items() if v}:
            ledger.event("expiry_blocked", {"order_id": order["order_id"], "reason": "wallet balances changed "
                                            "since VERIFIED; the transaction may have landed"}, self.clock())
            return "UNKNOWN: wallet balances changed since the order was verified; use an RPC with full " \
                   "history and run resolve again, or check by hand (force-expire)"
        ledger.transition(order["order_id"], EXPIRED, {
            "finalized_block_height": fin_height, "finalized_slot": fin_slot, "status_context_slot": status_slot,
            "reason": "not on chain, getTransaction null, blockhash expired, balances unchanged"}, self.clock())
        return EXPIRED

    def _book(self, ledger, order, tx, wallet):
        facts, now = order["facts"], self.clock()
        wallet = facts.get("wallet", wallet)
        try:
            meta, message = tx["meta"], tx["transaction"]["message"]
            signatures = tx["transaction"]["signatures"]
            loaded = meta.get("loadedAddresses") or {}
            keys = list(message["accountKeys"]) + list(loaded.get("writable", [])) + list(loaded.get("readonly", []))
            pre, post, fee = meta["preBalances"], meta["postBalances"], meta["fee"]
            if signatures[0] != facts["signature"] or keys[0] != wallet or len(pre) != len(keys) \
                    or len(post) != len(keys) or type(fee) is not int:
                raise Rejected("getTransaction result does not match the order")
            deltas = {"sol": post[0] - pre[0]}
            for sign, entries in ((-1, meta.get("preTokenBalances") or []),
                                  (1, meta.get("postTokenBalances") or [])):
                for entry in entries:
                    if entry.get("owner") != wallet:
                        continue
                    amount = entry["uiTokenAmount"]["amount"]
                    if not isinstance(amount, str) or not amount.isdigit():
                        raise Rejected("token balance amount is not an integer string")
                    deltas[entry["mint"]] = deltas.get(entry["mint"], 0) + sign * int(amount)
        except Rejected:
            raise
        except (KeyError, TypeError, IndexError, AttributeError, ValueError) as exc:
            raise Rejected("getTransaction result is malformed: %s" % type(exc).__name__) from exc
        deltas["sol"] += deltas.get(SOL.mint, 0)
        sol_delta, usdc_delta = deltas["sol"], deltas.get(USDC.mint, 0)
        request = OrderRequest(order["side"], order["input_mint"], order["output_mint"], order["in_amount"],
                               wallet, 0)
        price = order["decision"].get("price", "0")
        data = {"deltas": deltas, "slot": tx.get("slot"), "block_time": tx.get("blockTime")}
        if meta.get("err") is not None:
            ledger.book_fill(order["order_id"], now, "FEE_ONLY", order["side"], sol_delta, usdc_delta, fee,
                             tx.get("slot"), facts["signature"], price, data, FAILED,
                             {"reason": "landed but failed on chain", "onchain_err": str(meta["err"])[:300],
                              "fee_lamports": fee})
            return FAILED
        anomaly = None
        persisting = facts.get("persisting_atas", [])
        expected_fee = fee + config.ATA_RENT_LAMPORTS * len(persisting)
        try:
            if fee > facts.get("network_fee", fee):
                raise Rejected("network fee %d above the verified %d" % (fee, facts["network_fee"]))
            check_deltas(request, facts["min_out"], deltas, expected_fee)
        except Rejected as exc:
            anomaly = str(exc)
        ledger.book_fill(order["order_id"], now, "SWAP", order["side"], sol_delta, usdc_delta, fee,
                         tx.get("slot"), facts["signature"], price, data, CONFIRMED,
                         {"fee_lamports": fee, "anomaly": anomaly})
        if anomaly:
            gates.remove_arm(self.paths.arm)
            ledger.event("anomaly_disarmed", {"order_id": order["order_id"], "problem": anomaly}, now)
        return CONFIRMED

    # cycles ---------------------------------------------------------------------------

    def _balances(self, rpc, wallet):
        _, accounts = rpc.multiple_accounts([wallet])
        lamports = accounts[0]["lamports"] if accounts[0] else 0
        _, tokens = rpc.token_accounts_by_owner(wallet)
        usdc = 0
        for _, account in tokens:
            token = parse_token_account(account["data"])
            if token.owner == wallet and token.mint == USDC.mint:
                usdc += token.amount
        return lamports, usdc

    def _decision(self, mandate, ledger, rpc, now):
        snapshot = self.snapshot_fn(mandate, now)
        candles = snapshot.get("candles") or []
        if not candles:
            raise Rejected("Snapshot has no candles")
        price = Decimal(str(candles[-1]["close"]))
        if not price.is_finite() or price <= 0:
            raise Rejected("Snapshot price is invalid")
        target = self.target_fn(mandate, snapshot)
        lamports, usdc = self._balances(rpc, mandate.wallet_pubkey)
        position, cost = ledger.position()
        today = ledger.realized_on(utc_day(now))
        decision = decide(mandate, target, price, position, cost, lamports, usdc, today)
        decision.update(target=target, price=str(price), as_of=snapshot.get("as_of"),
                        lamports=lamports, usdc=usdc, position_sol=position, cost_basis_usdc=cost,
                        today_realized_usdc=today)
        return decision

    def run_once(self):
        with wallet_locks(self.paths):
            ledger = self.ledger()
            summary = {"resolved": self.resolve()}
            state = self.state(ledger)
            summary["mode"] = state.mode
            if ledger.non_terminal():
                return dict(summary, action="WAIT", reason="an order is not final yet; no new order")
            if state.mode == "DISARMED":
                return dict(summary, action="NONE", reason=state.reason)
            if state.mode == "DRY_RUN":
                return dict(summary, **self._dry_cycle(state, ledger))
            return dict(summary, **self._live_cycle(state, ledger))

    def dry_run_once(self):
        with wallet_locks(self.paths):
            ledger = self.ledger()
            state = self.state(ledger)
            if state.mandate is None or state.mandate_problems:
                raise Rejected("A valid mandate is required for a dry run: %s"
                               % (state.mandate_error or "; ".join(state.mandate_problems)))
            if not state.gate("private_rpc")["ok"]:
                raise Rejected("A private RPC is required: %s" % state.gate("private_rpc")["detail"])
            return self._dry_cycle(state, ledger)

    def _dry_cycle(self, state, ledger):
        mandate, now = state.mandate, self.clock()
        jupiter, rpc = self._clients(mandate)
        record = {"mode": "DRY_RUN"}
        try:
            decision = self._decision(mandate, ledger, rpc, now)
            record["decision"] = decision
            side, amount = decision["side"], decision["amount"]
            if side is None:          # nothing to do: probe the path with a small order instead
                price = Decimal(decision["price"])
                buy = min(mandate.max_trade_usdc, decision["usdc"])
                sell = min(sol_for_usdc(mandate.max_trade_usdc, price),
                           decision["lamports"] - config.SOL_RESERVE_LAMPORTS)
                if buy >= config.MIN_TRADE_USDC_ATOMS:
                    side, amount = "BUY", buy
                elif usdc_value(max(sell, 0), price) >= config.MIN_TRADE_USDC_ATOMS:
                    side, amount = "SELL", sell
                else:
                    raise Rejected("Wallet needs at least 1 USDC or SOL above the reserve for a dry run")
                record["probe"] = True
            request = make_request(side, amount, mandate)
            order = jupiter.order(request, reference_price=decision["price"])
            verified = verify(order, rpc, mandate.wallet_pubkey)
            record.update(ok=True, side=side, amount=amount, request_id=order.request_id,
                          out_amount=order.out_amount, min_out=order.min_out, fee_bps=order.fee_bps,
                          priority_lamports=verified.priority_lamports, deltas=verified.deltas,
                          expected_fee=verified.expected_fee, jupiter_instruction=verified.swap,
                          inner_programs=list(verified.inner_programs),
                          last_valid_block_height=order.last_valid_block_height)
        except Exception as exc:     # a dry run never signs; record and carry on
            record.update(ok=False, error=_text(exc)[:500])
        ledger.record_dry_run(state.mandate_sha, record["ok"], record, now)
        return {"action": "DRY_RUN", "ok": record["ok"], "detail": record}

    def _live_cycle(self, state, ledger):
        mandate, now = state.mandate, self.clock()
        jupiter, rpc = self._clients(mandate)
        try:
            decision = self._decision(mandate, ledger, rpc, now)
        except Rejected as exc:
            return {"action": "NONE", "reason": "no decision: %s" % exc}
        if decision["side"] is None:
            return {"action": "NONE", "reason": decision["reason"], "decision": decision}
        try:
            request = make_request(decision["side"], decision["amount"], mandate)
        except Rejected as exc:
            return {"action": "NONE", "reason": "order not allowed: %s" % exc}
        order_id = ledger.create_intent(request.side, request.input_mint, request.output_mint, request.amount,
                                        state.mandate_sha, decision, now)
        self._inflight.add(order_id)
        try:
            outcome = self._execute(order_id, request, decision, state, ledger, jupiter, rpc)
        finally:
            self._inflight.discard(order_id)
        if outcome in (SUBMITTED, UNKNOWN):
            try:
                self.resolve()
            except Rejected:
                pass
            outcome = ledger.state_of(order_id)
        return {"action": "ORDER", "order_id": order_id, "state": outcome, "decision": decision}

    def _fail(self, ledger, order_id, reason):
        ledger.transition(order_id, FAILED, {"reason": str(reason)[:500]}, self.clock())
        return FAILED

    def _execute(self, order_id, request, decision, state, ledger, jupiter, rpc):
        mandate = state.mandate
        try:
            order = jupiter.order(request, reference_price=decision["price"])
            verified = verify(order, rpc, mandate.wallet_pubkey)
        except Exception as exc:     # before signing every failure is safe: nothing can land
            return self._fail(ledger, order_id, "rejected before signing: %s" % _text(exc))
        ledger.transition(order_id, VERIFIED, {
            "request_id": order.request_id, "wallet": mandate.wallet_pubkey,
            "out_amount": order.out_amount, "min_out": order.min_out,
            "fee_bps": order.fee_bps, "last_valid_block_height": order.last_valid_block_height,
            "unsigned_tx_b64": base64.b64encode(order.transaction).decode(),
            "message_sha256": verified.message_sha256, "priority_lamports": verified.priority_lamports,
            "network_fee": verified.network_fee, "expected_fee": verified.expected_fee,
            "persisting_atas": list(verified.persisting_atas), "swap": verified.swap,
            "inner_programs": list(verified.inner_programs), "pre": verified.pre,
            "simulated_deltas": verified.deltas, "block_height_at_verify": verified.block_height,
            "order_payload": order.payload}, self.clock())
        if not self._still_live(ledger, state.mandate_sha):
            return self._fail(ledger, order_id, "disarmed before signing")
        if self.clock() - order.received_at > config.ORDER_MAX_AGE_S:
            return self._fail(ledger, order_id, "order older than %ss at signing time" % config.ORDER_MAX_AGE_S)
        bundle = {"message_sha256": verified.message_sha256, "order_id": order_id, "side": request.side,
                  "input_mint": request.input_mint, "output_mint": request.output_mint,
                  "in_amount": request.amount, "min_out": order.min_out}
        try:
            signature = self.signer.sign(verified.message_bytes, bundle)
            self.signature_verifier(mandate.wallet_pubkey, verified.message_bytes, signature)
            tx = parse_transaction(order.transaction)
            signed = with_signature(tx, 0, signature).serialize()
            if parse_transaction(signed).message.raw != verified.message_bytes:
                raise Rejected("signed transaction does not carry the verified message")
        except Exception as exc:     # no signature stored or sent: nothing can land
            return self._fail(ledger, order_id, "not signed: %s" % _text(exc))
        signature58 = b58encode(signature)
        ledger.transition(order_id, SIGNED, {"signature": signature58,
                                             "signed_tx_b64": base64.b64encode(signed).decode()}, self.clock())
        if not self._still_live(ledger, state.mandate_sha):
            # not sent; kept non-terminal anyway so no new order is placed until it provably expired
            ledger.transition(order_id, UNKNOWN, {"reason": "disarmed after signing; NOT sent"}, self.clock())
            return UNKNOWN
        try:
            answer = jupiter.execute(signed, order.request_id, signature58)
        except Exception as exc:                          # F13: whatever happened, the outcome is unknown
            answer = ExecuteAnswer("UNKNOWN", None, "execute error: %s" % type(exc).__name__, None)
        new_state = SUBMITTED if answer.outcome == "ACCEPTED" else UNKNOWN
        ledger.transition(order_id, new_state, {"execute_http": answer.http_status, "execute_detail": answer.detail,
                                                "execute_payload": answer.payload}, self.clock())
        return new_state


# arming -------------------------------------------------------------------------------

def arm(paths, mode, overrides, ask, interactive, now, ledger, gate_options=None, out=print):
    """Create the arm file after typed confirmation. Returns the arm record."""
    if not interactive:
        raise Rejected("arm must be run by a person in an interactive terminal")
    state = gates.evaluate(paths, now, ledger, **(gate_options or {}))
    for name in overrides:
        if name in gates.NEVER_OVERRIDE:
            raise Rejected("%s can never be overridden" % name)
        if name not in gates.OVERRIDABLE:
            raise Rejected("unknown gate %s" % name)
    if state.mandate is None or state.mandate_problems:
        raise Rejected("mandate not valid: %s" % (state.mandate_error or "; ".join(state.mandate_problems)))
    if not state.gate("private_rpc")["ok"]:
        raise Rejected("private_rpc gate failing: %s" % state.gate("private_rpc")["detail"])
    needed = []
    if mode == "LIVE":
        failing = [g["name"] for g in state.gates if not g["ok"]]
        missing = [g for g in failing if g not in overrides]
        if missing:
            raise Rejected("gates failing without --override: %s" % ", ".join(missing))
        needed = sorted(g for g in failing if g in overrides)
    elif mode != "DRY_RUN":
        raise Rejected("mode must be LIVE or DRY_RUN")
    m = state.mandate
    out("Mandate %s (sha256 %s...)" % (paths.mandate, state.mandate_sha[:12]))
    out("  wallet %s, max trade %s USDC, max position %s USDC, daily loss %s USDC, slippage %d bps"
        % (m.wallet_pubkey, m.max_trade_usdc / 1e6, m.max_position_usdc / 1e6, m.daily_loss_limit_usdc / 1e6,
           m.max_slippage_bps))
    out("  strategy %s %s, rpc host %s, expires %s" % (m.strategy, m.params_json, m.rpc_host,
                                                       time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(m.expires_at))))
    for gate in state.gates:
        out("  gate %-16s %s  %s" % (gate["name"], "OK  " if gate["ok"] else "FAIL", gate["detail"]))
    if mode == "LIVE":
        out("LIVE means REAL MONEY: the bot will sign and send swaps from this wallet.")
    phrase = "ARM %s %s" % (mode, m.wallet_pubkey[:8])
    if ask("Type exactly '%s' to continue: " % phrase).strip() != phrase:
        raise Rejected("confirmation phrase did not match; not armed")
    if needed:
        second = "OVERRIDE %s" % ",".join(needed)
        out("You are overriding failing gates: %s. This is recorded in the ledger." % ", ".join(needed))
        if ask("Type exactly '%s' to override: " % second).strip() != second:
            raise Rejected("override phrase did not match; not armed")
    record = {"mode": mode, "mandate_sha256": state.mandate_sha, "wallet_pubkey": m.wallet_pubkey,
              "armed_at": now, "overrides": needed}
    gates.bind_wallet(paths, m.wallet_pubkey, now)          # refuses if another ledger owns the wallet
    gates.write_arm(paths.arm, record)
    ledger.event("arm", record, now)
    for name in needed:
        ledger.event("override", {"gate": name, "detail": state.gate(name)["detail"],
                                  "mandate_sha256": state.mandate_sha}, now)
    return record


def disarm(paths, now, ledger=None):
    removed = gates.remove_arm(paths.arm)
    if ledger is not None:
        try:
            ledger.event("disarm", {"removed": removed}, now)
        except Exception:      # the kill switch must never fail because of the ledger
            pass
    return removed


def force_expire(engine, order_id, ask, interactive):
    """Operator escape hatch for an order the resolver keeps UNKNOWN (e.g. balances changed).

    Still requires chain proof that it can no longer land (finalized height past
    lastValidBlockHeight + margin and no status). If it DID land, the ledger will
    miss that fill: check the wallet history yourself first.
    """
    if not interactive:
        raise Rejected("force-expire must be run by a person in an interactive terminal")
    ledger = engine.ledger()
    order = ledger.order(order_id)
    if order is None or order["state"] not in (UNKNOWN, SUBMITTED):
        raise Rejected("order is not UNKNOWN/SUBMITTED")
    mandate, error = mandate_mod.load(engine.paths.mandate)
    if mandate is None:
        raise Rejected("a readable mandate (rpc_url) is needed: %s" % error)
    rpc = Rpc(mandate.rpc_url, engine._http(mandate))
    _, height = rpc.epoch_info("finalized")
    if height <= order["facts"]["last_valid_block_height"] + config.EXPIRY_MARGIN_BLOCKS:
        raise Rejected("the transaction can still land; wait")
    if rpc.signature_status(order["facts"]["signature"]) is not None:
        raise Rejected("the RPC knows this signature; run resolve instead")
    phrase = "EXPIRE %s" % order_id[:8]
    if ask("I checked the wallet history by hand. Type exactly '%s': " % phrase).strip() != phrase:
        raise Rejected("phrase did not match")
    ledger.transition(order_id, EXPIRED, {"reason": "force-expired by operator", "finalized_block_height": height},
                      engine.clock())
    ledger.event("force_expire", {"order_id": order_id}, engine.clock())
    return [(order_id, EXPIRED)]
