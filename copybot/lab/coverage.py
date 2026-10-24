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
    ("Binance announcements (amendment 16)", "live", "listings, delistings, exchange news (publisher time)", "10 min",
     "free", "no", (), "https://www.binance.com/bapi/composite", 2 * 86400),
    ("Cointelegraph RSS (amendment 16)", "live", "crypto news headlines", "10 min", "free", "no", (),
     "https://cointelegraph.com", 86400),
    ("CoinDesk RSS (amendment 16)", "live", "crypto news headlines", "10 min", "free", "no", (),
     "https://www.coindesk.com", 86400),
    ("Federal Reserve press releases RSS (amendment 21b)", "live", "FOMC statements and Board releases (headlines)",
     "10 min", "free", "no", (), "https://www.federalreserve.gov/feeds", 30 * 86400),
    ("BLS latest numbers RSS (amendment 21b)", "live", "CPI, jobs and other indicator releases (headlines)", "10 min",
     "free", "no", (), "https://www.bls.gov/feed", 14 * 86400),
    ("ECB press releases RSS (amendment 21b)", "live", "ECB decisions, speeches and releases (headlines)", "10 min",
     "free", "no", (), "https://www.ecb.europa.eu", 3 * 86400),
    ("CNBC Economy RSS (amendment 21b)", "live", "economy and macro news headlines", "10 min", "free", "no", (),
     "https://www.cnbc.com", 3 * 86400),
    ("Binance fapi klines, 12 markets (amendment 21)", "live", "hourly bars of crypto and TradFi perps for abnormal "
     "moves", "1 h", "free (weight limit 2,400/min)", "no", (), "https://fapi.binance.com/fapi/v1/klines", 3 * 3600),
    ("CoinMetrics community exchange flows (amendment 21q)", "live", "btc/eth daily exchange inflow, outflow and "
     "exchange supply; point-in-time only from 2026-10-24 (the free series are revised)", "1 d (polled every 6 h)",
     "free, CC BY-NC 4.0", "no", (), "https://community-api.coinmetrics.io/v4/timeseries", 2 * 86400),
    ("GDELT DOC 2.0 (amendment 16)", "live", "world news mentioning crypto (titles, URLs)", "30 min, backoff to 24 h",
     "free, but limits this address (HTTP 429, amendment 17 point 9)", "no", (), "https://api.gdeltproject.org", 86400),
)
GAPS = (
    ("news history before amendment 16", "RSS and GDELT are collected forward only; Binance announcements are "
                                         "backfilled from their own timestamps; licensed archives need a key or "
                                         "payment", "ask the user before any key or payment"),
    ("released macro figures (CPI value, surprise)", "only the scheduled times are fetched (amendment 14 point 1)",
     "not fetched"),
    ("liquidations history", "no free historical source on data.binance.vision", "not available free"),
    ("trade history beyond the pilot", "pilot: 8 coins in 2023 (amendment 14); all 32 coins 2020-2023 are 151 GB "
                                       "zipped (measured 2026-10-20)", "needs the user's yes (budget 10 GB)"),
    ("full historical order books", "bookDepth gives aggregate depth at +-1..5 % from 2023 only; no levels or queue",
     "not available free"),
    ("Hyperliquid history", "live API only (fundingHistory per coin), not cached", "free, not fetched"),
    ("data after 2023-12", "2024 not fetched; 2025-01-01 onwards is reserved and never read", "reserved"),
    ("hourly FX, rates and index data (amendment 21)", "BLOCKED: no hourly source on the allowed hosts (FRED is "
                                                       "daily and lagged); only USDBRL and SPY/QQQ perps exist",
     "a new data host needs the user's yes"),
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


ERROR_RECENT_S = 2 * 3600             # a source is "errors" only with an error this recent; older ones stay counted


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
        "SELECT source, MAX(CASE WHEN metric NOT IN ('error', 'news_error', 'onchain_error') THEN ts END) last_ts, "
        "SUM(CASE WHEN ts>=? THEN 1 ELSE 0 END) n_24h, "
        "SUM(CASE WHEN ts>=? AND metric IN ('error', 'news_error', 'onchain_error') THEN 1 ELSE 0 END) errors_24h, "
        "MAX(CASE WHEN metric IN ('error', 'news_error', 'onchain_error') THEN ts END) last_err FROM observations "
        "GROUP BY source",
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
            last = max((v["last_ts"] for v in m if v["last_ts"]), default=None)        # data rows only, not errors
            n = sum(v["n_24h"] or 0 for v in m)
            err = sum(v["errors_24h"] or 0 for v in m)
            last_err = max((v["last_err"] or 0 for v in m), default=0) or None
            age = (now - last) if last else None
            recent = last_err is not None and now - last_err < ERROR_RECENT_S     # an outage hours ago is not a problem now
            failing = last_err is not None and last is not None and last_err > last and age > ERROR_RECENT_S
            row |= {"rows_24h": n, "errors_24h": err, "last_ts": last, "age_s": age, "last_error_ts": last_err,
                    "health": ("never seen" if last is None else "failing" if failing else "stale" if age > stale_s
                               else "errors" if recent else "ok")}
        rows.append(row)
    from lab import ingest
    return {"sources": rows, "ingest": ingest.status(db), "gaps": [{"data": g, "why": w, "status": s} for g, w, s in GAPS],
            "fetch_pauses_24h": _fetch_pauses(db, now), "progress": progress(db, rows, now),
            "paid_sources_active": 0, "keys_used": 0,
            "note": "free public sources only; no key or payment is used. Reserved data from 2025-01-01 is never read."}


def progress(db, rows=None, now=None):
    """Display only (the user's directive point 7): results, not activity. Hours of the last 24 with data per live
    source, jobs finished and failed in 24 h, the age of the oldest job that could run now, and every recorded
    measurement with its verdict."""
    now = now or time.time()
    hours = {r["source"]: r["h"] for r in db.q(
        "SELECT source, COUNT(DISTINCT ts / 3600) h FROM observations WHERE ts>=? AND metric NOT IN "
        "('error', 'news_error', 'onchain_error') GROUP BY source", int(now - DAY))}
    live = []
    for row in rows or []:
        if row.get("kind") == "live":
            pre = next((x[7] for x in SOURCES if x[0] == row["source"]), None)
            h = max((v for k, v in hours.items() if k and pre and k.startswith(pre)), default=0)
            live.append({"source": row["source"], "hours_with_data_24h": min(24, h)})
    try:
        j = db.one("SELECT SUM(CASE WHEN status='done' THEN 1 ELSE 0 END), SUM(CASE WHEN status='failed' THEN 1 "
                   "ELSE 0 END) FROM jobs WHERE updated_ts>=?", now - DAY)
        oldest = db.one("SELECT MIN(created_ts) FROM jobs WHERE status='queued' AND next_run<=?", now)[0]
    except Exception:                                       # noqa: BLE001 - no jobs table yet
        j, oldest = (0, 0), None
    meas = []
    for r in db.q("SELECT ts, payload FROM events WHERE kind='research.measurement' ORDER BY id"):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        meas.append({"hypothesis": p.get("hypothesis"), "name": p.get("name"), "verdict": p.get("verdict"),
                     "reason": (p.get("reason") or "")[:160], "ts": r["ts"], "rule": p.get("rule")})
    return {"live_sources": live, "jobs_done_24h": j[0] or 0, "jobs_failed_24h": j[1] or 0,
            "oldest_runnable_job_age_s": (now - oldest) if oldest else None, "measurements": meas,
            "forward": forward(db, now), "hypotheses": _hypotheses(db, now)}


def _hypotheses(db, now):
    """Amendment 17's pipeline (display only); a failure here never hides the rest of the page."""
    try:
        from lab import hypogen
        return hypogen.view(db, now)
    except Exception as e:                                  # noqa: BLE001
        return {"error": repr(e)[:200]}


FORWARD_FROM = 1792627200                       # 2026-10-22 00:00 UTC: amendments 16d and 16f collect from here
FORWARD_TESTS = (("H5F", "16d", 20, 60 * DAY), ("H5X", "16f", 20, 7 * DAY))   # (id, amendment, symbols, window)
M1F_FROM = 1792886400                           # 2026-10-25 00:00 UTC: amendment 17j point 2
M1F_RX = re.compile(r"Extend the Monitoring Tag to (?:Include )?(.+?)(?:,? and Remove|,? Remove| on \d{4}-\d{2}-\d{2}|$)")
M1F_STABLE = {"USDT", "USDC", "FDUSD", "DAI", "TUSD", "USDE", "USD1", "PYUSD", "EURC", "AEUR", "EURI", "BTC"}   # 3c


def forward(db, now=None):
    """Display only: the locked forward tests (16d, 16f) and how many USD-M listing announcements news-watch has
    collected for them so far. The final sample rules (no earlier funding, a Hyperliquid perp, full windows) are applied
    once, when the measurement runs; this counts candidates."""
    now = now or time.time()
    coins = {}
    for r in db.q("SELECT payload FROM observations WHERE detector='news/1' AND metric='news_item' AND ts>=? "
                  "ORDER BY ts, rowid", FORWARD_FROM):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        t = p.get("title") or ""
        if p.get("backfill") or p.get("category") != "listing" or (p.get("fetched_ts") or 0) < FORWARD_FROM \
                or "Futures Will Launch" not in t or "Perpetual" not in t or "Coin-Margined" in t \
                or "TradFi" in t:                       # precision of 16d/16f (2026-10-24): not a crypto listing
            continue
        for c in p.get("coins") or []:
            coins.setdefault(c, p.get("published_ts") or p.get("fetched_ts"))
    first = sorted(coins.items(), key=lambda x: (x[1], x[0]))
    out = []
    for hid, amendment, n, window in FORWARD_TESTS:
        nth = first[n - 1][1] if len(first) >= n else None
        out.append({"hypothesis": hid, "rule": f"research/PROTOCOL_V3.md amendment {amendment}", "needed": n,
                    "collected": min(len(first), n), "coins": [c for c, _ in first[:n]],
                    "earliest_run_ts": nth + window if nth else None, "deadline": "2027-06-30",
                    "what": "nye USD-M-listninger indsamlet siden 2026-10-22 (kandidater; de endelige stikprøveregler "
                            "anvendes ved kørslen)"})
    out.append({"hypothesis": "U1F", "rule": "research/PROTOCOL_V3.md amendment 17i", "needed": 20, "collected": None,
                "coins": [], "earliest_run_ts": None, "deadline": "2027-06-30",
                "what": "Upbit-KRW-noteringer fra 2026-10-25; tælles først ved målingen (CoinMetrics' katalog læses én "
                        "gang)"})
    return out + [monitoring_forward(db)]


def monitoring_tagged(title):
    """17j point 2: the coins an "Extend the Monitoring Tag" title adds (empty for any other title)."""
    m = M1F_RX.search(title or "")
    if not m:
        return []
    return [w for w in re.split(r"[\s,&]+|\band\b", m.group(1)) if re.fullmatch(r"(?=.*[A-Z])[A-Z0-9]{1,12}", w)]


def monitoring_forward(db):
    """Display only: M1F candidates counted from news-watch titles by 17j points 2, 3a and 3c; 3b and 3d (delisting,
    spot price) are applied when the measurement runs."""
    items = []
    for r in db.q("SELECT payload FROM observations WHERE detector='news/1' AND metric='news_item' AND source LIKE "
                  "'%binance.com%' AND payload LIKE '%Monitoring Tag%'"):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        coins = monitoring_tagged(p.get("title"))
        if coins and p.get("usable_from"):
            items.append((p["usable_from"], coins))
    seen, picked, notes = set(), [], set()
    for t, coins in sorted(items):
        for c in sorted(coins):
            if t >= M1F_FROM and c not in seen and c not in M1F_STABLE and len(picked) < 20:
                picked.append((c, t))
                notes.add(t)
            seen.add(c)
    n = len(picked)
    return {"hypothesis": "M1F", "rule": "research/PROTOCOL_V3.md amendment 17j", "needed": 20, "collected": n,
            "announcements": len(notes), "coins": [c for c, _ in picked],
            "earliest_run_ts": picked[-1][1] + 7 * DAY + 3 * DAY if n >= 20 else None, "deadline": "2027-06-30",
            "what": f"Monitoring-Tag-mønter fra 2026-10-25 i {len(notes)} meddelelser (mindst 6; kandidater, afnotering "
                    "og spotpris anvendes ved kørslen)"}


def _head(verdict):
    v = (verdict or "").split(":")[0].split("(")[0].strip().upper()
    return v.split()[0] if v else "NO RESULT"


EXTERNAL_ALIVE_S = 86400               # an external process that has not written its file for a day is not shown running


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
    from lab import ops
    ext = ops.external_freshness()
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
        if head == "RUNNING" and r["exp_id"] in ext:  # an external process claimed running: show it only with a sign of
            age = ext[r["exp_id"]]["last_write_age_s"]  # life (research/LINUX_DRIFT.md 2026-10-23)
            if age is None or age > EXTERNAL_ALIVE_S:
                head = "UNVERIFIED"
                v = (f"no data file of {ext[r['exp_id']]['label']} on this host" if age is None else
                     f"{ext[r['exp_id']]['label']}: last write {int(age // 3600)} h ago") + f" (recorded: {v or ''})"
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
