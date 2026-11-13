"""PAPIR LIVE tab of the event farm dashboard (research/tools/farm_dashboard.py): the forward paper book
(event_farm_forward_v2.ForwardBookV2) shown READ-ONLY. Empty state without a book; a synthetic book (synthetic mode, no
activation, temporary directory) rendered with status, open positions, primary frequencies / status shares / fill
uncertainty and R only in the collapsed appendix; the database file is byte-identical after rendering. No market data,
no network, no activation."""
import hashlib
import io
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_filters as ff  # noqa: E402
from research.tools import event_farm_forward as fw  # noqa: E402
from research.tools import event_farm_forward_v2 as fv  # noqa: E402
from research.tools import farm_dashboard as fd  # noqa: E402

BS = 300
SYMS = ["SYN1", "SYN2"]
CFG = {"warmup_bars": 50, "coverage_window_bars": 40}
R_WORDS = ("brutto R", "netto R", "værste fald", "R @")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def section(doc, cls):
    m = re.search(rf'<section class="pane {cls}">(.*?)</section>', doc, re.S)
    return m.group(1)


def damaged(seed, days):
    out = []
    for k, b in enumerate(ef.random_walk_bars(seed, days)):
        if k in (130, 131, 700):
            continue
        if k == 300:
            b = b[:5] + (0.0,)
        out.append(b)
    return out


def build_book(path):
    """The offline path of tests/test_event_farm_forward_v2.py: SyntheticSource, SYN symbols, injected clock."""
    bars = {"SYN1": damaged(41, 3), "SYN2": ef.random_walk_bars(42, 3)}
    src, now = fw.SyntheticSource(), [0]
    book = fv.ForwardBookV2(path, src, SYMS, clock=lambda: now[0], config=CFG)
    done = {s: 0 for s in SYMS}
    t0, t1 = bars["SYN2"][0][0], bars["SYN2"][-1][0] + BS
    for t in list(range(t0 + 12 * BS, t1, 12 * BS)) + [t1]:
        for s in SYMS:
            new = [b for b in bars[s][done[s]:] if b[0] + BS <= t]
            src.publish(s, new)
            done[s] += len(new)
        now[0] = t
        book.step()
    rev = bars["SYN2"][-3]
    src.push_once("SYN2", [rev[:5] + (rev[5] + 1.0,)])           # a revision: logged in conflicts, nothing rebooked
    book.step()
    book.close()


class EmptyState(unittest.TestCase):
    def test_no_book_gives_the_empty_state_with_four_requirements(self):
        doc = fd.render(fd.build(seed=83, days=2, instruments=1))
        lv = section(doc, "p-lv")
        self.assertIn('<label for="t-lv">PAPIR LIVE</label>', doc)
        self.assertIn("#t-lv:checked~.wrap .p-lv{display:block}", doc)
        self.assertIn(fd.EMPTY_TEXT, lv)
        self.assertEqual(fd.EMPTY_TEXT, "Ikke aktiveret — venter på direktørens godkendelse, ejerens D5-underskrift, "
                                        "G31 og 5m-stream")
        self.assertIn(fd.LIVE_BANNER, lv)
        self.assertEqual(lv.count("<li><i></i>"), 4)
        for name in ("Direktørens godkendelse", "Ejerens D5-underskrift", "G31", "5m-stream"):
            self.assertIn(name, lv)
        for w in R_WORDS:
            self.assertNotIn(w, lv)

    def test_missing_file_is_the_empty_state_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "event_farm_forward_v2.db")
            live = fd.read_forward(p)
            self.assertEqual(live["state"], "missing")
            self.assertEqual(os.listdir(d), [])
            self.assertIn(fd.EMPTY_TEXT, fd.live_tab(live))

    def test_other_databases_are_refused_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("lab.db", "pm_lp.db", "event_farm.db"):
                p = os.path.join(d, name)
                with self.assertRaises(ValueError):
                    fd.read_forward(p)
                out = os.path.join(d, "farm.html")
                with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
                    fd.main(["--out", out, "--days", "2", "--instruments", "1", "--forward-db", p])
            self.assertEqual(os.listdir(d), [])


class WithBook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "event_farm_forward_v2_dash.db")
        build_book(cls.path)
        cls.sha_before = sha(cls.path)
        cls.files_before = sorted(os.listdir(cls.tmp.name))
        cls.null = ff.null_with_filters(seed=83, instruments=1, days=2, costs=fd.NULL_COSTS)
        cls.live = fd.read_forward(cls.path, null=cls.null)
        cls.doc = fd.render(fd.build(seed=83, days=2, instruments=1), cls.live)
        cls.lv = section(cls.doc, "p-lv")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_database_is_byte_identical_and_no_side_files(self):
        self.assertEqual(sha(self.path), self.sha_before)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), self.files_before)

    def test_connection_is_read_only(self):
        db = fd.open_ro(self.path)
        try:
            self.assertEqual(db.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("CREATE TABLE x (a)")
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE meta SET v = 'x' WHERE k = 'step'")
        finally:
            db.close()
        self.assertEqual(sha(self.path), self.sha_before)

    def test_status_and_data_quality(self):
        lv = self.lv
        self.assertEqual(self.live["state"], "ok")
        self.assertIn(fd.LIVE_BANNER, lv)
        self.assertNotIn(fd.EMPTY_TEXT, lv)
        for w in ("aktiveret siden", "IntegrityHalt", "Status pr. symbol", "seneste bar", "dækning", "huller",
                  "revisioner", "F3 blokeret", "Tilstand <code>synthetic</code>"):
            self.assertIn(w, lv)
        rep = self.live["report"]
        for s in SYMS:
            self.assertIn(f"<td class=mono>{s}</td>", lv)
            last = self.live["symbols"][s]["last_ts"]
            self.assertEqual(last, max(b[0] for b in self.live["symbols"][s]["bars"]))
            self.assertIn(fd.dhm(last), lv)
        self.assertEqual(rep["data"]["SYN1"]["gaps"][0], 2)               # two holes declared in SYN1
        self.assertGreater(self.live["symbols"]["SYN1"]["f3_blocked_bars"], 0)
        self.assertEqual(self.live["symbols"]["SYN2"]["conflicts"], 1)
        self.assertIsNone(self.live["halted"])

    def test_open_positions_per_test(self):
        pend = [t for t in self.live["trades"] if t["status"] == "pending"]
        self.assertTrue(pend)
        self.assertIn(f"Åbne papirpositioner <small>{len(pend)} i", self.lv)
        for t in pend[:5]:
            self.assertIn(f"<td class=mono>{t['variant']}</td>", self.lv)
            self.assertIn(t["open_state"], self.lv)
            self.assertTrue(t["open_state"] in ("venter på fyld", "åben") or t["open_state"].startswith("i position"))

    def test_primary_table_has_all_96_tests_in_register_order(self):
        prim = self.lv.split('<details class="bilag">')[0]
        tests = fv.test_ids()
        self.assertEqual(len(tests), 96)
        pos = [prim.find(f"<tr><td class=mono>{t}</td>", prim.find("Primært")) for t in tests]
        self.assertTrue(all(p > 0 for p in pos))
        self.assertEqual(pos, sorted(pos))
        for w in ("frekvenser, statusandele og fill-usikkerhed", "pr. symbol-dag", "null pr. instr.-dag",
                  "bar rammer stop og mål", "fyld kun ved berøring"):
            self.assertIn(w, prim)

    def test_r_only_in_the_collapsed_appendix_with_the_null(self):
        lv = self.lv
        self.assertEqual(lv.count('<details class="bilag">'), 1)
        self.assertNotIn('<details class="bilag" open', lv)
        before, rest = lv.split('<details class="bilag">')
        bilag, after = rest.split("</details>")
        for part in (before, after):
            for w in R_WORDS:
                self.assertNotIn(w, part)
        for c in ("28", "0", "1", "5", "8"):
            self.assertIn(f"netto R @{c} bps", bilag)
            self.assertIn(f"null netto R @{c} bps", bilag)
        self.assertIn("brutto R", bilag)
        self.assertIn("null seed 83", bilag)
        self.assertIn("ingen rangordning", bilag)
        rows = re.findall(r"<tr><td class=mono>([^<]+)</td>", bilag)
        self.assertEqual(rows, fv.test_ids())                       # register order, never sorted by R
        self.assertNotIn('class="pos"', bilag)
        self.assertNotIn('class="neg"', bilag)

    def test_one_chart_per_symbol_with_entry_stop_target(self):
        for s in SYMS:
            self.assertIn(f'aria-label="{s} 5m papirbog"', self.lv)
        svgs = re.findall(r"<svg[^>]*papirbog.*?</svg>", self.lv, re.S)
        self.assertEqual(len(svgs), 2)
        self.assertTrue(any("indgang" in x and "mål" in x and "stop" in x for x in svgs))
        self.assertTrue(any(re.search(r"(LONG|SHORT) ×\d+", x) for x in svgs))

    def test_no_script_no_http(self):
        doc = self.doc.lower()
        self.assertNotIn("<script", doc)
        self.assertNotIn("http", doc)
        self.assertNotRegex(doc, r"\b(src|srcset)\s*=")

    def test_main_with_forward_db_writes_only_out(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "farm.html")
            buf = io.StringIO()
            real = ff.null_with_filters
            ff.null_with_filters = lambda **k: self.null                  # keep the test fast (seed 83 null cached)
            try:
                with redirect_stdout(buf):
                    self.assertEqual(fd.main(["--out", out, "--days", "2", "--instruments", "1",
                                              "--forward-db", self.path]), 0)
            finally:
                ff.null_with_filters = real
            self.assertIn("papir live: ok", buf.getvalue())
            self.assertEqual(os.listdir(d), ["farm.html"])
        self.assertEqual(sha(self.path), self.sha_before)
        self.assertEqual(sorted(os.listdir(self.tmp.name)), self.files_before)

    def test_book_without_activation_is_synthetic(self):
        self.assertEqual(self.live["identity"]["mode"], "synthetic")
        self.assertEqual(self.live["identity"]["schema"], "event_farm_forward/2")


class WarmupBox(unittest.TestCase):
    def live(self, n1, n2, statuses=("not_taken_warmup", "not_taken_warmup", "pending")):
        live = {"meta": {"start_ts": 1794521400}, "trades": [{"status": x} for x in statuses]}
        rep = {"data": {"BTCUSDT": {"processed": n1}, "ETHUSDT": {"processed": n2}}}
        return live, rep, {"warmup_bars": 288, "bar_seconds": 300}

    def test_progress_eta_and_skipped_count_during_warmup(self):
        html = fd.warmup_box(*self.live(239, 240))
        self.assertIn("Opvarmning", html)
        self.assertIn("<b>239 / 288</b>", html)
        self.assertIn("<b>240 / 288</b>", html)
        self.assertIn(fd.dhm(1794521400 + 288 * 300), html)               # 2026-11-13 22:10 UTC
        self.assertIn("Setups sprunget over i opvarmningen: <b>2</b>", html)

    def test_gone_once_every_symbol_is_past_warmup(self):
        self.assertEqual(fd.warmup_box(*self.live(288, 300)), "")
        self.assertIn("Opvarmning", fd.warmup_box(*self.live(288, 287)))


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
