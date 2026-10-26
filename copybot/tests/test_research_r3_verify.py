"""Amendment 24a point 4: r3_verify passes 44 good files, and fails a sha256 that differs from the log, a broken zip, a
bar outside its month and a missing file that was never recorded absent; a recorded 404 passes as absent."""
import calendar
import io
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "research", "tools"))

from lab import r3  # noqa: E402
from lab.engine import data  # noqa: E402
import r3_verify as v  # noqa: E402


def month_zip(y, m, shift=0):
    a = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp())
    n = calendar.monthrange(y, m)[1] * 1440
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("x.csv", "".join(f"{(a + k * 60 + shift) * 1000},1,1,1,1,1\n" for k in range(n)))
    return buf.getvalue()


class Verify(unittest.TestCase):
    def setUp(self):
        self.old, self.tmp = data.CACHE, tempfile.mkdtemp(prefix="r3v")
        data.CACHE = self.tmp

    def tearDown(self):
        data.CACHE = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fetch(self, get):
        return r3.fetch(now=r3.FETCH_FROM, get=get)

    @staticmethod
    def get_month(u):
        y, m = u.rsplit("-1m-", 1)[1][:7].split("-")
        return month_zip(int(y), int(m))

    def test_44_good_files_pass(self):
        self.fetch(self.get_month)
        res = v.verify()
        self.assertTrue(res["ok"], [f for f in res["files"] if not f["ok"]][:2])
        self.assertEqual((res["expected"], res["present"], res["absent"]), (44, 44, 0))
        self.assertTrue(all(f["missing_minutes"] == 0 and f["outside_month"] == 0 for f in res["files"]))

    def test_tampered_broken_outside_and_unrecorded_missing_fail(self):
        self.fetch(self.get_month)
        with open(r3.path("BTCUSDT", 2020, 3), "wb") as f:              # differs from the logged sha256
            f.write(month_zip(2020, 3, shift=60))
        with open(r3.path("BTCUSDT", 2020, 4), "wb") as f:
            f.write(b"PK\x03\x04 not a zip")
        os.remove(r3.path("ETHUSDT", 2021, 12))                           # never recorded absent
        res = v.verify()
        bad = {f["file"]: f["why"] for f in res["files"] if not f["ok"]}
        self.assertFalse(res["ok"])
        self.assertIn("sha256 differs from the log", bad["BTCUSDT-1m-2020-03.zip"])
        self.assertIn("bad zip", bad["BTCUSDT-1m-2020-04.zip"])
        self.assertEqual(bad["ETHUSDT-1m-2021-12.zip"], "missing and not recorded absent")
        self.assertEqual(len(bad), 3)

    def test_bar_outside_the_month_fails_and_a_recorded_404_passes(self):
        def get(u):
            if u.endswith("ETHUSDT-1m-2020-03.zip"):
                raise urllib.error.HTTPError(u, 404, "nf", None, None)
            if u.endswith("BTCUSDT-1m-2021-01.zip"):
                return month_zip(2020, 12)                                 # December bars in the January file
            return self.get_month(u)
        self.fetch(get)
        res = v.verify()
        bad = {f["file"]: f["why"] for f in res["files"] if not f["ok"]}
        self.assertEqual(bad, {"BTCUSDT-1m-2021-01.zip": "bars outside the month"})
        self.assertEqual(res["absent"], 1)


if __name__ == "__main__":
    unittest.main()
