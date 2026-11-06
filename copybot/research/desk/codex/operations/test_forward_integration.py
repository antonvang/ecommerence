"""Forward contracts exercised only with synthetic paths and throwaway keys."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import authorization
import research_runner as runner
from job_store import JobStore
from study_builder import build_demo

sys.path.insert(0, str(runner.COPYBOT))
from research.tools import owner_approval


def forward_specimen(now):
    study = build_demo(study_id="test_forward_only", bars=32, candidates=1)
    shift = now - 7200 - study["candidates"][0]["protocol"]["window"]["start"]
    study["mode"] = "forward_paper"
    study["source"] = dict(kind="local_forward_export", source_id="paper_books",
                           adapter_version="test-v1", receipt=None, signature=None)
    study["created_at"] += shift
    for c in study["candidates"]:
        for window in (c["protocol"]["window"], c["fixture"]["window"]):
            window["start"] += shift
            window["end"] += shift
        for universe in (c["protocol"]["universe"], c["fixture"]["universe"]):
            for listing in universe.values():
                listing["listed_from"] += shift
        for row in c["fixture"]["observations"]:
            row["ts"] += shift
            row["signals"][c["protocol"]["signal_key"]]["avail_ts"] += shift
        for event in c["paper_events"]:
            for key in ("ts", "quote_ts", "avail_ts"):
                event[key] += shift
        c["fixture"]["lock"] = dict(protocol_sha256=runner.digest({k:c["fixture"][k] for k in
            ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}),
            data_sha256=runner.digest(c["fixture"]["observations"]))
    return study


class ForwardIntegrationTests(unittest.TestCase):
    def key(self, directory, name, principal, namespace):
        key = Path(directory) / name
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                       check=True, capture_output=True)
        signers = Path(directory) / (name + "_allowed")
        signers.write_text(principal + ' namespaces="' + namespace + '" ' +
                           Path(str(key) + ".pub").read_text())
        return key, signers

    def test_signed_pre_window_approval_and_capture_with_resume(self):
        now = int(time.time())
        study = forward_specimen(now)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            db, auth_db = directory / "jobs.db", directory / "approval.db"
            runner.submit(study, db)
            blocked = runner.run(db)
            self.assertEqual(blocked["status"], "BLOCKED")
            with JobStore(db) as store:
                self.assertEqual(store.list_jobs()[0]["attempts"], 0)
            # No real identity or market observation is involved in this test.
            owner_key, owner_signers = self.key(directory, "throwaway_owner", "owner", "copybot-approval")
            collector_key, collector_signers = self.key(directory, "throwaway_collector", "collector", "copybot-forward-data")
            protocol = runner.protocol_bundle(study)
            frozen_at = study["created_at"]
            stmt = owner_approval.statement(study["study_id"], runner.digest(protocol), 1,
                "one-test-nonce", frozen_at, frozen_at + 3600,
                "I approve this exact forward paper study")
            approved = authorization.freeze_protocol(protocol, stmt, owner_approval.sign(stmt, str(owner_key)),
                owner_signers, auth_db, frozen_at)
            self.assertEqual(approved["status"], "OWNER_APPROVED", approved)
            self.assertLess(stmt["expires"], now)
            candidate = study["candidates"][0]
            receipt = dict(schema_version=1, source_id=study["source"]["source_id"],
                adapter_version=study["source"]["adapter_version"], protocol_sha256=runner.digest(protocol),
                data_sha256=runner.digest(runner.data_bundle(study)),
                captured_from=candidate["protocol"]["window"]["start"], captured_to=candidate["protocol"]["window"]["end"])
            message = directory / "capture.json"
            message.write_text(runner.canonical(receipt))
            subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(collector_key),
                "-n", "copybot-forward-data", str(message)], check=True, capture_output=True)
            study["source"].update(receipt=receipt, signature=Path(str(message)+".sig").read_text())
            # A finalized export is a different immutable input snapshot. Its
            # queue is new; the data-free authorization remains the same.
            final_db = directory / "final_jobs.db"
            runner.submit(study, final_db)
            trust = dict(owner=str(owner_signers), collector=str(collector_signers), authorization_db=str(auth_db))
            report = runner.run(final_db, owner_signers=trust)
            self.assertEqual(report["status"], "COMPLETE", report)
            with JobStore(final_db) as store:
                job = store.list_jobs()[0]
            self.assertEqual(job["result"]["authorization"]["status"], "OWNER_APPROVED")
            self.assertEqual(job["result"]["authorization"]["provenance"]["status"], "VERIFIED_CAPTURE")
            self.assertEqual(job["attempts"], 1)
            before = runner.canonical(report)
            self.assertEqual(runner.canonical(runner.run(final_db, owner_signers=trust)), before)
            # A provenance tag is insufficient: tampered receipt cannot verify.
            bad = copy.deepcopy(job["payload"]["context"])
            bad["source"]["receipt"]["data_sha256"] = "0" * 64
            self.assertEqual(runner.verify_capture(bad, collector_signers, now)["status"], "BLOCKED_SOURCE_PROVENANCE")

    def test_queue_and_authorization_roles_cannot_share_a_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "same.db"
            with self.assertRaisesRegex(runner.StudyError, "separate"):
                runner.run(path, owner_signers=dict(authorization_db=str(path)))

    def test_existing_stream_policy_is_bound_and_protected_sources_block(self):
        import hashlib
        context = dict(source=dict(source_id="paper_books"),
            source_registry_sha256=hashlib.sha256(runner.STREAM_REGISTRY.read_bytes()).hexdigest(),
            window_start=int(time.time()) - 7200, window_end=int(time.time()) - 3600)
        self.assertEqual(runner.source_policy(context)["status"], "SOURCE_ALLOWED")
        for source in ("coinm_live", "pm_lp_collector", "fwd_tob_universe", "invented_stream"):
            changed = copy.deepcopy(context)
            changed["source"]["source_id"] = source
            self.assertEqual(runner.source_policy(changed)["status"], "BLOCKED_SOURCE_POLICY")
        context["source_registry_sha256"] = "0" * 64
        self.assertEqual(runner.source_policy(context)["status"], "BLOCKED_SOURCE_POLICY")


if __name__ == "__main__":
    unittest.main()
