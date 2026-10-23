"""research/PROTOCOL_V3.md amendment 9: settled funding in the simulated paper ledgers from T_F (section 2), the separate
simulated balance overview with its reconciliation (section 5), non-decisional edge monitoring (section 4), and the
dashboard truth fixes (data freshness, agent output per 24 h)."""
import collections
import math
import os
import shutil
import statistics
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, jobs, paper, paper_runner, pipeline, watch  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402
from lab.paper import Book, PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.lab_fixtures import approve_paper, frozen  # noqa: E402
from tests.test_lab_paper_runner import EID, HOUR, MON, SAT, feed  # noqa: E402

B = "E_xs_momentum_p2"
S1 = datetime(2026, 10, 17, 16, 0, tzinfo=timezone.utc).timestamp()      # a settlement after T_F (= SAT, 10:30)
S0 = datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc).timestamp()       # a settlement before T_F
RATE = 0.0003


def ffeed(now, rates=None, opens=None, px=100.0):
    """feed() plus what Binance also returns: the in-progress bar last in klines, and settled funding {ts: rate}.
    opens: {bar_open_ts: open} for chosen bars (the funding price is the open of the bar starting at a settlement)."""
    base, h = feed(now, px), int(now) // HOUR * HOUR

    def get(path):
        if "klines" in path:
            kl = [[k[0], (opens or {}).get(k[0] // 1000, k[1])] + k[2:] for k in base(path)]
            o = (opens or {}).get(h, px)
            return kl + [[h * 1000, o, o, o, o, 1, (h + HOUR) * 1000 - 1]]
        if "fundingRate" in path:
            return [{"fundingTime": int(t) * 1000 + 3, "fundingRate": str(r)} for t, r in sorted((rates or {}).items())
                    if t <= now]
        return base(path)
    return get


def counted(get):
    n = collections.Counter()

    def g(path):
        n[next(k for k in ("klines", "fundingRate", "depth") if k in path)] += 1
        return get(path)
    return g, n


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfund")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True)]
        for p in self.p:
            p.start()
        self.db.append("experiments", exp_id=EID, version=1, created_ts=0, mechanism_tag="calendar_day_of_week",
                       fingerprint="f", spec_json={"template": "day_of_week", "execution": "taker"})
        approve_paper(self.db, EID)
        frozen(self.db, EID, "cost", {"selected": 1})
        frozen(self.db, EID, "backtest", {"variants": [
            {"variant": 0, "params": {"mode": "flat_weekend"}, "fit": None, "positions": {}},
            {"variant": 1, "params": {"mode": "weekend_only"}, "fit": None, "positions": {}}]})   # long all on weekends

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def forward(self, eid=B):
        """B as an active forward test (amendment 7) with pinned artifacts; it trades 2 long and 2 short."""
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="xs", fingerprint=eid,
                       spec_json={"template": "xs_momentum", "execution": "taker"})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="REJECTED", actor="fixture",
                       reason="fixture: rejected at validation")
        c = frozen(self.db, eid, "cost", {"selected": 0})
        b = frozen(self.db, eid, "backtest", {"variants": [{"variant": 0, "params": {"lookback_days": 7, "k": 2},
                                                            "fit": None, "positions": {}}]})
        pins = mock.patch.dict(paper.FORWARD_ACCOUNTS, {eid: (c["sha256"], b["sha256"])}, clear=True)
        pins.start()
        self.addCleanup(pins.stop)
        self.db.event("forward.approved", "human:test", eid, {"reason": "fixture forward test"})
        return "FWD_" + eid

    def rows(self, led=None):
        return [dict(r) for r in self.db.q("SELECT * FROM sim_funding" + (" WHERE exp_id=?" if led else "") +
                                           " ORDER BY id", *([led] if led else []))]


class Funding(Base):
    def test_long_pays_and_short_receives_at_the_open_of_the_settlement_bar(self):
        led = self.forward()
        paper_runner.run(self.db, feed(SAT), SAT)                                   # T_F = SAT
        held = PaperEngine(self.db).ledger(led)["positions"]
        self.assertEqual(sorted(q > 0 for q in held.values()), [False, False, True, True])
        out = paper_runner.run(self.db, ffeed(S1 + 1800, {S1: RATE}, {S1: 101.0}), S1 + 1800)["results"]
        rows = {r["instrument"]: r for r in self.rows(led)}
        self.assertEqual(set(rows), set(held))
        for s, q in held.items():
            r = rows[s]
            self.assertEqual((r["settle_ts"], r["qty"], r["rate"], r["price"]), (int(S1), q, RATE, 101.0))
            self.assertAlmostEqual(r["amount"], -q * 101.0 * RATE, places=12)
            self.assertTrue(r["amount"] < 0 if q > 0 else r["amount"] > 0)         # long pays, short receives
        self.assertEqual(out[led]["funding"], 4)
        self.assertEqual(len(self.rows(EID)), len(data.UNIVERSE))                  # every ledger the runner processes

    def test_only_after_t_f_once_and_idempotent(self):
        rates = {S0: 0.01, S1: RATE}
        paper_runner.run(self.db, feed(SAT), SAT)
        t_f = self.db.q("SELECT payload FROM events WHERE kind='paper.funding_started'")
        self.assertEqual(len(t_f), 1)
        self.assertEqual(paper.funding_t0(self.db), int(SAT))
        for t in (S1 + 1800, S1 + 1860, S1 + 2 * HOUR):                            # same hour twice, then later
            paper_runner.run(self.db, ffeed(t, rates, {S1: 100.5}), t)
        rows = self.rows(EID)
        self.assertEqual({r["settle_ts"] for r in rows}, {int(S1)})               # the 08:00 settlement precedes T_F
        self.assertEqual(len(rows), len(data.UNIVERSE))
        eng = PaperEngine(self.db, lambda: S1 + 3 * HOUR)
        g = ffeed(S1 + 3 * HOUR, rates, {S1: 100.5})
        again = {s: paper_runner.hourly(s, S1 + 3 * HOUR, g)[1::2] for s in data.UNIVERSE}
        self.assertEqual(eng.book_funding(EID, again, paper.funding_t0(self.db)), [])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='paper.funding_started'")[0], 1)

    def test_a_settlement_waits_for_its_bar_and_books_in_order(self):
        paper_runner.run(self.db, feed(SAT), SAT)
        eng, t_f = PaperEngine(self.db, lambda: S1 + 1800), paper.funding_t0(self.db)
        s = data.UNIVERSE[0]
        self.assertEqual(eng.book_funding(EID, {s: ({S1: RATE}, {})}, t_f), [])     # bar not out yet: nothing
        self.assertEqual(len(eng.book_funding(EID, {s: ({S1: RATE}, {S1: 99.0})}, t_f)), 1)

    def test_qty_is_the_position_held_just_before_the_settlement(self):
        paper_runner.run(self.db, feed(SAT), SAT)                                   # Saturday: long all 8
        held = PaperEngine(self.db).ledger(EID)["positions"]
        settle = int(MON) // HOUR * HOUR                                           # Monday 00:00
        r = paper_runner.run(self.db, ffeed(MON, {settle: RATE}), MON)["results"][EID]
        self.assertTrue(all(o["status"] == "filled" for o in r["orders"]))         # Monday: sold flat at 00:30
        self.assertEqual(PaperEngine(self.db).ledger(EID)["positions"], {})
        rows = {x["instrument"]: x for x in self.rows(EID)}
        self.assertEqual({s: x["qty"] for s, x in rows.items()}, held)            # held before 00:00, not after
        t2 = settle + 8 * HOUR                                                     # flat at the next settlement
        paper_runner.run(self.db, ffeed(t2 + 1800, {settle: RATE, t2: RATE}), t2 + 1800)
        self.assertEqual(len(self.rows(EID)), len(rows))

    def test_a_paused_ledger_still_accrues_through_the_hourly_cache(self):
        cache = {}
        paper_runner.run(self.db, feed(SAT), SAT, cache=cache)
        Risk(self.db, lambda: SAT).pause(EID, "consecutive_losses", 2, 2, "test pause")
        held = PaperEngine(self.db).ledger(EID)["positions"]
        g, n = counted(ffeed(S1 + 1800, {S1: RATE}))
        r = paper_runner.run(self.db, g, S1 + 1800, cache=cache)["results"][EID]
        self.assertEqual((r["status"], r["marked"], r["funding"]), ("paused", True, len(held)))
        self.assertEqual(PaperEngine(self.db).ledger(EID)["positions"], held)
        self.assertEqual((n["klines"], n["fundingRate"]), (len(held),) * 2)       # once per symbol this hour
        paper_runner.run(self.db, g, S1 + 1860, cache=cache)
        self.assertEqual((n["klines"], n["fundingRate"]), (len(held),) * 2)       # nothing more this hour
        self.assertEqual(len(self.rows(EID)), len(held))

    def test_a_closing_ledger_books_its_last_settlement_before_it_closes(self):
        led = self.forward()
        paper_runner.run(self.db, feed(SAT), SAT)
        held = PaperEngine(self.db).ledger(led)["positions"]
        self.db.event("forward.stopped", "human:test", B, {"reason": "fixture stop"})
        r = paper_runner.run(self.db, ffeed(S1 + 1800, {S1: RATE}), S1 + 1800)["results"][led]
        self.assertEqual((r["status"], r["funding"]), ("closing", len(held)))
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])

    def test_cash_pnl_marks_and_reconciliation_include_funding(self):
        paper_runner.run(self.db, feed(SAT), SAT)
        eng = PaperEngine(self.db)
        before = eng.ledger(EID)
        paper_runner.run(self.db, ffeed(S1 + 1800, {S1: RATE}), S1 + 1800)
        led = eng.ledger(EID)
        fund = self.db.one("SELECT SUM(amount) FROM sim_funding WHERE exp_id=?", EID)[0]
        self.assertLess(fund, 0)
        self.assertAlmostEqual(led["funding"], fund, places=9)
        self.assertAlmostEqual(led["cash"], before["cash"] + fund, places=9)       # no trade on Saturday afternoon
        self.assertAlmostEqual(led["realized"], before["realized"] + fund, places=9)
        mark = self.db.one("SELECT equity, cash FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", EID)
        self.assertAlmostEqual(mark["cash"], led["cash"], places=9)                # the hourly mark includes it
        pnl = eng.pnl(EID, {s: 100.0 for s in led["positions"]})
        self.assertAlmostEqual(pnl["total"], pnl["realized"] + pnl["unrealized"], places=9)
        self.assertAlmostEqual(pnl["funding"], fund, places=9)
        rec = eng.reconcile(EID)
        self.assertTrue(rec["ok"], rec["problems"])
        c = rec["cash"]
        self.assertAlmostEqual(c["cash"], c["capital"] + c["fill_flows"] - c["fees"] + c["funding"], places=9)
        self.assertAlmostEqual(c["funding"], fund, places=9)

    def test_reconciliation_rejects_a_funding_row_that_does_not_match_the_fills(self):
        paper_runner.run(self.db, feed(SAT), SAT)
        s = data.UNIVERSE[0]
        q = PaperEngine(self.db).ledger(EID)["positions"][s]
        self.db.append("sim_funding", exp_id=EID, ts=int(S1), settle_ts=int(S1), instrument=s, qty=2 * q, rate=RATE,
                       price=100.0, amount=-2 * q * 100.0 * RATE)
        self.db.append("sim_funding", exp_id=EID, ts=int(S1), settle_ts=int(S0), instrument=s, qty=0.0, rate=RATE,
                       price=100.0, amount=1.0)
        rec = PaperEngine(self.db).reconcile(EID)
        self.assertFalse(rec["ok"])
        txt = "; ".join(rec["problems"])
        for want in ("is not the position held before the settlement", "is not after T_F",
                     "amount is not -qty * price * rate"):
            self.assertIn(want, txt)


class Balance(Base):
    def setUp(self):
        super().setUp()
        self.led = self.forward()
        paper_runner.run(self.db, feed(SAT), SAT)
        paper_runner.run(self.db, ffeed(S1 + 1800, {S1: RATE}), S1 + 1800)

    def last(self, led):
        return self.db.one("SELECT equity FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", led)[0]

    def test_formal_headline_excludes_forward_and_the_combined_overview_counts_nothing_twice(self):
        b = command.balance(self.db, S1 + 1800)
        self.assertEqual((b["strategies"], b["capital"], b["equity"]),
                         (1, paper_runner.CAPITAL, self.last(EID)))                   # FWD never in the headline
        f, c = b["forward"], b["combined"]
        self.assertEqual((f["ledgers"], f["capital"], f["equity"]), (1, paper_runner.CAPITAL, self.last(self.led)))
        self.assertFalse(f["approved"] or c["approved"])
        self.assertTrue(f["simulated"] and c["simulated"])
        self.assertIn("ikke godkendt", c["label"])
        for k in command.MONEY:
            self.assertAlmostEqual(c[k], b[k] + f[k], places=9, msg=k)
        self.assertEqual(c["capital"], 2 * paper_runner.CAPITAL)
        sums = {e: self.db.one("SELECT SUM(amount) FROM sim_funding WHERE exp_id=?", e)[0] for e in (EID, self.led)}
        self.assertAlmostEqual(b["funding"], sums[EID], places=9)
        self.assertAlmostEqual(f["funding"], sums[self.led], places=9)
        self.assertAlmostEqual(c["fees"], self.db.one("SELECT SUM(fee) FROM sim_fills")[0], places=9)
        self.assertAlmostEqual(b["pnl"], b["realized"] + b["unrealized"], places=6)
        rec = b["reconciliation"]
        self.assertTrue(rec["ok"], rec["details"])
        self.assertGreaterEqual(rec["checks"], 2 + 3 * len(command.MONEY))
        self.assertEqual((b["trading"], b["paused"], f["running"], f["paused"]), (1, 0, 1, 0))

    def test_reconciliation_catches_a_mark_that_disagrees_with_the_fills_and_funding(self):
        row = self.db.one("SELECT * FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", EID)
        self.db.append("sim_equity", exp_id=EID, ts=row["ts"] + 60, equity=row["equity"], cash=row["cash"] + 5.0,
                       exposure=row["exposure"], peak=row["peak"], drawdown=row["drawdown"])
        rec = command.balance(self.db, S1 + 1900)["reconciliation"]
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["problems"], [f"{EID}: equity - capital = realized + unrealized"])
        self.assertAlmostEqual(rec["details"][0]["diff"], 5.0, places=6)

    def test_paused_formal_ledger_is_counted_as_paused_not_trading(self):
        Risk(self.db, lambda: S1).pause(EID, "consecutive_losses", 2, 2, "test pause")
        b = command.balance(self.db, S1 + 1900)
        self.assertEqual((b["trading"], b["paused"]), (0, 1))


class Edge(Base):
    DAY = 86400

    def marks(self, led, closes, t0):
        """One mark at noon on day 0 (capital), then a close at 23:00 of each later day."""
        self.db.append("sim_equity", exp_id=led, ts=int(t0) + 12 * HOUR, equity=10000.0, cash=10000.0, exposure=0.0,
                       peak=10000.0, drawdown=0.0)
        for i, v in enumerate(closes):
            self.db.append("sim_equity", exp_id=led, ts=int(t0) + i * self.DAY + 23 * HOUR, equity=v, cash=v,
                           exposure=0.0, peak=10000.0, drawdown=0.0)

    def test_no_expectation_without_a_hash_verified_validation_series(self):
        t0 = int(SAT) // self.DAY * self.DAY
        self.marks(EID, [10000.0, 10100.0, 10000.0], t0)
        e = command.edge(self.db, EID, t0 + 3 * self.DAY + HOUR)
        self.assertIsNone(e["z"])
        self.assertIn("ingen forventning", e["no_expectation"])                    # no validate.json recorded
        frozen(self.db, EID, "validate", {"skipped": "rejected at cost check"})
        e = command.edge(self.db, EID, t0 + 3 * self.DAY + HOUR)
        self.assertEqual((e["z"], e["expectation"]), (None, None))
        self.assertIn("ingen forventning", e["no_expectation"])
        self.assertFalse(e["decisional"])

    def test_z_is_live_mean_minus_expected_mean_over_the_standard_error(self):
        t0 = int(SAT) // self.DAY * self.DAY
        closes = [10000.0, 10100.0, 10100.0 * 0.99, 10100.0 * 0.99 * 1.02]
        self.marks(EID, closes, t0)
        self.db.append("sim_equity", exp_id=EID, ts=t0 + 4 * self.DAY + HOUR, equity=1.0, cash=1.0, exposure=0.0,
                       peak=10000.0, drawdown=0.9999)                            # today: not a finished day
        val = [0.001, -0.002, 0.003, 0.0, 0.004]
        frozen(self.db, EID, "validate", {"daily_net": val})
        now = t0 + 4 * self.DAY + 2 * HOUR
        e = command.edge(self.db, EID, now)
        live = [0.01, -0.01, 0.02]
        self.assertEqual(e["days"], 3)
        self.assertAlmostEqual(e["net_per_day_pct"], statistics.mean(live), places=12)
        self.assertAlmostEqual(e["net_per_day"], (closes[-1] - closes[0]) / 3, places=9)
        m, sd = statistics.mean(val), statistics.stdev(val)
        self.assertAlmostEqual(e["z"], (statistics.mean(live) - m) / (sd / math.sqrt(3)), places=9)
        self.assertAlmostEqual(e["days_live"], (now - (t0 + 12 * HOUR)) / self.DAY, places=9)
        self.assertIsNone(command.edge(self.db, EID, t0 + 2 * self.DAY + HOUR)["z"])  # one daily return: no z
        self.db.event("paper.started", "agent:paper-1", "SHADOW_" + EID, {"capital": 10000.0, "costs": {
            "taker_fee": 0.0005}, "simulated": True})
        self.marks("SHADOW_" + EID, closes, t0)                                     # a shadow uses its base's series
        self.assertAlmostEqual(command.edge(self.db, "SHADOW_" + EID, now)["z"], e["z"], places=12)
        v = {s["exp_id"]: s for s in command.paper_view(self.db, now=now)["strategies"]}
        self.assertAlmostEqual(v["SHADOW_" + EID]["edge"]["z"], e["z"], places=12)

    def test_the_watcher_mentions_a_low_edge_but_never_fails_on_it(self):
        self.db.event("system.running", "system:supervisor", None, {"pid": 1})
        self.db.event("forward.approved", "human:test", "E_low", {"reason": "fixture"})
        self.db.event("paper.started", "agent:paper-1", "FWD_E_low", {"capital": 10000.0})
        frozen(self.db, "E_low", "validate", {"daily_net": [0.001 + 0.01 * (-1) ** i for i in range(100)]})
        now = time.time()
        t0 = int(now) // self.DAY * self.DAY - 16 * self.DAY
        self.marks("FWD_E_low", [10000.0 * 0.99 ** i for i in range(16)], t0)
        self.db.append("sim_equity", exp_id="FWD_E_low", ts=int(now) - 600, equity=8500.0, cash=8500.0,
                       exposure=0.0, peak=10000.0, drawdown=0.15)
        ok, why = watch._paper(self.path, now, {"status": "running"})
        self.assertTrue(ok, why)
        self.assertIn("edge below expectation (non-decisional", why)
        self.assertIn("FWD_E_low z=-", why)
        ok, why = watch._paper(self.path, t0 + 10 * self.DAY, {"status": "running"})      # under 14 days: silent
        self.assertNotIn("edge below", why)


class Truth(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        jobs.init(self.db)
        self.now = time.time()

    def test_data_updated_is_the_newest_of_research_and_live_market_data(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "klines"))
            f = os.path.join(d, "klines", "x.csv")
            open(f, "w").close()
            os.utime(f, (self.now - 9000, self.now - 9000))
            with mock.patch.object(command.mdata, "CACHE", d):
                self.db.append("datasets", exp_id="E", split="train", source="s", path="p", ts=int(self.now - 7200))
                self.db.append("events", ts=int(self.now - 3600), kind="scan.finished", actor="system:scanner",
                               exp_id=None, payload={})
                self.assertEqual(command.last_data_update(self.db)["newest_source"], "scanner pass")
                self.db.append("sim_equity", exp_id="FWD_x", ts=int(self.now - 600), equity=1.0, cash=1.0,
                               exposure=0.0, peak=1.0, drawdown=0.0)
                k = command.kpis(self.db, 900, self.now)["data"]
        self.assertEqual((k["newest_ts"], k["newest_source"]), (int(self.now - 600), "paper mark"))
        self.assertEqual((k["last_scan_ts"], k["last_gateway_read_ts"]), (int(self.now - 3600), int(self.now - 7200)))
        self.assertAlmostEqual(k["last_download_ts"], self.now - 9000, places=0)

    def test_agent_output_and_failures_in_the_last_24_hours(self):
        db = self.db
        for w in ("supervisor", "backtest-1", "discovery-scanner", "risk-1"):
            db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status) VALUES(?,?,1,1,'',?)",
                           (w, int(self.now), "running" if w == "supervisor" else "idle"))
        for _ in range(2):
            db.event("job.done", "backtest-1", "E1", {"job_id": "backtest|E1"})
        db.event("job.started", "backtest-1", "E1", {"job_id": "backtest|E1"})             # bookkeeping, not output
        db.event("job.retry", "backtest-1", "E1", {"job_id": "backtest|E1"})
        db.event("job.timeout", "system:queue", "E2", {"job_id": "backtest|E2", "owner": "backtest-1"})
        db.append("events", ts=int(self.now) - 90000, kind="job.done", actor="backtest-1", exp_id="E0", payload={})
        db.event("scan.finished", "system:scanner", None, {"observations": 3})
        db.event("market.event", "system:scanner", None, {"decision": "NO_ACTION"})
        a = {x["agent"]: x for x in command.agents(db, self.now)["agents"]}
        self.assertEqual({k: a["backtest-1"][k] for k in ("jobs_done_24h", "jobs_failed_24h", "output_24h")},
                         {"jobs_done_24h": 2, "jobs_failed_24h": 2, "output_24h": 2})
        self.assertEqual((a["discovery-scanner"]["output_24h"], a["discovery-scanner"]["jobs_done_24h"]), (2, 0))
        self.assertEqual(a["risk-1"]["output_24h"], 0)
        self.assertEqual(command.kpis(db, 900, self.now)["agents_with_output_24h"], 2)


class Dashboard(unittest.TestCase):
    def test_simulated_overview_row_is_separate_from_the_formal_saldo(self):
        with open(os.path.join(os.path.dirname(command.__file__), "dashboard.html"), encoding="utf-8") as f:
            html = f.read()
        for s in ("SIMULERET SAMLET (ikke godkendt)", "Fremadtest-saldo", "Samlet simuleret værdi",
                  "Samlet simuleret P&amp;L", "med output 24 t", "data.newest_ts", "Edge mod validering (z)",
                  "ingen forventning"):
            self.assertIn(s, html)
        self.assertEqual(html.count('class="mcard'), 7)                            # 4 money cards + one row of 3
        self.assertNotIn("fremadtest udenfor saldoen", html)                       # moved out of #balsub

    def test_each_paper_group_is_shown_on_its_own_row_and_marked_simulated(self):
        """research/LINUX_DRIFT.md 2026-10-23: one account table, a row per group (lanes, forward test, shadow)
        and a total, all simulated; replaces the seven money cards whose biggest number was the shadow account."""
        with open(os.path.join(os.path.dirname(command.__file__), "dashboard.html"), encoding="utf-8") as f:
            html = f.read()
        for s in ('"Baner og scanner"', '"Fremadtest"', '"Skyggehandel"', "I alt (alt simuleret)", "Saldo (paper)",
                  "ikke godkendt", "simuleret · ingen rigtige penge · ikke bevis", "AFSTEMNING AFVIGER",
                  "med output 24 t", "data.newest_ts", "Edge mod validering (z)", "ingen forventning"):
            self.assertIn(s, html)
        self.assertIn("renderAccounts(b)", html)                                  # under the cards (user, 2026-10-23)


class VerifierFindings(Base):
    """Findings of the adversarial review of the paper accounting (2026-10-19), adopted from its probes."""

    def test_funding_after_a_flat_spell_longer_than_the_1000_bar_window(self):
        nopause = mock.patch("lab.risk.Risk.after_trade_closed", lambda *a, **k: None)
        nopause.start()
        self.addCleanup(nopause.stop)
        paper_runner.run(self.db, feed(SAT), SAT)                                    # T_F = SAT, long all 8
        mon_settle = int(MON) // HOUR * HOUR
        paper_runner.run(self.db, ffeed(MON, {mon_settle: RATE}), MON)              # books Mon 00:00, goes flat
        self.assertEqual(len(self.rows(EID)), len(data.UNIVERSE))
        sat2 = SAT + 49 * 86400                                                      # seven weeks later
        s_new = int(sat2) // HOUR * HOUR + 6 * HOUR
        rates = {t: RATE for t in range(mon_settle, s_new + 1, 8 * HOUR)}
        self.assertLess(len(rates), 200)
        r = paper_runner.run(self.db, ffeed(sat2, rates), sat2)["results"][EID]
        self.assertEqual(r["status"], "ok")
        paper_runner.run(self.db, ffeed(s_new + 1800, rates), s_new + 1800)
        self.assertIn(s_new, {x["settle_ts"] for x in self.rows(EID)})              # never blocked for good

    def test_reconcile_reads_one_snapshot_while_another_connection_fills(self):
        paper_runner.run(self.db, feed(SAT), SAT)
        other = DB(self.path)
        self.addCleanup(other.close)
        book = Book(ts=SAT + 60, bids=((99.99, 1000.0),), asks=((100.01, 1000.0),))
        real, done = paper.held_before, []

        def hb(fills, points):
            if not done:                                  # paper-1 commits a fill in the middle of risk-1's reconcile
                done.append(PaperEngine(other, lambda: SAT + 60).submit_taker(EID, "race|1", data.UNIVERSE[0], "sell",
                                                                             0.5, book, reduce_only=True))
            return real(fills, points)
        with mock.patch.object(paper, "held_before", hb):
            rec = PaperEngine(self.db).reconcile(EID)
        self.assertEqual(done[0]["status"], "filled")
        self.assertTrue(rec["ok"], rec["problems"])                                  # no false FAIL_CLOSED

    def test_balance_reads_one_snapshot_while_another_connection_fills(self):
        from lab import command
        paper_runner.run(self.db, feed(SAT), SAT)
        other = DB(self.path)
        self.addCleanup(other.close)
        book = Book(ts=SAT + 60, bids=((99.99, 1000.0),), asks=((100.01, 1000.0),))
        real = command._balance_reconciliation

        def wrapped(db, out, st, fw):
            PaperEngine(other, lambda: SAT + 60).submit_taker(EID, "race|2", data.UNIVERSE[0], "sell", 0.5, book,
                                                              reduce_only=True)
            return real(db, out, st, fw)
        with mock.patch.object(command, "_balance_reconciliation", wrapped):
            rec = command.balance(self.db, SAT + 60)["reconciliation"]
        self.assertTrue(rec["ok"], rec["problems"])


if __name__ == "__main__":
    unittest.main()
