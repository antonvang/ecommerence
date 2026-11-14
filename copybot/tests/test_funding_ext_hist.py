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


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401
    unittest.main()
