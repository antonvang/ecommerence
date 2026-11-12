"""Director decision 101: three context filters on top of the 12 baseline event farm variants (design before the
protocol lock; nothing is activated). research/desk/EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md.

Every filter is a pure function of bars[:known_i + 1] of the setup's own 5m series. `context(bars)` computes three causal
series in one pass (the value at bar i uses bars 0..i only, so truncating or rewriting the future cannot change it), and
`passes(setup, ctx, combo)` reads them at the setup's known_i. The baseline variants are not changed: a filter only
keeps or drops a baseline setup, with the engine's own entry, stop, target and outcome.

DEFINITIONS (FILTER_PARAMS, fixed now, before any data; reasons in the draft):
F1 TREND_1H. 1h bars = complete UTC hours of 12 consecutive 5m bars (o first, h max, l min, c last); an incomplete hour
   is dropped. A 1h bar exists from the close of its last 5m bar. 1h swings: fractal k1 = 2 as in the engine (h[j] >
   the k1 highs before, >= the k1 highs after; lows mirrored), known when 1h bar j + k1 has closed. Trend = +1 when the
   last two confirmed swing highs AND the last two confirmed swing lows are each higher (strictly), -1 when both are
   lower, else 0. A long setup passes only with trend +1, a short only with -1.
F2 PDL_RETEST. Day D = UTC date of the setup's known bar. PDH / PDL = max high / min low of the 5m bars of day D-1, only
   if D-1 has >= 95 % of its 288 bars (else no level: nothing passes). Long side, scanning day D's bars up to known_i:
   breakout = a close > PDH; after it, a close < PDH cancels it; retest = a later bar (not the breakout bar) within
   retest_bars = 12 bars of the breakout with low <= PDH while no close < PDH occurred since the breakout; a breakout
   without a retest within 12 bars is spent until a close < PDH resets it. A long setup passes when a retested breakout
   is in force at known_i (no close < PDH since the breakout) and its entry >= PDH. Short mirrored with PDL.
F3 VWAP_STRETCH. VWAP anchored at 00:00 UTC (anchor parameter): sum(tp * v) / sum(v) over the anchor's bars up to and
   including bar i, tp = (h + l + c) / 3; undefined when sum(v) = 0. Stretch = dir * (VWAP - close_i) / ATR, ATR = the
   setup's engine ATR (atr_at known_i). A setup passes when stretch >= 1.0: a long at least one ATR below VWAP
   (discount), a short at least one ATR above (premium). VWAP needs volume: a session with a missing 5m bar or a bar
   with missing / zero volume is INCOMPLETE from that bar to the session's end, and F3 is BLOCKED there (no setup
   passes), never approximated.
Combinations: every non-empty subset of {F1, F2, F3} (7) applied to each of the 12 baseline variants = 84 new tests.
"""
from __future__ import annotations

import itertools
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import event_farm_driver as drv  # noqa: E402

BS = 300
FILTER_PARAMS = {"k1": 2, "hour_s": 3600, "pd_min_coverage": 0.95, "retest_bars": 12, "vwap_anchor": "00:00",
                 "stretch_atr": 1.0}
FILTERS = ("F1", "F2", "F3")
COMBOS = tuple("+".join(c) for n in (1, 2, 3) for c in itertools.combinations(FILTERS, n))   # 7
BASELINE_TESTS = 12
REFERENCE_N_MIN = 19753                     # register 19,438 + 315 event farm tests (orders 90 and 100)


def combo_ids():
    return list(COMBOS)


def all_forward_tests():
    """Baseline 12 plus 7 combos x 12 variants = 96 forward tests."""
    ef = drv.engine()
    vids = [ef._variant_id(v) for v in ef.VARIANTS]
    return [f"base/{v}" for v in vids] + [f"{c}/{v}" for c in COMBOS for v in vids]


def reference_n():
    return REFERENCE_N_MIN + len(all_forward_tests())


def _hhmm(text):
    hh, mm = text.split(":")
    return int(hh) * 3600 + int(mm) * 60


# ---------------------------------------------------------------- causal context series

def trend_1h(bars, k1=FILTER_PARAMS["k1"], hour_s=FILTER_PARAMS["hour_s"]):
    """trend[i] in {+1, -1, 0} as known at the close of 5m bar i."""
    need = hour_s // BS
    h1, out = [], []
    sh, sl = [], []                               # confirmed 1h swing levels in time order
    cur, members, state = None, [], 0
    for b in bars:
        start = b[0] // hour_s * hour_s
        if start != cur:
            cur, members = start, []
        members.append(b)
        if b[0] + BS == start + hour_s:           # the hour has closed with this bar
            if len(members) == need and all(m[0] == start + k * BS for k, m in enumerate(members)):
                h1.append((start, members[0][1], max(m[2] for m in members), min(m[3] for m in members),
                           members[-1][4]))
                j = len(h1) - 1 - k1
                if j - k1 >= 0:
                    H, L = [x[2] for x in h1], [x[3] for x in h1]
                    if H[j] > max(H[j - k1:j]) and H[j] >= max(H[j + 1:j + k1 + 1]):
                        sh.append(H[j])
                    if L[j] < min(L[j - k1:j]) and L[j] <= min(L[j + 1:j + k1 + 1]):
                        sl.append(L[j])
                    if len(sh) >= 2 and len(sl) >= 2:
                        up = sh[-1] > sh[-2] and sl[-1] > sl[-2]
                        down = sh[-1] < sh[-2] and sl[-1] < sl[-2]
                        state = 1 if up else (-1 if down else 0)
            cur, members = None, []
        out.append(state)
    return out


def prior_day_retest(bars, min_cov=FILTER_PARAMS["pd_min_coverage"], retest_bars=FILTER_PARAMS["retest_bars"]):
    """Per bar i: (pdh, pdl, long_ok, short_ok) as known at the close of bar i.
    Per side and UTC day a small state machine over the day's bars (k = position in the day):
    idle --close beyond--> broken(b = k) --touch at b < k <= b + N, no close back--> retested
    broken/retested --close back--> idle; broken without a touch by k = b + N --> spent --close back--> idle.
    ok = retested and still in force."""
    per_day = 86400 // BS
    day_hi, day_lo, day_n = {}, {}, {}
    out, cur_day, st = [], None, None
    for b in bars:
        d = b[0] // 86400
        if d != cur_day:
            cur_day, prev = d, d - 1
            ok = day_n.get(prev, 0) >= min_cov * per_day
            st = {"lvl": {1: day_hi[prev] if ok else None, -1: day_lo[prev] if ok else None}, "k": 0,
                  1: {"b": None, "re": False, "spent": False}, -1: {"b": None, "re": False, "spent": False}}
        day_hi[d] = max(day_hi.get(d, b[2]), b[2])
        day_lo[d] = min(day_lo.get(d, b[3]), b[3])
        day_n[d] = day_n.get(d, 0) + 1
        k = st["k"]
        st["k"] += 1
        res = {}
        for side in (1, -1):
            lvl, s = st["lvl"][side], st[side]
            if lvl is None:
                res[side] = False
                continue
            c = b[4]
            beyond = c > lvl if side > 0 else c < lvl
            back = c < lvl if side > 0 else c > lvl
            touch = b[3] <= lvl if side > 0 else b[2] >= lvl
            if s["b"] is not None:
                if back:
                    s.update(b=None, re=False)
                elif not s["re"]:
                    if touch and k > s["b"]:
                        s["re"] = True
                    elif k - s["b"] >= retest_bars:
                        s.update(b=None, re=False, spent=True)
            elif s["spent"]:
                if back:
                    s["spent"] = False
            elif beyond:
                s.update(b=k, re=False)
            res[side] = s["b"] is not None and s["re"]
        out.append((st["lvl"][1], st["lvl"][-1], res[1], res[-1]))
    return out


def vwap_series(bars, anchor=FILTER_PARAMS["vwap_anchor"]):
    """(vwap[i], status[i]) over the anchor session up to and including bar i, tp = (h + l + c) / 3.
    status OK only if the session's bars so far are complete from the anchor (no missing 5m bar) and every one has a
    volume > 0; otherwise INCOMPLETE for the rest of that session and vwap None (never an approximate value)."""
    a = _hhmm(anchor)
    out, sess, pv, vv, bad, nxt = [], None, 0.0, 0.0, False, None
    for b in bars:
        sid = (b[0] - a) // 86400
        if sid != sess:
            sess, pv, vv = sid, 0.0, 0.0
            nxt = sid * 86400 + a                                  # the session's first slot
            bad = False
        if b[0] != nxt or not (isinstance(b[5], (int, float)) and math.isfinite(b[5]) and b[5] > 0):
            bad = True
        nxt = b[0] + BS
        if not bad:
            pv += (b[2] + b[3] + b[4]) / 3.0 * b[5]
            vv += b[5]
        out.append((None, "INCOMPLETE") if bad else (pv / vv, "OK"))
    return out


def context(bars, fp=None):
    fp = {**FILTER_PARAMS, **(fp or {})}
    return {"trend": trend_1h(bars, fp["k1"], fp["hour_s"]),
            "pd": prior_day_retest(bars, fp["pd_min_coverage"], fp["retest_bars"]),
            "vwap": vwap_series(bars, fp["vwap_anchor"]), "close": [b[4] for b in bars], "fp": fp}


def vwap_status(setup, ctx):
    return ctx["vwap"][setup["known_i"]][1]


# ---------------------------------------------------------------- the filters

def f1(setup, ctx):
    return ctx["trend"][setup["known_i"]] == setup["dir"]


def f2(setup, ctx):
    pdh, pdl, long_ok, short_ok = ctx["pd"][setup["known_i"]]
    if setup["dir"] > 0:
        return bool(long_ok) and setup["entry"] >= pdh
    return bool(short_ok) and setup["entry"] <= pdl


def stretch(setup, ctx):
    k = setup["known_i"]
    vw, status = ctx["vwap"][k]
    if status != "OK" or not setup.get("atr"):
        return None
    return setup["dir"] * (vw - ctx["close"][k]) / setup["atr"]


def f3(setup, ctx):
    s = stretch(setup, ctx)
    return s is not None and s >= ctx["fp"]["stretch_atr"]


FILTER_FN = {"F1": f1, "F2": f2, "F3": f3}


def passes(setup, ctx, combo):
    return all(FILTER_FN[f](setup, ctx) for f in combo.split("+"))


def apply(setups, bars, combo, ctx=None):
    """The baseline setups that pass `combo`, unchanged. ctx may be passed to share one causal pass."""
    ctx = ctx or context(bars)
    return [s for s in setups if passes(s, ctx, combo)]


def lookahead_signal(fp=None):
    """signal_fn for validation_engine.check_lookahead: the three context series as one number per bar."""
    def fn(bars):
        c = context(bars, fp)
        out = []
        for t, (pd, (vw, _)) in zip(c["trend"], zip(c["pd"], c["vwap"])):
            pdh, pdl, lo, so = pd
            out.append(t * 1e6 + (pdh or 0.0) + 1e-3 * (pdl or 0.0) + 10 * lo + 20 * so + 1e-6 * (vw or 0.0))
        return out
    return fn


# ---------------------------------------------------------------- null with filters

def null_with_filters(seed=83, instruments=3, days=60, costs=(0.0, 1.0, 5.0, 8.0)):
    """The engine null's bars (event_farm.null_run's generator and seeds) with the baseline and all 7 combos."""
    ef = drv.engine()
    base = ef.params()
    bars_by = {f"RW{k + 1}": ef.random_walk_bars(seed * 1000 + k, days, base["bar_seconds"]) for k in range(instruments)}
    out = {"seed": seed, "instruments": instruments, "days": days, "tests": {}}
    for name in sorted(bars_by):
        b = bars_by[name]
        events = ef.detect(b, base)
        ctx = context(b)
        for v in ef.VARIANTS:
            vid = ef._variant_id(v)
            pv = ef.params(**v)
            setups, _ = ef.build_setups(events, b, pv)
            outs = [ef.setup_outcome(s, b, pv) for s in setups]
            for combo in ("base",) + COMBOS:
                d = out["tests"].setdefault(f"{combo}/{vid}", {"setups": 0, "gross": [], "cost_r": []})
                for s, o in zip(setups, outs):
                    if combo != "base" and not passes(s, ctx, combo):
                        continue
                    d["setups"] += 1
                    if o["gross_r"] is not None:
                        d["gross"].append(o["gross_r"])
                        d["cost_r"].append(1e-4 * s["entry"] / s["risk"])
    for tid, d in out["tests"].items():
        g = d.pop("gross")
        cr = d.pop("cost_r")
        d["setups_per_instrument_day"] = d["setups"] / (instruments * days)
        d["trades"] = len(g)
        d["mean_gross_r"] = statistics.fmean(g) if g else None
        d["t_gross"] = (statistics.fmean(g) / statistics.pstdev(g) * math.sqrt(len(g))
                        if len(g) > 1 and statistics.pstdev(g) > 0 else None)
        d["mean_net_r"] = {f"{c:g}": (statistics.fmean([x - c * y for x, y in zip(g, cr)]) if g else None) for c in costs}
    return out


def pooled(null, prefix):
    rows = [d for t, d in null["tests"].items() if t.split("/")[0] == prefix and d["trades"]]
    n = sum(d["trades"] for d in rows)
    if not n:
        return {"trades": 0, "mean_gross_r": None, "mean_net_r": None}
    return {"trades": n, "mean_gross_r": sum(d["mean_gross_r"] * d["trades"] for d in rows) / n,
            "mean_net_r": {c: sum(d["mean_net_r"][c] * d["trades"] for d in rows) / n for c in rows[0]["mean_net_r"]},
            "setups_per_instrument_day": sum(d["setups_per_instrument_day"] for d in rows) / len(rows)}


def v2_filter_records(start_date, end_date):
    """Seven FUTURE records (one per combo, 12 variants each) in the 96-test forward family; in memory only."""
    from research.tools import factory, register_v2 as v2
    tests = all_forward_tests()
    universe = {"definition": "96 fremadrettede tests: 12 baseline + 7 filterkombinationer x 12", "size": len(tests),
                "members_sha256": factory.sha(tests)}
    src = {"name": "fapi 5m klines BTCUSDT/ETHUSDT, kun lukkede barer, fremadrettet (beskrevet, ikke godkendt)",
           "sha256": factory.sha({"endpoint": "GET /fapi/v1/klines", "interval": "5m"})}
    cost = {"name": "lab-papirbog 28 bps rundtur", "round_trip_bps": 28.0, "sha256": factory.sha({"rt_bps": 28.0})}
    recs = []
    for combo in COMBOS:
        vals = {"combo": combo, "filter_params": FILTER_PARAMS, "family_tests": 12, "reference_n": reference_n(),
                "reference_n_min_before": REFERENCE_N_MIN, "classification": "RELATED_MECHANISM",
                "independent_lineage": False, "independent_discovery_claim": False, "status": "UDKAST, IKKE LÅST",
                "activated": False, "engine": {"commit": drv.ENGINE_COMMIT, "sha256": drv.ENGINE_SHA256}}
        method = f"baseline-setups filtreret med {combo}; beskrivende; N = {reference_n()}"
        recs.append(v2.record(
            f"EVENT_FARM_FWD_FILTER_{combo.replace('+', '_')}", v2.FUTURE, hypothesis_id=f"EVENT_FARM:FWD:{combo}",
            lineage=drv.LINEAGE, trial_universe=universe, variants_tested=None, parameters=v2.parameters_block(vals),
            code_hash=drv.ENGINE_SHA256, data_source=src, data_period={"start": start_date, "end": end_date},
            cost_model=cost, evaluation_method={"name": method, "sha256": factory.sha(method)},
            data_quality={"status": "NOT_CHECKED"}, deviations=[]))
    return recs


def main():
    s = null_with_filters()
    print(f"null seed {s['seed']}, {s['instruments']} x {s['days']} dage")
    for prefix in ("base",) + COMBOS:
        p = pooled(s, prefix)
        net = p["mean_net_r"] or {}
        print(f"{prefix:10s} setups/instr-dag {p.get('setups_per_instrument_day', 0):.2f} handler {p['trades']} "
              f"brutto {p['mean_gross_r'] if p['mean_gross_r'] is None else round(p['mean_gross_r'], 4)} "
              f"netto@1 {net.get('1')} netto@8 {net.get('8')}")
    ts = [d["t_gross"] for d in s["tests"].values() if d["t_gross"] is not None]
    print("max |t| over", len(s["tests"]), "tests:", round(max(abs(t) for t in ts), 2))
    print("N =", reference_n())


if __name__ == "__main__":
    main()
