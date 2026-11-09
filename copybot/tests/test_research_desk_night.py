"""Director order 51 P3: the full synthetic desk night passes every integrity check (and reports, never hides, a FAIL)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import desk_night  # noqa: E402


class DeskNight(unittest.TestCase):
    def test_all_integrity_checks_pass(self):
        with tempfile.TemporaryDirectory() as d:
            rep = desk_night.run(d)
        self.assertEqual(rep["fail"], 0, [c for c in rep["checks"] if c["result"] == "FAIL"])
        self.assertGreaterEqual(len(rep["checks"]), 12)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
