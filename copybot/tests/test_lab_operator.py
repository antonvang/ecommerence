"""Fleet control commands record who ran them: the human, or an AI assistant acting for them."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import __main__ as cli  # noqa: E402
from lab.db import DB  # noqa: E402


class Operator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labop")
        self.path = os.path.join(self.tmp, "lab.db")
        DB(self.path).close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def actor(self, env):
        clean = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
            self.assertEqual(cli.main(["pause", "--reason", "operator test pause"], db_path=self.path,
                                      out=lambda *a: None), 0)
            cli.main(["resume", "--reason", "operator test resume"], db_path=self.path, out=lambda *a: None)
        db = DB(self.path)
        try:
            return db.one("SELECT actor FROM events WHERE kind='system.paused' ORDER BY id DESC LIMIT 1")[0]
        finally:
            db.close()

    def test_an_assistant_session_is_recorded_as_the_assistant(self):
        self.assertEqual(self.actor({"CLAUDECODE": "1"}), "ai:claude-code for " + cli.human())

    def test_a_terminal_is_recorded_as_the_human(self):
        self.assertEqual(self.actor({}), cli.human())


if __name__ == "__main__":
    unittest.main()
