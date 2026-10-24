import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import check_note_times as cnt  # noqa: E402


class NoteTimes(unittest.TestCase):
    """research/LINUX_DRIFT.md 2026-10-24: a written time may not lie after the commit that wrote it."""

    def run_on(self, rows, since=""):
        with mock.patch.object(cnt, "blame", lambda p: rows):
            return cnt.check(["x.md"], since)

    def test_a_time_after_its_commit_is_flagged_and_ca_may_round_up_five_minutes(self):
        rows = [("2026-10-24", "10:32", "Målt 2026-10-24 ca. 10:45 lokal tid"),          # 13 min late
                ("2026-10-24", "12:53", "**Opfølgning 2026-10-24 kl. 12:54:**"),         # 1 min late, exact
                ("2026-10-24", "17:55", "Søgt 2026-10-24 ca. 18:00 lokal tid"),           # rounding: ok
                ("2026-10-24", "13:14", "Skrevet 2026-10-24 kl. 13:13 af Claude."),       # before: ok
                ("2026-10-24", "09:00", "data til 2026-10-23 23:50"),                     # another day: ok
                ("2026-10-23", "16:17", "register til 2026-10-23 16:20 lokal tid")]       # before --since
        self.assertEqual([b[2] for b in self.run_on(rows)], ["10:45", "12:54", "16:20"])
        self.assertEqual([b[2] for b in self.run_on(rows, since="2026-10-24")], ["10:45", "12:54"])

    def test_research_notes_from_2026_10_24_on_have_no_time_after_their_commit(self):
        bad = cnt.check(sorted(cnt.glob.glob(os.path.join(cnt.HERE, "research", "**", "*.md"), recursive=True)),
                        since="2026-10-24")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
