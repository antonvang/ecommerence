"""P2_PLAN.md section 8 as code: turn evaluation files into a verdict, once.

    python3 -m jupiter_bot.research.verdict --batch BATCH_ID [--evaluations DIR] [--out DIR]

A batch is one replay CLI invocation (all files share `batch.id`); each grid
entry (`grid_index`) gets its own verdict. Evaluation files are never edited;
each verdict is a new write-once file in `research/verdicts/`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

DATA = Path.home() / ".local" / "share" / "jupiter-bot" / "research"
PRIMARY = (120, 25)
ROBUST = ((300, 25), (120, 50))
MIN_COVERAGE = Decimal("95")
DEV_MAX_SHARE = Decimal("0.0125")        # 5 % / 4 trials (Bonferroni)
HOLDOUT_MAX_SHARE = Decimal("0.05")
DEV_MIN_ROUND_TRIPS, HOLDOUT_MIN_ROUND_TRIPS = 10, 5
MAX_MISSING_QUOTE_PCT = Decimal("5")


def D(value):
    return Decimal(str(value))


def _cells(records):
    return {(int(r["delay_s"]), int(r["extra_cost_bps"])): r for r in records}


def _data_problems(record):
    if record is None:
        return ["primary cell (120 s, 25 bps) is missing"]
    if record.get("status") != "OK":
        return ["primary cell was REJECTED: %s" % record.get("error")]
    m = record["metrics"]
    return ["%s %s %% < 95 %%" % (key, m[key]) for key in
            ("candle_coverage_pct", "quote_coverage_buy_pct", "quote_coverage_sell_pct")
            if D(m[key]) < MIN_COVERAGE]


def development(records):
    """(verdict, checks) for one grid entry's cells on the development period."""
    cells = _cells(records)
    primary = cells.get(PRIMARY)
    problems = _data_problems(primary)
    if problems:
        return "INCONCLUSIVE_DATA", problems
    m, c = primary["metrics"], primary["controls"]
    checks = [
        ("return after costs > 0 (120 s, 25 bps)", D(m["return_pct"]) > 0, m["return_pct"]),
        ("random entries beating it <= 1.25 %", D(c["random_entries"]["share_beating_strategy"]) <= DEV_MAX_SHARE,
         c["random_entries"]["share_beating_strategy"]),
        ("shuffled signals beating it <= 1.25 %", D(c["shuffled_signals"]["share_beating_strategy"]) <= DEV_MAX_SHARE,
         c["shuffled_signals"]["share_beating_strategy"]),
    ]
    for key in ROBUST:
        cell = cells.get(key)
        usable = cell is not None and cell.get("status") == "OK"
        value = cell["metrics"]["return_pct"] if usable else "missing/rejected"
        checks.append(("return > 0 at %d s, %d bps" % key, usable and D(value) > 0, value))
    checks.append(("MISSING_QUOTE <= 5 %", D(m["missing_quote_pct"]) <= MAX_MISSING_QUOTE_PCT, m["missing_quote_pct"]))
    rows = [dict(check=name, ok=bool(ok), value=value) for name, ok, value in checks]
    if m["round_trips"] < DEV_MIN_ROUND_TRIPS:
        rows.append(dict(check="at least 10 round trips", ok=False, value=m["round_trips"]))
        return "INCONCLUSIVE", rows
    rows.append(dict(check="at least 10 round trips", ok=True, value=m["round_trips"]))
    return ("PASS_DEV" if all(r["ok"] for r in rows) else "FAIL"), rows


def holdout(records):
    cells = _cells(records)
    primary = cells.get(PRIMARY)
    problems = _data_problems(primary)
    if problems:
        return "INCONCLUSIVE_DATA", problems
    m, c = primary["metrics"], primary["controls"]
    rows = [dict(check="return after costs > 0 (120 s, 25 bps)", ok=D(m["return_pct"]) > 0, value=m["return_pct"]),
            dict(check="random entries beating it <= 5 %",
                 ok=D(c["random_entries"]["share_beating_strategy"]) <= HOLDOUT_MAX_SHARE,
                 value=c["random_entries"]["share_beating_strategy"])]
    if m["round_trips"] < HOLDOUT_MIN_ROUND_TRIPS:
        rows.append(dict(check="at least 5 round trips", ok=False, value=m["round_trips"]))
        return "INCONCLUSIVE", rows
    rows.append(dict(check="at least 5 round trips", ok=True, value=m["round_trips"]))
    return ("PASS" if all(r["ok"] for r in rows) else "FAIL"), rows


def select(dev_results):
    """The one configuration that goes to the holdout: lowest random share, then fewest trades."""
    passed = [r for r in dev_results if r["verdict"] == "PASS_DEV"]
    if not passed:
        return None

    def key(r):
        share = next(row["value"] for row in r["checks"] if row["check"].startswith("random entries"))
        return D(share), r["trades"]
    return min(passed, key=key)


def load_batch(evaluations, batch_id):
    groups = {}
    for path in sorted(Path(evaluations).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("batch") or {}).get("id") == batch_id:
            groups.setdefault(record.get("grid_index", 0), []).append(record)
    return groups


def judge_batch(evaluations, batch_id, out, now=None):
    now = time.time() if now is None else now
    groups = load_batch(evaluations, batch_id)
    if not groups:
        raise ValueError("no evaluation files with batch.id %s in %s" % (batch_id, evaluations))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for index, records in sorted(groups.items()):
        labels = {r["label"] for r in records}
        if len(labels) != 1:
            raise ValueError("mixed labels in one grid entry: %s" % sorted(labels))
        label = labels.pop()
        verdict, checks = (holdout if label == "holdout" else development)(records)
        primary = _cells(records).get(PRIMARY)
        result = dict(label=label, verdict=verdict, strategy=records[0]["strategy"], params=records[0]["params"],
                      plan_sha256=records[0]["plan_sha256"], batch_id=batch_id, grid_index=index,
                      evaluation_run_ids=sorted(r["run_id"] for r in records), created_at=now, checks=checks,
                      trades=primary["metrics"]["trades"] if primary and primary.get("metrics") else None)
        target = out / ("%s-%s-%d.json" % (label, batch_id, index))
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)   # never replaced
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
        results.append(dict(result, path=str(target)))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m jupiter_bot.research.verdict")
    parser.add_argument("--batch", help="judge one replay batch")
    parser.add_argument("--select", action="store_true",
                        help="pick the holdout candidate from all development verdicts in --out")
    parser.add_argument("--evaluations", default=str(DATA / "evaluations"))
    parser.add_argument("--out", default=str(DATA / "verdicts"))
    args = parser.parse_args(argv)
    if args.select:
        dev = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(args.out).glob("development-*.json"))]
        chosen = select(dev)
        print(json.dumps({"selected_for_holdout": chosen and {"strategy": chosen["strategy"],
                                                              "params": chosen["params"]},
                          "development_verdicts": len(dev)}))
        return 0
    if not args.batch:
        parser.error("--batch or --select is required")
    try:
        results = judge_batch(args.evaluations, args.batch, args.out)
    except (ValueError, OSError) as exc:
        print("STOP: %s" % exc, file=sys.stderr)
        return 1
    for result in results:
        print(json.dumps({k: result[k] for k in ("label", "strategy", "params", "verdict", "path")}))
    chosen = select([r for r in results if r["label"] == "development"])
    if chosen:
        print(json.dumps({"selected_for_holdout": {"strategy": chosen["strategy"], "params": chosen["params"]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
