"""Amendment 14a (research/PROTOCOL_V3.md): the three measurement hypotheses on amendment 14's data, locked as written
in research/drafts/AENDRING14_HYPOTESER_UDKAST.md. MEASUREMENT ONLY: no position, no return series, nothing traded, no
paper account changed; step 2 of H2/H3 (the carry rules) is not implemented here.

- H1 `makrodybde` (points 1-9): book depth within 1 % is lower around scheduled FOMC / CPI / jobs-report times.
- H2 `opmaerk` step 1: a pageview shock predicts next week's settled funding beyond the coin's own last week.
- H3 `smaahandel` step 1: a shock in the taker-buy share of trades < 1,000 USD does the same.

Reading (point 4): a Reader is opened for one split window of one hypothesis and refuses any row after 2023-12-31 and
any row outside its window; it is the only code that opens a data file and it records each file's size and sha256.
run() checks file presence first (UNTESTABLE when short), measures train, applies the train gate, and only after a
passed gate opens a Reader for validation. alpha = 0.05 / 3 per test (point 2). An outcome decides nothing for trading.
"""
from __future__ import annotations

import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import os
import random
import statistics
import time
import zipfile
from datetime import datetime, timezone

from lab.engine import data as mdata

RULE = "research/PROTOCOL_V3.md amendment 14a"
DRAFT = "research/drafts/AENDRING14_HYPOTESER_UDKAST.md"
ARTIFACT_ID = "MEASURE_14a"
EVENT = "research.measurement"
ALPHA = 0.05 / 3                                   # point 2: separate measurement error rate 0.05 over three tests
END = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()   # 2024 is holdout, 2025+ reserved (amendment 14 point 2)
HOUR, DAY, WEEK = 3600, 86400, 7 * 86400
UNIVERSE = mdata.UNIVERSE
SPLITS = {"H1": ("train", "validation"), "H2": ("train3", "validation3"), "H3": ("train", "validation")}
NAMES = {"H1": "makrodybde", "H2": "opmaerk (step 1)", "H3": "smaahandel (step 1)"}
ARTICLE = dict(zip(UNIVERSE, ("Binance", "Ripple_Labs", "Dogecoin", "Cardano_(blockchain_platform)",
                              "Chainlink_(blockchain)", "Litecoin", "Avalanche_(blockchain_platform)",
                              "Polkadot_(cryptocurrency)")))              # H2.2: BNB and XRP by their firm articles
PAGEVIEW_LAG_S = 2 * DAY                          # amendment 14 point 3 (= ingest.PAGEVIEW_LAG_S)
FUNDING_FILE = "{sym}-fundingRate-{y}-{m:02d}.zip"   # families.FILE_PATTERNS["binance_um_fundingRate"]
# H1 (draft H1.3, H1.6-H1.8)
MIN_SNAPSHOTS, VALID_SHARE, MIN_COINS = 90, 0.95, 6
CONTROL_DAYS, CONTROL_MIN, CONTROL_SPAN = 5, 3, 14
PLACEBO_N, PLACEBO_SEED, PLACEBO_P = 2000, 17, 0.10
MIN_EVENTS = {"train": 15, "validation": 8}
PRACTICAL_FALL = 0.15                             # a fall below 15 % is reported as practically negligible
EVENT_TYPES = {"FOMC statement": "fomc", "Consumer Price Index": "cpi", "Employment Situation": "jobs"}
# sign-flip test (H1.7)
EXACT_MAX, FLIP_DRAWS, FLIP_SEED = 20, 100_000, 7
# H2/H3 step 1 (H2.3, H2.4, H2.7, H3.3, H3.4, H3.7)
BLOCK, BOOT_N, BOOT_SEED = 4, 2000, 7
LOOKBACK_DAYS = {"H2": 15, "H3": 14}              # first week = first Monday >= window start + this many days
MIN_WEEKS = {"H2": {"train3": 60, "validation3": 18}, "H3": {"train": 25, "validation": 12}}
MIN_SETTLEMENTS = 21                              # a complete 7-day funding interval (3 settlements a day)
H3_HOURS, H3_DAYS = 72, 11


class Refused(Exception):
    """A read the amendment does not allow (after 2023-12-31, outside the split window, wrong split)."""


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M")


def _day(ts):
    return int(ts) // DAY * DAY


def _weekday(ts):
    return datetime.fromtimestamp(ts, timezone.utc).weekday()


# ---------- reader ----------
def path_of(root, kind, key, y=None, m=None):
    """Where ingest (and the market cache) keep a file; no I/O."""
    if kind == "bookdepth":
        return os.path.join(root, "ingest", "bookdepth_1h", f"{key}-{y}-{m:02d}.csv.gz")
    if kind == "aggtrades":
        return os.path.join(root, "ingest", "aggtrades_1h", f"{key}-{y}-{m:02d}.csv.gz")
    if kind == "funding":
        return os.path.join(root, "funding", FUNDING_FILE.format(sym=key, y=y, m=m))
    if kind == "pageviews":
        return os.path.join(root, "ingest", "pageviews", f"{key}.json")
    if kind == "calendar":
        return os.path.join(root, "ingest", "calendar", f"{key}-{y}.json")
    raise Refused(f"unknown data kind {kind}")


def read_bytes(path):
    """The single place a data file is opened (tests replace it to prove what is and is not read)."""
    with open(path, "rb") as f:
        return f.read()


class Reader:
    """Read-only access to one split window of one hypothesis. Every row is checked: after 2023-12-31 or outside
    the window -> Refused. There is no default split, so validation is read only when asked for by name."""

    def __init__(self, root, split, hypothesis):
        if split not in SPLITS.get(hypothesis, ()):
            raise Refused(f"{hypothesis} may read only {SPLITS.get(hypothesis)} (amendment 14a point 4), not {split}")
        a, b = mdata.window(split)                     # raises for reserved windows
        if b >= END:
            raise Refused(f"{split} ends after 2023-12-31: 2024 is holdout (amendment 14 point 2)")
        self.root, self.split, self.h, self.a, self.b, self.files = root, split, hypothesis, a, b, []

    def _check(self, ts, what):
        if ts >= END:
            raise Refused(f"{what}: row at {_iso(ts)} is after 2023-12-31 (amendment 14 point 2)")
        if not self.a <= ts <= self.b:
            raise Refused(f"{what}: row at {_iso(ts)} is outside {self.split} ({_iso(self.a)} .. {_iso(self.b)})")

    def _months(self, months):
        own = mdata.months(self.split)
        for ym in months or own:
            if tuple(ym) not in own:
                raise Refused(f"{ym[0]}-{ym[1]:02d} is outside {self.split}")
        return months or own

    def _read(self, path):
        raw = read_bytes(path)
        self.files.append({"path": os.path.relpath(path, self.root).replace("\\", "/"), "bytes": len(raw),
                           "sha256": hashlib.sha256(raw).hexdigest(), "split": self.split})
        return raw

    def hours(self, kind, coin, months=None):
        """Hourly ingest summaries ('bookdepth' or 'aggtrades') -> {hour_ts: {column: float or None}}. A row is usable
        from its available_ts, never earlier than the hour's end (amendment 14 point 3)."""
        out = {}
        for y, m in self._months(months):
            p = path_of(self.root, kind, coin, y, m)
            if not os.path.isfile(p):
                continue
            rows = csv.reader(io.StringIO(gzip.decompress(self._read(p)).decode("utf-8")))
            cols = next(rows, None) or []
            for r in rows:
                d = {c: (float(v) if v != "" else None) for c, v in zip(cols, r)}
                t = int(d["hour_ts"])
                self._check(t, os.path.basename(p))
                d["available_ts"] = max(d.get("available_ts") or 0, t + HOUR)
                out[t] = d
        return out

    def funding(self, sym, months=None):
        """Settled funding {settlement hour ts: rate} from the monthly archive zips (as engine.data.load)."""
        out = {}
        for y, m in self._months(months):
            p = path_of(self.root, "funding", sym, y, m)
            if not os.path.isfile(p):
                continue
            with zipfile.ZipFile(io.BytesIO(self._read(p))) as z:
                for name in z.namelist():
                    for r in csv.reader(io.TextIOWrapper(z.open(name), encoding="utf-8")):
                        if r and r[0][:1].isdigit():
                            ts = int(r[0]) // 1000
                            self._check(ts, os.path.basename(p))
                            out[ts - ts % HOUR] = float(r[2])
        return out

    def pageviews(self, article):
        """{day ts: (views, available_ts)} for the days inside the window; usable from D+2 00:00 UTC. The file spans
        2020-2023: days outside the window are never returned, and a day after 2023-12-31 is refused."""
        p = path_of(self.root, "pageviews", article)
        out = {}
        if not os.path.isfile(p):
            return out
        for x in json.loads(self._read(p)).get("rows", []):
            d = datetime.strptime(x["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
            if d >= END:
                self._check(d, os.path.basename(p))
            if self.a <= d <= self.b:
                out[int(d)] = (float(x["views"]), max(float(x.get("available_ts") or 0), d + PAGEVIEW_LAG_S))
        return out

    def calendar(self):
        """(scheduled events with a time inside the window, days inside the window with any listed event). Times are
        known in advance (amendment 14 point 3); unscheduled meetings have no time and are never events."""
        events, days = [], set()
        for y in sorted({y for y, _m in mdata.months(self.split)}):
            for kind in ("fomc", "bls"):
                p = path_of(self.root, "calendar", kind, y)
                if not os.path.isfile(p):
                    continue
                for e in json.loads(self._read(p)).get("events", []):
                    d = datetime.strptime(e["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
                    if d >= END or (e.get("ts") or 0) >= END:
                        self._check(max(d, e.get("ts") or 0), os.path.basename(p))
                    if e.get("kind") == "cancelled" or not self.a <= d <= self.b:
                        continue
                    days.add(int(d))
                    t = e.get("ts")
                    if e.get("scheduled") and t and e.get("event") in EVENT_TYPES and self.a <= t <= self.b:
                        events.append({"type": EVENT_TYPES[e["event"]], "ts": int(t), "date": e["date"]})
        return sorted(events, key=lambda e: e["ts"]), days


def coverage(h, root):
    """File presence only (os.stat, nothing opened) for both splits: enough coins with every monthly file, and the
    calendar / pageview files the measurement needs. {'ok', 'reason', 'splits'}."""
    out, why = {}, None
    for sp in SPLITS[h]:
        ms = mdata.months(sp)
        coins = []
        for c in UNIVERSE:
            need = ([path_of(root, "bookdepth", c, y, m) for y, m in ms] if h == "H1" else
                    [path_of(root, "funding", c, y, m) for y, m in ms]
                    + ([path_of(root, "pageviews", ARTICLE[c])] if h == "H2" else
                       [path_of(root, "aggtrades", c, y, m) for y, m in ms]))
            if all(os.path.isfile(p) for p in need):
                coins.append(c)
        cal = [path_of(root, "calendar", k, y) for k in ("fomc", "bls") for y in sorted({y for y, _ in ms})]
        miss_cal = [os.path.relpath(p, root) for p in cal if h == "H1" and not os.path.isfile(p)]
        out[sp] = {"coins_with_all_files": coins, "missing_calendar": miss_cal}
        if len(coins) < MIN_COINS and not why:
            why = f"{sp}: only {len(coins)} coins have every file (need {MIN_COINS})"
        if miss_cal and not why:
            why = f"{sp}: calendar files missing: {', '.join(miss_cal)}"
    return {"ok": why is None, "reason": why, "splits": out}


# ---------- statistics ----------
def sign_flip_p(ys, draws=FLIP_DRAWS, seed=FLIP_SEED):
    """One-sided sign-flip p that the mean is < 0: the share of sign patterns whose sum is <= the observed sum. Exact
    (all 2^n patterns, counted by meet-in-the-middle) for n <= 20, else `draws` random patterns, p = (k+1)/(draws+1)."""
    n = len(ys)
    if not n:
        return None
    s = sum(ys)
    tol = 1e-12 * (1 + sum(abs(y) for y in ys))
    if n <= EXACT_MAX:
        def sums(v):
            out = [0.0]
            for y in v:
                out = [x + y for x in out] + [x - y for x in out]
            return out
        left, right = sorted(sums(ys[:n // 2])), sums(ys[n // 2:])
        return sum(bisect.bisect_right(left, s + tol - x) for x in right) / 2 ** n
    rng, k = random.Random(seed), 0
    for _ in range(draws):
        k += sum(y if rng.random() < 0.5 else -y for y in ys) <= s + tol
    return (k + 1) / (draws + 1)


def block_bootstrap(xs, alpha=ALPHA, block=BLOCK, draws=BOOT_N, seed=BOOT_SEED):
    """Moving-block bootstrap of the mean over consecutive weeks (blocks of `block`, not circular). The one-sided lower
    bound at 1 - alpha is the largest bootstrap mean with at most alpha of the draws at or below it."""
    n = len(xs)
    if n < block:
        return {"lower": None, "draws": 0}
    rng, k = random.Random(seed), math.ceil(n / block)
    means = []
    for _ in range(draws):
        s = []
        for _ in range(k):
            i = rng.randrange(n - block + 1)
            s.extend(xs[i:i + block])
        means.append(sum(s[:n]) / n)
    means.sort()
    j = max(1, math.floor(alpha * draws))
    return {"lower": means[j - 1], "rank": j, "draws": draws, "block": block, "seed": seed, "alpha": alpha,
            "median": means[draws // 2]}


def ranks(v):
    """Average ranks (ties share their mean rank)."""
    order = sorted(range(len(v)), key=lambda i: v[i])
    r, i = [0.0] * len(v), 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxx, syy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def spearman(x, y):
    return pearson(ranks(x), ranks(y))


def ols_residuals(y, x):
    """Residuals of y on a constant and x. With no spread in x the slope is 0 (the minimum-norm solution)."""
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxx = sum((a - mx) ** 2 for a in x)
    beta = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx if sxx > 0 else 0.0
    return [b - my - beta * (a - mx) for a, b in zip(x, y)]


# ---------- H1 makrodybde ----------
def depth(row, level=1, field="min"):
    """D(c,h): the thinner side within `level` % in the hour's thinnest snapshot (field 'min'; 'mean' is secondary).
    None for an invalid hour: fewer than 90 snapshots, a missing side or a non-positive value."""
    if row is None or (row.get("snapshots") or 0) < MIN_SNAPSHOTS:
        return None
    lo, hi = row.get(f"{field}_usd_{-level:+d}"), row.get(f"{field}_usd_{level:+d}")
    if lo is None or hi is None or min(lo, hi) <= 0:
        return None
    return min(lo, hi)


def window_hours(t, before=HOUR, after=HOUR):
    """W(e): the clock hours that overlap [T - before, T + after)."""
    return list(range(int(t - before) // HOUR * HOUR, int(t + after), HOUR))


def x_value(d, hours):
    """X: the minimum of D over the hours; None unless every hour is valid."""
    v = [d.get(h) for h in hours]
    return None if not v or any(x is None for x in v) else min(v)


def control_offsets(t, event_days, a):
    """Control days: the 5 latest weekdays (Mon-Fri) before the event day, within 14 days, skipping days with any
    listed event, and never before the window start (no history across the boundary). Returns day offsets in s."""
    day0, out = _day(t), []
    for k in range(1, CONTROL_SPAN + 1):
        d = day0 - k * DAY
        if _weekday(d) >= 5 or d in event_days:
            continue
        if min(window_hours(t)) - k * DAY < a:
            break
        out.append(k * DAY)
        if len(out) == CONTROL_DAYS:
            break
    return out


def event_y(D, t, event_days, a, b, before=HOUR, after=HOUR):
    """Y(e) = mean over coins of ln(X(e,c) / K(e,c)), K = median X of the control days (>= 3 per coin); None unless
    >= 6 coins and >= 3 control days. Returns (Y or None, {coin: Y(e,c)}, control days)."""
    hours = window_hours(t, before, after)
    offs = control_offsets(t, event_days, a)
    if hours[0] < a or hours[-1] + HOUR - 1 > b or len(offs) < CONTROL_MIN:
        return None, {}, len(offs)
    per = {}
    for c, d in D.items():
        x = x_value(d, hours)
        ks = [k for k in (x_value(d, [h - o for h in hours]) for o in offs) if k is not None]
        if x is not None and len(ks) >= CONTROL_MIN:
            per[c] = math.log(x / statistics.median(ks))
    return (sum(per.values()) / len(per) if len(per) >= MIN_COINS else None), per, len(offs)


def placebo(D, times, event_days, a, b, observed, n=PLACEBO_N, seed=PLACEBO_SEED):
    """Placebo p: share of `n` pseudo-event sets whose mean is <= the observed mean. A set has one pseudo-event per
    real event at the same UTC clock time, drawn without replacement per clock time among the window's weekdays
    without a listed event whose Y is valid (the same control rule as the events)."""
    pools = {}
    for tod in sorted({t % DAY for t in times}):
        pools[tod] = []
        for d in range(_day(a), _day(b) + 1, DAY):
            if _weekday(d) < 5 and d not in event_days:
                y = event_y(D, d + tod, event_days, a, b)[0]
                if y is not None:
                    pools[tod].append(y)
    need = {tod: sum(1 for t in times if t % DAY == tod) for tod in pools}
    if any(len(pools[tod]) < need[tod] for tod in pools):
        return {"p": None, "reason": "too few pseudo-event days", "pool": {str(k): len(v) for k, v in pools.items()}}
    rng, k, means = random.Random(seed), 0, []
    for _ in range(n):
        ys = [y for tod in sorted(pools) for y in rng.sample(pools[tod], need[tod])]
        m = sum(ys) / len(ys)
        means.append(m)
        k += m <= observed
    return {"p": k / n, "n": n, "seed": seed, "at_or_below": k, "pool": {str(t): len(v) for t, v in pools.items()},
            "mean_of_sets": sum(means) / n}


def h1_measure(reader):
    """H1 on one split: coverage of valid hours, events, Y(e), placebo, sign-flip p, secondary figures."""
    a, b = reader.a, reader.b
    rows = {c: reader.hours("bookdepth", c) for c in UNIVERSE}
    D = {c: {t: depth(r) for t, r in rows[c].items() if depth(r) is not None} for c in UNIVERSE}
    total = (b + 1 - a) // HOUR
    valid = {c: len(D[c]) / total for c in UNIVERSE}
    good = [c for c in UNIVERSE if valid[c] >= VALID_SHARE]
    out = {"split": reader.split, "valid_hour_share": valid, "coins_95": good}
    if len(good) < MIN_COINS:
        return out | {"untestable": f"only {len(good)} coins have >= 95 % valid hours in {reader.split}"}
    events, days = reader.calendar()
    rows_e, used = [], []
    for e in events:
        y, per, nc = event_y(D, e["ts"], days, a, b)
        rows_e.append({"type": e["type"], "T": _iso(e["ts"]) + " UTC", "Y": y, "coins": len(per),
                       "control_days": nc, "dropped": None if y is not None else
                       ("fewer than 3 control days in the window" if nc < CONTROL_MIN else "fewer than 6 coins")})
        if y is not None:
            used.append((e, y))
    ys = [y for _e, y in used]
    out |= {"events": rows_e, "n": len(ys), "n_listed": len(events)}
    if len(ys) < MIN_EVENTS[reader.split]:
        return out | {"untestable": f"{len(ys)} events in {reader.split} (minimum {MIN_EVENTS[reader.split]})"}
    mean = sum(ys) / len(ys)
    out |= {"mean_Y": mean, "fall": 1 - math.exp(mean), "practically_negligible": 1 - math.exp(mean) < PRACTICAL_FALL,
            "placebo": placebo(D, [e["ts"] for e, _y in used], days, a, b, mean),
            "sign_flip_p": sign_flip_p(ys), "sign_flip": "exact" if len(ys) <= EXACT_MAX else f"{FLIP_DRAWS} draws"}
    out["secondary"] = h1_secondary(rows, D, used, days, a, b)
    return out


def h1_secondary(rows, d1, used, days, a, b):
    """Reported, decides nothing: +-2 %, mean depth, each event type, the hour before T against the hour after T."""
    def mean_y(D, ev, before=HOUR, after=HOUR):
        ys = [y for y in (event_y(D, e["ts"], days, a, b, before, after)[0] for e in ev) if y is not None]
        return {"n": len(ys), "mean_Y": sum(ys) / len(ys) if ys else None}
    ev = [e for e, _y in used]
    d2 = {c: {t: depth(r, 2) for t, r in rows[c].items() if depth(r, 2) is not None} for c in rows}
    dm = {c: {t: depth(r, 1, "mean") for t, r in rows[c].items() if depth(r, 1, "mean") is not None} for c in rows}
    by_type = {}
    for e, y in used:
        by_type.setdefault(e["type"], []).append(y)
    return {"depth_2pct": mean_y(d2, ev), "mean_depth_1pct": mean_y(dm, ev),
            "by_type": {k: {"n": len(v), "mean_Y": sum(v) / len(v)} for k, v in sorted(by_type.items())},
            "hour_before_T": mean_y(d1, ev, HOUR, 0), "hour_after_T": mean_y(d1, ev, 0, HOUR),
            "decisional": False}


# ---------- H2 / H3 step 1 ----------
def mondays(split, lookback_days):
    """Decision times: Mondays 01:00 UTC from the first Monday >= window start + lookback days, while [t, t + 7 d)
    lies inside the window (so no 2024 settlement is ever an outcome)."""
    a, b = mdata.window(split)
    d = a + lookback_days * DAY
    while _weekday(d) != 0:
        d += DAY
    out, t = [], d + HOUR
    while t + WEEK <= b + 1:
        out.append(t)
        t += WEEK
    return out


def shock_s(pv, t):
    """H2: S(c,t) = A(c,t-2) - mean A(c,d) for d = t-15..t-3, A = ln(1 + views). Every day must be present and
    usable at t (D+2 00:00 UTC); else None."""
    day, a = _day(t), {}
    for k in range(2, 16):
        r = pv.get(day - k * DAY)
        if r is None or r[1] > t:
            return None
        a[k] = math.log1p(r[0])
    return a[2] - sum(a[k] for k in range(3, 16)) / 13


def _share(rows):
    buy = sum(r["buy_usd_lt1k"] or 0.0 for r in rows)
    tot = buy + sum(r["sell_usd_lt1k"] or 0.0 for r in rows)
    return buy / tot if tot > 0 else None


def shock_r(tr, t):
    """H3: R(c,t) = (a72 - m) / s. a72 = taker-buy share of < 1k USD notional over the 72 hourly rows usable at t
    (available_ts <= t, i.e. hours t-72h .. t-1h); m, s = mean and sample deviation of the 11 day shares of the 24-hour
    blocks before those 72 hours (14 days in all). Every hour must be present; None if s = 0 or a share is undefined."""
    def block(start, n):
        rows = [tr.get(h) for h in range(start, start + n * HOUR, HOUR)]
        if any(r is None or r["available_ts"] > t for r in rows):
            return None
        return _share(rows)
    t0 = int(t) - H3_HOURS * HOUR
    a72 = block(t0, H3_HOURS)
    days = [block(t0 - (k + 1) * 24 * HOUR, 24) for k in range(H3_DAYS)]
    if a72 is None or any(x is None for x in days):
        return None
    s = statistics.stdev(days)
    return (a72 - statistics.fmean(days)) / s if s > 0 else None


def funding_sums(fr, t):
    """F_before = funding settled in (t - 7 d, t), F_after = in [t, t + 7 d); None unless both weeks are complete."""
    before = [r for ts, r in fr.items() if t - WEEK < ts < t]
    after = [r for ts, r in fr.items() if t <= ts < t + WEEK]
    if len(before) < MIN_SETTLEMENTS or len(after) < MIN_SETTLEMENTS:
        return None
    return sum(before), sum(after)


def week_rho(shock, fund, coins=UNIVERSE):
    """rho_t = Spearman(shock, u) with u the cross-sectional OLS residual of F_after on F_before; >= 6 coins."""
    cs = [c for c in coins if shock.get(c) is not None and fund.get(c) is not None]
    if len(cs) < MIN_COINS:
        return None, len(cs)
    u = ols_residuals([fund[c][1] for c in cs], [fund[c][0] for c in cs])
    return spearman([shock[c] for c in cs], u), len(cs)


def flow_measure(reader):
    """H2 or H3 step 1 on one split: the weekly rho_t series, its mean and the block-bootstrap lower bound."""
    h, sp = reader.h, reader.split
    fr = {c: reader.funding(c) for c in UNIVERSE}
    if h == "H2":
        src = {c: reader.pageviews(ARTICLE[c]) for c in UNIVERSE}
        shock_of = shock_s
    else:
        src = {c: reader.hours("aggtrades", c) for c in UNIVERSE}
        shock_of = shock_r
    weeks, rhos, excl = [], [], []
    for t in mondays(sp, LOOKBACK_DAYS[h]):
        shock = {c: shock_of(src[c], t) for c in UNIVERSE}
        fund = {c: funding_sums(fr[c], t) for c in UNIVERSE}
        rho, n = week_rho(shock, fund)
        weeks.append({"t": _iso(t) + " UTC", "coins": n, "rho": rho})
        if rho is not None:
            rhos.append(rho)
        if h == "H2":
            excl.append(week_rho(shock, fund, [c for c in UNIVERSE if c not in ("BNBUSDT", "XRPUSDT")])[0])
    out = {"split": sp, "weeks": weeks, "mondays": len(weeks), "n": len(rhos)}
    if len(rhos) < MIN_WEEKS[h][sp]:
        return out | {"untestable": f"{len(rhos)} weeks with >= {MIN_COINS} coins in {sp} "
                                    f"(minimum {MIN_WEEKS[h][sp]})"}
    out |= {"mean_rho": sum(rhos) / len(rhos), "bootstrap": block_bootstrap(rhos)}
    if h == "H2":
        ex = [x for x in excl if x is not None]
        out["secondary"] = {"without_BNB_XRP": {"n": len(ex), "mean_rho": sum(ex) / len(ex) if ex else None},
                            "decisional": False}
    return out


# ---------- runner ----------
MEASURE = {"H1": h1_measure, "H2": flow_measure, "H3": flow_measure}


def train_gate(h, m):
    if h == "H1":
        p = (m.get("placebo") or {}).get("p")
        return m["mean_Y"] < 0 and p is not None and p < PLACEBO_P
    return m["mean_rho"] > 0


def validation_pass(h, m):
    if h == "H1":
        p = (m.get("placebo") or {}).get("p")
        return m["sign_flip_p"] is not None and m["sign_flip_p"] < ALPHA and p is not None and p < PLACEBO_P
    lo = m["bootstrap"]["lower"]
    return lo is not None and lo > 0


def _code():
    here = os.path.abspath(__file__)
    with open(here, "rb") as f:
        out = {"file": "lab/measure.py", "sha256": hashlib.sha256(f.read()).hexdigest()}
    try:
        from lab.registry import git
        out["commit"] = git("rev-parse", "HEAD")
        out["clean"] = not git("status", "--porcelain", "--", here)
    except Exception:
        out["commit"] = None
    return out


def run(hypothesis, root=None):
    """One measurement (amendment 14a point 1): coverage -> train -> train gate -> (only then) validation. Returns a
    JSON-serialisable dict with verdict PASS, REJECTED or UNTESTABLE."""
    h = hypothesis.upper()
    if h not in SPLITS:
        raise Refused(f"unknown hypothesis {hypothesis}: H1, H2 or H3")
    root = root or mdata.CACHE
    tr, va = SPLITS[h]
    res = {"hypothesis": h, "name": NAMES[h], "rule": RULE, "draft": DRAFT, "alpha": ALPHA, "splits": [tr, va],
           "seeds": ({"placebo": PLACEBO_SEED, "sign_flip": FLIP_SEED} if h == "H1" else {"bootstrap": BOOT_SEED}),
           "code": _code(), "started": _iso(time.time()) + " UTC", "validation_read": False, "inputs": [],
           "decisional_for_trading": False}

    def done(verdict, reason):
        res["verdict"], res["reason"] = verdict, reason
        res["finished"] = _iso(time.time()) + " UTC"
        return res
    res["coverage"] = coverage(h, root)
    if not res["coverage"]["ok"]:
        return done("UNTESTABLE", res["coverage"]["reason"])
    r = Reader(root, tr, h)
    try:
        res["train"] = MEASURE[h](r)
    finally:
        res["inputs"] += r.files
    if res["train"].get("untestable"):
        return done("UNTESTABLE", res["train"]["untestable"])
    res["train_gate"] = train_gate(h, res["train"])
    if not res["train_gate"]:
        return done("REJECTED", f"train gate failed; {va} not read")
    res["validation_read"] = True
    v = Reader(root, va, h)
    try:
        res["validation"] = MEASURE[h](v)
    finally:
        res["inputs"] += v.files
    if res["validation"].get("untestable"):
        return done("UNTESTABLE", res["validation"]["untestable"])
    ok = validation_pass(h, res["validation"])
    return done("PASS" if ok else "REJECTED", f"validation test {'passed' if ok else 'failed'} at alpha {ALPHA:.4f}")
