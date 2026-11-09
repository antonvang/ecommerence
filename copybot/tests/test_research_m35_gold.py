"""Amendments 35/35a: the m35 runner reads only valid open-gold hours from the lock, finds events from data up to h,
needs a valid h + 4 h, counts without ever printing b, d or c, and judges with Student's t."""
import datetime as dt
import io
import json
import math
import os
import random
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "tools"))
import m35_gold as m  # noqa: E402
from lab import sessions  # noqa: E402

F, H, D = m.FIRST, 3600, 86400


def snap(h, paxg, xaut, xau=4000.0, late=60, extra=None):
    rows = {"XAUUSDT": [xau], "PAXGUSDT": [paxg], "XAUTUSDT": [xaut]}
    rows = {k: v for k, v in rows.items() if v[0] is not None}
    p = {"columns": ["markPrice"], "rows": rows, "premium_fetched_at": h + late}
    p.update(extra or {})
    return (h + late, p)


def noisy(hours, seed=1, spikes=()):
    rnd = random.Random(seed)
    out = {}
    for h in hours:
        e = rnd.gauss(0, 0.0002)
        if h in spikes:
            e += 0.01
        out[h] = snap(h, 4000 * math.exp(e), 4000 * math.exp(-e))
    return out


class Series(unittest.TestCase):
    def test_only_valid_open_hours_from_the_lock(self):
        sat = F + 5 * D + 12 * H                                           # Saturday noon: gold closed
        self.assertFalse(sessions.opened("commodity", sat))
        snaps = {F - H: snap(F - H, 4000, 4000), F: snap(F, 4000, 4000), F + H: snap(F + H, 4000, 4000, late=601),
                 F + 2 * H: snap(F + 2 * H, None, 4000), sat: snap(sat, 4000, 4000)}
        b = m.series(snaps, F + 30 * D)
        self.assertEqual(sorted(b["A"]), [F])
        self.assertEqual(sorted(b["B"]), [F, F + 2 * H])                    # XAUT is there when PAXG is missing

    def test_median_needs_twenty_prior_snapshots(self):
        b = {F + k * H: 0.0 for k in range(25)}
        d = m.deviations(b)
        self.assertNotIn(F + 19 * H, d)
        self.assertIn(F + 20 * H, d)


class Events(unittest.TestCase):
    def hours(self, days):
        return [h for h in range(F, F + days * D, H) if sessions.opened("commodity", h)]

    def test_a_spike_after_warm_up_is_an_event_only_with_a_valid_h_plus_4h(self):
        hs = self.hours(12)
        spike = hs[150]
        snaps = noisy(hs, spikes={spike})
        b = m.series(snaps, F + 20 * D)
        self.assertIn(spike, m.events(b["A"], m.deviations(b["A"])))
        del snaps[spike + m.LEAD]
        b = m.series(snaps, F + 20 * D)
        self.assertNotIn(spike, m.events(b["A"], m.deviations(b["A"])))

    def test_no_events_before_100_prior_deviations(self):
        hs = self.hours(12)
        snaps = noisy(hs, spikes={hs[30]})
        b = m.series(snaps, F + 20 * D)
        self.assertNotIn(hs[30], m.events(b["A"], m.deviations(b["A"])))

    def test_first_event_per_day(self):
        self.assertEqual(m.first_per_day([F + 3 * H, F + 5 * H, F + D + H]), {F: F + 3 * H, F + D: F + D + H})

    def test_count_shows_no_basis_values(self):
        hs = self.hours(12)
        out = m.count_snaps(noisy(hs, spikes={hs[150]}), F + 20 * D)
        flat = json.dumps(out)
        self.assertNotIn("0.0", flat)                                       # integers only
        self.assertGreaterEqual(out["pairs"]["A"]["events_with_outcome"], 1)
        self.assertEqual(out["days_need"], 28)

    def test_convergence_has_positive_c(self):
        hs = self.hours(60)
        rnd = random.Random(3)
        snaps = {}
        for h in hs:
            e = rnd.gauss(0, 0.00005)
            if h % D == 0 and h >= F + 8 * D:                                # a spike at 00 UTC, gone 1 h later
                e += rnd.choice((-1, 1)) * (0.01 + 0.001 * rnd.random())
            snaps[h] = snap(h, 4000 * math.exp(e), 4000 * math.exp(e))
        out = m.run_snaps(snaps, F + 70 * D)
        self.assertGreater(out["mean_c"], 0.009)
        self.assertEqual(out["verdict"], "PASS", out)

    def test_sign_of_zero_is_zero(self):
        self.assertEqual((m.sign(0.0), m.sign(-2), m.sign(3)), (0, -1, 1))


class Judge(unittest.TestCase):
    def days(self, vals):
        return {F + i * D: v for i, v in enumerate(vals)}

    def test_untestable_below_28_days(self):
        self.assertEqual(m.judge(self.days([0.01] * 27), {})["verdict"], "UNTESTABLE")

    def test_floor_and_placebo(self):
        strong = [0.008 + 0.001 * ((i % 5) - 2) for i in range(30)]
        noise = [0.01 * ((-1) ** i) for i in range(30)]
        self.assertEqual(m.judge(self.days(strong), self.days(noise))["verdict"], "PASS")
        weak = [0.003 + 0.001 * ((i % 5) - 2) for i in range(30)]           # significant, under 0.46 %
        self.assertEqual(m.judge(self.days(weak), self.days(noise))["verdict"], "SCREEN_FAIL")
        self.assertEqual(m.judge(self.days(strong), self.days(strong))["verdict"], "SCREEN_FAIL")

    def test_divergence_never_passes(self):
        neg = [-0.008 + 0.001 * ((i % 5) - 2) for i in range(30)]
        noise = [0.01 * ((-1) ** i) for i in range(30)]
        self.assertEqual(m.judge(self.days(neg), self.days(noise))["verdict"], "SCREEN_FAIL")


class Refusal(unittest.TestCase):
    def test_run_refuses_below_28_event_days(self):
        fake = {"rule": "x", "pairs": {}, "event_days": 3, "days_need": 28}
        with mock.patch.object(m, "count_snaps", return_value=fake), mock.patch.object(m, "run_snaps") as r, \
                mock.patch("census_check.load", return_value=({}, {}, [])):
            buf = io.StringIO()
            with redirect_stdout(buf):
                m.main(["run", "--db", ":memory:"])
        r.assert_not_called()
        self.assertIn("refused", json.loads(buf.getvalue()))


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
