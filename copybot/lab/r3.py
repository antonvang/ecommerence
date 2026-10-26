"""PROTOCOL_V3 amendment 24: R3 - the minute reaction to scheduled macro releases, screened in explore0 (method m24).

Per coin (BTC, ETH) and release T: minute bar k opens at T + k min; s = sign ln(C_0 / O_0); y = s * ln(C_61 / C_1)
(entry at bar 1's close, T + 2 min; exit at bar 61's close, T + 62 min). The event's y is the mean over the coins with
bars 0, 1 and 61. Placebo: the same rule 7 days earlier (14 if that UTC day had a calendar event). Clusters are UTC
days; the verdict is J1's rule (m21iscreen.judge). Exploration, never evidence.

The 44 monthly 1-minute files are fetched only from 2026-11-14 00:00 UTC (the user's rule) or, with amendment 24a, in
K3-free slots 2026-10-27 14:35 .. 10-31 00:00 UTC (after the S7 test reboot, before pm_lp's D1), at most 2 downloads at a
time (the lab's shared slots), and only from data.binance.vision for BTCUSDT/ETHUSDT 2020-03..2021-12.

  python3 -m lab.r3 fetch             download the missing files (refused outside amendment 24a's windows)
  python3 -m lab.r3 run --out PATH    one screening; writes PATH.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import zipfile
from datetime import datetime, timezone

from lab import families, hypogen, m21iscreen, m21jscreen
from lab.engine import data

METHOD, RULE = "m24", "research/PROTOCOL_V3.md amendment 24"
KEY = f"macro_release|minute_drift_60m|{METHOD}"
SYMS = ("BTCUSDT", "ETHUSDT")
MINUTE, DAY, WEEK = 60, 86400, 7 * 86400
ENTRY_BAR, EXIT_BAR = 1, 61
FETCH_FROM = int(datetime(2026, 11, 14, tzinfo=timezone.utc).timestamp())
EARLY = (int(datetime(2026, 10, 27, 14, 35, tzinfo=timezone.utc).timestamp()),     # 24a: after the S7 test reboot,
         int(datetime(2026, 10, 31, tzinfo=timezone.utc).timestamp()))             # before pm_lp's D1 (10-31..11-13)
HOST = "https://data.binance.vision/data/futures/um/monthly/klines"
MONTHS = [(y, m) for y in (2020, 2021) for m in range(1, 13) if (y, m) >= (2020, 3)]      # explore0: 2020-03..2021-12


class Refused(RuntimeError):
    pass


def k3_free(now):
    """Amendment 24a: a K3-free slot, XX:35..(XX+1):25 UTC with XX even (amendment 22's rounds are every even hour +- 35 min)."""
    g = time.gmtime(now)
    return (g.tm_hour % 2 == 0 and g.tm_min >= 35) or (g.tm_hour % 2 == 1 and g.tm_min < 25)


def allowed(now):
    """Amendment 24 point 2 with 24a: from 2026-11-14 00:00 UTC, or inside the early window and a K3-free slot."""
    return now >= FETCH_FROM or (EARLY[0] <= now < EARLY[1] and k3_free(now))


def url(sym, y, m):
    return f"{HOST}/{sym}/1m/{sym}-1m-{y}-{m:02d}.zip"


def path(sym, y, m):
    return os.path.join(data.CACHE, "klines_1m", f"{sym}-1m-{y}-{m:02d}.zip")


def log_path():
    return os.path.join(data.CACHE, "klines_1m", "fetch_log.jsonl")


def _log(entry):
    os.makedirs(os.path.dirname(log_path()), exist_ok=True)
    with open(log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def fetch(now=None, get=None, clock=None):
    """Point 2 with 24a: download the missing files; refused outside `allowed`. A 404 is recorded, never replaced.
    Every run, a refused one too, appends one entry to fetch_log.jsonl (precision 2026-10-25). In the early window each
    file is checked again: a run that leaves the window stops, and the rest is recorded as `stopped` (24a)."""
    clock = clock or ((lambda: now) if now is not None else time.time)
    now = clock()
    if not allowed(now):
        why = "outside amendment 24a's window (2026-10-27 14:35 .. 10-31 00:00 UTC, K3-free slots) and before 2026-11-14"
        _log({"ts": int(now), "status": "refused", "why": why})
        raise Refused(f"amendment 24 point 2 / 24a: no historical request now: {why}")
    out = {"fetched": [], "present": [], "absent": [], "failed": []}
    files = {}
    for sym in SYMS:
        for y, m in MONTHS:
            p = path(sym, y, m)
            name = os.path.basename(p)
            if os.path.exists(p):
                out["present"].append(name)
                files[name] = {"status": "present"}
                continue
            if not allowed(clock()):                          # 24a: the window or the K3-free slot ended
                out.setdefault("stopped", []).append(name)
                files[name] = {"status": "stopped"}
                continue
            try:
                with families._download_slot():
                    blob = (get or families._urlopen)(url(sym, y, m))
            except urllib.error.HTTPError as e:
                key = "absent" if e.code == 404 else "failed"
                out[key].append(name)
                files[name] = {"status": key, "error": f"HTTP {e.code}"}
                continue
            except Exception as e:                           # noqa: BLE001 - recorded; the next run tries again
                out["failed"].append(name)
                files[name] = {"status": "failed", "error": f"{e!r}"[:200]}
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p + ".part", "wb") as f:
                f.write(blob)
            os.replace(p + ".part", p)
            out["fetched"].append(name)
            files[name] = {"status": "fetched", "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
    _log({"ts": int(now), "status": "ran", "counts": {k: len(v) for k, v in out.items()}, "files": files})
    return out


def bars(sym):
    """({minute open ts: (open, close)}, [{file, sha256}]) from the cached explore0 files (a header row is skipped)."""
    out, files = {}, []
    for y, m in MONTHS:
        p = path(sym, y, m)
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            blob = f.read()
        files.append({"file": os.path.basename(p), "sha256": hashlib.sha256(blob).hexdigest()})
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for name in z.namelist():
                for row in csv.reader(io.TextIOWrapper(z.open(name), encoding="utf-8")):
                    if not row or not row[0].strip().isdigit():
                        continue
                    t = int(row[0]) // 1000
                    out[t] = (float(row[1]), float(row[4]))
    return out, files


def reaction(b, t):
    """Point 4 for one coin: (y, None) or (None, reason)."""
    need = [t + k * MINUTE for k in (0, ENTRY_BAR, EXIT_BAR)]
    if any(x not in b for x in need):
        return None, "missing minute bar"
    o0, c0 = b[need[0]]
    if o0 <= 0 or c0 <= 0 or b[need[1]][1] <= 0 or b[need[2]][1] <= 0:
        return None, "non-positive price"
    r0 = math.log(c0 / o0)
    if r0 == 0:
        return None, "flat first bar (s = 0)"
    s = 1 if r0 > 0 else -1
    return s * math.log(b[need[2]][1] / b[need[1]][1]), None


def _event(px, vol, t, excl):
    ys, cs = [], []
    for sym in SYMS:
        y, why = reaction(px.get(sym, {}), t)
        if y is None:
            excl[why] = excl.get(why, 0) + 1
            continue
        ys.append(y)
        cs.append(m21iscreen.cost(vol.get(sym, {}), t - t % 3600) or m21iscreen.FLOOR)
    return (statistics.fmean(ys), statistics.fmean(cs)) if ys else (None, None)


def screen(px, vol, events, busy, a, b):
    """Points 4-6 on loaded bars: J1's judge on UTC-day clusters, placebo -7 d (-14 d on a calendar day)."""
    rows, pl_rows, excl, pl_excl = [], [], {}, {}
    for t, ev in events:
        if not a <= t < b:
            continue
        y, c = _event(px, vol, t, excl)
        if y is not None:
            rows.append({"sym": ev, "h": t, "y": y, "c": c})
        tp = t - WEEK if (t - WEEK) // DAY not in busy else t - 2 * WEEK
        if tp >= a:
            yp, _ = _event(px, vol, tp, pl_excl)
            if yp is not None:
                pl_rows.append({"h": tp, "y": yp})
    res = m21iscreen.judge(rows, pl_rows, KEY, {"excluded_coin_events": excl, "placebo_excluded_coin_events": pl_excl,
                                                "calendar_events": len(events)})
    res.update(method=METHOD, rule=RULE)
    if "placebo" in res:
        res["placebo"]["shift_days"] = "-7 (-14 if that day had a calendar event)"
    return res


def run(cache=None):
    """Point 7: one screening from the cache only (never a request)."""
    if cache:
        data.CACHE = cache
    reader = hypogen.Reader(hypogen.SCREEN)                   # 1 h quote volume for 21i's cost; get=None
    px, files = {}, []
    for sym in SYMS:
        px[sym], f = bars(sym)
        files += f
    vol = {s: {t: v[1] for t, v in reader.series(s, "klines", reader.a, reader.b - 1).items()} for s in SYMS}
    events, busy = m21jscreen.calendar(reader.a, reader.b)
    res = screen(px, vol, events, busy, reader.a, reader.b)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except OSError:
        commit = None
    missing = [os.path.basename(path(s, y, m)) for s in SYMS for y, m in MONTHS if not os.path.exists(path(s, y, m))]
    return {"rule": RULE, "method": METHOD, "code_commit": commit, "files": files, "missing_files": missing,
            "files_sha256": hashlib.sha256(json.dumps(files).encode()).hexdigest(), "result": res}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("fetch", "run"))
    ap.add_argument("--out", help="run: write <out>.json")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        try:
            print(json.dumps(fetch(), indent=1))
        except Refused as e:
            print(f"refused: {e}")
            return 2
        return 0
    rep = run()
    text = json.dumps(rep, indent=1, sort_keys=True, default=str)
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
