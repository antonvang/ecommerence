"""Order 74 P0: named so that `unittest discover -s tests` loads it first. Discovery does not import the tests package
by itself; importing it here installs the quarantine guard before any other test module is loaded."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import offline_market  # noqa: E402


class GuardIsInstalled(unittest.TestCase):
    def test_process_guard_is_on(self):
        self.assertTrue(offline_market._process_guard)
