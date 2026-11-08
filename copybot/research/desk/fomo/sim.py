"""SYNTHETIC execution simulator for the fomo / "Grok Bot" 30-second copy-trading claim (director order 56).

DESIGN ONLY. No network, no market data, no live trading, no keys. Every path is synthetic.
Standard library only; deterministic; pure functions over plain dicts.

Model in one paragraph: a pool (constant-product AMM, or a pump.fun-style bonding curve that can
migrate to an AMM or fail) is replayed event by event. The leader and the follower are separate
positions. The follower enters at the pool state at leader_time + delay_s, AFTER every swap in
between (the leader's own buy included). The follower's buy and sell move the pool. Exits are
filled at an executable sell quote (amount out for the full position after fees), never at a mid
price. Missing observations are never interpolated. Every input path gets exactly one output row.

Units: SOL and tokens. Prices are SOL per token. "mid" is reserve_sol / reserve_tokens and is used
only as a trigger/diagnostic (the video's TP trigger is a market-cap = mid-price multiple).
"""
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass

EXIT_REASONS = ("TP_10X", "TIME_STOP", "LEADER_SELL", "POOL_DEAD", "RUG", "NOT_EXECUTABLE", "MISSING_PRICE")
STATUSES = ("CLOSED", "NOT_FILLED", "MARKED_MISSING", "INVALID_INPUT")
EVENT_TYPES = ("swap", "leader_buy", "leader_sell", "rug", "pool_dead", "migrate", "missing", "tick")
TP_TRIGGERS = ("price", "executable")

# pump.fun-style curve constants as publicly described. ASSUMPTION, not verified on-chain here.
PUMPFUN_CURVE = {
    "virtual_sol": 30.0,
    "virtual_tokens": 1_073_000_000.0,
    "real_tokens": 793_100_000.0,
    "migration_tokens": 206_900_000.0,
    "migration_fee_sol": 0.0,
}
TOKEN_SUPPLY = 1_000_000_000.0  # pump.fun-style total supply; used only to express mid as market cap

# Fee scenario ported from the lab's old CopyBot (git 586fcbb: copybot/config.json). ONE scenario, not truth.
LEGACY_COPYBOT_FEES = {
    "dex_fee_frac": 0.005,
    "pumpfun_fee_frac": 0.005,
    "bot_fee_frac": 0.01,
    "mev_frac": 0.005,
    "network_fee_sol": 0.0015,
    "priority_fee_sol": 0.0,
}

_EPS = 1e-12


# ---------------------------------------------------------------- pools

class AMMPool:
    """Constant product x*y=k. Fee is taken from the INPUT amount. lp_fee_share of the fee stays in the
    pool (k grows); the rest leaves the pool (protocol). ASSUMPTION: default 1.0 (all fee to LPs)."""

    kind = "amm"

    def __init__(self, sol, tokens, fee_frac, lp_fee_share=1.0):
        if sol < 0 or tokens < 0 or not 0 <= fee_frac < 1 or not 0 <= lp_fee_share <= 1:
            raise ValueError("bad AMM pool spec")
        self.sol = float(sol)
        self.tokens = float(tokens)
        self.fee_frac = float(fee_frac)
        self.lp_fee_share = float(lp_fee_share)
        self.dead = False
        self.rugged = False
        self.complete = False

    def clone(self):
        c = AMMPool(self.sol, self.tokens, self.fee_frac, self.lp_fee_share)
        c.dead, c.rugged = self.dead, self.rugged
        return c

    def tradable(self):
        return not self.dead

    def k(self):
        return self.sol * self.tokens

    def mid_price(self):
        return self.sol / self.tokens if self.tokens > 0 else math.inf

    def quote_buy(self, sol_in):
        fee = sol_in * self.fee_frac
        eff = sol_in - fee
        den = self.sol + eff
        out = self.tokens * eff / den if den > 0 else 0.0
        return {"tokens_out": out, "sol_used": sol_in, "fee_sol": fee}

    def quote_sell(self, tokens_in):
        eff = tokens_in * (1.0 - self.fee_frac)
        den = self.tokens + eff
        out = self.sol * eff / den if den > 0 else 0.0
        den0 = self.tokens + tokens_in
        nofee = self.sol * tokens_in / den0 if den0 > 0 else 0.0
        return {"sol_out": out, "fee_sol": nofee - out, "gross_sol": nofee}

    def buy(self, sol_in):
        q = self.quote_buy(sol_in)
        self.sol += sol_in - q["fee_sol"] * (1.0 - self.lp_fee_share)
        self.tokens -= q["tokens_out"]
        return q

    def sell(self, tokens_in):
        q = self.quote_sell(tokens_in)
        self.tokens += tokens_in * (1.0 - self.fee_frac * (1.0 - self.lp_fee_share))
        self.sol -= q["sol_out"]
        return q


class BondingCurve:
    """pump.fun-style curve on virtual reserves (vS*vT=k). Fee on the SOL side, paid out of the curve.
    When the real token reserve is sold out the curve is COMPLETE and closed: no trading until a
    'migrate' event moves trading to an AMM (success) or kills it (failure)."""

    kind = "curve"

    def __init__(self, virtual_sol, virtual_tokens, real_tokens, fee_frac, migration_tokens, migration_fee_sol=0.0):
        if virtual_sol <= 0 or virtual_tokens <= real_tokens or real_tokens <= 0 or not 0 <= fee_frac < 1:
            raise ValueError("bad curve spec")
        self.vs = float(virtual_sol)
        self.vt = float(virtual_tokens)
        self.real_tokens = float(real_tokens)
        self.real_sol = 0.0
        self.fee_frac = float(fee_frac)
        self.migration_tokens = float(migration_tokens)
        self.migration_fee_sol = float(migration_fee_sol)
        self._t0 = float(real_tokens)
        self.dead = False
        self.rugged = False
        self.complete = False

    def clone(self):
        c = BondingCurve(self.vs, self.vt, self.real_tokens, self.fee_frac, self.migration_tokens, self.migration_fee_sol)
        c.real_sol, c._t0, c.dead, c.rugged, c.complete = self.real_sol, self._t0, self.dead, self.rugged, self.complete
        return c

    def tradable(self):
        return not self.dead and not self.complete

    def k(self):
        return self.vs * self.vt

    def mid_price(self):
        return self.vs / self.vt

    def quote_buy(self, sol_in):
        f = self.fee_frac
        eff = sol_in * (1.0 - f)
        out = self.vt * eff / (self.vs + eff)
        used = sol_in
        if out > self.real_tokens:  # fills only up to the remaining curve tokens
            out = self.real_tokens
            eff = self.vs * self.vt / (self.vt - out) - self.vs
            used = eff / (1.0 - f)
        return {"tokens_out": out, "sol_used": used, "fee_sol": used - eff, "eff": eff}

    def quote_sell(self, tokens_in):
        raw = min(self.vs * tokens_in / (self.vt + tokens_in), self.real_sol)
        fee = raw * self.fee_frac
        return {"sol_out": raw - fee, "fee_sol": fee, "gross_sol": raw}

    def buy(self, sol_in):
        q = self.quote_buy(sol_in)
        self.vs += q["eff"]
        self.vt -= q["tokens_out"]
        self.real_sol += q["eff"]
        self.real_tokens -= q["tokens_out"]
        if self.real_tokens <= self._t0 * 1e-12:
            self.real_tokens = 0.0
            self.complete = True
        return q

    def sell(self, tokens_in):
        q = self.quote_sell(tokens_in)
        self.vs -= q["gross_sol"]
        self.vt += tokens_in
        self.real_sol -= q["gross_sol"]
        self.real_tokens += tokens_in
        return q


# ---------------------------------------------------------------- params

@dataclass(frozen=True)
class Params:
    """time_stop_s, bot_fee_frac, slippage_tolerance and follow_sells are UNKNOWN for fomo and have no default."""
    size_sol: float
    time_stop_s: float
    bot_fee_frac: float
    slippage_tolerance: float
    follow_sells: bool
    delay_s: float = 30.0
    tp_multiple: float = 10.0
    tp_trigger: str = "price"
    dex_fee_frac: float = 0.0025      # ASSUMPTION (PumpSwap/Raydium-like)
    pumpfun_fee_frac: float = 0.01    # ASSUMPTION (historic pump.fun curve fee)
    priority_fee_sol: float = 0.0001  # ASSUMPTION
    network_fee_sol: float = 0.000005  # Solana base fee 5000 lamports per signature
    mev_frac: float = 0.0
    lp_fee_share: float = 1.0
    legacy_floor: bool = False

    def __post_init__(self):
        if self.size_sol <= 0 or self.time_stop_s < 0 or self.delay_s < 0 or self.tp_multiple <= 1:
            raise ValueError("bad size/time_stop/delay/tp")
        if self.tp_trigger not in TP_TRIGGERS:
            raise ValueError("tp_trigger must be 'price' or 'executable'")
        for name in ("bot_fee_frac", "mev_frac", "dex_fee_frac", "pumpfun_fee_frac"):
            if not 0 <= getattr(self, name) < 1:
                raise ValueError(name)
        if self.bot_fee_frac + self.mev_frac >= 1 or self.slippage_tolerance < 0:
            raise ValueError("bad fee/slippage")
        if self.priority_fee_sol < 0 or self.network_fee_sol < 0:
            raise ValueError("bad tx fee")


def _params(p):
    return p if isinstance(p, Params) else Params(**p)


def make_venue(spec, prm):
    kind = spec.get("kind")
    if kind == "amm":
        return AMMPool(spec["sol"], spec["tokens"], prm.dex_fee_frac, spec.get("lp_fee_share", prm.lp_fee_share))
    if kind == "curve":
        c = dict(PUMPFUN_CURVE)
        c.update({k: v for k, v in spec.items() if k != "kind"})
        return BondingCurve(c["virtual_sol"], c["virtual_tokens"], c["real_tokens"], prm.pumpfun_fee_frac,
                            c["migration_tokens"], c["migration_fee_sol"])
    raise ValueError("pool kind must be 'amm' or 'curve'")


# ---------------------------------------------------------------- world replay

class _World:
    def __init__(self, venue, prm):
        self.venue = venue
        self.prm = prm
        self.holdings = {}
        self.leader_tokens = 0.0
        self.leader_proceeds = 0.0
        self.leader_cost = 0.0
        self.leader_fill = None
        self.leader_sells = []  # (t, tokens, sol_out) of executed leader sells
        self.others_rejected = 0

    def tx_fees(self):
        return self.prm.priority_fee_sol + self.prm.network_fee_sol

    def apply(self, ev):
        typ, v = ev["type"], self.venue
        if typ == "swap":
            if not v.tradable():
                self.others_rejected += 1
                return
            actor = ev.get("actor", "_anon")
            if ev["side"] == "buy":
                q = v.buy(float(ev["size"]))
                self.holdings[actor] = self.holdings.get(actor, 0.0) + q["tokens_out"]
                if q["sol_used"] < float(ev["size"]) - _EPS:
                    self.others_rejected += 1
            elif ev["side"] == "sell":
                n = self.holdings.get(actor, 0.0) if ev["size"] == "all" else float(ev["size"])
                if n > 0:
                    v.sell(n)
                    self.holdings[actor] = self.holdings.get(actor, 0.0) - n
            else:
                raise ValueError("swap side must be buy or sell")
        elif typ == "leader_buy":
            if not v.tradable():
                return
            q = v.buy(float(ev["size_sol"]))
            if q["tokens_out"] <= 0:
                return
            self.leader_tokens = q["tokens_out"]
            self.leader_cost = q["sol_used"] + self.tx_fees()
            self.leader_fill = {"t": ev["t"], "size_sol": q["sol_used"], "tokens": q["tokens_out"],
                                "entry_price": q["sol_used"] / q["tokens_out"], "fee_sol": q["fee_sol"]}
        elif typ == "leader_sell":
            n = self.leader_tokens * float(ev.get("frac", 1.0))
            if n <= 0 or not v.tradable():
                return
            q = v.sell(n)
            self.leader_tokens -= n
            self.leader_proceeds += q["sol_out"] - self.tx_fees()
            self.leader_sells.append((ev["t"], n, q["sol_out"]))
        elif typ == "rug":
            frac = float(ev.get("frac", 1.0))
            if isinstance(v, AMMPool):
                v.sol *= (1.0 - frac)
                v.tokens *= (1.0 - frac)
            else:
                v.dead = True
            v.rugged = True
        elif typ == "pool_dead":
            v.dead = True
        elif typ == "migrate":
            if not isinstance(v, BondingCurve):
                raise ValueError("migrate needs a curve")
            if ev.get("success", True) and not v.dead:
                self.venue = AMMPool(max(v.real_sol - v.migration_fee_sol, 0.0), v.migration_tokens,
                                     self.prm.dex_fee_frac, self.prm.lp_fee_share)
            else:
                v.complete = True
                v.dead = True
        elif typ in ("missing", "tick"):
            return
        else:
            raise ValueError("unknown event type %r" % typ)

    def leader_mark(self):
        """Executable value of the leader's remaining tokens on the current state (hypothetical, not applied)."""
        v, n = self.venue, self.leader_tokens
        if n <= 0 or not v.tradable():
            return 0.0
        return v.quote_sell(n)["sol_out"] - self.tx_fees()


def _normalise_events(path):
    evs = []
    for i, ev in enumerate(path.get("events", [])):
        if ev.get("type") not in EVENT_TYPES:
            raise ValueError("unknown event type %r" % ev.get("type"))
        e = dict(ev)
        e["t"] = float(ev["t"])
        evs.append((e["t"], i, e))
    evs.sort(key=lambda x: (x[0], x[1]))
    return [e for _, _, e in evs]


def _cost_keys():
    return ("entry_bot_fee_sol", "entry_mev_sol", "entry_dex_fee_sol", "entry_priority_fee_sol", "entry_network_fee_sol",
            "exit_dex_fee_sol", "exit_bot_fee_sol", "exit_mev_sol", "exit_priority_fee_sol", "exit_network_fee_sol")


# ---------------------------------------------------------------- the trade

def simulate_trade(path, params):
    """Replay one synthetic path. Returns one result row (a JSON-safe dict). Raises ValueError on bad input."""
    prm = _params(params)
    events = _normalise_events(path)
    leaders = [e for e in events if e["type"] == "leader_buy"]
    if len(leaders) != 1:
        raise ValueError("a path needs exactly one leader_buy")
    lead_ev = leaders[0]
    t_lead = lead_ev["t"]
    t_entry = t_lead + prm.delay_s
    last_t = events[-1]["t"]
    end_t = max(float(path.get("end_t", last_t)), last_t)
    gaps = [(e["t"], float(e["until"])) for e in events if e["type"] == "missing"]
    world = _World(make_venue(path["pool"], prm), prm)
    costs = {k: 0.0 for k in _cost_keys()}
    row = {
        "path_id": path.get("id"), "status": None, "exit_reason": None, "not_executable_reason": None,
        "params": asdict(prm), "t_signal": t_lead, "t_entry": t_entry, "t_exit": None,
        "leader": None, "follower": None, "costs": costs,
        "gross_pnl_sol": 0.0, "net_pnl_sol": 0.0, "gross_pct": 0.0, "net_pct": 0.0, "cost_basis_sol": 0.0,
        "total_costs_sol": 0.0, "gap_net_pct": None,
        "max_mid_multiple_seen": None, "max_exec_multiple_seen": None, "legacy_floor_applied": False,
    }
    idx = 0

    def advance(t_incl):
        nonlocal idx
        while idx < len(events) and events[idx]["t"] <= t_incl:
            world.apply(events[idx])
            idx += 1

    # phase 1: everything up to and including the leader's buy (signal time)
    while events[idx] is not lead_ev:
        world.apply(events[idx])
        idx += 1
    mid_pre_leader = world.venue.mid_price() if world.venue.tradable() else None
    world.apply(lead_ev)
    idx += 1
    if world.leader_fill is None:
        row.update(status="NOT_FILLED", exit_reason="NOT_EXECUTABLE", not_executable_reason="leader_not_executable")
        return row
    row["leader"] = dict(world.leader_fill, mid_before=mid_pre_leader)

    bot_in = prm.size_sol * prm.bot_fee_frac
    mev_in = prm.size_sol * prm.mev_frac
    swap_in = prm.size_sol - bot_in - mev_in
    tx = prm.priority_fee_sol + prm.network_fee_sol
    v = world.venue
    signal_q = v.quote_buy(swap_in) if v.tradable() else None

    # phase 2: every event with t <= leader_time + delay, then the follower's buy
    advance(t_entry)
    v = world.venue
    reason = None
    if signal_q is None or signal_q["tokens_out"] <= 0:
        reason = "no_quote_at_signal"
    elif v.rugged:
        reason = "rugged"
    elif v.dead:
        reason = "pool_dead"
    elif v.complete:
        reason = "curve_complete"
    else:
        q_try = v.quote_buy(swap_in)
        quote_px = swap_in / signal_q["tokens_out"]
        if q_try["tokens_out"] <= 0:
            reason = "no_liquidity"
        elif q_try["sol_used"] < swap_in - _EPS:
            reason = "curve_capacity"
        elif swap_in / q_try["tokens_out"] > quote_px * (1.0 + prm.slippage_tolerance) * (1.0 + _EPS):
            reason = "slippage"
    if reason is not None:
        # a failed Solana transaction still pays base + priority fee (ASSUMPTION: no bot fee on failure)
        costs["entry_priority_fee_sol"] = prm.priority_fee_sol
        costs["entry_network_fee_sol"] = prm.network_fee_sol
        cb = prm.size_sol + tx
        row.update(status="NOT_FILLED", exit_reason="NOT_EXECUTABLE", not_executable_reason=reason,
                   cost_basis_sol=cb, net_pnl_sol=-tx, total_costs_sol=tx, net_pct=-tx / cb * 100.0)
        advance(min(t_entry + prm.time_stop_s, end_t))
        _finish_leader(row, world, min(t_entry + prm.time_stop_s, end_t))
        return row

    mid_pre_entry = v.mid_price()
    q = v.buy(swap_in)
    tokens = q["tokens_out"]
    entry_price = swap_in / tokens
    tokens_lost = 0.0
    lp = world.leader_fill["entry_price"]
    if prm.legacy_floor and entry_price < lp:  # legacy: the copy can never buy cheaper than the wallet it copies
        kept = swap_in / lp
        tokens_lost, tokens, entry_price = tokens - kept, kept, lp
        row["legacy_floor_applied"] = True
    d_in = q["fee_sol"]
    costs.update(entry_bot_fee_sol=bot_in, entry_mev_sol=mev_in, entry_dex_fee_sol=d_in,
                 entry_priority_fee_sol=prm.priority_fee_sol, entry_network_fee_sol=prm.network_fee_sol)
    effective_in = swap_in - d_in
    cost_basis = prm.size_sol + tx
    row["cost_basis_sol"] = cost_basis
    fol = {"size_sol": prm.size_sol, "swap_in_sol": swap_in, "tokens": tokens, "tokens_lost_legacy": tokens_lost,
           "quote_price_signal": swap_in / signal_q["tokens_out"], "entry_price": entry_price,
           "all_in_entry_price": prm.size_sol / tokens, "mid_before_entry": mid_pre_entry,
           "mid_after_entry": world.venue.mid_price(), "mid_before_exit": None, "exit_price": None,
           "exit_sol_out": None}
    row["follower"] = fol

    def wallet(sol_out):
        return sol_out - sol_out * prm.bot_fee_frac - sol_out * prm.mev_frac - tx

    # phase 3: observation points strictly after entry
    deadline = t_entry + prm.time_stop_s
    timers = {deadline} | {e["t"] + prm.delay_s for e in events if e["type"] == "leader_sell"}
    pts = {e["t"] for e in events if e["type"] != "missing"} | timers
    pts = sorted(t for t in pts if t_entry < t <= end_t and not any(a <= t < b for a, b in gaps))
    last_q = None
    max_mid = max_exec = None
    exit_q = exit_reason = None
    for t in pts:
        advance(t)
        v = world.venue
        if v.rugged:
            exit_reason = "RUG"
        elif v.dead:
            exit_reason = "POOL_DEAD"
        elif not v.tradable():
            continue
        if exit_reason is None:
            qs = v.quote_sell(tokens)
            last_q = qs
            mid_mult = v.mid_price() / mid_pre_entry
            exec_mult = wallet(qs["sol_out"]) / cost_basis
            max_mid = mid_mult if max_mid is None else max(max_mid, mid_mult)
            max_exec = exec_mult if max_exec is None else max(max_exec, exec_mult)
            if prm.tp_trigger == "price":
                tp_hit = mid_mult >= prm.tp_multiple * (1.0 - _EPS)
            else:
                tp_hit = exec_mult >= prm.tp_multiple * (1.0 - _EPS)
            if tp_hit:
                exit_reason = "TP_10X"
            elif prm.follow_sells and any(ts + prm.delay_s <= t for ts, _, _ in world.leader_sells):
                exit_reason = "LEADER_SELL"
            elif t >= deadline:
                exit_reason = "TIME_STOP"
            else:
                continue
        # execute the exit on this state
        row["t_exit"] = t
        lead_mark = world.leader_mark()
        if v.tradable():
            fol["mid_before_exit"] = v.mid_price()
            qs = v.sell(tokens)
            exit_q = {"sol_out": qs["sol_out"], "fee_sol": qs["fee_sol"]}
            if prm.legacy_floor and exit_reason == "LEADER_SELL" and world.leader_sells:
                _, ln, ls = world.leader_sells[-1]
                cap = tokens * (ls / ln)
                if exit_q["sol_out"] > cap:  # legacy: never sell dearer than the copied wallet
                    c = cap / exit_q["sol_out"]
                    exit_q = {"sol_out": exit_q["sol_out"] * c, "fee_sol": exit_q["fee_sol"] * c}
                    row["legacy_floor_applied"] = True
            _book_exit(costs, prm, exit_q)
        else:
            exit_q = {"sol_out": 0.0, "fee_sol": 0.0}  # nothing can be sold, no transaction
        break

    status = "CLOSED"
    if exit_reason is None:
        # no executable exit before the end: MISSING_PRICE, never interpolated, never a gain
        advance(end_t)
        v = world.venue
        end_q = v.quote_sell(tokens) if v.tradable() else {"sol_out": 0.0, "fee_sol": 0.0}
        cands = [c for c in (last_q, end_q) if c is not None]
        pick = min(cands, key=lambda c: c["sol_out"])
        sol_out, fee = pick["sol_out"], pick["fee_sol"]
        if sol_out > prm.size_sol:
            c = prm.size_sol / sol_out
            sol_out, fee = sol_out * c, fee * c
        exit_q = {"sol_out": sol_out, "fee_sol": fee}
        if sol_out > 0:
            _book_exit(costs, prm, exit_q)
        exit_reason, status = "MISSING_PRICE", "MARKED_MISSING"
        lead_mark = world.leader_mark()
        mark_t = end_t
    else:
        mark_t = row["t_exit"]

    sol_out = exit_q["sol_out"]
    fol["exit_sol_out"] = sol_out
    fol["exit_price"] = sol_out / tokens if tokens > 0 else None
    received = sol_out - costs["exit_bot_fee_sol"] - costs["exit_mev_sol"] - costs["exit_priority_fee_sol"] \
        - costs["exit_network_fee_sol"]
    gross = (sol_out + exit_q["fee_sol"]) - effective_in
    net = received - cost_basis
    total = sum(costs.values())
    row.update(status=status, exit_reason=exit_reason, gross_pnl_sol=gross, net_pnl_sol=net, total_costs_sol=total,
               gross_pct=gross / cost_basis * 100.0, net_pct=net / cost_basis * 100.0,
               max_mid_multiple_seen=max_mid, max_exec_multiple_seen=max_exec)
    _finish_leader(row, world, mark_t, lead_mark)
    return row


def _book_exit(costs, prm, exit_q):
    s = exit_q["sol_out"]
    costs.update(exit_dex_fee_sol=exit_q["fee_sol"], exit_bot_fee_sol=s * prm.bot_fee_frac,
                 exit_mev_sol=s * prm.mev_frac, exit_priority_fee_sol=prm.priority_fee_sol,
                 exit_network_fee_sol=prm.network_fee_sol)


def _finish_leader(row, world, mark_t, mark=None):
    if mark is None:
        mark = world.leader_mark()
    led = row["leader"]
    net = world.leader_proceeds + mark - world.leader_cost
    led.update(cost_basis_sol=world.leader_cost, net_pnl_sol=net, net_pct=net / world.leader_cost * 100.0,
               mark_t=mark_t, sells=[list(s) for s in world.leader_sells])
    row["gap_net_pct"] = led["net_pct"] - row["net_pct"]


def simulate_batch(paths, params):
    """One row per input path, always. A bad path becomes an INVALID_INPUT row (never dropped)."""
    out = []
    for i, path in enumerate(paths):
        try:
            r = simulate_trade(path, params)
        except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as e:
            r = {"path_id": path.get("id", i) if isinstance(path, dict) else i, "status": "INVALID_INPUT",
                 "exit_reason": "NOT_EXECUTABLE", "not_executable_reason": "invalid_input: %s" % e,
                 "net_pnl_sol": None, "net_pct": None, "gap_net_pct": None}
        if r.get("path_id") is None:
            r["path_id"] = i
        out.append(r)
    return out


# ---------------------------------------------------------------- summary

def summarise(results, seed=0, n_boot=2000, ci=0.95):
    n = len(results)
    by_status, by_reason = {}, {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_reason[r["exit_reason"]] = by_reason.get(r["exit_reason"], 0) + 1
    nets = [r["net_pct"] for r in results if r.get("net_pct") is not None]
    gaps = [r["gap_net_pct"] for r in results if r.get("gap_net_pct") is not None]
    sol = [r["net_pnl_sol"] for r in results if r.get("net_pnl_sol") is not None]
    out = {
        "n": n, "n_by_status": dict(sorted(by_status.items())), "n_by_exit_reason": dict(sorted(by_reason.items())),
        "n_without_pnl": n - len(nets),
        "mean_net_pct": statistics.fmean(nets) if nets else None,
        "median_net_pct": statistics.median(nets) if nets else None,
        "follower_net_sol_total": math.fsum(sol),
        "gap_mean_pct": statistics.fmean(gaps) if gaps else None,
        "gap_median_pct": statistics.median(gaps) if gaps else None,
        "ci_level": ci, "bootstrap_seed": seed, "n_boot": n_boot,
        "bootstrap_ci_mean_net_pct": None, "normal_ci_mean_net_pct": None,
    }
    if len(nets) >= 2:
        rng = random.Random(seed)
        m = len(nets)
        means = sorted(statistics.fmean(rng.choices(nets, k=m)) for _ in range(n_boot))
        lo = means[int(math.floor((1 - ci) / 2 * n_boot))]
        hi = means[min(int(math.ceil((1 + ci) / 2 * n_boot)) - 1, n_boot - 1)]
        out["bootstrap_ci_mean_net_pct"] = [lo, hi]
        z = statistics.NormalDist().inv_cdf((1 + ci) / 2)
        se = statistics.stdev(nets) / math.sqrt(m)
        out["normal_ci_mean_net_pct"] = [out["mean_net_pct"] - z * se, out["mean_net_pct"] + z * se]
    return out


def summary_json(results, **kw):
    return json.dumps(summarise(results, **kw), sort_keys=True)


# ---------------------------------------------------------------- legacy CopyBot port (idea, not code)

def legacy_buy_avg_price(spot_price, leader_price, size_sol, reserve_sol):
    """Old CopyBot: avg = max(spot, leader) * (1 + size/reserve). Equals fee-free x*y=k for leader <= spot."""
    return max(spot_price, leader_price) * (1.0 + size_sol / reserve_sol)


def legacy_sell_value(tokens, spot_price, leader_price, reserve_sol):
    """Old CopyBot: value v = tokens*min(spot, leader); proceeds = v*r/(r+v). Equals fee-free x*y=k sell."""
    v = tokens * min(spot_price, leader_price)
    return v * reserve_sol / (reserve_sol + v) if v > 0 else 0.0


def legacy_impact_ok(size_sol, reserve_sol, max_price_impact_pct=3.0):
    return size_sol / reserve_sol * 100.0 <= max_price_impact_pct


def copy_never_better_than_leader(row):
    """Legacy rule check: the copy can never buy cheaper or sell dearer than the wallet it copies."""
    bad = []
    f, led = row.get("follower"), row.get("leader")
    if not f or not led:
        return bad
    if f["entry_price"] < led["entry_price"] * (1 - 1e-12):
        bad.append("bought_cheaper_than_leader")
    if row["exit_reason"] == "LEADER_SELL" and led.get("sells") and f.get("exit_price") is not None:
        _, ln, ls = led["sells"][-1]
        if f["exit_price"] > ls / ln * (1 + 1e-12):
            bad.append("sold_dearer_than_leader")
    return bad


# ---------------------------------------------------------------- helpers for the doc

def required_mid_multiple(venue, tokens, target_wallet_sol, bot_fee_frac, mev_frac, tx_fees_sol, ref_mid):
    """Mid-price multiple (vs ref_mid) the AMM must reach, via buys by others, before a full executable sell
    of `tokens` returns `target_wallet_sol` to the wallet after all exit costs. Bisection; AMM only."""
    def wallet_after(extra):
        p = venue.clone()
        if extra > 0:
            p.buy(extra)
        s = p.quote_sell(tokens)["sol_out"]
        return s * (1 - bot_fee_frac - mev_frac) - tx_fees_sol, p.mid_price()
    lo, hi = 0.0, max(venue.sol, 1.0)
    while wallet_after(hi)[0] < target_wallet_sol:
        hi *= 2.0
        if hi > 1e15:
            return math.inf
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if wallet_after(mid)[0] >= target_wallet_sol:
            hi = mid
        else:
            lo = mid
    return wallet_after(hi)[1] / ref_mid


def amm_for_market_cap(mc_sol, k, supply=TOKEN_SUPPLY):
    """AMM reserves with constant k whose mid * supply equals mc_sol: S = sqrt(mc*k/supply), T = k/S."""
    s = math.sqrt(mc_sol * k / supply)
    return s, k / s


def worked_example():
    """Deterministic numbers for SYNTHETIC_EXECUTION_TESTS.md. Synthetic; not evidence."""
    out = {}
    # A: 30 SOL pool, leader 1 SOL at t=0, others 2 SOL at t=10 and 3 SOL at t=20, follower 1 SOL at t=30
    base = dict(size_sol=1.0, time_stop_s=25200, bot_fee_frac=0.01, slippage_tolerance=1.0, follow_sells=False)
    path = {"id": "A", "pool": {"kind": "amm", "sol": 30.0, "tokens": 1e9}, "end_t": 25230, "events": [
        {"t": 0, "type": "leader_buy", "size_sol": 1.0},
        {"t": 10, "type": "swap", "side": "buy", "size": 2.0},
        {"t": 20, "type": "swap", "side": "buy", "size": 3.0}]}
    rows = {}
    for d in (0, 30):
        prm = Params(delay_s=d, **base)
        r = simulate_trade(path, prm)
        rows[d] = r
        # rebuild the post-entry state to compute the TP needs
        w = _World(make_venue(path["pool"], prm), prm)
        for e in _normalise_events(path):
            if e["t"] <= d:
                w.apply(e)
        w.venue.buy(r["follower"]["swap_in_sol"])
        tx = prm.priority_fee_sol + prm.network_fee_sol
        ref = r["leader"]["mid_before"]
        out["A_delay_%d" % d] = {
            "leader_entry_price": r["leader"]["entry_price"], "follower_entry_price": r["follower"]["entry_price"],
            "follower_vs_leader_entry_pct": (r["follower"]["entry_price"] / r["leader"]["entry_price"] - 1) * 100,
            "follower_need_mid_x_vs_p0": required_mid_multiple(w.venue, r["follower"]["tokens"], 10 * r["cost_basis_sol"],
                                                               prm.bot_fee_frac, prm.mev_frac, tx, ref),
            "leader_need_mid_x_vs_p0": required_mid_multiple(w.venue, r["leader"]["tokens"], 10 * r["leader"]["cost_basis_sol"],
                                                             0.0, 0.0, tx, ref),
        }
    # B: the video's numbers. ASSUMPTIONS: SOL = $150; graduated pump.fun token, PumpSwap AMM seeded with
    # 85 SOL / 206.9M tokens (k fixed), drifted to $47.6K MC; follower $72 = 0.48 SOL; leader 1.0 SOL;
    # others' buys in the 30 s window calibrated so the MC at the bot's entry is $49.8K (+4.6 %).
    sol_usd = 150.0
    k = 85.0 * 206_900_000.0
    leg = LEGACY_COPYBOT_FEES
    s0, t0 = amm_for_market_cap(47_600 / sol_usd, k)
    prm_b = Params(size_sol=72.0 / sol_usd, time_stop_s=25200, slippage_tolerance=1.0, follow_sells=False,
                   tp_trigger="price", lp_fee_share=1.0, **leg)

    def mc_after(extra):
        p = AMMPool(s0, t0, prm_b.dex_fee_frac, 1.0)
        p.buy(1.0)
        if extra > 0:
            p.buy(extra)
        return p.mid_price() * TOKEN_SUPPLY * sol_usd
    lo, hi = 0.0, 50.0
    for _ in range(200):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if mc_after(m) < 49_800 else (lo, m)
    others = hi

    def run_b(prm, pump_extra=None):
        evs = [{"t": 0, "type": "leader_buy", "size_sol": 1.0},
               {"t": 15, "type": "swap", "side": "buy", "size": others}]
        p = {"id": "B", "pool": {"kind": "amm", "sol": s0, "tokens": t0}, "end_t": 25230, "events": evs}
        r0 = simulate_trade(p, prm)
        target_mid = r0["follower"]["mid_before_entry"] * prm.tp_multiple
        # pump by others until mid is exactly 10x the bot's entry spot price
        w = _World(make_venue(p["pool"], prm), prm)
        for e in _normalise_events(p):
            w.apply(e)
        w.venue.buy(r0["follower"]["swap_in_sol"])
        a, b = 0.0, 1e6
        for _ in range(300):
            m = (a + b) / 2
            c = w.venue.clone()
            c.buy(m)
            a, b = (m, b) if c.mid_price() < target_mid else (a, m)
        evs.append({"t": 3600, "type": "swap", "side": "buy", "size": b})
        return simulate_trade(p, prm)
    rb = run_b(prm_b)
    sweep = {}
    for size in (72.0 / sol_usd, 2.0, 5.0, 10.0, 20.0):
        r = run_b(Params(size_sol=size, time_stop_s=25200, slippage_tolerance=1.0, follow_sells=False,
                         tp_trigger="price", lp_fee_share=1.0, **leg))
        sweep["%.2f" % size] = {"exit_reason": r["exit_reason"], "net_pct": r["net_pct"],
                                "exec_multiple_at_tp": r["max_exec_multiple_seen"]}
    zero = Params(size_sol=72.0 / sol_usd, time_stop_s=25200, slippage_tolerance=1.0, follow_sells=False,
                  bot_fee_frac=0.0, dex_fee_frac=0.0, priority_fee_sol=0.0, network_fee_sol=0.0)
    rz = run_b(zero)
    out["B_video"] = {
        "assumptions": {"sol_usd": sol_usd, "pool_k": k, "pool_sol_at_47.6K": s0, "pool_tokens_at_47.6K": t0,
                        "leader_size_sol": 1.0, "others_window_sol": others, "follower_size_sol": 72.0 / sol_usd},
        "mc_leader_entry_usd": rb["leader"]["mid_before"] * TOKEN_SUPPLY * sol_usd,
        "mc_bot_entry_usd": rb["follower"]["mid_before_entry"] * TOKEN_SUPPLY * sol_usd,
        "legacy_fees": {"exit_reason": rb["exit_reason"], "net_pct": rb["net_pct"], "gross_pct": rb["gross_pct"],
                        "net_usd": rb["net_pnl_sol"] * sol_usd, "leader_net_pct": rb["leader"]["net_pct"],
                        "total_costs_usd": rb["total_costs_sol"] * sol_usd},
        "zero_fees": {"exit_reason": rz["exit_reason"], "net_pct": rz["net_pct"], "net_usd": rz["net_pnl_sol"] * sol_usd},
        "legacy_fees_size_sweep_sol": sweep,
    }
    return out


def random_path(seed, n_swaps=12):
    """Synthetic path generator for batch/determinism tests. Not calibrated to anything real."""
    rng = random.Random(seed)
    kind = rng.choice(["amm", "amm", "curve"])
    pool = {"kind": "amm", "sol": rng.uniform(5, 80), "tokens": 1e9} if kind == "amm" else {"kind": "curve"}
    evs = [{"t": 0, "type": "leader_buy", "size_sol": rng.uniform(0.2, 3.0)}]
    t = 0.0
    for i in range(n_swaps):
        t += rng.expovariate(1 / 40.0)
        side = "buy" if rng.random() < 0.55 else "sell"
        if side == "buy":
            evs.append({"t": round(t, 3), "type": "swap", "side": "buy", "size": rng.uniform(0.05, 4.0), "actor": "a%d" % (i % 4)})
        else:
            evs.append({"t": round(t, 3), "type": "swap", "side": "sell", "size": "all", "actor": "a%d" % (i % 4)})
    for a in range(4):  # others round-trip: every actor sells what it still holds
        t += rng.uniform(1, 30)
        evs.append({"t": round(t, 3), "type": "swap", "side": "sell", "size": "all", "actor": "a%d" % a})
    u = rng.random()
    if u < 0.1:
        evs.append({"t": round(t + 5, 3), "type": "rug", "frac": 0.99})
    elif u < 0.2:
        evs.append({"t": round(rng.uniform(20, t + 1), 3), "type": "missing", "until": round(t + 1e6, 3)})
    elif u < 0.25:
        evs.append({"t": round(t + 5, 3), "type": "pool_dead"})
    if rng.random() < 0.3:
        evs.append({"t": round(rng.uniform(1, t + 1), 3), "type": "leader_sell", "frac": 1.0})
    return {"id": "rnd%d" % seed, "pool": pool, "events": evs, "end_t": round(t + 600, 3)}
