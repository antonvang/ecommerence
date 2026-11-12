"""Event farm forward paper book runner: PROTOCOL_V3 amendment 46 = text 104 (sha256 396cf90c...), gate G31.

PAPER ONLY. It feeds closed 5m klines of BTCUSDT and ETHUSDT from the one allowed public endpoint (event_farm_source)
into ForwardBookV2 with the frozen config. No key, no account, no order: the adapter refuses every other URL.

THE ACTIVATION OBJECT. `Activation` approves the two actions (book and source) only if EVERY flag of G31 passes at
start, and nr.decide(GATE_MATRIX, "event_farm_forward_paper", now, "EVENT_FARM", flags) allows it:
- the amendment file has sha256 AMEND_SHA and stands byte for byte between the ef104 markers in PROTOCOL_V3.md;
- the code and texts of text 104 section 2 have exactly the listed sha256, in the working tree AND in git HEAD;
- the owner's statement names AMEND_SHA and the protocol, its signature verifies for principal 'owner' (ssh-keygen),
  the key is the anchored D5 key, and the hash-chained approval log holds its ACCEPTED entry;
- the activation slot lies inside the statement's validity (a later restart keeps the recorded slot);
- the 5m stream is APPROVED (or EXISTING_ACTIVE) in stream_registry.json under G31;
- the event farm test modules passed for exactly these code hashes (tests_green.json, written by `mark-tests-green`
  after a green suite);
- the host resolves to a public address through the system resolver, with no proxy variables (no DNS bypass).
A failed check: no request is made, exit code 2.

STOP RULES. A file STOP in the home directory stops the loop before the next call (lane-off / written order).
IntegrityHalt or a broken call log stop the book with exit codes 3/4 (systemd does not restart them). The code hashes
are re-checked before every step; a change stops the book (exit 5).

FILES (home ~/event_farm): event_farm_forward.db, event_farm_source_calls.jsonl, activation.json (slot and
statement, written once), status.json (last step), run.log (one line per step).
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
TOOLS = os.path.join(HERE, "research", "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from research.tools import event_farm_forward as fw  # noqa: E402
from research.tools import event_farm_forward_v2 as fv  # noqa: E402
from research.tools import event_farm_source as src  # noqa: E402
import nov14_readiness as nr  # noqa: E402
import owner_approval as oa  # noqa: E402

AMEND_SHA = "396cf90c0ea0ac58da7318f159f2d97d60075ef92ad3118db94e8b30a892451d"
AMEND_FILE = "research/desk/EVENT_FARM_FORWARD_AMENDMENT_FINAL_104.md"
PROTOCOL_ID = "EVENT_FARM_FORWARD_AMENDMENT_FINAL_104"
MARK_START, MARK_END = b"<!-- ef104:start -->\n", b"<!-- ef104:end -->"
D5_FINGERPRINT = "SHA256:lSdgtWU21pKqM1NLjrt5SytMIsj7N4lQ9R9IYfx4PJ4"
STATEMENT = "research/owner/ef_forward_104_statement.json"
APPROVAL_LOG = "research/owner/approval_log.jsonl"
ALLOWED_SIGNERS = "research/owner/allowed_signers"
STREAM_ID = "ef_fwd_5m_klines"
GATE, ACTION, STUDY = "G31_EVENT_FARM_FORWARD", "event_farm_forward_paper", "EVENT_FARM"
CODE = {                                                    # text 104 section 2
    "research/tools/event_farm.py": "7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76",
    "research/tools/event_farm_driver.py": "4b96e202266e3a5f0c8655e0ec30eefc8c170ba3b183cd97c5bf0815799b5be5",
    "research/tools/event_farm_filters.py": "1886b6f311e5eeae0d4c1a7ddbb3ad23fdead761fd0fb8ef6b0a40204aaf787c",
    "research/tools/event_farm_forward.py": "f25feba8f9c2bb86c962dfb56cce765d048919aa921f34429d2192917d32deac",
    "research/tools/event_farm_forward_v2.py": "ae8e57affae121cfc47148ab18ae211cb1e92ce20da510c2f7b28fa41a38b127",
    "research/tools/event_farm_source.py": "05907e03fe75520dacd57f4445295e1090d46996a38787a198b2ce8afa2462b7",
    "research/desk/EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md":
        "080ca5b071969810b7b058eb1759d9d3fd52441e3b54eff67e16543ea5bb2ef6",
    "research/desk/EVENT_FARM.md": "fe11a89b02003c1f3ec677fad30bb429f99bc7c967dbfe35a9fd93576b7ae10e",
}
TEST_MODULES = ("tests/test_event_farm.py", "tests/test_event_farm_driver.py", "tests/test_event_farm_filters.py",
                "tests/test_event_farm_forward.py", "tests/test_event_farm_forward_v2.py",
                "tests/test_event_farm_source.py", "tests/test_event_farm_revisions_104.py",
                "tests/test_event_farm_run.py")
PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
DEFAULT_HOME = os.path.expanduser("~/event_farm")
SLOT, OFFSET_S = 300, 20
EXIT_GATE, EXIT_HALT, EXIT_LOG, EXIT_CODE = 2, 3, 4, 5


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(path):
    with open(path, "rb") as f:
        return sha_bytes(f.read())


def git_blob(root, rel):
    """The file as committed in HEAD (bytes) or None."""
    r = subprocess.run(["git", "-C", root, "show", f"HEAD:./{rel}"], capture_output=True, timeout=30)
    return r.stdout if r.returncode == 0 else None


def code_ok(root):
    bad = [rel for rel, want in CODE.items() if not os.path.isfile(os.path.join(root, rel)) or
           sha_file(os.path.join(root, rel)) != want]
    return not bad, ("ok" if not bad else f"sha256 differs: {bad}")


def tests_fingerprint(root):
    parts = {rel: sha_file(os.path.join(root, rel)) for rel in sorted(CODE) + sorted(TEST_MODULES)
             if os.path.isfile(os.path.join(root, rel))}
    return sha_bytes(json.dumps(parts, sort_keys=True).encode())


# ------------------------------------------------------------------------------------------------ the checks
def check_amendment(root):
    try:
        if sha_file(os.path.join(root, AMEND_FILE)) != AMEND_SHA:
            return False, "amendment file sha256 differs"
        proto = open(os.path.join(root, "research/PROTOCOL_V3.md"), "rb").read()
        a, b = proto.index(MARK_START) + len(MARK_START), proto.index(MARK_END)
        if sha_bytes(proto[a:b]) != AMEND_SHA:
            return False, "PROTOCOL_V3 section between ef104 markers differs from text 104"
        head = git_blob(root, "research/PROTOCOL_V3.md")
        if head != proto:
            return False, "PROTOCOL_V3.md is not committed as it stands"
        return True, "amendment 46 committed, text 104 byte for byte"
    except (OSError, ValueError) as e:
        return False, f"amendment: {e}"


def check_code_committed(root):
    ok, why = code_ok(root)
    if not ok:
        return False, why
    for rel, want in CODE.items():
        blob = git_blob(root, rel)
        if blob is None or sha_bytes(blob) != want:
            return False, f"{rel} is not committed at its sha256"
    return True, "8 files at the text 104 sha256, committed"


def key_fingerprint(allowed_signers):
    with open(allowed_signers, encoding="utf-8") as f:
        line = next(x for x in f if x.startswith("owner "))
    key = " ".join(line.split()[2:4])
    r = subprocess.run(["ssh-keygen", "-lf", "-"], input=key.encode(), capture_output=True, timeout=30)
    return r.stdout.decode().split()[1] if r.returncode == 0 else None


def check_signature(root):
    """(ok, detail, statement)."""
    try:
        signers = os.path.join(root, ALLOWED_SIGNERS)
        if key_fingerprint(signers) != D5_FINGERPRINT:
            return False, "allowed_signers 'owner' is not the anchored D5 key", None
        raw = open(os.path.join(root, STATEMENT), encoding="utf-8").read()
        stmt = json.loads(raw)
        if raw.strip() != oa.canonical(stmt):
            return False, "statement file is not canonical", None
        if stmt.get("blob") != AMEND_SHA or stmt.get("protocol") != PROTOCOL_ID or stmt.get("scope") != "template":
            return False, "statement does not name text 104", None
        sig = open(os.path.join(root, STATEMENT + ".sig"), encoding="utf-8").read()
        if not oa.signature_ok(stmt, sig, signers):
            return False, "signature does not verify for principal 'owner'", None
        log = oa.AuditLog(os.path.join(root, APPROVAL_LOG))
        st_sha = sha_bytes(oa.canonical(stmt).encode())
        if not any(e.get("decision") == "ACCEPTED" and e.get("nonce") == stmt["nonce"] and
                   e.get("statement_sha256") == st_sha and e.get("blob") == AMEND_SHA for e in log.entries):
            return False, "no ACCEPTED approval-log entry for this statement", None
        return True, f"D5 signature verified, nonce {stmt['nonce']}", stmt
    except (OSError, ValueError, StopIteration, KeyError, oa.ApprovalError, subprocess.SubprocessError) as e:
        return False, f"signature: {type(e).__name__}: {e}", None


def check_stream(root):
    try:
        reg = json.load(open(os.path.join(root, "research/desk/stream_registry.json"), encoding="utf-8"))
        s = [x for x in reg["streams"] if x["id"] == STREAM_ID]
        ok = len(s) == 1 and s[0]["status"] in ("APPROVED", "EXISTING_ACTIVE") and s[0]["gate"] == GATE and \
            s[0]["source_host"] == src.HOST
        return ok, "5m stream approved" if ok else "5m stream not approved in stream_registry.json"
    except (OSError, ValueError, KeyError) as e:
        return False, f"stream registry: {e}"


def check_tests(root, home):
    try:
        rec = json.load(open(os.path.join(home, "tests_green.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return False, "no tests_green.json (run mark-tests-green after a green suite)"
    ok = rec.get("fingerprint") == tests_fingerprint(root)
    return ok, "event farm tests green for these code hashes" if ok else "tests_green.json is for other code"


def check_host(resolve=socket.getaddrinfo, env=os.environ):
    if any(env.get(v) for v in PROXY_VARS):
        return False, "a proxy variable is set (no bypass)"
    try:
        addrs = {a[4][0] for a in resolve(src.HOST, 443, proto=socket.IPPROTO_TCP)}
    except OSError as e:
        return False, f"host does not resolve: {e}"
    pub = [a for a in addrs if ipaddress.ip_address(a).is_global]
    return (bool(pub) and len(pub) == len(addrs)), f"resolves to {sorted(addrs)}"


FLAG_ORDER = ("director_approves_event_farm_forward_amendment", "event_farm_forward_amendment_committed",
              "owner_key_registered", "owner_signed_event_farm_forward_amendment_sha256",
              "fwd_5m_kline_stream_approved", "event_farm_forward_code_committed",
              "event_farm_forward_source_adapter_committed", "loader_tests_green", "host_reachable_without_bypass")


def run_checks(root, home, now, resolve=socket.getaddrinfo, env=os.environ):
    """{flag: (ok, detail)}, plus 'validity' and 'decide'; and the statement."""
    c = {}
    c["director_approves_event_farm_forward_amendment"] = (
        sha_file(os.path.join(root, AMEND_FILE)) == AMEND_SHA,
        "director decision 106 approved text 104 as the basis for the signature")
    c["event_farm_forward_amendment_committed"] = check_amendment(root)
    sig_ok, sig_why, stmt = check_signature(root)
    try:
        fp = key_fingerprint(os.path.join(root, ALLOWED_SIGNERS))
    except (OSError, StopIteration, subprocess.SubprocessError):
        fp = None
    c["owner_key_registered"] = (fp == D5_FINGERPRINT, f"owner key {fp} (D5 ANCHORED, decision 97)")
    c["owner_signed_event_farm_forward_amendment_sha256"] = (sig_ok, sig_why)
    c["fwd_5m_kline_stream_approved"] = check_stream(root)
    cc = check_code_committed(root)
    c["event_farm_forward_code_committed"] = cc
    c["event_farm_forward_source_adapter_committed"] = cc
    c["loader_tests_green"] = check_tests(root, home)
    c["host_reachable_without_bypass"] = check_host(resolve, env)
    act = read_activation(home)
    slot = act["start_ts"] if act else next_slot(now)
    if stmt is None:
        c["validity"] = (False, "no verified statement")
    elif act and act.get("statement_sha256") != sha_bytes(oa.canonical(stmt).encode()):
        c["validity"] = (False, "activation.json belongs to another statement")
    else:
        inside = stmt["issued"] <= (act["activated_at"] if act else now) < stmt["expires"]
        c["validity"] = (inside, "activated inside the statement's validity" if inside else
                         "activation would fall outside the statement's validity (a new signature is needed)")
    flags = {f for f in FLAG_ORDER if c[f][0]}
    with open(os.path.join(root, "research/desk/GATE_MATRIX.json"), encoding="utf-8") as f:
        matrix = json.load(f)
    allowed, reasons = nr.decide(matrix, ACTION, now, STUDY, flags)
    c["decide"] = (allowed, "G31 and G15 OPEN" if allowed else "; ".join(reasons))
    return c, stmt, slot


class Activation:
    """approved(action) is True only for the book and source actions, and only if every check passed."""

    def __init__(self, checks):
        self.ok = all(v[0] for v in checks.values())

    def approved(self, action):
        return self.ok and action in (fw.ACTION, src.ACTION)


# ------------------------------------------------------------------------------------------------ files
def read_activation(home):
    try:
        return json.load(open(os.path.join(home, "activation.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, sort_keys=True, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def next_slot(now):
    return int(-(-now // SLOT) * SLOT)


def log_line(home, rec):
    with open(os.path.join(home, "run.log"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())


def open_book(root, home, now, transport=None, clock=None, resolve=socket.getaddrinfo, env=os.environ):
    """(book, checks) or (None, checks) if any check fails. Writes activation.json on the first good start."""
    os.makedirs(home, exist_ok=True)
    checks, stmt, slot = run_checks(root, home, now, resolve, env)
    act = Activation(checks)
    if not act.ok:
        return None, checks
    if read_activation(home) is None:
        write_json(os.path.join(home, "activation.json"),
                   {"start_ts": slot, "activated_at": now, "statement_sha256": sha_bytes(oa.canonical(stmt).encode()),
                    "nonce": stmt["nonce"], "amendment_sha256": AMEND_SHA, "protocol": "PROTOCOL_V3 amendment 46"})
    slot = read_activation(home)["start_ts"]
    source = src.KlineSource(act, slot, os.path.join(home, "event_farm_source_calls.jsonl"), transport=transport,
                             clock=clock)
    book = fv.ForwardBookV2(os.path.join(home, "event_farm_forward.db"), source, fw.LIVE_SYMBOLS, mode="live",
                            activation=act, clock=clock)
    return book, checks


def step_once(root, home, book, now):
    if os.path.exists(os.path.join(home, "STOP")):
        return "stopped", None
    ok, why = code_ok(root)
    if not ok:
        return "code_changed", why
    stats = book.step()
    status = {"ts": now, "stats": stats, "halted": book.halted(), "start_ts": read_activation(home)["start_ts"]}
    write_json(os.path.join(home, "status.json"), status)
    log_line(home, {"ts": round(now, 1), **stats})
    return "ok", stats


def run(root, home, once=False, sleep=time.sleep, clock=time.time, transport=None):
    now = clock()
    book, checks = open_book(root, home, now, transport=transport, clock=clock)
    for k, (ok, why) in checks.items():
        print(f"{'OK ' if ok else 'NO '} {k}: {why}", flush=True)
    if book is None:
        print("GATE CLOSED: no request made", flush=True)
        return EXIT_GATE
    while True:
        if not once:
            now = clock()
            wait = next_slot(now) + OFFSET_S - now
            if wait > SLOT:
                wait -= SLOT
            sleep(max(0.0, wait))
        try:
            what, detail = step_once(root, home, book, clock())
        except fw.IntegrityHalt as e:
            log_line(home, {"ts": clock(), "halt": str(e)})
            print(f"INTEGRITY HALT: {e}", flush=True)
            return EXIT_HALT
        except src.LogBroken as e:
            log_line(home, {"ts": clock(), "log_broken": str(e)})
            print(f"CALL LOG BROKEN: {e}", flush=True)
            return EXIT_LOG
        except Exception as e:                              # noqa: BLE001 - rolled back by the book; try next slot
            log_line(home, {"ts": clock(), "error": f"{type(e).__name__}: {e}"})
            print(f"step error (rolled back): {type(e).__name__}: {e}", flush=True)
            what, detail = "error", None
        if what == "stopped":
            print("STOP file present: stopped before the next call", flush=True)
            return 0
        if what == "code_changed":
            print(f"CODE CHANGED: {detail}", flush=True)
            return EXIT_CODE
        if what == "ok":
            print(f"step {json.dumps(detail, sort_keys=True)}", flush=True)
        if once:
            return 0


def mark_tests_green(root, home, suite_summary):
    os.makedirs(home, exist_ok=True)
    rec = {"fingerprint": tests_fingerprint(root), "suite": suite_summary, "marked_at": time.time()}
    write_json(os.path.join(home, "tests_green.json"), rec)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="event farm forward paper book (PROTOCOL_V3 amendment 46)")
    ap.add_argument("cmd", choices=("check", "once", "run", "mark-tests-green"))
    ap.add_argument("--home", default=DEFAULT_HOME)
    ap.add_argument("--suite", default="", help="mark-tests-green: the suite's summary line")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        checks, _, slot = run_checks(HERE, a.home, time.time())
        for k, (ok, why) in checks.items():
            print(f"{'OK ' if ok else 'NO '} {k}: {why}")
        print("activation slot", slot, "| all ok" if all(v[0] for v in checks.values()) else "| GATE CLOSED")
        return 0 if all(v[0] for v in checks.values()) else EXIT_GATE
    if a.cmd == "mark-tests-green":
        if not a.suite:
            ap.error("--suite is required")
        print(json.dumps(mark_tests_green(HERE, a.home, a.suite)))
        return 0
    return run(HERE, a.home, once=(a.cmd == "once"))


if __name__ == "__main__":
    sys.exit(main())
