"""Opportunity scanner (ENGINE_PROPOSAL.md §3.1, stage S3). It records observations and proposes candidates. It never
evaluates profitability, never fetches evaluation data and never trades.

Detectors (predefined, explainable):
- venue_subsidy      Polymarket liquidity-reward pools vs competing qualifying liquidity (gross, before adverse
                     selection)
- pricing_constraint (a) Hyperliquid vs Binance perpetual mid-price gaps beyond two-venue taker costs,
                     (b) Binance perpetual premium (mark vs index), (c) Polymarket negRisk sum-of-asks (sampled)

A proposal becomes a candidate only if the same flag was seen in >= PERSIST distinct scans. Candidates are then
deduplicated: an existing fingerprint -> "seen again"; an active experiment on the same mechanism and execution ->
"covered"; a rejected one -> SUPPRESSED (graveyard, in registry.discover).
"""
from __future__ import annotations

import json
import random
import statistics
import time
import urllib.parse
import urllib.request

from lab import registry
from lab.lifecycle import state
from lab.registry import fingerprint

PERSIST = 2
SUBSIDY_YIELD_DAY = 0.005          # 0.5 %/day gross reward yield (median of the sample) flags a subsidy class
SUBSIDY_SAMPLE = 60
GAP_MIN = 0.0030                   # 0.30 % > about 0.19 % round-trip taker fees on two venues + spreads
GAP_MAX_SPREAD = 0.0010
PREMIUM_MIN = 0.005
NEGRISK_EVENTS = 150
NEGRISK_FEE, NEGRISK_MIN_PROFIT = 0.07, 5.0
ACTOR = "system:scanner"
CLOB, GAMMA = "https://clob.polymarket.com", "https://gamma-api.polymarket.com"
HL_INFO, BN = "https://api.hyperliquid.xyz/info", "https://fapi.binance.com"


def http_get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "copybot-research/1.0"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception:
            if i == 3:
                raise
            time.sleep(1 + i)


def http_post(url, body):
    for i in range(4):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"User-Agent": "copybot-research/1.0", "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except Exception:
            if i == 3:
                raise
            time.sleep(1 + i)


def obs(detector, source, instrument, metric, value, threshold=None, flagged=False, payload=None):
    return {"detector": detector, "source": source, "instrument": instrument, "metric": metric, "value": value,
            "threshold": threshold, "flagged": int(bool(flagged)), "payload": payload or {}}


def proposal(detector, metric, instrument_key, tag, family, horizon, execution, hypothesis, reason, needs, source):
    return {"detector": detector, "metric": metric, "instrument_key": instrument_key, "mechanism_tag": tag,
            "instrument": family, "horizon": horizon, "execution": execution, "hypothesis": hypothesis,
            "reason": reason, "data_requirements": needs, "source": source}


# ---------- detectors ----------
def _score(v, s):
    return ((v - s) / v) ** 2 if v > 0 and 0 <= s < v else 0.0


def venue_subsidy(get, post, now):
    rows, cur = [], ""
    while True:
        r = get(f"{CLOB}/rewards/markets/current" + (f"?next_cursor={urllib.parse.quote(cur)}" if cur else ""))
        rows += r.get("data") or []
        cur = r.get("next_cursor")
        if not cur or cur == "LTE=" or not r.get("data"):
            break
    src = f"{CLOB}/rewards/markets/current"
    out = [obs("venue_subsidy", src, "polymarket", "configured_pool_usd_day",
               sum(x.get("total_daily_rate") or 0 for x in rows), payload={"markets": len(rows)})]
    cand = sorted((x for x in rows if (x.get("total_daily_rate") or 0) >= 5), key=lambda x: x["condition_id"])
    random.Random(now // 86400).shuffle(cand)
    yields = []
    for x in cand[:SUBSIDY_SAMPLE]:
        try:
            m = get(f"{CLOB}/markets/{x['condition_id']}")
            b = get(f"{CLOB}/book?token_id={m['tokens'][0]['token_id']}")
        except Exception:
            continue
        bids = [(float(o["price"]), float(o["size"])) for o in b.get("bids", [])]
        asks = [(float(o["price"]), float(o["size"])) for o in b.get("asks", [])]
        if not bids or not asks:
            continue
        mid = (max(p for p, _ in bids) + min(p for p, _ in asks)) / 2
        v, s = x["rewards_max_spread"] / 100, x["rewards_max_spread"] / 200
        if mid - s <= 0 or mid + s >= 1:
            continue
        q1 = sum(_score(v, mid - p) * z for p, z in bids if z >= x["rewards_min_size"])
        q2 = sum(_score(v, p - mid) * z for p, z in asks if z >= x["rewards_min_size"])
        comp = min(q1, q2) if (mid < 0.10 or mid > 0.90) else max(min(q1, q2), max(q1, q2) / 3)
        ours = _score(v, s) * 100
        yields.append(ours / (comp + ours) * x["total_daily_rate"] / (100 * (1 - 2 * s)))
    props = []
    if yields:
        med = statistics.median(yields)
        flagged = med >= SUBSIDY_YIELD_DAY
        out.append(obs("venue_subsidy", src, "polymarket_reward_markets", "median_gross_yield_day", med,
                       SUBSIDY_YIELD_DAY, flagged, {"sampled": len(yields)}))
        if flagged:
            props.append(proposal(
                "venue_subsidy", "median_gross_yield_day", "polymarket_reward_markets",
                "venue_subsidy_liquidity_rewards", "polymarket_reward_markets", "days", "maker",
                "A small passive maker earns Polymarket liquidity rewards exceeding adverse selection and inventory losses",
                f"median gross reward yield {med:.2%}/day on {len(yields)} sampled markets (before adverse selection)",
                ["reward configs", "minute order books", "taker trades", "resolutions"], src))
    return out, props


def pricing_constraint(get, post, now):
    out, props = [], []
    # (a) cross-venue perpetual gaps
    try:
        hl = post(HL_INFO, {"type": "allMids"})
        bn = {x["symbol"]: x for x in get(f"{BN}/fapi/v1/ticker/bookTicker")}
        gaps = []
        for coin, mid in hl.items():
            if coin.startswith(("k", "@")) or f"{coin}USDT" not in bn:
                continue
            t = bn[f"{coin}USDT"]
            bb, ba = float(t["bidPrice"]), float(t["askPrice"])
            if bb <= 0 or ba <= 0:
                continue
            bmid, spread = (bb + ba) / 2, (ba - bb) / ((bb + ba) / 2)
            gap = float(mid) / bmid - 1
            gaps.append(abs(gap))
            if abs(gap) >= GAP_MIN and spread < GAP_MAX_SPREAD:
                out.append(obs("pricing_constraint", f"{HL_INFO} allMids + {BN}/fapi/v1/ticker/bookTicker", coin,
                               "cross_venue_gap", gap, GAP_MIN, True, {"binance_spread": spread}))
        out.append(obs("pricing_constraint", HL_INFO, "hyperliquid_binance_perps", "coins_compared", len(gaps),
                       payload={"max_abs_gap": max(gaps) if gaps else None}))
        if any(o["metric"] == "cross_venue_gap" for o in out):
            props.append(proposal(
                "pricing_constraint", "cross_venue_gap", None, "cross_venue_perp_gap", "hyperliquid_binance_perps",
                "minutes", "taker_two_venues",
                "Hyperliquid and Binance perpetual prices for the same coin diverge by more than two-venue costs, and converge",
                "mid gap >= 0.30 % with Binance spread < 0.10 % (HL spread not observed)",
                ["simultaneous top-of-book on both venues", "fees", "funding on both venues", "transfer constraints"],
                HL_INFO))
    except Exception as e:
        out.append(obs("pricing_constraint", HL_INFO, "hyperliquid_binance_perps", "error", None, payload={"error": repr(e)}))
    # (b) perpetual premium vs index
    try:
        pi = get(f"{BN}/fapi/v1/premiumIndex")
        n = 0
        for x in pi:
            m, i = float(x.get("markPrice") or 0), float(x.get("indexPrice") or 0)
            if m <= 0 or i <= 0:
                continue
            n += 1
            p = m / i - 1
            if abs(p) >= PREMIUM_MIN:
                out.append(obs("pricing_constraint", f"{BN}/fapi/v1/premiumIndex", x["symbol"], "perp_premium", p,
                               PREMIUM_MIN, True, {"funding": x.get("lastFundingRate")}))
        out.append(obs("pricing_constraint", f"{BN}/fapi/v1/premiumIndex", "binance_perps", "symbols_compared", n))
        if any(o["metric"] == "perp_premium" for o in out):
            props.append(proposal(
                "pricing_constraint", "perp_premium", None, "perp_premium_convergence", "binance_perps", "minutes",
                "taker", "Large perpetual premiums over the index revert faster than costs",
                "|mark/index - 1| >= 0.5 %", ["1-minute premium index", "spot and perp klines", "fees"],
                f"{BN}/fapi/v1/premiumIndex"))
    except Exception as e:
        out.append(obs("pricing_constraint", BN, "binance_perps", "error", None, payload={"error": repr(e)}))
    # (c) negRisk sum of asks (sampled)
    try:
        evs = (get(f"{GAMMA}/events/keyset?active=true&closed=false&limit={NEGRISK_EVENTS}").get("events") or [])
        checked = 0
        for e in evs:
            if not (e.get("negRisk") or e.get("enableNegRisk")) or e.get("negRiskAugmented"):
                continue
            mks = [m for m in e.get("markets") or [] if m.get("active") and not m.get("closed") and m.get("clobTokenIds")]
            if len(mks) < 2 or len(mks) != len(e.get("markets") or []):
                continue
            toks = [json.loads(m["clobTokenIds"])[0] for m in mks]
            books = {b["asset_id"]: b for b in post(f"{CLOB}/books", [{"token_id": t} for t in toks[:50]])}
            if len(books) != len(toks):
                continue
            checked += 1
            asks = [min(((float(o["price"]), float(o["size"])) for o in books[t].get("asks", [])), default=None)
                    for t in toks]
            if all(asks):
                cost = sum(p + NEGRISK_FEE * p * (1 - p) for p, _ in asks)
                size = min(z for _, z in asks)
                profit = (1 - cost) * size
                if cost < 1 and profit >= NEGRISK_MIN_PROFIT:
                    out.append(obs("pricing_constraint", f"{GAMMA}/events/keyset", e.get("slug"), "negrisk_locked_profit",
                                   profit, NEGRISK_MIN_PROFIT, True, {"cost": cost, "legs": len(toks)}))
        out.append(obs("pricing_constraint", f"{GAMMA}/events/keyset", "polymarket_negrisk", "events_checked", checked))
        if any(o["metric"] == "negrisk_locked_profit" for o in out):
            props.append(proposal(
                "pricing_constraint", "negrisk_locked_profit", None, "negrisk_sum_arbitrage", "polymarket_negrisk",
                "instant", "taker", "Sum of best YES asks in a complete negRisk event is below 1 after fees",
                "locked profit >= $5 at best-level size", ["order books of every leg"], f"{GAMMA}/events/keyset"))
    except Exception as e:
        out.append(obs("pricing_constraint", GAMMA, "polymarket_negrisk", "error", None, payload={"error": repr(e)}))
    return out, props


DETECTORS = {"venue_subsidy": venue_subsidy, "pricing_constraint": pricing_constraint}


# ---------- scanner ----------
def persisted(db, p, now):
    """Distinct scan timestamps (including now) with a flagged observation for this detector/metric(/instrument)."""
    q = "SELECT COUNT(DISTINCT ts) FROM observations WHERE detector=? AND metric=? AND flagged=1"
    args = [p["detector"], p["metric"]]
    if p["instrument_key"]:
        q += " AND instrument=?"
        args.append(p["instrument_key"])
    return db.one(q, *args)[0]


def run(db, names=None, get=http_get, post=http_post, now=None):
    now = int(now or time.time())
    summary = {"observations": 0, "flagged": 0, "proposals": 0, "waiting_persistence": 0, "created": [],
               "suppressed": [], "covered": [], "seen_again": [], "errors": []}
    for name in names or DETECTORS:
        observations, proposals = DETECTORS[name](get, post, now)
        with db.tx():
            for o in observations:
                db.append("observations", ts=now, **o)
                summary["observations"] += 1
                summary["flagged"] += o["flagged"]
                if o["metric"] == "error":
                    summary["errors"].append(o["payload"].get("error"))
        for p in proposals:
            summary["proposals"] += 1
            if persisted(db, p, now) < PERSIST:
                summary["waiting_persistence"] += 1
                db.event("candidate.pending_persistence", ACTOR, None, {k: p[k] for k in ("detector", "metric", "mechanism_tag")})
                continue
            fp = fingerprint(p["mechanism_tag"], p["instrument"], p["horizon"], p["execution"])
            existing = db.one("SELECT exp_id FROM experiments WHERE fingerprint=? LIMIT 1", fp)
            if existing:
                if state(db, existing["exp_id"]) in ("REJECTED", "WITHDRAWN"):
                    db.event("candidate.suppressed", ACTOR, existing["exp_id"],
                             {"reason": p["reason"], "scan_ts": now, "graveyard": existing["exp_id"]})
                    summary["suppressed"].append(existing["exp_id"])
                else:
                    db.event("candidate.seen_again", ACTOR, existing["exp_id"], {"reason": p["reason"], "scan_ts": now})
                    summary["seen_again"].append(existing["exp_id"])
                continue
            cover = registry.covering(db, p["mechanism_tag"], p["execution"], fp)
            if cover:
                db.event("candidate.covered", ACTOR, cover[0], {"mechanism": p["mechanism_tag"], "reason": p["reason"],
                                                                "scan_ts": now})
                summary["covered"].append(cover[0])
                continue
            exp_id = "C_" + fp[:10]
            st, dup = registry.discover(db, exp_id, p["hypothesis"], p["mechanism_tag"], p["instrument"], p["horizon"],
                                        p["execution"], p["source"], ACTOR,
                                        extra={"discovered_by": p["detector"], "reason": p["reason"],
                                               "data_requirements": p["data_requirements"], "scan_ts": now,
                                               "label": "CANDIDATE (not evaluated)"})
            (summary["suppressed"] if st == "SUPPRESSED" else summary["created"]).append(exp_id)
    db.event("scan.finished", ACTOR, None, {k: v for k, v in summary.items()})
    return summary
