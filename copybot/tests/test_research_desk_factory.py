"""Director order 50 P2: nightly research factory prototype (synthetic; throwaway keys only)."""
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.tools import desk_factory as df  # noqa: E402
from research.tools import owner_approval as oa  # noqa: E402


def keypair(d, name):
    path = os.path.join(d, name)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", path], check=True)
    with open(path + ".pub", encoding="utf-8") as f:
        return path, f.read().strip()


class DeskFactory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.owner, pub = keypair(cls.d, "owner_test")
        cls.assistant, _ = keypair(cls.d, "assistant_test")
        cls.allowed = os.path.join(cls.d, "allowed_signers")
        with open(cls.allowed, "w", encoding="utf-8") as f:
            f.write(f'owner namespaces="{oa.NAMESPACE}" {pub}\n')

    def approver(self, key, now, words="I approve this protocol for a forward test"):
        log = oa.AuditLog()

        def ap(rec):
            s = oa.statement(rec["id"], rec["protocol_sha256"], 1, os.urandom(8).hex(), now - 10, now + 3600, words)
            return oa.verify(s, oa.sign(s, key), self.allowed, rec["protocol_sha256"], 1, now, log)
        return ap

    def night1(self):
        desk, ideas, protocols, loader, now = df.synthetic()
        rep = df.nightly(desk, ideas, protocols, now, data_loader=loader)
        return desk, rep, protocols, loader, now

    def by_name(self, desk, name):
        return next(r for r in desk.records.values() if r["idea"]["name"] == name)

    def test_night_without_owner_approves_nothing(self):
        desk, rep, *_ = self.night1()
        self.assertEqual(rep["states"]["APPROVED"] + rep["states"]["FROZEN"] + rep["states"]["EVALUATED"], 0)
        self.assertEqual(sorted(rep["awaiting_owner"]),
                         sorted(self.by_name(desk, n)["id"] for n in ("fund_persist_A", "basis_B", "tsmom_C",
                                                                     "coinm_F")))
        self.assertEqual(desk.ledger.entries, [])
        self.assertTrue(rep["ledger_ok"])

    def test_duplicates_literature_power_and_incomplete_protocol_are_parked(self):
        desk, rep, *_ = self.night1()
        reasons = {r["idea"]["name"]: r.get("park_reason", "") for r in desk.records.values()}
        self.assertTrue(reasons["fund_persist_A_copy"].startswith("DUPLICATE"))
        self.assertEqual(reasons["rumour_D"], "NO_VERIFIED_LITERATURE")
        self.assertTrue(reasons["rev_E_lowpower"].startswith("INSUFFICIENT_POWER"))
        self.assertTrue(reasons["bad_G"].startswith("PROTOCOL_INCOMPLETE"))
        self.assertIn(self.by_name(desk, "fund_persist_A")["id"], self.by_name(desk, "basis_B")["related"])

    def test_assistant_key_or_delegated_words_never_approve(self):
        desk, rep, protocols, loader, now = self.night1()
        for ap in (self.approver(self.assistant, now), self.approver(self.owner, now, "Approved by Claude on behalf")):
            rep2 = df.nightly(desk, [], protocols, now, data_loader=loader, approver=ap)
            self.assertEqual(rep2["states"]["APPROVED"] + rep2["states"]["FROZEN"], 0)
        self.assertTrue(all(r.get("approval_refusals") for r in desk.records.values()
                            if r["state"] == "AWAITING_OWNER_APPROVAL"))

    def test_signed_owner_approval_then_gates_then_holm(self):
        desk, rep, protocols, loader, now = self.night1()
        rep2 = df.nightly(desk, [], protocols, now, data_loader=loader, approver=self.approver(self.owner, now))
        blocked = {b["id"]: b["why"] for b in rep2["blocked_by_gates"]}
        self.assertEqual(len(blocked), 4)                                  # window not finished yet: no data
        self.assertEqual(rep2["evaluated"], [])
        self.assertEqual(desk.ledger.entries, [])
        later = now + 86400 * 800
        rep3 = df.nightly(desk, [], protocols, later, data_loader=loader)
        coinm = self.by_name(desk, "coinm_F")
        self.assertEqual(coinm["state"], "FROZEN")                         # COIN-M stream gated
        self.assertTrue(any("coinm_fwd" in w for b in rep3["blocked_by_gates"] for w in b["why"]))
        self.assertEqual(self.by_name(desk, "fund_persist_A")["state"], "VALIDATED")
        self.assertIn(self.by_name(desk, "basis_B")["state"], ("REJECTED", "VALIDATED"))
        self.assertEqual(len(desk.ledger.entries), 3)
        desk.ledger.verify()
        # an identical re-run charges nothing and changes nothing (terminal states are final)
        rep4 = df.nightly(desk, [], protocols, later, data_loader=loader)
        self.assertEqual(len(desk.ledger.entries), 3)
        self.assertEqual(rep4["evaluated"], [])
        with self.assertRaises(df.DeskError):
            desk._move(self.by_name(desk, "fund_persist_A"), "PARKED", later, "reopen")

    def test_invalid_evaluator_input_charges_nothing(self):
        desk, rep, protocols, loader, now = self.night1()
        df.nightly(desk, [], protocols, now, data_loader=loader, approver=self.approver(self.owner, now))

        def bad(rec):
            fx = loader(rec)
            fx["hypotheses"][0]["fee_bps"] = 2.0                           # unknown cost component
            return fx
        rep = df.nightly(desk, [], protocols, now + 86400 * 800, data_loader=bad)
        self.assertEqual(desk.ledger.entries, [])
        self.assertEqual(rep["evaluated"], [])
        self.assertEqual(len(rep["errors"]), 3)
        rec = self.by_name(desk, "fund_persist_A")
        self.assertEqual(rec["state"], "DATA_ELIGIBLE")
        self.assertIn(["UNKNOWN_FIELD", "hypotheses[0].fee_bps"], rec["evaluation_refused"])
        df.nightly(desk, [], protocols, now + 86400 * 801, data_loader=loader)   # fixed input evaluates normally
        self.assertEqual(rec["state"], "VALIDATED")
        self.assertEqual(rec["result"]["evaluator"], "1.1")

    def test_protected_period_and_late_freeze_block_data(self):
        desk, rep, protocols, loader, now = self.night1()
        rec = self.by_name(desk, "tsmom_C")
        rec["protocol"]["window_start"] = 1_704_067_200                    # 2024: protected holdout
        rec["protocol_sha256"] = df.sha(rec["protocol"])
        df.nightly(desk, [], protocols, now, data_loader=loader, approver=self.approver(self.owner, now))
        why = desk.gates(rec, now + 86400 * 365)
        self.assertTrue(any("protected" in w for w in why))
        self.assertTrue(any("not frozen before" in w for w in why))

    def test_protocol_change_after_approval_is_refused(self):
        desk, rep, protocols, loader, now = self.night1()
        rec = self.by_name(desk, "basis_B")
        desk.approve(rec, now, self.approver(self.owner, now))
        rec["protocol"]["n_planned"] = 9999
        with self.assertRaises(df.DeskError):
            desk.freeze(rec, now)

    def test_failing_job_parks_only_that_idea_and_no_network(self):
        desk, ideas, protocols, loader, now = df.synthetic()
        ideas = ideas + [{"name": "boom", "mechanism": "tsmom", "direction": "+", "universe": ["U9"],
                          "estimand": "x", "evidence_ids": ["E2"]}]
        protocols = dict(protocols, boom={f: 1 for f in df.PROTOCOL_FIELDS})  # power check will blow up on types
        with mock.patch.object(df.p2_power, "sr_power", side_effect=lambda *a, **k: (_ for _ in ()).throw(
                ValueError("boom")) if a[1] == 1 else 0.99), \
                mock.patch.object(socket, "socket", side_effect=AssertionError("network")):
            rep = df.nightly(desk, ideas, protocols, now, data_loader=loader)
        self.assertEqual(len(rep["errors"]), 1)
        self.assertEqual(self.by_name(desk, "boom")["park_reason"], "JOB_FAILED")
        self.assertIn(self.by_name(desk, "fund_persist_A")["id"], rep["awaiting_owner"])

    def test_queue_and_budget(self):
        desk, ideas, protocols, loader, now = df.synthetic()
        rep = df.nightly(desk, ideas, protocols, now, max_new_ideas=3)
        self.assertEqual((len(rep["new"]), rep["queued"]), (3, len(ideas) - 3))
        desk2, *_ = df.synthetic()
        rep2 = df.nightly(desk2, ideas, protocols, now, cpu_budget_s=-1)
        self.assertTrue(rep2["budget_exhausted"])
        self.assertEqual(rep2["new"], [])

    def test_no_lab_imports(self):
        with open(df.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import lab", src)
        self.assertNotIn("from lab", src)
        self.assertNotIn("sqlite3", src)


if __name__ == "__main__":
    unittest.main()
