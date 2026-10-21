"""Amendment 16: the event and news scanner stores items once, keeps sources apart, records failures and never
trades; point-in-time fields; GDELT backs off after a refusal."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import news  # noqa: E402
from lab.db import DB  # noqa: E402

NOW = 1792600000


def binance_page(catalog, n=3, start=0, total=None):
    arts = [{"id": 1000 + start + i, "code": f"c{catalog}-{start + i}", "title": f"Binance Will List Foo{i} (FOO{i}) "
             f"and BARUSDT Perpetual", "type": 1, "releaseDate": (NOW - 3600 * (start + i)) * 1000}
            for i in range(n)]
    return json.dumps({"code": "000000", "data": {"catalogs": [{"catalogId": catalog, "total": total or n,
                                                                  "articles": arts}]}}).encode()


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Bitcoin hits a new high (BTC)</title><link>https://cointelegraph.com/a1</link><guid>g1</guid>
<pubDate>Wed, 21 Oct 2026 12:12:36 +0000</pubDate></item>
<item><title>Ether ETF flows</title><link>https://cointelegraph.com/a2</link><guid>g2</guid><pubDate>bad</pubDate></item>
</channel></rss>"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labnews")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        news._STATE.update({"gdelt_next": 0.0, "gdelt_wait": news.GDELT_EVERY})

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, fail=()):
        def g(url):
            for f in fail:
                if f in url:
                    raise OSError(f"refused {f}")
            if url.startswith(news.BINANCE):
                cat = int(url.split("catalogId=")[1].split("&")[0])
                page = int(url.split("pageNo=")[1].split("&")[0])
                return binance_page(cat, start=3 * (page - 1)) if page <= 2 else binance_page(cat, n=0)
            if url.startswith(news.GDELT):
                return json.dumps({"articles": [{"url": "https://x.example/a", "title": "Crypto markets",
                                                 "seendate": "20261021T120000Z", "domain": "x.example"}]}).encode()
            return RSS
        return g

    def stored(self):
        return news.items(self.db, limit=1000)


class Scanner(Base):
    def test_items_are_stored_once_with_point_in_time_fields(self):
        r = news.run(self.db, self.get(), now=NOW)
        self.assertEqual(r["errors"], [])
        first = len(self.stored())
        self.assertEqual(first, 3 * 3 + 2 * 2 + 1)                  # 3 Binance categories, 2 feeds, GDELT
        news.run(self.db, self.get(), now=NOW + 600)                # same items again: nothing new
        self.assertEqual(len(self.stored()), first)
        x = [i for i in self.stored() if i["source"] == "binance"][0]
        self.assertEqual(x["fetched_ts"], NOW)
        self.assertEqual(x["usable_from"], NOW)                     # forward items: usable from collection
        self.assertIn("FOO0", x["coins"]) if x["title"].startswith("Binance Will List Foo0") else None
        rss = [i for i in self.stored() if i["source"] == "cointelegraph"]
        self.assertEqual({i["published_ts"] for i in rss} - {None}, {1792584756.0})   # an unparsable date is None
        g = [i for i in self.stored() if i["source"] == "gdelt"][0]
        self.assertEqual(g["published_ts"], 1792584000)

    def test_coins_by_fixed_rules(self):
        self.assertEqual(news.coins("Binance Will List Foo (FOO) and BARUSDT, BAZUSDC Perpetual"), ["BAR", "BAZ", "FOO"])
        self.assertEqual(news.coins("Bitcoin rallies"), [])
        # amendment 16b: Binance futures-launch titles name bare tickers
        self.assertEqual(news.coins("Binance Futures Will Launch USDⓈ-M MOVR Perpetual Contract With Up to 50x "
                                    "Leverage"), ["MOVR"])
        self.assertEqual(news.coins("Binance Futures Will Launch RSR & LRC USDT-Margined Perpetual Contracts With Up "
                                    "to 50x Leverage"), ["LRC", "RSR"])
        self.assertEqual(news.coins("Binance Futures Will Launch USDⓈ-M 1000RATS, ACE and JTO Perpetual Contracts"),
                         ["1000RATS", "ACE", "JTO"])
        self.assertEqual(news.coins("Binance Futures Will Launch Coin-Margined XRP Perpetual"), ["XRP"])

    def test_one_failing_source_is_recorded_and_the_others_continue(self):
        r = news.run(self.db, self.get(fail=("cointelegraph",)), now=NOW)
        self.assertEqual(len(r["errors"]), 1)
        self.assertGreater(len(self.stored()), 0)
        err = self.db.q("SELECT source, payload FROM observations WHERE metric='news_error'")
        self.assertEqual([e["source"] for e in err], [news.RSS["cointelegraph"]])

    def test_gdelt_backs_off_after_a_refusal(self):
        news.run(self.db, self.get(fail=("gdeltproject",)), now=NOW)
        self.assertEqual(news._STATE["gdelt_next"], NOW + 2 * news.GDELT_EVERY)
        r = news.run(self.db, self.get(), now=NOW + 600)            # still waiting: GDELT not asked
        self.assertNotIn(news.GDELT, r["stored"])
        r = news.run(self.db, self.get(), now=NOW + 2 * news.GDELT_EVERY)
        self.assertIn(news.GDELT, r["stored"])

    def test_backfill_marks_items_and_delays_their_use(self):
        n = news.backfill(self.db, self.get(), now=NOW, sleep=lambda s: None)
        self.assertEqual(n, {"listing": 6, "delisting": 6, "binance_news": 6})
        b = [i for i in self.stored() if i["backfill"]]
        self.assertTrue(b and all(i["usable_from"] == i["published_ts"] + news.BACKFILL_LAG_S for i in b))
        self.assertEqual(news.backfill(self.db, self.get(), now=NOW, sleep=lambda s: None),
                         {"listing": 0, "delisting": 0, "binance_news": 0})       # a rerun stores nothing twice

    def test_backfill_waits_after_a_refusal_and_stops_a_category_without_crashing(self):
        calls, waits = {"n": 0}, []
        inner = self.get()

        def flaky(url):
            calls["n"] += 1
            if "catalogId=48" in url and "pageNo=2" in url and calls["n"] < 4:
                raise OSError("HTTP Error 429: Too Many Requests")
            return inner(url)
        n = news.backfill(self.db, flaky, now=NOW, sleep=waits.append)
        self.assertEqual(n["listing"], 6)                                     # page 2 came through after waiting
        self.assertIn(60, waits)
        always = lambda url: (_ for _ in ()).throw(OSError("429")) if "catalogId=161" in url else inner(url)  # noqa
        n = news.backfill(self.db, always, now=NOW, sleep=lambda s: None)
        self.assertEqual(n["delisting_stopped_at_page"], 1)                   # recorded, not raised
        self.assertGreater(self.db.one("SELECT COUNT(*) FROM observations WHERE metric='news_error'")[0], 0)

    def test_nothing_formal_is_written(self):
        news.run(self.db, self.get(), now=NOW)
        for t in ("results", "trials", "transitions", "alpha_ledger", "sim_fills"):
            if self.db.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", t):
                self.assertEqual(self.db.one(f"SELECT COUNT(*) FROM {t}")[0], 0, t)

    def test_an_oversized_feed_is_refused(self):
        class R:
            def __init__(self, n):
                self.n = n

            def read(self, k):
                return b"x" * min(self.n, k)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        from unittest import mock
        with mock.patch.object(news.urllib.request, "urlopen", lambda req, timeout=30: R(news.MAX_BYTES + 10)):
            with self.assertRaises(ValueError):
                news.http_get("https://cointelegraph.com/rss")


if __name__ == "__main__":
    unittest.main()
