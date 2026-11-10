"""Director order 82 point 1: research/desk/patches/82_close_post_terminal_funding.diff on a temporary copy of
lab/paper_runner.py. Funding on an open perp leg is still booked after CLOSE_INCOMPLETE_TERMINAL, recorded apart as
post-terminal funding and kept out of the strategy's performance. No row is deleted or booked twice. Synthetic only."""
import hashlib
import json
import os
import shutil
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

PATCH = os.path.join(HERE, "research", "desk", "patches", "82_close_post_terminal_funding.diff")
TARGET = os.path.join(HERE, "lab", "paper_runner.py")
T1, T2, T3 = NOW + 4 * HOUR, NOW + 12 * HOUR, NOW + 20 * HOUR   # after the 00:00, 08:00 and 16:00 UTC settlements


def apply(tmp):
    with open(PATCH, encoding="utf-8") as f:
        return apply_unified(f.read(), os.path.dirname(HERE), tmp)


class Base(unittest.TestCase):
    permanent = (".SPOT",)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lab82")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pm = load("paper_runner_patched82", apply(self.tmp)["copybot/lab/paper_runner.py"])
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

    def funding_ids(self):
        return [r["id"] for r in self.db.q("SELECT id FROM sim_funding WHERE exp_id=? ORDER BY id", self.led)]

    def total(self):
        return self.db.one("SELECT COALESCE(SUM(amount), 0) FROM sim_funding WHERE exp_id=?", self.led)[0]

    def posts(self):
        return [json.loads(r["payload"]) for r in self.db.q(
            "SELECT payload FROM events WHERE kind=? AND exp_id=? ORDER BY id", self.pm.POST_TERMINAL_FUNDING, self.led)]


class Isolated(unittest.TestCase):
    def test_touches_only_paper_runner_and_the_repo_is_unpatched(self):
        with open(TARGET, "rb") as f:
            before = hashlib.sha256(f.read()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(apply(tmp)), ["copybot/lab/paper_runner.py"])
        with open(TARGET, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), before)
        self.assertFalse(hasattr(real, "POST_TERMINAL_FUNDING"))


class PostTerminal(Base):
    def test_terminal_records_the_funding_cutoff(self):
        r = self.close(T1)
        self.assertEqual(r["close_state"], self.pm.INCOMPLETE_TERMINAL)
        s = json.loads(self.db.one("SELECT payload FROM events WHERE kind=? AND exp_id=? ORDER BY id DESC LIMIT 1",
                                   self.pm.CLOSE_STATE, self.led)["payload"])
        self.assertTrue(self.funding_ids())                # the 00:00 settlement was booked before the state
        self.assertEqual(s["funding_id_at_terminal"], max(self.funding_ids()))
        self.assertEqual(s["terminal_ts"], int(T1))

    def test_funding_after_terminal_is_booked_kept_and_recorded_apart(self):
        self.close(T1)
        before_ids, before_total = self.funding_ids(), self.total()
        r = self.close(T2)                     # past the 08:00 UTC settlement
        new = [i for i in self.funding_ids() if i not in before_ids]
        self.assertTrue(new)
        self.assertEqual(r["post_terminal_funding_rows"], len(new))
        (p,) = self.posts()
        self.assertEqual(p["funding_ids"], new)
        self.assertFalse(p["in_strategy_performance"])
        self.assertEqual(p["close_state"], self.pm.INCOMPLETE_TERMINAL)
        split = self.pm.funding_split(self.db, self.led)
        self.assertTrue(split["terminal"])
        self.assertEqual(split["post_terminal_ids"], new)
        self.assertAlmostEqual(split["strategy"], before_total)
        self.assertAlmostEqual(split["strategy"] + split["post_terminal"], self.total())
        self.assertEqual(split["rows"], len(self.funding_ids()))
        self.assertEqual(self.funding_ids()[:len(before_ids)], before_ids)     # nothing removed

    def test_repeats_and_restarts_book_and_record_nothing_twice(self):
        self.close(T1)
        self.close(T2)
        ids, posts = self.funding_ids(), self.posts()
        self.close(T2 + 60)
        self.db.close()
        self.db = DB(self.path)
        self.pm._HOURLY.clear()
        real._HOURLY.clear()
        self.close(T2 + 120)
        self.assertEqual(self.funding_ids(), ids)
        self.assertEqual(self.posts(), posts)

    def test_a_later_settlement_gets_its_own_record(self):
        self.close(T1)
        self.close(T2)
        self.close(T3)                        # past the 16:00 UTC settlement
        a, b = self.posts()
        self.assertFalse(set(a["funding_ids"]) & set(b["funding_ids"]))
        self.assertGreater(b["first_funding_id"], a["last_funding_id"])
        split = self.pm.funding_split(self.db, self.led)
        self.assertEqual(split["post_terminal_ids"], a["funding_ids"] + b["funding_ids"])

    def test_no_book_order_or_mark_after_terminal(self):
        self.close(T1)
        n = {t: self.db.one(f"SELECT COUNT(*) FROM {t} WHERE exp_id=?", self.led)[0]
             for t in ("sim_orders", "sim_fills", "sim_equity")}
        self.close(T2)
        self.assertEqual(n, {t: self.db.one(f"SELECT COUNT(*) FROM {t} WHERE exp_id=?", self.led)[0] for t in n})


class NotTerminal(Base):
    permanent = ()

    def test_a_retrying_close_has_no_post_terminal_funding(self):
        self.close(NOW + HOUR, spot=DNS, perp=DNS)
        self.close(NOW + 4 * HOUR, spot=DNS, perp=DNS)
        self.assertEqual(self.posts(), [])
        split = self.pm.funding_split(self.db, self.led)
        self.assertFalse(split["terminal"])
        self.assertAlmostEqual(split["strategy"], self.total())
        self.assertEqual(split["post_terminal_ids"], [])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
