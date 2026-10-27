"""Amendments 29/29a CLI (run from copybot/); research and paper only:

  python3 -m pilot run --rounds 32     simulated rounds against live public books; nothing is ever sent
  python3 -m pilot report | status
  python3 -m pilot resume              human only, in a terminal (Claude never runs it)
"""
import argparse
import json
import sys

import pilot as P
from pilot import core
from pilot.exchange import DryExchange


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run").add_argument("--rounds", type=int, required=True)
    for name in ("report", "status", "resume"):
        sub.add_parser(name)
    a = ap.parse_args(argv)
    ledger = core.Ledger()
    if a.cmd == "report":
        print(json.dumps(core.report(ledger), indent=1, ensure_ascii=False))
        return 0
    if a.cmd == "status":
        print(json.dumps({"state": ledger.state(), "dry_evidence": core.dry_evidence(ledger)[1]}, indent=1,
                         ensure_ascii=False))
        return 0
    if a.cmd == "resume":
        if not core.human_typed(P.RESUME_PHRASE):
            print("ikke genoptaget (kræver en interaktiv terminal og den præcise sætning)")
            return 1
        ledger.set_state(stopped=None)
        ledger.append(kind="resume", actor="human")
        print("genoptaget")
        return 0
    try:
        print(core.run(DryExchange(usdt=P.CAPITAL_USDT), ledger, a.rounds), "runder")
    except core.Stopped as e:
        print(f"STOP: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
