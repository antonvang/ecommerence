"""Order 75 P2: `python3 tests/test_x.py` puts only tests/ on sys.path and never imports the tests package. Every test
file imports this module right before unittest.main(), which installs the same quarantine guard."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests  # noqa: E402,F401
