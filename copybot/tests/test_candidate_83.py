"""Director order 83 points 1-2: the unapplied candidate series research/desk/patches/83_candidate_*.diff on temporary
copies. Post-terminal funding is booked once, reported apart by the net_report candidate and never counted as strategy
performance, also after a restart. research/tools/net_report.py (pinned e8cac57c) and lab/ are not changed. Synthetic
data only; no network, no DNS, no lab.db."""
import hashlib
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

from lab import carry90, lane, paper_runner as real  # noqa: E402
from lab.db import DB  # noqa: E402
from tests.test_lab_engine_remediation_67 import apply_unified, load  # noqa: E402
from tests.test_partial_close_78 import DNS, HOUR, NOW, market, no_network  # noqa: E402

PATCHES = os.path.join(HERE, "research", "desk", "patches")
C1, C2, C3 = ("83_candidate_1_observability.diff", "83_candidate_2_close.diff", "83_candidate_3_net_report.diff")
NET_REPORT = os.path.join(HERE, "research", "tools", "net_report.py")
NET_REPORT_PIN = "e8cac57c9a407912c25e884b2c4ca3b6c9f6b2cf2bf0d6ed8e2ee3acb31e405f"
T1, T2, T3 = NOW + 4 * HOUR, NOW + 12 * HOUR, NOW + 20 * HOUR   # after the 00:00, 08:00 and 16:00 UTC settlements


def apply(name, out):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(PATCHES, name), encoding="utf-8") as f:
        return apply_unified(f.read(), os.path.dirname(HERE), out)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Series(unittest.TestCase):
    def test_each_candidate_applies_strictly_and_the_repo_is_unchanged(self):
        before = {p: sha(os.path.join(HERE, p)) for p in ("lab/paper_runner.py", "lab/ops.py", "lab/risk.py",
                                                           "research/tools/net_report.py")}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(len(apply(C1, os.path.join(tmp, "1"))), 7)
            self.assertEqual(list(apply(C2, os.path.join(tmp, "2"))), ["copybot/lab/paper_runner.py"])
            self.assertEqual(list(apply(C3, os.path.join(tmp, "3"))), ["copybot/research/tools/net_report.py"])
        for p, h in before.items():
            self.assertEqual(sha(os.path.join(HERE, p)), h, p)
        self.assertEqual(sha(NET_REPORT), NET_REPORT_PIN)

    def test_candidate_1_is_exactly_72_then_81(self):
        from tests.test_observability_81 import stack
        with tempfile.TemporaryDirectory() as tmp:
            stacked, _ = stack(os.path.join(tmp, "s"))
            one = apply(C1, os.path.join(tmp, "c"))
            for rel, path in one.items():
                name = os.path.basename(rel)[:-3]
                self.assertEqual(sha(path), sha(stacked[name]), name)

    def test_the_readme_gives_the_order(self):
        with open(os.path.join(PATCHES, "83_candidate_README.md"), encoding="utf-8") as f:
            text = f.read()
        positions = [text.index(n) for n in (C1, C2, C3)]
        self.assertEqual(positions, sorted(positions))


class Base(unittest.TestCase):
    permanent = (".SPOT",)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab83")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pm = load("paper_runner_c83", apply(C2, os.path.join(self.tmp, "c2"))["copybot/lab/paper_runner.py"])
        self.nr = load("net_report_c83", apply(C3, os.path.join(self.tmp, "c3"))["copybot/research/tools/net_report.py"])
        self.nr_repo = load("net_report_repo83", NET_REPORT)
        self.path = os.path.join(self.tmp, "db", "lab.db")
        self.db = DB(self.path)
        self.addCleanup(lambda: self.db.close())
        for p in (mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True),
                  mock.patch("socket.getaddrinfo", no_network), mock.patch("socket.create_connection", no_network),
                  mock.patch("urllib.request.urlopen", no_network),
                  mock.patch.object(self.pm, "PERMANENT_UNAVAILABLE_SUFFIXES", self.permanent)):
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
        lane.retire(self.db, self.led, "source", "synthetic test stop", None, NOW + 60)

    def close(self, t, spot=None, perp=None):
        self.get.now, self.get.spot, self.get.perp = t, spot, perp
        return self.pm.close_ledger(self.db, self.led, self.led, self.get, t)

    def restart(self):
        self.db.close()
        self.db = DB(self.path)
        self.pm._HOURLY.clear()
        real._HOURLY.clear()

    def ro(self):
        con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        con.execute("PRAGMA query_only=ON")
        self.addCleanup(con.close)
        return con

    def row(self, mod, cutoff):
        rep = mod.build(self.ro(), cutoff, cutoff)
        return rep, [a for a in rep["accounts"] if a["ledger"] == self.led][0]

    def funding_rows(self, cutoff):
        return self.db.q("SELECT id, amount FROM sim_funding WHERE exp_id=? AND ts<=? ORDER BY id", self.led, cutoff)

    def post_event_ids(self):
        out = []
        for r in self.db.q("SELECT payload FROM events WHERE kind=? AND exp_id=? ORDER BY id", self.pm.POST_TERMINAL_FUNDING,
                           self.led):
            out += json.loads(r["payload"])["funding_ids"]
        return out


class PostTerminalReport(Base):
    def run_with_restart(self):
        self.close(T1)
        self.close(T2)
        self.restart()
        self.close(T2 + 60)
        self.close(T3)
        return int(T3 + 600)

    def test_post_terminal_funding_is_reported_apart_and_counted_once(self):
        cut = self.run_with_restart()
        rows = self.funding_rows(cut)
        ids = self.post_event_ids()
        self.assertEqual(len(ids), len(set(ids)))                      # recorded once, also after the restart
        rep, r = self.row(self.nr, cut)
        pt = r["post_terminal_funding"]
        self.assertTrue(pt["terminal"])
        self.assertEqual(pt["ids"], ids)
        self.assertFalse(pt["in_strategy_performance"])
        self.assertFalse(pt["validated"])
        self.assertAlmostEqual(r["funding"] + pt["amount"], sum(x["amount"] for x in rows))
        self.assertEqual(pt["rows"] + sum(1 for x in rows if x["id"] <= pt["cutoff_funding_id"]), len(rows))
        self.assertAlmostEqual(rep["summary"]["post_terminal_funding_total"], pt["amount"])
        self.assertEqual(rep["summary"]["post_terminal_accounts"], 1)
        self.assertAlmostEqual(r["at_mark"]["funding"] + r["after_mark"]["funding"], r["funding"])
        self.assertIn("Post-terminal funding (ikke strategi-performance, aldrig valideret)", self.nr.md(rep))

    def test_the_pinned_report_counts_it_as_strategy_funding(self):
        """Documents the fault the candidate removes (the repo's pinned net_report)."""
        cut = self.run_with_restart()
        _, r = self.row(self.nr_repo, cut)
        self.assertAlmostEqual(r["funding"], sum(x["amount"] for x in self.funding_rows(cut)))
        self.assertNotIn("post_terminal_funding", r)

    def test_the_report_is_reproducible(self):
        cut = self.run_with_restart()
        a = json.dumps(self.row(self.nr, cut)[0], sort_keys=True)
        self.restart()
        b = json.dumps(self.row(self.nr, cut)[0], sort_keys=True)
        self.assertEqual(a, b)

    def test_split_and_report_agree(self):
        cut = self.run_with_restart()
        split = self.pm.funding_split(self.db, self.led)
        _, r = self.row(self.nr, cut)
        self.assertEqual(split["post_terminal_ids"], r["post_terminal_funding"]["ids"])
        self.assertAlmostEqual(split["strategy"], r["funding"])


class LateSettlement(Base):
    def test_a_settlement_booked_after_terminal_but_settled_before_is_flagged(self):
        r = self.close(T1, perp=DNS)                       # fapi down: the 00:00 settlement is not booked yet
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        self.close(T2)                                     # fapi back: 00:00 and 08:00 are booked now
        (p,) = [json.loads(x["payload"]) for x in self.db.q("SELECT payload FROM events WHERE kind=? AND exp_id=?",
                                                            self.pm.POST_TERMINAL_FUNDING, self.led)]
        self.assertTrue(p["late_settlements"])
        self.assertTrue(all(ts < p["terminal_ts"] for _, ts in p["late_settlements"]))
        self.assertLess(len(p["late_settlements"]), len(p["funding_ids"]))
        split = self.pm.funding_split(self.db, self.led)
        self.assertEqual(len(split["late_settlement_ids"]), len(p["late_settlements"]))
        _, row = self.row(self.nr, int(T2 + 600))
        self.assertEqual(row["post_terminal_funding"]["late_settlements"], len(p["late_settlements"]))


class NotTerminal(Base):
    permanent = ()

    def test_a_retrying_close_changes_nothing_in_the_report(self):
        self.close(T1, spot=DNS)
        self.close(T2, spot=DNS)
        cut = int(T2 + 600)
        _, new = self.row(self.nr, cut)
        _, old = self.row(self.nr_repo, cut)
        self.assertFalse(new["post_terminal_funding"]["terminal"])
        self.assertAlmostEqual(new["funding"], old["funding"])
        self.assertAlmostEqual(new["at_mark"]["funding"], old["at_mark"]["funding"])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
