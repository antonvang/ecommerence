"""adversarial.strict_truncation_test: catches a family that reads the current bar's close (the blind spot of the
existing truncation/poison tests, statistics audit 2026-10-21); a gate since amendment 15 point 1."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab.engine import adversarial, catalogue  # noqa: E402

H = 3600


def bars(n=24 * 40, seed=5):
    rng, c, out = random.Random(seed), 100.0, []
    for h in range(n):
        c2 = c * math.exp(rng.gauss(0, 0.006))
        out.append((1_600_000_000 + h * H, c, c2))
        c = c2
    return out


def peek_current(b, f, p, fit=None):                     # reads close_i: a one-bar look-ahead
    return [0.0] + [1.0 if b[i][2] > b[i - 1][2] else -1.0 for i in range(1, len(b))]


def honest(b, f, p, fit=None):                           # uses closes before bar i only
    return [0.0, 0.0] + [1.0 if b[i - 1][2] > b[i - 2][2] else -1.0 for i in range(2, len(b))]


class Strict(unittest.TestCase):
    def test_the_old_tests_miss_the_current_close_and_the_strict_one_catches_it(self):
        x = bars()
        self.assertTrue(adversarial.truncation_test(peek_current, x, {}, {})["ok"])     # the documented blind spot
        self.assertTrue(adversarial.poison_test(peek_current, x, {}, {})["ok"])
        self.assertFalse(adversarial.strict_truncation_test(peek_current, x, {}, {})["ok"])

    def test_an_honest_family_passes(self):
        self.assertTrue(adversarial.strict_truncation_test(honest, bars(), {}, {})["ok"])

    def test_a_catalogue_template_passes(self):
        t = catalogue.TEMPLATES["vol_managed_long"]
        self.assertTrue(adversarial.strict_truncation_test(t["family"], bars(), {}, t["grid"][0])["ok"])

    def test_cross_sectional_strict_test_catches_the_current_close_and_volume(self):
        xs = {f"S{k}USDT": bars(seed=k) for k in range(4)}
        cheat = lambda b, f, p, fit=None, vol=None: {s: peek_current(x, f, p) for s, x in b.items()}   # noqa: E731
        self.assertTrue(adversarial.truncation_test_xs(cheat, xs, {s: {} for s in xs}, {})["ok"])     # the blind spot
        self.assertFalse(adversarial.strict_truncation_test_xs(cheat, xs, {s: {} for s in xs}, {})["ok"])
        fair = lambda b, f, p, fit=None, vol=None: {s: honest(x, f, p) for s, x in b.items()}         # noqa: E731
        self.assertTrue(adversarial.strict_truncation_test_xs(fair, xs, {s: {} for s in xs}, {})["ok"])
        vol = {s: {ts: float(i % 7) for i, (ts, _, _) in enumerate(x)} for s, x in xs.items()}

        def peek_volume(b, f, p, fit=None, v=None):          # reads the current bar's volume (known at its close)
            return {s: [1.0 if (v or {}).get(s, {}).get(x[0], 0) > 3 else 0.0 for x in bars_] for s, bars_ in b.items()}
        self.assertFalse(adversarial.strict_truncation_test_xs(peek_volume, xs, {s: {} for s in xs}, {},
                                                               volume_by=vol)["ok"])

    def test_the_pipeline_gate_includes_the_strict_test(self):
        import inspect
        from lab import pipeline
        src = inspect.getsource(pipeline.step_adversarial)
        self.assertIn("strict_truncation_test_xs", src)
        self.assertIn("for t in (trunc, strict, poison)", src)
        self.assertIn("adversarial.placebo_returns(", src)                     # amendment 15a point 1
        self.assertIn('block="auto"', inspect.getsource(pipeline._evaluate))  # amendment 15a point 2


if __name__ == "__main__":
    unittest.main()
