"""Operational gates. S7 (scheduled automation) may only be activated after stages 1-6 have run cleanly for at least
seven days (ENGINE_PROPOSAL.md §10). The gate is computed from the append-only event log, so it cannot be satisfied by
editing a setting.

Clean operation means, inside the window that ends now:
- hourly `system.alive` records from the supervisor covering >= 7 days, with no gap longer than 2 hours;
- no FAIL_CLOSED, no `worker.failed`, no failed startup and no `system.disk_low` event since the window began.
"""
from __future__ import annotations

import time

S7_DAYS = 7
MAX_GAP_S = 2 * 3600


def s7_gate(db, now=None, days=S7_DAYS):
    now = now or time.time()
    bad = db.q("SELECT ts, kind FROM events WHERE kind IN ('worker.failed','system.disk_low') OR "
               "(kind='system.startup' AND payload LIKE '%\"ok\":false%') ORDER BY ts")
    fc = db.q("SELECT ts FROM risk_events WHERE action='FAIL_CLOSED' ORDER BY ts")
    last_bad = max([r["ts"] for r in bad] + [r["ts"] for r in fc] + [0])
    alive = [r["ts"] for r in db.q("SELECT ts FROM events WHERE kind='system.alive' AND ts>? ORDER BY ts", last_bad)]
    # longest run of alive records ending at the latest one, with no gap > MAX_GAP_S, and the latest one recent
    run_start = None
    for i, t in enumerate(alive):
        if i == 0 or t - alive[i - 1] > MAX_GAP_S:
            run_start = t
    recent = bool(alive) and now - alive[-1] <= MAX_GAP_S
    covered = (alive[-1] - run_start) if (alive and recent) else 0.0
    need = days * 86400
    return {"gate": "S7", "open": covered >= need, "covered_s": covered, "required_s": need,
            "remaining_s": max(0.0, need - covered), "alive_records": len(alive), "last_alive_ts": alive[-1] if alive else None,
            "last_incident_ts": last_bad or None,
            "reason": ("clean for the required period" if covered >= need else
                       "no supervised operation recorded yet" if not alive else
                       "supervisor not currently running (last alive record too old)" if not recent else
                       f"clean operation so far: {covered / 86400:.2f} of {days} days")}
