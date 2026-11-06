"""Director order 51 P1: C1 forward volatility forecast journal (synthetic data only; no network; temp dirs only)."""
import ast
import calendar
import json
import math
import os
import random
import shutil
import socket
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "research", "tools"))

from research.tools import c1_forecast as c  # noqa: E402

DAY, HOUR = c.DAY, c.HOUR
SRC = os.path.join(HERE, "research", "tools", "c1_forecast.py")


def small_cfg(window=60):
    cfg = json.loads(json.dumps(c.DEFAULT_CONFIG))
    cfg["har"].update(est_window_days=window, min_rows=window)
    return cfg


def no_network(*a, **k):
    raise AssertionError("network access attempted")


class Fixture(unittest.TestCase):
    """A synthetic journal and the marks of three symbols, 100 days from the synthetic epoch (2033)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="c1_test_")
        self.cfg = small_cfg()
        marks, _ = c.synth_marks(("SYNA", "SYNB", "SYNC"), 100, seed=7)
        self.slots = {s: c.to_slots(m, self.cfg) for s, m in marks.items()}
        self.last = c.SYN_DAY0 + 95 * DAY                       # last input day L, target L+1
        self.clock = c.SimClock(self.last + 12 * HOUR)          # genesis at noon of L
        self.path = os.path.join(self.root, "j.jsonl")
        self.j = c.Journal(self.path, self.cfg, clock=self.clock)
        self.clock.t = self.last + 23 * HOUR + 1800             # 23:30 of L: after the 23:00 mark, before L+1

    def tearDown(self):
        shutil.rmtree(self.root)

    def rec(self, model=c.BENCHMARK, sym="SYNA", last=None):
        return c.build_forecast(model, sym, self.slots[sym], self.last if last is None else last, self.cfg)

    def issue(self, model=c.BENCHMARK, sym="SYNA"):
        return self.j.append_forecast(self.rec(model, sym))

    def reveal(self, f):
        st, v, ident, cov = c.realized(self.slots[f["symbol"]], f["symbol"], f["target_start"], self.cfg)
        return self.j.append_reveal(f["entry_hash"], st, v, ident, cov)


class ForecastRules(Fixture):
    def test_valid_forecast_records_everything(self):
        f = self.issue()
        for k in ("model", "model_version", "config_sha256", "input_cutoff_ts", "created_ts", "horizon_days",
                  "target_start", "target_end", "input_sha256", "coverage", "value", "earliest_eval_ts"):
            self.assertIn(k, f)
        self.assertEqual(f["config_sha256"], c.config_sha256(self.cfg))
        self.assertEqual(f["target_start"], self.last + DAY)
        self.assertEqual(f["target_end"], self.last + 2 * DAY)
        self.assertEqual(f["earliest_eval_ts"], f["target_end"] + self.cfg["settlement_lag_s"])
        self.assertLessEqual(f["input_cutoff_ts"], f["created_ts"])
        self.assertLess(f["created_ts"], f["target_start"])
        self.assertEqual(f["coverage"], 1.0)
        self.assertEqual(len(f["input_sha256"]), 64)

    def test_backdated_forecast_refused(self):
        with self.assertRaisesRegex(c.ForecastRefused, "backdated"):
            self.j.append_forecast(self.rec(), created_ts=self.clock.t - 3600)
        self.issue(c.BENCHMARK, "SYNA")
        self.clock.t -= 600                                       # journal time may not run backwards
        with self.assertRaisesRegex(c.ForecastRefused, "before the last journal entry"):
            self.issue(c.BENCHMARK, "SYNB")

    def test_forecast_created_inside_or_after_target_window_refused(self):
        r = self.rec()
        for t in (r["target_start"], r["target_start"] + 3600, r["target_end"] + 1):
            self.clock.t = t
            with self.assertRaisesRegex(c.ForecastRefused, "created at/after target start"):
                self.j.append_forecast(dict(r))

    def test_cutoff_after_creation_refused(self):
        r = self.rec()
        r["input_cutoff_ts"] = self.clock.t + 1
        with self.assertRaisesRegex(c.ForecastRefused, "input cutoff after creation"):
            self.j.append_forecast(r)
        self.clock.t = self.last + 23 * HOUR - 1                  # before the 23:00 mark that the input contains
        with self.assertRaisesRegex(c.ForecastRefused, "input cutoff after creation"):
            self.j.append_forecast(self.rec())

    def test_cutoff_after_target_start_refused(self):
        r = self.rec()
        r["input_cutoff_ts"] = r["target_start"] + 60
        with self.assertRaises(c.ForecastRefused):
            self.j.append_forecast(r)
        r = self.rec()
        r["input_last_day"] = r["target_start"]                  # input days overlapping the target
        with self.assertRaisesRegex(c.ForecastRefused, "overlap"):
            self.j.append_forecast(r)

    def test_low_coverage_refused(self):
        r = self.rec()
        r["coverage"] = 0.99
        with self.assertRaisesRegex(c.ForecastRefused, "coverage"):
            self.j.append_forecast(r)
        # a missing hour inside the input: the models refuse before anything reaches the journal
        drop = [("SYNA", c.SYN_DAY0 + 50 * DAY + 5 * HOUR)]
        marks, _ = c.synth_marks(("SYNA",), 100, seed=7, drop_slots=drop)
        sl = c.to_slots(marks["SYNA"], self.cfg)
        for model in (c.CANDIDATE, c.BENCHMARK):
            with self.assertRaises(c.ModelRefused):
                c.build_forecast(model, "SYNA", sl, self.last, self.cfg)
        # with a looser fit rule the HAR runs, but its input coverage < 1 is refused by the journal
        loose = small_cfg()
        loose["har"]["min_rows"] = 20
        jl = c.Journal(os.path.join(self.root, "loose.jsonl"), loose, clock=self.clock)
        r = c.build_forecast(c.CANDIDATE, "SYNA", sl, self.last, loose)
        self.assertLess(r["coverage"], 1.0)
        with self.assertRaisesRegex(c.ForecastRefused, "coverage"):
            jl.append_forecast(r)

    def test_no_reissue_and_bad_values(self):
        self.issue()
        with self.assertRaisesRegex(c.ForecastRefused, "no re-issue"):
            self.issue()
        for bad in (0.0, -1e-4, float("nan"), float("inf")):
            r = self.rec(sym="SYNB")
            r["value"] = bad
            with self.assertRaises(c.ForecastRefused):
                self.j.append_forecast(r)
        r = self.rec(sym="SYNB")
        r["target_end"] += HOUR
        with self.assertRaisesRegex(c.ForecastRefused, "aligned day"):
            self.j.append_forecast(r)
        r = self.rec(sym="SYNB")
        r["model_version"] = "har/0"
        with self.assertRaisesRegex(c.ForecastRefused, "unknown model"):
            self.j.append_forecast(r)

    def test_no_edit_or_delete_api(self):
        public = {n for n in dir(c.Journal) if not n.startswith("_")}
        self.assertEqual(public, {"append_forecast", "append_reveal", "entries"})

    def test_real_journal_needs_activation_and_synthetic_clock(self):
        with self.assertRaisesRegex(c.ForecastRefused, "activation"):
            c.Journal(os.path.join(self.root, "real.jsonl"), self.cfg, clock=lambda: 1.8e9, synthetic=False)
        with self.assertRaisesRegex(c.ForecastRefused, "synthetic epoch"):
            c.Journal(os.path.join(self.root, "early.jsonl"), self.cfg, clock=lambda: 1.8e9)
        other = small_cfg(61)
        with self.assertRaisesRegex(c.JournalCorrupt, "genesis"):
            c.Journal(self.path, other, clock=self.clock)


class Tampering(Fixture):
    def build(self):
        fa = self.issue(c.BENCHMARK, "SYNA")
        fb = self.issue(c.CANDIDATE, "SYNA")
        self.issue(c.BENCHMARK, "SYNB")
        return fa, fb

    def lines(self):
        with open(self.path, encoding="utf-8") as fh:
            return fh.read().splitlines()

    def write(self, lines, head=True):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("".join(x + "\n" for x in lines))
        if head:
            e = json.loads(lines[-1])
            with open(self.path + ".head", "w", encoding="utf-8") as fh:
                json.dump({"seq": e["seq"], "entry_hash": e["entry_hash"]}, fh)

    def test_clean_chain_verifies(self):
        self.build()
        es = c.verify_file(self.path)
        self.assertEqual([e["seq"] for e in es], [0, 1, 2, 3])
        self.assertEqual(es[1]["prev_hash"], es[0]["entry_hash"])

    def test_edited_value_detected(self):
        self.build()
        ls = self.lines()
        e = json.loads(ls[1])
        e["value"] *= 1.1
        ls[1] = json.dumps(e)
        self.write(ls, head=False)
        with self.assertRaisesRegex(c.JournalCorrupt, "chain broken"):
            c.verify_file(self.path)
        with self.assertRaises(c.JournalCorrupt):           # and every journal operation refuses
            self.issue(c.BENCHMARK, "SYNC")

    def test_rehashed_entry_breaks_the_next_link(self):
        self.build()
        ls = self.lines()
        e = json.loads(ls[1])
        e["value"] *= 1.1
        e["entry_hash"] = c.entry_hash(e)
        ls[1] = c.canonical(e).decode()
        self.write(ls, head=False)
        with self.assertRaisesRegex(c.JournalCorrupt, "line 2"):
            c.verify_file(self.path)

    def test_deleted_reordered_and_truncated(self):
        self.build()
        ls = self.lines()
        self.write(ls[:2] + ls[3:])
        with self.assertRaisesRegex(c.JournalCorrupt, "chain broken"):
            c.verify_file(self.path)
        self.write([ls[0], ls[2], ls[1], ls[3]])
        with self.assertRaises(c.JournalCorrupt):
            c.verify_file(self.path)
        self.write(ls[:3], head=False)                     # tail cut, head anchor still names seq 3
        with open(self.path + ".head", "w", encoding="utf-8") as fh:
            json.dump({"seq": 3, "entry_hash": json.loads(ls[3])["entry_hash"]}, fh)
        with self.assertRaisesRegex(c.JournalCorrupt, "head anchor"):
            c.verify_file(self.path)
        with open(self.path, "w", encoding="utf-8") as fh:  # partial last line
            fh.write("\n".join(ls))
        with self.assertRaisesRegex(c.JournalCorrupt, "partial"):
            c.verify_file(self.path)

    def test_consistently_rewritten_lookahead_chain_still_refused(self):
        """Someone rewrites the whole file and rehashes every link: the rules are re-checked on read."""
        self.build()
        es = [json.loads(x) for x in self.lines()]
        es[1]["created_ts"] = es[1]["target_start"] + 10
        es[2]["created_ts"] = es[3]["created_ts"] = es[1]["created_ts"]
        prev = c.GENESIS_PREV
        out = []
        for e in es:
            e["prev_hash"] = prev
            e["entry_hash"] = c.entry_hash(e)
            prev = e["entry_hash"]
            out.append(c.canonical(e).decode())
        self.write(out)
        with self.assertRaisesRegex(c.JournalCorrupt, "violates a journal rule"):
            c.verify_file(self.path)


class Reveals(Fixture):
    def test_early_reveal_refused(self):
        f = self.issue()
        self.clock.t = f["earliest_eval_ts"] - 1
        with self.assertRaisesRegex(c.RevealRefused, "before earliest evaluation"):
            self.reveal(f)
        self.clock.t = f["target_start"] + 3600              # inside the target window
        with self.assertRaises(c.RevealRefused):
            self.reveal(f)

    def test_double_reveal_refused(self):
        f = self.issue()
        self.clock.t = f["earliest_eval_ts"]
        r = self.reveal(f)
        self.assertEqual(r["status"], "ok")
        self.assertGreater(r["realized"], 0)
        with self.assertRaisesRegex(c.RevealRefused, "once only"):
            self.reveal(f)
        with self.assertRaisesRegex(c.RevealRefused, "no such forecast"):
            self.j.append_reveal("f" * 64, "ok", 1e-4, "a" * 64, 1.0)

    def test_void_reveal_for_incomplete_target(self):
        f = self.issue()
        self.clock.t = f["earliest_eval_ts"]
        sl = dict(self.slots["SYNA"])
        del sl[f["target_start"] + 7 * HOUR]
        st, v, ident, cov = c.realized(sl, "SYNA", f["target_start"], self.cfg)
        self.assertEqual((st, v), ("void", None))
        with self.assertRaises(c.RevealRefused):
            self.j.append_reveal(f["entry_hash"], "ok", 1e-4, ident, cov)   # ok needs full coverage
        r = self.j.append_reveal(f["entry_hash"], st, v, ident, cov)
        self.assertEqual(r["status"], "void")


class Evaluation(Fixture):
    def test_evaluation_without_reveal_refused(self):
        f = self.issue()
        self.clock.t = f["earliest_eval_ts"] + 10
        with self.assertRaisesRegex(c.EvaluationRefused, "no reveal"):
            c.evaluate(self.j.entries(), self.cfg, now=self.clock.t)

    def test_evaluation_refuses_forecast_not_created_before_target(self):
        f = dict(self.issue())
        f["created_ts"] = f["target_start"]
        with self.assertRaisesRegex(c.EvaluationRefused, "not created before"):
            c.evaluate([f], self.cfg, now=f["earliest_eval_ts"])

    def test_disagreeing_reveals_refused(self):
        fa, fb = self.issue(c.BENCHMARK), self.issue(c.CANDIDATE)
        self.clock.t = fa["earliest_eval_ts"]
        ra, rb = dict(self.reveal(fa)), dict(self.reveal(fb))
        rb["realized"] *= 2
        es = [e for e in self.j.entries() if e["kind"] == "forecast"] + [ra, rb]
        cfg = dict(self.cfg, dm=dict(self.cfg["dm"], min_days=1))
        with self.assertRaisesRegex(c.EvaluationRefused, "disagree"):
            c.evaluate(es, cfg, now=self.clock.t)

    def test_too_few_days_refused(self):
        fa, fb = self.issue(c.BENCHMARK), self.issue(c.CANDIDATE)
        self.clock.t = fa["earliest_eval_ts"]
        self.reveal(fa)
        self.reveal(fb)
        with self.assertRaisesRegex(c.EvaluationRefused, "min_days"):
            c.evaluate(self.j.entries(), self.cfg, now=self.clock.t)


class Math(unittest.TestCase):
    def test_qlike_hand_examples(self):
        self.assertAlmostEqual(c.qlike(2.0, 1.0), 2 - math.log(2) - 1, places=15)    # 0.306853
        self.assertAlmostEqual(c.qlike(2.0, 1.0), 0.30685281944005466, places=15)
        self.assertAlmostEqual(c.qlike(1.0, 2.0), 0.5 + math.log(2) - 1, places=15)  # 0.193147
        self.assertEqual(c.qlike(3e-4, 3e-4), 0.0)
        self.assertAlmostEqual(c.qlike(4e-4, 1e-4), 4 - math.log(4) - 1, places=12)  # scale-free in RV/F
        for rv, f in ((0.0, 1.0), (1.0, 0.0), (-1.0, 1.0), (1.0, float("nan"))):
            with self.assertRaises(c.EvaluationRefused):
                c.qlike(rv, f)

    def test_ewma_hand_example(self):
        cfg = json.loads(json.dumps(c.DEFAULT_CONFIG))
        cfg["ewma"]["max_seed_weight"] = 1.0                 # burn-in 1 for the hand example
        rv = {0: 1e-4, DAY: 2e-4, 2 * DAY: 3e-4}
        v, info = c.ewma_forecast(rv, 2 * DAY, cfg)
        # s1 = 1e-4; s2 = .94*1e-4 + .06*2e-4 = 1.06e-4; s3 = .94*1.06e-4 + .06*3e-4 = 1.1764e-4
        self.assertAlmostEqual(v, 1.1764e-4, places=16)
        self.assertEqual(info["run_days"], 3)
        rv[DAY] = None                                       # a gap restarts the recursion
        self.assertAlmostEqual(c.ewma_forecast(rv, 2 * DAY, cfg)[0], 3e-4, places=16)

    def test_ewma_burn_in_rule(self):
        self.assertEqual(c.ewma_burn_in(), 50)               # .94^49 = 0.0483 <= 0.05 < .94^48 = 0.0513
        self.assertLessEqual(0.94 ** 49, 0.05)
        self.assertGreater(0.94 ** 48, 0.05)
        rv = {d * DAY: 1e-4 for d in range(49)}
        with self.assertRaisesRegex(c.ModelRefused, "burn-in"):
            c.ewma_forecast(rv, 48 * DAY)
        rv[49 * DAY] = 1e-4
        self.assertAlmostEqual(c.ewma_forecast(rv, 49 * DAY)[0], 1e-4, places=16)

    def test_rv_definition(self):
        cfg = c.DEFAULT_CONFIG
        d = c.SYN_DAY0
        prices = [100 * math.exp(0.01 * k * (-1) ** k) for k in range(24)]
        marks = [(d + k * HOUR + 20, p) for k, p in enumerate(prices)]
        marks.append((d + 3 * HOUR + 50, 999.0))             # second row in a slot: ignored
        sl = c.to_slots(marks, cfg)
        rv, n, cut = c.day_rv(sl, d, cfg)
        want = math.fsum(math.log(prices[k] / prices[k - 1]) ** 2 for k in range(1, 24))
        self.assertEqual(n, 24)
        self.assertAlmostEqual(rv, want, places=15)
        self.assertEqual(cut, d + 23 * HOUR + 20)
        bad = c.to_slots([(t, p if t != d + 5 * HOUR + 20 else 0.0) for t, p in marks], cfg)
        self.assertEqual(c.day_rv(bad, d, cfg)[:2], (None, 23))  # invalid price = missing, never filled

    def test_ols_exact(self):
        rng = random.Random(3)
        X = [[1.0, rng.random(), rng.random(), rng.random()] for _ in range(50)]
        b = [0.5, -1.0, 2.0, 0.25]
        y = [sum(bi * xi for bi, xi in zip(b, row)) for row in X]
        for got, want in zip(c.ols(X, y), b):
            self.assertAlmostEqual(got, want, places=9)
        with self.assertRaises(c.ModelRefused):
            c.ols([[1.0, 1.0]] * 5, [1.0] * 5)

    def test_har_coefficients_recovered(self):
        n = 15000
        cfg = small_cfg(n - 40)
        marks, _ = c.synth_marks(("SYNA",), n, seed=51)
        sl = c.to_slots(marks["SYNA"], cfg)
        last = c.SYN_DAY0 + (n - 1) * DAY
        rv = c.rv_series(sl, c.SYN_DAY0, last, cfg)
        b, rows = c.har_fit(rv, last, cfg)
        self.assertEqual(rows, n - 40)
        b0, b1, b7, b30 = c.SYN_HAR
        self.assertAlmostEqual(b[0] / b0, 1.0, delta=0.15)
        for got, want in zip(b[1:], (b1, b7, b30)):
            self.assertAlmostEqual(got, want, delta=0.05)
        self.assertAlmostEqual(sum(b[1:]), b1 + b7 + b30, delta=0.02)

    def test_har_window_and_forecast(self):
        cfg = small_cfg(60)
        self.assertEqual(c.har_input_span(1000 * DAY, cfg), ((1000 - 89) * DAY, 1000 * DAY))
        self.assertEqual(c.har_input_span(1000 * DAY)[0], (1000 - 394) * DAY)    # default: 395 days
        rv = {d * DAY: 1e-4 * (1 + 0.1 * math.sin(d) + 0.05 * math.cos(3.1 * d)) for d in range(200)}
        v, info = c.har_forecast(rv, 199 * DAY, cfg)
        self.assertEqual(info["rows"], 60)
        b = info["coefs"]
        f = c._features(rv, 199 * DAY)
        self.assertAlmostEqual(v, sum(x * y for x, y in zip(b, f)), places=18)
        rv[150 * DAY] = None
        with self.assertRaisesRegex(c.ModelRefused, "min_rows"):
            c.har_forecast(rv, 199 * DAY, cfg)

    def test_hac_matches_hypo_engine_convention(self):
        from research.tools import hypo_engine
        rng = random.Random(9)
        x = [rng.gauss(0.01, 1) + (0.3 * i % 7) / 10 for i in range(300)]
        t, m, _ = c.hac_t(x, 5)
        t2, m2 = hypo_engine.hac_t(x, lags=5)
        self.assertAlmostEqual(t, t2, places=10)
        self.assertAlmostEqual(m, m2, places=14)
        self.assertAlmostEqual(c.p_one(1.6448536269514722), 0.05, places=9)
        self.assertEqual(c.DEFAULT_CONFIG["dm"]["nw_lags"], 5)             # F2: Newey-West, 5 lags


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="c1_e2e_")

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_synthetic_run_produces_dm_without_network_and_writes_only_out_dir(self):
        before = sorted(os.listdir(HERE))
        out = os.path.join(self.root, "out")
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.object(socket, "socket", no_network), \
                    mock.patch.object(socket, "create_connection", no_network), \
                    mock.patch.object(socket, "getaddrinfo", no_network):
                rep = c.synthetic_run(out, seed=5, symbols=("SYNA", "SYNB", "SYNC"), eval_days=25,
                                      cfg=small_cfg(60))
        finally:
            os.chdir(cwd)
        ev = rep["evaluation"]
        self.assertTrue(math.isfinite(ev["dm_t"]))
        self.assertTrue(0 <= ev["p_one"] <= 1)
        self.assertEqual(ev["T"], 25)
        self.assertEqual(ev["coin_days"], 75)
        self.assertEqual(ev["counts"]["revealed_ok"], 150)
        self.assertEqual(rep["refused"], {"model": 0, "forecast": 0})
        self.assertEqual(sorted(os.listdir(self.root)), ["out"])
        self.assertEqual(sorted(os.listdir(out)), ["c1_synthetic_journal.jsonl", "c1_synthetic_journal.jsonl.head",
                                                   "c1_synthetic_report.json"])
        self.assertEqual(sorted(os.listdir(HERE)), before)
        es = c.verify_file(os.path.join(out, "c1_synthetic_journal.jsonl"))
        self.assertTrue(all(e["created_ts" if e["kind"] != "reveal" else "revealed_ts"] >= c.SYN_DAY0 for e in es))
        self.assertTrue(es[0]["synthetic"])
        again = c.synthetic_run(os.path.join(self.root, "again"), seed=5, symbols=("SYNA", "SYNB", "SYNC"),
                                eval_days=25, cfg=small_cfg(60))
        self.assertEqual(again["evaluation"], ev)                          # deterministic
        self.assertEqual(again["journal_head"], rep["journal_head"])

    def test_module_imports_no_network_modules(self):
        with open(SRC, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
        self.assertFalse(mods & {"socket", "urllib", "http", "ssl", "requests", "aiohttp", "httpx", "websocket",
                                 "websockets", "ftplib", "smtplib", "subprocess"}, mods)
        with open(SRC, encoding="utf-8") as fh:
            src = fh.read()
        for word in ("pm_lp", "systemctl", "https://", "http://"):
            self.assertNotIn(word, src)


class Coverage(unittest.TestCase):
    """The counts-only reader on a synthetic census database (never the lab database)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="c1_cov_")
        self.db = os.path.join(self.root, "lab.db")
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts INTEGER, detector TEXT, metric TEXT, "
                    "payload TEXT)")
        con.execute("INSERT INTO observations(ts, detector, metric, payload) VALUES (?, 'census/1', 'snapshot', "
                    "'not json: a 2024 row must never be read')", (calendar.timegm((2024, 3, 1, 0, 0, 0)),))
        start = calendar.timegm((2026, 10, 27, 15, 0, 0))
        self.start = start
        self.end = calendar.timegm((2026, 11, 6, 13, 0, 0))
        gap = {calendar.timegm((2026, 10, 31, h, 0, 0)) for h in (4, 5)}
        for s in range(start, self.end + HOUR, HOUR):
            if s in gap:
                continue
            rows = {"BTCUSDT": [1.0, 1.0, 0.0001, 1.0], "ETHUSDT": [2.0, 2.0, 0.0001, 2.0],
                    "NEWUSDT": [3.0, 3.0, 0.0, None]}
            if s < calendar.timegm((2026, 11, 2, 0, 0, 0)):
                del rows["NEWUSDT"]
            if s == calendar.timegm((2026, 11, 3, 7, 0, 0)):
                rows["ETHUSDT"][0] = None                    # one bad ETH mark
            p = {"columns": ["markPrice", "indexPrice", "lastFundingRate", "lastPrice"], "rows": rows,
                 "premium_time_ms": (s + 30) * 1000}
            con.execute("INSERT INTO observations(ts, detector, metric, payload) VALUES (?, 'census/1', 'snapshot', "
                        "?)", (s + 30, json.dumps(p)))
        con.commit()
        con.close()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_counts_and_first_valid_dates(self):
        with open(self.db, "rb") as fh:
            before = fh.read()
        with mock.patch.object(socket, "socket", no_network):
            rep = c.coverage_report(self.db, now=self.end + 1800)
        with open(self.db, "rb") as fh:
            self.assertEqual(fh.read(), before)             # read-only
        s = rep["snapshots"]
        self.assertEqual((s["expected_slots"], s["present_slots"], s["missing_slots"]), (239, 237, 2))
        self.assertEqual(rep["days"]["incomplete_days"], ["2026-10-31"])
        self.assertEqual(rep["days"]["current_run_start"], "2026-11-01")
        fv = rep["first_valid_if_no_more_gaps"]
        self.assertEqual(fv["har_rv_1_7_30"]["first_target_day"], "2027-12-01")   # 11-01 + 395 days
        self.assertEqual(fv["ewma_094"]["first_target_day"], "2026-12-21")        # 11-01 + 50 days
        eth = rep["fields"]["markPrice"]["focus"]["ETHUSDT"]
        self.assertEqual(eth["current_run_start"], "2026-11-04")
        self.assertIn("2026-11-03", eth["incomplete_days"])
        self.assertEqual(rep["fields"]["markPrice"]["symbols"], 3)
        self.assertEqual(rep["fields"]["lastPrice"]["symbols"], 2)                 # None never counts
        txt = json.dumps(rep)
        for price in ("1.0, 1.0", "2.0, 2.0"):
            self.assertNotIn(price, txt)
        self.assertIn("2026-11-06", c.coverage_md(rep))

    def test_refuses_to_read_before_forward_start(self):
        con = c.open_ro(self.db)
        try:
            with self.assertRaises(c.C1Error):
                c.census_presence(con, since=calendar.timegm((2024, 1, 1, 0, 0, 0)))
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("INSERT INTO observations(ts) VALUES (1)")
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
