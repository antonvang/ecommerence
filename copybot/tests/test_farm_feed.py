"""PAPIR FEED (research/tools/farm_feed.py): the forward paper book as a static, script-free card feed, read-only.
Synthetic book only; no network."""
import hashlib
import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from research.tools import farm_dashboard as fd  # noqa: E402
from research.tools import farm_feed as ff  # noqa: E402
from test_farm_dashboard_live import build_book  # noqa: E402


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Feed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.db = os.path.join(cls.d, "event_farm_forward_feed.db")
        build_book(cls.db)
        cls.sha_before = sha(cls.db)
        cls.live = fd.read_forward(cls.db)
        cls.doc = ff.render(cls.live, now=1_800_000_000)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.d)

    def test_static_page_without_script_or_external_resources(self):
        self.assertNotRegex(self.doc, r"(?i)<script|\bon\w+\s*=|@import|url\(|https?://")
        self.assertIn("scroll-snap-type:y mandatory", self.doc)
        self.assertIn(ff.LABEL, self.doc)
        self.assertIn("Det er papir.", self.doc)

    def test_one_card_per_setup_newest_first_with_outcomes(self):
        groups = ff.setups(self.live)
        self.assertTrue(groups)
        self.assertEqual(sum(sum(g["status"].values()) for g in groups), len(self.live["trades"]))
        ts = [g["known_ts"] for g in groups]
        self.assertEqual(ts, sorted(ts, reverse=True))
        shown = min(len(groups), ff.MAX_CARDS)
        self.assertEqual(len(re.findall(r'<section class="card">', self.doc)), shown + 2)   # status + setups + end
        self.assertIn(f"1 / {shown}", self.doc)
        g = groups[0]
        self.assertIn(fd.px(g["entry"]), self.doc)
        self.assertIn(fd.px(g["stop"]), self.doc)
        for c in (g["chain"] or "").split(">"):
            if c:
                self.assertIn(f"#{c}", self.doc)

    def test_book_file_unchanged(self):
        ff.render(fd.read_forward(self.db))
        self.assertEqual(sha(self.db), self.sha_before)

    def test_no_book_gives_a_plain_card(self):
        doc = ff.render({"state": "missing", "path": "x"})
        self.assertIn("Bogen kan ikke vises", doc)
        self.assertIn("Det er papir.", doc)

    def test_cli_writes_only_the_out_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "feed.html")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(ff.main(["--forward-db", self.db, "--out", out]), 0)
            self.assertEqual(os.listdir(d), ["feed.html"])
        self.assertEqual(sha(self.db), self.sha_before)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401
    unittest.main()
