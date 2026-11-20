"""Gates read real files: plan lock + research verdicts, review file; CLI arm/check-mandate."""
import contextlib
import io
import json
import tempfile
import unittest
from unittest import mock

from jupiter_bot.execution import __main__ as cli
from jupiter_bot.execution import engine as E
from jupiter_bot.execution import gates
from jupiter_bot.execution import mandate as M
from jupiter_bot.research import lock as L
from jupiter_bot.research.strategies import STRATEGIES
from jupiter_bot.tests import execution_fakes as F
from jupiter_bot.tests.guard import setUpModule, tearDownModule  # noqa: F401

PARAMS = {"lookback_min": 240, "rebalance_min": 240}


class P2Gate(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = F.Env(self.dir.name)
        self.env.mandate()
        for name in (L.PLAN, *L.CODE):
            path = self.env.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# %s\n" % name)
        plan_sha, code_sha = L.hashes(self.env.repo)
        self.env.paths.plan_lock.parent.mkdir(parents=True)
        self.env.paths.plan_lock.write_text(json.dumps({"plan_sha256": plan_sha, "code_sha256": code_sha}))
        self.plan_sha = plan_sha
        self.env.paths.verdicts.mkdir()

    def tearDown(self):
        self.dir.cleanup()

    def verdict(self, name="v1", **changes):
        record = {"label": "holdout", "verdict": "PASS", "strategy": "tsmom", "params": PARAMS,
                  "plan_sha256": self.plan_sha, "evaluation_run_ids": ["r1"], "created_at": 0.0, "checks": []}
        record.update(changes)
        (self.env.paths.verdicts / ("%s.json" % name)).write_text(json.dumps(record))

    def gate(self):
        return gates.evaluate(self.env.paths, F.NOW, None).gate("p2_holdout_pass")

    def test_pass_only_for_matching_holdout_verdict(self):
        self.assertFalse(self.gate()["ok"])
        for i, change in enumerate([dict(label="development", verdict="PASS_DEV"), dict(verdict="FAIL"),
                                    dict(verdict="INCONCLUSIVE"), dict(plan_sha256="0" * 64),
                                    dict(strategy="reversal"), dict(params={"lookback_min": 1440, "rebalance_min": 240})]):
            self.verdict("bad%d" % i, **change)
        (self.env.paths.verdicts / "broken.json").write_text("{nope")
        self.assertFalse(self.gate()["ok"])
        self.verdict()
        gate = self.gate()
        self.assertTrue(gate["ok"], gate["detail"])
        (self.env.repo / L.CODE[0]).write_text("changed = True\n")      # code edited after the lock
        gate = self.gate()
        self.assertFalse(gate["ok"])
        self.assertIn("changed since the lock", gate["detail"])

    def test_no_lock(self):
        self.verdict()
        self.env.paths.plan_lock.unlink()
        self.assertIn("not locked", self.gate()["detail"])

    def test_review_gate_needs_exact_line(self):
        for text, ok in (("Verdict: APPROVED\n", True), ("  Verdict: APPROVED  \n", True),
                         ("Verdict: APPROVED?\n", False), ("verdict: approved\n", False), ("", False)):
            self.env.paths.review.write_text(text)
            self.assertEqual(gates.evaluate(self.env.paths, F.NOW, None).gate("review_done")["ok"], ok, text)


class Snapshot(unittest.TestCase):
    def test_default_snapshot_reads_journal_readonly_with_strategy_bars(self):
        paths = mock.Mock(journal="/x/obs.db")
        mandate = mock.Mock(strategy="tsmom", params=PARAMS)
        journal = mock.Mock()
        with mock.patch("jupiter_bot.marketdata.journal.Journal", return_value=journal) as opened, \
                mock.patch("jupiter_bot.marketdata.snapshot.build_snapshot", return_value={"ok": 1}) as built:
            self.assertEqual(E.default_snapshot(paths)(mandate, 123.0), {"ok": 1})
        opened.assert_called_once_with("/x/obs.db", readonly=True)
        built.assert_called_once_with(journal, 123.0, bars=STRATEGIES["tsmom"][1](PARAMS))
        journal.close.assert_called_once()
        snapshot = {"as_of": 0.0, "candles": []}
        self.assertEqual(E.default_target(mandate, snapshot), "FLAT")


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.env = F.Env(self.dir.name)
        self.base = ["--mandate", str(self.env.paths.mandate), "--data-dir", str(self.env.paths.ledger.parent)]

    def tearDown(self):
        self.dir.cleanup()

    def run_cli(self, *args, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(self.base + list(args), **kwargs)
        return code, out.getvalue(), err.getvalue()

    def test_check_mandate_hides_secrets(self):
        code, out, _ = self.run_cli("check-mandate")
        self.assertEqual(code, 1)
        self.env.mandate()
        code, out, _ = self.run_cli("check-mandate")
        self.assertEqual(code, 0, out)
        self.assertNotIn("secret-token", out)
        self.assertNotIn(str(self.env.keypair), out)
        self.assertIn(F.RPC_HOST, out)

    def test_arm_dry_run_via_cli_needs_phrase_and_tty(self):
        self.env.mandate()
        code, _, err = self.run_cli("arm", "--dry-run", ask=lambda p: "ARM DRY_RUN %s" % F.WALLET[:8],
                                    interactive=False)
        self.assertEqual(code, 1)
        self.assertIn("interactive terminal", err)
        code, out, _ = self.run_cli("arm", "--dry-run", ask=lambda p: "ARM DRY_RUN %s" % F.WALLET[:8],
                                    interactive=True)
        self.assertEqual(code, 0)
        self.assertIn("ARMED DRY_RUN", out)
        code, out, _ = self.run_cli("status")
        self.assertIn("Mode: DRY_RUN", out)
        code, _, err = self.run_cli("arm", "--override", "mandate_valid", ask=lambda p: "x", interactive=True)
        self.assertEqual(code, 1)
        self.assertIn("never be overridden", err)
        self.assertEqual(self.run_cli("disarm")[0], 0)
        self.assertFalse(self.env.paths.arm.exists())
        self.assertEqual(self.run_cli("disarm")[0], 0)        # idempotent kill switch

    def test_resolve_with_nothing_pending(self):
        self.env.mandate()
        code, out, _ = self.run_cli("resolve")
        self.assertEqual((code, json.loads(out)), (0, []))

    def test_mandate_sha_is_of_the_file_bytes(self):
        self.env.mandate()
        self.assertEqual(M.parse(self.env.paths.mandate.read_bytes()).sha256, M.read(self.env.paths.mandate)[1])


if __name__ == "__main__":
    unittest.main()
