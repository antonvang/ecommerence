"""Turn data/opkaldsliste.csv into a simple, printable call sheet (opkaldsark.html) for the adult who calls.
Tick boxes are saved in the browser (localStorage) so progress survives a reload. Local file only (gitignored data/)."""
import csv
import html
import sys

src = sys.argv[1] if len(sys.argv) > 1 else "data/opkaldsliste.csv"
out = sys.argv[2] if len(sys.argv) > 2 else "data/opkaldsark.html"
rows = list(csv.DictReader(open(src, encoding="utf-8-sig"), delimiter=";"))

cards = []
for i, r in enumerate(rows, 1):
    d = html.escape(r["butik"])
    tel = html.escape(r["telefon"])
    tel_link = "".join(ch for ch in r["telefon"] if ch.isdigit() or ch == "+")
    opener = html.escape(r["aabning"])
    fejl = html.escape(r["fejlliste"]).replace(" | ", "</li><li>")
    cards.append(f"""
<div class="card" id="c{i}">
  <div class="top"><span class="n">{i}</span> <b>{d}</b> · <a href="tel:{tel_link}">{tel}</a> · <a href="https://{d}" target="_blank" rel="noopener">åbn butik</a></div>
  <div class="say"><b>Sig fx:</b> "Vi har fundet, at {opener}."</div>
  <details><summary>Alle fund ({r['fejl']} fejl)</summary><ul><li>{fejl}</li></ul></details>
  <div class="boxes">
    <label><input type="checkbox" data-k="{d}|ringet"> Ringet</label>
    <label><input type="checkbox" data-k="{d}|talt"> Talt med ejer/ansvarlig</label>
    <label><input type="checkbox" data-k="{d}|ja"> Ja til gratis rapport</label>
    <label><input type="checkbox" data-k="{d}|samtykke"> Ja til opfølgning på mail</label>
    <label><input type="checkbox" data-k="{d}|bestilt"> Vil have rettelse (995 kr.)</label>
    <label><input type="checkbox" data-k="{d}|nej"> Nej tak / kontakt ikke igen</label>
  </div>
  <input class="mail" type="email" placeholder="Mailadresse (kun hvis de sagde ja)" data-k="{d}|mail">
  <input class="note" type="text" placeholder="Note (navn, hvad de sagde)" data-k="{d}|note">
</div>""")

page = f"""<!doctype html><html lang="da"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Opkaldsark</title><style>
:root{{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e4e4df;--accent:#1f4fd1}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141413;--card:#1e1e1c;--ink:#ececea;--muted:#a3a39d;--line:#33332f;--accent:#84a5ff}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:860px;margin:0 auto;padding:20px 16px 60px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}}
.n{{display:inline-block;min-width:26px;color:var(--muted)}}a{{color:var(--accent)}}.say{{margin:8px 0;padding:8px 10px;background:var(--bg);border-radius:8px}}
.boxes{{display:flex;flex-wrap:wrap;gap:6px 14px;margin:8px 0}}input.mail,input.note{{width:100%;margin-top:6px;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}}
.sum{{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);font-weight:600}}.muted{{color:var(--muted)}}
</style></head><body><div class="wrap">
<h1>Opkaldsark — GMC-Doktor</h1>
<p class="muted">Ring kl. 10–16 på hverdage. Læs manuskriptet i guiden. Send kun mail til dem, der har sagt ja. Afkrydsninger gemmes automatisk i denne browser.</p>
<div class="sum" id="sum"></div>
{''.join(cards)}
</div><script>
const KEY='gmcdoktor-opkald';
let st={{}};try{{st=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
document.querySelectorAll('[data-k]').forEach(el=>{{const k=el.dataset.k;if(el.type==='checkbox')el.checked=!!st[k];else el.value=st[k]||'';
el.addEventListener('input',()=>{{st[k]=el.type==='checkbox'?el.checked:el.value;try{{localStorage.setItem(KEY,JSON.stringify(st))}}catch(e){{}};sum()}})}});
function sum(){{const c=s=>Object.keys(st).filter(k=>k.endsWith('|'+s)&&st[k]).length;
document.getElementById('sum').textContent=`Ringet: ${{c('ringet')}} · Samtaler: ${{c('talt')}} · Ja til rapport: ${{c('ja')}} · Vil have rettelse: ${{c('bestilt')}}`}}
sum();
</script></body></html>"""
open(out, "w", encoding="utf-8").write(page)
print(f"{len(rows)} butikker i {out}")
