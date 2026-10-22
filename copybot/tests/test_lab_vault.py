"""research/LINUX_DRIFT.md 2026-10-22: the read-only Obsidian vault. Notes per hypothesis, amendment, ledger,
experiment and daily report; only Lab/ is written; the user's own notes are never touched; at most hourly and only for
the lab's own registry. Temporary databases and directories only; no network."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, hypogen, news, vault  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402

NOW = int(datetime(2026, 10, 22, 15, tzinfo=timezone.utc).timestamp())
PROTOCOL = """# Protokol

## Ændring 10d og 11b (2026-10-20): banen må hente data — før kode

Tekst om 10d.

## Ændring 17c (2026-10-22): margin-mønter fra titlen — før kode

Tekst om 17c.

### Præcisering af ændring 17c (2026-10-22): hører til 17c

## Rettelse 2026-10-21 til ændring 12e

Ikke en ændring.
"""


class Vault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labvault")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.root = os.path.join(self.tmp, "vault")
        self.p = [mock.patch.object(data, "CACHE", os.path.join(self.tmp, "cache")),
                  mock.patch.object(hypogen, "DIR", os.path.join(self.tmp, "hypotheses")),
                  mock.patch.object(hypogen, "cached_locks", lambda db, now=None: [])]
        for p in self.p:
            p.start()
        hypogen._CACHE.clear()
        it = news.item("binance", "m1", "https://www.binance.com/x", "Cross Margin Trading for FIL Enabled on Binance",
                       NOW - 400 * 86400, "binance_news", NOW, backfill=True)
        news.store(self.db, [it], news.BINANCE, NOW)
        for o in ("ar_1d", "far_7d"):
            self.db.event(hypogen.EV_SCREEN, "agent:cost-1", None, {"key": f"margin|{o}|m17", "verdict": "UNTESTABLE",
                                                                    "reason": "0 events with data (< 15)", "n": 0})
        self.db.event(hypogen.EV_SCREEN, "agent:cost-1", None, {
            "key": "margin|far_7d|m17c", "verdict": "SCREEN_FAIL", "reason": "failed: p <= 0.005", "n": 93,
            "mean": -0.0737, "median": -0.089, "p": 0.0044, "rule": hypogen.RULE_C, "method": hypogen.M17C})
        self.db.event("research.lane_report", "system:report-1", None, {"day": "2026-10-21", "accounts": 8,
                                                                        "net_total": -139.7, "met": []})

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_amendments_are_read_from_the_protocol_headings(self):
        am = vault.amendments(PROTOCOL)
        self.assertEqual([(a, d) for a, d, _, _ in am], [("10d og 11b", "2026-10-20"), ("17c", "2026-10-22")])
        self.assertIn("### Præcisering af ændring 17c", am[1][3])          # a clarification stays with its amendment
        self.assertNotIn("Rettelse", am[1][3])

    def test_notes_link_hypotheses_amendments_reports_and_the_index(self):
        n = vault.notes(self.db, NOW, PROTOCOL)
        h = n["Hypoteser/margin far_7d m17c.md"]
        self.assertIn("[[Ændring 17c]]", h)
        self.assertIn("SCREEN_FAIL", h)
        self.assertIn("-7.37 %", h)
        self.assertIn("Ændringer/Ændring 17c.md", n)
        self.assertIn("Tekst om 17c.", n["Ændringer/Ændring 17c.md"])
        self.assertIn("Rapporter/Bane 2026-10-21.md", n)
        self.assertIn("[[Type margin]]", n["Copybot.md"])
        self.assertIn("[[Bane 2026-10-21]]", n["Copybot.md"])
        self.assertTrue(all("Kun visning" in t for t in n.values()))

    def test_only_lab_is_written_and_the_users_notes_are_kept(self):
        mine = os.path.join(self.root, "Mine idéer.md")
        os.makedirs(self.root)
        with open(mine, "w") as f:
            f.write("min note\n")
        stale = os.path.join(self.root, vault.SUB, "Konti", "LANE_gone.md")
        os.makedirs(os.path.dirname(stale))
        with open(stale, "w") as f:
            f.write("old\n")
        r = vault.write(self.db, self.root, NOW, PROTOCOL)
        self.assertEqual(r["removed"], 1)
        self.assertFalse(os.path.exists(stale))
        with open(mine) as f:
            self.assertEqual(f.read(), "min note\n")
        self.assertTrue(os.path.exists(os.path.join(self.root, vault.SUB, "Copybot.md")))
        self.assertEqual(vault.write(self.db, self.root, NOW, PROTOCOL)["written"], 0)   # unchanged: nothing rewritten

    def test_at_most_hourly_and_only_for_the_labs_own_registry(self):
        self.assertIsNone(vault.maybe_write(self.db, NOW))                  # a temporary registry: never
        with mock.patch.object(vault, "PROTOCOL", os.path.join(self.tmp, "P.md")):
            with open(vault.PROTOCOL, "w") as f:
                f.write(PROTOCOL)
            self.assertGreater(vault.maybe_write(self.db, NOW, root=self.root)["notes"], 5)
            self.assertIsNone(vault.maybe_write(self.db, NOW + 600, root=self.root))
            self.assertIsNotNone(vault.maybe_write(self.db, NOW + 3600, root=self.root))
            with mock.patch.object(vault, "write", side_effect=RuntimeError("boom")):
                self.assertEqual(vault.maybe_write(self.db, NOW + 7300, root=self.root),
                                 {"error": "RuntimeError('boom')"})

    def test_strategy_pass_reports_it_and_writes_nothing_for_a_test_registry(self):
        with mock.patch.object(vault, "ROOT", os.path.join(self.tmp, "never")):
            out = fleet.strategy_pass(self.db)
        self.assertIn("vault", out)
        self.assertIsNone(out["vault"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "never")))
        json.dumps(out)


if __name__ == "__main__":
    unittest.main()
