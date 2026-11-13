"""Day-N report of the event farm forward paper book (research/tools/event_farm_report.py): refused before day N
without --preview, PAPIR label, all 96 tests in register order (no ranking), null side by side, call-log summary,
and the book file byte-identical afterwards. Synthetic book only; no network."""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from research.tools import event_farm_forward_v2 as fv  # noqa: E402
from research.tools import event_farm_report as er  # noqa: E402
from test_farm_dashboard_live import build_book  # noqa: E402


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.db = os.path.join(cls.d, "event_farm_forward_test.db")
        build_book(cls.db)
        cls.calls = os.path.join(cls.d, "event_farm_source_calls_test.jsonl")
        cls.sha_before = sha(cls.db)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.d)

    def doc(self, day=14, now=None, preview=False):
        from research.tools import farm_dashboard as fd
        live = fd.read_forward(self.db)
        start = int(live["meta"]["start_ts"])
        now = start + day * 86400 + 60 if now is None else start + now
        return er.build(day, self.db, self.calls, now=now, preview=preview)

    def test_refused_before_day_n_without_preview(self):
        with self.assertRaises(er.TooEarly):
            self.doc(14, now=13 * 86400)
        doc = self.doc(14, now=86400, preview=True)
        self.assertIn("FORHÅNDSVISNING", doc)
        self.assertIn("må ikke citeres", doc)
        with self.assertRaises(ValueError):
            self.doc(15)

    def test_label_tests_in_register_order_and_no_ranking(self):
        doc = self.doc(28)
        self.assertNotIn("FORHÅNDSVISNING", doc)
        self.assertIn("rapport dag 28", doc)
        self.assertIn(er.LABEL, doc)
        self.assertIn("To uger er ingen dokumentation", doc)
        tests = fv.test_ids()
        for part in doc.split("## Bilag")[0].split("## 4.")[1:], doc.split("## Bilag")[1:]:
            text = part[0]
            pos = [text.find(f"| {t} |") for t in tests]
            self.assertTrue(all(p >= 0 for p in pos))
            self.assertEqual(pos, sorted(pos))
        for w in ("Data og dækning", "Kald-loggen", "Primært", "både stop og mål", "kun berøring", "værste fald"):
            self.assertIn(w, doc)

    def test_book_unchanged_and_missing_call_log_reported(self):
        self.doc(14)
        self.assertEqual(sha(self.db), self.sha_before)
        self.assertIn("kæde ikke fundet", self.doc(14))

    def test_call_log_summary_counts_and_chain(self):
        from research.tools import event_farm_source as src
        p = os.path.join(self.d, "event_farm_source_calls_x.jsonl")
        prev, lines = src.GENESIS, []
        for i, (status, err) in enumerate([(200, None), (500, "HTTPError: 500"), (200, None)]):
            line = json.dumps({"seq": i, "prev": prev, "status": status, "error": err, "delivered": 1, "gaps": 0,
                               "wall_ts": 1000 + i}, sort_keys=True)
            prev = hashlib.sha256(line.encode()).hexdigest()
            lines.append(line)
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        c = er.call_log_summary(p)
        self.assertEqual((c["lines"], c["non_200"], c["errors"], c["delivered"], c["chain_ok"]),
                         (3, 1, {"HTTPError": 1}, 3, True))
        with open(p, "w") as f:
            f.write("\n".join(lines[1:]) + "\n")
        self.assertFalse(er.call_log_summary(p)["chain_ok"])

    def test_cli_preview_needs_out(self):
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            er.main(["--day", "14", "--preview", "--db", self.db, "--calls", self.calls, "--cache", ""])


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401
    unittest.main()
