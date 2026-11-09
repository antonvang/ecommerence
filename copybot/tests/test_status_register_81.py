"""Director order 81 P3: the append-only status register. Temporary files and synthetic events only; no real status."""
import ast
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.status import status_register as sr  # noqa: E402


class Register(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = os.path.join(d.name, "synthetic_register.jsonl")
        self.t = 1000.0

    def add(self, exp="SYNTH_A", status="DATA_SOURCE_UNAVAILABLE", effective=900, **k):
        self.t += 10
        return sr.append(self.path, exp, status, "synthetic reason", "synthetic:row:1", effective,
                         recorded_ts=self.t, **k)

    def lines(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read().splitlines()

    def write(self, lines):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def test_a_line_keeps_both_times_source_id_status_and_reason(self):
        e = self.add(effective=500)
        self.assertEqual((e["seq"], e["prev_hash"]), (1, sr.GENESIS))
        self.assertEqual((e["effective_ts"], e["recorded_ts"]), (500, 1010.0))
        self.assertEqual(e["experiment_id"], "SYNTH_A")
        self.assertEqual(e["status"], "DATA_SOURCE_UNAVAILABLE")
        self.assertEqual(e["reason"], "synthetic reason")
        self.assertEqual(e["source"], "synthetic:row:1")

    def test_the_chain_verifies_and_links(self):
        a = self.add()
        b = self.add("SYNTH_B", "PARTIAL_CLOSE")
        self.assertEqual(b["prev_hash"], a["hash"])
        v = sr.verify(self.path)
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual((v["entries"], v["head"]), (2, b["hash"]))

    def test_append_never_rewrites_earlier_lines(self):
        self.add()
        first = open(self.path, "rb").read()
        self.add("SYNTH_B")
        self.assertTrue(open(self.path, "rb").read().startswith(first))

    def test_a_changed_line_is_found(self):
        self.add()
        self.add("SYNTH_B")
        lines = self.lines()
        e = json.loads(lines[0])
        e["reason"] = "changed"
        lines[0] = json.dumps(e, sort_keys=True)
        self.write(lines)
        v = sr.verify(self.path)
        self.assertFalse(v["ok"])
        self.assertTrue(any("hash does not match" in p for p in v["problems"]))

    def test_a_rehashed_line_breaks_the_next_link(self):
        self.add()
        self.add("SYNTH_B")
        lines = self.lines()
        e = json.loads(lines[0])
        e["reason"] = "changed"
        e["hash"] = sr.line_hash(e)
        lines[0] = json.dumps(e, sort_keys=True)
        self.write(lines)
        v = sr.verify(self.path)
        self.assertFalse(v["ok"])
        self.assertTrue(any("prev_hash" in p for p in v["problems"]))

    def test_a_removed_or_reordered_line_is_found(self):
        for _ in range(3):
            self.add()
        lines = self.lines()
        self.write([lines[0], lines[2]])
        self.assertFalse(sr.verify(self.path)["ok"])
        self.write([lines[1], lines[0], lines[2]])
        self.assertFalse(sr.verify(self.path)["ok"])

    def test_a_cut_tail_needs_the_recorded_head(self):
        self.add()
        head = self.add("SYNTH_B")["hash"]
        self.write(self.lines()[:1])
        self.assertTrue(sr.verify(self.path)["ok"])                # undetectable from the file alone: documented
        v = sr.verify(self.path, expected_head=head)
        self.assertFalse(v["ok"])

    def test_a_torn_last_line_is_found_and_blocks_appending(self):
        self.add()
        with open(self.path, "ab") as f:
            f.write(b'{"seq": 2')
        self.assertFalse(sr.verify(self.path)["ok"])
        with self.assertRaises(sr.RegisterError):
            self.add()

    def test_nothing_is_appended_to_a_broken_chain(self):
        self.add()
        lines = self.lines()
        self.write([lines[0].replace("synthetic reason", "changed")])
        before = open(self.path, "rb").read()
        with self.assertRaises(sr.RegisterError):
            self.add("SYNTH_B")
        self.assertEqual(open(self.path, "rb").read(), before)

    def test_invalid_input_is_refused_and_writes_nothing(self):
        for kw in ({"status": "PASS"}, {"exp": ""}, {"effective": float("nan")}, {"effective": 10 ** 12}):
            with self.assertRaises(sr.RegisterError, msg=kw):
                self.add(**kw)
        for reason, source in (("", "s"), ("r", " ")):
            with self.assertRaises(sr.RegisterError):
                sr.append(self.path, "SYNTH_A", "PARTIAL_CLOSE", reason, source, 1, recorded_ts=2)
        self.assertFalse(os.path.exists(self.path) and os.path.getsize(self.path))

    def test_time_may_not_run_backwards(self):
        self.add()
        with self.assertRaises(sr.RegisterError):
            sr.append(self.path, "SYNTH_B", "PARTIAL_CLOSE", "r", "s", 1, recorded_ts=5)

    def test_a_correction_is_a_new_line_and_current_follows_it(self):
        a = self.add()
        b = self.add(status="EQUITY_NOT_COMPUTABLE", supersedes=a["seq"])
        self.assertEqual(len(self.lines()), 2)
        self.assertEqual(sr.current(self.path)["SYNTH_A"]["seq"], b["seq"])
        self.assertTrue(sr.verify(self.path)["ok"])

    def test_superseding_only_an_earlier_line_of_the_same_experiment(self):
        a = self.add()
        with self.assertRaises(sr.RegisterError):
            self.add("SYNTH_B", supersedes=a["seq"])
        with self.assertRaises(sr.RegisterError):
            self.add(supersedes=99)

    def test_current_refuses_a_broken_chain(self):
        self.add()
        self.write([self.lines()[0].replace("synthetic reason", "changed")])
        with self.assertRaises(sr.RegisterError):
            sr.current(self.path)

    def test_paths_inside_a_checkout_are_refused(self):
        for p in (os.path.join(HERE, "research", "status", "x.jsonl"), os.path.join(HERE, "x.jsonl"),
                  "/home/anton/ecommerence/copybot/research/status/x.jsonl"):
            with self.assertRaises(sr.RegisterError, msg=p):
                sr.append(p, "SYNTH_A", "PARTIAL_CLOSE", "r", "s", 1, recorded_ts=2)
            self.assertFalse(os.path.exists(p))

    def test_no_register_file_with_real_statuses_exists(self):
        folder = os.path.join(HERE, "research", "status")
        self.assertEqual([f for f in os.listdir(folder) if f.endswith((".jsonl", ".json", ".db"))], [])

    def test_the_module_touches_no_ledger_or_book(self):
        with open(sr.__file__, encoding="utf-8") as f:
            source = f.read()
        names = set()
        for n in ast.walk(ast.parse(source)):
            if isinstance(n, ast.Import):
                names |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or "").split(".")[0])
        self.assertEqual(names, {"fcntl", "hashlib", "json", "math", "os", "time"})
        for word in ("sqlite3", "lab.db", "alpha_ledger", "sim_equity", "sim_fills"):
            self.assertNotIn(word, source)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
