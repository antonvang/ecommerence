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

    def test_mini_chart_extends_to_the_last_exit_and_marks_it(self):
        bs = fd.BS_LIVE
        bars = [(1000 * bs + i * bs, 100.0, 101.0, 99.0, 100.5, 1.0) for i in range(200)]
        k_ts = bars[50][0] + bs                                    # known at the close of bar 50
        s = {"symbol": "BTCUSDT", "known_ts": k_ts, "dir": 1, "entry": 100.5, "stop": 99.0, "targets": {102.0},
             "exits": []}
        plain = ff.mini_chart(bars, s)
        self.assertEqual(plain.count("<rect"), ff.CHART_BEFORE + ff.CHART_AFTER)
        self.assertNotIn("<circle", plain)
        s["exits"] = [(bars[110][0] + bs, 99.0, "stop")]           # exit at the close of bar 110, 60 bars later
        doc = ff.mini_chart(bars, s)
        self.assertEqual(doc.count("<circle"), 1)
        self.assertIn(">stop</text>", doc)
        self.assertEqual(doc.count("<rect"), ff.CHART_BEFORE + (110 - 50) + 3)
        s["exits"] = [(bars[199][0] + bs, 99.0, "stop")]           # beyond CHART_AFTER_MAX: capped, marker dropped
        capped = ff.mini_chart(bars, s)
        self.assertLessEqual(capped.count("<rect"), ff.CHART_BEFORE + ff.CHART_AFTER_MAX)
        self.assertNotIn("<circle", capped)

    def test_liquidation_card_from_collector_db_read_only(self):
        import json
        from research.tools import fapi_collector as fc
        p = os.path.join(self.d, "positioning.db")
        db = fc.open_db(p)
        now = 1_800_000_000
        fc.start_ts(db, now - 7200)
        for k, (sym, side, usd) in enumerate([("BTCUSDT", "SELL", 2_500_000.0), ("ETHUSDT", "BUY", 40_000.0),
                                               ("SOLUSDT", "SELL", 10_000.0)]):
            ev = {"e": "forceOrder", "E": (now - 600 * (k + 1)) * 1000,
                  "o": {"s": sym, "S": side, "o": "LIMIT", "q": "1", "p": str(usd), "ap": str(usd), "X": "FILLED",
                        "z": "1", "T": 0}}
            fc.store_liquidation(db, json.dumps(ev), now, now - 7200)
        db.execute("INSERT INTO calls VALUES (?, 'rest', 'x', 200, 1, 1, NULL)", (now - 120,))
        db.commit()
        db.close()
        before = sha(p)
        liq = ff.read_liq(p, now)
        self.assertEqual((liq["n"], liq["symbols"]), (3, 3))
        self.assertAlmostEqual(liq["last_h"][0], 2_510_000.0)
        self.assertEqual(liq["top"][0][1], "BTCUSDT")
        doc = ff.render(self.live, now=now, liq=liq)
        self.assertIn("LIKVIDE<span>RINGER</span>", doc)
        self.assertIn("KUN OBSERVATION", doc)
        self.assertIn("2.5 mio USDT", doc)
        self.assertNotRegex(doc, r"(?i)<script|\bon\w+\s*=|@import|url\(|https?://")
        self.assertEqual(sha(p), before)
        self.assertIsNone(ff.read_liq(os.path.join(self.d, "nope.db"), now))

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
                self.assertEqual(ff.main(["--forward-db", self.db, "--out", out, "--liq-db", ""]), 0)
            self.assertEqual(os.listdir(d), ["feed.html"])
        self.assertEqual(sha(self.db), self.sha_before)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401
    unittest.main()
