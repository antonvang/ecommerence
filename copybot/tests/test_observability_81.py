"""Director order 81 P0: the unapplied patch research/desk/patches/81_observability_recovered.diff, applied strictly on top
of 72_external_watch_data_activity.diff on temporary copies. Synthetic data; no network, no DNS, no lab.db, no pm_lp.db.
lab/ is not changed by this test."""
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from lab import carry90, lane, paper_runner as real  # noqa: E402
from lab import risk as real_risk  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.mission import EXTERNAL_RUNNING_S  # noqa: E402
from research import pm_lp  # noqa: E402
from tests.test_lab_engine_remediation_67 import apply_unified, load  # noqa: E402
from tests.test_partial_close_78 import DNS, HOUR, NOW, market, no_network  # noqa: E402

PATCHES = os.path.join(HERE, "research", "desk", "patches")
EID = "X01_pm_lp_v1"
NAMES = ("ops", "fleet", "mission", "coverage", "risk", "lane", "watch")
LED = "FWD_E_synthetic"
DAY = 86400


def diff(name):
    with open(os.path.join(PATCHES, name), encoding="utf-8") as f:
        return f.read()


def stack(tmp):
    """Temporary copies of the lab files with 72 and then 81 applied; {name: patched path} and the 72-only paths."""
    tree = os.path.join(tmp, "tree", "copybot", "lab")
    os.makedirs(tree)
    for n in NAMES:
        shutil.copy(os.path.join(HERE, "lab", n + ".py"), tree)
    o72, o81 = os.path.join(tmp, "o72"), os.path.join(tmp, "o81")
    os.makedirs(o72)
    os.makedirs(o81)
    for rel, path in apply_unified(diff("72_external_watch_data_activity.diff"), os.path.dirname(HERE), o72).items():
        shutil.copy(path, tree)
    files = apply_unified(diff("81_observability_recovered.diff"), os.path.join(tmp, "tree"), o81)
    return {os.path.basename(k)[:-3]: v for k, v in files.items()}, o72


class Patched(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.files, self.o72 = stack(tmp.name)

    def mod(self, name):
        return load(f"lab._{name}81", self.files[name], package="lab")

    def pm_db(self, snaps=(), polls=(), status=()):
        fd, p = tempfile.mkstemp(suffix=".db", dir=self.tmp)
        os.close(fd)
        con = sqlite3.connect(p)
        con.execute("CREATE TABLE snaps(t INTEGER, cid TEXT)")
        con.execute("CREATE TABLE polls(t INTEGER, kind TEXT, cid TEXT, ok INTEGER)")
        con.execute("CREATE TABLE status(t INTEGER, cid TEXT, closed INTEGER, accepting INTEGER, payout REAL)")
        con.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO snaps VALUES(?,'c')", [(t,) for t in snaps])
        con.executemany("INSERT INTO polls VALUES(?,'trades','c',?)", polls)
        con.executemany("INSERT INTO status VALUES(?,'c',0,1,NULL)", [(t,) for t in status])
        con.commit()
        con.close()
        return p


class Stack(Patched):
    def test_81_builds_on_72_and_the_repo_stays_unpatched(self):
        self.assertEqual(sorted(self.files), sorted(NAMES))
        ops = load("lab._ops81a", self.files["ops"], package="lab")
        self.assertTrue(hasattr(ops, "data_activity_age"))         # from 72, not repeated
        self.assertTrue(hasattr(ops, "required_data_age"))         # from 81
        before = {n: hashlib.sha256(open(os.path.join(HERE, "lab", n + ".py"), "rb").read()).hexdigest() for n in NAMES}
        with tempfile.TemporaryDirectory() as tmp:
            stack(tmp)
        for n in NAMES:
            with open(os.path.join(HERE, "lab", n + ".py"), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), before[n], n)
        from lab import ops as repo_ops
        self.assertFalse(hasattr(repo_ops, "required_data_age"))
        self.assertFalse(hasattr(repo_ops, "data_activity_age"))


class Required(Patched):
    def setUp(self):
        super().setUp()
        self.ops = self.mod("ops")
        self.src = self.ops.EXTERNAL_REQUIRED[EID]

    def req(self, **k):
        return self.ops.required_data_age(self.pm_db(**k), self.src, 10_000)

    def test_trade_polls_alone_are_not_enough_although_72_would_accept_them(self):
        polls = [(9_990, 1)]
        ops72 = load("lab._ops72only", os.path.join(self.o72, "ops.py"), package="lab")
        p = self.pm_db(polls=polls)
        self.assertEqual(ops72.data_activity_age(p, 10_000), 10)   # the case 72 reads as active
        r = self.ops.required_data_age(p, self.src, 10_000)
        self.assertEqual(r["age"], 10_000)                         # no book snapshot has ever arrived

    def test_a_status_row_alone_is_not_enough(self):
        self.assertEqual(self.req(status=[9_990])["age"], 10_000)

    def test_failed_polls_are_not_observations(self):
        r = self.req(snaps=[9_990], polls=[(9_995, 0)])
        self.assertEqual(r["sources"]["trade polls"], 10_000)

    def test_every_source_fresh_gives_the_oldest_age(self):
        r = self.req(snaps=[9_990], polls=[(9_900, 1)])
        self.assertEqual(r["age"], 100)
        self.assertEqual(r["sources"], {"book snapshots": 10, "trade polls": 100})

    def test_unreadable_or_missing_database_decides_nothing(self):
        self.assertIsNone(self.ops.required_data_age(os.path.join(self.tmp, "none.db"), self.src, 10_000))
        p = os.path.join(self.tmp, "broken.db")
        with open(p, "wb") as f:
            f.write(b"not a database")
        self.assertIsNone(self.ops.required_data_age(p, self.src, 10_000))

    def test_the_read_changes_nothing(self):
        p = self.pm_db(snaps=[9_990], polls=[(9_900, 1)])
        with open(p, "rb") as f:
            before = f.read()
        self.ops.required_data_age(p, self.src, 10_000)
        with open(p, "rb") as f:
            self.assertEqual(f.read(), before)


class ExternalWatch(Patched):
    def setUp(self):
        super().setUp()
        self.fleet = self.mod("fleet")
        self.db = DB(os.path.join(self.tmp, "db", "lab.db"))
        self.addCleanup(self.db.close)

    def kinds(self):
        return [r[0] for r in self.db.q("SELECT kind FROM events WHERE kind LIKE 'external.%' ORDER BY id")]

    def watch(self, write_age, required):
        fresh = lambda now=None: {EID: {"label": "x", "last_write_age_s": write_age, "last_data_age_s": 5.0,  # noqa: E731
                                        "required_data_age_s": required, "basis": "every required data source"}}
        with mock.patch.object(self.fleet.ops, "external_freshness", fresh):
            return self.fleet.external_watch(self.db)

    def test_fresh_file_and_trade_polls_without_books_are_no_recovery(self):
        self.watch(EXTERNAL_RUNNING_S + 60, EXTERNAL_RUNNING_S + 60)
        self.assertEqual(self.watch(2.0, EXTERNAL_RUNNING_S + 120), [EID])
        self.assertEqual(self.kinds(), ["external.stale"])

    def test_every_required_source_is_a_recovery(self):
        self.watch(EXTERNAL_RUNNING_S + 60, EXTERNAL_RUNNING_S + 60)
        self.watch(2.0, 30.0)
        self.assertEqual(self.kinds(), ["external.stale", "external.recovered"])

    def test_unreadable_required_source_decides_nothing(self):
        self.watch(EXTERNAL_RUNNING_S + 60, EXTERNAL_RUNNING_S + 60)
        self.watch(2.0, None)
        self.assertEqual(self.kinds(), ["external.stale"])

    def test_a_process_without_data_rows_keeps_the_file_rule(self):
        fresh = lambda now=None: {"X": {"label": "x", "last_write_age_s": EXTERNAL_RUNNING_S + 1, "basis": "f"}}  # noqa: E731
        with mock.patch.object(self.fleet.ops, "external_freshness", fresh):
            self.assertEqual(self.fleet.external_watch(self.db), ["X"])


class Mission(Patched):
    def test_a_fresh_file_alone_does_not_read_as_running(self):
        m = self.mod("mission")
        cat = lambda x: m.status_category("EXTERNAL", EID, {EID: x}, None, None)  # noqa: E731
        self.assertEqual(cat({"last_write_age_s": 1.0, "required_data_age_s": 9_999.0}), "external — no valid data")
        self.assertEqual(cat({"last_write_age_s": 1.0, "required_data_age_s": 30.0}), "running (external process)")
        self.assertEqual(cat({"last_write_age_s": 9_999.0}), "external — no recent writes")
        self.assertEqual(cat({"last_write_age_s": 1.0}), "running (external process)")


class AutoResume(Patched):
    def setUp(self):
        super().setUp()
        self.risk_mod = self.mod("risk")
        self.db = DB(os.path.join(self.tmp, "db", "lab.db"))
        self.addCleanup(self.db.close)
        self.t = NOW
        self.risk = self.risk_mod.Risk(self.db, now=lambda: self.t)
        self.risk.pause(LED, "data_fetch", None, None, "synthetic")

    @staticmethod
    def ok():
        return None

    @staticmethod
    def bad():
        raise OSError("no route")

    def probe_for(self, minutes, probe):
        out = None
        for m in range(0, minutes + 1, 10):
            self.t = NOW + m * 60
            out = self.risk.auto_resume(LED, probe)
            if out:
                break
        return out

    def test_working_perp_does_not_hide_a_missing_spot_source(self):
        self.assertFalse(self.probe_for(180, [("perp", self.ok), ("spot", self.bad)]))
        self.assertTrue(self.risk.paused(LED))
        r = self.db.one("SELECT value, detail FROM risk_events WHERE exp_id=? AND action='PROBE' ORDER BY id DESC LIMIT 1", LED)
        self.assertEqual(r["value"], 0)
        self.assertIn("spot:", r["detail"])

    def test_every_source_working_resumes(self):
        self.assertTrue(self.probe_for(120, [("perp", self.ok), ("spot", self.ok)]))
        self.assertFalse(self.risk.paused(LED))

    def test_a_failure_of_one_source_restarts_the_run(self):
        src = {"bad": False}

        def spot():
            if src["bad"]:
                raise OSError("no route")
        self.t = NOW
        self.risk.auto_resume(LED, [("spot", spot)])
        self.t = NOW + 2400
        src["bad"] = True
        self.risk.auto_resume(LED, [("spot", spot)])
        src["bad"] = False
        self.t = NOW + 3600
        self.assertFalse(self.risk.auto_resume(LED, [("spot", spot)]))

    def test_no_declared_source_never_resumes(self):
        self.assertFalse(self.probe_for(180, []))
        self.assertTrue(self.risk.paused(LED))

    def test_a_single_probe_keeps_its_old_meaning(self):
        self.assertTrue(self.probe_for(120, self.ok))


class LaneProbe(Patched):
    """The patched lane.run_one with the patched Risk, on an account opened by the real code."""

    def setUp(self):
        super().setUp()
        self.db = DB(os.path.join(self.tmp, "db", "lab.db"))
        self.addCleanup(self.db.close)
        for p in (mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network)):
            p.start()
            self.addCleanup(p.stop)
        real._HOURLY.clear()
        self.get = market()
        with self.db.tx():
            self.db.append("observations", ts=NOW - 3600, detector="census/1", source="x", instrument="binance",
                           metric="snapshot", value=0.0, flagged=0, payload={})
        carry90.ensure(self.db, NOW - 60)
        self.led = {i["key"]: x for x, i in lane.started(self.db).items()}["carry90|BTCUSDT"]
        self.assertEqual(lane.run_one(self.db, self.led, self.get, NOW)["status"], "ok")
        self.risk_mod = self.mod("risk")
        self.lane = self.mod("lane")
        p = mock.patch.object(self.lane, "Risk", self.risk_mod.Risk)
        p.start()
        self.addCleanup(p.stop)
        self.risk_at(NOW + 60).pause(self.led, "data_fetch", None, None, "synthetic")

    def risk_at(self, t):
        return self.risk_mod.Risk(self.db, lambda: t)

    def run_for(self, spot):
        for m in range(10, 180, 10):
            t = NOW + 60 + m * 60
            self.get.now, self.get.spot = t, spot
            real._HOURLY.clear()
            self.lane.run_one(self.db, self.led, self.get, t)
            if not self.risk_at(t).paused(self.led):
                return True
        return False

    def test_a_carry_account_stays_paused_while_only_perp_data_work(self):
        self.assertFalse(self.run_for(DNS))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM risk_events WHERE exp_id=? AND rule='auto_resume'",
                                     self.led)[0], 0)
        r = self.db.one("SELECT detail FROM risk_events WHERE exp_id=? AND action='PROBE' ORDER BY id DESC LIMIT 1",
                        self.led)
        self.assertIn("spot:", r["detail"])

    def test_the_real_unpatched_probe_would_have_resumed(self):
        """Documents the fault the patch removes (real lab code, nothing patched)."""
        for m in range(10, 180, 10):
            t = NOW + 60 + m * 60
            self.get.now, self.get.spot = t, DNS
            real._HOURLY.clear()
            lane.run_one(self.db, self.led, self.get, t)
            if not real_risk.Risk(self.db, lambda: t).paused(self.led):
                return
        self.fail("the unpatched probe no longer resumes on perp data alone")

    def test_all_sources_working_resumes(self):
        self.assertTrue(self.run_for(None))


class Finished(Patched):
    def setUp(self):
        super().setUp()
        self.watch = self.mod("watch")
        p = mock.patch.object(self.watch, "_processes", lambda pattern: [123])
        p.start()
        self.addCleanup(p.stop)
        self.d0 = 20_000
        self.end = (self.d0 + pm_lp.TAIL_END + 1) * DAY

    def db_with(self, **k):
        p = self.pm_db(**k)
        con = sqlite3.connect(p)
        con.execute("INSERT INTO meta VALUES('D0', ?)", (str(self.d0),))
        con.commit()
        con.close()
        return p

    def test_the_calendar_alone_is_not_finished(self):
        ok, text = self.watch.check_collector(self.db_with(snaps=[self.d0 * DAY], status=[self.d0 * DAY]), self.end + 10)
        self.assertIsNone(ok)
        self.assertNotIn("finished (", text)

    def test_no_status_at_all_is_not_finished(self):
        self.assertIsNone(self.watch.check_collector(self.db_with(), self.end + 10)[0])

    def test_status_polls_to_the_end_are_finished(self):
        ok, text = self.watch.check_collector(self.db_with(status=[self.end - 3600]), self.end + 10)
        self.assertTrue(ok)
        self.assertIn("finished", text)

    def test_the_real_unpatched_check_reports_finished_on_the_date_alone(self):
        """Documents the fault the patch removes (real lab/watch.py)."""
        from lab import watch as real_watch
        with mock.patch.object(real_watch, "_processes", lambda pattern: [123]):
            self.assertEqual(real_watch.check_collector(self.db_with(), self.end + 10),
                             (True, "collection finished (after resolution tracking)"))

    def test_during_the_study_nothing_changes(self):
        now = self.d0 * DAY + DAY
        ok, _ = self.watch.check_collector(self.db_with(snaps=[int(now) - 10]), now)
        self.assertTrue(ok)
        ok, text = self.watch.check_collector(self.db_with(snaps=[int(now) - 10_000]), now)
        self.assertFalse(ok)
        self.assertIn("alive but last snapshot", text)


class Coverage(Patched):
    def test_a_running_claim_needs_data_not_a_fresh_file(self):
        cov = self.mod("coverage")
        db = DB(os.path.join(self.tmp, "db", "lab.db"))
        self.addCleanup(db.close)
        with db.tx():
            db.append("experiments", exp_id=EID, version=1, created_ts=1, mechanism_tag="m", fingerprint="f", spec_json="{}",
                      spec_path="p", spec_commit="c", code_hash="h", note="n")
            db.append("results", exp_id=EID, version=1, ts=2, label="l", verdict="RUNNING", metrics={}, evidence={},
                      supersedes=None)
        ext = {EID: {"label": "x", "last_write_age_s": 1.0, "required_data_age_s": 3 * DAY}}
        with mock.patch("lab.ops.external_freshness", lambda now=None: ext):
            out = cov.hypotheses(db)
        self.assertEqual(out["mechanisms"][0]["experiments"][0]["verdict"], "UNVERIFIED")
        ext[EID]["required_data_age_s"] = 60.0
        with mock.patch("lab.ops.external_freshness", lambda now=None: ext):
            out = cov.hypotheses(db)
        self.assertEqual(out["mechanisms"][0]["experiments"][0]["verdict"], "RUNNING")


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
