"""adversarial.strict_truncation_test: catches a family that reads the current bar's close (the blind spot of the
existing truncation/poison tests, statistics audit 2026-10-21). Not wired into any gate."""
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


if __name__ == "__main__":
    unittest.main()
