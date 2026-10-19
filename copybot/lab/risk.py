"""Risk and failure controls for simulated strategies (ENGINE_PROPOSAL.md §5, stage S4).

Circuit breakers PAUSE a strategy (lifecycle PAPER_TRADING -> PAUSED) or put the whole lab in FAIL_CLOSED. They never
reject a strategy: rejection only happens through the registered acceptance/rejection criteria. A pause is lifted
only through the lifecycle's human approval (PAUSED -> PAPER_TRADING with committed revalidation evidence), never
because a later simulated trade would have been profitable. Signals seen during a pause are logged as counterfactual
and excluded from any resume decision.
"""
from __future__ import annotations

import json
import time

from lab import lifecycle

GLOBAL = "GLOBAL"
DEFAULTS = {"consecutive_losses": 2, "max_drawdown": 0.10, "data_max_age_s": 60, "spread_max_mult": 3.0,
            "spread_strikes": 3, "spread_window_s": 86400}
ACTOR = "system:risk"


def rules_for(db, exp_id):
    if exp_id.startswith(("SHADOW_", "FWD_")):        # amendment 7 section 1: drawdown, data and spread only
        return {**DEFAULTS, "consecutive_losses": None}
    r = db.one("SELECT spec_json FROM experiments WHERE exp_id=? ORDER BY version DESC LIMIT 1", exp_id)
    spec = json.loads(r["spec_json"] or "{}") if r else {}
    return {**DEFAULTS, **(spec.get("risk") or {})}


class Risk:
    def __init__(self, db, now=time.time):
        self.db, self.now = db, now

    # ---------- state ----------
    def _last(self, exp_id, actions):
        q = f"SELECT * FROM risk_events WHERE exp_id=? AND action IN ({','.join('?' * len(actions))}) ORDER BY id DESC LIMIT 1"
        return self.db.one(q, exp_id, *actions)

    def paused(self, exp_id):
        r = self._last(exp_id, ("PAUSE", "CLEAR"))
        return r is not None and r["action"] == "PAUSE"

    def fail_closed(self):
        r = self._last(GLOBAL, ("FAIL_CLOSED", "CLEAR"))
        return r is not None and r["action"] == "FAIL_CLOSED"

    def warming(self, exp_id):
        r = self._last(exp_id, ("WARMUP", "WARMUP_DONE"))
        return r is not None and r["action"] == "WARMUP"

    def start_warmup(self, exp_id, detail="restart: entries blocked until fresh data passes the guards"):
        if not self.warming(exp_id):
            with self.db.tx():
                self._event(exp_id, "restart_warmup", None, None, "WARMUP", detail)

    def observe_book(self, exp_id, book):
        """A fresh, valid book ends the post-restart warm-up (logged). Stale or crossed data does not."""
        if not self.warming(exp_id) or book is None or book.crossed():
            return False
        lim = rules_for(self.db, exp_id)["data_max_age_s"]
        if self.now() - book.ts > lim:
            return False
        with self.db.tx():
            self._event(exp_id, "restart_warmup", self.now() - book.ts, lim, "WARMUP_DONE", "fresh data passed guards")
        return True

    def last_clear_ts(self, exp_id):
        r = self._last(exp_id, ("CLEAR",))
        return r["ts"] if r else 0

    def _event(self, exp_id, rule, value, threshold, action, detail, actor=ACTOR):
        self.db.append("risk_events", exp_id=exp_id, ts=int(self.now()), rule=rule, value=value, threshold=threshold,
                       action=action, detail=detail, actor=actor)
        self.db.event(f"risk.{action.lower()}", actor, None if exp_id == GLOBAL else exp_id,
                      {"rule": rule, "value": value, "threshold": threshold, "detail": detail})

    # ---------- entry gate ----------
    def _shadow_ok(self, ledger):
        """PROTOCOL v3 amendment 3: a SHADOW_ ledger may trade only while its experiment is in OBSERVATION and a
        human-started shadow is active. Amendment 7: a FWD_ ledger only while its human-started forward test with
        pinned artifacts is active."""
        if ledger.startswith("FWD_"):
            from lab.paper import forward_active
            return forward_active(self.db, ledger[len("FWD_"):])
        base = ledger[len("SHADOW_"):]
        r = self.db.one("SELECT kind, actor FROM events WHERE kind IN ('shadow.approved','shadow.stopped') AND exp_id=? "
                        "ORDER BY id DESC LIMIT 1", base)
        return bool(r and r["kind"] == "shadow.approved" and r["actor"].startswith("human:")
                    and lifecycle.state(self.db, base) == "OBSERVATION")

    def entry_allowed(self, exp_id, reduce_only, book):
        if exp_id.startswith(("SHADOW_", "FWD_")):
            if not self._shadow_ok(exp_id) and not reduce_only:
                return False, ("forward test is not active (needs a human start and the pinned artifacts)"
                               if exp_id.startswith("FWD_") else
                               "shadow trading is not active (needs OBSERVATION and a human start)")
            st = "PAPER_TRADING"                              # every other risk rule below applies unchanged
        else:
            st = lifecycle.state(self.db, exp_id)
            if reduce_only and st in lifecycle.FINAL:
                st = "PAUSED"                                 # amendment 4: positions are closed, never forgotten
        if st not in ("PAPER_TRADING", "PAUSED"):
            return False, f"strategy is {st}; only PAPER_TRADING strategies simulate orders"
        if book is None:
            return self.block(exp_id, "data_missing", None, None, "no order book")
        age = self.now() - book.ts
        lim = rules_for(self.db, exp_id)["data_max_age_s"]
        if age > lim:
            return self.block(exp_id, "data_stale", age, lim, f"book is {age:.0f}s old")
        if book.crossed():
            return self.block(exp_id, "data_inconsistent", None, None, "crossed or empty book")
        if not reduce_only and self.fail_closed():
            return False, "lab is FAIL_CLOSED"
        if not reduce_only and self.warming(exp_id):
            return False, "warming up after a restart"
        if not reduce_only and (st == "PAUSED" or self.paused(exp_id)):
            return False, "strategy is paused"
        if not reduce_only:
            from lab import promotion                         # amendment 4a: one gate for every new exposure
            ok, why = promotion.exposure_allowed(self.db, exp_id, self.now())
            if not ok:
                return False, f"not authorized: {why}"
        return True, "ok"

    def block(self, exp_id, rule, value, threshold, detail):
        with self.db.tx():
            self._event(exp_id, rule, value, threshold, "BLOCK", detail)
        return False, f"blocked: {detail}"

    # ---------- breakers ----------
    def pause(self, exp_id, rule, value, threshold, detail, cancel_open=None):
        if self.paused(exp_id):
            return
        with self.db.tx():
            self._event(exp_id, rule, value, threshold, "PAUSE", detail)
        if cancel_open:
            cancel_open(exp_id, f"paused by {rule}")
        if lifecycle.state(self.db, exp_id) == "PAPER_TRADING":
            lifecycle.auto_transition(self.db, exp_id, "PAUSED", ACTOR, f"circuit breaker {rule}: {detail}",
                                      {"rule": rule, "value": value, "threshold": threshold})

    def trip_fail_closed(self, rule, detail):
        if self.fail_closed():
            return
        with self.db.tx():
            self._event(GLOBAL, rule, None, None, "FAIL_CLOSED", detail)

    def fail_closed_causes(self):
        """The conditions that trip FAIL_CLOSED and are not re-checked within seconds by the fleet: broken hash chains
        or missing append-only triggers and cited evidence that does not resolve (checked at start only), an
        overfilled order (checked at start and at that ledger's next fill), and a started ledger that does not
        reconcile. Returns problems (empty = the cause is gone)."""
        from lab import legacy
        from lab.paper import PaperEngine
        out = []
        chains, triggers = self.db.verify()
        broken = {t: b for t, (_, b) in chains.items() if b is not None}
        if broken or not triggers:
            out.append(f"integrity: broken hash chains {broken or 'none'}" + ("" if triggers else
                                                                            ", append-only triggers missing"))
        bad_ev = legacy.verify_evidence(self.db)
        if bad_ev:
            out.append(f"integrity: {len(bad_ev)} cited evidence file(s) do not resolve in git")
        over = self.db.q("SELECT o.order_id FROM sim_orders o WHERE o.qty + 1e-9 < (SELECT COALESCE(SUM(qty),0) FROM "
                         "sim_fills f WHERE f.order_id=o.order_id)")
        if over:
            out.append(f"overfill: {', '.join(r[0] for r in over[:5])}")
        eng = PaperEngine(self.db)
        bad = [r[0] for r in self.db.q("SELECT DISTINCT exp_id FROM events WHERE kind='paper.started'")
               if not eng.reconcile(r[0])["ok"]]
        if bad:
            out.append(f"reconciliation fails for {', '.join(bad)}")
        return out

    def clear_fail_closed(self, actor, reason):
        """Only a human, and only once the cause is gone (fail_closed_causes): a CLEAR never lets the lab trade on a
        broken registry, an overfill or an unreconciled ledger."""
        if not actor.startswith("human:"):
            raise lifecycle.LifecycleError("only a human can clear FAIL_CLOSED")
        if not reason or len(reason) < 10:
            raise lifecycle.LifecycleError("a reason is required")
        causes = self.fail_closed_causes()
        if causes:
            raise lifecycle.LifecycleError("FAIL_CLOSED stays until the cause is gone: " + "; ".join(causes))
        with self.db.tx():
            self._event(GLOBAL, "manual_clear", None, None, "CLEAR", reason, actor)

    def record_resume(self, exp_id, actor):
        """Log the CLEAR that pairs with a human-approved PAUSED -> PAPER_TRADING transition."""
        last = self.db.one("SELECT to_state, actor FROM transitions WHERE exp_id=? ORDER BY id DESC LIMIT 1", exp_id)
        if not last or last["to_state"] != "PAPER_TRADING" or not last["actor"].startswith("human:"):
            raise lifecycle.LifecycleError("resume requires the human-approved lifecycle transition first")
        with self.db.tx():
            self._event(exp_id, "revalidated", None, None, "CLEAR", "resumed after approved revalidation", actor)

    def resume_simulated(self, ledger, actor, reason):
        """Amendment 7 section 1: only a human resumes a paused SHADOW_ or FWD_ ledger (a CLEAR with the reason)."""
        if not ledger.startswith(("SHADOW_", "FWD_")):
            raise lifecycle.LifecycleError("only simulated SHADOW_/FWD_ ledgers resume this way; an approved "
                                           "strategy resumes through its human-approved transition")
        if not actor.startswith("human:"):
            raise lifecycle.LifecycleError("only a human can resume a simulated ledger")
        if not reason or len(reason.strip()) < 10:
            raise lifecycle.LifecycleError("a reason of at least 10 characters is required")
        with self.db.tx():                             # BEGIN IMMEDIATE: two resumes at once record one CLEAR
            if not self.paused(ledger):
                return False
            dd = self.db.one("SELECT drawdown FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", ledger)
            lim = rules_for(self.db, ledger)["max_drawdown"]
            if dd and dd["drawdown"] >= lim:           # the unchanged breaker would pause it again at the next mark
                raise lifecycle.LifecycleError(f"drawdown {dd['drawdown']:.2%} is still at or above {lim:.0%} of the "
                                               "running peak; resume once it is below")
            self._event(ledger, "manual_resume", None, None, "CLEAR", reason.strip()[:300], actor)
        return True

    def after_trade_closed(self, exp_id, trades, cancel_open=None):
        """trades: [(close_ts, pnl)] of completed round trips. Counts only trades after the last CLEAR."""
        if exp_id.startswith(("SHADOW_", "FWD_")):       # simulated: drawdown, data, spread only (amendment 7)
            return 0
        lim = rules_for(self.db, exp_id)["consecutive_losses"]
        since = self.last_clear_ts(exp_id)
        streak = 0
        for ts, pnl in reversed([t for t in trades if t[0] >= since]):
            if pnl < 0:
                streak += 1
            else:
                break
        if streak >= lim:
            with self.db.tx():
                self._event(exp_id, "consecutive_losses", streak, lim, "WARN",
                            "two losses are not evidence the edge is gone; temporary pause only")
            self.pause(exp_id, "consecutive_losses", streak, lim, f"{streak} losing trades in a row", cancel_open)
        return streak

    def after_equity(self, exp_id, drawdown, cancel_open=None):
        lim = rules_for(self.db, exp_id)["max_drawdown"]
        if drawdown >= lim:
            self.pause(exp_id, "max_drawdown", drawdown, lim, f"drawdown {drawdown:.2%}", cancel_open)

    def after_spread(self, exp_id, spread, expected, cancel_open=None):
        r = rules_for(self.db, exp_id)
        if expected and spread > r["spread_max_mult"] * expected:
            with self.db.tx():
                self._event(exp_id, "spread_anomaly", spread, r["spread_max_mult"] * expected, "INVESTIGATE",
                            "spread far above the registered model")
            n = self.db.one("SELECT COUNT(*) FROM risk_events WHERE exp_id=? AND rule='spread_anomaly' AND "
                            "action='INVESTIGATE' AND ts>=?", exp_id, int(self.now()) - r["spread_window_s"])[0]
            if n >= r["spread_strikes"]:
                self.pause(exp_id, "spread_anomaly", n, r["spread_strikes"], f"{n} spread anomalies", cancel_open)

    def check_exposure(self, exp_id, claimed, ledger_positions):
        """Compare what a strategy believes it holds with the fill ledger; any mismatch fails the lab closed."""
        keys = set(claimed) | set(ledger_positions)
        diff = {k: (claimed.get(k, 0.0), ledger_positions.get(k, 0.0)) for k in keys
                if abs(claimed.get(k, 0.0) - ledger_positions.get(k, 0.0)) > 1e-9}
        if diff:
            self.trip_fail_closed("exposure_mismatch", f"{exp_id}: {diff}")
            return False
        return True
