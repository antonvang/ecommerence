"""PROTOCOL_V3 amendment 30: the EU-tradable label is built outside lab/ from the register and public market lists
(only entities with service b or e, no end date and Denmark), lab/ only reads the static file, nothing that decides
reads it, and the per-coin cost report counts fills, closed lane round trips with funding, and never lane results
for FWD accounts."""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "research", "tools"))

import coin_costs  # noqa: E402
import eu_venue_markets as evm  # noqa: E402
from lab import venue  # noqa: E402

HEAD = ("ae_competentAuthority,ae_homeMemberState,ae_lei_name,ae_lei,ae_lei_cou_code,ae_commercial_name,ae_address,"
        "ae_website,ae_website_platform,ac_authorisationNotificationDate,ac_authorisationEndDate,ac_serviceCode,"
        "ac_serviceCode_cou,ac_comments,ac_lastupdate,ac_legal_basis\n")


def reg_row(name, codes, cou="AT | DK | SE", end=""):
    svc = " | ".join(f"{c}. x" for c in codes)
    return f'X,AT,{name},LEI{len(name)},AT,{name},addr,w,,01/01/2025,{end},{svc},{cou},,01/01/2025,Art 63\n'


class Build(unittest.TestCase):
    def test_only_b_or_e_with_denmark_and_no_end_date_qualify_and_sources_are_hashed(self):
        csv_ = (HEAD + reg_row("Payward Europe Solutions Limited", "acde") + reg_row("Bitstamp Europe S.A.", "acd")
                + reg_row("OKX Europe Limited", "ab", cou="AT|SE") + reg_row("Bitvavo B.V.", "ab", end="01/09/2026")
                + reg_row("Coinbase Luxembourg S.A.", "ae")).encode("utf-8-sig")
        lists = {"kraken": {"result": {"XXBTZUSD": {"wsname": "XBT/USD"}, "X": {"wsname": "VET/EUR"},
                                       "Y": {"wsname": "FOO/GBP"}}},
                 "exchange.coinbase": [{"base_currency": "BTC", "quote_currency": "USDT", "status": "online"},
                                       {"base_currency": "OFF", "quote_currency": "USD", "status": "delisted"}]}

        def get(url):
            if url == evm.REGISTER:
                return csv_, "Thu, 22 Oct 2026 15:14:35 GMT"
            for k, v in lists.items():
                if k in url:
                    return json.dumps(v).encode(), None
            raise AssertionError(f"unexpected fetch {url}")
        out = evm.build(get=get, now=lambda: 1793110000)
        v = out["venues"]
        self.assertEqual({k for k, x in v.items() if x.get("qualifies")}, {"Kraken", "Coinbase"})
        self.assertEqual(v["Kraken"]["coins"], {"BTC": ["USD"], "VET": ["EUR"]})       # XBT -> BTC; GBP left out
        self.assertEqual(v["Coinbase"]["coins"], {"BTC": ["USDT"]})                    # a delisted product left out
        self.assertFalse(v["OKX"]["qualifies"])                                         # no Denmark
        self.assertFalse(v["Bitvavo"]["qualifies"])                                     # an end date
        self.assertFalse(v["Bitstamp"]["qualifies"])                                    # neither b nor e
        self.assertNotIn("coins", v["OKX"])                                             # not fetched at all
        self.assertTrue(all(x["api_entity"] == "uafklaret" for x in v.values()))
        self.assertEqual(len(out["register"]["sha256"]), 64)
        self.assertEqual(len(v["Kraken"]["sha256"]), 64)
        self.assertFalse(out["register"]["binance_listed"])


class Label(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="venue")
        self.path = os.path.join(self.tmp, "v.json")
        with open(self.path, "w") as fh:
            json.dump({"generated_at": 1, "register": {"sha256": "r" * 64}, "venues": {
                "Kraken": {"qualifies": True, "coins": {"BTC": ["USD"], "VET": ["EUR"]}},
                "Bitvavo": {"qualifies": True, "coins": {"EPIC": ["EUR"], "BTC": ["EUR"]}},
                "OKX": {"qualifies": False}}}, fh)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_label_per_coin(self):
        self.assertEqual(venue.eu_venues("BTCUSDT", self.path), ["Bitvavo", "Kraken"])
        self.assertEqual(venue.eu_venues("EPICUSDT.SPOT", self.path), ["Bitvavo"])
        self.assertEqual(venue.eu_venues("MITOUSDT", self.path), [])
        self.assertIsNone(venue.eu_venues("BTCUSDT", os.path.join(self.tmp, "missing.json")))
        lab = venue.label(["VETUSDT"], self.path)
        self.assertEqual(lab["coins"], {"VETUSDT": ["Kraken"]})
        self.assertIn("uafklaret", lab["note"])

    def test_candidates_are_labelled_only_by_coin_symbols(self):
        self.assertEqual(venue.spec_coins({"instrument": "binance_perps"}), [])
        self.assertEqual(venue.spec_coins({"instruments": ["BTCUSDT", "hyperliquid_binance_perps", "ETHUSDT.SPOT"]}),
                         ["BTCUSDT", "ETHUSDT.SPOT"])

    def test_the_repo_file_exists_and_names_the_register(self):
        with open(venue.PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertEqual(len(d["register"]["sha256"]), 64)
        self.assertFalse(d["register"]["binance_listed"])


class Starts(Label):
    """Amendment 30a: new accounts only on EU-tradable coins; a non-EU coin is dropped before any book is read."""

    def test_eu_block_reasons(self):
        from unittest import mock
        from lab import lane
        with mock.patch.object(venue, "PATH", self.path):
            self.assertIsNone(lane.eu_block("BTCUSDT"))
            self.assertIsNone(lane.eu_block("BTC"))                                   # HL coins are bare
            self.assertEqual(lane.eu_block("MITOUSDT"), "ikke EU-handelbar (30a)")
        with mock.patch.object(venue, "PATH", os.path.join(self.tmp, "gone.json")):
            self.assertEqual(lane.eu_block("BTCUSDT"), "EU-kilde mangler (30a)")

    def test_probe_drops_a_skipped_coin_without_reading_its_book(self):
        from unittest import mock
        from lab import lane, paper_runner
        read = []
        with mock.patch.object(paper_runner, "fetch_book", side_effect=lambda i, n, g: read.append(i) or
                               mock.Mock(crossed=lambda: False)):
            ok, dropped = lane._probe({"coins": ["BTCUSDT", "MITOUSDT"]}, None, None, 0,
                                      skip=lambda c: "ikke EU-handelbar (30a)" if c == "MITOUSDT" else None)
        self.assertEqual(ok, ["BTCUSDT"])
        self.assertEqual(dropped, [{"coin": "MITOUSDT", "reason": "ikke EU-handelbar (30a)"}])
        self.assertNotIn("MITOUSDT", read)
        self.assertNotIn("MITOUSDT.SPOT", read)


class Isolation(unittest.TestCase):
    def test_label_is_information_only(self):
        """Only display code reads it; venue.py fetches nothing."""
        users = []
        for root, _, files in os.walk(os.path.join(HERE, "lab")):
            for f in files:
                if f.endswith(".py") and f != "venue.py":
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        if re.search(r"\bvenue\.(eu_venues|label)\(", fh.read()):
                            users.append(f)
        self.assertEqual(sorted(users), ["command.py", "lane.py", "web.py"])          # display + 30a starts
        with open(os.path.join(HERE, "lab", "venue.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("urllib", src)
        self.assertNotIn("http", src.replace("https://", ""))


class Costs(unittest.TestCase):
    def test_fills_closed_lane_round_trips_with_funding_and_no_fwd_results(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE sim_fills (exp_id, instrument, side, px, qty, fee, slippage, mid)")
        con.execute("CREATE TABLE sim_funding (exp_id, instrument, amount)")
        fills = [("LANE_a", "EPICUSDT.SPOT", "buy", 1.01, 100, 0.1, 0.01, 1.0),
                 ("LANE_a", "EPICUSDT", "sell", 0.99, 100, 0.05, 0.01, 1.0),
                 ("LANE_a", "EPICUSDT.SPOT", "sell", 1.09, 100, 0.1, 0.01, 1.1),
                 ("LANE_a", "EPICUSDT", "buy", 1.11, 100, 0.05, 0.01, 1.1),
                 ("LANE_b", "BTCUSDT.SPOT", "buy", 100.0, 1, 0.1, 0.0, 100.0),          # still open
                 ("FWD_E_x_p1", "BTCUSDT", "buy", 100.02, 1, 0.05, 0.0002, 100.0)]
        con.executemany("INSERT INTO sim_fills VALUES (?,?,?,?,?,?,?,?)", fills)
        con.executemany("INSERT INTO sim_funding VALUES (?,?,?)", [("LANE_a", "EPICUSDT", 0.5),
                                                                    ("LANE_c", "XTZUSDT", 9.0)])   # funding only
        r = coin_costs.costs(con)
        lanes = {x["coin"]: x for x in r["lanes_closed"]}
        self.assertEqual(set(lanes), {"EPIC"})                                  # BTC open; XTZ never traded
        e = lanes["EPIC"]
        self.assertAlmostEqual(e["funding_usd"], 0.5)
        self.assertAlmostEqual(e["costs_usd"], 0.3 + 4 * 1.0, places=6)         # fees + |px-mid| x qty
        self.assertAlmostEqual(e["gross_before_costs_usd"], 0.5, places=6)    # flat at mid + funding
        fwd = [x for x in r["per_coin"] if x["type"] == "FWD"][0]
        self.assertEqual((fwd["coin"], fwd["fills"]), ("BTC", 1))
        self.assertAlmostEqual(fwd["slip_bp_mean"], 2.0, places=6)
        self.assertNotIn("FWD", json.dumps(r["lanes_closed"]))
        con.close()


if __name__ == "__main__":
    unittest.main()
