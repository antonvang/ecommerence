"""FORSKNINGSOVERSIGT for PAPER DASHBOARD V3 (director order 69 P0): a read-only overview of the research status,
taken from files in the repo. Display only: no new research numbers, nothing is locked or activated, no JavaScript,
no external resources.

Source (read as bytes, never written): research/desk/FALSIFICATION_MATRIX_ORDER61.md
- "## 1. Kandidater": the candidate table (hypothesis, endpoint, kill rule, data, approvals, earliest verdict,
  recommendation), shown verbatim per candidate with the design note it names;
- "## 2. Readiness for milepælene": the milestone table (date, what, status, source), with the time left to the first
  UTC time named in the date cell, counted from the dashboard cutoff;
- "## 3. Reelle blokeringer": the numbered blocker list;
- "## Tillæg ...": a later director decision on the same candidates, shown verbatim above them.
Markdown is rendered minimally (**bold**, `code`); text is HTML-escaped and any URL is replaced by "[URL udeladt]".

If the file is missing or a table no longer parses (fewer than the expected columns, no rows), a small curated copy
(CURATED_*) is shown instead, labelled with its source path and the git commit/date it was copied from, so a format
change is visible and never silently produces an empty or invented status.

The page never claims a validated profitable strategy: NO_VALIDATED is stated in the section header.
"""
import calendar
import datetime as dt
import hashlib
import html
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # copybot/
MATRIX = os.path.join("research", "desk", "FALSIFICATION_MATRIX_ORDER61.md")
DESK = os.path.join("research", "desk")
NO_VALIDATED = "Ingen valideret profitabel strategi"
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S*")
CURATED_FROM = "0f0bf50 · 2026-11-09 14:09:20 +0100"
CURATED_CANDIDATES = (
    ("K05", "negRisk v2", "Betinget GO, kun beskrivende fase A (α = 0); tillæg 62: fase A BLOCKED",
     "K05_NEGRISK_V2_DESIGN.md"),
    ("K04", "HLP-vault mod DTB3", "NO-GO alfa; tillæg 62: PARKERET", "K04_HLP_VAULT_DESIGN.md"),
    ("K10", "short efter Monitoring Tag", "NO-GO nu; tillæg 62: PARKERET", "K10_MONITORING_TAG_DESIGN.md"),
    ("U4", "H1 08:30-RV", "PREREG_READY; lås NO-GO; tillæg 62: kun offline audit", "U4_0830_PREREG_DRAFT.md"),
    ("U1", "ORB15-QQQ", "NO-GO", "orb15/ORB15_GO_NO_GO.md"),
    ("U2", "fomo 30 s-kopi", "NO-GO", "fomo/GO_NO_GO_RECOMMENDATION.md"))
CURATED_MILESTONES = (
    ("12/11 ≥ 17:11:51 UTC", "STRAKS 7 d", "MILESTONE_DRYRUN_60AC.md"),
    ("14/11", "gate-status", "GATE_STATUS_PREVIEW_2026-11-14.md"),
    ("19/11 ≥ 00:35 / 20:51:09 UTC", "HFC-1 14 d + PAR-BOG", "MILESTONE_DRYRUN_60AC.md"),
    ("20/11 ≥ 09:55:07 UTC", "S1", "S1_READINESS_2026-11-20.md"))
CURATED_BLOCKERS = ("**D5 ejernøgle** mangler (`OWNER_KEY_GUIDE_D5.md`).",
                    "**Lokal DNS** blokerer data-api.binance.vision m.fl.; 9 carry-konti STALE.",
                    "**W0-alfa** (0,0375) er reserveret til andre (D6).")

CSS = """
.rs-lead{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin:0 0 14px;padding:12px 14px;
border:1px solid var(--line);border-left:3px solid var(--amb);border-radius:10px;background:var(--panel)}
.rs-lead b.nv{font-size:15px;color:var(--txt)}.rs-lead span{color:var(--mut);font-size:13px}
.rs-src{font:12px var(--mono);color:var(--mut);overflow-wrap:anywhere}.rs-src b{color:var(--txt);font-weight:600}
.rs-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:16px;align-items:start}
.rs-h{margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}
.rs-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.rs-c{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;font-size:13px}
.rs-c header{display:flex;gap:8px;align-items:baseline;justify-content:space-between;margin:0 0 6px}
.rs-id{font:700 15px var(--mono)}.rs-c .rs-d{color:var(--mut);font-size:12px;margin:0 0 8px}
.rs-v{display:block;margin:0 0 8px;padding:6px 8px;border-radius:6px;font-size:12px;line-height:1.4}
.v-no{background:var(--neg-bg);color:#ffb3bb}.v-cond{background:var(--amb-bg);color:#ffd88a}
.v-prep{background:var(--blu-bg);color:#a9d4ff}.v-na{background:var(--panel2);color:var(--mut)}
.rs-c dl{display:grid;grid-template-columns:96px 1fr;gap:4px 10px;margin:0;font-size:12px}
.rs-c dt{color:var(--mut)}.rs-c dd{margin:0;color:var(--txt);overflow-wrap:anywhere}
.rs-c code,.rs-n code,.rs-b code,.rs-m code{font:11.5px var(--mono);color:#b9c3d6;background:var(--panel2);
padding:0 4px;border-radius:4px}
.rs-c .rs-src{margin-top:8px}
.rs-n{margin:0 0 12px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--panel2);
font-size:13px}.rs-n p{margin:4px 0 0;color:var(--txt)}
.rs-m{list-style:none;margin:0 0 16px;padding:0;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
.rs-m li{display:grid;grid-template-columns:74px 1fr;gap:2px 12px;padding:10px 12px;border-top:1px solid var(--line)}
.rs-m li:first-child{border-top:0}
.rs-m .md{font:700 15px var(--mono);color:var(--txt)}.rs-m .mt{font-size:11px;color:var(--mut);grid-column:1}
.rs-m .mw{font-weight:600;grid-column:2;grid-row:1}.rs-m .ms{grid-column:2;font-size:12px;color:var(--mut)}
.rs-m .mc{font:12px var(--mono);color:var(--blu)}.rs-m .rs-src{grid-column:2}
.rs-b{margin:0 0 12px;padding:0 0 0 18px;font-size:13px}.rs-b li{margin:0 0 8px;color:var(--txt)}
.rs-fb{margin:0 0 12px;padding:10px 12px;border:1px solid var(--amb);border-radius:10px;background:var(--amb-bg);
font-size:13px}
@media (max-width:1000px){.rs-grid{grid-template-columns:1fr}}
@media (max-width:600px){.rs-cards{grid-template-columns:1fr}.rs-c dl{grid-template-columns:84px 1fr}}
"""


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def md(s):
    """Minimal inline markdown: escape, scrub URLs, **bold** and `code`."""
    t = e(URL.sub("[URL udeladt]", "" if s is None else str(s)))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)


def plain(s):
    return re.sub(r"[*`]", "", "" if s is None else str(s)).strip()


def sections(text):
    """{heading text: [lines]} for every '## ' heading."""
    out, cur = {}, None
    for ln in text.splitlines():
        if ln.startswith("## "):
            cur = ln[3:].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(ln)
    return out


def find(secs, prefix):
    return next((v for k, v in secs.items() if k.startswith(prefix)), None)


def table(lines, need):
    """Rows of the first markdown table in lines as dicts keyed by the header, or None when the header lacks a needed
    column or a row has another number of cells (the caller then falls back to the curated copy)."""
    rows = [ln.strip() for ln in (lines or []) if ln.strip().startswith("|")]
    if len(rows) < 3 or not re.fullmatch(r"\|(\s*:?-{3,}:?\s*\|)+", rows[1].replace(" ", "")):
        return None
    cells = lambda r: [c.strip() for c in r.strip("|").split("|")]  # noqa: E731
    head = cells(rows[0])
    if not all(any(h.startswith(n) for h in head) for n in need):
        return None
    out = []
    for r in rows[2:]:
        c = cells(r)
        if len(c) != len(head):
            return None
        out.append(dict(zip(head, c)))
    return out or None


def col(row, prefix):
    return next((v for k, v in row.items() if k.startswith(prefix)), "")


def numbered(lines):
    """Items of the first numbered list (continuation lines are indented)."""
    items = []
    for ln in lines or []:
        m = re.match(r"\d+\.\s+(.*)", ln)
        if m:
            items.append(m.group(1).strip())
        elif items and ln.startswith((" ", "\t")) and ln.strip():
            items[-1] += " " + ln.strip()
        elif items and not ln.strip():
            continue
    return items


def desk_path(root, name):
    p = os.path.join(DESK, name)
    return p, os.path.exists(os.path.join(root, p))


def verdict_class(text):
    t = plain(text).upper()
    if t.startswith("NO-GO") or "NO-GO NU" in t[:12]:
        return "v-no"
    if "PREREG" in t[:20]:
        return "v-prep"
    if "GO" in t[:30]:
        return "v-cond"
    return "v-na"


def until(cell, cutoff):
    """Time from the cutoff to the date (and first HH:MM[:SS]) in a 'dd/mm ...' cell, in the cutoff's year."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})", cell)
    if not m:
        return None, ""
    y = dt.datetime.fromtimestamp(cutoff, dt.timezone.utc).year
    tm = re.search(r"(\d\d):(\d\d)(?::(\d\d))?", cell[m.end():])
    hh, mi, ss = (int(tm.group(1)), int(tm.group(2)), int(tm.group(3) or 0)) if tm else (0, 0, 0)
    try:
        t = calendar.timegm((y, int(m.group(2)), int(m.group(1)), hh, mi, ss))
    except (ValueError, OverflowError):
        return None, ""
    d = t - cutoff
    if d <= 0:
        return t, "tidspunkt passeret ved cutoff — se kilden for resultatet"
    days, hours = d // 86400, (d % 86400) // 3600
    return t, f"om {days} d {hours} t" if days else f"om {hours} t {(d % 3600) // 60} min"


def parse(root):
    path = os.path.join(root, MATRIX)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return {"ok": False, "why": f"{MATRIX} mangler"}
    text = raw.decode("utf-8", "replace")
    secs = sections(text)
    cands = table(find(secs, "1."), ("Hypotese", "Primært endepunkt", "Kill-regel", "Data", "Godkendelser",
                                      "Tidligste dom", "Anbefaling"))
    miles = table(find(secs, "2."), ("Dato", "Hvad", "Status", "Kilde"))
    blocks = numbered(find(secs, "3."))
    addendum = find(secs, "Tillæg")
    add_head = next((k for k in secs if k.startswith("Tillæg")), "")
    first = text.splitlines()[0] if text else ""
    why = [n for n, v in (("kandidattabellen (§1)", cands), ("milepælstabellen (§2)", miles),
                          ("blokeringslisten (§3)", blocks)) if not v]
    return {"ok": not why, "why": ", ".join(why) + " kunne ikke læses" if why else "", "sha": hashlib.sha256(raw)
            .hexdigest(), "title": first.lstrip("# ").strip(), "cands": cands or [], "miles": miles or [],
            "blocks": blocks, "addendum": " ".join(ln.strip() for ln in (addendum or []) if ln.strip()),
            "add_head": add_head}


def cand_card(root, row):
    hyp = col(row, "Hypotese")
    m = re.match(r"\*\*([^*]+)\*\*\s*(.*)", hyp)
    cid, desc = (m.group(1), m.group(2)) if m else (plain(hyp)[:12], hyp)
    notes = re.findall(r"`([^`]+\.md)`", hyp)
    desc = re.sub(r"\s*\(`[^`]+\.md`\)", "", desc)
    rec = col(row, "Anbefaling")
    src = []
    for n in notes:
        p, ok = desk_path(root, n)
        src.append(f"{e(p)}" + ("" if ok else " (ikke fundet)"))
    dl = "".join(f"<dt>{e(k)}</dt><dd>{md(col(row, k))}</dd>" for k in
                 ("Primært endepunkt", "Kill-regel", "Data", "Godkendelser", "Tidligste dom"))
    return (f'<article class="rs-c" data-id="{e(cid)}"><header><span class="rs-id">{e(cid)}</span></header>'
            f'<p class="rs-d">{md(desc)}</p><span class="rs-v {verdict_class(rec)}">{md(rec)}</span><dl>{dl}</dl>'
            f'<div class="rs-src">Kilde: {e(MATRIX)} §1' + ("".join(f" · {s}" for s in src)) + "</div></article>")


def section(root=HERE, cutoff=0):
    """(css, html) of the FORSKNINGSOVERSIGT section."""
    v = parse(root)
    o = ['<section class="rs" id="forskning">',
         '<h2>Forskningsoversigt <small>· status fra filer i repoet · kun læst · intet låses eller aktiveres '
         'herfra</small></h2>',
         f'<div class="rs-lead" id="no-validated"><b class="nv">{e(NO_VALIDATED)}.</b><span>Alt nedenfor er design, '
         'readiness eller planlagte målinger. Papirtal ovenfor er beskrivende og ikke en valideret strategi.</span>'
         '</div>']
    if v["ok"]:
        o.append(f'<p class="rs-src">Kilde: <b>{e(MATRIX)}</b> · “{e(v["title"])}” · sha256 {e(v["sha"][:12])}…</p>')
    else:
        o.append(f'<div class="rs-fb" id="rs-fallback"><b>Kildefilen kunne ikke læses</b> ({e(v["why"])}). Viser en '
                 f'kurateret kopi af {e(MATRIX)} @ {e(CURATED_FROM)}; den opdateres ikke af sig selv.</div>')
    o.append('<div class="rs-grid"><div>')
    o.append('<h3 class="rs-h" id="rs-kandidater">Hypoteser og kandidater</h3>')
    if v["ok"] and v["addendum"]:
        o.append(f'<div class="rs-n" id="rs-tillaeg"><b>{md(v["add_head"])}</b> — senere end tabellen og går forud'
                 f'<p>{md(v["addendum"])}</p><div class="rs-src">Kilde: {e(MATRIX)} (Tillæg)</div></div>')
    o.append('<div class="rs-cards">')
    if v["ok"]:
        o.extend(cand_card(root, r) for r in v["cands"])
    else:
        for cid, name, rec, note in CURATED_CANDIDATES:
            p, ok = desk_path(root, note)
            o.append(f'<article class="rs-c" data-id="{e(cid)}"><header><span class="rs-id">{e(cid)}</span></header>'
                     f'<p class="rs-d">{e(name)}</p><span class="rs-v {verdict_class(rec)}">{e(rec)}</span>'
                     f'<div class="rs-src">Kilde: {e(MATRIX)} @ {e(CURATED_FROM)} · {e(p)}'
                     f'{"" if ok else " (ikke fundet)"}</div></article>')
    o.append("</div></div><div>")
    o.append('<h3 class="rs-h" id="rs-milepaele">Kommende milepæle</h3><ol class="rs-m">')
    miles = ([(col(r, "Dato"), col(r, "Hvad"), col(r, "Status"), col(r, "Kilde")) for r in v["miles"]] if v["ok"] else
             [(d, w, "", f"`{s}`") for d, w, s in CURATED_MILESTONES])
    for date, what, status, src in miles:
        _, left = until(date, cutoff)
        names = re.findall(r"`([^`]+)`", src) or [plain(src)]
        paths = " · ".join(e(desk_path(root, n)[0]) for n in names if n)
        dm = re.match(r"\s*(\d{1,2}/\d{1,2})(.*)", date)
        o.append(f'<li><span class="md">{e(dm.group(1) if dm else date)}</span><span class="mw">{md(what)}</span>'
                 f'<span class="mt">{e((dm.group(2) if dm else "").strip())}</span><span class="ms">'
                 + (f'<span class="mc">{e(left)}</span> · ' if left else "") + f"{md(status)}</span>"
                 f'<span class="rs-src">Kilde: {paths}</span></li>')
    o.append("</ol>")
    o.append('<h3 class="rs-h" id="rs-blokeringer">Dokumenterede begrænsninger og blokeringer</h3><ol class="rs-b">')
    for b in (v["blocks"] if v["ok"] else CURATED_BLOCKERS):
        o.append(f"<li>{md(b)}</li>")
    o.append(f'</ol><p class="rs-src">Kilde: {e(MATRIX)} §2–§3' + ("" if v["ok"] else f" @ {e(CURATED_FROM)}")
             + "</p></div></div></section>")
    return CSS, "\n".join(o)
