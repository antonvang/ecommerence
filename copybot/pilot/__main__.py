"""Amendment 29 CLI (run from copybot/):

  python3 -m pilot run --rounds 32            dry run (default): live public books, simulated fills, nothing sent
  python3 -m pilot run --live --rounds 80     real orders; refused unless every amendment 29 point 9 check holds
  python3 -m pilot report | status
  python3 -m pilot confirm-today | resume     human only, in a terminal (Claude never runs these)
"""
import argparse
import json
import sys
import time

import pilot as P
from pilot import core
from pilot.exchange import DryExchange, LiveExchange


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--rounds", type=int, required=True)
    r.add_argument("--live", action="store_true")
    for name in ("report", "status", "confirm-today", "resume"):
        sub.add_parser(name)
    a = ap.parse_args(argv)
    ledger = core.Ledger()
    if a.cmd == "report":
        print(json.dumps(core.report(ledger), indent=1, ensure_ascii=False))
        return 0
    if a.cmd == "status":
        print(json.dumps({"state": ledger.state(), "dry_evidence": core.dry_evidence(ledger)[1],
                          "live_blockers": core.live_blockers(ledger)}, indent=1, ensure_ascii=False))
        return 0
    if a.cmd == "confirm-today":
        if not core.human_typed(P.CONFIRM_PHRASE):
            print("ikke bekræftet (kræver en interaktiv terminal og den præcise sætning)")
            return 1
        with open(core.confirm_path(ledger), "w", encoding="utf-8") as fh:
            fh.write(f"human {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        ledger.append(kind="confirm", actor="human")
        print("bekræftet for i dag")
        return 0
    if a.cmd == "resume":
        if not core.human_typed(P.RESUME_PHRASE):
            print("ikke genoptaget (kræver en interaktiv terminal og den præcise sætning)")
            return 1
        ledger.set_state(stopped=None)
        ledger.append(kind="resume", actor="human")
        print("genoptaget")
        return 0
    if a.live:
        blockers = core.live_blockers(ledger)
        if blockers:
            print("live afvist:\n- " + "\n- ".join(blockers))
            return 2
        ex = LiveExchange()
    else:
        ex = DryExchange(usdt=P.CAPITAL_USDT)
    try:
        print(core.run(ex, ledger, a.rounds), "runder")
    except core.Stopped as e:
        print(f"STOP: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
