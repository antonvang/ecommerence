"""PROTOCOL_V3 amendment 22: K3 - price pressure around funding settlement, a forward screening.

Every 4-hour settlement S: the coins are chosen at S - 35 min from the predicted funding (point in time), their marks are
stored from the per-minute premiumIndex fetch premium-watch already makes, in the real window S +- 35 min and the placebo
window S + 2 h +- 35 min, and entry/exit books are read for the traded groups. Endpoints are chosen on Binance's own mark
time and never interpolated. No statistic before 60 valid rounds on 20 UTC days per direction; then one look, frozen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
import time
import urllib.parse

DET = "k3/1"
RULE = "research/PROTOCOL_V3.md amendment 22"
H = 3600
ROUND_S, WIN_S, PLACEBO_SHIFT_S = 4 * H, 35 * 60, 2 * H
SELECT_S, ENTRY_S, EXIT_S, LATE_S = 35 * 60, 31 * 60, 60, 120     # a book later than LATE_S after its time is not read
HIGH_MIN, LOW_MAX, CTRL_MAX, GROUP_N = 0.0005, -0.0005, 0.0001, 10  # predicted funding per 8 h
FRESH_S = 90
MIN_COINS, MIN_ROUNDS, MIN_DAYS, P_MAX, P_PLACEBO = 3, 60, 20, 0.005, 0.05
FEE, C_FLOOR, BOOK_SIZES = 0.0005, 0.0046, (1_000, 5_000)
DEADLINE = dt.date(2027, 3, 31)
DEADLINE_END = int(dt.datetime(2027, 4, 1, tzinfo=dt.timezone.utc).timestamp())   # F point 3: the end of 2027-03-31
BTC = "BTCUSDT"
BN = "https://fapi.binance.com"
GROUPS = ("high", "low", "control")

_SEEN = set()          # (S, window, symbol, binance time) written by this process; a restart may repeat one (D point 3)
_BOOKS = set()         # (S, phase) read by this process


def _p(raw):
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def signal(x, intervals):
    """Predicted funding per 8 h (12i): lastFundingRate x 8 / the symbol's settlement interval in hours."""
    return float(x["lastFundingRate"]) * 8 / intervals.get(x["symbol"], 8)


def selection(db, S):
    r = db.one("SELECT ts, payload FROM observations WHERE detector=? AND metric='selection' AND value=? ORDER BY id "
               "LIMIT 1", DET, S)
    return None if r is None else {**_p(r["payload"]), "select_ts": r["ts"]}


def select(db, S, now, rows, intervals, perps, delisted):
    """C point 3: HIGH, LOW and CONTROL from the coins settling at S, stored before any later price is known."""
    sig, iv = {}, {}
    for x in rows:
        s = x.get("symbol")
        if s not in perps or s == BTC or x.get("lastFundingRate") in (None, "") or not x.get("nextFundingTime"):
            continue
        if int(x["nextFundingTime"]) // 1000 != S or (s[:-4] if s.endswith("USDT") else s) in delisted:
            continue
        sig[s], iv[s] = signal(x, intervals), intervals.get(s, 8)
    high = sorted((s for s in sig if sig[s] >= HIGH_MIN), key=lambda s: (-sig[s], s))[:GROUP_N]
    low = sorted((s for s in sig if sig[s] <= LOW_MAX), key=lambda s: (sig[s], s))[:GROUP_N]
    pool = sorted(s for s in sig if 0 <= sig[s] <= CTRL_MAX)
    ctrl = sorted(random.Random(S).sample(pool, min(GROUP_N, len(pool))))
    chosen = high + low + ctrl
    payload = {"S": S, "groups": {"high": high, "low": low, "control": ctrl},
               "signal": {s: sig[s] for s in chosen}, "interval_h": {s: iv[s] for s in chosen},
               "n_eligible": len(sig), "rule": RULE + " C"}
    db.append("observations", ts=int(now), detector=DET, source=f"{BN}/fapi/v1/premiumIndex", instrument="round",
              metric="selection", value=S, threshold=None, flagged=0, payload=payload)
    return {**payload, "select_ts": int(now)}


def _once(db, metric, S, now, payload=None):
    if db.one("SELECT 1 FROM observations WHERE detector=? AND metric=? AND value=?", DET, metric, S):
        return
    db.append("observations", ts=int(now), detector=DET, source="k3", instrument="round", metric=metric, value=S,
              threshold=None, flagged=0, payload={"S": S, "rule": RULE, **(payload or {})})


def book(get, sym):
    """D point 4: round trips through the current book (fees excluded); None when 100 levels cannot fill the size."""
    from lab import moves
    d = get(f"{BN}/fapi/v1/depth?symbol={urllib.parse.quote(sym)}&limit=100")
    bids = [(float(p), float(q)) for p, q in d.get("bids") or []]
    asks = [(float(p), float(q)) for p, q in d.get("asks") or []]
    if not bids or not asks:
        return {"error": "empty book"}
    mid = (bids[0][0] + asks[0][0]) / 2
    out = {}
    for s in BOOK_SIZES:
        buy, sell = moves.walk(asks, s), moves.walk(bids, s)
        out[f"rt_{s}"] = None if buy is None or sell is None else (buy - sell) / mid
    return out


def _books(db, S, phase, syms, get, now):
    for s in syms:
        try:
            b = book(get, s)
        except Exception as e:                                   # noqa: BLE001 - a missing book censors, never guesses
            b = {"error": f"{e!r}"[:200]}
        db.append("observations", ts=int(now), detector=DET, source=f"{BN}/fapi/v1/depth", instrument=s, metric="book",
                  value=b.get("rt_5000"), threshold=None, flagged=0, payload={"S": S, "phase": phase, **b})


def observe(db, now, rows, intervals, perps, get, delisted=lambda now: {}):
    """One premium-watch pass: select, store marks and read books for the rounds whose windows contain `now`."""
    now = int(now)
    by = {x.get("symbol"): x for x in rows}
    done = {"selected": 0, "marks": 0, "books": 0, "missed": 0}
    base = now - now % ROUND_S
    for S in (base - ROUND_S, base, base + ROUND_S):
        for window, centre in (("real", S), ("placebo", S + PLACEBO_SHIFT_S)):
            if not centre - WIN_S <= now <= centre + WIN_S:
                continue
            sel = selection(db, S)
            if sel is None:
                if window == "real" and S - SELECT_S <= now < S - ENTRY_S:
                    sel = select(db, S, now, rows, intervals, perps, delisted(now))
                    done["selected"] += 1
                else:
                    if window == "real":
                        _once(db, "missed", S, now, {"why": "no premium-watch pass between S-35 and S-31 min"})
                        done["missed"] += 1
                    continue
            g = sel["groups"]
            members = [(s, k) for k in GROUPS for s in g[k]]
            if window == "placebo":                              # D point 2: hourly settlers settle at S + 2 h
                members = [(s, k) for s, k in members if sel["interval_h"].get(s, 8) != 1]
            members.append((BTC, "btc"))
            with db.tx():
                for s, k in members:
                    x = by.get(s)
                    if not x or not x.get("markPrice") or not x.get("time"):
                        continue
                    key = (S, window, s, int(x["time"]))
                    if key in _SEEN:
                        continue
                    _SEEN.add(key)
                    db.append("observations", ts=now, detector=DET, source=f"{BN}/fapi/v1/premiumIndex", instrument=s,
                              metric="mark", value=float(x["markPrice"]), threshold=None, flagged=0,
                              payload={"S": S, "window": window, "group": k, "time": int(x["time"]),
                                       "index": x.get("indexPrice"), "rate": x.get("lastFundingRate"),
                                       "next_ts": int(x["nextFundingTime"]) // 1000 if x.get("nextFundingTime") else None})
                    done["marks"] += 1
            if window == "real":
                traded = g["high"] + g["low"]
                for phase, t in (("entry", S - ENTRY_S), ("exit", S - EXIT_S)):
                    if traded and t <= now <= t + LATE_S and (S, phase) not in _BOOKS and not db.one(
                            "SELECT 1 FROM observations WHERE detector=? AND metric='book' AND "
                            "json_extract(payload, '$.S')=? AND json_extract(payload, '$.phase')=?", DET, S, phase):
                        _BOOKS.add((S, phase))
                        _books(db, S, phase, traded, get, now)
                        done["books"] += len(traded)
    return done


# ---------------- analysis (amendment 22 E and F) ----------------

def _series(db, S, window):
    out = {}
    for r in db.q("SELECT instrument, value, payload FROM observations WHERE detector=? AND metric='mark' AND "
                  "json_extract(payload, '$.S')=? AND json_extract(payload, '$.window')=?", DET, S, window):
        p = _p(r["payload"])
        out.setdefault(r["instrument"], {})[p["time"] / 1000] = (r["value"], p.get("next_ts"))   # duplicates count once
    return out


def endpoint(series, target):
    """D point 3: the mark with the latest Binance time t, target - 90 s < t <= target; None if there is none."""
    ts = [t for t in series if target - FRESH_S < t <= target]
    return series[max(ts)][0] if ts else None


def _ret(series, a, b):
    x, y = endpoint(series, a), endpoint(series, b)
    return None if x is None or y is None or x <= 0 or y <= 0 else math.log(y / x)


def round_values(db, S, sel, window="real"):
    """Per group: {symbol: {"r_pre", "r_post", "v", "c"}} with BTC correction; coins without both endpoints are dropped."""
    centre = S if window == "real" else S + PLACEBO_SHIFT_S
    ser = _series(db, S, window)
    btc = ser.get(BTC, {})
    b_pre, b_post = _ret(btc, centre - ENTRY_S, centre - EXIT_S), _ret(btc, centre + EXIT_S, centre + ENTRY_S)
    books = {}
    if window == "real":
        for r in db.q("SELECT instrument, payload FROM observations WHERE detector=? AND metric='book' AND "
                      "json_extract(payload, '$.S')=? AND json_extract(payload, '$.phase')='entry'", DET, S):
            books.setdefault(r["instrument"], _p(r["payload"]))
    out = {k: {} for k in GROUPS}
    for k in GROUPS:
        for s in sel["groups"][k]:
            if window == "placebo" and sel["interval_h"].get(s, 8) == 1:
                continue
            m = ser.get(s, {})
            if window == "real":                                  # C point 4: an interval change drops the coin
                last = [m[t][1] for t in sorted(m) if t <= S - EXIT_S]
                if last and last[-1] != S:
                    continue
            raw_pre = _ret(m, centre - ENTRY_S, centre - EXIT_S)
            raw_post = _ret(m, centre + EXIT_S, centre + ENTRY_S)
            if raw_pre is None or b_pre is None:
                continue
            rt = books.get(s, {}).get("rt_5000")
            v = None if k == "control" else (-raw_pre if k == "high" else raw_pre)
            out[k][s] = {"r_pre": raw_pre - b_pre,
                         "r_post": None if raw_post is None or b_post is None else raw_post - b_post,
                         "v": v if rt is not None else None,
                         "c": max(C_FLOOR, 2 * (2 * FEE + rt)) if rt is not None else None}
    return out


def _mean(xs):
    return sum(xs) / len(xs)


def rounds(db, cutoff, window="real"):
    """Per selected round complete by `cutoff`: {"S", "d_high", "d_low", "v_high", "c_high", "v_low", "c_low"}."""
    out = []
    for r in db.q("SELECT value, ts, payload FROM observations WHERE detector=? AND metric='selection' ORDER BY value",
                  DET):
        S = int(r["value"])
        end = (S if window == "real" else S + PLACEBO_SHIFT_S) + ENTRY_S
        if end > cutoff:
            continue
        sel = {**_p(r["payload"]), "select_ts": r["ts"]}
        g = round_values(db, S, sel, window)
        row = {"S": S, "day": dt.datetime.fromtimestamp(S, dt.timezone.utc).date().isoformat()}
        ctrl = [x["r_pre"] for x in g["control"].values()]
        for k in ("high", "low"):
            vals = [x["r_pre"] for x in g[k].values()]
            row[f"d_{k}"] = (_mean(vals) - _mean(ctrl)) if len(vals) >= MIN_COINS and len(ctrl) >= MIN_COINS else None
            tr = [x for x in g[k].values() if x["v"] is not None]
            row[f"v_{k}"] = _mean([x["v"] for x in tr]) if tr else None
            row[f"c_{k}"] = _mean([x["c"] for x in tr]) if tr else None
        out.append(row)
    return out


def _t_greater(xs):
    from lab import k1k2
    return k1k2.t_greater(xs)


def evaluate(real, placebo):
    """E: verdict per direction from round lists (d_high is predicted < 0, d_low > 0)."""
    from lab import k1k2
    res, ps = {}, []
    for k, sgn in (("high", -1), ("low", 1)):
        d = [sgn * r[f"d_{k}"] for r in real if r[f"d_{k}"] is not None]
        res[k] = {"n_rounds": len(d), "mean": _mean(d) if d else None, "p": _t_greater(d) if len(d) >= 2 else None}
        ps.append(res[k]["p"] if res[k]["p"] is not None else 1.0)
    for k, adj in zip(("high", "low"), k1k2.holm(ps)):
        sgn = -1 if k == "high" else 1
        pd = [sgn * r[f"d_{k}"] for r in placebo if r[f"d_{k}"] is not None]
        pp = _t_greater(pd) if len(pd) >= 2 else None
        placebo_ok = len(pd) >= MIN_ROUNDS and (pp is None or pp > P_PLACEBO)
        tr = [r for r in real if r[f"v_{k}"] is not None]
        v, c = (_mean([r[f"v_{k}"] for r in tr]), _mean([r[f"c_{k}"] for r in tr])) if tr else (None, None)
        tradable = v is not None and v >= c
        mech = adj <= P_MAX and placebo_ok
        res[k].update({"holm_p": adj, "placebo_rounds": len(pd), "placebo_p": pp, "placebo_ok": placebo_ok,
                       "v_mean": v, "c_mean": c, "tradable": tradable,
                       "verdict": "PASS" if mech and tradable else
                       "SCREEN_FAIL (mekanisme bekræftet, ikke handlebar)" if mech else "SCREEN_FAIL"})
    return res


def counts(db, cutoff):
    real = rounds(db, cutoff)
    out = {"selected": db.one("SELECT COUNT(*) FROM observations WHERE detector=? AND metric='selection'", DET)[0],
           "missed": db.one("SELECT COUNT(*) FROM observations WHERE detector=? AND metric='missed'", DET)[0],
           "complete": len(real)}
    for k in ("high", "low"):
        ok = [r for r in real if r[f"d_{k}"] is not None]
        out[k] = {"valid_rounds": len(ok), "days": len({r["day"] for r in ok})}
    return out, real


def maybe_freeze(db, now=None):
    """F point 2: once per direction, at the first UTC day end where both minimums hold; never recomputed."""
    now = int(now or time.time())
    cutoff = min(now - now % 86400, DEADLINE_END)            # F point 3: nothing after the deadline ever counts
    done = {_p(r["payload"]).get("direction") for r in db.q("SELECT payload FROM events WHERE kind='research.k3_result'")}
    c, real = counts(db, cutoff)
    out = {}
    for k in ("high", "low"):
        if k in done or c[k]["valid_rounds"] < MIN_ROUNDS or c[k]["days"] < MIN_DAYS:
            continue
        res = evaluate(real, rounds(db, cutoff, "placebo"))[k]
        body = {"direction": k, "cutoff": cutoff, "counts": c[k], "result": res, "rule": RULE + " E/F"}
        body["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        db.event("research.k3_result", "system:k3", None, body)
        out[k] = res["verdict"]
    return out


# ---------------- per-round data-quality audit (amendment 22 precision 2) ----------------

def audit_round(db, S, window, now):
    """Counts only for one round and window; status gyldig / ugyldig / karantæne. Never a return or a mean."""
    sel = selection(db, S)
    if sel is None:
        return None
    centre = S if window == "real" else S + PLACEBO_SHIFT_S
    rows = db.q("SELECT ts, instrument, payload FROM observations WHERE detector=? AND metric='mark' AND "
                "json_extract(payload, '$.S')=? AND json_extract(payload, '$.window')=?", DET, S, window)
    passes = sorted({r["ts"] for r in rows})
    keys = [(r["instrument"], _p(r["payload"])["time"]) for r in rows]
    members = [s for k in GROUPS for s in sel["groups"][k]
               if window == "real" or sel["interval_h"].get(s, 8) != 1] + [BTC]
    ser = _series(db, S, window)
    ends = {"m-31": centre - ENTRY_S, "m-1": centre - EXIT_S, "m+1": centre + EXIT_S, "m+31": centre + ENTRY_S}
    coins, max_age, deviations = {}, 0.0, []
    for s in members:
        m = ser.get(s, {})
        missing = [n for n, t in ends.items() if endpoint(m, t) is None]
        for t in ends.values():
            ts = [x for x in m if t - FRESH_S < x <= t]
            if ts:
                max_age = max(max_age, t - max(ts))
        last = [m[t][1] for t in sorted(m) if t <= S - EXIT_S] if window == "real" and s != BTC else []   # C point 4
        changed = bool(last) and last[-1] != S
        if missing or changed:
            coins[s] = {"missing": missing, "interval_change": changed}
    out = {"S": S, "window": window, "passes": len(passes),
           "max_gap_s": max((b - a for a, b in zip(passes, passes[1:])), default=None), "rows": len(rows),
           "duplicates": len(keys) - len(set(keys)), "coins_expected": len(members),
           "coins_present": len({r["instrument"] for r in rows}), "coins_with_problems": coins,
           "max_endpoint_age_s": max_age, "rule": RULE + " precision 2"}
    if window == "real":
        off = sel["select_ts"] - S
        out["selection_offset_s"] = off
        if not -SELECT_S <= off < -ENTRY_S:
            deviations.append(f"udvælgelse {off} s fra S (skal være i [-2100, -1860))")
        books = {"entry": {"ok": 0, "error": 0, "censored": 0}, "exit": {"ok": 0, "error": 0, "censored": 0}}
        for r in db.q("SELECT ts, payload FROM observations WHERE detector=? AND metric='book' AND "
                      "json_extract(payload, '$.S')=?", DET, S):
            b = _p(r["payload"])
            ph = b.get("phase")
            if ph not in books:
                continue
            books[ph]["error" if b.get("error") else "censored" if b.get("rt_5000") is None else "ok"] += 1
            t0 = S - (ENTRY_S if ph == "entry" else EXIT_S)
            if not t0 <= r["ts"] <= t0 + LATE_S:
                deviations.append(f"{ph}-bog læst {r['ts'] - t0} s efter sit tidspunkt")
        out["books"] = books
    else:
        hourly = sorted({r["instrument"] for r in rows if sel["interval_h"].get(r["instrument"], 8) == 1})   # stored
        if hourly:
            deviations.append(f"timeafregnede mønter i placebo: {hourly}")
    if max_age > FRESH_S:
        deviations.append(f"endepunkt {max_age:.0f} s gammelt")
    g = round_values(db, S, sel, window)
    ok = {k: len(g[k]) >= MIN_COINS and len(g["control"]) >= MIN_COINS for k in ("high", "low")}
    out["directions_valid"] = ok
    out["deviations"] = sorted(set(deviations))
    out["status"] = "karantæne" if deviations else "gyldig" if all(ok.values()) else "ugyldig"
    db.append("observations", ts=int(now), detector=DET, source="k3", instrument="round", metric="round_audit",
              value=S, threshold=None, flagged=int(bool(deviations)), payload=out)
    return out


def maybe_audit(db, now=None):
    """Audit every selected round whose window has closed and has no audit yet (called from the hourly scanner)."""
    now = int(now or time.time())
    done = {(int(r["value"]), _p(r["payload"]).get("window"))
            for r in db.q("SELECT value, payload FROM observations WHERE detector=? AND metric='round_audit'", DET)}
    out = []
    for r in db.q("SELECT value FROM observations WHERE detector=? AND metric='selection' ORDER BY value", DET):
        S = int(r["value"])
        for window, end in (("real", S + WIN_S), ("placebo", S + PLACEBO_SHIFT_S + WIN_S)):
            if end < now and (S, window) not in done:
                a = audit_round(db, S, window, now)
                if a:
                    out.append((S, window, a["status"]))
    return out


def audit_view(db, last=6):
    rows = [_p(r["payload"]) for r in db.q("SELECT payload FROM observations WHERE detector=? AND "
                                           "metric='round_audit' ORDER BY id", DET)]
    counts = {}
    for a in rows:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    brief = [{k: a.get(k) for k in ("S", "window", "status", "passes", "max_gap_s", "duplicates", "coins_expected",
                                     "coins_present", "max_endpoint_age_s", "directions_valid", "deviations",
                                     "books", "coins_with_problems")} for a in rows[-last:]]
    return {"counts": counts, "latest": brief, "rule": RULE + " precision 2", "note": "kun datakvalitet; ingen afkast"}


def status(db, now=None):
    """Counts only until a frozen result exists (F point 2)."""
    now = int(now or time.time())
    c, _ = counts(db, min(now, DEADLINE_END))
    frozen = {_p(r["payload"])["direction"]: _p(r["payload"]) for r in db.q(
        "SELECT payload FROM events WHERE kind='research.k3_result' ORDER BY id")}
    late = dt.datetime.fromtimestamp(now, dt.timezone.utc).date() > DEADLINE
    out = {"rule": RULE, "counts": c, "needed": {"rounds": MIN_ROUNDS, "days": MIN_DAYS}, "directions": {},
           "audit": audit_view(db)}
    for k in ("high", "low"):
        if k in frozen:
            out["directions"][k] = {"status": frozen[k]["result"]["verdict"], "frozen": frozen[k]["sha256"]}
        else:
            out["directions"][k] = {"status": "UNTESTABLE" if late else "NO_DECISION",
                                    "why": f"{c[k]['valid_rounds']} af {MIN_ROUNDS} runder, {c[k]['days']} af "
                                           f"{MIN_DAYS} døgn; ingen statistik før (ændring 22 F)"}
    return out
