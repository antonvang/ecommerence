"""Data coverage, source health and the hypothesis register (research/AUDIT_2026-10-20.md points 2, 3 and 5). DISPLAY
ONLY: it reads the registry and the market cache's file names, downloads nothing, opens no key and changes no gate.

Every source row says what the lab has (period and files from the cache, rows from the observation chain), what it
costs and whether a key is needed; data classes the lab does not have are listed as gaps, never filled in.
"""
from __future__ import annotations

import json
import os
import re
import time

from lab.engine import data as mdata

DAY = 86400
# name, kind, content, resolution, cost, key, cache subdirectories, source prefix (datasets for history: the
# registered read windows; observations for live), seconds after which a live source counts as stale
SOURCES = (
    ("Binance USD-M (data.binance.vision)", "history", "perp klines + funding", "1 h", "free", "no",
     ("klines", "funding"), None, None),
    ("Binance spot (data.binance.vision)", "history", "spot klines", "1 h", "free", "no", ("spot_klines",), None,
     None),
    ("Binance metrics (data.binance.vision)", "history", "open interest, long/short ratios", "5 min", "free", "no",
     ("metrics", "metrics_daily"), "https://data.binance.vision/data/futures/um/daily/metrics", None),
    ("Deribit DVOL", "history", "BTC/ETH implied volatility index", "1 d", "free", "no", ("dvol",),
     "https://www.deribit.com", None),
    ("Coinmetrics community", "history", "MVRV, supply", "1 d", "free", "no", ("coinmetrics",),
     "https://community-api.coinmetrics.io", None),
    ("FRED", "history", "DFII10 real rate", "1 d", "free", "no", ("fred",), "https://fred.stlouisfed.org", None),
    ("DefiLlama stablecoins", "history", "stablecoin supply", "1 d", "free", "no", ("stable",),
     "https://stablecoins.llama.fi", None),
    ("Binance aggTrades (amendment 14)", "history", "trades per hour by size class (<1k, 1k-10k, 10k-100k, >=100k USD)",
     "1 h", "free", "no", ("ingest/aggtrades_1h",), None, None),
    ("Binance bookDepth (amendment 14)", "history", "notional at +-1..5 % from the mid, mean and minimum", "1 h",
     "free", "no", ("ingest/bookdepth_1h",), None, None),
    ("Wikipedia pageviews (amendment 14)", "history", "daily human views of 11 crypto articles (attention proxy)",
     "1 d", "free", "no", ("ingest/pageviews",), None, None),
    ("FOMC and BLS calendar (amendment 14)", "history", "scheduled FOMC, CPI and jobs-report times (no figures)",
     "event", "free", "no", ("ingest/calendar",), None, None),
    ("Binance fapi premiumIndex (live)", "live", "mark/index premium, predicted funding", "60 s",
     "free (weight limit 2,400/min)", "no", (), "https://fapi.binance.com/fapi/v1/premiumIndex", 900),
    ("Hyperliquid info (live)", "live", "predicted funding, mids, books", "60 s", "free (1,200 weight/min)", "no", (),
     "https://api.hyperliquid.xyz/info", 900),
    ("Polymarket Gamma/CLOB (live)", "live", "events, liquidity rewards", "per scan (about 40 min)", "free", "no", (),
     "https://gamma-api.polymarket.com", 7200),
)
GAPS = (
    ("news articles and headlines", "licensed feeds need a key or payment; GDELT's free API allows one request per "
                                    "5 s; Wikipedia pageviews are the proxy (amendment 14)", "ask the user before any "
                                                                                              "key or payment"),
    ("released macro figures (CPI value, surprise)", "only the scheduled times are fetched (amendment 14 point 1)",
     "not fetched"),
    ("liquidations history", "no free historical source on data.binance.vision", "not available free"),
    ("trade history beyond the pilot", "pilot: 8 coins in 2023 (amendment 14); all 32 coins 2020-2023 are 151 GB "
                                       "zipped (measured 2026-10-20)", "needs the user's yes (budget 10 GB)"),
    ("full historical order books", "bookDepth gives aggregate depth at +-1..5 % from 2023 only; no levels or queue",
     "not available free"),
    ("Hyperliquid history", "live API only (fundingHistory per coin), not cached", "free, not fetched"),
    ("data after 2023-12", "2024 not fetched; 2025-01-01 onwards is reserved and never read", "reserved"),
)
_MONTH = re.compile(r"(\d{4}-\d{2})(?:-\d{2})?\.(?:zip|csv\.gz)$")


_SCANNED = {}
SCAN_TTL_S = 300                                  # the cache only grows by explicit downloads: rescan every 5 min


def _cache(sub, root=None, now=None):
    d = os.path.join(root or mdata.CACHE, sub)
    now = now or time.time()
    hit = _SCANNED.get(d)
    if hit and now - hit[0] < SCAN_TTL_S:
        return hit[1]
    _SCANNED[d] = (now, _scan(d))
    return _SCANNED[d][1]


def _scan(d):
    if not os.path.isdir(d):
        return {"files": 0, "first": None, "last": None, "coins": 0, "mtime": None}
    months, coins, n, mt = [], set(), 0, None
    for base, _dirs, files in os.walk(d):
        for name in files:
            if name.endswith(".lock"):
                continue
            n += 1
            mt = max(mt or 0, os.stat(os.path.join(base, name)).st_mtime)
            m = _MONTH.search(name)
            if m:
                months.append(m.group(1))
            coins.add(name.split("-")[0])
    return {"files": n, "first": min(months) if months else None, "last": max(months) if months else None,
            "coins": len(coins), "mtime": mt}


def _fetch_pauses(db, now):
    rows = db.q("SELECT ts, payload FROM events WHERE kind='risk.pause' AND ts>=?", int(now - DAY))
    out = []
    for r in rows:
        p = json.loads(r["payload"] or "{}")
        if p.get("rule") == "data_fetch":
            out.append({"ts": r["ts"], "detail": (p.get("detail") or "")[:160]})
    return out


def sources(db, now=None, root=None):
    """One row per source: coverage from the cache or the observation chain, last seen, rows in 24 h, and health."""
    now = now or time.time()
    obs = {r["source"]: dict(r) for r in db.q(
        "SELECT source, MAX(ts) last_ts, SUM(CASE WHEN ts>=? THEN 1 ELSE 0 END) n_24h, "
        "SUM(CASE WHEN ts>=? AND metric='error' THEN 1 ELSE 0 END) errors_24h FROM observations GROUP BY source",
        int(now - DAY), int(now - DAY))}
    windows = [dict(r) for r in db.q("SELECT source, MIN(window_start) a, MAX(window_end) b, COUNT(*) n "
                                      "FROM datasets GROUP BY source")]
    rows = []
    for name, kind, content, res, cost, key, subs, prefix, stale_s in SOURCES:
        row = {"source": name, "kind": kind, "content": content, "resolution": res, "cost": cost, "key_needed": key}
        if subs:
            parts = [_cache(s, root, now) | {"dir": s} for s in subs]
            firsts = [p["first"] for p in parts if p["first"]]
            lasts = [p["last"] for p in parts if p["last"]]
            files = sum(p["files"] for p in parts)
            row |= {"files": files, "coins": max((p["coins"] for p in parts), default=0),
                    "period": f"{min(firsts)} .. {max(lasts)}" if firsts else None, "parts": parts,
                    "last_ts": max((p["mtime"] or 0 for p in parts), default=0) or None,
                    "health": "cached" if files else "pending" if subs[0].startswith("ingest/") else "missing"}
            w = [x for x in windows if prefix and (x["source"] or "").startswith(prefix)]
            if w:
                a, b = min(x["a"] for x in w), max(x["b"] for x in w)
                row |= {"registered_reads": sum(x["n"] for x in w),
                        "read_window": f"{time.strftime('%Y-%m-%d', time.gmtime(a))} .. "
                                       f"{time.strftime('%Y-%m-%d', time.gmtime(b))}"}
                row["period"] = row["period"] or row["read_window"]
        else:
            m = [v for s, v in obs.items() if s and s.startswith(prefix)]
            last = max((v["last_ts"] for v in m), default=None)
            n = sum(v["n_24h"] or 0 for v in m)
            err = sum(v["errors_24h"] or 0 for v in m)
            age = (now - last) if last else None
            row |= {"rows_24h": n, "errors_24h": err, "last_ts": last, "age_s": age,
                    "health": ("never seen" if last is None else "stale" if age > stale_s else
                               "errors" if err else "ok")}
        rows.append(row)
    from lab import ingest
    return {"sources": rows, "ingest": ingest.status(db), "gaps": [{"data": g, "why": w, "status": s} for g, w, s in GAPS],
            "fetch_pauses_24h": _fetch_pauses(db, now),
            "paid_sources_active": 0, "keys_used": 0,
            "note": "free public sources only; no key or payment is used. Reserved data from 2025-01-01 is never read."}


def _head(verdict):
    v = (verdict or "").split(":")[0].split("(")[0].strip().upper()
    return v.split()[0] if v else "NO RESULT"


def hypotheses(db):
    """One row per mechanism (deduplicated by mechanism_tag): experiments, variants tested, latest verdict, alpha
    spent; plus the multiple-testing totals and the exploration lane's own count (exploratory, not decisional). An
    experiment in a final lifecycle state (REJECTED, RETIRED, WITHDRAWN) counts as REJECTED whatever its last result
    row says; PASS here is a screening step, never documented profitability."""
    from lab import lifecycle
    latest = {}
    for r in db.q("SELECT exp_id, verdict, ts FROM results ORDER BY id"):
        latest[r["exp_id"]] = (r["verdict"], r["ts"])
    trials = {r["exp_id"]: r["n"] for r in db.q("SELECT exp_id, COUNT(DISTINCT variant) n FROM trials GROUP BY exp_id")}
    alpha = {r["exp_id"]: r["a"] for r in db.q("SELECT exp_id, SUM(alpha) a FROM alpha_ledger GROUP BY exp_id")}
    mech = {}
    for r in db.q("SELECT exp_id, mechanism_tag, spec_json, created_ts FROM experiments ORDER BY id"):
        tag = r["mechanism_tag"] or "untagged"
        m = mech.setdefault(tag, {"mechanism": tag, "experiments": [], "variants_tested": 0, "alpha_spent": 0.0,
                                  "hypothesis": None, "first_ts": r["created_ts"]})
        if r["exp_id"] in [e["exp_id"] for e in m["experiments"]]:
            continue                                   # a later version of the same experiment
        try:
            spec = json.loads(r["spec_json"] or "{}")
        except ValueError:
            spec = {}
        h = spec.get("hypothesis")
        if isinstance(h, dict):
            h = h.get("statement") or h.get("text") or json.dumps(h)[:200]
        m["hypothesis"] = (h or m["hypothesis"] or spec.get("title"))
        v, ts = latest.get(r["exp_id"], (None, None))
        st = lifecycle.state(db, r["exp_id"])
        head = _head(v)
        if st in lifecycle.FINAL:                  # a later rejection/retirement overrides an earlier screening verdict
            head = "REJECTED"
        m["experiments"].append({"exp_id": r["exp_id"], "verdict": head, "verdict_text": (v or "")[:200],
                                 "verdict_ts": ts, "state": st})
        m["variants_tested"] += trials.get(r["exp_id"], 0)
        m["alpha_spent"] += alpha.get(r["exp_id"], 0.0)
    rows = []
    for m in mech.values():
        heads = [e["verdict"] for e in m["experiments"]]
        status = next((h for h in ("PASS", "OBSERVE", "RUNNING", "INCONCLUSIVE", "INSUFFICIENT") if h in heads), None)
        m["status"] = status or ("REJECTED" if all(h in ("REJECTED", "FAIL", "INVALID", "NOT") for h in heads)
                                 else heads[-1] if heads else "NO RESULT")
        if isinstance(m["hypothesis"], str):
            m["hypothesis"] = m["hypothesis"][:300]
        rows.append(m)
    order = {"PASS": 0, "OBSERVE": 1, "RUNNING": 2, "INCONCLUSIVE": 3, "INSUFFICIENT": 4}
    rows.sort(key=lambda m: (order.get(m["status"], 9), m["mechanism"]))
    lane = 0
    for r in db.q("SELECT payload FROM events WHERE kind='research.explore'"):
        try:
            lane += int(json.loads(r["payload"] or "{}").get("evaluated") or 0)
        except (ValueError, TypeError):
            pass
    counts = {}
    for m in rows:
        counts[m["status"]] = counts.get(m["status"], 0) + 1
    return {"mechanisms": rows, "total_mechanisms": len(rows),
            "total_experiments": sum(len(m["experiments"]) for m in rows),
            "total_variants_tested": sum(m["variants_tested"] for m in rows),
            "alpha_spent": sum(m["alpha_spent"] for m in rows), "by_status": counts,
            "lane_variants_evaluated": lane, "lane_reviews": lane_multiple_testing(db),
            "multiple_testing": "formal tests spend alpha from the ledger (amendment 8); the exploration lane is "
                                "exploratory, never decisional, and its candidates must pass lane_review (15) and a "
                                "separate forward test"}


LANE_ALPHA = 0.10                     # amendment 11c/11d/15: placebo p < 0.10 per candidate
FDR_Q = 0.10


def lane_multiple_testing(db, method=None):
    """Display only, decides nothing: how many lane reviews pass by the per-candidate rule, how many chance alone would
    pass, and how many survive Benjamini-Hochberg at q = 0.10 with the conservative permutation p (k + 1) / (n + 1).
    Candidates overlap (variants of one family on shared coins), so the tests are dependent and both figures are
    approximate."""
    from lab import lane
    method = method or lane.REVIEW_METHOD
    ps = []
    for r in db.q("SELECT payload FROM events WHERE kind='research.lane_review'"):
        try:
            d = json.loads(r["payload"] or "{}")
        except ValueError:
            continue
        if d.get("method") != method or d.get("placebo_p") is None:
            continue
        n = int(d.get("placebo_n") or lane.REVIEW_PLACEBO_N)    # the review records p only; n is the lane's fixed n
        ps.append(((round(d["placebo_p"] * n) + 1) / (n + 1), d.get("ok"), d.get("key")))
    m = len(ps)
    fam = {}
    for _p, ok, k in ps:
        f = (k or "?").split(":")[0]
        x = fam.setdefault(f, {"family": f, "tests": 0, "passed": 0})
        x["tests"] += 1
        x["passed"] += bool(ok)
    bh = 0
    for i, (p, _ok, _k) in enumerate(sorted(ps), 1):
        if p <= FDR_Q * i / m:
            bh = i
    return {"method": method, "tests": m, "passed_rule": sum(1 for _p, ok, _k in ps if ok),
            "expected_by_chance": round(m * LANE_ALPHA, 1), "bh_q": FDR_Q, "bh_significant": bh,
            "by_function": sorted(fam.values(), key=lambda x: -x["passed"]), "placebo_n_assumed": lane.REVIEW_PLACEBO_N,
            "note": "per-candidate rule p < 0.10; BH with p = (k+1)/(n+1). The candidates are overlapping variants of "
                    "few functions on shared coins: dependent tests, not independent edges. A pass means timing value "
                    "in explore0 (2020-21), not profit now"}
