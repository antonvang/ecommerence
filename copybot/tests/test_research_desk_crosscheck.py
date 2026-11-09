"""Director order 50 P3: Claude's EVALUATOR_SPEC v1 implementation on the synthetic fixtures."""
import glob
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.desk.crosscheck import claude_eval as ce  # noqa: E402
from research.desk.crosscheck import compare  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "desk",
                   "synthetic_fixtures")


def load(name):
    with open(os.path.join(FIX, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


class CrossCheck(unittest.TestCase):
    def test_reproducible_and_injected_faults_counted(self):
        a, b = ce.evaluate(load("F2_lookahead")), ce.evaluate(load("F2_lookahead"))
        self.assertEqual(ce.canonical(a), ce.canonical(b))
        self.assertEqual(a["hypotheses"]["H_good_sign"]["n_lookahead"], 142)
        f4 = ce.evaluate(load("F4_survivorship"))["hypotheses"]["H_noise"]
        self.assertEqual((f4["n_not_member"], f4["n_extreme"]), (172, 1))
        f5 = ce.evaluate(load("F5_extreme_dupes_offgrid"))
        self.assertEqual(f5["hypotheses"]["H_good_sign_copy"]["status"], "DUPLICATE")
        self.assertEqual([e["reason"] for e in f5["ledger"]["errors"]], ["alpha", "variants", "variants", "variants"])
        self.assertEqual((f5["ledger"]["entries"], f5["ledger"]["idempotent_hits"]), (4, 1))
        self.assertTrue(all(h["status"] == "INSUFFICIENT" for h in ce.evaluate(load("F6_short"))["hypotheses"].values()))

    def test_planted_effect_survives_holm_and_compare_detects_differences(self):
        r = ce.evaluate(load("F1_clean"))["hypotheses"]
        self.assertTrue(r["H_good_sign"]["holm_reject"] and r["H_good_clip"]["holm_reject"])
        self.assertFalse(r["H_noise"]["holm_reject"])
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            ce.main(sorted(glob.glob(os.path.join(FIX, "*.json"))) + ["--out", d1])
            ce.main(sorted(glob.glob(os.path.join(FIX, "*.json"))) + ["--out", d2])
            self.assertTrue(all(v == [] for v in compare.compare(d1, d2).values()))
            p = os.path.join(d2, "F1_clean.json")
            with open(p, encoding="utf-8") as f:
                x = json.load(f)
            x["hypotheses"]["H_noise"]["t"] += 1e-6
            with open(p, "w", encoding="utf-8") as f:
                json.dump(x, f)
            self.assertEqual([d["path"] for d in compare.compare(d1, d2)["F1_clean.json"]], [".hypotheses.H_noise.t"])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
