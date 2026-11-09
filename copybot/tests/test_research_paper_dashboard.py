"""Director order 59-H P2: PAPER DASHBOARD V2 is read-only, static, honest about STALE/MISSING_MARK and drops no fills."""
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import paper_dashboard as pd  # noqa: E402

CUT = 1794182400          # 2026-11-09 00:00:00 UTC
GEN = CUT + 2280


def make_db(equity=(), fills=(), events=(), ledgers=None):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "lab.db")
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE events (id INTEGER PRIMARY KEY, ts INTEGER, kind TEXT, exp_id TEXT, payload TEXT);
        CREATE TABLE sim_equity (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, equity REAL, cash REAL,
                                 exposure REAL, peak REAL, drawdown REAL);
        CREATE TABLE sim_fills (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, order_id TEXT, instrument TEXT,
                                side TEXT, px REAL, qty REAL, fee REAL, mid REAL);
        CREATE TABLE sim_funding (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, instrument TEXT, amount REAL);
    """)
    for led, src in (ledgers if ledgers is not None else sorted({(q[0], "straks") for q in equity})):
        con.execute("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, 'lane.started', ?, ?)",
                    (CUT - 30 * 86400, led, json.dumps({"source": src, "name": led})))
        con.execute("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, 'paper.started', ?, ?)",
                    (CUT - 30 * 86400, led, json.dumps({"capital": 10000})))
    con.executemany("INSERT INTO sim_equity (exp_id, ts, equity, cash, exposure, peak, drawdown) "
                    "VALUES (?, ?, ?, 0, 0, 0, 0.0123)", equity)
    con.executemany("INSERT INTO sim_fills (exp_id, ts, order_id, instrument, side, px, qty, fee, mid) "
                    "VALUES (?, ?, 'o', ?, ?, ?, ?, ?, NULL)", fills)
    con.executemany("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, ?, ?, ?)",
                    [(ts, k, led, json.dumps(pl)) for ts, k, led, pl in events])
    con.commit()
    con.close()
    return p


def render(p, feed_n=200, cutoff=CUT):
    con = pd.connect_ro(p)
    try:
        return pd.render(con, GEN, cutoff, p, feed_n)
    finally:
        con.close()


def card(doc, led):
    m = re.search(r'<article class="bot b-%s [^"]*">(.*?)</article>' % re.escape(led), doc, re.S)
    assert m, led
    return m.group(0)


LEDGERS = [("FRESHUP", "straks"), ("FRESHDN", "pairs"), ("OLD", "carry90"), ("NOMARK", "lane")]
EQUITY = [("FRESHUP", CUT - 7200, 10000.0), ("FRESHUP", CUT - 600, 10031.85),
          ("FRESHDN", CUT - 3600, 10000.0), ("FRESHDN", CUT - 3541, 9893.28),
          ("OLD", CUT - 90000, 10000.0), ("OLD", CUT - 62000, 9990.0)]
FILLS = [("FRESHUP", CUT - 7000, "BTCUSDT", "buy", 100.0, 1.0, 0.04),
         ("FRESHUP", CUT - 300, "BTCUSDT", "sell", 101.0, 1.0, 0.04),
         ("FRESHDN", CUT - 3 * 86400, "ETHUSDT", "sell", 2000.0, 0.5, 0.4),
         ("OLD", CUT - 20 * 86400, "XAUUSDT", "buy", 2400.0, 0.1, 0.1),
         ("OLD", CUT + 600, "XAUUSDT", "sell", 2400.0, 0.1, 0.1)]          # after the cutoff: never shown
EVENTS = [(CUT - 1200, "straks.skipped", "FRESHUP", {"instrument": "USDBRLUSDT", "reason": "ingen retning"}),
          (CUT - 2 * 86400, "paper.skipped", "OLD", {"coin": "ADAUSDT", "reason": "likviditetsregel (31)"}),
          (CUT - 100, "lane.skipped", "NOT_SHOWN", {"coin": "ARIAUSDT", "reason": "ikke EU-handelbar (30a)"})]


class Dashboard(unittest.TestCase):
    def setUp(self):
        self.p = make_db(EQUITY, FILLS, EVENTS, LEDGERS)
        self.doc = render(self.p)

    def test_fresh_stale_missing_cards(self):
        up = card(self.doc, "FRESHUP")
        self.assertIn('class="chip c-FRESH">FRESH', up)
        old = card(self.doc, "OLD")
        self.assertIn("c-STALE", old)
        self.assertIn("Forældet — mærket 11-08 06:46 UTC, 17.2 t", old)
        self.assertIn("sidst kendt, ikke aktuel", old)
        nm = card(self.doc, "NOMARK")
        self.assertIn('class="chip c-MISSING_MARK">MISSING_MARK', nm)
        self.assertNotIn("bnet pos", nm)
        self.assertIn("MANGLER MÆRKNING: 1", self.doc)
        self.assertNotIn("health h-ok", self.doc)

    def test_net_colours(self):
        self.assertIn('bnet pos">+31.85', card(self.doc, "FRESHUP"))
        self.assertIn('bnet neg">−106.72', card(self.doc, "FRESHDN"))
        self.assertIn('bnet neg">−10.00', card(self.doc, "OLD"))

    def test_top_cards_no_current_total_when_stale_or_missing(self):
        self.assertIn('id="portfolio">Ikke tilgængelig', self.doc)
        self.assertIn("1 konti STALE / 1 MISSING_MARK", self.doc)
        self.assertIn("−74.87</div><div class=\"sub\">2 af 4 konti", self.doc)
        self.assertIn("Sidst kendt netto, STALE-konti", self.doc)
        self.assertIn("<b>Ikke aktuel</b>", self.doc)

    def test_current_total_when_all_fresh(self):
        p = make_db([("A", CUT - 60, 10005.0), ("B", CUT - 7200, 9997.0)], ledgers=[("A", "straks"), ("B", "pairs")])
        doc = render(p)
        self.assertIn('id="portfolio">+2.00', doc)
        self.assertIn("ALLE MÆRKER FRISKE", doc)

    def test_empty_db_renders_without_fake_total(self):
        p = make_db(ledgers=[])
        doc = render(p)
        self.assertIn('id="portfolio">Ikke tilgængelig', doc)
        self.assertIn("ingen konti i lab.db", doc)
        self.assertIn("INGEN DATA", doc)
        self.assertIn("Ingen registrerede papirhændelser", doc)
        self.assertNotIn("health h-ok", doc)

    def test_accounts_without_fills_or_marks(self):
        p = make_db(ledgers=[("X", "straks"), ("Y", "lane")])
        doc = render(p)
        self.assertIn('id="portfolio">Ikke tilgængelig', doc)
        self.assertIn("0 konti STALE / 2 MISSING_MARK", doc)
        self.assertEqual(doc.count('class="chip c-MISSING_MARK"'), 2)
        self.assertNotIn('class="ev ', doc)

    def test_every_fill_in_window_is_in_feed(self):
        fills = [("FRESHUP", CUT - 60 * i, "BTCUSDT", "buy" if i % 2 else "sell", 100.0 + i, 0.01 * i, 0.001)
                 for i in range(1, 151)]
        p = make_db(EQUITY, fills, (), LEDGERS)
        doc = render(p)
        rows = re.findall(r'<div class="ev [^"]*\bfill\b[^"]*"', doc)
        self.assertEqual(len(rows), 150)
        self.assertIn("150 nyeste af 150 registrerede", doc)
        for i in range(1, 151):
            self.assertIn(f"{0.01 * i:.6g} @ {100.0 + i:.6g}", doc)

    def test_feed_counts_and_cutoff(self):
        fills = re.findall(r'<div class="ev [^"]*\bfill\b', self.doc)
        self.assertEqual(len(fills), 4)                                   # the post-cutoff fill is excluded
        self.assertIn("6 nyeste af 6 registrerede hændelser til cutoff (4 fyld, 2 ", self.doc)
        self.assertIn("gebyr −0.4000", self.doc)
        doc = render(self.p, feed_n=2)
        self.assertEqual(len(re.findall(r'<div class="ev ', doc)), 2)
        self.assertIn("2 nyeste af 6 registrerede", doc)
        order = re.findall(r'<span class="t">([^<]+)</span>', self.doc)
        self.assertEqual(order, sorted(order, reverse=True))

    def test_skip_events_shown_only_for_shown_ledgers(self):
        self.assertIn("straks.skipped: ingen retning", self.doc)
        self.assertIn("paper.skipped: likviditetsregel (31)", self.doc)
        self.assertNotIn("ARIAUSDT", self.doc)
        self.assertIn("SPRUNGET OVER", self.doc)

    def test_period_classes(self):
        rows = re.findall(r'<div class="(ev [^"]*)"[^>]*><span class="t">([^<]+)<', self.doc)
        got = {t: c.split() for c, t in rows}
        recent = [c for t, c in got.items() if t.startswith("2026-11-08 23")]
        self.assertTrue(recent and all("in24" in c and "in7" in c for c in recent))
        three = [c for c, t in rows if t.startswith("2026-11-06")]
        self.assertTrue(three and all("in7" in c.split() and "in24" not in c.split() for c in three))
        self.assertIn("#fp-24:checked~.wrap .ev:not(.in24)", self.doc)

    def test_paper_badge_and_disclaimer(self):
        self.assertIn("PAPER / SIMULATION — ingen rigtige penge", self.doc)
        self.assertIn("Live-handel: <b>NO-GO</b>", self.doc)
        self.assertIn("mode=ro", self.doc)

    def test_static_no_scripts_no_urls_no_buttons(self):
        low = self.doc.lower()
        for bad in ("<script", "http://", "https://", "fetch(", "xmlhttprequest", "eval(", "<button", "<form",
                    "@import", "url(", "<link", "<img", "<iframe", "src="):
            self.assertNotIn(bad, low, bad)

    def test_db_untouched_and_connection_read_only(self):
        with open(self.p, "rb") as f:
            h0 = hashlib.sha256(f.read()).hexdigest()
        out = os.path.join(os.path.dirname(self.p), "dash.html")
        pd.main(["--db", self.p, "--cutoff", "2026-11-09T00:00:00Z", "--out", out], now=GEN)
        with open(self.p, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h0)
        con = pd.connect_ro(self.p)
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM sim_equity")
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("INSERT INTO events (ts, kind) VALUES (1, 'x')")
        con.close()

    def test_deterministic(self):
        self.assertEqual(render(self.p), self.doc)
        d = os.path.dirname(self.p)
        a, b = os.path.join(d, "a.html"), os.path.join(d, "b.html")
        pd.main(["--db", self.p, "--cutoff", "2026-11-09T00:00:00Z", "--out", a], now=GEN)
        pd.main(["--db", self.p, "--cutoff", "2026-11-09T00:00:00Z", "--out", b], now=GEN)
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())
        self.assertIn("Genereret:</b> 2026-11-09 00:38:00 UTC", self.doc)

    def test_html_escaping(self):
        p = make_db(EQUITY, (), [(CUT - 10, "straks.skipped", "FRESHUP",
                                  {"instrument": "<b>X</b>", "reason": "<script>alert(1)</script>"})], LEDGERS)
        doc = render(p)
        self.assertNotIn("<script", doc.lower())
        self.assertIn("&lt;script&gt;", doc)


if __name__ == "__main__":
    unittest.main()
