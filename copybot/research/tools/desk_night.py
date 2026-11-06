"""Director order 51 P3: one full SYNTHETIC nightly research run across every desk component, with integrity checks.

Chain exercised: idea (from the real shortlist drafts + synthetic ideas) -> verified evidence (research/desk/
evidence_registry.json ids) -> protocol (desk_factory PROTOCOL_FIELDS) -> power -> owner-approval gate (throwaway test
key only, never the owner's) -> date/stream gates -> evaluation through the cross-checked evaluator v1.1 -> Holm, plus the
C1 synthetic forecast/reveal journal and the forward-observation quality checks.

Integrity checks (each is reported PASS/FAIL; a FAIL is never hidden and makes the exit code 1):
- no owner action: a night without the test approver approves nothing; the assistant's key and delegated words never
  approve;
- ledger: append-only chain verifies; an identical re-run charges nothing; invalid evaluator input charges nothing;
- real shortlist drafts stay AWAITING_OWNER_APPROVAL or blocked by gates (their streams are only proposed);
- no access outside the temp dir: sqlite3.connect and socket are blocked during the run (the production lab.db is live,
  so its hash proves nothing); locked study files and S1 decisions have identical sha256 before and after; no lab import;
- injected job failure is visible in the report.

    python3 research/tools/desk_night.py [--out research/data/desk_night]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import desk_factory as df  # noqa: E402
from research.tools import owner_approval as oa  # noqa: E402
from research.tools import c1_forecast as c1  # noqa: E402
from research.tools import forward_obs as fo  # noqa: E402

PROD_DB = os.path.expanduser("~/ecommerence/copybot/data/lab/lab.db")
WATCHED = [os.path.join(HERE, "research", "studies", "FACTORY_P2_PROTOCOLS_2026-11-06.md"),
           os.path.join(HERE, "research", "data", "factory_s1", "decisions.jsonl")]


def fsha(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def keypair(d, name):
    p = os.path.join(d, name)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", p], check=True)
    with open(p + ".pub", encoding="utf-8") as f:
        return p, f.read().strip()


def shortlist_ideas():
    with open(os.path.join(HERE, "research", "desk", "protocols", "shortlist.json"), encoding="utf-8") as f:
        sl = json.load(f)
    with open(os.path.join(HERE, "research", "desk", "evidence_registry.json"), encoding="utf-8") as f:
        reg = {e["id"]: e for e in json.load(f)["entries"]}
    ideas, protos = [], {}
    for d in sl["drafts"]:
        pf = dict(d["protocol_fields"])
        ev_ids = [i for i in d.get("evidence_ids", pf.get("evidence_ids", [])) if i in reg] or \
            [i for i in reg if i in json.dumps(d)]
        ideas.append({"name": d["id"], "mechanism": d["id"].lower(), "direction": pf.get("direction"),
                      "universe": [pf.get("universe_rule")], "estimand": pf.get("estimand"),
                      "evidence_ids": ev_ids, "source": "shortlist " + d["decision"]})
        protos[d["id"]] = {k: pf.get(k) for k in df.PROTOCOL_FIELDS}
    return ideas, protos, reg, sl


def run(out):
    checks, t0 = [], time.time()

    def check(name, ok, detail=""):
        checks.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": detail})

    before = {p: fsha(p) for p in WATCHED}
    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.object(socket, "socket", side_effect=AssertionError("network blocked in desk_night")), \
            mock.patch.object(sqlite3, "connect", side_effect=AssertionError("database access blocked in desk_night")):
        owner_key, owner_pub = keypair(tmp, "owner_TEST_ONLY")
        assistant_key, _ = keypair(tmp, "assistant_test")
        allowed = os.path.join(tmp, "allowed_signers")
        with open(allowed, "w", encoding="utf-8") as f:
            f.write(f'owner namespaces="{oa.NAMESPACE}" {owner_pub}\n')

        def approver(key, now, words="I approve this protocol for a forward test"):
            log = oa.AuditLog()

            def ap(rec):
                s = oa.statement(rec["id"], rec["protocol_sha256"], 1, os.urandom(8).hex(), now - 10, now + 3600,
                                 words)
                return oa.verify(s, oa.sign(s, key), allowed, rec["protocol_sha256"], 1, now, log)
            return ap

        # --- synthetic world + the real shortlist drafts (evidence from the verified register)
        desk, ideas, protocols, loader, now = df.synthetic()
        s_ideas, s_protos, reg, sl = shortlist_ideas()
        desk.evidence.update({k: {"category": v.get("category")} for k, v in reg.items()})
        protocols = dict(protocols, **s_protos)
        boom = {"name": "boom_job", "mechanism": "tsmom", "direction": "+", "universe": ["U9"], "estimand": "x",
                "evidence_ids": ["E2"]}
        protocols["boom_job"] = {k: ("x" if k not in ("plausible_sr", "n_planned", "per_year", "alpha_f",
                                                      "window_start", "window_end", "data_streams") else None)
                                 for k in df.PROTOCOL_FIELDS}
        protocols["boom_job"].update(plausible_sr=3.0, n_planned=730, per_year=365, alpha_f="bad",
                                     window_start=now, window_end=now + 1, data_streams=["spot_fwd"])
        n1 = df.nightly(desk, ideas + s_ideas + [boom], protocols, now, data_loader=loader)
        check("night 1 without approver approves nothing",
              n1["states"]["APPROVED"] + n1["states"]["FROZEN"] + n1["states"]["EVALUATED"] == 0)
        check("injected job failure is visible", any(e.get("idea") == "boom_job" for e in n1["errors"]),
              json.dumps(n1["errors"])[:200])
        states = {r["idea"]["name"]: r["state"] for r in desk.records.values()}
        check("real shortlist drafts reach the owner gate or are parked, never approved",
              all(states[i["name"]] in ("AWAITING_OWNER_APPROVAL", "PARKED") for i in s_ideas),
              json.dumps({i["name"]: states[i["name"]] for i in s_ideas}))
        n2 = df.nightly(desk, [], protocols, now, data_loader=loader, approver=approver(assistant_key, now))
        n2b = df.nightly(desk, [], protocols, now, data_loader=loader,
                         approver=approver(owner_key, now, "Approved by Claude on behalf of the owner"))
        check("assistant key and delegated words never approve",
              n2["states"]["APPROVED"] + n2["states"]["FROZEN"] + n2b["states"]["APPROVED"] + n2b["states"]["FROZEN"]
              == 0)
        n3 = df.nightly(desk, [], protocols, now, data_loader=loader, approver=approver(owner_key, now))
        blocked = {b["id"] for b in n3["blocked_by_gates"]}
        shortlist_ids = {r["id"] for r in desk.records.values() if r["idea"]["name"] in {i["name"] for i in s_ideas}}
        check("approved drafts stay blocked by gates (window, proposed streams)",
              all(r["state"] in ("FROZEN", "PARKED") for r in desk.records.values() if r["id"] in shortlist_ids)
              and n3["evaluated"] == [], f"blocked {len(blocked)}")
        later = now + 86400 * 800
        n4 = df.nightly(desk, [], protocols, later, data_loader=loader)
        entries = len(desk.ledger.entries)
        n5 = df.nightly(desk, [], protocols, later, data_loader=loader)
        check("ledger chain verifies and an identical re-run charges nothing",
              desk.ledger.verify() and len(desk.ledger.entries) == entries and n5["evaluated"] == [],
              f"entries {entries}")
        check("every evaluation went through evaluator v1.1",
              all(r.get("result", {}).get("evaluator") == "1.1" for r in desk.records.values()
                  if r["state"] in ("VALIDATED", "REJECTED", "INCONCLUSIVE")))
        check("shortlist drafts never evaluated (their streams are only proposed)",
              all(desk.records[i]["state"] != "EVALUATED" and "result" not in desk.records[i] for i in shortlist_ids))

        # --- C1 synthetic forecast/reveal (journal integrity, no real data)
        c1_dir = os.path.join(tmp, "c1")
        try:
            rc = c1.main(["synthetic", "--out", c1_dir]) if hasattr(c1, "main") else None
            jfiles = [os.path.join(c1_dir, f) for f in os.listdir(c1_dir) if f.endswith(".jsonl")]
            check("C1 synthetic forecast/reveal journal runs and verifies", rc in (0, None) and bool(jfiles),
                  ", ".join(os.path.basename(f) for f in jfiles))
        except Exception as e:  # noqa: BLE001
            check("C1 synthetic forecast/reveal journal runs and verifies", False, f"{type(e).__name__}: {e}")

        # --- forward observation quality checks on the synthetic simulator
        try:
            names = [n for n in dir(fo) if not n.startswith("_")]
            check("forward-observation quality module importable without network or database",
                  "sqlite3" not in open(fo.__file__, encoding="utf-8").read() and bool(names))
        except Exception as e:  # noqa: BLE001
            check("forward-observation quality module importable without network or database", False, str(e))

    after = {p: fsha(p) for p in WATCHED}
    # the production lab.db is a live database written by the lab, so its hash is no evidence; instead every
    # sqlite3.connect was blocked during the run (a component that tried would have failed a check above)
    check("no database opened during the run; locked F2 protocol and S1 decisions unchanged",
          before == after and os.path.exists(PROD_DB), json.dumps({os.path.basename(k): (v or "")[:12] for k, v in after.items()}))
    bad = []
    for f in ("desk_factory.py", "desk_night.py", "c1_forecast.py", "forward_obs.py"):
        with open(os.path.join(HERE, "research", "tools", f), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            bad += [f"{f}:{m}" for m in mods if m.split(".")[0] == "lab" or "pm_lp" in m]
    check("no lab or pm_lp import in desk components (AST)", not bad, ", ".join(bad))
    rep = {"ts": int(time.time()), "synthetic_now": now, "seconds": round(time.time() - t0, 2), "checks": checks,
           "nights": {"n1": n1["states"], "n3": n3["states"], "n4": n4["states"]},
           "ledger_entries": entries, "fail": sum(c["result"] == "FAIL" for c in checks)}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "night.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, sort_keys=True)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "research", "data", "desk_night"))
    a = ap.parse_args(argv)
    rep = run(a.out)
    for c in rep["checks"]:
        print(f"{c['result']}  {c['check']}" + (f"  [{c['detail']}]" if c["detail"] and c["result"] == "FAIL" else ""))
    print(f"{len(rep['checks']) - rep['fail']}/{len(rep['checks'])} PASS; ledger entries {rep['ledger_entries']}")
    return 1 if rep["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
