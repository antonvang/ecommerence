"""End-to-end operational contracts, not evidence about trading performance."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import research_runner as runner
from job_store import JobStore
from study_builder import build_demo


class RunnerTests(unittest.TestCase):
    def study(self, candidates=1):
        return build_demo(bars=32, candidates=candidates)

    def test_protocol_binds_source_and_candidate_definitions(self):
        study = self.study()
        self.assertIs(runner.validate_study(study), study)
        changed = copy.deepcopy(study)
        changed["source"]["seed"] += 1
        self.assertNotEqual(runner.digest(runner.protocol_bundle(study)),
                            runner.digest(runner.protocol_bundle(changed)))
        changed = copy.deepcopy(study)
        changed["candidates"][0]["protocol"]["lookback"] = 3
        with self.assertRaises(runner.StudyError):
            runner.validate_study(changed)

    def test_same_event_and_fixture_must_be_on_active_member_grid(self):
        for fault in ("offgrid", "embargo", "nonmember", "gap"):
            with self.subTest(fault=fault):
                study = self.study()
                c = study["candidates"][0]
                if fault == "offgrid":
                    for row, event in zip(c["fixture"]["observations"], c["paper_events"]):
                        row["ts"] += 1
                        row["signals"][c["protocol"]["signal_key"]]["avail_ts"] += 1
                        for key in ("ts", "quote_ts", "avail_ts"):
                            event[key] += 1
                elif fault == "embargo":
                    c["protocol"]["window"]["embargo_s"] = 60
                    c["fixture"]["window"]["embargo_s"] = 60
                elif fault == "nonmember":
                    for universe in (c["protocol"]["universe"], c["fixture"]["universe"]):
                        universe["SYN_A"]["listed_from"] += 60
                else:
                    del c["fixture"]["observations"][2]
                    del c["paper_events"][2]
                with self.assertRaises(runner.StudyError):
                    runner.validate_study(study)

    def test_matching_outcome_leak_is_not_a_causal_recipe(self):
        study = self.study()
        c = study["candidates"][0]
        for row, event in zip(c["fixture"]["observations"], c["paper_events"]):
            value = 1.0 if row["ret"] > 0 else -1.0
            row["signals"][c["protocol"]["signal_key"]]["value"] = value
            event["signal"] = value
        c["fixture"]["lock"]["data_sha256"] = runner.digest(c["fixture"]["observations"])
        with self.assertRaisesRegex(runner.StudyError, "causal"):
            runner.validate_study(study)

    def test_terminal_return_and_paper_signal_are_bound(self):
        for field in ("terminal", "signal", "funding"):
            study = self.study()
            c = study["candidates"][0]
            if field == "terminal":
                c["terminal_marks"]["SYN_A"] *= 1.01
            elif field == "signal":
                c["paper_events"][0]["signal"] = 0.25
            else:
                c["paper_events"][0]["funding_rate"] += 0.01
            with self.subTest(field=field), self.assertRaises(runner.StudyError):
                runner.validate_study(study)

    def test_forward_label_without_trust_cannot_run(self):
        study = self.study()
        study["mode"] = "forward_paper"
        study["source"] = dict(kind="local_forward_export", source_id="test-only",
                               adapter_version="v1", receipt=None, signature=None)
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "jobs.sqlite3"
            runner.submit(study, db)
            report = runner.run(db)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertFalse(report["pooled_hypotheses"])
            with JobStore(db) as store:
                job = store.list_jobs()[0]
            self.assertEqual(report["blocked"][0]["status"], "BLOCKED_OWNER_APPROVAL")
            self.assertEqual((job["status"], job["attempts"], job["result"]), ("queued", 0, None))

    def test_partial_batch_has_no_multiple_testing_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "jobs.sqlite3"
            runner.submit(self.study(3), db)
            with JobStore(db) as store:
                now = int(time.time())
                job = store.claim("partial", now, 30)
                store.complete(job["job_id"], job["token"], runner.evaluate_payload(job["payload"]), now)
            report = runner.summary(db)
            self.assertEqual(report["status"], "PENDING")
            self.assertEqual(len(report["pooled_hypotheses"]), 1)
            h = next(iter(report["pooled_hypotheses"].values()))
            self.assertIsNone(h["holm_reject"])
            self.assertIsNone(h["bh_reject"])

    def test_changed_implementation_blocks_before_spending_job_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "jobs.sqlite3"
            runner.submit(self.study(), db)
            with mock.patch.object(runner, "implementation_hash", return_value="0" * 64):
                with self.assertRaisesRegex(runner.StudyError, "implementation"):
                    runner.run(db)
            with JobStore(db) as store:
                job = store.list_jobs()[0]
            self.assertEqual((job["status"], job["attempts"]), ("queued", 0))

    def test_quality_error_cannot_hide_behind_risk_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "jobs.sqlite3"
            runner.submit(self.study(), db)
            with JobStore(db) as store:
                payload = store.list_jobs()[0]["payload"]
            with mock.patch("paper_engine.simulate_paper", return_value=dict(
                    status="RISK_STOPPED", errors=[dict(reason="LOOKAHEAD_SIGNAL")])):
                result = runner.evaluate_payload(payload)
            self.assertEqual(result["status"], "BLOCKED_PAPER_QUALITY")

    def test_parallel_cli_and_repeat_are_identical_and_budgeted(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            command = [sys.executable, "-B", str(Path(runner.__file__)), "demo",
                       "--out", str(out), "--candidates", "3", "--workers", "3"]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            previous = (out / "report.json").read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(previous, (out / "report.json").read_bytes())
            report = json.loads(previous)
            self.assertEqual(report["counts"]["succeeded"], 3)
            self.assertFalse(report["automatic_promotion"])
            with JobStore(out / "jobs.sqlite3") as store:
                self.assertTrue(all(job["attempts"] == 1 for job in store.list_jobs()))


if __name__ == "__main__":
    unittest.main()
