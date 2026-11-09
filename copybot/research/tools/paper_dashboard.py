"""PAPER DASHBOARD V2: one static, self-contained, read-only HTML page of the paper books (director orders 59-H P2
and 59-J).

    python3 research/tools/paper_dashboard.py [--db PATH] [--cutoff YYYY-MM-DDTHH:MM:SSZ] --out PATH.html [--feed N]

LOCAL prototype only; production deploy is NO-GO until director review (research/desk/PAPER_DASHBOARD_V2.md).

Every number per account (net at the mark, mark time and age, FRESH/STALE/MISSING_MARK, fills, max drawdown) and the
summary come from research.tools.net_report.build(con, now, cutoff); nothing is recomputed here. The activity feed lists
recorded sim_fills rows and recorded skip/refusal/error events of the shown ledgers, newest first, up to the cutoff.
No current portfolio value is shown unless every account is FRESH (and at least one account exists).

Layout (59-J): bot cards ordered FRESH, STALE, MISSING_MARK, then by name, start time and ledger id; duplicate names are
numbered "name #1", "name #2" by (start time, ledger id) and that label is used on the card, the filter chip and the
feed rows (the ledger id stays on the card). A snapshot banner gives the generation time, the cutoff and the command
to run again; a "Sådan læses tallene" box explains net and FRESH/STALE/MISSING_MARK. The feed shows the same rows as
before, split into executed paper fills and skips/refusals/errors.

HANDELSCHART (59-K, research/tools/paper_chart.py): under the bot grid, one read-only SVG trade chart per instrument
of the FRESH books (most fills first, at most 6), picked with a CSS-only radio selector; fills, recorded market marks
(gap-broken), funding settlement prices, instrument-tied skips and net_report's documented entry; never equity.

STRATEGIKIRKEGÅRD (order 60 D, research/tools/paper_graveyard.py): after the activity feed, every attempt of the
factory register (research/data/factory, read-only) with the register's own totals, statuses and recorded text,
CSS-only status/lineage filters and a DIAGNOSTIC_ONLY U3 luck bar (video_triage.luck_bar); nothing is activated.

Read-only: lab.db is opened as file:...?mode=ro with PRAGMA query_only=ON. No network, no JS, no external resources;
filters are pure CSS (radio inputs + :checked sibling selectors). The page does not refresh itself.
"""
import argparse
import collections
import datetime as dt
import html
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from research.tools import net_report  # noqa: E402
from research.tools import paper_chart  # noqa: E402
from research.tools import paper_graveyard  # noqa: E402

DB = net_report.DB
SKIP_KINDS = ("straks.skipped", "paper.skipped", "lane.skipped", "paper.refused", "paper.error",
              "paper.mark_failed", "paper.mark_recovered")
KIND_LABEL = {"straks.skipped": "SPRUNGET OVER", "paper.skipped": "SPRUNGET OVER", "lane.skipped": "SPRUNGET OVER",
              "paper.refused": "AFVIST", "paper.error": "FEJL", "paper.mark_failed": "MÆRKNING FEJLEDE",
              "paper.mark_recovered": "MÆRKNING GENOPRETTET"}
DAY = 86400
SPARK_POINTS = 48
RANK = {"FRESH": 0, "STALE": 1, "MISSING_MARK": 2}
CMD = "python3 research/tools/paper_dashboard.py --out <fil>"
CMD_HEAD, CMD_ARG = CMD.split(" --out ")[0], "--out <fil>"   # the argument never wraps inside "--out"


def start_key(a):
    return (a["started"] if a["started"] is not None else -1, str(a["ledger"]))


def labels(accs):
    """Display label per ledger: the account name, and for a name shared by several ledgers "name #k", numbered by
    (start time, ledger id) so the same ledger always gets the same number in every place it is shown."""
    groups = collections.defaultdict(list)
    for a in accs:
        groups[a["name"] or a["ledger"]].append(a)
    out = {}
    for nm, grp in groups.items():
        if len(grp) == 1:
            out[grp[0]["ledger"]] = nm
        else:
            for k, a in enumerate(sorted(grp, key=start_key), 1):
                out[a["ledger"]] = f"{nm} #{k}"
    return out


def ordered(accs):
    """FRESH first, then STALE, then MISSING_MARK; within a group by name, start time, ledger id (deterministic)."""
    return sorted(accs, key=lambda a: (RANK.get(a["mark_status"], len(RANK)), str(a["name"] or a["ledger"]),
                                       *start_key(a)))


def connect_ro(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def parse_cutoff(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())


def utc(t, fmt="%Y-%m-%d %H:%M:%S"):
    return "–" if t is None else dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime(fmt) + " UTC"


def money(x):
    """Signed amount with a real minus sign; never rounds a loss to look like a gain."""
    if x is None:
        return "–"
    r = round(x, 2)
    sign = "+" if r > 0 else ("−" if r < 0 else "±")
    return f"{sign}{abs(r):,.2f}"


def tone(x):
    r = round(x or 0.0, 2)
    return "pos" if r > 0 else ("neg" if r < 0 else "zero")


def ident(s):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def feed(con, ledgers, cutoff, n):
    """Newest-first recorded events of the shown ledgers up to the cutoff: fills plus skip/refusal/error events.
    Returns (rows, totals) where totals counts everything up to the cutoff, so a cut feed is never silent."""
    leds = sorted(ledgers)
    ph = ",".join("?" * len(leds)) or "NULL"
    rows, totals = [], {"fills": 0, "events": 0}
    if leds:
        totals["fills"] = con.execute(f"SELECT COUNT(*) FROM sim_fills WHERE exp_id IN ({ph}) AND ts<=?",
                                      (*leds, cutoff)).fetchone()[0]
        for i, ts, led, sym, side, px, q, fee in con.execute(
                f"SELECT id, ts, exp_id, instrument, side, px, qty, fee FROM sim_fills WHERE exp_id IN ({ph}) "
                f"AND ts<=? ORDER BY ts DESC, id DESC LIMIT ?", (*leds, cutoff, n)):
            rows.append({"ts": ts, "order": (1, i), "kind": "fill", "ledger": led, "instrument": sym, "side": side,
                         "px": px, "qty": q, "fee": fee})
    kp = ",".join("?" * len(SKIP_KINDS))
    where = f"kind IN ({kp}) AND ts<=? AND (exp_id IN ({ph}) OR (kind='paper.error' AND exp_id IS NULL))"
    args = (*SKIP_KINDS, cutoff, *leds)
    totals["events"] = con.execute(f"SELECT COUNT(*) FROM events WHERE {where}", args).fetchone()[0]
    for i, ts, kind, led, p in con.execute(f"SELECT id, ts, kind, exp_id, payload FROM events WHERE {where} "
                                           f"ORDER BY ts DESC, id DESC LIMIT ?", (*args, n)):
        try:
            pl = json.loads(p) if p else {}
        except ValueError:
            pl = {"reason": "(payload ikke læsbar)"}
        if not isinstance(pl, dict):
            pl = {}
        sym = pl.get("instrument") or pl.get("coin") or ""
        reason = pl.get("reason") or pl.get("error") or ""
        rows.append({"ts": ts, "order": (0, i), "kind": kind, "ledger": led or "system", "instrument": sym,
                     "side": pl.get("side"), "qty": pl.get("qty"), "reason": str(reason)})
    rows.sort(key=lambda r: (r["ts"], r["order"]), reverse=True)
    return rows[:n], totals


def spark(con, led, cutoff, capital, cls):
    pts = con.execute("SELECT ts, equity FROM sim_equity WHERE exp_id=? AND ts<=? ORDER BY ts, id",
                      (led, cutoff)).fetchall()
    if len(pts) < 2:
        return '<div class="spark none">ingen equity-forløb</div>'
    step = max(1, -(-len(pts) // SPARK_POINTS))
    sel = pts[::step]
    if sel[-1] != pts[-1]:
        sel.append(pts[-1])
    t0, t1 = sel[0][0], sel[-1][0]
    vals = [v for _, v in sel] + [capital]
    lo, hi = min(vals), max(vals)
    span, tspan = (hi - lo) or 1.0, (t1 - t0) or 1
    xy = " ".join(f"{(t - t0) / tspan * 120:.1f},{30 - (v - lo) / span * 28:.1f}" for t, v in sel)
    base = 30 - (capital - lo) / span * 28
    return (f'<svg class="spark {cls}" viewBox="0 0 120 32" preserveAspectRatio="none" role="img" '
            f'aria-label="registreret equity, {len(pts)} mærker"><line x1="0" x2="120" y1="{base:.1f}" '
            f'y2="{base:.1f}" class="base"/><polyline points="{xy}"/></svg>')


CSS = """
:root{--bg:#0a0d14;--panel:#111725;--panel2:#161e30;--line:#24304a;--txt:#e6ebf5;--mut:#8a96ad;--pos:#16c784;
--neg:#ff4d5e;--amb:#f5a623;--acc:#7b61ff;--blu:#3fa9f5}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.f{position:absolute;opacity:0;pointer-events:none;width:1px;height:1px}
.wrap{max-width:1280px;margin:0 auto;padding:0 16px 40px}
header{position:sticky;top:0;z-index:5;background:rgba(10,13,20,.96);border-bottom:1px solid var(--line);
padding:12px 0;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
.logo{font-weight:900;letter-spacing:.18em;font-size:22px}.logo span{color:var(--acc)}
.paper{background:var(--amb);color:#1a1200;font-weight:900;font-size:18px;padding:8px 16px;border-radius:10px;
letter-spacing:.04em;border:2px solid #ffd27a}
.cut{color:var(--mut);font-size:13px}.cut b{color:var(--txt)}
.health{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:12px;margin-left:8px}
.h-ok{background:rgba(22,199,132,.15);color:var(--pos)}.h-warn{background:rgba(245,166,35,.15);color:var(--amb)}
.h-bad{background:rgba(255,77,94,.15);color:var(--neg)}
.banner{margin:14px 0 0;padding:12px 14px;border-radius:12px;border:1px solid var(--blu);
background:rgba(63,169,245,.10);font-size:14px}.banner b{color:#fff}
.banner code{display:inline-block;margin:4px 0;padding:2px 8px;border-radius:6px;background:#0b1120;color:var(--blu);
font:13px ui-monospace,Menlo,Consolas,monospace;overflow-wrap:break-word}
.banner code span{white-space:nowrap}.banner .bcut{display:block;color:var(--mut);
font-size:12px}
.howto{margin:12px 0 0;padding:12px 16px;background:var(--panel);border:1px solid var(--line);border-radius:14px;
font-size:13px}.howto h3{margin:0 0 6px;font-size:13px;letter-spacing:.06em;text-transform:uppercase}
.howto ul{margin:0;padding-left:18px}.howto li{margin:3px 0;color:var(--mut)}.howto li b{color:var(--txt)}
.tops{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:16px 0}
.top{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
.top h3{margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut)}
.big{font-size:32px;font-weight:800;font-variant-numeric:tabular-nums}.sub{color:var(--mut);font-size:12px}
.top.na .big{color:var(--amb);font-size:24px}.top.stale .big{opacity:.8}
.pos{color:var(--pos)}.neg{color:var(--neg)}.zero{color:var(--mut)}
h2{font-size:16px;margin:24px 0 10px;letter-spacing:.06em;text-transform:uppercase}
h2 small{color:var(--mut);font-weight:400;text-transform:none;letter-spacing:0}
.filters{display:flex;flex-direction:column;gap:8px;background:var(--panel);border:1px solid var(--line);
border-radius:14px;padding:12px}
.frow{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.frow>b{color:var(--mut);font-size:12px;width:64px}
.pill{cursor:pointer;padding:4px 10px;border-radius:999px;border:1px solid var(--line);background:var(--panel2);
color:var(--mut);font-size:12px;user-select:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.bot{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;
padding:14px;display:flex;flex-direction:column;gap:8px}
.bot.s-STALE{border-color:rgba(245,166,35,.45);background:var(--panel)}
.bot.s-MISSING_MARK{border-color:rgba(255,77,94,.55);background:var(--panel)}
.bot.s-STALE .bnet{opacity:.55}
.bhead{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.avatar{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;font-weight:900;
background:var(--acc);color:#fff;flex:none}
.bname{font-weight:800;font-size:15px;word-break:break-word}.bled{color:var(--mut);font-size:11px}
.src{font-size:11px;padding:2px 8px;border-radius:6px;background:#1f2940;color:var(--blu);text-transform:uppercase}
.chip{display:inline-block;padding:3px 8px;border-radius:8px;font-size:11px;font-weight:700}
.c-FRESH{background:rgba(22,199,132,.15);color:var(--pos)}.c-STALE{background:rgba(245,166,35,.15);color:var(--amb)}
.c-MISSING_MARK{background:rgba(255,77,94,.15);color:var(--neg)}
.bnet{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:4px 10px;font-size:12px;color:var(--mut)}
.stats b{color:var(--txt);font-weight:600}
.spark{width:100%;height:36px}.spark polyline{fill:none;stroke-width:1.6;vector-effect:non-scaling-stroke}
.spark .base{stroke:var(--line);stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
.spark.pos polyline{stroke:var(--pos)}.spark.neg polyline{stroke:var(--neg)}
.spark.zero polyline,.spark.old polyline{stroke:var(--mut)}
.spark.none{font-size:11px;color:var(--mut);height:auto}
.feedbox{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.ev{display:grid;grid-template-columns:180px 170px 120px 1fr;gap:8px;padding:8px 12px;
border-top:1px solid var(--line);font-size:13px;align-items:center}
.ev:first-child{border-top:0}
.ev .t{color:var(--mut);font-variant-numeric:tabular-nums;font-size:12px;white-space:nowrap}
.ev .who{font-weight:700;word-break:break-word}.ev .sym{font-family:ui-monospace,Menlo,Consolas,monospace}
.ev.fill{border-left:4px solid var(--blu)}
.ev.skip{background:rgba(245,166,35,.05);border-left:4px solid var(--amb)}
.ev.err{background:rgba(255,77,94,.07);border-left:4px solid var(--neg)}
.fh{margin:16px 0 8px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;display:flex;gap:8px;
align-items:center;flex-wrap:wrap}.fh small{color:var(--mut);font-weight:400;text-transform:none;letter-spacing:0}
.tag{padding:2px 8px;border-radius:6px;font-size:11px;font-weight:800}.t-fill{background:rgba(63,169,245,.15);
color:var(--blu)}.t-skip{background:rgba(245,166,35,.15);color:var(--amb)}
.side{display:inline-block;min-width:44px;text-align:center;padding:1px 6px;border-radius:6px;font-size:11px;
font-weight:800;margin-right:6px}.buy{background:rgba(63,169,245,.15);color:var(--blu)}
.sell{background:rgba(123,97,255,.18);color:#b3a4ff}.sk{background:rgba(245,166,35,.15);color:var(--amb)}
.er{background:rgba(255,77,94,.15);color:var(--neg)}
.fee{color:var(--neg);font-size:12px;margin-left:8px}.why{color:var(--mut)}
.empty{padding:16px;color:var(--mut)}
footer{margin-top:28px;padding-top:16px;border-top:1px solid var(--line);color:var(--mut);font-size:12px}
footer p{margin:4px 0}footer b{color:var(--txt)}
@media (max-width:720px){header{position:static}.ev{grid-template-columns:1fr 1fr}.ev>span:last-child{grid-column:1/-1}
.big{font-size:26px}.paper{font-size:15px}}
"""


def page(rep, frows, totals, db_path, feed_n, conspark, chart=None, graveyard=None):
    sm = rep["summary"]
    cutoff, now = sm["cutoff"], rep["generated"]
    accs = ordered(rep["accounts"])
    n_acc = len(accs)
    names = labels(accs)
    status = {a["ledger"]: a["mark_status"] for a in accs}
    out = []
    w = out.append

    # --- filter state inputs (pure CSS filters) ---
    bot_ids = ["all"] + [ident(a["ledger"]) for a in accs]
    radios = [f'<input class="f" type="radio" name="fb" id="fb-{b}"{" checked" if b == "all" else ""}>'
              for b in bot_ids]
    radios += [f'<input class="f" type="radio" name="fp" id="fp-{p}"{" checked" if p == "all" else ""}>'
               for p in ("all", "24", "7")]
    radios += [f'<input class="f" type="radio" name="fs" id="fs-{s}"{" checked" if s == "all" else ""}>'
               for s in ("all", "FRESH", "STALE", "MISSING_MARK")]
    hc = chart(names) if chart else ("", "", "")         # 59-K HANDELSCHART: (radios, css, section html)
    radios.append(hc[0])
    gy = graveyard() if graveyard else ("", "", "")      # 60-D STRATEGIKIRKEGÅRD: (radios, css, section html)
    radios.append(gy[0])
    css = [CSS, hc[1], gy[1]]
    on = "{background:var(--acc);color:#fff;border-color:var(--acc)}"
    for b in bot_ids:
        css.append(f"#fb-{b}:checked~.wrap label[for=fb-{b}]{on}")
        if b != "all":
            css.append(f"#fb-{b}:checked~.wrap .ev:not(.b-{b}),#fb-{b}:checked~.wrap .bot:not(.b-{b}){{display:none}}")
    for p in ("all", "24", "7"):
        css.append(f"#fp-{p}:checked~.wrap label[for=fp-{p}]{on}")
    css.append("#fp-24:checked~.wrap .ev:not(.in24),#fp-7:checked~.wrap .ev:not(.in7){display:none}")
    for s in ("all", "FRESH", "STALE", "MISSING_MARK"):
        css.append(f"#fs-{s}:checked~.wrap label[for=fs-{s}]{on}")
        if s != "all":
            css.append(f"#fs-{s}:checked~.wrap .ev:not(.s-{s}),#fs-{s}:checked~.wrap .bot:not(.s-{s}){{display:none}}")

    w("<!DOCTYPE html>")
    w('<html lang="da"><head><meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width,initial-scale=1">')
    w("<title>COPYBOT Paper Dashboard</title>")
    w("<style>" + "\n".join(css) + "</style></head><body>")
    w("\n".join(radios))
    w('<div class="wrap">')

    # --- header ---
    if n_acc == 0:
        health = '<span class="health h-bad">INGEN DATA</span>'
    elif sm["missing_mark"]:
        health = f'<span class="health h-bad">MANGLER MÆRKNING: {sm["missing_mark"]}</span>'
    elif sm["stale"]:
        health = f'<span class="health h-warn">FORÆLDEDE MÆRKER: {sm["stale"]}</span>'
    else:
        health = '<span class="health h-ok">ALLE MÆRKER FRISKE</span>'
    w('<header><div class="logo">COPY<span>BOT</span></div>')
    w('<div class="paper" id="paper-badge">PAPER / SIMULATION — ingen rigtige penge</div>')
    w(f'<div class="cut">Cutoff: <b>{e(utc(cutoff))}</b>{health}</div></header>')
    w(f'<div class="banner" id="snapshot"><b>Statisk snapshot genereret {e(utc(now))}. Kør kommandoen igen for nye '
      f'tal.</b><br><code>{e(CMD_HEAD)} <span>{e(CMD_ARG)}</span></code>'
      f'<span class="bcut">Datacutoff: <b>{e(utc(cutoff))}</b> · tallene er frosset '
      f'ved cutoff og opdaterer ikke sig selv · kun registrerede papirdata fra lab.db</span></div>')
    th = sm["stale_threshold_s"] // 3600
    w('<section class="howto" id="howto"><h3>Sådan læses tallene</h3><ul>'
      '<li><b>Netto</b> = seneste equity-mærke minus startkapital, som defineret i net_report: det seneste timemærke '
      'på eller før cutoff.</li>'
      f'<li><b>FRESH</b> = mærket er højst {th} t gammelt ved cutoff. <b>STALE</b> = mærket er ældre; tallet er den '
      'sidst kendte værdi og ikke aktuelt. <b>MISSING_MARK</b> = intet mærke før cutoff.</li>'
      '<li>Funding, gebyrer og fyld kan ligge senere end mærket: fyldtal og feed går til cutoff, netto står ved '
      'mærket.</li>'
      '<li>Papir-P&amp;L uden gearing og uden marginmodel.</li></ul></section>')

    # --- top cards ---
    cur = sm["portfolio_current_total"]
    w('<section class="tops">')
    if cur is not None and n_acc > 0:
        cap = sum(a["capital"] for a in accs)
        val = sum(a["value"] for a in accs)
        w(f'<div class="top"><h3>Aktuel porteføljeværdi</h3><div class="big {tone(cur)}" id="portfolio">'
          f'{e(money(cur))}</div><div class="sub">samlet netto ved mærket, alle {n_acc} konti FRESH; '
          f'kapital {cap:,.2f} → værdi {val:,.2f}</div></div>')
    else:
        why = (f'{sm["stale"]} konti STALE / {sm["missing_mark"]} MISSING_MARK' if n_acc else "ingen konti i lab.db")
        w(f'<div class="top na"><h3>Aktuel porteføljeværdi</h3><div class="big" id="portfolio">Ikke tilgængelig</div>'
          f'<div class="sub">{e(why)}; en samlet værdi vises kun når alle konti er FRESH</div></div>')
    if sm["fresh"]:
        nf = sm["net_fresh_total"]
        w(f'<div class="top"><h3>FRESH-konti netto</h3><div class="big {tone(nf)}">{e(money(nf))}</div>'
          f'<div class="sub">{sm["fresh"]} af {n_acc} konti; mærke højst '
          f'{sm["stale_threshold_s"] // 3600} t gammelt ved cutoff</div></div>')
    else:
        w(f'<div class="top na"><h3>FRESH-konti netto</h3><div class="big">Ikke tilgængelig</div>'
          f'<div class="sub">0 af {n_acc} konti FRESH</div></div>')
    if sm["stale"]:
        ns = sm["net_stale_last_known"]
        w(f'<div class="top stale"><h3>Sidst kendt netto, STALE-konti</h3><div class="big {tone(ns)}">'
          f'{e(money(ns))}</div><div class="sub"><b>Ikke aktuel</b>: {sm["stale"]} konti med mærke ældre end '
          f'{sm["stale_threshold_s"] // 3600} t</div></div>')
    else:
        w('<div class="top"><h3>Sidst kendt netto, STALE-konti</h3><div class="big zero">–</div>'
          '<div class="sub">ingen STALE-konti</div></div>')
    w("</section>")

    # --- filters ---
    w('<section class="filters" aria-label="filtre">')
    w('<div class="frow"><b>Bot</b><label class="pill" for="fb-all">Alle</label>'
      + "".join(f'<label class="pill" for="fb-{ident(a["ledger"])}">{e(names[a["ledger"]])}</label>' for a in accs)
      + "</div>")
    w('<div class="frow"><b>Periode</b><label class="pill" for="fp-all">Alt</label>'
      '<label class="pill" for="fp-24">24 t</label><label class="pill" for="fp-7">7 d</label>'
      '<span class="sub">(relativt til cutoff; gælder aktivitetsfeedet)</span></div>')
    w('<div class="frow"><b>Status</b><label class="pill" for="fs-all">Alle</label>'
      '<label class="pill" for="fs-FRESH">FRESH</label><label class="pill" for="fs-STALE">STALE</label>'
      '<label class="pill" for="fs-MISSING_MARK">MISSING_MARK</label></div>')
    w("</section>")

    # --- bot grid ---
    w(f'<h2>Copy grid <small>· {n_acc} papirkonti · netto = seneste mærke − kapital</small></h2>')
    w('<section class="grid">')
    if not accs:
        w('<div class="empty">Ingen papirkonti fundet (ingen lane.started-hændelser).</div>')
    for a in accs:
        led, st = a["ledger"], a["mark_status"]
        nm = names[led]
        if st == "FRESH":
            chip = f'<span class="chip c-FRESH">FRESH</span>'
            netline = f'<div class="bnet {tone(a["net"])}">{e(money(a["net"]))}</div>'
            scls = tone(a["net"])
        elif st == "STALE":
            age = a["mark_age_s"] / 3600
            chip = (f'<span class="chip c-STALE">Forældet — mærket {e(utc(a["marked_at"], "%m-%d %H:%M"))}, '
                    f'{age:.1f} t</span>')
            netline = (f'<div class="bnet {tone(a["net"])}">{e(money(a["net"]))}</div>'
                       f'<div class="sub">sidst kendt, ikke aktuel</div>')
            scls = "old"
        else:
            chip = '<span class="chip c-MISSING_MARK">MISSING_MARK</span>'
            netline = '<div class="bnet zero">–</div><div class="sub">ingen mærkning før cutoff</div>'
            scls = "old"
        w(f'<article class="bot b-{ident(led)} s-{st}">')
        w(f'<div class="bhead"><div style="display:flex;gap:10px"><div class="avatar">{e(nm[:1].upper())}</div>'
          f'<div><div class="bname">{e(nm)}</div><div class="bled">{e(led)}</div></div></div>'
          f'<span class="src">{e(a["source"])}</span></div>')
        w(f"<div>{chip}</div>")
        w(netline)
        w(conspark(led, a["capital"], scls))
        w(f'<div class="stats"><span>Aktiv</span><b>{"ja" if a["active"] else "nej"}</b>'
          f'<span>Fyld</span><b>{a["fills"]}</b>'
          f'<span>Maks. fald</span><b>{a["max_drawdown"]:.2%}</b>'
          f'<span>Kapital</span><b>{a["capital"]:,.0f}</b>'
          f'<span>Seneste mærke</span><b>{e(utc(a["marked_at"], "%m-%d %H:%M:%S"))}</b></div>')
        w("</article>")
    w("</section>")

    # --- HANDELSCHART (59-K): read-only trade charts under the bot overview ---
    if hc[2]:
        w(hc[2])

    # --- activity feed ---
    shown = len(frows)
    allr = totals["fills"] + totals["events"]
    w(f'<h2>Aktivitet <small>· {shown} nyeste af {allr} registrerede hændelser til cutoff '
      f'({totals["fills"]} fyld, {totals["events"]} overspring/afvisninger/fejl); maks. {feed_n} vises</small></h2>')
    w('<section id="feed">')
    if not frows:
        w('<div class="feedbox"><div class="empty">Ingen registrerede papirhændelser til cutoff.</div></div>')
    rowhtml = {"fill": [], "other": []}
    for r in frows:
        led = r["ledger"]
        st = status.get(led, "MISSING_MARK")
        cls = ["ev", f"b-{ident(led)}", f"s-{st}"]
        if r["ts"] > cutoff - DAY:
            cls.append("in24")
        if r["ts"] > cutoff - 7 * DAY:
            cls.append("in7")
        who = names.get(led, led)
        if r["kind"] == "fill":
            cls.append("fill")
            sd = "buy" if r["side"] == "buy" else "sell"
            what = (f'<span class="side {sd}">{"KØB" if sd == "buy" else "SÆLG"}</span>'
                    f'{r["qty"]:.6g} @ {r["px"]:.6g}<span class="fee">gebyr −{abs(r["fee"] or 0):.4f}</span>')
        else:
            bad = r["kind"] in ("paper.error", "paper.mark_failed")
            cls.append("err" if bad else "skip")
            lab = KIND_LABEL.get(r["kind"], r["kind"])
            what = (f'<span class="side {"er" if bad else "sk"}">{e(lab)}</span>'
                    f'<span class="why">{e(r["kind"])}: {e(r["reason"][:240])}</span>')
        rowhtml["fill" if r["kind"] == "fill" else "other"].append(
            f'<div class="{" ".join(cls)}" data-kind="{e(r["kind"])}"><span class="t">{e(utc(r["ts"]))}</span>'
            f'<span class="who">{e(who)}</span><span class="sym">{e(r["instrument"])}</span><span>{what}</span></div>')
    if frows:
        for key, tag, title, total, none in (
                ("fill", "t-fill", "Udførte papirhandler", totals["fills"],
                 "Ingen udførte papirhandler blandt de viste."),
                ("other", "t-skip", "Spring over / afvisninger / fejl", totals["events"],
                 "Ingen overspring, afvisninger eller fejl blandt de viste.")):
            rs = rowhtml[key]
            w(f'<h3 class="fh" id="feed-{key}"><span class="tag {tag}">{e(title)}</span><small>{len(rs)} viste af '
              f'{total} til cutoff</small></h3>')
            w(f'<div class="feedbox fb-{key}">' + ("\n".join(rs) if rs else f'<div class="empty">{e(none)}</div>')
              + "</div>")
    w("</section>")

    # --- STRATEGIKIRKEGÅRD (60-D): every registered attempt, read-only, after the activity feed ---
    if gy[2]:
        w(gy[2])

    # --- footer ---
    w("<footer>")
    w(f'<p><b>Datakilde:</b> {e(db_path)} (mode=ro, PRAGMA query_only=ON). Tal pr. konto og summen fra '
      f'research/tools/net_report.build; feed fra sim_fills og events (' + ", ".join(SKIP_KINDS) + ').</p>')
    w(f"<p><b>Genereret:</b> {e(utc(now))} · <b>Cutoff:</b> {e(utc(cutoff))} · STALE-tærskel "
      f"{sm['stale_threshold_s'] // 3600} t</p>")
    w("<p><b>Ansvarsfraskrivelse:</b> Beskrivende papir-P&amp;L uden gearing og uden marginmodel (ubegrænset "
      "sikkerhedsstillelse for korte perp-ben). Ikke en verificeret eksekverbar strategi. Ikke "
      "investeringsrådgivning. Live-handel: <b>NO-GO</b>. Ingen knapper, ingen ordrer, ingen konti eller wallets.</p>")
    w("<p>Lokal prototype (direktørordre 59-H P2, 59-J, 59-K Handelschart, 60-D Strategikirkegård). Produktionsdeploy: NO-GO indtil direktørgennemgang.</p>")
    w("</footer></div></body></html>")
    return "\n".join(out) + "\n"


def render(con, now, cutoff, db_path=DB, feed_n=200, factory_dir=paper_graveyard.FACTORY):
    rep = net_report.build(con, int(now), int(cutoff))
    frows, totals = feed(con, [a["ledger"] for a in rep["accounts"]], int(cutoff), int(feed_n))
    return page(rep, frows, totals, db_path, feed_n,
                lambda led, cap, cls: spark(con, led, int(cutoff), cap, cls),
                lambda names: paper_chart.section(con, rep, int(cutoff), names, SKIP_KINDS),
                lambda: paper_graveyard.section(factory_dir))


def write_atomic(path, doc):
    """Director order 63: the browser must never read a half-written page. Write a temp file in the same folder,
    fsync it and rename it over the target; on any error the last good snapshot stays."""
    d = os.path.dirname(os.path.abspath(path)) or "."
    tmp = os.path.join(d, f".{os.path.basename(path)}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(doc)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def main(argv=None, now=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB)
    ap.add_argument("--cutoff", help="UTC cutoff YYYY-MM-DDTHH:MM:SSZ (default: now)")
    ap.add_argument("--out", required=True, help="output .html path")
    ap.add_argument("--feed", type=int, default=200, help="max feed rows (default 200)")
    ap.add_argument("--factory", default=paper_graveyard.FACTORY,
                    help="factory register folder for STRATEGIKIRKEGÅRD (read-only; default research/data/factory)")
    ap.add_argument("--refresh", type=int, default=0,
                    help="add <meta http-equiv=refresh> every N seconds (director order 63; 0 = off; no JavaScript)")
    a = ap.parse_args(argv)
    now = int(dt.datetime.now(dt.timezone.utc).timestamp()) if now is None else int(now)
    cutoff = parse_cutoff(a.cutoff) if a.cutoff else now
    con = connect_ro(a.db)
    try:
        doc = render(con, now, cutoff, a.db, a.feed, a.factory)
    finally:
        con.close()
    if a.refresh:
        if not 30 <= a.refresh <= 3600:
            raise SystemExit("--refresh must be 30..3600 seconds")
        doc = doc.replace('<meta charset="utf-8">',
                          f'<meta charset="utf-8"><meta http-equiv="refresh" content="{int(a.refresh)}">', 1)
    write_atomic(a.out, doc)
    print(f"{a.out}: {len(doc.encode())} bytes, cutoff {utc(cutoff)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
