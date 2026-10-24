"""Dashboard research pipeline and capacity (research/LINUX_DRIFT.md 2026-10-24 22:28). Read-only: research-memory's
records with their own statuses (never merged), the forward tests' counters, and capacity status per paper ledger.
Nothing is decided, reopened or recomputed here.
"""
from __future__ import annotations

import collections
import time

from lab import capacity, coverage, edgemonitor, memory

STAGES = ("opdaget", "undersøgt", "hypotese", "protokol", "screening", "validering", "papir/skygge", "overvågning")
STAGE_OF = {"screen": "screening", "study": "screening", "measurement": "validering", "catalogue": "validering",
            "family": "validering", "legacy": "validering"}
CAPACITY = "UNTESTABLE_CAPACITY"
CAPACITY_WHY = ("ingen dokumenteret nettofordel at skalere, og bogdata kun ved få størrelser og mønter "
                "(research/drafts/SYSTEMKORT_OG_RISICI_2026-10-24.md punkt 4)")


def view(db, now=None):
    now = now or time.time()
    recs = memory.memory(db.con)
    rows = []
    for r in recs:
        verdict = r.get("state") or r.get("verdict") or "?"
        rows.append({"source": r["source"], "id": r["id"], "stage": STAGE_OF.get(r["source"], "screening"),
                     "status": str(verdict).split(" ")[0].split(":")[0], "verdict": verdict,
                     "n": r.get("n"), "clusters": r.get("clusters"), "mean": r.get("mean"), "p": r.get("p"),
                     "cost_hurdle": r.get("cost_hurdle"), "failed": r.get("failed"), "retest": r.get("retest"),
                     "reason": r.get("reason")})
    by_status = collections.Counter(x["status"] for x in rows)
    forward = coverage.forward(db, now)
    paper = [r["exp_id"] for r in db.q("SELECT DISTINCT exp_id FROM sim_fills ORDER BY exp_id")]
    stage_counts = collections.Counter(x["stage"] for x in rows)
    stage_counts["papir/skygge"] = len(paper)
    stage_counts["overvågning"] = sum(1 for f in forward if (f.get("collected") or 0) > 0)
    return {"stages": [{"stage": s, "n": stage_counts.get(s, 0)} for s in STAGES],
            "by_status": dict(sorted(by_status.items())), "records": rows, "forward": forward,
            "capacity": [{"ledger": led, "status": CAPACITY, "why": CAPACITY_WHY} for led in paper],
            "capacity_curve": capacity.latest(db), "edge_monitor": edgemonitor.view(db, now),
            "notes": ["statusser fra research-memory, aldrig slået sammen; intet genåbnes herfra",
                      "trinene 'opdaget', 'undersøgt', 'hypotese' og 'protokol' tælles ikke automatisk endnu: de står "
                      "i scannerens poster og i protokollen"],
            "now": now}
