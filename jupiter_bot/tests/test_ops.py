import sqlite3
import tempfile
import unittest
from pathlib import Path

from jupiter_bot import ops
from jupiter_bot.core import Rejected
from jupiter_bot.marketdata.journal import Journal

NOW = 1_800_000_000.0


def status(**last_ok):
    rows = [{"source": s, "outcome": "OK", "n": 1, "last": t} for s, t in last_ok.items()]
    rows.append({"source": "binance_spot_klines", "outcome": "TRANSPORT_ERROR", "n": 5, "last": NOW})
    return {"outcomes": rows}


FRESH = {s: NOW - 60 for s in ops.MAX_AGE}


class Staleness(unittest.TestCase):
    def test_all_fresh_is_quiet(self):
        self.assertEqual(ops.stale_sources(status(**FRESH), NOW), [])

    def test_errors_do_not_count_as_ok(self):
        fresh = dict(FRESH, binance_spot_klines=NOW - 20 * 60)
        self.assertEqual(ops.stale_sources(status(**fresh), NOW), ["binance_spot_klines: no OK for 20 min"])

    def test_missing_source_is_never_ok(self):
        fresh = dict(FRESH)
        del fresh["jupiter_quote"]
        self.assertEqual(ops.stale_sources(status(**fresh), NOW), ["jupiter_quote: never OK"])

    def test_hourly_sources_get_three_hours(self):
        fresh = dict(FRESH, solana_status=NOW - 2 * 3600)
        self.assertEqual(ops.stale_sources(status(**fresh), NOW), [])


class Throttle(unittest.TestCase):
    def test_first_problem_alerts_then_stays_quiet(self):
        message, state = ops.decide({}, ["jupiter_quote: no OK for 20 min"], NOW)
        self.assertTrue(message.startswith("STALE"))
        message, state = ops.decide(state, ["jupiter_quote: no OK for 35 min"], NOW + 900)
        self.assertIsNone(message)
        message, _ = ops.decide(state, ["jupiter_quote: no OK for 6 h"], NOW + ops.RENOTIFY)
        self.assertTrue(message.startswith("STALE"))

    def test_new_source_alerts_again(self):
        _, state = ops.decide({}, ["jupiter_quote: x"], NOW)
        message, _ = ops.decide(state, ["binance_spot_klines: x", "jupiter_quote: x"], NOW + 60)
        self.assertIn("binance_spot_klines", message)

    def test_recovery_is_announced_once(self):
        _, state = ops.decide({}, ["jupiter_quote: x"], NOW)
        message, state = ops.decide(state, [], NOW + 60)
        self.assertIn("recovered", message)
        self.assertEqual(ops.decide(state, [], NOW + 120)[0], None)


class Backup(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.journal = self.root / "observations.db"
        Journal(self.journal).close()

    def tearDown(self):
        self.dir.cleanup()

    def test_copy_is_a_readable_journal_and_old_copies_are_pruned(self):
        dest = self.root / "backups"
        for day in range(4):
            ops.backup(self.journal, dest, keep=2, now=NOW + day * 86400)
        names = sorted(p.name for p in dest.iterdir())
        self.assertEqual(len(names), 2)
        self.assertTrue(all(ops.BACKUP_NAME.match(n) for n in names))
        Journal(dest / names[-1], readonly=True).close()

    def test_refuses_a_foreign_database(self):
        foreign = self.root / "copybot.db"
        db = sqlite3.connect(str(foreign))
        db.execute("CREATE TABLE t (x)")
        db.commit()
        db.close()
        with self.assertRaises(Rejected):
            ops.backup(foreign, self.root / "backups")
        self.assertFalse((self.root / "backups").exists())


if __name__ == "__main__":
    unittest.main()
