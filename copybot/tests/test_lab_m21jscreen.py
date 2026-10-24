"""Amendment 21j: macro post-release drift (J1) and Wikipedia attention shocks (J2) - only explore0 rows are read,
the placebo avoids calendar days, attention is used from its available_ts, and the cost hurdle is the 21i rule."""
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypogen, m21iscreen, m21jscreen as m  # noqa: E402

H, D = 3600, 86400
A, B = hypogen.bounds("explore0")


def captured(fn, *a):
    """The rows a screen hands to its judge (an UNTESTABLE result carries no means)."""
    got = {}
    orig = m21iscreen.judge

    def spy(rows, pl, key, extra=None):
        got["rows"] = rows
        return orig(rows, pl, key, extra)
    m21iscreen.judge = spy
    try:
        return fn(*a), got["rows"]
    finally:
        m21iscreen.judge = orig


def px_line(n, start=A, slope=0.0005):
    return {start + i * H: 100.0 * math.exp(slope * i) for i in range(n)}


class Calendar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="m21j")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_only_scheduled_events_inside_explore0(self):
        ev = [{"date": "2020-01-29", "event": "FOMC statement", "scheduled": True, "ts": 1580324400.0},
              {"date": "2020-03-03", "event": "FOMC statement", "scheduled": False, "ts": None},
              {"date": "2020-04-29", "event": "FOMC statement", "scheduled": True, "ts": 1588183200.0}]
        with open(os.path.join(self.tmp, "fomc-2020.json"), "w") as f:
            json.dump({"events": ev}, f)
        events, busy = m.calendar(A, B, root=self.tmp)
        self.assertEqual(events, [(1588183200, "FOMC statement")])               # January is before explore0
        self.assertEqual(len(busy), 2)                                            # the unscheduled day counts as busy


class J1(unittest.TestCase):
    def test_follows_the_reaction_bar_and_skips_busy_placebo_days(self):
        p = px_line(3000)
        px, vol = {"BTCUSDT": p, "ETHUSDT": p}, {"BTCUSDT": {}, "ETHUSDT": {}}
        h = A + 2000 * H
        busy = {(h - 7 * D) // D}
        r, rows = captured(m.j1, px, vol, A, B, ([(h + 1800, "Consumer Price Index")], busy))
        self.assertEqual(r["n_events"], 1)
        self.assertAlmostEqual(rows[0]["y"], 24 * 0.0005)                         # up bar -> follow, 24 h of drift
        self.assertEqual(rows[0]["c"], hypogen.COST)
        self.assertEqual(r["method"], "m21j")


class J2(unittest.TestCase):
    def test_a_shock_week_is_used_from_tuesday_with_the_weeks_direction(self):
        monday = A + (7 - datetime.fromtimestamp(A, timezone.utc).weekday()) % 7 * D
        rows = []
        for i in range(9 * 7):
            d = datetime.fromtimestamp(monday + i * D, timezone.utc).strftime("%Y-%m-%d")
            rows.append({"date": d, "views": 3000 if i >= 8 * 7 else 1000})
        rows.append({"date": "2023-01-02", "views": 10 ** 9})                      # outside explore0: never read
        wk = m.weekly(rows, A, B)
        self.assertEqual(len(wk), 9)
        shock = monday + 8 * 7 * D
        p = px_line(3000)
        vol = {t: 1e9 / 24 for t in p}                                             # liquid: the 0.46 % floor
        r, rows = captured(m.j2, {"BTCUSDT": p}, {"BTCUSDT": vol}, A, B, {"Bitcoin": wk})
        self.assertEqual(r["n_events"], 1)
        t = shock + 8 * D
        self.assertEqual(rows[0]["h"], shock)
        self.assertAlmostEqual(rows[0]["y"], math.log(p[t + 168 * H] / p[t]))     # rising week -> s = +1
        self.assertEqual(m.j2({"BTCUSDT": p}, {"BTCUSDT": {}}, A, B, {"Bitcoin": wk})["excluded"],
                         {"no volume history": 1})
        self.assertEqual(r["descriptive_not_tested"]["shocks per coin"]["BTCUSDT"], 1)


if __name__ == "__main__":
    unittest.main()
