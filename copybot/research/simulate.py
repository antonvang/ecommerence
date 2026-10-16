"""Eksekverbare priser mod poolens reserver (x*y=k) med gebyrer. Hver handel returnerer alle sine input."""
from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class Costs:
    pool_fee: float = 0.003   # pr. side, ESTIMERET (PumpSwap LP + protokol + creator)
    tx_sol: float = 0.0005    # netværk + priority pr. transaktion, ESTIMERET


def buy_tokens(res_sol, res_tok, sol_in, fee):
    """Tokens ud for sol_in SOL ind (gebyr trækkes af input)."""
    if res_sol <= 0 or res_tok <= 0 or sol_in <= 0:
        return 0.0
    x = sol_in * (1 - fee)
    return res_tok * x / (res_sol + x)


def sell_tokens(res_sol, res_tok, tok_in, fee):
    """SOL ud for tok_in tokens ind (gebyr trækkes af output)."""
    if res_sol <= 0 or res_tok <= 0 or tok_in <= 0:
        return 0.0
    return res_sol * tok_in / (res_tok + tok_in) * (1 - fee)


@dataclass
class Trade:
    mint: str
    t_entry: int
    t_exit: int
    entry_sig: Optional[str]
    exit_sig: Optional[str]
    entry_res_sol: float
    entry_res_tok: float
    exit_res_sol: Optional[float]
    exit_res_tok: Optional[float]
    size_sol: float
    tokens: float
    sol_out: Optional[float]
    net_return: Optional[float]
    status: str            # ok | ingen-exit-data
    costs: dict

    def as_dict(self):
        return asdict(self)


class PoolHistory:
    """Poolens tilstand over tid: (ts, slot, idx, res_sol, res_tok, sig) fra graduation og handler, i tidsorden."""

    def __init__(self, sol0, tok0, grad_ts, events):
        rows = [(grad_ts, -1, -1, sol0, tok0, None)]
        rows += sorted((e["ts"], e["slot"], e["idx"], e["res_sol"], e["res_tok"], e["sig"]) for e in events)
        # dubletter (samme signatur) og uordnede hændelser: sorteret ovenfor, dubletter fjernes her
        seen, self.rows = set(), []
        for r in rows:
            if r[5] is not None and r[5] in seen:
                continue
            seen.add(r[5])
            self.rows.append(r)
        self.ts = [r[0] for r in self.rows]

    def state_at(self, t):
        """Seneste tilstand med blocktid <= t (en handel i samme sekund som t regnes som sket før os)."""
        i = bisect.bisect_right(self.ts, t) - 1
        return self.rows[i] if i >= 0 else None


def simulate(mint, hist, t_entry, exit_state, t_exit, size_sol, costs=Costs()):
    """Køb ved t_entry mod hist, sælg mod exit_state (res_sol, res_tok, sig) eller None hvis exit-data mangler."""
    st = hist.state_at(t_entry)
    tokens = buy_tokens(st[3], st[4], size_sol - costs.tx_sol, costs.pool_fee)
    base = dict(mint=mint, t_entry=t_entry, t_exit=t_exit, entry_sig=st[5], entry_res_sol=st[3], entry_res_tok=st[4],
                size_sol=size_sol, tokens=tokens, costs={"pool_fee": costs.pool_fee, "tx_sol": costs.tx_sol})
    if exit_state is None:
        return Trade(exit_sig=None, exit_res_sol=None, exit_res_tok=None, sol_out=None, net_return=None,
                     status="ingen-exit-data", **base)
    res_sol, res_tok, sig = exit_state
    out = sell_tokens(res_sol, res_tok, tokens, costs.pool_fee) - costs.tx_sol
    return Trade(exit_sig=sig, exit_res_sol=res_sol, exit_res_tok=res_tok, sol_out=out, net_return=out / size_sol - 1,
                 status="ok", **base)
