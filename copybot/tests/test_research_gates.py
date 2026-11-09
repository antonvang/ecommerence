"""PROTOCOL_V3 amendment 40: the quarantine register is pinned, api.upbit.com stays inside n4_kimchi.py, and research
tools read news/1 only through gates.news_rows, which keeps backfilled 2024+ rows out."""
import calendar
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
import gates  # noqa: E402

REGISTER = os.path.join(HERE, "research", "data", "QUARANTINE.json")
SCANNED = ("lab", "pilot", os.path.join("research", "tools"))


def unchanged(path, sha256):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest() == sha256


def py_files():
    for root in SCANNED:
        for dirpath, _, files in os.walk(os.path.join(HERE, root)):
            for f in files:
                if f.endswith(".py"):
                    p = os.path.join(dirpath, f)
                    with open(p, encoding="utf-8") as fh:
                        yield os.path.relpath(p, HERE), fh.read()


class Quarantine(unittest.TestCase):
    def setUp(self):
        with open(REGISTER, encoding="utf-8") as f:
            self.reg = json.load(f)

    def test_integrity_logic_on_a_generated_file(self):
        """Order 73: the pin check is tested on a generated file. A quarantined file is not opened, hashed or stat'ed."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "synthetic.json")
            with open(path, "wb") as f:
                f.write(b'{"synthetic": true}')
            pin = hashlib.sha256(b'{"synthetic": true}').hexdigest()
            self.assertTrue(unchanged(path, pin))
            with open(path, "ab") as f:
                f.write(b" ")
            self.assertFalse(unchanged(path, pin))

    def test_register_pins_every_listed_file_without_opening_it(self):
        files = [e for e in self.reg["entries"] if e.get("path")]
        self.assertTrue(files)
        with mock.patch("builtins.open", side_effect=AssertionError("opened")), \
                mock.patch("os.stat", side_effect=AssertionError("stat")):
            for e in files:
                self.assertRegex(e["sha256"], "^[0-9a-f]{64}$", e["id"])

    def test_no_test_names_a_quarantined_file(self):
        """test_research_gate_status only asserts that the tool refuses the path, under a mocked open."""
        names = [os.path.basename(e["path"]) for e in self.reg["entries"] if e.get("path")]
        tests = os.path.join(HERE, "tests")
        for f in sorted(os.listdir(tests)):
            if f.endswith(".py") and f != "test_research_gate_status.py":
                with open(os.path.join(tests, f), encoding="utf-8") as fh:
                    src = fh.read()
                for n in names:
                    self.assertNotIn(n, src, f)

    def test_every_entry_says_what_is_forbidden(self):
        for e in self.reg["entries"]:
            self.assertTrue(e["forbidden"] and e["deviation"] and e["sha256" if e.get("path") else "id"])
        ids = {e["id"] for e in self.reg["entries"]}
        self.assertIn("news-backfill-2024plus-exposure", ids)

    def test_no_tool_refers_to_a_quarantined_file(self):
        names = [os.path.basename(e["path"]) for e in self.reg["entries"] if e.get("path")]
        for rel, src in py_files():
            for n in names:
                self.assertNotIn(n, src, rel)


class UpbitHost(unittest.TestCase):
    def test_only_n4_kimchi_names_the_host(self):
        hits = [rel for rel, src in py_files() if "api.upbit.com" in src]
        self.assertEqual(hits, [os.path.join("research", "tools", "n4_kimchi.py")])


class NewsGate(unittest.TestCase):
    def test_research_tools_use_the_helper(self):
        for rel, src in py_files():
            if not rel.startswith(os.path.join("research", "tools")) or rel.endswith("gates.py"):
                continue
            if "news/1" in src:
                self.assertRegex(src, r"(from gates import|import gates)", rel)
                self.assertIn("news_rows(", src, rel)

    def test_holdout_constant(self):
        self.assertEqual(gates.HOLDOUT_START_TS, calendar.timegm((2024, 1, 1, 0, 0, 0)))

    def test_filters_backfilled_2024_plus(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE observations (ts INTEGER, detector TEXT, metric TEXT, payload TEXT)")
        rows = [("old", True, 1700000000), ("h2024", True, 1704067200), ("h2025", True, 1740000000),
                ("live", False, 1790000000), ("nodate", True, None), ("str", "False", 1790000001)]
        for i, (k, bf, pub) in enumerate(rows):
            con.execute("INSERT INTO observations VALUES (?, 'news/1', 'news_item', ?)",
                        (i, json.dumps({"key": k, "backfill": bf, "published_ts": pub})))
        con.execute("INSERT INTO observations VALUES (9, 'news/1', 'news_error', ?)",
                    (json.dumps({"key": "err", "backfill": False}),))
        got = [p["key"] for _, p in gates.news_rows(con)]
        self.assertEqual(got, ["old", "live", "str"])
        self.assertEqual([p["key"] for _, p in gates.news_rows(con, "news_error")], ["err"])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
