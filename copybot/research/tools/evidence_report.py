"""Director order 75 P4: read-only evidence report per research hypothesis in the factory register.

For every row of the register the report states what was actually examined, which data exist, which data are missing,
whether the result is exploratory or independently validated, whether costs are included, whether it is statistically
interpretable, and why it is PASS, FAIL, BLOCKED or INCONCLUSIVE.

Rules:
- The only input is one register file, research/data/factory/registry.json (schema copybot.factory/1, built by
  research/tools/factory.py). Nothing else is opened: no market data, no database, no network.
- The only output is the file given with --out. The register is never written.
- What the register does not contain stands as MISSING_INPUT. Nothing is guessed or derived from names, and free text
  in the register (e.g. an `evidence` string saying "PASS") is quoted but never interpreted.
- PASS needs status VALIDATED and documented independent validation in the input (see documented_validation). No other
  status and no text can give PASS. The labels are this document's own: the report promotes nothing and changes no
  status, lock, alpha, ledger, book or lane.
- Register text that mentions holdout or 2024 is left out, so no holdout outcome can reach the report.

KNOWN holds three facts the register does not carry, each with its date and source note.

    python3 research/tools/evidence_report.py --out research/desk/EVIDENCE_REPORT_75.md [--registry PATH]
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # copybot/
REGISTRY = os.path.join(HERE, "research", "data", "factory", "registry.json")

MISSING = "MISSING_INPUT"
VERDICTS = ("PASS", "FAIL", "BLOCKED", "INCONCLUSIVE")
FIELDS = ("undersoegt", "data_findes", "data_mangler", "validering", "omkostninger", "statistik", "hvorfor")
FIELD_LABELS = {"undersoegt": "Undersøgt", "data_findes": "Data findes", "data_mangler": "Data mangler",
                "validering": "Eksplorativ / valideret", "omkostninger": "Omkostninger inkluderet",
                "statistik": "Statistisk fortolkeligt", "hvorfor": "Hvorfor"}
GROUPS = (("records", "Lab-eksperimenter (records)"), ("offdb_studies", "Off-database-studier (offdb_studies)"),
          ("hypothesis_pipeline", "Amendment-17-pipelinen (hypothesis_pipeline)"),
          ("ledger_only", "Kun i ledgeren (ledger.entries)"))

NO_STATUS = "(ingen status i registret)"
# status -> (verdict, reason). VALIDATED is decided in verdict_for: PASS only with documented independent validation.
STATUS_MAP = {
    "VALIDATED": ("PASS", "kun med dokumenteret uafhængig validering i input; ellers INCONCLUSIVE"),
    "REJECTED": ("FAIL", "registrets afgørelse; årsagen til afvisningen står ikke i registret"),
    "INCONCLUSIVE": ("INCONCLUSIVE", "registrets egen afgørelse: ingen konklusion"),
    "TESTED": ("INCONCLUSIVE", "testet, men registret har ingen afgørelse"),
    "FROZEN": ("BLOCKED", "låst, men ikke testet; test kræver ledger-opkrævning efter låsen (factory.py)"),
    "APPROVED": ("BLOCKED", "godkendt, men ikke låst eller testet (factory.py)"),
    "PROPOSED": ("BLOCKED", "forslag, ikke testet; godkendelse kræver en menneskelig aktør (factory.py)"),
    "CLOSED": ("INCONCLUSIVE", "lukket uden afgørelse; CLOSED er ikke en afgørelse i factory.py VERDICTS"),
    "EXTERNAL": ("INCONCLUSIVE", "ekstern; registret har ingen afgørelse"),
    "UNKNOWN": ("INCONCLUSIVE", "lab-tilstanden kunne ikke mappes af factory.py"),
    "HOLDOUT_ACCESS_CONTAMINATED": ("BLOCKED", "adgangsbrud på holdout; kan ikke evalueres rent"),
    "PASS_UNREACHABLE / PENDING_FORMAL_CLOSE": ("INCONCLUSIVE", "gaten kan ikke nås og den formelle lukning afventer; "
                                                "ingen påstand om en fordel"),
    "DESIGN_ONLY": ("BLOCKED", "kun design, ikke låst, ingen observationer"),
}
NO_STATUS_RULE = ("INCONCLUSIVE", "rækken har intet statusfelt; tekst i registret tolkes ikke som en afgørelse")
UNMAPPED_RULE = ("INCONCLUSIVE", "ukendt status i registret; kan ikke mappes sikkert")

# Facts not in the register. Exact ids only. A row with an id in the register keeps its register fields and takes the
# status and verdict from here; the others become rows of their own. Never PASS.
KNOWN = (
    {"id": "LQ1", "date": "2026-11-09", "status": "DESIGN_ONLY", "verdict": "BLOCKED",
     "source": "research/desk/lq1/LQ1_PROTOCOL_DRAFT.md",
     "note": "UDKAST, IKKE LÅST: ingen observationer læst, ingen alfa opkrævet, ingen ejergodkendelse. Beslægtet med "
             "LIQREC1 og ikke en selvstændig ny hypotese.",
     "fields": {"undersoegt": "design-only; ingen observationer er læst (kilden)",
                "statistik": "NEJ (ingen observationer; kilden)"}},
    {"id": "N4", "date": "2026-11-09", "status": "HOLDOUT_ACCESS_CONTAMINATED", "verdict": "BLOCKED",
     "source": "research/desk/SECURITY_DEVIATION_N4_HASHING_2026-11-09.md",
     "note": "Adgangsbruddet er dokumenteret; det er ikke en påstand om bevidst tilpasning af en strategi. Fil, historik "
             "og protokol bevares uændret.",
     "fields": {}},
    {"id": "X01_pm_lp_v1", "date": "2026-11-09", "status": "PASS_UNREACHABLE / PENDING_FORMAL_CLOSE",
     "verdict": "INCONCLUSIVE", "source": "research/desk/PM_LP_D1_STATUS_72.md",
     "note": "pm_lp_v1: ingen PASS og ingen påstand om en positiv eller negativ fordel; F2 og pilot er BLOCKED. Endelig "
             "status først efter den oprindelige evalueringsprocedure.",
     "fields": {}},
)

EXPLORATIVE_NOTES = ("screens are exploratory", "never evidence")
GAP_LEGACY = "tested_without_trials_or_alpha (counted as 1 attempt)"
BLOCKED_TEXT = re.compile(r"holdout|2024", re.I)
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S*")
MAX_TEXT = 240


class ReportError(Exception):
    pass


def text(value):
    """Register text made safe for a report: no holdout/2024 text, no URLs, one line, capped."""
    t = " ".join(str(value).split())
    if BLOCKED_TEXT.search(t):
        return "[udeladt: teksten nævner holdout/2024]"
    t = URL.sub("[URL udeladt]", t)
    return t if len(t) <= MAX_TEXT else t[:MAX_TEXT - 1] + "…"


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def miss(note=None):
    return f"{MISSING} ({note})" if note else MISSING


def num(x):
    return f"{x:.6g}" if isinstance(x, float) else str(x)


def is_missing(value):
    return str(value).startswith(MISSING)


def documented_validation(row):
    """The input's documentation of independent validation, or None. All of it is needed: `passed` is exactly True and
    `validator`, `method` and `source` are non-empty strings. Schema copybot.factory/1 has no such field today."""
    v = row.get("independent_validation")
    if not isinstance(v, dict) or v.get("passed") is not True:
        return None
    for key in ("validator", "method", "source"):
        if not isinstance(v.get(key), str) or not v[key].strip():
            return None
    return v


def verdict_for(status, row):
    """(verdict, reason). The only way to PASS is status VALIDATED together with documented independent validation."""
    if status is None:
        return NO_STATUS_RULE
    if status == "VALIDATED":
        v = documented_validation(row)
        if v is None:
            return ("INCONCLUSIVE", "status VALIDATED, men ingen dokumenteret uafhængig validering i input")
        return ("PASS", f"status VALIDATED og dokumenteret uafhængig validering ({text(v['validator'])}; "
                        f"{text(v['source'])})")
    return STATUS_MAP.get(status, UNMAPPED_RULE)


def status_of(row):
    st = row.get("status")
    return st if isinstance(st, str) and st else None


def validering(row, entries, measured=False):
    v = documented_validation(row)
    if v is not None:
        return f"UAFHAENGIGT_VALIDERET ({text(v['validator'])}; {text(v['source'])})"
    notes = [str(e.get("note") or "") for e in entries]
    if not measured and any(m in n for n in notes for m in EXPLORATIVE_NOTES):
        return "EKSPLORATIV (ledger-note: aldrig evidens)"
    return miss("registret dokumenterer ingen uafhængig validering")


def flag_field(row, key, note):
    """JA/NEJ only from a real bool in the input; otherwise MISSING_INPUT with the note."""
    val = row.get(key)
    if isinstance(val, bool):
        return "JA" if val else "NEJ"
    return miss(note)


def ledger_text(entries):
    if not entries:
        return "ikke i ledgeren"
    variants = sum(e.get("variants") or 0 for e in entries)
    alpha = sum(e.get("alpha") or 0 for e in entries)
    return f"ledger: forsøg={len(entries)}, varianter={variants}, alfa={num(float(alpha))}"


def record_row(r, entries, gaps):
    facts = [f"{label}={text(r[key])}" for key, label in (("mechanism_tag", "mekanisme"), ("lab_state", "lab_state"),
                                                          ("trials", "trials"), ("results", "resultatrækker"))
             if r.get(key) is not None]
    if r.get("spec_path"):
        facts.append("spec=" + text(r["spec_path"]) + (f"@{text(r['spec_commit'])[:12]}" if r.get("spec_commit") else ""))
    facts.append(ledger_text(entries))
    found = None
    if r.get("datasets") is not None:
        found = f"datasets={num(r['datasets'])}, distinkte hashes={num(r.get('dataset_hashes', MISSING))}"
    keys = r.get("spec_keys") if isinstance(r.get("spec_keys"), list) else []
    lacks = []
    if r.get("id") in (gaps.get(GAP_LEGACY) or []):
        lacks.append("gaps: tested_without_trials_or_alpha")
    if r.get("datasets") == 0:
        lacks.append("datasets=0 i registret")
    if not r.get("spec_path"):
        lacks.append("ingen spec_path i registret")
    if "data_requirements" in keys:
        lacks.append("spec-felt data_requirements findes; indholdet står ikke i registret")
    costs = [k for k in keys if "cost" in str(k)]
    trials, results = r.get("trials"), r.get("results")
    if isinstance(r.get("statistically_interpretable"), bool):
        stat = "JA" if r["statistically_interpretable"] else "NEJ"
    elif r.get("id") in (gaps.get(GAP_LEGACY) or []):
        stat = "NEJ (legacy: ingen trials- eller alfa-rækker)"
    elif trials == 0 and results == 0:
        stat = "NEJ (ingen trials eller resultater registreret)"
    else:
        stat = miss("registret har ingen z, Sharpe, N_eff, DSR eller PBO pr. forsøg")
    return {"undersoegt": "; ".join(facts) if facts else MISSING, "data_findes": found or MISSING,
            "data_mangler": "; ".join(lacks) if lacks else miss("registret angiver ikke manglende data"),
            "validering": validering(r, entries),
            "omkostninger": flag_field(r, "costs_included", ("spec-felt " + ", ".join(costs) +
                                                             " findes; indholdet står ikke i registret") if costs
                                       else "intet omkostningsfelt i registret"),
            "statistik": stat}


def offdb_row(o, entries, gaps):
    facts = [f"evidens: «{text(o['evidence'])}»"] if o.get("evidence") else []
    facts += [f"{label}={text(o[key])}" for key, label in (("attempts", "attempts"), ("confidence", "konfidens"),
                                                           ("lineage", "lineage")) if o.get(key) is not None]
    if o.get("counted_elsewhere"):
        facts.append(f"talt andetsteds: {text(o['counted_elsewhere'])}")
    if isinstance(o.get("files"), list) and o["files"]:
        facts.append("studiefiler: " + "; ".join(text(f) for f in o["files"]))
    facts.append(ledger_text(entries))
    lacks = "gaps: offdb_unknown_fields" if o.get("id") in (gaps.get("offdb_unknown_fields") or []) else \
        miss("registret angiver ikke manglende data")
    cost_note = ("evidens-teksten nævner omkostninger; om de er indregnet står ikke som felt"
                 if "cost" in str(o.get("evidence") or "").lower() else "intet omkostningsfelt i registret")
    return {"undersoegt": "; ".join(facts) if facts else MISSING,
            "data_findes": miss("registret har ingen dataoversigt for studiet"), "data_mangler": lacks,
            "validering": validering(o, entries), "omkostninger": flag_field(o, "costs_included", cost_note),
            "statistik": flag_field(o, "statistically_interpretable", "registret har ingen statistik pr. studie")}


def pipeline_row(h, entries):
    facts = [f"{label}={text(h[key])}" for key, label in (("type", "type"), ("candidate", "kandidater"),
                                                          ("screens", "screens"), ("measurements", "målinger"))
             if h.get(key) is not None]
    facts.append(ledger_text(entries))
    measured = bool(h.get("measurements"))
    valid = validering(h, entries, measured=measured)
    if isinstance(h.get("statistically_interpretable"), bool):
        stat = "JA" if h["statistically_interpretable"] else "NEJ"
    elif valid.startswith("EKSPLORATIV"):
        stat = "NEJ (eksplorativ screen; aldrig evidens ifølge ledger-noten)"
    else:
        stat = miss("udfaldet står ikke i registret; kun antal")
    return {"undersoegt": "; ".join(facts) if facts else MISSING,
            "data_findes": miss("kun antal i registret"), "data_mangler": miss("registret angiver ikke manglende data"),
            "validering": valid, "omkostninger": flag_field(h, "costs_included", "intet omkostningsfelt i registret"),
            "statistik": stat}


def ledger_only_row(entries, reg):
    sources = sorted({text(e.get("source")) for e in entries if e.get("source")})
    facts = ["kilde: " + ", ".join(sources)] if sources else []
    expl = reg.get("exploration")
    if "exploration lane" in sources and isinstance(expl, dict):
        facts.append(f"kørsler={text(expl.get('runs'))}, kandidater={text(expl.get('candidates'))}")
    facts.append(ledger_text(entries))
    valid = validering({}, entries)
    return {"undersoegt": "; ".join(facts), "data_findes": miss("kun antal i registret"),
            "data_mangler": miss("registret angiver ikke manglende data"), "validering": valid,
            "omkostninger": miss("intet omkostningsfelt i registret"),
            "statistik": ("NEJ (eksplorativ; aldrig evidens ifølge ledger-noten)" if valid.startswith("EKSPLORATIV")
                          else miss("registret har ingen statistik pr. forsøg"))}


def known_row(k):
    out = {f: MISSING for f in FIELDS}
    out.update(k["fields"])
    return out


def _dicts(value, name, flags, key):
    """The objects of a register list that have a string id under `key`; anything else is flagged and left out."""
    if not isinstance(value, list):
        flags.append(f"{name}: {MISSING}")
        return []
    good = [x for x in value if isinstance(x, dict) and isinstance(x.get(key), str)]
    if len(good) != len(value):
        flags.append(f"{name}: {len(value) - len(good)} rækker uden gyldigt id er udeladt")
    return good


def build(reg):
    """View model of the register: {rows, known_extra, flags, ...}. Raises nothing for missing keys; flags them."""
    if not isinstance(reg, dict):
        raise ReportError("registret er ikke et JSON-objekt")
    flags = []
    lg = reg.get("ledger") if isinstance(reg.get("ledger"), dict) else {}
    if not lg:
        flags.append(f"ledger: {MISSING}")
    entries = _dicts(lg.get("entries"), "ledger.entries", flags, "hid") if lg else []
    by_hid = collections.defaultdict(list)
    for e in entries:
        by_hid[e.get("hid")].append(e)
    gaps = {k: v for k, v in reg["gaps"].items() if isinstance(v, list)} if isinstance(reg.get("gaps"), dict) else {}
    if not gaps:
        flags.append(f"gaps: {MISSING}")
    records = _dicts(reg.get("records"), "records", flags, "id")
    offdb = _dicts(reg.get("offdb_studies"), "offdb_studies", flags, "id")
    pipeline = _dicts(reg.get("hypothesis_pipeline"), "hypothesis_pipeline", flags, "key")
    known = {k["id"]: k for k in KNOWN}
    rows, seen = [], collections.Counter()

    def add(group, rid, status, source, fields):
        seen[rid] += 1
        row = {"id": rid, "group": group, "status": status, **fields}
        k = known.get(rid)
        if k:
            verdict, why = k["verdict"], f"{k['status']}: {k['note']} (kilde: {k['source']}, {k['date']})"
            row["status_register"], row["status"] = status, k["status"]
        else:
            verdict, why = verdict_for(status, source)
            why = f"status {status}: {why}" if status else why
            if group == "records" and source.get("lab_state") is not None:
                why += f" (lab_state={text(source['lab_state'])})"
        row["verdict"], row["hvorfor"] = verdict, why
        rows.append(row)

    for r in sorted(records, key=lambda x: x["id"]):
        add("records", r.get("id"), status_of(r), r, record_row(r, by_hid.get(r.get("id"), []), gaps))
    for o in sorted(offdb, key=lambda x: x["id"]):
        add("offdb_studies", o.get("id"), status_of(o), o, offdb_row(o, by_hid.get(o.get("id"), []), gaps))
    for h in sorted(pipeline, key=lambda x: x["key"]):
        add("hypothesis_pipeline", h.get("key"), status_of(h), h, pipeline_row(h, by_hid.get(h.get("key"), [])))
    for hid in sorted(h for h in by_hid if h not in seen):
        add("ledger_only", hid, None, {}, ledger_only_row(by_hid[hid], reg))
    for rid in sorted(r for r, n in seen.items() if n > 1):
        flags.append(f"id {rid} står {seen[rid]} gange på tværs af kilderne")

    extra = []
    for k in sorted(KNOWN, key=lambda x: x["id"]):
        if k["id"] not in seen:
            extra.append({"id": k["id"], "group": "known", "status": k["status"], "verdict": k["verdict"],
                          **known_row(k), "hvorfor": f"{k['status']}: {k['note']} (kilde: {k['source']}, {k['date']})"})

    # the register's own totals against a plain count; differences are shown, never fixed
    if lg and lg.get("attempts") != len(entries):
        flags.append(f"ledger.attempts siger {lg.get('attempts')}, men ledger.entries har {len(entries)} poster")
    by_status = reg.get("by_status")
    counted = collections.Counter(status_of(r) for r in records)
    if isinstance(by_status, dict):
        if dict(counted) != by_status:
            flags.append("by_status afviger fra optællingen over records")
    else:
        flags.append(f"by_status: {MISSING}")
    return {"rows": rows, "known_extra": extra, "flags": flags, "schema": reg.get("schema"),
            "attempts": lg.get("attempts"), "variants": lg.get("variants"),
            "validated": sum(1 for r in records if r.get("status") == "VALIDATED"),
            "validated_documented": sum(1 for r in records
                                        if r.get("status") == "VALIDATED" and documented_validation(r)),
            "n_records": len(records)}


def _table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return out


def _hyp_table(rows):
    return _table(["Id", "Status", "Verdict"] + [FIELD_LABELS[f] for f in FIELDS],
                  [[r["id"], r["status"] or NO_STATUS, r["verdict"]] + [r[f] for f in FIELDS] for r in rows])


def render(view, digest):
    """Markdown. A pure function of the view and the register's hash: no clock, no paths, sorted rows."""
    rows, extra = view["rows"], view["known_extra"]
    L = ["# Evidensrapport (direktørordre 75, P4)", "",
         "Read-only. Genereret af `research/tools/evidence_report.py` fra registret alene.", "",
         f"Input: `registry.json`, sha256 `{digest}`, schema `{view['schema'] or MISSING}`, "
         f"ledger: forsøg {view['attempts'] if view['attempts'] is not None else MISSING}, "
         f"varianter {view['variants'] if view['variants'] is not None else MISSING}.", "",
         "## Hovedkonklusion", ""]
    if view["validated"] == 0:
        L.append(f"**Lab'et har ingen VALIDATED hypoteser.** 0 af {view['n_records']} lab-eksperimenter har status "
                 "VALIDATED, og ingen række har dokumenteret uafhængig validering.")
    else:
        L.append(f"**{view['validated']} af {view['n_records']} lab-eksperimenter har status VALIDATED, og "
                 f"{view['validated_documented']} af dem har dokumenteret uafhængig validering i input.**")
    n_pass = sum(1 for r in rows if r["verdict"] == "PASS")
    L += ["", f"PASS i denne rapport: {n_pass}. **Ingen automatisk promovering:** PASS, FAIL, BLOCKED og INCONCLUSIVE er "
          "etiketter i dette dokument. De ændrer ingen status, lås, alfa, ledger, bog eller bane.", ""]

    L += ["## Fordeling", "", "Verdict pr. kilde (rækker fra registret; kendte forhold uden for registret står særskilt):",
          ""]
    table = []
    for g, label in GROUPS:
        sel = [r for r in rows if r["group"] == g]
        table.append([label, len(sel)] + [sum(1 for r in sel if r["verdict"] == v) for v in VERDICTS])
    table.append(["I alt", len(rows)] + [sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS])
    L += _table(["Kilde", "Rækker"] + list(VERDICTS), table)
    L += ["", "Status pr. række (for id'er i den statiske tabel står den aktuelle status; registrets `by_status` er uændret):",
          ""]
    st = collections.Counter(r["status"] or NO_STATUS for r in rows)
    verdicts_of = collections.defaultdict(collections.Counter)
    for r in rows:
        verdicts_of[r["status"] or NO_STATUS][r["verdict"]] += 1
    L += _table(["Status", "Rækker", "Verdict"],
                [[s, st[s], ", ".join(f"{v} {n}" for v, n in sorted(verdicts_of[s].items()))] for s in sorted(st)])

    L += ["", "## Statusmapping", "",
          "Mappingen står i `STATUS_MAP` i værktøjet. Status uden for tabellen bliver INCONCLUSIVE, aldrig PASS.", ""]
    L += _table(["Status", "Verdict", "Grund"], [[s, v, why] for s, (v, why) in sorted(STATUS_MAP.items())]
                + [[NO_STATUS, *NO_STATUS_RULE], ["(ukendt status)", *UNMAPPED_RULE]])
    L += ["", "PASS kræver status VALIDATED **og** et objekt `independent_validation` i input med `passed` lig `true` og "
          "ikke-tomme `validator`, `method` og `source`. Feltet findes ikke i schema `copybot.factory/1` i dag.", ""]

    L += ["## Sådan læses felterne", "",
          f"- `{MISSING}`: registret indeholder ikke oplysningen. Det er ikke det samme som at den ikke findes andre "
          "steder, og det er ikke en negativ konstatering.",
          "- Omkostninger: `JA`/`NEJ` kun fra feltet `costs_included` (ægte bool). Et spec-felt eller en tekst alene "
          f"giver `{MISSING}`.",
          "- Statistik: `JA`/`NEJ` fra `statistically_interpretable`. Ellers `NEJ` kun når registret selv viser, at der "
          f"intet er at fortolke (ingen trials/resultater, legacy-hul, eksplorativ screen); ellers `{MISSING}`.",
          "- Fritekst fra registret er citeret og afgør ikke noget. Tekst, der nævner holdout eller 2024, er udeladt.", ""]

    L += [f"## Hyppighed af {MISSING}", "", "Antal rækker fra registret pr. felt:", ""]
    table = []
    for f in FIELDS:
        if f == "hvorfor":
            continue
        counts = [sum(1 for r in rows if r["group"] == g and is_missing(r[f])) for g, _ in GROUPS]
        table.append([FIELD_LABELS[f]] + counts + [sum(counts)])
    L += _table(["Felt"] + [g for g, _ in GROUPS] + ["I alt"], table)

    L += ["", "## Kendte forhold (statisk, dateret tabel)", "", "Disse står ikke i registret, eller registrets status er "
          "ikke den aktuelle. Eksakte id'er; intet er udledt af navne.", ""]
    L += _table(["Id", "Dato", "Status", "Verdict", "Note", "Kilde"],
                [[k["id"], k["date"], k["status"], k["verdict"], k["note"], k["source"]]
                 for k in sorted(KNOWN, key=lambda x: x["id"])])

    L += ["", "## Registerkontrol", ""]
    L += [f"- {f}" for f in view["flags"]] if view["flags"] else ["- Ingen afvigelser mellem registrets totaler og optællingen."]

    L += ["", "## Hypoteser", ""]
    for g, label in GROUPS:
        sel = [r for r in rows if r["group"] == g]
        L += [f"### {label}: {len(sel)} rækker", ""]
        L += (_hyp_table(sel) if sel else ["Ingen."]) + [""]
    L += [f"### Kendte forhold uden for registret: {len(extra)} rækker", ""]
    L += (_hyp_table(extra) if extra else ["Ingen."]) + [""]
    return "\n".join(L)


def load(path):
    """(register, sha256 of its bytes). Only a file named registry.json is ever opened, read-only."""
    if os.path.basename(path) != "registry.json":
        raise ReportError(f"input skal hedde registry.json, ikke {os.path.basename(path)}")
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except (ValueError, UnicodeDecodeError) as ex:
        raise ReportError(f"registret kan ikke læses: {ex}") from ex


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--registry", default=REGISTRY)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if os.path.abspath(a.out) == os.path.abspath(a.registry):
        print("evidence_report: --out må ikke være registret", file=sys.stderr)
        return 2
    try:
        reg, digest = load(a.registry)
        body = render(build(reg), digest)
    except (OSError, ReportError) as ex:
        print(f"evidence_report: {ex}", file=sys.stderr)
        return 2
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
