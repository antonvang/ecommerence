"""COPYBOT PAPIR FEED: the event farm forward paper book as a vertical, full-screen card feed for the phone.

One static page, no JavaScript, no external resources (CSS scroll-snap only). Cards, newest first:
- a status card (warm-up progress or live counts, IntegrityHalt, PAPIR label);
- one card per setup (symbol, bar, setup kind): direction, the pattern chain, a mini candle chart around the setup with
  entry / stop / target lines, and the outcome across the tests that saw it (target, stop, timeout, open, skipped);
- a closing card: paper only, no evidence of an edge, link back to the dashboard.

The forward book is read with farm_dashboard.read_forward (read-only, query_only); nothing in ~/event_farm is written.

    python3 -m research.tools.farm_feed --forward-db ~/event_farm/event_farm_forward.db      # -> ~/copybot_farm_feed.html
"""
from __future__ import annotations

import argparse
import collections
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import farm_dashboard as fd  # noqa: E402
from research.tools.farm_dashboard import e  # noqa: E402

DEFAULT_OUT = "~/copybot_farm_feed.html"
DASH = "file:///home/anton/copybot_farm.html"
MAX_CARDS = 60
CHART_BEFORE, CHART_AFTER = 36, 24          # bars shown around the setup bar
STATUS_TXT = {"target": "mål", "stop": "stop", "timeout": "timeout", "missed": "misset", "no_fill": "ikke fyldt",
              "pending": "åben", "not_taken_warmup": "opvarmning"}
LABEL = "PAPIR / SIMULERING — ingen rigtige penge, ingen evidens for en fordel"

CSS = """
:root{color-scheme:dark;--bg:#07090d;--card:#0f141d;--line:#222a38;--txt:#eef2f8;--mut:#8d97a8;--pos:#19d38f;
--neg:#ff5468;--amb:#f4b740;--acc:#7c8cff;--sans:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.45 var(--sans)}
.feed{height:100svh;overflow-y:auto;scroll-snap-type:y mandatory;overscroll-behavior:contain}
.card{height:100svh;scroll-snap-align:start;scroll-snap-stop:always;display:flex;flex-direction:column;
justify-content:center;padding:22px 16px 26px;max-width:560px;margin:0 auto;position:relative}
.top{position:absolute;top:14px;left:16px;right:16px;display:flex;justify-content:space-between;align-items:center;
font-size:12px;letter-spacing:.08em;color:var(--mut);text-transform:uppercase}
.badge{display:inline-block;padding:3px 9px;border-radius:999px;font-weight:700;font-size:12px;letter-spacing:.06em}
.b-paper{background:rgba(255,84,104,.14);color:#ff8d9b;border:1px solid rgba(255,84,104,.4)}
.b-amb{background:rgba(244,183,64,.14);color:var(--amb)}.b-pos{background:rgba(25,211,143,.14);color:var(--pos)}
.b-neg{background:rgba(255,84,104,.14);color:var(--neg)}.b-mut{background:#1a2130;color:var(--mut)}
h1{font-size:40px;line-height:1.05;margin:0 0 8px;letter-spacing:-.02em}h1 span{color:var(--amb)}
h2{font-size:30px;margin:0;letter-spacing:-.01em}.sub{color:var(--mut);font-size:14px}
.dir{font-size:56px;font-weight:800;line-height:1;margin:6px 0 2px}.long{color:var(--pos)}.short{color:var(--neg)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}.chip{background:#182031;border:1px solid var(--line);
border-radius:999px;padding:3px 10px;font-size:13px;font-family:var(--mono)}
.chart{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px;margin:10px 0}
.chart svg{display:block;width:100%;height:auto}
.levels{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:8px 0}
.lv{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 10px}
.lv span{display:block;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em}
.lv b{font-family:var(--mono);font-size:14px;overflow-wrap:anywhere}
.out{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.big{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px}
.stat span{display:block;font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.08em}
.stat b{font-size:30px}
.bar{height:14px;background:#1a2130;border-radius:7px;overflow:hidden;margin:6px 0 2px}.bar i{display:block;height:100%;
background:linear-gradient(90deg,var(--amb),#ffd77a)}
.hint{position:absolute;bottom:14px;left:0;right:0;text-align:center;color:var(--mut);font-size:12px}
a{color:var(--acc)}
"""


def setups(live):
    """Trades grouped per setup (symbol, known_ts, kind), newest first, with per-status counts over the tests."""
    g = collections.OrderedDict()
    for t in sorted(live["trades"], key=lambda t: (-t["known_ts"], t["symbol"], t["kind"], t["variant"])):
        k = (t["symbol"], t["known_ts"], t["kind"])
        if k not in g:
            g[k] = {"symbol": t["symbol"], "known_ts": t["known_ts"], "kind": t["kind"], "dir": t["dir"],
                    "entry": t["entry"], "stop": t["stop"], "targets": set(), "status": collections.Counter(),
                    "variants": [], "chain": t.get("chain")}
        s = g[k]
        s["targets"].add(round(t["target"], 8))
        s["status"][t["status"]] += 1
        s["variants"].append(t["variant"])
    return list(g.values())


def mini_chart(bars, s, w=520, h=320):
    """Candles around the setup bar with entry / stop / target lines; the setup bar is marked."""
    k = next((i for i, b in enumerate(bars) if b[0] >= s["known_ts"] - fd.BS_LIVE), len(bars) - 1)
    lo_i, hi_i = max(0, k - CHART_BEFORE), min(len(bars), k + CHART_AFTER)
    win = bars[lo_i:hi_i]
    if not win:
        return ""
    tg = sorted(s["targets"])
    tg = tg if len(tg) <= 1 else [tg[0], tg[-1]]                             # nearest and farthest target only
    levels = [s["entry"], s["stop"]] + tg
    lo = min(min(b[3] for b in win), *levels)
    hi = max(max(b[2] for b in win), *levels)
    pad = (hi - lo) * 0.06 or 1.0
    lo, hi = lo - pad, hi + pad
    n = max(len(win), CHART_BEFORE + CHART_AFTER)
    cw = (w - 8) / n

    def y(p):
        return 4 + (hi - p) / (hi - lo) * (h - 8)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(s["symbol"])} 5m omkring setup">']
    mark_x = None
    for i, b in enumerate(win):
        x = 4 + i * cw + cw / 2
        if lo_i + i == k:
            mark_x = x
        up = b[4] >= b[1]
        col = "#19d38f" if up else "#ff5468"
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y(b[2]):.1f}" y2="{y(b[3]):.1f}" stroke="{col}" stroke-width="1"/>')
        top, bot = y(max(b[1], b[4])), y(min(b[1], b[4]))
        out.append(f'<rect x="{x - cw * 0.35:.1f}" y="{top:.1f}" width="{cw * 0.7:.1f}" height="{max(1.0, bot - top):.1f}" '
                   f'fill="{col}"/>')
    if mark_x is not None:
        out.append(f'<line x1="{mark_x:.1f}" x2="{mark_x:.1f}" y1="0" y2="{h}" stroke="#7c8cff" stroke-dasharray="3 4"/>')
    for p, col, lbl in ([(s["entry"], "#eef2f8", "indgang"), (s["stop"], "#ff5468", "stop")]
                        + [(t, "#19d38f", "mål") for t in tg]):
        out.append(f'<line x1="0" x2="{w}" y1="{y(p):.1f}" y2="{y(p):.1f}" stroke="{col}" stroke-opacity=".75" '
                   f'stroke-dasharray="6 4"/><text x="{w - 4}" y="{y(p) - 3:.1f}" text-anchor="end" font-size="11" '
                   f'fill="{col}" font-family="ui-monospace,monospace" paint-order="stroke" stroke="#0f141d" stroke-width="3">'
                   f'{lbl} {fd.px(p)}</text>')
    out.append("</svg>")
    return "".join(out)


def status_card(live, now):
    ident, rep, cfg = live["identity"], live["report"], live["identity"]["config"]
    trades = live["trades"]
    taken = [t for t in trades if not t["status"].startswith("not_taken")]
    st = collections.Counter(t["status"] for t in taken)
    need = int(cfg["warmup_bars"])
    done = {s: d["processed"] for s, d in rep["data"].items()}
    warm = min(done.values()) < need if done else True
    halted = live["halted"]
    head = (f'<span class="badge b-neg">STOP: {e(halted)}</span>' if halted else
            '<span class="badge b-amb">OPVARMNING</span>' if warm else '<span class="badge b-pos">● LIVE PAPIR</span>')
    body = []
    if warm:
        eta = fd.dhm(int(live["meta"]["start_ts"]) + need * int(cfg["bar_seconds"]))
        for s, n in done.items():
            body.append(f'<div class="sub">{e(s)} · {min(n, need)} / {need} barer</div>'
                        f'<div class="bar"><i style="width:{min(100, 100 * n // need)}%"></i></div>')
        body.append(f'<p class="sub">Første papirhandler fra <b>{e(eta)} UTC</b>. Indtil da bygger motoren niveauer og '
                    'struktur; setups vises men tages ikke.</p>')
    tiles = [(len(taken) - st.get("missed", 0) - st.get("no_fill", 0), "papirhandler"), (st.get("pending", 0), "åbne"), (st.get("target", 0), "mål ramt"),
             (st.get("stop", 0), "stop ramt")]
    return (f'<section class="card"><div class="top"><span>copybot · event farm</span>{head}</div>'
            f'<h1>PAPIR<span>FEED</span></h1><div class="sub">BTCUSDT · ETHUSDT · 5m · {len(ident["tests"])} tests · '
            f'opdateret {e(fd.dhm(int(now)))} UTC</div>' + "".join(body) +
            '<div class="big">' + "".join(f'<div class="stat"><span>{e(lbl)}</span><b>{v}</b></div>' for v, lbl in tiles)
            + f'</div><span class="badge b-paper">{e(LABEL)}</span><div class="hint">↓ swipe</div></section>')


def setup_card(live, s, i, n):
    bars = live["symbols"][s["symbol"]]["bars"]
    long_ = s["dir"] > 0
    st = s["status"]
    total = sum(st.values())
    skipped = st.get("not_taken_warmup", 0)
    outs = []
    for k, cls in (("target", "b-pos"), ("stop", "b-neg"), ("timeout", "b-mut"), ("pending", "b-amb"),
                   ("missed", "b-mut"), ("no_fill", "b-mut"), ("not_taken_warmup", "b-mut")):
        if st.get(k):
            outs.append(f'<span class="badge {cls}">{st[k]} × {e(STATUS_TXT[k])}</span>')
    other = sum(v for k, v in st.items() if k not in STATUS_TXT)
    if other:
        outs.append(f'<span class="badge b-mut">{other} × andet</span>')
    chain = [c for c in (s["chain"] or "").split(">") if c]
    tg = sorted(s["targets"])
    tg_txt = fd.px(tg[0]) if len(tg) == 1 else f"{fd.px(tg[0])}–{fd.px(tg[-1])}"
    verdict = ("sprunget over (opvarmning)" if skipped == total else
               "åben" if st.get("pending") else "afsluttet")
    return (f'<section class="card"><div class="top"><span>{e(s["symbol"])} · 5m · {e(fd.dhm(s["known_ts"]))} UTC</span>'
            f'<span>{i} / {n}</span></div>'
            f'<div class="dir {"long" if long_ else "short"}">{"▲ LONG" if long_ else "▼ SHORT"}</div>'
            f'<div class="sub">{e(s["kind"])} · {e(verdict)} · {total} tests så den</div>'
            '<div class="chips">' + "".join(f'<span class="chip">#{e(c)}</span>' for c in chain) + "</div>"
            f'<div class="chart">{mini_chart(bars, s)}</div>'
            f'<div class="levels"><div class="lv"><span>indgang</span><b>{fd.px(s["entry"])}</b></div>'
            f'<div class="lv"><span>stop</span><b>{fd.px(s["stop"])}</b></div>'
            f'<div class="lv"><span>mål</span><b>{e(tg_txt)}</b></div></div>'
            f'<div class="out">{"".join(outs)}</div></section>')


def end_card():
    return ('<section class="card"><h2>Det er papir.</h2><p class="sub">Alle handler her er simulerede efter regler, der '
            'blev låst før start (PROTOCOL_V3 ændring 46). Ingen konto, ingen nøgler, ingen ordrer. 28 bps omkostning er '
            'en antagelse. To uger er ingen dokumentation; rapporter kommer efter dag 14, 28 og 90.</p>'
            f'<p><a href="{DASH}">Fuldt dashboard →</a></p></section>')


def render(live, now=None):
    now = time.time() if now is None else now
    head = ('<!doctype html><html lang="da"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<title>Papir feed</title><style>{CSS}</style></head><body><main class="feed">')
    if live is None or live.get("state") != "ok":
        why = "ingen bog" if live is None else live.get("reason") or live.get("state")
        return (head + f'<section class="card"><h1>PAPIR<span>FEED</span></h1><p class="sub">Bogen kan ikke vises: '
                f'{e(why)}.</p></section>' + end_card() + "</main></body></html>")
    groups = setups(live)[:MAX_CARDS]
    cards = [status_card(live, now)] + [setup_card(live, s, i + 1, len(groups)) for i, s in enumerate(groups)]
    if not groups:
        cards.append('<section class="card"><h2>Ingen setups endnu</h2><p class="sub">Motoren har ikke fundet en '
                     'komplet kæde (sweep → MSS → FVG/OB) siden start.</p></section>')
    return head + "".join(cards) + end_card() + "</main></body></html>"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--forward-db", default="~/event_farm/event_farm_forward.db")
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    try:
        live = fd.read_forward(os.path.expanduser(a.forward_db))
    except ValueError as ex:
        raise SystemExit(str(ex))
    doc = render(live)
    out = os.path.expanduser(a.out)
    fd.write_atomic(out, doc)
    print(f"{out}: {len(doc.encode())} bytes, papir live: {live['state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
