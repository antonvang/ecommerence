"""Event farm historical lab (research/tools/event_farm_hist.py, PROTOCOL_V3 amendment 47): file names only from the
verify file, sha256 before opening, rows outside the month discarded, DEV never sees CHECK bars, CHECK logged before
computing, DEV trials logged. Synthetic zips in a temp dir only; no network, no market file."""
import hashlib
import io
import json
import os
import random
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from research.tools import event_farm_hist as eh  # noqa: E402

MONTHS = [f"2020-{m:02d}" for m in range(3, 13)] + [f"2021-{m:02d}" for m in range(1, 13)]


def month_rows(name, rng, px, minutes=None, extra=()):
    lo, hi = eh.month_bounds(name)
    rows = []
    for t in range(lo, hi, 60)[:minutes]:
        o = px
        px *= 1 + rng.gauss(0, 0.0008)
        rows.append([t * 1000, o, max(o, px) * 1.0002, min(o, px) * 0.9998, px, rng.randint(1, 50), t * 1000 + 59999])
    rows += [list(r) for r in extra]
    return rows, px


def write_zip(path, rows):
    buf = io.StringIO()
    for r in rows:
        buf.write(",".join(str(x) for x in r) + "\n")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(os.path.basename(path)[:-4] + ".csv", buf.getvalue())


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Hist(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.cache = os.path.join(cls.d, "klines_1m")
        os.makedirs(cls.cache)
        rng = random.Random(7)
        files = []
        for s, px in (("BTCUSDT", 9000.0), ("ETHUSDT", 230.0)):
            for m in MONTHS:
                name = f"{s}-1m-{m}.zip"
                # 4 days per month keep the test fast; one stray row from the next month is discarded
                rows, px = month_rows(name, rng, px, minutes=4 * 1440,
                                      extra=[[eh.month_bounds(name)[1] * 1000, 1, 1, 1, 1, 1, 0]])
                p = os.path.join(cls.cache, name)
                write_zip(p, rows)
                files.append({"file": name, "ok": True, "sha256": sha(p)})
        # a 2024 file sits in the cache and must never be opened (not in the verify file)
        with open(os.path.join(cls.cache, "BTCUSDT-1m-2024-01.zip"), "wb") as f:
            f.write(b"not a zip")
        cls.verify = os.path.join(cls.d, "verify.json")
        with open(cls.verify, "w") as f:
            json.dump({"files": files, "ok": True}, f)
        cls.logs = os.path.join(cls.d, "logs")
        cls.bars, cls.info = eh.load_bars(cls.cache, cls.verify, work=None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d)

    def test_identity_and_month_filter(self):
        self.assertEqual(self.info["files"], 44)
        self.assertEqual(self.info["rows_discarded"], 44)
        for s in eh.SYMBOLS:
            ts = [b[0] for b in self.bars[s]]
            self.assertEqual(len(ts), 22 * 4 * 288)
            self.assertTrue(all(eh.EXPLORE_START <= t < eh.EXPLORE_END for t in ts))

    def test_sha_mismatch_refused_before_parsing(self):
        bad = os.path.join(self.d, "bad_verify.json")
        v = json.load(open(self.verify))
        v["files"][3]["sha256"] = "0" * 64
        json.dump(v, open(bad, "w"))
        with self.assertRaises(eh.Refused):
            eh.load_bars(self.cache, bad, work=None)

    def test_names_outside_explore0_refused(self):
        for name in ("BTCUSDT-1m-2024-01.zip", "BTCUSDT-1m-2025-03.zip", "BTCUSDT-1m-2022-01.zip", "SOLUSDT-1m-2021-01.zip",
                     "BTCUSDT-1m-2020-02.zip"):
            self.assertIsNone(eh.NAME.match(name), name)
        bad = os.path.join(self.d, "bad_names.json")
        v = json.load(open(self.verify))
        v["files"][0]["file"] = "BTCUSDT-1m-2024-01.zip"
        json.dump(v, open(bad, "w"))
        with self.assertRaises(eh.Refused):
            eh.identity(self.cache, bad)

    def test_dev_never_sees_check_bars(self):
        dev, frm = eh.part_bars(self.bars["BTCUSDT"], "dev")
        self.assertTrue(all(b[0] + eh.BS <= eh.DEV_END for b in dev))
        chk, frm_c = eh.part_bars(self.bars["BTCUSDT"], "check")
        self.assertEqual(frm_c, eh.DEV_END)
        self.assertTrue(chk[0][0] < eh.DEV_END <= chk[-1][0])
        v = ("fvg/rr2/market",)
        a = eh.run({"BTCUSDT": dev}, variants=v, combos=("base",), count_from=frm)
        tampered = [b if b[0] < eh.DEV_END else (b[0], b[1] * 3, b[2] * 3, b[3] * 3, b[4] * 3, b[5]) for b in self.bars["BTCUSDT"]]
        b = eh.run({"BTCUSDT": eh.part_bars(tampered, "dev")[0]}, variants=v, combos=("base",), count_from=frm)
        self.assertEqual(a, b)
        c = eh.run({"BTCUSDT": chk}, variants=v, combos=("base",), count_from=frm_c)
        self.assertGreaterEqual(c["days"], 1)

    def test_cli_dev_logs_trial_and_check_logs_before(self):
        common = ["--cache", self.cache, "--verify", self.verify, "--log-dir", self.logs, "--work", "",
                  "--variants", "fvg/rr2/market", "--no-null"]
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            self.assertEqual(eh.main(common + ["--set", "rr=3", "--combos", "base,F1"]), 0)
        self.assertIn("UDVIKLING", out.getvalue())
        self.assertIn("| F1/fvg/rr2/market |", out.getvalue())
        trials = [json.loads(x) for x in open(os.path.join(self.logs, "dev_trials.jsonl"))]
        self.assertEqual(trials[-1]["tests"], 2)
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            eh.main(common + ["--check"])
        self.assertFalse(os.path.exists(os.path.join(self.logs, "check_openings.jsonl")))
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            eh.main(common + ["--check", "--reason", "test"])
        self.assertIn("KONTROL", out.getvalue())
        opens = [json.loads(x) for x in open(os.path.join(self.logs, "check_openings.jsonl"))]
        self.assertEqual(opens[-1]["reason"], "test")
        self.assertEqual(len([json.loads(x) for x in open(os.path.join(self.logs, "dev_trials.jsonl"))]), len(trials))

    def test_unknown_parameter_refused(self):
        with self.assertRaises(SystemExit):
            eh.parse_set(["nope=1"])
        self.assertEqual(eh.parse_set(["rr=2.5", "chain_breaks=[\"mss\",\"bos\"]"]),
                         {"rr": 2.5, "chain_breaks": ("mss", "bos")})


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401
    unittest.main()
