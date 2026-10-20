"""Amendment 14: free data sources fetched one unit at a time (network replaced by a fake server)."""
import gzip
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, ingest, jobs, pipeline  # noqa: E402
from lab.db import DB  # noqa: E402

AGG = ingest.BINANCE + "/monthly/aggTrades/BNBUSDT/BNBUSDT-aggTrades-2023-03.zip"
H = 1677628800                                    # 2023-03-01 00:00 UTC


def zipped(name, text):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, text)
    return b.getvalue()


class Resp(io.BytesIO):
    def __init__(self, data, length=True):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if length else {}


class Fake:
    """url -> bytes; a missing url is a 404. Records every url asked for."""
    def __init__(self, files, length=True):
        self.files, self.asked, self.length = dict(files), [], length

    def __call__(self, url, timeout=120):
        self.asked.append(url)
        if url not in self.files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return Resp(self.files[url], self.length)

    def add(self, url, data, checksum=True, bad=False):
        self.files[url] = data
        if checksum:
            sha = hashlib.sha256(data + (b"x" if bad else b"")).hexdigest()
            self.files[url + ".CHECKSUM"] = f"{sha}  {os.path.basename(url)}\n".encode()


TRADES = ("agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
          f"1,10,50,1,1,{H * 1000 + 5},false\n"          # taker bought 500 USD (< 1k)
          f"2,10,5000,2,3,{H * 1000 + 9},true\n"         # taker sold 50,000 USD (10k-100k)
          f"3,20,10000,4,4,{(H + 3600) * 1000},false\n")  # next hour: bought 200,000 USD (>= 100k)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "ingest")
        self.db = DB(os.path.join(self.tmp.name, "lab.db"))
        jobs.init(self.db)
        self.free = lambda: 100 * 1024 ** 3

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def run_unit(self, unit, fake, budget=ingest.BUDGET_BYTES, free=None):
        return ingest.run_unit(unit, budget, fake, free or self.free, self.root)


class Summaries(Base):
    def test_trades_by_hand(self):
        fake = Fake({})
        fake.add(AGG, zipped("x.csv", TRADES))
        out = self.run_unit("aggtrades|BNBUSDT|2023-03", fake)
        with gzip.open(out["out"], "rt") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        a, b = rows
        self.assertEqual((int(a["hour_ts"]), int(a["available_ts"]), int(a["trades"])), (H, H + 3600, 2))
        self.assertAlmostEqual(float(a["buy_usd"]), 500)
        self.assertAlmostEqual(float(a["sell_usd"]), 50_000)
        self.assertAlmostEqual(float(a["buy_usd_lt1k"]), 500)
        self.assertAlmostEqual(float(a["sell_usd_10k_100k"]), 50_000)
        self.assertAlmostEqual(float(a["vwap"]), 10)
        self.assertAlmostEqual(float(b["buy_usd_ge100k"]), 200_000)
        self.assertAlmostEqual(float(b["max_trade_usd"]), 200_000)
        self.assertFalse(os.listdir(os.path.join(self.root, ".raw")))          # raw file deleted
        self.assertEqual(out["rows"], 2)

    def test_headerless_file(self):
        fake = Fake({})
        fake.add(AGG, zipped("x.csv", TRADES.split("\n", 1)[1]))
        self.assertEqual(self.run_unit("aggtrades|BNBUSDT|2023-03", fake)["rows"], 2)

    def test_depth_by_hand_and_missing_days(self):
        fake = Fake({})
        url = ingest.BINANCE + "/daily/bookDepth/BNBUSDT/BNBUSDT-bookDepth-2023-02-01.zip"
        fake.add(url, zipped("d.csv", "timestamp,percentage,depth,notional\n"
                                      "2023-02-01 00:00:10,-1,1,100\n2023-02-01 00:00:40,-1,1,300\n"
                                      "2023-02-01 00:00:40,1,1,50\n2023-02-01 01:10:00,-1,1,7\n"))
        out = self.run_unit("bookdepth|BNBUSDT|2023-02", fake)
        self.assertEqual((out["files"], len(out["missing_days"])), (1, 27))
        with gzip.open(out["out"], "rt") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(int(rows[0]["snapshots"]), 2)
        self.assertAlmostEqual(float(rows[0]["mean_usd_-1"]), 200)
        self.assertAlmostEqual(float(rows[0]["min_usd_-1"]), 100)
        self.assertAlmostEqual(float(rows[0]["mean_usd_+1"]), 50)
        self.assertEqual(rows[0]["mean_usd_+5"], "")
        self.assertAlmostEqual(float(rows[1]["mean_usd_-1"]), 7)

    def test_pageviews_point_in_time(self):
        url = ingest.WIKI + "/Bitcoin/daily/20200101/20231231"
        fake = Fake({url: json.dumps({"items": [{"timestamp": "2020010100", "views": 5},
                                                {"timestamp": "2020010200", "views": 7}]}).encode()})
        out = self.run_unit("pageviews|Bitcoin", fake)
        with open(out["out"]) as f:
            rows = json.load(f)["rows"]
        self.assertEqual(rows[0], {"date": "2020-01-01", "views": 5, "available_ts": 1577836800 + 2 * 86400})
        self.assertEqual((out["first"], out["last"]), ("2020-01-01", "2020-01-02"))


FOMC_CUR = ("<h4>2022 FOMC Meetings</h4>"
            '<div class="fomc-meeting__month"><strong>January</strong></div><div class="fomc-meeting__date">25-26</div>'
            '<div class="fomc-meeting__month"><strong>Jan/Feb</strong></div><div class="fomc-meeting__date">31-1*</div>'
            "<h4>2021 FOMC Meetings</h4>"
            '<div class="fomc-meeting__month"><strong>March</strong></div><div class="fomc-meeting__date">16-17*</div>')
FOMC_2020 = ('<h5 class="x">January 28-29 Meeting - 2020</h5><h5 class="x">March 15 (unscheduled) Meeting - 2020</h5>'
             '<h5 class="x">March 17-18 (cancelled) Meeting - 2020</h5><h5 class="x">March 23 (notation vote) - 2020</h5>')
BLS_HTML = ('<td class="date-cell"><p>Wednesday, March 10, 2021</p></td>\n<td class="time-cell"><p>08:30 AM</p></td>\n'
            '<td class="desc-cell"><p><strong>Consumer Price Index</strong> for February 2021</p></td>'
            '<td class="date-cell"><p>Friday, March 5, 2021</p></td>\n<td class="time-cell"><p>10:00 AM</p></td>\n'
            '<td class="desc-cell"><p><strong>Productivity and Costs</strong> for x</p></td>')


class Calendars(Base):
    def test_fomc_current_page(self):
        ev = ingest.parse_fomc(FOMC_CUR, 2022)
        self.assertEqual([e["date"] for e in ev], ["2022-01-26", "2022-02-01"])
        self.assertEqual(ev[0]["ts"], 1643223600)                     # 14:00 EST = 19:00 UTC
        self.assertTrue(ev[1]["sep"])
        self.assertEqual(ingest.parse_fomc(FOMC_CUR, 2021)[0]["ts"], 1616004000)   # 14:00 EDT = 18:00 UTC

    def test_fomc_2020_page(self):
        ev = {e["date"]: e for e in ingest.parse_fomc(FOMC_2020, 2020)}
        self.assertTrue(ev["2020-01-29"]["scheduled"])
        self.assertEqual((ev["2020-03-15"]["kind"], ev["2020-03-15"]["ts"]), ("unscheduled", None))
        self.assertEqual(ev["2020-03-18"]["kind"], "cancelled")
        self.assertEqual(ev["2020-03-23"]["kind"], "notation vote")

    def test_bls(self):
        ev = ingest.parse_bls(BLS_HTML, 2021)
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["event"], ev[0]["date"], ev[0]["ts"]), ("Consumer Price Index", "2021-03-10",
                                                                        1615383000))   # 08:30 EST = 13:30 UTC

    def test_unparsable_page_is_refused(self):
        fake = Fake({ingest.BLS.format(year=2021): b"<html>new layout</html>"})
        with self.assertRaises(ingest.Refused):
            self.run_unit("bls|2021", fake)


class Guards(Base):
    def test_nothing_after_2023(self):
        for unit in ("aggtrades|BNBUSDT|2024-01", "bookdepth|BNBUSDT|2025-03", "bls|2024", "fomc|2025", "x|y"):
            with self.assertRaises(ingest.Refused, msg=unit):
                self.run_unit(unit, Fake({}))
        self.assertTrue(all(u.split("|")[-1][:4] <= "2023" for u in ingest.plan() if u[0] in "abf"))
        for u in ingest.plan():
            ingest.guard(u)                                               # the whole plan is allowed

    def test_checksum_mismatch_refused_and_removed(self):
        fake = Fake({})
        fake.add(AGG, zipped("x.csv", TRADES), bad=True)
        with self.assertRaises(ingest.Refused):
            self.run_unit("aggtrades|BNBUSDT|2023-03", fake)
        self.assertFalse(os.listdir(os.path.join(self.root, ".raw")))

    def test_budget(self):
        data = zipped("x.csv", TRADES)
        for length in (True, False):                                      # with and without Content-Length
            fake = Fake({}, length=length)
            fake.add(AGG, data)
            with self.assertRaises(ingest.Refused):
                self.run_unit("aggtrades|BNBUSDT|2023-03", fake, budget=len(data) - 1)
            self.assertFalse([f for f in os.listdir(os.path.join(self.root, ".raw"))])

    def test_disk_margin(self):
        fake = Fake({})
        fake.add(AGG, zipped("x.csv", TRADES))
        with self.assertRaises(ingest.Refused):
            self.run_unit("aggtrades|BNBUSDT|2023-03", fake, free=lambda: ingest.MARGIN)

    def test_missing_file_is_not_an_error(self):
        out = self.run_unit("aggtrades|BNBUSDT|2023-03", Fake({}))
        self.assertEqual((out["bytes"], out["missing"]), (0, [AGG]))


class Queue(Base):
    def step(self, fake, worker="data-1"):
        job = jobs.claim(self.db, worker, ("ingest",))
        try:
            res = ingest.step_ingest(self.db, job, worker, fake, self.free, self.root)
        except pipeline.StepError as e:
            jobs.fail(self.db, job["job_id"], worker, repr(e), retryable=False)
            return None
        jobs.complete(self.db, job["job_id"], worker, res)
        return res

    def test_one_at_a_time_in_plan_order_and_done_once(self):
        self.assertEqual(ingest.enqueue(self.db), 1)
        self.assertEqual(ingest.enqueue(self.db), 0)                   # one job at a time
        first = ingest.plan()[0]
        self.assertEqual(self.db.one("SELECT payload FROM jobs WHERE kind='ingest'")["payload"],
                         json.dumps({"unit": first}))
        html = FOMC_2020.encode()
        res = self.step(Fake({ingest.FOMC_HIST.format(year=2020): html}))
        self.assertEqual(res["rows"], 4)
        ev = json.loads(self.db.one("SELECT payload FROM events WHERE kind='ingest.done'")["payload"])
        self.assertEqual((ev["unit"], ev["bytes"], ev["decisional"]), (first, len(FOMC_2020), False))
        self.assertTrue(ev["out"].startswith("ingest/calendar/"))
        self.assertEqual(ingest.enqueue(self.db), 1)                   # the next unit
        self.assertEqual(json.loads(self.db.one("SELECT payload FROM jobs WHERE status='queued'")["payload"])["unit"],
                         ingest.plan()[1])
        self.assertEqual(ingest.status(self.db)["done"], 1)

    def test_leftovers_of_an_interrupted_unit_are_removed(self):
        raw = os.path.join(self.root, ".raw")
        os.makedirs(raw)
        for name in ("BNBUSDT-bookDepth-2023-01-01.zip", "x.zip.123.part"):
            open(os.path.join(raw, name), "wb").close()
        ingest.enqueue(self.db)
        self.step(Fake({ingest.FOMC_HIST.format(year=2020): FOMC_2020.encode()}))
        self.assertEqual(os.listdir(raw), [])

    def test_refused_unit_is_recorded_and_skipped(self):
        ingest.enqueue(self.db)
        self.assertIsNone(self.step(Fake({ingest.FOMC_HIST.format(year=2020): b"nothing"})))
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='ingest.refused'")[0], 1)
        st = ingest.status(self.db)
        self.assertEqual((st["failed"], len(st["refused"])), ([ingest.plan()[0]], 1))
        self.assertEqual(ingest.enqueue(self.db), 1)                   # moves on to the next unit

    def test_budget_spent_stops_queueing(self):
        self.db.event("ingest.done", "system:data-1", None, {"unit": "x", "bytes": ingest.BUDGET_BYTES})
        self.assertEqual(ingest.enqueue(self.db), 0)
        self.assertEqual(ingest.status(self.db)["budget_left_bytes"], 0)

    def test_a_test_database_never_queues_ingestion(self):
        self.assertFalse(ingest.auto(self.db))
        self.assertEqual(fleet.strategy_pass(self.db)["ingest_queued"], 0)
        self.assertIsNone(self.db.one("SELECT 1 FROM jobs WHERE kind='ingest'"))

    def test_wired_to_the_data_agent(self):
        kinds = {name: k for name, _r, k, *_ in fleet.ROSTER}
        self.assertIn("ingest", kinds["data-1"])
        self.assertIn("ingest", pipeline.HANDLERS)


if __name__ == "__main__":
    unittest.main()
