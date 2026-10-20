"""Amendment 14 (research/PROTOCOL_V3.md): new free data sources, fetched one unit at a time by the data agent.

- aggTrades (data.binance.vision, monthly): summarised per hour and coin, with the traded notional in four size
  classes; the raw file is deleted after the summary.
- bookDepth (data.binance.vision, daily, from 2023-01): notional at +-1..5 % from the mid, summarised per hour.
- Wikipedia pageviews (wikimedia.org REST, daily, human users): attention as a time-stamped news proxy.
- FOMC statement times (federalreserve.gov) and BLS CPI / Employment Situation release times (bls.gov): times only,
  never the released figures.

Guards: nothing after 2023-12-31 (2024 is holdout, 2025+ reserved); each Binance file is checked against its
.CHECKSUM; a 10 GB download budget; at least 2 GB free disk beyond what is being written. Every finished unit is an
`ingest.done` event (URL, bytes, sha256, rows, output file and its sha256). Data only: nothing here is evidence, and a
strategy that uses it needs its own hypothesis committed before a test (point 6).
"""
from __future__ import annotations

import calendar
import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from lab import jobs
from lab.data import sha256_file
from lab.engine import data as mdata

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
END = datetime(2024, 1, 1, tzinfo=UTC).timestamp()        # point 2: nothing at or after this is fetched
BUDGET_BYTES = 10 * 10 ** 9                                 # point 4: more needs the user's yes
MARGIN = 2 * 1024 ** 3                                      # point 5: free disk kept beyond the file being written
CHUNK = 1 << 20
UA = "copybot-research/1.0 (amendment 14; public data)"
BINANCE = "https://data.binance.vision/data/futures/um"
WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user"
FOMC_HIST = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"
FOMC_CAL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BLS = "https://www.bls.gov/schedule/{year}/home.htm"
UNIVERSE = mdata.UNIVERSE
MONTHS = tuple(f"2023-{m:02d}" for m in range(1, 13))
YEARS = (2020, 2021, 2022, 2023)
ARTICLES = ("Bitcoin", "Ethereum", "Cryptocurrency", "Binance", "Ripple_Labs", "Dogecoin",
            "Cardano_(blockchain_platform)", "Chainlink_(blockchain)", "Litecoin", "Avalanche_(blockchain_platform)",
            "Polkadot_(cryptocurrency)")
PAGEVIEW_LAG_S = 2 * 86400            # point 3: a day's count is used from D+2 00:00 UTC
SIZE_EDGES = (1_000, 10_000, 100_000)  # point 1: notional classes < 1k, 1k-10k, 10k-100k, >= 100k USD
DEPTH_LEVELS = (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
ROOT = os.path.join(mdata.CACHE, "ingest")
JOB = {"priority": 80, "max_attempts": 3, "timeout_s": 3600}
ACTOR = "system:ingest"


class Refused(Exception):
    """A unit the amendment does not allow (period, checksum, budget, disk): never retried."""


# ---------- plan ----------
def plan():
    """Every unit of the pilot, small ones first: calendars, pageviews, book depth, then trades."""
    out = [f"fomc|{y}" for y in YEARS] + [f"bls|{y}" for y in YEARS] + [f"pageviews|{a}" for a in ARTICLES]
    out += [f"bookdepth|{c}|{m}" for m in MONTHS for c in UNIVERSE]
    out += [f"aggtrades|{c}|{m}" for m in MONTHS for c in UNIVERSE]
    return out


def _month_bounds(month):
    y, m = map(int, month.split("-"))
    a = datetime(y, m, 1, tzinfo=UTC).timestamp()
    return a, a + calendar.monthrange(y, m)[1] * 86400


def guard(unit):
    """Point 2: a unit that ends after 2023-12-31 is refused."""
    parts = unit.split("|")
    if parts[0] in ("aggtrades", "bookdepth"):
        end = _month_bounds(parts[2])[1]
    elif parts[0] in ("fomc", "bls"):
        end = datetime(int(parts[1]) + 1, 1, 1, tzinfo=UTC).timestamp()
    elif parts[0] == "pageviews":
        end = END
    else:
        raise Refused(f"unknown unit {unit}")
    if end > END:
        raise Refused(f"{unit} ends after 2023-12-31: 2024 is holdout and 2025+ is reserved (amendment 14 point 2)")
    return end


# ---------- network ----------
def _open(url, timeout=120):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)


def _text(url, opener=None):
    with (opener or _open)(url) as r:
        return r.read().decode("utf-8-sig")


def download(url, path, budget_left, opener=None, free=None):
    """Stream `url` to `path`; returns (bytes, sha256) or None for a 404. Refuses when the budget or the free disk
    would be crossed."""
    free = free or (lambda: shutil.disk_usage(os.path.dirname(path)).free)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part, n, h = f"{path}.{os.getpid()}.part", 0, hashlib.sha256()
    try:
        with (opener or _open)(url) as r, open(part, "wb") as f:
            size = int((getattr(r, "headers", None) or {}).get("Content-Length") or 0)
            if size and size > budget_left:
                raise Refused(f"{url}: {size} bytes would exceed the download budget ({budget_left} left)")
            if size and free() < MARGIN + size:
                raise Refused(f"{url}: less than 2 GB free disk beyond {size} bytes")
            for chunk in iter(lambda: r.read(CHUNK), b""):
                n += len(chunk)
                if n > budget_left:
                    raise Refused(f"{url}: download budget reached ({budget_left} bytes left)")
                f.write(chunk)
                h.update(chunk)
        if free() < MARGIN:
            raise Refused(f"{url}: less than 2 GB free disk after download")
        os.replace(part, path)
        return n, h.hexdigest()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    finally:
        if os.path.exists(part):
            os.remove(part)


def checked(url, path, budget_left, opener=None, free=None):
    """A Binance file verified against its published .CHECKSUM (point 5)."""
    try:
        want = _text(url + ".CHECKSUM", opener).split()[0].strip().lower()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None                                                    # no such file published
        raise
    got = download(url, path, budget_left, opener, free)
    if got is None:
        return None
    if got[1] != want:
        os.remove(path)
        raise Refused(f"{url}: sha256 {got[1]} does not match the published checksum {want}")
    return got


# ---------- summaries ----------
def _csv_rows(zpath):
    with zipfile.ZipFile(zpath) as z:
        with z.open(z.namelist()[0]) as f:
            for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                if row and row[0][:1].isdigit():                      # older files have no header line
                    yield row


def _bucket(usd):
    return sum(usd >= e for e in SIZE_EDGES)


TRADE_COLS = (["hour_ts", "available_ts", "trades", "buy_qty", "sell_qty", "buy_usd", "sell_usd"]
              + [f"{s}_usd_{b}" for s in ("buy", "sell") for b in ("lt1k", "1k_10k", "10k_100k", "ge100k")]
              + ["max_trade_usd", "vwap"])


def summarise_trades(zpath):
    """Per hour: counts, bought/sold quantity and notional, notional per size class, largest trade, VWAP. The taker is
    the buyer unless is_buyer_maker is true (then the seller took liquidity)."""
    hours = {}
    for r in _csv_rows(zpath):
        px, qty, ts_ms, maker = float(r[1]), float(r[2]), int(r[5]), r[6].strip().lower() == "true"
        usd = px * qty
        h = hours.setdefault(ts_ms // 3_600_000 * 3600, [0, 0.0, 0.0, 0.0, 0.0, [0.0] * 4, [0.0] * 4, 0.0])
        side = 1 if maker else 0                                     # 0 = taker bought, 1 = taker sold
        h[0] += 1
        h[1 + side] += qty
        h[3 + side] += usd
        h[5 + side][_bucket(usd)] += usd
        h[7] = max(h[7], usd)
    rows = []
    for t in sorted(hours):
        n, bq, sq, bu, su, bb, sb, mx = hours[t]
        rows.append([t, t + 3600, n, bq, sq, bu, su, *bb, *sb, mx, (bu + su) / (bq + sq) if bq + sq else None])
    return rows


DEPTH_COLS = (["hour_ts", "available_ts", "snapshots"] + [f"mean_usd_{l:+d}" for l in DEPTH_LEVELS]
              + [f"min_usd_{l:+d}" for l in DEPTH_LEVELS])


def summarise_depth(zpaths):
    """Per hour: number of snapshots and the mean and minimum notional at each level (+-1..5 %)."""
    hours = {}
    for zp in zpaths:
        for r in _csv_rows(zp):
            ts = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
            lvl, usd = int(float(r[1])), float(r[3])
            if lvl not in DEPTH_LEVELS:
                continue
            h = hours.setdefault(int(ts) // 3600 * 3600, {"snaps": set(), "lv": {}})
            h["snaps"].add(int(ts))
            s = h["lv"].setdefault(lvl, [0.0, 0, None])
            s[0] += usd
            s[1] += 1
            s[2] = usd if s[2] is None else min(s[2], usd)
    rows = []
    for t in sorted(hours):
        lv = hours[t]["lv"]
        mean = [lv[l][0] / lv[l][1] if l in lv else None for l in DEPTH_LEVELS]
        low = [lv[l][2] if l in lv else None for l in DEPTH_LEVELS]
        rows.append([t, t + 3600, len(hours[t]["snaps"]), *mean, *low])
    return rows


def _write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = f"{path}.{os.getpid()}.part"
    with gzip.open(part, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    os.replace(part, path)
    return path


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = f"{path}.{os.getpid()}.part"
    with open(part, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(part, path)
    return path


# ---------- calendars ----------
MONTHS_EN = {m: i for i, m in enumerate(calendar.month_name) if m}
MONTHS_EN.update({m[:3]: i for m, i in list(MONTHS_EN.items())})


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET).astimezone(UTC).timestamp()


def _meeting_day(year, month_txt, day_txt):
    """'Jan/Feb' + '31-1' -> (year, 2, 1): the statement comes on the last day of the meeting."""
    mons = [MONTHS_EN[x.strip()] for x in month_txt.split("/")]
    days = [int(x) for x in re.findall(r"\d+", day_txt)]
    m = mons[-1] if len(days) > 1 and days[-1] < days[0] else mons[0]
    return year, m, days[-1]


def parse_fomc(html, year):
    """FOMC statements of `year`: scheduled meetings at 14:00 ET on their last day (known in advance); unscheduled
    meetings and notation votes are listed with no time and scheduled=False (not known in advance, point 3);
    cancelled meetings are listed as cancelled."""
    out = []
    if f"{year} FOMC Meetings" in html:                                   # the current calendar page (2021 onwards)
        i = html.find(f"{year} FOMC Meetings")
        j = html.find("FOMC Meetings", i + 20)
        seg = html[i:j if j > 0 else None]
        rows = re.findall(r'fomc-meeting__month[^>]*>(?:\s*<strong>)?\s*([^<]+?)\s*<.*?fomc-meeting__date[^>]*>\s*'
                          r'([^<]+?)\s*<', seg, re.S)
    else:                                                                 # a historical year page
        rows = [(m, d) for m, d in re.findall(r"<h5[^>]*>\s*([A-Z][a-z]+(?:/[A-Z][a-z]+)?)\s+(\d[^<]*?)\s*"
                                              r"(?:Meeting)?\s*-\s*" + str(year) + r"\s*</h5>", html)]
    for month_txt, day_txt in rows:
        low = day_txt.lower()
        y, m, d = _meeting_day(year, month_txt, day_txt.split("(")[0])
        kind = ("cancelled" if "cancelled" in low else "unscheduled" if "unscheduled" in low else
                "notation vote" if "notation" in low else "scheduled")
        out.append({"event": "FOMC statement", "date": f"{y}-{m:02d}-{d:02d}", "kind": kind,
                    "scheduled": kind == "scheduled", "sep": "*" in day_txt,
                    "ts": _et(y, m, d, 14, 0) if kind == "scheduled" else None})
    return out


BLS_ROW = re.compile(r'<td class="date-cell"><p>([^<]+)</p></td>\s*<td class="time-cell"><p>([^<]+)</p></td>\s*'
                     r'<td class="desc-cell"><p><strong>([^<]+)</strong>\s*([^<]*)', re.S)
BLS_KEEP = ("Consumer Price Index", "Employment Situation")


def parse_bls(html, year):
    out = []
    for date_txt, time_txt, name, ref in BLS_ROW.findall(html):
        name = name.strip()
        if name not in BLS_KEEP:
            continue
        d = datetime.strptime(date_txt.strip().split(", ", 1)[1], "%B %d, %Y")
        t = datetime.strptime(time_txt.strip(), "%I:%M %p")
        if d.year != year:
            continue
        out.append({"event": name, "reference": ref.strip(), "date": d.strftime("%Y-%m-%d"), "scheduled": True,
                    "ts": _et(d.year, d.month, d.day, t.hour, t.minute)})
    return out


# ---------- units ----------
def _tmp():
    return os.path.join(ROOT, ".raw")


def run_unit(unit, budget_left, opener=None, free=None, root=None):
    """Fetch and summarise one unit. Returns the ingest.done payload (without the event bookkeeping)."""
    root = root or ROOT
    guard(unit)
    kind, *rest = unit.split("|")
    raw = os.path.join(root, ".raw")
    if kind == "aggtrades":
        coin, month = rest
        url = f"{BINANCE}/monthly/aggTrades/{coin}/{coin}-aggTrades-{month}.zip"
        zp = os.path.join(raw, os.path.basename(url))
        try:
            got = checked(url, zp, budget_left, opener, free)
            if got is None:
                return {"unit": unit, "missing": [url], "bytes": 0, "rows": 0}
            rows = summarise_trades(zp)
        finally:
            if os.path.exists(zp):
                os.remove(zp)                                              # point 5: the raw file is not kept
        out = _write_csv(os.path.join(root, "aggtrades_1h", f"{coin}-{month}.csv.gz"), TRADE_COLS, rows)
        return {"unit": unit, "urls": [url], "bytes": got[0], "sha256": [got[1]], "rows": len(rows), "out": out}
    if kind == "bookdepth":
        coin, month = rest
        a, b = _month_bounds(month)
        files, shas, missing, n = [], [], [], 0
        try:
            for t in range(int(a), int(b), 86400):
                day = time.strftime("%Y-%m-%d", time.gmtime(t))
                url = f"{BINANCE}/daily/bookDepth/{coin}/{coin}-bookDepth-{day}.zip"
                zp = os.path.join(raw, os.path.basename(url))
                got = checked(url, zp, budget_left - n, opener, free)
                if got is None:
                    missing.append(day)
                    continue
                n += got[0]
                files.append(zp)
                shas.append(got[1])
            rows = summarise_depth(files)
        finally:
            for zp in files:
                if os.path.exists(zp):
                    os.remove(zp)
        out = _write_csv(os.path.join(root, "bookdepth_1h", f"{coin}-{month}.csv.gz"), DEPTH_COLS, rows)
        return {"unit": unit, "bytes": n, "files": len(shas), "sha256": shas, "missing_days": missing,
                "rows": len(rows), "out": out}
    if kind == "pageviews":
        (article,) = rest
        url = f"{WIKI}/{urllib.parse.quote(article, safe='')}/daily/20200101/20231231"
        try:
            body = _text(url, opener)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            body = '{"items": []}'
        items = json.loads(body).get("items", [])
        rows = []
        for x in items:
            day = datetime.strptime(x["timestamp"][:8], "%Y%m%d").replace(tzinfo=UTC).timestamp()
            rows.append({"date": time.strftime("%Y-%m-%d", time.gmtime(day)), "views": x["views"],
                         "available_ts": day + PAGEVIEW_LAG_S})
        out = _write_json(os.path.join(root, "pageviews", f"{article}.json"),
                          {"article": article, "source": url, "rule": "amendment 14 point 3: usable from D+2 00:00 UTC",
                           "rows": rows})
        return {"unit": unit, "urls": [url], "bytes": len(body), "rows": len(rows), "out": out,
                "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None}
    if kind in ("fomc", "bls"):
        year = int(rest[0])
        url = (FOMC_HIST.format(year=year) if year <= 2020 else FOMC_CAL) if kind == "fomc" else BLS.format(year=year)
        html = _text(url, opener)
        events = parse_fomc(html, year) if kind == "fomc" else parse_bls(html, year)
        if not events:
            raise Refused(f"{url}: no {kind.upper()} events parsed for {year} (page layout changed?)")
        out = _write_json(os.path.join(root, "calendar", f"{kind}-{year}.json"),
                          {"source": url, "year": year, "events": events,
                           "rule": "amendment 14 point 3: scheduled times are known in advance; no released figures"})
        return {"unit": unit, "urls": [url], "bytes": len(html), "rows": len(events), "out": out}
    raise Refused(f"unknown unit {unit}")


# ---------- registry ----------
def done_units(db):
    return {json.loads(r["payload"])["unit"]: json.loads(r["payload"]) for r in
            db.q("SELECT payload FROM events WHERE kind='ingest.done' ORDER BY id")}


def spent(db):
    return sum(int(p.get("bytes") or 0) for p in done_units(db).values())


def clear_raw(root=None):
    """Remove raw files left by an interrupted unit (a stopped fleet never reaches the unit's own cleanup). Safe because
    only one ingest job runs at a time (enqueue). Returns the number of files removed."""
    raw, n = os.path.join(root or ROOT, ".raw"), 0
    if os.path.isdir(raw):
        for f in os.scandir(raw):
            if f.is_file():
                os.remove(f.path)
                n += 1
    return n


def step_ingest(db, job, worker, opener=None, free=None, root=None):
    from lab import pipeline
    unit = (job.get("payload") or {}).get("unit")
    if unit in done_units(db):
        return {"unit": unit, "skipped": "already done"}
    clear_raw(root)
    left = BUDGET_BYTES - spent(db)
    try:
        out = run_unit(unit, left, opener, free, root)
    except Refused as e:
        db.event("ingest.refused", f"system:{worker}", None, {"unit": unit, "reason": str(e)[:300]})
        raise pipeline.StepError(str(e)) from None                       # not retried
    if out.get("out"):
        out["out_sha256"] = sha256_file(out["out"])
        out["out"] = os.path.relpath(out["out"], os.path.dirname(root or ROOT))
    out["decisional"] = False
    db.event("ingest.done", f"system:{worker}", None, out)
    return {k: v for k, v in out.items() if k != "sha256"}


def auto(db):
    """Only the lab's own database queues ingestion: a test database never leads the data agent to the network."""
    from lab.db import DEFAULT_DB
    return os.path.abspath(getattr(db, "path", "") or "") == os.path.abspath(DEFAULT_DB)


def enqueue(db, now=None, actor="strategy-1"):
    """One ingest job at a time (point 5), in plan order, while the budget lasts. Returns the number of new jobs."""
    jobs.init(db)
    if db.one("SELECT 1 FROM jobs WHERE kind='ingest' AND status IN ('queued', 'running', 'blocked')"):
        return 0
    if spent(db) >= BUDGET_BYTES:
        return 0
    seen = {r["job_id"] for r in db.q("SELECT job_id FROM jobs WHERE kind='ingest'")}
    done = done_units(db)
    for unit in plan():
        if unit in done or f"ingest|{unit}" in seen:
            continue
        return jobs.enqueue(db, f"ingest|{unit}", "ingest", None, {"unit": unit}, actor=f"system:{actor}", now=now,
                            **JOB)[1]
    return 0


def status(db):
    """For the coverage panel: units done per source, bytes spent of the budget, refusals and failed jobs."""
    done = done_units(db)
    units = plan()
    by = {}
    for u in units:
        k = u.split("|")[0]
        b = by.setdefault(k, {"source": k, "units": 0, "done": 0, "rows": 0, "bytes": 0})
        b["units"] += 1
        if u in done:
            b["done"] += 1
            b["rows"] += int(done[u].get("rows") or 0)
            b["bytes"] += int(done[u].get("bytes") or 0)
    failed = [r["job_id"].split("|", 1)[1] for r in db.q("SELECT job_id FROM jobs WHERE kind='ingest' AND "
                                                          "status='failed'")] if _has_jobs(db) else []
    refused = [json.loads(r["payload"]) for r in db.q("SELECT payload FROM events WHERE kind='ingest.refused' "
                                                      "ORDER BY id DESC LIMIT 10")]
    s = spent(db)                                       # the same figure the budget check uses
    return {"by_source": list(by.values()), "spent_bytes": s, "budget_bytes": BUDGET_BYTES,
            "budget_left_bytes": max(0, BUDGET_BYTES - s), "units": len(units), "done": len(done),
            "failed": failed, "refused": refused, "rule": "research/PROTOCOL_V3.md amendment 14"}


def _has_jobs(db):
    return bool(db.one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'"))
