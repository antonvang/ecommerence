"""Director order 67 (research/desk/PAPER_ENGINE_REMEDIATION_67.md): paper-engine remediation in isolated dev. Every
new behaviour is behind a flag that is off by default (BOOK_AGE_MODE "off", DAILY_RETURNS_MODE "legacy",
FUNDING_MISSING_MODE "legacy"); these tests switch the flags on in temporary databases only. The STRAKS/PAR patch is
tested against temporary copies; lab/straks.py, lab/pairs.py and research/tools/net_report.py stay byte-identical.
Synthetic data, no network, no DNS."""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from dataclasses import asdict
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import lab  # noqa: E402
from lab import carry90, lane, markprov, paper, paper_runner as pr, pipeline, reportcheck  # noqa: E402
from lab import risk as risk_mod  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import Book, CostModel, PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.test_lab_mark_failed import market as carry_market  # noqa: E402
from tests.test_lab_straks import market as straks_market  # noqa: E402

HOUR, DAY = 3600, 86400
NOW = datetime(2026, 11, 5, 21, 30, tzinfo=timezone.utc).timestamp()
DNS = urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
COSTS = CostModel(taker_fee=0.001, extra_slippage=0.0002, expected_spread=0.0004)
PATCH = os.path.join(HERE, "research", "desk", "patches", "66_straks_pairs_mark_guard.diff")
PINS = {"lab/straks.py": "7a110f1fa20fb7d28b76269fc039eec4c75ddfa7353602f2f8824490b722a542",
        "lab/pairs.py": "5c9b60a4314a40a5e4d517427c4960220682b8f6179a445a5554903180ce1219",
        "research/tools/net_report.py": "e8cac57c9a407912c25e884b2c4ca3b6c9f6b2cf2bf0d6ed8e2ee3acb31e405f"}
SIM = ("sim_orders", "sim_fills", "sim_cancels", "sim_equity", "sim_funding")


def no_network(*a, **k):
    raise AssertionError("order 67 tests must not touch the network or DNS")


def load(name, path, package=None):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    if package:
        mod.__package__ = package
    spec.loader.exec_module(mod)
    return mod


def apply_unified(diff, root, out_dir):
    """A strict unified-diff applier (context must match exactly). Returns {relative path: written file}."""
    lines, i, out = diff.splitlines(keepends=True), 0, {}
    while i < len(lines):
        if not lines[i].startswith("+++ "):
            i += 1
            continue
        rel = lines[i][4:].split("\t")[0].strip()[2:]                # "b/copybot/lab/x.py" -> "copybot/lab/x.py"
        with open(os.path.join(root, rel)) as f:
            src = f.readlines()
        res, pos, i = [], 0, i + 1
        while i < len(lines) and lines[i].startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[i])
            start, old_n, new_n = int(m.group(1)) - 1, int(m.group(2) or 1), int(m.group(4) or 1)
            res.extend(src[pos:start])
            pos, i = start, i + 1
            while old_n or new_n:
                t = lines[i]
                if t[0] in " -":
                    assert src[pos] == t[1:], (rel, pos + 1, src[pos], t)
                    if t[0] == " ":
                        res.append(src[pos])
                        new_n -= 1
                    pos, old_n = pos + 1, old_n - 1
                else:
                    assert t[0] == "+", t
                    res.append(t[1:])
                    new_n -= 1
                i += 1
        res.extend(src[pos:])
        dst = os.path.join(out_dir, os.path.basename(rel))
        with open(dst, "w") as f:
            f.writelines(res)
        out[rel] = dst
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab67")
        self.dbs = []
        self.db = self.new_db("lab.db")
        self.p = [mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)]
        for p in self.p:
            p.start()
        pr._HOURLY.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        for d in self.dbs:
            d.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def new_db(self, name):
        d = DB(os.path.join(self.tmp, name))
        self.dbs.append(d)
        return d

    def ledger(self, led="LANE_67b0000001", source="straks", db=None):
        db = db or self.db
        db.event("lane.started", "system:lane", led, {"key": led, "source": source, "name": "T", "coins": ["X"],
                                                      "capital": 10_000.0, "t": int(NOW - DAY), "costs": asdict(COSTS)})
        db.event("paper.started", "system:test", led, {"capital": 10_000.0, "costs": asdict(COSTS), "simulated": True})
        return led

    def fill(self, led, ts, side, qty, px, inst="X", fee=0.0):
        n = self.db.one("SELECT COUNT(*) FROM sim_orders")[0]
        oid = f"{led}|t{n}|{inst}"
        with self.db.tx():
            self.db.append("sim_orders", order_id=oid, exp_id=led, ts=int(ts), instrument=inst, side=side, qty=qty,
                           limit_px=None, style="taker", reduce_only=0, signal_ref="test", cost_model=asdict(COSTS))
            self.db.append("sim_fills", fill_id=f"{oid}|0", order_id=oid, exp_id=led, ts=int(ts), instrument=inst,
                           side=side, px=px, qty=qty, fee=fee, slippage=0.0, liquidity="taker", mid=px,
                           book_ts=int(ts))

    def carry(self, db=None, get=None):
        db = db or self.db
        with db.tx():
            db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                      metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(db, NOW - 60)
        led = {i["key"]: x for x, i in lane.started(db).items()}["carry90|BTCUSDT"]
        get = get or carry_market()
        self.assertEqual(lane.run_one(db, led, get, NOW)["status"], "ok")
        return led, get

    def hashes(self, db, tables=SIM):
        return {t: [r[0] for r in db.q(f"SELECT hash FROM {t} ORDER BY id")] for t in tables}


# ======================================================================= P0-A book age
class BookAge(Base):
    def book(self, observed):
        return Book(ts=NOW, bids=((99.99, 1000.0),), asks=((100.01, 1000.0),), observed=observed)

    def test_off_is_the_old_behaviour(self):
        self.assertEqual(risk_mod.BOOK_AGE_MODE, "off")              # the default for every active book
        with mock.patch.object(risk_mod, "WALL", lambda: NOW + 7):
            b = pr.fetch_book("BTCUSDT", NOW, carry_market())
        self.assertEqual((b.ts, b.observed), (NOW, NOW + 7))         # ts stays the pass clock
        self.assertEqual(b, Book(ts=NOW, bids=b.bids, asks=b.asks))  # observed never changes equality
        led = self.ledger()
        with mock.patch.object(risk_mod, "WALL", lambda: NOW + 600):  # read 10 minutes before execution
            r = PaperEngine(self.db, lambda: NOW).submit_taker(led, "o1", "X", "buy", 1.0, self.book(NOW))
        self.assertEqual(r["status"], "filled")                      # off: the gate still uses the pass clock
        p = json.loads(self.db.one("SELECT payload FROM sim_exec")[0])
        self.assertFalse({"book_observed_wall", "exec_wall", "book_age_exec_s"} & set(p))

    def test_measure_records_the_real_age_and_changes_nothing_else(self):
        led = self.ledger()
        with mock.patch.object(risk_mod, "BOOK_AGE_MODE", "measure"), \
                mock.patch.object(risk_mod, "WALL", lambda: NOW + 95):
            r = PaperEngine(self.db, lambda: NOW).submit_taker(led, "o1", "X", "buy", 1.0, self.book(NOW + 5))
        self.assertEqual(r["status"], "filled")
        p = json.loads(self.db.one("SELECT payload FROM sim_exec")[0])
        self.assertEqual((p["book_observed_wall"], p["exec_wall"], p["book_age_exec_s"]), (NOW + 5, NOW + 95, 90))

    def test_guard_refuses_a_book_older_than_the_limit_at_execution(self):
        led = self.ledger()
        eng = PaperEngine(self.db, lambda: NOW)
        with mock.patch.object(risk_mod, "BOOK_AGE_MODE", "guard"), \
                mock.patch.object(risk_mod, "WALL", lambda: NOW + 125):
            old = eng.submit_taker(led, "o1", "X", "buy", 1.0, self.book(NOW + 5))         # 120 s old
            fresh = eng.submit_taker(led, "o2", "X", "buy", 1.0, self.book(NOW + 123))     # 2 s old
            legacy = eng.submit_taker(led, "o3", "X", "buy", 1.0, self.book(None))         # no observation time
        self.assertEqual((old["status"], fresh["status"], legacy["status"]), ("refused", "filled", "filled"))
        self.assertIn("120s old", old["reason"])
        blk = self.db.one("SELECT rule, value, action FROM risk_events WHERE action='BLOCK'")
        self.assertEqual((blk["rule"], blk["value"], blk["action"]), ("data_stale", 120, "BLOCK"))
        self.assertIsNone(self.db.one("SELECT 1 FROM sim_orders WHERE order_id='o1'"))     # refused: retried later

    def test_measure_keeps_orders_fills_marks_and_funding_byte_identical(self):
        a = self.new_db("off.db")
        led_a, _ = self.carry(a)
        b = self.new_db("measure.db")
        with mock.patch.object(risk_mod, "BOOK_AGE_MODE", "measure"):
            led_b, _ = self.carry(b)
        self.assertEqual(led_a, led_b)
        self.assertEqual(self.hashes(a), self.hashes(b))
        pa = [json.loads(r[0]) for r in a.q("SELECT payload FROM sim_exec ORDER BY id")]
        pb = [json.loads(r[0]) for r in b.q("SELECT payload FROM sim_exec ORDER BY id")]
        self.assertEqual(pa, [{k: v for k, v in x.items() if k not in ("book_observed_wall", "exec_wall",
                                                                       "book_age_exec_s")} for x in pb])
        self.assertTrue(all(x["book_age_exec_s"] is not None for x in pb))


# ======================================================================= P0-B daily returns
class DailyReturns(Base):
    def marks(self, led, days, missing, start=None, step=-0.004):
        d0 = start or int(NOW // DAY * DAY) - (days + 1) * DAY
        eq = 10_000.0
        for k in range(days):
            if k not in missing:
                self.db.append("sim_equity", exp_id=led, ts=d0 + k * DAY + 23 * HOUR, equity=eq, cash=eq,
                               exposure=0.0, peak=10_000.0, drawdown=0.0)
            eq *= 1 + step
        return d0

    INFO = {"ts": NOW - 20 * DAY, "expectation": {"mean": 0.001, "sd": 0.002}}

    def stats(self, led, mode):
        with mock.patch.object(lane, "DAILY_RETURNS_MODE", mode):
            return lane.stats(self.db, led, NOW, self.INFO)

    def test_a_missing_day_is_invalid_and_low_coverage_is_inconclusive(self):
        led = self.ledger(source=None)
        d0 = self.marks(led, 10, {5})                 # 9 marked days, 2026 day 5 has no mark
        legacy, strict = self.stats(led, "legacy"), self.stats(led, "strict")
        self.assertEqual(legacy["days"], 8)           # one of them spans two calendar days
        self.assertLessEqual(legacy["z"], lane.Z_RETIRE)      # the 'edge' rule (days >= 7, z <= -3) would fire
        self.assertNotIn("observation", legacy)               # legacy output unchanged
        ob = strict["observation"]
        self.assertEqual((strict["days"], ob["valid_pairs"], ob["day_pairs"], ob["status"]), (7, 7, 9, "INCONCLUSIVE"))
        self.assertAlmostEqual(ob["coverage"], 7 / 9)
        (span,) = ob["invalid_spans"]
        self.assertEqual((span["missing_days_ts"], span["status"]), ([d0 // DAY * DAY + 5 * DAY], "INVALID"))
        self.assertIsNone(strict["z"])                # INCONCLUSIVE: no day-based rule decides
        self.assertAlmostEqual(strict["mean"], -0.004)     # only true one-day returns; nothing rescaled

    def test_enough_coverage_keeps_the_rule_on_the_valid_days_only(self):
        led = self.ledger(source=None)
        self.marks(led, 20, {9})
        strict = self.stats(led, "strict")
        ob = strict["observation"]
        self.assertEqual((ob["valid_pairs"], ob["day_pairs"], ob["status"]), (17, 19, "OK"))
        self.assertAlmostEqual(strict["mean"], -0.004)
        self.assertAlmostEqual(strict["z"], (-0.004 - 0.001) / (0.002 / 17 ** 0.5))

    def test_default_is_legacy(self):
        self.assertEqual(lane.DAILY_RETURNS_MODE, "legacy")


# ======================================================================= P0-C funding
class FundingFailClosed(Base):
    def setup_missing(self):
        led = self.ledger()
        t_f, st = int(NOW - 20 * HOUR), int(NOW // HOUR * HOUR - 16 * HOUR)
        self.fill(led, st - 600, "buy", 1.0, 100.0)
        funding = {st + k * 8 * HOUR: 0.0001 for k in range(-6, 2)}   # an 8-hourly series (68: interval known)
        opens = {t: 100.0 for t in range(st - 4 * HOUR, int(NOW), HOUR) if t != st}       # the bar at st is missing
        return led, t_f, st, {"X": (funding, opens)}

    def test_legacy_waits_silently_as_before(self):
        led, t_f, st, data = self.setup_missing()
        eng = PaperEngine(self.db, lambda: NOW)
        self.assertEqual(eng.book_funding(led, data, t_f), [])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=?", paper.FUNDING_MISSING)[0], 0)
        self.assertEqual(eng.funding_status["X"]["state"], "MISSING_BAR")       # known in memory only
        self.assertEqual(pr.funding_fields(eng), {})                             # no new result field

    def test_fail_closed_is_a_visible_error_and_invents_nothing(self):
        led, t_f, st, data = self.setup_missing()
        with mock.patch.object(paper, "FUNDING_MISSING_MODE", "fail_closed"):
            for k in range(2):                                                  # two passes: one event
                eng = PaperEngine(self.db, lambda: NOW + k * 600)
                self.assertEqual(eng.book_funding(led, data, t_f), [])
                f = pr.funding_fields(eng)
            self.assertEqual(f["funding_status"], "ERROR")
            self.assertEqual(f["funding_detail"]["X"]["settle_ts"], st)
        (e,) = self.db.q("SELECT payload FROM events WHERE kind=?", paper.FUNDING_MISSING)
        p = json.loads(e[0])
        self.assertEqual((p["instrument"], p["settle_ts"], p["booked"], p["state"]), ("X", st, False, "MISSING_BAR"))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_funding")[0], 0)     # neither st nor the later one
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])

    def test_fail_closed_waiting_for_the_newest_bar_is_not_an_error(self):
        led = self.ledger()
        st = int(NOW // HOUR * HOUR)
        self.fill(led, st - 600, "buy", 1.0, 100.0)
        with mock.patch.object(paper, "FUNDING_MISSING_MODE", "fail_closed"):
            eng = PaperEngine(self.db, lambda: NOW)
            series = {st - k * 8 * HOUR: 0.0001 for k in range(6)}       # 8-hourly (68: the interval is known)
            eng.book_funding(led, {"X": (series, {st - HOUR: 100.0})}, int(NOW - 5 * HOUR))
            self.assertEqual(pr.funding_fields(eng)["funding_status"], "WAITING")
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=?", paper.FUNDING_MISSING)[0], 0)

    def test_fail_closed_unreadable_funding_on_the_pause_path_is_recorded_once_an_hour(self):
        base = carry_market()
        led, _ = self.carry(get=base)
        Risk(self.db, lambda: NOW + 60).pause(led, "spread_anomaly", None, None, "fixture")   # human-only pause

        def get(path):
            if "klines" in path or "fundingRate" in path:
                raise DNS
            return base(path)
        base.now = NOW + 9 * HOUR                                  # a settlement (8 h grid) is due
        with mock.patch.object(paper, "FUNDING_MISSING_MODE", "fail_closed"):
            r1 = lane.run_one(self.db, led, get, NOW + 9 * HOUR)
            r2 = lane.run_one(self.db, led, get, NOW + 9 * HOUR + 600)
        self.assertEqual((r1["status"], r1["funding_status"], r2["funding_status"]), ("paused", "ERROR", "ERROR"))
        (e,) = self.db.q("SELECT payload FROM events WHERE kind=?", pr.FUNDING_UNAVAILABLE)
        self.assertEqual(json.loads(e[0])["error_class"], "dns")
        legacy = lane.run_one(self.db, led, get, NOW + 10 * HOUR)
        self.assertNotIn("funding_status", legacy)

    def test_default_is_legacy(self):
        self.assertEqual(paper.FUNDING_MISSING_MODE, "legacy")


# ======================================================================= P1 #4 STRAKS/PAR patch
class StraksPairsPatch(Base):
    def patched(self):
        with open(PATCH) as f:
            files = apply_unified(f.read(), ROOT, self.tmp)
        self.assertEqual(set(files), {"copybot/lab/straks.py", "copybot/lab/pairs.py"})
        return (load("lab.straks", files["copybot/lab/straks.py"], "lab"),
                load("lab.pairs", files["copybot/lab/pairs.py"], "lab"))

    def use(self, name, mod):
        return [mock.patch.dict(sys.modules, {f"lab.{name}": mod}), mock.patch.object(lab, name, mod, create=True)]

    def straks_run(self, db, fail_at=None):
        with db.tx():
            db.append("observations", ts=NOW - 7200, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                      metric="z_1h", value=0.0, flagged=0, payload={})
        from lab import straks                                   # the patched module while its patch is active
        straks.ensure(db, NOW - 3600)
        led = {i["key"]: x for x, i in lane.started(db).items()}["straks|cont"]
        with mock.patch("time.time", lambda: NOW - 600):
            db.event("opportunity.move", "system:scanner", None, {"instrument": "CLUSDT", "flags": ["z_1h"],
                                                                "ret_1h": 0.03, "ret_24h": 0.01})
        base = straks_market()

        def get(path):
            if "/fapi/v1/depth" in path and get.fail:
                raise DNS
            return base(path)
        out = []
        for k, t in enumerate((NOW, NOW + HOUR, NOW + 2 * HOUR)):
            get.fail, base.now = (k == fail_at), t
            out.append(lane.run_one(db, led, get, t))
        return led, out

    def test_the_patch_applies_to_copies_and_the_frozen_files_stay_pinned(self):
        self.patched()
        for rel, sha in PINS.items():
            with open(os.path.join(HERE, rel), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), sha, rel)

    def test_patched_straks_records_failure_and_recovery_with_identical_books(self):
        s, _ = self.patched()
        ref = self.new_db("ref.db")
        led_r, out_r = self.straks_run(ref, fail_at=1)                       # the frozen module: silent
        self.assertEqual(ref.one("SELECT COUNT(*) FROM events WHERE kind=?", pr.MARK_FAILED)[0], 0)
        new = self.new_db("new.db")
        ps = self.use("straks", s)
        for p in ps:
            p.start()
        try:
            led_n, out_n = self.straks_run(new, fail_at=1)
        finally:
            for p in reversed(ps):
                p.stop()
        self.assertEqual([r["marked"] for r in out_r], [r["marked"] for r in out_n])      # same return values
        self.assertTrue(str(out_n[1]["marked"]).startswith("no mark prices"))
        self.assertEqual(self.hashes(ref), self.hashes(new))                               # identical books
        self.assertEqual(new.one("SELECT COUNT(*) FROM events WHERE kind=? AND exp_id=?", pr.MARK_FAILED, led_n)[0], 1)
        self.assertEqual(new.one("SELECT COUNT(*) FROM events WHERE kind=? AND exp_id=?", pr.MARK_RECOVERED,
                                 led_n)[0], 1)

    def test_patched_pairs_records_a_failed_mark(self):
        _, pmod = self.patched()
        with self.db.tx():
            self.db.append("observations", ts=NOW - 7200, detector="abnormal_move/1", source="x", instrument="CLUSDT",
                           metric="z_1h", value=0.0, flagged=0, payload={})
        from lab import pairs
        pairs.ensure(self.db, NOW - 3600)
        led = {i["key"]: x for x, i in lane.started(self.db).items()}["pairs|v1"]
        get = straks_market()
        with mock.patch.object(pr, "_mark_hourly", side_effect=DNS):
            r0 = lane.run_one(self.db, led, get, NOW)                                     # frozen: silent
            self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=?", pr.MARK_FAILED)[0], 0)
            ps = self.use("pairs", pmod)
            for p in ps:
                p.start()
            try:
                r1 = lane.run_one(self.db, led, get, NOW + HOUR)
            finally:
                for p in reversed(ps):
                    p.stop()
        self.assertTrue(str(r0["marked"]).startswith("no mark prices"))
        self.assertTrue(str(r1["marked"]).startswith("no mark prices"))
        (e,) = self.db.q("SELECT payload FROM events WHERE kind=? AND exp_id=?", pr.MARK_FAILED, led)
        self.assertEqual(json.loads(e[0])["error_class"], "dns")


# ======================================================================= P1 #7 basis on a flip
class BasisReference(Base):
    def compare(self, led):
        nr = load("net_report_67", os.path.join(HERE, "research", "tools", "net_report.py"))
        ref = load("basis_ref_67", os.path.join(HERE, "research", "tools", "basis_ref.py"))
        con = sqlite3.connect(f"file:{self.db.path}?mode=ro", uri=True)
        try:
            before = nr.account(con, led, lane.started(self.db)[led], int(NOW + DAY))["instruments"]["X"]
            fills = con.execute("SELECT ts, order_id, instrument, side, px, qty, fee, mid FROM sim_fills WHERE "
                                "exp_id=? ORDER BY id", (led,)).fetchall()
        finally:
            con.close()
        return before, ref.instruments(fills)["X"], PaperEngine(self.db).ledger(led)

    def test_flip_long_to_short(self):
        led = self.ledger()
        self.fill(led, NOW, "buy", 1.0, 100.0)
        self.fill(led, NOW + 60, "sell", 2.0, 110.0)
        self.fill(led, NOW + 120, "buy", 1.0, 100.0)
        before, after, eng = self.compare(led)
        self.assertEqual((before["realized_price_pnl"], before["round_trips"], before["direction_last"]),
                         (10.0, 1, "long"))
        self.assertEqual((after["realized_price_pnl"], after["round_trips"], after["direction_last"], after["flips"]),
                         (20.0, 2, "short", 1))
        self.assertAlmostEqual(after["realized_price_pnl"], sum(p for _, p in eng["trades"]))   # = the engine

    def test_flip_then_add_then_partial_close(self):
        led = self.ledger()
        self.fill(led, NOW, "buy", 2.0, 100.0)
        self.fill(led, NOW + 60, "sell", 3.0, 90.0)          # -20 on the long; short 1 @ 90
        self.fill(led, NOW + 120, "sell", 1.0, 95.0)         # short 2 @ 92.5
        self.fill(led, NOW + 180, "buy", 1.0, 80.0)          # +12.5 closed; short 1 left
        before, after, eng = self.compare(led)
        self.assertAlmostEqual(before["realized_price_pnl"], -20.0 + (97.5 - 80.0))     # old basis 100 carried
        self.assertAlmostEqual(before["open_basis"], 97.5)
        self.assertAlmostEqual(after["realized_price_pnl"], -20.0 + 12.5)
        self.assertAlmostEqual(after["open_basis"], 92.5)
        self.assertAlmostEqual(eng["basis"]["X"], 92.5)
        self.assertEqual((before["direction_last"], after["direction_last"]), ("long", "short"))

    def test_no_flip_is_identical(self):
        led = self.ledger()
        for k, (side, q, px) in enumerate((("buy", 1, 100), ("buy", 1, 104), ("sell", 1.5, 110), ("sell", .5, 99))):
            self.fill(led, NOW + 60 * k, side, q, px)
        before, after, _ = self.compare(led)
        keys = set(before) - {"funding"}                       # funding: net_report's own column
        self.assertEqual({k: before[k] for k in keys}, {k: after[k] for k in keys})


# ======================================================================= P2 #10 mark provenance prototype
class MarkProvenance(Base):
    def test_rows_reproduce_the_equity_row_and_catch_a_wrong_one(self):
        led = self.ledger()
        self.fill(led, NOW, "buy", 2.0, 100.0)
        self.fill(led, NOW, "sell", 1.0, 50.0, inst="Y")
        eng = PaperEngine(self.db, lambda: NOW + 60)
        marks = {"X": 101.0, "Y": 49.0}
        books = {i: Book(ts=NOW, bids=((m - .5, 1),), asks=((m + .5, 1),), observed=NOW + 3) for i, m in marks.items()}
        eng.mark(led, marks)
        eq = dict(self.db.one("SELECT id, equity, cash, exposure FROM sim_equity WHERE exp_id=?", led))
        prov = markprov.rows(led, NOW + 60, eng.ledger(led)["positions"], marks, books, eq["id"])
        self.assertEqual([(r["instrument"], r["qty"], r["book_observed"]) for r in prov], [("X", 2.0, NOW + 3),
                                                                                          ("Y", -1.0, NOW + 3)])
        self.assertEqual(markprov.check(prov, eq), [])
        prov[0]["mark_px"] = 102.0
        self.assertEqual(len(markprov.check(prov, eq)), 3)                  # equity, exposure and mid all disagree


# ======================================================================= P2 #11 day boundary
class DayBoundary(Base):
    def test_rows_at_exactly_midnight_differ_between_the_reports(self):
        """Characterisation (not a fix): at a row stamped exactly 00:00:00 UTC, net_report (ts <= cutoff) counts it for
        the ended day while lane.report, reportcheck and straks_report (ts < end) leave it to the next day."""
        led = self.ledger(source=None)
        day = datetime.fromtimestamp(NOW, timezone.utc).strftime("%Y-%m-%d")
        end = int(NOW // DAY * DAY) + DAY
        self.fill(led, end - HOUR, "buy", 1.0, 100.0)
        for ts, eq, cash in ((end - 30 * 60, 10_000.0, 9_900.0), (end, 10_050.0, 9_900.0)):
            self.db.append("sim_equity", exp_id=led, ts=ts, equity=eq, cash=cash, exposure=100.0, peak=10_050.0,
                           drawdown=0.0)
        self.db.append("sim_funding", exp_id=led, ts=end, settle_ts=end, instrument="X", qty=1.0, rate=0.001,
                       price=100.0, amount=-0.1)
        lane_row = next(r for r in lane.report(self.db, day)["accounts"] if r["ledger"] == led)
        con = sqlite3.connect(f"file:{self.db.path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rc = reportcheck.expected(con, day)[led]
            nr = load("net_report_67b", os.path.join(HERE, "research", "tools", "net_report.py")).account(
                con, led, lane.started(self.db)[led], end)
            sr = load("straks_report_67", os.path.join(HERE, "research", "tools", "straks_report.py")).account_level(
                con, led, 10_000.0, 0.0002, end)
        finally:
            con.close()
        self.assertEqual((lane_row["equity"], rc["equity"], sr["value"]), (10_000.0, 10_000.0, 10_000.0))
        self.assertEqual((lane_row["funding"], rc["funding"]), (0.0, 0.0))
        self.assertEqual((nr["value"], nr["funding"], nr["marked_at"]), (10_050.0, -0.1, end))   # the 00:00:00 rows


if __name__ == "__main__":
    unittest.main()
