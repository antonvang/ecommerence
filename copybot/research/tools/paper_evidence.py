"""EVIDENS section of the paper dashboard (director order 75 P4, shown on the owner's request).

Display of research/tools/evidence_report.py: per hypothesis what is documented and what is missing. Read-only: it opens
only the register file evidence_report opens. No market data, no order entry, no JavaScript. Nothing is promoted.
"""
import collections
import html
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_report as er  # noqa: E402

ORDER = {"PASS": 0, "BLOCKED": 1, "INCONCLUSIVE": 2, "FAIL": 3}
CLS = {"PASS": "ev-p", "FAIL": "ev-f", "BLOCKED": "ev-b", "INCONCLUSIVE": "ev-i"}
FIELDS = (("omkostninger", "Omkostninger"), ("statistik", "Statistik"), ("data_mangler", "Data mangler"),
          ("validering", "Validering"))
CSS = """
.evn{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 14px}
.evn>div{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.evn b{display:block;font-size:30px;font-variant-numeric:tabular-nums;line-height:1.1}
.evn span{color:var(--mut);font-size:12px;letter-spacing:.06em;text-transform:uppercase}
.ev-p{color:var(--pos)}.ev-f{color:var(--neg)}.ev-b{color:var(--amb)}.ev-i{color:var(--mut)}
.evt{overflow:auto;max-height:640px;border:1px solid var(--line);border-radius:12px}
.evt table{border-collapse:collapse;width:100%;font-size:13px}
.evt th{position:sticky;top:0;background:var(--panel2);text-align:left;font-size:12px;color:var(--mut);padding:8px 10px}
.evt td{border-top:1px solid var(--line);padding:7px 10px;vertical-align:top;overflow-wrap:anywhere}
.evt td.m{color:var(--mut);font-size:12px}
@media (max-width:600px){.evn{grid-template-columns:1fr 1fr}.evt .opt{display:none}}
"""


def _txt(value):
    return html.escape(str(value if value is not None else er.MISSING))


def section(path=None):
    """(css, html). Fails soft: a missing or unreadable register gives a plain notice, never a broken page."""
    try:
        reg, digest = er.load(path or er.REGISTRY)
        view = er.build(reg)
    except (OSError, ValueError, KeyError, TypeError) as err:
        return CSS, ('<details class="fold" id="evidens"><summary><span class="sum-t">Evidens</span><span class="sum-s">'
                     f'kan ikke læses: {_txt(type(err).__name__)}</span></summary></details>')
    rows = sorted(view["rows"] + view["known_extra"], key=lambda r: (ORDER.get(r["verdict"], 9), str(r["id"])))
    n = collections.Counter(r["verdict"] for r in rows)
    missing = {k: sum(1 for r in rows if er.is_missing(r.get(k))) for k, _ in FIELDS}
    out = ['<details class="fold" id="evidens"><summary><span class="sum-t">Evidens</span><span class="sum-s">'
           f'{len(rows)} hypoteser · {view["validated_documented"]} uafhængigt validerede · fold ud</span></summary>'
           '<div class="fold-in"><div class="evn">']
    for v in er.VERDICTS:
        out.append(f'<div><b class="{CLS[v]}">{n.get(v, 0)}</b><span>{v}</span></div>')
    out.append('</div><p class="sub"><b>Ingen hypotese er uafhængigt valideret, og intet promoveres herfra.</b> '
               + " · ".join(f'{lab} mangler for {missing[k]}' for k, lab in FIELDS)
               + f'. Kilde: research/data/factory/registry.json (sha256 {_txt(digest[:16])}…); '
               'research/tools/evidence_report.py.</p>')
    out.append('<div class="evt"><table><thead><tr><th>Hypotese</th><th>Dom</th><th>Hvorfor</th>'
               '<th class="opt">Omkostninger</th><th class="opt">Statistik</th></tr></thead><tbody>')
    for r in rows:
        v = r["verdict"]
        out.append(f'<tr><td>{_txt(r["id"])}</td><td class="{CLS.get(v, "ev-i")}">{_txt(v)}</td>'
                   f'<td class="m">{_txt(r.get("hvorfor"))}</td><td class="m opt">{_txt(r.get("omkostninger"))}</td>'
                   f'<td class="m opt">{_txt(r.get("statistik"))}</td></tr>')
    out.append("</tbody></table></div></div></details>")
    return CSS, "".join(out)
