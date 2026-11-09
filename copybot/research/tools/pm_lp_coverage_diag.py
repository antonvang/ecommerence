"""Director order 72 P1: diagnostic pm_lp coverage against the whole observation window.

This is NOT gate D1. research/pm_lp.py coverage() stays the locked evaluator and is not imported or changed here. The
difference: a day with no panel, or a short panel, still counts in full in the denominator here.

Read-only. Counts only: no market id, price, reward or result is read into the report. Stdlib only, no network.
"""
import argparse
import calendar
import os
import sqlite3
import time

DAY = 86400
MINUTES = 1440


def utc_day(text):
    return calendar.timegm(time.strptime(text, "%Y-%m-%d")) // DAY


def day_text(day):
    return time.strftime("%Y-%m-%d", time.gmtime(day * DAY))


def load(db, window):
    """{day: {"panel": n, "snaps": q}}, {day: {"polls": n, "failed": m}} for the window (same UTC day rule as D1)."""
    first, last = window
    days = {d: {"panel": 0, "snaps": 0} for d in range(first, last + 1)}
    for d, n in db.execute("SELECT day, COUNT(*) FROM panel WHERE day BETWEEN ? AND ? GROUP BY day", window):
        days[d]["panel"] = n
    for d, n in db.execute("SELECT p.day, COUNT(*) FROM snaps s JOIN panel p ON p.cid=s.cid AND p.day=s.t/86400 "
                           "WHERE p.day BETWEEN ? AND ? GROUP BY p.day", window):
        days[d]["snaps"] = n
    polls = {}
    for d, n, m in db.execute("SELECT t/86400, COUNT(*), COALESCE(SUM(1-ok),0) FROM polls WHERE kind='trades' AND "
                              "t>=? AND t<? GROUP BY t/86400", (first * DAY, (last + 1) * DAY)):
        polls[d] = {"polls": n, "failed": m}
    return days, polls


def minutes_seen(db, window):
    first, last = window
    return [r[0] for r in db.execute("SELECT DISTINCT t/60 FROM snaps WHERE t>=? AND t<? ORDER BY 1",
                                     (first * DAY, (last + 1) * DAY))]


def gaps(minutes, start_min, end_min, min_gap=5):
    """Holes of at least min_gap minutes in [start_min, end_min), including at the two edges: [(from, to_excl)]."""
    out, prev = [], start_min - 1
    for m in sorted(x for x in set(minutes) if start_min <= x < end_min):
        if m - prev - 1 >= min_gap:
            out.append((prev + 1, m))
        prev = m
    if end_min - prev - 1 >= min_gap:
        out.append((prev + 1, end_min))
    return out


def diagnose(days, window, panel_size, as_of, polls=None):
    """Every day of the window counts panel_size * 1440. A running day counts only its elapsed part so far."""
    first, last = window
    polls = polls or {}
    full = panel_size * MINUTES
    rows, seen, elapsed_expected = [], 0, 0.0
    for d in range(first, last + 1):
        x = days.get(d, {"panel": 0, "snaps": 0})
        done = min(1.0, max(0.0, (as_of - d * DAY) / DAY))
        obs = min(x["snaps"], full)
        status = ("FUTURE" if done == 0 else "NO_PANEL" if x["panel"] == 0 else
                  "SHORT_PANEL" if x["panel"] < panel_size else "NO_DATA" if obs == 0 else "OBSERVED")
        rows.append({"day": d, "status": status, "panel": x["panel"], "snaps": x["snaps"], "elapsed": done,
                     "coverage": obs / (full * done) if done else None})
        seen += obs
        elapsed_expected += full * done
    total = full * (last - first + 1)
    remaining = total - elapsed_expected
    panel_rows = sum(days.get(d, {"panel": 0})["panel"] for d in range(first, last + 1))
    snaps_in_panel = sum(days.get(d, {"snaps": 0})["snaps"] for d in range(first, last + 1))
    n_polls = sum(v["polls"] for v in polls.values())
    failed = sum(v["failed"] for v in polls.values())
    rate_full = max((v["polls"] for v in polls.values()), default=0)
    left_days = remaining / full if full else 0.0
    return {"rows": rows, "window_minutes_expected": total, "observed": seen,
            "coverage_elapsed": seen / elapsed_expected if elapsed_expected else None,
            "coverage_whole_window": seen / total if total else None,
            "best_case_whole_window": (seen + remaining) / total if total else None,
            "locked_formula_for_comparison": snaps_in_panel / (panel_rows * MINUTES) if panel_rows else None,
            "polls": n_polls, "polls_failed": failed, "poll_fail_rate": failed / n_polls if n_polls else None,
            "poll_fail_rate_best_case": (failed / (n_polls + rate_full * left_days)
                                         if n_polls + rate_full * left_days else None)}


def render(rep, gap_list):
    pct = lambda v: "n/a" if v is None else "%.2f %%" % (100 * v)  # noqa: E731
    out = ["| Dag (UTC) | Status | Panel | Snaps | Forløbet | Dækning |", "|---|---|---|---|---|---|"]
    for r in rep["rows"]:
        out.append("| %s | %s | %d | %d | %.2f | %s |" % (day_text(r["day"]), r["status"], r["panel"], r["snaps"],
                                                         r["elapsed"], pct(r["coverage"])))
    out += ["", "- Dækning af forløbet tid: " + pct(rep["coverage_elapsed"]),
            "- Dækning af hele vinduet indtil nu: " + pct(rep["coverage_whole_window"]),
            "- Bedste tilfælde for hele vinduet: " + pct(rep["best_case_whole_window"]),
            "- Den låste formel, kun til sammenligning: " + pct(rep["locked_formula_for_comparison"]),
            "- Fejlede trade-polls: %d af %d = %s (bedste tilfælde %s)" % (
                rep["polls_failed"], rep["polls"], pct(rep["poll_fail_rate"]), pct(rep["poll_fail_rate_best_case"])),
            "", "Huller på mindst 30 minutter uden nogen snapshot (UTC):", ""]
    for a, b in gap_list:
        out.append("- %s til %s (%d min)" % (time.strftime("%m-%d %H:%M", time.gmtime(a * 60)),
                                             time.strftime("%m-%d %H:%M", time.gmtime(b * 60)), b - a))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--first", default="2026-10-31")
    ap.add_argument("--last", default="2026-11-13")
    ap.add_argument("--panel-size", type=int, default=200)
    args = ap.parse_args()
    now = time.time()
    window = (utc_day(args.first), utc_day(args.last))
    db = sqlite3.connect(f"file:{os.path.abspath(args.db)}?mode=ro", uri=True, timeout=2)
    db.execute("PRAGMA query_only=ON")
    days, polls = load(db, window)
    end = min(int(now) // 60, (window[1] + 1) * MINUTES)
    print(render(diagnose(days, window, args.panel_size, now, polls),
                 gaps(minutes_seen(db, window), window[0] * MINUTES, end, min_gap=30)), end="")


if __name__ == "__main__":
    main()
