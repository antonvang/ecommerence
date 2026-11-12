"""Director order 102: the forward paper book v2 (96 tests) on synthetic 5m bars only, the register review and the
final amendment's sha256. Databases live in a temporary directory; no market data, no network, no activation."""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_filters as ff  # noqa: E402
from research.tools import event_farm_forward as fw  # noqa: E402
from research.tools import event_farm_forward_v2 as fv  # noqa: E402

BS = 300
SYMS = ["SYN1", "SYN2"]
CFG = {"warmup_bars": 50, "coverage_window_bars": 40}
AMEND = os.path.join(HERE, "research", "desk", "EVENT_FARM_FORWARD_AMENDMENT_FINAL_102.md")
SHAFILE = AMEND[:-3] + ".sha256"


def damaged(seed, days):
    """A synthetic series with missing bars (incomplete hours, gaps) and bars without volume (VWAP blocked)."""
    out = []
    for k, b in enumerate(ef.random_walk_bars(seed, days)):
        if k in (130, 131, 700, 1005):
            continue
        if k in (300, 1100):
            b = b[:5] + (0.0,)
        out.append(b)
    return out


def series():
    return {"SYN1": damaged(41, 5), "SYN2": ef.random_walk_bars(42, 5)}


class Run:
    def __init__(self, tmp, name, cls=fv.ForwardBookV2, config=CFG):
        self.src, self.now, self.cls, self.config = fw.SyntheticSource(), [0], cls, config
        self.path = os.path.join(tmp, name)
        self.book = self.open()

    def open(self):
        return self.cls(self.path, self.src, SYMS, clock=lambda: self.now[0], config=self.config)

    def feed_until(self, bars, t_end):
        """Publish every not yet published bar that has closed by t_end, then step once with the clock at t_end."""
        self.done = getattr(self, "done", {x: 0 for x in SYMS})
        for x in SYMS:
            new = [b for b in bars[x][self.done[x]:] if b[0] + BS <= t_end]
            self.src.publish(x, new)
            self.done[x] += len(new)
        self.now[0] = t_end
        return self.book.step()


def feed_bar_by_bar(run, bars):
    t0 = min(b[0] for s in SYMS for b in bars[s])
    t1 = max(b[0] for s in SYMS for b in bars[s]) + BS
    published = {s: 0 for s in SYMS}
    for t in range(t0 + BS, t1 + BS, BS):
        for s in SYMS:
            new = [b for b in bars[s][published[s]:] if b[0] + BS <= t]
            run.src.publish(s, new)
            published[s] += len(new)
        run.now[0] = t
        run.book.step()
    for _ in range(3):                                 # let the last gaps be declared (no newer bar: nothing waits)
        run.book.step()


def offline(bars, warmup):
    """All 96 tests over the full series: baseline setups from the warmup on, filtered with the full-series context."""
    out = {}
    for s, bb in bars.items():
        ctx = ff.context(bb)
        events = ef.detect(bb, ef.params())
        for v in ef.VARIANTS:
            vid = ef._variant_id(v)
            pv = ef.params(**v)
            setups, _ = ef.build_setups(events, bb, pv)
            for x in setups:
                if x["known_i"] < warmup:
                    continue
                o = ef.setup_outcome(x, bb, pv)
                val = (x["entry"], x["stop"], x["target"], "pending" if o["status"] == "incomplete" else o["status"],
                       o["exit_px"])
                for combo in ("base",) + ff.COMBOS:
                    if combo == "base" or ff.passes(x, ctx, combo):
                        out[(f"{combo}/{vid}", s, x["known_ts"], x["kind"])] = val
    return out


def booked(book):
    rows = book.db.execute("SELECT variant, symbol, known_ts, kind, entry, stop, target, status, exit_px FROM trades "
                           "WHERE status NOT LIKE 'not_taken%'").fetchall()
    return {r[:4]: tuple(r[4:]) for r in rows}


class LivePath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bars = series()
        cls.one = Run(cls.tmp.name, "event_farm_forward_v2_one.db")
        feed_bar_by_bar(cls.one, cls.bars)
        cls.chunk = Run(cls.tmp.name, "event_farm_forward_v2_chunk.db")
        t0 = cls.bars["SYN2"][0][0]
        t1 = cls.bars["SYN2"][-1][0] + BS
        for t in list(range(t0 + 50 * BS, t1, 97 * BS)) + [t1]:
            cls.chunk.feed_until(cls.bars, t)
        for _ in range(3):
            cls.chunk.book.step()

    @classmethod
    def tearDownClass(cls):
        cls.one.book.close()
        cls.chunk.book.close()
        cls.tmp.cleanup()

    def test_processed_bars_are_the_series_without_holes(self):
        for s in SYMS:
            self.assertEqual(self.one.book.bars[s], self.bars[s])
        self.assertEqual(self.one.book.db.execute("SELECT COUNT(*) FROM gaps").fetchone()[0], 3)

    def test_bar_by_bar_equals_offline_for_all_96_tests(self):
        want = offline(self.bars, CFG["warmup_bars"])
        got = booked(self.one.book)
        self.assertEqual(got, want)
        combos = {k[0].split("/")[0] for k in got}
        self.assertTrue({"base", "F1", "F3"} <= combos, combos)
        self.assertEqual({t for t, _ in self.one.book.variants}, set(ff.all_forward_tests()))

    def test_batching_gives_the_same_book(self):
        self.assertEqual(self.one.book.dump(), self.chunk.book.dump())

    def test_live_context_uses_only_bars_up_to_k(self):
        for s in SYMS:
            bb = self.bars[s]
            full = ff.context(bb)
            for k in range(len(bb)):
                live = self.one.book.point_context(s, k)
                self.assertEqual(live["trend"][k], full["trend"][k], (s, k))
                self.assertEqual(live["pd"][k], full["pd"][k], (s, k))
                self.assertEqual(live["vwap"][k], full["vwap"][k], (s, k))
            self.assertEqual(self.one.book.trend[s].states, ff.trend_1h(bb))

    def test_incomplete_hours_and_missing_volume_in_the_live_path(self):
        bb = self.bars["SYN1"]
        ts = [b[0] for b in bb]
        k_zero = ts.index(ef.START + 300 * BS)                       # the bar with volume 0
        st = [self.one.book.point_context("SYN1", k)["vwap"][k][1] for k in range(len(bb))]
        self.assertEqual(st[k_zero - 1], "OK")
        day_end = ts.index(ef.START + 575 * BS)                     # last bar of that UTC day
        self.assertEqual(set(st[k_zero:day_end + 1]), {"INCOMPLETE"})
        self.assertEqual(st[day_end + 1], "OK")
        rows = self.one.book.db.execute("SELECT variant, known_i FROM trades WHERE symbol = 'SYN1' AND variant LIKE '%F3%' "
                                        "AND status NOT LIKE 'not_taken%'").fetchall()
        self.assertTrue(all(st[k] == "OK" for _, k in rows))
        tr = fv.Trend1H()
        for b in bb[:200]:
            tr.step(b)
        self.assertEqual(len(tr.h1), 15)                             # 16 hours, hour 10 (bars 130, 131 missing) dropped

    def test_known_ts_of_every_booked_test(self):
        bb = self.bars["SYN1"]
        for known_ts, k, fill_ts in self.one.book.db.execute(
                "SELECT known_ts, known_i, fill_ts FROM trades WHERE symbol = 'SYN1'"):
            self.assertEqual(known_ts, bb[k][0] + BS)
            if fill_ts is not None:
                self.assertGreaterEqual(fill_ts + BS, known_ts)

    def test_dedup_and_idempotence(self):
        before = self.one.book.dump(with_steps=True)
        self.one.src.push_once("SYN2", self.bars["SYN2"][10:20])
        self.assertEqual(set(self.one.book.step().values()), {0})
        self.assertEqual(self.one.book.dump(with_steps=True), before)

    def test_report_v2_covers_96_tests(self):
        r = fv.report_v2(self.one.book)
        self.assertEqual((r["n_tests"], r["reference_n"]), (96, 19849))
        self.assertIn("ingen evidens", r["label"])


class Restart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bars = {"SYN1": damaged(51, 2), "SYN2": ef.random_walk_bars(52, 2)}

    def test_reopen_and_crash_replay_are_identical(self):
        ref = Run(self.tmp.name, "event_farm_forward_v2_ref.db")
        feed_bar_by_bar(ref, self.bars)
        half = {s: [b for b in self.bars[s] if b[0] < ef.START + 280 * BS] for s in SYMS}
        r = Run(self.tmp.name, "event_farm_forward_v2_re.db")
        feed_bar_by_bar(r, half)
        r.book.close()
        r.book = r.open()
        self.assertEqual(r.book.trend["SYN1"].states, ff.trend_1h(r.book.bars["SYN1"]))
        before = r.book.dump(with_steps=True)
        calls = {"n": 0}
        real = r.book._insert

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 25:
                raise OSError("simulated crash")
            return real(*a, **k)
        rest = {s: [b for b in self.bars[s] if b[0] >= ef.START + 280 * BS] for s in SYMS}
        for s in SYMS:
            r.src.publish(s, rest[s])
        r.now[0] = self.bars["SYN2"][-1][0] + BS
        with mock.patch.object(r.book, "_insert", side_effect=flaky):
            with self.assertRaises(OSError):
                r.book.step()
        self.assertEqual(r.book.dump(with_steps=True), before)
        r.book.step()
        for _ in range(3):
            r.book.step()
        self.assertEqual(r.book.dump(), ref.book.dump())
        r.book.close()
        ref.book.close()

    def test_v1_and_v2_files_are_not_interchangeable(self):
        r1 = Run(self.tmp.name, "event_farm_forward_x.db", cls=fw.ForwardBook)
        feed_bar_by_bar(r1, {s: self.bars[s][:20] for s in SYMS})
        r1.book.close()
        with self.assertRaises(fw.IntegrityHalt):
            fv.ForwardBookV2(r1.path, r1.src, SYMS, clock=lambda: 0, config=CFG)

    def test_live_mode_is_not_activated(self):
        with mock.patch("sqlite3.connect", side_effect=AssertionError("database opened")):
            with self.assertRaises(fw.NotActivated):
                fv.ForwardBookV2(os.path.join(self.tmp.name, "event_farm_forward_live.db"),
                                 fw.SyntheticSource({"source": "x"}), list(fw.LIVE_SYMBOLS), mode="live")


class Register(unittest.TestCase):
    def test_96_tests_and_n_19849_match_the_records(self):
        from research.tools import factory, register_v2 as v2
        recs = fv.v2_final_records("2026-12-01", "2027-02-28")
        self.assertEqual(len(recs), 19)
        for r in recs:
            self.assertEqual(v2.validate(r), [])
            self.assertEqual(r["era"], v2.FUTURE)
            self.assertEqual(r["variants_tested"], v2.MISSING_INPUT)
            self.assertFalse(r["parameters"]["values"]["independent_lineage"])
        c = fv.register_counts(recs)
        self.assertEqual(c["covered"], 96)
        self.assertEqual(c["universe"], [96])
        self.assertEqual(c["reference_n"], [19849])
        self.assertEqual(c["members_sha256"], [factory.sha(ff.all_forward_tests())])
        self.assertEqual(ff.reference_n(), 19753 + 96)

    def test_the_v1_plan_is_superseded_by_revisions_of_the_same_ids(self):
        from research.tools import register_v2 as v2
        old = {r["record_id"]: r for r in fw.v2_plan_records("2026-12-01", "2027-02-28")}
        new = {r["record_id"]: r for r in fv.v2_final_records("2026-12-01", "2027-02-28")}
        self.assertTrue(set(old) <= set(new))
        for rid, o in old.items():
            self.assertEqual(o["parameters"]["values"]["reference_n_forward"], 19765)
            self.assertEqual(o["trial_universe"]["size"], 12)
            chain = []
            v2.chain_append(chain, o, "2026-11-12")
            v2.chain_append(chain, new[rid], "2026-11-12")
            v2.chain_verify(chain)


class FinalText(unittest.TestCase):
    def test_sha256_file_matches_the_amendment(self):
        with open(SHAFILE, encoding="utf-8") as f:
            line = f.read().split()
        self.assertEqual(line[0], fv.file_sha256(AMEND))
        self.assertEqual(line[1], os.path.basename(AMEND))

    def test_the_amendment_names_the_current_code_sha256(self):
        with open(AMEND, encoding="utf-8") as f:
            text = f.read()
        for rel in ("event_farm.py", "event_farm_driver.py", "event_farm_forward.py", "event_farm_filters.py",
                    "event_farm_forward_v2.py"):
            sha = fv.file_sha256(os.path.join(HERE, "research", "tools", rel))
            self.assertIn(f"`research/tools/{rel}` | `{sha}`", text, rel)
        self.assertIn("ANTAGELSE", text)
        self.assertIn("19.849", text)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
