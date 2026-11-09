"""Amendment 37: point-in-time shrunk BTC betas from prior RTH hours, residual signal and outcome, 4v4 long-short with
at least 6 names, Student t on the first 40 valid days, counts without values before the run."""
import datetime as dt
import io
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))
import m37_cryptoeq as m  # noqa: E402
from lab import sessions  # noqa: E402

COLS = ["markPrice", "indexPrice"]


def et(d, h, mi=1):
    return int(dt.datetime.combine(d, dt.time(h, mi), sessions.ET).timestamp())


def db_with(snaps):
    tmp = tempfile.mkdtemp(prefix="m37")
    path = os.path.join(tmp, "lab.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts, detector, metric, payload)")
    for t, rows in snaps:
        con.execute("INSERT INTO observations (ts, detector, metric, payload) VALUES (?,?,?,?)",
                    (t, "census/1", "snapshot", json.dumps({"columns": COLS, "premium_fetched_at": t,
                                                            "rows": {s: list(v) for s, v in rows.items()}})))
    con.commit()
    con.close()
    return tmp, path


class Betas(unittest.TestCase):
    def test_shrunk_ols_from_the_prior_15_trading_days_only(self):
        d = dt.date(2026, 11, 20)
        prior = list(m.base.trading_days(dt.date(2026, 11, 1), d - dt.timedelta(days=1)))
        rets = []
        for i, day in enumerate(prior):
            for k in range(3):
                x = 0.001 * ((i + k) % 5 - 2)
                rets.append((day, {m.BTC: x, "COINUSDT": 2 * x, "HOODUSDT": x}))
        rets.append((d, {m.BTC: 0.05, "COINUSDT": -1.0}))                  # the day itself is never used
        b = m.betas(rets, d)
        self.assertAlmostEqual(b["COINUSDT"], 1.5)
        self.assertAlmostEqual(b["HOODUSDT"], 1.0)
        self.assertNotIn("MSTRUSDT", b)

    def test_under_20_hours_leaves_the_name_out(self):
        d = dt.date(2026, 11, 20)
        rets = [(dt.date(2026, 11, 19), {m.BTC: 0.001 * k, "COINUSDT": 0.002 * k}) for k in range(19)]
        self.assertEqual(m.betas(rets, d), {})


class Returns(unittest.TestCase):
    def test_only_rth_pairs_30_to_90_min_apart(self):
        d = dt.date(2026, 11, 3)
        s = lambda t, p: (t, {m.BTC: {"markPrice": p}, "COINUSDT": {"indexPrice": p}})   # noqa: E731
        snaps = [s(et(d, 8), 100), s(et(d, 9), 101), s(et(d, 10), 102), s(et(d, 11), 103), s(et(d, 14), 104)]
        got = m.rth_returns(snaps)
        self.assertEqual(len(got), 1)                                      # 10 -> 11 only (9 -> 10 starts pre-open)
        self.assertAlmostEqual(got[0][1]["COINUSDT"], math.log(103 / 102))


class Signals(unittest.TestCase):
    def test_raw_star_and_long_short(self):
        xp = {m.BTC: {"markPrice": 100.0}, "COINUSDT": {"indexPrice": 50.0}}
        P = {m.BTC: {"markPrice": 110.0}, "COINUSDT": {"markPrice": 60.0}}
        E = {m.BTC: {"markPrice": 100.0}, "COINUSDT": {"indexPrice": 60.0}}
        X = {m.BTC: {"markPrice": 90.0}, "COINUSDT": {"indexPrice": 57.0}}
        rw, btc = m.raw((None, None, (0, xp)), ((0, P), (0, E), (0, X)))
        st = m.star(rw, btc, {"COINUSDT": 1.5})
        self.assertAlmostEqual(st["COINUSDT"][0], math.log(1.2) - 1.5 * math.log(1.1))
        self.assertAlmostEqual(st["COINUSDT"][1], math.log(0.95) - 1.5 * math.log(0.9))
        self.assertIsNone(m.ls_half([(1, 1)] * 5))
        self.assertGreater(m.ls_half([(i, -i) for i in range(8)]), 0)    # reversal is positive


class Judge(unittest.TestCase):
    def rows(self, vals):
        return [(dt.date(2026, 11, 2) + dt.timedelta(days=i), v) for i, v in enumerate(vals)]

    def test_untestable_below_40_and_the_floor(self):
        self.assertEqual(m.judge(self.rows([0.02] * 39), [])["verdict"], "UNTESTABLE")
        noise = self.rows([0.01 * (-1) ** i for i in range(40)])
        strong = self.rows([0.012 + 0.002 * (i % 5 - 2) for i in range(40)])
        weak = self.rows([0.005 + 0.002 * (i % 5 - 2) for i in range(40)])   # significant but under 0.75 %
        self.assertEqual(m.judge(strong, noise)["verdict"], "PASS")
        self.assertEqual(m.judge(weak, noise)["verdict"], "SCREEN_FAIL")
        self.assertEqual(m.judge(strong, strong)["verdict"], "SCREEN_FAIL")

    def test_run_uses_the_first_40_valid_days(self):
        beta = {s: 1.0 for s in m.NAMES}
        rw = {s: (0.01 * i, -0.01 * i) for i, s in enumerate(m.NAMES)}
        rows = [(dt.date(2026, 11, 2) + dt.timedelta(days=i), rw, (0.0, 0.0), None, None, beta) for i in range(45)]
        self.assertEqual(m.run(rows)["days"], 40)


class EndToEnd(unittest.TestCase):
    def test_count_reports_days_and_names_only(self):
        snaps = []
        for d in m.base.trading_days(dt.date(2026, 10, 27), dt.date(2026, 11, 4)):
            for h in range(8, 17):
                k = len(snaps)
                rows = {m.BTC: (100 + (k % 3), 100.0)}
                for i, s in enumerate(m.NAMES):
                    rows[s] = (50 + i + (k * (i + 1)) % 4, 50 + i + (k * (i + 2)) % 3)
                snaps.append((et(d, h), rows))
        tmp, path = db_with(snaps)
        self.addCleanup(shutil.rmtree, tmp, True)
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        out = m.count(db, et(dt.date(2026, 11, 5), 0))
        self.assertEqual(out["valid_days"], 3)                              # 11-02, 11-03, 11-04
        self.assertEqual({r["names"] for r in out["days"]}, {8})
        self.assertNotIn(".", json.dumps(out).replace("amendment 37 point 13: counts only", ""))

    def test_run_refuses_below_40(self):
        with mock.patch.object(m, "count", return_value={"valid_days": 3}), mock.patch.object(m, "run") as r:
            buf = io.StringIO()
            with redirect_stdout(buf):
                m.main(["run", "--db", ":memory:"])
        r.assert_not_called()
        self.assertIn("refused", json.loads(buf.getvalue()))


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
