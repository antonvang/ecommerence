"""COPYBOT EVENT FARM dashboard: one static, self-contained HTML page of the event farm (research/tools/event_farm.py)
run on SYNTHETIC DATA ONLY (the engine's own random walk and null run, seed 83 by default).

    python3 research/tools/farm_dashboard.py [--out ~/copybot_farm.html] [--seed 83] [--days 60] [--instruments 3]

Our own design in the dark style of research/tools/paper_dashboard.py (same CSS tokens). Four tabs (OVERBLIK, CHART,
STUDIER, HÆNDELSER) and every toggle work without JavaScript: hidden radio/checkbox inputs plus `:checked ~`
selectors. No <script>, no external resource, no network, no cache, no database, no market data. `--out` is the only
file written (atomically: temp file in the same folder, fsync, rename). The output is deterministic for a seed: no
clock time is printed. Real charts need G01 (14/11), G15/D5 and the director's approval; until then
`build(source=...)` refuses anything but "synthetic".
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402

DEFAULT_OUT = "~/copybot_farm.html"
BACK = "file:///home/anton/copybot_dashboard.html"
BANNER = ("SYNTETISKE DATA — ingen markedsdata; rigtige charts kræver G01 (14/11), G15/D5 og direktørens "
          "godkendelse")
SOURCE = "synthetic"
CHART_DAYS = 4
EVENT_ROWS_PER_KIND = 15

# layer -> (label, colour, kinds, on by default). Every kind of ef.kinds() has exactly one layer.
LAYERS = collections.OrderedDict([
    ("swings", ("Swings (fraktal)", "#8b95a7", ("swing_high", "swing_low"), False)),
    ("pools", ("Likviditetspuljer", "#f2b33d", ("liquidity_pool_high", "liquidity_pool_low"), True)),
    ("sweeps", ("Sweeps", "#d17bff", ("sweep_high", "sweep_low"), True)),
    ("structure", ("MSS / BOS", "#4aa3f0", ("mss_bull", "mss_bear", "bos_bull", "bos_bear"), True)),
    ("fvg", ("FVG / iFVG", "#2dd4bf", ("fvg_bull", "fvg_bear", "ifvg_bull", "ifvg_bear"), True)),
    ("ob", ("Order blocks", "#6d7cff", ("ob_bull", "ob_bear"), True)),
    ("disp", ("Displacement", "#e7ebf2", ("displacement_bull", "displacement_bear"), False)),
    ("sessions", ("Session opens", "#a9b4c7", ("session_open_asia", "session_open_london", "session_open_ny"), True)),
    ("rej", ("Rejections", "#ff9f43", ("rejection_high", "rejection_low"), False)),
    ("setups", ("Setups (indgang / mål / stop)", "#16c784", ("setup_long", "setup_short"), True)),
])
LAYER_OF = {k: name for name, (_, _, ks, _) in LAYERS.items() for k in ks}

# kind -> the definition entry in event_farm's docstring (the text after "- " up to the first ":")
DEF_KEY = {"swing": "swing_high (fractal k)", "liquidity_pool": "liquidity level", "sweep": "sweep_high",
           "bos": "structure", "mss": "structure", "displacement": "displacement_bull/bear", "ob": "ob_bull",
           "fvg": "fvg_bull", "ifvg": "fvg_bull", "session_open": "session_open_<name>", "rejection": "rejection_high",
           "setup": "setup (chain)"}


def e(s):
    return html.escape(str(s), quote=True)


def hm(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%H:%M")


def dhm(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def px(x):
    return f"{x:,.2f}".replace(",", " ")


def num(x, d=1):
    return f"{x:.{d}f}"


def definitions():
    """{docstring key: text} parsed from event_farm's DEFINITIONS block (the engine's own wording)."""
    doc = ef.__doc__ or ""
    block = doc.split("DEFINITIONS", 1)[1] if "DEFINITIONS" in doc else ""
    out, cur = {}, None
    for line in block.splitlines():
        m = re.match(r"^- ([^:]+): (.*)$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = m.group(2).strip()
        elif cur and line.startswith("  "):
            out[cur] += " " + line.strip()
    return out


def def_for(kind, defs):
    for prefix in sorted(DEF_KEY, key=len, reverse=True):
        if kind.startswith(prefix):
            return DEF_KEY[prefix], defs.get(DEF_KEY[prefix], "")
    return "", ""


def build(seed=83, days=60, instruments=3, source=SOURCE):
    """The engine's null run on its synthetic random walk. Any other source is refused (no market data before G01,
    G15/D5 and the director's approval)."""
    if source != SOURCE:
        raise ValueError(f"kun syntetiske data: kilde {source!r} afvist (kræver G01, G15/D5 og direktørens godkendelse)")
    if not (1 <= days <= 400 and 1 <= instruments <= 10):
        raise ValueError("days must be 1..400 and instruments 1..10")
    s = ef.null_run(seed=seed, instruments=instruments, days=days)
    s["_engine_sha"] = ef.code_sha()
    return s


# ---------------------------------------------------------------- CSS

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
code,.mono{font:12px var(--mono)}
a{color:var(--blu)}
.hdr{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;justify-content:space-between;padding:14px 0 10px;
border-bottom:1px solid var(--line)}
.brand{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center}
.logo{font-weight:800;letter-spacing:.16em;font-size:18px}.logo span{color:var(--amb)}
.tabs{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.tabs label{cursor:pointer;color:var(--mut);font-size:12px;font-weight:700;letter-spacing:.08em;padding:6px 11px;
border-radius:6px;white-space:nowrap}
.tabs label:hover{color:var(--txt);background:var(--panel)}
.back{font-size:12px;color:var(--mut);text-decoration:none;white-space:nowrap}.back:hover{color:var(--txt)}
.syn{margin:12px 0 6px;padding:10px 14px;border-radius:10px;background:var(--amb-bg);border:1px solid rgba(242,179,61,.5);
color:var(--amb);font-weight:800;font-size:14px;letter-spacing:.01em}
.prov{font-size:11px;color:var(--mut);line-height:1.6;overflow-wrap:anywhere}.prov code{color:#b9c3d6;font-size:11px}
.pane{display:none}
h2{font-size:17px;font-weight:700;margin:22px 0 10px;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}
h2 small,.sub{color:var(--mut);font-weight:400;font-size:12px}
h3{font-size:13px;margin:16px 0 8px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.12em;color:var(--amb);text-transform:uppercase;margin-top:18px}
.lead{color:#c3cad6;max-width:820px;margin:4px 0 0}
.tiles{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin:14px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;min-width:0}
.tile b{display:block;font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.2}
.tile span{display:block;font-size:10px;font-weight:700;letter-spacing:.1em;color:var(--mut);text-transform:uppercase}
.tile i{display:block;font-style:normal;font-size:11px;color:var(--mut)}
.box{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0;min-width:0}
.null{border-left:3px solid var(--neg)}
.null b.big{font-size:20px;color:var(--neg)}
.cov{display:grid;gap:3px;margin-top:8px}
.covrow{display:grid;grid-template-columns:44px 1fr;gap:6px;align-items:center;font:11px var(--mono);color:var(--mut)}
.cells{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:2px}
.cell{height:16px;border-radius:2px;background:var(--amb)}
.cell.c0{background:var(--panel2)}
.covax{display:flex;justify-content:space-between;font:10px var(--mono);color:var(--mut);margin-left:50px}
.voc{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.vk{background:var(--panel2);border-radius:8px;padding:9px 11px;font-size:12px;min-width:0}
.vk .vh{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.vk .vh b{font:600 12px var(--mono);overflow-wrap:anywhere}.vk .vh span{color:var(--mut);font:11px var(--mono);white-space:nowrap}
.vk p{margin:5px 0 0;color:#aeb7c6;line-height:1.45}.vk p em{color:var(--mut);font-style:normal;font-size:11px}
.sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:baseline}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:var(--pos)}.neg{color:var(--neg)}.mut{color:var(--mut)}
.pick{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.pick label{cursor:pointer;font:12px var(--mono);padding:4px 10px;border-radius:6px;background:var(--panel);
border:1px solid var(--line);color:var(--mut)}
.chartgrid{display:grid;grid-template-columns:minmax(0,1fr) 270px;gap:12px;align-items:start}
.plotbox{background:var(--plot);border:1px solid var(--line);border-radius:12px;padding:8px;min-width:0}
.plotscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.plotscroll svg{display:block;width:100%;min-width:760px;height:auto}
.side{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.side h3{margin:0 0 6px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
.lyr{display:grid;grid-template-columns:16px 1fr auto;gap:8px;align-items:center;cursor:pointer;padding:6px 6px;
border-radius:6px;font-size:12px}
.lyr:hover{background:var(--panel2)}
.lyr .bx{width:14px;height:14px;border-radius:3px;border:1.5px solid var(--mut)}
.lyr small{display:block;color:var(--mut);font:10px var(--mono);overflow-wrap:anywhere}
.lyr .c{font:12px var(--mono);color:var(--mut)}
.legend{font-size:11px;color:var(--mut);margin-top:8px;line-height:1.5}
.study{display:grid;grid-template-columns:150px minmax(0,1fr);gap:12px;align-items:start}
.dlist{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:6px;max-height:640px;overflow-y:auto}
.dlist label{display:flex;justify-content:space-between;cursor:pointer;font:12px var(--mono);color:var(--mut);
padding:3px 8px;border-radius:5px}
.dlist label:hover{color:var(--txt)}.dlist label i{font-style:normal;color:#5b6577}
.sdp{display:none}
.kgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px}
.chains{list-style:none;margin:0;padding:0;font-size:12px}
.chains li{padding:7px 0;border-bottom:1px solid var(--line);line-height:1.5;overflow-wrap:anywhere}
.chains b{font-family:var(--mono)}
.st{display:inline-block;padding:1px 7px;border-radius:5px;font-size:11px;font-weight:700}
.st-target{background:var(--pos-bg);color:var(--pos)}.st-stop{background:var(--neg-bg);color:var(--neg)}
.st-other{background:var(--panel2);color:var(--mut)}
.efilt{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}
.efilt label{cursor:pointer;font:11px var(--mono);padding:3px 8px;border-radius:5px;background:var(--panel);
border:1px solid var(--line);color:var(--mut)}
.foot{margin-top:28px;padding-top:12px;border-top:1px solid var(--line);font-size:11px;color:var(--mut)}
@media (max-width:1000px){.tiles{grid-template-columns:repeat(3,minmax(0,1fr))}.voc{grid-template-columns:repeat(2,minmax(0,1fr))}
.chartgrid{grid-template-columns:1fr}}
@media (max-width:640px){.wrap{padding:0 12px 32px}.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
.voc{grid-template-columns:1fr}.tile b{font-size:20px}.study{grid-template-columns:1fr}
.dlist{display:flex;max-height:none;overflow-x:auto;overflow-y:hidden;gap:2px}.dlist label{flex:0 0 auto}
.kgrid{grid-template-columns:1fr}.syn{font-size:13px}.tabs label{padding:6px 7px;font-size:11px;letter-spacing:.05em}.covrow{grid-template-columns:34px 1fr}.covax{margin-left:40px}}
"""


def dyn_css(chart_n, day_keys, kinds_shown):
    on = "{color:var(--txt);background:var(--panel2);border-color:var(--amb)}"
    css = []
    for t in ("ov", "ch", "st", "ev"):
        css.append(f"#t-{t}:checked~.wrap .p-{t}{{display:block}}"
                   f"#t-{t}:checked~.wrap label[for=t-{t}]{{color:var(--amb);background:var(--panel)}}")
    for n in range(chart_n):
        css.append(f"#cd-{n}:checked~.wrap .dv:not(.dv-{n}){{display:none}}#cd-{n}:checked~.wrap label[for=cd-{n}]{on}")
    for name, (_, col, _, _) in LAYERS.items():
        css.append(f"#ly-{name}:not(:checked)~.wrap .ly-{name}{{display:none}}"
                   f"#ly-{name}:checked~.wrap label[for=ly-{name}] .bx{{background:{col};border-color:{col}}}"
                   f"#ly-{name}:not(:checked)~.wrap label[for=ly-{name}]{{opacity:.55}}")
    for n, _ in enumerate(day_keys):
        css.append(f"#sd-{n}:checked~.wrap .sdp-{n}{{display:block}}"
                   f"#sd-{n}:checked~.wrap label[for=sd-{n}]{{color:var(--amb);background:var(--panel2)}}")
    css.append(f"#ek-all:checked~.wrap label[for=ek-all]{on}")
    for k in kinds_shown:
        css.append(f"#ek-{k}:checked~.wrap .er:not(.er-{k}){{display:none}}#ek-{k}:checked~.wrap label[for=ek-{k}]{on}")
    return "\n".join(css)


# ---------------------------------------------------------------- OVERBLIK

def overview(s, setups_n, defs):
    st = s["_study"]
    days = st["days"]
    n_days, n_inst = s["days"], s["instruments"]
    out = ['<div class="eyebrow">Observationskorpus · beskrivende, ingen strategi</div>',
           '<h2>Hvad farmen mærker</h2>',
           '<p class="lead">Hver dag af syntetisk 5-minutters støj køres bar for bar gennem den frosne motor '
           '<code>event_farm.py</code>: likviditetspuljer dannes og sweepes, strukturen skifter, gaps og order blocks '
           'opstår, og hver regelbaseret kæde får en indgang, et mål og et stop, når den kan kendes. Udfaldsbogen '
           'skriver, hvad der fulgte. Ingen fremtidige barer bruges.</p>']
    tiles = [(n_days, "dage", "syntetisk kalender"), (n_inst, "instrumenter", ", ".join(st["instruments"])),
             (f"{s['bars']:,}".replace(",", " "), "barer", "5m, random walk"),
             (f"{s['events']:,}".replace(",", " "), "hændelser", f"{len(ef.BASE_KINDS) + 3} typer"),
             (f"{setups_n:,}".replace(",", " "), "setups", "standardparametre"),
             (num(s["events_per_instrument_day"]), "pr. instr.-dag", "hændelser")]
    out.append('<div class="tiles">' + "".join(
        f'<div class="tile"><span>{e(lbl)}</span><b>{e(v)}</b><i>{e(sub)}</i></div>' for v, lbl, sub in tiles) + "</div>")
    # null result
    costs = [f"{c:g}" for c in s["costs"]]
    main_cost = f"{ef.DEFAULTS['cost_bps']:g}"
    vs = s["variants"]
    pos = sum(1 for v in vs.values() if v["net"][main_cost]["mean_net_r"] is not None
              and v["net"][main_cost]["mean_net_r"] > 0)
    gpos = sum(1 for v in vs.values() if v["mean_gross_r"] is not None and v["mean_gross_r"] > 0)
    rows = []
    for vid, v in vs.items():
        cells = []
        for c in costs:
            m = v["net"][c]["mean_net_r"]
            cells.append('<td class="n mut">n/a</td>' if m is None else
                         f'<td class="n {"pos" if m > 0 else "neg"}">{m:+.3f}</td>')
        g = "n/a" if v["mean_gross_r"] is None else f"{v['mean_gross_r']:+.3f}"
        t = "n/a" if v["t_gross"] is None else f"{v['t_gross']:+.2f}"
        rows.append(f"<tr><td class=mono>{e(vid)}</td><td class=n>{v['trades']}</td><td class=n>{v['hit_rate']:.2f}</td>"
                    f"<td class=n>{g}</td><td class=n>{t}</td>{''.join(cells)}</tr>")
    out.append(
        '<div class="box null"><h2 style="margin-top:0">Udfaldsbogen på ren støj '
        f'<small>null-kørsel, seed {s["seed"]}, {s["pooled_trades"]} handler over {len(vs)} varianter</small></h2>'
        f'<p><b class="big">{pos} af {len(vs)} varianter positive</b> netto efter {main_cost} bps rundtur '
        f'({gpos} af {len(vs)} positive brutto). Puljet brutto R pr. handel: {s["pooled_mean_gross_r"]:+.4f}.</p>'
        '<p class="lead"><b>Mønstrene findes i ren støj.</b> Denne serie er en driftløs tilfældig gang uden nogen '
        f'information, og alligevel mærker motoren {num(s["events_per_instrument_day"])} hændelser og '
        f'{num(setups_n / max(1, n_days * n_inst), 2)} setups pr. instrument-dag. At et sweep, et MSS eller en FVG '
        'optræder, er derfor ikke i sig selv en kant; kun en låst test på rigtige data efter gates kan vise noget.</p>'
        '<div class="tw"><table><thead><tr><th>variant</th><th class=n>handler</th><th class=n>mål-andel</th>'
        '<th class=n>brutto R</th><th class=n>t</th>'
        + "".join(f"<th class=n>netto R @{c} bps</th>" for c in costs) + "</tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></div></div>")
    # coverage stripe
    keys = sorted(days)
    rows = []
    for inst in st["instruments"]:
        cells = "".join(
            f'<div class="cell{"" if days[d]["coverage"][inst] > 0 else " c0"}" '
            f'style="opacity:{0.25 + 0.75 * days[d]["coverage"][inst]:.2f}" '
            f'title="{e(d)} {e(inst)}: dækning {100 * days[d]["coverage"][inst]:.0f} %"></div>' for d in keys)
        rows.append(f'<div class="covrow"><span>{e(inst)}</span><div class="cells">{cells}</div></div>')
    ev_cells = []
    mx = max([sum(days[d]["kinds"].values()) for d in keys] or [1])
    for d in keys:
        n = sum(days[d]["kinds"].values())
        ev_cells.append(f'<div class="cell" style="background:var(--acc);opacity:{0.2 + 0.8 * n / max(1, mx):.2f}" '
                        f'title="{e(d)}: {n} hændelser"></div>')
    rows.append(f'<div class="covrow"><span>hænd.</span><div class="cells">{"".join(ev_cells)}</div></div>')
    out.append(f'<div class="box"><h2 style="margin-top:0">Dækning <small>{len(keys)} dage × {n_inst} instrumenter; '
               'farve = andel af dagens 288 barer, nederste række = hændelser pr. dag</small></h2>'
               f'<div class="cov">{"".join(rows)}</div>'
               f'<div class="covax"><span>{e(keys[0] if keys else "")}</span><span>{e(keys[-1] if keys else "")}</span></div></div>')
    # vocabulary
    total = collections.Counter()
    for d in days.values():
        total.update(d["kinds"])
    cards = []
    for k in ef.kinds():
        key, text = def_for(k, defs)
        col = LAYERS[LAYER_OF[k]][1]
        cards.append(f'<div class="vk"><div class="vh"><b><i class="sw" style="background:{col}"></i>{e(k)}</b>'
                     f'<span>{total.get(k, 0)}</span></div><p>{e(text)}<br><em>motor: “{e(key)}”</em></p></div>')
    for k in ef.NOT_DEFINED:
        cards.append(f'<div class="vk"><div class="vh"><b class="mut">{e(k)}</b><span>ikke talt</span></div>'
                     '<p>I videoens ordforråd, men motoren påstår ingen præcis regel; derfor mærkes typen ikke.</p></div>')
    pp = ", ".join(f"{k}={v}" for k, v in sorted(ef.DEFAULTS.items()) if k != "sessions")
    out.append('<div class="box"><h2 style="margin-top:0">Det sporede ordforråd <small>præcise definitioner fra '
               'motorens docstring; tallet er antal i hele korpuset</small></h2>'
               f'<div class="voc">{"".join(cards)}</div><p class="prov">parametre: <code>{e(pp)}</code></p></div>')
    return "\n".join(out)


# ---------------------------------------------------------------- CHART

def chart_picks(s, n=CHART_DAYS):
    """Up to n (instrument, day) pairs, instruments in turn; per instrument the day (not the first, ATR warm-up) with
    the most decided setups (target or stop), ties to the earlier day. Deterministic for a seed."""
    keys = s["day_keys"]
    insts = sorted(s["_bars"])
    bs = ef.params()["bar_seconds"]
    picks = []
    for k in range(n):
        inst = insts[k % len(insts)]
        r = s["_results"][inst]
        score = collections.Counter(ef.known_day(su, bs) for su, o in zip(r["setups"], r["setup_outcomes"])
                                    if o["status"] in ("target", "stop"))
        cand = [d for d in (keys[1:] or keys) if (inst, d) not in picks]
        if cand:
            picks.append((inst, max(cand, key=lambda d: (score[d], -keys.index(d)))))
    return picks


def day_range(bars, day):
    idx = [i for i, b in enumerate(bars) if ef._day(b[0]) == day]
    return idx[0], idx[-1] + 1


def tip(ev, extra=""):
    t = f"{ev['kind']} · ts {dhm(ev['ts'])} UTC · known_ts {dhm(ev['known_ts'])} UTC"
    return f"<title>{e(t + extra)}</title>"


def chart_svg(inst, bars, res, d0, d1, p):
    W, L, R, T, PH, KS = 1200, 8, 64, 22, 440, 46       # width, left/right pad, top, plot height, known-strip height
    H = T + PH + KS + 22
    n = d1 - d0
    bw = (W - L - R) / n
    day_ev = [ev for ev in res["events"] if d0 <= ev["known_i"] < d1]
    day_su = [(su, o) for su, o in zip(res["setups"], res["setup_outcomes"]) if d0 <= su["known_i"] < d1]
    lo = min(b[3] for b in bars[d0:d1])
    hi = max(b[2] for b in bars[d0:d1])
    for su, _ in day_su:
        lo, hi = min(lo, su["stop"], su["target"]), max(hi, su["stop"], su["target"])
    pad = (hi - lo) * 0.04 or 1.0
    lo, hi = lo - pad, hi + pad

    def X(i):
        return L + (min(max(i, d0), d1 - 1) - d0) * bw + bw / 2

    def Y(v):
        return T + (hi - v) / (hi - lo) * PH

    def f(v):
        return f"{v:.1f}"

    g = collections.OrderedDict((name, []) for name in LAYERS)
    counts = collections.Counter()
    ky = T + PH + 10                                      # known-strip baseline
    lane = {name: k for k, name in enumerate(LAYERS)}

    def known_mark(layer, i, ki, col):
        y = ky + 3 * lane[layer]
        return (f'<line x1="{f(X(i))}" y1="{f(y)}" x2="{f(X(ki))}" y2="{f(y)}" stroke="{col}" stroke-width="1" '
                f'stroke-opacity=".6"/><path d="M{f(X(ki))} {f(y - 2.5)}l2.5 2.5-2.5 2.5-2.5-2.5z" fill="{col}"/>')

    for ev in day_ev:
        k, layer = ev["kind"], LAYER_OF[ev["kind"]]
        col = LAYERS[layer][1]
        counts[layer] += 1
        i, ki = ev["i"], ev["known_i"]
        t = tip(ev)
        if layer == "swings":
            shp = f'<circle cx="{f(X(i))}" cy="{f(Y(ev["level"]))}" r="2.2" fill="{col}">{t}</circle>'
        elif layer == "pools":
            x0 = X(ev["members_i"][0])
            shp = (f'<g>{t}<line x1="{f(x0)}" y1="{f(Y(ev["level"]))}" x2="{f(X(ki + 36))}" y2="{f(Y(ev["level"]))}" '
                   f'stroke="{col}" stroke-width="1.4" stroke-dasharray="5 3"/>'
                   + "".join(f'<circle cx="{f(X(m))}" cy="{f(Y(ev["level"]))}" r="2.6" fill="none" stroke="{col}"/>'
                             for m in ev["members_i"]) + "</g>")
        elif layer == "sweeps":
            up = k == "sweep_high"
            x, y = X(ev["pierce_i"]), Y(ev["extreme"])
            tri = f"M{f(x)} {f(y - 9)}l-4.5 -7h9z" if up else f"M{f(x)} {f(y + 9)}l-4.5 7h9z"
            shp = (f'<g>{t}<line x1="{f(X(i - 8))}" y1="{f(Y(ev["level"]))}" x2="{f(x + 4)}" y2="{f(Y(ev["level"]))}" '
                   f'stroke="{col}" stroke-width="1.2"/><path d="{tri}" fill="{col}"/></g>')
        elif layer == "structure":
            lbl = ("MSS" if k.startswith("mss") else "BOS") + ("↑" if ev["dir"] > 0 else "↓")
            yl = Y(ev["level"])
            dash = "" if k.startswith("mss") else ' stroke-dasharray="2 2"'
            shp = (f'<g>{t}<line x1="{f(X(ev["swing_i"]))}" y1="{f(yl)}" x2="{f(X(i))}" y2="{f(yl)}" stroke="{col}" '
                   f'stroke-width="{1.6 if k.startswith("mss") else 1}"{dash}/>'
                   f'<text x="{f(X(i) + 3)}" y="{f(yl - 3)}" fill="{col}" font-size="9" font-family="monospace">{lbl}</text></g>')
        elif layer == "fvg":
            if k.startswith("ifvg"):
                x0, x1 = X(ev["fvg_known_i"]), X(ki)
                dash = ' stroke-dasharray="3 2"'
                fill = "none"
            else:
                x0, x1 = X(i - 1), X(ki + 12)
                dash, fill = "", col
            shp = (f'<rect x="{f(x0)}" y="{f(Y(ev["zone_hi"]))}" width="{f(max(2, x1 - x0))}" '
                   f'height="{f(max(1, Y(ev["zone_lo"]) - Y(ev["zone_hi"])))}" fill="{fill}" fill-opacity=".16" '
                   f'stroke="{col}" stroke-opacity=".7" stroke-width=".8"{dash}>{t}</rect>')
        elif layer == "ob":
            x0, x1 = X(i) - bw / 2, X(ev["displacement_i"] + 12)
            shp = (f'<rect x="{f(x0)}" y="{f(Y(ev["zone_hi"]))}" width="{f(max(2, x1 - x0))}" '
                   f'height="{f(max(1, Y(ev["zone_lo"]) - Y(ev["zone_hi"])))}" fill="{col}" fill-opacity=".14" '
                   f'stroke="{col}" stroke-width=".9">{t}</rect>')
        elif layer == "disp":
            b = bars[i]
            shp = (f'<rect x="{f(X(i) - bw / 2 - 1)}" y="{f(Y(b[2]) - 2)}" width="{f(bw + 2)}" '
                   f'height="{f(Y(b[3]) - Y(b[2]) + 4)}" fill="none" stroke="{col}" stroke-width=".9" '
                   f'stroke-opacity=".8">{t}</rect>')
        elif layer == "sessions":
            name = k.replace("session_open_", "")
            shp = (f'<g>{t}<line x1="{f(X(i))}" y1="{T}" x2="{f(X(i))}" y2="{T + PH}" stroke="{col}" '
                   f'stroke-dasharray="1 4" stroke-width="1"/><text x="{f(X(i) + 3)}" y="{T + 10}" fill="{col}" '
                   f'font-size="10" font-family="monospace">{e(name)} {f(ev["level"])}</text></g>')
        else:                                             # rejections
            b = bars[i]
            y = Y(b[2]) if k == "rejection_high" else Y(b[3])
            shp = f'<circle cx="{f(X(i))}" cy="{f(y)}" r="3.4" fill="none" stroke="{col}" stroke-width="1.2">{t}</circle>'
        g[layer].append(shp + known_mark(layer, i, ki, col))
    for su, o in day_su:
        counts["setups"] += 1
        d = su["dir"]
        ki = su["known_i"]
        end = o["exit_i"] if o["exit_i"] is not None else ki + p["max_hold"]
        x0, x1 = X(ki), X(end) + bw / 2
        ye, yt, ys = Y(su["entry"]), Y(su["target"]), Y(su["stop"])
        res_txt = f" · udfald {o['status']}" + ("" if o["net_r"] is None else f" · netto {o['net_r']:+.2f} R")
        t = tip(su, f" · {su['chain']} · indgang {px(su['entry'])} · mål {px(su['target'])} · stop {px(su['stop'])}{res_txt}")
        lab = ("LONG" if d > 0 else "SHORT") + f" {o['status']}"
        g["setups"].append(
            f'<g>{t}<rect x="{f(x0)}" y="{f(min(ye, yt))}" width="{f(max(3, x1 - x0))}" height="{f(abs(yt - ye))}" '
            f'fill="#16c784" fill-opacity=".16" stroke="#16c784" stroke-width=".8"/>'
            f'<rect x="{f(x0)}" y="{f(min(ye, ys))}" width="{f(max(3, x1 - x0))}" height="{f(abs(ys - ye))}" '
            f'fill="#ff4d5e" fill-opacity=".16" stroke="#ff4d5e" stroke-width=".8"/>'
            f'<line x1="{f(x0)}" y1="{f(ye)}" x2="{f(x1)}" y2="{f(ye)}" stroke="#e7ebf2" stroke-width="1"/>'
            f'<line x1="{f(X(su["i"]))}" y1="{f(ys)}" x2="{f(x0)}" y2="{f(ye)}" stroke="#16c784" stroke-width=".8" '
            f'stroke-dasharray="2 3" stroke-opacity=".7"/>'
            f'<text x="{f(x0 + 2)}" y="{f((yt - 4) if d > 0 else (yt + 11))}" fill="#16c784" font-size="10" '
            f'font-family="monospace" font-weight="700">{e(lab)}</text></g>'
            + known_mark("setups", su["i"], ki, "#16c784"))
    # axes and candles
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{e(inst)} 5m syntetisk">',
             f'<rect x="0" y="0" width="{W}" height="{H}" fill="#0e131d"/>']
    for q in range(6):
        v = lo + (hi - lo) * q / 5
        y = Y(v)
        parts.append(f'<line x1="{L}" y1="{f(y)}" x2="{W - R}" y2="{f(y)}" stroke="#232b3b" stroke-width=".6"/>'
                     f'<text x="{W - R + 6}" y="{f(y + 3)}" fill="#8b95a7" font-size="10" font-family="monospace">{f(v)}</text>')
    for j in range(d0, d1, 24):
        x = X(j)
        parts.append(f'<line x1="{f(x)}" y1="{T}" x2="{f(x)}" y2="{T + PH + KS}" stroke="#1a2130" stroke-width=".6"/>'
                     f'<text x="{f(x)}" y="{H - 6}" fill="#8b95a7" font-size="10" font-family="monospace" '
                     f'text-anchor="middle">{hm(bars[j][0])}</text>')
    parts.append(f'<text x="{L}" y="13" fill="#8b95a7" font-size="10" font-family="monospace">{e(inst)} · 5m · '
                 f'{e(ef._day(bars[d0][0]))} UTC · SYNTETISK</text>'
                 f'<line x1="{L}" y1="{T + PH + 4}" x2="{W - R}" y2="{T + PH + 4}" stroke="#232b3b"/>'
                 f'<text x="{W - R + 6}" y="{ky + 12}" fill="#8b95a7" font-size="9" font-family="monospace">kendt</text>'
                 f'<text x="{W - R + 6}" y="{ky + 23}" fill="#8b95a7" font-size="9" font-family="monospace">ved ◆</text>')
    cw = max(1.0, bw * 0.62)
    candles = []
    for j in range(d0, d1):
        _, o, h, l, c, _ = bars[j]
        col = "#16c784" if c >= o else "#ff4d5e"
        x = X(j)
        candles.append(f'<line x1="{f(x)}" y1="{f(Y(h))}" x2="{f(x)}" y2="{f(Y(l))}" stroke="{col}" stroke-width=".8"/>'
                       f'<rect x="{f(x - cw / 2)}" y="{f(Y(max(o, c)))}" width="{f(cw)}" '
                       f'height="{f(max(.8, abs(Y(o) - Y(c))))}" fill="{col}"/>')
    parts.append('<g class="candles">' + "".join(candles) + "</g>")
    for name, items in g.items():
        parts.append(f'<g class="ly-{name}">' + "".join(items) + "</g>")
    parts.append("</svg>")
    return "".join(parts), counts


def chart_tab(s, picks, p):
    out = ['<h2>Chart <small>5m lys, syntetiske dage; slå lag til og fra i panelet; hold musen over en figur for '
           'kind, ts og known_ts</small></h2>', '<div class="pick">']
    for n, (inst, day) in enumerate(picks):
        out.append(f'<label for="cd-{n}">{e(inst)} · {e(day)}</label>')
    out.append("</div>")
    svgs, cnts = [], []
    for n, (inst, day) in enumerate(picks):
        bars = s["_bars"][inst]
        d0, d1 = day_range(bars, day)
        svg, c = chart_svg(inst, bars, s["_results"][inst], d0, d1, p)
        svgs.append(f'<div class="dv dv-{n}">{svg}</div>')
        cnts.append(c)
    side = ['<div class="side"><h3>Lag</h3>']
    for name, (label, col, ks, _) in LAYERS.items():
        cs = "".join(f'<span class="dv dv-{n}">{cnts[n][name]}</span>' for n in range(len(picks)))
        side.append(f'<label class="lyr" for="ly-{name}"><span class="bx"></span><span>{e(label)}'
                    f'<small>{e(" ".join(ks))}</small></span><span class="c">{cs}</span></label>')
    side.append('<div class="legend">◆ i båndet under lysene = <b>known_ts</b>: baren hvor mønstret først kunne '
                'kendes; stregen går tilbage til hvor det ligger (ts). Et mønster tegnes ved ts, men ingen regel må '
                'bruge det før ◆. Setups: grøn = indgang→mål, rød = indgang→stop, fra known_ts til udgang.</div></div>')
    out.append(f'<div class="chartgrid"><div class="plotbox"><div class="plotscroll">{"".join(svgs)}</div></div>'
               f'{"".join(side)}</div>')
    return "\n".join(out)


# ---------------------------------------------------------------- STUDIER

def studies(s, p):
    st = s["_study"]
    keys = sorted(st["days"])
    bs = p["bar_seconds"]
    chains = collections.defaultdict(list)
    for inst in sorted(s["_results"]):
        r, bars = s["_results"][inst], s["_bars"][inst]
        for su, o in zip(r["setups"], r["setup_outcomes"]):
            chains[ef.known_day(su, bs)].append((inst, su, o, bars))
    lst = ['<div class="dlist">']
    for n, d in enumerate(keys):
        dd = st["days"][d]
        ns = sum(v for k, v in dd["kinds"].items() if k.startswith("setup_"))
        lst.append(f'<label for="sd-{n}">{e(d)}<i>{ns}</i></label>')
    lst.append("</div>")
    panes = []
    for n, d in enumerate(keys):
        dd = st["days"][d]
        ks = sorted(dd["kinds"].items())
        half = (len(ks) + 1) // 2
        tabs = []
        for part in (ks[:half], ks[half:]):
            tabs.append('<table><thead><tr><th>type</th><th class=n>n</th></tr></thead><tbody>'
                        + "".join(f'<tr><td class=mono><i class="sw" style="background:{LAYERS[LAYER_OF[k]][1]}"></i>'
                                  f'{e(k)}</td><td class=n>{v}</td></tr>' for k, v in part) + "</tbody></table>")
        cov = " · ".join(f"{e(i)} {100 * c:.0f} %" for i, c in dd["coverage"].items())
        outc = " · ".join(f"{e(k)} {v}" for k, v in dd["outcomes"].items()) or "ingen"
        items = []
        for inst, su, o, bars in sorted(chains.get(d, []), key=lambda x: (x[1]["known_i"], x[0])):
            def kt(i):
                return hm(bars[i][0] + bs)
            side = "long" if su["dir"] > 0 else "short"
            parts = su["chain"].split(">")
            stc = "st-target" if o["status"] == "target" else ("st-stop" if o["status"] == "stop" else "st-other")
            net = "" if o["net_r"] is None else f' netto <b class="{"pos" if o["net_r"] > 0 else "neg"}">{o["net_r"]:+.2f} R</b>'
            items.append(
                f'<li><b>{kt(su["known_i"])} {e(inst)} {side}</b> — {e(parts[0])} @{hm(su["ts"])} (kendt '
                f'{kt(su["sweep_known_i"])}) → {e(parts[1])} (kendt {kt(su["break_known_i"])}) → anker {e(parts[2])} '
                f'(kendt {kt(su["anchor_known_i"])}) → indgang {px(su["entry"])} ({e(su["entry_mode"])}), mål '
                f'{px(su["target"])}, stop {px(su["stop"])} → <span class="st {stc}">{e(o["status"])}</span>{net}</li>')
        panes.append(
            f'<div class="sdp sdp-{n}"><div class="box"><h2 style="margin-top:0">Farm study — {e(d)} '
            f'<small>syntetisk; dækning {cov}</small></h2>'
            f'<p class="sub">Udfald: {outc} · netto R i alt {dd["net_r_sum"]:+.2f} over {dd["trades"]} handler '
            f'(standardparametre: anker {e(p["anchor"])}, indgang {e(p["entry_mode"])}, rr {p["rr"]:g}, '
            f'{p["cost_bps"]:g} bps).</p>'
            f'<div class="kgrid">{"".join(tabs)}</div>'
            f'<h3>Kæder ({len(items)}) <span class="sub">sweep → MSS → anker → setup → udfald; tider = known_ts (UTC)</span></h3>'
            f'<ul class="chains">{"".join(items) or "<li class=mut>ingen kæder denne dag</li>"}</ul></div></div>')
    return ('<h2>Studier <small>én daglig farm study pr. syntetisk dag; vælg dag (tal = setups)</small></h2>'
            f'<div class="study">{"".join(lst)}<div>{"".join(panes)}</div></div>')


# ---------------------------------------------------------------- HÆNDELSER

def events_tab(s, p, per_kind=EVENT_ROWS_PER_KIND):
    inst = sorted(s["_results"])[0]
    r, bars = s["_results"][inst], s["_bars"][inst]
    bs = p["bar_seconds"]
    hz = p["horizons"][-1]
    seen = collections.Counter()
    rows = []
    items = [(ev, oc) for ev, oc in zip(r["events"], r["event_outcomes"])]
    items += [(su, {"ret_atr": {}, "_setup": o}) for su, o in zip(r["setups"], r["setup_outcomes"])]
    items.sort(key=lambda x: (x[0]["known_i"], x[0]["kind"]))
    for ev, oc in items:
        k = ev["kind"]
        if seen[k] >= per_kind:
            continue
        seen[k] += 1
        if "zone_lo" in ev:
            lvl = f"{px(ev['zone_lo'])}–{px(ev['zone_hi'])}"
        elif "entry" in ev:
            lvl = f"ind {px(ev['entry'])} · mål {px(ev['target'])} · stop {px(ev['stop'])}"
        elif "level" in ev:
            lvl = px(ev["level"])
        else:
            lvl = ""
        if "_setup" in oc:
            o = oc["_setup"]
            fw = e(o["status"]) + ("" if o["net_r"] is None else f" {o['net_r']:+.2f} R")
        else:
            v = oc["ret_atr"].get(hz)
            fw = "n/a" if v is None else f"{v:+.2f}"
        lag = (ev["known_ts"] - ev["ts"]) // 60
        rows.append(f'<tr class="er er-{e(k)}"><td class=mono><i class="sw" style="background:{LAYERS[LAYER_OF[k]][1]}">'
                    f'</i>{e(k)}</td><td class=mono>{dhm(ev["ts"])}</td><td class=mono>{dhm(ev["known_ts"])}</td>'
                    f'<td class=n>{lag}</td><td class=n>{ev["dir"]:+d}</td><td class=mono>{lvl}</td>'
                    f'<td class="n mono">{fw}</td></tr>')
    shown = [k for k in ef.kinds() if seen[k]]
    filt = ['<div class="efilt"><label for="ek-all">alle</label>']
    filt += [f'<label for="ek-{k}">{e(k)} {seen[k]}</label>' for k in shown]
    filt.append("</div>")
    html_ = (f'<h2>Hændelser <small>{e(inst)}, de første {per_kind} pr. type i tidsorden ({len(rows)} rækker af '
             f'{len(r["events"]) + len(r["setups"])}); fremad = afkast i ATR {hz} barer efter known_ts '
             f'(setups: udfald)</small></h2>' + "".join(filt)
             + '<div class="box tw"><table><thead><tr><th>type</th><th>ts (UTC)</th><th>known_ts (UTC)</th>'
             '<th class=n>forsinkelse min</th><th class=n>retn.</th><th>niveau / zone</th><th class=n>fremad</th></tr>'
             f'</thead><tbody>{"".join(rows)}</tbody></table></div>')
    return html_, shown


# ---------------------------------------------------------------- page

def render(s):
    p = ef.params()
    defs = definitions()
    setups_n = sum(len(r["setups"]) for r in s["_results"].values())
    picks = chart_picks(s)
    ev_html, shown = events_tab(s, p)
    keys = sorted(s["_study"]["days"])
    inputs = [f'<input class="f" type="radio" name="tab" id="t-{t}"{" checked" if t == "ov" else ""}>'
              for t in ("ov", "ch", "st", "ev")]
    inputs += [f'<input class="f" type="radio" name="cd" id="cd-{n}"{" checked" if n == 0 else ""}>'
               for n in range(len(picks))]
    inputs += [f'<input class="f" type="checkbox" id="ly-{name}"{" checked" if on else ""}>'
               for name, (_, _, _, on) in LAYERS.items()]
    inputs += [f'<input class="f" type="radio" name="sd" id="sd-{n}"{" checked" if n == 0 else ""}>'
               for n in range(len(keys))]
    inputs += ['<input class="f" type="radio" name="ek" id="ek-all" checked>']
    inputs += [f'<input class="f" type="radio" name="ek" id="ek-{k}">' for k in shown]
    prov = (f'kilde: <code>event_farm.random_walk_bars</code> + <code>event_farm.null_run</code> (driftløs log-random '
            f'walk, σ {ef.NULL_SIGMA_BAR * 1e4:g} bps pr. 5m-bar, {ef.NULL_SUB_STEPS} delskridt) · seed '
            f'<code>{s["seed"]}</code> · {s["instruments"]} instrumenter × {s["days"]} dage · motor '
            f'<code>research/tools/event_farm.py</code> sha256 <code>{e(s["_engine_sha"])}</code>')
    doc = [
        '<!doctype html><html lang="da"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>COPYBOT EVENT FARM (syntetisk)</title>'
        f'<style>{CSS}\n{dyn_css(len(picks), keys, shown)}</style></head><body>',
        "\n".join(inputs),
        '<div class="wrap"><header class="hdr"><div class="brand"><div class="logo">COPYBOT <span>EVENT FARM</span></div>'
        '<nav class="tabs"><label for="t-ov">OVERBLIK</label><label for="t-ch">CHART</label>'
        '<label for="t-st">STUDIER</label><label for="t-ev">HÆNDELSER</label></nav></div>'
        f'<a class="back" href="{BACK}">← papir-dashboard</a></header>',
        f'<div class="syn" role="alert">{e(BANNER)}</div><div class="prov">{prov}</div>',
        f'<section class="pane p-ov">{overview(s, setups_n, defs)}</section>',
        f'<section class="pane p-ch">{chart_tab(s, picks, p)}</section>',
        f'<section class="pane p-st">{studies(s, p)}</section>',
        f'<section class="pane p-ev">{ev_html}</section>',
        '<footer class="foot">Beskrivende mærkning, ingen strategi; intet er låst, aktiveret eller ført som alfa. '
        'Statisk side uden JavaScript og uden eksterne ressourcer. '
        f'<a href="{BACK}">Tilbage til papir-dashboardet</a>.</footer></div></body></html>',
    ]
    return "\n".join(doc)


def write_atomic(path, doc):
    """As paper_dashboard.write_atomic: temp file in the same folder, fsync, rename; the last good page survives."""
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"output .html (default {DEFAULT_OUT})")
    ap.add_argument("--seed", type=int, default=83)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--instruments", type=int, default=3)
    ap.add_argument("--source", default=SOURCE, help="only 'synthetic' is accepted")
    a = ap.parse_args(argv)
    try:
        s = build(a.seed, a.days, a.instruments, a.source)
    except ValueError as ex:
        raise SystemExit(str(ex))
    doc = render(s)
    out = os.path.expanduser(a.out)
    write_atomic(out, doc)
    print(f"{out}: {len(doc.encode())} bytes, seed {a.seed}, {s['days']} dage, syntetisk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
