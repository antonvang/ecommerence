"""STRAKS 7-day descriptive report (research/PROTOCOL_V3.md amendment 41 point 7, 41a point 4, rettelse 41b;
research/desk/NOV14_READINESS.md section 7, AMB-24). Diagnostic only: never evidence, no candidate, alpha or LÅS.

    python3 research/tools/straks_report.py [--db PATH] [--out DIR]
    python3 research/tools/straks_report.py --dry-run [--out DIR]       # synthetic DB only, never lab.db

Accounts STRAKS-FØLG LANE_35f39bb233 and STRAKS-MOD LANE_a751c1f595 (lane.started 2026-11-05 17:01:51 UTC). Data
cutoff, fail-closed (AMB-24): lane.started + 7 x 24 h = 2026-11-12 17:01:51 UTC; every row with ts >= cutoff is ignored.
The tool refuses (exit 2, NOT_DUE) before cutoff + 10 min (the pass that started before the cutoff has finished
writing). Per account and market class: signals seen / traded / skipped by reason / refused / not resolved, round
trips and positions open at the cutoff, gross (price move at the mid), net, fees, book, allowance, funding, largest
exposure and drawdown, timing deviations (entry vs signal, hold vs 24 h), all with and without the three 41b_timing
signals; the market's own 24 h move after the same signals (opportunity.outcome) apart from the simulated result.

Reads lab.db only as sqlite URI file:...?mode=ro with PRAGMA query_only=ON. Stdlib only, no network, never pm_lp.
Exit 0 reported, 2 NOT_DUE, 3 integrity failure (lane start differs from the pinned one, missing DB, other report).
The shared ledger helpers here are also used by parbog_report.py.
"""
import argparse
import calendar
import collections
import datetime as dt
import hashlib
import json
import os
import sqlite3
import statistics as st
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = "/home/anton/ecommerence/copybot/data/lab/lab.db"
OUT = os.path.join(HERE, "research", "data", "straks_report")
RULE = "research/PROTOCOL_V3.md amendment 41 point 7, 41a point 4, rettelse 41b"
ACCOUNTS = {"LANE_35f39bb233": ("STRAKS-FØLG", +1, "straks|cont"), "LANE_a751c1f595": ("STRAKS-MOD", -1, "straks|rev")}
START_TS = calendar.timegm((2026, 11, 5, 17, 1, 51))      # lane.started event ts of both accounts (NOV14 section 7)
HORIZON_S = 7 * 24 * 3600                                  # AMB-24 fail-closed: 7 x 24 h, not the calendar date
CUTOFF = START_TS + HORIZON_S                              # 2026-11-12 17:01:51 UTC
SETTLE_S = 600
HOLD_S = 24 * 3600                                         # amendment 41 point 4
FRESH_S = 2 * 3600                                         # amendment 41 point 2
FLAG_41B = frozenset({58416, 58417, 58591})               # rettelse 41b point 2 (as net_report.FLAG_41B)
CAPITAL = 10_000.0
SUBCLASS = {"BTCUSDT": "krypto", "ETHUSDT": "krypto", "XAUUSDT": "metaller", "XAGUSDT": "metaller",
            "XPTUSDT": "metaller", "COPPERUSDT": "metaller", "CLUSDT": "energi", "BZUSDT": "energi",
            "NATGASUSDT": "energi", "SPYUSDT": "aktieindeks", "QQQUSDT": "aktieindeks", "USDBRLUSDT": "FX"}
FIXED_LINES = ("Diagnostisk og beskrivende (41a punkt 4); aldrig bevis; ingen kandidat, alfa eller LÅS (41 punkt 7).",
               "FØLG og MOD er ikke økonomiske spejlbilleder: begge betaler omkostninger, og funding og fyldpriser er "
               "asymmetriske.",
               "24 t, 1.000 USDT og retningsreglen ændres ikke på baggrund af resultaterne.",
               "Teoretisk P&L uden gearing: ingen marginmodel, ubegrænset sikkerhedsstillelse for korte perp-ben.",
               "Ingen annualisering af kortvarig P&L.")
FORBIDDEN_WORDS = ("profitabel", "lønsom", "rentabel", "anbefal", "bevist", "edge bekræftet")


class Refused(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


# ---- shared read-only ledger helpers (also used by parbog_report.py) ------------------------------------------------

def ro_uri(path):
    return "file:" + urllib.parse.quote(os.path.abspath(path)) + "?mode=ro"


def connect_ro(path):
    if not os.path.isfile(path):
        raise Refused("NO_DB", 3, f"database not found: {path}")
    con = sqlite3.connect(ro_uri(path), uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def lane_start(con, ledger, start_ts, source, key=None):
    """(event ts, payload) of the account's lane.started; refuses when it is missing or not the pinned start."""
    r = con.execute("SELECT ts, payload FROM events WHERE kind='lane.started' AND exp_id=? ORDER BY id", (ledger,)
                    ).fetchall()
    if len(r) != 1:
        raise Refused("START_MISMATCH", 3, f"{ledger}: {len(r)} lane.started events (expected 1)")
    ts, p = int(r[0][0]), json.loads(r[0][1])
    if ts != start_ts or p.get("source") != source or (key and p.get("key") != key):
        raise Refused("START_MISMATCH", 3, f"{ledger}: lane.started ts {ts} source {p.get('source')} key "
                                           f"{p.get('key')} != pinned {start_ts} {source} {key}")
    return ts, p


def retired_before(con, ledger, cutoff):
    r = con.execute("SELECT ts, payload FROM events WHERE kind='lane.retired' AND exp_id=? AND ts < ? ORDER BY id "
                    "LIMIT 1", (ledger, cutoff)).fetchone()
    if not r:
        return None
    p = json.loads(r[1])
    return {"ts": int(r[0]), "utc": utc(int(r[0])), "rule": p.get("rule"), "detail": p.get("detail")}


def orders(con, ledger, cutoff, slip):
    """{order_id: order} for orders with ts < cutoff: filled qty, VWAP, mid, fee, book, allowance (as net_report)."""
    out = {}
    for oid, ts, inst, side, qty, ro, ref in con.execute(
            "SELECT order_id, ts, instrument, side, qty, reduce_only, signal_ref FROM sim_orders WHERE exp_id=? "
            "AND ts < ? ORDER BY id", (ledger, cutoff)):
        out[oid] = {"order_id": oid, "ts": int(ts), "instrument": inst, "side": side, "qty": float(qty),
                    "reduce_only": bool(ro), "signal_ref": ref, "filled": 0.0, "notional": 0.0, "mid_notional": 0.0,
                    "fee": 0.0, "book": 0.0, "allowance": 0.0, "fills": 0, "no_mid": 0, "cancelled": False}
    for oid, px, q, fee, mid, side in con.execute(
            "SELECT order_id, px, qty, fee, mid, side FROM sim_fills WHERE exp_id=? AND ts < ? ORDER BY id",
            (ledger, cutoff)):
        o = out.get(oid)
        if o is None:
            continue
        o["filled"] += q
        o["notional"] += px * q
        o["fee"] += fee
        o["fills"] += 1
        if mid:
            allow = px * q * slip / ((1 + slip) if side == "buy" else (1 - slip))
            o["allowance"] += allow
            o["book"] += abs(px - mid) * q - allow
            o["mid_notional"] += mid * q
        else:
            o["no_mid"] += 1
    for (oid,) in con.execute("SELECT order_id FROM sim_cancels WHERE exp_id=? AND ts < ?", (ledger, cutoff)):
        if oid in out:
            out[oid]["cancelled"] = True
    for o in out.values():
        o["vwap"] = o["notional"] / o["filled"] if o["filled"] else None
        o["mid"] = o["mid_notional"] / o["filled"] if o["filled"] and not o["no_mid"] else None
    return out


def funding(con, ledger, cutoff):
    return [{"ts": int(ts), "settle_ts": int(s), "instrument": i, "amount": float(a)} for ts, s, i, a in con.execute(
        "SELECT ts, settle_ts, instrument, amount FROM sim_funding WHERE exp_id=? AND ts < ? ORDER BY id",
        (ledger, cutoff))]


def leg_result(entry, exit_, fund):
    """One leg's round trip: gross price move at the mid, costs, funding settled while held; net = gross - fees -
    book - allowance + funding. Checked against the fill-price P&L."""
    sign = 1 if entry["side"] == "buy" else -1
    q = entry["filled"]
    r = {"instrument": entry["instrument"], "direction": "long" if sign > 0 else "short", "qty": q,
         "entry_ts": entry["ts"], "entry_mid": entry["mid"], "entry_notional_mid": (entry["mid"] or 0.0) * q,
         "partial_entry": entry["cancelled"] or q + 1e-12 < entry["qty"],
         "fees": entry["fee"], "book": entry["book"], "allowance": entry["allowance"]}
    if exit_ is None or not exit_["filled"]:
        r.update(open=True, exit_ts=None, gross=None, net=None,
                 funding=sum(f["amount"] for f in fund if f["settle_ts"] >= entry["ts"]))
        return r
    t1 = exit_["ts"]
    f = sum(x["amount"] for x in fund if entry["ts"] <= x["settle_ts"] <= t1)
    r["fees"] += exit_["fee"]
    r["book"] += exit_["book"]
    r["allowance"] += exit_["allowance"]
    qx = exit_["filled"]
    gross = sign * qx * ((exit_["mid"] or 0.0) - (entry["mid"] or 0.0)) if entry["mid"] and exit_["mid"] else None
    px_pnl = sign * (exit_["vwap"] * qx - entry["vwap"] * q)
    r.update(open=False, exit_ts=t1, hold_s=t1 - entry["ts"], funding=f, gross=gross, qty_exit=qx,
             qty_mismatch=abs(qx - q) > 1e-9,
             net=(gross - r["fees"] - r["book"] - r["allowance"] + f) if gross is not None else None,
             fill_price_pnl_plus_funding_minus_fees=px_pnl - r["fees"] + f)
    r["decomposition_ok"] = (r["net"] is not None and not r["qty_mismatch"]
                             and abs(r["net"] - r["fill_price_pnl_plus_funding_minus_fees"]) < 1e-6)
    return r


def account_level(con, ledger, capital, slip, cutoff):
    """Everything cut at the last hourly mark before the cutoff (lane.decomposition's convention): net = equity -
    capital; parts from rows with ts <= that mark; fills between it and the cutoff are counted, not hidden."""
    eq = con.execute("SELECT ts, equity, cash, exposure FROM sim_equity WHERE exp_id=? AND ts < ? ORDER BY ts DESC, "
                     "id DESC LIMIT 1", (ledger, cutoff)).fetchone()
    agg = con.execute("SELECT COUNT(*), MAX(exposure), MAX(drawdown), MIN(ts) FROM sim_equity WHERE exp_id=? AND "
                      "ts < ?", (ledger, cutoff)).fetchone()
    hours = {int(t) // 3600 for (t,) in con.execute("SELECT ts FROM sim_equity WHERE exp_id=? AND ts < ?",
                                                     (ledger, cutoff))}
    if eq is None:
        return {"marked_at": None, "net": None, "marks": 0, "note": "ingen timemærkning før skæringen"}
    tm = int(eq[0])
    fills = con.execute("SELECT px, qty, fee, mid, side FROM sim_fills WHERE exp_id=? AND ts <= ?", (ledger, tm)
                        ).fetchall()
    fund = con.execute("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=? AND ts <= ?", (ledger, tm)
                       ).fetchone()[0]
    fees = sum(f[2] for f in fills)
    allow = sum(f[0] * f[1] * slip / ((1 + slip) if f[4] == "buy" else (1 - slip)) for f in fills if f[3])
    book = sum(abs(f[0] - f[3]) * f[1] for f in fills if f[3]) - allow
    net = float(eq[1]) - capital
    after = con.execute("SELECT COUNT(*) FROM sim_fills WHERE exp_id=? AND ts > ? AND ts < ?", (ledger, tm, cutoff)
                        ).fetchone()[0]
    span = range(int(agg[3]) // 3600, tm // 3600 + 1) if agg[3] is not None else range(0)
    return {"marked_at": tm, "marked_at_utc": utc(tm), "value": float(eq[1]), "net": net, "net_on_capital": net / capital,
            "funding": float(fund), "fees": fees, "book": book, "allowance": allow,
            "price_move": net - float(fund) + fees + book + allow, "unrealised_open_exposure_at_mark": float(eq[3]),
            "marks": int(agg[0]), "hours_without_mark": sum(1 for h in span if h not in hours),
            "max_exposure": float(agg[1] or 0.0), "max_drawdown": float(agg[2] or 0.0),
            "fills_after_last_mark_before_cutoff": int(after)}


def q(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "sum": 0.0, "median": None, "min": None, "max": None}
    return {"n": len(vals), "sum": sum(vals), "median": st.median(vals), "min": min(vals), "max": max(vals)}


def totals(trades):
    closed = [t for t in trades if not t["open"]]
    return {"round_trips": len(closed), "open_at_cutoff": len(trades) - len(closed),
            **{k: sum((t[k] or 0.0) for t in closed) for k in ("gross", "net", "fees", "book", "allowance", "funding")},
            "open_costs_paid": sum(t["fees"] + t["book"] + t["allowance"] for t in trades if t["open"]),
            "open_funding": sum(t["funding"] for t in trades if t["open"]),
            "largest_entry_notional": max((abs(t["entry_notional_mid"]) for t in trades), default=0.0),
            "decomposition_failures": sum(1 for t in closed if not t.get("decomposition_ok"))}


def write_outputs(out, base, raw, text):
    os.makedirs(out, exist_ok=True)
    jp, mp = os.path.join(out, base + ".json"), os.path.join(out, base + ".md")
    if os.path.exists(jp) or os.path.exists(mp):
        try:
            with open(jp, "rb") as f:
                same = json.loads(f.read()).get("result_sha256") == json.loads(raw)["result_sha256"]
        except (OSError, ValueError):
            same = False
        if same and os.path.exists(mp):
            return                                       # idempotent: the same result is already on disk
        if same:                                         # a crash after the .json: complete the pair (as hfc1 B3)
            _atomic(mp, text.encode("utf-8"))
            return
        raise Refused("EXISTS", 3, f"{jp} exists with a different result; not overwritten")
    _atomic(mp, text.encode("utf-8"))                    # .md first: a lone .md is refused (EXISTS), never trusted
    _atomic(jp, raw)


def _atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def check_wording(text):
    bad = [w for w in FORBIDDEN_WORDS if w in text.lower()]
    if bad:
        raise Refused("WORDING", 3, f"forbidden conclusion wording in report: {bad}")
    return text


def f2(v, pct=False):
    if v is None:
        return "n/a"
    return f"{v * 100:+.2f} %" if pct else f"{v:+.2f}"


# ---- straks -----------------------------------------------------------------------------------------------------------

def direction(move):
    """Copy of lab/straks.direction (amendment 41 point 2); tests check that both agree."""
    flags = move.get("flags") or []
    r = move.get("ret_24h") if ("z_1h" not in flags and "z_24h" in flags) else move.get("ret_1h")
    if r is None or r == 0:
        return 0
    return 1 if r > 0 else -1


def moves(con, t0, cutoff):
    out = {}
    for mid, ts, p in con.execute("SELECT id, ts, payload FROM events WHERE kind='opportunity.move' AND exp_id IS NULL "
                                  "AND ts >= ? AND ts < ? ORDER BY id", (t0, cutoff)):
        m = json.loads(p)
        inst = m.get("instrument")
        out[int(mid)] = {"id": int(mid), "ts": int(ts), "instrument": inst, "class": m.get("class") or "ukendt",
                         "subclass": SUBCLASS.get(inst, "ukendt"), "d_follow": direction(m), "flag_41b": mid in FLAG_41B}
    return out


def outcomes(con, cutoff):
    """opportunity.outcome ret_24h_after per move id, only if written and ending before the cutoff."""
    out = {}
    for ts, p in con.execute("SELECT ts, payload FROM events WHERE kind='opportunity.outcome' AND ts < ? ORDER BY id",
                             (cutoff,)):
        o = json.loads(p)
        if o.get("move_id") is None or o.get("ret_24h_after") is None:
            continue
        if o.get("to_s") is not None and int(o["to_s"]) >= cutoff:
            continue
        out[int(o["move_id"])] = float(o["ret_24h_after"])
    return out


def straks_account(con, ledger, sign, mv, outc, cutoff, slip):
    os_ = orders(con, ledger, cutoff, slip)
    fund = funding(con, ledger, cutoff)
    entries, exits = {}, {}
    for o in os_.values():
        parts = o["order_id"].split("|")
        if len(parts) >= 4 and parts[2].isdigit() and parts[1] in ("entry", "exit"):
            (entries if parts[1] == "entry" else exits)[int(parts[2])] = o
    fund_by = collections.defaultdict(list)
    for f in fund:
        fund_by[f["instrument"]].append(f)
    trades = []
    for mid_, e in sorted(entries.items(), key=lambda kv: kv[1]["ts"]):
        if not e["filled"]:
            continue
        t = leg_result(e, exits.get(mid_), fund_by[e["instrument"]])
        m = mv.get(mid_)
        t.update(move_id=mid_, flag_41b=mid_ in FLAG_41B, signal_ts=m["ts"] if m else None,
                 entry_delay_s=(e["ts"] - m["ts"]) if m else None, cls=m["class"] if m else "ukendt",
                 subclass=SUBCLASS.get(e["instrument"], "ukendt"), move_in_window=m is not None)
        trades.append(t)
    assigned = {id(f) for t in trades for f in fund_by[t["instrument"]]
                if f["settle_ts"] >= t["entry_ts"] and (t["open"] or f["settle_ts"] <= t["exit_ts"])}
    skipped = {}
    for ts, p in con.execute("SELECT ts, payload FROM events WHERE kind='straks.skipped' AND exp_id=? AND ts < ? "
                             "ORDER BY id", (ledger, cutoff)):
        j = json.loads(p)
        skipped.setdefault(int(j["move_id"]), j.get("reason") or "ukendt")
    refused = {}
    for kind, p in con.execute("SELECT kind, payload FROM events WHERE kind IN ('paper.refused', "
                               "'paper.signal_while_paused') AND exp_id=? AND ts < ? ORDER BY id", (ledger, cutoff)):
        j = json.loads(p)
        parts = (j.get("order_id") or "").split("|")
        if len(parts) >= 3 and parts[1] == "entry" and parts[2].isdigit():
            refused.setdefault(int(parts[2]), f"{kind}: {j.get('reason')}")
    traded_ids = {t["move_id"] for t in trades}
    unfilled = {k for k, e in entries.items() if not e["filled"]}
    sig = []
    for m in mv.values():
        if m["id"] in traded_ids:
            s = "handlet"
        elif m["id"] in unfilled:
            s = "afvist: ordre uden fyld"
        elif m["id"] in skipped:
            s = "sprunget: " + skipped[m["id"]]
        elif m["id"] in refused:
            s = "afvist: " + refused[m["id"]]
        elif cutoff - m["ts"] <= FRESH_S:
            s = "uafklaret: signal < 2 t før skæringen"
        else:
            s = "uafklaret: ingen ordre, ingen straks.skipped (bogfejl registreres ikke i lab.db)"
        sig.append({**m, "status": s, "ret_24h_after": outc.get(m["id"])})
    return trades, sig, len(fund) - len(assigned), sum(f["amount"] for f in fund if id(f) not in assigned)


def market_move(sigs, sign):
    """The market's own 24 h move after the signals, signed in this account's direction; not the simulated result."""
    v = [s["d_follow"] * sign * s["ret_24h_after"] for s in sigs if s["ret_24h_after"] is not None and s["d_follow"]]
    return {"signals": len(sigs), "with_outcome": len(v), "signed_ret_24h_after": q(v)}


def timing(trades):
    delays = [t["entry_delay_s"] for t in trades if t["entry_delay_s"] is not None]
    neg = sorted(t["move_id"] for t in trades if t["entry_delay_s"] is not None and t["entry_delay_s"] < 0)
    holds = [t["hold_s"] for t in trades if not t["open"]]
    return {"entry_delay_s": q(delays), "entry_before_signal_move_ids": neg,
            "entry_before_signal_not_flagged_41b": sorted(set(neg) - FLAG_41B),
            "flagged_41b_without_negative_delay": sorted(m for m in FLAG_41B if m in {t["move_id"] for t in trades}
                                                         and m not in neg),
            "entry_later_than_2h": sorted(t["move_id"] for t in trades if (t["entry_delay_s"] or 0) > FRESH_S),
            "hold_minus_24h_s": q([h - HOLD_S for h in holds]),
            "exit_before_24h_move_ids": sorted(t["move_id"] for t in trades if not t["open"] and t["hold_s"] < HOLD_S),
            "trades_without_signal_in_window": sorted(t["move_id"] for t in trades if not t["move_in_window"])}


def by_key(items, key):
    g = collections.defaultdict(list)
    for x in items:
        g[x[key]].append(x)
    return dict(sorted(g.items()))


def sig_counts(sigs):
    c = collections.Counter(s["status"] for s in sigs)
    return {"seen": len(sigs), "traded": c.get("handlet", 0),
            "skipped": {k[len("sprunget: "):]: v for k, v in c.items() if k.startswith("sprunget: ")},
            "refused": {k[len("afvist: "):]: v for k, v in c.items() if k.startswith("afvist: ")},
            "unresolved": {k[len("uafklaret: "):]: v for k, v in c.items() if k.startswith("uafklaret: ")}}


def variant(trades, sigs, sign):
    v = {"signals": sig_counts(sigs), "trades": totals(trades), "timing": timing(trades),
         "market_move_after_signal": market_move(sigs, sign),
         "market_move_after_signal_traded_only": market_move([s for s in sigs if s["status"] == "handlet"], sign),
         "per_class": {}, "per_subclass": {}}
    for key, name in (("cls", "per_class"), ("subclass", "per_subclass")):
        sk = "class" if key == "cls" else "subclass"
        tg, sg = by_key(trades, key), by_key(sigs, sk)
        for c in sorted(set(tg) | set(sg)):
            v[name][c] = {"signals": sig_counts(sg.get(c, [])), "trades": totals(tg.get(c, [])),
                          "market_move_after_signal": market_move(sg.get(c, []), sign)}
    return v


def build(con, now, cutoff=CUTOFF, start_ts=START_TS):
    if now < cutoff + SETTLE_S:
        raise Refused("NOT_DUE", 2, f"data cutoff {utc(cutoff)}; earliest run {utc(cutoff + SETTLE_S)}; now {utc(now)}")
    accts, pinned_t = {}, set()
    for led, (name, sign, key) in ACCOUNTS.items():
        ts, p = lane_start(con, led, start_ts, "straks", key)
        pinned_t.add(int(p.get("t", ts)))
    t_rule = min(pinned_t)                       # lab/straks reads moves from the payload's t (lane.started(db)["ts"])
    mv = moves(con, t_rule, cutoff)
    outc = outcomes(con, cutoff)
    for led, (name, sign, key) in ACCOUNTS.items():
        ts, p = lane_start(con, led, start_ts, "straks", key)
        slip = float((p.get("costs") or {}).get("extra_slippage", 0.0002))
        cap = float(p.get("capital") or CAPITAL)
        trades, sigs, unassigned_n, unassigned_amt = straks_account(con, led, sign, mv, outc, cutoff, slip)
        acct = account_level(con, led, cap, slip, cutoff)
        flagged = [t for t in trades if t["flag_41b"]]
        closed_by_mark = acct.get("marked_at") is not None and all(
            not t["open"] and t["exit_ts"] <= acct["marked_at"] for t in flagged)
        without = {"net": (acct["net"] - sum(t["net"] for t in flagged)) if closed_by_mark and acct["net"] is not None
                   and all(t["net"] is not None for t in flagged) else None}
        if without["net"] is None and flagged:
            without["reason"] = "en 41b-handel var åben ved seneste mærkning eller uden mid: UNKNOWN (fail-closed)"
        accts[led] = {
            "name": name, "direction_sign": sign, "capital": cap, "lane_started_ts": ts, "lane_started_utc": utc(ts),
            "payload_t": p.get("t"), "retired_before_cutoff": retired_before(con, led, cutoff),
            "account_at_last_mark": acct, "account_net_without_41b": without,
            "funding_rows_not_assigned_to_a_trade": {"rows": unassigned_n, "amount": unassigned_amt},
            "with_41b": variant(trades, sigs, sign),
            "without_41b": variant([t for t in trades if not t["flag_41b"]], [s for s in sigs if not s["flag_41b"]],
                                   sign),
            "trades": trades}
    return {"rule": RULE, "accounts": accts, "cutoff_ts": cutoff, "cutoff_utc": utc(cutoff),
            "start_ts": start_ts, "start_utc": utc(start_ts), "signal_window_start_ts": t_rule,
            "signal_window_start_utc": utc(t_rule), "horizon_h": HORIZON_S // 3600,
            "flag_41b_move_ids": sorted(FLAG_41B), "signals_total": len(mv),
            "signals_between_payload_t_and_event_ts": sum(1 for m in mv.values() if m["ts"] < start_ts),
            "boundary_note": "skæringen bruger lane.started-eventets ts (17:01:51); papirløberens payload-t ligger "
                             f"{start_ts - t_rule} s før og afgrænser signalerne som lab/straks.py gør",
            "not_recorded_in_db": ["entry not sent: invalid book / bog ikke hentet (kun i gennemløbets svar)"],
            "fixed_lines": list(FIXED_LINES),
            "research_status": "INCONCLUSIVE (diagnostisk; ingen test; afgør intet)"}


def md(rep):
    L = [f"# STRAKS 7 d-opgørelse (kørt {rep['run_utc']}{', DRY-RUN syntetisk' if rep['dry_run'] else ''})", "",
         *[f"- {x}" for x in FIXED_LINES], "",
         f"Regel: {RULE}. Konti startet {rep['start_utc']}; dataskæring **{rep['cutoff_utc']}** (7 × 24 t, AMB-24); "
         f"signaler fra {rep['signal_window_start_utc']} (payload-t). Database `{rep['db_uri']}` (query_only). "
         f"Resultat-sha256 `{rep['result_sha256']}`.", ""]
    for led, a in rep["accounts"].items():
        x = a["account_at_last_mark"]
        L += [f"## {a['name']} ({led})", "",
              f"Seneste timemærkning før skæringen: {x.get('marked_at_utc')}; netto {f2(x.get('net'))} "
              f"({f2(x.get('net_on_capital'), True)} af kapitalen); funding {f2(x.get('funding'))}, gebyrer "
              f"{f2(-x['fees'] if x.get('fees') is not None else None)}, bog {f2(-x['book'] if x.get('book') is not None else None)}, "
              f"tillæg {f2(-x['allowance'] if x.get('allowance') is not None else None)}, prisbevægelse "
              f"{f2(x.get('price_move'))}; maks. eksponering {x.get('max_exposure', 0):,.0f}, maks. fald "
              f"{(x.get('max_drawdown') or 0):.2%}; mærkninger {x.get('marks')} (timer uden: {x.get('hours_without_mark')});"
              f" fyld efter mærkningen og før skæringen: {x.get('fills_after_last_mark_before_cutoff')}.",
              f"Netto uden 41b: {f2(a['account_net_without_41b']['net'])}"
              + (f" ({a['account_net_without_41b'].get('reason')})" if a['account_net_without_41b'].get('reason') else "")
              + (f". Stoppet før skæringen: {a['retired_before_cutoff']}" if a["retired_before_cutoff"] else "") + ".",
              "", "| Variant | Signaler | Handlet | Sprunget (årsag) | Afvist | Uafklaret | Rundture | Åbne | Brutto | "
              "Netto (lukkede) | Gebyrer | Bog | Tillæg | Funding | Marked 24 t efter (median, n) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for vname in ("with_41b", "without_41b"):
            v = a[vname]
            s, t, mm = v["signals"], v["trades"], v["market_move_after_signal"]["signed_ret_24h_after"]
            L.append(f"| {'med 41b' if vname == 'with_41b' else 'uden 41b'} | {s['seen']} | {s['traded']} | "
                     f"{_d(s['skipped'])} | {_d(s['refused'])} | {_d(s['unresolved'])} | {t['round_trips']} | "
                     f"{t['open_at_cutoff']} | {f2(t['gross'])} | {f2(t['net'])} | {f2(-t['fees'])} | {f2(-t['book'])} | "
                     f"{f2(-t['allowance'])} | {f2(t['funding'])} | {f2(mm['median'], True)} ({mm['n']}) |")
        L += ["", "| Klasse (med 41b) | Signaler | Handlet | Sprunget | Rundture | Åbne | Brutto | Netto (lukkede) | "
                  "Marked 24 t efter (median) |", "|---|---|---|---|---|---|---|---|---|"]
        for c, v in a["with_41b"]["per_subclass"].items():
            s, t = v["signals"], v["trades"]
            L.append(f"| {c} | {s['seen']} | {s['traded']} | {sum(s['skipped'].values())} | {t['round_trips']} | "
                     f"{t['open_at_cutoff']} | {f2(t['gross'])} | {f2(t['net'])} | "
                     f"{f2(v['market_move_after_signal']['signed_ret_24h_after']['median'], True)} |")
        tm = a["with_41b"]["timing"]
        L += ["", f"Timing: indgang − signal median {tm['entry_delay_s']['median']} s (min {tm['entry_delay_s']['min']}, "
                  f"maks {tm['entry_delay_s']['max']}); indgang før signalet: {tm['entry_before_signal_move_ids']} "
                  f"(uden for 41b: {tm['entry_before_signal_not_flagged_41b']}); senere end 2 t: "
                  f"{tm['entry_later_than_2h']}; hold − 24 t median {tm['hold_minus_24h_s']['median']} s; ud før 24 t: "
                  f"{tm['exit_before_24h_move_ids']}.", ""]
    L += [f"Ikke registreret i lab.db (kan ikke tælles, UNKNOWN): {'; '.join(rep['not_recorded_in_db'])}.", ""]
    return check_wording("\n".join(L) + "\n")


def _d(d):
    return ", ".join(f"{k}: {v}" for k, v in sorted(d.items())) or "0"


def run(db, out, now, dry_run=False):
    if now < CUTOFF + SETTLE_S:                                  # refuse before the database is even opened
        raise Refused("NOT_DUE", 2, f"data cutoff {utc(CUTOFF)}; earliest run {utc(CUTOFF + SETTLE_S)}")
    con = connect_ro(db)
    try:
        result = build(con, now)
    finally:
        con.close()
    rsha = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    rep = {**result, "result_sha256": rsha, "run_utc": utc(now), "db_uri": ro_uri(db), "dry_run": dry_run}
    raw = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False).encode()
    base = ("DRYRUN_" if dry_run else "") + "straks_7d_" + dt.datetime.fromtimestamp(CUTOFF, dt.timezone.utc
                                                                                      ).strftime("%Y-%m-%d")
    write_outputs(out, base, raw, md(rep))
    return rep, os.path.join(out, base + ".json")


# ---- synthetic data (--dry-run and tests only) ---------------------------------------------------------------------

SCHEMA = [
    "CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts, kind, actor, exp_id, payload, prev_hash TEXT NOT "
    "NULL, hash TEXT NOT NULL UNIQUE)",
    "CREATE TABLE sim_orders(id INTEGER PRIMARY KEY AUTOINCREMENT, order_id, exp_id, ts, instrument, side, qty, "
    "limit_px, style, reduce_only, signal_ref, cost_model, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)",
    "CREATE TABLE sim_fills(id INTEGER PRIMARY KEY AUTOINCREMENT, fill_id, order_id, exp_id, ts, instrument, side, px, "
    "qty, fee, slippage, liquidity, mid, book_ts, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)",
    "CREATE TABLE sim_funding(id INTEGER PRIMARY KEY AUTOINCREMENT, exp_id, ts, settle_ts, instrument, qty, rate, "
    "price, amount, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)",
    "CREATE TABLE sim_equity(id INTEGER PRIMARY KEY AUTOINCREMENT, exp_id, ts, equity, cash, exposure, peak, drawdown, "
    "prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)",
    "CREATE TABLE sim_cancels(id INTEGER PRIMARY KEY AUTOINCREMENT, order_id, exp_id, ts, reason, prev_hash TEXT NOT "
    "NULL, hash TEXT NOT NULL UNIQUE)"]


class Synth:
    """Minimal writer for synthetic lab-shaped databases (tests and --dry-run); a simple ledger keeps cash and marks."""

    def __init__(self, path, slip=0.0002, taker=0.001):
        self.con = sqlite3.connect(path)
        for s in SCHEMA:
            self.con.execute(s)
        self.n, self.slip, self.taker = 0, slip, taker
        self.cash, self.pos = {}, collections.defaultdict(dict)

    def _h(self):
        self.n += 1
        return f"h{self.n}"

    def event(self, ts, kind, exp_id, payload, id_=None):
        self.con.execute("INSERT INTO events(id, ts, kind, actor, exp_id, payload, prev_hash, hash) VALUES "
                         "(?, ?, ?, 'test', ?, ?, '', ?)", (id_, ts, kind, exp_id, json.dumps(payload), self._h()))
        return self.con.execute("SELECT last_insert_rowid()").fetchone()[0]

    def start(self, led, ts, source, key, capital=10_000.0, t=None):
        self.cash[led] = capital
        self.event(ts, "lane.started", led, {"key": key, "source": source, "capital": capital, "t": t or ts,
                                             "costs": {"extra_slippage": self.slip, "taker_fee": self.taker}})
        self.event(ts, "paper.started", led, {"capital": capital})

    def order(self, led, oid, ts, inst, side, qty, mid, reduce_only=False, ref=None, fill_qty=None):
        self.con.execute("INSERT INTO sim_orders(order_id, exp_id, ts, instrument, side, qty, style, reduce_only, "
                         "signal_ref, cost_model, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, 'taker', ?, ?, '{}', '', ?)",
                         (oid, led, ts, inst, side, qty, int(reduce_only), ref, self._h()))
        fq = qty if fill_qty is None else fill_qty
        lvl = mid * (1.0005 if side == "buy" else 0.9995)              # 5 bp book walk
        px = lvl * ((1 + self.slip) if side == "buy" else (1 - self.slip))
        fee = self.taker * px * fq
        self.con.execute("INSERT INTO sim_fills(fill_id, order_id, exp_id, ts, instrument, side, px, qty, fee, "
                         "slippage, liquidity, mid, book_ts, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, "
                         "'taker', ?, ?, '', ?)", (oid + "|0", oid, led, ts, inst, side, px, fq, fee, mid, ts, self._h()))
        if fq < qty:
            self.con.execute("INSERT INTO sim_cancels(order_id, exp_id, ts, reason, prev_hash, hash) VALUES "
                             "(?, ?, ?, 'IOC remainder (depth or limit)', '', ?)", (oid, led, ts, self._h()))
        sg = 1 if side == "buy" else -1
        self.cash[led] -= sg * px * fq + fee
        self.pos[led][inst] = self.pos[led].get(inst, 0.0) + sg * fq
        return px, fee

    def fund(self, led, ts, settle_ts, inst, amount):
        self.cash[led] += amount
        self.con.execute("INSERT INTO sim_funding(exp_id, ts, settle_ts, instrument, qty, rate, price, amount, "
                         "prev_hash, hash) VALUES (?, ?, ?, ?, 0, 0, 0, ?, '', ?)",
                         (led, ts, settle_ts, inst, amount, self._h()))

    def mark(self, led, ts, marks, peak=None):
        held = {i: qv for i, qv in self.pos[led].items() if abs(qv) > 1e-12}
        eq = self.cash[led] + sum(qv * marks[i] for i, qv in held.items())
        ex = sum(abs(qv) * marks[i] for i, qv in held.items())
        pk = max(peak or 10_000.0, eq)
        self.con.execute("INSERT INTO sim_equity(exp_id, ts, equity, cash, exposure, peak, drawdown, prev_hash, hash) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, '', ?)", (led, ts, eq, self.cash[led], ex, pk, (pk - eq) / pk,
                                                                  self._h()))
        return eq

    def close(self):
        self.con.commit()
        self.con.close()


def synthetic(dirpath):
    """Both accounts; four signals: 58416 (41b: entry 41 s before the signal, closed after 24 h), 60001 (crypto,
    closed), 60002 (skipped: open position), 60003 (metal, open at the cutoff), and one post-cutoff fill and signal."""
    path = os.path.join(dirpath, "lab.db")
    s = Synth(path)
    t0 = START_TS
    for led, (name, sign, key) in ACCOUNTS.items():
        s.start(led, t0, "straks", key, t=t0 - 40)
    s.event(t0 + 3600, "opportunity.move", None, {"instrument": "CLUSDT", "class": "commodity", "flags": ["z_1h"],
                                                  "ret_1h": 0.02, "ret_24h": 0.01}, id_=58416)
    s.event(t0 + 7200, "opportunity.move", None, {"instrument": "BTCUSDT", "class": "crypto", "flags": ["z_24h"],
                                                  "ret_1h": 0.001, "ret_24h": -0.05}, id_=60001)
    s.event(t0 + 7300, "opportunity.move", None, {"instrument": "BTCUSDT", "class": "crypto", "flags": ["z_1h"],
                                                  "ret_1h": 0.03, "ret_24h": 0.0}, id_=60002)
    s.event(CUTOFF - 3 * 86400, "opportunity.move", None, {"instrument": "XAUUSDT", "class": "commodity",
                                                          "flags": ["z_1h"], "ret_1h": -0.01, "ret_24h": 0.0}, id_=60003)
    s.event(CUTOFF + 100, "opportunity.move", None, {"instrument": "ETHUSDT", "class": "crypto", "flags": ["z_1h"],
                                                     "ret_1h": 0.01, "ret_24h": 0.0}, id_=60004)
    for mid_, px in ((58416, 1.03), (60001, 0.97)):
        s.event(t0 + 3600 + 86400 + 60, "opportunity.outcome", None, {"move_id": mid_, "ret_24h_after": px - 1,
                                                                      "from_s": t0, "to_s": t0 + 90000})
    for led, (name, sign, key) in ACCOUNTS.items():
        side = lambda d: "buy" if d * sign > 0 else "sell"                         # noqa: E731
        rev = lambda d: "sell" if d * sign > 0 else "buy"                          # noqa: E731
        s.order(led, f"{led}|entry|58416|CLUSDT", t0 + 3600 - 41, "CLUSDT", side(1), 10.0, 100.0,
                ref="straks.entry@58416")
        s.order(led, f"{led}|entry|60001|BTCUSDT", t0 + 7260, "BTCUSDT", side(-1), 0.01, 100000.0,
                ref="straks.entry@60001")
        s.event(t0 + 7360, "straks.skipped", led, {"move_id": 60002, "instrument": "BTCUSDT",
                                                   "reason": "åben position på markedet"})
        s.fund(led, t0 + 3 * 3600 + 30, t0 + 3 * 3600, "BTCUSDT", 0.5 * sign)
        s.order(led, f"{led}|exit|58416|CLUSDT", t0 + 3600 + 86400 + 10, "CLUSDT", rev(1), 10.0, 103.0,
                reduce_only=True, ref="straks.exit@58416")
        s.order(led, f"{led}|exit|60001|BTCUSDT", t0 + 7260 + 86400 + 10, "BTCUSDT", rev(-1), 0.01, 97000.0,
                reduce_only=True, ref="straks.exit@60001")
        s.mark(led, t0 + 2 * 86400, {})
        s.order(led, f"{led}|entry|60003|XAUUSDT", CUTOFF - 3 * 86400 + 30, "XAUUSDT", side(-1), 0.25, 4000.0,
                ref="straks.entry@60003")
        s.mark(led, CUTOFF - 1800, {"XAUUSDT": 3990.0})
        s.order(led, f"{led}|exit|60003|XAUUSDT", CUTOFF + 50, "XAUUSDT", rev(-1), 0.25, 3900.0, reduce_only=True,
                ref="straks.exit@60003")
        s.mark(led, CUTOFF + 1800, {})
    s.close()
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true", help="synthetic DB in a temp dir; never lab.db")
    a = ap.parse_args(argv)
    try:
        if a.dry_run:
            tmp = tempfile.mkdtemp(prefix="straks_dry_")
            rep, path = run(synthetic(tmp), a.out or os.path.join(tmp, "out"), CUTOFF + SETTLE_S + 60, True)
        else:
            rep, path = run(a.db, a.out or OUT, time.time())
    except Refused as e:
        print(json.dumps({"status": e.status, "detail": e.detail}, ensure_ascii=False))
        return e.code
    print(json.dumps({"status": "REPORTED", "file": path, "result_sha256": rep["result_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
