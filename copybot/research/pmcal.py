"""pmcal_v1: kalibrering af Polymarket-kontrakter i halerne, præcis som research/PMCAL_SPEC.md.

  python -m research.pmcal fetch dev       hent udvikling + validering (metadata + daglig prishistorik, SHA-256)
  python -m research.pmcal dev             vælg konfiguration på udvikling, tjek validering, beregn n_req
  python -m research.pmcal fetch holdout   kræver committet research/PMCAL_FROZEN.md
  python -m research.pmcal holdout         åbner holdout én gang; kræver committet PMCAL_FROZEN.md

Kun offentlige, læse-only API'er. Ingen konto, ingen wallet, ingen ordrer.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "research", "pmcal")
GAMMA, CLOB = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
HOUR, DAY = 3600, 86400

PERIODS = {"dev": ("2024-01-01", "2025-12-31"), "val": ("2026-01-01", "2026-06-30"),
           "holdout": ("2026-07-01", "2026-10-16")}
CONFIGS = {"F7": (7, "fav"), "F1": (1, "fav"), "L7": (7, "long"), "L1": (1, "long")}
FAV, LONG = (0.80, 0.95), (0.05, 0.20)
MIN_VOL, MIN_VOL_SENS = 10_000.0, 1_000.0
SHORT = re.compile(r"up or down|\bup/down\b|price of .* (above|below) .* on|bitcoin above|ethereum above", re.I)
CRYPTO = re.compile(r"bitcoin|btc|ethereum|\beth\b|solana|crypto|xrp|doge", re.I)
BASE = {"s": 0.005, "f": 0.05, "f_crypto": 0.07}
HIGH = {"s": 0.015, "f": 0.07, "f_crypto": 0.07}
Z_A, Z_B = 3.0233, 0.8416                 # en-sidet alpha 0.005/4, styrke 80 %


# ---------- tid ----------
def ts(s):
    """ISO-dato/-tid eller Polymarkets '2024-01-01 20:32:09+00' -> unix sekunder (UTC)."""
    if not s:
        return None
    s = s.strip().replace(" ", "T").replace("Z", "+00:00")
    if re.search(r"[+-]\d\d$", s):
        s += ":00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())


def week_of(t):
    y, w, _ = datetime.fromtimestamp(t, timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


# ---------- marked-regler (§3) ----------
def loads(x):
    if isinstance(x, list):
        return x
    try:
        return json.loads(x) if x else None
    except (TypeError, ValueError):
        return None


def slim(m):
    """De felter spec'en (§2) bruger."""
    ev = (m.get("events") or [{}])[0]
    return {"id": int(m["id"]), "question": m.get("question") or "", "outcomes": loads(m.get("outcomes")),
            "outcomePrices": loads(m.get("outcomePrices")), "clobTokenIds": loads(m.get("clobTokenIds")),
            "createdAt": m.get("createdAt"), "closedTime": m.get("closedTime"), "endDate": m.get("endDate"),
            "volumeNum": m.get("volumeNum"), "event": str(ev.get("id") or m["id"]),
            "event_title": ev.get("title") or "", "event_slug": ev.get("slug") or ""}


def static_reason(m, min_vol):
    """§3 punkt 1-2. None = ok, ellers grund til udelukkelse."""
    if not m["outcomes"] or len(m["outcomes"]) != 2:
        return "not_binary"
    if not m["clobTokenIds"] or len(m["clobTokenIds"]) != 2:
        return "no_order_book"
    if (m["volumeNum"] or 0) < min_vol:
        return "volume"
    if SHORT.search(m["question"]):
        return "short_price_market"
    if ts(m["endDate"]) is None:
        return "no_end_date"
    return None


def date_reason(m, h):
    """§3 punkt 4, datodelen."""
    te = ts(m["endDate"]) - h * DAY
    c, cl = ts(m["createdAt"]), ts(m["closedTime"])
    if c is None or c > te - DAY:
        return "created_too_late"
    if cl is None:
        return "no_closed_time"
    if cl <= te:
        return "closed_before_entry"
    return None


def entry_price(hist, te):
    """§3.4: punkt p1 i (te-36 t, te] og p0 <= t(p1)-20 t. Returnerer pris for udfald 0 eller None."""
    if not hist:
        return None
    pts = sorted((int(x["t"]), float(x["p"])) for x in hist if "t" in x and "p" in x)
    p1 = None
    for t, p in pts:
        if t <= te:
            p1 = (t, p)
        else:
            break
    if p1 is None or p1[0] <= te - 36 * HOUR:
        return None
    if not any(t <= p1[0] - 20 * HOUR for t, _ in pts):
        return None
    return p1[1]


def payout(m, idx):
    """Endelig udbetaling for udfald idx (§3.6); None hvis ikke afgjort til 0 / 0.5 / 1."""
    op = m["outcomePrices"]
    if not op or len(op) != 2:
        return None
    try:
        y = float(op[idx])
    except (TypeError, ValueError):
        return None
    for v in (0.0, 0.5, 1.0):
        if abs(y - v) <= 0.01:
            return v
    return None


def select(markets, h, min_vol, hist_of):
    """Ét marked pr. event (§3.5): laveste id blandt dem der består punkt 1-4.

    hist_of(token) -> prishistorik. Returnerer (marked, pris for udfald 0, D-tæller) eller (None, None, D-tæller).
    D-tæller: (prøvet-første-dato-åbne, havde-punkter) for det første dato-åbne marked i eventet.
    """
    d_first = None
    for m in sorted(markets, key=lambda x: x["id"]):
        if static_reason(m, min_vol) or date_reason(m, h):
            continue
        p = entry_price(hist_of(m["clobTokenIds"][0]), ts(m["endDate"]) - h * DAY)
        if d_first is None:
            d_first = p is not None
        if p is not None:
            return m, p, d_first
    return None, None, d_first


def fee_rate(m, scen):
    txt = " ".join((m["question"], m["event_title"], m["event_slug"]))
    return scen["f_crypto"] if CRYPTO.search(txt) else scen["f"]


def cost(q, m, scen):
    return q + scen["s"] + fee_rate(m, scen) * q * (1 - q)


def side_for(p0, kind):
    """(udfaldsindeks, pris) for favorit- eller longshot-siden; p0 = pris for udfald 0."""
    fav = 0 if p0 >= 0.5 else 1
    idx = fav if kind == "fav" else 1 - fav
    return idx, (p0 if idx == 0 else 1 - p0)


def random_side(event_id):
    return int(hashlib.sha256(str(event_id).encode()).hexdigest(), 16) % 2


def run(events, config, scen=BASE, min_vol=MIN_VOL, hist_of=None, baseline=False):
    """events: {event_id: [markeder]}. Returnerer (rækker, udelukkelser, D=(n, ok))."""
    h, kind = CONFIGS[config]
    lo, hi = FAV if kind == "fav" else LONG
    rows, excl, d = [], collections.Counter(), [0, 0]
    for ev in sorted(events):
        m, p0, d_first = select(events[ev], h, min_vol, hist_of)
        if d_first is not None:
            d[0] += 1
            d[1] += int(d_first)
        if m is None:
            excl["no_eligible_market"] += 1
            continue
        idx, q = side_for(p0, kind)
        if not lo <= q <= hi:
            excl["outside_bucket"] += 1
            continue
        if baseline:
            idx = random_side(ev)
            q = p0 if idx == 0 else 1 - p0
        y = payout(m, idx)
        if y is None:
            excl["unresolved_or_bad_payout"] += 1
            continue
        c = cost(q, m, scen)
        end = ts(m["endDate"])
        rows.append({"event": ev, "market": m["id"], "end": end, "week": week_of(end), "q": q, "y": y, "c": c,
                     "r": (y - c) / c, "crypto": bool(CRYPTO.search(" ".join((m["question"], m["event_title"],
                                                                                 m["event_slug"]))))})
    return rows, excl, d


# ---------- statistik ----------
def cluster_lb(rows, q=0.005, n=10000, seed=5):
    """Nedre kvantil af middel-r ved bootstrap over opløsningsuger (clusters)."""
    wk = collections.defaultdict(lambda: [0.0, 0])
    for r in rows:
        wk[r["week"]][0] += r["r"]
        wk[r["week"]][1] += 1
    cl = list(wk.values())
    if len(cl) < 2:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        s = k = 0
        for a, b in rng.choices(cl, k=len(cl)):
            s += a
            k += b
        means.append(s / k)
    means.sort()
    return means[int(q * n)]


def n_req(mean, sd):
    if mean is None or mean <= 0 or not sd:
        return None
    return math.ceil(((Z_A + Z_B) * sd / mean) ** 2)


def summarize(rows, bootstrap=True):
    r = [x["r"] for x in sorted(rows, key=lambda x: (x["end"], x["event"]))]
    if not r:
        return {"events": 0, "total_net": 0.0, "mean": None, "sd": None, "lb_99_5": None, "thirds": [],
                "win_rate": None, "mean_price": None, "max_dd": 0.0, "weeks": 0}
    eq = peak = dd = 0.0
    for x in r:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    t = len(r) // 3
    return {"events": len(r), "total_net": sum(r), "mean": statistics.mean(r),
            "sd": statistics.stdev(r) if len(r) > 1 else None,
            "lb_99_5": cluster_lb(rows) if bootstrap else None,
            "thirds": [sum(r[:t]), sum(r[t:2 * t]), sum(r[2 * t:])] if t else [],
            "win_rate": sum(1 for x in rows if x["y"] == 1.0) / len(rows),
            "mean_price": statistics.mean(x["q"] for x in rows),
            "mean_cost": statistics.mean(x["c"] for x in rows), "max_dd": dd,
            "weeks": len({x["week"] for x in rows})}


def calibration(rows, edges=(0.05, 0.10, 0.15, 0.20, 0.80, 0.85, 0.90, 0.95)):
    out = {}
    for a, b in zip(edges, edges[1:]):
        sel = [x for x in rows if a <= x["q"] < b or (b == edges[-1] and x["q"] == b)]
        if sel:
            out[f"{a:.2f}-{b:.2f}"] = {"n": len(sel), "implied": statistics.mean(x["q"] for x in sel),
                                       "observed": statistics.mean(x["y"] for x in sel)}
    return out


def gates(s, base, high, nreq, d):
    return {
        "D datatjek >= 90 %": d[0] > 0 and d[1] / d[0] >= 0.90,
        "G1 total netto > 0": s["total_net"] > 0,
        "G2 nedre 99,5 % grænse > 0": (s["lb_99_5"] if s["lb_99_5"] is not None else -1) > 0,
        "G3 events >= n_req": nreq is not None and s["events"] >= nreq,
        "G4 middel > tilfældig side": s["mean"] is not None and base["mean"] is not None and s["mean"] > base["mean"],
        "G5 netto > 0 med høje omk.": high["total_net"] > 0,
        "G6 positiv i >= 2 af 3 tredjedele": sum(1 for x in s["thirds"] if x > 0) >= 2,
    }


# ---------- data ----------
def get(url):
    for i in range(8):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception:
            if i == 7:
                raise
            time.sleep(2 * (i + 1))


def save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    raw = json.dumps(obj, sort_keys=True).encode()
    with open(os.path.join(DATA, name + ".json"), "wb") as f:
        f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def load(name):
    with open(os.path.join(DATA, name + ".json"), "rb") as f:
        raw = f.read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def fetch_markets(period, min_vol, log=print):
    a, b = PERIODS[period]
    out, cur = [], None
    while True:
        url = (f"{GAMMA}/markets/keyset?closed=true&limit=500&volume_num_min={int(min_vol)}"
               f"&end_date_min={a}T00:00:00Z&end_date_max={b}T23:59:59Z"
               + (f"&after_cursor={urllib.parse.quote(cur)}" if cur else ""))
        r = get(url)
        out += [slim(m) for m in r.get("markets") or []]
        cur = r.get("next_cursor")
        if not cur or not r.get("markets"):
            break
        if len(out) % 20000 < 500:
            log(f"  {period}: {len(out)} markeder")
    return out


def group(markets, period):
    a, b = ts(PERIODS[period][0]), ts(PERIODS[period][1]) + DAY
    ev = collections.defaultdict(list)
    for m in markets:
        e = ts(m["endDate"])
        if e is not None and a <= e < b:
            ev[m["event"]].append(m)
    return ev


def fetch_histories(events, min_vols, hist, log=print):
    """Henter daglig historik dovent i id-rækkefølge pr. event, for hver horisont og volumen-grænse."""
    lock = threading.Lock()

    def hist_of(tok):
        with lock:
            if tok in hist:
                return hist[tok]
        h = get(f"{CLOB}/prices-history?market={tok}&interval=max&fidelity=1440").get("history", [])
        with lock:
            hist[tok] = h
        return h

    def one(ev):
        for h in {c[0] for c in CONFIGS.values()}:
            for mv in min_vols:
                select(events[ev], h, mv, hist_of)

    keys = sorted(events)
    with ThreadPoolExecutor(8) as ex:
        for i, _ in enumerate(ex.map(one, keys)):
            if i % 5000 == 0:
                log(f"  historik: {i}/{len(keys)} events, {len(hist)} tokens")
    return hist


def fetch(which, log=print):
    periods = ("dev", "val") if which == "dev" else ("holdout",)
    if which == "holdout" and frozen() is None:
        raise SystemExit("research/PMCAL_FROZEN.md skal være committet (uden ændringer) før holdout-data hentes")
    min_vols = (MIN_VOL,) if which == "dev" else (MIN_VOL, MIN_VOL_SENS)
    man = {"fetched": int(time.time()), "git": git_head(), "files": {}}
    for p in periods:
        mk = fetch_markets(p, min(min_vols), log)
        man["files"]["markets_" + p] = save("markets_" + p, mk)
        log(f"{p}: {len(mk)} markeder")
        hist = fetch_histories(group(mk, p), min_vols, {}, log)
        man["files"]["histories_" + p] = save("histories_" + p, hist)
        log(f"{p}: {len(hist)} historikker")
    save("manifest_" + which, man)


def from_cache(period):
    mk, h1 = load("markets_" + period)
    hist, h2 = load("histories_" + period)
    return group(mk, period), (lambda tok: hist.get(tok)), {"markets_" + period: h1, "histories_" + period: h2}


# ---------- git ----------
def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return None


def frozen():
    p = os.path.join(HERE, "research", "PMCAL_FROZEN.md")
    try:
        dirty = subprocess.check_output(["git", "status", "--porcelain", p], cwd=HERE, text=True).strip()
        tracked = subprocess.check_output(["git", "ls-files", p], cwd=HERE, text=True).strip()
    except Exception:
        return None
    if dirty or not tracked:
        return None
    vals = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            if ":" in line and line.split(":")[0] in ("config", "n_req"):
                k, v = (x.strip() for x in line.split(":", 1))
                vals[k] = v if k == "config" else (None if v == "none" else int(v))
    return vals if vals.get("config") in CONFIGS and "n_req" in vals else None


# ---------- kommandoer ----------
def report(rows, excl, d):
    return {"summary": summarize(rows), "exclusions": dict(excl), "data_check": {"n": d[0], "ok": d[1]},
            "calibration": calibration(rows)}


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    out = os.path.join(HERE, "data", "research", "results")
    os.makedirs(out, exist_ok=True)
    if cmd == "fetch":
        fetch(args[1] if len(args) > 1 else "")
        return
    if cmd == "dev":
        dev_ev, dev_h, h1 = from_cache("dev")
        val_ev, val_h, h2 = from_cache("val")
        dev = {c: report(*run(dev_ev, c, hist_of=dev_h)) for c in CONFIGS}
        ok = [c for c in CONFIGS if dev[c]["summary"]["mean"] is not None]
        best = max(ok, key=lambda c: dev[c]["summary"]["mean"]) if ok else None
        res = {"version": "pmcal_v1_dev", "built": int(time.time()), "git": git_head(), "dev": dev, "config": best,
               "data_hashes": {**h1, **h2}}
        if best:
            vrows, vex, vd = run(val_ev, best, hist_of=val_h)
            drows = run(dev_ev, best, hist_of=dev_h)[0]
            both = [x["r"] for x in drows + vrows]
            m = statistics.mean(both) if both else None
            sd = statistics.stdev(both) if len(both) > 1 else None
            vmean = summarize(vrows, False)["mean"]
            res.update({"validation": report(vrows, vex, vd),
                        "validation_random_side": summarize(run(val_ev, best, hist_of=val_h, baseline=True)[0]),
                        "dev_val_mean": m, "dev_val_sd": sd, "n_req": n_req(m, sd),
                        "dev_mean_positive": dev[best]["summary"]["mean"] > 0,
                        "validation_mean_positive": vmean is not None and vmean > 0})
        json.dump(res, open(os.path.join(out, "pmcal_v1_dev.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in res.items() if k != "data_hashes"}, indent=1, default=str))
    elif cmd == "holdout":
        fz = frozen()
        if fz is None:
            raise SystemExit("research/PMCAL_FROZEN.md skal være committet (uden ændringer) før holdout åbnes")
        ev, hf, hashes = from_cache("holdout")
        cfg, nreq = fz["config"], fz["n_req"]
        rows, excl, d = run(ev, cfg, hist_of=hf)
        s = summarize(rows)
        base = summarize(run(ev, cfg, hist_of=hf, baseline=True)[0])
        high = summarize(run(ev, cfg, HIGH, hist_of=hf)[0], False)
        wk = collections.defaultdict(float)
        for x in rows:
            wk[x["week"]] += x["r"]
        res = {"version": "pmcal_v1", "built": int(time.time()), "git": git_head(), "period": PERIODS["holdout"],
               "config": cfg, "n_req": nreq, **report(rows, excl, d), "random_side": base, "high_cost": high,
               "gates": gates(s, base, high, nreq, d),
               "not_selected_configs": {c: summarize(run(ev, c, hist_of=hf)[0], False) for c in CONFIGS if c != cfg},
               "by_category": {"crypto": summarize([x for x in rows if x["crypto"]], False),
                               "other": summarize([x for x in rows if not x["crypto"]], False)},
               "sensitivity_min_volume_1k": summarize(run(ev, cfg, min_vol=MIN_VOL_SENS, hist_of=hf)[0], False),
               "weekly": dict(sorted(wk.items())), "rows": rows, "data_hashes": hashes}
        json.dump(res, open(os.path.join(out, "pmcal_v1.json"), "w", encoding="utf-8"), indent=1)
        print(json.dumps({k: v for k, v in res.items() if k not in ("rows", "data_hashes", "weekly")}, indent=1,
                         default=str))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
