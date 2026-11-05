"""Daily net report of the paper books (director order 44 P2; research/reviews/INBOX.md 2026-11-05). Descriptive only.

    python3 research/tools/net_report.py [--db PATH] [--out DIR]

Read-only lab.db. Per account (lane.started with a source: straks, carry90, pairs, and every carry lane): capital,
latest marked value, net, fees, paid distance from the mid split into book walk and modelled slippage allowance,
booked funding, the residual price move, realized round trips and open positions (unrealized at the last mark), max
gross exposure and max drawdown; per instrument and direction. Straks orders flagged by rettelse 41b are reported with
and without. No annualisation. Writes <out>/net_<UTC date>.json and .md and prints the sha256.
"""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import sqlite3

DB = "/home/anton/ecommerence/copybot/data/lab/lab.db"
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(HERE, "research", "data", "net_report")
FLAG_41B = {58416, 58417, 58591}                 # move ids handled before their signal (rettelse 41b)


def flagged(order_id):
    parts = order_id.split("|")
    return len(parts) > 2 and parts[1] in ("entry", "exit") and parts[2].isdigit() and int(parts[2]) in FLAG_41B


def account(con, led, info):
    ps = con.execute("SELECT payload FROM events WHERE kind='paper.started' AND exp_id=? ORDER BY id LIMIT 1",
                     (led,)).fetchone()
    capital = float(json.loads(ps[0])["capital"]) if ps else float(info.get("capital") or 10000)
    s = float((info.get("costs") or {}).get("extra_slippage", 0.0002))
    eq = con.execute("SELECT ts, equity, cash, exposure FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1",
                     (led,)).fetchone()
    agg = con.execute("SELECT MAX(exposure), MAX(drawdown) FROM sim_equity WHERE exp_id=?", (led,)).fetchone()
    fills = con.execute("SELECT ts, order_id, instrument, side, px, qty, fee, mid FROM sim_fills WHERE exp_id=? "
                        "ORDER BY id", (led,)).fetchall()
    funding = con.execute("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=?", (led,)).fetchone()[0]
    fund_by = dict(con.execute("SELECT instrument, SUM(amount) FROM sim_funding WHERE exp_id=? GROUP BY instrument",
                               (led,)).fetchall())
    net = (eq[1] - capital) if eq else 0.0
    out = {"ledger": led, "source": info.get("source") or "lane", "name": info.get("name") or info.get("function"),
           "started": info.get("t"), "capital": capital, "value": eq[1] if eq else capital,
           "marked_at": eq[0] if eq else None, "net": net, "funding": funding, "fees": 0.0, "book": 0.0,
           "allowance": 0.0, "fills": len(fills), "max_exposure": agg[0] or 0.0, "max_drawdown": agg[1] or 0.0,
           "instruments": {}, "flagged_41b": {"fills": 0, "fees": 0.0}}
    inst = collections.defaultdict(lambda: {"pos": 0.0, "basis": 0.0, "round_trips": 0, "realized": 0.0, "fees": 0.0,
                                            "direction": None, "open_since": None})
    for ts, oid, sym, side, px, q, fee, mid in fills:
        sg = 1 if side == "buy" else -1
        out["fees"] += fee
        if mid:
            paid = abs(px - mid) * q
            allow = px * q * s / ((1 + s) if side == "buy" else (1 - s))
            out["allowance"] += allow
            out["book"] += paid - allow
        if flagged(oid):
            out["flagged_41b"]["fills"] += 1
            out["flagged_41b"]["fees"] += fee
        st = inst[sym]
        st["fees"] += fee
        p0 = st["pos"]
        if p0 == 0:
            st["direction"], st["open_since"] = ("long" if sg > 0 else "short"), ts
        if p0 == 0 or (p0 > 0) == (sg > 0):
            st["basis"] = (st["basis"] * abs(p0) + px * q) / (abs(p0) + q)
            st["pos"] = p0 + sg * q
        else:
            closed = min(q, abs(p0))
            st["realized"] += closed * (px - st["basis"]) * (1 if p0 > 0 else -1)
            st["pos"] = p0 + sg * q
            if abs(st["pos"]) < 1e-12:
                st["pos"], st["round_trips"] = 0.0, st["round_trips"] + 1
    out["price_move"] = net - funding + out["fees"] + out["book"] + out["allowance"]
    for sym, st in inst.items():
        out["instruments"][sym] = {"direction_last": st["direction"], "round_trips": st["round_trips"],
                                   "realized_price_pnl": st["realized"], "fees": st["fees"],
                                   "funding": fund_by.get(sym, 0.0), "open_qty": st["pos"],
                                   "open_basis": st["basis"] if st["pos"] else None,
                                   "open_since": st["open_since"] if st["pos"] else None}
    return out


def build(con, now):
    rows = []
    gone = {e for (e,) in con.execute("SELECT exp_id FROM events WHERE kind='lane.retired'")}
    for ts, led, p in con.execute("SELECT ts, exp_id, payload FROM events WHERE kind='lane.started' ORDER BY id"):
        info = json.loads(p)
        info.setdefault("t", ts)
        if led in gone and info.get("source") not in ("straks", "carry90", "pairs"):
            continue                                              # stopped carry lanes are in their own reports
        r = account(con, led, info)
        r["active"] = led not in gone
        rows.append(r)
    return {"generated": int(now), "rule": "director order 44 P2 (research/reviews/INBOX.md)", "no_trade_benchmark": 0.0,
            "note": "descriptive; no annualisation; net = latest hourly mark minus capital; price_move = residual",
            "accounts": rows}


def md(rep):
    when = dt.datetime.fromtimestamp(rep["generated"], dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Nettorapport for papirbøgerne ({when})", "",
             "Beskrivende; ingen annualisering; mod ingen-handel = 0. Netto = seneste timemærkning − kapital; "
             "prisbevægelse = resten efter funding, gebyrer, bog og tillæg.", "",
             "| Konto | Kilde | Aktiv | Netto | Funding | Gebyrer | Bog | Tillæg | Prisbevægelse | Fyld | Maks. eksponering | "
             "Maks. fald |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["accounts"]:
        lines.append(f"| {r['name']} ({r['ledger'][-6:]}) | {r['source']} | {'ja' if r['active'] else 'nej'} | "
                     f"{r['net']:+.2f} | {r['funding']:+.2f} | {-r['fees']:+.2f} | {-r['book']:+.2f} | "
                     f"{-r['allowance']:+.2f} | {r['price_move']:+.2f} | {r['fills']} | {r['max_exposure']:,.0f} | "
                     f"{r['max_drawdown']:.2%} |")
    lines += ["", "## Pr. instrument (kun konti med handler)", ""]
    for r in rep["accounts"]:
        if not r["instruments"]:
            continue
        lines.append(f"**{r['name']}** ({r['ledger']})" + (f"; 41b-mærkede fyld {r['flagged_41b']['fills']}, "
                     f"gebyrer {r['flagged_41b']['fees']:.2f}" if r["flagged_41b"]["fills"] else ""))
        for sym, i in sorted(r["instruments"].items()):
            op = f", åben {i['open_qty']:+.4f} @ {i['open_basis']:.4f}" if i["open_qty"] else ""
            lines.append(f"- {sym}: {i['direction_last']}, {i['round_trips']} lukkede, realiseret pris "
                         f"{i['realized_price_pnl']:+.2f}, gebyrer {-i['fees']:+.2f}, funding {i['funding']:+.2f}{op}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    rep = build(con, now)
    os.makedirs(a.out, exist_ok=True)
    day = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y-%m-%d")
    raw = json.dumps(rep, sort_keys=True, indent=1).encode()
    with open(os.path.join(a.out, f"net_{day}.json"), "wb") as f:
        f.write(raw)
    with open(os.path.join(a.out, f"net_{day}.md"), "w") as f:
        f.write(md(rep))
    print(f"net_{day}.json sha256 {hashlib.sha256(raw).hexdigest()} accounts {len(rep['accounts'])}")


if __name__ == "__main__":
    main()
