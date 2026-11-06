"""Claude's side of the EVALUATOR_SPEC v1 cross-check (director order 50 P3). Reuses the lab research statistics
(research/tools/hypo_engine.py: hac_t, p_one, holm, bh) where the spec's convention matches; everything else follows
the spec text. Synthetic fixtures only.

    python3 research/desk/crosscheck/claude_eval.py research/desk/synthetic_fixtures/*.json --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import hypo_engine as he  # noqa: E402

SPECIAL = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}
COUNTERS = ("n_offgrid", "n_duplicates", "n_not_member", "n_missing_ret", "n_signal_missing", "n_lookahead",
            "n_funding_missing", "n_extreme", "n_gap_bars", "n_empty_bars")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def num(v):
    """Finite float or None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        v = SPECIAL.get(v)
        if v is None:
            return None
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def member(universe, a, t):
    u = universe.get(a)
    return u is not None and u["listed_from"] <= t and (u["delisted_at"] is None or t < u["delisted_at"])


def nw_lag(T):
    return max(0, min(T - 1, int(math.floor(4 * (T / 100) ** (2 / 9)))))


def evaluate(fx):
    cad, start, end = fx["cadence_s"], fx["window"]["start"], fx["window"]["end"]
    grid = list(range(start, end, cad))
    gset = set(grid)
    base = {k: 0 for k in COUNTERS}
    rows_at = {}                          # t -> {asset: row} (first occurrence, members only)
    any_rows = set()
    for o in fx["observations"]:
        t = o["ts"]
        if t not in gset:
            base["n_offgrid"] += 1
            continue
        any_rows.add(t)
        d = rows_at.setdefault(t, {})
        if o["asset"] in d or (o["asset"], t) in base.get("_seen_nm", set()):
            base["n_duplicates"] += 1
            continue
        if not member(fx["universe"], o["asset"], t):
            base.setdefault("_seen_nm", set()).add((o["asset"], t))
            base["n_not_member"] += 1
            continue
        d[o["asset"]] = o
    base.pop("_seen_nm", None)

    out, seen_fp, tested = {}, {}, []
    for h in fx["hypotheses"]:
        c = dict(base)
        prev = {}                         # asset -> w used at the previous grid bar if that bar was valid
        xs, gs = [], []
        tot_cost = tot_fund = 0.0
        for t in grid:
            if t not in any_rows:
                c["n_gap_bars"] += 1
            cur = {}
            nets, grs = [], []
            for a, o in sorted(rows_at.get(t, {}).items()):
                r = num(o.get("ret"))
                sig = (o.get("signals") or {}).get(h["signal_key"])
                sv = num(sig.get("value")) if isinstance(sig, dict) else None
                if r is None:                         # spec 3.1: MISSING; steps 2-7 do not apply
                    c["n_missing_ret"] += 1
                    continue
                if sv is None:
                    c["n_signal_missing"] += 1
                    w = 0.0
                elif sig["avail_ts"] > t:
                    c["n_lookahead"] += 1
                    w = 0.0
                elif h["rule"] == "sign":
                    w = 1.0 if sv > 0 else (-1.0 if sv < 0 else 0.0)
                else:
                    w = min(1.0, max(-1.0, sv))
                cost = h["cost_bps"] / 10_000 * abs(w - prev.get(a, 0.0))
                f = 0.0
                if h["funding"]:
                    fr = num(o.get("funding"))
                    if fr is None:
                        c["n_funding_missing"] += 1
                    else:
                        f = w * fr
                if abs(r) > 0.5:
                    c["n_extreme"] += 1
                g = w * r
                nets.append(g - cost - f)
                grs.append(g)
                tot_cost += cost
                tot_fund += f
                cur[a] = w
            prev = cur
            if t in any_rows and not nets:
                c["n_empty_bars"] += 1
            if nets:
                xs.append(math.fsum(nets) / len(nets))
                gs.append(math.fsum(grs) / len(grs))
        T = len(xs)
        res = {**c, "T": T, "mean_gross": math.fsum(gs) / T if T else None,
               "mean_net": math.fsum(xs) / T if T else None, "total_cost": tot_cost, "total_funding": tot_fund,
               "hac_lag": None, "se": None, "t": None, "p_one": None, "holm_reject": None, "bh_reject": None,
               "duplicate_of": None, "status": "INSUFFICIENT"}
        if T >= 30:
            L = nw_lag(T)
            res["hac_lag"] = L
            m = math.fsum(xs) / T
            d = [v - m for v in xs]
            S = math.fsum(v * v for v in d) / T + 2 * math.fsum(
                (1 - k / (L + 1)) * math.fsum(d[i] * d[i - k] for i in range(k, T)) / T for k in range(1, L + 1))
            if S > 0:
                tstat, _ = he.hac_t(xs, lags=L)
                res.update(status="TESTED", t=tstat, se=math.sqrt(S / T), p_one=he.p_one(tstat))
        fp = (h["family"], h["signal_key"], h["rule"])
        if fp in seen_fp:
            res.update(status="DUPLICATE", duplicate_of=seen_fp[fp])
        else:
            seen_fp[fp] = h["hid"]
        if res["status"] == "TESTED":
            tested.append(h["hid"])
        out[h["hid"]] = res
    if tested:
        ps = [out[k]["p_one"] for k in tested]
        for k, hr, br in zip(tested, he.holm(ps, fx["alpha"]), he.bh(ps, fx["q_fdr"])):
            out[k]["holm_reject"], out[k]["bh_reject"] = hr, br
    return {"spec_version": 1, "fixture_id": fx["fixture_id"], "hypotheses": out, "ledger": ledger(fx)}


def ledger(fx):
    entries, keys, errors, hits, totals = [], set(), [], 0, {}
    prev = "0" * 64
    for q in fx.get("ledger_requests", []):
        if q["key"] in keys:
            hits += 1
            continue
        v, a = q.get("variants"), q.get("alpha")
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            errors.append({"key": q["key"], "reason": "variants"})
            continue
        if num(a) is None or a < 0:
            errors.append({"key": q["key"], "reason": "alpha"})
            continue
        e = {"seq": len(entries), "key": q["key"], "hid": q["hid"], "family": q["family"], "variants": v,
             "alpha": a, "ts": q["ts"], "prev": prev}
        prev = hashlib.sha256(canonical(e).encode()).hexdigest()
        entries.append(e)
        keys.add(q["key"])
        t = totals.setdefault(q["family"], {"attempts": 0, "variants": 0, "alpha": 0.0, "_h": set()})
        t["attempts"] += 1
        t["variants"] += v
        t["alpha"] += a
        t["_h"].add(q["hid"])
    tot = {f: {"attempts": t["attempts"], "variants": t["variants"], "alpha": t["alpha"], "hypotheses": len(t["_h"])}
           for f, t in totals.items()}
    return {"entries": len(entries), "head": prev, "idempotent_hits": hits, "errors": errors, "totals": tot}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    for p in a.fixtures:
        with open(p, encoding="utf-8") as f:
            r = evaluate(json.load(f))
        with open(os.path.join(a.out, r["fixture_id"] + ".json"), "w", encoding="utf-8") as f:
            f.write(canonical(r) + "\n")


if __name__ == "__main__":
    main()
