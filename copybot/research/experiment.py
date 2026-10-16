"""Eksperiment launch_v1: kører de forudregistrerede hypoteser i HYPOTHESES.md på launch-datasættet.

  python -m research.experiment            (skriver data/research/results/launch_v1.json og research/RESULTS_launch_v1.md)

Rækkefølgen følger forudregistreringen: tærskler og exit vælges på train, validering afgør hvem der går videre,
og testperioden bruges først derefter og kun én gang.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import statistics
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.features import features  # noqa: E402
from research.simulate import Costs, PoolHistory, simulate  # noqa: E402

VERSION = "launch_v1"
EXITS = (300, 900, 1800, 3600)
DELAY, SIZE = 2, 0.25
HIGH_COST = Costs(pool_fee=0.005, tx_sol=0.002)


def quantile(xs, q):
    s = sorted(xs)
    return s[min(int(q * len(s)), len(s) - 1)] if s else None


def metrics(trades, seed=7):
    """Nøgletal for en liste af handler (i tidsorden). net_return er pr. handel i SOL."""
    ok = [t for t in trades if t.status == "ok"]
    r = [t.net_return for t in ok]
    out = {"n": len(r), "n_missing_exit": len(trades) - len(ok)}
    if not r:
        return out
    wins, losses = [x for x in r if x > 0], [x for x in r if x <= 0]
    eq = peak = dd = 0.0
    for x in r:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    rng = random.Random(seed)
    boots = sorted(statistics.mean(rng.choices(r, k=len(r))) for _ in range(4000))
    srt = sorted(r)
    out.update({
        "mean": statistics.mean(r), "median": statistics.median(r),
        "win_rate": len(wins) / len(r), "avg_win": statistics.mean(wins) if wins else 0.0,
        "avg_loss": statistics.mean(losses) if losses else 0.0,
        "pf": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else None,
        "max_dd_positions": dd, "mean_ex_top3": statistics.mean(srt[:-3]) if len(srt) > 3 else None,
        "worst": srt[0], "best": srt[-1],
        "ci95": [boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]],
        "lb_bonferroni3": boots[int(0.0167 * len(boots))],
        "pessimistic_mean": statistics.mean(r + [-1.0] * out["n_missing_exit"]),
    })
    return out


def load(db_path):
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    grads = [dict(g) for g in db.execute("SELECT * FROM grads WHERE sampled=1 AND events_status='ok' ORDER BY grad_ts, grad_slot")]
    ev = {}
    for e in db.execute("SELECT * FROM events"):
        ev.setdefault(e["mint"], []).append(dict(e))
    snaps = {}
    for s in db.execute("SELECT * FROM snapshots WHERE status='ok'"):
        snaps[(s["mint"], s["t"])] = (s["res_sol"], s["res_tok"], s["sig"])
    db.close()
    return grads, ev, snaps


class Launch:
    def __init__(self, g, events, snaps):
        self.g, self.events, self.snaps = g, events, snaps
        self.hist = PoolHistory(g["sol0"], g["tok0"], g["grad_ts"], events)
        self._f = {}

    def f(self, D):
        if D not in self._f:
            self._f[D] = features(self.g, self.events, D)
        return self._f[D]

    def trade(self, D, H, delay=DELAY, size=SIZE, costs=Costs()):
        t_exit = self.g["grad_ts"] + H
        return simulate(self.g["mint"], self.hist, self.g["grad_ts"] + D + delay,
                        self.snaps.get((self.g["mint"], t_exit)), t_exit, size, costs)


def hypotheses(train):
    """Tærskler fittet på train (kun på træk ved beslutningstidspunktet, aldrig på afkast)."""
    f60 = [x.f(60) for x in train]
    f120 = [x.f(120) for x in train]
    ub75 = quantile([f["uniq_buyers"] for f in f60], 0.75)
    t3_50 = quantile([f["top3_share"] for f in f60], 0.50)
    pm25 = quantile([f["price_mult"] for f in f120], 0.25)
    return {
        "H0": {"D": 60, "rule": lambda x: True, "desc": "alle graduations"},
        "H1": {"D": 60, "rule": lambda x: (x.f(60)["uniq_buyers"] >= ub75 and x.f(60)["top3_share"] <= t3_50 and x.f(60)["net_sol"] > 0),
               "desc": f"unikke købere >= {ub75}, top-3 andel <= {t3_50:.2f}, netto SOL > 0", "thresholds": {"uniq_buyers": ub75, "top3_share": t3_50}},
        "H2": {"D": 120, "rule": lambda x: x.f(120)["price_mult"] <= pm25 and x.f(120)["net_sol_30s"] > 0,
               "desc": f"prisgang siden graduation <= {pm25:.3f}, netto SOL sidste 30 s > 0", "thresholds": {"price_mult": pm25}},
        "H3": {"D": 60, "rule": lambda x: x.f(60)["max_holder_share"] < 0.25, "desc": "største holder < 25 % af poolens start-tokens"},
    }


def run(db_path, out_dir, md_path, log=print):
    grads, ev, snaps = load(db_path)
    L = [Launch(g, ev.get(g["mint"], []), snaps) for g in grads]
    n = len(L)
    train, val, test = L[:n // 2], L[n // 2:3 * n // 4], L[3 * n // 4:]
    span = lambda s: [time.strftime("%Y-%m-%d %H:%M", time.localtime(s[0].g["grad_ts"])),
                      time.strftime("%Y-%m-%d %H:%M", time.localtime(s[-1].g["grad_ts"]))] if s else None
    H = hypotheses(train)
    res = {"version": VERSION, "built": int(time.time()), "n_launches": n,
           "splits": {"train": [len(train), span(train)], "validation": [len(val), span(val)], "test": [len(test), span(test)]},
           "assumptions": {"delay_s": DELAY, "size_sol": SIZE, "costs": Costs().__dict__, "costs_status": "ESTIMERET",
                           "not_modelled": ["andre handler i samme slot før vores", "fejlede transaktioner", "MEV ud over gebyr-estimatet"]},
           "hypotheses": {}}
    for hid, h in H.items():
        sel = lambda part: [x for x in part if h["rule"](x)]
        tr = sel(train)
        by_exit = {E: metrics([x.trade(h["D"], E) for x in tr]) for E in EXITS}
        r = {"desc": h["desc"], "D": h["D"], "thresholds": h.get("thresholds"), "train_by_exit": by_exit,
             "selected_frac_train": len(tr) / max(len(train), 1)}
        if hid == "H0":
            r["validation_by_exit"] = {E: metrics([x.trade(60, E) for x in val]) for E in EXITS}
            r["test_by_exit"] = {E: metrics([x.trade(60, E) for x in test]) for E in EXITS}
            r["verdict"] = "REFERENCE"
            res["hypotheses"][hid] = r
            continue
        best = max(EXITS, key=lambda E: by_exit[E].get("mean", -9))
        r["exit"] = best
        vm = metrics([x.trade(h["D"], best) for x in sel(val)])
        r["validation"] = vm
        passed = vm.get("n", 0) > 0 and vm["mean"] > 0 and (vm.get("pf") or 0) > 1
        r["passed_validation"] = passed
        tm = metrics([x.trade(h["D"], best) for x in sel(test)])
        r["test"] = tm  # åbnes kun én gang; rapporteres også for dem, der ikke bestod validering
        if not passed:
            r["verdict"] = "REJECTED (validering)"
        elif tm.get("n", 0) and tm["mean"] > 0 and tm["lb_bonferroni3"] > 0:
            r["verdict"] = "OUT-OF-SAMPLE VALIDATED"
        elif tm.get("n", 0) and tm["mean"] > 0:
            r["verdict"] = "INCONCLUSIVE"
        else:
            r["verdict"] = "REJECTED (test)"
        # følsomhed på test (hele perioden efter train: validering + test)
        oos = sel(val) + sel(test)
        r["sensitivity_oos"] = {
            "delay": {d: metrics([x.trade(h["D"], best, delay=d) for x in oos]).get("mean") for d in (0, 2, 5, 10)},
            "size": {s: metrics([x.trade(h["D"], best, size=s) for x in oos]).get("mean") for s in (0.1, 0.25, 1.0, 2.0)},
            "high_cost": metrics([x.trade(h["D"], best, costs=HIGH_COST) for x in oos]).get("mean"),
        }
        res["hypotheses"][hid] = r
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, VERSION + ".json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_md(res))
    log(report_md(res))
    return res


def pct(x):
    return "–" if x is None else f"{x * 100:+.1f} %"


def report_md(res):
    s = res["splits"]
    out = [f"# Resultater: {res['version']}", "",
           f"Bygget {time.strftime('%Y-%m-%d %H:%M', time.localtime(res['built']))} af `research/experiment.py` ud fra "
           f"`research/HYPOTHESES.md` (forudregistreret). {res['n_launches']} graduations.", "",
           f"- Train: {s['train'][0]} ({s['train'][1][0]} → {s['train'][1][1]})" if s["train"][1] else "",
           f"- Validering: {s['validation'][0]} ({s['validation'][1][0]} → {s['validation'][1][1]})" if s["validation"][1] else "",
           f"- Test: {s['test'][0]} ({s['test'][1][0]} → {s['test'][1][1]})" if s["test"][1] else "",
           f"- Antagelser: {res['assumptions']['size_sol']} SOL pr. handel, {res['assumptions']['delay_s']} s forsinkelse, "
           f"gebyr {res['assumptions']['costs']['pool_fee'] * 100:.2f} %/side + {res['assumptions']['costs']['tx_sol']} SOL/tx "
           f"({res['assumptions']['costs_status']}). Ikke modelleret: " + "; ".join(res["assumptions"]["not_modelled"]) + ".", ""]
    h0 = res["hypotheses"]["H0"]
    out += ["## H0: køb alle graduations (reference)", "", "| Exit | Train gns. | Validering gns. | Test gns. | Test median | Test n |",
            "|---|---|---|---|---|---|"]
    for E in EXITS:
        tr, va, te = h0["train_by_exit"][E], h0["validation_by_exit"][E], h0["test_by_exit"][E]
        out.append(f"| {E // 60} min | {pct(tr.get('mean'))} | {pct(va.get('mean'))} | {pct(te.get('mean'))} | {pct(te.get('median'))} | {te.get('n')} |")
    out += ["", "## Hypoteser", "", "| ID | Regel | Exit | Train gns. | Valid. gns. | Valid. PF | Test n | Test gns. | Test median | Uden top 3 | 95 % CI | Dom |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for hid in ("H1", "H2", "H3"):
        h = res["hypotheses"][hid]
        tr = h["train_by_exit"][h["exit"]]
        va, te = h["validation"], h["test"]
        ci = te.get("ci95")
        out.append(f"| {hid} | {h['desc']} | {h['exit'] // 60} min | {pct(tr.get('mean'))} (n={tr.get('n')}) | {pct(va.get('mean'))} (n={va.get('n')}) | "
                   f"{va.get('pf') and round(va['pf'], 2)} | {te.get('n')} | {pct(te.get('mean'))} | {pct(te.get('median'))} | "
                   f"{pct(te.get('mean_ex_top3'))} | {('[' + pct(ci[0]) + ', ' + pct(ci[1]) + ']') if ci else '–'} | **{h['verdict']}** |")
    out += ["", "## Følsomhed (validering + test samlet)", "", "| ID | Forsinkelse 0/2/5/10 s | Størrelse 0,1/0,25/1/2 SOL | Høje omkostninger |", "|---|---|---|---|"]
    for hid in ("H1", "H2", "H3"):
        sn = res["hypotheses"][hid]["sensitivity_oos"]
        out.append(f"| {hid} | {' / '.join(pct(v) for v in sn['delay'].values())} | {' / '.join(pct(v) for v in sn['size'].values())} | {pct(sn['high_cost'])} |")
    out += ["", "Dom-kategorier: REFERENCE, REJECTED (validering/test), INCONCLUSIVE (positiv men usikker), "
            "OUT-OF-SAMPLE VALIDATED (positiv og nedre grænse > 0 efter Bonferroni for 3 hypoteser). "
            "Ingen af dem er LIVE-PAPER VALIDATED, før en live paper-test har bekræftet dem.", ""]
    return "\n".join(x for x in out if x is not None)


if __name__ == "__main__":
    run(os.path.join(HERE, "data", "research", "launches.db"), os.path.join(HERE, "data", "research", "results"),
        os.path.join(HERE, "research", "RESULTS_" + VERSION + ".md"))
