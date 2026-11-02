"""MISSION27_3 point 12b: a descriptive first look at hlcensus/1 (PROTOCOL_V3 amendment 38 A). No hypothesis; nothing
decides.

  python3 research/tools/hlcensus_look.py run [--db PATH]   refuses below 48 snapshots (earliest ~2026-11-04 15:00 UTC)

Written 2026-11-02 before any hlcensus/1 value was read (only the snapshot count and timestamps were seen). Measures,
as fixed in point 12b:
  1. universe size per hour, isDelisted count, names added/removed between consecutive snapshots;
  2. names only on Hyperliquid (no census/1 perp in the same hour after the k-prefix is dropped), and how many are
     liquid (dayNtlVlm >= 5 million USD);
  3. annualised hourly funding (rate * 24 * 365): median, 10th and 90th percentile for liquid HL-only names vs liquid
     shared names, pooled over all hours;
  4. openInterest concentration: the top 10 names' share of total OI notional (openInterest * markPx), median over hours.
Not a perp-perp spread (amendment 13a point 2 lost and is not repeated).
"""
import json
import os
import sqlite3
import statistics as st
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(HERE, "data", "lab", "lab.db")
MIN_SNAPSHOTS = 48
LIQUID_USD = 5e6
YEAR_H = 24 * 365


def base(name):
    """Hyperliquid's k-prefixed names (kPEPE = 1000 PEPE) map to the bare ticker; others are unchanged."""
    return name[1:] if len(name) > 1 and name[0] == "k" and name[1:].isupper() else name


def on_binance(name, symbols):
    b = base(name)
    return any(s in symbols for s in (b + "USDT", "1000" + b + "USDT", "1000000" + b + "USDT"))


def _q(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarise(snaps):
    """snaps: chronological [(ts, {columns, rows}, census_symbols or None)] -> the four point-12b measures."""
    sizes, delisted, added, removed, only_n, only_liq = [], [], [], [], [], []
    f_only, f_shared, top10 = [], [], []
    prev = None
    for ts, snap, symbols in snaps:
        cols = snap["columns"]
        ix = {c: cols.index(c) for c in ("funding", "markPx", "openInterest", "dayNtlVlm", "isDelisted")}
        rows = snap["rows"]
        names = set(rows)
        sizes.append(len(names))
        delisted.append(sum(1 for r in rows.values() if r[ix["isDelisted"]] == 1.0))
        if prev is not None:
            added.append(len(names - prev))
            removed.append(len(prev - names))
        prev = names
        notional = []
        hour_only = hour_liq = 0
        for name, r in rows.items():
            mark, oi, vol, fr = r[ix["markPx"]], r[ix["openInterest"]], r[ix["dayNtlVlm"]], r[ix["funding"]]
            if mark is not None and oi is not None:
                notional.append(mark * oi)
            if symbols is None:
                continue
            liquid = vol is not None and vol >= LIQUID_USD
            only = not on_binance(name, symbols)
            hour_only += only
            hour_liq += only and liquid
            if liquid and fr is not None:
                (f_only if only else f_shared).append(fr * YEAR_H)
        if symbols is not None:
            only_n.append(hour_only)
            only_liq.append(hour_liq)
        tot = sum(notional)
        if tot > 0:
            top10.append(sum(sorted(notional, reverse=True)[:10]) / tot)

    def dist(xs):
        return {"n": len(xs), "p10": _q(xs, 0.1), "median": _q(xs, 0.5), "p90": _q(xs, 0.9)}

    def med(xs):
        return st.median(xs) if xs else None

    return {"snapshots": len(snaps), "hours_with_census": len(only_n),
            "universe": {"median": med(sizes), "min": min(sizes, default=None), "max": max(sizes, default=None)},
            "delisted_median": med(delisted), "added_total": sum(added), "removed_total": sum(removed),
            "hl_only_median": med(only_n), "hl_only_liquid_median": med(only_liq),
            "funding_apr_liquid_hl_only": dist(f_only), "funding_apr_liquid_shared": dist(f_shared),
            "oi_top10_share_median": med(top10),
            "label": "beskrivende; ingen hypotese; afgør intet (MISSION27_3 punkt 12b)"}


def load(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out = []
    for ts, payload in con.execute("SELECT ts, payload FROM observations WHERE detector='hlcensus/1' "
                                   "AND metric='snapshot' ORDER BY ts"):
        hour = ts - ts % 3600
        c = con.execute("SELECT payload FROM observations WHERE detector='census/1' AND metric='snapshot' "
                        "AND ts>=? AND ts<? ORDER BY ts LIMIT 1", (hour, hour + 3600)).fetchone()
        out.append((ts, json.loads(payload), set(json.loads(c[0])["rows"]) if c else None))
    return out


def count(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    return con.execute("SELECT COUNT(*) FROM observations WHERE detector='hlcensus/1' AND metric='snapshot'").fetchone()[0]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ["run"]:
        print("usage: hlcensus_look.py run [--db PATH]")
        return
    path = argv[argv.index("--db") + 1] if "--db" in argv else DB
    n = count(path)
    if n < MIN_SNAPSHOTS:
        print(json.dumps({"refused": f"{n} snapshots < {MIN_SNAPSHOTS} (MISSION27_3 point 12b)"}))
        return
    print(json.dumps(summarise(load(path)), indent=1))


if __name__ == "__main__":
    main()
