"""Real SSH verification with throwaway keys, never an operational owner key."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

import authorization as auth
from job_store import JobStore

NOW = 1000000
START = NOW + 60


def protocol(study_id="study"):
    return dict(schema_version=1, study_id=study_id, mode="forward_paper", created_at=NOW - 10,
                alpha=0.05, q_fdr=0.05,
                source_identity=dict(kind="local_forward", source_id="owned-feed", adapter_version=1),
                candidates=[dict(candidate_id="C", family="F",
                    protocol=dict(window=dict(start=START, end=START + 86400), cadence_s=60),
                    paper_plan=dict(protocol_id="C", max_gross_fraction=0.25))])


class AuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.TemporaryDirectory(prefix="authorization-test-keys-")
        cls.root = Path(cls.keys.name)
        for name in ("owner", "other"):
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name,
                            "-f", str(cls.root / name)], check=True, capture_output=True)
        cls.owner_public = (cls.root / "owner.pub").read_text().strip()
        cls.other_public = (cls.root / "other.pub").read_text().strip()

    @classmethod
    def tearDownClass(cls):
        cls.keys.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="authorization-registry-")
        self.addCleanup(self.directory.cleanup)
        self.root_case = Path(self.directory.name)
        self.db = self.root_case / "authorizations.sqlite3"
        self.signers = self.root_case / "allowed_signers"
        self.signers.write_text(f'owner namespaces="{auth.owner.NAMESPACE}" {self.owner_public}\n')
        self.bundle = protocol()

    def signed(self, bundle=None, nonce="unique-nonce", key="owner", **changes):
        bundle = self.bundle if bundle is None else bundle
        statement = auth.owner.statement(bundle["study_id"], auth.protocol_digest(bundle), 1,
                                         nonce, NOW - 10, NOW + 20,
                                         "I approve this exact frozen forward protocol")
        statement.update(changes)
        return statement, auth.owner.sign(statement, str(type(self).root / key))

    def freeze(self, statement=None, signature=None, **changes):
        if statement is None:
            statement, signature = self.signed()
        return auth.freeze_protocol(changes.pop("bundle", self.bundle), statement, signature,
                                    changes.pop("signers", self.signers),
                                    changes.pop("db", self.db), changes.pop("now", NOW))

    def check(self, **changes):
        return auth.verify_authorization(changes.pop("digest", auth.protocol_digest(self.bundle)),
                                         changes.pop("study_id", self.bundle["study_id"]),
                                         changes.pop("window_start", START),
                                         changes.pop("signers", self.signers),
                                         changes.pop("db", self.db))

    def test_pre_window_receipt_remains_valid_after_short_expiry(self):
        statement, signature = self.signed()
        result = self.freeze(statement, signature)
        self.assertEqual(result["status"], "OWNER_APPROVED")
        self.assertEqual(result["verified_at"], NOW)
        with mock.patch.object(auth.owner, "verify", wraps=auth.owner.verify) as verified:
            checked = self.check()
        self.assertEqual(checked["status"], "OWNER_APPROVED")
        self.assertLess(statement["expires"], START + 86400)
        self.assertEqual(verified.call_args.args[5], NOW)
        later_retry = self.freeze(statement, signature, now=START + 86400)
        self.assertEqual(later_retry["status"], "OWNER_APPROVED")
        self.assertTrue(later_retry["idempotent"])
        self.assertEqual(later_retry["verified_at"], NOW)
        self.assertEqual(later_retry["receipt_sha256"], result["receipt_sha256"])

    def test_post_window_registration_and_future_creation_refused(self):
        statement, signature = self.signed(expires=START + 100)
        result = self.freeze(statement, signature, now=START + 1)
        self.assertEqual(result["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertFalse(self.db.exists())
        changed = copy.deepcopy(self.bundle)
        changed["created_at"] = NOW + 1
        statement, signature = self.signed(changed)
        self.assertEqual(self.freeze(statement, signature, bundle=changed)["status"], "BLOCKED_OWNER_APPROVAL")

    def test_exact_start_is_allowed_but_not_a_later_candidate_start_only(self):
        statement, signature = self.signed(expires=START + 1)
        self.assertEqual(self.freeze(statement, signature, now=START)["status"], "OWNER_APPROVED")
        self.assertEqual(self.check(window_start=NOW)["status"], "BLOCKED_OWNER_APPROVAL")

    def test_wrong_payload_template_and_key_are_refused(self):
        statement, signature = self.signed(key="other")
        self.assertEqual(self.freeze(statement, signature)["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertFalse(self.db.exists())
        statement, signature = self.signed(template="another-study")
        self.assertEqual(self.freeze(statement, signature)["status"], "BLOCKED_OWNER_APPROVAL")
        statement, signature = self.signed()
        changed = copy.deepcopy(self.bundle)
        changed["alpha"] = 0.01
        self.assertEqual(self.freeze(statement, signature, bundle=changed)["status"], "BLOCKED_OWNER_APPROVAL")

    def test_nonce_cannot_authorize_another_protocol(self):
        self.assertEqual(self.freeze()["status"], "OWNER_APPROVED")
        changed = copy.deepcopy(self.bundle)
        changed["alpha"] = 0.01
        statement, signature = self.signed(changed)
        result = self.freeze(statement, signature, bundle=changed, now=NOW + 1)
        self.assertEqual(result["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertIn("NONCE_REUSE_CONFLICT", result["reasons"])
        self.assertEqual(self.check()["status"], "OWNER_APPROVED")

    def test_expired_unregistered_statement_does_not_create_receipt(self):
        statement, signature = self.signed(expires=NOW)
        self.assertEqual(self.freeze(statement, signature)["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertFalse(self.db.exists())

    def test_revoked_key_blocks_saved_receipt_but_added_other_key_does_not(self):
        saved = self.freeze()
        self.signers.write_text(f'owner namespaces="{auth.owner.NAMESPACE}" {self.owner_public}\n'
                                f'owner namespaces="{auth.owner.NAMESPACE}" {self.other_public}\n')
        checked = self.check()
        self.assertEqual(checked["status"], "OWNER_APPROVED")
        self.assertEqual(checked["owner_signers_sha256"], saved["owner_signers_sha256"])
        self.assertNotEqual(checked["current_owner_signers_sha256"], saved["owner_signers_sha256"])
        self.signers.write_text(f'owner namespaces="{auth.owner.NAMESPACE}" {self.other_public}\n')
        self.assertEqual(self.check()["status"], "BLOCKED_OWNER_APPROVAL")

    def test_lookup_requires_protocol_and_study_binding(self):
        self.freeze()
        self.assertEqual(self.check(digest="0" * 64)["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertEqual(self.check(study_id="different")["status"], "BLOCKED_OWNER_APPROVAL")
        absent = self.root_case / "missing.sqlite3"
        self.assertEqual(self.check(db=absent)["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertFalse(absent.exists())

    def test_foreign_and_research_databases_are_not_modified(self):
        foreign = self.root_case / "foreign.sqlite3"
        with sqlite3.connect(foreign) as connection:
            connection.execute("CREATE TABLE private_data(value TEXT)")
        before = foreign.read_bytes()
        self.assertEqual(self.freeze(db=foreign)["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertEqual(foreign.read_bytes(), before)
        jobs = self.root_case / "jobs.sqlite3"
        with JobStore(jobs) as store:
            store.enqueue("research", dict(not_an_authorization=True), now=NOW)
        before = jobs.read_bytes()
        self.assertEqual(self.freeze(db=jobs)["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertEqual(jobs.read_bytes(), before)
        with JobStore(jobs) as store:
            self.assertEqual(store.counts()["total"], 1)

    def test_receipt_tampering_and_late_registration_time_fail_closed(self):
        self.freeze()
        with sqlite3.connect(self.db) as connection:
            job_id, raw = connection.execute("SELECT job_id,payload_json FROM jobs").fetchone()
            receipt = json.loads(raw)
            receipt["verified_at"] = START + 1
            receipt["receipt_sha256"] = auth.protocol_digest(auth._receipt_body(receipt))
            connection.execute("UPDATE jobs SET payload_json=? WHERE job_id=?",
                               (json.dumps(receipt), job_id))
        self.assertEqual(self.check()["status"], "BLOCKED_OWNER_APPROVAL")

    def test_research_jobs_cannot_be_mixed_into_authorization_registry(self):
        self.freeze()
        with JobStore(self.db) as store:
            store.enqueue("not-authorization", dict(research_job=True), now=NOW)
        self.assertEqual(self.check()["status"], "BLOCKED_OWNER_APPROVAL")

    def test_receipt_is_stored_only_after_existing_verifier_accepts(self):
        with mock.patch.object(auth.owner, "verify", return_value=("REFUSED", ["test refusal"])):
            result = self.freeze()
        self.assertEqual(result["status"], "BLOCKED_OWNER_APPROVAL")
        self.assertFalse(self.db.exists())
        self.freeze()
        with JobStore(self.db) as store:
            rows = store.list_jobs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payload"]["kind"], auth.REGISTRY_KIND)
        self.assertEqual(rows[0]["payload"]["verified_at"], NOW)


if __name__ == "__main__":
    unittest.main()
