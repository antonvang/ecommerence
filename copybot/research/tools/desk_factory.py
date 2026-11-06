"""Director order 50 P2: nightly research factory — isolated, synthetic orchestration prototype.

State machine (one record per idea; transitions only forward along this chain, terminal states final):

    IDEA -> LITERATURE_SCREENED -> PROTOCOL_DRAFT -> POWER_CHECKED -> AWAITING_OWNER_APPROVAL -> APPROVED -> FROZEN
         -> DATA_ELIGIBLE -> EVALUATED -> REJECTED | INCONCLUSIVE | VALIDATED
    side exits: PARKED (duplicate, no literature, insufficient power, failed job), never deleted.

Rules enforced here (tests in tests/test_research_desk_factory.py):
- ideas may be generated automatically; duplicates (same fingerprint) and related mechanisms (same lineage) are found;
- power is computed before any data (research/tools/p2_power.sr_power) at a stated plausible effect; < 0.8 parks;
- the run NEVER creates or simulates an owner approval: AWAITING_OWNER_APPROVAL -> APPROVED only through an injected
  `approver` callback that must return an ACCEPTED owner-signature verification (research/tools/owner_approval.verify);
  the nightly run passes no approver, so nothing is approved;
- FROZEN needs the full protocol + its sha256; DATA_ELIGIBLE needs every data gate (earliest data time, protected
  periods, stream status) to pass at `now`; data is only handed to the evaluator after DATA_ELIGIBLE;
- each evaluation charges the append-only ledger (research/tools/factory.Ledger) with an idempotent key before the
  test; Holm over the family's evaluated hypotheses is the primary decision; nothing is reopened or promoted;
- a failing job is recorded and parks only that idea; the run itself never raises and never touches the lab
  (it imports no lab module and writes only to its own output directory);
- queue and resource budget: at most `max_new_ideas` per night and `cpu_budget_s` CPU seconds for the run.

    python3 research/tools/desk_factory.py --synthetic --out research/data/desk_factory
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import hypo_engine as he  # noqa: E402
from research.tools import p2_power  # noqa: E402
from research.tools.factory import Ledger, FactoryError  # noqa: E402
from research.desk.crosscheck import claude_eval_v111 as ev  # noqa: E402

CHAIN = ["IDEA", "LITERATURE_SCREENED", "PROTOCOL_DRAFT", "POWER_CHECKED", "AWAITING_OWNER_APPROVAL", "APPROVED",
         "FROZEN", "DATA_ELIGIBLE", "EVALUATED"]
TERMINAL = {"REJECTED", "INCONCLUSIVE", "VALIDATED", "PARKED"}
PROTOCOL_FIELDS = ("primary_hypothesis", "estimand", "direction", "universe_rule", "window_start", "window_end",
                   "cost_model", "data_streams", "alpha_f", "plausible_sr", "per_year", "n_planned")
POWER_MIN = 0.8
ALPHA = 0.05


class DeskError(Exception):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def fingerprint(idea):
    return sha([idea.get("mechanism"), idea.get("direction"), sorted(idea.get("universe") or []),
                idea.get("estimand")])


class Desk:
    def __init__(self, evidence=None, lineage_of=None, streams=None, protected=None):
        self.records, self.log, self.ledger = {}, [], Ledger()
        self.evidence = evidence or {}               # registry id -> entry (research/desk/evidence_registry.json)
        self.lineage_of = lineage_of or (lambda m: m)
        self.streams = streams or {}                 # stream id -> {"status", "available_from"}
        self.protected = protected or []             # [(start_ts, end_ts, reason)] never accessible

    # ------------------------------------------------------------ bookkeeping
    def _move(self, rec, to, now, note=""):
        cur = rec["state"]
        if cur in TERMINAL:
            raise DeskError(f"{rec['id']}: {cur} is terminal")
        if to not in TERMINAL and CHAIN.index(to) != CHAIN.index(cur) + 1:
            raise DeskError(f"{rec['id']}: {cur} -> {to} skips the chain")
        if cur == "EVALUATED" and to == "PARKED":
            raise DeskError("an evaluated hypothesis is never parked")
        rec["state"] = to
        rec["history"].append({"ts": now, "to": to, "note": note})
        self.log.append({"ts": now, "id": rec["id"], "from": cur, "to": to, "note": note})

    def park(self, rec, now, reason):
        rec["park_reason"] = reason
        self._move(rec, "PARKED", now, reason)

    # ------------------------------------------------------------ stages
    def add_idea(self, idea, now):
        fp = fingerprint(idea)
        dup = next((r for r in self.records.values() if r["fingerprint"] == fp), None)
        rid = f"D{len(self.records):04d}"
        rec = {"id": rid, "idea": idea, "fingerprint": fp, "lineage": self.lineage_of(idea.get("mechanism")),
               "state": "IDEA", "history": [{"ts": now, "to": "IDEA", "note": idea.get("source", "")}]}
        self.records[rid] = rec
        rec["related"] = sorted(r["id"] for r in self.records.values()
                                if r["id"] != rid and r["lineage"] == rec["lineage"])
        if dup:
            self.park(rec, now, f"DUPLICATE of {dup['id']}")
        return rec

    def screen_literature(self, rec, now):
        ids = [i for i in rec["idea"].get("evidence_ids", []) if i in self.evidence]
        if not ids:
            return self.park(rec, now, "NO_VERIFIED_LITERATURE")
        rec["evidence_ids"] = ids
        self._move(rec, "LITERATURE_SCREENED", now, ",".join(ids))

    def draft_protocol(self, rec, protocol, now):
        missing = [f for f in PROTOCOL_FIELDS if protocol.get(f) in (None, "", [])]
        if missing:
            return self.park(rec, now, "PROTOCOL_INCOMPLETE:" + ",".join(missing))
        rec["protocol"], rec["protocol_sha256"] = protocol, sha(protocol)
        self._move(rec, "PROTOCOL_DRAFT", now, rec["protocol_sha256"][:12])

    def check_power(self, rec, now):
        p = rec["protocol"]
        pw = p2_power.sr_power(p["plausible_sr"], p["n_planned"], p["per_year"], p["alpha_f"])
        rec["power"] = pw
        if pw < POWER_MIN:
            return self.park(rec, now, f"INSUFFICIENT_POWER {pw:.3f} < {POWER_MIN}")
        self._move(rec, "POWER_CHECKED", now, f"power {pw:.3f}")
        self._move(rec, "AWAITING_OWNER_APPROVAL", now, "needs a signed owner statement")

    def approve(self, rec, now, approver=None):
        """Only an injected approver that returns ("ACCEPTED", []) from owner_approval.verify can approve."""
        if approver is None:
            return False
        decision, reasons = approver(rec)
        if decision != "ACCEPTED":
            rec.setdefault("approval_refusals", []).append(reasons)
            return False
        self._move(rec, "APPROVED", now, "owner signature verified")
        return True

    def freeze(self, rec, now):
        if rec["state"] != "APPROVED":
            raise DeskError("only an approved protocol is frozen")
        if sha(rec["protocol"]) != rec["protocol_sha256"]:
            raise DeskError("protocol changed after approval")
        rec["frozen_ts"] = now
        self._move(rec, "FROZEN", now, rec["protocol_sha256"][:12])

    def gates(self, rec, now):
        p, why = rec["protocol"], []
        if now < p["window_end"]:
            why.append("window not finished")
        for s in p["data_streams"]:
            st = self.streams.get(s)
            if st is None or st["status"] != "EXISTING_ACTIVE":
                why.append(f"stream {s} not active")
            elif now < st.get("available_from", 0):
                why.append(f"stream {s} gated until {st['available_from']}")
        for a, b, reason in self.protected:
            if p["window_start"] < b and a < p["window_end"]:
                why.append(f"protected period: {reason}")
        if rec.get("frozen_ts") is None or rec["frozen_ts"] > p["window_start"]:
            why.append("protocol not frozen before the window start")
        return why

    def make_eligible(self, rec, now):
        why = self.gates(rec, now)
        if why:
            rec["gate_block"] = why
            return False
        self._move(rec, "DATA_ELIGIBLE", now, "all gates pass")
        return True

    def evaluate(self, rec, now, data_loader, family_results):
        """The loader returns an EVALUATOR_SPEC v1.1 fixture whose hypotheses include rec["id"] (the primary).
        Input is validated fail-closed BEFORE the ledger charge; an invalid input charges nothing, changes no state
        and is reported. A valid evaluation charges first (idempotent key), then runs the cross-checked evaluator."""
        if rec["state"] != "DATA_ELIGIBLE":
            raise DeskError("data only after DATA_ELIGIBLE")
        fx = data_loader(rec)
        errs = ev.validate(fx)
        hids = [h.get("hid") for h in fx.get("hypotheses", [])] if isinstance(fx, dict) else []
        if not errs and rec["id"] not in hids:
            errs = [("PRIMARY_MISSING", "hypotheses")]
        if errs:
            rec["evaluation_refused"] = [list(e) for e in errs]
            raise DeskError(f"{rec['id']}: evaluator input invalid: {errs[:3]}")
        key = sha([rec["id"], rec["protocol_sha256"], ev.sha(fx), ev.VERSION])
        self.ledger.charge(rec["id"], rec["lineage"], now, 1, rec["protocol"]["alpha_f"], "desk_factory", key=key)
        out = ev.evaluate(fx)
        r = out["hypotheses"][rec["id"]]
        rec["result"] = {k: r[k] for k in ("T", "mean_net", "t", "p_one", "status", "hac_lag")}
        rec["result"]["evaluator"] = ev.VERSION
        if r["status"] != "TESTED":
            self._move(rec, "EVALUATED", now, r["status"])
            return self._move(rec, "INCONCLUSIVE", now, r["status"])
        self._move(rec, "EVALUATED", now, f"t {r['t']:.2f}")
        family_results.setdefault(rec["lineage"], []).append(rec)

    def decide(self, family_results, now):
        for fam, recs in family_results.items():
            rej = he.holm([r["result"]["p_one"] for r in recs], ALPHA)
            for r, ok in zip(recs, rej):
                self._move(r, "VALIDATED" if ok else "REJECTED", now, f"Holm over {len(recs)} in {fam}")


# ---------------------------------------------------------------- nightly run

def nightly(desk, ideas, protocols, now, data_loader=None, approver=None, max_new_ideas=20, cpu_budget_s=60.0):
    """One night. Never raises; every job failure parks only its idea. Returns the report dict."""
    t0 = time.process_time()
    report = {"ts": now, "new": [], "parked": [], "awaiting_owner": [], "blocked_by_gates": [], "evaluated": [],
              "errors": [], "budget_exhausted": False, "queued": 0}
    queue = list(ideas)[:max_new_ideas]
    report["queued"] = max(0, len(ideas) - max_new_ideas)
    for idea in queue:
        if time.process_time() - t0 > cpu_budget_s:
            report["budget_exhausted"] = True
            break
        try:
            rec = desk.add_idea(idea, now)
            report["new"].append(rec["id"])
            if rec["state"] == "IDEA":
                desk.screen_literature(rec, now)
            if rec["state"] == "LITERATURE_SCREENED":
                desk.draft_protocol(rec, protocols.get(idea.get("name"), {}), now)
            if rec["state"] == "PROTOCOL_DRAFT":
                desk.check_power(rec, now)
        except Exception as e:                       # noqa: BLE001 - a failed job never stops the run
            report["errors"].append({"idea": idea.get("name"), "error": f"{type(e).__name__}: {e}"})
            if "rec" in locals() and rec["state"] not in TERMINAL and rec["state"] != "EVALUATED":
                desk.park(rec, now, "JOB_FAILED")
    fam = {}
    for rec in list(desk.records.values()):
        try:
            if rec["state"] == "AWAITING_OWNER_APPROVAL":
                if not desk.approve(rec, now, approver):
                    report["awaiting_owner"].append(rec["id"])
                    continue
            if rec["state"] == "APPROVED":
                desk.freeze(rec, now)
            if rec["state"] == "FROZEN" and not desk.make_eligible(rec, now):
                report["blocked_by_gates"].append({"id": rec["id"], "why": rec["gate_block"]})
                continue
            if rec["state"] == "DATA_ELIGIBLE" and data_loader is not None:
                desk.evaluate(rec, now, data_loader, fam)
                report["evaluated"].append(rec["id"])
        except Exception as e:                       # noqa: BLE001
            report["errors"].append({"id": rec["id"], "error": f"{type(e).__name__}: {e}"})
    try:
        desk.decide(fam, now)
    except Exception as e:                           # noqa: BLE001
        report["errors"].append({"stage": "decide", "error": f"{type(e).__name__}: {e}"})
    report["parked"] = sorted(r["id"] + ":" + r.get("park_reason", "") for r in desk.records.values()
                              if r["state"] == "PARKED")
    report["states"] = {s: sum(r["state"] == s for r in desk.records.values()) for s in CHAIN + sorted(TERMINAL)}
    report["ledger_ok"] = desk.ledger.verify()
    report["cpu_s"] = round(time.process_time() - t0, 3)
    return report


def report_md(rep):
    L = [f"# Natlig forskningsfabrik (syntetisk) — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(rep['ts']))}", "",
         f"Nye idéer: {len(rep['new'])}; i kø til næste nat: {rep['queued']}; CPU {rep['cpu_s']} s; "
         f"budget opbrugt: {rep['budget_exhausted']}; ledger intakt: {rep['ledger_ok']}.", "",
         "| Tilstand | Antal |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in rep["states"].items() if v]
    L += ["", "Parkerede (afviste idéer): " + ("; ".join(rep["parked"]) or "ingen"),
          "Afventer ejerens signerede godkendelse (simuleres aldrig): " + (", ".join(rep["awaiting_owner"]) or "ingen"),
          "Blokeret af datagates: " + ("; ".join(f"{b['id']} ({', '.join(b['why'])})" for b in rep["blocked_by_gates"])
                                       or "ingen"),
          "Evalueret: " + (", ".join(rep["evaluated"]) or "ingen"),
          "Fejl (kun det enkelte job stoppet): " + (json.dumps(rep["errors"], ensure_ascii=False) if rep["errors"]
                                                   else "ingen")]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- synthetic end-to-end world

def synthetic(seed=0):
    rng = random.Random(seed)
    evidence = {"E1": {"category": 1}, "E2": {"category": 3}, "E3": {"category": 4}}
    lineage = {"funding_persist": "carry", "basis_carry": "carry", "tsmom": "momentum", "st_reversal": "reversal"}
    now = 1_800_000_000
    streams = {"funding_fwd": {"status": "EXISTING_ACTIVE", "available_from": 0},
               "spot_fwd": {"status": "EXISTING_ACTIVE", "available_from": 0},
               "coinm_fwd": {"status": "BLOCKED_UNTIL_2026-11-28", "available_from": now + 10 ** 7}}
    ideas = [
        {"name": "fund_persist_A", "mechanism": "funding_persist", "direction": "+", "universe": ["U1"],
         "estimand": "net 8h", "evidence_ids": ["E1"], "source": "literature"},
        {"name": "fund_persist_A_copy", "mechanism": "funding_persist", "direction": "+", "universe": ["U1"],
         "estimand": "net 8h", "evidence_ids": ["E1"], "source": "auto"},
        {"name": "basis_B", "mechanism": "basis_carry", "direction": "+", "universe": ["U1"], "estimand": "net 1d",
         "evidence_ids": ["E1"], "source": "literature"},
        {"name": "tsmom_C", "mechanism": "tsmom", "direction": "+", "universe": ["U2"], "estimand": "net 1w",
         "evidence_ids": ["E2"], "source": "literature"},
        {"name": "rumour_D", "mechanism": "st_reversal", "direction": "-", "universe": ["U2"], "estimand": "net 1d",
         "evidence_ids": ["X9"], "source": "blog"},
        {"name": "rev_E_lowpower", "mechanism": "st_reversal", "direction": "-", "universe": ["U3"],
         "estimand": "net 1h", "evidence_ids": ["E3"], "source": "literature"},
        {"name": "coinm_F", "mechanism": "basis_carry", "direction": "+", "universe": ["U4"], "estimand": "net 1q",
         "evidence_ids": ["E1"], "source": "literature"},
        {"name": "bad_G", "mechanism": "tsmom", "direction": "-", "universe": ["U5"], "estimand": "net 1d",
         "evidence_ids": ["E2"], "source": "auto"},
    ]

    def proto(sr, n, streams_, start=now + 86400):
        return {"primary_hypothesis": "mean net > 0", "estimand": "mean daily net return", "direction": "+",
                "universe_rule": "listed >= 30d before start", "window_start": start,
                "window_end": start + n * 86400, "cost_model": "taker 5 bp + spread", "data_streams": streams_,
                "alpha_f": 0.0125, "plausible_sr": sr, "per_year": 365, "n_planned": n}
    protocols = {"fund_persist_A": proto(3.0, 730, ["funding_fwd", "spot_fwd"]),
                 "basis_B": proto(2.5, 730, ["funding_fwd", "spot_fwd"]),
                 "tsmom_C": proto(2.5, 730, ["spot_fwd"]),
                 "rev_E_lowpower": proto(0.5, 60, ["spot_fwd"]),
                 "coinm_F": proto(3.0, 730, ["coinm_fwd"]),
                 "bad_G": {"primary_hypothesis": "", "estimand": "x"}}
    effects = {"fund_persist_A": 0.004, "basis_B": 0.0, "tsmom_C": 0.0}

    def loader(rec):
        """Synthetic v1.1 fixture: one asset, daily bars, signal always long, effect mu per bar."""
        r2 = random.Random(rec["id"])
        mu = effects.get(rec["idea"]["name"], 0.0)
        p = rec["protocol"]
        obs = [{"ts": p["window_start"] + k * 86400, "asset": "U", "ret": mu + r2.gauss(0, 0.01), "funding": 0.0,
                "signals": {"s": {"value": 1.0, "avail_ts": p["window_start"]}}} for k in range(p["n_planned"])]
        return {"fixture_id": rec["id"], "cadence_s": 86400, "alpha": 0.05, "q_fdr": 0.1,
                "window": {"start": p["window_start"], "end": p["window_end"]},
                "universe": {"U": {"listed_from": p["window_start"], "delisted_at": None}},
                "hypotheses": [{"hid": rec["id"], "family": rec["lineage"], "signal_key": "s", "rule": "sign",
                                "cost_bps": 0.0, "funding": False}],
                "observations": obs, "ledger_requests": []}
    _ = rng
    return Desk(evidence, lambda m: lineage.get(m, m), streams, [(0, 1_735_689_600, "2024 holdout")]), ideas, \
        protocols, loader, now


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "research", "data", "desk_factory"))
    a = ap.parse_args(argv)
    desk, ideas, protocols, loader, now = synthetic()
    rep = nightly(desk, ideas, protocols, now, data_loader=loader)          # night 1: no approver -> nothing approved
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "night1.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, sort_keys=True, indent=1, default=str)
    with open(os.path.join(a.out, "night1.md"), "w", encoding="utf-8") as f:
        f.write(report_md(rep))
    print(report_md(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
