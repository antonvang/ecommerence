"""Director order 82 point 3: one regression file across the unapplied patches 72, 80, 81 and 82 for missing market
data, false recovery and partial closes. Temporary copies and synthetic data only; lab/ and the pinned lab/straks.py and
lab/pairs.py are never changed; no network, no DNS, no lab.db."""
import hashlib
import inspect
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from lab import carry90, lane, pairs, straks, paper_runner as real  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.mission import EXTERNAL_RUNNING_S  # noqa: E402
from lab.paper import PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from research.tools import partial_close as pc  # noqa: E402
from tests.test_lab_engine_remediation_67 import apply_unified, load  # noqa: E402
from tests.test_partial_close_78 import HOUR, NOW, PERP, SPOT, market, no_network  # noqa: E402

PATCHES = os.path.join(HERE, "research", "desk", "patches")
CLOSE = ("80_close_terminal_state.diff", "81_close_terminal_state_v2.diff", "82_close_post_terminal_funding.diff")
FROZEN = {"straks.py": "7a110f1fa20fb7d28b76269fc039eec4c75ddfa7353602f2f8824490b722a542",
          "pairs.py": "5c9b60a4314a40a5e4d517427c4960220682b8f6179a445a5554903180ce1219"}
EID = "X01_pm_lp_v1"


def text(name):
    with open(os.path.join(PATCHES, name), encoding="utf-8") as f:
        return f.read()


def close_module(name, tmp):
    os.makedirs(tmp, exist_ok=True)
    path = apply_unified(text(name), os.path.dirname(HERE), tmp)["copybot/lab/paper_runner.py"]
    return load("pr_" + name[:2], path)


class Patches(unittest.TestCase):
    def test_every_patch_applies_strictly_to_the_current_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in CLOSE + ("72_external_watch_data_activity.diff",):
                out = os.path.join(tmp, name)
                os.makedirs(out)
                self.assertTrue(apply_unified(text(name), os.path.dirname(HERE), out), name)

    def test_81_observability_applies_on_top_of_72(self):
        from tests.test_observability_81 import stack
        with tempfile.TemporaryDirectory() as tmp:
            files, _ = stack(tmp)
        self.assertIn("ops", files)

    def test_the_close_patches_are_alternatives_not_a_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "a", "copybot", "lab")
            os.makedirs(first)
            apply_unified(text(CLOSE[1]), os.path.dirname(HERE), first)        # 81 v2 applied in a copy
            with self.assertRaises(AssertionError):                            # 82 does not apply on top of it
                apply_unified(text(CLOSE[2]), os.path.join(tmp, "a"), tmp)

    def test_the_repo_and_the_pinned_books_are_unchanged(self):
        for f, sha in FROZEN.items():
            with open(os.path.join(HERE, "lab", f), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sha, f)
        for mod in ("POST_TERMINAL_FUNDING", "CLOSE_STATE", "close_state_of"):
            self.assertFalse(hasattr(real, mod))


class MissingSpot(unittest.TestCase):
    """The same carry account, spot book host permanently gone, under the real code and each close patch."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab82r")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for p in (mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)):
            p.start()
            self.addCleanup(p.stop)

    def account(self, name):
        db = DB(os.path.join(self.tmp, name, "lab.db"))
        self.addCleanup(db.close)
        real._HOURLY.clear()
        get = market()
        with db.tx():
            db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                      metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(db, NOW - 60)
        led = {i["key"]: x for x, i in lane.started(db).items()}["carry90|BTCUSDT"]
        self.assertEqual(lane.run_one(db, led, get, NOW)["status"], "ok")
        lane.retire(db, led, "source", "synthetic test stop", None, NOW + 60)
        before = dict(PaperEngine(db).ledger(led)["positions"])
        return db, led, get, before

    def run_close(self, close_ledger, db, led, get, t):
        get.now, get.spot, get.perp = t, real.urllib.error.URLError(OSError("blocked")), None
        return close_ledger(db, led, led, get, t)

    def verdict78(self, db, led, before):
        closed = {}
        for r in db.q("SELECT f.instrument, f.qty FROM sim_fills f JOIN sim_orders o ON o.order_id=f.order_id "
                      "WHERE f.exp_id=? AND o.reduce_only=1", led):
            closed[r["instrument"]] = closed.get(r["instrument"], 0.0) + r["qty"]
        mark = db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", led)[0]
        fill = db.one("SELECT MAX(ts) FROM sim_fills WHERE exp_id=?", led)[0]
        return pc.classify_close(before, PaperEngine(db).ledger(led)["positions"], closed, fill, mark)["status"]

    def test_real_code_closes_the_perp_alone_and_says_only_closing(self):
        db, led, get, before = self.account("real")
        r = self.run_close(real.close_ledger, db, led, get, NOW + HOUR)
        self.assertEqual(r["status"], "closing")
        self.assertNotIn("close_state", r)
        self.assertEqual(set(PaperEngine(db).ledger(led)["positions"]), {SPOT})
        self.assertEqual(self.verdict78(db, led, before), pc.PARTIAL_CLOSE)

    def test_80_marks_it_partial_terminal(self):
        db, led, get, before = self.account("p80")
        pm = close_module(CLOSE[0], os.path.join(self.tmp, "m80"))
        r = self.run_close(pm.close_ledger, db, led, get, NOW + HOUR)
        self.assertEqual(r["close_state"], pm.PARTIAL_TERMINAL)
        self.assertEqual(set(PaperEngine(db).ledger(led)["positions"]), {SPOT})

    def test_81_and_82_keep_the_pair_and_mark_it_incomplete(self):
        for i, name in enumerate(CLOSE[1:]):
            db, led, get, before = self.account(f"p8{i + 1}")
            pm = close_module(name, os.path.join(self.tmp, f"m{name[:2]}"))
            r = self.run_close(pm.close_ledger, db, led, get, NOW + HOUR)
            self.assertEqual(r["close_state"], pm.INCOMPLETE_TERMINAL, name)
            self.assertFalse(r["closed"], name)
            self.assertTrue(r["requires_decision"], name)
            self.assertEqual(PaperEngine(db).ledger(led)["positions"], before, name)
            self.assertEqual(self.verdict78(db, led, before), pc.CLOSE_INCOMPLETE, name)

    def test_no_version_ever_reports_success_with_a_leg_open(self):
        for name in CLOSE:
            db, led, get, before = self.account("s" + name[:2])
            pm = close_module(name, os.path.join(self.tmp, "s" + name[:2] + "m"))
            for t in (NOW + HOUR, NOW + 2 * HOUR, NOW + 9 * 86400):
                r = self.run_close(pm.close_ledger, db, led, get, t)
                if PaperEngine(db).ledger(led)["positions"]:
                    self.assertNotEqual(r["close_state"], pm.CLOSE_SUCCESS, (name, t))


class FalseRecovery(unittest.TestCase):
    """Trade polls work, the book host does not: 72 alone recovers, 72 + 81 does not."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        from tests.test_observability_81 import stack
        self.files, o72 = stack(os.path.join(self.tmp, "s"))
        self.ops81 = load("lab._ops81r", self.files["ops"], package="lab")
        self.fleet81 = load("lab._fleet81r", self.files["fleet"], package="lab")
        self.ops72 = load("lab._ops72r", os.path.join(o72, "ops.py"), package="lab")
        self.fleet72 = load("lab._fleet72r", os.path.join(o72, "fleet.py"), package="lab")
        pm = os.path.join(self.tmp, "home", "data", "research", "pm_lp")
        os.makedirs(pm)
        self.pm_db = os.path.join(pm, "pm_lp.db")
        con = sqlite3.connect(self.pm_db)
        con.execute("CREATE TABLE snaps(t INTEGER, cid TEXT)")
        con.execute("CREATE TABLE polls(t INTEGER, kind TEXT, cid TEXT, ok INTEGER)")
        con.execute("CREATE TABLE status(t INTEGER, cid TEXT, closed INTEGER, accepting INTEGER, payout REAL)")
        con.commit()
        con.close()

    def poll(self, t, ok=1):
        con = sqlite3.connect(self.pm_db)
        con.execute("INSERT INTO polls VALUES(?,'trades','c',?)", (t, ok))
        con.commit()
        con.close()

    def run_watch(self, ops, fleet, db, now):
        with mock.patch.object(ops, "HERE", os.path.join(self.tmp, "home")), \
                mock.patch.object(fleet.ops, "external_freshness", lambda n=None: {
                    k: v for k, v in ops.external_freshness(now).items() if k == EID}):
            return fleet.external_watch(db, now)

    def kinds(self, db):
        return [r[0] for r in db.q("SELECT kind FROM events WHERE kind LIKE 'external.%' ORDER BY id")]

    def test_trade_polls_without_books(self):
        t0 = 1_800_000_000
        self.poll(t0 - 5 * EXTERNAL_RUNNING_S)
        dbs = {}
        for tag, ops, fleet in (("72", self.ops72, self.fleet72), ("81", self.ops81, self.fleet81)):
            dbs[tag] = DB(os.path.join(self.tmp, tag, "lab.db"))
            self.addCleanup(dbs[tag].close)
            self.run_watch(ops, fleet, dbs[tag], t0)
        self.poll(t0 + 10)                                  # a trade poll works again; no book snapshot arrives
        for tag, ops, fleet in (("72", self.ops72, self.fleet72), ("81", self.ops81, self.fleet81)):
            self.run_watch(ops, fleet, dbs[tag], t0 + 20)
        self.assertEqual(self.kinds(dbs["72"]), ["external.stale", "external.recovered"])   # the false recovery
        self.assertEqual(self.kinds(dbs["81"]), ["external.stale"])


class OneBookProbe(unittest.TestCase):
    """Order 82 point 2: STRAKS and PAR-BOG resume a data_fetch pause on one BTCUSDT book. Documented, not changed."""

    def test_the_frozen_probes_read_one_btc_book(self):
        for mod in (straks, pairs):
            src = inspect.getsource(mod.run_one)
            self.assertIn('risk.auto_resume(ledger, lambda: pr.fetch_book("BTCUSDT", now, get))', src)
            self.assertNotIn('"data_fetch"', src)          # these modules never set the pause the probe would lift

    def test_the_markets_each_book_needs(self):
        self.assertEqual(len({s for p in pairs.PAIRS for s in p}), 8)
        from lab import moves
        self.assertEqual(len(moves.WATCH), 12)

    def test_one_working_book_resumes_a_book_whose_other_markets_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(os.path.join(tmp, "lab.db"))
            try:
                t = {"now": NOW}
                risk = Risk(db, now=lambda: t["now"])
                risk.pause("LANE_synthetic_straks", "data_fetch", None, None, "synthetic")
                btc_ok = lambda: None                                        # noqa: E731
                resumed = False
                for m in range(0, 120, 10):
                    t["now"] = NOW + m * 60
                    resumed = risk.auto_resume("LANE_synthetic_straks", btc_ok)   # XAU, CL, SPY ... never asked
                    if resumed:
                        break
                self.assertTrue(resumed)
            finally:
                db.close()

    def test_the_81_multi_source_rule_would_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            risk_part = text("81_observability_recovered.diff").split("--- a/copybot/lab/risk.py")[1]
            risk_part = "--- a/copybot/lab/risk.py" + risk_part.split("--- a/copybot/lab/lane.py")[0]
            files = apply_unified(risk_part, os.path.dirname(HERE), tmp)       # only the risk.py part of 81
            rk = load("lab._risk82", files["copybot/lab/risk.py"], package="lab")
            db = DB(os.path.join(tmp, "lab.db"))
            try:
                t = {"now": NOW}
                risk = rk.Risk(db, now=lambda: t["now"])
                risk.pause("LANE_synthetic_straks", "data_fetch", None, None, "synthetic")

                def xau():
                    raise OSError("no bars")
                probes = [("BTCUSDT", lambda: None), ("XAUUSDT", xau)]
                for m in range(0, 180, 10):
                    t["now"] = NOW + m * 60
                    self.assertFalse(risk.auto_resume("LANE_synthetic_straks", probes))
                self.assertTrue(risk.paused("LANE_synthetic_straks"))
            finally:
                db.close()


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
