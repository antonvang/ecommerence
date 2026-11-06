"""Claude's EVALUATOR_SPEC v1.1 implementation (director order 51 P0): v1 + fail-closed validation, embargo, fsum in
sorted order, explicit S <= 0 / duplicate precedence, key_conflict against double alpha charges, atomic output.

    python3 research/desk/crosscheck/claude_eval_v11.py FIXTURE.json... --out DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import hypo_engine as he  # noqa: E402

VERSION = "1.1"
SPECIAL = {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}
COUNTERS = ("n_offgrid", "n_embargo", "n_duplicates", "n_not_member", "n_missing_ret", "n_signal_missing",
            "n_lookahead", "n_funding_missing", "n_extreme", "n_gap_bars", "n_empty_bars")
TOP = {"fixture_id", "cadence_s", "alpha", "q_fdr", "window", "universe", "hypotheses", "observations",
       "ledger_requests"}
TMAX = 4_102_444_800
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_measure(v):
    return v is None or is_num(v) or (isinstance(v, str) and v in SPECIAL)


def num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        v = SPECIAL.get(v)
        if v is None:
            return None
    if not is_num(v) or not math.isfinite(v):
        return None
    return float(v)


def nes(v):
    return isinstance(v, str) and v != ""


# ---------------------------------------------------------------- 1. validation

def validate(fx):
    errs = set()

    def e(code, path):
        errs.add((code, path))

    def fields(obj, path, required, allowed):
        if not isinstance(obj, dict):
            e("BAD_TYPE", path)
            return False
        for k in required:
            if k not in obj:
                e("MISSING_FIELD", f"{path}.{k}" if path else k)
        for k in obj:
            if k not in allowed:
                e("UNKNOWN_FIELD", f"{path}.{k}" if path else k)
        return True

    def time_ok(v, path):
        if not is_int(v) or not (0 <= v <= TMAX):
            e("BAD_TIME", path)
            return False
        return True

    if not fields(fx, "", TOP, TOP | {"lock"}):
        return sorted(errs)
    fid = fx.get("fixture_id")
    if "fixture_id" in fx and not (nes(fid) and ID_RE.match(fid)):
        e("BAD_TYPE", "fixture_id")
    cad = fx.get("cadence_s")
    if "cadence_s" in fx:
        if not is_int(cad):
            e("BAD_TYPE", "cadence_s")
        elif cad <= 0:
            e("BAD_VALUE", "cadence_s")
    for k in ("alpha", "q_fdr"):
        if k in fx:
            if not is_num(fx[k]):
                e("BAD_TYPE", k)
            elif not (0 < fx[k] < 1):
                e("BAD_VALUE", k)
    w = fx.get("window")
    if "window" in fx and fields(w, "window", ("start", "end"), {"start", "end", "embargo_s"}):
        ok = all(time_ok(w[k], f"window.{k}") for k in ("start", "end") if k in w)
        if ok and "start" in w and "end" in w and w["start"] >= w["end"]:
            e("BAD_VALUE", "window")
        if "embargo_s" in w:
            if not is_int(w["embargo_s"]):
                e("BAD_TYPE", "window.embargo_s")
            elif ok and "start" in w and "end" in w and not (0 <= w["embargo_s"] < w["end"] - w["start"]):
                e("BAD_VALUE", "window.embargo_s")
    u = fx.get("universe")
    if "universe" in fx:
        if not isinstance(u, dict):
            e("BAD_TYPE", "universe")
        else:
            for a, m in u.items():
                p = f"universe.{a}"
                if fields(m, p, ("listed_from", "delisted_at"), {"listed_from", "delisted_at"}):
                    lf = m.get("listed_from")
                    if "listed_from" in m and time_ok(lf, f"{p}.listed_from"):
                        d = m.get("delisted_at")
                        if "delisted_at" in m and d is not None and (not time_ok(d, f"{p}.delisted_at") or d <= lf):
                            e("BAD_VALUE", f"{p}.delisted_at")
    hyps = fx.get("hypotheses")
    hids, keys_used = set(), set()
    if "hypotheses" in fx:
        if not isinstance(hyps, list):
            e("BAD_TYPE", "hypotheses")
            hyps = []
        hreq = ("hid", "family", "signal_key", "rule", "cost_bps", "funding")
        for i, h in enumerate(hyps):
            p = f"hypotheses[{i}]"
            if not fields(h, p, hreq, set(hreq)):
                continue
            for k in ("hid", "family", "signal_key"):
                if k in h and not nes(h[k]):
                    e("BAD_TYPE", f"{p}.{k}")
            if "rule" in h and h["rule"] not in ("sign", "clip1"):
                e("BAD_TYPE", f"{p}.rule")
            if "cost_bps" in h:
                if not is_num(h["cost_bps"]):
                    e("BAD_TYPE", f"{p}.cost_bps")
                elif not math.isfinite(h["cost_bps"]) or h["cost_bps"] < 0:
                    e("BAD_VALUE", f"{p}.cost_bps")
            if "funding" in h and not isinstance(h["funding"], bool):
                e("BAD_TYPE", f"{p}.funding")
            if nes(h.get("hid")):
                if h["hid"] in hids:
                    e("DUPLICATE_HID", f"{p}.hid")
                hids.add(h["hid"])
    obs = fx.get("observations")
    if "observations" in fx:
        if not isinstance(obs, list):
            e("BAD_TYPE", "observations")
            obs = []
        for i, o in enumerate(obs):
            p = f"observations[{i}]"
            if not fields(o, p, ("ts", "asset", "ret", "funding", "signals"),
                          {"ts", "asset", "ret", "funding", "signals"}):
                continue
            if "ts" in o:
                time_ok(o["ts"], f"{p}.ts")
            if "asset" in o and not isinstance(o["asset"], str):
                e("BAD_TYPE", f"{p}.asset")
            for k in ("ret", "funding"):
                if k in o and not is_measure(o[k]):
                    e("BAD_TYPE", f"{p}.{k}")
            sg = o.get("signals")
            if "signals" in o:
                if not isinstance(sg, dict):
                    e("BAD_TYPE", f"{p}.signals")
                else:
                    for sk, sv in sg.items():
                        q = f"{p}.signals.{sk}"
                        if fields(sv, q, ("value", "avail_ts"), {"value", "avail_ts"}):
                            keys_used.add(sk)
                            if "value" in sv and not is_measure(sv["value"]):
                                e("BAD_TYPE", f"{q}.value")
                            if "avail_ts" in sv:
                                time_ok(sv["avail_ts"], f"{q}.avail_ts")
    for i, h in enumerate(hyps if isinstance(hyps, list) else []):
        if isinstance(h, dict) and nes(h.get("signal_key")) and h["signal_key"] not in keys_used:
            e("UNKNOWN_SIGNAL", f"hypotheses[{i}].signal_key")
    lr = fx.get("ledger_requests")
    if "ledger_requests" in fx:
        if not isinstance(lr, list):
            e("BAD_TYPE", "ledger_requests")
        else:
            req = ("key", "hid", "family", "variants", "alpha", "ts")
            for i, q in enumerate(lr):
                p = f"ledger_requests[{i}]"
                if not fields(q, p, req, set(req)):
                    continue
                for k in ("key", "hid", "family"):
                    if k in q and not nes(q[k]):
                        e("BAD_TYPE", f"{p}.{k}")
                if "ts" in q:
                    time_ok(q["ts"], f"{p}.ts")
    if "lock" in fx:
        lk = fx["lock"]
        if fields(lk, "lock", ("protocol_sha256", "data_sha256"), {"protocol_sha256", "data_sha256"}):
            if not errs:
                proto = {k: fx[k] for k in ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}
                if lk.get("protocol_sha256") != sha(proto):
                    e("LOCK_MISMATCH", "lock.protocol_sha256")
                if lk.get("data_sha256") != sha(fx["observations"]):
                    e("LOCK_MISMATCH", "lock.data_sha256")
    return sorted(errs)


# ---------------------------------------------------------------- evaluation

def member(universe, a, t):
    m = universe.get(a)
    return m is not None and m["listed_from"] <= t and (m["delisted_at"] is None or t < m["delisted_at"])


def nw_lag(T):
    return max(0, min(T - 1, int(math.floor(4 * (T / 100) ** (2 / 9)))))


def evaluate(fx):
    errs = validate(fx)
    fid = fx.get("fixture_id") if isinstance(fx, dict) and nes(fx.get("fixture_id")) and \
        ID_RE.match(fx.get("fixture_id")) else None
    if errs:
        return {"spec_version": VERSION, "fixture_id": fid, "status": "INVALID_INPUT",
                "errors": [{"code": c, "path": p} for c, p in errs]}
    cad, start, end = fx["cadence_s"], fx["window"]["start"], fx["window"]["end"]
    emb = fx["window"].get("embargo_s", 0)
    grid = list(range(start, end, cad))
    gset = set(grid)
    live = [t for t in grid if t >= start + emb]
    base = {k: 0 for k in COUNTERS}
    rows_at, any_rows, reserved = {}, set(), set()
    for o in fx["observations"]:
        t, a = o["ts"], o["asset"]
        if t not in gset:
            base["n_offgrid"] += 1
            continue
        if t < start + emb:
            base["n_embargo"] += 1
            continue
        any_rows.add(t)
        if (t, a) in reserved:
            base["n_duplicates"] += 1
            continue
        reserved.add((t, a))
        if not member(fx["universe"], a, t):
            base["n_not_member"] += 1
            continue
        rows_at.setdefault(t, {})[a] = o

    out, seen_fp, tested = {}, {}, []
    for h in fx["hypotheses"]:
        c = dict(base)
        prev, xs, gs, costs, funds = {}, [], [], [], []
        for t in live:
            if t not in any_rows:
                c["n_gap_bars"] += 1
            cur, nets, grs = {}, [], []
            for a in sorted(rows_at.get(t, {})):
                o = rows_at[t][a]
                r = num(o["ret"])
                if r is None:
                    c["n_missing_ret"] += 1
                    continue
                sig = o["signals"].get(h["signal_key"])
                sv = num(sig["value"]) if sig is not None else None
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
                    fr = num(o["funding"])
                    if fr is None:
                        c["n_funding_missing"] += 1
                    else:
                        f = w * fr
                if abs(r) > 0.5:
                    c["n_extreme"] += 1
                g = w * r
                nets.append(g - cost - f)
                grs.append(g)
                costs.append(cost)
                funds.append(f)
                cur[a] = w
            prev = cur
            if t in any_rows and not nets:
                c["n_empty_bars"] += 1
            if nets:
                xs.append(math.fsum(nets) / len(nets))
                gs.append(math.fsum(grs) / len(grs))
        T = len(xs)
        res = {**c, "T": T, "mean_gross": math.fsum(gs) / T if T else None,
               "mean_net": math.fsum(xs) / T if T else None, "total_cost": math.fsum(costs),
               "total_funding": math.fsum(funds), "hac_lag": None, "se": None, "t": None, "p_one": None,
               "holm_reject": None, "bh_reject": None, "duplicate_of": None, "status": "INSUFFICIENT"}
        if T >= 30:
            L = nw_lag(T)
            res["hac_lag"] = L
            m = math.fsum(xs) / T
            d = [v - m for v in xs]
            S = math.fsum(v * v for v in d) / T + 2 * math.fsum(
                (1 - k / (L + 1)) * math.fsum(d[i] * d[i - k] for i in range(k, T)) / T for k in range(1, L + 1))
            if S > 0:
                se = math.sqrt(S / T)
                tstat = m / se
                res.update(status="TESTED", t=tstat, se=se, p_one=he.p_one(tstat))
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
    return {"spec_version": VERSION, "fixture_id": fx["fixture_id"], "status": "OK", "hypotheses": out,
            "ledger": ledger(fx["ledger_requests"])}


def ledger(reqs):
    entries, accepted, errors, hits, totals = [], {}, [], 0, {}
    prev = "0" * 64
    for q in reqs:
        v, a = q["variants"], q["alpha"]
        if q["key"] in accepted:
            if accepted[q["key"]] == (q["hid"], q["family"], v, a):
                hits += 1
            else:
                errors.append({"key": q["key"], "reason": "key_conflict"})
            continue
        if not is_int(v) or v < 1:
            errors.append({"key": q["key"], "reason": "variants"})
            continue
        if not is_num(a) or not math.isfinite(a) or a < 0:
            errors.append({"key": q["key"], "reason": "alpha"})
            continue
        e = {"seq": len(entries), "key": q["key"], "hid": q["hid"], "family": q["family"], "variants": v,
             "alpha": a, "ts": q["ts"], "prev": prev}
        prev = sha(e)
        entries.append(e)
        accepted[q["key"]] = (q["hid"], q["family"], v, a)
        t = totals.setdefault(q["family"], {"attempts": 0, "variants": 0, "alphas": [], "_h": set()})
        t["attempts"] += 1
        t["variants"] += v
        t["alphas"].append(a)
        t["_h"].add(q["hid"])
    tot = {f: {"attempts": t["attempts"], "variants": t["variants"], "alpha": math.fsum(t["alphas"]),
               "hypotheses": len(t["_h"])} for f, t in totals.items()}
    return {"entries": len(entries), "head": prev, "idempotent_hits": hits, "errors": errors, "totals": tot}


def write_atomic(path, text):
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    for p in a.fixtures:
        with open(p, encoding="utf-8") as f:
            fx = json.load(f)
        r = evaluate(fx)
        name = r["fixture_id"] or os.path.splitext(os.path.basename(p))[0]
        write_atomic(os.path.join(a.out, name + ".json"), canonical(r))


if __name__ == "__main__":
    main()
