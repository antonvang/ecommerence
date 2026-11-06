"""PAR-BOG diagnostic report (research/PROTOCOL_V3.md amendment 43 point 7 and 43a; research/desk/NOV14_READINESS.md
section 8, AMB-25). Exploration only: never evidence, no candidate, alpha or LÅS.

    python3 research/tools/parbog_report.py [--db PATH] [--out DIR]
    python3 research/tools/parbog_report.py --dry-run [--out DIR]       # synthetic DB only, never lab.db

Account PAR-BOG LANE_68b8b6feb9 (lane.started 2026-11-05 20:41:09 UTC). Data cutoff, fail-closed (AMB-25):
lane.started + 14 x 24 h = 2026-11-19 20:41:09 UTC; every row with ts >= cutoff is ignored, a position still open
then is reported open (exit reason "åben ved skæring"). The tool refuses (exit 2, NOT_DUE) before cutoff + 10 min.
Per pair and per exit reason (normal / stop / tid, from the exit orders' signal_ref `pairs.<why>@...` written by
lab/pairs.py): trades, gross (price move at the mid, both legs), net, fees, book, allowance, funding (both legs), hold
time, entry z and net notional at entry (QQQ/SPY reported with net exposure, ChatGPT 11-05), partial legs (43a), the
refusals recorded in lab.db, and the not-sent reasons that lab/pairs.py does not persist (UNKNOWN, never 0).

Reads lab.db only as sqlite URI file:...?mode=ro with PRAGMA query_only=ON. Stdlib only, no network, never pm_lp.
Exit 0 reported, 2 NOT_DUE, 3 integrity failure.
"""
import argparse
import calendar
import collections
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import straks_report as sr  # noqa: E402

HERE = sr.HERE
DB = sr.DB
OUT = os.path.join(HERE, "research", "data", "parbog_report")
RULE = "research/PROTOCOL_V3.md amendment 43 point 7, 43a"
LEDGER, NAME, KEY = "LANE_68b8b6feb9", "PAR-BOG", "pairs|v1"
PAIRS = (("BZUSDT", "CLUSDT"), ("ETHUSDT", "BTCUSDT"), ("QQQUSDT", "SPYUSDT"), ("XAGUSDT", "XAUUSDT"))  # 43 point 1
START_TS = calendar.timegm((2026, 11, 5, 20, 41, 9))       # lane.started event ts (NOV14 section 8)
HORIZON_S = 14 * 24 * 3600                                  # AMB-25 fail-closed: 14 x 24 h
CUTOFF = START_TS + HORIZON_S                               # 2026-11-19 20:41:09 UTC
SETTLE_S = 600
HOLD_S = 72 * 3600                                          # 43 point 5
REASONS = ("normal", "stop", "tid")
NOT_PERSISTED = ("ikke sendt: bog for tynd (43a punkt 2)", "BLOCKED: ukendt lot-størrelse (43a punkt 3)",
                 "ikke sendt: under minimumsnotional (43a punkt 1)", "not sent: invalid book / bog ikke hentet")
FIXED_LINES = ("Diagnostisk udforskning (43 punkt 7); aldrig bevis; ingen kandidat, alfa eller LÅS.",
               "2, 0,5, 4, 72 t og 720 t ændres ikke på baggrund af udfaldet.",
               "Teoretisk P&L uden gearing: ingen marginmodel; 1:1-positioner bærer markedsbeta (RISK_REGISTER_P3).",
               "Ingen annualisering af kortvarig P&L.")
_ORDER = re.compile(r"^(?P<led>[^|]+)\|(?P<kind>in|out)\|(?P<tag>[A-Z0-9]+-[A-Z0-9]+)\|(?P<hour>\d+)\|(?P<sym>[A-Z0-9]+)$")
_REF = re.compile(r"^pairs\.(?P<why>[a-zæøå]+)@(?P<hour>\d+)(?::z=(?P<z>[-+0-9.eE]+|None))?$")


def parse_ref(ref):
    m = _REF.match(ref or "")
    if not m:
        return None, None
    z = m.group("z")
    try:
        return m.group("why"), float(z) if z not in (None, "None") else None
    except ValueError:
        return m.group("why"), None


def trades(con, cutoff, slip):
    os_ = sr.orders(con, LEDGER, cutoff, slip)
    fund = sr.funding(con, LEDGER, cutoff)
    fund_by = collections.defaultdict(list)
    for f in fund:
        fund_by[f["instrument"]].append(f)
    groups, problems = collections.OrderedDict(), []
    for o in sorted(os_.values(), key=lambda o: (o["ts"], o["order_id"])):
        m = _ORDER.match(o["order_id"])
        if not m:
            problems.append(f"ukendt ordre-id {o['order_id']}")
            continue
        groups.setdefault((m.group("tag"), m.group("kind"), int(m.group("hour"))), []).append(o)
    seq = collections.defaultdict(list)
    for (tag, kind, hour), legs in groups.items():
        seq[tag].append((kind, hour, legs))
    out = []
    for tag in sorted(seq):
        pend = None
        for kind, hour, legs in sorted(seq[tag], key=lambda x: (min(o["ts"] for o in x[2]), x[0] != "out")):
            if kind == "in":
                if pend is not None:
                    problems.append(f"{tag}: ny indgang {hour} før udgang af {pend[0]}")
                    out.append(pair_trade(tag, pend, None, fund_by))
                pend = (hour, legs)
            else:
                if pend is None:
                    problems.append(f"{tag}: udgang {hour} uden indgang")
                    continue
                out.append(pair_trade(tag, pend, (hour, legs), fund_by))
                pend = None
        if pend is not None:
            out.append(pair_trade(tag, pend, None, fund_by))
    assigned = {id(f) for t in out for leg in t["legs"] for f in fund_by[leg["instrument"]]
                if f["settle_ts"] >= leg["entry_ts"] and (leg["open"] or f["settle_ts"] <= leg["exit_ts"])}
    return out, problems, {"rows": len(fund) - len(assigned),
                           "amount": sum(f["amount"] for f in fund if id(f) not in assigned)}


def pair_trade(tag, entry, exit_, fund_by):
    hour, legs = entry
    ex = {o["instrument"]: o for o in exit_[1]} if exit_ else {}
    res = [sr.leg_result(o, ex.get(o["instrument"]), fund_by[o["instrument"]]) for o in legs if o["filled"]]
    _, z_in = parse_ref(legs[0]["signal_ref"])
    why = None
    if exit_:
        whys = {parse_ref(o["signal_ref"])[0] for o in exit_[1]}
        why = whys.pop() if len(whys) == 1 else "uens: " + ",".join(sorted(map(str, whys)))
        if why not in REASONS and not why.startswith("uens"):
            why = f"ukendt ({why})"
    closed = bool(exit_) and all(not r["open"] for r in res) and len(res) == len(legs)
    t = {"pair": tag, "entry_hour": hour, "entry_ts": min(o["ts"] for o in legs), "entry_utc": sr.utc(min(
        o["ts"] for o in legs)), "z_entry": z_in, "legs": res, "legs_ordered": len(legs), "legs_filled": len(res),
        "partial_legs": sum(1 for r in res if r["partial_entry"]) + (len(legs) - len(res)),
        "net_notional_at_entry": sum((1 if r["direction"] == "long" else -1) * r["entry_notional_mid"] for r in res),
        "gross_notional_at_entry": sum(abs(r["entry_notional_mid"]) for r in res),
        "open": not closed, "exit_reason": why if closed else "åben ved skæring"}
    if closed:
        t["exit_ts"] = max(r["exit_ts"] for r in res)
        t["hold_h"] = (t["exit_ts"] - t["entry_ts"]) / 3600
        t["z_exit"] = parse_ref(exit_[1][0]["signal_ref"])[1]
    for k in ("gross", "net"):
        t[k] = sum(r[k] for r in res) if closed and all(r[k] is not None for r in res) else None
    for k in ("fees", "book", "allowance", "funding"):
        t[k] = sum(r[k] for r in res)
    t["decomposition_ok"] = closed and all(r.get("decomposition_ok") for r in res)
    return t


def agg(ts):
    closed = [t for t in ts if not t["open"]]
    return {"trades": len(ts), "closed": len(closed), "open_at_cutoff": len(ts) - len(closed),
            **{k: sum(t[k] or 0.0 for t in closed) for k in ("gross", "net")},
            **{k: sum(t[k] for t in ts) for k in ("fees", "book", "allowance", "funding")},
            "hold_h": sr.q([t.get("hold_h") for t in closed]), "partial_legs": sum(t["partial_legs"] for t in ts),
            "max_abs_net_notional_at_entry": max((abs(t["net_notional_at_entry"]) for t in ts), default=0.0),
            "decomposition_failures": sum(1 for t in closed if not t["decomposition_ok"])}


def by_reason(ts):
    out = {r: agg([t for t in ts if t["exit_reason"] == r]) for r in (*REASONS, "åben ved skæring")}
    for r in sorted({t["exit_reason"] for t in ts} - set(out)):
        out[r] = agg([t for t in ts if t["exit_reason"] == r])
    return out


def build(con, now, cutoff=CUTOFF, start_ts=START_TS):
    if now < cutoff + SETTLE_S:
        raise sr.Refused("NOT_DUE", 2, f"data cutoff {sr.utc(cutoff)}; earliest run {sr.utc(cutoff + SETTLE_S)}; "
                                       f"now {sr.utc(now)}")
    ts0, p = sr.lane_start(con, LEDGER, start_ts, "pairs", KEY)
    slip = float((p.get("costs") or {}).get("extra_slippage", 0.0002))
    cap = float(p.get("capital") or 10_000.0)
    tr, problems, unassigned = trades(con, cutoff, slip)
    refused = collections.Counter()
    for (pl,) in con.execute("SELECT payload FROM events WHERE kind IN ('paper.refused', 'paper.signal_while_paused') "
                             "AND exp_id=? AND ts < ?", (LEDGER, cutoff)):
        refused[json.loads(pl).get("reason") or "ukendt"] += 1
    tags = [f"{a}-{b}" for a, b in PAIRS]
    per_pair = {tag: {"total": agg([t for t in tr if t["pair"] == tag]),
                      "by_exit_reason": by_reason([t for t in tr if t["pair"] == tag])} for tag in tags}
    for tag in sorted({t["pair"] for t in tr} - set(tags)):
        problems.append(f"par uden for ændring 43 punkt 1: {tag}")
    return {"rule": RULE, "ledger": LEDGER, "name": NAME, "capital": cap, "start_ts": ts0, "start_utc": sr.utc(ts0),
            "payload_t": p.get("t"), "cutoff_ts": cutoff, "cutoff_utc": sr.utc(cutoff), "horizon_h": HORIZON_S // 3600,
            "retired_before_cutoff": sr.retired_before(con, LEDGER, cutoff),
            "account_at_last_mark": sr.account_level(con, LEDGER, cap, slip, cutoff),
            "total": agg(tr), "by_exit_reason": by_reason(tr), "per_pair": per_pair,
            "refused_in_db": dict(sorted(refused.items())),
            "not_sent_not_recorded_in_db": {r: None for r in NOT_PERSISTED},
            "funding_rows_not_assigned_to_a_trade": unassigned, "integrity_problems": problems,
            "tid_exit_before_72h": [t["entry_utc"] + " " + t["pair"] for t in tr
                                    if t["exit_reason"] == "tid" and t["hold_h"] < HOLD_S / 3600],
            "trades": tr, "fixed_lines": list(FIXED_LINES),
            "research_status": "INCONCLUSIVE (diagnostisk udforskning; ingen test; afgør intet)"}


def md(rep):
    a = rep["account_at_last_mark"]
    L = [f"# PAR-BOG diagnostisk opgørelse (kørt {rep['run_utc']}{', DRY-RUN syntetisk' if rep['dry_run'] else ''})", "",
         *[f"- {x}" for x in FIXED_LINES], "",
         f"Regel: {RULE}. Konto {rep['name']} ({rep['ledger']}) startet {rep['start_utc']}; dataskæring "
         f"**{rep['cutoff_utc']}** (14 × 24 t, AMB-25). Database `{rep['db_uri']}` (query_only). Resultat-sha256 "
         f"`{rep['result_sha256']}`.", "",
         f"Seneste timemærkning før skæringen {a.get('marked_at_utc')}: netto {sr.f2(a.get('net'))}, funding "
         f"{sr.f2(a.get('funding'))}, gebyrer {sr.f2(-(a.get('fees') or 0))}, bog {sr.f2(-(a.get('book') or 0))}, tillæg "
         f"{sr.f2(-(a.get('allowance') or 0))}, prisbevægelse {sr.f2(a.get('price_move'))}; maks. eksponering "
         f"{a.get('max_exposure', 0):,.0f}, maks. fald {(a.get('max_drawdown') or 0):.2%}.", "",
         "| Par | Udgangsårsag | Handler | Lukkede | Åbne | Brutto (lukkede) | Netto (lukkede) | Gebyrer | Bog | Tillæg | Funding | "
         "Median hold (t) | Delvise ben | Maks. |nettonotional| ved indgang |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]

    def row(name, why, x):
        return (f"| {name} | {why} | {x['trades']} | {x['closed']} | {x['open_at_cutoff']} | {sr.f2(x['gross'])} | "
                f"{sr.f2(x['net'])} | {sr.f2(-x['fees'])} | {sr.f2(-x['book'])} | {sr.f2(-x['allowance'])} | "
                f"{sr.f2(x['funding'])} | {'n/a' if x['hold_h']['median'] is None else round(x['hold_h']['median'], 1)}"
                f" | {x['partial_legs']} | {x['max_abs_net_notional_at_entry']:,.0f} |")
    L.append(row("alle", "alle", rep["total"]))
    for why, x in rep["by_exit_reason"].items():
        L.append(row("alle", why, x))
    for tag, pp in rep["per_pair"].items():
        L.append(row(tag, "alle", pp["total"]))
        for why, x in pp["by_exit_reason"].items():
            if x["trades"]:
                L.append(row(tag, why, x))
    L += ["", f"Afvist i lab.db: {rep['refused_in_db'] or 'ingen'}.",
          "Ikke sendt og ikke registreret i lab.db (UNKNOWN, ikke 0): " + "; ".join(rep["not_sent_not_recorded_in_db"]) + ".",
          f"Integritet: {rep['integrity_problems'] or 'ingen fund'}; 'tid' før 72 t: {rep['tid_exit_before_72h'] or 'ingen'}.",
          ""]
    return sr.check_wording("\n".join(L) + "\n")


def run(db, out, now, dry_run=False):
    if now < CUTOFF + SETTLE_S:                                  # refuse before the database is even opened
        raise sr.Refused("NOT_DUE", 2, f"data cutoff {sr.utc(CUTOFF)}; earliest run {sr.utc(CUTOFF + SETTLE_S)}")
    con = sr.connect_ro(db)
    try:
        result = build(con, now)
    finally:
        con.close()
    rsha = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    rep = {**result, "result_sha256": rsha, "run_utc": sr.utc(now), "db_uri": sr.ro_uri(db), "dry_run": dry_run}
    raw = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False).encode()
    base = ("DRYRUN_" if dry_run else "") + "parbog_" + dt.datetime.fromtimestamp(CUTOFF, dt.timezone.utc
                                                                                 ).strftime("%Y-%m-%d")
    sr.write_outputs(out, base, raw, md(rep))
    return rep, os.path.join(out, base + ".json")


# ---- synthetic data (--dry-run and tests only) ---------------------------------------------------------------------

def synthetic(dirpath):
    """PAR-BOG with four trades: ETH-BTC out 'normal', QQQ-SPY out 'stop', XAG-XAU out 'tid' after 72 h, BZ-CL open at
    the cutoff (its exit after the cutoff is ignored); XAG leg partially filled."""
    path = os.path.join(dirpath, "lab.db")
    s = sr.Synth(path)
    t0 = START_TS
    s.start(LEDGER, t0, "pairs", KEY, t=t0 - 39)
    L = LEDGER

    def trade(tag, a, b, sa, h_in, h_out, pa, pb, pa2, pb2, why, z_in=2.3, z_out=0.2, fill_a=None):
        qa, qb = round(1000 / pa, 3), round(1000 / pb, 3)
        sd = lambda x: "buy" if x > 0 else "sell"                                  # noqa: E731
        fa = None if fill_a is None else fill_a * qa
        s.order(L, f"{L}|in|{tag}|{h_in}|{a}", h_in + 5, a, sd(sa), qa, pa, ref=f"pairs.ind@{h_in}:z={z_in}",
                fill_qty=fa)
        s.order(L, f"{L}|in|{tag}|{h_in}|{b}", h_in + 5, b, sd(-sa), qb, pb, ref=f"pairs.ind@{h_in}:z={z_in}")
        if h_out is not None:
            s.order(L, f"{L}|out|{tag}|{h_out}|{a}", h_out + 5, a, sd(-sa), fa if fa is not None else qa, pa2,
                    reduce_only=True, ref=f"pairs.{why}@{h_out}:z={z_out}")
            s.order(L, f"{L}|out|{tag}|{h_out}|{b}", h_out + 5, b, sd(sa), qb, pb2, reduce_only=True,
                    ref=f"pairs.{why}@{h_out}:z={z_out}")
    H0 = t0 // 3600 * 3600 + 3600
    trade("ETHUSDT-BTCUSDT", "ETHUSDT", "BTCUSDT", -1, H0, H0 + 10 * 3600, 4000.0, 100000.0, 3960.0, 100000.0, "normal")
    s.fund(L, H0 + 8 * 3600 + 20, H0 + 8 * 3600, "ETHUSDT", 0.3)
    trade("QQQUSDT-SPYUSDT", "QQQUSDT", "SPYUSDT", 1, H0 + 86400, H0 + 86400 + 5 * 3600, 600.0, 650.0, 570.0, 650.0,
          "stop", z_in=-2.1, z_out=-4.2)
    trade("XAGUSDT-XAUUSDT", "XAGUSDT", "XAUUSDT", 1, H0 + 2 * 86400, H0 + 5 * 86400, 50.0, 4000.0, 50.5, 4000.0,
          "tid", z_in=-2.0, z_out=-1.0, fill_a=0.5)
    s.mark(L, H0 + 6 * 86400, {})
    trade("BZUSDT-CLUSDT", "BZUSDT", "CLUSDT", -1, CUTOFF - 3 * 3600, None, 70.0, 66.0, 0, 0, None)
    s.mark(L, CUTOFF - 600, {"BZUSDT": 70.0, "CLUSDT": 66.0})
    s.order(L, f"{L}|out|BZUSDT-CLUSDT|{CUTOFF // 3600 * 3600 + 3600}|BZUSDT", CUTOFF + 3600, "BZUSDT", "buy",
            round(1000 / 70.0, 3), 69.0, reduce_only=True, ref=f"pairs.normal@{CUTOFF // 3600 * 3600 + 3600}:z=0.1")
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
            tmp = tempfile.mkdtemp(prefix="parbog_dry_")
            rep, path = run(synthetic(tmp), a.out or os.path.join(tmp, "out"), CUTOFF + SETTLE_S + 60, True)
        else:
            rep, path = run(a.db, a.out or OUT, time.time())
    except sr.Refused as e:
        print(json.dumps({"status": e.status, "detail": e.detail}, ensure_ascii=False))
        return e.code
    print(json.dumps({"status": "REPORTED", "file": path, "result_sha256": rep["result_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
