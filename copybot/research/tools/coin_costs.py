"""Amendment 30 point 4: descriptive execution cost per coin from all paper fills (read-only), with the EU label.

Per coin and account type (LANE, SHADOW, FWD, ...): fills, slippage against mid (bp: mean, median, p95), fee (bp),
notional, and the cost in USD. For lanes only, per coin: the realized gross result of closed round trips (cash flow
of all spot and perp fills of that coin with the net quantity back at zero, before fees, slippage cost already in the
prices, funding received included) and the share of it that fees plus slippage take. FWD_E accounts give execution numbers
only, never a result (amendment 7 points 4-5). Description only: nothing is removed or changed from it.

  python3 research/tools/coin_costs.py [--db data/lab/lab.db] [--out FILE.json]
"""
import argparse
import collections
import json
import os
import sqlite3
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lab import venue  # noqa: E402


def kind(exp_id):
    return exp_id.split("_")[0]


def coin(instrument):
    return venue.base(instrument)


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.95 * len(xs)))]


def costs(con):
    rows = con.execute("SELECT exp_id, instrument, side, px, qty, fee, slippage, mid FROM sim_fills "
                       "WHERE mid > 0 AND px > 0 AND qty > 0").fetchall()
    per = collections.defaultdict(list)
    flows = collections.defaultdict(lambda: {"cash": 0.0, "fees": 0.0, "slip_usd": 0.0, "net": collections.Counter()})
    for exp, ins, side, px, qty, fee, slip, mid in rows:
        c, k = coin(ins), kind(exp)
        notional = px * qty
        slip_bp = abs(px - mid) / mid * 1e4
        per[(k, c)].append((slip_bp, fee / notional * 1e4, notional, fee + abs(px - mid) * qty))
        if k == "LANE":
            f = flows[(exp, c)]
            sgn = 1 if side.lower() in ("sell", "s", "short") else -1
            f["cash"] += sgn * notional
            f["fees"] += fee
            f["slip_usd"] += abs(px - mid) * qty
            f["net"][ins] += -sgn * qty
    table = []
    for (k, c), xs in sorted(per.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        s = [x[0] for x in xs]
        table.append({"type": k, "coin": c, "fills": len(xs), "slip_bp_mean": round(statistics.mean(s), 2),
                      "slip_bp_median": round(statistics.median(s), 2), "slip_bp_p95": round(p95(s), 2),
                      "fee_bp_mean": round(statistics.mean(x[1] for x in xs), 2),
                      "notional_usd": round(sum(x[2] for x in xs), 2), "cost_usd": round(sum(x[3] for x in xs), 4),
                      "eu_venues": venue.eu_venues(c + "USDT")})
    for exp, ins, amount in con.execute("SELECT exp_id, instrument, amount FROM sim_funding WHERE exp_id LIKE 'LANE%'"):
        flows[(exp, coin(ins))]["funding"] = flows[(exp, coin(ins))].get("funding", 0.0) + amount
    lanes = collections.defaultdict(lambda: {"round_trips": 0, "gross_usd": 0.0, "fees_usd": 0.0, "slip_usd": 0.0,
                                             "funding_usd": 0.0})
    for (exp, c), f in flows.items():
        if f["net"] and all(abs(q) < 1e-9 for q in f["net"].values()):          # traded and flat again
            g = lanes[c]
            g["round_trips"] += 1
            g["gross_usd"] += f["cash"] + f["slip_usd"] + f.get("funding", 0.0)   # at mid, funding included
            g["funding_usd"] += f.get("funding", 0.0)
            g["fees_usd"] += f["fees"]
            g["slip_usd"] += f["slip_usd"]
    lane_rows = []
    for c, g in sorted(lanes.items(), key=lambda kv: -kv[1]["round_trips"]):
        cost = g["fees_usd"] + g["slip_usd"]
        lane_rows.append({"coin": c, "closed_lane_coins": g["round_trips"], "gross_before_costs_usd": round(g["gross_usd"], 4),
                          "funding_usd": round(g["funding_usd"], 4), "costs_usd": round(cost, 4),
                          "net_usd": round(g["gross_usd"] - cost, 4),
                          "cost_share_of_gross": round(cost / g["gross_usd"], 3) if g["gross_usd"] >= 0.01 else None,
                          "eu_venues": venue.eu_venues(c + "USDT")})
    return {"rule": "research/PROTOCOL_V3.md amendment 30 point 4 (beskrivende)", "fills": len(rows),
            "per_coin": table, "lanes_closed": lane_rows,
            "note": "funding er med i brutto for banerne; FWD kun eksekveringstal; intet fjernes eller ændres herfra"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/lab/lab.db")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    res = costs(sqlite3.connect(f"file:{a.db}?mode=ro", uri=True))
    txt = json.dumps(res, indent=1, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
