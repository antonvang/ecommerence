"""Daily net report of the paper books (director order 44 P2; research/reviews/INBOX.md 2026-11-05). Descriptive only.

    python3 research/tools/net_report.py [--db PATH] [--out DIR] [--cutoff YYYY-MM-DDTHH:MM:SSZ]

Addendum 59-C: everything is read as of an explicit UTC cutoff (default 00:00:00 UTC of the run day). Each account's
equity mark gets an age at the cutoff and a status FRESH (<= 2 h) / STALE (> 2 h) / MISSING_MARK; funding, fees and
fills are also reported cut at the same marked_at ("at_mark"); no total is called a current portfolio value while any
account is STALE or MISSING_MARK.

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
STALE_S = 7200                                   # director addendum 59-C: a mark older than 2 h at the cutoff is STALE
FAR = 2 ** 62                                    # "no cutoff" for SQL comparisons


def freshness(mark_ts, cutoff):
    """(status, age_s) of an equity mark at the report's explicit cutoff (addendum 59-C): MISSING_MARK without a mark,
    STALE when older than STALE_S, else FRESH (exactly STALE_S is FRESH)."""
    if mark_ts is None:
        return "MISSING_MARK", None
    age = cutoff - mark_ts
    return ("STALE" if age > STALE_S else "FRESH"), age


def flagged(order_id):
    parts = order_id.split("|")
    return len(parts) > 2 and parts[1] in ("entry", "exit") and parts[2].isdigit() and int(parts[2]) in FLAG_41B


def account(con, led, info, cutoff=None):
    ps = con.execute("SELECT payload FROM events WHERE kind='paper.started' AND exp_id=? ORDER BY id LIMIT 1",
                     (led,)).fetchone()
    capital = float(json.loads(ps[0])["capital"]) if ps else float(info.get("capital") or 10000)
    s = float((info.get("costs") or {}).get("extra_slippage", 0.0002))
    lim = FAR if cutoff is None else cutoff          # everything is read as of the report's cutoff (addendum 59-C)
    eq = con.execute("SELECT ts, equity, cash, exposure FROM sim_equity WHERE exp_id=? AND ts<=? ORDER BY id DESC "
                     "LIMIT 1", (led, lim)).fetchone()
    agg = con.execute("SELECT MAX(exposure), MAX(drawdown) FROM sim_equity WHERE exp_id=? AND ts<=?",
                      (led, lim)).fetchone()
    fills = con.execute("SELECT ts, order_id, instrument, side, px, qty, fee, mid FROM sim_fills WHERE exp_id=? "
                        "AND ts<=? ORDER BY id", (led, lim)).fetchall()
    funding = con.execute("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=? AND ts<=?",
                          (led, lim)).fetchone()[0]
    fund_by = dict(con.execute("SELECT instrument, SUM(amount) FROM sim_funding WHERE exp_id=? AND ts<=? "
                               "GROUP BY instrument", (led, lim)).fetchall())
    mark = eq[0] if eq else None
    m_lim = mark if mark is not None else -1
    fund_m = con.execute("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=? AND ts<=?",
                         (led, m_lim)).fetchone()[0]
    at = {"fees": 0.0, "book": 0.0, "allowance": 0.0, "fills": 0, "funding": fund_m}
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
        in_mark = mark is not None and ts <= mark
        if in_mark:
            at["fees"] += fee
            at["fills"] += 1
        if mid:
            paid = abs(px - mid) * q
            allow = px * q * s / ((1 + s) if side == "buy" else (1 - s))
            out["allowance"] += allow
            out["book"] += paid - allow
            if in_mark:
                at["allowance"] += allow
                at["book"] += paid - allow
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
    at["price_move"] = net - at["funding"] + at["fees"] + at["book"] + at["allowance"]
    out["at_mark"] = at                              # funding, fees and fills cut at the same marked_at as equity
    out["after_mark"] = {"fills": out["fills"] - at["fills"], "funding": funding - at["funding"],
                         "fees": out["fees"] - at["fees"]}
    out["mark_status"], out["mark_age_s"] = freshness(mark, lim if cutoff is not None else (mark or 0))
    for sym, st in inst.items():
        out["instruments"][sym] = {"direction_last": st["direction"], "round_trips": st["round_trips"],
                                   "realized_price_pnl": st["realized"], "fees": st["fees"],
                                   "funding": fund_by.get(sym, 0.0), "open_qty": st["pos"],
                                   "open_basis": st["basis"] if st["pos"] else None,
                                   "open_since": st["open_since"] if st["pos"] else None}
    return out


def build(con, now, cutoff=None):
    """cutoff: the report's explicit UTC cutoff (epoch s). None keeps the old behaviour: as of `now`."""
    eff = now if cutoff is None else cutoff
    rows = []
    gone = {e for (e,) in con.execute("SELECT exp_id FROM events WHERE kind='lane.retired'")}
    for ts, led, p in con.execute("SELECT ts, exp_id, payload FROM events WHERE kind='lane.started' ORDER BY id"):
        info = json.loads(p)
        info.setdefault("t", ts)
        if led in gone and info.get("source") not in ("straks", "carry90", "pairs"):
            continue                                              # stopped carry lanes are in their own reports
        r = account(con, led, info, eff)
        r["active"] = led not in gone
        rows.append(r)
    by = collections.Counter(r["mark_status"] for r in rows)
    fresh = [r for r in rows if r["mark_status"] == "FRESH"]
    stale = [r for r in rows if r["mark_status"] == "STALE"]
    summary = {"cutoff": int(eff), "stale_threshold_s": STALE_S, "fresh": by["FRESH"], "stale": by["STALE"],
               "missing_mark": by["MISSING_MARK"], "net_fresh_total": sum(r["net"] for r in fresh),
               "net_stale_last_known": sum(r["net"] for r in stale),
               "portfolio_current_total": (sum(r["net"] for r in rows)
                                           if not by["STALE"] and not by["MISSING_MARK"] else None)}
    return {"generated": int(now), "rule": "director order 44 P2 (research/reviews/INBOX.md); STALE marking addendum 59-C",
            "no_trade_benchmark": 0.0,
            "note": "descriptive; no annualisation; net = latest hourly mark at or before the cutoff minus capital; "
                    "price_move = residual; at_mark = funding/fees/fills cut at the same marked_at; unleveraged "
                    "theoretical P&L: no margin model, unlimited collateral for short perp legs",
            "summary": summary, "accounts": rows}


def md(rep):
    when = dt.datetime.fromtimestamp(rep["generated"], dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sm = rep.get("summary") or {}
    cut = dt.datetime.fromtimestamp(sm.get("cutoff", rep["generated"]), dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cur = sm.get("portfolio_current_total")
    status = [f"**Cutoff: {cut}.** Mærkestatus (tærskel {sm.get('stale_threshold_s', STALE_S) // 3600} t): "
              f"FRESH {sm.get('fresh', 0)}, STALE {sm.get('stale', 0)}, MISSING_MARK {sm.get('missing_mark', 0)}.", "",
              f"- Netto, FRESH-konti: {sm.get('net_fresh_total', 0.0):+.2f}",
              f"- Sidst kendte netto, STALE-konti (ikke aktuel værdi): {sm.get('net_stale_last_known', 0.0):+.2f}",
              ("- Samlet netto: " + (f"{cur:+.2f}" if cur is not None else
                                     "**ingen aktuel porteføljeværdi** (der findes STALE/MISSING_MARK-konti)")), ""]
    lines = [f"# Nettorapport for papirbøgerne ({when})", "", *status,
             "Beskrivende; ingen annualisering; mod ingen-handel = 0. Netto = seneste timemærkning − kapital; "
             "prisbevægelse = resten efter funding, gebyrer, bog og tillæg.", "",
             "**Teoretisk P&L uden gearing:** papirmotoren har ingen marginmodel og forudsætter ubegrænset "
             "sikkerhedsstillelse for korte perp-ben; tallene er ikke verificeret eksekverbar strategi. Parbogens 1:1-"
             "positioner bærer markedsbeta (RISK_REGISTER_P3: ETH/BTC 1,25, QQQ/SPY 1,54, XAG/XAU 1,67).", "",
             "| Konto | Kilde | Aktiv | Mærke (UTC) | Alder (t) | Status | Netto ved mærket | Funding | Gebyrer | Bog | "
             "Tillæg | Prisbevægelse | Fyld | Maks. eksponering | Maks. fald |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    def hm(t):
        return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%m-%d %H:%M:%S") if t is not None else "–"
    for r in rep["accounts"]:
        age = f"{r['mark_age_s'] / 3600:.1f}" if r.get("mark_age_s") is not None else "–"
        lines.append(f"| {r['name']} ({r['ledger'][-6:]}) | {r['source']} | {'ja' if r['active'] else 'nej'} | "
                     f"{hm(r.get('marked_at'))} | {age} | {r.get('mark_status', '–')} | "
                     f"{r['net']:+.2f} | {r['funding']:+.2f} | {-r['fees']:+.2f} | {-r['book']:+.2f} | "
                     f"{-r['allowance']:+.2f} | {r['price_move']:+.2f} | {r['fills']} | {r['max_exposure']:,.0f} | "
                     f"{r['max_drawdown']:.2%} |")
    lines += ["", "Kolonnerne ovenfor (funding, gebyrer, bog, tillæg, fyld) løber til cutoff. Afgrænset ved samme "
              "mærke som equity (addendum 59-C P2):", "",
              "| Konto | Funding@mærke | Gebyrer@mærke | Bog@mærke | Tillæg@mærke | Prisbevægelse@mærke | Fyld@mærke | "
              "Efter mærket: fyld / funding |", "|---|---|---|---|---|---|---|---|"]
    for r in rep["accounts"]:
        a, b = r.get("at_mark") or {}, r.get("after_mark") or {}
        if not a:
            continue
        lines.append(f"| {r['name']} ({r['ledger'][-6:]}) | {a['funding']:+.2f} | {-a['fees']:+.2f} | "
                     f"{-a['book']:+.2f} | {-a['allowance']:+.2f} | {a['price_move']:+.2f} | {a['fills']} | "
                     f"{b.get('fills', 0)} / {b.get('funding', 0.0):+.2f} |")
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
    ap.add_argument("--cutoff", help="explicit UTC cutoff, YYYY-MM-DDTHH:MM:SSZ (default: 00:00:00 UTC of the run day)")
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    if a.cutoff:
        cutoff = dt.datetime.strptime(a.cutoff, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    else:
        cutoff = dt.datetime.fromtimestamp(now, dt.timezone.utc).replace(hour=0, minute=0, second=0,
                                                                         microsecond=0).timestamp()
    rep = build(con, now, int(cutoff))
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
