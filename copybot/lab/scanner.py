"""Opportunity scanner (ENGINE_PROPOSAL.md §3.1, stage S3). It records observations and proposes candidates. It never
evaluates profitability, never fetches evaluation data and never trades.

Detectors (predefined, explainable):
- venue_subsidy      Polymarket liquidity-reward pools vs competing qualifying liquidity (gross, before adverse
                     selection)
- pricing_constraint (a) Hyperliquid vs Binance perpetual mid-price gaps beyond two-venue taker costs,
                     (b) Binance perpetual premium (mark vs index), (c) Polymarket negRisk sum-of-asks (sampled)
- abnormal_move      unusual moves of a fixed list of Binance USD-M perps across asset classes (amendment 21,
                     lab/moves.py): observations and analysis records only, never a proposal

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

PERSIST = 2                        # flagged in >= 2 scans that lie in different clock hours ...
PERSIST_BUCKET = 3600
PERSIST_WINDOW = 24 * 3600         # ... within the last 24 h (PROTOCOL_V3 amendment 5)
EVENT_DEDUP_S = 6 * 3600           # one market.event per detector/metric/instrument/decision per 6 h
GRAVEYARD = ("REJECTED", "WITHDRAWN", "SUPPRESSED")
VERSION = {"venue_subsidy": 1, "pricing_constraint": 2,    # persistence only counts observations of the same version
           "abnormal_move": 1}
GAP_IDENTITY_MAX = 0.03            # larger gaps are treated as an instrument-identity mismatch, never as an opportunity
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


def vname(detector):
    base = detector.split("/")[0]
    return f"{base}/{VERSION[base]}"


def obs(detector, source, instrument, metric, value, threshold=None, flagged=False, payload=None):
    return {"detector": vname(detector), "source": source, "instrument": instrument, "metric": metric, "value": value,
            "threshold": threshold, "flagged": int(bool(flagged)), "payload": payload or {}}


def proposal(detector, metric, instrument_key, tag, family, horizon, execution, hypothesis, reason, needs, source):
    return {"detector": vname(detector), "metric": metric, "instrument_key": instrument_key, "mechanism_tag": tag,
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


def _perps(get):
    """Live USDT-margined perpetuals on crypto underlyings (no dated futures, no stock/commodity contracts)."""
    info = get(f"{BN}/fapi/v1/exchangeInfo")
    return {s["symbol"] for s in info.get("symbols", []) if s.get("contractType") == "PERPETUAL"
            and s.get("underlyingType") == "COIN" and s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT"}


def premium_obs(get, perps, funding=None, intervals=None, raw=None, rows_out=None):
    """Measurement (b): |mark/index - 1| >= PREMIUM_MIN per perp, flagged, plus the count compared. funding: if given,
    receives {symbol: predicted funding per 8 hours} of every compared perp (12e; 12i: lastFundingRate x 8 / the
    symbol's settlement interval from `intervals`, 8 hours when unknown); raw: if given, receives the raw rates;
    rows_out: if given, receives every row of the response (amendment 22: K3 reuses this fetch)."""
    out, n = [], 0
    intervals = intervals or {}
    for x in get(f"{BN}/fapi/v1/premiumIndex"):
        if rows_out is not None:
            rows_out.append(x)
        if x.get("symbol") not in perps:
            continue
        m, i = float(x.get("markPrice") or 0), float(x.get("indexPrice") or 0)
        if m <= 0 or i <= 0:
            continue
        n += 1
        if funding is not None and x.get("lastFundingRate") not in (None, ""):
            r = float(x["lastFundingRate"])
            funding[x["symbol"]] = r * EIGHT_HOURS / intervals.get(x["symbol"], EIGHT_HOURS)
            if raw is not None:
                raw[x["symbol"]] = r
        p = m / i - 1
        if abs(p) >= PREMIUM_MIN:
            out.append(obs("pricing_constraint", f"{BN}/fapi/v1/premiumIndex", x["symbol"], "perp_premium", p,
                           PREMIUM_MIN, True, {"funding": x.get("lastFundingRate")}))
    out.append(obs("pricing_constraint", f"{BN}/fapi/v1/premiumIndex", "binance_perps", "symbols_compared", n))
    return out


PERPS_EVERY = 3600
_PERPS = {}                                     # premium-watch: url -> (fetched at, perps); exchangeInfo once an hour
FUNDING_MIN = 0.0005                            # 12f: predicted funding >= 0.05 % per 8 h is recorded, flagged
FLOOR = 0.0001                                  # the 0.01 % interest floor per 8 hours (12i: rates are per 8 h)
EIGHT_HOURS = 8                                 # 12i: Binance thresholds are per 8 hours
INTERVALS = {}                                  # 12i: symbol -> settlement interval in hours (fundingInfo); others 8
_INTERVALS_AT = {}                              # url -> when fundingInfo was last fetched (at most hourly)


def intervals(get, now):
    """12i: Binance fundingInfo (public GET, at most once an hour). Symbols not listed settle every 8 hours. A failed
    fetch keeps what is known (and 8 hours for the rest: the stricter reading)."""
    at = _INTERVALS_AT.get(BN)
    if at is None or now - at >= PERPS_EVERY:
        _INTERVALS_AT[BN] = now
        try:
            got = {x["symbol"]: int(x["fundingIntervalHours"]) for x in get(f"{BN}/fapi/v1/fundingInfo")
                   if x.get("symbol") and int(x.get("fundingIntervalHours") or 0) > 0}
            INTERVALS.clear()
            INTERVALS.update(got)
        except Exception:
            pass
    return INTERVALS
LIVE = {}                                       # 12e: url -> (measured at, {symbol: predicted funding}), in memory only
HL_LIVE = {}                                    # 13: url -> (measured at, {coin: predicted funding x 8}), in memory only
HL_EIGHT = 8                                    # 13: Hyperliquid settles hourly; x 8 compares with Binance's 8-hour rate


def hl_obs(res, now):
    """Amendment 13: Hyperliquid metaAndAssetCtxs -> rows (predicted funding x 8 >= FUNDING_MIN, flagged, plus the
    count compared) and {coin: predicted funding x 8} for every listed perp (no k- or @-prefixed or delisted coin)."""
    meta, ctxs = res
    live = {}
    for a, c in zip(meta.get("universe") or [], ctxs):
        name = a.get("name") or ""
        if not name or name.startswith(("k", "@")) or a.get("isDelisted") or c.get("funding") in (None, ""):
            continue
        live[name] = float(c["funding"]) * HL_EIGHT
    rows = [obs("pricing_constraint", HL_INFO, name, "hl_predicted_funding", r, FUNDING_MIN, True)
            for name, r in sorted(live.items()) if r >= FUNDING_MIN]
    rows.append(obs("pricing_constraint", HL_INFO, "hyperliquid_perps", "hl_symbols_compared", len(live)))
    if live:                                    # display only: the market's funding on Hyperliquid (x 8)
        vals, top = sorted(live.values()), max(live, key=lambda k: (live[k], k))
        rows += [obs("pricing_constraint", HL_INFO, "hyperliquid_perps", "hl_funding_median", vals[len(vals) // 2]),
                 obs("pricing_constraint", HL_INFO, "hyperliquid_perps", "hl_funding_top", live[top],
                     payload={"symbol": top})]
    return rows, live


def premium_watch(db, get=http_get, now=None, post=None):
    """Amendment 12a: measurement (b) every minute, written as observations only (no market.event, no candidate);
    12e: plus predicted funding >= FUNDING_MIN as flagged rows, and every perp's predicted funding in LIVE."""
    now = int(now or time.time())
    hit = _PERPS.get(BN)
    if hit is None or now - hit[0] >= PERPS_EVERY or not hit[1]:
        _PERPS[BN] = hit = (now, _perps(get))
    funding, raw = {}, {}
    iv = intervals(get, now)
    allrows = []
    rows = premium_obs(get, hit[1], funding, iv, raw, allrows)
    rows += [obs("pricing_constraint", f"{BN}/fapi/v1/premiumIndex", sym, "predicted_funding", r, FUNDING_MIN, True,
                 {"raw": raw.get(sym), "interval_h": iv.get(sym, EIGHT_HOURS), "per": "8h"})
             for sym, r in sorted(funding.items()) if r >= FUNDING_MIN]
    if funding:                                 # 12e precision: the market's funding, for display only
        src, vals = f"{BN}/fapi/v1/premiumIndex", sorted(funding.values())
        top = max(funding, key=lambda k: (funding[k], k))
        rows += [obs("pricing_constraint", src, "binance_perps", "funding_median", vals[len(vals) // 2]),
                 obs("pricing_constraint", src, "binance_perps", "funding_above_floor",
                     sum(1 for v in vals if v > FLOOR + 1e-12) / len(vals)),
                 obs("pricing_constraint", src, "binance_perps", "funding_top", funding[top], payload={"symbol": top})]
    LIVE[BN] = (now, funding)
    body = {"type": "metaAndAssetCtxs"}             # amendment 13: Hyperliquid's predicted funding, same minute
    try:
        hl_rows, live = hl_obs(post(HL_INFO, body) if post else http_post(HL_INFO, body), now)
        rows += hl_rows
        HL_LIVE[HL_INFO] = (now, live)
    except Exception as e:                          # Binance's measurement stands; the next minute tries again
        rows.append(obs("pricing_constraint", HL_INFO, "hyperliquid_perps", "error", None,
                        payload={"error": repr(e)[:300]}))
    with db.tx():
        for o in rows:
            db.append("observations", ts=now, **o)
    k3_res = None
    try:                                            # amendment 22 H: K3 never stops premium-watch
        from lab import k3, lane
        k3_res = k3.observe(db, now, allrows, iv, hit[1], get, delisted=lambda t: lane.delistings(db, t))
    except Exception as e:                          # noqa: BLE001
        if now - _K3_ERR.get("at", 0) >= 600:       # recorded at most every 10 min
            _K3_ERR["at"] = now
            db.append("observations", ts=now, detector="k3/1", source="k3", instrument=None, metric="error",
                      value=None, threshold=None, flagged=0, payload={"error": repr(e)[:300]})
        k3_res = {"error": repr(e)[:200]}
    try:                                            # amendment 28: the census never stops premium-watch
        from lab import census
        census_res = census.guarded(db, now, allrows, get, hit[1])
    except Exception as e:                          # noqa: BLE001
        census_res = {"error": repr(e)[:200]}
    return {"observations": len(rows), "flagged": sum(o["flagged"] for o in rows), "decisional": False, "k3": k3_res,
            "census": census_res}


_K3_ERR = {}


def pricing_constraint(get, post, now):
    out, props = [], []
    try:   # only live USDT-margined perpetuals on crypto underlyings (no dated futures, no stock/commodity contracts)
        perps = _perps(get)
    except Exception as e:
        perps = set()
        out.append(obs("pricing_constraint", BN, "binance_perps", "error", None, payload={"error": repr(e)}))
    # (a) cross-venue perpetual gaps
    try:
        hl = post(HL_INFO, {"type": "allMids"})
        bn = {x["symbol"]: x for x in get(f"{BN}/fapi/v1/ticker/bookTicker") if x["symbol"] in perps}
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
            if abs(gap) > GAP_IDENTITY_MAX:
                out.append(obs("pricing_constraint", HL_INFO, coin, "identity_mismatch_suspected", gap, GAP_IDENTITY_MAX,
                               False, {"note": "same ticker, different instrument or units; not an opportunity"}))
                continue
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
                "mid gap 0.30-3 % with Binance spread < 0.10 % (HL spread not observed; >3 % treated as identity mismatch)",
                ["simultaneous top-of-book on both venues", "fees", "funding on both venues", "transfer constraints"],
                HL_INFO))
    except Exception as e:
        out.append(obs("pricing_constraint", HL_INFO, "hyperliquid_binance_perps", "error", None, payload={"error": repr(e)}))
    # (b) perpetual premium vs index
    try:
        out += premium_obs(get, perps)
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


def _abnormal_move(get, post, now):
    from lab import moves
    return moves.detect(get, post, now)


def _after_moves(db, observations, now, get):
    from lab import moves
    return moves.record(db, observations, now, get)


CATCHUP_GAP_S, CATCHUP_LAST_S, CATCHUP_MAX = 120, 480, 3     # amendment 21z C: every 120 s, start <= close + 480 s


def failed_moves(db, ts):
    """Markets of moves.WATCH whose abnormal_move scan at `ts` failed to fetch (21z C point 3): an `error` row per
    market, or every market when the detector itself failed. history_short is not a fetch failure."""
    from lab import moves
    rows = {r["instrument"] for r in db.q("SELECT instrument FROM observations WHERE detector=? AND ts=? AND "
                                          "metric='error'", vname(moves.DETECTOR), ts)}
    return set(moves.WATCH) if None in rows else rows & set(moves.WATCH)


def catch_up(db, syms, after_ts, attempt, get=http_get, now=None):
    """21z C: one in-window rescan of only the markets in `syms`, stored as an ordinary scan with its own ts and a
    `catch_up` tag; the move records run as after a scheduled scan. Returns the markets that failed again."""
    from lab import moves
    now = int(now or time.time())
    try:
        observations, _ = moves.detect(get, None, now, syms=set(syms))
    except Exception as e:                            # noqa: BLE001 - recorded like a failing detector
        observations = [obs("abnormal_move", "detector", None, "error", None,
                            payload={"error": f"detector failed: {e!r}"[:300]})]
    tag = {"after_error_ts": after_ts, "attempt": attempt, "rule": "research/PROTOCOL_V3.md amendment 21z C"}
    observations = [{**o, "payload": {**o["payload"], "catch_up": tag}} for o in observations]
    with db.tx():
        for o in observations:
            db.append("observations", ts=now, **o)
    try:
        records = moves.record(db, observations, now, get)
    except Exception as e:                            # noqa: BLE001 - the analysis never stops the scan
        records = f"records failed: {e!r}"[:300]
    return {"ts": now, "attempt": attempt, "markets": sorted(syms),
            "failed": sorted(failed_moves(db, now) & set(syms)), "records": records}


DETECTORS = {"venue_subsidy": venue_subsidy, "pricing_constraint": pricing_constraint,
             "abnormal_move": _abnormal_move}                     # amendment 21: data and analysis records only
AFTER = {"abnormal_move": _after_moves}                           # runs after the detector's observations are stored


# ---------- scanner ----------
def persisted(db, p, now):
    """Distinct clock hours within the last 24 h (including now) with a flagged observation for this
    detector/metric and, when the proposal names one, the same instrument (amendment 5)."""
    q = "SELECT COUNT(DISTINCT ts / ?) FROM observations WHERE detector=? AND metric=? AND flagged=1 AND ts > ?"
    args = [PERSIST_BUCKET, p["detector"], p["metric"], now - PERSIST_WINDOW]
    if p["instrument_key"]:
        q += " AND instrument=?"
        args.append(p["instrument_key"])
    return db.one(q, *args)[0]


def market_event(db, now, key, decision, why, magnitude=None, persistence=None, quality=None, exp_id=None,
                 source=None):
    """Record what the scanner saw and what it decided (amendment 5: a record, never a trade or a gate).
    Deduplicated: the same key and decision is written at most once per EVENT_DEDUP_S. Returns True if written."""
    k = json.dumps(key, sort_keys=True)
    for r in db.q("SELECT exp_id, payload FROM events WHERE kind='market.event' AND json_extract(payload, '$.scan_ts') "
                  "> ? ORDER BY id DESC", now - EVENT_DEDUP_S):        # the scan's clock, the same one as `now`
        p = json.loads(r["payload"])
        if json.dumps(p.get("key"), sort_keys=True) != k:
            continue
        same = (p.get("decision") == decision and r["exp_id"] == exp_id
                and str(p.get("why")).split(":")[0] == str(why).split(":")[0])
        if same:
            return False                  # the newest record for this key already says this: nothing new to record
        break                             # the decision, the experiment or the reason changed: record it now
    priority = round(min(5.0, magnitude), 2) if (decision == "INVESTIGATE" and magnitude) else 0.0
    db.event("market.event", ACTOR, exp_id, {"key": key, "decision": decision, "why": why, "priority": priority,
                                             "magnitude": magnitude, "persistence_hours_24h": persistence,
                                             "data_quality": quality, "source": source, "scan_ts": now})
    return True


def _magnitude(observations, p):
    """Largest flagged |value|/threshold for this proposal's metric (and instrument) in this scan (gaps and premiums
    can be negative; the size of the deviation is what matters)."""
    m = [abs(o["value"]) / abs(o["threshold"]) for o in observations
         if o["flagged"] and o["metric"] == p["metric"] and o["threshold"] and o["value"] is not None
         and (not p["instrument_key"] or o["instrument"] == p["instrument_key"])]
    return round(max(m), 3) if m else None


def run(db, names=None, get=http_get, post=http_post, now=None):
    now = int(now or time.time())
    summary = {"observations": 0, "flagged": 0, "proposals": 0, "waiting_persistence": 0, "created": [],
               "suppressed": [], "covered": [], "seen_again": [], "errors": [], "market_events": 0,
               "investigate": 0, "no_action": 0}

    def decide(p, decision, why, observations, quality, exp_id=None):
        key = {"detector": p["detector"], "metric": p["metric"], "instrument": p["instrument_key"] or p["instrument"]}
        if market_event(db, now, key, decision, why, _magnitude(observations, p), persisted(db, p, now), quality,
                        exp_id, p["source"]):
            summary["market_events"] += 1
        summary["investigate" if decision == "INVESTIGATE" else "no_action"] += 1

    for name in names or DETECTORS:
        try:
            observations, proposals = DETECTORS[name](get, post, now)
        except Exception as e:                        # one failing detector never stops the others
            observations, proposals = [obs(vname(name), "detector", None, "error", None,
                                           payload={"error": f"detector failed: {e!r}"[:300]})], []
        errors = [o for o in observations if o["metric"] == "error"]
        quality = {"observations": len(observations), "errors": len(errors)}
        for o in errors:                              # an unstable data source is an event of its own
            if market_event(db, now, {"detector": vname(name), "source": o["source"], "metric": "error"}, "NO_ACTION",
                            f"data source failed: {str(o['payload'].get('error'))[:160]}", quality=quality,
                            source=o["source"]):
                summary["market_events"] += 1
        with db.tx():
            for o in observations:
                db.append("observations", ts=now, **o)
                summary["observations"] += 1
                summary["flagged"] += o["flagged"]
                if o["metric"] == "error":
                    summary["errors"].append(o["payload"].get("error"))
        if name in AFTER:
            try:
                summary[f"{name}_records"] = AFTER[name](db, observations, now, get)
            except Exception as e:                    # noqa: BLE001 - the analysis never stops the scan
                summary["errors"].append(f"{name} records failed: {e!r}"[:300])
        for p in proposals:
            summary["proposals"] += 1
            if persisted(db, p, now) < PERSIST:
                summary["waiting_persistence"] += 1
                db.event("candidate.pending_persistence", ACTOR, None, {k: p[k] for k in ("detector", "metric", "mechanism_tag")})
                decide(p, "NO_ACTION", f"waiting for persistence: flagged in {persisted(db, p, now)} of the required "
                       f"{PERSIST} clock hours within 24 h", observations, quality)
                continue
            fp = fingerprint(p["mechanism_tag"], p["instrument"], p["horizon"], p["execution"])
            existing = db.one("SELECT exp_id FROM experiments WHERE fingerprint=? LIMIT 1", fp)
            if existing:
                st0 = state(db, existing["exp_id"])
                if st0 in GRAVEYARD:
                    db.event("candidate.suppressed", ACTOR, existing["exp_id"],
                             {"reason": p["reason"], "scan_ts": now, "graveyard": existing["exp_id"]})
                    summary["suppressed"].append(existing["exp_id"])
                    decide(p, "NO_ACTION", f"graveyard: {existing['exp_id']} is {st0}", observations, quality,
                           existing["exp_id"])
                else:
                    db.event("candidate.seen_again", ACTOR, existing["exp_id"], {"reason": p["reason"], "scan_ts": now})
                    summary["seen_again"].append(existing["exp_id"])
                    decide(p, "NO_ACTION", f"already registered: {existing['exp_id']} is {st0}", observations,
                           quality, existing["exp_id"])           # amendment 5: covered, INVESTIGATE is for new ones
                continue
            cover = registry.covering(db, p["mechanism_tag"], p["execution"], fp)
            if cover:
                db.event("candidate.covered", ACTOR, cover[0], {"mechanism": p["mechanism_tag"], "reason": p["reason"],
                                                                "scan_ts": now})
                summary["covered"].append(cover[0])
                decide(p, "NO_ACTION", f"covered by active experiment {cover[0]}", observations, quality, cover[0])
                continue
            exp_id = "C_" + fp[:10]
            st, dup = registry.discover(db, exp_id, p["hypothesis"], p["mechanism_tag"], p["instrument"], p["horizon"],
                                        p["execution"], p["source"], ACTOR,
                                        extra={"discovered_by": p["detector"], "reason": p["reason"],
                                               "data_requirements": p["data_requirements"], "scan_ts": now,
                                               "label": "CANDIDATE (not evaluated)"})
            (summary["suppressed"] if st == "SUPPRESSED" else summary["created"]).append(exp_id)
            if st == "SUPPRESSED":
                decide(p, "NO_ACTION", f"graveyard match {dup}: suppressed as {exp_id}", observations, quality, exp_id)
            else:
                decide(p, "INVESTIGATE", f"new candidate {exp_id}; a test needs a pre-registered forward template",
                       observations, quality, exp_id)
    db.event("scan.finished", ACTOR, None, {k: v for k, v in summary.items()})
    return summary
