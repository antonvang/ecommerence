"""Træk ved beslutningstidspunktet. Bruger KUN hændelser med blocktid < grad_ts + D (ingen fremtidig information)."""
from __future__ import annotations


def features(grad, events, D):
    """grad: dict med grad_ts, sol0, tok0. events: poolens handler (alle; filtreres her)."""
    cut = grad["grad_ts"] + D
    ev = sorted((e for e in events if e["ts"] < cut), key=lambda e: (e["slot"], e["idx"]))
    buys = [e for e in ev if e["side"] == "buy"]
    sells = [e for e in ev if e["side"] == "sell"]
    buy_sol = sum(e["sol"] for e in buys)
    sell_sol = sum(e["sol"] for e in sells)
    by_buyer = {}
    for e in buys:
        by_buyer[e["trader"]] = by_buyer.get(e["trader"], 0.0) + e["sol"]
    top = sorted(by_buyer.values(), reverse=True)
    net_tok = {}
    for e in ev:
        net_tok[e["trader"]] = net_tok.get(e["trader"], 0.0) + (e["tokens"] if e["side"] == "buy" else -e["tokens"])
    last = ev[-1] if ev else None
    p0 = grad["sol0"] / grad["tok0"]
    p = (last["res_sol"] / last["res_tok"]) if last else p0
    recent = [e for e in ev if e["ts"] >= cut - 30]
    return {
        "D": D,
        "n_events": len(ev),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "uniq_buyers": len(by_buyer),
        "uniq_sellers": len({e["trader"] for e in sells}),
        "buy_sol": buy_sol,
        "sell_sol": sell_sol,
        "net_sol": buy_sol - sell_sol,
        "net_sol_30s": sum(e["sol"] if e["side"] == "buy" else -e["sol"] for e in recent),
        "top1_share": top[0] / buy_sol if buy_sol else 0.0,
        "top3_share": sum(top[:3]) / buy_sol if buy_sol else 0.0,
        "max_holder_share": max(net_tok.values()) / grad["tok0"] if net_tok else 0.0,
        "price_mult": p / p0,
        "res_sol": last["res_sol"] if last else grad["sol0"],
    }
