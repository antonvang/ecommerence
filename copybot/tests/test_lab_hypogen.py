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
        name = f"{sym}-1h-{y}-{m:02d}.zip" if kind in ("klines", "spot_klines") else f"{sym}-fundingRate-{y}-{m:02d}.zip"
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
        self.assertEqual(len(hypogen.TYPES) * len(hypogen.OUTCOMES), 108)          # 60 (17) + 48 (17a)
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


class FirstPrice(Base):
    def test_17a_outcomes_start_at_the_first_available_price_on_perp_and_spot(self):
        t = T(2020, 6, 10, 5) + 1800
        start = T(2020, 6, 11, 2)                                   # the market opens 20.5 h after the announcement

        def write(kind, y, m):
            for sym, px in (("NEWUSDT", lambda ts: 10.0 if ts < start + 3 * H else 12.0), ("BTCUSDT", lambda ts: 9e3)):
                a, b = T(y, m), T(y + (m == 12), 1 if m == 12 else m + 1)
                rows = [(ts * 1000, px(ts), 0, 0, px(ts), 1, ts * 1000 + H * 1000 - 1, 5.0) for ts in range(a, b, H)
                        if sym == "BTCUSDT" or ts >= start]
                self.zip(kind if kind == "klines" else "spot_klines", sym, y, m, rows)
        for y, m in ((2020, 6), (2020, 7)):
            write("klines", y, m)
            write("spot", y, m)
        r = hypogen.Reader("explore0")
        import math
        for name in ("far_1d", "far_7d", "sar_1d", "sar_7d"):
            y, why = hypogen.outcome(r, "NEW", t, name)
            self.assertAlmostEqual(y, math.log(1.2), msg=name)
        self.assertEqual(hypogen.outcome(r, "NEW", t, "ar_1d")[1], "missing price")     # 17: no price at t
        self.assertEqual(hypogen.outcome(r, "OLD", t, "sar_1d")[1], "no price within 72 h")
        self.assertTrue(hypogen._url("NEWUSDT", "spot", 2020, 6).startswith(data.SPOT_BASE))


class MarginTitles(Base):
    """Amendment 17c: margin coins are read from the title by fixed rules (method m17c), only for the margin
    candidates m17 screened UNTESTABLE; screening and measurement are otherwise unchanged."""

    def margin(self, coin, usable):
        it = news.item("binance", f"m{coin}{usable}", "https://www.binance.com/x",
                       f"Cross Margin Trading for {coin} Enabled on Binance", usable - news.BACKFILL_LAG_S,
                       "binance_news", NOW, backfill=True)
        news.store(self.db, [it], news.BINANCE, NOW)

    def test_fixed_title_rules(self):
        cases = {
            "Binance Adds RAD & RARE on Isolated Margin, Stablecoins Annual Interest Rate Starts at 6.20%!": {"RAD", "RARE"},
            "Cross Margin Trading for 1INCH Enabled on Binance": {"1INCH"},
            "DOT, ANT, CRV, BAL and YFI Enabled on Binance Margin Trading": {"DOT", "ANT", "CRV", "BAL", "YFI"},
            "CELR/BUSD & FTM/BUSD Pairs Enabled on Isolated Margin, BUSD Annual Interest Rate Starts at 6.20%!":
                {"CELR", "FTM"},
            "Binance Adds CVC, FRONT, QI, RAD, TWT on Cross Margin and BIDR, T on Isolated Margin":
                {"CVC", "FRONT", "QI", "RAD", "TWT"},
            "Isolated Margin Trading for FET and ALGO Enabled on Binance": {"FET", "ALGO"},
            "Binance Adds USDC & BNB on Cross Margin": set(),                     # stablecoin and context: stop list
            "New BUSD Trading Pairs Enabled on Binance Isolated Margin": set(),
            "Tiered Leverage Up to 10x Enabled For Isolated Margin Trading On Binance": set()}
        for title, want in cases.items():
            with self.subTest(title=title):
                self.assertEqual(hypogen.coins_c(title), want)
                if want:
                    self.assertIn("margin", hypogen.types_of(title))

    def test_m17_finds_no_margin_coin_and_m17c_does(self):
        self.margin("FIL", T(2020, 6, 10))
        self.announce("AAA", T(2020, 6, 10))
        a, b = hypogen.bounds("explore0")
        items = hypogen._items(self.db)
        self.assertEqual(hypogen.events(items, a, b)["margin"], [])
        c = hypogen.events(items, a, b, hypogen.M17C)
        self.assertEqual([e["coin"] for e in c["margin"]], ["FIL"])
        self.assertEqual(c["spot_listing"], hypogen.events(items, a, b)["spot_listing"])   # other types: unchanged

    def test_candidates_only_where_m17_was_untestable(self):
        self.margin("FIL", T(2020, 6, 10))
        self.assertEqual(len(hypogen.candidates(self.db, NOW, fresh=True)), 108)
        self.db.event(hypogen.EV_SCREEN, "agent:cost-1", None, {"key": "margin|ar_1d|m17", "verdict": "UNTESTABLE"})
        self.db.event(hypogen.EV_SCREEN, "agent:cost-1", None, {"key": "margin|ar_7d|m17", "verdict": "SCREEN_FAIL"})
        c = {x["key"]: x for x in hypogen.candidates(self.db, NOW + 1, fresh=True)}
        self.assertEqual(len(c), 109)
        self.assertEqual((c["margin|ar_1d|m17c"]["status"], c["margin|ar_1d|m17c"]["events"]), ("QUEUED_FOR_SCREEN", 1))
        self.assertEqual(c["margin|ar_1d|m17c"]["rule"], hypogen.RULE_C)
        self.assertNotIn("margin|ar_7d|m17c", c)                       # an m17 result is never screened again
        self.assertEqual(hypogen.enqueue(self.db, NOW + 2, lock_list=[]), 1)
        rec = {json.loads(r[0])["key"]: json.loads(r[0]) for r in self.db.q("SELECT payload FROM events WHERE kind=?",
                                                                            hypogen.EV_HYP)}
        self.assertEqual(rec["margin|ar_1d|m17c"]["rule"], hypogen.RULE_C)
        self.assertEqual(rec["margin|ar_1d|m17"]["rule"], hypogen.RULE)

    def test_screen_and_locked_measurement_use_the_title_coins(self):
        evs = []
        for i, (y, m, n) in enumerate(((2020, 6, 10), (2021, 6, 10), (2022, 6, 16), (2023, 9, 8))):
            for j in range(n):
                coin, t = f"M{i}{j:02d}", T(y, m, 1 + j, 3) + 900
                evs.append((coin, t))
                self.margin(coin, t)
        months = [(y, m) for y in (2020, 2021, 2022, 2023) for m in (5, 6, 8, 9)]
        self.jump_market(evs, months)
        res = hypogen.screen(self.db, "margin|ar_1d|m17c", no_net)
        self.assertEqual((res["verdict"], res["n"], res["method"], res["rule"]),
                         ("SCREEN_PASS", 20, hypogen.M17C, hypogen.RULE_C), res.get("reason"))
        self.assertEqual(hypogen.screen(self.db, "margin|ar_1d|m17", no_net)["verdict"], "UNTESTABLE")
        with open(hypogen.draft(res)) as f:
            spec = json.load(f)
        self.assertEqual((spec["method"], spec["rule"]), (hypogen.M17C, hypogen.RULE_C))
        out = hypogen.measure_locked(self.db, "margin|ar_1d|m17c", "0" * 64, 2, spec)
        self.assertEqual(out["verdict"], "PASS", out.get("reason"))
        self.assertEqual((out["phases"]["train3"]["n"], out["phases"]["validation3"]["n"]), (16, 8))
        old = hypogen.measure_locked(self.db, "margin|ar_1d|m17", "0" * 64, 2, {**spec, "method": hypogen.METHOD})
        self.assertEqual(old["verdict"], "UNTESTABLE")


class ForwardPlacebo(Base):
    """Amendment 17e: under m17e the placebo moves to t + 30 d when t - 30 d has fewer than 15 events with data (a newly
    listed coin has no price a month before); everything else is m17's, and only m17 FAILs without a placebo get it."""

    def new_coins(self, n=20, again=False, may=False):
        """n coins whose files start in the event month (no price 30 days earlier unless `may`); the price jumps 3 % at
        the event and, with `again`, once more 30 days later (a drift of new coins, not of the announcement)."""
        evs = []
        for i in range(n):
            coin, t = f"N{i:02d}", T(2020 + i % 2, 6, 10 + i // 2, 3) + 900
            evs.append((coin, t))
            self.announce(coin, t)
        for y in (2020, 2021):
            for m in (5, 6, 7, 8):
                self.klines("BTCUSDT", y, m, lambda ts: 50000.0)
                for coin, t in evs:
                    if int(coin[1:]) % 2 == y - 2020 and (m >= 6 or may):
                        marks = (t, t + 30 * 24 * H) if again else (t,)
                        self.klines(coin + "USDT", y, m, lambda ts, mk=marks: 100.0 * 1.03 ** sum(
                            ts >= -(-x // H) * H for x in mk))
        return evs

    def test_a_new_coin_gets_the_forward_placebo_and_m17_keeps_its_result(self):
        self.new_coins()
        old = hypogen.screen(self.db, "spot_listing|ar_1d|m17", no_net)
        self.assertEqual((old["verdict"], old["placebo"]["n"], old["placebo"]["shift_days"]), ("SCREEN_FAIL", 0, -30))
        self.assertEqual(old["reason"], "failed: placebo p > 0.05 (n >= 15)")
        res = hypogen.screen(self.db, "spot_listing|ar_1d|m17e", no_net)
        self.assertEqual((res["verdict"], res["rule"], res["method"]), ("SCREEN_PASS", hypogen.RULE_E, hypogen.M17E),
                         res.get("reason"))
        self.assertEqual((res["n"], res["placebo"]["n"], res["placebo"]["shift_days"]), (20, 20, 30))
        self.assertEqual(res["events_sha256"], old["events_sha256"])           # the same events and outcomes as m17
        with open(hypogen.draft(res)) as f:
            spec = json.load(f)
        self.assertEqual(spec["placebo"], "samme mønter med t + 30 d")
        self.assertIn("blandt 124 kandidater", spec["risks"])

    def test_a_drift_that_goes_on_a_month_later_fails_the_forward_placebo(self):
        self.new_coins(again=True)
        res = hypogen.screen(self.db, "spot_listing|ar_1d|m17e", no_net)
        self.assertEqual((res["verdict"], res["placebo"]["shift_days"]), ("SCREEN_FAIL", 30))
        self.assertEqual(res["reason"], "failed: placebo p > 0.05 (n >= 15)")

    def test_the_backward_placebo_is_kept_where_it_has_data(self):
        self.new_coins(may=True)
        res = hypogen.screen(self.db, "spot_listing|ar_1d|m17e", no_net)
        self.assertEqual((res["verdict"], res["placebo"]["n"], res["placebo"]["shift_days"]), ("SCREEN_PASS", 20, -30))

    def test_candidates_only_for_m17_fails_whose_placebo_had_too_few_events(self):
        self.announce("AAA", T(2020, 6, 10))
        ev = lambda p: self.db.event(hypogen.EV_SCREEN, "agent:cost-1", None, p)   # noqa: E731
        ev({"key": "spot_listing|sar_7d|m17", "verdict": "SCREEN_FAIL", "placebo": {"n": 0, "p": None}})
        ev({"key": "spot_listing|sar_1d|m17", "verdict": "SCREEN_FAIL", "placebo": {"n": 40, "p": 0.01}})
        ev({"key": "staking|sar_7d|m17", "verdict": "SCREEN_FAIL", "placebo": {"n": 14, "p": None}})
        ev({"key": "airdrop|ar_1d|m17", "verdict": "UNTESTABLE"})
        c = {x["key"]: x for x in hypogen.candidates(self.db, NOW, fresh=True)}
        self.assertEqual(sorted(k for k in c if k.endswith("|m17e")), ["spot_listing|sar_7d|m17e", "staking|sar_7d|m17e"])
        self.assertEqual((c["spot_listing|sar_7d|m17e"]["status"], c["spot_listing|sar_7d|m17e"]["rule"]),
                         ("QUEUED_FOR_SCREEN", hypogen.RULE_E))
        self.assertEqual(len(c), 110)
        self.assertEqual(hypogen.enqueue(self.db, NOW + 1, lock_list=[]), 1)
        rec = {json.loads(r[0])["key"]: json.loads(r[0]) for r in self.db.q("SELECT payload FROM events WHERE kind=?",
                                                                            hypogen.EV_HYP)}
        self.assertEqual(rec["staking|sar_7d|m17e"]["rule"], hypogen.RULE_E)


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
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind=?", hypogen.EV_HYP)[0], 108)
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
        self.assertEqual(v["total"], 108)
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
