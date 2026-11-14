"""Funding extremes lab (research/tools/funding_ext_hist.py, amendment 48): manifest names only, sha256 before opening,
signals use only earlier settlements, entry one hour after the settlement, no overlap, DEV/CHECK windows, cost 28 bps.
Synthetic data only; no network, no market file."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from research.tools import event_farm_hist as eh  # noqa: E402
from research.tools import funding_ext_hist as fx  # noqa: E402

MONTHS = [f"2020-{m:02d}" for m in range(2, 13)] + [f"2021-{m:02d}" for m in range(1, 13)]


class Funding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        files = {}
        for s in ("BTCUSDT", "ETHUSDT"):
            for m in MONTHS:
                n = f"{s}-fundingRate-{m}.zip"
                lo, hi = fx.month_bounds(n)
                rows = ["calc_time,funding_interval_hours,last_funding_rate"]
                for k, t in enumerate(range(lo, hi, 8 * 3600)):
                    rows.append(f"{t * 1000 + 7},8,{0.0001 * (1 + (k % 7 == 0) * 5)}")
                rows.append(f"{hi * 1000},8,0.5")                 # next month: discarded
                p = os.path.join(cls.d, n)
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr(n[:-4] + ".csv", "\n".join(rows) + "\n")
                files[n] = {"sha256": eh._sha(p), "size": os.path.getsize(p)}
        cls.man = os.path.join(cls.d, "man.json")
        json.dump({"kind": "POST_HOC_IDENTITY", "files": files, "missing": []}, open(cls.man, "w"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_load_checks_sha_and_month(self):
        fund, dropped = fx.load_funding(self.d, self.man)
        self.assertEqual(dropped, 92)                      # 46 headers + 46 rows of the next month
        self.assertTrue(all(t % 3600 == 0 for t, _ in fund["BTCUSDT"]))
        m = json.load(open(self.man))
        m["files"]["ETHUSDT-fundingRate-2021-05.zip"]["sha256"] = "0" * 64
        bad = os.path.join(self.d, "bad.json")
        json.dump(m, open(bad, "w"))
        with self.assertRaises(eh.Refused):
            fx.load_funding(self.d, bad)
        m = json.load(open(self.man))
        m["files"]["BTCUSDT-fundingRate-2024-01.zip"] = m["files"].pop("BTCUSDT-fundingRate-2021-05.zip")
        json.dump(m, open(bad, "w"))
        with self.assertRaises(eh.Refused):
            fx.funding_names(bad)

    def test_signals_use_only_earlier_settlements(self):
        fund = [(1000 * 8 * 3600 + k * 8 * 3600, 0.0001) for k in range(100)]
        fund[80] = (fund[80][0], 0.01)
        sig = fx.signals(fund, 1.0)
        self.assertEqual(sig, [(fund[80][0], 1)])
        later = list(fund)
        later[90] = (later[90][0], 0.5)                     # a later extreme cannot change the earlier signal
        self.assertEqual(fx.signals(later, 1.0)[0], (fund[80][0], 1))

    def test_trades_entry_one_hour_later_no_overlap_window(self):
        t0 = eh.DEV_END - 200 * 3600
        bars = [(t0 + k * 3600, 100.0 + k, 101.0 + k, 99.0 + k, 100.0 + k, 1.0) for k in range(400)]
        sigs = [(t0 + 10 * 3600, 1), (t0 + 12 * 3600, 1), (t0 + 30 * 3600, -1)]
        tr = fx.trades(bars, sigs, 8, "contra", eh.EXPLORE_START, eh.DEV_END)
        self.assertEqual(len(tr), 2)                        # the second signal falls inside the first trade
        x = tr[0]
        self.assertEqual(x["dir"], -1)
        self.assertAlmostEqual(x["gross_bps"], -((118.0 / 110.0) - 1) * 1e4)
        self.assertAlmostEqual(x["net_bps"], x["gross_bps"] - 28.0)
        late = [(eh.DEV_END - 4 * 3600, 1)]                 # exit would be after DEV_END: not a DEV trade
        self.assertEqual(fx.trades(bars, late, 8, "contra", eh.EXPLORE_START, eh.DEV_END), [])
        self.assertEqual(len(fx.trades(bars, late, 8, "contra", eh.DEV_END - 10 * 3600, eh.EXPLORE_END)), 1)

    def test_maker_fills_only_on_trade_through(self):
        t0 = eh.DEV_END - 200 * 3600
        bars1h = [(t0 + k * 3600, 100.0, 100.5, 99.5, 100.0, 1.0) for k in range(100)]
        bars1h[18] = (bars1h[18][0], 100.0, 101.0, 99.0, 101.0, 1.0)       # exit close for a signal at t0+10h, hold 8
        bars5 = [(t0 + k * 300, 100.0, 100.02, 99.98, 100.0, 1.0) for k in range(1200)]
        sig = [(t0 + 10 * 3600, -1)]                                      # low funding, contra = long
        mk = fx.trades(bars1h, sig, 8, "contra", eh.EXPLORE_START, eh.DEV_END, 5.0, bars5)
        self.assertEqual(len(mk), 1)
        self.assertFalse(mk[0]["filled"])                                 # 99.98 never trades through 99.95
        j = (11 * 3600) // 300 + 3                                        # inside the hour after the reference
        bars5[j] = (bars5[j][0], 100.0, 100.0, 99.95, 100.0, 1.0)         # touch only: still no fill
        self.assertFalse(fx.trades(bars1h, sig, 8, "contra", eh.EXPLORE_START, eh.DEV_END, 5.0, bars5)[0]["filled"])
        bars5[j] = (bars5[j][0], 100.0, 100.0, 99.94, 100.0, 1.0)
        x = fx.trades(bars1h, sig, 8, "contra", eh.EXPLORE_START, eh.DEV_END, 5.0, bars5)[0]
        self.assertTrue(x["filled"])
        self.assertAlmostEqual(x["gross_bps"], (101.0 / 99.95 - 1) * 1e4)
        self.assertAlmostEqual(x["taker_bps"], (101.0 / 100.0 - 1) * 1e4)
        late = (12 * 3600) // 300 + 1                                     # after the 60-minute window: ignored
        bars5[j] = (bars5[j][0], 100.0, 100.02, 99.98, 100.0, 1.0)
        bars5[late] = (bars5[late][0], 100.0, 100.0, 90.0, 100.0, 1.0)
        self.assertFalse(fx.trades(bars1h, sig, 8, "contra", eh.EXPLORE_START, eh.DEV_END, 5.0, bars5)[0]["filled"])
        s = fx.summarize([{**x, "sym": "BTCUSDT"}])
        self.assertAlmostEqual(s["net_grid"]["9"], x["gross_bps"] - 9.0)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401
    unittest.main()
