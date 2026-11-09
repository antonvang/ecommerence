"""Director orders 59-H P2 and 59-J: PAPER DASHBOARD V2 is read-only, static, honest about STALE/MISSING_MARK, drops no
fills, orders cards FRESH/STALE/MISSING_MARK, numbers duplicate names consistently and splits fills from skips."""
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
    for spec in (ledgers if ledgers is not None else sorted({(q[0], "straks") for q in equity})):
        led, src = spec[0], spec[1]
        name = spec[2] if len(spec) > 2 else led
        t0 = spec[3] if len(spec) > 3 else CUT - 30 * 86400
        con.execute("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, 'lane.started', ?, ?)",
                    (t0, led, json.dumps({"source": src, "name": name})))
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
        self.assertIn('bnet old">−10.00', card(self.doc, "OLD"))         # order 69: a STALE net is grey

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
        for key in ("fill", "other"):
            box = re.search(r'<div class="feedbox fb-%s">(.*?)</div>\n?(?=<h3|</section>)' % key, self.doc, re.S)
            order = re.findall(r'<span class="t">([^<]+)</span>', box.group(1))
            self.assertTrue(order)
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

    # --- director order 59-J ---
    def test_cards_ordered_fresh_stale_missing(self):
        leds = re.findall(r'<article class="bot b-([^ ]+) s-([A-Z_]+)">', self.doc)
        self.assertEqual(leds, [("FRESHDN", "FRESH"), ("FRESHUP", "FRESH"), ("OLD", "STALE"),
                                ("NOMARK", "MISSING_MARK")])
        chips = re.findall(r'<label class="pill" for="fb-([^"]+)">', self.doc)
        self.assertEqual(chips, ["all", "FRESHDN", "FRESHUP", "OLD", "NOMARK"])

    def test_duplicate_names_numbered_consistently(self):
        led = [("Z9", "lane", "carry_floor", CUT - 10 * 86400), ("A1", "lane", "carry_floor", CUT - 20 * 86400),
               ("M5", "lane", "carry_floor", CUT - 20 * 86400), ("S", "straks", "straks", CUT - 5 * 86400)]
        eq = [("Z9", CUT - 60, 10001.0), ("A1", CUT - 60, 10002.0), ("M5", CUT - 9000, 9999.0),
              ("S", CUT - 60, 10000.0)]
        fl = [("Z9", CUT - 100, "BTCUSDT", "buy", 1.0, 1.0, 0.01), ("A1", CUT - 200, "ETHUSDT", "buy", 1.0, 1.0, 0.01),
              ("M5", CUT - 300, "SOLUSDT", "buy", 1.0, 1.0, 0.01)]
        ev = [(CUT - 400, "paper.skipped", "M5", {"coin": "ADAUSDT", "reason": "r"})]
        doc = render(make_db(eq, fl, ev, led))
        want = {"A1": "carry_floor #1", "M5": "carry_floor #2", "Z9": "carry_floor #3"}   # by start, then ledger id
        for lid, lab in want.items():
            c = card(doc, lid)
            self.assertIn(f'<div class="bname">{lab}</div><div class="bled">{lid}</div>', c)
            self.assertIn(f'<label class="pill" for="fb-{lid}">{lab}</label>', doc)
            rows = re.findall(r'<div class="ev [^"]*\bb-%s\b[^"]*"[^>]*>.*?<span class="who">([^<]*)</span>' % lid, doc)
            self.assertTrue(rows, lid)
            self.assertEqual(set(rows), {lab})
        self.assertIn('<div class="bname">straks</div>', doc)                         # unique name: no number
        self.assertNotIn("straks #", doc)
        self.assertNotIn('class="who">carry_floor<', doc)
        leds = re.findall(r'<article class="bot b-([^ ]+) s-', doc)
        self.assertEqual(leds, ["A1", "Z9", "S", "M5"])                              # FRESH by name/start, then STALE
        p2 = make_db(eq, fl, ev, list(reversed(led)))                                # insertion order irrelevant
        strip = lambda h: re.sub(r"<b>Datakilde:</b> [^ ]+", "", h)  # noqa: E731
        self.assertEqual(strip(doc), strip(render(p2)))

    def test_snapshot_banner(self):
        m = re.search(r'<div class="banner" id="snapshot"><b>Statisk snapshot genereret '
                      r'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC)\. Kør kommandoen igen for nye tal\.</b>', self.doc)
        self.assertTrue(m)
        self.assertEqual(m.group(1), "2026-11-09 00:38:00 UTC")
        code = re.search(r"<code>(.*?)</code>", self.doc).group(1)
        self.assertEqual(re.sub(r"<[^>]+>", "", code), "python3 research/tools/paper_dashboard.py --out &lt;fil&gt;")
        self.assertIn("Datacutoff: <b>2026-11-09 00:00:00 UTC</b>", self.doc)
        self.assertLess(self.doc.index('id="snapshot"'), self.doc.index('class="tops"'))

    def test_explanation_box(self):
        box = re.search(r'<section class="howto" id="howto">(.*?)</section>', self.doc, re.S).group(1)
        self.assertIn("Sådan læses tallene", box)
        self.assertIn("<b>Netto</b> = seneste equity-mærke minus startkapital", box)
        self.assertIn("seneste timemærke på eller før cutoff", box)
        self.assertIn("<b>FRESH</b> = mærket er højst 2 t gammelt ved cutoff", box)
        self.assertIn("<b>STALE</b> = mærket er ældre; tallet er den sidst kendte værdi og ikke aktuelt", box)
        self.assertIn("<b>MISSING_MARK</b> = intet mærke før cutoff", box)
        self.assertIn("Funding, gebyrer og fyld kan ligge senere end mærket", box)
        self.assertIn("uden gearing og uden marginmodel", box)

    def test_feed_split_keeps_every_row(self):
        fill_box = re.search(r'<div class="feedbox fb-fill">(.*?)</div>\n?(?=<h3)', self.doc, re.S).group(1)
        other_box = re.search(r'<div class="feedbox fb-other">(.*?)</div>\n?</section>', self.doc, re.S).group(1)
        fills = re.findall(r'<div class="(ev [^"]*)" data-kind="([^"]+)"', fill_box)
        other = re.findall(r'<div class="(ev [^"]*)" data-kind="([^"]+)"', other_box)
        self.assertEqual(len(fills), 4)
        self.assertEqual(len(other), 2)
        self.assertTrue(all(k == "fill" and "fill" in c.split() for c, k in fills))
        self.assertTrue(all(k != "fill" and "skip" in c.split() and "fill" not in c.split() for c, k in other))
        self.assertIn("Udførte papirhandler</span><small>4 viste af 4 til cutoff", self.doc)
        self.assertIn("Spring over / afvisninger / fejl</span><small>2 viste af 2 til cutoff", self.doc)
        self.assertIn("6 nyeste af 6 registrerede hændelser til cutoff (4 fyld, 2 ", self.doc)
        self.assertLess(self.doc.index('id="feed-fill"'), self.doc.index('id="feed-other"'))
        doc = render(self.p, feed_n=3)                                     # a cut feed still states both totals
        self.assertIn("3 nyeste af 6 registrerede", doc)
        self.assertIn("viste af 4 til cutoff", doc)
        self.assertIn("viste af 2 til cutoff", doc)
        self.assertEqual(len(re.findall(r'<div class="ev ', doc)), 3)
        err = render(make_db(EQUITY, (), [(CUT - 5, "paper.error", "FRESHUP", {"error": "boom"})], LEDGERS))
        self.assertRegex(err, r'<div class="ev [^"]*\berr\b[^"]*" data-kind="paper.error">')
        self.assertIn("Ingen udførte papirhandler blandt de viste.", err)

    def test_twelve_accounts_all_shown(self):
        led, eq = [], []
        for i in range(12):
            lid = f"L{i:02d}"
            led.append((lid, "lane", "carry_floor" if i < 5 else f"bot{i}", CUT - (40 - i) * 86400))
            if i % 3 == 0:
                eq.append((lid, CUT - 600, 10000.0 + i))                 # FRESH
            elif i % 3 == 1:
                eq.append((lid, CUT - 30000, 10000.0 - i))               # STALE
        doc = render(make_db(eq, (), (), led))
        arts = re.findall(r'<article class="bot b-([^ ]+) s-([A-Z_]+)">', doc)
        self.assertEqual(len(arts), 12)
        self.assertEqual({a for a, _ in arts}, {f"L{i:02d}" for i in range(12)})
        st = [s for _, s in arts]
        self.assertEqual(st, sorted(st, key=pd.RANK.get))
        self.assertEqual(st.count("FRESH"), 4)
        self.assertEqual(st.count("STALE"), 4)
        self.assertEqual(st.count("MISSING_MARK"), 4)
        self.assertEqual(len(re.findall(r'<label class="pill" for="fb-L\d\d">', doc)), 12)
        self.assertEqual(sorted(re.findall(r'carry_floor #(\d)<', doc)), sorted(["1", "2", "3", "4", "5"] * 2))
        self.assertIn("12 papirkonti", doc)
        self.assertIn('id="portfolio">Ikke tilgængelig', doc)

    def test_stale_never_styled_as_current(self):
        old = card(self.doc, "OLD")
        self.assertNotIn("c-FRESH", old)
        self.assertNotIn(">FRESH<", old)
        self.assertNotIn("spark pos", old)
        self.assertNotIn("spark neg", old)
        self.assertIn("sidst kendt, ikke aktuel", old)
        self.assertIn('class="bnet old"', old)                          # order 69: grey, never green/red
        self.assertNotRegex(old, r'bnet (pos|neg)')
        self.assertNotRegex(self.doc, r'id="portfolio">[+−±]')
        self.assertNotIn("alle 4 konti FRESH", self.doc)
        self.assertNotIn("ALLE MÆRKER FRISKE", self.doc)
        only_stale = render(make_db([("A", CUT - 30000, 10050.0)], ledgers=[("A", "straks")]))
        self.assertIn('id="portfolio">Ikke tilgængelig', only_stale)
        self.assertNotIn("c-FRESH", card(only_stale, "A"))
        self.assertIn("FORÆLDEDE MÆRKER: 1", only_stale)

    def test_numbers_and_timestamps_unchanged_from_59h_render(self):
        """Golden values taken from the 59-H render of this synthetic DB (before 59-J): the same numbers appear."""
        tok = re.compile(r"[+−±][\d,]+\.\d\d|\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC|\d\d-\d\d \d\d:\d\d(?::\d\d)? UTC|"
                         r"\d+\.\d t\b|\d+(?:\.\d+)?(?:e[+-]?\d+)? @ \d+(?:\.\d+)?|gebyr −[\d.]+|\d+\.\d\d%")

        def toks(h):
            return tok.findall(re.sub(r"<[^>]+>", " ", re.sub(r"<svg.*?</svg>", "", h, flags=re.S)))
        golden = {"FRESHUP": ["+31.85", "1.23%", "11-08 23:50:00 UTC"],
                  "FRESHDN": ["−106.72", "1.23%", "11-08 23:00:59 UTC"],
                  "OLD": ["11-08 06:46 UTC", "17.2 t", "−10.00", "1.23%", "11-08 06:46:40 UTC"],
                  "NOMARK": ["0.00%"]}
        for led, want in golden.items():
            self.assertEqual(toks(card(self.doc, led)), want, led)
        self.assertIn("<span>Fyld</span><b>2</b>", card(self.doc, "FRESHUP"))
        self.assertIn("<span>Fyld</span><b>1</b>", card(self.doc, "OLD"))
        self.assertIn("<span>Kapital</span><b>10,000</b>", card(self.doc, "NOMARK"))
        rows = sorted(tuple(toks(r)) for r in re.findall(r'<div class="ev [^"]*"[^>]*>.*?</div>', self.doc))
        self.assertEqual(rows, sorted([
            ("2026-11-08 23:55:00 UTC", "1 @ 101", "gebyr −0.0400"), ("2026-11-08 23:40:00 UTC",),
            ("2026-11-08 22:03:20 UTC", "1 @ 100", "gebyr −0.0400"), ("2026-11-07 00:00:00 UTC",),
            ("2026-11-06 00:00:00 UTC", "0.5 @ 2000", "gebyr −0.4000"),
            ("2026-10-20 00:00:00 UTC", "0.1 @ 2400", "gebyr −0.1000")]))
        self.assertEqual(re.findall(r'class="big[^"]*"[^>]*>([^<]*)<', self.doc),
                         ["Ikke tilgængelig", "−74.87", "−10.00"])


if __name__ == "__main__":
    unittest.main()
