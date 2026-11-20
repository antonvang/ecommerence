"""Forward paper view: the locked strategies replayed from the development start to now.

    python3 -m jupiter_bot.research.forward --journal J [--plan-lock L] [--out DIR]

Runs only when the plan is locked and the code matches the lock (replay's
`forward` label enforces both). For every locked grid entry it writes
`research/forward/<strategy>-<grid_index>.json` (replaced each run; this is a
view, not an evaluation record) with the replay result at the plan's primary
setting (120 s delay, 25 bps extra cost), no controls, plus the position the
strategy wants right now. Nothing here can place an order.

P2_PLAN.md section 6: watching this is allowed; changing rules, parameters or
code after the holdout starts voids the holdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from ..core import Rejected
from ..marketdata.journal import Journal
from ..marketdata.snapshot import build_snapshot
from . import replay
from .strategies import STRATEGIES

DATA = Path.home() / ".local" / "share" / "jupiter-bot"
PRIMARY_DELAY, PRIMARY_COST = 120, 25
SETTLE = 120.0          # end the replay a little before now so the last quotes have landed


def _now_target(journal_path, fn, bars, params, now):
    journal = Journal(journal_path, readonly=True)
    try:
        return fn(build_snapshot(journal, now, bars=bars(params)), dict(params))
    except Rejected as exc:
        return "WAIT (%s)" % exc
    finally:
        journal.close()


def run(journal_path, plan_lock=replay.DEFAULT_PLAN_LOCK, out=DATA / "research" / "forward", clock=time.time):
    lock, _ = replay.read_lock(plan_lock)
    if lock is None:
        raise Rejected("No plan lock; the forward view starts only after the plan is locked")
    start = lock["windows"]["development"][0]
    now = clock()
    end = float(int((now - SETTLE) // 60) * 60)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (fn, bars, grid) in sorted(STRATEGIES.items()):
        for index, params in enumerate(grid):
            target = out / ("%s-%d.json" % (name, index))
            with tempfile.TemporaryDirectory(dir=out) as scratch:
                try:
                    if end <= start:
                        raise Rejected("The development window has not started yet")
                    record = replay.run(journal_path, name, fn, params, start, end, PRIMARY_DELAY, PRIMARY_COST,
                                        "forward", bars=bars(params), out_dir=scratch, plan_lock=plan_lock,
                                        controls=0, clock=lambda: now)
                except Rejected as exc:
                    record = dict(status="REJECTED", error=str(exc), strategy=name, params=params,
                                  label="forward", period=dict(start=start, end=end))
            record.pop("path", None)
            record.update(grid_index=index, updated_at=now,
                          now_target=_now_target(journal_path, fn, bars, params, now))
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(record), encoding="utf-8")
            os.replace(tmp, target)
            written.append(dict(file=str(target), status=record["status"], now_target=record["now_target"]))
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m jupiter_bot.research.forward")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--plan-lock", default=str(replay.DEFAULT_PLAN_LOCK))
    parser.add_argument("--out", default=str(DATA / "research" / "forward"))
    args = parser.parse_args(argv)
    try:
        for row in run(Path(args.journal), Path(args.plan_lock), Path(args.out)):
            print(json.dumps(row))        # status and target only; returns stay in the files
    except Rejected as exc:
        print("SKIP: %s" % exc)            # not an error: the plan is simply not locked yet
    return 0


if __name__ == "__main__":
    sys.exit(main())
