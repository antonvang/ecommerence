"""Go-live gates, the arm file, and the effective mode.

Mode rules (evaluated fresh every time, never cached):
  DISARMED  no mandate, invalid/expired mandate, no arm file, or the arm file
            belongs to another mandate version (any edit of mandate.json).
  DRY_RUN   arm file with mode DRY_RUN for this exact mandate; mandate_valid
            and private_rpc OK. Never signs.
  LIVE      arm file with mode LIVE for this exact mandate, and every gate is OK
            or was overridden at arm time (only overridable gates).
"""
from __future__ import annotations

import os
import time
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core import canonical, strict_json
from ..research import lock as plan_lock
from . import config
from . import mandate as mandate_mod

GATES = ("p2_holdout_pass", "mandate_valid", "private_rpc", "dry_run_ok", "review_done")
OVERRIDABLE = ("p2_holdout_pass", "dry_run_ok", "review_done")
NEVER_OVERRIDE = ("mandate_valid", "private_rpc")
ARM_KEYS = ("mode", "mandate_sha256", "wallet_pubkey", "armed_at", "overrides")
REVIEW_LINE = "Verdict: APPROVED"


def load_verdicts(directory):
    """All parseable verdict files (research.verdict output). Unreadable files are skipped."""
    directory = Path(directory)
    found = []
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.json")):
        try:
            record = strict_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(record, dict):
            found.append(dict(record, _file=path.name))
    return found


def gate_p2(paths, mandate, verdict_loader=load_verdicts, lock_loader=None, verify=None):
    lock_loader = lock_loader or (lambda: plan_lock.load(paths.plan_lock.parent))
    verify = verify or (lambda record: plan_lock.verify(record, paths.repo))
    try:
        record = lock_loader()
    except (OSError, ValueError) as exc:
        return False, "plan lock unreadable: %s" % type(exc).__name__
    if record is None:
        return False, "P2 plan is not locked"
    try:
        problems = verify(record)
    except (OSError, KeyError) as exc:
        return False, "plan lock cannot be verified: %s" % type(exc).__name__
    if problems:
        return False, "plan lock broken: %s" % "; ".join(problems)
    if mandate is None:
        return False, "no valid mandate to match a verdict against"
    for verdict in verdict_loader(paths.verdicts):
        if (verdict.get("label") == "holdout" and verdict.get("verdict") == "PASS"
                and verdict.get("plan_sha256") == record.get("plan_sha256")
                and verdict.get("strategy") == mandate.strategy and verdict.get("params") == mandate.params):
            return True, "holdout PASS for %s %s (%s)" % (mandate.strategy, mandate.params_json, verdict["_file"]
                                                          if "_file" in verdict else "verdict")
    return False, "no holdout PASS verdict for %s %s under the current plan lock" % (
        mandate.strategy, mandate.params_json)


def gate_review(paths):
    try:
        text = Path(paths.review).read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, "no %s" % Path(paths.review).name
    except (OSError, UnicodeDecodeError) as exc:
        return False, "review unreadable: %s" % type(exc).__name__
    if any(line.strip() == REVIEW_LINE for line in text.splitlines()):
        return True, "%s says %s" % (Path(paths.review).name, REVIEW_LINE)
    return False, "%s has no line '%s'" % (Path(paths.review).name, REVIEW_LINE)


# arm file ---------------------------------------------------------------------------

def read_arm(path):
    """(record | None, problem | None)."""
    path = Path(path)
    try:
        raw = path.read_bytes()[:16384]
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, "arm file unreadable: %s" % type(exc).__name__
    try:
        record = strict_json(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "arm file is not valid JSON"
    if not isinstance(record, dict) or set(record) != set(ARM_KEYS):
        return None, "arm file has the wrong keys"
    if record["mode"] not in ("LIVE", "DRY_RUN") or not isinstance(record["overrides"], list) \
            or any(g not in OVERRIDABLE for g in record["overrides"]):
        return None, "arm file is malformed"
    return record, None


def write_arm(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".armed-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(canonical(record))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def remove_arm(path):
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False


# evaluation ------------------------------------------------------------------------

@dataclass
class State:
    mandate: object
    mandate_error: object
    mandate_problems: list
    mandate_sha: object
    arm: object
    arm_problem: object
    gates: list = field(default_factory=list)
    mode: str = "DISARMED"
    reason: str = ""

    def gate(self, name):
        return next(g for g in self.gates if g["name"] == name)


def evaluate(paths, now, ledger=None, verdict_loader=load_verdicts, lock_loader=None, lock_verify=None,
             uid=None):
    """Compute mandate validity, gates and effective mode. Reads files only; no network."""
    mandate, error = mandate_mod.load(paths.mandate)
    _, sha = mandate_mod.read(paths.mandate) if paths.mandate.exists() else (None, None)
    problems = mandate_mod.problems(mandate, now, paths.repo, uid) if mandate else []
    arm, arm_problem = read_arm(paths.arm)
    state = State(mandate, error, problems, sha, arm, arm_problem)

    valid = mandate is not None and not problems
    if mandate is None:
        detail = error or "no mandate at %s" % paths.mandate
    else:
        detail = "; ".join(problems) if problems else "valid until %s" % _iso(mandate.expires_at)
    ok_p2, detail_p2 = gate_p2(paths, mandate if valid else None, verdict_loader, lock_loader, lock_verify)
    if mandate is None:
        rpc_ok, rpc_detail = False, "no mandate"
    elif mandate_mod.is_public_rpc(mandate.rpc_host):
        rpc_ok, rpc_detail = False, "%s is a public solana.com endpoint" % mandate.rpc_host
    else:
        rpc_ok, rpc_detail = True, "rpc host %s" % mandate.rpc_host
    dry = ledger.dry_runs_ok(sha) if (ledger is not None and sha) else 0
    ok_review, detail_review = gate_review(paths)
    raw = [("p2_holdout_pass", ok_p2, detail_p2), ("mandate_valid", valid, detail),
           ("private_rpc", rpc_ok, rpc_detail),
           ("dry_run_ok", dry >= config.DRY_RUNS_REQUIRED,
            "%d of %d successful DRY_RUN cycles with this mandate" % (dry, config.DRY_RUNS_REQUIRED)),
           ("review_done", ok_review, detail_review)]
    arm_matches = arm is not None and sha is not None and arm["mandate_sha256"] == sha \
        and mandate is not None and arm["wallet_pubkey"] == mandate.wallet_pubkey
    overrides = set(arm["overrides"]) if arm_matches and arm["mode"] == "LIVE" else set()
    for name, ok, text in raw:
        if not ok and name in overrides:
            text = "OVERRIDDEN by operator at arm time (%s): %s" % (_iso(arm["armed_at"]), text)
        state.gates.append({"name": name, "ok": bool(ok), "detail": text})

    if not valid:
        state.mode, state.reason = "DISARMED", "mandate not valid"
    elif arm is None:
        state.mode, state.reason = "DISARMED", arm_problem or "not armed"
    elif not arm_matches:
        state.mode, state.reason = "DISARMED", "arm file belongs to another mandate version; re-arm"
    elif not rpc_ok:
        state.mode, state.reason = "DISARMED", "public RPC"
    elif arm["mode"] == "DRY_RUN":
        state.mode, state.reason = "DRY_RUN", "armed for dry runs only"
    else:
        failing = [g["name"] for g in state.gates if not g["ok"] and g["name"] not in overrides]
        if failing:
            state.mode, state.reason = "DISARMED", "gates failing: %s" % ", ".join(failing)
        else:
            state.mode, state.reason = "LIVE", "armed" + (" with overrides: %s" % ", ".join(sorted(overrides))
                                                         if overrides else "")
    return state


def _iso(at):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(at)))
    except (TypeError, ValueError, OverflowError):
        return "?"
