"""Tal, dom og dashboard-data ud fra databasen."""
from __future__ import annotations

import statistics
import time
from datetime import datetime

COLORS = ["#f5a35c", "#7aa7ff", "#5fe0a8", "#f27fb8", "#b49cff", "#5fd0e8", "#e8d35f", "#ff8a7a", "#9be37a", "#c7a27a"]
MIN_TRADES = 30


def trade_stats(pnls):
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    net = sum(pnls)
    return {
        "n": n,
        "win_rate": len(wins) / n * 100 if n else 0.0,
        "net": net,
        "pf": (sum(wins) / sum(losses)) if losses else (float("inf") if wins else 0.0),
        "ex_best": net - max(pnls) if pnls else 0.0,
    }


def max_drawdown(values):
    peak, dd = None, 0.0
    for v in values:
        peak = v if peak is None else max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak * 100)
    return dd


def verdict(st, backtest):
    if st["n"] < MIN_TRADES:
        return {"level": "wait", "title": "FOR TIDLIGT AT SIGE",
                "text": f"{st['n']} af mindst {MIN_TRADES} handler. Færre handler end det er mest held."}
    if st["net"] <= 0:
        return {"level": "bad", "title": "IKKE PROFITABEL",
                "text": "Efter forsinkelse, slippage og gebyrer taber strategien penge. Sæt ikke rigtige penge i."}
    if st["pf"] < 1.3 or st["ex_best"] <= 0:
        return {"level": "meh", "title": "USIKKER",
                "text": "Lille plus, men det hænger på få store vindere. Det kan lige så godt være held."}
    if backtest:
        return {"level": "ok", "title": "LOVENDE I BACKTEST",
                "text": "Men backtesten er for optimistisk: du valgte wallets, fordi de allerede havde vundet. "
                        "Kør paper trading i 1-2 uger, før du stoler på det."}
    return {"level": "ok", "title": "LOVENDE",
            "text": "Plus efter alle omkostninger på nye data. Fortsæt paper, og start live med et lille beløb."}


def shadow_table(s, wallets):
    rows = s.q("SELECT * FROM positions WHERE book='shadow' AND closed_ts IS NOT NULL")
    out = {w["addr"]: {"pnls": [], "lead": [], "us": [], "holds": []} for w in wallets}
    for r in rows:
        d = out.get(r["wallet"])
        if d is None:
            continue
        d["pnls"].append(r["pnl_usd"])
        d["us"].append(r["pnl_usd"] / r["cost_usd"] * 100)
        d["holds"].append((r["closed_ts"] - r["opened_ts"]) / 60)
        if r["leader_entry"] and r["leader_exit"]:
            d["lead"].append((r["leader_exit"] / r["leader_entry"] - 1) * 100)
    res = {}
    for a, d in out.items():
        st = trade_stats(d["pnls"])
        st["leader_avg"] = statistics.mean(d["lead"]) if d["lead"] else None
        st["us_avg"] = statistics.mean(d["us"]) if d["us"] else None
        st["med_hold"] = statistics.median(d["holds"]) if d["holds"] else None
        res[a] = st
    return res


def initials(label):
    t = "".join(ch for ch in label if ch.isalnum())
    parts = [p for p in label.replace("-", "_").split("_") if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (t[:2] or "??").upper()


def build_state(s):
    wallets = s.get("wallets", [])
    cfg = s.get("config", {})
    mode = s.get("mode", "PAPER")
    start = s.get("start_balance", 0.0) or 0.0
    cash = s.get("cash", 0.0) or 0.0
    open_rows = s.q("SELECT * FROM positions WHERE book='port' AND closed_ts IS NULL")
    balance = cash + sum(r["tokens_left"] * r["last_price"] for r in open_rows)
    closed = s.q("SELECT * FROM positions WHERE book='port' AND closed_ts IS NOT NULL ORDER BY closed_ts")
    pnls = [r["pnl_usd"] for r in closed]
    st = trade_stats(pnls)
    eq = s.q("SELECT ts, equity, wallet FROM equity ORDER BY ts")
    step = max(1, len(eq) // 1500)
    eq_pts = [[r["ts"], round(r["equity"], 4), r["wallet"]] for r in eq[::step]]
    if eq and eq_pts[-1][0] != eq[-1]["ts"]:
        eq_pts.append([eq[-1]["ts"], round(eq[-1]["equity"], 4), eq[-1]["wallet"]])
    if mode == "PAPER":
        eq_pts.append([int(time.time()), round(balance, 4), s.get("active")])

    color = {w["addr"]: COLORS[i % len(COLORS)] for i, w in enumerate(wallets)}
    label = {w["addr"]: w["label"] for w in wallets}
    active = s.get("active")
    fired = set(s.get("fired", []))
    shadow = shadow_table(s, wallets)

    by_wallet = {}
    for r in closed:
        by_wallet.setdefault(r["wallet"], []).append(r["pnl_usd"])

    # hvem fulgte vi hvornår
    segs = []
    for e in s.q("SELECT ts, kind, wallet FROM events WHERE kind IN ('follow','pause') ORDER BY id"):
        if segs:
            segs[-1]["end"] = e["ts"]
        segs.append({"wallet": e["wallet"], "start": e["ts"], "end": None})
    end_ts = eq_pts[-1][0] if eq_pts else int(time.time())
    for sg in segs:
        sg["end"] = sg["end"] or end_ts
        w = sg["wallet"]
        sg["label"] = label.get(w, "pause") if w else "pause"
        sg["color"] = color.get(w, "#3a4466")
        sg["pnl"] = sum(r["pnl_usd"] for r in closed if r["wallet"] == w and sg["start"] <= r["closed_ts"] <= sg["end"]) if w else 0.0
    fires = [[e["ts"], e["wallet"]] for e in s.q("SELECT ts, wallet FROM events WHERE kind='fired' ORDER BY ts")]

    traders = []
    for i, w in enumerate(wallets):
        a = w["addr"]
        sh = shadow[a]
        status = "following" if a == active else ("fired" if a in fired else "bench")
        traders.append({
            "rank": i + 1, "addr": a, "label": w["label"], "initials": initials(w["label"]), "color": color[a],
            "status": status, "shadow_n": sh["n"], "shadow_wr": sh["win_rate"], "shadow_pnl": sh["net"],
            "leader_avg": sh["leader_avg"], "us_avg": sh["us_avg"], "med_hold": sh["med_hold"],
            "port_pnl": sum(by_wallet.get(a, [])) if a in by_wallet else None,
        })

    last6 = [1 if p > 0 else 0 for p in by_wallet.get(active, [])[-6:]] if active else []
    feed = [dict(r) for r in s.q("SELECT ts, kind, wallet, text, pnl FROM events WHERE kind NOT IN ('start', 'skip') "
                                  "ORDER BY id DESC LIMIT 60")]
    lat = s.get("latency", [])
    hb = s.get("heartbeat")
    costs = s.one("SELECT COALESCE(SUM(costs_usd),0) FROM positions WHERE book='port'")[0]
    shadow_all = trade_stats([r["pnl_usd"] for r in s.q("SELECT pnl_usd FROM positions WHERE book='shadow' AND closed_ts IS NOT NULL")])
    return {
        "mode": mode, "live": bool(hb and time.time() - hb < 90), "now": int(time.time()),
        "balance": balance, "start_balance": start, "pnl": balance - start,
        "pnl_pct": (balance / start - 1) * 100 if start else 0.0, "multiple": balance / start if start else 0.0,
        "trades_copied": s.one("SELECT COUNT(*) FROM positions WHERE book='port'")[0],
        "open_positions": [{"symbol": r["symbol"], "wallet": label.get(r["wallet"], ""), "value": r["tokens_left"] * r["last_price"],
                            "cost": r["cost_usd"]} for r in open_rows],
        "active": None if not active else {
            "addr": active, "label": label.get(active, active[:6]), "initials": initials(label.get(active, "??")),
            "color": color.get(active), "rank": next((t["rank"] for t in traders if t["addr"] == active), None),
            "last6": last6, "with_him": sum(by_wallet.get(active, [])), "shadow": shadow.get(active)},
        "fire_rule": {"n": cfg.get("fire_after_losses", 0), "streak": s.get("streak", 0),
                      "fired_count": s.get("fired_count", 0), "next": cfg.get("next_trader", "list")},
        "equity": eq_pts, "fires": fires, "segments": segs, "feed": feed, "traders": traders,
        "costs_paid": costs, "skips": s.get("skips", {}), "latency": statistics.median(lat) if lat else None,
        "stats": {**st, "max_dd": max_drawdown([p[1] for p in eq_pts])},
        "shadow_all": shadow_all,
        "verdict": verdict(st, mode == "BACKTEST"),
        "radar": [{"ts": r["ts"], "label": label.get(r["wallet"], r["wallet"][:6]), "color": color.get(r["wallet"], "#3a4466"),
                   "initials": initials(label.get(r["wallet"], "??")), "side": r["side"], "symbol": r["symbol"],
                   "usd": r["usd"], "status": r["status"], "copied": r["copied"], "following": r["wallet"] == active}
                  for r in s.q("SELECT * FROM signals ORDER BY id DESC LIMIT 40")],
        "pulse": {"tx_seen": s.one("SELECT COUNT(*) FROM seen")[0], "heartbeat": hb,
                  "signals": s.one("SELECT COUNT(*) FROM signals")[0],
                  "signals_24h": s.one("SELECT COUNT(*) FROM signals WHERE ts >= ?", int(time.time()) - 86400)[0],
                  "last_signal": (s.one("SELECT MAX(ts) FROM signals") or [None])[0],
                  "wallets": len(wallets), "open": len(open_rows)},
        "last_error": s.get("last_error"),
    }


def _f(v, fmt="{:+.2f}"):
    return "-" if v is None else fmt.format(v)


def print_report(s, title, log=print):
    st = build_state(s)
    S = st["stats"]
    log("")
    log("=" * 78)
    log(f" {title}")
    log("=" * 78)
    log(f" Konto:        ${st['start_balance']:.2f} -> ${st['balance']:.2f}  ({st['pnl_pct']:+.1f} %)")
    pf = "uendelig" if S["pf"] == float("inf") else f"{S['pf']:.2f}"
    log(f" Handler:      {S['n']}   vindere {S['win_rate']:.0f} %   profit factor {pf}   max drawdown {S['max_dd']:.0f} %")
    log(f" Uden bedste handel: {S['ex_best']:+.2f} USD   gebyrer + slippage betalt: ${st['costs_paid']:.2f}")
    log(f" Wallets fyret: {st['fire_rule']['fired_count']}")
    if st["skips"]:
        log(" Købssignaler sprunget over: " + ", ".join(f"{k} {v}" for k, v in sorted(st["skips"].items(), key=lambda x: -x[1])))
    log("")
    log(" Hver wallet kopieret med fast beløb (shadow) - viser hvad kopiering reelt giver:")
    log(f" {'#':>2} {'wallet':<18}{'handler':>8}{'vind%':>7}{'netto $':>10}{'wallet %':>10}{'os %':>8}{'holdt min':>10}")
    for t in st["traders"]:
        log(f" {t['rank']:>2} {t['label'][:17]:<18}{t['shadow_n']:>8}{t['shadow_wr']:>7.0f}{t['shadow_pnl']:>10.2f}"
            f"{_f(t['leader_avg'], '{:+.1f}'):>10}{_f(t['us_avg'], '{:+.1f}'):>8}{_f(t['med_hold'], '{:.0f}'):>10}")
    log("   'wallet %' = hvad walletten selv fik pr. handel (før gebyrer). 'os %' = hvad vi fik som kopi.")
    log("   Forskellen er prisen for at komme for sent + slippage + gebyrer.")
    v = st["verdict"]
    log("")
    log(f" DOM: {v['title']}")
    log(f"      {v['text']}")
    log("=" * 78)
    return st


def fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
