"""PROTOCOL_V3 amendment 21d: a descriptive integration test of the chain move + news + calendar around one scheduled
release (FOMC 2026-10-28 18:00 UTC). It reads the registry read-only and Binance 1 h klines (fapi, allowed GET) and
writes a report; the windows are the locked ones (point 3) and nothing is added afterwards. Never a strategy result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone

from lab import moves

RULE = "research/PROTOCOL_V3.md amendment 21d"
HOUR = 3600
AFTER = {"1h": 1, "4h": 4, "24h": 24}                       # point 3: returns to the closes T + k hours
FED = "https://www.federalreserve.gov/feeds/press_all.xml"
OTHER_MACRO = {"cnbc_economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
               "ecb_press": "https://www.ecb.europa.eu/rss/press.html"}


def _p(row):
    return json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]


def market(get, sym, t):
    """Point 3 for one market from Binance klines: returns from the close at T to T + 1/4/24 h, the event hour's z
    and volume ratio by amendment 21's rule, and the sha256 of the response. Missing bars stay missing."""
    url = (f"{moves.BN}/fapi/v1/klines?symbol={sym}&interval=1h&startTime={(t - (moves.HIST + 2) * HOUR) * 1000}"
           f"&endTime={(t + 24 * HOUR) * 1000 - 1}&limit=1500")
    try:
        raw = get(url)
    except Exception as e:                                      # noqa: BLE001 - one market never stops the report
        return {"error": f"{e!r}"[:200], "url": url}
    rows = raw if isinstance(raw, list) else json.loads(raw)
    sha = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
    close = {int(k[0]) // 1000: float(k[4]) for k in rows}      # bar open -> close
    vol = {int(k[0]) // 1000: float(k[7]) for k in rows}
    out = {"url": url, "sha256": sha, "bars": len(rows), "missing": []}
    ref = close.get(t - HOUR)                                   # close of the 17:00-18:00 bar = the price at T
    if not ref:
        out["missing"].append("reference bar (T - 1 h)")
    for name, k in AFTER.items():
        c = close.get(t + (k - 1) * HOUR)
        if ref and c:
            out[f"ret_{name}"] = math.log(c / ref)
        else:
            out[f"ret_{name}"] = None
            out["missing"].append(f"bar closing T + {name}")
    trail = [math.log(close[h] / close[h - HOUR]) for h in range(t - moves.HIST * HOUR, t, HOUR)
             if close.get(h) and close.get(h - HOUR)]
    if ref and close.get(t) and len(trail) >= moves.MIN_RETURNS:
        sigma = statistics.pstdev(trail)
        out["z_event_hour"] = math.log(close[t] / ref) / sigma if sigma > 0 else None
        vols = [vol[h] for h in range(t - moves.HIST * HOUR, t, HOUR) if h in vol]
        med = statistics.median(vols) if vols else 0
        out["volume_ratio_event_hour"] = vol.get(t, 0) / med if med else None
    else:
        out["z_event_hour"] = out["volume_ratio_event_hour"] = None
        out["missing"].append(f"event hour z ({len(trail)} trailing returns)")
    return out


def scanner(q, t):
    """The scanner's own observations and records (point 3, 5 and 6)."""
    flags = [{"instrument": r["instrument"], "metric": r["metric"], "value": r["value"], "ts": r["ts"],
              "delay_s": r["ts"] - (_p(r).get("close_s") or r["ts"])}
             for r in q("SELECT ts, instrument, metric, value, payload FROM observations WHERE detector='abnormal_move/1' "
                        "AND flagged=1 AND ts BETWEEN ? AND ? ORDER BY ts", t, t + 3 * HOUR)]
    scans = [r["ts"] for r in q("SELECT DISTINCT ts FROM observations WHERE detector='abnormal_move/1' AND ts BETWEEN "
                                "? AND ? ORDER BY ts", t - HOUR, t + 25 * HOUR)]
    delays = []
    for ts in scans:
        r = q("SELECT payload FROM observations WHERE detector='abnormal_move/1' AND metric='z_1h' AND ts=? LIMIT 1", ts)
        if r and _p(r[0]).get("close_s"):
            delays.append(ts - _p(r[0])["close_s"])
    problems = [{"ts": r["ts"], "instrument": r["instrument"], "metric": r["metric"],
                 "detail": (_p(r).get("error") or r["value"])}
                for r in q("SELECT ts, instrument, metric, value, payload FROM observations WHERE "
                           "detector='abnormal_move/1' AND metric IN ('error', 'history_short') AND ts BETWEEN ? AND ? "
                           "ORDER BY ts", t - HOUR, t + 25 * HOUR)]
    recs = []
    for r in q("SELECT id, ts, payload FROM events WHERE kind='opportunity.move' AND ts BETWEEN ? AND ? ORDER BY id",
               t, t + 3 * HOUR):
        p = _p(r)
        end = p["move_hour_s"] + HOUR
        news = p.get("news") or []
        recs.append({"id": r["id"], "instrument": p["instrument"], "flags": p.get("flags"), "move_hour_s": p["move_hour_s"],
                     "fomc_in_macro": any("FOMC" in (m.get("event") or "") for m in (p.get("macro") or {}).get(
                         "releases", [])), "macro_error": (p.get("macro") or {}).get("error"),
                     "news": len(news), "news_public_before_hour_end": sum(1 for n in news
                                                                           if (n.get("published_ts") or 1e20) <= end),
                     "book": p.get("book")})
    outs = {_p(r)["move_id"]: _p(r)["ret_24h_after"] for r in q("SELECT payload FROM events WHERE "
                                                                 "kind='opportunity.outcome'")}
    for x in recs:
        x["outcome_24h"] = outs.get(x["id"])
    return {"flags": flags, "scans": len(scans), "scan_delay_s": {"max": max(delays), "median": statistics.median(delays)}
            if delays else None, "problems": problems, "records": recs}


def newschain(q, t):
    """Point 4: the Fed's own release time against when news-watch stored it; other macro sources; duplicates."""
    def items(src, lo, hi):
        return [(r["ts"], _p(r)) for r in q("SELECT ts, payload FROM observations WHERE detector='news/1' AND "
                                            "metric='news_item' AND source=? AND json_extract(payload, "
                                            "'$.published_ts') BETWEEN ? AND ? ORDER BY ts", src, lo, hi)]
    fed = [{"title": p.get("title"), "published_ts": p.get("published_ts"), "stored_ts": ts,
            "latency_s": ts - p["published_ts"]} for ts, p in items(FED, t - 1800, t + 2 * HOUR)]
    other = {}
    titles = [x["title"] for x in fed]
    for name, src in OTHER_MACRO.items():
        got = items(src, t - 1800, t + 2 * HOUR)
        titles += [p.get("title") for _, p in got]
        other[name] = {"items": len(got), "first_latency_s": min((ts - p["published_ts"] for ts, p in got), default=None)}
    norm = [" ".join((x or "").lower().split()) for x in titles]
    errors = [{"ts": r["ts"], "source": r["source"]} for r in q(
        "SELECT ts, source FROM observations WHERE detector='news/1' AND metric='news_error' AND ts BETWEEN ? AND ?",
        t - HOUR, t + 25 * HOUR)]
    latest = q("SELECT ts, payload FROM observations WHERE detector='news/1' AND metric='news_item' AND source=? AND "
               "ts<=? ORDER BY json_extract(payload, '$.published_ts') DESC LIMIT 1", FED, t + 2 * HOUR)
    lp = _p(latest[0]) if latest else {}
    return {"fed": fed, "fed_status": "ok" if fed else "mangler",                         # 21d precision 2026-10-25
            "fed_latest_stored": {"title": lp.get("title"), "published_ts": lp.get("published_ts"),
                                  "stored_ts": latest[0]["ts"],
                                  "label": "forældet" if (lp.get("published_ts") or 0) < t - 1800 else "i vinduet"}
            if latest else None,
            "fed_errors": sum(1 for e in errors if e["source"] == FED),
            "other_macro": other, "duplicate_titles": len(norm) - len(set(norm)), "news_errors": errors}


def report(q, get, t, now=None):
    now = now or time.time()
    if now < t + 25 * HOUR:
        raise ValueError("the 24 h window is not closed yet (amendment 21d point 7: after T + 25 h)")
    return {"rule": RULE, "event": "FOMC statement", "T": t, "T_utc": datetime.fromtimestamp(t, timezone.utc).isoformat(),
            "label": "DESCRIPTIVE integration test - one event, never evidence for a strategy", "generated": now,
            "markets": {s: {"label": moves.WATCH[s][1], **market(get, s, t)} for s in moves.WATCH},
            "scanner": scanner(q, t), "news": newschain(q, t)}


def readonly(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return lambda sql, *a: con.execute(sql, a).fetchall()


def main(argv=None):
    from lab import news
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/lab/lab.db")
    ap.add_argument("--at", default="2026-10-28T18:00:00+00:00")
    ap.add_argument("--out", help="write <out>.json")
    a = ap.parse_args(argv)
    t = int(datetime.fromisoformat(a.at).timestamp())
    rep = report(readonly(a.db), lambda url: json.loads(news.http_get(url)), t)
    text = json.dumps(rep, indent=1, sort_keys=True, default=str)
    if a.out:
        with open(a.out + ".json", "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
