"""Danish HTML report for one store."""
import html

from .checks import AREAS

ICON = {"fejl": "✗", "advarsel": "!", "ok": "✓", "ukendt": "?"}
LABEL = {"fejl": "Fejl", "advarsel": "Advarsel", "ok": "OK", "ukendt": "Ukendt"}
SEV_ORDER = {"kritisk": 0, "høj": 1, "middel": 2, "lav": 3}

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e4df;--bad:#b42318;--warn:#b54708;--ok:#067647;--accent:#1f4fd1}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ececea;--muted:#a3a39d;--line:#33332f;--bad:#f97066;--warn:#fdb022;--ok:#47cd89;--accent:#84a5ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
.score{display:flex;gap:18px;align-items:center;flex-wrap:wrap}.big{font-size:44px;font-weight:700;line-height:1}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line)}
.fejl{color:var(--bad)}.advarsel{color:var(--warn)}.ok{color:var(--ok)}
.item{border-top:1px solid var(--line);padding:12px 0}.item:first-child{border-top:0}
.t{font-weight:600}.ev{font-size:13px;color:var(--muted);word-break:break-word}.fix{margin-top:4px}
a{color:var(--accent)}ol{padding-left:20px}
"""


def render(res):
    d = html.escape(res["domain"])
    out = [f"<!doctype html><html lang='da'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>GMC-tjek: {d}</title><style>{CSS}</style></head><body><div class='wrap'>"]
    out.append(f"<h1>Google Shopping-tjek: {d}</h1><div class='muted'>Udført {html.escape(res.get('checked_at', ''))} · kun offentlige sider</div>")
    if not res.get("reachable"):
        out.append("<div class='card'>Butikken kunne ikke hentes. " + html.escape(" ".join(res.get("notes", []))) + "</div></div></body></html>")
        return "".join(out)
    checks = res["checks"]
    bad = sorted([c for c in checks if c["status"] in ("fejl", "advarsel")], key=lambda c: (c["status"] != "fejl", SEV_ORDER[c["severity"]]))
    cnt = res.get("counts", {})
    out.append("<div class='card score'>"
               f"<div><div class='big'>{res['score']}</div><div class='muted'>af 100</div></div>"
               f"<div><div><span class='pill fejl'>{res['n_fail']} fejl</span> <span class='pill advarsel'>{res['n_warn']} advarsler</span></div>"
               f"<div class='muted' style='margin-top:6px'>Kritiske: {cnt.get('kritisk', 0)} · Høje: {cnt.get('høj', 0)} · Middel: {cnt.get('middel', 0)}</div></div></div>")
    if bad:
        out.append("<h2>Det vigtigste at rette først</h2><div class='card'><ol>")
        for c in bad[:5]:
            out.append(f"<li><span class='{c['status']}'>{html.escape(c['title'])}</span> <span class='muted'>({c['severity']})</span></li>")
        out.append("</ol></div>")
    for area in AREAS:
        items = [c for c in checks if c["area"] == area]
        if not items:
            continue
        out.append(f"<h2>{html.escape(area)}</h2><div class='card'>")
        for c in items:
            ref = f" · <a href='{html.escape(c['ref'])}'>Googles regel</a>" if c.get("ref") else ""
            out.append(f"<div class='item'><div class='t'><span class='{c['status']}'>{ICON[c['status']]} {LABEL[c['status']]}</span> · "
                       f"{html.escape(c['title'])} <span class='muted'>({c['severity']})</span></div>"
                       f"<div class='ev'>{html.escape(str(c['evidence']))}</div>")
            if c["status"] != "ok":
                out.append(f"<div class='fix'><b>Hvorfor:</b> {html.escape(c['why'])}<br><b>Sådan retter du det:</b> {html.escape(c['fix'])}{ref}</div>")
            out.append("</div>")
        out.append("</div>")
    if res.get("notes"):
        out.append("<h2>Bemærkninger</h2><div class='card'>" + "<br>".join(html.escape(n) for n in res["notes"]) + "</div>")
    out.append("<p class='muted' style='margin-top:28px'>Tjekket læser kun butikkens offentlige sider og respekterer robots.txt. "
               "Det ser derfor ikke selve Merchant Center-kontoen. Google afgør selv, om varer og konti godkendes. "
               "Rapporten er vejledning, ikke juridisk rådgivning.</p></div></body></html>")
    return "".join(out)
