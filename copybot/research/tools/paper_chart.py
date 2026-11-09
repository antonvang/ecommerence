"""HANDELSCHART for PAPER DASHBOARD V2 (director order 59-K): read-only static SVG trade charts, one instrument per
chart, of recorded paper fills. Display only: no order entry, no buttons, no JavaScript, no external resources.

Data (all read-only, all already in lab.db; no new sources):
- sim_fills of the FRESH paper books (net_report.build mark_status FRESH) up to the cutoff: KØB = green ▲ and
  SÆLG = red ▼ with the apex at the exact (ts, px) of the fill; a <title> tooltip per marker (SVG, not JS).
- observations metric='mark' for the same instrument (Binance USDⓈ-M premiumIndex mark, detector k3/1) when present:
  drawn as a line that is BROKEN wherever two consecutive points are more than GAP_FACTOR x the median spacing apart;
  every gap is shaded and has a <title>. Never interpolated. In the 59-K survey only BTCUSDT of the charted
  instruments has such a series. Without it the chart has markers only and says "Handelspriser — ikke en markedskurs".
- sim_funding.price at each funding settlement of the shown books (if the column exists): discrete points,
  "Funding-afregningspris", never a line.
- events of the skip kinds whose payload names an "instrument" equal to the chart's instrument: grey markers in a
  separate lane under the price area (a skip has no price, so it is never put on the price axis).
- Entry (gns.): net_report.account()'s own open_qty/open_basis per instrument at the cutoff, as a dashed horizontal
  line, only for an open position whose fills never flipped it through zero without going flat (net_report keeps the
  old basis on a flip, so such a basis is not documented and no line is drawn).
sim_equity is never read here: equity is not an instrument price.

Charts: the instruments with the most fills in the FRESH books (ties by name), at most MAX_CHARTS; a CSS-only radio
selector shows one at a time. Window: from the first fill of the instrument to the cutoff, or the last WINDOW_S if
longer (the hidden older fills are counted). Each chart is rendered in three SVG sizes (viewBox, width 100%) and CSS
shows the one that fits the screen, so text stays readable on desktop, tablet and mobile.
"""
import collections
import datetime as dt
import html
import json
import math
import re
import statistics

MAX_CHARTS = 6
WINDOW_S = 7 * 86400
GAP_FACTOR = 3
MIN_SPAN_S = 2 * 3600
MARKET_LABEL = "Markedskurs (mark, Binance USD-M premiumIndex)"
FILL_ONLY = "Handelspriser — ikke en markedskurs"
FUND_LABEL = "Funding-afregningspris"
# key: (viewBox width, height, left, right, top, bottom margin, font px, max x ticks, max y ticks, marker half-width)
VARIANTS = (("d", 1180, 470, 14, 86, 30, 46, 12, 9, 7, 7),
            ("t", 760, 420, 12, 80, 28, 44, 12, 6, 6, 6),
            ("m", 380, 330, 8, 64, 26, 42, 11, 4, 5, 5))
SKIP_LANE = 22
TIME_STEPS = (900, 1800, 3600, 7200, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 2 * 86400)

CSS = """
.hc{margin-top:8px}
.hc-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.hc-tab{cursor:pointer;padding:6px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel2);
color:var(--mut);font:600 13px ui-monospace,Menlo,Consolas,monospace;user-select:none}
.hc-tab small{font-weight:400;margin-left:6px;opacity:.8}
.chart{display:none;background:#0d121d;border:1px solid var(--line);border-radius:16px;overflow:hidden}
.ch-head{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:12px 14px;border-bottom:1px solid var(--line);
background:linear-gradient(180deg,#121a2a,#0d121d)}
.ch-sym{font:800 20px ui-monospace,Menlo,Consolas,monospace;letter-spacing:.02em}
.ch-paper{background:var(--amb);color:#1a1200;font-weight:900;font-size:11px;padding:3px 8px;border-radius:6px;
letter-spacing:.06em}
.ch-kind{font-size:12px;font-weight:700;padding:3px 8px;border-radius:6px}
.ch-kind.k-mkt{background:rgba(63,169,245,.14);color:var(--blu)}
.ch-kind.k-fill{background:rgba(245,166,35,.14);color:var(--amb)}
.ch-bots{color:var(--mut);font-size:12px}.ch-bots b{color:var(--txt)}
.ch-meta{display:flex;flex-wrap:wrap;gap:4px 16px;padding:8px 14px;font-size:12px;color:var(--mut)}
.ch-meta b{color:var(--txt);font-weight:600}
.ch-leg{display:flex;flex-wrap:wrap;gap:6px 16px;padding:0 14px 8px;font-size:12px;color:var(--mut);align-items:center}
.ch-leg span{display:inline-flex;align-items:center;gap:6px}.ch-leg svg{width:18px;height:12px}
.ch-plot{padding:0 4px}
.cv{display:block;width:100%;height:auto}
.cv-t,.cv-m{display:none}
.cv .bg{fill:#0d121d}.cv .grd{stroke:#1c2638;stroke-width:1}.cv .axl{stroke:#2a3650;stroke-width:1}
.cv .tk{fill:#8a96ad;font-family:ui-monospace,Menlo,Consolas,monospace}.cv .tk.dt{fill:#c3cbdb;font-weight:700}
.cv .wm{fill:#e6ebf5;opacity:.045;font-weight:900;font-family:ui-monospace,Menlo,Consolas,monospace}
.cv .wp{fill:#f5a623;opacity:.55;font-weight:900;letter-spacing:.08em}
.cv .gap{fill:#ffffff;fill-opacity:.045}
.cv .gapt{fill:#5d6a85;font-style:italic}
.cv .mkt{fill:none;stroke:#3fa9f5;stroke-width:1.6;stroke-linejoin:round;stroke-linecap:round}
.cv .mkd{fill:#3fa9f5}
.cv .last{fill:#3fa9f5}.cv .lastt{fill:#05121f;font-weight:800;font-family:ui-monospace,Menlo,Consolas,monospace}
.cv .mk.buy{fill:#16c784;stroke:#0d121d;stroke-width:1.5}
.cv .mk.sell{fill:#ff4d5e;stroke:#0d121d;stroke-width:1.5}
.cv .mk.fund{fill:#0d121d;stroke:#f5a623;stroke-width:1.8}
.cv .mk.skip{fill:#8a96ad;stroke:#0d121d;stroke-width:1.2}
.cv .lane{fill:#111827}.cv .lanet{fill:#6c7891}
.cv .entry{stroke-width:1.3;stroke-dasharray:6 4}.cv .entry.long{stroke:#16c784}.cv .entry.short{stroke:#ff4d5e}
.cv .eb{fill:#0d121d;fill-opacity:.88;stroke-width:1}.cv .eb.long{stroke:#16c784}.cv .eb.short{stroke:#ff4d5e}
.cv .et{fill:#e6ebf5;font-family:ui-monospace,Menlo,Consolas,monospace}
.cv .cut{stroke:#7b61ff;stroke-width:1;stroke-dasharray:3 3}.cv .cutt{fill:#a796ff}
.ch-notes{padding:8px 14px 12px;font-size:12px;color:var(--mut);border-top:1px solid var(--line)}
.ch-notes p{margin:3px 0}.ch-notes b{color:var(--txt)}
.hc-none{padding:16px;color:var(--mut);background:var(--panel);border:1px solid var(--line);border-radius:14px}
.hc-rest{color:var(--mut);font-size:12px;margin:8px 2px 0}
@media (max-width:1000px){.cv-d{display:none}.cv-t{display:block}}
@media (max-width:600px){.cv-t{display:none}.cv-m{display:block}.ch-sym{font-size:17px}}
"""


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def ident(s):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


def utc(t, fmt="%Y-%m-%d %H:%M:%S"):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime(fmt) + " UTC"


def has_table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def columns(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")} if has_table(con, table) else set()


def num(v, nd=8):
    """Exact-enough plain number for tooltips: up to nd significant digits, thousands separators."""
    return format(float(v), f",.{nd}g")


def flipped(fills):
    """True when the position crossed zero without going flat since it was last flat (net_report then keeps the
    old basis, so the average entry is not documented)."""
    pos, flip = 0.0, False
    for f in fills:
        new = pos + (1 if f["side"] == "buy" else -1) * f["qty"]
        if abs(new) < 1e-12:
            pos, flip = 0.0, False
            continue
        if pos != 0 and (pos > 0) != (new > 0):
            flip = True
        pos = new
    return flip


def market(con, sym, t0, t1):
    """Recorded mark points of this instrument in [t0, t1], split into segments at gaps > GAP_FACTOR x median."""
    if not has_table(con, "observations"):
        return None
    pts = []
    for ts, v in con.execute("SELECT ts, value FROM observations WHERE metric='mark' AND instrument=? AND ts>=? "
                             "AND ts<=? ORDER BY ts, id", (sym, t0, t1)):
        try:
            pts.append((int(ts), float(v)))
        except (TypeError, ValueError):
            continue
    if not pts:
        return None
    d = [b[0] - a[0] for a, b in zip(pts, pts[1:])]
    med = statistics.median(d) if d else 0
    thr = max(GAP_FACTOR * med, 1)
    segs = [[pts[0]]]
    gaps = []
    for a, b in zip(pts, pts[1:]):
        if b[0] - a[0] > thr:
            gaps.append((a[0], b[0]))
            segs.append([b])
        else:
            segs[-1].append(b)
    edges = []
    if med and pts[0][0] - t0 > thr:
        edges.append((t0, pts[0][0]))
    if med and t1 - pts[-1][0] > thr:
        edges.append((pts[-1][0], t1))
    return {"points": pts, "segments": segs, "gaps": gaps, "edge_gaps": edges, "median": med, "thr": thr}


def collect(con, rep, cutoff, names, skip_kinds):
    """The chart data: list of charts (most fills first, capped) and the instruments left out."""
    fresh = sorted(a["ledger"] for a in rep["accounts"] if a["mark_status"] == "FRESH")
    accs = {a["ledger"]: a for a in rep["accounts"]}
    if not fresh:
        return [], []
    ph = ",".join("?" * len(fresh))
    allf = collections.defaultdict(list)
    for i, led, ts, sym, side, px, q, fee in con.execute(
            f"SELECT id, exp_id, ts, instrument, side, px, qty, fee FROM sim_fills WHERE exp_id IN ({ph}) AND ts<=? "
            f"ORDER BY id", (*fresh, cutoff)):
        allf[sym].append({"id": i, "ledger": led, "ts": int(ts), "side": "buy" if side == "buy" else "sell",
                          "px": float(px), "qty": float(q), "fee": float(fee or 0.0)})
    order = sorted(allf, key=lambda s: (-len(allf[s]), s))
    chosen, rest = order[:MAX_CHARTS], [(s, len(allf[s])) for s in order[MAX_CHARTS:]]
    fcols = columns(con, "sim_funding")
    skips_by = collections.defaultdict(list)
    kp = ",".join("?" * len(skip_kinds))
    for i, ts, kind, led, p in con.execute(f"SELECT id, ts, kind, exp_id, payload FROM events WHERE kind IN ({kp}) "
                                           f"AND exp_id IN ({ph}) AND ts<=? ORDER BY ts, id",
                                           (*skip_kinds, *fresh, cutoff)):
        try:
            pl = json.loads(p) if p else {}
        except ValueError:
            continue
        if isinstance(pl, dict) and isinstance(pl.get("instrument"), str) and pl["instrument"]:
            skips_by[pl["instrument"]].append({"ts": int(ts), "kind": kind, "ledger": led,
                                               "reason": str(pl.get("reason") or pl.get("error") or "")})
    charts = []
    for sym in chosen:
        fl = allf[sym]
        first = min(f["ts"] for f in fl)
        long_ = cutoff - first > WINDOW_S
        w0 = cutoff - WINDOW_S if long_ else first
        span = max(cutoff - w0, MIN_SPAN_S)
        x0 = w0 if long_ else int(cutoff - span - 0.03 * span)
        x1 = int(cutoff + 0.015 * span)
        shown = sorted((f for f in fl if f["ts"] >= x0), key=lambda f: (f["ts"], f["id"]))
        by_led = collections.defaultdict(list)
        for f in fl:
            by_led[f["ledger"]].append(f)
        entries, undocumented = [], []
        for led in sorted(by_led):
            st = (accs[led].get("instruments") or {}).get(sym)
            if not st or not st.get("open_qty") or st.get("open_basis") is None:
                continue
            if flipped(by_led[led]):
                undocumented.append(led)
                continue
            entries.append({"ledger": led, "px": float(st["open_basis"]), "qty": float(st["open_qty"]),
                            "dir": "long" if st["open_qty"] > 0 else "short"})
        fund = []
        if {"price", "instrument", "exp_id", "ts"} <= fcols:
            tcol = "COALESCE(settle_ts, ts)" if "settle_ts" in fcols else "ts"
            seen = collections.OrderedDict()
            for t, price, led in con.execute(
                    f"SELECT {tcol}, price, exp_id FROM sim_funding WHERE instrument=? AND exp_id IN ({ph}) AND ts<=? "
                    f"AND price IS NOT NULL ORDER BY {tcol}, id", (sym, *fresh, cutoff)):
                t = int(t)
                if x0 <= t <= cutoff:
                    seen.setdefault((t, float(price)), []).append(led)
            fund = [{"ts": t, "px": p, "ledgers": sorted(set(ls))} for (t, p), ls in seen.items()]
        sk = [s for s in skips_by.get(sym, []) if s["ts"] >= x0]
        charts.append({"instrument": sym, "fills": shown, "fills_total": len(fl), "hidden": len(fl) - len(shown),
                       "long": long_, "x0": x0, "x1": x1, "w0": w0, "cutoff": cutoff,
                       "bots": sorted(by_led, key=lambda led: names.get(led, led)),
                       "fill_counts": {led: len(v) for led, v in by_led.items()},
                       "entries": entries, "undocumented": undocumented, "funding": fund, "skips": sk,
                       "market": market(con, sym, x0, cutoff)})
    return charts, rest


def nice(x):
    if x <= 0:
        return 1.0
    p = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if x <= m * p:
            return m * p
    return 10 * p


def yrange(c):
    vals = [f["px"] for f in c["fills"]] + [f["px"] for f in c["funding"]] + [x["px"] for x in c["entries"]]
    if c["market"]:
        vals += [v for _, v in c["market"]["points"]]
    if not vals:
        return 0.0, 1.0
    lo, hi = min(vals), max(vals)
    if hi - lo < abs(hi) * 1e-6 or hi == lo:
        d = abs(hi) * 0.005 or 1.0
        lo, hi = lo - d, hi + d
    pad = (hi - lo) * 0.09
    return lo - pad, hi + pad


def decimals(step):
    """Fewest decimals that print every tick of this step exactly (0.25 -> 2, 0.5 -> 1, 1000 -> 0)."""
    for d in range(12):
        if abs(round(step, d) - step) <= step * 1e-9:
            return d
    return 12


def tri(x, y, s, up):
    """Triangle with its apex exactly at (x, y): ▲ body below the point for KØB, ▼ body above for SÆLG."""
    h = s * 1.45
    yb = y + h if up else y - h
    return f"M{x:.2f} {y:.2f}L{x - s:.2f} {yb:.2f}L{x + s:.2f} {yb:.2f}Z"


def svg(c, names, var):
    key, W, H, ml, mr, mt, mb, fs, xt, yt, ms = var
    lane = SKIP_LANE if c["skips"] else 0
    pl, pr, pt = ml, W - mr, mt
    pb = H - mb - lane - (6 if lane else 0)
    x0, x1 = c["x0"], c["x1"]
    lo, hi = yrange(c)
    X = lambda t: pl + (t - x0) / (x1 - x0) * (pr - pl)  # noqa: E731
    Y = lambda v: pb - (v - lo) / (hi - lo) * (pb - pt)  # noqa: E731
    sym = c["instrument"]
    o = [f'<svg class="cv cv-{key}" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img" '
         f'data-instrument="{e(sym)}" data-x0="{x0}" data-x1="{x1}" data-y0="{lo!r}" data-y1="{hi!r}" '
         f'data-plot="{pl},{pt},{pr},{pb}" aria-label="{e(sym)} handelschart, papir/simulation">',
         f'<rect class="bg" x="0" y="0" width="{W}" height="{H}"/>']
    # watermark
    o.append(f'<text class="wm" x="{(pl + pr) / 2:.1f}" y="{(pt + pb) / 2 + fs:.1f}" text-anchor="middle" '
             f'font-size="{max(28, int((pr - pl) / 9))}">{e(sym)}</text>')
    o.append(f'<text class="wp" x="{pl + 6}" y="{pt - 10}" font-size="{fs - 1}">PAPER / SIMULATION</text>')
    # y grid + right price axis
    step = nice((hi - lo) / yt)
    dec = decimals(step)
    v = math.ceil(lo / step) * step
    while v <= hi + 1e-12:
        y = Y(v)
        o.append(f'<line class="grd" x1="{pl}" x2="{pr}" y1="{y:.2f}" y2="{y:.2f}"/>')
        o.append(f'<text class="tk" x="{pr + 6}" y="{y + fs * 0.35:.2f}" font-size="{fs}">{v:,.{dec}f}</text>')
        v += step
    # x grid + time axis (UTC)
    span = x1 - x0
    tstep = next((s for s in TIME_STEPS if span / s <= xt), TIME_STEPS[-1])
    t = (x0 // tstep + 1) * tstep
    last_day = None
    while t < x1:
        x = X(t)
        o.append(f'<line class="grd" x1="{x:.2f}" x2="{x:.2f}" y1="{pt}" y2="{pb + lane + (6 if lane else 0)}"/>')
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
        o.append(f'<text class="tk" x="{x:.2f}" y="{H - mb + fs + 8}" text-anchor="middle" font-size="{fs}">'
                 f'{d:%H:%M}</text>')
        if d.date() != last_day and (d.hour == 0 or last_day is None):
            o.append(f'<text class="tk dt" x="{x:.2f}" y="{H - mb + 2 * fs + 12}" text-anchor="middle" '
                     f'font-size="{fs}">{d:%m-%d}</text>')
        last_day = d.date()
        t += tstep
    o.append(f'<text class="tk" x="{pr + 6}" y="{H - mb + 2 * fs + 12}" font-size="{fs - 1}">UTC</text>')
    o.append(f'<line class="axl" x1="{pl}" x2="{pr}" y1="{pb}" y2="{pb}"/>'
             f'<line class="axl" x1="{pr}" x2="{pr}" y1="{pt}" y2="{pb}"/>')
    # cutoff line
    xc = X(c["cutoff"])
    o.append(f'<line class="cut" x1="{xc:.2f}" x2="{xc:.2f}" y1="{pt}" y2="{pb}"><title>Cutoff {e(utc(c["cutoff"]))}'
             f'</title></line><text class="cutt" x="{xc - 4:.2f}" y="{pt + fs}" text-anchor="end" '
             f'font-size="{fs - 1}">cutoff</text>')
    # market series: gap bands, broken polylines, last price tag
    m = c["market"]
    if m:
        for a, b in m["gaps"] + m["edge_gaps"]:
            xa, xb = X(a), X(b)
            mins = (b - a) / 60
            dur = f"{mins:.0f} min" if mins < 120 else f"{mins / 60:.1f} t"
            o.append(f'<rect class="gap" x="{xa:.2f}" y="{pt}" width="{max(xb - xa, 0.5):.2f}" height="{pb - pt}">'
                     f'<title>Hul i markedsdata: {e(utc(a, "%m-%d %H:%M:%S"))} – {e(utc(b, "%m-%d %H:%M:%S"))} '
                     f'({dur}); linjen er brudt, ikke interpoleret</title></rect>')
            if xb - xa > 9 * fs:
                o.append(f'<text class="gapt" x="{(xa + xb) / 2:.1f}" y="{pb - 8}" text-anchor="middle" '
                         f'font-size="{fs - 1}">ingen markedsdata</text>')
        budget = max(int(pr - pl), 1)
        for seg in m["segments"]:
            if len(seg) == 1:
                o.append(f'<circle class="mkd" cx="{X(seg[0][0]):.2f}" cy="{Y(seg[0][1]):.2f}" r="1.6"/>')
                continue
            o.append(f'<polyline class="mkt" data-t0="{seg[0][0]}" data-t1="{seg[-1][0]}" points="'
                     + " ".join(f"{X(a):.2f},{Y(b):.2f}" for a, b in thin(seg, X, len(m["points"]) > 2 * budget))
                     + '"/>')
        lt, lv = m["points"][-1]
        yl = Y(lv)
        o.append(f'<rect class="last" x="{pr + 1}" y="{yl - fs * 0.8:.2f}" width="{mr - 3}" height="{fs * 1.6:.2f}" '
                 f'rx="3"><title>Seneste mark {e(num(lv))} ({e(utc(lt))})</title></rect>'
                 f'<text class="lastt" x="{pr + 5}" y="{yl + fs * 0.35:.2f}" font-size="{fs}">{lv:,.{dec}f}</text>')
    # entry lines (documented open positions only), labels nudged apart
    labs = []
    for en in c["entries"]:
        y = Y(en["px"])
        o.append(f'<line class="entry {en["dir"]}" x1="{pl}" x2="{pr}" y1="{y:.2f}" y2="{y:.2f}" '
                 f'data-px="{en["px"]!r}"><title>Entry (gns.) {e(num(en["px"]))} · {e(names.get(en["ledger"]))} '
                 f'{en["dir"].upper()} {abs(en["qty"]):.6g} (net_report open_basis)</title></line>')
        labs.append([y, en])
    labs.sort(key=lambda a: a[0])
    gap_px = fs * 1.7
    for i in range(1, len(labs)):
        if labs[i][0] - labs[i - 1][0] < gap_px:
            labs[i][0] = labs[i - 1][0] + gap_px
    for y, en in labs:
        bot = names.get(en["ledger"], en["ledger"])
        txt = f'Entry (gns.) {en["px"]:,.{dec + 2}f} · {bot} {en["dir"].upper()}'
        wdt = len(txt) * fs * 0.62 + 10
        ly = min(max(y - fs * 0.9, pt + 2), pb - fs * 1.5)
        o.append(f'<rect class="eb {en["dir"]}" x="{pl + 4}" y="{ly:.2f}" width="{wdt:.1f}" height="{fs * 1.45:.2f}" '
                 f'rx="3"/><text class="et" x="{pl + 9}" y="{ly + fs * 1.05:.2f}" font-size="{fs - 1}">'
                 f'{e(txt)}</text>')
    # funding settlement prices: discrete diamonds
    for f in c["funding"]:
        x, y = X(f["ts"]), Y(f["px"])
        s = ms * 0.75
        o.append(f'<path class="mk fund" data-ts="{f["ts"]}" data-px="{f["px"]!r}" d="M{x:.2f} {y - s:.2f}L{x + s:.2f} '
                 f'{y:.2f}L{x:.2f} {y + s:.2f}L{x - s:.2f} {y:.2f}Z"><title>{e(utc(f["ts"]))} · {FUND_LABEL} '
                 f'{e(num(f["px"]))} · ' + e(", ".join(sorted(names.get(x_, x_) for x_ in f["ledgers"]))) + '</title></path>')
    # fills
    for f in c["fills"]:
        x, y = X(f["ts"]), Y(f["px"])
        up = f["side"] == "buy"
        o.append(f'<path class="mk {f["side"]}" data-ts="{f["ts"]}" data-px="{f["px"]!r}" d="{tri(x, y, ms, up)}">'
                 f'<title>{e(utc(f["ts"]))} · {e(names.get(f["ledger"], f["ledger"]))} · '
                 f'{"KØB" if up else "SÆLG"} {e(sym)} · {f["qty"]:.6g} @ {e(num(f["px"]))} · '
                 f'gebyr {abs(f["fee"]):.4f}</title></path>')
    # skip lane (no price): grey markers by time only
    if lane:
        ly = pb + 6
        o.append(f'<rect class="lane" x="{pl}" y="{ly}" width="{pr - pl}" height="{lane}"/>'
                 f'<text class="lanet" x="{pr + 6}" y="{ly + lane / 2 + fs * 0.35:.1f}" font-size="{fs - 1}">'
                 f'Spring over</text>')
        for s in c["skips"]:
            o.append(f'<circle class="mk skip" data-ts="{s["ts"]}" cx="{X(s["ts"]):.2f}" cy="{ly + lane / 2:.1f}" '
                     f'r="{ms * 0.7:.1f}"><title>{e(utc(s["ts"]))} · {e(names.get(s["ledger"], s["ledger"]))} · '
                     f'SPRUNGET OVER {e(sym)} · {e(s["kind"])}: {e(s["reason"][:200])}</title></circle>')
    o.append("</svg>")
    return "".join(o)


def thin(seg, X, on):
    """Min/max per pixel column (only when the series has many more points than pixels): every kept point is a
    recorded point, extremes are preserved, nothing is invented."""
    if not on:
        return seg
    out, col, grp = [], None, []
    for p in seg + [None]:
        c = None if p is None else int(X(p[0]))
        if grp and c != col:
            lo = min(grp, key=lambda q: q[1])
            hi = max(grp, key=lambda q: q[1])
            keep = sorted({grp[0], lo, hi, grp[-1]}, key=lambda q: q[0])
            out.extend(keep)
            grp = []
        if p is not None:
            col = c
            grp.append(p)
    return out


def legend_icon(kind):
    shapes = {"buy": '<path d="M9 1L3 11L15 11Z" fill="#16c784"/>',
              "sell": '<path d="M9 11L3 1L15 1Z" fill="#ff4d5e"/>',
              "mkt": '<line x1="1" x2="17" y1="6" y2="6" stroke="#3fa9f5" stroke-width="2"/>',
              "gap": '<rect x="1" y="1" width="16" height="10" fill="#ffffff" fill-opacity=".06" stroke="#3a4763" '
                     'stroke-dasharray="2 2"/>',
              "fund": '<path d="M9 1L14 6L9 11L4 6Z" fill="#0d121d" stroke="#f5a623" stroke-width="1.8"/>',
              "skip": '<circle cx="9" cy="6" r="4" fill="#8a96ad"/>',
              "long": '<line x1="1" x2="17" y1="6" y2="6" stroke="#16c784" stroke-width="1.5" stroke-dasharray="4 3"/>',
              "short": '<line x1="1" x2="17" y1="6" y2="6" stroke="#ff4d5e" stroke-width="1.5" '
                       'stroke-dasharray="4 3"/>'}
    return f'<svg viewBox="0 0 18 12" aria-hidden="true">{shapes[kind]}</svg>'


def card(c, names):
    sym, m = c["instrument"], c["market"]
    nb = sum(1 for f in c["fills"] if f["side"] == "buy")
    pts = len({f["ts"] for f in c["fills"]})
    ns = len(c["fills"]) - nb
    bots = " · ".join(f'<b>{e(names.get(b, b))}</b> ({c["fill_counts"][b]} fyld)' for b in c["bots"])
    kind = (f'<span class="ch-kind k-mkt">{e(MARKET_LABEL)} + handler</span>' if m else
            f'<span class="ch-kind k-fill">{e(FILL_ONLY)}</span>')
    hm = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%m-%d %H:%M")  # noqa: E731
    win = (f'seneste 7 d: {hm(c["w0"])} – {e(utc(c["cutoff"], "%m-%d %H:%M"))}; '
           f'{c["hidden"]} ældre fyld ikke vist' if c["long"] else
           f'alle handler til cutoff: {hm(c["w0"])} – {e(utc(c["cutoff"], "%m-%d %H:%M"))}')
    o = [f'<article class="chart ch-{ident(sym)}" data-instrument="{e(sym)}">',
         f'<div class="ch-head"><span class="ch-sym">{e(sym)}</span><span class="ch-paper">PAPER / SIMULATION</span>'
         f'{kind}<span class="ch-bots">Bots: {bots}</span></div>',
         f'<div class="ch-meta"><span>Vindue: <b>{win}</b></span><span>Fyld i vinduet: <b>{len(c["fills"])}</b> '
         f'({nb} køb / {ns} salg)' + (f'; fordelt på {pts} tidspunkter, fyld på samme tidspunkt ligger oven i hinanden'
                                      if pts < len(c["fills"]) else "") + '</span>']
    if m:
        o.append(f'<span>Markedspunkter: <b>{len(m["points"])}</b> i {len(m["segments"])} segmenter, '
                 f'{len(m["gaps"]) + len(m["edge_gaps"])} huller</span>')
    if c["funding"]:
        o.append(f'<span>{FUND_LABEL}er: <b>{len(c["funding"])}</b></span>')
    if c["skips"]:
        o.append(f'<span>Sprunget over: <b>{len(c["skips"])}</b></span>')
    o.append("</div>")
    leg = [("buy", "KØB (fyldpris)"), ("sell", "SÆLG (fyldpris)")]
    if m:
        leg = [("mkt", "Markedskurs (mark)"), ("gap", "hul i markedsdata, linjen brudt")] + leg
    if c["funding"]:
        leg.append(("fund", FUND_LABEL))
    if any(x["dir"] == "long" for x in c["entries"]):
        leg.append(("long", "Entry (gns.) LONG"))
    if any(x["dir"] == "short" for x in c["entries"]):
        leg.append(("short", "Entry (gns.) SHORT"))
    if c["skips"]:
        leg.append(("skip", "Sprunget over (ingen pris)"))
    o.append('<div class="ch-leg">' + "".join(f"<span>{legend_icon(k)}{e(t)}</span>" for k, t in leg) + "</div>")
    o.append('<div class="ch-plot">' + "".join(svg(c, names, v) for v in VARIANTS) + "</div>")
    notes = []
    if m:
        notes.append(f'<b>Markedskurs</b>: registrerede mark-observationer (observations, metric=mark) for {e(sym)}. '
                     f'Medianafstand {m["median"]:.0f} s; linjen brydes ved huller over {GAP_FACTOR}× medianen '
                     f'({m["thr"] / 60:.1f} min) og interpoleres aldrig. Handelsmarkørerne er en separat serie.')
    else:
        notes.append(f'<b>{e(FILL_ONLY)}</b>: der findes ingen registreret markedskursserie for {e(sym)}; markørerne '
                     f'er papirfyldpriser og forbindes ikke med en linje.')
    if c["funding"]:
        notes.append(f"<b>{FUND_LABEL}</b> (sim_funding.price) er enkeltpunkter ved hver 8-timers afregning, ikke en "
                     "kurve.")
    if c["entries"]:
        notes.append("<b>Entry (gns.)</b> = net_report's gennemsnitlige indgangspris for den åbne position ved cutoff "
                     "(open_basis); ingen ny P&amp;L beregnes her.")
    if c["undocumented"]:
        notes.append("Ingen entry-linje for " + ", ".join(e(names.get(x, x)) for x in c["undocumented"])
                     + ": positionen vendte gennem nul uden at være flad, så gennemsnittet er ikke dokumenteret.")
    notes.append("Hold musen over en markør for tid, side, mængde @ pris og gebyr. Kun visning: ingen ordrer.")
    o.append('<div class="ch-notes">' + "".join(f"<p>{n}</p>" for n in notes) + "</div></article>")
    return "\n".join(o)


def section(con, rep, cutoff, names, skip_kinds):
    """(radio inputs, css, html) of the HANDELSCHART section; the radios go before .wrap like the other filters."""
    charts, rest = collect(con, rep, int(cutoff), names, skip_kinds)
    ids = [ident(c["instrument"]) for c in charts]
    radios = "".join(f'<input class="f" type="radio" name="fc" id="fc-{i}"{" checked" if k == 0 else ""}>'
                     for k, i in enumerate(ids))
    on = "{background:var(--acc);color:#fff;border-color:var(--acc)}"
    css = [CSS] + [f"#fc-{i}:checked~.wrap label[for=fc-{i}]{on}#fc-{i}:checked~.wrap .ch-{i}{{display:block}}"
                   for i in ids]
    o = ['<section class="hc" id="handelschart">',
         '<h2>Handelschart <small>· kun visning af registrerede papirhandler for FRESH-bøgerne · ét instrument pr. '
         'graf · ingen ordrer fra grafen</small></h2>']
    if not charts:
        o.append('<div class="hc-none">Ingen handelschart: ingen FRESH-papirbøger med fyld til cutoff.</div>')
    else:
        o.append('<div class="hc-tabs" aria-label="vælg instrument">' + "".join(
            f'<label class="hc-tab" for="fc-{i}">{e(c["instrument"])}<small>{c["fills_total"]} fyld</small></label>'
            for i, c in zip(ids, charts)) + "</div>")
        o.extend(card(c, names) for c in charts)
        if rest:
            o.append(f'<p class="hc-rest">Ikke vist (maks. {MAX_CHARTS} grafer, flest fyld først): '
                     + ", ".join(f"{e(s)} ({n})" for s, n in rest) + ".</p>")
    o.append("</section>")
    return radios, "\n".join(css), "\n".join(o)
