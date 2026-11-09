"""Director order 59-K: HANDELSCHART in PAPER DASHBOARD V2 is display-only, one instrument per SVG, fill markers at the
exact (ts, px), market line only from recorded marks and broken at gaps, fill-only charts labelled as such, skips only
when tied to an instrument, entry lines only for documented open positions, never equity, static and read-only."""
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import paper_chart as pc  # noqa: E402
from research.tools import paper_dashboard as pd  # noqa: E402

CUT = 1794182400          # 2026-11-09 00:00:00 UTC
GEN = CUT + 2280
GAP = (CUT - 12000, CUT - 8000)


def make_db(fills, obs=(), funding=(), events=(), equity=None, ledgers=None):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "lab.db")
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE events (id INTEGER PRIMARY KEY, ts INTEGER, kind TEXT, exp_id TEXT, payload TEXT);
        CREATE TABLE sim_equity (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, equity REAL, cash REAL,
                                 exposure REAL, peak REAL, drawdown REAL);
        CREATE TABLE sim_fills (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, order_id TEXT, instrument TEXT,
                                side TEXT, px REAL, qty REAL, fee REAL, mid REAL);
        CREATE TABLE sim_funding (id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, settle_ts INTEGER, instrument TEXT,
                                  qty REAL, rate REAL, price REAL, amount REAL);
        CREATE TABLE observations (id INTEGER PRIMARY KEY, ts, detector, source, instrument, metric, value);
    """)
    for led, src, name in (ledgers or [("A", "straks", "STRAKS-FØLG"), ("B", "pairs", "PAR-BOG"),
                                       ("OLD", "carry90", "CARRY90-BTC")]):
        con.execute("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, 'lane.started', ?, ?)",
                    (CUT - 30 * 86400, led, json.dumps({"source": src, "name": name})))
        con.execute("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, 'paper.started', ?, ?)",
                    (CUT - 30 * 86400, led, json.dumps({"capital": 10000})))
    eq = equity if equity is not None else [("A", CUT - 600, 12345.67), ("B", CUT - 600, 9876.5),
                                            ("OLD", CUT - 90000, 10001.0)]
    con.executemany("INSERT INTO sim_equity (exp_id, ts, equity, cash, exposure, peak, drawdown) "
                    "VALUES (?, ?, ?, 0, 0, 0, 0.01)", eq)
    con.executemany("INSERT INTO sim_fills (exp_id, ts, order_id, instrument, side, px, qty, fee, mid) "
                    "VALUES (?, ?, 'o', ?, ?, ?, ?, ?, NULL)", fills)
    con.executemany("INSERT INTO observations (ts, detector, source, instrument, metric, value) "
                    "VALUES (?, 'k3/1', 'premiumIndex', ?, ?, ?)", obs)
    con.executemany("INSERT INTO sim_funding (exp_id, ts, settle_ts, instrument, qty, rate, price, amount) "
                    "VALUES (?, ?, ?, ?, 1, 0.0001, ?, 0.01)", funding)
    con.executemany("INSERT INTO events (ts, kind, exp_id, payload) VALUES (?, ?, ?, ?)",
                    [(ts, k, led, json.dumps(pl)) for ts, k, led, pl in events])
    con.commit()
    con.close()
    return p


FILLS = [("A", CUT - 20000, "BTCUSDT", "buy", 100.0, 1.0, 0.04),
         ("B", CUT - 18000, "BTCUSDT", "sell", 101.5, 0.5, 0.02),
         ("A", CUT - 15000, "BTCUSDT", "buy", 102.0, 1.0, 0.04),        # A open long 2 @ 101 (net_report basis)
         ("B", CUT - 9000, "BTCUSDT", "buy", 101.0, 0.5, 0.02),         # B flat: no entry line
         ("A", CUT - 30000, "XAUUSDT", "sell", 2400.0, 0.1, 0.1),
         ("A", CUT - 25000, "XAUUSDT", "buy", 2390.0, 0.1, 0.1),        # A flat in XAU
         ("B", CUT - 22000, "XAUUSDT", "buy", 2395.0, 0.2, 0.1),        # B open long 0.2 @ 2395
         ("A", CUT - 5000, "ETHUSDT", "buy", 2000.0, 1.0, 0.2),
         ("A", CUT - 4000, "ETHUSDT", "sell", 2010.0, 2.0, 0.4),        # flips through zero: entry not documented
         ("OLD", CUT - 50000, "SOLUSDT", "buy", 150.0, 3.0, 0.1),       # STALE book: no chart
         ("A", CUT + 600, "BTCUSDT", "sell", 103.0, 1.0, 0.04)]         # after the cutoff: never shown
OBS = ([(t, "BTCUSDT", "mark", 100.0 + (t % 7) * 0.1) for t in range(CUT - 21000, GAP[0] + 1, 60)]
       + [(t, "BTCUSDT", "mark", 101.0 + (t % 5) * 0.1) for t in range(GAP[1], CUT - 99, 60)]
       + [(CUT - 10000, "BTCUSDT", "funding_rate", 0.0001)]           # another metric: never a price point
       + [(CUT - 3000, "SOLUSDT", "mark", 151.0)])
FUNDING = [("A", CUT - 14390, CUT - 14400, "BTCUSDT", 101.7), ("B", CUT - 14385, CUT - 14400, "BTCUSDT", 101.7),
           ("A", CUT - 28790, CUT - 28800, "XAUUSDT", 2398.0)]
EVENTS = [(CUT - 11000, "straks.skipped", "A", {"instrument": "BTCUSDT", "reason": "åben position på markedet"}),
          (CUT - 11500, "paper.skipped", "A", {"coin": "XAUUSDT", "reason": "coin, ikke instrument"}),
          (CUT - 11600, "straks.skipped", "A", {"reason": "intet instrument"}),
          (CUT - 11700, "straks.skipped", "OLD", {"instrument": "BTCUSDT", "reason": "STALE-bog"})]


def render(p, cutoff=CUT):
    con = pd.connect_ro(p)
    try:
        return pd.render(con, GEN, cutoff, p, 200)
    finally:
        con.close()


def section(doc):
    m = re.search(r'<section class="hc" id="handelschart">.*?</section>', doc, re.S)
    assert m
    return m.group(0)


def svgs(doc, sym=None):
    out = re.findall(r'<svg class="cv cv-[dtm]"[^>]*>.*?</svg>', section(doc), re.S)
    return [s for s in out if sym is None or f'data-instrument="{sym}"' in s.split(">", 1)[0]]


def article(doc, sym):
    m = re.search(r'<article class="chart ch-%s" data-instrument="%s">.*?</article>' % (sym, sym), doc, re.S)
    assert m, sym
    return m.group(0)


def scale(s):
    head = s.split(">", 1)[0]
    g = lambda k: float(re.search(r'%s="([^"]+)"' % k, head).group(1))  # noqa: E731
    pl, pt, pr, pb = map(float, re.search(r'data-plot="([^"]+)"', head).group(1).split(","))
    x0, x1, y0, y1 = g("data-x0"), g("data-x1"), g("data-y0"), g("data-y1")
    return (lambda t: pl + (t - x0) / (x1 - x0) * (pr - pl)), (lambda v: pb - (v - y0) / (y1 - y0) * (pb - pt))


class Handelschart(unittest.TestCase):
    def setUp(self):
        self.p = make_db(FILLS, OBS, FUNDING, EVENTS)
        self.doc = render(self.p)
        self.sec = section(self.doc)

    def test_one_chart_per_instrument_most_fills_first(self):
        arts = re.findall(r'<article class="chart ch-([^"]+)" data-instrument="([^"]+)">', self.sec)
        self.assertEqual([s for _, s in arts], ["BTCUSDT", "XAUUSDT", "ETHUSDT"])
        self.assertNotIn("SOLUSDT", self.sec)                                 # only the FRESH books are charted
        self.assertEqual(len(svgs(self.doc)), 3 * len(pc.VARIANTS))
        for s in svgs(self.doc):
            self.assertEqual(len(re.findall(r'data-instrument="', s)), 1)      # exactly one instrument per SVG
            sym = re.search(r'data-instrument="([^"]+)"', s).group(1)
            named = set(re.findall(r"(?:KØB|SÆLG|SPRUNGET OVER) ([A-Z]+USDT)", s))
            self.assertLessEqual(named, {sym})
            others = {"BTCUSDT", "XAUUSDT", "ETHUSDT", "SOLUSDT"} - {sym}
            self.assertFalse(any(o in s for o in others), sym)

    def test_buy_sell_markers_at_exact_fill_positions(self):
        want = {"BTCUSDT": (3, 1), "XAUUSDT": (2, 1), "ETHUSDT": (1, 1)}
        for sym, (nb, ns) in want.items():
            for s in svgs(self.doc, sym):
                X, Y = scale(s)
                mk = re.findall(r'<path class="mk (buy|sell)" data-ts="(\d+)" data-px="([^"]+)" d="M([\d.]+) '
                                r'([\d.]+)L([\d.]+) ([\d.]+)', s)
                self.assertEqual(sum(1 for m in mk if m[0] == "buy"), nb, sym)
                self.assertEqual(sum(1 for m in mk if m[0] == "sell"), ns, sym)
                db = sorted((side, ts, px) for led, ts, i, side, px, q, f in FILLS if i == sym and ts <= CUT
                            and led in ("A", "B"))
                self.assertEqual(sorted((m[0], int(m[1]), float(m[2])) for m in mk), db)
                for side, ts, px, ax, ay, bx, by in mk:
                    self.assertAlmostEqual(float(ax), X(int(ts)), delta=0.01)
                    self.assertAlmostEqual(float(ay), Y(float(px)), delta=0.01)
                    self.assertGreater(float(by), float(ay)) if side == "buy" else self.assertLess(float(by),
                                                                                                    float(ay))
                titles = re.findall(r'<path class="mk (?:buy|sell)"[^>]*><title>([^<]+)</title>', s)
                self.assertEqual(len(titles), nb + ns)
                self.assertTrue(all(re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC · .+ · (KØB|SÆLG) "
                                              r"[A-Z]+ · [\d.e+-]+ @ [\d,.]+ · gebyr \d+\.\d{4}$", t) for t in titles))
        self.assertIn(".cv .mk.buy{fill:#16c784", self.doc)
        self.assertIn(".cv .mk.sell{fill:#ff4d5e", self.doc)

    def test_fill_only_chart_label_and_no_market_line(self):
        xau = article(self.doc, "XAUUSDT")
        self.assertIn("Handelspriser — ikke en markedskurs", xau)
        self.assertNotIn('class="mkt"', xau)
        self.assertNotIn("<polyline", xau)
        self.assertNotIn('class="gap"', xau)
        btc = article(self.doc, "BTCUSDT")
        self.assertNotIn("Handelspriser — ikke en markedskurs", btc)
        self.assertIn("Markedskurs (mark", btc)

    def test_market_line_broken_at_gap(self):
        for s in svgs(self.doc, "BTCUSDT"):
            X, _ = scale(s)
            segs = re.findall(r'<polyline class="mkt" data-t0="(\d+)" data-t1="(\d+)" points="([^"]+)"', s)
            self.assertEqual(len(segs), 2)
            for t0, t1, pts in segs:
                self.assertFalse(int(t0) <= GAP[0] and int(t1) >= GAP[1])     # no segment spans the gap
                xs = [float(p.split(",")[0]) for p in pts.split()]
                self.assertTrue(all(not (a < X(GAP[0] + 1) and b > X(GAP[1] - 1)) for a, b in zip(xs, xs[1:])))
            self.assertEqual((int(segs[0][1]), int(segs[1][0])), GAP)
            self.assertRegex(s, r'<rect class="gap" x="%.2f"[^>]*><title>Hul i markedsdata: 11-08 20:40:00 UTC – '
                                r'11-08 21:46:40 UTC \(67 min\); linjen er brudt, ikke interpoleret</title>'
                             % X(GAP[0]))
        self.assertNotIn("0.0001", "".join(svgs(self.doc, "BTCUSDT")))          # funding_rate metric not plotted

    def test_dense_market_series_thinned_to_recorded_points(self):
        t0 = CUT - 20000
        obs = [(t0 + 4 * i, "BTCUSDT", "mark", 100.0 + (i % 97) * 0.01) for i in range(4800)]
        obs[2345] = (obs[2345][0], "BTCUSDT", "mark", 108.0)                    # a spike must survive thinning
        obs[3456] = (obs[3456][0], "BTCUSDT", "mark", 95.0)
        doc = render(make_db(FILLS, obs))
        for s in svgs(doc, "BTCUSDT"):
            X, Y = scale(s)
            segs = re.findall(r'<polyline class="mkt" data-t0="\d+" data-t1="\d+" points="([^"]+)"', s)
            self.assertEqual(len(segs), 1)
            pts = [tuple(map(float, p.split(","))) for p in segs[0].split()]
            self.assertLess(len(pts), 4800)
            ys = [y for _, y in pts]
            self.assertAlmostEqual(min(ys), Y(108.0), delta=0.01)
            self.assertAlmostEqual(max(ys), Y(95.0), delta=0.01)
            real = {(round(X(t), 2), round(Y(v), 2)) for t, _, _, v in obs}
            self.assertTrue(all((round(x, 2), round(y, 2)) in real for x, y in pts))

    def test_funding_points_are_discrete(self):
        btc = svgs(self.doc, "BTCUSDT")[0]
        f = re.findall(r'<path class="mk fund" data-ts="(\d+)" data-px="([^"]+)"', btc)
        self.assertEqual(f, [(str(CUT - 14400), "101.7")])                     # one settlement, deduped
        self.assertIn("Funding-afregningspris 101.7 · PAR-BOG, STRAKS-FØLG", btc)
        self.assertEqual(len(re.findall(r'class="mk fund"', svgs(self.doc, "XAUUSDT")[0])), 1)
        self.assertNotIn("<polyline", "".join(svgs(self.doc, "XAUUSDT")))

    def test_skip_markers_only_with_instrument(self):
        for s in svgs(self.doc, "BTCUSDT"):
            sk = re.findall(r'<circle class="mk skip" data-ts="(\d+)"', s)
            self.assertEqual(sk, [str(CUT - 11000)])                           # STALE book's skip not shown
            self.assertIn("SPRUNGET OVER BTCUSDT · straks.skipped: åben position på markedet", s)
        for sym in ("XAUUSDT", "ETHUSDT"):
            for s in svgs(self.doc, sym):
                self.assertNotIn("mk skip", s)
                self.assertNotIn("Spring over", s)
        self.assertNotIn("coin, ikke instrument", self.sec)
        self.assertNotIn("intet instrument", self.sec)

    def test_entry_lines_only_for_documented_open_positions(self):
        for s in svgs(self.doc, "BTCUSDT"):
            _, Y = scale(s)
            en = re.findall(r'<line class="entry (long|short)" x1="[^"]+" x2="[^"]+" y1="([\d.]+)"[^>]*'
                            r'data-px="([^"]+)"><title>([^<]+)</title>', s)
            self.assertEqual([(d, float(px)) for d, _, px, _ in en], [("long", 101.0)])
            self.assertAlmostEqual(float(en[0][1]), Y(101.0), delta=0.01)
            self.assertIn("STRAKS-FØLG LONG 2", en[0][3])
            self.assertIn("Entry (gns.) 101.0", s)
        xau = svgs(self.doc, "XAUUSDT")[0]
        self.assertEqual(re.findall(r'class="entry (\w+)"[^>]*data-px="([^"]+)"', xau), [("long", "2395.0")])
        self.assertIn("PAR-BOG LONG", xau)
        eth = article(self.doc, "ETHUSDT")
        self.assertNotIn('class="entry', eth)
        self.assertIn("Ingen entry-linje for STRAKS-FØLG: positionen vendte gennem nul", eth)

    def test_equity_never_plotted_as_price(self):
        for bad in ("12345", "12,345", "9876", "9,876"):
            self.assertNotIn(bad, self.sec)
        for s in svgs(self.doc, "BTCUSDT"):
            head = s.split(">", 1)[0]
            self.assertLess(float(re.search(r'data-y1="([^"]+)"', head).group(1)), 200)
        with open(pc.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotRegex(src, r"(?i)from\s+sim_equity")

    def test_static_no_scripts_no_urls_no_buttons(self):
        low = self.doc.lower()
        for bad in ("<script", "http://", "https://", "fetch(", "xmlhttprequest", "eval(", "<button", "<form",
                    "@import", "url(", "<link", "<img", "<iframe", "src=", "onclick", "onmouse", "<foreignobject"):
            self.assertNotIn(bad, low, bad)
        self.assertIn("ingen ordrer fra grafen", self.sec)
        self.assertNotIn("Chart Trader", self.doc)
        for sym in ("BTCUSDT", "XAUUSDT", "ETHUSDT"):
            self.assertIn('<span class="ch-paper">PAPER / SIMULATION</span>', article(self.doc, sym))

    def test_css_only_selector(self):
        radios = re.findall(r'<input class="f" type="radio" name="fc" id="fc-([^"]+)"( checked)?>', self.doc)
        self.assertEqual(radios, [("BTCUSDT", " checked"), ("XAUUSDT", ""), ("ETHUSDT", "")])
        for sym in ("BTCUSDT", "XAUUSDT", "ETHUSDT"):
            self.assertIn(f"#fc-{sym}:checked~.wrap .ch-{sym}{{display:block}}", self.doc)
            self.assertIn(f'<label class="hc-tab" for="fc-{sym}">', self.sec)
        self.assertIn(".chart{display:none;", self.doc)
        self.assertLess(self.doc.index('<section class="grid">'), self.doc.index('id="handelschart"'))
        self.assertLess(self.doc.index('id="handelschart"'), self.doc.index('<section id="feed">'))

    def test_db_untouched_and_deterministic(self):
        with open(self.p, "rb") as f:
            h0 = hashlib.sha256(f.read()).hexdigest()
        d = os.path.dirname(self.p)
        a, b = os.path.join(d, "a.html"), os.path.join(d, "b.html")
        pd.main(["--db", self.p, "--cutoff", "2026-11-09T00:00:00Z", "--out", a], now=GEN)
        pd.main(["--db", self.p, "--cutoff", "2026-11-09T00:00:00Z", "--out", b], now=GEN)
        with open(self.p, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h0)
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())
        self.assertEqual(render(self.p), self.doc)

    def test_cap_and_window(self):
        fills = [("A", CUT - 3600 - i * 60, f"S{k}USDT", "buy" if i % 2 else "sell", 10.0 + k, 1.0, 0.01)
                 for k in range(8) for i in range(10 - k)]
        fills += [("A", CUT - 10 * 86400, "S0USDT", "buy", 9.0, 1.0, 0.01)]    # older than 7 days
        doc = render(make_db(fills))
        arts = re.findall(r'<article class="chart ch-([^"]+)"', doc)
        self.assertEqual(arts, [f"S{k}USDT" for k in range(6)])
        self.assertIn("Ikke vist (maks. 6 grafer, flest fyld først): S6USDT (4), S7USDT (3).", doc)
        s0 = article(doc, "S0USDT")
        self.assertIn("seneste 7 d: 11-02 00:00 – 11-09 00:00 UTC; 1 ældre fyld ikke vist", s0)
        self.assertEqual(len(re.findall(r'class="mk (?:buy|sell)"', svgs(doc, "S0USDT")[0])), 10)
        self.assertIn("alle handler til cutoff", article(doc, "S1USDT"))

    def test_no_fresh_books_no_chart(self):
        doc = render(make_db(FILLS, OBS, FUNDING, EVENTS, equity=[("A", CUT - 90000, 10000.0)]))
        self.assertIn("Ingen handelschart: ingen FRESH-papirbøger med fyld til cutoff.", doc)
        self.assertNotIn("<svg class=\"cv", doc)
        self.assertNotIn('name="fc"', doc)

    def test_old_schema_without_observations_or_funding_price(self):
        p = make_db(FILLS)
        con = sqlite3.connect(p)
        con.executescript("DROP TABLE observations; DROP TABLE sim_funding; CREATE TABLE sim_funding (id INTEGER "
                          "PRIMARY KEY, exp_id TEXT, ts INTEGER, instrument TEXT, amount REAL);")
        con.close()
        doc = render(p)
        btc = article(doc, "BTCUSDT")
        self.assertIn("Handelspriser — ikke en markedskurs", btc)
        self.assertNotIn("mk fund", btc)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
