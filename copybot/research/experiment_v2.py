"""Eksperiment smart_v2: forudregistrerede smart-money-hypoteser (HYPOTHESES.md, v2 + ændring).

  python -m research.experiment_v2

Udvikling på stikprøve 1 (train 75 % / validering 25 %); holdout = stikprøve 2 (disjunkt), åbnes én gang.
Wallet-historik kommer kun fra stikprøve 1.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.experiment import EXITS, HIGH_COST, Launch, metrics, pct, quantile  # noqa: E402
from research.simulate import Costs  # noqa: E402
from research.wallets import wallet_features  # noqa: E402

VERSION = "smart_v2"
D = 60


def load(db_path):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    grads = [dict(g) for g in db.execute("SELECT * FROM grads WHERE sampled IN (1,2) AND events_status='ok' ORDER BY grad_ts, grad_slot")]
    ev = {}
    for e in db.execute("SELECT e.* FROM events e JOIN grads g ON g.mint=e.mint WHERE g.sampled IN (1,2)"):
        ev.setdefault(e["mint"], []).append(dict(e))
    snaps = {(s["mint"], s["t"]): (s["res_sol"], s["res_tok"], s["sig"]) for s in db.execute("SELECT * FROM snapshots WHERE status='ok'")}
    db.close()
    return grads, ev, snaps


def run(db_path, out_dir, md_path, log=print):
    grads, ev, snaps = load(db_path)
    L = [Launch(g, ev.get(g["mint"], []), snaps) for g in grads]
    dev = [x for x in L if x.g["sampled"] == 1]
    hold = [x for x in L if x.g["sampled"] == 2]
    n = len(dev)
    train, val = dev[:3 * n // 4], dev[3 * n // 4:]
    outcome = lambda x: x.trade(D, 900).net_return  # H0: køb 62 s, sælg 15 min (forudregistreret)
    wf = wallet_features(L, dev, outcome, D)       # historik KUN fra stikprøve 1 (ændringen)
    fw = lambda x: wf[x.g["mint"]]
    tr_f = [fw(x) for x in train]
    sc75 = quantile([f["smart_count"] for f in tr_f], 0.75)
    ws75 = quantile([f["smart_wscore"] for f in tr_f if f["smart_wscore"] is not None], 0.75)
    bs25 = quantile([f["bad_share"] for f in tr_f], 0.25)
    H = {
        "H4": {"rule": lambda x: fw(x)["smart_count"] >= sc75,  # som forudregistreret (tærskel 0 = alle)
               "desc": f"early buyers med positiv historik >= {sc75}", "thresholds": {"smart_count": sc75}},
        "H5": {"rule": lambda x: fw(x)["smart_wscore"] is not None and fw(x)["smart_wscore"] >= ws75,
               "desc": f"SOL-vægtet historik-score >= {ws75:+.3f}", "thresholds": {"smart_wscore": ws75}},
        "H6": {"rule": lambda x: fw(x)["bad_share"] <= bs25,
               "desc": f"andel køb fra wallets med dårlig historik <= {bs25:.3f}", "thresholds": {"bad_share": bs25}},
    }
    span = lambda s: [time.strftime("%Y-%m-%d %H:%M", time.localtime(s[0].g["grad_ts"])),
                      time.strftime("%Y-%m-%d %H:%M", time.localtime(s[-1].g["grad_ts"]))] if s else None
    cover = lambda part: sum(1 for x in part if fw(x)["known_buyers"] > 0) / max(len(part), 1)
    res = {"version": VERSION, "built": int(time.time()), "n_launches": len(L),
           "splits": {"train": [len(train), span(train)], "validation": [len(val), span(val)], "test": [len(hold), span(hold)]},
           "test_is": "holdout (stikprøve 2, disjunkt)",
           "coverage_known_buyers": {"train": cover(train), "validation": cover(val), "holdout": cover(hold)},
           "assumptions": {"delay_s": 2, "size_sol": 0.25, "costs": Costs().__dict__, "costs_status": "ESTIMERET",
                           "not_modelled": ["andre handler i samme slot før vores", "fejlede transaktioner", "MEV ud over gebyr-estimatet"]},
           "hypotheses": {"H0": {"desc": "alle (reference)", "D": D,
                                 "train_by_exit": {E: metrics([x.trade(D, E) for x in train]) for E in EXITS},
                                 "validation_by_exit": {E: metrics([x.trade(D, E) for x in val]) for E in EXITS},
                                 "test_by_exit": {E: metrics([x.trade(D, E) for x in hold]) for E in EXITS},
                                 "verdict": "REFERENCE"}}}
    for hid, h in H.items():
        sel = lambda part: [x for x in part if h["rule"](x)]
        tr = sel(train)
        by_exit = {E: metrics([x.trade(D, E) for x in tr]) for E in EXITS}
        best = max(EXITS, key=lambda E: by_exit[E].get("mean", -9))
        vm = metrics([x.trade(D, best) for x in sel(val)])
        passed = vm.get("n", 0) > 0 and vm["mean"] > 0 and (vm.get("pf") or 0) > 1
        tm = metrics([x.trade(D, best) for x in sel(hold)])
        if not passed:
            verdict = "REJECTED (validering)"
        elif tm.get("n", 0) and tm["mean"] > 0 and tm["lb_bonferroni3"] > 0:
            verdict = "OUT-OF-SAMPLE VALIDATED"
        elif tm.get("n", 0) and tm["mean"] > 0:
            verdict = "INCONCLUSIVE"
        else:
            verdict = "REJECTED (holdout)"
        oos = sel(val) + sel(hold)
        res["hypotheses"][hid] = {
            "desc": h["desc"], "D": D, "thresholds": h["thresholds"], "train_by_exit": by_exit, "exit": best,
            "selected_frac_train": len(tr) / max(len(train), 1), "validation": vm, "passed_validation": passed,
            "test": tm, "verdict": verdict,
            "sensitivity_oos": {
                "delay": {d: metrics([x.trade(D, best, delay=d) for x in oos]).get("mean") for d in (0, 2, 5, 10)},
                "size": {s: metrics([x.trade(D, best, size=s) for x in oos]).get("mean") for s in (0.1, 0.25, 1.0, 2.0)},
                "high_cost": metrics([x.trade(D, best, costs=HIGH_COST) for x in oos]).get("mean")}}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, VERSION + ".json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    md = report_md(res)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    log(md)
    return res


def report_md(res):
    s, c = res["splits"], res["coverage_known_buyers"]
    out = [f"# Resultater: {res['version']}", "", f"Bygget {time.strftime('%Y-%m-%d %H:%M', time.localtime(res['built']))} "
           f"af `research/experiment_v2.py` ud fra `research/HYPOTHESES.md` (v2 + ændring, forudregistreret).", "",
           f"- Train: {s['train'][0]} ({s['train'][1][0]} → {s['train'][1][1]})",
           f"- Validering: {s['validation'][0]} ({s['validation'][1][0]} → {s['validation'][1][1]})",
           f"- Holdout (disjunkt stikprøve 2): {s['test'][0]} ({s['test'][1][0]} → {s['test'][1][1]})",
           f"- Andel launches med mindst én early buyer med historik: train {c['train'] * 100:.0f} %, "
           f"validering {c['validation'] * 100:.0f} %, holdout {c['holdout'] * 100:.0f} %",
           f"- Antagelser: 0,25 SOL, 2 s forsinkelse, {res['assumptions']['costs']['pool_fee'] * 100:.2f} %/side + "
           f"{res['assumptions']['costs']['tx_sol']} SOL/tx (ESTIMERET).", "",
           "## H0: køb alle (reference)", "", "| Exit | Train | Validering | Holdout | Holdout median |", "|---|---|---|---|---|"]
    h0 = res["hypotheses"]["H0"]
    for E in EXITS:
        out.append(f"| {E // 60} min | {pct(h0['train_by_exit'][E].get('mean'))} | {pct(h0['validation_by_exit'][E].get('mean'))} | "
                   f"{pct(h0['test_by_exit'][E].get('mean'))} | {pct(h0['test_by_exit'][E].get('median'))} |")
    out += ["", "## Hypoteser", "", "| ID | Regel | Exit | Train | Validering | Valid. PF | Holdout n | Holdout gns. | Median | Uden top 3 | 95 % CI | Dom |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for hid in ("H4", "H5", "H6"):
        h = res["hypotheses"][hid]
        tr, va, te = h["train_by_exit"][h["exit"]], h["validation"], h["test"]
        ci = te.get("ci95")
        out.append(f"| {hid} | {h['desc']} | {h['exit'] // 60} min | {pct(tr.get('mean'))} (n={tr.get('n')}) | {pct(va.get('mean'))} (n={va.get('n')}) | "
                   f"{va.get('pf') and round(va['pf'], 2)} | {te.get('n')} | {pct(te.get('mean'))} | {pct(te.get('median'))} | {pct(te.get('mean_ex_top3'))} | "
                   f"{('[' + pct(ci[0]) + ', ' + pct(ci[1]) + ']') if ci else '–'} | **{h['verdict']}** |")
    out += ["", "## Følsomhed (validering + holdout)", "", "| ID | Forsinkelse 0/2/5/10 s | Størrelse 0,1/0,25/1/2 SOL | Høje omkostninger |", "|---|---|---|---|"]
    for hid in ("H4", "H5", "H6"):
        sn = res["hypotheses"][hid]["sensitivity_oos"]
        out.append(f"| {hid} | {' / '.join(pct(v) for v in sn['delay'].values())} | {' / '.join(pct(v) for v in sn['size'].values())} | {pct(sn['high_cost'])} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    run(os.path.join(HERE, "data", "research", "launches.db"), os.path.join(HERE, "data", "research", "results"),
        os.path.join(HERE, "research", "RESULTS_" + VERSION + ".md"))
