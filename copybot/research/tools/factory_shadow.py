"""Director order 47 P3: synthetic shadow run of the research factory (research/reviews/INBOX.md).

Three parts, all read-only and without protected market data:

A. **Pipeline shadow.** Every recorded lab transition (lab.db, read-only) is replayed against the factory's rules and
   gets ALLOW or BLOCK with a reason class. The lab performed all of them, so every BLOCK is a decision difference;
   each must fall in a documented class (explained) or it is reported as UNEXPLAINED. Nothing is rewritten.
B. **Adversarial suite.** Scripted cases with an expected outcome: non-human and delegated approvals, incomplete
   pre-registration, 2024 holdout, COIN-M before 2026-11-28, survivorship (universe fixed after the window start),
   changed data or pre-registration after the lock, missing or stale ledger charge, double charge of an identical
   re-run, refunds, retest of a final status, promotion to paper, a broken ledger, unknown ids, the P2 control cases
   F1 (INSUFFICIENT_POWER), F2 (CONDITIONAL), F3 (DEFERRED + date gate) and one legitimate path (false-block check).
   Unauthorized ALLOW (expected BLOCK, got ALLOW) and false BLOCK (expected ALLOW, got BLOCK) are counted separately.
C. **Factory at scale.** Synthetic worlds with ~1,000 strongly correlated null candidates (momentum lookback 2-200 x
   skip 0-5) plus six real-signal variants and one hidden look-ahead variant. Every candidate goes PROPOSED -> blocked
   test without approval -> human approval -> freeze -> ledger charge -> test -> verdict (Holm). Reports false
   selections, true findings, the leak, a survivorship bias measurement and full traceability (ledger entries per
   tested candidate; identical re-runs charge nothing).

    python3 research/tools/factory_shadow.py [--db PATH] [--worlds N] [--procs K]   # -> research/data/factory_shadow/
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import random
import sqlite3
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import factory as fa  # noqa: E402
from research.tools import hypo_engine as he  # noqa: E402

OUT = os.path.join(HERE, "research", "data", "factory_shadow")
NOW = 1_794_000_000                    # 2026-11-06 ~ (inside the order's period; before 2026-11-28)
LATER = fa.COINM_FROM + 86_400
SAFE_DS = [{"path": "syn.zip", "sha256": "ab" * 32, "window_start": 1_640_995_200, "window_end": 1_703_980_800,
            "source": "usdm"}]         # 2022-01-01 .. 2023-12-31 (train3 + validation3), never the 2024 holdout


def prereg(**kw):
    r = {"family": "SYN", "mechanism": "synthetic", "mechanism_tag": "cross_sectional_momentum", "direction": 1,
         "universe": ["S0", "S1"], "windows": {"eval": "2022-2023"}, "sources": ["synthetic"], "datasets": SAFE_DS,
         "parameter_family": {"L": [1]}, "estimand": "net mean daily", "benchmark": "zero", "cost_model": "5 bp",
         "rejection": "net <= 0 or Holm p > 0.05", "spec_commit": "c" * 40, "universe_asof": 1_640_995_200}
    r.update(kw)
    return r


OWNER = {"actor": "human:owner", "reason": "owner approves in person"}


# ---------------------------------------------------------------- A. pipeline shadow

CLASSES = {
    "propose": "factory equivalent: PROPOSED",
    "no-op": "SUPPRESSED <-> DISCOVERED are both PROPOSED in the factory",
    "legacy": "legacy import: record only, counted as 1 attempt (lower bound), never re-tested",
    "delegated-approval": "template approval recorded as human:anton but reason says Claude approved on the owner's "
                          "behalf; the factory requires the owner's own approval",
    "instruction-cited-approval": "template approval recorded as human:anton whose reason cites a general owner "
                                  "instruction ('User instruction ...'); executed by the assistant, not the owner's "
                                  "own approval",
    "approval-link-missing": "registration without a template, family or human approval link",
    "hash-at-access": "lab hashes datasets when it reads them (after SCREENING starts); the factory requires hashes "
                      "at the freeze, before any data access",
    "universe-asof-unrecorded": "lab specs do not record a point-in-time universe date; survivorship cannot be ruled "
                                "out by the record",
    "prereg-field-missing": "a factory pre-registration field has no lab equivalent in the spec",
    "no-charge": "verdict without trials or alpha rows (no ledger charge)",
    "human-verdict": "a human verdict after a screen pass",
}
FIELD_MAP = {"family": ("template", "family"), "mechanism": ("mechanism",), "direction": ("hypothesis",),
             "universe": ("universe",), "windows": ("datasets",), "sources": ("sources",), "datasets": ("datasets",),
             "parameter_family": ("grid",), "estimand": ("acceptance", "methodology"), "benchmark": ("baseline",),
             "cost_model": ("costs",), "rejection": ("rejection",)}


def pipeline_shadow(con):
    rows = con.execute("SELECT id, exp_id, ts, from_state, to_state, actor, reason, evidence FROM transitions "
                       "ORDER BY id").fetchall()
    specs = {e: (json.loads(sj or "{}"), sc) for e, sj, sc in con.execute(
        "SELECT exp_id, spec_json, spec_commit FROM experiments e WHERE version=(SELECT MAX(version) FROM experiments "
        "WHERE exp_id=e.exp_id)")}
    approvals = {}
    for eid, payload, actor in con.execute("SELECT id, payload, actor FROM events WHERE kind IN "
                                           "('template.approved', 'family.approved')"):
        approvals[eid] = (actor, json.loads(payload or "{}").get("reason", ""))
    ds_first = dict(con.execute("SELECT exp_id, MIN(ts) FROM datasets GROUP BY exp_id").fetchall())
    charged = {e for (e,) in con.execute("SELECT DISTINCT exp_id FROM trials")} | \
              {e for (e,) in con.execute("SELECT DISTINCT exp_id FROM alpha_ledger WHERE alpha > 0")}
    out = []
    for tid, exp, ts, frm, to, actor, reason, evidence in rows:
        actor = actor or ""
        dec, cls = "ALLOW", []
        if frm is None and actor == "legacy-import":
            cls = ["legacy"]
        elif frm is None:
            cls = ["propose"]
        elif {frm, to} == {"DISCOVERED", "SUPPRESSED"}:
            cls = ["no-op"]
        elif (frm, to) == ("DISCOVERED", "REGISTERED"):
            ev = json.loads(evidence or "{}")
            ap = approvals.get(ev.get("template_approval_event") or ev.get("family_approval_event"))
            if ap is None and not actor.startswith("human:"):
                dec, cls = "BLOCK", ["approval-link-missing"]
            elif ap is not None and fa.delegated({"reason": ap[1]}):
                dec = "BLOCK"
                cls = ["delegated-approval"] if "claude" in ap[1].lower() else ["instruction-cited-approval"]
        elif (frm, to) == ("REGISTERED", "SCREENING"):
            spec, commit = specs.get(exp, ({}, None))
            missing = [k for k, src in FIELD_MAP.items() if not any(spec.get(x) for x in src)]
            if not commit:
                missing.append("spec_commit")
            if missing:
                dec, cls = "BLOCK", ["prereg-field-missing"]
            first = ds_first.get(exp)
            if first is None or first >= ts:
                dec = "BLOCK"
                cls.append("hash-at-access")
            if not spec.get("universe_asof"):
                dec = "BLOCK"
                cls.append("universe-asof-unrecorded")
        elif frm == "SCREENING":
            if exp not in charged:
                dec, cls = "BLOCK", ["no-charge"]
        elif (frm, to) == ("SCREEN_PASSED", "REJECTED") and actor.startswith("human:"):
            cls = ["human-verdict"]
        else:
            dec, cls = "BLOCK", ["UNEXPLAINED"]
        out.append({"id": tid, "exp_id": exp, "from": frm, "to": to, "lab": "ALLOW", "factory": dec, "classes": cls})
    summary = {}
    for o in out:
        for c in o["classes"] or ["-"]:
            k = f"{o['factory']}:{c}"
            summary[k] = summary.get(k, 0) + 1
    unexplained = [o for o in out if "UNEXPLAINED" in o["classes"]]
    return {"transitions": len(out), "summary": dict(sorted(summary.items())), "unexplained": unexplained,
            "classes": CLASSES, "rows": out}


# ---------------------------------------------------------------- B. adversarial suite

def fresh(lmap=None):
    led = fa.Ledger()
    return led, fa.Register(led, lmap or {})


def at_frozen(reg, hid, ts=NOW, **kw):
    reg.propose(hid, prereg(estimand=f"e-{hid}", **kw), ts)
    reg.move(hid, "APPROVED", ts + 1, OWNER)
    reg.move(hid, "FROZEN", ts + 2)


def suite():
    cases = []

    def case(name, expect, fn):
        try:
            got, why = fn()
        except Exception as e:                 # noqa: BLE001 - a crash in a case is a BLOCK (fail-closed)
            got, why = "BLOCK", [f"exception: {e}"]
        cases.append({"case": name, "expect": expect, "got": got, "why": why,
                      "unauthorized_allow": expect == "BLOCK" and got == "ALLOW",
                      "false_block": expect == "ALLOW" and got == "BLOCK"})

    def approve_with(ev):
        _, reg = fresh()
        reg.propose("H", prereg(), NOW)
        return reg.gate("H", "APPROVED", NOW + 1, ev)

    case("approve: system actor", "BLOCK", lambda: approve_with({"actor": "system"}))
    case("approve: claude actor", "BLOCK", lambda: approve_with({"actor": "claude"}))
    case("approve: chatgpt actor", "BLOCK", lambda: approve_with({"actor": "chatgpt:director"}))
    case("approve: human label, reason says Claude on behalf", "BLOCK", lambda: approve_with(
        {"actor": "human:anton", "reason": "Approved by Claude (AI assistant) on behalf of the user"}))
    case("approve: owner in person", "ALLOW", lambda: approve_with(OWNER))

    def freeze_with(**kw):
        _, reg = fresh()
        reg.propose("H", prereg(**kw), NOW)
        reg.move("H", "APPROVED", NOW + 1, OWNER)
        return reg.gate("H", "FROZEN", kw.pop("_ts", NOW + 2))

    case("freeze: estimand missing", "BLOCK", lambda: freeze_with(estimand=""))
    case("freeze: dataset without sha256", "BLOCK", lambda: freeze_with(datasets=[{**SAFE_DS[0], "sha256": ""}]))
    case("freeze: 2024 holdout", "BLOCK", lambda: freeze_with(
        datasets=[{**SAFE_DS[0], "window_start": 1_704_067_200, "window_end": 1_706_745_600}]))
    case("freeze: COIN-M before 2026-11-28", "BLOCK", lambda: freeze_with(
        datasets=[{**SAFE_DS[0], "source": "binance COIN-M"}]))

    def coinm_after():
        _, reg = fresh()
        reg.propose("H", prereg(datasets=[{**SAFE_DS[0], "source": "binance COIN-M"}]), LATER)
        reg.move("H", "APPROVED", LATER + 1, OWNER)
        return reg.gate("H", "FROZEN", LATER + 2)
    case("freeze: COIN-M after 2026-11-28", "ALLOW", coinm_after)
    case("freeze: survivor universe (fixed at window end)", "BLOCK",
         lambda: freeze_with(universe_asof=SAFE_DS[0]["window_end"]))
    case("freeze: universe date not recorded", "BLOCK", lambda: freeze_with(universe_asof=None))
    case("freeze: point-in-time universe", "ALLOW", lambda: freeze_with())

    def test_with(charge="after", ds=None, edit=None):
        led, reg = fresh()
        at_frozen(reg, "H")
        if charge == "before":
            led.charge("H", "L", NOW + 1, 1, 0.01, "syn")
        elif charge == "after":
            led.charge("H", "L", NOW + 3, 1, 0.01, "syn", key="k1")
        if edit:
            reg.recs["H"].update(edit)
        return reg.gate("H", "TESTED", NOW + 4, {"datasets": ds} if ds else None)

    case("test: no ledger charge", "BLOCK", lambda: test_with(charge=None))
    case("test: charge made before the freeze", "BLOCK", lambda: test_with(charge="before"))
    case("test: data changed after lock", "BLOCK", lambda: test_with(ds=[{**SAFE_DS[0], "sha256": "cd" * 32}]))
    case("test: pre-registration changed after lock", "BLOCK", lambda: test_with(edit={"estimand": "nicer"}))
    case("test: legitimate", "ALLOW", lambda: test_with())

    def double_charge():
        led, reg = fresh()
        at_frozen(reg, "H")
        led.charge("H", "L", NOW + 3, 1, 0.01, "syn", key="same-attempt")
        led.charge("H", "L", NOW + 3, 1, 0.01, "syn", key="same-attempt")
        n = len(led.entries)
        return ("ALLOW", []) if n == 1 else ("BLOCK", [f"{n} entries for one attempt"])
    case("identical re-run charges once", "ALLOW", double_charge)

    def refund():
        led, _ = fresh()
        led.charge("H", "L", NOW, 1, -0.01, "syn")
        return "ALLOW", []
    case("refund alpha", "BLOCK", refund)

    def retest_final():
        led, reg = fresh()
        at_frozen(reg, "H")
        led.charge("H", "L", NOW + 3, 1, 0.01, "syn", key="a1")
        reg.move("H", "TESTED", NOW + 4)
        reg.move("H", "REJECTED", NOW + 5)
        led.charge("H", "L", NOW + 6, 1, 0.01, "syn", key="a2")
        return reg.gate("H", "TESTED", NOW + 7)
    case("retest a REJECTED hypothesis", "BLOCK", retest_final)

    def promote():
        led, reg = fresh()
        at_frozen(reg, "H")
        led.charge("H", "L", NOW + 3, 1, 0.01, "syn", key="a1")
        reg.move("H", "TESTED", NOW + 4)
        return reg.gate("H", "VALIDATED", NOW + 5, {"promote_to_paper": True})
    case("promote to paper trading", "BLOCK", promote)

    def broken_ledger():
        led, reg = fresh()
        at_frozen(reg, "H")
        led.charge("H", "L", NOW + 3, 1, 0.01, "syn", key="a1")
        led.entries[0]["alpha"] = 0.0
        return reg.gate("H", "TESTED", NOW + 4)
    case("broken ledger (fail-closed)", "BLOCK", broken_ledger)
    case("unknown hypothesis id (fail-closed)", "BLOCK", lambda: fresh()[1].gate("nope", "APPROVED", NOW, OWNER))

    def rollback():
        led, reg = fresh()
        at_frozen(reg, "H")
        before = copy.deepcopy(reg.recs["H"])
        try:
            reg.move("H", "TESTED", NOW + 4)          # no charge -> refused
        except fa.FactoryError:
            pass
        same = reg.recs["H"] == before and len(reg.log) == 2
        return ("ALLOW", []) if same else ("BLOCK", ["record changed by a refused move"])
    case("refused move leaves the record unchanged (rollback)", "ALLOW", rollback)

    def control(assessment, earliest=None, ts=NOW, step="APPROVED"):
        led, reg = fresh()
        reg.propose("F", prereg(assessment=assessment, earliest_data_ts=earliest), ts)
        if step == "APPROVED":
            return reg.gate("F", "APPROVED", ts + 1, OWNER)
        reg.recs["F"]["assessment"] = None
        reg.move("F", "APPROVED", ts + 1, OWNER)
        reg.recs["F"]["assessment"] = assessment
        return reg.gate("F", step, ts + 2)
    case("F1 control: INSUFFICIENT_POWER despite synthetic profit", "BLOCK",
         lambda: control("INSUFFICIENT_POWER"))
    case("F2 control: CONDITIONAL", "BLOCK", lambda: control("CONDITIONAL"))
    case("F3 control: DEFERRED", "BLOCK", lambda: control("DEFERRED", fa.COINM_FROM))
    case("F3 date gate alone, before 2026-11-28", "BLOCK", lambda: control(None, fa.COINM_FROM, NOW, "FROZEN"))
    case("F3 date gate alone, after 2026-11-28", "ALLOW", lambda: control(None, fa.COINM_FROM, LATER, "FROZEN"))
    return cases


# ---------------------------------------------------------------- C. factory at scale

def big_grid():
    g = [("momk", (lb, sk)) for lb in range(2, 201) for sk in (0, 1, 2, 3, 5)]
    g += [("char", L) for L in range(1, 7)]
    g += [("momk", (20, -1))]                       # hidden look-ahead: includes the traded day's own return
    return g


def fast_leak(cands, w, seed, samples=3):
    """Exact truncation test with the truncated worlds built once per world."""
    rng = random.Random(seed)
    T = len(w["r"][0])
    pre = he.prefix(w["r"])
    tw = []
    for _ in range(samples):
        t = rng.randrange(230, T - 1)
        r2 = [row[:t] + [rng.gauss(0, 0.03) for _ in range(T - t)] for row in w["r"]]
        tw.append((t, {**w, "r": r2}, he.prefix(r2)))
    out = []
    for fam, L in cands:
        leak = False
        for t, w2, pre2 in tw:
            if any(he.signal(fam, L, w, pre, i, t) != he.signal(fam, L, w2, pre2, i, t) for i in range(len(w["r"]))):
                leak = True
                break
        out.append(leak)
    return out


def survivorship_bias(w, drop=0.25, start=230):
    """Equal-weight daily mean of all assets vs only the assets that 'survived' (top 75 % by full-window return,
    a universe chosen with end-of-window knowledge)."""
    r = w["r"]
    tot = sorted(((sum(v or 0.0 for v in row[start:]), i) for i, row in enumerate(r)), reverse=True)
    keep = {i for _, i in tot[:int(len(r) * (1 - drop))]}

    def ew(ids):
        days = []
        for t in range(start, len(r[0])):
            xs = [r[i][t] for i in ids if r[i][t] is not None]
            days.append(sum(xs) / len(xs) if xs else 0.0)
        return sum(days) / len(days)
    return ew(range(len(r))), ew(keep)


def scale_world(args):
    idx, signal_ic, n, T = args
    seed = int(hashlib.sha256(f"p3|{idx}|{signal_ic}".encode()).hexdigest()[:12], 16)
    w = he.world(seed, n=n, T=T, ic=signal_ic)
    cands = big_grid()
    leaks = fast_leak(cands, w, seed)
    pre = he.prefix(w["r"])
    rows, nets = [], []
    for (fam, L), leak in zip(cands, leaks):
        gross, net = he.portfolio(fam, L, w, pre, 205, 0.0005)
        tn, mn = he.hac_t(net)
        rows.append({"fam": fam, "L": L, "leak": leak, "net_mean": mn, "p": he.p_one(tn)})
    holm = he.holm([x["p"] for x in rows])
    for x, h in zip(rows, holm):
        x["holm"] = h and not x["leak"] and x["net_mean"] > 0
        x["raw"] = x["p"] <= 0.05 and not x["leak"] and x["net_mean"] > 0
    allb, surv = survivorship_bias(w)

    # the factory path for every candidate
    led, reg = fresh()
    blocked_without_approval = 0
    tested = 0
    for j, (fam, L) in enumerate(cands):
        hid = f"W{idx}_{fam}_{L}"
        reg.propose(hid, prereg(estimand=f"{fam}:{L}"), NOW)
        if reg.gate(hid, "TESTED", NOW + 1)[0] == "BLOCK":
            blocked_without_approval += 1
        reg.move(hid, "APPROVED", NOW + 1, OWNER)
        reg.move(hid, "FROZEN", NOW + 2)
        key = fa.sha([hid, reg.recs[hid]["frozen"], "code-v1"])
        led.charge(hid, "syn", NOW + 3, 1, 0.05 / len(cands), "shadow", key=key)
        led.charge(hid, "syn", NOW + 3, 1, 0.05 / len(cands), "shadow", key=key)     # identical re-run
        reg.move(hid, "TESTED", NOW + 4)
        tested += 1
        verdict = "VALIDATED" if rows[j]["holm"] else ("REJECTED" if rows[j]["net_mean"] <= 0 or rows[j]["leak"]
                                                        else "INCONCLUSIVE")
        reg.move(hid, verdict, NOW + 5)
    led.verify()
    per_hid = {}
    for e in led.entries:
        per_hid[e["hid"]] = per_hid.get(e["hid"], 0) + 1
    return {"world": idx, "ic": signal_ic, "candidates": len(cands),
            "raw_selected_null": sum(x["raw"] for x in rows if x["fam"] != "char"),
            "holm_selected_null": sum(x["holm"] for x in rows if x["fam"] != "char"),
            "holm_selected_true": sum(x["holm"] for x in rows if x["fam"] == "char"),
            "leak_caught": rows[-1]["leak"], "leak_false_alarms": sum(x["leak"] for x in rows[:-1]),
            "blocked_without_approval": blocked_without_approval, "tested": tested,
            "ledger_entries": len(led.entries), "max_entries_per_candidate": max(per_hid.values()),
            "alpha_charged": round(sum(e["alpha"] for e in led.entries), 10),
            "survivorship_ew_all": allb, "survivorship_ew_survivors": surv,
            "n_eff": he.effective_trials([he.portfolio(f, L, w, pre, 205, 0.0005)[1]
                                          for f, L in cands[::25]])}


def build(con, worlds=5, n=24, T=500, procs=4):
    jobs = [(i, 0.0, n, T) for i in range(worlds)] + [(i, 0.03, n, T) for i in range(worlds)]
    if procs > 1:
        with Pool(procs) as pool:
            scale = pool.map(scale_world, jobs)
    else:
        scale = [scale_world(j) for j in jobs]
    cases = suite()
    return {"schema": "copybot.factory_shadow/1", "rule": "research/reviews/INBOX.md director order 47 P3",
            "pipeline": pipeline_shadow(con) if con is not None else None,
            "suite": {"cases": cases, "unauthorized_allow": sum(c["unauthorized_allow"] for c in cases),
                      "false_block": sum(c["false_block"] for c in cases)},
            "scale": scale}


def md(rep, digest):
    L = ["# Factory shadow run P3 (synthetic + read-only pipeline replay)", "",
         f"`research/tools/factory_shadow.py`; data `research/data/factory_shadow/report.json` (sha256 `{digest}`).", ""]
    p = rep["pipeline"]
    if p:
        L += [f"## A. Pipeline shadow: {p['transitions']} lab transitions replayed", "",
              "| Factory decision : class | Count |", "|---|---|"]
        L += [f"| {k} | {v} |" for k, v in p["summary"].items()]
        L += ["", f"Unexplained differences: {len(p['unexplained'])}.", ""]
    s = rep["suite"]
    L += ["## B. Adversarial suite", "",
          f"Unauthorized ALLOW: **{s['unauthorized_allow']}**. False BLOCK: **{s['false_block']}**.", "",
          "| Case | Expected | Got | Reason |", "|---|---|---|---|"]
    for c in s["cases"]:
        L.append(f"| {c['case']} | {c['expect']} | {c['got']} | {'; '.join(c['why'])[:110]} |")
    L += ["", "## C. Factory at scale", "",
          "| World | ic | Candidates | Raw null hits | Holm null hits | Holm true hits (of 6) | Leak caught | Leak false "
          "alarms | Test blocked w/o approval | Ledger entries / tested | Max entries per candidate | Alpha charged | "
          "EW all vs survivors (bp/day) | N_eff (1 in 25) |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for w in rep["scale"]:
        L.append(f"| {w['world']} | {w['ic']} | {w['candidates']} | {w['raw_selected_null']} | "
                 f"{w['holm_selected_null']} | {w['holm_selected_true']} | {w['leak_caught']} | "
                 f"{w['leak_false_alarms']} | {w['blocked_without_approval']} | {w['ledger_entries']} / {w['tested']} | "
                 f"{w['max_entries_per_candidate']} | {w['alpha_charged']:.4f} | "
                 f"{w['survivorship_ew_all'] * 1e4:.1f} vs {w['survivorship_ew_survivors'] * 1e4:.1f} | "
                 f"{w['n_eff']:.1f} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "lab", "lab.db"))
    ap.add_argument("--worlds", type=int, default=5)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rep = build(con, worlds=a.worlds, procs=a.procs)
    os.makedirs(a.out, exist_ok=True)
    body = json.dumps(rep, sort_keys=True, indent=1) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as f:
        f.write(body)
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(md(rep, digest))
    print(digest)
    print(md(rep, digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
