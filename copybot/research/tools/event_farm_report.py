"""Event farm forward paper book: the descriptive day-N report (PROTOCOL_V3 amendment 46, text 104 section 6).

Reports after 14, 28 and 90 days, labelled PAPIR / SIMULERING whatever the outcome:
- primary: frequencies, status shares, fill uncertainty (share of trades with a bar hitting both stop and target, share
  filled on touch only), coverage, gaps, revisions, F3 blocks and the call log's errors;
- appendix: R gross and net per test in register order, no ranking, with the filter null seed 83 side by side.

The book file and the call log are opened read-only (farm_dashboard.read_forward, event_farm_source.verify_log); nothing
in ~/event_farm is written. Before day N has passed since the book's first bar the report is refused unless --preview,
which writes a page marked FORHÅNDSVISNING.

    python3 -m research.tools.event_farm_report --day 14
    python3 -m research.tools.event_farm_report --day 14 --preview --out /tmp/x.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import farm_dashboard as fd  # noqa: E402

DAYS = (14, 28, 90)
DEFAULT_DB = "~/event_farm/event_farm_forward.db"
DEFAULT_CALLS = "~/event_farm/event_farm_source_calls.jsonl"
LABEL = "PAPIR / SIMULERING — beskrivende; ingen rigtige penge; ingen evidens for en fordel"
CLOSING = ("**To uger er ingen dokumentation.** At påvise +0,1 R ved N = 19.849 med 80 % styrke kræver ca. 2.900 handler "
           "pr. test. En påstand kræver en ny, låst, bekræftende protokol (ændring 46 afsnit 6). Observationerne bruges "
           "ikke til at vælge eller kalibrere en ny hypotese (G05).")


class TooEarly(Exception):
    pass


def utc(ts):
    return "–" if ts is None else dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def pct(a, b):
    return "–" if not b else f"{100 * a / b:.1f} %"


def num(x, f="{:+.3f}"):
    return "–" if x is None else f.format(x)


def call_log_summary(path):
    """Counts from the append-only call log, read-only: lines, chain ok, status != 200, errors, rows delivered."""
    from research.tools import event_farm_source as src
    out = {"path": path, "lines": 0, "chain_ok": None, "non_200": 0, "errors": {}, "delivered": 0, "gaps": 0,
           "first_wall": None, "last_wall": None}
    if not path or not os.path.exists(path):
        return out
    try:
        src.verify_log(path)
        out["chain_ok"] = True
    except (src.LogBroken, ValueError) as ex:
        out["chain_ok"] = False
        out["chain_error"] = str(ex)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out["lines"] += 1
            if r.get("status") != 200:
                out["non_200"] += 1
            if r.get("error"):
                k = str(r["error"]).split(":")[0][:60]
                out["errors"][k] = out["errors"].get(k, 0) + 1
            out["delivered"] += int(r.get("delivered") or 0)
            out["gaps"] += int(r.get("gaps") or 0)
            w = r.get("wall_ts")
            if w is not None:
                out["first_wall"] = w if out["first_wall"] is None else min(out["first_wall"], w)
                out["last_wall"] = w if out["last_wall"] is None else max(out["last_wall"], w)
    return out


def elapsed_days(live, now):
    start = live["meta"].get("start_ts")
    return None if start is None else (now - int(start)) / 86400


def render(live, calls, day, now, preview=False):
    ident, rep, cfg = live["identity"], live["report"], live["identity"]["config"]
    tests = ident["tests"]
    null = live.get("null")
    start = live["meta"].get("start_ts")
    ed = elapsed_days(live, now)
    trades = live["trades"]
    taken = [t for t in trades if not t["status"].startswith("not_taken")]
    L = []
    title = f"# Event farm fremadrettet papirbog — rapport dag {day}"
    if preview:
        title += " (FORHÅNDSVISNING, ikke rapporten)"
    L += [title, "", f"**{LABEL}.**", "",
          f"Lavet {utc(now)} UTC af `research/tools/event_farm_report.py` (read-only). Bog `{live['path']}`, "
          f"første bar {utc(start)} UTC, {num(ed, '{:.2f}')} døgn forløbet, {live['steps']['n']} skridt med data. "
          f"Tilstand `{ident.get('mode')}`; IntegrityHalt: {live['halted'] or 'ingen'}.", ""]
    if preview:
        L += [f"> Forhåndsvisning før dag {day}: tallene er foreløbige og må ikke citeres som dag {day}-rapporten.", ""]

    # data quality
    L += ["## 1. Data og dækning", "",
          "| symbol | behandlede barer | slots | dækning | huller (antal / barer) | for sene | revisioner (i alt / "
          "behandlede / 24 t) | afviste | F3 blokeret (barer / døgn) | maks. bogføringsforsinkelse (s) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for s, d in rep["data"].items():
        S = live["symbols"][s]
        rej = ", ".join(f"{k} {v}" for k, v in d["rejected"].items()) or "0"
        L.append(f"| {s} | {d['processed']} | {d['slots']} | {pct(d['processed'], d['slots'])} | {d['gaps'][0]} / "
                 f"{d['gaps'][1]} | {d['late']} | {S['conflicts']} / {S['conflicts_processed']} / {S['conflicts_24h']} | "
                 f"{rej} | {S['f3_blocked_bars']} / {S['f3_blocked_days']} | {num(d['booking_delay_s_max'], '{:.0f}')} |")
    L += ["", f"Opvarmning: de første {cfg['warmup_bars']} barer pr. symbol; setups i den er `not_taken_warmup` og indgår "
          f"ikke ({sum(1 for t in trades if t['status'] == 'not_taken_warmup')} stk.).", ""]

    # call log
    c = calls
    chain = {True: "hel", False: f"BRUDT ({c.get('chain_error')})", None: "ikke fundet"}[c["chain_ok"]]
    errs = ", ".join(f"{k} {v}" for k, v in sorted(c["errors"].items())) or "ingen"
    L += ["## 2. Kald-loggen", "",
          f"`{c['path']}`: {c['lines']} kald ({utc(c['first_wall'])} → {utc(c['last_wall'])} UTC), kæde {chain}, "
          f"status ≠ 200: {c['non_200']}, fejl: {errs}, leverede lukkede barer {c['delivered']}, rapporterede huller "
          f"{c['gaps']}.", ""]

    # events
    L += ["## 3. Mærkede hændelser pr. instrument-døgn", "", "| hændelse | " + " | ".join(rep["events"]) + " |",
          "|---|" + "---|" * len(rep["events"])]
    kinds = sorted({k for v in rep["events"].values() for k in v})
    for k in kinds:
        L.append(f"| {k} | " + " | ".join(num(rep["events"][s].get(k), "{:.2f}") for s in rep["events"]) + " |")
    L.append("")

    # primary
    sym_days = sum(d["processed"] for d in rep["data"].values()) / 288 or None
    L += ["## 4. Primært: frekvenser, statusandele og fill-usikkerhed (registerorden, ingen rangordning)", "",
          f"{len(taken)} papirhandler taget i alt ({sum(1 for t in taken if t['status'] == 'pending')} åbne). Andele er "
          "af tagne handler; fill-usikkerhed er af lukkede handler uden hul.", "",
          "| test | setups / instr.-døgn | null | tagne | mål | stop | timeout | missed | no_fill | åbne | hul | "
          "både stop og mål | kun berøring |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for tid in tests:
        v = rep["variants"][tid]
        st = v["status"]
        n_all = sum(st.values())
        n_tk = sum(n for k, n in st.items() if not k.startswith("not_taken"))
        nf = "–" if null is None else f"{null['tests'][tid]['setups_per_instrument_day']:.2f}"
        per = "–" if not sym_days else f"{n_all / sym_days:.2f}"
        L.append(f"| {tid} | {per} | {nf} | {n_tk} | " + " | ".join(pct(st.get(k, 0), n_tk) for k in fd.FINAL_STATUSES)
                 + f" | {st.get('pending', 0)} | {v['gap_affected']} | {num(v['both_hit_share'], '{:.2f}')} | "
                 f"{num(v['touch_only_share'], '{:.2f}')} |")
    L.append("")

    # appendix
    grid = [f"{x:g}" for x in cfg["null_cost_grid_bps"]]
    L += ["## Bilag: R pr. test (registerorden, ingen rangordning)", "",
          "Brutto og netto R pr. lukket handel uden hul. Netto ved lab-modellen (28 bps rundtur er en ANTAGELSE) og ved "
          f"{'/'.join(grid)} bps; værste fald bogfører hul-handler som stop. Null = seed 83 med filtre, side om side.", "",
          "| test | lukkede | brutto R | netto R (lab) | " + " | ".join(f"netto @{g}" for g in grid) +
          " | værste fald | netto USDT | null handler | null brutto R | null netto @28 | "
          + " | ".join(f"null @{g}" for g in grid) + " |",
          "|---|---|---|---|" + "---|" * len(grid) + "---|---|---|---|---|" + "---|" * len(grid)]
    for tid in tests:
        v = rep["variants"][tid]
        nv = None if null is None else null["tests"][tid]
        L.append(f"| {tid} | {v['trades_clean']} | {num(v['mean_gross_r'])} | {num(v['mean_net_r_lab'])} | "
                 + " | ".join(num(v["mean_net_r_grid"].get(g)) for g in grid)
                 + f" | {num(v['worst_case_mean_net_r_lab'])} | {num(v['net_usdt_clean'], '{:+.2f}')} | "
                 + ("– | – | – | " + " | ".join("–" for _ in grid) if nv is None else
                    f"{nv['trades']} | {num(nv['mean_gross_r'])} | {num(nv['mean_net_r'].get('28'))} | "
                    + " | ".join(num(nv["mean_net_r"].get(g)) for g in grid)) + " |")
    L += ["", f"Konto pr. test {cfg['account_usdt']:,.0f} USDT, {cfg['notional_usdt']:,.0f} USDT notional pr. "
          f"papirhandel; en test med konto ≤ {cfg['account_stop_usdt']:,.0f} USDT tager ingen nye handler. Familie "
          f"{len(tests)} tests, reference-N {rep.get('reference_n')}.", "", CLOSING, ""]
    return "\n".join(L)


def build(day, db, calls_path, now=None, preview=False, null=None):
    if day not in DAYS:
        raise ValueError(f"dag {day} er ikke en rapportdag {DAYS}")
    now = time.time() if now is None else now
    live = fd.read_forward(db, null=null)
    if live["state"] != "ok":
        raise ValueError(f"bogen kan ikke læses: {live.get('reason') or live['state']}")
    ed = elapsed_days(live, now)
    if not preview and (ed is None or ed < day):
        raise TooEarly(f"dag {day} er ikke gået: {0 if ed is None else ed:.2f} døgn siden første bar (brug --preview)")
    return render(live, call_log_summary(calls_path), day, now, preview)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", type=int, required=True, choices=DAYS)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--calls", default=DEFAULT_CALLS)
    ap.add_argument("--out", default=None, help="default research/studies/EVENT_FARM_FORWARD_DAY<N>.md "
                                                "(a preview needs --out)")
    ap.add_argument("--preview", action="store_true", help="before day N: write a page marked FORHÅNDSVISNING")
    ap.add_argument("--cache", default=fd.DEFAULT_CACHE)
    a = ap.parse_args(argv)
    if a.preview and not a.out:
        raise SystemExit("--preview kræver --out (forhåndsvisningen skrives ikke i research/studies)")
    from research.tools import event_farm_filters as ff
    cache = os.path.expanduser(a.cache) if a.cache else None
    null = fd.cached(cache, "null", (83, fd.NULL_COSTS), lambda: ff.null_with_filters(seed=83, costs=fd.NULL_COSTS))
    try:
        doc = build(a.day, os.path.expanduser(a.db), os.path.expanduser(a.calls), preview=a.preview, null=null)
    except (ValueError, TooEarly) as ex:
        raise SystemExit(str(ex))
    out = a.out or os.path.join(HERE, "research", "studies", f"EVENT_FARM_FORWARD_DAY{a.day}.md")
    fd.write_atomic(os.path.expanduser(out), doc)
    print(f"{out}: {len(doc.encode())} bytes, dag {a.day}{' (forhåndsvisning)' if a.preview else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
