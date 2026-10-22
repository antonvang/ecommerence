"""research/LINUX_DRIFT.md 2026-10-22: `lab hypo-audit` summarises what amendment 17 recorded, read-only."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import hypoaudit, hypogen  # noqa: E402
from lab.db import DB  # noqa: E402


class HypoAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labha")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        ev = lambda p: self.db.event(hypogen.EV_SCREEN, "system:test", None, p)  # noqa: E731
        ev({"key": "airdrop|ar_1d|m17", "verdict": "UNTESTABLE", "events": 37, "n": 11,
            "excluded": {"missing price": 26}})
        ev({"key": "airdrop|ar_7d|m17", "verdict": "UNTESTABLE", "events": 37, "n": 9,
            "excluded": {"missing price": 26, "window outside the phase": 2}})
        ev({"key": "spot_listing|sar_7d|m17", "verdict": "SCREEN_FAIL", "n": 113, "mean": -0.19, "p": 0.0001,
            "placebo": {"n": 0, "mean": None, "p": None},
            "checks": {"p <= 0.005": True, "same sign": True, "placebo p > 0.05 (n >= 15)": False}})
        ev({"key": "margin|vol_3d|m17c", "verdict": "SCREEN_FAIL", "n": 63, "mean": -0.15, "p": 0.001,
            "placebo": {"n": 60, "mean": -0.1, "p": 0.022},
            "checks": {"p <= 0.005": True, "placebo p > 0.05 (n >= 15)": False}})
        ev({"key": "margin|sar_1d|m17c", "verdict": "SCREEN_PASS", "n": 287, "mean": -0.02, "p": 0.0012})
        ev({"key": "x|far_7d|m17", "verdict": "SCREEN_PASS", "n": 50, "mean": -0.1, "p": 0.001})
        ev({"key": "x|far_7d|m17", "verdict": "SCREEN_PASS", "n": 50, "mean": -0.1, "p": 0.001})   # a repeat
        self.db.event("research.measurement", "system:test", None,
                      {"hypothesis": "margin|sar_1d|m17c", "verdict": "REJECTED", "reason": "validation3: p 0.44"})
        self.db.event("research.measurement", "system:test", None, {"hypothesis": "H5", "verdict": "PASS"})

    def tearDown(self):
        self.db.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_counts_causes_blind_spot_and_independent_record(self):
        lines = []
        self.assertEqual(hypoaudit.main(self.db.path, out=lines.append), 0)
        text = "\n".join(lines)
        self.assertEqual(lines[0], "6 keys screened: SCREEN_FAIL 2, SCREEN_PASS 2, UNTESTABLE 2")
        self.assertIn("      52  missing price", text)
        self.assertIn("  airdrop              2 keys    37 events  n <= 11", text)
        self.assertIn("     2  placebo p > 0.05 (n >= 15)", text)
        self.assertIn("failed WITHOUT a placebo value (blind spot, see research/studies/AUDIT_HYPOTESER_2026-10-22.md): 1",
                      text)
        self.assertIn("  spot_listing|sar_7d|m17  n=113  mean=-0.1900  p=0.0001", text)
        self.assertNotIn("margin|vol_3d|m17c  n=", text)               # it had a placebo value
        self.assertIn("SCREEN_PASS 2; measured on independent data 1; passed there 0", text)
        self.assertIn("  margin|sar_1d|m17c: REJECTED (validation3: p 0.44)", text)
        self.assertIn("  x|far_7d|m17: not measured (needs a LÅS-17 lock)", text)

    def test_it_writes_nothing(self):
        before = self.db.one("SELECT COUNT(*) FROM events")[0]
        hypoaudit.main(self.db.path, out=lambda s: None)
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events")[0], before)


if __name__ == "__main__":
    unittest.main()
