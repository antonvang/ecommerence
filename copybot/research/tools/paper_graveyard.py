"""STRATEGIKIRKEGÅRD for PAPER DASHBOARD V2 (director order 60, track D): a read-only view of every attempt in the
factory register, the failed ones included. Display only: no new research numbers, no activation of anything, no
JavaScript, no external resources.

Data (read-only, opened as bytes and never written; nothing else is read):
- research/data/factory/registry.json (research/tools/factory.py snapshot, schema copybot.factory/1): the
  multiple-testing ledger (ledger.entries, one entry per attempt), ledger.attempts / variants / alpha_gross,
  by_status, records (lab experiments), hypothesis_pipeline (amendment 17), offdb_studies, exploration, gaps;
- research/data/factory/registry.md: its stated totals ("Attempts N, variants V, gross alpha charged A"), its status
  table and the sha256 it names for registry.json, compared with the JSON (a difference is flagged, never fixed);
- research/data/factory/offdb_studies.json: compared with the copy embedded in the register (a study added after the
  snapshot is shown and flagged, and is not counted);
- research/data/factory/migration_v1.json and legacy_manifest_v1.json: the documented limitations per lab experiment
  (decision codes, approval status, lock before screening, universe size, legacy triple).

Every number shown is the register's own; the page only counts rows to check them against the register's totals.
Statuses are the register's `status` values; an attempt without one (amendment-17 screens, off-database studies, the
exploration lane) is shown as "ingen status i registret", never as a pass. Quoted text is the register's own text,
HTML-escaped and truncated (full text in a title tooltip); a URL inside it would be replaced by "[URL udeladt]".

U3 luck/multiple-testing bar: research.tools.video_triage.luck_bar(N, 1.0) with N = the register's attempt count, i.e.
the expected maximum of N independent standard-normal null z values. DIAGNOSTIC_ONLY: no test, no validation. The
register holds no per-attempt z or Sharpe values, so nothing is compared with the bar.
"""
import collections
import datetime as dt
import hashlib
import html
import json
import os
import re

from research.tools import factory
from research.tools import video_triage

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # copybot/
FACTORY = os.path.join(HERE, "research", "data", "factory")
FILES = ("registry.json", "registry.md", "offdb_studies.json", "migration_v1.json", "legacy_manifest_v1.json")
MAXQ = 200
NONE = "NONE"
NONE_LABEL = "ingen status i registret"
STATUS_ORDER = ("REJECTED", "INCONCLUSIVE", "PROPOSED", "APPROVED", "FROZEN", "TESTED", "CLOSED", "EXTERNAL",
                "VALIDATED")
Z_SINGLE = 1.96
INTRO = "Sådan ser en ærlig '99,7 % kills' ud: alle forsøg står her, også dem der fejlede."
LABEL = "DIAGNOSTIC_ONLY — ingen test, ingen validering"
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S*")
MD_TOTALS = re.compile(r"Attempts (\d+), variants (\d+), gross alpha charged ([0-9]+(?:\.[0-9]+)?)")
MD_SHA = re.compile(r"registry\.json` \(sha256 `([0-9a-f]{64})`\)")
STAT_KEYS = re.compile(r"sharpe|zscore|z_score|t_stat|tstat", re.I)

CSS = """
.gv{margin-top:8px}
.gv-intro{margin:0 0 12px;padding:12px 16px;border-radius:12px;border:1px solid var(--line);background:var(--panel);
font-size:14px}.gv-intro b{color:#fff}.gv-intro p{margin:4px 0;color:var(--mut)}.gv-intro p.lead{color:var(--txt);
font-size:15px;font-weight:700}
.gv-flag{margin:0 0 12px;padding:10px 14px;border-radius:12px;border:1px solid var(--neg);background:rgba(255,77,94,.10);
font-size:13px}.gv-flag b{color:var(--neg)}.gv-flag ul{margin:4px 0 0;padding-left:18px}
.gv-note{margin:0 0 12px;padding:10px 14px;border-radius:12px;border:1px solid var(--amb);
background:rgba(245,166,35,.08);font-size:13px}.gv-note b{color:var(--amb)}.gv-note ul{margin:4px 0 0;padding-left:18px}
.gv-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin:0 0 12px}
.gv-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.gv-card h3{margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut)}
.gv-num{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums}.gv-num small{font-size:14px;color:var(--mut);
font-weight:600}
.gv-sub{color:var(--mut);font-size:12px;margin-top:4px}.gv-sub b{color:var(--txt);font-weight:600}
.gv-ok{color:var(--pos);font-weight:700}.gv-bad{color:var(--neg);font-weight:700}
.gv-sts{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.gst{display:inline-block;padding:2px 8px;border-radius:7px;font-size:11px;font-weight:800;letter-spacing:.02em;
white-space:nowrap}
.gst-REJECTED{background:rgba(255,77,94,.15);color:var(--neg)}.gst-INCONCLUSIVE{background:rgba(245,166,35,.15);
color:var(--amb)}.gst-PROPOSED,.gst-APPROVED,.gst-FROZEN,.gst-TESTED{background:rgba(123,97,255,.16);color:#b3a4ff}
.gst-CLOSED{background:var(--panel2);color:#aab4c8}.gst-EXTERNAL{background:rgba(63,169,245,.15);color:var(--blu)}
.gst-VALIDATED{background:rgba(22,199,132,.15);color:var(--pos)}.gst-NONE{background:transparent;color:var(--mut);
border:1px dashed var(--line);font-weight:600}
.gv-u3{background:var(--panel);border:1px solid var(--amb);border-radius:12px;padding:14px 16px;margin:0 0 12px}
.gv-u3 h3{margin:0 0 4px;font-size:13px;letter-spacing:.04em}.gv-u3 .dg{display:inline-block;background:var(--amb);
color:#1a1200;font-weight:900;font-size:11px;padding:3px 8px;border-radius:6px;letter-spacing:.04em;margin-left:6px}
.gv-u3 p{margin:6px 0;font-size:13px;color:var(--mut)}.gv-u3 p b{color:var(--txt)}
.gv-u3 ul{margin:4px 0;padding-left:18px;font-size:12px;color:var(--mut)}
.u3bar{display:block;width:100%;height:auto;max-width:760px;margin:6px 0}
.u3bar .trk{fill:#1b2232}.u3bar .fil{fill:rgba(245,166,35,.55)}.u3bar .ref{stroke:#8a96ad;stroke-width:2;
stroke-dasharray:4 3}.u3bar .mx{stroke:var(--amb);stroke-width:3}.u3bar text{fill:#8a96ad;font:12px ui-monospace,Menlo,
Consolas,monospace}.u3bar text.hi{fill:#f5a623;font-weight:800}
.gv-filters{display:flex;flex-direction:column;gap:8px;background:var(--panel);border:1px solid var(--line);
border-radius:12px;padding:12px;margin:0 0 12px}
.gv-filters .frow>b{width:72px}
.gv-pill small{opacity:.75;margin-left:4px}
.gv-box{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:auto;max-height:78vh}
.gv-t{width:100%;border-collapse:collapse;font-size:12px;min-width:1080px;table-layout:fixed}
.gv-t col.c0{width:44px}.gv-t col.c1{width:15%}.gv-t col.c2{width:14%}.gv-t col.c3{width:118px}.gv-t col.c4{width:24%}
.gv-t col.c5{width:12%}.gv-t col.c6{width:17%}.gv-t col.c7{width:14%}
.gv-t th{position:sticky;top:0;z-index:1;background:var(--panel2);color:var(--mut);text-align:left;font-weight:700;
font-size:11px;text-transform:uppercase;letter-spacing:.06em;padding:8px 10px;border-bottom:1px solid var(--line)}
.gv-t td{padding:7px 10px;border-top:1px solid var(--line);vertical-align:top;color:var(--txt)}
.gv-t tr.gv-r:nth-child(even) td{background:rgba(255,255,255,.015)}
.gv-t .sq{color:var(--mut);font-variant-numeric:tabular-nums;white-space:nowrap}
.gv-t .gid{font:600 12px ui-monospace,Menlo,Consolas,monospace;overflow-wrap:anywhere}
.gv-t .gid .gv-sub{display:block;font:400 11px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin-top:3px}
.gv-t .lin{overflow-wrap:anywhere}.gv-t .lin span{display:block;color:var(--mut);font-size:11px}
.gv-t .q{color:#c3cbdb}.gv-t .q span{display:block;color:var(--mut);font-size:11px;margin-top:2px}
.gv-t .lim span{display:inline-block;margin:0 4px 3px 0;padding:1px 6px;border-radius:5px;background:var(--panel2);
color:#aab4c8;font-size:11px}
.gv-t .gsrc{font:11px ui-monospace,Menlo,Consolas,monospace;color:var(--blu);overflow-wrap:anywhere}
.gv-t .gsrc span{display:block;color:var(--mut);margin-top:2px}.gv-t .q,.gv-t .lim{overflow-wrap:anywhere}
.gv-t .na{color:var(--mut)}.gv-t .lim span.na{background:none;padding:0}
.gv-t .gst-NONE{white-space:normal;text-align:center}
.gv-h3{margin:16px 0 8px;font-size:13px;letter-spacing:.06em;text-transform:uppercase}
.gv-h3 small{color:var(--mut);font-weight:400;text-transform:none;letter-spacing:0}
.gv-foot{margin:8px 0 0;font-size:12px;color:var(--mut)}.gv-foot b{color:var(--txt)}
"""


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def clean(s):
    """The register's own text with any URL replaced (the page carries no URLs)."""
    return URL.sub("[URL udeladt]", "" if s is None else str(s))


def sid(s):
    """CSS-safe status key."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


def quote(s, n=MAXQ):
    """Verbatim, escaped, truncated; the full text goes into a title tooltip when cut."""
    t = clean(s)
    if len(t) <= n:
        return e(t)
    return f'<span title="{e(t)}">{e(t[:n - 1])}…</span>'


def num(x):
    return f"{x:,}".replace(",", ".")


def day(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d") if ts else None


def load(path=FACTORY):
    """Bytes of the five factory files (read-only). Returns {name: bytes or None}."""
    out = {}
    for name in FILES:
        p = os.path.join(path, name)
        try:
            with open(p, "rb") as f:
                out[name] = f.read()
        except OSError:
            out[name] = None
    return out


def _json(raw):
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def line_of(lines, field, value):
    """1-based line in registry.json where `"field": value` first stands (indent=1 dump), else None."""
    needle = f'"{field}": {json.dumps(value, ensure_ascii=False)}'
    for i, ln in enumerate(lines, 1):
        s = ln.strip().rstrip(",")
        if s == needle:
            return i
    return None


def has_stats(obj):
    """True if any key of the register looks like a per-attempt z/Sharpe/t value."""
    if isinstance(obj, dict):
        return any(STAT_KEYS.search(str(k)) or has_stats(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(has_stats(v) for v in obj)
    return False


def decision_code(text):
    m = re.match(r"([A-Z][A-Z_]{3,})\b", text or "")
    return m.group(1) if m else (text or "")


def build(raw):
    """View model of the register. Raises nothing for a malformed or missing register; `error` says what is wrong."""
    reg = _json(raw.get("registry.json"))
    if not isinstance(reg, dict) or not isinstance(reg.get("ledger"), dict):
        why = "registry.json mangler" if raw.get("registry.json") is None else "registry.json kan ikke læses"
        return {"error": why}
    lg = reg["ledger"]
    entries = sorted(lg.get("entries") or [], key=lambda x: x.get("seq", 0))
    lines = raw["registry.json"].decode("utf-8").splitlines()
    recs = {r.get("id"): r for r in reg.get("records") or []}
    offr = {o.get("id"): o for o in reg.get("offdb_studies") or []}
    pipe = {h.get("key"): h for h in reg.get("hypothesis_pipeline") or []}
    mig = {r.get("exp_id"): r for r in (_json(raw.get("migration_v1.json")) or {}).get("rows") or []}
    legacy = {t[0]: t for t in (_json(raw.get("legacy_manifest_v1.json")) or {}).get("triples") or [] if t}
    offf = (_json(raw.get("offdb_studies.json")) or {}).get("studies") or []
    gap_key = next((k for k in (reg.get("gaps") or {}) if k.startswith("tested_without_trials")), None)
    gap_ids = set((reg.get("gaps") or {}).get(gap_key) or ())
    expl = reg.get("exploration") or {}

    def record_cells(r, row):
        st = r.get("status") or NONE
        row["status"], row["tag"] = st, r.get("mechanism_tag")
        row["outcome"] = [("lab_state", r.get("lab_state")), ("results-rækker i lab.db", r.get("results")),
                          ("trials", r.get("trials"))]
        row["outcome_note"] = "Ingen begrundelsestekst i registret; kun resultatlabel og antal."
        keys = set(r.get("spec_keys") or ())
        ck = sorted(k for k in keys if "cost" in k)
        row["cost"] = None
        row["cost_note"] = ("spec-felt " + ", ".join(f"«{k}»" for k in ck) + " findes; indholdet står ikke i "
                            "registret") if ck else None
        lim = []
        m = mig.get(r.get("id")) or {}
        for d in m.get("decisions") or []:
            lim.append((decision_code(d), d))
        if m.get("approval_status") and m["approval_status"] not in (c for c, _ in lim):
            lim.append((f"approval {m['approval_status']}", "migration_v1 approval_status"))
        if m.get("spec_locked_before_screening") is not None:
            lim.append(("spec låst før screening: " + ("ja" if m["spec_locked_before_screening"] else "nej"),
                        "migration_v1 spec_locked_before_screening"))
        if isinstance(m.get("universe"), list):
            lim.append((f"univers {len(m['universe'])} symboler", "migration_v1 universe"))
        if r.get("id") in gap_ids:
            lim.append((gap_key, "registry.json gaps"))
        t = legacy.get(r.get("id"))
        if t:
            lim.append((f"legacy-triple (protokol {t[2] if len(t) > 2 and t[2] is not None else '–'})",
                        "legacy_manifest_v1 triples"))
        row["limits"] = lim
        src = [f"registry.json:L{line_of(lines, 'id', r.get('id'))}" if line_of(lines, "id", r.get("id"))
               else "registry.json"]
        if r.get("spec_path"):
            src.append(f"{r['spec_path']} @{(r.get('spec_commit') or '–')[:12]}")
        row["src"] = src

    def offdb_cells(o, row):
        row["status"], row["tag"] = NONE, o.get("lineage")
        row["outcome"] = [("evidence", o.get("evidence")), ("confidence", o.get("confidence")),
                          ("attempts (studiefelt)", o.get("attempts"))]
        row["outcome_note"] = None
        ev = o.get("evidence") or ""
        row["cost"] = ev if "cost" in ev.lower() else None
        row["limits"] = [(o.get("counted_elsewhere"), "counted_elsewhere")] if o.get("counted_elsewhere") else []
        row["src"] = list(o.get("files") or [])

    def pipe_cells(h, row):
        row["status"], row["tag"] = NONE, h.get("type")
        row["outcome"] = [("candidate", h.get("candidate")), ("screens", h.get("screens")),
                          ("measurements", h.get("measurements"))]
        row["outcome_note"] = "Udfaldet af screeningen står ikke i registret; kun antal."
        row["cost"], row["limits"], row["src"] = None, [], ["lab.db events (amendment 17)"]

    rows = []
    for x in entries:
        hid = x.get("hid")
        row = {"id": hid, "seq": x.get("seq"), "lineage": x.get("lineage"), "source": x.get("source"),
               "variants": x.get("variants"), "alpha": x.get("alpha"), "date": day(x.get("ts")), "note": x.get("note"),
               "ledger": True}
        if x.get("source") == "lab" and hid in recs:
            record_cells(recs[hid], row)
        elif hid in offr:
            offdb_cells(offr[hid], row)
        elif hid in pipe:
            pipe_cells(pipe[hid], row)
        else:
            row.update(status=NONE, tag=None, cost=None, limits=[], src=[], outcome_note=None,
                       outcome=[("runs", expl.get("runs")), ("candidates", expl.get("candidates"))]
                       if hid == "explore0" else [])
        ln = line_of(lines, "hid", hid)
        row["src"] = [f"registry.json:L{ln} (ledger seq {x.get('seq')})" if ln else "registry.json"] + \
            [s for s in row["src"] if not s.startswith("registry.json")]
        rows.append(row)

    in_ledger = {x.get("hid") for x in entries}
    extra = []
    for r in reg.get("records") or []:
        if r.get("id") not in in_ledger:
            row = {"id": r.get("id"), "seq": None, "lineage": r.get("lineage"), "source": "lab (record)",
                   "variants": None, "alpha": r.get("alpha_spent"), "date": day(r.get("created_ts")), "note": None,
                   "ledger": False}
            record_cells(r, row)
            extra.append(row)
    for o in reg.get("offdb_studies") or []:
        if o.get("id") not in in_ledger:
            row = {"id": o.get("id"), "seq": None, "lineage": o.get("lineage"), "source": "off-database study",
                   "variants": None, "alpha": o.get("alpha"), "date": None, "note": o.get("note"), "ledger": False}
            offdb_cells(o, row)
            ln = line_of(lines, "id", o.get("id"))
            row["src"] = ([f"registry.json:L{ln}"] if ln else []) + row["src"]
            extra.append(row)
    for h in reg.get("hypothesis_pipeline") or []:
        if h.get("key") not in in_ledger:
            row = {"id": h.get("key"), "seq": None, "lineage": f"m17:{h.get('type') or h.get('key')}",
                   "source": "amendment 17", "variants": None, "alpha": h.get("alpha"), "date": None, "note": None,
                   "ledger": False}
            pipe_cells(h, row)
            ln = line_of(lines, "key", h.get("key"))
            row["src"] = ([f"registry.json:L{ln}"] if ln else []) + row["src"]
            extra.append(row)
    late = [o for o in offf if o.get("id") not in offr]
    for o in late:
        row = {"id": o.get("id"), "seq": None, "lineage": o.get("lineage"), "source": "offdb_studies.json (ikke i "
               "registersnapshot)", "variants": None, "alpha": o.get("alpha"), "date": None, "note": o.get("note"),
               "ledger": False}
        offdb_cells(o, row)
        row["src"] = ["offdb_studies.json"] + row["src"]
        extra.append(row)

    # --- checks: the register's own totals against a plain count of its rows; differences are flagged only ---
    flags, notes = [], []
    attempts, variants, alpha = lg.get("attempts"), lg.get("variants"), lg.get("alpha_gross")
    lin = lg.get("lineages") or {}
    count = {"entries": len(entries), "unique_ids": len(in_ledger),
             "seq_ok": [x.get("seq") for x in entries] == list(range(len(entries))),
             "variants": sum(x.get("variants") or 0 for x in entries),
             "alpha": round(sum(x.get("alpha") or 0 for x in entries), 10),
             "lineage_attempts": sum(v.get("attempts") or 0 for v in lin.values()),
             "lineages": len(lin), "by_source": collections.Counter(x.get("source") for x in entries)}
    if count["entries"] != attempts:
        flags.append(f"ledger.entries har {count['entries']} poster, men ledger.attempts siger {attempts}")
    if count["unique_ids"] != count["entries"]:
        flags.append(f"{count['entries'] - count['unique_ids']} gentagne id'er i ledger.entries")
    if not count["seq_ok"]:
        flags.append("ledger seq er ikke 0..N-1")
    if count["variants"] != variants:
        flags.append(f"sum af variants i ledger.entries er {count['variants']}, ledger.variants siger {variants}")
    if alpha is None or abs(count["alpha"] - alpha) > 1e-9:
        flags.append(f"sum af alpha i ledger.entries er {count['alpha']}, ledger.alpha_gross siger {alpha}")
    if count["lineage_attempts"] != attempts:
        flags.append(f"sum af attempts over ledger.lineages er {count['lineage_attempts']}, ledger.attempts {attempts}")
    try:
        chk = factory.Ledger()
        chk.entries = [dict(x) for x in entries]
        chain = chk.verify()
    except Exception as ex:          # noqa: BLE001 - any break is reported, never repaired
        chain = False
        flags.append(f"hash-kæden i ledger.entries holder ikke: {ex}")
    md = (raw.get("registry.md") or b"").decode("utf-8", "replace")
    m = MD_TOTALS.search(md)
    md_tot = None
    if m:
        md_tot = (int(m.group(1)), int(m.group(2)), float(m.group(3)))
        if md_tot[0] != attempts or md_tot[1] != variants or abs(md_tot[2] - (alpha or 0)) > 5e-7:
            flags.append(f"registry.md siger attempts {md_tot[0]}, variants {md_tot[1]}, alpha {m.group(3)}; "
                         f"registry.json siger {attempts}, {variants}, {alpha}")
    else:
        flags.append("registry.md mangler linjen 'Attempts N, variants V, gross alpha charged A'")
    md_status = dict((k, int(v)) for k, v in re.findall(r"^\| ([A-Z_]+) \| (\d+) \|$", md, re.M))
    by_status = reg.get("by_status") or {}
    if md_status and md_status != by_status:
        flags.append(f"statustabellen i registry.md {md_status} afviger fra by_status {by_status}")
    rec_status = collections.Counter(r.get("status") for r in reg.get("records") or [])
    if dict(rec_status) != by_status:
        flags.append(f"optalt status over records {dict(rec_status)} afviger fra by_status {by_status}")
    sha = hashlib.sha256(raw["registry.json"]).hexdigest()
    ms = MD_SHA.search(md)
    if ms and ms.group(1) != sha:
        flags.append(f"registry.md nævner sha256 {ms.group(1)[:12]}…, men registry.json har {sha[:12]}…")
    for o in late:
        notes.append(f"offdb_studies.json har studiet {o.get('id')} (attempts {o.get('attempts')}), som ikke er i "
                     f"registersnapshottet; registret er ikke genereret igen, og studiet tælles ikke her.")
    for o in offf:
        if o.get("id") in offr and o != offr[o.get("id")]:
            notes.append(f"offdb_studies.json og registrets kopi af {o.get('id')} er forskellige; registrets kopi vises.")
    for name in FILES:
        if raw.get(name) is None:
            notes.append(f"{name} findes ikke; dens felter vises som –.")
    return {"error": None, "reg": reg, "rows": rows, "extra": extra, "attempts": attempts, "variants": variants,
            "alpha": alpha, "by_status": by_status, "count": count, "flags": flags, "notes": notes, "sha": sha,
            "md_sha_ok": bool(ms and ms.group(1) == sha), "md_tot": md_tot, "chain": chain,
            "stats_present": has_stats(reg.get("ledger")) or has_stats(reg.get("records")),
            "offsets": reg.get("family_alpha_rows") or {}}


def status_chip(st):
    return (f'<span class="gst gst-{sid(st)}">{e(st)}</span>' if st != NONE
            else f'<span class="gst gst-NONE">{e(NONE_LABEL)}</span>')


def u3_svg(bar):
    """Static z axis 0..5 with the single-test reference (1.96) and E[max z] under N null trials."""
    w, h, x0, x1 = 760, 74, 20, 740
    top = 5.0

    def X(z):
        return x0 + (x1 - x0) * max(0.0, min(z, top)) / top
    o = [f'<svg class="u3bar" viewBox="0 0 {w} {h}" role="img" aria-label="U3 luck bar, diagnostisk">',
         f'<rect class="trk" x="{x0}" y="26" width="{x1 - x0}" height="14" rx="4"/>',
         f'<rect class="fil" x="{x0}" y="26" width="{X(bar) - x0:.1f}" height="14" rx="4"/>',
         f'<line class="ref" x1="{X(Z_SINGLE):.1f}" x2="{X(Z_SINGLE):.1f}" y1="18" y2="48"/>',
         f'<line class="mx" x1="{X(bar):.1f}" x2="{X(bar):.1f}" y1="14" y2="52"/>',
         f'<text x="{X(Z_SINGLE):.1f}" y="12" text-anchor="middle">1,96 (én test, 5 % tosidet)</text>',
         f'<text class="hi" x="{X(bar):.1f}" y="66" text-anchor="middle">E[max z] ≈ {bar:.2f}</text>']
    for z in range(0, 6):
        o.append(f'<text x="{X(z):.1f}" y="66" text-anchor="middle">{z}</text>' if abs(z - bar) > 0.45
                 else "")
    o.append("</svg>")
    return "".join(o)


def row_html(r, lid):
    cls = f"gv-r gs-{sid(r['status'])} gl-{lid[r['lineage']]}"
    seq = r["seq"] if r["seq"] is not None else "–"
    tag = f"<span>{e(r['tag'])}</span>" if r.get("tag") and r["tag"] != r["lineage"] else ""
    meta = []
    if r.get("variants") is not None:
        meta.append(f"varianter {r['variants']}")
    if r.get("alpha") is not None:
        meta.append(f"alfa {r['alpha']:.6g}")
    if r.get("date"):
        meta.append(r["date"])
    out = []
    for k, v in r.get("outcome") or []:
        if v is not None:
            out.append(f"{e(k)}: <q>{quote(v)}</q>" if isinstance(v, str) else f"{e(k)}: {e(v)}")
    oc = " · ".join(out) or '<span class="na">–</span>'
    if r.get("outcome_note"):
        oc += f"<span>{e(r['outcome_note'])}</span>"
    if r.get("note"):
        oc += f"<span>ledger-note: <q>{quote(r['note'], 160)}</q></span>"
    cost = (f"<q>{quote(r['cost'], 160)}</q>" if r.get("cost") else
            f'<span class="na">{e(r["cost_note"])}</span>' if r.get("cost_note") else '<span class="na">–</span>')
    lim = "".join(f'<span title="{e(clean(full))}">{e(clean(short)[:90])}</span>' for short, full in r["limits"]) \
        if r.get("limits") else '<span class="na">–</span>'
    src = "".join(f"<span>{e(clean(s))}</span>" if k else e(clean(s)) for k, s in enumerate(r.get("src") or [])) \
        or '<span class="na">–</span>'
    return (f'<tr class="{cls}" data-id="{e(r["id"])}"><td class="sq">{seq}</td><td class="gid">{e(r["id"])}'
            f'<span class="gv-sub">{e(r["source"])}{(" · " + e(" · ".join(meta))) if meta else ""}</span></td>'
            f'<td class="lin">{e(r["lineage"])}{tag}</td><td>{status_chip(r["status"])}</td><td class="q">{oc}</td>'
            f'<td class="q">{cost}</td><td class="lim">{lim}</td><td class="gsrc">{src}</td></tr>')


HEAD = ('<colgroup>' + "".join(f'<col class="c{i}">' for i in range(8)) + "</colgroup><thead>"
        "<tr><th>Seq</th><th>Id · kilde</th><th>Lineage · mekanisme</th><th>Status</th><th>Udfald som registreret"
        "</th><th>Omkostninger</th><th>Databegrænsninger</th><th>Kilde (fil/linje/commit)</th></tr></thead>")


def section(path=FACTORY):
    """(radio inputs, css, html) of the STRATEGIKIRKEGÅRD section; the radios go before .wrap like the other filters."""
    v = build(load(path))
    head = ['<section class="gv" id="kirkegaard">',
            '<h2>Strategikirkegård <small>· alle registrerede forsøg fra fabriksregistret · kun visning · intet '
            'aktiveres herfra</small></h2>',
            f'<div class="gv-intro"><p class="lead">{e(INTRO)}</p><p>Labbets regel: <b>lås før data</b> '
            '(spec og kriterier låses i git, før data ses), <b>holdout</b> (2024 røres ikke) og <b>kun fremad</b> '
            '(forward-only: nye data efter låsen). Et forsøg tæller, også når det fejler; alfa refunderes aldrig.</p>'
            '<p>Tallene og teksterne er registrets egne (research/data/factory, read-only). Siden regner ingen nye '
            'forskningsresultater og validerer intet.</p></div>']
    if v["error"]:
        head.append(f'<div class="gv-flag"><b>Registret kan ikke vises:</b> {e(v["error"])} '
                    f'({e(os.path.join(path, "registry.json"))}).</div></section>')
        return "", CSS, "\n".join(head)
    rows, extra = v["rows"], v["extra"]
    allrows = rows + extra
    st_count = collections.Counter(r["status"] for r in allrows)
    sts = [s for s in STATUS_ORDER if s in st_count] + sorted(s for s in st_count if s not in STATUS_ORDER
                                                              and s != NONE) + ([NONE] if NONE in st_count else [])
    lin_count = collections.Counter(r["lineage"] for r in allrows)
    lins = sorted(lin_count, key=lambda x: (-lin_count[x], str(x)))
    lid = {x: i for i, x in enumerate(lins)}
    radios = [f'<input class="f" type="radio" name="gs" id="gs-{sid(s)}"{" checked" if s == "all" else ""}>'
              for s in ["all"] + sts]
    radios += [f'<input class="f" type="radio" name="gl" id="gl-{i}"{" checked" if i == "all" else ""}>'
               for i in ["all"] + list(range(len(lins)))]
    on = "{background:var(--acc);color:#fff;border-color:var(--acc)}"
    css = [CSS]
    for s in ["all"] + [sid(x) for x in sts]:
        css.append(f"#gs-{s}:checked~.wrap label[for=gs-{s}]{on}")
        if s != "all":
            css.append(f"#gs-{s}:checked~.wrap .gv-r:not(.gs-{s}){{display:none}}")
    for i in ["all"] + list(range(len(lins))):
        css.append(f"#gl-{i}:checked~.wrap label[for=gl-{i}]{on}")
        if i != "all":
            css.append(f"#gl-{i}:checked~.wrap .gv-r:not(.gl-{i}){{display:none}}")

    o = head
    if v["flags"]:
        o.append('<div class="gv-flag" id="gv-flags"><b>AFVIGELSE i registret</b> (vist, ikke rettet; tallene ovenfor '
                 'er registrets egne):<ul>' + "".join(f"<li>{e(f)}</li>" for f in v["flags"]) + "</ul></div>")
    if v["notes"]:
        o.append('<div class="gv-note" id="gv-notes"><b>Bemærk</b><ul>' + "".join(f"<li>{e(n)}</li>"
                                                                                 for n in v["notes"]) + "</ul></div>")
    c = v["count"]
    ok = not any(f.startswith(("ledger.entries", "registry.md siger", "sum af attempts")) for f in v["flags"])
    chk = (f'<span class="gv-ok">✓ optalt {c["entries"]} poster i ledger.entries</span>' if ok
           else f'<span class="gv-bad">✗ optalt {c["entries"]} poster i ledger.entries</span>')
    md = (f"registry.md: {v['md_tot'][0]}" if v["md_tot"] else "registry.md: –")
    src = c["by_source"]
    o.append('<div class="gv-cards">')
    o.append(f'<div class="gv-card" id="gv-attempts"><h3>Registrerede forsøg</h3><div class="gv-num">'
             f'{e(v["attempts"])}<small> forsøg</small></div><div class="gv-sub"><b>{e(num(v["variants"]))}</b> '
             f'varianter · {c["lineages"]} lineages · registrets egne tal (ledger.attempts / ledger.variants)</div>'
             f'<div class="gv-sub">{chk} · {e(md)} · hash-kæde '
             f'{"OK" if v["chain"] else "BRUDT"}</div><div class="gv-sub">'
             + " · ".join(f"{e(k)} {n}" for k, n in sorted(src.items(), key=lambda kv: (-kv[1], str(kv[0]))))
             + "</div></div>")
    bs = v["by_status"]
    order = [s for s in STATUS_ORDER if s in bs] + sorted(s for s in bs if s not in STATUS_ORDER)
    none_n = sum(1 for r in rows if r["status"] == NONE)
    o.append(f'<div class="gv-card" id="gv-status"><h3>Status (by_status, {sum(bs.values())} lab-eksperimenter)</h3>'
             '<div class="gv-sts">' + "".join(f'<span class="gst gst-{sid(s)}">{e(s)} {e(bs[s])}</span>' for s in order)
             + "</div>"
             + ('<div class="gv-sub">Ingen post i registret har status <b>VALIDATED</b>.</div>'
                if "VALIDATED" not in bs else "")
             + f'<div class="gv-sub">{none_n} af {len(rows)} forsøg har {e(NONE_LABEL)} (amendment-17-screens, '
             'off-database-studier, explore0); de tælles kun som forsøg.</div></div>')
    off = "; ".join(f"{e(k)}: reserveret {e(x.get('reserved'))}, offset {e(x.get('offset'))}"
                    for k, x in sorted(v["offsets"].items()))
    alpha_txt = f"{v['alpha']:.6f}" if isinstance(v["alpha"], (int, float)) else "–"
    o.append(f'<div class="gv-card" id="gv-alpha"><h3>Alfa belastet</h3><div class="gv-num">{e(alpha_txt)}</div>'
             '<div class="gv-sub">brutto (ledger.alpha_gross); intet refunderes</div>'
             + (f'<div class="gv-sub">Familie-rækker (ikke forsøg): {off}</div>' if off else "") + "</div>")
    o.append("</div>")

    # --- U3: DIAGNOSTIC_ONLY luck bar, reused from video_triage ---
    n = v["attempts"]
    if isinstance(n, int) and n >= 2:
        bar = video_triage.luck_bar(n, 1.0)
        cmp_txt = ("Registret har ingen z- eller Sharpe-værdier pr. forsøg, så der er intet at holde op mod "
                   "stregen: <b>sammenligningsdata mangler</b>." if not v["stats_present"] else
                   "Registret har felter, der ligner z/Sharpe-værdier, men denne visning sammenligner dem ikke.")
        o.append(f'<div class="gv-u3" id="gv-u3"><h3>U3 held / multiple testing<span class="dg">{e(LABEL)}</span>'
                 f'</h3>{u3_svg(bar)}<p>Forventet største z-værdi blandt <b>N = {n}</b> uafhængige nul-forsøg '
                 f'(ingen reel effekt nogen steder): <b>E[max z] ≈ {bar:.3f}</b>. Til sammenligning er 1,96 grænsen '
                 'for én enkelt test. For en årlig Sharpe over T år er stregen E[max z]/√T.</p>'
                 f'<p>N = registrets antal forsøg (ledger.attempts). Formel og funktion: '
                 'research/tools/video_triage.luck_bar(N, T=1) (Bailey &amp; López de Prado). <b>Antagelse: de '
                 f'{n} forsøg er uafhængige</b>; forsøg i samme lineage er i praksis korrelerede, og de '
                 f'{e(num(v["variants"]))} varianter indgår ikke i N, så stregen er kun en grov skala.</p>'
                 "<ul>" + "".join(f"<li>{e(a)}</li>" for a in video_triage.LUCK_ASSUMPTIONS) + "</ul>"
                 f"<p>{cmp_txt}</p></div>")
    else:
        o.append(f'<div class="gv-u3" id="gv-u3"><h3>U3 held / multiple testing<span class="dg">{e(LABEL)}</span>'
                 f'</h3><p>Ingen streg: registrets antal forsøg ({e(n)}) er under 2.</p></div>')

    # --- filters ---
    o.append('<section class="gv-filters" aria-label="filtre for kirkegården">')
    o.append('<div class="frow"><b>Status</b><label class="pill gv-pill" for="gs-all">Alle<small>'
             f'{len(allrows)}</small></label>' + "".join(
                 f'<label class="pill gv-pill" for="gs-{sid(s)}">{e(s if s != NONE else NONE_LABEL)}<small>'
                 f'{st_count[s]}</small></label>' for s in sts) + "</div>")
    o.append('<div class="frow"><b>Lineage</b><label class="pill gv-pill" for="gl-all">Alle</label>' + "".join(
        f'<label class="pill gv-pill" for="gl-{lid[x]}">{e(x)}<small>{lin_count[x]}</small></label>' for x in lins)
        + "</div>")
    o.append('<div class="frow"><span class="sub">Filtrene virker på begge tabeller og kan kombineres. Rent CSS; '
             'tallene i chipsene er antal rækker.</span></div></section>')

    # --- tables ---
    o.append(f'<h3 class="gv-h3" id="gv-ledger">Forsøg i ledgeren <small>· {len(rows)} rækker = ledger.attempts '
             f'{e(v["attempts"])} · registrets rækkefølge (seq)</small></h3>')
    o.append('<div class="gv-box"><table class="gv-t">' + HEAD + "<tbody>"
             + "\n".join(row_html(r, lid) for r in rows) + "</tbody></table></div>")
    o.append(f'<h3 class="gv-h3" id="gv-extra">Registreret, men ikke et forsøg i ledgeren <small>· {len(extra)} '
             'rækker (forslag, lukkede/eksterne eksperimenter, studier talt andetsteds eller med 0 forsøg)</small>'
             '</h3>')
    o.append('<div class="gv-box"><table class="gv-t">' + HEAD + "<tbody>"
             + ("\n".join(row_html(r, lid) for r in extra) if extra else
                '<tr><td colspan="8" class="na">Ingen.</td></tr>') + "</tbody></table></div>")
    o.append(f'<p class="gv-foot"><b>Kilde:</b> {e(os.path.relpath(os.path.join(path, "registry.json"), HERE))} '
             f'(schema {e(v["reg"].get("schema"))}, sha256 {e(v["sha"][:16])}…'
             f'{", matcher registry.md" if v["md_sha_ok"] else ""}) samt registry.md, offdb_studies.json, '
             'migration_v1.json og legacy_manifest_v1.json, kun læst. Registret genereres af '
             'research/tools/factory.py; denne side ændrer det aldrig.</p>')
    o.append("</section>")
    return "\n".join(radios), "\n".join(css), "\n".join(o)
