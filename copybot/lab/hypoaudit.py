"""Read-only audit of the hypothesis pipeline (`python3 -m lab hypo-audit`, research/LINUX_DRIFT.md 2026-10-22).

What amendment 17's screening and the locked measurements recorded, summarised so blind spots stay visible: verdicts,
the exclusion causes behind UNTESTABLE, the failed checks behind SCREEN_FAIL (and the placebo checks that failed for
lack of a placebo value), and how the screen passes did on independent data. It changes and decides nothing.
"""
from __future__ import annotations

import collections
import json
import sqlite3

from lab import hypogen

PLACEBO = "placebo"


def _payloads(con, kind):
    for (raw,) in con.execute("SELECT payload FROM events WHERE kind=? ORDER BY id", (kind,)):
        yield json.loads(raw)


def audit(con):
    res = {}
    for p in _payloads(con, hypogen.EV_SCREEN):
        res[p["key"]] = p                                       # the latest result per key counts
    verdicts = collections.Counter(p.get("verdict") for p in res.values())
    causes, types = collections.Counter(), {}
    for k, p in res.items():
        if p.get("verdict") != "UNTESTABLE":
            continue
        for cause, n in (p.get("excluded") or {}).items():
            causes[cause] += n
        t = types.setdefault(k.split("|")[0], {"keys": 0, "events": 0, "max_n": 0})
        t["keys"] += 1
        t["events"] = max(t["events"], p.get("events") or 0)
        t["max_n"] = max(t["max_n"], p.get("n") or 0)
    failed, no_placebo = collections.Counter(), []
    for k, p in sorted(res.items()):
        if p.get("verdict") != "SCREEN_FAIL":
            continue
        for check, ok in (p.get("checks") or {}).items():
            if not ok:
                failed[check] += 1
                if check.startswith(PLACEBO) and (p.get("placebo") or {}).get("p") is None:
                    no_placebo.append({"key": k, "n": p.get("n"), "mean": p.get("mean"), "p": p.get("p")})
    passed = sorted(k for k, p in res.items() if p.get("verdict") == "SCREEN_PASS")
    measured = {}
    for p in _payloads(con, "research.measurement"):
        if p.get("hypothesis") in res:
            measured[p["hypothesis"]] = {"verdict": p.get("verdict"), "reason": p.get("reason")}
    return {"keys": len(res), "verdicts": dict(verdicts), "untestable_causes": dict(causes.most_common()),
            "untestable_types": types, "failed_checks": dict(failed.most_common()), "no_placebo_value": no_placebo,
            "screen_pass": passed, "measured": measured,
            "independent_hits": sum(1 for k in passed if (measured.get(k) or {}).get("verdict") == "PASS"),
            "independent_measured": sum(1 for k in passed if k in measured), "decisional": False}


def main(db_path, out=print):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        a = audit(con)
    finally:
        con.close()
    out(f"{a['keys']} keys screened: " + ", ".join(f"{v} {n}" for v, n in sorted(a["verdicts"].items())))
    out("UNTESTABLE - excluded events by cause (summed over keys):")
    for cause, n in a["untestable_causes"].items():
        out(f"  {n:6d}  {cause}")
    out("UNTESTABLE - by type (keys, events in explore0, largest n with data):")
    for t, v in sorted(a["untestable_types"].items(), key=lambda x: (-x[1]["keys"], x[0])):
        out(f"  {t:18s} {v['keys']:3d} keys  {v['events']:4d} events  n <= {v['max_n']}")
    out("SCREEN_FAIL - failed checks (a key can fail several):")
    for check, n in a["failed_checks"].items():
        out(f"  {n:4d}  {check}")
    out(f"placebo check failed WITHOUT a placebo value (blind spot, see research/studies/AUDIT_HYPOTESER_2026-10-22.md): "
        f"{len(a['no_placebo_value'])}")
    for r in a["no_placebo_value"]:
        out(f"  {r['key']}  n={r['n']}  mean={r['mean']:+.4f}  p={r['p']:.4g}")
    out(f"SCREEN_PASS {len(a['screen_pass'])}; measured on independent data {a['independent_measured']}; "
        f"passed there {a['independent_hits']}")
    for k in a["screen_pass"]:
        m = a["measured"].get(k)
        out(f"  {k}: " + (f"{m['verdict']} ({m['reason']})" if m else "not measured (needs a LÅS-17 lock)"))
    return 0
