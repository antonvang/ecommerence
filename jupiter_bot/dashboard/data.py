"""Read-only data for the dashboard. Every function here only READS.

The journal is opened with `Journal(path, readonly=True)` per call (SQLite
`mode=ro`); research, paper and execution files are read if they exist and
reported as absent otherwise. Nothing is created, repaired or cached on disk.

All functions return plain dicts that `json.dumps` can encode. Times are Unix
seconds (UTC). Prices are USDC per SOL, computed from integer atoms with the
decimals in `core` (USDC 6, SOL 9).

Large tables have no time index, and the dashboard may not create one. Recent
rows are found by binary search on the rowid (rows are appended in time
order), so a request reads the last day, not the whole multi-GB journal.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from bisect import bisect_right
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .. import ops
from ..core import ASSETS, SOL, USDC, Rejected, atoms, strict_json
from ..marketdata.journal import Journal

REPO = Path(__file__).resolve().parents[2]
DAY = 86400.0

# The collector's two fixed quote sizes (marketdata/collect.py SCHEDULE).
BUY_IN_ATOMS = atoms("25", USDC)        # 25 USDC -> SOL
SELL_IN_ATOMS = atoms("0.35", SOL)      # 0.35 SOL -> USDC
CANDLE_SOURCE, CANDLE_INSTRUMENT, CANDLE_INTERVAL = "binance_spot_klines", "SOL/USDC", 60
MATCH_WINDOW = 120.0                    # a quote is compared with a bar closed at most this long before
MAX_POINTS = 720
BUCKETS = (60, 120, 300, 600, 900, 1800, 3600, 7200, 14400)

# Rows of the "Indsamling" table: (source, instrument or None, Danish label).
SOURCE_ROWS = (
    ("binance_spot_klines", "SOL/USDC", "Binance 1m-candles SOL/USDC"),
    ("jupiter_quote", "USDC/SOL", "Jupiter køb 25 USDC → SOL"),
    ("jupiter_quote", "SOL/USDC", "Jupiter salg 0,35 SOL → USDC"),
    ("solana_status", None, "Solana status"),
    ("jupiter_status", None, "Jupiter status"),
    ("agave_releases", None, "Agave releases"),
)
NOT_ERRORS = ("OK", "COOLDOWN")          # COOLDOWN = deliberately skipped, no request sent

MANDATE_FIELDS = ("wallet_pubkey", "max_position_usdc", "max_trade_usdc", "daily_loss_limit_usdc",
                  "allowed_mints", "expires_at")
MODES = ("DISARMED", "DRY_RUN", "LIVE")
ORDER_FIELDS = ("total", "pending", "confirmed", "failed", "unknown")
BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
MAX_EVALUATIONS = 500


@dataclass(frozen=True)
class Paths:
    journal: Path
    data_dir: Path
    mandate: Path
    repo: Path = REPO

    @classmethod
    def defaults(cls, journal=None, data_dir=None, mandate=None, repo=None):
        home = Path.home()
        data_dir = Path(data_dir) if data_dir else home / ".local" / "share" / "jupiter-bot"
        return cls(journal=Path(journal) if journal else data_dir / "observations.db",
                   data_dir=data_dir,
                   mandate=Path(mandate) if mandate else home / ".config" / "jupiter-bot" / "mandate.json",
                   repo=Path(repo) if repo else REPO)

    @property
    def research(self):
        return self.data_dir / "research"

    @property
    def plan_lock(self):
        return self.research / "plan_lock.json"

    @property
    def evaluations(self):
        return self.research / "evaluations"

    @property
    def forward_paper(self):
        return self.research / "forward"

    @property
    def backups(self):
        return self.data_dir / "backups"

    @property
    def health_state(self):
        return self.data_dir / "health-state.json"

    @property
    def execution_db(self):
        return self.data_dir / "execution.db"

    @property
    def plan_md(self):
        return self.repo / "jupiter_bot" / "research" / "P2_PLAN.md"

    @property
    def execution_package(self):
        return self.repo / "jupiter_bot" / "execution"


# Pure helpers ----------------------------------------------------------------

def price_usdc_per_sol(input_mint, output_mint, in_amount, out_amount):
    """USDC per SOL from integer atoms, exact. USDC->SOL is a buy, SOL->USDC a sell."""
    if isinstance(in_amount, bool) or isinstance(out_amount, bool) \
            or not isinstance(in_amount, int) or not isinstance(out_amount, int):
        raise Rejected("Amounts must be integer atoms")
    if in_amount <= 0 or out_amount <= 0:
        raise Rejected("Amounts must be positive")
    if (input_mint, output_mint) == (USDC.mint, SOL.mint):
        usdc, sol = in_amount, out_amount
    elif (input_mint, output_mint) == (SOL.mint, USDC.mint):
        usdc, sol = out_amount, in_amount
    else:
        raise Rejected("Not a SOL/USDC quote")
    return (Decimal(usdc) / Decimal(10) ** USDC.decimals) / (Decimal(sol) / Decimal(10) ** SOL.decimals)


def side_of(input_mint, output_mint):
    if (input_mint, output_mint) == (USDC.mint, SOL.mint):
        return "buy"
    if (input_mint, output_mint) == (SOL.mint, USDC.mint):
        return "sell"
    return None


def gap_bps(side, jupiter_price, reference_price):
    """Jupiter's executable price vs the Binance close, in bps; positive = worse than Binance.

    buy:  paying more USDC per SOL than Binance  -> positive
    sell: receiving fewer USDC per SOL than Binance -> positive
    """
    jupiter_price, reference_price = Decimal(jupiter_price), Decimal(reference_price)
    if reference_price <= 0:
        raise Rejected("Reference price must be positive")
    if side == "buy":
        diff = jupiter_price - reference_price
    elif side == "sell":
        diff = reference_price - jupiter_price
    else:
        raise Rejected("Unknown side")
    return diff / reference_price * 10000


def bucket_seconds(hours, max_points=MAX_POINTS):
    span = hours * 3600.0
    for size in BUCKETS:
        if span / size <= max_points:
            return size
    return BUCKETS[-1]


def first_rowid_since(db, table, column, since):
    """Smallest rowid whose `column` >= since, assuming rows were appended in time order."""
    low_high = db.execute("SELECT min(rowid), max(rowid) FROM %s" % table).fetchone()
    low, high = low_high[0], low_high[1]
    if low is None:
        return None
    last = db.execute("SELECT %s FROM %s WHERE rowid=?" % (column, table), (high,)).fetchone()
    if last is None or last[0] < since:
        return high + 1
    while low < high:
        middle = (low + high) // 2
        row = db.execute("SELECT %s FROM %s WHERE rowid>=? ORDER BY rowid LIMIT 1" % (column, table),
                         (middle,)).fetchone()
        if row[0] < since:
            low = middle + 1
        else:
            high = middle
    return low


def _float(value, digits=None):
    if value is None:
        return None
    try:
        number = float(Decimal(str(value)))
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits) if digits is not None else number


def _file_info(path):
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return {"path": str(path), "bytes": stat.st_size, "modified_at": stat.st_mtime}


def _read_json(path, max_bytes=50 * 1024 * 1024):
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise Rejected("File too large")
    return strict_json(path.read_text(encoding="utf-8"))


def _open(paths):
    """(journal, error). The journal must exist and be ours; it is opened read-only."""
    if not Path(paths.journal).is_file():
        return None, "Journal findes ikke: %s" % paths.journal
    try:
        return Journal(paths.journal, readonly=True), None
    except (Rejected, sqlite3.Error) as exc:
        return None, "Journal kan ikke læses: %s" % exc


# Overview: status bar + collection ---------------------------------------------

def _last_ok(db, cutoff, source, instrument=None):
    clause, args = "source=? AND outcome='OK'", [source]
    if instrument is not None:
        clause += " AND instrument=?"
        args.append(instrument)
    if cutoff is not None:
        row = db.execute("SELECT max(requested_at) FROM fetches WHERE rowid>=? AND " + clause,
                         [cutoff] + args).fetchone()
        if row[0] is not None:
            return row[0]
    row = db.execute("SELECT requested_at FROM fetches WHERE " + clause + " ORDER BY rowid DESC LIMIT 1",
                     args).fetchone()
    return row[0] if row else None


def _candle_stats(db, now):
    key = (CANDLE_SOURCE, CANDLE_INSTRUMENT, CANDLE_INTERVAL)
    count, first, last = db.execute(
        "SELECT count(*), min(start), max(start) FROM candles WHERE source=? AND instrument=? AND interval_s=?",
        key).fetchone()
    starts = [row[0] for row in db.execute(
        "SELECT start FROM candles WHERE source=? AND instrument=? AND interval_s=? AND start>=? ORDER BY start",
        key + (now - DAY,))]
    gaps = [dict(after=a, before=b, missing=int(round((b - a) / CANDLE_INTERVAL)) - 1)
            for a, b in zip(starts, starts[1:]) if b - a != CANDLE_INTERVAL]
    missing_total = int(round((last - first) / CANDLE_INTERVAL)) + 1 - count if count else 0
    return {"bars": count, "first_start": first, "last_start": last,
            "last_end": last + CANDLE_INTERVAL if last is not None else None,
            "bars_24h": len(starts), "gaps_24h": len(gaps), "missing_bars_24h": sum(g["missing"] for g in gaps),
            "missing_bars_total": missing_total, "recent_gaps": gaps[-10:]}


def _backups(paths, now):
    directory = paths.backups
    try:
        names = sorted(p.name for p in directory.iterdir() if ops.BACKUP_NAME.match(p.name))
    except OSError:
        names = []
    if not names:
        return {"count": 0, "newest": None}
    newest = directory / names[-1]
    info = _file_info(newest) or {}
    return {"count": len(names), "newest": {"name": names[-1], "date": names[-1][13:23],
                                            "bytes": info.get("bytes"), "modified_at": info.get("modified_at"),
                                            "age_s": now - info["modified_at"] if info else None},
            "total_bytes": sum((_file_info(directory / n) or {}).get("bytes", 0) for n in names)}


def _health_state(paths, now):
    info = _file_info(paths.health_state)
    if info is None:
        return {"exists": False}
    try:
        state = _read_json(paths.health_state)
        stale = [str(s) for s in state.get("stale", [])] if isinstance(state, dict) else []
    except Exception as exc:
        return {"exists": True, "error": str(exc), "age_s": now - info["modified_at"]}
    return {"exists": True, "stale": stale, "age_s": now - info["modified_at"],
            "modified_at": info["modified_at"]}


def overview(paths, now=None):
    now = time.time() if now is None else now
    journal_files = [_file_info(Path(str(paths.journal) + suffix)) for suffix in ("", "-wal", "-shm")]
    result = {"now": now, "journal": {"path": str(paths.journal), "exists": journal_files[0] is not None,
                                      "bytes": sum(f["bytes"] for f in journal_files if f)},
              "backups": _backups(paths, now), "health_state": _health_state(paths, now)}
    journal, error = _open(paths)
    if journal is None:
        result.update(status={"level": "error", "problems": [error], "warnings": []},
                      sources=[], candles=None, last_cycle_at=None, first_fetch_at=None, days_collected=0)
        return result
    try:
        db = journal.db
        first = db.execute("SELECT requested_at FROM fetches ORDER BY rowid LIMIT 1").fetchone()
        last = db.execute("SELECT requested_at FROM fetches ORDER BY rowid DESC LIMIT 1").fetchone()
        cutoff = first_rowid_since(db, "fetches", "requested_at", now - DAY)
        hour_cutoff = first_rowid_since(db, "fetches", "requested_at", now - 3600)
        counts = {}
        if cutoff is not None:
            for row in db.execute("""SELECT source, coalesce(instrument, '') AS instrument, outcome, count(*) AS n
                                     FROM fetches WHERE rowid>=? AND requested_at>=?
                                     GROUP BY source, instrument, outcome""", (cutoff, now - DAY)):
                counts.setdefault((row["source"], row["instrument"]), {})[row["outcome"]] = row["n"]
        recent_errors = {}
        if hour_cutoff is not None:
            for row in db.execute("""SELECT source, coalesce(instrument, '') AS instrument, count(*) AS n
                                     FROM fetches WHERE rowid>=? AND requested_at>=? AND outcome NOT IN (?, ?)
                                     GROUP BY source, instrument""", (hour_cutoff, now - 3600) + NOT_ERRORS):
                recent_errors[(row["source"], row["instrument"])] = row["n"]
        sources = []
        for source, instrument, label in SOURCE_ROWS:
            by_outcome = counts.get((source, instrument or ""), {})
            ok = by_outcome.get("OK", 0)
            skipped = by_outcome.get("COOLDOWN", 0)
            errors = sum(n for outcome, n in by_outcome.items() if outcome not in NOT_ERRORS)
            last_ok = _last_ok(db, cutoff, source, instrument)
            last_error = None
            if errors and cutoff is not None:
                clause = "source=?" + (" AND instrument=?" if instrument else "")
                row = db.execute("SELECT requested_at, outcome, error FROM fetches WHERE rowid>=? AND "
                                 + clause + " AND outcome NOT IN (?, ?) ORDER BY rowid DESC LIMIT 1",
                                 [cutoff, source] + ([instrument] if instrument else []) + list(NOT_ERRORS)).fetchone()
                if row is not None:
                    last_error = {"at": row["requested_at"], "outcome": row["outcome"], "error": row["error"]}
            limit = ops.MAX_AGE.get(source)
            sources.append({
                "source": source, "instrument": instrument, "label": label,
                "last_ok_at": last_ok, "last_ok_age_s": now - last_ok if last_ok is not None else None,
                "max_age_s": limit, "stale": last_ok is None or (limit is not None and now - last_ok > limit),
                "ok_24h": ok, "errors_24h": errors, "skipped_24h": skipped,
                "error_rate_24h": errors / (ok + errors) if ok + errors else None,
                "errors_1h": recent_errors.get((source, instrument or ""), 0),
                "outcomes_24h": by_outcome, "last_error": last_error})
        last_ok_per_source = {}
        for row in sources:
            if row["last_ok_at"] is not None:
                last_ok_per_source[row["source"]] = max(last_ok_per_source.get(row["source"], 0.0), row["last_ok_at"])
        problems = ops.stale_sources(
            {"outcomes": [{"source": s, "outcome": "OK", "last": t} for s, t in last_ok_per_source.items()]}, now)
        candles = _candle_stats(db, now)
    finally:
        journal.close()
    last_cycle = last[0] if last else None
    warnings = []
    if last_cycle is None:
        problems = problems + ["ingen kald i journalen endnu"]
    elif now - last_cycle > 180:
        warnings.append("seneste cyklus for %d min siden (forventet hvert minut)" % ((now - last_cycle) // 60))
    for row in sources:
        if row["errors_1h"]:
            warnings.append("%s: %d fejl den seneste time" % (row["label"], row["errors_1h"]))
    if candles["gaps_24h"]:
        warnings.append("%d hul(ler) i Binance-candles de seneste 24 t" % candles["gaps_24h"])
    backups = result["backups"]
    if not backups["count"]:
        warnings.append("ingen backup fundet")
    elif backups["newest"]["age_s"] is not None and backups["newest"]["age_s"] > 2 * DAY:
        warnings.append("nyeste backup er over 2 døgn gammel")
    health = result["health_state"]
    if not health.get("exists"):
        warnings.append("alarm-timeren har ikke kørt (ingen health-state.json)")
    elif health.get("age_s", 0) > 3600:
        warnings.append("alarm-timeren har ikke kørt i over en time")
    level = "error" if problems else ("warning" if warnings else "ok")
    result.update(status={"level": level, "problems": problems, "warnings": warnings},
                  sources=sources, candles=candles, last_cycle_at=last_cycle,
                  first_fetch_at=first[0] if first else None,
                  days_collected=(now - first[0]) / DAY if first else 0)
    return result


# Market -------------------------------------------------------------------------

def _bucketed(points, size, reducer):
    """[(t, value)] -> [[bucket_end, reduce(values)]], buckets aligned to `size`."""
    buckets = {}
    for t, value in points:
        buckets.setdefault(math.floor(t / size) * size, []).append(value)
    return [[start + size, reducer(values)] for start, values in sorted(buckets.items())]


def market(paths, hours=24, now=None):
    now = time.time() if now is None else now
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        hours = 24.0
    hours = min(max(hours if math.isfinite(hours) else 24.0, 1.0), 24.0 * 31)
    size = bucket_seconds(hours)
    since = now - hours * 3600
    empty = {"now": now, "hours": hours, "bucket_s": size, "since": since,
             "series": {k: [] for k in ("binance", "buy", "sell", "gap_buy", "gap_sell")}, "latest": {},
             "summary": {}, "counts": {"bars": 0, "quotes_buy": 0, "quotes_sell": 0, "unmatched": 0,
                                       "other_sizes": 0}}
    journal, error = _open(paths)
    if journal is None:
        return dict(empty, error=error)
    try:
        db = journal.db
        bars = [(row["end"], Decimal(row["close"])) for row in db.execute(
            """SELECT end, close FROM candles WHERE source=? AND instrument=? AND interval_s=? AND start>=?
               ORDER BY start""", (CANDLE_SOURCE, CANDLE_INSTRUMENT, CANDLE_INTERVAL, since - MATCH_WINDOW))]
        cutoff = first_rowid_since(db, "quotes", "observed_at", since)
        quotes = [] if cutoff is None else [tuple(row) for row in db.execute(
            """SELECT input_mint, output_mint, in_amount, out_amount, observed_at, router FROM quotes
               WHERE rowid>=? AND observed_at>=? ORDER BY rowid""", (cutoff, since))]
    finally:
        journal.close()
    ends = [end for end, _ in bars]
    prices = {"buy": [], "sell": []}
    gaps = {"buy": [], "sell": []}
    latest = {}
    unmatched = other_sizes = 0
    for input_mint, output_mint, in_amount, out_amount, observed_at, router in quotes:
        side = side_of(input_mint, output_mint)
        if side is None:
            continue
        if in_amount != (BUY_IN_ATOMS if side == "buy" else SELL_IN_ATOMS):
            other_sizes += 1
            continue
        try:
            price = price_usdc_per_sol(input_mint, output_mint, in_amount, out_amount)
        except Rejected:
            continue
        prices[side].append((observed_at, price))
        latest[side] = {"at": observed_at, "price": _float(price, 6), "router": router,
                        "in_amount": in_amount, "out_amount": out_amount}
        index = bisect_right(ends, observed_at) - 1
        if index >= 0 and observed_at - ends[index] <= MATCH_WINDOW:
            bps = gap_bps(side, price, bars[index][1])
            gaps[side].append((observed_at, bps))
            latest[side]["gap_bps"] = _float(bps, 2)
            latest[side]["reference_close"] = _float(bars[index][1], 6)
        else:
            unmatched += 1
    in_window = [(end, close) for end, close in bars if end >= since]
    if in_window:
        latest["binance"] = {"at": in_window[-1][0], "close": _float(in_window[-1][1], 6)}

    def median(values):
        return float(statistics.median(values))

    series = {
        "binance": [[t, round(float(v), 6)] for t, v in _bucketed(in_window, size, lambda vs: vs[-1])],
        "buy": [[t, round(v, 6)] for t, v in _bucketed(prices["buy"], size, median)],
        "sell": [[t, round(v, 6)] for t, v in _bucketed(prices["sell"], size, median)],
        "gap_buy": [[t, round(v, 2)] for t, v in _bucketed(gaps["buy"], size, median)],
        "gap_sell": [[t, round(v, 2)] for t, v in _bucketed(gaps["sell"], size, median)],
    }
    closes = [close for _, close in in_window]
    summary = {
        "binance_first": _float(closes[0], 6) if closes else None,
        "binance_last": _float(closes[-1], 6) if closes else None,
        "binance_min": _float(min(closes), 6) if closes else None,
        "binance_max": _float(max(closes), 6) if closes else None,
        "binance_change_pct": _float((closes[-1] / closes[0] - 1) * 100, 3) if closes else None,
        "gap_buy_median_bps": round(median([g for _, g in gaps["buy"]]), 2) if gaps["buy"] else None,
        "gap_sell_median_bps": round(median([g for _, g in gaps["sell"]]), 2) if gaps["sell"] else None,
        "round_trip_median_bps": None,
    }
    if gaps["buy"] and gaps["sell"]:
        summary["round_trip_median_bps"] = round(summary["gap_buy_median_bps"] + summary["gap_sell_median_bps"], 2)
    return dict(empty, series=series, latest=latest, summary=summary,
                counts={"bars": len(in_window), "quotes_buy": len(prices["buy"]),
                        "quotes_sell": len(prices["sell"]), "unmatched": unmatched, "other_sizes": other_sizes})


# Research -----------------------------------------------------------------------

def _window(value):
    if not isinstance(value, dict):
        return None
    start, end = _float(value.get("start")), _float(value.get("end"))
    if start is None or end is None or end <= start:
        return None
    return {"start": start, "end": end}


def _progress(window, data_first, data_last, now):
    if window is None:
        return None
    span = window["end"] - window["start"]
    covered = 0.0
    if data_first is not None and data_last is not None:
        covered = max(0.0, min(data_last, window["end"]) - max(data_first, window["start"]))
    elapsed = min(max(now - window["start"], 0.0), span)
    state = "ikke startet" if now < window["start"] else ("afsluttet" if now >= window["end"] else "i gang")
    return dict(window, days=span / DAY, covered_days=covered / DAY, covered_share=covered / span,
                elapsed_share=elapsed / span, state=state)


def _data_span(paths):
    journal, _ = _open(paths)
    if journal is None:
        return None, None
    try:
        row = journal.db.execute(
            "SELECT min(start), max(end) FROM candles WHERE source=? AND instrument=? AND interval_s=?",
            (CANDLE_SOURCE, CANDLE_INSTRUMENT, CANDLE_INTERVAL)).fetchone()
        return row[0], row[1]
    finally:
        journal.close()


_evaluation_cache = {}


def _evaluation_row(path):
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _evaluation_cache:
        return _evaluation_cache[key]
    run = _read_json(path)
    if not isinstance(run, dict):
        raise Rejected("Not a JSON object")
    metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
    benchmarks = run.get("benchmarks") if isinstance(run.get("benchmarks"), dict) else {}
    controls = run.get("controls") if isinstance(run.get("controls"), dict) else {}
    random_entries = controls.get("random_entries") if isinstance(controls.get("random_entries"), dict) else {}
    shuffled = controls.get("shuffled_signals") if isinstance(controls.get("shuffled_signals"), dict) else {}
    period = _window(run.get("period"))
    ret, hold = _float(metrics.get("return_pct")), _float(benchmarks.get("hold_sol_return_pct"))
    verdict = run.get("verdict")
    row = {
        "file": path.name, "run_id": str(run.get("run_id", path.stem)), "created_at": _float(run.get("created_at")),
        "label": str(run.get("label", "")), "strategy": str(run.get("strategy", "")),
        "params": run.get("params") if isinstance(run.get("params"), dict) else {},
        "delay_s": _float(run.get("delay_s")), "extra_cost_bps": _float(run.get("extra_cost_bps")),
        "period": period, "plan_sha256": run.get("plan_sha256"),
        "return_pct": ret, "hold_sol_return_pct": hold,
        "excess_vs_hold_pct": ret - hold if ret is not None and hold is not None else None,
        "max_drawdown_pct": _float(metrics.get("max_drawdown_pct")),
        "trades": metrics.get("trades"), "missing": metrics.get("missing"),
        "random_runs": random_entries.get("runs"),
        "random_share_beating": _float(random_entries.get("share_beating_strategy")),
        "shuffled_share_beating": _float(shuffled.get("share_beating_strategy")),
        "verdict": verdict if verdict is None or isinstance(verdict, (str, int, float, bool)) else json.dumps(verdict),
    }
    _evaluation_cache[key] = row
    return row


def evaluations(paths):
    directory = paths.evaluations
    try:
        files = sorted(p for p in directory.iterdir() if p.suffix == ".json" and p.is_file())
    except OSError:
        return {"exists": False, "runs": [], "errors": []}
    runs, errors = [], []
    for path in files[-MAX_EVALUATIONS:]:
        try:
            runs.append(_evaluation_row(path))
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
    runs.sort(key=lambda r: (r["created_at"] or 0.0, r["run_id"]), reverse=True)
    return {"exists": True, "runs": runs, "errors": errors, "truncated": len(files) > MAX_EVALUATIONS}


def research(paths, now=None):
    now = time.time() if now is None else now
    lock = {"exists": paths.plan_lock.is_file()}
    state = "draft" if paths.plan_md.is_file() else "missing"
    if lock["exists"]:
        try:
            raw = _read_json(paths.plan_lock)
            if not isinstance(raw, dict):
                raise Rejected("Not a JSON object")
            code = raw.get("code_sha256") if isinstance(raw.get("code_sha256"), dict) else {}
            lock.update(plan_path=raw.get("plan_path"), plan_sha256=raw.get("plan_sha256"),
                        code_sha256={str(k): str(v) for k, v in code.items()}, git_commit=raw.get("git_commit"),
                        locked_at=_float(raw.get("locked_at")), approved_by=raw.get("approved_by"),
                        development=_window(raw.get("development")), holdout=_window(raw.get("holdout")))
            state = "locked"
        except Exception as exc:
            lock["error"] = str(exc)
            state = "invalid"
    data_first, data_last = _data_span(paths)
    evals = evaluations(paths)
    locked_hash = lock.get("plan_sha256") if state == "locked" else None
    for run in evals["runs"]:
        run["matches_lock"] = (run["plan_sha256"] == locked_hash) if locked_hash else None
    return {"now": now, "state": state, "plan_md_exists": paths.plan_md.is_file(), "lock": lock,
            "data": {"first": data_first, "last": data_last,
                     "days": (data_last - data_first) / DAY if data_first is not None else 0.0},
            "progress": {"development": _progress(lock.get("development"), data_first, data_last, now),
                         "holdout": _progress(lock.get("holdout"), data_first, data_last, now)},
            "evaluations": evals}


# Forward paper view (research/forward/*.json, written by research.forward) -------------

FORWARD_POINTS = 400


def _downsample(points, limit=FORWARD_POINTS):
    if len(points) <= limit:
        return points
    step = len(points) / float(limit)
    picked = [points[int(i * step)] for i in range(limit)]
    return picked[:-1] + [points[-1]]


def _sol_path(paths, start, end, times):
    """SOL price change in % since `start`, from Binance closes, at the given times (reference line)."""
    journal, _ = _open(paths)
    if journal is None or not times:
        return []
    try:
        rows = journal.db.execute(
            """SELECT end, close FROM candles WHERE source='binance_spot_klines' AND instrument='SOL/USDC'
               AND interval_s=60 AND end>=? AND end<=? ORDER BY end""", (start, end)).fetchall()
    finally:
        journal.close()
    if not rows:
        return []
    base = float(rows[0][1])
    result, j = [], 0
    for t in times:
        while j + 1 < len(rows) and rows[j + 1][0] <= t:
            j += 1
        if rows[j][0] <= t:
            result.append([t, (float(rows[j][1]) / base - 1) * 100])
    return result


def load_forward_paper(paths):
    """The only place that knows the forward view files. Read-only."""
    directory = paths.forward_paper
    try:
        files = sorted(p for p in directory.iterdir() if p.suffix == ".json" and p.is_file())
    except OSError:
        return {"exists": False, "configs": []}
    configs, errors = [], []
    for path in files:
        try:
            run = _read_json(path)
            metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
            bench = run.get("benchmarks") if isinstance(run.get("benchmarks"), dict) else {}
            period = _window(run.get("period"))
            initial = 25.01
            equity = [[float(t), (float(v) / initial - 1) * 100] for t, v in (run.get("equity") or [])]
            equity = _downsample(equity)
            sol = _sol_path(paths, period["start"], period["end"], [t for t, _ in equity]) if period else []
            target = run.get("now_target")
            configs.append({
                "file": path.name, "strategy": str(run.get("strategy", "")),
                "params": run.get("params") if isinstance(run.get("params"), dict) else {},
                "grid_index": run.get("grid_index"), "status": str(run.get("status", "")),
                "error": run.get("error"), "updated_at": _float(run.get("updated_at")), "period": period,
                "return_pct": _float(metrics.get("return_pct")),
                "hold_sol_return_pct": _float(bench.get("hold_sol_return_pct")),
                "max_drawdown_pct": _float(metrics.get("max_drawdown_pct")),
                "trades": metrics.get("trades"), "round_trips": metrics.get("round_trips"),
                "missing_quotes": metrics.get("missing_quotes"),
                "open_position": bool(metrics.get("open_position_at_end")),
                "now_target": target if isinstance(target, str) else None,
                "series": {"strategy": equity, "sol": sol},
            })
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
    return {"exists": True, "configs": configs, "errors": errors}


def paper(paths, now=None):
    return dict(load_forward_paper(paths), now=time.time() if now is None else now)


def load_mandate(path):
    """Whitelisted mandate fields only. Unknown fields are counted, never shown."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        raw = _read_json(path, max_bytes=1024 * 1024)
    except Exception as exc:
        return {"error": "mandate.json kan ikke læses: %s" % exc}
    return _safe_mandate(raw)


def _safe_mandate(raw):
    if not isinstance(raw, dict):
        return {"error": "mandate.json er ikke et JSON-objekt"}
    mandate = {"hidden_fields": len([k for k in raw if k not in MANDATE_FIELDS]), "warnings": []}
    pubkey = raw.get("wallet_pubkey")
    if isinstance(pubkey, str) and BASE58.match(pubkey):
        mandate["wallet_pubkey"] = pubkey
    elif pubkey is not None:
        mandate["warnings"].append("wallet_pubkey ligner ikke en offentlig nøgle og vises ikke")
    for field in ("max_position_usdc", "max_trade_usdc", "daily_loss_limit_usdc", "expires_at"):
        if field in raw:
            mandate[field] = _float(raw[field])
    mints = raw.get("allowed_mints")
    if isinstance(mints, list):
        symbols = {asset.mint: asset.symbol for asset in ASSETS.values()}
        mandate["allowed_mints"] = [{"mint": m, "symbol": symbols.get(m)} for m in mints
                                    if isinstance(m, str) and BASE58.match(m)]
    return mandate


def run_execution_status(paths, timeout=15):
    """The documented read interface: `python3 -m jupiter_bot.execution status --json`."""
    completed = subprocess.run([sys.executable, "-m", "jupiter_bot.execution", "status", "--json"],
                               cwd=str(paths.repo), capture_output=True, timeout=timeout, check=False,
                               stdin=subprocess.DEVNULL)
    if completed.returncode != 0:
        raise Rejected("execution status exit %d" % completed.returncode)
    return strict_json(completed.stdout.decode("utf-8"))


_status_cache = {}


def execution(paths, now=None, runner=None, cache_s=30):
    now = time.time() if now is None else now
    mandate = load_mandate(paths.mandate)
    built = paths.execution_package.is_dir()
    result = {"now": now, "built": built, "mode": "DISARMED", "armed": False, "mandate": mandate,
              "mandate_exists": mandate is not None, "ledger_exists": paths.execution_db.is_file(),
              "gates": [], "orders": None, "today_realized_pnl_usdc": None, "status_error": None}
    status = None
    if built:
        cached = _status_cache.get(str(paths.repo))
        if runner is None and cached and now - cached[0] < cache_s:
            status = cached[1]
        else:
            try:
                status = (runner or run_execution_status)(paths)
                if runner is None:
                    _status_cache[str(paths.repo)] = (now, status)
            except Exception as exc:
                result["status_error"] = str(exc)
    if isinstance(status, dict):
        mode = status.get("mode")
        result["mode"] = mode if mode in MODES else "UKENDT"
        result["armed"] = status.get("armed") is True
        if status.get("mandate") is not None:
            result["mandate"] = _safe_mandate(status["mandate"])
        gates = status.get("gates") if isinstance(status.get("gates"), list) else []
        result["gates"] = [{"name": str(g.get("name", "")), "ok": g.get("ok") if isinstance(g.get("ok"), bool) else None,
                            "detail": str(g.get("detail", ""))} for g in gates if isinstance(g, dict)]
        orders = status.get("orders") if isinstance(status.get("orders"), dict) else {}
        result["orders"] = {k: orders.get(k) if isinstance(orders.get(k), int) else None for k in ORDER_FIELDS}
        result["today_realized_pnl_usdc"] = _float(status.get("today_realized_pnl_usdc"))
    else:
        result["gates"] = _known_gates(paths, mandate, now)
    return result


def _known_gates(paths, mandate, now):
    """Before execution exists: what can be read from files, without judging any result."""
    holdout = [r for r in evaluations(paths)["runs"] if r["label"] == "holdout"]
    expires = mandate.get("expires_at") if isinstance(mandate, dict) else None
    return [
        {"name": "p2_plan_locked", "ok": paths.plan_lock.is_file(),
         "detail": "plan_lock.json findes" if paths.plan_lock.is_file() else "planen er ikke låst"},
        {"name": "p2_holdout_pass", "ok": None,
         "detail": "ingen holdout-kørsel endnu" if not holdout else
         "%d holdout-kørsel(er); afgøres af planens beslutningsregel" % len(holdout)},
        {"name": "mandate_present", "ok": isinstance(mandate, dict) and "error" not in mandate,
         "detail": "mandate.json findes" if mandate else "intet mandat (~/.config/jupiter-bot/mandate.json)"},
        {"name": "mandate_not_expired", "ok": (expires > now) if expires is not None else None,
         "detail": "udløber ikke før %s" % time.strftime("%Y-%m-%d", time.gmtime(expires)) if expires else "—"},
        {"name": "execution_built", "ok": paths.execution_package.is_dir(),
         "detail": "jupiter_bot/execution findes" if paths.execution_package.is_dir() else "ikke bygget"},
    ]
