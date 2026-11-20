"""python3 -m jupiter_bot.execution {status [--json] | check-mandate | dry-run-once | run-once |
                                    arm [--dry-run] [--override GATE]... | disarm | resolve |
                                    force-expire ORDER_ID | code-hash}

Global options (before the command): --mandate PATH --data-dir DIR --journal PATH
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from ..core import Rejected
from . import config, gates
from . import mandate as mandate_mod
from .engine import Engine, arm, disarm, force_expire, wallet_locks
from .ledger import Ledger


def _paths(args):
    return config.Paths.defaults(mandate=args.mandate, data_dir=args.data_dir, journal=args.journal)


def _print_status(status, state):
    print("Mode: %s%s" % (status["mode"], "  (%s)" % state.reason if state.reason else ""))
    mandate = status["mandate"]
    if mandate:
        print("Mandate: wallet %s, max trade %s USDC, max position %s USDC, daily loss %s USDC"
              % (mandate["wallet_pubkey"], mandate["max_trade_usdc"], mandate["max_position_usdc"],
                 mandate["daily_loss_limit_usdc"]))
    elif state.mandate_error:
        print("Mandate: INVALID: %s" % state.mandate_error)
    else:
        print("Mandate: none")
    for gate in status["gates"]:
        print("  %-16s %s  %s" % (gate["name"], "OK  " if gate["ok"] else "FAIL", gate["detail"]))
    o = status["orders"]
    print("Orders: %d total, %d pending, %d unknown, %d confirmed, %d failed/expired"
          % (o["total"], o["pending"], o["unknown"], o["confirmed"], o["failed"]))
    print("Realised P&L today (UTC): %.6f USDC" % status["today_realized_pnl_usdc"])


def main(argv=None, engine_factory=Engine, ask=input, interactive=None):
    parser = argparse.ArgumentParser(prog="python3 -m jupiter_bot.execution")
    parser.add_argument("--mandate")
    parser.add_argument("--data-dir")
    parser.add_argument("--journal")
    sub = parser.add_subparsers(dest="command", required=True)
    status_p = sub.add_parser("status")
    status_p.add_argument("--json", action="store_true")
    sub.add_parser("check-mandate")
    sub.add_parser("dry-run-once")
    sub.add_parser("run-once")
    sub.add_parser("resolve")
    arm_p = sub.add_parser("arm")
    arm_p.add_argument("--dry-run", action="store_true", help="arm for DRY_RUN cycles only (never signs)")
    arm_p.add_argument("--override", action="append", default=[], metavar="GATE",
                       help="override a failing gate (%s)" % ", ".join(gates.OVERRIDABLE))
    sub.add_parser("disarm")
    expire_p = sub.add_parser("force-expire", help="operator: mark one UNKNOWN order EXPIRED after checking by hand")
    expire_p.add_argument("order_id")
    sub.add_parser("code-hash", help="print the Execution-SHA256 a reviewer must put in P3_REVIEW.md")
    args = parser.parse_args(argv)
    paths = _paths(args)
    now = time.time()
    try:
        if args.command == "status":
            engine = engine_factory(paths)
            status, state = engine.status()
            if args.json:
                print(json.dumps(status, sort_keys=True, allow_nan=False))
            else:
                _print_status(status, state)
            return 0
        if args.command == "code-hash":
            print("Execution-SHA256: %s" % gates.execution_code_sha256(paths.repo))
            return 0
        if args.command == "check-mandate":
            mandate, error = mandate_mod.load(paths.mandate)
            if mandate is None:
                print("INVALID: %s" % (error or "no mandate at %s" % paths.mandate))
                return 1
            problems = mandate_mod.problems(mandate, now, paths.repo)
            if mandate_mod.is_public_rpc(mandate.rpc_host):
                problems.append("rpc_url is a public solana.com endpoint (private_rpc gate fails)")
            print(json.dumps(dict(mandate.public(), strategy=mandate.strategy, params=mandate.params,
                                  max_slippage_bps=mandate.max_slippage_bps, rpc_host=mandate.rpc_host,
                                  sha256=mandate.sha256), indent=2, sort_keys=True))
            for problem in problems:
                print("PROBLEM: %s" % problem)
            print("OK" if not problems else "NOT USABLE")
            return 0 if not problems else 1
        if args.command == "disarm":
            ledger = None
            try:
                ledger = Ledger(paths.ledger) if paths.ledger.exists() else None
            except Exception:
                ledger = None
            try:
                removed = disarm(paths, now, ledger)
            finally:
                if ledger is not None:
                    ledger.close()
            print("DISARMED" + ("" if removed else " (no arm file was present)"))
            return 0
        if args.command == "arm":
            interactive = sys.stdin.isatty() if interactive is None else interactive
            with wallet_locks(paths):
                ledger = Ledger(paths.ledger)
                try:
                    record = arm(paths, "DRY_RUN" if args.dry_run else "LIVE", args.override, ask,
                                 interactive, now, ledger)
                finally:
                    ledger.close()
            print("ARMED %s%s" % (record["mode"], " with overrides %s" % record["overrides"]
                                  if record["overrides"] else ""))
            print("Kill switch: python3 -m jupiter_bot.execution disarm")
            return 0
        engine = engine_factory(paths)
        try:
            if args.command == "resolve":
                with wallet_locks(paths):
                    result = engine.resolve()
            elif args.command == "force-expire":
                interactive = sys.stdin.isatty() if interactive is None else interactive
                with wallet_locks(paths):
                    result = force_expire(engine, args.order_id, ask, interactive)
            elif args.command == "dry-run-once":
                result = engine.dry_run_once()
            else:
                result = engine.run_once()
        finally:
            engine.close()
        print(json.dumps(result, sort_keys=True, default=str, indent=2))
        return 0
    except Rejected as exc:
        print("STOP: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("STOP: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
