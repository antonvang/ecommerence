"""HFC-1 (research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md): daily forward cohort of high-funding USDT perps
and their paper carry feasibility. Descriptive; decides nothing; touches no lab state.

  python3 research/tools/hfc1_daily.py cohort --day 2026-11-04   after 00:35 UTC the next day; one book read per leg
  python3 research/tools/hfc1_daily.py outcomes                  3 d / 14 d realised funding for every stored cohort

Reads lab.db read-only (census/1 snapshots). Network: data-api.binance.vision (spot exchangeInfo + depth) and
fapi.binance.com (perp depth), the hosts lab/paper_runner.py and lab/capacity.py already use; >= 0.25 s between calls.
"""
import calendar
import datetime as dt
import hashlib
import json
import os
import statistics as st
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = "file:/home/anton/ecommerence/copybot/data/lab/lab.db?mode=ro"
OUT = os.path.join(HERE, "research", "data", "hfc1")
SPOT, PERP = "https://data-api.binance.vision", "https://fapi.binance.com"
FIRST, LAST = dt.date(2026, 11, 4), dt.date(2026, 11, 24)
BE, M2 = 0.125, 0.188                     # APR thresholds (27.4 B)
TAKER, SLIP = 0.001, 0.0002               # lab cost model per side
SIZES = (1000.0, 5000.0)                  # USDT per leg
H = {"3d": 9, "14d": 42}                  # 8 h funding periods
MIN_SNAPS = 24
PAUSE = 0.25


def get(url):
    time.sleep(PAUSE)
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def snapshots(con, t0, t1):
    out = []
    for ts, p in con.execute("SELECT ts, payload FROM observations WHERE detector='census/1' AND metric='snapshot' "
                             "AND ts >= ? AND ts < ? ORDER BY ts", (t0, t1)):
        j = json.loads(p)
        cols = j["columns"]
        if "lastFundingRate" not in cols:
            continue
        i = cols.index("lastFundingRate")
        rates = {}
        for sym, row in j["rows"].items():
            if sym.endswith("USDT"):
                try:
                    rates[sym] = float(row[i])
                except (TypeError, ValueError, IndexError):
                    pass
        out.append((ts, rates, set(j.get("coin_perps") or [])))
    return out


def cohort_members(snaps):
    """C0: 72 h mean lastFundingRate x 1095 >= 12.5 % with >= MIN_SNAPS snapshots."""
    acc = {}
    for _, rates, _ in snaps:
        for s, v in rates.items():
            acc.setdefault(s, []).append(v)
    return {s: st.fmean(v) for s, v in acc.items() if len(v) >= MIN_SNAPS and st.fmean(v) * 1095 >= BE}


def walk(levels, notional, mid):
    """VWAP for `notional` USDT through [[price, qty], ...]; None if 20 levels do not suffice."""
    left, cost, qty = notional, 0.0, 0.0
    for p, q in levels:
        p, q = float(p), float(q)
        take = min(left, p * q)
        cost += take
        qty += take / p
        left -= take
        if left <= 1e-9:
            return cost / qty
    return None


def leg_cost(book, n):
    """Round trip on one leg at size n: (buy VWAP - sell VWAP)/mid x n + 2 sides x (taker + slippage) x n."""
    bids, asks = book.get("bids") or [], book.get("asks") or []
    if not bids or not asks:
        return None, None
    mid = (float(bids[0][0]) + float(asks[0][0])) / 2
    buy, sell = walk(asks, n, mid), walk(bids, n, mid)
    spread = (float(asks[0][0]) - float(bids[0][0])) / mid
    if buy is None or sell is None:
        return None, spread
    return (buy - sell) / mid * n + 2 * (TAKER + SLIP) * n, spread


def cohort(day):
    if not FIRST <= day <= LAST:
        sys.exit(f"refused: HFC-1 cohorts are {FIRST}..{LAST}")
    end = calendar.timegm(day.timetuple()) + 86400
    if time.time() < end + 35 * 60:
        sys.exit("refused: run after 00:35 UTC the next day")
    import sqlite3
    con = sqlite3.connect(DB, uri=True)
    snaps = snapshots(con, end - 3 * 86400, end)
    if not snaps:
        sys.exit("no census snapshots in the window")
    c0 = cohort_members(snaps)
    perps_trading = snaps[-1][2]
    raw_info = get(f"{SPOT}/api/v3/exchangeInfo?symbolStatus=TRADING")
    spot_ok = {s["symbol"] for s in json.loads(raw_info)["symbols"] if s.get("status") == "TRADING"}
    rows, books = [], {}
    for sym, f in sorted(c0.items()):
        r = {"symbol": sym, "f8h": f, "apr": f * 1095, "m2": f * 1095 >= M2}
        base = sym[:-4]
        if base[:1].isdigit():
            r["drop"] = "F1 multiplikator"
        elif sym not in spot_ok:
            r["drop"] = "F1 intet spotpar"
        elif sym not in perps_trading:
            r["drop"] = "F2 perp ikke TRADING"
        else:
            try:
                sb = json.loads(get(f"{SPOT}/api/v3/depth?symbol={sym}&limit=20"))
                pb = json.loads(get(f"{PERP}/fapi/v1/depth?symbol={sym}&limit=20"))
            except Exception as e:                               # noqa: BLE001 - recorded as a drop-out
                r["drop"] = f"F3 bog ikke hentet: {type(e).__name__}"
                rows.append(r)
                continue
            books[sym] = {"spot": sb, "perp": pb}
            r["spot_spread"], r["perp_spread"] = leg_cost(sb, SIZES[0])[1], leg_cost(pb, SIZES[0])[1]
            if r["spot_spread"] is None or r["perp_spread"] is None:
                r["drop"] = "F3 tom side"
            for n in SIZES:
                cs, cp = leg_cost(sb, n)[0], leg_cost(pb, n)[0]
                key = str(int(n))
                if cs is None or cp is None:
                    r[f"cost_{key}"] = None
                    r.setdefault("drop_size", []).append(f"F4 {key}")
                    continue
                r[f"cost_{key}"] = cs + cp
                for h, k in H.items():
                    r[f"covered_{h}_{key}"] = f * k * n >= cs + cp
        rows.append(r)
    os.makedirs(OUT, exist_ok=True)
    body = {"day": str(day), "run_ts": int(time.time()), "snapshots": len(snaps), "c0": len(c0),
            "spot_info_sha256": hashlib.sha256(raw_info).hexdigest(), "rows": rows, "books": books}
    raw = json.dumps(body, sort_keys=True).encode()
    path = os.path.join(OUT, f"{day}.json")
    with open(path, "wb") as fh:
        fh.write(raw)
    summary(body, hashlib.sha256(raw).hexdigest())


def summary(body, sha):
    rows = body["rows"]
    drops = {}
    for r in rows:
        if "drop" in r:
            drops[r["drop"].split(":")[0]] = drops.get(r["drop"].split(":")[0], 0) + 1
    passed = [r for r in rows if "drop" not in r]
    out = {"day": body["day"], "sha256": sha, "snapshots": body["snapshots"], "C0": body["c0"],
           "C0_m2": sum(r["m2"] for r in rows), "drops": drops, "books_ok": len(passed)}
    for n in ("1000", "5000"):
        ok = [r for r in passed if r.get(f"cost_{n}") is not None]
        out[f"F4_{n}"] = len(ok)
        for h in H:
            out[f"covered_{h}_{n}"] = sum(bool(r.get(f"covered_{h}_{n}")) for r in ok)
        if ok:
            out[f"median_cost_bp_{n}"] = round(st.median(r[f"cost_{n}"] / float(n) * 1e4 for r in ok), 1)
    print(json.dumps(out, ensure_ascii=False))


def outcomes():
    import sqlite3
    con = sqlite3.connect(DB, uri=True)
    for name in sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []:
        body = json.load(open(os.path.join(OUT, name)))
        day = dt.date.fromisoformat(body["day"])
        end = calendar.timegm(day.timetuple()) + 86400
        res = {"day": body["day"]}
        for h, k in H.items():
            t1 = end + k // 3 * 86400
            if time.time() < t1:
                res[h] = "endnu ikke"
                continue
            snaps = snapshots(con, end, t1)
            expect = k // 3 * 24                                 # hourly snapshots
            cov = []
            for r in body["rows"]:
                v = [s[1][r["symbol"]] for s in snaps if r["symbol"] in s[1]]
                n = "1000"
                cost = r.get(f"cost_{n}")
                if len(v) < 0.75 * expect or cost is None:
                    cov.append(None)                             # missing counts as not covered
                else:
                    cov.append(st.fmean(v) * k * float(n) / cost)
            res[h] = {"members": len(cov), "missing_or_no_cost": sum(c is None for c in cov),
                      "covered": sum(c is not None and c >= 1 for c in cov),
                      "median_coverage": round(st.median([c for c in cov if c is not None]), 2) if any(
                          c is not None for c in cov) else None}
        print(json.dumps(res, ensure_ascii=False))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["cohort"] and len(argv) == 3 and argv[1] == "--day":
        cohort(dt.date.fromisoformat(argv[2]))
    elif argv[:1] == ["outcomes"]:
        outcomes()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
