"""Amendment 22: K3 forward collection and screening - point-in-time selection, no interpolation, duplicates once,
interval changes and missed rounds counted, books at entry/exit only, placebo without hourly settlers, a planted effect
passes, noise fails, a mechanism below the cost rule is not tradable, and one frozen look after 60 rounds on 20 days."""
import json
import math
import os
import random
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import k3, scanner  # noqa: E402
from lab.db import DB  # noqa: E402

H = 3600
S = 1_800_014_400                       # a 4-hour settlement (S % 14400 == 0)
COINS = {                               # symbol: (lastFundingRate, interval hours)
    "HIGH1USDT": (0.0030, 4), "HIGH2USDT": (0.0004, 4), "HIGH3USDT": (0.0020, 8), "HOURLYUSDT": (0.0002, 1),
    "LOW1USDT": (-0.0010, 4), "LOW2USDT": (-0.0008, 4), "LOW3USDT": (-0.0030, 8),
    "C1USDT": (0.0001, 8), "C2USDT": (0.00005, 4), "C3USDT": (0.0, 8), "C4USDT": (0.00002, 4),
    "MIDUSDT": (0.0003, 8),             # 0.03 %/8 h: in no group
    "GONEUSDT": (0.0050, 4),            # delisted: excluded
    "BTCUSDT": (0.0001, 8),
}
PERPS = set(COINS)
INTERVALS = {s: iv for s, (_, iv) in COINS.items()}


def book(levels=50, qty=100.0, px=1.0):
    return {"bids": [[f"{px - 0.0001 * (i + 1):.6f}", str(qty)] for i in range(levels)],
            "asks": [[f"{px + 0.0001 * (i + 1):.6f}", str(qty)] for i in range(levels)]}


class Feed:
    """premiumIndex rows per pass: a mark path per coin, Binance time a few seconds before the lab's ts."""
    def __init__(self, path=None, skip=(), next_ts=None, rates=None):
        self.path = path or (lambda sym, t: 1.0)
        self.skip, self.next_ts, self.rates = set(skip), next_ts or {}, rates or {}
        self.depth_calls = []

    def rows(self, t):
        out = []
        for sym, (rate, iv) in COINS.items():
            if (sym, t) in self.skip:
                continue
            nxt = self.next_ts.get(sym, lambda t: S if t < S else S + iv * H)(t)
            out.append({"symbol": sym, "markPrice": str(self.path(sym, t)), "indexPrice": "1.0",
                        "lastFundingRate": str(self.rates.get(sym, rate)), "nextFundingTime": nxt * 1000,
                        "time": (t - 3) * 1000})
        return out

    def get(self, url):
        self.depth_calls.append(url)
        return book()


def run(db, feed, start=S - 35 * 60, end=S + 2 * H + 36 * 60, step=60):
    for t in range(start, end, step):
        k3.observe(db, t, feed.rows(t), INTERVALS, PERPS, feed.get, delisted=lambda now: {"GONE": "Delist GONE"})


class Collection(unittest.TestCase):
    def setUp(self):
        k3._SEEN.clear()
        k3._BOOKS.clear()

    def test_point_in_time_selection_groups_and_exclusions(self):
        db = DB(":memory:")
        feed = Feed()
        run(db, feed, end=S - 33 * 60)
        sel = k3.selection(db, S)
        self.assertEqual(sel["select_ts"], S - 35 * 60)
        g = sel["groups"]
        self.assertEqual(g["high"], ["HIGH1USDT", "HIGH3USDT", "HOURLYUSDT", "HIGH2USDT"])   # 0.6/0.2/0.16/0.08 %
        self.assertEqual(g["low"], ["LOW3USDT", "LOW1USDT", "LOW2USDT"])          # -0.3, -0.2, -0.16 %/8 h
        self.assertNotIn("GONEUSDT", json.dumps(g))                                  # delisting announcement
        self.assertNotIn("BTCUSDT", json.dumps(g))
        self.assertNotIn("MIDUSDT", json.dumps(g))
        self.assertEqual(sorted(g["control"]), ["C1USDT", "C2USDT", "C3USDT", "C4USDT"])
        later = Feed(rates={"MIDUSDT": 0.01})                                         # a later rate changes nothing
        run(db, later, start=S - 33 * 60, end=S - 32 * 60)
        self.assertEqual(k3.selection(db, S)["groups"], g)
        self.assertEqual(db.one("SELECT COUNT(*) FROM observations WHERE metric='selection'")[0], 1)

    def test_a_round_without_a_pass_before_s_minus_31_is_missed(self):
        db = DB(":memory:")
        run(db, Feed(), start=S - 30 * 60, end=S - 25 * 60)
        self.assertIsNone(k3.selection(db, S))
        self.assertEqual(db.one("SELECT COUNT(*) FROM observations WHERE metric='missed'")[0], 1)
        self.assertEqual(db.one("SELECT COUNT(*) FROM observations WHERE metric='mark'")[0], 0)

    def test_books_once_at_entry_and_exit_and_never_late(self):
        db = DB(":memory:")
        feed = Feed()
        run(db, feed, end=S + 5 * 60)
        phases = [json.loads(r[0])["phase"] for r in db.q("SELECT payload FROM observations WHERE metric='book'")]
        traded = 7
        self.assertEqual((phases.count("entry"), phases.count("exit")), (traded, traded))
        db2 = DB(":memory:")                                                          # a restart at S - 20 min
        k3._BOOKS.clear()
        k3.select(db2, S, S - 35 * 60, Feed().rows(S - 35 * 60), INTERVALS, PERPS, {})
        run(db2, Feed(), start=S - 20 * 60, end=S - 10 * 60)
        self.assertEqual(db2.one("SELECT COUNT(*) FROM observations WHERE metric='book'")[0], 0)

    def test_no_interpolation_duplicates_once_stale_and_interval_change(self):
        db = DB(":memory:")
        path = lambda sym, t: 1.0 * math.exp(-0.01 * (sym == "HIGH1USDT") * (t >= S - 120))
        skip = {("LOW1USDT", t) for t in range(S - 33 * 60, S - 29 * 60)}            # no mark around S - 31 min
        nxt = {"HIGH2USDT": lambda t: S + 4 * H if t >= S - 10 * 60 else S}           # interval changed at S - 10 min
        feed = Feed(path=path, skip=skip, next_ts=nxt)
        run(db, feed, end=S + 40 * 60)
        k3._SEEN.clear()                                                              # a restart repeats one pass
        k3.observe(db, S - 5 * 60, feed.rows(S - 5 * 60), INTERVALS, PERPS, feed.get)
        g = k3.round_values(db, S, k3.selection(db, S))
        self.assertNotIn("LOW1USDT", g["low"])                                        # missing endpoint: dropped
        self.assertNotIn("HIGH2USDT", g["high"])                                      # interval change: dropped
        self.assertAlmostEqual(g["high"]["HIGH1USDT"]["r_pre"], -0.01, places=9)
        self.assertAlmostEqual(g["control"]["C1USDT"]["r_pre"], 0.0, places=12)
        series = {100.0: (1.0, S), 160.0: (2.0, S)}
        self.assertIsNone(k3.endpoint(series, 300))                                    # 140 s old: stale
        self.assertEqual(k3.endpoint(series, 200), 2.0)

    def test_placebo_window_has_no_hourly_settlers(self):
        db = DB(":memory:")
        run(db, Feed())
        syms = {r[0] for r in db.q("SELECT instrument FROM observations WHERE metric='mark' AND "
                                   "json_extract(payload, '$.window')='placebo'")}
        self.assertNotIn("HOURLYUSDT", syms)
        self.assertIn("HIGH1USDT", syms)
        self.assertIn("BTCUSDT", syms)

    def test_round_audit_counts_quality_and_flags_protocol_deviations(self):     # amendment 22 precision 2
        db = DB(":memory:")
        nxt = {"BTCUSDT": lambda t: S + 4 * H}                                        # BTC does not settle at S
        feed = Feed(next_ts=nxt)
        run(db, feed)
        self.assertEqual(k3.maybe_audit(db, S + 2 * H + 30 * 60), [(S, "real", "gyldig")])   # placebo still open
        out = k3.maybe_audit(db, S + 2 * H + 36 * 60)
        self.assertEqual(out, [(S, "placebo", "gyldig")])
        self.assertEqual(k3.maybe_audit(db, S + 3 * H), [])                         # once per round and window
        a = k3.status(db, S + 3 * H)["audit"]
        self.assertEqual(a["counts"], {"gyldig": 2})
        real = a["latest"][0]
        self.assertEqual((real["duplicates"], real["coins_with_problems"], real["deviations"]), (0, {}, []))
        self.assertEqual(real["books"]["entry"], {"ok": 0, "error": 0, "censored": 7})   # the fixture book holds
        self.assertEqual(real["books"]["exit"]["censored"], 7)                             # < 5 000 USD: censored
        self.assertNotIn("r_pre", json.dumps(a))                                     # counts only, never a return
        db2 = DB(":memory:")                                                          # a deviation: placebo with an
        k3._SEEN.clear()                                                              # hourly settler
        k3._BOOKS.clear()
        run(db2, Feed(next_ts=nxt))
        db2.append("observations", ts=S + 2 * H, detector="k3/1", source="t", instrument="HOURLYUSDT", metric="mark",
                   value=1.0, threshold=None, flagged=0,
                   payload={"S": S, "window": "placebo", "group": "high", "time": (S + 2 * H) * 1000, "next_ts": S})
        sel = k3.selection(db2, S)
        bad = k3.audit_round(db2, S, "placebo", S + 3 * H)
        self.assertEqual(bad["status"], "karantæne")                                 # a stored hourly settler in
        self.assertIn("HOURLYUSDT", bad["deviations"][0])                            # placebo is a deviation
        self.assertEqual(bad["coins_present"], bad["coins_expected"] + 1)
        sel_hourly = [s for s, h in sel["interval_h"].items() if h == 1]
        self.assertEqual(sel_hourly, ["HOURLYUSDT"])
        db3 = DB(":memory:")                                                          # missing marks: ugyldig
        k3._SEEN.clear()
        k3._BOOKS.clear()
        skip = {(s, t) for s in ("LOW1USDT", "LOW2USDT") for t in range(S - 33 * 60, S + 40 * 60)}   # after selection
        run(db3, Feed(skip=skip, next_ts=nxt), end=S + 36 * 60)
        r = k3.audit_round(db3, S, "real", S + 36 * 60)
        self.assertEqual((r["status"], r["directions_valid"]), ("ugyldig", {"high": True, "low": False}))
        self.assertEqual(r["coins_with_problems"]["LOW1USDT"]["missing"], ["m-31", "m-1", "m+1", "m+31"])

    def test_k3_never_stops_premium_watch(self):
        db = DB(":memory:")

        def get(url):
            if "exchangeInfo" in url:
                return {"symbols": [{"symbol": "AAAUSDT", "contractType": "PERPETUAL", "underlyingType": "COIN",
                                     "status": "TRADING", "quoteAsset": "USDT"}]}
            if "fundingInfo" in url:
                return []
            return [{"symbol": "AAAUSDT", "markPrice": "1", "indexPrice": "1", "lastFundingRate": "0.0001"}]
        with mock.patch.object(k3, "observe", side_effect=RuntimeError("boom")):
            out = scanner.premium_watch(db, get, S - 30 * 60, post=lambda u, b: [{"universe": []}, []])
            scanner.premium_watch(db, get, S - 29 * 60, post=lambda u, b: [{"universe": []}, []])
        self.assertIn("boom", out["k3"]["error"])
        self.assertEqual(db.one("SELECT COUNT(*) FROM observations WHERE detector='k3/1' AND metric='error'")[0], 1)
        self.assertGreater(out["observations"], 0)


def synth(n, d_high, d_low, v_high=0.0, c=0.0046, noise=0.002, seed=1, days=None):
    rng = random.Random(seed)
    return [{"S": S + i * 4 * H, "day": f"d{i // 3 if days is None else i % days}",
             "d_high": d_high + rng.gauss(0, noise), "d_low": d_low + rng.gauss(0, noise),
             "v_high": v_high + rng.gauss(0, noise), "c_high": c, "v_low": None, "c_low": None} for i in range(n)]


class Screening(unittest.TestCase):
    def test_planted_effect_passes_noise_fails_and_cost_rule_holds(self):
        placebo = synth(60, 0.0, 0.0, seed=5)
        r = k3.evaluate(synth(60, -0.006, 0.0, v_high=0.006), placebo)
        self.assertEqual(r["high"]["verdict"], "PASS")
        self.assertEqual(r["low"]["verdict"], "SCREEN_FAIL")
        r = k3.evaluate(synth(60, -0.006, 0.0, v_high=0.003), placebo)                # real but below 0.46 %
        self.assertEqual(r["high"]["verdict"], "SCREEN_FAIL (mekanisme bekræftet, ikke handlebar)")
        r = k3.evaluate(synth(60, 0.0, 0.0, v_high=0.006, seed=3), placebo)
        self.assertEqual(r["high"]["verdict"], "SCREEN_FAIL")
        r = k3.evaluate(synth(60, -0.006, 0.0, v_high=0.006), synth(60, -0.006, 0.0, seed=4))   # placebo moves too
        self.assertFalse(r["high"]["placebo_ok"])
        self.assertEqual(r["high"]["verdict"], "SCREEN_FAIL")
        r = k3.evaluate(synth(60, -0.006, 0.0, v_high=0.006), synth(59, 0.0, 0.0))        # too little placebo
        self.assertFalse(r["high"]["placebo_ok"])

    def test_no_statistic_before_the_minimum_and_one_frozen_look(self):
        db = DB(":memory:")
        st = k3.status(db, S)
        self.assertEqual(st["directions"]["high"]["status"], "NO_DECISION")
        self.assertNotIn("p", json.dumps(st["directions"]).replace('"why"', ""))
        few = synth(60, -0.006, 0.0, v_high=0.006, days=19)                           # 60 rounds, 19 days
        with mock.patch.object(k3, "rounds", lambda db, cutoff, window="real": few):
            self.assertEqual(k3.maybe_freeze(db, S + 86400), {})
        enough = synth(60, -0.006, 0.0, v_high=0.006, days=20)
        with mock.patch.object(k3, "rounds", lambda db, cutoff, window="real":
                               enough if window == "real" else synth(60, 0.0, 0.0, seed=5)):
            self.assertEqual(k3.maybe_freeze(db, S + 86400)["high"], "PASS")
            self.assertEqual(k3.maybe_freeze(db, S + 2 * 86400), {})                  # never recomputed
            st = k3.status(db, S + 2 * 86400)
        self.assertEqual(st["directions"]["high"]["status"], "PASS")
        self.assertEqual(st["directions"]["low"]["status"], "SCREEN_FAIL")                # each direction once
        self.assertEqual(db.one("SELECT COUNT(*) FROM events WHERE kind='research.k3_result'")[0], 2)

    def test_after_the_deadline_only_rounds_before_it_count_and_late_minimums_are_untestable(self):
        db = DB(":memory:")
        seen = []

        def fake(db, cutoff, window="real"):
            seen.append(cutoff)
            return synth(60, -0.006, 0.0, v_high=0.006, days=20) if cutoff > k3.DEADLINE_END - 86400 else []
        late = k3.DEADLINE_END + 10 * 86400 + 3600
        with mock.patch.object(k3, "rounds", fake):
            k3.maybe_freeze(db, late)                                                 # the lab ran late: the cutoff
        self.assertEqual(max(seen), k3.DEADLINE_END)                                  # is still the deadline
        db2 = DB(":memory:")
        with mock.patch.object(k3, "rounds", lambda db, cutoff, window="real": []):
            self.assertEqual(k3.maybe_freeze(db2, late), {})
            self.assertEqual(k3.status(db2, late)["directions"]["high"]["status"], "UNTESTABLE")


if __name__ == "__main__":
    unittest.main()
