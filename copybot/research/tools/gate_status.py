"""Director order 60 track B (P0): read-only gate-status report for the 2026-11-14 status (stdlib only).

Reads research/desk/GATE_MATRIX.json through research/tools/nov14_readiness.py (imported, never modified) and prints,
for a given UTC time, every gate with a status READY / BLOCKED / WITHDRAWN / NOT_DUE / NEEDS_VERIFIED_OWNER_APPROVAL
and its missing requirements, the known study statuses as the repo documents record them (each one re-found in its
source file at run time, fail-closed), the DNS and data-coverage dependencies, the pin check (verify_hashes) and the
matrix validation. It opens, locks, signs, fetches and activates nothing: no flag is ever assumed, so an owner
approval is always reported as missing. The only file it may write is the --out markdown, never a protected file.

    python3 research/tools/gate_status.py --at 2026-11-14T00:30:00Z
    python3 research/tools/gate_status.py --at 2026-11-14T00:30:00Z --out research/desk/GATE_STATUS_x.md
    python3 research/tools/gate_status.py --check-dns     # only then: `getent hosts` for the static DNS list

Status mapping (from the matrix's own `kind` / `earliest_utc` / `required_flags`, opening_kinds and the actions'
per-study flags; no new rule):
  never                      -> BLOCKED (never opens inside the horizon)
  constraint                 -> READY (always applies; it restricts how an allowed action is done, opens nothing)
  every study of the gate WITHDRAWN (study table below)                 -> WITHDRAWN (stays closed)
  earliest_utc not reached   -> NOT_DUE (missing: the date + the flags)
  date, date reached         -> READY
  date+owner / owner         -> READY only if every required flag is present; else NEEDS_VERIFIED_OWNER_APPROVAL if a
                                missing flag is an owner decision (OWNER_DECISIONS_NOV14.md D-table), else BLOCKED
  date+lock                  -> per study: gate flags + the smallest flag set of the matrix actions that take that study
                                through the gate (opening_kinds: 'only after the study's lock amendment is committed');
                                no such action -> BLOCKED for that study; the gate is READY if READY for one study
READY is additionally capped by nov14_readiness.gate_status: never READY unless that evaluator says OPEN.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
import nov14_readiness as nr  # noqa: E402  (read-only import; that file is not changed)

READY, BLOCKED, WITHDRAWN, NOT_DUE, NEEDS = ("READY", "BLOCKED", "WITHDRAWN", "NOT_DUE",
                                              "NEEDS_VERIFIED_OWNER_APPROVAL")
STATUS_ORDER = (READY, NEEDS, NOT_DUE, BLOCKED, WITHDRAWN)
NO_LOCK_LINE = "Ingen automatisk lås. Ingen gate åbnes af dette værktøj."

OWNER_DECISIONS = os.path.join(HERE, "research", "desk", "OWNER_DECISIONS_NOV14.md")
INBOX = "research/reviews/INBOX.md"
PACKETS = "research/desk/OWNER_DECISION_PACKETS.md"
M27_4 = "research/studies/MISSION27_4_2026-11-02.md"
HFC1_P = "research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md"
MATRIX_REL = "research/desk/GATE_MATRIX.json"
READINESS_REL = "research/desk/NOV14_READINESS.md"

# never opened by this tool, whatever a config line says (order 60 / quarantine rules)
FORBIDDEN_READS = ("N4_KIMCHI_PAIRS", os.sep + "quarantine" + os.sep)

# --- DNS (static; observed, not probed) -------------------------------------------------------------------------
DNS_BLOCKED_HOSTS = ("data-api.binance.vision", "data.binance.vision", "clob.polymarket.com",
                     "gamma-api.polymarket.com")
DNS_LABEL = "BLOKERET (lokal DNS)"
DNS_NOTE = ("Statisk liste: den lokale DNS (192.168.1.3) svarede `::`/0.0.0.0 for disse værter, observeret "
            "2026-11-06..09 (MISSION27_4 afsnit 17-24). Den skal genkontrolleres med `getent hosts <vært>` på dagen "
            "(`--check-dns`). Værktøjet laver ingen netværkskald og omgår ikke filteret.")
DNS_SOURCES = ((M27_4, "Samme DNS-filter blokerer nu også"), (M27_4, "DNS svarer igen `::` for clob/gamma.polymarket.com"),
               (M27_4, "DNS-blokeringen fortsætter (`::` for clob.polymarket.com og data-api.binance.vision)"))

# --- known study statuses (as the repo documents record them; every source is re-found at run time) ------------
# status_of_record: the reporting status. withdrawn: its gates are reported WITHDRAWN (and stay closed).
STUDIES = (
    {"id": "F2", "matrix": "F2", "status": "BLOCKED", "action": ("f2_calibration_run", "F2"),
     "note": "CONDITIONAL; ingen kalibrering eller bekræftelse uden ejerens daterede ja (D3/D4)",
     "sources": ((INBOX, "P1 F2 BLOCKED"), (PACKETS, "F2 er fortsat CONDITIONAL og BLOCKED"))},
    {"id": "A_n6", "matrix": "A_n6", "status": "READY_NOT_LOCKED", "action": ("lock_commit_A", "A_n6"),
     "note": "kun VERIFIED_OWNER_APPROVAL kan låse; chat-ja = UNVERIFIED_ORIGIN, generel instruks = GENERIC_INSTRUCTION",
     "sources": ((INBOX, "forbliver A n6 READY_NOT_LOCKED"), (INBOX, "Direktøren: A n6 kræver"))},
    {"id": "B_n4", "matrix": "B_n4", "status": "WITHDRAWN_BEFORE_LOCK", "withdrawn": True,
     "action": ("lock_commit_B", "B_n4"),
     "note": "i forskningsrapporteringen; registret forbliver BLOCKED indtil en ejerautoriseret overgang; ingen N4b",
     "sources": ((INBOX, "WITHDRAWN_BEFORE_LOCK i forskningsrapporteringen"), (PACKETS, "B-1 (anbefalet)"))},
    {"id": "C1", "matrix": "C1", "status": "READY_NOT_ACTIVE", "action": ("c1_activate", "C1"),
     "note": "ingen rigtig prognose; ingen godkendt forward-1h-kline-kilde (G19)",
     "sources": ((MATRIX_REL, "READY_NOT_ACTIVE"), (INBOX, "C1 READY_NOT_ACTIVE"))},
    {"id": "W0", "matrix": None, "status": "0.0375_LEFT_NO_RANKING_ACCEPTED", "action": ("alpha_charge_w0", "F2"),
     "note": "W0 0,0375 tilbage (3 x alpha_F 0,0125); direktøren har ikke accepteret rangeringen; ingen opkrævning",
     "sources": ((PACKETS, "W0 har 0,0375 tilbage"), (PACKETS, "Direktøren har **ikke** accepteret Claudes rangering"),
                 (INBOX, "W0-rangeringen (F2, LIQPROXY1, FUNDFRAG1) accepteres IKKE endnu"))},
    {"id": "HFC1", "matrix": "HFC1", "status": "DESCRIPTIVE", "action": ("hfc1_report_3d", "HFC1"),
     "note": "beskrivende; kohorterne 11-06, 11-07 og 11-08 mangler (ikke dannet, DNS; efterdannes ikke); "
             "11-04 og 11-05 INCONCLUSIVE",
     "sources": ((INBOX, "kohorterne 11-06, 11-07 og 11-08 forbliver"), (HFC1_P, "## Kohorte 11-06 — IKKE DANNET"),
                 (HFC1_P, "## Kohorte 11-07 — IKKE DANNET"), (HFC1_P, "## Kohorte 11-08 — IKKE DANNET"))},
    {"id": "S1", "matrix": "S1", "status": "OBSERVATION", "action": ("s1_evaluate", "S1"),
     "note": "read-only shadow-job i observationsfase (INBOX: S1 ACTIVE); evaluering tidligst 2026-11-20 09:55:07 UTC; "
             "få nye overgange -> INSUFFICIENT_OBSERVATION, aldrig automatisk PASS",
     "sources": ((M27_4, "S1: 0 nye overgange (fase OBSERVATION)"), (INBOX, "S1 ACTIVE"))},
)

# --- hosts and data coverage per matrix study (and per gate); every source re-found at run time ---------------------
DEPENDENCIES = (
    {"id": "A_n6", "hosts": ("data.binance.vision",), "gates": ("G01_HIST_1114", "G13_LOCK_A"),
     "coverage": "indlæseren skrives først efter låsen; dækningen for n6's explore0-data er ikke opgjort i repoet",
     "sources": ((MATRIX_REL, "fetch only from data.binance.vision through the lab's download path"),)},
    {"id": "A_n6_X3", "hosts": ("data.binance.vision",), "gates": ("G09_COINM_1128",),
     "coverage": "COIN-M cm-sti, tidligst 2026-11-28; dapi.binance.com er ikke tilladt",
     "sources": ((MATRIX_REL, "only from data.binance.vision; dapi.binance.com is not an allowed host"),)},
    {"id": "B_n4", "hosts": ("api.upbit.com",), "gates": ("G08_UPBIT_N4", "G14_LOCK_B"),
     "coverage": "WITHDRAWN_BEFORE_LOCK: ingen adgang; Binance-krydsningens kilde er ikke fastlagt (AMB-19); den "
                 "karantænerede parliste bruges aldrig",
     "sources": ((MATRIX_REL, "Upbit's public API (market/all, candles/days) only for N4's research tool"),)},
    {"id": "F2", "hosts": ("data.binance.vision",), "gates": ("G01_HIST_1114", "G17_F2_CALIBRATION", "G16_F2_WINDOW"),
     "coverage": "lokal cache (kun filnavne talt): i explore0 har 15 af 20 mønter alle 22 måneder (SOL 16, AVAX 16, "
                 "DOT 17, DOGE 18, FIL 15); manglende måneder kræver data.binance.vision",
     "sources": ((MATRIX_REL, "fetch only from data.binance.vision through the lab's download path"),
                 (READINESS_REL, "I explore0 har 15 mønter alle 22 måneder"))},
    {"id": "C1", "hosts": (), "gates": ("G18_C1_ACTIVATION", "G19_FWD_KLINE_SOURCE"),
     "coverage": "ingen godkendt forward-1h-kline-strøm (vært, endpoint og kadence ikke besluttet); daglige "
                 "arkivfiler kommer efter døgnet",
     "sources": ((MATRIX_REL, "there is no approved forward 1h-kline stream"),)},
    {"id": "HFC1", "hosts": ("data-api.binance.vision", "fapi.binance.com"), "gates": ("G21_HFC1_3D",),
     "coverage": "kohortedannelse kræver spotbogen (data-api.binance.vision); 11-06, 11-07 og 11-08 ikke dannet "
                 "(ConnectionRefused, DNS); udfald læses read-only fra lab.db census",
     "sources": ((HFC1_P, "(`data-api.binance.vision` spot, `fapi.binance.com` perp)"),
                 (HFC1_P, "lokal DNS svarer `::` for data-api.binance.vision"))},
    {"id": "STRAKS", "hosts": ("fapi.binance.com",), "gates": ("G22_STRAKS_7D",),
     "coverage": "ren perp-bog (fapi), mærkes normalt; rapporten læser lab.db read-only",
     "sources": ((M27_4, "STRAKS og PAR-BOG (kun perp/fapi) mærkes normalt"),)},
    {"id": "PAIRS", "hosts": ("fapi.binance.com",), "gates": ("G23_PAIRS_1119",),
     "coverage": "ren perp-bog (fapi), mærkes normalt; rapporten læser lab.db read-only",
     "sources": ((M27_4, "STRAKS og PAR-BOG (kun perp/fapi) mærkes normalt"),)},
    {"id": "S1", "hosts": (), "gates": ("G24_S1_EVAL",),
     "coverage": "kun lab.db (mode=ro); S1-hullet er registreret (MONITORING_GAP)",
     "sources": (("research/studies/FACTORY_S1_P0_2026-11-06.md", "| Læseadgang | lab.db åbnes med `mode=ro`"),
                 (INBOX, "S1-hullet registreret"))},
    {"id": "F3", "hosts": ("data.binance.vision",), "gates": ("G09_COINM_1128", "G25_F3_DEFERRED"),
     "coverage": "DEFERRED; COIN-M tidligst 2026-11-28; observationsenhed ikke fastlagt",
     "sources": ((MATRIX_REL, "only from data.binance.vision; dapi.binance.com is not an allowed host"),)},
    {"id": "LIQPROXY1", "hosts": ("fapi.binance.com", "data-api.binance.vision"), "gates": ("G20_W0_ALPHA",),
     "coverage": "kræver nye strømme fwd_tob_universe og fwd_spec_journal (PROPOSED_NEEDS_SEPARATE_APPROVAL)",
     "sources": (("research/desk/protocols/LIQPROXY1_v1.md", "bn_census, fwd_tob_universe, fwd_spec_journal"),
                 ("research/desk/stream_registry.json", "data-api.binance.vision /api/v3/ticker/bookTicker (new"))},
    {"id": "FUNDFRAG1", "hosts": ("fapi.binance.com", "data-api.binance.vision"), "gates": ("G20_W0_ALPHA",),
     "coverage": "kræver ny strøm fwd_spec_journal (PROPOSED_NEEDS_SEPARATE_APPROVAL)",
     "sources": (("research/desk/protocols/FUNDFRAG1_v1.md", "bn_census, fwd_spec_journal"),
                 ("research/desk/stream_registry.json", "data-api.binance.vision exchangeInfo (already fetched hourly)"))},
    {"id": "OPS", "hosts": (), "gates": ("G11_RESTART_1128",), "coverage": "ingen værtsafhængighed", "sources": ()},
)
# outside the matrix, but DNS-affected and needed for the 14/11 picture (not gates; nothing here is touched)
OUTSIDE_MATRIX = (
    {"id": "pm_lp (collector)", "hosts": ("clob.polymarket.com",),
     "coverage": "DEGRADED; urørt (G12_PMLP: aldrig rørt af disse undersøgelser)",
     "sources": (("research/PM_LP_SPEC.md", "GET clob.polymarket.com/rewards/markets/current"), (INBOX, "pm_lp DEGRADED"))},
    {"id": "lane/carry90 spotben (9 konti)", "hosts": ("data-api.binance.vision",),
     "coverage": "ingen equity-mærkning siden 2026-11-08 06:40:31 UTC -> STALE i net_report",
     "sources": (("research/desk/STALE_EQUITY_59C.md", "https://data-api.binance.vision`, som den lokale DNS svarer `::` for"),)},
    {"id": "K05 negRisk v2 (kun design)", "hosts": ("gamma-api.polymarket.com", "clob.polymarket.com"),
     "coverage": "design alene (ordre 60 E); ingen data eller strøm",
     "sources": (("research/desk/PROFIT_SEARCH_2026-11-09.md", "GET på gamma-api.polymarket.com og"),)},
)
GATE_HOSTS = {"G01_HIST_1114": ("data.binance.vision",), "G08_UPBIT_N4": ("api.upbit.com",),
              "G09_COINM_1128": ("data.binance.vision",), "G19_FWD_KLINE_SOURCE": ()}


def _safe_path(root, rel):
    p = os.path.normpath(os.path.join(root, rel))
    if any(f in p for f in FORBIDDEN_READS):
        raise nr.MatrixError("forbidden read: %s" % rel)
    return p


def find_line(rel, needle, root=HERE):
    """1-based line number of the first line containing `needle` in the repo file `rel`, or None (missing file too)."""
    try:
        with open(_safe_path(root, rel), encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if needle in line:
                    return i
    except OSError:
        return None
    return None


def check_sources(sources, root=HERE):
    """[(cite, found)] with cite 'file:line' or 'file (ikke fundet: needle)'."""
    out = []
    for rel, needle in sources:
        n = find_line(rel, needle, root)
        out.append(("%s:%d" % (rel, n), True) if n else ("%s (IKKE FUNDET: %r)" % (rel, needle), False))
    return out


def owner_decision_flags(matrix, path=OWNER_DECISIONS):
    """{flag: 'D<n>'} for every matrix flag named in a D-row of OWNER_DECISIONS_NOV14.md (`x_<id>` = prefix)."""
    every = set()
    for g in matrix.get("gates", []):
        every |= set(g.get("required_flags", []))
    for a in matrix.get("actions", []):
        for fl in (a.get("studies") or {}).values():
            every |= set(fl)
    out = {}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [ln for ln in fh if re.match(r"^\|\s*D\d+\s*\|", ln)]
    except OSError:
        rows = []
    for ln in rows:
        did = re.match(r"^\|\s*(D\d+)", ln).group(1)
        for tok in re.findall(r"`([^`]+)`", ln):
            if tok.endswith("_<id>"):
                for f in every:
                    if f.startswith(tok[:-4]):
                        out.setdefault(f, did)
            elif tok in every:
                out.setdefault(tok, did)
    return out


def owner_flag(flag, odf):
    return flag in odf or flag.startswith("owner_")


def _fmt_flag(f, odf):
    return "%s (%s)" % (f, odf[f]) if f in odf else f


def _flags_status(missing, odf):
    if not missing:
        return READY
    return NEEDS if any(owner_flag(f, odf) for f in missing) else BLOCKED


def study_route_flags(matrix, gid, study):
    """Smallest flag set among the matrix actions that take `study` through gate `gid` (None if no such action)."""
    sets = [frozenset(a["studies"][study]) for a in matrix.get("actions", [])
            if gid in a.get("gates", []) and study in (a.get("studies") or {})]
    if not sets:
        return None
    return sorted(sets, key=lambda s: (len(s), sorted(s)))[0]


def evaluate_gate(matrix, g, t, withdrawn=frozenset(), flags=frozenset(), odf=None):
    """{'id','kind','protects','status','missing':[...],'per_study':{...}} for one gate at epoch t."""
    odf = odf if odf is not None else {}
    flags = frozenset(flags)
    kind = g.get("kind")
    res = {"id": g.get("id"), "kind": kind, "protects": g.get("protects", ""), "earliest_utc": g.get("earliest_utc"),
           "opens_by": g.get("opens_by", ""), "missing": [], "per_study": {}, "hosts": list(GATE_HOSTS.get(g.get("id"), ()))}
    studies = list(g.get("studies", []))
    if kind == "never":
        res.update(status=BLOCKED, missing=["åbner aldrig i horisonten (kind=never)"])
        return res
    if kind == "constraint":
        res.update(status=READY, missing=[])
        return res
    if kind not in nr.KINDS:
        res.update(status=BLOCKED, missing=["ukendt kind %r (fail-closed)" % (kind,)])
        return res
    if studies and all(s in withdrawn for s in studies):
        res.update(status=WITHDRAWN, missing=["alle undersøgelser trukket tilbage før lås (%s); forbliver lukket"
                                              % ", ".join(studies)])
        return res
    try:
        e = nr.gate_earliest(g)
    except nr.MatrixError as exc:
        res.update(status=BLOCKED, missing=["ugyldig earliest_utc: %s" % exc])
        return res
    if kind in ("date", "date+owner", "date+lock") and e is None:
        res.update(status=BLOCKED, missing=["dateret kind uden earliest_utc (fail-closed)"])
        return res
    base = nr.gate_status(g, t, flags)
    gate_missing = sorted(set(g.get("required_flags", [])) - flags)
    if e is not None and t < e:
        res.update(status=NOT_DUE, missing=["dato %s" % g["earliest_utc"]] + [_fmt_flag(f, odf) for f in gate_missing])
        if kind == "date+lock":
            for s in studies:
                if s in withdrawn:
                    res["per_study"][s] = (WITHDRAWN, [])
                    continue
                route = study_route_flags(matrix, g["id"], s)
                miss = ["ingen handling i matrixen"] if route is None else \
                    [_fmt_flag(f, odf) for f in sorted((set(route) | set(gate_missing)) - flags)]
                res["per_study"][s] = (NOT_DUE, miss)
            res["missing"] += ["%s: %s" % (s, ", ".join(m) if m else v) for s, (v, m) in res["per_study"].items()]
        return res
    if kind == "date":
        st = READY
    elif kind in ("date+owner", "owner"):
        st = _flags_status(gate_missing, odf)
        res["missing"] = [_fmt_flag(f, odf) for f in gate_missing]
    else:                                                       # date+lock: per study
        per = {}
        for s in studies:
            if s in withdrawn:
                per[s] = (WITHDRAWN, [])
                continue
            route = study_route_flags(matrix, g["id"], s)
            if route is None:
                per[s] = (BLOCKED, ["ingen handling i matrixen fører %s gennem %s" % (s, g["id"])])
                continue
            miss = sorted((set(route) | set(gate_missing)) - flags)
            per[s] = (_flags_status(miss, odf), [_fmt_flag(f, odf) for f in miss])
        res["per_study"] = per
        got = {v[0] for v in per.values()}
        st = next((x for x in (READY, NEEDS, BLOCKED, WITHDRAWN) if x in got), BLOCKED)
        res["missing"] = ["%s: %s" % (s, ", ".join(m) if m else v) for s, (v, m) in per.items() if v != READY]
    if st == READY and base != "OPEN":                          # never more open than the matrix evaluator
        st = BLOCKED
        res["missing"].append("nov14_readiness.gate_status = %s" % base)
    res["status"] = st
    return res


def withdrawn_studies(study_rows):
    return frozenset(r["matrix"] for r in study_rows if r.get("withdrawn") and r.get("verified") and r.get("matrix"))


def study_rows(matrix, t, root=HERE, studies=STUDIES, flags=frozenset()):
    rows = []
    for s in studies:
        cites = check_sources(s["sources"], root)
        ok = bool(cites) and all(f for _, f in cites)
        act, as_study = s["action"]
        allowed, why = nr.decide(matrix, act, t, as_study, flags)
        rows.append({"id": s["id"], "matrix": s.get("matrix"), "status": s["status"] if ok else "UNVERIFIED_SOURCE",
                     "status_of_record": s["status"], "verified": ok, "withdrawn": bool(s.get("withdrawn")),
                     "note": s["note"], "sources": [c for c, _ in cites], "action": act, "action_study": as_study,
                     "action_allowed": allowed, "action_reasons": why})
    return rows


def dependency_rows(root=HERE, deps=DEPENDENCIES, outside=OUTSIDE_MATRIX, dns_live=None):
    rows = []
    for kind, items in (("matrix", deps), ("uden for matrixen", outside)):
        for d in items:
            hosts = []
            for h in d["hosts"]:
                lab = DNS_LABEL if h in DNS_BLOCKED_HOSTS else "ikke på DNS-listen"
                if dns_live is not None and h in dns_live:
                    lab += "; getent i dag: %s" % dns_live[h]
                hosts.append((h, lab))
            cites = check_sources(d["sources"], root)
            rows.append({"id": d["id"], "scope": kind, "hosts": hosts, "gates": list(d.get("gates", ())),
                         "dns_affected": any(h in DNS_BLOCKED_HOSTS for h in d["hosts"]), "coverage": d["coverage"],
                         "sources": [c for c, _ in cites], "sources_ok": all(f for _, f in cites)})
    return rows


def getent_status(host, runner):
    """Label for one `getent hosts` result. runner(host) -> (returncode, stdout)."""
    rc, out = runner(host)
    if rc == 2:
        return "IKKE FUNDET (getent rc 2)"
    if rc != 0:
        return "FEJL (getent rc %s)" % rc
    addrs = [ln.split()[0] for ln in out.splitlines() if ln.split()]
    if addrs and all(a in ("::", "0.0.0.0") for a in addrs):
        return DNS_LABEL + " (svar %s)" % ", ".join(sorted(set(addrs)))
    return "OPLØSES (%s)" % ", ".join(addrs[:2])


def _getent_runner(host):                                       # only reached with --check-dns
    import subprocess
    p = subprocess.run(["getent", "hosts", host], capture_output=True, text=True, timeout=10, check=False)
    return p.returncode, p.stdout


def check_dns(hosts=DNS_BLOCKED_HOSTS, runner=None):
    runner = runner or _getent_runner
    return {h: getent_status(h, runner) for h in hosts}


def _sha(path):
    try:
        return nr.sha256_file(path)
    except OSError:
        return "MISSING"


def build(matrix, at, root=HERE, matrix_path=nr.MATRIX, readiness_path=nr.READINESS, owner_path=OWNER_DECISIONS,
          dns_live=None, flags=frozenset(), studies=STUDIES, deps=DEPENDENCIES, outside=OUTSIDE_MATRIX):
    """The full report as a dict (deterministic for a fixed `at` and fixed files)."""
    t = nr.to_epoch(at)
    odf = owner_decision_flags(matrix, owner_path)
    srows = study_rows(matrix, t, root, studies, flags)
    wd = withdrawn_studies(srows)
    gates = [evaluate_gate(matrix, g, t, wd, flags, odf) for g in matrix.get("gates", [])]
    counts = {s: sum(1 for g in gates if g["status"] == s) for s in STATUS_ORDER}
    try:
        horizon = nr.parse_utc(matrix.get("horizon_end_utc"))
    except nr.MatrixError:
        horizon = None
    return {
        "at_utc": dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matrix": {"path": os.path.relpath(matrix_path, root) if matrix_path.startswith(root) else matrix_path,
                   "sha256": _sha(matrix_path), "version": matrix.get("version"), "as_of_utc": matrix.get("as_of_utc"),
                   "horizon_end_utc": matrix.get("horizon_end_utc"),
                   "beyond_horizon": horizon is not None and t > horizon},
        "readiness_sha256": _sha(readiness_path), "owner_decisions_sha256": _sha(owner_path),
        "verify_hashes": nr.verify_hashes(matrix, readiness_path, root),
        "pins": len(matrix.get("protocol_identities", [])),
        "validate": nr.validate(matrix, check_tools=os.path.isfile(os.path.join(root, "research/tools/n6_funding.py"))),
        "gates": gates, "counts": counts, "owner_flags": odf, "studies": srows,
        "dependencies": dependency_rows(root, deps, outside, dns_live), "dns_checked": dns_live is not None,
        "dns_live": dns_live or {}, "no_lock_line": NO_LOCK_LINE,
    }


def _cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def render(rep, preview_generated_on=None):
    L = []
    L.append("# Gate-status pr. %s (UTC)" % rep["at_utc"])
    L.append("")
    if preview_generated_on:
        L.append("> **PREVIEW — genereret %s. Dette er IKKE 14/11-statusrapporten.** Den skal genereres igen på dagen "
                 "(`date -u` først), og DNS skal genkontrolleres med `getent hosts`." % preview_generated_on)
        L.append("")
    L.append("**%s**" % rep["no_lock_line"])
    L.append("")
    L.append("Read-only: ingen flag antages, så enhver ejergodkendelse står som manglende, indtil en "
             "VERIFIED_OWNER_APPROVAL faktisk foreligger. Et chat-ja er UNVERIFIED_ORIGIN og åbner intet.")
    L.append("")
    m = rep["matrix"]
    L.append("Kilder: `%s` (%s, as_of %s, horisont %s, sha256 `%s`), `%s` (sha256 `%s`), "
             "`research/desk/OWNER_DECISIONS_NOV14.md` (sha256 `%s`)." % (
                 m["path"], m["version"], m["as_of_utc"], m["horizon_end_utc"], m["sha256"][:16], READINESS_REL,
                 rep["readiness_sha256"][:16], rep["owner_decisions_sha256"][:16]))
    if m["beyond_horizon"]:
        L.append("")
        L.append("> ADVARSEL: tidspunktet ligger efter matrixens horisont; matrixen skal udgives i en ny version.")
    L.append("")
    vh = rep["verify_hashes"]
    L.append("- Pins (`nov14_readiness.verify_hashes`): %s" % (
        "OK (%d/%d filer matcher, tabel = matrix)" % (rep["pins"], rep["pins"]) if not vh else
        "MISMATCH (%d): %s" % (len(vh), "; ".join(vh))))
    va = rep["validate"]
    L.append("- Matrixvalidering (`nov14_readiness.validate`): %s" % ("OK" if not va else
                                                                     "PROBLEMER (%d): %s" % (len(va), "; ".join(va))))
    L.append("")
    L.append("## 1. Optælling")
    L.append("")
    L.append("| Status | Antal gates |")
    L.append("|---|---|")
    for s in STATUS_ORDER:
        L.append("| %s | %d |" % (s, rep["counts"][s]))
    L.append("| i alt | %d |" % len(rep["gates"]))
    nc = sum(1 for g in rep["gates"] if g["kind"] == "constraint")
    L.append("")
    L.append("READY omfatter %d begrænsninger (kind `constraint`), der altid gælder og intet åbner." % nc)
    L.append("")
    L.append("## 2. Gates")
    L.append("")
    L.append("| Gate | Kind | Beskytter | Tidligst (UTC) | Status | Mangler |")
    L.append("|---|---|---|---|---|---|")
    for g in rep["gates"]:
        L.append("| `%s` | %s | %s | %s | **%s** | %s |" % (
            g["id"], g["kind"], _cell(g["protects"]), g["earliest_utc"] or "—", g["status"],
            _cell("; ".join(g["missing"])) if g["missing"] else "—"))
    L.append("")
    L.append("## 3. Kræver verificeret ejergodkendelse (NEEDS_VERIFIED_OWNER_APPROVAL)")
    L.append("")
    needs = [g for g in rep["gates"] if g["status"] == NEEDS]
    if not needs:
        L.append("Ingen.")
    for g in needs:
        L.append("- `%s`: %s" % (g["id"], _cell("; ".join(g["missing"]))))
    L.append("")
    L.append("D-numrene henviser til `research/desk/OWNER_DECISIONS_NOV14.md`. Tidligere godkendelser er "
             "UNVERIFIED_ORIGIN og genbruges ikke.")
    L.append("")
    L.append("## 4. Undersøgelser (status som registreret i repoets dokumenter)")
    L.append("")
    L.append("| Undersøgelse | Status | Note | Matrixhandling på tidspunktet | Kilde |")
    L.append("|---|---|---|---|---|")
    for s in rep["studies"]:
        act = "`%s` (%s): %s" % (s["action"], s["action_study"], "tilladt" if s["action_allowed"] else
                                 "blokeret — " + "; ".join(s["action_reasons"]))
        L.append("| %s | **%s** | %s | %s | %s |" % (s["id"], s["status"], _cell(s["note"]), _cell(act),
                                                    _cell(", ".join(s["sources"]))))
    L.append("")
    L.append("En status vises kun, hvis alle dens kildelinjer findes i filerne nu; ellers UNVERIFIED_SOURCE (fail-closed). "
             "Hvor kilden kun er INBOX-tekst, er INBOX-linjen citeret.")
    L.append("")
    L.append("## 5. DNS- og datadækningsafhængigheder")
    L.append("")
    L.append(DNS_NOTE)
    L.append("")
    if rep["dns_checked"]:
        L.append("`--check-dns` (getent): " + "; ".join("%s: %s" % (h, v) for h, v in sorted(rep["dns_live"].items())))
    else:
        L.append("`getent` ikke kørt (standard). Status for værterne er den statiske observation, ikke dagens.")
    L.append("")
    L.append("| Punkt | Omfang | Gates | Værter | DNS-berørt | Datadækning | Kilde |")
    L.append("|---|---|---|---|---|---|---|")
    for d in rep["dependencies"]:
        hosts = "; ".join("%s: %s" % hl for hl in d["hosts"]) or "ingen vært"
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            d["id"], d["scope"], ", ".join("`%s`" % x for x in d["gates"]) or "—", _cell(hosts),
            "JA" if d["dns_affected"] else "nej", _cell(d["coverage"]),
            _cell(", ".join(d["sources"]) or "—")))
    L.append("")
    L.append("## 6. Statusværdier")
    L.append("")
    L.append("- READY: gaten er åben efter matrixens egne betingelser (dato nået og alle flag til stede), eller en "
             "begrænsning, der altid gælder. Aldrig mere åben end `nov14_readiness.gate_status`.")
    L.append("- NOT_DUE: `earliest_utc` er ikke nået; datoen og flagene står som manglende.")
    L.append("- NEEDS_VERIFIED_OWNER_APPROVAL: datoen er nået (eller der er ingen dato), men mindst ét ejerbeslutningsflag "
             "(D-tabellen) mangler.")
    L.append("- BLOCKED: `never`-gate, malformet gate, ingen matrixhandling for undersøgelsen, eller kun "
             "ikke-ejerflag mangler.")
    L.append("- WITHDRAWN: alle gatens undersøgelser er registreret trukket tilbage før lås; forbliver lukket.")
    L.append("")
    L.append("**%s**" % rep["no_lock_line"])
    L.append("")
    return "\n".join(L)


def protected_paths(matrix, root=HERE):
    p = {nr.MATRIX, nr.READINESS, OWNER_DECISIONS, os.path.join(root, PACKETS), os.path.join(root, INBOX),
         os.path.join(root, "research/desk/blocked_actions.json"), os.path.abspath(__file__),
         os.path.join(root, "research/tools/nov14_readiness.py")}
    p |= {os.path.join(root, r["path"]) for r in matrix.get("protocol_identities", [])}
    for group in (STUDIES, DEPENDENCIES, OUTSIDE_MATRIX):
        for item in group:
            p |= {os.path.join(root, rel) for rel, _ in item.get("sources", ())}
    return {os.path.realpath(x) for x in p}


def write_out(path, text, matrix, root=HERE):
    rp = os.path.realpath(path)
    if not rp.endswith(".md"):
        raise nr.MatrixError("--out must be a .md file")
    if rp in protected_paths(matrix, root) or any(f in rp for f in FORBIDDEN_READS):
        raise nr.MatrixError("--out refuses a protected file: %s" % path)
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write(text)


def now_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--at", help="UTC 'YYYY-MM-DDTHH:MM:SSZ' (default: now)")
    ap.add_argument("--out", help="write the markdown here (never a protected file)")
    ap.add_argument("--check-dns", action="store_true", help="run `getent hosts` for the static DNS list")
    ap.add_argument("--preview-generated-on", help="mark the output as a PREVIEW generated on this date")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--matrix", default=nr.MATRIX)
    args = ap.parse_args(argv)
    at = args.at or now_utc()
    try:
        nr.parse_utc(at)
        m = nr.load(args.matrix)
        rep = build(m, at, matrix_path=args.matrix, dns_live=check_dns() if args.check_dns else None)
        text = json.dumps(rep, ensure_ascii=False, indent=1, sort_keys=True) if args.json else \
            render(rep, args.preview_generated_on)
        if args.out:
            write_out(args.out, text, m)
        else:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
    except nr.MatrixError as exc:
        sys.stderr.write("gate_status: %s\n" % exc)
        return 2
    return 0 if not rep["verify_hashes"] else 1


if __name__ == "__main__":
    sys.exit(main())
