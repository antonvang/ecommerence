import datetime as dt
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))
import m27_audit as m  # noqa: E402
from lab import sessions  # noqa: E402

COLS = ["markPrice", "indexPrice", "lastFundingRate", "lastPrice", "openPrice", "highPrice", "lowPrice", "quoteVolume",
        "count"]


def db_with(rows):
    tmp = tempfile.mkdtemp(prefix="m27")
    path = os.path.join(tmp, "lab.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, ts, detector, source, instrument, metric, value, "
                "threshold, flagged, payload)")
    for r in rows:
        con.execute("INSERT INTO observations (ts, detector, instrument, metric, value, flagged, payload) "
                    "VALUES (?,?,?,?,?,?,?)", r)
    con.commit()
    con.close()
    return tmp, path


def snap(ts, prices):
    return (ts, "census/1", None, "snapshot", len(prices), 0,
            json.dumps({"columns": COLS, "premium_fetched_at": ts,
                        "rows": {s: [p, i] + [None] * 7 for s, (p, i) in prices.items()}}))


class Census(unittest.TestCase):
    def test_census_honours_the_lock_and_signals_use_mark_before_open_against_index_at_prior_x(self):
        d0, d1 = dt.date(2026, 10, 28), dt.date(2026, 10, 29)
        x0 = dt.datetime.combine(d0, dt.time(14, 0), sessions.ET).timestamp()      # >= 60 min before the 16:00 close
        p1 = dt.datetime.combine(d1, dt.time(9, 0), sessions.ET).timestamp()       # last snapshot before the 09:30 open
        late = m.LOCK_34 + 3600
        tmp, path = db_with([snap(x0, {"AAA": (100.0, 100.0)}), snap(p1, {"AAA": (110.0, 999.0)}),
                             snap(late, {"AAA": (1.0, 1.0)})])
        self.addCleanup(shutil.rmtree, tmp, True)
        snaps = m.census(m.ro(path), before=m.LOCK_34)
        self.assertEqual(len(snaps), 2)                                          # the post-lock hour is never read
        s = m.signals(snaps, ["AAA"])
        self.assertAlmostEqual(s[str(d1)]["AAA"], 0.09531, places=4)            # ln(110 / 100): mark at P, index at X

    def test_dependence_sees_a_common_factor(self):
        rets = {h: {f"S{i}": (0.01 if h % 2 else -0.01) + 0.0001 * i for i in range(60)} for h in range(12)}
        out = m.dependence(rets, [f"S{i}" for i in range(60)])
        self.assertGreater(out["mean_pair_corr"], 0.9)
        self.assertGreater(out["mean_r2_on_market"], 0.9)


class Costs(unittest.TestCase):
    def test_off_hours_ratio_in_both_halves(self):
        rows = []
        for k in range(40):
            t = 1793000000 + k * 3600
            off = k % 2 == 0
            rows.append((t, "abnormal_move/1", "X", "book_rt", 0.0002 if off else 0.0001, 0,
                         json.dumps({"off_hours": off, "open_s": t})))
        tmp, path = db_with(rows)
        self.addCleanup(shutil.rmtree, tmp, True)
        out = m.costs(m.ro(path))["off_hours_vs_open"]["by_market"]["X"]
        self.assertEqual(out["ratio"], [2.0, 2.0])
        self.assertTrue(out["same_direction"])


class Flags(unittest.TestCase):
    def test_rows_after_a_recovery_are_counted_apart(self):
        rec = 1793000000
        tmp, path = db_with([(rec + 600, "abnormal_move/1", "X", "z_1h", 5, 1, "{}"),
                             (rec + 99999, "abnormal_move/1", "X", "z_1h", 0, 0, "{}")])
        self.addCleanup(shutil.rmtree, tmp, True)
        log = os.path.join(tmp, "watch.log")
        with open(log, "w") as f:
            f.write(dt.datetime.fromtimestamp(rec, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                    + "+00:00 Copybot: scanner virker igen: x\n")
        out = m.flags(m.ro(path), log)
        self.assertEqual((out["after_gap"]["flagged"], out["other"]["flagged"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
