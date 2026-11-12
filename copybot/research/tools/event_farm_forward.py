"""Director order 100 (DESIGN ONLY): the event farm FORWARD paper book, isolated and not activated.

WHAT IT IS. A bar-by-bar paper book that runs the frozen engine (event_farm.py @ f686c9a, sha256 checked through
event_farm_driver.engine) on closed 5m bars and books every setup of the 12 registered variants with entry, stop and
target fixed at known_ts, the engine's conservative fill rules and the lab's paper-book costs (lab/lane.py COSTS:
taker 0.001, extra slippage 0.0002, expected spread 0.0004; every fill is treated as a taker fill). Simulation only.

WHAT IT IS NOT. It contains no network code and no data source: bars arrive only through an injected `source` object
with `provenance` and `fetch(symbol, since_ts)`. A live source (fapi 5m klines, described in
research/desk/EVENT_FARM_FORWARD_AMENDMENT_DRAFT_100.md) is NOT part of this module. Live mode raises NotActivated
unless an injected activation object approves it; nothing in the lab constructs one today. It writes only its own
SQLite file, whose name must be event_farm_forward*.db and which may not be a lab or pm_lp database.

RULES (fixed in FROZEN_CONFIG; live mode refuses any other config):
- a bar is stored only if it is on the 5m grid, has ts + 300 <= now (closed) and valid OHLC; anything else is logged
  in `rejected`. A re-delivered bar with other values is logged in `conflicts`; the first value is kept.
- bars are processed strictly in time order. A missing bar is waited for until a stored bar lies gap_wait_s beyond it;
  then the gap is recorded and processing continues. A bar arriving after its slot was passed is logged in `late_bars`
  and never processed (the engine does not rewind).
- the engine state is in memory and rebuilt on open by replaying the processed bars (deterministic). Each step is one
  SQLite transaction; an exception rolls it back and the memory state is rebuilt from the file (restart-safe).
- setups are booked in the step in which their bar is processed (bar time); booking_delay_s records the wall delay.
  Setups before warmup_bars, during a coverage pause, after the end date or in a stopped variant are recorded with a
  not_taken_* status and no outcome.
- outcomes: event_farm.setup_outcome on the processed bars (stop first on a bar that touches both; fill bar counts
  only the stop). A trade whose window contains a declared gap is gap_affected (primary statistics exclude it; a
  worst-case sensitivity books it as a stop).
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import statistics
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import event_farm_driver as drv  # noqa: E402

SCHEMA = "event_farm_forward/1"
BS = 300
LIVE_SYMBOLS = ("BTCUSDT", "ETHUSDT")
SYNTHETIC_SYMBOL = re.compile(r"^SYN[A-Z0-9_]{0,16}$")
DB_NAME = re.compile(r"^event_farm_forward[A-Za-z0-9_-]{0,48}\.db$")
DB_FORBIDDEN = ("/home/anton/ecommerence/", "lab.db", "pm_lp.db", "/quarantine", "quarantine/", "research/data",
                "data/lab/", "/lab/market")
ACTION = "event_farm_forward_paper"

FROZEN_CONFIG = {
    "bar_seconds": BS, "warmup_bars": 288, "gap_wait_s": 600, "coverage_window_bars": 288, "coverage_min": 0.95,
    "notional_usdt": 1000.0, "account_usdt": 10000.0, "account_stop_usdt": 8000.0, "duration_days": 90,
    "costs": {"taker_fee": 0.001, "extra_slippage": 0.0002, "half_spread": 0.0002},
    "null_cost_grid_bps": [0.0, 1.0, 5.0, 8.0],
}
FINAL = ("target", "stop", "timeout", "missed", "no_fill")
NOT_TAKEN = ("not_taken_warmup", "not_taken_coverage", "not_taken_ended", "not_taken_variant_stopped")


class NotActivated(Exception):
    """Live mode without an approving activation object."""


class SourceRefused(Exception):
    """A source, symbol set or database path that this book does not accept."""


class IntegrityHalt(Exception):
    """A rule of the book was broken; the book stops and books nothing more."""


def variants():
    ef = drv.engine()
    return [(ef._variant_id(v), v) for v in ef.VARIANTS]


def check_db_path(path):
    """String checks only, before anything touches the file system."""
    if not isinstance(path, str) or not path:
        raise SourceRefused("no database path")
    norm = os.path.normpath(os.path.abspath(path))
    low = norm.lower()
    for frag in DB_FORBIDDEN:
        if frag in low:
            raise SourceRefused(f"database path contains {frag!r}: refused")
    if not DB_NAME.match(os.path.basename(norm)):
        raise SourceRefused("database file must be named event_farm_forward*.db")
    return norm


class SyntheticSource:
    """Test source that behaves like a "closed bars since ts" query: fetch returns every published row with ts > since_ts
    (all rows when since_ts is None), plus rows pushed with push_once (late, revised or malformed rows), once."""

    def __init__(self, provenance=None):
        self.provenance = provenance or {"source": "synthetic", "generator": "tests"}
        self.rows, self.once = {}, {}

    def publish(self, symbol, rows):
        self.rows.setdefault(symbol, []).extend(rows)

    def push_once(self, symbol, rows):
        self.once.setdefault(symbol, []).extend(rows)

    def fetch(self, symbol, since_ts):
        out = [r for r in self.rows.get(symbol, []) if since_ts is None or r[0] > since_ts]
        out, self.once[symbol] = out + self.once.get(symbol, []), []
        return out


def lab_costs(trade, exit_px, cfg):
    """Net USDT and net R of one trade under the lab's paper costs: taker fee on both fills plus slippage and half the
    expected spread against us on both fills (conservative: a resting limit is also charged as a taker)."""
    c = cfg["costs"]
    qty = cfg["notional_usdt"] / trade["entry"]
    d = trade["dir"]
    gross = d * (exit_px - trade["entry"]) * qty
    fees = c["taker_fee"] * qty * (trade["entry"] + exit_px)
    adverse = (c["extra_slippage"] + c["half_spread"]) * qty * (trade["entry"] + exit_px)
    net = gross - fees - adverse
    return {"gross_usdt": gross, "fees_usdt": fees, "slippage_usdt": adverse, "net_usdt": net,
            "net_r_lab": net / (trade["risk"] * qty)}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bars (symbol TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL, seq INTEGER,
    received_step INTEGER, PRIMARY KEY (symbol, ts));
CREATE TABLE IF NOT EXISTS late_bars (symbol TEXT, ts INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,
    received_step INTEGER, in_gap INTEGER, PRIMARY KEY (symbol, ts));
CREATE TABLE IF NOT EXISTS conflicts (symbol TEXT, ts INTEGER, row TEXT, received_step INTEGER, processed INTEGER,
    PRIMARY KEY (symbol, ts, row));
CREATE TABLE IF NOT EXISTS rejected (symbol TEXT, row TEXT, reason TEXT, received_step INTEGER,
    PRIMARY KEY (symbol, row, reason));
CREATE TABLE IF NOT EXISTS gaps (symbol TEXT, from_ts INTEGER, to_ts INTEGER, n_bars INTEGER, declared_step INTEGER,
    PRIMARY KEY (symbol, from_ts));
CREATE TABLE IF NOT EXISTS events (symbol TEXT, known_i INTEGER, n INTEGER, kind TEXT, ts INTEGER, known_ts INTEGER,
    i INTEGER, dir INTEGER, payload TEXT, PRIMARY KEY (symbol, known_i, n));
CREATE TABLE IF NOT EXISTS trades (variant TEXT, symbol TEXT, known_ts INTEGER, kind TEXT, known_i INTEGER, ts INTEGER,
    chain TEXT, dir INTEGER, entry REAL, stop REAL, target REAL, risk REAL, atr REAL, entry_mode TEXT,
    booked_step INTEGER, booked_wall_ts REAL, booking_delay_s REAL, status TEXT, fill_ts INTEGER, exit_ts INTEGER,
    exit_px REAL, both_hit INTEGER, touch_only INTEGER, gross_r REAL, net_r_lab REAL, net_usdt REAL,
    gap_affected INTEGER, PRIMARY KEY (variant, symbol, known_ts, kind));
CREATE TABLE IF NOT EXISTS steps (step INTEGER PRIMARY KEY, wall_ts REAL, new_bars INTEGER, processed INTEGER,
    new_events INTEGER, new_trades INTEGER, closed_trades INTEGER);
"""


class ForwardBook:
    def __init__(self, db_path, source, symbols, mode="synthetic", activation=None, clock=None, config=None):
        self.path = check_db_path(db_path)                          # string checks first: nothing touched yet
        cfg = dict(FROZEN_CONFIG)
        cfg.update(config or {})
        prov = getattr(source, "provenance", None)
        if mode == "synthetic":
            if not isinstance(prov, dict) or prov.get("source") != "synthetic":
                raise SourceRefused("synthetic mode needs a source whose provenance says source 'synthetic'")
            if not symbols or not all(SYNTHETIC_SYMBOL.match(s) for s in symbols):
                raise SourceRefused("synthetic mode takes only SYN... symbols")
        elif mode == "live":
            if tuple(symbols) != LIVE_SYMBOLS or cfg != FROZEN_CONFIG:
                raise SourceRefused("live mode takes exactly BTCUSDT, ETHUSDT and the frozen config")
            if activation is None or not callable(getattr(activation, "approved", None)) or \
                    activation.approved(ACTION) is not True:
                raise NotActivated("the event farm forward book is not activated (gate, amendment and D5 signature)")
        else:
            raise SourceRefused(f"unknown mode {mode!r}")
        self.ef = drv.engine()                                       # sha256 of the frozen engine before any use
        self.source, self.symbols, self.mode, self.cfg = source, tuple(symbols), mode, cfg
        self.clock = clock or time.time
        self.variants = variants()
        self.params = {vid: self.ef.params(**{"bar_seconds": BS, **v}) for vid, v in self.variants}
        self.p0 = self.ef.params(bar_seconds=BS)
        self.margin = self.p0["mss_window"] + self.p0["sweep_reclaim_bars"] + 2
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.executescript(SCHEMA_SQL)
        self._meta_check()
        self._load()

    # ---- meta, halting, loading
    def _identity(self):
        return {"schema": SCHEMA, "engine_sha256": drv.ENGINE_SHA256, "engine_commit": drv.ENGINE_COMMIT,
                "mode": self.mode, "symbols": list(self.symbols), "config": self.cfg,
                "variants": [vid for vid, _ in self.variants],
                "source_provenance": dict(sorted(self.source.provenance.items()))}

    def _meta_check(self):
        ident = json.dumps(self._identity(), sort_keys=True)
        row = self.db.execute("SELECT v FROM meta WHERE k = 'identity'").fetchone()
        if row is None:
            self.db.execute("INSERT INTO meta VALUES ('identity', ?)", (ident,))
            self.db.execute("INSERT INTO meta VALUES ('step', '0')")
        elif row[0] != ident:
            raise IntegrityHalt("database identity differs (engine, mode, symbols, config, variants or source)")

    def halted(self):
        row = self.db.execute("SELECT v FROM meta WHERE k = 'halted'").fetchone()
        return None if row is None else row[0]

    def _halt(self, reason):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES ('halted', ?)", (reason,))

    def _load(self):
        """Rebuild the in-memory engine state by replaying the processed bars of every symbol."""
        self.farm, self.bars, self.events = {}, {}, {}
        for s in self.symbols:
            rows = self.db.execute("SELECT ts, o, h, l, c, v FROM bars WHERE symbol = ? AND seq IS NOT NULL ORDER BY seq",
                                   (s,)).fetchall()
            farm = self.ef.Farm(self.p0)
            evs = []
            for r in rows:
                evs.extend(farm.step(tuple(r)))
            self.farm[s], self.bars[s], self.events[s] = farm, [tuple(r) for r in rows], evs

    # ---- one step
    def step(self):
        reason = self.halted()
        if reason:
            raise IntegrityHalt(f"book halted: {reason}")
        now = self.clock()
        step_no = int(self.db.execute("SELECT v FROM meta WHERE k = 'step'").fetchone()[0]) + 1
        self.db.execute("BEGIN IMMEDIATE")
        try:
            stats = {"new_bars": 0, "processed": 0, "new_events": 0, "new_trades": 0, "closed_trades": 0}
            for s in self.symbols:
                self._receive(s, self.source.fetch(s, self._last_stored(s)), now, step_no, stats)
            self._advance(step_no, now, stats)
            if any(stats.values()):
                self.db.execute("UPDATE meta SET v = ? WHERE k = 'step'", (str(step_no),))
                self.db.execute("INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (step_no, now, stats["new_bars"], stats["processed"], stats["new_events"],
                                 stats["new_trades"], stats["closed_trades"]))
            self.db.execute("COMMIT")
            return stats
        except IntegrityHalt as e:
            self.db.execute("ROLLBACK")
            self._halt(str(e))
            self._load()
            raise
        except BaseException:
            self.db.execute("ROLLBACK")
            self._load()
            raise

    def _last_stored(self, s):
        r = self.db.execute("SELECT MAX(ts) FROM bars WHERE symbol = ?", (s,)).fetchone()
        return r[0]

    def _last_processed(self, s):
        return self.bars[s][-1][0] if self.bars[s] else None

    def _receive(self, s, rows, now, step_no, stats):
        last_p = self._last_processed(s)
        for row in rows:
            key = json.dumps(list(row) if isinstance(row, (list, tuple)) else repr(row))
            ok = isinstance(row, (list, tuple)) and len(row) == 6 and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in row)
            reason = None
            if not ok:
                reason = "shape"
            else:
                ts, o, h, l, c, v = row
                if int(ts) != ts or int(ts) % BS:
                    reason = "off_grid"
                elif h < max(o, c) or l > min(o, c) or v < 0:
                    reason = "ohlc"
                elif ts + BS > now:
                    reason = "not_closed"
            if reason:
                self.db.execute("INSERT OR IGNORE INTO rejected VALUES (?, ?, ?, ?)", (s, key, reason, step_no))
                continue
            ts = int(row[0])
            vals = tuple(float(x) for x in row[1:])
            old = self.db.execute("SELECT o, h, l, c, v, seq FROM bars WHERE symbol = ? AND ts = ?", (s, ts)).fetchone()
            if old is not None:
                if tuple(old[:5]) != vals:
                    self.db.execute("INSERT OR IGNORE INTO conflicts VALUES (?, ?, ?, ?, ?)",
                                    (s, ts, key, step_no, int(old[5] is not None)))
                continue
            if last_p is not None and ts <= last_p:
                in_gap = self.db.execute("SELECT 1 FROM gaps WHERE symbol = ? AND from_ts <= ? AND to_ts >= ?",
                                         (s, ts, ts)).fetchone() is not None
                self.db.execute("INSERT OR IGNORE INTO late_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (s, ts) + vals + (step_no, int(in_gap)))
                continue
            self.db.execute("INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)", (s, ts) + vals + (step_no,))
            stats["new_bars"] += 1

    def _next_bar(self, s):
        """(bar, gap) for the next bar of s that may be processed now, or None. gap = (from_ts, to_ts) when the missing
        slots before it have been waited for long enough (a stored bar lies gap_wait_s beyond the first missing one)."""
        first = self.db.execute("SELECT ts, o, h, l, c, v FROM bars WHERE symbol = ? AND seq IS NULL ORDER BY ts LIMIT 1",
                                (s,)).fetchone()
        if first is None:
            return None
        last = self._last_processed(s)
        if last is None or first[0] == last + BS:
            return tuple(first), None
        newest = self.db.execute("SELECT MAX(ts) FROM bars WHERE symbol = ?", (s,)).fetchone()[0]
        if newest - (last + BS) >= self.cfg["gap_wait_s"]:
            return tuple(first), (last + BS, first[0] - BS)
        return None

    def _advance(self, step_no, now, stats):
        """Process every bar that may be processed, in global (ts, symbol) order, one bar at a time."""
        while True:
            cand = []
            for s in self.symbols:
                nb = self._next_bar(s)
                if nb is not None:
                    cand.append((nb[0][0], s, nb))
            if not cand:
                return
            _, s, (bar, gap) = min(cand)
            self._take(s, bar, gap, step_no, now, stats)

    def _take(self, s, bar, gap, step_no, now, stats):
        if gap is not None:
            self.db.execute("INSERT INTO gaps VALUES (?, ?, ?, ?, ?)",
                            (s, gap[0], gap[1], (gap[1] - gap[0]) // BS + 1, step_no))
        if self.db.execute("SELECT v FROM meta WHERE k = 'start_ts'").fetchone() is None:
            self.db.execute("INSERT INTO meta VALUES ('start_ts', ?)", (str(bar[0]),))
        k = len(self.bars[s])
        self.db.execute("UPDATE bars SET seq = ? WHERE symbol = ? AND ts = ?", (k, s, bar[0]))
        self.bars[s].append(bar)
        new = self.farm[s].step(bar)
        for n, e in enumerate(new):
            if e["known_i"] != k or e["known_ts"] != bar[0] + BS or e["i"] > k:
                raise IntegrityHalt(f"{s}: event {e['kind']} is not known at the bar being processed")
            payload = {x: v for x, v in e.items() if x not in ("kind", "ts", "known_ts", "i", "known_i", "dir")}
            self.db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (s, k, n, e["kind"], e["ts"], e["known_ts"], e["i"], e["dir"],
                             json.dumps(payload, sort_keys=True)))
        self.events[s].extend(new)
        stats["processed"] += 1
        stats["new_events"] += len(new)
        self._book(s, k, step_no, now, stats)
        self._resolve(s, stats)

    # ---- booking
    def _coverage(self, s, k):
        """Share of the coverage window ending at processed bar k that has a processed bar."""
        w = self.cfg["coverage_window_bars"]
        end = self.bars[s][k][0]
        lo = end - (w - 1) * BS
        n = 0
        for b in reversed(self.bars[s][:k + 1]):
            if b[0] < lo:
                break
            n += 1
        return n / w

    def _account(self, vid, at_ts):
        r = self.db.execute("SELECT COALESCE(SUM(net_usdt), 0) FROM trades WHERE variant = ? AND exit_ts IS NOT NULL "
                            "AND exit_ts < ? AND status IN ('target', 'stop', 'timeout')", (vid, at_ts)).fetchone()
        return self.cfg["account_usdt"] + r[0]

    def _book(self, s, k, step_no, now, stats):
        """Book the setups whose break is bar k. Only events from k - margin on can take part in a chain that breaks at
        k (a sweep older than mss_window cannot chain), so the suffix gives the same setups as the full history."""
        bars = self.bars[s]
        evs = [e for e in self.events[s] if e["known_i"] >= k - self.margin]
        end_ts = int(self.db.execute("SELECT v FROM meta WHERE k = 'start_ts'").fetchone()[0]) + \
            self.cfg["duration_days"] * 86400
        for vid, _ in self.variants:
            setups, _ = self.ef.build_setups(evs, bars, self.params[vid])
            for st in setups:
                if st["known_i"] != k:
                    continue
                if st["known_ts"] != bars[k][0] + BS or st["i"] > k:
                    raise IntegrityHalt(f"{s}/{vid}: setup not known at its bar")
                if k < self.cfg["warmup_bars"]:
                    status = "not_taken_warmup"
                elif st["known_ts"] > end_ts:
                    status = "not_taken_ended"
                elif self._coverage(s, k) < self.cfg["coverage_min"]:
                    status = "not_taken_coverage"
                elif self._account(vid, st["known_ts"]) <= self.cfg["account_stop_usdt"]:
                    status = "not_taken_variant_stopped"
                else:
                    status = "pending"
                key = (vid, s, st["known_ts"], st["kind"])
                if self.db.execute("SELECT 1 FROM trades WHERE variant = ? AND symbol = ? AND known_ts = ? AND kind = ?",
                                   key).fetchone():
                    raise IntegrityHalt(f"{key}: booked twice")
                self.db.execute(
                    "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, "
                    "NULL, NULL, NULL, NULL, NULL, 0)",
                    key + (k, st["ts"], st["chain"], st["dir"], st["entry"], st["stop"], st["target"], st["risk"],
                           st["atr"], st["entry_mode"], step_no, now, now - st["known_ts"], status))
                stats["new_trades"] += 1

    # ---- outcomes
    def _gap_inside(self, s, lo_ts, hi_ts):
        return self.db.execute("SELECT 1 FROM gaps WHERE symbol = ? AND to_ts >= ? AND from_ts <= ?",
                               (s, lo_ts, hi_ts)).fetchone() is not None

    def _resolve(self, s, stats):
        bars = self.bars[s]
        rows = self.db.execute("SELECT variant, known_ts, kind, known_i, dir, entry, stop, target, risk, atr, entry_mode "
                               "FROM trades WHERE symbol = ? AND status = 'pending'", (s,)).fetchall()
        for vid, known_ts, kind, k, d, entry, stop, target, risk, atr, mode in rows:
            st = {"dir": d, "entry": entry, "stop": stop, "target": target, "risk": risk, "known_i": k,
                  "entry_mode": mode, "atr": atr}
            o = self.ef.setup_outcome(st, bars, self.params[vid])
            last_ts = bars[-1][0]
            if o["status"] == "incomplete":
                gap = self._gap_inside(s, known_ts, last_ts)
                self.db.execute("UPDATE trades SET gap_affected = ? WHERE variant = ? AND symbol = ? AND known_ts = ? "
                                "AND kind = ?", (int(gap), vid, s, known_ts, kind))
                continue
            fill_ts = bars[o["fill_i"]][0] if o["fill_i"] is not None else None
            exit_ts = bars[o["exit_i"]][0] + BS if o["exit_i"] is not None else None
            if fill_ts is not None and fill_ts + BS <= known_ts and mode != "market":
                raise IntegrityHalt(f"{s}/{vid}: fill before known_ts")
            touch = 0
            if o["fill_i"] is not None and mode != "market":
                fb = bars[o["fill_i"]]
                touch = int(fb[3] == entry if d > 0 else fb[2] == entry)
            gap = self._gap_inside(s, known_ts, exit_ts if exit_ts is not None else last_ts)
            cost = lab_costs(st, o["exit_px"], self.cfg) if o["exit_px"] is not None else None
            self.db.execute(
                "UPDATE trades SET status = ?, fill_ts = ?, exit_ts = ?, exit_px = ?, both_hit = ?, touch_only = ?, "
                "gross_r = ?, net_r_lab = ?, net_usdt = ?, gap_affected = ? WHERE variant = ? AND symbol = ? AND "
                "known_ts = ? AND kind = ?",
                (o["status"], fill_ts, exit_ts, o["exit_px"], int(o["both_hit_bars"] > 0), touch, o["gross_r"],
                 cost and cost["net_r_lab"], cost and cost["net_usdt"], int(gap), vid, s, known_ts, kind))
            stats["closed_trades"] += 1

    # ---- reading
    def dump(self, with_steps=False):
        """Every table as sorted rows (for audits and equality checks). booked_step / wall fields are excluded unless
        with_steps, because they depend on how bars were batched into steps, not on the bars."""
        out = {}
        for t in ("bars", "late_bars", "conflicts", "rejected", "gaps", "events", "trades"):
            cols = [r[1] for r in self.db.execute(f"PRAGMA table_info({t})")]
            drop = set() if with_steps else {"received_step", "booked_step", "booked_wall_ts", "booking_delay_s",
                                             "declared_step", "seq"}
            keep = [c for c in cols if c not in drop]
            out[t] = sorted(self.db.execute(f"SELECT {', '.join(keep)} FROM {t}").fetchall(), key=repr)
        return out

    def close(self):
        self.db.close()


# ---------------------------------------------------------------- Register V2 plan (in code, never persisted)

REGISTER_N_BEFORE = 19438                 # register_stats.REGISTER_COUNTS["variants"] at order 100
HISTORICAL_EVENT_FARM_TESTS = 315         # event_farm_driver.all_tests(), counted although explore0 has not run
FORWARD_TESTS = 12
REFERENCE_N_MIN = REGISTER_N_BEFORE + HISTORICAL_EVENT_FARM_TESTS          # 19,753, the order's floor
REFERENCE_N_FORWARD = REFERENCE_N_MIN + FORWARD_TESTS                      # 19,765, used by the forward diagnostics


def v2_plan_records(start_date, end_date):
    """One FUTURE record per registered variant, validated in memory. The dates are set at approval; nothing is written.
    Each record names the 12-variant family as its universe and the reference N (>= 19,753) in its parameters."""
    from research.tools import factory, register_v2 as v2
    ids = [vid for vid, _ in variants()]
    universe = {"definition": "12 setup-varianter (event_farm.VARIANTS), fremadrettet papir 5m BTCUSDT+ETHUSDT",
                "size": len(ids), "members_sha256": factory.sha(ids)}
    src = {"name": "fapi 5m klines BTCUSDT/ETHUSDT, kun lukkede barer, fremadrettet (beskrevet, ikke godkendt)",
           "sha256": factory.sha({"endpoint": "GET /fapi/v1/klines", "interval": "5m", "symbols": list(LIVE_SYMBOLS)})}
    cost = {"name": "lab-papirbog: taker 0,001 + slippage 0,0002 + halv spread 0,0002 pr. fyld",
            "round_trip_bps": 2e4 * sum(FROZEN_CONFIG["costs"].values()), "sha256": factory.sha(FROZEN_CONFIG["costs"])}
    method = "beskrivende papirbog; R pr. handel uden huller; null seed 83; multiple testing med N >= 19.765"
    recs = []
    for vid, v in variants():
        vals = {"variant": vid, "variant_params": v, "frozen_config": FROZEN_CONFIG, "study_id": "EVENT_FARM",
                "classification": "RELATED_MECHANISM", "independent_lineage": False,
                "independent_discovery_claim": False, "engine": {"commit": drv.ENGINE_COMMIT, "sha256": drv.ENGINE_SHA256},
                "reference_n_min": REFERENCE_N_MIN, "reference_n_forward": REFERENCE_N_FORWARD,
                "historical_tests_counted": HISTORICAL_EVENT_FARM_TESTS, "status": "UDKAST, IKKE LÅST", "activated": False}
        recs.append(v2.record(
            f"EVENT_FARM_FWD_{vid.replace('/', '_')}", v2.FUTURE, hypothesis_id=f"EVENT_FARM:FWD:{vid}",
            lineage=drv.LINEAGE, trial_universe=universe, variants_tested=None, parameters=v2.parameters_block(vals),
            code_hash=drv.ENGINE_SHA256, data_source=src, data_period={"start": start_date, "end": end_date},
            cost_model=cost, evaluation_method={"name": method, "sha256": factory.sha(method)},
            data_quality={"status": "NOT_CHECKED"}, deviations=[]))
    return recs


# ---------------------------------------------------------------- report

def report(book, null=None):
    """Descriptive report: data quality, label counts, per-variant statuses and R (primary: trades without a gap), the
    worst case for gap trades, fill uncertainty, and the null side by side when given (event_farm.null_run output)."""
    db, cfg = book.db, book.cfg
    out = {"identity": book._identity(), "halted": book.halted(), "data": {}, "events": {}, "variants": {}}
    for s in book.symbols:
        n = db.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM bars WHERE symbol = ? AND seq IS NOT NULL", (s,)).fetchone()
        span = 0 if n[0] == 0 else (n[2] - n[1]) // BS + 1
        out["data"][s] = {
            "processed": n[0], "slots": span, "coverage": n[0] / span if span else None,
            "gaps": db.execute("SELECT COUNT(*), COALESCE(SUM(n_bars), 0) FROM gaps WHERE symbol = ?", (s,)).fetchone(),
            "late": db.execute("SELECT COUNT(*) FROM late_bars WHERE symbol = ?", (s,)).fetchone()[0],
            "conflicts": db.execute("SELECT COUNT(*) FROM conflicts WHERE symbol = ?", (s,)).fetchone()[0],
            "rejected": dict(db.execute("SELECT reason, COUNT(*) FROM rejected WHERE symbol = ? GROUP BY reason "
                                        "ORDER BY reason", (s,)).fetchall()),
            "booking_delay_s_max": db.execute("SELECT MAX(booking_delay_s) FROM trades WHERE symbol = ?", (s,)).fetchone()[0]}
        days = max(1, n[0] / 288)
        out["events"][s] = {k: c / days for k, c in db.execute(
            "SELECT kind, COUNT(*) FROM events WHERE symbol = ? GROUP BY kind ORDER BY kind", (s,)).fetchall()}
    for vid, _ in book.variants:
        rows = db.execute("SELECT status, gross_r, net_r_lab, entry, risk, both_hit, touch_only, gap_affected, net_usdt "
                          "FROM trades WHERE variant = ?", (vid,)).fetchall()
        status = {}
        for r in rows:
            status[r[0]] = status.get(r[0], 0) + 1
        clean = [r for r in rows if r[0] in ("target", "stop", "timeout") and not r[7]]
        gapped = [r for r in rows if r[0] in ("target", "stop", "timeout", "pending") and r[7]]
        g = [r[1] for r in clean]
        net_grid = {f"{c:g}": (statistics.fmean([r[1] - c * 1e-4 * r[3] / r[4] for r in clean]) if clean else None)
                    for c in cfg["null_cost_grid_bps"]}
        worst = [r[2] for r in clean] + [-1.0 - 2 * sum(cfg["costs"].values()) * r[3] / r[4] for r in gapped]
        out["variants"][vid] = {
            "status": dict(sorted(status.items())), "trades_clean": len(clean), "gap_affected": len(gapped),
            "mean_gross_r": statistics.fmean(g) if g else None,
            "mean_net_r_lab": statistics.fmean([r[2] for r in clean]) if clean else None,
            "net_usdt_clean": math.fsum(r[8] for r in clean), "mean_net_r_grid": net_grid,
            "worst_case_mean_net_r_lab": statistics.fmean(worst) if worst else None,
            "both_hit_share": (sum(r[5] for r in clean) / len(clean)) if clean else None,
            "touch_only_share": (sum(r[6] for r in clean) / len(clean)) if clean else None}
        if null is not None:
            nv = null["variants"][vid]
            out["variants"][vid]["null"] = {"setups_per_instrument_day": nv["setups_per_instrument_day"],
                                            "mean_gross_r": nv["mean_gross_r"], "trades": nv["trades"],
                                            "mean_net_r_grid": {c: nv["net"][c]["mean_net_r"] for c in nv["net"]}}
    if null is not None:
        out["null"] = {"seed": null["seed"], "instruments": null["instruments"], "days": null["days"],
                       "events_per_instrument_day": null["events_per_instrument_day"],
                       "pooled_mean_gross_r": null["pooled_mean_gross_r"]}
    out["label"] = "PAPIR / SIMULERING - beskrivende; ingen evidens for en fordel"
    return out


__all__ = ["ForwardBook", "SyntheticSource", "report", "lab_costs", "check_db_path", "FROZEN_CONFIG", "NotActivated",
           "SourceRefused", "IntegrityHalt"]
