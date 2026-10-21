"""Amendment 16a (research/PROTOCOL_V3.md): measurement hypothesis H4 `notering`, locked as written in
research/drafts/H4_NOTERING_FUNDING.md. MEASUREMENT ONLY: no position, nothing traded, no paper account changed.

Claim: settled funding (per 8 h) on a newly listed USD-M perp is higher in (t0, t0 + 7 d] than in (t0 + 30 d, t0 + 60 d].

- Events: Binance announcements stored by lab/news.py (detector "news/1", source "binance", category "listing") whose
  title contains "Binance Futures Will Launch" and "Perpetual"; symbols = news.coins(title) + "USDT" (amendment 16's
  fixed rules). One event per symbol: its earliest such announcement. The registry is opened read-only.
- Funding: monthly fundingRate archives of data.binance.vision (USD-M), each verified against its published .CHECKSUM
  (ingest.checked; a cached file is checked against the checksum too), only months 2022-01..2023-12. A Reader refuses any
  other month, any row at or after 2024-01-01 and any symbol not admitted to its phase.
- Phases: symbols announced in train3 months are read first (t0 searched only up to 2023-06); validation3 symbols (and
  train-announced symbols without a settlement by 2023-06) are admitted to a Reader only after the train gate passed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import statistics
import time
import urllib.error
import zipfile
from datetime import datetime, timezone

from lab import ingest, measure, news
from lab.engine import data as mdata

Refused = measure.Refused
RULE = "research/PROTOCOL_V3.md amendment 16a"
DRAFT = "research/drafts/H4_NOTERING_FUNDING.md"
DRAFT_SHA256 = "753b21aef638c72583295ebee570b0365c3c01e20c538175ff5a0581fca0603d"   # amendment 16a point 1
ARTIFACT_ID = "MEASURE_16a"
EVENT = measure.EVENT
HYPOTHESIS, NAME = "H4", "notering"
ALPHA = 0.05                                       # amendment 16a point 2: own error rate for this one test
HOUR, DAY = 3600, 86400
START = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
END = int(measure.END)                             # 2024-01-01: holdout from here, 2025+ reserved
FIRST, LAST = (2022, 1), (2023, 12)                # the only archive months that may be fetched or read
SPLITS = ("train3", "validation3")
TRAIN_LAST = mdata.SPLITS["train3"][1]             # (2023, 6)
VALID_FIRST = mdata.SPLITS["validation3"][0]       # (2023, 7)
TRAIN_END = mdata.window("train3")[1] + 1          # 2023-07-01 00:00 UTC
TITLE_MUST = ("Binance Futures Will Launch", "Perpetual")
EARLY, EARLY3, LATE = (0, 7 * DAY), (0, 3 * DAY), (30 * DAY, 60 * DAY)          # draft 3 (half-open (a, b])
P_EARLY, P_LATE = (90 * DAY, 97 * DAY), (120 * DAY, 150 * DAY)                    # draft 4: placebo start t0 + 90 d
SPAN, P_SPAN = 60 * DAY, 150 * DAY
MIN_N = {"train3": 20, "validation3": 8}           # draft 6
ROUND_TRIP = 0.0046                                # draft 3: F1's cost model, 0.46 % round trip
FLIP_DRAWS, FLIP_SEED = measure.FLIP_DRAWS, measure.FLIP_SEED   # exact for n <= 20, else 100,000 draws, seed 7
URL = ingest.BINANCE + "/monthly/fundingRate/{sym}/" + measure.FUNDING_FILE
BUDGET_BYTES = 200 * 10 ** 6                       # a couple of hundred small monthly files (16a point 3) fit easily
PAUSE_S, RETRIES = 0.2, 3
SLEEP = time.sleep                                 # replaced in tests


def _iso(ts):
    return measure._iso(ts) + " UTC" if ts is not None else None


def _ym(ts):
    d = datetime.fromtimestamp(ts, timezone.utc)
    return d.year, d.month


def _next(ym):
    return (ym[0] + 1, 1) if ym[1] == 12 else (ym[0], ym[1] + 1)


def _months(a, b):
    out = []
    while a <= b:
        out.append(a)
        a = _next(a)
    return out


# ---------- events ----------
def announcements(db_path):
    """Binance listing announcements of a USD-M perpetual launch, read-only from the registry."""
    if not db_path or not os.path.isfile(db_path):
        raise Refused(f"registry {db_path} not found (the announcements come from lab/news.py observations)")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT payload FROM observations WHERE detector=? AND metric='news_item' ORDER BY id",
                           (news.DETECTOR,)).fetchall()
    finally:
        con.close()
    out = []
    for (p,) in rows:
        x = json.loads(p) if isinstance(p, str) else p
        t = x.get("title") or ""
        if x.get("source") == "binance" and x.get("category") == "listing" and all(s in t for s in TITLE_MUST):
            out.append(x)
    return out


def events(items):
    """({symbol: earliest announcement}, [announcements that name no usable symbol]). Symbols come from news.coins
    (tokens in parentheses and XXXUSDT/USDC/FDUSD pairs) + 'USDT'; a COIN-M launch is not a USD-M listing."""
    per, skipped = {}, []
    for x in sorted(items, key=lambda x: (x.get("published_ts") or 0, x.get("key") or "")):
        t, pub = x.get("title") or "", x.get("published_ts")
        base = {"key": x.get("key"), "title": t, "published": _iso(pub) if pub else None}
        if not pub:
            skipped.append(base | {"reason": "no_publication_time"})
            continue
        if "COIN-M" in t.upper():
            skipped.append(base | {"reason": "coin_m_launch"})
            continue
        cs = news.coins(t)
        if not cs:
            skipped.append(base | {"reason": "no_coin_by_fixed_rules"})
        for c in cs:
            s = c + "USDT"
            if s in per:
                per[s]["later_announcements"] += 1
            else:
                per[s] = {"symbol": s, "published_ts": int(pub), "published": _iso(pub), "key": x.get("key"),
                          "title": t, "usable_from": x.get("usable_from"), "backfill": x.get("backfill"),
                          "later_announcements": 0}
    return per, skipped


def classify(per):
    """Phase of each symbol by its announcement (no data read): ('train3' | 'validation3' | exclusion reason)."""
    out = {}
    for s, e in per.items():
        p = e["published_ts"]
        if p < START:
            out[s] = ("announced_before_2022", "first settlement cannot be shown to lie in 2022-2023 without "
                      "pre-2022 data (a listing before train3 or a re-listing); not fetched")
        elif p >= END:
            out[s] = ("announced_after_2023", "2024 is holdout and 2025+ reserved; not fetched")
        elif p + SPAN >= END:
            out[s] = ("day60_after_2023", "t0 >= announcement, so day 60 lies after 2023-12-31; not fetched")
        else:
            out[s] = ("train3" if p < TRAIN_END else "validation3", None)
    return out


# ---------- archive access ----------
def fetch(url, path, budget, opener=None, free=None):
    """('downloaded' | 'cached', published sha256) or None when the archive has no such file. A download goes through
    ingest.checked (checksum verified, download budget, free-disk margin); a cached file's checksum is fetched so the
    Reader can verify it. Network errors are retried RETRIES times; a 404 is never retried."""
    last = None
    for i in range(RETRIES):
        try:
            budget["requests"] += 1
            if os.path.isfile(path):
                try:
                    want = ingest._text(url + ".CHECKSUM", opener).split()[0].strip().lower()
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        raise Refused(f"{url}: a cached file the archive no longer publishes a checksum for")
                    raise
                SLEEP(PAUSE_S)
                return "cached", want
            got = ingest.checked(url, path, budget["left"], opener, free)
            SLEEP(PAUSE_S)
            if got is None:
                return None
            budget["left"] -= got[0]
            budget["downloaded_bytes"] += got[0]
            budget["downloads"] += 1
            return "downloaded", got[1]
        except OSError as e:
            last = e
            SLEEP(2 * (i + 1))
    raise IOError(f"download failed after {RETRIES} attempts: {url}: {last!r}")


def new_budget():
    return {"left": BUDGET_BYTES, "requests": 0, "downloads": 0, "downloaded_bytes": 0}


class Reader:
    """Funding archive access for one phase. Refuses a month outside 2022-01..2023-12, a row outside 2022-01-01 ..
    2023-12-31 and a symbol not admitted to the phase. Every file read is recorded with its size and sha256."""

    def __init__(self, root, split, symbols, budget, opener=None, free=None):
        if split not in SPLITS:
            raise Refused(f"H4 reads only {SPLITS} (amendment 16a), not {split}")
        self.root, self.split, self.symbols, self.budget = root, split, frozenset(symbols), budget
        self.opener, self.free, self.files, self.absent, self._memo = opener, free, [], [], {}

    def month(self, sym, y, m):
        """{settlement hour ts: raw rate} of one archive month, or None when the archive has no such file."""
        if sym not in self.symbols:
            raise Refused(f"{sym} is not admitted to {self.split} (validation symbols only after a passed train gate)")
        if not FIRST <= (y, m) <= LAST:
            raise Refused(f"{sym} {y}-{m:02d}: only 2022-01..2023-12 may be fetched or read (amendment 16a point 3; "
                          "2024 is holdout, 2025+ reserved)")
        if (sym, y, m) in self._memo:
            return self._memo[sym, y, m]
        path = measure.path_of(self.root, "funding", sym, y, m)
        url = URL.format(sym=sym, y=y, m=m)
        got = fetch(url, path, self.budget, self.opener, self.free)
        if got is None:
            self.absent.append(f"{sym}-{y}-{m:02d}")
            self._memo[sym, y, m] = None
            return None
        raw = measure.read_bytes(path)
        sha = hashlib.sha256(raw).hexdigest()
        if sha != got[1]:
            raise Refused(f"{url}: cached sha256 {sha} does not match the published checksum {got[1]}")
        self.files.append({"path": os.path.relpath(path, self.root).replace("\\", "/"), "bytes": len(raw),
                           "sha256": sha, "split": self.split, "symbol": sym, "fetch": got[0],
                           "checksum": "verified"})
        out = {}
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                for r in csv.reader(io.TextIOWrapper(z.open(name), encoding="utf-8")):
                    if r and r[0][:1].isdigit():
                        ts = int(r[0]) // 1000
                        if not START <= ts < END:
                            raise Refused(f"{os.path.basename(path)}: row at {_iso(ts)} is outside 2022-01-01 .. "
                                          "2023-12-31 (amendment 16a point 3)")
                        out[ts - ts % HOUR] = float(r[2])
        self._memo[sym, y, m] = out
        return out


# ---------- measurement ----------
def per_8h(fr):
    """{ts: rate x 8 / hours since the previous settlement} (amendment 12i); the first settlement has no previous one
    and is left out (so is t0, draft 3)."""
    ts = sorted(fr)
    return {b: fr[b] * 8 / ((b - a) / HOUR) for a, b in zip(ts, ts[1:])}


def _in(series, t0, w):
    return [v for t, v in series.items() if t0 + w[0] < t <= t0 + w[1]]


def _mean(v):
    return sum(v) / len(v) if v else None


def y_value(fr, t0, early=EARLY, late=LATE):
    """(Y = F_early - F_late, F_early, F_late, settlements early, late); None values when a window is empty."""
    p = per_8h({t: r for t, r in fr.items() if t >= t0})
    e, l_ = _in(p, t0, early), _in(p, t0, late)
    fe, fl = _mean(e), _mean(l_)
    return (fe - fl if fe is not None and fl is not None else None), fe, fl, len(e), len(l_)


def _excl(e, split, reason, detail):
    return {"symbol": e["symbol"], "split": split, "announced": e["published"], "reason": reason, "detail": detail}


def measure_symbol(reader, e, search_from, search_to, check_before=True):
    """Draft 2-4 for one symbol. Returns {'deferred': True} when no settlement lies in search_from..search_to (train
    phase: the symbol belongs to validation3 if it has one later), an exclusion, or the measured row."""
    s, pub, sp = e["symbol"], e["published_ts"], reader.split
    am = _ym(pub)
    if check_before:                                   # a re-listing: an archive month before the announcement
        for y, m in _months(FIRST, (am[0], am[1] - 1) if am[1] > 1 else (am[0] - 1, 12)):
            if reader.month(s, y, m):
                return _excl(e, sp, "funding_before_announcement", f"settlements in {y}-{m:02d} (re-listing)")
    fr, t0 = {}, None
    for y, m in _months(max(search_from, am), search_to):
        rows = reader.month(s, y, m)
        if not rows:
            continue
        early = [t for t in rows if t < pub]
        if early:
            return _excl(e, sp, "funding_before_announcement", f"settlement at {_iso(min(early))} (re-listing)")
        fr, t0 = dict(rows), min(rows)
        break
    if t0 is None:
        if search_to < LAST:
            return {"deferred": True}
        return _excl(e, sp, "no_settlement", "no settlement after the announcement in the 2022-2023 archive")
    if t0 + SPAN >= END:
        return _excl(e, sp, "day60_after_2023", f"t0 {_iso(t0)}: day 60 lies after 2023-12-31")
    last_needed = _ym(min(t0 + P_SPAN, END - 1))
    for y, m in _months(_next(_ym(t0)), last_needed):
        fr.update(reader.month(s, y, m) or {})
    gone = {a for a in reader.absent if a.startswith(s + "-")}

    def gap(until):
        return [f"{y}-{m:02d}" for y, m in _months(_ym(t0), _ym(until)) if f"{s}-{y}-{m:02d}" in gone]
    if not any(t0 + SPAN <= t < END for t in fr):
        return _excl(e, sp, "fewer_than_60_days", f"t0 {_iso(t0)}, last settlement {_iso(max(fr))} "
                     "(delisted or archive ends before day 60)")
    if gap(t0 + SPAN):
        return _excl(e, sp, "archive_month_missing", f"months {', '.join(gap(t0 + SPAN))} absent inside t0..t0+60d")
    y, fe, fl, ne, nl = y_value(fr, t0)
    if y is None:
        return _excl(e, sp, "empty_window", f"settlements early {ne}, late {nl}")
    y3, fe3, _fl, n3, _nl = y_value(fr, t0, EARLY3)
    first60 = sorted(t for t in fr if t <= t0 + SPAN)
    row = {"symbol": s, "split": "train3" if t0 < TRAIN_END else "validation3", "announced": e["published"],
           "announcement_key": e["key"], "title": e["title"], "t0": _iso(t0), "Y": y, "F_early": fe, "F_late": fl,
           "n_early": ne, "n_late": nl, "Y_days_1_3": y3, "n_early_1_3": n3,
           "early_raw_sum": sum(r for t, r in fr.items() if t0 < t <= t0 + EARLY[1]),
           "intervals_h": sorted({(b - a) // HOUR for a, b in zip(first60, first60[1:])})}
    row["covers_round_trip"] = row["early_raw_sum"] >= ROUND_TRIP
    if t0 + P_SPAN >= END:
        row["placebo"] = {"Y": None, "reason": "day 150 lies after 2023-12-31"}
    elif not any(t0 + P_SPAN <= t < END for t in fr):
        row["placebo"] = {"Y": None, "reason": "no settlement on or after day 150"}
    elif gap(t0 + P_SPAN):
        row["placebo"] = {"Y": None, "reason": f"months {', '.join(gap(t0 + P_SPAN))} absent"}
    else:
        py, pe, pl, pne, pnl = y_value(fr, t0, P_EARLY, P_LATE)
        row["placebo"] = {"Y": py, "F_early": pe, "F_late": pl, "n_early": pne, "n_late": pnl}
    return row


def p_greater(ys):
    """One-sided sign-flip p for mean > 0: measure.sign_flip_p on -Y (exact for n <= 20, else 100,000 draws, seed 7,
    p = (k + 1) / (B + 1)); the flipped distribution is symmetric, so this is P(flipped sum >= observed sum)."""
    return measure.sign_flip_p([-y for y in ys], FLIP_DRAWS, FLIP_SEED)


def summary(rows, split):
    """Primary mean Y and the secondary figures (decide nothing): median Y, share covering a round trip, Y days 1-3,
    placebo at t0 + 90 d."""
    ys = [r["Y"] for r in rows]
    out = {"split": split, "n": len(ys), "symbols": [r["symbol"] for r in rows], "mean_Y": _mean(ys)}
    if not ys:
        return out
    y3 = [r["Y_days_1_3"] for r in rows if r["Y_days_1_3"] is not None]
    pl = [r["placebo"]["Y"] for r in rows if r["placebo"].get("Y") is not None]
    out["secondary"] = {"median_Y": statistics.median(ys),
                        "share_covering_round_trip": sum(r["covers_round_trip"] for r in rows) / len(rows),
                        "round_trip": ROUND_TRIP,
                        "Y_days_1_3": {"n": len(y3), "mean": _mean(y3)},
                        "placebo_t0_plus_90d": {"n": len(pl), "mean_Y": _mean(pl),
                                                "median_Y": statistics.median(pl) if pl else None},
                        "decisional": False}
    return out


def _code():
    here = os.path.abspath(__file__)
    with open(here, "rb") as f:
        out = {"file": "lab/measure_h4.py", "sha256": hashlib.sha256(f.read()).hexdigest()}
    try:
        from lab.registry import git
        out["commit"] = git("rev-parse", "HEAD")
        out["clean"] = not git("status", "--porcelain", "--", here)
    except Exception:
        out["commit"] = None
    return out


def _draft_sha():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), DRAFT), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _phase(res, root, split, todo, per, budget, opener, free, search):
    """Measure the symbols of one phase. Returns (rows, deferred symbols)."""
    r = Reader(root, split, todo, budget, opener, free)
    rows, deferred = [], []
    try:
        for s in sorted(todo):
            frm, to, before = search(s)
            out = measure_symbol(r, per[s], frm, to, before)
            if out.get("deferred"):
                deferred.append(s)
            elif out.get("reason"):
                res["excluded"].append(out)
            else:
                rows.append(out)
    finally:
        res["inputs"] += r.files
        res["absent_months"] += r.absent
    return rows, deferred


def run(root=None, db_path=None, opener=None, free=None):
    """One measurement (amendment 16a point 1): events -> train3 symbols -> train gate -> (only then) validation3
    symbols. Returns a JSON-serialisable dict with verdict PASS, REJECTED or UNTESTABLE."""
    root = root or mdata.CACHE
    if _draft_sha() != DRAFT_SHA256:
        raise Refused(f"{DRAFT} differs from the text locked by amendment 16a (sha256 {DRAFT_SHA256})")
    res = {"hypothesis": HYPOTHESIS, "name": NAME, "rule": RULE, "draft": DRAFT, "draft_sha256": DRAFT_SHA256,
           "alpha": ALPHA, "splits": list(SPLITS), "seeds": {"sign_flip": FLIP_SEED},
           "sign_flip": {"exact_max_n": measure.EXACT_MAX, "draws": FLIP_DRAWS, "p": "(k + 1) / (B + 1)"},
           "code": _code(), "started": _iso(time.time()), "validation_read": False, "inputs": [],
           "absent_months": [], "excluded": [], "decisional_for_trading": False}
    budget = new_budget()

    def done(verdict, reason):
        counts = {}
        for x in res["excluded"]:
            counts[x["reason"]] = counts.get(x["reason"], 0) + 1
        res["excluded_counts"] = dict(sorted(counts.items()))
        res["network"] = {k: v for k, v in budget.items() if k != "left"}
        res["verdict"], res["reason"] = verdict, reason
        res["finished"] = _iso(time.time())
        return res
    items = announcements(db_path)
    per, skipped = events(items)
    res["announcements"] = {"matching": len(items), "symbols": len(per), "skipped": skipped,
                            "skipped_counts": {k: sum(1 for x in skipped if x["reason"] == k)
                                               for k in sorted({x["reason"] for x in skipped})}}
    phase = classify(per)
    for s in sorted(phase):
        if phase[s][0] not in SPLITS:
            res["excluded"].append(_excl(per[s], None, *phase[s]))
    train = [s for s in phase if phase[s][0] == "train3"]
    valid = [s for s in phase if phase[s][0] == "validation3"]
    res["train"], deferred = _phase(res, root, "train3", train, per, budget, opener, free,
                                    lambda s: (FIRST, TRAIN_LAST, True))
    res["train"] = summary(res["train"], "train3") | {"rows": res["train"]}
    res["deferred_to_validation3"] = sorted(deferred)
    if res["train"]["n"] < MIN_N["train3"]:
        return done("UNTESTABLE", f"{res['train']['n']} symbols in train3 (minimum {MIN_N['train3']}); "
                                  "validation3 not read")
    res["train_gate"] = res["train"]["mean_Y"] > 0
    if not res["train_gate"]:
        return done("REJECTED", "train gate failed (mean Y <= 0); validation3 not read")
    res["validation_read"] = True
    rows, _none = _phase(res, root, "validation3", valid + deferred, per, budget, opener, free,
                         lambda s: (VALID_FIRST, LAST, s not in deferred))
    res["validation"] = summary(rows, "validation3") | {"rows": rows}
    n = res["validation"]["n"]
    if n < MIN_N["validation3"]:
        return done("UNTESTABLE", f"{n} symbols in validation3 (minimum {MIN_N['validation3']})")
    p = p_greater([r["Y"] for r in rows])
    res["validation"] |= {"sign_flip_p": p, "sign_flip": "exact" if n <= measure.EXACT_MAX else f"{FLIP_DRAWS} draws"}
    ok = p < ALPHA
    return done("PASS" if ok else "REJECTED", f"one-sided sign-flip p {p:.4f} {'<' if ok else '>='} alpha {ALPHA}")


# ---------- H5 notering_lav (amendment 16c): the data-suggested opposite of H4, on listings H4 never read ----------
H5_RULE = "research/PROTOCOL_V3.md amendment 16c"
H5_DRAFT = "research/drafts/H5_NOTERING_LAV.md"
H5_DRAFT_SHA256 = "71b6058b6ca29f9e7c2e63309d429b0ccc0b153d34a220173cf7dfbc08a143c6"   # amendment 16c point 1
H5_ARTIFACT_ID = "MEASURE_16c"
H5_MIN_N = 8


def p_less(ys):
    """One-sided sign-flip p for mean < 0 (exact for n <= 20, else 100,000 draws, seed 7, p = (k + 1) / (B + 1))."""
    return measure.sign_flip_p(list(ys), FLIP_DRAWS, FLIP_SEED)


def run_h5(root=None, db_path=None, opener=None, free=None):
    """Amendment 16c: only symbols announced in 2023-07..2023-12 whose first settlement lies there too (draft 2);
    no train gate (H4's train is the hypothesis' source); one-sided test of mean Y < 0 at alpha 0.05."""
    root = root or mdata.CACHE
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), H5_DRAFT), "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != H5_DRAFT_SHA256:
            raise Refused(f"{H5_DRAFT} differs from the text locked by amendment 16c (sha256 {H5_DRAFT_SHA256})")
    res = {"hypothesis": "H5", "name": "notering_lav", "rule": H5_RULE, "draft": H5_DRAFT,
           "draft_sha256": H5_DRAFT_SHA256, "alpha": ALPHA, "splits": ["validation3"],
           "seeds": {"sign_flip": FLIP_SEED}, "code": _code(), "started": _iso(time.time()), "inputs": [],
           "absent_months": [], "excluded": [], "decisional_for_trading": False}
    budget = new_budget()
    items = announcements(db_path)
    per, skipped = events(items)
    res["announcements"] = {"matching": len(items), "symbols": len(per),
                            "skipped_counts": {k: sum(1 for x in skipped if x["reason"] == k)
                                               for k in sorted({x["reason"] for x in skipped})}}
    phase = classify(per)
    valid = []
    for s in sorted(phase):
        if phase[s][0] == "validation3":
            valid.append(s)
        elif phase[s][0] == "train3":
            res["excluded"].append(_excl(per[s], None, "announced_before_2023_07", "H4's train window: not H5's sample"))
        else:
            res["excluded"].append(_excl(per[s], None, *phase[s]))
    rows, _none = _phase(res, root, "validation3", valid, per, budget, opener, free,
                         lambda s: (VALID_FIRST, LAST, True))
    rows = [r for r in rows if r["split"] == "validation3"]
    res["validation"] = summary(rows, "validation3") | {"rows": rows}
    if rows:
        res["validation"]["secondary"]["share_negative_early_sum"] = (
            sum(1 for r in rows if r["early_raw_sum"] < 0) / len(rows))
    counts = {}
    for x in res["excluded"]:
        counts[x["reason"]] = counts.get(x["reason"], 0) + 1
    res["excluded_counts"] = dict(sorted(counts.items()))
    res["network"] = {k: v for k, v in budget.items() if k != "left"}
    n = len(rows)
    if n < H5_MIN_N:
        res["verdict"], res["reason"] = "UNTESTABLE", f"{n} symbols (minimum {H5_MIN_N})"
    else:
        p = p_less([r["Y"] for r in rows])
        res["validation"] |= {"sign_flip_p": p, "sign_flip": "exact" if n <= measure.EXACT_MAX else f"{FLIP_DRAWS} draws"}
        ok = p < ALPHA
        res["verdict"] = "PASS" if ok else "REJECTED"
        res["reason"] = f"one-sided sign-flip p (mean Y < 0) {p:.4f} {'<' if ok else '>='} alpha {ALPHA}"
    res["finished"] = _iso(time.time())
    return res
