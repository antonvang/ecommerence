"""Holder vinderne? Klarede de wallets, der var bedst som kopi (shadow) i første halvdel, sig også bedst i anden?

  python persistence.py [--db data/backtest.db]

Deler perioden på midten efter købstidspunkt og sammenligner hver wallets shadow-resultat i de to halvdele.
Er rangordenen tilfældig fra halvdel til halvdel, kan "følg den bedste wallet" ikke slå at kopiere i blinde.
"""
from __future__ import annotations

import argparse
import os
import statistics
from datetime import datetime

from store import Store

HERE = os.path.dirname(os.path.abspath(__file__))


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = ranks(a), ranks(b)
    try:
        return statistics.correlation(ra, rb)
    except statistics.StatisticsError:
        return None


def analyse(s, log=print):
    label = {w["addr"]: w["label"] for w in s.get("wallets", [])}
    rows = s.q("SELECT wallet, opened_ts, pnl_usd, cost_usd FROM positions WHERE book='shadow' AND closed_ts IS NOT NULL")
    if not rows:
        log("Ingen lukkede shadow-handler i databasen.")
        return None
    t0 = min(r["opened_ts"] for r in rows)
    t1 = max(r["opened_ts"] for r in rows)
    mid = (t0 + t1) / 2
    per = {a: [[], []] for a in label}
    for r in rows:
        per.setdefault(r["wallet"], [[], []])[0 if r["opened_ts"] < mid else 1].append(r["pnl_usd"])

    log(f"Periode {datetime.fromtimestamp(t0):%d.%m %H:%M} -> {datetime.fromtimestamp(t1):%d.%m %H:%M}, "
        f"delt ved {datetime.fromtimestamp(mid):%d.%m %H:%M}")
    log(f" {'wallet':<12}{'H1 n':>6}{'H1 $':>9}{'H1 $/h':>8}   {'H2 n':>6}{'H2 $':>9}{'H2 $/h':>8}")
    both = []
    for a, (h1, h2) in sorted(per.items(), key=lambda kv: -sum(kv[1][0])):
        def f(x):
            return f"{len(x):>6}{sum(x):>9.2f}{(sum(x) / len(x) if x else 0):>8.2f}"
        log(f" {label.get(a, a[:8])[:11]:<12}{f(h1)}   {f(h2)}")
        if h1 and h2:
            both.append((a, sum(h1), sum(h2), sum(h1) / len(h1), sum(h2) / len(h2)))

    res = {"n_wallets": len(both)}
    if len(both) >= 3:
        res["rho_total"] = spearman([b[1] for b in both], [b[2] for b in both])
        res["rho_per_trade"] = spearman([b[3] for b in both], [b[4] for b in both])
        by_h1 = sorted(both, key=lambda b: -b[1])
        k = max(1, len(both) // 3)
        top, rest = by_h1[:k], by_h1[k:]
        res["top_h2_per_trade"] = statistics.mean(b[4] for b in top)
        res["rest_h2_per_trade"] = statistics.mean(b[4] for b in rest)
        res["best_h1"] = label.get(by_h1[0][0], by_h1[0][0][:8])
        res["best_h1_h2_rank"] = sorted(both, key=lambda b: -b[2]).index(by_h1[0]) + 1
        log("")
        log(f" Rangkorrelation H1 -> H2 (Spearman, {len(both)} wallets): total $ {res['rho_total']:+.2f}, "
            f"$ pr. handel {res['rho_per_trade']:+.2f}" if res["rho_total"] is not None else " Rangkorrelation: ikke beregnelig")
        log(f" Top {k} fra H1 gav i H2 {res['top_h2_per_trade']:+.2f} $/handel, resten {res['rest_h2_per_trade']:+.2f} $/handel")
        log(f" H1's bedste ({res['best_h1']}) blev nr. {res['best_h1_h2_rank']} af {len(both)} i H2")
        log(" (+1 = samme rækkefølge, 0 = tilfældig, -1 = omvendt. Med under 10 wallets er alt under ca. 0,6 støj.)")
    else:
        log(" For få wallets med handler i begge halvdele til at måle noget.")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "backtest.db"))
    a = ap.parse_args()
    s = Store(a.db)
    analyse(s)
    s.close()


if __name__ == "__main__":
    main()
