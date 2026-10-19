"""Forward paper tests and pause rules for simulated ledgers (research/PROTOCOL_V3.md amendment 7)."""
import collections
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, lifecycle, paper, paper_runner, pipeline  # noqa: E402
from lab.__main__ import main  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.lab_fixtures import approve_paper, frozen  # noqa: E402
from tests.test_lab_paper_runner import HOUR, MON, SAT, feed  # noqa: E402

A, B = "E_day_of_week_p1", "E_xs_momentum_p2"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfwd")
        self.path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.path)
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("lab.__main__.TERMINAL_GUARD", lambda step: None)]     # a human in a terminal
        for p in self.p:
            p.start()
        pins = {}
        for eid, tpl, variants, sel in (
                (A, "day_of_week", [{"variant": 0, "params": {"mode": "flat_weekend"}, "fit": None, "positions": {}},
                                   {"variant": 1, "params": {"mode": "weekend_only"}, "fit": None, "positions": {}}], 1),
                (B, "xs_momentum", [{"variant": 0, "params": {"lookback_days": 7, "k": 2}, "fit": None,
                                     "positions": {}}], 0)):
            self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=tpl, fingerprint=eid,
                           spec_json={"template": tpl, "execution": "taker"})
            self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="REJECTED", actor="fixture",
                           reason="fixture: rejected at validation")
            c = frozen(self.db, eid, "cost", {"selected": sel})
            b = frozen(self.db, eid, "backtest", {"variants": variants})
            pins[eid] = (c["sha256"], b["sha256"])
        self.pins = mock.patch.dict(paper.FORWARD_ACCOUNTS, pins, clear=True)
        self.pins.start()

    def tearDown(self):
        self.pins.stop()
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *argv):
        lines = []
        rc = main(list(argv), self.path, lines.append)
        return rc, "\n".join(lines)

    def count(self, table, eid=None):
        return self.db.one(f"SELECT COUNT(*) FROM {table}" + (" WHERE exp_id=?" if eid else ""),
                           *([eid] if eid else []))[0]


class Start(Base):
    def test_only_a_human_starts_the_listed_forward_tests_with_their_pinned_artifacts(self):
        self.assertEqual(self.cli("forward-start", "--reason", "short")[0], 1)
        self.assertEqual(self.cli("forward-start", "--exp", "E_other", "--reason", "user approved on 2026-10-18")[0], 1)
        self.assertEqual(paper_runner.forward_experiments(self.db), [])
        rc, txt = self.cli("forward-start", "--reason", "user approved forward tests on 2026-10-18")
        self.assertEqual(rc, 0, txt)
        ev = self.db.q("SELECT actor, exp_id FROM events WHERE kind='forward.approved' ORDER BY id")
        self.assertEqual([(r["actor"].startswith("human:"), r["exp_id"]) for r in ev], [(True, A), (True, B)])
        self.assertEqual(paper_runner.forward_experiments(self.db), [A, B])
        self.db.event("forward.approved", "agent:x", A, {"reason": "not a human"})
        self.assertNotIn(A, paper_runner.forward_experiments(self.db))               # the latest must be a human's

    def test_a_changed_artifact_stops_the_forward_test(self):
        self.cli("forward-start", "--reason", "user approved forward tests on 2026-10-18")
        frozen(self.db, A, "backtest", {"variants": [{"variant": 1, "params": {"mode": "flat_weekend"}, "fit": None,
                                                      "positions": {}}]})       # a different recorded artifact
        self.assertEqual(paper_runner.forward_experiments(self.db), [B])
        self.assertEqual(self.cli("forward-start", "--exp", A, "--reason", "user approved forward tests again")[0], 1)


class Trading(Base):
    def test_forward_ledgers_trade_apart_from_the_formal_record_and_the_headline_balance(self):
        before = {t: self.count(t) for t in ("results", "trials", "transitions", "approvals", "experiments")}
        self.cli("forward-start", "--reason", "user approved forward tests on 2026-10-18")
        g, n = feed(SAT), collections.Counter()

        def counted(path):
            n["depth" if "depth" in path else "other"] += 1
            return g(path)
        out = paper_runner.run(self.db, counted, SAT)["results"]
        self.assertEqual({k: v["status"] for k, v in out.items()}, {"FWD_" + A: "ok", "FWD_" + B: "ok"})
        orders = sum(len(v["orders"]) for v in out.values())
        self.assertEqual(n["depth"], len(data.UNIVERSE) + orders)                 # one shared book per symbol
        self.assertGreater(self.count("sim_orders", "FWD_" + A), 0)
        self.assertEqual(self.count("sim_orders", A), 0)
        self.assertEqual({t: self.count(t) for t in before}, before)              # no formal record touched
        self.assertEqual(lifecycle.state(self.db, A), "REJECTED")                # nothing revived
        b = command.balance(self.db)
        self.assertEqual((b["forward"]["ledgers"], b["strategies"], b["capital"]), (2, 0, None))
        self.assertEqual(b["forward"]["capital"], 2 * paper_runner.CAPITAL)
        self.assertEqual(b["combined"]["capital"], 2 * paper_runner.CAPITAL)        # amendment 9: shown apart
        v = {s["exp_id"]: s for s in command.paper_view(self.db)["strategies"]}
        self.assertTrue(v["FWD_" + A]["forward"])
        self.assertIn("ikke godkendt", v["FWD_" + A]["label"])
        self.assertIn("fremadtest", v["FWD_" + A]["name"])
        tags = [i["tag"] for i in command.feed(self.db)["items"]]
        self.assertIn("FREMADTEST", tags)
        self.assertNotIn("KØB", tags)                                             # orders are shown per account

    def test_a_stopped_forward_test_closes_its_positions(self):
        self.cli("forward-start", "--exp", A, "--reason", "user approved forward tests on 2026-10-18")
        paper_runner.run(self.db, feed(SAT), SAT)
        self.assertTrue(PaperEngine(self.db).ledger("FWD_" + A)["positions"])
        self.cli("forward-stop", "--exp", A, "--reason", "user stopped the forward test")
        r = paper_runner.run(self.db, feed(SAT + HOUR), SAT + HOUR)["results"]["FWD_" + A]
        self.assertEqual(r["status"], "closing")
        self.assertEqual(PaperEngine(self.db).ledger("FWD_" + A)["positions"], {})
        self.assertTrue(PaperEngine(self.db).reconcile("FWD_" + A)["ok"])


class ReviewFixes(Base):
    def test_forward_start_is_all_or_nothing(self):
        paper.FORWARD_ACCOUNTS[B] = ("0" * 64, "0" * 64)                        # one pin no longer matches
        rc, txt = self.cli("forward-start", "--reason", "user approved forward tests on 2026-10-18")
        self.assertEqual(rc, 1)
        self.assertIn(B, txt)
        self.assertEqual(self.count("events WHERE kind='forward.approved'"), 0)    # nothing started

    def test_closing_reads_only_books_once_an_hour_and_marks(self):
        self.cli("forward-start", "--reason", "user approved forward tests on 2026-10-18")
        cache = {}                                                                 # the live runner's shared cache
        paper_runner.run(self.db, feed(SAT), SAT, cache=cache)
        pos = [PaperEngine(self.db).ledger("FWD_" + e)["positions"] for e in (A, B)]
        held, symbols = sum(len(p) for p in pos), {s for p in pos for s in p}
        self.cli("forward-stop", "--reason", "user stopped the forward tests")
        n = collections.Counter()
        g = feed(SAT + HOUR)

        def counted(path):
            n["depth" if "depth" in path else "bars/funding"] += 1
            return g(path)
        paper_runner.run(self.db, counted, SAT + HOUR, cache=cache)
        self.assertEqual(n["depth"], held)                                          # one fresh book per close order
        self.assertEqual(n["bars/funding"], 2 * len(symbols))   # amendment 9: funding data once per symbol and hour
        closings = self.count("events WHERE kind='paper.closing'")
        self.assertEqual(self.count("sim_equity WHERE ts>=?".replace("?", str(int(SAT + HOUR) // HOUR * HOUR))), 2)
        paper_runner.run(self.db, counted, SAT + HOUR + 60, cache=cache)          # same hour: nothing to send
        self.assertEqual(self.count("events WHERE kind='paper.closing'"), closings)
        self.assertEqual(n["depth"], held)
        self.assertEqual(n["bars/funding"], 2 * len(symbols))

    def test_a_resume_is_refused_while_the_drawdown_breaker_would_trip_again(self):
        led = "FWD_" + A
        for dd in (0.12,):
            self.db.append("sim_equity", exp_id=led, ts=int(SAT), equity=8800.0, cash=8800.0, exposure=0.0,
                           peak=10000.0, drawdown=dd)
        Risk(self.db).after_equity(led, 0.12)
        rc, txt = self.cli("sim-resume", led, "--reason", "user wants to resume the forward test")
        self.assertEqual(rc, 1)
        self.assertIn("still at or above", txt)
        self.db.append("sim_equity", exp_id=led, ts=int(SAT + HOUR), equity=9500.0, cash=9500.0, exposure=0.0,
                       peak=10000.0, drawdown=0.05)
        self.assertEqual(self.cli("sim-resume", led, "--reason", "user wants to resume the forward test")[0], 0)
        self.assertFalse(Risk(self.db).paused(led))


class PauseRules(Base):
    def test_two_losses_in_a_row_pause_approved_paper_but_not_simulated_ledgers(self):
        losses = [(1, -1.0), (2, -1.0)]
        for led in ("FWD_" + A, "SHADOW_E_mvrv_value_p3"):
            self.assertEqual(Risk(self.db).after_trade_closed(led, losses), 0)
            self.assertFalse(Risk(self.db).paused(led))
        approve_paper(self.db, "E_paper_x")
        self.assertEqual(Risk(self.db).after_trade_closed("E_paper_x", losses), 2)
        self.assertTrue(Risk(self.db).paused("E_paper_x"))

    def test_a_drawdown_pauses_a_forward_ledger_and_only_a_human_resumes_it(self):
        led = "FWD_" + A
        Risk(self.db).after_equity(led, 0.12)                                      # 12 % > 10 %
        self.assertTrue(Risk(self.db).paused(led))
        with self.assertRaises(lifecycle.LifecycleError):
            Risk(self.db).resume_simulated(led, "agent:risk-1", "an agent may not resume this")
        with self.assertRaises(lifecycle.LifecycleError):
            Risk(self.db).resume_simulated("E_paper_x", "human:x", "approved strategies resume by revalidation")
        self.assertEqual(self.cli("sim-resume", led, "--reason", "short")[0], 1)
        rc, txt = self.cli("sim-resume", led, "--reason", "user looked at the drawdown and resumes")
        self.assertEqual(rc, 0, txt)
        self.assertFalse(Risk(self.db).paused(led))
        clear = self.db.one("SELECT actor, rule FROM risk_events WHERE exp_id=? AND action='CLEAR'", led)
        self.assertTrue(clear["actor"].startswith("human:"))
        self.assertEqual(clear["rule"], "manual_resume")

    def test_the_dashboard_shows_why_a_ledger_is_paused_and_how_to_resume_it(self):
        from lab import command
        led = "FWD_" + A
        self.assertIsNone(command._pause_info(Risk(self.db), led))
        Risk(self.db).after_equity(led, 0.12)
        info = command._pause_info(Risk(self.db), led)
        self.assertEqual(info["rule"], "max_drawdown")
        self.assertIn(f"python3 -m lab sim-resume {led}", info["resume"])

    def test_sim_resume_is_typed_by_a_human_in_a_terminal(self):
        led = "FWD_" + A
        Risk(self.db).after_equity(led, 0.12)
        from lab import __main__ as cli_mod
        with mock.patch("lab.__main__.TERMINAL_GUARD", cli_mod.terminal_human), \
                mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            rc, txt = self.cli("sim-resume", led, "--reason", "an assistant resumes the ledger")
        self.assertEqual(rc, 1)
        self.assertIn("an assistant session may not resume a simulated ledger", txt)
        self.assertTrue(Risk(self.db).paused(led))
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
        with mock.patch("lab.__main__.TERMINAL_GUARD", cli_mod.terminal_human), \
                mock.patch.dict(os.environ, env, clear=True), mock.patch("sys.stdin.isatty", lambda: False):
            rc, txt = self.cli("sim-resume", led, "--reason", "no terminal resumes the ledger")
        self.assertEqual(rc, 1)
        self.assertIn("must be typed in an interactive terminal", txt)
        self.assertTrue(Risk(self.db).paused(led))

    def test_a_paused_forward_ledger_is_kept_and_marked(self):
        self.cli("forward-start", "--exp", A, "--reason", "user approved forward tests on 2026-10-18")
        paper_runner.run(self.db, feed(SAT), SAT)
        held = PaperEngine(self.db).ledger("FWD_" + A)["positions"]
        Risk(self.db, lambda: SAT).pause("FWD_" + A, "max_drawdown", 0.12, 0.1, "test")
        r = paper_runner.run(self.db, feed(MON), MON)["results"]["FWD_" + A]  # Monday: the rule would sell
        self.assertEqual((r["status"], r["marked"]), ("paused", True))
        self.assertEqual(PaperEngine(self.db).ledger("FWD_" + A)["positions"], held)


if __name__ == "__main__":
    unittest.main()
