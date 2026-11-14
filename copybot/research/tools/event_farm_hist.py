"""Event farm historical development lab (PROTOCOL_V3 amendment 47, owner chat yes 2026-11-14).

The frozen engine (research/tools/event_farm.py) and filters (event_farm_filters.py) run on 5m bars aggregated from the
44 cached explore0 files BTCUSDT/ETHUSDT-1m-2020-03..2021-12. Parameters can be changed freely for DEVELOPMENT; the
forward paper book (amendment 46) is not touched and none of its pinned files is edited.

FAIL-CLOSED DATA RULES (amendment 47 point 1), in this order:
1. the 44 file names come from research/studies/R3_m24_verify.json, each must match NAME (BTC/ETH, 2020-03..2021-12);
   the cache directory is never listed;
2. every file's sha256 must equal the verify file's before it is opened; one difference = Refused (BLOCKED);
3. rows outside the file's month are discarded and counted; aggregation to 5m keeps only complete buckets.
No network code. Never 2024 (G03), 2025+ (G04) or the quarantine (G07).

SPLIT (amendment 47 point 2): DEV = bars with close before 2021-07-01 00:00 UTC, results use only those bars (a trade
not finished before then is 'incomplete'). CHECK = 2021-07-01..2021-12-31, sealed: it runs only with --check, every
opening is appended to check_openings.jsonl BEFORE anything is computed. Every DEV configuration is appended to
dev_trials.jsonl and counts in N (point 3). Costs as the paper book: event_farm_forward.lab_costs (28 bps round trip).

UDVIKLING / explore0 = udforskning, aldrig bevis. Kun papir og forskning.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import pickle
import re
import statistics
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_filters as ff  # noqa: E402
from research.tools import event_farm_forward as fw  # noqa: E402

BS = 300
CACHE = "/home/anton/ecommerence/copybot/data/lab/market/klines_1m"
VERIFY = os.path.join(HERE, "research", "studies", "R3_m24_verify.json")
OUT_DIR = os.path.join(HERE, "research", "data", "event_farm_hist")
WORK = os.path.expanduser("~/.cache/copybot_farm_hist")
NAME = re.compile(r"^(BTCUSDT|ETHUSDT)-1m-(2020-(0[3-9]|1[0-2])|2021-(0[1-9]|1[0-2]))\.zip$")
SYMBOLS = ("BTCUSDT", "ETHUSDT")
N_FILES = 44
EXPLORE_START = 1583020800                      # 2020-03-01 00:00 UTC
DEV_END = 1625097600                            # 2021-07-01 00:00 UTC
EXPLORE_END = 1640995200                        # 2022-01-01 00:00 UTC
CHECK_WARM_BARS = 3 * 288                       # engine/filters warm on the 3 days before CHECK; nothing counted there
COSTS = fw.FROZEN_CONFIG
COMBOS = ("base",) + tuple(ff.COMBOS)
LABEL = "UDVIKLING på explore0 (2020-03..2021-06) - udforskning, aldrig bevis; kun papir"
LABEL_CHECK = "KONTROL på explore0 (2021-07..2021-12) - forseglet periode, åbning logget; stadig udforskning"


class Refused(Exception):
    """A data rule failed: nothing is opened or computed."""


# ------------------------------------------------------------------------------------------------ data
def expected(verify_path=VERIFY):
    with open(verify_path, encoding="utf-8") as f:
        v = json.load(f)
    files = [r for r in v.get("files", []) if isinstance(r, dict)]
    bad = [r.get("file") for r in files if not NAME.match(str(r.get("file", "")))]
    if bad:
        raise Refused(f"verify file names outside BTC/ETH 2020-03..2021-12: {bad[:3]}")
    if len(files) != N_FILES or not all(r.get("ok") and re.fullmatch(r"[0-9a-f]{64}", str(r.get("sha256"))) for r in files):
        raise Refused(f"verify file must list {N_FILES} ok files with sha256")
    return sorted((r["file"], r["sha256"]) for r in files)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def identity(cache=CACHE, verify_path=VERIFY):
    """{name: {sha256, size}} after checking every expected file; Refused on a missing file or a sha256 difference."""
    man, bad = {}, []
    for name, sha in expected(verify_path):
        p = os.path.join(cache, name)
        if not os.path.isfile(p):
            bad.append(f"{name}: missing")
            continue
        got = _sha(p)
        if got != sha:
            bad.append(f"{name}: sha256 {got[:12]} != {sha[:12]}")
        man[name] = {"sha256": got, "size": os.path.getsize(p)}
    if bad:
        raise Refused("identity manifest differs (BLOCKED): " + "; ".join(bad[:5]))
    return man


def month_bounds(name):
    y, m = map(int, NAME.match(name).group(2).split("-"))
    lo = int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp())
    hi = int(dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
    return lo, hi


def read_month(path, name):
    """1m rows (ts, o, h, l, c, v) inside the file's month, and the count of discarded rows."""
    lo, hi = month_bounds(name)
    rows, dropped = [], 0
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.namelist() if m.endswith(".csv")]
        if len(members) != 1:
            raise Refused(f"{name}: expected one csv, found {members}")
        with z.open(members[0]) as fh:
            for r in csv.reader(io.TextIOWrapper(fh, encoding="ascii")):
                if not r or not r[0].isdigit():
                    dropped += 1
                    continue
                t = int(r[0])
                t = t // 1000 if t > 10 ** 11 else t
                if not lo <= t < hi:
                    dropped += 1
                    continue
                rows.append((t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    rows.sort()
    return rows, dropped


def aggregate(bars_1m, bs=BS):
    need = bs // 60
    buckets = collections.OrderedDict()
    for b in bars_1m:
        buckets.setdefault(b[0] // bs * bs, []).append(b)
    out, dropped = [], 0
    for start, mins in buckets.items():
        if len(mins) != need or any(m[0] != start + 60 * k for k, m in enumerate(mins)):
            dropped += 1
            continue
        out.append((start, mins[0][1], max(m[2] for m in mins), min(m[3] for m in mins), mins[-1][4],
                    math.fsum(m[5] for m in mins)))
    return out, dropped


def load_bars(cache=CACHE, verify_path=VERIFY, work=WORK):
    """{symbol: 5m bars 2020-03..2021-12} and an info dict. Identity is checked on every call (before any parse); the
    parsed bars are cached under `work` keyed by the identity manifest."""
    man = identity(cache, verify_path)
    key = hashlib.sha256(json.dumps(man, sort_keys=True).encode()).hexdigest()[:16]
    pk = os.path.join(work, f"bars5m_{key}.pkl") if work else None
    if pk and os.path.isfile(pk):
        with open(pk, "rb") as f:
            got = pickle.load(f)
        got["info"]["from_cache"] = True
        return got["bars"], got["info"]
    bars, info = {}, {"manifest_key": key, "files": len(man), "rows_discarded": 0, "buckets_dropped": {}}
    for s in SYMBOLS:
        one = []
        for name in sorted(n for n in man if n.startswith(s + "-")):
            rows, dropped = read_month(os.path.join(cache, name), name)
            one += rows
            info["rows_discarded"] += dropped
        b5, drop = aggregate(one)
        ef.check_bars(b5)
        bars[s], info["buckets_dropped"][s] = b5, drop
    if pk:
        os.makedirs(work, exist_ok=True)
        with open(pk + ".tmp", "wb") as f:
            pickle.dump({"bars": bars, "info": info}, f)
        os.replace(pk + ".tmp", pk)
    info["from_cache"] = False
    return bars, info


def part_bars(bars, part):
    """(bars, count_from_ts): DEV ends at the last bar closing by DEV_END; CHECK starts CHECK_WARM_BARS before it."""
    if part == "dev":
        return [b for b in bars if EXPLORE_START <= b[0] and b[0] + BS <= DEV_END], EXPLORE_START
    if part == "check":
        i = next((k for k, b in enumerate(bars) if b[0] >= DEV_END), len(bars))
        return [b for b in bars[max(0, i - CHECK_WARM_BARS):] if b[0] + BS <= EXPLORE_END], DEV_END
    raise ValueError("part must be dev or check")


# ------------------------------------------------------------------------------------------------ the run
def variant_over(vid):
    an, rr, em = vid.split("/")
    return {"anchor": an, "rr": float(rr[2:]), "entry_mode": em}


VARIANTS = tuple(ef._variant_id(v) for v in ef.VARIANTS)
SETUP_KEYS = ("anchor", "rr", "entry_mode", "stop_buffer_atr", "min_risk_atr", "fill_window", "max_hold", "ambiguous",
              "chain_breaks", "mss_window")


def run(bars_by_sym, over=None, variants=VARIANTS, combos=COMBOS, count_from=EXPLORE_START, fp=None, bs=BS):
    """Per test '<combo>/<variant>': setups, statuses and per-trade gross R, lab net R and net USDT (cost model of
    the paper book). Only setups with known_ts >= count_from count; outcomes use only the given bars."""
    over = dict(over or {})
    res = {f"{c}/{v}": {"setups": 0, "status": collections.Counter(), "gross": [], "net_r": [], "net_usdt": [],
                        "daily": collections.Counter(), "by": collections.defaultdict(list)}
           for v in variants for c in combos}
    days = set()
    det_cache = {}
    for s in sorted(bars_by_sym):
        bars = bars_by_sym[s]
        if not bars:
            continue
        days |= {b[0] // 86400 for b in bars if b[0] >= count_from}
        ctx = ff.context(bars, fp) if any(c != "base" for c in combos) else None
        for v in variants:
            p = ef.params(**{**over, **variant_over(v), "bar_seconds": bs})
            dkey = (s, json.dumps({k: p[k] for k in p if k not in SETUP_KEYS}, sort_keys=True, default=str))
            if dkey not in det_cache:
                det_cache.clear()
                det_cache[dkey] = ef.detect(bars, p)
            setups, _ = ef.build_setups(det_cache[dkey], bars, p)
            for st in setups:
                if st["known_ts"] < count_from:
                    continue
                o = ef.setup_outcome(st, bars, p)
                cost = fw.lab_costs(st, o["exit_px"], COSTS) if o["exit_px"] is not None else None
                for c in combos:
                    if c != "base" and not ff.passes(st, ctx, c):
                        continue
                    d = res[f"{c}/{v}"]
                    d["setups"] += 1
                    d["status"][o["status"]] += 1
                    if cost:
                        d["gross"].append(o["gross_r"])
                        d["net_r"].append(cost["net_r_lab"])
                        d["net_usdt"].append(cost["net_usdt"])
                        d["daily"][st["known_ts"] // 86400] += cost["net_r_lab"]
                        half = dt.datetime.fromtimestamp(st["known_ts"], dt.timezone.utc)
                        for key in ("long" if st["dir"] > 0 else "short", s,
                                    f"{half.year}H{1 + (half.month > 6)}"):
                            d["by"][key].append(cost["net_r_lab"])
    return summarize(res, len(days))


def _t(xs):
    if len(xs) < 2:
        return None
    sd = statistics.stdev(xs)
    return statistics.fmean(xs) / (sd / math.sqrt(len(xs))) if sd > 0 else None


def summarize(res, n_days):
    out = {"days": n_days, "tests": {}}
    for tid, d in res.items():
        n = len(d["net_r"])
        daily = [d["daily"].get(k, 0.0) for k in sorted(d["daily"])]
        out["tests"][tid] = {
            "setups": d["setups"], "per_day": d["setups"] / max(1, n_days), "trades": n,
            "status": dict(sorted(d["status"].items())),
            "win_share": (d["status"].get("target", 0) / n) if n else None,
            "mean_gross_r": statistics.fmean(d["gross"]) if n else None,
            "mean_net_r": statistics.fmean(d["net_r"]) if n else None,
            "sum_net_usdt": math.fsum(d["net_usdt"]),
            "t_daily_net_r": _t(daily),
            "cost_r_median": (statistics.median([g - r for g, r in zip(d["gross"], d["net_r"])]) if n else None),
            "by": {k: [len(v), statistics.fmean(v)] for k, v in sorted(d["by"].items())},
        }
    return out


def null_run(over=None, variants=VARIANTS, combos=("base",), days=60, seed=83, bs=BS):
    """The same configuration on the fixed engine null (driftless random walk, seed 83): what chance gives. The bar
    volatility is the engine's 5m null sigma scaled by sqrt(bs / 300) so other timeframes are comparable."""
    sig = ef.NULL_SIGMA_BAR * math.sqrt(bs / BS)
    bars = {f"SYN{i}": ef.random_walk_bars(seed + i, days * bs // BS, bar_seconds=bs,
                                           sigma_bar=sig) for i in range(2)}
    return run(bars, over, variants, combos, count_from=0, bs=bs)


def resample(bars5, bs):
    """5m bars -> bs-second bars (complete buckets only)."""
    if bs == BS:
        return bars5
    if bs % BS:
        raise ValueError("timeframe must be a multiple of 5m")
    need = bs // BS
    buckets = collections.OrderedDict()
    for b in bars5:
        buckets.setdefault(b[0] // bs * bs, []).append(b)
    return [(t, m[0][1], max(x[2] for x in m), min(x[3] for x in m), m[-1][4], math.fsum(x[5] for x in m))
            for t, m in buckets.items() if len(m) == need]


# ------------------------------------------------------------------------------------------------ logs
def config_sha(over, variants, combos, bs=BS):
    return hashlib.sha256(json.dumps({"over": over or {}, "variants": list(variants), "combos": list(combos),
                                      **({"bs": bs} if bs != BS else {})},
                                     sort_keys=True, default=str).encode()).hexdigest()


def append_log(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")


def n_trials(out_dir=OUT_DIR):
    p = os.path.join(out_dir, "dev_trials.jsonl")
    if not os.path.isfile(p):
        return 0, 0
    recs = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
    return len(recs), sum(r.get("tests", 0) for r in recs)


# ------------------------------------------------------------------------------------------------ report
def fmt(x, f="{:+.3f}"):
    return "–" if x is None else f.format(x)


BY_KEYS = ("long", "short", "BTCUSDT", "ETHUSDT", "2020H1", "2020H2", "2021H1", "2021H2")


def markdown(out, null, part, over, variants, combos, info, trials, note="", bs=BS):
    lab = LABEL_CHECK if part == "check" else LABEL
    L = [f"# Event farm historisk lab: {part.upper()}", "", f"**{lab}**", "",
         f"Konfiguration (ændringer fra motorens standard): `{json.dumps(over or {}, sort_keys=True)}` · "
         f"config sha `{config_sha(over, variants, combos, bs)[:12]}` · {out['days']} dage · BTCUSDT+ETHUSDT "
         f"{bs // 60}m · "
         f"omkostning som papirbogen (28 bps rundtur).", "",
         f"Data: {info.get('files')} filer, identitet ok (sha256 mod R3_m24_verify), {info.get('rows_discarded')} rækker "
         f"kasseret uden for måned, ufuldstændige 5m-spande {info.get('buckets_dropped')}.", "",
         f"Udviklingskørsler i alt (inkl. denne): {trials[0]} kørsler, {trials[1]} tests. Jo flere forsøg, jo større "
         "chance for et tilfældigt godt tal.", ""]
    if note:
        L += [note, ""]
    L += ["| test | setups/dag | handler | mål | stop | timeout | brutto R | netto R | netto USDT | t (dagl.) | "
          "omk. R (median) | null brutto R | null netto R |", "|" + "---|" * 13]
    for tid, r in out["tests"].items():
        st = r["status"]
        nl = null["tests"].get("base/" + tid.split("/", 1)[1], {}) if null else {}
        L.append(f"| {tid} | {r['per_day']:.2f} | {r['trades']} | {st.get('target', 0)} | {st.get('stop', 0)} | "
                 f"{st.get('timeout', 0)} | {fmt(r['mean_gross_r'])} | {fmt(r['mean_net_r'])} | "
                 f"{r['sum_net_usdt']:+.0f} | {fmt(r['t_daily_net_r'], '{:+.2f}')} | {fmt(r['cost_r_median'], '{:.2f}')} | "
                 f"{fmt(nl.get('mean_gross_r'))} | {fmt(nl.get('mean_net_r'))} |")
    L += ["", "Opdeling af netto R (antal handler, gns. netto R): retning, symbol og halvår.", "",
          "| test | " + " | ".join(BY_KEYS) + " |", "|" + "---|" * (len(BY_KEYS) + 1)]
    for tid, r in out["tests"].items():
        if r["trades"]:
            L.append(f"| {tid} | " + " | ".join(
                (f"{r['by'][k][0]} / {r['by'][k][1]:+.2f}" if k in r["by"] else "–") for k in BY_KEYS) + " |")
    L += ["", "Brutto R = før omkostninger; netto R = efter 28 bps (papirbogens model); 1.000 USDT pr. handel. "
          "Null = samme regler på en driftløs random walk (seed 83, 2 × 60 dage): det tilfældighed giver. "
          "Beskrivende; ingen rangering er en anbefaling."]
    return "\n".join(L) + "\n"


def parse_set(items):
    over = {}
    for it in items or []:
        k, _, v = it.partition("=")
        if k not in ef.DEFAULTS:
            raise SystemExit(f"unknown parameter {k!r}; known: {sorted(ef.DEFAULTS)}")
        try:
            over[k] = json.loads(v)
        except json.JSONDecodeError:
            over[k] = v
        if isinstance(ef.DEFAULTS[k], tuple) and isinstance(over[k], list):
            over[k] = tuple(tuple(x) if isinstance(x, list) else x for x in over[k])
    return over


def main(argv=None):
    ap = argparse.ArgumentParser(description="event farm historical development lab (PROTOCOL_V3 amendment 47)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="engine parameter override")
    ap.add_argument("--variants", default=",".join(VARIANTS), help="comma list of anchor/rrN/entry_mode")
    ap.add_argument("--combos", default="base", help="comma list of base,F1,F2,F3,F1+F2,... or 'all'")
    ap.add_argument("--check", action="store_true", help="open the sealed CHECK period (logged before computing)")
    ap.add_argument("--reason", default="", help="why CHECK is opened (required with --check)")
    ap.add_argument("--no-null", action="store_true")
    ap.add_argument("--out", default="", help="markdown file to write")
    ap.add_argument("--cache", default=CACHE)
    ap.add_argument("--verify", default=VERIFY)
    ap.add_argument("--log-dir", default=OUT_DIR)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--note", default="")
    ap.add_argument("--tf", type=int, default=5, help="timeframe in minutes (multiple of 5); 5m bars are resampled")
    a = ap.parse_args(argv)
    over = parse_set(a.set)
    variants = tuple(v for v in a.variants.split(",") if v)
    for v in variants:
        variant_over(v)
    combos = COMBOS if a.combos == "all" else tuple(c for c in a.combos.split(",") if c)
    if any(c not in COMBOS for c in combos):
        raise SystemExit(f"unknown combo; known: {COMBOS}")
    if a.tf != 5 and combos != ("base",):
        raise SystemExit("filters F1-F3 are defined on 5m bars only (1h trend, prior day, VWAP from 5m); use --combos base")
    part = "check" if a.check else "dev"
    bs = a.tf * 60
    csha = config_sha(over, variants, combos, bs)
    if part == "check":
        if not a.reason:
            raise SystemExit("--check needs --reason")
        append_log(os.path.join(a.log_dir, "check_openings.jsonl"),
                   {"ts": round(time.time(), 1), "config_sha": csha, "over": over, "variants": list(variants),
                    "combos": list(combos), "tf_min": a.tf, "reason": a.reason})
    bars, info = load_bars(a.cache, a.verify, a.work or None)
    sel, frm = {}, None
    for s, b in bars.items():
        pb, frm = part_bars(b, part)
        sel[s] = resample(pb, bs)
    t0 = time.time()
    out = run(sel, over, variants, combos, count_from=frm, bs=bs)
    null = None if a.no_null else null_run(over, variants, bs=bs)
    if part == "dev":
        append_log(os.path.join(a.log_dir, "dev_trials.jsonl"),
                   {"ts": round(time.time(), 1), "config_sha": csha, "over": over, "variants": list(variants),
                    "combos": list(combos), "tf_min": a.tf, "tests": len(out["tests"]),
                    "result_sha": hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()[:16]})
    md = markdown(out, null, part, over, variants, combos, info, n_trials(a.log_dir), a.note, bs)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    print(md)
    print(f"[{part}] {len(out['tests'])} tests in {time.time() - t0:.0f} s; bars cache {info.get('from_cache')}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
