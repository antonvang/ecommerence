"""Amendment 16a: measurement hypothesis H4 `notering` on SYNTHETIC announcements (stored as lab/news.py stores them)
and SYNTHETIC funding archives (Binance layout, served by a fake opener with .CHECKSUM files). No network."""
import hashlib
import io
import itertools
import json
import os
import random
import shutil
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import __main__ as cli, ingest, measure, measure_h4 as h4, news, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402

H, D = 3600, 86400
UTC = timezone.utc
NOW = 1792600000


def ts(y, m, d, hh=0):
    return int(datetime(y, m, d, hh, tzinfo=UTC).timestamp())


class Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


class Fake:
    """url -> bytes; a missing url is a 404. Records every url asked for."""
    def __init__(self):
        self.files, self.asked = {}, []

    def __call__(self, url, timeout=120):
        self.asked.append(url)
        if url not in self.files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return Resp(self.files[url])

    def add(self, url, data):
        self.files[url] = data
        self.files[url + ".CHECKSUM"] = f"{hashlib.sha256(data).hexdigest()}  {os.path.basename(url)}\n".encode()

    def symbols_asked(self):
        return {u.split("/fundingRate/")[1].split("/")[0] for u in self.asked}


def month_zip(sym, y, m, rows):
    """A monthly fundingRate zip in the archive's layout (header line + calc_time ms, interval hours, rate)."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(f"{sym}-fundingRate-{y}-{m:02d}.csv", "calc_time,funding_interval_hours,last_funding_rate\n"
                   + "".join(f"{t * 1000 + 4},{iv},{r:.10f}\n" for t, iv, r in rows))
    return b.getvalue()


def publish(fake, sym, t0, end, rate, interval=8, skip=()):
    """Settlements every `interval` hours from t0 to end (inclusive), rate(t - t0, t); months in `skip` are absent."""
    by = {}
    for t in range(t0, min(end, h4.END - 1) + 1, interval * H):
        d = datetime.fromtimestamp(t, UTC)
        by.setdefault((d.year, d.month), []).append((t, interval, rate(t - t0, t)))
    for (y, m), rows in by.items():
        if (y, m) not in skip:
            fake.add(h4.URL.format(sym=sym, y=y, m=m), month_zip(sym, y, m, rows))


def grid(t, step=8 * H):
    return (t + step - 1) // step * step


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labh4")
        self.root = os.path.join(self.tmp, "market")
        self.dbp = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.dbp)
        self.fake, self.n = Fake(), 0
        self.patches = [mock.patch.object(h4, "SLEEP", lambda s: None),
                        mock.patch.object(ingest, "_open", side_effect=AssertionError("network used in a test"))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def announce(self, title, published, category="listing", source="binance"):
        self.n += 1
        x = news.item(source, f"a{self.n}", f"https://www.binance.com/en/support/announcement/a{self.n}", title,
                      published, category, NOW, backfill=True)
        news.store(self.db, [x], news.BINANCE, NOW)

    def listing(self, sym, pub, t0=None, end=None, rate=None, interval=8, skip=(), paren=False):
        coin = sym[:-4]
        name = f"Foo ({coin})" if paren else f"{coin}USDT"
        self.announce(f"Binance Futures Will Launch USDⓈ-M {name} Perpetual Contract With Up to 20x Leverage", pub)
        if t0 is None:
            t0 = grid(pub + D, interval * H)
        publish(self.fake, sym, t0, end or t0 + 200 * D, rate or (lambda dt, t: 0.0001), interval, skip)
        return t0

    def scenario(self, train=22, valid=10, train_prem=0.0005, valid_prem=0.0005, seed=3):
        """`train` symbols announced 2022-02..2022-12 and `valid` announced 2023-07..2023-08. Early premium per
        settlement (per 8 h) on days 1-7; a callable premium takes the symbol index. A third of them settle every 4 h."""
        rng = random.Random(seed)
        out = {"train": [], "valid": []}
        for kind, n, start, step, prem in (("train", train, ts(2022, 2, 1, 5), 15, train_prem),
                                           ("valid", valid, ts(2023, 7, 3, 5), 5, valid_prem)):
            for i in range(n):
                sym = f"{'TA' if kind == 'train' else 'VA'}{i:02d}USDT"
                iv = 4 if i % 3 == 0 else 8
                p = prem(i) if callable(prem) else prem
                noise = {}

                def rate(dt, t, p=p, iv=iv, noise=noise):
                    noise.setdefault(t, rng.gauss(0, 0.00002))
                    return (0.0001 + (p if dt <= 7 * D else 0.0) + noise[t]) * iv / 8
                end = ts(2023, 12, 31, 16) if kind == "valid" else None
                self.listing(sym, start + i * step * D, end=end, rate=rate, interval=iv, paren=i % 2 == 0)
                out[kind].append(sym)
        return out

    def run_h4(self):
        return h4.run(self.root, self.dbp, opener=self.fake, free=lambda: 10 ** 12)


class Statistics(unittest.TestCase):
    def test_per_8h_normalisation_with_4_hour_intervals(self):
        t = ts(2022, 3, 1)
        fr = {t: 0.5, t + 4 * H: 0.0001, t + 8 * H: 0.0001, t + 16 * H: 0.0001}
        got = h4.per_8h(fr)
        self.assertEqual(sorted(got), [t + 4 * H, t + 8 * H, t + 16 * H])           # the first settlement is left out
        for k, v in ((t + 4 * H, 0.0002), (t + 8 * H, 0.0002), (t + 16 * H, 0.0001)):
            self.assertAlmostEqual(got[k], v, places=15)

    def test_t0_is_excluded(self):
        t0 = ts(2022, 3, 1)
        fr = {t: 0.0001 for t in range(t0, t0 + 61 * D, 8 * H)}
        fr[t0] = 1.0                                          # a huge first settlement changes nothing
        y, fe, fl, ne, nl = h4.y_value(fr, t0)
        self.assertAlmostEqual(fe, 0.0001)
        self.assertAlmostEqual(y, 0.0)
        self.assertEqual((ne, nl), (21, 90))                  # (t0, t0 + 7 d] and (t0 + 30 d, t0 + 60 d]

    def test_exact_sign_flip_for_small_n(self):
        ys = [0.3, -0.1, 0.25, 0.05, -0.2, 0.4, 0.12, -0.07, 0.33, 0.02]
        s = sum(ys)
        brute = sum(sum(g * y for g, y in zip(sg, ys)) >= s - 1e-12
                    for sg in itertools.product((1, -1), repeat=len(ys))) / 2 ** len(ys)
        self.assertAlmostEqual(h4.p_greater(ys), brute)
        self.assertAlmostEqual(h4.p_greater([1.0] * 8), 1 / 256)
        self.assertGreater(h4.p_greater([-1.0] * 8), 0.99)

    def test_draws_above_20(self):
        ys = [0.1] * 25
        self.assertAlmostEqual(h4.p_greater(ys), 1 / (h4.FLIP_DRAWS + 1))      # p = (k + 1) / (B + 1), k = 0


class Measurement(Base):
    def test_known_effect_passes(self):
        sc = self.scenario()
        res = self.run_h4()
        self.assertEqual(res["verdict"], "PASS", res["reason"])
        self.assertEqual(res["train"]["n"], 22)
        self.assertEqual(res["validation"]["n"], 10)
        self.assertEqual(res["validation"]["sign_flip"], "exact")
        self.assertAlmostEqual(res["validation"]["sign_flip_p"], 1 / 1024)
        self.assertEqual(sorted(res["train"]["symbols"]), sc["train"])
        self.assertAlmostEqual(res["train"]["mean_Y"], 0.0005, delta=0.00003)       # per 8 h, also for 4-h symbols
        sec = res["train"]["secondary"]
        self.assertEqual(sec["placebo_t0_plus_90d"]["n"], 22)
        self.assertAlmostEqual(sec["placebo_t0_plus_90d"]["mean_Y"], 0.0, delta=0.00002)
        self.assertEqual(sec["share_covering_round_trip"], 1.0)    # 7 d x 3 x 0.06 % > 0.46 %
        late = [r for r in res["validation"]["rows"] if r["placebo"]["Y"] is None]
        self.assertTrue(late and all(r["placebo"]["reason"] == "day 150 lies after 2023-12-31" for r in late))
        self.assertEqual(res["validation"]["secondary"]["placebo_t0_plus_90d"]["n"], 10 - len(late))
        self.assertEqual(res["rule"], "research/PROTOCOL_V3.md amendment 16a")
        self.assertEqual(res["alpha"], 0.05)
        self.assertEqual(res["seeds"], {"sign_flip": 7})
        self.assertTrue(res["inputs"] and all(len(f["sha256"]) == 64 and f["checksum"] == "verified"
                                              for f in res["inputs"]))
        self.assertTrue({f["split"] for f in res["inputs"]} == {"train3", "validation3"})
        self.assertFalse(any(u.split("fundingRate-")[-1][:4] >= "2024" for u in self.fake.asked))
        four = [r for r in res["train"]["rows"] if r["intervals_h"] == [4]]
        self.assertTrue(four)
        self.assertAlmostEqual(four[0]["F_late"], 0.0001, delta=0.00002)

    def test_null_validation_does_not_pass(self):
        self.scenario(valid_prem=lambda i: 0.0003 if i % 2 else -0.0003)
        res = self.run_h4()
        self.assertTrue(res["train_gate"])
        self.assertEqual(res["verdict"], "REJECTED")
        self.assertGreaterEqual(res["validation"]["sign_flip_p"], 0.05)

    def test_failed_gate_leaves_validation_untouched(self):
        sc = self.scenario(train_prem=-0.0003)
        read = []
        real = measure.read_bytes
        with mock.patch.object(measure, "read_bytes", side_effect=lambda p: read.append(p) or real(p)):
            res = self.run_h4()
        self.assertEqual(res["verdict"], "REJECTED")
        self.assertFalse(res["validation_read"])
        self.assertNotIn("validation", res)
        self.assertFalse(self.fake.symbols_asked() & set(sc["valid"]))          # not downloaded, not even probed
        self.assertFalse([p for p in read if os.path.basename(p)[:2] == "VA"])  # not read
        self.assertFalse([f for f in os.listdir(os.path.join(self.root, "funding")) if f.startswith("VA")])

    def test_too_few_train_symbols_is_untestable_without_validation(self):
        sc = self.scenario(train=5)
        res = self.run_h4()
        self.assertEqual(res["verdict"], "UNTESTABLE")
        self.assertFalse(self.fake.symbols_asked() & set(sc["valid"]))

    def test_2024_is_refused(self):
        r = h4.Reader(self.root, "train3", {"TA00USDT"}, h4.new_budget(), self.fake, lambda: 10 ** 12)
        with self.assertRaises(h4.Refused):
            r.month("TA00USDT", 2024, 1)
        with self.assertRaises(h4.Refused):
            r.month("TA00USDT", 2021, 12)
        with self.assertRaises(h4.Refused):
            r.month("VA00USDT", 2023, 3)                                       # not admitted to the phase
        self.assertEqual(self.fake.asked, [])
        self.fake.add(h4.URL.format(sym="TA00USDT", y=2023, m=12),
                      month_zip("TA00USDT", 2023, 12, [(ts(2023, 12, 31, 16), 8, 0.0001), (ts(2024, 1, 1), 8, 0.1)]))
        with self.assertRaises(h4.Refused):
            r.month("TA00USDT", 2023, 12)
        with self.assertRaises(h4.Refused):
            h4.Reader(self.root, "holdout", {"TA00USDT"}, h4.new_budget())

    def test_announcements_in_2024_and_late_2023_are_not_fetched(self):
        self.scenario(train=20, valid=8)
        self.listing("ZZ24USDT", ts(2024, 2, 1))
        self.listing("LATEUSDT", ts(2023, 11, 15))
        res = self.run_h4()
        why = {x["symbol"]: x["reason"] for x in res["excluded"]}
        self.assertEqual(why["ZZ24USDT"], "announced_after_2023")
        self.assertEqual(why["LATEUSDT"], "day60_after_2023")
        self.assertFalse(self.fake.symbols_asked() & {"ZZ24USDT", "LATEUSDT"})

    def test_relistings_and_delistings_are_excluded_with_reasons(self):
        self.scenario()
        pub = ts(2022, 8, 1, 10)
        self.announce("Binance Futures Will Launch USDⓈ-M RL01USDT Perpetual Contract", pub)
        publish(self.fake, "RL01USDT", ts(2022, 3, 1), ts(2022, 4, 30), lambda dt, t: 0.0001)    # earlier listing
        publish(self.fake, "RL01USDT", grid(pub + D), grid(pub + D) + 200 * D, lambda dt, t: 0.0001)
        self.announce("Binance Futures Will Launch USDⓈ-M RL02USDT Perpetual Contract", ts(2022, 8, 15, 10))
        publish(self.fake, "RL02USDT", ts(2022, 8, 1), ts(2023, 3, 1), lambda dt, t: 0.0001)   # same month, earlier
        self.listing("DL01USDT", ts(2022, 9, 1, 3), end=ts(2022, 9, 2) + 40 * D)             # delisted on day 40
        self.listing("GP01USDT", ts(2022, 9, 1, 3), skip={(2022, 10)})                        # a month missing
        self.listing("OLD1USDT", ts(2021, 11, 20))
        self.announce("Binance Futures Will Launch Multiple TradFi USDⓈ-Margined Perpetual Contracts", ts(2022, 12, 1))
        self.announce("Binance Futures Will Launch COIN-Margined XYZ (XYZ) Perpetual Contract", ts(2022, 12, 2))
        self.announce("Binance Will List Foo (FOO)", ts(2022, 12, 3))                         # not a futures launch
        res = self.run_h4()
        self.assertEqual(res["verdict"], "PASS")
        why = {x["symbol"]: (x["reason"], x["detail"]) for x in res["excluded"]}
        self.assertEqual(why["RL01USDT"][0], "funding_before_announcement")
        self.assertIn("2022-03", why["RL01USDT"][1])
        self.assertEqual(why["RL02USDT"][0], "funding_before_announcement")
        self.assertEqual(why["DL01USDT"][0], "fewer_than_60_days")
        self.assertEqual(why["GP01USDT"][0], "archive_month_missing")
        self.assertEqual(why["OLD1USDT"][0], "announced_before_2022")
        self.assertEqual(res["excluded_counts"]["funding_before_announcement"], 2)
        self.assertEqual(res["announcements"]["skipped_counts"], {"coin_m_launch": 1, "no_coin_by_fixed_rules": 1})
        self.assertNotIn("FOOUSDT", why)
        self.assertNotIn("OLD1USDT", self.fake.symbols_asked())
        self.assertEqual(res["train"]["n"], 22)

    def test_train_announcement_settling_in_july_belongs_to_validation(self):
        self.scenario(valid=8)
        self.listing("JUNEUSDT", ts(2023, 6, 29, 5), t0=ts(2023, 7, 2), end=ts(2023, 12, 31))
        res = self.run_h4()
        self.assertIn("JUNEUSDT", res["deferred_to_validation3"])
        self.assertIn("JUNEUSDT", res["validation"]["symbols"])
        july = [f for f in res["inputs"] if f["symbol"] == "JUNEUSDT"]
        self.assertTrue(july and all(f["split"] == "validation3" for f in july))

    def test_draft_must_match_the_lock(self):
        with mock.patch.object(h4, "DRAFT_SHA256", "0" * 64):
            with self.assertRaises(h4.Refused):
                self.run_h4()

    def test_cached_files_are_verified_against_the_checksum(self):
        self.scenario(train=3, valid=0)
        first = self.run_h4()
        again = self.run_h4()
        self.assertTrue(all(f["fetch"] == "downloaded" for f in first["inputs"]))
        self.assertTrue(all(f["fetch"] == "cached" for f in again["inputs"]))
        self.assertEqual([f["sha256"] for f in first["inputs"]], [f["sha256"] for f in again["inputs"]])
        p = os.path.join(self.root, first["inputs"][0]["path"])
        with open(p, "ab") as f:
            f.write(b"x")
        with self.assertRaises(h4.Refused):
            self.run_h4()

    def test_bad_checksum_is_refused(self):
        self.scenario(train=1, valid=0)
        u = h4.URL.format(sym="TA00USDT", y=2022, m=2)
        self.fake.files[u + ".CHECKSUM"] = b"0" * 64 + b"  x.zip\n"
        with self.assertRaises(ingest.Refused):
            self.run_h4()


class H5(Base):
    """Amendment 16c: the opposite direction, only on listings announced in 2023-07..2023-12."""
    def run_h5(self):
        return h4.run_h5(self.root, self.dbp, opener=self.fake, free=lambda: 10 ** 12)

    def test_lower_early_funding_passes_and_train_listings_are_never_read(self):
        sc = self.scenario(train=5, valid=10, train_prem=0.0005, valid_prem=-0.0004)
        res = self.run_h5()
        self.assertEqual(res["verdict"], "PASS", res["reason"])
        self.assertEqual(sorted(res["validation"]["symbols"]), sc["valid"])
        self.assertAlmostEqual(res["validation"]["sign_flip_p"], 1 / 1024)
        early = {x["symbol"] for x in res["excluded"] if x["reason"] == "announced_before_2023_07"}
        self.assertTrue(set(sc["train"]) <= early)                  # (16b also reads a bogus TA01USDTUSDT: no data)
        self.assertFalse(any(t in u for u in self.fake.asked for t in sc["train"]))   # H4's sample stays unread
        self.assertEqual(res["validation"]["secondary"]["share_negative_early_sum"], 1.0)
        self.assertEqual(res["rule"], "research/PROTOCOL_V3.md amendment 16c")

    def test_higher_early_funding_does_not_pass_and_too_few_is_untestable(self):
        self.scenario(train=0, valid=10, valid_prem=0.0004)
        self.assertEqual(self.run_h5()["verdict"], "REJECTED")
        shutil.rmtree(self.root, ignore_errors=True)
        self.tearDown()
        self.setUp()
        self.scenario(train=0, valid=5, valid_prem=-0.0004)
        self.assertEqual(self.run_h5()["verdict"], "UNTESTABLE")

    def test_the_draft_must_match_the_locked_text(self):
        with mock.patch.object(h4, "H5_DRAFT_SHA256", "0" * 64):
            with self.assertRaises(h4.Refused):
                self.run_h5()


class Cli(Base):
    def test_measure_h4_saves_an_artifact_and_records_once(self):
        self.scenario(train=3, valid=0)
        out = []
        with mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")), \
                mock.patch.object(ingest, "_open", self.fake), mock.patch.object(ingest, "MARGIN", 0):
            args = ["measure", "H4", "--data-dir", self.root, "--record"]
            self.assertEqual(cli.main(args, db_path=self.dbp, out=out.append), 0)
            res = json.loads(out[-1])
            self.assertEqual(res["verdict"], "UNTESTABLE")
            self.assertEqual(len(os.listdir(os.path.join(self.tmp, "artifacts", h4.ARTIFACT_ID))), 1)
            self.assertEqual(cli.main(args, db_path=self.dbp, out=out.append), 1)
            self.assertIn("already has a recorded measurement", out[-1])
        rows = self.db.q("SELECT payload FROM events WHERE kind='research.measurement'")
        self.assertEqual([json.loads(r["payload"])["hypothesis"] for r in rows], ["H4"])

    def test_missing_registry_is_refused(self):
        out = []
        self.assertEqual(cli.main(["measure", "H4", "--data-dir", self.root], db_path=os.path.join(self.tmp, "x.db"),
                                  out=out.append), 1)
        self.assertIn("refused", out[-1])


if __name__ == "__main__":
    unittest.main()
