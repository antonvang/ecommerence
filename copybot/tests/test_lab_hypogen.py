"""Amendment 17: the automatic hypothesis pipeline - fixed event types and outcomes, point-in-time events traced to
their observations, a reader that refuses every month outside its phase (and everything from 2024), screening only in
explore0, dedup with negative results kept, drafts, locks from the committed protocol and the locked measurement."""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, hypogen, jobs, measure, news, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402

H = 3600
T = lambda y, m, d=1, h=0: int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp())   # noqa: E731
NOW = T(2026, 10, 21, 20)


def no_net(url):
    raise urllib.error.HTTPError(url, 404, "not in this test", None, None)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labhypo")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch.object(data, "CACHE", os.path.join(self.tmp, "cache")),
                  mock.patch.object(hypogen, "DIR", os.path.join(self.tmp, "hypotheses"))]
        for p in self.p:
            p.start()
        hypogen._CACHE.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def zip(self, kind, sym, y, m, rows):
        name = f"{sym}-1h-{y}-{m:02d}.zip" if kind == "klines" else f"{sym}-fundingRate-{y}-{m:02d}.zip"
        d = os.path.join(data.CACHE, kind)
        os.makedirs(d, exist_ok=True)
        buf = io.StringIO()
        for r in rows:
            buf.write(",".join(str(x) for x in r) + "\n")
        with zipfile.ZipFile(os.path.join(d, name), "w") as z:
            z.writestr(name[:-4] + ".csv", buf.getvalue())

    def klines(self, sym, y, m, price, volume=lambda ts: 1000.0):
        a = T(y, m)
        b = T(y + (m == 12), 1 if m == 12 else m + 1)
        self.zip("klines", sym, y, m, [(ts * 1000, price(ts), 0, 0, price(ts), 1, ts * 1000 + H * 1000 - 1,
                                        volume(ts)) for ts in range(a, b, H)])

    def funding(self, sym, y, m, rate):
        a = T(y, m)
        b = T(y + (m == 12), 1 if m == 12 else m + 1)
        self.zip("funding", sym, y, m, [(ts * 1000, 8, rate(ts)) for ts in range(a, b, 8 * H)])

    def announce(self, coin, usable, title=None, sid=None):
        it = news.item("binance", sid or f"{coin}{usable}", "https://www.binance.com/x", title or
                       f"Binance Will List Foo ({coin})", usable - news.BACKFILL_LAG_S, "listing", NOW, backfill=True)
        news.store(self.db, [it], news.BINANCE, NOW)

    def jump_market(self, coins_events, months, jump=1.03):
        """Each coin's price is 100 and jumps by `jump` in the first hour after its own event; BTC stays flat."""
        for y, m in months:
            self.klines("BTCUSDT", y, m, lambda ts: 50000.0)
            for coin, t in coins_events:
                self.klines(coin + "USDT", y, m, lambda ts, t=t: 100.0 * (jump if ts >= -(-t // H) * H else 1.0))


class Rules(Base):
    def test_fixed_types_and_outcomes(self):
        self.assertEqual(len(hypogen.TYPES) * len(hypogen.OUTCOMES), 60)
        self.assertEqual(hypogen.types_of("Binance Will List Arweave (AR) in the Innovation Zone"),
                         ["spot_listing", "innovation_zone"])
        self.assertEqual(hypogen.types_of("Binance Futures Will Launch USDT-Margined REEF Perpetual Contract"),
                         ["futures_listing"])
        self.assertEqual(hypogen.types_of("Binance Futures Will Launch Coin-Margined XRP Perpetual"), [])
        self.assertEqual(hypogen.types_of("Binance Will Delist MCO (MCO) on 2020/11/02"), ["delisting"])
        self.assertEqual(hypogen.types_of("Binance Futures Will Delist FOOUSDT Perpetual"), ["futures_delisting"])
        self.assertEqual(hypogen.types_of("Binance Will Update the Leverage & Margin Tiers of FOOUSDT"),
                         ["margin_tiers"])
        self.assertEqual(hypogen.types_of("Binance Will Add DGB (DGB) on Isolated Margin"), ["margin"])
        self.assertEqual(hypogen.types_of("Binance Concludes Mask Learn & Trade (MASK)"), [])     # precision: whole words

    def test_events_are_traced_point_in_time_and_deduplicated_per_30_days(self):
        self.announce("AAA", T(2020, 6, 10))
        self.announce("AAA", T(2020, 6, 20), sid="dup")              # 10 days later: the same event
        self.announce("AAA", T(2020, 8, 1), sid="later")             # > 30 days: a new event
        self.announce("BBB", T(2022, 3, 1))                          # outside explore0
        ev = hypogen.events(hypogen._items(self.db), *hypogen.bounds("explore0"))["spot_listing"]
        self.assertEqual([(e["coin"], e["t"]) for e in ev], [("AAA", T(2020, 6, 10)), ("AAA", T(2020, 8, 1))])
        self.assertTrue(all(isinstance(e["obs"], int) for e in ev))

    def test_reader_refuses_every_month_outside_its_phase_and_2024(self):
        r = hypogen.Reader("explore0")
        for y, m in ((2020, 2), (2022, 1), (2024, 1), (2025, 3)):
            with self.assertRaises(hypogen.Refused):
                r.month("AAAUSDT", "klines", y, m)
        with self.assertRaises(hypogen.Refused):
            hypogen.Reader("validation3").month("AAAUSDT", "funding", 2024, 1)
        with self.assertRaises(hypogen.Refused):
            hypogen.Reader("holdout")
        self.assertEqual(hypogen.bounds("validation3")[1], int(measure.END))
        self.assertEqual(r.month("AAAUSDT", "klines", 2020, 6), {})          # not cached, no network: no data

    def test_outcomes(self):
        t = T(2020, 6, 10, 5) + 1800
        self.jump_market([("AAA", t)], [(2020, 5), (2020, 6)])
        self.funding("AAAUSDT", 2020, 5, lambda ts: 0.0001)
        self.funding("AAAUSDT", 2020, 6, lambda ts: 0.0001 if ts <= t else 0.0004)
        r = hypogen.Reader("explore0")
        y, why = hypogen.outcome(r, "AAA", t, "ar_1d")
        self.assertAlmostEqual(y, __import__("math").log(1.03))
        self.assertAlmostEqual(hypogen.outcome(r, "AAA", t, "fund_7d")[0], 0.0003)
        self.assertEqual(hypogen.outcome(r, "AAA", t, "vol_3d")[1], "zero volatility")
        self.assertAlmostEqual(hypogen.outcome(r, "AAA", t, "volume_1d")[0], 0.0)
        self.assertEqual(hypogen.outcome(r, "BBB", t, "ar_1d")[1], "missing price")
        self.assertEqual(hypogen.outcome(r, "AAA", T(2020, 3, 3), "fund_7d")[1], "window outside the phase")


class Screening(Base):
    def setup_pass(self, n=20, jump=1.03):
        evs = []
        for i in range(n):
            coin = f"C{i:02d}"
            t = T(2020 + i % 2, 6, 10 + i // 2, 3) + 900
            evs.append((coin, t))
            self.announce(coin, t)
        self.jump_market(evs, [(2020, 4), (2020, 5), (2020, 6), (2021, 4), (2021, 5), (2021, 6)], jump)
        return evs

    def test_a_clear_effect_passes_the_screen_and_writes_a_draft(self):
        self.setup_pass()
        res = hypogen.screen(self.db, "spot_listing|ar_1d|m17", no_net)
        self.assertEqual(res["verdict"], "SCREEN_PASS", res.get("reason"))
        self.assertEqual((res["n"], res["direction"]), (20, 1))
        self.assertEqual(res["label"], "EXPLORATORY (never evidence)")
        self.assertEqual(res["placebo"]["n"], 20)
        path = hypogen.draft(res)
        with open(path) as f:
            spec = json.load(f)
        self.assertEqual((spec["key"], spec["direction"], spec["type"]), ("spot_listing|ar_1d|m17", 1, "spot_listing"))
        self.assertTrue(os.path.exists(path[:-5] + ".md"))

    def test_a_small_effect_fails_on_cost_and_few_events_are_untestable(self):
        self.setup_pass(jump=1.002)
        res = hypogen.screen(self.db, "spot_listing|ar_1d|m17", no_net)
        self.assertEqual(res["verdict"], "SCREEN_FAIL")
        self.assertIn("|mean| >= 0.0046", res["reason"])
        self.assertEqual(hypogen.screen(self.db, "launchpool|ar_1d|m17", no_net)["verdict"], "UNTESTABLE")
        self.assertEqual(hypogen.screen(self.db, "futures_listing|fund_7d|m17", no_net)["verdict"], "COVERED")

    def test_enqueue_records_candidates_once_runs_one_screen_at_a_time_and_never_repeats_a_result(self):
        self.assertEqual(hypogen.enqueue(self.db, NOW, lock_list=[]), 0)           # no announcements: nothing
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=?", hypogen.EV_HYP)[0], 0)
        self.setup_pass()
        self.assertEqual(hypogen.enqueue(self.db, NOW, lock_list=[]), 1)
        self.assertEqual(hypogen.enqueue(self.db, NOW + 1, lock_list=[]), 0)       # one at a time
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=?", hypogen.EV_HYP)[0], 60)
        hyp = json.loads(self.db.one("SELECT payload FROM events WHERE kind=? LIMIT 1", hypogen.EV_HYP)[0])
        self.assertEqual(set(hyp["sources"]), {"detector", "events", "first_obs", "last_obs", "events_sha256"})
        job = jobs.claim(self.db, "cost-1", ("hypo_screen",))
        first = job["payload"]["key"]
        out = hypogen.step_screen(self.db, job, "cost-1", get=no_net)
        jobs.complete(self.db, job["job_id"], "cost-1", out)
        self.assertEqual(hypogen.step_screen(self.db, job, "cost-1", get=no_net)["skipped"],
                         "already screened (point 4)")
        hypogen._CACHE.clear()
        self.assertEqual(hypogen.enqueue(self.db, NOW + 2, lock_list=[]), 1)
        nxt = json.loads(self.db.one("SELECT payload FROM jobs WHERE kind='hypo_screen' AND status='queued'")[0])["key"]
        self.assertNotEqual(nxt, first)
        c = {x["key"]: x for x in hypogen.candidates(self.db, NOW + 3, fresh=True)}
        self.assertEqual(c[first]["status"], out["verdict"])
        self.assertEqual(c["futures_listing|fund_7d|m17"]["status"], "COVERED")
        self.assertGreater(c[nxt]["priority"], 0)
        v = hypogen.view(self.db, NOW + 3)
        self.assertEqual(v["total"], 60)
        self.assertEqual([r["key"] for r in v["results"]], [first])


class Locked(Base):
    KEY = "spot_listing|ar_1d|m17"

    def spec(self):
        return json.dumps({"key": self.KEY, "type": "spot_listing", "outcome": "ar_1d", "direction": 1}) + "\n"

    def test_locks_need_the_committed_draft_with_the_same_sha256(self):
        raw = self.spec()
        sha = hashlib.sha256(raw.encode()).hexdigest()
        text = f"intro `LÅS-17 <nøgle> <sha256>`\nLÅS-17 {self.KEY} {sha}\nLÅS-17 other|ar_7d|m17 {'0' * 64}\n"
        got = hypogen.locks(text, read=lambda p: raw if p.endswith(hypogen.fname(self.KEY) + ".json") else
                            (_ for _ in ()).throw(IOError(p)))
        self.assertEqual([(k, i) for k, _, i, _ in got], [(self.KEY, 1)])
        self.assertEqual(hypogen.locks(f"LÅS-17 {self.KEY} {'1' * 64}\n", read=lambda p: raw), [])

    def test_a_locked_hypothesis_is_measured_once_on_train3_then_validation3(self):
        evs = []
        for i in range(16):
            evs.append((f"T{i:02d}", T(2022, 6, 5 + i, 3) + 900))
        for i in range(8):
            evs.append((f"V{i:02d}", T(2023, 9, 5 + i, 3) + 900))
        for c, t in evs:
            self.announce(c, t)
        self.jump_market(evs, [(2022, 6), (2023, 9)])
        raw = self.spec()
        lock = [(self.KEY, hashlib.sha256(raw.encode()).hexdigest(), 1, json.loads(raw))]
        self.assertEqual(hypogen.enqueue(self.db, NOW, lock_list=lock), 2)     # a screen and the measurement
        job = jobs.claim(self.db, "validation-1", ("hypo_measure",))
        out = hypogen.step_measure(self.db, job, "validation-1", get=no_net, lock_list=lock)
        self.assertEqual(out["verdict"], "PASS", out)
        ev = json.loads(self.db.one("SELECT payload FROM events WHERE kind=?", measure.EVENT)[0])
        self.assertEqual((ev["rule"], ev["alpha"], ev["phases"]["train3"]["n"], ev["phases"]["validation3"]["n"]),
                         ("17", 0.025, 16, 8))
        self.assertEqual(hypogen.step_measure(self.db, job, "validation-1", lock_list=lock)["skipped"],
                         "already measured")
        with self.assertRaises(pipeline.StepError):
            hypogen.step_measure(self.db, {"payload": {"key": "launchpool|ar_1d|m17"}}, "validation-1", lock_list=lock)

    def test_the_fleet_runs_the_new_jobs_on_existing_agents(self):
        kinds = {name: k for name, _, k, *_ in fleet.ROSTER}
        self.assertIn("hypo_screen", kinds["cost-1"])
        self.assertIn("hypo_screen", kinds["cost-2"])
        self.assertIn("hypo_measure", kinds["validation-1"])
        self.assertIn("hypo_measure", kinds["validation-2"])
        self.assertEqual(len(fleet.ROSTER), 18)                  # no new agent or worker
        self.assertIn("hypo_screen", pipeline.HANDLERS)
        self.assertIn("hypo_measure", pipeline.HANDLERS)


if __name__ == "__main__":
    unittest.main()
