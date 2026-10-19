"""research/PROTOCOL_V3.md amendment 11: lane accounts trade the exploration lane's candidates on paper and retire by
fixed rules. Simulated only; never evidence; nothing formal is written."""
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
from lab import watch  # noqa: E402
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
                    for i in range(1000)]
        if "fundingRate" in path:
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
            "checks": {"a": cand, "b": True, "c": True}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lablane")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch.object(explore, "eligible", lambda db: ["fcarry"]),
                  mock.patch.object(explore, "universe", lambda fam: tuple(COINS))]
        for p in self.p:
            p.start()
        lane._CANDIDATES.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def publish(self, results, name="fcarry_1", record=True):
        art = pipeline.save_artifact(os.path.join(explore.DIR, "2026-10-19"), name,
                                     {"label": explore.LABEL, "family": "fcarry", "results": results})
        if record:
            self.db.event("research.explore", "system:backtest-1", None,
                          {"family": "fcarry", "variants": [r["key"] for r in results], "decisional": False,
                           "artifact_sha256": art["sha256"]})
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
    def test_starts_one_per_hour_one_per_function_at_most_three(self):
        self.publish([result("a1", sharpe=5), result("a2", sharpe=4), result("b1", fn="carry_floor", sharpe=3,
                                                                              params={"days": 7, "q": 0.8}),
                      result("c1", fn="carry_hysteresis", sharpe=2, params={"lookback_days": 7, "exit_apr": 0.0}),
                      result("d1", fn="carry_filter_weekly", sharpe=1.5)])
        get = market()
        first = lane.manage(self.db, NOW, get, fids=["fcarry"])["started"]
        self.assertEqual(first, lane.ledger_id("a1"))
        self.assertIsNone(lane.manage(self.db, NOW + 60, get, fids=["fcarry"])["started"])     # one per hour
        second = lane.manage(self.db, NOW + HOUR, get, fids=["fcarry"])["started"]
        self.assertEqual(second, lane.ledger_id("b1"))                  # a2 has the same function as a1
        lane.manage(self.db, NOW + 2 * HOUR, get, fids=["fcarry"])
        self.assertEqual(len(lane.active(self.db)), 3)
        self.assertIsNone(lane.manage(self.db, NOW + 3 * HOUR, get, fids=["fcarry"])["started"])   # three slots

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

    def test_edge_missing_after_seven_days(self):
        led = self.started(sharpe=10.0)                   # sd 0.1 %/day on capital
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
        lane.run_one(self.db, led, market(rate=0.0), NOW)          # never on: no position, no funding
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


class Scanner(Base):
    """Amendment 12: scanner accounts."""
    def scan(self, ts, prems):
        self.db.append("observations", ts=int(ts), detector="pricing_constraint/2", source="premiumIndex",
                       instrument="binance_perps", metric="symbols_compared", value=100, threshold=None, flagged=0,
                       payload=None)
        for sym, v in prems.items():
            self.db.append("observations", ts=int(ts), detector="pricing_constraint/2", source="premiumIndex",
                           instrument=sym, metric="perp_premium", value=v, threshold=0.005, flagged=1, payload=None)

    def test_entry_rule(self):
        self.scan(NOW - 2 * HOUR, {"AAAUSDT": 0.006, "CCCUSDT": 0.006, "DDDUSDT": -0.02})
        self.scan(NOW - HOUR, {"AAAUSDT": 0.007, "BBBUSDT": 0.012, "EEEUSDT": 0.006, "DDDUSDT": -0.03})
        self.assertEqual(lane.scan_candidates(self.db, NOW), ["BBBUSDT", "AAAUSDT"])   # largest first; no negative

    def test_stale_scans_open_nothing_and_hold(self):
        self.scan(NOW - 4 * HOUR, {"BBBUSDT": 0.02})
        self.assertEqual(lane.scan_candidates(self.db, NOW), [])
        self.assertEqual(lane.scan_signal(self.db, "BBBUSDT", True, NOW), 1.0)
        self.assertEqual(lane.scan_signal(self.db, "BBBUSDT", False, NOW), 0.0)

    def test_starts_at_once_up_to_five_independent_of_lane_slots(self):
        self.scan(NOW - 60, {f"C{i}USDT": 0.01 + i / 1000 for i in range(7)})
        out = lane.manage(self.db, NOW, market(), fids=[])
        self.assertEqual(len(out["scanner"]["started"]), lane.PROBES)                # probes per pass
        out = lane.manage(self.db, NOW + 60, market(), fids=[])
        self.assertEqual(len(out["scanner"]["started"]), 2)                          # five in all
        info = lane.started(self.db)
        self.assertEqual(len(info), 5)
        self.assertTrue(all(lane.is_scanner(i) and len(i["coins"]) == 1 for i in info.values()))
        self.assertEqual(sorted(i["coins"][0] for i in info.values()), [f"C{i}USDT" for i in range(2, 7)])
        self.publish([result()])                                                     # the lane still starts its own
        self.assertIsNotNone(lane.manage(self.db, NOW + 120, market(), fids=["fcarry"])["started"])

    def test_trades_both_legs_and_closes_when_the_premium_is_gone(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.015})
        led = lane.manage(self.db, NOW, market(), fids=[])["scanner"]["started"][0]
        r = lane.run_one(self.db, led, market(), NOW)
        self.assertEqual(r["signal"], {"BBBUSDT": 1.0})
        pos = PaperEngine(self.db).ledger(led)["positions"]
        self.assertAlmostEqual(pos["BBBUSDT.SPOT"], -pos["BBBUSDT"])
        self.assertAlmostEqual(pos["BBBUSDT.SPOT"] * 100.0, 5_000, delta=2.0)       # half the account per leg
        self.scan(NOW + HOUR - 60, {})                                               # not flagged in this scan
        g = market()
        g.now = NOW + HOUR
        self.assertEqual(lane.run_one(self.db, led, g, NOW + HOUR)["signal"], {"BBBUSDT": 1.0})   # one scan gone
        self.scan(NOW + 2 * HOUR - 60, {})
        g.now = NOW + 2 * HOUR
        self.assertEqual(lane.run_one(self.db, led, g, NOW + 2 * HOUR)["signal"], {"BBBUSDT": 0.0})
        self.assertEqual(PaperEngine(self.db).ledger(led)["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile(led)["ok"])

    def test_retire_rules_and_cooldown(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.015})
        led = lane.manage(self.db, NOW, market(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, market(), NOW)
        self.mark(led, NOW + 30, 9_600.0)                                            # -4 %: below the 5 % stop
        self.assertEqual(lane.manage(self.db, NOW + 60, None, fids=[])["retired"], [])
        self.mark(led, NOW + 90, 9_450.0)
        self.assertEqual(lane.manage(self.db, NOW + 120, None, fids=[])["retired"], [led])
        self.assertEqual(lane.retired(self.db)[led]["rule"], "loss")
        self.scan(NOW + 180, {"BBBUSDT": 0.015})
        self.assertEqual(lane.manage(self.db, NOW + 240, market(), fids=[])["scanner"]["started"], [])   # cooldown
        out = lane.manage(self.db, NOW + 240 + lane.SCAN_COOLDOWN_S, market(), fids=[])
        self.assertEqual(out["scanner"]["started"], [])                              # the scan is stale by then
        self.scan(NOW + lane.SCAN_COOLDOWN_S + 200, {"BBBUSDT": 0.015})
        out = lane.manage(self.db, NOW + 240 + lane.SCAN_COOLDOWN_S, market(), fids=[])
        self.assertEqual(len(out["scanner"]["started"]), 1)

    def test_flat_and_source_rules(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.015, "CCCUSDT": 0.02})
        out = lane.manage(self.db, NOW, market(), fids=[])["scanner"]["started"]
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
        self.scan(NOW - 60, {"BBBUSDT": 0.015})
        led = lane.manage(self.db, NOW, market(), fids=[])["scanner"]["started"][0]
        lane.set_policy(self.db, False, "human:test", "stop all lane accounts now")
        self.assertEqual(lane.manage(self.db, NOW + 60, market(), fids=[])["retired"], [led])
        self.assertEqual(lane.manage(self.db, NOW + 120, market(), fids=[]).get("scanner"), None)

    def test_view_names_and_labels(self):
        self.scan(NOW - 60, {"BBBUSDT": 0.015})
        led = lane.manage(self.db, NOW, market(), fids=[])["scanner"]["started"][0]
        lane.run_one(self.db, led, market(), NOW)
        with mock.patch("time.time", lambda: NOW + 60):
            v = command.paper_view(self.db, now=NOW + 60)
            b = command.balance(self.db, now=NOW + 60)
        s = next(x for x in v["strategies"] if x["exp_id"] == led)
        self.assertEqual(s["label"], lane.SCAN_LABEL)
        self.assertEqual(s["name"], "Scannerkonto BBBUSDT")
        self.assertTrue(s["lane_info"]["scanner"])
        self.assertEqual(b["lane"]["scanner"], 1)
        self.assertIsNone(b["capital"])


class PremiumWatch(Base):
    """Amendment 12a: the perp premium every minute, observations only."""
    def setUp(self):
        super().setUp()
        scanner._PERPS.clear()
        self.urls = []

    def get(self, prem):
        def g(url):
            self.urls.append(url)
            if url.endswith("/fapi/v1/exchangeInfo"):
                return {"symbols": [{"symbol": s, "contractType": "PERPETUAL", "underlyingType": "COIN",
                                     "status": "TRADING", "quoteAsset": "USDT"} for s in ("AAAUSDT", "BBBUSDT")]}
            if url.endswith("/fapi/v1/premiumIndex"):
                return [{"symbol": s, "markPrice": str(100 * (1 + v)), "indexPrice": "100", "lastFundingRate": "0.001"}
                        for s, v in prem.items()]
            raise AssertionError(url)
        return g

    def test_writes_observations_only_and_reads_the_perp_list_hourly(self):
        events = self.db.one("SELECT COUNT(*) FROM events")[0]
        out = scanner.premium_watch(self.db, self.get({"AAAUSDT": 0.012, "BBBUSDT": 0.001, "ZZZUSDT": 0.05}), NOW - 60)
        self.assertEqual((out["observations"], out["flagged"]), (2, 1))           # ZZZ is not a traded perp
        scanner.premium_watch(self.db, self.get({"AAAUSDT": 0.006}), NOW - 30)
        self.assertEqual(sum(u.endswith("exchangeInfo") for u in self.urls), 1)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events")[0], events)   # no market.event, no candidate
        self.assertTrue(all(u.startswith("https://fapi.binance.com/") for u in self.urls))
        self.assertEqual(lane.scans(self.db, NOW), [int(NOW - 30), int(NOW - 60)])
        self.assertEqual(lane.scan_candidates(self.db, NOW), ["AAAUSDT"])
        led = lane.manage(self.db, NOW, market(), fids=[])["scanner"]["started"][0]
        self.assertEqual(lane.started(self.db)[led]["coins"], ["AAAUSDT"])
        scanner.premium_watch(self.db, self.get({}), NOW + 3600 + 1)
        self.assertEqual(sum(u.endswith("exchangeInfo") for u in self.urls), 2)   # the list again after an hour


if __name__ == "__main__":
    unittest.main()
