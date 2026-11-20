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

import ast
import hashlib
import os
import re
import time
from decimal import Decimal
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core import Rejected, canonical, strict_json
from ..research import lock as plan_lock
from . import config
from . import mandate as mandate_mod

GATES = ("p2_holdout_pass", "mandate_valid", "private_rpc", "dry_run_ok", "review_done")
OVERRIDABLE = ("p2_holdout_pass", "dry_run_ok", "review_done")
NEVER_OVERRIDE = ("mandate_valid", "private_rpc")
ARM_KEYS = ("mode", "mandate_sha256", "wallet_pubkey", "armed_at", "overrides")
REVIEW_LINE = "Verdict: APPROVED"
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


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
    except Exception as exc:          # a malformed lock must never crash status (F17)
        return False, "plan lock unreadable: %s" % type(exc).__name__
    if record is None:
        return False, "P2 plan is not locked"
    if not isinstance(record, dict):
        return False, "plan lock is malformed"
    try:
        problems = verify(record)
    except Exception as exc:
        return False, "plan lock cannot be verified: %s" % type(exc).__name__
    if problems:
        return False, "plan lock broken: %s" % "; ".join(problems)
    if mandate is None:
        return False, "no valid mandate to match a verdict against"
    try:
        verdicts = list(verdict_loader(paths.verdicts))
    except Exception as exc:
        return False, "verdicts unreadable: %s" % type(exc).__name__
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        if (verdict.get("label") == "holdout" and verdict.get("verdict") == "PASS"
                and verdict.get("plan_sha256") == record.get("plan_sha256")
                and verdict.get("strategy") == mandate.strategy and verdict.get("params") == mandate.params):
            return True, "holdout PASS for %s %s (%s)" % (mandate.strategy, mandate.params_json, verdict["_file"]
                                                          if "_file" in verdict else "verdict")
    return False, "no holdout PASS verdict for %s %s under the current plan lock" % (
        mandate.strategy, mandate.params_json)


def _module_file(base, parts):
    target = base.joinpath(*parts) if parts else base
    for candidate in (target.with_suffix(".py"), target / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def execution_code_files(repo):
    """execution/*.py plus every jupiter_bot module they import, transitively (N2), plus the
    package __init__ files that importing them runs. Found by parsing the imports (ast), so a
    new dependency is covered automatically."""
    root = Path(repo) / "jupiter_bot"
    pending = sorted((root / "execution").glob("*.py"))
    seen = set()
    while pending:
        path = pending.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        parent = path.parent
        while parent != root.parent and (parent / "__init__.py").is_file():
            pending.append(parent / "__init__.py")
            parent = parent.parent
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    base = path.parent
                    for _ in range(node.level - 1):
                        base = base.parent
                    parts = node.module.split(".") if node.module else []
                elif node.module and (node.module == "jupiter_bot" or node.module.startswith("jupiter_bot.")):
                    base, parts = root, node.module.split(".")[1:]
                else:
                    continue
                targets.append(_module_file(base, parts))
                targets += [_module_file(base, parts + [alias.name]) for alias in node.names]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "jupiter_bot" or alias.name.startswith("jupiter_bot."):
                        targets.append(_module_file(root, alias.name.split(".")[1:]))
            pending += [t for t in targets if t is not None and root in t.parents]
    return sorted(seen)


def execution_code_sha256(repo):
    """sha256 over `relative/path NUL sha256(file) LF` for every file of execution_code_files."""
    digest = hashlib.sha256()
    for path in execution_code_files(repo):
        name = path.relative_to(Path(repo)).as_posix()
        digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
    return digest.hexdigest()


def gate_review(paths):
    """The review must name the commit and the exact execution code it approved (F8)."""
    name = Path(paths.review).name
    try:
        text = Path(paths.review).read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, "no %s" % name
    except (OSError, UnicodeDecodeError) as exc:
        return False, "review unreadable: %s" % type(exc).__name__
    lines = [line.strip() for line in text.splitlines()]
    if REVIEW_LINE not in lines:
        return False, "%s has no line '%s'" % (name, REVIEW_LINE)
    commits = [l.split(":", 1)[1].strip() for l in lines if l.startswith("Commit:")]
    if len(commits) != 1 or not COMMIT.match(commits[0]):
        return False, "%s needs exactly one line 'Commit: <git sha>'" % name
    hashes = [l.split(":", 1)[1].strip() for l in lines if l.startswith("Execution-SHA256:")]
    if len(hashes) != 1:
        return False, "%s needs exactly one line 'Execution-SHA256: <hash>'" % name
    current = execution_code_sha256(paths.repo)
    if hashes[0] != current:
        return False, "execution code changed since the review (now %s...); re-review" % current[:12]
    return True, "%s: %s for commit %s, code hash matches" % (name, REVIEW_LINE, commits[0][:12])


# wallet binding (F7) -------------------------------------------------------------------

def read_binding(paths, wallet):
    try:
        record = strict_json(paths.wallet_binding(wallet).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeDecodeError):
        return {"ledger": None}
    return record if isinstance(record, dict) else {"ledger": None}


def ledger_id(paths):
    return os.path.realpath(str(paths.ledger))


def bind_wallet(paths, wallet, now):
    """Bind the wallet to this ledger, once. Refuses if it is bound to another ledger."""
    current = read_binding(paths, wallet)
    if current is not None:
        if current.get("ledger") != ledger_id(paths):
            raise Rejected("wallet %s is bound to another ledger (%s); refusing" % (wallet, current.get("ledger")))
        return current
    record = {"wallet_pubkey": wallet, "ledger": ledger_id(paths), "bound_at": now}
    _write_private(paths.wallet_binding(wallet), record)
    return record


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
    _write_private(path, record)


def _write_private(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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


def journal_price(paths, now):
    """Latest observed SOL/USDC close in the journal (read-only), or None."""
    try:
        from ..marketdata.journal import Journal
        journal = Journal(paths.journal, readonly=True)
        try:
            rows = journal.bars_as_of("binance_spot_klines", "SOL/USDC", 60, now, 1)
        finally:
            journal.close()
        price = Decimal(str(rows[-1]["close"])) if rows else None
        return price if price is not None and price.is_finite() and price > 0 else None
    except Exception:
        return None


def evaluate(paths, now, ledger=None, verdict_loader=load_verdicts, lock_loader=None, lock_verify=None,
             uid=None, price_fn=None):
    """Compute mandate validity, gates and effective mode. Reads files only; no network."""
    mandate, error, sha = mandate_mod.load_once(paths.mandate)      # one read: parse and hash agree (F11)
    price = (price_fn or (lambda: journal_price(paths, now)))() if mandate else None
    problems = mandate_mod.problems(mandate, now, paths.repo, uid, price) if mandate else []
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
    elif (read_binding(paths, mandate.wallet_pubkey) or {}).get("ledger") != ledger_id(paths):
        state.mode, state.reason = "DISARMED", "wallet not bound to this ledger (another --data-dir?); re-arm here"
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
