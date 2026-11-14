"""Funding extremes, historical development lab (PROTOCOL_V3 amendment 48, owner's choice 2026-11-14).

Hypothesis: when an 8h funding settlement is extreme against the previous 30 days (only settlements before it), the
leveraged side pays and price moves against it over the next hours. Control: the same rule with the crowd ('pro').

Data: price = 1h bars from the 44 amendment-47 files (event_farm_hist.load_bars, sha256 against R3_m24_verify);
funding = BTC/ETH monthly files 2020-02..2021-12, names and sha256 from the committed POST_HOC_IDENTITY manifest,
checked before opening (one difference = Refused). Rows outside the file's month are discarded and counted.

Time: settlement T is known at T. Entry at the close of the 1h bar T..T+1h (one hour later, conservative), exit at the
close H hours after the entry. No new entry in a symbol while a position is open. Cost 28 bps round trip.
DEV = entries and exits before 2021-07-01; CHECK = signals from 2021-07-01, sealed, logged before computing.

UDVIKLING / explore0 = udforskning, aldrig bevis. Kun papir og forskning.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import statistics
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import event_farm_hist as eh  # noqa: E402

MANIFEST = os.path.join(HERE, "research", "data", "event_farm_hist", "funding_identity_manifest.json")
FUNDING_DIR = "/home/anton/ecommerence/copybot/data/lab/market/funding"
LOG_DIR = eh.OUT_DIR
COST_BPS = 28.0
H1 = 3600
LOOKBACK_S = 30 * 86400
MIN_HISTORY = 60                                   # settlements in the lookback before a signal counts
PCTS = (0.90, 0.95, 1.0)                           # 1.0 = beyond every settlement of the previous 30 days
HOLDS = (4, 8, 24)
DIRS = ("contra", "pro")
LABEL = "UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir"
LABEL_CHECK = "KONTROL på explore0 (2021-07..2021-12) - forseglet periode, åbning logget; stadig udforskning"


class Refused(eh.Refused):
    pass


def funding_names(manifest_path=MANIFEST):
    with open(manifest_path, encoding="utf-8") as f:
        m = json.load(f)
    if m.get("kind") != "POST_HOC_IDENTITY" or m.get("missing"):
        raise Refused("funding manifest is not a complete POST_HOC_IDENTITY manifest")
    pat = eh.re.compile(r"^(BTCUSDT|ETHUSDT)-fundingRate-(2020-(0[2-9]|1[0-2])|2021-(0[1-9]|1[0-2]))\.zip$")
    files = m["files"]
    bad = [n for n in files if not pat.match(n)]
    if bad or len(files) != 46:
        raise Refused(f"funding manifest names outside BTC/ETH 2020-02..2021-12 or not 46 files: {bad[:3]}")
    return sorted((n, r["sha256"]) for n, r in files.items())


def month_bounds(name):
    y, mth = map(int, name[-11:-4].split("-"))                 # ...-YYYY-MM.zip
    lo = int(dt.datetime(y, mth, 1, tzinfo=dt.timezone.utc).timestamp())
    hi = int(dt.datetime(y + (mth == 12), mth % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
    return lo, hi


def load_funding(fdir=FUNDING_DIR, manifest_path=MANIFEST):
    """{symbol: [(settlement_ts, rate)]} sorted, and the discarded-row count. Every sha256 is checked first."""
    names = funding_names(manifest_path)
    bad = []
    for n, sha in names:
        p = os.path.join(fdir, n)
        if not os.path.isfile(p) or eh._sha(p) != sha:
            bad.append(n)
    if bad:
        raise Refused(f"funding identity differs (BLOCKED): {bad[:5]}")
    out, dropped = collections.defaultdict(dict), 0
    for n, _ in names:
        sym = n.split("-")[0]
        lo, hi = month_bounds(n)
        with zipfile.ZipFile(os.path.join(fdir, n)) as z:
            members = [m for m in z.namelist() if m.endswith(".csv")]
            if len(members) != 1:
                raise Refused(f"{n}: expected one csv")
            with z.open(members[0]) as fh:
                for r in csv.reader(io.TextIOWrapper(fh, encoding="ascii")):
                    if not r or not r[0].strip().isdigit():
                        dropped += 1
                        continue
                    t = int(r[0])
                    t = t // 1000 if t > 10 ** 11 else t
                    t = (t + 1800) // H1 * H1                     # calc_time can be a few ms off the hour
                    if not lo <= t < hi:
                        dropped += 1
                        continue
                    out[sym][t] = float(r[-1])
    return {s: sorted(v.items()) for s, v in out.items()}, dropped


def pct_rank(hist, x):
    """Share of hist strictly below x and share strictly above x."""
    hs = sorted(hist)
    return bisect.bisect_left(hs, x) / len(hs), (len(hs) - bisect.bisect_right(hs, x)) / len(hs)


def signals(fund, pct):
    """[(T, side)] with side +1 = extreme high funding (longs crowded), -1 = extreme low. Only earlier settlements."""
    out = []
    ts = [t for t, _ in fund]
    for i, (t, r) in enumerate(fund):
        j = bisect.bisect_left(ts, t - LOOKBACK_S)
        hist = [x for _, x in fund[j:i]]
        if len(hist) < MIN_HISTORY:
            continue
        below, above = pct_rank(hist, r)
        if pct >= 1.0:
            hi, lo = r > max(hist), r < min(hist)
        else:
            hi, lo = below >= pct, above >= pct
        if hi:
            out.append((t, 1))
        elif lo:
            out.append((t, -1))
    return out


def trades(bars1h, sigs, hold, direction, t_from, t_to):
    """Non-overlapping trades: entry close of bar T..T+1h, exit close `hold` hours later; both inside [t_from, t_to)."""
    idx = {b[0]: k for k, b in enumerate(bars1h)}
    out, busy_until = [], -1
    for t, side in sigs:
        if t < t_from or t <= busy_until:
            continue
        k = idx.get(t)
        if k is None or k + hold >= len(bars1h):
            continue
        k2 = k + hold
        if bars1h[k2][0] != t + hold * H1 or bars1h[k2][0] + H1 > t_to:
            continue
        d = -side if direction == "contra" else side
        gross = d * (bars1h[k2][4] / bars1h[k][4] - 1) * 1e4
        out.append({"t": t, "dir": d, "gross_bps": gross, "net_bps": gross - COST_BPS})
        busy_until = bars1h[k2][0]
    return out


def _t(xs):
    if len(xs) < 2 or statistics.stdev(xs) == 0:
        return None
    return statistics.fmean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs)))


def summarize(tr):
    g = [x["gross_bps"] for x in tr]
    n = [x["net_bps"] for x in tr]
    by = collections.defaultdict(list)
    for x in tr:
        d = dt.datetime.fromtimestamp(x["t"], dt.timezone.utc)
        for k in ("long" if x["dir"] > 0 else "short", x["sym"], f"{d.year}H{1 + (d.month > 6)}"):
            by[k].append(x["net_bps"])
    return {"trades": len(tr), "mean_gross_bps": statistics.fmean(g) if g else None,
            "mean_net_bps": statistics.fmean(n) if n else None, "t_net": _t(n),
            "win_share": (sum(1 for x in n if x > 0) / len(n)) if n else None,
            "by": {k: [len(v), statistics.fmean(v)] for k, v in sorted(by.items())}}


def run(bars1h_by_sym, fund_by_sym, part, pcts=PCTS, holds=HOLDS, dirs=DIRS):
    t_from, t_to = (eh.EXPLORE_START, eh.DEV_END) if part == "dev" else (eh.DEV_END, eh.EXPLORE_END)
    res, base = {}, {}
    sig_cache = {}
    for p in pcts:
        for h in holds:
            for d in dirs:
                tr = []
                for s in sorted(bars1h_by_sym):
                    key = (s, p)
                    if key not in sig_cache:
                        sig_cache[key] = signals(fund_by_sym[s], p)
                    for x in trades(bars1h_by_sym[s], sig_cache[key], h, d, t_from, t_to):
                        tr.append({**x, "sym": s})
                res[f"p{p:g}/h{h}/{d}"] = summarize(tr)
    for h in holds:                                  # reference: long at every settlement (the market's drift)
        tr = []
        for s in sorted(bars1h_by_sym):
            every = [(t, -1) for t, _ in fund_by_sym[s]]          # side -1 + contra = long
            tr += [{**x, "sym": s} for x in trades(bars1h_by_sym[s], every, h, "contra", t_from, t_to)]
        base[f"h{h}"] = summarize(tr)
    return res, base


def markdown(res, base, part, info, trials, note=""):
    L = [f"# Funding-ekstremer, historisk lab: {part.upper()}", "",
         f"**{LABEL_CHECK if part == 'check' else LABEL}**", "",
         "Regel: afregning ekstrem mod de forrige 30 dage (p = andel af historikken, den slår; p1 = ny 30-dages top/bund). "
         "contra = imod flokken (høj funding → short), pro = med flokken. Indgang 1 time efter afregningen, hold h timer, "
         f"ingen overlap pr. symbol. Omkostning {COST_BPS:g} bps rundtur. BTCUSDT+ETHUSDT.", "",
         f"Data: pris {info['price_files']} filer (sha256 mod R3_m24_verify), funding {info['funding_files']} filer "
         f"(POST_HOC_IDENTITY), {info['funding_rows_discarded']} funding-rækker kasseret uden for måned.", "",
         f"Udviklingskørsler i alt (inkl. denne): {trials[0]} kørsler, {trials[1]} tests.", ""]
    if note:
        L += [note, ""]
    L += ["| test | handler | brutto bps | netto bps | t (netto) | andel > 0 | long | short | BTC | ETH | "
          "2020H1 | 2020H2 | 2021H1 | 2021H2 |", "|" + "---|" * 14]
    keys = ("long", "short", "BTCUSDT", "ETHUSDT", "2020H1", "2020H2", "2021H1", "2021H2")
    f = eh.fmt
    for tid, r in res.items():
        L.append(f"| {tid} | {r['trades']} | {f(r['mean_gross_bps'], '{:+.1f}')} | {f(r['mean_net_bps'], '{:+.1f}')} | "
                 f"{f(r['t_net'], '{:+.2f}')} | {f(r['win_share'], '{:.2f}')} | " +
                 " | ".join(f"{r['by'][k][0]} / {r['by'][k][1]:+.0f}" if k in r["by"] else "–" for k in keys) + " |")
    L += ["", "Reference: long ved hver afregning (markedets drift i perioden, samme hold og omkostning):", "",
          "| hold | handler | brutto bps | netto bps |", "|---|---|---|---|"]
    for h, r in base.items():
        L.append(f"| {h} | {r['trades']} | {f(r['mean_gross_bps'], '{:+.1f}')} | {f(r['mean_net_bps'], '{:+.1f}')} |")
    L += ["", "Beskrivende; ingen rangering er en anbefaling. Tallene i long/short/symbol/halvår er antal / gns. netto bps."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="funding extremes historical lab (PROTOCOL_V3 amendment 48)")
    ap.add_argument("--pcts", default=",".join(f"{p:g}" for p in PCTS))
    ap.add_argument("--holds", default=",".join(map(str, HOLDS)))
    ap.add_argument("--dirs", default=",".join(DIRS))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--reason", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--cache", default=eh.CACHE)
    ap.add_argument("--verify", default=eh.VERIFY)
    ap.add_argument("--funding-dir", default=FUNDING_DIR)
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--log-dir", default=LOG_DIR)
    ap.add_argument("--work", default=eh.WORK)
    a = ap.parse_args(argv)
    pcts = tuple(float(x) for x in a.pcts.split(","))
    holds = tuple(int(x) for x in a.holds.split(","))
    dirs = tuple(a.dirs.split(","))
    if any(d not in DIRS for d in dirs) or any(not 0.5 <= p <= 1.0 for p in pcts) or any(h < 1 for h in holds):
        raise SystemExit("bad --pcts/--holds/--dirs")
    part = "check" if a.check else "dev"
    cfg = {"pcts": pcts, "holds": holds, "dirs": dirs}
    csha = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    if part == "check":
        if not a.reason:
            raise SystemExit("--check needs --reason")
        eh.append_log(os.path.join(a.log_dir, "funding_check_openings.jsonl"),
                      {"ts": round(time.time(), 1), "config_sha": csha, **cfg, "reason": a.reason})
    bars, info5 = eh.load_bars(a.cache, a.verify, a.work or None)
    fund, dropped = load_funding(a.funding_dir, a.manifest)
    bars1h = {s: eh.resample(b, H1) for s, b in bars.items()}
    res, base = run(bars1h, fund, part, pcts, holds, dirs)
    if part == "dev":
        eh.append_log(os.path.join(a.log_dir, "funding_dev_trials.jsonl"),
                      {"ts": round(time.time(), 1), "config_sha": csha, **cfg, "tests": len(res)})
    p = os.path.join(a.log_dir, "funding_dev_trials.jsonl")
    recs = [json.loads(x) for x in open(p, encoding="utf-8")] if os.path.isfile(p) else []
    info = {"price_files": info5["files"], "funding_files": 46, "funding_rows_discarded": dropped}
    md = markdown(res, base, part, info, (len(recs), sum(r["tests"] for r in recs)), a.note)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
