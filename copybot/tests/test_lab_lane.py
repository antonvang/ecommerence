"""research/PROTOCOL_V3.md amendment 11: lane accounts trade the exploration lane's candidates on paper and retire by
fixed rules. Simulated only; never evidence; nothing formal is written."""
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import __main__ as cli, command, explore, lane, lifecycle, paper_runner, pipeline, promotion, scanner  # noqa: E402
from lab import jobs, watch  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402

HOUR, DAY = 3600, 86400
NOW = datetime(2026, 10, 20, 2, 30, tzinfo=timezone.utc).timestamp()      # after the 01:00 UTC decision
COINS = ["ADAUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "XRPUSDT"]


def market(rate=0.0003, px=100.0, spot_px=100.0, spread=0.02, missing=(), log=None):
    """Fake public REST: USD-M klines, settled funding every 8 h at `rate`, USD-M and spot depth. `missing`: symbols
    whose spot book fails. `log` collects every URL asked for."""
    def get(path):
        if log is not None:
            log.append(path)
        if path.startswith("https://data-api.binance.vision/api/v3/depth"):
            sym = path.split("symbol=")[1].split("&")[0]
            if sym in missing:
                raise OSError("HTTP 400 invalid symbol")
            return {"bids": [[str(spot_px - spread / 2), "1000"]], "asks": [[str(spot_px + spread / 2), "1000"]]}
        if path.startswith("https://"):
            raise AssertionError(path)
        now = get.now
        if "klines" in path:
            start = int(now) // HOUR * HOUR - 1000 * HOUR
            return [[(start + i * HOUR) * 1000, px, px, px, px, 1, (start + (i + 1) * HOUR) * 1000 - 1, 100.0]
                    for i in range(1001)]                  # as Binance: the bar in progress comes last
        if "fundingRate" in path:
            if rate is None:                               # no settlement published
                return []
            last = int(now) // (8 * HOUR) * 8 * HOUR
            return [{"fundingTime": (last - k * 8 * HOUR) * 1000, "fundingRate": str(rate)} for k in range(199, -1, -1)]
        if "/fapi/v1/depth" in path:
            return {"bids": [[str(px - spread / 2), "1000"]], "asks": [[str(px + spread / 2), "1000"]]}
        raise AssertionError(path)
    get.now = NOW
    return get


def result(key="fcarry.carry_filter|a", fn="carry_filter", params=None, coins=None, sharpe=2.0, cand=True, fam="fcarry"):
    return {"key": key, "family": fam, "function": fn, "params": params or {"lookback_days": 7, "enter_apr": 0.1},
            "coins": coins, "net_sharpe_ann": sharpe, "net_total": 0.73, "days": 730, "candidate": cand,
            "checks": {"a": cand, "b": True, "c": True}, "method": explore.METHOD}


_EU = mock.patch.object(lane, "eu_block", lambda coin: None)    # amendment 30a is tested in test_lab_venue.py


def setUpModule():
    _EU.start()


def tearDownModule():
    _EU.stop()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lablane")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch.object(explore, "eligible", lambda db: ["fcarry"]),
                  mock.patch.object(explore, "universe", lambda fam: tuple(COINS)),
                  mock.patch.object(paper_runner, "HL_POST", self.no_network),          # no test reaches Hyperliquid
                  mock.patch.object(scanner, "http_post", self.no_network)]
        for p in self.p:
            p.start()
        lane._CANDIDATES.clear()
        lane._SPOT_LIST.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def no_network(*a, **k):
        raise AssertionError(f"network call in a test: {a}")

    def publish(self, results, name="fcarry_1", record=True, reviewed=True):
        art = pipeline.save_artifact(os.path.join(explore.DIR, "2026-10-19"), name,
                                     {"label": explore.LABEL, "family": "fcarry", "results": results})
        if record:
            self.db.event("research.explore", "system:backtest-1", None,
                          {"family": "fcarry", "variants": [r["key"] for r in results], "decisional": False,
                           "artifact_sha256": art["sha256"]})
        for r in results if reviewed else ():          # amendment 11c: a passed review lets a candidate start
            self.db.event("research.lane_review", "system:adversarial-1", None, {"key": r["key"], "ok": True,
                                                                                  "method": lane.REVIEW_METHOD})
        return art

    def started(self, get=None, now=NOW, **kw):
        self.publish([result(**kw)])
        out = lane.manage(self.db, now, get or market(), fids=["fcarry"])
        self.assertIsNotNone(out["started"], out)
        return out["started"]

    def mark(self, led, ts, equity):
        self.db.append("sim_equity", exp_id=led, ts=int(ts), equity=equity, cash=equity, exposure=0.0, peak=10_000.0,
                       drawdown=max(0.0, 1 - equity / 10_000.0))


class Candidates(Base):
    def test_only_recorded_candidates_best_first(self):
        self.publish([result("k1", sharpe=1.5), result("k2", sharpe=3.0), result("k3", cand=False)])
        self.publish([result("k4", sharpe=9.0)], name="fcarry_2", record=False)    # no research.explore event
        self.assertEqual([r["key"] for r in lane.candidates(self.db, ["fcarry"])], ["k2", "k1"])

    def test_family_without_live_model_is_not_traded(self):
        self.publish([result("d1", fam="dbasis", fn="basis_threshold")])
        self.assertEqual(lane.candidates(self.db, ["dbasis"]), [])

    def test_expectation_is_per_capital_half_of_the_one_leg_backtest(self):
        e = lane.expectation(result(sharpe=2.0))
        m = 0.73 / 730
        self.assertAlmostEqual(e["mean"], m / 2)
        self.assertAlmostEqual(e["sd"], m * math.sqrt(365) / 2.0 / 2)


class Start(Base):
    def test_starts_one_per_ten_minutes_two_per_function_at_most_six(self):
        floor = {"days": 7, "q": 0.8}
        hyst = {"lookback_days": 7, "exit_apr": 0.0}
        self.publish([result("a1", sharpe=9), result("a2", sharpe=8), result("a3", sharpe=7),
                      result("b1", fn="carry_floor", sharpe=6, params=floor),
                      result("b2", fn="carry_floor", sharpe=5, params=floor),
                      result("c1", fn="carry_hysteresis", sharpe=4, params=hyst),
                      result("c2", fn="carry_hysteresis", sharpe=3, params=hyst),
                      result("d1", fn="carry_filter_weekly", sharpe=2)])
        get = market()
        self.assertEqual(lane.manage(self.db, NOW, get, fids=["fcarry"])["started"], lane.ledger_id("a1"))
        self.assertIsNone(lane.manage(self.db, NOW + 60, get, fids=["fcarry"])["started"])     # one per 10 minutes
        got = [lane.manage(self.db, NOW + k * lane.START_EVERY, get, fids=["fcarry"])["started"] for k in range(1, 7)]
        self.assertEqual(got[:5], [lane.ledger_id(k) for k in ("a2", "b1", "b2", "c1", "c2")])   # a3: a1, a2 hold it
        self.assertIsNone(got[5])                                                                 # six slots
        self.assertEqual(len(lane.active(self.db)), lane.SLOTS)

    def test_coins_without_both_books_are_dropped_and_too_few_skip(self):
        with mock.patch.object(explore, "universe", lambda fam: tuple(COINS + ["SOLUSDT"])):
            led = self.started(market(missing=("DOGEUSDT",)), coins=None)
        info = lane.started(self.db)[led]
        self.assertNotIn("DOGEUSDT", info["coins"])
        self.assertEqual(len(info["coins"]), 5)
        self.assertEqual([d["coin"] for d in info["dropped"]], ["DOGEUSDT"])
        self.publish([result("k9", fn="carry_floor", params={"days": 7, "q": 0.8})], name="fcarry_9")
        out = lane.manage(self.db, NOW + HOUR, market(missing=("ADAUSDT",)), fids=["fcarry"])
        self.assertEqual(out["skipped"], ["k9"])
        self.assertIsNone(out["started"])
        self.assertIn("k9", lane.tried_keys(self.db))

    def test_all_coins_means_the_coins_it_was_tested_on(self):
        art = pipeline.save_artifact(os.path.join(explore.DIR, "2026-10-19"), "fcarry_t",
                                     {"label": explore.LABEL, "family": "fcarry", "coins": COINS[:5],
                                      "results": [result()]})
        self.db.event("research.explore", "system:backtest-1", None, {"artifact_sha256": art["sha256"]})
        self.db.event("research.lane_review", "system:adversarial-1", None, {"key": "fcarry.carry_filter|a", "ok": True,
                                                                                    "method": lane.REVIEW_METHOD})
        with mock.patch.object(explore, "universe", lambda fam: tuple(COINS + ["SOLUSDT", "APEUSDT"])):
            led = lane.manage(self.db, NOW, market(), fids=["fcarry"])["started"]
        self.assertEqual(lane.started(self.db)[led]["coins"], COINS[:5])

    def test_an_account_trading_untested_coins_is_retired(self):
        art = pipeline.save_artifact(os.path.join(explore.DIR, "2026-10-19"), "fcarry_t",
                                     {"label": explore.LABEL, "family": "fcarry", "coins": COINS[:5],
                                      "results": [result()]})
        led = lane.ledger_id("fcarry.carry_filter|a")             # as started before the fix: all universe coins
        self.db.event("lane.started", lane.ACTOR, led, {"key": "fcarry.carry_filter|a", "family": "fcarry",
                                                        "function": "carry_filter", "params": {}, "basket": None,
                                                        "coins": COINS + ["APEUSDT"], "artifact": art["path"],
                                                        "artifact_sha256": art["sha256"], "t": int(NOW)})
        self.assertEqual(lane.manage(self.db, NOW + 60, None, fids=["fcarry"])["retired"], [led])
        self.assertEqual(lane.retired(self.db)[led]["rule"], "basket")

    def test_no_start_while_fail_closed_or_off(self):
        self.publish([result()])
        Risk(self.db).trip_fail_closed("test", "fixture")
        self.assertIsNone(lane.manage(self.db, NOW, market(), fids=["fcarry"])["started"])


class Trade(Base):
    def test_hedged_entry_funding_on_perp_only_and_reconciled(self):
        led = self.started()
        get = market()
        r = lane.run_one(self.db, led, get, NOW)
        self.assertEqual(r["status"], "ok", r)
        self.assertTrue(all(v == 1.0 for v in r["signal"].values()))
        pos = PaperEngine(self.db).ledger(led)["positions"]
        for s in COINS:
            self.assertAlmostEqual(pos[s + lane.SPOT], -pos[s])
            self.assertGreater(pos[s + lane.SPOT], 0)
            self.assertAlmostEqual(pos[s + lane.SPOT] * 100.0, 10_000 / (2 * len(COINS)), delta=1.0)
        self.assertTrue(r["reconciled"])
        self.assertFalse(Risk(self.db).fail_closed())
        get.now = NOW + 8 * HOUR                       # one settlement later
        lane.run_one(self.db, led, get, NOW + 8 * HOUR)
        rows = self.db.q("SELECT instrument, amount FROM sim_funding WHERE exp_id=?", led)
        self.assertTrue(rows)
        self.assertTrue(all(not x["instrument"].endswith(lane.SPOT) and x["amount"] > 0 for x in rows))
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])

    def test_no_signal_no_orders_and_no_rebalancing(self):
        led = self.started()
        r = lane.run_one(self.db, led, market(rate=0.0), NOW)
        self.assertEqual(r["orders"], [])
        lane.run_one(self.db, led, market(), NOW + HOUR)
        n = self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", led)[0]
        g = market(px=110.0)                            # the price moved: the quantity is held, nothing rebalances
        g.now = NOW + 2 * HOUR
        lane.run_one(self.db, led, g, NOW + 2 * HOUR)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders WHERE exp_id=?", led)[0], n)

    def test_signal_off_closes_both_legs(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)
        g = market(rate=0.0)
        g.now = NOW + 2 * DAY
        lane.run_one(self.db, led, g, NOW + 2 * DAY)
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})

    def test_31_running_lane_opens_only_within_the_floor_and_always_closes(self):
        led = self.started()
        wide = market(spread=0.4)                       # 0.4 % a leg, 0.8 % a coin: over 0.46 %
        r = lane.run_one(self.db, led, wide, NOW)
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertEqual({o["status"] for o in r["orders"]}, {"not sent: likviditetsregel (31)"})
        self.assertEqual(len(r["orders"]), 2 * len(COINS))
        lane.run_one(self.db, led, wide, NOW + 60)      # the same hour again: no repeat rows
        rows = [json.loads(x["payload"]) for x in
                self.db.q("SELECT payload FROM events WHERE kind='paper.skipped' AND exp_id=?", led)]
        self.assertEqual(sorted(p["coin"] for p in rows), sorted(COINS))
        self.assertTrue(all("likviditetsregel (31): bogens rundtur" in p["reason"] for p in rows))
        self.assertAlmostEqual(rows[0]["liquidity"]["round_trip"], 0.008, places=6)
        good = market()
        good.now = NOW + HOUR                           # the book is fine again: the lane opens
        lane.run_one(self.db, led, good, NOW + HOUR)
        self.assertEqual(len(PaperEngine(self.db).ledger(led)["positions"]), 2 * len(COINS))
        off = market(rate=0.0, spread=2.0)             # a 4 % book never blocks a close
        off.now = NOW + 2 * DAY
        lane.run_one(self.db, led, off, NOW + 2 * DAY)
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertEqual(len(self.db.q("SELECT 1 FROM events WHERE kind='paper.skipped' AND exp_id=?", led)),
                         len(COINS))

    def test_only_public_depth_on_the_spot_host(self):
        log = []
        led = self.started(market(log=log))
        lane.run_one(self.db, led, market(log=log), NOW)
        spot = [u for u in log if u.startswith("https://")]
        self.assertTrue(spot)
        self.assertTrue(all(u.startswith("https://data-api.binance.vision/api/v3/depth?symbol=") and u.endswith("&limit=20")
                            for u in spot))

    def test_runner_trades_and_nothing_formal_is_written(self):
        self.publish([result()])
        paper_runner.run(self.db, get=market(), now=NOW)            # manage starts it; the next pass trades it
        led = lane.active(self.db)[0]
        res = paper_runner.run(self.db, get=market(), now=NOW + 60)
        self.assertEqual(res["results"][led]["status"], "ok", res)
        for t in ("results", "trials", "transitions", "approvals", "alpha_ledger"):
            if self.db.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", t):
                self.assertEqual(self.db.one(f"SELECT COUNT(*) FROM {t}")[0], 0, t)
        self.assertTrue(promotion.exposure_allowed(self.db, led, NOW)[0])
        self.assertTrue(promotion._ledgers_reconcile(self.db))


class Retire(Base):
    def test_loss_retires_and_runner_closes_reduce_only(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)
        self.mark(led, NOW + 30, 9_650.0)
        out = lane.manage(self.db, NOW + 60, market(), fids=["fcarry"])
        self.assertEqual(out["retired"], [led])
        self.assertEqual(lane.retired(self.db)[led]["rule"], "loss")
        self.assertFalse(lane.is_active(self.db, led))
        g = market()
        g.now = NOW + HOUR
        paper_runner.run(self.db, get=g, now=NOW + HOUR)
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertTrue(all(o["reduce_only"] for o in self.db.q("SELECT reduce_only FROM sim_orders WHERE exp_id=? "
                                                                 "AND order_id LIKE '%close%'", led)))

    def test_a_closed_ledger_gets_a_final_mark_in_the_same_hour(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)                      # opens and marks this hour
        lane.retire(self.db, led, "edge", "fixture", now=NOW + 60)
        g = market(spread=2.0)                                         # a wide book: the close costs money
        g.now = NOW + 600                                              # same clock hour as the mark
        paper_runner.run(self.db, get=g, now=NOW + 600)
        eng = PaperEngine(self.db)
        self.assertEqual(eng.ledger(led)["positions"], {})
        last = self.db.one("SELECT equity, ts FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1", led)
        self.assertEqual(last["ts"], int(NOW + 600))
        self.assertAlmostEqual(last["equity"], eng.ledger(led)["cash"])
        self.assertEqual(paper_runner.closing_ledgers(self.db), [])   # done: not processed again
        self.assertTrue(eng.reconcile(led)["ok"])

    def test_edge_missing_after_seven_days(self):
        led = self.started(sharpe=10.0)                   # sd 0.1 %/day on capital
        lane.run_one(self.db, led, market(), NOW)         # holds positions (not flat)
        day0 = int(NOW) // DAY * DAY
        eq = 10_000.0
        for d in range(9):                                # -0.3 %/day: far below, still above the 3 % loss stop
            self.mark(led, day0 + d * DAY + 23 * HOUR, eq)
            eq *= 0.997
        self.assertIsNone(lane.manage(self.db, day0 + 7 * DAY + 60, None, fids=["fcarry"])["started"])
        self.assertTrue(lane.is_active(self.db, led))     # 6 daily returns: not yet
        out = lane.manage(self.db, day0 + 9 * DAY + 60, None, fids=["fcarry"])
        self.assertEqual(out["retired"], [led])
        r = lane.retired(self.db)[led]
        self.assertEqual(r["rule"], "edge")
        self.assertLessEqual(r["stats"]["z"], lane.Z_RETIRE)

    def test_paused_for_a_day_family_gone_expired(self):
        led = self.started()
        Risk(self.db, lambda: NOW).pause(led, "data_fetch", None, None, "fixture")
        self.assertEqual(lane.manage(self.db, NOW + 3600, None, fids=["fcarry"])["retired"], [])
        self.assertEqual(lane.manage(self.db, NOW + DAY + 1, None, fids=["fcarry"])["retired"], [led])
        led2 = self.started(now=NOW + 2 * DAY, key="k2", fn="carry_floor", params={"days": 7, "q": 0.8})
        self.assertEqual(lane.manage(self.db, NOW + 2 * DAY + 60, None, fids=[])["retired"], [led2])
        led3 = self.started(now=NOW + 3 * DAY, key="k3", fn="carry_hysteresis",
                            params={"lookback_days": 7, "exit_apr": 0.0})
        out = lane.manage(self.db, NOW + 3 * DAY + lane.MAX_AGE_S, None, fids=["fcarry"])
        self.assertEqual(out["retired"], [led3])
        self.assertEqual({lane.retired(self.db)[x]["rule"] for x in (led, led2, led3)}, {"paused", "family", "expired"})

    def test_flat_lane_account_retires_after_three_days(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)                  # holds
        g = market(rate=0.0)
        g.now = NOW + HOUR
        lane.run_one(self.db, led, g, NOW + HOUR)                  # out: flat from its last trade
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertEqual(lane.manage(self.db, NOW + HOUR + 3 * DAY - 60, None, fids=["fcarry"])["retired"], [])
        self.assertEqual(lane.manage(self.db, NOW + HOUR + 3 * DAY, None, fids=["fcarry"])["retired"], [led])
        self.assertEqual(lane.retired(self.db)[led]["rule"], "flat")

    def test_a_lane_account_that_never_traded_retires_a_day_after_start(self):
        """Amendment 11f."""
        led = self.started()
        lane.run_one(self.db, led, market(rate=0.0), NOW)          # never on: no position
        self.assertEqual(lane.manage(self.db, NOW + DAY - 60, None, fids=["fcarry"])["retired"], [])
        self.assertEqual(lane.manage(self.db, NOW + DAY, None, fids=["fcarry"])["retired"], [led])
        r = lane.retired(self.db)[led]
        self.assertEqual((r["rule"], r["detail"]), ("flat", "ingen position siden start i 24 timer (11f)"))

    def test_a_variant_that_holds_nothing_reads_no_book(self):
        """Amendment 11h: 11b is checked on the hourly data before any book is read."""
        self.publish([result()])
        log = []
        out = lane.manage(self.db, NOW, market(rate=0.0, log=log), fids=["fcarry"])
        self.assertEqual((out["started"], out["skipped"]), (None, ["fcarry.carry_filter|a"]))
        self.assertFalse([u for u in log if "depth" in u], log)
        skip = [p for _, _, _, _, p in lane._events(self.db, "lane.skipped")][-1]
        self.assertEqual((skip["reason"], skip["retry"], skip["books_read"]), ("would hold nothing now (11b)", True,
                                                                                False))
        log.clear()
        self.assertIsNotNone(lane.manage(self.db, NOW + DAY, market(log=log), fids=["fcarry"])["started"])
        self.assertTrue([u for u in log if "depth" in u])                             # holds: the books are read

    def test_a_variant_that_would_hold_nothing_now_is_skipped_and_retried_a_day_later(self):
        self.publish([result()])
        out = lane.manage(self.db, NOW, market(rate=0.0), fids=["fcarry"])
        self.assertEqual((out["started"], out["skipped"]), (None, ["fcarry.carry_filter|a"]))
        self.assertIsNone(lane.manage(self.db, NOW + HOUR, market(), fids=["fcarry"])["started"])
        self.assertIsNotNone(lane.manage(self.db, NOW + lane.RETRY_S, market(), fids=["fcarry"])["started"])

    def test_a_retired_variant_never_restarts(self):
        led = self.started()
        lane.retire(self.db, led, "edge", "fixture")
        self.assertIsNone(lane.manage(self.db, NOW + 2 * HOUR, market(), fids=["fcarry"])["started"])

    def test_human_off_retires_all_and_blocks_starts(self):
        led = self.started()
        with self.assertRaises(lifecycle.LifecycleError):
            lane.set_policy(self.db, False, "system:x", "an agent may not do this")
        lane.set_policy(self.db, False, "human:test", "stop all lane accounts now")
        self.assertEqual(lane.manage(self.db, NOW + 60, market(), fids=["fcarry"])["retired"], [led])
        self.publish([result("k2", fn="carry_floor", params={"days": 7, "q": 0.8})], name="fcarry_2")
        self.assertIsNone(lane.manage(self.db, NOW + 2 * HOUR, market(), fids=["fcarry"])["started"])
        lane.set_policy(self.db, True, "human:test", "lane accounts may start again")
        self.assertIsNotNone(lane.manage(self.db, NOW + 3 * HOUR, market(), fids=["fcarry"])["started"])

    def test_cli_lane_off_refused_in_an_assistant_session(self):
        lines = []
        with mock.patch.object(cli, "TERMINAL_GUARD", lambda step: "an assistant session may not " + step):
            rc = cli.main(["lane-off", "--reason", "stop everything please"], db_path=self.db.path, out=lines.append)
        self.assertEqual(rc, 1)
        self.assertTrue(lane.policy_on(self.db))

    def test_source_rule_retires_an_account_whose_funding_does_not_pay(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)                  # positions, then no pass books any funding
        self.assertEqual(lane.manage(self.db, NOW + 13 * DAY, None, fids=["fcarry"])["retired"], [])
        self.assertEqual(lane.manage(self.db, NOW + 14 * DAY, None, fids=["fcarry"])["retired"], [led])
        self.assertEqual(lane.retired(self.db)[led]["rule"], "source")

    def test_source_rule_keeps_an_account_paid_by_funding(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)
        g = market()
        g.now = NOW + 4 * DAY
        lane.run_one(self.db, led, g, NOW + 4 * DAY)
        led_ = PaperEngine(self.db).ledger(led)
        self.assertGreater(led_["funding"], led_["fees"])
        self.assertEqual(lane.manage(self.db, NOW + 14 * DAY, None, fids=["fcarry"])["retired"], [])

    def test_promising_is_recorded_once_and_decides_nothing(self):
        led = self.started(sharpe=0.5)                     # a low expectation, met by a steady gain
        lane.run_one(self.db, led, market(), NOW)
        g = market()
        g.now = NOW + 4 * DAY
        lane.run_one(self.db, led, g, NOW + 4 * DAY)        # funding pays the fees (the source rule holds)
        day0 = int(NOW) // DAY * DAY
        eq = 10_000.0
        for d in range(32):
            eq *= 1.0006
            self.mark(led, day0 + d * DAY + 23 * HOUR, eq)
        lane.manage(self.db, day0 + 32 * DAY + 60, None, fids=["fcarry"])
        lane.manage(self.db, day0 + 32 * DAY + 120, None, fids=["fcarry"])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='lane.promising'")[0], 1)
        self.assertTrue(lane.is_active(self.db, led))


class Views(Base):
    def test_balance_watch_and_feed_keep_lane_apart(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)
        with mock.patch("time.time", lambda: NOW + 60):
            b = command.balance(self.db, now=NOW + 60)
            v = command.paper_view(self.db, now=NOW + 60)
        self.assertIsNone(b["capital"])                    # no formal ledger: the lane is never in the headline
        self.assertEqual(b["lane"]["ledgers"], 1)
        self.assertFalse(b["lane"]["evidence"])
        self.assertEqual(b["combined"]["ledgers"], 0)
        s = next(x for x in v["strategies"] if x["exp_id"] == led)
        self.assertTrue(s["lane"])
        self.assertEqual(s["label"], lane.LABEL)
        self.assertIn("Banekonto fcarry.carry_filter", s["name"])
        con = self.db.con
        self.assertIn(led, watch._active_ledgers(con))
        kinds = {i["tag"] for i in command.feed(self.db)["items"]}
        self.assertIn("BANEKONTO", kinds)


def hi():
    return market(rate=0.0008)                         # settled funding persistent above 0.05 %


class Scanner(Base):
    """Amendments 12, 12c and 12e: scanner accounts follow persistent high predicted funding."""
    def setUp(self):
        super().setUp()
        scanner.LIVE.clear()

    def scan(self, ts, fund):
        """One premium-watch measurement: symbols_compared plus flagged predicted_funding rows."""
        self.db.append("observations", ts=int(ts), detector="pricing_constraint/2", source="premiumIndex",
                       instrument="binance_perps", metric="symbols_compared", value=100, threshold=None, flagged=0,
                       payload=None)
        for sym, v in fund.items():
            self.db.append("observations", ts=int(ts), detector="pricing_constraint/2", source="premiumIndex",
                           instrument=sym, metric="predicted_funding", value=v, threshold=0.001, flagged=1,
                           payload=None)

    def live(self, ts, fund):
        scanner.LIVE[scanner.BN] = (int(ts), dict(fund))

    def test_entry_candidates(self):
        self.scan(NOW - 120, {"AAAUSDT": 0.0011, "CCCUSDT": 0.002})
        self.scan(NOW - 60, {"AAAUSDT": 0.0012, "BBBUSDT": 0.003})
        self.assertEqual(lane.scan_candidates(self.db, NOW), ["BBBUSDT", "AAAUSDT"])   # latest measurement only

    def test_stale_measurements_open_nothing_and_hold(self):
        self.scan(NOW - 4 * HOUR, {"BBBUSDT": 0.003})
        self.assertEqual(lane.scan_candidates(self.db, NOW), [])
        self.assertEqual(lane.scan_signal(self.db, "BBBUSDT", True, NOW), 1.0)
        self.assertEqual(lane.scan_signal(self.db, "BBBUSDT", False, NOW), 0.0)

    def test_settled_funding_must_be_persistent(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        out = lane.manage(self.db, NOW, market(rate=0.0001), fids=[])["scanner"]
        self.assertEqual((out["started"], out["skipped"]), ([], ["BBBUSDT"]))
        self.assertEqual(lane.manage(self.db, NOW + 600, hi(), fids=[])["scanner"]["started"], [])   # 1 h wait
        led = lane.manage(self.db, NOW + HOUR, hi(), fids=[])["scanner"]["started"][0]
        t = lane.started(self.db)[led]["trigger"]
        self.assertEqual((t["funding"], round(t["settled_avg3"], 6)), (0.003, 0.0008))

    def test_starts_at_once_up_to_ten_independent_of_lane_slots(self):
        self.scan(NOW - 60, {f"C{i:02d}USDT": 0.001 + i / 10000 for i in range(12)})
        per_pass = [len(lane.manage(self.db, NOW + 60 * k, hi(), fids=[])["scanner"]["started"]) for k in range(5)]
        self.assertEqual(per_pass, [lane.PROBES, lane.PROBES, lane.PROBES, 1, 0])      # probes per pass, ten in all
        info = lane.started(self.db)
        self.assertEqual(len(info), lane.SCAN_SLOTS)
        self.assertTrue(all(lane.is_scanner(i) and len(i["coins"]) == 1 for i in info.values()))
        self.assertEqual(sorted(i["coins"][0] for i in info.values()), [f"C{i:02d}USDT" for i in range(2, 12)])
        self.publish([result()])                                                     # the lane still starts its own
        self.assertIsNotNone(lane.manage(self.db, NOW + 600, hi(), fids=["fcarry"])["started"])

    def test_holds_until_two_settled_rates_are_low_and_a_settlement_is_booked(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        r = lane.run_one(self.db, led, hi(), NOW)
        self.assertEqual(r["signal"], {"BBBUSDT": 1.0})
        pos = PaperEngine(self.db).ledger(led)["positions"]
        self.assertAlmostEqual(pos["BBBUSDT.SPOT"], -pos["BBBUSDT"])
        self.assertAlmostEqual(pos["BBBUSDT.SPOT"] * 100.0, 5_000, delta=2.0)       # half the account per leg
        low = market(rate=0.00005)                                                  # settled below the floor
        low.now = NOW + HOUR
        self.assertEqual(lane.run_one(self.db, led, low, low.now)["signal"], {"BBBUSDT": 1.0})   # no settlement yet
        low.now = NOW + 6 * HOUR                                                    # 08:30: 08:00 is booked
        self.assertEqual(lane.run_one(self.db, led, low, low.now)["signal"], {"BBBUSDT": 0.0})
        self.assertTrue(self.db.one("SELECT 1 FROM sim_funding WHERE exp_id=? AND instrument='BBBUSDT'", led))
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])

    def test_high_settled_rates_or_no_settled_data_hold(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, hi(), NOW)
        g = hi()
        g.now = NOW + 13 * HOUR
        self.assertEqual(lane.run_one(self.db, led, g, g.now)["signal"], {"BBBUSDT": 1.0})
        none = market(rate=None)
        none.now = NOW + 20 * HOUR
        self.assertEqual(lane.run_one(self.db, led, none, none.now)["signal"], {"BBBUSDT": 1.0})

    def test_reopens_only_on_two_high_measurements(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, hi(), NOW)
        low = market(rate=0.00005)
        low.now = NOW + 6 * HOUR
        lane.run_one(self.db, led, low, low.now)
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.scan(NOW + 13 * HOUR + 120, {})                                       # funding no longer high
        self.scan(NOW + 14 * HOUR, {"BBBUSDT": 0.002})
        self.assertEqual(lane.scan_signal(self.db, "BBBUSDT", False, NOW + 14 * HOUR + 10, led), 0.0)   # one only
        self.scan(NOW + 14 * HOUR + 60, {"BBBUSDT": 0.002})
        self.assertEqual(lane.scan_signal(self.db, "BBBUSDT", False, NOW + 14 * HOUR + 70, led), 1.0)

    def test_retire_rules_and_cooldown(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, hi(), NOW)
        self.mark(led, NOW + 30, 9_600.0)                                            # -4 %: below the 5 % stop
        self.assertEqual(lane.manage(self.db, NOW + 60, None, fids=[])["retired"], [])
        self.mark(led, NOW + 90, 9_450.0)
        self.assertEqual(lane.manage(self.db, NOW + 120, None, fids=[])["retired"], [led])
        self.assertEqual(lane.retired(self.db)[led]["rule"], "loss")
        self.scan(NOW + 180, {"BBBUSDT": 0.003})
        self.assertEqual(lane.manage(self.db, NOW + 240, hi(), fids=[])["scanner"]["started"], [])   # cooldown
        self.scan(NOW + lane.SCAN_COOLDOWN_S + 200, {"BBBUSDT": 0.003})
        out = lane.manage(self.db, NOW + 240 + lane.SCAN_COOLDOWN_S, hi(), fids=[])
        self.assertEqual(len(out["scanner"]["started"]), 1)

    def test_flat_and_source_rules(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003, "CCCUSDT": 0.004})
        out = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"]
        info = lane.started(self.db)
        flat = next(x for x in out if info[x]["coins"] == ["BBBUSDT"])
        held = next(x for x in out if info[x]["coins"] == ["CCCUSDT"])
        lane.run_one(self.db, held, market(rate=0.0), NOW)                            # holds, but earns no funding
        self.assertEqual(lane.manage(self.db, NOW + 2 * DAY - 60, None, fids=[])["retired"], [])
        self.assertEqual(lane.manage(self.db, NOW + 2 * DAY, None, fids=[])["retired"], [flat])
        self.assertEqual(lane.retired(self.db)[flat]["rule"], "flat")
        self.assertEqual(lane.manage(self.db, NOW + 3 * DAY, None, fids=[])["retired"], [held])
        self.assertEqual(lane.retired(self.db)[held]["rule"], "source")

    def test_human_off_stops_scanner_accounts_too(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        lane.set_policy(self.db, False, "human:test", "stop all lane accounts now")
        self.assertEqual(lane.manage(self.db, NOW + 60, hi(), fids=[])["retired"], [led])
        self.assertEqual(lane.manage(self.db, NOW + 120, hi(), fids=[]).get("scanner"), None)

    def test_view_names_labels_and_trigger(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, hi(), NOW)
        with mock.patch("time.time", lambda: NOW + 60):
            v = command.paper_view(self.db, now=NOW + 60)
            b = command.balance(self.db, now=NOW + 60)
            ln = command.lane_view(self.db, now=NOW + 60)
        s = next(x for x in v["strategies"] if x["exp_id"] == led)
        self.assertEqual(s["label"], lane.SCAN_LABEL)
        self.assertEqual(s["name"], "Scannerkonto BBBUSDT")
        self.assertTrue(s["lane_info"]["scanner"])
        self.assertEqual(b["lane"]["scanner"], 1)
        self.assertIsNone(b["capital"])
        self.assertEqual(ln["active"][0]["trigger"], "forventet funding 0.300% · snit af 3 afregninger 0.080%")


class PremiumWatch(Base):
    """Amendments 12a and 12e: the premium and predicted funding every minute, observations only."""
    def setUp(self):
        super().setUp()
        scanner._PERPS.clear()
        scanner.LIVE.clear()
        self.urls = []

    def get(self, rows):
        """rows: {symbol: (premium, predicted funding)}."""
        def g(url):
            self.urls.append(url)
            if url.endswith("/fapi/v1/exchangeInfo"):
                return {"symbols": [{"symbol": s, "contractType": "PERPETUAL", "underlyingType": "COIN",
                                     "status": "TRADING", "quoteAsset": "USDT"} for s in ("AAAUSDT", "BBBUSDT")]}
            if url.endswith("/fapi/v1/premiumIndex"):
                return [{"symbol": s, "markPrice": str(100 * (1 + p)), "indexPrice": "100", "lastFundingRate": str(f)}
                        for s, (p, f) in rows.items()]
            if url.endswith("/fapi/v1/fundingInfo"):                       # 12i: settlement intervals
                return [{"symbol": s, "fundingIntervalHours": h} for s, h in getattr(self, "intervals", {}).items()]
            raise AssertionError(url)
        return g

    def post(self, url, body):
        self.urls.append(url)
        assert url == scanner.HL_INFO and body == {"type": "metaAndAssetCtxs"}, (url, body)
        return [{"universe": [{"name": "AAA"}, {"name": "kPEPE"}, {"name": "OLD", "isDelisted": True}]},
                [{"funding": "0.0002"}, {"funding": "0.01"}, {"funding": "0.01"}]]

    def test_12i_a_4_hour_coin_is_measured_per_8_hours(self):
        scanner.INTERVALS.clear()
        scanner._INTERVALS_AT.clear()
        self.addCleanup(scanner.INTERVALS.clear)
        self.addCleanup(scanner._INTERVALS_AT.clear)
        self.intervals = {"AAAUSDT": 4}
        scanner.premium_watch(self.db, self.get({"AAAUSDT": (0.0, 0.0003), "BBBUSDT": (0.0, 0.0003)}), NOW, self.post)
        rows = {r["instrument"]: r for r in self.db.q("SELECT instrument, value, payload FROM observations WHERE "
                                                      "metric='predicted_funding'")}
        self.assertEqual(set(rows), {"AAAUSDT"})                       # 0.03 % per 4 h = 0.06 % per 8 h >= 0.05 %
        self.assertAlmostEqual(rows["AAAUSDT"]["value"], 0.0006)
        p = json.loads(rows["AAAUSDT"]["payload"])
        self.assertEqual((p["raw"], p["interval_h"], p["per"]), (0.0003, 4, "8h"))
        self.assertAlmostEqual(scanner.LIVE[scanner.BN][1]["BBBUSDT"], 0.0003)   # 8-hourly: unchanged

    def test_12i_funding_info_is_read_hourly_and_a_failure_keeps_what_is_known(self):
        scanner.INTERVALS.clear()
        scanner._INTERVALS_AT.clear()
        self.addCleanup(scanner.INTERVALS.clear)
        self.addCleanup(scanner._INTERVALS_AT.clear)
        self.intervals = {"AAAUSDT": 4}
        scanner.intervals(self.get({}), NOW)
        self.intervals = {"AAAUSDT": 1}
        scanner.intervals(self.get({}), NOW + 60)                        # within the hour: not read again
        self.assertEqual(scanner.INTERVALS, {"AAAUSDT": 4})
        boom = lambda url: (_ for _ in ()).throw(OSError("down"))       # noqa: E731
        scanner.intervals(boom, NOW + 3601)
        self.assertEqual(scanner.INTERVALS, {"AAAUSDT": 4})

    def test_writes_observations_only_and_reads_the_perp_list_hourly(self):
        events = self.db.one("SELECT COUNT(*) FROM events")[0]
        out = scanner.premium_watch(self.db, self.get({"AAAUSDT": (0.012, 0.0025), "BBBUSDT": (0.001, 0.0002),
                                                       "ZZZUSDT": (0.05, 0.01)}), NOW - 60, self.post)
        # premium AAA flagged, symbols_compared, predicted funding AAA flagged; ZZZ is not a traded perp
        # + median, share, top (12e); + Hyperliquid AAA x 8 = 0.16 % flagged, the count, median and top (13)
        self.assertEqual((out["observations"], out["flagged"]), (10, 3))
        self.assertEqual(scanner.HL_LIVE[scanner.HL_INFO], (int(NOW - 60), {"AAA": 0.0016}))
        self.assertEqual(scanner.LIVE[scanner.BN], (int(NOW - 60), {"AAAUSDT": 0.0025, "BBBUSDT": 0.0002}))
        scanner.premium_watch(self.db, self.get({"AAAUSDT": (0.006, 0.0012)}), NOW - 30, self.post)
        self.assertEqual(sum(u.endswith("exchangeInfo") for u in self.urls), 1)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events")[0], events)   # no market.event, no candidate
        self.assertTrue(all(u.startswith("https://fapi.binance.com/") or u == scanner.HL_INFO for u in self.urls))
        self.assertEqual(lane.scans(self.db, NOW), [int(NOW - 30), int(NOW - 60)])
        self.assertEqual(lane.scan_candidates(self.db, NOW), ["AAAUSDT"])
        self.assertEqual(lane.live_funding("AAAUSDT", NOW), (0.0012, int(NOW - 30)))
        led = lane.manage(self.db, NOW, market(rate=0.0008), fids=[])["scanner"]["started"][0]
        self.assertEqual(lane.started(self.db)[led]["coins"], ["AAAUSDT"])
        scanner.premium_watch(self.db, self.get({}), NOW + 3600 + 1, self.post)
        self.assertEqual(sum(u.endswith("exchangeInfo") for u in self.urls), 2)   # the list again after an hour
        self.assertEqual(lane.live_funding("AAAUSDT", NOW + 3600 + 1 + lane.SCAN_LIVE_MAX_S + 1), (None, None))

    def test_its_measurements_count_as_its_output(self):
        for k in range(3):
            scanner.premium_watch(self.db, self.get({"AAAUSDT": (0.0, 0.0001)}), NOW - 60 * k, self.post)
        self.db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status, stale_after) "
                            "VALUES('premium-watch', ?, 1, 1, '', 'idle', 180)", (int(NOW),))
        a = next(x for x in command.agents(self.db, now=NOW + 1)["agents"] if x["agent"] == "premium-watch")
        self.assertEqual(a["measurements_24h"], 3)
        self.assertGreaterEqual(a["output_24h"], 3)

    def test_market_funding_is_recorded_and_shown(self):
        out = scanner.premium_watch(self.db, self.get({"AAAUSDT": (0.0, 0.0004), "BBBUSDT": (0.0, 0.0001)}), NOW - 60, self.post)
        self.assertEqual(out["flagged"], 1)                                       # Hyperliquid AAA only
        m = command.lane_view(self.db, now=NOW)["market"]
        self.assertEqual((m["median"], m["above_floor"], m["top"], m["top_symbol"]), (0.0004, 0.5, 0.0004, "AAAUSDT"))
        self.assertEqual(m["entry_min"], lane.SCAN_FUND_MIN)
        self.assertEqual((m["hl_top"], m["hl_top_symbol"]), (0.0016, "AAA"))
        self.assertEqual(m["hl_entry_min"], lane.HL_FUND_MIN)


def hl_post(rate=0.0002, fail=(), now=lambda: NOW, log=None):
    """Fake Hyperliquid /info: hourly settled funding at `rate` per hour for 48 h, 1h candles (the one in progress
    last), and a book around 100. `fail`: coins whose book fails."""
    def post(body):
        if log is not None:
            log.append(body)
        t, hour = body["type"], int(now()) // HOUR * HOUR
        if t == "fundingHistory":
            return [{"coin": body["coin"], "fundingRate": str(rate), "premium": "0", "time": (hour - k * HOUR) * 1000 + 7}
                    for k in range(48, -1, -1)]
        if t == "candleSnapshot":
            return [{"t": (hour - k * HOUR) * 1000, "o": "100", "c": "100"} for k in range(48, -1, -1)]
        if t == "l2Book":
            if body["coin"] in fail:
                raise OSError("no such coin")
            return {"levels": [[{"px": "99.99", "sz": "1000", "n": 1}], [{"px": "100.01", "sz": "1000", "n": 1}]]}
        raise AssertionError(body)
    return post


class Hyperliquid(Base):
    """Amendment 13: long Binance spot, short Hyperliquid perp, decided by Hyperliquid's funding."""
    def setUp(self):
        super().setUp()
        scanner.HL_LIVE.clear()
        self.clock = [NOW]
        self.p.append(mock.patch.object(paper_runner, "HL_POST", hl_post(now=lambda: self.clock[0])))
        self.p[-1].start()

    def scan(self, ts, fund):
        self.db.append("observations", ts=int(ts), detector="pricing_constraint/2", source="hl",
                       instrument="hyperliquid_perps", metric="hl_symbols_compared", value=100, threshold=None,
                       flagged=0, payload=None)
        for coin, v in fund.items():
            self.db.append("observations", ts=int(ts), detector="pricing_constraint/2", source="hl", instrument=coin,
                           metric="hl_predicted_funding", value=v, threshold=0.001, flagged=1, payload=None)

    def at(self, t):
        self.clock[0] = t
        g = market()
        g.now = t
        return g

    def test_obs_parsing(self):
        rows, live = scanner.hl_obs(({"universe": [{"name": "AAA"}, {"name": "kBONK"}, {"name": "@12"},
                                                    {"name": "OLD", "isDelisted": True}, {"name": "BBB"}]},
                                     [{"funding": "0.0002"}, {"funding": "1"}, {"funding": "1"}, {"funding": "1"},
                                      {"funding": "0.00001"}]), NOW)
        self.assertEqual(live, {"AAA": 0.0016, "BBB": 0.00008})
        self.assertEqual([(r["instrument"], r["metric"]) for r in rows],
                         [("AAA", "hl_predicted_funding"), ("hyperliquid_perps", "hl_symbols_compared"),
                          ("hyperliquid_perps", "hl_funding_median"), ("hyperliquid_perps", "hl_funding_top")])

    def test_starts_trades_and_books_hourly_funding_on_the_hl_leg(self):
        self.scan(NOW - 60, {"AAA": 0.002})
        led = lane.manage(self.db, NOW, self.at(NOW), fids=[])["hl"]["started"][0]
        info = lane.started(self.db)[led]
        self.assertEqual((info["source"], info["coins"], info["legs"]), ("hl", ["AAA"],
                                                                         {"perp": "HL:AAA", "spot": "AAAUSDT.SPOT"}))
        self.assertAlmostEqual(info["trigger"]["settled_avg3"], 0.0016)
        r = lane.run_one(self.db, led, self.at(NOW), NOW)
        self.assertEqual(r["signal"], {"AAA": 1.0})
        pos = PaperEngine(self.db).ledger(led)["positions"]
        self.assertAlmostEqual(pos["AAAUSDT.SPOT"], -pos["HL:AAA"])
        self.assertAlmostEqual(pos["AAAUSDT.SPOT"] * 100.0, 5_000, delta=5.0)
        lane.run_one(self.db, led, self.at(NOW + 2 * HOUR), NOW + 2 * HOUR)
        rows = self.db.q("SELECT instrument, amount FROM sim_funding WHERE exp_id=?", led)
        self.assertEqual({x["instrument"] for x in rows}, {"HL:AAA"})
        self.assertEqual(len(rows), 2)                                               # 03:00 and 04:00
        self.assertTrue(all(x["amount"] > 0 for x in rows))                         # the short receives
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])

    def test_13a_needs_ten_basis_points_on_hyperliquid(self):
        self.scan(NOW - 60, {"AAA": 0.0007, "BBB": 0.0012})                          # x8: 0.07 % and 0.12 %
        self.assertEqual(lane.hl_candidates(self.db, NOW)[0], ["BBB"])

    def test_not_persistent_or_no_book_is_skipped(self):
        self.scan(NOW - 60, {"AAA": 0.002, "BBB": 0.003})
        with mock.patch.object(paper_runner, "HL_POST", hl_post(rate=0.00001, now=lambda: NOW)):
            out = lane.manage(self.db, NOW, self.at(NOW), fids=[])["hl"]
        self.assertEqual((out["started"], sorted(out["skipped"])), ([], ["AAA", "BBB"]))
        with mock.patch.object(paper_runner, "HL_POST", hl_post(fail=("BBB",), now=lambda: NOW + HOUR)):
            out = lane.manage(self.db, NOW + HOUR, self.at(NOW + HOUR), fids=[])["hl"]
        self.assertEqual(out["skipped"], ["BBB"])
        self.assertEqual(len(out["started"]), 1)

    def test_holds_eight_hours_then_leaves_after_two_low_settled_hours(self):
        self.scan(NOW - 60, {"AAA": 0.002})
        led = lane.manage(self.db, NOW, self.at(NOW), fids=[])["hl"]["started"][0]
        lane.run_one(self.db, led, self.at(NOW), NOW)
        with mock.patch.object(paper_runner, "HL_POST", hl_post(rate=0.00001, now=lambda: self.clock[0])):
            t = NOW + HOUR                                                          # low, but before 8 h
            self.assertEqual(lane.run_one(self.db, led, self.at(t), t)["signal"], {"AAA": 1.0})
            t = NOW + 8 * HOUR
            self.assertEqual(lane.run_one(self.db, led, self.at(t), t)["signal"], {"AAA": 0.0})
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])

    def test_retired_hl_account_is_closed_by_the_runner(self):
        self.scan(NOW - 60, {"AAA": 0.002})
        led = lane.manage(self.db, NOW, self.at(NOW), fids=[])["hl"]["started"][0]
        lane.run_one(self.db, led, self.at(NOW), NOW)
        lane.retire(self.db, led, "loss", "fixture", now=NOW + 60)
        paper_runner.run(self.db, get=self.at(NOW + HOUR), now=NOW + HOUR)
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])
        self.assertFalse(Risk(self.db).fail_closed())

    def test_views(self):
        self.scan(NOW - 60, {"AAA": 0.002})
        led = lane.manage(self.db, NOW, self.at(NOW), fids=[])["hl"]["started"][0]
        lane.run_one(self.db, led, self.at(NOW), NOW)
        v = command.lane_view(self.db, now=NOW + 60)
        self.assertEqual(v["counts"]["hl"], 1)
        r = v["active"][0]
        self.assertEqual((r["name"], r["held"], r["hl"]), ("HL-konto AAA", ["AAA"], True))
        self.assertEqual(r["trigger"], "Hyperliquid-funding ×8 0.200% · snit af 24 timer ×8 0.160%")
        self.assertEqual(lane.label(lane.started(self.db)[led]), lane.HL_LABEL)

    def test_16e_only_spot_delistings_count(self):
        """Amendment 16e point 6: the Binance leg is spot, so only spot delistings count."""
        self.scan(NOW - 60, {"AAA": 0.002, "BBB": 0.003})
        news_item(self.db, "Binance Futures Will Delist AAAUSDT Perpetual Contract", NOW - 120)   # other venue's perp
        news_item(self.db, "Binance Will Delist BBB on 2026-10-28", NOW - 120)                   # the spot leg goes
        out = lane.manage(self.db, NOW, self.at(NOW), fids=[])["hl"]
        self.assertEqual(out["skipped"], ["BBB"])
        self.assertEqual([lane.started(self.db)[x]["coins"] for x in out["started"]], [["AAA"]])
        news_item(self.db, "Binance Will Delist AAA on 2026-10-29", NOW + 90)
        self.assertEqual(lane.manage(self.db, NOW + 120, None, fids=[])["retired"], out["started"])
        self.assertEqual(lane.retired(self.db)[out["started"][0]]["rule"], "delisting")


class LaneView(Base):
    def test_main_page_view_lists_active_and_stopped_accounts(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)
        self.publish([result("k2", fn="carry_floor", params={"days": 7, "q": 0.8})], name="fcarry_2")
        led2 = lane.manage(self.db, NOW + lane.START_EVERY, market(), fids=["fcarry"])["started"]
        lane.retire(self.db, led2, "edge", "fixture", now=NOW + lane.START_EVERY + 60)
        v = command.lane_view(self.db, now=NOW + 2 * HOUR)
        self.assertEqual([r["ledger"] for r in v["active"]], [led])
        self.assertEqual([r["ledger"] for r in v["recent"]], [led2])
        self.assertEqual(v["counts"], {"lane": 1, "lane_slots": lane.SLOTS, "scanner": 0,
                                       "scanner_slots": lane.SCAN_SLOTS, "hl": 0, "hl_slots": lane.HL_SLOTS})
        r = v["active"][0]
        self.assertEqual((r["status"], len(r["held"])), ("aktiv", len(COINS)))
        self.assertAlmostEqual(r["funding_minus_fees"], r["funding"] - r["fees"])
        self.assertEqual(v["recent"][0]["status"], "stoppet: edge")
        self.assertAlmostEqual(v["recent"][0]["days"], 60 / 86400)        # lifetime, not age today (2026-10-24)
        self.assertAlmostEqual(r["days"], (NOW + 2 * HOUR - lane.started(self.db)[led]["ts"]) / 86400)   # active: age
        self.assertFalse(v["evidence"])


def review_market(days=396, regime=21, start=1606780800):
    """explore0-like data for COINS from 2020-12-01 (through the review window R, 2021): ratio bars at 1 and funding
    that alternates between `regime` days high and `regime` days negative. With 21-day regimes a 7-day filter catches
    most of each high regime; with 7-day regimes it always enters late and loses."""
    bars, funding = {}, {}
    for c in COINS:
        bars[c] = [(start + i * HOUR, 1.0, 1.0) for i in range(days * 24)]
        fr = {}
        for k in range(days * 3):
            t = start + k * 8 * HOUR
            hi = (k // (3 * regime)) % 2 == 0
            fr[t] = -(0.0009 if hi else -0.0006)                                # cost convention (fcarry.py)
        funding[c] = fr
    return bars, funding


def families_load():
    from lab import families
    return families.load("fcarry")


def families_costs():
    from lab import families
    return families.load("fcarry")["costs"]


class CostGate(Base):
    """Amendment 12g: an account opens only if 3 days of predicted funding cover the walked round-trip cost."""
    def test_walk_by_hand(self):
        from lab.paper import Book
        b = Book(ts=NOW, bids=((99.0, 10), (98.0, 10)), asks=((101.0, 10), (102.0, 10)))      # mid 100
        self.assertAlmostEqual(lane.walk(b, "buy", 5), 0.01)                                # all at 101
        self.assertAlmostEqual(lane.walk(b, "buy", 20), (101 * 10 + 102 * 10) / 20 / 100 - 1)
        self.assertAlmostEqual(lane.walk(b, "sell", 20), 1 - (99 * 10 + 98 * 10) / 20 / 100)
        self.assertIsNone(lane.walk(b, "buy", 21))
        c = lane.round_trip_cost(b, b, 500)                    # 5 coins at mid 100: 1 % each walk
        self.assertAlmostEqual(c, 4 * 0.01 + 4 * (lane.COSTS.taker_fee + lane.COSTS.extra_slippage))

    def scan(self, ts, fund):
        Scanner.scan(self, ts, fund)

    def test_too_little_funding_for_the_cost_is_skipped(self):
        wide = market(rate=0.0008, spread=1.0)                 # 1 % spread on both books
        self.scan(NOW - 60, {"BBBUSDT": 0.0006})               # 3 days: 0.54 %, cost about 2.5 %
        out = lane.manage(self.db, NOW, wide, fids=[])["scanner"]
        self.assertEqual((out["started"], out["skipped"]), ([], ["BBBUSDT"]))
        p = self.db.one("SELECT payload FROM events WHERE kind='lane.skipped' ORDER BY id DESC LIMIT 1")["payload"]
        self.assertIn("do not cover the round-trip cost", p)
        self.scan(NOW + HOUR, {"BBBUSDT": 0.0006})
        self.assertEqual(len(lane.manage(self.db, NOW + HOUR + 1, hi(), fids=[])["scanner"]["started"]), 1)

    def test_a_book_too_thin_for_the_size_is_skipped(self):
        def thin(path):
            g = hi()
            if "depth" in path:
                return {"bids": [["99.99", "1"]], "asks": [["100.01", "1"]]}             # 100 USD a side
            return g(path)
        thin.now = NOW
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        out = lane.manage(self.db, NOW, thin, fids=[])["scanner"]
        self.assertEqual(out["skipped"], ["BBBUSDT"])
        self.assertIn("too thin", self.db.one("SELECT payload FROM events WHERE kind='lane.skipped'")["payload"])


class LiquidityGate(Base):
    """Amendment 25: a new lane opens only where the measured book round trip at its size is within 21i's floor;
    unknown, empty, thin, not trading or censored blocks; existing positions are never touched."""
    def book(self, spread=0.02, qty=1000.0, px=100.0):
        from lab.paper import Book
        return Book(ts=NOW, bids=((px - spread / 2, qty),), asks=((px + spread / 2, qty),))

    def curve(self, inst, metric="rt_5000", rt=0.0001, size=5000, ts=NOW - 3600, censored=False, payload=None):
        from lab import capacity
        p = payload or {"size_usd": size, "round_trip": None if censored else rt, "censored": censored}
        self.db.append("observations", ts=int(ts), detector=capacity.DETECTOR, source="t", instrument=inst,
                       metric=metric, value=None if censored else rt, threshold=None, flagged=0, payload=p)

    def legs(self, s=0.1, p=0.1, **kw):
        return {"AUSDT.SPOT": self.book(s, **kw), "AUSDT": self.book(p, **kw)}

    def test_limit_unknown_empty_crossed_and_thin(self):
        ok, d = lane.liquidity_gate(self.db, self.legs(), 5000, NOW)                 # 0.1 % a leg: 0.2 % total
        self.assertTrue(ok)
        self.assertAlmostEqual(d["round_trip"], 0.002, places=6)
        ok, d = lane.liquidity_gate(self.db, self.legs(0.3, 0.3), 5000, NOW)         # 0.6 % > 0.46 %
        self.assertFalse(ok)
        self.assertIn("bogens rundtur", d["reason"])
        self.assertFalse(lane.liquidity_gate(self.db, {"AUSDT.SPOT": None, "AUSDT": self.book()}, 5000, NOW)[0])
        from lab.paper import Book
        crossed = Book(ts=NOW, bids=((101.0, 10.0),), asks=((100.0, 10.0),))
        self.assertIn("tom eller krydset",
                      lane.liquidity_gate(self.db, {"AUSDT.SPOT": crossed, "AUSDT": self.book()}, 5000, NOW)[1]["reason"])
        empty = Book(ts=NOW, bids=(), asks=((100.0, 10.0),))
        self.assertFalse(lane.liquidity_gate(self.db, {"AUSDT.SPOT": empty, "AUSDT": self.book()}, 5000, NOW)[0])
        ok, d = lane.liquidity_gate(self.db, self.legs(qty=1.0), 5000, NOW)           # 100 USD a side
        self.assertFalse(ok)
        self.assertIn("for tynd", d["reason"])

    def test_the_capacity_curve_blocks_settling_unlisted_errors_censored_and_wider_books(self):
        for status in ("SETTLING", "NOT_LISTED"):
            dbn = DB(os.path.join(self.tmp, f"{status}.db"))
            old, self.db = self.db, dbn
            try:
                self.curve("AUSDT", metric="not_trading", payload={"status": status})
                ok, d = lane.liquidity_gate(self.db, self.legs(), 5000, NOW)
                self.assertFalse(ok)
                self.assertIn(status, d["reason"])                                   # live books alone would pass
            finally:
                self.db = old
                dbn.close()
        db2 = DB(os.path.join(self.tmp, "b.db"))
        old, self.db = self.db, db2
        try:
            self.curve("AUSDT", metric="error", payload={"error": "ValueError('empty book')"})
            self.assertIn("error", lane.liquidity_gate(self.db, self.legs(), 5000, NOW)[1]["reason"])
        finally:
            self.db = old
            db2.close()
        for name, rows in (("censored", [dict(size=5000, censored=True)]),
                           ("wider", [dict(size=5000, rt=0.004)])):
            dbx = DB(os.path.join(self.tmp, f"{name}.db"))
            old, self.db = self.db, dbx
            try:
                for kw in rows:
                    self.curve("AUSDT.SPOT", **kw)
                ok, d = lane.liquidity_gate(self.db, self.legs(), 5000, NOW)
                self.assertFalse(ok, name)
                if name == "wider":                                                   # the larger of live and curve
                    self.assertAlmostEqual(d["legs"]["AUSDT.SPOT"]["used"], 0.004)
            finally:
                self.db = old
                dbx.close()
        dbs = DB(os.path.join(self.tmp, "stale.db"))
        old, self.db = self.db, dbs
        try:
            self.curve("AUSDT", metric="not_trading", payload={"status": "SETTLING"}, ts=NOW - 25 * HOUR)
            ok, d = lane.liquidity_gate(self.db, self.legs(), 5000, NOW)              # older than 24 h: not used
            self.assertTrue(ok)
            self.assertEqual(d["legs"]["AUSDT"]["curve_status"], "absent")
        finally:
            self.db = old
            dbs.close()

    def test_new_scanner_and_family_lanes_are_gated_existing_ones_are_not(self):
        Scanner.scan(self, NOW - 60, {"BBBUSDT": 0.003})
        out = lane.manage(self.db, NOW, market(rate=0.0008, spread=0.3), fids=[])["scanner"]   # 0.3 %/leg: 0.6 %
        self.assertEqual((out["started"], out["skipped"]), ([], ["BBBUSDT"]))
        p = json.loads(self.db.one("SELECT payload FROM events WHERE kind='lane.skipped' ORDER BY id DESC")["payload"])
        self.assertIn("likviditetsgate (25): bogens rundtur", p["reason"])
        self.assertEqual(lane.classify("lane.skipped", p), "afvist af omkostninger")
        self.assertEqual(lane.classify("lane.skipped", {"reason": "likviditetsgate (25): AUSDT: bogen er for tynd"}),
                         "utilstrækkelige data")

        def thin_doge(path):                                                          # one coin's spot book too thin
            if "depth" in path and "DOGEUSDT" in path:
                return {"bids": [["99.99", "1"]], "asks": [["100.01", "1"]]}
            return base(path)
        base = market()
        thin_doge.now = NOW
        with mock.patch.object(explore, "universe", lambda fam: tuple(COINS + ["SOLUSDT"])):   # 6 coins, 5 kept
            led = self.started(thin_doge)
        info = lane.started(self.db)[led]
        self.assertNotIn("DOGEUSDT", info["coins"])
        self.assertTrue(any("likviditetsgate (25)" in d["reason"] for d in info["dropped"] if d["coin"] == "DOGEUSDT"))
        wide = market(spread=2.0)                                                     # books turn untradable later:
        wide.now = NOW + HOUR                                                         # the running lane is untouched
        out = lane.manage(self.db, NOW + HOUR, wide, fids=["fcarry"])
        self.assertIn(led, lane.active(self.db))
        self.assertNotIn(led, out.get("retired") or [])


class Symbols(unittest.TestCase):
    def test_non_ascii_symbols_are_url_encoded(self):
        seen = []
        def get(url):
            seen.append(url)
            url.encode("ascii")                          # what urllib needs; raises for a raw non-ASCII URL
            return {"bids": [["1", "1"]], "asks": [["1.1", "1"]]}
        paper_runner.fetch_book("我踏马来了USDT", NOW, get)
        paper_runner.fetch_book("我踏马来了USDT.SPOT", NOW, get)
        self.assertTrue(all("%E6%88%91" in u for u in seen))


class Execution(Base):
    """Amendment 12h: execution measured per leg, unsynchronised books refused, decomposition and classes."""
    def scan(self, ts, fund):
        Scanner.scan(self, ts, fund)

    def test_leg_stats_by_hand(self):
        from lab.paper import Book
        b = Book(ts=NOW, bids=((99.0, 10), (98.0, 10)), asks=((101.0, 10), (102.0, 10)))
        g = lane.leg_stats(b, 15, "XUSDT.SPOT", 123.0)
        self.assertAlmostEqual(g["spread"], 0.02)
        self.assertAlmostEqual(g["depth_bid_usd"], 99 * 10 + 98 * 10)
        self.assertAlmostEqual(g["depth_ask_usd"], 101 * 10 + 102 * 10)
        self.assertAlmostEqual(g["vwap_buy"], (101 * 10 + 102 * 5) / 15 / 100 - 1)
        self.assertAlmostEqual(g["vwap_sell"], 1 - (99 * 10 + 98 * 5) / 15 / 100)
        self.assertEqual((g["instrument"], g["fetched_at"]), ("XUSDT.SPOT", 123.0))

    def test_the_start_records_both_legs_and_the_basis(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, market(rate=0.0008, spot_px=100.5), fids=[])["scanner"]["started"][0]
        ex = lane.started(self.db)[led]["trigger"]["execution"]
        self.assertEqual((ex["spot"]["instrument"], ex["perp"]["instrument"]), ("BBBUSDT.SPOT", "BBBUSDT"))
        self.assertAlmostEqual(ex["basis"], 100.5 / 100 - 1)
        self.assertLess(ex["skew_s"], lane.EXEC_SKEW_MAX)
        self.assertEqual(ex["size_usd_per_leg"], 5000.0)
        self.assertGreater(ex["round_trip_cost"], 4 * (lane.COSTS.taker_fee + lane.COSTS.extra_slippage))

    def test_unsynchronised_books_are_refused_as_unknown(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        clock = iter([1000.0, 1010.0])                                   # the second book 10 s later
        with mock.patch.object(lane, "_wall", lambda: next(clock)):
            out = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]
        self.assertEqual(out["skipped"], ["BBBUSDT"])
        p = json.loads(self.db.one("SELECT payload FROM events WHERE kind='lane.skipped'")["payload"])
        self.assertIn("unsynchronised", p["reason"])
        self.assertEqual(p["trigger"]["execution"]["round_trip_cost"], "UNKNOWN")
        self.assertEqual(lane.classify("lane.skipped", p), "utilstrækkelige data")

    def test_negative_funding_never_covers_the_cost(self):
        from lab.paper import Book
        b = Book(ts=NOW, bids=((99.99, 1000),), asks=((100.01, 1000),))
        t = {}
        with self.assertRaises(ValueError) as e:
            lane._cost_gate(t, b, b, -0.0005, {"s": 1.0, "p": 1.0}, ("s", "p"))
        self.assertIn("do not cover", str(e.exception))
        self.assertEqual(lane.classify("lane.skipped", {"reason": str(e.exception)}), "afvist af omkostninger")

    def test_decomposition_sums_to_net_without_double_counting(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, market(rate=0.0008, spread=0.2), NOW)     # 0.4 % round trip: within amendment 31
        g = market(rate=0.0008, spread=0.2, px=101.0, spot_px=100.8)          # price and basis move
        g.now = NOW + 8 * HOUR
        lane.run_one(self.db, led, g, g.now)
        d = lane.decomposition(self.db, led)
        self.assertAlmostEqual(d["funding"] + d["fees"] + d["spread_slippage"] + d["price_basis"], d["net"], places=9)
        self.assertLess(d["spread_slippage"], 0)
        self.assertLess(d["fees"], 0)
        self.assertGreater(d["funding"], 0)
        self.assertEqual(d["fills_without_mid"], 0)
        self.assertAlmostEqual(d["book"] + d["allowance"], d["spread_slippage"], places=9)    # 2026-10-24 split
        notional = sum(f["px"] * f["qty"] for f in self.db.q("SELECT px, qty FROM sim_fills WHERE exp_id=?", led))
        self.assertAlmostEqual(-d["allowance"] / notional, lane.COSTS.extra_slippage, delta=1e-6)
        self.assertLess(d["book"], 0)
        self.assertAlmostEqual(d["price_basis_gap"], 0.0, places=6)           # 21t: residual = mid-based price P&L
        self.assertEqual((d["fills_better_than_mid"], d["fills_after_mark"]), (0, 0))
        mark_ts = self.db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", led)[0]       # a fill after the mark
        self.db.append("sim_orders", order_id="late", exp_id=led, ts=mark_ts + 60, instrument="BBBUSDT", side="buy",
                       qty=1.0, limit_px=None, style="taker", reduce_only=0, signal_ref="t", cost_model={})
        self.db.append("sim_fills", fill_id="late|0", order_id="late", exp_id=led, ts=mark_ts + 60,
                       instrument="BBBUSDT", side="buy", px=101.5, qty=1.0, fee=0.05, slippage=None, liquidity="taker",
                       mid=101.0, book_ts=mark_ts + 59.5)
        d2 = lane.decomposition(self.db, led)
        self.assertEqual(d2["fills_after_mark"], 1)
        self.assertAlmostEqual(d2["price_basis_gap"], 0.0, places=6)          # LINUX_DRIFT 22:27: cut at the mark
        self.assertAlmostEqual(d2["fees"], d["fees"], places=9)                 # the late fill waits for the next mark

    def test_classes_and_view(self):
        self.assertEqual(lane.classify("lane.started", {}), "afventer fremadtest")
        self.assertEqual(lane.classify("lane.started", {}, ready=True), "klar til formel, menneskegodkendt validering")
        self.assertEqual(lane.classify("lane.skipped", {"reason": "a book is too thin for the account's size (12g)"}),
                         "utilstrækkelige data")
        self.scan(NOW - 60, {"BBBUSDT": 0.003, "CCCUSDT": 0.0006})
        lane.manage(self.db, NOW, market(rate=0.0008, spread=0.1), fids=[])   # 0.1 %/leg: liquid enough for 25
        v = command.lane_view(self.db, now=NOW + 60)
        classes = {p["coin"]: p["class"] for p in v["probes"]}
        self.assertEqual(classes["BBBUSDT"], "afventer fremadtest")
        self.assertEqual(classes["CCCUSDT"], "afvist af omkostninger")
        self.assertIn("decomposition", v["active"][0])


class Review(Base):
    """Amendment 11c: candidates are reviewed adversarially before they may trade."""
    def test_unreviewed_or_failed_candidates_never_start(self):
        self.publish([result("k1", sharpe=5)], reviewed=False)
        self.assertIsNone(lane.manage(self.db, NOW, market(), fids=["fcarry"])["started"])
        self.db.event("research.lane_review", "system:adversarial-1", None, {"key": "k1", "ok": False, "method": lane.REVIEW_METHOD})
        self.assertIsNone(lane.manage(self.db, NOW + HOUR, market(), fids=["fcarry"])["started"])
        self.db.event("research.lane_review", "system:adversarial-1", None, {"key": "k1", "ok": True, "method": lane.REVIEW_METHOD})
        self.assertEqual(lane.manage(self.db, NOW + 2 * HOUR, market(), fids=["fcarry"])["started"],
                         lane.ledger_id("k1"))

    def test_an_old_method_job_and_artifact_are_not_reused(self):
        import hashlib
        self.publish([result("k1", sharpe=5)], reviewed=False)
        old = hashlib.sha256(b"k1").hexdigest()[:10]                          # the 11d naming: the key alone
        jobs_mod = __import__("lab.jobs", fromlist=["enqueue"])
        jobs_mod.init(self.db)
        jobs_mod.enqueue(self.db, f"lane_review|{old}", "lane_review", None, {"key": "k1"}, actor="system:t", now=NOW)
        self.db.con.execute("UPDATE jobs SET status='done' WHERE job_id=?", (f"lane_review|{old}",))
        self.assertEqual(lane.enqueue_reviews(self.db, NOW, fids=["fcarry"]), 1)
        self.assertNotEqual(lane.review_id("k1"), old)

    def test_an_old_method_review_does_not_count(self):
        self.publish([result("k1", sharpe=5)], reviewed=False)
        self.db.event("research.lane_review", "system:adversarial-1", None, {"key": "k1", "ok": True})   # 11c
        out = lane.manage(self.db, NOW, market(), fids=["fcarry"])
        self.assertIsNone(out["started"])
        self.assertEqual(out["reviews_queued"], 1)                                    # reviewed again (11i: by manage)
        self.assertEqual(lane.enqueue_reviews(self.db, NOW, fids=["fcarry"]), 0)      # already queued, not twice

    def test_the_market_shift_placebo_separates_timing_from_noise(self):
        import random
        from lab.engine import adversarial
        from lab.families import fcarry
        costs = lane._stressed(families_costs())
        bars, funding = review_market()
        pos = fcarry.carry_filter(bars, funding, {"lookback_days": 7, "enter_apr": 0.3}, None)
        self.assertLess(adversarial.placebo_circular(bars, pos, funding, costs, n=20)["p"], 0.10)       # regimes
        flat = {c: {t: -0.0003 for t in f} for c, f in funding.items()}
        pos = fcarry.carry_filter(bars, flat, {"lookback_days": 7, "enter_apr": 0.3}, None)
        self.assertGreaterEqual(adversarial.placebo_circular(bars, pos, flat, costs, n=20)["p"], 0.10)  # no timing
        bars, funding = review_market(days=180)
        low = 0
        for seed in range(8):                                                   # noise: p is not stuck at zero
            rng = random.Random(100 + seed)
            noise = {c: {t: -rng.uniform(-0.0004, 0.001) for t in f} for c, f in funding.items()}
            pos = fcarry.carry_filter(bars, noise, {"lookback_days": 3, "enter_apr": 0.3}, None)
            low += adversarial.placebo_circular(bars, pos, noise, costs, n=20, seed=seed)["p"] < 0.10
        self.assertLessEqual(low, 2)

    def test_the_returns_placebo_ignores_trends_and_separates_timing_from_noise(self):
        import random
        from lab.engine import adversarial
        from lab.families import fcarry
        costs = lane._stressed(families_costs())
        bars, funding = review_market()
        trend = {c: [(t, math.exp(i / 2000), math.exp((i + 1) / 2000)) for i, (t, _, _) in enumerate(b)]
                 for c, b in bars.items()}                                     # a steady trend, no timing
        hold = {c: [1.0] * len(b) for c, b in trend.items()}
        zero = {c: {} for c in trend}
        self.assertLess(adversarial.placebo_circular(trend, hold, zero, costs, n=20)["p"], 0.10)   # 11d: false find
        self.assertGreaterEqual(adversarial.placebo_returns(trend, hold, zero, costs, n=20)["p"], 0.10)
        pos = fcarry.carry_filter(bars, funding, {"lookback_days": 7, "enter_apr": 0.3}, None)
        self.assertLess(adversarial.placebo_returns(bars, pos, funding, costs, n=20)["p"], 0.10)    # regimes
        low = 0
        for seed in range(8):                                                   # noise: p is not stuck at zero
            rng = random.Random(100 + seed)
            noise = {c: {t: -rng.uniform(-0.0004, 0.001) for t in f} for c, f in funding.items()}
            pos = fcarry.carry_filter(bars, noise, {"lookback_days": 3, "enter_apr": 0.3}, None)
            low += adversarial.placebo_returns(bars, pos, noise, costs, n=20, seed=seed)["p"] < 0.10
        self.assertLessEqual(low, 2)

    def test_selection_reads_2020_and_review_reads_2021_only(self):
        bars, funding = review_market(days=670, start=1583020800)              # 2020-03-01..2021-12-30
        cut = explore.SELECT[1]
        quiet = {c: {t: (v if t < cut else 0.0) for t, v in f.items()} for c, f in funding.items()}   # edge only in 2020
        r = result(params={"lookback_days": 7, "enter_apr": 0.3})
        fam = families_load()
        sel = explore.evaluate("fcarry", fam, "carry_filter", r["params"], bars, quiet)
        self.assertTrue(sel["candidate"], sel["checks"])                       # chosen on 2020
        self.assertLess(sel["days"], 310)                                      # figures from S only
        rev = lane.review(r, bars, quiet)
        self.assertFalse(rev["ok"])                                            # 2021 has no edge: the review fails
        self.assertTrue(rev["checks"]["strict look-ahead exact"])
        late = {c: {t: (v if t >= cut else 0.0) for t, v in f.items()} for c, f in funding.items()}   # edge only in 2021
        self.assertFalse(explore.evaluate("fcarry", fam, "carry_filter", r["params"], bars, late)["candidate"])

    def test_reviews_wait_while_every_lane_slot_is_taken(self):
        self.publish([result(f"k{i}", sharpe=10 - i * 0.5) for i in range(9)], reviewed=False)
        with mock.patch.object(lane, "SLOTS", 0):                             # 0 active >= 0 slots: all taken
            self.assertEqual(lane.enqueue_reviews(self.db, NOW, fids=["fcarry"]), 0)
        self.assertEqual(lane.enqueue_reviews(self.db, NOW, fids=["fcarry"]), lane.REVIEW_QUEUE_MAX)   # a free slot

    def test_reviews_skip_a_function_at_its_two_account_cap(self):
        """Amendment 11g."""
        for i in range(lane.PER_FUNCTION):
            self.db.event("lane.started", lane.ACTOR, f"LANE_cap{i}", {"key": f"cap{i}", "family": "fcarry",
                                                                        "function": "carry_filter", "t": int(NOW)})
        self.publish([result(f"f{i}", sharpe=10 - i * 0.1) for i in range(4)]
                     + [result(f"g{i}", fn="carry_floor", params={"days": 7, "q": 0.5 + i / 100}, sharpe=5 - i * 0.1)
                        for i in range(2)], reviewed=False)
        self.assertEqual(lane.enqueue_reviews(self.db, NOW, fids=["fcarry"]), 2)
        ids = {r[0] for r in self.db.q("SELECT job_id FROM jobs WHERE kind='lane_review'")}
        self.assertEqual(ids, {f"lane_review|{lane.review_id(f'g{i}')}" for i in range(2)})
        lane.retire(self.db, "LANE_cap0", "flat", "fixture", now=NOW + 60)            # room again: its best first
        self.assertEqual(lane.enqueue_reviews(self.db, NOW + 120, fids=["fcarry"]), 4)

    def test_11i_a_review_is_ordered_only_for_a_candidate_that_holds_something_now(self):
        """Amendment 11i: the start pass checks 11b on the hourly data first; a candidate holding nothing gets 11b's
        skip and 24 h retry instead of a review; at most the free slots wait for a review."""
        self.publish([result(f"k{i}", sharpe=10 - i * 0.5) for i in range(4)], reviewed=False)
        held = {"k1", "k3"}
        with mock.patch.object(lane, "_would_hold", lambda r, coins, get, now, skip_unreadable=False:
                               coins if r["key"] in held else []):
            out = lane.manage(self.db, NOW, market(), fids=["fcarry"])
        self.assertEqual(out["reviews_queued"], 2)
        self.assertIsNone(out["started"])                                            # no start without a review
        ids = {r[0] for r in self.db.q("SELECT job_id FROM jobs WHERE kind='lane_review'")}
        self.assertEqual(ids, {f"lane_review|{lane.review_id(k)}" for k in held})
        skipped = {json.loads(p)["key"]: json.loads(p) for (p,) in self.db.q(
            "SELECT payload FROM events WHERE kind='lane.skipped'")}
        self.assertEqual(set(skipped), {"k0", "k2"})
        self.assertTrue(all(p["retry"] and p["reason"] == "would hold nothing now (11b)" and p["books_read"] is False
                            and p["reviewed"] is False for p in skipped.values()))
        self.assertEqual(lane.enqueue_reviews(self.db, NOW + 60, fids=["fcarry"], holds=lambda r: True), 0)  # tried
        with mock.patch.object(lane, "SLOTS", 1):                                  # one free slot: one review at most
            self.db.con.execute("DELETE FROM jobs WHERE kind='lane_review'")
            self.assertEqual(lane.enqueue_reviews(self.db, NOW + 60, fids=["fcarry"], cap=1,
                                                  holds=lambda r: True), 1)

    def test_reviews_are_queued_best_first_at_most_six(self):
        self.publish([result(f"k{i}", sharpe=10 - i * 0.5) for i in range(9)], reviewed=False)
        self.assertEqual(lane.enqueue_reviews(self.db, NOW, fids=["fcarry"]), lane.REVIEW_QUEUE_MAX)
        self.assertEqual(lane.enqueue_reviews(self.db, NOW + 60, fids=["fcarry"]), 0)
        ids = {r[0] for r in self.db.q("SELECT job_id FROM jobs WHERE kind='lane_review'")}
        self.assertEqual(ids, {f"lane_review|{lane.review_id(f'k{i}')}" for i in range(6)})

    def test_a_rule_that_catches_the_regime_passes_and_one_that_is_always_late_fails(self):
        r = result(params={"lookback_days": 7, "enter_apr": 0.3})
        good = lane.review(r, *review_market())
        self.assertTrue(good["ok"], good["checks"])
        self.assertLess(good["placebo"]["p"], 0.10)
        bad = lane.review(r, *review_market(regime=7))
        self.assertFalse(bad["ok"])
        self.assertFalse(bad["checks"]["24-bar delay net Sharpe >= 1.0 at 2x costs"], bad["delayed_net_sharpe"])
        self.assertTrue(bad["checks"]["look-ahead truncation exact"] and bad["checks"]["poison exact"])

    def test_the_job_writes_artifact_and_event_and_decides_only_the_lane(self):
        self.publish([result("k1", params={"lookback_days": 7, "enter_apr": 0.3})], reviewed=False)
        bars, funding = review_market()
        out = lane.step_review(self.db, {"payload": {"key": "k1"}}, "adversarial-1",
                               load=lambda fam: (bars, funding, [], {"files": 0}))
        self.assertTrue(out["ok"])
        self.assertTrue(lane.reviews(self.db)["k1"]["ok"])
        self.assertTrue(os.path.exists(os.path.join(pipeline.ARTIFACTS, lane.REVIEW_DIR, f"{lane.review_id('k1')}.json")))
        for t in ("results", "trials", "transitions", "alpha_ledger"):
            if self.db.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", t):
                self.assertEqual(self.db.one(f"SELECT COUNT(*) FROM {t}")[0], 0, t)


class Report(Base):
    """Amendment 12d: the daily account report decides nothing."""
    def test_queued_only_after_a_day_with_an_account(self):
        jobs.init(self.db)
        self.assertEqual(lane.enqueue_report(self.db, NOW + DAY), 0)
        self.started()
        self.assertEqual(lane.enqueue_report(self.db, NOW + DAY), 1)
        j = jobs.get(self.db, f"lane_report|{explore._day(NOW)}")
        self.assertEqual(j["kind"], "lane_report")
        self.assertEqual(j["next_run"], explore._day_start(explore._day(NOW)) + DAY + lane.REPORT_DELAY_S)

    def test_rows_and_pilot_paper_criteria(self):
        led = self.started()
        lane.run_one(self.db, led, market(), NOW)
        g = market()
        g.now = NOW + 4 * DAY
        lane.run_one(self.db, led, g, NOW + 4 * DAY)                         # funding pays the fees
        day0 = int(NOW) // DAY * DAY
        self.mark(led, day0 + 4 * DAY + 23 * HOUR, 10_050.0)
        day = explore._day(day0 + 4 * DAY)
        r = lane.report(self.db, day)
        row = r["accounts"][0]
        self.assertEqual((row["ledger"], row["source"], row["status"]), (led, "lane", "aktiv"))
        self.assertGreater(row["funding_minus_fees"], 0)
        self.assertTrue(row["pilot_paper_criteria_met"], row["pilot_paper_criteria"])
        self.assertEqual(r["met"], [led])
        early = lane.report(self.db, explore._day(day0 + DAY))["accounts"][0]   # day 1: too few days, fees unpaid
        self.assertFalse(early["pilot_paper_criteria_met"])
        lane.retire(self.db, led, "edge", "fixture", now=day0 + 5 * DAY + HOUR)
        late = lane.report(self.db, explore._day(day0 + 5 * DAY))["accounts"][0]
        self.assertEqual(late["status"], "stoppet: edge")
        self.assertFalse(late["pilot_paper_criteria_met"])

    def test_step_waits_for_the_day_then_writes_artifact_and_event(self):
        self.started()
        day = explore._day(NOW)
        job = {"payload": {"day": day}}
        with mock.patch("time.time", lambda: NOW + 60):
            with self.assertRaises(pipeline.Deferred):
                lane.step_report(self.db, job, "report-1")
        with mock.patch("time.time", lambda: explore._day_start(day) + DAY + lane.REPORT_DELAY_S + 1):
            out = lane.step_report(self.db, job, "report-1")
        self.assertEqual(out["accounts"], 1)
        ev = self.db.one("SELECT payload FROM events WHERE kind='research.lane_report'")
        self.assertIn('"decisional": false', ev["payload"].replace('"decisional":false', '"decisional": false'))
        self.assertTrue(os.path.exists(os.path.join(pipeline.ARTIFACTS, lane.REPORT_DIR, f"{day}.json")))



class PerEightHours(unittest.TestCase):
    """12i: Binance settlements are compared per 8 hours, whatever the coin's interval."""
    H = 3600

    def test_per8h_scales_by_the_interval(self):
        t0 = 1_790_000_000 // (8 * self.H) * (8 * self.H)
        four = {t0 + k * 4 * self.H: 0.00005 for k in range(4)}
        self.assertTrue(all(abs(v - 0.0001) < 1e-15 for v in lane.per8h(four).values()))
        eight = {t0 + k * 8 * self.H: 0.0001 for k in range(3)}
        self.assertEqual(set(lane.per8h(eight).values()), {0.0001})
        mixed = {t0: 0.0001, t0 + 8 * self.H: 0.0001, t0 + 9 * self.H: 0.0001}  # switched to 1 h
        self.assertAlmostEqual(lane.per8h(mixed)[t0 + 9 * self.H], 0.0008)
        self.assertEqual(lane.per8h({t0: 0.0002}), {t0: 0.0002})              # a single settlement: 8-hourly
        self.assertEqual(lane.per8h({}), {})

    def test_the_floor_rate_on_a_4_hour_coin_is_not_below_the_floor(self):
        t0 = 1_790_000_000 // (8 * self.H) * (8 * self.H)
        four = {t0 + k * 4 * self.H: 0.00005 for k in range(4)}             # 0.005 % per 4 h = 0.01 % per 8 h
        self.assertTrue(lane._two_settled_low(four))                        # the old raw comparison exited here
        self.assertFalse(lane._two_settled_low(lane.per8h(four)))           # 12i: held at the floor
        low = {t0 + k * 4 * self.H: 0.00002 for k in range(4)}
        self.assertTrue(lane._two_settled_low(lane.per8h(low)))



class SpotPairs(Base):
    """Amendment 19: scanner and HL accounts skip coins without a Binance spot pair before spending a probe."""
    def setUp(self):
        super().setUp()
        scanner.LIVE.clear()
        scanner.HL_LIVE.clear()

    def scan(self, ts, fund):
        Scanner.scan(self, ts, fund)

    def with_list(self, pairs, log=None, fail=False):
        base = hi()

        def get(path):
            if "/api/v3/exchangeInfo" in path:
                if log is not None:
                    log.append(path)
                if fail:
                    raise OSError("timed out")
                return {"symbols": [{"symbol": s, "status": "TRADING"} for s in pairs]
                        + [{"symbol": "HALTUSDT", "status": "BREAK"}]}
            return base(path)
        return get

    def test_coins_without_spot_do_not_take_the_probes(self):
        self.scan(NOW - 60, {f"C{i:02d}USDT": 0.003 - i / 10000 for i in range(6)})
        log = []
        get = self.with_list(["C03USDT", "C04USDT", "C05USDT", "BTCUSDT"], log)
        out = lane.manage(self.db, NOW, get, fids=[])["scanner"]
        self.assertEqual(out["skipped"], ["C00USDT", "C01USDT", "C02USDT"])
        info = lane.started(self.db)
        self.assertEqual(sorted(info[x]["coins"][0] for x in out["started"]), ["C03USDT", "C04USDT", "C05USDT"])
        skip = [p for _, _, _, _, p in lane._events(self.db, "lane.skipped")]
        self.assertEqual({p["reason"] for p in skip}, {lane.NO_SPOT})
        self.assertEqual(log, ["https://data-api.binance.vision/api/v3/exchangeInfo?symbolStatus=TRADING"])
        lane.manage(self.db, NOW + 600, get, fids=[])
        self.assertEqual(len(log), 1)                                           # at most once an hour
        lane.manage(self.db, NOW + HOUR + 600, get, fids=[])
        self.assertEqual(len(log), 2)

    def test_without_a_list_nothing_is_skipped_and_a_failed_read_keeps_the_last(self):
        self.scan(NOW - 60, {"AAAUSDT": 0.003, "BBBUSDT": 0.002})
        out = lane.manage(self.db, NOW, self.with_list([], fail=True), fids=[])["scanner"]
        self.assertEqual(len(out["started"]), 2)                                # as before amendment 19
        self.assertIsNone(lane.spot_pairs(None, NOW))
        lane._SPOT_LIST.clear()
        self.assertEqual(lane.spot_pairs(self.with_list(["AAAUSDT"]), NOW), {"AAAUSDT"})   # BREAK is not trading
        self.assertEqual(lane.spot_pairs(self.with_list([], fail=True), NOW + 2 * HOUR), {"AAAUSDT"})

    def test_hl_checks_the_spot_leg(self):
        scanner.HL_LIVE.clear()
        self.db.append("observations", ts=int(NOW - 60), detector="pricing_constraint/2", source="hl",
                       instrument="hl", metric="hl_symbols_compared", value=10, threshold=None, flagged=0, payload=None)
        for c, v in (("XMR", 0.004), ("AAA", 0.003)):                          # the highest has no spot pair
            self.db.append("observations", ts=int(NOW - 60), detector="pricing_constraint/2", source="hl",
                           instrument=c, metric="hl_predicted_funding", value=v, threshold=0.001, flagged=1,
                           payload=None)
        with mock.patch.object(paper_runner, "hl_hourly", side_effect=OSError("probe spent")) as probe:
            out = lane.manage_hl(self.db, NOW, self.with_list(["AAAUSDT"]))
        self.assertEqual(out["skipped"], ["XMR", "AAA"])
        self.assertEqual(probe.call_count, 1)                                   # only AAA was probed
        reasons = {p["coin"]: p["reason"] for _, _, _, _, p in lane._events(self.db, "lane.skipped")}
        self.assertEqual(reasons, {"XMR": lane.NO_SPOT, "AAA": "OSError('probe spent')"})


if __name__ == "__main__":
    unittest.main()


def news_item(db, title, usable_from, published=None, category="delisting"):
    """One stored announcement as news-watch writes it (amendment 16)."""
    p = {"category": category, "title": title, "usable_from": usable_from,
         "published_ts": usable_from - 600 if published is None else published, "source": "binance",
         "key": f"binance:{title}"}
    db.append("observations", ts=int(usable_from), detector="news/1", source="binance-cms", instrument=p["key"],
              metric="news_item", value=p["published_ts"], threshold=None, flagged=0, payload=p)


class Delisting(Base):
    """Amendment 16e: Binance delisting announcements keep scanner and HL accounts away and stop open ones."""
    def setUp(self):
        super().setUp()
        scanner.LIVE.clear()
        scanner.HL_LIVE.clear()

    def news(self, title, usable_from, published=None, category="delisting"):
        news_item(self.db, title, usable_from, published, category)

    def scan(self, ts, fund):
        Scanner.scan(self, ts, fund)

    def test_coin_rule(self):
        cases = {"Binance Will Delist EPIC, QUICK on 2026-10-28": ["EPIC", "QUICK"],
                 "Binance Futures Will Delist PTBUSDT and MITOUSDT USDⓈ-M Perpetual Contracts (2026-10-23)":
                     ["PTB", "MITO"],
                 "Binance Futures Will Delist USDⓈ-Margined IPUSDT and IPUSDC Perpetual Contracts (2026-06-28)": ["IP"],
                 "Binance Will Delist COS, D, HIGH, MBOX on 2026-06-19": ["COS", "D", "HIGH", "MBOX"],
                 "Binance Futures Will Delist Multiple Perpetual Contracts (2026-04-08 & 2026-04-09)": []}
        for title, coins in cases.items():
            self.assertEqual(lane.delist_coins(title), coins, title)

    def test_which_announcements_and_when(self):
        self.news("Binance Will Delist AAA on 2026-10-28", NOW - 60)
        self.news("Binance Futures Will Delist BBBUSDT Perpetual Contract", NOW - 60)
        self.news("Binance Margin Will Delist CCC on 2026-10-28", NOW - 60)                 # not the coin itself
        self.news("Binance Will Delist DDD on 2026-10-29", NOW + 60)                          # not usable yet
        self.news("Binance Will Delist EEE on 2026-08-01", NOW - 60, published=NOW - 31 * DAY)   # first fetch, old
        self.news("Binance Will Delist FFF on 2026-10-30", NOW - 60, category="binance_news")
        self.assertEqual(sorted(lane.delistings(self.db, NOW)), ["AAA", "BBB"])
        self.assertEqual(sorted(lane.delistings(self.db, NOW, spot_only=True)), ["AAA"])
        self.assertEqual(lane.delistings(self.db, NOW + 31 * DAY), {})

    def test_scanner_skips_before_spending_a_probe(self):
        self.news("Binance Futures Will Delist C00USDT and C01USDT USDⓈ-M Perpetual Contracts (2026-10-23)", NOW - 60)
        self.scan(NOW - 60, {f"C{i:02d}USDT": 0.002 - i / 10000 for i in range(5)})
        out = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]
        self.assertEqual(out["skipped"], ["C00USDT", "C01USDT"])
        info = lane.started(self.db)
        self.assertEqual(sorted(info[x]["coins"][0] for x in out["started"]), ["C02USDT", "C03USDT", "C04USDT"])
        skip = [p for _, _, _, _, p in lane._events(self.db, "lane.skipped")]
        self.assertTrue(all(p["reason"].startswith("afnotering annonceret (16e): Binance Futures") for p in skip))

    def test_open_scanner_account_stops(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.003})
        led = lane.manage(self.db, NOW, hi(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, hi(), NOW)
        self.assertEqual(lane.manage(self.db, NOW + 60, None, fids=[])["retired"], [])
        self.news("Binance Futures Will Delist BBBUSDT Perpetual Contract", NOW + 90)
        self.assertEqual(lane.manage(self.db, NOW + 120, None, fids=[])["retired"], [led])
        self.assertEqual(lane.retired(self.db)[led]["rule"], "delisting")
