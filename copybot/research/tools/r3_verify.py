"""Amendment 24a point 4: check R3's 44 cached minute files before the one screening, read-only and without a request.

Per file: present (or recorded `absent` after a 404); the sha256 on disk equals the last `fetched` sha256 in
fetch_log.jsonl; the zip passes its CRC check; every minute bar's open time lies in the file's own month (and so in
explore0 2020-03..2021-12); rows, first and last bar, and minutes missing against a full month. Exit 0 only if every
file passes. No comparison with Binance's .CHECKSUM files (they would be other requests; amendment 24a point 4).

  python3 research/tools/r3_verify.py [--cache data/lab/market] [--out PATH.json]
"""
import argparse
import calendar
import csv
import hashlib
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lab import r3  # noqa: E402
from lab.engine import data  # noqa: E402


def _logged():
    """{file: (status, sha256)} from the last fetch_log entry that names the file (refused entries name none)."""
    out = {}
    if not os.path.exists(r3.log_path()):
        return out
    with open(r3.log_path(), encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            for name, v in (e.get("files") or {}).items():
                if v.get("status") == "present" and name in out:
                    continue                                  # a later run saw it cached; keep the fetch record
                out[name] = (v.get("status"), v.get("sha256"))
    return out


def check_file(sym, y, m, logged):
    name = os.path.basename(r3.path(sym, y, m))
    p = r3.path(sym, y, m)
    status, logged_sha = logged.get(name, (None, None))
    row = {"file": name, "logged": status}
    if not os.path.exists(p):
        row["ok"] = status == "absent"
        row["why"] = "recorded absent (404)" if row["ok"] else "missing and not recorded absent"
        return row
    with open(p, "rb") as f:
        blob = f.read()
    row["sha256"] = hashlib.sha256(blob).hexdigest()
    row["sha256_matches_log"] = row["sha256"] == logged_sha
    a = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())
    b = a + calendar.monthrange(y, m)[1] * 86400
    times, outside = [], 0
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            row["crc_ok"] = z.testzip() is None
            for n in z.namelist():
                for rec in csv.reader(io.TextIOWrapper(z.open(n), encoding="utf-8")):
                    if not rec or not rec[0].strip().isdigit():
                        continue
                    t = int(rec[0]) // 1000
                    times.append(t)
                    outside += not a <= t < b
    except zipfile.BadZipFile as e:
        row.update(crc_ok=False, why=f"bad zip: {e}")
        row["ok"] = False
        return row
    row.update(rows=len(times), outside_month=outside, missing_minutes=(b - a) // 60 - len(set(times)),
               first=min(times) if times else None, last=max(times) if times else None)
    row["ok"] = bool(row["sha256_matches_log"] and row["crc_ok"] and times and outside == 0)
    if not row["ok"]:
        row["why"] = ", ".join(w for w, bad in (("sha256 differs from the log", not row["sha256_matches_log"]),
                                                ("CRC", not row["crc_ok"]), ("no bars", not times),
                                                ("bars outside the month", outside)) if bad)
    return row


def verify(cache=None):
    if cache:
        data.CACHE = cache
    logged = _logged()
    rows = [check_file(s, y, m, logged) for s in r3.SYMS for y, m in r3.MONTHS]
    return {"rule": "research/PROTOCOL_V3.md amendment 24a point 4", "expected": len(rows),
            "present": sum(1 for r in rows if "sha256" in r), "absent": sum(1 for r in rows if r["logged"] == "absent"
                                                                             and "sha256" not in r),
            "ok": all(r["ok"] for r in rows), "files": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    res = verify(a.cache)
    text = json.dumps(res, indent=1, sort_keys=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    bad = [r for r in res["files"] if not r["ok"]]
    print(json.dumps({k: res[k] for k in ("expected", "present", "absent", "ok")}), *[f"{r['file']}: {r.get('why')}"
                                                                                     for r in bad], sep="\n")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
