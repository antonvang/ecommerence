"""Acceptance for stage S2: reproduce tsmom_v1 and pmcal_v1 development results through the lab.

Data passes the gateway (purpose "reproduce", dev/validation only, hashes must equal the recorded ones); statistics
come from lab.stats; strategy simulation reuses the unchanged research modules. Every number is compared with the
stored result file. Holdout data is never requested.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import subprocess

from lab import stats
from lab.data import Gateway
from lab.db import HERE

RESULTS = os.path.join(HERE, "data", "research", "results")
TOL = 1e-12


def code_blob(path):
    try:
        return subprocess.check_output(["git", "rev-parse", f"HEAD:copybot/{path}"], cwd=HERE, text=True).strip()
    except Exception:
        return None


def same(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is None and b is None
        return math.isclose(a, b, rel_tol=TOL, abs_tol=TOL)
    return a == b


def compare(ours, stored, fields, prefix, out):
    for ours_k, stored_k in fields:
        ok = same(ours[ours_k], stored[stored_k])
        out.append({"field": f"{prefix}.{stored_k}", "ours": ours[ours_k], "stored": stored[stored_k], "match": ok})


def reproduce_tsmom(db, actor="system:repro"):
    from research import tsmom as T
    stored = json.load(open(os.path.join(RESULTS, "tsmom_v1_dev.json"), encoding="utf-8"))
    files = {os.path.join(T.DATA, k + ".json"): v for k, v in stored["data_hashes"].items()}
    gw, code = Gateway(db, actor), code_blob("research/tsmom.py")
    for split, period in (("dev", T.DEV), ("validation", T.VAL)):
        gw.access("L14_tsmom_v1", split, list(files), (T.ts(period[0]), T.ts(period[1]) + T.WEEK),
                  "tsmom fetch cache (Binance + Hyperliquid public APIs)", "reproduce", code, files)
    d, hashes = T.data_from_cache()
    rows = [{"field": "data_hashes", "ours": hashes == stored["data_hashes"], "stored": True,
             "match": hashes == stored["data_hashes"]}]

    def summ(weeks):
        r = [w["net"] for w in weeks]
        s = stats.series_summary(r, 52, lb=lambda x: stats.block_lb(x, 0.005, block=8))
        return s

    fields = [("n", "weeks"), ("total", "total_net"), ("mean", "mean_week"), ("sd", "sd_week"),
              ("sharpe_ann", "sharpe_ann"), ("max_dd", "max_dd"), ("worst", "worst_week"), ("thirds", "thirds"),
              ("lb", "lb_99_5"), ("psr_0", "psr_0")]
    dev = {}
    for L in T.LOOKBACKS:
        dev[L] = summ(T.run(d, T.DEV, L))
        compare(dev[L], stored["dev_by_L"][str(L)], fields, f"dev_by_L.{L}", rows)
    L = max(T.LOOKBACKS, key=lambda k: dev[k]["sharpe_ann"] if dev[k]["sharpe_ann"] is not None else -9)
    rows.append({"field": "L", "ours": L, "stored": stored["L"], "match": L == stored["L"]})
    compare(summ(T.run(d, T.VAL, L)), stored["validation"], fields, "validation", rows)
    both = [w["net"] for w in T.run(d, T.DEV, L) + T.run(d, T.VAL, L)]
    m, sd = statistics.mean(both), statistics.stdev(both)
    agg = {"m": m, "sd": sd, "n_req": stats.n_req(m, sd, z_a=2.5758)}
    compare(agg, stored, [("m", "dev_val_mean"), ("sd", "dev_val_sd"), ("n_req", "n_req")], "", rows)
    return finish(db, actor, "L14_tsmom_v1", rows)


def reproduce_pmcal(db, actor="system:repro"):
    from research import pmcal as P
    stored = json.load(open(os.path.join(RESULTS, "pmcal_v1_dev.json"), encoding="utf-8"))
    gw, code = Gateway(db, actor), code_blob("research/pmcal.py")
    for split, period, names in (("dev", "dev", ("markets_dev", "histories_dev")),
                                 ("validation", "val", ("markets_val", "histories_val"))):
        files = {os.path.join(P.DATA, n + ".json"): stored["data_hashes"][n] for n in names}
        a, b = P.PERIODS[period]
        gw.access("L16_pmcal_v1", split, list(files), (P.ts(a), P.ts(b) + P.DAY),
                  "pmcal fetch cache (Polymarket Gamma + CLOB public APIs)", "reproduce", code, files)
    dev_ev, dev_h, h1 = P.from_cache("dev")
    val_ev, val_h, h2 = P.from_cache("val")
    rows = [{"field": "data_hashes", "ours": {**h1, **h2} == stored["data_hashes"], "stored": True,
             "match": {**h1, **h2} == stored["data_hashes"]}]

    def summ(rws):
        ordered = sorted(rws, key=lambda x: (x["end"], x["event"]))
        r = [x["r"] for x in ordered]
        s = stats.series_summary(r)
        s["lb"] = stats.cluster_lb(stats.clusters_in_order(rws, lambda x: x["week"], lambda x: x["r"]), 0.005)
        s["weeks"] = len({x["week"] for x in rws})
        return s

    fields = [("n", "events"), ("total", "total_net"), ("mean", "mean"), ("sd", "sd"), ("lb", "lb_99_5"),
              ("thirds", "thirds"), ("max_dd", "max_dd"), ("weeks", "weeks")]
    dev = {}
    for c in P.CONFIGS:
        dev[c] = summ(P.run(dev_ev, c, hist_of=dev_h)[0])
        compare(dev[c], stored["dev"][c]["summary"], fields, f"dev.{c}", rows)
    best = max([c for c in P.CONFIGS if dev[c]["mean"] is not None], key=lambda c: dev[c]["mean"])
    rows.append({"field": "config", "ours": best, "stored": stored["config"], "match": best == stored["config"]})
    vrows = P.run(val_ev, best, hist_of=val_h)[0]
    compare(summ(vrows), stored["validation"]["summary"], fields, "validation", rows)
    both = [x["r"] for x in P.run(dev_ev, best, hist_of=dev_h)[0] + vrows]
    m, sd = statistics.mean(both), statistics.stdev(both)
    agg = {"m": m, "sd": sd, "n_req": stats.n_req(m, sd, z_a=3.0233)}
    compare(agg, stored, [("m", "dev_val_mean"), ("sd", "dev_val_sd"), ("n_req", "n_req")], "", rows)
    return finish(db, actor, "L16_pmcal_v1", rows)


def finish(db, actor, exp_id, rows):
    bad = [r for r in rows if not r["match"]]
    db.event("repro.verified" if not bad else "repro.failed", actor, exp_id,
             {"fields": len(rows), "mismatches": [r["field"] for r in bad]})
    return {"exp_id": exp_id, "fields": len(rows), "mismatches": bad, "ok": not bad}
