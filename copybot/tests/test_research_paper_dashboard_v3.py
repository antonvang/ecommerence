"""Director order 69 P0, DASHBOARD V3: the main view holds only current (FRESH) paper data, STALE/MISSING_MARK accounts
live in a collapsed archive and are never styled or labelled as current, the portfolio total is unknown whenever any
account is not FRESH, the research overview and milestones are shown with their sources, the page stays static
(no script/URL/fetch/eval/button/form), the DB is untouched, the output is deterministic and the page fits a size
budget with one responsive SVG per chart."""
import hashlib
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import paper_chart as pc  # noqa: E402
from research.tools import paper_dashboard as pd  # noqa: E402
from research.tools import paper_research as pr  # noqa: E402
from tests.test_research_paper_dashboard import CUT, EQUITY, EVENTS, FILLS, GEN, LEDGERS, make_db  # noqa: E402

SIZE_BUDGET = 400 * 1024


def render(p, root=pd.HERE, cutoff=CUT):
    con = pd.connect_ro(p)
    try:
        return pd.render(con, GEN, cutoff, p, 200, root=root)
    finally:
        con.close()


def main_view(doc):
    return doc[doc.index('id="overblik"'):doc.index('id="arkiv"')]


def archive(doc):
    m = re.search(r'<details class="fold arch" id="arkiv">.*?</details>', doc, re.S)
    assert m
    return m.group(0)


def cards(html_):
    return re.findall(r'<article class="bot b-([^ ]+) s-([A-Z_]+)">(.*?)</article>', html_, re.S)


class V3(unittest.TestCase):
    def setUp(self):
        self.p = make_db(EQUITY, FILLS, EVENTS + [(CUT - 5000, "paper.mark_failed", "OLD", {"error": "dns"})],
                         LEDGERS)
        self.doc = render(self.p)

    def test_stale_not_in_main_view_but_in_archive(self):
        main, arch = main_view(self.doc), archive(self.doc)
        self.assertEqual({(led, st) for led, st, _ in cards(main)}, {("FRESHUP", "FRESH"), ("FRESHDN", "FRESH")})
        self.assertEqual({(led, st) for led, st, _ in cards(arch)}, {("OLD", "STALE"), ("NOMARK", "MISSING_MARK")})
        for led in ("OLD", "NOMARK"):
            self.assertNotIn(f"b-{led} ", main)
        self.assertNotIn("Sidst kendt netto, STALE-konti", main)
        self.assertNotIn("−10.00", main)                                   # the STALE net never shows up there
        self.assertTrue(archive(self.doc).startswith('<details class="fold arch" id="arkiv"><summary>'))   # closed

    def test_no_stale_value_styled_or_labelled_as_current(self):
        arch = archive(self.doc)
        for led, st, body in cards(arch):
            self.assertNotIn("c-FRESH", body)
            self.assertNotRegex(body, r'bnet (pos|neg)')
            self.assertNotRegex(body, r'spark (pos|neg)')
            if st == "STALE":
                self.assertIn('class="bnet old"', body)
                self.assertIn("sidst kendt, ikke aktuel", body)
                self.assertIn("Forældet — mærket", body)
        self.assertIn('<div class="big old">−10.00</div>', arch)
        self.assertIn("<b>Ikke aktuel</b>", arch)
        self.assertIn("sidst kendt netto −10.00 (sidst kendt, ikke aktuel)", arch)
        self.assertNotIn("Aktuel", arch.replace("Ikke aktuel", "").replace("ikke aktuel", ""))
        dq = re.search(r'b-OLD .*?<div class="dq">(.*?)</div>', arch, re.S).group(1)
        self.assertIn("paper.mark_failed 1×, senest 11-08 22:36", dq)
        self.assertIn("spotben/DNS", dq)                                    # carry90 = spot leg: the static note
        self.assertIn(pd.e(pd.STALE_NOTE), arch)
        self.assertIn("research/desk/MARK_FAILED_59D.md", arch)
        st = render(make_db([("S", CUT - 30000, 10001.0)], ledgers=[("S", "straks")]))
        self.assertIn("årsag ikke registreret her; kør lab_qc", archive(st))   # no DNS claim for a perp-only book
        self.assertNotIn('id="stale-why"', st)

    def test_portfolio_total_unknown_unless_all_fresh(self):
        cases = {"stale": [("A", CUT - 60, 10005.0), ("B", CUT - 30000, 9997.0)],
                 "missing": [("A", CUT - 60, 10005.0)],
                 "both": [("A", CUT - 30000, 10005.0)]}
        for name, eq in cases.items():
            doc = render(make_db(eq, ledgers=[("A", "straks"), ("B", "pairs")]))
            self.assertIn('id="portfolio">Ikke tilgængelig', doc, name)
            self.assertNotRegex(doc, r'id="portfolio">[+−±]')
        doc = render(make_db([("A", CUT - 60, 10005.0), ("B", CUT - 7200, 9997.0)],
                             ledgers=[("A", "straks"), ("B", "pairs")]))
        self.assertIn('id="portfolio">+2.00', doc)
        self.assertIn("Ingen forældede konti ved cutoff.", doc)
        self.assertIn('id="fresh-net">−74.87', self.doc)
        self.assertIn("kun FRESH, ikke en porteføljeværdi", self.doc)

    def test_header_health_strip(self):
        hdr = self.doc[:self.doc.index("</header>")]
        self.assertIn('PAPER / SIMULATION — ingen rigtige penge', hdr)
        self.assertIn("Statisk snapshot genereret 2026-11-09 00:38:00 UTC", hdr)
        self.assertIn("Datacutoff: <b>2026-11-09 00:00:00 UTC</b>", hdr)
        self.assertIn("FRESH <b>2</b>", hdr)
        self.assertIn("STALE <b>1</b>", hdr)
        self.assertIn("MISSING_MARK <b>1</b>", hdr)
        dq = re.search(r'<section class="dqp" id="datakvalitet">.*?</section>', self.doc, re.S).group(0)   # V4: moved here
        self.assertRegex(dq, r"DB: skema \d+/17 tabeller \(let tjek\)")         # synthetic DB: a few tables only
        self.assertIn("kør lab_qc", dq)
        self.assertIn("2 af 4 konti friske", dq)
        self.assertIn("PASS_UNREACHABLE / PENDING_FORMAL_CLOSE", dq)
        self.assertIn("research/desk/PM_LP_D1_STATUS_72.md", dq)
        empty = tempfile.mkdtemp()
        try:
            doc = render(self.p, root=empty)
        finally:
            shutil.rmtree(empty)
        self.assertIn("kør lab_qc (ingen dokumenteret kørsel fundet)", doc)
        self.assertIn("Rapportafstemning: ingen fundet", doc)

    def test_v4_layer_and_order(self):
        self.assertIn(".dqp .dq-grid", self.doc)
        self.assertNotIn("<script", self.doc)
        self.assertLess(self.doc.index('id="overblik"'), self.doc.index('id="datakvalitet"'))
        self.assertLess(self.doc.index('id="datakvalitet"'), self.doc.index('id="arkiv"'))
        self.assertIn('href="#datakvalitet"', self.doc)

    def test_research_overview_with_sources(self):
        sec = re.search(r'<section class="rs" id="forskning">.*?</section>', self.doc, re.S).group(0)
        self.assertIn("Ingen valideret profitabel strategi", sec)
        self.assertIn(pr.MATRIX, sec)
        ids = re.findall(r'<article class="rs-c" data-id="([^"]+)">', sec)
        self.assertEqual(ids, ["K05", "K04", "K10", "U4", "U1", "U2"])
        for body in re.findall(r'<article class="rs-c".*?</article>', sec, re.S):
            self.assertIn("Kilde: research/desk/FALSIFICATION_MATRIX_ORDER61.md §1", body)
            self.assertRegex(body, r"research/desk/\S+\.md")
        self.assertIn('id="rs-tillaeg"', sec)
        self.assertIn("D5 ejernøgle", sec)
        self.assertIn("Lokal DNS", sec)
        self.assertIn("W0-alfa", sec)
        self.assertNotRegex(self.doc.lower(), r"valideret profitabel strategi(?! *[.<])|profitabel strategi fundet")
        self.assertLess(self.doc.index('id="aktivitet"'), self.doc.index('id="forskning"'))
        self.assertLess(self.doc.index('id="forskning"'), self.doc.index('id="kirkegaard-fold"'))

    def test_milestones_listed(self):
        ms = re.search(r'<ol class="rs-m">(.*?)</ol>', self.doc, re.S).group(1)
        items = re.findall(r'<span class="md">([^<]+)</span><span class="mw">([^<]+)</span>', ms)
        self.assertEqual([d for d, _ in items], ["12/11", "14/11", "19/11", "20/11"])
        txt = " ".join(w for _, w in items)
        for want in ("STRAKS", "gate", "HFC-1", "PAR-BOG", "S1"):
            self.assertIn(want, txt)
        self.assertIn("om 3 d 17 t", ms)                                    # 11-09 00:00 -> 12/11 17:11:51 UTC
        self.assertEqual(ms.count("Kilde: research/desk/"), 4)

    def test_research_fallback_when_matrix_missing_or_broken(self):
        root = tempfile.mkdtemp()
        try:
            doc = render(self.p, root=root)
            self.assertIn('id="rs-fallback"', doc)
            self.assertIn(pr.CURATED_FROM, doc)
            self.assertEqual(re.findall(r'<article class="rs-c" data-id="([^"]+)">', doc),
                             ["K05", "K04", "K10", "U4", "U1", "U2"])
            self.assertEqual(len(re.findall(r'<span class="md">', doc)), 4)
            os.makedirs(os.path.join(root, "research", "desk"))
            with open(os.path.join(pd.HERE, pr.MATRIX), encoding="utf-8") as f:
                broken = f.read().replace("| Hypotese |", "| Idé |")
            with open(os.path.join(root, pr.MATRIX), "w", encoding="utf-8") as f:
                f.write(broken)
            doc = render(self.p, root=root)
            self.assertIn("kandidattabellen (§1) kunne ikke læses", doc)
        finally:
            shutil.rmtree(root)

    def test_static_no_script_urls_buttons_forms(self):
        low = self.doc.lower()
        for bad in ("<script", "http://", "https://", "fetch(", "xmlhttprequest", "eval(", "<button", "<form",
                    "@import", "url(", "<link", "<img", "<iframe", "src=", "onclick", "onload", "javascript:"):
            self.assertNotIn(bad, low, bad)
        self.assertTrue(all(h.startswith("#") for h in re.findall(r'href="([^"]*)"', self.doc)))

    def test_db_byte_identical_and_deterministic(self):
        with open(self.p, "rb") as f:
            h0 = hashlib.sha256(f.read()).hexdigest()
        d = os.path.dirname(self.p)
        a, b = os.path.join(d, "a.html"), os.path.join(d, "b.html")
        pd.main(["--db", self.p, "--cutoff", "2026-11-09T00:00:00Z", "--out", a, "--refresh", "300"], now=GEN)
        pd.main(["--db", self.p, "--cutoff", "2026-11-09T00:00:00Z", "--out", b, "--refresh", "300"], now=GEN)
        with open(self.p, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h0)
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())
        self.assertEqual(render(self.p), self.doc)

    def test_page_size_budget_and_one_svg_per_chart(self):
        self.assertEqual(len(pc.VARIANTS), 1)
        size = len(self.doc.encode())
        self.assertLess(size, SIZE_BUDGET, size)
        self.assertEqual(len(re.findall(r'<svg class="cv ', self.doc)), len(re.findall(r'<article class="chart ', self.doc)))
        print(f"\nV3 synthetic fixture page: {size} bytes (budget {SIZE_BUDGET})")

    def test_layout_order_folds_and_responsive_css(self):
        order = ['id="snapshot"', 'id="health"', 'id="overblik"', 'id="arkiv"', 'id="handelschart"',
                 'id="aktivitet"', 'id="forskning"', 'id="kirkegaard-fold"', "<footer>"]
        idx = [self.doc.index(x) for x in order]
        self.assertEqual(idx, sorted(idx))
        self.assertIn('<details class="fold" id="kirkegaard-fold"><summary>', self.doc)      # collapsed by default
        self.assertNotRegex(self.doc, r"<details[^>]*\bopen\b")
        self.assertIn('<meta name="viewport" content="width=device-width,initial-scale=1">', self.doc)
        for q in ("@media (max-width:1000px)", "@media (max-width:600px)", "@media (max-width:640px)"):
            self.assertIn(q, self.doc)
        self.assertIn("Kun læsning:", self.doc)
        self.assertIn("Ansvarsfraskrivelse:", self.doc)


if __name__ == "__main__":
    unittest.main()
