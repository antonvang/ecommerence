"""PAPER DASHBOARD V3: one static, self-contained, read-only HTML page of the paper books (director orders 59-H P2,
59-J, 59-K, 60-D, 63, 69 P0 "DASHBOARD V3" and 70 P3 "V4": readability, hierarchy, mobile, data-quality section).

    python3 research/tools/paper_dashboard.py [--db PATH] [--cutoff YYYY-MM-DDTHH:MM:SSZ] --out PATH.html [--feed N]
                                              [--factory DIR] [--refresh SECONDS]

LOCAL prototype only; production deploy is NO-GO until director review (research/desk/PAPER_DASHBOARD_V2.md, V3 part).

Every number per account (net at the mark, mark time and age, FRESH/STALE/MISSING_MARK, fills, max drawdown) and the
summary come from research.tools.net_report.build(con, now, cutoff); nothing is recomputed here. The activity feed lists
recorded sim_fills rows and recorded skip/refusal/error events of the shown ledgers, newest first, up to the cutoff.
No current portfolio value is shown unless every account is FRESH (and at least one account exists).

V3 layout (order 69), top to bottom:
1. Header: COPYBOT, the PAPER / SIMULATION badge, the snapshot (generation) time and data cutoff in UTC, and a health
   strip: FRESH / STALE / MISSING_MARK counts, a light DB check (lab_qc.SCHEMA_TABLES present; the full integrity and
   hash-chain checks are too heavy for a 5-minute refresh, so the strip says "kør lab_qc" and shows the last run
   documented in research/desk/LAB_QC.md) and the last report reconciliation (research/data/net_report/reconcile_*.md).
2. Overblik: only current paper data. Hero cards for the FRESH accounts, the FRESH net total labelled as such, and
   "Aktuel porteføljeværdi: Ikke tilgængelig" whenever any account is STALE or MISSING_MARK.
3. Arkiv - forældede konti (<details>, collapsed): STALE and MISSING_MARK accounts with their history, sparkline (grey),
   last mark time, age and data quality (recorded paper.mark_failed events and the static STALE_NOTE); every number is
   labelled "sidst kendt, ikke aktuel" and is never coloured green/red.
4. HANDELSCHART (research/tools/paper_chart.py): one responsive SVG per instrument of the FRESH books.
5. Aktivitet: CSS-only filters, then executed paper fills and skips/refusals/errors in two boxes.
6. FORSKNINGSOVERSIGT (research/tools/paper_research.py): candidates, milestones and blockers read from
   research/desk/FALSIFICATION_MATRIX_ORDER61.md, each with its source path; "Ingen valideret profitabel strategi".
7. STRATEGIKIRKEGÅRD (research/tools/paper_graveyard.py), collapsed by default.
8. Footer: sources, read-only statement, disclaimer.
Cards are ordered FRESH, STALE, MISSING_MARK, then by name, start time and ledger id; duplicate names are numbered
"name #1", "name #2" by (start time, ledger id) on the card, the filter chip and the feed rows.

Read-only: lab.db is opened as file:...?mode=ro with PRAGMA query_only=ON. No network, no JS, no external resources;
filters and folding are pure HTML/CSS (radio inputs + :checked sibling selectors, <details>). The page does not
refresh itself unless --refresh adds a <meta http-equiv="refresh">.
"""
import argparse
import collections
import datetime as dt
import glob
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
from research.tools import paper_research  # noqa: E402

DB = net_report.DB
HERE = paper_research.HERE
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
LAB_QC_DOC = os.path.join("research", "desk", "LAB_QC.md")
RECONCILE_GLOB = os.path.join("research", "data", "net_report", "reconcile_*.md")
# Static data-quality note (order 69): why the lane/carry90 books are STALE. Text only; it is shown as the documented
# cause for STALE accounts whose source has a spot leg, never used to compute or hide anything.
SPOT_SOURCES = ("lane", "carry90")
STALE_NOTE = ("Spotbenet i lane- og carry90-kontiene mærkes fra data-api.binance.vision. Den lokale DNS blokerer den "
              "vært siden ca. 2026-11-06 20:45 UTC (kun en kort åbning 2026-11-08 06:39–06:45 UTC), så equity-mærket "
              "står stille, mens funding stadig bogføres. Blokeringen omgås ikke.")
STALE_NOTE_SRC = ("research/desk/MARK_FAILED_59D.md", "research/desk/STALE_EQUITY_59C.md",
                  "research/desk/FALSIFICATION_MATRIX_ORDER61.md §3")
STALE_NOTE_AS_OF = "2026-11-09"


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


def mark_quality(con, ledgers, cutoff):
    """Recorded paper.mark_failed events per ledger up to the cutoff: {ledger: (count, last ts)} (data quality)."""
    leds = sorted(ledgers)
    if not leds:
        return {}
    ph = ",".join("?" * len(leds))
    return {led: (n, last) for led, n, last in con.execute(
        f"SELECT exp_id, COUNT(*), MAX(ts) FROM events WHERE kind='paper.mark_failed' AND ts<=? AND exp_id IN ({ph}) "
        f"GROUP BY exp_id", (cutoff, *leds))}


def health(con, root):
    """Light, read-only health facts for the header strip. Nothing heavy runs here (the dashboard refreshes every
    5 minutes): the schema-table presence check of lab_qc on the open read-only connection, the last lab_qc run as
    documented in LAB_QC.md, and the status line of the newest reconcile_*.md. Missing pieces say so."""
    h = {"schema": None, "qc": None, "rec": None}
    try:
        from research.tools import lab_qc
        want = tuple(lab_qc.SCHEMA_TABLES)
    except Exception:                                     # lab_qc not importable: skip, the strip says "kør lab_qc"
        want = ()
    if want:
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        h["schema"] = (sum(1 for t in want if t in have), len(want))
    try:
        with open(os.path.join(root, LAB_QC_DOC), encoding="utf-8") as f:
            runs = re.findall(r"^## [^\n(]*\((\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)[^)\n]*\)\s*\n+Samlet \*\*([A-Z]+)\*\*"
                              r"[^:\n]*:\s*([^\n]+?)\.?\s*$", f.read(), re.M)
        if runs:
            h["qc"] = runs[-1]
    except OSError:
        pass
    files = sorted(glob.glob(os.path.join(root, RECONCILE_GLOB)))
    if files:
        try:
            with open(files[-1], encoding="utf-8") as f:
                m = re.search(r"\*\*Status: ([A-Z_]+)\*\*", f.read())
            day = re.search(r"reconcile_(\d{4}-\d\d-\d\d)\.md$", files[-1])
            h["rec"] = (day.group(1) if day else "?", m.group(1) if m else "ukendt",
                        os.path.relpath(files[-1], root))
        except OSError:
            pass
    return h


CSS = """
:root{color-scheme:dark;--bg:#0b0e14;--panel:#121722;--panel2:#181e2b;--plot:#0e131d;--line:#232b3b;--txt:#e7ebf2;
--mut:#8b95a7;--pos:#16c784;--neg:#ff4d5e;--amb:#f2b33d;--acc:#6d7cff;--blu:#4aa3f0;--pos-bg:rgba(22,199,132,.12);
--neg-bg:rgba(255,77,94,.12);--amb-bg:rgba(242,179,61,.12);--blu-bg:rgba(74,163,240,.12);
--sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 var(--sans);
-webkit-text-size-adjust:100%}
.f{position:absolute;opacity:0;pointer-events:none;width:1px;height:1px}
.wrap{max-width:1320px;margin:0 auto;padding:0 20px 40px}
code{font:12px var(--mono)}
.hdr{display:grid;grid-template-columns:1fr auto;gap:12px 24px;align-items:center;padding:16px 0 12px;
border-bottom:1px solid var(--line)}
.brand{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center}
.logo{font-weight:800;letter-spacing:.16em;font-size:20px}.logo span{color:var(--acc)}
.paper{background:var(--amb);color:#1a1200;font-weight:800;font-size:13px;padding:5px 10px;border-radius:6px;
letter-spacing:.03em}
.banner{text-align:right;font-size:12px;color:var(--mut);line-height:1.55}
.banner b{color:var(--txt);font-weight:600}.banner>b:first-child{font-weight:500;color:var(--mut)}
.banner code{display:inline-block;margin:2px 0;padding:1px 6px;border-radius:4px;background:var(--panel2);
color:#b9c3d6;overflow-wrap:anywhere}.banner code span{white-space:nowrap}.banner .bcut{display:block}
.strip{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;font-size:12px}
.hs{display:inline-flex;gap:6px;align-items:center;padding:3px 9px;border-radius:6px;background:var(--panel);
border:1px solid var(--line);color:var(--mut);white-space:nowrap}.hs b{color:var(--txt);font-variant-numeric:tabular-nums}
.hs i{width:7px;height:7px;border-radius:50%;display:inline-block}
.d-f{background:var(--pos)}.d-s{background:var(--amb)}.d-m{background:var(--neg)}.d-n{background:var(--mut)}
.hs.hq{white-space:normal}
.health{display:inline-block;padding:3px 9px;border-radius:6px;font-weight:700;font-size:12px}
.h-ok{background:var(--pos-bg);color:var(--pos)}.h-warn{background:var(--amb-bg);color:var(--amb)}
.h-bad{background:var(--neg-bg);color:var(--neg)}
.toc{position:sticky;top:0;z-index:5;display:flex;gap:2px;overflow-x:auto;white-space:nowrap;padding:6px 0;
background:rgba(11,14,20,.94);border-bottom:1px solid var(--line);margin:0 0 4px;scrollbar-width:none}
.toc a{color:var(--mut);text-decoration:none;font-size:13px;padding:5px 10px;border-radius:6px}
.toc a:hover{color:var(--txt);background:var(--panel)}
h2{font-size:17px;font-weight:700;margin:32px 0 12px;letter-spacing:.01em;display:flex;flex-wrap:wrap;
align-items:baseline;gap:4px 10px}
h2 small{color:var(--mut);font-weight:400;font-size:13px}
.sub{color:var(--mut);font-size:12px}
.pos{color:var(--pos)}.neg{color:var(--neg)}.zero,.old{color:var(--mut)}
.tops{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 12px}
.top{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.top h3{margin:0 0 6px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--mut)}
.big,.kn{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2;letter-spacing:-.01em}
.kn small{font-size:15px;color:var(--mut);font-weight:500}
.top.na{border-color:rgba(242,179,61,.35)}.top.na .big{color:var(--amb);font-size:24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.arch-grid{grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}
.bot{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;
flex-direction:column;gap:8px;min-width:0}
.bot.s-FRESH{border-top:2px solid var(--pos)}
.bhead{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.bname{font-weight:700;font-size:15px;word-break:break-word}.bled{color:var(--mut);font:11px var(--mono)}
.src{font-size:11px;font-weight:600;padding:2px 7px;border-radius:5px;background:var(--panel2);color:#a9b4c7;
text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}
.chip{display:inline-block;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700}
.c-FRESH{background:var(--pos-bg);color:var(--pos)}.c-STALE{background:var(--amb-bg);color:var(--amb)}
.c-MISSING_MARK{background:var(--neg-bg);color:var(--neg)}
.bmid{display:flex;justify-content:space-between;align-items:center;gap:8px}
.bnet{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.01em;line-height:1.15}
.stats{display:grid;grid-template-columns:auto 1fr auto 1fr;gap:3px 10px;font-size:12px;color:var(--mut)}
.stats b{color:var(--txt);font-weight:600;font-variant-numeric:tabular-nums}
.mk-at{font-size:12px;color:var(--mut)}.mk-at b{color:var(--txt);font-weight:600;font-variant-numeric:tabular-nums}
.spark{width:100%;height:56px}.spark polyline{fill:none;stroke-width:1.6;vector-effect:non-scaling-stroke}
.spark .base{stroke:#2d3648;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
.spark.pos polyline{stroke:var(--pos)}.spark.neg polyline{stroke:var(--neg)}
.spark.zero polyline,.spark.old polyline{stroke:#6f7a8f}
.spark.none{font-size:11px;color:var(--mut);height:auto}
.howto{margin:12px 0 0;padding:10px 14px;border:1px solid var(--line);border-radius:12px;font-size:12px;
background:transparent}.howto h3{margin:0 0 4px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;
color:var(--mut)}.howto ul{margin:0;padding-left:16px;columns:2 360px;column-gap:28px}
.howto li{margin:2px 0;color:var(--mut);break-inside:avoid}.howto li b{color:var(--txt)}
details.fold{margin:28px 0 0;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
details.fold>summary{cursor:pointer;list-style:none;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;
padding:14px 16px}
details.fold>summary::-webkit-details-marker{display:none}
details.fold>summary::before{content:"\\25B8";color:var(--mut);font-size:12px;width:12px}
details.fold[open]>summary::before{content:"\\25BE"}
details.fold[open]>summary{border-bottom:1px solid var(--line)}
.sum-t{font-size:17px;font-weight:700}.sum-s{color:var(--mut);font-size:13px}
.fold-in{padding:14px 16px 16px}
.fold .gv>h2{display:none}
.arch .bot{background:var(--panel2);border-style:dashed}
.arch .bnet{font-size:22px}
.arch .top{background:var(--panel2);margin:0 0 12px;max-width:520px}
.why{margin:0 0 14px;padding:10px 14px;border-left:3px solid var(--amb);background:var(--amb-bg);border-radius:6px;
font-size:13px}.why p{margin:0 0 4px}.why .rs-src{margin-top:4px}
.dq{font-size:12px;color:var(--mut);border-top:1px solid var(--line);padding-top:6px}.dq b{color:var(--txt)}
.ah3{margin:18px 0 8px;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}
.filters{display:flex;flex-direction:column;gap:6px;margin:0 0 12px}
.frow{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.frow>b{color:var(--mut);font-size:12px;
font-weight:600;width:64px}
.pill{cursor:pointer;padding:3px 10px;border-radius:999px;border:1px solid var(--line);background:var(--panel);
color:var(--mut);font-size:12px;user-select:none}
#feed{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);grid-template-rows:auto auto;grid-auto-flow:column;
gap:8px 16px}
#feed>.feedbox:only-child{grid-column:1/-1}
.feedbox{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:auto;max-height:620px}
.ev{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:2px 10px;padding:8px 12px;
border-top:1px solid var(--line);font-size:13px;align-items:baseline}
.ev:first-child{border-top:0}
.ev .t{color:var(--mut);font:12px var(--mono);white-space:nowrap}
.ev .who{font-weight:600;word-break:break-word}.ev .sym{font:12px var(--mono);color:#b9c3d6}
.ev>span:last-child{grid-column:1/-1}
.ev.fill{box-shadow:inset 3px 0 0 var(--blu)}
.ev.skip{box-shadow:inset 3px 0 0 var(--amb)}
.ev.err{background:rgba(255,77,94,.05);box-shadow:inset 3px 0 0 var(--neg)}
.fh{margin:0;font-size:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-weight:600}
.fh small{color:var(--mut);font-weight:400}
.tag{padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;letter-spacing:.03em}
.t-fill{background:var(--blu-bg);color:var(--blu)}.t-skip{background:var(--amb-bg);color:var(--amb)}
.side{display:inline-block;min-width:44px;text-align:center;padding:1px 6px;border-radius:4px;font-size:11px;
font-weight:700;margin-right:6px}.buy{background:var(--pos-bg);color:var(--pos)}
.sell{background:var(--neg-bg);color:#ff8a96}.sk{background:var(--amb-bg);color:var(--amb)}
.er{background:var(--neg-bg);color:var(--neg)}
.fee{color:var(--mut);font-size:12px;margin-left:8px}.why-t{color:var(--mut)}
.empty{padding:16px;color:var(--mut)}
footer{margin-top:36px;padding-top:16px;border-top:1px solid var(--line);color:var(--mut);font-size:12px}
footer p{margin:4px 0}footer b{color:var(--txt)}footer ul{margin:4px 0 8px;padding-left:16px}
footer code{color:#b9c3d6}
@media (max-width:1000px){.tops{grid-template-columns:1fr 1fr}.tops .top:first-child{grid-column:1/-1}
#feed{grid-template-columns:1fr;grid-auto-flow:row}.hdr{grid-template-columns:1fr}.banner{text-align:left}}
@media (max-width:600px){.wrap{padding:0 14px 32px}.tops{grid-template-columns:1fr}.big,.kn{font-size:26px}
.paper{font-size:12px}.logo{font-size:18px}.grid{grid-template-columns:1fr}.stats{grid-template-columns:auto 1fr}
.feedbox{max-height:520px}h2{font-size:16px}.sum-t{font-size:16px}}
"""


# V4 (order 70 P3): a layer on top of the V3 CSS. Readability, spacing and touch targets only.
CSS_V4 = """
html,body{font-size:15px}
.wrap{max-width:1240px;padding:0 24px 56px}
.hdr{padding:20px 0 14px}
.banner code{display:none}
.toc{padding:8px 0;margin:0 0 8px}.toc a{font-size:14px;padding:8px 12px}
h2{font-size:20px;margin:44px 0 16px}h2 small{font-size:13px}
.sum-t{font-size:18px}
.tops{gap:16px;margin:0 0 16px}.top{padding:20px 22px}.top h3{font-size:12px;margin:0 0 10px}
.big,.kn{font-size:40px;line-height:1.1}.kn small{font-size:16px}.top.na .big{font-size:26px}
.sub{font-size:13px;margin-top:6px}
.grid{gap:16px}.bot{padding:18px 20px;gap:10px}.bname{font-size:16px}.bnet{font-size:34px}
.stats{font-size:13px;gap:4px 12px}.spark{height:64px}
.pill{padding:6px 12px;font-size:13px}
.ev{padding:10px 14px;font-size:13.5px}
.dqp .dq-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.dqc{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;align-items:baseline;align-content:start;background:var(--panel);
border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.dqc i{width:9px;height:9px;border-radius:50%;display:inline-block}
.dqc b{font-size:14px}.dqc span{grid-column:2;color:var(--mut);font-size:13px;overflow-wrap:anywhere}
.dqc.warn{border-color:rgba(242,179,61,.45)}.dqc.bad{border-color:rgba(255,77,94,.5)}
.hist-mark{margin:44px 0 -28px;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
@media (max-width:1000px){.big,.kn{font-size:34px}}
@media (max-width:600px){.toc{position:static;display:grid;grid-template-columns:repeat(4,1fr);overflow:visible;white-space:normal;gap:4px}
.toc a{padding:9px 2px;text-align:center;font-size:12.5px;background:var(--panel);overflow-wrap:anywhere}
.wrap{padding:0 16px 40px}.big,.kn{font-size:32px}.bnet{font-size:30px}h2{font-size:18px;margin:32px 0 12px}
.top{padding:16px}.toc a{padding:10px 12px}.howto ul{columns:1}.frow>b{width:100%}.hs{white-space:normal}}
"""

# Static note like STALE_NOTE; the diagnostic numbers live in the source file.
PMLP_NOTE_AS_OF = "2026-11-09"
PMLP_NOTE = ("pm_lp_v1: PASS_UNREACHABLE / PENDING_FORMAL_CLOSE. D1 kan ikke længere nås; ingen påstand om hypotesen.")
PMLP_NOTE_SRC = "research/desk/PM_LP_D1_STATUS_72.md"


def bot_card(a, nm, conspark, quality, cutoff):
    """One account card. FRESH: coloured net (current). STALE / MISSING_MARK: grey net, labelled last known."""
    led, st = a["ledger"], a["mark_status"]
    o = [f'<article class="bot b-{ident(led)} s-{st}">',
         f'<div class="bhead"><div><div class="bname">{e(nm)}</div><div class="bled">{e(led)}</div></div>'
         f'<span class="src">{e(a["source"])}</span></div>']
    if st == "FRESH":
        age = a.get("mark_age_s")
        o.append(f'<div class="bmid"><div class="bnet {tone(a["net"])}">{e(money(a["net"]))}</div>'
                 f'<span title="Datamærkets alder, ikke strategiens kvalitet" class="chip c-FRESH">FRESH</span></div>'
                 '<div class="sub">netto ved mærket · papir-P&amp;L, ikke valideret</div>')
        scls = tone(a["net"])
        agetxt = f"{int(age // 60)} min" if age is not None else "–"
    elif st == "STALE":
        age = a["mark_age_s"] / 3600
        o.append(f'<div><span class="chip c-STALE">Forældet — mærket {e(utc(a["marked_at"], "%m-%d %H:%M"))}, '
                 f'{age:.1f} t</span></div>')
        o.append(f'<div class="bnet old">{e(money(a["net"]))}</div><div class="sub">sidst kendt, ikke aktuel</div>')
        scls, agetxt = "old", None
    else:
        o.append('<div><span class="chip c-MISSING_MARK">MISSING_MARK</span></div>')
        o.append('<div class="bnet zero">–</div><div class="sub">ingen mærkning før cutoff</div>')
        scls, agetxt = "old", None
    o.append(conspark(led, a["capital"], scls))
    o.append(f'<div class="stats"><span>Fyld</span><b>{a["fills"]}</b>'
             f'<span>Maks. fald</span><b>{a["max_drawdown"]:.2%}</b>'
             f'<span>Kapital</span><b>{a["capital"]:,.0f}</b>'
             f'<span>Aktiv</span><b>{"ja" if a["active"] else "nej"}</b></div>'
             f'<div class="mk-at">Seneste mærke <b>{e(utc(a["marked_at"], "%m-%d %H:%M:%S"))}</b>'
             + (f' · alder <b>{e(agetxt)}</b>' if agetxt else "") + "</div>")
    if st != "FRESH":
        n, last = quality.get(led, (0, None))
        mf = (f"paper.mark_failed {n}×, senest {e(utc(last, '%m-%d %H:%M'))}" if n else "0× paper.mark_failed")
        why = ("årsag: spotben/DNS (se noten øverst)" if a["source"] in SPOT_SOURCES and st == "STALE"
               else "årsag ikke registreret her; kør lab_qc")
        o.append(f'<div class="dq"><b>Datakvalitet:</b> {st} · {mf} · {e(why)}</div>')
    o.append("</article>")
    return "".join(o)


def page(rep, frows, totals, db_path, feed_n, conspark, chart=None, graveyard=None, research=None, quality=None,
         hinfo=None):
    sm = rep["summary"]
    cutoff, now = sm["cutoff"], rep["generated"]
    accs = ordered(rep["accounts"])
    n_acc = len(accs)
    names = labels(accs)
    status = {a["ledger"]: a["mark_status"] for a in accs}
    fresh = [a for a in accs if a["mark_status"] == "FRESH"]
    old = [a for a in accs if a["mark_status"] == "STALE"]
    nomark = [a for a in accs if a["mark_status"] not in ("FRESH", "STALE")]
    quality = quality or {}
    hinfo = hinfo or {"schema": None, "qc": None, "rec": None}
    th = sm["stale_threshold_s"] // 3600
    out = []
    w = out.append

    # --- filter state inputs (pure CSS filters; they act on the activity feed) ---
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
    rs = research() if research else ("", "")           # 69 FORSKNINGSOVERSIGT: (css, section html)
    css = [CSS, hc[1], gy[1], rs[0], CSS_V4]
    on = "{background:var(--acc);color:#fff;border-color:var(--acc)}"
    for b in bot_ids:
        css.append(f"#fb-{b}:checked~.wrap label[for=fb-{b}]{on}")
        if b != "all":
            css.append(f"#fb-{b}:checked~.wrap .ev:not(.b-{b}){{display:none}}")
    for p in ("all", "24", "7"):
        css.append(f"#fp-{p}:checked~.wrap label[for=fp-{p}]{on}")
    css.append("#fp-24:checked~.wrap .ev:not(.in24),#fp-7:checked~.wrap .ev:not(.in7){display:none}")
    for s in ("all", "FRESH", "STALE", "MISSING_MARK"):
        css.append(f"#fs-{s}:checked~.wrap label[for=fs-{s}]{on}")
        if s != "all":
            css.append(f"#fs-{s}:checked~.wrap .ev:not(.s-{s}){{display:none}}")

    w("<!DOCTYPE html>")
    w('<html lang="da"><head><meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width,initial-scale=1">')
    w("<title>COPYBOT Paper Dashboard</title>")
    w("<style>" + "\n".join(css) + "</style></head><body>")
    w("\n".join(radios))
    w('<div class="wrap">')

    # --- 1. header: brand, PAPER badge, snapshot + cutoff (UTC), health strip ---
    if n_acc == 0:
        health_chip = '<span class="health h-bad">INGEN DATA</span>'
    elif sm["missing_mark"]:
        health_chip = f'<span class="health h-bad">MANGLER MÆRKNING: {sm["missing_mark"]}</span>'
    elif sm["stale"]:
        health_chip = f'<span class="health h-warn">FORÆLDEDE MÆRKER: {sm["stale"]}</span>'
    else:
        health_chip = '<span class="health h-ok">ALLE MÆRKER FRISKE</span>'
    w('<header class="hdr"><div class="brand"><div class="logo">COPY<span>BOT</span></div>'
      '<div class="paper" id="paper-badge">PAPER / SIMULATION — ingen rigtige penge</div></div>')
    w(f'<div class="banner" id="snapshot"><b>Statisk snapshot genereret {e(utc(now))}. Kør kommandoen igen for nye '
      f'tal.</b><br><code>{e(CMD_HEAD)} <span>{e(CMD_ARG)}</span></code>'
      f'<span class="bcut">Datacutoff: <b>{e(utc(cutoff))}</b> · tallene er frosset '
      f'ved cutoff og opdaterer ikke sig selv · kun registrerede papirdata fra lab.db</span></div>')
    sc = hinfo["schema"]
    if sc is None:
        db_txt, db_dot = "DB: let tjek ikke muligt — kør lab_qc", "d-n"
    else:
        db_txt = f"DB: skema {sc[0]}/{sc[1]} tabeller (let tjek)"
        db_dot = "d-f" if sc[0] == sc[1] else "d-m"
    qc = hinfo["qc"]
    qc_txt = (f"Fuld integritet + hashkæder: kør lab_qc · senest dokumenteret {qc[0]}: {qc[1]} ({qc[2]}) · "
              f"{LAB_QC_DOC}" if qc else "Fuld integritet + hashkæder: kør lab_qc (ingen dokumenteret kørsel fundet)")
    qc_dot = "d-n" if not qc else {"PASS": "d-f", "WARN": "d-s"}.get(qc[1], "d-m")
    rec = hinfo["rec"]
    rec_txt = (f"Rapportafstemning {rec[0]}: {rec[1]} · {rec[2]}" if rec else "Rapportafstemning: ingen fundet")
    rec_dot = "d-n" if not rec else ("d-f" if rec[1] == "RECONCILED" else "d-m")
    w(f'<div class="strip" id="health"><span class="hs"><i class="d-f"></i>FRESH <b>{sm["fresh"]}</b></span>'
      f'<span class="hs"><i class="d-s"></i>STALE <b>{sm["stale"]}</b></span>'
      f'<span class="hs"><i class="d-m"></i>MISSING_MARK <b>{sm["missing_mark"]}</b></span>{health_chip}</div></header>')
    w('<nav class="toc" aria-label="sektioner"><a href="#overblik">Overblik</a><a href="#datakvalitet">Datakvalitet</a><a href="#arkiv">Arkiv</a>'
      '<a href="#handelschart">Handelschart</a><a href="#aktivitet">Aktivitet</a><a href="#forskning">Forskning</a>'
      '<a href="#kirkegaard-fold">Kirkegård</a><a href="#kilder">Kilder</a></nav>')

    # --- 2. Overblik: only current (FRESH) paper data ---
    w(f'<section class="ov" id="overblik"><h2>Overblik — aktuelle papirdata <small>kun FRESH-konti (mærke højst '
      f'{th} t gammelt ved cutoff) · {n_acc} papirkonti i alt; forældede konti ligger i arkivet</small></h2>')
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
        w(f'<div class="top"><h3>FRESH-konti netto</h3><div class="big {tone(nf)}" id="fresh-net">{e(money(nf))}</div>'
          f'<div class="sub">{sm["fresh"]} af {n_acc} konti; mærke højst {th} t gammelt ved cutoff · kun FRESH, '
          f'ikke en porteføljeværdi</div></div>')
    else:
        w(f'<div class="top na"><h3>FRESH-konti netto</h3><div class="big" id="fresh-net">Ikke tilgængelig</div>'
          f'<div class="sub">0 af {n_acc} konti FRESH</div></div>')
    w(f'<div class="top"><h3>Datadækning</h3><div class="kn">{sm["fresh"]}<small> / {n_acc} konti FRESH</small></div>'
      f'<div class="sub">{len(old)} STALE og {len(nomark)} MISSING_MARK i arkivet nedenfor; '
      f'{"ingen" if not (old or nomark) else "ingen af dem"} indgår i tallene her</div></div>')
    w("</section>")
    w('<section class="grid">')
    if not accs:
        w('<div class="empty">Ingen papirkonti fundet (ingen lane.started-hændelser).</div>')
    elif not fresh:
        w('<div class="empty">Ingen FRESH-konti ved cutoff. Sidst kendte tal står i arkivet og er ikke aktuelle.</div>')
    for a in fresh:
        w(bot_card(a, names[a["ledger"]], conspark, quality, cutoff))
    w("</section>")
    w('<section class="howto" id="howto"><h3>Sådan læses tallene</h3><ul>'
      '<li><b>Netto</b> = seneste equity-mærke minus startkapital, det seneste timemærke på eller før cutoff.</li>'
      f'<li><b>FRESH</b> = mærket er højst {th} t gammelt ved cutoff. Det handler kun om dataens alder og '
      '<b>siger intet om strategiens kvalitet</b>.</li>'
      '<li><b>STALE</b> = mærket er ældre; tallet er den sidst kendte værdi og ikke aktuelt. '
      '<b>MISSING_MARK</b> = intet mærke før cutoff.</li>'
      '<li>Funding, gebyrer og fyld kan ligge senere end mærket.</li>'
      '<li>Papir-P&amp;L uden gearing og uden marginmodel.</li></ul></section>')
    w("</section>")

    # --- 2b. Datakvalitet (V4): one place for everything that says how far the numbers can be trusted ---
    mark_cls = "bad" if sm["missing_mark"] else ("warn" if sm["stale"] else "")
    mark_dot = "d-m" if sm["missing_mark"] else ("d-s" if sm["stale"] else "d-f")
    w('<section class="dqp" id="datakvalitet"><h2>Datakvalitet <small>hvor meget tallene kan bære</small></h2>'
      '<div class="dq-grid">'
      f'<div class="dqc {mark_cls}" id="h-marks"><i class="{mark_dot}"></i><b>Mærker</b><span>{sm["fresh"]} af {n_acc} '
      f'konti friske · {sm["stale"]} forældede · {sm["missing_mark"]} uden mærke</span></div>'
      f'<div class="dqc" id="h-db"><i class="{db_dot}"></i><b>Database</b><span>{e(db_txt)}</span></div>'
      f'<div class="dqc" id="h-qc"><i class="{qc_dot}"></i><b>Integritet</b><span>{e(qc_txt)}</span></div>'
      f'<div class="dqc" id="h-rec"><i class="{rec_dot}"></i><b>Afstemning</b><span>{e(rec_txt)}</span></div>'
      f'<div class="dqc bad" id="h-pmlp"><i class="d-m"></i><b>pm_lp (statisk note pr. {PMLP_NOTE_AS_OF})</b>'
      f'<span>{e(PMLP_NOTE)} Kilde: {e(PMLP_NOTE_SRC)}</span></div></div></section>')

    # --- 3. Arkiv — forældede konti (collapsed) ---
    w('<div class="hist-mark" aria-hidden="true">Historik og analyse</div>')
    ns = sm["net_stale_last_known"]
    w('<details class="fold arch" id="arkiv"><summary><span class="sum-t">Arkiv — forældede konti</span>'
      f'<span class="sum-s">{len(old)} STALE · {len(nomark)} MISSING_MARK · '
      + (f'sidst kendt netto {e(money(ns))} (sidst kendt, ikke aktuel)' if old else "ingen sidst kendte tal")
      + '</span></summary><div class="fold-in">')
    if old or nomark:
        if any(a["source"] in SPOT_SOURCES for a in old):
            w(f'<div class="why" id="stale-why"><p><b>Hvorfor forældet (statisk note pr. {STALE_NOTE_AS_OF}):</b> '
              f'{e(STALE_NOTE)}</p><div class="rs-src">Kilde: ' + " · ".join(e(x) for x in STALE_NOTE_SRC)
              + "</div></div>")
        if old:
            w(f'<div class="top stale"><h3>Sidst kendt netto, STALE-konti</h3><div class="big old">{e(money(ns))}</div>'
              f'<div class="sub"><b>Ikke aktuel</b>: {sm["stale"]} konti med mærke ældre end {th} t · '
              f'sidst kendt, ikke aktuel</div></div>')
            w('<section class="grid arch-grid" aria-label="STALE-konti">'
              + "".join(bot_card(a, names[a["ledger"]], conspark, quality, cutoff) for a in old) + "</section>")
        if nomark:
            w(f'<h3 class="ah3">Uden mærke (MISSING_MARK) · {len(nomark)}</h3>')
            w('<section class="grid arch-grid" aria-label="MISSING_MARK-konti">'
              + "".join(bot_card(a, names[a["ledger"]], conspark, quality, cutoff) for a in nomark) + "</section>")
    else:
        w('<div class="empty">Ingen forældede konti ved cutoff.</div>')
    w("</div></details>")

    # --- 4. HANDELSCHART (59-K): read-only trade charts of the FRESH books ---
    if hc[2]:
        w(hc[2])

    # --- 5. Aktivitet: filters + feed (fills and skips separated) ---
    shown = len(frows)
    allr = totals["fills"] + totals["events"]
    w('<section class="act" id="aktivitet">')
    w(f'<h2>Aktivitet <small>· {shown} nyeste af {allr} registrerede hændelser til cutoff '
      f'({totals["fills"]} fyld, {totals["events"]} overspring/afvisninger/fejl); maks. {feed_n} vises</small></h2>')
    w('<div class="filters" aria-label="filtre">')
    w('<div class="frow"><b>Bot</b><label class="pill" for="fb-all">Alle</label>'
      + "".join(f'<label class="pill" for="fb-{ident(a["ledger"])}">{e(names[a["ledger"]])}</label>' for a in accs)
      + "</div>")
    w('<div class="frow"><b>Periode</b><label class="pill" for="fp-all">Alt</label>'
      '<label class="pill" for="fp-24">24 t</label><label class="pill" for="fp-7">7 d</label>'
      '<span class="sub">(relativt til cutoff)</span></div>')
    w('<div class="frow"><b>Status</b><label class="pill" for="fs-all">Alle</label>'
      '<label class="pill" for="fs-FRESH">FRESH</label><label class="pill" for="fs-STALE">STALE</label>'
      '<label class="pill" for="fs-MISSING_MARK">MISSING_MARK</label>'
      '<span class="sub">filtrene virker på feedet; "Alt" dækker kun de viste rækker</span></div>')
    w("</div>")
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
                    f'<span class="why-t">{e(r["kind"])}: {e(r["reason"][:240])}</span>')
        rowhtml["fill" if r["kind"] == "fill" else "other"].append(
            f'<div class="{" ".join(cls)}" data-kind="{e(r["kind"])}"><span class="t">{e(utc(r["ts"]))}</span>'
            f'<span class="who">{e(who)}</span><span class="sym">{e(r["instrument"])}</span><span>{what}</span></div>')
    if frows:
        for key, tag, title, total, none in (
                ("fill", "t-fill", "Udførte papirhandler", totals["fills"],
                 "Ingen udførte papirhandler blandt de viste."),
                ("other", "t-skip", "Spring over / afvisninger / fejl", totals["events"],
                 "Ingen overspring, afvisninger eller fejl blandt de viste.")):
            rs_ = rowhtml[key]
            w(f'<h3 class="fh" id="feed-{key}"><span class="tag {tag}">{e(title)}</span><small>{len(rs_)} viste af '
              f'{total} til cutoff</small></h3>')
            w(f'<div class="feedbox fb-{key}">' + ("\n".join(rs_) if rs_ else f'<div class="empty">{e(none)}</div>')
              + "</div>")
    w("</section></section>")

    # --- 6. FORSKNINGSOVERSIGT (69): research status read from repo files ---
    if rs[1]:
        w(rs[1])

    # --- 7. STRATEGIKIRKEGÅRD (60-D): every registered attempt, collapsed by default ---
    if gy[2]:
        m = re.search(r'<div class="gv-num">([^<]+)<small> forsøg</small>', gy[2])
        w('<details class="fold" id="kirkegaard-fold"><summary><span class="sum-t">Strategikirkegård</span>'
          '<span class="sum-s">alle registrerede forsøg fra fabriksregistret'
          + (f" · {e(m.group(1))} forsøg" if m else "") + " · kun visning · fold ud</span></summary>"
          '<div class="fold-in">' + gy[2] + "</div></details>")

    # --- 8. footer: sources, read-only statement, disclaimer ---
    w("<footer>")
    w('<p id="kilder"><b>Kilder</b> (alle kun læst):</p><ul>'
      f"<li><b>Datakilde:</b> {e(db_path)} (mode=ro, PRAGMA query_only=ON). Tal pr. konto og summen fra research/tools/net_report.build;"
      " feed fra sim_fills og events (" + ", ".join(SKIP_KINDS) + ").</li>"
      "<li>Handelschart: sim_fills, observations (metric=mark), sim_funding.price og net_report open_basis "
      "(research/tools/paper_chart.py).</li>"
      f"<li>Sundhed: lab_qc.SCHEMA_TABLES (let skematjek), {e(LAB_QC_DOC)}, {e(RECONCILE_GLOB)}.</li>"
      f"<li>Forskningsoversigt: {e(paper_research.MATRIX)} (research/tools/paper_research.py).</li>"
      "<li>Strategikirkegård: research/data/factory (research/tools/paper_graveyard.py).</li>"
      f"<li>STALE-note: statisk tekst i research/tools/paper_dashboard.py pr. {STALE_NOTE_AS_OF} "
      "(" + ", ".join(e(x) for x in STALE_NOTE_SRC) + ").</li></ul>")
    w(f"<p><b>Genereret:</b> {e(utc(now))} · <b>Cutoff:</b> {e(utc(cutoff))} · STALE-tærskel {th} t</p>")
    w("<p><b>Kun læsning:</b> siden skriver intet, starter intet og har ingen JavaScript, knapper, formularer, "
      "ordrer, konti eller wallets.</p>")
    w("<p><b>Ansvarsfraskrivelse:</b> Beskrivende papir-P&amp;L uden gearing og uden marginmodel (ubegrænset "
      "sikkerhedsstillelse for korte perp-ben). Ikke en verificeret eksekverbar strategi. "
      f"{e(paper_research.NO_VALIDATED)}. Ikke investeringsrådgivning. Live-handel: <b>NO-GO</b>. Ingen knapper, "
      "ingen ordrer, ingen konti eller wallets.</p>")
    w("<p>Lokal prototype (direktørordre 59-H P2, 59-J, 59-K Handelschart, 60-D Strategikirkegård, 63, 69 V3). "
      "Produktionsdeploy: NO-GO indtil direktørgennemgang.</p>")
    w("</footer></div></body></html>")
    return "\n".join(out) + "\n"


def render(con, now, cutoff, db_path=DB, feed_n=200, factory_dir=paper_graveyard.FACTORY, root=HERE):
    rep = net_report.build(con, int(now), int(cutoff))
    leds = [a["ledger"] for a in rep["accounts"]]
    frows, totals = feed(con, leds, int(cutoff), int(feed_n))
    return page(rep, frows, totals, db_path, feed_n,
                lambda led, cap, cls: spark(con, led, int(cutoff), cap, cls),
                lambda names: paper_chart.section(con, rep, int(cutoff), names, SKIP_KINDS),
                lambda: paper_graveyard.section(factory_dir),
                lambda: paper_research.section(root, int(cutoff)),
                mark_quality(con, leds, int(cutoff)), health(con, root))


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
