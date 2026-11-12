"""HANDELSCHART for PAPER DASHBOARD V2 (director order 59-K, V3 order 69, V4 2026-11-12): read-only static SVG trade
charts, one instrument per chart, of recorded paper fills. Display only: no order entry, no buttons, no JavaScript, no
external resources.

Data (all read-only, all already in lab.db; no new sources, no network):
- sim_fills of the FRESH paper books (net_report.build mark_status FRESH) up to the cutoff: KØB = green ▲ and
  SÆLG = red ▼ with the apex at the exact (ts, px) of the fill; a <title> tooltip per marker (SVG, not JS).
- Price line (V4), one recorded series per chart, never mixed and never interpolated:
  1. observations detector census/1 metric snapshot (amendment 28: the hourly census of every Binance USDⓈ-M perp),
     payload rows[SYMBOL][0] = markPrice (payload columns[0] must be "markPrice"). Read only inside the chart window
     and never before the earliest start of the shown books. Broken wherever two consecutive snapshots are more than
     CENSUS_GAP_S apart (a missing hour); every recorded snapshot is a dot with a tooltip.
  2. else observations metric='mark' (Binance USDⓈ-M premiumIndex mark, detector k3/1): broken wherever two
     consecutive points are more than GAP_FACTOR x the median spacing apart.
  Every gap (also at the window edges) is shaded with a <title>. Without either series (e.g. a .SPOT leg) the chart has
  markers only and says FILL_ONLY ("kun handelspriser").
- Positions (V4): each book's fills of the instrument are split into trades (flat -> flat; a flip through zero closes
  the trade and opens a new one at the flipping fill's price). Each trade is a shaded box from entry to exit (or to
  the cutoff while open) between the average entry and exit price, plus a bar in a per-book position lane. The tooltip
  of a closed trade gives the price P&L, the fees and the result after fees (funding not included).
- sim_funding.price at each funding settlement of the shown books (if the column exists): small discrete diamonds,
  "Funding-afregningspris", never a line.
- events of the skip kinds whose payload names an "instrument" equal to the chart's instrument: grey markers in a
  separate lane (a skip has no price, so it is never put on the price axis).
- Entry (gns.): net_report.account()'s own open_qty/open_basis per instrument at the cutoff, as a dashed horizontal
  line, only for an open position whose fills never flipped it through zero without going flat (net_report keeps the
  old basis on a flip, so such a basis is not documented and no line is drawn).
sim_equity is never read here: equity is not an instrument price.

Layers (V4): CSS-only checkboxes before .wrap (#hl-line, #hl-trades, #hl-pos, #hl-fund, #hl-gaps, #hl-skip) hide the
matching <g class="hl-..."> groups; the labels sit in each chart's side panel ("Lag") with per-chart counts.
Charts: the instruments with the most fills in the FRESH books (ties by name), at most MAX_CHARTS; a CSS-only radio
selector shows one at a time. Window: from the first fill of the instrument to the cutoff, or the last WINDOW_S if
longer (the hidden older fills are counted). Each chart is ONE responsive SVG (viewBox, width 100%); on narrow screens
CSS enlarges the text, hides every other time label and scales the markers about their apex (transform-box: fill-box),
so the apex stays at the exact (ts, px). The data cutoff is printed inside the chart.
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
CENSUS_GAP_S = 5400                      # hourly census: > 90 min between two snapshots = a missing hour = a gap
MAX_DOTS = 400                           # census dots (one per recorded snapshot) only while the series is sparse
MIN_SPAN_S = 2 * 3600
MARKET_LABEL = "Markedskurs (mark, Binance USD-M premiumIndex)"
CENSUS_LABEL = "Markedskurs (markPrice, Binance USD-M census, 1 t)"
FILL_ONLY = "Kun handelspriser — ingen registreret markedskurs"
FUND_LABEL = "Funding-afregningspris"
SAFE_SYM = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
# key: (viewBox width, price-area height, left, right, top, bottom margin, font px, max x ticks, max y ticks,
# marker half-width). V3: one responsive size; the mobile look is CSS only (see CSS @media below).
VARIANTS = (("d", 960, 380, 14, 118, 52, 60, 14, 14, 8, 7),)
SKIP_LANE = 18
POS_LANE = 15
POS_GAP = 4
TIME_STEPS = (900, 1800, 3600, 7200, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 2 * 86400)
# layer id -> (label, colour)
LAYERS = collections.OrderedDict((("line", ("Prislinje", "#4aa3f0")), ("trades", ("Handler KØB / SÆLG", "#16c784")),
                                  ("pos", ("Positioner", "#a99cff")), ("fund", ("Funding", "#f2b33d")),
                                  ("gaps", ("Huller i prisdata", "#8b95a7")), ("skip", ("Sprunget over", "#c9d1de"))))

CSS = """
.hc-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.hc-tab{cursor:pointer;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--panel);
color:var(--mut);font:600 13px var(--mono);user-select:none}
.hc-tab small{font:500 11px var(--sans);margin-left:6px;opacity:.85}
.hc-tab i{display:inline-block;width:7px;height:7px;border-radius:50%;margin-left:7px;vertical-align:1px}
.hc-tab i.p-on{background:#4aa3f0}.hc-tab i.p-off{background:transparent;border:1.5px solid var(--amb)}
.chart{display:none;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.ch-head{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line)}
.ch-sym{font:700 18px var(--mono);letter-spacing:.01em}
.ch-paper{background:var(--amb);color:#1a1200;font-weight:800;font-size:10.5px;padding:2px 7px;border-radius:5px;
letter-spacing:.06em}
.ch-kind{font-size:12px;font-weight:600;padding:2px 8px;border-radius:5px}
.ch-kind.k-mkt{background:var(--blu-bg);color:var(--blu)}
.ch-kind.k-fill{background:var(--amb-bg);color:var(--amb);font-weight:800}
.ch-upd{font:12px var(--mono);color:var(--mut)}.ch-upd b{color:#a99cff;font-weight:700}
.ch-bots{color:var(--mut);font-size:12px;flex-basis:100%}.ch-bots b{color:var(--txt);font-weight:600}
.ch-body{display:grid;grid-template-columns:minmax(0,1fr) 290px;grid-template-rows:auto 1fr;
grid-template-areas:"plot side" "notes side"}
.ch-plot{grid-area:plot;padding:6px 2px 4px;background:var(--plot);min-width:0}
.ch-notes{grid-area:notes;padding:10px 16px 12px;font-size:12px;color:var(--mut);border-top:1px solid var(--line);
columns:2 320px;column-gap:28px}
.ch-side{grid-area:side;border-left:1px solid var(--line);padding:12px 14px;font-size:12px;color:var(--mut);display:flex;
flex-direction:column;gap:10px}
.ch-side h3{margin:0;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
.ch-lyrs{display:flex;flex-direction:column;gap:2px}
.lyr{display:grid;grid-template-columns:16px 1fr auto;gap:8px;align-items:center;cursor:pointer;padding:5px 6px;
border-radius:6px;font-size:12.5px;color:var(--txt);user-select:none}
.lyr:hover{background:var(--panel2)}
.lyr .bx{width:14px;height:14px;border-radius:3px;border:1.5px solid var(--mut)}
.lyr small{display:block;color:var(--mut);font:10.5px var(--mono);overflow-wrap:anywhere}
.lyr .c{font:12px var(--mono);color:var(--mut)}
.lyr svg{width:18px;height:12px;vertical-align:-1px;margin-right:6px}
.ch-meta{display:flex;flex-direction:column;gap:4px}.ch-meta b{color:var(--txt);font-weight:600}
.ch-notes p{margin:0 0 6px}.ch-notes b{color:var(--txt)}
.cv{display:block;width:100%;height:auto}
.cv .bg{fill:var(--plot)}.cv .grd{stroke:#1a2131;stroke-width:1}.cv .grd.day{stroke:#2a3346}
.cv .axl{stroke:#2b3447;stroke-width:1}
.cv .tk{fill:#9aa4b6;font-family:var(--mono)}.cv .tk.dt{fill:#d5dbe6;font-weight:700}
.cv .ttl{fill:#e7ebf2;font-weight:800;font-family:var(--mono)}.cv .src{fill:#7fbef5;font-family:var(--mono)}
.cv .src.none{fill:#f2b33d;font-weight:800}
.cv .upd{fill:#c3b9ff;font-family:var(--mono);font-weight:700}.cv .upd2{fill:#8b95a7;font-family:var(--mono)}
.cv .wm{fill:#e7ebf2;opacity:.035;font-weight:800;font-family:var(--mono)}
.cv .wp{fill:#f2b33d;opacity:.55;font-weight:800;letter-spacing:.08em}
.cv .gap{fill:#ffffff;fill-opacity:.045;stroke:#3b465c;stroke-dasharray:3 3;stroke-width:1;
vector-effect:non-scaling-stroke}
.cv .gapt{fill:#6f7a8f;font-style:italic}
.cv .mkt{fill:none;stroke:#4aa3f0;stroke-width:2;stroke-linejoin:round;stroke-linecap:round;
vector-effect:non-scaling-stroke}
.cv .mkd{fill:#4aa3f0}.cv .mkp{fill:#4aa3f0;stroke:#0e131d;stroke-width:.8}
.cv .last{fill:#4aa3f0}.cv .lastt{fill:#06121f;font-weight:800;font-family:var(--mono)}
.cv .mk.buy{fill:#16c784;stroke:#e7ebf2;stroke-width:1.2}
.cv .mk.sell{fill:#ff4d5e;stroke:#e7ebf2;stroke-width:1.2}
.cv .mk.fund{fill:#0e131d;stroke:#f2b33d;stroke-width:1.5}
.cv .mk.skip{fill:#8b95a7;stroke:#0e131d;stroke-width:1.2}
.cv .pbox{stroke-width:1;vector-effect:non-scaling-stroke}
.cv .pbox.win{fill:#16c784;fill-opacity:.16;stroke:#16c784;stroke-opacity:.55}
.cv .pbox.loss{fill:#ff4d5e;fill-opacity:.16;stroke:#ff4d5e;stroke-opacity:.55}
.cv .pbox.open{fill:#a99cff;fill-opacity:.12;stroke:#a99cff;stroke-opacity:.6;stroke-dasharray:4 3}
.cv .pbox.mixed{fill:#a99cff;fill-opacity:.10;stroke:#a99cff;stroke-opacity:.45}
.cv .pres{fill:#0b0e14;font-family:var(--mono);font-weight:800;pointer-events:none}
.cv .pcon{stroke:#c9d1de;stroke-opacity:.5;stroke-width:1;stroke-dasharray:2 3;vector-effect:non-scaling-stroke}
.cv .plane{fill:#131a27}.cv .pbar.long{fill:#16c784}.cv .pbar.short{fill:#ff4d5e}.cv .pbar.open{fill-opacity:.55}
.cv .plt{fill:#c9d1de;font-family:var(--mono);font-weight:600}
.cv .lane{fill:#131a27}.cv .lanet{fill:#6f7a8f}
.cv .entry{stroke-width:1.3;stroke-dasharray:6 4;vector-effect:non-scaling-stroke}.cv .entry.long{stroke:#16c784}
.cv .entry.short{stroke:#ff4d5e}
.cv .eb{fill:#0e131d;fill-opacity:.9;stroke-width:1}.cv .eb.long{stroke:#16c784}.cv .eb.short{stroke:#ff4d5e}
.cv .et{fill:#e7ebf2;font-family:var(--mono)}
.cv .cut{stroke:#a99cff;stroke-width:1.2;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}.cv .cutt{fill:#c3b9ff}
.hc-none{padding:16px;color:var(--mut);background:var(--panel);border:1px solid var(--line);border-radius:12px}
.hc-rest{color:var(--mut);font-size:12px;margin:8px 2px 0}
@media (max-width:1100px){.ch-body{grid-template-columns:1fr;grid-template-rows:auto;grid-template-areas:"plot" "side" "notes"}
.ch-side{border-left:0;border-top:1px solid var(--line)}
.ch-lyrs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px 8px}}
@media (max-width:640px){.cv .tk{font-size:29px}.cv .tk.dt{transform:translateY(12px)}
.cv .tk.xo,.cv .gapt,.cv .lastg,.cv .wm,.cv .plt,.cv .pres,.cv .upd2,.cv .src,.cv .eg{display:none}
.cv .ttl{font-size:34px}.cv .upd{font-size:24px}.cv .wp,.cv .cutt{font-size:21px}.cv .lanet{font-size:16px}
.cv .mk.buy{transform-box:fill-box;transform-origin:50% 0;transform:scale(1.9)}
.cv .mk.sell{transform-box:fill-box;transform-origin:50% 100%;transform:scale(1.9)}
.cv .mk.fund,.cv .mk.skip,.cv .mkp{transform-box:fill-box;transform-origin:50% 50%;transform:scale(1.8)}
.ch-sym{font-size:16px}.ch-side{padding:10px 12px}.ch-plot{padding:4px 0}.ch-lyrs{grid-template-columns:1fr}}
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


def usd(v):
    return f"{v:+,.2f} USD"


def dur(s):
    m = s / 60
    return f"{m:.0f} min" if m < 120 else (f"{m / 60:.1f} t" if m < 48 * 60 else f"{m / 1440:.1f} d")


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


def trades(fills):
    """Round trips of ONE book in ONE instrument (fills in id order): flat -> flat. A fill that crosses zero closes the
    trade with the part that brings it flat and opens a new one (flip=True) with the rest at the same fill price. Fees
    are split pro rata on such a fill. Average-cost basis as net_report (realized = closed qty x (exit - basis))."""
    out, cur, pos = [], None, 0.0
    for f in fills:
        sg, q, px, fee = (1 if f["side"] == "buy" else -1), f["qty"], f["px"], abs(f["fee"])
        if q <= 0:
            continue
        rest, flip = q, False
        if pos and (pos > 0) != (sg > 0):
            closed = min(q, abs(pos))
            cur["exit_qty"] += closed
            cur["exit_val"] += closed * px
            cur["fees"] += fee * closed / q
            cur["price_pnl"] += closed * (px - cur["basis"]) * (1 if pos > 0 else -1)
            cur["n"] += 1
            pos += sg * closed
            rest = q - closed
            if abs(pos) <= 1e-9 * max(1.0, q):
                pos = 0.0
                cur["end"], cur["exit_fill"] = f["ts"], f["id"]
                cur["exit"] = cur["exit_val"] / cur["exit_qty"]
                cur["net"] = cur["price_pnl"] - cur["fees"]
                out.append(cur)
                cur = None
            if rest <= 1e-9 * max(1.0, q):
                continue
            flip = True
        if not pos:
            cur = {"ledger": f["ledger"], "dir": "long" if sg > 0 else "short", "start": f["ts"], "end": None,
                   "basis": px, "qty": 0.0, "max_qty": 0.0, "exit_qty": 0.0, "exit_val": 0.0, "fees": 0.0,
                   "price_pnl": 0.0, "n": 0, "flip": flip, "exit": None, "net": None, "exit_fill": None}
        else:
            cur["basis"] = (cur["basis"] * abs(pos) + px * rest) / (abs(pos) + rest)
        cur["qty"] += rest
        cur["fees"] += fee * rest / q
        cur["n"] += 1
        pos += sg * rest
        cur["max_qty"] = max(cur["max_qty"], abs(pos))
    if cur:
        cur["open_qty"] = abs(pos)
        out.append(cur)
    return out


def split(pts, thr, t0, t1):
    """Recorded points -> segments broken where two neighbours are more than thr apart; plus the gaps and the
    edge gaps (window start -> first point, last point -> cutoff). Nothing is interpolated."""
    segs, gaps = [[pts[0]]], []
    for a, b in zip(pts, pts[1:]):
        if b[0] - a[0] > thr:
            gaps.append((a[0], b[0]))
            segs.append([b])
        else:
            segs[-1].append(b)
    edges = []
    if pts[0][0] - t0 > thr:
        edges.append((t0, pts[0][0]))
    if t1 - pts[-1][0] > thr:
        edges.append((pts[-1][0], t1))
    return {"points": pts, "segments": segs, "gaps": gaps, "edge_gaps": edges, "thr": thr}


def market(con, sym, t0, t1):
    """Recorded k3 mark points of this instrument in [t0, t1], split into segments at gaps > GAP_FACTOR x median."""
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
    m = split(pts, max(GAP_FACTOR * med, 1), t0 if med else pts[0][0], t1 if med else pts[-1][0])
    m.update(source="k3", median=med)
    return m


def census(con, wins):
    """{symbol: [(ts, markPrice)]} from the hourly census/1 snapshots, one query for all charts. wins: {symbol:
    (t0, t1)}. Only rows whose payload is valid JSON with columns[0] == 'markPrice'; null/absent prices are skipped
    (the missing hour then shows as a gap). Symbols that are not plain tickers are never put into a JSON path."""
    syms = [s for s in sorted(wins) if SAFE_SYM.match(s)]
    if not syms or not {"payload", "detector", "metric"} <= columns(con, "observations"):
        return {}
    t0, t1 = min(wins[s][0] for s in syms), max(wins[s][1] for s in syms)
    sel = ", ".join("json_extract(payload, ?)" for _ in syms)
    out = {s: [] for s in syms}
    for row in con.execute(f"SELECT ts, json_extract(payload, '$.columns[0]'), {sel} FROM observations "
                           f"WHERE detector='census/1' AND metric='snapshot' AND ts>=? AND ts<=? AND json_valid(payload) "
                           f"ORDER BY ts, id", (*[f'$.rows."{s}"[0]' for s in syms], t0, t1)):
        if row[1] != "markPrice":
            continue
        ts = int(row[0])
        for s, v in zip(syms, row[2:]):
            if v is None or not wins[s][0] <= ts <= wins[s][1]:
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v > 0 and math.isfinite(v):
                out[s].append((ts, v))
    return out


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
    wins = {}
    for sym in chosen:
        fl = allf[sym]
        first = min(f["ts"] for f in fl)
        long_ = cutoff - first > WINDOW_S
        w0 = cutoff - WINDOW_S if long_ else first
        span = max(cutoff - w0, MIN_SPAN_S)
        x0 = w0 if long_ else int(cutoff - span - 0.03 * span)
        starts = [accs[f["ledger"]].get("started") for f in fl]
        starts = [int(s) for s in starts if isinstance(s, (int, float))]
        s0 = max(x0, min(starts)) if starts else x0          # never before the books started
        wins[sym] = (long_, w0, x0, int(cutoff + 0.015 * span), s0)
    cen = census(con, {s: (w[4], cutoff) for s, w in wins.items()})
    charts = []
    for sym in chosen:
        fl = allf[sym]
        long_, w0, x0, x1, s0 = wins[sym]
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
        tr = []
        for led in sorted(by_led):
            tr += [t for t in trades(by_led[led]) if t["end"] is None or t["end"] >= x0]
        tr.sort(key=lambda t: (t["start"], t["ledger"]))
        fund = []
        if {"price", "instrument", "exp_id", "ts"} <= fcols:
            tcol = "COALESCE(settle_ts, ts)" if "settle_ts" in fcols else "ts"
            rcol = "rate" if "rate" in fcols else "NULL"
            seen = collections.OrderedDict()
            for t, price, led, rate in con.execute(
                    f"SELECT {tcol}, price, exp_id, {rcol} FROM sim_funding WHERE instrument=? AND exp_id IN ({ph}) "
                    f"AND ts<=? AND price IS NOT NULL ORDER BY {tcol}, id", (sym, *fresh, cutoff)):
                t = int(t)
                if x0 <= t <= cutoff:
                    seen.setdefault((t, float(price)), []).append((led, rate))
            fund = [{"ts": t, "px": p, "ledgers": sorted({x for x, _ in ls}),
                     "rates": sorted({float(r) for _, r in ls if isinstance(r, (int, float))})}
                    for (t, p), ls in seen.items()]
        sk = [s for s in skips_by.get(sym, []) if s["ts"] >= x0]
        pts = cen.get(sym)
        if pts:
            m = split(pts, CENSUS_GAP_S, s0, cutoff)
            m.update(source="census", median=statistics.median([b[0] - a[0] for a, b in zip(pts, pts[1:])])
                     if len(pts) > 1 else 0)
        else:
            m = market(con, sym, x0, cutoff)
        charts.append({"instrument": sym, "fills": shown, "fills_total": len(fl), "hidden": len(fl) - len(shown),
                       "long": long_, "x0": x0, "x1": x1, "w0": w0, "cutoff": cutoff, "series_from": s0,
                       "bots": sorted(by_led, key=lambda led: names.get(led, led)),
                       "fill_counts": {led: len(v) for led, v in by_led.items()}, "trades": tr,
                       "entries": entries, "undocumented": undocumented, "funding": fund, "skips": sk,
                       "market": m})
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
    pad = (hi - lo) * 0.08
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


def trade_title(t, sym, names, cutoff):
    bot = names.get(t["ledger"], t["ledger"])
    head = f'{t["dir"].upper()} {sym} · {bot}'
    flip = " · åbnet ved vending gennem nul (indgang = vendingsfyldets pris)" if t["flip"] else ""
    if t["end"] is None:
        return (f'{head} · ÅBEN siden {utc(t["start"], "%m-%d %H:%M:%S")} ({dur(cutoff - t["start"])} ved cutoff) · '
                f'{t["open_qty"]:.6g} @ {num(t["basis"])} (gns. indgang) · gebyrer indtil nu {t["fees"]:.4f}{flip}')
    return (f'{head} · {utc(t["start"], "%m-%d %H:%M:%S")} → {utc(t["end"], "%m-%d %H:%M:%S")} '
            f'({dur(t["end"] - t["start"])}) · {t["qty"]:.6g} @ {num(t["basis"])} → {num(t["exit"])} · '
            f'pris-P&L {usd(t["price_pnl"])} · gebyrer {t["fees"]:.4f} · resultat efter gebyrer {usd(t["net"])} '
            f'(funding ikke medregnet){flip}')


def svg(c, names, var):
    key, W, PH, ml, mr, mt, mb, fs, xt, yt, ms = var
    bots = c["bots"]
    pos_h = (10 + len(bots) * (POS_LANE + POS_GAP)) if c["trades"] else 0
    lane = SKIP_LANE if c["skips"] else 0
    pl, pr, pt = ml, W - mr, mt
    pb = pt + PH
    yp = pb + 10                                           # top of the position lanes
    ys = pb + pos_h + 6                                    # top of the skip lane
    ya = pb + pos_h + (lane + 6 if lane else 0)            # bottom of everything above the time axis
    H = ya + mb
    x0, x1 = c["x0"], c["x1"]
    lo, hi = yrange(c)
    X = lambda t: pl + (t - x0) / (x1 - x0) * (pr - pl)  # noqa: E731
    Y = lambda v: pb - (v - lo) / (hi - lo) * (pb - pt)  # noqa: E731
    Xc = lambda t: min(max(X(t), pl), pr)  # noqa: E731
    sym, m = c["instrument"], c["market"]
    o = [f'<svg class="cv cv-{key}" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" role="img" '
         f'data-instrument="{e(sym)}" data-x0="{x0}" data-x1="{x1}" data-y0="{lo!r}" data-y1="{hi!r}" '
         f'data-plot="{pl},{pt},{pr},{pb}" aria-label="{e(sym)} handelschart, papir/simulation">',
         f'<rect class="bg" x="0" y="0" width="{W}" height="{H}"/>']
    # header band: symbol + price source (left), data cutoff (right) -- the chart says how fresh it is
    if m:
        src = (f"markPrice · census/1 · 1 t · {len(m['points'])} snapshots" if m["source"] == "census" else
               f"mark · k3/1 · {len(m['points'])} punkter")
        o.append(f'<text class="ttl" x="{pl + 2}" y="{fs + 12}" font-size="{fs + 6}">{e(sym)}</text>'
                 f'<text class="src" x="{pl + 2 + (len(sym) + 1) * (fs + 6) * 0.62:.1f}" y="{fs + 12}" '
                 f'font-size="{fs - 1}">{e(src)} · tider i UTC</text>')
    else:
        o.append(f'<text class="ttl" x="{pl + 2}" y="{fs + 12}" font-size="{fs + 6}">{e(sym)}</text>'
                 f'<text class="src none" x="{pl + 2 + (len(sym) + 1) * (fs + 6) * 0.62:.1f}" y="{fs + 12}" '
                 f'font-size="{fs - 1}">KUN HANDELSPRISER — ingen registreret markedskurs</text>')
    o.append(f'<text class="upd" x="{W - 8}" y="{fs + 8}" text-anchor="end" font-size="{fs - 1}">Data til '
             f'{e(utc(c["cutoff"], "%Y-%m-%d %H:%M"))}</text>')
    if m:
        lt = m["points"][-1][0]
        o.append(f'<text class="upd2" x="{W - 8}" y="{2 * fs + 12}" text-anchor="end" font-size="{fs - 3}">seneste '
                 f'prispunkt {e(utc(lt, "%m-%d %H:%M"))} ({dur(max(c["cutoff"] - lt, 0))} før cutoff)</text>')
    o.append(f'<text class="wm" x="{(pl + pr) / 2:.1f}" y="{(pt + pb) / 2 + fs:.1f}" text-anchor="middle" '
             f'font-size="{max(28, int((pr - pl) / 9))}">{e(sym)}</text>')
    o.append(f'<text class="wp" x="{pl + 6}" y="{pt + fs + 2}" font-size="{fs - 3}">PAPER / SIMULATION</text>')
    # y grid + right price axis
    step = nice((hi - lo) / yt)
    dec = decimals(step)
    v = math.ceil(lo / step) * step
    while v <= hi + 1e-12:
        y = Y(v)
        o.append(f'<line class="grd" x1="{pl}" x2="{pr}" y1="{y:.2f}" y2="{y:.2f}"/>')
        o.append(f'<text class="tk" x="{pr + 7}" y="{y + fs * 0.35:.2f}" font-size="{fs}">{v:,.{dec}f}</text>')
        v += step
    # x grid + time axis (UTC); a brighter line at each UTC midnight
    span = x1 - x0
    tstep = next((s for s in TIME_STEPS if span / s <= xt), TIME_STEPS[-1])
    t = (x0 // tstep + 1) * tstep
    last_day, k = None, 0
    while t < x1:
        x = X(t)
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
        mid = d.hour == 0 and d.minute == 0
        o.append(f'<line class="grd{" day" if mid else ""}" x1="{x:.2f}" x2="{x:.2f}" y1="{pt}" y2="{ya}"/>')
        lab = f"{d:%m-%d}" if tstep >= 86400 else f"{d:%H:%M}"
        if x <= pr - 2.2 * fs:                             # no label under the "UTC" tag at the right edge
            o.append(f'<text class="tk{" xo" if k % 2 else ""}" x="{x:.2f}" y="{ya + fs + 8}" text-anchor="middle" '
                     f'font-size="{fs}">{lab}</text>')
        k += 1
        if tstep < 86400 and d.date() != last_day and (mid or last_day is None):
            o.append(f'<text class="tk dt" x="{x:.2f}" y="{ya + 2 * fs + 12}" text-anchor="middle" '
                     f'font-size="{fs}">{d:%m-%d}</text>')
        last_day = d.date()
        t += tstep
    o.append(f'<text class="tk" x="{pr + 7}" y="{ya + fs + 8}" font-size="{fs - 1}">UTC</text>')
    o.append(f'<line class="axl" x1="{pl}" x2="{pr}" y1="{pb}" y2="{pb}"/>'
             f'<line class="axl" x1="{pr}" x2="{pr}" y1="{pt}" y2="{pb}"/>')
    # gaps layer (bands + labels); the line itself is broken regardless of this layer
    if m:
        g = ['<g class="hl-gaps">']
        for a, b in m["gaps"] + m["edge_gaps"]:
            xa, xb = Xc(a), Xc(b)
            g.append(f'<rect class="gap" x="{xa:.2f}" y="{pt}" width="{max(xb - xa, 0.5):.2f}" height="{pb - pt}">'
                     f'<title>Hul i markedsdata: {e(utc(a, "%m-%d %H:%M:%S"))} – {e(utc(b, "%m-%d %H:%M:%S"))} '
                     f'({dur(b - a)}); linjen er brudt, ikke interpoleret</title></rect>')
            if xb - xa > 9 * fs:
                g.append(f'<text class="gapt" x="{(xa + xb) / 2:.1f}" y="{pb - 8}" text-anchor="middle" '
                         f'font-size="{fs - 2}">ingen markedsdata</text>')
        o.append("".join(g) + "</g>")
    # positions layer: boxes in the price area, entry->exit connectors, lanes per book, entry (gns.) lines
    g = ['<g class="hl-pos">']
    boxes = collections.OrderedDict()
    for tr in c["trades"]:
        xa = Xc(tr["start"])
        xb = Xc(tr["end"] if tr["end"] is not None else c["cutoff"])
        ya_, yb_ = Y(tr["basis"]), Y(tr["exit"] if tr["exit"] is not None else tr["basis"])
        k_ = (round(xa, 1), round(xb, 1), tr["end"] is None)     # same period (e.g. mirrored books): one box
        boxes.setdefault(k_, []).append((tr, xa, xb, ya_, yb_))
    for grp in boxes.values():
        tr, xa, xb, ya_, yb_ = grp[0]
        ys_ = [v for _, _, _, a_, b_ in grp for v in (a_, b_)]
        top, h = min(ys_), max(max(ys_) - min(ys_), 3.0)
        if tr["end"] is None:
            top -= 1.5
        kinds = {"open" if t["end"] is None else ("win" if t["net"] > 0 else "loss") for t, *_ in grp}
        cls = kinds.pop() if len(kinds) == 1 else "mixed"
        title = "\n".join(trade_title(t, sym, names, c["cutoff"]) for t, *_ in grp)
        g.append(f'<rect class="pbox {cls}" data-ledger="{e(",".join(t["ledger"] for t, *_ in grp))}" '
                 f'data-t0="{tr["start"]}" data-t1="{tr["end"] if tr["end"] is not None else ""}" x="{xa:.2f}" '
                 f'y="{top:.2f}" width="{max(xb - xa, 1.5):.2f}" height="{h:.2f}"><title>{e(title)}</title></rect>')
        if tr["end"] is not None:
            g.append(f'<line class="pcon" x1="{xa:.2f}" y1="{ya_:.2f}" x2="{xb:.2f}" y2="{yb_:.2f}"/>')
    if c["trades"]:
        for i, led in enumerate(bots):
            ly = yp + i * (POS_LANE + POS_GAP)
            g.append(f'<rect class="plane" x="{pl}" y="{ly}" width="{pr - pl}" height="{POS_LANE}"/>'
                     f'<text class="plt" x="{pr + 7}" y="{ly + POS_LANE * 0.78:.1f}" font-size="{fs - 3}">'
                     f'{e(names.get(led, led))}</text>')
            for tr in (x for x in c["trades"] if x["ledger"] == led):
                xa = Xc(tr["start"])
                xb = Xc(tr["end"] if tr["end"] is not None else c["cutoff"])
                g.append(f'<rect class="pbar {tr["dir"]}{" open" if tr["end"] is None else ""}" '
                         f'data-t0="{tr["start"]}" x="{xa:.2f}" y="{ly + 2}" width="{max(xb - xa, 2):.2f}" '
                         f'height="{POS_LANE - 4}" rx="2"><title>{e(trade_title(tr, sym, names, c["cutoff"]))}'
                         f'</title></rect>')
                lbl = ("åben" if tr["end"] is None else f'{tr["net"]:+,.2f}')
                if xb - xa > (len(lbl) + 2) * (fs - 4) * 0.62:
                    g.append(f'<text class="pres" x="{xa + 4:.2f}" y="{ly + POS_LANE * 0.74:.1f}" '
                             f'font-size="{fs - 4}">{e(lbl)}</text>')
    labs = []
    for en in c["entries"]:
        y = Y(en["px"])
        g.append(f'<line class="entry {en["dir"]}" x1="{pl}" x2="{pr}" y1="{y:.2f}" y2="{y:.2f}" '
                 f'data-px="{en["px"]!r}"><title>Entry (gns.) {e(num(en["px"]))} · {e(names.get(en["ledger"]))} '
                 f'{en["dir"].upper()} {abs(en["qty"]):.6g} (net_report open_basis)</title></line>')
        labs.append([y, en])
    labs.sort(key=lambda a: a[0])
    gap_px = fs * 1.9
    for i in range(1, len(labs)):
        if labs[i][0] - labs[i - 1][0] < gap_px:
            labs[i][0] = labs[i - 1][0] + gap_px
    for y, en in labs:
        bot = names.get(en["ledger"], en["ledger"])
        txt = f'Entry (gns.) {en["px"]:,.{dec + 2}f} · {bot} {en["dir"].upper()}'
        wdt = len(txt) * (fs - 1) * 0.62 + 10
        ly = min(max(y - fs * 0.9, pt + 2), pb - fs * 1.5)
        g.append(f'<g class="eg"><rect class="eb {en["dir"]}" x="{pl + 4}" y="{ly:.2f}" width="{wdt:.1f}" '
                 f'height="{fs * 1.45:.2f}" rx="3"/><text class="et" x="{pl + 9}" y="{ly + fs * 1.05:.2f}" '
                 f'font-size="{fs - 1}">{e(txt)}</text></g>')
    o.append("".join(g) + "</g>")
    # price line layer: broken polylines, census dots, last price tag
    if m:
        g = ['<g class="hl-line">']
        budget = max(int(pr - pl), 1)
        dots = m["source"] == "census" and len(m["points"]) <= MAX_DOTS
        for seg in m["segments"]:
            if len(seg) == 1 and not dots:
                g.append(f'<circle class="mkd" cx="{X(seg[0][0]):.2f}" cy="{Y(seg[0][1]):.2f}" r="1.8"/>')
                continue
            if len(seg) > 1:
                g.append(f'<polyline class="mkt" data-t0="{seg[0][0]}" data-t1="{seg[-1][0]}" points="'
                         + " ".join(f"{X(a):.2f},{Y(b):.2f}" for a, b in thin(seg, X, len(m["points"]) > 2 * budget))
                         + '"/>')
        if dots:
            for a, b in m["points"]:
                g.append(f'<circle class="mkp" cx="{X(a):.2f}" cy="{Y(b):.2f}" r="2.2"><title>{e(utc(a))} · '
                         f'markPrice {e(num(b))}</title></circle>')
        lt, lv = m["points"][-1]
        yl = Y(lv)
        g.append(f'<g class="lastg"><rect class="last" x="{pr + 1}" y="{yl - fs * 0.8:.2f}" width="{mr - 3}" '
                 f'height="{fs * 1.6:.2f}" rx="3"><title>Seneste mark {e(num(lv))} ({e(utc(lt))})</title></rect>'
                 f'<text class="lastt" x="{pr + 6}" y="{yl + fs * 0.35:.2f}" font-size="{fs}">{lv:,.{dec}f}</text></g>')
        o.append("".join(g) + "</g>")
    # cutoff line ("nu" for the snapshot)
    xc = X(c["cutoff"])
    o.append(f'<line class="cut" x1="{xc:.2f}" x2="{xc:.2f}" y1="{pt}" y2="{ya}"><title>Cutoff {e(utc(c["cutoff"]))}'
             f'</title></line><text class="cutt" x="{xc - 4:.2f}" y="{pt + fs}" text-anchor="end" '
             f'font-size="{fs - 2}">cutoff</text>')
    # funding settlement prices: small discrete diamonds
    g = ['<g class="hl-fund">']
    for f in c["funding"]:
        x, y = X(f["ts"]), Y(f["px"])
        s = ms * 0.6
        rate = (" · rate " + ", ".join(f"{r * 100:.4f} %" for r in f["rates"])) if f["rates"] else ""
        g.append(f'<path class="mk fund" data-ts="{f["ts"]}" data-px="{f["px"]!r}" d="M{x:.2f} {y - s:.2f}L{x + s:.2f} '
                 f'{y:.2f}L{x:.2f} {y + s:.2f}L{x - s:.2f} {y:.2f}Z"><title>{e(utc(f["ts"]))} · {FUND_LABEL} '
                 f'{e(num(f["px"]))} · ' + e(", ".join(sorted(names.get(x_, x_) for x_ in f["ledgers"]))) + e(rate)
                 + '</title></path>')
    o.append("".join(g) + "</g>")
    # fills (KØB / SÆLG); a fill that closes a trade carries the result after fees
    closes = {t["exit_fill"]: t for t in c["trades"] if t["exit_fill"] is not None}
    g = ['<g class="hl-trades">']
    for f in c["fills"]:
        x, y = X(f["ts"]), Y(f["px"])
        up = f["side"] == "buy"
        tr = closes.get(f["id"])
        res = (f' · lukker {tr["dir"].upper()}: resultat efter gebyrer {usd(tr["net"])}' if tr else "")
        g.append(f'<path class="mk {f["side"]}" data-ts="{f["ts"]}" data-px="{f["px"]!r}" d="{tri(x, y, ms, up)}">'
                 f'<title>{e(utc(f["ts"]))} · {e(names.get(f["ledger"], f["ledger"]))} · '
                 f'{"KØB" if up else "SÆLG"} {e(sym)} · {f["qty"]:.6g} @ {e(num(f["px"]))} · '
                 f'gebyr {abs(f["fee"]):.4f}{e(res)}</title></path>')
    o.append("".join(g) + "</g>")
    # skip lane (no price): grey markers by time only
    if lane:
        g = ['<g class="hl-skip">']
        g.append(f'<rect class="lane" x="{pl}" y="{ys}" width="{pr - pl}" height="{lane}"/>'
                 f'<text class="lanet" x="{pr + 7}" y="{ys + lane / 2 + fs * 0.35:.1f}" font-size="{fs - 3}">'
                 f'Spring over</text>')
        for s in c["skips"]:
            g.append(f'<circle class="mk skip" data-ts="{s["ts"]}" cx="{X(s["ts"]):.2f}" cy="{ys + lane / 2:.1f}" '
                     f'r="{ms * 0.6:.1f}"><title>{e(utc(s["ts"]))} · {e(names.get(s["ledger"], s["ledger"]))} · '
                     f'SPRUNGET OVER {e(sym)} · {e(s["kind"])}: {e(s["reason"][:200])}</title></circle>')
        o.append("".join(g) + "</g>")
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
              "trades": '<path d="M5 1L1 8L9 8Z" fill="#16c784"/><path d="M13 11L9 4L17 4Z" fill="#ff4d5e"/>',
              "line": '<path d="M1 9L6 4L11 7L17 2" fill="none" stroke="#4aa3f0" stroke-width="2"/>',
              "gaps": '<rect x="1" y="1" width="16" height="10" fill="#ffffff" fill-opacity=".06" stroke="#3b465c" '
                      'stroke-dasharray="2 2"/>',
              "fund": '<path d="M9 2L13 6L9 10L5 6Z" fill="#0e131d" stroke="#f2b33d" stroke-width="1.6"/>',
              "skip": '<circle cx="9" cy="6" r="4" fill="#8b95a7"/>',
              "pos": '<rect x="1" y="2" width="16" height="8" fill="#16c784" fill-opacity=".25" stroke="#16c784"/>',
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
    lab = CENSUS_LABEL if m and m["source"] == "census" else MARKET_LABEL
    kind = (f'<span class="ch-kind k-mkt">{e(lab)} + handler</span>' if m else
            f'<span class="ch-kind k-fill">{e(FILL_ONLY)}</span>')
    hm = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%m-%d %H:%M")  # noqa: E731
    win = (f'seneste 7 d: {hm(c["w0"])} – {e(utc(c["cutoff"], "%m-%d %H:%M"))}; '
           f'{c["hidden"]} ældre fyld ikke vist' if c["long"] else
           f'alle handler til cutoff: {hm(c["w0"])} – {e(utc(c["cutoff"], "%m-%d %H:%M"))}')
    upd = f'<span class="ch-upd">Data til cutoff <b>{e(utc(c["cutoff"]))}</b>'
    if m:
        lt = m["points"][-1][0]
        upd += f' · seneste prispunkt {e(utc(lt, "%m-%d %H:%M"))}'
    upd += "</span>"
    closed = [t for t in c["trades"] if t["end"] is not None]
    opened = len(c["trades"]) - len(closed)
    gaps = (len(m["gaps"]) + len(m["edge_gaps"])) if m else 0
    o = [f'<article class="chart ch-{ident(sym)}" data-instrument="{e(sym)}">',
         f'<div class="ch-head"><span class="ch-sym">{e(sym)}</span><span class="ch-paper">PAPER / SIMULATION</span>'
         f'{kind}{upd}<span class="ch-bots">Bøger: {bots}</span></div>',
         '<div class="ch-body"><div class="ch-plot">' + "".join(svg(c, names, v) for v in VARIANTS) + "</div>",
         '<aside class="ch-side"><h3>Lag</h3><div class="ch-lyrs">']
    sub = {"line": ("markPrice · census/1 · 1 t" if m and m["source"] == "census" else
                    "mark · k3/1" if m else "ingen serie — kun handelspriser"),
           "trades": f"{nb} køb / {ns} salg (fyldpris)",
           "pos": f"{len(closed)} lukkede · {opened} åbne · bånd pr. bog",
           "fund": "afregningspris (sim_funding.price)",
           "gaps": (f"brudt ved > {c['market']['thr'] / 60:.0f} min" if m else "ingen prisserie"),
           "skip": "kun med instrument i payload"}
    cnt = {"line": len(m["points"]) if m else 0, "trades": len(c["fills"]), "pos": len(c["trades"]),
           "fund": len(c["funding"]), "gaps": gaps, "skip": len(c["skips"])}
    for name, (label, _) in LAYERS.items():
        o.append(f'<label class="lyr" for="hl-{name}"><span class="bx"></span><span>{legend_icon(name)}{e(label)}'
                 f'<small>{e(sub[name])}</small></span><span class="c">{cnt[name]}</span></label>')
    o.append("</div>")
    o.append(f'<div class="ch-meta"><span>Vindue: <b>{win}</b></span><span>Fyld i vinduet: <b>{len(c["fills"])}</b> '
             f'({nb} køb / {ns} salg)' + (f'; fordelt på {pts} tidspunkter, fyld på samme tidspunkt ligger oven i '
                                          f'hinanden' if pts < len(c["fills"]) else "") + '</span>')
    if m:
        o.append(f'<span>Markedspunkter: <b>{len(m["points"])}</b> i {len(m["segments"])} segmenter, '
                 f'{gaps} huller</span>')
    if closed:
        tot = sum(t["net"] for t in closed)
        o.append(f'<span>Lukkede handler i vinduet: <b>{len(closed)}</b>, resultat efter gebyrer <b>{e(usd(tot))}</b> '
                 f'(funding ikke medregnet)</span>')
    if c["trades"]:
        o.append("<span>Positionsbånd oppefra: " + ", ".join(e(names.get(b, b)) for b in c["bots"]) + "</span>")
    if c["funding"]:
        o.append(f'<span>{FUND_LABEL}er: <b>{len(c["funding"])}</b></span>')
    if c["skips"]:
        o.append(f'<span>Sprunget over: <b>{len(c["skips"])}</b></span>')
    o.append("</div>")
    notes = []
    if m and m["source"] == "census":
        notes.append(f'<b>Prislinje</b>: markPrice for {e(sym)} fra den timevise census af Binance USDⓈ-M-perps '
                     f'(observations, census/1 snapshot), kun fra bøgernes start '
                     f'({e(utc(c["series_from"], "%m-%d %H:%M"))}) til cutoff. Hvert punkt er et registreret snapshot; '
                     f'linjen brydes, hvor der er mere end {CENSUS_GAP_S // 60} min mellem to snapshots, og '
                     f'interpoleres aldrig ud over det.')
    elif m:
        notes.append(f'<b>Markedskurs</b>: registrerede mark-observationer (observations, metric=mark) for {e(sym)}. '
                     f'Medianafstand {m["median"]:.0f} s; linjen brydes ved huller over {GAP_FACTOR}× medianen '
                     f'({m["thr"] / 60:.1f} min) og interpoleres aldrig. Handelsmarkørerne er en separat serie.')
    else:
        notes.append(f'<b>{e(FILL_ONLY)}</b>: der findes ingen registreret markedskursserie for {e(sym)}; markørerne '
                     f'er papirfyldpriser og forbindes ikke med en linje.')
    notes.append("<b>Positioner</b>: én kasse pr. handel fra indgang til udgang (åben: til cutoff) mellem gns. "
                 "indgangs- og udgangspris; grøn = gevinst, rød = tab efter gebyrer, lilla stiplet = åben, lilla = "
                 "bøger med samme handel og modsat resultat (fx STRAKS-FØLG/MOD). Båndene under grafen viser hver "
                 "bogs retning (grøn = long, rød = short) og resultatet efter gebyrer.")
    if c["funding"]:
        notes.append(f"<b>{FUND_LABEL}</b> (sim_funding.price) er enkeltpunkter ved hver afregning, ikke en kurve.")
    if c["entries"]:
        notes.append("<b>Entry (gns.)</b> = net_report's gennemsnitlige indgangspris for den åbne position ved cutoff "
                     "(open_basis); ingen ny P&amp;L beregnes her.")
    if c["undocumented"]:
        notes.append("Ingen entry-linje for " + ", ".join(e(names.get(x, x)) for x in c["undocumented"])
                     + ": positionen vendte gennem nul uden at være flad, så gennemsnittet er ikke dokumenteret.")
    notes.append("Hold musen over en markør eller kasse for tid, side, mængde @ pris, gebyr og resultat. Kun visning: "
                 "ingen ordrer.")
    o.append("</aside>")
    o.append('<div class="ch-notes">' + "".join(f"<p>{n}</p>" for n in notes) + "</div></div></article>")
    return "\n".join(o)


def section(con, rep, cutoff, names, skip_kinds):
    """(inputs, css, html) of the HANDELSCHART section; the radios and layer checkboxes go before .wrap like the
    other filters."""
    charts, rest = collect(con, rep, int(cutoff), names, skip_kinds)
    ids = [ident(c["instrument"]) for c in charts]
    radios = "".join(f'<input class="f" type="radio" name="fc" id="fc-{i}"{" checked" if k == 0 else ""}>'
                     for k, i in enumerate(ids))
    if charts:
        radios += "".join(f'<input class="f" type="checkbox" id="hl-{n}" checked>' for n in LAYERS)
    on = "{background:var(--acc);color:#fff;border-color:var(--acc)}"
    css = [CSS] + [f"#fc-{i}:checked~.wrap label[for=fc-{i}]{on}#fc-{i}:checked~.wrap .ch-{i}{{display:block}}"
                   for i in ids]
    if charts:
        css += [f"#hl-{n}:not(:checked)~.wrap .hl-{n}{{display:none}}"
                f"#hl-{n}:checked~.wrap label[for=hl-{n}] .bx{{background:{col};border-color:{col}}}"
                f"#hl-{n}:not(:checked)~.wrap label[for=hl-{n}]{{opacity:.5}}" for n, (_, col) in LAYERS.items()]
    o = ['<section class="hc" id="handelschart">',
         '<h2>Handelschart <small>· kun visning af registrerede papirhandler for FRESH-bøgerne · ét instrument pr. '
         'graf · lag slås til og fra i panelet · ingen ordrer fra grafen</small></h2>']
    if not charts:
        o.append('<div class="hc-none">Ingen handelschart: ingen FRESH-papirbøger med fyld til cutoff.</div>')
    else:
        o.append('<div class="hc-tabs" aria-label="vælg instrument">' + "".join(
            f'<label class="hc-tab" for="fc-{i}">{e(c["instrument"])}<small>{c["fills_total"]} fyld</small>'
            f'<i class="{"p-on" if c["market"] else "p-off"}" title="'
            f'{"prislinje" if c["market"] else "kun handelspriser"}"></i></label>'
            for i, c in zip(ids, charts)) + "</div>")
        o.extend(card(c, names) for c in charts)
        if rest:
            o.append(f'<p class="hc-rest">Ikke vist (maks. {MAX_CHARTS} grafer, flest fyld først): '
                     + ", ".join(f"{e(s)} ({n})" for s, n in rest) + ".</p>")
    o.append("</section>")
    return radios, "\n".join(css), "\n".join(o)
