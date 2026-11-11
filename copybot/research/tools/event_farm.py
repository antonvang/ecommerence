"""Event farm: deterministic labelling of ICT/SMC chart concepts on OHLCV bars, rule-based chains, an outcome book and a
daily study (research/desk/EVENT_FARM.md). Pure stdlib; no file, network or market data is read here.

A DESCRIPTIVE LABELLER, NOT A STRATEGY. Nothing here is activated, locked or charged to alpha. A setup is a label with
an entry, stop and target fixed by rule at the moment the pattern could be known; its outcome book says what followed.

NO LOOKAHEAD BY CONSTRUCTION. `Farm.step(bar)` sees one bar at a time and emits only events that are known at that bar's
close. Every event carries `ts` (where the pattern lies: the open time of its anchor bar), `known_ts` (close time of the
last bar it needed) and `known_i` (that bar's index). Chains use only events with known_i <= the chain's known_i and
bars[:known_i + 1]; outcomes use only bars after known_i. tests/test_event_farm.py checks truncation invariance.

BARS: a list of (ts, o, h, l, c, v), ts = bar open in epoch seconds (UTC), strictly increasing. A bar closes at
ts + bar_seconds. Gaps are allowed: the detectors work on bar order and the study reports coverage per day.

DEFINITIONS (every threshold is a parameter in DEFAULTS):
- ATR: atr_before(i) = mean true range of bars i-n..i-1 (known at the open of bar i); atr_at(i) = mean of i-n+1..i
  (known at the close of bar i). True range of bar 0 = h - l. None before n bars; a detector that needs ATR is silent.
- swing_high (fractal k): h[j] > every high of the k bars before and h[j] >= every high of the k bars after. Known only
  at bar j + k. swing_low mirrored. Ties to the right keep the earlier bar, so equal highs give one pivot.
- liquidity level: every confirmed swing is a level, active until swept, broken or pool_lookback bars without a new
  member. liquidity_pool_high/low: a new swing within pool_tol_atr * atr_before of an active, non-pending level on the
  same side joins it; the pool event fires when the level reaches 2 members (level = the extreme member).
- sweep_high: a bar with h > level + sweep_min_atr * ATR (level known before that bar) starts a pending sweep; the
  first bar within sweep_reclaim_bars (counting the piercing bar) that closes below the level completes it. If none
  does, the level is broken (accepted) and dropped silently. One sweep event per side per bar (the furthest level).
  sweep_low mirrored. Direction: sweep_high -1, sweep_low +1.
- structure: a close above the most recent confirmed, unbroken swing high (known before the bar) is bos_bull when the
  structure trend is up or undefined and mss_bull (= CHoCH) when it is down; the trend then becomes up. Mirrored.
- displacement_bull/bear: |c - o| > disp_atr * atr_before.
- ob_bull: at a bullish displacement, the last bearish bar (c < o) among the ob_lookback bars before it; zone = its
  low..high. ob_bear mirrored. Known at the displacement bar.
- fvg_bull: l[i] > h[i-2] and the gap >= fvg_min_atr * atr_before; zone h[i-2]..l[i]; ts = middle bar. fvg_bear mirrored.
  ifvg_bear (inversion): a later close below an active fvg_bull's low; ifvg_bull mirrored. FVGs expire after fvg_max_age.
- session_open_<name>: the bar whose [ts, ts + bar_seconds) contains the session time (UTC "HH:MM"); level = its open.
- rejection_high: range >= rej_min_atr * atr_before and upper wick >= rej_wick_frac * range. rejection_low mirrored.
- setup (chain): sweep_low -> the first mss_bull (or a break in chain_breaks) within mss_window bars of it -> anchor =
  the most recent fvg_bull (anchor "fvg"), ob_bull ("ob") or fvg else ob ("fvg_then_ob") known between the sweep's
  piercing bar and the break. Entry: zone mid ("mid"), near edge ("edge") or the break bar's close ("market"); a limit
  at or beyond that close becomes a market entry. Stop: sweep extreme -/+ stop_buffer_atr * atr_at(break). Target:
  entry +/- rr * risk. A risk below min_risk_atr * ATR is discarded (counted as bad_risk). A sweep feeds one chain.
"""
from __future__ import annotations

import collections
import hashlib
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DEFAULTS = {
    "bar_seconds": 300, "atr_n": 14, "swing_k": 3,
    "pool_tol_atr": 0.10, "pool_lookback": 288,
    "sweep_reclaim_bars": 1, "sweep_min_atr": 0.0,
    "disp_atr": 1.2, "ob_lookback": 5,
    "fvg_min_atr": 0.10, "fvg_max_age": 288,
    "sessions": (("asia", "00:00"), ("london", "07:00"), ("ny", "13:30")),
    "rej_wick_frac": 0.6, "rej_min_atr": 1.0,
    "mss_window": 24, "chain_breaks": ("mss",), "anchor": "fvg_then_ob", "entry_mode": "mid",
    "stop_buffer_atr": 0.0, "rr": 2.0, "min_risk_atr": 0.25,
    "fill_window": 12, "max_hold": 48, "horizons": (1, 3, 6, 12), "cost_bps": 1.0,
    "ambiguous": "stop_first",
}

BASE_KINDS = ("swing_high", "swing_low", "liquidity_pool_high", "liquidity_pool_low", "sweep_high", "sweep_low",
              "bos_bull", "bos_bear", "mss_bull", "mss_bear", "displacement_bull", "displacement_bear",
              "ob_bull", "ob_bear", "fvg_bull", "fvg_bear", "ifvg_bull", "ifvg_bear", "rejection_high", "rejection_low")
SETUP_KINDS = ("setup_long", "setup_short")
NOT_DEFINED = ("inducement", "manipulation_leg")    # in the video's vocabulary; no precise rule is claimed for them


def kinds(p=None):
    """The vocabulary for parameters p: base kinds, one session kind per configured session, the setup kinds."""
    p = params(**(p or {}))
    return BASE_KINDS + tuple(f"session_open_{n}" for n, _ in p["sessions"]) + SETUP_KINDS


def params(**over):
    unknown = sorted(k for k in over if k not in DEFAULTS)
    if unknown:
        raise ValueError(f"unknown parameter(s) {unknown}")
    p = dict(DEFAULTS)
    p.update(over)
    if type(p["swing_k"]) is not int or p["swing_k"] < 1 or type(p["atr_n"]) is not int or p["atr_n"] < 1:
        raise ValueError("swing_k and atr_n must be integers >= 1")
    if not 0.5 < p["rej_wick_frac"] <= 1.0:
        raise ValueError("rej_wick_frac must be in (0.5, 1]")
    if p["sweep_reclaim_bars"] < 1 or p["fill_window"] < 1 or p["max_hold"] < 1:
        raise ValueError("sweep_reclaim_bars, fill_window and max_hold must be >= 1")
    if p["anchor"] not in ("fvg", "ob", "fvg_then_ob") or p["entry_mode"] not in ("mid", "edge", "market"):
        raise ValueError("anchor must be fvg|ob|fvg_then_ob and entry_mode mid|edge|market")
    if p["ambiguous"] not in ("stop_first", "target_first"):
        raise ValueError("ambiguous must be stop_first (the rule) or target_first (a bracket, never the rule)")
    if not set(p["chain_breaks"]) <= {"mss", "bos"} or not p["chain_breaks"]:
        raise ValueError("chain_breaks must be a non-empty subset of (mss, bos)")
    p["sessions"] = tuple((str(n), str(t)) for n, t in p["sessions"])
    p["horizons"] = tuple(sorted(set(int(h) for h in p["horizons"])))
    p["chain_breaks"] = tuple(p["chain_breaks"])
    return p


def check_bars(bars):
    prev = None
    for i, b in enumerate(bars):
        if len(b) != 6 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in b):
            raise ValueError(f"bar {i} is not (ts, o, h, l, c, v) of finite numbers")
        ts, o, h, l, c, _ = b
        if h < max(o, c) or l > min(o, c):
            raise ValueError(f"bar {i}: high/low do not contain open/close")
        if prev is not None and ts <= prev:
            raise ValueError(f"bar {i}: ts is not strictly increasing")
        prev = ts


def _hhmm(text):
    hh, mm = text.split(":")
    sec = int(hh) * 3600 + int(mm) * 60
    if not 0 <= sec < 86400:
        raise ValueError(f"session time {text!r} is outside the day")
    return sec


class Farm:
    """Streaming detector. step(bar) returns the events known at that bar's close, in a fixed order."""

    def __init__(self, p=None):
        self.p = params(**(p or {}))
        self.sess = [(n, _hhmm(t)) for n, t in self.p["sessions"]]
        self.ts, self.o, self.h, self.l, self.c, self.tr = [], [], [], [], [], []
        self.levels = []                        # liquidity levels (swings and pools)
        self.fvgs = []                          # active FVGs for inversion
        self.last_sh = self.last_sl = None      # most recent confirmed swing high / low
        self.trend = None

    # ---- ATR known at the open (before) and at the close (at) of bar i
    def atr_before(self, i):
        n = self.p["atr_n"]
        return None if i < n else math.fsum(self.tr[i - n:i]) / n

    def atr_at(self, i):
        return self.atr_before(i + 1) if i + 1 <= len(self.tr) else None

    def _ev(self, kind, i, direction, **extra):
        k = len(self.ts) - 1
        ev = {"kind": kind, "ts": self.ts[i], "known_ts": self.ts[k] + self.p["bar_seconds"], "i": i, "known_i": k,
              "dir": direction}
        ev.update(extra)
        return ev

    def step(self, bar):
        ts, o, h, l, c, _ = bar
        if self.ts and ts <= self.ts[-1]:
            raise ValueError("ts is not strictly increasing")
        prev_c = self.c[-1] if self.c else None
        self.ts.append(ts), self.o.append(o), self.h.append(h), self.l.append(l), self.c.append(c)
        self.tr.append(h - l if prev_c is None else max(h - l, abs(h - prev_c), abs(l - prev_c)))
        i, p, out = len(self.ts) - 1, self.p, []
        a = self.atr_before(i)
        self._sessions(i, out)
        self._sweeps(i, a, out)
        self._structure(i, out)
        self._displacement(i, a, out)
        self._fvg(i, a, out)
        self._rejection(i, a, out)
        self._swings(i, a, out)
        return out

    def _sessions(self, i, out):
        bs, ts = self.p["bar_seconds"], self.ts[i]
        tod = ts % 86400
        for name, sec in self.sess:
            if tod <= sec < tod + bs:
                out.append(self._ev(f"session_open_{name}", i, 0, session_ts=ts - tod + sec, level=self.o[i]))

    def _sweeps(self, i, a, out):
        p, h, l, c = self.p, self.h[i], self.l[i], self.c[i]
        done = {"high": [], "low": []}
        keep = []
        for lv in self.levels:
            hi = lv["side"] == "high"
            if lv["pending"] is None:
                if i - lv["last_i"] > p["pool_lookback"]:
                    continue                                        # expired
                if lv["known_i"] < i:
                    margin = p["sweep_min_atr"] * a if (p["sweep_min_atr"] and a is not None) else 0.0
                    if p["sweep_min_atr"] and a is None:
                        keep.append(lv)
                        continue
                    if (hi and h > lv["level"] + margin) or (not hi and l < lv["level"] - margin):
                        lv["pending"], lv["extreme"] = i, (h if hi else l)
            if lv["pending"] is not None:
                lv["extreme"] = max(lv["extreme"], h) if hi else min(lv["extreme"], l)
                if (hi and c < lv["level"]) or (not hi and c > lv["level"]):
                    done[lv["side"]].append(lv)
                    continue
                if i - lv["pending"] + 1 >= p["sweep_reclaim_bars"]:
                    continue                                        # accepted beyond the level: broken, dropped
            keep.append(lv)
        self.levels = keep
        for side, kind, d in (("high", "sweep_high", -1), ("low", "sweep_low", 1)):
            if done[side]:
                pick = max(done[side], key=lambda v: v["level"]) if side == "high" else min(done[side], key=lambda v: v["level"])
                out.append(self._ev(kind, pick["pending"], d, level=pick["level"], extreme=pick["extreme"],
                                    pool=pick["count"] >= 2, members=pick["count"], n_levels=len(done[side]),
                                    pierce_i=pick["pending"]))

    def _structure(self, i, out):
        c = self.c[i]
        sh, sl = self.last_sh, self.last_sl
        if sh and not sh["broken"] and sh["known_i"] < i and c > sh["level"]:
            sh["broken"] = True
            kind = "mss_bull" if self.trend == "down" else "bos_bull"
            self.trend = "up"
            out.append(self._ev(kind, i, 1, level=sh["level"], swing_i=sh["i"]))
        if sl and not sl["broken"] and sl["known_i"] < i and c < sl["level"]:
            sl["broken"] = True
            kind = "mss_bear" if self.trend == "up" else "bos_bear"
            self.trend = "down"
            out.append(self._ev(kind, i, -1, level=sl["level"], swing_i=sl["i"]))

    def _displacement(self, i, a, out):
        if a is None or a <= 0:
            return
        o, c = self.o[i], self.c[i]
        body = c - o
        if abs(body) <= self.p["disp_atr"] * a:
            return
        d = 1 if body > 0 else -1
        out.append(self._ev("displacement_bull" if d > 0 else "displacement_bear", i, d, body_atr=abs(body) / a))
        for j in range(i - 1, max(-1, i - 1 - self.p["ob_lookback"]), -1):
            if (d > 0 and self.c[j] < self.o[j]) or (d < 0 and self.c[j] > self.o[j]):
                out.append(self._ev("ob_bull" if d > 0 else "ob_bear", j, d, zone_lo=self.l[j], zone_hi=self.h[j],
                                    displacement_i=i))
                break

    def _fvg(self, i, a, out):
        p, c = self.p, self.c[i]
        keep = []
        for g in self.fvgs:
            if i - g["known_i"] > p["fvg_max_age"]:
                continue
            if g["dir"] > 0 and c < g["zone_lo"]:
                out.append(self._ev("ifvg_bear", g["i"], -1, zone_lo=g["zone_lo"], zone_hi=g["zone_hi"], fvg_known_i=g["known_i"]))
                continue
            if g["dir"] < 0 and c > g["zone_hi"]:
                out.append(self._ev("ifvg_bull", g["i"], 1, zone_lo=g["zone_lo"], zone_hi=g["zone_hi"], fvg_known_i=g["known_i"]))
                continue
            keep.append(g)
        self.fvgs = keep
        if i < 2:
            return
        if p["fvg_min_atr"] and a is None:
            return
        need = p["fvg_min_atr"] * a if p["fvg_min_atr"] else 0.0
        for d, lo, hi in ((1, self.h[i - 2], self.l[i]), (-1, self.h[i], self.l[i - 2])):
            if hi > lo and hi - lo >= need:
                ev = self._ev("fvg_bull" if d > 0 else "fvg_bear", i - 1, d, zone_lo=lo, zone_hi=hi)
                out.append(ev)
                self.fvgs.append(ev)

    def _rejection(self, i, a, out):
        if a is None or a <= 0:
            return
        o, h, l, c = self.o[i], self.h[i], self.l[i], self.c[i]
        rng = h - l
        if rng <= 0 or rng < self.p["rej_min_atr"] * a:
            return
        f = self.p["rej_wick_frac"]
        if h - max(o, c) >= f * rng:
            out.append(self._ev("rejection_high", i, -1, wick_frac=(h - max(o, c)) / rng))
        if min(o, c) - l >= f * rng:
            out.append(self._ev("rejection_low", i, 1, wick_frac=(min(o, c) - l) / rng))

    def _swings(self, i, a, out):
        k = self.p["swing_k"]
        j = i - k
        if j - k < 0:
            return
        H, L = self.h, self.l
        if H[j] > max(H[j - k:j]) and H[j] >= max(H[j + 1:i + 1]):
            out.append(self._ev("swing_high", j, 0, level=H[j]))
            self.last_sh = {"level": H[j], "i": j, "known_i": i, "broken": False}
            self._add_level("high", H[j], j, i, a, out)
        if L[j] < min(L[j - k:j]) and L[j] <= min(L[j + 1:i + 1]):
            out.append(self._ev("swing_low", j, 0, level=L[j]))
            self.last_sl = {"level": L[j], "i": j, "known_i": i, "broken": False}
            self._add_level("low", L[j], j, i, a, out)

    def _add_level(self, side, level, j, i, a, out):
        if a is not None:
            tol = self.p["pool_tol_atr"] * a
            match = [lv for lv in self.levels if lv["side"] == side and lv["pending"] is None and
                     abs(lv["level"] - level) <= tol]
            if match:
                lv = max(match, key=lambda v: v["last_i"])
                lv["count"] += 1
                lv["level"] = max(lv["level"], level) if side == "high" else min(lv["level"], level)
                lv["last_i"], lv["known_i"] = i, i
                lv["members_i"].append(j)
                if lv["count"] == 2:
                    out.append(self._ev(f"liquidity_pool_{side}", j, 0, level=lv["level"], members_i=list(lv["members_i"])))
                return
        self.levels.append({"side": side, "level": level, "count": 1, "known_i": i, "last_i": i, "pending": None,
                            "extreme": None, "members_i": [j]})


def detect(bars, p=None):
    """All events of `bars`, in emission order (by known_i, then a fixed detector order)."""
    check_bars(bars)
    farm = Farm(p)
    out = []
    for b in bars:
        out.extend(farm.step(b))
    return out


def atr_at(bars, i, n):
    """ATR known at the close of bar i (mean true range of bars i-n+1..i); uses bars[:i + 1] only."""
    if i + 1 < n:
        return None
    trs = []
    for j in range(i - n + 1, i + 1):
        _, _, h, l, _, _ = bars[j]
        trs.append(h - l if j == 0 else max(h - l, abs(h - bars[j - 1][4]), abs(l - bars[j - 1][4])))
    return math.fsum(trs) / n


# ---------------------------------------------------------------- chains

def build_setups(events, bars, p=None):
    """(setups, chain_stats). Uses only events with known_i <= the break's known_i and bars[:break.known_i + 1]."""
    p = params(**(p or {}))
    breaks = {1: tuple(f"{b}_bull" for b in p["chain_breaks"]), -1: tuple(f"{b}_bear" for b in p["chain_breaks"])}
    anchors = {"fvg": ("fvg",), "ob": ("ob",), "fvg_then_ob": ("fvg", "ob")}[p["anchor"]]
    stats = collections.Counter()
    last_sweep = {1: None, -1: None}
    seen = []
    setups = []
    groups = collections.OrderedDict()                              # by known_i: a bar's events are known together
    for ev in events:
        groups.setdefault(ev["known_i"], []).append(ev)
    ordered = []
    for k in sorted(groups):
        g = groups[k]
        ordered += [(e, True) for e in g] + [(e, False) for e in g]  # first make the bar's events visible, then act
    for ev, visible_pass in ordered:
        if visible_pass:
            seen.append(ev)
            if ev["kind"] in ("sweep_low", "sweep_high"):
                last_sweep[ev["dir"]] = ev
            continue
        d = 1 if ev["kind"] in breaks[1] else (-1 if ev["kind"] in breaks[-1] else 0)
        if not d:
            continue
        sw = last_sweep[d]
        if sw is None or ev["known_i"] - sw["known_i"] > p["mss_window"]:
            continue
        last_sweep[d] = None                                        # a sweep feeds one chain
        stats["sweep_break"] += 1
        side = "bull" if d > 0 else "bear"
        anchor = None
        for name in anchors:
            cand = [e for e in seen if e["kind"] == f"{name}_{side}" and sw["pierce_i"] <= e["known_i"] <= ev["known_i"]]
            if cand:
                anchor = cand[-1]
                break
        if anchor is None:
            stats["no_anchor"] += 1
            continue
        k = ev["known_i"]
        past = bars[:k + 1]
        a = atr_at(past, k, p["atr_n"])
        if a is None or a <= 0:
            stats["no_atr"] += 1
            continue
        close = past[k][4]
        lo, hi = anchor["zone_lo"], anchor["zone_hi"]
        mode = p["entry_mode"]
        entry = close if mode == "market" else ((lo + hi) / 2 if mode == "mid" else (hi if d > 0 else lo))
        if mode != "market" and ((d > 0 and entry >= close) or (d < 0 and entry <= close)):
            entry, mode = close, "market"                           # a limit through the market fills at the close
        stop = sw["extreme"] - d * p["stop_buffer_atr"] * a
        risk = d * (entry - stop)
        if risk < p["min_risk_atr"] * a:
            stats["bad_risk"] += 1
            continue
        stats["setup"] += 1
        setups.append({
            "kind": "setup_long" if d > 0 else "setup_short", "ts": sw["ts"], "known_ts": ev["known_ts"], "i": sw["i"],
            "known_i": k, "dir": d, "entry": entry, "stop": stop, "target": entry + d * p["rr"] * risk, "risk": risk,
            "atr": a, "entry_mode": mode, "rr": p["rr"],
            "chain": f"{sw['kind']}>{ev['kind']}>{anchor['kind']}", "sweep_known_i": sw["known_i"],
            "break_known_i": k, "anchor_known_i": anchor["known_i"]})
    return setups, dict(sorted(stats.items()))


# ---------------------------------------------------------------- outcome book

def event_outcome(ev, bars, p=None):
    """Forward returns in ATR at fixed horizons, MFE/MAE over the longest horizon, net bps of a hypothetical market
    entry at the known close (directional events only). Only bars after known_i; a missing horizon is None."""
    p = params(**(p or {}))
    i0, n = ev["known_i"], len(bars)
    a = atr_at(bars, i0, p["atr_n"])
    c0 = bars[i0][4]
    d = ev["dir"] or 1
    res = {"ret_atr": {}, "net_bps": {}, "mfe_atr": None, "mae_atr": None, "atr": a}
    if a is None or a <= 0:
        return res
    for hz in p["horizons"]:
        if i0 + hz < n:
            r = bars[i0 + hz][4] - c0
            res["ret_atr"][hz] = d * r / a
            if ev["dir"]:
                res["net_bps"][hz] = d * r / c0 * 1e4 - p["cost_bps"]
        else:
            res["ret_atr"][hz] = None
            if ev["dir"]:
                res["net_bps"][hz] = None
    hmax = p["horizons"][-1]
    if i0 + hmax < n:
        hi = max(b[2] for b in bars[i0 + 1:i0 + hmax + 1])
        lo = min(b[3] for b in bars[i0 + 1:i0 + hmax + 1])
        res["mfe_atr"], res["mae_atr"] = ((hi - c0) / a, (c0 - lo) / a) if d > 0 else ((c0 - lo) / a, (hi - c0) / a)
    return res


def setup_outcome(s, bars, p=None):
    """Fill, then target or stop first. Conservative rules: a bar touching both stop and target is a stop (ambiguous =
    "target_first" exists only to bracket that rule's cost); on the fill bar only the stop counts; a limit fills at its price (no improvement); a gap through the stop exits at the open;
    a gap through the target exits at the target; a target reached before the fill cancels (missed)."""
    p = params(**(p or {}))
    d, entry, stop, target, risk = s["dir"], s["entry"], s["stop"], s["target"], s["risk"]
    i0, n = s["known_i"], len(bars)
    out = {"status": None, "fill_i": None, "exit_i": None, "exit_px": None, "both_hit_bars": 0,
           "gross_r": None, "net_r": None, "gross_bps": None, "net_bps": None, "mfe_atr": None, "mae_atr": None}

    def stop_px(o):
        return min(stop, o) if d > 0 else max(stop, o)

    if s["entry_mode"] == "market":
        fill = i0
    else:
        fill = None
        for j in range(i0 + 1, i0 + p["fill_window"] + 1):
            if j >= n:
                out["status"] = "incomplete"
                return out
            _, o, h, l, _, _ = bars[j]
            if (d > 0 and l <= entry) or (d < 0 and h >= entry):
                fill = j
                if (d > 0 and l <= stop) or (d < 0 and h >= stop):
                    out.update(status="stop", fill_i=j, exit_i=j, exit_px=stop_px(o))
                break
            if (d > 0 and h >= target) or (d < 0 and l <= target):
                out["status"] = "missed"
                return out
        if fill is None:
            out["status"] = "no_fill"
            return out
    out["fill_i"] = fill
    if out["status"] is None:
        for j in range(fill + 1, fill + p["max_hold"] + 1):
            if j >= n:
                out["status"] = "incomplete"
                return out
            _, o, h, l, _, _ = bars[j]
            hit_stop = (d > 0 and l <= stop) or (d < 0 and h >= stop)
            hit_tgt = (d > 0 and h >= target) or (d < 0 and l <= target)
            if hit_stop and hit_tgt:
                out["both_hit_bars"] += 1
                if p["ambiguous"] == "target_first":
                    hit_stop = False
            if hit_stop:
                out.update(status="stop", exit_i=j, exit_px=stop_px(o))
                break
            if hit_tgt:
                out.update(status="target", exit_i=j, exit_px=target)
                break
        if out["status"] is None:
            j = fill + p["max_hold"]
            out.update(status="timeout", exit_i=j, exit_px=bars[j][4])
    gross = d * (out["exit_px"] - entry)
    out["gross_r"] = gross / risk
    out["net_r"] = out["gross_r"] - p["cost_bps"] / 1e4 * entry / risk
    out["gross_bps"] = gross / entry * 1e4
    out["net_bps"] = out["gross_bps"] - p["cost_bps"]
    span = bars[fill + 1:out["exit_i"] + 1] if out["exit_i"] > fill else bars[fill:fill + 1]
    hi, lo = max(b[2] for b in span), min(b[3] for b in span)
    a = s["atr"]
    out["mfe_atr"], out["mae_atr"] = ((hi - entry) / a, (entry - lo) / a) if d > 0 else ((entry - lo) / a, (hi - entry) / a)
    return out


def farm(bars, p=None):
    """Events, setups, chain stats and the outcome book of one instrument."""
    p = params(**(p or {}))
    events = detect(bars, p)
    setups, chain_stats = build_setups(events, bars, p)
    return {"events": events, "setups": setups, "chain_stats": chain_stats,
            "event_outcomes": [event_outcome(e, bars, p) for e in events],
            "setup_outcomes": [setup_outcome(s, bars, p) for s in setups]}


# ---------------------------------------------------------------- daily study

def _day(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")


def known_day(ev, bar_seconds):
    """UTC date of the bar at which an event became known (known_ts is that bar's close, which may be 00:00 next day)."""
    return _day(ev["known_ts"] - bar_seconds)


def study(results, bars_by_inst, p=None):
    """Per UTC day (of the bar at which each event became known): counts per kind and chain, coverage per instrument, setup outcomes."""
    p = params(**(p or {}))
    per_day = 86400 // p["bar_seconds"]
    days = collections.defaultdict(lambda: {"kinds": collections.Counter(), "chains": collections.Counter(),
                                            "outcomes": collections.Counter(), "net_r": [], "bars": collections.Counter()})
    for inst in sorted(bars_by_inst):
        for b in bars_by_inst[inst]:
            days[_day(b[0])]["bars"][inst] += 1
        r = results[inst]
        for e in r["events"]:
            days[known_day(e, p["bar_seconds"])]["kinds"][e["kind"]] += 1
        for s, o in zip(r["setups"], r["setup_outcomes"]):
            dd = days[known_day(s, p["bar_seconds"])]
            dd["kinds"][s["kind"]] += 1
            dd["chains"][s["chain"]] += 1
            dd["outcomes"][o["status"]] += 1
            if o["net_r"] is not None:
                dd["net_r"].append(o["net_r"])
    out = {"instruments": sorted(bars_by_inst), "bars_per_full_day": per_day, "days": {}}
    for day in sorted(days):
        dd = days[day]
        out["days"][day] = {"kinds": dict(sorted(dd["kinds"].items())), "chains": dict(sorted(dd["chains"].items())),
                            "outcomes": dict(sorted(dd["outcomes"].items())),
                            "coverage": {i: dd["bars"][i] / per_day for i in out["instruments"]},
                            "net_r_sum": math.fsum(dd["net_r"]), "trades": len(dd["net_r"])}
    return out


def study_markdown(st, title="Event farm"):
    """A deterministic markdown overview: totals, vocabulary, coverage and the daily farm study."""
    days = st["days"]
    total = collections.Counter()
    for d in days.values():
        total.update(d["kinds"])
    n_ev = sum(total.values())
    lines = [f"# {title}", "",
             f"- dage: {len(days)}; instrumenter: {len(st['instruments'])} ({', '.join(st['instruments'])}); "
             f"hændelser: {n_ev}", "", "## Ordforråd", "", "| type | antal | pr. dag |", "|---|---:|---:|"]
    for k in sorted(total):
        lines.append(f"| {k} | {total[k]} | {total[k] / max(1, len(days)):.1f} |")
    lines += ["", "## Dækning og udfald pr. dag", "",
              "| dag | dækning | hændelser | setups | mål | stop | timeout | ingen fyld | misset | ufuldst. | netto R |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for day in sorted(days):
        d = days[day]
        cov = statistics.fmean(d["coverage"].values()) if d["coverage"] else 0.0
        o = d["outcomes"]
        setups = sum(v for k, v in d["kinds"].items() if k.startswith("setup_"))
        lines.append(f"| {day} | {100 * cov:.0f} % | {sum(d['kinds'].values())} | {setups} | {o.get('target', 0)} | "
                     f"{o.get('stop', 0)} | {o.get('timeout', 0)} | {o.get('no_fill', 0)} | {o.get('missed', 0)} | "
                     f"{o.get('incomplete', 0)} | {d['net_r_sum']:+.2f} |")
    lines += ["", "## Farm study pr. dag", ""]
    for day in sorted(days):
        d = days[day]
        kinds_txt = ", ".join(f"{k} {v}" for k, v in d["kinds"].items())
        chains_txt = ", ".join(f"{k} {v}" for k, v in d["chains"].items()) or "ingen"
        lines.append(f"- **{day}**: {kinds_txt}. Kæder: {chains_txt}.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- null test on a synthetic random walk

START = 1767571200                       # 2026-01-05 00:00 UTC, a synthetic calendar only


NULL_SIGMA_BAR, NULL_SUB_STEPS = 0.0011, 60     # ~11 bps per 5-minute bar; 5-second steps inside the bar


def random_walk_bars(seed, days, bar_seconds=300, sub_steps=NULL_SUB_STEPS, sigma_bar=NULL_SIGMA_BAR, start=START,
                     price=20000.0):
    """A driftless log random walk sampled in sub_steps per bar (no information by construction): o = previous close,
    h/l = the extremes of the sub-path, c = its end. A coarse sub-path (few steps) jumps through limit and stop prices,
    which biases fills (EVENT_FARM.md), so the null uses fine steps."""
    rng = random.Random(seed)
    sigma = sigma_bar / math.sqrt(sub_steps)
    bars, px = [], price
    for k in range(days * 86400 // bar_seconds):
        o = hi = lo = px
        for _ in range(sub_steps):
            px *= math.exp(rng.gauss(0.0, sigma))
            hi, lo = max(hi, px), min(lo, px)
        bars.append((start + k * bar_seconds, o, hi, lo, px, float(rng.randint(1, 1000))))
    return bars


VARIANTS = tuple({"anchor": an, "rr": rr, "entry_mode": em}
                 for an in ("fvg", "ob") for rr in (1.0, 2.0, 3.0) for em in ("mid", "market"))


def _variant_id(v):
    return f"{v['anchor']}/rr{v['rr']:g}/{v['entry_mode']}"


def _tstat(x):
    if len(x) < 2:
        return None
    sd = statistics.pstdev(x)
    return None if sd <= 1e-15 else statistics.fmean(x) / sd * math.sqrt(len(x))


def null_run(seed=83, instruments=3, days=60, p=None, costs=(0.0, 1.0, 5.0)):
    """Run the farm on pure noise. Returns counts per day, setup outcomes per variant (gross and net at each cost),
    and the daily net-R series per variant (for multiple testing). Deterministic for a given seed."""
    base = params(**(p or {}))
    bars_by = {f"RW{k + 1}": random_walk_bars(seed * 1000 + k, days, base["bar_seconds"]) for k in range(instruments)}
    results = {name: farm(b, base) for name, b in bars_by.items()}
    st = study(results, bars_by, base)
    n_days = len(st["days"])
    kind_tot = collections.Counter()
    for r in results.values():
        kind_tot.update(e["kind"] for e in r["events"])
    day_keys = sorted(st["days"])
    variants = {}
    series = []
    for v in VARIANTS:
        pv = params(**{**base, **v})
        gross_r, gross_bps, cost_r, status, daily = [], [], [], collections.Counter(), collections.Counter()
        bracket, both = [], 0
        ptf = params(**{**pv, "ambiguous": "target_first"})
        n_setups = 0
        for name, b in bars_by.items():
            setups, _ = build_setups(results[name]["events"], b, pv)
            n_setups += len(setups)
            for s in setups:
                o = setup_outcome(s, b, pv)
                status[o["status"]] += 1
                if o["gross_r"] is not None:
                    gross_r.append(o["gross_r"])
                    gross_bps.append(o["gross_bps"])
                    cost_r.append(1e-4 * s["entry"] / s["risk"])          # R cost of 1 bps round trip
                    daily[known_day(s, pv["bar_seconds"])] += o["net_r"]
                    both += o["both_hit_bars"] > 0
                    bracket.append(setup_outcome(s, b, ptf)["gross_r"])
        net = {}
        for cost in costs:
            vals = [g - cost * c for g, c in zip(gross_r, cost_r)]
            net[f"{cost:g}"] = {"mean_net_r": statistics.fmean(vals) if vals else None,
                                "t": _tstat(vals), "sum_net_r": math.fsum(vals)}
        variants[_variant_id(v)] = {
            "setups": n_setups, "setups_per_instrument_day": n_setups / max(1, n_days * instruments), "status": dict(sorted(status.items())),
            "trades": len(gross_r), "mean_gross_r": statistics.fmean(gross_r) if gross_r else None,
            "t_gross": _tstat(gross_r), "mean_gross_bps": statistics.fmean(gross_bps) if gross_bps else None,
            "hit_rate": status["target"] / max(1, status["target"] + status["stop"] + status["timeout"]), "net": net,
            "both_hit_trades": both, "mean_gross_r_target_first": statistics.fmean(bracket) if bracket else None}
        series.append([daily[d] for d in day_keys])
    pooled_gross = [v["mean_gross_r"] * v["trades"] for v in variants.values() if v["trades"]]
    pooled_bracket = [v["mean_gross_r_target_first"] * v["trades"] for v in variants.values() if v["trades"]]
    trades = sum(v["trades"] for v in variants.values())
    return {
        "seed": seed, "instruments": instruments, "days": n_days, "bars": sum(len(b) for b in bars_by.values()),
        "events": sum(kind_tot.values()), "events_per_instrument_day": sum(kind_tot.values()) / (instruments * n_days),
        "per_kind_per_instrument_day": {k: kind_tot[k] / (instruments * n_days) for k in sorted(kind_tot)},
        "chain_stats": {name: r["chain_stats"] for name, r in sorted(results.items())},
        "variants": variants, "pooled_mean_gross_r": math.fsum(pooled_gross) / trades if trades else None,
        "pooled_mean_gross_r_target_first": math.fsum(pooled_bracket) / trades if trades else None,
        "pooled_trades": trades, "series": series, "day_keys": day_keys, "costs": list(costs),
        "_bars": bars_by, "_results": results, "_study": st}


def lookahead_signal(p=None):
    """signal_fn for validation_engine.check_lookahead: a numeric digest per bar of the events and setups known at
    that bar. Truncating the future must not change any value up to the cut."""
    pp = params(**(p or {}))
    codes = {k: n + 1 for n, k in enumerate(kinds(pp))}

    def fn(bars):
        ev = detect(bars, pp)
        setups, _ = build_setups(ev, bars, pp)
        out = [0.0] * len(bars)
        for e in ev + setups:
            num = sum(v for k, v in sorted(e.items()) if k in ("level", "zone_lo", "zone_hi", "entry", "stop", "target")
                      and isinstance(v, float))
            out[e["known_i"]] += codes[e["kind"]] * 1000.0 + num + e["i"] * 1e-3
        return out
    return fn


# ---------------------------------------------------------------- validation and Register V2 (in code, not persisted)

def code_sha():
    with open(os.path.abspath(__file__), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _core(summary):
    return {k: v for k, v in summary.items() if not k.startswith("_") and k != "series"}


def v2_records(summary, p=None):
    """Two FUTURE records for the null run, validated in memory and never written: the setup-variant family and the
    descriptive event-kind x horizon family. Register V2 is the bookkeeping; nothing here is locked or charged."""
    from research.tools import factory, register_v2 as v2
    pp = params(**(p or {}))
    first, last = summary["day_keys"][0], summary["day_keys"][-1]
    src = {"name": "syntetisk log-random walk (event_farm.random_walk_bars), ingen markedsdata",
           "sha256": factory.sha({"seed": summary["seed"], "instruments": summary["instruments"], "days": summary["days"],
                                  "sigma_bar": NULL_SIGMA_BAR, "sub_steps": NULL_SUB_STEPS,
                                  "bar_seconds": pp["bar_seconds"]})}
    params_block = v2.parameters_block({k: (list(v) if isinstance(v, tuple) else v) for k, v in sorted(pp.items())
                                        if k != "sessions"} | {"sessions": [list(x) for x in pp["sessions"]]})
    cost = {"name": "parametriseret rundtur (ANTAGELSE)", "round_trip_bps": pp["cost_bps"],
            "sha256": factory.sha({"cost_bps": pp["cost_bps"], "grid": summary["costs"]})}
    result_sha = factory.sha(_core(summary))
    kinds_base = [k for k in kinds(pp) if not k.startswith("setup_")]
    event_family = [f"{k}@{h}" for k in kinds_base for h in pp["horizons"]]
    setup_family = [_variant_id(v) for v in VARIANTS]
    recs = []
    for rid, fam, method in (
            ("EVENT_FARM_NULL_SETUPS", setup_family, "netto R pr. setup, dagssummer, blok-bootstrap max-t over familien"),
            ("EVENT_FARM_NULL_EVENTS", event_family, "beskrivende fremadrettet afkast i ATR pr. type og horisont")):
        recs.append(v2.record(
            rid, v2.FUTURE, hypothesis_id=rid, lineage="event_farm/ICT-SMC-mærkning (beskrivende, null)",
            trial_universe={"definition": f"{len(fam)} varianter: {fam[0]} .. {fam[-1]}", "size": len(fam),
                            "members_sha256": factory.sha(fam)},
            variants_tested={"count": len(fam), "artifact": "event_farm.null_run i hukommelsen (ikke persisteret)",
                             "sha256": result_sha},
            parameters=params_block, code_hash=code_sha(), data_source=src,
            data_period={"start": first, "end": last}, cost_model=cost,
            evaluation_method={"name": method, "sha256": factory.sha(method)},
            data_quality={"status": "NOT_CHECKED"}, deviations=[]))
    return recs


def validate_null(summary, p=None, floor_cost_bps=1.0, lookahead_bars=2000):
    """validation_engine on the null run: lookahead (truncation invariance), multiple testing over the setup variants,
    and costs on the pooled gross edge. A diagnostic; it decides nothing."""
    from research.tools import validation_engine as ve
    pp = params(**(p or {}))
    bars = next(iter(summary["_bars"].values()))[:lookahead_bars]
    look = ve.check_lookahead(signal_fn=lookahead_signal(pp), data=bars, n_checks=20)
    n = len(VARIANTS)
    mt = ve.check_multiple_testing(series=summary["series"], time_index=list(range(len(summary["day_keys"]))),
                                   n_tested=n, n_preregistered=n, n_reported=n, reps=999, seed=83)
    trades = [(v["mean_gross_bps"], v["trades"]) for v in summary["variants"].values() if v["trades"]]
    gross_bps = math.fsum(m * t for m, t in trades) / max(1, sum(t for _, t in trades))
    costs = ve.check_costs(gross_bps_per_trade=gross_bps, assumed_cost_bps=pp["cost_bps"], floor_cost_bps=floor_cost_bps)
    return {"lookahead": look, "multiple_testing": mt, "costs": costs,
            "assess": ve.assess([look, mt, costs], required=(ve.LOOKAHEAD, ve.MULTIPLE_TESTING, ve.COSTS))}


def null_markdown(summary, checks=None):
    lines = [f"# Event farm null (seed {summary['seed']}, {summary['instruments']} instrumenter, {summary['days']} dage, "
             f"{summary['bars']} barer)", "",
             f"- hændelser: {summary['events']} ({summary['events_per_instrument_day']:.1f} pr. instrument-dag)",
             f"- puljet brutto R pr. handel over alle varianter: {summary['pooled_mean_gross_r']:+.4f} "
             f"({summary['pooled_trades']} handler); med target_first-parentes: "
             f"{summary['pooled_mean_gross_r_target_first']:+.4f}", "", "| type | pr. instrument-dag |", "|---|---:|"]
    for k, v in summary["per_kind_per_instrument_day"].items():
        lines.append(f"| {k} | {v:.2f} |")
    costs = [f"{c:g}" for c in summary["costs"]]
    lines += ["", "| variant | setups pr. instr.-dag | handler | mål-andel | begge-ramt | brutto R | brutto R (target_first) | t | brutto bps | "
              + " | ".join(f"netto R @{c} bps" for c in costs) + " |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|" + "---:|" * len(costs)]
    for vid, v in summary["variants"].items():
        g = "n/a" if v["mean_gross_r"] is None else f"{v['mean_gross_r']:+.3f}"
        t = "n/a" if v["t_gross"] is None else f"{v['t_gross']:+.2f}"
        gb = "n/a" if v["mean_gross_bps"] is None else f"{v['mean_gross_bps']:+.2f}"
        nets = " | ".join("n/a" if v["net"][c]["mean_net_r"] is None else f"{v['net'][c]['mean_net_r']:+.3f}" for c in costs)
        tf = "n/a" if v["mean_gross_r_target_first"] is None else f"{v['mean_gross_r_target_first']:+.3f}"
        lines.append(f"| {vid} | {v['setups_per_instrument_day']:.2f} | {v['trades']} | {v['hit_rate']:.2f} | {v['both_hit_trades']} | "
                     f"{g} | {tf} | {t} | {gb} | {nets} |")
    if checks:
        lines += ["", "## validation_engine", ""]
        for name in ("lookahead", "multiple_testing", "costs"):
            c = checks[name]
            lines.append(f"- {name}: {c['status']}: {c['reason']}")
        lines.append(f"- samlet: {checks['assess']['status']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Event farm null run on a synthetic random walk (stdout only).")
    ap.add_argument("--seed", type=int, default=83)
    ap.add_argument("--instruments", type=int, default=3)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--study", action="store_true", help="also print the daily farm study")
    a = ap.parse_args(argv)
    s = null_run(a.seed, a.instruments, a.days)
    checks = validate_null(s)
    print(null_markdown(s, checks))
    for rec in v2_records(s):
        print(f"V2 {rec['record_id']}: varianter {rec['variants_tested']['count']}, univers {rec['trial_universe']['size']}")
    if a.study:
        print(study_markdown(s["_study"], "Event farm (syntetisk støj)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
