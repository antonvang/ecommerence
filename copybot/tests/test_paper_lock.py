import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper import single_instance  # noqa: E402


class PaperLock(unittest.TestCase):
    def test_only_one_instance(self):
        root = tempfile.mkdtemp()
        first = single_instance(root)
        self.assertIsNotNone(first)
        self.assertIsNone(single_instance(root))
        first.close()
        again = single_instance(root)
        self.assertIsNotNone(again)
        again.close()


if __name__ == "__main__":
    unittest.main()
