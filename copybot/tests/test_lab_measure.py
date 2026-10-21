"""Amendment 14a: the three measurement hypotheses (H1, H2/H3 step 1) on SYNTHETIC files in the ingest formats only."""
import csv
import gzip
import itertools
import json
import math
import os
import random
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import __main__ as cli, ingest, measure, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402

H, D = 3600, 86400
UTC = timezone.utc
COINS = measure.UNIVERSE


def ts(y, m, d, hh=0, mm=0):
    return int(datetime(y, m, d, hh, mm, tzinfo=UTC).timestamp())


def months(y0, y1):
    return [(y, m) for y in range(y0, y1 + 1) for m in range(1, 13)]


def month_hours(y, m):
    a = ts(y, m, 1)
    b = ts(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return range(a, b, H)


# 2023 schedule as the public plan lists it (dates only; times follow the calendar parser's rules)
FOMC = [(2, 1), (3, 22), (5, 3), (6, 14), (7, 26), (9, 20), (11, 1), (12, 13)]
CPI = [(1, 12), (2, 14), (3, 14), (4, 12), (5, 10), (6, 13), (7, 12), (8, 10), (9, 13), (10, 12), (11, 14), (12, 12)]
JOBS = [(1, 6), (2, 3), (3, 10), (4, 7), (5, 5), (6, 2), (7, 7), (8, 4), (9, 1), (10, 6), (11, 3), (12, 8)]


def write_calendar(root):
    cal = os.path.join(root, "ingest", "calendar")
    fomc = [{"event": "FOMC statement", "date": f"2023-{m:02d}-{d:02d}", "kind": "scheduled", "scheduled": True,
             "sep": False, "ts": ingest._et(2023, m, d, 14, 0)} for m, d in FOMC]
    fomc.append({"event": "FOMC statement", "date": "2023-03-16", "kind": "unscheduled", "scheduled": False,
                 "sep": False, "ts": None})
    bls = [{"event": name, "reference": "x", "date": f"2023-{m:02d}-{d:02d}", "scheduled": True,
            "ts": ingest._et(2023, m, d, 8, 30)} for name, days in (("Consumer Price Index", CPI),
                                                                    ("Employment Situation", JOBS)) for m, d in days]
    ingest._write_json(os.path.join(cal, "fomc-2023.json"), {"year": 2023, "events": fomc})
    ingest._write_json(os.path.join(cal, "bls-2023.json"), {"year": 2023, "events": bls})
    return sorted(e["ts"] for e in fomc + bls if e["ts"])


def write_csv(path, cols, rows):
    """ingest._write_csv's format (gzip csv, header line, None as empty) at a fast compression level."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", newline="", compresslevel=1) as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def depth_row(t, d, snaps=120):
    mean = [d * 2.0] * 10
    low = [d * 3, d * 2.5, d * 2, d * 1.5, d * 1.02, d, d * 1.5, d * 2, d * 2.5, d * 3]    # thinner side: +1 %
    mean[4] = mean[5] = d * 1.5
    return [t, t + H, snaps, *mean, *low]


def write_depth(root, effect, seed, corrupt=(), thin=None):
    """8 coins x 2023, lognormal noise; hours inside an event window are multiplied by effect[split]."""
    rng = random.Random(seed)
    times = write_calendar(root)
    hot = {h for t in times for h in measure.window_hours(t)}
    for c in COINS:
        base = rng.uniform(5e5, 5e6)
        for y, m in months(2023, 2023):
            p = os.path.join(root, "ingest", "bookdepth_1h", f"{c}-{y}-{m:02d}.csv.gz")
            if (y, m) in corrupt:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(b"must never be read")
                continue
            f = effect["train"] if m <= 8 else effect["validation"]
            snaps = 80 if (thin or {}).get(c) == (y, m) else 120
            rows = [depth_row(h, base * math.exp(rng.gauss(0, 0.1)) * (f if h in hot else 1.0), snaps)
                    for h in month_hours(y, m)]
            write_csv(p, ingest.DEPTH_COLS, rows)


def write_funding(root, rate_of, years):
    for c in COINS:
        for y, m in months(*years):
            rows = "".join(f"{(h * 1000) + 3},8,{rate_of(c, h):.10f}\n" for h in month_hours(y, m) if h % (8 * H) == 0)
            p = os.path.join(root, "funding", f"{c}-fundingRate-{y}-{m:02d}.zip")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with zipfile.ZipFile(p, "w") as z:
                z.writestr(os.path.basename(p)[:-4] + ".csv", "calc_time,funding_interval_hours,last_funding_rate\n"
                           + rows)


REF = ts(2022, 1, 3, 1)                                 # a Monday 01:00 UTC


def week_of(h):
    return (h - REF) // (7 * D)


class Shocks:
    """z[coin, week] ~ N(0, 1): the weekly shock that drives both the signal and (with `effect`) next week's funding."""
    def __init__(self, seed, effect):
        self.rng, self.z, self.effect = random.Random(seed), {}, effect
        self.noise = random.Random(seed + 1)

    def __call__(self, c, k):
        return self.z.setdefault((c, k), self.rng.gauss(0, 1))

    def rate(self, c, h):
        return 0.0001 + (0.00002 * self(c, week_of(h)) if self.effect else 0.0) + self.noise.gauss(0, 0.000005)


def write_pageviews(root, z):
    for c in COINS:
        rows = []
        for d in range(ts(2022, 1, 1), ts(2024, 1, 1), D):
            v = 1000 * math.exp(z.noise.gauss(0, 0.05))
            if (d + 2 * D + H - REF) % (7 * D) == 0:      # day t-2 of a Monday t
                v *= math.exp(z(c, week_of(d + 2 * D + H)))
            rows.append({"date": datetime.fromtimestamp(d, UTC).strftime("%Y-%m-%d"), "views": int(v),
                         "available_ts": d + ingest.PAGEVIEW_LAG_S})
        ingest._write_json(os.path.join(root, "ingest", "pageviews", f"{measure.ARTICLE[c]}.json"),
                           {"article": measure.ARTICLE[c], "rows": rows})


def trade_row(t, buy, sell):
    return [t, t + H, 100, 1, 1, buy + 5e4, sell + 5e4, buy, 1e4, 1e4, 1e4, sell, 1e4, 1e4, 1e4, 9e4, 1.0]


def write_trades(root, z):
    for c in COINS:
        for y, m in months(2023, 2023):
            rows = []
            for h in month_hours(y, m):
                k = week_of(h + 72 * H)                    # inside [t-72h, t) of the Monday t = REF + (k)*week
                in_block = (h + 72 * H - REF) % (7 * D) < 72 * H
                share = 0.5 + z.noise.gauss(0, 0.02) + (0.03 * z(c, k) if in_block else 0.0)
                rows.append(trade_row(h, 1e5 * share, 1e5 * (1 - share)))
            write_csv(os.path.join(root, "ingest", "aggtrades_1h", f"{c}-{y}-{m:02d}.csv.gz"),
                              ingest.TRADE_COLS, rows)


class approx(float):
    def __eq__(self, other):
        return abs(self - other) < 1e-12


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()


class SignFlipAndBootstrap(unittest.TestCase):
    def test_exact_p_for_small_n(self):
        self.assertEqual(measure.sign_flip_p([-1.0, -2.0, 0.5]), 2 / 8)        # -2.5 and -3.5 of 8 patterns
        self.assertEqual(measure.sign_flip_p([-0.3] * 10), 1 / 1024)
        rng = random.Random(3)
        ys = [rng.gauss(-0.2, 1) for _ in range(12)]
        s = sum(ys)
        brute = sum(sum(g * y for g, y in zip(sg, ys)) <= s + 1e-12 for sg in itertools.product((1, -1), repeat=12))
        self.assertEqual(measure.sign_flip_p(ys), brute / 2 ** 12)

    def test_large_n_uses_seeded_draws(self):
        p = measure.sign_flip_p([-1.0] * 25, draws=2000)
        self.assertEqual(p, 1 / 2001)
        self.assertEqual(measure.sign_flip_p([0.1, -0.2] * 11, draws=500), measure.sign_flip_p([0.1, -0.2] * 11,
                                                                                               draws=500))

    def test_block_bootstrap_lower_bound(self):
        rng = random.Random(1)
        pos = measure.block_bootstrap([0.3 + rng.gauss(0, 0.2) for _ in range(23)])
        self.assertGreater(pos["lower"], 0)
        self.assertEqual((pos["rank"], pos["draws"], pos["block"], pos["seed"]), (33, 2000, 4, 7))
        self.assertLess(measure.block_bootstrap([rng.gauss(0, 0.3) for _ in range(23)])["lower"], 0)

    def test_spearman_and_residuals(self):
        self.assertAlmostEqual(measure.spearman([1, 2, 3, 4], [10, 20, 30, 45]), 1.0)
        self.assertIsNone(measure.spearman([1, 1, 1], [1, 2, 3]))
        u = measure.ols_residuals([1.0, 3.0, 5.0, 8.0], [0.0, 1.0, 2.0, 3.0])
        self.assertAlmostEqual(sum(u), 0.0)
        self.assertEqual(measure.ols_residuals([1.0, 2.0], [5.0, 5.0]), [-0.5, 0.5])   # no spread: slope 0


class ReaderRefuses(Tmp):
    def test_wrong_or_reserved_split(self):
        for sp, h in (("holdout", "H1"), ("validation3", "H1"), ("train", "H2"), ("train3", "H3")):
            with self.assertRaises(measure.Refused):
                measure.Reader(self.root, sp, h)

    def test_out_of_window_month_and_rows(self):
        r = measure.Reader(self.root, "train", "H1")
        with self.assertRaises(measure.Refused):
            r.hours("bookdepth", "BNBUSDT", months=[(2023, 9)])
        p = os.path.join(self.root, "ingest", "bookdepth_1h", "BNBUSDT-2023-08.csv.gz")
        ingest._write_csv(p, ingest.DEPTH_COLS, [depth_row(ts(2023, 8, 31, 23), 1e6), depth_row(ts(2023, 9, 1), 1e6)])
        with self.assertRaisesRegex(measure.Refused, "outside train"):
            r.hours("bookdepth", "BNBUSDT")

    def test_2024_rows_are_refused(self):
        p = os.path.join(self.root, "ingest", "aggtrades_1h", "BNBUSDT-2023-12.csv.gz")
        ingest._write_csv(p, ingest.TRADE_COLS, [trade_row(ts(2024, 1, 1), 1, 1)])
        with self.assertRaisesRegex(measure.Refused, "after 2023-12-31"):
            measure.Reader(self.root, "validation", "H3").hours("aggtrades", "BNBUSDT")
        ingest._write_json(os.path.join(self.root, "ingest", "pageviews", "Binance.json"),
                           {"rows": [{"date": "2023-12-31", "views": 1, "available_ts": 0},
                                     {"date": "2024-01-01", "views": 1, "available_ts": 0}]})
        with self.assertRaisesRegex(measure.Refused, "after 2023-12-31"):
            measure.Reader(self.root, "validation3", "H2").pageviews("Binance")
        write_funding(self.root, lambda c, h: 0.0001, (2023, 2023))
        p = os.path.join(self.root, "funding", "BNBUSDT-fundingRate-2023-12.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("x.csv", f"calc_time,funding_interval_hours,last_funding_rate\n{ts(2024, 1, 1) * 1000},8,0.1\n")
        with self.assertRaisesRegex(measure.Refused, "after 2023-12-31"):
            measure.Reader(self.root, "validation", "H3").funding("BNBUSDT")

    def test_pageviews_outside_the_window_are_not_returned_and_lag_is_enforced(self):
        ingest._write_json(os.path.join(self.root, "ingest", "pageviews", "Binance.json"),
                           {"rows": [{"date": "2023-06-30", "views": 5, "available_ts": 0},
                                     {"date": "2023-07-01", "views": 7, "available_ts": ts(2023, 7, 1)}]})
        r = measure.Reader(self.root, "train3", "H2")
        self.assertEqual(r.pageviews("Binance"), {ts(2023, 6, 30): (5.0, ts(2023, 7, 2))})   # D+2 even if the file
        self.assertEqual(len(r.files), 1)                                                  # says earlier


class PointInTime(unittest.TestCase):
    def test_pageview_day_usable_from_d_plus_2(self):
        t = ts(2023, 3, 13, 1)                               # Monday 01:00
        day0 = measure._day(t)
        pv = {day0 - k * D: (100.0, day0 - k * D + 2 * D) for k in range(1, 21)}
        pv[day0 - 2 * D] = (1000.0, day0)                    # day t-2: usable from t 00:00 <= 01:00
        self.assertAlmostEqual(measure.shock_s(pv, t), math.log1p(1000) - math.log1p(100))
        pv[day0 - 2 * D] = (1000.0, t + 1)                   # published after the decision
        self.assertIsNone(measure.shock_s(pv, t))
        pv[day0 - 2 * D] = (1000.0, day0)
        pv[day0 - 1 * D] = (10.0 ** 9, day0 + D)             # day t-1 is not usable yet and never part of S
        self.assertAlmostEqual(measure.shock_s(pv, t), math.log1p(1000) - math.log1p(100))

    def test_hourly_rows_usable_from_the_hour_end(self):
        t = ts(2023, 3, 13, 1)
        rng = random.Random(5)
        tr = {h: {"buy_usd_lt1k": 50 + rng.random(), "sell_usd_lt1k": 50.0, "available_ts": h + H}
              for h in range(t - 15 * D, t + 5 * H, H)}
        r0 = measure.shock_r(tr, t)
        tr[t]["buy_usd_lt1k"] = 10 ** 6                                # hour 01:00-02:00 ends after t: unused
        self.assertEqual(measure.shock_r(tr, t), r0)
        tr[t - H]["buy_usd_lt1k"] = 10 ** 6                            # hour 00:00-01:00 ends at t: used
        self.assertNotEqual(measure.shock_r(tr, t), r0)
        del tr[t - H]
        self.assertIsNone(measure.shock_r(tr, t))                      # a missing hour: no shock that week

    def test_reader_never_dates_an_hour_before_its_end(self):
        root = tempfile.mkdtemp()
        row = trade_row(ts(2023, 3, 1), 1, 1)
        row[1] = row[0]                                                # file claims the hour is usable at its start
        ingest._write_csv(os.path.join(root, "ingest", "aggtrades_1h", "BNBUSDT-2023-03.csv.gz"), ingest.TRADE_COLS,
                          [row])
        got = measure.Reader(root, "train", "H3").hours("aggtrades", "BNBUSDT")
        self.assertEqual(got[ts(2023, 3, 1)]["available_ts"], ts(2023, 3, 1) + H)

    def test_event_window_hours(self):
        self.assertEqual(measure.window_hours(ts(2023, 3, 22, 18)), [ts(2023, 3, 22, 17), ts(2023, 3, 22, 18)])
        self.assertEqual(len(measure.window_hours(ts(2023, 3, 14, 12, 30))), 3)


class H1(Tmp):
    def test_known_effect_passes_and_the_september_jobs_report_is_dropped(self):
        write_depth(self.root, {"train": 0.6, "validation": 0.6}, seed=11)
        res = measure.run("H1", self.root)
        self.assertEqual(res["verdict"], "PASS", res["reason"])
        self.assertTrue(res["train_gate"] and res["validation_read"])
        self.assertEqual((res["train"]["n"], res["validation"]["n"]), (21, 10))
        sep1 = [e for e in res["validation"]["events"] if e["T"].startswith("2023-09-01")]
        self.assertEqual(len(sep1), 1)
        self.assertIsNone(sep1[0]["Y"])
        self.assertEqual(sep1[0]["control_days"], 0)
        self.assertEqual(res["validation"]["sign_flip_p"], 1 / 1024)
        self.assertEqual(res["validation"]["placebo"]["p"], 0.0)
        self.assertEqual(res["validation"]["placebo"]["n"], 2000)
        self.assertEqual(res["seeds"], {"placebo": 17, "sign_flip": 7})
        self.assertEqual(res["rule"], "research/PROTOCOL_V3.md amendment 14a")
        self.assertAlmostEqual(res["alpha"], 0.05 / 3)
        self.assertEqual({x["split"] for x in res["inputs"]}, {"train", "validation"})
        self.assertTrue(all(len(x["sha256"]) == 64 and x["bytes"] > 0 for x in res["inputs"]))
        self.assertFalse(res["train"]["secondary"]["decisional"])
        json.dumps(res)

    def test_null_data_does_not_pass(self):
        write_depth(self.root, {"train": 1.0, "validation": 1.0}, seed=12)
        res = measure.run("H1", self.root)
        self.assertNotEqual(res["verdict"], "PASS")

    def test_failed_train_gate_never_reads_validation(self):
        write_depth(self.root, {"train": 1.5, "validation": 0.6}, seed=13,
                    corrupt=[(2023, m) for m in (9, 10, 11, 12)])
        opened = []
        real = measure.read_bytes
        with mock.patch.object(measure, "read_bytes", lambda p: opened.append(p) or real(p)):
            res = measure.run("H1", self.root)
        self.assertEqual(res["verdict"], "REJECTED")
        self.assertFalse(res["train_gate"])
        self.assertFalse(res["validation_read"])
        self.assertNotIn("validation", res)
        self.assertFalse([p for p in opened if any(f"-2023-{m}." in p for m in ("09", "10", "11", "12"))])
        self.assertEqual({x["split"] for x in res["inputs"]}, {"train"})

    def test_missing_files_are_untestable_before_any_read(self):
        write_depth(self.root, {"train": 0.6, "validation": 0.6}, seed=14)
        for c in COINS[:3]:
            os.remove(os.path.join(self.root, "ingest", "bookdepth_1h", f"{c}-2023-10.csv.gz"))
        with mock.patch.object(measure, "read_bytes", side_effect=AssertionError("read")):
            res = measure.run("H1", self.root)
        self.assertEqual(res["verdict"], "UNTESTABLE")
        self.assertIn("validation", res["reason"])
        self.assertEqual(res["inputs"], [])

    def test_depth_value_rules(self):
        self.assertIsNone(measure.depth({"snapshots": 89, "min_usd_-1": 1.0, "min_usd_+1": 1.0}))
        self.assertEqual(measure.depth({"snapshots": 90, "min_usd_-1": 2.0, "min_usd_+1": 1.0}), 1.0)
        self.assertIsNone(measure.depth({"snapshots": 120, "min_usd_-1": None, "min_usd_+1": 1.0}))
        self.assertEqual(measure.depth({"snapshots": 120, "mean_usd_-2": 3.0, "mean_usd_+2": 4.0}, 2, "mean"), 3.0)

    def test_fewer_than_six_coins_with_95_percent_valid_hours_is_untestable(self):
        write_depth(self.root, {"train": 0.6, "validation": 0.6}, seed=15, thin={c: (2023, 3) for c in COINS[:3]})
        res = measure.run("H1", self.root)
        self.assertEqual(res["verdict"], "UNTESTABLE")
        self.assertIn("95 %", res["reason"])
        self.assertEqual(len(res["train"]["coins_95"]), 5)
        self.assertFalse(res["validation_read"])


class FlowHypotheses(Tmp):
    def test_h2_known_effect_passes(self):
        z = Shocks(21, effect=True)
        write_pageviews(self.root, z)
        write_funding(self.root, z.rate, (2022, 2023))
        res = measure.run("H2", self.root)
        self.assertEqual(res["verdict"], "PASS", res["reason"])
        self.assertEqual((res["train"]["n"], res["validation"]["n"]), (75, 23))
        self.assertEqual(res["train"]["weeks"][0]["t"], "2022-01-17 01:00 UTC")
        self.assertEqual(res["validation"]["weeks"][-1]["t"], "2023-12-18 01:00 UTC")
        self.assertGreater(res["validation"]["bootstrap"]["lower"], 0)
        self.assertEqual(res["seeds"], {"bootstrap": 7})
        json.dumps(res)

    def test_h2_null_does_not_pass(self):
        z = Shocks(22, effect=False)
        write_pageviews(self.root, z)
        write_funding(self.root, z.rate, (2022, 2023))
        self.assertNotEqual(measure.run("H2", self.root)["verdict"], "PASS")

    def test_h3_known_effect_passes_and_null_does_not(self):
        z = Shocks(31, effect=True)
        write_trades(self.root, z)
        write_funding(self.root, z.rate, (2023, 2023))
        res = measure.run("H3", self.root)
        self.assertEqual(res["verdict"], "PASS", res["reason"])
        self.assertEqual((res["train"]["n"], res["validation"]["n"]), (32, 14))
        null = tempfile.mkdtemp(dir=self.root)
        z = Shocks(32, effect=False)
        write_trades(null, z)
        write_funding(null, z.rate, (2023, 2023))
        self.assertNotEqual(measure.run("H3", null)["verdict"], "PASS")

    def test_incomplete_funding_week_drops_the_coin(self):
        t = ts(2023, 3, 13, 1)
        fr = {h: 0.0001 for h in range(measure._day(t) - 8 * D, measure._day(t) + 9 * D, 8 * H)}
        self.assertEqual(measure.funding_sums(fr, t), (approx(0.0021), approx(0.0021)))
        fr.pop(measure._day(t) + 8 * H)                      # one settlement of the outcome week missing
        self.assertIsNone(measure.funding_sums(fr, t))


class Cli(Tmp):
    def test_measure_saves_an_artifact_and_records_once(self):
        out, db = [], os.path.join(self.root, "lab.db")
        with mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.root, "artifacts")):
            self.assertEqual(cli.main(["measure", "H2", "--data-dir", self.root], db_path=db, out=out.append), 0)
            res = json.loads(out[-1])
            self.assertEqual(res["verdict"], "UNTESTABLE")
            self.assertEqual(len(os.listdir(os.path.join(self.root, "artifacts", measure.ARTIFACT_ID))), 1)
            self.assertEqual(len(res["artifact"]["sha256"]), 64)
            self.assertFalse(os.path.exists(db))                   # nothing recorded without --record
            self.assertEqual(cli.main(["measure", "H2", "--data-dir", self.root, "--record"], db_path=db,
                                      out=out.append), 0)
            self.assertEqual(cli.main(["measure", "H2", "--data-dir", self.root, "--record"], db_path=db,
                                      out=out.append), 1)
            self.assertIn("already has a recorded measurement", out[-1])
        d = DB(db)
        rows = d.q("SELECT payload FROM events WHERE kind='research.measurement'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["payload"])["verdict"], "UNTESTABLE")
        d.close()


if __name__ == "__main__":
    unittest.main()
