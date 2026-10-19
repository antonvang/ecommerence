"""F2 dbasis (amendment 8, instrument model spot_delivery_ratio): calendar and rolls, the synthetic convergence test,
the stitched transform on synthetic Binance-layout zips, flat roll bars, the rules, the embargo / coverage / approval
guards, an end-to-end screen through the real pipeline, and F1 left unchanged. No network: data._fetch refuses every
file that is not on disk, and the coverage check gets an injected HEAD."""
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lab import families, fleet, jobs, lifecycle, pipeline  # noqa: E402
from lab.engine import adversarial, backtest, catalogue, data  # noqa: E402
from lab.families import dbasis  # noqa: E402
from tests.test_lab_families import CLEAN, FR, KL, A3Base, _pzip, problems_of, ts  # noqa: E402

HOUR, DAY = 3600, 86400
COINS = ("XRPUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT")
DRAFT = os.path.join(families.FAMILY_DIR, "drafts", "dbasis.json")    # not read by discovery until it moves
DBASIS = families.load(DRAFT)


def utc(t):
    return datetime.fromtimestamp(t, timezone.utc)


def write_market(root, symbols, span, seed=3, high=0.15, low=0.02, drop=()):
    """Perp, spot (open times in microseconds) and funding zips as in test_lab_families, plus the COIN-M quarterlies:
    every contract trades from 10 days before it is held to its expiry (rows outside the held window must be ignored),
    with F = S * (1 + lock * (e - t) / (e - f0)) * small noise, lock = annual basis * (e - f0) / year; the annual basis
    alternates `high` and `low` per contract and coin. `drop` = {(coin, ts)} hours missing from the held quarterly."""
    rng = random.Random(seed)
    a, b = span
    held = data.quarterlies(a, b - HOUR)
    for j, sym in enumerate(symbols):
        px, perp, spot, fund, S = 100.0 + 10 * j, {}, {}, {}, {}
        for t in range(a - 20 * DAY, b, HOUR):
            o = px
            px *= 1 + rng.gauss(0, 0.003)
            S[t] = px
            if t < a:
                continue
            d = utc(t)
            perp.setdefault((d.year, d.month), []).append([t * 1000, o, max(o, px), min(o, px), px, 1, t * 1000 + 3599999])
            spot.setdefault((d.year, d.month), []).append([t * 10 ** 6, o, max(o, px), min(o, px), px, 1,
                                                           t * 10 ** 6 + 3599999999])
            if t % (8 * HOUR) == 0:
                fund.setdefault((d.year, d.month), []).append([t * 1000, 8, 0.0001])
        for (y, m), rows in perp.items():
            _pzip(os.path.join(root, "klines", f"{sym}-1h-{y}-{m:02d}.zip"), KL, rows)
            _pzip(os.path.join(root, "spot_klines", f"{sym}-1h-{y}-{m:02d}.zip"), KL, spot[(y, m)])
            _pzip(os.path.join(root, "funding", f"{sym}-fundingRate-{y}-{m:02d}.zip"), FR, fund[(y, m)])
        for k, (e, f0, f1) in enumerate(held):
            ann = high if (k + j) % 2 == 0 else low
            lock = ann * (e - f0) / (365 * DAY)
            c, rows, prev = data.delivery_symbol(sym, e), {}, None
            for t in range(max(a, f0 - 10 * DAY), min(b, e), HOUR):
                if (sym, t) in drop:
                    continue
                fv = S[t] * (1 + lock * (e - t) / (e - f0)) * (1 + rng.gauss(0, 0.0001))
                o = prev if prev is not None else fv
                d = utc(t)
                rows.setdefault((d.year, d.month), []).append([t * 1000, o, max(o, fv), min(o, fv), fv, 1,
                                                               t * 1000 + 3599999])
                prev = fv
            for (y, m), r in rows.items():
                _pzip(os.path.join(root, "cm_klines", f"{c}-1h-{y}-{m:02d}.zip"), KL, r)


class Calendar(unittest.TestCase):
    def test_binance_quarterly_expiries_and_rolls(self):
        want = ["2022-03-25", "2022-06-24", "2022-09-30", "2022-12-30", "2023-03-31", "2023-06-30", "2023-09-29",
                "2023-12-29", "2024-03-29", "2024-06-28", "2024-09-27", "2024-12-27"]
        got = [utc(data.quarterly_expiry(y, m)).strftime("%Y-%m-%d") for y in (2022, 2023, 2024) for m in (3, 6, 9, 12)]
        self.assertEqual(got, want)
        for y in (2022, 2023, 2024):
            for m in (3, 6, 9, 12):
                e = data.quarterly_expiry(y, m)
                r = data.roll_time(e)
                self.assertEqual((utc(e).strftime("%a %H:%M"), utc(r).strftime("%a %H:%M"), e - r),
                                 ("Fri 08:00", "Wed 01:00", 55 * HOUR))
        with self.assertRaises(ValueError):
            data.quarterly_expiry(2023, 4)

    def test_held_contracts_are_contiguous_and_named(self):
        a, b = data.window_bounds("train3")
        held = data.quarterlies(a, b)
        self.assertEqual(held[0][1] <= a < held[0][2], True)
        self.assertTrue(all(x[2] == y[1] for x, y in zip(held, held[1:])))
        self.assertEqual(data.delivery_symbol("ADAUSDT", data.quarterly_expiry(2023, 3)), "ADAUSD_230331")
        plan = data.delivery_plan("LINKUSDT", "validation3")
        self.assertEqual([c["contract"] for c in plan], ["LINKUSD_230929", "LINKUSD_231229", "LINKUSD_240329"])
        self.assertEqual([os.path.basename(p) for _, p in plan[0]["files"]],
                         ["LINKUSD_230929-1h-2023-07.zip", "LINKUSD_230929-1h-2023-08.zip",
                          "LINKUSD_230929-1h-2023-09.zip"])
        self.assertTrue(plan[0]["files"][0][0].startswith(
            "https://data.binance.vision/data/futures/cm/monthly/klines/LINKUSD_230929/1h/"))
        self.assertEqual(len(data.expected_paths("LINKUSDT", "validation3", spot=True, delivery=True)["delivery"]),
                         sum(len(c["files"]) for c in plan))


class ConvergenceSelftest(unittest.TestCase):
    def test_every_criterion_passes(self):
        r = dbasis.convergence_selftest()
        self.assertEqual(len(r["checks"]), 8)
        self.assertTrue(r["ok"], [k for k, ok in r["checks"].items() if not ok])

    def test_a_broken_stitch_fails_it(self):
        with mock.patch.object(dbasis, "roll_bars", lambda bars, held: set()):        # no flat roll bar
            r = dbasis.convergence_selftest()
        self.assertFalse(r["ok"])
        self.assertFalse(r["checks"]["4 no return is earned between two contracts"])


class Transform(unittest.TestCase):
    """The stitched spot_delivery_ratio series on synthetic zips (2022-01..2022-07: two rolls)."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="dbasis_tr")
        cls.span = (ts(2022, 1, 1), ts(2022, 8, 1))
        drop = {("ADAUSDT", data.roll_time(data.quarterly_expiry(2022, 6)))}       # the June roll bar is missing
        write_market(cls.root, COINS[:3], cls.span, drop=drop)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        def no_fetch(url, path, get=None):
            if os.path.exists(path):
                return path
            raise AssertionError(f"a test tried to fetch {url}")
        self.p = [mock.patch.dict(data.SPLITS, {"t1": ((2022, 1), (2022, 7))}),
                  mock.patch.object(data, "CACHE", self.root), mock.patch.object(data, "_fetch", no_fetch)]
        for p in self.p:
            p.start()
        self.per = {s: {**data.files_for(s, "t1"), "spot": data.spot_files_for(s, "t1"),
                        "delivery": data.delivery_files_for(s, "t1")} for s in COINS[:3]}
        self.spec = {"family": "dbasis", "instrument_model": "spot_delivery_ratio"}

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()

    def test_the_ratio_is_spot_over_the_held_quarterly(self):
        bars, funding, dups, fd = families.transform(self.spec, self.per, "t1")
        self.assertEqual(funding, {s: {} for s in COINS[:3]})                          # no funding
        self.assertTrue(all(fd.perp[s] for s in COINS[:3]))                           # the benchmark's perps
        a, b = data.window_bounds("t1")
        held = data.quarterlies(a, b)
        s = "XRPUSDT"
        sp = {t: c for t, _, c in data.load({"klines": self.per[s]["spot"], "funding": []}, "t1")[0]}
        for t, o, c in bars[s][::97]:
            e = dbasis.expiry_at(t, held)
            con = next(x for x in self.per[s]["delivery"] if x["expiry"] == e)
            fut = {x[0]: x[2] for x in data.load({"klines": con["paths"], "funding": []}, "t1")[0]}
            self.assertAlmostEqual(c, sp[t] / fut[t], places=12)
        self.assertEqual(len(bars[s]), (b - a + 1) // HOUR)                            # every hour, once
        self.assertEqual(dups[s], 0)

    def test_rows_outside_the_held_window_are_ignored(self):
        bars, *_ = families.transform(self.spec, self.per, "t1")
        r = data.roll_time(data.quarterly_expiry(2022, 3))
        march = next(x for x in self.per["XRPUSDT"]["delivery"] if x["contract"] == "XRPUSD_220325")
        fut = {x[0]: x[2] for x in data.load({"klines": march["paths"], "funding": []}, "t1")[0]}
        self.assertIn(r + HOUR, fut)                                                   # March still trades after
        june = next(x for x in self.per["XRPUSDT"]["delivery"] if x["contract"] == "XRPUSD_220624")
        jf = {x[0]: x[2] for x in data.load({"klines": june["paths"], "funding": []}, "t1")[0]}
        bar = next(x for x in bars["XRPUSDT"] if x[0] == r + HOUR)
        sp = {t: c for t, _, c in data.load({"klines": self.per["XRPUSDT"]["spot"], "funding": []}, "t1")[0]}
        self.assertAlmostEqual(bar[2], sp[r + HOUR] / jf[r + HOUR], places=12)         # the June contract is held

    def test_a_missing_quarterly_hour_lowers_coverage_and_the_next_bar_is_flat(self):
        bars, *_ = families.transform(self.spec, self.per, "t1")
        r = data.roll_time(data.quarterly_expiry(2022, 6))
        self.assertNotIn(r, [x[0] for x in bars["ADAUSDT"]])
        q = data.quality(bars["ADAUSDT"], "t1")
        self.assertLess(q["coverage"], 1.0)
        for fn, p in (("basis_threshold", {"theta": 0.01}), ("basis_cross_section", {"k": 3})):
            pos = getattr(dbasis, fn)(bars, {}, p)
            i = next(k for k, x in enumerate(bars["ADAUSDT"]) if x[0] > r)            # the first bar after the gap
            self.assertEqual(pos["ADAUSDT"][i], 0.0, fn)

    def test_each_roll_charges_both_legs_twice(self):
        bars, *_ = families.transform(self.spec, self.per, "t1")
        s = "XRPUSDT"
        held = data.quarterlies(*data.window_bounds("t1"))
        pos = dbasis._apply(bars[s], held, [(bars[s][0][0], 1.0)])                     # held throughout
        costs = {"taker_fee": 0.0015, "half_spread": 0.0006, "slippage": 0.0006}
        rows = backtest.apply_costs(backtest.gross(bars[s], pos), {}, costs)
        rolls = dbasis.roll_bars(bars[s], held)
        self.assertEqual(len(rolls), 2)
        fee = sum(r[3] for r in rows)
        self.assertAlmostEqual(fee, (1 + 2 * len(rolls)) * costs["taker_fee"], places=12)   # entry + 2 per roll
        self.assertEqual({i for i in range(len(pos)) if pos[i] == 0.0}, rolls)


def bars_from(points):
    """Hand-made stitched bars: [(ts, ratio)] -> [(ts, ratio, ratio)]."""
    return [(t, r, r) for t, r in points]


class Attribution(unittest.TestCase):
    """The cash flow is the carry the held contract accrues while held; the rest of the gross is basis and price
    P&L (amendment 8 point 8)."""

    def one_contract(self, ann=0.10):
        a = ts(2022, 4, 1)
        held = data.quarterlies(a, ts(2022, 6, 20))
        e, f0, _ = held[0] if dbasis.expiry_at(a, held) == held[0][0] else held[1]
        lock = ann * (e - f0) / (365 * DAY)
        return [(t, 0, 1 / (1 + lock * (e - t) / (e - f0))) for t in range(a, ts(2022, 6, 20), HOUR)], held

    def att(self, bars, pos):
        rows = {"X": backtest.apply_costs(backtest.gross(bars, pos), {}, {"taker_fee": 0.0015, "half_spread": 0.0006,
                                                                         "slippage": 0.0006})}
        return dbasis.attribution(backtest.metrics(backtest.portfolio(rows)), {"X": bars}, {"X": pos})

    def test_churn_never_raises_the_carry(self):
        bars, held = self.one_contract()
        full = self.att(bars, [1.0] * len(bars))
        weekly = self.att(bars, [1.0 if (t // (7 * DAY)) % 2 == 0 else 0.0 for t, _, _ in bars])
        self.assertLess(weekly["locked_basis_carry"], full["locked_basis_carry"])
        self.assertAlmostEqual(full["gross_ratio_pnl"], full["locked_basis_carry"], delta=2e-4)
        self.assertFalse(weekly["gates"]["locked basis carry - costs > 0"])            # churn: costs > carry

    def test_a_level_that_never_converges_accrues_no_carry(self):
        """Review of 3600c85 (N1): a constant USDT/USD offset, or a level that only oscillates and is traded on its
        swings, earns no carry; only the convergence a contract actually delivered counts."""
        a = ts(2022, 4, 4)
        flat = [(t, 0, 0.998) for t in range(a, a + 40 * DAY, HOUR)]
        r = self.att(flat, [1.0] * len(flat))
        self.assertAlmostEqual(r["locked_basis_carry"], 0.0, places=12)
        self.assertFalse(r["gates"]["locked basis carry - costs > 0"])
        wave = [(t, 0, 1 / (1.03 + 0.006 * math.sin(2 * math.pi * t / (10 * DAY)))) for t in range(a, a + 60 * DAY, HOUR)]
        book = [0.0] + [1.0 if 1 / wave[i - 1][2] > 1.03 else 0.0 for i in range(1, len(wave))]
        r = self.att(wave, book)
        self.assertFalse(all(r["gates"].values()), r)

    def test_a_widening_basis_is_basis_pnl_not_carry(self):
        a = ts(2022, 4, 4)
        held = data.quarterlies(a, a + 30 * DAY)
        e = dbasis.expiry_at(a, held)
        bars = []
        for k, t in enumerate(range(a, a + 30 * DAY, HOUR)):
            b = 0.03 + 0.05 * k / (30 * 24)                                             # 3 % widening to 8 %
            bars.append((t, 0, 1 / (1 + b * (e - t) / (365 * DAY))))
        r = self.att(bars, [1.0] * len(bars))
        self.assertLess(r["gross_ratio_pnl"], 0)
        self.assertLess(r["locked_basis_carry"], 0)                                    # it widened: no convergence
        self.assertFalse(r["gates"]["locked basis carry - costs > 0"])


class Rules(unittest.TestCase):
    """The three rules on hand-made ratio series inside one quarter (2022-04-01..2022-06-30)."""

    def series(self, basis_of_day):
        a = ts(2022, 4, 1)
        held = data.quarterlies(a, ts(2022, 7, 1))
        out = []
        for t in range(a, ts(2022, 7, 1), HOUR):
            e = dbasis.expiry_at(t, held)
            b = basis_of_day((t - a) // DAY)
            out.append((t, 1 / (1 + b * (e - t) / (365 * DAY))))
        return bars_from(out)

    def test_threshold_enters_exits_with_hysteresis_only_at_01_utc(self):
        b = self.series(lambda d: 0.12 if d < 10 else (0.06 if d < 20 else 0.02))
        pos = dbasis.basis_threshold({"X": b}, {}, {"theta": 0.10})["X"]
        changes = [b[i][0] for i in range(1, len(b)) if pos[i] != pos[i - 1]]
        held = data.quarterlies(b[0][0], b[-1][0])
        rolls = {b[i][0] for i in dbasis.roll_bars(b, held)}
        self.assertTrue(all(t % DAY == HOUR or t in rolls or t - HOUR in rolls for t in changes), changes)
        day = lambda d: ts(2022, 4, 1) + d * DAY + HOUR                                # noqa: E731
        idx = {x[0]: i for i, x in enumerate(b)}
        self.assertEqual(pos[idx[day(0)]], 1.0)                                         # 12 % >= 10 %
        self.assertEqual(pos[idx[day(12)]], 1.0)                                        # 6 % < 10 % but >= 5 %: keep
        self.assertEqual(pos[idx[day(21)]], 0.0)                                        # 2 % < 5 %: exit

    def test_threshold_exits_at_the_roll_and_needs_theta_again(self):
        r = data.roll_time(data.quarterly_expiry(2022, 6))
        a = ts(2022, 6, 1)
        held = data.quarterlies(a, ts(2022, 7, 15))
        pts = []
        for t in range(a, ts(2022, 7, 15), HOUR):
            e = dbasis.expiry_at(t, held)
            pts.append((t, 1 / (1 + 0.07 * (e - t) / (365 * DAY))))                   # 7 %: between theta/2 and theta
        b = bars_from(pts)
        idx = {x[0]: i for i, x in enumerate(b)}
        pos = dbasis.basis_threshold({"X": b}, {}, {"theta": 0.10})["X"]
        self.assertEqual(max(pos), 0.0)                                                # never at theta: never in
        hi = bars_from([(t, 1 / (1 + (0.12 if t < r else 0.07) * (dbasis.expiry_at(t, held) - t) / (365 * DAY)))
                        for t, _ in pts])
        pos = dbasis.basis_threshold({"X": hi}, {}, {"theta": 0.10})["X"]
        self.assertEqual(pos[idx[r - HOUR]], 1.0)                                       # held to the roll
        self.assertEqual(pos[idx[r]], 0.0)                                              # the flat roll bar
        self.assertEqual(pos[idx[r + 2 * HOUR]], 0.0)                                   # 7 % < theta: stays out

    def test_decisions_use_the_close_of_the_00_00_bar(self):
        b = self.series(lambda d: 0.12)
        i = next(k for k, x in enumerate(b) if x[0] % DAY == HOUR)                    # the first 01:00 bar
        poisoned = list(b)
        poisoned[i] = (b[i][0], 0.5, 0.5)                                               # its own prices: ignored
        self.assertEqual(dbasis.basis_threshold({"X": b}, {}, {"theta": 0.10})["X"][:i + 1],
                         dbasis.basis_threshold({"X": poisoned}, {}, {"theta": 0.10})["X"][:i + 1])

    def test_hold_to_roll_enters_only_the_day_after_a_roll(self):
        r = data.roll_time(data.quarterly_expiry(2022, 6))
        b = self.series(lambda d: 0.12)
        pos = dbasis.basis_hold_to_roll({"X": b}, {}, {"theta": 0.05})["X"]
        self.assertEqual(max(pos[:len(b) // 2]), 0.0)                                   # mid-quarter start: flat
        idx = {x[0]: i for i, x in enumerate(b)}
        self.assertEqual(pos[idx[r]], 0.0)                                              # the roll bar
        self.assertEqual(pos[idx[r + DAY - HOUR]], 0.0)                                 # still the roll day
        self.assertEqual(pos[idx[r + DAY]], 1.0)                                        # the day after the roll

    def test_cross_section_holds_the_k_highest_eligible_on_mondays(self):
        mk = lambda v: self.series(lambda d: v)                                         # noqa: E731
        bars = {"A": mk(0.20), "B": mk(0.10), "C": mk(0.06), "D": mk(0.03)}
        pos = dbasis.basis_cross_section(bars, {}, {"k": 2})
        monday = ts(2022, 4, 4) + HOUR
        i = next(k for k, x in enumerate(bars["A"]) if x[0] == monday + 2 * HOUR)
        self.assertEqual([pos[s][i] for s in "ABCD"], [1.0, 1.0, 0.0, 0.0])
        pos3 = dbasis.basis_cross_section(bars, {}, {"k": 5})
        self.assertEqual([pos3[s][i] for s in "ABCD"], [1.0, 1.0, 1.0, 0.0])            # D is below 5 %
        before = next(k for k, x in enumerate(bars["A"]) if x[0] == monday - 2 * HOUR)
        self.assertEqual([pos[s][before] for s in "ABCD"], [0.0] * 4)                   # first Monday not yet

    def test_exact_look_ahead_tests_pass_on_real_shapes(self):
        rng = random.Random(1)
        bars = {s: self.series(lambda d, s=s: 0.02 + 0.15 * rng.random()) for s in "ABC"}
        for fn, p in (("basis_threshold", {"theta": 0.10}), ("basis_hold_to_roll", {"theta": 0.05}),
                      ("basis_cross_section", {"k": 2})):
            f = getattr(dbasis, fn)
            self.assertTrue(adversarial.truncation_test_xs(f, bars, {s: {} for s in bars}, p)["ok"], fn)
            self.assertTrue(adversarial.poison_test_xs(f, bars, {s: {} for s in bars}, p)["ok"], fn)


class FileRules(unittest.TestCase):
    def fam(self, **u):
        f = json.loads(json.dumps(DBASIS))
        f["universe"].update(u)
        return f

    def test_the_draft_file_is_valid_and_not_discovered(self):
        self.assertEqual(families.validate(DBASIS), [])
        self.assertNotIn("dbasis", families.family_ids())                   # the discovery agent never sees it
        self.assertEqual(families.symbols(DBASIS), tuple(DBASIS["universe"]["symbols"]))

    def test_base_and_holdout_exclude_are_fixed(self):
        """Review of 3600c85 (N2): no covered coin can be left out through holdout_exclude or another base."""
        self.assertTrue(any("holdout_exclude exactly" in p for p in families.validate(
            self.fam(holdout_exclude=["BTCUSDT", "ETHUSDT", "SOLUSDT", "ETCUSDT"]))))
        self.assertTrue(any("universe.base must be 30v3" in p for p in families.validate(self.fam(base="8"))))
        self.assertEqual(len(families.delivery_candidates(self.fam(base="8"))), 27)

    def test_universe_rules(self):
        self.assertTrue(families.validate(self.fam(symbols=list(COINS[:4]), min_symbols=5)))       # < 5 coins
        self.assertTrue(any("BTC, ETH and SOL" in p for p in
                            families.validate(self.fam(symbols=["BTCUSDT"] + list(COINS[:5]), min_symbols=5))))
        self.assertTrue(any("min_symbols" in p for p in families.validate(self.fam(min_symbols=5))))
        self.assertTrue(families.validate(self.fam(symbols=list(COINS[:5]) + ["PEPEUSDT"], min_symbols=5)))

    def test_f1_is_unchanged_by_the_new_rules(self):
        self.assertEqual(problems_of(), [])
        self.assertFalse(families.delivery_model(families.load("fcarry")))
        files = families.expected_files(families.load("fcarry"))
        self.assertEqual({d: len(p) for d, p in files.items()},
                         {"data/lab/market/klines": 720, "data/lab/market/funding": 720,
                          "data/lab/market/spot_klines": 720})


class Guards(A3Base):
    """Point 17: no COIN-M request before 2026-11-28 (not even before 10-24, unlike spot), the coverage check is
    refused before then, and approval and registration need a recorded coverage of >= 5 coins plus the passing
    convergence test."""

    def test_no_coin_m_file_before_november_28(self):
        u = data.delivery_plan("ADAUSDT", "train3")[0]["files"][0][0]
        self.assertEqual(families.source_of(u), "binance_cm_klines_1h")
        self.assertFalse(families.fetch_allowed("binance_cm_klines_1h", "train3", now=ts(2026, 10, 20)))
        self.assertTrue(families.fetch_allowed(families.SPOT, "train3", now=ts(2026, 10, 20)))
        self.assertFalse(families.fetch_allowed("binance_cm_klines_1h", "train3", now=ts(2026, 11, 27, 23)))
        self.assertTrue(families.fetch_allowed("binance_cm_klines_1h", "train3", now=ts(2026, 11, 28)))
        called = []
        get = families.guarded_get("train3", fetch=lambda url: called.append(url) or b"zip")
        self.now[0] = ts(2026, 10, 20)
        with self.assertRaises(families.Embargoed):
            get(u)
        self.assertEqual(called, [])

    def test_a_real_request_always_uses_the_real_clock(self):
        """Review of 3600c85 (N3): a `now` in the future never opens the embargo for real HEAD requests."""
        with mock.patch.object(families, "_head", mock.Mock(side_effect=AssertionError("no request"))):
            with self.assertRaises(families.FamilyError):
                families.check_coverage(self.db, DRAFT, "human:anton", now=ts(2026, 12, 1))   # data.CLOCK: 11-20

    def test_quarterlies_must_still_exist_in_the_latest_whole_month(self):
        """Review of 3600c85 (N4): a coin whose quarterlies stopped (no file in the latest whole month) is not
        covered, so alpha_F is never spent on a family whose forward window cannot be tested."""
        draft = list(DBASIS["universe"]["symbols"])
        bases = tuple(c[:-4] + "USD_" for c in draft)
        stopped = "/" + draft[0][:-4] + "USD_"
        head = lambda u: any(f"/{b}" in u for b in bases) and not (stopped in u and "-2026-10.zip" in u)  # noqa: E731
        with mock.patch.object(families, "TRUST_INJECTED_COVERAGE", True):
            covered, checked = families.check_coverage(self.db, DRAFT, "human:anton", head=head, now=ts(2026, 11, 29))
            self.assertTrue(any("-2026-10.zip" in u for u in checked))
            self.assertEqual(covered, sorted(draft[1:]))
            self.assertTrue(any("must be exactly" in p for p in families._blocking_problems(self.db, DBASIS)))

    def test_the_coverage_check_is_refused_before_november_28(self):
        heads = []
        with self.assertRaises(families.FamilyError):
            families.check_coverage(self.db, DRAFT, "human:anton", head=lambda u: heads.append(u) or True,
                                    now=ts(2026, 11, 27, 23, 59))
        self.assertEqual(heads, [])
        self.assertIsNone(self.db.one("SELECT 1 FROM events WHERE kind='family.coverage'"))

    def covered_only(self, coins):
        """An injected HEAD: every quarterly zip of `coins` present, every other candidate's absent."""
        bases = tuple(c[:-4] + "USD_" for c in coins)
        return lambda u: any(f"/{b}" in u for b in bases)

    def test_approval_needs_the_recorded_coverage_and_registration_too(self):
        bad = families._blocking_problems(self.db, DBASIS)
        self.assertTrue(any("coverage is not recorded" in p for p in bad), bad)
        draft = list(DBASIS["universe"]["symbols"])
        with mock.patch.object(families, "TRUST_INJECTED_COVERAGE", True):
            covered, _ = families.check_coverage(self.db, DRAFT, "human:anton", head=self.covered_only(draft[:-1]),
                                                 now=ts(2026, 11, 29))
            self.assertEqual(covered, sorted(draft[:-1]))                               # the last coin has a gap
            bad = families._blocking_problems(self.db, DBASIS)
            self.assertTrue(any("must be exactly the coins" in p for p in bad), bad)    # still in the universe
            six = json.loads(json.dumps(DBASIS))
            six["universe"].update(symbols=draft[:-1], min_symbols=5)
            self.assertEqual([p for p in families._blocking_problems(self.db, six) if "coverage" in p or
                              "exactly" in p or "fewer" in p], [])
            with mock.patch.object(families, "approval_payload", lambda db, fid: {"alpha_family": 0.0125,
                                                                                  "instances": [], "blobs": {}}), \
                    mock.patch.object(families, "reserved", lambda db, fid: 0.0125):
                self.assertTrue(any("must be exactly" in p for p in families.registration_block(self.db, DBASIS)))

    def test_every_candidate_is_checked_and_no_coin_is_left_out_by_hand(self):
        draft = list(DBASIS["universe"]["symbols"])
        with mock.patch.object(families, "TRUST_INJECTED_COVERAGE", True):
            covered, checked = families.check_coverage(self.db, DRAFT, "human:anton",
                                                       head=self.covered_only(draft + ["ETCUSDT"]),
                                                       now=ts(2026, 11, 29))
            self.assertEqual(len({u.split("/klines/")[1].split("/")[0][:-11] for u in checked}), 27)  # 30v3 - 3
            self.assertEqual(covered, sorted(draft + ["ETCUSDT"]))
            bad = families._blocking_problems(self.db, DBASIS)                         # ETC covered but left out
            self.assertTrue(any("must be exactly the coins" in p and "ETCUSDT" in p for p in bad), bad)

    def test_an_injected_head_never_counts_in_production(self):
        families.check_coverage(self.db, DRAFT, "human:anton", head=lambda u: True, now=ts(2026, 11, 29))
        ev = json.loads(self.db.one("SELECT payload FROM events WHERE kind='family.coverage'")[0])
        self.assertEqual(ev["via"], "injected")
        self.assertTrue(any("coverage is not recorded" in p for p in families._blocking_problems(self.db, DBASIS)))

    def test_the_cli_is_refused_before_november_28_without_a_request(self):
        from lab.__main__ import main
        out = []
        with mock.patch.object(families, "_head", mock.Mock(side_effect=AssertionError("no request"))), \
                mock.patch("research.pm_lp.install_dns_cache", lambda: None):
            rc = main(["family-coverage", DRAFT], db_path=self.db_path, out=out.append)
        self.assertEqual(rc, 1)
        self.assertIn("none before 2026-11-28", out[0])

    def test_head_counts_only_200_and_404(self):
        import urllib.error

        class R:
            def __init__(self, status):
                self.status, self.headers = status, {"Content-Length": "123", "ETag": '"x"'}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        u = data.delivery_plan("ADAUSDT", "train3")[0]["files"][0][0]
        with mock.patch("urllib.request.urlopen", lambda req, timeout=60: R(200)):
            self.assertEqual(families._head(u), {"present": True, "status": 200, "length": "123", "etag": '"x"'})
        with mock.patch("urllib.request.urlopen", lambda req, timeout=60: R(204)):
            with self.assertRaises(families.FamilyError):
                families._head(u)
        for code, absent in ((404, True), (403, False), (503, False)):
            def err(req, timeout=60, code=code):
                raise urllib.error.HTTPError(u, code, "x", None, None)
            with mock.patch("urllib.request.urlopen", err):
                if absent:
                    self.assertEqual(families._head(u), {"present": False, "status": 404})
                else:
                    with self.assertRaises(urllib.error.HTTPError):
                        families._head(u)
        with self.assertRaises(families.FamilyError):
            families._head("https://example.com/data/futures/cm/x.zip")

    def test_a_failing_or_missing_convergence_test_blocks_the_approval(self):
        with mock.patch.object(dbasis, "convergence_selftest", lambda: {"ok": False, "checks": {"x": False}}):
            self.assertIn("synthetic convergence test fails: x", families._blocking_problems(self.db, DBASIS))
        with mock.patch.object(dbasis, "convergence_selftest", None):
            delattr(dbasis, "convergence_selftest")
            self.assertTrue(any("no synthetic convergence test" in p
                                for p in families._blocking_problems(self.db, DBASIS)))

    def test_a_quarterly_leg_unpublished_for_60_days_stops_waiting(self):
        split = data.forward_split(ts(2026, 12, 1), 12, tagged=True)
        end = data.window_bounds(split)[1]
        root = tempfile.mkdtemp(prefix="dbasis_pub")
        with mock.patch.object(data, "CACHE", root):
            e = data.expected_paths("ADAUSDT", split, spot=True)
            for kind in ("klines", "spot"):                                       # perp and spot are published
                os.makedirs(os.path.dirname(e[kind][-1][1]), exist_ok=True)
                open(e[kind][-1][1], "wb").close()
            self.assertIsNone(families.unpublished(["ADAUSDT"], split, delivery=False, now=end))
            wait = families.unpublished(["ADAUSDT"], split, delivery=True, now=end + 10 * DAY)
            self.assertIn("delivery files", wait)                                  # waits for the quarterly leg
            self.assertIsNone(families.unpublished(["ADAUSDT"], split, delivery=True, now=end + 61 * DAY))
        shutil.rmtree(root, ignore_errors=True)


SPAN = (ts(2022, 1, 1), ts(2024, 1, 1))


class Screen(A3Base):
    """A synthetic end-to-end screen of one dbasis instance through data -> backtest -> cost -> adversarial ->
    validate -> report: six coins of spot, perp, funding and COIN-M quarterly zips, the coverage check after
    2026-11-28 with an injected HEAD, the real approval and registration path, and data._fetch refusing any file that
    is not on disk."""
    market = None

    @classmethod
    def setUpClass(cls):
        cls.market = tempfile.mkdtemp(prefix="dbasis_scr")
        write_market(cls.market, COINS, SPAN)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        super().setUp()
        real = families.load

        def small(path_or_fid):
            fam = real(path_or_fid)
            if fam.get("family_id") == "dbasis":
                fam["universe"].update(symbols=list(COINS), min_symbols=5)
                fam["instances"] = [i for i in fam["instances"] if i["id"] == "thresh"]
            return fam

        def disk_only(url, path, get=None):
            if os.path.exists(path):
                return path
            raise AssertionError(f"a family test tried to fetch {url}")
        real_path = families.path_of
        self.p5 = [mock.patch.object(data, "CACHE", self.market), mock.patch.object(data, "_fetch", disk_only),
                   mock.patch.object(families, "load", small), mock.patch.object(pipeline, "PLACEBO_N", 20),
                   mock.patch.object(data, "UNIVERSE_30_V3", COINS + ("BTCUSDT",)),   # candidates: the six coins
                   mock.patch.object(families, "TRUST_INJECTED_COVERAGE", True),
                   mock.patch.object(families, "family_ids", lambda: ["dbasis"]),    # as if moved in after coverage
                   mock.patch.object(families, "path_of", lambda fid: DRAFT if fid == "dbasis" else real_path(fid)),
                   ]
        for p in self.p5:
            p.start()

    def tearDown(self):
        for p in reversed(self.p5):
            p.stop()
        super().tearDown()

    def test_a_dbasis_instance_screens_end_to_end(self):
        e = families.exp_id("dbasis", "thresh")
        families.discover_all(self.db)
        self.assertEqual(lifecycle.state(self.db, e), "DISCOVERED")                     # no exact graveyard hit
        self.now[0] = ts(2026, 11, 29)
        covered, _ = families.check_coverage(self.db, DRAFT, "human:anton", head=lambda u: True)
        self.assertEqual(covered, sorted(COINS))
        code = families.request(self.db, "dbasis", "human:anton", "Anton approves F2 after reading it")
        families.confirm(self.db, code, CLEAN["family"]["committed"][:8], "human:anton")
        self.assertEqual(fleet.strategy_pass(self.db)["registered"], [e])
        ag = [a for a in fleet.agents(self.db_path) if a.kinds]
        for _ in range(50):
            for a in ag:
                a(self.db)
            c = jobs.counts(self.db)
            if not (c["queued"] or c["running"] or c["blocked"]):
                break
        self.assertEqual((c["failed"], c["done"]), (0, 6), c)
        self.assertIn(lifecycle.state(self.db, e), ("OBSERVATION", "REJECTED"))
        bt = pipeline.frozen_artifact(self.db, e, "backtest")
        per = {s: {**data.files_for(s, "train3"), "spot": data.spot_files_for(s, "train3"),   # past the gateway:
                   "delivery": data.delivery_files_for(s, "train3")} for s in COINS}          # files on disk only
        bars, *_ = families.transform({"instrument_model": "spot_delivery_ratio"}, per, "train3")
        held = data.quarterlies(*data.window_bounds("train3"))
        for v in bt["variants"]:
            for s, pos in v["positions"].items():
                for i in dbasis.roll_bars(bars[s], held):
                    self.assertEqual(pos[i], 0.0, (s, i))                                # flat on every roll bar
        cost = pipeline.frozen_artifact(self.db, e, "cost")
        perp, raw = {}, {}
        for s in COINS:
            perp[s], raw[s], _ = data.load(data.files_for(s, "train3"), "train3")
        want = json.loads(json.dumps(pipeline._strip(pipeline._benchmark(perp, raw, catalogue.COSTS)), default=str))
        self.assertEqual(cost["benchmark"], want)                                       # the perps' buy-and-hold
        paths = [r[0] for r in self.db.q("SELECT path FROM datasets WHERE exp_id=? AND split='dev'", e)]
        self.assertEqual(sum("/cm_klines/" in p for p in paths),
                         sum(len(c["files"]) for s in COINS for c in data.delivery_plan(s, "train3")))
        val = pipeline.frozen_artifact(self.db, e, "validate")
        if not val.get("skipped"):
            att = val["attribution"]
            self.assertEqual(att["cash_flow"], "locked_basis")
            self.assertTrue({"mechanism attribution: locked basis carry - costs > 0",
                             "mechanism attribution: basis and price P&L <= locked basis carry"} <= set(val["gates"]))
        self.assertIsNone(self.db.one("SELECT 1 FROM transitions WHERE to_state='SCREEN_PASSED'"))


if __name__ == "__main__":
    unittest.main()
