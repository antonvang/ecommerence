import json
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import command, moves, scanner  # noqa: E402
from lab.db import DB  # noqa: E402

H = 3600
NOW = 1_800_000_000 - 1_800_000_000 % H + 120          # 2 minutes into an hour


def klines(n=722, jump=0.0, start_px=100.0, end=NOW - 120, seed=1, vol_last=None):
    """n closed hourly klines ending at `end` (the current hour's open), small noise, `jump` added to the last log
    return; plus the open (unclosed) current hour, which must be ignored."""
    rnd, px, out = random.Random(seed), start_px, []
    t0 = end - n * H
    for i in range(n):
        r = rnd.gauss(0, 0.002) + (jump if i == n - 1 else 0.0)
        px *= math.exp(r)
        q = vol_last if (vol_last and i == n - 1) else 1000.0 + rnd.random()
        out.append([(t0 + i * H) * 1000, "0", "0", "0", f"{px:.6f}", "1", (t0 + (i + 1) * H) * 1000 - 1, f"{q}", 1, "0",
                    "0", "0"])
    out.append([end * 1000, "0", "0", "0", "999", "1", (end + H) * 1000 - 1, "1", 1, "0", "0", "0"])
    return out


def market(jumps=None, fail=(), stale=(), short=(), depth=True):
    jumps = jumps or {}

    def get(url):
        sym = url.split("symbol=")[1].split("&")[0]
        if sym in fail:
            raise OSError("boom")
        if "/klines" in url:
            if sym in stale:
                return klines(end=NOW - 120 - 4 * H)
            return klines(n=100 if sym in short else 722, jump=jumps.get(sym, 0.0), seed=sum(map(ord, sym)))
        if "/premiumIndex" in url:
            return {"markPrice": "100.1", "indexPrice": "100.0"}
        if "/depth" in url:
            if not depth:
                return {"bids": [], "asks": []}
            return {"bids": [[f"{100 - i * 0.01:.2f}", "100"] for i in range(50)],
                    "asks": [[f"{100.02 + i * 0.01:.2f}", "100"] for i in range(50)]}
        raise AssertionError(url)
    return get


class Stats(unittest.TestCase):
    def test_z_scores_use_the_closed_hours_and_the_trailing_720(self):
        s = moves.stats(klines(jump=0.02), NOW)
        self.assertEqual(s["returns"], 720)
        self.assertGreater(s["z_1h"], moves.Z1)                       # a 2 % hour against 0.2 % noise
        self.assertAlmostEqual(s["z_24h"], s["ret_24h"] / (s["sigma_1h"] * math.sqrt(24)))
        self.assertEqual(s["close_s"], NOW - 120)                      # the unclosed hour is ignored
        self.assertNotEqual(s["price"], 999.0)

    def test_short_history_gives_no_z(self):
        self.assertEqual(moves.stats(klines(n=100), NOW), {"short": 98})


class Detect(unittest.TestCase):
    def test_observations_flags_errors_and_no_proposals(self):
        obs, props = moves.detect(market(jumps={"XAUUSDT": -0.03}, fail=("CLUSDT",), stale=("BZUSDT",),
                                         short=("NATGASUSDT",)), None, NOW)
        self.assertEqual(props, [])
        by = {(o["instrument"], o["metric"]): o for o in obs}
        self.assertTrue(by[("XAUUSDT", "z_1h")]["flagged"])
        self.assertFalse(by[("BTCUSDT", "z_1h")]["flagged"])
        self.assertEqual(by[("XAUUSDT", "z_1h")]["detector"], "abnormal_move/1")
        self.assertEqual(by[("XAUUSDT", "z_1h")]["payload"]["venue"], "Binance USD-M perpetual")
        self.assertIn("boom", by[("CLUSDT", "error")]["payload"]["error"])
        self.assertIn("min old", by[("BZUSDT", "error")]["payload"]["error"])
        self.assertEqual(by[("NATGASUSDT", "history_short")]["value"], 98)
        self.assertAlmostEqual(by[("XAUUSDT", "premium")]["value"], 0.001)


class Triage(unittest.TestCase):
    BASE = {"class": "crypto", "flags": ["z_1h"], "z_1h": 5.0, "move_hour_s": NOW, "tails_720h": 0,
            "book": {"round_trip": 0.001}, "macro": {"releases": []}, "news": []}

    def t(self, **kw):
        return moves.triage({**self.BASE, **kw})

    def test_fixed_rules_in_order(self):
        self.assertEqual(self.t()["verdict"], "REJECT_TESTED")
        self.assertEqual(self.t()["explanations"], ["unexplained"])
        self.assertEqual(self.t(flags=["z_24h"])["verdict"], "NOT_SCREENED")
        self.assertEqual(self.t(flags=["volume_ratio"], z_1h=0.5)["verdict"], "REJECT_NOT_DIRECTIONAL")
        self.assertEqual(self.t(flags=["volume_ratio"], z_1h=3.0)["verdict"], "NOT_SCREENED")
        self.assertEqual(self.t(book={"error": "empty book"})["verdict"], "REJECT_ILLIQUID")
        self.assertEqual(self.t(book={"round_trip": 0.006})["verdict"], "REJECT_ILLIQUID")
        self.assertEqual(self.t(**{"class": "fx"})["verdict"], "FORWARD_ONLY")
        e = self.t(tails_720h=3, macro={"releases": [{"event": "FOMC statement"}]},
                   news=[{"published_ts": NOW + H + 1}])["explanations"]
        self.assertEqual(e, ["routine_tail", "macro_release"])                     # news after the hour explains nothing
        self.assertIn("news", self.t(news=[{"published_ts": NOW + 10}])["explanations"])

    def test_tails_are_counted_in_the_trailing_window(self):
        self.assertEqual(moves.stats(klines(), NOW)["tails_720h"], 0)


class Records(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        moves._KLINES.clear()
        moves._MACRO.update(ts=NOW, events=[], error=None)       # no network in tests

    def news(self, ts, title, published=None):
        p = {"title": title, "source": "coindesk", "published_ts": ts if published is None else published, "url": "u",
             "usable_from": ts}
        self.db.append("observations", ts=ts, detector="news/1", source="rss", instrument=title, metric="news_item",
                       value=ts, threshold=None, flagged=0, payload=p)

    def test_a_flagged_market_gets_one_analysis_record_with_context_and_no_candidate(self):
        self.news(NOW - 2 * H, "Gold slides as the dollar jumps after hot CPI")
        self.news(NOW - 2 * H, "Bitcoin ETF flows steady")                              # not a gold keyword
        self.news(NOW - 2 * H, "Fed statement on gold reserves", published=NOW - 9 * 86400)   # stored now, old
        s = scanner.run(self.db, ["abnormal_move"], get=market(jumps={"XAUUSDT": -0.03}), now=NOW)
        self.assertEqual(s["abnormal_move_records"], 1)
        self.assertEqual(s["created"], [])
        self.assertIsNone(self.db.one("SELECT 1 FROM experiments LIMIT 1"))
        r = self.db.q("SELECT payload FROM events WHERE kind='opportunity.move'")
        self.assertEqual(len(r), 1)
        p = json.loads(r[0]["payload"])
        self.assertEqual((p["instrument"], p["decisional"]), ("XAUUSDT", False))
        self.assertIn("z_1h", p["flags"])
        self.assertIn("BTCUSDT", p["others"])
        self.assertGreater(p["book"]["round_trip"], 0)
        self.assertEqual([x["title"] for x in p["news"]], ["Gold slides as the dollar jumps after hot CPI"])
        self.assertEqual(p["triage"]["verdict"], "FORWARD_ONLY")                      # amendment 21e: TradFi
        self.assertIn("news", p["triage"]["explanations"])
        self.assertEqual(p["triage"]["tails_720h"], p["tails_720h"])
        again = scanner.run(self.db, ["abnormal_move"], get=market(jumps={"XAUUSDT": -0.03}), now=NOW + 60)
        self.assertEqual(again["abnormal_move_records"], 0)                            # deduplicated for 6 h
        f = [x for x in command.feed(self.db)["items"] if x.get("tag") == "BEVÆGELSE"]
        self.assertEqual(len(f), 1)
        self.assertIn("Guld", f[0]["text"])
        self.assertIn("intet handles", f[0]["text"])
        self.assertIn("vurdering FORWARD_ONLY", f[0]["text"])

    def test_the_macro_calendar_marks_a_release_in_the_move_window(self):
        t = moves.stats(klines(jump=-0.03), NOW)["open_s"]
        cpi = {"event": "Consumer Price Index", "ts": t - 2 * H, "date": "d", "scheduled": True}
        fomc = {"event": "FOMC statement", "ts": t + 5 * H, "date": "d", "scheduled": True}
        m = moves.macro_near([cpi, fomc], None, t)
        self.assertEqual([x["event"] for x in m["releases"]], ["Consumer Price Index"])
        moves._MACRO.update(ts=0.0, events=[], error=None)
        ev, err = moves.calendar(NOW, fetch=lambda url: (_ for _ in ()).throw(OSError("down")))
        self.assertEqual(ev, [])
        self.assertIn("down", err)
        self.assertIn("error", moves.macro_near(ev, err, t))
        moves._MACRO.update(ts=0.0, events=[], error=None)

    def test_a_thin_book_is_reported_not_guessed(self):
        scanner.run(self.db, ["abnormal_move"], get=market(jumps={"XAUUSDT": -0.03}, depth=False), now=NOW)
        p = json.loads(self.db.one("SELECT payload FROM events WHERE kind='opportunity.move'")["payload"])
        self.assertEqual(p["book"], {"error": "empty book"})

    def test_the_forward_outcome_is_stored_once_after_24_hours(self):
        scanner.run(self.db, ["abnormal_move"], get=market(jumps={"XAUUSDT": -0.03}), now=NOW)
        move = self.db.one("SELECT id, payload FROM events WHERE kind='opportunity.move'")
        t = json.loads(move["payload"])["move_hour_s"]
        self.assertEqual(moves.outcomes(self.db, NOW + 2 * H), 0)                       # not due
        later = NOW + 25 * H
        moves._KLINES["XAUUSDT"] = moves._closed(klines(n=760, end=later - 120, seed=5), later)
        self.assertEqual(moves.outcomes(self.db, later), 1)
        self.assertEqual(moves.outcomes(self.db, later), 0)                             # once
        o = json.loads(self.db.one("SELECT payload FROM events WHERE kind='opportunity.outcome'")["payload"])
        self.assertEqual((o["move_id"], o["from_s"], o["to_s"]), (move["id"], t + H, t + H + 24 * H))

    def test_a_failing_analysis_never_stops_the_scan(self):
        orig = scanner.AFTER["abnormal_move"]
        scanner.AFTER["abnormal_move"] = lambda *a: 1 / 0
        try:
            s = scanner.run(self.db, ["abnormal_move"], get=market(), now=NOW)
        finally:
            scanner.AFTER["abnormal_move"] = orig
        self.assertGreater(s["observations"], 0)
        self.assertTrue(any("records failed" in e for e in s["errors"]))


if __name__ == "__main__":
    unittest.main()
