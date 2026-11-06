"""HFC-1 outcome report (research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md, director orders 46 P2 and
49 P2; research/desk/NOV14_READINESS.md section 6, AMB-21..23). Descriptive only: no test, no p-value, no conclusion.

    python3 research/tools/hfc1_report3d.py [--horizon 3d|14d] [--cohort 2026-11-04 ...] [--db PATH] [--out DIR]
    python3 research/tools/hfc1_report3d.py --dry-run [--out DIR]      # synthetic DB + cohort only, never lab.db

For every stored cohort day d (research/data/hfc1/<d>.json, written by hfc1_daily.py) the horizon window is
[d+1 00:00, d+1+H 00:00) UTC. A cohort is reported only when the clock is at or after window end + 35 min (the last
23:xx census/1 snapshot has landed); otherwise it is NOT_DUE and nothing about it is computed. If no requested cohort
is due the tool exits 2 (NOT_DUE) and writes nothing.

All C0 members are reported, also those without a spot pair: realised funding is a perp-only measure and is computed
for every member; cost, coverage and net need the cohort's book-walk cost and are "n/a" for dropouts (never "missing").
"Missing" (protocol: absent from later snapshots, or > 25 % of the window's snapshots missing) counts as not covered,
never as success. Dropouts (F1-F5) are reported per filter step, separately. Both sizes (1 000 and 5 000 USDT per leg),
both denominators (funding break-even against perp notional, net on allocated capital 2 x N at 1x).

Reads lab.db only as sqlite URI file:...?mode=ro with PRAGMA query_only=ON. Stdlib only, no network, never pm_lp.
Writes <out>/hfc1_<H>_<cohorts>.json and .md (refuses to overwrite a different existing report). Exit 0 reported,
2 NOT_DUE, 3 integrity failure (cohort file hash mismatch, missing DB, existing different report).
"""
import argparse
import calendar
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
COHORTS = os.path.join(HERE, "research", "data", "hfc1")
OUT = os.path.join(HERE, "research", "data", "hfc1_report3d")
OFFDB = os.path.join(HERE, "research", "data", "factory", "offdb_studies.json")
PROTOCOL = "research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md"
FIRST, LAST = dt.date(2026, 11, 4), dt.date(2026, 11, 24)
M2 = 0.188                                  # C0+ threshold (protocol 'Kohorte og filtre')
SIZES = ("1000", "5000")                    # USDT per leg (F4)
H = {"3d": (3, 9), "14d": (14, 42)}         # days, 8 h periods (as hfc1_daily.H)
MISSING_FRAC = 0.25                         # protocol 'Udfald': > 25 % of the window's snapshots missing
SETTLE_S = 35 * 60                          # NOV14_READINESS section 6: run >= 00:35 UTC after the window end
PINNED = {"2026-11-04": "a5f831c40c19", "2026-11-05": "b43afaf295c4"}   # file sha256 prefixes in the protocol text
FORBIDDEN_WORDS = ("profitabel", "lønsom", "rentabel", "anbefal", "bevist", "edge bekræftet")
FIXED_LINES = ("Beskrivende; afgør intet; ingen test, ingen p-værdi (protokollen: \"ingen statistisk test\").",
               "3 dage siger intet om langsigtet profit." ,
               "Ingen evaluering, konklusion eller ny udvælgelsesregel før beslutningsnotatet efter 11-28 (AMB-21).",
               "Kendt begrænsning: lastFundingRate × perioder antager 8 t-intervaller; perps med 4 t-interval "
               "undervurderes (protokollens 'Kendte begrænsninger').",
               "Omkostningen er bogens gennemgang ved kohortedannelsen (én bogaflæsning, ind og ud på samme bog) + taker "
               "og tillæg; en realiseret exit-bog er ikke observeret (ingen netværk).")


class Refused(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


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


def window(day, horizon):
    """[start, end) of the outcome window of cohort `day` and the earliest run time."""
    days, _ = H[horizon]
    start = calendar.timegm(day.timetuple()) + 86400
    end = start + days * 86400
    return start, end, end + SETTLE_S


def snapshots(con, t0, t1):
    """census/1 snapshots with t0 <= ts < t1: [(ts, {USDT symbol: lastFundingRate}, {trading perps})] (as
    hfc1_daily.snapshots, plus the perp-status set)."""
    out = []
    for ts, p in con.execute("SELECT ts, payload FROM observations WHERE detector='census/1' AND metric='snapshot' "
                             "AND ts >= ? AND ts < ? ORDER BY ts, id", (t0, t1)):
        j = json.loads(p)
        cols = j.get("columns") or []
        if "lastFundingRate" not in cols:
            continue
        i = cols.index("lastFundingRate")
        rates = {}
        for sym, row in (j.get("rows") or {}).items():
            if sym.endswith("USDT"):
                try:
                    rates[sym] = float(row[i])
                except (TypeError, ValueError, IndexError):
                    pass
        out.append((ts, rates, set(j.get("coin_perps") or [])))
    return out


def load_cohort(path, day, pins=PINNED):
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    pin = pins.get(str(day))
    if pin is not None and not sha.startswith(pin):
        raise Refused("COHORT_HASH_MISMATCH", 3, f"{path}: sha256 {sha[:12]}… differs from the protocol's {pin}…")
    body = json.loads(raw)
    if body.get("day") != str(day):
        raise Refused("COHORT_DAY_MISMATCH", 3, f"{path}: day {body.get('day')} != {day}")
    return body, sha, pin is not None


def _q(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "median": None, "min": None, "max": None}
    return {"n": len(vals), "median": st.median(vals), "min": min(vals), "max": max(vals)}


def member_rows(body, snaps, horizon):
    days, k = H[horizon]
    expect = days * 24                                   # hourly census snapshots (hfc1_daily.outcomes)
    last = snaps[-1] if snaps else None
    out = []
    for r in body["rows"]:
        sym = r["symbol"]
        v = [s[1][sym] for s in snaps if sym in s[1]]
        present_last = bool(last and sym in last[1])
        trading_last = bool(last and sym in last[2])
        reasons = []
        if not v:
            reasons.append("ingen observationer i vinduet")
        if len(v) < (1 - MISSING_FRAC) * expect:
            reasons.append(f"{len(v)} af {expect} snapshots (> 25 % mangler)")
        if not present_last:
            reasons.append("mangler i vinduets sidste snapshot (afnoteret/omdøbt?)")
        missing = bool(reasons)
        m = {"symbol": sym, "apr_cohort": r.get("apr"), "c0plus": bool(r.get("m2")), "drop": r.get("drop"),
             "drop_size": r.get("drop_size") or [], "n_obs": len(v), "expected_obs": expect,
             "obs_coverage": len(v) / expect if expect else None, "present_in_last_snapshot": present_last,
             "perp_trading_at_end": trading_last, "missing": missing, "missing_reasons": reasons,
             "missing_75pct_rule_only": len(v) < (1 - MISSING_FRAC) * expect,
             "realised_f8h": None if missing else st.fmean(v),
             "partial_f8h_not_used": st.fmean(v) if (missing and v) else None,
             "status": ("manglende" if missing else "observeret") + ("" if trading_last or not present_last
                                                                     else "; perp ikke TRADING ved vinduets slut")}
        m["realised_apr"] = None if missing else m["realised_f8h"] * 1095
        for n in SIZES:
            N = float(n)
            cost = r.get(f"cost_{n}")
            rf = None if missing else m["realised_f8h"] * k * N
            d = {"cost": cost, "cost_known": cost is not None, "realised_funding": rf,
                 "ex_ante_covered": r.get(f"covered_{horizon}_{n}"),
                 "breakeven_apr_perp_notional": (cost / (N * days / 365.0)) if cost is not None else None}
            if cost is None:
                d.update(covered_ex_post=None, coverage_ratio=None, net=None, net_on_allocated=None)
            elif missing:                                 # protocol: missing counts as not covered, never as success
                d.update(covered_ex_post=False, coverage_ratio=None, net=None, net_on_allocated=None)
            else:
                d.update(covered_ex_post=rf >= cost, coverage_ratio=(rf / cost) if cost > 0 else None,
                         net=rf - cost, net_on_allocated=(rf - cost) / (2 * N))
            m[f"N{n}"] = d
        out.append(m)
    return out


def groups(members, horizon):
    """Named member subsets: C0, C0+, passed F1-F5 / F1-F6 at each size, and each dropout step."""
    g = {"C0": members, "C0+": [m for m in members if m["c0plus"]]}
    for n in SIZES:
        p5 = [m for m in members if not m["drop"] and m[f"N{n}"]["cost_known"]]
        g[f"bestod_F1-F5_N{n}"] = p5
        g[f"bestod_F1-F6_{horizon}_N{n}"] = [m for m in p5 if m[f"N{n}"]["ex_ante_covered"] is True]
    steps = sorted({m["drop"].split(":")[0] for m in members if m["drop"]})
    for s in steps:
        g[f"frafald {s}"] = [m for m in members if m["drop"] and m["drop"].split(":")[0] == s]
    for n in SIZES:
        f4 = [m for m in members if not m["drop"] and not m[f"N{n}"]["cost_known"]]
        if f4:
            g[f"frafald F4 N{n}"] = f4
    return g


def summarise(ms):
    s = {"members": len(ms), "c0plus": sum(m["c0plus"] for m in ms),
         "missing": sum(m["missing"] for m in ms), "missing_75pct_rule_only": sum(m["missing_75pct_rule_only"]
                                                                                for m in ms),
         "dropouts": sum(1 for m in ms if m["drop"]), "observed": sum(not m["missing"] for m in ms),
         "absent_in_last_snapshot": sum(not m["present_in_last_snapshot"] for m in ms),
         "perp_not_trading_at_end": sum(m["present_in_last_snapshot"] and not m["perp_trading_at_end"] for m in ms),
         "obs_coverage": _q([m["obs_coverage"] for m in ms]), "realised_apr": _q([m["realised_apr"] for m in ms])}
    for n in SIZES:
        d = [m[f"N{n}"] for m in ms]
        known = [x for x in d if x["cost_known"]]
        cov = sum(x["covered_ex_post"] is True for x in known)
        s[f"N{n}"] = {
            "cost_known": len(known), "cost_unknown_no_spot_or_book": len(d) - len(known),
            "realised_funding": _q([x["realised_funding"] for x in d]),
            "covered_ex_post": cov,
            "covered_share_of_cost_known": (cov / len(known)) if known else None,
            "covered_share_strict_all_members": (cov / len(d)) if d else None,
            "ex_ante_covered": sum(x["ex_ante_covered"] is True for x in known),
            "ex_ante_and_ex_post_covered": sum(x["ex_ante_covered"] is True and x["covered_ex_post"] is True
                                               for x in known),
            "coverage_ratio": _q([x["coverage_ratio"] for x in known]),
            "cost": _q([x["cost"] for x in known]),
            "breakeven_apr_perp_notional": _q([x["breakeven_apr_perp_notional"] for x in known]),
            "net": _q([x["net"] for x in known]), "net_on_allocated": _q([x["net_on_allocated"] for x in known])}
    return s


def cohort_report(con, body, sha, pinned, horizon):
    day = dt.date.fromisoformat(body["day"])
    t0, t1, due = window(day, horizon)
    snaps = snapshots(con, t0, t1)
    hours = sorted({ts // 3600 for ts, _, _ in snaps})
    expect = H[horizon][0] * 24
    ms = member_rows(body, snaps, horizon)
    if len(ms) != body.get("c0"):
        raise Refused("COHORT_INCOMPLETE", 3, f"{body['day']}: {len(ms)} rows != c0 {body.get('c0')}")
    gs = groups(ms, horizon)
    return {"cohort": body["day"], "horizon": horizon, "window_utc": [utc(t0), utc(t1)], "window_ts": [t0, t1],
            "due_utc": utc(due), "cohort_file_sha256": sha, "cohort_file_pinned_in_protocol": pinned,
            "cohort_snapshots_ex_ante": body.get("snapshots"),
            "census_snapshots_in_window": len(snaps), "census_snapshots_expected": expect,
            "census_hours_covered": len(hours), "census_hours_missing": expect - len(hours),
            "last_snapshot_utc": utc(snaps[-1][0]) if snaps else None,
            "groups": {k: summarise(v) for k, v in gs.items()}, "members": ms}


def offdb_proposal(cohorts, horizon, files):
    """The entry FACTORY_REGISTRY.md ('HFC-1's udfald fra 08/11 tilføjes til den tid') asks for; proposed, never
    written. attempts 0 / alpha 0: the protocol runs no statistical test (see MILESTONE_REPORT_TOOLS.md)."""
    ident = f"HFC1_OUTCOME_{horizon.upper()}_" + "_".join(cohorts)
    existing = None
    try:
        with open(OFFDB, encoding="utf-8") as f:
            existing = any(s.get("id") == ident for s in json.load(f).get("studies", []))
    except (OSError, ValueError):
        existing = None
    return {"entry": {"id": ident, "files": sorted(files), "lineage": "delta_neutral_funding_carry", "attempts": 0,
                      "alpha": 0.0, "note": "proposed by research/tools/hfc1_report3d.py; not written by the tool",
                      "counted_elsewhere": "protocol entry HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04 (descriptive)",
                      "evidence": f"descriptive {horizon} outcome of cohort(s) {', '.join(cohorts)}; no statistical "
                                  f"test, no p-value", "confidence": "high"},
            "target": os.path.relpath(OFFDB, HERE), "already_present": existing,
            "written": False}


def stored_cohorts(cohort_dir):
    """{day: path} of the cohort files hfc1_daily.py wrote for the protocol's days 11-04..11-24."""
    paths = {}
    for name in sorted(os.listdir(cohort_dir)) if os.path.isdir(cohort_dir) else []:
        if name.endswith(".json"):
            try:
                d = dt.date.fromisoformat(name[:-5])
            except ValueError:
                continue
            if FIRST <= d <= LAST:
                paths[d] = os.path.join(cohort_dir, name)
    return paths


def build(con, cohort_dir, days, horizon, now, pins=PINNED):
    paths = stored_cohorts(cohort_dir)
    want = sorted(days) if days else sorted(paths)
    status, reports = {}, []
    for d in want:
        t0, t1, due = window(d, horizon)
        if d not in paths:
            status[str(d)] = {"status": "NO_COHORT_FILE", "due_utc": utc(due)}
            continue
        if now < due:
            status[str(d)] = {"status": "NOT_DUE", "window_end_utc": utc(t1), "due_utc": utc(due)}
            continue
        body, sha, pinned = load_cohort(paths[d], d, pins)
        reports.append(cohort_report(con, body, sha, pinned, horizon))
        status[str(d)] = {"status": "REPORTED", "due_utc": utc(due)}
    return status, reports


def md(rep):
    L = [f"# HFC-1 {rep['horizon']}-udfald (kørt {rep['run_utc']}{', DRY-RUN syntetisk' if rep['dry_run'] else ''})",
         "", *[f"- {x}" for x in FIXED_LINES], "",
         f"Protokol: `{PROTOCOL}`. Database: `{rep['db_uri']}` (PRAGMA query_only=ON). Resultat-sha256 "
         f"`{rep['result_sha256']}`.", "", "| Kohorte | Status | Tidligst |", "|---|---|---|"]
    for d, s in sorted(rep["cohort_status"].items()):
        L.append(f"| {d} | {s['status']} | {s['due_utc']} |")
    for c in rep["cohorts"]:
        L += ["", f"## Kohorte {c['cohort']} — vindue [{c['window_utc'][0]}, {c['window_utc'][1]})", "",
              f"Census-snapshots i vinduet {c['census_snapshots_in_window']} af forventet "
              f"{c['census_snapshots_expected']} (timer uden snapshot: {c['census_hours_missing']}); kohortefil "
              f"sha256 `{c['cohort_file_sha256'][:12]}…` ({'fastlåst i protokollen' if c['cohort_file_pinned_in_protocol'] else 'ikke fastlåst i protokollen'}).",
              "", "| Gruppe | Medl. | Manglende | Frafald | Obs.-dækning median | Realiseret APR median |",
              "|---|---|---|---|---|---|"]
        for g, s in c["groups"].items():
            L.append(f"| {g} | {s['members']} | {s['missing']} | {s['dropouts']} | {_f(s['obs_coverage']['median'], '%')}"
                     f" | {_f(s['realised_apr']['median'], '%')} |")
        for n in SIZES:
            L += ["", f"**N = {int(n):,} USDT pr. ben** (allokeret kapital 1x = {2 * int(n):,})".replace(",", "."), "",
                  "| Gruppe | Omk. kendt | Uden omk. (n/a) | Dækket ex post (af kendte) | Dækket, streng nævner | "
                  "Ex ante → ex post | Median dækningsgrad | Median break-even APR (perp-notional) | "
                  "Netto USDT median (min; maks) | Netto på allokeret median |", "|---|---|---|---|---|---|---|---|---|---|"]
            for g, s in c["groups"].items():
                x = s[f"N{n}"]
                L.append(f"| {g} | {x['cost_known']} | {x['cost_unknown_no_spot_or_book']} | {x['covered_ex_post']}"
                         f" ({_f(x['covered_share_of_cost_known'], '%')}) | {_f(x['covered_share_strict_all_members'], '%')}"
                         f" | {x['ex_ante_covered']} → {x['ex_ante_and_ex_post_covered']} | "
                         f"{_f(x['coverage_ratio']['median'])} | {_f(x['breakeven_apr_perp_notional']['median'], '%')} | "
                         f"{_f(x['net']['median'])} ({_f(x['net']['min'])}; {_f(x['net']['max'])}) | "
                         f"{_f(x['net_on_allocated']['median'], '%')} |")
        miss = [m for m in c["members"] if m["missing"]]
        L += ["", f"Manglende udfald ({len(miss)}; tælles som ikke dækket, aldrig som succes; bliver i opgørelsen):"]
        L += [f"- {m['symbol']}: {'; '.join(m['missing_reasons'])}" for m in miss] or ["- ingen"]
    L += ["", "## Foreslået offdb-post (skrives ikke af værktøjet)", "", "```json",
          json.dumps(rep["offdb_proposal"], ensure_ascii=False, indent=1, sort_keys=True), "```", ""]
    text = "\n".join(L) + "\n"
    low = text.lower()
    bad = [w for w in FORBIDDEN_WORDS if w in low]
    if bad:
        raise Refused("WORDING", 3, f"forbidden conclusion wording in report: {bad}")
    return text


def _f(v, kind=""):
    if v is None:
        return "n/a"
    return f"{v * 100:.1f} %" if kind == "%" else f"{v:.2f}"


def run(db, cohort_dir, out, days, horizon, now, dry_run=False, pins=PINNED):
    stored = sorted(stored_cohorts(cohort_dir))
    if not any(now >= window(d, horizon)[2] for d in (days or stored)):
        raise Refused("NOT_DUE", 2, json.dumps({str(d): {"status": "NOT_DUE", "due_utc": utc(window(d, horizon)[2])}
                                                for d in sorted(days or stored)}, sort_keys=True))  # DB not opened
    con = connect_ro(db)
    try:
        status, reports = build(con, cohort_dir, days, horizon, now, pins)
    finally:
        con.close()
    if not reports:
        raise Refused("NOT_DUE", 2, json.dumps(status, sort_keys=True))
    cohorts = [r["cohort"] for r in reports]
    base = ("DRYRUN_" if dry_run else "") + f"hfc1_{horizon}_" + "_".join(cohorts)
    files = [os.path.relpath(os.path.join(OUT, base + e), HERE) for e in (".json", ".md")]   # canonical location
    result = {"cohort_status": status, "cohorts": reports, "horizon": horizon, "protocol": PROTOCOL,
              "sizes_usdt_per_leg": [int(n) for n in SIZES], "fixed_lines": list(FIXED_LINES),
              "research_status": "INCONCLUSIVE (beskrivende; ingen test; afgør intet)",
              "offdb_proposal": offdb_proposal(cohorts, horizon, files)}
    rsha = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    rep = {**result, "result_sha256": rsha, "run_utc": utc(now), "db_uri": ro_uri(db), "dry_run": dry_run}
    raw = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False).encode()
    text = md(rep)
    write_outputs(out, base, raw, text)
    return rep, os.path.join(out, base + ".json")


def write_outputs(out, base, raw, text):
    os.makedirs(out, exist_ok=True)
    jp, mp = os.path.join(out, base + ".json"), os.path.join(out, base + ".md")
    if os.path.exists(jp) or os.path.exists(mp):
        try:
            with open(jp, "rb") as f:
                same = json.loads(f.read()).get("result_sha256") == json.loads(raw)["result_sha256"]
        except (OSError, ValueError):
            same = False
        if same:
            return                                       # idempotent: the same result is already on disk
        raise Refused("EXISTS", 3, f"{jp} exists with a different result; not overwritten")
    with open(jp, "wb") as f:
        f.write(raw)
    with open(mp, "w", encoding="utf-8") as f:
        f.write(text)


# ---- synthetic data (--dry-run and tests only) ---------------------------------------------------------------------

SCHEMA = ("CREATE TABLE observations(id INTEGER PRIMARY KEY AUTOINCREMENT, ts, detector, source, instrument, metric, "
          "value, threshold, flagged, payload, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)")


def synthetic(dirpath, day=dt.date(2026, 11, 4), horizon="3d", drop_last=(), sparse=()):
    """A tiny lab.db with hourly census/1 snapshots over the window and a matching cohort file. Members: AAAUSDT
    (passed, high funding), BBBUSDT (passed, low funding), CCCUSDT and DDDUSDT (no spot pair), 1000EEEUSDT
    (multiplier); `drop_last` symbols vanish from the last 6 snapshots, `sparse` ones appear in every third only."""
    db = os.path.join(dirpath, "lab.db")
    con = sqlite3.connect(db)
    con.execute(SCHEMA)
    t0, t1, _ = window(day, horizon)
    rates = {"AAAUSDT": 0.0006, "BBBUSDT": 0.0001, "CCCUSDT": 0.0004, "DDDUSDT": 0.0003, "1000EEEUSDT": 0.0005}
    n = 0
    for i, ts in enumerate(range(t0 - 3 * 86400, t1 + 2 * 3600, 3600)):
        rows = {}
        for s, r in rates.items():
            if s in drop_last and ts >= t1 - 6 * 3600:
                continue
            if s in sparse and t0 <= ts < t1 and i % 3:
                continue
            rows[s] = ["1", "1", str(r * (5 if ts >= t1 else 1)), "1", "1", "1", "1", "1", "1"]
        p = {"columns": ["markPrice", "indexPrice", "lastFundingRate", "lastPrice", "openPrice", "highPrice",
                         "lowPrice", "quoteVolume", "count"], "rows": rows, "coin_perps": sorted(rows)}
        n += 1
        con.execute("INSERT INTO observations(ts, detector, source, instrument, metric, value, flagged, payload, "
                    "prev_hash, hash) VALUES (?, 'census/1', 'x', NULL, 'snapshot', 0, 0, ?, '', ?)",
                    (ts + 120, json.dumps(p), f"h{n}"))
    con.commit()
    con.close()
    rows = [{"symbol": "AAAUSDT", "f8h": 0.0006, "apr": 0.657, "m2": True, "cost_1000": 9.0, "cost_5000": 70.0,
             "covered_3d_1000": False, "covered_3d_5000": False, "covered_14d_1000": True, "covered_14d_5000": False},
            {"symbol": "BBBUSDT", "f8h": 0.0002, "apr": 0.219, "m2": True, "cost_1000": 9.0, "cost_5000": None,
             "drop_size": ["F4 5000"], "covered_3d_1000": False, "covered_14d_1000": False},
            {"symbol": "CCCUSDT", "f8h": 0.0004, "apr": 0.438, "m2": True, "drop": "F1 intet spotpar"},
            {"symbol": "DDDUSDT", "f8h": 0.00015, "apr": 0.164, "m2": False, "drop": "F1 intet spotpar"},
            {"symbol": "1000EEEUSDT", "f8h": 0.0005, "apr": 0.547, "m2": True, "drop": "F1 multiplikator"}]
    cdir = os.path.join(dirpath, "hfc1")
    os.makedirs(cdir, exist_ok=True)
    body = {"day": str(day), "run_ts": t0 + 2400, "snapshots": 72, "c0": len(rows), "rows": rows, "books": {},
            "spot_info_sha256": "0" * 64}
    with open(os.path.join(cdir, f"{day}.json"), "w") as f:
        json.dump(body, f, sort_keys=True)
    return db, cdir


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DB)
    ap.add_argument("--cohort-dir", default=COHORTS)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cohort", action="append", default=[], help="cohort day (repeatable); default all stored")
    ap.add_argument("--horizon", choices=sorted(H), default="3d")
    ap.add_argument("--dry-run", action="store_true", help="synthetic DB and cohort in a temp dir; never lab.db")
    a = ap.parse_args(argv)
    days = [dt.date.fromisoformat(d) for d in a.cohort]
    try:
        if a.dry_run:
            tmp = tempfile.mkdtemp(prefix="hfc1_dry_")
            db, cdir = synthetic(tmp, horizon=a.horizon)
            now = window(dt.date(2026, 11, 4), a.horizon)[2] + 60
            rep, path = run(db, cdir, a.out or os.path.join(tmp, "out"), [dt.date(2026, 11, 4)], a.horizon, now, True,
                            pins={})
        else:
            rep, path = run(a.db, a.cohort_dir, a.out or OUT, days, a.horizon, time.time())
    except Refused as e:
        print(json.dumps({"status": e.status, "detail": e.detail}, ensure_ascii=False))
        return e.code
    print(json.dumps({"status": "REPORTED", "file": path, "result_sha256": rep["result_sha256"],
                      "cohorts": {k: v["status"] for k, v in rep["cohort_status"].items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
